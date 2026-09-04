/* Smoke test per vita/matrice/ — senza browser e senza dipendenze.
 *
 * Stessa scelta di `check_vita.cjs`: jsdom non si installa da questa rete e il
 * resto di tools/ gira in sola stdlib, quindi il DOM e' uno shim di un centinaio
 * di righe. Regge perche' la pagina costruisce i nodi uno a uno e se ne tiene il
 * riferimento invece di scrivere `innerHTML`; il giorno che torna a farlo questo
 * check smette di girare, ed e' il segnale giusto.
 *
 * Cosa verifica:
 *   1. lo script gira e disegna su TUTTE le coppie di assi, senza eccezioni;
 *   2. nessuna coordinata NaN o Infinity in nessun attributo SVG — il modo tipico
 *      in cui un grafico sbagliato non si vede invece di rompersi;
 *   3. gli assi «per 100 kcal» NON contengono gli alimenti senza calorie: e' la
 *      divisione per zero, e senza il controllo passa come punto a coordinata
 *      infinita, cioe' sparisce e basta;
 *   4. una cella vuota resta un buco: un alimento senza vitamina C misurata non
 *      finisce a zero sull'asse della vitamina C;
 *   5. il dato pubblicato coincide con i CSV di tools/food/data (se qualcuno
 *      tocca il catalogo senza rilanciare il build, qui diventa rosso);
 *   6. la classifica dice le stesse cose del grafico, ed e' la via senza colore:
 *      dieci righe col nome scritto;
 *   7. la tavolozza e' ancora quella di vita/index.html, valore per valore.
 *
 *   python tools/build_matrice.py && node tools/check_matrice.cjs
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const PAGE = path.join(ROOT, "vita", "matrice", "index.html");
const DATI = path.join(ROOT, "vita", "matrice", "data", "matrice.json");
const CSV = path.join(ROOT, "tools", "food", "data");

const fails = [], notes = [];
const ok = (cond, msg) => { (cond ? notes : fails).push((cond ? "ok   " : "FAIL ") + msg); };

/* ── lo shim di DOM ─────────────────────────────────────────────────────── */
function nodo(nome) {
  return {
    nodeName: nome, figli: [], attr: {}, style: {}, ascolti: {},
    _testo: null, className: "", value: "",
    get firstChild() { return this.figli[0] || null; },
    appendChild(c) { this.figli.push(c); return c; },
    removeChild(c) { this.figli = this.figli.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attr[k] = String(v); },
    getAttribute(k) { return k in this.attr ? this.attr[k] : null; },
    addEventListener(t, f) { (this.ascolti[t] = this.ascolti[t] || []).push(f); },
    fire(t) { (this.ascolti[t] || []).forEach((f) => f({})); },
    set textContent(v) { this.figli = []; this._testo = String(v); },
    get textContent() {
      if (this._testo !== null) return this._testo;
      return this.figli.map((f) => f.nodeName === "#text" ? f.dato : f.textContent).join("");
    }
  };
}
function testo(d) { return { nodeName: "#text", dato: String(d), figli: [], get textContent() { return this.dato; } }; }

const perId = {};
const document = {
  createElementNS(_ns, t) { return nodo(t); },
  createElement(t) { return nodo(t); },
  createTextNode: testo,
  documentElement: nodo("html"),
  getElementById: (id) => perId[id] || (perId[id] = nodo("div")),
  querySelector(sel) {
    if (sel === "#classifica tbody") return perId["__tbody"] || (perId["__tbody"] = nodo("tbody"));
    return nodo("div");
  }
};
const sandbox = {
  document, window: {}, console,
  getComputedStyle: () => ({ getPropertyValue: () => "" }),  // il ripiego della pagina
  Math, isFinite, String, Number, Array, Object, JSON, parseFloat, parseInt
};
sandbox.window = sandbox;

const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
try {
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox, { timeout: 10000 });
  ok(true, "lo script della pagina gira senza eccezioni");
} catch (e) {
  ok(false, "lo script della pagina esplode: " + e.message);
}
const M = sandbox.window.MATRICE;
if (!M) { ok(false, "la pagina non espone window.MATRICE: il check non puo' proseguire"); esci(); }

const dati = JSON.parse(fs.readFileSync(DATI, "utf8"));
M.accendi(dati);

