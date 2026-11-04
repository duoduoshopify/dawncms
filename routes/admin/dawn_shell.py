# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/shell.py
# 后台设计系统：侧栏布局壳 + 语义化组件 + 菜单注册表（插件扩展点）
# 后台界面多语言：locales/{lang}.json（Shopify 式），admin_lang Cookie 经 ASGI 中间件注入 contextvar

import contextvars
import json
from pathlib import Path

from fasthtml.common import *

from dawn_config import dawn_site_name

DAWN_LOCALE_DIR = Path(__file__).parent / "locales"
_dawn_adm_locale_cache = {}
_dawn_adm_lang_var = contextvars.ContextVar("adm_lang", default="zh-CN")
DAWN_ADMIN_LANGS = {"zh-CN": "简体中文", "en": "English", "ja": "日本語", "zh-TW": "繁體中文"}

DAWN_GROUP_KEYS = {"概览": "menu.group.overview", "内容": "menu.group.content",
               "用户": "menu.group.users", "站点": "menu.group.site", "插件": "menu.group.plugins"}


def _dawn_adm_locale() -> dict:
    lang = _dawn_adm_lang_var.get()
    if lang in _dawn_adm_locale_cache:
        return _dawn_adm_locale_cache[lang]
    table = {}
    f = DAWN_LOCALE_DIR / f"{lang}.json"
    if lang != "zh-CN" and f.exists():
        try:
            table = json.loads(f.read_text("utf-8"))
        except Exception:
            table = {}
    _dawn_adm_locale_cache[lang] = table
    return table


def dawn_adm_t(key: str, default: str = "") -> str:
    """后台文案翻译：当前请求语言（admin_lang Cookie）→ 缺键回退 default/中文"""
    return _dawn_adm_locale().get(key) or default


class DawnAdminLangMiddleware:
    """纯 ASGI 中间件：读 admin_lang Cookie 写入 contextvar（同任务传播，shell 零改动）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        lang = "zh-CN"
        for h, v in scope.get("headers", []):
            if h == b"cookie":
                for part in v.decode("latin1").split(";"):
                    if part.strip().startswith("admin_lang="):
                        cand = part.strip().split("=", 1)[1].strip()
                        if cand in DAWN_ADMIN_LANGS:
                            lang = cand
                break
        token = _dawn_adm_lang_var.set(lang)
        try:
            await self.app(scope, receive, send)
        finally:
            _dawn_adm_lang_var.reset(token)

DAWN_ADM_CSS = r"""
:root{
  --adm-bg:#0a0e17; --adm-sidebar:#0d1322; --adm-card:#121a2c; --adm-card-hover:#182138;
  --adm-line:#1c2438; --adm-line-strong:#28334f;
  --adm-text:#e6eaf2; --adm-dim:#8b94a8; --adm-faint:#5a6378;
  --adm-accent:#6366f1; --adm-accent-soft:rgba(99,102,241,.14);
}
body{background:var(--adm-bg);color:var(--adm-text);
  font-family:'PingFang SC','Microsoft YaHei',system-ui,sans-serif}
.adm-sidebar{background:var(--adm-sidebar);border-right:1px solid var(--adm-line)}
.adm-group-label{font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--adm-faint);font-weight:700;padding:0 12px;margin:18px 0 6px}
.adm-link{display:flex;align-items:center;gap:9px;padding:7px 12px;margin:1px 8px;
  border-radius:8px;font-size:13.5px;color:var(--adm-dim);font-weight:500;
  border-left:2px solid transparent;transition:all .15s}
.adm-link:hover{color:var(--adm-text);background:var(--adm-card)}
.adm-link.active{color:var(--adm-text);background:var(--adm-accent-soft);
  border-left-color:var(--adm-accent);font-weight:600}
.adm-link .adm-ico{width:18px;text-align:center;font-size:14px}
.adm-topbar{background:var(--adm-sidebar);border-bottom:1px solid var(--adm-line)}
.adm-card{background:var(--adm-card);border:1px solid var(--adm-line);border-radius:12px}
::placeholder{color:var(--adm-faint)}

