# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/logwatch/plugin.py
# DawnCMS 日志分析插件：
#   - 全站请求记录中间件（独立 database/logwatch.db，不影响主库）
#   - 蜘蛛识别（搜索引擎 / AI 爬虫 / SEO 工具，25+ 种 UA）
#   - 恶意行为检测：路径探测、404 洪水、高频访问，自动观察名单 + 可选自动封禁
#   - 后台面板：流量概览 / 蜘蛛抓取 / 未抓取页面 / 安全与封禁 / 实时日志

import random
import sqlite3
import time
from html import escape
from pathlib import Path

from fasthtml.common import (
    A, Button, Div, Form, H2, H3, Input, Label, Option, P, Script, Select, Span,
    Table, Tbody, Td, Th, Thead, Tr,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse

from blog.dawn_factory import dawn_get_blog_db
from routes.admin.dawn_shell import (
    _dawn_admin_shell, _dawn_require_admin, _dawn_msg,
    DAWN_INPUT, DAWN_BTN, DAWN_BTN_GHOST, dawn_register_admin_page,
)

DAWN_PLUGIN = {
    "key": "logwatch",
    "label": "日志分析",
    "group": "插件",
    "icon": "📈",
    "url": "/dadmin/plugins/logwatch",
}

_DAWN_DB = Path(__file__).resolve().parent.parent.parent / "database" / "logwatch.db"

# 不参与日志记录的前缀（静态资产/主题资产）
_DAWN_SKIP_PREFIXES = ("/static/", "/theme-assets/")

# 蜘蛛 UA 指纹：子串(小写) -> (名称, 类别)
_DAWN_SPIDERS = {
    "googlebot": ("Googlebot", "搜索引擎"),
    "adsbot-google": ("AdsBot-Google", "搜索引擎"),
    "bingbot": ("Bingbot", "搜索引擎"),
    "baiduspider": ("Baiduspider", "搜索引擎"),
    "yandexbot": ("YandexBot", "搜索引擎"),
    "duckduckbot": ("DuckDuckBot", "搜索引擎"),
    "sogou": ("Sogou Spider", "搜索引擎"),
    "360spider": ("360Spider", "搜索引擎"),
    "bytespider": ("Bytespider", "搜索引擎"),
    "petalbot": ("PetalBot", "搜索引擎"),
    "applebot": ("Applebot", "搜索引擎"),
    "gptbot": ("GPTBot", "AI 爬虫"),
    "oai-searchbot": ("OAI-SearchBot", "AI 爬虫"),
    "chatgpt-user": ("ChatGPT-User", "AI 爬虫"),
    "claudebot": ("ClaudeBot", "AI 爬虫"),
    "claude-user": ("Claude-User", "AI 爬虫"),
    "anthropic-ai": ("Anthropic-AI", "AI 爬虫"),
    "perplexitybot": ("PerplexityBot", "AI 爬虫"),
    "cohere-ai": ("Cohere-AI", "AI 爬虫"),
    "meta-externalagent": ("Meta-ExternalAgent", "AI 爬虫"),
    "semrushbot": ("SemrushBot", "SEO 工具"),
    "ahrefsbot": ("AhrefsBot", "SEO 工具"),
    "mj12bot": ("MJ12bot", "SEO 工具"),
    "dotbot": ("DotBot", "SEO 工具"),
    "exabot": ("Exabot", "SEO 工具"),
    "facebot": ("FacebookBot", "社交"),
    "twitterbot": ("Twitterbot", "社交"),
    "slackbot": ("Slackbot", "社交"),
}

# 恶意路径探测指纹（小写子串）
_DAWN_PROBE_PATTERNS = (
    ".env", ".git/", "wp-login", "wp-admin", "wp-content", "wordpress", "xmlrpc",
    "phpmyadmin", "adminer", ".php", ".asp", ".jsp", "cgi-bin", "/etc/passwd",
    "eval(", "../", ".bak", ".sql", ".zip", "/vendor/", "boaform", "hudson",
    "actuator", "/shell", "config.json", ".well-known/change-password",
)

_DAWN_DEFAULT_CFG = {
    "retention_days": "30",     # 日志保留天数
    "auto_block": "0",          # 观察名单命中阈值后是否自动封禁
    "rate_limit": "120",        # 单 IP 每分钟请求阈值
    "flood_404": "30",          # 单 IP 每小时 404 阈值
    "block_probes": "1",        # 路径探测直接封禁（一次性明显恶意）
}


# ---------- 存储层 ----------

def _dawn_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(_DAWN_DB), timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def _dawn_init_db() -> None:
    _DAWN_DB.parent.mkdir(parents=True, exist_ok=True)
    db = _dawn_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        ip TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        status INTEGER NOT NULL,
        ms REAL NOT NULL,
        ua TEXT DEFAULT '',
        referer TEXT DEFAULT '',
        spider TEXT DEFAULT '',
        flag TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_req_ts ON requests(ts);
    CREATE INDEX IF NOT EXISTS idx_req_ip ON requests(ip, ts);
    CREATE INDEX IF NOT EXISTS idx_req_spider ON requests(spider, ts);
    CREATE INDEX IF NOT EXISTS idx_req_path ON requests(path);
    CREATE TABLE IF NOT EXISTS watchlist(
        ip TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        hits INTEGER DEFAULT 1,
        last_seen REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS blocklist(
        ip TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        auto INTEGER DEFAULT 0,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS config(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    for k, v in _DAWN_DEFAULT_CFG.items():
        db.execute("INSERT OR IGNORE INTO config(key, value) VALUES(?,?)", (k, v))
    db.commit()
    db.close()


def _dawn_cfg() -> dict:
    db = _dawn_db()
    rows = db.execute("SELECT key, value FROM config").fetchall()
    db.close()
    out = dict(_DAWN_DEFAULT_CFG)
    out.update({r["key"]: r["value"] for r in rows})
    return out


def _dawn_detect_spider(ua: str) -> tuple[str, str]:
    ua_l = (ua or "").lower()
    for sub, (name, kind) in _DAWN_SPIDERS.items():
        if sub in ua_l:
            return name, kind
    return "", ""


def _dawn_detect_probe(path: str) -> str:
    p = path.lower()
    for pat in _DAWN_PROBE_PATTERNS:
        if pat in p:
            return f"路径探测:{pat}"
    return ""


def _dawn_log_request(ip, method, path, status, ms, ua, referer, spider, flag) -> None:
    now = time.time()
    db = _dawn_db()
    db.execute(
        "INSERT INTO requests(ts,ip,method,path,status,ms,ua,referer,spider,flag) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now, ip, method[:10], path[:300], status, round(ms, 1),
         (ua or "")[:300], (referer or "")[:300], spider, flag))
    cfg = None
    # 行为分析：404 洪水 + 高频访问（命中才查配置）
    reasons = []
    if flag:
        reasons.append(flag)
    if status == 404:
        n404 = db.execute(
            "SELECT COUNT(*) c FROM requests WHERE ip=? AND status=404 AND ts>?",
            (ip, now - 3600)).fetchone()["c"]
        cfg = cfg or _dawn_cfg()
        if n404 >= int(cfg["flood_404"]):
            reasons.append(f"404洪水({n404}/h)")
    nrate = db.execute(
        "SELECT COUNT(*) c FROM requests WHERE ip=? AND ts>?", (ip, now - 60)).fetchone()["c"]
    cfg = cfg or _dawn_cfg()
    if nrate >= int(cfg["rate_limit"]):
        reasons.append(f"高频访问({nrate}/min)")
    if reasons:
        reason = "; ".join(dict.fromkeys(reasons))[:200]
        db.execute(
            "INSERT INTO watchlist(ip, reason, hits, last_seen) VALUES(?,?,1,?) "
            "ON CONFLICT(ip) DO UPDATE SET reason=excluded.reason, hits=hits+1, last_seen=excluded.last_seen",
            (ip, reason, now))
        if cfg["auto_block"] == "1" or (cfg["block_probes"] == "1" and flag):
            db.execute(
                "INSERT OR IGNORE INTO blocklist(ip, reason, auto, created_at) VALUES(?,?,1,?)",
                (ip, reason, now))
    # 1% 概率顺手清理过期数据
    if random.random() < 0.01:
        cutoff = now - int(cfg["retention_days"]) * 86400
        db.execute("DELETE FROM requests WHERE ts<?", (cutoff,))
        db.execute("DELETE FROM watchlist WHERE last_seen<?", (cutoff,))
    db.commit()
    db.close()


def _dawn_is_blocked(ip: str) -> bool:
    db = _dawn_db()
    row = db.execute("SELECT 1 FROM blocklist WHERE ip=?", (ip,)).fetchone()
    db.close()
    return bool(row)


class DawnLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _DAWN_SKIP_PREFIXES):
            return await call_next(request)
        ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
              or (request.client.host if request.client else "") or "?")
        ua = request.headers.get("user-agent", "")
        spider, _kind = _dawn_detect_spider(ua)
        flag = _dawn_detect_probe(path)
        if _dawn_is_blocked(ip):
            _dawn_log_request(ip, request.method, path, 403, 0, ua,
                              request.headers.get("referer", ""), spider, "已封禁IP访问")
            return PlainTextResponse("Forbidden", status_code=403)
        t0 = time.time()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
            return resp
        finally:
            _dawn_log_request(ip, request.method, path, status,
                              (time.time() - t0) * 1000, ua,
                              request.headers.get("referer", ""), spider, flag)


# ---------- 后台 UI 小件 ----------

def _dawn_tabs(active: str):
    items = [
        ("overview", "流量概览", "/dadmin/plugins/logwatch"),
        ("spiders", "蜘蛛抓取", "/dadmin/plugins/logwatch/spiders"),
        ("uncrawled", "未抓取页面", "/dadmin/plugins/logwatch/uncrawled"),
        ("security", "安全与封禁", "/dadmin/plugins/logwatch/security"),
        ("live", "实时日志", "/dadmin/plugins/logwatch/live"),
    ]
    return Div(
        *[A(label, href=url,
            cls="px-4 py-2 rounded-lg text-sm font-bold " + (
                "bg-indigo-600 text-white" if k == active else "text-slate-400 hover:text-slate-200"))
          for k, label, url in items],
        cls="flex flex-wrap gap-2 mb-6")


def _dawn_stat_card(label, value, sub=""):
    return Div(
        P(label, cls="text-xs text-slate-400 mb-1"),
        P(str(value), cls="text-2xl font-black text-slate-100"),
        P(sub, cls="text-xs text-slate-500 mt-1") if sub else None,
        cls="bg-slate-800/60 rounded-xl p-4 border border-slate-700/60")


def _dawn_table(headers, rows):
    return Table(
        Thead(Tr(*[Th(h, cls="px-3 py-2 text-left text-xs text-slate-400") for h in headers])),
        Tbody(*rows),
        cls="w-full text-sm")


def _dawn_ts(ts) -> str:
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))


