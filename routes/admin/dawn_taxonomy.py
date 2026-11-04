# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/taxonomy.py
# 分类 / 连载系列 / 标签

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
    @app.get("/dadmin/categories")
    async def admin_categories(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        categories = await DawnBlogService.get_categories()
        from plugins import dawn_collect_hooks
        tax_langs = (await dawn_collect_hooks("admin_tax_langs") or [[]])[0]
        tax_assets = await dawn_collect_hooks("admin_tax_assets")
        rows = []
        for c in categories:
            tax_cells = await dawn_collect_hooks("admin_tax_cell", kind="category", item=c)
            tax_cells = [td for grp in tax_cells for td in (grp if isinstance(grp, list) else [grp])]
            rows.append(Tr(
            Td(str(c.get("id")), cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td(c.get("name", ""), cls="px-3 py-2.5 text-slate-200 text-sm font-semibold"),
            Td(c.get("slug", ""), cls="px-3 py-2.5 text-slate-400 text-xs font-mono"),
            Td(c.get("description", ""), cls="px-3 py-2.5 text-slate-400 text-xs"),
            Td(str(c.get("sort_order", 0)), cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td("📚 连载" if c.get("is_series") else "—", cls="px-3 py-2.5 text-xs " + ("text-amber-400 font-semibold" if c.get("is_series") else "text-slate-600")),
            *tax_cells,
            Td(
                Form(
                    Input(type="hidden", name="cat_id", value=str(c.get("id"))),
                    Input(name="name", value=c.get("name", ""), cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-24"),
                    Input(name="slug", value=c.get("slug", ""), cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-28 ml-1"),
                    Input(name="sort_order", value=str(c.get("sort_order", 0)), type="number", cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-16 ml-1"),
                    Label(
                        Input(type="checkbox", name="is_series", value="1", checked=bool(c.get("is_series")), cls="mr-1"),
                        Span("连载教程", cls="text-xs text-slate-400"),
                        cls="inline-flex items-center ml-2"
                    ),
                    Button("保存", type="submit", cls=DAWN_BTN_GHOST + " ml-1"),
                    method="post", action="/dadmin/category/update", style="display:inline"
                ),
                Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('确认删除该分类？文章不会被删除。')"),
                     method="post", action=f"/dadmin/category/delete/{c.get('id')}", style="display:inline;margin-left:6px"),
                cls="px-3 py-2.5 whitespace-nowrap"
            ),
            cls="border-b border-slate-800/60"
        ))

        return _dawn_admin_shell("categories", Div(
            _dawn_msg(msg) if msg else None,
            H1("分类管理", cls="text-2xl font-black text-white mb-6"),
            Form(
                Input(name="name", placeholder="分类名称", required=True, cls=DAWN_INPUT + " w-40"),
                Input(name="slug", placeholder="slug", required=True, cls=DAWN_INPUT + " w-40 ml-2"),
                Input(name="description", placeholder="描述", cls=DAWN_INPUT + " w-56 ml-2"),
                Input(name="sort_order", placeholder="排序", type="number", value="0", cls=DAWN_INPUT + " w-20 ml-2"),
                Label(
                    Input(type="checkbox", name="is_series", value="1", cls="mr-1"),
                    Span("连载教程", cls="text-xs text-slate-400"),
                    cls="inline-flex items-center ml-2"
                ),
                Button("＋ 新增分类", type="submit", cls=DAWN_BTN + " ml-2"),
                method="post", action="/dadmin/category/create",
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-wrap items-center gap-y-2"
            ),
            Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in (["ID", "名称", "Slug", "描述", "排序", "类型"] + [f"译名·{l.split('-')[0].upper()}" for l in tax_langs] + ["操作"])])),
                Tbody(*rows),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"
            ),
            *tax_assets,
        ))

    @app.post("/dadmin/category/create")
    async def admin_category_create(session, name: str = "", slug: str = "", description: str = "", sort_order: int = 0, is_series: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        try:
            await DawnBlogService.create_category({"name": name.strip(), "slug": slug.strip(), "description": description.strip(), "sort_order": int(sort_order or 0), "is_series": 1 if is_series else 0})
        except Exception as e:
            return RedirectResponse(f"/dadmin/categories?msg=创建失败：{str(e)[:80]}", status_code=303)
        return RedirectResponse("/dadmin/categories?msg=已创建", status_code=303)

    @app.post("/dadmin/category/update")
    async def admin_category_update(session, cat_id: int = 0, name: str = "", slug: str = "", sort_order: int = 0, is_series: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.update_category(int(cat_id), {"name": name.strip(), "slug": slug.strip(), "sort_order": int(sort_order or 0), "is_series": 1 if is_series else 0})
        return RedirectResponse("/dadmin/categories?msg=已保存", status_code=303)

    @app.post("/dadmin/category/delete/{cat_id}")
    async def admin_category_delete(session, cat_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.delete_category(cat_id)
        return RedirectResponse("/dadmin/categories?msg=已删除", status_code=303)

    @app.get("/dadmin/series")
    async def admin_series(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        all_series = await DawnBlogService.get_series()
        from plugins import dawn_collect_hooks
        tax_langs = (await dawn_collect_hooks("admin_tax_langs") or [[]])[0]
        tax_assets = await dawn_collect_hooks("admin_tax_assets")
        rows = []
        for s in all_series:
            cnt = len(await DawnBlogService.get_series_posts(s.get("id"), include_admin=True))
            tax_cells = await dawn_collect_hooks("admin_tax_cell", kind="series", item=s)
            tax_cells = [td for grp in tax_cells for td in (grp if isinstance(grp, list) else [grp])]
            rows.append(Tr(
                Td(str(s.get("id")), cls="px-3 py-2.5 text-slate-500 text-xs"),
                Td(s.get("name", ""), cls="px-3 py-2.5 text-slate-200 text-sm font-semibold"),
                Td(s.get("slug", ""), cls="px-3 py-2.5 text-slate-400 text-xs font-mono"),
                Td(s.get("description", ""), cls="px-3 py-2.5 text-slate-400 text-xs"),
                Td(f"{cnt} 篇", cls="px-3 py-2.5 text-slate-500 text-xs"),
                *tax_cells,
                Td(
                    A("查看", href=f"/series/{s.get('slug','')}", target="_blank", cls="text-indigo-400 hover:text-indigo-300 text-xs mr-3"),
                    Form(
                        Input(type="hidden", name="series_id", value=str(s.get("id"))),
                        Input(name="name", value=s.get("name", ""), cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-28"),
                        Input(name="slug", value=s.get("slug", ""), cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-28 ml-1"),
                        Input(name="sort_order", value=str(s.get("sort_order", 0)), type="number", cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-16 ml-1"),
                        Button("保存", type="submit", cls=DAWN_BTN_GHOST + " ml-1"),
                        method="post", action="/dadmin/series/update", style="display:inline"
                    ),
                    Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('删除系列？文章会保留，仅解除关联。')"),
                         method="post", action=f"/dadmin/series/delete/{s.get('id')}", style="display:inline;margin-left:6px"),
                    cls="px-3 py-2.5 whitespace-nowrap"
                ),
                cls="border-b border-slate-800/60"
            ))

        return _dawn_admin_shell("series", Div(
            _dawn_msg(msg) if msg else None,
            H1("连载系列", cls="text-2xl font-black text-white mb-2"),
            P("系列是跨分类的连载合集：文章在编辑器里选择所属系列并填序号，前台按序号正序输出。删除系列不会删除文章。", cls="text-slate-500 text-sm mb-6"),
            Form(
                Input(name="name", placeholder="系列名称", required=True, cls=DAWN_INPUT + " w-44"),
                Input(name="slug", placeholder="slug", required=True, cls=DAWN_INPUT + " w-40 ml-2"),
                Input(name="description", placeholder="描述", cls=DAWN_INPUT + " w-64 ml-2"),
                Button("＋ 新增系列", type="submit", cls=DAWN_BTN + " ml-2"),
                method="post", action="/dadmin/series/create",
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-wrap items-center gap-y-2"
            ),
            Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in (["ID", "名称", "Slug", "描述", "文章数"] + [f"译名·{l.split('-')[0].upper()}" for l in tax_langs] + ["操作"])])),
                Tbody(*rows),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"
            ),
            *tax_assets,
        ))

    @app.post("/dadmin/series/create")
    async def admin_series_create(session, name: str = "", slug: str = "", description: str = "", sort_order: int = 0):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        try:
            await DawnBlogService.create_series({"name": name.strip(), "slug": slug.strip(), "description": description.strip(), "sort_order": int(sort_order or 0)})
        except Exception as e:
            return RedirectResponse(f"/dadmin/series?msg=创建失败：{str(e)[:80]}", status_code=303)
        return RedirectResponse("/dadmin/series?msg=已创建", status_code=303)

    @app.post("/dadmin/series/update")
    async def admin_series_update(session, series_id: int = 0, name: str = "", slug: str = "", sort_order: int = 0):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.update_series(int(series_id), {"name": name.strip(), "slug": slug.strip(), "sort_order": int(sort_order or 0)})
        return RedirectResponse("/dadmin/series?msg=已保存", status_code=303)

    @app.post("/dadmin/series/delete/{series_id}")
    async def admin_series_delete(session, series_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.delete_series(series_id)
        return RedirectResponse("/dadmin/series?msg=已删除（文章已解除关联）", status_code=303)

    @app.get("/dadmin/tags")
    async def admin_tags(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        tags = await DawnBlogService.list_tags_with_counts()
        from plugins import dawn_collect_hooks
        tax_langs = (await dawn_collect_hooks("admin_tax_langs") or [[]])[0]
        tax_assets = await dawn_collect_hooks("admin_tax_assets")
        rows = []
        for t in tags:
            tax_cells = await dawn_collect_hooks("admin_tax_cell", kind="tag", item=t)
            tax_cells = [td for grp in tax_cells for td in (grp if isinstance(grp, list) else [grp])]
            rows.append(Tr(
            Td(str(t.get("id")), cls="px-3 py-2.5 text-slate-500 text-xs"),
            Td(t.get("name", ""), cls="px-3 py-2.5 text-slate-200 text-sm font-semibold"),
            Td(t.get("slug", ""), cls="px-3 py-2.5 text-slate-400 text-xs font-mono"),
            Td(str(t.get("post_count", 0)), cls="px-3 py-2.5 text-slate-500 text-xs"),
            *tax_cells,
            Td(
                Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('确认删除该标签？文章不会被删除。')"),
                     method="post", action=f"/dadmin/tag/delete/{t.get('id')}", style="display:inline"),
                cls="px-3 py-2.5 whitespace-nowrap"
            ),
            cls="border-b border-slate-800/60"
        ))

        return _dawn_admin_shell("tags", Div(
            _dawn_msg(msg) if msg else None,
            H1("标签管理", cls="text-2xl font-black text-white mb-6"),
            Form(
                Input(name="name", placeholder="标签名称", required=True, cls=DAWN_INPUT + " w-40"),
                Input(name="slug", placeholder="slug（留空自动生成）", cls=DAWN_INPUT + " w-48 ml-2"),
                Button("＋ 新增标签", type="submit", cls=DAWN_BTN + " ml-2"),
                method="post", action="/dadmin/tag/create",
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-wrap items-center gap-y-2"
            ),
            Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in (["ID", "名称", "Slug", "文章数"] + [f"译名·{l.split('-')[0].upper()}" for l in tax_langs] + ["操作"])])),
                Tbody(*rows) if rows else Tbody(Tr(Td("暂无标签。", colspan=str(4 + len(tax_langs) + 1), cls="px-3 py-10 text-center text-slate-500"))),
                cls="w-full rounded-xl overflow-hidden border border-slate-800"
            ),
            *tax_assets,
        ))

    @app.post("/dadmin/tag/create")
    async def admin_tag_create(session, name: str = "", slug: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if not (name or "").strip():
            return RedirectResponse("/dadmin/tags?msg=标签名称不能为空", status_code=303)
        await DawnBlogService.create_tag(name.strip(), slug.strip())
        return RedirectResponse("/dadmin/tags?msg=已创建", status_code=303)

    @app.post("/dadmin/tag/delete/{tag_id}")
    async def admin_tag_delete(session, tag_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.delete_tag(tag_id)
        return RedirectResponse("/dadmin/tags?msg=已删除", status_code=303)

    # ---- Newsletter 订阅管理 ----

