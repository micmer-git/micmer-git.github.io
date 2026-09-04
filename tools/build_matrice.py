#!/usr/bin/env python3
"""Il pasto dietro il numero: prepara i dati della Matrice.

Ordine MC #87 del 04/09/2026. Michele aveva visto passare una app che mette
«200 foods plotted on the numbers nobody prints on the label» e ha chiesto se
andava aggiunta qui.

Non si aggiunge quella — e' di qualcun altro. Ma i dati per farla ci sono gia'
tutti, e da mesi: `tools/food/data/foods.csv` sono 206 alimenti con 26 valori
nutrizionali ciascuno, `orac.csv` e' la tabella USDA 2010 riletta a mano.
Quello che manca e' la VISTA. E c'e' una colonna che l'app di nessun altro puo'
avere: quante volte quell'alimento e' finito davvero nel piatto di Michele,
contata su `food_log.csv`.

Questo script non calcola nessuna delle misure derivate: emette i valori per
100 g e basta. Le formule («proteine per 100 kcal», «carboidrati diviso fibra»)
stanno UNA volta sola, nella pagina, perche' e' li' che si scelgono gli assi:
scriverle anche qui vorrebbe dire due definizioni della stessa cosa che
divergono al primo ritocco.

    python tools/build_matrice.py
    node tools/check_matrice.cjs
"""
from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter
from datetime import date

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATI = os.path.join(RADICE, "tools", "food", "data")
USCITA = os.path.join(RADICE, "vita", "matrice", "data", "matrice.json")

# I valori per 100 g che la pagina usa per costruire gli assi. La chiave corta
# tiene il file leggero: 206 alimenti x 14 numeri viaggiano in ~40 kB invece che
# in 150, e questa pagina si apre anche in valle con due tacche.
CAMPI = [
    ("kcal", "kcal"), ("prot", "protein_g"), ("carb", "carb_g"),
    ("zuc", "sugar_g"), ("fib", "fiber_g"), ("gras", "fat_g"),
    ("sat", "satfat_g"), ("mono", "monounsat_g"), ("poli", "polyunsat_g"),
    ("k", "potassium_mg"), ("fe", "iron_mg"), ("mg", "magnesium_mg"),
    ("vitc", "vitc_mg"), ("na", "sodium_mg"),
]


def numero(x):
    """Una cella vuota e' un dato che non c'e', non uno zero.

    ⚠️ La differenza conta e non e' pedanteria: uno zero dice «questo alimento
    non ne ha», un buco dice «non lo sappiamo». Sul grafico il primo e' un punto
    sull'asse, il secondo NON deve comparire — altrimenti ogni alimento senza
    vitamina C misurata sembra un alimento senza vitamina C.
    """
    s = str(x or "").strip().replace(",", ".")
    if s in ("", "-", "n/a", "na"):
        return None
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def leggi_orac():
    """`orac.csv` comincia con venticinque righe di avvertenze, e vanno saltate.

    Il file stesso lo dice: «Un parser deve saltare le righe che cominciano
    con '#'». Lo dice perche' l'ORAC e' una misura in vitro che l'USDA ha
    RITIRATO nel 2012, e chi la guarda senza quel contesto la legge come un
    punteggio da massimizzare. La pagina si porta dietro l'avvertenza.
    """
    p = os.path.join(DATI, "orac.csv")
    righe = [r for r in io.open(p, encoding="utf-8").read().splitlines()
             if not r.startswith("#") and r.strip()]
    fuori = {}
    for r in csv.DictReader(io.StringIO("\n".join(righe))):
        v = numero(r.get("orac_umol_te_100g"))
        if v is not None:
            fuori[r["food_id"]] = (v, (r.get("confidence") or "").strip() or None)
    return fuori


def leggi_volte():
    """Quante volte quell'alimento e' comparso nel diario, e l'ultima data.

    E' la colonna che nessun'altra matrice di nutrienti puo' avere, ed e' il
    motivo per cui questa pagina non e' la copia di quella che Michele aveva
    visto: la nuvola resta quella dei 206 alimenti possibili, ma i SUOI si
    vedono, e si vede dove stanno rispetto a tutti gli altri.
    """
    p = os.path.join(DATI, "food_log.csv")
    conta, ultima = Counter(), {}
    for r in csv.DictReader(io.open(p, encoding="utf-8")):
        fid = (r.get("food_id") or "").strip()
        if not fid:
            continue
        conta[fid] += 1
        d = (r.get("date") or "").strip()
        if d and d > ultima.get(fid, ""):
            ultima[fid] = d
    return conta, ultima


def main():
    orac = leggi_orac()
    volte, ultima = leggi_volte()

    alimenti, senza_kcal = [], []
    for r in csv.DictReader(io.open(os.path.join(DATI, "foods.csv"), encoding="utf-8")):
        fid = r["id"].strip()
        voce = {"id": fid, "n": r["name_it"].strip(), "g": r["group"].strip()}
        for corta, lunga in CAMPI:
            v = numero(r.get(lunga))
            if v is not None:
                voce[corta] = v
        if voce.get("kcal") in (None, 0):
            # Non si butta: si tiene e si dichiara. Un integratore o una spezia
            # senza calorie e' un dato vero, ed e' la pagina a doverlo escludere
            # dagli assi «per 100 kcal» invece di dividere per zero.
            senza_kcal.append(fid)
        if fid in orac:
            voce["orac"], voce["orac_c"] = orac[fid]
        if volte.get(fid):
            voce["volte"] = volte[fid]
            voce["ultima"] = ultima.get(fid)
        nota = (r.get("note") or "").strip()
        if nota:
            voce["nota"] = nota
        if (r.get("plant") or "").strip() not in ("", "0"):
            voce["pianta"] = 1
        if (r.get("upf") or "").strip() == "1":
            voce["upf"] = 1
        alimenti.append(voce)

    mangiati = [a for a in alimenti if a.get("volte")]
    fuori = {
        "generato": date.today().isoformat(),
        "conto": {
            "alimenti": len(alimenti),
            "mangiati": len(mangiati),
            "con_orac": sum(1 for a in alimenti if "orac" in a),
            "senza_kcal": len(senza_kcal),
        },
        "fonti": {
            "nutrienti": "tools/food/data/foods.csv — catalogo di Vita, valori per 100 g",
            "orac": "tools/food/data/orac.csv — USDA ORAC Release 2 (2010), RITIRATA dall'USDA nel 2012",
            "diario": "tools/food/data/food_log.csv — quante volte l'alimento è finito nel piatto",
        },
        "alimenti": alimenti,
    }
    os.makedirs(os.path.dirname(USCITA), exist_ok=True)
    with io.open(USCITA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(fuori, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    kb = os.path.getsize(USCITA) / 1024
    print(f"vita/matrice/data/matrice.json scritto: {len(alimenti)} alimenti, "
          f"{len(mangiati)} mangiati davvero, {fuori['conto']['con_orac']} con ORAC, "
          f"{len(senza_kcal)} senza calorie ({kb:.0f} kB)")


if __name__ == "__main__":
    main()