/* ── 亮色主题（html.adm-light，顶栏按钮切换，localStorage 记忆）── */
/* 暖纸色系：避免纯白眩光，整体低对比柔和 */
html.adm-light{
  --adm-bg:#f2f1ec; --adm-sidebar:#faf9f5; --adm-card:#fdfcf9; --adm-card-hover:#f0eee8;
  --adm-line:#e6e3da; --adm-line-strong:#d5d1c5;
  --adm-text:#3a3f46; --adm-dim:#6e747c; --adm-faint:#a2a7ad;
}
html.adm-light .bg-slate-900\/40,
html.adm-light .bg-slate-900\/60,
html.adm-light .bg-slate-900\/70{background:#fdfcf9}
html.adm-light .bg-slate-800\/80{background:#fdfcf9}
html.adm-light .bg-slate-800\/60,
html.adm-light .bg-slate-800{background:#efede6}
html.adm-light .bg-slate-800\/70{background:#eceae2}
html.adm-light .bg-slate-700{background:#e6e3da}
html.adm-light .text-white,
html.adm-light .text-slate-100{color:#3a3f46}
html.adm-light .text-slate-200{color:#454b53}
html.adm-light .text-slate-300{color:#4d545d}
html.adm-light .text-slate-400{color:#667079}
html.adm-light .text-slate-500{color:#767d86}
html.adm-light .text-slate-600{color:#9aa0a8}
html.adm-light .border-slate-800,
html.adm-light .border-slate-800\/60{border-color:#e6e3da}
html.adm-light .border-slate-700,
html.adm-light .border-slate-700\/60{border-color:#d9d5c9}
html.adm-light .border-slate-600{border-color:#c8c3b5}
html.adm-light .border-slate-500{border-color:#b8b2a2}
html.adm-light .hover\:bg-slate-800:hover{background:#e9e6dd}
html.adm-light .text-indigo-300,
html.adm-light .text-indigo-400{color:#4f46e5}
html.adm-light .text-emerald-400{color:#059669}
html.adm-light .text-amber-400{color:#b45309}
html.adm-light .text-sky-400{color:#0284c7}
html.adm-light .text-red-400{color:#dc2626}
/* 实色按钮保持白字（修复全局 text-white→深色 把彩色按钮变成黑字的问题） */
html.adm-light .bg-indigo-600, html.adm-light .bg-indigo-500,
html.adm-light .bg-rose-600\/80, html.adm-light .bg-rose-500,
html.adm-light .bg-red-600\/80, html.adm-light .bg-red-500,
html.adm-light .bg-emerald-600, html.adm-light .bg-emerald-500,
html.adm-light .bg-indigo-600 *, html.adm-light .bg-indigo-500 *,
html.adm-light .bg-rose-600\/80 *, html.adm-light .bg-rose-500 *,
html.adm-light .bg-red-600\/80 *, html.adm-light .bg-red-500 *,
html.adm-light .bg-emerald-600 *, html.adm-light .bg-emerald-500 *{color:#fff}
/* 实色按钮：轻投影 + hover 加深 */
html.adm-light .bg-indigo-600, html.adm-light .bg-indigo-500,
html.adm-light .bg-rose-600\/80, html.adm-light .bg-rose-500,
html.adm-light .bg-red-600\/80, html.adm-light .bg-red-500,
html.adm-light .bg-emerald-600, html.adm-light .bg-emerald-500{box-shadow:0 1px 2px rgba(70,60,40,.14)}
html.adm-light .bg-indigo-600:hover{background:#4338ca}
html.adm-light .bg-indigo-500:hover{background:#4f46e5}
html.adm-light .bg-rose-600\/80:hover, html.adm-light .bg-rose-500:hover{background:#be123c}
html.adm-light .bg-red-600\/80:hover, html.adm-light .bg-red-500:hover{background:#b91c1c}
html.adm-light .bg-emerald-600:hover, html.adm-light .bg-emerald-500:hover{background:#047857}
/* 渐变主按钮（DAWN_BTN）保持白字 + 轻投影 */
html.adm-light [class*="bg-gradient-to"],
html.adm-light [class*="bg-gradient-to"] *{color:#fff}
html.adm-light [class*="bg-gradient-to"]{box-shadow:0 1px 2px rgba(70,60,40,.14)}
/* 次级按钮（灰底）加描边，避免"一片灰" */
html.adm-light .bg-slate-800{border:1px solid #dcd8cb}
html.adm-light .bg-slate-800:hover{background:#e7e4d9;border-color:#cfcabb}
/* 卡片轻投影，从背景中浮起 */
html.adm-light .bg-slate-900\/40,
html.adm-light .bg-slate-900\/60,
html.adm-light .bg-slate-900\/70,
html.adm-light .bg-slate-800\/80{box-shadow:0 1px 2px rgba(70,60,40,.06)}
/* 侧栏当前项：indigo 深字 + 稍强底色 */
html.adm-light .adm-link.active{color:#4338ca;background:rgba(99,102,241,.12)}
html.adm-light .adm-link:hover{color:#2e3339}
/* 表格行 hover 微高亮 */
html.adm-light tbody tr:hover{background:#f5f3ec}
.adm-theme-btn{cursor:pointer;font-size:14px;padding:5px 10px;border-radius:8px;
  border:1px solid var(--adm-line);background:transparent;color:var(--adm-dim)}
.adm-theme-btn:hover{color:var(--adm-text);border-color:var(--adm-line-strong)}
"""

DAWN_INPUT = "w-full px-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-200 text-sm focus:outline-none focus:border-indigo-500"
DAWN_LABEL = "block text-slate-400 text-xs font-bold uppercase tracking-wider mb-1.5"
DAWN_BTN = "px-5 py-2.5 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-bold hover:opacity-90"
DAWN_BTN_DANGER = "px-3 py-1.5 rounded-lg bg-red-600/80 text-white text-xs font-bold hover:bg-red-500"
DAWN_BTN_GHOST = "px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs font-semibold hover:border-slate-500"


# ── 菜单注册表：插件可通过 dawn_register_admin_page 挂入 ──────────────
DAWN_ADMIN_MENU = [
    {"group": "概览", "items": [
        {"key": "dashboard", "label": "仪表盘", "url": "/dadmin", "icon": "📊"},
    ]},
    {"group": "内容", "items": [
        {"key": "posts", "label": "文章", "url": "/dadmin/posts", "icon": "📝"},
        {"key": "new", "label": "写文章", "url": "/dadmin/post/new", "icon": "✏️"},
        {"key": "categories", "label": "分类", "url": "/dadmin/categories", "icon": "🗂"},
        {"key": "series", "label": "系列", "url": "/dadmin/series", "icon": "📚"},
        {"key": "tags", "label": "标签", "url": "/dadmin/tags", "icon": "🏷"},
        {"key": "media", "label": "媒体库", "url": "/dadmin/media", "icon": "🖼"},
    ]},
    {"group": "用户", "items": [
        {"key": "members", "label": "会员", "url": "/dadmin/members", "icon": "👥"},
        {"key": "newsletter", "label": "订阅", "url": "/dadmin/newsletter", "icon": "📮"},
    ]},
    {"group": "站点", "items": [
        {"key": "settings", "label": "设置", "url": "/dadmin/settings", "icon": "⚙️"},
        {"key": "nav", "label": "导航", "url": "/dadmin/nav", "icon": "🧭"},
        {"key": "appearance", "label": "外观", "url": "/dadmin/appearance", "icon": "🎨"},
    ]},
    {"group": "插件", "items": []},
]


def dawn_register_admin_page(group: str, key: str, label: str, url: str, icon: str = "🧩") -> None:
    """插件/扩展模块注册后台菜单项（分组不存在时自动创建）"""
    for g in DAWN_ADMIN_MENU:
        if g["group"] == group:
            if not any(i["key"] == key for i in g["items"]):
                g["items"].append({"key": key, "label": label, "url": url, "icon": icon})
            return
    DAWN_ADMIN_MENU.append({"group": group, "items": [{"key": key, "label": label, "url": url, "icon": icon}]})


def _dawn_require_admin(session):
    return bool((session or {}).get("is_admin"))


def _dawn_menu_title(active: str) -> str:
    for g in DAWN_ADMIN_MENU:
        for i in g["items"]:
            if i["key"] == active:
                return i["label"]
    return ""


def _dawn_admin_shell(active: str, content, title: str = "", full: bool = False):
    # full 参数保留兼容；后台内容区已全局改为流式宽度
    page_title = title or dawn_adm_t(f"menu.{active}", _dawn_menu_title(active))
    lang = _dawn_adm_lang_var.get()
    menu_blocks = []
    for g in DAWN_ADMIN_MENU:
        if not g["items"]:
            continue
        menu_blocks.append(Div(dawn_adm_t(DAWN_GROUP_KEYS.get(g["group"], ""), g["group"]), cls="adm-group-label"))
        for item in g["items"]:
            menu_blocks.append(A(
                Span(item["icon"], cls="adm-ico"),
                Span(dawn_adm_t(f"menu.{item['key']}", item["label"])),
                href=item["url"],
                cls=f"adm-link {'active' if active == item['key'] else ''}"
            ))

    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Title(f"{page_title + ' · ' if page_title else ''}{dawn_adm_t('adm.title', '博客后台')} - {dawn_site_name()}"),
            Link(rel="icon", type="image/svg+xml", href="/static/logo.svg"),
            Link(rel="apple-touch-icon", href="/static/logo.svg"),
            Script("""(function(){
  try{if((localStorage.getItem('dawn_adm_theme')||'light')==='light')document.documentElement.classList.add('adm-light');}
  catch(e){document.documentElement.classList.add('adm-light');}
  window.dawnAdmToggleTheme=function(){
    var l=document.documentElement.classList.toggle('adm-light');
    try{localStorage.setItem('dawn_adm_theme',l?'light':'dark');}catch(e){}
    dawnAdmThemeBtn();
  };
  window.dawnAdmThemeBtn=function(){
    var b=document.getElementById('adm-theme-btn');
    if(b)b.textContent=document.documentElement.classList.contains('adm-light')?'☀️ 亮色':'🌙 暗色';
  };
  document.addEventListener('DOMContentLoaded',dawnAdmThemeBtn);
})();"""),
            Link(rel="stylesheet", href="/static/vendor/tailwind.admin.css?v=1"),
            Script(src="/static/vendor/htmx.min.js"),
            Style(DAWN_ADM_CSS),
        ),
        Body(
            Div(
                # 左侧栏
                Div(
                    Div(
                        A(
                            Img(src="/static/logo.svg", alt=dawn_site_name(), width="30", height="30", cls="rounded-md"),
                            Div(
                                Div(dawn_site_name(), cls="text-white font-black text-sm leading-tight"),
                                Div(dawn_adm_t("adm.title", "博客后台"), cls="text-[11px]", style="color:var(--adm-faint)"),
                            ),
                            href="/dadmin", cls="flex items-center gap-2.5 px-4 py-4",
                            style="border-bottom:1px solid var(--adm-line)"
                        ),
                        Div(*menu_blocks, cls="py-2 flex-1 overflow-y-auto"),
                        Div(
                            A(dawn_adm_t("adm.view_site", "🌐 查看前台"), href="/", cls="adm-link"),
                            A(dawn_adm_t("adm.logout", "⏻ 退出登录"), href="/dadmin/logout", cls="adm-link"),
                            cls="py-3", style="border-top:1px solid var(--adm-line)"
                        ),
                        cls="adm-sidebar fixed inset-y-0 left-0 w-[228px] flex flex-col"
                    ),
                ),
                # 主区
                Div(
                    Div(
                        H1(page_title, cls="text-white font-black text-lg") if page_title else Span(),
                        Div(
                            Button("☀️ 亮色", id="adm-theme-btn", type="button", cls="adm-theme-btn",
                                   onclick="dawnAdmToggleTheme()"),
                            Span(dawn_adm_t("adm.role_admin", "管理员"), cls="text-xs", style="color:var(--adm-dim)"),
                            cls="flex items-center gap-3"
                        ),
                        cls="adm-topbar sticky top-0 z-40 px-8 py-3.5 flex items-center justify-between"
                    ),
                    Div(content, cls="px-8 py-7"),
                    cls="ml-[228px] min-h-screen"
                ),
            ),
        ),
        lang=lang
    )


def _dawn_msg(text: str, ok: bool = True):
    if not text:
        return None
    return Div(text, cls=f"mb-4 px-4 py-3 rounded-lg text-sm font-semibold {'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' if ok else 'bg-red-500/15 text-red-300 border border-red-500/30'}")
