#!/usr/bin/env python3
"""Svuota la casella del diario dentro `tools/food/data/food_log.csv`.

/vita e' una pagina statica: quando Michele annota qualcosa dal telefono, l'annotazione
va nel Worker `vita-diario` (D1), che la serve subito alla pagina. Ma il registro del
cibo e' uno solo ed e' il CSV in questo repo — quindi ogni ora questo script prende le
operazioni pendenti e le SCRIVE nel CSV, poi le marca `applied`. Da quel momento la
pagina le legge dalla build, non piu' dalla casella: nessun doppio conteggio.

Le tre operazioni:

  add   una riga nuova           -> si appende in coda a food_log.csv
  set   correggi una quantita'   -> si riscrive la riga puntata da row_key
  del   togli una riga           -> si toglie la riga puntata da row_key

`row_key` e' `<pasto>|<food_id>|<ordinale nel pasto>`: la stessa chiave con cui la
pagina identifica una riga di `days.json`. Per ritrovarla nel CSV si ricostruisce lo
stesso ordinamento — le righe di quel giorno e di quel pasto, nell'ordine in cui
stanno nel file — e si prende l'n-esima con quel food_id.

**Le righe ricostruite si smentiscono, non si correggono.** `fill_defaults.py` inventa
i pasti dei giorni muti e scrive in `assumed_log.csv`, che qui non entra mai. Fino al
2026-08-14 un `set`/`del` su una di quelle veniva saltato — corretto come principio, ma
lasciava Michele senza modo di dire "quel piatto non l'ho mangiato". Ora la dashboard
manda quelle operazioni con row_key `assunto|<pasto>|<food_id>`, e qui diventano righe
di `food/data/diary_suppress.csv`: un `del` toglie l'ipotesi, un `set` la toglie e
scrive al suo posto una riga VERA con la quantita' dichiarata. Il diario resta il
racconto di Michele; l'ipotesi smentita sparisce al primo `fill_defaults`.

Un `set`/`del` su una riga che nel CSV non c'e' e non e' marcata assunta resta SALTATO
e riferito, non forzato.

Se il Worker non risponde, o le chiavi non ci sono, lo script esce a zero senza
scrivere: la Action oraria deve continuare a rigenerare /vita anche quando la casella
non e' raggiungibile.

    python tools/apply_diary_ops.py
    python tools/apply_diary_ops.py --check     # dice cosa farebbe, non scrive
"""
import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "food", "data", "food_log.csv")
FIELDS = ["date", "meal", "food_id", "qty", "note", "source"]
# La lista delle ricostruzioni smentite. La legge fill_defaults.py, che senza di
# essa rimetterebbe la riga al giro dopo: `assumed_log.csv` e' un OUTPUT, e
# cancellarci dentro non vuol dire niente.
SUPPRESS = os.path.join(HERE, "food", "data", "diary_suppress.csv")
SUPPRESS_FIELDS = ["date", "meal", "food_id", "nota", "quando"]
# Le righe ricostruite arrivano dalla dashboard con questo prefisso al posto
# dell'ordinale: `assunto|<pasto>|<food_id>` — dove food_id puo' essere
# `recipe:<id>`, perche' una ricetta si smentisce intera.
PREFISSO_ASSUNTO = "assunto|"
BASE = (os.environ.get("VITA_DIARY_URL")
        or "https://vita-diario.micmer-recastello.workers.dev").rstrip("/")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def api(path, body=None, method="GET"):
    admin = (os.environ.get("VITA_DIARY_ADMIN") or "").strip()
    if not admin:
        return None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    # Cloudflare risponde 403 allo user-agent di urllib, anche sugli endpoint
    # pubblici: senza questa riga sembra un problema di chiavi e non lo e'.
    req.add_header("User-Agent", "vita-apply-diary-ops/1.0")
    req.add_header("X-Vita-Admin", admin)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  ! casella non raggiungibile ({e}) — /vita si rigenera lo stesso",
              file=sys.stderr)
        return None


def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("date")]


