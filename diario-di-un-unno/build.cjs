#!/usr/bin/env node
// Build diario-di-un-unno/index.html from content JSON
const fs = require('fs');
const path = require('path');

const contentPath = path.join('C:/Users/micme/Desktop/micmer/openclaw/tmp/intervals/diario-unno-content.json');
const outPath = path.join(__dirname, 'index.html');
const data = JSON.parse(fs.readFileSync(contentPath, 'utf8'));

const fmt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');

const navDots = data.months.map(m => `<a class="dot" href="#m-${m.id}" title="${m.period} — ${m.title}">${m.mood}</a>`).reverse().join('');

const monthSections = [...data.months].reverse().map(m => `
  <article class="story" id="m-${m.id}">
    <header class="story-head">
      <span class="month-num">${m.period} · ${m.weeks}</span>
      <span class="month-mood">${m.mood}</span>
    </header>
    <h2 class="story-title">${m.title}</h2>
    <div class="story-body">${m.body}</div>
    <div class="stat-strip">${m.stat}</div>
  </article>
`).join('');

const html = `<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${data.title} — ${data.author}</title>
<meta name="description" content="${data.subtitle}: ${data.stats.months} capitoli mensili dall'aprile 2023 al giugno 2026 — un romanzo in numeri di Michele Merelli.">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;600&family=Cinzel:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root {
    /* Nordic / Hun palette: deep stone, ember red, antique bronze, parchment */
    --bg: #1a1814; --paper: #221f1a; --paper-2: #2b2620;
    --ink: #e8dfc9; --ink-soft: #c8b894;
    --gold: #c89a3f; --gold-soft: rgba(200,154,63,0.15);
    --rule: rgba(200,154,63,0.25);
    --muted: #8a7d62; --accent: #b34a2e;
    --rune: #d4a453;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body { background: var(--bg); color: var(--ink); font-family: 'EB Garamond', Georgia, serif; font-size: 19px; line-height: 1.7; max-width: 760px; margin: 0 auto; padding: 60px 28px 100px; }
  body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: -1;
    background-image:
      radial-gradient(ellipse at 12% 20%, rgba(200,154,63,0.08) 0, transparent 45%),
      radial-gradient(ellipse at 85% 78%, rgba(179,74,46,0.06) 0, transparent 45%),
      radial-gradient(circle at 50% 8%, rgba(200,154,63,0.04) 0, transparent 35%);
  }
  h1.cover { font-family: 'Cinzel', serif; font-size: 2.8rem; font-weight: 700; letter-spacing: 0.05em; text-align: center; line-height: 1.1; margin-bottom: 8px; color: var(--ink); }
  h1.cover .accent { display: block; font-size: 0.4em; letter-spacing: 0.25em; text-transform: uppercase; color: var(--gold); margin-bottom: 12px; }
  h1.cover .runes { display: block; font-size: 0.55em; letter-spacing: 0.4em; color: var(--rune); margin-top: 14px; opacity: 0.75; }
  .cover-sub { text-align: center; color: var(--ink-soft); font-style: italic; max-width: 560px; margin: 24px auto 30px; font-size: 1.1rem; line-height: 1.5; }
  .cover-stats { display: flex; gap: 28px; justify-content: center; flex-wrap: wrap; margin: 30px 0 24px; }
  .cover-stat { text-align: center; }
  .cover-stat .num { font-family: 'Cinzel', serif; font-size: 1.7rem; color: var(--gold); font-weight: 700; }
  .cover-stat .label { font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); margin-top: 4px; }
  .ornament { text-align: center; color: var(--gold); margin: 36px 0; font-size: 1.4rem; letter-spacing: 1.2em; opacity: 0.7; }
  .reading-note { background: var(--paper); border: 1px dashed var(--rule); padding: 16px 22px; margin: 28px auto; max-width: 540px; font-size: 0.92rem; color: var(--ink-soft); font-style: italic; text-align: center; border-radius: 4px; }
  .reading-note strong { color: var(--accent); font-style: normal; font-family: 'IBM Plex Mono', monospace; font-size: 0.85em; letter-spacing: 0.12em; text-transform: uppercase; }

  /* Prologue special block */
  .prologue { margin: 50px 0; padding: 30px 28px; background: var(--paper); border: 1px solid var(--rule); border-radius: 6px; position: relative; }
  .prologue::before { content: "✦"; position: absolute; top: -14px; left: 50%; transform: translateX(-50%); background: var(--bg); padding: 0 12px; color: var(--gold); font-size: 1.2rem; }
  .prologue .ptag { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold); display: block; text-align: center; margin-bottom: 6px; }
  .prologue h2 { font-family: 'Cinzel', serif; font-size: 1.6rem; font-weight: 700; text-align: center; color: var(--ink); margin-bottom: 4px; }
  .prologue .psub { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: var(--muted); text-align: center; margin-bottom: 20px; letter-spacing: 0.05em; }
  .prologue p { margin-bottom: 14px; font-size: 1.04rem; }
  .prologue strong { color: var(--rune); font-weight: 600; }

  /* Month nav */
  .month-grid { display: grid; grid-template-columns: repeat(13, 1fr); gap: 6px; max-width: 560px; margin: 32px auto; }
  .month-grid .dot { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; background: var(--paper); border: 1px solid var(--rule); border-radius: 4px; text-decoration: none; transition: all 0.25s ease; }
  .month-grid .dot:hover { transform: translateY(-2px); border-color: var(--gold); background: var(--gold-soft); }

  /* Month chapter */
  .story { margin: 64px 0; padding-bottom: 48px; border-bottom: 1px dashed var(--rule); scroll-margin-top: 30px; }
  .story:last-child { border-bottom: none; }
  .story-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
  .month-num { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--gold); }
  .month-mood { font-size: 1.6rem; }
  h2.story-title { font-family: 'Cinzel', serif; font-size: 1.7rem; font-weight: 700; margin-bottom: 18px; line-height: 1.2; color: var(--ink); }
  .story-body { font-size: 1.05rem; }
  .story-body p { margin-bottom: 14px; }
  .story-body p:first-child::first-letter { font-family: 'Cinzel', serif; font-size: 2.8rem; float: left; line-height: 0.9; padding: 6px 10px 0 0; color: var(--gold); }
  .story-body strong { color: var(--rune); font-weight: 600; }
  .story-body em { color: var(--ink-soft); }
  .story-body a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--rule); transition: all 0.2s; }
  .story-body a:hover { color: var(--gold); border-bottom-color: var(--gold); }
  .stat-strip { margin-top: 22px; padding-top: 14px; border-top: 1px solid var(--rule); font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: var(--muted); letter-spacing: 0.05em; }

  .end-marker { text-align: center; margin: 60px 0 30px; font-family: 'Cinzel', serif; color: var(--gold); font-size: 1.2rem; letter-spacing: 0.25em; }
  .colophon { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; text-align: center; color: var(--muted); margin-top: 60px; letter-spacing: 0.1em; line-height: 2; }
  .colophon a { color: var(--gold); text-decoration: none; border-bottom: 1px dotted var(--muted); }
  .colophon a:hover { border-bottom-color: var(--gold); }

  @media (max-width: 600px) {
    body { font-size: 17px; padding: 30px 18px 60px; }
    h1.cover { font-size: 2rem; }
    h2.story-title { font-size: 1.45rem; }
    .month-grid { grid-template-columns: repeat(8, 1fr); }
    .cover-stats { gap: 18px; }
    .cover-stat .num { font-size: 1.4rem; }
  }
</style>
</head>
<body>

<h1 class="cover">
  <span class="accent">${data.subtitle}</span>
  ${data.title}
  <span class="runes">ᚺᚢᚾ · ᛗᛁᚲᚺᛖᛚᛖ · ᚹᛟᛚᚠ</span>
</h1>
<p class="cover-sub">Un romanzo in numeri di ${data.author}, mese per mese.<br>${data.stats.months} lune di gambe, di tribù, di metri verticali.</p>

<div class="cover-stats">
  <div class="cover-stat"><div class="num">${data.stats.months}</div><div class="label">Lune</div></div>
  <div class="cover-stat"><div class="num">${fmt(data.stats.activities)}</div><div class="label">Sortite</div></div>
  <div class="cover-stat"><div class="num">${fmt(data.stats.km)}</div><div class="label">km</div></div>
  <div class="cover-stat"><div class="num">${fmt(data.stats.elev)}</div><div class="label">m saliti</div></div>
  <div class="cover-stat"><div class="num">${fmt(data.stats.kj)}</div><div class="label">kJ forgiati</div></div>
  <div class="cover-stat"><div class="num">${fmt(data.stats.hours)}</div><div class="label">h in moto</div></div>
</div>

<div class="reading-note">
  <strong>Come si legge</strong><br>
  L'ordine in pagina è il più recente in alto. Il diario va letto <em>dal basso verso l'alto</em>: la <em>preistoria</em> è in fondo, il presente in cima.
  Ogni capitolo è una luna piena, non un riassunto.
</div>

<div class="ornament">⚜ · ⚜ · ⚜</div>

<nav class="month-grid" aria-label="${data.stats.months} lune">${navDots}</nav>

<div class="ornament">·</div>

${monthSections}

<div class="prologue" id="m-prologue">
  <span class="ptag">⚔ ${data.prologue.title}</span>
  <h2>${data.prologue.subtitle}</h2>
  <p class="psub">prima dei dati · prima del wattmetro · prima del 2024</p>
  ${data.prologue.body}
</div>

<div class="end-marker">⚜ FINIS ⚜</div>

<div class="colophon">
  Composto a Bergamo Alta · ${data.author}<br>
  ${data.stats.months} lune dall'aprile 2023 al giugno 2026<br>
  <a href="../signore-dei-kj.html">↗ Il Signore dei kJ, mese per mese</a> ·
  <a href="../">↗ Indice</a>
</div>

</body>
</html>
`;

fs.writeFileSync(outPath, html, 'utf8');
console.log('Wrote', outPath, '(' + (html.length / 1024).toFixed(1) + ' KB)');
console.log('Months:', data.months.length);
console.log('Total stats: ' + data.stats.activities + ' activities, ' + data.stats.km + ' km, ' + data.stats.elev + ' m elev');
