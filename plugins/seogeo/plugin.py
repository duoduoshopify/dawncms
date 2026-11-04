# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/seogeo/plugin.py
# DawnCMS 站点级 SEO/GEO 插件：
#   - 动态 robots.txt（AI 爬虫分组管控，对齐谷歌官方文档）
#   - llms.txt / llms-full.txt（面向 AI 引擎的社区约定文件）
#   - head 注入（站长验证 / twitter:site / article 时间戳）
#   - 每篇文章 SEO 标题/描述/noindex 覆盖（编辑页面板）
#   - 增强 sitemap.xml（image 扩展 + 真实 lastmod）
#   - 后台体检页 + 谷歌官方注意事项提醒区

import sqlite3
import time
from html import escape
from pathlib import Path

from fasthtml.common import (
    A, Button, Div, Form, H1, H2, H3, Input, Label, P, Span, Table, Tbody, Td,
    Textarea, Th, Thead, Tr,
)
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from dawn_config import dawn_site_name, dawn_site_tagline, DAWN_SITE_BASE_URL
from blog.dawn_factory import dawn_get_blog_db
from services.dawn_blog_service import DawnBlogService
from routes.admin.dawn_shell import (
    _dawn_admin_shell, _dawn_require_admin, _dawn_msg,
    DAWN_INPUT, DAWN_LABEL, DAWN_BTN, DAWN_BTN_GHOST, dawn_register_admin_page,
)
from plugins import dawn_register_hook

DAWN_PLUGIN = {
    "key": "seogeo",
    "label": "SEO / GEO",
    "group": "插件",
    "icon": "🔍",
    "url": "/dadmin/plugins/seogeo",
}

_DAWN_DB = Path("database/blog.db")

DAWN_DEFAULTS = {
    "robots_mode": "allow_all",      # allow_all | block_ai | custom
    "robots_custom": "",
    "llms_enabled": "1",
    "llms_intro": "",
    "gsc_token": "",                 # Google Search Console HTML 验证标记 content 值
    "bing_token": "",                # Bing Webmaster msvalidate.01
    "twitter_handle": "",            # @xxx
    "org_sameas": "",                # 逗号分隔的社交/主页链接
    "seo_home_title": "",            # 首页 <title> 覆盖（留空用站点名）
    "seo_home_desc": "",             # 首页 meta description 覆盖（留空用站点标语）
    "title_sep": "",                 # 标题分隔符（留空用 " - "，常见 "｜"）
    "og_image": "",                  # 默认 og:image（留空用 /static/logo.svg）
    "org_name": "",                  # Organization schema 名称（留空用站点名）
    "org_logo": "",                  # Organization logo URL（留空用 /static/logo.svg）
    "org_type": "Organization",      # Organization | Person（个人博客可选 Person）
}

# AI 爬虫清单（2026）。note 会显示在后台，帮助客户理解每个爬虫的影响。
DAWN_AI_CRAWLERS = [
    ("GPTBot", "OpenAI 模型训练爬虫"),
    ("OAI-SearchBot", "ChatGPT 搜索索引爬虫（影响 ChatGPT 搜索引用）"),
    ("ChatGPT-User", "ChatGPT 用户实时提问时的网页访问"),
    ("ClaudeBot", "Anthropic 模型训练爬虫"),
    ("Claude-User", "Claude 用户实时提问时的网页访问"),
    ("Claude-SearchBot", "Claude 搜索索引爬虫"),
    ("PerplexityBot", "Perplexity 搜索索引爬虫"),
    ("Perplexity-User", "Perplexity 用户实时访问"),
    ("Google-Extended", "谷歌 Gemini 训练/grounding 控制令牌（不影响搜索排名）"),
    ("Applebot-Extended", "苹果 AI 训练控制令牌（不影响 Spotlight/Safari 收录）"),
    ("Meta-ExternalAgent", "Meta AI 训练爬虫"),
    ("Bytespider", "字节跳动爬虫（豆包等）"),
    ("CCBot", "Common Crawl 公共语料库"),
    ("Amazonbot", "亚马逊 Alexa/AI 爬虫"),
    ("cohere-ai", "Cohere 训练爬虫"),
    ("Diffbot", "Diffbot 知识图谱爬虫"),
]

