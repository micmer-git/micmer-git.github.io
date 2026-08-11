#!/usr/bin/env python3
"""
build_vita.py — build /vita: i tre tracker in cima, e sotto una colonna con ogni
serie misurabile della vita di Michele — carico, sonno, HRV, corpo, volume, tavola.

I grafici stanno **uno sopra l'altro**, non a griglia: condividono l'asse x, quindi
l'occhio puo' scendere lungo la pagina confrontando lo stesso mese fra serie diverse.
E' l'unica cosa che una griglia di riquadri non lascia fare, e il motivo per cui la
pagina e' fatta cosi'.

Where the other tools in here read a *published page* and keep the hub honest against
it, this one goes straight to the source: it pulls the whole wellness history and the
whole activity list from Intervals.icu, packs them into one compact payload, and
inlines that into a single self-contained HTML file. No runtime fetch, no API key on
the client, no dependency — the page is a flat file that happens to hold eleven years.

What the data actually is (measured 2026-08-09, not assumed — see --check):

  * wellness runs 2015-03-29 → today, 4.152 days, and *every* day carries ctl/atl.
  * but the load feeding them only becomes real in 2019: 2015-2018 activities came in
    from Strava without HR or power, so their training load is zero. Load charts
    therefore start where the load does, not where the record does.
  * **2022 is missing entirely** — no activities at all. CTL decays to zero across it,
    which reads like a year off the bike and is not what happened: it is a hole in the
    archive. Every long no-activity run is shaded and labelled rather than drawn
    through, because a smooth line across a gap is a lie a chart tells very well.
  * sleep, sleepScore, HRV, resting HR and steps start in **2025** (the watch), VO2max
    likewise. Weight is 65 points and body fat 53 over the same window — sparse enough
    that they are drawn as clouds with a fitted trend, never as a line.

Each tile states its own window, so no tile can imply coverage it does not have.

Usage
-----
    set INTERVALS_API_KEY=...          (or --api-key, or tools/.intervals_key)

    python tools/build_vita.py --check      # report coverage, write nothing
    python tools/build_vita.py              # pull + rebuild the page
    python tools/build_vita.py --offline    # rebuild from the cached pull

The raw pull is cached to `tools/.cruscotto_cache.json` (gitignored) so re-rendering
while working on the page costs nothing and cannot be rate-limited. `--dry-run` does
everything except write. The previous page is copied to `index.html.bak` first.
"""
import argparse
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from sync_intervals import api, get_api_key  # noqa: E402  (same folder, shared auth)
import vita_trackers  # noqa: E402  (i tre tracker in cima alla pagina)

CACHE = os.path.join(HERE, ".cruscotto_cache.json")
OUT_DIR = os.path.join(ROOT, "vita")
OUT = os.path.join(OUT_DIR, "index.html")
REPORT = os.path.join(HERE, "vita_tests.md")
FOOD_DATA = os.path.join(OUT_DIR, "cibo", "data")

# Aggregati giornalieri di alimentazione, esportati da ~/health-log con
# `scripts/build_nutrition_series.py --export`. Vive qui perche' la GitHub Action
# non ha accesso a quella repo — e perche' quello che esce sono **solo** i totali
# del giorno: il diario dei pasti, con dentro dove e con chi ha mangiato, resta
# privato di la'.
NUTRITION = os.path.join(FOOD_DATA, "nutrition.csv")
# Dettaglio giorno per giorno per il popup: pasti, alimenti, % dei fabbisogni.
# Stesso esportatore, flag `--export-days`.
DAYS = os.path.join(FOOD_DATA, "days.json")
# Il MODELLO della flora (scripts/microbiome_model.py). Non e' una misura: nessuno
# ha sequenziato niente, e la pagina lo dice a caratteri grandi.
MICROBES = os.path.join(FOOD_DATA, "microbiome.csv")
# Matrice alimento x genere: il modello della flora letto al contrario, cioe'
# quali cibi davvero mangiati muovono quali generi. Non e' una misura in piu',
# e' il cablaggio del modello reso visibile.
FLORA_FOODS = os.path.join(FOOD_DATA, "flora_foods.csv")

# The athlete. Intervals.icu also accepts "0" for "whoever owns the key", but the
# explicit id keeps the CI logs readable when a key is swapped.
ATHLETE = os.environ.get("INTERVALS_ATHLETE_ID", "i302515")
OLDEST = "2012-01-01"

# Categorical slots 1-4 of the dataviz reference palette, dark steps. Validated as a
# set against this page's card surface (#211d16), not against the reference surface:
# adjacent worst CVD dE 8.4, normal-vision 19.3, all four >= 3:1 on the card. The
# scatter that needs all-pairs separation carries two of them only (blue/orange,
# dE 31.8) — four hues cannot clear the all-pairs floor and yellow beside orange is
# exactly the pair that fails. Colour never carries identity alone: every series is
# named in its own title or legend.
C = {
    "blue": "#3987e5",
    "orange": "#d95926",
    "aqua": "#199e70",
    "yellow": "#c98500",
    "red": "#e66767",       # the negative arm of Forma — a diverging pole, not a series
}

# Sport buckets. Six raw types collapse to four so a stack never needs a fifth hue.
SPORTS = ["Bici", "Corsa", "Nuoto", "Altro"]
SPORT_OF = {
    "Ride": 0, "VirtualRide": 0, "GravelRide": 0, "MountainBikeRide": 0, "EBikeRide": 0,
    "Run": 1, "TrailRun": 1, "VirtualRun": 1,
    "Swim": 2, "OpenWaterSwim": 2,
}


# --------------------------------------------------------------------- fetching

def pull(key, use_cache=False):
    """Wellness + activities, whole history. Cached raw so re-renders are free."""
    if use_cache:
        if not os.path.exists(CACHE):
            sys.exit(f"--offline but no cache at {CACHE} — run once without it.")
        with open(CACHE, encoding="utf-8") as f:
            raw = json.load(f)
        print(f"  cache  {raw['pulled']}  "
              f"{len(raw['wellness'])} giorni · {len(raw['activities'])} attività")
        return raw

    today = date.today().isoformat()
    print(f"  GET wellness   {OLDEST} → {today}")
    wellness = api(f"athlete/{ATHLETE}/wellness?oldest={OLDEST}&newest={today}", key)
    print(f"  GET activities {OLDEST} → {today}")
    acts = api(f"athlete/{ATHLETE}/activities?oldest={OLDEST}&newest={today}", key)
    if not wellness or not acts:
        sys.exit("Intervals.icu returned nothing — check the API key and try again.")

    raw = {"pulled": today, "wellness": wellness, "activities": acts}
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    print(f"  cached {len(wellness)} giorni · {len(acts)} attività → "
          f"{os.path.basename(CACHE)}")
    return raw


# ---------------------------------------------------------------- shaping

def r1(v):
    return None if v is None else round(float(v), 1)


def ri(v):
    return None if v is None else int(round(float(v)))


def build_payload(raw):
    """Daily arrays on one shared index, plus the activity list. Nothing is smoothed
    or filled here — the page does its own rolling means so the range switch can
    recompute them over whatever window is on screen."""
    well = sorted(raw["wellness"], key=lambda r: r["id"])
    acts = raw["activities"]

    d0 = datetime.strptime(well[0]["id"], "%Y-%m-%d").date()
    dN = datetime.strptime(well[-1]["id"], "%Y-%m-%d").date()
    n = (dN - d0).days + 1
    idx = {}
    for r in well:
        d = datetime.strptime(r["id"], "%Y-%m-%d").date()
        idx[r["id"]] = (d - d0).days

    def col(name, conv):
        out = [None] * n
        for r in well:
            i = idx[r["id"]]
            v = r.get(name)
            if v is not None:
                out[i] = conv(v)
        return out

    ctl = col("ctl", r1)
    atl = col("atl", r1)
    load = col("ctlLoad", ri)
    sleep = col("sleepSecs", lambda v: int(round(v / 60.0)))   # minutes
    score = col("sleepScore", ri)
    hrv = col("hrv", r1)
    rhr = col("restingHR", ri)
    steps = col("steps", ri)
    vo2 = col("vo2max", r1)
    weight = col("weight", r1)
    bodyfat = col("bodyFat", r1)

    # ctl/atl exist for every single day by construction (Intervals fills the calendar),
    # so "first non-null" would say 2015 for a series that is flat zero until 2019.
    # The honest start is where the load becomes sustained: the first day whose next
    # 28 days carry more than a token amount of it.
    load_i0 = 0
    for i in range(n - 28):
        if sum(load[j] or 0 for j in range(i, i + 28)) > 100:
            load_i0 = i
            break

    # activities -> [dayIdx, sport, movingSecs, metres, gainMetres, load]
    # piu' una lista parallela di nomi/id: il popup della giornata apre le attivita'
    # con il loro nome vero e il link a Intervals, e "Morning Ride" non e' un nome.
    arows, anames, act_days = [], [], set()
    for a in acts:
        sd = (a.get("start_date_local") or "")[:10]
        if not sd or sd not in idx:
            # an activity outside the wellness calendar cannot be placed on the axis
            continue
        i = idx[sd]
        arows.append([
            i,
            SPORT_OF.get(a.get("type") or "", 3),
            int(a.get("moving_time") or 0),
            int(round(a.get("distance") or 0)),
            int(round(a.get("total_elevation_gain") or 0)),
            int(round(a.get("icu_training_load") or 0)),
        ])
        anames.append([a.get("name") or "", a.get("id") or "",
                       a.get("strava_id") or ""])
        act_days.add(i)
    order = sorted(range(len(arows)), key=lambda j: arows[j])
    arows = [arows[j] for j in order]
    anames = [anames[j] for j in order]

    # Long runs with no activity at all. 2022 is the big one; the early years have
    # their own. Drawn as shaded "nessun dato" bands instead of being interpolated
    # across, because CTL decaying through a hole looks exactly like detraining.
    gaps, run_start = [], None
    for i in range(n):
        if i in act_days:
            if run_start is not None and i - run_start >= 45:
                gaps.append([run_start, i - 1])
            run_start = None
        elif run_start is None:
            run_start = i
    if run_start is not None and n - run_start >= 45:
        gaps.append([run_start, n - 1])

    def first(a):
        for i, v in enumerate(a):
            if v is not None:
                return i
        return None

    # ---- alimentazione: aggregati giornalieri, se il CSV c'e' ----------------
    # Le colonne diventano array sullo stesso indice giornaliero di tutto il resto,
    # cosi' una serie di cibo e una di allenamento si possono incrociare senza
    # riallineare niente. Se il file manca, i riquadri del cibo semplicemente non
    # compaiono: meglio nessun grafico che un grafico vuoto.
    nutri, nutri_first, nutri_last = {}, {}, {}
    if os.path.exists(NUTRITION):
        import csv as _csv
        with open(NUTRITION, encoding="utf-8", newline="") as fh:
            nrows = [r for r in _csv.DictReader(fh) if r.get("date")]
        cols = [c for c in (nrows[0].keys() if nrows else []) if c != "date"]
        for c in cols:
            nutri[c] = [None] * n
        for r in nrows:
            i = idx.get(r["date"])
            if i is None:
                continue                       # giorno fuori dal calendario wellness
            for c in cols:
                v = r.get(c)
                if v not in (None, ""):
                    nutri[c][i] = round(float(v), 2)
        # Il diario copre 92 giorni su 4.152: tenere array interi vorrebbe dire
        # spedire ~87.000 `null` (la pagina passava da 322 a 761 KB). Ogni serie
        # esce come blocco contiguo {i0, v} e la pagina la ridistende al volo.
        for c in cols:
            a = nutri[c]
            i0 = next((i for i, v in enumerate(a) if v is not None), None)
            if i0 is None:
                nutri[c] = None
                continue
            i1 = len(a) - 1 - next(i for i, v in enumerate(reversed(a)) if v is not None)
            nutri[c] = {"i0": i0, "v": a[i0:i1 + 1]}
            nutri_first[c] = i0
            nutri_last[c] = i1
        nutri = {c: b for c, b in nutri.items() if b}
        print(f"  alimentazione: {len(nrows)} giorni, {len(nutri)} serie")
    else:
        print(f"  alimentazione: nessun {os.path.basename(NUTRITION)}, riquadri saltati")

    # il modello della flora: stesse colonne -> stesse serie sull'indice giornaliero
    microbes, microbe_first = {}, {}
    if os.path.exists(MICROBES):
        import csv as _csv
        with open(MICROBES, encoding="utf-8", newline="") as fh:
            mrows = [r for r in _csv.DictReader(fh) if r.get("date")]
        mcols = [c for c in (mrows[0].keys() if mrows else []) if c != "date"]
        tmp = {c: [None] * n for c in mcols}
        for r in mrows:
            i = idx.get(r["date"])
            if i is None:
                continue
            for c in mcols:
                if r.get(c) not in (None, ""):
                    tmp[c][i] = round(float(r[c]), 2)
        for c in mcols:
            i0 = next((i for i, v in enumerate(tmp[c]) if v is not None), None)
            if i0 is None:
                continue
            i1 = len(tmp[c]) - 1 - next(i for i, v in enumerate(reversed(tmp[c])) if v is not None)
            microbes[c] = {"i0": i0, "v": tmp[c][i0:i1 + 1]}
            microbe_first[c] = i0
        print(f"  flora (modello): {len(mrows)} giorni, {len(microbes)} serie")

    flora_foods = []
    if os.path.exists(FLORA_FOODS):
        import csv as _csv
        with open(FLORA_FOODS, encoding="utf-8", newline="") as fh:
            for r in _csv.DictReader(fh):
                flora_foods.append({k: (float(v) if k not in ("food_id", "name") else v)
                                    for k, v in r.items()})
        print(f"  flora x alimenti: {len(flora_foods)} alimenti")

    days_detail = {}
    if os.path.exists(DAYS):
        with open(DAYS, encoding="utf-8") as fh:
            days_detail = json.load(fh)
        print(f"  dettaglio giornaliero: {len(days_detail)} giorni")

    payload = {
        "built": date.today().isoformat(),
        "nutri": nutri,
        "microbes": microbes,
        "floraFoods": flora_foods,
        "days": days_detail,
        "pulled": raw["pulled"],
        "d0": d0.isoformat(),
        "n": n,
        "sports": SPORTS,
        "gaps": gaps,
        "ctl": ctl, "atl": atl, "load": load,
        "sleep": sleep, "score": score, "hrv": hrv, "rhr": rhr,
        "steps": steps, "vo2": vo2, "weight": weight, "bodyfat": bodyfat,
        "acts": arows,
        "anames": anames,
        "first": {
            "load": load_i0,
            "act": arows[0][0] if arows else 0,
            "sleep": first(sleep), "score": first(score), "hrv": first(hrv),
            "rhr": first(rhr), "steps": first(steps), "vo2": first(vo2),
            "weight": first(weight), "bodyfat": first(bodyfat),
            **{f"n_{c}": i for c, i in nutri_first.items() if i is not None},
            **{f"m_{c}": i for c, i in microbe_first.items()},
        },
        # dove ogni serie del cibo SMETTE. Il diario si ferma prima di oggi, e un
        # asse che arriva comunque a oggi disegna una settimana di vuoto che si
        # legge come "non ha mangiato" invece che "non l'ha raccontato".
        "last": {f"n_{c}": i for c, i in nutri_last.items()},
    }
    return payload


# ------------------------------------------------------------------ reporting

def coverage(p):
    """What the payload actually contains, per field and per year. Printed by every
    run and appended to the cumulative report, so a field quietly going empty at the
    source shows up as a step in the history rather than as a blank tile nobody
    thought to look at."""
    d0 = datetime.strptime(p["d0"], "%Y-%m-%d").date()
    lines = []
    lines.append(f"span: {p['d0']} → "
                 f"{(d0 + timedelta(days=p['n'] - 1)).isoformat()}  ({p['n']} giorni)")
    fields = ["ctl", "load", "sleep", "score", "hrv", "rhr", "steps", "vo2",
              "weight", "bodyfat"]
    for f in fields:
        vals = [v for v in p[f] if v is not None]
        nz = [v for v in vals if v]
        # ctl/atl are filled for the whole calendar by Intervals itself, so they have
        # no "first" entry — their story is the load's, reported on its own row.
        i0 = 0 if f == "ctl" else p["first"].get(f)
        since = (d0 + timedelta(days=i0)).isoformat() if i0 is not None else "—"
        lines.append(f"  {f:9s} {len(vals):5d} valori ({len(nz)} non nulli)  dal {since}")
    lines.append(f"  {'acts':9s} {len(p['acts']):5d} attività")
    by = defaultdict(int)
    for a in p["acts"]:
        by[(d0 + timedelta(days=a[0])).year] += 1
    lines.append("  attività per anno: " +
                 " ".join(f"{y}:{by[y]}" for y in sorted(by)))
    lines.append(f"  buchi ≥45 giorni senza attività: {len(p['gaps'])} → " +
                 ", ".join(f"{(d0 + timedelta(days=a)).isoformat()}"
                           f"→{(d0 + timedelta(days=b)).isoformat()}"
                           for a, b in p["gaps"][:8]) +
                 (" …" if len(p["gaps"]) > 8 else ""))
    return "\n".join(lines)


