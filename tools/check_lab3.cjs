/* Smoke test jsdom per top-20/lab3.html — 100 varianti in 10 temi (round 3, 2026-08-05).
 *
 * Stub di canvas (con controllo di coordinate finite), Image (le tile CARTO non si
 * scaricano), IntersectionObserver e rAF a clock finto. Fa girare TUTTE le schede
 * dall'inizio alla fine e controlla: markup (schede, chip, stelle, nav dei temi),
 * geometria finita, nessuna eccezione dentro i draw, voto e blob di copia.
 *
 *   node tools/check_lab3.cjs
 *
 * jsdom risale da qui a ../node_modules o allo scratchpad; altrove: npm i jsdom.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..");

const html = fs.readFileSync(path.join(ROOT, "top-20", "lab3.html"), "utf8");
const data = fs.readFileSync(path.join(ROOT, "top-20", "_data.js"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/)[1];

const dom = new JSDOM(html.replace(/<script[\s\S]*?<\/script>/g, ""),
  { url: "https://example.org/", runScripts: "outside-only" });
const w = dom.window, errors = [], bad = [];

const fin = (tag) => (x, y) => {
  if (!Number.isFinite(x) || !Number.isFinite(y)) bad.push(tag + ": " + x + "," + y);
};
function ctx() {
  const chk = fin("geom");
  const grad = { addColorStop() {} };
  const self = {
    canvas: null, _n: 0,
    setTransform() {}, transform() {}, translate(x, y) { chk(x, y); }, rotate() {}, scale() {},
    clearRect() {}, save() {}, restore() {}, clip() {},
    beginPath() {}, closePath() {}, rect() {},
    fillRect(x, y, w2, h2) { chk(x, y); chk(w2, h2); },
    strokeRect(x, y, w2, h2) { chk(x, y); chk(w2, h2); },
    moveTo(x, y) { self._n++; chk(x, y); }, lineTo(x, y) { self._n++; chk(x, y); },
    quadraticCurveTo(a, b, c, d) { chk(a, b); chk(c, d); },
    arc(x, y, r) { self._n++; chk(x, y); if (!Number.isFinite(r) || r < 0) bad.push("raggio " + r); },
    stroke() {}, fill() {}, setLineDash() {},
    drawImage() { self._n += 40; }, fillText() { self._n++; },
    measureText: t => ({ width: String(t || "").length * 6.2 }),
    createRadialGradient: () => grad, createLinearGradient: () => grad,
    getImageData: (x, y, w2, h2) => ({ width: w2, height: h2, data: new Uint8ClampedArray(w2 * h2 * 4) }),
    putImageData() {},
    font: "", fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1,
    globalCompositeOperation: "", shadowColor: "", shadowBlur: 0,
    lineJoin: "", lineCap: "", textAlign: "", textBaseline: ""
  };
  return self;
}
w.HTMLCanvasElement.prototype.getContext = function () {
  if (!this._g) { this._g = ctx(); this._g.canvas = this; }
  return this._g;
};
Object.defineProperty(w.HTMLCanvasElement.prototype, "width", { writable: true, value: 800 });
Object.defineProperty(w.HTMLCanvasElement.prototype, "height", { writable: true, value: 600 });
w.Element.prototype.getBoundingClientRect = function () {
  return { width: 400, height: 300, top: 100, left: 0, right: 400, bottom: 400 };
};
w.Image = class { constructor() { this.crossOrigin = ""; } set src(v) { this._s = v; } set onload(f) {} };
w.matchMedia = () => ({ matches: false, addListener() {}, addEventListener() {} });
w.devicePixelRatio = 1;
w.innerHeight = 900;
const warns = [];
w.console = Object.assign({}, console, { warn: (...a) => warns.push(a.join(" ")) });

const ios = [];
w.IntersectionObserver = class {
  constructor(cb) { this.cb = cb; this.targets = []; ios.push(this); }
  observe(t) { this.targets.push(t); } unobserve() {} disconnect() {}
};
let rafQ = [];
w.requestAnimationFrame = f => { rafQ.push(f); return rafQ.length; };
w.cancelAnimationFrame = () => {};

try { w.eval(data + "\n" + script); }
catch (e) { errors.push("EVAL: " + e.message + "\n" + e.stack); }

const d = w.document;

/* --- markup --- */
const cards = d.querySelectorAll(".card");
if (cards.length !== 101) errors.push("schede: " + cards.length + " (attese 101 = base + 100)");
const votable = d.querySelectorAll(".stbtn");
if (votable.length !== 100) errors.push("stelle: " + votable.length + " (attese 100)");
const chips = d.querySelectorAll(".chip");
if (chips.length !== 1100) errors.push("chip: " + chips.length + " (attesi 1100 = 100 × 11)");
const navs = d.querySelectorAll("#tnav a");
if (navs.length !== 10) errors.push("temi in nav: " + navs.length + " (attesi 10)");
const fams = d.querySelectorAll("section.fam");
if (fams.length !== 11) errors.push("sezioni: " + fams.length + " (attese 11)");
if (!d.getElementById("freetxt")) errors.push("manca la casella libera del prossimo round");
cards.forEach(c => {
  if (!c.querySelector("canvas.cv")) errors.push(c.id + ": manca il canvas");
  if (!c.querySelector(".meta h3")) errors.push(c.id + ": manca il titolo");
});
/* ogni tema deve avere esattamente 10 varianti votabili */
const perFam = {};
cards.forEach(c => {
  const id = (c.dataset.id || "").slice(0, 2);
  if (id) perFam[id] = (perFam[id] || 0) + 1;
});
for (const k of ["MA", "RI", "VO", "MO", "AR", "MT", "ST", "PU", "SC", "LE"]) {
  if (perFam[k] !== 10) errors.push("tema " + k + ": " + (perFam[k] || 0) + " varianti (attese 10)");
}

