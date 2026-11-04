# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/auth.py
# 后台登录 / 退出

import os
from datetime import datetime
from pathlib import Path
from fasthtml.common import *

from dawn_config import DAWN_ADMIN_PASSWORD, dawn_site_name, DAWN_DEFAULT_AUTHOR, DAWN_SITE_BASE_URL, DAWN_EMAIL_ENABLED
from ui.dawn_layout import DawnSafeHTML
from services.dawn_blog_service import DawnBlogService
from services.dawn_image_service import DawnBlogImageService
from services.dawn_member_service import DawnMemberService
from services.dawn_email_service import DawnEmailService
from blog.dawn_crud import DawnBlogCRUD

from .dawn_shell import _dawn_admin_shell, _dawn_require_admin, _dawn_msg, DAWN_INPUT, DAWN_LABEL, DAWN_BTN, DAWN_BTN_DANGER, DAWN_BTN_GHOST



def dawn_setup(app):
    @app.get("/dadmin/login")
    async def admin_login(session, error: str = ""):
        if _dawn_require_admin(session):
            return RedirectResponse("/dadmin")
        return Html(
            Head(
                Meta(charset="utf-8"),
                Title(f"登录 - {dawn_site_name()}"),
                Script(src="https://cdn.tailwindcss.com"),
                Style("body{background:#020617}"),
            ),
            Body(
                Div(
                    Form(
                        H1("🔐 博客后台登录", cls="text-white font-black text-xl mb-6 text-center"),
                        _dawn_msg("密码错误", ok=False) if error else None,
                        Input(type="password", name="password", placeholder="管理密码", required=True, cls=DAWN_INPUT),
                        Button("登录", type="submit", cls=DAWN_BTN + " w-full mt-4"),
                        method="post", action="/dadmin/login",
                        cls="w-full max-w-sm p-8 rounded-2xl border border-slate-800 bg-slate-900/60"
                    ),
                    cls="min-h-screen flex items-center justify-center px-6"
                )
            ),
            lang="zh-CN"
        )

    @app.post("/dadmin/login")
    async def admin_login_post(session, password: str = ""):
        if password and password == DAWN_ADMIN_PASSWORD:
            session["is_admin"] = True
            return RedirectResponse("/dadmin", status_code=303)
        return RedirectResponse("/dadmin/login?error=1", status_code=303)

    @app.get("/dadmin/logout")
    async def admin_logout(session):
        session.pop("is_admin", None)
        return RedirectResponse("/")

