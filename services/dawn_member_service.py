# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# services/member_service.py
# 会员服务（注册 / 登录 / 查询）

import hashlib
import re
import secrets
from datetime import datetime

import aiosqlite

from blog.dawn_factory import dawn_get_blog_db

DAWN_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DAWN_ITERATIONS = 100_000


def _dawn_hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), DAWN_ITERATIONS)
    return f"{salt}${digest.hex()}"


def _dawn_verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_dawn_hash_password(password, salt), stored)


class DawnMemberService:
    @staticmethod
    async def register(email: str, password: str, name: str = "") -> tuple[bool, str, int]:
        email = (email or "").strip().lower()
        if not DAWN_EMAIL_RE.match(email):
            return False, "邮箱格式不正确", 0
        if len(password or "") < 6:
            return False, "密码至少 6 位", 0
        db = await dawn_get_blog_db()
        try:
            exists = await (await db.execute("SELECT id FROM members WHERE email=?", (email,))).fetchone()
            if exists:
                return False, "该邮箱已注册，请直接登录", 0
            cur = await db.execute(
                "INSERT INTO members (email, password_hash, name) VALUES (?, ?, ?)",
                (email, _dawn_hash_password(password), (name or "").strip()[:40]),
            )
            await db.commit()
            return True, "注册成功", cur.lastrowid
        finally:
            await db.close()

    @staticmethod
    async def authenticate(email: str, password: str) -> tuple[bool, str, dict | None]:
        email = (email or "").strip().lower()
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        try:
            row = await (await db.execute("SELECT * FROM members WHERE email=?", (email,))).fetchone()
            if not row:
                return False, "邮箱或密码错误", None
            member = dict(row)
            if not member.get("is_active"):
                return False, "账号已被禁用", None
            if not _dawn_verify_password(password or "", member.get("password_hash", "")):
                return False, "邮箱或密码错误", None
            await db.execute("UPDATE members SET last_login_at=? WHERE id=?",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), member["id"]))
            await db.commit()
            return True, "登录成功", member
        finally:
            await db.close()

    @staticmethod
    async def get_member(member_id: int) -> dict | None:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        try:
            row = await (await db.execute("SELECT id, email, name, is_active, email_verified, created_at, last_login_at FROM members WHERE id=?", (int(member_id),))).fetchone()
            return dict(row) if row else None
        finally:
            await db.close()

    @staticmethod
    async def list_members() -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        try:
            rows = await (await db.execute("SELECT id, email, name, is_active, email_verified, created_at, last_login_at FROM members ORDER BY id DESC")).fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    @staticmethod
    async def set_active(member_id: int, active: bool) -> None:
        db = await dawn_get_blog_db()
        try:
            await db.execute("UPDATE members SET is_active=? WHERE id=?", (1 if active else 0, int(member_id)))
            await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def delete_member(member_id: int) -> None:
        db = await dawn_get_blog_db()
        try:
            await db.execute("DELETE FROM members WHERE id=?", (int(member_id),))
            await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def reset_password(member_id: int, new_password: str) -> bool:
        if len(new_password or "") < 6:
            return False
        db = await dawn_get_blog_db()
        try:
            await db.execute("UPDATE members SET password_hash=? WHERE id=?",
                             (_dawn_hash_password(new_password), int(member_id)))
            await db.commit()
            return True
        finally:
            await db.close()
