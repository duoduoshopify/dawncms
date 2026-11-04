# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# ui/blog_article.py
# 博客文章详情页渲染（TOC / 上一篇下一篇 / 相关文章 / JSON-LD）

import re



def dawn_extract_toc_and_anchors(raw_html: str) -> tuple[list, str]:
    toc_items = []
    h2_index = 0
    h3_index = 0

    def add_heading_ids(match):
        nonlocal h2_index, h3_index
        level, attrs, inner_html = match.group(1), match.group(2) or "", match.group(3) or ""
        heading_text = re.sub(r"<[^>]+>", "", inner_html).strip()
        if level == "2":
            h2_index += 1
            h3_index = 0
            anchor = f"section-{h2_index:02d}"
        else:
            if h2_index < 1:
                h2_index = 1
            h3_index += 1
            anchor = f"section-{h2_index:02d}-{h3_index:02d}"
        toc_items.append({"level": level, "text": heading_text or "未命名章节", "anchor": anchor})
        clean_attrs = re.sub(r'\sid="[^"]*"', "", attrs)
        return f'<h{level}{clean_attrs} id="{anchor}">{inner_html}</h{level}>'

    html_with_ids = re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", add_heading_ids, str(raw_html or ""), flags=re.S)
    return toc_items, html_with_ids


DAWN_DOC_CSS = """
.doc-shell{min-height:100vh}
.doc-progress{position:fixed;top:0;left:0;height:2px;width:0;background:linear-gradient(90deg,var(--accent),var(--accent-deep));z-index:60;transition:width .12s linear}
.doc-col{position:sticky;top:84px;max-height:calc(100vh - 100px);overflow:auto}
.doc-col::-webkit-scrollbar{width:4px}
.doc-col::-webkit-scrollbar-thumb{background:rgba(var(--muted-rgb),.35);border-radius:999px}
.doc-main{max-width:720px}
.doc-content{font-family:var(--doc-font);font-size:1.06rem}
.doc-content h2{font-size:1.55rem;font-weight:800;color:var(--ink);margin:2.6rem 0 1.1rem;padding-left:.9rem;border-left:4px solid var(--accent);line-height:1.4}
.doc-content h3{font-size:1.22rem;font-weight:700;color:var(--ink);margin:1.9rem 0 .8rem}
.doc-content h4{font-size:1.05rem;font-weight:600;color:var(--ink-soft);margin:1.3rem 0 .6rem}
.doc-content p{color:var(--ink-soft);line-height:2;margin:1.1rem 0}
.doc-content ul,.doc-content ol{color:var(--ink-soft);line-height:1.95;margin:1.1rem 0;padding-left:1.5rem}
.doc-content li{margin:.35rem 0}
.doc-content strong{color:var(--ink)}
.doc-content code{font-family:ui-monospace,monospace;background:var(--code-bg);color:var(--code-text);padding:.18rem .45rem;border-radius:5px;font-size:.88em}
.doc-content pre{background:var(--ink);border-radius:12px;padding:1.2rem;overflow:auto;margin:1.6rem 0}
.doc-content pre code{background:none;padding:0;color:var(--hairline-soft)}
.doc-content blockquote{border-left:3px solid var(--accent);background:var(--wash);padding:1rem 1.3rem;margin:1.6rem 0;color:var(--ink-2);border-radius:0 10px 10px 0}
.doc-content table{width:100%;border-collapse:collapse;margin:1.6rem 0;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:.92rem}
.doc-content th{background:var(--wash);color:var(--ink);padding:.75rem;text-align:left;border:1px solid var(--hairline)}
.doc-content td{padding:.75rem;border:1px solid var(--hairline-soft);color:var(--ink-soft)}
.doc-content img{max-width:100%;border-radius:12px;margin:1.6rem 0;border:1px solid var(--hairline-soft)}
.doc-content hr{border:0;border-top:1px solid var(--hairline);margin:2.4rem auto;width:40%}
.doc-content .md-cta{margin:1.9rem 0;padding:1.5rem 1.6rem;border-radius:16px;border:1px solid rgba(var(--accent-rgb),.3);background:linear-gradient(135deg,rgba(var(--accent-rgb),.07),rgba(var(--accent-rgb),.02))}
.doc-content .md-cta-title{font-size:1.05rem;font-weight:800;color:var(--ink)}
.doc-content .md-cta-desc{font-size:.95rem;color:var(--ink-2);margin-top:.5rem}
.doc-content .md-cta-btn{display:inline-block;margin-top:1rem;padding:.7rem 1.4rem;border-radius:999px;background:var(--ink);color:var(--paper);text-decoration:none;font-weight:600}
.doc-content .md-cta-btn:hover{background:var(--accent)}
.doc-content a{color:var(--accent);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:4px;text-decoration-color:rgba(var(--accent-rgb),.45);font-weight:600}
.doc-content a:hover{color:var(--accent-deep);text-decoration-color:var(--accent-deep)}
.doc-content code a,.doc-content pre a{color:inherit;text-decoration:none}
.toc-link{display:block;font-size:.84rem;color:var(--muted);padding:.35rem .6rem;border-radius:6px;border-left:2px solid transparent}
.toc-link:hover{color:var(--ink);background:rgba(var(--ink-rgb),.04)}
.toc-link.active{color:var(--accent);border-left-color:var(--accent);background:rgba(var(--accent-rgb),.06)}
.toc-h3{padding-left:1.5rem;font-size:.78rem}
.doc-content h2[id],.doc-content h3[id]{scroll-margin-top:88px}
html{scroll-behavior:smooth}
.doc-shell{overflow:visible !important}
.doc-main,.doc-content{min-width:0}
.doc-content{overflow-wrap:anywhere;word-break:break-word}
.doc-content table{display:block;max-width:100%;overflow-x:auto}
.doc-content iframe,.doc-content video,.doc-content .md-embed,.doc-content .md-code-block,.doc-content pre{max-width:100%}
.doc-content .md-embed iframe,.doc-content .md-embed video{display:block;width:100%;min-height:240px;border:0;background:var(--ink);border-radius:12px}
@media (max-width:767px){.doc-shell{overflow-x:hidden !important}.doc-content{font-size:1rem}.doc-content .md-embed iframe,.doc-content .md-embed video{min-height:200px}}
"""

