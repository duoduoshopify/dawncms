#!/usr/bin/env bash
# DawnCMS 一键启动（Linux / macOS）：bash start.sh
set -e
cd "$(dirname "$0")"

if [ ! -x venv/bin/python ]; then
    echo "[错误] 尚未安装，请先运行: bash install.sh"
    exit 1
fi

exec venv/bin/python dawn_main.py
