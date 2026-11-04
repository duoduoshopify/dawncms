# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# services/markdown_renderer.py
# Markdown 渲染服务

import re
import markdown
from markdown.extensions import tables, fenced_code, toc, attr_list
from markdown.extensions.codehilite import CodeHiliteExtension

class DawnMarkdownRenderer:
    
    _md = None
    
    @classmethod
    def _get_md(cls):
        if cls._md is None:
            cls._md = markdown.Markdown(
                extensions=[
                    'tables',
                    'fenced_code',
                    'attr_list',
                    'codehilite',
                    'nl2br',
                    'sane_lists',
                ],
                extension_configs={
                    'codehilite': {
                        'css_class': 'highlight',
                        'linenums': False
                    }
                }
            )
        return cls._md
    
    @classmethod
    def dawn_render(cls, md_content: str) -> str:
        """渲染 Markdown 为 HTML"""
        md = cls._get_md()
        md.reset()  # 重置状态，避免多次调用时状态累积
        prepared = cls._preprocess_custom_blocks(md_content or '')
        html = md.convert(prepared)
        return cls._enhance_rendered_html(html)
    
    @classmethod
    def render_with_prose(cls, md_content: str) -> str:
        """渲染并包裹 prose 样式类"""
        html = cls.dawn_render(md_content)
        return f'<div class="prose prose-invert max-w-none">{html}</div>'
    
    @classmethod
    def extract_toc(cls, md_content: str) -> str:
        """提取目录结构"""
        md = cls._get_md()
        md.reset()
        md.convert(md_content or '')
        return md.toc if hasattr(md, 'toc') else ''

    @classmethod
    def extract_stats(cls, md_content: str) -> dict:
        text = md_content or ''
        word_count = len(re.findall(r"\S+", text))
        heading_count = len(re.findall(r"^#{1,6}\s+", text, flags=re.MULTILINE))
        image_count = len(re.findall(r"!\[[^\]]*\]\([^\)]+\)", text))
        code_block_count = len(re.findall(r"```", text)) // 2
        return {
            "word_count": word_count,
            "heading_count": heading_count,
            "image_count": image_count,
            "code_block_count": code_block_count,
        }

    @classmethod
    def render_preview_payload(cls, md_content: str) -> dict:
        return {
            "html": cls.render_with_prose(md_content),
            "toc": cls.extract_toc(md_content),
            "stats": cls.extract_stats(md_content),
        }

    @classmethod
    def _preprocess_custom_blocks(cls, md_content: str) -> str:
        text = md_content or ''

        def repl_cta(match):
            body = match.group(1) or ''
            fields = {}
            for line in body.splitlines():
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                fields[key.strip()] = value.strip()
            title = fields.get('title', '立即咨询')
            desc = fields.get('desc', '')
            button_text = fields.get('button_text', '查看详情')
            button_url = fields.get('button_url', '/contact')
            return (
                f'\n<div class="md-cta" data-md-block="cta">'
                f'<div class="md-cta-title">{title}</div>'
                f'<div class="md-cta-desc">{desc}</div>'
                f'<a class="md-cta-btn" href="{button_url}">{button_text}</a>'
                f'</div>\n'
            )

        def repl_embed(match):
            provider = (match.group(1) or '').strip().lower()
            url = (match.group(2) or '').strip()
            if provider == 'youtube':
                video_id = ''
                yt = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]+)', url)
                if yt:
                    video_id = yt.group(1)
                if video_id:
                    return (
                        '\n<div class="md-embed" data-md-block="youtube">'
                        f'<iframe src="https://www.youtube.com/embed/{video_id}" '
                        'title="YouTube video" loading="lazy" allowfullscreen></iframe>'
                        '</div>\n'
                    )
            if provider == 'video':
                return (
                    '\n<div class="md-embed" data-md-block="self-video">'
                    f'<video controls playsinline preload="metadata" src="{url}"></video>'
                    '</div>\n'
                )
            return f'\n<p><a href="{url}">{url}</a></p>\n'

        def _parse_kv_block(body: str):
            """解析 card 块内的 key: value 行 + 剩余正文行。返回 (kv dict, content str)。kv 值已 HTML 转义"""
            from html import escape as _esc
            kv, content_lines = {}, []
            for line in body.strip().splitlines():
                ls = line.strip()
                m = re.match(r'^(url|title|desc|text|icon|bg|image|author)\s*[:：]\s*(.+)$', ls)
                if m and not content_lines:
                    kv[m.group(1)] = _esc(m.group(2).strip(), quote=True)
                elif ls:
                    content_lines.append(line)
            return kv, "\n".join(content_lines).strip()

        def _inline_md(text: str) -> str:
            """卡片内嵌内容的轻量 markdown（粗体/斜体/链接/行内代码），先转义"""
            from html import escape as _esc
            t = _esc(str(text or ""))
            t = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', t)
            t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
            t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
            return t.replace("\n", "<br>")

        def repl_bookmark(match):
            kv, _ = _parse_kv_block(match.group(1))
            url = kv.get("url", "")
            if not url:
                return "\n"
            title = kv.get("title") or url
            desc = kv.get("desc", "")
            image = kv.get("image", "")
            import urllib.parse as _up
            domain = _up.urlparse(url).netloc
            return (
                '\n<figure class="md-card md-bookmark">'
                f'<a class="md-bookmark-container" href="{url}" target="_blank" rel="noopener">'
                f'<div class="md-bookmark-content">'
                f'<div class="md-bookmark-title">{title}</div>'
                + (f'<div class="md-bookmark-desc">{desc}</div>' if desc else '')
                + f'<div class="md-bookmark-meta"><span class="md-bookmark-domain">{domain}</span></div>'
                '</div>'
                + (f'<div class="md-bookmark-thumb"><img src="{image}" alt="" loading="lazy"></div>' if image else '')
                + '</a></figure>\n'
            )

        def repl_callout(match):
            kv, content = _parse_kv_block(match.group(1))
            icon = kv.get("icon", "💡")
            bg = kv.get("bg", "")
            style = f' style="background:{bg}"' if bg else ""
            return (
                f'\n<div class="md-card md-callout"{style}>'
                f'<div class="md-callout-icon">{icon}</div>'
                f'<div class="md-callout-content">{_inline_md(content)}</div>'
                '</div>\n'
            )

        def repl_toggle(match):
            kv, content = _parse_kv_block(match.group(1))
            title = kv.get("title", "展开")
            return (
                '\n<details class="md-card md-toggle">'
                f'<summary>{title}</summary>'
                f'<div class="md-toggle-content">{_inline_md(content)}</div>'
                '</details>\n'
            )

        def repl_button(match):
            kv, content = _parse_kv_block(match.group(1))
            text = kv.get("text") or content or "按钮"
            url = kv.get("url", "#")
            return (
                f'\n<div class="md-card md-button"><a href="{url}" class="md-button-btn">{text}</a></div>\n'
            )

        def repl_gallery(match):
            from html import escape as _esc
            kv, content = _parse_kv_block(match.group(1))
            imgs = []
            for line in (content or "").splitlines():
                parts = [x.strip() for x in line.split("|")]
                if parts and parts[0]:
                    imgs.append((_esc(parts[0], quote=True), _esc(parts[1], quote=True) if len(parts) > 1 else ""))
            if not imgs:
                return "\n"
            cells = "".join(
                f'<figure class="md-gallery-item"><img src="{u}" alt="{c}" loading="lazy">'
                + (f'<figcaption>{c}</figcaption>' if c else '') + '</figure>'
                for u, c in imgs
            )
            cols = min(len(imgs), 3)
            return f'\n<div class="md-card md-gallery md-gallery-cols-{cols}">{cells}</div>\n'

        def repl_header(match):
            kv, content = _parse_kv_block(match.group(1))
            bg = kv.get("bg", "")
            style = f' style="background:{bg}"' if bg else ""
            btn = ""
            if kv.get("text") and kv.get("url"):
                btn = f'<a class="md-header-btn" href="{kv["url"]}">{kv["text"]}</a>'
            return (
                f'\n<div class="md-card md-header"{style}>'
                f'<h2 class="md-header-title">{kv.get("title", "")}</h2>'
                + (f'<p class="md-header-desc">{_inline_md(content)}</p>' if content else '')
                + btn + '</div>\n'
            )

        text = re.sub(r':::cta\s+([\s\S]*?):::', repl_cta, text, flags=re.MULTILINE)
        text = re.sub(r':::bookmark\s+([\s\S]*?):::', repl_bookmark, text, flags=re.MULTILINE)
        text = re.sub(r':::callout\s+([\s\S]*?):::', repl_callout, text, flags=re.MULTILINE)
        text = re.sub(r':::toggle\s+([\s\S]*?):::', repl_toggle, text, flags=re.MULTILINE)
        text = re.sub(r':::button\s+([\s\S]*?):::', repl_button, text, flags=re.MULTILINE)
        text = re.sub(r':::gallery\s+([\s\S]*?):::', repl_gallery, text, flags=re.MULTILINE)
        text = re.sub(r':::header\s+([\s\S]*?):::', repl_header, text, flags=re.MULTILINE)
        text = re.sub(r':::embed\s+(youtube)\s+([^\n]+)\s+:::', repl_embed, text, flags=re.MULTILINE)
        text = re.sub(r':::embed\s+(video)\s+([^\n]+)\s+:::', repl_embed, text, flags=re.MULTILINE)
        return text

    @classmethod
    def _enhance_rendered_html(cls, html: str) -> str:
        html = re.sub(
            r'<pre><code class="language-([^"]+)">([\s\S]*?)</code></pre>',
            r'<div class="md-code-block"><div class="md-code-lang">\1</div><pre><code class="language-\1">\2</code></pre></div>',
            html,
            flags=re.MULTILINE,
        )
        return html
