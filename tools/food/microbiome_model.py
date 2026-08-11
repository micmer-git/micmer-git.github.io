#!/usr/bin/env python3
"""Un MODELLO della flora intestinale a partire da cosa si e' mangiato.

Da leggere prima di guardare qualunque grafico che esca di qui:

    **Nessuno ha sequenziato niente.** Non esiste un campione, non esiste una
    misura. Questo file prende le associazioni fra dieta e abbondanza relativa
    che la letteratura riporta come DIREZIONALI (piu' fibra -> piu'
    Faecalibacterium, piu' fermentati -> piu' Lactobacillus, piu' grassi e
    proteine animali -> piu' Bacteroides) e le fa girare su un modello
    log-lineare giocattolo. Il risultato e' "come si muoverebbe una flora tipo
    se rispondesse solo alla dieta, e solo in quel verso".

    Serve a vedere una TENDENZA e a rendere visibile un ragionamento, non a
    dire cosa c'e' nell'intestino di qualcuno. La variabilita' fra persone e'
    enorme, la genetica e i farmaci contano quanto la dieta, e l'ordine di
    grandezza degli effetti qui e' scelto per essere leggibile, non calibrato
    su una coorte.

Il modello, per intero e in chiaro:

  1. Ogni giorno produce cinque *driver* normalizzati 0..1 sulla media mobile a
     30 giorni: fibra, diversita' vegetale, fermentati, ultra-processati e
     proteine+grassi animali. La finestra e' 30 giorni perche' la composizione
     risponde alla dieta abituale, non al singolo pasto — un pranzo non sposta
     una flora.
  2. Ogni genere ha una quota di partenza `base` (ordini di grandezza tipici di
     un adulto occidentale sano) e un vettore di sensibilita' ai driver.
  3. quota_grezza = base · exp(Σ sensibilita' · (driver − 0,5))
  4. Le quote si normalizzano a 100: e' una composizione, quindi qualcuno sale
     solo se qualcun altro scende. Questa e' l'unica cosa che il modello dice
     con sicurezza, ed e' anche la piu' importante da capire.

    python scripts/microbiome_model.py --check
    python scripts/microbiome_model.py --export <path.csv>
"""
import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

import common

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SERIES = common.DERIVED / "nutrition_series.csv"
OUT = common.DERIVED / "microbiome.csv"

WIN = 30          # giorni: la flora segue la dieta abituale, non il singolo pasto

# I cinque driver e il valore che viene considerato "pieno" (driver = 1).
DRIVERS = {
    "fiber":   ("fiber_g", 45.0),
    "plants":  ("plants_7d", 30.0),
    "ferment": ("_ferment", 1.0),
    "upf":     ("_upf", 0.35),
    "animal":  ("_animal", 1.0),
}

# base: quota di partenza in %. sens: sensibilita' ai driver (log-lineare).
# Il segno viene dalla direzione riportata in letteratura; il modulo e' scelto
# per essere leggibile. Emoji = il "key shifter", il driver che pesa di piu'.
GENERA = [
    ("Faecalibacterium", 12.0, {"fiber": 1.10, "plants": 0.55, "upf": -0.60}, "🌾"),
    ("Bacteroides",      14.0, {"animal": 0.85, "fiber": -0.45, "upf": 0.25}, "🥩"),
    ("Prevotella",       10.0, {"fiber": 0.95, "plants": 0.70, "animal": -0.80}, "🌱"),
    ("Bifidobacterium",   7.0, {"fiber": 0.85, "ferment": 0.70, "upf": -0.55}, "🍶"),
    ("Roseburia",         8.0, {"fiber": 0.90, "plants": 0.40, "upf": -0.35}, "🌾"),
    ("Blautia",          10.0, {"plants": 0.45, "fiber": 0.30, "animal": 0.20}, "🌱"),
    ("Ruminococcus",      8.0, {"fiber": 0.70, "plants": 0.35}, "🥔"),
    ("Eubacterium",       7.0, {"fiber": 0.75, "plants": 0.30, "upf": -0.30}, "🌾"),
    ("Akkermansia",       3.5, {"plants": 0.80, "fiber": 0.45, "upf": -0.70}, "🫐"),
    ("Lactobacillus",     2.0, {"ferment": 1.20, "upf": -0.35}, "🍶"),
]
# quel che resta ("Altri") tiene il totale a 100 senza fingere che dieci generi
# siano tutto l'intestino: non lo sono, sono i dieci di cui si parla.


