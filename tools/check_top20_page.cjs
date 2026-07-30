/* Headless smoke test for top-20/index.html.
 *
 * There is no browser on this machine, so the page's own script is extracted and
 * run against a stub DOM plus a canvas context that records every coordinate it
 * is handed. It catches what matters: reference errors, NaN geometry, and a dot
 * that leaves the canvas. Run: node tools/.check_page.js
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");

const html = fs.readFileSync(path.join(ROOT, "top-20", "index.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/g).pop()
                   .replace(/^<script>/, "").replace(/<\/script>$/, "");
const data = fs.readFileSync(path.join(ROOT, "top-20", "_data.js"), "utf8")
               .replace(/^const /gm, "var ");

const W = 640, H = 480, PW = 640, PH = 46;
const bad = [];
let strokes = 0, arcs = 0;

function ctx(w, h, tag){
  const rec = (x, y, what) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) bad.push(tag+" "+what+" non finito: "+x+","+y);
  };
  return {
    _t:[1,0,0,1,0,0],
    setTransform(){}, clearRect(){}, beginPath(){}, closePath(){},
    moveTo(x,y){ rec(x,y,"moveTo"); }, lineTo(x,y){ rec(x,y,"lineTo"); },
    arc(x,y,r){ rec(x,y,"arc"); if(!Number.isFinite(r)||r<0) bad.push(tag+" raggio "+r); arcs++; },
    stroke(){ strokes++; }, fill(){},
    set globalAlpha(v){ if(!(v>=0&&v<=1)) bad.push(tag+" alpha "+v); },
    get globalAlpha(){ return 1; },
    set lineWidth(v){ if(!(v>0)) bad.push(tag+" lineWidth "+v); },
    get lineWidth(){ return 1; },
    strokeStyle:"", fillStyle:"", lineJoin:"", lineCap:""
  };
}

function el(tag){
  const e = {
    tagName:(tag||"div").toUpperCase(), className:"", id:"", style:{}, children:[],
    _html:"", _text:"", width:0, height:0,
    classList:{ _s:new Set(),
      add(c){this._s.add(c)}, remove(c){this._s.delete(c)},
      toggle(c,on){ on ? this._s.add(c) : this._s.delete(c) },
      contains(c){return this._s.has(c)} },
    set innerHTML(v){ this._html = v; }, get innerHTML(){ return this._html; },
    set textContent(v){ this._text = v; }, get textContent(){ return this._text; },
    appendChild(c){ this.children.push(c); return c; },
    insertBefore(c){ this.children.push(c); return c; },
    addEventListener(){}, removeEventListener(){},
    getBoundingClientRect(){ return this.tagName === "CANVAS" && this._prof
      ? {width:PW, height:PH} : {width:W, height:H}; },
    getContext(){ return this._ctx || (this._ctx = ctx(this.width, this.height, this.className)); },
    scrollTo(){}, scrollTop:0, scrollHeight:1000, clientHeight:500,
    querySelector(sel){ return this._q(sel)[0] || null; },
    querySelectorAll(sel){ return this._q(sel); },
    _q(sel){
      // enough of a selector engine for what the page asks of it
      if (sel === ".cv"){ const c = el("canvas"); return [c]; }
      if (sel === ".prof"){ const c = el("canvas"); c._prof = true; return [c]; }
      if (sel === ".legname" || sel === ".replay") return [el("p")];
      if (sel === ".beats li"){
        return [0,1,2,3,4].map(() => el("li"));
      }
      return [];
    }
  };
  return e;
}

const slides = [];
global.document = {
  createElement: el,
  getElementById(id){ return (global.document._by[id] || (global.document._by[id] = el("div"))); },
  querySelectorAll(sel){
    // le venti schede sono state iniettate in #story: sono loro le .slide
    return sel === ".slide" ? slides.concat(global.document._by["story"].children) : [];
  },
  _by:{}
};
global.matchMedia = () => ({matches:false});
global.devicePixelRatio = 2;
/* Il vero test è far scorrere l'animazione fino in fondo: rAF esegue subito, con
   un tetto di frame per non ricorrere all'infinito su venti scene in parallelo. */
let frames = 0;
global.requestAnimationFrame = (f) => { if (frames++ < 40000) f(); return 0; };
global.cancelAnimationFrame = () => {};
global.addEventListener = () => {};
global.setTimeout = (f) => 0;
global.clearTimeout = () => {};
const observed = [];
global.IntersectionObserver = class {
  constructor(cb){ this.cb = cb; ioList.push(this); }
  observe(t){ observed.push(t); }
};
const ioList = [];

// il page script chiude su document/window: eseguilo
eval(data + "\n" + script);

if (!ioList.length) { console.log("!! nessun IntersectionObserver registrato"); process.exit(1); }
const io = ioList[0];

// niente scene senza slide osservate: le sezioni iniettate finiscono in
// document._by.story.children
const story = global.document._by["story"];
const sections = story.children;
console.log("sezioni iniettate:", sections.length);
if (sections.length !== 20) { console.log("!! attese 20 schede"); process.exit(1); }

// ogni scheda deve avere titolo, kicker, 4 statistiche e 5 righe
let issues = 0;
sections.forEach((s, i) => {
  const h = s.innerHTML;
  for (const need of ["st-title", "st-kick", "beats", "replay", "class=\"cv\"", "class=\"prof\""]){
    if (h.indexOf(need) < 0){ console.log("!! scheda", i+1, "senza", need); issues++; }
  }
  const stats = (h.match(/class="stat"/g) || []).length;
  if (stats !== 4){ console.log("!! scheda", i+1, "ha", stats, "statistiche"); issues++; }
  const li = (h.match(/<li>/g) || []).length;
  if (li !== 5){ console.log("!! scheda", i+1, "ha", li, "righe"); issues++; }
  if (/undefined|NaN|null/.test(h)){ console.log("!! scheda", i+1, "contiene undefined/NaN/null"); issues++; }
});

// far girare l'animazione: entra in vista -> start(), poi avanza a mano
io.cb(observed.map(t => ({target:t, isIntersecting:true})));
console.log("start() su", observed.length, "slide senza eccezioni");

// l'indice deve avere 20 voci
const grid = global.document._by["grid20"];
console.log("voci d'indice:", grid.children.length);
if (grid.children.length !== 20) issues++;

console.log("frame disegnati:", frames, "· stroke:", strokes, "· arc:", arcs);
if (strokes < 20 * 100){ console.log("!! troppo pochi stroke: l'animazione non è girata"); issues++; }
if (bad.length){
  console.log("!! coordinate non valide:", bad.length);
  bad.slice(0,8).forEach(b => console.log("   ", b));
  process.exit(1);
}
if (issues){ console.log("!!", issues, "problemi di markup"); process.exit(1); }
console.log("\nOK — 20 schede, geometria finita, nessuna eccezione");
