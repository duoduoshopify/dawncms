# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# ui/blog_pages.py
# 博客前台列表页渲染（宣纸墨韵 · 浅色文人风）




def dawn_category_slug_map(categories: list) -> dict:
    return {c.get("name", ""): c.get("slug", "") for c in categories}


def dawn_post_url(post: dict, categories: list) -> str:
    cat_map = dawn_category_slug_map(categories)
    cat_slug = cat_map.get(post.get("category", ""), "uncategorized")
    return f"/{cat_slug}/{post.get('slug', '')}"


def dawn_category_url(cat_slug: str | None = "", page: int = 1) -> str:
    slug = str(cat_slug or "").strip()
    if not slug:
        return f"/?page={page}" if page > 1 else "/"
    base = f"/{slug}"
    return f"{base}?page={page}" if page > 1 else base


def dawn_cover_url(post: dict) -> str:
    cover = (post or {}).get("cover_image", "")
    if cover:
        return _dawn_themed_cover(cover)
    return "/static/images/blog-fallback-cover.svg"


def _dawn_themed_cover(cover: str) -> str:
    """演示封面跟随当前主题：/uploads/blog/covers/series-XX.svg → covers/{主题key}/series-XX.svg（文件存在才替换）"""
    prefix = "/uploads/blog/covers/"
    if not cover.startswith(prefix):
        return cover
    rest = cover[len(prefix):]
    if not rest or "/" in rest:
        return cover
    try:
        import os
        from dawn_themes import dawn_get_active_theme_key
        key = dawn_get_active_theme_key()
        if key and os.path.isfile(f"static{prefix}{key}/{rest}"):
            return f"{prefix}{key}/{rest}"
    except Exception:
        pass
    return cover




DAWN_LIST_CSS = """
    .masthead { background: radial-gradient(circle at 50% 0%, rgba(var(--accent-rgb),.05) 0%, transparent 60%); }
    .cat-tab { position:relative; padding:.4rem .2rem; color:var(--ink-2); font-size:.92rem; }
    .cat-tab:hover { color:var(--ink); }
    .cat-tab.active { color:var(--accent); font-weight:700; }
    .cat-tab.active::after { content:''; position:absolute; left:0; right:0; bottom:-6px; height:2px; background:var(--accent); border-radius:2px; }
    .card-title { transition: color .25s ease; }
    .group:hover .card-title { color:var(--accent); }
    .feature-grid { align-items: stretch; }
    .feature-cover { aspect-ratio: 16/10; border-bottom:1px solid var(--hairline-soft); }
    .list-cover { aspect-ratio: 16/9; border-bottom:1px solid var(--hairline-soft); }
    .cover-img { transition: transform .5s ease; }
    .group:hover .cover-img { transform: scale(1.03); }
"""


