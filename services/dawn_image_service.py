# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
import datetime
import os
import re
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from PIL import Image

from blog.dawn_crud import DawnBlogCRUD


DAWN_BASE_DIR = Path(__file__).parent.parent
DAWN_BLOG_UPLOAD_ROOT = DAWN_BASE_DIR / "static" / "uploads" / "blog"
DAWN_SITE_HOST = urlparse(os.environ.get("SITE_BASE_URL", "http://localhost:5010")).netloc.lower()
DAWN_REMOTE_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(([^\)]+)\)|<img[^>]+src=[\"']([^\"']+)[\"']",
    re.I,
)


class DawnBlogImageService:
    @staticmethod
    def semantic_slug(text: str, fallback: str = "blog-image") -> str:
        raw = re.sub(r"\s+", " ", str(text or "").strip())
        if not raw:
            return fallback

        slug = DawnBlogCRUD.generate_slug_from_translation(raw)
        if slug and not re.fullmatch(r"(?:post-\d{8}|\d+)", slug):
            return slug[:96]

        ascii_parts = re.findall(r"[a-z0-9]+", raw.lower())
        if ascii_parts:
            return "-".join(ascii_parts)[:96]
        return fallback

    @staticmethod
    def semantic_base_name(name_hint: str = "", fallback: str = "blog-image", unique_token: str | None = None) -> str:
        stem = DawnBlogImageService.semantic_slug(name_hint or fallback, fallback=fallback)
        token = (unique_token or uuid.uuid4().hex[:8]).strip("-")
        return f"{stem}-{token}" if token else stem

    @staticmethod
    def dated_upload_dir(now: datetime.datetime | None = None) -> Path:
        current = now or datetime.datetime.now()
        upload_dir = DAWN_BLOG_UPLOAD_ROOT / current.strftime("%Y") / current.strftime("%m") / current.strftime("%d")
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    @staticmethod
    def file_url_for(path: Path) -> str:
        rel = path.relative_to(DAWN_BLOG_UPLOAD_ROOT).as_posix()
        return f"/uploads/blog/{rel}"

    @staticmethod
    def _asset_payload_for_file(file_path: Path, original_name: str, mime_type: str, size_bytes: int, created_by: str) -> dict:
        return {
            "file_name": file_path.name,
            "original_name": original_name,
            "file_url": DawnBlogImageService.file_url_for(file_path),
            "file_path": str(file_path),
            "thumb_url": "",
            "thumb_path": "",
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "width": 0,
            "height": 0,
            "alt_text": re.sub(r"[-_]+", " ", file_path.stem).strip()[:120] or "blog media",
            "caption": "",
            "created_by": created_by,
        }

    @staticmethod
    def is_remote_image_url(url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.netloc or "").lower()
        return not (host == DAWN_SITE_HOST or host.endswith(f".{DAWN_SITE_HOST}") or host in {"localhost", "127.0.0.1"})

    @staticmethod
    def extract_remote_image_urls(content: str = "", cover_image: str = "") -> list[str]:
        urls = set()
        for md_url, html_url in DAWN_REMOTE_IMAGE_RE.findall(content or ""):
            url = (md_url or html_url or "").strip()
            if DawnBlogImageService.is_remote_image_url(url):
                urls.add(url)
        if DawnBlogImageService.is_remote_image_url(cover_image or ""):
            urls.add(str(cover_image).strip())
        return sorted(urls)

    @staticmethod
    def _alt_text_from_url(url: str) -> str:
        name = Path(urlparse(url).path).stem or "blog-image"
        return re.sub(r"[-_]+", " ", name).strip()[:120] or "blog image"

    @staticmethod
    def _save_image(content: bytes, source_url: str, created_by: str = "blog-auto-localizer", name_hint: str = "", unique_token: str | None = None) -> dict:
        upload_dir = DawnBlogImageService.dated_upload_dir()
        original_name = Path(urlparse(source_url).path).name or "remote-image"
        ext = Path(original_name).suffix.lower()
        base_name = DawnBlogImageService.semantic_base_name(name_hint or original_name or DawnBlogImageService._alt_text_from_url(source_url), fallback="blog-image", unique_token=unique_token)

        if ext == ".svg" or content.lstrip()[:120].lower().startswith(b"<svg"):
            file_path = upload_dir / f"{base_name}.svg"
            file_path.write_bytes(content)
            return {
                "file_name": file_path.name,
                "original_name": original_name,
                "file_url": DawnBlogImageService.file_url_for(file_path),
                "file_path": str(file_path),
                "thumb_url": "",
                "thumb_path": "",
                "mime_type": "image/svg+xml",
                "size_bytes": len(content),
                "width": 0,
                "height": 0,
                "alt_text": DawnBlogImageService._alt_text_from_url(source_url),
                "caption": "",
                "created_by": created_by,
            }

        image = Image.open(BytesIO(content))
        image = image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
        if image.width > 1600:
            new_height = int((1600 / image.width) * image.height)
            image = image.resize((1600, new_height), Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(output, format="WEBP", quality=82, optimize=True)
        saved = output.getvalue()
        file_path = upload_dir / f"{base_name}.webp"
        file_path.write_bytes(saved)

        thumb = image.copy()
        thumb.thumbnail((480, 480), Image.Resampling.LANCZOS)
        thumb_output = BytesIO()
        thumb.save(thumb_output, format="WEBP", quality=76, optimize=True)
        thumb_path = upload_dir / f"{base_name}_thumb.webp"
        thumb_path.write_bytes(thumb_output.getvalue())

        return {
            "file_name": file_path.name,
            "original_name": original_name,
            "file_url": DawnBlogImageService.file_url_for(file_path),
            "file_path": str(file_path),
            "thumb_url": DawnBlogImageService.file_url_for(thumb_path),
            "thumb_path": str(thumb_path),
            "mime_type": "image/webp",
            "size_bytes": len(saved),
            "width": image.width,
            "height": image.height,
            "alt_text": DawnBlogImageService._alt_text_from_url(source_url),
            "caption": "",
            "created_by": created_by,
        }

    @staticmethod
    async def _download_image(url: str) -> bytes:
        timeout = aiohttp.ClientTimeout(total=25)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DawnCMSImageLocalizer/1.0)"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                content_type = (resp.headers.get("content-type") or "").lower()
                content = await resp.read()
                if not content_type.startswith("image/") and not content.lstrip()[:120].lower().startswith(b"<svg"):
                    raise ValueError(f"远程资源不是图片: {content_type}")
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError("远程图片超过 8MB，已跳过自动本地化")
                return content

    @staticmethod
    async def _download_binary(url: str, max_size_bytes: int = 25 * 1024 * 1024) -> tuple[bytes, str]:
        timeout = aiohttp.ClientTimeout(total=60)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DawnCMSMediaFetcher/1.0)"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                content_type = (resp.headers.get("content-type") or "application/octet-stream").lower()
                content = await resp.read()
                if len(content) > max_size_bytes:
                    raise ValueError("远程媒体文件过大，已跳过保存")
                return content, content_type

    @staticmethod
    async def localize_single_remote_image(url: str, created_by: str = "blog-auto-localizer", name_hint: str = "", unique_token: str | None = None) -> dict:
        content_bytes = await DawnBlogImageService._download_image(url)
        asset = DawnBlogImageService._save_image(content_bytes, url, created_by=created_by, name_hint=name_hint, unique_token=unique_token)
        await DawnBlogCRUD.create_media_asset(asset)
        return asset

    @staticmethod
    async def localize_payload_images(data: dict, created_by: str = "blog-auto-localizer") -> dict:
        content = str(data.get("content", "") or "")
        cover_image = str(data.get("cover_image", "") or "")
        urls = DawnBlogImageService.extract_remote_image_urls(content, cover_image)
        if not urls:
            return data

        name_hints = {}
        for alt_text, url in re.findall(r"!\[([^\]]*)\]\(([^\)]+)\)", content or ""):
            if DawnBlogImageService.is_remote_image_url(url):
                name_hints.setdefault(url.strip(), str(alt_text or "").strip())
        if DawnBlogImageService.is_remote_image_url(cover_image or ""):
            name_hints.setdefault(str(cover_image).strip(), "blog-cover")

        replacements = {}
        for url in urls:
            try:
                asset = await DawnBlogImageService.localize_single_remote_image(
                    url,
                    created_by=created_by,
                    name_hint=name_hints.get(url, "") or Path(urlparse(url).path).stem,
                )
                replacements[url] = asset["file_url"]
            except Exception as exc:
                print(f"⚠️ [DawnBlogImageService] 远程图片本地化失败: {url} :: {str(exc)[:180]}")

        if not replacements:
            return data

        for old_url, new_url in replacements.items():
            content = content.replace(old_url, new_url)
            if cover_image == old_url:
                cover_image = new_url

        data["content"] = content
        data["cover_image"] = cover_image
        return data
