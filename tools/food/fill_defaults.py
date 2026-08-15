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

# Quello che Michele ha detto di NON aver mangiato, riga per riga.
#
# Una ricostruzione e' un'ipotesi, e un'ipotesi si deve poter smentire: fino al
# 2026-08-14 non si poteva, perche' `assumed_log.csv` viene riscritto da zero a
# ogni giro e cancellarci dentro una riga non serviva a niente — tornava il giro
# dopo. La smentita quindi non vive nell'output, vive qui: un file di INPUT, che
# nessuno rigenera, dove ogni riga dice "questo, quel giorno, in quel pasto, non
# c'era". `fill_defaults` la legge e non emette la riga corrispondente.
#
# La chiave e' (data, pasto, food_id), dove food_id puo' essere `recipe:<id>`:
# una ricetta si toglie intera, che e' l'unico modo sensato — togliere le
# lenticchie e lasciare il curry non descrive nessuna cena mai avvenuta. E una
# ricetta smentita chiude il pasto per quel giorno: vedi il commento in fondo a
# `main`, dove la smentita si applica.
SUPPRESS = common.DATA / "diary_suppress.csv"
SUPPRESS_FIELDS = ["date", "meal", "food_id", "nota", "quando"]


def carica_soppressioni():
    if not SUPPRESS.exists():
        return set()
    fuori = set()
    with SUPPRESS.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("date") and r.get("food_id"):
                fuori.add((r["date"], r.get("meal") or "", r["food_id"]))
    return fuori

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

    # ---- merenda di tutti i giorni ----------------------------------------
    # Dichiarata il 2026-08-11: 200 g di yogurt greco, un frutto a rotazione e
    # una-due gallette di farro. E' l'unico pasto davvero quotidiano dopo la
    # colazione, quindi va nella ricostruzione di ogni giorno che non ne ha gia'
    # uno raccontato.
    FRUTTA = ["banana", "mela", "arancia", "kiwi", "pesca", "mandarino"]
    for d in daterange(d0, d1):
        k = d.isoformat()
        if "merenda" in taken[k] or "spuntino" in taken[k]:
            continue
        taken[k].add("merenda")
        # rotazione deterministica sul giorno: una pagina statica non puo'
        # cambiare la frutta a ogni rigenerazione
        frutto = FRUTTA[d.toordinal() % len(FRUTTA)]
        for fid, qty in (("yogurt_greco_0", 200), (frutto, 1), ("gallette_farro", 18)):
            added.append({"date": k, "meal": "merenda", "food_id": fid, "qty": qty,
                          "note": "merenda di tutti i giorni, dichiarata", "source": "assunto"})

    # ---- il panino delle uscite lunghe -------------------------------------
    # Dichiarato il 2026-08-11: in bici oltre l'ora, **un panino integrale da 60 g
    # con marmellata ai frutti di bosco e un cucchiaino di burro d'arachidi per
    # ogni ora**. Non e' una stima: e' una regola che l'utente segue, quindi si
    # applica alle uscite vere, non a un giorno tipo.
    ride_h = defaultdict(float)
    if common.ACTIVITIES_CSV.exists():
        with common.ACTIVITIES_CSV.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                t = (r.get("type") or "")
                if t not in ("Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide"):
                    continue
                dd = (r.get("date") or "")[:10]
                if dd:
                    ride_h[dd] += float(r.get("moving_time_s") or 0) / 3600.0

    # Se il carburante della bici è già stato raccontato, la regola automatica non
    # deve aggiungerne un'altra versione. La nota esplicita mantiene la distinzione
    # da un normale pane+marmellata mangiato a casa nello stesso giorno.
    bike_fuel_observed = {
        r["date"] for r in log
        if "panin" in (r.get("note") or "").lower()
        and "bici" in (r.get("note") or "").lower()
    }

    n_panini = 0
    for d in daterange(d0, d1):
        k = d.isoformat()
        h = ride_h.get(k, 0.0)
        if h < 1.0 or k in bike_fuel_observed:
            continue
        # un panino per ora piena; una uscita da 2h50 ne vale 3, da 1h10 ne vale 1
        n = max(1, round(h))
        n_panini += n
        for fid, qty in (("pane_integrale", 60 * n),
                         ("marmellata_fragola", 20 * n),
                         ("burro_arachidi_sgrassato", 6 * n)):
            added.append({"date": k, "meal": "spuntino", "food_id": fid, "qty": qty,
                          "note": f"{n} panino/i in bici ({h:.1f} h di uscita), dichiarato",
                          "source": "assunto"})

    # Le smentite si applicano QUI, in fondo: cosi' valgono su tutte le famiglie di
    # ricostruzione (colazione, ricette settimanali, piatti del mese, merenda,
    # panino) senza doverle ripetere in cinque punti diversi.
    #
    # Un piatto smentito chiude il PASTO, non solo se stesso. La ragione e' che la
    # ricostruzione di un giorno passato non e' stabile: le ricette settimanali si
    # distribuiscono sui giorni ancora liberi, quindi la cena del 14 puo' essere il
    # dahl oggi e la crostata domani. Se la smentita valesse solo per il food_id,
    # Michele direbbe "non ho mangiato il dahl", il giro dopo comparirebbe la
    # crostata al suo posto, e non ne uscirebbe piu'.
    #
    # Vale solo per le ricette, che nel pasto sono UNA: il contorno additivo
    # (yogurt, mela, gallette della merenda) si toglie uno per uno, perche' li'
    # negare la mela non dice niente sullo yogurt.
    fuori = carica_soppressioni()
    n_tolte = 0
    if fuori:
        pasti_chiusi = {(d, m) for d, m, f in fuori if f.startswith("recipe:")}
        prima = len(added)
        added = [r for r in added
                 if (r["date"], r["meal"], r["food_id"]) not in fuori
                 and not (r["food_id"].startswith("recipe:")
                          and (r["date"], r["meal"]) in pasti_chiusi)]
        n_tolte = prima - len(added)

    added.sort(key=lambda r: (r["date"], r["meal"]))

    n_days = (d1 - d0).days + 1
    by_kind = defaultdict(int)
    for r in added:
        by_kind[r["food_id"]] += 1
    print(f"finestra {d0} → {d1}  ({n_days} giorni, {len(days)} raccontati)")
    for fid, n in sorted(by_kind.items()):
        print(f"  +{n:4d}  {fid}")
    print(f"  totale {len(added)} righe assunte")
    if n_tolte:
        print(f"  -{n_tolte} tolte perche' smentite in {SUPPRESS.name}")
    print(f"  panini da bici distribuiti: {n_panini}")

    if args.check:
        print("\n(--check: niente scritto)")
        return
    common.write_csv(OUT, FIELDS, added)
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