def load_series():
    with SERIES.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("date")]


def extra_drivers():
    """fermentati e proteine+grassi animali per giorno: servono i singoli alimenti,
    quindi si ricalcolano dal log invece di leggerli dalla serie aggregata."""
    foods = common.load_foods()
    recipes = common.load_recipes()
    rows = list(common.load_food_log())
    ap = common.DERIVED / "assumed_log.csv"
    if ap.exists():
        with ap.open(encoding="utf-8", newline="") as fh:
            rows += [r for r in csv.DictReader(fh) if r.get("date")]
    rows = common.expand_log(rows, recipes)
    ferm, upf, animal, kcal = (defaultdict(float) for _ in range(4))
    for r in rows:
        f = foods.get(r["food_id"])
        if not f:
            continue
        q = float(r["qty"])
        k = f["per_unit"]["kcal"] * q
        d = r["date"]
        kcal[d] += k
        if f["fermented"]:
            ferm[d] += k
        if f["upf"]:
            upf[d] += k
        # "animale" = gruppi proteine/latticini, cioe' proteine e grassi animali
        if f["group"] in ("proteine", "latticini"):
            animal[d] += k
    return ferm, upf, animal, kcal


def food_influence(days_window=None):
    """Quali alimenti, fra quelli davvero mangiati, muovono di piu' ogni genere.

    Non e' una misura in piu': e' il MODELLO letto al contrario. Ogni alimento ha
    un suo profilo sui cinque driver (quanta fibra porta per caloria, se e' una
    pianta, se e' fermentato, se e' ultra-processato, se e' animale); il modello
    dice quanto ogni driver spinge ogni genere; il prodotto dei due, pesato per
    quante calorie di quell'alimento sono davvero entrate, dice quanto quell'
    alimento conta nel risultato. Serve a rispondere a "cosa devo mangiare di
    piu'" senza spacciarlo per un referto.
    """
    foods = common.load_foods()
    recipes = common.load_recipes()
    rows = list(common.load_food_log())
    ap = common.DERIVED / "assumed_log.csv"
    if ap.exists():
        with ap.open(encoding="utf-8", newline="") as fh:
            rows += [r for r in csv.DictReader(fh) if r.get("date")]
    rows = common.expand_log(rows, recipes)

    kcal_of = defaultdict(float)
    for r in rows:
        f = foods.get(r["food_id"])
        if not f:
            continue
        if days_window and r["date"] not in days_window:
            continue
        kcal_of[r["food_id"]] += f["per_unit"]["kcal"] * float(r["qty"])
    total = sum(kcal_of.values()) or 1.0

    out = []
    for fid, kc in kcal_of.items():
        f = foods[fid]
        per = f["per_unit"]
        k100 = per["kcal"] or 1e-9
        # profilo dell'alimento sui driver, in unita' confrontabili fra loro
        prof = {
            # g di fibra per 100 kcal, rapportati a una densita' "piena" di 5 g/100 kcal
            "fiber": min(1.0, (per["fiber_g"] / k100 * 100) / 5.0),
            "plants": 1.0 if f["plant"] else 0.0,
            "ferment": 1.0 if f["fermented"] else 0.0,
            "upf": 1.0 if f["upf"] else 0.0,
            "animal": 1.0 if f["group"] in ("proteine", "latticini") else 0.0,
        }
        share = kc / total
        row = {"food_id": fid, "name": f["name"], "kcal": round(kc),
               "share_pct": round(100 * share, 2)}
        for name, base, sens, emoji in GENERA:
            # spinta = quanto i driver di questo alimento premono su questo genere,
            # scalata da quanto peso ha nella dieta
            row[name] = round(sum(w * prof.get(k, 0.0) for k, w in sens.items())
                              * share * 100, 3)
        out.append(row)
    out.sort(key=lambda r: -r["kcal"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--export")
    ap.add_argument("--export-foods", help="matrice alimento x genere (CSV)")
    args = ap.parse_args()

    rows = load_series()
    ferm, upf, animal, kcal = extra_drivers()
    by_date = {r["date"]: r for r in rows}
    days = sorted(by_date)

    def raw(name, d):
        r = by_date.get(d)
        if not r:
            return None
        if name == "_ferment":
            return (ferm.get(d, 0) / kcal[d]) if kcal.get(d) else 0.0
        if name == "_upf":
            return (upf.get(d, 0) / kcal[d]) if kcal.get(d) else 0.0
        if name == "_animal":
            return (animal.get(d, 0) / kcal[d]) if kcal.get(d) else 0.0
        v = r.get(name)
        return float(v) if v not in (None, "") else None

    out = []
    for d in days:
        cur = date.fromisoformat(d)
        drv = {}
        for key, (field, full) in DRIVERS.items():
            vals = []
            for j in range(WIN):
                k = (cur - timedelta(days=j)).isoformat()
                v = raw(field, k)
                if v is not None:
                    vals.append(v)
            if not vals:
                drv[key] = .5
                continue
            drv[key] = max(0.0, min(1.0, (sum(vals) / len(vals)) / full))

        shares, contrib = {}, {}
        for name, base, sens, emoji in GENERA:
            expo = sum(w * (drv[k] - .5) for k, w in sens.items())
            shares[name] = base * math.exp(expo)
            # il driver che spinge di piu' questo genere, oggi
            best = max(sens.items(), key=lambda kv: abs(kv[1] * (drv[kv[0]] - .5)))
            contrib[name] = best[0]
        known = sum(shares.values())
        others = max(5.0, 100.0 - sum(b for _, b, _, _ in GENERA))
        tot = known + others
        row = {"date": d}
        for name, *_ in GENERA:
            row[name] = round(100.0 * shares[name] / tot, 2)
        row["Altri"] = round(100.0 * others / tot, 2)
        for k, v in drv.items():
            row["drv_" + k] = round(v, 3)
        out.append(row)

    fields = ["date"] + [g[0] for g in GENERA] + ["Altri"] + \
             ["drv_" + k for k in DRIVERS]
    first, last = out[0], out[-1]
    print(f"{len(out)} giorni, {days[0]} → {days[-1]}   (MODELLO, non una misura)")
    print(f"  {'genere':<18}{'inizio':>8}{'oggi':>8}{'Δ':>8}   spinto da")
    for name, base, sens, emoji in GENERA:
        d0v, d1v = first[name], last[name]
        print(f"  {emoji} {name:<16}{d0v:7.2f}%{d1v:7.2f}%{d1v - d0v:+7.2f}   "
              f"{', '.join(f'{k}{w:+.2f}' for k, w in sens.items())}")
    print("  driver oggi: " + " · ".join(f"{k} {last['drv_' + k]:.2f}" for k in DRIVERS))

    if args.check:
        print("\n(--check: niente scritto)")
        return
    common.write_csv(OUT, fields, out)
    print(f"\n-> {OUT}")
    if args.export:
        from pathlib import Path
        p = Path(args.export)
        p.parent.mkdir(parents=True, exist_ok=True)
        common.write_csv(p, fields, out)
        print(f"-> {p}")

    if args.export_foods:
        from pathlib import Path
        infl = food_influence()
        top = infl[:22]
        ffields = ["food_id", "name", "kcal", "share_pct"] + [g[0] for g in GENERA]
        print("\n  alimenti che muovono di piu' la flora (modello letto al contrario):")
        for r in top[:10]:
            best = max(((g[0], r[g[0]]) for g in GENERA), key=lambda kv: abs(kv[1]))
            print(f"    {r['name']:<34} {r['share_pct']:5.1f} % kcal   "
                  f"spinge {best[0]} {best[1]:+.2f}")
        p = Path(args.export_foods)
        p.parent.mkdir(parents=True, exist_ok=True)
        common.write_csv(p, ffields, top)
        print(f"-> {p}  ({len(top)} alimenti)")


if __name__ == "__main__":
    main()
