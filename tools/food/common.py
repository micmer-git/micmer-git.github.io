"""Percorsi condivisi, database alimenti/ricette e fabbisogni. Solo stdlib.

Questa cartella e' la pipeline dell'alimentazione, portata dentro il repo del sito
il 2026-08-11: prima viveva in ~/health-log, che ha il remote su un repo che non
esiste e quindi non era pubblicabile. Una copia sola, qui, dove il push funziona.
"""
import csv
import json
import os
from pathlib import Path

# la root della pipeline e' questa cartella, non il repo
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DERIVED = DATA / "derived"
DERIVED.mkdir(parents=True, exist_ok=True)

FOODS_CSV = DATA / "foods.csv"
RECIPES_CSV = DATA / "recipes.csv"
FOOD_LOG_CSV = DATA / "food_log.csv"
ACTIVITIES_CSV = DATA / "activities.csv"
# Le attivita' che Intervals non ha, ricostruite dall'export Strava: vedi
# tools/strava_backfill.py. File separato perche' activities.csv lo riscrive
# `build_vita.py --sync-source` a ogni ora.
ACTIVITIES_BACKFILL_CSV = DATA / "activities_backfill.csv"
DAILY_NUTRITION_CSV = DERIVED / "daily_nutrition.csv"
BALANCE_CSV = DERIVED / "energy_balance.csv"

# I nutrienti tracciati, nell'ordine in cui compaiono ovunque.
MACROS = ("kcal", "protein_g", "carb_g", "sugar_g", "fiber_g", "fat_g",
          # DI CHE GRASSO. Dal 17/08/2026 il catalogo li porta tutti e tre e non solo
          # i saturi, quindi il conto si puo' fare su OGNI giorno e non solo sui quattro
          # al mese pesati da Cronometer. Sono RICOSTRUITI da profili di acidi grassi
          # noti (tools/food/profili_grassi.py), non misurati: dove Cronometer c'e', la
          # misura vince, e la serie dichiara quale dei due sta guardando.
          "satfat_g", "monounsat_g", "polyunsat_g", "transfat_g", "omega3_g")
MICROS = ("sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg",
          "zinc_mg", "vitc_mg", "vita_ug", "vitd_ug", "b12_ug", "folate_ug")
NUTRIENTS = MACROS + MICROS

LABELS = {
    "kcal": "Energia", "protein_g": "Proteine", "carb_g": "Carboidrati",
    "sugar_g": "di cui zuccheri", "fiber_g": "Fibre", "fat_g": "Grassi",
    "satfat_g": "di cui saturi", "monounsat_g": "di cui monoinsaturi",
    "polyunsat_g": "di cui polinsaturi", "transfat_g": "di cui trans",
    "omega3_g": "Omega 3 (ALA)",
    "sodium_mg": "Sodio", "potassium_mg": "Potassio", "calcium_mg": "Calcio",
    "iron_mg": "Ferro", "magnesium_mg": "Magnesio", "zinc_mg": "Zinco",
    "vitc_mg": "Vitamina C", "vita_ug": "Vitamina A", "vitd_ug": "Vitamina D",
    "b12_ug": "Vitamina B12", "folate_ug": "Folati",
}
UNITS = {n: ("kcal" if n == "kcal" else n.rsplit("_", 1)[1].replace("ug", "µg"))
         for n in NUTRIENTS}


def backfill_load_by_day():
    """{giorno: carico ricostruito} da activities_backfill.csv, {} se non c'e'.

    Sta qui, in comune, perche' la usano due superfici: build_vita.py per la CTL dei
    grafici e metabolismo.py per la componente "forma" del momento metabolico. Con due
    copie, il 2022 esisterebbe in un posto e non nell'altro — che e' esattamente il
    modo in cui questa repo ha gia' divergito una volta (vedi build_food.py).
    """
    out = {}
    if not ACTIVITIES_BACKFILL_CSV.exists():
        return out
    with ACTIVITIES_BACKFILL_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            d = (row.get("date") or "")[:10]
            if not d:
                continue
            try:
                out[d] = out.get(d, 0.0) + float(row.get("training_load") or 0)
            except ValueError:
                continue
    return out


