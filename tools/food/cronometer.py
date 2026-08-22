#!/usr/bin/env python3
"""
cronometer.py — l'export Cronometer, cioè i giorni in cui il cibo è MISURATO.

Fino al 2026-08-13 la serie dell'alimentazione prima del 2026 era quasi tutta
ricostruita: `food_log.csv` copriva solo il 2026, e per il resto la pagina sommava
gli screenshot di Google Photos e i pasti abituali di `fill_defaults.py`. Poi è
arrivato l'export di Cronometer, che sono **265 giornate davvero pesate e registrate**,
dal 2024-06-04 al 2026-08-06, con una sessantina di nutrienti per giorno.

Non è un miglioramento di dettaglio, è una correzione di rotta: sui 74 giorni con il
diario pieno, la ricostruzione stava sotto di 471 kcal mediane, 37 g di proteine,
106 g di carboidrati, 13 g di fibra e 498 mg di sodio. Sistematicamente bassa, non
rumorosa. Dove Cronometer c'è, Cronometer vince.

## I due file

- `data/cronometer/dailysummary.csv` — i totali. Una riga `Total` per giorno con tutti
  i nutrienti, più una riga per pasto (Breakfast/Lunch/Dinner/Snacks/Bike) con i suoi.
- `data/cronometer/servings.csv` — le porzioni, cioè quali alimenti in quale pasto.

## Giornate piene e giornate parziali

La colonna `Completed` di Cronometer è `false` su tutte e 2.175 le righe: non è mai
stata usata, e come indicatore non vale niente. La completezza va deducibile dai dati,
e serve dedurla perché **106 dei 265 giorni stanno sotto le 800 kcal**: non sono
giornate di digiuno, sono giornate in cui è stato registrato un pasto solo e poi si è
smesso. 126 giorni hanno un solo gruppo-pasto.

Sovrascrivere un giorno così con 400 kcal cancellerebbe un pranzo e una cena veri per
sostituirli con il nulla — peggiorerebbe il dato invece di correggerlo. Quindi:

- **giorno pieno** (≥ 3 gruppi-pasto e ≥ 1.500 kcal): i totali Cronometer sostituiscono
  tutto, e la giornata diventa osservata al 100 %.
- **giorno parziale**: i pasti registrati su Cronometer sostituiscono i corrispondenti
  della ricostruzione, e il resto della giornata resta ricostruito. La quota osservata
  sale ma non arriva a 100.

Le due soglie stanno in FULL_MEALS/FULL_KCAL, si cambiano lì, e `--check` dice subito
quanti giorni cadono di qua e di là.

## Le quote (vegetale, latticini, animale, ultra-processato)

Cronometer dà le kcal esatte per pasto ma non per singolo alimento. Le quote sono
rapporti di kcal, quindi servono kcal per alimento: si stimano dai grammi e dalla
densità calorica del gruppo, e poi **si normalizzano al totale vero del pasto**. Il
totale del giorno resta quindi esatto: approssimata è solo la ripartizione dentro il
pasto, che è l'unica cosa che quelle quote chiedono.

## Le specie vegetali

`plants_day` conta specie botaniche distinte, e i nomi Cronometer sono composti in
inglese ("Porridge Banana Cioccolato Peanut" sono quattro specie). Il riconoscimento è
a parole chiave (PLANTS) invece che a tabella nome-per-nome: 349 righe scritte a mano
sarebbero da riscrivere al prossimo export, mentre le parole chiave reggono i nomi
nuovi da sole. `--check` stampa quello che non ha riconosciuto, in ordine di frequenza:
quella lista è il lavoro da fare, se un giorno vale la pena farlo.

    python tools/food/cronometer.py --check
    python tools/food/cronometer.py            # scrive data/derived/cronometer_days.json
"""
import argparse
import collections
import csv
import json
import re
import sys

