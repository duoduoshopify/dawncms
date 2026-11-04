# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# routes/admin/__init__.py
# 后台聚合入口：布局壳 + 各功能模块

from . import dawn_auth, dawn_dashboard, dawn_posts, dawn_taxonomy, dawn_media, dawn_users, dawn_site
from .dawn_shell import DawnAdminLangMiddleware


def dawn_setup(app):
    app.add_middleware(DawnAdminLangMiddleware)
    dawn_auth.dawn_setup(app)
    dawn_dashboard.dawn_setup(app)
    dawn_posts.dawn_setup(app)
    dawn_taxonomy.dawn_setup(app)
    dawn_media.dawn_setup(app)
    dawn_users.dawn_setup(app)
    dawn_site.dawn_setup(app)
