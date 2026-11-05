# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
"""DawnCMS - 主题系统 v2（独立主题包 + 兼容旧接口）

主题包 = themes/ 下的目录：
    theme.json      元信息：{"key","name","description","author","version","preview":["#..."], "extends":"shimo"}
    vars.json       CSS 变量覆盖（缺省用 DAWN_DEFAULT_TOKENS 宣纸默认值）
    style.css       附加 CSS（可选，根目录，向后兼容旧包）
    assets/
        core/       平台基线（base.css / doc.css / doc.js / list.css），放同名文件即覆盖
        css/*.css   主题主样式（按文件名排序拼接）
        js/*.js     主题脚本（按文件名排序拼接）
        fonts/ img/ 字体与图片，经 /theme-assets/{key}/{path} 对外服务
    locales/        主题 UI 文案翻译：{lang}.json（中文默认版命名 zh-CN.default.json）
    templates/      Jinja2 沙盒模板（base.html / list.html / post.html / page.html / gate.html / 404.html ...）

- extends：模板 / vars.json / style.css / assets / locales 全部沿父主题链回退（子覆盖父）
- 自定义主题两种来源：
    1) 后台上传 zip 主题包 -> themes/custom/{key}/（Jinja2 沙盒渲染）
- 后台保持暗色，主题只影响前台
"""
import contextvars
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

DAWN_DB_PATH = str(Path(__file__).parent / "database" / "blog.db")


def _dawn_get_setting(key, default=""):
    try:
        db = sqlite3.connect(DAWN_DB_PATH, timeout=5)
        row = db.execute("SELECT value FROM site_settings WHERE key = ?", (key,)).fetchone()
        db.close()
        return row[0] if row else default
    except Exception:
        return default