import common

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SRC = common.DATA / "cronometer"
DAILY = SRC / "dailysummary.csv"
SERVINGS = SRC / "servings.csv"
OUT = common.DERIVED / "cronometer_days.json"

# Le soglie che separano una giornata piena da una registrata a metà. Vedi docstring.
FULL_MEALS = 3
FULL_KCAL = 1500.0

# Colonna Cronometer -> nutriente della pipeline, con il fattore di conversione.
# La vitamina D è l'unica che cambia unità: Cronometer la dà in UI, noi in µg, e
# 40 UI = 1 µg. Senza il fattore la copertura di vitamina D uscirebbe quaranta volte
# troppo alta e l'indice vitaminico si tapperebbe a 100 su ogni giorno Cronometer.
NUTRIENT_MAP = {
    "kcal": ("Energy (kcal)", 1.0),
    "protein_g": ("Protein (g)", 1.0),
    "carb_g": ("Carbs (g)", 1.0),
    "sugar_g": ("Sugars (g)", 1.0),
    "fiber_g": ("Fiber (g)", 1.0),
    "fat_g": ("Fat (g)", 1.0),
    "satfat_g": ("Saturated (g)", 1.0),
    "omega3_g": ("Omega-3 (g)", 1.0),
    "sodium_mg": ("Sodium (mg)", 1.0),
    "potassium_mg": ("Potassium (mg)", 1.0),
    "calcium_mg": ("Calcium (mg)", 1.0),
    "iron_mg": ("Iron (mg)", 1.0),
    "magnesium_mg": ("Magnesium (mg)", 1.0),
    "zinc_mg": ("Zinc (mg)", 1.0),
    "vitc_mg": ("Vitamin C (mg)", 1.0),
    "vita_ug": ("Vitamin A (µg)", 1.0),
    "vitd_ug": ("Vitamin D (IU)", 1.0 / 40.0),
    "b12_ug": ("B12 (Cobalamin) (µg)", 1.0),
    "folate_ug": ("Folate (µg)", 1.0),
}

# --- di che grasso sono fatti i grassi ---------------------------------------
# Chiesto il 2026-08-17: "vorrei che mostri i grassi divisi tra saturi, insaturi e
# trans". Il database interno (foods.csv) ha SOLO `satfat_g`: mono, poli e trans
# non ci sono, e non e' una dimenticanza — non esiste una fonte per riempirli su
# 400 alimenti senza inventarli. Cronometer invece li misura tutti e quattro.
#
# Quindi la scomposizione dei grassi esiste **solo dove Cronometer ha pesato il
# giorno intero**, ed e' misurata; altrove non esiste, e resta vuota invece di
# essere ricostruita. E' la stessa regola di tutta la repo: meglio un pezzo di
# serie mancante che un pezzo di serie che finge. Va in un dizionario suo e non
# in NUTRIENT_MAP perche' quelle chiavi devono restare esattamente le colonne di
# `common.NUTRIENTS`, che sono quelle che il database interno sa produrre.
FAT_SPLIT_MAP = {
    "mono_g": ("Monounsaturated (g)", 1.0),
    "poly_g": ("Polyunsaturated (g)", 1.0),
    "trans_g": ("Trans-Fats (g)", 1.0),
}

MEAL_IT = {"Breakfast": "colazione", "Lunch": "pranzo", "Dinner": "cena",
           "Snacks": "spuntino", "Bike": "in bici", "'-": "non_specificato",
           "Total": "totale"}

# Quale fascia della RICOSTRUZIONE viene sostituita da quale gruppo di Cronometer.
# Serve solo ai giorni parziali: se Cronometer ha il pranzo vero, il pranzo inventato
# da fill_defaults.py per quel giorno se ne deve andare, e la cena inventata resta.
# `Bike` finisce su `spuntino` perché è lì che la ricostruzione mette il carburante
# della bici (il panino delle uscite lunghe): mangiarne due sarebbe doppio conteggio.
# `'-` non ha fascia — è il gruppo "non assegnato" di Cronometer — e quindi non
# sostituisce niente: si somma come cibo osservato in più, che è quello che è.
SLOT_OF = {
    "Breakfast": ("colazione",), "Lunch": ("pranzo",), "Dinner": ("cena",),
    "Snacks": ("spuntino", "merenda"), "Bike": ("spuntino",),
}

