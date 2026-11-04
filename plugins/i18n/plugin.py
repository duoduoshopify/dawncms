# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/i18n/plugin.py
# 前端多语言插件：对接 OpenAI 兼容大模型 API，翻译文章并缓存，前台按语言访问

import hashlib
import json
import re
import asyncio
from datetime import datetime

import aiohttp
import aiosqlite
from fasthtml.common import *

from dawn_config import dawn_site_name, dawn_site_tagline, DAWN_SITE_BASE_URL
from blog.dawn_factory import dawn_get_blog_db
from services.dawn_blog_service import DawnBlogService
from services.dawn_markdown_renderer import DawnMarkdownRenderer
from routes.admin.dawn_shell import _dawn_admin_shell, _dawn_require_admin, _dawn_msg, DAWN_INPUT, DAWN_LABEL, DAWN_BTN, DAWN_BTN_DANGER, DAWN_BTN_GHOST, dawn_register_admin_page
from ui.dawn_layout import DAWN_BASE_CSS, DawnSafeHTML
from plugins import dawn_register_hook
import dawn_themes
from ui.dawn_article import DAWN_DOC_CSS, DAWN_DOC_JS, dawn_extract_toc_and_anchors
from ui.dawn_pages import dawn_category_slug_map, dawn_post_url, dawn_cover_url, DAWN_LIST_CSS

DAWN_PLUGIN = {
    "key": "i18n",
    "label": "多语言",
    "group": "插件",
    "icon": "🌐",
    "url": "/dadmin/plugins/i18n",
}

# BCP 47 区域码（URL/DB/Cookie 统一小写；hreflang 用标准大小写）
DAWN_LANG_NAMES = {
    "en-us": "English", "ja-jp": "日本語", "ko-kr": "한국어", "zh-tw": "繁體中文",
    "fr-fr": "Français", "de-de": "Deutsch", "es-es": "Español", "ru-ru": "Русский",
    "pt-pt": "Português", "it-it": "Italiano", "th-th": "ไทย", "vi-vn": "Tiếng Việt",
}

# 旧语言码 → 新 BCP 47 区域码
DAWN_LANG_MIGRATE = {
    "en": "en-us", "ja": "ja-jp", "ko": "ko-kr", "zh-TW": "zh-tw",
    "fr": "fr-fr", "de": "de-de", "es": "es-es", "ru": "ru-ru",
    "pt": "pt-pt", "it": "it-it", "th": "th-th", "vi": "vi-vn",
}


def _dawn_hreflang_code(lang: str) -> str:
    """en-us -> en-US（hreflang / html lang 标准大小写）"""
    parts = (lang or "").split("-")
    return f"{parts[0]}-{parts[1].upper()}" if len(parts) > 1 else lang

# 主题 UI 文案字典：主题模板通过 {{ t('key', '中文默认') }} 取用，未覆盖语言/键回退中文
DAWN_UI_STRINGS = {
    "en-us": {
        "login": "Sign in", "register": "Sign up", "admin": "Admin", "logout": "Sign out",
        "subscribe_title": "Subscribe", "subscribe_sub": "Get new posts in your inbox",
        "subscribe_btn": "Subscribe",
    },
    "ja-jp": {
        "login": "ログイン", "register": "登録", "admin": "管理", "logout": "ログアウト",
        "subscribe_title": "購読する", "subscribe_sub": "新着記事をメールでお届けします",
        "subscribe_btn": "購読",
    },
    "ko-kr": {
        "login": "로그인", "register": "가입", "admin": "관리", "logout": "로그아웃",
        "subscribe_title": "구독하기", "subscribe_sub": "새 글을 이메일로 받아보세요",
        "subscribe_btn": "구독",
    },
    "zh-tw": {
        "login": "登入", "register": "註冊", "admin": "管理", "logout": "登出",
        "subscribe_title": "訂閱本站", "subscribe_sub": "新文章發布時，第一時間寄到你的信箱",
        "subscribe_btn": "訂閱",
    },
    "fr-fr": {"login": "Connexion", "register": "Inscription", "admin": "Admin", "logout": "Déconnexion",
           "subscribe_title": "S'abonner", "subscribe_sub": "Recevez les nouveaux articles par email",
           "subscribe_btn": "S'abonner"},
    "de-de": {"login": "Anmelden", "register": "Registrieren", "admin": "Admin", "logout": "Abmelden",
           "subscribe_title": "Abonnieren", "subscribe_sub": "Neue Artikel per E-Mail erhalten",
           "subscribe_btn": "Abonnieren"},
    "es-es": {"login": "Entrar", "register": "Registrarse", "admin": "Admin", "logout": "Salir",
           "subscribe_title": "Suscribirse", "subscribe_sub": "Recibe nuevos artículos por email",
           "subscribe_btn": "Suscribirse"},
}

# 文章页字符串（post.html）
DAWN_ARTICLE_STRINGS = {
    "en-us": {"prev_post": "Previous", "next_post": "Next", "back_home": "Back to home",
           "rail_nav": "Series", "author_label": "Author", "newest_post": "This is the latest",
           "first_post": "This is the first", "no_posts": "No posts yet", "no_toc": "No outline",
           "series_block_title": "Part of series", "toc_title": "On this page",
           "related_title": "Related posts", "series_badge": "Series", "home": "Home", "docs_center": "Docs Center"},
    "ja-jp": {"prev_post": "前の記事", "next_post": "次の記事", "back_home": "ホームへ戻る",
           "rail_nav": "連載ナビ", "author_label": "著者", "newest_post": "最新の記事です",
           "first_post": "最初の記事です", "no_posts": "記事がありません", "no_toc": "目次なし",
           "series_block_title": "この連載について", "toc_title": "目次",
           "related_title": "関連記事", "series_badge": "連載", "home": "ホーム", "docs_center": "ドキュメント"},
    "zh-tw": {"prev_post": "上一篇", "next_post": "下一篇", "back_home": "返回首頁",
              "rail_nav": "專欄導航", "author_label": "內容作者", "newest_post": "已經是最新篇",
              "first_post": "已經是第一篇", "no_posts": "暫無文章", "no_toc": "暫無目錄",
              "series_block_title": "本篇所屬連載", "toc_title": "本頁目錄",
              "related_title": "相關文章", "series_badge": "連載", "home": "首頁", "docs_center": "文件中心"},
}
for _lang, _tbl in DAWN_ARTICLE_STRINGS.items():
    DAWN_UI_STRINGS.setdefault(_lang, {}).update(_tbl)


DAWN_ADMIN_LANGS_UI = {"zh-CN": "简体中文", "en": "English", "ja": "日本語", "zh-TW": "繁體中文"}


def _dawn_adm_lang_now() -> str:
    try:
        from routes.admin.dawn_shell import _dawn_adm_lang_var
        return _dawn_adm_lang_var.get()
    except Exception:
        return "zh-CN"


def _dawn_ui_translator(lang: str):
    table = DAWN_UI_STRINGS.get(lang, {})
    return lambda key, default="": table.get(key, default or key)

# 主流 OpenAI 兼容 API 服务商预设（均可直接填入使用；custom = 完全自定义）
DAWN_PROVIDERS = [
    # ---- 国内 ----
    {"key": "deepseek", "label": "DeepSeek 深度求索", "base_url": "https://api.deepseek.com/v1",
     "models": ["deepseek-chat", "deepseek-reasoner"], "hint": "platform.deepseek.com，性价比极高，推荐"},
    {"key": "qwen", "label": "阿里通义千问 DashScope", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"], "hint": "bailian.console.aliyun.com"},
    {"key": "moonshot", "label": "Kimi 月之暗面", "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-k2-0711-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"], "hint": "platform.moonshot.cn"},
    {"key": "zhipu", "label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-4-flash", "glm-4-air", "glm-4-plus"], "hint": "bigmodel.cn，glm-4-flash 免费"},
    {"key": "doubao", "label": "字节豆包 火山方舟", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-1-5-lite-32k", "doubao-1-5-pro-32k"], "hint": "console.volcengine.com/ark"},
    {"key": "hunyuan", "label": "腾讯混元", "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
     "models": ["hunyuan-lite", "hunyuan-standard", "hunyuan-turbo"], "hint": "console.cloud.tencent.com/hunyuan，lite 免费"},
    {"key": "qianfan", "label": "百度千帆", "base_url": "https://qianfan.baidubce.com/v2",
     "models": ["ernie-speed-128k", "ernie-4.0-turbo-8k", "ernie-lite-8k"], "hint": "console.bce.baidu.com/qianfan，speed/lite 免费"},
    {"key": "spark", "label": "讯飞星火", "base_url": "https://spark-api-open.xf-yun.com/v1",
     "models": ["lite", "generalv3.5", "4.0Ultra"], "hint": "xinghuo.xfyun.cn，lite 免费"},
    {"key": "yi", "label": "零一万物 Yi", "base_url": "https://api.lingyiwanwu.com/v1",
     "models": ["yi-lightning", "yi-large"], "hint": "platform.lingyiwanwu.com"},
    {"key": "stepfun", "label": "阶跃星辰 Step", "base_url": "https://api.stepfun.com/v1",
     "models": ["step-1-8k", "step-2-16k"], "hint": "platform.stepfun.com"},
    {"key": "minimax", "label": "MiniMax", "base_url": "https://api.minimaxi.com/v1",
     "models": ["MiniMax-Text-01", "abab6.5s-chat"], "hint": "platform.minimaxi.com"},
    {"key": "siliconflow", "label": "硅基流动 SiliconFlow", "base_url": "https://api.siliconflow.cn/v1",
     "models": ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3", "THUDM/GLM-4-9B-0414"],
     "hint": "cloud.siliconflow.cn，聚合多家开源模型，小模型免费"},
    # ---- 国际 ----
    {"key": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1",
     "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"], "hint": "platform.openai.com"},
    {"key": "gemini", "label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"], "hint": "aistudio.google.com，有免费额度"},
    {"key": "grok", "label": "xAI Grok", "base_url": "https://api.x.ai/v1",
     "models": ["grok-3-mini", "grok-3"], "hint": "console.x.ai"},
    {"key": "mistral", "label": "Mistral AI", "base_url": "https://api.mistral.ai/v1",
     "models": ["mistral-small-latest", "mistral-large-latest"], "hint": "console.mistral.ai，有免费层"},
    {"key": "groq", "label": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], "hint": "console.groq.com，免费额度高、速度快"},
    {"key": "openrouter", "label": "OpenRouter 聚合", "base_url": "https://openrouter.ai/api/v1",
     "models": ["openai/gpt-4o-mini", "deepseek/deepseek-chat", "google/gemini-2.0-flash-001"],
     "hint": "openrouter.ai，一个 Key 用所有模型"},
    {"key": "together", "label": "Together AI", "base_url": "https://api.together.xyz/v1",
     "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"], "hint": "api.together.ai"},
    {"key": "cohere", "label": "Cohere", "base_url": "https://api.cohere.ai/compatibility/v1",
     "models": ["command-r-plus", "command-r"], "hint": "dashboard.cohere.com"},
    {"key": "perplexity", "label": "Perplexity", "base_url": "https://api.perplexity.ai",
     "models": ["sonar", "sonar-pro"], "hint": "perplexity.ai/settings/api"},
    # ---- 本地/自建 ----
    {"key": "ollama", "label": "Ollama 本地", "base_url": "http://localhost:11434/v1",
     "models": ["qwen2.5:7b", "llama3.1:8b", "glm4:9b"], "hint": "本地部署免 Key（Key 可随意填）"},
    {"key": "lmstudio", "label": "LM Studio 本地", "base_url": "http://localhost:1234/v1",
     "models": [], "hint": "本地部署免 Key，模型名以实际加载为准"},
    {"key": "custom", "label": "自定义（OpenAI 兼容）", "base_url": "",
     "models": [], "hint": "任何兼容 /chat/completions 的端点"},
]

_dawn_tables_ready = False


async def _dawn_ensure_tables():
    global _dawn_tables_ready
    if _dawn_tables_ready:
        return
    db = await dawn_get_blog_db()
    await db.execute("""CREATE TABLE IF NOT EXISTS plugin_i18n_config (
        key TEXT PRIMARY KEY, value TEXT DEFAULT '')""")
    await db.execute("""CREATE TABLE IF NOT EXISTS plugin_i18n_translations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        lang TEXT NOT NULL,
        title TEXT DEFAULT '',
        desc_md TEXT DEFAULT '',
        content_md TEXT DEFAULT '',
        source_hash TEXT DEFAULT '',
        status TEXT DEFAULT 'done',
        error TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        UNIQUE(post_id, lang))""")
    try:
        await db.execute("ALTER TABLE plugin_i18n_translations ADD COLUMN desc_md TEXT DEFAULT ''")
    except Exception:
        pass
    await db.execute("""CREATE TABLE IF NOT EXISTS plugin_i18n_taxonomy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        lang TEXT NOT NULL,
        name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        UNIQUE(kind, source_id, lang))""")
    for old_c, new_c in DAWN_LANG_MIGRATE.items():
        await db.execute("UPDATE OR IGNORE plugin_i18n_translations SET lang=? WHERE lang=?", (new_c, old_c))
        await db.execute("UPDATE OR IGNORE plugin_i18n_taxonomy SET lang=? WHERE lang=?", (new_c, old_c))
    olds = tuple(k for k in DAWN_LANG_MIGRATE if k not in DAWN_LANG_NAMES)
    if olds:
        marks = ",".join("?" * len(olds))
        await db.execute(f"DELETE FROM plugin_i18n_translations WHERE lang IN ({marks})", olds)
        await db.execute(f"DELETE FROM plugin_i18n_taxonomy WHERE lang IN ({marks})", olds)
    await db.commit()
    await db.close()
    _dawn_tables_ready = True


