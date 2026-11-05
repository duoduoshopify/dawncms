# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/dawn_plugins.py
# 插件管理：加载状态 / 错误展示 / 启用停用（重启生效）

from fasthtml.common import *
from starlette.responses import RedirectResponse

from .dawn_shell import _dawn_admin_shell, _dawn_require_admin, _dawn_msg, DAWN_BTN, dawn_register_admin_page


def dawn_setup(app):
    dawn_register_admin_page("插件", "plugins", "插件管理", "/dadmin/plugins", "🧩")

    @app.get("/dadmin/plugins")
    async def admin_plugins(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        from plugins import dawn_get_loaded_plugins, DAWN_PLUGIN_API
        rows = []
        for p in dawn_get_loaded_plugins():
            status = p.get("status", "")
            if status == "ok":
                status_html = Span("运行中", cls="text-emerald-400 text-xs font-semibold")
            elif status == "disabled":
                status_html = Span("已停用（重启后生效）", cls="text-slate-500 text-xs font-semibold")
            else:
                status_html = Span(status, cls="text-red-400 text-xs font-semibold break-all")
            is_on = status != "disabled"
            rows.append(Tr(
                Td(Div(
                    Span(p.get("label") or p.get("name", ""), cls="text-white text-sm font-semibold"),
                    Span(f"  {p.get('name', '')}", cls="text-slate-500 text-xs font-mono"),
                )),
                Td(Span(str(p.get("api_version") or "—"), cls="text-slate-400 text-xs font-mono")),
                Td(A("打开", href=p["url"], cls="text-indigo-400 text-xs hover:underline") if p.get("url") else Span("—", cls="text-slate-600 text-xs")),
                Td(status_html),
                Td(Form(
                    Button("停用" if is_on else "启用", type="submit",
                           cls="px-3 py-1.5 rounded-lg text-xs font-bold " +
                               ("border border-slate-700 text-slate-300 hover:border-slate-500" if is_on
                                else "bg-emerald-600 text-white hover:bg-emerald-500")),
                    method="post", action=f"/dadmin/plugins/{p.get('name', '')}/toggle",
                    **{"onsubmit": "return confirm('启停插件需要重启服务才会生效，确认继续？')"}
                )),
                cls="border-b border-slate-800"
            ))
        return _dawn_admin_shell("plugins", Div(
            _dawn_msg(msg) if msg else None,
            H1("插件管理", cls="text-2xl font-black text-white mb-2"),
            P(f"插件目录：plugins/<名称>/plugin.py，约定 DAWN_PLUGIN 元信息 + dawn_setup(app)。核心插件 API 版本：{DAWN_PLUGIN_API}。启停需重启服务生效；加载失败不影响其他插件。",
              cls="text-slate-500 text-sm mb-6"),
            Table(
                Thead(Tr(
                    Th("插件", cls="text-left text-slate-500 text-xs font-semibold pb-3"),
                    Th("API", cls="text-left text-slate-500 text-xs font-semibold pb-3"),
                    Th("页面", cls="text-left text-slate-500 text-xs font-semibold pb-3"),
                    Th("状态", cls="text-left text-slate-500 text-xs font-semibold pb-3"),
                    Th("操作", cls="text-left text-slate-500 text-xs font-semibold pb-3"),
                )),
                Tbody(*rows),
                cls="w-full"
            ),
            cls="p-5 rounded-xl border border-slate-800 bg-slate-900/40"
        ))

    @app.post("/dadmin/plugins/{name}/toggle")
    async def admin_plugin_toggle(session, name: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        import re as _re
        if not _re.fullmatch(r"[a-z0-9_\-]+", name or ""):
            return RedirectResponse("/dadmin/plugins?msg=插件名不合法", status_code=303)
        from plugins import dawn_get_loaded_plugins, dawn_set_plugin_enabled
        known = {p.get("name"): p for p in dawn_get_loaded_plugins()}
        if name not in known:
            return RedirectResponse("/dadmin/plugins?msg=未找到该插件", status_code=303)
        enable = known[name].get("status") == "disabled"
        dawn_set_plugin_enabled(name, enable)
        return RedirectResponse(f"/dadmin/plugins?msg=已{'启用' if enable else '停用'} {name}，重启服务后生效", status_code=303)