# Parola chiave -> specie botanica. Si cercano TUTTE, non la prima: un porridge con
# banana e cacao conta avena, banana e cacao. Le chiavi lunghe stanno prima delle
# corte perché "sweet potato" non deve finire in "potato".
PLANTS = [
    ("sweet potato", "patata_dolce"), ("okinawan sweet potato", "patata_dolce"),
    ("peanut butter", "arachide"), ("peanut", "arachide"), ("pb2", "arachide"),
    ("chickpea", "cece"), ("ceci", "cece"), ("chick pea", "cece"), ("hummus", "cece"),
    ("lentil", "lenticchia"), ("lenticchie", "lenticchia"), ("dahl", "lenticchia"),
    ("black bean", "fagiolo_nero"), ("cannellini", "fagiolo"), ("kidney bean", "fagiolo"),
    ("mexican bean", "fagiolo"), ("fagioli", "fagiolo"), ("bean", "fagiolo"),
    ("green bean", "fagiolino"),
    ("soy", "soia"), ("soia", "soia"), ("tofu", "soia"), ("tvp", "soia"),
    ("textured vegetable protein", "soia"), ("edamame", "soia"),
    ("pea", "pisello"), ("piselli", "pisello"), ("lupin", "legume_misto"),
    ("oat", "avena"), ("porridge", "avena"), ("oatmeal", "avena"),
    ("spelt", "farro"), ("farro", "farro"), ("barley", "orzo"), ("orzo", "orzo"),
    ("quinoa", "quinoa"), ("teff", "teff"), ("buckwheat", "grano_saraceno"),
    ("saraceno", "grano_saraceno"), ("amaranth", "amaranto"), ("sorgo", "sorgo"),
    ("rye", "segale"), ("segale", "segale"), ("rice", "riso"), ("risotto", "riso"),
    ("couscous", "frumento"), ("pasta", "frumento"), ("spaghetti", "frumento"),
    ("bread", "frumento"), ("pane", "frumento"), ("panino", "frumento"),
    ("wheat", "frumento"), ("flour", "frumento"), ("focaccia", "frumento"),
    ("croissant", "frumento"), ("pizza", "frumento"), ("brioche", "frumento"),
    ("crepe", "frumento"), ("waffle", "frumento"), ("cake", "frumento"),
    ("pie", "frumento"), ("strudel", "frumento"), ("baklava", "frumento"),
    ("brownie", "frumento"), ("noodle", "frumento"), ("ravioli", "frumento"),
    ("lasagn", "frumento"), ("gallette", "frumento"), ("cracker", "frumento"),
    ("bun", "frumento"), ("tart", "frumento"), ("polenta", "mais"),
    ("corn", "mais"), ("mais", "mais"), ("cereal", "frumento"), ("bran", "frumento"),
    ("apple", "mela"), ("mela", "mela"), ("banana", "banana"), ("banane", "banana"),
    ("orange", "arancia"), ("arancia", "arancia"), ("clementine", "mandarino"),
    ("tangerine", "mandarino"), ("mandarino", "mandarino"), ("lemon", "limone"),
    ("grapefruit", "pompelmo"), ("strawberr", "fragola"), ("fragola", "fragola"),
    ("blueberr", "mirtillo"), ("mirtill", "mirtillo"), ("raspberr", "lampone"),
    ("frutti di bosco", "frutti_di_bosco"), ("mixed berries", "frutti_di_bosco"),
    ("mixed berr", "frutti_di_bosco"), ("berries", "frutti_di_bosco"),
    ("peach", "pesca"), ("pesca", "pesca"), ("apricot", "albicocca"),
    ("pear", "pera"), ("mango", "mango"), ("melon", "melone"), ("crenshaw", "melone"),
    ("watermelon", "anguria"), ("pineapple", "ananas"), ("ananas", "ananas"),
    ("grape", "uva"), ("raisin", "uva"), ("date", "dattero"), ("kiwi", "kiwi"),
    ("avocado", "avocado"), ("olive", "oliva"), ("oliva", "oliva"),
    ("rhubarb", "rabarbaro"), ("amla", "amla"), ("coconut", "cocco"),
    ("tomato", "pomodoro"), ("pomodor", "pomodoro"), ("caprese", "pomodoro"),
    ("ketchup", "pomodoro"), ("ragu", "pomodoro"), ("passata", "pomodoro"),
    ("onion", "cipolla"), ("cipolla", "cipolla"), ("garlic", "aglio"),
    ("carrot", "carota"), ("carote", "carota"), ("spinach", "spinacio"),
    ("spinaci", "spinacio"), ("arugula", "rucola"), ("rucola", "rucola"),
    ("lettuce", "lattuga"), ("salad", "verdura_mista"), ("insalata", "verdura_mista"),
    ("spring mix", "verdura_mista"), ("macedonia", "frutta"),
    ("mixed vegetable", "verdura_mista"), ("broccoli", "broccolo"),
    ("cauliflower", "cavolfiore"), ("cabbage", "cavolo_rosso"), ("chard", "bietola"),
    ("pepper, sweet", "peperone"), ("bell pepper", "peperone"), ("peperon", "peperone"),
    ("peppers, sweet", "peperone"), ("pumpkin", "zucca"), ("squash", "zucca"),
    ("zucchin", "zucchina"), ("aubergine", "melanzana"), ("eggplant", "melanzana"),
    ("melanzan", "melanzana"), ("potato", "patata"), ("patate", "patata"),
    ("french fries", "patata"), ("beet", "barbabietola"), ("mushroom", "fungo"),
    ("porcini", "fungo"), ("funghi", "fungo"), ("cucumber", "cetriolo"),
    ("pickle", "cetriolo"), ("horseradish", "rafano"), ("sprout", "soia"),
    ("cocoa", "cacao"), ("cacao", "cacao"), ("chocolate", "cacao"),
    ("cioccolato", "cacao"), ("hazelnut", "nocciola"), ("almond", "mandorla"),
    ("mandorl", "mandorla"), ("walnut", "noce"), ("pecan", "noce"),
    ("macadamia", "noce"), ("cashew", "anacardo"), ("pistachio", "pistacchio"),
    ("chia", "chia"), ("flax", "lino"), ("hemp", "canapa"),
    ("sunflower seed", "girasole"), ("sesame", "sesamo"), ("wheat germ", "frumento"),
    ("coffee", "caffe"), ("caffe", "caffe"), ("cappuccino", "caffe"),
    ("espresso", "caffe"), ("latte cioccolato", "cacao"), ("cafe latte", "caffe"),
    ("tea", "te"), ("matcha", "te"), ("rooibos", "te"), ("chicory", "cicoria"),
    ("basil", "basilico"), ("basilico", "basilico"), ("pesto", "basilico"),
    ("parsley", "prezzemolo"), ("rosemary", "rosmarino"), ("rosmarino", "rosmarino"),
    ("oregano", "origano"), ("cinnamon", "cannella"), ("curry", "curry"),
    ("cumin", "cumino"), ("mustard", "senape"), ("nutritional yeast", "lievito"),
    ("lievito", "lievito"), ("yeast", "lievito"), ("psyllium", "psillio"),
    ("spirulina", "spirulina"), ("honey", "miele_fiori"),
    # generici, in fondo perché le chiavi specifiche vincono prima: una
    # "Strawberry Jam" è fragola, una "Jam or Preserves" e basta è frutta e stop.
    ("jam", "frutta"), ("marmellata", "frutta"), ("preserves", "frutta"),
    ("juice", "frutta"), ("balsamic", "uva"), ("smoothie", "frutta"),
]