async def _dawn_get_config() -> dict:
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row
    rows = await (await db.execute("SELECT key, value FROM plugin_i18n_config")).fetchall()
    await db.close()
    cfg = {r["key"]: r["value"] for r in rows}
    return {
        "provider": cfg.get("provider", "custom"),
        "base_url": cfg.get("base_url", "https://api.openai.com/v1"),
        "api_key": cfg.get("api_key", ""),
        "model": cfg.get("model", "gpt-4o-mini"),
        "languages": ",".join(DAWN_LANG_MIGRATE.get(l.strip(), l.strip()) for l in (cfg.get("languages", "en-us") or "").split(",") if l.strip()),
        "auto_detect": cfg.get("auto_detect", "1"),
        "auto_redirect": cfg.get("auto_redirect", "0"),
    }


async def _dawn_save_config(data: dict):
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    for k in ("provider", "base_url", "api_key", "model", "languages", "auto_detect", "auto_redirect"):
        if k in data:
            await db.execute(
                "INSERT INTO plugin_i18n_config(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, data[k]))
    await db.commit()
    await db.close()


def _dawn_lang_list(cfg: dict) -> list:
    return [l.strip() for l in (cfg.get("languages") or "").split(",") if l.strip()]


def _dawn_source_hash(post: dict) -> str:
    raw = (post.get("title", "") + "\n" + (post.get("content") or ""))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _dawn_get_translations(post_id: int) -> dict:
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row
    rows = await (await db.execute(
        "SELECT * FROM plugin_i18n_translations WHERE post_id=?", (post_id,))).fetchall()
    await db.close()
    return {r["lang"]: dict(r) for r in rows}


async def _dawn_save_translation(post_id: int, lang: str, title: str, content_md: str,
                            source_hash: str, status: str = "done", error: str = "",
                            desc_md: str = ""):
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    await db.execute(
        """INSERT INTO plugin_i18n_translations(post_id, lang, title, desc_md, content_md, source_hash, status, error, updated_at)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(post_id, lang) DO UPDATE SET
             title=excluded.title, desc_md=excluded.desc_md, content_md=excluded.content_md,
             source_hash=excluded.source_hash,
             status=excluded.status, error=excluded.error, updated_at=excluded.updated_at""",
        (post_id, lang, title, desc_md, content_md, source_hash, status, error,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await db.commit()
    await db.close()


# ---------- 分类/系列名称翻译 ----------

async def _dawn_get_taxonomy_map() -> dict:
    """返回 {(kind, source_id, lang): {name, description}}"""
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row
    rows = await (await db.execute("SELECT * FROM plugin_i18n_taxonomy")).fetchall()
    await db.close()
    return {(r["kind"], r["source_id"], r["lang"]): dict(r) for r in rows}


async def _dawn_save_taxonomy(kind: str, source_id: int, lang: str, name: str, description: str = ""):
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    await db.execute(
        """INSERT INTO plugin_i18n_taxonomy(kind, source_id, lang, name, description, updated_at)
           VALUES(?, ?, ?, ?, ?, ?)
           ON CONFLICT(kind, source_id, lang) DO UPDATE SET
             name=excluded.name, description=excluded.description, updated_at=excluded.updated_at""",
        (kind, source_id, lang, name, description, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await db.commit()
    await db.close()


async def _dawn_tax_names(kind: str, lang: str) -> dict:
    """{source_id: 译名}，无译名的不出现（调用方回退原名）"""
    tax_map = await _dawn_get_taxonomy_map()
    return {sid: v["name"] for (k, sid, lg), v in tax_map.items()
            if k == kind and lg == lang and v.get("name")}


# ---------- 大模型调用 ----------

def _dawn_chunk_markdown(md: str, limit: int = 1800) -> list:
    """按段落切块，每块不超过 limit 字符"""
    blocks = re.split(r"(\n\s*\n)", md)
    chunks, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) > limit:
            chunks.append(cur)
            cur = b
        else:
            cur += b
    if cur.strip():
        chunks.append(cur)
    return chunks or [md]


async def _dawn_llm_translate(cfg: dict, text: str, lang: str, is_title: bool = False) -> str:
    lang_name = DAWN_LANG_NAMES.get(lang, lang)
    kind = "标题" if is_title else "Markdown 正文片段"
    prompt = (
        f"你是专业翻译。将以下中文博客文章{kind}翻译成 {lang_name}（语言代码 {lang}）。\n"
        "要求：\n"
        "1. 保留所有 Markdown 语法标记（#、*、链接、代码块、图片语法等）原样不动\n"
        "2. 代码块内容、URL、HTML 标签、品牌名不翻译\n"
        "3. 只输出翻译结果，不要任何解释或前后缀\n\n"
        f"原文：\n{text}"
    )
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.post(url, headers=headers, json=body) as resp:
            if resp.status != 200:
                detail = (await resp.text())[:200]
                raise RuntimeError(f"API {resp.status}: {detail}")
            data = await resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def _dawn_translate_post(cfg: dict, post: dict, lang: str) -> tuple:
    """翻译标题 + 摘要 + 正文（分块），返回 (title, desc, content_md)"""
    title = await _dawn_llm_translate(cfg, post.get("title", ""), lang, is_title=True)
    desc = ""
    if (post.get("description") or "").strip():
        desc = await _dawn_llm_translate(cfg, post["description"], lang, is_title=True)
    md = post.get("content") or ""
    parts = []
    for chunk in _dawn_chunk_markdown(md):
        parts.append(await _dawn_llm_translate(cfg, chunk, lang))
    return title, desc, "\n\n".join(parts)


# ---------- 前台钩子：原文页显示语言入口 + hreflang ----------

def _dawn_hreflang_links(article_url: str, slug: str, translations: dict, langs: list) -> str:
    links = [f'<link rel="alternate" hreflang="zh-CN" href="{article_url}">']
    for lang in langs:
        t = translations.get(lang)
        if t and t.get("status") == "done":
            links.append(f'<link rel="alternate" hreflang="{_dawn_hreflang_code(lang)}" '
                         f'href="{DAWN_SITE_BASE_URL.rstrip("/")}/{lang}/{slug}">')
    links.append(f'<link rel="alternate" hreflang="x-default" href="{article_url}">')
    return "\n".join(links)


def _dawn_page_hreflang(zh_path: str, lang_tpl: str, langs: list) -> str:
    """通用 hreflang 互链：zh_path=中文页路径，lang_tpl=译文页路径模板（{l} 占位语言码）"""
    base = DAWN_SITE_BASE_URL.rstrip("/")
    links = [f'<link rel="alternate" hreflang="zh-CN" href="{base}{zh_path}">']
    for lang in langs:
        links.append(f'<link rel="alternate" hreflang="{_dawn_hreflang_code(lang)}" '
                     f'href="{base}{lang_tpl.format(l=lang)}">')
    links.append(f'<link rel="alternate" hreflang="x-default" href="{base}{zh_path}">')
    return "\n".join(links)


def _dawn_langs_sync() -> list:
    """同步读语言配置（head_extra 同步钩子用）"""
    import sqlite3
    try:
        db = sqlite3.connect("database/blog.db")
        row = db.execute("SELECT value FROM plugin_i18n_config WHERE key='languages'").fetchone()
        has_done = db.execute(
            "SELECT 1 FROM plugin_i18n_translations WHERE status='done' LIMIT 1").fetchone()
        db.close()
        if not has_done:
            return []
        return [l.strip() for l in (row[0] if row else "").split(",") if l.strip()]
    except Exception:
        return []


def _dawn_head_extra_hook(ctx: dict) -> str:
    """中文原文页补 hreflang（译文侧在 _list_page/post 渲染输出；文章页走 article_render 钩子）"""
    langs = _dawn_langs_sync()
    if not langs:
        return ""
    if ctx.get("is_home"):
        return _dawn_page_hreflang("/", "/{l}/", langs)
    if isinstance(ctx.get("series"), dict) and ctx["series"].get("slug"):
        s = ctx["series"]["slug"]
        return _dawn_page_hreflang(f"/series/{s}", "/{l}/s/" + s, langs)
    if isinstance(ctx.get("tag"), dict) and ctx["tag"].get("slug"):
        s = ctx["tag"]["slug"]
        return _dawn_page_hreflang(f"/tag/{s}", "/{l}/t/" + s, langs)
    cur = ctx.get("current_cat")
    if cur and isinstance(cur, str) and not ctx.get("a"):
        return _dawn_page_hreflang(f"/{cur}", "/{l}/c/" + cur, langs)
    return ""


async def _dawn_list_hreflang(page_type: str, slug: str, cat_slug: str) -> str:
    """译文列表页 hreflang：回链中文原文页 + 其它语言版本（双向闭合）"""
    langs = _dawn_lang_list(await _dawn_get_config())
    if not langs:
        return ""
    if page_type == "home":
        return _dawn_page_hreflang("/", "/{l}/", langs)
    if page_type == "category" and cat_slug:
        return _dawn_page_hreflang(f"/{cat_slug}", "/{l}/c/" + cat_slug, langs)
    if page_type == "series" and slug:
        return _dawn_page_hreflang(f"/series/{slug}", "/{l}/s/" + slug, langs)
    if page_type == "tag" and slug:
        return _dawn_page_hreflang(f"/tag/{slug}", "/{l}/t/" + slug, langs)
    return ""


async def _dawn_article_render_hook(article: dict, session: dict):
    if article.get("gated"):
        return None
    cfg = await _dawn_get_config()
    langs = _dawn_lang_list(cfg)
    if not langs or not cfg.get("api_key"):
        return None
    translations = await _dawn_get_translations(article.get("id", 0))
    done = [l for l in langs if translations.get(l, {}).get("status") == "done"]
    if not done:
        return None
    categories = await DawnBlogService.get_categories()
    article_url = f"{DAWN_SITE_BASE_URL.rstrip('/')}{dawn_post_url(article, categories)}"
    links = [f'<a href="/{l}/{article.get("slug", "")}" style="font-weight:600">{DAWN_LANG_NAMES.get(l, l)}</a>'
             for l in done]
    return {
        "article_banner": "🌐 本文有其他语言版本：" + " · ".join(links),
        "extra_head": _dawn_hreflang_links(article_url, article.get("slug", ""), translations, langs),
    }


# ---------- 多语言 sitemap ----------

# ---------- 浏览器语言 / 国家识别 ----------

DAWN_BOT_UA = re.compile(r"bot|spider|crawler|slurp|curl|wget|python-requests|headless", re.I)



def _dawn_parse_accept_language(header: str) -> list:
    """解析 Accept-Language，按 q 值降序返回语言代码"""
    out = []
    for part in (header or "").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, q = part.partition(";q=")
        try:
            qv = float(q) if q else 1.0
        except ValueError:
            qv = 1.0
        out.append((qv, code.strip()))
    return [c for _, c in sorted(out, key=lambda x: -x[0])]


async def _dawn_langs_with_translations() -> set:
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    rows = await (await db.execute(
        "SELECT DISTINCT lang FROM plugin_i18n_translations WHERE status='done'")).fetchall()
    await db.close()
    return {r[0] for r in rows}


def _dawn_set_lang_cookie(resp, lang: str):
    resp.set_cookie("site_lang", lang, max_age=180 * 86400, path="/", samesite="lax")
    return resp


# ---------- 列表页文案 / 语言切换下拉 ----------

DAWN_LIST_ZH = {
    "home_label": "首页", "about_label": "关于", "docs_label": "文档", "portal_sub": "共 {n} 篇译文（大模型翻译，仅供参考）",
    "cat_sub": "本分类共 {n} 篇译文", "series_sub": "连载系列 · 共 {n} 篇译文，按顺序阅读",
    "tag_sub": "标签下共 {n} 篇译文", "empty": "暂无该语言的译文", "read_fmt": "{n} 分钟",
    "site_tagline": "",
}

DAWN_LIST_T = {
    "en-us": {"home_label": "Home", "about_label": "About", "docs_label": "Docs", "portal_sub": "{n} posts · machine-translated, for reference",
           "cat_sub": "{n} posts in this category", "series_sub": "Series · {n} posts, read in order",
           "tag_sub": "{n} posts under this tag", "empty": "No translated posts yet", "read_fmt": "{n} min read",
           "site_tagline": "A lightweight, self-hosted CMS built for the long term"},
    "ja-jp": {"home_label": "ホーム", "about_label": "概要", "docs_label": "ドキュメント", "portal_sub": "全 {n} 件（機械翻訳）",
           "cat_sub": "このカテゴリに {n} 件", "series_sub": "連載 · 全 {n} 件",
           "tag_sub": "このタグに {n} 件", "empty": "翻訳記事はまだありません", "read_fmt": "{n} 分",
           "site_tagline": "軽量・セルフホスト・長期運営のためのCMS"},
    "zh-tw": {"home_label": "首頁", "about_label": "關於", "docs_label": "文件", "portal_sub": "共 {n} 篇譯文（大模型翻譯，僅供參考）",
              "cat_sub": "本分類共 {n} 篇譯文", "series_sub": "連載系列 · 共 {n} 篇譯文，按順序閱讀",
              "tag_sub": "標籤下共 {n} 篇譯文", "empty": "暫無該語言的譯文", "read_fmt": "{n} 分鐘",
              "site_tagline": "輕量、自持、長期主義的內容管理系統"},
}


def _dawn_lt(lang: str, key: str) -> str:
    return DAWN_LIST_T.get(lang, {}).get(key) or DAWN_LIST_ZH[key]


# 作者署名本地化（头像取首字符，英文版自动变为 "S"）
DAWN_AUTHOR_T = {"en-us": "DawnCMS Team", "ja-jp": "DawnCMS 編集部", "zh-tw": "站長"}


def _dawn_localize_read_time(rt: str, lang: str) -> str:
    """DB 存储的“6分钟”按语言本地化"""
    m = re.match(r"\s*(\d+)\s*分钟", rt or "")
    if not m:
        return rt or ""
    return _dawn_lt(lang, "read_fmt").format(n=m.group(1))


async def _dawn_lang_switch_entries(page_type: str = "", slug: str = "", cat_slug: str = "", current: str = "zh") -> list:
    """当前页面各语言版本的对应 URL（切换后停留在同一页面而非首页）。无译文时返回 []"""
    try:
        await _dawn_ensure_tables()
        zh_url = "/"
        if page_type == "article":
            from blog.dawn_crud import DawnBlogCRUD
            post = await DawnBlogCRUD.get_post_by_slug_admin(slug)
            if not post:
                return []
            categories = await DawnBlogService.get_categories()
            zh_url = dawn_post_url(post, categories)
            trans = await _dawn_get_translations(post.get("id", 0))
            langs = sorted(l for l, tr in trans.items() if tr.get("status") == "done")
        elif page_type == "category":
            zh_url = f"/{cat_slug}"
            langs = sorted(await _dawn_langs_with_translations())
        elif page_type == "series":
            zh_url = f"/series/{slug}"
            langs = sorted(await _dawn_langs_with_translations())
        elif page_type == "tag":
            zh_url = f"/tag/{slug}"
            langs = sorted(await _dawn_langs_with_translations())
        else:
            langs = sorted(await _dawn_langs_with_translations())
        if not langs:
            return []
        entries = [{"lang": "zh", "label": "中文", "url": zh_url, "current": current == "zh", "code": "zh-CN"}]
        for l in langs:
            if page_type == "category":
                url = f"/{l}/c/{cat_slug}"
            elif page_type == "series":
                url = f"/{l}/s/{slug}"
            elif page_type == "tag":
                url = f"/{l}/t/{slug}"
            elif page_type == "article":
                url = f"/{l}/{slug}"
            else:
                url = f"/{l}"
            entries.append({"lang": l, "label": DAWN_LANG_NAMES.get(l, l), "url": url,
                            "current": current == l, "code": _dawn_hreflang_code(l)})
        return entries
    except Exception as e:
        print(f"[i18n] lang_switch 生成失败: {e}")
        return []


async def _dawn_lang_switch_hook(page_type: str = "", slug: str = "", cat_slug: str = "", current: str = "zh"):
    """lang_switch 钩子：主程序页面传入页面定位信息，返回切换项列表"""
    return await _dawn_lang_switch_entries(page_type, slug, cat_slug, current)


async def _dawn_sitemap_hook():
    await _dawn_ensure_tables()
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row
    rows = await (await db.execute(
        """SELECT t.lang, t.updated_at, p.slug, p.visibility, p.category FROM plugin_i18n_translations t
           JOIN posts p ON p.id = t.post_id
           WHERE t.status='done' AND p.is_published=1""")).fetchall()
    await db.close()
    urls = []
    seen_langs = set()
    seen_cat_langs = set()
    base = DAWN_SITE_BASE_URL.rstrip("/")
    categories = await DawnBlogService.get_categories()
    cat_slug_by_name = {c.get("name"): c.get("slug", "") for c in categories}
    for r in rows:
        r = dict(r)
        if r["visibility"] != "public":
            continue
        lang = r["lang"]
        seen_langs.add(lang)
        lastmod = (r["updated_at"] or "")[:10]
        urls.append(f'<url><loc>{base}/{lang}/{r["slug"]}</loc>'
                    + (f'<lastmod>{lastmod}</lastmod>' if lastmod else "")
                    + '<changefreq>monthly</changefreq><priority>0.6</priority></url>')
        cat_slug = cat_slug_by_name.get(r.get("category", ""), "")
        if cat_slug and (lang, cat_slug) not in seen_cat_langs:
            seen_cat_langs.add((lang, cat_slug))
    for lang in sorted(seen_langs):
        urls.append(f'<url><loc>{base}/{lang}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
    for lang, cat_slug in sorted(seen_cat_langs):
        urls.append(f'<url><loc>{base}/{lang}/c/{cat_slug}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    # 系列 / 标签译文页
    tax_map = await _dawn_get_taxonomy_map()
    for lang in sorted(seen_langs):
        for series in await DawnBlogService.get_series():
            if tax_map.get(("series", series.get("id"), lang), {}).get("name"):
                urls.append(f'<url><loc>{base}/{lang}/s/{series.get("slug", "")}</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>')
        for tag in await DawnBlogService.list_tags():
            if tax_map.get(("tag", tag.get("id"), lang), {}).get("name"):
                urls.append(f'<url><loc>{base}/{lang}/t/{tag.get("slug", "")}</loc><changefreq>weekly</changefreq><priority>0.4</priority></url>')
    return urls


# ---------- 后台批量翻译任务 ----------

_dawn_job = {"running": False, "total": 0, "done": 0, "current": "", "errors": []}


async def _dawn_run_translate_job(post_ids: set | None = None):
    global _dawn_job
    try:
        cfg = await _dawn_get_config()
        langs = _dawn_lang_list(cfg)
        posts = await DawnBlogService.get_all_posts_for_admin()
        if post_ids:
            posts = [p for p in posts if p.get("id") in post_ids]
        pending = []
        for p in posts:
            h = _dawn_source_hash(p)
            translations = await _dawn_get_translations(p["id"])
            for lang in langs:
                t = translations.get(lang)
                if t and t.get("status") == "done" and t.get("source_hash") == h:
                    continue
                pending.append((p, lang, h))
        _dawn_job.update({"total": len(pending), "done": 0, "errors": []})
        for p, lang, h in pending:
            _dawn_job["current"] = f"{p.get('title', '')[:20]} → {lang}"
            try:
                title, desc, content_md = await _dawn_translate_post(cfg, p, lang)
                await _dawn_save_translation(p["id"], lang, title, content_md, h, desc_md=desc)
            except Exception as e:
                await _dawn_save_translation(p["id"], lang, "", "", "", status="failed", error=str(e)[:300])
                _dawn_job["errors"].append(f"{p.get('title', '')[:15]}({lang}): {str(e)[:60]}")
            _dawn_job["done"] += 1
    finally:
        _dawn_job["running"] = False
        _dawn_job["current"] = ""


# ---------- 后台文章编辑页：原文/译文 tab 同屏编辑 ----------

def _dawn_back(request, default="/dadmin/plugins/i18n"):
    """提交后跳回来源后台页（referer 须在 /dadmin/ 下，否则回默认页）"""
    ref = request.headers.get("referer") or ""
    return ref if "/dadmin/" in ref else default


DAWN_I18N_TAB_CSS = """
.i18n-tab{padding:.45rem .95rem;font-size:.75rem;font-weight:600;color:#94a3b8;
  border:1px solid #334155;border-bottom:none;border-radius:.5rem .5rem 0 0;background:transparent;cursor:pointer}
.i18n-tab-on{background:#1e293b;color:#fff;border-color:#475569}
"""


async def _dawn_admin_post_panel_hook(post_id: int = 0, post: dict | None = None):
    """编辑页底部面板：原文（只读参考）+ 各语言译文 tab，同屏对照编辑/保存/AI 重译"""
    if not post_id or not post:
        return None
    cfg = await _dawn_get_config()
    langs = _dawn_lang_list(cfg)
    if not langs:
        return None
    translations = await _dawn_get_translations(post_id)
    src_hash = _dawn_source_hash(post)
    slug = post.get("slug", "")

    def _tab_btn(key, label):
        return Button(label, type="button", **{"data-i18n-tab": key,
                      "onclick": f"i18nTab('{key}')",
                      "class": "i18n-tab" + (" i18n-tab-on" if key == "src" else "")})

    def _pane(key, *children, show=False):
        return Div(*children, id=f"i18n-pane-{key}", **{"data-i18n-pane": key},
                   cls=("block" if show else "hidden") + " border border-slate-700 rounded-b-xl rounded-tr-xl p-5 bg-slate-900/40")

    tabs = [_tab_btn("src", "📄 中文 · 原文")]
    panes = [_pane("src",
                   P("只读参考——修改原文请使用上方表单", cls="text-xs text-slate-500 mb-4"),
                   H3("标题", cls=DAWN_LABEL), Div(post.get("title", ""), cls="text-sm text-slate-200 mb-4"),
                   H3("摘要", cls=DAWN_LABEL), Div(post.get("description", "") or "（空）", cls="text-sm text-slate-400 mb-4 whitespace-pre-wrap"),
                   H3("正文 Markdown", cls=DAWN_LABEL),
                   Pre(post.get("content", "") or "", cls="text-xs text-slate-300 whitespace-pre-wrap rounded-lg p-4 max-h-96 overflow-auto",
                       style="background:var(--adm-bg);border:1px solid var(--adm-line)"),
                   show=True)]

    for lang in langs:
        t = translations.get(lang) or {}
        stale = bool(t.get("source_hash") and t.get("source_hash") != src_hash)
        if not t:
            badge = Span("⬜ 未翻译", cls="text-xs text-slate-500")
        elif stale:
            badge = Span("⚠️ 原文已变更", cls="text-xs text-amber-400")
        elif t.get("status") == "done":
            badge = Span("✅ 已完成", cls="text-xs text-emerald-400")
        else:
            badge = Span(f"❌ {t.get('error', '失败')[:30]}", cls="text-xs text-red-400")
        tabs.append(_tab_btn(lang, f"🌐 {DAWN_LANG_NAMES.get(lang, lang)}"))
        panes.append(_pane(lang,
            Div(
                Div(badge, Span(t.get("updated_at", ""), cls="text-xs text-slate-600 ml-3"),
                    A("🔗 前台预览", href=f"/{lang}/{slug}", target="_blank",
                      cls="text-xs text-indigo-400 hover:text-indigo-300 ml-3")),
                Div(
                    Button("✨ AI 翻译/重译", type="button", cls=DAWN_BTN_GHOST,
                           onclick=f"i18nRetranslate('{lang}', {post_id})"),
                    Button("💾 保存译文", type="button", cls=DAWN_BTN_GHOST + " border-emerald-700 text-emerald-300",
                           onclick=f"i18nSave('{lang}', {post_id})"),
                    Span("", id=f"f-msg-{lang}", cls="text-xs ml-3 text-slate-500"),
                    cls="flex items-center"),
                cls="flex items-center justify-between flex-wrap gap-2 mb-4"),
            H3("译文标题", cls=DAWN_LABEL),
            Input(id=f"f-title-{lang}", value=t.get("title", ""), cls=DAWN_INPUT + " mb-4"),
            H3("译文摘要", cls=DAWN_LABEL),
            Textarea(t.get("desc_md", "") or "", id=f"f-desc-{lang}", rows=2, cls=DAWN_INPUT + " mb-4"),
            H3("译文正文（Markdown）", cls=DAWN_LABEL),
            Textarea(t.get("content_md", "") or "", id=f"f-content-{lang}", rows=18,
                     cls=DAWN_INPUT + " font-mono text-xs"),
        ))

    js = """
function i18nTab(key){
  document.querySelectorAll('[data-i18n-pane]').forEach(function(p){p.classList.toggle('hidden', p.dataset.i18nPane!==key);p.classList.toggle('block', p.dataset.i18nPane===key)});
  document.querySelectorAll('[data-i18n-tab]').forEach(function(b){b.classList.toggle('i18n-tab-on', b.dataset.i18nTab===key)});
}
async function i18nSave(lang, postId){
  var msg=document.getElementById('f-msg-'+lang);
  var fd=new FormData();
  fd.append('post_id',postId);fd.append('lang',lang);
  fd.append('title',document.getElementById('f-title-'+lang).value);
  fd.append('desc_md',document.getElementById('f-desc-'+lang).value);
  fd.append('content_md',document.getElementById('f-content-'+lang).value);
  msg.textContent='保存中…';msg.className='text-xs ml-3 text-slate-400';
  try{
    var r=await fetch('/dadmin/plugins/i18n/api/save_translation',{method:'POST',body:fd});
    var j=await r.json();
    msg.textContent=j.ok?('✅ 已保存 '+j.updated_at):('❌ '+(j.error||'保存失败'));
    msg.className='text-xs ml-3 '+(j.ok?'text-emerald-400':'text-red-400');
  }catch(e){msg.textContent='❌ 网络错误';msg.className='text-xs ml-3 text-red-400';}
}
async function i18nRetranslate(lang, postId){
  var msg=document.getElementById('f-msg-'+lang);
  if(!confirm('用 AI 重新翻译并覆盖当前译文编辑框？（不点「保存译文」不会写入）'))return;
  msg.textContent='AI 翻译中…（可能需要几十秒）';msg.className='text-xs ml-3 text-slate-400';
  try{
    var fd=new FormData();fd.append('post_id',postId);fd.append('lang',lang);
    var r=await fetch('/dadmin/plugins/i18n/api/translate_one',{method:'POST',body:fd});
    var j=await r.json();
    if(j.ok){
      document.getElementById('f-title-'+lang).value=j.title||'';
      document.getElementById('f-desc-'+lang).value=j.desc_md||'';
      document.getElementById('f-content-'+lang).value=j.content_md||'';
      msg.textContent='✅ 翻译完成，已填入编辑框（请检查后保存）';msg.className='text-xs ml-3 text-emerald-400';
    }else{msg.textContent='❌ '+(j.error||'翻译失败');msg.className='text-xs ml-3 text-red-400';}
  }catch(e){msg.textContent='❌ 网络错误';msg.className='text-xs ml-3 text-red-400';}
}
"""
    return Div(
        Style(DAWN_I18N_TAB_CSS),
        H2("🌐 多语言译文", cls="text-white font-bold text-base mb-1"),
        P("原文与各语言译文同屏对照，点 tab 切换；译文独立保存，不影响上方原文表单",
          cls="text-xs text-slate-500 mb-4"),
        Div(*tabs, cls="flex gap-1 flex-wrap"),
        *panes,
        Script(js),
        cls="mt-8 p-5 rounded-xl border border-slate-800 bg-slate-900/20", id="i18n-panel"
    )



# ---------- 后台列表集成钩子：翻译操作下沉到业务列表 ----------

async def _dawn_admin_post_cell_hook(post: dict | None = None):
    """文章列表「多语言」列：各语言状态徽章（点击跳编辑页译文面板）+ JS 全译按钮"""
    if not post:
        return None
    cfg = await _dawn_get_config()
    langs = _dawn_lang_list(cfg)
    if not langs:
        return None
    translations = await _dawn_get_translations(post.get("id"))
    src_hash = _dawn_source_hash(post)
    pid = post.get("id")
    bits = []
    for lang in langs:
        t = translations.get(lang)
        code = lang.split("-")[0].upper()
        if not t:
            badge, color, tip = "—", "text-slate-600", "未翻译"
        elif t.get("status") == "failed":
            badge, color, tip = "❌", "text-red-400", t.get("error", "失败")[:40]
        elif t.get("source_hash") != src_hash:
            badge, color, tip = "⚠️", "text-amber-400", "原文已变更，建议重译"
        else:
            badge, color, tip = "✅", "text-emerald-400", "已翻译"
        bits.append(A(f"{code}{badge}", href=f"/dadmin/post/edit/{pid}#i18n-panel",
                      cls=f"text-xs {color} hover:text-indigo-300 mr-2 whitespace-nowrap no-underline",
                      title=f"{DAWN_LANG_NAMES.get(lang, lang)}：{tip}"))
    langs_js = json.dumps(langs)
    bits.append(Button("⚡ 全译", type="button", cls=DAWN_BTN_GHOST + " !py-0.5 !px-1.5 !text-[10px]",
                       onclick=f"i18nPostAll(this, {pid}, {langs_js})"))
    return Td(Div(*bits, cls="flex flex-wrap items-center gap-y-1"), cls="px-3 py-2.5")


async def _dawn_admin_post_toolbar_hook():
    """文章列表头部：一键翻译全部待译（后台任务）+ 行内 JS 助手"""
    cfg = await _dawn_get_config()
    if not _dawn_lang_list(cfg):
        return None
    js = """
async function i18nPostAll(btn, postId, langs){
  if(!confirm('后台翻译该文章的全部待译语言？（已是最新的语言会跳过）'))return;
  btn.disabled=true;btn.textContent='⏳';
  for(var i=0;i<langs.length;i++){
    var fd=new FormData();fd.append('post_id',postId);fd.append('lang',langs[i]);fd.append('skip_fresh','1');
    try{await fetch('/dadmin/plugins/i18n/api/translate_one',{method:'POST',body:fd});}catch(e){}
  }
  location.reload();
}
"""
    return Div(
        Form(Button("⚡ 一键翻译全部待译文章", type="submit", cls=DAWN_BTN_GHOST + " !text-xs",
                    onclick="return confirm('将翻译所有未译/已过期/失败的文章，后台运行，确认？')"),
             method="post", action="/dadmin/plugins/i18n/translate_all", style="display:inline"),
        Script(js),
        cls="inline-flex items-center ml-3")


async def _dawn_admin_tax_langs_hook():
    """分类/系列/标签列表询问目标语言列"""
    cfg = await _dawn_get_config()
    return _dawn_lang_list(cfg)


async def _dawn_admin_tax_cell_hook(kind: str = "", item: dict | None = None):
    """分类/系列/标签列表「多语言名称」列：每语言输入框 + 保存/AI"""
    if not kind or not item:
        return None
    langs = _dawn_lang_list(await _dawn_get_config())
    if not langs:
        return None
    tax_map = await _dawn_get_taxonomy_map()
    sid = item.get("id")
    tds = []
    for lang in langs:
        cur = tax_map.get((kind, sid, lang), {})
        key = f"{kind}-{sid}-{lang}"
        tds.append(Td(
            Div(
                Span(lang.split("-")[0].upper(), cls="text-[10px]", style="color:var(--adm-faint)"),
                Span("", id=f"tax-msg-{key}", cls="text-[10px] text-slate-500"),
                cls="mb-1 flex items-center gap-2"),
            Div(
                Input(id=f"tax-name-{key}", value=cur.get("name", ""), placeholder=item.get("name", ""),
                      cls="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 w-28"),
                Button("💾", type="button", cls=DAWN_BTN_GHOST + " !py-0.5 !px-1.5 ml-1", title="保存该语言名称",
                       onclick=f"i18nTaxSave('{kind}',{sid},'{lang}')"),
                Button("✨", type="button", cls=DAWN_BTN_GHOST + " !py-0.5 !px-1.5 ml-1", title="AI 翻译（填入后再保存）",
                       onclick=f"i18nTaxAI('{kind}',{sid},'{lang}')"),
                cls="flex items-center"),
            cls="px-3 py-2 align-top"))
    return tds


def _dawn_admin_tax_assets_hook():
    """分类/系列/标签列表页脚：行内 JS 助手（只注入一次）"""
    js = """
if(!window.i18nTaxSave){
window.i18nTaxSave = async function(kind,id,lang){
  var key=kind+'-'+id+'-'+lang;
  var msg=document.getElementById('tax-msg-'+key);
  var fd=new FormData();
  fd.append('kind',kind);fd.append('source_id',id);fd.append('lang',lang);
  fd.append('name',document.getElementById('tax-name-'+key).value);
  msg.textContent='…';
  try{
    var r=await fetch('/dadmin/plugins/i18n/api/taxonomy_save',{method:'POST',body:fd});
    var j=await r.json();
    msg.textContent=j.ok?'✅ 已保存':'❌ '+(j.error||'失败');
  }catch(e){msg.textContent='❌ 网络错误';}
  setTimeout(function(){msg.textContent=''},2500);
};
window.i18nTaxAI = async function(kind,id,lang){
  var key=kind+'-'+id+'-'+lang;
  var msg=document.getElementById('tax-msg-'+key);
  msg.textContent='AI…';
  try{
    var fd=new FormData();fd.append('kind',kind);fd.append('source_id',id);fd.append('lang',lang);
    var r=await fetch('/dadmin/plugins/i18n/api/taxonomy_translate',{method:'POST',body:fd});
    var j=await r.json();
    if(j.ok){document.getElementById('tax-name-'+key).value=j.name||'';msg.textContent='✅ 已填入，点 💾 保存';}
    else{msg.textContent='❌ '+(j.error||'失败');}
  }catch(e){msg.textContent='❌ 网络错误';}
};
}
"""
    return Script(js)


def dawn_setup(app):
    dawn_themes.dawn_register_locale_provider(lambda lang: DAWN_UI_STRINGS.get(lang, {}))
    dawn_register_admin_page(DAWN_PLUGIN["group"], DAWN_PLUGIN["key"], DAWN_PLUGIN["label"], DAWN_PLUGIN["url"], DAWN_PLUGIN["icon"])
    dawn_register_hook("article_render", _dawn_article_render_hook)
    dawn_register_hook("sitemap_urls", _dawn_sitemap_hook)
    dawn_register_hook("lang_switch", _dawn_lang_switch_hook)
    dawn_register_hook("admin_post_panel", _dawn_admin_post_panel_hook)
    dawn_register_hook("admin_post_cell", _dawn_admin_post_cell_hook)
    dawn_register_hook("admin_post_toolbar", _dawn_admin_post_toolbar_hook)
    dawn_register_hook("admin_tax_langs", _dawn_admin_tax_langs_hook)
    dawn_register_hook("admin_tax_cell", _dawn_admin_tax_cell_hook)
    dawn_register_hook("admin_tax_assets", _dawn_admin_tax_assets_hook)
    dawn_register_hook("head_extra", _dawn_head_extra_hook)

    from starlette.middleware.base import BaseHTTPMiddleware

    class _I18nDetectMiddleware(BaseHTTPMiddleware):
        """识别浏览器语言 / CDN 国家头，首次访问写 i18n_suggest cookie（或可选 302 跳转首页）"""

        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            try:
                if request.method != "GET":
                    return resp
                path = request.url.path
                first_seg = path.strip("/").split("/")[0].lower()
                if first_seg in DAWN_LANG_NAMES or path.startswith(("/lang/", "/dadmin", "/static", "/docs", "/feed", "/sitemap")) \
                        or "." in path.rsplit("/", 1)[-1]:
                    return resp
                cur_lang = request.cookies.get("site_lang")
                if cur_lang:
                    migrated = DAWN_LANG_MIGRATE.get(cur_lang)
                    if migrated and migrated != cur_lang:
                        resp.set_cookie("site_lang", migrated, max_age=180 * 86400, path="/", samesite="lax")
                    return resp
                cfg = await _dawn_get_config()
                if cfg.get("auto_detect", "1") != "1":
                    return resp
                if DAWN_BOT_UA.search(request.headers.get("user-agent", "")):
                    return resp
                avail = await _dawn_langs_with_translations()
                if not avail:
                    return resp
                accepts = _dawn_parse_accept_language(request.headers.get("accept-language", ""))
                country = (request.headers.get("cf-ipcountry") or request.headers.get("x-country-code") or "").lower()
                target = ""
                for al in accepts:
                    al = DAWN_LANG_MIGRATE.get(al, al)
                    for a in sorted(avail):
                        if a == al or a.split("-")[0] == al.split("-")[0]:
                            target = a
                            break
                    if target:
                        break
                if not target and country:
                    for a in sorted(avail):
                        if a.rsplit("-", 1)[-1] == country:
                            target = a
                            break
                if not target:
                    return resp
                if cfg.get("auto_redirect") == "1" and path in ("", "/"):
                    return RedirectResponse(f"/{target}", status_code=302)
                resp.set_cookie("i18n_suggest", target, max_age=180 * 86400, path="/", samesite="lax")
                return resp
            except Exception:
                return resp

    app.add_middleware(_I18nDetectMiddleware)

    @app.get("/dadmin/plugins/i18n")
    async def i18n_admin(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        cfg = await _dawn_get_config()
        langs = _dawn_lang_list(cfg)

        providers_json = json.dumps({p["key"]: p for p in DAWN_PROVIDERS}, ensure_ascii=False)
        provider_opts = [
            Option(p["label"], value=p["key"], selected=(p["key"] == cfg["provider"]))
            for p in DAWN_PROVIDERS
        ]
        cur_hint = next((p["hint"] for p in DAWN_PROVIDERS if p["key"] == cfg["provider"]),
                        DAWN_PROVIDERS[-1]["hint"])

        config_form = Div(
            Form(
                Div(
                    Div(Label("服务商预设", cls=DAWN_LABEL),
                        Select(*provider_opts, name="provider", id="i18n-provider", cls=DAWN_INPUT),
                        P("选择预设后自动填充 API 地址和模型建议，仍可手动修改；选「自定义」则完全自由填写",
                          cls="text-[11px] mt-1", style="color:var(--adm-faint)")),
                    Div(Label("API Base URL", cls=DAWN_LABEL),
                        Input(name="base_url", id="i18n-base-url", value=cfg["base_url"], cls=DAWN_INPUT),
                        P("兼容 OpenAI /chat/completions 的接口地址", id="i18n-url-hint",
                          cls="text-[11px] mt-1", style="color:var(--adm-faint)")),
                    Div(Label("API Key", cls=DAWN_LABEL),
                        Input(name="api_key", value=cfg["api_key"], type="password", cls=DAWN_INPUT),
                        P(cur_hint, id="i18n-key-hint", cls="text-[11px] mt-1", style="color:var(--adm-faint)")),
                    Div(Label("模型", cls=DAWN_LABEL),
                        Input(name="model", id="i18n-model", value=cfg["model"],
                              list="i18n-model-list", cls=DAWN_INPUT),
                        DawnSafeHTML('<datalist id="i18n-model-list"></datalist>'),
                        P("输入时有该服务商的模型建议可直接选，也可手动填写任意模型名",
                          cls="text-[11px] mt-1", style="color:var(--adm-faint)")),
                    Div(Label("目标语言（逗号分隔）", cls=DAWN_LABEL),
                        Input(name="languages", value=cfg["languages"], placeholder="en,ja,ko", cls=DAWN_INPUT),
                        P("支持：" + "、".join(f"{k}={v}" for k, v in DAWN_LANG_NAMES.items()),
                          cls="text-[11px] mt-1", style="color:var(--adm-faint)")),
                    Div(Label("自动语言识别", cls=DAWN_LABEL),
                        Label(
                            Input(type="checkbox", name="auto_detect", value="1",
                                  checked=(cfg["auto_detect"] == "1"), cls="accent-indigo-500 mr-2"),
                            Span("识别浏览器语言 / CDN 国家头，弹条建议切换（推荐，SEO 安全）",
                                 cls="text-sm text-slate-300"),
                            cls="flex items-center mt-1"),
                        Label(
                            Input(type="checkbox", name="auto_redirect", value="1",
                                  checked=(cfg["auto_redirect"] == "1"), cls="accent-indigo-500 mr-2"),
                            Span("首页直接 302 跳转到检测语言（仅首次访问首页生效，自动跳过爬虫）",
                                 cls="text-sm text-slate-300"),
                            cls="flex items-center mt-2"),
                        P("浏览器语言取 Accept-Language 请求头；国家识别用 Cloudflare CF-IPCountry / X-Country-Code 头（站点在 CDN 后时免费可用，无需 IP 库）",
                          cls="text-[11px] mt-1.5", style="color:var(--adm-faint)")),
                    cls="grid grid-cols-1 md:grid-cols-2 gap-4"
                ),
                Button("保存配置", type="submit", cls=DAWN_BTN + " mt-4"),
                method="post", action="/dadmin/plugins/i18n/config"
            ),
            DawnSafeHTML(f"""<script>
(function(){{
  var DAWN_PROVIDERS = {providers_json};
  var sel = document.getElementById('i18n-provider');
  var urlIn = document.getElementById('i18n-base-url');
  var modelIn = document.getElementById('i18n-model');
  var dl = document.getElementById('i18n-model-list');
  var keyHint = document.getElementById('i18n-key-hint');
  function apply(key, force) {{
    var p = DAWN_PROVIDERS[key]; if (!p) return;
    if (p.base_url && (force || !urlIn.value)) urlIn.value = p.base_url;
    dl.innerHTML = (p.models || []).map(function(m){{return '<option value="'+m+'">'}}).join('');
    if ((p.models || []).length && force) modelIn.value = p.models[0];
    keyHint.textContent = p.hint || '';
  }}
  sel.addEventListener('change', function(){{ apply(sel.value, true); }});
  apply(sel.value, false);
}})();
</script>"""),
        )

        content = Div(
            _dawn_msg(msg) if msg else None,
            (Div(
                Div(f"⏳ 批量翻译进行中：{_dawn_job['done']} / {_dawn_job['total']}　{_dawn_job['current']}",
                    cls="text-sm font-semibold text-sky-300"),
                Script("setTimeout(function(){location.reload()},3000)"),
                cls="adm-card p-4 mb-4"
            ) if _dawn_job["running"] else None),
            Div(
                H2("后台界面语言", cls="text-white font-bold text-sm mb-3"),
                Form(
                    Select(
                        *[Option(v, value=k, selected=(k == _dawn_adm_lang_now())) for k, v in DAWN_ADMIN_LANGS_UI.items()],
                        name="lang", cls=DAWN_INPUT + " !w-56"),
                    Button("保存", type="submit", cls=DAWN_BTN + " !py-2 text-xs ml-3"),
                    method="post", action="/dadmin/plugins/i18n/admin-lang",
                    cls="flex items-center"),
                P("只影响后台界面文案（菜单/通用词），与前台访客语言无关。语言包位于 routes/admin/locales/，可自行增补 JSON。",
                  cls="text-[11px] mt-2", style="color:var(--adm-faint)"),
                cls="adm-card p-6 mb-5"),
            Div(H2("大模型 API 配置", cls="text-white font-bold text-sm mb-3"),
                config_form, cls="adm-card p-6 mb-5"),
            Div(
                H2("翻译操作入口", cls="text-white font-bold text-sm mb-3"),
                Div(
                    A("📝 文章列表", href="/dadmin/posts", cls=DAWN_BTN_GHOST + " inline-block"),
                    Span("每行显示各语言翻译状态，点状态徽章跳到编辑页译文面板；工具栏可一键翻译全部待译",
                         cls="text-xs ml-3", style="color:var(--adm-dim)"),
                    cls="mb-3 flex items-center"),
                Div(
                    A("✏️ 文章编辑页", href="/dadmin/posts", cls=DAWN_BTN_GHOST + " inline-block"),
                    Span("底部「多语言译文」面板：原文/译文 tab 同屏对照，独立保存、AI 重译先填框再确认",
                         cls="text-xs ml-3", style="color:var(--adm-dim)"),
                    cls="mb-3 flex items-center"),
                Div(
                    A("🗂 分类 / 系列 / 标签", href="/dadmin/categories", cls=DAWN_BTN_GHOST + " inline-block"),
                    Span("各列表行内直接填写/AI 翻译对应语言名称（标签在标签页同理）",
                         cls="text-xs ml-3", style="color:var(--adm-dim)"),
                    cls="flex items-center"),
                cls="adm-card p-6"),
        )
        return _dawn_admin_shell("i18n", content, title="多语言")

    @app.post("/dadmin/plugins/i18n/config")
    async def i18n_config_save(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        data = {k: str(form.get(k, "")).strip()
                for k in ("provider", "base_url", "api_key", "model", "languages")}
        data["auto_detect"] = "1" if form.get("auto_detect") else "0"
        data["auto_redirect"] = "1" if form.get("auto_redirect") else "0"
        await _dawn_save_config(data)
        return RedirectResponse("/dadmin/plugins/i18n?msg=配置已保存", status_code=303)

    @app.post("/dadmin/plugins/i18n/admin-lang")
    async def i18n_admin_lang(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        lang = str(form.get("lang", "zh-CN"))
        resp = RedirectResponse("/dadmin/plugins/i18n?msg=后台语言已切换", status_code=303)
        if lang in DAWN_ADMIN_LANGS_UI:
            resp.set_cookie("admin_lang", lang, max_age=180 * 86400, path="/", samesite="lax")
        return resp

    @app.post("/dadmin/plugins/i18n/api/save_translation")
    async def i18n_api_save(session, request):
        if not _dawn_require_admin(session):
            return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
        form = await request.form()
        post_id = int(form.get("post_id", 0) or 0)
        lang = str(form.get("lang", "")).strip()
        post = await DawnBlogService.get_post_by_id(post_id)
        if not post or lang not in _dawn_lang_list(await _dawn_get_config()):
            return JSONResponse({"ok": False, "error": "参数无效"})
        await _dawn_save_translation(post_id, lang,
                                str(form.get("title", "")), str(form.get("content_md", "")),
                                _dawn_source_hash(post), desc_md=str(form.get("desc_md", "")))
        return JSONResponse({"ok": True, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    @app.post("/dadmin/plugins/i18n/api/translate_one")
    async def i18n_api_translate(session, request):
        if not _dawn_require_admin(session):
            return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
        form = await request.form()
        post_id = int(form.get("post_id", 0) or 0)
        lang = str(form.get("lang", "")).strip()
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return JSONResponse({"ok": False, "error": "请先在多语言设置中配置 API Key"})
        post = await DawnBlogService.get_post_by_id(post_id)
        if not post:
            return JSONResponse({"ok": False, "error": "文章不存在"})
        if str(form.get("skip_fresh", "")) == "1":
            t = (await _dawn_get_translations(post_id)).get(lang)
            if t and t.get("status") == "done" and t.get("source_hash") == _dawn_source_hash(post):
                return JSONResponse({"ok": True, "skipped": True})
        try:
            title, desc, content_md = await _dawn_translate_post(cfg, post, lang)
            await _dawn_save_translation(post_id, lang, title, content_md, _dawn_source_hash(post), desc_md=desc)
            return JSONResponse({"ok": True, "title": title, "desc_md": desc, "content_md": content_md})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)[:200]})

    @app.post("/dadmin/plugins/i18n/api/taxonomy_save")
    async def i18n_api_tax_save(session, request):
        if not _dawn_require_admin(session):
            return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
        form = await request.form()
        kind, lang = str(form.get("kind", "")), str(form.get("lang", "")).strip()
        if kind not in ("category", "series", "tag") or lang not in _dawn_lang_list(await _dawn_get_config()):
            return JSONResponse({"ok": False, "error": "参数无效"})
        await _dawn_save_taxonomy(kind, int(form.get("source_id", 0) or 0), lang,
                             str(form.get("name", "")).strip(), str(form.get("description", "")))
        return JSONResponse({"ok": True})

    @app.post("/dadmin/plugins/i18n/api/taxonomy_translate")
    async def i18n_api_tax_translate(session, request):
        if not _dawn_require_admin(session):
            return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
        form = await request.form()
        kind, source_id, lang = str(form.get("kind", "")), int(form.get("source_id", 0) or 0), str(form.get("lang", "")).strip()
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return JSONResponse({"ok": False, "error": "请先配置 API Key"})
        source = None
        if kind == "category":
            source = next((c for c in await DawnBlogService.get_categories() if c.get("id") == source_id), None)
        elif kind == "series":
            source = next((x for x in await DawnBlogService.get_series() if x.get("id") == source_id), None)
        elif kind == "tag":
            source = next((x for x in await DawnBlogService.list_tags() if x.get("id") == source_id), None)
        if not source:
            return JSONResponse({"ok": False, "error": "对象不存在"})
        try:
            name = await _dawn_llm_translate(cfg, source.get("name", ""), lang, is_title=True)
            return JSONResponse({"ok": True, "name": name.strip()})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)[:200]})

    @app.post("/dadmin/plugins/i18n/translate")
    async def i18n_translate(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        post_id, lang = int(form.get("post_id", 0)), str(form.get("lang", ""))
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)
        post = await DawnBlogService.get_post_by_id(post_id)
        if not post:
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)
        try:
            title, desc, content_md = await _dawn_translate_post(cfg, post, lang)
            await _dawn_save_translation(post_id, lang, title, content_md, _dawn_source_hash(post), desc_md=desc)
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)
        except Exception as e:
            await _dawn_save_translation(post_id, lang, "", "", "", status="failed", error=str(e)[:300])
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)

    @app.post("/dadmin/plugins/i18n/translate_all")
    async def i18n_translate_all(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return RedirectResponse("/dadmin/plugins/i18n?msg=请先配置 API Key", status_code=303)
        if _dawn_job["running"]:
            return RedirectResponse("/dadmin/plugins/i18n?msg=批量翻译正在进行中", status_code=303)
        _dawn_job["running"] = True
        asyncio.create_task(_dawn_run_translate_job())
        return RedirectResponse("/dadmin/plugins/i18n?msg=批量翻译已启动，页面将自动刷新进度", status_code=303)

    @app.post("/dadmin/plugins/i18n/translate_post_all")
    async def i18n_translate_post_all(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        post_id = int(form.get("post_id", 0))
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)
        if _dawn_job["running"]:
            return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)
        _dawn_job["running"] = True
        asyncio.create_task(_dawn_run_translate_job(post_ids={post_id}))
        return RedirectResponse(_dawn_back(request, "/dadmin/posts"), status_code=303)

    @app.get("/dadmin/plugins/i18n/view/{post_id}/{lang}")
    async def i18n_view(session, post_id: int, lang: str):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        post = await DawnBlogService.get_post_by_id(post_id)
        translations = await _dawn_get_translations(post_id)
        t = translations.get(lang)
        if not post or not t:
            return RedirectResponse("/dadmin/plugins/i18n?msg=译文不存在", status_code=303)

        stale = t.get("source_hash") and t.get("source_hash") != _dawn_source_hash(post)
        html = DawnMarkdownRenderer.render_with_prose(t.get("content_md") or "")
        front_url = f"/{lang}/{post.get('slug', '')}"

        meta_rows = Div(
            Div(Span("语言", cls="text-xs", style="color:var(--adm-faint)"),
                Span(f"{DAWN_LANG_NAMES.get(lang, lang)}（{lang}）", cls="text-sm ml-2 text-slate-200"), cls="py-1.5"),
            Div(Span("状态", cls="text-xs", style="color:var(--adm-faint)"),
                Span("⚠️ 原文已变更，建议重译" if stale else ("✅ 翻译完成" if t.get("status") == "done" else "❌ " + t.get("error", "失败")),
                     cls=f"text-sm ml-2 {'text-amber-400' if stale else ('text-emerald-400' if t.get('status') == 'done' else 'text-red-400')}"),
                cls="py-1.5"),
            Div(Span("更新时间", cls="text-xs", style="color:var(--adm-faint)"),
                Span(t.get("updated_at", ""), cls="text-sm ml-2 text-slate-400"), cls="py-1.5"),
            cls="mb-4"
        )

        content = Div(
            Div(
                A("← 返回多语言管理", href="/dadmin/plugins/i18n",
                  cls="text-xs", style="color:var(--adm-dim)"),
                cls="mb-4"
            ),
            meta_rows,
            Div(
                Div(
                    H3("译文标题", cls="text-xs font-bold mb-2", style="color:var(--adm-faint)"),
                    Div(t.get("title", ""), cls="text-white font-bold text-lg"),
                    cls="adm-card p-5 mb-4"
                ),
                Div(
                    Div(
                        H3("前台渲染效果", cls="text-xs font-bold", style="color:var(--adm-faint)"),
                        A("🔗 前台打开", href=front_url, cls="text-xs text-indigo-400 hover:text-indigo-300"),
                        cls="flex items-center justify-between mb-2"
                    ),
                    Div(DawnSafeHTML(html), cls="rounded-lg p-5",
                        style="background:var(--adm-bg);border:1px solid var(--adm-line)"),
                    cls="adm-card p-5 mb-4"
                ),
                Div(
                    H3("Markdown 源文", cls="text-xs font-bold mb-2", style="color:var(--adm-faint)"),
                    Pre(t.get("content_md", ""), cls="text-xs text-slate-300 whitespace-pre-wrap rounded-lg p-4",
                        style="background:var(--adm-bg);border:1px solid var(--adm-line)"),
                    cls="adm-card p-5"
                ),
            ),
        )
        return _dawn_admin_shell("i18n", content, title=f"译文预览 · {post.get('title', '')[:20]}")

    @app.post("/dadmin/plugins/i18n/taxonomy/save")
    async def i18n_taxonomy_save(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        await _dawn_save_taxonomy(str(form.get("kind", "")), int(form.get("source_id", 0)),
                             str(form.get("lang", "")), str(form.get("name", "")).strip())
        return RedirectResponse(_dawn_back(request, "/dadmin/categories"), status_code=303)

    @app.post("/dadmin/plugins/i18n/taxonomy/translate")
    async def i18n_taxonomy_translate(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        kind, source_id, lang = str(form.get("kind", "")), int(form.get("source_id", 0)), str(form.get("lang", ""))
        cfg = await _dawn_get_config()
        if not cfg.get("api_key"):
            return RedirectResponse(_dawn_back(request, "/dadmin/categories"), status_code=303)
        source = None
        if kind == "category":
            source = next((c for c in await DawnBlogService.get_categories() if c.get("id") == source_id), None)
        elif kind == "series":
            source = next((s for s in await DawnBlogService.get_series() if s.get("id") == source_id), None)
        elif kind == "tag":
            source = next((t for t in await DawnBlogService.list_tags() if t.get("id") == source_id), None)
        if not source:
            return RedirectResponse(_dawn_back(request, "/dadmin/categories"), status_code=303)
        try:
            name = await _dawn_llm_translate(cfg, source.get("name", ""), lang, is_title=True)
            desc = ""
            if (source.get("description") or "").strip():
                desc = await _dawn_llm_translate(cfg, source["description"], lang, is_title=True)
            await _dawn_save_taxonomy(kind, source_id, lang, name.strip(), desc.strip())
            return RedirectResponse(_dawn_back(request, "/dadmin/categories"), status_code=303)
        except Exception as e:
            return RedirectResponse(_dawn_back(request, "/dadmin/categories"), status_code=303)

    @app.post("/dadmin/plugins/i18n/delete")
    async def i18n_delete(session, request):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        post_id, lang = int(form.get("post_id", 0)), str(form.get("lang", ""))
        await _dawn_ensure_tables()
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM plugin_i18n_translations WHERE post_id=? AND lang=?", (post_id, lang))
        await db.commit()
        await db.close()
        return RedirectResponse("/dadmin/plugins/i18n?msg=已删除翻译", status_code=303)

    # ---------- 前台翻译页 ----------

    async def _front_ctx(session, title="", desc="", lang=""):
        from ui.dawn_layout import dawn_get_nav_links
        if lang:
            # 导航镜像中文站：同一批 nav_links，label 走语言表翻译，站内 URL 加语言前缀
            _NAV_KEYS = {"首页": "home_label", "关于": "about_label", "文档": "docs_label"}
            nav = []
            for link in dawn_get_nav_links("header"):
                label, url = str(link.get("label", "")), str(link.get("url", ""))
                key = _NAV_KEYS.get(label)
                if key:
                    label = _dawn_lt(lang, key) or label
                if url.startswith("/") and not url.startswith(f"/{lang}"):
                    url = f"/{lang}" if url == "/" else f"/{lang}{url}"
                nav.append({**link, "label": label, "url": url})
        else:
            nav = dawn_get_nav_links("header")
        try:
            from dawn_config import dawn_site_tagline
            tagline = dawn_site_tagline()
        except ImportError:
            tagline = ""
        base = {
            "site_name": dawn_site_name(), "site_tagline": (_dawn_lt(lang, "site_tagline") or tagline) if lang else tagline,
            "site_base_url": DAWN_SITE_BASE_URL.rstrip("/"),
            "page_title": f"{title} - {dawn_site_name()}" if title else dawn_site_name(),
            "page_desc": desc or tagline,
            "canonical": "",
            "og_locale": (_dawn_hreflang_code(lang).replace("-", "_") if lang else "zh_CN"),
            "og_locale_alternates": (["zh_CN"] if lang else []),
            "year": datetime.now().strftime("%Y"),
            "nav": nav,
            "footer_nav": ([{"label": "中文首页", "url": "/"},
                            {"label": f"RSS · {DAWN_LANG_NAMES.get(lang, lang)}", "url": f"/{lang}/feed.xml"},
                            {"label": "Admin", "url": "/dadmin"}] if lang else dawn_get_nav_links("footer")),
            "member_name": (session or {}).get("member_name", ""),
            "is_admin": bool((session or {}).get("is_admin")),
            "theme_css": dawn_themes.dawn_theme_root_css(),
            "base_css": dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/base.css", DAWN_BASE_CSS)
                        + "\n" + dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/list.css", DAWN_LIST_CSS),
            "doc_css": dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/doc.css", DAWN_DOC_CSS),
            "layout_css": dawn_themes.dawn_layout_override_css(),
            "layout_mode": dawn_themes.dawn_get_layout_mode(),
            "page_width": dawn_themes.dawn_theme_settings().get("page_width", "Page width"),
            "home_sections": dawn_themes.dawn_theme_home_sections(),
            "global_js": "",
            "site_schema": "",
            "og_image": f"{DAWN_SITE_BASE_URL.rstrip('/')}/static/logo.svg",
        }
        base["_lang"] = lang
        return base

    async def _translated_posts(lang: str, category_name: str = "") -> list:
        """该语言全部已发布公开译文（可按分类名过滤），含译名/译摘要回退"""
        await _dawn_ensure_tables()
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        sql = """SELECT t.title AS t_title, t.desc_md AS t_desc, p.slug, p.title, p.created_at,
                        p.category, p.description, p.cover_image, p.id AS post_id,
                        p.read_time, p.view_count
                 FROM plugin_i18n_translations t JOIN posts p ON p.id = t.post_id
                 WHERE t.lang=? AND t.status='done' AND p.is_published=1 AND p.visibility='public'"""
        args = [lang]
        if category_name:
            sql += " AND p.category=?"
            args.append(category_name)
        sql += " ORDER BY p.created_at DESC"
        rows = await (await db.execute(sql, args)).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    async def _translated_docs_groups(lang: str, current_slug: str = "") -> list:
        """翻译版文档侧栏分组（与中文版 _dawn_docs_groups 同构）：分类在前、连载在后，每组 6 篇，URL 指向译文页"""
        categories = await DawnBlogService.get_categories()
        cat_names = await _dawn_tax_names("category", lang)
        series_names = await _dawn_tax_names("series", lang)
        all_trans = await _translated_posts(lang)
        groups = []
        for c in categories:
            asc = bool(c.get("is_series"))
            posts = sorted((r for r in all_trans if (r.get("category") or "") == c.get("name", "")),
                           key=lambda x: x.get("created_at", ""), reverse=not asc)[:6]
            if not posts:
                continue
            groups.append({
                "name": cat_names.get(c.get("id")) or c.get("name", ""),
                "slug": c.get("slug", ""), "is_series": asc,
                "url": f"/{lang}/c/{c.get('slug', '')}",
                "posts": [{"title": r.get("t_title") or r.get("title", ""),
                           "url": f"/{lang}/{r.get('slug', '')}",
                           "current": bool(current_slug) and r.get("slug") == current_slug} for r in posts],
            })
        try:
            for se in await DawnBlogService.get_series():
                sp = await DawnBlogService.get_series_posts(se.get("id"))
                order = {x.get("id"): i for i, x in enumerate(sp)}
                group = [r for r in all_trans if r.get("post_id") in order]
                group.sort(key=lambda r: order[r.get("post_id")])
                if not group:
                    continue
                groups.append({
                    "name": series_names.get(se.get("id")) or se.get("name", ""),
                    "slug": se.get("slug", ""), "is_series": True,
                    "url": f"/{lang}/s/{se.get('slug', '')}",
                    "posts": [{"title": r.get("t_title") or r.get("title", ""),
                               "url": f"/{lang}/{r.get('slug', '')}",
                               "current": bool(current_slug) and r.get("slug") == current_slug} for r in group[:6]],
                })
        except Exception as e:
            print(f"[i18n] 侧栏系列分组失败: {e}")
        return groups

    async def _list_page(session, lang, posts, categories, current_cat="", page=1,
                         series=None, tag=None, notice="", title="", desc="", canonical="",
                         base_url="", page_type="home", slug="", cat_slug=""):
        """翻译版列表页：与中文版共用 list.html，布局/结构完全一致"""
        cat_names = await _dawn_tax_names("category", lang)
        tag_names = await _dawn_tax_names("tag", lang)
        series_names = await _dawn_tax_names("series", lang)
        cat_id_by_name = {c.get("name"): c.get("id") for c in categories}

        tag_map = {}
        ids = [r.get("post_id") for r in posts if r.get("post_id")]
        if ids:
            try:
                raw = await DawnBlogService.get_tags_for_posts(ids)
                for pid, tlist in (raw or {}).items():
                    tag_map[pid] = [{"name": tag_names.get(t.get("id")) or t.get("name", "")} for t in tlist]
            except Exception:
                pass

        def card(r):
            d = r.get("t_desc") or r.get("description") or ""
            cid = cat_id_by_name.get(r.get("category"), 0)
            return {
                "url": f"/{lang}/{r.get('slug', '')}",
                "title": r.get("t_title") or r.get("title", ""),
                "desc": d[:110] + ("…" if len(d) > 110 else ""),
                "cover": dawn_cover_url(r),
                "category": cat_names.get(cid) or r.get("category", ""),
                "date": (r.get("created_at") or "")[:10],
                "read_time": _dawn_localize_read_time(r.get("read_time", ""), lang),
                "views": r.get("view_count", 0),
                "member": False,
                "tags": tag_map.get(r.get("post_id"), []),
            }

        if series:
            order = {}
            try:
                order = {sp.get("id"): (sp.get("series_order") or 0)
                         for sp in await DawnBlogService.get_series_posts(series.get("id"))}
            except Exception:
                pass
            sorted_posts = sorted(posts, key=lambda r: (0, order.get(r.get("post_id"), 0))
                                  if order.get(r.get("post_id"), 0) > 0 else (1, r.get("created_at", "")))
        else:
            sorted_posts = sorted(posts, key=lambda r: r.get("created_at", ""), reverse=True)

        per_page = 12
        page = max(1, page)
        total = len(sorted_posts)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        paged = sorted_posts[(page - 1) * per_page: page * per_page]

        cat_counts = {}
        for r in posts:
            cat_counts[r.get("category") or "未分类"] = cat_counts.get(r.get("category") or "未分类", 0) + 1
        cats = [{"slug": c.get("slug", ""), "name": cat_names.get(c.get("id")) or c.get("name", ""),
                 "count": cat_counts.get(c.get("name", ""), 0),
                 "url": f"/{lang}/c/{c.get('slug', '')}"} for c in categories]

        lang_switch = await _dawn_lang_switch_entries(page_type, slug, cat_slug, current=lang)
        home_url = f"/{lang}"

        if not paged:
            ctx = await _front_ctx(session, title=title, desc=desc, lang=lang)
            ctx.update({
                "canonical": canonical, "empty": True, "empty_msg": _dawn_lt(lang, "empty"),
                "cats": cats, "current_cat": current_cat, "q": "",
                "home_url": home_url, "search_action": "", "html_lang": _dawn_hreflang_code(lang),
                "lang_switch": lang_switch,
            })
            return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("list.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

        if series:
            heading = series_names.get(series.get("id")) or series.get("name", "")
            sub_line = series.get("description") or _dawn_lt(lang, "series_sub").format(n=total)
        elif tag:
            heading = f"#{tag_names.get(tag.get('id')) or tag.get('name', '')}"
            sub_line = _dawn_lt(lang, "tag_sub").format(n=total)
        elif current_cat:
            cur = next((c for c in categories if c.get("slug") == current_cat), None)
            heading = (cat_names.get(cur.get("id")) or cur.get("name", "")) if cur else current_cat
            sub_line = _dawn_lt(lang, "cat_sub").format(n=total)
        else:
            heading = dawn_site_name()
            sub_line = _dawn_lt(lang, "portal_sub").format(n=total)

        # 侧栏分组：分类（含连载标记）+ 连载系列，与中文版同构
        all_trans = await _translated_posts(lang)
        by_cat = {}
        for r in all_trans:
            by_cat.setdefault(r.get("category") or "未分类", []).append(r)
        cat_groups = []
        for c in categories:
            asc = bool(c.get("is_series"))
            group = sorted(by_cat.get(c.get("name", ""), []),
                           key=lambda x: x.get("created_at", ""), reverse=not asc)[:6]
            if not group:
                continue
            cat_groups.append({
                "name": cat_names.get(c.get("id")) or c.get("name", ""),
                "slug": c.get("slug", ""), "is_series": asc,
                "url": f"/{lang}/c/{c.get('slug', '')}",
                "posts": [{"title": r.get("t_title") or r.get("title", ""),
                           "url": f"/{lang}/{r.get('slug', '')}"} for r in group],
            })
        series_groups = []
        try:
            for se in await DawnBlogService.get_series():
                sp = await DawnBlogService.get_series_posts(se.get("id"))
                order = {x.get("id"): i for i, x in enumerate(sp)}
                group = [r for r in all_trans if r.get("post_id") in order]
                group.sort(key=lambda r: order[r.get("post_id")])
                if not group:
                    continue
                series_groups.append({
                    "name": series_names.get(se.get("id")) or se.get("name", ""),
                    "slug": se.get("slug", ""), "is_series": True,
                    "url": f"/{lang}/s/{se.get('slug', '')}",
                    "posts": [{"title": r.get("t_title") or r.get("title", ""),
                               "url": f"/{lang}/{r.get('slug', '')}"} for r in group[:6]],
                })
        except Exception as e:
            print(f"[i18n] 系列分组失败: {e}")

        ctx = await _front_ctx(session, title=title, desc=desc, lang=lang)
        ctx.update({
            "canonical": canonical, "heading": heading, "sub_line": sub_line,
            "notice": notice, "q": "", "cats": cats, "current_cat": current_cat,
            "cat_groups": cat_groups, "series_groups": series_groups,
            "docs_groups": await _translated_docs_groups(lang),
            "series_mode": bool(series), "per_page": per_page,
            "featured": card(paged[0]) if paged else None,
            "recent": [card(r) for r in paged[1:5]],
            "posts": [card(r) for r in paged],
            "page": page, "pages": total_pages, "total": total,
            "base_url": base_url,
            "extra_head": (await _dawn_list_hreflang(page_type, slug, cat_slug)),
            "home_url": home_url, "search_action": "", "html_lang": _dawn_hreflang_code(lang),
            "lang_switch": lang_switch,
            "is_home": page_type == "home",
        })
        return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("list.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

    async def _portal(lang: str, session, page: int = 1, subscribed: str = "", subscribe_error: str = ""):
        """翻译版首页：与中文版同布局（list.html），内容为该语言译文"""
        posts = await _translated_posts(lang)
        if not posts:
            raise HTTPException(status_code=404)
        notice = ""
        if subscribed:
            notice = "✅ Subscribed! New posts will be emailed to you" if lang == "en" else "✅ 订阅成功"
        elif subscribe_error:
            notice = "Invalid email address, please try again" if lang == "en" else "邮箱格式不正确，请重试"
        categories = await DawnBlogService.get_categories()
        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        return await _list_page(session, lang, posts, categories, page=page, notice=notice,
                                title="", desc=(_dawn_lt(lang, "site_tagline") or dawn_site_tagline()),
                                canonical=f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}",
                                base_url=f"/{lang}?page=", page_type="home")

    async def _category(lang: str, cat_slug: str, session, page: int = 1):
        """分类译文列表页（与中文分类页同布局）"""
        categories = await DawnBlogService.get_categories()
        cat = next((c for c in categories if c.get("slug") == cat_slug), None)
        if not cat:
            raise HTTPException(status_code=404)
        posts = await _translated_posts(lang, cat.get("name", ""))
        cat_names = await _dawn_tax_names("category", lang)
        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        cat_label = cat_names.get(cat.get("id")) or cat.get("name", "")
        return await _list_page(session, lang, posts, categories, current_cat=cat_slug, page=page,
                                title=f"{cat_label} - {lang_name}", desc=cat.get("description", ""),
                                canonical=f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/c/{cat_slug}",
                                base_url=f"/{lang}/c/{cat_slug}?page=",
                                page_type="category", cat_slug=cat_slug)

    async def _feed(lang: str):
        """该语言的 RSS 订阅源"""
        from xml.sax.saxutils import escape
        posts = await _translated_posts(lang)
        if not posts:
            raise HTTPException(status_code=404)
        base = DAWN_SITE_BASE_URL.rstrip("/")
        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        items = []
        for r in posts[:50]:
            link = f"{base}/{lang}/{r['slug']}"
            items.append(
                f"<item><title>{escape(r.get('t_title') or r.get('title', ''))}</title>"
                f"<link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
                f"<description>{escape(r.get('t_desc') or r.get('description') or '')}</description>"
                f"<category>{escape(r.get('category', ''))}</category>"
                f"<pubDate>{(r.get('created_at') or '')[:19]}</pubDate></item>"
            )
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
               f"<title>{escape(dawn_site_name())} · {escape(lang_name)}</title>"
               f"<link>{base}/{lang}</link>"
               f"<description>{escape(dawn_site_name())} {escape(lang_name)}</description>"
               f"<language>{escape(lang)}</language>"
               + "".join(items) + "</channel></rss>")
        return Response(xml, media_type="application/rss+xml")

    async def _series(lang: str, series_slug: str, session, page: int = 1):
        """系列译文页（与中文系列页同布局，连载顺序）"""
        series = await DawnBlogService.get_series_by_slug(series_slug)
        if not series:
            raise HTTPException(status_code=404)
        series_posts = await DawnBlogService.get_series_posts(series.get("id"))
        ids = {sp.get("id") for sp in series_posts}
        posts = [r for r in await _translated_posts(lang) if r.get("post_id") in ids]
        tax_map = await _dawn_get_taxonomy_map()
        tr = tax_map.get(("series", series.get("id"), lang), {})
        sname = tr.get("name") or series.get("name", "")
        sdesc = tr.get("description") or series.get("description", "")
        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        return await _list_page(session, lang, posts, await DawnBlogService.get_categories(), page=page,
                                series={**series, "description": sdesc},
                                title=f"{sname} - {lang_name}", desc=sdesc or sname,
                                canonical=f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/s/{series_slug}",
                                base_url=f"/{lang}/s/{series_slug}?page=",
                                page_type="series", slug=series_slug)

    async def _tag(lang: str, tag_slug: str, session, page: int = 1):
        """标签译文页（与中文标签页同布局）"""
        tag = await DawnBlogService.get_tag_by_slug(tag_slug)
        if not tag:
            raise HTTPException(status_code=404)
        tag_posts = await DawnBlogService.get_posts_by_tag_slug(tag_slug)
        ids = {tp.get("id") for tp in tag_posts}
        posts = [r for r in await _translated_posts(lang) if r.get("post_id") in ids]
        tag_names = await _dawn_tax_names("tag", lang)
        tname = tag_names.get(tag.get("id")) or tag.get("name", "")
        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        return await _list_page(session, lang, posts, await DawnBlogService.get_categories(), page=page,
                                tag=tag,
                                title=f"#{tname} - {lang_name}", desc=tname,
                                canonical=f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/t/{tag_slug}",
                                base_url=f"/{lang}/t/{tag_slug}?page=",
                                page_type="tag", slug=tag_slug)

    async def _post(lang: str, slug: str, session):
        is_admin = bool((session or {}).get("is_admin"))
        is_member = bool((session or {}).get("member_id"))
        article = await DawnBlogService.get_post(slug, is_admin=is_admin, is_member=is_member)
        if not article:
            raise HTTPException(status_code=404)
        if article.get("gated"):
            categories = await DawnBlogService.get_categories()
            return RedirectResponse(dawn_post_url(article, categories), status_code=302)

        translations = await _dawn_get_translations(article.get("id", 0))
        t = translations.get(lang)
        if not t or t.get("status") != "done":
            raise HTTPException(status_code=404)

        categories = await DawnBlogService.get_categories()
        original_url = f"{DAWN_SITE_BASE_URL.rstrip('/')}{dawn_post_url(article, categories)}"
        html = DawnMarkdownRenderer.render_with_prose(t.get("content_md") or "")
        toc_items, html_with_ids = dawn_extract_toc_and_anchors(html)

        lang_name = DAWN_LANG_NAMES.get(lang, lang)
        done_langs = [l for l, tr in translations.items() if tr.get("status") == "done"]
        hreflang = _dawn_hreflang_links(original_url, slug, translations, done_langs)
        switcher_parts = [
            f'<a href="{original_url}" style="font-weight:600;text-decoration:underline">中文</a>'
        ]
        for other in sorted(done_langs):
            if other == lang:
                continue
            switcher_parts.append(
                f'<a href="/{other}/{slug}" style="font-weight:600">{DAWN_LANG_NAMES.get(other, other)}</a>')
        _BANNER_T = {
            "en-us": "🌐 This post was machine-translated into English, for reference only. Switch language: ",
            "ja-jp": "🌐 この記事は AI により日本語に翻訳されました。言語切替：",
            "zh-tw": "🌐 本文由大模型翻譯為繁體中文，僅供參考。切換語言：",
        }
        banner = (_BANNER_T.get(lang) or f"🌐 本文由大模型翻译为 {lang_name}，仅供参考。切换语言：") \
            + " · ".join(switcher_parts)
        a = {
            "title": t.get("title") or article.get("title", ""),
            "desc": t.get("desc_md") or article.get("description", ""),
            "category": article.get("category", ""),
            "category_slug": dawn_category_slug_map(categories).get(article.get("category", ""), "uncategorized"),
            "date": (article.get("created_at", "") or "")[:10],
            "author": article.get("author", ""),
            "cover": dawn_cover_url(article),
            "cover_abs": dawn_cover_url(article),
            "read_time": article.get("read_time", ""),
            "views": article.get("view_count", 0),
        }

        # 标签：译名 + 翻译版标签页链接
        post_tags = await DawnBlogService.get_post_tags(article.get("id", 0))
        tag_names = await _dawn_tax_names("tag", lang)
        tags = [{"name": tag_names.get(t.get("id")) or t.get("name", ""),
                 "slug": t.get("slug", ""), "url": f"/{lang}/t/{t.get('slug', '')}"}
                for t in post_tags]

        # 连载：译名 + 翻译版系列页链接 + 系列内译文导航
        series_info, series_block = None, None
        sid = article.get("series_id") or 0
        if sid:
            series = await DawnBlogService.get_series_by_id(sid)
            if series:
                series_names = await _dawn_tax_names("series", lang)
                sname = series_names.get(series.get("id")) or series.get("name", "")
                surl = f"/{lang}/s/{series.get('slug', '')}"
                series_info = {"name": sname, "slug": series.get("slug", ""), "url": surl}
                sposts = await DawnBlogService.get_series_posts(sid)
                tmap = {r.get("post_id"): r for r in await _translated_posts(lang)}
                items = [{"url": f"/{lang}/{tmap[p['id']]['slug']}",
                          "title": tmap[p["id"]].get("t_title") or tmap[p["id"]].get("title", ""),
                          "current": p.get("id") == article.get("id")}
                         for p in sposts if p.get("id") in tmap]
                if items:
                    series_block = {"name": sname, "slug": series.get("slug", ""), "url": surl, "posts": items}

        # 相关文章：同分类其他译文
        related = [{"url": f"/{lang}/{r['slug']}",
                    "title": r.get("t_title") or r.get("title", ""),
                    "cover": dawn_cover_url(r),
                    "date": (r.get("created_at") or "")[:10],
                    "desc": r.get("t_desc") or r.get("description") or ""}
                   for r in await _translated_posts(lang, article.get("category", ""))
                   if r.get("post_id") != article.get("id")][:3]

        # 左栏专栏导航（与中文版同构：全分类 + 译名 + 译文链接）
        all_trans = await _translated_posts(lang)
        cat_names = await _dawn_tax_names("category", lang)
        cur_cat_obj0 = next((c for c in categories if c.get("name") == article.get("category")), None)
        if cur_cat_obj0:
            a["category"] = cat_names.get(cur_cat_obj0.get("id")) or a["category"]
        a["read_time"] = _dawn_localize_read_time(a.get("read_time", ""), lang)
        a["author"] = DAWN_AUTHOR_T.get(lang) or a.get("author", "")
        by_cat = {}
        for r in all_trans:
            by_cat.setdefault(r.get("category") or "未分类", []).append(r)
        current_cat_obj = next((c for c in categories if c.get("name") == article.get("category")), None)
        rail_cats = []
        for cat in categories:
            cat_asc = bool(cat.get("is_series"))
            cps = sorted(by_cat.get(cat.get("name", ""), []),
                         key=lambda x: x.get("created_at", ""), reverse=not cat_asc)[:10]
            rail_cats.append({
                "name": cat_names.get(cat.get("id")) or cat.get("name", "未分类"),
                "slug": cat.get("slug", "uncategorized"),
                "open": bool(current_cat_obj and current_cat_obj.get("slug") == cat.get("slug")),
                "is_series": cat_asc,
                "posts": [{"url": f"/{lang}/{r.get('slug', '')}",
                           "title": r.get("t_title") or r.get("title", ""),
                           "current": r.get("slug") == slug} for r in cps],
            })
        a["dawn_category_url"] = f"/{lang}/c/{a['category_slug']}"

        def _r_nav(r):
            return {"url": f"/{lang}/{r.get('slug', '')}",
                    "title": r.get("t_title") or r.get("title", "")} if r else None

        prev_nav, next_nav = None, None
        if series_block:
            sps = series_block["posts"]
            s_i = next((i for i, p in enumerate(sps) if p.get("current")), -1)
            prev_nav = sps[s_i - 1] if s_i > 0 else None
            next_nav = sps[s_i + 1] if 0 <= s_i + 1 < len(sps) else None
        else:
            cat_is_series = bool(current_cat_obj and current_cat_obj.get("is_series"))
            cps = sorted(by_cat.get(article.get("category", ""), []),
                         key=lambda x: x.get("created_at", ""), reverse=not cat_is_series)
            c_i = next((i for i, p in enumerate(cps) if p.get("slug") == slug), -1)
            if cat_is_series:
                prev_nav = _r_nav(cps[c_i - 1]) if c_i > 0 else None
                next_nav = _r_nav(cps[c_i + 1]) if 0 <= c_i + 1 < len(cps) else None
            else:
                prev_nav = _r_nav(cps[c_i + 1]) if 0 <= c_i + 1 < len(cps) else None
                next_nav = _r_nav(cps[c_i - 1]) if c_i > 0 else None

        ctx = await _front_ctx(session, title=a["title"], desc=a["desc"], lang=lang)
        self_url = f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/{slug}"
        a["jsonld_article"] = json.dumps({
            "@context": "https://schema.org", "@type": "Article",
            "headline": a["title"], "description": a["desc"],
            "inLanguage": _dawn_hreflang_code(lang),
            "author": {"@type": "Person", "name": a.get("author") or "站长"},
            "publisher": {"@type": "Organization", "name": dawn_site_name()},
            "datePublished": article.get("created_at", ""),
            "dateModified": article.get("updated_at", article.get("created_at", "")),
            "mainEntityOfPage": self_url, "articleSection": a.get("category", ""),
        }, ensure_ascii=False)
        ctx.update({
            "canonical": self_url,
            "a": a, "content": html_with_ids, "toc": toc_items,
            "tags": tags, "prev": prev_nav, "next": next_nav, "related": related,
            "rail_cats": rail_cats, "series_block": series_block, "series_info": series_info,
            "docs_groups": await _translated_docs_groups(lang, current_slug=slug),
            "jsonld_article": a["jsonld_article"], "jsonld_breadcrumb": "", "jsonld_itemlist": "",
            "doc_js": dawn_themes.dawn_chain_asset_text(dawn_themes.dawn_get_package(dawn_themes.dawn_get_active_theme_key()), "core/doc.js", DAWN_DOC_JS), "article_banner": banner, "extra_head": hreflang,
            "home_url": f"/{lang}", "html_lang": _dawn_hreflang_code(lang),
            "lang_switch": await _dawn_lang_switch_entries("article", slug=slug, current=lang),
        })
        return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("post.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

    # ---- 路由注册：BCP 47 区域码逐语言显式注册（避免与中文分类 /{cat_slug} 冲突）----
    def _reg_lang_routes(code):
        @app.get(f"/{code}/")
        async def _p_slash():
            return RedirectResponse(f"/{code}", status_code=301)

        @app.get(f"/{code}")
        async def _p(session, page: int = 1, subscribed: str = "", subscribe_error: str = ""):
            return await _portal(code, session, page, subscribed, subscribe_error)

        @app.get(f"/{code}/c/{'{cat_slug}'}")
        async def _c(cat_slug: str, session, page: int = 1):
            return await _category(code, cat_slug, session, page)

        @app.get(f"/{code}/s/{'{series_slug}'}")
        async def _s(series_slug: str, session, page: int = 1):
            return await _series(code, series_slug, session, page)

        @app.get(f"/{code}/t/{'{tag_slug}'}")
        async def _t(tag_slug: str, session, page: int = 1):
            return await _tag(code, tag_slug, session, page)

        @app.get(f"/{code}/feed.xml")
        async def _f():
            return await _feed(code)

        @app.get(f"/{code}/about")
        async def _ab(session):
            return await _about_page(code, session)

        @app.get(f"/{code}/docs")
        async def _di(session):
            return await _docs_index(code, session)

        @app.get(f"/{code}/docs/{'{slug}'}")
        async def _da(slug: str, session):
            return await _docs_article(code, slug, session)

        @app.get(f"/{code}/{'{slug}'}")
        async def _a(slug: str, session):
            return await _post(code, slug, session)

        for _n, _fn in (("portal", _p), ("category", _c), ("series", _s),
                        ("tag", _t), ("feed", _f), ("post", _a)):
            _fn.__qualname__ = f"i18n_{_n}_{code.replace('-', '_')}"

    for _code in DAWN_LANG_NAMES:
        _reg_lang_routes(_code)

    # ---- About / Docs 翻译版（与中文站导航镜像的落地页）----

    _DAWN_ABOUT_HTML_EN = """
<div class="text-center mb-4">
  <span class="eyebrow block mb-5">About</span>
  <h1 class="ff-serif text-4xl font-black text-[var(--ink)] mb-3">About This Site</h1>
  <p class="text-[var(--accent)] font-semibold tracking-widest mb-10">Powered by DawnCMS</p>
</div>
<div class="p-7 rounded-2xl border border-[var(--hairline)] bg-[var(--card)] mb-4">
  <h2 class="ff-serif text-xl font-bold text-[var(--ink)] mb-3">Long-termism: a blog is an asset, not a consumable</h2>
  <p class="text-[var(--ink-soft)] leading-loose mb-2">Social media content is consumable — 24 hours after publishing, the algorithm buries it. A blog post is an asset: a good article keeps working in search engines for three, five years, bringing you readers, trust, and opportunities while you sleep.</p>
  <p class="text-[var(--ink-2)] leading-loose">Compounding applies to writing too: post No.1 goes unnoticed, post No.20 starts getting searched, and by post No.100 you own a content moat no one can copy overnight.</p>
</div>
<div class="p-7 rounded-2xl border border-[var(--hairline)] bg-[var(--card)] mb-10">
  <h2 class="ff-serif text-xl font-bold text-[var(--ink)] mb-3">About DawnCMS</h2>
  <p class="text-[var(--ink-soft)] leading-loose">This site runs on DawnCMS — a lightweight, self-hosted CMS built for long-term writing. Your data stays yours, themes are swappable, and no third-party platform is required.</p>
</div>
<div class="text-center">
  <a href="/{lang}" class="btn-primary">Start Reading</a>
  <a href="/{lang}/feed.xml" class="btn-secondary ml-3">Subscribe</a>
</div>
"""

    _DAWN_DOCS_T = {
        "en-us": {
            "index_title": "Theme Development Docs",
            "index_desc": "DawnCMS theme development docs: quick start, token reference, design guide, upload & debugging.",
            "index_intro": "A theme package = theme.json + vars.json + style.css + Jinja2 templates. Four chapters, from quick start to design guide.",
            "items": {
                "quick-start": ("Quick Start", "Theme package structure, extends inheritance, minimal theme, three-step launch"),
                "tokens": ("Token Reference", "Purpose, defaults, and interplay of all 28 tokens"),
                "design-guide": ("Design Guide", "Reskin vs rebuild, contrast baselines, dark/light techniques, checklist"),
                "upload-debug": ("Upload, Debugging & FAQ", "Zip packaging rules, DevTools live color tuning, template debugging, FAQ"),
            },
        },
    }

    def _dawn_docs_meta(lang):
        from routes.dawn_docs import DAWN_DOCS
        t = _DAWN_DOCS_T.get(lang)
        if not t:
            return DAWN_DOCS
        return [{**d, "title": t["items"].get(d["slug"], (d["title"], d["desc"]))[0],
                 "desc": t["items"].get(d["slug"], (d["title"], d["desc"]))[1]} for d in DAWN_DOCS]

    def _dawn_load_doc_lang(lang, slug):
        from routes.dawn_docs import _dawn_load_doc, DAWN_DOCS_DIR
        doc = _dawn_load_doc(slug)
        if not doc:
            return None
        p = DAWN_DOCS_DIR / lang / doc["file"]
        if p.exists():
            doc = {**doc, "markdown": p.read_text(encoding="utf-8")}
        return doc

    async def _about_page(lang, session):
        from routes.dawn_frontend import DAWN_ABOUT_HTML
        t = _DAWN_DOCS_T.get(lang, {})
        content = (_DAWN_ABOUT_HTML_EN.replace("{lang}", lang) if lang == "en-us" else DAWN_ABOUT_HTML)
        ctx = await _front_ctx(session, title=_dawn_lt(lang, "about_label"), lang=lang)
        ctx.update({
            "title": _dawn_lt(lang, "about_label"), "content": content,
            "canonical": f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/about",
            "home_url": f"/{lang}", "html_lang": _dawn_hreflang_code(lang),
            "lang_switch": [], "extra_head": "",
        })
        return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("page.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

    async def _docs_index(lang, session):
        t = _DAWN_DOCS_T.get(lang, {})
        ctx = await _front_ctx(session, title=t.get("index_title", "主题开发文档"),
                               desc=t.get("index_desc", ""), lang=lang)
        ctx.update({
            "title": t.get("index_title", "主题开发文档"),
            "desc": t.get("index_desc", ""),
            "canonical": f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/docs",
            "docs_intro": t.get("index_intro", ""),
            "docs_items": _dawn_docs_meta(lang),
            "docs_base": f"/{lang}",
            "home_url": f"/{lang}", "html_lang": _dawn_hreflang_code(lang),
            "lang_switch": [], "extra_head": "",
        })
        return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("docs-index.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

    async def _docs_article(lang, slug, session):
        from starlette.exceptions import HTTPException
        from routes.dawn_docs import DAWN_DOCS
        from ui.dawn_article import DAWN_DOC_JS, dawn_extract_toc_and_anchors
        from services.dawn_markdown_renderer import DawnMarkdownRenderer
        doc = _dawn_load_doc_lang(lang, slug)
        if not doc:
            raise HTTPException(status_code=404)
        meta = {d["slug"]: d for d in _dawn_docs_meta(lang)}
        doc = {**doc, **{k: v for k, v in meta.get(slug, {}).items() if k in ("title", "desc")}}
        html = DawnMarkdownRenderer.render_with_prose(doc["markdown"])
        toc_items, html_with_ids = dawn_extract_toc_and_anchors(html)
        items = _dawn_docs_meta(lang)
        idx = next((i for i, d in enumerate(items) if d["slug"] == slug), 0)
        prev_doc = items[idx - 1] if idx > 0 else None
        next_doc = items[idx + 1] if idx + 1 < len(items) else None
        t = _DAWN_DOCS_T.get(lang, {})
        ctx = await _front_ctx(session, title=f"{doc['title']} - {t.get('index_title', '主题开发文档')}",
                               desc=doc["desc"], lang=lang)
        ctx.update({
            "title": f"{doc['title']} - {t.get('index_title', '主题开发文档')}",
            "canonical": f"{DAWN_SITE_BASE_URL.rstrip('/')}/{lang}/docs/{slug}",
            "doc": doc, "doc_html": html_with_ids, "toc": toc_items,
            "docs_items": items, "prev_doc": prev_doc, "next_doc": next_doc,
            "doc_js": DAWN_DOC_JS, "docs_base": f"/{lang}",
            "home_url": f"/{lang}", "html_lang": _dawn_hreflang_code(lang),
            "lang_switch": [], "extra_head": "",
        })
        return _dawn_set_lang_cookie(HTMLResponse(dawn_themes.dawn_render("docs-article.html", lang=ctx.pop("_lang", ""), **ctx)), lang)

    # ---- 旧 /lang/{lang} 路径 301 迁移（SEO 权重转移）----
    @app.get("/lang/{lang}")
    async def _legacy_home(lang: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}", status_code=301)

    @app.get("/lang/{lang}/c/{cat_slug}")
    async def _legacy_cat(lang: str, cat_slug: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}/c/{cat_slug}", status_code=301)

    @app.get("/lang/{lang}/s/{series_slug}")
    async def _legacy_series(lang: str, series_slug: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}/s/{series_slug}", status_code=301)

    @app.get("/lang/{lang}/t/{tag_slug}")
    async def _legacy_tag(lang: str, tag_slug: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}/t/{tag_slug}", status_code=301)

    @app.get("/lang/{lang}/feed.xml")
    async def _legacy_feed(lang: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}/feed.xml", status_code=301)

    @app.get("/lang/{lang}/{slug}")
    async def _legacy_post(lang: str, slug: str):
        return RedirectResponse(f"/{DAWN_LANG_MIGRATE.get(lang, lang)}/{slug}", status_code=301)