def recompute_ctl_atl(loads, ctl0=0.0, atl0=0.0, tau_ctl=42.0, tau_atl=7.0):
    """Media esponenziale di Intervals su una sequenza di carichi giornalieri.

    Che le costanti siano 42 e 7 non e' un'ipotesi: rifacendo i conti dal `ctlLoad`
    di Intervals si riottengono i loro `ctl` con un errore assoluto mediano di 0,03
    su una scala attorno a 95, massimo 1,0 su 4.156 giorni. E' la stessa formula.
    """
    ctl, atl, c, a = [], [], float(ctl0), float(atl0)
    for v in loads:
        v = float(v or 0)
        c += (v - c) / tau_ctl
        a += (v - a) / tau_atl
        ctl.append(c)
        atl.append(a)
    return ctl, atl


def load_env():
    """Legge .env nella root della repo (KEY=VALUE) e lo fonde nell'ambiente."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return os.environ


def load_profile():
    """profile.json + i fabbisogni derivati (proteine dal peso, tetti dalle kcal)."""
    profile = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    ref = profile.get("reference_kcal", 2600)
    rda = dict(profile.get("rda", {}))
    rda["protein_g"] = round(profile["weight_kg"] * profile.get("protein_g_per_kg", 1.6), 1)
    limits = profile.get("limits", {})
    profile["rda"] = rda
    # I tetti percentuali diventano grammi sulla dieta di riferimento.
    profile["limits_abs"] = {
        "sodium_mg": limits.get("sodium_mg", 2000),
        "satfat_g": round(ref * limits.get("satfat_pct_kcal", 10) / 100 / 9, 1),
        "sugar_g": round(ref * limits.get("sugar_pct_kcal", 10) / 100 / 4, 1),
    }
    return profile


def load_foods():
    """foods.csv -> {id: {...}} con i nutrienti normalizzati a 1 unita' di misura."""
    foods = {}
    seen = set()
    with FOODS_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            # Due id uguali: il dizionario terrebbe l'ultimo e l'altro sparirebbe
            # senza un rumore. E' successo il 2026-08-11, con due agenti che
            # leggevano mesi diversi e hanno definito `arancia` e `broccoli`
            # tutti e due. Qui si ferma tutto, che e' l'unico modo di accorgersene.
            if row["id"] in seen:
                raise SystemExit(
                    f"foods.csv: id duplicato '{row['id']}'. Due definizioni dello "
                    f"stesso alimento: tienine una sola, o una delle due sparisce "
                    f"in silenzio dai conti.")
            seen.add(row["id"])
            ref = float(row["ref_qty"])
            foods[row["id"]] = {
                "id": row["id"],
                "name": row["name_it"],
                "group": row.get("group", ""),
                "unit": row["unit"],
                "confidence": row.get("confidence", ""),
                "note": row.get("note", ""),
                # specie vegetale (per il conteggio "quante piante a settimana"),
                # fermentato e ultra-processato: servono all'indice microbiota in
                # build_nutrition_series.py. Vuoti sui file vecchi, e va bene.
                "plant": (row.get("plant") or "").strip(),
                "fermented": (row.get("fermented") or "0").strip() == "1",
                "upf": (row.get("upf") or "0").strip() == "1",
                # quanto pesa UN pezzo, per le voci che il catalogo tiene a unita'.
                # 0 = non si sa, e allora l'alimento resta fuori dai conti che
                # ragionano in grammi (ORAC, Daily Dozen) invece di valere un grammo.
                "grammi_pezzo": float(row.get("grammi_pezzo") or 0),
                "per_unit": {n: float(row.get(n) or 0) / ref for n in NUTRIENTS},
            }
    return foods


