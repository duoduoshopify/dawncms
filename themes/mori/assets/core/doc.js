/* 文章页交互（原 ui.blog_article.DOC_JS）：TOC 高亮 + 阅读进度条 */
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
        var main = document.querySelector('.doc-main');
        if (!bar || !main) return;
        var rect = main.getBoundingClientRect();
        var total = main.scrollHeight - window.innerHeight;
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
