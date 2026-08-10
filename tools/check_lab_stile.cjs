/* Smoke test per lab-stile/index.html — la griglia 3×3. Senza browser, senza
 * dipendenze.
 *
 * Stessa scelta di check_vita.cjs, per la stessa ragione: jsdom non si installa da
 * questa rete (il proxy blocca npm; i check_lab3/lab4 del top-20 lo pretendono e
 * infatti qui non girano), e il DOM e' uno shim di un centinaio di righe. Regge
 * perche' la pagina costruisce i nodi uno a uno e se ne tiene il riferimento — se
 * un giorno torna a scrivere innerHTML e a rileggerlo con querySelector, questo
 * check smette di girare, ed e' il segnale giusto.
 *
 * Cosa verifica:
 *   1. la griglia ha NOVE caselle, ognuna con la sua istantanea appesa, gli 11
 *      gettoni e la stella; nessun identificativo duplicato;
 *   2. l'istantanea e' il riquadro VERO di /vita: le classi .tile/.t-side/.t-title/
 *      .t-now/.t-cap/.t-legend/.t-foot, i testi presi parola per parola dalla
 *      specifica in build_vita.py, e un <svg> con due spezzate;
 *   3. i DATI sono veri: le 40 coppie CTL/ATL della pagina vengono ricercate nel
 *      payload di vita/index.html alla data che dichiarano, e devono coincidere;
 *      poi le coordinate del tracciato vengono INVERTITE con l'aritmetica degli
 *      assi e ricondotte ai valori di partenza. Una spezzata finta non sopravvive
 *      a questo giro;
 *   4. nessuna coordinata NaN/Infinity, nessun segno fuori dal viewBox, nessuna
 *      etichetta d'asse tagliata dalla gronda (stessa costante TICKW di /vita);
 *   5. ogni casella DICHIARA le sue differenze: cinque righe fisse, e ogni token
 *      che differisce da BASE dev'esserci scritto col suo valore — e nessun token
 *      identico a BASE dev'essere spacciato per una differenza;
 *   6. i token dichiarati sono davvero applicati come custom property sul
 *      contenitore dell'istantanea (altrimenti la casella mostrerebbe un'altra
 *      variante senza dirlo);
 *   7. ogni numero STAMPATO nella casella viene ricalcolato qui con una seconda
 *      implementazione di WCAG e di ΔE OKLab e ricercato, formattato, dentro il
 *      testo della casella. Una lettura di contrasto che si autocertifica non vale
 *      niente;
 *   8. le due misure gia' in produzione non sono regredite: --muted #9a8d70 sopra
 *      4,5:1 e --gold #e2c98f sopra ΔE 15 da tutti e quattro gli slot; i quattro
 *      slot invariati; e le due caselle che sfondano una soglia (V3, V9) lo
 *      dichiarano in pagina col numero;
 *   9. il voto funziona: gettone, stella, contatore, blob da incollare in chat.
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
const VITA = path.join(ROOT, "vita", "index.html");
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
      contains: c => this.classList._s.has(c) ||
        (this.attrs.class || "").split(/\s+/).includes(c),
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
  getBoundingClientRect() { return { width: 372, height: 214, top: 0, left: 0, right: 372, bottom: 214 }; }
  get clientWidth() { return 372; }
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
for (const id of ["main", "prog", "copy", "wipe", "outbox", "foot"]) document.getElementById(id);

const sandbox = {
  document, console,
  window: {}, innerWidth: 1220, innerHeight: 900,
  setTimeout: () => 0, clearTimeout() {}, addEventListener() {},
  Math, Date, JSON, Number, String, Array, Object, Map, Set, RegExp, Error, Intl,
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
const f2 = n => n.toFixed(2).replace(".", ",");
const f1 = n => n.toFixed(1).replace(".", ",");

/* --------------- aritmetica degli assi, anch'essa riscritta invece che importata */
const TICKW = 6.05;
function nice(lo, hi) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const span = hi - lo, mag = Math.pow(10, Math.floor(Math.log10(span / 3)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).filter(s => span / s <= 5)[0] || mag * 10;
  return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step };
}
function tickLabels(yd) {
  const out = [];
  for (let v = yd.lo; v <= yd.hi + 1e-9; v += yd.step)
    out.push(v.toLocaleString("it-IT", { minimumFractionDigits: yd.step < 1 ? 1 : 0,
      maximumFractionDigits: yd.step < 1 ? 1 : 0 }));
  return out;
}
const padFor = labs => Math.min(74, Math.max(28, Math.ceil(Math.max(...labs.map(s => s.length)) * TICKW) + 10));

