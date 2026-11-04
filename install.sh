#!/usr/bin/env bash
# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# DawnCMS 一键安装（Linux / macOS）：bash install.sh
set -e
cd "$(dirname "$0")"

PY=""
for cmd in python3.12 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PY="$cmd"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "[错误] 未找到 Python 3.10+（推荐 3.12）。"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  macOS:         brew install python@3.12"
    echo "  或访问:        https://www.python.org/downloads/"
    exit 1
fi

exec "$PY" install.py
