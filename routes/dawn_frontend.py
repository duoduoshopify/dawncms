# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/frontend.py
# 博客前台路由（主题包渲染：/ 列表 / 分类 / 文章 / 搜索 / 标签 / sitemap / feed）

import json
import re
import time
from urllib.parse import quote

from fasthtml.common import *
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, JSONResponse

from dawn_config import dawn_site_name, dawn_site_tagline, DAWN_SITE_BASE_URL, DAWN_DEFAULT_AUTHOR
from services.dawn_blog_service import DawnBlogService
from blog.dawn_crud import DawnBlogCRUD
from ui.dawn_pages import dawn_post_url, dawn_category_url, dawn_category_slug_map, dawn_cover_url, DAWN_LIST_CSS
from ui.dawn_article import DAWN_DOC_CSS, DAWN_DOC_JS, dawn_extract_toc_and_anchors
from ui.dawn_layout import DAWN_BASE_CSS, dawn_get_nav_links
import dawn_themes


def _dawn_is_admin(session) -> bool:
    return bool((session or {}).get("is_admin"))


def _dawn_is_member(session) -> bool:
    return bool((session or {}).get("member_id"))


def _dawn_ctx(session, title="", desc="", canonical=""):
    page_title = f"{title} - {dawn_site_name()}" if title else dawn_site_name()
    nav = dawn_get_nav_links("header")
    base_url = DAWN_SITE_BASE_URL.rstrip("/")
    site_schema = (
        '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "Organization",
            "name": dawn_site_name(), "url": base_url,
            "logo": {"@type": "ImageObject", "url": f"{base_url}/static/logo.svg", "width": 96, "height": 96},
        }, ensure_ascii=False) + '</script>\n'
        '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "WebSite",
            "name": dawn_site_name(), "url": base_url,
            "potentialAction": {"@type": "SearchAction",
                                "target": {"@type": "EntryPoint",
                                           "urlTemplate": f"{base_url}/search?q={{search_term_string}}"},
                                "query-input": "required name=search_term_string"},
        }, ensure_ascii=False) + '</script>'
    )
    global_js = ""
    try:
        from plugins import dawn_collect_hooks_sync
        for res in dawn_collect_hooks_sync("nav_links"):
            if isinstance(res, list):
                nav.extend(res)
        for res in dawn_collect_hooks_sync("global_js"):
            if isinstance(res, str):
                global_js += res
    except Exception:
        pass
    # 主题编辑预览：注入 postMessage 监听器（接收后台编辑器的 CSS 即时覆盖）
    if dawn_themes._dawn_preview_var.get():
        global_js += """<script>
window.addEventListener('message', function(e){
  var d = e.data || {};
  if (d.type !== 'dawn-theme-preview') return;
  var el = document.getElementById('dawn-preview-override');
  if (!el) { el = document.createElement('style'); el.id = 'dawn-preview-override'; document.head.appendChild(el); }
  el.textContent = (d.imports || '') + '\n' + (d.css || '');
});
</script>"""
    return {
        "site_name": dawn_site_name(), "site_tagline": dawn_site_tagline(),
        "site_base_url": DAWN_SITE_BASE_URL.rstrip("/"),
        "site_schema": site_schema,
        "og_image": f"{base_url}/static/logo.svg",
        "og_locale": "zh_CN",
        "og_locale_alternates": [],
        "page_title": page_title, "page_desc": desc or dawn_site_tagline(),
        "canonical": canonical, "year": time.strftime("%Y"),
        "nav": nav, "footer_nav": dawn_get_nav_links("footer"),
        "global_js": global_js,
        "member_name": (session or {}).get("member_name", ""),
        "is_admin": _dawn_is_admin(session),
        "theme_css": dawn_themes.dawn_theme_root_css(),
        "home_sections": dawn_themes.dawn_theme_home_sections(),
        "base_css": dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/base.css", DAWN_BASE_CSS)
                    + "\n" + dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/list.css", DAWN_LIST_CSS),
        "doc_css": dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/doc.css", DAWN_DOC_CSS),
        "layout_css": dawn_themes.dawn_layout_override_css(),
        "layout_mode": dawn_themes.dawn_get_layout_mode(),
        "page_width": dawn_themes.dawn_theme_settings().get("page_width", "Page width"),
    }


def _dawn_render(template, session, lang="", **kw):
    base = _dawn_ctx(session, kw.pop("title", ""), kw.pop("desc", ""), kw.pop("canonical", ""))
    base.update(kw)
    try:
        from plugins import dawn_collect_hooks_sync
        dawn_collect_hooks_sync("seo_ctx", ctx=base)
        extras = []
        for res in dawn_collect_hooks_sync("head_extra", ctx=base):
            if isinstance(res, str):
                extras.append(res)
        if extras:
            base["extra_head"] = (base.get("extra_head") or "") + "".join(extras)
    except Exception:
        pass
    return HTMLResponse(dawn_themes.dawn_render(template, lang=lang, **base))


def _dawn_is_internal_tag(t) -> bool:
    """hash- 前缀标签为内部结构标签（#docs/#landing 等），不在前台展示"""
    name = (t.get("name", "") or "") if isinstance(t, dict) else str(t or "")
    slug = (t.get("slug", "") or "") if isinstance(t, dict) else ""
    return name.startswith("hash-") or slug.startswith("hash-")