def load_recipes():
    """recipes.csv -> {id: {name, servings, ingredients: [{food_id, qty, note}]}}.

    Le ricette senza food_id sono segnaposto: l'utente deve ancora dare gli
    ingredienti. Restano nel database cosi' l'app puo' mostrarle come da fare.
    """
    recipes = {}
    if not RECIPES_CSV.exists():
        return recipes
    with RECIPES_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rid = row["recipe_id"]
            r = recipes.setdefault(rid, {
                "id": rid, "name": row["name"],
                "servings": float(row.get("servings") or 1),
                "ingredients": [], "todo": "",
            })
            if row.get("food_id"):
                r["ingredients"].append({
                    "food_id": row["food_id"], "qty": float(row["qty"]),
                    "note": row.get("note", ""),
                })
            elif row.get("note"):
                r["todo"] = row["note"]
    return recipes


PHOTO_BATCHES = DATA / "photo_batches"

# I due file di riferimento nati il 27-28/08/2026 e rimasti INERTI fino al
# 03/09/2026 (ordini MC #31 e #32). Sono tabelle di appartenenza e di valori, non
# di consumo: da soli non dicono niente, e servono a build_nutrition_series.py per
# tirar fuori due serie giornaliere. Il perche' di ogni numero sta in RIFERIMENTI.md.
ORAC_CSV = DATA / "orac.csv"
DAILY_DOZEN_CSV = DATA / "daily_dozen.csv"

# Le dodici caselle nell'ordine di Greger, e quante porzioni al giorno ne chiede.
# VERIFICATE sulla fonte (https://nutritionfacts.org/daily-dozen/) il 03/09/2026:
# fagioli 3, bacche 1, altra frutta 3, crucifere 1, foglie verdi 2, altre verdure 2,
# lino 1, frutta secca e semi 1, erbe e spezie 1, cereali integrali 3, bevande 5
# (60 oz, cioe' cinque bicchieri da 12 oz), esercizio 1.
#
# L'ordine sta QUI e in nessun altro posto: la pagina disegna dodici righe e se le
# leggesse da una sua lista, quella lista resterebbe indietro alla prima modifica.
DAILY_DOZEN = (
    ("fagioli", 3), ("frutti_di_bosco", 1), ("altra_frutta", 3), ("crucifere", 1),
    ("verdure_foglia_verde", 2), ("altre_verdure", 2), ("semi_di_lino", 1),
    ("noci_e_semi", 1), ("erbe_e_spezie", 1), ("cereali_integrali", 3),
    ("bevande", 5), ("esercizio", 1),
)
DAILY_DOZEN_IT = {
    "fagioli": "Fagioli e legumi", "frutti_di_bosco": "Frutti di bosco",
    "altra_frutta": "Altra frutta", "crucifere": "Crucifere",
    "verdure_foglia_verde": "Foglie verdi", "altre_verdure": "Altre verdure",
    "semi_di_lino": "Semi di lino", "noci_e_semi": "Frutta secca e semi",
    "erbe_e_spezie": "Erbe e spezie", "cereali_integrali": "Cereali integrali",
    "bevande": "Bevande", "esercizio": "Esercizio",
}


