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
 *   4b. la vista compatta (ridgeline): l'interruttore esiste e ricorda la scelta,
 *      ogni corsia disegnata ha il proprio nome scritto SULLA linea (li' l'identita'
 *      non ha nessun altro posto dove stare), niente esce dal viewBox — nemmeno i
 *      tracciati, che e' il punto: le corsie sono tagliate ai bordi apposta —,
 *      congelare una serie la marca e la lascia nella ridgeline principale, e gli
 *      interruttori laterali cambiano davvero cosa viene disegnato;
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
/* La larghezza che il finto DOM dichiara. E' una variabile e non una costante
   perche' mezza impaginazione dipende da quanto spazio c'e': la ridgeline scrive
   l'escursione di ogni corsia a destra del nome solo se ci sta, e una regola del
   genere si verifica soltanto misurandola a piu' larghezze. 360 e' la colonna di un
   telefono, 1040 il pannello su un portatile. */
let SHIM_W = 360;
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
  getBoundingClientRect() { return { width: SHIM_W, height: 180, top: 0, left: 0, right: SHIM_W, bottom: 180 }; }
  get clientWidth() { return SHIM_W; }
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
for (const id of ["tip", "totals", "ranges", "viewsw", "range-note", "compact",
  "panel-carico", "panel-notte", "panel-recupero", "panel-corpo", "panel-metabolismo",
  "panel-volume", "panel-incroci", "panel-tavola", "tracks", "sheet", "sheet-in"]) document.getElementById(id);

/* localStorage finto: la pagina ci salva la forma della vista e quali serie sono
   accese, ed e' l'unico stato che sopravvive alla visita — quindi va verificato che
   ci finisca davvero, non solo che la pagina non esploda senza. Parte vuoto, cosi'
   i default che il check misura sono quelli di una prima visita. */
const LS = {};
const localStorage = {
  getItem: k => (k in LS ? LS[k] : null),
  setItem: (k, v) => { LS[k] = String(v); },
  removeItem: k => { delete LS[k]; },
};