def _dawn_split_tags(article_tags: list):
    """返回 (公开标签 cards, 内部标签名 list)"""
    public = [{"name": t.get("name", ""), "slug": t.get("slug", "")} for t in article_tags if not _dawn_is_internal_tag(t)]
    internal = [(t.get("slug") or t.get("name") or "").replace("hash-", "#") for t in article_tags if _dawn_is_internal_tag(t)]
    return public, internal


async def _dawn_docs_groups(all_posts: list, cats: list, categories: list, session, current_slug: str = "") -> list:
    """文档目录侧栏分组（首页与文章页共用同一套数据和渲染）：分类在前、连载在后，每组最多 6 篇 + 查看全部。
    current_slug 非空时给对应文章项打 current 标记（文章页当前项圆点）。"""
    series_names = {c.get("name", "") for c in categories if c.get("is_series")}
    groups = []
    for c in cats:
        asc = c["name"] in series_names
        group_posts = sorted(
            (p for p in all_posts if (p.get("category") or "未分类") == c["name"]),
            key=lambda x: x.get("created_at", ""), reverse=not asc)[:6]
        if not group_posts:
            continue
        groups.append({
            "name": c["name"], "slug": c["slug"], "url": f"/{c['slug']}",
            "is_series": c["name"] in series_names,
            "posts": [{"title": p.get("title", ""), "url": dawn_post_url(p, categories),
                       "current": bool(current_slug) and p.get("slug") == current_slug} for p in group_posts],
        })
    try:
        for s in await DawnBlogService.get_series():
            s_posts = await DawnBlogService.get_series_posts(s.get("id"), include_admin=_dawn_is_admin(session))
            if not s_posts:
                continue
            groups.append({
                "name": s.get("name", ""), "slug": s.get("slug", ""), "is_series": True,
                "url": f"/series/{s.get('slug', '')}",
                "posts": [{"title": p.get("title", ""), "url": dawn_post_url(p, categories),
                           "current": bool(current_slug) and p.get("slug") == current_slug} for p in s_posts[:6]],
            })
    except Exception as e:
        print(f"加载系列分组失败: {e}")
    return groups


async def _dawn_card(p: dict, categories: list, tag_map: dict | None = None) -> dict:
    raw_tags = tag_map.get(p.get("id"), []) if tag_map else []
    public_tags = [t for t in raw_tags if not _dawn_is_internal_tag(t)]
    return {
        "url": dawn_post_url(p, categories),
        "title": p.get("title", ""),
        "desc": (p.get("description", "") or "")[:110] + ("…" if len(p.get("description", "") or "") > 110 else ""),
        "cover": dawn_cover_url(p),
        "category": p.get("category", ""),
        "date": (p.get("created_at", "") or "")[:10],
        "read_time": p.get("read_time", ""),
        "views": p.get("view_count", 0),
        "member": p.get("visibility") == "member",
        "tags": public_tags,
    }


async def _dawn_lang_switch(page_type="", slug="", cat_slug=""):
    """经插件钩子取当前页面的语言切换项（i18n 插件未启用时为空）"""
    try:
        from plugins import dawn_collect_hooks
        for res in await dawn_collect_hooks("lang_switch", page_type=page_type, slug=slug, cat_slug=cat_slug):
            if isinstance(res, list) and res:
                return res
    except Exception:
        pass
    return []


