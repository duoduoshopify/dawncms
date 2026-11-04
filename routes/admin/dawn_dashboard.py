# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/dashboard.py
# 仪表盘：真实数据总览 + 待办 + 快捷操作

from fasthtml.common import *

from dawn_config import dawn_site_name
from blog.dawn_factory import dawn_get_blog_db
from .dawn_shell import _dawn_admin_shell, _dawn_require_admin, DAWN_BTN, DAWN_BTN_GHOST


async def _dawn_stats() -> dict:
    db = await dawn_get_blog_db()
    try:
        async def one(sql, *args):
            row = await (await db.execute(sql, args)).fetchone()
            return row[0] if row else 0

        return {
            "posts_total": await one("SELECT COUNT(*) FROM posts"),
            "posts_pub": await one("SELECT COUNT(*) FROM posts WHERE is_published=1"),
            "posts_draft": await one("SELECT COUNT(*) FROM posts WHERE is_published=0"),
            "posts_sched": await one("SELECT COUNT(*) FROM posts WHERE scheduled_at != '' AND scheduled_at > datetime('now', 'localtime')"),
            "views": await one("SELECT COALESCE(SUM(view_count),0) FROM posts"),
            "members": await one("SELECT COUNT(*) FROM members"),
            "subs": await one("SELECT COUNT(*) FROM newsletter_subscribers WHERE is_active=1"),
            "series": await one("SELECT COUNT(*) FROM series"),
        }
    finally:
        await db.close()


async def _dawn_recent_posts(limit: int = 6) -> list:
    db = await dawn_get_blog_db()
    import aiosqlite
    db.row_factory = aiosqlite.Row
    try:
        rows = await (await db.execute(
            "SELECT id, title, category, is_published, view_count, created_at FROM posts ORDER BY updated_at DESC LIMIT ?",
            (limit,))).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


def _dawn_stat_card(icon: str, label: str, value, sub: str = "", href: str = ""):
    inner = Div(
        Div(
            Span(icon, cls="text-xl"),
            Span(label, cls="text-xs font-semibold", style="color:var(--adm-dim)"),
            cls="flex items-center gap-2 mb-2"
        ),
        Div(str(value), cls="text-3xl font-black text-white tracking-tight"),
        Div(sub, cls="text-[11px] mt-1", style="color:var(--adm-faint)") if sub else None,
        cls="adm-card p-5"
    )
    return A(inner, href=href, cls="block hover:opacity-90") if href else inner


def dawn_setup(app):
    @app.get("/dadmin")
    async def admin_dashboard(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")

        s = await _dawn_stats()
        recent = await _dawn_recent_posts()

        stat_cards = Div(
            _dawn_stat_card("📝", "文章", s["posts_total"], f"已发布 {s['posts_pub']} · 草稿 {s['posts_draft']}", "/dadmin/posts"),
            _dawn_stat_card("👀", "总阅读量", s["views"], "", "/dadmin/posts"),
            _dawn_stat_card("👥", "会员", s["members"], "", "/dadmin/members"),
            _dawn_stat_card("📮", "订阅用户", s["subs"], "", "/dadmin/newsletter"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        )

        todos = []
        if s["posts_draft"]:
            todos.append(A(f"✏️ 有 {s['posts_draft']} 篇草稿待完成", href="/dadmin/posts", cls="block py-2 text-sm hover:text-white", style="color:var(--adm-dim)"))
        if s["posts_sched"]:
            todos.append(A(f"⏰ {s['posts_sched']} 篇文章定时待发布", href="/dadmin/posts", cls="block py-2 text-sm hover:text-white", style="color:var(--adm-dim)"))
        if not todos:
            todos.append(Div("一切就绪，没有待办事项", cls="py-2 text-sm", style="color:var(--adm-faint)"))

        recent_rows = [
            Div(
                Span("🟢" if p["is_published"] else "⚪", cls="mr-2 text-xs"),
                A(p["title"] or "无标题", href=f"/dadmin/post/edit/{p['id']}", cls="text-sm text-slate-200 hover:text-indigo-300 font-medium"),
                Span(p.get("category") or "", cls="ml-2 text-[11px]", style="color:var(--adm-faint)"),
                Span(f"{p.get('view_count', 0)} 阅读", cls="ml-auto text-[11px]", style="color:var(--adm-faint)"),
                cls="flex items-center py-2.5",
                style="border-bottom:1px solid var(--adm-line)"
            ) for p in recent
        ]

        quick = Div(
            A("✏️ 写新文章", href="/dadmin/post/new", cls=DAWN_BTN),
            A("🎨 切换主题", href="/dadmin/appearance", cls=DAWN_BTN_GHOST + " inline-block ml-2 py-2.5"),
            A("📮 发 Newsletter", href="/dadmin/newsletter", cls=DAWN_BTN_GHOST + " inline-block ml-2 py-2.5"),
            cls="mb-6"
        )

        content = Div(
            quick,
            stat_cards,
            Div(
                Div(
                    H2("待办", cls="text-white font-bold text-sm mb-2"),
                    *todos,
                    cls="adm-card p-5"
                ),
                Div(
                    H2("最近更新", cls="text-white font-bold text-sm mb-2"),
                    *recent_rows,
                    cls="adm-card p-5"
                ),
                cls="grid grid-cols-1 lg:grid-cols-2 gap-4"
            ),
        )
        return _dawn_admin_shell("dashboard", content)
