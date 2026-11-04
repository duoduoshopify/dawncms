/* 主题公共脚本：导航滚动阴影 */
(function () {
  var nav = document.querySelector('nav');
  if (!nav) return;
  function onScroll() {
    nav.style.boxShadow = window.scrollY > 8 ? '0 10px 30px -18px rgba(0,0,0,.45)' : 'none';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();
