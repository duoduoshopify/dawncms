# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/site.py
# 导航 / 外观主题

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from fasthtml.common import *

from dawn_config import DAWN_ADMIN_PASSWORD, dawn_site_name, dawn_site_tagline, dawn_set_site_info, DAWN_DEFAULT_AUTHOR, DAWN_SITE_BASE_URL, DAWN_EMAIL_ENABLED
from ui.dawn_layout import DawnSafeHTML
from services.dawn_blog_service import DawnBlogService
from services.dawn_image_service import DawnBlogImageService
from services.dawn_member_service import DawnMemberService
from services.dawn_email_service import DawnEmailService
from blog.dawn_crud import DawnBlogCRUD

from .dawn_shell import _dawn_admin_shell, _dawn_require_admin, _dawn_msg, DAWN_INPUT, DAWN_LABEL, DAWN_BTN, DAWN_BTN_DANGER, DAWN_BTN_GHOST



def dawn_setup(app):
    @app.get("/dadmin/settings")
    async def admin_settings(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        return _dawn_admin_shell("settings", Div(
            _dawn_msg(msg) if msg else None,
            H1("站点设置", cls="text-2xl font-black text-white mb-2"),
            P("站点名称与标语用于前台页头/页脚、浏览器标题后缀、SEO meta、RSS 与邮件落款。保存后约 30 秒内全站生效。",
              cls="text-slate-500 text-sm mb-6"),
            Form(
                Div(
                    Label("站点名称", cls=DAWN_LABEL),
                    Input(name="site_name", value=dawn_site_name(), required=True, maxlength="60", cls=DAWN_INPUT),
                    cls="mb-4"),
                Div(
                    Label("站点标语", cls=DAWN_LABEL),
                    Input(name="site_tagline", value=dawn_site_tagline(), maxlength="120", cls=DAWN_INPUT),
                    P("留空则恢复默认标语", cls="text-slate-600 text-xs mt-1.5"),
                    cls="mb-6"),
                Button("保存", type="submit", cls=DAWN_BTN),
                method="post", action="/dadmin/settings",
                cls="max-w-lg p-5 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
        ))

    @app.post("/dadmin/settings")
    async def admin_settings_save(session, site_name: str = "", site_tagline: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if not site_name.strip():
            return RedirectResponse("/dadmin/settings?msg=站点名称不能为空", status_code=303)
        dawn_set_site_info(site_name, site_tagline)
        return RedirectResponse("/dadmin/settings?msg=✅ 已保存", status_code=303)

    @app.get("/dadmin/nav")
    async def admin_nav(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        links = await DawnBlogCRUD.list_nav_links()

        def _row(l):
            loc_badge = ("🔝 头部", "text-indigo-300 bg-indigo-500/15") if l["location"] == "header" else ("🔻 底部", "text-emerald-300 bg-emerald-500/15")
            return Tr(
                Td(Form(
                    Input(type="hidden", name="link_id", value=str(l["id"])),
                    Input(name="label", value=l["label"], cls=DAWN_INPUT + " !py-1.5"),
                    method="post", action="/dadmin/nav/update", id=f"nav-form-{l['id']}"),
                    cls="px-3 py-2"),
                Td(Input(name="url", value=l["url"], form=f"nav-form-{l['id']}", cls=DAWN_INPUT + " !py-1.5"), cls="px-3 py-2"),
                Td(Input(type="number", name="sort_order", value=str(l["sort_order"]), form=f"nav-form-{l['id']}",
                         cls=DAWN_INPUT + " !py-1.5 !w-20"), cls="px-3 py-2"),
                Td(Span(loc_badge[0], cls=f"px-2 py-1 rounded text-xs font-bold {loc_badge[1]}"), cls="px-3 py-2"),
                Td(
                    Select(
                        Option("显示", value="1", selected=bool(l["is_active"])),
                        Option("隐藏", value="0", selected=not bool(l["is_active"])),
                        name="is_active", form=f"nav-form-{l['id']}", cls=DAWN_INPUT + " !py-1.5 !w-24"),
                    cls="px-3 py-2"),
                Td(Div(
                    Button("保存", type="submit", form=f"nav-form-{l['id']}", cls=DAWN_BTN_GHOST),
                    Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER + " ml-2",
                                onclick="return confirm('删除该导航链接？')"),
                         method="post", action=f"/dadmin/nav/{l['id']}/delete", cls="inline"),
                    cls="flex items-center"), cls="px-3 py-2"),
                cls="border-b border-slate-800/60"
            )

        header_rows = [_row(l) for l in links if l["location"] == "header"]
        footer_rows = [_row(l) for l in links if l["location"] == "footer"]

        def _table(rows, empty_text):
            return Table(
                Thead(Tr(*[Th(t, cls="px-3 py-2 text-left text-slate-500 text-xs") for t in ["名称", "链接地址", "排序", "位置", "状态", "操作"]])),
                Tbody(*rows) if rows else Tbody(Tr(Td(empty_text, colspan="6", cls="px-3 py-8 text-center text-slate-500"))),
                cls="w-full rounded-xl overflow-hidden border border-slate-800 mb-8")

        return _dawn_admin_shell("nav", Div(
            _dawn_msg(msg) if msg else None,
            H1("导航管理", cls="text-2xl font-black text-white mb-2"),
            P("头部导航显示在页面顶部，底部导航显示在页脚。排序数字越小越靠前。链接可填站内路径（如 /about）或完整外链。",
              cls="text-slate-500 text-sm mb-6"),
            Div(
                H2("➕ 新增链接", cls="text-white font-bold text-sm mb-3"),
                Form(
                    Input(name="label", placeholder="名称（如：友情链接）", required=True, cls=DAWN_INPUT + " flex-1 min-w-0"),
                    Input(name="url", placeholder="链接（如 /about 或 https://...）", required=True, cls=DAWN_INPUT + " flex-[2] min-w-0 ml-2"),
                    Select(Option("头部导航", value="header"), Option("底部导航", value="footer"),
                           name="location", cls=DAWN_INPUT + " !w-32 ml-2"),
                    Input(type="number", name="sort_order", value="10", cls=DAWN_INPUT + " !w-20 ml-2"),
                    Button("添加", type="submit", cls=DAWN_BTN + " ml-2 shrink-0"),
                    method="post", action="/dadmin/nav/create",
                    cls="flex items-center flex-wrap gap-y-2"
                ),
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            H2("🔝 头部导航", cls="text-white font-bold mb-3"),
            _table(header_rows, "暂无头部导航链接"),
            H2("🔻 底部导航", cls="text-white font-bold mb-3"),
            _table(footer_rows, "暂无底部导航链接"),
        ))

    @app.post("/dadmin/nav/create")
    async def admin_nav_create(session, label: str = "", url: str = "", location: str = "header", sort_order: int = 0):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if label.strip() and url.strip():
            await DawnBlogCRUD.create_nav_link(location, label, url, sort_order)
        return RedirectResponse("/dadmin/nav?msg=已添加", status_code=303)

    @app.post("/dadmin/nav/update")
    async def admin_nav_update(session, link_id: int = 0, label: str = "", url: str = "",
                               sort_order: int = 0, is_active: str = "1"):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        if label.strip() and url.strip():
            await DawnBlogCRUD.update_nav_link(link_id, label, url, sort_order, 1 if is_active == "1" else 0)
        return RedirectResponse("/dadmin/nav?msg=已保存", status_code=303)

    @app.post("/dadmin/nav/{link_id}/delete")
    async def admin_nav_delete(session, link_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        await DawnBlogCRUD.delete_nav_link(link_id)
        return RedirectResponse("/dadmin/nav?msg=已删除", status_code=303)

    # ---- 外观主题管理 ----

    @app.get("/dadmin/appearance")
    async def admin_appearance(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_all_themes, dawn_get_active_theme_key
        themes_map = dawn_all_themes()
        active = dawn_get_active_theme_key()

        cards = []
        for key, t in themes_map.items():
            is_active = key == active
            sw = t["swatch"]
            is_custom = bool(t.get("custom"))
            preview = Div(
                Div(
                    Div(cls="h-16 rounded-t-xl", style=f"background:{sw[0]};border-bottom:1px solid {sw[1]}22"),
                    Div(
                        Span("", cls="inline-block w-16 h-2 rounded-full", style=f"background:{sw[1]}"),
                        Span("", cls="inline-block w-8 h-2 rounded-full ml-1", style=f"background:{sw[2]}"),
                        cls="px-4 py-3"
                    ),
                    cls="rounded-xl overflow-hidden border border-slate-700"
                )
            )
            delete_btn = None
            if is_custom:
                delete_btn = Button("删除该主题", type="submit", form=f"del-theme-{key}",
                                    cls="block text-xs text-red-400 hover:text-red-300 mt-1 ml-1",
                                    onclick="return confirm('删除该自定义主题？')")
            edit_btn = None
            if t.get("package"):
                edit_btn = A("✏️ 编辑 / 预览", href=f"/dadmin/theme/{key}/edit",
                             cls="inline-block text-xs text-indigo-400 hover:text-indigo-300 mt-1 ml-1")
            cards.append(
                Div(
                    Label(
                        Input(type="radio", name="theme", value=key, checked=is_active, cls="hidden peer"),
                        Div(
                            preview,
                            Div(
                                Span(t["label"], cls="text-white font-bold text-sm"),
                                Span("当前使用" if is_active else "", cls="text-xs text-indigo-400 ml-2 font-semibold"),
                                Span("自定义" if is_custom else "", cls="text-xs text-emerald-400 ml-2 font-semibold"),
                                cls="mt-3"
                            ),
                            P(t["desc"], cls="text-slate-500 text-xs mt-1"),
                            cls="p-4 rounded-xl border-2 cursor-pointer transition-all " +
                                ("border-indigo-500 bg-slate-900/70" if is_active else "border-slate-800 bg-slate-900/40 hover:border-slate-600")
                        ),
                        cls="block", onclick="this.querySelector('input[type=radio]').checked=true; this.closest('form').submit();"
                    ),
                    Div(edit_btn, delete_btn, cls="flex items-center gap-3"),
                    cls="relative"
                )
            )

        from dawn_themes import DAWN_LAYOUTS, dawn_get_layout_mode, dawn_get_package, dawn_theme_settings, _dawn_get_setting
        custom_css_val = _dawn_get_setting("custom_css", "")
        custom_head_val = _dawn_get_setting("custom_head_code", "")
        custom_body_val = _dawn_get_setting("custom_body_code", "")
        cur_layout = dawn_get_layout_mode()
        layout_cards = [
            Div(
                Label(
                    Input(type="radio", name="layout", value=k, checked=(k == cur_layout), cls="hidden peer"),
                    Div(
                        Div(
                            Div(cls="rounded-md border border-slate-600 bg-slate-800 h-3 " + ("w-3/4 mx-auto" if k == "boxed" else "w-full")),
                            Div(cls="rounded-md border border-slate-600 bg-slate-800 h-8 mt-2 " + ("w-3/5 mx-auto" if k == "boxed" else "w-11/12 mx-auto" if k == "full" else "w-full")),
                            Div(cls="rounded-md border border-slate-600 bg-slate-800 h-3 mt-2 " + ("w-2/3 mx-auto" if k == "boxed" else "w-10/12 mx-auto" if k == "full" else "w-full")),
                            cls="py-4"
                        ),
                        Div(
                            Span(lay["label"], cls="text-white font-bold text-sm"),
                            Span("当前使用" if k == cur_layout else "", cls="text-xs text-indigo-400 ml-2 font-semibold"),
                            cls="mt-1"
                        ),
                        P(lay["desc"], cls="text-slate-500 text-xs mt-1"),
                        cls="p-4 rounded-xl border-2 cursor-pointer transition-all " +
                            ("border-indigo-500 bg-slate-900/70" if k == cur_layout else "border-slate-800 bg-slate-900/40 hover:border-slate-600")
                    ),
                    cls="block", onclick="this.querySelector('input[type=radio]').checked=true; this.closest('form').submit();"
                )
            )
            for k, lay in DAWN_LAYOUTS.items()
        ]

        settings_block = None
        pkg = dawn_get_package(active)
        schema = pkg.settings_schema() if pkg else {}
        if schema:
            cur_settings = dawn_theme_settings(active)
            fields = []
            for name, spec in schema.items():
                val = cur_settings.get(name, "")
                t = spec.get("type")
                if t == "select":
                    field = Select(*[Option(o, value=o, selected=(o == val)) for o in (spec.get("options") or [])],
                                   name=name, cls=DAWN_INPUT)
                elif t == "color":
                    field = Div(
                        Input(type="color", name=name, value=val or "#000000",
                              cls="w-16 h-10 rounded-lg cursor-pointer bg-slate-800 border border-slate-700"),
                        Span(val, cls="text-slate-500 text-xs ml-3 self-center"),
                        cls="flex"
                    )
                elif t == "textarea":
                    field = Textarea(val, name=name, rows=4, cls=DAWN_INPUT,
                                     placeholder=spec.get("placeholder", ""))
                else:
                    field = Input(type="text", name=name, value=val, cls=DAWN_INPUT,
                                  placeholder=spec.get("placeholder", ""))
                default_val = str(spec.get("default", ""))
                fields.append(Div(
                    Div(
                        Label(spec.get("label", name), cls=DAWN_LABEL + " mb-0"),
                        Span("已修改", cls="text-amber-400/90 text-xs font-semibold") if val != default_val
                        else Span("默认", cls="text-slate-600 text-xs"),
                        cls="flex items-baseline justify-between mb-1"
                    ),
                    field,
                    P("⚠ 已废弃：页面宽度改由上方「页面版式」统一控制（「无际 · 通栏」等同于原 Full width），本项保留仅为兼容旧主题。", cls="text-amber-400/90 text-xs mt-1") if name == "page_width" else None,
                    P(spec["description"], cls="text-slate-500 text-xs mt-1") if spec.get("description") else None,
                    P(f"默认值：{default_val or '（空）'}", cls="text-slate-600 text-xs mt-1") if val != default_val else None,
                    cls="mb-3"
                ))
            settings_block = Div(
                Div(
                    H2("⚙️ 主题设置", cls="text-white font-bold text-sm"),
                    Form(
                        Button("全部恢复默认", type="submit",
                               cls="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs font-semibold hover:border-red-500 hover:text-red-400"),
                        method="post", action="/dadmin/appearance/settings/reset",
                        **{"onsubmit": "return confirm('将当前主题全部设置恢复为默认值？此操作立即生效。')"}
                    ),
                    cls="flex items-center justify-between mb-3"
                ),
                P(f"当前主题「{pkg.name}」暴露的自定义选项（保存后立即生效）。标注「已修改」的为自定义值，未标注的跟随 theme.json 默认值。", cls="text-slate-500 text-xs mb-3"),
                Form(*fields, Button("保存主题设置", type="submit", cls=DAWN_BTN),
                     method="post", action="/dadmin/appearance/settings"),
                cls="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            )

        return _dawn_admin_shell("appearance", Div(
            _dawn_msg(msg) if msg else None,
            H1("外观主题", cls="text-2xl font-black text-white mb-2"),
            P("点击主题卡片即可切换，前台立即生效（无需重启）。主题只影响前台，后台保持暗色。", cls="text-slate-500 text-sm mb-6"),
            Form(
                Div(*cards, cls="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6"),
                Button("保存主题", type="submit", cls=DAWN_BTN),
                method="post", action="/dadmin/appearance"
            ),
            *[Form(method="post", action=f"/dadmin/appearance/{k}/delete", id=f"del-theme-{k}", cls="hidden")
              for k, t in themes_map.items() if t.get("custom")],
            Div(
                H2("📐 页面版式", cls="text-white font-bold text-sm mb-3"),
                P("点击即切换：书函 1200px 居中留白；铺陈 1560px 宽幕（侧栏加宽、正文字号微调）；无际取消宽度限制、内容铺满视口。", cls="text-slate-500 text-xs mb-1"),
                P("⚠ 宽幕仅在浏览器视口 ≥1400px 时生效：1366×768 等小屏设备切换后前台不会有变化，属正常设计，并非保存失败。", cls="text-amber-400/90 text-xs mb-3"),
                Form(
                    Div(*layout_cards, cls="grid grid-cols-1 md:grid-cols-2 gap-4"),
                    method="post", action="/dadmin/appearance/layout"
                ),
                cls="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            settings_block,
            Div(
                H2("⬆️ 上传自定义主题", cls="text-white font-bold text-sm mb-3"),
                P("上传完整主题包 zip（含 theme.json + vars.json + templates/*.html），可彻底改布局结构。格式见前台 /docs 文档中心。", cls="text-slate-500 text-xs mb-3"),
                Form(
                    Input(type="file", name="theme_zip", accept=".zip", required=True,
                          cls="text-slate-400 text-sm file:mr-3 file:px-4 file:py-2 file:rounded-lg file:border-0 file:bg-emerald-600 file:text-white file:text-sm file:font-semibold hover:file:bg-emerald-500"),
                    Button("上传主题包 zip", type="submit", cls=DAWN_BTN),
                    method="post", action="/dadmin/appearance/upload_zip", enctype="multipart/form-data",
                    cls="flex items-center gap-3"
                ),
                cls="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            Div(
                H2("🧩 自定义代码", cls="text-white font-bold text-sm mb-3"),
                P("自定义 CSS 注入全站 </head> 之前（在全部主题样式之后，优先级最高）；head / body 代码原样注入对应位置，可用于统计、验证 meta、第三方挂件。仅管理员可编辑，请确保代码可信。", cls="text-slate-500 text-xs mb-3"),
                Form(
                    Label("自定义 CSS", cls=DAWN_LABEL),
                    Textarea(custom_css_val, name="custom_css", rows=5, cls=DAWN_INPUT,
                             placeholder="例如：:root{--accent:#0f6bff}"),
                    Label("head 注入代码（</head> 前）", cls=DAWN_LABEL + " mt-3"),
                    Textarea(custom_head_val, name="custom_head_code", rows=3, cls=DAWN_INPUT,
                             placeholder='<meta name="..." content="..."> 或 <script>...</script>'),
                    Label("body 注入代码（</body> 前）", cls=DAWN_LABEL + " mt-3"),
                    Textarea(custom_body_val, name="custom_body_code", rows=3, cls=DAWN_INPUT,
                             placeholder="<script>...</script>"),
                    Button("保存自定义代码", type="submit", cls=DAWN_BTN + " mt-3"),
                    method="post", action="/dadmin/appearance/custom_code"
                ),
                cls="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            Div(
                H2("💾 配置备份", cls="text-white font-bold text-sm mb-3"),
                P("导出全站配置（主题、版式、主题设置、首页区块、自定义代码等 site_settings 全部内容）为 JSON；导入按 key 覆盖写回，即「一键恢复」。", cls="text-slate-500 text-xs mb-3"),
                Div(
                    A("⬇️ 导出配置 JSON", href="/dadmin/settings/export", cls=DAWN_BTN),
                    Form(
                        Input(type="file", name="settings_json", accept=".json", required=True,
                              cls="text-slate-400 text-sm file:mr-3 file:px-4 file:py-2 file:rounded-lg file:border-0 file:bg-emerald-600 file:text-white file:text-sm file:font-semibold hover:file:bg-emerald-500"),
                        Button("导入配置", type="submit", cls=DAWN_BTN),
                        method="post", action="/dadmin/settings/import", enctype="multipart/form-data",
                        cls="flex items-center gap-3"
                    ),
                    cls="flex items-center gap-4 flex-wrap"
                ),
                cls="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            Div(
                H2("自定义主题开发", cls="text-white font-bold text-sm mb-2"),
                P("主题 = 一组 CSS 变量（纸底/墨色/强调色/边框等 24 个 token）。完整字段说明见前台 /docs 文档中心；也可用环境变量 SITE_THEME 指定默认主题。", cls="text-slate-500 text-xs"),
                cls="p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
        ))

    @app.post("/dadmin/appearance")
    async def admin_appearance_save(session, theme: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_set_active_theme
        if dawn_set_active_theme(theme):
            return RedirectResponse("/dadmin/appearance?msg=主题已切换，前台立即生效", status_code=303)
        return RedirectResponse("/dadmin/appearance?msg=未知主题", status_code=303)

    @app.post("/dadmin/appearance/settings")
    async def admin_appearance_settings_save(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_get_active_theme_key, dawn_set_theme_settings
        form = await request.form()
        key = dawn_get_active_theme_key()
        saved, skipped = dawn_set_theme_settings(key, dict(form))
        msg = f"主题设置已保存（{saved} 项）"
        if skipped:
            msg += f"，跳过 {len(skipped)} 项（格式不符）"
        return RedirectResponse(f"/dadmin/appearance?msg={msg}", status_code=303)

    @app.post("/dadmin/appearance/layout")
    async def admin_appearance_layout(session, layout: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_set_layout_mode
        if dawn_set_layout_mode(layout):
            return RedirectResponse("/dadmin/appearance?msg=版式已切换，前台立即生效", status_code=303)
        return RedirectResponse("/dadmin/appearance?msg=未知版式", status_code=303)

    @app.post("/dadmin/appearance/settings/reset")
    async def admin_appearance_settings_reset(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_reset_theme_settings
        n = dawn_reset_theme_settings()
        return RedirectResponse(f"/dadmin/appearance?msg=已恢复默认（清除 {n} 项自定义设置）", status_code=303)

    @app.post("/dadmin/appearance/custom_code")
    async def admin_appearance_custom_code(session, custom_css: str = "", custom_head_code: str = "", custom_body_code: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import _dawn_set_setting
        _dawn_set_setting("custom_css", custom_css)
        _dawn_set_setting("custom_head_code", custom_head_code)
        _dawn_set_setting("custom_body_code", custom_body_code)
        return RedirectResponse("/dadmin/appearance?msg=自定义代码已保存，前台立即生效", status_code=303)

    @app.get("/dadmin/settings/export")
    async def admin_settings_export(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        import sqlite3
        from dawn_themes import DAWN_DB_PATH
        db = sqlite3.connect(DAWN_DB_PATH, timeout=5)
        rows = db.execute("SELECT key, value FROM site_settings ORDER BY key").fetchall()
        db.close()
        payload = json.dumps({
            "dawncms_settings": 1,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "settings": dict(rows),
        }, ensure_ascii=False, indent=2)
        return Response(payload.encode("utf-8"), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=dawncms-settings.json"})

    @app.post("/dadmin/settings/import")
    async def admin_settings_import(request, session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import _dawn_set_setting
        form = await request.form()
        upload = form.get("settings_json")
        if not upload or not getattr(upload, "filename", ""):
            return RedirectResponse("/dadmin/appearance?msg=请选择 JSON 文件", status_code=303)
        try:
            data = json.loads((await upload.read()).decode("utf-8"))
            settings = data.get("settings") if isinstance(data, dict) else None
            if not isinstance(settings, dict) or \
                    not all(isinstance(k, str) and isinstance(v, str) for k, v in settings.items()):
                raise ValueError("bad settings payload")
        except Exception:
            return RedirectResponse("/dadmin/appearance?msg=文件格式不正确，请使用本系统导出的配置 JSON", status_code=303)
        for k, v in settings.items():
            _dawn_set_setting(k, v)
        return RedirectResponse(f"/dadmin/appearance?msg=已导入 {len(settings)} 项配置并生效", status_code=303)

    @app.post("/dadmin/appearance/upload_zip")
    async def admin_appearance_upload_zip(request, session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_save_uploaded_theme
        form = await request.form()
        upload = form.get("theme_zip")
        if not upload or not getattr(upload, "filename", ""):
            return RedirectResponse("/dadmin/appearance?msg=请选择 zip 文件", status_code=303)
        raw = await upload.read()
        ok, msg = dawn_save_uploaded_theme(raw)
        if ok:
            msg += "，点击卡片即可启用"
        return RedirectResponse(f"/dadmin/appearance?msg={msg}", status_code=303)

    @app.post("/dadmin/appearance/{key}/delete")
    async def admin_appearance_delete(session, key: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_delete_theme_package, dawn_get_package
        pkg = dawn_get_package(key)
        if pkg and pkg.custom:
            dawn_delete_theme_package(key)
        return RedirectResponse("/dadmin/appearance?msg=已删除（若该主题在使用中，已回退默认主题）", status_code=303)

    # ---- 主题编辑器（Shopify 式：可视设置 + 区块 + 实时预览） ----

    _DAWN_CSS_SETTINGS = {"accent_color", "dark_theme_accent_color", "body_font", "headings_font"}

    def _ed_input(name, spec, value, attr="data-set"):
        """按 schema 类型渲染设置控件。attr 为 data 属性名（设置用 data-set，区块设置用 data-skey）"""
        t = spec.get("type")
        common = {attr: name}
        if t == "color":
            v = value if re.match(r"^#[0-9a-fA-F]{6}$", value or "") else "#000000"
            return Div(
                Input(type="color", value=v, cls="w-10 h-9 rounded cursor-pointer border border-slate-700 bg-transparent", **common),
                Input(type="text", value=value, placeholder="#000000", cls=DAWN_INPUT + " !w-28 ml-2 font-mono !text-xs", **common),
                cls="flex items-center")
        if t == "select":
            return Select(*[Option(o, value=o, selected=(o == value)) for o in (spec.get("options") or [])],
                          cls=DAWN_INPUT + " !py-2", **common)
        if t == "range":
            return Div(
                Input(type="range", min=str(spec.get("min", 0)), max=str(spec.get("max", 100)),
                      step=str(spec.get("step", 1)), value=value or str(spec.get("default", "")),
                      cls="flex-1 accent-indigo-500", **common),
                Span(value or str(spec.get("default", "")), cls="text-slate-400 text-xs ml-3 w-10 text-right",
                     **{"data-range-out": name}),
                cls="flex items-center")
        if t == "toggle":
            return Label(
                Input(type="checkbox", checked=(value == "1"), cls="peer hidden", **common),
                Div(cls="w-9 h-5 rounded-full bg-slate-700 peer-checked:bg-indigo-500 relative transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-4 after:h-4 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-4 cursor-pointer"),
                cls="inline-block")
        if t == "textarea":
            return Textarea(value, rows=4, placeholder=spec.get("placeholder", ""), cls=DAWN_INPUT, **common)
        return Input(type="text", value=value, placeholder=spec.get("placeholder", ""), cls=DAWN_INPUT, **common)

    def _ed_field(label, desc, control):
        return Div(
            Label(label, cls=DAWN_LABEL),
            control,
            P(desc, cls="text-slate-600 text-xs mt-1.5 leading-relaxed") if desc else None,
            cls="py-3 border-b border-slate-800/60 last:border-b-0")

    @app.get("/dadmin/theme/{key}/edit")
    async def admin_theme_edit(session, key: str, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_get_package, dawn_preview_signature, dawn_theme_editor_state
        pkg = dawn_get_package(key)
        if not pkg or not (pkg.path / "theme.json").exists():
            return RedirectResponse("/dadmin/appearance?msg=该主题不是完整主题包，无法编辑", status_code=303)
        state = dawn_theme_editor_state(key)
        schema = state["schema"]
        settings = state["settings"]
        sig = dawn_preview_signature(key)
        preview_url = f"/?__theme_preview={key}&__sig={sig}"

        # 设置分组（按 theme.json 声明顺序归组）
        groups, group_order = {}, []
        for name, spec in schema.items():
            g = spec.get("group") or "其他"
            if g not in groups:
                groups[g] = []
                group_order.append(g)
            groups[g].append((name, spec))
        settings_html = []
        for g in group_order:
            rows = []
            for name, spec in groups[g]:
                css_attr = {"data-css": "1"} if name in _DAWN_CSS_SETTINGS else {}
                rows.append(_ed_field(spec.get("label", name), spec.get("description", ""),
                                      Div(_ed_input(name, spec, settings.get(name, "")), **css_attr)))
            settings_html.append(
                Div(
                    H3(g, cls="text-slate-300 text-xs font-bold uppercase tracking-widest mb-1"),
                    *rows,
                    cls="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 mb-4"))

        # 首页区块面板
        sections_html = None
        if state["sections"]:
            sec_rows = []
            for i, sec in enumerate(state["sections"]):
                sec_settings = []
                for sname, sspec in (sec.get("schema") or {}).items():
                    sec_settings.append(_ed_field(
                        sspec.get("label", sname), sspec.get("description", ""),
                        _ed_input(sname, sspec, sec["settings"].get(sname, ""), attr="data-sec-set")))
                sec_rows.append(
                    Div(
                        Div(
                            Span("▦", cls="text-slate-600 mr-2 cursor-grab"),
                            Span(sec["label"], cls="text-slate-200 text-sm font-semibold flex-1"),
                            Button("↑", type="button", onclick=f"dawnSecMove({i},-1)",
                                   cls="text-slate-500 hover:text-slate-200 px-1.5 text-xs" + (" invisible" if i == 0 else "")),
                            Button("↓", type="button", onclick=f"dawnSecMove({i},1)",
                                   cls="text-slate-500 hover:text-slate-200 px-1.5 text-xs" + (" invisible" if i == len(state["sections"]) - 1 else "")),
                            Label(
                                Input(type="checkbox", checked=sec["enabled"], cls="peer hidden",
                                      onchange=f"dawnSecToggle({i}, this.checked)", **{"data-sec-toggle": str(i)}),
                                Div(cls="w-9 h-5 rounded-full bg-slate-700 peer-checked:bg-indigo-500 relative transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-4 after:h-4 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-4 cursor-pointer"),
                                cls="inline-block ml-1"),
                            cls="flex items-center"),
                        Div(*sec_settings, cls="pl-6 mt-1") if sec_settings else None,
                        cls="py-2.5 border-b border-slate-800/60 last:border-b-0",
                        **{"data-sec-row": sec["type"]}))
            sections_html = Div(
                H3("首页区块", cls="text-slate-300 text-xs font-bold uppercase tracking-widest mb-1"),
                *sec_rows,
                cls="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 mb-4")

        editor_js = """
(function(){
  var KEY = %s;
  var state = %s;
  var frame = document.getElementById('theme-preview-frame');
  var badge = document.getElementById('draft-badge');
  var timer = null;
  function markDirty(){ if(badge) badge.style.display=''; }
  function schedule(reload){
    markDirty();
    clearTimeout(timer);
    timer = setTimeout(function(){ saveDraft(reload); }, 450);
  }
  function saveDraft(reload){
    fetch('/dadmin/theme/'+KEY+'/draft', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(state)})
      .then(function(r){return r.json();}).then(function(){
        if (reload) { try{ frame.contentWindow.location.reload(); }catch(e){ frame.src = frame.src; } }
        else { pushCss(); }
      }).catch(function(){});
  }
  function pushCss(){
    fetch('/dadmin/theme/'+KEY+'/preview_css', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({settings: state.settings})})
      .then(function(r){return r.json();}).then(function(d){
        try{ frame.contentWindow.postMessage({type:'dawn-theme-preview', imports:d.imports, css:d.css}, '*'); }catch(e){}
      }).catch(function(){});
  }
  document.querySelectorAll('[data-set]').forEach(function(el){
    var name = el.getAttribute('data-set');
    var isCss = !!el.closest('[data-css]');
    var evt = (el.type==='range'||el.type==='color'||el.type==='text'||el.tagName==='TEXTAREA') ? 'input' : 'change';
    el.addEventListener(evt, function(){
      var v = (el.type==='checkbox') ? (el.checked?'1':'0') : el.value;
      state.settings[name] = v;
      document.querySelectorAll('[data-set="'+name+'"]').forEach(function(o){ if(o!==el && o.type!=='checkbox') o.value=v; });
      var out = document.querySelector('[data-range-out="'+name+'"]');
      if (out) out.textContent = v;
      schedule(!isCss);
    });
  });
  document.querySelectorAll('[data-sec-set]').forEach(function(el){
    var row = el.closest('[data-sec-row]');
    var idx = state.sections.findIndex(function(s){ return s.type === row.getAttribute('data-sec-row'); });
    var skey = el.getAttribute('data-sec-set');
    el.addEventListener(el.tagName==='SELECT' ? 'change' : 'input', function(){
      var v = (el.type==='checkbox') ? (el.checked?'1':'0') : el.value;
      state.sections[idx].settings[skey] = v;
      schedule(true);
    });
  });
  window.dawnSecToggle = function(i, on){ state.sections[i].enabled = on; schedule(true); };
  window.dawnSecMove = function(i, dir){
    var j = i + dir;
    if (j < 0 || j >= state.sections.length) return;
    var t = state.sections[i]; state.sections[i] = state.sections[j]; state.sections[j] = t;
    saveDraft(true);
    setTimeout(function(){ location.reload(); }, 400);
  };
  window.dawnViewport = function(w){
    var wrap = document.getElementById('preview-wrap');
    wrap.style.maxWidth = w;
    document.querySelectorAll('[data-vp]').forEach(function(b){ b.classList.toggle('!text-white', b.getAttribute('data-vp')===w); });
  };
})();
""" % (json.dumps(key), json.dumps({"settings": settings, "sections": [
            {"type": s["type"], "enabled": s["enabled"], "settings": s["settings"]} for s in state["sections"]]
        }, ensure_ascii=False).replace("</", "<\\/"))

        return _dawn_admin_shell("appearance", Div(
            _dawn_msg(msg) if msg else None,
            Div(
                Div(
                    A("← 返回外观", href="/dadmin/appearance", cls="text-slate-500 hover:text-slate-300 text-sm"),
                    H1(f"定制主题：{pkg.name}", cls="text-xl font-black text-white mt-1"),
                    cls=""),
                Div(
                    Span("● 未保存更改", id="draft-badge",
                         cls="text-amber-400 text-xs font-bold mr-3",
                         style="" if state["has_draft"] else "display:none"),
                    A("代码 (JSON)", href=f"/dadmin/theme/{key}/code", cls="text-slate-400 hover:text-slate-200 text-xs mr-3"),
                    Form(Button("放弃更改", type="submit", cls=DAWN_BTN_GHOST,
                                onclick="return confirm('放弃所有未保存的更改？')"),
                         method="post", action=f"/dadmin/theme/{key}/discard", cls="inline mr-2"),
                    Form(Button("保存发布", type="submit", cls=DAWN_BTN),
                         method="post", action=f"/dadmin/theme/{key}/save", cls="inline"),
                    cls="flex items-center"),
                cls="flex items-center justify-between mb-4 flex-wrap gap-y-2"),
            Div(
                Div(
                    sections_html,
                    *settings_html,
                    cls="w-full xl:w-[340px] flex-none xl:h-[calc(100vh-220px)] xl:overflow-y-auto pr-1"),
                Div(
                    Div(
                        Span("预览", cls="text-slate-400 text-xs font-bold"),
                        Div(
                            Button("桌面", type="button", onclick="dawnViewport('100%')", cls="text-slate-400 hover:text-slate-200 text-xs px-2 !text-white", **{"data-vp": "100%"}),
                            Button("平板", type="button", onclick="dawnViewport('820px')", cls="text-slate-400 hover:text-slate-200 text-xs px-2", **{"data-vp": "820px"}),
                            Button("手机", type="button", onclick="dawnViewport('390px')", cls="text-slate-400 hover:text-slate-200 text-xs px-2", **{"data-vp": "390px"}),
                            cls="ml-3"),
                        A("新窗口打开 ↗", href=preview_url, target="_blank", cls="text-indigo-400 hover:text-indigo-300 text-xs ml-auto"),
                        cls="mb-2 flex items-center"),
                    Div(
                        Iframe(src=preview_url, id="theme-preview-frame",
                               cls="w-full rounded-xl border border-slate-700 bg-white",
                               style="height:calc(100vh - 260px); min-height:480px;"),
                        id="preview-wrap", cls="mx-auto transition-all"),
                    cls="flex-1 min-w-0"),
                cls="flex flex-col xl:flex-row gap-5 items-start"),
            Script(editor_js),
        ))

    @app.post("/dadmin/theme/{key}/draft")
    async def admin_theme_draft(request, session, key: str):
        if not _dawn_require_admin(session):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from dawn_themes import dawn_get_package, dawn_set_theme_settings, dawn_set_theme_home_sections
        if not dawn_get_package(key):
            return JSONResponse({"error": "theme not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body.get("settings"), dict):
            dawn_set_theme_settings(key, body["settings"], draft=True)
        if isinstance(body.get("sections"), list):
            dawn_set_theme_home_sections(key, body["sections"], draft=True)
        return JSONResponse({"ok": True})

    @app.post("/dadmin/theme/{key}/preview_css")
    async def admin_theme_preview_css(request, session, key: str):
        if not _dawn_require_admin(session):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from dawn_themes import dawn_get_package, dawn_theme_settings_css, _dawn_validate_setting_value, _dawn_get_setting
        pkg = dawn_get_package(key)
        if not pkg:
            return JSONResponse({"imports": "", "css": ""})
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = (body or {}).get("settings") or {}
        s = {}
        for name, spec in pkg.settings_schema().items():
            if name in payload:
                v, _ok = _dawn_validate_setting_value(spec, payload.get(name))
                s[name] = v
            else:
                s[name] = _dawn_get_setting(f"theme_{key}_set_{name}", str(spec.get("default", "")))
        imports, css = dawn_theme_settings_css(key, values=s)
        return JSONResponse({"imports": imports, "css": css})

    @app.post("/dadmin/theme/{key}/save")
    async def admin_theme_save(session, key: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_theme_publish_draft
        n = dawn_theme_publish_draft(key)
        return RedirectResponse(f"/dadmin/theme/{key}/edit?msg=✅ 已发布 {n} 项更改", status_code=303)

    @app.post("/dadmin/theme/{key}/discard")
    async def admin_theme_discard(session, key: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_theme_clear_draft
        dawn_theme_clear_draft(key)
        return RedirectResponse(f"/dadmin/theme/{key}/edit?msg=已放弃未保存的更改", status_code=303)

    @app.get("/dadmin/theme/{key}/code")
    async def admin_theme_code(session, key: str, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_get_package, dawn_preview_signature
        pkg = dawn_get_package(key)
        if not pkg or not (pkg.path / "theme.json").exists():
            return RedirectResponse("/dadmin/appearance?msg=该主题不是完整主题包，无 JSON 可编辑", status_code=303)
        theme_json_raw = (pkg.path / "theme.json").read_text(encoding="utf-8")
        vars_file = pkg.path / "vars.json"
        vars_json_raw = vars_file.read_text(encoding="utf-8") if vars_file.exists() else "{}"
        sig = dawn_preview_signature(key)
        preview_url = f"/?__theme_preview={key}&__sig={sig}"

        return _dawn_admin_shell("appearance", Div(
            _dawn_msg(msg) if msg else None,
            Div(
                Div(
                    A("← 返回可视化编辑", href=f"/dadmin/theme/{key}/edit", cls="text-slate-500 hover:text-slate-300 text-sm"),
                    H1(f"主题代码：{pkg.name}", cls="text-2xl font-black text-white mt-1"),
                    P(f"themes/{key}/ · 保存前自动备份为 .bak", cls="text-slate-600 text-xs mt-1"),
                    cls="mb-5"),
                cls=""),
            Div(
                Form(
                    Div(
                        Label("theme.json（元数据 + 设置项 schema）", cls=DAWN_LABEL),
                        Textarea(theme_json_raw, name="theme_json", spellcheck="false",
                                 cls=DAWN_INPUT + " font-mono !text-xs leading-relaxed h-72 whitespace-pre"),
                        cls="mb-4"),
                    Div(
                        Label("vars.json（设计变量默认值）", cls=DAWN_LABEL),
                        Textarea(vars_json_raw, name="vars_json", spellcheck="false",
                                 cls=DAWN_INPUT + " font-mono !text-xs leading-relaxed h-56 whitespace-pre"),
                        cls="mb-5"),
                    Button("💾 保存并刷新预览", type="submit", cls=DAWN_BTN),
                    method="post", action=f"/dadmin/theme/{key}/code",
                    cls="p-4 rounded-xl border border-slate-800 bg-slate-900/40"
                ),
                Div(
                    Div(
                        Span("实时预览", cls="text-slate-400 text-xs font-bold"),
                        A("新窗口打开 ↗", href=preview_url, target="_blank",
                          cls="text-indigo-400 hover:text-indigo-300 text-xs ml-3"),
                        cls="mb-2 flex items-center"),
                    Iframe(src=preview_url, id="theme-preview-frame",
                           cls="w-full rounded-xl border border-slate-700 bg-white",
                           style="height:calc(100vh - 260px); min-height:480px;"),
                    cls="sticky top-4"
                ),
                cls="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start"
            ),
        ))

    @app.post("/dadmin/theme/{key}/code")
    async def admin_theme_code_save(session, key: str, theme_json: str = "", vars_json: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from dawn_themes import dawn_get_package, dawn_reload_themes
        pkg = dawn_get_package(key)
        if not pkg or not (pkg.path / "theme.json").exists():
            return RedirectResponse("/dadmin/appearance?msg=主题不存在", status_code=303)
        try:
            meta = json.loads(theme_json)
        except Exception as e:
            return RedirectResponse(f"/dadmin/theme/{key}/code?msg=theme.json 解析失败：{e}", status_code=303)
        if (meta.get("key") or "") != key:
            return RedirectResponse(f"/dadmin/theme/{key}/code?msg=theme.json 的 key 必须等于目录名「{key}」", status_code=303)
        if not meta.get("name"):
            return RedirectResponse(f"/dadmin/theme/{key}/code?msg=theme.json 缺少 name 字段", status_code=303)
        try:
            vars_data = json.loads(vars_json or "{}")
        except Exception as e:
            return RedirectResponse(f"/dadmin/theme/{key}/code?msg=vars.json 解析失败：{e}", status_code=303)
        if not isinstance(vars_data, dict):
            return RedirectResponse(f"/dadmin/theme/{key}/code?msg=vars.json 必须是 JSON 对象", status_code=303)

        theme_file = pkg.path / "theme.json"
        vars_file = pkg.path / "vars.json"
        shutil.copy2(theme_file, str(theme_file) + ".bak")
        if vars_file.exists():
            shutil.copy2(vars_file, str(vars_file) + ".bak")
        theme_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        vars_file.write_text(json.dumps(vars_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        dawn_reload_themes()
        return RedirectResponse(f"/dadmin/theme/{key}/code?msg=✅ 已保存，右侧预览已是最新", status_code=303)

