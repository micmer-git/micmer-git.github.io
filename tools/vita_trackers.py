#!/usr/bin/env python3
"""
vita_trackers.py — i tre tracker di questo repo, letti dai loro dati pubblicati.

Non genera niente: espone i loader e il changelog, e la pagina /vita li compone
insieme ai grafici (tools/build_vita.py). Ogni loader legge il dato *pubblicato*
dalla pagina del tracker, non un database a parte, cosi' l'hub non puo' andare
alla deriva rispetto alle pagine a cui punta:

  gazzaniga-orezzo/_data.js     RAW (bici) + RUN — 11 anni su una salita
  diario-di-un-unno/index.html  i 39 capitoli mensili e le loro strisce di dati
  sogni-di-un-unno/data.json    le settimane di sonno

…piu' `git log` per la colonna "cosa e' cambiato".

    python tools/vita_trackers.py --check    # stampa cosa ha trovato
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
    "spostamenti": "#8b7cf6", # violet — geography
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


# ----------------------------------------------------------- spostamenti

def load_spostamenti():
    data = json.loads(read("vita/spostamenti/data/travel.json"))
    totals = data["totals"]
    return {
        "key": "spostamenti",
        "href": "spostamenti/",
        "eyebrow": "la geografia",
        "title": "Spostamenti",
        "blurb": "Dodici anni di città, voli, strada e luoghi che ritornano — "
                 "su un globo da scorrere.",
        "accent": ACCENT["spostamenti"],
        "stats": [
            {"v": it(totals["trips"]), "l": "viaggi"},
            {"v": it(totals["countries"]), "l": "paesi esteri"},
            {"v": it(totals["co2T"], 1) + " t", "l": "CO₂e voli"},
        ],
        "chart": {"kind": "none", "unit": "", "caption": "", "points": []},
        "last": data["meta"]["built"],
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
    "vita/spostamenti": ("spostamenti", "Spostamenti"),
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



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="riporta e basta")
    ap.parse_args()
    trackers = [load_gazzaniga(), load_diario(), load_sogni(), load_spostamenti()]
    for t in trackers:
        print(f"  {t['title']:<24} last {t['last']}  "
              f"{len(t['chart']['points'])} punti  "
              f"{' · '.join(s['v'] + ' ' + s['l'] for s in t['stats'])}")
    print(f"  changelog: {len(changelog())} voci")


if __name__ == "__main__":
    main()
