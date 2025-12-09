(function () {
  const source = document.querySelector('[data-text-source]');
  const track = document.querySelector('[data-reader-track]');
  if (!source || !track) return;

  const counter = document.querySelector('[data-chunk-counter]');
  const progress = document.querySelector('[data-reader-progress]');
  let words = collectWords(source);
  let slides = [];

  function collectWords(node) {
    const allowed = node.querySelectorAll('p, blockquote, li, figcaption, h2, h3');
    const merged = Array.from(allowed)
      .map((el) => el.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .join(' ');
    return merged.split(/\s+/).filter(Boolean);
  }

  function debounce(fn, delay) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), delay);
    };
  }

  function wordsPerSlide() {
    const base = window.innerWidth < 640 ? 120 : 170;
    const heightFactor = Math.max(0.75, Math.min(1.5, window.innerHeight / 820));
    const widthFactor = Math.max(0.85, Math.min(1.25, track.clientWidth / 940));
    return Math.max(70, Math.round(base * heightFactor * widthFactor));
  }

  function updateCounter(activeIndex) {
    const total = slides.length;
    const safeIndex = total === 0 ? 0 : activeIndex;
    if (counter) {
      counter.textContent = total === 0 ? '0 / 0' : `${safeIndex + 1} / ${total}`;
    }
    if (progress) {
      const percentage = total === 0 ? 0 : ((safeIndex + 1) / total) * 100;
      progress.style.width = `${percentage}%`;
    }
  }

  function buildSlides() {
    words = collectWords(source);
    const chunkSize = wordsPerSlide();
    track.innerHTML = '';
    slides = [];

    for (let i = 0; i < words.length; i += chunkSize) {
      const slice = words.slice(i, i + chunkSize);
      const slide = document.createElement('section');
      slide.className = 'reader-slide';
      slide.innerHTML = `<p>${slice.join(' ')}</p>`;
      track.appendChild(slide);
      slides.push(slide);
    }

    updateCounter(0);
  }

  function syncOnScroll() {
    const index = Math.round(track.scrollLeft / track.clientWidth);
    const safeIndex = Math.min(slides.length - 1, Math.max(0, index));
    updateCounter(safeIndex);
  }

  const rebuild = debounce(buildSlides, 250);

  track.addEventListener('scroll', syncOnScroll);
  window.addEventListener('resize', rebuild);
  document.addEventListener('reader:update', rebuild);
  track.setAttribute('tabindex', '0');

  buildSlides();
})();
