# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# blog/factory.py
# 博客系统数据库连接

import aiosqlite
import os
from pathlib import Path

DAWN_BASE_DIR = Path(__file__).parent.parent
DAWN_BLOG_DB_PATH = os.path.join(DAWN_BASE_DIR, "database", "blog.db")

async def dawn_get_blog_db():
    db = await aiosqlite.connect(DAWN_BLOG_DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    return db

async def dawn_init_blog_db():
    db = await dawn_get_blog_db()
    db.row_factory = aiosqlite.Row

    await db.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT DEFAULT ''
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            content TEXT NOT NULL,
            category TEXT DEFAULT '未分类',
            author TEXT DEFAULT '站长',
            read_time TEXT DEFAULT '5分钟',
            keywords TEXT,
            cover_image TEXT,
            template TEXT DEFAULT 'default',
            visibility TEXT DEFAULT 'public',
            is_published INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    for sql in [
        "ALTER TABLE posts ADD COLUMN visibility TEXT DEFAULT 'public'",
        "ALTER TABLE posts ADD COLUMN template TEXT DEFAULT 'default'",
        "ALTER TABLE posts ADD COLUMN scheduled_at TEXT DEFAULT ''",
        "ALTER TABLE members ADD COLUMN email_verified INTEGER DEFAULT 0",
        "ALTER TABLE categories ADD COLUMN is_series INTEGER DEFAULT 0",
        "ALTER TABLE posts ADD COLUMN series_id INTEGER DEFAULT 0",
        "ALTER TABLE posts ADD COLUMN series_order INTEGER DEFAULT 0",
    ]:
        try:
            await db.execute(sql)
        except Exception:
            pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS member_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            token TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS media_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_url TEXT NOT NULL,
            file_path TEXT NOT NULL,
            thumb_url TEXT DEFAULT '',
            thumb_path TEXT DEFAULT '',
            mime_type TEXT DEFAULT '',
            size_bytes INTEGER DEFAULT 0,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            alt_text TEXT DEFAULT '',
            caption TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS blog_post_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            content TEXT DEFAULT '',
            edited_by TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS media_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            usage_type TEXT DEFAULT 'content_image',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(media_id, post_id, usage_type),
            FOREIGN KEY (media_id) REFERENCES media_assets(id) ON DELETE CASCADE,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS post_slug_redirects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            old_slug TEXT UNIQUE NOT NULL,
            new_slug TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    """)

    for sql in [
        "ALTER TABLE media_assets ADD COLUMN thumb_url TEXT DEFAULT ''",
        "ALTER TABLE media_assets ADD COLUMN thumb_path TEXT DEFAULT ''",
    ]:
        try:
            await db.execute(sql)
        except Exception:
            pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS post_tags (
            post_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (post_id, tag_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS nav_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL DEFAULT 'header',
            label TEXT NOT NULL,
            url TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)


    nav_count = (await (await db.execute("SELECT COUNT(*) FROM nav_links")).fetchone())[0]
    if nav_count == 0:
        default_nav = [
            ("header", "首页", "/", 1),
            ("header", "关于", "/about", 2),
            ("footer", "关于", "/about", 1),
            ("footer", "RSS 订阅", "/feed.xml", 2),
        ]
        for location, label, url, order in default_nav:
            await db.execute(
                "INSERT INTO nav_links (location, label, url, sort_order) VALUES (?, ?, ?, ?)",
                (location, label, url, order)
            )

    default_categories = [
        ("未分类", "uncategorized", "默认分类", 99),
    ]

    for name, slug, desc, order in default_categories:
        await db.execute(
            "INSERT OR IGNORE INTO categories (name, slug, description, sort_order) VALUES (?, ?, ?, ?)",
            (name, slug, desc, order)
        )

    await db.commit()
    await db.close()
    print("✅ 博客数据库初始化完成")
