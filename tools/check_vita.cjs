/* Smoke test per vita/index.html — senza browser e senza dipendenze.
 *
 * jsdom non si installa da questa rete, e comunque il resto di tools/ gira in sola
 * stdlib: qui il DOM e' uno shim di poche decine di righe. Regge perche' la pagina
 * costruisce i nodi uno a uno e se ne tiene il riferimento, invece di scrivere
 * innerHTML e poi rileggerlo con querySelector — se un giorno torna a farlo, questo
 * check smette di girare, ed e' il segnale giusto.
 *
 * Cosa verifica:
 *   1. lo script gira senza eccezioni, e ogni riquadro si disegna su TUTTE e quattro
 *      le finestre temporali (un renderer che esplode viene ripreso dalla pagina, ma
 *      lascia il motivo in data-err: qui e' un errore, non un riquadro vuoto);
 *   2. nessuna coordinata NaN/Infinity in nessun attributo SVG — il modo tipico in cui
 *      un grafico sbagliato non si vede invece di rompersi;
 *   3. i totali in testata rifatti a mano dal payload coincidono con quelli scritti;
 *   4. ogni riquadro ha la sua tabella di ripiego, e ogni riquadro con piu' di una
 *      serie ha la legenda (l'identita' non puo' stare nel solo colore);
 *   5. la tavolozza nel CSS e' ancora quella validata contro il fondo della scheda;
 *   6. il buco 2021-2023 e' dichiarato fra i gaps: le zone "nessun dato" dipendono
 *      da quello, e senza si tornerebbe a disegnare una linea attraverso il vuoto.
 *
 *   node tools/check_vita.cjs
 *
 * L'esito viene appeso a tools/vita_tests.md insieme a quello dei build.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const PAGE = path.join(ROOT, "vita", "index.html");
const REPORT = path.join(__dirname, "vita_tests.md");

const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const fails = [], notes = [];
const ok = (cond, msg) => { (cond ? notes : fails).push((cond ? "ok   " : "FAIL ") + msg); };

/* Il payload viene inlineato dentro <script>: se un nome di attivita' o di
   alimento contenesse "</script" il browser chiuderebbe li' il blocco e la pagina
   resterebbe senza JS — cioe' senza un solo grafico, senza nessun errore visibile
   nel sorgente. Si controlla che i tag siano esattamente due e che lo script
   arrivi in fondo. */
{
  const opens = (html.match(/<script>/g) || []).length;
  const closes = (html.match(/<\/script>/g) || []).length;
  const body = (html.match(/<script>([\s\S]*?)<\/script>/) || [])[1] || "";
  const okTags = opens === 1 && closes === 1;
  (okTags ? notes : fails).push((okTags ? "ok   " : "FAIL ") +
    `un solo blocco <script> (aperti ${opens}, chiusi ${closes}) — nessun "</script" nel payload`);
  const ends = /drawAll\(\);/.test(body.slice(-400));
  (ends ? notes : fails).push((ends ? "ok   " : "FAIL ") +
    `lo script arriva in fondo (${(body.length / 1024).toFixed(0)} KB, chiude su drawAll)`);
}

