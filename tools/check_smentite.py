"""Prova a secco della catena delle smentite, senza Worker e senza toccare i CSV veri.

Tre casi, che sono i tre che la dashboard puo' mandare:
  1. `del` su una ricostruzione   -> una riga in diary_suppress.csv, niente nel diario
  2. `set` su una ricostruzione   -> la smentita PIU' una riga vera, source=dichiarato
  3. `set` su una riga inesistente e non assunta -> saltata, come prima
"""
import csv, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_diary_ops as ad

tmp = tempfile.mkdtemp()
ad.LOG = os.path.join(tmp, "food_log.csv")
ad.SUPPRESS = os.path.join(tmp, "diary_suppress.csv")

with open(ad.LOG, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=ad.FIELDS)
    w.writeheader()
    w.writerow({"date": "2026-08-14", "meal": "pranzo", "food_id": "mela",
                "qty": "150", "note": "", "source": "dichiarato"})

OPS = [
    {"id": 1, "day": "2026-08-14", "kind": "del",
     "row_key": "assunto|cena|recipe:crostata_dolce", "created_at": "2026-08-15T06:00:00Z"},
    {"id": 2, "day": "2026-08-14", "kind": "set", "qty": 1.5,
     "row_key": "assunto|pranzo|recipe:torta_salata_frittata", "created_at": "2026-08-15T06:01:00Z"},
    {"id": 3, "day": "2026-08-14", "kind": "set", "qty": 90,
     "row_key": "cena|pane|0", "created_at": "2026-08-15T06:02:00Z"},
]

marcati = {}
ad.api = lambda rotta, corpo=None, method="GET": (
    {"ops": OPS} if rotta == "/api/pending" else marcati.update(corpo or {}) or {})
os.environ["VITA_DIARY_ADMIN"] = "prova"
sys.argv = ["apply_diary_ops.py"]

ad.main()

print("\n--- food_log.csv ---")
righe = list(csv.DictReader(open(ad.LOG, encoding="utf-8")))
for r in righe:
    print(" ", r["date"], r["meal"], r["food_id"], r["qty"], "|", r["source"], "|", r["note"][:45])

print("--- diary_suppress.csv ---")
fuori = list(csv.DictReader(open(ad.SUPPRESS, encoding="utf-8")))
for r in fuori:
    print(" ", r["date"], r["meal"], r["food_id"], "|", r["nota"])

print("--- marcate come viste ---", sorted(marcati.get("ids", [])))

ok = True
def check(nome, cond):
    global ok
    ok = ok and cond
    print(("  OK   " if cond else "  ROTTO") + "  " + nome)

print("\nverifiche:")
check("la smentita del `del` c'e'",
      any(r["food_id"] == "recipe:crostata_dolce" and r["meal"] == "cena" for r in fuori))
check("il `del` NON ha scritto nel diario",
      not any(r["food_id"] == "recipe:crostata_dolce" for r in righe))
check("il `set` ha smentito l'ipotesi",
      any(r["food_id"] == "recipe:torta_salata_frittata" for r in fuori))
check("il `set` ha scritto una riga vera, dichiarata",
      any(r["food_id"] == "recipe:torta_salata_frittata" and r["source"] == "dichiarato"
          and r["qty"] == "1.5" and r["meal"] == "pranzo" for r in righe))
check("la riga inesistente e' stata saltata, non inventata",
      not any(r["food_id"] == "pane" for r in righe))
check("tutte e tre marcate, cosi' non tornano ogni ora",
      sorted(marcati.get("ids", [])) == [1, 2, 3])
check("il diario di partenza e' intatto",
      any(r["food_id"] == "mela" and r["qty"] == "150" for r in righe))

sys.exit(0 if ok else 1)
