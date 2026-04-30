/**
 * Auto-rotate between the two main pages (/ and /detail.html) every 20s.
 *
 * Hardened against multi-day kiosk drift:
 *   - Uses a wall-clock deadline (Date.now()) checked by setInterval, so a
 *     long-paused timer (browser tab freeze, throttling) can't desync.
 *     When the page resumes, the next tick will detect the missed deadline
 *     and switch immediately.
 *   - Listens to pageshow / resume / visibilitychange to re-arm the loop
 *     after browser power-saves the tab (Page Lifecycle freeze).
 *   - Self-heals via a 1-hour periodic location.reload() that clears any
 *     accumulated JS state, leaks, or stuck network requests.
 *
 * Disable rotation by appending ?norotate to the URL.
 */
(function () {
  if (new URLSearchParams(location.search).has('norotate')) return;

  const PAGES = ['/', '/detail.html'];
  const INTERVAL_MS = 20000;
  const HARD_RELOAD_MS = 60 * 60 * 1000;   // 1 hour

  function currentKey() {
    const p = location.pathname;
    if (p === '/' || p === '/index.html') return '/';
    if (p === '/detail.html') return '/detail.html';
    return null;
  }
  const cur = currentKey();
  if (cur === null) return;
  const target = PAGES[(PAGES.indexOf(cur) + 1) % PAGES.length];

  const startTs = Date.now();
  let nextSwitchAt = startTs + INTERVAL_MS;

  function maybeSwitch() {
    if (document.hidden) return;                              // wait until visible
    if (Date.now() < nextSwitchAt) return;                    // not due yet
    location.href = target;                                   // navigate
  }

  function maybeHardReload() {
    if (Date.now() - startTs >= HARD_RELOAD_MS) location.reload();
  }

  // Tick at 1Hz — cheap, and resilient to long pauses (deadline check
  // is wall-clock, not delta-based).
  setInterval(() => { maybeSwitch(); maybeHardReload(); }, 1000);

  // Re-check immediately on any visibility / lifecycle event so a
  // freeze-then-resume doesn't make us wait for the next 1s tick.
  ['pageshow', 'resume', 'visibilitychange', 'focus'].forEach(evt =>
    window.addEventListener(evt, maybeSwitch));
})();
