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
  /* I gestori si TENGONO, invece di essere buttati. Finche' la pagina era solo
     grafici bastava disegnarli e misurarli; da quando c'e' il diario, meta' di
     quello che puo' rompersi sta dietro un click — scegliere il pasto, premere un
     preset, correggere una quantita' — e un DOM che scarta i gestori non puo'
     provarne nemmeno uno. `fire()` chiama il gestore come farebbe il browser. */
  addEventListener(type, fn) { (this._on = this._on || {})[type] = fn; }
  fire(type, ev) {
    const fn = this._on && this._on[type];
    if (typeof fn !== "function") return false;
    fn(Object.assign({ target: this, currentTarget: this }, ev || {}));
    return true;
  }
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

/* `fetch` finto: registra la richiesta e risponde a vuoto. Serve al diario, che da
   quando ha un Worker dietro parla in rete — e la cosa da verificare non e' la
   rete, e' COSA le manda: pasto, alimento, quantita', row_key. Quello si guarda
   qui, senza uscire dal processo. */
const FETCHES = [];
const fakeFetch = (url, opts) => {
  const o = opts || {};
  FETCHES.push({ url: String(url), method: o.method || "GET",
                 headers: o.headers || {},
                 body: o.body ? JSON.parse(o.body) : null });
  const body = /\/api\/day\//.test(String(url)) ? { ops: [] } : { ok: true };
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
};

