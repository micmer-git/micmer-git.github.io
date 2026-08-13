#!/usr/bin/env python3
"""
strava_backfill.py — le attività che Intervals.icu non ha, riprese dall'export Strava.

Perché esiste. Intervals è la sorgente di /vita, ma non ha tutto: il 2026-08-13 il
confronto con l'export Strava ha trovato **654 attività** che su Intervals non ci sono,
e il buco più grosso è un anno intero. Il 2022 su Intervals ha ZERO attività, mentre su
Strava ne ha 394. Nella pagina si vedeva come una banda "nessun dato" larga dodici mesi,
con la CTL che decade fino a zero: identico, a occhio, a un anno di stop. Non è successo.

    2022: 394    2023: 106    2021: 88    2017: 26    2018: 21    altri: 19

Cosa fa. Legge `activities.csv` dall'export Strava (dentro lo zip o già estratto),
lo confronta con `tools/food/data/activities.csv` (l'ultimo pull di Intervals), e scrive
le attività che mancano in `tools/food/data/activities_backfill.csv`, nello stesso schema
più le colonne di provenienza. **Non tocca activities.csv**, che è rigenerato ogni ora
da `build_vita.py --sync-source` e sovrascriverebbe qualunque cosa ci scrivessimo dentro.

## Il carico ricostruito

Strava non esporta il training load di Intervals, quindi va stimato. Il modello NON è
scelto a occhio: è calibrato sulle attività che stanno in tutte e due le sorgenti
(~2.090 accoppiate per data + nome, con ripiego sulla durata a meno di due minuti).

Di quattro forme provate, vince la TRIMP — durata per un esponenziale della frequenza
cardiaca — che è poi la stessa famiglia con cui Intervals calcola il carico da cardio:

    load = a · ore · e^(k · (hr − 50)/140)

| modello | corsa | bici | nuoto |
|---|---|---|---|
| a · Relative Effort | 16,5 % | 25,3 % | 9,1 % |
| a · RE + b · ore | 9,7 % | 27,8 % | 13,0 % |
| **TRIMP (questa)** | **7,3 %** | **20,6 %** | **11,9 %** |

(errore assoluto mediano sulle accoppiate). Aggiungere la potenza media sulla bici porta
il 20,6 % a 19,1 %: un punto, in cambio di un secondo modello da mantenere e di una
colonna che nel 2022 c'è solo su metà delle uscite. Non vale, e non è stato preso.

Ordine di ripiego, per attività: TRIMP se c'è la frequenza cardiaca (368 delle 394 del
2022), altrimenti il rapporto mediano carico/Relative Effort per sport, altrimenti
durata per il carico orario mediano di quello sport. Ogni riga porta scritto in
`load_method` quale dei tre l'ha prodotta, perché un carico stimato dalla sola durata e
uno stimato dalla cardio non valgono uguale e non vanno letti uguale.

**Quello che esce è ricostruito, non osservato.** I coefficienti fitati finiscono in
`activities_backfill.json` accanto al CSV, così un rebuild è verificabile.

    python tools/strava_backfill.py ~/Desktop/export_14488475.zip
    python tools/strava_backfill.py export.zip --check   # riporta e basta
"""
import argparse
import collections
import csv
import datetime as dt
import io
import json
import math
import os
import re
import statistics
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ACTIVITIES = os.path.join(HERE, "food", "data", "activities.csv")
OUT_CSV = os.path.join(HERE, "food", "data", "activities_backfill.csv")
OUT_JSON = os.path.join(HERE, "food", "data", "activities_backfill.json")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Strava scrive "Virtual Ride", Intervals "VirtualRide". Stessa cosa, due alfabeti.
TYPE_MAP = {
    "Virtual Ride": "VirtualRide", "Virtual Run": "VirtualRun",
    "Backcountry Ski": "BackcountrySki", "Nordic Ski": "NordicSki",
    "Alpine Ski": "AlpineSki", "Weight Training": "WeightTraining",
    "Trail Run": "TrailRun", "Open Water Swim": "OpenWaterSwim",
    "Gravel Ride": "GravelRide", "Mountain Bike Ride": "MountainBikeRide",
    "E-Bike Ride": "EBikeRide",
}
SPORT = {"Ride": "bike", "VirtualRide": "bike", "GravelRide": "bike",
         "MountainBikeRide": "bike", "EBikeRide": "bike",
         "Run": "run", "TrailRun": "run", "VirtualRun": "run",
         "Swim": "swim", "OpenWaterSwim": "swim"}