def _dawn_set_setting(key, value):
    db = sqlite3.connect(DAWN_DB_PATH, timeout=5)
    db.execute("INSERT INTO site_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()
    db.close()

DAWN_THEMES_DIR = Path(__file__).parent / "themes"
DAWN_CUSTOM_DIR = DAWN_THEMES_DIR / "custom"
DAWN_DEFAULT_PACKAGE = "shimo"

DAWN_LAYOUTS = {
    "boxed": {"label": "书函 · 1200px", "desc": "居中留白，适合长文阅读"},
    "full": {"label": "铺陈 · 宽幕", "desc": "1560px 宽幕（≥1400px 屏生效），侧栏加宽"},
}

# ---------- 设计 token（shimo 宣纸墨韵默认值；全站 CSS 使用这套变量名） ----------

DAWN_DEFAULT_TOKENS = {
    "paper": "#f8f6f1", "card": "#fffdf9", "wash": "#f0ede5",
    "ink": "#23211d", "ink_soft": "#3a372f", "ink_2": "#5a554a",
    "muted": "#8a857a", "faint": "#a8a398", "ghost": "#c6c1b5",
    "hairline": "#e5e1d6", "hairline_soft": "#efece3", "hairline_strong": "#cfc9ba",
    "accent": "#b4362e", "accent_deep": "#93291f", "accent_soft": "#f7ebe9",
    "accent_rgb": "180,54,46", "ink_rgb": "35,33,29", "muted_rgb": "138,133,122",
    "serif": "'Noto Serif SC','Songti SC','SimSun',Georgia,serif",
    "doc_font": "'Noto Serif SC','Songti SC',Georgia,serif",
    "code_bg": "#efece3", "code_text": "#8a2f28",
    "hl_yellow": "#efe7c8", "hl_green": "#dfe8d8", "hl_red": "#f0dcd8", "hl_purple": "#e6def0",
    "tag_bg": "#f0ede5", "tag_text": "#6b675e",
}

DAWN_ALLOWED_ZIP_SUFFIXES = {".json", ".html", ".css", ".js", ".md", ".txt", ".svg", ".png", ".jpg", ".jpeg",
                        ".webp", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf"}
DAWN_MAX_ZIP_SIZE = 4 * 1024 * 1024
DAWN_MAX_ZIP_FILES = 120
DAWN_THEME_TOKEN_KEYS = set(DAWN_DEFAULT_TOKENS.keys())
_dawn_key_re = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

# 主题静态资产（/theme-assets/{key}/{path}）：MIME 与后缀白名单
DAWN_ASSET_SUFFIXES = {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
                  ".woff", ".woff2", ".ttf", ".otf", ".json", ".txt"}
DAWN_ASSET_MIME = {
    ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
}


def dawn_asset_url(pkg, rel: str, fallback: str = "") -> str:
    """主题资产 URL（沿继承链查找）；找不到返回 fallback。带主题版本号查询参数，主题升级后自动破缓存"""
    if not pkg:
        return fallback
    key, f = pkg.find_asset(rel)
    if not f:
        return fallback
    v = str(pkg.meta.get("version", "") or "").strip()
    url = f"/theme-assets/{key}/{rel}"
    return f"{url}?v={v}" if v else url


def dawn_chain_asset_text(pkg, rel: str, fallback: str = "") -> str:
    """沿继承链读 assets/{rel} 文本内容（如 css/base.css、js/doc.js），找不到返回 fallback。

    平台共享样式/脚本以此下沉到主题目录：默认主题 shimo 的 assets/ 承载平台基线，
    任何主题放置同名文件即可覆盖（extends 链上子主题优先）。
    """
    if pkg:
        _, f = pkg.find_asset(rel)
        if f:
            try:
                return f.read_text("utf-8")
            except Exception:
                pass
    return fallback


def dawn_serve_theme_asset(key: str, rel: str):
    """/theme-assets 路由处理：校验 key/路径/后缀，返回 FileResponse 或 None"""
    from starlette.responses import FileResponse
    if not key or not _dawn_key_re.match(key):
        return None
    pkg = dawn_get_package(key)
    if not pkg:
        return None
    rel = (rel or "").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    base = (pkg.path / "assets").resolve()
    target = (base / rel).resolve()
    if not str(target).startswith(str(base) + os.sep) or not target.is_file():
        return None
    suffix = target.suffix.lower()
    if suffix not in DAWN_ASSET_SUFFIXES:
        return None
    return FileResponse(str(target), media_type=DAWN_ASSET_MIME.get(suffix, "application/octet-stream"),
                        headers={"Cache-Control": "public, max-age=86400"})

_dawn_pkg_cache = {}
_dawn_envs = {}


# ---------- 主题包 ----------

class DawnThemePackage:
    def __init__(self, key, path, meta):
        self.key = key
        self.path = path
        self.meta = meta
        self.name = meta.get("name", key)
        self.parent_key = meta.get("extends") or None
        self.custom = DAWN_CUSTOM_DIR in path.parents

    def tokens(self):
        t = dict(DAWN_DEFAULT_TOKENS)
        vf = self.path / "vars.json"
        if vf.exists():
            try:
                for k, v in json.loads(vf.read_text("utf-8")).items():
                    kk = k.replace("-", "_")
                    if kk in t and isinstance(v, str):
                        t[kk] = v
            except Exception:
                pass
        return t

    def style_css(self):
        parts = []
        for th in reversed(self._chain()):
            f = th.path / "style.css"
            if f.exists():
                parts.append(f.read_text("utf-8"))
            css_dir = th.path / "assets" / "css"
            if css_dir.is_dir():
                for cf in sorted(css_dir.glob("*.css")):
                    parts.append(f"/* === {th.key}/assets/css/{cf.name} === */\n" + cf.read_text("utf-8"))
        return "\n".join(parts)

    def scripts_js(self):
        """assets/js/*.js 按文件名排序拼接，沿父主题链回退（父在前、子在后可覆盖）"""
        parts = []
        for th in reversed(self._chain()):
            js_dir = th.path / "assets" / "js"
            if js_dir.is_dir():
                for jf in sorted(js_dir.glob("*.js")):
                    parts.append(f"/* === {th.key}/assets/js/{jf.name} === */\n" + jf.read_text("utf-8"))
        return "\n".join(parts)

    def find_asset(self, rel: str):
        """在自身及父主题链中找 assets/{rel}，返回 (theme_key, Path) 或 (None, None)"""
        for th in self._chain():
            f = th.path / "assets" / rel
            if f.is_file():
                return th.key, f
        return None, None

    def template_dirs(self):
        dirs = []
        for th in self._chain():
            d = th.path / "templates"
            if d.is_dir():
                dirs.append(str(d))
        return dirs

    def settings_schema(self):
        """theme.json 的 settings 字段：{name: {type, label, default, options, group, min, max, step, unit}}"""
        raw = self.meta.get("settings") or {}
        out = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict) and v.get("type") in ("select", "color", "text", "image", "range", "toggle", "textarea"):
                    out[k] = v
        return out

    def home_sections_schema(self):
        """theme.json 的 home_sections 字段：[{type, label, settings:{...}}]"""
        raw = self.meta.get("home_sections") or []
        out = []
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, dict) and s.get("type") and s.get("label"):
                    out.append(s)
        return out

    def has_templates(self):
        return bool(self.template_dirs())

    def _chain(self):
        out, seen, cur = [], set(), self
        while cur and cur.key not in seen:
            seen.add(cur.key)
            out.append(cur)
            cur = dawn_get_package(cur.parent_key) if cur.parent_key else None
        return out