const sandbox = {
  document, console, localStorage,
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

  /* --------------------------------------- 3. medie delle ultime due settimane */
  const N = D.n;
  let secs = 0, dist = 0, gain = 0;
  for (const [, , s, m, up] of D.acts) { secs += s; dist += m; gain += up; }
  const totalsHtml = document.getElementById("totals").innerHTML;
  const it = v => v.toLocaleString("it-IT");
  for (const label of ["sonno", "HRV", "FC riposo", "allenamento", "chilometri",
                        "kcal", "proteine", "carboidrati", "fibre", "vegetale"]) {
    ok(totalsHtml.includes(`>${label}<`), `testata 14 giorni: ${label}`);
  }
  ok(totalsHtml.includes("vs prima"), "ogni media dichiara il confronto con i 14 giorni precedenti");
  ok(totalsHtml.includes('data-food="1"'), "le metriche alimentari aprono gli insight");
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

  /* ------------------- 4a. i riquadri nuovi: presenti, pieni, e dichiarati
     Cinque vengono dal modello metabolico e due dalla lista delle attivita'. Non
     basta che esistano: quattro di loro sono numeri COSTRUITI (heat strain, FatMax,
     momento metabolico) o un sensore letto fuori dal suo mestiere (la temperatura al
     polso, che non e' il meteo), e su un grafico un numero costruito e un numero
     misurato hanno lo stesso aspetto. Quindi ognuno deve portare in chiaro la propria
     natura: se un giorno qualcuno accorcia una didascalia, il check se ne accorge. */
  const NEW_TILES = [
    ["Temperatura", /non è il meteo/i],
    ["Heat strain", /indice costruito/i],
    ["FatMax", /è un modello/i],
    ["Minuti dentro la banda", /modello/i],
    ["Momento metabolico", /componenti/i],
    ["Mezze maratone", /21,0975/],
    ["Salite lunghe", /mediana/i],
  ];
  const strip0 = s => String(s).replace(/<[^>]+>/g, "");
  for (const [title, must] of NEW_TILES) {
    const m = K.MOUNTED.find(([, t]) => t.title === title);
    ok(!!m, `il riquadro "${title}" è in pagina`);
    if (!m) continue;
    const [n, t] = m;
    ok(!n.art.dataset.err, `"${title}" non solleva` + (n.art.dataset.err ? `: ${n.art.dataset.err}` : ""));
    ok(!n.art.dataset.empty, `"${title}" disegna qualcosa (non è un riquadro vuoto)`);
    ok(n.tbody.innerHTML.includes("<tr"), `"${title}" ha la sua tabella di ripiego`);
    ok(must.test(strip0(n.foot.innerHTML)),
      `"${title}" dichiara cosa è nel piede (cerco ${must})`);
    ok(/\S/.test(String(n.now.innerHTML)), `"${title}" ha il suo numero di testa`);
  }

  /* il momento metabolico non si disegna sotto la soglia di componenti: e' la
     differenza fra "questo giorno vale −8" e "questo giorno varrebbe −8 se avessi
     tre delle sei cose che servono per dirlo" */
  const mm = K.mm;
  ok(!!mm, "il momento metabolico è arrivato in pagina");
  if (mm) {
    const cnt = (D.metab || {}).mm_n;
    let sotto = 0, sopra = 0;
    for (let i = 0; i < D.n; i++) {
      if (mm.arr[i] === null || mm.arr[i] === undefined) continue;
      if (!(cnt && cnt[i] !== null && cnt[i] >= K.mmMin)) sotto++; else sopra++;
    }
    ok(sotto === 0,
      `nessun giorno disegnato poggia su meno di ${K.mmMin} componenti (${sotto} violazioni)`);
    ok(mm.dropped > 0 && sopra === mm.drawn,
      `${mm.drawn} giorni disegnati, ${mm.dropped} scartati sotto soglia`);
    const t = K.MOUNTED.find(([, x]) => x.title === "Momento metabolico");
    ok(t && String(t[1].cap).includes(String(K.mmMin)),
      "e la didascalia dice qual è la soglia");
  }

  /* --------------------------------------- 4b. la vista compatta (ridgeline)
     La vista estesa si controlla riquadro per riquadro; questa ha un solo disegno e
     venti corsie dentro, quindi i controlli sono diversi: che l'identita' ci sia
     (il nome sulla linea, perche' qui non c'e' ne' legenda ne' colonna laterale),
     che niente sfori il viewBox — TRACCIATI COMPRESI, perche' la normalizzazione per
     corsia funziona tagliando ai bordi e se il taglio salta la corsia invade quella
     sopra —, e che i tre comandi (vista, congelamento, interruttori) cambino davvero
     il DOM invece di limitarsi a cambiare una variabile. */
  const C = K.compact;
  ok(!!C, "window.CRUSCOTTO.compact esposto");
  if (C) {
    ok(/id="viewsw"/.test(html), "l'interruttore di vista e' in pagina (#viewsw)");
    const sw = document.getElementById("viewsw");
    ok(sw._kids.length === 2, `l'interruttore ha due posizioni (${sw._kids.length})`);
    ok(C.view() === "estesa", "senza preferenza salvata si parte dalla vista estesa");
    ok(C.series.length >= 15, `${C.series.length} serie dichiarate per la ridgeline`);

    C.setView("compatta");
    ok(C.view() === "compatta" && document.body.dataset.view === "compatta",
      "setView(compatta) commuta la vista e marca il body (e' cio' che il CSS legge)");
    ok(LS["vita:view"] === "compatta", "la scelta della vista finisce in localStorage");
    ok(sw._kids.filter(b => b.attrs["aria-pressed"] === "true").length === 1,
      "una sola posizione dell'interruttore risulta premuta");
    ok(/propria/.test(C.note.innerHTML) && /percentile/.test(C.note.innerHTML),
      "la pagina dichiara che ogni corsia e' riscalata sulla propria storia");

    /* geometria della ridgeline, su tutte e quattro le finestre */
    const scan = tag => {
      const svgs = [C.svg(), C.pinSvg()].filter(Boolean);
      const out = [], nan = [], coll = [];
      for (const svg of svgs) {
        const [, , W, H] = svg.attrs.viewBox.split(/\s+/).map(Number);
        const kids = svg.descendants();
        for (const c of kids) {
          for (const [k, v] of Object.entries(c.attrs)) {
            if (/NaN|Infinity|undefined/.test(v)) nan.push(`<${c.tagName} ${k}="${v.slice(0, 50)}">`);
          }
          const num = k => c.attrs[k] === undefined ? null : parseFloat(c.attrs[k]);
          const pts = [];
          if (c.tagName === "circle") pts.push([num("cx"), num("cy")]);
          if (c.tagName === "rect") pts.push([num("x"), num("y")],
            [num("x") + num("width"), num("y") + num("height")]);
          if (c.tagName === "line") pts.push([num("x1"), num("y1")], [num("x2"), num("y2")]);
          if (c.tagName === "path") {
            /* i tracciati usano solo M/L/Z, quindi ogni numero e' una coordinata */
            const n = (c.attrs.d.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
            for (let i = 0; i + 1 < n.length; i += 2) pts.push([n[i], n[i + 1]]);
          }
          for (const [x, y] of pts) {
            if (x < -0.6 || x > W + 0.6 || y < -0.6 || y > H + 0.6) {
              out.push(`[${tag}] <${c.tagName}> a ${x.toFixed(1)},${y.toFixed(1)} fuori da ${W}×${H}`);
              break;
            }
          }
        }
        /* etichette sulla stessa riga: il nome a sinistra e l'escursione a destra
           non si devono toccare, o la corsia perde l'uno o l'altra */
        const byRow = {};
        for (const c of kids.filter(c => c.tagName === "text")) {
          const w = (c.textContent || "").length * GLYPH, x = parseFloat(c.attrs.x);
          const a = c.attrs["text-anchor"];
          const l = a === "end" ? x - w : a === "middle" ? x - w / 2 : x;
          (byRow[c.attrs.y] = byRow[c.attrs.y] || []).push({ l, r: l + w, s: c.textContent });
        }
        for (const y of Object.keys(byRow)) {
          const row = byRow[y].sort((a, b) => a.l - b.l);
          for (let i = 1; i < row.length; i++) {
            if (row[i].l < row[i - 1].r + 1) coll.push(`[${tag}] "${row[i - 1].s}" e "${row[i].s}"`);
          }
        }
      }
      return { out, nan, coll };
    };

    const gOut = [], gNan = [], gColl = [], counts = [], heights = [];
    for (const w of [360, 1040]) {
      SHIM_W = w;
      /* una corsia congelata per volta: la striscia appiccicata e' un secondo SVG
         con la sua geometria, e non verrebbe mai misurata se non ce ne fosse una */
      C.pin(C.series[0].key);
      for (const r of ["2a", "1a", "3m", "sempre"]) {
        try { K.setRange(r); } catch (e) { fails.push(`FAIL compatta setRange(${r}): ${e && e.stack || e}`); }
        const s = scan(`${w}px/${r}`);
        gOut.push(...s.out); gNan.push(...s.nan); gColl.push(...s.coll);
        if (w === 1040 && r === "sempre") {
          counts.push(`${C.lanes().length} corsie`);
          heights.push(`alto ${C.svg().attrs.viewBox.split(/\s+/)[3]} px`);
        }
        /* L'etichetta non e' piu' solo il nome: puo' portare il fiocco delle
           congelate e il marchio "· rada". Si confronta con quello che la corsia
           DICE di aver scritto (labelText) e si pretende che il nome ci sia dentro,
           invece di inseguire i decori uno per uno con una replace(). */
        const noLab = C.lanes().filter(L => !L.label ||
          String(L.label.textContent) !== L.labelText ||
          !String(L.labelText).includes(L.name));
        if (noLab.length) fails.push(`FAIL [${w}px/${r}] ${noLab.length} corsie senza il proprio nome sulla linea`);
      }
      C.unpin(C.series[0].key);
    }
    SHIM_W = 360;
    ok(gNan.length === 0, "compatta: nessuna coordinata NaN/Infinity" +
      (gNan.length ? ` — ${gNan.length}, es. ${gNan[0]}` : ""));
    ok(gOut.length === 0, "compatta: nessun segno fuori dal viewBox, tracciati compresi" +
      (gOut.length ? ` — ${gOut.length}, es. ${gOut[0]}` : ""));
    ok(gColl.length === 0, "compatta: nessuna etichetta sovrapposta sulla stessa riga" +
      (gColl.length ? ` — ${gColl.length}, es. ${gColl[0]}` : ""));
    notes.push(`info  compatta su 1040 px, finestra "sempre": ${counts.join(", ")}, ${heights.join(", ")}`);

    K.setRange("sempre");
    const lanes0 = C.lanes();
    ok(lanes0.length >= 7, `compatta: almeno sette corsie in colonna (${lanes0.length})`);
    ok(lanes0.every(L => L.label && String(L.label.textContent) === L.labelText &&
      String(L.labelText).includes(L.name)),
      "compatta: ogni corsia mostrata ha il proprio nome scritto sulla linea");

    /* ---- congelamento: marca la serie e la lascia dov'era ---- */
    const k1 = lanes0[0].key, k2 = lanes0[1].key;
    C.pin(k1);
    ok(C.pinned().includes(k1), `pin(${k1}) congela la serie`);
    const still = C.lanes().find(L => L.key === k1);
    ok(!!still, "la corsia congelata resta nella ridgeline principale (non viene spostata via)");
    ok(still && still.g.dataset.pinned === "1", "la corsia congelata e' marcata nel DOM (data-pinned)");
    ok(C.pinLanes().some(L => L.key === k1), "e compare nella striscia appiccicata in cima");
    C.pin(k2);
    ok(C.pinLanes().length === 2, `piu' serie congelabili insieme (${C.pinLanes().length})`);
    ok(C.pinLanes().every(L => L.label &&
      String(L.label.textContent).replace("❄ ", "") === L.name),
      "anche nella striscia il nome sta sulla linea");
    ok(LS["vita:pin"] && LS["vita:pin"].split(",").length === 2,
      "le congelate finiscono in localStorage");
    C.unpin(k1); C.unpin(k2);
    ok(C.pinned().length === 0 && C.pinLanes().length === 0,
      "sganciandole spariscono dalla striscia e la striscia si chiude");

    /* ---- interruttori laterali: cambiano davvero il disegno ---- */
    /* solo gli interruttori di serie: in cima alla colonna ci sono anche "tutte" e
       "somma", che sono comandi, non serie */
    const railBtns = C.rail.descendants().filter(n => n.className === "cx-sw");
    ok(railBtns.length === C.series.length,
      `un interruttore per serie (${railBtns.length}/${C.series.length})`);
    const heads = C.rail.descendants().filter(n => n.className === "cx-grp-h")
      .map(n => n.textContent);
    const secs = [...new Set(C.series.map(s => s.sec))];
    ok(secs.every(s => heads.includes(s)),
      `gli interruttori sono raggruppati per sezione (${heads.join(", ")})`);

    const before = C.lanes().length, kOff = lanes0[0].key, nOff = lanes0[0].name;
    C.toggle(kOff);
    const after = C.lanes();
    ok(after.length === before - 1,
      `spegnere un interruttore toglie una corsia dal disegno (${before} → ${after.length})`);
    ok(!after.some(L => L.key === kOff), `"${nOff}" non e' piu' fra le corsie disegnate`);
    ok(!C.svg().descendants().some(c => c.tagName === "text" &&
      String(c.textContent).replace("❄ ", "") === nOff),
      `e la sua etichetta e' sparita dall'SVG`);
    ok(LS["vita:off"] === kOff, "la serie spenta finisce in localStorage");
    C.toggle(kOff);
    ok(C.lanes().length === before, "riaccendendolo la corsia torna");

    /* ---- 4c. selezione a isolamento -----------------------------------------
       Un click su una voce laterale ISOLA quella serie; un click su un'altra
       sposta l'isolamento; lo stesso una seconda volta rimette tutto. Piu' serie
       insieme si accendono col modificatore o col modo "somma". Si prova
       railClick(), cioe' esattamente la funzione che il bottone chiama: provare la
       regola sotto verificherebbe la regola e non il cablaggio. */
    const kA = C.series[0].key, kB = C.series[1].key;
    C.showAll();
    ok(C.enabled().length === C.series.length && C.isolated() === null,
      `"tutte" riaccende ogni serie (${C.enabled().length})`);

    C.railClick(kA, {});
    ok(C.isolated() === kA && C.enabled().length === 1 && C.enabled()[0] === kA,
      `un click isola "${C.series[0].name}": resta disegnata solo lei`);
    ok(C.lanes().length === 1 && C.lanes()[0].key === kA,
      "e nella ridgeline c'e' davvero una corsia sola");
    ok(LS["vita:iso"] === kA, "l'isolamento finisce in localStorage");
    ok(C.series[0]._btn && C.series[0]._btn.dataset.iso === "1",
      "l'interruttore isolato e' marcato (data-iso), non solo premuto");

    C.railClick(kB, {});
    ok(C.isolated() === kB && C.enabled().length === 1 && C.enabled()[0] === kB,
      `un click su un'altra voce sposta l'isolamento su "${C.series[1].name}"`);
    ok(C.series[0]._btn.dataset.iso !== "1", "e la precedente smette di essere marcata");

    C.railClick(kB, {});
    ok(C.isolated() === null && C.enabled().length === C.series.length,
      "la stessa voce una seconda volta rimette tutto");

    /* piu' serie insieme: col modificatore... */
    C.railClick(kA, {});
    C.railClick(kB, { metaKey: true });
    ok(C.isolated() === null && C.enabled().length === 2 &&
      C.enabled().includes(kA) && C.enabled().includes(kB),
      "⌘/Ctrl-click ne accende una seconda senza sciogliere la selezione");
    C.railClick(kB, { ctrlKey: true });
    ok(C.enabled().length === 1 && C.enabled()[0] === kA,
      "e un secondo modificato la rispegne");

    /* ...e col modo dedicato, che e' il gemello raggiungibile da tastiera */
    C.showAll(); C.setMulti(true);
    ok(C.multi() === true && C.multiBtn.attrs["aria-pressed"] === "true",
      "il modo \"somma\" si accende e lo dichiara (aria-pressed)");
    C.railClick(kA, {});
    ok(C.isolated() === null && C.enabled().length === C.series.length - 1 &&
      !C.enabled().includes(kA),
      "in modo somma un click semplice spegne una voce sola invece di isolare");
    C.setMulti(false); C.showAll();
    ok(C.multi() === false && C.enabled().length === C.series.length,
      "spegnendo il modo somma e riaccendendo tutto si torna al punto di partenza");

    /* un'interazione che non si annuncia non esiste: deve stare scritta in pagina */
    const note = C.note.innerHTML;
    ok(/isola/i.test(note), "la pagina dichiara che un click isola");
    ok(/Ctrl/.test(note) && /somma/.test(note),
      "la pagina dichiara come accenderne piu' di una (modificatore e modo somma)");
    ok(!!C.allBtn && !!C.multiBtn, "i due comandi \"tutte\" e \"somma\" sono in pagina");

    /* ---- 4d. il vuoto di una corsia e' disegnato, non lasciato bianco ---------
       Misurato il 2026-08-11: in finestra "sempre", a 1040 px, NESSUNA corsia si
       ferma a meta' — ogni tracciato arriva al bordo destro. Quello che manca e'
       l'INIZIO: il carico attacca al 37 % della larghezza, sonno e HRV all'86 %, la
       tavola all'82 %, e la temperatura al polso si spezza in sette tratti perche'
       esiste solo nei giorni con un'uscita. Quei vuoti si leggevano come un grafico
       rotto. Adesso ogni vuoto porta il suo tratteggio e ogni inizio il suo
       trattino, e questo controllo tiene che sia cosi'. */
    K.setRange("sempre");
    /* si misura contro la geometria che il disegno ha DAVVERO usato (voidPx,
       startGapPx), non contro una regola riscritta qui: due copie della stessa
       soglia divergono al primo ritocco, e questo controllo comincerebbe a
       promuovere corsie che non hanno un vuoto visibile */
    const withVoid = C.lanes().filter(L => L.voidPx > 0);
    const lateStart = C.lanes().filter(L => L.i0 !== null && L.startGapPx > 12);
    ok(withVoid.length >= 5,
      `${withVoid.length} corsie su ${C.lanes().length} hanno del vuoto da dichiarare`);
    ok(lateStart.length >= 5,
      `${lateStart.length} corsie cominciano visibilmente dopo il bordo sinistro`);
    const dashOf = L => L.g.descendants().filter(c => c.tagName === "line" &&
      c.attrs["stroke-dasharray"]);
    const noDash = withVoid.filter(L => dashOf(L).length === 0);
    ok(noDash.length === 0, "ogni corsia con del vuoto lo dichiara con un tratteggio" +
      (noDash.length ? ` — senza: ${noDash.map(L => L.name).join(", ")}` : ""));
    const tickOf = L => L.g.descendants().filter(c => c.tagName === "line" &&
      !c.attrs["stroke-dasharray"] && Math.abs(parseFloat(c.attrs.x1) - parseFloat(c.attrs.x2)) < .01);
    const noTick = lateStart.filter(L => tickOf(L).length === 0);
    ok(noTick.length === 0, "e il giorno in cui comincia porta il suo trattino verticale" +
      (noTick.length ? ` — senza: ${noTick.map(L => L.name).join(", ")}` : ""));
    /* i buchi IN MEZZO valgono come quelli in testa: la temperatura al polso esiste
       solo nei giorni con un'uscita e si spezza in piu' tratti */
    const spezzate = C.lanes().filter(L =>
      L.g.descendants().filter(c => c.tagName === "path" && c.attrs.fill === "none").length > 1);
    ok(spezzate.length === 0 || spezzate.every(L => dashOf(L).length >= 2),
      `anche i buchi in mezzo sono tratteggiati (${spezzate.length} corsie spezzate: ` +
      `${spezzate.map(L => L.name).join(", ") || "nessuna"})`);

    /* le serie rade: poche misure vere unite da una media mobile. La linea e'
       continua, il dato no, e l'etichetta lo deve dire. */
    const rade = C.lanes().filter(L => L.sparse);
    ok(rade.length >= 1, `almeno una corsia e' marcata come rada (${rade.map(L => L.name).join(", ") || "nessuna"})`);
    ok(rade.every(L => /rada/.test(L.labelText)),
      "ogni corsia rada lo scrive nella propria etichetta");
    ok(C.lanes().filter(L => !L.sparse).every(L => !/rada/.test(L.labelText)),
      "e nessuna corsia densa se lo prende");

    /* ---- 4e. trasparenza: la corsia occlude meno, e la congelata si marca col
       tratto invece che con un riquadro. I due numeri sono decisioni misurate
       (l'occlusore stava a .88 e si leggeva come una scatola), quindi si fissano
       qui: una deriva "solo di un pelo" non deve poter passare inosservata. */
    const occl = C.svg().descendants().filter(c => c.tagName === "path" &&
      c.attrs.fill === "var(--paper)").map(c => Number(c.attrs.opacity));
    ok(occl.length > 0, `le corsie hanno il loro occlusore (${occl.length} riempimenti)`);
    ok(occl.length > 0 && Math.max(...occl) <= .70,
      `l'occlusione e' scesa sotto .70 (max ${Math.max(...occl)}) — era .88, la "scatola"`);
    ok(occl.length > 0 && Math.min(...occl) >= .50,
      `ma non sotto .50 (min ${Math.min(...occl)}): piu' in basso le due corsie ` +
      `sovrapposte pesano uguale e la sovrapposizione perde il davanti`);

    C.pin(kA);
    const pinG = C.lanes().find(L => L.key === kA);
    const otherG = C.lanes().find(L => L.key !== kA);
    const strokesOf = L => L.g.descendants().filter(c => c.tagName === "path" &&
      c.attrs.fill === "none");
    ok(pinG && strokesOf(pinG).some(p => Number(p.attrs["stroke-width"]) >= 2.5),
      "la corsia congelata si marca ingrossando il tratto");
    ok(pinG && strokesOf(pinG).some(p => Number(p.attrs["stroke-width"]) >= 6 &&
      Number(p.attrs.opacity) < .4), "e prende un alone trasparente, non un bordo");
    ok(otherG && strokesOf(otherG).every(p => Number(p.attrs.opacity) < .9),
      "mentre le altre si ritirano — il congelamento e' contrasto, non un riquadro");
    /* dentro il gruppo di una corsia l'unico rettangolo ammesso e' la zona sensibile,
       che e' trasparente: se ne comparisse uno pieno saremmo tornati alla scatola */
    const boxes = C.lanes().flatMap(L => L.g.descendants()
      .filter(c => c.tagName === "rect" && c.attrs.fill !== "transparent"));
    ok(boxes.length === 0,
      "e dentro una corsia non c'e' nessun rettangolo pieno: congelare non aggiunge riquadri");
    C.unpin(kA);

    /* ---- e la vista estesa e' rimasta quella di prima ---- */
    C.setView("estesa");
    ok(C.view() === "estesa" && document.body.dataset.view === "estesa",
      "si torna alla vista estesa");
    const backErr = K.MOUNTED.filter(([n]) => n.art.dataset.err).map(([, t]) => t.title);
    const backEmpty = K.MOUNTED.filter(([n]) => n.art.dataset.empty).map(([, t]) => t.title);
    ok(backErr.length === 0, "tornando all'estesa nessun riquadro solleva" +
      (backErr.length ? ` — ${backErr.join(", ")}` : ""));
    ok(backEmpty.length === 0, "tornando all'estesa nessun riquadro resta vuoto" +
      (backEmpty.length ? ` — ${backEmpty.join(", ")}` : ""));
  }

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

/* --ridge: la vista compatta letta a parole — una riga per corsia, con la quota a
   cui sta la sua linea di base, l'escursione che si e' data e quanto sconfina in
   quella sopra. E' l'unico modo, da qui, di rispondere a "quante ne vedo insieme". */
if (ran && process.argv.includes("--ridge")) {
  const C = sandbox.CRUSCOTTO.compact;
  SHIM_W = 1040;
  C.setView("compatta"); sandbox.CRUSCOTTO.setRange("sempre");
  const svg = C.svg(), H = Number(svg.attrs.viewBox.split(/\s+/)[3]);
  const L = C.lanes();
  console.log(`\n--- ridgeline, 1040 px, finestra "sempre": ${L.length} corsie, alta ${H} px ---`);
  let prev = null;
  for (const l of L) {
    const rng = l.g._kids.filter(c => c.tagName === "text" && c.attrs["text-anchor"] === "end")
      .map(c => c.textContent)[0] || "—";
    const seg = l.g._kids.filter(c => c.tagName === "path" && c.attrs.fill === "none").length;
    console.log(`  y ${String(Math.round(l.base)).padStart(5)}  ${l.name.padEnd(20)} ` +
      `escursione ${rng.padEnd(24)} ${seg} tratti` +
      (prev === null ? "" : `  passo ${Math.round(l.base - prev)}`));
    prev = l.base;
  }
  const vh = 900;
  const amp = L.length > 1 ? L[1].base - L[0].base : 0;
  const fit = Math.floor((vh - (L[0].base - 5)) / (amp || 1)) + 1;
  console.log(`  → in una schermata alta ${vh} px ci stanno ${fit} corsie intere`);
  C.setView("estesa"); SHIM_W = 360;
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