# Fermentati: contano come "giorno con almeno un fermentato" nell'indice del microbiota.
FERMENTED = ("yogurt", "yoghurt", "skyr", "kefir", "cheese", "formagg", "grana",
             "parmigiano", "parmesan", "mozzarella", "burrata", "ricotta",
             "gorgonzola", "scamorza", "fiocchi di latte", "soy sauce", "miso",
             "tempeh", "sauerkraut", "kimchi", "pickle", "sourdough", "beer",
             "vinegar", "bresaola", "prosciutto", "salami", "mortadella")

# Ultra-processati. Non "confezionato": roba formulata, con ingredienti che in cucina
# non esistono. Le merendine e le bibite sì, il pane del fornaio no.
UPF = ("pop tarts", "coca", "cola", "moon pie", "stroopwafel", "ice cream", "gelato",
       "protein powder", "whey", "pudding", "mousse", "hazelnut spread", "candies",
       "soy chips", "cereal party mix", "energy", "isostar", "maurten", "bar,",
       "uncrustable", "hot dog", "sausage", "bacon", "nugget", "french fries",
       "ketchup", "mayo", "salad dressing", "ragu, original", "party mix",
       "cheesecake", "brioche", "croissant", "pop-tart", "collage powder", "glycine")

# Densità calorica per categoria Cronometer, in kcal per grammo. Serve SOLO a pesare
# la ripartizione delle kcal del pasto fra i suoi alimenti: il totale del pasto resta
# quello vero, questi numeri decidono solo chi se ne prende quanto.
KCAL_PER_G = {
    "Fats and Oils": 7.0, "Nut and Seed Products": 5.8, "Sweets": 4.0,
    "Baked Products": 3.0, "Cereal Grains and Pasta": 3.5, "Breakfast Cereals": 3.6,
    "Snacks": 4.5, "Legumes and Legume Products": 1.4, "Dairy and Egg Products": 1.3,
    "Beef Products": 2.2, "Pork Products": 3.0, "Poultry Products": 1.7,
    "Sausages and Luncheon Meats": 2.6, "Lamb, Veal, and Game Products": 2.3,
    "Fruits and Fruit Juices": 0.6, "Vegetables and Vegetable Products": 0.5,
    "Soups, Sauces, and Gravies": 0.8, "Spices and Herbs": 2.5,
    "Beverages": 0.4, "Supplements": 3.5, "Meals, Entrees, and Sidedishes": 1.6,
    "Fast Foods": 2.5, "Restaurant Foods": 2.5, "": 1.5,
}
DAIRY = ("Dairy and Egg Products",)
ANIMAL = ("Beef Products", "Pork Products", "Poultry Products",
          "Sausages and Luncheon Meats", "Lamb, Veal, and Game Products",
          "Finfish and Shellfish Products")
