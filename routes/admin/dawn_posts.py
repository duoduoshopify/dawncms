# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/posts.py
# 文章列表 / 编辑器 / 版本 / 预览

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

def _dawn_post_form(post: dict | None, categories: list, action: str, revisions: list | None = None,
               all_tags: list | None = None, post_tag_ids: set | None = None,
               all_series: list | None = None):
    p = post or {}
    post_tag_ids = post_tag_ids or set()
    cat_names = [c.get("name", "") for c in categories]
    if p.get("category") and p["category"] not in cat_names:
        cat_names.append(p["category"])

    revision_block = None
    if revisions:
        revision_block = Div(
            H3("历史版本", cls="text-white font-bold text-sm mb-3"),
            *[Div(
                Span(r.get("created_at", ""), cls="text-slate-400 text-xs mr-3"),
                Span((r.get("title", "") or "")[:30], cls="text-slate-500 text-xs mr-3"),
                Form(
                    Button("恢复", type="submit", cls=DAWN_BTN_GHOST),
                    method="post", action=f"/dadmin/post/revision/restore/{r.get('id')}", style="display:inline"
                ),
                cls="flex items-center mb-2"
            ) for r in revisions],
            cls="mt-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
        )

    return Div(
        Form(
            Input(type="hidden", name="post_id", value=str(p.get("id", ""))),
            Div(
                Div(
                    Label("标题 *", cls=DAWN_LABEL),
                    Input(name="title", value=p.get("title", ""), required=True, cls=DAWN_INPUT, id="post-title"),
                    cls="mb-4"
                ),
                Div(
                    Label("Slug（留空自动生成）", cls=DAWN_LABEL),
                    Div(
                        Input(name="slug", value=p.get("slug", ""), cls=DAWN_INPUT, id="post-slug", placeholder="url-friendly-slug"),
                        Button("生成", type="button", cls=DAWN_BTN_GHOST + " ml-2 shrink-0",
                               hx_post="/dadmin/post/slug-preview", hx_target="#slug-result", hx_swap="innerHTML",
                               hx_include="#post-title"),
                        cls="flex items-center"
                    ),
                    Div(id="slug-result", cls="text-xs text-slate-500 mt-1"),
                    cls="mb-4"
                ),
                Div(
                    Div(
                        Label("分类", cls=DAWN_LABEL),
                        Select(*[Option(n, value=n, selected=(p.get("category") == n)) for n in cat_names],
                               name="category", cls=DAWN_INPUT),
                    ),
                    Div(
                        Label("作者", cls=DAWN_LABEL),
                        Input(name="author", value=p.get("author", DAWN_DEFAULT_AUTHOR), cls=DAWN_INPUT),
                    ),
                    Div(
                        Label("阅读时长", cls=DAWN_LABEL),
                        Input(name="read_time", value=p.get("read_time", "5分钟"), cls=DAWN_INPUT),
                    ),
                    cls="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4"
                ),
                Div(
                    Label("摘要（SEO description）", cls=DAWN_LABEL),
                    Textarea(p.get("description", ""), name="description", rows=2, cls=DAWN_INPUT),
                    cls="mb-4"
                ),
                Div(
                    Div(
                        Label("连载系列（跨分类，可选）", cls=DAWN_LABEL),
                        Select(
                            Option("— 不属于任何系列 —", value="0", selected=(not p.get("series_id"))),
                            *[Option(s.get("name", ""), value=str(s.get("id")), selected=(p.get("series_id") == s.get("id"))) for s in (all_series or [])],
                            name="series_id", cls=DAWN_INPUT),
                    ),
                    Div(
                        Label("系列内序号（越小越靠前，0=按发布时间）", cls=DAWN_LABEL),
                        Input(name="series_order", type="number", value=str(p.get("series_order") or 0), cls=DAWN_INPUT),
                    ),
                    cls="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4"
                ),
                Div(
                    Label("关键词（逗号分隔）", cls=DAWN_LABEL),
                    Input(name="keywords", value=p.get("keywords", ""), cls=DAWN_INPUT),
                    cls="mb-4"
                ),
                Div(
                    Label("标签", cls=DAWN_LABEL),
                    Div(
                        *[Label(
                            Input(type="checkbox", name="tag_ids", value=str(t.get("id")),
                                  checked=(t.get("id") in post_tag_ids), cls="mr-1.5 accent-indigo-500"),
                            t.get("name", ""),
                            cls="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-800/70 text-slate-300 text-xs mr-2 mb-2 cursor-pointer hover:bg-slate-800"
                        ) for t in (all_tags or [])] or [Span("暂无标签，先到「标签」页创建", cls="text-slate-600 text-xs")],
                        cls="flex flex-wrap"
                    ),
                    cls="mb-4"
                ),
                Div(
                    Div(
                        Label("定时发布（留空=立即；未来时间=到点自动上线）", cls=DAWN_LABEL),
                        Input(type="datetime-local", name="scheduled_at",
                              value=(p.get("scheduled_at") or "").replace(" ", "T")[:16], cls=DAWN_INPUT),
                    ),
                    cls="mb-4"
                ),
                Div(
                    Label("封面图 URL（可填 /uploads/... 或外链，外链会自动本地化）", cls=DAWN_LABEL),
                    Input(name="cover_image", value=p.get("cover_image", ""), cls=DAWN_INPUT),
                    cls="mb-4"
                ),
                Div(
                    Div(
                        Label("可见性", cls=DAWN_LABEL),
                        Select(
                            Option("公开", value="public", selected=(p.get("visibility", "public") == "public")),
                            Option("会员专享", value="member", selected=(p.get("visibility") == "member")),
                            Option("仅管理员", value="admin_only", selected=(p.get("visibility") == "admin_only")),
                            name="visibility", cls=DAWN_INPUT
                        ),
                    ),
                    Div(
                        Label("发布状态", cls=DAWN_LABEL),
                        Select(
                            Option("草稿", value="0", selected=(not p.get("is_published"))),
                            Option("发布", value="1", selected=bool(p.get("is_published"))),
                            name="is_published", cls=DAWN_INPUT
                        ),
                    ),
                    cls="grid grid-cols-2 gap-4 mb-4"
                ),
                Div(
                    Label("页面模板", cls=DAWN_LABEL),
                    Select(
                        *[Option({"default": "默认博文（hero 居中）", "docs": "文档（左侧栏目录）", "landing": "落地页（无导航动画块）", "changelog": "更新日志时间线", "roadmap": "路线图时间线", "showcase": "展示墙"}.get(v, v),
                                 value=v, selected=(p.get("template", "default") == v))
                          for v in ("default", "docs", "landing", "changelog", "roadmap", "showcase")],
                        name="template", cls=DAWN_INPUT
                    ),
                    P("主题按此字段选择正文版式；hash- 前缀标签（如 hash-docs）为内部结构标签，前台不展示。", cls="text-slate-500 text-xs mt-1"),
                    cls="mb-4"
                ),
                cls="p-6 rounded-2xl border border-slate-800 bg-slate-900/40"
            ),
            Div(
                Label("正文（所见即所得编辑，存储为 Markdown）", cls=DAWN_LABEL),
                Textarea(p.get("content", ""), name="content", id="post-content", style="display:none"),
                Div(id="dawn-vditor"),
                Link(rel="stylesheet", href="/static/vendor/vditor/dist/index.css"),
                Script(src="/static/vendor/vditor/dist/index.min.js"),
                Script(src="/static/vendor/dawn_editor.js?v=2"),
                DawnSafeHTML(f"<script>window.addEventListener('DOMContentLoaded',function(){{dawnInitEditor('{p.get('id') or 'new'}');}});</script>"),
                Div(
                    Button("前台排版预览", type="button", cls=DAWN_BTN_GHOST,
                           hx_post="/dadmin/post/preview", hx_target="#preview-box", hx_swap="innerHTML",
                           hx_include="#post-content"),
                    Span("输入 / 可唤起块菜单（CTA / 视频 / 折叠块…），图片可粘贴或拖拽直接上传；Ctrl+S 保存", cls="text-slate-600 text-xs ml-3"),
                    cls="mt-3 flex items-center"
                ),
                Div(id="preview-box", cls="mt-4 p-5 rounded-xl border border-slate-800 bg-slate-900/40 doc-content hidden",
                    style="display:block;min-height:40px"),
                cls="mt-6 p-6 rounded-2xl border border-slate-800 bg-slate-900/40"
            ),
            Div(
                Button("💾 保存", type="submit", cls=DAWN_BTN),
                A("返回列表", href="/dadmin", cls=DAWN_BTN_GHOST + " ml-3"),
                cls="mt-6"
            ),
            method="post", action=action
        ),
        revision_block
    )




