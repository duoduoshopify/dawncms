# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# services/email_service.py
# 邮件发送服务（SMTP；未配置时降级为日志输出）

import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from dawn_config import (
    DAWN_SMTP_SERVER, DAWN_SMTP_PORT, DAWN_SMTP_USER, DAWN_SMTP_PASSWORD, DAWN_SMTP_FROM,
    DAWN_EMAIL_ENABLED, dawn_site_name, DAWN_SITE_BASE_URL,
)


class DawnEmailService:

    @staticmethod
    def _send_sync(to: str, subject: str, html: str) -> tuple[bool, str]:
        if not DAWN_EMAIL_ENABLED:
            print(f"[email] SMTP 未配置，跳过发送 -> {to}: {subject}")
            return False, "SMTP 未配置"
        try:
            msg = MIMEText(html, "html", "utf-8")
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = formataddr((str(Header(dawn_site_name(), "utf-8")), DAWN_SMTP_FROM))
            msg["To"] = to
            if DAWN_SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(DAWN_SMTP_SERVER, DAWN_SMTP_PORT, timeout=15)
            else:
                server = smtplib.SMTP(DAWN_SMTP_SERVER, DAWN_SMTP_PORT, timeout=15)
                server.starttls()
            server.login(DAWN_SMTP_USER, DAWN_SMTP_PASSWORD)
            server.sendmail(DAWN_SMTP_FROM, [to], msg.as_string())
            server.quit()
            return True, "ok"
        except Exception as e:
            print(f"[email] 发送失败 -> {to}: {e}")
            return False, str(e)[:120]

    @staticmethod
    async def send(to: str, subject: str, html: str) -> tuple[bool, str]:
        return await asyncio.to_thread(DawnEmailService._send_sync, to, subject, html)

    @staticmethod
    def _wrap(body_html: str) -> str:
        return f"""
<div style="max-width:560px;margin:0 auto;padding:32px 24px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#0f172a;color:#e2e8f0;border-radius:12px">
  {body_html}
  <hr style="border:none;border-top:1px solid #334155;margin:28px 0 16px">
  <p style="color:#64748b;font-size:12px">此邮件由 <a href="{DAWN_SITE_BASE_URL}" style="color:#818cf8">{dawn_site_name()}</a> 发送</p>
</div>"""

    @staticmethod
    async def send_verify_email(to: str, token: str) -> tuple[bool, str]:
        link = f"{DAWN_SITE_BASE_URL}/verify-email?token={token}"
        return await DawnEmailService.send(
            to, f"【{dawn_site_name()}】验证你的邮箱",
            DawnEmailService._wrap(f"""
  <h2 style="color:#fff">验证邮箱</h2>
  <p>点击下方按钮完成邮箱验证（24 小时内有效）：</p>
  <p><a href="{link}" style="display:inline-block;padding:12px 28px;border-radius:10px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;text-decoration:none;font-weight:bold">验证邮箱</a></p>
  <p style="color:#94a3b8;font-size:13px">如果按钮无法点击，请复制链接打开：<br>{link}</p>"""))

    @staticmethod
    async def send_reset_email(to: str, token: str) -> tuple[bool, str]:
        link = f"{DAWN_SITE_BASE_URL}/reset-password?token={token}"
        return await DawnEmailService.send(
            to, f"【{dawn_site_name()}】重置密码",
            DawnEmailService._wrap(f"""
  <h2 style="color:#fff">重置密码</h2>
  <p>你申请了重置密码，点击下方按钮设置新密码（1 小时内有效）：</p>
  <p><a href="{link}" style="display:inline-block;padding:12px 28px;border-radius:10px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;text-decoration:none;font-weight:bold">重置密码</a></p>
  <p style="color:#94a3b8;font-size:13px">如果按钮无法点击，请复制链接打开：<br>{link}</p>
  <p style="color:#94a3b8;font-size:13px">如果这不是你的操作，请忽略本邮件。</p>"""))

    @staticmethod
    async def send_newsletter(to: str, unsubscribe_token: str, post: dict, dawn_post_url: str) -> tuple[bool, str]:
        title = post.get("title", "")
        desc = post.get("description", "")
        unsub = f"{DAWN_SITE_BASE_URL}/unsubscribe?token={unsubscribe_token}"
        return await DawnEmailService.send(
            to, f"【{dawn_site_name()}】新文章：{title}",
            DawnEmailService._wrap(f"""
  <p style="color:#818cf8;font-size:12px;letter-spacing:2px">新文章发布</p>
  <h2 style="color:#fff">{title}</h2>
  <p style="color:#94a3b8">{desc[:200]}</p>
  <p><a href="{dawn_post_url}" style="display:inline-block;padding:12px 28px;border-radius:10px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;text-decoration:none;font-weight:bold">阅读全文</a></p>
  <p style="font-size:12px"><a href="{unsub}" style="color:#64748b">退订邮件通知</a></p>"""))
