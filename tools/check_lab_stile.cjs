/* Smoke test per lab-stile/index.html — senza browser e senza dipendenze.
 *
 * Stessa scelta di check_vita.cjs, per la stessa ragione: jsdom non si installa da
 * questa rete (i check_lab3/4 del top-20 lo pretendono e infatti qui non girano), e
 * il DOM e' uno shim di un centinaio di righe. Regge perche' la pagina costruisce i
 * nodi uno a uno e se ne tiene il riferimento — se un giorno torna a scrivere
 * innerHTML e a rileggerlo con querySelector, questo check smette di girare, ed e'
 * il segnale giusto.
 *
 * Cosa verifica:
 *   1. lo script gira, espone window.LAB, monta tutte le sezioni e tutte le varianti
 *      con i loro 11 gettoni, la stella e la nota;
 *   2. ogni anteprima di direzione contiene davvero i componenti veri di /vita:
 *      i totali, le tre schede-tracker, il riquadro con la legenda (due serie) e la
 *      tabella di ripiego — cioe' che il confronto sia fra le stesse cose;
 *   3. i token della direzione sono applicati come custom property sul contenitore
 *      (--paper, --ink, i quattro slot della tavolozza): se non lo fossero,
 *      l'anteprima mostrerebbe la direzione sbagliata senza dirlo;
 *   4. nessuna coordinata NaN/Infinity negli SVG, nessun segno fuori dal viewBox,
 *      nessuna etichetta dell'asse y tagliata dalla gronda (stessa costante di
 *      4,85px per glifo che usa il disegno);
 *   5. il contrasto scritto in pagina viene RICALCOLATO qui da capo, con una seconda
 *      implementazione di WCAG e di ΔE OKLab, e confrontato riga per riga: una
 *      lettura di contrasto che si autocertifica non vale niente;
 *   6. i verdetti attesi: la tavolozza dei grafici passa 3:1 sul fondo di TUTTE le
 *      direzioni, D1 ha il grigio dei piedini sotto 4,5:1, le altre tre no;
 *   7. il voto funziona: gettone, stella, contatore, e il blob da incollare in chat.
 *
 *   node tools/check_lab_stile.cjs [--verbose]
 *
 * L'esito viene appeso a tools/lab_stile_tests.md.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const PAGE = path.join(ROOT, "lab-stile", "index.html");
const REPORT = path.join(__dirname, "lab_stile_tests.md");

const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const fails = [], notes = [];
const ok = (cond, msg) => { (cond ? notes : fails).push((cond ? "ok   " : "FAIL ") + msg); };

/* ------------------------------------------------------------------ DOM shim */
const ALL = [];
class Node {
  constructor(tag, ns) {
    this.tagName = String(tag).toUpperCase(); this.tag = tag; this.ns = ns || null;
    this.attrs = {}; this.children = []; this.parent = null;
    this.dataset = {}; this._text = ""; this._html = ""; this._ev = {};
    this.value = "";
    this._css = {};
    this.style = {
      setProperty: (k, v) => { this._css[k] = String(v); },
      removeProperty: (k) => { delete this._css[k]; },
    };
    this.classList = {
      _s: new Set(),
      add: (...c) => c.forEach(x => this.classList._s.add(x)),
      remove: (...c) => c.forEach(x => this.classList._s.delete(x)),
      contains: c => this.classList._s.has(c),
    };
    ALL.push(this);
  }
  set className(v) { this.attrs.class = String(v); }
  get className() { return this.attrs.class || ""; }
  set id(v) { this.attrs.id = String(v); }
  get id() { return this.attrs.id || ""; }
  set textContent(v) { this._text = String(v); }
  get textContent() {
    if (this.children.length) return this._text + this.children.map(c => c.textContent).join("");
    return this._text;
  }
  set innerHTML(v) { this._html = String(v); this.children = []; }
  get innerHTML() { return this._html; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.attrs.class = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  addEventListener(t, f) { (this._ev[t] = this._ev[t] || []).push(f); }
  click() { fire(this, "click"); }
  select() {}
  getBoundingClientRect() { return { width: 430, height: 220, top: 0, left: 0, right: 430, bottom: 220 }; }
  get clientWidth() { return 430; }
  get parentNode() { return this.parent; }
  walk() { return this.children.flatMap(c => [c, ...c.walk()]); }
}
const fire = (node, type, ev) => (node._ev[type] || []).forEach(f => f.call(node, ev || {}));

const byId = {};
const documentElement = new Node("html");
const document = {
  documentElement,
  createElement: t => new Node(t),
  createElementNS: (ns, t) => new Node(t, ns),
  getElementById: id => byId[id] || (byId[id] = new Node("div")),
  body: new Node("body"),
  activeElement: { tagName: "BODY" },
  addEventListener() {},
};
for (const id of ["main", "tnav", "prog", "copy", "wipe", "rand", "outbox", "foot"]) document.getElementById(id);

const sandbox = {
  document, console,
  window: {}, innerWidth: 1280, innerHeight: 900,
  setTimeout: () => 0, clearTimeout() {}, addEventListener() {},
  Math, Date, JSON, Number, String, Array, Object, Map, Set, RegExp, Error,
  isFinite, parseFloat, parseInt,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

let ran = true;
try {
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox, { filename: "lab-stile-inline.js", timeout: 60000 });
} catch (e) {
  ran = false;
  fails.push("FAIL lo script della pagina ha sollevato: " + (e && e.stack || e));
}
ok(ran, "lo script inline gira senza eccezioni");

/* ------------------------------------------------- colore, seconda implementazione
   Riscritto qui apposta: la pagina calcola i suoi rapporti e questo check li
   ricalcola per conto proprio. Se le due non coincidono, una delle due sbaglia. */
const srgb = h => [1, 3, 5].map((_, i) => parseInt(String(h).replace("#", "").substr(i * 2, 2), 16) / 255);
const toLin = c => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const L = h => { const [r, g, b] = srgb(h).map(toLin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const cr = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
function oklab(h) {
  const [r, g, b] = srgb(h).map(toLin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
          1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
          0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
}
const dE = (a, b) => { const p = oklab(a), q = oklab(b);
  return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };

if (ran) {
  const K = sandbox.LAB;
  ok(!!K, "window.LAB esposto");
  const cls = (n, c) => (n.attrs.class || "").split(/\s+/).includes(c) || n.classList.contains(c);

  /* ------------------------------------------------- 1. sezioni e varianti */
  ok(K.FAMS.length === 5, `5 sezioni montate (${K.FAMS.length})`);
  ok(K.ITEMS.length === 22, `22 varianti votabili (${K.ITEMS.length})`);
  ok(K.DIRS.length === 4, `4 direzioni complete (${K.DIRS.length})`);
  const badVote = K.ITEMS.filter(v => v.chips.length !== 11 || !v.star || !v.note).map(v => v.id);
  ok(badVote.length === 0, "ogni variante ha 11 gettoni, la stella e la nota" +
    (badVote.length ? " — rotte: " + badVote.join(", ") : ""));
  const ids = K.ITEMS.map(v => v.id);
  ok(new Set(ids).size === ids.length, "nessun identificativo di variante duplicato");

  /* Ogni variante deve avere il suo campione ATTACCATO alla propria scheda: un
     contenitore costruito e mai appeso disegna benissimo in memoria e lascia una
     sezione vuota nel browser — e' successo, ed e' il motivo per cui questo
     controllo cammina l'albero invece di fidarsi del numero di SVG creati. */
  const orfane = K.ITEMS.filter(v => {
    const kids = v.card.walk();
    return !kids.some(n => n.tag === "svg") ||
           !kids.some(n => cls(n, "demo") || cls(n, "spec"));
  }).map(v => v.id);
  ok(orfane.length === 0, "ogni variante ha il campione appeso alla propria scheda" +
    (orfane.length ? " — staccate: " + orfane.join(", ") : ""));
  const senzaToken = K.ITEMS.filter(v =>
    !v.card.walk().some(n => (cls(n, "demo") || cls(n, "spec")) && n._css["--paper"])).map(v => v.id);
  ok(senzaToken.length === 0, "ogni campione ha i token della sua variante" +
    (senzaToken.length ? " — senza: " + senzaToken.join(", ") : ""));

  /* --------------------------- 2. i componenti veri dentro ogni direzione */
  for (const fam of K.FAMS) {
    for (const v of fam.items) {
      if (fam.key !== "dir") continue;
      const kids = v.card.walk();
      const totals = kids.filter(n => cls(n, "total")).length;
      const tracks = kids.filter(n => cls(n, "track")).length;
      const plots = kids.filter(n => n.tag === "svg").length;
      const legend = kids.filter(n => cls(n, "t-legend")).length;
      const rows = kids.filter(n => cls(n, "fallback"))
        .flatMap(n => n.children.filter(c => c.tag === "tbody"))
        .flatMap(n => n.children).length;
      const foot = kids.filter(n => cls(n, "t-foot")).length;
      ok(totals === 5, `${v.id}: 5 numeri in testata (${totals})`);
      ok(tracks === 3, `${v.id}: le 3 schede-tracker (${tracks})`);
      ok(plots >= 1, `${v.id}: almeno un grafico SVG (${plots})`);
      ok(legend === 1, `${v.id}: la legenda c'e' (due serie sul riquadro)`);
      ok(rows >= 6, `${v.id}: tabella di ripiego con ${rows} righe`);
      ok(foot === 1, `${v.id}: il piede del riquadro con finestra e n`);
    }
  }

  /* ------------------------------- 3. i token applicati sul contenitore */
  for (const d of K.DIRS) {
    const item = K.ITEMS.find(v => v.id === d.id);
    const demo = item.card.walk().find(n => cls(n, "demo"));
    ok(!!demo, `${d.id}: il contenitore .demo esiste`);
    if (!demo) continue;
    const miss = ["bg", "paper", "ink", "muted", "gold", "s1", "s2", "s3", "s4"]
      .filter(k => demo._css["--" + k] !== d.tok[k]);
    ok(miss.length === 0, `${d.id}: token applicati sul contenitore` +
      (miss.length ? " — sbagliati/mancanti: " + miss.join(", ") : ` (--paper ${demo._css["--paper"]})`));
  }

  /* ---------------------------------------- 4. geometria degli SVG */
  const bad = [];
  for (const n of ALL) {
    if (!n.ns) continue;
    for (const [k, val] of Object.entries(n.attrs)) {
      if (/NaN|Infinity|undefined|null/.test(val)) bad.push(`<${n.tag} ${k}="${String(val).slice(0, 50)}">`);
    }
  }
  const svgs = ALL.filter(n => n.tag === "svg");
  ok(bad.length === 0, `nessuna coordinata NaN/Infinity in ${ALL.filter(n => n.ns).length} nodi SVG` +
    (bad.length ? ` — ${bad.length}, es. ${bad[0]}` : ""));
  ok(svgs.length >= 22, `almeno un grafico per variante (${svgs.length} SVG)`);

  const GLYPH = 4.85;
  const outside = [], clipped = [], emptyD = [];
  for (const s of svgs) {
    const [, , W, H] = s.attrs.viewBox.split(/\s+/).map(Number);
    for (const c of s.walk()) {
      const num = k => (c.attrs[k] === undefined ? null : parseFloat(c.attrs[k]));
      const pts = [];
      if (c.tag === "circle") pts.push([num("cx"), num("cy")]);
      if (c.tag === "line") pts.push([num("x1"), num("y1")], [num("x2"), num("y2")]);
      if (c.tag === "path") {
        const nums = String(c.attrs.d || "").match(/-?\d+(\.\d+)?/g) || [];
        for (let i = 0; i + 1 < nums.length; i += 2) pts.push([+nums[i], +nums[i + 1]]);
        if (!/[ML]/.test(c.attrs.d || "")) emptyD.push(String(c.attrs.d));
      }
      for (const [x, y] of pts) {
        if (x < -0.6 || x > W + 0.6 || y < -0.6 || y > H + 0.6) {
          outside.push(`<${c.tag}> a ${x},${y} fuori da ${W}×${H}`); break;
        }
      }
      if (c.tag === "text" && c.attrs["text-anchor"] === "end") {
        const w = (c.textContent || "").length * GLYPH;
        if (num("x") - w < -0.5) clipped.push(`"${c.textContent}" sborda di ${(w - num("x")).toFixed(1)}px`);
      }
    }
  }
  ok(emptyD.length === 0, "ogni <path> ha un tracciato reale");
  ok(outside.length === 0, "nessun segno fuori dal proprio viewBox" +
    (outside.length ? ` — ${outside.length}, es. ${outside[0]}` : ""));
  ok(clipped.length === 0, "nessuna etichetta dell'asse y tagliata dalla gronda" +
    (clipped.length ? ` — ${clipped.length}, es. ${clipped[0]}` : ""));

  /* ------------------- 5. il contrasto scritto in pagina, ricalcolato qui */
  let worstDelta = 0, checked = 0;
  for (const r of K.READOUTS) {
    for (const row of r.rows) {
      const mine = cr(row.fg, r.paper);
      worstDelta = Math.max(worstDelta, Math.abs(mine - row.ratio));
      checked++;
      if (row.pass !== (mine >= row.need - 0.005))
        fails.push(`FAIL ${r.id} · ${row.role}: la pagina dice ${row.pass ? "passa" : "non passa"}, ` +
          `il ricalcolo dice ${mine.toFixed(2)}:1 contro ${row.need}`);
    }
  }
  ok(worstDelta < 1e-9, `${checked} rapporti di contrasto ricalcolati coincidono ` +
    `(scarto massimo ${worstDelta.toExponential(1)})`);
  ok(Math.abs(K.contrast("#ece3cd", "#211d16") - cr("#ece3cd", "#211d16")) < 1e-9,
    "la formula di contrasto della pagina e quella del check danno lo stesso numero");
  ok(Math.abs(K.deltaE("#c89a3f", "#c98500") - dE("#c89a3f", "#c98500")) < 1e-9,
    "idem per ΔE OKLab");

  /* --------------------------------------------- 6. i verdetti attesi */
  const PAL = K.PAL;
  for (const d of K.DIRS) {
    const under = ["s1", "s2", "s3", "s4"].filter(k => cr(PAL[k], d.tok.paper) < 3);
    ok(under.length === 0, `${d.id} (${d.name}): la tavolozza validata tiene 3:1 sul fondo ` +
      `${d.tok.paper} — ` + ["s1", "s2", "s3", "s4"].map(k => cr(PAL[k], d.tok.paper).toFixed(2)).join(" / ") +
      (under.length ? ` — sotto: ${under.join(", ")}` : ""));
  }
  const rd = id => K.READOUTS.find(r => r.id === id);
  ok(rd("D1") && rd("D1").fails === 1,
    `D1 dichiara esattamente 1 ruolo sotto soglia (il minuto, ${cr("#8a7d62", "#211d16").toFixed(2)}:1)` +
    (rd("D1") ? ` — ne dichiara ${rd("D1").fails}` : ""));
  for (const id of ["D2", "D3", "D4"]) {
    ok(rd(id) && rd(id).fails === 0, `${id}: nessun ruolo sotto soglia`);
  }
  /* l'accento sta sulla stessa scheda della serie gialla: A1 e' quello di oggi e
     non la distingue, A4 e' l'unico candidato che ci riesce */
  ok(dE("#c89a3f", "#c98500") < 15,
    `l'oro di oggi resta a ΔE ${dE("#c89a3f", "#c98500").toFixed(1)} dalla serie 4 (sotto 15)`);
  ok(["#3987e5", "#d95926", "#199e70", "#c98500"].every(s => dE("#e2c98f", s) >= 15),
    `A4 #e2c98f supera 15 da tutte e quattro le serie ` +
    `(min ${Math.min(...["#3987e5", "#d95926", "#199e70", "#c98500"].map(s => dE("#e2c98f", s))).toFixed(1)})`);

  /* -------------------------------------------------------- 7. il voto */
  const v0 = K.ITEMS[0];
  fire(v0.chips[7], "click");
  ok(v0.chips[7].classList.contains("sel"), "il gettone si seleziona");
  ok(K.votes()[v0.id] && K.votes()[v0.id].n === 7, "il voto finisce nel modello");
  fire(v0.star, "click");
  ok(v0.card.classList.contains("star"), "la stella marca la scheda");
  const prog = document.getElementById("prog").textContent.replace(/\s+/g, " ");
  ok(/^1 \/ 22 votate$/.test(prog), `il contatore dice «${prog}»`);
  fire(document.getElementById("copy"), "click");
  const blob = document.getElementById("outbox").value;
  ok(/VOTI LAB-STILE/.test(blob), "il blob ha l'intestazione");
  ok(new RegExp("★ " + v0.id).test(blob), "il blob riporta la preferita");
  ok(/CONTRASTO MISURATO IN PAGINA/.test(blob), "il blob porta con se' le letture di contrasto");
  ok(/D1 su #211d16: 1 ruoli sotto soglia/.test(blob), "e dice quale direzione ha un ruolo sotto soglia");

  if (process.argv.includes("--verbose")) {
    console.log("\n--- letture di contrasto, direzione per direzione ---");
    for (const r of K.READOUTS.filter(x => x.id.charAt(0) === "D")) {
      console.log(`\n  ${r.id} — scheda ${r.paper}`);
      for (const row of r.rows) console.log(`    ${row.pass ? "✓" : "✗"} ${row.role.padEnd(34)} ` +
        `${row.ratio.toFixed(2)}:1 (serve ${row.need})`);
    }
  }
}

/* ------------------------------------ la tavolozza e i caratteri nel sorgente */
const PALCSS = { s1: "#3987e5", s2: "#d95926", s3: "#199e70", s4: "#c98500" };
for (const [k, v] of Object.entries(PALCSS)) {
  ok(new RegExp(k + ':\\s*"' + v + '"', "i").test(html), `${k} = ${v} (slot validato, invariato)`);
}
for (const f of ["Cinzel", "EB\\+Garamond", "IBM\\+Plex\\+Mono", "Fraunces", "Newsreader",
                 "Inter", "Instrument\\+Serif", "JetBrains\\+Mono"]) {
  ok(new RegExp("family=" + f).test(html), `il carattere ${f.replace(/\\\+/g, " ")} e' nel link di Google Fonts`);
}
ok(/prefers-reduced-motion/.test(html), "il movimento ridotto e' rispettato");
ok(/prefers-color-scheme/.test(html), "la cornice segue il tema di sistema");

/* --------------------------------------------------------------------- esito */
const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
const body = [...notes, ...fails].join("\n");
console.log(body);
console.log(fails.length ? `\n${fails.length} CONTROLLI FALLITI` : "\ntutto a posto");

const head = fs.existsSync(REPORT) ? "" : "# /lab-stile — report cumulativo\n";
fs.appendFileSync(REPORT,
  `${head}\n## ${stamp} — check_lab_stile.cjs\n\n\`\`\`\n${body}\n\`\`\`\n\n` +
  `esito: ${fails.length ? fails.length + " FALLITI" : "tutti passati"} (${notes.length} ok)\n`, "utf8");

process.exit(fails.length ? 1 : 0);
