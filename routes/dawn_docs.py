# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/docs.py
# /docs 文档中心：主题开发文档（分篇），注册在 frontend 之前避免被分类路由吃掉
# 页面结构由主题模板 docs-index.html / docs-article.html 控制

from pathlib import Path
from fasthtml.common import *

from dawn_config import DAWN_SITE_BASE_URL
from ui.dawn_article import DAWN_DOC_JS, dawn_extract_toc_and_anchors
from services.dawn_markdown_renderer import DawnMarkdownRenderer
from routes.dawn_frontend import _dawn_render

DAWN_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "theme-dev"

DAWN_DOCS = [
    {"slug": "quick-start", "num": "01", "title": "快速上手", "desc": "主题包结构、extends 继承、最小主题、三步上线", "file": "01-quick-start.md"},
    {"slug": "tokens", "num": "02", "title": "变量参考", "desc": "全部 28 个 token 的用途、默认值与联动关系", "file": "02-tokens.md"},
    {"slug": "design-guide", "num": "03", "title": "设计指南", "desc": "换肤还是换骨、对比度底线、深浅主题技巧、检验清单", "file": "03-design-guide.md"},
    {"slug": "upload-debug", "num": "04", "title": "上传、调试与 FAQ", "desc": "zip 打包规范、DevTools 实时调色、模板调试、常见问题", "file": "04-upload-debug.md"},
]


def _dawn_load_doc(slug: str) -> dict | None:
    doc = next((d for d in DAWN_DOCS if d["slug"] == slug), None)
    if not doc:
        return None
    path = DAWN_DOCS_DIR / doc["file"]
    if not path.exists():
        return None
    return {**doc, "markdown": path.read_text(encoding="utf-8")}


def dawn_setup(app):
    @app.get("/docs")
    async def docs_index(session):
        return _dawn_render(
            "docs-index.html", session,
            title="主题开发文档",
            desc="DawnCMS 主题开发文档：快速上手、变量参考、设计指南、上传调试。",
            canonical=f"{DAWN_SITE_BASE_URL}/docs",
            docs_intro="主题包 = theme.json + vars.json + style.css + Jinja2 模板。从快速上手到设计指南，四篇讲完。",
            docs_items=DAWN_DOCS,
        )

    @app.get("/docs/{slug}")
    async def docs_article(session, slug: str):
        from starlette.exceptions import HTTPException
        doc = _dawn_load_doc(slug)
        if not doc:
            raise HTTPException(status_code=404)

        html = DawnMarkdownRenderer.render_with_prose(doc["markdown"])
        toc_items, html_with_ids = dawn_extract_toc_and_anchors(html)
        idx = next((i for i, d in enumerate(DAWN_DOCS) if d["slug"] == slug), 0)
        prev_doc = DAWN_DOCS[idx - 1] if idx > 0 else None
        next_doc = DAWN_DOCS[idx + 1] if idx + 1 < len(DAWN_DOCS) else None

        return _dawn_render(
            "docs-article.html", session,
            title=f"{doc['title']} - 主题开发文档",
            desc=doc["desc"],
            canonical=f"{DAWN_SITE_BASE_URL}/docs/{doc['slug']}",
            doc=doc, doc_html=html_with_ids, toc=toc_items,
            docs_items=DAWN_DOCS, prev_doc=prev_doc, next_doc=next_doc,
            doc_js=DAWN_DOC_JS,
        )