if (ran) {
  const K = sandbox.LAB;
  ok(!!K, "window.LAB esposto");
  const cls = (n, c) => (n.attrs.class || "").split(/\s+/).includes(c);
  const SLOTS = ["s1", "s2", "s3", "s4"];
  const BASE = K.BASE, PAL = K.PAL, CELLS = K.CELLS, DATA = K.data;

  /* ------------------------------------------------------ 1. le nove caselle */
  ok(CELLS.length === 9, `nove caselle nella griglia (${CELLS.length})`);
  const ids = CELLS.map(v => v.id);
  ok(new Set(ids).size === 9, "nessun identificativo di casella duplicato — " + ids.join(" "));
  const badVote = CELLS.filter(v => v.chips.length !== 11 || !v.star).map(v => v.id);
  ok(badVote.length === 0, "ogni casella ha 11 gettoni e la stella" +
    (badVote.length ? " — rotte: " + badVote.join(", ") : ""));

  /* La casella deve avere il campione ATTACCATO: un contenitore costruito e mai
     appeso disegna benissimo in memoria e lascia un buco nel browser — e' gia'
     successo, ed e' il motivo per cui questo controllo cammina l'albero. */
  const orfane = CELLS.filter(v => {
    const kids = v.card.walk();
    return !kids.some(n => n.tag === "svg") || !kids.some(n => cls(n, "demo"));
  }).map(v => v.id);
  ok(orfane.length === 0, "ogni casella ha l'istantanea appesa alla propria scheda" +
    (orfane.length ? " — staccate: " + orfane.join(", ") : ""));

  /* ------------------- 2. l'istantanea e' il riquadro vero, non un mockup */
  const PARTI = ["tile", "t-side", "t-head", "t-title", "t-now", "t-cap", "t-legend", "t-foot"];
  for (const v of CELLS) {
    const kids = v.card.walk();
    const miss = PARTI.filter(c => !kids.some(n => cls(n, c)));
    ok(miss.length === 0, `${v.id}: la marcatura vera del riquadro di /vita` +
      (miss.length ? " — manca ." + miss.join(", .") : ` (${PARTI.length} classi)`));
    const title = kids.find(n => cls(n, "t-title"));
    const cap = kids.find(n => cls(n, "t-cap"));
    const foot = kids.find(n => cls(n, "t-foot"));
    const leg = kids.filter(n => cls(n, "t-legend"));
    ok(title && title.textContent === DATA.TILE.title, `${v.id}: titolo «${title && title.textContent}»`);
    ok(cap && cap.textContent === DATA.TILE.cap, `${v.id}: didascalia «${cap && cap.textContent}»`);
    ok(foot && foot.textContent === DATA.TILE.foot, `${v.id}: piede «${foot && foot.textContent}»`);
    ok(leg.length === 1 && /Fitness \(CTL\)/.test(leg[0].textContent) &&
       /Fatica \(ATL\)/.test(leg[0].textContent), `${v.id}: la legenda nomina le due serie`);
  }
  /* i testi devono venire dalla specifica vera, quindi devono esistere anche li' */
  const bv = fs.readFileSync(path.join(ROOT, "tools", "build_vita.py"), "utf8");
  for (const s of [DATA.TILE.title, DATA.TILE.cap, DATA.TILE.foot, DATA.TILE.nowUnit]) {
    ok(bv.indexOf(s) >= 0, `«${s}» e' testo vero di build_vita.py, non riscritto qui`);
  }

  /* ------------------------------------------------------- 3. i dati sono veri */
  ok(DATA.CTL.length === 40 && DATA.ATL.length === 40 && DATA.DATES.length === 40,
    `40 punti di CTL, ATL e date (${DATA.CTL.length}/${DATA.ATL.length}/${DATA.DATES.length})`);
  let vitaChecked = 0;
  if (fs.existsSync(VITA)) {
    const vh = fs.readFileSync(VITA, "utf8");
    const i0 = vh.indexOf("const D = ");
    const D = JSON.parse(vh.slice(i0 + 10, vh.indexOf("\n", i0)).replace(/;\s*$/, ""));
    const day0 = Date.UTC(...D.d0.split("-").map((x, i) => +x - (i === 1 ? 1 : 0)));
    const bad = [];
    DATA.DATES.forEach((iso, k) => {
      const idx = Math.round((Date.UTC(...iso.split("-").map((x, i) => +x - (i === 1 ? 1 : 0))) - day0) / 86400000);
      const c = D.ctl[idx], a = D.atl[idx];
      if (c === undefined || Math.abs(c - DATA.CTL[k]) > 0.05) bad.push(`${iso} CTL ${DATA.CTL[k]}≠${c}`);
      else if (a === undefined || Math.abs(a - DATA.ATL[k]) > 0.05) bad.push(`${iso} ATL ${DATA.ATL[k]}≠${a}`);
      else vitaChecked++;
    });
    ok(bad.length === 0, `le 40 coppie CTL/ATL coincidono col payload di /vita alla data dichiarata ` +
      `(${vitaChecked}/40)` + (bad.length ? " — divergono: " + bad.slice(0, 3).join("; ") : ""));
  } else {
    fails.push("FAIL vita/index.html assente: i dati dell'istantanea non sono verificabili");
  }

  /* le coordinate del tracciato, invertite fino ai valori di partenza */
  const yd = nice(Math.min(0, ...DATA.CTL, ...DATA.ATL), Math.max(...DATA.CTL, ...DATA.ATL));
  const labs = tickLabels(yd);
  const P = { l: padFor(labs), r: 8, t: 9, b: 20 };
  let recovered = 0, worstV = 0;
  for (const v of CELLS) {
    const svg = v.card.walk().find(n => n.tag === "svg");
    const [, , W, H] = svg.attrs.viewBox.split(/\s+/).map(Number);
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const invY = y => yd.lo + (P.t + ih - y) / ih * (yd.hi - yd.lo);
    const invX = x => (x - P.l) / iw * (DATA.DAY[39] - DATA.DAY[0]) + DATA.DAY[0];
    for (const [stroke, arr] of [["var(--s1)", DATA.CTL], ["var(--s2)", DATA.ATL]]) {
      const p = svg.children.find(n => n.tag === "path" && n.attrs.stroke === stroke && n.attrs.fill === "none");
      if (!p) { fails.push(`FAIL ${v.id}: manca la spezzata ${stroke}`); continue; }
      const nums = p.attrs.d.match(/-?\d+(\.\d+)?/g).map(Number);
      if (nums.length !== 80) { fails.push(`FAIL ${v.id}: la spezzata ha ${nums.length / 2} punti, non 40`); continue; }
      for (let i = 0; i < 40; i++) {
        worstV = Math.max(worstV, Math.abs(invY(nums[i * 2 + 1]) - arr[i]));
        worstV = Math.max(worstV, Math.abs(invX(nums[i * 2]) - DATA.DAY[i]) / 40);
        recovered++;
      }
    }
  }
  ok(worstV < 0.35, `${recovered} punti riletti dalle coordinate degli SVG tornano ai valori veri ` +
    `(scarto massimo ${worstV.toFixed(3)}, il tracciato arrotonda a 0,1px)`);

  /* -------------------------- 4. geometria: niente NaN, niente fuori quadro */
  const badAttr = [];
  for (const n of ALL) {
    if (!n.ns) continue;
    for (const [k, val] of Object.entries(n.attrs))
      if (/NaN|Infinity|undefined|null/.test(val)) badAttr.push(`<${n.tag} ${k}="${String(val).slice(0, 50)}">`);
  }
  const svgs = ALL.filter(n => n.tag === "svg");
  ok(badAttr.length === 0, `nessuna coordinata NaN/Infinity in ${ALL.filter(n => n.ns).length} nodi SVG` +
    (badAttr.length ? ` — ${badAttr.length}, es. ${badAttr[0]}` : ""));
  ok(svgs.length === 9, `un grafico per casella (${svgs.length} SVG)`);
  const outside = [], clipped = [], emptyD = [];
  for (const s of svgs) {
    const [, , W, H] = s.attrs.viewBox.split(/\s+/).map(Number);
    for (const c of s.walk()) {
      const num = k => (c.attrs[k] === undefined ? null : parseFloat(c.attrs[k]));
      const pts = [];
      if (c.tag === "line") pts.push([num("x1"), num("y1")], [num("x2"), num("y2")]);
      if (c.tag === "path") {
        const nums = String(c.attrs.d || "").match(/-?\d+(\.\d+)?/g) || [];
        for (let i = 0; i + 1 < nums.length; i += 2) pts.push([+nums[i], +nums[i + 1]]);
        if (!/[ML]/.test(c.attrs.d || "")) emptyD.push(String(c.attrs.d));
      }
      for (const [x, y] of pts)
        if (x < -0.6 || x > W + 0.6 || y < -0.6 || y > H + 0.6) {
          outside.push(`<${c.tag}> a ${x},${y} fuori da ${W}×${H}`); break;
        }
      if (c.tag === "text" && c.attrs["text-anchor"] === "end") {
        const w = (c.textContent || "").length * TICKW;
        if (num("x") - w < -0.5) clipped.push(`"${c.textContent}" sborda di ${(w - num("x")).toFixed(1)}px`);
      }
    }
  }
  ok(emptyD.length === 0, "ogni <path> ha un tracciato reale");
  ok(outside.length === 0, "nessun segno fuori dal proprio viewBox" +
    (outside.length ? ` — ${outside.length}, es. ${outside[0]}` : ""));
  ok(clipped.length === 0, "nessuna etichetta dell'asse y tagliata dalla gronda" +
    (clipped.length ? ` — ${clipped.length}, es. ${clipped[0]}` : ""));

  /* --------------------- 5. ogni casella DICHIARA le sue differenze esatte */
  const COLTOK = ["bg", "paper", "paper-2", "ink", "ink-soft", "muted", "gold", "rule"];
  /* la riga "forma" e' compatta per stare in una riga sola: pad 6/10/5, corpo
     17px/1,45. Il check ricostruisce la stessa forma invece di fidarsi. */
  const FORMTOK = {
    rad: t => "raggio " + t.rad,
    pad: t => "pad " + t.pad.replace(/px/g, "").split(/\s+/).join("/"),
    fs:  t => "corpo " + t.fs + "/" + t.lh.replace(".", ","),
    lh:  t => "corpo " + t.fs + "/" + t.lh.replace(".", ","),
    tw:  t => "colonna " + t.tw,
  };
  for (const v of CELLS) {
    ok(v.deltaText.length === 5, `${v.id}: cinque righe di differenze (${v.deltaText.length})`);
    const txt = v.deltaText.join(" | ");
    const changed = COLTOK.filter(k => v.tok[k] !== BASE[k]);
    const unstated = changed.filter(k => txt.indexOf("--" + k + " " + v.tok[k]) < 0);
    ok(unstated.length === 0, `${v.id}: dichiara i ${changed.length} token di colore che cambia` +
      (unstated.length ? " — taciuti: " + unstated.join(", ") : (changed.length ? " (" +
        changed.map(k => "--" + k + " " + v.tok[k]).join(" ") + ")" : " (nessuno)")));
    /* e nessuna differenza inventata: un token identico a BASE non va elencato */
    const bugie = COLTOK.filter(k => v.tok[k] === BASE[k] && txt.indexOf("--" + k + " ") >= 0);
    ok(bugie.length === 0, `${v.id}: nessuna differenza dichiarata che non esiste` +
      (bugie.length ? " — inventati: " + bugie.join(", ") : ""));
    const fchanged = Object.keys(FORMTOK).filter(k => v.tok[k] !== BASE[k]);
    const fmiss = fchanged.filter(k => txt.indexOf(FORMTOK[k](v.tok)) < 0);
    ok(fmiss.length === 0, `${v.id}: dichiara le misure che cambia` +
      (fmiss.length ? " — taciute: " + fmiss.map(k => FORMTOK[k](v.tok)).join(", ")
                    : (fchanged.length ? " (" + [...new Set(fchanged.map(k => FORMTOK[k](v.tok)))].join(" · ") + ")"
                                       : " (nessuna)")));
    if (v.id === "V1")
      ok(v.deltaText.every(s => / = oggi$/.test(s)),
        "V1 dichiara di non cambiare niente in tutte e cinque le righe (e' il metro)");
    if (v.tok["ff-d"] !== BASE["ff-d"] || v.tok["ff-b"] !== BASE["ff-b"] || v.tok["ff-m"] !== BASE["ff-m"])
      ok(/caratteri /.test(v.deltaText[4]) && !/= oggi/.test(v.deltaText[4]),
        `${v.id}: dichiara i caratteri diversi — ${v.deltaText[4].slice(11)}`);
  }

  /* ------------ 6. i token dichiarati sono applicati sul contenitore vero */
  for (const v of CELLS) {
    const host = v.snap;
    const miss = ["bg", "paper", "ink", "ink-soft", "muted", "gold", "rad", "fs", "ff-d", "ff-m"]
      .concat(SLOTS).filter(k => host._css["--" + k] !== v.tok[k]);
    ok(miss.length === 0, `${v.id}: token applicati come custom property sull'istantanea` +
      (miss.length ? " — sbagliati/mancanti: " + miss.join(", ") : ` (--paper ${host._css["--paper"]})`));
  }

  /* ------- 7. ogni numero stampato, ricalcolato qui e ricercato nel testo */
  let printed = 0;
  for (const v of CELLS) {
    const surf = v.tok[v.surfKey || "paper"];
    ok(v.m.surf === surf, `${v.id}: misura sulla superficie giusta (${surf}` +
      (v.bare ? ", il fondo pagina: senza scheda il riquadro appoggia li'" : "") + ")");
    const r1 = v.figText[0], r2 = v.figText[1], r3 = v.figText[2];
    ok(r1.indexOf("su " + surf) === 0, `${v.id}: la riga del contrasto nomina la superficie`);
    for (const [tk, lab] of [["ink", "ink"], ["ink-soft", "soft"], ["muted", "muted"], ["gold", "oro"]]) {
      const mine = cr(v.tok[tk], surf), pass = mine >= 4.5 - 0.005;
      const want = lab + " " + f2(mine) + (pass ? "✓" : "✗");
      if (r1.indexOf(want) < 0)
        fails.push(`FAIL ${v.id}: la casella non stampa «${want}» — stampa «${r1}»`);
      else printed++;
    }
    const des = SLOTS.map(k => dE(v.tok.gold, PAL[k]));
    SLOTS.forEach((k, i) => {
      const want = k + " " + f1(des[i]) + (des[i] >= 15 - 0.005 ? "" : "✗");
      if (r2.indexOf(want) < 0) fails.push(`FAIL ${v.id}: ΔE non stampato «${want}» — «${r2}»`);
      else printed++;
    });
    const minDE = Math.min(...des), okDE = minDE >= 15 - 0.005;
    const wantMin = "min " + f1(minDE) + (okDE ? "✓" : "✗");
    if (r2.indexOf(wantMin) < 0) fails.push(`FAIL ${v.id}: minimo ΔE non stampato «${wantMin}» — «${r2}»`);
    else printed++;
    const sl = SLOTS.map(k => cr(PAL[k], surf));
    sl.forEach(x => { if (r3.indexOf(f2(x)) < 0) fails.push(`FAIL ${v.id}: contrasto serie non stampato ${f2(x)}`); else printed++; });
    const minS = Math.min(...sl), okS = minS >= 3 - 0.005;
    if (r3.indexOf("min " + f2(minS) + (okS ? "✓" : "✗")) < 0)
      fails.push(`FAIL ${v.id}: minimo serie non stampato — «${r3}»`);
    else printed++;
    /* e il verdetto in testa alla casella deve contare gli stessi guai */
    const mine = [4.5, 4.5, 4.5, 4.5].filter((need, i) =>
      cr(v.tok[["ink", "ink-soft", "muted", "gold"][i]], surf) < need - 0.005).length +
      des.filter(d => d < 15 - 0.005).length + sl.filter(x => x < 3 - 0.005).length;
    ok(v.m.fails === mine, `${v.id}: il verdetto in testa dice ${v.m.fails} fuori soglia, ` +
      `il ricalcolo indipendente ne conta ${mine}`);
    ok(v.pill.textContent === (mine ? mine + " fuori soglia" : "tutto in soglia"),
      `${v.id}: la pastiglia stampa «${v.pill.textContent}»`);
  }
  ok(true, `${printed} numeri stampati in pagina ricalcolati e ritrovati uno per uno`);
  ok(Math.abs(K.contrast("#ece3cd", "#211d16") - cr("#ece3cd", "#211d16")) < 1e-9,
    "la formula di contrasto della pagina e quella del check danno lo stesso numero");
  ok(Math.abs(K.deltaE("#e2c98f", "#c98500") - dE("#e2c98f", "#c98500")) < 1e-9, "idem per ΔE OKLab");

  /* --------------------- 8. le misure gia' in produzione non sono regredite */
  ok(BASE.muted === "#9a8d70" && cr(BASE.muted, BASE.paper) >= 4.5,
    `--muted ${BASE.muted} sta a ${cr(BASE.muted, BASE.paper).toFixed(2)}:1 sulla scheda (minimo 4,5)`);
  ok(BASE.gold === "#e2c98f" && SLOTS.every(k => dE(BASE.gold, PAL[k]) >= 15),
    `--gold ${BASE.gold} sta a ΔE ${Math.min(...SLOTS.map(k => dE(BASE.gold, PAL[k]))).toFixed(1)} ` +
    "dallo slot piu' vicino (minimo 15)");
  ok(cr("#8a7d62", BASE.paper) < 4.5 && dE("#c89a3f", PAL.s4) < 15,
    `i due valori di ieri restano fuori soglia: #8a7d62 a ${cr("#8a7d62", BASE.paper).toFixed(2)}:1, ` +
    `#c89a3f a ΔE ${dE("#c89a3f", PAL.s4).toFixed(1)} dallo slot 4`);
  /* V9 e' il controllo: rimette i due valori di ieri e ne escono TRE guai, non
     due — #8a7d62 sotto 4,5:1 e #c89a3f sotto ΔE 15 sia dallo slot 4 (5,2) sia,
     cosa che il laboratorio precedente non aveva isolato, dallo slot 2 (14,6). */
  const v9 = CELLS.find(v => v.id === "V9");
  ok(v9 && v9.m.fails === 3, `V9 «oro di ieri» dichiara in pagina 3 soglie sfondate ` +
    `(minuto ${cr("#8a7d62", BASE.paper).toFixed(2)}:1, ΔE ${dE("#c89a3f", PAL.s4).toFixed(1)} da s4 ` +
    `e ${dE("#c89a3f", PAL.s2).toFixed(1)} da s2) — ne dichiara ${v9 && v9.m.fails}`);
  const v3 = CELLS.find(v => v.id === "V3");
  ok(v3 && v3.m.fails === 1, `V3 «inchiostro» dichiara in pagina 1 soglia sfondata (${v3 && v3.m.fails})`);
  const passing = CELLS.filter(v => v.m.fails === 0).map(v => v.id);
  ok(passing.length === 7, `sette caselle su nove passano tutte le soglie: ${passing.join(" ")}`);

  /* --------------------------------------------------------------- 9. il voto */
  const v0 = CELLS[0];
  fire(v0.chips[7], "click");
  ok(v0.chips[7].classList.contains("sel"), "il gettone si seleziona");
  ok(K.votes()[v0.id] && K.votes()[v0.id].n === 7, "il voto finisce nel modello");
  fire(v0.star, "click");
  ok(v0.card.classList.contains("star"), "la stella marca la casella");
  const prog = document.getElementById("prog").textContent.replace(/\s+/g, " ");
  ok(/^1 \/ 9 votate$/.test(prog), `il contatore dice «${prog}»`);
  fire(document.getElementById("copy"), "click");
  const blob = document.getElementById("outbox").value;
  ok(/VOTI LAB-STILE micmer — griglia 3×3/.test(blob), "il blob ha l'intestazione");
  ok(new RegExp("★ " + v0.id).test(blob), "il blob riporta la preferita");
  ok(/MISURATO IN PAGINA:/.test(blob), "il blob si porta dietro le misure");
  ok(new RegExp("V9 su " + BASE.paper + " — minuto " + f2(cr("#8a7d62", BASE.paper)).replace(/[.,]/g, "[.,]"))
    .test(blob), "e il blob dice il numero della casella che sfonda");

  if (process.argv.includes("--verbose")) {
    console.log("\n--- le nove caselle, misura per misura ---");
    for (const v of CELLS) {
      const surf = v.tok[v.surfKey || "paper"];
      console.log(`\n  ${v.id} ${v.name} — superficie ${surf}`);
      console.log("    " + v.figText.join("\n    "));
      console.log("    " + v.deltaText.join("\n    "));
    }
  }
}

