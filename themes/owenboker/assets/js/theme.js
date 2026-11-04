(function(){
  // 快速搜索弹窗（⌘K / Ctrl+K / 点击导航搜索框触发）
  var qsModal = document.querySelector('[data-qs-modal]');
  var qsOpenFn = function(){}, qsCloseFn = function(){}, qsIsOpen = function(){ return false; };
  if (qsModal) {
    var qsInput = qsModal.querySelector('[data-qs-input]');
    var qsList = qsModal.querySelector('[data-qs-results]');
    var qsLang = (document.documentElement.lang || 'zh').toLowerCase().indexOf('zh') === 0
      ? 'zh' : (document.documentElement.lang || '').toLowerCase();
    var qsHint = qsModal.getAttribute('data-qs-hint') || 'Type to search';
    var qsEmpty = qsModal.getAttribute('data-qs-empty') || 'No results';
    var qsItems = [], qsActive = -1, qsTimer = null, qsSeq = 0;
    var esc = function(s){ var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; };
    var qsMsg = function(msg){
      qsItems = []; qsActive = -1;
      qsList.innerHTML = '<div class="px-4 py-8 text-center text-sm text-[var(--faint)]">' + esc(msg) + '</div>';
    };
    var qsPaint = function(){
      if (!qsItems.length) { qsMsg(qsEmpty); return; }
      qsList.innerHTML = qsItems.map(function(it, i){
        return '<a href="' + esc(it.url) + '" data-qs-item="' + i + '" class="flex items-center gap-3 px-3 py-2.5 rounded-lg no-underline' +
          (i === qsActive ? ' bg-[var(--wash)]' : '') + '">' +
          '<span class="flex-1 min-w-0"><span class="block truncate text-sm font-medium text-[var(--ink)]">' + esc(it.title) + '</span>' +
          '<span class="block truncate text-xs text-[var(--faint)]">' + esc(it.category || '') + (it.category && it.date ? ' · ' : '') + esc(it.date || '') + '</span></span>' +
          '<span class="flex-none text-[var(--ghost)]">↵</span></a>';
      }).join('');
    };
    var qsSearch = function(){
      var q = qsInput.value.trim();
      if (!q) { qsMsg(qsHint); return; }
      var seq = ++qsSeq;
      fetch('/api/quick-search?q=' + encodeURIComponent(q) + '&lang=' + encodeURIComponent(qsLang))
        .then(function(r){ return r.ok ? r.json() : []; })
        .then(function(data){
          if (seq !== qsSeq) return;
          qsItems = Array.isArray(data) ? data : [];
          qsActive = qsItems.length ? 0 : -1;
          qsPaint();
        })
        .catch(function(){});
    };
    qsOpenFn = function(){
      qsModal.classList.remove('hidden'); qsModal.classList.add('flex');
      document.body.style.overflow = 'hidden';
      if (!qsInput.value.trim()) qsMsg(qsHint);
      setTimeout(function(){ qsInput.focus(); qsInput.select(); }, 30);
    };
    qsCloseFn = function(){
      qsModal.classList.add('hidden'); qsModal.classList.remove('flex');
      document.body.style.overflow = '';
    };
    qsIsOpen = function(){ return !qsModal.classList.contains('hidden'); };
    qsInput.addEventListener('input', function(){
      clearTimeout(qsTimer); qsTimer = setTimeout(qsSearch, 200);
    });
    qsInput.addEventListener('keydown', function(e){
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!qsItems.length) return;
        qsActive = (qsActive + (e.key === 'ArrowDown' ? 1 : -1) + qsItems.length) % qsItems.length;
        qsPaint();
        var el = qsList.querySelector('[data-qs-item="' + qsActive + '"]');
        if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var it = qsItems[qsActive >= 0 ? qsActive : 0];
        if (it) window.location.href = it.url;
      } else if (e.key === 'Escape') {
        qsCloseFn();
      }
    });
  }
  // 主题切换 + 移动端抽屉菜单
  function applyTheme(dark){
    document.documentElement.classList.toggle('dark', dark);
    try{ localStorage.setItem('owenboker-theme', dark ? 'dark' : 'light'); }catch(e){}
  }
  document.addEventListener('click', function(e){
    var qo = e.target.closest('[data-qs-open]');
    if (qo) { e.preventDefault(); qsOpenFn(); return; }
    var qc = e.target.closest('[data-qs-close]');
    if (qc) { qsCloseFn(); return; }
    var t = e.target.closest('[data-theme-toggle]');
    if (t) { applyTheme(!document.documentElement.classList.contains('dark')); return; }
    var m = e.target.closest('[data-mobile-menu-toggle]');
    if (m) { var d = document.querySelector('[data-mobile-menu]'); if (d) d.classList.add('open'); return; }
    var c = e.target.closest('[data-mobile-menu-close]');
    if (c) { var d2 = document.querySelector('[data-mobile-menu]'); if (d2) d2.classList.remove('open'); return; }
    var dm = e.target.closest('[data-docs-menu-toggle]');
    if (dm) { var dd = document.querySelector('[data-docs-menu]'); if (dd) dd.classList.add('open'); return; }
    var dc = e.target.closest('[data-docs-menu-close]');
    if (dc) { var dd2 = document.querySelector('[data-docs-menu]'); if (dd2) dd2.classList.remove('open'); return; }
    var nd = e.target.closest('[data-nav-dropdown-toggle]');
    if (nd) { nd.classList.toggle('open'); return; }
    var ds = e.target.closest('[data-docs-section-toggle]');
    if (ds) { var sec = ds.closest('[data-docs-section]'); if (sec) sec.classList.toggle('open'); return; }
  });
  // 键盘：Escape 关闭抽屉/下拉；⌘K / Ctrl+K 打开快速搜索弹窗
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape') {
      if (qsIsOpen()) { qsCloseFn(); return; }
      var dd = document.querySelector('[data-docs-menu].open'); if (dd) { dd.classList.remove('open'); return; }
      var mm = document.querySelector('[data-mobile-menu].open'); if (mm) { mm.classList.remove('open'); return; }
      var nd = document.querySelector('[data-nav-dropdown-toggle].open'); if (nd) { nd.classList.remove('open'); return; }
    }
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
      var tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
      e.preventDefault();
      if (qsModal) qsOpenFn(); else window.location.href = '/search';
    }
  });

  // 滚动后给顶栏加 stuck（scrollY > 0），由透明铺底色
  var header = document.querySelector('[data-header]');
  if (header) {
    var checkStuck = function(){ header.classList.toggle('stuck', window.scrollY > 0); };
    window.addEventListener('scroll', function(){ requestAnimationFrame(checkStuck); }, { passive: true });
    checkStuck();
  }

  // 代码块复制按钮（注入到 .md-code-lang 栏）
  var COPY_LABELS = { copy: '复制', ok: '已复制', err: '错误' };
  if (document.documentElement.lang && document.documentElement.lang.indexOf('zh') !== 0) {
    COPY_LABELS = { copy: 'Copy', ok: 'Copied', err: 'Error' };
  }
  document.querySelectorAll('.md-code-block').forEach(function(block){
    var bar = block.querySelector('.md-code-lang');
    var code = block.querySelector('pre code');
    if (!bar || !code || bar.querySelector('.md-code-copy')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'md-code-copy';
    btn.textContent = COPY_LABELS.copy;
    btn.addEventListener('click', function(){
      var done = function(){ btn.textContent = COPY_LABELS.ok; setTimeout(function(){ btn.textContent = COPY_LABELS.copy; }, 1500); };
      var fail = function(){ btn.textContent = COPY_LABELS.err; setTimeout(function(){ btn.textContent = COPY_LABELS.copy; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code.innerText).then(done, fail);
      } else {
        try {
          var ta = document.createElement('textarea');
          ta.value = code.innerText; document.body.appendChild(ta); ta.select();
          document.execCommand('copy'); document.body.removeChild(ta); done();
        } catch(e) { fail(); }
      }
    });
    bar.appendChild(btn);
  });

  // 文档侧栏：滚动到当前项
  var curSidebar = document.querySelector('.dc-sidebar a .bg-\\[var\\(--accent\\)\\].w-1\\.5');
  if (curSidebar) {
    var link = curSidebar.closest('a');
    if (link && link.scrollIntoView) link.scrollIntoView({ block: 'center' });
  }

  // 侧栏 prev/next：按侧栏 DOM 顺序串链，覆盖后端日期序
  (function(){
    var sidebar = document.querySelector('[data-docs-menu]');
    if (!sidebar) return;
    var links = Array.from(sidebar.querySelectorAll('a[href]')).filter(function(a){ return a.querySelector('span') && !a.hasAttribute('data-docs-view-all'); });
    var curIdx = links.findIndex(function(a){ return a.querySelector('.bg-\\[var\\(--accent\\)\\].w-1\\.5'); });
    if (curIdx < 0) return;
    var fill = function(sel, link, label){
      var box = document.querySelector(sel);
      if (!box || !link) return;
      box.setAttribute('href', link.getAttribute('href'));
      var titleEl = box.querySelector('[data-docs-nav-title]');
      var t = link.querySelector('span:last-child');
      if (titleEl && t) titleEl.textContent = t.textContent;
    };
    fill('.docs-prev', links[curIdx - 1]);
    fill('.docs-next', links[curIdx + 1]);
  })();

  // PhotoSwipe 5 灯箱：正文图片点击放大
  (function(){
    var content = document.querySelector('.doc-content');
    if (!content) return;
    var imgs = Array.from(content.querySelectorAll('img')).filter(function(img){ return !img.closest('a'); });
    if (!imgs.length) return;
    var ready = false;
    imgs.forEach(function(img){
      var wrap = function(){
        if (img.closest('a')) return;
        var a = document.createElement('a');
        a.href = img.currentSrc || img.src;
        a.setAttribute('data-pswp-width', img.naturalWidth || 1200);
        a.setAttribute('data-pswp-height', img.naturalHeight || 800);
        a.target = '_blank';
        img.parentNode.insertBefore(a, img);
        a.appendChild(img);
      };
      if (img.complete && img.naturalWidth) wrap(); else img.addEventListener('load', wrap, { once: true });
    });
    var ensure = function(){
      if (ready) return Promise.resolve();
      ready = true;
      if (!document.querySelector('link[data-pswp-css]')) {
        var l = document.createElement('link');
        l.rel = 'stylesheet'; l.setAttribute('data-pswp-css', '1');
        l.href = 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.css';
        document.head.appendChild(l);
      }
      return Promise.all([
        import('https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js'),
        import('https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js'),
      ]);
    };
    content.addEventListener('click', function(e){
      var a = e.target.closest('a[data-pswp-width]');
      if (!a) return;
      e.preventDefault();
      ensure().then(function(mods){
        var LB = mods[0].default;
        var lb = new LB({
          gallery: content, children: 'a[data-pswp-width]',
          pswpModule: mods[1].default,
        });
        lb.init();
        var items = Array.from(content.querySelectorAll('a[data-pswp-width]'));
        lb.loadAndOpen(items.indexOf(a));
        ready = lb;
      });
    });
  })();
})();
