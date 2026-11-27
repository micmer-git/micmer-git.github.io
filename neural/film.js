(() => {
  'use strict';

  const frame = document.querySelector('[data-film-frame]');
  const mount = frame?.querySelector('[data-film-mount]');
  const poster = frame?.querySelector('.film-poster');
  if (!mount || !poster || !('IntersectionObserver' in window)) return;

  const root = document.documentElement;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const autoMotion = () => root.dataset.motion ? root.dataset.motion === 'on' : !reducedMotion.matches;
  let inView = false;
  let started = false;
  let failed = false;
  let player;
  let ready = false;
  let requestedByViewer = false;
  let viewerPaused = false;
  let pagePausing = false;
  let timer;
  mount.hidden = true;

  function pause() {
    if (ready && [1, 3].includes(player.getPlayerState())) {
      pagePausing = true;
      player.pauseVideo();
    }
  }

  function update() {
    if (!ready) return;
    if (!inView || document.hidden || !autoMotion()) {
      pause();
    } else if (!viewerPaused) {
      player.playVideo();
    }
  }

  function fallback() {
    clearTimeout(timer);
    failed = true;
    ready = false;
    mount.hidden = true;
    poster.hidden = false;
    player?.destroy();
    mount.replaceChildren();
  }

  function connect() {
    if (failed || player) return;
    const iframe = document.createElement('iframe');
    iframe.title = '3D Printing Helices — Particleworks Europe';
    iframe.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = 'strict-origin-when-cross-origin';
    iframe.src = 'https://www.youtube-nocookie.com/embed/AH0ia7rLy0s?' + new URLSearchParams({
      enablejsapi: '1', playsinline: '1', controls: '1', mute: '1', origin: location.origin
    });
    mount.replaceChildren(iframe);
    player = new window.YT.Player(iframe, {events: {
      onReady() {
        clearTimeout(timer);
        ready = true;
        player.mute();
        poster.hidden = true;
        mount.hidden = false;
        if (requestedByViewer && inView && !document.hidden) player.playVideo();
        else update();
        requestedByViewer = false;
      },
      onStateChange({data}) {
        if (data === 1) {
          viewerPaused = false;
          if (!inView || document.hidden) pause();
        } else if (data === 2) {
          if (!pagePausing) viewerPaused = true;
          pagePausing = false;
        } else if (data === 0) {
          viewerPaused = true;
        }
      },
      onError: fallback
    }});
  }

  function load() {
    started = true;
    timer = setTimeout(fallback, 16000);
    if (window.YT?.Player) { connect(); return; }
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      connect();
    };
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.onerror = fallback;
    document.head.appendChild(script);
  }

  poster.addEventListener('click', event => {
    if (failed || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    requestedByViewer = true;
    if (!inView) frame.scrollIntoView({block: 'nearest', behavior: 'instant'});
    if (!started) load();
  });

  new IntersectionObserver(([entry]) => {
    const nowVisible = entry.isIntersecting && entry.intersectionRatio >= 0.35;
    if (nowVisible === inView) return;
    inView = nowVisible;
    if (inView && !started) load();
    else update();
  }, {threshold: [0, 0.35]}).observe(frame);
  document.addEventListener('visibilitychange', update);
  new MutationObserver(update).observe(root, {attributes: true, attributeFilter: ['data-motion']});
  reducedMotion.addEventListener('change', () => { if (!root.dataset.motion) update(); });
})();