const sandbox = {
  document, console, localStorage, fetch: fakeFetch,
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

  /* La provenienza e' un campo, non piu' una raccomandazione (16/08/2026). Un riquadro
     nuovo che nasce senza `src` scivolerebbe in pagina senza dire da dove vengono i suoi
     numeri, ed e' esattamente cio' che la terza regola di CLAUDE.md vieta. */
  const SRC_OK = ["misurato", "ricostruito", "modello", "stima"];
  const senzaSrc = K.TILES.filter(t => !SRC_OK.includes(t.src));
  ok(senzaSrc.length === 0,
    `ogni riquadro dichiara la provenienza (${K.TILES.length - senzaSrc.length}/${K.TILES.length})` +
    (senzaSrc.length ? " — senza: " + senzaSrc.map(t => `${t.title}=${t.src}`).join(", ") : ""));
  {
    const per = {};
    K.TILES.forEach(t => { per[t.src] = (per[t.src] || 0) + 1; });
    ok(Object.keys(per).length >= 3,
      "il vocabolario e' usato davvero, non una parola sola: " +
      Object.entries(per).map(([k, v]) => `${k} ${v}`).join(" · "));
  }

  /* Ogni ⓘ deve puntare a una voce viva del registro: un bottone che apre il vuoto e'
     peggio del paragrafo che ha sostituito. */
  if (K.info) {
    const chiavi = [...K.info.reg.keys()];
    ok(chiavi.length >= 8, `il registro degli ⓘ ha ${chiavi.length} voci`);
    const orfane = SRC_OK.map(s => "provenienza:" + s).filter(k => !K.info.reg.has(k));
    ok(orfane.length === 0,
      "ogni tipo di provenienza ha la sua scheda" + (orfane.length ? " — manca " + orfane.join(", ") : ""));
    ok(K.info.reg.has("provenienza:ignota"),
      "e c'e' anche la scheda per il caso 'nessuno l'ha dichiarata'");
  } else ok(false, "window.CRUSCOTTO.info non e' esposto");

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
     etichette sull'asse x che si sovrappone. La larghezza di un glifo monospazio a
     font-size 10 e' ~6.05px: **la stessa costante che usa la pagina** (TICKW) per
     dimensionare la gronda, quindi il controllo misura la stessa cosa che il disegno
     assume. Se la' cambia il corpo del testo, va cambiata anche qui, o il check
     smette di vedere le sovrapposizioni invece di segnalarle.
     Dal 17/08/2026 gli assi sono a corpo 10 e non piu' 8 (AXIS_FS in build_vita.py):
     a 8 px le etichette non si leggevano da telefono. */
  const GLYPH = 6.05;
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

  /* ------------------------------------- 2c. gli otto ottavi (chiesti il 17/08/2026)
     Sono barre nere alte 3px, una per ottavo della finestra, col numero della media
     sopra. Tre modi in cui si rompono senza che nessuno se ne accorga, e quindi tre
     controlli: sparire del tutto (una `frames:false` di troppo, o un renderer che non
     li chiama piu'), diventare nove perche' l'arrotondamento degli ottavi ha sbagliato
     un giro, e il numero che sborda dal suo ottavo e finisce addosso al vicino. */
  let framed = 0, tooMany = [], spill = [];
  for (const [n, t] of K.MOUNTED) {
    const svg = n.box._kids.find(c => c.tagName === "svg");
    if (!svg) continue;
    const kids = svg.descendants();
    const bars = kids.filter(c => c.tagName === "rect" && c.attrs.fill === "var(--ink)" &&
      parseFloat(c.attrs.height) === 3);
    if (!bars.length) continue;
    framed++;
    if (bars.length > 8) tooMany.push(`${t.title}: ${bars.length} ottavi`);
    /* Il numero puo' essere piu' largo del suo ottavo — la pagina se ne accorge e
       stampa una etichetta ogni due invece che una per ottavo. Quello che NON puo'
       succedere e' che due numeri disegnati si tocchino, o che uno esca dalla scheda:
       si misurano quelli, non la regola che dovrebbe averli evitati. */
    const [, , VW] = svg.attrs.viewBox.split(/\s+/).map(Number);
    const lab = kids.filter(c => c.tagName === "text" && c.attrs["font-weight"] === "700")
      .map(c => { const lw = (c.textContent || "").length * GLYPH;
        return { l:parseFloat(c.attrs.x) - lw / 2, r:parseFloat(c.attrs.x) + lw / 2,
                 y:parseFloat(c.attrs.y), s:c.textContent }; })
      .sort((a, b) => a.l - b.l);
    for (const q of lab) {
      if (q.l < -0.5 || q.r > VW + 0.5)
        spill.push(`${t.title}: "${q.s}" esce dalla scheda (${q.l.toFixed(0)}→${q.r.toFixed(0)} su ${VW})`);
    }
    for (let i = 1; i < lab.length; i++) {
      /* stessa riga = stessa altezza: due numeri a quote diverse non si toccano */
      if (Math.abs(lab[i].y - lab[i - 1].y) > 6) continue;
      if (lab[i].l < lab[i - 1].r + 1)
        spill.push(`${t.title}: "${lab[i - 1].s}" e "${lab[i].s}" si toccano`);
    }
  }
  ok(framed > 0, `gli otto ottavi sono disegnati (${framed} riquadri)`);
  ok(tooMany.length === 0, `mai piu' di otto ottavi per riquadro` +
    (tooMany.length ? ` — ${tooMany[0]}` : ""));
  ok(spill.length === 0, `i numeri degli ottavi non si toccano e non escono dalla scheda` +
    (spill.length ? ` — ${spill.length}, es. ${spill[0]}` : ""));

  /* --------------------------------------- 3. medie delle ultime due settimane */
  const N = D.n;
  let secs = 0, dist = 0, gain = 0;
  for (const [, , s, m, up] of D.acts) { secs += s; dist += m; gain += up; }
  const totalsHtml = ["totals-recovery", "totals-food"]
    .map(id => document.getElementById(id).innerHTML).join("");
  const it = v => v.toLocaleString("it-IT");
  for (const label of ["sonno", "HRV", "FC riposo", "allenamento", "chilometri",
                        "kcal", "proteine", "carboidrati", "fibre", "vegetale"]) {
    ok(totalsHtml.includes(`>${label}<`), `testata 14 giorni: ${label}`);
  }
  ok(totalsHtml.includes("vs prima"), "ogni media dichiara il confronto con i 14 giorni precedenti");
  ok(totalsHtml.includes('data-food="kcal"'), "le metriche alimentari aprono gli insight");
  const totals = document.getElementById("totals"), insightSheet = document.getElementById("sheet-in");
  try {
    totals.onclick({ target: { closest: () => ({ dataset: { food: "kcal" } }) } });
    ok(insightSheet.innerHTML.includes('class="target-track"'),
      "il popup delle medie mostra le barre colorate rispetto al target");
    ok(D.foodProfile && D.foodProfile.reference_kcal === 2600 &&
       insightSheet.innerHTML.includes("target"),
      "la barra delle kcal usa e dichiara il target del profilo");
    ok(insightSheet.innerHTML.includes("Alimenti · ultime due settimane"),
      "il popup elenca gli alimenti aggregati delle ultime due settimane");
    ok(insightSheet.innerHTML.includes("Burro di arachidi sgrassato in polvere") &&
       insightSheet.innerHTML.includes("Latte parzialmente scremato"),
      "l'inventario recente contiene peanut butter e latte corretti");
    ok(insightSheet.innerHTML.includes("osservati") && insightSheet.innerHTML.includes("ricostruiti"),
      "i conteggi separano consumi osservati e ricostruiti");
  } catch (e) { fails.push(`FAIL popup delle medie: ${e && e.stack || e}`); }
  ok(K.compare && K.compare.series.length >= 20,
    "il correlatore offre almeno venti serie selezionabili");
  ok(Array.from(document.getElementById("compare-plot").children).some(n => n.tagName === "svg"),
    "il correlatore disegna la nuvola di punti iniziale");
  ok(document.getElementById("compare-result").innerHTML.includes("r ="),
    "il correlatore dichiara r");
  ok(Math.round(gain / 1000) > 1000, `dislivello totale plausibile: ${it(Math.round(gain))} m`);

  /* --------------------------------- 4. ripiego tabellare + legende */
  const noTable = K.MOUNTED.filter(([n]) => !n.tbody.innerHTML.includes("<tr")).map(([, t]) => t.title);
  ok(noTable.length === 0, `ogni riquadro ha la tabella di ripiego` +
    (noTable.length ? ` — mancano: ${noTable.join(", ")}` : ""));

  /* La didascalia e la legenda del numero grande stanno sotto "dati", non in pagina
     (2026-08-14). E' facile che tornino su per sbaglio la prossima volta che qualcuno
     tocca tileNode, e sarebbe invisibile: il riquadro funzionerebbe lo stesso. */
  const noCap = K.MOUNTED.filter(([n, t]) => t.cap && !String(n.cap && n.cap.innerHTML)
    .includes(String(t.cap).slice(0, 24))).map(([, t]) => t.title);
  ok(noCap.length === 0, "ogni didascalia sta dentro il pannello «dati»" +
    (noCap.length ? ` — mancano: ${noCap.join(", ")}` : ""));
  const unitOut = K.MOUNTED.filter(([n, t]) => t.now && t.nowUnit &&
    String(n.now.innerHTML).includes(t.nowUnit)).map(([, t]) => t.title);
  ok(unitOut.length === 0, "nessun «media 7 gg» stampato accanto al numero grande" +
    (unitOut.length ? ` — ce l'hanno: ${unitOut.join(", ")}` : ""));

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
    /* i quattro dell'ossidazione dei grassi: due modelli e due misure, e la
       differenza deve restare scritta nel piede di ognuno */
    ["Grassi al minuto", /vale la sua variazione/i],
    ["Passo contro battito", /a parità di battito/i],
    ["Efficienza aerobica", /ma sale anche se/i],
    ["Il caldo", /non c'è niente da pesare/i],
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
    /* la nota di metodo sta sotto "dati" dal 14/8, non piu' sotto il grafico */
    ok(must.test(strip0(n.cap.innerHTML)),
      `"${title}" dichiara cosa è, dentro «dati» (cerco ${must})`);
    ok(!must.test(strip0(n.foot.innerHTML)),
      `"${title}" non rimette la nota di metodo sotto il grafico`);
    /* non tutti hanno un numero di testa: una nuvola come "Il caldo" e' una
       relazione, e un "valore di oggi" li' sarebbe l'ultima corsa spacciata per
       un livello. Il controllo vale su chi lo dichiara. */
    if (t.now) ok(/\S/.test(String(n.now.innerHTML)), `"${title}" ha il suo numero di testa`);
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
    /* Dal 16/08 l'annuncio non e' piu' un paragrafo da 1.139 caratteri ma una riga di
       chip accanto al grafico: l'intento del controllo qui sopra resta identico — un
       gesto che non si annuncia non esiste — e questo verifica che l'annuncio sia
       rimasto COMPATTO invece di riscivolare in prosa. */
    ok(/cx-gesti/.test(note), "i gesti sono annunciati come chip, accanto al disegno");
    /* Nessuna tesi deve tornare a vivere in due posti. Il 16/08 «Mangiare oggi non
       compra l'allenamento di domani» stava sia in CX_PRESETS sia nel rapporto del
       coach, con due corpi gia' diversi: qualcuno ne aveva riscritta una sola. Ora il
       coach DERIVA dai preset, e questo controllo verifica che la copia non torni. */
    if (K.coach && K.compare) {
      const html = K.coach.html();
      const titoli = (K.compare.presets || []).map(p => p.t).filter(Boolean);
      const doppi = titoli.filter(t => {
        let n = 0, i = 0;
        for (;;) { const j = html.indexOf(t, i); if (j < 0) break; n++; i = j + t.length; }
        return n > 1;
      });
      ok(doppi.length === 0,
        "nessuna tesi e' scritta due volte nel rapporto" + (doppi.length ? " — " + doppi.join(" · ") : ""));
    }
    ok(note.replace(/<[^>]*>/g, "").length <= 260,
      `l'intestazione della vista compatta e' una riga, non un saggio (${note.replace(/<[^>]*>/g, "").length} caratteri)`);
    ok(!!K.info && K.info.reg.has("compatta"),
      "e il metodo per intero e' dietro l'ⓘ, non perso");

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

  /* ------------------------------- 5c. il correlatore: completo, e sulle variazioni
     Due controlli che nascono da due bug veri.
     Il primo: l'elenco delle serie confrontabili era scritto a mano accanto al
     registro della ridgeline, e c'era rimasto indietro — heat strain, temperatura e
     momento metabolico non si potevano incrociare. Ora esce da RIDGE, e questo
     controllo tiene il fatto che nessuna corsia resti fuori dal menu.
     Il secondo: la correlazione si leggeva solo sui livelli, dove due serie che
     salgono nello stesso periodo escono associate anche se non c'entrano. Il modo
     "variazioni" deve esserci e deve dare un r DIVERSO da quello sui livelli, se no
     vuol dire che il differenziatore non sta differenziando niente. */
  const CMP = K.compare;
  ok(!!CMP, "window.CRUSCOTTO.compare esposto");
  if (CMP && K.compact) {
    const keys = new Set(CMP.series.map(s => s[0]));
    const missing = K.compact.series.map(l => l.key).filter(k => !keys.has(k));
    ok(missing.length === 0,
      `ogni corsia della ridgeline si puo' incrociare (${CMP.series.length} serie` +
      (missing.length ? `, mancano: ${missing.join(", ")}` : "") + ")");
    for (const k of ["heat", "temp", "mm"]) {
      ok(keys.has(k), `la serie "${k}" e' fra quelle confrontabili`);
    }
    ok(!!document.getElementById("compare-mode"), "il selettore livelli/variazioni e' in pagina");

    /* r sui livelli contro r sulle variazioni, su una coppia che di sicuro ha
       dell'andamento condiviso: fitness e fatica salgono e scendono insieme. */
    const sx = CMP.byKey.get("ctl"), sy = CMP.byKey.get("atl");
    if (sx && sy) {
      const rLv = CMP.pearson(CMP.pairsFor(sx, sy, 0, 0, 0, D.n - 1));
      const rD1 = CMP.pearson(CMP.pairsFor(sx, sy, 1, 0, 0, D.n - 1));
      ok(rLv !== null && rD1 !== null, "r calcolabile sia sui livelli sia sulle variazioni");
      if (rLv !== null && rD1 !== null) {
        ok(Math.abs(rLv - rD1) > 0.01,
          `livelli e variazioni danno r diversi (${rLv.toFixed(2)} contro ${rD1.toFixed(2)})`);
        ok(Math.abs(rLv) <= 1.0001 && Math.abs(rD1) <= 1.0001, "r resta dentro [-1, 1]");
      }
    }
  }

  /* --------------------------------- 5c-bis. le dieci coppie, e i due slot liberi
     Un preset che punta a una serie che non esiste piu' non rompe niente: sparisce
     dalla barra, in silenzio. Per questo si contano — se qualcuno toglie una serie
     dal registro (com'e' appena successo al VO2max) le pastiglie che la usavano
     devono farsi notare qui e non nel browser di Michele. */
  if (CMP && CMP.presets) {
    const dead = CMP.presets.filter(p => !CMP.byKey.has(p.x) || !CMP.byKey.has(p.y));
    ok(dead.length === 0, `le ${CMP.presets.length} coppie notevoli puntano a serie vive` +
      (dead.length ? ` — rotte: ${dead.map(p => p.t).join(", ")}` : ""));
    ok(CMP.presets.length === 10, `dieci coppie notevoli (${CMP.presets.length})`);
    const noWhy = CMP.presets.filter(p => !p.why || p.why.length < 60).map(p => p.t);
    ok(noWhy.length === 0, "ogni coppia dice perché guardarla" +
      (noWhy.length ? ` — mute: ${noWhy.join(", ")}` : ""));
    /* ogni tesi deve reggere il proprio r: si ricalcola qui, e se un preset e'
       diventato una frase falsa il check lo dice invece di lasciarla in pagina */
    const wrong = [];
    for (const p of CMP.presets) {
      const sx = CMP.byKey.get(p.x), sy = CMP.byKey.get(p.y);
      if (!sx || !sy) continue;
      const pts = CMP.pairsFor(sx, sy, { lv:0, d1:1, d7:7 }[p.mode] || 0, p.lag || 0, 0, D.n - 1);
      const r = CMP.pearson(pts);
      if (r === null || pts.length < 50) { wrong.push(`${p.t} (n ${pts.length})`); continue; }
      if (p.tag === "zero" && Math.abs(r) > 0.15) wrong.push(`${p.t} non è più uno zero (r ${r.toFixed(2)})`);
      if (p.tag !== "zero" && p.tag !== "poco n" && Math.abs(r) < 0.15)
        wrong.push(`${p.t} si è spento (r ${r.toFixed(2)})`);
    }
    ok(wrong.length === 0, "ogni coppia notevole regge ancora il proprio r" +
      (wrong.length ? ` — da riscrivere: ${wrong.join(" · ")}` : ""));
    /* La barra: dieci pastiglie nel DOM, ma solo TRE a schermo (17/08/2026 — dieci
       tesi in fila non si leggevano, si saltavano). Il controllo tiene tutte e due
       le meta' del patto: che le sette in piu' ci siano ancora, e che siano
       nascoste. Contate col `class`, perche' l'errore probabile qui e' esattamente
       che qualcuno tolga `cx-hid` "per vederle tutte" e riporti il muro di prima. */
    const chips = document.getElementById("compare-presets");
    ok(chips._kids.length === CMP.presets.length + 2,
      `la barra ha le dieci pastiglie, il bottone «altre» e lo slot libero (${chips._kids.length})`);
    const hid = chips._kids.filter(b => /(^| )cx-hid( |$)/.test(b.className || ""));
    ok(hid.length === CMP.presets.length - 3,
      `tre pastiglie a schermo, le altre ${hid.length} dietro un bottone`);
    const tog = chips._kids.find(b => /(^| )cx-tog( |$)/.test(b.className || ""));
    ok(!!tog && chips.attrs["data-open"] === "0", "il gruppo delle altre parte chiuso");
    if (tog) {
      tog.fire("click");
      const chips2 = document.getElementById("compare-presets");
      ok(chips2.attrs["data-open"] === "1", "e il bottone «altre» lo apre davvero");
      chips2._kids.find(b => /(^| )cx-tog( |$)/.test(b.className || "")).fire("click");
    }
    /* lo slot "questa e' mia": due, non venti, e devono sopravvivere alla visita */
    const add = document.getElementById("compare-presets")._kids.slice(-1)[0];
    add.fire("click"); add.fire("click"); add.fire("click");
    ok(CMP.mine.length === 2, `gli slot personali si fermano a due (${CMP.mine.length})`);
    ok(/cxmine/.test(Object.keys(LS).join(",")), "e sono salvati per la visita dopo");
  }

  /* ------------------------------------------- 5c-ter. l'opinione del coach
     Il rapporto non ha nemmeno un numero scritto a mano: se una serie sparisce,
     al posto della cifra deve uscire un trattino, mai "NaN" o "undefined" — che
     e' il modo tipico in cui un testo generato smette di dire la verita' senza
     smettere di sembrare autorevole. */
  const CO = K.coach;
  ok(!!CO, "window.CRUSCOTTO.coach esposto");
  if (CO) {
    let html = "";
    try { html = CO.html(); } catch (e) { fails.push("FAIL il rapporto solleva: " + (e && e.stack || e)); }
    const bare = String(html).replace(/<[^>]+>/g, "");
    ok(html.length > 2000, `il rapporto ha del testo (${(html.length / 1000).toFixed(1)} KB)`);
    ok(!/NaN|undefined/.test(html), "nessun NaN o undefined nel rapporto");
    for (const t of ["La tavola", "Il motore", "La gamba", "Cosa questo rapporto non sa"])
      ok(bare.includes(t), `il rapporto ha la sezione "${t}"`);
    ok(/r -?0,\d\d · n \d/.test(bare), "ogni associazione porta il suo r e il suo n");
    ok(/±40/.test(bare) && /ricostruit/i.test(bare) && /non è un parere medico/i.test(bare),
      "il rapporto dichiara i propri limiti (modello, ricostruito, non è un referto)");
    const lead = document.getElementById("coach-lead");
    ok(/\S/.test(String(lead.innerHTML)), "la scheda in cima porta già il verdetto");
    ok(!/NaN|undefined/.test(String(lead.innerHTML)), "e senza NaN");
    document.getElementById("coach-btn").fire("click");
    ok(document.getElementById("coach").classList.contains("on"),
      "il bottone apre il rapporto");
    K.coach.close();
  }

  /* --------------------------------------------- 5d. il diario, e la sua data
     Il giorno si indirizza per data di calendario, ma l'indice di calendario e'
     un offset in millisecondi da mezzanotte LOCALE: chi lo riconverte con
     `toISOString()` normalizza a UTC e, a est di Greenwich, torna indietro di un
     giorno. Il popup ha avuto per mesi esattamente questo difetto — da Roma
     apriva la cena di ieri — e questo check non poteva vederlo perche' la CI gira
     in UTC, dove l'offset e' zero. Qui il round-trip si prova a offset forzato. */
  const dia = K.diary;
  ok(!!dia, "window.CRUSCOTTO.diary esposto");
  if (dia) {
    const realDays = Object.keys(D.days || {})
      .filter(k => !k.startsWith("_") && typeof D.days[k] === "object");
    const trip = realDays.filter(k => {
      const i = dia.idxOf(k);
      return i !== null && dia.iso(i) === k;
    });
    ok(trip.length === realDays.length,
      `data → indice → data torna su tutti i ${realDays.length} giorni con del cibo` +
      (trip.length === realDays.length ? "" : ` (${realDays.length - trip.length} sfasati)`));

    /* la prova che conta: il giorno aperto dall'indice e' QUEL giorno, non il vicino */
    const wrong = realDays.slice(-40).filter(k => {
      openDay(dia.idxOf(k));
      const want = Math.round(D.days[k].tot.kcal);
      const m = sheetIn.innerHTML.match(/Tavola — ([\d.]+) kcal/);
      return !m || Math.abs(Number(m[1].replace(/\./g, "")) - want) > 1;
    });
    ok(wrong.length === 0, "il popup apre il giorno chiesto, non quello prima" +
      (wrong.length ? ` — sfasati: ${wrong.slice(0, 3).join(", ")}` : ""));

    /* Ogni riga di un pasto deve saper dire la propria quantita' — o con `f`+`qn`,
       e allora il diario sa anche risalire alla riga di food_log.csv da correggere,
       o con la stringa `q` gia' fatta, che e' il caso dei giorni Cronometer: quelli
       non vengono dal diario, quindi non hanno un food_id nostro e nel diario
       restano giustamente in sola lettura. Quello che NON deve esistere e' una riga
       che non ha ne' l'uno ne' l'altra: la quantita' sparirebbe dallo schermo. */
    const cat = D.foodCat || {};
    const mute = [], unknownId = new Set();
    let fromLog = 0, fromCron = 0;
    for (const k of realDays) {
      const meals = D.days[k].meals || {};
      for (const m of Object.keys(meals)) for (const it of meals[m]) {
        if (it.f !== undefined) { fromLog++; if (!cat[it.f]) unknownId.add(it.f); }
        else if (it.q !== undefined) fromCron++;
        else mute.push(`${k}/${m}/${it.n}`);
      }
    }
    ok(mute.length === 0, `ogni riga di pasto dichiara la propria quantita'` +
      (mute.length ? ` — mute: ${mute.slice(0, 3).join(", ")}` :
        ` (${fromLog} dal diario, ${fromCron} da Cronometer)`));
    ok(unknownId.size === 0,
      `ogni alimento del diario e' nel catalogo (${Object.keys(cat).length} voci)` +
      (unknownId.size ? ` — mancano ${[...unknownId].slice(0, 4).join(", ")}` : ""));
    ok(fromCron > 0, `i giorni Cronometer arrivano nel popup (${fromCron} righe misurate)`);

    /* Ricette e preset servivano ad annotare da qui, e da quando si annota da
       Mission Control non li apre piu' nessuno: nel payload non ci devono
       tornare. Un elenco che nessuno legge e' un elenco che va indietro senza
       che se ne accorga nessuno — e' la quarta regola di questa repo. */
    const morti = ["foodRec", "foodPre"].filter(k => D[k] !== undefined);
    ok(morti.length === 0,
      "il payload non porta piu' dati che nessuno legge"
      + (morti.length ? ` — ci sono ancora: ${morti.join(", ")}` : ""));

    /* apertura, e le righe che ne escono */
    const dayK = realDays[realDays.length - 1];
    const node = document.getElementById("diary-in");
    let threw = null;
    try { dia.open(dia.idxOf(dayK)); } catch (e) { threw = e; }
    ok(!threw, "il diario si apre senza sollevare" + (threw ? `: ${threw.stack || threw}` : ""));
    const rows = () => node.descendants().filter(n => /(^| )d-row( |$)/.test(n.className || ""));
    ok(rows().length > 0, `il diario elenca le righe del giorno (${rows().length})`);
    ok(node.descendants().some(n => (n.attrs.type === "date")),
      "il diario ha il selettore di data per sfogliare");

    /* ---- di sola lettura, e per davvero ------------------------------------
       Fino al 2026-08-14 qui si controllava che il diario sapesse SCRIVERE: la
       bozza locale quando il Worker non c'era, il preset che parte nel pasto
       scelto, la correzione che manda una row_key invece di una riga nuova.
       Quel lavoro si e' spostato in Mission Control, che e' dietro login: una
       pagina pubblica non e' il posto dove tenere una chiave che scrive nel
       repo. I controlli non spariscono, si girano sul fatto nuovo — se domani
       qualcuno rimettesse un campo scrivibile qui, questi lo prendono. */
    FETCHES.length = 0;
    dia.open(dia.idxOf(dayK));      /* riapre a rete azzerata: e' l'apertura che si misura */

    const editabili = node.descendants().filter(n =>
      (n.tagName === "input" && n.attrs.type !== "date") || n.tagName === "textarea");
    ok(editabili.length === 0,
      "nel diario non c'e' nessun campo scrivibile, a parte il calendario per sfogliare"
      + (editabili.length ? ` — trovati: ${editabili.map(n => n.attrs.type || n.tagName).join(", ")}` : ""));

    /* I bottoni che restano sono solo quelli per MUOVERSI dentro quello che gia'
       esiste: chiudere, il giorno prima, il giorno dopo, l'ultimo, e da 17/08/2026
       la finestra (giorno / 7 / 14). Nessuno che tolga o aggiunga una riga.
       Il controllo non e' stato allargato per far passare i tre nuovi: e' stato
       girato sul fatto nuovo, e resta esattamente lo stesso divieto — il diario si
       legge, si annota da Mission Control. Un bottone che si chiamasse «aggiungi» o
       «cancella» lo farebbe fallire come prima. */
    const bottoni = node.descendants().filter(n => n.tagName === "button");
    const ammessi = ["×", "‹ giorno prima", "giorno dopo ›", "ultimo giorno",
                     "il giorno", "7 giorni", "14 giorni"];
    const estranei = bottoni.filter(b => !ammessi.includes((b.textContent || "").trim()));
    ok(estranei.length === 0,
      `i bottoni del diario sono solo di navigazione (${bottoni.length})`
      + (estranei.length ? ` — estranei: ${estranei.map(b => b.textContent).join(", ")}` : ""));

    ok(FETCHES.length === 0,
      `aprire il diario non chiama piu' nessun Worker (${FETCHES.length} richieste)`);

    ok(typeof dia.write !== "function" && typeof dia.ops !== "function",
      "e la pagina non espone piu' nemmeno il modo di scrivere");

    const rinvio = node.descendants().find(n => /Mission Control/.test(n.textContent || ""));
    ok(!!rinvio, "il diario dice dove si annota adesso");

    /* La row_key resta nella forma che apply_diary_ops.py sa ritrovare: e' la
       stessa che Mission Control manda, e vederla uguale nei due posti e' quello
       che tiene onesto il confronto. */
    const conFood = dia.rows(dayK).rows.find(r => r.f);
    ok(conFood && conFood.id.split("|").length === 3,
      `le righe portano ancora la row_key a tre pezzi (${conFood ? conFood.id : "nessuna"})`);

    dia.close();
  }

  /* ------------------------------------------- 6. il 2022, che non e' piu' un buco
     Fino al 2026-08-13 qui si controllava che il buco lungo un anno FOSSE dichiarato:
     su Intervals il 2022 ha zero attivita', e disegnarlo pieno sarebbe stato mentire.
     Adesso le 394 attivita' di quell'anno sono tornate dall'export Strava
     (tools/strava_backfill.py) e il buco non c'e' piu'. Il controllo si gira, e resta
     un controllo: il 2022 deve avere attivita' vere, non deve piu' essere fra i buchi,
     e deve essere marcato come RICOSTRUITO — perche' il suo carico e' stimato da durata
     e cardio, non misurato. Se un giorno il backfill sparisse, il buco tornerebbe e
     dovrebbe tornare anche la sua banda: e' il caso che le due righe qui sotto tengono. */
  const d0 = new Date(D.d0 + "T00:00:00");
  /* campi locali, non `toISOString()`: vedi 5d */
  const iso = i => { const d = new Date(d0.getTime() + i * 86400000), p = v => String(v).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; };
  const spans = D.gaps.map(([a, b]) => `${iso(a)}→${iso(b)}`);
  const hole = D.gaps.find(([a, b]) => iso(a) < "2022-01-01" && iso(b) > "2022-12-31");
  const n2022 = D.acts.filter(a => iso(a[0]).startsWith("2022")).length;

  if (n2022 > 0) {
    ok(!hole, `il 2022 non e' piu' un buco: ${n2022} attivita' in pagina`);
    const rec = (D.recon || []).find(([a, b]) => iso(a) < "2022-01-01" && iso(b) > "2022-12-31");
    ok(!!rec, `e il 2022 e' marcato "carico ricostruito"` +
      (rec ? ` (${iso(rec[0])}→${iso(rec[1])})` : ` — recon: ${(D.recon || []).length} fasce`));
    const stim = D.acts.filter(a => iso(a[0]).startsWith("2022") && a[6]).length;
    ok(stim === n2022, `e tutte e ${n2022} portano il carico segnato come stimato (${stim})`);
  } else {
    ok(!!hole, `il buco che copre tutto il 2022 e' dichiarato` +
      (hole ? ` (${iso(hole[0])}→${iso(hole[1])})` : ` — gaps: ${spans.join(", ")}`));
  }
  ok(D.gaps.length >= 3, `${D.gaps.length} buchi ≥45 giorni dichiarati: ${spans.join(", ")}`);
}

/* -------------------------------------------------- 5. la tavolozza nel CSS */
/* Passi CHIARI dal 16/08/2026: la pagina ha preso il vestito della home e la scheda
   e' bianca, non piu' #211d16. I passi scuri di prima, nati per stagliarsi su una
   carta scura, sul bianco sbiadivano. Il controllo non e' stato tolto, e' stato
   girato sul fatto nuovo — e vale sempre la stessa cosa: questi quattro devono
   restare identici a `C` in tools/build_vita.py, che disegna i PNG. Sono un registro
   solo letto da due parti; se divergono, pagina e immagini dicono due colori diversi. */
/* Dal 17/08/2026 i primi tre sono i colori LETTERALI della home (io-blue, io-red,
   io-green portato a 4:1 perche' #34A853 sta a 2,8 e sotto 3:1 una linea da 2px non
   e' un oggetto grafico leggibile). Il quarto resta viola: il quarto colore della
   home e' il giallo, e il giallo li' e' sempre un FONDO dietro testo nero, mai un
   tratto — a 1,7:1 come linea non esisterebbe. */
const PAL = { "--s1": "#4285f4", "--s2": "#ea4335", "--s3": "#1e8e3e", "--s4": "#8430ce" };
for (const [k, v] of Object.entries(PAL)) {
  ok(new RegExp(k + ":\\s*" + v, "i").test(html), `CSS ${k} = ${v} (slot validato)`);
}
ok(/--paper:#ffffff/.test(html), "CSS --paper = #ffffff (il fondo su cui la tavolozza e' stata validata)");

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
/* --gold si chiama --accent dal 16/08/2026: sul fondo chiaro e' diventato il nero
   della home, e un token chiamato "gold" che contiene nero manda fuori strada. */
const paper = pick("--paper"), muted = pick("--muted"), accent = pick("--accent");
if (muted && paper) {
  const r = ratio(muted, paper);
  ok(r >= 4.5, `--muted ${muted} su ${paper}: ${r.toFixed(2)}:1 (minimo 4,5 per il testo piccolo)`);
}
ok(!!accent && !/--gold\s*:/.test(html),
  "l'accento si chiama --accent, e di --gold non e' rimasto niente in pagina");
if (accent && paper) {
  const r = ratio(accent, paper);
  ok(r >= 4.5, `--accent ${accent} su ${paper}: ${r.toFixed(2)}:1`);
  let worst = null;
  for (const [k, v] of Object.entries(PAL)) {
    const d = dE(accent, v);
    if (!worst || d < worst[1]) worst = [k, d];
  }
  ok(worst[1] >= 15,
    `--accent ${accent} contro gli slot dei grafici: peggiore ${worst[0]} ΔE ${worst[1].toFixed(1)} ` +
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