def _dawn_flag_badge(flag: str):
    if not flag:
        return Span("-", cls="text-slate-600 text-xs")
    color = "rose" if ("探测" in flag or "洪水" in flag or "高频" in flag or "封禁" in flag) else "amber"
    return Span(escape(flag), cls=f"px-2 py-0.5 rounded text-[11px] bg-{color}-500/15 text-{color}-300")


def _dawn_status_badge(status: int):
    color = "emerald" if status < 300 else ("sky" if status < 400 else ("amber" if status < 500 else "rose"))
    return Span(str(status), cls=f"px-2 py-0.5 rounded text-[11px] font-mono bg-{color}-500/15 text-{color}-300")


# ---------- 插件注册 ----------

def dawn_setup(app):
    _dawn_init_db()
    dawn_register_admin_page(DAWN_PLUGIN["group"], DAWN_PLUGIN["key"], DAWN_PLUGIN["label"],
                             DAWN_PLUGIN["url"], DAWN_PLUGIN["icon"])
    app.add_middleware(DawnLogMiddleware)

    # ---- 流量概览 ----

    @app.get("/dadmin/plugins/logwatch")
    async def logwatch_overview(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        db = _dawn_db()
        now = time.time()
        today0 = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        y0, y1 = today0 - 86400, today0

        def _pvuv(start, end=None):
            q = "SELECT COUNT(*) pv, COUNT(DISTINCT ip) uv FROM requests WHERE ts>=? AND spider=''"
            args = [start]
            if end:
                q += " AND ts<?"
                args.append(end)
            r = db.execute(q, args).fetchone()
            return r["pv"], r["uv"]

        pv_t, uv_t = _pvuv(today0)
        pv_y, uv_y = _pvuv(y0, y1)

        def _delta(a, b):
            if not b:
                return ""
            return f"昨日 {b}（{'+' if a >= b else ''}{round((a - b) / b * 100)}%）"

        spider_today = db.execute(
            "SELECT COUNT(*) c FROM requests WHERE ts>=? AND spider!=''", (today0,)).fetchone()["c"]
        blocked_today = db.execute(
            "SELECT COUNT(*) c FROM requests WHERE ts>=? AND flag!=''", (today0,)).fetchone()["c"]
        watch_n = db.execute("SELECT COUNT(*) c FROM watchlist").fetchone()["c"]
        block_n = db.execute("SELECT COUNT(*) c FROM blocklist").fetchone()["c"]

        trend = db.execute(
            "SELECT date(ts,'unixepoch','localtime') d, COUNT(*) pv, COUNT(DISTINCT ip) uv, "
            "SUM(CASE WHEN spider!='' THEN 1 ELSE 0 END) bot "
            "FROM requests WHERE ts>=? GROUP BY d ORDER BY d DESC", (now - 7 * 86400,)).fetchall()
        top_pages = db.execute(
            "SELECT path, COUNT(*) c FROM requests "
            "WHERE ts>=? AND spider='' AND path NOT LIKE '/dadmin%' "
            "GROUP BY path ORDER BY c DESC LIMIT 10", (now - 7 * 86400,)).fetchall()
        top_refs = db.execute(
            "SELECT referer, COUNT(*) c FROM requests "
            "WHERE ts>=? AND referer!='' AND spider='' "
            "GROUP BY referer ORDER BY c DESC LIMIT 10", (now - 7 * 86400,)).fetchall()
        top_ips = db.execute(
            "SELECT ip, COUNT(*) c, MAX(ts) last FROM requests WHERE ts>=? "
            "GROUP BY ip ORDER BY c DESC LIMIT 10", (now - 7 * 86400,)).fetchall()
        status_dist = db.execute(
            "SELECT status, COUNT(*) c FROM requests WHERE ts>=? "
            "GROUP BY status ORDER BY c DESC LIMIT 8", (now - 7 * 86400,)).fetchall()
        db.close()

        cards = Div(
            _dawn_stat_card("今日 PV", pv_t, _delta(pv_t, pv_y)),
            _dawn_stat_card("今日 UV（独立 IP）", uv_t, _delta(uv_t, uv_y)),
            _dawn_stat_card("今日蜘蛛访问", spider_today),
            _dawn_stat_card("今日异常请求", blocked_today),
            _dawn_stat_card("观察名单 IP", watch_n, A("管理 →", href="/dadmin/plugins/logwatch/security",
                                                    cls="text-indigo-400")),
            _dawn_stat_card("已封禁 IP", block_n, A("管理 →", href="/dadmin/plugins/logwatch/security",
                                                    cls="text-indigo-400")),
            cls="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6")

        trend_tbl = _dawn_table(
            ["日期", "PV", "UV", "蜘蛛"],
            [Tr(Td(r["d"], cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(r["pv"], cls="px-3 py-1.5 text-slate-200"),
                Td(r["uv"], cls="px-3 py-1.5 text-slate-200"),
                Td(r["bot"], cls="px-3 py-1.5 text-slate-400"))
             for r in trend] or [Tr(Td("暂无数据", colspan=4, cls="px-3 py-3 text-slate-500"))])

        pages_tbl = _dawn_table(
            ["页面", "访问量（7 天）"],
            [Tr(Td(A(escape(r["path"][:70]), href=escape(r["path"]), target="_blank",
                     cls="text-indigo-300 hover:underline font-mono text-xs"),
                   cls="px-3 py-1.5"),
                Td(r["c"], cls="px-3 py-1.5 text-slate-200"))
             for r in top_pages] or [Tr(Td("暂无数据", colspan=2, cls="px-3 py-3 text-slate-500"))])

        refs_tbl = _dawn_table(
            ["来源", "次数"],
            [Tr(Td(escape((r["referer"] or "")[:70]), cls="px-3 py-1.5 text-slate-300 text-xs font-mono"),
                Td(r["c"], cls="px-3 py-1.5 text-slate-200"))
             for r in top_refs] or [Tr(Td("暂无数据", colspan=2, cls="px-3 py-3 text-slate-500"))])

        ips_tbl = _dawn_table(
            ["IP", "请求数（7 天）", "最近访问"],
            [Tr(Td(escape(r["ip"]), cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(r["c"], cls="px-3 py-1.5 text-slate-200"),
                Td(_dawn_ts(r["last"]), cls="px-3 py-1.5 text-slate-400 text-xs"))
             for r in top_ips] or [Tr(Td("暂无数据", colspan=3, cls="px-3 py-3 text-slate-500"))])

        status_tbl = _dawn_table(
            ["状态码", "次数"],
            [Tr(Td(_dawn_status_badge(r["status"]), cls="px-3 py-1.5"),
                Td(r["c"], cls="px-3 py-1.5 text-slate-200"))
             for r in status_dist] or [Tr(Td("暂无数据", colspan=2, cls="px-3 py-3 text-slate-500"))])

        def _panel(title, tbl):
            return Div(H3(title, cls="text-sm font-bold text-slate-300 mb-3"),
                       Div(tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto"),
                       cls="min-w-0")

        content = Div(
            _dawn_tabs("overview"),
            cards,
            _panel("近 7 天趋势", trend_tbl),
            Div(_panel("TOP 页面（7 天）", pages_tbl), _panel("TOP 来源（7 天）", refs_tbl),
                cls="grid lg:grid-cols-2 gap-5 mt-5"),
            Div(_panel("TOP IP（7 天）", ips_tbl), _panel("状态码分布（7 天）", status_tbl),
                cls="grid lg:grid-cols-2 gap-5 mt-5"),
        )
        return _dawn_admin_shell("logwatch", content, "日志分析 · 流量概览")

    # ---- 蜘蛛抓取 ----

    @app.get("/dadmin/plugins/logwatch/spiders")
    async def logwatch_spiders(session, spider: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        db = _dawn_db()
        now = time.time()
        today0 = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        stats = db.execute(
            "SELECT spider, COUNT(*) total, SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) today, "
            "COUNT(DISTINCT path) paths, MAX(ts) last "
            "FROM requests WHERE spider!='' GROUP BY spider ORDER BY total DESC", (today0,)).fetchall()
        where, args = "spider!=''", []
        if spider:
            where += " AND spider=?"
            args.append(spider)
        recent = db.execute(
            f"SELECT ts, spider, method, path, status, ip FROM requests WHERE {where} "
            f"ORDER BY ts DESC LIMIT 60", args).fetchall()
        top_paths = db.execute(
            f"SELECT path, COUNT(*) c FROM requests WHERE {where} "
            f"GROUP BY path ORDER BY c DESC LIMIT 20", args).fetchall()
        db.close()

        kind_map = {v[0]: v[1] for v in _DAWN_SPIDERS.values()}
        stats_tbl = _dawn_table(
            ["蜘蛛", "类别", "总访问", "今日", "抓取页面数", "最近抓取", ""],
            [Tr(Td(escape(r["spider"]), cls="px-3 py-1.5 font-mono text-xs text-slate-200"),
                Td(kind_map.get(r["spider"], "-"), cls="px-3 py-1.5 text-slate-400 text-xs"),
                Td(r["total"], cls="px-3 py-1.5 text-slate-200"),
                Td(r["today"], cls="px-3 py-1.5 text-slate-200"),
                Td(r["paths"], cls="px-3 py-1.5 text-slate-200"),
                Td(_dawn_ts(r["last"]), cls="px-3 py-1.5 text-slate-400 text-xs"),
                Td(A("只看它 →", href=f"/dadmin/plugins/logwatch/spiders?spider={r['spider']}",
                     cls="text-indigo-400 text-xs"), cls="px-3 py-1.5"))
             for r in stats] or [Tr(Td("还没有蜘蛛来访", colspan=7, cls="px-3 py-3 text-slate-500"))])

        recent_tbl = _dawn_table(
            ["时间", "蜘蛛", "路径", "状态", "IP"],
            [Tr(Td(_dawn_ts(r["ts"]), cls="px-3 py-1.5 font-mono text-xs text-slate-400"),
                Td(escape(r["spider"]), cls="px-3 py-1.5 text-xs text-emerald-300"),
                Td(escape(r["path"][:70]), cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(_dawn_status_badge(r["status"]), cls="px-3 py-1.5"),
                Td(escape(r["ip"]), cls="px-3 py-1.5 font-mono text-xs text-slate-500"))
             for r in recent] or [Tr(Td("暂无记录", colspan=5, cls="px-3 py-3 text-slate-500"))])

        paths_tbl = _dawn_table(
            ["被抓取路径", "次数"],
            [Tr(Td(escape(r["path"][:80]), cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(r["c"], cls="px-3 py-1.5 text-slate-200"))
             for r in top_paths] or [Tr(Td("暂无记录", colspan=2, cls="px-3 py-3 text-slate-500"))])

        filter_note = Div(
            Span(f"当前筛选：{escape(spider)}  ", cls="text-amber-300 text-sm"),
            A("清除筛选", href="/dadmin/plugins/logwatch/spiders", cls="text-indigo-400 text-sm"),
        ) if spider else None

        content = Div(
            _dawn_tabs("spiders"),
            filter_note,
            Div(H3("蜘蛛总览", cls="text-sm font-bold text-slate-300 mb-3"),
                Div(stats_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
            Div(
                Div(H3("蜘蛛抓取路径 TOP 20", cls="text-sm font-bold text-slate-300 mb-3"),
                    Div(paths_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
                Div(H3("最近抓取记录（60 条）", cls="text-sm font-bold text-slate-300 mb-3"),
                    Div(recent_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
                cls="grid xl:grid-cols-2 gap-5 mt-5"),
        )
        return _dawn_admin_shell("logwatch", content, "日志分析 · 蜘蛛抓取")

    # ---- 未抓取页面 ----

    @app.get("/dadmin/plugins/logwatch/uncrawled")
    async def logwatch_uncrawled(session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        expected = {}  # path -> (类型, 标题)
        blog = await dawn_get_blog_db()
        try:
            cat_slug = {r[0]: r[1] for r in await (await blog.execute(
                "SELECT name, slug FROM categories")).fetchall()}
            cat_kind = {r[0]: r[1] for r in await (await blog.execute(
                "SELECT slug, is_series FROM categories")).fetchall()}
            for slug, is_series in cat_kind.items():
                expected[("/series/" if is_series else "/") + slug] = (
                    "系列" if is_series else "分类", slug)
            for r in await (await blog.execute("SELECT slug FROM tags")).fetchall():
                expected[f"/tag/{r[0]}"] = ("标签", r[0])
            posts = await (await blog.execute(
                "SELECT slug, category, title FROM posts WHERE is_published=1 AND visibility='public'")).fetchall()
            for slug, cat, title in posts:
                cs = cat_slug.get(cat, "uncategorized")
                expected[f"/{cs}/{slug}"] = ("文章", title)
        finally:
            await blog.close()
        for p, label in [("/", "首页"), ("/about", "关于页"), ("/docs", "文档中心"),
                         ("/feed.xml", "RSS"), ("/sitemap.xml", "站点地图"), ("/robots.txt", "robots")]:
            expected[p] = ("系统", label)

        db = _dawn_db()
        crawled = {r["path"] for r in db.execute(
            "SELECT DISTINCT path FROM requests WHERE spider IN ('Googlebot','Baiduspider','Bingbot')"
        ).fetchall()}
        last_crawl = {r["path"]: r["last"] for r in db.execute(
            "SELECT path, MAX(ts) last FROM requests WHERE spider!='' GROUP BY path").fetchall()}
        db.close()

        uncrawled = [(p, k, t) for p, (k, t) in expected.items() if p not in crawled]
        crawled_known = [(p, k, t, last_crawl.get(p)) for p, (k, t) in expected.items() if p in crawled]

        un_tbl = _dawn_table(
            ["页面", "类型", "标题/说明"],
            [Tr(Td(A(escape(p), href=escape(p), target="_blank",
                     cls="text-indigo-300 hover:underline font-mono text-xs"), cls="px-3 py-1.5"),
                Td(k, cls="px-3 py-1.5 text-slate-400 text-xs"),
                Td(escape((t or "")[:40]), cls="px-3 py-1.5 text-slate-300 text-xs"))
             for p, k, t in sorted(uncrawled)]
            or [Tr(Td("全部页面均已被主流蜘蛛抓取 🎉", colspan=3, cls="px-3 py-3 text-emerald-300"))])

        known_tbl = _dawn_table(
            ["页面", "类型", "最近被抓取"],
            [Tr(Td(escape(p), cls="px-3 py-1.5 font-mono text-xs text-slate-400"),
                Td(k, cls="px-3 py-1.5 text-slate-500 text-xs"),
                Td(_dawn_ts(ts) if ts else "-", cls="px-3 py-1.5 text-slate-400 text-xs"))
             for p, k, t, ts in sorted(crawled_known, key=lambda x: -(x[3] or 0))[:50]])

        content = Div(
            _dawn_tabs("uncrawled"),
            Div(
                _dawn_stat_card("应收录页面", len(expected)),
                _dawn_stat_card("已被主流蜘蛛抓取", len(crawled_known),
                                "Googlebot / Baiduspider / Bingbot"),
                _dawn_stat_card("未被抓取", len(uncrawled),
                                "抓取覆盖率 " + (f"{round(len(crawled_known) / len(expected) * 100)}%" if expected else "-")),
                cls="grid grid-cols-3 gap-3 mb-6"),
            Div(H3("未抓取页面（需关注）", cls="text-sm font-bold text-rose-300 mb-3"),
                Div(un_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
            Div(H3("已抓取页面（最近 50 条）", cls="text-sm font-bold text-slate-300 mb-3 mt-6"),
                Div(known_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
            P("提示：统计口径为主流蜘蛛（Googlebot/Baiduspider/Bingbot）的访问记录；"
              "新站上线初期未抓取属正常，可向 GSC/百度站长手动提交加速。",
              cls="text-xs text-slate-500 mt-4"),
        )
        return _dawn_admin_shell("logwatch", content, "日志分析 · 未抓取页面")

    # ---- 安全与封禁 ----

    @app.get("/dadmin/plugins/logwatch/security")
    async def logwatch_security(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        cfg = _dawn_cfg()
        db = _dawn_db()
        watch = db.execute(
            "SELECT ip, reason, hits, last_seen FROM watchlist ORDER BY last_seen DESC LIMIT 100").fetchall()
        blocked = db.execute(
            "SELECT ip, reason, auto, created_at FROM blocklist ORDER BY created_at DESC").fetchall()
        flagged = db.execute(
            "SELECT ts, ip, path, status, flag FROM requests WHERE flag!='' "
            "ORDER BY ts DESC LIMIT 50").fetchall()
        db.close()

        watch_tbl = _dawn_table(
            ["IP", "触发原因", "命中次数", "最近触发", "操作"],
            [Tr(Td(escape(r["ip"]), cls="px-3 py-1.5 font-mono text-xs text-amber-300"),
                Td(escape(r["reason"]), cls="px-3 py-1.5 text-xs text-slate-300"),
                Td(r["hits"], cls="px-3 py-1.5 text-slate-200"),
                Td(_dawn_ts(r["last_seen"]), cls="px-3 py-1.5 text-xs text-slate-400"),
                Td(Form(
                    Input(type="hidden", name="ip", value=r["ip"]),
                    Button("封禁", type="submit",
                           cls="px-3 py-1 rounded bg-rose-600/80 text-white text-xs font-bold hover:bg-rose-500"),
                    method="post", action="/dadmin/plugins/logwatch/block"), cls="px-3 py-1.5"))
             for r in watch] or [Tr(Td("观察名单为空", colspan=5, cls="px-3 py-3 text-slate-500"))])

        block_tbl = _dawn_table(
            ["IP", "原因", "来源", "封禁时间", "操作"],
            [Tr(Td(escape(r["ip"]), cls="px-3 py-1.5 font-mono text-xs text-rose-300"),
                Td(escape(r["reason"][:60]), cls="px-3 py-1.5 text-xs text-slate-300"),
                Td("自动" if r["auto"] else "手动", cls="px-3 py-1.5 text-xs text-slate-400"),
                Td(_dawn_ts(r["created_at"]), cls="px-3 py-1.5 text-xs text-slate-400"),
                Td(Form(
                    Input(type="hidden", name="ip", value=r["ip"]),
                    Button("解除", type="submit",
                           cls="px-3 py-1 rounded bg-slate-600 text-white text-xs font-bold hover:bg-slate-500"),
                    method="post", action="/dadmin/plugins/logwatch/unblock"), cls="px-3 py-1.5"))
             for r in blocked] or [Tr(Td("暂无封禁", colspan=5, cls="px-3 py-3 text-slate-500"))])

        flagged_tbl = _dawn_table(
            ["时间", "IP", "路径", "状态", "标记"],
            [Tr(Td(_dawn_ts(r["ts"]), cls="px-3 py-1.5 font-mono text-xs text-slate-400"),
                Td(escape(r["ip"]), cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(escape(r["path"][:60]), cls="px-3 py-1.5 font-mono text-xs text-slate-300"),
                Td(_dawn_status_badge(r["status"]), cls="px-3 py-1.5"),
                Td(_dawn_flag_badge(r["flag"]), cls="px-3 py-1.5"))
             for r in flagged] or [Tr(Td("暂无异常请求", colspan=5, cls="px-3 py-3 text-slate-500"))])

        def _check(key, label):
            return Label(
                Input(type="checkbox", name=key, value="1", checked=(cfg[key] == "1"),
                      cls="mr-2 accent-indigo-500"),
                Span(label, cls="text-sm text-slate-300"), cls="flex items-center")

        cfg_form = Form(
            H3("检测与封禁策略", cls="text-sm font-bold text-slate-300 mb-3"),
            Div(
                Div(Label("日志保留天数", cls="text-xs text-slate-400 block mb-1"),
                    Input(name="retention_days", value=cfg["retention_days"], cls=DAWN_INPUT)),
                Div(Label("高频阈值（次/分钟）", cls="text-xs text-slate-400 block mb-1"),
                    Input(name="rate_limit", value=cfg["rate_limit"], cls=DAWN_INPUT)),
                Div(Label("404 洪水阈值（次/小时）", cls="text-xs text-slate-400 block mb-1"),
                    Input(name="flood_404", value=cfg["flood_404"], cls=DAWN_INPUT)),
                cls="grid md:grid-cols-3 gap-3 mb-3"),
            Div(_check("auto_block", "命中阈值自动封禁 IP"),
                _check("block_probes", "路径探测直接封禁 IP（推荐）"),
                cls="flex flex-wrap gap-6 mb-4"),
            Button("保存设置", type="submit", cls=DAWN_BTN),
            method="post", action="/dadmin/plugins/logwatch/config")

        manual_form = Form(
            Div(Input(name="ip", placeholder="手动封禁 IP，如 1.2.3.4", cls=DAWN_INPUT + " flex-1"),
                Button("封禁", type="submit", cls=DAWN_BTN + " ml-2"),
                cls="flex items-center"),
            method="post", action="/dadmin/plugins/logwatch/block", cls="mt-4")

        content = Div(
            _dawn_tabs("security"),
            _dawn_msg(msg) if msg else None,
            Div(cfg_form, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-5 mb-6"),
            Div(H3("观察名单（自动标记的可疑 IP）", cls="text-sm font-bold text-amber-300 mb-3"),
                Div(watch_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
            Div(H3("封禁名单", cls="text-sm font-bold text-rose-300 mb-3 mt-6"),
                Div(block_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto"),
                manual_form),
            Div(H3("最近异常请求（50 条）", cls="text-sm font-bold text-slate-300 mb-3 mt-6"),
                Div(flagged_tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto")),
        )
        return _dawn_admin_shell("logwatch", content, "日志分析 · 安全与封禁")

    @app.post("/dadmin/plugins/logwatch/config")
    async def logwatch_config_save(session, retention_days: str = "30", rate_limit: str = "120",
                                   flood_404: str = "30", auto_block: str = "", block_probes: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        db = _dawn_db()
        for k, v in [("retention_days", retention_days), ("rate_limit", rate_limit),
                     ("flood_404", flood_404),
                     ("auto_block", "1" if auto_block == "1" else "0"),
                     ("block_probes", "1" if block_probes == "1" else "0")]:
            db.execute("INSERT INTO config(key,value) VALUES(?,?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        db.commit()
        db.close()
        return RedirectResponse("/dadmin/plugins/logwatch/security?msg=" + "设置已保存", status_code=303)

    @app.post("/dadmin/plugins/logwatch/block")
    async def logwatch_block(session, ip: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        ip = (ip or "").strip()
        if ip:
            db = _dawn_db()
            db.execute("INSERT OR REPLACE INTO blocklist(ip, reason, auto, created_at) VALUES(?,?,0,?)",
                       (ip, "手动封禁", time.time()))
            db.commit()
            db.close()
        return RedirectResponse("/dadmin/plugins/logwatch/security?msg=" + f"已封禁 {ip}", status_code=303)

    @app.post("/dadmin/plugins/logwatch/unblock")
    async def logwatch_unblock(session, ip: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        ip = (ip or "").strip()
        if ip:
            db = _dawn_db()
            db.execute("DELETE FROM blocklist WHERE ip=?", (ip,))
            db.execute("DELETE FROM watchlist WHERE ip=?", (ip,))
            db.commit()
            db.close()
        return RedirectResponse("/dadmin/plugins/logwatch/security?msg=" + f"已解除 {ip}", status_code=303)

    # ---- 实时日志 ----

    @app.get("/dadmin/plugins/logwatch/live")
    async def logwatch_live(session, spider: str = "", flag: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        where, args = "1=1", []
        if spider == "1":
            where += " AND spider!=''"
        if flag == "1":
            where += " AND flag!=''"
        db = _dawn_db()
        rows = db.execute(
            f"SELECT ts, ip, method, path, status, ms, spider, flag FROM requests "
            f"WHERE {where} ORDER BY ts DESC LIMIT 100", args).fetchall()
        db.close()

        filters = Div(
            A("全部", href="/dadmin/plugins/logwatch/live",
              cls="px-3 py-1.5 rounded-lg text-xs font-bold " + (
                  "bg-indigo-600 text-white" if not (spider or flag) else "text-slate-400")),
            A("只看蜘蛛", href="/dadmin/plugins/logwatch/live?spider=1",
              cls="px-3 py-1.5 rounded-lg text-xs font-bold " + (
                  "bg-indigo-600 text-white" if spider == "1" else "text-slate-400")),
            A("只看异常", href="/dadmin/plugins/logwatch/live?flag=1",
              cls="px-3 py-1.5 rounded-lg text-xs font-bold " + (
                  "bg-indigo-600 text-white" if flag == "1" else "text-slate-400")),
            Span("每 8 秒自动刷新", cls="text-xs text-slate-500 ml-3"),
            cls="flex items-center gap-2 mb-4")

        tbl = _dawn_table(
            ["时间", "IP", "蜘蛛", "方法", "路径", "状态", "耗时", "标记"],
            [Tr(Td(_dawn_ts(r["ts"]), cls="px-3 py-1 font-mono text-[11px] text-slate-400 whitespace-nowrap"),
                Td(escape(r["ip"]), cls="px-3 py-1 font-mono text-[11px] text-slate-300"),
                Td(escape(r["spider"]) if r["spider"] else Span("-", cls="text-slate-600"),
                   cls="px-3 py-1 text-[11px] text-emerald-300"),
                Td(escape(r["method"]), cls="px-3 py-1 font-mono text-[11px] text-slate-400"),
                Td(escape(r["path"][:60]), cls="px-3 py-1 font-mono text-[11px] text-slate-300"),
                Td(_dawn_status_badge(r["status"]), cls="px-3 py-1"),
                Td(f"{r['ms']:.0f}ms", cls="px-3 py-1 font-mono text-[11px] text-slate-400"),
                Td(_dawn_flag_badge(r["flag"]), cls="px-3 py-1"))
             for r in rows] or [Tr(Td("暂无记录", colspan=8, cls="px-3 py-3 text-slate-500"))])

        content = Div(
            _dawn_tabs("live"),
            filters,
            Div(tbl, cls="bg-slate-800/60 rounded-xl border border-slate-700/60 p-3 overflow-x-auto"),
            Script("setTimeout(function(){location.reload()}, 8000)"),
        )
        return _dawn_admin_shell("logwatch", content, "日志分析 · 实时日志")
