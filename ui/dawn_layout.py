# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# ui/layout.py
# 独立博客站点布局（宣纸墨韵 · 浅色文人风）

import json
import sqlite3
from pathlib import Path
from fasthtml.common import *
from dawn_config import dawn_site_name, dawn_site_tagline, DAWN_SITE_BASE_URL
from dawn_themes import dawn_theme_root_css, dawn_layout_override_css, dawn_get_layout_mode

DAWN_DB_PATH = str(Path(__file__).resolve().parent.parent / "database" / "blog.db")

DAWN_DEFAULT_HEADER_NAV = [{"label": "首页", "url": "/"}, {"label": "关于", "url": "/about"}]
DAWN_DEFAULT_FOOTER_NAV = [{"label": "关于", "url": "/about"}, {"label": "RSS 订阅", "url": "/feed.xml"}]

DAWN_BASE_CSS = """
    body { background: var(--paper); color: var(--ink-soft); font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif; transition: background .3s ease, color .3s ease; }
    ::selection { background: rgba(var(--accent-rgb),.18); }
    .ff-serif { font-family: var(--serif); }
    .btn-primary { display:inline-block; padding:.75rem 1.8rem; border-radius:999px; background:var(--ink); color:var(--paper); font-weight:600; letter-spacing:.05em; transition:all .25s ease; }
    .btn-primary:hover { background:var(--accent); }
    .btn-secondary { display:inline-block; padding:.75rem 1.8rem; border-radius:999px; border:1px solid var(--ink); color:var(--ink); font-weight:600; letter-spacing:.05em; transition:all .25s ease; }
    .btn-secondary:hover { border-color:var(--accent); color:var(--accent); }
    .line-clamp-2 { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .line-clamp-3 { display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
    .paper-card { background:var(--card); border:1px solid var(--hairline); transition:all .3s ease; }
    .paper-card:hover { border-color:var(--hairline-strong); box-shadow:0 12px 32px -16px rgba(var(--ink-rgb),.18); transform:translateY(-3px); }
    .eyebrow { color:var(--accent); font-size:.75rem; font-weight:700; letter-spacing:.35em; }
    .hairline-b { border-bottom:1px solid var(--hairline); }
    a { transition: color .2s ease; }
"""


def dawn_get_nav_links(location: str) -> list:
    """同步读取导航链接（layout 为同步函数）；失败时回退默认导航"""
    try:
        db = sqlite3.connect(DAWN_DB_PATH, timeout=5)
        rows = db.execute(
            "SELECT label, url FROM nav_links WHERE location = ? AND is_active = 1 ORDER BY sort_order, id",
            (location,)).fetchall()
        db.close()
        links = [{"label": r[0], "url": r[1]} for r in rows]
        if links:
            return links
    except Exception:
        pass
    return list(DAWN_DEFAULT_HEADER_NAV if location == "header" else DAWN_DEFAULT_FOOTER_NAV)


class DawnSafeHTML:
    def __init__(self, html):
        self._html = html

    def __html__(self):
        return self._html


