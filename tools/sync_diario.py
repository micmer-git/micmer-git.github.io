#!/usr/bin/env python3
"""
sync_diario.py — refresh the numbers in diario-di-un-unno from Intervals.icu.

Each chapter is a calendar month, and its stat strip is
    <n> attività · <km> km · <m> m · <h> h · <kJ> kJ
      = count · Σdistance/1000 · Σtotal_elevation_gain · Σmoving_time/3600 · Σicu_joules/1000

That was not assumed — 38 of the 39 published chapters reproduce from the API to
the digit, including the ones marked "≈". The only one that didn't was the month
the page was last built in, frozen mid-month. So this script recomputes every
chapter's strip and the cover totals, and leaves everything else alone.

**What it deliberately does not touch.** The "W104–W107" week labels follow no rule
recoverable from the page (no epoch + weekday reproduces more than 15 of the 25
published ranges), so generating them would mean inventing numbers. The prose is
the author's. Both are reported, not written:

  - a month still marked "— in corso" after it has ended
  - a month with activities and no chapter at all

    python tools/sync_diario.py --dry-run
    python tools/sync_diario.py
"""
import argparse
import os
import re
import shutil
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE = "diario-di-un-unno/index.html"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, HERE)
from sync_intervals import api, get_api_key            # noqa: E402

MESI = {"Gennaio": 1, "Febbraio": 2, "Marzo": 3, "Aprile": 4, "Maggio": 5, "Giugno": 6,
        "Luglio": 7, "Agosto": 8, "Settembre": 9, "Ottobre": 10, "Novembre": 11,
        "Dicembre": 12}
NOMI = {v: k for k, v in MESI.items()}

STRIP = re.compile(
    r'(?P<open><div class="stat-strip">)\s*'
    r'(?P<p0>≈?)(?P<n>[\d.]+) attività · (?P<p1>≈?)(?P<km>[\d.]+) km · '
    r'(?P<p2>≈?)(?P<m>[\d.]+) m · (?P<p3>≈?)(?P<h>[\d.]+) h · '
    r'(?P<p4>≈?)(?P<kj>[\d.]+) kJ')
PERIOD = re.compile(r'<span class="month-num">([^<]*)</span>')


def it(n):
    return f"{int(round(n)):,}".replace(",", ".")


def month_stats(acts):
    return {
        "n": len(acts),
        "km": sum(a.get("distance") or 0 for a in acts) / 1000,
        "m": sum(a.get("total_elevation_gain") or 0 for a in acts),
        "h": sum(a.get("moving_time") or 0 for a in acts) / 3600,
        "kj": sum(a.get("icu_joules") or 0 for a in acts) / 1000,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    p = os.path.join(ROOT, PAGE)
    with open(p, encoding="utf-8") as f:
        html = f.read()

    periods = PERIOD.findall(html)
    keys = []                                   # (year, month) newest-first, as on the page
    for s in periods:
        m = re.match(r"(\w+) (\d{4})", s.strip())
        keys.append((int(m.group(2)), MESI[m.group(1)]) if m and m.group(1) in MESI else None)
    strips = list(STRIP.finditer(html))
    if len(strips) != len(keys):
        sys.exit(f"{len(keys)} chapter headings but {len(strips)} stat strips — "
                 "the page markup moved; fix the patterns before syncing.")
    print(f"{len(keys)} chapters, {keys[-1][0]}-{keys[-1][1]:02d} → {keys[0][0]}-{keys[0][1]:02d}")

    key = get_api_key(args.api_key)
    oldest = date(keys[-1][0], keys[-1][1], 1).isoformat()
    today = date.today()
    acts = api(f"athlete/i302515/activities?oldest={oldest}&newest={today.isoformat()}", key)
    if acts is None:
        sys.exit("Could not list activities.")
    by_month = {}
    for a in acts:
        by_month.setdefault(a.get("start_date_local", "")[:7], []).append(a)
    print(f"  {len(acts)} activities in {len(by_month)} months")

    # ---- rewrite each strip, keeping the author's ≈ markers
    changes, totals = [], {"n": 0, "km": 0.0, "m": 0.0, "h": 0.0, "kj": 0.0}
    out, cursor = [], 0
    for k, mt in zip(keys, strips):
        st = month_stats(by_month.get(f"{k[0]}-{k[1]:02d}", []))
        for f in totals:
            totals[f] += st[f]
        g = mt.groupdict()
        new = (f"{g['open']}{g['p0']}{it(st['n'])} attività · {g['p1']}{it(st['km'])} km · "
               f"{g['p2']}{it(st['m'])} m · {g['p3']}{it(st['h'])} h · "
               f"{g['p4']}{it(st['kj'])} kJ")
        if new != html[mt.start():mt.end()]:
            changes.append((f"{NOMI[k[1]]} {k[0]}",
                            html[mt.start() + len(g['open']):mt.end()], new[len(g['open']):]))
        out.append(html[cursor:mt.start()])
        out.append(new)
        cursor = mt.end()
    out.append(html[cursor:])
    html = "".join(out)

    # ---- cover totals, from the raw sums (not the rounded strips)
    cover = [("Sortite", it(totals["n"])), ("km", it(totals["km"])),
             ("m saliti", it(totals["m"])), ("kJ forgiati", it(totals["kj"])),
             ("h in moto", it(totals["h"])), ("Lune", str(len(keys)))]
    for lab, val in cover:
        pat = r'<div class="num">[\d.]+</div><div class="label">' + re.escape(lab) + r'</div>'
        rep = f'<div class="num">{val}</div><div class="label">{lab}</div>'
        html, k = re.subn(pat, rep, html, count=1)
        if k != 1:
            sys.exit(f"cover stat '{lab}' found {k} times, expected 1 — page markup moved.")

    if changes:
        print(f"\n{len(changes)} chapter(s) updated:")
        for name, was, now in changes:
            print(f"  {name}\n    era  {was}\n    ora  {now}")
    else:
        print("\nAll chapter numbers were already current.")
    print(f"\ncopertina: {len(keys)} lune · {it(totals['n'])} sortite · {it(totals['km'])} km · "
          f"{it(totals['m'])} m · {it(totals['kj'])} kJ · {it(totals['h'])} h")

    # ---- editorial follow-ups: reported, never written
    todo = []
    stale = [i for i, s in enumerate(periods) if "in corso" in s]
    for i in stale:
        y, mo = keys[i]
        if (y, mo) != (today.year, today.month):
            todo.append(f'"{periods[i].strip()}" — quel mese è finito, il capitolo '
                        f'è ancora marcato «in corso» (e la settimana resta aperta)')
    have = {f"{y}-{mo:02d}" for y, mo in keys}
    for mk in sorted(set(by_month) - have):
        st = month_stats(by_month[mk])
        todo.append(f"{mk} non ha un capitolo — {st['n']} attività, {it(st['km'])} km, "
                    f"{it(st['m'])} m, {it(st['kj'])} kJ in attesa di racconto")
    if todo:
        print("\nDa scrivere a mano (numeri pronti, prosa no):")
        for t in todo:
            print(f"  · {t}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return
    shutil.copyfile(p, p + ".bak")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nWrote {PAGE}  (backup: index.html.bak)")


if __name__ == "__main__":
    main()