/* ── 5. il dato pubblicato e i CSV ──────────────────────────────────────── */
function csv(file, saltaCommenti) {
  let righe = fs.readFileSync(path.join(CSV, file), "utf8").split(/\r?\n/).filter((r) => r.trim());
  if (saltaCommenti) righe = righe.filter((r) => !r.startsWith("#"));
  const cap = righe[0].split(",");
  return righe.slice(1).map((r) => {
    /* Un CSV con le virgolette: `fonte` contiene virgole. Basta un parser
       minimo, ma deve esserci — con uno split secco il conto delle colonne
       cambia riga per riga e il check misura un'altra cosa. */
    const celle = []; let cur = "", dentro = false;
    for (const ch of r) {
      if (ch === '"') dentro = !dentro;
      else if (ch === "," && !dentro) { celle.push(cur); cur = ""; }
      else cur += ch;
    }
    celle.push(cur);
    const o = {};
    cap.forEach((c, i) => { o[c.trim()] = (celle[i] || "").trim(); });
    return o;
  });
}
const foods = csv("foods.csv", false);
const orac = csv("orac.csv", true);
const log = csv("food_log.csv", false);
ok(dati.alimenti.length === foods.length,
  `il file pubblicato ha gli stessi alimenti del catalogo (${dati.alimenti.length} vs ${foods.length})`);
const conOrac = dati.alimenti.filter((a) => a.orac != null).length;
const idsFood = new Set(foods.map((f) => f.id));
const oracUtili = new Set(orac.filter((o) => idsFood.has(o.food_id) && o.orac_umol_te_100g).map((o) => o.food_id));
ok(conOrac === oracUtili.size, `l'ORAC copre ${conOrac} alimenti, come dice orac.csv (${oracUtili.size})`);
const mangiatiCsv = new Set(log.map((r) => r.food_id).filter((x) => idsFood.has(x)));
const mangiatiJson = dati.alimenti.filter((a) => a.volte).length;
ok(mangiatiJson === mangiatiCsv.size,
  `gli alimenti finiti nel piatto sono ${mangiatiJson}, come nel diario (${mangiatiCsv.size})`);

/* ── 1+2. ogni coppia di assi, e nessuna coordinata malata ──────────────── */
const svg = perId["grafico"];
const MALATI = [];
/* ⚠️ SI GUARDANO GLI ATTRIBUTI NUMERICI, UNO PER UNO, E NON LE STRINGHE.
 *
 * La prima versione cercava /nan|infinity/ dentro OGNI attributo, e il primo
 * giro e' diventato rosso su `data-id="banana"` — che contiene «nan». Un check
 * che grida al lupo su una banana lo si spegne dopo tre giorni, ed e' peggio di
 * non averlo. Quindi: l'elenco degli attributi che devono essere un numero, e
 * il numero si legge davvero. */
const NUMERICI = ["cx", "cy", "r", "x", "y", "x1", "y1", "x2", "y2",
  "width", "height", "font-size", "stroke-width", "fill-opacity", "stroke-opacity"];
function frugaSvg(n, dove) {
  for (const k of NUMERICI) {
    if (!(k in n.attr)) continue;
    const v = Number(n.attr[k]);
    if (!Number.isFinite(v)) MALATI.push(`${dove} ${n.nodeName}[${k}]="${n.attr[k]}"`);
  }
  /* `transform` e `viewBox` sono numeri dentro una frase: «translate» contiene
     una «e», che in un numero e' l'esponente. Quindi non si spezza la stringa —
     si cercano le parole NaN/Infinity, che sono l'unico modo in cui un conto
     sbagliato finisce li' dentro. */
  for (const k of ["transform", "viewBox"]) {
    if (k in n.attr && /\b(NaN|-?Infinity|undefined)\b/.test(String(n.attr[k])))
      MALATI.push(`${dove} ${n.nodeName}[${k}]="${n.attr[k]}"`);
  }
  n.figli.forEach((f) => f.attr && frugaSvg(f, dove));
}
let coppie = 0, vuoti = 0;
for (const mx of M.MISURE) {
  for (const my of M.MISURE) {
    M.stato.x = mx.id; M.stato.y = my.id;
    try { M.disegna(); } catch (e) { ok(false, `disegno ${mx.id}/${my.id}: ${e.message}`); }
    coppie++;
    const cerchi = svg.figli.filter((f) => f.nodeName === "circle");
    if (!cerchi.length) vuoti++;
    frugaSvg(svg, `${mx.id}/${my.id}`);
  }
}
ok(coppie === M.MISURE.length ** 2, `disegnate tutte le ${coppie} coppie di assi`);
ok(vuoti === 0, `nessuna coppia di assi lascia il grafico vuoto (${vuoti} vuote)`);
ok(MALATI.length === 0, "nessuna coordinata NaN/Infinity nell'SVG" +
  (MALATI.length ? ": " + MALATI.slice(0, 3).join(" · ") : ""));