def append_report(p, note, wrote):
    """Append, never overwrite: the trend across builds is the evidence."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    head = "" if os.path.exists(REPORT) else (
        "# /vita/cruscotto — report cumulativo dei build\n\n"
        "Ogni run di `tools/build_cruscotto.py` appende qui cosa ha trovato nei dati\n"
        "Intervals.icu e cosa ha scritto. Si aggiunge, non si sovrascrive: la storia\n"
        "è il punto — un campo che smette di arrivare si vede come uno scalino.\n")
    with open(REPORT, "a", encoding="utf-8") as f:
        if head:
            f.write(head)
        f.write(f"\n## {stamp} — {note}\n\n```\n{coverage(p)}\n```\n")
        f.write(f"\npagina: {'scritta' if wrote else 'NON scritta'}"
                f"{f' ({wrote} KB)' if wrote else ''}\n")


# ---------------------------------------------------------------------- page

def highlights():
    """Le tre pagine-racconto, in cima: titolo, tre numeri, l'ultima modifica.

    Nessun grafico qui — hanno le loro pagine per quello, e sotto c'e' una
    colonna di grafici che e' il vero contenuto di /vita. Sono un indice, e un
    indice deve stare in poche righe."""
    out = []
    for t in (vita_trackers.load_gazzaniga(), vita_trackers.load_diario(),
              vita_trackers.load_sogni(), vita_trackers.load_spostamenti()):
        out.append({
            "key": t["key"], "title": t["title"], "href": t["href"],
            "eyebrow": t["eyebrow"], "blurb": t["blurb"], "accent": t["accent"],
            "last": t["last"],
            "stats": [{"v": s["v"], "l": s["l"]} for s in t["stats"]],
        })
    return out


def build_html(p):
    js = json.dumps(p, separators=(",", ":"))
    return TEMPLATE.replace("__DATA__", js).replace("__BUILT__", p["built"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key")
    ap.add_argument("--offline", action="store_true",
                    help="rebuild from tools/.cruscotto_cache.json, no network")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--dry-run", action="store_true", help="build but do not write")
    args = ap.parse_args()

    key = None if args.offline else get_api_key(args.api_key)
    raw = pull(key, use_cache=args.offline)
    p = build_payload(raw)
    p["tracks"] = highlights()
    print()
    print(coverage(p))

    if args.check or args.dry_run:
        append_report(p, "--check" if args.check else "--dry-run", wrote=0)
        print(f"\n(niente scritto; report → {os.path.basename(REPORT)})")
        return

    html = build_html(p)
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        shutil.copyfile(OUT, OUT + ".bak")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"\nwrote {OUT} ({kb} KB)")
    append_report(p, "build", wrote=kb)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vita — Michele Merelli</title>
<meta name="description" content="Undici anni di dati in un pannello solo: carico, forma, sonno, HRV, frequenza a riposo, peso, volume. Da Intervals.icu.">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:url" content="https://micmer-git.github.io/vita/">
<meta property="og:title" content="Vita — Michele Merelli">
<meta property="og:description" content="Carico, forma, sonno, HRV, peso, volume: ogni serie che misuro, in un pannello solo.">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500;600&family=Cinzel:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    /* Due valori qui dentro sono MISURATI, non scelti (laboratorio di stile,
       2026-08-10) — cambiarli a occhio rimette i difetti che sistemano, e il
       check li rimisura a ogni run:
         --muted  era #8a7d62 = 4,15:1 sulla scheda, sotto il minimo di 4,5:1 per
                  il testo normale — ed e' il colore di OGNI piede, didascalia,
                  etichetta d'asse e intestazione di tabella della pagina.
                  #9a8d70 sta a 5,13:1: margine vero, e resta recessivo.
         --gold   era #c89a3f, a ΔE 5,2 dallo slot 4 dei grafici (#c98500) sulla
                  stessa scheda: l'accento del sito si spacciava per una serie di
                  dati. #e2c98f sta a ΔE 18,6 da quello slot, contrasto 10,4:1. */
    --bg:#17150f; --paper:#211d16; --paper-2:#2a2519;
    --ink:#ece3cd; --ink-soft:#c6b997; --muted:#9a8d70;
    --gold:#e2c98f; --rule:rgba(200,154,63,.22);
    --grid:rgba(236,227,205,.09); --axis:rgba(236,227,205,.20);
    /* categorical slots 1-4, dark steps, validated against --paper */
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --neg:#e66767;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    background:var(--bg); color:var(--ink);
    font-family:'EB Garamond',Georgia,serif; font-size:18px; line-height:1.6;
    max-width:1280px; margin:0 auto; padding:44px 20px 90px;
    -webkit-text-size-adjust:100%;
  }
  body::before{
    content:""; position:fixed; inset:0; pointer-events:none; z-index:-1;
    background-image:
      radial-gradient(ellipse at 12% 10%,rgba(200,154,63,.09) 0,transparent 46%),
      radial-gradient(ellipse at 88% 84%,rgba(57,135,229,.07) 0,transparent 46%);
  }
  a{color:inherit}
  .mono{font-family:'IBM Plex Mono',ui-monospace,monospace}

  /* ---------- hero ---------- */
  header{text-align:center}
  .eyebrow{font-family:'IBM Plex Mono',monospace; font-size:.66rem; letter-spacing:.24em;
    text-transform:uppercase; color:var(--gold)}
  .eyebrow a{text-decoration:none; border-bottom:1px solid var(--rule)}
  .eyebrow a:hover{color:var(--ink)}
  h1{font-family:'Cinzel',serif; font-size:clamp(2.6rem,10vw,4.4rem); font-weight:700;
    letter-spacing:.06em; line-height:1; margin:12px 0 6px}
  .sub{color:var(--ink-soft); font-style:italic; max-width:36em; margin:12px auto 0;
    font-size:1.02rem}

  /* ---------- headline numbers ---------- */
  .totals{display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
    gap:16px 10px; margin:30px auto 0; max-width:1000px}
  .total{text-align:center}
  .total .n{font-family:'Cinzel',serif; font-size:1.5rem; font-weight:700; color:var(--gold);
    font-variant-numeric:tabular-nums; line-height:1.1}
  .total .l{font-family:'IBM Plex Mono',monospace; font-size:.58rem; letter-spacing:.13em;
    text-transform:uppercase; color:var(--muted); margin-top:4px}

  /* ---------- range control ---------- */
  .ranges{display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:30px 0 6px}
  .ranges button{
    font-family:'IBM Plex Mono',monospace; font-size:.66rem; letter-spacing:.14em;
    text-transform:uppercase; padding:7px 15px; border-radius:999px; cursor:pointer;
    background:transparent; border:1px solid var(--rule); color:var(--ink-soft);
    transition:border-color .15s,color .15s,background .15s;
  }
  .ranges button:hover{border-color:var(--gold); color:var(--ink)}
  .ranges button[aria-pressed="true"]{border-color:var(--gold); color:var(--bg);
    background:var(--gold); font-weight:600}
  .ranges button:focus-visible{outline:2px solid var(--gold); outline-offset:3px}
  .range-note{text-align:center; color:var(--muted); font-size:.82rem; font-style:italic;
    margin-top:8px}

  /* ---------- la colonna di grafici ----------
     Uno sopra l'altro, non a griglia: cosi' tutti condividono lo stesso asse x e
     l'occhio puo' scendere lungo la pagina confrontando lo stesso mese fra serie
     diverse — che e' l'unica cosa che una griglia di riquadri non lascia fare.
     Il prezzo e' l'altezza, quindi ogni riquadro e' basso e il titolo, il numero
     di oggi e il grafico stanno sulla stessa riga dove c'e' spazio. */
  .panel{display:flex; flex-direction:column; gap:8px; margin:20px 0 0}
  .tile{
    position:relative; background:var(--paper); border:1px solid var(--rule);
    border-radius:7px; padding:9px 13px 7px; transition:border-color .16s,background .16s;
    min-width:0; display:grid; grid-template-columns:170px 1fr; gap:0 16px;
    align-items:center;
  }
  .tile:hover{border-color:rgba(200,154,63,.4); background:var(--paper-2)}
  .t-side{min-width:0}
  .t-head{display:flex; align-items:baseline; gap:8px; flex-wrap:wrap}
  .t-title{font-family:'Cinzel',serif; font-size:.98rem; font-weight:600;
    letter-spacing:.02em; line-height:1.2}
  .t-now{font-family:'IBM Plex Mono',monospace; font-size:1.15rem; font-weight:600;
    font-variant-numeric:tabular-nums; color:var(--gold); line-height:1.15; margin-top:3px}
  .t-now small{display:block; font-size:.55rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted); font-weight:400; margin-top:1px}
  .t-cap{font-family:'IBM Plex Mono',monospace; font-size:.55rem; letter-spacing:.08em;
    text-transform:uppercase; color:var(--muted); margin-top:2px; line-height:1.45}
  .t-legend{display:flex; gap:9px; flex-wrap:wrap; margin:3px 0 0;
    font-family:'IBM Plex Mono',monospace; font-size:.54rem; letter-spacing:.06em;
    text-transform:uppercase; color:var(--ink-soft)}
  .t-legend i{display:inline-block; width:8px; height:8px; border-radius:2px;
    margin-right:4px; vertical-align:-1px}
  /* le leve dell'indice microbiota: l'emoji dice quale, il numero quanto e' tirata */
  .t-shift{display:flex; gap:11px; flex-wrap:wrap; margin-top:5px; font-size:.95rem}
  .t-shift b{font-family:'IBM Plex Mono',monospace; font-size:.68rem; font-weight:600}
  svg.plot{width:100%; height:auto; display:block; touch-action:pan-y; overflow:visible}
  .t-foot{font-family:'IBM Plex Mono',monospace; font-size:.53rem; letter-spacing:.06em;
    color:var(--muted); margin-top:3px; line-height:1.45; grid-column:1/-1}
  .t-empty{font-style:italic; color:var(--muted); font-size:.8rem; padding:14px 0;
    text-align:center}

  /* ---------- data fallback ---------- */
  details.data{margin-top:4px; grid-column:1/-1}
  details.data summary{font-family:'IBM Plex Mono',monospace; font-size:.55rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted); cursor:pointer;
    list-style:none}
  details.data summary::-webkit-details-marker{display:none}
  details.data summary::before{content:"▸ "; }
  details.data[open] summary::before{content:"▾ "; }
  details.data summary:hover{color:var(--ink-soft)}
  table.fallback{width:100%; border-collapse:collapse; margin-top:6px; font-size:.72rem;
    font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums}
  table.fallback th,table.fallback td{text-align:right; padding:2px 0 2px 8px;
    border-bottom:1px solid rgba(200,154,63,.12); color:var(--ink-soft); white-space:nowrap}
  table.fallback th:first-child,table.fallback td:first-child{text-align:left; padding-left:0}
  table.fallback th{color:var(--muted); font-weight:500}

  /* ---------- il popup della giornata ---------- */
  .sheet{position:fixed; inset:0; z-index:20; display:none; background:rgba(10,9,6,.72);
    backdrop-filter:blur(2px); padding:4vh 14px; overflow-y:auto}
  .sheet.on{display:block}
  .sheet-in{position:relative; max-width:760px; margin:0 auto; background:var(--paper);
    border:1px solid var(--rule); border-radius:9px; padding:20px 22px 24px;
    box-shadow:0 20px 60px rgba(0,0,0,.6)}
  .sheet h3{font-family:'Cinzel',serif; font-size:1.5rem; font-weight:700; margin:0}
  .sheet .when{font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--gold)}
  .sheet-x{position:absolute; top:12px; right:12px; background:none; border:0; cursor:pointer;
    color:var(--muted); font-size:1.5rem; line-height:1; padding:4px 8px}
  .sheet-x:hover{color:var(--ink)}
  .sheet-hd{padding-right:34px}
  .sheet h4{font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.17em;
    text-transform:uppercase; color:var(--gold); font-weight:600; margin:20px 0 7px;
    border-top:1px solid var(--rule); padding-top:11px}
  .kv{display:grid; grid-template-columns:repeat(auto-fit,minmax(94px,1fr)); gap:10px 14px}
  .kv div b{font-family:'IBM Plex Mono',monospace; font-size:.95rem; color:var(--ink);
    font-variant-numeric:tabular-nums; display:block}
  .kv div span{font-family:'IBM Plex Mono',monospace; font-size:.52rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted)}
  .acts li{list-style:none; display:flex; justify-content:space-between; gap:12px;
    padding:6px 0; border-bottom:1px solid rgba(200,154,63,.12); flex-wrap:wrap}
  .acts a{color:var(--ink); text-decoration:none; border-bottom:1px solid var(--rule)}
  .acts a:hover{color:var(--gold)}
  .acts em{font-family:'IBM Plex Mono',monospace; font-size:.66rem; color:var(--muted);
    font-style:normal; white-space:nowrap}
  .meal{margin-bottom:9px}
  .meal .mname{font-family:'IBM Plex Mono',monospace; font-size:.55rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--ink-soft)}
  .meal ul{list-style:none; margin-top:3px}
  .meal li{display:flex; justify-content:space-between; gap:10px; font-size:.86rem;
    color:var(--ink-soft); padding:1px 0}
  .meal li i{font-style:normal; font-family:'IBM Plex Mono',monospace; font-size:.68rem;
    color:var(--muted); white-space:nowrap}
  .meal li.asm{opacity:.62}
  .meal li.asm::after{content:" ricostruito"; font-family:'IBM Plex Mono',monospace;
    font-size:.5rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted)}
  .bars{display:grid; gap:4px}
  .bar{display:grid; grid-template-columns:96px 1fr 46px; gap:9px; align-items:center;
    font-family:'IBM Plex Mono',monospace; font-size:.62rem; color:var(--ink-soft)}
  .bar u{text-decoration:none; color:var(--muted)}
  .bar div{height:7px; border-radius:99px; background:rgba(236,227,205,.09); overflow:hidden}
  .bar div i{display:block; height:100%; border-radius:99px}
  .bar b{text-align:right; color:var(--ink); font-variant-numeric:tabular-nums;
    font-weight:500}
  .hint{font-family:'IBM Plex Mono',monospace; font-size:.53rem; letter-spacing:.09em;
    color:var(--muted); text-align:center; margin-top:9px}

  /* ---------- tooltip ---------- */
  .tip{position:fixed; z-index:9; pointer-events:none; opacity:0; transition:opacity .1s;
    background:#0e0d09; border:1px solid var(--rule); border-radius:5px; padding:6px 10px;
    font-family:'IBM Plex Mono',monospace; font-size:.68rem; line-height:1.55;
    color:var(--ink-soft); max-width:240px; box-shadow:0 6px 20px rgba(0,0,0,.5)}
  .tip.on{opacity:1}
  .tip .v{color:var(--gold); font-weight:600}
  .tip .d{color:var(--muted); font-size:.62rem; letter-spacing:.06em}

  /* ---------- le tre pagine-racconto, in cima ---------- */
  .tracks{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
    gap:12px; margin:30px 0 0}
  .track{position:relative; display:block; text-decoration:none; border-radius:7px;
    border:1px solid var(--rule); background:var(--paper); padding:14px 16px 12px;
    transition:border-color .16s,background .16s,transform .16s; overflow:hidden}
  .track::before{content:""; position:absolute; inset:0 auto 0 0; width:3px; background:var(--a)}
  .track:hover{border-color:var(--a); background:var(--paper-2); transform:translateY(-2px)}
  .track:focus-visible{outline:2px solid var(--a); outline-offset:3px}
  .track .k{font-family:'IBM Plex Mono',monospace; font-size:.56rem; letter-spacing:.19em;
    text-transform:uppercase; color:var(--a)}
  .track h3{font-family:'Cinzel',serif; font-size:1.12rem; font-weight:700; margin:4px 0 0}
  .track p{color:var(--ink-soft); font-size:.85rem; line-height:1.5; margin-top:5px}
  .track .nums{display:flex; gap:14px; flex-wrap:wrap; margin-top:9px}
  .track .nums b{font-family:'IBM Plex Mono',monospace; font-size:.82rem; font-weight:600;
    color:var(--ink); font-variant-numeric:tabular-nums; display:block}
  .track .nums span{font-family:'IBM Plex Mono',monospace; font-size:.5rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted)}
  @media(prefers-reduced-motion:reduce){.track{transition:none}.track:hover{transform:none}}

  /* ---------- sections ---------- */
  h2.band{font-family:'Cinzel',serif; font-size:.9rem; letter-spacing:.2em;
    text-transform:uppercase; color:var(--gold); text-align:center; font-weight:600;
    margin:36px 0 2px}
  .band-sub{text-align:center; color:var(--muted); font-size:.82rem; font-style:italic;
    max-width:52em; margin:0 auto}

  /* ---------- also / footer ---------- */
  .also{margin-top:44px; text-align:center}
  .also a{display:inline-block; margin:6px 6px; padding:7px 15px; border-radius:999px;
    border:1px solid var(--rule); color:var(--ink-soft); text-decoration:none; font-size:.85rem}
  .also a:hover{border-color:var(--gold); color:var(--ink)}
  footer{margin-top:34px; text-align:center; color:var(--muted); font-size:.78rem;
    line-height:1.7}
  @media(prefers-reduced-motion:reduce){*{transition:none !important}}
  /* Sotto i 720px la colonna laterale del riquadro non ci sta piu' accanto al
     grafico: titolo e numero passano sopra, il grafico prende tutta la larghezza.
     E' l'unico punto in cui il layout cambia forma, non solo dimensione. */
  @media(max-width:720px){
    .tile{grid-template-columns:1fr; gap:5px 0; padding:11px 12px 8px}
    .t-side{display:flex; align-items:baseline; justify-content:space-between;
      gap:10px; flex-wrap:wrap}
    .t-now{font-size:1rem; margin-top:0; text-align:right}
    .t-now small{display:inline; margin-left:5px}
    .t-cap{flex-basis:100%; margin-top:0}
  }
  @media(max-width:560px){
    body{padding:26px 11px 64px; font-size:17px}
    .totals{grid-template-columns:repeat(auto-fit,minmax(92px,1fr)); gap:13px 8px}
    .total .n{font-size:1.25rem}
    .ranges{gap:6px}
    .ranges button{padding:6px 12px; font-size:.62rem}
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">micmer · quadro di comando</div>
  <h1>Vita</h1>
  <p class="sub">Tutto quello che misuro, in una colonna sola. I numeri arrivano da
  Intervals.icu e dal diario alimentare, e sono inseriti nella pagina quando viene
  generata: nessuna chiamata, nessun dato che esce di qui.</p>
</header>

<div class="totals" id="totals"></div>

<nav class="tracks" id="tracks" aria-label="Le pagine"></nav>

<div class="ranges" id="ranges" role="group" aria-label="Finestra temporale"></div>
<p class="range-note" id="range-note"></p>

<h2 class="band">Carico</h2>
<p class="band-sub">Quanto lavoro c'è addosso, e quanto ne è già stato smaltito.</p>
<main class="panel" id="panel-carico"></main>

<h2 class="band">Notte</h2>
<p class="band-sub">Il sonno come lo misura l'orologio — dal 2025 in poi.</p>
<main class="panel" id="panel-notte"></main>

<h2 class="band">Recupero</h2>
<p class="band-sub">Cosa dice il cuore al mattino, prima che cominci qualsiasi cosa.</p>
<main class="panel" id="panel-recupero"></main>

<h2 class="band">Corpo</h2>
<p class="band-sub">Poche misure, prese di rado: nuvole di punti con la loro tendenza.</p>
<main class="panel" id="panel-corpo"></main>

<h2 class="band">Volume</h2>
<p class="band-sub">Le ore, i chilometri, il dislivello — e come si dividono.</p>
<main class="panel" id="panel-volume"></main>

<h2 class="band">Incroci</h2>
<p class="band-sub">Una serie contro l'altra. La retta è una regressione dei minimi
quadrati e <em>r</em> è la correlazione. Il risultato onesto di questa sezione è che
sono <strong>tutte vicine a zero</strong>: niente di quello che l'orologio misura al
mattino sa dire cosa è successo il giorno prima. Le nuvole sono qui apposta — una
correlazione nulla si vede solo se la si disegna.</p>
<main class="panel" id="panel-incroci"></main>

<h2 class="band" id="cibo">Tavola</h2>
<p class="band-sub">Cosa entra, contro cosa serve. Queste serie sono una
<strong>ricostruzione</strong>, non un diario: due anni di giornate rimesse insieme
da quello che Michele ha dichiarato di mangiare — la colazione fissa, due avocado
toast e due dahl a settimana, e i piatti che ogni mese ricorrevano nelle sue foto,
ognuno una volta nella sua settimana e poi a rotazione. Per sua stessa stima quei
piatti sono circa il <strong>75 %</strong> di cosa mangia: il restante quarto —
spuntini, avanzi, il resto — qui non c'è, quindi le calorie sono una base, non un
totale. Il primo riquadro dice quanta parte di ogni giorno è invece osservata
davvero.</p>
<main class="panel" id="panel-tavola"></main>

<nav class="also">
  <a href="../top-20/">Venti giorni su 2.923</a>
  <a href="../bike-to-work/">Al lavoro in bici</a>
  <a href="../signore-dei-kj.html">Il Signore dei kJ</a>
  <a href="../viaggi/">Viaggi</a>
  <a href="../league-of-strava/">League of Strava</a>
  <a href="../">Profilo</a>
</nav>

<footer>
  Generato il <span class="mono">__BUILT__</span> da
  <span class="mono">tools/build_vita.py</span>, leggendo Intervals.icu e gli
  aggregati giornalieri del diario alimentare.<br>
  Il carico è registrato dal 2019; sonno, HRV, passi e VO₂max dal 2025; la tavola
  da maggio 2026. Il <strong>2022 manca dall'archivio</strong>: le zone tratteggiate
  non sono riposo, sono assenza di dati.
</footer>

<div class="tip" id="tip" role="status" aria-live="polite"></div>

<div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-t">
  <div class="sheet-in" id="sheet-in"></div>
</div>

<script>
const D = __DATA__;

/* Le serie del cibo viaggiano compresse come {i0, v}: qui tornano array lunghi
   quanto il calendario, cosi' ogni riquadro le indicizza per giorno come tutte
   le altre e non deve sapere niente della compressione. */
(function expandBlocks() {
  const wide = src => {
    const out = {};
    for (const k in (src || {})) {
      const b = src[k], a = new Array(D.n).fill(null);
      for (let i = 0; i < b.v.length; i++) a[b.i0 + i] = b.v[i];
      out[k] = a;
    }
    return out;
  };
  D.nutri = wide(D.nutri);
  D.microbes = wide(D.microbes);
})();

/* ------------------------------------------------------------------ time */
const DAY = 86400000;
const D0 = new Date(D.d0 + "T00:00:00");
const dayDate = i => new Date(D0.getTime() + i * DAY);
const N = D.n;
const MON = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"];
const DOW = ["lun","mar","mer","gio","ven","sab","dom"];
const fmtDate = i => { const d = dayDate(i);
  return d.getDate() + " " + MON[d.getMonth()] + " " + d.getFullYear(); };

/* Ranges. "sempre" is resolved per tile against that series' own first day, so a
   tile can never imply coverage it does not have. */
const RANGES = [
  { key:"2a",     label:"2 anni",    days:730 },
  { key:"1a",     label:"1 anno",    days:365 },
  { key:"3m",     label:"trimestre", days:91 },
  { key:"sempre", label:"sempre",    days:null },
];
/* Due anni di default: e' la finestra in cui quasi tutte le serie esistono
   davvero (sonno e HRV partono nel 2025), quindi e' quella in cui la colonna si
   legge tutta. "sempre" resta raggiungibile perche' il carico ha undici anni di
   storia e buttarli via sarebbe un peccato. */
let range = "2a";

function windowFor(firstIdx, lastIdx) {
  const last = lastIdx === undefined || lastIdx === null ? N - 1 : lastIdx;
  const r = RANGES.find(r => r.key === range);
  const from = r.days === null ? firstIdx : last - r.days + 1;
  return [Math.max(from, firstIdx, 0), last];
}
/* media mobile letta dove la serie finisce davvero, non dove finisce il calendario:
   per il cibo le due cose non coincidono */
function lastMean(arr, w) {
  let e = -1;
  for (let i = N - 1; i >= 0; i--) if (arr[i] !== null && arr[i] !== undefined) { e = i; break; }
  if (e < 0) return null;
  const r = rolling(arr, Math.max(0, e - w + 1), e, w);
  return r[r.length - 1];
}

/* ------------------------------------------------------- number formatting */
const nf = (v, d = 0) => v === null || v === undefined || !isFinite(v) ? "—"
  : v.toLocaleString("it-IT", { minimumFractionDigits:d, maximumFractionDigits:d });
const hhmm = m => m === null || m === undefined ? "—"
  : Math.floor(m / 60) + "h " + String(Math.round(m % 60)).padStart(2, "0") + "'";
const FMT = {
  num0:v => nf(v,0), num1:v => nf(v,1), hhmm,
  hours:v => nf(v,1) + " h", km:v => nf(v,0) + " km", m:v => nf(v,0) + " m",
  kg:v => nf(v,1) + " kg", pct:v => nf(v,1) + " %", bpm:v => nf(v,0) + " bpm",
  ms:v => nf(v,0) + " ms", tss:v => nf(v,0) + " TSS",
};

/* ------------------------------------------------------------ aggregation */
/* Adaptive bucketing: a bar per day over eleven years is a smear, so the bucket
   widens until at most ~110 of them fit. The label says which width won. */
function bucketPlan(from, to) {
  const days = to - from + 1;
  if (days <= 110) return { step:"d", label:"al giorno" };
  if (days <= 780) return { step:"w", label:"a settimana" };
  /* the whole archive is 4.152 days = 137 months, which still draws as a dense but
     readable bar field; falling back to years there would answer eleven years of
     volume with twelve bars, which is a summary, not a chart */
  if (days <= 4800) return { step:"m", label:"al mese" };
  return { step:"y", label:"all'anno" };
}
/* Monday-based weeks, calendar months and years — the same conventions the other
   pages on this site aggregate by. */
function bucketKey(i, step) {
  const d = dayDate(i);
  if (step === "d") return i;
  if (step === "w") { const off = (d.getDay() + 6) % 7; return i - off; }
  if (step === "m") return -(d.getFullYear() * 12 + d.getMonth()) - 1;
  return -100000 - d.getFullYear();
}
function bucketLabel(k, step) {
  if (step === "d") return fmtDate(k);
  if (step === "w") return "sett. del " + fmtDate(k);
  if (step === "m") { const t = -(k + 1); return MON[t % 12] + " " + Math.floor(t / 12); }
  return String(-(k + 100000));
}
function bucketStartIdx(k, step) {
  if (step === "d" || step === "w") return k;
  if (step === "m") { const t = -(k + 1);
    return Math.round((new Date(Math.floor(t / 12), t % 12, 1) - D0) / DAY); }
  return Math.round((new Date(-(k + 100000), 0, 1) - D0) / DAY);
}
/* Sum or mean a daily array into buckets. `mean` skips nulls; `sum` treats them as 0
   only when the day is inside the series' own coverage — outside it, the bucket is
   dropped rather than counted as a zero. */
function aggregate(arr, from, to, how, step) {
  const acc = new Map();
  for (let i = from; i <= to; i++) {
    const v = arr[i];
    if (v === null || v === undefined) { if (how === "mean") continue; }
    const k = bucketKey(i, step);
    let a = acc.get(k); if (!a) { a = { s:0, n:0, k }; acc.set(k, a); }
    a.s += (v || 0); a.n += 1;
  }
  return [...acc.values()].sort((a, b) => bucketStartIdx(a.k, step) - bucketStartIdx(b.k, step))
    .map(a => ({ k:a.k, i:bucketStartIdx(a.k, step), v: how === "mean" ? (a.n ? a.s / a.n : null) : a.s, n:a.n }));
}
/* Trailing rolling mean — the same window an athlete reads on a watch. */
function rolling(arr, from, to, w) {
  const out = [];
  for (let i = from; i <= to; i++) {
    let s = 0, n = 0;
    for (let j = Math.max(from, i - w + 1); j <= i; j++) {
      const v = arr[j]; if (v !== null && v !== undefined) { s += v; n++; }
    }
    out.push(n >= Math.max(2, w / 3) ? s / n : null);
  }
  return out;
}
function stats(vals) {
  const v = vals.filter(x => x !== null && x !== undefined && isFinite(x));
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b);
  return { n:v.length, min:s[0], max:s[s.length - 1],
    mean:v.reduce((a, b) => a + b, 0) / v.length,
    med:s[Math.floor(s.length / 2)] };
}
/* Least squares + Pearson r. Both are reported; a fitted line without its r invites
   the reader to see a relationship that the number would deny. */
function fit(pts) {
  const n = pts.length; if (n < 4) return null;
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  for (const [x, y] of pts) { sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; }
  const dx = n * sxx - sx * sx, dy = n * syy - sy * sy;
  if (!dx || !dy) return null;
  const m = (n * sxy - sx * sy) / dx, b = (sy - m * sx) / n;
  const r = (n * sxy - sx * sy) / Math.sqrt(dx * dy);
  return { m, b, r, n };
}

/* ------------------------------------------------------------------- svg */
const NS = "http://www.w3.org/2000/svg";
const el = (t, a = {}) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const nice = (lo, hi) => {
  if (lo === hi) { lo -= 1; hi += 1; }
  const span = hi - lo, mag = Math.pow(10, Math.floor(Math.log10(span / 3)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= 5) || mag * 10;
  return { lo:Math.floor(lo / step) * step, hi:Math.ceil(hi / step) * step, step };
};

/* Room for the y labels, measured rather than assumed. At font-size 8 an IBM Plex
   Mono glyph is ~4.85px wide, so a five-figure tick ("50.000") needs 38px where a
   two-figure one needs 20 — a fixed gutter either clips the big numbers or wastes a
   tenth of a 320px tile on the small ones. Every axis below sizes its own. */
const TICKW = 4.85;
const yTicks = (yd, fmt) => {
  const out = [];
  for (let v = yd.lo; v <= yd.hi + 1e-9; v += yd.step) out.push([v, String(fmt(v))]);
  return out;
};
const padFor = ticks => Math.min(62, Math.max(24,
  Math.ceil(Math.max(...ticks.map(t => t[1].length)) * TICKW) + 9));
const axisText = (x, y, s, anchor) => el("text", { x, y, "text-anchor":anchor,
  fill:"var(--muted)", "font-size":"8", "font-family":"'IBM Plex Mono',monospace" });
function yAxis(svg, ticks, Y, l, right) {
  for (const [v, lab] of ticks) {
    const y = Y(v);
    svg.appendChild(el("line", { x1:l, x2:right, y1:y, y2:y,
      stroke:v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width":1 }));
    const t = axisText(l - 5, y + 3, lab, "end");
    t.textContent = lab; svg.appendChild(t);
  }
}

const tip = document.getElementById("tip");
function showTip(x, y, html) {
  tip.innerHTML = html; tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(Math.max(8, x - r.width / 2), innerWidth - r.width - 8) + "px";
  tip.style.top = Math.max(8, y - r.height - 12) + "px";
}
const hideTip = () => tip.classList.remove("on");
addEventListener("scroll", hideTip, { passive:true });

/* A chart frame: axes, gridlines, the shaded no-data bands, and the scales. Every
   renderer below draws into one of these, so they cannot drift apart. */
function frame(svg, W, H, xdom, ydom, opts = {}) {
  const yd = nice(ydom[0], ydom[1]);
  const ticks = yTicks(yd, opts.ytick || (v => nf(v, yd.step < 1 ? 1 : 0)));
  const P = { l:padFor(ticks), r:6, t:8, b:16 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const [x0, x1] = xdom;
  const X = v => P.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;

  /* no-data bands first, under everything */
  if (opts.gaps !== false) for (const [a, b] of D.gaps) {
    if (b < x0 || a > x1) continue;
    const xa = X(Math.max(a, x0)), xb = X(Math.min(b, x1));
    if (xb - xa < 1.5) continue;
    svg.appendChild(el("rect", { x:xa, y:P.t, width:xb - xa, height:ih,
      fill:"rgba(236,227,205,.05)" }));
    svg.appendChild(el("rect", { x:xa, y:P.t, width:xb - xa, height:ih,
      fill:"none", stroke:"rgba(236,227,205,.16)", "stroke-width":1,
      "stroke-dasharray":"2 3" }));
    if (xb - xa > 46) {
      const t = el("text", { x:(xa + xb) / 2, y:P.t + 10, "text-anchor":"middle",
        fill:"var(--muted)", "font-size":"7.5", "letter-spacing":".08em",
        "font-family":"'IBM Plex Mono',monospace" });
      t.textContent = "nessun dato"; svg.appendChild(t);
    }
  }
  yAxis(svg, ticks, Y, P.l, W - P.r);
  /* x ticks: 3-5 dates across the window, never overlapping */
  if (opts.xticks !== false) {
    const kmax = iw < 260 ? 3 : iw < 420 ? 4 : 5;
    for (let k = 0; k < kmax; k++) {
      const v = x0 + (x1 - x0) * k / (kmax - 1), d = dayDate(Math.round(v));
      const span = x1 - x0;
      const lab = span > 900 ? String(d.getFullYear())
        : span > 150 ? MON[d.getMonth()] + " " + String(d.getFullYear()).slice(2)
        : d.getDate() + " " + MON[d.getMonth()];
      const t = axisText(X(v), H - 4, lab,
        k === 0 ? "start" : k === kmax - 1 ? "end" : "middle");
      t.textContent = lab; svg.appendChild(t);
    }
  }
  return { X, Y, P, iw, ih, yd };
}

/* A path that BREAKS on nulls rather than bridging them. */
function pathOf(pts, X, Y) {
  let d = "", pen = false;
  for (const [x, y] of pts) {
    if (y === null || y === undefined || !isFinite(y)) { pen = false; continue; }
    d += (pen ? "L" : "M") + X(x).toFixed(1) + " " + Y(y).toFixed(1) + " ";
    pen = true;
  }
  return d.trim();
}

/* ------------------------------------------------------ il popup di un giorno
   Un click su un punto qualsiasi apre la giornata intera: sonno e recupero,
   le attività con il link a Intervals e a Strava, i pasti alimento per alimento,
   e le coperture dei fabbisogni. È il posto in cui una serie torna a essere una
   giornata — e in cui si vede subito se un valore strano viene da un dato strano
   o da una giornata strana. */
const sheet = document.getElementById("sheet");
const sheetIn = document.getElementById("sheet-in");
const MEAL_IT = { colazione:"Colazione", pranzo:"Pranzo", cena:"Cena",
  spuntino:"Spuntino", non_specificato:"Non specificato" };
const NUTRI_IT = { protein_g:"Proteine", carb_g:"Carboidrati", fiber_g:"Fibre",
  fat_g:"Grassi", omega3_g:"Omega 3", potassium_mg:"Potassio", calcium_mg:"Calcio",
  iron_mg:"Ferro", magnesium_mg:"Magnesio", zinc_mg:"Zinco", vitc_mg:"Vit. C",
  vita_ug:"Vit. A", vitd_ug:"Vit. D", b12_ug:"Vit. B12", folate_ug:"Folati" };
const CAP_IT = { sodium_mg:"Sodio", satfat_g:"Grassi saturi", sugar_g:"Zuccheri" };

function bar(label, pct, cap) {
  const w = Math.max(0, Math.min(100, pct));
  /* oltre il 100 % la barra resta piena: è una copertura, non una gara. Sui tetti
     (sodio, saturi, zuccheri) il colore vira quando si sfonda. */
  const col = cap ? (pct > 100 ? "var(--neg)" : "var(--s4)")
                  : (pct >= 100 ? "var(--s3)" : pct >= 50 ? "var(--s4)" : "var(--s2)");
  return `<div class="bar"><u>${label}</u><div><i style="width:${w}%;background:${col}"></i></div><b>${nf(pct, 0)}%</b></div>`;
}

function openDay(i) {
  if (i < 0 || i >= N) return;
  const k = dayDate(i).toISOString().slice(0, 10);
  /* Il dettaglio arriva in tre forme: un giorno con pasti veri, un puntatore a una
     "forma ricostruita" (le centinaia di giorni identici stanno in _p una volta
     sola), e niente. Le ricette ricostruite si ridistendono da _t, il template. */
  let day = (D.days || {})[k];
  if (typeof day === "string") day = ((D.days || {})._p || {})[day];
  const acts = D.acts.map((a, j) => [a, j]).filter(([a]) => a[0] === i);
  const sleep = D.sleep[i], hrv = D.hrv[i], rhr = D.rhr[i], steps = D.steps[i];
  const score = D.score[i], w = D.weight[i];
  const ctl = D.ctl[i], atl = D.atl[i];

  let h = `<div class="sheet-hd"><div class="when">${DOW[(dayDate(i).getDay() + 6) % 7]}</div>` +
    `<h3 id="sheet-t">${fmtDate(i)}</h3></div>`;

  const kv = [];
  if (sleep !== null) kv.push([hhmm(sleep), "sonno"]);
  if (score !== null) kv.push([nf(score), "punteggio"]);
  if (hrv !== null) kv.push([nf(hrv) + " ms", "hrv"]);
  if (rhr !== null) kv.push([nf(rhr), "fc riposo"]);
  if (steps !== null) kv.push([nf(steps), "passi"]);
  if (w !== null) kv.push([nf(w, 1) + " kg", "peso"]);
  if (ctl !== null) kv.push([nf(ctl, 0), "fitness"]);
  if (ctl !== null && atl !== null) kv.push([nf(ctl - atl, 0), "forma"]);
  if (kv.length) h += `<h4>Corpo</h4><div class="kv">` +
    kv.map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("") + `</div>`;

  if (acts.length) {
    h += `<h4>Allenamento</h4><ul class="acts">` + acts.map(([a, j]) => {
      const nm = (D.anames || [])[j] || ["", "", ""];
      const bits = [];
      if (a[2]) bits.push(hhmm(a[2] / 60));
      if (a[3]) bits.push(nf(a[3] / 1000, 1) + " km");
      if (a[4]) bits.push(nf(a[4]) + " m");
      if (a[5]) bits.push(nf(a[5]) + " TSS");
      const links = [];
      if (nm[1]) links.push(`<a href="https://intervals.icu/activities/${nm[1]}" target="_blank" rel="noopener">Intervals</a>`);
      if (nm[2]) links.push(`<a href="https://www.strava.com/activities/${nm[2]}" target="_blank" rel="noopener">Strava</a>`);
      return `<li><span>${nm[0] || S[a[1]]}${links.length ? " · " + links.join(" · ") : ""}</span><em>${bits.join(" · ")}</em></li>`;
    }).join("") + `</ul>`;
  }

  if (day && day.recipes && !day.meals) {
    /* giornata interamente ricostruita: si dice, e si mostra da cosa */
    const tpl = (D.days || {})._t || {};
    h += `<h4>Tavola — ${nf(day.tot.kcal)} kcal · ricostruita</h4>`;
    h += `<p class="hint" style="text-align:left;margin:0 0 8px">Di questo giorno non hai raccontato niente: qui sotto c'è lo schema abituale, non un pasto osservato.</p>`;
    for (const rn of day.recipes) {
      h += `<div class="meal"><div class="mname">${rn}</div><ul>` +
        (tpl[rn] || []).map(it => `<li class="asm"><span>${it.n}</span><i>${it.q} · ${nf(it.kcal)} kcal</i></li>`).join("") +
        `</ul></div>`;
    }
    h += `<h4>Macro e micro, in % del fabbisogno</h4><div class="bars">` +
      Object.keys(NUTRI_IT).filter(nn => day.pct[nn] !== undefined)
        .map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
      Object.keys(day.cap || {}).map(nn => bar(CAP_IT[nn] || nn, day.cap[nn], true)).join("") +
      `</div>`;
  } else if (day) {
    const meals = day.meals || {};
    const order = ["colazione", "pranzo", "cena", "spuntino", "non_specificato"];
    const keys = order.filter(m => meals[m]).concat(
      Object.keys(meals).filter(m => !order.includes(m)));
    if (keys.length) {
      h += `<h4>Tavola — ${nf(day.tot.kcal)} kcal` +
        (day.asm ? ` · ${nf(Math.round(100 * day.obs / (day.obs + day.asm)))}% osservato` : "") +
        `</h4>`;
      for (const m of keys) {
        h += `<div class="meal"><div class="mname">${MEAL_IT[m] || m}</div><ul>` +
          meals[m].map(it => `<li class="${it.a ? "asm" : ""}"><span>${it.n}${it.r ? ` <u style="color:var(--muted);text-decoration:none">· ${it.r}</u>` : ""}</span><i>${it.q} · ${nf(it.kcal)} kcal</i></li>`).join("") +
          `</ul></div>`;
      }
      const macro = ["protein_g", "carb_g", "fiber_g", "fat_g"];
      h += `<h4>Macro e micro, in % del fabbisogno</h4><div class="bars">` +
        macro.filter(nn => day.pct[nn] !== undefined).map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
        Object.keys(NUTRI_IT).filter(nn => !macro.includes(nn) && day.pct[nn] !== undefined)
          .map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
        Object.keys(day.cap || {}).map(nn => bar(CAP_IT[nn] || nn, day.cap[nn], true)).join("") +
        `</div><p class="hint">Sui tetti (sodio, saturi, zuccheri) il rosso è uno sforamento, non un obiettivo mancato.</p>`;
    }
  } else {
    h += `<h4>Tavola</h4><p class="t-empty">Nessun pasto per questo giorno.</p>`;
  }

  sheetIn.innerHTML = h;
  /* Il bottone di chiusura e' un nodo vero appeso dopo, non un pezzo della stringa
     qui sopra: interrogare all'indietro l'HTML appena scritto e' proprio la cosa
     che rende la pagina impossibile da pilotare senza browser — e che il check
     non saprebbe piu' fare. Vale anche per un solo bottone. */
  const x = mk("button", "sheet-x", sheetIn, "×");
  x.setAttribute("type", "button");
  x.setAttribute("aria-label", "Chiudi");
  x.addEventListener("click", closeDay);
  sheet.classList.add("on");
  document.body.style.overflow = "hidden";
}
function closeDay() {
  sheet.classList.remove("on");
  document.body.style.overflow = "";
}
sheet.addEventListener("click", ev => { if (ev.target === sheet) closeDay(); });
addEventListener("keydown", ev => { if (ev.key === "Escape") closeDay(); });

/* --------------------------------------------------------------- renderers */
/* Each returns {stats, table, foot} so the tile can print its own summary and its
   own data fallback without the renderer knowing about the DOM around it. */

function rLines(svg, W, H, t, from, to) {
  const series = t.series.map(s => ({ ...s, vals:s.get(from, to) }));
  const all = series.flatMap(s => s.vals.map(p => p[1])).filter(v => v !== null && isFinite(v));
  if (!all.length) return null;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (t.zero) lo = Math.min(0, lo);
  const g = frame(svg, W, H, [from, to], [lo, hi], { ytick:t.ytick });
  for (const s of series) {
    if (s.area) {
      const base = g.Y(Math.max(g.yd.lo, 0));
      const d = pathOf(s.vals, g.X, g.Y);
      if (d) {
        const first = s.vals.find(p => p[1] !== null), last = [...s.vals].reverse().find(p => p[1] !== null);
        svg.appendChild(el("path", { d:d + " L" + g.X(last[0]) + " " + base +
          " L" + g.X(first[0]) + " " + base + " Z", fill:s.col, opacity:".14" }));
      }
    }
    svg.appendChild(el("path", { d:pathOf(s.vals, g.X, g.Y), fill:"none", stroke:s.col,
      "stroke-width":s.w || 2, "stroke-linejoin":"round", "stroke-linecap":"round" }));
  }
  crosshair(svg, g, W, H, from, to, i => series.map(s => {
    const p = s.vals[i - from]; return p && p[1] !== null
      ? `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${s.col};margin-right:5px"></i>${s.name} <span class="v">${(t.fmt || FMT.num0)(p[1])}</span>` : null;
  }).filter(Boolean).join("<br>"));
  return {
    stats:stats(series[0].vals.map(p => p[1])),
    table:tableOf(series, from, to, t.fmt),
  };
}

/* Diverging area around zero: the two arms are a polarity, not two series, so they
   take the diverging poles and the midpoint is the axis itself. */
function rDiverge(svg, W, H, t, from, to) {
  const vals = t.get(from, to);
  const nums = vals.map(p => p[1]).filter(v => v !== null && isFinite(v));
  if (!nums.length) return null;
  const m = Math.max(Math.abs(Math.min(...nums)), Math.abs(Math.max(...nums)));
  const g = frame(svg, W, H, [from, to], [-m, m], { ytick:t.ytick });
  const zero = g.Y(0);
  for (const sign of [1, -1]) {
    const clipped = vals.map(([x, v]) => [x, v === null ? null : (sign > 0 ? Math.max(0, v) : Math.min(0, v))]);
    const d = pathOf(clipped, g.X, g.Y);
    if (!d) continue;
    const f = clipped.find(p => p[1] !== null), l = [...clipped].reverse().find(p => p[1] !== null);
    svg.appendChild(el("path", { d:d + " L" + g.X(l[0]) + " " + zero + " L" + g.X(f[0]) + " " + zero + " Z",
      fill:sign > 0 ? C_POS : C_NEG, opacity:".26" }));
  }
  svg.appendChild(el("path", { d:pathOf(vals, g.X, g.Y), fill:"none",
    stroke:"var(--ink-soft)", "stroke-width":1.2, opacity:".55" }));
  crosshair(svg, g, W, H, from, to, i => {
    const p = vals[i - from]; if (!p || p[1] === null) return null;
    const s = p[1] >= 0 ? "fresco" : "carico";
    return `${t.name} <span class="v">${(t.fmt || FMT.num0)(p[1])}</span><br><span class="d">${s}</span>`;
  });
  return { stats:stats(vals.map(p => p[1])), table:tableOf([{ name:t.name, vals }], from, to, t.fmt) };
}
const C_POS = "#3987e5", C_NEG = "#e66767";

function rBars(svg, W, H, t, from, to) {
  const plan = bucketPlan(from, to);
  const b = aggregate(t.arr, from, to, t.how || "sum", plan.step)
    .map(o => ({ ...o, v:t.scale ? t.scale(o.v) : o.v }))
    .filter(o => o.v !== null && isFinite(o.v));
  if (!b.length) return null;
  const hi = Math.max(...b.map(o => o.v));
  const g = frame(svg, W, H, [from, to], [0, hi], { ytick:t.ytick });
  /* Barre. Una quantita' sommata su un intervallo e' un'area, non un punto: la
     barra dice "in questa settimana, tanto", la linea direbbe "in questo istante,
     tanto" — che di una somma non e' vero. */
  const bw = Math.max(1.2, Math.min(22, g.iw / b.length - 1.6));
  for (const o of b) {
    const x = g.X(o.i) - bw / 2, y = g.Y(o.v);
    const r = el("rect", { x, y, width:bw, height:Math.max(.8, g.Y(0) - y),
      rx:Math.min(2, bw / 2), fill:t.col, style:"cursor:pointer" });
    r.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
      `<span class="d">${bucketLabel(o.k, plan.step)}</span><br>${t.name} <span class="v">${(t.fmt || FMT.num0)(o.v)}</span>`));
    r.addEventListener("pointerleave", hideTip);
    r.addEventListener("click", () => openDay(o.i));
    svg.appendChild(r);
  }
  return { stats:stats(b.map(o => o.v)), plan,
    table:`<tr><th>${plan.label}</th><th>${t.name}</th></tr>` +
      b.slice(-40).reverse().map(o => `<tr><td>${bucketLabel(o.k, plan.step)}</td><td>${(t.fmt || FMT.num0)(o.v)}</td></tr>`).join("") };
}

/* Stacked bars. A 2px surface gap between segments so adjacent fills never fuse. */
function rStack(svg, W, H, t, from, to) {
  const plan = bucketPlan(from, to);
  const cols = t.cols, names = t.names;
  const per = t.arrs.map(a => aggregate(a, from, to, "sum", plan.step));
  const keys = per[0] ? per[0].map(o => o.k) : [];
  if (!keys.length) return null;
  const rows = keys.map((k, j) => ({ k, i:per[0][j].i,
    parts:per.map(p => (t.scale ? t.scale(p[j].v) : p[j].v) || 0) }));
  const hi = Math.max(...rows.map(r => r.parts.reduce((a, b) => a + b, 0)));
  if (!(hi > 0)) return null;
  const g = frame(svg, W, H, [from, to], [0, hi], { ytick:t.ytick });
  /* Impilate: la domanda qui e' una composizione — quanto fa il totale e come si
     divide — e impilare e' l'unica forma che risponde a tutte e due insieme.
     2px di superficie fra un segmento e l'altro, o due colori adiacenti si
     fondono in una banda sola. */
  const bw = Math.max(1.6, Math.min(26, g.iw / rows.length - 1.8));
  for (const r of rows) {
    let acc = 0;
    const total = r.parts.reduce((a, b) => a + b, 0);
    r.parts.forEach((v, si) => {
      if (!(v > 0)) return;
      const yTop = g.Y(acc + v), yBot = g.Y(acc);
      const h = Math.max(.8, yBot - yTop - (acc > 0 ? 2 : 0));
      const rect = el("rect", { x:g.X(r.i) - bw / 2, y:yTop, width:bw, height:h,
        rx:Math.min(2, bw / 2), fill:cols[si], style:"cursor:pointer" });
      rect.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
        `<span class="d">${bucketLabel(r.k, plan.step)}</span><br>` +
        r.parts.map((p, k) => p > 0 ? `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${cols[k]};margin-right:5px"></i>${names[k]} <span class="v">${(t.fmt || FMT.num1)(p)}</span>` : null).filter(Boolean).join("<br>") +
        `<br><span class="d">totale ${(t.fmt || FMT.num1)(total)}</span>`));
      rect.addEventListener("pointerleave", hideTip);
      rect.addEventListener("click", () => openDay(r.i));
      svg.appendChild(rect);
      acc += v;
    });
  }
  return { stats:stats(rows.map(r => r.parts.reduce((a, b) => a + b, 0))), plan,
    table:`<tr><th>${plan.label}</th>${names.map(n => `<th>${n}</th>`).join("")}</tr>` +
      rows.slice(-30).reverse().map(r => `<tr><td>${bucketLabel(r.k, plan.step)}</td>${r.parts.map(p => `<td>${(t.fmt || FMT.num1)(p)}</td>`).join("")}</tr>`).join("") };
}

/* The cloud-and-trend form: every day is a dot, the line is the trailing mean, and
   an optional band marks the reference the dots should be read against. */
function rCloud(svg, W, H, t, from, to) {
  const arr = t.arr;
  const days = to - from + 1;
  const pts = [];
  for (let i = from; i <= to; i++) if (arr[i] !== null && arr[i] !== undefined) pts.push([i, arr[i]]);
  if (!pts.length) return null;
  const mean = rolling(arr, from, to, t.win || 7);
  const nums = pts.map(p => p[1]);

  /* Il dominio y lo detta la MEDIA MOBILE, non i picchi giornalieri.
     Scalando sugli estremi, una notte da tre ore o un giorno da trentamila passi
     si prende meta' dell'altezza e schiaccia la media in una riga piatta — che e'
     esattamente la serie che si voleva guardare. Qui la banda della media occupa
     il grosso dell'altezza, allargata quel tanto che basta a contenere il corpo
     centrale della nuvola (dal 10esimo al 90esimo percentile). I punti che
     restano fuori non si disegnano, e il piede della scheda li conta: meglio
     dichiararli che appiattire tutto per farceli stare. */
  const mvals = mean.filter(v => v !== null && isFinite(v));
  const q = (a, p) => { const s = [...a].sort((x, y) => x - y);
    return s[Math.max(0, Math.min(s.length - 1, Math.round(p * (s.length - 1))))]; };
  let lo, hi;
  if (mvals.length >= 2) {
    const mLo = Math.min(...mvals), mHi = Math.max(...mvals);
    const pad = Math.max((mHi - mLo) * .45, Math.abs(mHi) * .02, 1e-6);
    lo = Math.min(mLo - pad, q(nums, .10));
    hi = Math.max(mHi + pad, q(nums, .90));
  } else {
    lo = Math.min(...nums); hi = Math.max(...nums);
    const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
  }
  if (t.band) { lo = Math.min(lo, t.band[0]); hi = Math.max(hi, t.band[1]); }
  if (t.zero) lo = Math.max(0, lo);
  const outside = nums.filter(v => v < lo || v > hi).length;
  const g = frame(svg, W, H, [from, to], [lo, hi], { ytick:t.ytick });
  const inRange = v => v >= g.yd.lo && v <= g.yd.hi;
  if (t.band) {
    const yA = g.Y(t.band[1]), yB = g.Y(t.band[0]);
    svg.appendChild(el("rect", { x:g.P.l, y:yA, width:g.iw, height:Math.max(1, yB - yA),
      fill:t.col, opacity:".07" }));
  }
  /* over ~800 days the dots stop being dots; the daily cloud becomes weekly means */
  if (days > 800) {
    const w = aggregate(arr, from, to, "mean", "w").filter(o => o.v !== null);
    for (const o of w) if (inRange(o.v))
      svg.appendChild(el("circle", { cx:g.X(o.i), cy:g.Y(o.v), r:1.6,
        fill:t.col, opacity:".5" }));
  } else {
    const r = days > 420 ? 1.5 : days > 200 ? 1.9 : days > 90 ? 2.4 : 3;
    for (const [x, y] of pts) if (inRange(y))
      svg.appendChild(el("circle", { cx:g.X(x), cy:g.Y(y), r,
        fill:t.col, opacity:".38" }));
  }
  svg.appendChild(el("path", { d:pathOf(mean.map((v, k) => [from + k, v]), g.X, g.Y),
    fill:"none", stroke:t.col, "stroke-width":2.2, "stroke-linejoin":"round",
    "stroke-linecap":"round" }));
  crosshair(svg, g, W, H, from, to, i => {
    const v = arr[i], m = mean[i - from];
    if (v === null && m === null) return null;
    return `${t.name} <span class="v">${(t.fmt || FMT.num0)(v)}</span>` +
      (m !== null ? `<br><span class="d">media ${t.win || 7} gg ${(t.fmt || FMT.num0)(m)}</span>` : "");
  });
  return { stats:stats(nums), outside,
    table:tableOf([{ name:t.name, vals:pts }], from, to, t.fmt, true) };
}

/* A step line: VO2max moves in plateaus, so joining the estimates with a slope would
   invent a smoothness the estimate does not have. */
function rStep(svg, W, H, t, from, to) {
  const pts = [];
  for (let i = from; i <= to; i++) if (t.arr[i] !== null && t.arr[i] !== undefined) pts.push([i, t.arr[i]]);
  if (!pts.length) return null;
  const nums = pts.map(p => p[1]);
  const g = frame(svg, W, H, [from, to], [Math.min(...nums) - .5, Math.max(...nums) + .5], { ytick:t.ytick });
  let d = "";
  pts.forEach(([x, y], k) => {
    d += (k ? "L" + g.X(x).toFixed(1) + " " + g.Y(pts[k - 1][1]).toFixed(1) + " L" : "M") +
      g.X(x).toFixed(1) + " " + g.Y(y).toFixed(1) + " ";
  });
  d += "L" + g.X(to).toFixed(1) + " " + g.Y(pts[pts.length - 1][1]).toFixed(1);
  svg.appendChild(el("path", { d, fill:"none", stroke:t.col, "stroke-width":2,
    "stroke-linejoin":"round" }));
  for (const [x, y] of pts) svg.appendChild(el("circle", { cx:g.X(x), cy:g.Y(y), r:2,
    fill:t.col, stroke:"var(--paper)", "stroke-width":1 }));
  crosshair(svg, g, W, H, from, to, i => {
    let last = null; for (const [x, y] of pts) if (x <= i) last = y;
    return last === null ? null : `${t.name} <span class="v">${(t.fmt || FMT.num1)(last)}</span>`;
  });
  return { stats:stats(nums), table:tableOf([{ name:t.name, vals:pts }], from, to, t.fmt, true) };
}

/* x-vs-y scatter with a least-squares line and its r. Groups are capped at two so the
   colours clear the all-pairs separation floor. */
function rXY(svg, W, H, t, from, to) {
  const groups = t.points(from, to);
  const all = groups.flatMap(g => g.pts);
  if (all.length < 4) return null;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const xd = nice(Math.min(...xs), Math.max(...xs)), yd = nice(Math.min(...ys), Math.max(...ys));
  const ticks = yTicks(yd, t.ytick || (v => nf(v, yd.step < 1 ? 1 : 0)));
  const P = { l:padFor(ticks), r:8, t:8, b:20 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X = v => P.l + (v - xd.lo) / (xd.hi - xd.lo) * iw;
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;
  yAxis(svg, ticks, Y, P.l, W - P.r);
  /* x ticks thinned to whatever fits: a label is only drawn if it clears the last
     one it was placed beside, so the axis never turns into overlapping ink */
  let lastRight = -1e9;
  for (let v = xd.lo; v <= xd.hi + 1e-9; v += xd.step) {
    if (v < Math.min(...xs) - xd.step || v > Math.max(...xs) + xd.step) continue;
    const lab = String((t.xtick || (u => nf(u, xd.step < 1 ? 1 : 0)))(v));
    const half = lab.length * TICKW / 2;
    if (X(v) - half < lastRight + 6 || X(v) + half > W) continue;
    lastRight = X(v) + half;
    const tx = axisText(X(v), H - 6, lab, "middle");
    tx.textContent = lab; svg.appendChild(tx);
  }
  groups.forEach(gr => {
    for (const p of gr.pts) {
      const c = el("circle", { cx:X(p[0]), cy:Y(p[1]), r:t.r || 2.6, fill:gr.col,
        opacity:".45", stroke:"var(--paper)", "stroke-width":.6 });
      c.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
        (p[2] !== undefined ? `<span class="d">${fmtDate(p[2])}</span><br>` : "") +
        `${t.xname} <span class="v">${(t.xfmt || FMT.num0)(p[0])}</span><br>` +
        `${t.yname} <span class="v">${(t.yfmt || FMT.num0)(p[1])}</span>` +
        (groups.length > 1 ? `<br><span class="d">${gr.name}</span>` : "")));
      c.addEventListener("pointerleave", hideTip);
      if (p[2] !== undefined) { c.setAttribute("style", "cursor:pointer");
        c.addEventListener("click", () => openDay(p[2])); }
      svg.appendChild(c);
    }
  });
  const f = fit(all.map(p => [p[0], p[1]]));
  if (f) {
    const xa = Math.min(...xs), xb = Math.max(...xs);
    svg.appendChild(el("line", { x1:X(xa), y1:Y(f.m * xa + f.b), x2:X(xb), y2:Y(f.m * xb + f.b),
      stroke:"var(--ink-soft)", "stroke-width":1.6, "stroke-dasharray":"5 3", opacity:".8" }));
  }
  return { fit:f, stats:stats(ys),
    table:`<tr><th>${t.xname}</th><th>${t.yname}</th></tr>` +
      all.slice(-30).reverse().map(p => `<tr><td>${(t.xfmt || FMT.num0)(p[0])}</td><td>${(t.yfmt || FMT.num0)(p[1])}</td></tr>`).join("") };
}

/* Seven categories, one series: plain bars with the spread drawn as a whisker, so the
   weekday effect is read against how noisy each weekday is. */
function rDow(svg, W, H, t, from, to) {
  const buckets = Array.from({ length:7 }, () => []);
  for (let i = from; i <= to; i++) {
    const v = t.arr[i]; if (v === null || v === undefined) continue;
    buckets[(dayDate(i).getDay() + 6) % 7].push(v);
  }
  if (!buckets.some(b => b.length)) return null;
  const st = buckets.map(b => stats(b));
  const lo = Math.min(...st.filter(Boolean).map(s => s.min));
  const hi = Math.max(...st.filter(Boolean).map(s => s.max));
  const yd = nice(lo, hi);
  const ticks = yTicks(yd, t.ytick || (v => nf(v, 0)));
  const P = { l:padFor(ticks), r:8, t:8, b:16 }, iw = W - P.l - P.r, ih = H - P.t - P.b;
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;
  yAxis(svg, ticks, Y, P.l, W - P.r);
  const slot = iw / 7, bw = Math.min(26, slot * .52);
  st.forEach((s, k) => {
    if (!s) return;
    const cx = P.l + slot * (k + .5);
    svg.appendChild(el("line", { x1:cx, x2:cx, y1:Y(s.min), y2:Y(s.max),
      stroke:t.col, "stroke-width":1, opacity:".35" }));
    const r = el("rect", { x:cx - bw / 2, y:Y(s.mean), width:bw,
      height:Math.max(1.5, Y(yd.lo) - Y(s.mean)), rx:2, fill:t.col });
    r.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
      `<span class="d">${DOW[k]} · ${s.n} giorni</span><br>media <span class="v">${(t.fmt || FMT.num0)(s.mean)}</span>` +
      `<br><span class="d">da ${(t.fmt || FMT.num0)(s.min)} a ${(t.fmt || FMT.num0)(s.max)}</span>`));
    r.addEventListener("pointerleave", hideTip);
    svg.appendChild(r);
    const tx = axisText(cx, H - 4, DOW[k], "middle");
    tx.textContent = DOW[k]; svg.appendChild(tx);
  });
  const best = st.map((s, k) => s ? [s.mean, k] : null).filter(Boolean).sort((a, b) => b[0] - a[0])[0];
  return { stats:stats(buckets.flat()), best:best && DOW[best[1]],
    table:`<tr><th>giorno</th><th>media</th><th>n</th></tr>` +
      st.map((s, k) => s ? `<tr><td>${DOW[k]}</td><td>${(t.fmt || FMT.num0)(s.mean)}</td><td>${s.n}</td></tr>` : "").join("") };
}

/* Matrice di dispersione: righe × colonne di mini-scatter, ognuno con la sua retta
   e la sua r. Serve a guardare nove ipotesi insieme invece che una alla volta —
   ed è l'unico modo onesto di mostrarne nove, perché nove riquadri separati
   inviterebbero a raccontare la più forte e tacere le altre otto.
   La cella è colorata dalla FORZA della correlazione, non dal suo segno preso a sé:
   una scala divergente blu↔rosso attorno allo zero, grigio in mezzo. Il grigio
   centrale è la maggioranza dei casi, ed è giusto che lo sia. */
function rMatrix(svg, W, H, t, from, to) {
  const rows = t.rows, cols = t.cols;
  /* la gronda si misura sui nomi delle righe, come ogni altro asse della pagina:
     a corpo 10 "Qualità" e' 42px e in 44 non ci sta */
  const gap = 6, labT = 15;
  const labL = Math.min(96, Math.max(40, Math.ceil(
    Math.max(...rows.map(r => r.name.length)) * TICKW) + 8));
  const cw = (W - labL - gap * (cols.length - 1)) / cols.length;
  const ch = (H - labT - gap * (rows.length - 1)) / rows.length;
  if (cw < 24 || ch < 20) return null;

  let best = null, n_ok = 0;
  const table = [];
  cols.forEach((c, ci) => {
    const tx = axisText(labL + ci * (cw + gap) + cw / 2, 10, c.name, "middle");
    tx.textContent = c.name; svg.appendChild(tx);
  });
  rows.forEach((r, ri) => {
    const ty = axisText(labL - 6, labT + ri * (ch + gap) + ch / 2 + 3.5, r.name, "end");
    ty.textContent = r.name; svg.appendChild(ty);

    cols.forEach((c, ci) => {
      const x0 = labL + ci * (cw + gap), y0 = labT + ri * (ch + gap);
      const pts = [];
      for (let i = from; i <= to; i++) {
        const a = c.arr[i], b = r.arr[i];
        if (a === null || a === undefined || b === null || b === undefined) continue;
        pts.push([a, b, i]);
      }
      const f = fit(pts.map(p => [p[0], p[1]]));
      const strength = f ? Math.abs(f.r) : 0;
      /* fondo divergente: |r| porta l'intensità, il segno il verso */
      const bg = !f ? "rgba(236,227,205,.03)"
        : (f.r >= 0 ? `rgba(57,135,229,${(strength * .30).toFixed(3)}`
                    : `rgba(230,103,103,${(strength * .30).toFixed(3)}`) + ")";
      svg.appendChild(el("rect", { x:x0, y:y0, width:cw, height:ch, rx:3, fill:bg,
        stroke:"rgba(236,227,205,.10)", "stroke-width":1 }));
      if (!pts.length) return;
      n_ok++;
      const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
      const xa = Math.min(...xs), xb = Math.max(...xs);
      const ya = Math.min(...ys), yb = Math.max(...ys);
      const PX = v => x0 + 3 + (xb === xa ? cw / 2 - 3 : (v - xa) / (xb - xa) * (cw - 6));
      const PY = v => y0 + ch - 3 - (yb === ya ? ch / 2 - 3 : (v - ya) / (yb - ya) * (ch - 6));
      for (const p of pts) {
        const dot = el("circle", { cx:PX(p[0]), cy:PY(p[1]), r:1.5, fill:t.col,
          opacity:".5" });
        dot.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
          `<span class="d">${fmtDate(p[2])}</span><br>${c.name} <span class="v">${(c.fmt || FMT.num0)(p[0])}</span>` +
          `<br>${r.name} <span class="v">${(r.fmt || FMT.num0)(p[1])}</span>`));
        dot.addEventListener("pointerleave", hideTip);
        dot.addEventListener("click", () => openDay(p[2]));
        svg.appendChild(dot);
      }
      if (f) {
        svg.appendChild(el("line", { x1:PX(xa), y1:PY(f.m * xa + f.b),
          x2:PX(xb), y2:PY(f.m * xb + f.b), stroke:"var(--ink-soft)",
          "stroke-width":1.1, opacity:".75" }));
        const lab = axisText(x0 + cw - 3, y0 + 10, "", "end");
        lab.setAttribute("fill", strength >= .3 ? "var(--ink)" : "var(--muted)");
        lab.setAttribute("font-size", "8.5");
        lab.textContent = (f.r >= 0 ? "+" : "") + f.r.toFixed(2);
        svg.appendChild(lab);
        table.push([`${r.name} ↔ ${c.name}`, f.r, f.n]);
        if (!best || strength > Math.abs(best[1])) best = [`${r.name} ↔ ${c.name}`, f.r, f.n];
      }
    });
  });
  if (!n_ok) return null;
  table.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  return {
    best2:best && `più forte ${best[0]} r ${(best[1] >= 0 ? "+" : "") + best[1].toFixed(2)} su ${best[2]} giorni`,
    table:`<tr><th>coppia</th><th>r</th><th>giorni</th></tr>` +
      table.map(([k, r, n]) => `<tr><td>${k}</td><td>${(r >= 0 ? "+" : "") + r.toFixed(2)}</td><td>${n}</td></tr>`).join(""),
  };
}

/* Heatmap di correlazione. E' l'unico posto della pagina dove una griglia batte
   tutto il resto: con dodici serie ci sono 66 coppie, e 66 scatter non si guardano.
   Qui il colore porta un valore continuo con un segno — quindi scala DIVERGENTE
   (blu positivo ↔ rosso negativo) con il grigio nel mezzo, mai un arcobaleno, e il
   grigio centrale e' la maggioranza delle celle perche' la maggioranza delle
   correlazioni e' nulla. Il numero e' scritto in ogni cella che ha spazio: il
   colore da solo non si legge a due decimali, e serve anche a chi non lo distingue.
   Solo il triangolo inferiore: la matrice e' simmetrica, disegnarla tutta sarebbe
   il doppio dell'inchiostro per zero informazione in piu'. */
function rHeat(svg, W, H, t, from, to) {
  const V = t.vars.filter(v => Array.isArray(v.arr));
  const n = V.length;
  if (n < 3) return null;

  const labL = Math.min(104, Math.max(52, Math.ceil(
    Math.max(...V.map(v => v.name.length)) * TICKW) + 8));
  const labB = 58, pad = 1.5;
  const cell = Math.min((W - labL - 8) / (n - 1), (H - labB - 8) / (n - 1));
  if (cell < 14) return null;
  const x0 = labL, y0 = 6;

  const pear = (a, b) => {
    const pts = [];
    for (let i = from; i <= to; i++) {
      const p = a[i], q = b[i];
      if (p === null || p === undefined || q === null || q === undefined) continue;
      pts.push([p, q]);
    }
    if (pts.length < 20) return null;         /* sotto i 20 giorni non si dice niente */
    const f = fit(pts);
    return f ? { r: f.r, n: f.n } : null;
  };

  const rows = [];
  let strongest = null;
  /* riga i = variabile i+1, colonna j = variabile j — triangolo inferiore */
  for (let i = 1; i < n; i++) {
    for (let j = 0; j < i; j++) {
      const res = pear(V[i].arr, V[j].arr);
      const cx = x0 + j * cell, cy = y0 + (i - 1) * cell;
      const g = res ? Math.min(1, Math.abs(res.r) / 0.6) : 0;
      /* il grigio del fondo scheda e' il punto zero: da li' ci si allontana verso
         il blu o verso il rosso, e la distanza e' |r| */
      const fill = !res ? "rgba(236,227,205,.035)"
        : (res.r >= 0 ? `rgba(57,135,229,${(g * .78).toFixed(3)})`
                      : `rgba(230,103,103,${(g * .78).toFixed(3)})`);
      const rect = el("rect", { x:cx + pad, y:cy + pad, width:cell - pad * 2,
        height:cell - pad * 2, rx:2, fill,
        stroke:"rgba(236,227,205,.08)", "stroke-width":1 });
      if (res) {
        rect.setAttribute("style", "cursor:pointer");
        rect.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
          `${V[i].name} ↔ ${V[j].name}<br><span class="v">r ${(res.r >= 0 ? "+" : "") + res.r.toFixed(2)}</span>` +
          `<br><span class="d">su ${nf(res.n)} giorni</span>`));
        rect.addEventListener("pointerleave", hideTip);
        rows.push([`${V[i].name} ↔ ${V[j].name}`, res.r, res.n]);
        if (!strongest || Math.abs(res.r) > Math.abs(strongest[1])) {
          strongest = [`${V[i].name} ↔ ${V[j].name}`, res.r, res.n];
        }
      }
      svg.appendChild(rect);
      if (res && cell >= 26) {
        const tx = el("text", { x:cx + cell / 2, y:cy + cell / 2 + 3,
          "text-anchor":"middle", "font-size":"8.5",
          "font-family":"'IBM Plex Mono',monospace",
          fill:g > .55 ? "var(--ink)" : "var(--muted)" });
        tx.textContent = (res.r >= 0 ? "+" : "") + res.r.toFixed(2).replace("0.", ".");
        svg.appendChild(tx);
      }
    }
  }
  /* etichette: righe a sinistra, colonne in basso ruotate — a orizzontale si
     sovrapporrebbero, ed e' il difetto classico di ogni heatmap */
  for (let i = 1; i < n; i++) {
    const ty = axisText(labL - 6, y0 + (i - 1) * cell + cell / 2 + 3, V[i].name, "end");
    ty.textContent = V[i].name; svg.appendChild(ty);
  }
  for (let j = 0; j < n - 1; j++) {
    const cx = x0 + j * cell + cell / 2, cy = y0 + (n - 1) * cell + 7;
    const tx = el("text", { x:cx, y:cy, "text-anchor":"end", "font-size":"8",
      "font-family":"'IBM Plex Mono',monospace", fill:"var(--muted)",
      transform:`rotate(-52 ${cx.toFixed(1)} ${cy.toFixed(1)})` });
    tx.textContent = V[j].name; svg.appendChild(tx);
  }
  rows.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  return {
    best2:strongest && `più forte ${strongest[0]} r ${(strongest[1] >= 0 ? "+" : "") + strongest[1].toFixed(2)}`,
    table:`<tr><th>coppia</th><th>r</th><th>giorni</th></tr>` +
      rows.slice(0, 40).map(([k, r, nn]) => `<tr><td>${k}</td><td>${(r >= 0 ? "+" : "") + r.toFixed(2)}</td><td>${nn}</td></tr>`).join(""),
  };
}

/* Griglia generica: righe × colonne, un valore per cella, colore = valore.
   La usano la matrice alimenti × generi e la striscia temporale. Il colore e'
   divergente quando il valore ha un segno (blu sopra zero, rosso sotto, grigio in
   mezzo) e sequenziale a una tinta sola quando e' solo una grandezza — mai un
   arcobaleno, e mai una tinta al centro di una divergente. */
function rGrid(svg, W, H, t, from, to) {
  const rows = t.rows, cols = t.cols;
  if (!rows.length || !cols.length) return null;
  const labL = Math.min(t.labMax || 118, Math.max(46, Math.ceil(
    Math.max(...rows.map(r => r.name.length)) * TICKW) + 8));
  const labB = t.labB ?? 56, pad = 1.2, top = 6;
  const cw = (W - labL - 8) / cols.length;
  const ch = (H - labB - top) / rows.length;
  if (cw < 8 || ch < 9) return null;

  let hottest = null;
  const cells = [];
  rows.forEach((r, i) => {
    cols.forEach((c, j) => {
      const cell = t.cell(i, j);
      const x = labL + j * cw, y = top + i * ch;
      let fill = "rgba(236,227,205,.035)";
      if (cell && cell.v !== null && cell.v !== undefined) {
        const g = Math.min(1, Math.abs(cell.v) / (t.vmax || 1));
        fill = t.diverging === false
          ? `rgba(57,135,229,${(g * .80).toFixed(3)})`
          : (cell.v >= 0 ? `rgba(57,135,229,${(g * .80).toFixed(3)}`
                         : `rgba(230,103,103,${(g * .80).toFixed(3)}`) + ")";
        if (!hottest || Math.abs(cell.v) > Math.abs(hottest.v)) hottest = { ...cell, i, j };
        cells.push([r.name, c.name, cell]);
      }
      const rect = el("rect", { x:x + pad, y:y + pad, width:Math.max(1, cw - pad * 2),
        height:Math.max(1, ch - pad * 2), rx:2, fill,
        stroke:"rgba(236,227,205,.07)", "stroke-width":1 });
      if (cell && cell.tip) {
        rect.setAttribute("style", "cursor:pointer");
        rect.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY, cell.tip));
        rect.addEventListener("pointerleave", hideTip);
        if (cell.day !== undefined) rect.addEventListener("click", () => openDay(cell.day));
      }
      svg.appendChild(rect);
      if (cell && cell.txt && cw >= 26 && ch >= 15) {
        const tx = el("text", { x:x + cw / 2, y:y + ch / 2 + 3, "text-anchor":"middle",
          "font-size":"8", "font-family":"'IBM Plex Mono',monospace",
          fill:Math.abs(cell.v) / (t.vmax || 1) > .55 ? "var(--ink)" : "var(--muted)" });
        tx.textContent = cell.txt; svg.appendChild(tx);
      }
    });
    const ty = axisText(labL - 5, top + i * ch + ch / 2 + 3, r.name, "end");
    ty.textContent = r.name; svg.appendChild(ty);
  });
  /* etichette di colonna ruotate: a orizzontale si sovrappongono, ed e' il
     difetto classico di ogni heatmap con piu' di cinque colonne */
  const every = Math.max(1, Math.ceil(cols.length / (t.maxColLabels || 14)));
  cols.forEach((c, j) => {
    if (j % every) return;
    const cx = labL + j * cw + cw / 2, cy = top + rows.length * ch + 7;
    const tx = el("text", { x:cx, y:cy, "text-anchor":"end", "font-size":"8",
      "font-family":"'IBM Plex Mono',monospace", fill:"var(--muted)",
      transform:`rotate(-52 ${cx.toFixed(1)} ${cy.toFixed(1)})` });
    tx.textContent = c.name; svg.appendChild(tx);
  });
  return { best2:t.summary ? t.summary(hottest, cells) : null,
           table:t.table ? t.table(cells) : "" };
}

/* Slope chart: ogni genere e' una linea con due punti, da com'era a com'e'.
   E' la forma giusta per "distribuzione + come e' cambiata": la y resta la quota,
   quindi si legge la composizione, e la pendenza e' il cambiamento. Dieci linee
   sovrapposte in un grafico temporale sarebbero state illeggibili, e dieci colori
   non passerebbero comunque nessuna soglia di separazione — qui il colore porta
   solo il SEGNO (sale/scende), l'identita' sta nell'etichetta accanto al punto. */
function rSlope(svg, W, H, t, from, to) {
  const items = t.items.map(it => {
    const a = it.arr, s = a[from], e = a[to];
    let s2 = s, e2 = e;
    if (s2 === null || s2 === undefined)
      for (let i = from; i <= to; i++) if (a[i] !== null) { s2 = a[i]; break; }
    if (e2 === null || e2 === undefined)
      for (let i = to; i >= from; i--) if (a[i] !== null) { e2 = a[i]; break; }
    return { ...it, a:s2, b:e2 };
  }).filter(it => it.a !== null && it.a !== undefined && it.b !== null && it.b !== undefined);
  if (items.length < 2) return null;

  const vals = items.flatMap(it => [it.a, it.b]);
  const yd = nice(Math.min(...vals), Math.max(...vals));
  const ticks = yTicks(yd, v => nf(v, 0) + "%");
  const labW = 118;
  const P = { l:padFor(ticks), r:labW, t:12, b:22 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  if (iw < 60) return null;
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;
  yAxis(svg, ticks, Y, P.l, P.l + iw);

  const xa = P.l + 6, xb = P.l + iw - 6;
  for (const [x, lab] of [[xa, t.labA], [xb, t.labB]]) {
    const tx = axisText(x, H - 6, lab, x === xa ? "start" : "end");
    tx.textContent = lab; svg.appendChild(tx);
  }
  /* le etichette a destra si scostano finche' non si toccano piu': con dieci
     generi due quote vicine scriverebbero una sopra l'altra */
  const order = [...items].sort((p, q) => q.b - p.b);
  let prev = -1e9;
  for (const it of order) {
    it._ly = Math.max(Y(it.b), prev + 12);
    prev = it._ly;
  }
  for (const it of items) {
    const up = it.b >= it.a;
    const col = up ? "var(--s1)" : "var(--neg)";
    svg.appendChild(el("line", { x1:xa, y1:Y(it.a), x2:xb, y2:Y(it.b),
      stroke:col, "stroke-width":1.8, opacity:".85" }));
    for (const [x, v] of [[xa, it.a], [xb, it.b]])
      svg.appendChild(el("circle", { cx:x, cy:Y(v), r:3, fill:col,
        stroke:"var(--paper)", "stroke-width":1 }));
    const lab = el("text", { x:xb + 8, y:it._ly + 3.5, fill:"var(--ink-soft)",
      "font-size":"9", "font-family":"'IBM Plex Mono',monospace" });
    lab.textContent = `${it.emoji} ${it.name} ${(it.b - it.a >= 0 ? "+" : "")}${(it.b - it.a).toFixed(1)}`;
    svg.appendChild(lab);
    svg.appendChild(el("line", { x1:xb + 3, y1:Y(it.b), x2:xb + 6, y2:it._ly,
      stroke:"var(--rule)", "stroke-width":1 }));
  }
  const moved = [...items].sort((p, q) => Math.abs(q.b - q.a) - Math.abs(p.b - p.a))[0];
  return {
    best2:`si muove di piu' ${moved.name} ${(moved.b - moved.a >= 0 ? "+" : "")}${(moved.b - moved.a).toFixed(1)} punti`,
    table:`<tr><th>genere</th><th>${t.labA}</th><th>${t.labB}</th><th>Δ</th></tr>` +
      order.map(it => `<tr><td>${it.emoji} ${it.name}</td><td>${it.a.toFixed(2)}%</td><td>${it.b.toFixed(2)}%</td><td>${(it.b - it.a >= 0 ? "+" : "")}${(it.b - it.a).toFixed(2)}</td></tr>`).join(""),
  };
}

/* One crosshair implementation for every day-indexed renderer. */
function crosshair(svg, g, W, H, from, to, describe) {
  const line = el("line", { y1:g.P.t, y2:g.P.t + g.ih, stroke:"var(--gold)",
    "stroke-width":1, opacity:"0", "pointer-events":"none" });
  svg.appendChild(line);
  const hit = el("rect", { x:g.P.l, y:g.P.t, width:g.iw, height:g.ih, fill:"transparent" });
  const at = ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const i = Math.round(from + (px - g.P.l) / g.iw * (to - from));
    if (i < from || i > to) return;
    const html = describe(i);
    line.setAttribute("x1", g.X(i)); line.setAttribute("x2", g.X(i));
    line.setAttribute("opacity", html ? ".55" : "0");
    if (html) showTip(ev.clientX, ev.clientY, `<span class="d">${fmtDate(i)}</span><br>${html}`);
    else hideTip();
  };
  hit.addEventListener("pointermove", at);
  hit.addEventListener("pointerenter", at);
  hit.addEventListener("pointerleave", () => { line.setAttribute("opacity", "0"); hideTip(); });
  /* un click sul grafico apre la giornata sotto il cursore */
  hit.setAttribute("style", "cursor:pointer");
  hit.addEventListener("click", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const i = Math.round(from + (px - g.P.l) / g.iw * (to - from));
    if (i >= from && i <= to) openDay(i);
  });
  svg.appendChild(hit);
}

function tableOf(series, from, to, fmt, sparse) {
  /* the fallback is a summary, not a dump: at most 30 rows, newest first */
  const rows = [];
  const s0 = series[0].vals;
  const step = Math.max(1, Math.ceil(s0.length / 30));
  for (let k = s0.length - 1; k >= 0; k -= step) {
    const p = s0[k]; if (!p || p[1] === null) continue;
    rows.push(`<tr><td>${fmtDate(p[0])}</td>` +
      series.map(s => { const q = s.vals.find(v => v[0] === p[0]);
        return `<td>${q && q[1] !== null ? (fmt || FMT.num0)(q[1]) : "—"}</td>`; }).join("") + "</tr>");
    if (rows.length >= 30) break;
  }
  return `<tr><th>data</th>${series.map(s => `<th>${s.name}</th>`).join("")}</tr>` + rows.join("");
}

/* ------------------------------------------------------------------ tiles */
const secsOf = (() => {                       /* daily activity aggregates, once */
  const secs = new Array(N).fill(0), dist = new Array(N).fill(0),
        gain = new Array(N).fill(0), cnt = new Array(N).fill(0);
  const bySport = D.sports.map(() => new Array(N).fill(0));
  for (const [i, sp, s, m, up] of D.acts) {
    secs[i] += s; dist[i] += m; gain[i] += up; cnt[i] += 1; bySport[sp][i] += s;
  }
  return { secs, dist, gain, cnt, bySport };
})();

const daysOf = f => D.first[f] ?? 0;
/* a day index on an x axis is meaningless as a number — label it as a month.
   Declared up here because TILES reads it while it is being built. */
const monthTick = v => { const d = dayDate(Math.round(v));
  return MON[d.getMonth()] + " " + String(d.getFullYear()).slice(2); };
const S = D.sports;
const SC = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
const SCH = [C_POS, "#d95926", "#199e70", "#c98500"];

const TILES = [
  /* ---- Carico ---- */
  { panel:"carico", cls:"wide", h:190, first:"load",
    title:"Fitness e fatica", cap:"CTL e ATL · giorno per giorno",
    legend:[["Fitness (CTL)", SCH[0]], ["Fatica (ATL)", SCH[1]]],
    now:() => D.ctl[N - 1], nowFmt:FMT.num0, nowUnit:"CTL oggi",
    kind:rLines, spec:{ zero:true, fmt:FMT.num0, series:[
      { name:"Fitness (CTL)", col:SCH[0], area:true, get:(a, b) => D.ctl.slice(a, b + 1).map((v, k) => [a + k, v]) },
      { name:"Fatica (ATL)", col:SCH[1], get:(a, b) => D.atl.slice(a, b + 1).map((v, k) => [a + k, v]) },
    ] },
    foot:"Arancio sopra blu: si sta scavando." },

  { panel:"carico", cls:"wide", h:150, first:"load",
    title:"Forma", cap:"CTL − ATL · sopra lo zero si è freschi",
    now:() => D.ctl[N - 1] - D.atl[N - 1], nowFmt:FMT.num0, nowUnit:"forma oggi",
    kind:rDiverge, spec:{ name:"Forma", fmt:FMT.num0,
      get:(a, b) => { const o = []; for (let i = a; i <= b; i++) o.push([i, D.ctl[i] === null || D.atl[i] === null ? null : D.ctl[i] - D.atl[i]]); return o; } },
    foot:"Blu credito, rosso debito." },

  { panel:"carico", h:170, first:"load", title:"Carico", cap:"TSS sommato",
    now:() => D.load.slice(N - 7).reduce((a, b) => a + (b || 0), 0), nowFmt:FMT.num0, nowUnit:"TSS ultimi 7 gg",
    kind:rBars, spec:{ name:"Carico", arr:D.load, how:"sum", col:"var(--s1)", fmt:FMT.tss } },

  { panel:"carico", h:170, first:"act", title:"Ore", cap:"tempo in movimento",
    now:() => secsOf.secs.slice(N - 7).reduce((a, b) => a + b, 0) / 3600, nowFmt:FMT.num1, nowUnit:"ore ultimi 7 gg",
    kind:rBars, spec:{ name:"Ore", arr:secsOf.secs, how:"sum", scale:v => v / 3600,
      col:"var(--s3)", fmt:FMT.hours } },

  /* ---- Notte ---- */
  { panel:"notte", cls:"half", h:180, first:"sleep",
    title:"Durata del sonno", cap:"ogni notte · media mobile 7 giorni",
    now:() => { const r = rolling(D.sleep, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.hhmm, nowUnit:"media 7 notti",
    kind:rCloud, spec:{ name:"Sonno", arr:D.sleep, col:"var(--s1)", fmt:FMT.hhmm,
      band:[420, 480], win:7, ytick:v => (v / 60).toFixed(0) + "h" },
    foot:"Fascia: 7–8 ore." },

  { panel:"notte", h:180, first:"score", title:"Punteggio del sonno",
    cap:"come lo valuta l'orologio · 0–100",
    now:() => { const r = rolling(D.score, N - 14, N - 1, 14); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"media 14 notti",
    kind:rCloud, spec:{ name:"Punteggio", arr:D.score, col:"var(--s3)", fmt:FMT.num0, win:14 } },

  { panel:"notte", h:180, first:"sleep", title:"Sonno per giorno della settimana",
    cap:"media · il baffo è l'escursione fra la notte più corta e la più lunga",
    kind:rDow, spec:{ name:"Sonno", arr:D.sleep, col:"var(--s4)", fmt:FMT.hhmm,
      ytick:v => (v / 60).toFixed(0) + "h" } },

  /* ---- Recupero ---- */
  { panel:"recupero", cls:"half", h:180, first:"hrv",
    title:"HRV", cap:"variabilità cardiaca al risveglio · media mobile 7 giorni",
    now:() => { const r = rolling(D.hrv, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"ms, media 7 gg",
    kind:rCloud, spec:{ name:"HRV", arr:D.hrv, col:"var(--s2)", fmt:FMT.ms, win:7 },
    foot:"Conta la media, non il singolo giorno." },

  { panel:"recupero", h:180, first:"rhr", title:"Frequenza a riposo",
    cap:"battiti al minuto · media mobile 7 giorni",
    now:() => { const r = rolling(D.rhr, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"bpm, media 7 gg",
    kind:rCloud, spec:{ name:"FC a riposo", arr:D.rhr, col:"var(--s1)", fmt:FMT.bpm, win:7 } },

  { panel:"recupero", h:180, first:"vo2", title:"VO₂max stimato",
    cap:"stima dell'orologio · ml/kg/min",
    now:() => { for (let i = N - 1; i >= 0; i--) if (D.vo2[i] !== null) return D.vo2[i]; return null; },
    nowFmt:FMT.num1, nowUnit:"ml/kg/min",
    kind:rStep, spec:{ name:"VO₂max", arr:D.vo2, col:"var(--s3)", fmt:FMT.num1 },
    foot:"A gradini: la stima si aggiorna a scatti." },

  { panel:"recupero", h:180, first:"steps", title:"Passi", cap:"al giorno · media mobile 7 giorni",
    now:() => { const r = rolling(D.steps, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"passi/giorno",
    kind:rCloud, spec:{ name:"Passi", arr:D.steps, col:"var(--s4)", fmt:FMT.num0, zero:true,
      ytick:v => v >= 1000 ? (v / 1000) + "k" : String(v) } },

  /* ---- Corpo ---- */
  { panel:"corpo", h:180, first:"weight", title:"Peso", cap:"ogni pesata registrata",
    now:() => { for (let i = N - 1; i >= 0; i--) if (D.weight[i] !== null) return D.weight[i]; return null; },
    nowFmt:FMT.num1, nowUnit:"kg, ultima pesata",
    kind:rXY, spec:{ xname:"giorno", yname:"Peso", yfmt:FMT.kg, r:3.2,
      xfmt:v => fmtDate(Math.round(v)), xtick:monthTick,
      points:(a, b) => [{ name:"Peso", col:"var(--s2)", pts:sparsePts(D.weight, a, b) }] },
    foot:"65 pesate: una nuvola, non una serie." },

  { panel:"corpo", h:180, first:"bodyfat", title:"Massa grassa", cap:"stima della bilancia · %",
    now:() => { for (let i = N - 1; i >= 0; i--) if (D.bodyfat[i] !== null) return D.bodyfat[i]; return null; },
    nowFmt:FMT.num1, nowUnit:"%, ultima misura",
    kind:rXY, spec:{ xname:"giorno", yname:"Massa grassa", yfmt:FMT.pct, r:3.2,
      xfmt:v => fmtDate(Math.round(v)), xtick:monthTick,
      points:(a, b) => [{ name:"Massa grassa", col:"var(--s4)", pts:sparsePts(D.bodyfat, a, b) }] } },

  /* ---- Volume ---- */
  { panel:"volume", cls:"half", h:170, first:"act", title:"Mix per sport",
    cap:"ore, impilate", legend:S.map((s, i) => [s, SCH[i]]),
    kind:rStack, spec:{ arrs:secsOf.bySport, names:S, cols:SC, scale:v => v / 3600,
      fmt:FMT.hours } },

  { panel:"volume", h:170, first:"act", title:"Chilometri", cap:"distanza sommata",
    now:() => secsOf.dist.reduce((a, b) => a + b, 0) / 1000, nowFmt:FMT.num0, nowUnit:"km in tutto",
    kind:rBars, spec:{ name:"Distanza", arr:secsOf.dist, how:"sum", scale:v => v / 1000,
      col:"var(--s2)", fmt:FMT.km } },

  { panel:"volume", h:170, first:"act", title:"Dislivello", cap:"metri di salita sommati",
    now:() => secsOf.gain.reduce((a, b) => a + b, 0), nowFmt:FMT.num0, nowUnit:"m in tutto",
    kind:rBars, spec:{ name:"Dislivello", arr:secsOf.gain, how:"sum", col:"var(--s4)",
      fmt:FMT.m, ytick:v => v >= 1000 ? (v / 1000) + "k" : String(v) } },

  { panel:"volume", h:190, first:"act", title:"Distanza contro dislivello",
    cap:"una attività, un punto · solo bici e corsa",
    legend:[["Bici", SCH[0]], ["Corsa", SCH[1]]],
    kind:rXY, spec:{ xname:"Distanza", yname:"Dislivello", xfmt:FMT.km, yfmt:FMT.m, r:2.2,
      points:(a, b) => [0, 1].map(sp => ({ name:S[sp], col:SCH[sp],
        pts:D.acts.filter(x => x[0] >= a && x[0] <= b && x[1] === sp && x[3] > 500)
          .map(x => [x[3] / 1000, x[4], x[0]]) })) },
    foot:"Solo bici e corsa: gli altri sport non hanno questo asse." },

  /* ---- Incroci ---- */
  { panel:"incroci", h:180, first:"sleep", title:"Sonno contro carico del giorno prima",
    cap:"TSS di ieri → ore dormite stanotte",
    kind:rXY, spec:{ xname:"TSS di ieri", yname:"Sonno", xfmt:FMT.tss, yfmt:FMT.hhmm, r:2.8,
      points:(a, b) => [{ name:"notti", col:"var(--s1)",
        pts:pairPts(i => D.load[i - 1], i => D.sleep[i], a, b, x => x > 0) }] } },

  { panel:"incroci", h:180, first:"hrv", title:"HRV contro il sonno della notte",
    cap:"ore dormite → HRV al risveglio",
    kind:rXY, spec:{ xname:"Sonno", yname:"HRV", xfmt:FMT.hhmm, yfmt:FMT.ms, r:2.8,
      xtick:v => (v / 60).toFixed(0) + "h",
      points:(a, b) => [{ name:"mattine", col:"var(--s2)",
        pts:pairPts(i => D.sleep[i], i => D.hrv[i], a, b) }] } },

  { panel:"incroci", h:180, first:"rhr", title:"FC a riposo contro carico del giorno prima",
    cap:"TSS di ieri → battiti stamattina",
    kind:rXY, spec:{ xname:"TSS di ieri", yname:"FC a riposo", xfmt:FMT.tss, yfmt:FMT.bpm, r:2.8,
      points:(a, b) => [{ name:"mattine", col:"var(--s3)",
        pts:pairPts(i => D.load[i - 1], i => D.rhr[i], a, b, x => x > 0) }] } },

  { panel:"incroci", h:180, first:"hrv", title:"HRV contro forma",
    cap:"CTL − ATL → HRV al risveglio",
    kind:rXY, spec:{ xname:"Forma", yname:"HRV", xfmt:FMT.num0, yfmt:FMT.ms, r:2.8,
      points:(a, b) => [{ name:"mattine", col:"var(--s4)",
        pts:pairPts(i => (D.ctl[i] === null || D.atl[i] === null ? null : D.ctl[i] - D.atl[i]), i => D.hrv[i], a, b) }] } },

  { panel:"incroci", h:180, first:"vo2", title:"VO₂max contro fitness",
    cap:"CTL del giorno → VO₂max stimato",
    kind:rXY, spec:{ xname:"Fitness (CTL)", yname:"VO₂max", xfmt:FMT.num0,
      yfmt:FMT.num1, r:2.8,
      points:(a, b) => [{ name:"stime", col:"var(--s1)",
        pts:pairPts(i => D.ctl[i], i => D.vo2[i], a, b) }] },
    foot:"Fra fitness 90 e 190 la stima non si sposta." },

  /* ---- Tavola: presenti solo se _nutrition.csv era sul disco al build ---- */
  ...nutriTiles(),
];

/* Le serie del cibo arrivano da una repo privata come aggregati giornalieri, e
   possono benissimo non esserci. Costruire i riquadri da una funzione, invece che
   scriverli a mano nella lista, fa sparire l'intera sezione quando il file manca —
   invece di lasciare in pagina otto rettangoli che dicono "nessun dato". */
function nutriTiles() {
  const N_ = D.nutri || {};
  if (!N_.kcal) return [];
  const has = k => Array.isArray(N_[k]);
  const t = [];
  const MICR = D.microbes || {};
  const GEN = [["Faecalibacterium", "🌾"], ["Bacteroides", "🥩"], ["Prevotella", "🌱"],
               ["Bifidobacterium", "🍶"], ["Roseburia", "🌾"], ["Blautia", "🌱"],
               ["Ruminococcus", "🥔"], ["Eubacterium", "🌾"], ["Akkermansia", "🫐"],
               ["Lactobacillus", "🍶"]].filter(([g]) => Array.isArray(MICR[g]));

  t.push({ panel:"tavola", h:118, first:"n_kcal", title:"Quanto è raccontato",
    cap:"kcal osservate contro ricostruite · i piatti dichiarati sono ~75 % della dieta", legend:[["Osservate", SCH[2]], ["Ricostruite", SCH[3]]],
    now:() => { const a = N_.kcal_observed, b = N_.kcal_assumed; let o = 0, s = 0;
      for (let i = 0; i < N; i++) if (a[i] !== null) { o += a[i]; s += a[i] + (b[i] || 0); }
      return s ? 100 * o / s : null; },
    nowFmt:v => nf(v, 0) + " %", nowUnit:"osservato",
    kind:rStack, spec:{ arrs:[N_.kcal_observed, N_.kcal_assumed],
      names:["Osservate", "Ricostruite"], cols:["var(--s3)", "var(--s4)"], fmt:FMT.num0 },
    foot:"Osservato = un pasto raccontato. Ricostruito = lo schema mensile dichiarato, che copre circa tre quarti della dieta." });

  t.push({ panel:"tavola", h:118, first:"n_kcal", title:"Energia",
    cap:"kcal al giorno · media mobile 7 giorni",
    now:() => lastMean(N_.kcal, 7),
    nowFmt:FMT.num0, nowUnit:"kcal, media 7 gg",
    kind:rCloud, spec:{ name:"Energia", arr:N_.kcal, col:"var(--s2)", fmt:FMT.num0,
      zero:true, win:7 } });

  t.push({ panel:"tavola", h:118, first:"n_fiber_g", title:"Fibre",
    cap:"grammi al giorno · la fascia è l'obiettivo, 30 g",
    now:() => lastMean(N_.fiber_g, 7),
    nowFmt:FMT.num1, nowUnit:"g, media 7 gg",
    kind:rCloud, spec:{ name:"Fibre", arr:N_.fiber_g, col:"var(--s3)", fmt:v => nf(v, 1) + " g",
      band:[30, 45], zero:true, win:7 } });

  if (has("plants_7d")) t.push({ panel:"tavola", h:118, first:"n_plants_7d",
    title:"Piante diverse", cap:"specie vegetali distinte negli ultimi 7 giorni · obiettivo 30",
    now:() => { for (let i = N - 1; i >= 0; i--) if (N_.plants_7d[i] !== null) return N_.plants_7d[i]; return null; },
    nowFmt:FMT.num0, nowUnit:"su 30",
    kind:rCloud, spec:{ name:"Piante", arr:N_.plants_7d, col:"var(--s1)", fmt:FMT.num0,
      band:[30, 30], zero:true, win:14 },
    foot:"Cereali, legumi, frutta secca, erbe e spezie contano." });

  t.push({ panel:"tavola", h:118, first:"n_carb_g", title:"Carboidrati contro fabbisogno",
    cap:"ingeriti e stimati dal TSS del giorno",
    legend:[["Ingeriti", SCH[0]], ["Stimati dal carico", SCH[1]]],
    now:() => lastMean(N_.carb_gap_g, 7),
    nowFmt:v => (v > 0 ? "+" : "") + nf(v, 0), nowUnit:"g di scarto, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + " g", series:[
      { name:"Ingeriti", col:SCH[0], area:true, get:(a, b) => N_.carb_g.slice(a, b + 1).map((v, k) => [a + k, v]) },
      { name:"Stimati dal carico", col:SCH[1], get:(a, b) => N_.carb_target_g.slice(a, b + 1).map((v, k) => [a + k, v]) },
    ] },
    foot:"Stima: 3 g/kg da fermo, ~6 a TSS 100, fino a 10." });

  t.push({ panel:"tavola", h:118, first:"n_sugar_g", title:"Zuccheri",
    cap:"grammi al giorno · media mobile 7 giorni",
    now:() => lastMean(N_.sugar_g, 7),
    nowFmt:FMT.num1, nowUnit:"g, media 7 gg",
    kind:rCloud, spec:{ name:"Zuccheri", arr:N_.sugar_g, col:"var(--s4)",
      fmt:v => nf(v, 1) + " g", zero:true, win:7 } });

  t.push({ panel:"tavola", h:118, first:"n_magnesium_mg", title:"Magnesio e potassio",
    cap:"% del fabbisogno coperta", legend:[["Magnesio", SCH[2]], ["Potassio", SCH[0]]],
    now:() => { const v = lastMean(N_.magnesium_mg, 7); return v === null ? null : 100 * v / 350; },
    nowFmt:v => nf(v, 0) + " %", nowUnit:"magnesio, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + " %", series:[
      { name:"Magnesio", col:SCH[2], get:(a, b) => rolling(N_.magnesium_mg, a, b, 7).map((v, k) => [a + k, v === null ? null : 100 * v / 350]) },
      { name:"Potassio", col:SCH[0], get:(a, b) => rolling(N_.potassium_mg, a, b, 7).map((v, k) => [a + k, v === null ? null : 100 * v / 3500]) },
    ] },
    foot:"100 % = fabbisogno coperto." });

  t.push({ panel:"tavola", h:118, first:"n_vit_index", title:"Vitamine e minerali",
    cap:"indice 0-100 · media delle coperture, ognuna tagliata a 100",
    legend:[["Vitamine", SCH[1]], ["Minerali", SCH[2]]],
    now:() => lastMean(N_.vit_index, 7),
    nowFmt:FMT.num0, nowUnit:"vitamine, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0), series:[
      { name:"Vitamine", col:SCH[1], get:(a, b) => rolling(N_.vit_index, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Minerali", col:SCH[2], get:(a, b) => rolling(N_.min_index, a, b, 7).map((v, k) => [a + k, v]) },
    ] },
    foot:"Ogni nutriente tagliato al 100 % prima della media." });

  if (has("microbiome")) t.push({ panel:"tavola", h:118, first:"n_microbiome",
    title:"Indice microbiota", cap:"proxy 0-100 dal diario, non una misura",
    now:() => lastMean(N_.microbiome, 14),
    nowFmt:FMT.num0, nowUnit:"su 100, 14 gg",
    kind:rCloud, spec:{ name:"Microbiota", arr:N_.microbiome, col:"var(--s1)",
      fmt:FMT.num0, zero:true, win:14 },
    foot:"Proxy: piante 40 %, fibra 30 %, fermentati 15 %, ultra-processati −15 %.",
    /* le emoji dicono quali leve stanno spingendo l'indice, adesso, e quanto:
       il numero da solo non dice mai da dove viene */
    shifters:() => {
      const M = D.microbes || {};
      const at = a => { if (!a) return null;
        for (let i = N - 1; i >= 0; i--) if (a[i] !== null) return a[i]; return null; };
      return [["🌾", "fibra", at(M.drv_fiber)], ["🌱", "piante", at(M.drv_plants)],
              ["🍶", "fermentati", at(M.drv_ferment)], ["⚙️", "ultra-proc.", at(M.drv_upf), 1]]
        .filter(x => x[2] !== null);
    } });

  /* La matrice 3×3: tre input della tavola contro tre uscite del recupero.
     Nove ipotesi guardate insieme — se ne mostrassi solo la più forte starei
     scegliendo il risultato dopo aver visto i dati. */
  if (has("fiber_g") && has("magnesium_mg")) t.push({
    panel:"tavola", h:340, first:"n_fiber_g", title:"Tavola contro recupero",
    cap:"nove incroci · colonne: cosa è entrato · righe: come è andata la notte",
    kind:rMatrix, spec:{ col:"var(--s1)",
      cols:[{ name:"Fibre", arr:N_.fiber_g, fmt:v => nf(v, 0) + " g" },
            { name:"Magnesio", arr:N_.magnesium_mg, fmt:v => nf(v, 0) + " mg" },
            { name:"Potassio", arr:N_.potassium_mg, fmt:v => nf(v, 0) + " mg" }],
      rows:[{ name:"HRV", arr:D.hrv, fmt:FMT.ms },
            { name:"Sonno", arr:D.sleep, fmt:FMT.hhmm },
            { name:"Qualità", arr:D.score, fmt:FMT.num0 }] },
    foot:"Blu positivo, rosso negativo, grigio quasi niente. Il grigio è il risultato più probabile, e conta." });

  /* Tutte contro tutte. Dodici serie fanno 66 coppie: 66 nuvole non si guardano,
     una griglia si. E' l'unico punto della pagina in cui una griglia e' la forma
     giusta — e lo e' perche' qui il colore porta un valore continuo con un segno. */
  t.push({ panel:"tavola", h:430, first:"n_fiber_g",
    title:"Tutte contro tutte", cap:"correlazione fra ogni coppia di serie · triangolo inferiore",
    kind:rHeat, spec:{ vars:[
      { name:"Fibre", arr:N_.fiber_g }, { name:"Magnesio", arr:N_.magnesium_mg },
      { name:"Potassio", arr:N_.potassium_mg }, { name:"Zuccheri", arr:N_.sugar_g },
      { name:"Energia", arr:N_.kcal }, { name:"Piante", arr:N_.plants_7d },
      { name:"Microbiota", arr:N_.microbiome },
      { name:"HRV", arr:D.hrv }, { name:"Sonno", arr:D.sleep },
      { name:"Qualità", arr:D.score }, { name:"FC riposo", arr:D.rhr },
      { name:"Passi", arr:D.steps }, { name:"Carico", arr:D.load },
    ] },
    foot:"Blu positivo, rosso negativo, grigio niente. Celle vuote = meno di 20 giorni in comune. Attenzione alle celle più accese: magnesio, potassio e fibre stanno negli stessi alimenti, e microbiota è <em>costruito</em> da piante e fibre — quelle non sono scoperte, sono il cablaggio. Le coppie che direbbero qualcosa (tavola contro recupero) restano grigie." });

  /* I dieci generi di cui si parla, modellati. Il titolo dice "modello" e la
     didascalia lo ripete: qui non c'è nessun campione, nessuna sequenza, nessuna
     misura — solo le associazioni direzionali fra dieta e abbondanza relativa
     fatte girare su un modello log-lineare i cui pesi stanno nel sorgente. */

  if (GEN.length >= 5) t.push({ panel:"tavola", h:300, first:"m_Faecalibacterium",
    title:"Flora intestinale — modello, non una misura",
    cap:"dieci generi noti · quota stimata da come si è mangiato",
    labA:"inizio finestra", labB:"oggi",
    kind:rSlope, spec:{ labA:"inizio", labB:"oggi",
      items:GEN.map(([g, e]) => ({ name:g, emoji:e, arr:MICR[g] })) },
    /* niente piede su questa: il titolo dice gia' "modello, non una misura" e la
       riga sotto era troppo lunga. L'avvertenza per esteso resta nell'etichetta
       dei dati, dove non sta fra i piedi ma non sparisce nemmeno. */
    noFoot:true,
    dataNote:"Modello, non una misura: associazioni direzionali da letteratura su un modello log-lineare, pesi nel sorgente. È una composizione: qualcuno sale solo se qualcun altro scende." });

  /* ---- quote settimanali: vegetale, latticini, ultra-processato ---------- */
  if (has("pct_plant")) t.push({ panel:"tavola", h:170, first:"n_pct_plant",
    title:"Da dove arrivano le calorie", cap:"% delle kcal · quote sovrapposte, non una torta",
    legend:[["Vegetale", SCH[2]], ["Latticini", SCH[0]], ["Ultra-processato", SCH[3]]],
    now:() => lastMean(N_.pct_plant, 7), nowFmt:v => nf(v, 0) + " %", nowUnit:"vegetale, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + " %", series:[
      { name:"Vegetale", col:SCH[2], area:true, get:(a, b) => rolling(N_.pct_plant, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Latticini", col:SCH[0], get:(a, b) => rolling(N_.pct_dairy, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Ultra-processato", col:SCH[3], get:(a, b) => rolling(N_.pct_upf, a, b, 7).map((v, k) => [a + k, v]) },
    ] },
    foot:"Un alimento può contare in più quote: il latte è latticino e animale, un cornetto è vegetale (frumento) e ultra-processato. Per questo non sommano a cento." });

  /* ---- quali cibi muovono la flora: heatmap alimenti × generi ------------ */
  const FF = D.floraFoods || [];
  if (FF.length && GEN.length >= 5) {
    const gens = GEN.map(([g, e]) => ({ name:`${e} ${g.slice(0, 9)}`, key:g }));
    const items = FF.slice(0, 16).map(f => ({ name:f.name.length > 20 ? f.name.slice(0, 19) + "…" : f.name, f }));
    const vmax = Math.max(...items.flatMap(it => gens.map(g => Math.abs(it.f[g.key] || 0)))) || 1;
    t.push({ panel:"tavola", h:430, first:"m_Faecalibacterium",
      title:"Quali cibi muovono la flora", cap:"il modello letto al contrario · spinta di ogni alimento su ogni genere",
      kind:rGrid, spec:{ rows:items, cols:gens, vmax, labMax:150, labB:74,
        cell:(i, j) => { const v = items[i].f[gens[j].key];
          if (v === undefined) return null;
          return { v, txt:Math.abs(v) >= 1 ? v.toFixed(0) : "",
            tip:`${items[i].f.name}<br>${gens[j].key} <span class="v">${v >= 0 ? "+" : ""}${v.toFixed(2)}</span>` +
                `<br><span class="d">${items[i].f.share_pct.toFixed(1)} % delle kcal</span>` }; },
        summary:h => h && `spinge di più ${items[h.i].f.name} su ${gens[h.j].key}`,
        table:cells => `<tr><th>alimento</th><th>genere</th><th>spinta</th></tr>` +
          cells.filter(c => Math.abs(c[2].v) > .3).sort((a, b) => Math.abs(b[2].v) - Math.abs(a[2].v))
            .slice(0, 30).map(c => `<tr><td>${c[0]}</td><td>${c[1]}</td><td>${c[2].v >= 0 ? "+" : ""}${c[2].v.toFixed(2)}</td></tr>`).join("") },
      foot:"La spinta è quanto quell'alimento preme sul genere <em>per come pesa nella tua dieta</em>: un cibo ottimo ma mangiato di rado conta poco, ed è giusto così. Resta il modello, non una misura." });
  }

  /* ---- striscia temporale: molte serie, una riga ciascuna ---------------- */
  const STRIP = [
    ["Fibre", N_.fiber_g], ["Piante", N_.plants_7d], ["Vegetale %", N_.pct_plant],
    ["Ultra-proc. %", N_.pct_upf], ["Zuccheri", N_.sugar_g], ["Energia", N_.kcal],
    ["Microbiota", N_.microbiome], ["Sonno", D.sleep], ["HRV", D.hrv],
    ["FC riposo", D.rhr], ["Carico", D.load],
  ].filter(([, a]) => Array.isArray(a));
  if (STRIP.length >= 6) t.push({ panel:"tavola", h:300, first:"n_fiber_g",
    title:"Tutto, nel tempo", cap:"una riga per serie · il passo si adatta allo spazio: settimane, mesi, anni",
    kind:(svg, W, H, spec, a, b) => {
      /* Ogni riga ha unita' sue — grammi, ore, battiti — quindi il colore non puo'
         essere il valore: e' il PERCENTILE dentro la storia di quella riga. Cosi'
         le righe si possono confrontare fra loro, e si vede in che settimane tutto
         si muoveva insieme. */
      /* Il passo si sceglie dalla larghezza che c'e', non si spera che ci stia:
         con 104 settimane in una scheda stretta le colonne sarebbero da 2 px e il
         riquadro spariva. Settimane finche' ci stanno, poi mesi, poi anni. */
      const room = Math.max(6, Math.floor((W - 96 - 8) / 9));
      let step = "w";
      for (const s_ of ["w", "m", "y"]) {
        step = s_;
        if (aggregate(STRIP[0][1], a, b, "mean", s_).length <= room) break;
      }
      const weeks = aggregate(STRIP[0][1], a, b, "mean", step).map(o => o.i);
      if (weeks.length < 4) return null;
      const rowsData = STRIP.map(([name, arr]) => {
        const agg = aggregate(arr, a, b, "mean", step);
        const byI = new Map(agg.map(o => [o.i, o.v]));
        const vals = agg.map(o => o.v).filter(v => v !== null && isFinite(v)).sort((x, y) => x - y);
        return { name, byI, vals, arr };
      });
      return rGrid(svg, W, H, {
        rows:rowsData, cols:weeks.map(i => ({ name:bucketLabel(i, step).replace("sett. del ", "") })),
        vmax:1, diverging:false, labMax:96, labB:70, maxColLabels:10,
        cell:(i, j) => { const r = rowsData[i], v = r.byI.get(weeks[j]);
          if (v === null || v === undefined || !r.vals.length) return null;
          const pos = r.vals.filter(x => x <= v).length / r.vals.length;
          return { v:pos, day:weeks[j],
            tip:`<span class="d">${bucketLabel(weeks[j], step)}</span><br>${r.name} <span class="v">${nf(v, 1)}</span>` +
                `<br><span class="d">${nf(pos * 100, 0)}° percentile della sua storia</span>` }; },
        summary:() => `${rowsData.length} serie · ${weeks.length} ${step === "w" ? "settimane" : step === "m" ? "mesi" : "anni"}`,
        table:() => `<tr><th>serie</th><th>min</th><th>mediana</th><th>max</th></tr>` +
          rowsData.filter(r => r.vals.length).map(r => `<tr><td>${r.name}</td><td>${nf(r.vals[0], 1)}</td><td>${nf(r.vals[Math.floor(r.vals.length / 2)], 1)}</td><td>${nf(r.vals[r.vals.length - 1], 1)}</td></tr>`).join(""),
      }, a, b);
    }, spec:{},
    foot:"Il colore è il percentile dentro la <em>propria</em> riga, non il valore: righe con unità diverse diventano confrontabili, e si vedono le settimane in cui tutto si muoveva insieme. Chiaro = basso per quella serie, acceso = alto." });

  /* i conteggi: quante volte è entrato in casa un certo alimento */
  const TAL = [["cnt_avocado", "avocado", "🥑"], ["cnt_lenticchie", "porzioni di lenticchie", "🫘"],
               ["cnt_uova", "uova", "🥚"], ["cnt_banane", "banane", "🍌"],
               ["cnt_avena", "porzioni di avena", "🌾"], ["cnt_patate_dolci", "porzioni di patate dolci", "🍠"]]
    .filter(([k]) => has(k));
  if (TAL.length) t.push({ panel:"tavola", h:180, first:"n_cnt_avocado",
    title:"Quanti ne sono passati", cap:"conteggio cumulato dall'inizio della finestra",
    legend:TAL.slice(0, 4).map(([, l, e], i) => [`${e} ${l}`, SCH[i % 4]]),
    kind:rLines, spec:{ zero:true, fmt:FMT.num0,
      series:TAL.slice(0, 4).map(([k, l, e], i) => ({ name:`${e} ${l}`, col:SCH[i % 4],
        get:(a, b) => { let acc = 0; const o = [];
          for (let j = a; j <= b; j++) { acc += N_[k][j] || 0; o.push([j, acc]); }
          return o; } })) },
    foot:"Cumulato, quindi la pendenza è il ritmo: una riga che si appiattisce è un alimento che ha smesso di entrare." });

  return t;
}

function sparsePts(arr, a, b) {
  const o = [];
  for (let i = a; i <= b; i++) if (arr[i] !== null && arr[i] !== undefined) o.push([i, arr[i], i]);
  return o;
}
function pairPts(fx, fy, a, b, keepX) {
  const o = [];
  for (let i = Math.max(a, 1); i <= b; i++) {
    const x = fx(i), y = fy(i);
    if (x === null || x === undefined || y === null || y === undefined) continue;
    if (keepX && !keepX(x)) continue;
    o.push([x, y, i]);
  }
  return o;
}

/* ------------------------------------------------------------------ render */
/* Built node by node rather than from an innerHTML blob, and every part kept on a
   reference: nothing here has to query the document back for something it just
   made, which is what lets tools/check_vita.cjs drive the whole page against a
   fifty-line DOM shim instead of pulling in a browser. */
const mk = (tag, cls, parent, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
};

function tileNode(t) {
  const art = mk("article", "tile" + (t.cls ? " " + t.cls : ""));
  const side = mk("div", "t-side", art);
  const head = mk("div", "t-head", side);
  mk("div", "t-title", head, t.title);
  const now = mk("div", "t-now", side);
  mk("div", "t-cap", side, t.cap);
  const shift = t.shifters ? mk("div", "t-shift", side) : null;
  if (t.legend) {
    const lg = mk("div", "t-legend", side);
    lg.innerHTML = t.legend.map(([n, c]) =>
      `<span><i style="background:${c}"></i>${n}</span>`).join("");
  }
  const box = mk("div", "figbox", art);
  const foot = mk("div", "t-foot", art);
  const det = mk("details", "data", art);
  const sum = mk("summary", null, det, "dati");
  const tbl = mk("table", "fallback", det);
  const tbody = mk("tbody", null, tbl);
  /* si tiene il riferimento, non lo si ricerca: `children` nel browser e' una
     HTMLCollection e non ha .find() — cercarlo li' uccideva l'intero script, cioe'
     la pagina senza nemmeno un grafico */
  return { art, now, box, foot, sum, tbody, shift };
}

function drawTile(n, t) {
  n.box.innerHTML = "";
  const W = Math.max(240, n.box.clientWidth || n.art.clientWidth - 32 || 360), H = t.h;
  const svg = el("svg", { class:"plot", viewBox:`0 0 ${W} ${H}`,
    role:"img", "aria-label":t.title + " — " + t.cap });
  const [from, to] = windowFor(t.first ? daysOf(t.first) : 0,
    t.first ? (D.last || {})[t.first] : undefined);
  let res = null, err = null;
  if (to - from >= 2) {
    /* a renderer that throws must not take the page down with it — but it must not
       masquerade as "no data" either, so the reason is kept where a check can see it */
    try { res = t.kind(svg, W, H, t.spec, from, to); }
    catch (e) { err = e; res = null; }
  }
  n.art.dataset.err = err ? String(err && err.message || err) : "";
  n.art.dataset.empty = res ? "" : "1";

  if (res) n.box.appendChild(svg);
  else mk("p", "t-empty", n.box, "Nessun dato in questa finestra.");

  if (t.shifters && n.shift) {
    n.shift.innerHTML = t.shifters().map(([e, lab, v, inv]) =>
      `<span title="${lab}">${e} <b style="color:${(inv ? 1 - v : v) >= .6 ? "var(--s3)" : (inv ? 1 - v : v) >= .35 ? "var(--s4)" : "var(--neg)"}">${nf(v * 100, 0)}</b></span>`).join("");
  }
  if (t.now) {
    const v = t.now();
    n.now.innerHTML = v === null || v === undefined || !isFinite(v) ? ""
      : `${t.nowFmt(v)}<br><small>${t.nowUnit}</small>`;
  }

  /* Il piede dice solo quello che non si vede dal grafico. La finestra e il
     conteggio dei punti erano rumore — l'asse mostra già le date, e "n 92" non ha
     mai cambiato una decisione. Restano il passo di aggregazione quando non è
     ovvio, la correlazione, e i punti lasciati fuori scala, che è l'unica cosa
     che il disegno tace davvero. */
  /* Il piede torna sotto il riquadro (2026-08-10: "in genere precedente versione
     era meglio"). Dice quello che il disegno tace: il passo di aggregazione, la
     correlazione, i punti lasciati fuori scala, e la nota di metodo. */
  const bits = [];
  if (res) {
    bits.push(`${fmtDate(from)} → ${fmtDate(to)}`);
    if (res.plan) bits.push(res.plan.label);
    if (res.stats) bits.push(`n ${nf(res.stats.n)}`);
    if (res.fit) bits.push(`r ${res.fit.r.toFixed(2)}`);
    if (res.best2) bits.push(res.best2);
    if (res.best) bits.push(`più alta ${res.best}`);
    if (res.outside) bits.push(`${res.outside} fuori scala`);
  }
  n.foot.innerHTML = t.noFoot ? "" : bits.join(" · ") + (t.foot ? `<br>${t.foot}` : "");
  n.sum.textContent = t.dataNote ? `dati · ${t.dataNote}` : "dati";
  n.tbody.innerHTML = res ? res.table : "";
}

const MOUNTED = [];
for (const t of TILES) {
  const host = document.getElementById("panel-" + t.panel);
  if (!host) continue;
  const n = tileNode(t);
  host.appendChild(n.art);
  MOUNTED.push([n, t]);
}
const drawAll = () => { for (const [n, t] of MOUNTED) drawTile(n, t); };
window.CRUSCOTTO = { D, TILES, MOUNTED, drawAll, setRange:k => { range = k; drawAll(); } };
window.openDay = openDay;   /* il check lo chiama per verificare il popup */

/* ---------------------------------------------------------- range control */
const rangesEl = document.getElementById("ranges");
for (const r of RANGES) {
  const b = document.createElement("button");
  b.textContent = r.label; b.type = "button";
  b.setAttribute("aria-pressed", String(r.key === range));
  b.addEventListener("click", () => {
    range = r.key;
    for (const c of rangesEl.children) c.setAttribute("aria-pressed", String(c === b));
    noteEl.textContent = noteFor();
    drawAll();
  });
  rangesEl.appendChild(b);
}
const noteEl = document.getElementById("range-note");
function noteFor() {
  return range === "sempre"
    ? "Ogni riquadro parte da dove comincia la sua serie, non da dove comincia l'archivio: il carico dal 2019, sonno e HRV dal 2025."
    : "La stessa finestra su tutti i riquadri. Dove la serie non arriva così indietro, il riquadro parte da dove può.";
}
noteEl.textContent = noteFor();

/* --------------------------------------------------- le tre pagine in cima */
document.getElementById("tracks").innerHTML = (D.tracks || []).map(t => `
  <a class="track" href="${t.href}" style="--a:${t.accent}">
    <div class="k">${t.eyebrow}</div>
    <h3>${t.title}</h3>
    <p>${t.blurb}</p>
    <div class="nums">${t.stats.map(s =>
      `<div><b>${s.v}</b><span>${s.l}</span></div>`).join("")}</div>
  </a>`).join("");

/* ------------------------------------------------------------- headline */
(function totals() {
  const secs = secsOf.secs.reduce((a, b) => a + b, 0);
  const km = secsOf.dist.reduce((a, b) => a + b, 0) / 1000;
  const up = secsOf.gain.reduce((a, b) => a + b, 0);
  const nights = D.sleep.filter(v => v !== null).length;
  const sl = rolling(D.sleep, N - 30, N - 1, 30);
  const hv = rolling(D.hrv, N - 30, N - 1, 30);
  const items = [
    [nf(D.acts.length), "attività"],
    [nf(Math.round(km)), "chilometri"],
    [nf(Math.round(up / 1000)) + "k", "metri di salita"],
    [nf(Math.round(secs / 3600)), "ore in movimento"],
    [nf(Math.round(D.ctl[N - 1])), "fitness (CTL)"],
    [nf(Math.round(D.ctl[N - 1] - D.atl[N - 1])), "forma"],
    [nf(nights), "notti misurate"],
    [hhmm(sl[sl.length - 1]), "sonno, 30 gg"],
    [nf(Math.round(hv[hv.length - 1])), "HRV, 30 gg"],
  ];
  document.getElementById("totals").innerHTML = items.map(([n, l]) =>
    `<div class="total"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
})();

drawAll();
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(drawAll, 160); });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
