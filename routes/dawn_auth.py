# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/auth.py
# 会员注册 / 登录 / 退出（页面结构由主题模板 auth.html / message.html 控制）

from fasthtml.common import *

from services.dawn_member_service import DawnMemberService
from services.dawn_email_service import DawnEmailService
from blog.dawn_crud import DawnBlogCRUD
from routes.dawn_frontend import _dawn_render

# 会员页双语：访客带着 site_lang=en Cookie（访问过英文版）时自动渲染英文
DAWN_AUTH_EN = {
    "注册会员": "Create account", "会员登录": "Sign in", "忘记密码": "Forgot password",
    "设置新密码": "Set new password", "检查你的邮箱": "Check your inbox", "邮箱验证": "Email verification",
    "← 返回首页": "← Back to home", "邮箱": "Email", "昵称（可选）": "Name (optional)",
    "密码（至少 6 位）": "Password (6+ chars)", "密码": "Password",
    "注册": "Sign up", "登录": "Sign in",
    "已有账号？": "Already have an account?", "直接登录": "Sign in",
    "还没有账号？": "No account yet?", "免费注册": "Sign up free", "忘记密码？": "Forgot password?",
    "注册邮箱": "Account email", "发送重置链接": "Send reset link",
    "新密码（至少 6 位）": "New password (6+ chars)", "重置密码": "Reset password",
    "如果该邮箱已注册，重置链接已发送，1 小时内有效。": "If that email is registered, a reset link is on its way (valid for 1 hour).",
    "返回登录": "Back to sign in", "✅ 邮箱验证成功": "✅ Email verified",
    "链接无效或已过期": "Link invalid or expired", "返回首页": "Back to home",
}


def _dawn_at(request, zh: str) -> str:
    try:
        if (request.cookies.get("site_lang") or "").startswith("en"):
            return DAWN_AUTH_EN.get(zh, zh)
    except Exception:
        pass
    return zh


def _dawn_lang(request) -> str:
    return "en" if _dawn_at(request, "邮箱") == "Email" else ""


def _dawn_auth_page(request, session, title: str, fields: list, action: str, button: str,
                    tips: list | None = None, error: str = ""):
    return _dawn_render(
        "auth.html", session, lang=_dawn_lang(request),
        title=title,
        robots_meta="noindex,nofollow",
        auth_title=title, auth_fields=fields, auth_action=action,
        auth_button=button, auth_tips=tips or [], auth_error=error,
        auth_back_label=_dawn_at(request, "← 返回首页"),
    )


def _dawn_message_page(request, session, title: str, body: str = "",
                       link_text: str = "", link_url: str = "/"):
    return _dawn_render(
        "message.html", session, lang=_dawn_lang(request),
        title=title,
        robots_meta="noindex,nofollow",
        message_title=title, message_body=body,
        message_link_text=link_text or _dawn_at(request, "返回首页"),
        message_link_url=link_url,
    )


