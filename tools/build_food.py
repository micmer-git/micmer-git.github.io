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

REGISTRO = os.path.join(FOOD, "data", "food_log.csv")
SALUTE = "salute.json"
# Due giorni interi di silenzio. Uno solo non dice niente: oggi e' in corso, e
# ieri puo' essere raccontato domattina. Tre erano gia' troppi — e' il buco che
# e' passato inosservato dal 19 al 21/08/2026.
GIORNI_A_SECCO = 2


QUATTRO = ("pct_plant", "pct_dairy", "pct_animal", "pct_other")
# Un punto percentuale. Le quattro quote si arrotondano a un decimale, quindi uno
# scarto di 0,1 e' l'arrotondamento e non un errore; mezzo punto e' gia' sospetto,
# uno intero vuol dire che una caloria e' finita in due fette o in nessuna.
TOLLERANZA_PARTIZIONE = 1.0


def partizione_delle_calorie(dove):
    """Le quattro quote di «Da dove arrivano le calorie» devono fare cento.

    «Attento che la somma li' deve essere 100%» (Michele, 21/08/2026, ordine #23).
    Vegetale, latticini, animale e altro sono una **partizione**: ogni caloria sta
    in una fetta sola. Se un alimento nuovo entra in foods.csv senza il campo
    `plant`, la sua quota sparisce da tutte e quattro e il riquadro mente di
    quel tanto, senza che nessun disegno se ne accorga — la somma non e' scritta
    da nessuna parte, quindi non c'e' niente che stoni.

    L'ultra-processato NON entra nel conto: attraversa tutte e quattro (un
    cornetto e' vegetale e ultra-processato insieme), quindi sommarlo con loro
    darebbe piu' di cento per costruzione.
    """
    import csv as _csv

    p = os.path.join(dove, "nutrition.csv")
    peggio, giorno, fuori = 0.0, None, 0
    with open(p, encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            if not all(c in r for c in QUATTRO):
                return {"ok": None, "perche": "nutrition.csv non porta le quattro quote"}
            try:
                s = sum(float(r[c]) for c in QUATTRO)
            except (ValueError, TypeError):
                continue
            if s == 0:                      # giorno senza cibo: non e' una partizione rotta
                continue
            d = abs(s - 100.0)
            if d > peggio:
                peggio, giorno = d, next(iter(r.values()))
            if d > TOLLERANZA_PARTIZIONE:
                fuori += 1
    return {"ok": fuori == 0, "scarto_max": round(peggio, 3),
            "giorno_peggiore": giorno, "giorni_fuori": fuori,
            "tolleranza": TOLLERANZA_PARTIZIONE}


def salute_del_diario(dove):
    """Scrive quanti giorni sono che nel registro non entra niente.

    Serve perche' un registro a digiuno e uno sano si assomigliano troppo:
    `fill_defaults.py` ricostruisce i pasti abituali nei giorni muti, quindi la
    pagina mostra numeri anche quando nessuno ha annotato nulla, l'Action resta
    verde e il Worker risponde `ok:true` con la casella vuota. Nessuno di quei
    tre segnali sa distinguere «non ha mangiato niente di diverso dal solito» da
    «non lo sta piu' scrivendo nessuno».

    Qui la differenza diventa un fatto pubblico e leggibile da fuori, cosi' che
    `bin/check-health.ps1` del repo agents la trovi ogni giorno. Vale la regola
    di casa: osservato e ricostruito non sono la stessa cosa, e questo file dice
    quale dei due si sta guardando.
    """
    import datetime as _dt
    import json as _json

    giorni = set()
    righe = 0
    with open(REGISTRO, encoding="utf-8") as f:
        next(f, None)
        for riga in f:
            g = riga.split(",", 1)[0].strip()
            if len(g) == 10 and g[4] == "-":
                giorni.add(g)
                righe += 1

    ultimo = max(giorni) if giorni else None
    oggi = _dt.date.today()
    secco = ((oggi - _dt.date.fromisoformat(ultimo)).days if ultimo else 9999)

    part = partizione_delle_calorie(dove)
    stato = {
        # Due cose in un segnale solo, e i campi sotto dicono quale delle due:
        # che il diario riceva ancora righe, e che le quattro quote facciano cento.
        "ok": secco <= GIORNI_A_SECCO and part.get("ok") is not False,
        "partizione": part,
        "ultimo_giorno": ultimo,
        "giorni_a_secco": secco,
        "soglia": GIORNI_A_SECCO,
        "righe": righe,
        "giorni": len(giorni),
        "letto": oggi.isoformat(),
        # Dal 2026-08-14 /vita e' pubblica e si legge soltanto: si annota da
        # Mission Control, che e' dietro login e parla con lo stesso Worker.
        "dove_si_annota": "https://micmer-mission.pages.dev — pannello Vita",
    }
    p = os.path.join(dove, SALUTE)
    with open(p, "w", encoding="utf-8") as f:
        _json.dump(stato, f, ensure_ascii=False, indent=1)
    return stato


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

    stato = salute_del_diario(DATA)
    p = stato["partizione"]
    if p.get("ok") is False:
        print(f"\n· ⚠ LE QUATTRO QUOTE NON FANNO CENTO: {p['giorni_fuori']} giorni oltre "
              f"{p['tolleranza']} punti, il peggiore {p['giorno_peggiore']} "
              f"({p['scarto_max']}). Di solito e' un alimento nuovo in foods.csv "
              f"senza il campo `plant`.")
    elif p.get("ok"):
        print(f"\n· le quattro quote fanno cento (scarto massimo {p['scarto_max']} punti)")

    if stato["ok"]:
        print(f"\n· diario alimentare: nutrito — ultimo giorno {stato['ultimo_giorno']}")
    else:
        print(f"\n· ⚠ DIARIO A SECCO: {stato['giorni_a_secco']} giorni senza una riga "
              f"(ultimo {stato['ultimo_giorno']}). La pagina intanto mostra i pasti "
              f"ricostruiti, che e' il motivo per cui non se ne accorge nessuno.")

    print("\nfile pubblicati in vita/cibo/data/:")
    for f in ("nutrition.csv", "days.json", "microbiome.csv", "flora_foods.csv",
              "metabolismo.csv", SALUTE):
        p = os.path.join(DATA, f)
        print(f"  {f:<18} {os.path.getsize(p) // 1024:5d} KB" if os.path.exists(p)
              else f"  {f:<18} MANCANTE")
    print("\nora: python tools/build_vita.py  (per inlinarli nella pagina)")


if __name__ == "__main__":
    main()
