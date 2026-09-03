#!/usr/bin/env python3
"""Serie giornaliere di alimentazione, dal diario + la ricostruzione + il carico.

Produce `data/derived/nutrition_series.csv`, una riga al giorno, e sa esportarne
una copia per il sito (`--export <path>`). Quello che esce non e' il diario: sono
solo aggregati giornalieri. Il dettaglio dei pasti resta in questa repo.

Le serie, e da dove escono:

| colonna | cos'e' |
|---|---|
| `kcal`, `protein_g`, `carb_g`, `sugar_g`, `fiber_g`, `fat_g` | somma del giorno |
| `magnesium_mg`, `potassium_mg` | somma del giorno |
| `vit_index`, `min_index` | vedi sotto |
| `plants_7d` | specie vegetali **distinte** negli ultimi 7 giorni |
| `carb_target_g` | fabbisogno di carboidrati stimato dal TSS del giorno |
| `carb_gap_g` | ingeriti − stimati |
| `microbiome` | indice proxy 0-100, vedi sotto |
| `kcal_observed`, `kcal_assumed` | quanta parte della giornata e' raccontata |

**`vit_index` e `min_index`.** Media delle percentuali di fabbisogno coperte, ognuna
**tagliata a 100 prima di fare la media**: senza il taglio, 900 µg di vitamina A da
una carota coprirebbero il buco di vitamina D, che non e' come funziona un
fabbisogno. Vitamine: C, A, D, B12, folati. Minerali: potassio, calcio, ferro,
magnesio, zinco — il sodio no, e' un tetto, non un obiettivo.

**`carb_target_g`.** Regola pratica da letteratura endurance: 3 g/kg al giorno da
fermo, ~6 g/kg attorno a un TSS di 100, fino a 10 g/kg nelle giornate grosse.
Linearizzata come `g/kg = 3 + 0,03 · TSS`, tagliata in [3, 10]. E' un ordine di
grandezza per leggere lo scarto, non una prescrizione.

**`microbiome`.** Un **proxy costruito dal diario**, non una misura: nessuno qui sta
sequenziando niente. Pesa quello che la letteratura associa alla diversita' del
microbiota, con i pesi scritti in chiaro qui sotto in MICROBIOME_W: diversita'
vegetale sui 7 giorni (obiettivo 30 specie), fibra media sui 7 giorni (obiettivo
30 g), giorni con almeno un fermentato, e una penalita' per la quota di calorie
ultra-processate. Serve a vedere una tendenza, e va letto solo come tale.

    python scripts/build_nutrition_series.py
    python scripts/build_nutrition_series.py --check
    python scripts/build_nutrition_series.py --export ../micmer.../vita/cibo/data/nutrition.csv
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta

import common

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = common.DERIVED / "nutrition_series.csv"
ASSUMED = common.DERIVED / "assumed_log.csv"
# I giorni misurati con Cronometer, preparati da cronometer.py. Dove ci sono, vincono
# loro: vedi il docstring di quel file per il perche' e per la regola pieno/parziale.
CRONOMETER = common.DERIVED / "cronometer_days.json"

VITAMINS = ("vitc_mg", "vita_ug", "vitd_ug", "b12_ug", "folate_ug")
MINERALS = ("potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg")

# I nutrienti che il diario mostra PER PASTO (ordine #22, 21/08/2026): le tre righe
# della testata del pasto, piu' tutti quelli che hanno un fabbisogno in profile.json,
# perche' sono esattamente quelli di cui si puo' dire «che percentuale mi ha dato».
# NON sono tutti i 22: sodio, zuccheri e la scomposizione dei grassi hanno un tetto,
# non un obiettivo, e un tetto per pasto non vuol dire niente — si supera nel giorno,
# non nella colazione. L'ordine e' quello dell'array emesso in `mn`, e viaggia nel
# payload come `_mn`: e' l'unico posto dove sta scritto, quindi non puo' divergere.
MEAL_NUTRIENTS = ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g", "omega3_g",
                  "potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg",
                  "vitc_mg", "vita_ug", "vitd_ug", "b12_ug", "folate_ug")


def arrotonda(v):
    """Un decimale sui numeri grandi, tre sui piccoli.

    Un decimale fisso e' abbastanza per 2.619,5 kcal e non lo e' per 0,7 g di
    omega-3: li' l'arrotondamento vale il 7 % del valore. Finche' le percentuali
    di fabbisogno le calcolava solo Python — sul totale VERO, prima di arrotondare
    — non si vedeva. Da quando le ricalcola anche la pagina, partendo dal numero
    arrotondato, le due risposte divergevano: omega-3 al 35 % secondo la pagina e
    al 37 % secondo il payload, a due centimetri di distanza nello stesso riquadro.
    Il check di /vita lo ha preso al primo giro.

    Tre decimali sui piccoli costano pochi byte — sono pochi numeri — e tolgono
    la divergenza alla radice invece di allargare la tolleranza del controllo.
    """
    return round(v, 1) if abs(v) >= 10 else round(v, 3)

PLANT_TARGET = 30      # la regola dei 30 vegetali diversi a settimana
FIBER_TARGET = 30.0    # g/giorno, come da profile.json

# "anche il numero di avocado, lenticchie e cosi' via" (2026-08-10). Ogni voce e'
# (etichetta, {food_id: quanto vale UNO}), cosi' il conteggio esce in unita' che
# hanno senso a dirsi: un avocado, un uovo, una porzione di lenticchie secche —
# non "1.847 grammi di avocado".
TALLY = {
    "avocado":     ("avocado", {"avocado": 150.0}),
    "lenticchie":  ("porzioni di lenticchie", {"lenticchie_secche": 100.0}),
    "uova":        ("uova", {"uovo_intero": 1.0}),
    "banane":      ("banane", {"banana": 1.0}),
    "ceci":        ("porzioni di ceci", {"ceci_scatola": 200.0, "ceci_secchi": 100.0,
                                         "farina_ceci": 100.0, "hummus": 100.0}),
    "avena":       ("porzioni di avena", {"avena_fiocchi": 50.0, "crusca_avena": 50.0}),
    "patate_dolci": ("porzioni di patate dolci", {"patate_dolci": 200.0}),
    "caffe":       ("caffe'", {"caffe_espresso": 1.0}),
}

MICROBIOME_W = {
    "plants": 0.40,     # diversita' vegetale: il fattore con piu' evidenza dietro
    "fiber": 0.30,      # substrato fermentabile
    "fermented": 0.15,  # apporto diretto di microrganismi
    "unprocessed": 0.15,  # penalita' ultra-processati (emulsionanti, dolcificanti)
}

FIELDS = ["date", "kcal", "protein_g", "carb_g", "sugar_g", "fiber_g", "fat_g",
          "satfat_g", "magnesium_mg", "potassium_mg", "sodium_mg",
          "vit_index", "min_index", "plants_day", "plants_7d",
          "tss", "carb_target_g", "carb_gap_g", "microbiome",
          "kcal_observed", "kcal_assumed", "n_items",
          # ORIGINE delle calorie, quattro fette di una torta sola: fanno 100 (±0,1 di
          # arrotondamento). Percentuali e non grammi perche' la domanda e' "quanto
          # della mia dieta e'..." e non "quanto ne ho mangiato".
          "pct_plant", "pct_dairy", "pct_animal", "pct_other",
          # LAVORAZIONE, che e' un altro asse e NON una quinta fetta: un cornetto e'
          # vegetale e ultra-processato insieme. Attraversa le quattro di sopra e non
          # va sommato con loro.
          "pct_upf",
          # MACRO in quota di energia: proteine e carboidrati x4 kcal/g, grassi x9.
          # Anche queste fanno ~100, e quello che manca e' fibra e alcol, che le
          # 4/4/9 non contano.
          "pct_kcal_protein", "pct_kcal_carb", "pct_kcal_fat",
          # DI CHE GRASSO sono fatti i grassi. Fino al 17/08/2026 esistevano solo dove
          # Cronometer aveva pesato la giornata intera — quattro giorni al mese — perche'
          # il database interno conosceva i soli saturi. Ora il catalogo porta anche mono,
          # poli e trans, RICOSTRUITI da profili di acidi grassi noti
          # (tools/food/profili_grassi.py), e la serie esiste su ogni giorno con del cibo.
          # Restano due cose diverse, e `fat_split_src` dice sempre quale: dove Cronometer
          # ha pesato vince la MISURA, altrove e' una RICOSTRUZIONE. Dove non c'e' ne'
          # l'una ne' l'altra la cella resta vuota, non zero.
          "mono_g", "poly_g", "trans_g", "fat_split_mis",
          # ORAC: la capacita' antiossidante in vitro del giorno, in micromol Trolox
          # equivalenti. `orac_cov_pct` e' la quota di calorie del giorno che arriva
          # da alimenti per cui un valore ORAC esiste davvero: senza, un totale basso
          # e un catalogo bucato hanno lo stesso aspetto. Vuote — non zero — dove il
          # giorno lo ha scritto Cronometer, che non porta food_id.
          "orac", "orac_cov_pct",
          # Le dodici caselle di Greger, in PORZIONI del giorno. Anche queste vuote
          # sui giorni di Cronometer, per la stessa ragione.
          ] + ["dd_" + c for c, _ in common.DAILY_DOZEN] + [
          # quante prese di integratore, che fino al 03/09/2026 il registro non
          # sapeva contare perche' non ne aveva nessuna
          "suppl_n",
          ] + ["cnt_" + k for k in TALLY]


# Esercizio, la dodicesima casella: non e' un alimento e il diario non lo sa. Greger
# chiede 90 minuti moderati OPPURE 40 vigorosi, quindi un minuto vigoroso vale 2,25
# minuti moderati e la casella si spunta con `min_mod/90 + min_vig/40`.
# Il taglio fra moderato e vigoroso e' l'`intensity` di Intervals (l'intensity factor):
# 0,75 e' la soglia dichiarata qui e da nessun'altra parte. Sotto — o dove l'intensity
# manca — l'uscita conta come moderata, che e' il verso prudente.
ESERCIZIO_IF = 0.75
MIN_MODERATI = 90.0
MIN_VIGOROSI = 40.0


def macro_split(t):
    """Quota di energia da proteine, carboidrati e grassi. Fanno 100 per costruzione.

    Il denominatore sono le tre macro (Atwater 4/4/9), NON le kcal del giorno. Sembra
    un dettaglio e non lo e': le kcal arrivano dal database alimenti o da Cronometer,
    le macro sono campi loro, e i due conti non tornano mai identici. Dividendo per le
    kcal, le tre quote sommavano fra 97 e 122 a seconda del giorno — cioe' una
    "composizione" che a volte fa 122 %, che come composizione non si puo' vedere.
    Diviso per le macro fa 100 sempre, ed e' anche la definizione che usa qualunque
    app di nutrizione quando dice "il tuo split e' 20/55/25".

    Le kcal restano la serie dell'energia: questa risponde a "di cosa erano fatte".
    """
    e = {"protein": t["protein_g"] * 4.0, "carb": t["carb_g"] * 4.0,
         "fat": t["fat_g"] * 9.0}
    tot = sum(e.values()) or 1.0
    return {"pct_kcal_" + k: round(100.0 * v / tot, 1) for k, v in e.items()}


def load_rows():
    """food_log + assumed_log, gia' espansi dalle ricette, con la provenienza."""
    recipes = common.load_recipes()
    rows = list(common.load_food_log())
    for r in rows:
        r.setdefault("source", "dichiarato")
    if ASSUMED.exists():
        with ASSUMED.open(encoding="utf-8", newline="") as fh:
            rows += [r for r in csv.DictReader(fh) if r.get("date")]
    else:
        print("  ! manca assumed_log.csv — gira prima scripts/fill_defaults.py",
              file=sys.stderr)
    # expand_log porta avanti tutte le chiavi della riga, quindi `source`
    # sopravvive all'espansione delle ricette
    return common.expand_log(rows, recipes)


