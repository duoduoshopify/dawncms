# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/assistant/plugin.py
# AI 助手插件：与多语言插件共用 plugin_i18n_config 表中的 AI 服务商配置
# （一处配置，两处使用）。提供：
#   1. 文章辅助：摘要 / 关键词 / Slug / 标签建议（文章编辑页底部面板）
#   2. 主题配置建议：自然语言 → 按 theme.json settings schema 校验的配置，
#      只写入草稿位，用户预览确认后才会发布
# 未配置 API Key 时所有功能降级为配置指引，站点其余功能完全不受影响。

import json
import re

import aiohttp
from fasthtml.common import *

from blog.dawn_factory import dawn_get_blog_db
from services.dawn_blog_service import DawnBlogService
from routes.admin.dawn_shell import (
    _dawn_admin_shell, _dawn_require_admin, _dawn_msg,
    DAWN_INPUT, DAWN_LABEL, DAWN_BTN, DAWN_BTN_GHOST, dawn_register_admin_page,
)
from ui.dawn_layout import DawnSafeHTML
from plugins import dawn_register_hook, dawn_get_loaded_plugins
import dawn_themes

DAWN_PLUGIN = {
    "key": "ai",
    "label": "AI 助手",
    "group": "插件",
    "icon": "✨",
    "url": "/dadmin/plugins/ai",
    "api_version": 1,
}


# ---------- AI 服务商配置（与多语言插件共用 plugin_i18n_config 表） ----------

