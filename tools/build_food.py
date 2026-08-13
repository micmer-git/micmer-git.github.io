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
  1b. `cronometer.py`     — l'export Cronometer, cioe' i 265 giorni in cui il cibo
                            e' stato pesato per davvero, in
                            `data/derived/cronometer_days.json`. Va DOPO
                            fill_defaults.py e PRIMA della serie: il passo 2 usa
                            questi giorni per buttare via la ricostruzione dove
                            esiste la misura. Vedi il docstring di cronometer.py
                            per la regola pieno/parziale.
  2. `build_nutrition_series.py` — somma diario + ricostruzione in una serie
                            giornaliera, e la esporta in `vita/cibo/data/nutrition.csv`
                            (aggregati) e `vita/cibo/data/days.json` (dettaglio popup).
  3. `microbiome_model.py` — il modello della flora e la matrice alimento x genere,
                            in `vita/cibo/data/microbiome.csv` e `flora_foods.csv`.
                            Va dopo il passo 2: legge la serie che produce.
  4. `metabolismo.py`     — temperatura delle uscite (misurata), FatMax (modello)
                            e "momento metabolico" (indice composito), in
                            `vita/cibo/data/metabolismo.csv`. Legge la serie del
                            passo 2 e la cache di Intervals `tools/.cruscotto_cache.json`.

**Il passo 4 non fa rete, mai.** Legge solo la cache gia' scaricata. Se la cache
non c'e' viene SALTATO con un avviso, invece di far fallire tutta la build: chi
clona il repo senza la cache (che e' un artefatto locale, non versionato) deve
poter rigenerare comunque nutrizione e flora. La cache si rinfresca a parte, con
`tools/sync_intervals.py`, che la rete la usa.

I file sotto `vita/cibo/data/` sono **generati**: si rigenerano da qui, non si
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


CACHE = os.path.join(HERE, ".cruscotto_cache.json")


def run(script, *args, optional=False):
    """`optional=True` = se lo script fallisce si prosegue invece di uscire.

    Serve solo a metabolismo.py, che dipende dalla cache di Intervals: la cache
    e' un artefatto locale non versionato, e la sua assenza non deve impedire di
    rigenerare nutrizione e flora, che non ne hanno bisogno.
    """
    cmd = [sys.executable, os.path.join(FOOD, script), *args]
    print(f"\n· {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=FOOD, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "").rstrip()
    if out:
        print("\n".join("  " + l for l in out.splitlines()))
    if r.returncode != 0:
        if optional:
            print("  SALTATO: " + (r.stderr or "").strip().splitlines()[0]
                  if (r.stderr or "").strip() else "  SALTATO")
            return None
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
        run("cronometer.py")
        run("build_nutrition_series.py")
        run("microbiome_model.py", "--check")
        run("metabolismo.py", "--check", optional=True)
        print("\n(--check: nessun file pubblico scritto; cache derived rigenerata)")
        return

    run("fill_defaults.py")
    run("cronometer.py")
    os.makedirs(DATA, exist_ok=True)
    run("build_nutrition_series.py",
        "--export", os.path.join(DATA, "nutrition.csv"),
        "--export-days", os.path.join(DATA, "days.json"))
    run("microbiome_model.py",
        "--export", os.path.join(DATA, "microbiome.csv"),
        "--export-foods", os.path.join(DATA, "flora_foods.csv"))
    if os.path.exists(CACHE):
        run("metabolismo.py", "--export", os.path.join(DATA, "metabolismo.csv"),
            optional=True)
    else:
        print(f"\n· metabolismo.py SALTATO: manca {CACHE}"
              f"\n  (rigenerala con tools/sync_intervals.py — quella la rete la usa)")

    print("\nfile pubblicati in vita/cibo/data/:")
    for f in ("nutrition.csv", "days.json", "microbiome.csv", "flora_foods.csv",
              "metabolismo.csv"):
        p = os.path.join(DATA, f)
        print(f"  {f:<18} {os.path.getsize(p) // 1024:5d} KB" if os.path.exists(p)
              else f"  {f:<18} MANCANTE")
    print("\nora: python tools/build_vita.py  (per inlinarli nella pagina)")


if __name__ == "__main__":
    main()
