# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/exporter/plugin.py
# 内置示例插件：数据导出（文章 / 订阅者 → JSON / CSV）

import csv
import io
import json
from datetime import datetime

from fasthtml.common import *
from starlette.responses import StreamingResponse

from routes.admin.dawn_shell import _dawn_admin_shell, _dawn_require_admin, DAWN_BTN, dawn_register_admin_page
from services.dawn_blog_service import DawnBlogService
from blog.dawn_factory import dawn_get_blog_db
import aiosqlite

DAWN_PLUGIN = {
    "key": "exporter",
    "label": "数据导出",
    "group": "插件",
    "icon": "📦",
    "url": "/dadmin/plugins/export",
}


async def _dawn_export_posts(fmt: str):
    posts = await DawnBlogService.get_all_posts_for_admin()
    for p in posts:
        p.pop("content_html", None)
    if fmt == "json":
        payload = json.dumps(posts, ensure_ascii=False, indent=2).encode("utf-8")
        media, fname = "application/json", "posts.json"
    else:
        buf = io.StringIO()
        keys = ["id", "title", "slug", "category", "is_published", "visibility",
                "view_count", "author", "created_at", "updated_at", "excerpt"]
        w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(posts)
        payload, media, fname = buf.getvalue().encode("utf-8-sig"), "text/csv", "posts.csv"
    return payload, media, fname


async def _dawn_export_subscribers(fmt: str):
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row
    rows = await (await db.execute(
        "SELECT email, is_active, subscribed_at FROM newsletter_subscribers ORDER BY subscribed_at DESC"
    )).fetchall()
    await db.close()
    subs = [dict(r) for r in rows]
    if fmt == "json":
        payload = json.dumps(subs, ensure_ascii=False, indent=2).encode("utf-8")
        return payload, "application/json", "subscribers.json"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["email", "is_active", "subscribed_at"])
    w.writeheader()
    w.writerows(subs)
    return buf.getvalue().encode("utf-8-sig"), "text/csv", "subscribers.csv"


def dawn_setup(app):
    dawn_register_admin_page(DAWN_PLUGIN["group"], DAWN_PLUGIN["key"], DAWN_PLUGIN["label"], DAWN_PLUGIN["url"], DAWN_PLUGIN["icon"])

    @app.get("/dadmin/plugins/export")
    async def plugin_export_page(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        posts = await DawnBlogService.get_all_posts_for_admin()
        content = Div(
            Div(
                H2("导出文章", cls="text-white font-bold text-sm mb-1"),
                P(f"共 {len(posts)} 篇（含草稿，正文不导出）", cls="text-xs mb-4", style="color:var(--adm-dim)"),
                A("⬇ 下载 JSON", href="/dadmin/plugins/export/posts.json", cls=DAWN_BTN),
                A("⬇ 下载 CSV", href="/dadmin/plugins/export/posts.csv", cls=DAWN_BTN + " ml-2"),
                cls="adm-card p-6 mb-4"
            ),
            Div(
                H2("导出订阅者", cls="text-white font-bold text-sm mb-1"),
                P("含退订状态与订阅时间", cls="text-xs mb-4", style="color:var(--adm-dim)"),
                A("⬇ 下载 JSON", href="/dadmin/plugins/export/subscribers.json", cls=DAWN_BTN),
                A("⬇ 下载 CSV", href="/dadmin/plugins/export/subscribers.csv", cls=DAWN_BTN + " ml-2"),
                cls="adm-card p-6"
            ),
        )
        return _dawn_admin_shell("exporter", content, title="数据导出")

    @app.get("/dadmin/plugins/export/posts.{fmt}")
    async def plugin_export_posts(session, fmt: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if fmt not in ("json", "csv"):
            return Response("unsupported format", status_code=400)
        payload, media, fname = await _dawn_export_posts(fmt)
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        return Response(payload, media_type=media, headers={
            "Content-Disposition": f'attachment; filename="{ts}-{fname}"'
        })

    @app.get("/dadmin/plugins/export/subscribers.{fmt}")
    async def plugin_export_subs(session, fmt: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if fmt not in ("json", "csv"):
            return Response("unsupported format", status_code=400)
        payload, media, fname = await _dawn_export_subscribers(fmt)
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        return Response(payload, media_type=media, headers={
            "Content-Disposition": f'attachment; filename="{ts}-{fname}"'
        })