/* ── 3. la divisione per zero ───────────────────────────────────────────── */
const senzaKcal = dati.alimenti.filter((a) => !(a.kcal > 0));
ok(senzaKcal.length > 0, `nel catalogo ci sono ${senzaKcal.length} alimenti senza calorie: il caso esiste davvero`);
const perKcal = M.MISURE.filter((m) => /_kcal$/.test(m.id));
let intrusi = 0;
for (const m of perKcal) for (const a of senzaKcal) if (m.f(a) != null) intrusi++;
ok(intrusi === 0, `nessun alimento senza calorie finisce su un asse «per 100 kcal» (${perKcal.length} assi controllati)`);

/* ── 4. il buco resta un buco ───────────────────────────────────────────── */
/* L'ORAC e' il caso vero: 139 alimenti su 206 non ce l'hanno, e il file da cui
   viene lo dice a chiare lettere — «chi manca non e' dimenticato, e' senza un
   valore difendibile». Se quei 139 finissero a zero, la pagina direbbe che il
   caffe' e la carne hanno zero polifenoli misurati, che non e' quello che si sa. */
const misuraOrac = M.MISURE.find((m) => m.id === "orac");
const senzaOrac = dati.alimenti.filter((a) => a.orac === undefined);
ok(senzaOrac.length > 100, `il buco esiste ed e' grande: ${senzaOrac.length} alimenti senza ORAC`);
ok(senzaOrac.every((a) => misuraOrac.f(a) === null),
  "nessun alimento senza ORAC finisce a zero sull'asse dell'ORAC");

/* ── 6. la via senza colore ─────────────────────────────────────────────── */
M.stato.x = "kcal"; M.stato.y = "prot_kcal"; M.disegna();
const tbody = perId["__tbody"];
ok(tbody.figli.length === 10, `la classifica ha dieci righe (${tbody.figli.length})`);
ok(tbody.figli.every((tr) => (tr.figli[0] ? tr.figli[0].textContent.trim().length : 0) > 1),
  "ogni riga della classifica porta il nome scritto dell'alimento");
const nomiScritti = svg.figli.filter((f) => f.nodeName === "text" && f.attr["font-weight"] === "700").length;
ok(nomiScritti >= 5, `almeno cinque nomi sono scritti sul grafico, non solo colorati (${nomiScritti})`);
ok(perId["legenda"].figli.length >= 4, "la legenda elenca le quattro famiglie");

/* ── 7. la tavolozza, valore per valore ─────────────────────────────────── */
const vitaCss = fs.readFileSync(path.join(ROOT, "vita", "index.html"), "utf8");
const daRoot = (testo, nome) => {
  const m = testo.match(new RegExp("--" + nome + "\\s*:\\s*([^;]+);"));
  return m ? m[1].trim().toLowerCase() : null;
};
for (const t of ["s1", "s2", "s3", "s4", "muted", "paper", "ink", "bg"]) {
  const qui = daRoot(html, t), la = daRoot(vitaCss, t);
  ok(qui !== null && qui === la, `--${t} è lo stesso di vita/index.html (${qui} vs ${la})`);
}
/* --muted e' il colore di ogni didascalia ed etichetta d'asse: sotto 4,5:1 sul
   fondo della scheda una pagina di numeri diventa illeggibile a chi non ha la
   vista di un ventenne. Si misura, non si spera. */
function luminanza(hex) {
  const c = hex.replace("#", "");
  const v = [0, 2, 4].map((i) => {
    const x = parseInt(c.slice(i, i + 2), 16) / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
const contrasto = (a, b) => {
  const [x, y] = [luminanza(a), luminanza(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const cMuted = contrasto(daRoot(html, "muted"), daRoot(html, "paper"));
ok(cMuted >= 4.5, `--muted sul fondo della scheda sta a ${cMuted.toFixed(2)}:1 (serve 4,5:1)`);

/* ── il referto ─────────────────────────────────────────────────────────── */
function esci() {
  notes.forEach((n) => console.log(n));
  fails.forEach((f) => console.log(f));
  console.log(fails.length ? `\n${fails.length} controlli rossi su ${fails.length + notes.length}.`
    : `\ntutto a posto — ${notes.length} controlli.`);
  process.exit(fails.length ? 1 : 0);
}
esci();
