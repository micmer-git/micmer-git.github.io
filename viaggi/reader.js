(function () {
  const source = document.querySelector('[data-text-source]');
  const track = document.querySelector('[data-reader-track]');
  if (!source || !track) return;

  const counter = document.querySelector('[data-chunk-counter]');
  const progress = document.querySelector('[data-reader-progress]');
  const dotsWrapper = document.querySelector('[data-reader-dots]');
  const fab = document.querySelector('[data-reader-next]');
  const slides = [];
  const dots = [];
  let observer;
  let activeIndex = 0;

  function updateCounter(index) {
    const total = slides.length;
    const safeIndex = Math.min(Math.max(index, 0), Math.max(total - 1, 0));
    if (counter) {
      counter.textContent = total === 0 ? '0 / 0' : `${safeIndex + 1} / ${total}`;
    }
    if (progress) {
      const percentage = total === 0 ? 0 : ((safeIndex + 1) / total) * 100;
      progress.style.width = `${percentage}%`;
    }
  }

  function setActive(index) {
    activeIndex = index;
    slides.forEach((slide, i) => {
      slide.classList.toggle('is-active', i === activeIndex);
    });
    dots.forEach((dot, i) => {
      dot.classList.toggle('is-active', i === activeIndex);
    });
    updateCounter(activeIndex);
  }

  function scrollToIndex(nextIndex) {
    const target = slides[nextIndex];
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function handleFab() {
    const nextIndex = Math.min(slides.length - 1, activeIndex + 1);
    scrollToIndex(nextIndex);
  }

  function handleKeydown(event) {
    const key = event.key;
    const forwardKeys = ['ArrowDown', 'PageDown', ' '];
    const backwardKeys = ['ArrowUp', 'PageUp'];
    const isTextInput = ['INPUT', 'TEXTAREA'].includes(event.target.tagName) || event.target.isContentEditable;

    if (isTextInput) return;

    if (forwardKeys.includes(key)) {
      event.preventDefault();
      scrollToIndex(Math.min(slides.length - 1, activeIndex + 1));
    }

    if (backwardKeys.includes(key)) {
      event.preventDefault();
      scrollToIndex(Math.max(0, activeIndex - 1));
    }
  }

  function buildDots() {
    if (!dotsWrapper) return;
    dotsWrapper.innerHTML = '';
    slides.forEach((slide, index) => {
      const dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'reader-dot';
      dot.setAttribute('aria-label', `Vai alla sezione ${index + 1}`);
      dot.addEventListener('click', () => scrollToIndex(index));
      dotsWrapper.appendChild(dot);
      dots.push(dot);
    });
  }

  function buildSlides() {
    const sections = Array.from(source.querySelectorAll(':scope > section'));
    track.innerHTML = '';
    slides.length = 0;
    dots.length = 0;

    if (observer) observer.disconnect();

    if (sections.length === 0) {
      updateCounter(0);
      return;
    }

    sections.forEach((section, index) => {
      const slide = document.createElement('section');
      slide.className = 'reader-slide';
      slide.dataset.slideIndex = String(index);

      const corridor = document.createElement('div');
      corridor.className = 'reader-corridor';
      corridor.innerHTML = section.innerHTML;

      slide.appendChild(corridor);
      track.appendChild(slide);
      slides.push(slide);
    });

    buildDots();
    attachObserver();
    setActive(0);
    track.scrollTo({ top: 0 });
  }

  function attachObserver() {
    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = parseInt(entry.target.dataset.slideIndex || '0', 10);
            setActive(index);
          }
        });
      },
      { root: track, threshold: 0.6 }
    );

    slides.forEach((slide) => observer.observe(slide));
  }

  buildSlides();

  track.setAttribute('tabindex', '0');
  window.addEventListener('keydown', handleKeydown);
  window.addEventListener('resize', () => setActive(activeIndex));

  if (fab) {
    fab.addEventListener('click', handleFab);
  }

  document.addEventListener('reader:update', buildSlides);
})();
