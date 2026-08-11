#!/usr/bin/env python3
"""Ricostruisce i pasti abituali nei giorni in cui il diario non dice niente.

L'utente ha dichiarato il 2026-08-09 il suo schema di base:

  * colazione, tutti i giorni in cui non dice altro: 50 g di avena, 15 g di cacao
    100%, 15 g di cioccolato 50%, 25 g di burro d'arachidi sgrassato, 1 banana e
    60 g di latte intero (ricetta `colazione_standard`);
  * **2 avocado toast a settimana** (2 fette di pane integrale, 3 uova, 1 avocado);
  * **2 dahl a settimana** (300 g di lenticchie, 2 cipolle, 800 g di patate dolci,
    cumino, curry, 80 g di latte intero fanno 3 zuppe).

Quello che aggiunge non e' un dato: e' una ricostruzione. Per questo **non tocca
`food_log.csv`** e scrive in `data/derived/assumed_log.csv`, rigenerabile da zero
a ogni run. Chi legge le serie puo' cosi' sempre chiedersi quanta parte del piatto
sia stata osservata e quanta assunta — ed e' esattamente la domanda giusta da
farsi davanti a un grafico dell'apporto di fibre.

    python scripts/fill_defaults.py            # dal primo all'ultimo giorno del log
    python scripts/fill_defaults.py --from 2026-05-01 --to 2026-07-31
    python scripts/fill_defaults.py --check    # dice cosa aggiungerebbe, non scrive
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta

import common

# le note e i nomi degli alimenti hanno accenti: una console cp1252 non deve
# far fallire una ricostruzione riuscita
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = common.DERIVED / "assumed_log.csv"
FIELDS = ["date", "meal", "food_id", "qty", "note", "source"]

BREAKFAST = "recipe:colazione_standard"
WEEKLY = [
    # (food_id, porzioni a settimana, pasto, nota)
    ("recipe:avocado_toast", 2, "pranzo", "2 a settimana, dichiarato da te"),
    ("recipe:dahl_lenticchie_patate_dolci", 2, "cena", "2 a settimana, dichiarato da te"),
]


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def iso_week(d):
    return d.isocalendar()[:2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--check", action="store_true", help="riporta e basta")
    args = ap.parse_args()

    log = common.load_food_log()
    if not log:
        raise SystemExit("food_log.csv e' vuoto: non c'e' niente da ricostruire.")
    days = sorted({r["date"] for r in log})
    # Due anni indietro di default (chiesto il 2026-08-10). Prima di maggio 2026 il
    # diario e' vuoto, quindi la' dentro la ricostruzione e' TUTTO: la serie diventa
    # "come mangia di solito", non "cosa ha mangiato". Va letta cosi', ed e' il
    # motivo per cui la quota osservata e' il primo riquadro della sezione.
    d1 = date.fromisoformat(args.d_to or max(days[-1], date.today().isoformat()))
    d0 = date.fromisoformat(args.d_from) if args.d_from else min(
        date.fromisoformat(days[0]), d1 - timedelta(days=730))

    # cosa c'e' gia', giorno per giorno
    meals_by_day = defaultdict(set)
    ids_by_day = defaultdict(list)
    for r in log:
        meals_by_day[r["date"]].add(r["meal"])
        ids_by_day[r["date"]].append(r["food_id"])

    added = []
    # Quali fasce sono gia' occupate, contando ANCHE quello che aggiungiamo noi.
    # Senza questo, l'avocado toast settimanale e il piatto del mese finivano
    # tutti e due sullo stesso pranzo: 421 fasce doppie e 267.000 kcal fantasma
    # su 215 giorni. `meals_by_day` da solo conosce il diario vero, non le righe
    # che stiamo scrivendo mentre le scriviamo.
    taken = defaultdict(set)
    for k, ms in meals_by_day.items():
        taken[k] |= set(ms)

    # ---- colazione nei giorni che non ne hanno una -------------------------
    for d in daterange(d0, d1):
        k = d.isoformat()
        if "colazione" in taken[k]:
            continue
        taken[k].add("colazione")
        added.append({"date": k, "meal": "colazione", "food_id": BREAKFAST,
                      "qty": 1, "note": "colazione di default", "source": "assunto"})

    # ---- le due ricette settimanali ---------------------------------------
    weeks = defaultdict(list)
    for d in daterange(d0, d1):
        weeks[iso_week(d)].append(d)

    for fid, target, meal, note in WEEKLY:
        for wk, dates in sorted(weeks.items()):
            have = sum(1 for d in dates for f in ids_by_day[d.isoformat()] if f == fid)
            missing = target - have
            if missing <= 0:
                continue
            # si mettono nei giorni piu' scarichi del diario: se un giorno e' gia'
            # raccontato per intero, infilarci dentro una zuppa in piu' e' il modo
            # piu' rapido di gonfiare le kcal di una giornata che era gia' completa
            cand = [d for d in dates if meal not in taken[d.isoformat()]]
            cand.sort(key=lambda d: (len(ids_by_day[d.isoformat()]), d.isoformat()))
            for d in cand[:missing]:
                taken[d.isoformat()].add(meal)
                added.append({"date": d.isoformat(), "meal": meal, "food_id": fid,
                              "qty": 1, "note": note, "source": "assunto"})

    # ---- i piatti del mese ------------------------------------------------
    # Dichiarati il 2026-08-10, mese per mese, con la fascia di kcal di un pasto.
    # Ogni piatto compare **una volta** nella sua settimana, poi ruota sugli altri
    # giorni del mese. La rotazione e' deterministica (indice del giorno, non
    # random): una pagina statica non puo' cambiare i propri numeri a ogni
    # rigenerazione, o due build dello stesso giorno raccontano due diete.
    pat_file = common.DATA / "monthly_patterns.csv"
    if pat_file.exists():
        by_month = defaultdict(list)
        with pat_file.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                by_month[r["month"]].append(r["dish_id"])

        for d in daterange(d0, d1):
            k = d.isoformat()
            dishes = by_month.get(k[:7])
            if not dishes:
                continue
            # pranzo e cena: si riempiono solo se la fascia e' ancora libera —
            # libera davvero, cioe' ne' nel diario ne' fra le righe gia' assunte
            for slot, off in (("pranzo", 0), ("cena", 1)):
                if slot in taken[k]:
                    continue
                taken[k].add(slot)
                # la prima settimana del mese fa sfilare i piatti in ordine, cosi'
                # ognuno compare almeno una volta; dopo, ruotano
                idx_ = (d.day - 1) * 2 + off
                fid = "recipe:" + dishes[idx_ % len(dishes)]
                added.append({"date": k, "meal": slot, "food_id": fid, "qty": 1,
                              "note": "piatto del mese, ricostruito", "source": "assunto"})

    added.sort(key=lambda r: (r["date"], r["meal"]))

    n_days = (d1 - d0).days + 1
    by_kind = defaultdict(int)
    for r in added:
        by_kind[r["food_id"]] += 1
    print(f"finestra {d0} → {d1}  ({n_days} giorni, {len(days)} raccontati)")
    for fid, n in sorted(by_kind.items()):
        print(f"  +{n:4d}  {fid}")
    print(f"  totale {len(added)} righe assunte")

    if args.check:
        print("\n(--check: niente scritto)")
        return
    common.write_csv(OUT, FIELDS, added)
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
