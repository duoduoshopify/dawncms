# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================

# dawn_config.py
# DawnCMS 站点全局配置（均可用环境变量覆盖）

import os
import time
from urllib.parse import urlparse

DAWN_SITE_NAME = os.environ.get("SITE_NAME", "DawnCMS")
DAWN_SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "轻量、自持、长期主义的内容管理系统")
DAWN_SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "http://localhost:5010").rstrip("/")
DAWN_SITE_HOST = urlparse(DAWN_SITE_BASE_URL).netloc
DAWN_DEFAULT_AUTHOR = os.environ.get("BLOG_DEFAULT_AUTHOR", "站长")
DAWN_ADMIN_PASSWORD = os.environ.get("BLOG_ADMIN_PASSWORD", "change-me-now")
DAWN_PORT = int(os.environ.get("PORT", "5010"))

DAWN_SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
DAWN_SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
DAWN_SMTP_USER = os.environ.get("SMTP_USER", "")
DAWN_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
DAWN_SMTP_FROM = os.environ.get("SMTP_FROM", "") or DAWN_SMTP_USER
DAWN_EMAIL_ENABLED = bool(DAWN_SMTP_SERVER and DAWN_SMTP_USER and DAWN_SMTP_PASSWORD)

# 站点名称/标语：site_settings 表优先（后台可改），其次环境变量/默认值；30s 缓存
_DAWN_SITE_CACHE: dict = {}


def _dawn_site_setting(key: str, default: str) -> str:
    now = time.time()
    hit = _DAWN_SITE_CACHE.get(key)
    if hit and now - hit[1] < 30:
        return hit[0]
    value = default
    try:
        from dawn_themes import _dawn_get_setting
        value = _dawn_get_setting(key, "") or default
    except Exception:
        pass
    _DAWN_SITE_CACHE[key] = (value, now)
    return value


def dawn_site_name() -> str:
    return _dawn_site_setting("site_name", DAWN_SITE_NAME)


def dawn_site_tagline() -> str:
    return _dawn_site_setting("site_tagline", DAWN_SITE_TAGLINE)


def dawn_set_site_info(name: str = "", tagline: str = "") -> None:
    from dawn_themes import _dawn_set_setting
    if name is not None:
        _dawn_set_setting("site_name", name.strip())
    if tagline is not None:
        _dawn_set_setting("site_tagline", tagline.strip())
    _DAWN_SITE_CACHE.clear()
