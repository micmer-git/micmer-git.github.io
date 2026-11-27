(() => {
  const dialog = document.querySelector('dialog.reader');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const view = dialog.querySelector('.reader-view');
  const title = dialog.querySelector('#reader-title');
  const closeButton = dialog.querySelector('[data-reader-close]');
  const previous = dialog.querySelector('[data-reader-prev]');
  const next = dialog.querySelector('[data-reader-next]');
  const zoomButton = dialog.querySelector('[data-reader-zoom]');
  const download = dialog.querySelector('[data-reader-download]');
  const pageOutput = dialog.querySelector('[data-reader-page]');
  const status = dialog.querySelector('[data-reader-status]');
  const transcript = dialog.querySelector('[data-reader-text]');
  let canvas = view.querySelector('canvas');
  let session;

  function fitWidth() {
    const style = getComputedStyle(view);
    return Math.max(1, view.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  }

  function controls() {
    const total = session.pdf?.numPages ?? 0;
    previous.disabled = session.number <= 1 || !total;
    next.disabled = session.number >= total;
    zoomButton.disabled = !total;
    zoomButton.setAttribute('aria-pressed', String(session.zoomed));
    pageOutput.textContent = total ? `Page ${session.number} of ${total}` : '';
  }

  function busy(message) {
    status.hidden = false;
    status.textContent = message;
    view.setAttribute('aria-busy', 'true');
  }

  function showError() {
    canvas.hidden = true;
    transcript.textContent = '';
    status.hidden = false;
    status.textContent = 'This page could not be displayed. ';
    const link = document.createElement('a');
    link.href = download.href;
    link.textContent = 'Open the original PDF';
    link.target = '_blank';
    link.rel = 'noopener';
    status.append(link);
    view.setAttribute('aria-busy', 'false');
  }

  async function pageText(page) {
    try {
      const content = await page.getTextContent();
      return content.items.map(item => (item.str || '') + (item.hasEOL ? '\n' : ' ')).join('').trim();
    } catch {
      return '';
    }
  }

  async function draw() {
    const current = session;
    if (!current?.pdf) return;
    const revision = ++current.revision;
    const active = () => session === current && current.revision === revision && dialog.open;
    current.render?.cancel();
    current.width = fitWidth();
    busy(`Loading page ${current.number}…`);
    try {
      const page = await current.pdf.getPage(current.number);
      if (!active()) return;
      const width = current.width * (current.zoomed ? 2 : 1);
      const viewport = page.getViewport({scale: width / page.getViewport({scale: 1}).width});
      const density = Math.min(window.devicePixelRatio || 1, 2, 4096 / Math.max(width, viewport.height));
      // A render owns its canvas. Cancelling a previous frame can finish asynchronously.
      const frame = document.createElement('canvas');
      frame.setAttribute('aria-hidden', 'true');
      frame.style.maxWidth = 'none';
      frame.style.width = `${width}px`;
      frame.style.height = `${viewport.height}px`;
      frame.width = Math.max(1, Math.round(width * density));
      frame.height = Math.max(1, Math.round(viewport.height * density));
      const options = {canvas: frame, viewport, transform: [density, 0, 0, density, 0, 0]};
      current.render = page.render(options);
      const text = pageText(page);
      await current.render.promise;
      if (!active()) return;
      canvas.replaceWith(frame);
      canvas = frame;
      status.hidden = true;
      view.setAttribute('aria-busy', 'false');
      const contents = await text;
      if (active()) transcript.textContent = contents || 'This page contains an illustration. The original PDF is available to download.';
    } catch {
      if (active()) showError();
    }
  }

  async function openReader(link) {
    const paper = link.closest('.paper');
    const current = {
      link, number: 1, zoomed: false, revision: 0, width: 0,
      x: window.scrollX, y: window.scrollY,
      overflow: document.documentElement.style.overflow
    };
    session = current;
    title.textContent = paper?.dataset.title || paper?.querySelector('h3')?.textContent || 'Publication';
    download.href = link.href;
    transcript.textContent = '';
    canvas.hidden = true;
    controls();
    busy('Opening PDF…');
    dialog.showModal();
    document.documentElement.style.overflow = 'hidden';
    closeButton.focus({preventScroll: true});
    view.scrollTo(0, 0);
    try {
      const pdfjs = await import('./vendor/pdfjs/pdf.min.mjs');
      if (session !== current) return;
      pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/pdf.worker.min.mjs', document.baseURI).href;
      current.loading = pdfjs.getDocument({url: link.href, isEvalSupported: false});
      const pdf = await current.loading.promise;
      if (session !== current) return;
      current.pdf = pdf;
      controls();
      draw();
    } catch {
      if (session === current && dialog.open) showError();
    }
  }

  function turn(delta) {
    if (!session?.pdf) return;
    const number = session.number + delta;
    if (number < 1 || number > session.pdf.numPages) return;
    session.number = number;
    canvas.hidden = true;
    transcript.textContent = '';
    view.scrollTo(0, 0);
    controls();
    draw();
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-read]');
    if (!link || session || event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    openReader(link);
  });
  previous.addEventListener('click', () => turn(-1));
  next.addEventListener('click', () => turn(1));
  zoomButton.addEventListener('click', () => {
    if (!session?.pdf) return;
    session.zoomed = !session.zoomed;
    view.scrollTo(0, 0);
    controls();
    draw();
  });
  closeButton.addEventListener('click', () => dialog.close());
  // Native dialog handles Escape and keeps tab focus inside until it closes.
  dialog.addEventListener('close', () => {
    const current = session;
    if (!current) return;
    session = undefined;
    current.render?.cancel();
    current.loading?.destroy().catch(() => {});
    canvas.width = canvas.height = 1;
    canvas.hidden = true;
    transcript.textContent = '';
    document.documentElement.style.overflow = current.overflow;
    current.link.focus({preventScroll: true});
    window.scrollTo({left: current.x, top: current.y, behavior: 'instant'});
  });
  function resize() {
    if (dialog.open && session?.pdf && Math.abs(session.width - fitWidth()) >= 1) draw();
  }
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(view);
  else window.addEventListener('resize', resize);
})();