# La banda cardiaca del modello TRIMP: (hr - HR_REST) / (HR_MAX - HR_REST). Non sono
# misure di Michele, sono i due estremi con cui il fit è stato fatto — cambiarli
# invalida i coefficienti in FIT, che vanno rifatti girando di nuovo lo script.
HR_REST, HR_SPAN = 50.0, 140.0

FIELDS = ["date", "name", "type", "moving_time_s", "elapsed_time_s", "distance_m",
          "elevation_m", "calories", "training_load", "intensity", "avg_hr",
          "max_hr", "avg_power_w", "np_w", "source", "load_method", "strava_id"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_date(s):
    m = re.match(r"(\w+) (\d+), (\d{4})", s or "")
    if not m or m.group(1) not in MONTHS:
        return None
    return dt.date(int(m.group(3)), MONTHS.index(m.group(1)) + 1,
                   int(m.group(2))).isoformat()


def read_strava(path):
    """activities.csv dall'export, sia zippato sia già estratto."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist()
                         if n.rstrip("/").endswith("activities.csv")
                         and n.count("/") == 0), None)
            if name is None:
                sys.exit(f"{path}: nessun activities.csv nella radice dello zip.")
            raw = z.read(name)
    else:
        with open(path, "rb") as fh:
            raw = fh.read()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))
    for r in rows:
        r["_date"] = parse_date(r.get("Activity Date"))
        r["_type"] = TYPE_MAP.get((r.get("Activity Type") or "").strip(),
                                  (r.get("Activity Type") or "").strip())
    return [r for r in rows if r["_date"]]


def read_intervals():
    if not os.path.exists(ACTIVITIES):
        sys.exit(f"manca {ACTIVITIES} — gira prima build_vita.py --sync-source.")
    with open(ACTIVITIES, encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("date")]


def pair_up(srows, irows):
    """Accoppia Strava<->Intervals. Quello che resta spaiato da Strava è ciò che
    manca a Intervals, cioè il lavoro di questo script.

    In DUE passate, e l'ordine conta. Con una passata sola, un'attività senza nome
    che ripiega sulla durata si prende la riga che il nome di un'ALTRA attività
    dello stesso giorno avrebbe agganciato di netto — e quella finisce fra le
    mancanti pur essendoci. Succedeva su una trentina di giorni fra 2024 e 2026,
    cioè proprio gli anni che Intervals ha sincronizzato bene: erano falsi buchi.
    Quindi prima TUTTI i nomi esatti, poi la durata su quello che avanza.

    Le righe di Intervals senza nome e senza durata sono segnaposto del calendario,
    non allenamenti: se restano fra i candidati la loro durata legge 0 e si mangiano
    le attività corte.
    """
    by_day = collections.defaultdict(list)
    for r in irows:
        if not (r.get("name") or "").strip() and num(r.get("moving_time_s")) is None:
            continue
        by_day[r["date"][:10]].append(r)

    pairs, used = [], set()

    def take(r, hit, queue):
        if hit is None:
            queue.append(r)
        else:
            used.add(id(hit))
            pairs.append((r, hit))

    def free(day):
        return [c for c in by_day.get(day, []) if id(c) not in used]

    # passata 1: nome identico, stesso giorno.
    q1 = []
    for r in srows:
        name = (r.get("Activity Name") or "").strip()
        take(r, next((c for c in free(r["_date"])
                      if (c["name"] or "").strip() == name), None), q1)

    # passata 2: la DISTANZA, che è il campo che sopravvive al passaggio fra le due
    # piattaforme. Il nome no: Michele ribattezza le uscite su Strava e Intervals si
    # tiene il "Bergamo Cycling" dell'import, quindi lo stesso giro si presenta con
    # due nomi diversi. E nemmeno lo sport: una camminata di corsa esce Run di qua e
    # Hike di là. La distanza invece combacia al metro (2025-12-03: 28.365,8 contro
    # 28.369,85). Tolleranza: 50 m o lo 0,5 %, il maggiore dei due.
    q2 = []
    for r in q1:
        sd = num(r.get("Distance"))
        hit = None
        if sd and sd > 0:
            tol = max(50.0, sd * 0.005)
            cands = [c for c in free(r["_date"]) if num(c.get("distance_m"))]
            if cands:
                near = min(cands, key=lambda c: abs(num(c["distance_m"]) - sd))
                if abs(num(near["distance_m"]) - sd) <= tol:
                    hit = near
        take(r, hit, q2)

    # passata 3: la durata, per quello che una distanza non ce l'ha (rulli, palestra).
    missing = []
    for r in q2:
        smt = num(r.get("Moving Time"))
        hit = None
        cands = free(r["_date"])
        if smt is not None and cands:
            near = min(cands, key=lambda c: abs((num(c["moving_time_s"]) or 0) - smt))
            if abs((num(near["moving_time_s"]) or 0) - smt) <= 120:
                hit = near
        take(r, hit, missing)
    return pairs, missing


def solve(A, y):
    """Minimi quadrati con le equazioni normali. Solo stdlib, niente numpy."""
    k = len(A[0])
    M = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(k)]
         + [sum(A[r][i] * y[r] for r in range(len(A)))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            return None
        for r in range(k):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for j in range(c, k + 1):
                M[r][j] -= f * M[c][j]
    return [M[i][k] / M[i][i] for i in range(k)]


def fit(pairs):
    """Coefficienti per sport: TRIMP, rapporto su Relative Effort, carico orario."""
    g = collections.defaultdict(list)
    for s, i in pairs:
        load = num(i.get("training_load"))
        if not load or load <= 0:
            continue
        g[SPORT.get(i.get("type") or "", "other")].append({
            "re": num(s.get("Relative Effort")),
            "hours": (num(s.get("Moving Time")) or 0) / 3600.0,
            "hr": num(s.get("Average Heart Rate")),
            "load": load})

    model = {}
    for sport, v in g.items():
        m = {"n": len(v)}
        hr = [x for x in v if x["hr"] and x["hours"] > 0.08]
        if len(hr) >= 20:
            c = solve([[1.0, (x["hr"] - HR_REST) / HR_SPAN] for x in hr],
                      [math.log(x["load"]) - math.log(x["hours"]) for x in hr])
            if c:
                m["trimp"] = [round(c[0], 4), round(c[1], 4)]
                err = [abs(math.exp(c[0]) * x["hours"]
                           * math.exp(c[1] * (x["hr"] - HR_REST) / HR_SPAN) - x["load"])
                       / x["load"] for x in hr]
                m["trimp_median_err"] = round(100 * statistics.median(err), 1)
                m["trimp_n"] = len(hr)
        re_ = [x for x in v if x["re"]]
        if re_:
            m["re_ratio"] = round(statistics.median(x["load"] / x["re"] for x in re_), 4)
            m["re_n"] = len(re_)
        dur = [x for x in v if x["hours"] > 0.08]
        if dur:
            m["per_hour"] = round(statistics.median(x["load"] / x["hours"] for x in dur), 2)
        model[sport] = m
    return model


def estimate(model, sport, hours, hr, re_):
    """(carico, metodo). L'ordine è quello dell'accuratezza misurata nel docstring."""
    m = model.get(sport) or model.get("other") or {}
    if hr and hours > 0 and "trimp" in m:
        a, k = m["trimp"]
        return math.exp(a) * hours * math.exp(k * (hr - HR_REST) / HR_SPAN), "trimp_hr"
    if re_ and "re_ratio" in m:
        return m["re_ratio"] * re_, "relative_effort"
    if hours > 0 and "per_hour" in m:
        return m["per_hour"] * hours, "durata"
    return None, "nessuno"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export", help="export_XXXXXXX.zip di Strava, o activities.csv")
    ap.add_argument("--check", action="store_true", help="riporta e basta, non scrive")
    args = ap.parse_args()

    srows = read_strava(args.export)
    irows = read_intervals()
    print(f"  Strava    {len(srows)} attività")
    print(f"  Intervals {len(irows)} attività")

    pairs, missing = pair_up(srows, irows)
    print(f"  accoppiate {len(pairs)} · mancanti a Intervals {len(missing)}")

    model = fit(pairs)
    print("\n  modello del carico, per sport:")
    for sport, m in sorted(model.items(), key=lambda x: -x[1]["n"]):
        bits = [f"n={m['n']}"]
        if "trimp" in m:
            bits.append(f"TRIMP err {m['trimp_median_err']}% su {m['trimp_n']}")
        if "re_ratio" in m:
            bits.append(f"carico/RE {m['re_ratio']}")
        if "per_hour" in m:
            bits.append(f"{m['per_hour']}/ora")
        print(f"    {sport:6s} " + " · ".join(bits))

    out, methods = [], collections.Counter()
    for r in sorted(missing, key=lambda x: (x["_date"], x.get("Activity ID") or "")):
        sport = SPORT.get(r["_type"], "other")
        hours = (num(r.get("Moving Time")) or 0) / 3600.0
        load, method = estimate(model, sport, hours,
                                num(r.get("Average Heart Rate")),
                                num(r.get("Relative Effort")))
        methods[method] += 1
        out.append({
            "date": r["_date"],
            "name": (r.get("Activity Name") or "").strip(),
            "type": r["_type"],
            "moving_time_s": int(num(r.get("Moving Time")) or 0),
            "elapsed_time_s": int(num(r.get("Elapsed Time")) or 0),
            "distance_m": round(num(r.get("Distance")) or 0, 2),
            "elevation_m": round(num(r.get("Elevation Gain")) or 0, 2),
            "calories": round(num(r.get("Calories")) or 0),
            "training_load": round(load) if load else "",
            "intensity": "",          # Strava non lo esporta
            "avg_hr": round(num(r.get("Average Heart Rate")) or 0) or "",
            "max_hr": round(num(r.get("Max Heart Rate")) or 0) or "",
            "avg_power_w": round(num(r.get("Average Watts")) or 0) or "",
            "np_w": "",               # idem
            "source": "strava_backfill",
            "load_method": method,
            "strava_id": (r.get("Activity ID") or "").strip(),
        })

    years = collections.Counter(r["date"][:4] for r in out)
    print(f"\n  da ricostruire: {len(out)} attività")
    print("    per anno:  " + "  ".join(f"{y}:{n}" for y, n in sorted(years.items())))
    print("    per metodo: " + "  ".join(f"{m}:{n}" for m, n in methods.most_common()))

    if args.check:
        print("\n  (--check: niente scritto)")
        return

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({
            "built": dt.date.today().isoformat(),
            "export": os.path.basename(args.export),
            "strava_activities": len(srows),
            "intervals_activities": len(irows),
            "paired": len(pairs),
            "backfilled": len(out),
            "by_year": dict(sorted(years.items())),
            "by_method": dict(methods),
            "hr_rest": HR_REST, "hr_span": HR_SPAN,
            "model": model,
        }, fh, indent=2, ensure_ascii=False)
    print(f"\n-> {OUT_CSV}")
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    main()