def _dawn_load_package_dir(path):
    mf = path / "theme.json"
    if not mf.exists():
        return None
    try:
        meta = json.loads(mf.read_text("utf-8"))
    except Exception:
        return None
    return DawnThemePackage(meta.get("key") or path.name, path, meta)


def dawn_list_packages():
    out = []
    for base in (DAWN_THEMES_DIR, DAWN_CUSTOM_DIR):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and d.name != "custom":
                pkg = _dawn_load_package_dir(d)
                if pkg:
                    out.append(pkg)
    return out


def dawn_get_package(key):
    if not key:
        return None
    if key in _dawn_pkg_cache:
        return _dawn_pkg_cache[key]
    for base in (DAWN_THEMES_DIR, DAWN_CUSTOM_DIR):
        d = base / key
        if d.is_dir():
            pkg = _dawn_load_package_dir(d)
            if pkg:
                _dawn_pkg_cache[key] = pkg
                return pkg
    return None


# ---------- 主题列表 / 激活 ----------

def dawn_all_themes():
    """后台外观页用：{key: {label, desc, swatch, custom, package}}"""
    out = {}
    for pkg in dawn_list_packages():
        preview = pkg.meta.get("preview") or []
        sw = tuple(preview[:3]) if len(preview) >= 3 else None
        if not sw:
            t = pkg.tokens()
            sw = (t["paper"], t["ink"], t["accent"])
        out[pkg.key] = {"label": pkg.name, "desc": pkg.meta.get("description", ""),
                        "swatch": sw, "custom": pkg.custom, "package": pkg.has_templates()}
    return out


def dawn_get_active_theme_key():
    pv = _dawn_preview_var.get()
    if pv and dawn_get_package(pv):
        return pv
    key = _dawn_get_setting("active_theme", os.environ.get("SITE_THEME", DAWN_DEFAULT_PACKAGE))
    if dawn_get_package(key):
        return key
    return DAWN_DEFAULT_PACKAGE


# ---- 主题预览（后台编辑页 iframe 用，HMAC 签名免登录态依赖） ----
_dawn_preview_var = contextvars.ContextVar("dawn_theme_preview", default=None)


def dawn_preview_signature(key: str) -> str:
    secret = os.environ.get("SESSION_SECRET", "dawncms-secret-change-me")
    return hmac.new(secret.encode(), f"theme-preview:{key}".encode(), hashlib.sha256).hexdigest()[:32]


def dawn_set_preview_from_query(key: str, sig: str) -> None:
    if key and sig and hmac.compare_digest(sig, dawn_preview_signature(key)) and dawn_get_package(key):
        _dawn_preview_var.set(key)


def dawn_set_active_theme(key):
    if dawn_get_package(key):
        _dawn_set_setting("active_theme", key)
        return True
    return False


# ---------- 主题设置（theme.json settings schema → site_settings 存储 → 模板 ctx） ----------

