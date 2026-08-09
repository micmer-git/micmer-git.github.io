#!/usr/bin/env python3
"""
build_vita.py — regenerate /vita, the hub over every tracker in this repo.

Reads each tracker's *own* published data (no separate database), so the hub can
never drift from the pages it points at:

  gazzaniga-orezzo/_data.js   RAW (bike) + RUN — 11 years of one climb
  diario-di-un-unno/index.html  the 39 monthly chapters and their stat strips
  sogni-di-un-unno/data.json    260 weeks of sleep

…plus `git log` for the "what changed" column. Everything is inlined into
vita/index.html, so the page is one self-contained file with no fetch at runtime.

    python tools/build_vita.py            # writes vita/index.html
    python tools/build_vita.py --check    # print what it found, write nothing

Run it after any tracker gets new data (the weekly workflow does).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# the tracker names contain → and accents; a cp1252 console must not kill the build
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# Accent per tracker. These are categorical slots 1–3 of the dataviz reference
# palette stepped for a dark surface; the trio passes lightness/chroma/CVD/
# normal-vision/contrast on all pairs. Every place a colour appears it sits next
# to the tracker's name, so identity is never carried by hue alone.
ACCENT = {
    "gazzaniga": "#d95926",   # ember — echoes the climb page
    "diario": "#199e70",      # aqua
    "sogni": "#3987e5",       # blue — echoes the night page
}

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def it(n, dec=0):
    """Italian number formatting: 48.496 / 1,2"""
    s = f"{n:,.{dec}f}"
    return s.replace(",", "~").replace(".", ",").replace("~", ".")


def mmss(secs):
    secs = int(round(secs))
    return f"{secs // 60}:{secs % 60:02d}"


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------- gazzaniga

def load_gazzaniga():
    txt = read("gazzaniga-orezzo/_data.js")

    def arr(name):
        m = re.search(r"const %s\s*=\s*(\[.*?\])\s*;" % name, txt, re.S)
        return json.loads(m.group(1)) if m else []

    raw, run = arr("RAW"), arr("RUN")
    if not raw:
        raise SystemExit("gazzaniga: RAW not found in _data.js")

    scale = 4.24 / 3.36                      # index.html scales the bike segment
    bike = [(date(r[0], r[1], r[2]), r[3] * scale) for r in raw if r[3] <= 1141]
    runs = [(date(r[0], r[1], r[2]), r[3]) for r in run]
    allx = sorted(bike + runs)

    gain = len(bike) * 282 + len(runs) * 284
    last = allx[-1][0]

    # ascents per month over the trailing 36 months — magnitude over time
    counts = {}
    for d, _ in allx:
        counts[(d.year, d.month)] = counts.get((d.year, d.month), 0) + 1
    months, y, mo = [], last.year, last.month
    for _ in range(36):
        months.append({"label": f"{MESI[mo - 1][:3]} {str(y)[2:]}", "v": counts.get((y, mo), 0)})
        y, mo = (y - 1, 12) if mo == 1 else (y, mo - 1)
    months.reverse()

    return {
        "key": "gazzaniga",
        "href": "../gazzaniga-orezzo/",
        "eyebrow": "la salita",
        "title": "Gazzaniga → Orezzo",
        "blurb": "Una sola salita, undici anni, ogni singola ripetizione — "
                 "in bici e di corsa — raccontata in dati.",
        "accent": ACCENT["gazzaniga"],
        "stats": [
            {"v": it(len(allx)), "l": "ascensioni"},
            {"v": it(gain / 8849, 1), "l": "volte l'Everest"},
            {"v": mmss(min(s for _, s in bike)), "l": "record in bici"},
        ],
        "chart": {"kind": "bars", "unit": "ascensioni",
                  "caption": "Ascensioni al mese, ultimi tre anni",
                  "points": months},
        "last": last.isoformat(),
    }


# ------------------------------------------------------------------ diario

def load_diario():
    txt = read("diario-di-un-unno/index.html")
    nums = re.findall(r'<div class="num">([^<]*)</div>', txt)
    labels = re.findall(r'<div class="label">([^<]*)</div>', txt)
    cover = dict(zip(labels, nums))

    periods = re.findall(r'<span class="month-num">([^<·—]+)', txt)
    strips = re.findall(r'<div class="stat-strip">([^<]*)', txt)

    def n(s):
        return int(s.replace(".", ""))

    points = []
    for period, strip in zip(periods, strips):
        m = re.search(r"([\d.]+)\s*km", strip)
        if m:
            points.append({"label": period.strip(), "v": n(m.group(1))})
    points.reverse()                          # the page lists newest first

    return {
        "key": "diario",
        "href": "../diario-di-un-unno/",
        "eyebrow": "la cronaca",
        "title": "Diario di un Unno",
        "blurb": f"{cover.get('Lune', '39')} capitoli mensili: ogni luna di "
                 "allenamento scritta come un romanzo in numeri.",
        "accent": ACCENT["diario"],
        "stats": [
            {"v": cover.get("Lune", "—"), "l": "lune"},
            {"v": cover.get("km", "—"), "l": "km"},
            {"v": cover.get("m saliti", "—"), "l": "m saliti"},
        ],
        "chart": {"kind": "bars", "unit": "km",
                  "caption": "Chilometri per capitolo mensile",
                  "points": points},
        "last": git_last("diario-di-un-unno"),
    }


# ------------------------------------------------------------------- sogni

def load_sogni():
    weeks = json.loads(read("sogni-di-un-unno/data.json"))
    dur = [w for w in weeks if isinstance(w.get("dur"), (int, float))]
    tail = dur[-104:]
    points = [{"label": w.get("date", ""), "v": round(w["dur"], 2)} for w in tail]
    recent = [w["dur"] for w in dur[-52:]]
    avg = sum(recent) / len(recent)
    years = sorted({w.get("year") for w in weeks if w.get("year")})

    return {
        "key": "sogni",
        "href": "../sogni-di-un-unno/",
        "eyebrow": "le notti",
        "title": "Sogni di un Unno",
        "blurb": f"{len(weeks)} settimane di sonno dal {years[0]} a oggi — "
                 "quando vado a letto, quanto dormo, e cosa ne è del carico.",
        "accent": ACCENT["sogni"],
        "stats": [
            {"v": it(len(weeks)), "l": "settimane"},
            {"v": it(avg, 1) + " h", "l": "media, ultimo anno"},
            {"v": str(years[-1] - years[0] + 1), "l": "anni tracciati"},
        ],
        "chart": {"kind": "line", "unit": "h",
                  "caption": "Ore di sonno per settimana, ultime due stagioni",
                  "points": points},
        "last": git_last("sogni-di-un-unno"),
    }


# --------------------------------------------------------------- git / meta

def git(*args):
    try:
        return subprocess.run(["git", "-C", ROOT, *args], capture_output=True,
                              text=True, encoding="utf-8", timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_last(path):
    out = git("log", "-1", "--format=%ad", "--date=short", "--", path)
    return out or date.today().isoformat()


TRACKED = {
    "gazzaniga-orezzo": ("gazzaniga", "Gazzaniga → Orezzo"),
    "diario-di-un-unno": ("diario", "Diario di un Unno"),
    "sogni-di-un-unno": ("sogni", "Sogni di un Unno"),
    "vita": (None, "Vita"),
}


def changelog(per_tracker=5, limit=14):
    """Recent commits per tracker, merged newest first.

    Taken per tracker rather than globally: one busy fortnight on the climb would
    otherwise push every other tracker off the page.
    """
    # \x1f, not \x1e: str.splitlines() treats RS as a line break and would eat the row
    sep = "\x1f"
    seen, entries = set(), []
    for path, (key, label) in TRACKED.items():
        if not key or not os.path.exists(os.path.join(ROOT, path)):
            continue
        out = git("log", f"-{per_tracker}", f"--format=%ad{sep}%s{sep}%H",
                  "--date=short", "--", path)
        for line in out.split("\n"):
            parts = line.split(sep)
            if len(parts) != 3:
                continue
            d, subject, sha = parts
            if sha in seen:
                for e in entries:                 # one commit can touch two trackers
                    if e["sha"] == sha and not any(w["key"] == key for w in e["who"]):
                        e["who"].append({"key": key, "label": label})
                continue
            seen.add(sha)
            entries.append({"sha": sha, "date": d, "text": subject,
                            "who": [{"key": key, "label": label}]})
    entries.sort(key=lambda e: e["date"], reverse=True)
    for e in entries:
        del e["sha"]
    return entries[:limit]


# ------------------------------------------------------------------- render

def build(trackers, log):
    payload = json.dumps({"trackers": trackers, "log": log},
                         ensure_ascii=False, separators=(",", ":"))
    built = date.today()
    totals = {
        "ascese": trackers[0]["stats"][0]["v"],
        "km": trackers[1]["stats"][1]["v"],
        "notti": trackers[2]["stats"][0]["v"],
    }
    return TEMPLATE.replace("__DATA__", payload) \
                   .replace("__BUILT__", f"{built.day} {MESI[built.month - 1]} {built.year}") \
                   .replace("__ASCESE__", totals["ascese"]) \
                   .replace("__KM__", totals["km"]) \
                   .replace("__NOTTI__", totals["notti"])


TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vita — Michele Merelli</title>
<meta name="description" content="Il quadro di comando: ogni tracker di Michele Merelli in un posto solo — la salita di Orezzo, il diario di allenamento, le notti.">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:url" content="https://micmer-git.github.io/vita/">
<meta property="og:title" content="Vita — Michele Merelli">
<meta property="og:description" content="Ogni tracker in un posto solo: la salita, la cronaca, le notti.">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;600&family=Cinzel:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#17150f; --paper:#211d16; --paper-2:#2a2519;
    --ink:#ece3cd; --ink-soft:#c6b997; --muted:#8a7d62;
    --gold:#c89a3f; --rule:rgba(200,154,63,.22);
    --grid:rgba(236,227,205,.10);
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    background:var(--bg); color:var(--ink);
    font-family:'EB Garamond',Georgia,serif; font-size:19px; line-height:1.65;
    max-width:940px; margin:0 auto; padding:56px 24px 100px;
    -webkit-text-size-adjust:100%;
  }
  body::before{
    content:""; position:fixed; inset:0; pointer-events:none; z-index:-1;
    background-image:
      radial-gradient(ellipse at 14% 16%,rgba(200,154,63,.09) 0,transparent 46%),
      radial-gradient(ellipse at 86% 80%,rgba(57,135,229,.06) 0,transparent 46%);
  }
  a{color:inherit}
  .mono{font-family:'IBM Plex Mono',ui-monospace,monospace}

  /* ---------- hero ---------- */
  header{text-align:center; margin-bottom:12px}
  .eyebrow{font-family:'IBM Plex Mono',monospace; font-size:.68rem; letter-spacing:.24em;
    text-transform:uppercase; color:var(--gold)}
  h1{font-family:'Cinzel',serif; font-size:clamp(3rem,13vw,5.2rem); font-weight:700;
    letter-spacing:.06em; line-height:1; margin:14px 0 6px}
  .sub{color:var(--ink-soft); font-style:italic; max-width:34em; margin:14px auto 0}
  .ornament{text-align:center; color:var(--gold); margin:34px 0 10px;
    font-size:1.1rem; letter-spacing:1.1em; opacity:.65}

  /* ---------- top numbers ---------- */
  .totals{display:flex; gap:34px; justify-content:center; flex-wrap:wrap; margin:26px 0 6px}
  .total{text-align:center}
  .total .n{font-family:'Cinzel',serif; font-size:1.75rem; font-weight:700; color:var(--gold);
    font-variant-numeric:tabular-nums}
  .total .l{font-family:'IBM Plex Mono',monospace; font-size:.62rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--muted); margin-top:3px}

  /* ---------- cards ---------- */
  .cards{display:grid; gap:22px; margin:44px 0 0}
  .card{
    position:relative; overflow:hidden;
    background:var(--paper); border:1px solid var(--rule); border-radius:8px;
    padding:26px 26px 18px; transition:border-color .18s,transform .18s,background .18s;
  }
  .card::before{content:""; position:absolute; inset:0 auto 0 0; width:3px; background:var(--a)}
  .card:hover,.card:focus-within{border-color:var(--a); background:var(--paper-2); transform:translateY(-2px)}
  @media(prefers-reduced-motion:reduce){.card{transition:none}.card:hover{transform:none}}
  .card-head{display:flex; align-items:baseline; gap:12px; flex-wrap:wrap}
  .card .kicker{font-family:'IBM Plex Mono',monospace; font-size:.64rem; letter-spacing:.2em;
    text-transform:uppercase; color:var(--a)}
  .card h2{font-family:'Cinzel',serif; font-size:1.65rem; font-weight:700; letter-spacing:.02em;
    margin:6px 0 0; width:100%}
  /* stretched link: the whole card is clickable, but the markup stays valid —
     the chart and its <details> sit on a higher layer and keep their own pointer */
  .card h2 a{text-decoration:none; color:inherit}
  .card h2 a::after{content:""; position:absolute; inset:0; z-index:1}
  .card h2 a:focus-visible{outline:2px solid var(--a); outline-offset:4px; border-radius:3px}
  .card figure,.card .figbox{position:relative; z-index:2}
  .card .blurb{color:var(--ink-soft); margin:8px 0 18px; max-width:46em}
  /* auto-fit rather than flex-wrap: the three stats stay on an even grid instead of
     leaving one orphan on a second line when the labels get long */
  .card .row{display:grid; grid-template-columns:repeat(auto-fit,minmax(104px,1fr));
    gap:14px 24px; margin-bottom:16px}
  .card .row .n{font-family:'Cinzel',serif; font-size:1.35rem; color:var(--ink);
    font-variant-numeric:tabular-nums}
  .card .row .l{font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.13em;
    text-transform:uppercase; color:var(--muted); margin-top:2px}
  .card figure{margin:0}
  .card figcaption{font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted); margin-bottom:6px}
  /* no fixed height: let the viewBox drive it, or the SVG letterboxes inside the card */
  .plot{width:100%; height:auto; display:block; touch-action:pan-y}
  .card-foot{display:flex; justify-content:space-between; align-items:center; gap:14px;
    border-top:1px solid var(--rule); margin-top:14px; padding-top:11px; flex-wrap:wrap}
  .stamp{font-family:'IBM Plex Mono',monospace; font-size:.62rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted)}
  .go{font-family:'IBM Plex Mono',monospace; font-size:.68rem; letter-spacing:.13em;
    text-transform:uppercase; color:var(--a); font-weight:600}

  /* ---------- changelog ---------- */
  section.log{margin-top:58px}
  h3{font-family:'Cinzel',serif; font-size:1.15rem; letter-spacing:.14em; text-transform:uppercase;
    color:var(--gold); text-align:center; font-weight:600}
  .log-sub{text-align:center; color:var(--muted); font-size:.9rem; font-style:italic; margin-top:4px}
  ol.entries{list-style:none; margin:26px 0 0; border-top:1px solid var(--rule)}
  ol.entries li{display:grid; grid-template-columns:6.5rem 1fr; gap:16px;
    padding:12px 2px; border-bottom:1px solid var(--rule)}
  ol.entries time{font-family:'IBM Plex Mono',monospace; font-size:.7rem; letter-spacing:.06em;
    color:var(--muted); padding-top:.35em}
  .what{color:var(--ink-soft); font-size:.95rem}
  .chips{margin-top:5px; display:flex; gap:7px; flex-wrap:wrap}
  .chip{font-family:'IBM Plex Mono',monospace; font-size:.58rem; letter-spacing:.1em;
    text-transform:uppercase; padding:2px 8px; border-radius:999px;
    border:1px solid currentColor; opacity:.92}

  /* ---------- cruscotto ---------- */
  /* Not a tracker card: the dashboard has no story of its own, it is the raw
     instrument panel behind all of them. It sits above the cards, styled as a band
     rather than a fourth card, so it cannot be mistaken for one. */
  .dash{display:block; margin:34px 0 0; padding:20px 24px; border-radius:8px;
    text-decoration:none; border:1px solid var(--rule); background:var(--paper);
    transition:border-color .18s,background .18s,transform .18s}
  .dash:hover{border-color:var(--gold); background:var(--paper-2); transform:translateY(-2px)}
  .dash:focus-visible{outline:2px solid var(--gold); outline-offset:3px}
  .dash .k{font-family:'IBM Plex Mono',monospace; font-size:.64rem; letter-spacing:.2em;
    text-transform:uppercase; color:var(--gold)}
  .dash h2{font-family:'Cinzel',serif; font-size:1.5rem; font-weight:700; margin:5px 0 0}
  .dash p{color:var(--ink-soft); font-size:.95rem; margin-top:6px; max-width:52em}
  .dash .go{font-family:'IBM Plex Mono',monospace; font-size:.66rem; letter-spacing:.13em;
    text-transform:uppercase; color:var(--gold); font-weight:600; margin-top:10px;
    display:inline-block}
  @media(prefers-reduced-motion:reduce){.dash{transition:none}.dash:hover{transform:none}}

  /* ---------- also / footer ---------- */
  .also{margin-top:46px; text-align:center}
  .also a{display:inline-block; margin:6px 7px; padding:7px 15px; border-radius:999px;
    border:1px solid var(--rule); color:var(--ink-soft); text-decoration:none; font-size:.86rem;
    transition:border-color .18s,color .18s}
  .also a:hover{border-color:var(--gold); color:var(--ink)}
  footer{margin-top:52px; text-align:center; color:var(--muted); font-size:.78rem;
    border-top:1px solid var(--rule); padding-top:20px}

  /* ---------- tooltip ---------- */
  .tip{position:fixed; z-index:9; pointer-events:none; opacity:0; transition:opacity .12s;
    background:#0e0d09; border:1px solid var(--rule); border-radius:5px; padding:6px 10px;
    font-family:'IBM Plex Mono',monospace; font-size:.68rem; color:var(--ink);
    white-space:nowrap; box-shadow:0 6px 18px rgba(0,0,0,.45)}
  .tip.on{opacity:1}
  .tip .v{color:var(--gold); font-weight:600}

  table.fallback{width:100%; border-collapse:collapse; margin-top:10px; font-size:.8rem}
  table.fallback th,table.fallback td{text-align:left; padding:3px 8px 3px 0;
    border-bottom:1px solid var(--rule); font-variant-numeric:tabular-nums}
  details.data{margin-top:12px}
  details.data[open] summary{color:var(--ink-soft); margin-bottom:4px}
  details.data summary{font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted); cursor:pointer}

  @media(max-width:560px){
    body{font-size:17px; padding:40px 16px 80px}
    .totals{gap:22px}
    ol.entries li{grid-template-columns:1fr; gap:4px}
    ol.entries time{padding-top:0}
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">micmer · quadro di comando</div>
  <h1>Vita</h1>
  <p class="sub">Tutto quello che misuro, in un posto solo. Ogni riquadro legge i
  dati della sua pagina: se là cambia qualcosa, qui si vede.</p>
</header>

<div class="totals">
  <div class="total"><div class="n">__ASCESE__</div><div class="l">ascensioni</div></div>
  <div class="total"><div class="n">__KM__</div><div class="l">km percorsi</div></div>
  <div class="total"><div class="n">__NOTTI__</div><div class="l">settimane di sonno</div></div>
</div>

<div class="ornament">✦ ✦ ✦</div>

<a class="dash" href="cruscotto/">
  <div class="k">tutti i numeri, senza racconto</div>
  <h2>Cruscotto</h2>
  <p>Ventidue grafici su un pannello solo: carico e forma dal 2019, sonno, HRV,
  frequenza a riposo, VO₂max, peso, volume e gli incroci fra una serie e l'altra.
  Presi da Intervals.icu e inseriti nella pagina, non caricati dal browser.</p>
  <span class="go">Apri il cruscotto →</span>
</a>

<main class="cards" id="cards"></main>

<section class="log">
  <h3>Cronaca</h3>
  <p class="log-sub">Cosa è cambiato, e dove.</p>
  <ol class="entries" id="entries"></ol>
</section>

<nav class="also">
  <a href="cruscotto/">Cruscotto</a>
  <a href="../top-20/">Venti giorni su 2.923</a>
  <a href="../bike-to-work/">Al lavoro in bici</a>
  <a href="../signore-dei-kj.html">Il Signore dei kJ</a>
  <a href="../signore-dei-kj-weekly.html">…settimanale</a>
  <a href="../viaggi/">Viaggi</a>
  <a href="../league-of-strava/">League of Strava</a>
  <a href="../">Profilo</a>
</nav>

<footer>
  Generato il __BUILT__ da <span class="mono">tools/build_vita.py</span>,
  leggendo i dati pubblicati di ogni tracker.
</footer>

<div class="tip" id="tip" role="status" aria-live="polite"></div>

<script>
const VITA = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const el = (t, a = {}) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const tip = document.getElementById("tip");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

function showTip(html, x, y) {
  tip.innerHTML = html; tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(Math.max(8, x - r.width / 2), innerWidth - r.width - 8) + "px";
  tip.style.top = Math.max(8, y - r.height - 12) + "px";
}
const hideTip = () => tip.classList.remove("on");

/* One measure, one series per plot — the card title names it, so no legend.
   Bars for counts, a line for a continuous weekly measure. */
function plot(box, chart, accent) {
  const pts = chart.points;
  if (!pts.length) return;
  const W = 600, H = 110, PAD_B = 14, PAD_T = 10;
  const max = Math.max(...pts.map(p => p.v)) || 1;
  const min = chart.kind === "line" ? Math.min(...pts.map(p => p.v)) : 0;
  const span = (max - min) || 1;
  const num = v => String(Math.round(v * 10) / 10).replace(".", ",");
  /* a line chart is not zero-based, so the rule at the foot is the minimum, not zero —
     say the range out loud rather than let the baseline imply one */
  const caption = chart.caption + (chart.kind === "line"
    ? ` · scala ${num(min)}–${num(max)} ${chart.unit}` : "");
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%",
    class: "plot", role: "img",
    "aria-label": caption + " — " + pts.length + " valori, da " +
      pts[0].label + " a " + pts[pts.length - 1].label });
  const x = i => (i / Math.max(1, pts.length - 1)) * (W - 8) + 4;
  const y = v => PAD_T + (1 - (v - min) / span) * (H - PAD_T - PAD_B);

  svg.appendChild(el("line", { x1: 0, y1: H - PAD_B, x2: W, y2: H - PAD_B,
    stroke: "var(--grid)", "stroke-width": 1 }));

  if (chart.kind === "bars") {
    const gap = 2, bw = Math.max(1.5, (W - 8) / pts.length - gap);
    pts.forEach((p, i) => {
      const h = Math.max(p.v > 0 ? 2 : 0, ((p.v - min) / span) * (H - PAD_T - PAD_B));
      if (!h) return;
      svg.appendChild(el("rect", { x: 4 + i * ((W - 8) / pts.length), y: H - PAD_B - h,
        width: bw, height: h, rx: Math.min(2, bw / 2), fill: accent }));
    });
  } else {
    const d = pts.map((p, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ");
    svg.appendChild(el("path", { d, fill: "none", stroke: accent, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" }));
  }

  /* hover layer: a marker that snaps to the nearest point */
  const dot = el("circle", { r: 4, fill: accent, stroke: "var(--paper)",
    "stroke-width": 2, opacity: 0 });
  svg.appendChild(dot);
  const hit = el("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" });
  svg.appendChild(hit);

  const move = ev => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(pts.length - 1,
      Math.round(((ev.clientX - r.left) / r.width * W - 4) / ((W - 8) / Math.max(1, pts.length - 1)))));
    const p = pts[i];
    const cx = chart.kind === "bars"
      ? 4 + i * ((W - 8) / pts.length) + ((W - 8) / pts.length - 2) / 2 : x(i);
    dot.setAttribute("cx", cx); dot.setAttribute("cy", y(p.v));
    dot.setAttribute("opacity", 1);
    showTip(`${p.label} · <span class="v">${String(p.v).replace(".", ",")}</span> ${chart.unit}`,
      r.left + cx / W * r.width, r.top + y(p.v) / H * r.height);
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { dot.setAttribute("opacity", 0); hideTip(); });

  const fig = document.createElement("figure");
  const cap = document.createElement("figcaption");
  cap.textContent = caption;
  fig.appendChild(cap); fig.appendChild(svg);

  /* non-visual fallback */
  const det = document.createElement("details");
  det.className = "data";
  det.innerHTML = `<summary>dati</summary><table class="fallback"><tbody>` +
    pts.map(p => `<tr><th scope="row">${p.label}</th><td>${String(p.v).replace(".", ",")} ${chart.unit}</td></tr>`).join("") +
    `</tbody></table>`;
  fig.appendChild(det);
  box.appendChild(fig);
}

const dateIt = s => {
  const M = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
  const [y, m, d] = s.split("-");
  return `${+d} ${M[+m - 1]} ${y}`;
};

const cards = document.getElementById("cards");
VITA.trackers.forEach(t => {
  const art = document.createElement("article");
  art.className = "card"; art.style.setProperty("--a", t.accent);
  art.innerHTML =
    `<div class="card-head"><span class="kicker">${t.eyebrow}</span>
       <h2><a href="${t.href}">${t.title}</a></h2></div>
     <p class="blurb">${t.blurb}</p>
     <div class="row">${t.stats.map(s =>
        `<div><div class="n">${s.v}</div><div class="l">${s.l}</div></div>`).join("")}</div>
     <div class="figbox"></div>
     <div class="card-foot"><span class="stamp">aggiornato ${dateIt(t.last)}</span>
     <span class="go">apri →</span></div>`;
  cards.appendChild(art);
  plot(art.querySelector(".figbox"), t.chart, t.accent);
});

const entries = document.getElementById("entries");
VITA.log.forEach(e => {
  const li = document.createElement("li");
  li.innerHTML = `<time datetime="${e.date}">${dateIt(e.date)}</time>
    <div><div class="what">${e.text}</div>
    <div class="chips">${e.who.map(w =>
      `<span class="chip" style="color:${VITA.trackers.find(t => t.key === w.key)?.accent || "var(--muted)"}">${w.label}</span>`
    ).join("")}</div></div>`;
  entries.appendChild(li);
});
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    trackers = [load_gazzaniga(), load_diario(), load_sogni()]
    log = changelog()

    for t in trackers:
        print(f"  {t['title']:<24} last {t['last']}  "
              f"{len(t['chart']['points'])} punti  "
              f"{' · '.join(s['v'] + ' ' + s['l'] for s in t['stats'])}")
    print(f"  changelog: {len(log)} voci")

    if args.check:
        return
    out_dir = os.path.join(ROOT, "vita")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build(trackers, log))
    print(f"\nwrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