async def _dawn_list_response(session, posts, categories, current_cat, all_posts, page,
                         search_query="", tag=None, notice="", sort_asc=False, series=None,
                         lang_switch=None, is_home=False, author=""):
    robots_meta = "noindex,follow" if search_query else ""
    tag_map = await DawnBlogService.get_tags_for_posts([p.get("id") for p in posts])
    if series:
        sorted_articles = sorted(posts, key=lambda x: (0, x.get("series_order") or 0) if (x.get("series_order") or 0) > 0 else (1, x.get("created_at", ""))) if posts else []
        sort_asc = True
    else:
        sorted_articles = sorted(posts, key=lambda x: x.get("created_at", ""), reverse=not sort_asc) if posts else []
    per_page = 12
    page = max(1, page)
    total_count = len(sorted_articles)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    paged = sorted_articles[(page - 1) * per_page: page * per_page]
    all_posts = all_posts if all_posts is not None else sorted_articles

    cat_counts = {}
    for p in all_posts:
        name = p.get("category") or "未分类"
        cat_counts[name] = cat_counts.get(name, 0) + 1
    cats = [{"slug": c.get("slug", ""), "name": c.get("name", ""), "count": cat_counts.get(c.get("name", ""), 0),
             "url": f"/{c.get('slug', '')}"}
            for c in categories]

    cat_name_map = {c.get("slug", ""): c.get("name", "") for c in categories}
    current_cat_name = cat_name_map.get(current_cat, current_cat)

    if not paged:
        empty_msg = (
            f"没有找到与「{search_query}」相关的文章" if search_query else
            f"标签 #{tag.get('name', '')} 下暂无文章" if tag else
            f"系列「{series.get('name', '')}」下暂无文章" if series else
            (f"分类「{current_cat_name}」下暂无文章" if current_cat else "暂无文章，敬请期待...")
        )
        return _dawn_render("list.html", session, empty=True, empty_msg=empty_msg,
                       title=(f"系列：{series.get('name', '')}" if series else (f"标签：{tag.get('name', '')}" if tag else "博客")),
                       cats=cats, current_cat=current_cat, q=search_query,
                       robots_meta=robots_meta,
                       lang_switch=lang_switch or [])

    heading = (
        f"「{search_query}」的搜索结果" if search_query else
        f"#{tag.get('name', '')}" if tag else
        series.get("name", "") if series else
        f"作者：{author}" if author else
        current_cat_name if current_cat else
        dawn_site_tagline()
    )
    sub_line = (
        f"共找到 {total_count} 篇相关文章" if search_query else
        f"标签下共 {total_count} 篇文章" if tag else
        (series.get("description") or f"连载系列 · 共 {total_count} 篇，按顺序阅读") if series else
        f"该作者共发布 {total_count} 篇文章" if author else
        f"本分类共 {total_count} 篇文章" if current_cat else
        "把每一次阅读、思考与实践，落笔成文"
    )

    featured = await _dawn_card(paged[0], categories, tag_map)
    recent = [await _dawn_card(p, categories, tag_map) for p in paged[1:5]]
    cards = [await _dawn_card(p, categories, tag_map) for p in paged]

    cat_groups = []
    series_slugs = {c.get("slug", "") for c in categories if c.get("is_series")}
    series_names = {c.get("name", "") for c in categories if c.get("is_series")}
    for c in cats:
        asc = c["name"] in series_names
        group_posts = sorted(
            (p for p in all_posts if (p.get("category") or "未分类") == c["name"]),
            key=lambda x: x.get("created_at", ""), reverse=not asc)
        group_posts = [{"title": p.get("title", ""), "url": dawn_post_url(p, categories)}
                       for p in group_posts[:6]]
        if group_posts:
            cat_groups.append({"name": c["name"], "slug": c["slug"], "posts": group_posts,
                               "url": f"/{c['slug']}",
                               "is_series": c["name"] in series_names})

    series_groups = []
    try:
        for s in await DawnBlogService.get_series():
            s_posts = await DawnBlogService.get_series_posts(s.get("id"), include_admin=_dawn_is_admin(session))
            if not s_posts:
                continue
            series_groups.append({
                "name": s.get("name", ""), "slug": s.get("slug", ""), "is_series": True,
                "url": f"/series/{s.get('slug', '')}",
                "posts": [{"title": p.get("title", ""), "url": dawn_post_url(p, categories)} for p in s_posts[:6]],
            })
    except Exception as e:
        print(f"加载系列分组失败: {e}")

    docs_groups = await _dawn_docs_groups(all_posts, cats, categories, session)

    if series:
        base_url = f"/series/{series.get('slug', '')}?page="
        canonical = f"{DAWN_SITE_BASE_URL}/series/{series.get('slug', '')}"
        title = f"系列：{series.get('name', '')}"
        desc = series.get("description") or f"连载系列「{series.get('name', '')}」的全部文章。"
    elif tag:
        base_url = f"/tag/{tag.get('slug', '')}?page="
        canonical = f"{DAWN_SITE_BASE_URL}/tag/{tag.get('slug', '')}"
        title = f"标签：{tag.get('name', '')}"
        desc = f"标签 #{tag.get('name', '')} 下的全部文章。"
    elif search_query:
        base_url = f"/search?q={quote(search_query)}&page="
        canonical = ""
        title = f"搜索：{search_query}"
        desc = "搜索结果"
    elif author:
        base_url = f"/author/{quote(author)}?page="
        canonical = f"{DAWN_SITE_BASE_URL}/author/{quote(author)}"
        title = f"作者：{author}"
        desc = f"{author} 发布的全部文章。"
    elif current_cat:
        base_url = f"/{current_cat}?page="
        canonical = f"{DAWN_SITE_BASE_URL}/{current_cat}"
        title = f"{current_cat_name} - 博客"
        desc = f"聚合 {current_cat_name} 主题的最新文章。"
    else:
        base_url = "/?page="
        canonical = DAWN_SITE_BASE_URL
        title = ""
        desc = "最新文章与分享。"

    extra_head = ""
    if current_cat:
        extra_head = '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "博客", "item": DAWN_SITE_BASE_URL},
                {"@type": "ListItem", "position": 2, "name": current_cat_name, "item": canonical},
            ]}, ensure_ascii=False) + "</script>"

    return _dawn_render("list.html", session,
                   title=title, desc=desc, canonical=canonical,
                   heading=heading, sub_line=sub_line, notice=notice, q=search_query,
                   cats=cats, current_cat=current_cat,
                   cat_groups=cat_groups, series_groups=series_groups, docs_groups=docs_groups,
                   series_mode=sort_asc, per_page=per_page,
                   featured=featured, recent=recent, posts=cards,
                   page=page, pages=total_pages, total=total_count,
                   base_url=base_url, extra_head=extra_head, robots_meta=robots_meta,
                   lang_switch=lang_switch or [], is_home=is_home)




def _dawn_tokenize(text: str) -> set:
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9一-鿿]{2,}", text.lower()))