async def _dawn_ai_config() -> dict:
    db = await dawn_get_blog_db()
    try:
        await db.execute("CREATE TABLE IF NOT EXISTS plugin_i18n_config ("
                         "key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
        rows = await (await db.execute("SELECT key, value FROM plugin_i18n_config")).fetchall()
    finally:
        await db.close()
    cfg = {r["key"]: r["value"] for r in rows}
    return {
        "provider": cfg.get("provider", ""),
        "base_url": cfg.get("base_url", ""),
        "api_key": cfg.get("api_key", ""),
        "model": cfg.get("model", ""),
    }


async def _dawn_ai_chat(cfg: dict, prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """OpenAI 兼容 /chat/completions 调用。失败抛 RuntimeError。"""
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    body = {"model": cfg["model"], "messages": messages, "temperature": temperature}
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.post(url, headers=headers, json=body) as resp:
            if resp.status != 200:
                detail = (await resp.text())[:200]
                raise RuntimeError(f"API {resp.status}: {detail}")
            data = await resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


def _dawn_extract_json(text: str) -> dict:
    """从模型输出中提取第一个 JSON 对象（容忍 ```json 包裹和前后废话）"""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _dawn_plain_text(md: str, limit: int = 3000) -> str:
    """Markdown 粗略转纯文本并截断，供 prompt 使用"""
    t = re.sub(r"```.*?```", " ", md or "", flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[#>*`\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


# ---------- 后台：AI 助手主页 ----------

def _dawn_status_card(cfg: dict, i18n_active: bool):
    configured = bool(cfg.get("api_key") and cfg.get("base_url") and cfg.get("model"))
    if configured:
        state = Div(
            Span("● 已配置", cls="text-emerald-400 font-bold text-sm"),
            Span(f"{cfg['provider'] or 'custom'} · {cfg['model']}", cls="text-slate-400 text-xs ml-3"),
            cls="mb-2"
        )
    else:
        state = Div(Span("● 未配置 API Key", cls="text-amber-400 font-bold text-sm"), cls="mb-2")
    note = P(
        "AI 服务商（Base URL / Key / 模型）与「多语言」插件共用同一份配置。",
        A("前往多语言设置页配置 →", href="/dadmin/plugins/i18n", cls="text-indigo-400 hover:text-indigo-300")
        if i18n_active else
        Span("启用「多语言」插件后即可在其设置页填写服务商信息。", cls="text-slate-500"),
        cls="text-slate-500 text-xs mb-3"
    )
    test = Div(
        Button("测试连接", type="button", cls=DAWN_BTN_GHOST,
               hx_post="/dadmin/plugins/ai/test", hx_target="#ai-test-result", hx_swap="innerHTML"),
        Span(id="ai-test-result", cls="text-xs ml-3 text-slate-400"),
        cls="flex items-center"
    ) if configured else None
    return Div(H3("服务商状态", cls="text-white font-bold text-sm mb-3"), state, note, test,
               cls="p-5 rounded-2xl border border-slate-800 bg-slate-900/40 mb-5")


def _dawn_theme_card(cfg: dict):
    """主题配置助手：自然语言 → schema 校验 → 草稿预览 → 确认发布"""
    key = dawn_themes.dawn_get_active_theme_key()
    pkg = dawn_themes.dawn_get_package(key)
    schema = pkg.settings_schema() if pkg else {}
    body = [H3("主题配置助手", cls="text-white font-bold text-sm mb-2"),
            P(f"用自然语言描述想要的风格，AI 只会修改当前主题（{pkg.name if pkg else key}）"
              "theme.json 声明过的设置项；生成的配置先进入草稿，预览确认后才会发布。",
              cls="text-slate-500 text-xs mb-3")]
    if not cfg.get("api_key"):
        body.append(P("配置 API Key 后可用。", cls="text-slate-600 text-xs"))
    elif not schema:
        body.append(P("当前主题未声明可配置项（theme.json settings），无需使用。", cls="text-slate-600 text-xs"))
    else:
        body += [
            Textarea(name="requirement", rows=2, cls=DAWN_INPUT + " mb-2", id="ai-theme-req",
                     placeholder="例如：改成适合技术文档的宽松风格，主色调用深绿，正文用衬线字体"),
            Div(
                Button("生成配置建议", type="button", cls=DAWN_BTN,
                       hx_post="/dadmin/plugins/ai/theme-suggest", hx_target="#ai-theme-result",
                       hx_swap="innerHTML", hx_include="#ai-theme-req"),
                Span("生成约需几秒到几十秒", cls="text-slate-600 text-xs ml-3"),
                cls="flex items-center"
            ),
            Div(id="ai-theme-result", cls="mt-4"),
        ]
    if dawn_themes.dawn_theme_has_draft(key):
        sig = dawn_themes.dawn_preview_signature(key)
        body.append(Div(
            Span("⚠ 当前主题存在未发布的草稿更改", cls="text-amber-400 text-xs mr-3"),
            A("前台预览草稿", href=f"/?__theme_preview={key}&__sig={sig}", target="_blank",
              cls="text-indigo-400 hover:text-indigo-300 text-xs mr-3"),
            A("到主题编辑器处理", href=f"/dadmin/theme/{key}/edit",
              cls="text-slate-400 hover:text-slate-200 text-xs"),
            cls="mt-4 pt-3 border-t border-slate-800"
        ))
    return Div(*body, cls="p-5 rounded-2xl border border-slate-800 bg-slate-900/40 mb-5")


def dawn_setup(app):
    dawn_register_admin_page(DAWN_PLUGIN["group"], DAWN_PLUGIN["key"], DAWN_PLUGIN["label"],
                             DAWN_PLUGIN["url"], DAWN_PLUGIN["icon"])
    dawn_register_hook("admin_post_panel", _dawn_admin_post_panel)

    @app.get("/dadmin/plugins/ai")
    async def ai_home(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        cfg = await _dawn_ai_config()
        i18n_active = any(p.get("name") == "i18n" and p.get("status") == "ok"
                          for p in dawn_get_loaded_plugins())
        return _dawn_admin_shell("ai", Div(
            _dawn_msg(msg) if msg else None,
            H1("AI 助手", cls="text-2xl font-black text-white mb-2"),
            P("可选辅助层：未配置 API 时站点全部功能照常使用。文章辅助入口在文章编辑页底部「✨ AI 助手」面板。",
              cls="text-slate-500 text-sm mb-5"),
            _dawn_status_card(cfg, i18n_active),
            _dawn_theme_card(cfg),
        ))

    @app.post("/dadmin/plugins/ai/test")
    async def ai_test(session):
        if not _dawn_require_admin(session):
            return Span("未登录", cls="text-red-400")
        cfg = await _dawn_ai_config()
        try:
            out = await _dawn_ai_chat(cfg, "只回复两个字：正常")
            return Span(f"✅ 连接成功：{out[:20]}", cls="text-emerald-400")
        except Exception as e:
            return Span(f"❌ {e}", cls="text-red-400")

    # ---------- 文章辅助（编辑器底部面板调用） ----------

    @app.post("/dadmin/plugins/ai/assist")
    async def ai_assist(session, kind: str = "", title: str = "", content: str = ""):
        if not _dawn_require_admin(session):
            return Span("未登录", cls="text-red-400")
        cfg = await _dawn_ai_config()
        if not cfg.get("api_key"):
            return Span("尚未配置 API Key，请到「AI 助手」页查看配置指引。", cls="text-amber-400 text-xs")
        plain = _dawn_plain_text(content)
        if not title.strip() and not plain:
            return Span("请先填写标题或正文再生成。", cls="text-amber-400 text-xs")
        try:
            if kind == "description":
                out = await _dawn_ai_chat(cfg, (
                    "为以下博客文章写一段 60-120 字的中文摘要，用作 SEO description。"
                    "要求：自然流畅、包含核心关键词、不要引号和前后缀，只输出摘要本身。\n\n"
                    f"标题：{title}\n正文：{plain}"))
                return _dawn_suggestion(out, "填入摘要", "desc")
            if kind == "keywords":
                out = await _dawn_ai_chat(cfg, (
                    "为以下博客文章给出 4-6 个 SEO 关键词，用英文逗号分隔，只输出关键词本身。\n\n"
                    f"标题：{title}\n正文：{plain}"))
                return _dawn_suggestion(out, "填入关键词", "keywords")
            if kind == "slug":
                out = await _dawn_ai_chat(cfg, (
                    "为以下博客文章生成一个英文 URL slug：全小写、单词用连字符分隔、"
                    "3-6 个单词、只含字母数字连字符，只输出 slug 本身。\n\n"
                    f"标题：{title}\n正文：{plain[:800]}"), temperature=0.2)
                slug = re.sub(r"[^a-z0-9-]+", "-", out.lower()).strip("-")[:80]
                if not slug:
                    return Span("AI 未给出有效 slug，请重试。", cls="text-amber-400 text-xs")
                cands = (await DawnBlogService.generate_slug_candidates(slug)).get("candidates", [])
                final = cands[0]["slug"] if cands else slug
                adjusted = bool(cands and cands[0].get("adjusted"))
                return _dawn_suggestion(final, "填入 Slug", "slug",
                                        note="（已自动去重）" if adjusted else "")
            if kind == "tags":
                existing = [t.get("name", "") for t in await DawnBlogService.list_tags()]
                out = await _dawn_ai_chat(cfg, (
                    "为以下博客文章推荐标签。规则：优先从已有标签中挑选最合适的，"
                    "不足时再补充 1-3 个新标签。用英文逗号分隔，只输出标签名。\n\n"
                    f"已有标签：{', '.join(existing) or '（无）'}\n\n标题：{title}\n正文：{plain}"))
                return _dawn_tag_suggestion(out, existing)
        except Exception as e:
            return Span(f"❌ {e}", cls="text-red-400 text-xs")
        return Span("未知类型", cls="text-red-400 text-xs")

    # ---------- 主题配置建议（草稿预览确认） ----------

    @app.post("/dadmin/plugins/ai/theme-suggest")
    async def ai_theme_suggest(session, requirement: str = ""):
        if not _dawn_require_admin(session):
            return Span("未登录", cls="text-red-400")
        req = (requirement or "").strip()
        if not req:
            return Span("请先描述想要的风格。", cls="text-amber-400 text-xs")
        cfg = await _dawn_ai_config()
        if not cfg.get("api_key"):
            return Span("尚未配置 API Key。", cls="text-amber-400 text-xs")
        key = dawn_themes.dawn_get_active_theme_key()
        pkg = dawn_themes.dawn_get_package(key)
        schema = pkg.settings_schema() if pkg else {}
        if not schema:
            return Span("当前主题没有可配置项。", cls="text-amber-400 text-xs")

        lines = []
        for name, spec in schema.items():
            line = f"- {name}（{spec.get('label', name)}，类型 {spec.get('type')}，默认 {spec.get('default', '')}）"
            if spec.get("options"):
                line += f"，可选值：{' / '.join(str(o) for o in spec['options'])}"
            if spec.get("type") == "range":
                line += f"，取值范围 {spec.get('min', 0)}~{spec.get('max', 100)}"
            if spec.get("type") == "toggle":
                line += "，取值 1 或 0"
            lines.append(line)
        prompt = (
            "你是网站主题配置助手。根据用户需求，从下面允许的配置项中挑选需要修改的项，"
            "输出一个 JSON 对象：键必须是下列配置项名，值必须合法（select 只能从可选值里选，"
            "color 必须是 #rrggbb，range 在范围内，toggle 用 \"1\"/\"0\"）。"
            "只输出 JSON，不要任何解释；不确定的项不要包含。\n\n"
            f"允许的配置项：\n" + "\n".join(lines) + f"\n\n用户需求：{req}"
        )
        try:
            raw = await _dawn_ai_chat(cfg, prompt, temperature=0.2)
        except Exception as e:
            return Span(f"❌ {e}", cls="text-red-400 text-xs")
        data = _dawn_extract_json(raw)
        values = {k: str(v) for k, v in data.items() if k in schema}
        if not values:
            return Span("AI 未给出符合要求的配置，请换一种描述重试。", cls="text-amber-400 text-xs")

        saved, skipped = dawn_themes.dawn_set_theme_settings(key, values, draft=True)
        if not saved:
            return Span("AI 给出的值均未通过 schema 校验，未写入草稿。", cls="text-amber-400 text-xs")

        current = dawn_themes.dawn_theme_settings(key)
        rows = []
        for name, new_val in values.items():
            spec = schema.get(name, {})
            rows.append(Tr(
                Td(spec.get("label", name), cls="px-3 py-2 text-slate-300 text-xs"),
                Td(str(current.get(name, "")) or "（默认）", cls="px-3 py-2 text-slate-500 text-xs"),
                Td(str(new_val), cls="px-3 py-2 text-indigo-300 text-xs font-mono"),
                cls="border-b border-slate-800/60"
            ))
        sig = dawn_themes.dawn_preview_signature(key)
        return Div(
            P(f"✅ 已生成 {saved} 项配置并写入草稿（不影响线上，预览确认后才发布）"
              + (f"，{len(skipped)} 项未通过校验被跳过" if skipped else ""),
              cls="text-emerald-400 text-xs mb-3"),
            Table(
                Thead(Tr(Th("设置项", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                         Th("当前值", cls="px-3 py-2 text-left text-slate-500 text-xs"),
                         Th("AI 建议", cls="px-3 py-2 text-left text-slate-500 text-xs"))),
                Tbody(*rows),
                cls="w-full rounded-xl overflow-hidden border border-slate-800 mb-3"
            ),
            Div(
                A("👁 前台预览草稿", href=f"/?__theme_preview={key}&__sig={sig}", target="_blank",
                  cls=DAWN_BTN_GHOST),
                Form(Button(f"✅ 确认发布（{saved} 项）", type="submit", cls=DAWN_BTN + " ml-2"),
                     method="post", action=f"/dadmin/theme/{key}/save", style="display:inline"),
                Form(Button("放弃草稿", type="submit", cls=DAWN_BTN_GHOST + " ml-2",
                            onclick="return confirm('确定放弃这份 AI 生成的草稿？')"),
                     method="post", action=f"/dadmin/theme/{key}/discard", style="display:inline"),
                cls="flex items-center flex-wrap gap-y-2"
            ),
        )


# ---------- 文章编辑页底部面板（admin_post_panel 钩子） ----------

def _dawn_fill_button(label: str, target: str, value: str):
    js_value = json.dumps(value, ensure_ascii=False)
    return Button(label, type="button", cls=DAWN_BTN_GHOST + " ml-3 shrink-0",
                  onclick=f"var el=document.querySelector('[name={target}]');"
                          f"if(el){{el.value={js_value};el.dispatchEvent(new Event('input'));}}")


def _dawn_suggestion(text: str, fill_label: str, target: str, note: str = ""):
    return Div(
        Span(text, cls="text-slate-200 text-xs break-all"),
        Span(note, cls="text-slate-600 text-xs ml-1") if note else None,
        _dawn_fill_button(fill_label, target, text),
        cls="flex items-center py-1"
    )


def _dawn_tag_suggestion(raw: str, existing: list):
    names = [t.strip() for t in re.split(r"[,，、]", raw or "") if t.strip()][:8]
    if not names:
        return Span("AI 未给出有效标签，请重试。", cls="text-amber-400 text-xs")
    lower = {e.lower(): e for e in existing}
    matched = [lower[n.lower()] for n in names if n.lower() in lower]
    new = [n for n in names if n.lower() not in lower]
    parts = []
    if matched:
        js_names = json.dumps(matched, ensure_ascii=False)
        parts.append(Div(
            Span("勾选已有标签：" + "、".join(matched), cls="text-slate-200 text-xs"),
            Button("一键勾选", type="button", cls=DAWN_BTN_GHOST + " ml-3 shrink-0",
                   onclick=f"var names={js_names};"
                           "document.querySelectorAll('input[name=tag_ids]').forEach(function(cb){"
                           "if(names.indexOf(cb.parentElement.textContent.trim())>=0)cb.checked=true;});"),
            cls="flex items-center py-1"
        ))
    if new:
        parts.append(Div(
            Span("新标签建议：" + "、".join(new), cls="text-slate-400 text-xs"),
            Span("（可先到「标签」页创建后再勾选）", cls="text-slate-600 text-xs ml-1"),
            cls="flex items-center py-1"
        ))
    return Div(*parts)


async def _dawn_admin_post_panel(post_id: int, post: dict):
    cfg = await _dawn_ai_config()
    if not cfg.get("api_key"):
        return Div(
            Span("✨ AI 助手", cls="text-slate-400 text-sm font-bold mr-3"),
            A("配置 API Key 后可用（摘要 / 关键词 / Slug / 标签一键生成）→",
              href="/dadmin/plugins/ai", cls="text-indigo-400 hover:text-indigo-300 text-xs"),
            cls="mt-6 p-4 rounded-2xl border border-slate-800 bg-slate-900/40"
        )
    buttons = [
        ("生成摘要", "description"), ("生成关键词", "keywords"),
        ("生成 Slug", "slug"), ("推荐标签", "tags"),
    ]
    return Div(
        H3("✨ AI 助手", cls="text-white font-bold text-sm mb-1"),
        P("基于当前标题和正文生成，结果需手动点击「填入」才会写入表单，保存前可随时修改。",
          cls="text-slate-600 text-xs mb-3"),
        Div(
            *[Button(label, type="button", cls=DAWN_BTN_GHOST + " mr-2 mb-2",
                     hx_post="/dadmin/plugins/ai/assist",
                     hx_vals=f'{{"kind":"{kind}"}}',
                     hx_target="#ai-assist-result", hx_swap="innerHTML",
                     hx_include="#post-title,#post-content")
              for label, kind in buttons],
            cls="flex flex-wrap"
        ),
        Div(id="ai-assist-result", cls="mt-1 min-h-[20px]"),
        cls="mt-6 p-5 rounded-2xl border border-slate-800 bg-slate-900/40"
    )