def dawn_setup(app):
    @app.get("/dadmin/posts")
    async def admin_home(session, msg: str = "", q: str = "", status: str = "", category: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        posts = await DawnBlogService.get_admin_posts_filtered(q.strip(), status, category)
        categories = await DawnBlogService.get_categories()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = []
        for p in posts:
            pid = p.get("id")
            sched = (p.get("scheduled_at") or "")[:16]
            is_scheduled = bool(p.get("is_published")) and sched and sched > now_str
            if not p.get("is_published"):
                status_html = Span("📝 草稿", cls="text-amber-400")
            elif is_scheduled:
                status_html = Span(f"⏰ 定时 {sched}", cls="text-sky-400")
            else:
                status_html = Span("✅ 已发布", cls="text-emerald-400")
            from plugins import dawn_collect_hooks
            i18n_cells = await dawn_collect_hooks("admin_post_cell", post=p)
            i18n_cells = [c for grp in i18n_cells for c in (grp if isinstance(grp, list) else [grp])]
            rows.append(Tr(
                Td(Input(type="checkbox", name="ids", value=str(pid), cls="adm-row-check accent-indigo-500"), cls="px-3 py-2.5 w-8"),
                Td(str(pid), cls="px-3 py-2.5 text-slate-500 text-xs"),
                Td(
                    A(p.get("title", ""), href=f"/dadmin/post/edit/{pid}", cls="text-slate-200 hover:text-indigo-300 font-semibold text-sm"),
                    Div(p.get("slug", ""), cls="text-slate-600 text-xs mt-0.5"),
                ),
                Td(p.get("category", ""), cls="px-3 py-2.5 text-slate-400 text-xs"),
                Td(status_html, cls="px-3 py-2.5 text-xs"),
                Td({"member": "🔒 会员", "admin_only": "🙈 管理员"}.get(p.get("visibility", "public"), "🌐 公开"),
                   cls="px-3 py-2.5 text-xs text-slate-400"),
                Td(str(p.get("view_count", 0)), cls="px-3 py-2.5 text-slate-500 text-xs"),
                Td((p.get("updated_at") or "")[:16], cls="px-3 py-2.5 text-slate-500 text-xs"),
                *i18n_cells,
                Td(
                    Form(Button("发布" if not p.get("is_published") else "下架", type="submit", cls=DAWN_BTN_GHOST),
                         method="post", action=f"/dadmin/post/toggle/{pid}", style="display:inline"),
                    Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('确认删除该文章？')"),
                         method="post", action=f"/dadmin/post/delete/{pid}", style="display:inline;margin-left:6px"),
                    cls="px-3 py-2.5 whitespace-nowrap"
                ),
                cls="border-b border-slate-800/60 hover:bg-slate-900/40"
            ))

        def _opt(val, label, cur):
            return Option(label, value=val, selected=(val == cur))

        toolbar = Form(
            Input(type="text", name="q", value=q, placeholder="搜索标题 / Slug…", cls=DAWN_INPUT + " !w-64"),
            Select(
                _opt("", "全部状态", status),
                _opt("published", "已发布", status),
                _opt("draft", "草稿", status),
                _opt("scheduled", "定时中", status),
                name="status", cls=DAWN_INPUT + " !w-32"
            ),
            Select(
                _opt("", "全部分类", category),
                *[_opt(c.get("name", ""), c.get("name", ""), category) for c in categories],
                name="category", cls=DAWN_INPUT + " !w-36"
            ),
            Button("筛选", type="submit", cls=DAWN_BTN_GHOST + " !py-2.5"),
            A("重置", href="/dadmin/posts", cls="text-xs text-slate-500 hover:text-slate-300 self-center"),
            method="get", action="/dadmin/posts",
            cls="flex items-center gap-2.5 mb-4 flex-wrap"
        )

        batch_bar = Div(
            Input(type="checkbox", id="adm-check-all", cls="accent-indigo-500 mr-2",
                  onclick="document.querySelectorAll('.adm-row-check').forEach(c=>c.checked=this.checked)"),
            Span("全选", cls="text-xs text-slate-400 mr-4"),
            Button("批量发布", name="action", value="publish", type="submit", cls=DAWN_BTN_GHOST),
            Button("批量下架", name="action", value="unpublish", type="submit", cls=DAWN_BTN_GHOST + " ml-2"),
            Button("批量删除", name="action", value="delete", type="submit", cls=DAWN_BTN_DANGER + " ml-2",
                   onclick="return confirm('确认删除所选文章？此操作不可恢复。')"),
            cls="flex items-center mb-3 px-1"
        )

        table = Table(
            Thead(Tr(
                Th("", cls="px-3 py-2 w-8"),
                Th("ID", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("标题", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("分类", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("状态", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("可见性", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("阅读", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("更新", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("多语言", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                Th("操作", cls="px-3 py-2 text-left text-slate-500 text-xs"),
            )),
            Tbody(*rows) if rows else Tbody(Tr(Td("没有匹配的文章。", colspan="10", cls="px-3 py-10 text-center text-slate-500"))),
            cls="w-full rounded-xl overflow-hidden border border-slate-800"
        )

        from plugins import dawn_collect_hooks as _collect
        toolbar_hooks = await _collect("admin_post_toolbar")
        return _dawn_admin_shell("posts", Div(
            _dawn_msg(msg) if msg else None,
            Div(
                H1("文章管理", cls="text-2xl font-black text-white"),
                Div(*toolbar_hooks, A("＋ 写新文章", href="/dadmin/post/new", cls=DAWN_BTN),
                    cls="flex items-center"),
                cls="flex items-center justify-between mb-6"
            ),
            toolbar,
            Form(batch_bar, table, method="post", action="/dadmin/posts/batch", id="adm-batch-form"),
            Div(f"共 {len(posts)} 篇", cls="text-xs text-slate-600 mt-3"),
        ))

    @app.post("/dadmin/posts/batch")
    async def admin_posts_batch(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        action = form.get("action", "")
        ids = []
        for v in form.getlist("ids") if hasattr(form, "getlist") else form.get("ids", "").split(","):
            try:
                ids.append(int(v))
            except (TypeError, ValueError):
                continue
        if not ids:
            return RedirectResponse("/dadmin/posts?msg=未选择文章", status_code=303)
        done = 0
        for pid in ids:
            ok = False
            if action == "publish":
                ok = await DawnBlogService.publish_post(pid)
            elif action == "unpublish":
                ok = await DawnBlogService.unpublish_post(pid)
            elif action == "delete":
                ok = await DawnBlogService.delete_post(pid)
            if ok:
                done += 1
        label = {"publish": "发布", "unpublish": "下架", "delete": "删除"}.get(action, "处理")
        return RedirectResponse(f"/dadmin/posts?msg=已{label} {done} 篇", status_code=303)

    @app.get("/dadmin/post/new")
    async def admin_post_new(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        categories = await DawnBlogService.get_categories()
        all_tags = await DawnBlogService.list_tags()
        all_series = await DawnBlogService.get_series()
        return _dawn_admin_shell("new", Div(
            H1("写新文章", cls="text-2xl font-black text-white mb-6"),
            _dawn_post_form(None, categories, "/dadmin/post/save", all_tags=all_tags, all_series=all_series)
        ))

    @app.get("/dadmin/post/edit/{post_id}")
    async def admin_post_edit(session, post_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        post = await DawnBlogService.get_post_by_id(post_id)
        if not post:
            return RedirectResponse("/dadmin/posts?msg=" + "文章不存在")
        categories = await DawnBlogService.get_categories()
        revisions = await DawnBlogService.list_post_revisions(post_id, limit=10)
        all_tags = await DawnBlogService.list_tags()
        post_tag_ids = set(await DawnBlogService.get_post_tag_ids(post_id))
        all_series = await DawnBlogService.get_series()
        from plugins import dawn_collect_hooks
        panels = await dawn_collect_hooks("admin_post_panel", post_id=post_id, post=post)
        return _dawn_admin_shell("posts", Div(
            H1(f"编辑文章 #{post_id}", cls="text-2xl font-black text-white mb-6"),
            _dawn_post_form(post, categories, "/dadmin/post/save", revisions, all_tags, post_tag_ids, all_series),
            *panels
        ))

    @app.post("/dadmin/post/save")
    async def admin_post_save(request, session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        g = lambda k, d="": (form.get(k) or d).strip() if isinstance(form.get(k) or d, str) else form.get(k, d)
        scheduled_raw = g("scheduled_at")
        scheduled_at = scheduled_raw.replace("T", " ")[:16]
        data = {
            "title": g("title"),
            "description": g("description"),
            "keywords": g("keywords"),
            "category": g("category") or "未分类",
            "author": g("author") or DAWN_DEFAULT_AUTHOR,
            "read_time": g("read_time") or "5分钟",
            "cover_image": g("cover_image"),
            "visibility": g("visibility") or "public",
            "template": g("template") or "default",
            "is_published": 1 if g("is_published") == "1" else 0,
            "scheduled_at": scheduled_at,
            "series_id": int(g("series_id", "0") or 0),
            "series_order": int(g("series_order", "0") or 0),
            "content": form.get("content") or "",
        }
        slug = g("slug")
        if slug:
            data["slug"] = slug
        try:
            tag_ids = [int(t) for t in form.getlist("tag_ids")]
        except Exception:
            tag_ids = []

        post_id = g("post_id")
        pid = int(post_id) if post_id.isdigit() else 0
        if pid > 0:
            old = await DawnBlogService.get_post_by_id(pid)
            await DawnBlogService.create_post_revision(pid, old or {}, edited_by="admin")
            ok = await DawnBlogService.update_post(pid, data)
            if old and data.get("slug") and old.get("slug") != data["slug"]:
                await DawnBlogService.register_slug_redirect(pid, old.get("slug", ""), data["slug"])
            await DawnBlogService.set_post_tags(pid, tag_ids)
            updated = await DawnBlogService.get_post_by_id(pid)
            if updated:
                await DawnBlogService.sync_post_media_usages(pid, updated.get("content", ""), updated.get("cover_image", ""))
            return RedirectResponse(f"/dadmin/posts?msg={'已保存' if ok else '保存失败：slug 冲突'}", status_code=303)

        pid = await DawnBlogService.create_post(data)
        await DawnBlogService.set_post_tags(pid, tag_ids)
        new_post = await DawnBlogService.get_post_by_id(pid)
        if new_post:
            await DawnBlogService.sync_post_media_usages(pid, new_post.get("content", ""), new_post.get("cover_image", ""))
        return RedirectResponse("/dadmin/posts?msg=已创建", status_code=303)

    @app.post("/dadmin/post/toggle/{post_id}")
    async def admin_post_toggle(session, post_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        post = await DawnBlogService.get_post_by_id(post_id)
        if post:
            if post.get("is_published"):
                await DawnBlogService.unpublish_post(post_id)
            else:
                await DawnBlogService.publish_post(post_id)
        return RedirectResponse("/dadmin/posts", status_code=303)

    @app.post("/dadmin/post/delete/{post_id}")
    async def admin_post_delete(session, post_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogService.delete_post(post_id)
        return RedirectResponse("/dadmin/posts?msg=已删除", status_code=303)

    @app.post("/dadmin/post/revision/restore/{revision_id}")
    async def admin_revision_restore(session, revision_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        pid = await DawnBlogService.restore_post_revision(revision_id)
        return RedirectResponse(f"/dadmin/post/edit/{pid}" if pid else "/dadmin", status_code=303)

    @app.post("/dadmin/post/preview")
    async def admin_post_preview(session, content: str = ""):
        if not _dawn_require_admin(session):
            return Div("未登录", cls="text-red-400 text-sm")
        payload = DawnBlogService.preview_payload(content)
        stats = payload.get("stats", {})
        return Div(
            Div(f"字数 {stats.get('word_count', 0)} · 标题 {stats.get('heading_count', 0)} · 图片 {stats.get('image_count', 0)}",
                cls="text-slate-500 text-xs mb-3"),
            DawnSafeHTML(payload.get("html", "")),
        )

    @app.post("/dadmin/post/slug-preview")
    async def admin_slug_preview(session, title: str = ""):
        if not _dawn_require_admin(session):
            return Div("未登录", cls="text-red-400 text-sm")
        result = await DawnBlogService.generate_slug_candidates(title)
        cands = result.get("candidates", [])
        if not cands:
            return Span("无法生成 slug", cls="text-amber-400")
        return Div(
            *[Div(
                A(c.get("slug", ""), href="#", cls="text-indigo-300 hover:text-indigo-200 font-mono",
                  onclick=f"document.getElementById('post-slug').value='{c.get('slug','')}';return false;"),
                Span("（已自动去重）" if c.get("adjusted") else "", cls="text-slate-600 ml-2"),
                cls="py-0.5"
            ) for c in cands],
            cls="text-xs"
        )