DAWN_ABOUT_HTML = """
<div class="text-center mb-4">
  <span class="eyebrow block mb-5">About</span>
  <h1 class="ff-serif text-4xl font-black text-[var(--ink)] mb-3">关于本站</h1>
  <p class="text-[var(--accent)] font-semibold tracking-widest mb-10">Powered by DawnCMS</p>
</div>
<div class="p-7 rounded-2xl border border-[var(--hairline)] bg-[var(--card)] mb-4">
  <h2 class="ff-serif text-xl font-bold text-[var(--ink)] mb-3">长期主义：博客是资产，不是消耗品</h2>
  <p class="text-[var(--ink-soft)] leading-loose mb-2">社交媒体上的内容是消耗品——发布 24 小时后就被算法淹没。而博客文章是资产：一篇好文章会在搜索引擎里持续工作三年、五年，在你睡觉的时候依然为你带来读者、信任与机会。</p>
  <p class="text-[var(--ink-2)] leading-loose">复利效应同样适用于写作：第 1 篇无人问津，第 20 篇开始被搜索到，第 100 篇时，你已经拥有了一座别人无法一夜复制的内容护城河。</p>
</div>
<div class="p-7 rounded-2xl border border-[var(--hairline)] bg-[var(--card)] mb-10">
  <h2 class="ff-serif text-xl font-bold text-[var(--ink)] mb-3">关于 DawnCMS</h2>
  <p class="text-[var(--ink-soft)] leading-loose">本站由 DawnCMS 驱动——一个轻量、自持、为长期写作而生的内容管理系统。数据自持、主题可换、无需依赖第三方平台。</p>
</div>
<div class="text-center">
  <a href="/" class="btn-primary">开始阅读</a>
  <a href="/feed.xml" class="btn-secondary ml-3">订阅更新</a>
</div>
"""