# 谷歌官方注意事项（后台常驻提醒）。url 均为官方文档。
DAWN_GOOGLE_NOTES = [
    ("Google-Extended ≠ 谷歌搜索",
     "屏蔽 Google-Extended 只影响 Gemini 等产品的 AI 训练与 grounding，不影响搜索收录与排名；"
     "AI Overviews / AI Mode 使用的是 Googlebot。",
     "https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers#google-extended"),
    ("无法单独屏蔽 AI Overviews",
     "AI Overviews / AI Mode 与搜索共用 Googlebot。想限制内容在 AI 功能中的展示，"
     "只能用 nosnippet / max-snippet / data-nosnippet / noindex，不能单独屏蔽 AI 功能而不影响搜索。",
     "https://developers.google.com/search/docs/appearance/ai-features"),
    ("llms.txt 不是谷歌标准",
     "谷歌官方明确表示出现在 AI 功能中「不需要创建新的机器可读文件」。llms.txt 是面向其它 AI 引擎的社区约定，"
     "本插件默认开启，可在下方关闭。",
     "https://developers.google.com/search/docs/fundamentals/ai-optimization-guide"),
    ("标题和描述可能被谷歌重写",
     "谷歌会根据用户查询动态重写标题链接和摘要。控制好长度（标题 10-60 字符、描述 70-160 字符）"
     "并确保与正文一致，可降低重写概率。",
     "https://developers.google.com/search/docs/appearance/title-link"),
    ("sitemap 的 lastmod 必须真实",
     "谷歌只在 lastmod 真实反映页面最后修改时间时才信任它。本插件已用文章的 updated_at 生成，请勿手动伪造。",
     "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap"),
    ("上线前必须配置 SITE_BASE_URL 并启用 HTTPS",
     "canonical、OG、sitemap、结构化数据全部依赖 .env 里的 SITE_BASE_URL。当前若是 localhost，"
     "上线前务必改为正式域名；HTTPS 是谷歌技术要求之一。",
     "https://developers.google.com/search/docs/essentials/technical"),
    ("上线后到 Search Console 验证并提交 sitemap",
     "验证站点所有权（可用本页的 HTML 标记 token），提交 /sitemap.xml，用 URL 检查工具确认抓取渲染正常。",
     "https://developers.google.com/search/docs/monitor-debug/search-console-start"),
    ("robots.txt 不能阻止收录",
     "被 robots.txt 屏蔽的页面仍可能以「仅 URL」形式被索引（无摘要）。真正不想被收录的页面要用 noindex，"
     "本插件支持按文章设置。",
     "https://developers.google.com/search/docs/crawling-indexing/robots/intro"),
    ("结构化数据必须与可见内容一致",
     "JSON-LD 描述的内容必须在页面上可见，否则可能被判定为垃圾结构化数据并遭人工处理。",
     "https://developers.google.com/search/docs/appearance/structured-data/sd-policies"),
    ("分页 rel=next/prev 已被谷歌废弃",
     "谷歌多年不使用 rel=next/prev 作为索引信号。分页页保持自引用 canonical 即可，本系统已默认如此。",
     "https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading"),
    ("内容质量是根本",
     "技术优化只是入场券。谷歌核心排序围绕「有用、可靠、以人为本的内容」（E-E-A-T），"
     "体检页全绿不代表排名，持续输出原创深度内容才是根本。",
     "https://developers.google.com/search/docs/fundamentals/creating-helpful-content"),
    ("多语言：hreflang 必须双向闭合",
     "本系统已在 HTML head 和 sitemap（xhtml:link）双通道输出完整 hreflang 簇（含 x-default），"
     "译文页 canonical 为自引用。新增语言后无需手工处理，但译文质量差会被判定为近似重复——确保机器翻译后有人工校对。",
     "https://developers.google.com/search/docs/specialty/international/localized-versions"),
    ("多语言：Googlebot 主要从单一地域抓取",
     "谷歌抓取时一般不切换语言/地区，发现多语言版本主要靠 hreflang 而非自动跳转。"
     "本系统的浏览器语言识别跳转已豁免爬虫 UA；不要把爬虫也 302 到译文版，否则中文原文可能无法被抓取。",
     "https://developers.google.com/search/docs/specialty/international/locale-adaptive-pages"),
]


# ---------- 配置读写 ----------

