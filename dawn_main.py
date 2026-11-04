# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================

# dawn_main.py
# DawnCMS 独立博客系统入口

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fasthtml.common import fast_app, serve
from dawn_config import DAWN_PORT, dawn_site_name
from blog.dawn_factory import dawn_init_blog_db
from routes import dawn_frontend, admin, dawn_auth, dawn_docs

Path("database").mkdir(exist_ok=True)
Path("static/uploads/blog").mkdir(parents=True, exist_ok=True)

app, rt = fast_app(
    secret_key=os.environ.get("SESSION_SECRET", "blog-standalone-secret-change-me"),
    static_path="static",
)

from starlette.responses import FileResponse

@app.get("/static/{fname:path}")
async def _dawn_static_files(fname: str):
    # vendor 资源（Vditor/Tailwind/编辑器 JS）内容稳定，强缓存 7 天；其余 1 小时
    resp = FileResponse(f"static/{fname}")
    resp.headers["Cache-Control"] = "public, max-age=604800" if fname.startswith("vendor/") else "public, max-age=3600"
    return resp


from starlette.middleware.base import BaseHTTPMiddleware


async def _dawn_theme_preview_dispatch(request, call_next):
    q = request.query_params
    if "__theme_preview" in q:
        import dawn_themes
        dawn_themes.dawn_set_preview_from_query(q.get("__theme_preview", ""), q.get("__sig", ""))
    return await call_next(request)


app.add_middleware(BaseHTTPMiddleware, dispatch=_dawn_theme_preview_dispatch)

admin.dawn_setup(app)
dawn_auth.dawn_setup(app)
dawn_docs.dawn_setup(app)

from plugins import dawn_load_plugins
dawn_load_plugins(app)

dawn_frontend.dawn_setup(app)


def _dawn_demote_static_route(app):
    routes = app.router.routes
    static_routes = [r for r in routes if getattr(r, "path", "").startswith("/{fname")]
    other_routes = [r for r in routes if not getattr(r, "path", "").startswith("/{fname")]
    app.router.routes[:] = other_routes + static_routes


_dawn_demote_static_route(app)


# ---------- 404 / 500 主题化错误页 ----------

from fasthtml.common import A, Div, H1, P, Span, to_xml
from starlette.responses import HTMLResponse
from ui.dawn_layout import dawn_wrapper
import dawn_themes


def _dawn_error_ctx(request, code: int, title: str, desc: str):
    session = getattr(request, "session", None)
    ctx = dawn_frontend._dawn_ctx(session, f"{code} {title}", desc)
    ctx.update({
        "robots_meta": "noindex, nofollow",
        "error_code": code,
        "error_title": title,
        "error_message": desc,
        "request_path": request.url.path,
    })
    return ctx, (request.cookies.get("site_lang") or "")


def _dawn_error_page(code: int, title: str, desc: str, session: dict | None):
    return dawn_wrapper(
        Div(
            Span(f"{dawn_site_name()} · ERROR", cls="eyebrow block mb-5"),
            H1(f"{code}", cls="ff-serif text-7xl font-black text-[var(--ink)] mb-4"),
            P(title, cls="ff-serif text-2xl font-bold text-[var(--ink)] mb-3"),
            P(desc, cls="text-[var(--muted)] mb-10"),
            Div(
                A("返回首页", href="/", cls="btn-primary"),
                A("浏览文档", href="/docs", cls="btn-secondary ml-3"),
                cls="flex items-center justify-center"
            ),
            cls="max-w-[860px] mx-auto px-6 py-28 text-center"
        ),
        title=f"{code} {title}",
        description=desc,
        session=session,
    )


async def _dawn_404(request, exc):
    title, desc = "页面不存在", "你要找的页面可能已被移动、删除，或从未存在过。"
    try:
        ctx, lang = _dawn_error_ctx(request, 404, title, desc)
        return HTMLResponse(dawn_themes.dawn_render("404.html", lang=lang, **ctx), status_code=404)
    except Exception:
        return HTMLResponse(to_xml(_dawn_error_page(
            404, title, desc, getattr(request, "session", None))), status_code=404)


async def _dawn_500(request, exc):
    title, desc = "服务器开小差了", "内部错误已记录，请稍后再试。"
    try:
        ctx, lang = _dawn_error_ctx(request, 500, title, desc)
        return HTMLResponse(dawn_themes.dawn_render("404.html", lang=lang, **ctx), status_code=500)
    except Exception:
        return HTMLResponse(to_xml(_dawn_error_page(
            500, title, desc, getattr(request, "session", None))), status_code=500)


app.exception_handlers[404] = _dawn_404
app.exception_handlers[500] = _dawn_500


@app.on_event("startup")
async def _dawn_startup():
    await dawn_init_blog_db()


if __name__ == "__main__":
    # 不能直接 serve()：它固定以导入字符串 "dawn_main:app" 启动 uvicorn，
    # 模块会被二次导入，而 plugins/__init__.py 的 _dawn_loaded 缓存会让
    # dawn_load_plugins 在新 app 上提前返回，插件路由（如 i18n 的 /en-us）丢失。
    # 直接传 app 对象可保证注册过插件路由的实例被服务。
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DAWN_PORT)
