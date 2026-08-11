#!/usr/bin/env python3
"""
build_food.py — rigenera tutti i dati dell'alimentazione che /vita pubblica.

Un comando solo al posto di tre, e soprattutto **dentro questo repo**. Fino al
2026-08-10 la pipeline viveva in `~/health-log`, che ha il remote puntato su
`pweurope/mangiafortissimo` — un repo che non esiste — quindi non era pubblicabile
e la GitHub Action non poteva rigenerare niente: i CSV in `vita/` erano copie
committate a mano, che e' esattamente il modo in cui due superfici divergono senza
che nessuno se ne accorga. Ora la sorgente sta qui, una copia sola.

Cosa gira, in ordine, e perche' quest'ordine:

  1. `fill_defaults.py`   — ricostruisce i pasti abituali nei giorni muti
                            (colazione fissa, 2 avocado toast e 2 dahl a settimana,
                            piu' i piatti del mese) in `data/derived/assumed_log.csv`.
                            **Non tocca `food_log.csv`**: il diario resta quello
                            che l'utente ha davvero raccontato.
  2. `build_nutrition_series.py` — somma diario + ricostruzione in una serie
                            giornaliera, e la esporta in `vita/cibo/data/nutrition.csv`
                            (aggregati) e `vita/cibo/data/days.json` (dettaglio popup).
  3. `microbiome_model.py` — il modello della flora e la matrice alimento x genere,
                            in `vita/cibo/data/microbiome.csv` e `flora_foods.csv`.
                            Va per ultimo: legge la serie prodotta al passo 2.

I quattro file sotto `vita/` sono **generati**: si rigenerano da qui, non si
modificano a mano.

    python tools/build_food.py
    python tools/build_food.py --check     # riporta e basta, non scrive
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FOOD = os.path.join(HERE, "food")
VITA = os.path.join(os.path.dirname(HERE), "vita")
DATA = os.path.join(VITA, "cibo", "data")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def run(script, *args):
    cmd = [sys.executable, os.path.join(FOOD, script), *args]
    print(f"\n· {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=FOOD, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "").rstrip()
    if out:
        print("\n".join("  " + l for l in out.splitlines()))
    if r.returncode != 0:
        sys.stderr.write((r.stderr or "")[-2000:])
        sys.exit(f"\n{script} è uscito con {r.returncode}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="riporta, non scrive")
    args = ap.parse_args()

    if args.check:
        # The microbiome check consumes the two derived files from the earlier
        # stages. They are gitignored build cache, so regenerate them while still
        # guaranteeing that --check never touches the published vita/cibo/data.
        run("fill_defaults.py")
        run("build_nutrition_series.py")
        run("microbiome_model.py", "--check")
        print("\n(--check: nessun file pubblico scritto; cache derived rigenerata)")
        return

    run("fill_defaults.py")
    os.makedirs(DATA, exist_ok=True)
    run("build_nutrition_series.py",
        "--export", os.path.join(DATA, "nutrition.csv"),
        "--export-days", os.path.join(DATA, "days.json"))
    run("microbiome_model.py",
        "--export", os.path.join(DATA, "microbiome.csv"),
        "--export-foods", os.path.join(DATA, "flora_foods.csv"))

    print("\nfile pubblicati in vita/cibo/data/:")
    for f in ("nutrition.csv", "days.json", "microbiome.csv", "flora_foods.csv"):
        p = os.path.join(DATA, f)
        print(f"  {f:<18} {os.path.getsize(p) // 1024:5d} KB" if os.path.exists(p)
              else f"  {f:<18} MANCANTE")
    print("\nora: python tools/build_vita.py  (per inlinarli nella pagina)")


if __name__ == "__main__":
    main()
