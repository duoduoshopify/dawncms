#!/usr/bin/env python3
# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================

# install.py
# DawnCMS 一键安装（跨平台，由 install.sh / install.bat 调用，也可直接 python install.py）

import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "venv"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def step(msg: str):
    print(f"\n==> {msg}", flush=True)


def main() -> int:
    os_name = "Windows" if sys.platform == "win32" else ("macOS" if sys.platform == "darwin" else "Linux")
    print(f"DawnCMS 一键安装 · {os_name} · Python {sys.version.split()[0]}")

    if sys.version_info < (3, 10):
        print("\n[错误] 需要 Python 3.10 或更高版本（推荐 3.12）。")
        print("  下载地址: https://www.python.org/downloads/")
        return 1
    if sys.version_info[:2] != (3, 12):
        print(f"[提示] 当前 Python {sys.version_info.major}.{sys.version_info.minor}，"
              "官方测试环境为 3.12，如遇到问题请改用 3.12。")

    step("创建虚拟环境 venv/")
    if venv_python().exists():
        print("  已存在，跳过创建")
    else:
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])

    step("安装依赖（requirements.txt 锁定版本）")
    py = str(venv_python())
    subprocess.check_call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])

    step("准备数据目录")
    (ROOT / "database").mkdir(exist_ok=True)
    (ROOT / "static" / "uploads" / "blog").mkdir(parents=True, exist_ok=True)

    step("生成配置文件 .env")
    env_file = ROOT / ".env"
    if env_file.exists():
        print("  .env 已存在，保留原配置不动")
    else:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        text = text.replace("BLOG_ADMIN_PASSWORD=change-me-now",
                            f"BLOG_ADMIN_PASSWORD={secrets.token_urlsafe(12)}")
        text = text.replace("SESSION_SECRET=please-change-me",
                            f"SESSION_SECRET={secrets.token_urlsafe(32)}")
        env_file.write_text(text, encoding="utf-8")
        print("  已从 .env.example 生成 .env，后台密码与会话密钥已随机生成")

    port = "5010"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("PORT="):
            port = line.split("=", 1)[1].strip() or port

    starter = "start.bat（双击）" if sys.platform == "win32" else "./start.sh"
    print(f"""
============================================================
安装完成！

启动方式: {starter}
前台地址: http://localhost:{port}/
后台地址: http://localhost:{port}/dadmin
后台密码: 见 .env 文件的 BLOG_ADMIN_PASSWORD（已随机生成）
============================================================""")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 安装失败（命令退出码 {e.returncode}），请把上方报错信息反馈给开发者。")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(1)