# Cronometer mette le uova insieme ai latticini in una categoria sola. Un uovo non e'
# un latticino, e in una torta che deve fare 100 la fetta sbagliata non si compensa
# con niente: quindi si guarda il nome prima della categoria.
EGGS = ("egg", "uova", "uovo")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def grams(amount):
    """"150.00 g" -> 150. Le unità non a peso valgono una porzione convenzionale.

    Non è una stima nutrizionale, è solo un peso relativo per spartire le kcal del
    pasto: "1 cup" pesa più di "1 tbsp" e questo basta a non dare a un cucchiaino di
    miele la stessa fetta di calorie di un piatto di pasta.
    """
    m = re.match(r"\s*([\d.,]+)\s*(.*)", amount or "")
    if not m:
        return 100.0
    try:
        q = float(m.group(1).replace(",", ""))
    except ValueError:
        return 100.0
    u = m.group(2).strip().lower()
    if u.startswith("g") or u.startswith("ml"):
        return q
    if u.startswith("kg") or u.startswith("l"):
        return q * 1000
    for key, w in (("tbsp", 15), ("tsp", 5), ("cup", 200), ("scoop", 30),
                   ("slice", 30), ("large", 130), ("medium", 110), ("small", 80),
                   ("full recipe", 400), ("serving", 150), ("each", 100)):
        if key in u:
            return q * w
    return q * 100.0


