// Scrollytelling glue: the paragraph you are reading drives the sticky figure beside it,
// and pixel oil drips between chapters. No libraries; everything pauses off-screen and
// respects the Motion toggle / prefers-reduced-motion.
(() => {
  'use strict';
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const moving = () => root.dataset.motion ? root.dataset.motion === 'on' : !reduced.matches;
  const hasIO = 'IntersectionObserver' in window;

  // 1. Oil chapter: each step selects the machine shown in the flow bench.
  const oil = document.querySelector('[data-scrolly="oil"]');
  if (oil) {
    const steps = [...oil.querySelectorAll('.step')];
    const pick = step => {
      steps.forEach(s => s.classList.toggle('is-active', s === step));
      const button = document.querySelector(`[data-machine="${step.dataset.step}"]`);
      if (button && button.getAttribute('aria-pressed') !== 'true') button.click();
    };
    steps.forEach(step => step.addEventListener('click', event => {
      if (!event.target.closest('a')) pick(step);
    }));
    // Keep the highlighted step honest when the reader uses the buttons directly.
    document.querySelectorAll('[data-machine]').forEach(button => button.addEventListener('click', () => {
      steps.forEach(s => s.classList.toggle('is-active', s.dataset.step === button.dataset.machine));
    }));
    if (hasIO) {
      const io = new IntersectionObserver(entries => {
        for (const entry of entries) if (entry.isIntersecting) pick(entry.target);
      }, {rootMargin: '-48% 0px -48% 0px'});
      steps.forEach(step => io.observe(step));
    }
    steps[0]?.classList.add('is-active');
  }

  // 2. Particle atlas: pips and the active beat follow the stage sequence.js publishes.
  const atlas = document.querySelector('[data-scrolly="atlas"]');
  if (atlas) {
    const pips = [...atlas.querySelectorAll('.pips li')];
    const beats = [...atlas.querySelectorAll('.beat')];
    const mark = stage => {
      pips.forEach((pip, i) => pip.classList.toggle('on', i <= stage));
      beats.forEach((beat, i) => beat.classList.toggle('is-active', i === stage));
    };
    atlas.addEventListener('atlas-state', event => mark(event.detail.stage));
    // sequence.js may have published before this script ran; read its caption instead.
    const label = atlas.querySelector('[data-sequence-label]');
    mark(Math.max(0, (parseInt(label?.textContent, 10) || 1) - 1));
  }

  // 3. Chapter dividers: a few pixels of oil drip from the end of a chapter into a pool.
  const W = 64, H = 26, POOL = H - 3;
  const ink = ['#36858d', '#54798a', '#98d8cb'];
  function drip(canvas) {
    canvas.width = W; canvas.height = H;
    const c = canvas.getContext('2d');
    if (!c) return;
    let visible = !hasIO, frame = 0, last = 0, t = 0, drops = [], fill = 0;
    const seed = [...canvas.parentElement.children].indexOf(canvas) * 7.31;
    function draw() {
      c.clearRect(0, 0, W, H);
      // pool: grows a little each time a drop lands, ripple is a 1px wave
      const width = Math.round(12 + fill * 34);
      const x0 = Math.round(W / 2 - width / 2);
      c.fillStyle = ink[0];
      c.fillRect(x0, POOL, width, 2);
      c.fillStyle = ink[2];
      for (let x = 0; x < width; x += 2) if (Math.sin(x * .7 + t * 6 + seed) > .55) c.fillRect(x0 + x, POOL - 1, 1, 1);
      // nozzle at the top
      c.fillStyle = ink[1];
      c.fillRect(W / 2 - 2, 0, 4, 2);
      for (const d of drops) {
        c.fillStyle = d.y > POOL - 6 ? ink[2] : ink[0];
        c.fillRect(Math.round(d.x), Math.round(d.y), 2, d.v > 30 ? 3 : 2);
        if (d.splash) {
          c.fillStyle = ink[2];
          c.fillRect(Math.round(d.x - d.splash), POOL - 2, 1, 1);
          c.fillRect(Math.round(d.x + 1 + d.splash), POOL - 2, 1, 1);
        }
      }
    }
    function still() { drops = [{x: W / 2 - 1, y: 9, v: 0}]; fill = .7; t = 0; draw(); }
    function tick(now) {
      frame = 0;
      if (!visible || document.hidden || !moving()) { last = 0; return; }
      const dt = last ? Math.min(.08, (now - last) / 1000) : 0;
      if (!last || now - last >= 40) {
        last = now; t += dt;
        if (Math.random() < dt * 1.6 && drops.length < 3) drops.push({x: W / 2 - 1 + Math.round(Math.sin(t + seed)), y: 2, v: 4});
        for (const d of drops) {
          if (d.splash) { d.splash += dt * 14; continue; }
          d.v += 90 * dt; d.y += d.v * dt;
          if (d.y >= POOL - 2) { d.y = POOL - 2; d.splash = 1; fill = Math.min(1, fill + .05); }
        }
        drops = drops.filter(d => !d.splash || d.splash < 4);
        draw();
      }
      frame = requestAnimationFrame(tick);
    }
    function sync() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0; last = 0;
      if (!moving()) { still(); return; }
      if (visible && !document.hidden) frame = requestAnimationFrame(tick);
    }
    if (hasIO) new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }).observe(canvas);
    new MutationObserver(sync).observe(root, {attributes: true, attributeFilter: ['data-motion']});
    reduced.addEventListener?.('change', sync);
    document.addEventListener('visibilitychange', sync);
    still(); sync();
  }
  document.querySelectorAll('canvas.drip').forEach(drip);
})();