def _righe_csv_commentato(path):
    """Le righe di un CSV che comincia con un blocco di commenti `#`.

    `orac.csv` e `daily_dozen.csv` portano in testa la loro fonte e le loro
    avvertenze, che e' il motivo per cui si possono leggere senza aprire un altro
    file. csv.DictReader da solo prenderebbe il primo `#` come intestazione.
    """
    if not path.exists():
        return []
    righe = [l for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    return list(csv.DictReader(righe)) if righe else []


def load_orac():
    """orac.csv -> {food_id: (valore µmol TE/100 g, confidence)}.

    ⚠️ Il valore e' SEMPRE per 100 g o 100 ml, anche per gli alimenti che il catalogo
    tiene a unita' (banana, mela, uovo). Chi lo usa deve moltiplicare per i grammi
    veri, non per la quantita' del diario: una banana e' 1 nel diario e ~120 g nel
    piatto, e sbagliare qui fa un errore di due ordini di grandezza in un numero che
    nessuno sa a memoria — cioe' un errore che non si vede.
    """
    out = {}
    for r in _righe_csv_commentato(ORAC_CSV):
        try:
            out[r["food_id"]] = (float(r["orac_umol_te_100g"]),
                                 (r.get("confidence") or "").strip())
        except (TypeError, ValueError):
            continue
    return out


def load_daily_dozen():
    """daily_dozen.csv -> {categoria: {food_id: grammi di UNA porzione}}.

    Un alimento puo' comparire in piu' categorie (cavolo nero e rucola sono insieme
    crucifere e foglie verdi): spunta una casella per ciascuna, mai due volte la
    stessa. Le righe senza food_id sono le caselle scoperte — `semi_di_lino`, che
    nel catalogo non esiste, ed `esercizio`, che non e' un alimento — e restano
    fuori dalla mappa apposta: chi disegna deve poter distinguere «zero porzioni»
    da «questa casella non e' misurabile da qui».
    """
    out = {}
    for r in _righe_csv_commentato(DAILY_DOZEN_CSV):
        fid = (r.get("food_id") or "").strip()
        cat = (r.get("categoria") or "").strip()
        if not fid or not cat:
            continue
        try:
            porz = float(r["porzione_g"])
        except (TypeError, ValueError, KeyError):
            continue
        if porz > 0:
            out.setdefault(cat, {})[fid] = porz
    return out


def load_food_log():
    """Il diario, piu' i lotti letti dagli screenshot.

    `data/photo_batches/*.csv` esiste perche' la lettura delle ~400 schermate di
    Google Photos e' un lavoro parallelo: piu' agenti leggono mesi diversi e ognuno
    scrive il PROPRIO file. Se scrivessero tutti in food_log.csv si sovrascriverebbero
    a vicenda, e il modo in cui se ne accorgerebbe qualcuno sarebbe un diario con
    dei buchi. Stessa identica intestazione, stessa semantica: sono righe osservate.
    """
    rows = []
    with FOOD_LOG_CSV.open(encoding="utf-8", newline="") as fh:
        rows += [row for row in csv.DictReader(fh) if row.get("date")]
    if PHOTO_BATCHES.exists():
        seen = {(r["date"], r["meal"], r["food_id"]) for r in rows}
        for p in sorted(PHOTO_BATCHES.glob("*.csv")):
            with p.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if not row.get("date"):
                        continue
                    k = (row["date"], row.get("meal", ""), row.get("food_id", ""))
                    if k in seen:          # stesso pasto letto due volte: si tiene uno
                        continue
                    seen.add(k)
                    row.setdefault("source", "foto")
                    rows.append(row)
    return rows


def expand_log(rows, recipes):
    """Sostituisce le righe `recipe:<id>` con i loro ingredienti.

    Una porzione di ricetta e' qty=1. qty=0.5 dimezza tutti gli ingredienti.
    """
    out = []
    for row in rows:
        fid = row["food_id"]
        if not fid.startswith("recipe:"):
            out.append(row)
            continue
        rid = fid.split(":", 1)[1]
        recipe = recipes.get(rid)
        if recipe is None or not recipe["ingredients"]:
            out.append({**row, "food_id": f"__ricetta_sconosciuta__{rid}"})
            continue
        portions = float(row["qty"]) / recipe["servings"]
        for ing in recipe["ingredients"]:
            # `recipe_id` oltre al nome: il nome serve a leggere, l'id a rimetterci
            # le mani. Una riga ricostruita si toglie o si corregge per RICETTA
            # intera (non ha senso cancellare le lenticchie e lasciare il curry), e
            # per dirlo a fill_defaults serve l'id con cui l'ha scritta lui.
            out.append({**row, "food_id": ing["food_id"],
                        "qty": ing["qty"] * portions,
                        "recipe": recipe["name"],
                        "recipe_id": rid})
    return out


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