/* --- animazione: tutte le schede, dall'inizio alla fine --- */
ios.forEach(o => o.cb(o.targets.map(t => ({ target: t, isIntersecting: true })), o));
let ts = 0;
for (let k = 0; k < 620; k++) {
  const q = rafQ; rafQ = [];
  ts += 50;                       /* dt è cappato a 50 ms per frame */
  q.forEach(f => { try { f(ts); } catch (e) { errors.push("rAF: " + e.message); } });
  if (!q.length) break;
}
if (warns.length) errors.push("draw in errore → " + warns.slice(0, 6).join(" | "));
const mute = [];
cards.forEach(c => {
  const g = c.querySelector("canvas.cv")._g;
  if (!g || g._n < 200) mute.push(c.dataset.id + "(" + (g ? g._n : "nessun contesto") + ")");
});
if (mute.length) errors.push("schede che non disegnano: " + mute.join(", "));
if (bad.length) errors.push("geometria non finita (" + bad.length + "): " + bad.slice(0, 5).join(" | "));

/* --- voto, stella, blob --- */
const c1 = d.getElementById("ma01");
c1.querySelectorAll(".chip")[9].dispatchEvent(new w.Event("click", { bubbles: true }));
if (!c1.querySelector(".chip.sel")) errors.push("il chip non si seleziona");
c1.querySelector(".stbtn").dispatchEvent(new w.Event("click", { bubbles: true }));
if (!c1.classList.contains("star")) errors.push("la stella non marca la scheda");
const prog = d.getElementById("prog").textContent;
if (!/1\s*\/\s*100/.test(prog.replace(/\s+/g, " "))) errors.push("progresso: «" + prog + "»");
const navB = d.querySelector('#tnav b[data-fam="mano"]');
if (navB && navB.textContent !== "1/10") errors.push("contatore del tema: " + navB.textContent);
d.getElementById("copy").dispatchEvent(new w.Event("click", { bubbles: true }));
const blob = d.getElementById("outbox").value;
if (!/VOTI LAB3/.test(blob)) errors.push("blob senza intestazione");
if (!/★ MA01/.test(blob)) errors.push("blob senza la preferita");
if (!/PREFERITE: MA01/.test(blob)) errors.push("blob senza il riepilogo preferite");

if (errors.length) { console.error("✗ lab3\n- " + errors.join("\n- ")); process.exit(1); }
console.log("✓ lab3: 101 schede, 10 temi × 10, " + Math.round(ts / 1000) + "s di animazione simulata, voto e blob ok");