/* ---------------------------- la tavolozza e i caratteri, letti nel sorgente */
const PALCSS = { s1: "#3987e5", s2: "#d95926", s3: "#199e70", s4: "#c98500" };
for (const [k, v] of Object.entries(PALCSS))
  ok(new RegExp(k + ':\\s*"' + v + '"', "i").test(html), `${k} = ${v} (slot validato, invariato)`);
for (const f of ["Cinzel", "EB\\+Garamond", "IBM\\+Plex\\+Mono", "Fraunces", "Newsreader",
                 "Inter", "Instrument\\+Serif", "JetBrains\\+Mono"])
  ok(new RegExp("family=" + f).test(html), `il carattere ${f.replace(/\\\+/g, " ")} e' nel link di Google Fonts`);
ok(/grid-template-columns:repeat\(3,1fr\)/.test(html), "la griglia e' dichiarata 3×3");
ok(/aspect-ratio:1\/1/.test(html), "le caselle sono quadrate (aspect-ratio 1/1)");
ok(/@media\(max-width:1040px\)[\s\S]{0,120}repeat\(2,1fr\)/.test(html) &&
   /@media\(max-width:660px\)[\s\S]{0,120}grid-template-columns:1fr/.test(html),
  "la griglia collassa 3 → 2 → 1 colonna");
ok(/prefers-reduced-motion/.test(html), "il movimento ridotto e' rispettato");
ok(!/innerHTML\s*=/.test(script), "la pagina non scrive mai innerHTML (disciplina di check_vita.cjs)");

/* --------------------------------------------------------------------- esito */
const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
const body = [...notes, ...fails].join("\n");
console.log(body);
console.log(fails.length ? `\n${fails.length} CONTROLLI FALLITI` : "\ntutto a posto");

const head = fs.existsSync(REPORT) ? "" : "# /lab-stile — report cumulativo\n";
fs.appendFileSync(REPORT,
  `${head}\n## ${stamp} — check_lab_stile.cjs (griglia 3×3)\n\n\`\`\`\n${body}\n\`\`\`\n\n` +
  `esito: ${fails.length ? fails.length + " FALLITI" : "tutti passati"} (${notes.length} ok)\n`, "utf8");

process.exit(fails.length ? 1 : 0);