def plants_of(name):
    low = " " + (name or "").lower() + " "
    return {sp for kw, sp in PLANTS if kw in low}


def has(name, words):
    low = (name or "").lower()
    return any(w in low for w in words)


def load():
    """(totali per giorno, totali per pasto, porzioni per giorno/pasto)."""
    if not DAILY.exists() or not SERVINGS.exists():
        return {}, {}, {}
    day_tot, meal_tot = {}, collections.defaultdict(dict)
    with DAILY.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            d, g = r.get("Date"), (r.get("Group") or "").strip()
            if not d or num(r.get("Energy (kcal)")) is None:
                continue
            vals = {}
            for m in (NUTRIENT_MAP, FAT_SPLIT_MAP):
                for nut, (col, factor) in m.items():
                    v = num(r.get(col))
                    vals[nut] = (v * factor) if v is not None else 0.0
            if g == "Total":
                day_tot[d] = vals
            else:
                meal_tot[d][g] = vals

    servings = collections.defaultdict(lambda: collections.defaultdict(list))
    with SERVINGS.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            d = r.get("Day")
            if not d:
                continue
            servings[d][(r.get("Group") or "").strip()].append({
                "name": (r.get("Food Name") or "").strip(),
                "amount": (r.get("Amount") or "").strip(),
                "cat": (r.get("Category") or "").strip(),
            })
    return day_tot, meal_tot, servings