async def _dawn_ensure_tables():
    db = await dawn_get_blog_db()
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS plugin_seogeo_config (
            key TEXT PRIMARY KEY, value TEXT DEFAULT '')""")
        await db.execute("""CREATE TABLE IF NOT EXISTS plugin_seogeo_post (
            slug TEXT PRIMARY KEY,
            seo_title TEXT DEFAULT '',
            seo_desc TEXT DEFAULT '',
            robots TEXT DEFAULT '',
            updated_at TEXT DEFAULT '')""")
        await db.commit()
    finally:
        await db.close()


async def _dawn_get_config() -> dict:
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    try:
        rows = await (await db.execute("SELECT key, value FROM plugin_seogeo_config")).fetchall()
        cfg = dict(DAWN_DEFAULTS)
        cfg.update({r[0]: r[1] for r in rows})
        return cfg
    finally:
        await db.close()


async def _dawn_save_config(data: dict):
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    try:
        for k in DAWN_DEFAULTS:
            if k in data:
                await db.execute(
                    "INSERT INTO plugin_seogeo_config(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, str(data.get(k) or "")))
        await db.commit()
    finally:
        await db.close()


def _dawn_cfg_sync() -> dict:
    """同步读配置（head_extra 等同步钩子用），失败时返回默认"""
    try:
        db = sqlite3.connect(str(_DAWN_DB))
        rows = db.execute("SELECT key, value FROM plugin_seogeo_config").fetchall()
        db.close()
        cfg = dict(DAWN_DEFAULTS)
        cfg.update({r[0]: r[1] for r in rows})
        return cfg
    except Exception:
        return dict(DAWN_DEFAULTS)


def _dawn_post_seo_sync(slug: str) -> dict:
    try:
        db = sqlite3.connect(str(_DAWN_DB))
        row = db.execute(
            "SELECT seo_title, seo_desc, robots FROM plugin_seogeo_post WHERE slug=?",
            (slug,)).fetchone()
        db.close()
        if row:
            return {"seo_title": row[0] or "", "seo_desc": row[1] or "", "robots": row[2] or ""}
    except Exception:
        pass
    return {}


# ---------- robots.txt ----------

def _dawn_build_robots(cfg: dict) -> str:
    base = DAWN_SITE_BASE_URL.rstrip("/")
    mode = cfg.get("robots_mode", "allow_all")
    lines = []
    if mode == "custom":
        custom = (cfg.get("robots_custom") or "").strip()
        if custom:
            lines.append(custom)
    elif mode == "block_ai":
        for agent, _note in DAWN_AI_CRAWLERS:
            lines.append(f"User-agent: {agent}\nDisallow: /")
        lines.append("User-agent: *\nAllow: /\nDisallow: /dadmin\nDisallow: /search")
    else:
        lines.append("User-agent: *\nAllow: /\nDisallow: /dadmin\nDisallow: /search")
    if "Sitemap:" not in "\n".join(lines):
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n\n".join(lines) + "\n"


# ---------- llms.txt（社区约定，非谷歌标准） ----------

async def _dawn_llms_payload(full: bool) -> str:
    cfg = await _dawn_get_config()
    base = DAWN_SITE_BASE_URL.rstrip("/")
    intro = (cfg.get("llms_intro") or "").strip() or dawn_site_tagline()
    posts = await DawnBlogService.get_all_posts(published_only=True)
    posts = [p for p in posts if p.get("visibility", "public") == "public"]
    categories = await DawnBlogService.get_categories()
    cat_slug = {c.get("name", ""): c.get("slug", "") for c in categories}

    if not full:
        out = [f"# {dawn_site_name()}", "", f"> {intro}", "",
               f"站点地图: {base}/sitemap.xml", f"RSS: {base}/feed.xml", ""]
        i18n_langs, _trans = await _dawn_i18n_data()
        if i18n_langs:
            out.append("## 语言版本 / Languages")
            out.append("")
            out.append(f"- [中文版（默认）]({base}/)")
            for l in i18n_langs:
                out.append(f"- [{l} 版本]({base}/{l}/)（RSS: {base}/{l}/feed.xml）")
            out.append("")
        by_cat = {}
        for p in sorted(posts, key=lambda x: x.get("created_at", ""), reverse=True):
            by_cat.setdefault(p.get("category") or "未分类", []).append(p)
        for cat, items in by_cat.items():
            out.append(f"## {cat}")
            out.append("")
            for p in items:
                slug = cat_slug.get(p.get("category", ""), "uncategorized")
                url = f"{base}/{slug}/{p.get('slug', '')}"
                desc = (p.get("description") or "").strip().replace("\n", " ")[:120]
                line = f"- [{p.get('title', '无标题')}]({url})"
                out.append(f"{line}: {desc}" if desc else line)
            out.append("")
        return "\n".join(out)

    out = [f"# {dawn_site_name()}", "", f"> {intro}", ""]
    for p in sorted(posts, key=lambda x: x.get("created_at", ""), reverse=True):
        slug = cat_slug.get(p.get("category", ""), "uncategorized")
        url = f"{base}/{slug}/{p.get('slug', '')}"
        out.append(f"## {p.get('title', '无标题')}")
        out.append(f"URL: {url}")
        out.append(f"发布: {(p.get('created_at') or '')[:10]}  分类: {p.get('category', '')}")
        out.append("")
        out.append((p.get("content") or "").strip())
        out.append("\n---\n")
    return "\n".join(out)


# ---------- 增强 sitemap（image 扩展 + hreflang 注解 + 真实 lastmod） ----------

async def _dawn_i18n_data() -> tuple[list, dict]:
    """读 i18n 插件的语言配置与已完成译文（post_id -> [langs]）。未装/无译文返回空。"""
    try:
        db = await dawn_get_blog_db()
        try:
            row = await (await db.execute(
                "SELECT value FROM plugin_i18n_config WHERE key='languages'")).fetchone()
            langs = [l.strip() for l in ((row[0] if row else "") or "").split(",") if l.strip()]
            rows = await (await db.execute(
                "SELECT post_id, lang FROM plugin_i18n_translations WHERE status='done'")).fetchall()
            trans = {}
            for pid, lang in rows:
                if lang in langs:
                    trans.setdefault(pid, []).append(lang)
            return (langs if trans else [], trans)
        finally:
            await db.close()
    except Exception:
        return [], {}


def _dawn_hreflang_code(lang: str) -> str:
    """en-us -> en-US（hreflang 标准大小写）"""
    parts = lang.split("-", 1)
    return parts[0] + "-" + parts[1].upper() if len(parts) == 2 else lang


def _dawn_xhtml_links(zh_url: str, lang_urls: dict) -> str:
    out = [f'<xhtml:link rel="alternate" hreflang="zh-CN" href="{escape(zh_url)}"/>']
    for lang, url in lang_urls.items():
        out.append(f'<xhtml:link rel="alternate" hreflang="{_dawn_hreflang_code(lang)}" href="{escape(url)}"/>')
    out.append(f'<xhtml:link rel="alternate" hreflang="x-default" href="{escape(zh_url)}"/>')
    return "".join(out)


async def _dawn_build_sitemap() -> str:
    posts = await DawnBlogService.get_all_posts(published_only=True)
    posts = [p for p in posts if p.get("visibility", "public") == "public"]
    categories = await DawnBlogService.get_categories()
    cat_slug_by_name = {c.get("name", ""): c.get("slug", "") for c in categories}
    base = DAWN_SITE_BASE_URL.rstrip("/")
    i18n_langs, i18n_trans = await _dawn_i18n_data()

    def _lm(*vals):
        for v in vals:
            v = (v or "").strip()[:10]
            if v:
                return v
        return time.strftime("%Y-%m-%d")

    latest = max([_lm(p.get("updated_at"), p.get("created_at")) for p in posts] or [time.strftime("%Y-%m-%d")])
    home_alt = {l: f"{base}/{l}/" for l in i18n_langs}
    home_cluster = _dawn_xhtml_links(f"{base}/", home_alt) if home_alt else ""
    urls = [
        f'<url><loc>{base}/</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority>'
        + home_cluster + '</url>'
    ]
    # 译文首页（完整簇注解）
    for l, alt_url in home_alt.items():
        urls.append(f'<url><loc>{alt_url}</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority>'
                    + home_cluster + '</url>')
    # 标签页（译文标签页对所有配置语言存在）
    try:
        db0 = await dawn_get_blog_db()
        try:
            tag_rows = await (await db0.execute("SELECT slug FROM tags")).fetchall()
        finally:
            await db0.close()
    except Exception:
        tag_rows = []
    for t in tag_rows:
        tslug = t[0]
        if not tslug:
            continue
        zh_path, tpl = f"/tag/{tslug}", "/{l}/t/" + tslug
        alt = {l: f"{base}{tpl.format(l=l)}" for l in i18n_langs}
        cluster = _dawn_xhtml_links(f"{base}{zh_path}", alt) if alt else ""
        urls.append(f'<url><loc>{base}{zh_path}</loc><changefreq>weekly</changefreq><priority>0.5</priority>{cluster}</url>')
        for l in i18n_langs:
            urls.append(f'<url><loc>{base}{tpl.format(l=l)}</loc><changefreq>weekly</changefreq><priority>0.4</priority>{cluster}</url>')

    for cat in categories:
        slug = cat.get("slug", "")
        if not slug:
            continue
        cat_posts = [p for p in posts if (p.get("category") or "") == cat.get("name")]
        lm = max([_lm(p.get("updated_at"), p.get("created_at")) for p in cat_posts] or [latest])
        if cat.get("is_series"):
            zh_path, tpl = f"/series/{slug}", "/{l}/s/" + slug
        else:
            zh_path, tpl = f"/{slug}", "/{l}/c/" + slug
        alt = {l: f"{base}{tpl.format(l=l)}" for l in i18n_langs}
        cluster = _dawn_xhtml_links(f"{base}{zh_path}", alt) if alt else ""
        urls.append(f'<url><loc>{base}{zh_path}</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq><priority>0.75</priority>{cluster}</url>')
        for l in i18n_langs:
            urls.append(f'<url><loc>{base}{tpl.format(l=l)}</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority>{cluster}</url>')
    for post in posts:
        cat_slug = cat_slug_by_name.get(post.get("category", ""), "uncategorized")
        lm = _lm(post.get("updated_at"), post.get("created_at"))
        zh_url = f"{base}/{cat_slug}/{post.get('slug', '')}"
        post_langs = i18n_trans.get(post.get("id"), [])
        alt = {l: f"{base}/{l}/{post.get('slug', '')}" for l in post_langs}
        cluster = _dawn_xhtml_links(zh_url, alt) if alt else ""

        def _post_block(loc):
            b = f'<url><loc>{loc}</loc><lastmod>{lm}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority>{cluster}'
            cover = (post.get("cover_image") or "").strip()
            if cover:
                cover_url = cover if cover.startswith("http") else f"{base}{cover}"
                b += (f'<image:image><image:loc>{escape(cover_url)}</image:loc>'
                      f'<image:title>{escape(post.get("title", ""))}</image:title></image:image>')
            return b + '</url>'

        urls.append(_post_block(zh_url))
        for l in post_langs:
            urls.append(_post_block(f"{base}/{l}/{post.get('slug', '')}"))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
            + "\n".join(urls) + "\n</urlset>")


# ---------- 同步钩子：head 注入 + 每篇覆盖 ----------

def _dawn_build_site_schema(cfg: dict) -> str:
    """按插件配置重建站点级 JSON-LD（Organization + WebSite，谷歌官方结构化数据指南）"""
    import json as _json
    base = DAWN_SITE_BASE_URL.rstrip("/")
    org_name = (cfg.get("org_name") or "").strip() or dawn_site_name()
    org_logo = (cfg.get("org_logo") or "").strip() or f"{base}/static/logo.svg"
    if org_logo.startswith("/"):
        org_logo = base + org_logo
    org_type = cfg.get("org_type") if cfg.get("org_type") in ("Organization", "Person") else "Organization"
    org = {"@context": "https://schema.org", "@type": org_type,
           "name": org_name, "url": base}
    if org_type == "Organization":
        org["logo"] = {"@type": "ImageObject", "url": org_logo, "width": 96, "height": 96}
    else:
        org["image"] = org_logo
    sameas = [s.strip() for s in (cfg.get("org_sameas") or "").split(",") if s.strip()]
    if sameas:
        org["sameAs"] = sameas
    website = {"@context": "https://schema.org", "@type": "WebSite",
               "name": org_name, "url": base,
               "description": (cfg.get("seo_home_desc") or "").strip() or dawn_site_tagline(),
               "inLanguage": "zh-CN",
               "publisher": {"@type": org_type, "name": org_name},
               "potentialAction": {"@type": "SearchAction",
                                   "target": {"@type": "EntryPoint",
                                              "urlTemplate": f"{base}/search?q={{search_term_string}}"},
                                   "query-input": "required name=search_term_string"}}
    return ('<script type="application/ld+json">' + _json.dumps(org, ensure_ascii=False) + '</script>\n'
            '<script type="application/ld+json">' + _json.dumps(website, ensure_ascii=False) + '</script>')


def _dawn_seo_ctx_hook(ctx: dict):
    """seo_ctx：渲染前按配置/文章覆盖标题、描述、robots、OG 图、站点 schema（原地修改 ctx）"""
    cfg = _dawn_cfg_sync()

    # 首页标题/描述覆盖
    if ctx.get("is_home"):
        if (cfg.get("seo_home_title") or "").strip():
            ctx["page_title"] = cfg["seo_home_title"].strip()
        if (cfg.get("seo_home_desc") or "").strip():
            ctx["page_desc"] = cfg["seo_home_desc"].strip()

    # 标题分隔符（如 "｜"）
    sep = (cfg.get("title_sep") or "").strip()
    if sep and not ctx.get("is_home"):
        suffix = f" - {dawn_site_name()}"
        pt = ctx.get("page_title", "")
        if pt.endswith(suffix):
            ctx["page_title"] = pt[:-len(suffix)] + f" {sep} {dawn_site_name()}"

    # 默认 OG 图
    if (cfg.get("og_image") or "").strip():
        og = cfg["og_image"].strip()
        if og.startswith("/"):
            og = DAWN_SITE_BASE_URL.rstrip("/") + og
        ctx["og_image"] = og

    # 站点级 schema（组织名/logo/类型/sameAs 任一自定义时重建）
    if any((cfg.get(k) or "").strip() for k in ("org_name", "org_logo", "org_sameas", "seo_home_desc")) \
            or cfg.get("org_type") != "Organization":
        ctx["site_schema"] = _dawn_build_site_schema(cfg)

    # 每篇文章覆盖
    a = ctx.get("a")
    if not isinstance(a, dict) or not a.get("slug"):
        return
    seo = _dawn_post_seo_sync(a["slug"])
    if seo.get("seo_title"):
        ctx["page_title"] = seo["seo_title"]
        a["title"] = seo["seo_title"]
    if seo.get("seo_desc"):
        ctx["page_desc"] = seo["seo_desc"]
        a["desc"] = seo["seo_desc"]
    if seo.get("robots"):
        ctx["robots_meta"] = seo["robots"]


def _dawn_head_extra_hook(ctx: dict) -> str:
    """head_extra：全站注入验证标记、twitter:site、文章时间戳、max-image-preview"""
    cfg = _dawn_cfg_sync()
    tags = []
    if cfg.get("gsc_token"):
        tags.append(f'<meta name="google-site-verification" content="{escape(cfg["gsc_token"])}">')
    if cfg.get("bing_token"):
        tags.append(f'<meta name="msvalidate.01" content="{escape(cfg["bing_token"])}">')
    if cfg.get("twitter_handle"):
        h = cfg["twitter_handle"].lstrip("@")
        tags.append(f'<meta name="twitter:site" content="@{escape(h)}">')
    robots_add = "max-image-preview:large,max-snippet:-1"
    if ctx.get("robots_meta"):
        tags.insert(0, f'<meta name="robots" content="{escape(ctx["robots_meta"])},{robots_add}">')
        ctx["robots_meta"] = ""  # 已由本插件合并输出，清掉 base 的
    else:
        tags.insert(0, f'<meta name="robots" content="{robots_add}">')
    a = ctx.get("a")
    if isinstance(a, dict) and a.get("slug"):
        if a.get("date"):
            tags.append(f'<meta property="article:published_time" content="{escape(a["date"])}">')
        if a.get("updated"):
            tags.append(f'<meta property="article:modified_time" content="{escape(a["updated"])}">')
        if a.get("author"):
            tags.append(f'<meta name="author" content="{escape(str(a["author"]))}">')
    return "\n".join(tags)


# ---------- 后台：编辑页 SEO 面板 ----------

def _dawn_admin_post_panel_hook(post_id: int = 0, post: dict = None):
    post = post or {}
    slug = post.get("slug", "")
    seo = _dawn_post_seo_sync(slug) if slug else {}
    return Div(
        H3("🔍 SEO 设置（SEO / GEO 插件）", cls="text-sm font-bold text-slate-200 mb-3"),
        P("留空则使用文章标题/摘要。标题建议 10-60 字符，描述建议 70-160 字符。", cls="text-xs text-slate-500 mb-3"),
        Label("SEO 标题覆盖", cls=DAWN_LABEL),
        Input(id="seo-title", value=seo.get("seo_title", ""), placeholder=post.get("title", ""),
              cls=DAWN_INPUT + " w-full mb-3"),
        Label("SEO 描述覆盖", cls=DAWN_LABEL),
        Textarea(seo.get("seo_desc", ""), id="seo-desc", rows=2,
                 placeholder=(post.get("description", "") or "")[:80],
                 cls=DAWN_INPUT + " w-full mb-3"),
        Label(
            Input(type="checkbox", id="seo-noindex", checked=bool(seo.get("robots")),
                  cls="mr-2 accent-emerald-500"),
            "noindex（不收录此文章）",
            cls="text-sm text-slate-300 flex items-center mb-3"),
        Div(
            Button("💾 保存 SEO 设置", type="button", cls=DAWN_BTN_GHOST,
                   onclick=f"window.dawnSeoSave && window.dawnSeoSave('{slug}')"),
            Span(id="seo-save-msg", cls="text-xs text-slate-500 ml-3"),
            cls="flex items-center"),
        _dawn_seo_panel_js(),
        cls="mt-8 p-5 rounded-xl border border-slate-800 bg-slate-900/40",
    )


def _dawn_seo_panel_js():
    from fasthtml.common import Script
    return Script("""
