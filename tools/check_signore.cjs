/* Smoke test per signore-dei-kj.html — senza browser e senza dipendenze.
 *
 * jsdom non si installa da questa rete (il proxy blocca npm), quindi il DOM qui e'
 * uno shim di poche decine di righe, come in check_vita.cjs. Regge per la stessa
 * ragione: la pagina costruisce i nodi uno a uno e se ne tiene il riferimento
 * invece di scrivere innerHTML e rileggerlo — se un giorno torna a farlo, questo
 * check smette di girare, ed e' il segnale giusto.
 *
 * Cosa verifica:
 *   1. lo script inline gira, i sei grafici si disegnano, tutti i mesi montano
 *      la loro lista di attivita';
 *   2. geometria: niente NaN/Infinity negli SVG, niente segno fuori dal viewBox,
 *      nessuna etichetta y tagliata dalla gronda, nessuna coppia di etichette x
 *      sovrapposta (i controlli che si farebbero a occhio, se ci fosse un occhio);
 *   3. le schede attivita': ognuna si apre, ognuna ha un link a intervals.icu con
 *      un id vero, e il link a Strava c'e' esattamente dove c'e' `sid` — mai
 *      inventato dove l'API non lo espone;
 *   4. i totali della testata rifatti dal payload;
 *   5. niente link Strava rotti sopravvissuti nella prosa (ce n'erano tre);
 *   6. il buco d'archivio 2021→2023 e' dichiarato in pagina, e la saga non lo
 *      attraversa; il 2015-2018 e' nominato come non misurato, non come vuoto;
 *   7. ogni mese dell'indice ha davvero la sua ancora, e la pagina settimanale
 *      reindirizza a quella mensile.
 *
 *   node tools/check_signore.cjs [--verbose]
 *
 * L'esito viene appeso a tools/vita_tests.md, dove sta gia' quello degli altri build.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const PAGE = path.join(ROOT, "signore-dei-kj.html");
const ALIAS = path.join(ROOT, "signore-dei-kj-weekly.html");
const REPORT = path.join(__dirname, "vita_tests.md");

const html = fs.readFileSync(PAGE, "utf8");
const alias = fs.readFileSync(ALIAS, "utf8");

const fails = [], notes = [];
const ok = (cond, msg) => { (cond ? notes : fails).push((cond ? "ok   " : "FAIL ") + msg); };

/* ----------------------------------------------------------------- DOM shim */
const ALL = [];
class Node {
  constructor(tag, ns) {
    this.tagName = tag; this.ns = ns || null;
    this.attrs = {}; this.children = []; this.parent = null;
    this.style = {}; this.dataset = {}; this.title = "";
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
  set innerHTML(v) { this._html = String(v); }
  get innerHTML() { return this._html; }
  /* href/target/rel sono proprieta' riflesse sull'attributo: senza questo un
     `a.href = "..."` finirebbe in una proprieta' JS qualsiasi e il check
     cercherebbe un attributo che nel browser esiste e qui no */
  set href(v) { this.attrs.href = String(v); }
  get href() { return this.attrs.href || ""; }
  set target(v) { this.attrs.target = String(v); }
  get target() { return this.attrs.target || ""; }
  set rel(v) { this.attrs.rel = String(v); }
  get rel() { return this.attrs.rel || ""; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  addEventListener() {}
  descendants() { return this.children.flatMap(c => [c, ...c.descendants()]); }
  /* il testo dell'intero sottoalbero: come si legge una scheda senza browser */
  deepText() { return [this._text, ...this.children.map(c => c.deepText())].join(" "); }
}

/* La pagina cerca due sole cose nel DOM statico: i sei contenitori dei grafici
   (per id) e il .actlist dentro <details class="acts" data-month="YYYY-MM">.
   Entrambi si registrano qui a partire dall'HTML vero, cosi' il check fallisce
   se la pagina smette di emetterli invece di montare nel vuoto. */
const byId = {}, byMonth = {};
const MONTHS_IN_HTML = [...html.matchAll(/<details class="acts" data-month="(\d{4}-\d{2})"/g)]
  .map(m => m[1]);
const ANCHORS = new Set([...html.matchAll(/id="m-(\d{4}-\d{2})"/g)].map(m => m[1]));
const CHIPS = [...html.matchAll(/href="#m-(\d{4}-\d{2})"/g)].map(m => m[1]);
for (const m of MONTHS_IN_HTML) byMonth[m] = new Node("div");

const document = {
  createElement: t => new Node(t),
  createElementNS: (ns, t) => new Node(t, ns),
  getElementById: id => byId[id] || (byId[id] = new Node("div")),
  querySelector: sel => {
    const m = /data-month="(\d{4}-\d{2})"/.exec(sel);
    return m ? (byMonth[m[1]] || null) : null;
  },
  querySelectorAll: () => [],
  body: new Node("body"),
  addEventListener() {},
};

const sandbox = {
  document, console,
  window: {}, setTimeout: () => 0, clearTimeout() {}, addEventListener() {},
  Math, Date, JSON, Number, String, Array, Object, Map, Set, isFinite, parseFloat, parseInt,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

/* i due <script> vanno concatenati e girati come un programma solo: `const
   SIGNORE` e' un binding lessicale, e due runInContext separati non se lo
   passerebbero — nel browser invece lo vedono, quindi e' questo il montaggio fedele */
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
ok(scripts.length === 2, `la pagina emette i due <script> attesi (${scripts.length})`);

let ran = true;
try {
  vm.createContext(sandbox);
  vm.runInContext(scripts.join("\n;\n"), sandbox, { filename: "signore-inline.js", timeout: 120000 });
} catch (e) {
  ran = false;
  fails.push("FAIL lo script della pagina ha sollevato: " + (e && (e.stack || e)));
}
ok(ran, "lo script inline gira senza eccezioni");

if (ran) {
  const V = sandbox.SIGNORE_VIEW;
  ok(!!V, "window.SIGNORE_VIEW esposto");
  const D = V.D, g = V.g;

  /* ------------------------------------------------------ 1. montaggio */
  ok(D.acts.length > 1000, `payload: ${D.acts.length} attività inline`);
  ok(D.keys.length >= 40, `payload: ${D.keys.length} campi per attività`);
  ok(D.months.filter(m => m[1] >= 0).length === MONTHS_IN_HTML.length,
    `ogni mese con attività ha il suo <details> in pagina ` +
    `(${MONTHS_IN_HTML.length}/${D.months.filter(m => m[1] >= 0).length} su ${D.months.length} mesi)`);
  ok(V.CHARTS.length === 6, `sei grafici montati (${V.CHARTS.length})`);

  const mountedN = Object.values(V.MOUNTED).reduce((s, l) => s + l.length, 0);
  ok(mountedN === D.acts.length,
    `ogni attività del payload è montata in un mese (${mountedN}/${D.acts.length})`);
  const emptyMonths = MONTHS_IN_HTML.filter(m => !(V.MOUNTED[m] || []).length);
  ok(emptyMonths.length === 0,
    `nessun mese con <details> ma senza attività` +
    (emptyMonths.length ? ` — ${emptyMonths.join(", ")}` : ""));

  /* i mesi vuoti non devono avere un <details>, ma devono avere l'ancora */
  const voidMonths = D.months.filter(m => m[1] < 0).map(m => m[0]);
  ok(voidMonths.every(m => ANCHORS.has(m)),
    `anche i mesi senza attività restano in pagina (${voidMonths.length} vuoti)`);
  const orphan = [...new Set(CHIPS)].filter(m => !ANCHORS.has(m));
  ok(orphan.length === 0, `ogni voce dell'indice ha la sua ancora` +
    (orphan.length ? ` — orfane: ${orphan.join(", ")}` : ` (${new Set(CHIPS).size} mesi)`));

  /* ------------------------------------------ 2. geometria degli SVG */
  const bad = [];
  for (const n of ALL) {
    if (!n.ns) continue;
    for (const [k, v] of Object.entries(n.attrs)) {
      if (/NaN|Infinity|undefined|null/.test(v)) bad.push(`<${n.tagName} ${k}="${v.slice(0, 60)}">`);
    }
  }
  ok(bad.length === 0, `nessuna coordinata NaN/Infinity negli SVG` +
    (bad.length ? ` — ${bad.length}, es. ${bad[0]}` : ` (${ALL.filter(n => n.ns).length} nodi)`));

  const GLYPH = 4.85;
  const outside = [], clipped = [], collide = [];
  for (const [title, svg] of V.CHARTS) {
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
          outside.push(`${title}: <${c.tagName}> a ${x},${y} fuori da ${W}×${H}`); break;
        }
      }
      if (c.tagName === "text" && c.attrs["text-anchor"] === "end") {
        const w = (c.textContent || "").length * GLYPH;
        if (num("x") - w < -0.5) clipped.push(`${title}: "${c.textContent}" sborda di ${(w - num("x")).toFixed(1)}px`);
      }
    }
    const xlab = kids.filter(c => c.tagName === "text" && parseFloat(c.attrs.y) > H - 12)
      .map(c => {
        const w = (c.textContent || "").length * GLYPH, x = parseFloat(c.attrs.x);
        const a = c.attrs["text-anchor"];
        const l = a === "end" ? x - w : a === "middle" ? x - w / 2 : x;
        return { l, r: l + w, s: c.textContent };
      }).sort((a, b) => a.l - b.l);
    for (let i = 1; i < xlab.length; i++) {
      if (xlab[i].l < xlab[i - 1].r + 1) collide.push(`${title}: "${xlab[i - 1].s}" e "${xlab[i].s}" si toccano`);
    }
    const paths = kids.filter(c => c.tagName === "path");
    ok(paths.every(p => p.attrs.d && /[ML]/.test(p.attrs.d)),
      `[${title}] ogni <path> ha un tracciato reale`);
  }
  ok(outside.length === 0, `nessun segno fuori dal proprio viewBox` +
    (outside.length ? ` — ${outside.length}, es. ${outside[0]}` : ""));
  ok(clipped.length === 0, `nessuna etichetta y tagliata dalla gronda` +
    (clipped.length ? ` — ${clipped.length}, es. ${clipped[0]}` : ""));
  ok(collide.length === 0, `nessuna sovrapposizione fra etichette x` +
    (collide.length ? ` — ${collide.length}, es. ${collide[0]}` : ""));