def build():
    day_tot, meal_tot, servings = load()
    out, unknown = {}, collections.Counter()

    for d, tot in sorted(day_tot.items()):
        meals = servings.get(d, {})
        groups = [g for g in meals if g not in ("Total",)]
        n_items = sum(len(v) for v in meals.values())
        full = len(groups) >= FULL_MEALS and tot["kcal"] >= FULL_KCAL

        plants, ferm = set(), False
        share = collections.defaultdict(float)
        detail = {}

        for g, items in meals.items():
            # kcal vere del pasto quando ci sono; se no, la quota del giorno
            mk = (meal_tot.get(d, {}).get(g) or {}).get("kcal")
            weights = [grams(it["amount"]) * KCAL_PER_G.get(it["cat"], 1.5)
                       for it in items]
            tw = sum(weights) or 1.0
            if mk is None:
                mk = tot["kcal"] * (tw / sum(
                    sum(grams(x["amount"]) * KCAL_PER_G.get(x["cat"], 1.5)
                        for x in v) or 1.0 for v in meals.values()) or 1.0)
            rows = []
            for it, w in zip(items, weights):
                kc = mk * w / tw
                p = plants_of(it["name"])
                if p:
                    plants |= p
                else:
                    unknown[it["name"]] += 1
                if has(it["name"], FERMENTED):
                    ferm = True
                # stessa partizione di build_nutrition_series.py, stessa precedenza:
                # ogni caloria in una fetta sola, e le quattro fanno 100
                if it["cat"] in ANIMAL or has(it["name"], EGGS):
                    share["animal"] += kc
                elif it["cat"] in DAIRY:
                    share["dairy"] += kc
                elif p:
                    share["plant"] += kc
                else:
                    share["other"] += kc
                # asse trasversale, non una quinta fetta
                if has(it["name"], UPF):
                    share["upf"] += kc
                # `a` e `r` tengono la forma che il popup di /vita si aspetta dalle
                # righe del diario: a=0 vuol dire osservato (Cronometer lo e' sempre),
                # r vuoto vuol dire che non viene da una ricetta ricostruita.
                rows.append({"n": it["name"], "q": it["amount"], "kcal": round(kc),
                             "a": 0, "r": ""})
            detail[MEAL_IT.get(g, g.lower())] = rows

        # Giorno parziale: le fasce che Cronometer sostituisce, e la somma dei
        # nutrienti che ci mette dentro. Un giorno pieno non ne ha bisogno — lì
        # vale il totale, e la ricostruzione di quel giorno sparisce tutta.
        slots, partial = set(), {n: 0.0 for n in NUTRIENT_MAP}
        if not full:
            for g, vals in (meal_tot.get(d) or {}).items():
                slots.update(SLOT_OF.get(g, ()))
                for n in NUTRIENT_MAP:
                    partial[n] += vals.get(n, 0.0)

        out[d] = {
            "nutrients": {k: round(v, 3) for k, v in tot.items()},
            # la scomposizione dei grassi viaggia a parte, e solo per i giorni pieni:
            # su un giorno parziale la somma delle tre non e' il grasso della giornata,
            # e una composizione che non somma al suo totale non e' una composizione
            "fat_split": ({k: round(tot.get(k, 0.0), 2)
                           for k in ("satfat_g",) + tuple(FAT_SPLIT_MAP)} if full else None),
            "slots": sorted(slots),
            "partial_nutrients": {k: round(v, 3) for k, v in partial.items()},
            "meals": detail,
            # I nutrienti per pasto, con le chiavi italiane di `meals` (ordine #22:
            # i totali della colazione, non solo quelli del giorno). Qui esistono
            # gia' — `meal_tot` li somma per calcolare i giorni parziali — e vanno
            # emessi perche' a valle NON si possono riderivare: le voci di
            # Cronometer portano `q` come stringa gia' formattata ("1 cup"), senza
            # food_id ne' quantita' numerica.
            "meal_nut": {MEAL_IT.get(g, g.lower()): {n: round(v, 3) for n, v in vals.items()}
                         for g, vals in (meal_tot.get(d) or {}).items()},
            "meal_kcal": {MEAL_IT.get(g, g.lower()): round(v["kcal"])
                          for g, v in (meal_tot.get(d) or {}).items()},
            "plants": sorted(plants),
            "fermented": ferm,
            "shares": {k: round(v, 1) for k, v in share.items()},
            "n_items": n_items,
            "meal_groups": len(groups),
            "full": full,
        }
    return out, unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="riporta e basta, non scrive")
    args = ap.parse_args()

    if not DAILY.exists():
        print(f"  nessun export Cronometer in {SRC} — saltato")
        return
    days, unknown = build()
    if not days:
        print("  export Cronometer vuoto — saltato")
        return

    full = [d for d, v in days.items() if v["full"]]
    ds = sorted(days)
    kc = sorted(v["nutrients"]["kcal"] for v in days.values())
    print(f"{len(days)} giorni Cronometer, {ds[0]} → {ds[-1]}")
    print(f"  pieni (≥{FULL_MEALS} pasti e ≥{FULL_KCAL:.0f} kcal): {len(full)}")
    print(f"  parziali: {len(days) - len(full)}")
    print(f"  kcal mediane {kc[len(kc)//2]:.0f}")
    print(f"  specie vegetali riconosciute: "
          f"{len({p for v in days.values() for p in v['plants']})} distinte, "
          f"mediana {sorted(len(v['plants']) for v in days.values())[len(days)//2]} al giorno")
    tot_items = sum(v["n_items"] for v in days.values())
    print(f"  porzioni: {tot_items}, senza specie riconosciuta {sum(unknown.values())} "
          f"({100*sum(unknown.values())/max(1,tot_items):.0f} %)")
    if unknown:
        print("  i non riconosciuti più frequenti (quasi tutti animali o latticini,")
        print("  che una specie vegetale non ce l'hanno e non devono averla):")
        for n, c in unknown.most_common(12):
            print(f"    {c:4d}  {n[:64]}")

    if args.check:
        print("\n(--check: niente scritto)")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(days, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
