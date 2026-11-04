# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# services/blog_service.py
# 博客业务逻辑服务

import re

from blog.dawn_crud import DawnBlogCRUD
from services.dawn_markdown_renderer import DawnMarkdownRenderer
from typing import Optional, List
from datetime import datetime
from services.dawn_image_service import DawnBlogImageService

class DawnBlogService:


    @staticmethod
    def _is_live(post: dict, is_admin: bool = False) -> bool:
        """定时发布：scheduled_at 在未来的文章对外不可见（管理员可见）"""
        if is_admin:
            return True
        sched = str((post or {}).get('scheduled_at') or '').strip()
        if not sched:
            return True
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return sched[:16].replace('T', ' ') <= now

    @staticmethod
    def _filter_live(posts: list, is_admin: bool = False) -> list:
        return [p for p in posts if DawnBlogService._is_live(p, is_admin)]

    @staticmethod
    def _can_view_visibility(visibility: str, is_admin: bool = False, is_member: bool = False) -> bool:
        code = str(visibility or 'public')
        if is_admin:
            return True
        if code == 'public':
            return True
        if code == 'member':
            return is_member
        return False

    @staticmethod
    def _can_list_visibility(visibility: str, is_admin: bool = False) -> bool:
        code = str(visibility or 'public')
        if is_admin:
            return True
        return code in ('public', 'member')

    @staticmethod
    async def get_all_posts(published_only: bool = True, include_admin: bool = False) -> List[dict]:
        rows = await DawnBlogCRUD.list_posts(published_only=published_only, include_admin=include_admin)
        rows = [r for r in rows if DawnBlogService._can_list_visibility(r.get('visibility', 'public'), include_admin)]
        return DawnBlogService._filter_live(rows, include_admin)

    @staticmethod
    async def get_post(slug: str, is_admin: bool = False, is_member: bool = False) -> Optional[dict]:
        post = await DawnBlogCRUD.get_post_by_slug_admin(slug)
        if not post:
            return None
        if not post.get('is_published') and not is_admin:
            return None
        if not DawnBlogService._is_live(post, is_admin):
            return None
        if not DawnBlogService._can_list_visibility(post.get('visibility', 'public'), is_admin):
            return None
        post['gated'] = not DawnBlogService._can_view_visibility(post.get('visibility', 'public'), is_admin, is_member)
        if post['gated']:
            return post
        await DawnBlogCRUD.increment_view_count(post['id'])
        post['html_content'] = DawnMarkdownRenderer.render_with_prose(post['content'])
        return post

    @staticmethod
    async def get_post_by_id(post_id: int) -> Optional[dict]:
        return await DawnBlogCRUD.get_post_by_id(post_id)

    @staticmethod
    async def create_post(data: dict) -> int:
        data = await DawnBlogImageService.localize_payload_images(data, created_by=data.get('author', 'blog-create'))
        return await DawnBlogCRUD.create_post(data)

    @staticmethod
    async def update_post(post_id: int, data: dict) -> bool:
        data = await DawnBlogImageService.localize_payload_images(data, created_by=data.get('author', 'blog-update'))
        return await DawnBlogCRUD.update_post(post_id, data)

    @staticmethod
    async def delete_post(post_id: int) -> bool:
        return await DawnBlogCRUD.delete_post(post_id)

    @staticmethod
    async def get_categories() -> List[dict]:
        return await DawnBlogCRUD.get_categories()

    @staticmethod
    async def get_series() -> List[dict]:
        return await DawnBlogCRUD.get_series()

    @staticmethod
    async def get_series_by_id(series_id: int) -> dict | None:
        return await DawnBlogCRUD.get_series_by_id(series_id)

    @staticmethod
    async def get_series_by_slug(slug: str) -> dict | None:
        return await DawnBlogCRUD.get_series_by_slug(slug)

    @staticmethod
    async def create_series(data: dict) -> int:
        return await DawnBlogCRUD.create_series(data)

    @staticmethod
    async def update_series(series_id: int, data: dict) -> bool:
        return await DawnBlogCRUD.update_series(series_id, data)

    @staticmethod
    async def delete_series(series_id: int) -> bool:
        return await DawnBlogCRUD.delete_series(series_id)

    @staticmethod
    async def get_series_posts(series_id: int, include_admin: bool = False) -> List[dict]:
        rows = await DawnBlogCRUD.get_series_posts(series_id)
        rows = [r for r in rows if DawnBlogService._can_list_visibility(r.get('visibility', 'public'), include_admin)]
        return DawnBlogService._filter_live(rows, include_admin)

    @staticmethod
    async def get_posts_by_category(category: str, include_admin: bool = False) -> List[dict]:
        rows = await DawnBlogCRUD.get_posts_by_category(category, include_admin=include_admin)
        rows = [r for r in rows if DawnBlogService._can_list_visibility(r.get('visibility', 'public'), include_admin)]
        return DawnBlogService._filter_live(rows, include_admin)

    @staticmethod
    async def get_all_posts_for_admin() -> List[dict]:
        return await DawnBlogCRUD.get_all_posts_for_admin()

    @staticmethod
    async def get_admin_posts_filtered(q: str = "", status: str = "", category: str = "") -> List[dict]:
        return await DawnBlogCRUD.get_admin_posts_filtered(q, status, category)

    @staticmethod
    async def search_posts(keyword: str) -> List[dict]:
        return DawnBlogService._filter_live(await DawnBlogCRUD.search_posts(keyword))

    # ---- Tags ----

    @staticmethod
    async def list_tags() -> List[dict]:
        return await DawnBlogCRUD.list_tags()

    @staticmethod
    async def list_tags_with_counts() -> List[dict]:
        return await DawnBlogCRUD.list_tags_with_counts()

    @staticmethod
    async def create_tag(name: str, slug: str = '') -> int:
        return await DawnBlogCRUD.create_tag(name, slug)

    @staticmethod
    async def delete_tag(tag_id: int) -> bool:
        return await DawnBlogCRUD.delete_tag(tag_id)

    @staticmethod
    async def get_tag_by_slug(slug: str) -> Optional[dict]:
        return await DawnBlogCRUD.get_tag_by_slug(slug)

    @staticmethod
    async def get_post_tags(post_id: int) -> List[dict]:
        return await DawnBlogCRUD.get_post_tags(post_id)

    @staticmethod
    async def get_post_tag_ids(post_id: int) -> list:
        return await DawnBlogCRUD.get_post_tag_ids(post_id)

    @staticmethod
    async def get_tags_for_posts(post_ids: list) -> dict:
        return await DawnBlogCRUD.get_tags_for_posts(post_ids)

    @staticmethod
    async def set_post_tags(post_id: int, tag_ids: list) -> None:
        await DawnBlogCRUD.set_post_tags(post_id, tag_ids)

    @staticmethod
    async def get_posts_by_tag_slug(tag_slug: str, include_admin: bool = False) -> List[dict]:
        rows = await DawnBlogCRUD.get_posts_by_tag_slug(tag_slug, include_admin=include_admin)
        rows = [r for r in rows if DawnBlogService._can_list_visibility(r.get('visibility', 'public'), include_admin)]
        return DawnBlogService._filter_live(rows, include_admin)

    @staticmethod
    async def publish_post(post_id: int) -> bool:
        return await DawnBlogCRUD.update_post(post_id, {'is_published': 1})

    @staticmethod
    async def unpublish_post(post_id: int) -> bool:
        return await DawnBlogCRUD.update_post(post_id, {'is_published': 0})

    @staticmethod
    def preview_payload(md_content: str) -> dict:
        return DawnMarkdownRenderer.render_preview_payload(md_content)

    @staticmethod
    async def create_media_asset(data: dict) -> int:
        return await DawnBlogCRUD.create_media_asset(data)

    @staticmethod
    async def list_media_assets(limit: int = 80) -> List[dict]:
        return await DawnBlogCRUD.list_media_assets(limit=limit)

    @staticmethod
    async def get_media_asset(media_id: int) -> Optional[dict]:
        return await DawnBlogCRUD.get_media_asset(media_id)

    @staticmethod
    async def update_media_asset(media_id: int, data: dict) -> bool:
        return await DawnBlogCRUD.update_media_asset(media_id, data)

    @staticmethod
    async def delete_media_asset(media_id: int) -> Optional[dict]:
        return await DawnBlogCRUD.delete_media_asset(media_id)

    @staticmethod
    async def sync_post_media_usages(post_id: int, content: str, cover_image: str = '') -> None:
        urls = DawnBlogCRUD.extract_media_urls(content or '', cover_image or '')
        usages = []
        for url in urls:
            asset = await DawnBlogCRUD.get_media_asset_by_url(url)
            if not asset:
                continue
            usage_type = 'cover_image' if cover_image and url == cover_image else 'content_image'
            usages.append((int(asset['id']), usage_type))
        await DawnBlogCRUD.replace_post_media_usages(post_id, usages)

    @staticmethod
    async def get_media_usage_counts() -> dict:
        return await DawnBlogCRUD.list_media_usage_counts()

    @staticmethod
    async def bulk_delete_media_assets(media_ids: list) -> list:
        return await DawnBlogCRUD.bulk_delete_media_assets(media_ids)

    @staticmethod
    async def bulk_fill_media_alt(media_ids: list) -> int:
        return await DawnBlogCRUD.bulk_fill_media_alt(media_ids)

    @staticmethod
    async def replace_media_url_references(old_url: str, new_url: str) -> int:
        return await DawnBlogCRUD.replace_media_url_references(old_url, new_url)

    @staticmethod
    async def create_post_revision(post_id: int, data: dict, edited_by: str = '') -> int:
        return await DawnBlogCRUD.create_post_revision(post_id, data, edited_by)

    @staticmethod
    async def list_post_revisions(post_id: int, limit: int = 10) -> List[dict]:
        return await DawnBlogCRUD.list_post_revisions(post_id, limit=limit)

    @staticmethod
    async def restore_post_revision(revision_id: int) -> Optional[int]:
        revision = await DawnBlogCRUD.get_post_revision(revision_id)
        if not revision:
            return None
        await DawnBlogCRUD.update_post(revision['post_id'], {
            'title': revision.get('title', ''),
            'description': revision.get('description', ''),
            'keywords': revision.get('keywords', ''),
            'content': revision.get('content', ''),
        })
        restored = await DawnBlogCRUD.get_post_by_id(revision['post_id'])
        if restored:
            await DawnBlogService.sync_post_media_usages(revision['post_id'], restored.get('content', ''), restored.get('cover_image', ''))
        return revision['post_id']

    @staticmethod
    async def register_slug_redirect(post_id: int, old_slug: str, new_slug: str) -> None:
        await DawnBlogCRUD.upsert_slug_redirect(post_id, old_slug, new_slug)

    @staticmethod
    async def get_redirect_by_old_slug(old_slug: str) -> Optional[dict]:
        return await DawnBlogCRUD.get_redirect_by_old_slug(old_slug)

    @staticmethod
    async def create_category(data: dict) -> int:
        return await DawnBlogCRUD.create_category(data)

    @staticmethod
    async def update_category(cat_id: int, data: dict) -> bool:
        return await DawnBlogCRUD.update_category(cat_id, data)

    @staticmethod
    async def delete_category(cat_id: int) -> bool:
        return await DawnBlogCRUD.delete_category(cat_id)

    @staticmethod
    async def normalize_non_ascii_slugs() -> int:
        return await DawnBlogCRUD.normalize_non_ascii_slugs()

    @staticmethod
    async def generate_slug_candidates(title: str, current_post_id: int = 0) -> dict:
        base_rule = DawnBlogCRUD.generate_slug_from_translation(title)
        candidates = [base_rule]
        alt = DawnBlogCRUD.generate_slug(title)
        if alt and alt not in candidates:
            candidates.append(alt)

        final = []
        for cand in candidates[:4]:
            unique_slug, changed = await DawnBlogCRUD.ensure_unique_slug(cand, exclude_post_id=int(current_post_id or 0))
            final.append({
                'raw': cand,
                'slug': unique_slug,
                'adjusted': changed,
            })
        return {
            'candidates': final,
            'llm_error': '',
        }