  /* ogni grafico ha la sua tabella di ripiego: il dato non puo' stare solo nel
     disegno, e con un solo colore per grafico la tabella e' anche la legenda */
  const tables = ALL.filter(n => n.tagName === "table" && /<tr/.test(n.innerHTML));
  ok(tables.length >= V.CHARTS.length,
    `una tabella di numeri per grafico (${tables.length}/${V.CHARTS.length})`);
  const shortTable = tables.filter(t => (t.innerHTML.match(/<tr/g) || []).length < D.months.length);
  ok(shortTable.length === 0,
    `ogni tabella riporta tutti i ${D.months.length} mesi` +
    (shortTable.length ? ` — ${shortTable.length} incomplete` : ""));

  /* ---------------------------------------------- 3. le schede attività */
  const K = V.K;
  let opened = 0, noIcu = 0, badStrava = 0, missStrava = 0, thin = 0, ghosts = 0, ghostOk = 0;
  /* tutte, non un campione: aprire una scheda costa nulla e le poche attività
     rotte dell'archivio sono esattamente quelle che un campione salta */
  const sample = [];
  for (const m of Object.keys(V.MOUNTED)) {
    const list = V.MOUNTED[m], base = D.months.find(x => x[0] === m)[1];
    for (let i = 0; i < list.length; i++) sample.push([list[i], D.acts[base + i]]);
  }
  for (const [node, rowActs] of sample) {
    let card;
    try { card = node._fill().children.find(c => c.className === "actbody"); }
    catch (e) { fails.push(`FAIL apertura scheda: ${e && (e.stack || e)}`); break; }
    if (!card) continue;
    opened++;
    const links = card.descendants().filter(n => n.tagName === "a");
    const sid = rowActs ? rowActs[K.sid] : null;
    const id = rowActs ? rowActs[K.id] : null;
    /* le righe cieche (Strava non esposta dall'API) non hanno un id Intervals:
       per loro l'unico link giusto e' quello a Strava, piu' la spiegazione */
    if (!id) {
      ghosts++;
      if (/non ne espone i dati/.test(card.deepText()) &&
          links.some(a => /strava\.com\/activities\/\d{6,}/.test(a.href))) ghostOk++;
      continue;
    }
    if (!links.some(a => /^https:\/\/intervals\.icu\/activities\/i\d+$/.test(a.href))) noIcu++;
    const hasStrava = links.some(a => /strava\.com\/activities\/\d{6,}/.test(a.href));
    if (hasStrava && !sid) badStrava++;
    if (!hasStrava && sid) missStrava++;
    if (Number(card.dataset.stats) < 4) thin++;
  }
  ok(opened > 100, `${opened} schede attività aperte, tutte`);
  ok(ghosts === ghostOk,
    `ogni riga cieca dice perché lo è e linka a Strava (${ghostOk}/${ghosts}; ` +
    `${D.ghost_n} in tutta la saga)`);
  ok(noIcu === 0, `ogni scheda linka a intervals.icu con un id vero` + (noIcu ? ` — ${noIcu} senza` : ""));
  ok(badStrava === 0, `nessun link Strava inventato dove l'API non dà strava_id` +
    (badStrava ? ` — ${badStrava}` : ""));
  ok(missStrava === 0, `il link Strava c'è ovunque l'API lo dia` + (missStrava ? ` — ${missStrava} mancanti` : ""));
  ok(thin === 0, `nessuna scheda con meno di 4 statistiche` + (thin ? ` — ${thin}` : ""));

