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
DAILY_NUTRITION_CSV = DERIVED / "daily_nutrition.csv"
BALANCE_CSV = DERIVED / "energy_balance.csv"

# I nutrienti tracciati, nell'ordine in cui compaiono ovunque.
MACROS = ("kcal", "protein_g", "carb_g", "sugar_g", "fiber_g", "fat_g",
          "satfat_g", "omega3_g")
MICROS = ("sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg",
          "zinc_mg", "vitc_mg", "vita_ug", "vitd_ug", "b12_ug", "folate_ug")
NUTRIENTS = MACROS + MICROS

LABELS = {
    "kcal": "Energia", "protein_g": "Proteine", "carb_g": "Carboidrati",
    "sugar_g": "di cui zuccheri", "fiber_g": "Fibre", "fat_g": "Grassi",
    "satfat_g": "di cui saturi", "omega3_g": "Omega 3 (ALA)",
    "sodium_mg": "Sodio", "potassium_mg": "Potassio", "calcium_mg": "Calcio",
    "iron_mg": "Ferro", "magnesium_mg": "Magnesio", "zinc_mg": "Zinco",
    "vitc_mg": "Vitamina C", "vita_ug": "Vitamina A", "vitd_ug": "Vitamina D",
    "b12_ug": "Vitamina B12", "folate_ug": "Folati",
}
UNITS = {n: ("kcal" if n == "kcal" else n.rsplit("_", 1)[1].replace("ug", "µg"))
         for n in NUTRIENTS}


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
            out.append({**row, "food_id": ing["food_id"],
                        "qty": ing["qty"] * portions,
                        "recipe": recipe["name"]})
    return out


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
