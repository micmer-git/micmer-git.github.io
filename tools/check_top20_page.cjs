/* Smoke test jsdom per top-20/index.html — layout full-bleed (lab2, 2026-07-31).
 *
 * Stub di canvas (con controllo di coordinate finite), Image (le tile CARTO non
 * si scaricano: drawTiles salta i tile mai pronti), IntersectionObserver e rAF a
 * clock finto. Si fa girare l'animazione di TUTTE le schede fino in fondo e si
 * controllano: markup (testata, beat, contatori, legenda gara), geometria
 * finita, contatori che arrivano ai totali, beat visibile.
 *
 *   node tools/check_top20_page.cjs
 *
 * jsdom risale da qui a scratchpad/node_modules (il repo vive nello scratchpad
 * della sessione); altrove: npm i jsdom accanto al repo.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..");

const html = fs.readFileSync(path.join(ROOT, "top-20", "index.html"), "utf8");
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
  return {
    setTransform() {}, clearRect() {}, save() {}, restore() {}, clip() {},
    beginPath() {}, closePath() {}, rect() {}, fillRect() {},
    moveTo(x, y) { chk(x, y); }, lineTo(x, y) { chk(x, y); },
    arc(x, y, r) { chk(x, y); if (!Number.isFinite(r) || r < 0) bad.push("raggio " + r); },
    stroke() {}, fill() {}, drawImage() {}, fillText() {},
    measureText: t => ({ width: (t || "").length * 6.2 }),
    createRadialGradient: () => grad, createLinearGradient: () => grad,
    font: "", fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1,
    lineJoin: "", lineCap: "", textAlign: "", textBaseline: ""
  };
}
w.HTMLCanvasElement.prototype.getContext = function () { return this._g || (this._g = ctx()); };
Object.defineProperty(w.HTMLCanvasElement.prototype, "width", { writable: true, value: 800 });
Object.defineProperty(w.HTMLCanvasElement.prototype, "height", { writable: true, value: 600 });
w.Element.prototype.getBoundingClientRect = function () {
  return { width: 800, height: 600, top: 0, left: 0, right: 800, bottom: 600 };
};
w.Image = class { constructor() { this.crossOrigin = ""; } set src(v) { this._s = v; } set onload(f) {} };
w.matchMedia = () => ({ matches: false, addListener() {}, addEventListener() {} });
w.devicePixelRatio = 1;
const ios = [];
w.IntersectionObserver = class {
  constructor(cb) { this.cb = cb; this.targets = []; ios.push(this); }
  observe(t) { this.targets.push(t); } unobserve() {} disconnect() {}
};
let rafQ = [];
w.requestAnimationFrame = f => { rafQ.push(f); return rafQ.length; };
w.cancelAnimationFrame = () => {};

try { w.eval(data + "\n" + script); }
catch (e) { errors.push("EVAL: " + e.message); }

const d = w.document;
const slides = d.querySelectorAll(".story-slide");
if (slides.length !== 20) errors.push("story-slide: " + slides.length + " (attese 20)");
slides.forEach((s, i) => {
  for (const sel of [".cv2", ".shead h2", ".sbeat", ".sstats", ".stlink", ".replay2"])
    if (!s.querySelector(sel)) errors.push("scheda " + (i + 1) + " senza " + sel);
  if (/undefined|NaN/.test(s.innerHTML)) errors.push("scheda " + (i + 1) + " con undefined/NaN");
});
const race = d.querySelector(".story-slide.race");
if (!race) errors.push("manca la scheda race");
else if (race.querySelectorAll(".srace span").length !== 5)
  errors.push("legenda gara: " + race.querySelectorAll(".srace span").length + " voci");
if (d.getElementById("grid20").children.length !== 20)
  errors.push("indice: " + d.getElementById("grid20").children.length + " voci");

/* tutte in vista → start(); poi si spinge il clock oltre i 18 s di ogni scena */
for (const io of ios) if (io.targets.length) io.cb(io.targets.map(t => ({ target: t, isIntersecting: true })));
async function run() {
  try {
    /* il tick cappa dt a 50 ms: servono ~360 passi per i 18 s delle scene warp.
       I timer dello swap si fanno scattare DURANTE la corsa (a metà e verso la
       fine), così i frame successivi possono anche rispegnere il beat. */
    for (let ts = 0; ts <= 42000; ts += 100) {
      const q = rafQ; rafQ = [];
      for (const f of q) f(ts);
      if (ts === 12000 || ts === 30000) await new Promise(r => setTimeout(r, 420));
    }
  } catch (e) { errors.push("FRAME: " + (e.stack || e.message)); }

  const gavia = d.getElementById("gavia-mortirolo-2016");
  const kmTxt = gavia.querySelector(".s-km").textContent;
  const gainTxt = gavia.querySelector(".s-gain").textContent;
  const href = gavia.querySelector(".stlink").getAttribute("href") || "";
  if (href.indexOf("intervals.icu/activities/i62695131") < 0)
    errors.push("link attività Gavia: '" + href + "'");
  const beatTxt = gavia.querySelector(".sbeat").textContent;
  /* i valori si confrontano da numeri: il separatore delle migliaia dipende
     dall'ICU di node, non dalla pagina */
  const num = s => parseInt((s || "").replace(/\D/g, ""), 10);
  if (Math.abs(num(kmTxt) - 123) > 4) errors.push("contatore km Gavia a fine corsa: '" + kmTxt + "'");
  if (Math.abs(num(gainTxt) - 3212) > 120) errors.push("contatore D+ Gavia: '" + gainTxt + "'");
  if (!beatTxt || beatTxt.length < 10) errors.push("beat Gavia vuoto: '" + beatTxt + "'");
  /* a fine corsa il beat DEVE essersi spento: dal round 3 il testo vive ~2 s */
  if (gavia.querySelector(".sbeat").classList.contains("on"))
    errors.push("beat Gavia ancora acceso a fine corsa (doveva svanire)");
  const bologna = d.getElementById("bologna-2025");
  if (!bologna.querySelector(".sleg").textContent) errors.push("sleg Bologna vuoto (multi-tratto)");
  if (bad.length) errors.push("geometria: " + bad.length + " valori non finiti — " + bad.slice(0, 4).join(" · "));

  if (errors.length) { console.log("FAIL\n" + errors.join("\n")); process.exit(1); }
  console.log("OK — 20 schede full-bleed, geometria finita, contatori a totale, beat al centro, legenda gara");
}
run();