  /* ------------------------------------------- 4. i totali della testata */
  let kj = 0, dist = 0, up = 0, mov = 0;
  for (const r of D.acts) {
    kj += r[K.kj] || 0; dist += r[K.dist] || 0; up += r[K.up] || 0; mov += r[K.mov] || 0;
  }
  const it = v => Math.round(v).toLocaleString("it-IT");
  for (const [v, what] of [[kj, "kJ"], [Math.round(dist / 1000), "km"], [up, "m D+"]]) {
    ok(html.includes(it(v)), `testata: ${what} = ${it(v)} (ricalcolato dal payload)`);
  }
  ok(html.includes(it(Math.round(mov / 3600))), `testata: ore = ${it(Math.round(mov / 3600))}`);
  const forged = Math.floor(kj / D.ring_kj);
  ok(D.rings.length === forged,
    `anelli forgiati coerenti col contatore: ${D.rings.length} (kJ/${it(D.ring_kj)} = ${forged})`);

  /* --------------------------------- 6. il buco d'archivio, dichiarato */
  const hole = D.hole;
  ok(hole && hole[0] < "2022-01-01" && hole[1] > "2022-12-31",
    `il buco che copre tutto il 2022 è nel payload` + (hole ? ` (${hole[0]}→${hole[1]}, ${hole[2]}g)` : ""));
  ok(html.includes(hole[0]) && html.includes(hole[1]), "il buco è scritto in pagina, non solo nei dati");
  ok(/buco d'archivio/.test(html), "il buco è chiamato buco d'archivio, non pausa");
  ok(D.acts.every(r => r[K.date] >= D.era),
    `nessuna attività della saga precede l'inizio dell'era (${D.era}) — nessun grafico attraversa il vuoto`);
  ok(html.includes(D.load0) && /carico 0/.test(html),
    `il carico è dichiarato reale solo dal ${D.load0}, con il perché`);
  ok(/non allenamento mancato/.test(html),
    "il 2015-2018 è detto non misurato, non vuoto");
}

/* ------------------------------------------------- 5. prosa: link e ancore */
const stravaIds = [...html.matchAll(/strava\.com\/activities\/(\d+)/g)].map(m => m[1]);
const shortIds = [...new Set(stravaIds.filter(s => s.length < 9))];
ok(shortIds.length === 0, `nessun id Strava troncato sopravvissuto nella prosa` +
  (shortIds.length ? ` — ${shortIds.join(", ")}` : ` (${new Set(stravaIds).size} id distinti)`));
ok(!/href="#"/.test(html), "nessun link smontato lasciato a metà");

/* ------------------------------------------------- 7. la pagina settimanale */
ok(/http-equiv="refresh"[^>]*signore-dei-kj\.html/.test(alias),
  "signore-dei-kj-weekly.html reindirizza alla mensile");
ok(/rel="canonical"[^>]*signore-dei-kj\.html/.test(alias), "l'alias dichiara il canonical");
ok(alias.length < 20000, `l'alias è una pagina sottile (${(alias.length / 1024).toFixed(1)} KB)`);

/* -------------------------------------------------- la tavolozza nel CSS */
for (const [k, v] of Object.entries({ "--s1": "#b8860b", "--s2": "#8b2e1f" })) {
  ok(new RegExp(k + ":\\s*" + v, "i").test(html), `CSS ${k} = ${v} (slot validato)`);
}
ok(/--paper:#fffdf6/.test(html), "CSS --paper = #fffdf6 (il fondo su cui è stata validata)");

/* --------------------------------------------------------------- --verbose */
if (ran && process.argv.includes("--verbose")) {
  const V = sandbox.SIGNORE_VIEW, D = V.D, K = V.K;
  console.log("\n--- cosa dice la pagina, mese per mese ---");
  for (const m of D.months) {
    const n = m[1] < 0 ? 0 : m[2] - m[1] + 1;
    console.log(`  ${m[0]}  ${String(n).padStart(3)} att. ${String(m[3]).padStart(6)} kJ ` +
      `${String(m[4]).padStart(5)} km ${String(m[5]).padStart(6)} m ${String(m[6]).padStart(4)} h ` +
      `TL ${String(m[7]).padStart(5)}`);
  }
  console.log("\n--- anelli ---");
  for (const r of D.rings) console.log(`  ${r[0]}  ${r[1]}  ${r[2].toLocaleString("it-IT")} kJ  ${r[3]}`);
}

/* ------------------------------------------------------------------ esito */
const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
const body = [...notes, ...fails].join("\n");
console.log(body);
console.log(fails.length ? `\n${fails.length} CONTROLLI FALLITI` : "\ntutto a posto");

fs.appendFileSync(REPORT,
  `\n## ${stamp} — check_signore.cjs\n\n\`\`\`\n${body}\n\`\`\`\n\n` +
  `esito: ${fails.length ? fails.length + " FALLITI" : "tutti passati"} (${notes.length} ok)\n`, "utf8");

process.exit(fails.length ? 1 : 0);