def dawn_wrapper(content, title: str = "", description: str = "", canonical_url: str = "",
            extra_meta: list | None = None, session: dict | None = None, full_bleed: bool = True):
    page_title = f"{title} - {dawn_site_name()}" if title else dawn_site_name()
    is_admin = bool((session or {}).get("is_admin"))
    member_name = (session or {}).get("member_name", "")

    if is_admin:
        account_links = [
            A("退出", href="/dadmin/logout", cls="text-[var(--faint)] hover:text-[var(--ink-2)] text-sm ml-7"),
        ]
    elif member_name:
        account_links = [
            Span(f"👤 {member_name}", cls="text-[var(--ink-2)] text-sm ml-7"),
            A("退出", href="/logout", cls="text-[var(--faint)] hover:text-[var(--ink-2)] text-sm ml-7"),
        ]
    else:
        account_links = [
            A("登录", href="/login", cls="text-[var(--ink-2)] hover:text-[var(--ink)] text-sm ml-7"),
            A("注册", href="/register", cls="ml-5 px-4 py-1.5 rounded-full bg-[var(--ink)] text-[var(--paper)] text-sm font-semibold hover:bg-[var(--accent)]"),
        ]

    head_items = [
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Title(page_title),
        Meta(name="description", content=description or dawn_site_tagline()),
        Link(rel="canonical", href=canonical_url) if canonical_url else None,
        Link(rel="alternate", type="application/rss+xml", title=f"{dawn_site_name()} RSS", href="/feed.xml"),
        Script(src="https://cdn.tailwindcss.com"),
        Script(src="https://unpkg.com/htmx.org@1.9.10"),
        Style(dawn_theme_root_css() + DAWN_BASE_CSS + dawn_layout_override_css()),
    ]
    if extra_meta:
        head_items.extend(extra_meta)

    header_links = dawn_get_nav_links("header")
    footer_links = dawn_get_nav_links("footer")

    nav = Div(
        Div(
            A(
                Span(dawn_site_name()[:1].upper(), cls="w-8 h-8 mr-2.5 rounded-lg bg-[var(--accent)] text-[var(--paper)] ff-serif font-black text-lg flex items-center justify-center"),
                Span(dawn_site_name(), cls="ff-serif text-[var(--ink)] font-black text-xl tracking-wide"),
                href="/", cls="flex items-center"
            ),
            Div(
                *[A(l["label"], href=l["url"], cls="text-[var(--ink-2)] hover:text-[var(--accent)] text-sm font-medium ml-7") for l in header_links],
                *account_links,
                cls="flex items-center"
            ),
            cls="max-w-[1200px] mx-auto px-6 py-4 flex items-center justify-between"
        ),
        cls="hairline-b sticky top-0 z-50 backdrop-blur bg-[var(--paper)]/90"
    )

    footer = Div(
        Div(
            Div(
                Div(
                    Span("✉", cls="inline-block w-9 h-9 rounded-full border border-[var(--hairline)] text-[var(--accent)] text-sm leading-9 text-center mb-3"),
                    P(f"订阅{dawn_site_name()}", cls="ff-serif text-[var(--ink)] font-bold text-lg mb-1"),
                    P("新文章发布时，第一时间寄到你的邮箱", cls="text-[var(--muted)] text-xs mb-4"),
                    Form(
                        Input(type="email", name="email", required=True, placeholder="you@example.com",
                              cls="flex-1 min-w-0 px-4 py-2.5 rounded-full bg-white border border-[var(--hairline)] text-[var(--ink-soft)] text-sm focus:outline-none focus:border-[var(--accent)]"),
                        Button("订阅", type="submit",
                               cls="ml-2 px-5 py-2.5 rounded-full bg-[var(--ink)] text-[var(--paper)] text-sm font-semibold hover:bg-[var(--accent)] shrink-0"),
                        method="post", action="/subscribe",
                        cls="flex items-center max-w-sm mx-auto"
                    ),
                    cls="py-10 text-center"
                ),
                cls="hairline-b"
            ),
            Div(
                *[A(l["label"], href=l["url"], cls="text-[var(--muted)] hover:text-[var(--accent)] text-xs") for l in footer_links],
                cls="flex items-center justify-center gap-6 mt-8 mb-4"
            ) if footer_links else None,
            P(f"© 2026 {dawn_site_name()} · {dawn_site_tagline()}", cls="text-[var(--faint)] text-xs text-center"),
            P("Powered by DawnCMS", cls="text-[var(--faint)] text-xs text-center mt-1 opacity-70"),
            P(f"🖋️ {dawn_site_tagline()}", cls="ff-serif text-[var(--faint)] text-xs text-center mt-2 tracking-widest"),
            cls="max-w-[1200px] mx-auto px-6 pb-10"
        ),
        cls="mt-16"
    )

    body_cls = f"min-h-screen layout-{dawn_get_layout_mode()}"

    return Html(
        Head(*[h for h in head_items if h is not None]),
        Body(
            nav,
            content,
            footer,
            cls=body_cls
        ),
        lang="zh-CN"
    )
