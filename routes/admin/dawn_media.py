# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/media.py
# 媒体库

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
    @app.get("/dadmin/media")
    async def admin_media(session, msg: str = ""):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        assets = await DawnBlogService.list_media_assets(limit=120)
        usage_counts = await DawnBlogService.get_media_usage_counts()
        cards = []
        for a in assets:
            cards.append(Div(
                Img(src=a.get("thumb_url") or a.get("file_url"), alt=a.get("alt_text", ""), cls="w-full h-32 object-cover rounded-t-xl bg-slate-800"),
                Div(
                    P(a.get("file_url", ""), cls="text-indigo-300 text-[11px] font-mono break-all line-clamp-2"),
                    P(f"{a.get('original_name', '')} · {(a.get('size_bytes', 0) or 0) // 1024}KB · 被引用 {usage_counts.get(a.get('id'), 0)} 次",
                      cls="text-slate-500 text-[11px] mt-1"),
                    Div(
                        Button("复制URL", type="button", cls=DAWN_BTN_GHOST,
                               onclick=f"navigator.clipboard.writeText('{a.get('file_url','')}');this.textContent='已复制'"),
                        Form(Button("删除", type="submit", cls=DAWN_BTN_DANGER, onclick="return confirm('确认删除该媒体文件？')"),
                             method="post", action=f"/dadmin/media/delete/{a.get('id')}", style="display:inline"),
                        cls="flex items-center justify-between mt-2"
                    ),
                    cls="p-3"
                ),
                cls="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden"
            ))

        return _dawn_admin_shell("media", Div(
            _dawn_msg(msg) if msg else None,
            H1("媒体库", cls="text-2xl font-black text-white mb-6"),
            Form(
                Input(type="file", name="file", required=True, accept="image/*",
                      cls="text-slate-400 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:text-white file:text-sm file:font-bold"),
                Button("上传", type="submit", cls=DAWN_BTN + " ml-3"),
                method="post", action="/dadmin/media/upload", enctype="multipart/form-data",
                cls="mb-8 p-4 rounded-xl border border-slate-800 bg-slate-900/40"
            ),
            Div(*cards, cls="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4") if cards
            else P("暂无媒体文件", cls="text-slate-500"),
        ))

    @app.post("/dadmin/media/upload")
    async def admin_media_upload(request, session):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        form = await request.form()
        upload = form.get("file")
        if not upload or not getattr(upload, "filename", None):
            return RedirectResponse("/dadmin/media?msg=未选择文件", status_code=303)
        content = await upload.read()
        if len(content) > 8 * 1024 * 1024:
            return RedirectResponse("/dadmin/media?msg=文件超过8MB", status_code=303)
        try:
            asset = DawnBlogImageService._save_image(content, upload.filename, created_by="admin-upload", name_hint=Path(upload.filename).stem)
            await DawnBlogService.create_media_asset(asset)
        except Exception as e:
            return RedirectResponse(f"/dadmin/media?msg=上传失败：{str(e)[:80]}", status_code=303)
        return RedirectResponse("/dadmin/media?msg=已上传", status_code=303)

    @app.post("/dadmin/api/media/upload")
    async def admin_media_upload_json(request, session):
        """Vditor 编辑器 AJAX 上传（JSON 响应，格式与 Vditor upload 协议一致）"""
        if not _dawn_require_admin(session):
            return JSONResponse({"msg": "未登录", "code": 1}, status_code=401)
        form = await request.form()
        files = [v for v in form.values() if hasattr(v, "filename") and v.filename]
        succ, errs = {}, []
        for upload in files:
            content = await upload.read()
            if len(content) > 8 * 1024 * 1024:
                errs.append(upload.filename)
                continue
            try:
                asset = DawnBlogImageService._save_image(content, upload.filename, created_by="editor-upload", name_hint=Path(upload.filename).stem)
                await DawnBlogService.create_media_asset(asset)
                succ[upload.filename] = asset.get("file_url", "")
            except Exception:
                errs.append(upload.filename)
        return JSONResponse({
            "msg": "",
            "code": 0,
            "data": {"errFiles": errs, "succMap": succ},
        })

    @app.post("/dadmin/media/delete/{media_id}")
    async def admin_media_delete(session, media_id: int):
        if not _dawn_require_admin(session):
            return RedirectResponse("/dadmin/login")
        row = await DawnBlogService.delete_media_asset(media_id)
        if row:
            for key in ("file_path", "thumb_path"):
                fp = row.get(key) or ""
                try:
                    if fp and os.path.exists(fp):
                        os.remove(fp)
                except Exception:
                    pass
        return RedirectResponse("/dadmin/media?msg=已删除", status_code=303)