/* ----------------------------------------------------------------- DOM shim */
const ALL = [];
class Node {
  constructor(tag, ns) {
    this.tagName = tag; this.ns = ns || null;
    this.attrs = {}; this._kids = []; this.parent = null;
    this.style = { setProperty() {} }; this.dataset = {};
    this._text = ""; this._html = "";
    this.classList = {
      _s: new Set(),
      add: (...c) => c.forEach(x => this.classList._s.add(x)),
      remove: (...c) => c.forEach(x => this.classList._s.delete(x)),
      contains: c => this.classList._s.has(c),
    };
    ALL.push(this);
  }
  set className(v) { this.attrs.class = v; }
  get className() { return this.attrs.class || ""; }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  set innerHTML(v) { this._html = String(v); this._kids = []; }
  get innerHTML() { return this._html; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { c.parent = this; this._kids.push(c); return c; }
  /* `children` deve comportarsi come una HTMLCollection VERA: indicizzabile e
     iterabile, ma SENZA i metodi di Array. Prima era un array, e ha nascosto un
     bug fatale — `side.children.find(...)` girava qui e moriva nel browser, cioe'
     la pagina intera senza un grafico. Uno shim piu' permissivo del DOM vero non
     e' uno shim, e' un modo di non accorgersene. */
  get children() {
    const arr = this._kids;
    const col = { length: arr.length, item: i => arr[i] ?? null,
                  [Symbol.iterator]: function* () { yield* arr; } };
    arr.forEach((c, i) => { col[i] = c; });
    return col;
  }
  addEventListener() {}
  getBoundingClientRect() { return { width: 360, height: 180, top: 0, left: 0, right: 360, bottom: 180 }; }
  get clientWidth() { return 360; }
  /* the only descendant walk the page does is over ranges' direct children */
  descendants() { return this._kids.flatMap(c => [c, ...c.descendants()]); }
}

const byId = {};
const document = {
  createElement: t => new Node(t),
  createElementNS: (ns, t) => new Node(t, ns),
  getElementById: id => byId[id] || (byId[id] = new Node("div")),
  body: new Node("body"),
  addEventListener() {},
};
for (const id of ["tip", "totals", "ranges", "range-note",
  "panel-carico", "panel-notte", "panel-recupero", "panel-corpo",
  "panel-volume", "panel-incroci", "panel-tavola", "tracks", "sheet", "sheet-in"]) document.getElementById(id);

const sandbox = {
  document, console,
  window: {}, innerWidth: 1200, innerHeight: 900,
  setTimeout: () => 0, clearTimeout() {}, addEventListener() {},
  Math, Date, JSON, Number, String, Array, Object, Map, Set, isFinite, parseFloat, parseInt,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

let ran = true;
try {
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox, { filename: "vita-inline.js", timeout: 60000 });
} catch (e) {
  ran = false;
  fails.push("FAIL lo script della pagina ha sollevato: " + (e && e.stack || e));
}
ok(ran, "lo script inline gira senza eccezioni");

if (ran) {
  const K = sandbox.CRUSCOTTO;
  ok(!!K, "window.CRUSCOTTO esposto");
  const D = K.D;

  /* -------------------------------------------------- 1. tutti i riquadri */
  ok(K.TILES.length === K.MOUNTED.length,
    `ogni riquadro dichiarato e' montato (${K.MOUNTED.length}/${K.TILES.length})`);
  ok(K.MOUNTED.length >= 32, `almeno 32 riquadri (${K.MOUNTED.length})`);

  for (const r of ["2a", "1a", "3m", "sempre"]) {
    let threw = 0, empty = [];
    try { K.setRange(r); } catch (e) { fails.push(`FAIL setRange(${r}): ${e && e.stack || e}`); }
    K.MOUNTED.forEach(([n, t]) => {
      if (n.art.dataset.err) { threw++; fails.push(`FAIL [${r}] ${t.title}: ${n.art.dataset.err}`); }
      if (n.art.dataset.empty) empty.push(t.title);
    });
    ok(threw === 0, `finestra "${r}": nessun renderer solleva eccezioni`);
    if (r === "sempre") {
      ok(empty.length === 0, `finestra "sempre": nessun riquadro vuoto` +
        (empty.length ? ` — vuoti: ${empty.join(", ")}` : ""));
    } else {
      notes.push(`info  finestra "${r}": ${empty.length} riquadri senza dati` +
        (empty.length ? ` (${empty.join(", ")})` : ""));
    }
  }
  K.setRange("sempre");

  /* --------------------------------------------- 2. geometria finita ovunque */
  const bad = [];
  for (const n of ALL) {
    if (!n.ns) continue;                       /* solo i nodi SVG */
    for (const [k, v] of Object.entries(n.attrs)) {
      if (/NaN|Infinity|undefined|null/.test(v)) bad.push(`<${n.tagName} ${k}="${v.slice(0, 60)}">`);
    }
  }
  ok(bad.length === 0, `nessuna coordinata NaN/Infinity negli SVG` +
    (bad.length ? ` — ${bad.length} attributi, es. ${bad[0]}` : ` (${ALL.filter(n => n.ns).length} nodi controllati)`));

  /* i path devono avere un `d` non vuoto e con almeno un segmento */
  const paths = ALL.filter(n => n.tagName === "path");
  const emptyD = paths.filter(p => !p.attrs.d || !/[ML]/.test(p.attrs.d));
  ok(emptyD.length === 0, `ogni <path> ha un tracciato reale (${paths.length} path)`);

  /* --------------------------------- 2b. impaginazione: niente fuori, niente sopra
     Il posto dei controlli che si farebbero a occhio. Senza browser si misurano:
     ogni segno dentro il proprio viewBox, ogni etichetta dell'asse y dentro la sua
     gronda (il modo in cui "50.000" finisce tagliato a meta'), e nessuna coppia di
     etichette sull'asse x che si sovrappone. La larghezza di un glifo IBM Plex Mono
     a font-size 8 e' ~4.85px: **la stessa costante che usa la pagina** (TICKW) per
     dimensionare la gronda, quindi il controllo misura la stessa cosa che il disegno
     assume. Se la' cambia il corpo del testo, va cambiata anche qui, o il check
     smette di vedere le sovrapposizioni invece di segnalarle. */
  const GLYPH = 4.85;
  const outside = [], clipped = [], collide = [];
  for (const [n, t] of K.MOUNTED) {
    const svg = n.box._kids.find(c => c.tagName === "svg");
    if (!svg) continue;
    const [, , W, H] = svg.attrs.viewBox.split(/\s+/).map(Number);
    const kids = svg.descendants();
    for (const c of kids) {
      const num = k => c.attrs[k] === undefined ? null : parseFloat(c.attrs[k]);
      const pts = [];
      if (c.tagName === "circle") pts.push([num("cx"), num("cy")]);
      if (c.tagName === "rect") pts.push([num("x"), num("y")],
        [num("x") + num("width"), num("y") + num("height")]);
      if (c.tagName === "line") pts.push([num("x1"), num("y1")], [num("x2"), num("y2")]);
      for (const [x, y] of pts) {
        if (x < -0.6 || x > W + 0.6 || y < -0.6 || y > H + 0.6) {
          outside.push(`${t.title}: <${c.tagName}> a ${x && x.toFixed(1)},${y && y.toFixed(1)} fuori da ${W}×${H}`);
          break;
        }
      }
      /* etichetta dell'asse y: ancorata a destra, quindi il suo bordo sinistro e'
         x - larghezza. Sotto zero vuol dire tagliata dal bordo della scheda. */
      if (c.tagName === "text" && c.attrs["text-anchor"] === "end") {
        const w = (c.textContent || "").length * GLYPH;
        if (num("x") - w < -0.5) clipped.push(`${t.title}: "${c.textContent}" sborda di ${(w - num("x")).toFixed(1)}px`);
      }
    }
    /* etichette sull'asse x: stessa riga (y a fondo grafico), non si devono toccare */
    const xlab = kids.filter(c => c.tagName === "text" && parseFloat(c.attrs.y) > H - 12)
      .map(c => {
        const w = (c.textContent || "").length * GLYPH, x = parseFloat(c.attrs.x);
        const a = c.attrs["text-anchor"];
        const l = a === "end" ? x - w : a === "middle" ? x - w / 2 : x;
        return { l, r: l + w, s: c.textContent };
      }).sort((a, b) => a.l - b.l);
    for (let i = 1; i < xlab.length; i++) {
      if (xlab[i].l < xlab[i - 1].r + 1) {
        collide.push(`${t.title}: "${xlab[i - 1].s}" e "${xlab[i].s}" si sovrappongono`);
      }
    }
  }
  ok(outside.length === 0, `nessun segno fuori dal proprio viewBox` +
    (outside.length ? ` — ${outside.length}, es. ${outside[0]}` : ""));
  ok(clipped.length === 0, `nessuna etichetta dell'asse y tagliata dalla gronda` +
    (clipped.length ? ` — ${clipped.length}, es. ${clipped[0]}` : ""));
  ok(collide.length === 0, `nessuna sovrapposizione fra etichette dell'asse x` +
    (collide.length ? ` — ${collide.length}, es. ${collide[0]}` : ""));

  /* ------------------------------------------------ 3. totali ricalcolati */
  const N = D.n;
  let secs = 0, dist = 0, gain = 0;
  for (const [, , s, m, up] of D.acts) { secs += s; dist += m; gain += up; }
  const totalsHtml = document.getElementById("totals").innerHTML;
  const it = v => v.toLocaleString("it-IT");
  const expect = [
    [it(D.acts.length), "attività"],
    [it(Math.round(dist / 1000)), "chilometri"],
    [it(Math.round(secs / 3600)), "ore in movimento"],
    [it(D.sleep.filter(v => v !== null).length), "notti misurate"],
  ];
  for (const [v, label] of expect) {
    ok(totalsHtml.includes(`>${v}<`),
      `testata: ${label} = ${v} (ricalcolato dal payload)`);
  }
  ok(Math.round(gain / 1000) > 1000, `dislivello totale plausibile: ${it(Math.round(gain))} m`);

  /* --------------------------------- 4. ripiego tabellare + legende */
  const noTable = K.MOUNTED.filter(([n]) => !n.tbody.innerHTML.includes("<tr")).map(([, t]) => t.title);
  ok(noTable.length === 0, `ogni riquadro ha la tabella di ripiego` +
    (noTable.length ? ` — mancano: ${noTable.join(", ")}` : ""));

  const multi = K.MOUNTED.filter(([, t]) =>
    (t.spec.series && t.spec.series.length > 1) ||
    (t.spec.names && t.spec.names.length > 1) ||
    (t.spec.points && t.spec.points(0, N - 1).length > 1));
  const noLegend = multi.filter(([, t]) => !t.legend).map(([, t]) => t.title);
  ok(noLegend.length === 0, `ogni riquadro multi-serie ha la legenda (${multi.length} riquadri)` +
    (noLegend.length ? ` — mancano: ${noLegend.join(", ")}` : ""));

  /* ------------------------------- 5b. il popup della giornata si apre davvero
     E' l'unica parte della pagina che non si vede finche' non ci si clicca sopra,
     quindi e' anche l'unica che puo' rompersi senza che nessuno se ne accorga. */
  const sheetIn = document.getElementById("sheet-in");
  const openDay = sandbox.openDay;
  ok(typeof openDay === "function", "openDay() esiste");
  if (typeof openDay === "function") {
    // un giorno con dentro tutto: cibo + attivita' + wellness
    // _t (template) e _p (forme ricostruite) non sono giorni
    const withFood = Object.keys(D.days || {}).filter(k => !k.startsWith("_"));
    ok(withFood.length > 0, `il dettaglio giornaliero e' inlineato (${withFood.length} giorni)`);
    let opened = 0, sections = {};
    const d0 = new Date(D.d0 + "T00:00:00");
    const sample = withFood.filter(k => typeof D.days[k] === "object").slice(0, 20)
      .concat(withFood.filter(k => typeof D.days[k] === "string").slice(0, 20));
    for (const k of sample) {
      const i = Math.round((new Date(k + "T00:00:00") - d0) / 86400000);
      try { openDay(i); } catch (e) { fails.push(`FAIL openDay(${k}): ${e && e.stack || e}`); break; }
      const h = sheetIn.innerHTML;
      if (h.includes("Tavola")) sections.tavola = 1;
      if (h.includes("Corpo")) sections.corpo = 1;
      if (h.includes("Allenamento")) sections.allenamento = 1;
      if (h.includes("% del fabbisogno")) sections.micro = 1;
      if (h.length > 400) opened++;
    }
    ok(opened === sample.length, `il popup si riempie su tutti i giorni provati (${opened}/${sample.length}, veri + ricostruiti)`);
    for (const sec of ["corpo", "allenamento", "tavola", "micro"]) {
      ok(!!sections[sec], `il popup mostra la sezione "${sec}" su almeno un giorno`);
    }
    // un giorno senza cibo non deve esplodere
    try { openDay(10); ok(true, "openDay() regge un giorno senza diario alimentare"); }
    catch (e) { fails.push(`FAIL openDay su giorno senza cibo: ${e}`); }
    // i link devono puntare a Intervals/Strava, non essere costruiti a vuoto
    const anyLink = withFood.filter(k => typeof D.days[k] === "object").some(k => {
      const i = Math.round((new Date(k + "T00:00:00") - d0) / 86400000);
      openDay(i); return /intervals\.icu\/activities\/\d/.test(sheetIn.innerHTML);
    });
    ok(anyLink, "almeno un'attivita' nel popup linka a intervals.icu con un id vero");
  }

  /* ------------------------------------------------------ 6. il buco 2022 */
  const d0 = new Date(D.d0 + "T00:00:00");
  const iso = i => new Date(d0.getTime() + i * 86400000).toISOString().slice(0, 10);
  const spans = D.gaps.map(([a, b]) => `${iso(a)}→${iso(b)}`);
  const hole = D.gaps.find(([a, b]) => iso(a) < "2022-01-01" && iso(b) > "2022-12-31");
  ok(!!hole, `il buco che copre tutto il 2022 e' dichiarato` +
    (hole ? ` (${iso(hole[0])}→${iso(hole[1])})` : ` — gaps: ${spans.join(", ")}`));
  ok(D.gaps.length >= 3, `${D.gaps.length} buchi ≥45 giorni dichiarati: ${spans.join(", ")}`);
}

/* -------------------------------------------------- 5. la tavolozza nel CSS */
const PAL = { "--s1": "#3987e5", "--s2": "#d95926", "--s3": "#199e70", "--s4": "#c98500" };
for (const [k, v] of Object.entries(PAL)) {
  ok(new RegExp(k + ":\\s*" + v, "i").test(html), `CSS ${k} = ${v} (slot validato)`);
}
ok(/--paper:#211d16/.test(html), "CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)");

/* --------------------------------------------- 5b. i due valori MISURATI
   Il laboratorio di stile (2026-08-10) ha trovato due difetti nel sistema di
   colore, e li ha trovati misurando, non guardando. Qui si rimisurano a ogni run,
   perche' un colore lo si cambia "solo un pelo" molto piu' facilmente di quanto
   si rifaccia il conto:
     - il testo muted deve stare sopra 4,5:1 sulla scheda (e' testo piccolo, quindi
       vale la soglia normale, non quella del testo grande);
     - l'accento del sito deve stare a ΔE >= 15 da OGNI slot dei grafici, o smette
       di leggersi come accento e comincia a leggersi come una serie.
   Contrasto WCAG 2.x e ΔE in OKLab, le stesse formule del validatore. */
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = c => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
const relLum = h => { const [r, g, b] = hex(h).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [hi, lo] = [relLum(a), relLum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05); };
const oklab = h => {
  const [r, g, b] = hex(h).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
          1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
          0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
};
const dE = (a, b) => { const p = oklab(a), q = oklab(b);
  return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };

const pick = name => (html.match(new RegExp(name + ":\\s*(#[0-9a-f]{6})", "i")) || [])[1];
const paper = pick("--paper"), muted = pick("--muted"), gold = pick("--gold");
if (muted && paper) {
  const r = ratio(muted, paper);
  ok(r >= 4.5, `--muted ${muted} su ${paper}: ${r.toFixed(2)}:1 (minimo 4,5 per il testo piccolo)`);
}
if (gold && paper) {
  const r = ratio(gold, paper);
  ok(r >= 4.5, `--gold ${gold} su ${paper}: ${r.toFixed(2)}:1`);
  let worst = null;
  for (const [k, v] of Object.entries(PAL)) {
    const d = dE(gold, v);
    if (!worst || d < worst[1]) worst = [k, d];
  }
  ok(worst[1] >= 15,
    `--gold ${gold} contro gli slot dei grafici: peggiore ${worst[0]} ΔE ${worst[1].toFixed(1)} ` +
    `(minimo 15, o l'accento si spaccia per una serie)`);
}

/* --------------------------------------------------------------- --verbose
   Cosa dice davvero la pagina, riquadro per riquadro: il numero in testa e la riga
   di piede con finestra, n e correlazioni. Serve a leggere il contenuto senza
   aprire un browser — che da questa macchina non c'e'. */
if (ran && process.argv.includes("--verbose")) {
  const K = sandbox.CRUSCOTTO;
  const strip = s => String(s).replace(/<br>/g, " · ").replace(/<[^>]+>/g, "").trim();
  console.log("\n--- contenuto dei riquadri (finestra \"sempre\") ---");
  for (const [n, t] of K.MOUNTED) {
    const now = strip(n.now.innerHTML);
    console.log(`\n  ${t.title}${now ? "  [" + now + "]" : ""}`);
    console.log(`    ${strip(n.foot.innerHTML)}`);
  }
}

/* --table <titolo>: stampa la tabella dati di un riquadro. Serve a leggere i
   numeri che la pagina mostra senza aprirla. */
if (ran && process.argv.includes("--table")) {
  const want = (process.argv[process.argv.indexOf("--table") + 1] || "").toLowerCase();
  for (const [n, t] of sandbox.CRUSCOTTO.MOUNTED) {
    if (!t.title.toLowerCase().includes(want)) continue;
    console.log("\n--- " + t.title + " ---");
    const txt = n.tbody.innerHTML
      .replace(/<\/tr>/g, "\n").replace(/<[^>]+>/g, " ")
      .split("\n").map(l => l.trim().replace(/\s{2,}/g, "  "))
      .filter(Boolean).slice(0, 14).join("\n");
    console.log(txt);
  }
}

/* ------------------------------------------------------------------ esito */
const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
const body = [...notes, ...fails].join("\n");
console.log(body);
console.log(fails.length ? `\n${fails.length} CONTROLLI FALLITI` : "\ntutto a posto");

const head = fs.existsSync(REPORT) ? "" :
  "# /vita — report cumulativo dei build\n";
fs.appendFileSync(REPORT,
  `${head}\n## ${stamp} — check_vita.cjs\n\n\`\`\`\n${body}\n\`\`\`\n\n` +
  `esito: ${fails.length ? fails.length + " FALLITI" : "tutti passati"} ` +
  `(${notes.length} ok)\n`, "utf8");

process.exit(fails.length ? 1 : 0);