def dawn_setup(app):
    @app.get("/register")
    async def register_page(request, session, error: str = ""):
        at = lambda zh: _dawn_at(request, zh)
        fields = [
            {"label": at("邮箱"), "name": "email", "type": "email", "required": True},
            {"label": at("昵称（可选）"), "name": "name", "type": "text"},
            {"label": at("密码（至少 6 位）"), "name": "password", "type": "password", "required": True, "minlength": 6},
        ]
        tips = [{"text": at("已有账号？"), "link_text": at("直接登录"), "link_url": "/login"}]
        return _dawn_auth_page(request, session, at("注册会员"), fields, "/register", at("注册"), tips, error)

    @app.post("/register")
    async def register_post(session, email: str = "", password: str = "", name: str = ""):
        ok, msg, member_id = await DawnMemberService.register(email, password, name)
        if not ok:
            return RedirectResponse(f"/register?error={msg}", status_code=303)
        session["member_id"] = member_id
        session["member_name"] = (name or "").strip() or email.split("@")[0]
        token = await DawnBlogCRUD.create_member_token(member_id, "verify", ttl_minutes=60 * 24)
        await DawnEmailService.send_verify_email(email.strip().lower(), token)
        return RedirectResponse("/", status_code=303)

    @app.get("/login")
    async def login_page(request, session, error: str = "", next: str = ""):
        at = lambda zh: _dawn_at(request, zh)
        fields = [
            {"label": at("邮箱"), "name": "email", "type": "email", "required": True},
            {"label": at("密码"), "name": "password", "type": "password", "required": True},
        ]
        if next:
            fields.insert(0, {"label": "", "name": "next", "type": "hidden", "value": next})
        tips = [
            {"text": at("还没有账号？"), "link_text": at("免费注册"), "link_url": "/register"},
            {"text": "", "link_text": at("忘记密码？"), "link_url": "/forgot-password"},
        ]
        return _dawn_auth_page(request, session, at("会员登录"), fields, "/login", at("登录"), tips, error)

    @app.post("/login")
    async def login_post(session, email: str = "", password: str = "", next: str = ""):
        ok, msg, member = await DawnMemberService.authenticate(email, password)
        if not ok:
            return RedirectResponse(f"/login?error={msg}", status_code=303)
        session["member_id"] = member["id"]
        session["member_name"] = member.get("name") or member["email"].split("@")[0]
        target = next if (next or "").startswith("/") and not next.startswith("//") else "/"
        return RedirectResponse(target, status_code=303)

    @app.get("/logout")
    async def logout(session):
        session.pop("member_id", None)
        session.pop("member_name", None)
        return RedirectResponse("/")

    @app.get("/forgot-password")
    async def forgot_page(request, session, sent: str = ""):
        at = lambda zh: _dawn_at(request, zh)
        if sent:
            return _dawn_message_page(request, session, at("检查你的邮箱"),
                                      at("如果该邮箱已注册，重置链接已发送，1 小时内有效。"),
                                      at("返回登录"), "/login")
        fields = [{"label": at("注册邮箱"), "name": "email", "type": "email", "required": True}]
        return _dawn_auth_page(request, session, at("忘记密码"), fields, "/forgot-password", at("发送重置链接"))

    @app.post("/forgot-password")
    async def forgot_post(email: str = ""):
        member = await DawnBlogCRUD.get_member_by_email(email)
        if member and member.get("is_active"):
            token = await DawnBlogCRUD.create_member_token(member["id"], "reset", ttl_minutes=60)
            await DawnEmailService.send_reset_email(member["email"], token)
        return RedirectResponse("/forgot-password?sent=1", status_code=303)

    @app.get("/reset-password")
    async def reset_page(request, session, token: str = "", error: str = ""):
        at = lambda zh: _dawn_at(request, zh)
        fields = [
            {"label": "", "name": "token", "type": "hidden", "value": token},
            {"label": at("新密码（至少 6 位）"), "name": "password", "type": "password", "required": True, "minlength": 6},
        ]
        return _dawn_auth_page(request, session, at("设置新密码"), fields, "/reset-password", at("重置密码"), error=error)

    @app.post("/reset-password")
    async def reset_post(session, token: str = "", password: str = ""):
        if len(password or "") < 6:
            return RedirectResponse(f"/reset-password?token={token}&error=密码至少 6 位", status_code=303)
        member_id = await DawnBlogCRUD.consume_member_token(token, "reset") if token else 0
        if not member_id:
            return RedirectResponse(f"/reset-password?token={token}&error=链接无效或已过期，请重新申请", status_code=303)
        await DawnMemberService.reset_password(member_id, password)
        member = await DawnMemberService.get_member(member_id)
        if member:
            session["member_id"] = member["id"]
            session["member_name"] = member.get("name") or member["email"].split("@")[0]
        return RedirectResponse("/", status_code=303)

    @app.get("/verify-email")
    async def verify_email(request, session, token: str = ""):
        member_id = await DawnBlogCRUD.consume_member_token(token, "verify") if token else 0
        if member_id:
            await DawnBlogCRUD.mark_email_verified(member_id)
        return _dawn_message_page(
            request, session, _dawn_at(request, "邮箱验证"),
            _dawn_at(request, "✅ 邮箱验证成功") if member_id else _dawn_at(request, "链接无效或已过期"),
            _dawn_at(request, "返回首页"), "/")