DAWN_FONT_STACKS = {
    "System sans-serif": ("", "ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"),
    "Inter": ("Inter", "'Inter',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Roboto": ("Roboto", "'Roboto',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Raleway": ("Raleway", "'Raleway',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Montserrat": ("Montserrat", "'Montserrat',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Nunito Sans": ("Nunito Sans", "'Nunito Sans',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Work Sans": ("Work Sans", "'Work Sans',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "Source Sans 3": ("Source Sans 3", "'Source Sans 3',ui-sans-serif,system-ui,'PingFang SC','Microsoft YaHei',sans-serif"),
    "System serif": ("", "ui-serif,Georgia,'Songti SC','SimSun',serif"),
    "Roboto Serif": ("Roboto Serif", "'Roboto Serif',ui-serif,Georgia,'Songti SC',serif"),
    "Source Serif 4": ("Source Serif 4", "'Source Serif 4',ui-serif,Georgia,'Songti SC',serif"),
    "Playfair Display": ("Playfair Display", "'Playfair Display',ui-serif,Georgia,'Songti SC',serif"),
}


def _dawn_hex_rgb(v: str):
    h = (v or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _dawn_hex_mix(v: str, target=(255, 255, 255), t=0.3):
    rgb = _dawn_hex_rgb(v)
    if not rgb:
        return ""
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c + (tc - c) * t))) for c, tc in zip(rgb, target))


def dawn_theme_settings_css(theme_key=None, values=None):
    """主题设置派生的 CSS。返回 (imports, rules)：imports 为 @import 行（必须置于样式表最前），rules 为 :root/html.dark 覆盖。
    values 显式传入时直接使用（编辑器预览），否则从存储读取。"""
    s = values if values is not None else dawn_theme_settings(theme_key)
    if not s:
        return "", ""
    imports, root_rules, dark_rules = [], [], []
    for opt, var in ((s.get("body_font"), "--doc-font"), (s.get("headings_font"), "--serif")):
        f = DAWN_FONT_STACKS.get(opt or "")
        if f:
            if f[0]:
                imports.append(f"@import url('https://fonts.googleapis.com/css2?family={f[0].replace(' ', '+')}:ital,wght@0,400..900;1,400..900&display=swap');")
            root_rules.append(f"{var}:{f[1]}")
    accent = (s.get("accent_color") or "").strip()
    rgb = _dawn_hex_rgb(accent)
    if accent and rgb:
        root_rules.append(f"--accent:{accent}")
        root_rules.append(f"--accent-rgb:{rgb[0]},{rgb[1]},{rgb[2]}")
        root_rules.append("--accent-deep:color-mix(in srgb, var(--accent) 82%, black)")
        root_rules.append("--accent-soft:color-mix(in srgb, var(--accent) 8%, var(--paper))")
        dark_accent = (s.get("dark_theme_accent_color") or "").strip()
        drgb = _dawn_hex_rgb(dark_accent)
        if dark_accent and drgb and dark_accent.lower() != "#000000":
            dark_rules.append(f"--accent:{dark_accent}")
            dark_rules.append(f"--accent-rgb:{drgb[0]},{drgb[1]},{drgb[2]}")
        else:
            # Python 侧预计算调亮值（CSS 自定义属性不能在同规则内自引用，color-mix(var(--accent)) 会循环失效）
            lit = _dawn_hex_mix(accent, (255, 255, 255), 0.35)
            lrgb = _dawn_hex_rgb(lit)
            if lit and lrgb:
                dark_rules.append(f"--accent:{lit}")
                dark_rules.append(f"--accent-rgb:{lrgb[0]},{lrgb[1]},{lrgb[2]}")
        dark_rules.append("--accent-deep:color-mix(in srgb, var(--accent) 82%, black)")
        dark_rules.append("--accent-soft:color-mix(in srgb, var(--accent) 14%, transparent)")
    css = ""
    if root_rules:
        css += ":root{" + ";".join(root_rules) + "}"
    if dark_rules:
        css += "html.dark{" + ";".join(dark_rules) + "}"
    return "\n".join(imports), css

def dawn_theme_editor_state(theme_key) -> dict:
    """编辑器初始状态：settings = 正式 ∪ 草稿覆盖；sections = 草稿优先。供后台编辑器页面使用。"""
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return {"settings": {}, "sections": [], "schema": {}, "has_draft": False}
    schema = pkg.settings_schema()
    settings = {}
    for name, spec in schema.items():
        v = _dawn_get_setting(f"theme_{theme_key}_set_{name}", str(spec.get("default", "")))
        dv = _dawn_get_setting(f"theme_{theme_key}_draft_{name}", "")
        settings[name] = dv if dv != "" else v
    sections_raw = _dawn_get_setting(f"theme_{theme_key}_sections_draft", "") or _dawn_get_setting(f"theme_{theme_key}_sections", "")
    specs = {s["type"]: s for s in pkg.home_sections_schema()}
    saved = []
    if sections_raw:
        try:
            saved = json.loads(sections_raw)
        except Exception:
            saved = []
    saved_map = {s.get("type"): s for s in saved if isinstance(s, dict) and s.get("type") in specs}
    order = [s.get("type") for s in saved if isinstance(s, dict) and s.get("type") in specs]
    order += [t for t in specs if t not in order]
    sections = []
    for t in order:
        spec = specs[t]
        sv = saved_map.get(t) or {}
        stored = sv.get("settings") or {}
        merged = {name: str(stored.get(name, sspec.get("default", "")))
                  for name, sspec in (spec.get("settings") or {}).items()}
        sections.append({"type": t, "label": spec.get("label", t),
                         "enabled": bool(sv.get("enabled", True)),
                         "settings": merged, "schema": spec.get("settings") or {}})
    return {"settings": settings, "sections": sections, "schema": schema,
            "has_draft": dawn_theme_has_draft(theme_key)}


def dawn_theme_settings(theme_key=None):
    """当前主题的全部设置值（默认值兜底）。返回 {name: value}。预览上下文（编辑中）优先读草稿。"""
    theme_key = theme_key or dawn_get_active_theme_key()
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return {}
    preview = bool(_dawn_preview_var.get())
    out = {}
    for name, spec in pkg.settings_schema().items():
        v = _dawn_get_setting(f"theme_{theme_key}_set_{name}", str(spec.get("default", "")))
        if preview:
            dv = _dawn_get_setting(f"theme_{theme_key}_draft_{name}", "")
            if dv != "":
                v = dv
        out[name] = v
    return out


def _dawn_validate_setting_value(spec: dict, raw) -> tuple[str, bool]:
    """按 spec 校验单个设置值。返回 (value, ok)"""
    v = str(raw or "").strip()
    t = spec.get("type")
    if t == "select":
        if v not in (spec.get("options") or []):
            v = str(spec.get("default", ""))
    elif t == "color":
        if not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v):
            v = str(spec.get("default", ""))
    elif t == "image":
        if v and not (v.startswith("/") or v.startswith("http://") or v.startswith("https://")):
            return v, False
    elif t == "range":
        try:
            n = float(v)
            lo = float(spec.get("min", 0))
            hi = float(spec.get("max", 100))
            v = str(int(max(lo, min(hi, n))))
        except (TypeError, ValueError):
            v = str(spec.get("default", spec.get("min", 0)))
    elif t == "toggle":
        v = "1" if v in ("1", "true", "on", True, 1) else "0"
    elif t == "textarea":
        v = v[:5000]
    else:
        v = v[:500]
    return v, True


def dawn_set_theme_settings(theme_key, values: dict, draft: bool = False):
    """按 schema 校验后保存设置。draft=True 写入草稿位（预览用，不影响正式）。返回 (saved_count, skipped)"""
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return 0, []
    schema = pkg.settings_schema()
    slot = "draft" if draft else "set"
    saved, skipped = 0, []
    for name, spec in schema.items():
        if name not in values:
            continue
        v, ok = _dawn_validate_setting_value(spec, values.get(name))
        if not ok:
            skipped.append(name)
            continue
        _dawn_set_setting(f"theme_{theme_key}_{slot}_{name}", v)
        saved += 1
    return saved, skipped


def dawn_theme_has_draft(theme_key) -> bool:
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return False
    if any(_dawn_get_setting(f"theme_{theme_key}_draft_{name}", "") != "" for name in pkg.settings_schema()):
        return True
    return _dawn_get_setting(f"theme_{theme_key}_sections_draft", "") != ""


def dawn_theme_clear_draft(theme_key) -> None:
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return
    for name in pkg.settings_schema():
        _dawn_set_setting(f"theme_{theme_key}_draft_{name}", "")
    _dawn_set_setting(f"theme_{theme_key}_sections_draft", "")


def dawn_theme_publish_draft(theme_key) -> int:
    """草稿转正：draft → set，然后清空草稿。返回转正条数"""
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return 0
    n = 0
    for name in pkg.settings_schema():
        dv = _dawn_get_setting(f"theme_{theme_key}_draft_{name}", "")
        if dv != "":
            _dawn_set_setting(f"theme_{theme_key}_set_{name}", dv)
            n += 1
    sd = _dawn_get_setting(f"theme_{theme_key}_sections_draft", "")
    if sd:
        _dawn_set_setting(f"theme_{theme_key}_sections", sd)
        n += 1
    dawn_theme_clear_draft(theme_key)
    return n


def dawn_theme_home_sections(theme_key=None) -> list:
    """首页区块列表：[{type, label, enabled, settings:{name:value}, schema}]。预览上下文优先读草稿。"""
    theme_key = theme_key or dawn_get_active_theme_key()
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return []
    specs = {s["type"]: s for s in pkg.home_sections_schema()}
    if not specs:
        return []
    key = f"theme_{theme_key}_sections"
    raw = ""
    if _dawn_preview_var.get():
        raw = _dawn_get_setting(key + "_draft", "")
    raw = raw or _dawn_get_setting(key, "")
    saved = []
    if raw:
        try:
            saved = json.loads(raw)
        except Exception:
            saved = []
    saved_map = {s.get("type"): s for s in saved if isinstance(s, dict) and s.get("type") in specs}
    # 以 theme.json 声明顺序为基线，DB 顺序优先；新声明的区块自动补到末尾
    order = [s.get("type") for s in saved if isinstance(s, dict) and s.get("type") in specs]
    order += [t for t in specs if t not in order]
    out = []
    for t in order:
        spec = specs[t]
        sv = saved_map.get(t) or {}
        stored = sv.get("settings") or {}
        merged = {}
        for name, sspec in (spec.get("settings") or {}).items():
            merged[name] = str(stored.get(name, sspec.get("default", "")))
        out.append({"type": t, "label": spec.get("label", t),
                    "enabled": bool(sv.get("enabled", True)),
                    "settings": merged, "schema": spec.get("settings") or {}})
    return out


def dawn_set_theme_home_sections(theme_key, sections: list, draft: bool = False) -> bool:
    """保存首页区块（顺序 + 开关 + 区块设置）。未知类型拒绝。"""
    pkg = dawn_get_package(theme_key)
    if not pkg:
        return False
    specs = {s["type"]: s for s in pkg.home_sections_schema()}
    if not specs:
        return False
    clean = []
    for s in sections:
        if not isinstance(s, dict) or s.get("type") not in specs:
            continue
        spec = specs[s["type"]]
        settings = {}
        for name, sspec in (spec.get("settings") or {}).items():
            v, _ok = _dawn_validate_setting_value(sspec, (s.get("settings") or {}).get(name, sspec.get("default", "")))
            settings[name] = v
        clean.append({"type": s["type"], "enabled": bool(s.get("enabled", True)), "settings": settings})
    slot = "_draft" if draft else ""
    _dawn_set_setting(f"theme_{theme_key}_sections{slot}", json.dumps(clean, ensure_ascii=False))
    return True


def dawn_resolve_tokens(key=None):
    key = key or dawn_get_active_theme_key()
    t = dict(DAWN_DEFAULT_TOKENS)
    pkg = dawn_get_package(key)
    if pkg:
        t.update(pkg.tokens())
    return t


def dawn_theme_root_css():
    """兼容旧接口：当前主题的 :root 变量 CSS（末尾附主题设置派生 CSS）"""
    inner = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in dawn_resolve_tokens().items())
    css = ":root{" + inner + "}"
    pkg = dawn_get_package(dawn_get_active_theme_key())
    if pkg:
        extra = pkg.style_css()
        if extra:
            css += "\n" + extra
    settings_imports, settings_rules = dawn_theme_settings_css()
    if settings_imports:
        css = settings_imports + "\n" + css
    if settings_rules:
        css += "\n" + settings_rules
    return css


# ---------- 版式 ----------

def dawn_get_layout_mode():
    m = _dawn_get_setting("layout_mode", os.environ.get("SITE_LAYOUT", "boxed"))
    return m if m in DAWN_LAYOUTS else "boxed"


def dawn_set_layout_mode(mode):
    if mode not in DAWN_LAYOUTS:
        return False
    _dawn_set_setting("layout_mode", mode)
    return True


def dawn_layout_override_css():
    """宽屏模式（≥1400px 放宽到 1560px）。用 body 前缀提升优先级，不依赖 !important 和样式顺序"""
    if dawn_get_layout_mode() == "boxed":
        return ""
    return """
@media (min-width:1400px){
body .max-w-\\[1200px\\],
body .max-w-\\[1366px\\]{max-width:1560px}
body .article-grid{grid-template-columns:280px minmax(0,1fr) 260px;gap:40px}
body .article-grid .doc-main{max-width:none}
body .article-grid .doc-content{font-size:1.12rem}
}
"""


# ---------- Jinja2 模板渲染（沙盒） ----------

def _dawn_env_for(pkg):
    if pkg.key in _dawn_envs:
        return _dawn_envs[pkg.key]
    dirs = pkg.template_dirs()
    if not dirs:
        raise RuntimeError(f"主题 {pkg.key} 缺少 templates 目录")
    env = SandboxedEnvironment(loader=FileSystemLoader(dirs), autoescape=True,
                               trim_blocks=True, lstrip_blocks=True)
    _dawn_envs[pkg.key] = env
    return env


# ---------- 主题多语言（Shopify 式 JSON locale 文件） ----------
# 主题目录下 locales/{lang}.json（中文默认版命名 zh-CN.default.json），沿 extends 父主题链回退；
# 插件可经 dawn_register_locale_provider 注册兜底表（无 locales 目录的第三方主题自动兼容）。

_dawn_locale_cache = {}
_dawn_locale_providers = []


def dawn_register_locale_provider(func):
    """插件注册前台 UI 文案兜底表：func(lang) -> dict"""
    _dawn_locale_providers.append(func)


def _dawn_locale_candidates(lang: str) -> list:
    """BCP 47 回退链：en-us → [en-us, en]；zh-tw → [zh-tw, zh-TW, zh]"""
    parts = (lang or "").split("-")
    cands = [lang]
    if len(parts) > 1:
        cands.append(f"{parts[0]}-{parts[1].upper()}")
        cands.append(parts[0])
    return cands


def _dawn_theme_locale(pkg, lang):
    key = (pkg.key, lang)
    if key in _dawn_locale_cache:
        return _dawn_locale_cache[key]
    merged = {}
    for th in reversed(pkg._chain()):
        for cand in reversed(_dawn_locale_candidates(lang)):
            files = []
            if lang.startswith("zh"):
                files.append(th.path / "locales" / f"{cand}.default.json")
            files.append(th.path / "locales" / f"{cand}.json")
            for f in files:
                if f.exists():
                    try:
                        merged.update(json.loads(f.read_text("utf-8")))
                    except Exception:
                        pass
    _dawn_locale_cache[key] = merged
    return merged


def _dawn_make_translator(pkg, lang):
    if not lang or lang == "zh" or lang.startswith("zh-CN"):
        return lambda key, default="": default or key
    table = _dawn_theme_locale(pkg, lang)
    providers = [(p(lang) or {}) for p in _dawn_locale_providers]

    def t(key, default=""):
        v = table.get(key)
        if v:
            return v
        for p in providers:
            v = p.get(key)
            if v:
                return v
        return default or key

    return t


def dawn_render(template_name, lang="", **ctx):
    """用当前激活主题渲染模板。无模板包时回退 shimo 包。lang 非空时注入对应语言的 t()。"""
    key = dawn_get_active_theme_key()
    pkg = dawn_get_package(key)
    if not pkg or not pkg.has_templates():
        pkg = dawn_get_package(DAWN_DEFAULT_PACKAGE)
    try:
        tpl = _dawn_env_for(pkg).get_template(template_name)
    except Exception:
        pkg = dawn_get_package(DAWN_DEFAULT_PACKAGE)
        try:
            tpl = _dawn_env_for(pkg).get_template(template_name)
        except Exception:
            from starlette.exceptions import HTTPException
            raise HTTPException(status_code=404)
    ctx.setdefault("theme_key", pkg.key)
    ctx.setdefault("t", _dawn_make_translator(pkg, lang))
    ctx.setdefault("theme_js", pkg.scripts_js())
    ctx.setdefault("logo_url", dawn_asset_url(pkg, "img/logo.svg", "/static/logo.svg"))
    ctx.setdefault("theme_settings", dawn_theme_settings(key))
    return tpl.render(**ctx)


def dawn_reload_themes():
    _dawn_pkg_cache.clear()
    _dawn_envs.clear()
    _dawn_locale_cache.clear()


# ---------- zip 主题包上传 ----------

def dawn_save_uploaded_theme(content: bytes):
    if len(content) > DAWN_MAX_ZIP_SIZE:
        return False, f"主题包超过 {DAWN_MAX_ZIP_SIZE // (1024 * 1024)}MB 限制"
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception:
        return False, "不是有效的 zip 文件"

    names = [n for n in zf.namelist() if not n.endswith("/")]
    if not names:
        return False, "zip 为空"
    if len(names) > DAWN_MAX_ZIP_FILES:
        return False, f"文件数超过 {DAWN_MAX_ZIP_FILES} 限制"
    roots = {n.split("/")[0] for n in names}
    strip = all("/" in n for n in names) and len(roots) == 1
    prefix = (names[0].split("/")[0] + "/") if strip else ""
    inner = [n[len(prefix):] for n in names if n[len(prefix):]]

    if "theme.json" not in inner:
        return False, "zip 中缺少 theme.json"
    for n in inner:
        if Path(n).suffix.lower() not in DAWN_ALLOWED_ZIP_SUFFIXES:
            return False, f"不允许的文件类型：{n}"
        if ".." in n.split("/"):
            return False, "非法路径"

    try:
        meta = json.loads(zf.read(prefix + "theme.json").decode("utf-8"))
    except Exception:
        return False, "theme.json 解析失败"
    key = (meta.get("key") or "").strip().lower()
    if not _dawn_key_re.match(key):
        return False, "theme.json 的 key 需为 2-32 位小写字母/数字/连字符"
    if not meta.get("name"):
        return False, "theme.json 缺少 name"
    if not meta.get("extends") and "templates/base.html" not in inner:
        return False, "完整主题需包含 templates/base.html，或在 theme.json 声明 extends 继承"

    target = DAWN_CUSTOM_DIR / key
    target.mkdir(parents=True, exist_ok=True)
    for n in inner:
        dest = (target / n).resolve()
        if not str(dest).startswith(str(target.resolve())):
            return False, "非法路径"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(prefix + n))

    dawn_reload_themes()
    pkg = dawn_get_package(key)
    if not pkg:
        return False, "主题加载失败"
    try:
        _dawn_env_for(pkg)
    except Exception as e:
        dawn_delete_theme_package(key)
        return False, f"模板加载失败：{e}"
    return True, f"主题包「{pkg.name}」已安装"


def dawn_delete_theme_package(key):
    pkg = dawn_get_package(key)
    if not pkg or not pkg.custom:
        return False
    if dawn_get_active_theme_key() == key:
        dawn_set_active_theme(DAWN_DEFAULT_PACKAGE)
    shutil.rmtree(pkg.path, ignore_errors=True)
    dawn_reload_themes()
    return True
