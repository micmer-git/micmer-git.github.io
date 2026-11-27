(() => {
  'use strict';
  const root = document.documentElement;
  const motion = document.querySelector('.motion');
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let override;
  try { override = localStorage.getItem('micmer-neural-motion'); } catch {}
  const setMotion = () => {
    const on = override ? override === 'on' : !preference.matches;
    root.dataset.motion = on ? 'on' : 'off';
    motion.setAttribute('aria-pressed', String(on));
    motion.querySelector('b').textContent = root.dataset.motion;
    motion.title = on ? 'Pause scene animations' : 'Play scene animations';
  };
  setMotion();
  motion.hidden = false;
  motion.addEventListener('click', () => {
    override = root.dataset.motion === 'on' ? 'off' : 'on';
    try { localStorage.setItem('micmer-neural-motion', override); } catch {}
    setMotion();
    queueProgress();
  });
  preference.addEventListener('change', () => { setMotion(); queueProgress(); });
  document.querySelector('.sim-settings').hidden = false;

  const contents = document.querySelector('.contents');
  contents.addEventListener('click', event => {
    if (event.target.closest('a')) contents.open = false;
  });
  document.addEventListener('pointerdown', event => {
    if (!contents.contains(event.target)) contents.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && contents.open) {
      contents.open = false;
      contents.querySelector('summary').focus();
    }
  });
  const prologue = document.querySelector('.prologue');
  const wake = document.querySelector('.wake');
  const ink = wake.getContext('2d');
  let lastTide = -1;
  function drawWake(tide) {
    if (!ink || tide === lastTide) return;
    lastTide = tide;
    const w = wake.width, h = wake.height;
    ink.clearRect(0, 0, w, h);
    if (!tide) return;
    // Reuse the horizontal strokes of the water as the torn edge of the next page.
    for (let x = 0; x < w; x += 3) {
      const ripple = Math.sin(x * .042) * .23 + Math.sin(x * .12 + 2) * .1;
      const grain = .5 + .5 * Math.sin(38.9 * x);
      const depth = Math.max(1, Math.round(tide * (.52 + ripple + grain * .22)));
      ink.fillStyle = '#fafafa';
      ink.fillRect(x, h - depth, 3, depth);
      if (grain > .67) {
        ink.fillStyle = grain > .91 ? '#fafafa' : '#b8c6d4';
        ink.fillRect(x - 1, h - depth - Math.ceil(2 + grain * tide / 4), 2 + Math.round(grain * 3), 1);
      }
    }
  }
  let pending = false;
  function updateProgress() {
    pending = false;
    const scrollable = root.scrollHeight - innerHeight;
    root.style.setProperty('--read', scrollable ? Math.min(1, Math.max(0, scrollY / scrollable)) : 0);
    const exit = root.dataset.motion === 'on' ? Math.min(1, scrollY / Math.max(1, prologue.offsetHeight * .35)) : 0;
    prologue.style.setProperty('--hero-exit', exit);
    const tide = Math.max(0, Math.min(1, (scrollY / prologue.offsetHeight - .12) * 2.7));
    drawWake(root.dataset.motion === 'on' ? Math.round(35 * tide) : 0);
  }
  function queueProgress() {
    if (!pending) { pending = true; requestAnimationFrame(updateProgress); }
  }
  addEventListener('scroll', queueProgress, {passive:true});
  addEventListener('resize', queueProgress);
  updateProgress();

  const atlas = document.querySelector('[data-sequence]');
  const controls = document.querySelector('.atlas-controls');
  const step = document.querySelector('[data-atlas-next]');
  const status = document.querySelector('[data-atlas-status]');
  atlas.addEventListener('atlas-state', event => {
    const {stage, label} = event.detail;
    controls.hidden = stage === 0;
    step.textContent = stage === 1 ? 'Next design' : 'Next step';
    status.textContent = label;
  });
  step.addEventListener('click', () => {
    atlas.dispatchEvent(new CustomEvent('atlas-step', {detail:{direction:1}}));
  });
})();
