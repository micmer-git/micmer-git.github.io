#!/usr/bin/env python3
"""Collaudo del Worker del diario, contro l'istanza vera.

Non e' un unit test: e' la stessa cosa che fa `check_vita.cjs` per la pagina —
prova che quello che gira davvero fa quello che dice. Ogni caso qui dentro e' una
cosa che, se smettesse di valere, si scoprirebbe solo perche' un giorno il diario
di Michele avrebbe dentro qualcosa di sbagliato:

  * un browser senza chiave, o con la chiave sbagliata, non legge e non scrive;
  * la chiave del browser NON apre gli endpoint della pipeline;
  * un food_id che non e' un id (spazi, virgole, SQL) viene rifiutato prima di
    arrivare al CSV, che e' l'unico posto dove poi farebbe danno;
  * correggere due volte la stessa riga lascia UNA correzione, non due;
  * marcare `applied` toglie l'operazione dalla vista del giorno.

Le chiavi si leggono da `.dev.vars`, che e' gitignorato.

    python tools/diario-worker/check_worker.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("VITA_DIARY_URL",
                      "https://vita-diario.micmer-recastello.workers.dev")
HERE = os.path.dirname(os.path.abspath(__file__))
GIORNO = "1999-01-02"      # una data di prova: nessun giorno vero viene toccato

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def load_keys():
    p = os.path.join(HERE, ".dev.vars")
    out = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    key = os.environ.get("VITA_DIARY_KEY") or out.get("VITA_DIARY_KEY")
    admin = os.environ.get("VITA_DIARY_ADMIN") or out.get("VITA_DIARY_ADMIN")
    if not key or not admin:
        sys.exit("Mancano le chiavi: metti VITA_DIARY_KEY e VITA_DIARY_ADMIN in "
                 f"{p} o nell'ambiente.")
    return key, admin


KEY, ADMIN = load_keys()
fails, notes = [], []


def ok(cond, msg):
    """Stampa subito, oltre a tenere il conto.

    Un riepilogo alla fine e' inutile se un caso piu' avanti solleva: si perde
    l'unica riga che diceva perche'. Qui ogni esito esce quando succede."""
    line = ("ok   " if cond else "FAIL ") + msg
    (notes if cond else fails).append(line)
    print(line)


def call(method, path, body=None, key=None, admin=None):
    """(status, json|None). Gli errori HTTP sono risposte, non eccezioni."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    # Senza, il bordo di Cloudflare risponde 403 allo user-agent di urllib —
    # anche sull'endpoint pubblico, il che rende la diagnosi sviante: sembra una
    # chiave sbagliata e invece la richiesta al Worker non e' proprio arrivata.
    req.add_header("User-Agent", "vita-diario-check/1.0")
    if data:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-Vita-Key", key)
    if admin:
        req.add_header("X-Vita-Admin", admin)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except ValueError:
            return e.code, None


# ------------------------------------------------------- il giorno di prova pulito
# Un giro precedente interrotto a meta' lascia le sue operazioni pendenti, e il giro
# dopo conta quelle e sbaglia — cioe' il collaudo fallirebbe per colpa del collaudo.
# Si svuota il giorno di prova prima di cominciare: solo quello, e solo il pendente.
_st, _b = call("GET", f"/api/day/{GIORNO}", key=KEY)
_resti = [o["id"] for o in ((_b or {}).get("ops") or [])]
for _id in _resti:
    call("DELETE", f"/api/ops/{_id}", key=KEY)
if _resti:
    print(f"info  ripulite {len(_resti)} operazioni rimaste da un giro precedente")

# ---------------------------------------------------------------- salute
st, body = call("GET", "/api/health")
ok(st == 200 and body.get("ok") is True,
   f"/api/health risponde senza chiave ({st}, {body})")

# ---------------------------------------------------------------- la porta
st, _ = call("GET", f"/api/day/{GIORNO}")
ok(st == 401, f"senza chiave il giorno non si legge ({st})")
st, _ = call("GET", f"/api/day/{GIORNO}", key="chiave-sbagliata-ma-lunga-uguale")
ok(st == 401, f"con la chiave sbagliata nemmeno ({st})")
st, _ = call("GET", "/api/pending", key=KEY)
ok(st == 401, f"la chiave del browser NON apre /api/pending ({st})")
st, _ = call("POST", "/api/applied", {"ids": [1]}, key=KEY)
ok(st == 401, f"ne' /api/applied ({st})")