def dawn_setup(app):
    @app.get("/theme-assets/{key}/{path:path}")
    async def theme_asset_route(key: str, path: str):
        resp = dawn_themes.dawn_serve_theme_asset(key, path)
        if resp is None:
            raise HTTPException(status_code=404)
        return resp

    @app.get("/")
    async def blog_index(session, request, page: int = 1, subscribed: str = "", subscribe_error: str = ""):
        try:
            is_admin = _dawn_is_admin(session)
            posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
            categories = await DawnBlogService.get_categories()
            en = (request.cookies.get("site_lang") or "").startswith("en")
            notice = ("✅ Subscribed! New posts will be emailed to you" if en else "✅ 订阅成功，新文章发布时会邮件通知你") if subscribed else (
                ("Invalid email address, please try again" if en else "邮箱格式不正确，请重试") if subscribe_error else "")
            return await _dawn_list_response(session, posts, categories, "", posts, page, notice=notice,
                                        lang_switch=await _dawn_lang_switch("home"), is_home=True)
        except Exception as e:
            print(f"加载博客列表失败: {e}")
            return await _dawn_list_response(session, [], [], "", [])

    @app.get("/about")
    async def about_page(session):
        return _dawn_render("page.html", session, title="关于", content=DAWN_ABOUT_HTML)

    @app.get("/search")
    async def blog_search(session, q: str = ""):
        q = (q or "").strip()
        posts = await DawnBlogService.search_posts(q) if q else []
        categories = await DawnBlogService.get_categories()
        return await _dawn_list_response(session, posts, categories, "", posts, 1, search_query=q)

    @app.get("/api/quick-search")
    async def dawn_quick_search(q: str = "", lang: str = "zh"):
        q = (q or "").strip()[:60]
        if not q:
            return JSONResponse([])
        lang = (lang or "zh").lower()
        if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", lang) and lang != "zh":
            try:
                import aiosqlite
                from blog.dawn_factory import dawn_get_blog_db
                like = f"%{q}%"
                db = await dawn_get_blog_db()
                db.row_factory = aiosqlite.Row
                rows = await (await db.execute(
                    """SELECT t.title AS t_title, p.slug, p.created_at, p.category
                       FROM plugin_i18n_translations t JOIN posts p ON p.id = t.post_id
                       WHERE t.lang=? AND t.status='done' AND p.is_published=1 AND p.visibility='public'
                         AND (t.title LIKE ? OR t.content_md LIKE ?)
                       ORDER BY p.created_at DESC LIMIT 8""",
                    (lang, like, like))).fetchall()
                await db.close()
                return JSONResponse([{"title": r["t_title"], "url": f"/{lang}/{r['slug']}",
                                      "date": (r["created_at"] or "")[:10], "category": r["category"] or ""}
                                     for r in rows])
            except Exception:
                return JSONResponse([])
        categories = await DawnBlogService.get_categories()
        posts = (await DawnBlogService.search_posts(q))[:8]
        return JSONResponse([{"title": p.get("title", ""), "url": dawn_post_url(p, categories),
                              "date": (p.get("created_at") or "")[:10], "category": p.get("category") or ""}
                             for p in posts])

    # ---- /blog 旧路径 301 兼容 ----

    @app.get("/blog")
    async def legacy_blog_home(page: int = 1):
        return RedirectResponse(dawn_category_url("", page), status_code=301)

    @app.get("/blog/search")
    async def legacy_blog_search(q: str = ""):
        return RedirectResponse(f"/search?q={q}", status_code=301)

    @app.get("/blog/category/{cat_slug}")
    async def legacy_blog_category(cat_slug: str, page: int = 1):
        return RedirectResponse(dawn_category_url(cat_slug, page), status_code=301)

    @app.get("/blog/{cat_slug}")
    async def legacy_blog_cat(cat_slug: str, page: int = 1):
        return RedirectResponse(dawn_category_url(cat_slug, page), status_code=301)

    @app.get("/blog/{cat_slug}/{slug}")
    async def legacy_blog_article(cat_slug: str, slug: str):
        return RedirectResponse(f"/{cat_slug}/{slug}", status_code=301)

    # ---- 正文路由 ----

    @app.get("/sitemap.xml")
    async def sitemap():
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")
        posts = await DawnBlogService.get_all_posts(published_only=True)
        categories = await DawnBlogService.get_categories()
        cat_slug_by_name = dawn_category_slug_map(categories)

        urls = [
            f'<url><loc>{DAWN_SITE_BASE_URL}/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>'
        ]
        for cat in categories:
            slug = cat.get("slug", "")
            if slug:
                urls.append(f'<url><loc>{DAWN_SITE_BASE_URL}/{slug}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.75</priority></url>')
        for post in posts:
            if post.get("visibility", "public") != "public":
                continue
            cat_slug = cat_slug_by_name.get(post.get("category", ""), "uncategorized")
            lastmod = (post.get("updated_at") or post.get("created_at") or today)[:10]
            urls.append(
                f'<url><loc>{DAWN_SITE_BASE_URL}/{cat_slug}/{post.get("slug", "")}</loc>'
                f'<lastmod>{lastmod}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>'
            )
        try:
            from plugins import dawn_collect_hooks
            for res in await dawn_collect_hooks("sitemap_urls"):
                if isinstance(res, list):
                    urls.extend(res)
        except Exception:
            pass
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
        return Response(xml, media_type="application/xml")

    @app.get("/robots.txt")
    async def robots():
        return Response(
            f"User-agent: *\nAllow: /\nDisallow: /dadmin\nSitemap: {DAWN_SITE_BASE_URL}/sitemap.xml\n",
            media_type="text/plain"
        )

    @app.get("/feed.xml")
    async def rss_feed():
        from xml.sax.saxutils import escape
        posts = await DawnBlogService.get_all_posts(published_only=True)
        categories = await DawnBlogService.get_categories()
        slug_map = dawn_category_slug_map(categories)
        items = []
        for post in posts[:50]:
            if post.get("visibility", "public") != "public":
                continue
            cat_slug = slug_map.get(post.get("category", ""), "uncategorized")
            link = f"{DAWN_SITE_BASE_URL}/{cat_slug}/{post.get('slug', '')}"
            pub = (post.get("created_at") or "")[:19]
            items.append(
                f"<item><title>{escape(post.get('title', ''))}</title><link>{link}</link>"
                f"<guid isPermaLink=\"true\">{link}</guid>"
                f"<description>{escape(post.get('description', ''))}</description>"
                f"<category>{escape(post.get('category', ''))}</category>"
                f"<pubDate>{pub}</pubDate></item>"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>'
            f"<title>{escape(dawn_site_name())}</title>"
            f"<link>{DAWN_SITE_BASE_URL}</link>"
            f"<description>{escape(dawn_site_tagline())}</description>"
            f"<language>zh-cn</language>"
            + "".join(items) +
            "</channel></rss>"
        )
        return Response(xml, media_type="application/rss+xml")

    @app.get("/tag/{tag_slug}")
    async def tag_page(session, tag_slug: str, page: int = 1):
        is_admin = _dawn_is_admin(session)
        tag = await DawnBlogService.get_tag_by_slug(tag_slug)
        if not tag:
            raise HTTPException(status_code=404)
        posts = await DawnBlogService.get_posts_by_tag_slug(tag_slug, include_admin=is_admin)
        categories = await DawnBlogService.get_categories()
        all_posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
        return await _dawn_list_response(session, posts, categories, "", all_posts, page, tag=tag,
                                    lang_switch=await _dawn_lang_switch("tag", slug=tag_slug))

    @app.post("/subscribe")
    async def subscribe(request, email: str = ""):
        ok, msg = await DawnBlogCRUD.subscribe_newsletter(email)
        lang = request.cookies.get("site_lang") or ""
        base = f"/{lang}" if lang and not lang.startswith("zh") else "/"
        target = f"{base}?subscribed=1" if ok else f"{base}?subscribe_error=1"
        return RedirectResponse(target, status_code=303)

    @app.get("/unsubscribe")
    async def unsubscribe(request, session, token: str = ""):
        ok = await DawnBlogCRUD.unsubscribe_newsletter(token) if token else False
        en = (request.cookies.get("site_lang") or "").startswith("en")
        return _dawn_render(
            "message.html", session, lang="en" if en else "",
            title=("Unsubscribe" if en else "退订"),
            robots_meta="noindex,nofollow",
            message_title=("Unsubscribed" if ok else "Invalid link") if en else ("已退订" if ok else "链接无效"),
            message_body=("You will no longer receive new post notifications." if ok else "The unsubscribe link is invalid or expired.") if en
                         else ("你将不再收到新文章邮件通知。" if ok else "退订链接无效或已失效。"),
            message_link_text="Back to home" if en else "返回首页",
            message_link_url="/",
        )

    @app.get("/series/{series_slug}")
    async def blog_series(session, series_slug: str, page: int = 1):
        series = await DawnBlogService.get_series_by_slug(series_slug)
        if not series:
            raise HTTPException(status_code=404)
        is_admin = _dawn_is_admin(session)
        posts = await DawnBlogService.get_series_posts(series.get("id"), include_admin=is_admin)
        categories = await DawnBlogService.get_categories()
        all_posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
        return await _dawn_list_response(session, posts, categories, "", all_posts, page, series=series,
                                    lang_switch=await _dawn_lang_switch("series", slug=series_slug))

    @app.get("/tags/")
    @app.get("/tags")
    async def tags_wall(session):
        """标签墙：公开标签墙（hash- 内部标签不展示）"""
        tags = await DawnBlogService.list_tags_with_counts()
        tags = [{"name": t.get("name", ""), "slug": t.get("slug", ""), "count": t.get("count", t.get("post_count", 0))}
                for t in tags if not _dawn_is_internal_tag(t) and (t.get("count", t.get("post_count", 0)) or 0) > 0]
        tags.sort(key=lambda x: -x["count"])
        return _dawn_render("tags.html", session,
                       title="标签", desc="按主题浏览全部文章。",
                       canonical=f"{DAWN_SITE_BASE_URL}/tags/",
                       wall_tags=tags,
                       lang_switch=await _dawn_lang_switch("tags"))

    async def _dawn_hash_collection(session, hash_name: str, template: str, title: str, desc: str, order_asc: bool = False):
        """集合页：按 hash-{name} 标签取文章，渲染指定模板"""
        is_admin = _dawn_is_admin(session)
        tag = await DawnBlogService.get_tag_by_slug(f"hash-{hash_name}")
        if not tag:
            all_tags = await DawnBlogService.list_tags()
            tag = next((t for t in all_tags if t.get("name") == f"hash-{hash_name}"), None)
        posts = []
        if tag:
            posts = await DawnBlogService.get_posts_by_tag_slug(tag.get("slug", ""), include_admin=is_admin)
        posts = sorted(posts, key=lambda x: x.get("created_at", ""), reverse=not order_asc)
        categories = await DawnBlogService.get_categories()
        cards = [await _dawn_card(p, categories) for p in posts]
        return _dawn_render(template, session,
                       title=title, desc=desc,
                       canonical=f"{DAWN_SITE_BASE_URL}/{hash_name}",
                       posts=cards, total=len(cards),
                       robots_meta="noindex,follow" if not posts else "",
                       lang_switch=await _dawn_lang_switch(hash_name))

    @app.get("/author/{author_name}")
    async def author_page(session, author_name: str, page: int = 1):
        """作者归档页：作者归档页"""
        is_admin = _dawn_is_admin(session)
        all_posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
        posts = [p for p in all_posts if (p.get("author") or "") == author_name]
        if not posts:
            raise HTTPException(status_code=404)
        categories = await DawnBlogService.get_categories()
        return await _dawn_list_response(session, posts, categories, "", all_posts, page,
                                    author=author_name,
                                    lang_switch=await _dawn_lang_switch("author"))

    @app.get("/changelog")
    async def changelog_page(session):        return await _dawn_hash_collection(session, "changelog", "changelog.html",
                                           "更新日志", "产品功能与内容更新记录。")

    @app.get("/roadmap")
    async def roadmap_page(session):
        return await _dawn_hash_collection(session, "roadmap", "roadmap.html",
                                           "路线图", "正在规划与推进的方向。", order_asc=True)

    @app.get("/showcase")
    async def showcase_page(session):
        return await _dawn_hash_collection(session, "showcase", "showcase.html",
                                           "展示", "案例与作品展示。")

    @app.get("/{cat_slug}")
    async def blog_category(session, cat_slug: str, page: int = 1):
        try:
            is_admin = _dawn_is_admin(session)
            all_posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
            categories = await DawnBlogService.get_categories()
            if not any((c.get("slug") == cat_slug) for c in categories):
                raise HTTPException(status_code=404)
            is_series = any(c.get("slug") == cat_slug and c.get("is_series") for c in categories)
            posts = await DawnBlogService.get_posts_by_category(cat_slug, include_admin=is_admin)
            return await _dawn_list_response(session, posts, categories, cat_slug, all_posts, page, sort_asc=is_series,
                                        lang_switch=await _dawn_lang_switch("category", cat_slug=cat_slug))
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            print(f"加载分类列表失败: {e}")
            return await _dawn_list_response(session, [], [], cat_slug, [], page)

    @app.get("/{cat_slug}/{slug}")
    async def blog_article(cat_slug: str, slug: str, session, request):
        is_admin = _dawn_is_admin(session)
        article = await DawnBlogService.get_post(slug, is_admin=is_admin, is_member=_dawn_is_member(session))
        if not article:
            redirect = await DawnBlogService.get_redirect_by_old_slug(slug)
            if redirect:
                target = await DawnBlogService.get_post(redirect.get('new_slug', ''), is_admin=is_admin)
                if target:
                    categories = await DawnBlogService.get_categories()
                    real_cat_slug = dawn_category_slug_map(categories).get(target.get("category", ""), "uncategorized")
                    return RedirectResponse(f"/{real_cat_slug}/{target.get('slug', '')}", status_code=301)
            raise HTTPException(status_code=404)

        categories = await DawnBlogService.get_categories()
        real_cat_slug = dawn_category_slug_map(categories).get(article.get("category", ""), "uncategorized")
        if cat_slug != real_cat_slug:
            return RedirectResponse(f"/{real_cat_slug}/{slug}", status_code=301)

        current_path = f"/{real_cat_slug}/{article.get('slug', '')}"
        a_base = {
            "id": article.get("id", 0),
            "slug": article.get("slug", ""),
            "title": article.get("title", ""),
            "desc": article.get("description", ""),
            "category": article.get("category", ""),
            "category_slug": real_cat_slug,
            "date": (article.get("created_at", "") or "")[:10],
            "updated": (article.get("updated_at", "") or "")[:10],
            "author": article.get("author", DAWN_DEFAULT_AUTHOR),
        }

        # 会员门禁
        if article.get("gated"):
            return _dawn_render("gate.html", session, lang=(request.cookies.get("site_lang") or ""),
                           title=article.get("title", ""), desc=article.get("description", ""),
                           canonical=f"{DAWN_SITE_BASE_URL}{current_path}",
                           a=a_base, current_path=current_path)

        # TOC 提取 + 标题锚点
        raw_html = article.get("html_content") or ""
        toc_items, html_with_ids = dawn_extract_toc_and_anchors(raw_html)
        html_with_ids = re.sub(
            rf'<a\s+href="(https?://(?!{re.escape(DAWN_SITE_BASE_URL)})(?:[^"]+))"(?![^>]*\btarget=)',
            r'<a href="\1" target="_blank" rel="noopener noreferrer"',
            html_with_ids, flags=re.I)

        all_posts = await DawnBlogService.get_all_posts(published_only=True, include_admin=is_admin)
        posts_by_cat = {}
        for post in all_posts:
            posts_by_cat.setdefault(post.get("category") or "未分类", []).append(post)

        # 上下篇：系列文章优先按系列顺序（跨分类），否则连载分类正序、普通分类倒序
        series_info = None
        series_block = None
        article_series_id = article.get("series_id") or 0
        if article_series_id:
            series_info = await DawnBlogService.get_series_by_id(article_series_id)
            series_posts = await DawnBlogService.get_series_posts(article_series_id, include_admin=is_admin)
            s_idx = next((i for i, p in enumerate(series_posts) if p.get("id") == article.get("id")), -1)
            prev_post = series_posts[s_idx - 1] if s_idx > 0 else None
            next_post = series_posts[s_idx + 1] if 0 <= s_idx + 1 < len(series_posts) else None
            if series_info:
                series_block = {
                    "name": series_info.get("name", ""), "slug": series_info.get("slug", ""),
                    "posts": [{"url": dawn_post_url(p, categories), "title": p.get("title", "无标题"),
                               "current": p.get("id") == article.get("id")} for p in series_posts],
                }
            cur_cat_obj = next((c for c in categories if c.get("name") == article.get("category")), None)
            cat_is_series = bool(cur_cat_obj and cur_cat_obj.get("is_series"))
        else:
            cur_cat_obj = next((c for c in categories if c.get("name") == article.get("category")), None)
            cat_is_series = bool(cur_cat_obj and cur_cat_obj.get("is_series"))
            current_cat_posts = sorted(posts_by_cat.get(article.get("category", ""), []),
                                       key=lambda x: x.get("created_at", ""), reverse=not cat_is_series)
            current_idx = next((i for i, p in enumerate(current_cat_posts) if p.get("id") == article.get("id")), -1)
            if cat_is_series:
                prev_post = current_cat_posts[current_idx - 1] if current_idx > 0 else None
                next_post = current_cat_posts[current_idx + 1] if 0 <= current_idx + 1 < len(current_cat_posts) else None
            else:
                prev_post = current_cat_posts[current_idx + 1] if 0 <= current_idx + 1 < len(current_cat_posts) else None
                next_post = current_cat_posts[current_idx - 1] if current_idx > 0 else None

        def _pn(p):
            return {"url": dawn_post_url(p, categories), "title": p.get("title", "")} if p else None

        # 相关文章（打分：同分类 + 关键词重叠 + 热度 + 同作者）
        current_tokens = _dawn_tokenize(article.get("title", "")) | _dawn_tokenize(article.get("keywords", ""))
        related_scored = []
        for cand in all_posts:
            if cand.get("id") == article.get("id"):
                continue
            score, reasons = 0, []
            if cand.get("category") == article.get("category"):
                score += 6
                reasons.append("同分类")
            overlap = len(current_tokens & (_dawn_tokenize(cand.get("title", "")) | _dawn_tokenize(cand.get("keywords", ""))))
            if overlap:
                score += min(6, overlap * 2)
                reasons.append(f"关键词匹配 {overlap}")
            hot = min(2, (cand.get("view_count", 0) or 0) // 100)
            score += hot
            if hot:
                reasons.append("热门文章")
            if cand.get("author") == article.get("author"):
                score += 1
                reasons.append("同作者")
            related_scored.append((score, cand.get("created_at", ""), cand, reasons[:2]))
        related_scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        related = [{
            "url": dawn_post_url(x[2], categories), "title": x[2].get("title", ""),
            "cover": dawn_cover_url(x[2]), "category": x[2].get("category", ""),
            "desc": (x[2].get("description", "") or "")[:88] + ("..." if len(x[2].get("description", "") or "") > 88 else ""),
            "read_time": x[2].get("read_time", ""), "date": (x[2].get("created_at", "") or "")[:10],
            "reasons": x[3],
        } for x in related_scored[:6]]

        # 左栏专栏导航
        current_cat = next((c for c in categories if c.get("name") == article.get("category")), None)
        rail_cats = []
        for cat in categories:
            cat_asc = bool(cat.get("is_series"))
            cat_posts = sorted(posts_by_cat.get(cat.get("name", "未分类"), []),
                               key=lambda x: x.get("created_at", ""), reverse=not cat_asc)[:10]
            is_open = bool(current_cat and current_cat.get("slug") == cat.get("slug"))
            rail_cats.append({
                "name": cat.get("name", "未分类"), "slug": cat.get("slug", "uncategorized"),
                "open": is_open, "is_series": cat_asc,
                "posts": [{"url": dawn_post_url(p, categories), "title": p.get("title", "无标题"),
                           "current": p.get("slug") == article.get("slug")} for p in cat_posts],
            })

        article_tags = await DawnBlogService.get_post_tags(article.get("id", 0))
        tags, internal_tags = _dawn_split_tags(article_tags)

        # 文档目录侧栏：与首页同一套数据，仅多一个当前文章标记
        cats_for_nav = [{"name": c.get("name", "未分类"), "slug": c.get("slug", "uncategorized")} for c in categories]
        docs_groups = await _dawn_docs_groups(all_posts, cats_for_nav, categories, session,
                                              current_slug=article.get("slug", ""))

        canonical_url = f"{DAWN_SITE_BASE_URL}{current_path}"
        _cover = dawn_cover_url(article).strip()
        if _cover and not _cover.startswith("http"):
            _cover = f"{DAWN_SITE_BASE_URL}{_cover}"
        _article_sd = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": article.get("title", ""), "description": article.get("description", ""),
            "author": {"@type": "Person", "name": article.get("author", DAWN_DEFAULT_AUTHOR)},
            "publisher": {"@type": "Organization", "name": dawn_site_name(),
                          "logo": {"@type": "ImageObject", "url": f"{DAWN_SITE_BASE_URL}/static/logo.svg"}},
            "datePublished": article.get("created_at", ""),
            "dateModified": article.get("updated_at", article.get("created_at", "")),
            "mainEntityOfPage": canonical_url, "articleSection": article.get("category", ""),
        }
        if _cover:
            _article_sd["image"] = [_cover]
        jsonld_article = json.dumps(_article_sd, ensure_ascii=False)
        jsonld_breadcrumb = json.dumps({
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "博客", "item": DAWN_SITE_BASE_URL},
                {"@type": "ListItem", "position": 2, "name": article.get("category", "分类"), "item": f"{DAWN_SITE_BASE_URL}/{real_cat_slug}"},
                {"@type": "ListItem", "position": 3, "name": article.get("title", "文章"), "item": canonical_url},
            ]}, ensure_ascii=False)
        item_list, position = [], 1
        if prev_post:
            item_list.append({"@type": "ListItem", "position": position, "name": prev_post.get("title", "上一篇"),
                              "item": f"{DAWN_SITE_BASE_URL}{dawn_post_url(prev_post, categories)}"})
            position += 1
        item_list.append({"@type": "ListItem", "position": position, "name": article.get("title", "当前文章"), "item": canonical_url})
        position += 1
        if next_post:
            item_list.append({"@type": "ListItem", "position": position, "name": next_post.get("title", "下一篇"),
                              "item": f"{DAWN_SITE_BASE_URL}{dawn_post_url(next_post, categories)}"})
        jsonld_itemlist = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                                      "name": "相关文章导航", "itemListElement": item_list}, ensure_ascii=False)

        cover = dawn_cover_url(article)
        a = dict(a_base)
        a.update({
            "cover": cover, "cover_abs": cover,
            "read_time": article.get("read_time", ""), "views": article.get("view_count", 0),
        })

        plugin_extra = {}
        try:
            from plugins import dawn_collect_hooks
            for res in await dawn_collect_hooks("article_render", article=article, session=session):
                if isinstance(res, dict):
                    plugin_extra.update(res)
        except Exception:
            pass

        _tpl = "post.html"
        if (article.get("template") or "default") == "landing":
            _pkg = dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key())
            if _pkg and (_pkg.path / "templates" / "post-landing.html").exists():
                _tpl = "post-landing.html"
        return _dawn_render(_tpl, session,
                       title=article.get("title", ""), desc=article.get("description", ""),
                       canonical=canonical_url,
                       a=a, content=html_with_ids, toc=toc_items, tags=tags,
                       internal_tags=internal_tags,
                       post_template=article.get("template") or "default",
                       prev=_pn(prev_post), next=_pn(next_post), related=related,
                       rail_cats=rail_cats, series_block=series_block, docs_groups=docs_groups,
                       series_info=({"name": series_info.get("name", ""), "slug": series_info.get("slug", "")} if series_info else None),
                       jsonld_article=jsonld_article, jsonld_breadcrumb=jsonld_breadcrumb,
                       jsonld_itemlist=jsonld_itemlist,
                       doc_js=dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/doc.js", DAWN_DOC_JS),
                       lang_switch=await _dawn_lang_switch("article", slug=slug),
                       **plugin_extra)