DAWN_DOC_JS = """
(function () {
    function initDocInteractions() {
        var tocLinks = Array.from(document.querySelectorAll('.toc-link[data-anchor]'));
        if (!tocLinks.length) return;
        var headings = Array.from(document.querySelectorAll('.doc-content h2[id], .doc-content h3[id]'));
        if (!headings.length) return;

        function setActiveToc() {
            var pos = window.scrollY + 120;
            var current = headings[0].getAttribute('id');
            for (var i = 0; i < headings.length; i++) {
                if (headings[i].getBoundingClientRect().top + window.scrollY <= pos) {
                    current = headings[i].getAttribute('id');
                } else {
                    break;
                }
            }
            tocLinks.forEach(function (l) {
                l.classList.toggle('active', l.dataset.anchor === current);
            });
            var active = document.querySelector('.toc-link.active');
            if (active && active.scrollIntoView) {
                var col = active.closest('.doc-col');
                if (col) {
                    var r = active.getBoundingClientRect();
                    var cr = col.getBoundingClientRect();
                    if (r.top < cr.top + 40 || r.bottom > cr.bottom - 40) {
                        col.scrollTop += r.top - cr.top - cr.height / 3;
                    }
                }
            }
        }

        setActiveToc();
        window.addEventListener('scroll', setActiveToc, { passive: true });
        window.addEventListener('hashchange', function () { setTimeout(setActiveToc, 50); });
    }

    function mountCodeCopyButtons() {
        document.querySelectorAll('.md-code-block, .highlight').forEach(function (block) {
            if (block.querySelector('.md-code-copy')) return;
            block.style.position = 'relative';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'md-code-copy';
            btn.style.cssText = 'position:absolute;top:.55rem;right:.7rem;border:1px solid rgba(236,231,219,.3);background:rgba(248,246,241,.12);color:var(--hairline-soft);border-radius:8px;padding:.35rem .6rem;font-size:.72rem;font-weight:600;cursor:pointer;z-index:3';
            btn.textContent = '复制';
            btn.addEventListener('click', function () {
                var codeEl = block.querySelector('pre code, code');
                if (!codeEl) return;
                navigator.clipboard.writeText(codeEl.innerText || codeEl.textContent || '');
                btn.textContent = '已复制';
                setTimeout(function () { btn.textContent = '复制'; }, 1400);
            });
            block.appendChild(btn);
        });
    }

    function updateProgress() {
        var bar = document.querySelector('.doc-progress');
        var dawn_main = document.querySelector('.doc-main');
        if (!bar || !dawn_main) return;
        var rect = dawn_main.getBoundingClientRect();
        var total = dawn_main.scrollHeight - window.innerHeight;
        var passed = Math.min(Math.max(-rect.top, 0), Math.max(total, 1));
        bar.style.width = (passed / Math.max(total, 1) * 100) + '%';
    }

    function boot() {
        initDocInteractions();
        mountCodeCopyButtons();
        updateProgress();
        window.addEventListener('scroll', updateProgress, { passive: true });
        window.addEventListener('resize', updateProgress);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
"""