# ------------------------------------------------- quello che non deve entrare
brutti = [
    ({"day": "13/08/2026", "kind": "add", "meal": "spuntino", "food_id": "mela", "qty": 1}, "data all'italiana"),
    ({"day": GIORNO, "kind": "mangia", "meal": "spuntino", "food_id": "mela", "qty": 1}, "tipo inventato"),
    ({"day": GIORNO, "kind": "add", "meal": "spuntino", "food_id": "mela'); DROP TABLE ops;--", "qty": 1}, "SQL nell'id"),
    ({"day": GIORNO, "kind": "add", "meal": "spuntino", "food_id": "Mela Rossa", "qty": 1}, "spazi e maiuscole nell'id"),
    ({"day": GIORNO, "kind": "add", "meal": "aperitivo", "food_id": "mela", "qty": 1}, "pasto inventato"),
    ({"day": GIORNO, "kind": "add", "meal": "spuntino", "food_id": "mela", "qty": 99999}, "quantita' fuori scala"),
    ({"day": GIORNO, "kind": "add", "meal": "spuntino", "food_id": "mela", "qty": -3}, "quantita' negativa"),
    ({"day": GIORNO, "kind": "set", "qty": 10}, "correzione senza row_key"),
]
respinti = 0
for payload, perche in brutti:
    st, _ = call("POST", "/api/ops", payload, key=KEY)
    if st == 400:
        respinti += 1
    else:
        fails.append(f"FAIL accettata una cosa da rifiutare ({perche}): {st}")
ok(respinti == len(brutti), f"tutte e {len(brutti)} le richieste malformate respinte")

# ---------------------------------------------------------------- il giro buono
st, body = call("POST", "/api/ops",
                {"day": GIORNO, "kind": "add", "meal": "spuntino",
                 "food_id": "mela", "qty": 1, "note": "collaudo"}, key=KEY)
ok(st == 201 and body.get("op"), f"una mela si annota ({st})")
mela_id = (body.get("op") or {}).get("id")

st, body = call("POST", "/api/ops",
                {"day": GIORNO, "kind": "add", "meal": "colazione",
                 "food_id": "recipe:colazione_standard", "qty": 1}, key=KEY)
ok(st == 201, f"e anche una ricetta, con il suo prefisso ({st})")

for q in (80, 95):
    st, body = call("POST", "/api/ops",
                    {"day": GIORNO, "kind": "set", "row_key": "spuntino|pane_integrale|0",
                     "food_id": "pane_integrale", "qty": q}, key=KEY)
    ok(st == 201, f"correzione a {q} accettata ({st})")

st, body = call("GET", f"/api/day/{GIORNO}", key=KEY)
ops = body.get("ops") or []
sets = [o for o in ops if o["kind"] == "set"]
ok(len(ops) == 3, f"il giorno ha tre operazioni, non quattro ({len(ops)})")
ok(len(sets) == 1 and sets[0]["qty"] == 95,
   f"due correzioni sulla stessa riga ne lasciano UNA, l'ultima ({sets and sets[0]['qty']})")

# ---------------------------------------------------------------- disfare
st, _ = call("DELETE", f"/api/ops/{mela_id}", key=KEY)
ok(st == 200, f"un'annotazione pendente si disfa ({st})")
st, body = call("GET", f"/api/day/{GIORNO}", key=KEY)
ok(len(body.get("ops") or []) == 2, "e sparisce dal giorno")

# ---------------------------------------------------------------- il travaso
st, body = call("GET", "/api/pending", admin=ADMIN)
miei = [o["id"] for o in (body.get("ops") or []) if o["day"] == GIORNO]
ok(st == 200 and len(miei) == 2, f"la pipeline vede le due pendenti ({len(miei)})")

st, body = call("POST", "/api/applied", {"ids": miei}, admin=ADMIN)
ok(st == 200 and body.get("marcate") == 2, f"e le marca travasate ({body})")

st, body = call("GET", f"/api/day/{GIORNO}", key=KEY)
ok(len(body.get("ops") or []) == 0,
   "una volta nel repo non tornano piu' come pendenti — niente doppio conteggio")

st, _ = call("DELETE", f"/api/ops/{miei[0]}", key=KEY)
ok(st == 409, f"e non si possono piu' disfare da qui ({st}): si corregge nel repo")

print(f"\n{len(notes)} passati, {len(fails)} falliti")
if fails:
    sys.exit(1)
print("worker a posto")
