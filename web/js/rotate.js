/**
 * Auto-rotate between the two main pages (/ and /detail.html) every 20s.
 *
 * Useful for kiosk/bigscreen mode. Disable by appending ?norotate to the URL
 * when you need to interact with the page without getting bumped.
 * Respects tab visibility — pauses while the tab is hidden.
 */
(function(){
  if (new URLSearchParams(location.search).has('norotate')) return;

  const PAGES = ['/', '/detail.html'];
  const INTERVAL_MS = 20000;

  function currentKey(){
    const p = location.pathname;
    if (p === '/' || p === '/index.html') return '/';
    if (p === '/detail.html') return '/detail.html';
    return null;
  }

  const cur = currentKey();
  if (cur === null) return;
  const target = PAGES[(PAGES.indexOf(cur) + 1) % PAGES.length];
  // Keep the norotate flag out of the target URL so rotation continues on the next page.

  let timer = null;
  function schedule(){
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { if (!document.hidden) location.href = target; }, INTERVAL_MS);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (timer) { clearTimeout(timer); timer = null; } }
    else if (!timer) schedule();
  });
  schedule();
})();
