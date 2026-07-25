#!/usr/bin/env python3
"""
sync_sogni.py — append completed weeks to sogni-di-un-unno's data.json and load.json.

Both files are weekly series anchored to the same Monday M:

    data.json  startDate = M       sleep nights M+1 … M+7   (mean of sleepSecs / sleepScore)
    load.json  week      = M-1     activities   M   … M+6   (sums)

Those windows are not a guess — they were pinned by recomputing the last existing
week from the API until all six load figures (tl/km/elev/kj/n/maxHr) and both sleep
figures matched the published values exactly.

    python tools/sync_sogni.py --dry-run
    python tools/sync_sogni.py

**Bedtime and wake time cannot be refreshed.** The Intervals.icu wellness schema has
no sleep start/end field at all — only sleepSecs, sleepScore and sleepQuality. New
weeks therefore carry `bed`/`wake` as null and `bedStr`/`wakeStr` as "—"; the page
already guards on `d.bed !== null`, so the bedtime charts simply stop at the last
week that has real values. Refilling them needs whatever exported the original
figures (Garmin/Fitbit), not this script.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROME = ZoneInfo("Europe/Rome")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, HERE)
from sync_intervals import api, get_api_key            # noqa: E402  (same auth + UA)


def label(a, b):
    """'Apr 7-13, 2026' · 'Apr 28 - May 4, 2026' · 'Dec 30, 2025 - Jan 5, 2026'"""
    if a.year != b.year:
        return f"{MON[a.month - 1]} {a.day}, {a.year} - {MON[b.month - 1]} {b.day}, {b.year}"
    if a.month != b.month:
        return f"{MON[a.month - 1]} {a.day} - {MON[b.month - 1]} {b.day}, {b.year}"
    return f"{MON[a.month - 1]} {a.day}-{b.day}, {b.year}"


def quality(score):
    """Reproduces the buckets in the published data: Good >= 80, Fair >= 60, else Poor."""
    if score is None:
        return None
    return "Good" if score >= 80 else "Fair" if score >= 60 else "Poor"


def load_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def write_json(rel, data):
    p = os.path.join(ROOT, rel)
    shutil.copyfile(p, p + ".bak")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return p


MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
ABBR = ["gen", "feb", "mar", "apr", "mag", "giu",
        "lug", "ago", "set", "ott", "nov", "dic"]


def patch_page(sleep, loads, dry):
    """Rewrite the hero/footer figures the page hardcodes, so it can't contradict
    its own data. Each substitution must hit exactly once — if the page is edited
    into a shape these no longer match, that fails loudly instead of silently
    leaving a stale number on screen.

    The stat-bar's `±10.5 dev.std` is deliberately left alone: the weekly scores
    give 6.8, so that figure comes from some other population (nightly, most
    likely) and overwriting it would quietly change what it means.
    """
    rel = "sogni-di-un-unno/index.html"
    p = os.path.join(ROOT, rel)
    with open(p, encoding="utf-8") as f:
        html = f.read()

    scores = [w["score"] for w in sleep if w.get("score") is not None]
    n, nl = len(sleep), len(loads)
    mean = statistics.mean(scores)
    a = date.fromisoformat(sleep[0]["startDate"])
    b = date.fromisoformat(sleep[-1]["startDate"])
    la = date.fromisoformat(loads[0]["week"])
    lb = date.fromisoformat(loads[-1]["week"])

    import re
    edits = [
        (r"\d+ settimane, 20 eventi-cardine, dal \w+ \d{4} al \w+ \d{4}",
         f"{n} settimane, 20 eventi-cardine, dal {MESI[a.month-1]} {a.year} "
         f"al {MESI[b.month-1]} {b.year}"),
        (r"cinque anni di sonno · \d+ settimane",
         f"cinque anni di sonno · {n} settimane"),
        (r'<div class="num">\d+</div>', f'<div class="num">{n}</div>'),
        (r'<span class="v">\d+</span> settimane',
         f'<span class="v">{n}</span> settimane'),
        (r'<span class="v">[\d.,]+</span> media',
         f'<span class="v">{mean:.1f}</span> media'),
        (r"Cinque anni di Garmin sotto il polso, dal \w+ \d{4} al \w+ \d{4}",
         f"Cinque anni di Garmin sotto il polso, dal {MESI[a.month-1]} {a.year} "
         f"al {MESI[b.month-1]} {b.year}"),
        (r"La media dei cinque anni è <strong>[\d.,]+</strong>",
         f"La media dei cinque anni è <strong>{mean:.1f}</strong>".replace(".", ",")),
        (r"\d+ settimane Garmin \(\w+ \d{4} → \w+ \d{4}\) · \d+ settimane "
         r"intervals\.icu \(\w+ \d{4} → \w+ \d{4}\)",
         f"{n} settimane Garmin ({ABBR[a.month-1]} {a.year} → {ABBR[b.month-1]} {b.year})"
         f" · {nl} settimane intervals.icu ({ABBR[la.month-1]} {la.year} → "
         f"{ABBR[lb.month-1]} {lb.year})"),
    ]
    changed = 0
    for pat, repl in edits:
        html, k = re.subn(pat, repl, html, count=1)
        if k != 1:
            sys.exit(f"patch_page: pattern found {k} times, expected 1 — {pat}\n"
                     f"The page markup moved; fix the pattern before syncing again.")
        changed += 1
    print(f"  page figures updated: {n} settimane, {nl} settimane carico, "
          f"media {mean:.1f}  ({changed} sostituzioni)")
    if dry:
        return
    shutil.copyfile(p, p + ".bak")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key")
    ap.add_argument("--until", help="YYYY-MM-DD; default = today")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = get_api_key(args.api_key)
    today = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else date.today()

    sleep = load_json("sogni-di-un-unno/data.json")
    loads = load_json("sogni-di-un-unno/load.json")
    last_start = date.fromisoformat(sleep[-1]["startDate"])
    print(f"data.json: {len(sleep)} weeks, last starts {last_start.isoformat()}")
    print(f"load.json: {len(loads)} weeks, last is {loads[-1]['week']}")

    # every Monday whose full week (through M+7) is already over
    mondays = []
    m = last_start + timedelta(days=7)
    while m + timedelta(days=7) <= today:
        mondays.append(m)
        m += timedelta(days=7)
    if not mondays:
        print("No complete week to add yet.")
        print()
        patch_page(sleep, loads, args.dry_run)
        return
    print(f"\n{len(mondays)} complete weeks to add: "
          f"{mondays[0].isoformat()} → {mondays[-1].isoformat()}")

    oldest = (mondays[0]).isoformat()
    newest = (mondays[-1] + timedelta(days=7)).isoformat()
    well = api(f"athlete/i302515/wellness?oldest={oldest}&newest={newest}", key) or []
    acts = api(f"athlete/i302515/activities?oldest={oldest}&newest={newest}", key) or []
    print(f"  fetched {len(well)} wellness days, {len(acts)} activities")
    by_day = {w.get("id"): w for w in well}

    new_sleep, new_load = [], []
    for m in mondays:
        # ---- sleep: nights M+1 .. M+7
        nights = [by_day.get((m + timedelta(days=i)).isoformat()) for i in range(1, 8)]
        secs = [w["sleepSecs"] for w in nights if w and w.get("sleepSecs")]
        scores = [w["sleepScore"] for w in nights if w and w.get("sleepScore")]
        if not secs:
            print(f"  {m.isoformat()}: no sleep data, skipped")
            continue
        score = round(statistics.mean(scores)) if scores else None
        first, last = m + timedelta(days=1), m + timedelta(days=7)
        new_sleep.append({
            "date": label(first, last),
            "score": score,
            "quality": quality(score),
            "dur": statistics.mean(secs) / 3600,
            # Intervals.icu has no sleep start/end — see the module docstring
            "bedStr": "—", "wakeStr": "—", "bed": None, "wake": None, "bedRel": None,
            "year": last.year,
            "startDate": m.isoformat(),
            "ts": int(datetime(first.year, first.month, first.day,
                               tzinfo=ROME).timestamp() * 1000),
        })

        # ---- load: activities M .. M+6
        lo, hi = m, m + timedelta(days=6)
        sel = [a for a in acts
               if lo <= date.fromisoformat(a.get("start_date_local", "")[:10]) <= hi]
        new_load.append({
            "week": (m - timedelta(days=1)).isoformat(),
            "tl": round(sum(a.get("icu_training_load") or 0 for a in sel)),
            "km": round(sum(a.get("distance") or 0 for a in sel) / 1000),
            "elev": round(sum(a.get("total_elevation_gain") or 0 for a in sel)),
            "kj": round(sum(a.get("icu_joules") or 0 for a in sel) / 1000),
            "n": len(sel),
            "maxHr": max([a.get("max_heartrate") or 0 for a in sel] or [0]),
        })
        s, l = new_sleep[-1], new_load[-1]
        print(f"  + {s['date']:<24} sonno {s['dur']:.1f} h  score {s['score']}"
              f"   ·   carico tl {l['tl']}  {l['km']} km  {l['elev']} m  {l['n']} uscite")

    final_sleep, final_load = sleep + new_sleep, loads + new_load
    print()
    # always run, even with nothing new: the page's hardcoded figures must match
    # whatever is in the files right now, not only what this run happened to add
    patch_page(final_sleep, final_load, args.dry_run)
    if args.dry_run:
        print(f"\n--dry-run: {len(new_sleep)} weeks NOT written.")
        return
    if new_sleep:
        p1 = write_json("sogni-di-un-unno/data.json", final_sleep)
        p2 = write_json("sogni-di-un-unno/load.json", final_load)
        print(f"\nWrote {len(new_sleep)} weeks -> {os.path.basename(p1)}, "
              f"{os.path.basename(p2)}  (backups: *.bak)")


if __name__ == "__main__":
    main()
