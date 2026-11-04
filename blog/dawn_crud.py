# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# blog/crud.py
# 博客系统 CRUD 操作

import os
import re
import aiosqlite
from datetime import datetime
from .dawn_factory import dawn_get_blog_db

class DawnBlogCRUD:

    PINYIN_MAP = {
        '吸底': 'sticky', '加购': 'add-to-cart', '横幅': 'banner', '提升': 'boost', '转化率': 'conversion-rate',
        '教程': 'tutorial', '完整': 'complete', '指南': 'guide', '实战': 'playbook', '案例': 'case-study',
        '博客': 'blog', '文章': 'article', '优化': 'optimization', '转化': 'conversion', '独立站': 'dtc-store',
        '会员': 'member', '企业版': 'enterprise', '专业版': 'individual', '公开': 'public', '权限': 'visibility',
        'Google': 'google', 'Merchant': 'merchant', 'Center': 'center', '虚假陈述': 'misrepresentation',
        '结账': 'checkout', '商品页': 'product-page', '购物车': 'cart', '政策页': 'policy-page',
    }
    
    CN_EN_PHRASES = [
        ("搜索引擎优化", "search-engine-optimization"),
        ("关键词研究", "keyword-research"),
        ("完全指南", "complete-guide"),
        ("如何", "how-to"),
        ("入门", "basics"),
        ("基础", "fundamentals"),
        ("优化", "optimization"),
        ("策略", "strategy"),
        ("分析", "analysis"),
        ("内容", "content"),
        ("指南", "guide"),
        ("流量", "traffic"),
        ("转化", "conversion"),
        ("广告", "ads"),
        ("品牌", "brand"),
        ("竞争对手", "competitor"),
        ("投资回报率", "roi"),
        ("时代", "era"),
        ("趋势", "trends"),
        ("检测", "detection"),
        ("评测", "review"),
        ("实战", "playbook"),
        ("教程", "tutorial"),
        ("方法", "method"),
    ]

    @staticmethod
    def extract_media_urls(content: str, cover_image: str = '') -> list:
        urls = set()
        for match in re.findall(r"!\[[^\]]*\]\(([^\)]+)\)", content or ''):
            if match:
                urls.add(match.strip())
        if cover_image:
            urls.add(str(cover_image).strip())
        return [u for u in urls if u]

    @staticmethod
    def generate_slug(title: str) -> str:
        """从标题生成URL友好的slug"""
        text = (title or "").lower().strip()
        for cn, en in DawnBlogCRUD.CN_EN_PHRASES:
            text = text.replace(cn, f" {en} ")

        text = re.sub(r"[：:，,。！？!？（）()【】\[\]{}'\"·/\\]+", " ", text)
        text = text.replace("&", " and ").replace("+", " plus ")
        text = re.sub(r"[^a-z0-9\s\-]", " ", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text)
        slug = re.sub(r"^-+|-+$", "", text)

        if not slug:
            slug = f"post-{datetime.now().strftime('%Y%m%d')}"

        return slug[:96]

    @staticmethod
    def generate_slug_from_translation(title: str) -> str:
        text = title or ''
        for src, target in DawnBlogCRUD.PINYIN_MAP.items():
            text = text.replace(src, f' {target} ')
        return DawnBlogCRUD.generate_slug(text)

    @staticmethod
    def generate_slug_from_pinyin(title: str) -> str:
        text = title or ''
        out = text
        for src, target in DawnBlogCRUD.PINYIN_MAP.items():
            out = out.replace(src, f' {target} ')
        return DawnBlogCRUD.generate_slug(out)

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return DawnBlogCRUD.generate_slug(slug or '')

    @staticmethod
    async def ensure_unique_slug(slug: str, exclude_post_id: int = 0) -> tuple[str, bool]:
        db = await dawn_get_blog_db()
        base_slug = DawnBlogCRUD.normalize_slug(slug)
        candidate = base_slug
        counter = 1
        changed = False
        while True:
            if exclude_post_id > 0:
                row = await (await db.execute(
                    "SELECT id FROM posts WHERE slug = ? AND id != ?",
                    (candidate, exclude_post_id)
                )).fetchone()
            else:
                row = await (await db.execute(
                    "SELECT id FROM posts WHERE slug = ?",
                    (candidate,)
                )).fetchone()
            if not row:
                break
            changed = True
            candidate = f"{base_slug}-{counter}"
            counter += 1
        await db.close()
        return candidate, changed

    @staticmethod
    async def upsert_slug_redirect(post_id: int, old_slug: str, new_slug: str) -> None:
        if not old_slug or not new_slug or old_slug == new_slug:
            return
        db = await dawn_get_blog_db()
        await db.execute(
            "UPDATE post_slug_redirects SET new_slug = ?, is_active = 1 WHERE post_id = ?",
            (new_slug, post_id)
        )
        await db.execute(
            """
            INSERT INTO post_slug_redirects (post_id, old_slug, new_slug, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(old_slug) DO UPDATE SET
                post_id = excluded.post_id,
                new_slug = excluded.new_slug,
                is_active = 1
            """,
            (post_id, old_slug, new_slug)
        )
        await db.commit()
        await db.close()

    @staticmethod
    async def get_redirect_by_old_slug(old_slug: str) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM post_slug_redirects WHERE old_slug = ? AND is_active = 1",
            (old_slug,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None
    
    @staticmethod
    async def create_post(data: dict) -> int:
        """创建文章"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        slug = data.get('slug') or DawnBlogCRUD.generate_slug(data.get('title', ''))

        # 确保slug唯一
        base_slug = slug
        counter = 1
        while True:
            existing = await (await db.execute(
                "SELECT id FROM posts WHERE slug = ?", (slug,)
            )).fetchone()
            if not existing:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        cursor = await db.execute("""
            INSERT INTO posts (slug, title, description, content, category, author,
                             read_time, keywords, cover_image, template, visibility, is_published, scheduled_at, series_id, series_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            slug,
            data.get('title', ''),
            data.get('description', ''),
            data.get('content', ''),
            data.get('category', '未分类'),
            data.get('author', '搜投工具'),
            data.get('read_time', '5分钟'),
            data.get('keywords', ''),
            data.get('cover_image', ''),
            data.get('template', 'default'),
            data.get('visibility', 'public'),
            data.get('is_published', 0),
            data.get('scheduled_at', ''),
            data.get('series_id', 0),
            data.get('series_order', 0),
            now, now
        ))
        
        await db.commit()
        post_id = cursor.lastrowid
        await db.close()
        return post_id
    
    @staticmethod
    async def get_post_by_id(post_id: int) -> dict:
        """根据ID获取文章"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        row = await (await db.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)
        )).fetchone()
        
        await db.close()
        return dict(row) if row else None
    
    @staticmethod
    async def get_post_by_slug_admin(slug: str) -> dict:
        """根据slug获取已发布文章（管理员可见admin_only）"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row

        row = await (await db.execute(
            "SELECT * FROM posts WHERE slug = ? AND is_published = 1", (slug,)
        )).fetchone()

        await db.close()
        return dict(row) if row else None
    
    @staticmethod
    async def list_posts(published_only=True, limit=500, offset=0, category=None, include_admin=False) -> list:
        """获取文章列表"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        if published_only:
            where = "is_published = 1" if include_admin else "is_published = 1 AND COALESCE(visibility, 'public') IN ('public', 'member')"
        else:
            where = "1=1"
        params = []
        
        if category:
            where += " AND category = ?"
            params.append(category)
        
        sql = f"SELECT * FROM posts WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = await (await db.execute(sql, tuple(params))).fetchall()
        
        await db.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    async def update_post(post_id: int, data: dict) -> bool:
        """更新文章"""
        db = await dawn_get_blog_db()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 如果传了新的slug，检查唯一性
        new_slug = data.get('slug')
        if new_slug:
            existing = await (await db.execute(
                "SELECT id FROM posts WHERE slug = ? AND id != ?", (new_slug, post_id)
            )).fetchone()
            if existing:
                await db.close()
                return False
        
        await db.execute("""
            UPDATE posts SET 
                slug = COALESCE(?, slug),
                title = COALESCE(?, title),
                description = COALESCE(?, description),
                content = COALESCE(?, content),
                category = COALESCE(?, category),
                author = COALESCE(?, author),
                read_time = COALESCE(?, read_time),
                keywords = COALESCE(?, keywords),
                cover_image = COALESCE(?, cover_image),
                template = COALESCE(?, template),
                visibility = COALESCE(?, visibility),
                is_published = COALESCE(?, is_published),
                scheduled_at = COALESCE(?, scheduled_at),
                series_id = COALESCE(?, series_id),
                series_order = COALESCE(?, series_order),
                updated_at = ?
            WHERE id = ?
        """, (
            data.get('slug'),
            data.get('title'),
            data.get('description'),
            data.get('content'),
            data.get('category'),
            data.get('author'),
            data.get('read_time'),
            data.get('keywords'),
            data.get('cover_image'),
            data.get('template'),
            data.get('visibility'),
            data.get('is_published'),
            data.get('scheduled_at'),
            data.get('series_id'),
            data.get('series_order'),
            now, post_id
        ))
        
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def delete_post(post_id: int) -> bool:
        """删除文章"""
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        await db.commit()
        await db.close()
        return True
    
    @staticmethod
    async def increment_view_count(post_id: int):
        """增加浏览量"""
        db = await dawn_get_blog_db()
        await db.execute(
            "UPDATE posts SET view_count = view_count + 1 WHERE id = ?", (post_id,)
        )
        await db.commit()
        await db.close()
    
    @staticmethod
    async def get_categories() -> list:
        """获取分类列表"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        rows = await (await db.execute(
            "SELECT * FROM categories ORDER BY sort_order"
        )).fetchall()
        
        await db.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    async def get_posts_by_category(category_slug: str, limit=500, include_admin=False) -> list:
        """根据分类slug获取文章"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        cat_row = await (await db.execute(
            "SELECT name FROM categories WHERE slug = ?",
            (category_slug,)
        )).fetchone()
        
        if not cat_row:
            await db.close()
            return []
        
        category_name = cat_row['name']
        
        sql = (
            "SELECT * FROM posts WHERE category = ? AND is_published = 1 ORDER BY created_at DESC LIMIT ?"
            if include_admin else
            "SELECT * FROM posts WHERE category = ? AND is_published = 1 AND COALESCE(visibility, 'public') = 'public' ORDER BY created_at DESC LIMIT ?"
        )
        rows = await (await db.execute(sql, (category_name, limit))).fetchall()
        
        await db.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    async def get_all_posts_for_admin() -> list:
        """获取所有文章（包含未发布的），用于管理员"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        rows = await (await db.execute(
            "SELECT * FROM posts ORDER BY created_at DESC"
        )).fetchall()
        
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def get_admin_posts_filtered(q: str = "", status: str = "", category: str = "") -> list:
        """管理员文章列表：关键词 / 状态 / 分类 过滤"""
        where, args = [], []
        if q:
            where.append("(title LIKE ? OR slug LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if status == "published":
            where.append("is_published = 1 AND (scheduled_at = '' OR scheduled_at <= ?)")
            args.append(now_str)
        elif status == "draft":
            where.append("is_published = 0")
        elif status == "scheduled":
            where.append("is_published = 1 AND scheduled_at != '' AND scheduled_at > ?")
            args.append(now_str)
        if category:
            where.append("category = ?")
            args.append(category)
        sql = "SELECT * FROM posts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC"

        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(sql, args)).fetchall()
        await db.close()
        return [dict(r) for r in rows]
    
    @staticmethod
    async def search_posts(keyword: str, limit=20) -> list:
        """搜索文章"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        
        rows = await (await db.execute(
            """SELECT * FROM posts 
               WHERE is_published = 1 AND COALESCE(visibility, 'public') = 'public' AND 
               (title LIKE ? OR description LIKE ? OR content LIKE ?)
               ORDER BY created_at DESC LIMIT ?""",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)
        )).fetchall()
        
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def create_media_asset(data: dict) -> int:
        db = await dawn_get_blog_db()
        cursor = await db.execute(
            """
            INSERT INTO media_assets (
                file_name, original_name, file_url, file_path, thumb_url, thumb_path, mime_type,
                size_bytes, width, height, alt_text, caption, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get('file_name', ''),
                data.get('original_name', ''),
                data.get('file_url', ''),
                data.get('file_path', ''),
                data.get('thumb_url', ''),
                data.get('thumb_path', ''),
                data.get('mime_type', ''),
                int(data.get('size_bytes', 0) or 0),
                int(data.get('width', 0) or 0),
                int(data.get('height', 0) or 0),
                data.get('alt_text', ''),
                data.get('caption', ''),
                data.get('created_by', ''),
            )
        )
        await db.commit()
        media_id = cursor.lastrowid
        await db.close()
        return media_id

    @staticmethod
    async def list_media_assets(limit: int = 80) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM media_assets ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),)
        )).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def get_media_asset(media_id: int) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM media_assets WHERE id = ?",
            (media_id,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None

    @staticmethod
    async def get_media_asset_by_url(file_url: str) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM media_assets WHERE file_url = ?",
            (file_url,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None

    @staticmethod
    async def update_media_asset(media_id: int, data: dict) -> bool:
        db = await dawn_get_blog_db()
        await db.execute(
            """
            UPDATE media_assets SET
                file_name = COALESCE(?, file_name),
                original_name = COALESCE(?, original_name),
                file_url = COALESCE(?, file_url),
                file_path = COALESCE(?, file_path),
                thumb_url = COALESCE(?, thumb_url),
                thumb_path = COALESCE(?, thumb_path),
                mime_type = COALESCE(?, mime_type),
                size_bytes = COALESCE(?, size_bytes),
                width = COALESCE(?, width),
                height = COALESCE(?, height),
                alt_text = COALESCE(?, alt_text),
                caption = COALESCE(?, caption)
            WHERE id = ?
            """,
            (
                data.get('file_name'),
                data.get('original_name'),
                data.get('file_url'),
                data.get('file_path'),
                data.get('thumb_url'),
                data.get('thumb_path'),
                data.get('mime_type'),
                data.get('size_bytes'),
                data.get('width'),
                data.get('height'),
                data.get('alt_text'),
                data.get('caption'),
                media_id,
            )
        )
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def delete_media_asset(media_id: int) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM media_assets WHERE id = ?",
            (media_id,)
        )).fetchone()
        if not row:
            await db.close()
            return None
        await db.execute("DELETE FROM media_assets WHERE id = ?", (media_id,))
        await db.commit()
        await db.close()
        return dict(row)

    @staticmethod
    async def replace_post_media_usages(post_id: int, usages: list[tuple[int, str]]) -> None:
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM media_usages WHERE post_id = ?", (post_id,))
        for media_id, usage_type in usages:
            await db.execute(
                "INSERT OR IGNORE INTO media_usages (media_id, post_id, usage_type) VALUES (?, ?, ?)",
                (media_id, post_id, usage_type)
            )
        await db.commit()
        await db.close()

    @staticmethod
    async def list_media_usage_counts() -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT media_id, COUNT(*) AS usage_count FROM media_usages GROUP BY media_id"
        )).fetchall()
        await db.close()
        return {int(r['media_id']): int(r['usage_count']) for r in rows}

    @staticmethod
    async def bulk_delete_media_assets(media_ids: list[int]) -> list:
        deleted = []
        for media_id in media_ids:
            row = await DawnBlogCRUD.delete_media_asset(int(media_id))
            if row:
                deleted.append(row)
        return deleted

    @staticmethod
    async def bulk_fill_media_alt(media_ids: list[int]) -> int:
        db = await dawn_get_blog_db()
        affected = 0
        for media_id in media_ids:
            row = await (await db.execute(
                "SELECT id, alt_text, original_name, file_name FROM media_assets WHERE id = ?",
                (int(media_id),)
            )).fetchone()
            if not row:
                continue
            current_alt = (row['alt_text'] or '').strip()
            if current_alt:
                continue
            fallback = os.path.splitext((row['original_name'] or row['file_name'] or 'image'))[0]
            await db.execute("UPDATE media_assets SET alt_text = ? WHERE id = ?", (fallback, int(media_id)))
            affected += 1
        await db.commit()
        await db.close()
        return affected

    @staticmethod
    async def replace_media_url_references(old_url: str, new_url: str) -> int:
        if not old_url or not new_url or old_url == new_url:
            return 0
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, content, cover_image FROM posts WHERE content LIKE ? OR cover_image = ?",
            (f"%{old_url}%", old_url)
        )).fetchall()
        updated = 0
        for row in rows:
            content = (row['content'] or '').replace(old_url, new_url)
            cover_image = row['cover_image'] or ''
            if cover_image == old_url:
                cover_image = new_url
            await db.execute(
                "UPDATE posts SET content = ?, cover_image = ?, updated_at = ? WHERE id = ?",
                (content, cover_image, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row['id'])
            )
            updated += 1
        if updated:
            await db.commit()
        await db.close()
        return updated

    @staticmethod
    async def create_post_revision(post_id: int, data: dict, edited_by: str = '') -> int:
        db = await dawn_get_blog_db()
        cursor = await db.execute(
            """
            INSERT INTO blog_post_revisions (
                post_id, title, description, keywords, content, edited_by
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                data.get('title', ''),
                data.get('description', ''),
                data.get('keywords', ''),
                data.get('content', ''),
                edited_by,
            )
        )
        await db.commit()
        revision_id = cursor.lastrowid
        await db.close()
        return revision_id

    @staticmethod
    async def list_post_revisions(post_id: int, limit: int = 10) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM blog_post_revisions WHERE post_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (post_id, int(limit))
        )).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def get_post_revision(revision_id: int) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM blog_post_revisions WHERE id = ?",
            (revision_id,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None
    
    @staticmethod
    async def create_category(data: dict) -> int:
        """创建分类"""
        db = await dawn_get_blog_db()
        try:
            cursor = await db.execute("""
                INSERT INTO categories (name, slug, description, sort_order, is_series)
                VALUES (?, ?, ?, ?, ?)
            """, (
                data.get('name', ''),
                data.get('slug', ''),
                data.get('description', ''),
                data.get('sort_order', 0),
                data.get('is_series', 0)
            ))
            await db.commit()
            return cursor.lastrowid
        finally:
            await db.close()

    @staticmethod
    async def normalize_non_ascii_slugs() -> int:
        """将历史中文/非ASCII slug标准化为英文slug"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row

        rows = await (await db.execute("SELECT id, title, slug FROM posts")).fetchall()
        updated = 0

        for row in rows:
            post_id = row["id"]
            title = row["title"] or ""
            current_slug = row["slug"] or ""

            if current_slug and re.fullmatch(r"[a-z0-9\-]+", current_slug):
                continue

            new_slug = DawnBlogCRUD.generate_slug(title)
            base_slug = new_slug
            counter = 1
            while True:
                existing = await (await db.execute(
                    "SELECT id FROM posts WHERE slug = ? AND id != ?",
                    (new_slug, post_id)
                )).fetchone()
                if not existing:
                    break
                new_slug = f"{base_slug}-{counter}"
                counter += 1

            await db.execute("UPDATE posts SET slug = ? WHERE id = ?", (new_slug, post_id))
            updated += 1

        if updated:
            await db.commit()
        await db.close()
        return updated
    
    @staticmethod
    async def update_category(cat_id: int, data: dict) -> bool:
        """更新分类"""
        db = await dawn_get_blog_db()
        await db.execute("""
            UPDATE categories SET
                name = COALESCE(?, name),
                slug = COALESCE(?, slug),
                description = COALESCE(?, description),
                sort_order = COALESCE(?, sort_order),
                is_series = COALESCE(?, is_series)
            WHERE id = ?
        """, (
            data.get('name'),
            data.get('slug'),
            data.get('description'),
            data.get('sort_order'),
            data.get('is_series'),
            cat_id
        ))
        await db.commit()
        await db.close()
        return True
    
    @staticmethod
    async def delete_category(cat_id: int) -> bool:
        """删除分类"""
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def get_series() -> list:
        """获取全部连载系列"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM series ORDER BY sort_order, id"
        )).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def get_series_by_id(series_id: int) -> dict | None:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM series WHERE id = ?", (series_id,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None

    @staticmethod
    async def get_series_by_slug(slug: str) -> dict | None:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM series WHERE slug = ?", (slug,)
        )).fetchone()
        await db.close()
        return dict(row) if row else None

    @staticmethod
    async def create_series(data: dict) -> int:
        db = await dawn_get_blog_db()
        try:
            cursor = await db.execute("""
                INSERT INTO series (name, slug, description, sort_order)
                VALUES (?, ?, ?, ?)
            """, (
                data.get('name', ''),
                data.get('slug', ''),
                data.get('description', ''),
                data.get('sort_order', 0)
            ))
            await db.commit()
            return cursor.lastrowid
        finally:
            await db.close()

    @staticmethod
    async def update_series(series_id: int, data: dict) -> bool:
        db = await dawn_get_blog_db()
        await db.execute("""
            UPDATE series SET
                name = COALESCE(?, name),
                slug = COALESCE(?, slug),
                description = COALESCE(?, description),
                sort_order = COALESCE(?, sort_order)
            WHERE id = ?
        """, (
            data.get('name'),
            data.get('slug'),
            data.get('description'),
            data.get('sort_order'),
            series_id
        ))
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def delete_series(series_id: int) -> bool:
        """删除系列（文章保留，仅解除关联）"""
        db = await dawn_get_blog_db()
        await db.execute("UPDATE posts SET series_id = 0, series_order = 0 WHERE series_id = ?", (series_id,))
        await db.execute("DELETE FROM series WHERE id = ?", (series_id,))
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def get_series_posts(series_id: int) -> list:
        """系列内文章，按 series_order + 发布时间正序"""
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("""
            SELECT * FROM posts WHERE series_id = ?
            ORDER BY CASE WHEN series_order > 0 THEN 0 ELSE 1 END,
                     series_order, created_at
        """, (series_id,))).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    # ---- Tags ----

    @staticmethod
    async def list_tags() -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM tags ORDER BY name")).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def list_tags_with_counts() -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT t.*, COUNT(pt.post_id) AS post_count
               FROM tags t LEFT JOIN post_tags pt ON pt.tag_id = t.id
               GROUP BY t.id ORDER BY post_count DESC, t.name"""
        )).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def create_tag(name: str, slug: str = "") -> int:
        name = (name or "").strip()
        slug = (slug or "").strip() or DawnBlogCRUD.normalize_slug(name)
        if not slug:
            slug = f"tag-{int(datetime.now().timestamp())}"
        db = await dawn_get_blog_db()
        try:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO tags (name, slug) VALUES (?, ?)", (name, slug))
            await db.commit()
            tag_id = cursor.lastrowid
            if not tag_id:
                row = await (await db.execute("SELECT id FROM tags WHERE name = ? OR slug = ?", (name, slug))).fetchone()
                tag_id = row[0] if row else 0
            return tag_id
        finally:
            await db.close()

    @staticmethod
    async def delete_tag(tag_id: int) -> bool:
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM tags WHERE id = ?", (int(tag_id),))
        await db.commit()
        await db.close()
        return True

    @staticmethod
    async def get_tag_by_slug(slug: str) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM tags WHERE slug = ?", (slug,))).fetchone()
        await db.close()
        return dict(row) if row else None

    @staticmethod
    async def get_post_tag_ids(post_id: int) -> list:
        db = await dawn_get_blog_db()
        rows = await (await db.execute(
            "SELECT tag_id FROM post_tags WHERE post_id = ?", (int(post_id),))).fetchall()
        await db.close()
        return [r[0] for r in rows]

    @staticmethod
    async def get_post_tags(post_id: int) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT t.* FROM tags t JOIN post_tags pt ON pt.tag_id = t.id
               WHERE pt.post_id = ? ORDER BY t.name""", (int(post_id),))).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def get_tags_for_posts(post_ids: list) -> dict:
        if not post_ids:
            return {}
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(post_ids))
        rows = await (await db.execute(
            f"""SELECT pt.post_id, t.id, t.name, t.slug FROM post_tags pt
                JOIN tags t ON t.id = pt.tag_id WHERE pt.post_id IN ({placeholders})""",
            tuple(int(p) for p in post_ids))).fetchall()
        await db.close()
        out = {}
        for r in rows:
            out.setdefault(r["post_id"], []).append({"id": r["id"], "name": r["name"], "slug": r["slug"]})
        return out

    @staticmethod
    async def set_post_tags(post_id: int, tag_ids: list) -> None:
        db = await dawn_get_blog_db()
        await db.execute("DELETE FROM post_tags WHERE post_id = ?", (int(post_id),))
        for tid in tag_ids:
            await db.execute(
                "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
                (int(post_id), int(tid)))
        await db.commit()
        await db.close()

    @staticmethod
    async def get_posts_by_tag_slug(tag_slug: str, limit=200, include_admin=False) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        vis = "" if include_admin else "AND COALESCE(p.visibility, 'public') IN ('public', 'member')"
        rows = await (await db.execute(
            f"""SELECT p.* FROM posts p
                JOIN post_tags pt ON pt.post_id = p.id
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.slug = ? AND p.is_published = 1 {vis}
                ORDER BY p.created_at DESC LIMIT ?""",
            (tag_slug, limit))).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    # ---- 导航链接（header / footer 可编辑导航）----

    @staticmethod
    async def list_nav_links(location: str = "", active_only: bool = False) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        where, params = [], []
        if location:
            where.append("location = ?")
            params.append(location)
        if active_only:
            where.append("is_active = 1")
        sql = "SELECT * FROM nav_links"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY location, sort_order, id"
        rows = await (await db.execute(sql, tuple(params))).fetchall()
        await db.close()
        return [dict(r) for r in rows]

    @staticmethod
    async def create_nav_link(location: str, label: str, url: str, sort_order: int = 0) -> int:
        db = await dawn_get_blog_db()
        try:
            cur = await db.execute(
                "INSERT INTO nav_links (location, label, url, sort_order) VALUES (?, ?, ?, ?)",
                (location if location in ("header", "footer") else "header",
                 (label or "").strip()[:50], (url or "").strip()[:300], int(sort_order or 0)))
            await db.commit()
            return cur.lastrowid
        finally:
            await db.close()

    @staticmethod
    async def update_nav_link(link_id: int, label: str, url: str, sort_order: int, is_active: int) -> bool:
        db = await dawn_get_blog_db()
        try:
            await db.execute(
                "UPDATE nav_links SET label = ?, url = ?, sort_order = ?, is_active = ? WHERE id = ?",
                ((label or "").strip()[:50], (url or "").strip()[:300],
                 int(sort_order or 0), 1 if is_active else 0, int(link_id)))
            await db.commit()
            return True
        finally:
            await db.close()

    @staticmethod
    async def delete_nav_link(link_id: int) -> bool:
        db = await dawn_get_blog_db()
        try:
            await db.execute("DELETE FROM nav_links WHERE id = ?", (int(link_id),))
            await db.commit()
            return True
        finally:
            await db.close()

    # ---- Member tokens（邮箱验证 / 密码重置）----
    @staticmethod
    async def create_member_token(member_id: int, kind: str, ttl_minutes: int = 60) -> str:
        import secrets
        token = secrets.token_urlsafe(32)
        expires = datetime.fromtimestamp(datetime.now().timestamp() + ttl_minutes * 60).strftime("%Y-%m-%d %H:%M:%S")
        db = await dawn_get_blog_db()
        await db.execute(
            "INSERT INTO member_tokens (member_id, token, kind, expires_at) VALUES (?, ?, ?, ?)",
            (int(member_id), token, kind, expires))
        await db.commit()
        await db.close()
        return token

    @staticmethod
    async def consume_member_token(token: str, kind: str) -> int:
        """返回 member_id；无效/过期/已用返回 0"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM member_tokens WHERE token = ? AND kind = ? AND used_at = ''",
            (token, kind))).fetchone()
        if not row or row["expires_at"] < now:
            await db.close()
            return 0
        await db.execute(
            "UPDATE member_tokens SET used_at = ? WHERE id = ?", (now, row["id"]))
        await db.commit()
        member_id = int(row["member_id"])
        await db.close()
        return member_id

    @staticmethod
    async def mark_email_verified(member_id: int) -> None:
        db = await dawn_get_blog_db()
        await db.execute("UPDATE members SET email_verified = 1 WHERE id = ?", (int(member_id),))
        await db.commit()
        await db.close()

    @staticmethod
    async def get_member_by_email(email: str) -> dict:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM members WHERE email = ?", ((email or '').strip().lower(),))).fetchone()
        await db.close()
        return dict(row) if row else None

    # ---- Newsletter 订阅 ----

    @staticmethod
    async def subscribe_newsletter(email: str) -> tuple[bool, str]:
        import secrets
        email = (email or "").strip().lower()
        if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email):
            return False, "邮箱格式不正确"
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM newsletter_subscribers WHERE email = ?", (email,))).fetchone()
        if row:
            if row["is_active"]:
                await db.close()
                return True, "你已订阅过，无需重复操作"
            await db.execute(
                "UPDATE newsletter_subscribers SET is_active = 1 WHERE id = ?", (row["id"],))
            await db.commit()
            await db.close()
            return True, "已重新订阅"
        await db.execute(
            "INSERT INTO newsletter_subscribers (email, token) VALUES (?, ?)",
            (email, secrets.token_urlsafe(24)))
        await db.commit()
        await db.close()
        return True, "订阅成功"

    @staticmethod
    async def unsubscribe_newsletter(token: str) -> bool:
        db = await dawn_get_blog_db()
        cur = await db.execute(
            "UPDATE newsletter_subscribers SET is_active = 0 WHERE token = ?", (token,))
        await db.commit()
        changed = cur.rowcount > 0
        await db.close()
        return changed

    @staticmethod
    async def list_newsletter_subscribers(active_only: bool = False) -> list:
        db = await dawn_get_blog_db()
        db.row_factory = aiosqlite.Row
        where = "WHERE is_active = 1" if active_only else ""
        rows = await (await db.execute(
            f"SELECT * FROM newsletter_subscribers {where} ORDER BY id DESC")).fetchall()
        await db.close()
        return [dict(r) for r in rows]