def load_tss():
    """TSS per giorno da activities.csv, piu' il backfill Strava.

    Il backfill (tools/strava_backfill.py) porta le attivita' che Intervals non ha:
    senza, il fabbisogno di carboidrati di quei giorni si calcola su TSS zero, cioe'
    3 g/kg da fermo, e il divario esce enorme per il motivo sbagliato.
    """
    tss = defaultdict(float)
    for path in (common.ACTIVITIES_CSV, common.ACTIVITIES_BACKFILL_CSV):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                d = (r.get("date") or "")[:10]
                if d:
                    tss[d] += float(r.get("training_load") or 0)
    return tss


def load_esercizio():
    """{giorno: porzioni della casella `esercizio` dei Daily Dozen}.

    E' l'unica delle dodici che NON si legge nel diario alimentare: il dato sta in
    activities.csv, cioe' in intervals.icu. Sta scritto anche in daily_dozen.csv, che
    per questa categoria lascia il food_id vuoto apposta.
    """
    out = defaultdict(float)
    for path in (common.ACTIVITIES_CSV, common.ACTIVITIES_BACKFILL_CSV):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                d = (r.get("date") or "")[:10]
                if not d:
                    continue
                try:
                    minuti = float(r.get("moving_time_s") or 0) / 60.0
                except ValueError:
                    continue
                if minuti <= 0:
                    continue
                try:
                    inten = float(r.get("intensity") or 0)
                except ValueError:
                    inten = 0.0
                out[d] += minuti / (MIN_VIGOROSI if inten >= ESERCIZIO_IF else MIN_MODERATI)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--export", help="scrive una seconda copia qui (per il sito)")
    ap.add_argument("--export-days", help="dettaglio giorno per giorno in JSON (per il "
                                          "popup di /vita): pasti, alimenti e %% dei fabbisogni")
    args = ap.parse_args()

    foods = common.load_foods()
    profile = common.load_profile()
    rda = profile["rda"]
    weight = profile["weight_kg"]
    rows = load_rows()
    tss_of = load_tss()
    orac_of = common.load_orac()
    dozen_of = common.load_daily_dozen()
    eserc_of = load_esercizio()

    # ---- Cronometer: dove il cibo e' stato pesato davvero, la ricostruzione esce --
    # Un giorno PIENO (>=3 pasti, >=1500 kcal) si sostituisce per intero. Un giorno
    # PARZIALE sostituisce solo le fasce che Cronometer copre — il pranzo vero al
    # posto del pranzo inventato — e lascia in piedi il resto della ricostruzione,
    # perche' un solo pasto registrato non e' la prova che il resto non sia stato
    # mangiato: sono 164 giorni su 265, e presi per giornate intere farebbero sparire
    # 1.618 kcal mediane di cene vere.
    cron = {}
    if CRONOMETER.exists():
        import json as _json
        cron = _json.loads(CRONOMETER.read_text(encoding="utf-8"))
    cron_full = {d for d, v in cron.items() if v.get("full")}
    # la scomposizione dei grassi: solo giorni pieni, cioe' solo dove e' misurata
    fat_split = {d: v["fat_split"] for d, v in cron.items() if v.get("fat_split")}
    cron_slots = {d: set(v.get("slots") or ()) for d, v in cron.items()
                  if not v.get("full")}

    # dettaglio per il popup: per giorno, i pasti con dentro gli alimenti veri
    detail = defaultdict(lambda: defaultdict(list))
    # I nutrienti PER PASTO, non solo per giorno (ordine #22): «una roba tipo
    # chronometer che ci ha la colazione con le statistiche totali della colazione».
    # Non si possono riderivare a valle dalle voci gia' emesse: quelle di Cronometer
    # — 2.442 su 11.234 — non portano ne' food_id ne' quantita' numerica, solo una
    # stringa gia' formattata. Quindi si accumulano qui, dove i numeri ci sono.
    meal_nut = defaultdict(lambda: defaultdict(lambda: {n: 0.0 for n in common.NUTRIENTS}))
    per_day = defaultdict(lambda: {n: 0.0 for n in common.NUTRIENTS})
    plants_of = defaultdict(set)
    kcal_src = defaultdict(lambda: defaultdict(float))
    upf_kcal = defaultdict(float)
    src_kcal = defaultdict(lambda: defaultdict(float))
    ferm_days = set()
    tally = defaultdict(lambda: defaultdict(float))
    items = defaultdict(int)
    unknown = set()
    orac_day = defaultdict(float)        # µmol TE del giorno
    orac_kcal = defaultdict(float)       # kcal che vengono da alimenti CON un valore ORAC
    dd_day = defaultdict(lambda: defaultdict(float))   # porzioni per casella
    suppl_day = defaultdict(int)
    senza_orac = defaultdict(float)      # kcal per alimento scoperto, per il rapporto

    for r in rows:
        d = r["date"]
        # la riga cade se Cronometer copre tutto il giorno, o copre la sua fascia
        if d in cron_full or (r.get("meal") or "") in cron_slots.get(d, ()):
            continue
        f = foods.get(r["food_id"])
        if f is None:
            unknown.add(r["food_id"])
            continue
        qty = float(r["qty"])
        pasto = r.get("meal") or "non_specificato"
        for n in common.NUTRIENTS:
            c = f["per_unit"][n] * qty
            per_day[d][n] += c
            meal_nut[d][pasto][n] += c
        kcal = f["per_unit"]["kcal"] * qty
        kcal_src[d]["assumed" if r.get("source") == "assunto" else "observed"] += kcal
        items[d] += 1
        detail[d][pasto].append({
            "n": f["name"],
            # id e quantita' NUMERICA dell'alimento. Prima usciva solo la stringa
            # gia' formattata ("150 g"), che basta a disegnare un pasto ma non a
            # rimetterci le mani: il diario di /vita deve saper risalire dalla riga
            # sullo schermo alla riga di food_log.csv da correggere, e "1.2×" non e'
            # un numero ne' "Pane integrale" e' un id. La stringa non si emette
            # piu': la pagina la ricompone da qui e dall'unita' del catalogo, che
            # ora e' inlineata comunque — un dato solo invece di due che divergono.
            "f": r["food_id"],
            "qn": round(qty, 4),
            "kcal": round(kcal),
            "a": 1 if r.get("source") == "assunto" else 0,   # assunto, non osservato
            "r": r.get("recipe", ""),                        # da quale ricetta viene
            "ri": r.get("recipe_id", ""),                    # ...e con quale id, per poterla togliere
        })
        # ORIGINE: una torta vera, cioe' ogni caloria in una fetta sola.
        #
        # Fino al 2026-08-13 queste erano etichette sovrapposte — il latte contava sia
        # latticino sia animale, il cornetto sia vegetale sia ultra-processato — e la
        # somma faceva 128 %. Sovrapposte erano difendibili ma illeggibili: nessuno
        # guarda quattro percentuali senza sommarle con l'occhio, e quella somma non
        # voleva dire niente. Adesso l'origine e' una PARTIZIONE con precedenza, e le
        # quattro quote fanno 100.
        #
        # La precedenza risolve i casi doppi nell'unico modo che non perde calorie:
        #   latticini PRIMA di vegetale, ma solo se non ha una specie — cosi' il latte
        #     di soia va fra i vegetali, dov'e' giusto che stia;
        #   proteine (carne, pesce, uova) prima di vegetale — un ragu' ha il pomodoro
        #     dentro, ma e' un piatto di carne e sta fra gli animali;
        #   vegetale per tutto quello che una specie ce l'ha;
        #   altro per il resto: burro, miele, whey, cappuccino. Deve restare piccolo:
        #     se cresce, vuol dire che a foods.csv mancano dei `plant`.
        if f["group"] == "latticini" and not f["plant"]:
            src_kcal[d]["dairy"] += kcal
        elif f["group"] == "proteine":
            src_kcal[d]["animal"] += kcal
        elif f["plant"]:
            src_kcal[d]["plant"] += kcal
        else:
            src_kcal[d]["other"] += kcal
        if f["plant"]:
            plants_of[d].add(f["plant"])
        if f["fermented"]:
            ferm_days.add(d)
        if f["upf"]:
            upf_kcal[d] += kcal
        for key, (_lab, ids) in TALLY.items():
            if r["food_id"] in ids:
                tally[d][key] += qty / ids[r["food_id"]]

        # ---- ORAC e Daily Dozen ragionano in GRAMMI, il diario in pezzi ------
        # `grammi_pezzo` esiste solo per le voci a unita' (una banana = 120 g) ed e'
        # ricavato dal catalogo stesso, kcal del pezzo su kcal per 100 g dell'USDA.
        # Dove manca, l'alimento resta FUORI da tutti e due i conti invece di valere
        # un grammo: un pezzo di pizza senza peso non e' mezzo grammo di pizza.
        grammi = qty * f["grammi_pezzo"] if f["unit"] == "unit" else (
            qty if f["unit"] in ("g", "ml") else 0.0)
        if grammi:
            v = orac_of.get(r["food_id"])
            if v is not None:
                orac_day[d] += v[0] * grammi / 100.0
                orac_kcal[d] += kcal
            elif kcal:
                senza_orac[r["food_id"]] += kcal
            for cat, mappa in dozen_of.items():
                porz = mappa.get(r["food_id"])
                if porz:
                    dd_day[d][cat] += grammi / porz
        if f["group"] == "integratori" and not f["per_unit"]["kcal"]:
            # Un integratore vero e proprio, cioe' una voce del gruppo che non porta
            # calorie: whey, barrette e tortini stanno nello stesso gruppo ma sono
            # cibo, e contarli qui direbbe che Michele prende sei integratori al
            # giorno. La discriminante e' che di un integratore vero non si sa nulla:
            # zero kcal perche' l'etichetta non c'e'.
            suppl_day[d] += 1

    if unknown:
        print(f"  ! alimenti sconosciuti, ignorati: {sorted(unknown)}", file=sys.stderr)

    # ---- e adesso entra Cronometer, al posto di quello che si e' appena tolto ----
    for d, v in cron.items():
        full = v.get("full")
        src = v["nutrients"] if full else v["partial_nutrients"]
        if not src.get("kcal"):
            continue
        for n in common.NUTRIENTS:
            per_day[d][n] = (0.0 if full else per_day[d][n]) + float(src.get(n) or 0.0)
        kcal = float(src["kcal"])
        if full:
            kcal_src[d]["observed"] = kcal
            kcal_src[d]["assumed"] = 0.0
            items[d] = v.get("n_items") or 0
            plants_of[d] = set(v.get("plants") or ())
            for q in ("plant", "dairy", "animal", "other"):
                src_kcal[d][q] = float((v.get("shares") or {}).get(q) or 0.0)
            upf_kcal[d] = float((v.get("shares") or {}).get("upf") or 0.0)
            detail[d] = {m: list(it) for m, it in (v.get("meals") or {}).items()}
            # Il giorno pieno di Cronometer SOSTITUISCE la ricostruzione, quindi i
            # totali per pasto si sostituiscono anche loro: sommarli lascerebbe
            # dentro i pasti ipotizzati che quel giorno non esistono piu'.
            meal_nut[d] = defaultdict(lambda: {n: 0.0 for n in common.NUTRIENTS})
            for m, vals in (v.get("meal_nut") or {}).items():
                meal_nut[d][m] = {n: float(vals.get(n) or 0.0) for n in common.NUTRIENTS}
        else:
            # parziale: le fasce vere si sommano a quello che resta della ricostruzione,
            # e le quote/specie si accumulano invece di azzerare quelle rimaste in piedi
            kcal_src[d]["observed"] += kcal
            items[d] += v.get("n_items") or 0
            plants_of[d] |= set(v.get("plants") or ())
            frac = kcal / (v["nutrients"]["kcal"] or kcal)   # quota del giorno coperta
            for q in ("plant", "dairy", "animal", "other"):
                src_kcal[d][q] += float((v.get("shares") or {}).get(q) or 0.0) * frac
            upf_kcal[d] += float((v.get("shares") or {}).get("upf") or 0.0) * frac
            for m, it in (v.get("meals") or {}).items():
                if m in (v.get("slots") or ()) or m == "in bici":
                    detail[d][m] = list(it)
                    # solo le fasce che Cronometer sostituisce davvero: le altre
                    # restano quelle della ricostruzione, totali compresi
                    vals = (v.get("meal_nut") or {}).get(m)
                    if vals is not None:
                        meal_nut[d][m] = {n: float(vals.get(n) or 0.0) for n in common.NUTRIENTS}
        if v.get("fermented"):
            ferm_days.add(d)

    if cron:
        n_full = len(cron_full)
        print(f"  Cronometer: {len(cron)} giorni misurati — {n_full} interi, "
              f"{len(cron) - n_full} parziali (solo le fasce registrate)")

    # Prima del primo integratore registrato la colonna e' VUOTA, non zero. Fino al
    # 03/09/2026 il registro non aveva nessun modo di annotare un integratore: uno
    # zero su quei giorni direbbe «non ne ha preso nessuno», che e' una cosa che
    # nessuno sa. Senza questa riga il riquadro nasceva con due anni di zeri piatti e
    # un solo picco in fondo — un grafico che dice del catalogo, non della persona.
    primo_suppl = min(suppl_day) if suppl_day else None

    days = sorted(per_day)
    if not days:
        raise SystemExit("nessun giorno da elaborare.")
    d0, d1 = date.fromisoformat(days[0]), date.fromisoformat(days[-1])

    out = []
    cur = d0
    while cur <= d1:
        k = cur.isoformat()
        t = per_day.get(k)
        if t is None:
            cur += timedelta(days=1)
            continue

        def pct(n):
            target = rda.get(n)
            return min(100.0, 100.0 * t[n] / target) if target else None

        vit = [pct(n) for n in VITAMINS if rda.get(n)]
        mine = [pct(n) for n in MINERALS if rda.get(n)]
        vit_index = sum(vit) / len(vit) if vit else 0.0
        min_index = sum(mine) / len(mine) if mine else 0.0

        # diversita' vegetale sulla finestra scorrevole di 7 giorni
        win = {p for j in range(7)
               for p in plants_of.get((cur - timedelta(days=j)).isoformat(), ())}
        fiber7 = [per_day[(cur - timedelta(days=j)).isoformat()]["fiber_g"]
                  for j in range(7)
                  if (cur - timedelta(days=j)).isoformat() in per_day]
        ferm7 = sum(1 for j in range(7)
                    if (cur - timedelta(days=j)).isoformat() in ferm_days)

        # --- il fabbisogno di carboidrati, e quanto ci si puo' credere ---------
        # VERIFICATO il 18/08/2026 (Michele: "verifica anche carbo stimati dal carico
        # se precisi"), confrontando la mediana del modello con le fasce pubblicate
        # (Burke et al. 2011 / linee guida ACSM), raggruppando gli 788 giorni per ORE
        # DI MOVIMENTO vere invece che per TSS:
        #
        #   ore/giorno      n     modello      letteratura   esito
        #   poco o niente   18    3,0 g/kg      3-5 g/kg     dentro, al bordo basso
        #   circa un'ora   100    5,0 g/kg      5-7 g/kg     dentro, al bordo basso
        #   una-tre ore    508    6,2 g/kg      6-10 g/kg    dentro, al bordo basso
        #   oltre tre ore  162   10,0 g/kg      8-12 g/kg    dentro, ma TAPPATO
        #
        # Sta dentro in tutte e quattro le fasce, e sta sempre sul BORDO BASSO. Il
        # che vuol dire che lo "scarto carboidrati" della pagina, se sbaglia, sbaglia
        # per difetto: il buco vero e' quello mostrato o piu' grande, mai piu' piccolo.
        #
        # Il tappo passa da 10 a 12 g/kg. Dieci non veniva da nessuna parte — la fascia
        # per chi si muove oltre le tre ore arriva a 12 — e mordeva su 101 giorni su
        # 788 (13 %): appiattiva proprio le giornate piu' grosse, cioe' quelle in cui
        # la domanda "quanto mi e' mancato" ha una risposta interessante. Il pavimento
        # resta 3: e' il fondo della fascia "poco o niente", ed e' giusto che un giorno
        # fermo non chieda zero carboidrati.
        tss = tss_of.get(k, 0.0)
        g_per_kg = max(3.0, min(12.0, 3.0 + 0.03 * tss))
        carb_target = weight * g_per_kg

        kcal_tot = t["kcal"] or 1.0
        upf_share = min(0.5, upf_kcal.get(k, 0.0) / kcal_tot)
        micro = 100.0 * (
            MICROBIOME_W["plants"] * min(1.0, len(win) / PLANT_TARGET) +
            MICROBIOME_W["fiber"] * min(1.0, (sum(fiber7) / len(fiber7)) / FIBER_TARGET
                                        if fiber7 else 0.0) +
            MICROBIOME_W["fermented"] * min(1.0, ferm7 / 7.0) +
            MICROBIOME_W["unprocessed"] * (1.0 - upf_share / 0.5)
        )

        out.append({
            "date": k,
            "kcal": round(t["kcal"]), "protein_g": round(t["protein_g"], 1),
            "carb_g": round(t["carb_g"], 1), "sugar_g": round(t["sugar_g"], 1),
            "fiber_g": round(t["fiber_g"], 1), "fat_g": round(t["fat_g"], 1),
            "satfat_g": round(t["satfat_g"], 1),
            "magnesium_mg": round(t["magnesium_mg"]),
            "potassium_mg": round(t["potassium_mg"]),
            "sodium_mg": round(t["sodium_mg"]),
            "vit_index": round(vit_index, 1), "min_index": round(min_index, 1),
            "plants_day": len(plants_of.get(k, ())), "plants_7d": len(win),
            "tss": round(tss), "carb_target_g": round(carb_target),
            "carb_gap_g": round(t["carb_g"] - carb_target),
            "microbiome": round(micro, 1),
            "kcal_observed": round(kcal_src[k]["observed"]),
            "kcal_assumed": round(kcal_src[k]["assumed"]),
            "n_items": items[k],
            **{"pct_" + q: round(100.0 * src_kcal[k].get(q, 0.0) / (t["kcal"] or 1), 1)
               for q in ("plant", "dairy", "animal", "other")},
            "pct_upf": round(100.0 * upf_kcal.get(k, 0.0) / (t["kcal"] or 1), 1),
            **macro_split(t),
            # DI CHE GRASSO, su OGNI giorno e non solo sui pochi pesati.
            # Dove Cronometer ha pesato la giornata la misura vince; altrove si usa la
            # ricostruzione dai profili di acidi grassi del catalogo. `fat_split_src`
            # dice sempre quale dei due si sta guardando: sono due cose diverse e la
            # pagina non deve poterle confondere.
            **{c: round(fat_split[k][sv], 2) if k in fat_split
                  else (round(t[cat], 2) if t.get(cat) else "")
               for c, sv, cat in (("mono_g", "mono_g", "monounsat_g"),
                                  ("poly_g", "poly_g", "polyunsat_g"),
                                  ("trans_g", "trans_g", "transfat_g"))},
            # 1 = pesato da Cronometer, 0 = ricostruito dal catalogo. NUMERICO e non
            # una parola: la pagina carica queste colonne come serie di numeri, e una
            # stringa qui dentro fa cadere il build con un ValueError che sembra
            # tutt'altro (successo il 17/08/2026, costato mezz'ora).
            "fat_split_mis": (1 if k in fat_split else 0) if (k in fat_split or t.get("fat_g")) else "",
            # ORAC e Daily Dozen: VUOTI, non zero, dove il giorno lo ha scritto
            # Cronometer per intero. Le sue voci non portano food_id — solo una
            # stringa gia' formattata — quindi non c'e' niente da cercare in
            # orac.csv, e uno zero li' vorrebbe dire «quel giorno non ha mangiato
            # niente di colorato» invece di «da qui non si vede». E' la stessa
            # regola dei buchi nei grafici: un buco resta un buco.
            "orac": ("" if k in cron_full else round(orac_day.get(k, 0.0))),
            "orac_cov_pct": ("" if k in cron_full else
                             round(100.0 * orac_kcal.get(k, 0.0) / (t["kcal"] or 1), 1)),
            # L'ESERCIZIO fa eccezione e non si svuota mai: non viene dal diario ma
            # da intervals.icu, quindi su un giorno di Cronometer si sa lo stesso.
            # Una casella senza NESSUN alimento mappato resta VUOTA per sempre, e
            # non a zero: `semi_di_lino` non ha una voce in foods.csv, quindi «zero
            # porzioni» li' vorrebbe dire «non ne ha mangiati», che non e' quello
            # che si sa — quello che si sa e' che il catalogo non li conosce.
            **{"dd_" + c: (round(eserc_of.get(k, 0.0), 2) if c == "esercizio"
                           else "" if (c not in dozen_of or k in cron_full)
                           else round(dd_day[k].get(c, 0.0), 2))
               for c, _ in common.DAILY_DOZEN},
            "suppl_n": ("" if (k in cron_full or primo_suppl is None or k < primo_suppl)
                        else suppl_day.get(k, 0)),
            **{"cnt_" + key: round(tally[k].get(key, 0.0), 2) for key in TALLY},
        })
        cur += timedelta(days=1)

    n = len(out)
    avg = lambda key: sum(r[key] for r in out) / n
    print(f"{n} giorni, {d0} → {d1}")
    print(f"  kcal medie      {avg('kcal'):7.0f}   "
          f"(osservate {100 * avg('kcal_observed') / max(1, avg('kcal')):.0f} %, "
          f"ricostruite {100 * avg('kcal_assumed') / max(1, avg('kcal')):.0f} %)")
    print(f"  fibra           {avg('fiber_g'):7.1f} g")
    print(f"  carboidrati     {avg('carb_g'):7.1f} g  contro {avg('carb_target_g'):.0f} g stimati dal TSS")
    print(f"  zuccheri        {avg('sugar_g'):7.1f} g")
    print(f"  magnesio        {avg('magnesium_mg'):7.0f} mg  (fabbisogno {rda['magnesium_mg']})")
    print(f"  potassio        {avg('potassium_mg'):7.0f} mg  (fabbisogno {rda['potassium_mg']})")
    print(f"  indice vitamine {avg('vit_index'):7.1f} %")
    print(f"  indice minerali {avg('min_index'):7.1f} %")
    print(f"  piante / 7 gg   {avg('plants_7d'):7.1f}   (obiettivo {PLANT_TARGET})")
    print(f"  microbiota      {avg('microbiome'):7.1f} / 100")
    for q, lab in (("pct_plant", "vegetale"), ("pct_dairy", "latticini"),
                   ("pct_upf", "ultra-processato"), ("pct_animal", "animale")):
        print(f"  quota {lab:<18} {avg(q):5.1f} % delle kcal")
    # ---- ORAC e Daily Dozen: quanto se ne vede davvero -----------------------
    con_orac = [r for r in out if r["orac"] != "" and r["kcal"]]
    if con_orac:
        cov = sum(r["orac_cov_pct"] for r in con_orac) / len(con_orac)
        print(f"  ORAC medio      {sum(r['orac'] for r in con_orac) / len(con_orac):7.0f} "
              f"µmol TE  (su {len(con_orac)} giorni; copre il {cov:.0f} % delle kcal, "
              f"{len(orac_of)} alimenti a listino)")
        peggiori = sorted(senza_orac.items(), key=lambda x: -x[1])[:5]
        if peggiori:
            print("    scoperti che pesano di piu': " +
                  ", ".join(f"{f} ({k / 1000:.0f}k kcal)" for f, k in peggiori))
    ultimi = [r for r in out[-7:] if r["dd_fagioli"] != ""]
    if ultimi:
        print("  Daily Dozen, ultimi 7 giorni (porzioni medie / prescritte):")
        for c, target in common.DAILY_DOZEN:
            vals = [r["dd_" + c] for r in ultimi if r["dd_" + c] != ""]
            if not vals:
                continue
            m = sum(vals) / len(vals)
            print(f"    {common.DAILY_DOZEN_IT[c]:<22} {m:5.2f} / {target}"
                  f"   {'OK' if m >= target else ''}")
    con_suppl = sum(1 for r in out if r["suppl_n"] not in ("", 0))
    print(f"  integratori: {con_suppl} giorni con almeno una presa registrata")

    print("  conteggi (totale sul periodo):")
    for key, (lab, _ids) in TALLY.items():
        print(f"    {sum(r['cnt_' + key] for r in out):8.0f}  {lab}")

    if args.check:
        print("\n(--check: niente scritto)")
        return
    common.write_csv(OUT, FIELDS, out)
    print(f"\n-> {OUT}")
    if args.export:
        from pathlib import Path
        p = Path(args.export)
        p.parent.mkdir(parents=True, exist_ok=True)
        common.write_csv(p, FIELDS, out)
        print(f"-> {p}  (solo aggregati)")

    if args.export_days:
        # Il popup di /vita apre la giornata: qui dentro ci vanno i pasti veri con
        # gli alimenti, e le percentuali di fabbisogno di ogni nutriente. E' piu'
        # di quanto esca nel CSV — l'utente l'ha chiesto esplicitamente il
        # 2026-08-10 ("food injected ingredients, macro micro and so on").
        import json
        from pathlib import Path
        # I giorni interamente ricostruiti sono la stessa colazione ripetuta
        # centinaia di volte: esportarne il dettaglio faceva 949 KB di ripetizione.
        # Di quelli esce solo l'elenco delle ricette usate, e la pagina lo ridistende
        # dal template qui sotto. I giorni con del cibo VERO escono per intero.
        recipes = common.load_recipes()
        used = sorted({it["r"] for k in detail for m in detail[k]
                       for it in detail[k][m] if it["r"]})
        template = {}
        for rid, rec in recipes.items():
            if rec["name"] not in used:
                continue
            template[rec["name"]] = [
                {"n": foods[i["food_id"]]["name"],
                 "q": f"{i['qty'] / rec['servings']:g} {foods[i['food_id']]['unit']}",
                 "kcal": round(foods[i["food_id"]]["per_unit"]["kcal"] * i["qty"]
                               / rec["servings"])}
                for i in rec["ingredients"] if i["food_id"] in foods]

        days = {"_t": template}

        # Inventario delle ultime due settimane per il popup delle medie. Le righe
        # sono gia' espanse dalle ricette: lo stesso food_id viene quindi davvero
        # sommato anche quando arriva da pasti/ricette diversi. Quantita' e numero
        # di occasioni osservate restano separati dalle ricostruzioni, per non
        # presentare una stima automatica come qualcosa che Michele ha raccontato.
        recent_start = d1 - timedelta(days=13)
        recent = {}
        for item in rows:
            item_day = date.fromisoformat(item["date"])
            if not recent_start <= item_day <= d1:
                continue
            # stesso taglio fatto sopra: se Cronometer copre il giorno o la fascia,
            # quella riga della ricostruzione non conta piu' nei totali e non deve
            # comparire nemmeno nell'inventario di quindici giorni
            if (item["date"] in cron_full
                    or (item.get("meal") or "") in cron_slots.get(item["date"], ())):
                continue
            food = foods.get(item["food_id"])
            if food is None:
                continue
            bucket = "assumed" if item.get("source") == "assunto" else "observed"
            rec = recent.setdefault(item["food_id"], {
                "id": item["food_id"], "name": food["name"], "unit": food["unit"],
                "qty_observed": 0.0, "qty_assumed": 0.0,
                "occ_observed": set(), "occ_assumed": set(),
            })
            rec[f"qty_{bucket}"] += float(item["qty"])
            rec[f"occ_{bucket}"].add((item["date"], item.get("meal") or ""))
        days["_14foods"] = [{
            "id": rec["id"], "name": rec["name"], "unit": rec["unit"],
            "qty_observed": round(rec["qty_observed"], 2),
            "qty_assumed": round(rec["qty_assumed"], 2),
            "occ_observed": len(rec["occ_observed"]),
            "occ_assumed": len(rec["occ_assumed"]),
        } for rec in sorted(recent.values(),
                            key=lambda x: (-(len(x["occ_observed"]) +
                                             len(x["occ_assumed"])), x["name"]))]
        profiles = {}
        for r in out:
            k = r["date"]
            t = per_day[k]
            if not r["kcal_observed"]:
                # Tutto ricostruito. Questi giorni sono poche forme ripetute
                # centinaia di volte (colazione sola, colazione+toast,
                # colazione+dahl, tutte e tre): se ne emette una copia per forma e
                # la data ci punta. Da 497 KB a una manciata.
                # `piatti` e' `recipes` con dentro di che rimetterci le mani: il
                # pasto e l'id, non il solo nome. Un giorno tutto ricostruito non ha
                # `meals`, quindi la dashboard non aveva NIENTE da cliccare — e sono
                # la maggioranza dei giorni. Con questo, ogni piatto ipotizzato ha
                # la sua riga e si puo' smentire.
                #
                # Non rompe la deduplica dei profili: il pasto e l'id fanno parte
                # della forma tanto quanto il nome, quindi due giorni identici
                # restano identici e continuano a condividere un profilo solo.
                # Le ricette entrano una volta sola, non una per ingrediente: `f` e'
                # la stessa chiave che il diario usa per scriverle, `recipe:<id>`.
                # Gli assunti sciolti (yogurt, mela, gallette della merenda) entrano
                # per se stessi, perche' li' negare la mela non dice niente sullo
                # yogurt.
                # `q` e' la quantita' da proporre quando si corregge: per una
                # ricetta e' 1 porzione (fill_defaults le scrive sempre cosi'), per
                # un assunto sciolto e' la quantita' ipotizzata. Senza, il campo si
                # aprirebbe su un numero finto.
                piatti = {}
                for m in detail[k]:
                    for it in detail[k][m]:
                        f = "recipe:" + it["ri"] if it.get("ri") else it.get("f")
                        if not f:
                            continue
                        piatti.setdefault((m, f), (
                            it.get("r") if it.get("ri") else (it.get("n") or f),
                            1 if it.get("ri") else it.get("qn"),
                        ))
                prof = {
                    "recipes": sorted({it["r"] for m in detail[k]
                                       for it in detail[k][m] if it["r"]}),
                    "piatti": [{"m": m, "f": f, "n": nome, "q": q}
                               for (m, f), (nome, q) in sorted(piatti.items())],
                    "tot": {n: arrotonda(t[n]) for n in common.NUTRIENTS},
                    "pct": {n: round(100.0 * t[n] / rda[n]) for n in common.NUTRIENTS
                            if rda.get(n)},
                    "cap": {n: round(100.0 * t[n] / v)
                            for n, v in profile["limits_abs"].items() if v},
                    "obs": 0, "asm": r["kcal_assumed"],
                }
                sig = json.dumps(prof, sort_keys=True, ensure_ascii=False)
                pid = profiles.setdefault(sig, f"p{len(profiles)}")
                days[k] = pid
                continue
            days[k] = {
                "meals": {m: v for m, v in detail[k].items()},
                "tot": {n: arrotonda(t[n]) for n in common.NUTRIENTS},
                "pct": {n: round(100.0 * t[n] / rda[n]) for n in common.NUTRIENTS
                        if rda.get(n)},
                "cap": {n: round(100.0 * t[n] / v)
                        for n, v in profile["limits_abs"].items() if v},
                # I nutrienti PER PASTO (ordine #22). Stanno accanto a `meals` invece
                # che dentro, cosi' la forma di `meals` — una lista di voci — non
                # cambia e la pagina che la disegna non se ne accorge.
                #
                # Sono un ARRAY nell'ordine di MEAL_NUTRIENTS, dichiarato una volta
                # sola in `_mn`, non un oggetto con le chiavi per esteso. Con le
                # chiavi days.json passava da 1,6 a 3,3 MB — raddoppiato — e quel
                # file la pagina se lo inlina tutto: erano i NOMI a pesare, ripetuti
                # duemilaottocento volte, non i numeri.
                #
                # Le percentuali di fabbisogno NON si emettono: si ricavano dividendo
                # per `foodProfile.rda`, che la pagina ha gia'. Emetterle sarebbe un
                # secondo elenco della stessa cosa — la quarta regola della repo — e
                # sarebbe il secondo a restare indietro.
                "mn": {m: [arrotonda(mn[n]) for n in MEAL_NUTRIENTS]
                       for m, mn in meal_nut[k].items() if mn["kcal"] > 0},
                "obs": r["kcal_observed"], "asm": r["kcal_assumed"],
            }
        # le forme dedotte tornano indietro come oggetti veri, indicizzati per id
        days["_p"] = {pid: json.loads(sig) for sig, pid in profiles.items()}
        # l'ordine degli array `mn`, scritto una volta sola: chi legge un pasto sa
        # cosa sono i suoi sedici numeri senza che nessuno debba ricordarselo
        days["_mn"] = list(MEAL_NUTRIENTS)
        p = Path(args.export_days)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(days, ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")
        print(f"-> {p}  ({len(days)} giorni, {p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
