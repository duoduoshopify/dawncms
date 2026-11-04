# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# scripts/seed_blog_series.py
# 生成《博客运营实战》20 篇系列：分类 + 标签 + SVG 封面 + 文章入库

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from blog.dawn_crud import DawnBlogCRUD
from blog.dawn_factory import dawn_get_blog_db
from scripts.blog_series.data1 import DAWN_POSTS as P1
from scripts.blog_series.data2 import DAWN_POSTS as P2
from scripts.blog_series.data3 import DAWN_POSTS as P3
from scripts.blog_series.data4 import DAWN_POSTS as P4

DAWN_ALL_POSTS = P1 + P2 + P3 + P4

DAWN_CATEGORIES = [
    ("起步篇", "getting-started", "博客冷启动：定位、选型、上线", 1),
    ("内容篇", "content", "选题、写作流程与质量标准", 2),
    ("增长篇", "growth", "SEO、关键词、推广与数据分析", 3),
    ("变现与运营篇", "monetization", "会员、邮件订阅、变现与维护", 4),
]

DAWN_GRADIENTS = [
    ("#4f46e5", "#7c3aed"), ("#0ea5e9", "#6366f1"), ("#f59e0b", "#ef4444"),
    ("#10b981", "#0ea5e9"), ("#8b5cf6", "#ec4899"), ("#f97316", "#eab308"),
]

DAWN_COVER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>
  </linearGradient></defs>
  <rect width="1200" height="675" fill="url(#g)"/>
  <circle cx="1050" cy="120" r="220" fill="#ffffff" opacity="0.08"/>
  <circle cx="140" cy="600" r="260" fill="#000000" opacity="0.10"/>
  <text x="70" y="120" font-size="34" fill="#ffffff" opacity="0.85" font-family="sans-serif" font-weight="bold">博客运营实战</text>
  <text x="70" y="330" font-size="150" fill="#ffffff" opacity="0.9" font-family="sans-serif" font-weight="900">{num:02d}</text>
  <text x="70" y="430" font-size="44" fill="#ffffff" font-family="sans-serif" font-weight="bold">{title}</text>
  <text x="70" y="590" font-size="24" fill="#ffffff" opacity="0.7" font-family="sans-serif">{category} · 共 20 篇</text>
</svg>"""


def dawn_fit_title(title: str) -> str:
    return title if len(title) <= 22 else title[:21] + "…"


async def dawn_main():
    cover_dir = Path("static/uploads/blog/covers")
    cover_dir.mkdir(parents=True, exist_ok=True)

    # 分类
    cat_ids = {}
    for name, slug, desc, order in DAWN_CATEGORIES:
        try:
            cat_ids[name] = await DawnBlogCRUD.create_category(
                {"name": name, "slug": slug, "description": desc, "sort_order": order})
        except Exception:
            pass
    print(f"分类: {len(DAWN_CATEGORIES)}")

    # 标签
    tag_names = sorted({t for p in DAWN_ALL_POSTS for t in p["tags"]})
    tag_ids = {}
    for name in tag_names:
        tag_ids[name] = await DawnBlogCRUD.create_tag(name)
    print(f"标签: {len(tag_ids)}: {tag_names}")

    db = await dawn_get_blog_db()
    created = 0
    for i, p in enumerate(DAWN_ALL_POSTS):
        existing = await (await db.execute(
            "SELECT id FROM posts WHERE slug = ?", (p["slug"],))).fetchone()
        if existing:
            continue

        # SVG 封面
        c1, c2 = DAWN_GRADIENTS[i % len(DAWN_GRADIENTS)]
        cover_name = f"series-{p['num']:02d}.svg"
        cover_path = cover_dir / cover_name
        cover_path.write_text(
            DAWN_COVER_SVG.format(c1=c1, c2=c2, num=p["num"],
                             title=dawn_fit_title(p["title"]), category=p["category"]),
            encoding="utf-8")

        post_id = await DawnBlogCRUD.create_post({
            "title": p["title"],
            "slug": p["slug"],
            "description": p["description"],
            "content": p["content"],
            "category": p["category"],
            "author": "站长",
            "read_time": p["read_time"],
            "keywords": p["keywords"],
            "cover_image": f"/uploads/blog/covers/{cover_name}",
            "visibility": "public",
            "is_published": 1,
        })

        # 错峰发布日期：每周一篇，倒序排列
        days_ago = (len(DAWN_ALL_POSTS) - p["num"]) * 7
        await db.execute(
            "UPDATE posts SET created_at = datetime('now', ?), updated_at = datetime('now', ?) WHERE id = ?",
            (f"-{days_ago} days", f"-{days_ago} days", post_id))

        # 标签关联
        for tname in p["tags"]:
            await db.execute(
                "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
                (post_id, tag_ids[tname]))
        await db.commit()
        created += 1

    await db.commit()
    await db.close()
    print(f"文章: 新建 {created} 篇，共 {len(DAWN_ALL_POSTS)} 篇")


if __name__ == "__main__":
    asyncio.run(dawn_main())
