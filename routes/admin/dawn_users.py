# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/users.py
# 会员 / 邮件订阅

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
    @app.get("/dadmin/members")
    async def admin_members(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        members = await DawnMemberService.list_members()
        rows = [Tr(
            Td(str(m.get("id")), cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td(
                Div(m.get("email", ""), cls="text-slate-200 text-sm font-semibold"),
                Div(m.get("name", ""), cls="text-slate-500 text-xs"),
            ),
            Td("📧 已验证" if m.get("email_verified") else "未验证",
               cls=f"px-3 py-2.5 text-xs {'text-emerald-400' if m.get('email_verified') else 'text-slate-600'}"),
            Td((m.get("created_at") or "")[:16], cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td((m.get("last_login_at") or "从未登录")[:16], cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td("✅ 正常" if m.get("is_active") else "🚫 已禁用",
               cls=f"px-3 py-2.5 text-xs {'text-emerald-400' if m.get('is_active') else 'text-red-400'}"),
            Td(
                Form(Button("禁用" if m.get("is_active") else "启用", type="submit", cls=DAWN_BTN_GHOST),
                     method="post", action=f"/dadmin/member/toggle/{m.get('id')}", style="display:inline"),
                Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('确认删除该会员？')"),
                     method="post", action=f"/dadmin/member/delete/{m.get('id')}", style="display:inline;margin-left:6px"),
                cls="px-3 py-2.5 whitespace-nowrap"
            ),
            cls="border-b border-slate-800/60 hover:bg-slate-900/40"
        ) for m in members]

        return _dawn_admin_shell("members", Div(
            _dawn_msg(msg) if msg else None,
            Div(
                H1("会员管理", cls="text-2xl font-black text-white"),
                Span(f"共 {len(members)} 位会员", cls="text-slate-500 text-sm"),
                cls="flex items-center justify-between mb-6"
            ),
            Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in ["ID", "邮箱 / 昵称", "邮箱验证", "注册时间", "最近登录", "状态", "操作"]])),
                Tbody(*rows) if rows else Tbody(Tr(Td("暂无会员注册。", colspan="7", cls="px-3 py-10 text-center text-slate-500"))),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"
            ),
        ))

    @app.post("/dadmin/member/toggle/{member_id}")
    async def admin_member_toggle(session, member_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        member = await DawnMemberService.get_member(member_id)
        if member:
            await DawnMemberService.set_active(member_id, not member.get("is_active"))
        return RedirectResponse("/dadmin/members", status_code=303)

    @app.post("/dadmin/member/delete/{member_id}")
    async def admin_member_delete(session, member_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnMemberService.delete_member(member_id)
        return RedirectResponse("/dadmin/members?msg=已删除", status_code=303)

    # ---- 标签管理 ----

    @app.get("/dadmin/newsletter")
    async def admin_newsletter(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        subscribers = await DawnBlogCRUD.list_newsletter_subscribers()
        active = [s for s in subscribers if s.get("is_active")]
        posts = await DawnBlogService.get_all_posts_for_admin()
        published = [p for p in posts if p.get("is_published")]

        rows = [Tr(
            Td(s.get("email", ""), cls="px-3 py-2.5 text-slate-200 text-sm"),
            Td((s.get("created_at") or "")[:16], cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td("✅ 订阅中" if s.get("is_active") else "🚫 已退订",
               cls=f"px-3 py-2.5 text-xs {'text-emerald-400' if s.get('is_active') else 'text-red-400'}"),
            cls="border-b border-slate-800/60"
        ) for s in subscribers]

        smtp_warn = None if DAWN_EMAIL_ENABLED else Div(
            "⚠️ 未配置 SMTP（.env 中 DAWN_SMTP_SERVER / DAWN_SMTP_USER / DAWN_SMTP_PASSWORD），群发不会真正发送，只会记录日志。",
            cls="mb-4 px-4 py-3 rounded-lg text-sm font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30")

        return _dawn_admin_shell("newsletter", Div(
            _dawn_msg(msg) if msg else None,
            smtp_warn,
            Div(
                H1("邮件订阅", cls="text-2xl font-black text-white"),
                Span(f"共 {len(subscribers)} 人 · {len(active)} 人订阅中", cls="text-slate-500 text-sm"),
                cls="flex items-center justify-between mb-6"
            ),
            Div(
                H2("📨 推送文章给订阅者", cls="text-white font-bold text-sm mb-3"),
                Form(
                    Select(
                        *[Option(f"#{p.get('id')} {p.get('title', '')}", value=str(p.get("id"))) for p in published],
                        name="post_id", cls=DAWN_INPUT + " flex-1 min-w-0"),
                    Button("发送", type="submit", cls=DAWN_BTN + " ml-2 shrink-0",
                           onclick=f"return confirm('确认向 {len(active)} 位订阅者发送该文章？')"),
                    method="post", action="/dadmin/newsletter/send",
                    cls="flex items-center"
                ) if published else P("暂无已发布文章", cls="text-slate-600 text-sm"),
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in ["邮箱", "订阅时间", "状态"]])),
                Tbody(*rows) if rows else Tbody(Tr(Td("暂无订阅者。前台页脚有订阅入口。", colspan="3", cls="px-3 py-10 text-center text-slate-500"))),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"
            ),
        ))

    @app.post("/dadmin/newsletter/send")
    async def admin_newsletter_send(session, post_id: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        post = await DawnBlogService.get_post_by_id(int(post_id or 0))
        if not post or not post.get("is_published"):
            return RedirectResponse("/dadmin/newsletter?msg=文章不存在或未发布", status_code=303)
        categories = await DawnBlogService.get_categories()
        cat_slug = next((c.get("slug") for c in categories if c.get("name") == post.get("category")), "uncategorized")
        dawn_post_url = f"{DAWN_SITE_BASE_URL}/{cat_slug}/{post.get('slug', '')}"
        subscribers = await DawnBlogCRUD.list_newsletter_subscribers(active_only=True)
        sent, failed = 0, 0
        for s in subscribers:
            ok, _ = await DawnEmailService.send_newsletter(s["email"], s["token"], post, dawn_post_url)
            sent += 1 if ok else 0
            failed += 0 if ok else 1
        return RedirectResponse(f"/dadmin/newsletter?msg=推送完成：成功 {sent}，失败 {failed}", status_code=303)

    # ---- 导航管理（头部 / 底部链接可编辑）----