window.dawnSeoSave = async function(slug){
  var msg = document.getElementById('seo-save-msg');
  var fd = new FormData();
  fd.append('slug', slug);
  fd.append('seo_title', document.getElementById('seo-title').value);
  fd.append('seo_desc', document.getElementById('seo-desc').value);
  fd.append('robots', document.getElementById('seo-noindex').checked ? 'noindex,follow' : '');
  try{
    var r = await fetch('/dadmin/plugins/seogeo/api/save_post', {method:'POST', body:fd});
    var j = await r.json();
    msg.textContent = j.ok ? '✅ 已保存' : ('❌ ' + (j.error||'失败'));
  }catch(e){ msg.textContent = '❌ 网络错误'; }
  setTimeout(function(){ msg.textContent=''; }, 3000);
};
""")


# ---------- 后台：体检 ----------

def _dawn_check_post(p: dict, cat_slug_map: dict) -> list:
    """返回 (检查项, 是否通过, 说明) 列表，依据谷歌官方文档"""
    checks = []
    title = p.get("title", "") or ""
    tlen = len(title)
    checks.append(("标题长度", 10 <= tlen <= 60, f"{tlen} 字符（建议 10-60）"))
    desc = (p.get("description") or "").strip()
    dlen = len(desc)
    checks.append(("meta 描述", 70 <= dlen <= 160, f"{dlen} 字符（建议 70-160）" if desc else "缺失"))
    checks.append(("封面图（og:image）", bool((p.get("cover_image") or "").strip()), ""))
    slug = p.get("slug", "") or ""
    import re as _re
    checks.append(("slug 规范", bool(_re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug)),
                   "小写字母数字+连字符"))
    content = p.get("content", "") or ""
    checks.append(("正文长度", len(content) >= 300, f"{len(content)} 字符（至少 300）"))
    checks.append(("关键词字段", bool((p.get("keywords") or "").strip()), ""))
    checks.append(("正文含内链", content.count("](") >= 1, "至少 1 个链接"))
    return checks


async def _dawn_site_checks() -> list:
    checks = []
    base = DAWN_SITE_BASE_URL.rstrip("/")
    checks.append(("SITE_BASE_URL 非 localhost", "localhost" not in base and "127.0.0.1" not in base,
                   f"当前 {base}（上线前必须改为正式域名）"))
    checks.append(("HTTPS", base.startswith("https://"), "谷歌技术要求之一"))
    cfg = await _dawn_get_config()
    checks.append(("Search Console 验证 token", bool(cfg.get("gsc_token")), "设置页填入"))
    checks.append(("favicon", (Path("static/logo.svg").exists()), "static/logo.svg"))
    checks.append(("首页标题自定义", bool((cfg.get("seo_home_title") or "").strip()),
                   "设置页可覆盖（谷歌可能重写，但自定义可提高相关性）"))
    checks.append(("首页描述自定义", bool((cfg.get("seo_home_desc") or "").strip()), "建议 70-160 字符"))
    checks.append(("默认 OG 图自定义", bool((cfg.get("og_image") or "").strip()), "建议 1200×630"))
    checks.append(("组织 schema 信息", bool((cfg.get("org_name") or "").strip() or (cfg.get("org_sameas") or "").strip()),
                   "名称/sameAs 可增强知识面板"))
    checks.append(("sitemap 含图片扩展", True, "本插件已增强"))
    checks.append(("robots.txt 动态化", True, f"当前模式：{cfg.get('robots_mode')}"))
    checks.append(("llms.txt", cfg.get("llms_enabled") == "1", "社区约定，可在设置页关闭"))
    checks.append(("会员/搜索页 noindex", True, "搜索页与登录注册页已内置"))
    return checks


# ---------- 后台页面 ----------

def _dawn_notes_section():
    cards = []
    for title, body, url in DAWN_GOOGLE_NOTES:
        cards.append(Div(
            Div(
                Span("⚠️", cls="mr-2"),
                Span(title, cls="text-sm font-bold text-amber-300"),
                A("官方文档 ↗", href=url, target="_blank", rel="noopener",
                  cls="ml-auto text-xs text-indigo-400 hover:text-indigo-300"),
                cls="flex items-center mb-1.5"),
            P(body, cls="text-xs text-slate-400 leading-relaxed"),
            cls="p-4 rounded-xl border border-amber-900/40 bg-amber-950/20"))
    return Div(
        H2("谷歌官方注意事项", cls="text-lg font-bold text-white mb-1"),
        P("以下提醒均来自 Google Search Central 官方文档（2025-12 更新），改动前请阅读对应文档。",
          cls="text-xs text-slate-500 mb-4"),
        Div(*cards, cls="grid grid-cols-1 lg:grid-cols-2 gap-3"),
        cls="mt-10")


def dawn_setup(app):
    dawn_register_admin_page(DAWN_PLUGIN["group"], DAWN_PLUGIN["key"], DAWN_PLUGIN["label"],
                             DAWN_PLUGIN["url"], DAWN_PLUGIN["icon"])
    dawn_register_hook("head_extra", _dawn_head_extra_hook)
    dawn_register_hook("seo_ctx", _dawn_seo_ctx_hook)
    dawn_register_hook("admin_post_panel", _dawn_admin_post_panel_hook)

    # ---- 前台路由（先于核心 frontend.setup 注册，覆盖默认 robots/sitemap） ----

    @app.get("/robots.txt")
    async def dawn_robots():
        cfg = await _dawn_get_config()
        return PlainTextResponse(_dawn_build_robots(cfg))

    @app.get("/llms.txt")
    async def dawn_llms_txt():
        cfg = await _dawn_get_config()
        if cfg.get("llms_enabled") != "1":
            return PlainTextResponse("llms.txt disabled", status_code=404)
        return PlainTextResponse(await _dawn_llms_payload(full=False))

    @app.get("/llms-full.txt")
    async def dawn_llms_full():
        cfg = await _dawn_get_config()
        if cfg.get("llms_enabled") != "1":
            return PlainTextResponse("llms-full.txt disabled", status_code=404)
        return PlainTextResponse(await _dawn_llms_payload(full=True))

    @app.get("/sitemap.xml")
    async def dawn_sitemap():
        return Response(await _dawn_build_sitemap(), media_type="application/xml")

    # ---- 后台：设置页 ----

    @app.get("/dadmin/plugins/seogeo")
    async def seogeo_admin(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        cfg = await _dawn_get_config()
        mode = cfg.get("robots_mode", "allow_all")

        def _radio(val, label):
            return Label(
                Input(type="radio", name="robots_mode", value=val, checked=(mode == val),
                      cls="mr-2 accent-emerald-500"),
                Span(label, cls="text-sm text-slate-300"),
                cls="flex items-center gap-1")

        crawler_rows = [
            Tr(Td(a, cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
               Td(n, cls="px-3 py-1.5 text-xs text-slate-500"))
            for a, n in DAWN_AI_CRAWLERS
        ]
        preview = _dawn_build_robots(cfg)

        return _dawn_admin_shell("seogeo", Div(
            _dawn_msg(msg) if msg else None,
            H1("SEO / GEO 设置", cls="text-2xl font-black text-white mb-6"),
            Div(
                A("🔍 设置", href="/dadmin/plugins/seogeo", cls="text-sm text-emerald-400 font-bold mr-5"),
                A("🩺 SEO 体检", href="/dadmin/plugins/seogeo/checkup",
                  cls="text-sm text-slate-400 hover:text-slate-200"),
                cls="mb-6"),
            Form(
                H2("站点 SEO 基础", cls="text-base font-bold text-white mb-3"),
                Label("首页标题（&lt;title&gt;，留空用站点名）", cls=DAWN_LABEL),
                Input(name="seo_home_title", value=cfg.get("seo_home_title", ""),
                      placeholder=dawn_site_name(), cls=DAWN_INPUT + " w-full mb-3"),
                Label("首页描述（meta description，留空用站点标语）", cls=DAWN_LABEL),
                Textarea(cfg.get("seo_home_desc", ""), name="seo_home_desc", rows=2,
                         placeholder=dawn_site_tagline(), cls=DAWN_INPUT + " w-full mb-3"),
                Label("标题分隔符（留空用「-」，常见「｜」）", cls=DAWN_LABEL),
                Input(name="title_sep", value=cfg.get("title_sep", ""), placeholder="｜",
                      cls=DAWN_INPUT + " w-32 mb-3"),
                Label("默认 OG 分享图（留空用 /static/logo.svg，建议 1200×630）", cls=DAWN_LABEL),
                Input(name="og_image", value=cfg.get("og_image", ""), placeholder="/static/og-cover.png",
                      cls=DAWN_INPUT + " w-full mb-6"),

                H2("组织信息（Organization / WebSite schema）", cls="text-base font-bold text-white mb-3"),
                Label("组织/作者类型", cls=DAWN_LABEL),
                Div(
                    Label(Input(type="radio", name="org_type", value="Organization",
                                checked=(cfg.get("org_type") != "Person"), cls="mr-2 accent-emerald-500"),
                          Span("Organization（组织/品牌）", cls="text-sm text-slate-300"), cls="flex items-center mr-5"),
                    Label(Input(type="radio", name="org_type", value="Person",
                                checked=(cfg.get("org_type") == "Person"), cls="mr-2 accent-emerald-500"),
                          Span("Person（个人博客）", cls="text-sm text-slate-300"), cls="flex items-center"),
                    cls="flex mb-3"),
                Label("名称（留空用站点名）", cls=DAWN_LABEL),
                Input(name="org_name", value=cfg.get("org_name", ""), cls=DAWN_INPUT + " w-full mb-3"),
                Label("Logo URL（留空用 /static/logo.svg）", cls=DAWN_LABEL),
                Input(name="org_logo", value=cfg.get("org_logo", ""), cls=DAWN_INPUT + " w-full mb-3"),
                Label("社交/主页链接（sameAs，逗号分隔）", cls=DAWN_LABEL),
                Input(name="org_sameas", value=cfg.get("org_sameas", ""),
                      placeholder="https://x.com/xxx, https://github.com/xxx", cls=DAWN_INPUT + " w-full mb-6"),

                H2("搜索引擎验证", cls="text-base font-bold text-white mb-3"),
                Label("Google Search Console HTML 标记 content 值", cls=DAWN_LABEL),
                Input(name="gsc_token", value=cfg.get("gsc_token", ""),
                      placeholder="google-site-verification=xxx 中的 content", cls=DAWN_INPUT + " w-full mb-3"),
                Label("Bing Webmaster msvalidate.01", cls=DAWN_LABEL),
                Input(name="bing_token", value=cfg.get("bing_token", ""), cls=DAWN_INPUT + " w-full mb-3"),
                Label("Twitter / X 账号（twitter:site）", cls=DAWN_LABEL),
                Input(name="twitter_handle", value=cfg.get("twitter_handle", ""), placeholder="@yourhandle",
                      cls=DAWN_INPUT + " w-full mb-6"),

                H2("AI 爬虫管控（robots.txt）", cls="text-base font-bold text-white mb-3"),
                Div(_radio("allow_all", "全部放行（默认，利于被 AI 搜索引用）"),
                    _radio("block_ai", "屏蔽已知 AI 训练/搜索爬虫（不影响谷歌/必应收录）"),
                    _radio("custom", "完全自定义"),
                    cls="flex flex-wrap gap-5 mb-3"),
                Textarea(cfg.get("robots_custom", ""), name="robots_custom", rows=4,
                         placeholder="自定义模式时生效：完整 robots.txt 内容（Sitemap 行会自动追加）",
                         cls=DAWN_INPUT + " w-full font-mono text-xs mb-3"),
                H3("当前 robots.txt 预览", cls="text-xs font-bold text-slate-400 mb-1"),
                Textarea(preview, readonly=True, rows=min(preview.count("\n") + 1, 14),
                         cls=DAWN_INPUT + " w-full font-mono text-xs mb-4 opacity-70"),

                H2("llms.txt（GEO，社区约定）", cls="text-base font-bold text-white mb-3"),
                Label(
                    Input(type="checkbox", name="llms_enabled", value="1",
                          checked=(cfg.get("llms_enabled") == "1"), cls="mr-2 accent-emerald-500"),
                    Span("启用 /llms.txt 与 /llms-full.txt", cls="text-sm text-slate-300"),
                    cls="flex items-center mb-3"),
                Label("站点简介（llms.txt 顶部引用块，留空用站点标语）", cls=DAWN_LABEL),
                Textarea(cfg.get("llms_intro", ""), name="llms_intro", rows=2,
                         cls=DAWN_INPUT + " w-full mb-6"),

                Button("💾 保存设置", type="submit", cls=DAWN_BTN),
                method="post", action="/dadmin/plugins/seogeo/save",
                cls="p-5 rounded-xl border border-slate-800 bg-slate-900/40"),
            Div(
                H3("AI 爬虫清单参考", cls="text-sm font-bold text-slate-300 mb-2"),
                Table(
                    Thead(Tr(Th("User-agent", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                             Th("说明", cls="px-3 py-2 text-left text-slate-500 text-xs"))),
                    Tbody(*crawler_rows),
                    cls="w-full rounded-xl overflow-hidden border border-slate-800"),
                cls="mt-8"),
            _dawn_notes_section(),
        ))

    @app.post("/dadmin/plugins/seogeo/save")
    async def seogeo_save(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        data = {k: form.get(k, "") for k in DAWN_DEFAULTS}
        data["llms_enabled"] = "1" if form.get("llms_enabled") else "0"
        await _dawn_save_config(data)
        return RedirectResponse("/dadmin/plugins/seogeo?msg=已保存", status_code=303)

    # ---- 后台：体检页 ----

    @app.get("/dadmin/plugins/seogeo/checkup")
    async def seogeo_checkup(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        site_checks = await _dawn_site_checks()
        posts = await DawnBlogService.get_all_posts(published_only=False)
        categories = await DawnBlogService.get_categories()
        cat_slug_map = {c.get("name", ""): c.get("slug", "") for c in categories}

        site_rows = []
        for name, ok, note in site_checks:
            site_rows.append(Tr(
                Td("✅" if ok else "🔴", cls="px-3 py-2"),
                Td(name, cls="px-3 py-2 text-sm text-slate-200"),
                Td(note, cls="px-3 py-2 text-xs text-slate-500")))

        post_rows = []
        for p in posts:
            checks = _dawn_check_post(p, cat_slug_map)
            passed = sum(1 for _n, ok, _d in checks if ok)
            total = len(checks)
            fails = [f"{n}（{d}）" if d else n for n, ok, d in checks if not ok]
            score_cls = ("text-emerald-400" if passed == total else
                         "text-amber-400" if passed >= total - 2 else "text-red-400")
            post_rows.append(Tr(
                Td(Span(f"{passed}/{total}", cls=f"font-mono font-bold {score_cls}"), cls="px-3 py-2"),
                Td(A(p.get("title", "")[:30], href=f"/dadmin/post/edit/{p.get('id')}",
                     cls="text-sm text-slate-200 hover:text-emerald-300"), cls="px-3 py-2"),
                Td("、".join(fails) if fails else "全部通过",
                   cls="px-3 py-2 text-xs text-slate-500")))

        return _dawn_admin_shell("seogeo", Div(
            H1("SEO 体检", cls="text-2xl font-black text-white mb-6"),
            Div(
                A("🔍 设置", href="/dadmin/plugins/seogeo", cls="text-sm text-slate-400 hover:text-slate-200 mr-5"),
                A("🩺 SEO 体检", href="/dadmin/plugins/seogeo/checkup", cls="text-sm text-emerald-400 font-bold"),
                cls="mb-6"),
            H2("站点级检查", cls="text-base font-bold text-white mb-3"),
            Table(Tbody(*site_rows),
                  cls="w-full rounded-xl overflow-hidden border border-slate-800 mb-8"),
            H2("文章级检查（依据谷歌标题链接 / 摘要 / URL 结构官方指南）", cls="text-base font-bold text-white mb-3"),
            Table(
                Thead(Tr(Th("得分", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                         Th("文章", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                         Th("待改进项", cls="px-3 py-2 text-left text-slate-500 text-xs"))),
                Tbody(*post_rows),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"),
            _dawn_notes_section(),
        ))

    # ---- 后台：文章 SEO JSON API ----

    @app.post("/dadmin/plugins/seogeo/api/save_post")
    async def seogeo_save_post(session, request):
        if not _dawn_require_admin(session):
            return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
        form = await request.form()
        slug = (form.get("slug") or "").strip()
        if not slug:
            return JSONResponse({"ok": False, "error": "参数无效"})
        await _dawn_ensure_tables()
        db = await dawn_get_blog_db()
        try:
            await db.execute(
                "INSERT INTO plugin_seogeo_post(slug, seo_title, seo_desc, robots, updated_at) "
                "VALUES(?, ?, ?, ?, datetime('now')) "
                "ON CONFLICT(slug) DO UPDATE SET seo_title=excluded.seo_title, "
                "seo_desc=excluded.seo_desc, robots=excluded.robots, updated_at=excluded.updated_at",
                (slug, form.get("seo_title", ""), form.get("seo_desc", ""), form.get("robots", "")))
            await db.commit()
        finally:
            await db.close()
        return JSONResponse({"ok": True})