def write_log(rows):
    # newline="" + lineterminator: il file e' a CRLF e va tenuto tale, se no ogni
    # travaso riscriverebbe 400 righe di diff per un a capo cambiato
    with open(LOG, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS, lineterminator="\r\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def leggi_soppressioni():
    if not os.path.exists(SUPPRESS):
        return []
    with open(SUPPRESS, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def scrivi_soppressioni(righe):
    with open(SUPPRESS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SUPPRESS_FIELDS)
        w.writeheader()
        w.writerows(righe)


def chiave_assunta(row_key):
    """(pasto, food_id) da `assunto|<pasto>|<food_id>`, o None se non e' una di quelle.

    I pezzi sono esattamente tre: ne' il pasto ne' il food_id contengono "|". Il
    food_id puo' essere `recipe:<id>`, che ha i due punti ma non la barra, quindi
    lo split semplice basta e non serve limitarne il numero.
    """
    if not row_key.startswith(PREFISSO_ASSUNTO):
        return None
    pezzi = row_key.split("|")
    if len(pezzi) != 3 or not pezzi[2]:
        return None
    return pezzi[1], pezzi[2]


def locate(rows, day, row_key):
    """L'indice in `rows` della riga puntata da row_key, o None.

    row_key = pasto|food_id|ordinale. L'ordinale conta SOLO le righe con quel
    food_id dentro quel pasto, nell'ordine del file — che e' lo stesso ordine con
    cui la pagina le ha numerate leggendo days.json.
    """
    try:
        meal, food_id, nth = row_key.rsplit("|", 2)
        nth = int(nth)
    except (ValueError, AttributeError):
        return None
    seen = 0
    for i, r in enumerate(rows):
        if r["date"] != day or (r.get("meal") or "") != meal:
            continue
        if r["food_id"] != food_id:
            continue
        if seen == nth:
            return i
        seen += 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="riporta e basta, non scrive")
    args = ap.parse_args()

    if not (os.environ.get("VITA_DIARY_ADMIN") or "").strip():
        print("  diario: nessuna chiave admin, casella non interrogata")
        return

    payload = api("/api/pending")
    if payload is None:
        return
    ops = payload.get("ops") or []
    if not ops:
        print("  diario: casella vuota")
        return

    rows = read_log()
    fuori = leggi_soppressioni()
    n_fuori_prima = len(fuori)
    applied, skipped = [], []

    # add per ultime: un `set`/`del` punta a una riga che c'era gia' quando la pagina
    # l'ha numerata, e infilarci in mezzo le righe nuove sposterebbe gli ordinali
    for op in sorted(ops, key=lambda o: (o["day"], o["kind"] == "add", o["id"])):
        kind, day = op["kind"], op["day"]
        if kind == "add":
            rows.append({
                "date": day, "meal": op.get("meal") or "spuntino",
                "food_id": op["food_id"], "qty": f'{float(op["qty"]):g}',
                "note": (op.get("note") or "annotato dal diario di /vita"),
                "source": "dichiarato",
            })
            applied.append(op["id"])
            print(f"  + {day} {op.get('meal')} {op['food_id']} {float(op['qty']):g}")
            continue

        # Una riga ricostruita non sta nel CSV, quindi non si "corregge": si
        # SMENTISCE. `del` la toglie dalle ipotesi; `set` la toglie e al suo posto
        # scrive una riga vera con la quantita' che hai detto tu — cosi' la
        # provenienza resta onesta (dichiarato, non assunto) e non si conta due volte.
        assunta = chiave_assunta(op.get("row_key") or "")
        if assunta:
            pasto, food_id = assunta
            fuori.append({"date": day, "meal": pasto, "food_id": food_id,
                          "nota": (op.get("note") or "smentita dal diario"),
                          "quando": op.get("created_at") or ""})
            if kind == "set" and float(op.get("qty") or 0) > 0:
                rows.append({
                    "date": day, "meal": pasto, "food_id": food_id,
                    "qty": f'{float(op["qty"]):g}',
                    "note": "ricostruzione corretta a mano dal diario",
                    "source": "dichiarato",
                })
                print(f"  ~ {day} {pasto} {food_id}: ricostruzione -> dichiarata {float(op['qty']):g}")
            else:
                print(f"  - {day} {pasto} {food_id}: ricostruzione smentita")
            applied.append(op["id"])
            continue

        i = locate(rows, day, op.get("row_key") or "")
        if i is None:
            # tipicamente: la riga era una ricostruzione di fill_defaults.py, che in
            # food_log.csv non c'e' e non deve entrarci
            skipped.append(op["id"])
            print(f"  ? {day} {op.get('row_key')}: non e' una riga del diario, saltata")
            continue
        if kind == "set":
            rows[i]["qty"] = f'{float(op["qty"]):g}'
            rows[i]["note"] = (rows[i].get("note") or "") + " · corretto dal diario di /vita"
            print(f"  ~ {day} {op['row_key']} -> {float(op['qty']):g}")
        else:
            print(f"  - {day} {op['row_key']} ({rows[i]['qty']})")
            rows.pop(i)
        applied.append(op["id"])

    print(f"  diario: {len(applied)} operazioni travasate"
          + (f", {len(skipped)} saltate" if skipped else ""))

    if args.check:
        print("  (--check: niente scritto, niente marcato)")
        return

    write_log(rows)
    if len(fuori) != n_fuori_prima:
        scrivi_soppressioni(fuori)
        print(f"  diario: {len(fuori) - n_fuori_prima} ricostruzioni smentite -> {os.path.basename(SUPPRESS)}")
    # Anche le saltate si marcano: restando pendenti tornerebbero a ogni ora, e a
    # ogni ora fallirebbero allo stesso modo. Il riferimento resta qui sopra.
    if applied or skipped:
        api("/api/applied", {"ids": applied + skipped}, method="POST")


if __name__ == "__main__":
    main()
