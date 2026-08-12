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

VITAMINS = ("vitc_mg", "vita_ug", "vitd_ug", "b12_ug", "folate_ug")
MINERALS = ("potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg")

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
          # quote di calorie per origine: vegetale, latticini, ultra-processato,
          # animale. Sono percentuali del giorno, non grammi, perche' la domanda
          # e' "quanto della mia dieta e'..." e non "quanto ne ho mangiato".
          "pct_plant", "pct_dairy", "pct_upf", "pct_animal"] +          ["cnt_" + k for k in TALLY]


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
    """TSS per giorno da activities.csv."""
    tss = defaultdict(float)
    if not common.ACTIVITIES_CSV.exists():
        return tss
    with common.ACTIVITIES_CSV.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = (r.get("date") or "")[:10]
            if d:
                tss[d] += float(r.get("training_load") or 0)
    return tss


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

    # dettaglio per il popup: per giorno, i pasti con dentro gli alimenti veri
    detail = defaultdict(lambda: defaultdict(list))
    per_day = defaultdict(lambda: {n: 0.0 for n in common.NUTRIENTS})
    plants_of = defaultdict(set)
    kcal_src = defaultdict(lambda: defaultdict(float))
    upf_kcal = defaultdict(float)
    src_kcal = defaultdict(lambda: defaultdict(float))
    ferm_days = set()
    tally = defaultdict(lambda: defaultdict(float))
    items = defaultdict(int)
    unknown = set()

    for r in rows:
        f = foods.get(r["food_id"])
        if f is None:
            unknown.add(r["food_id"])
            continue
        qty = float(r["qty"])
        d = r["date"]
        for n in common.NUTRIENTS:
            per_day[d][n] += f["per_unit"][n] * qty
        kcal = f["per_unit"]["kcal"] * qty
        kcal_src[d]["assumed" if r.get("source") == "assunto" else "observed"] += kcal
        items[d] += 1
        detail[d][r.get("meal") or "non_specificato"].append({
            "n": f["name"],
            "q": f"{qty:g} {f['unit']}" if f["unit"] != "unit" else
                 (f"{qty:g}×" if qty != 1 else "1"),
            "kcal": round(kcal),
            "a": 1 if r.get("source") == "assunto" else 0,   # assunto, non osservato
            "r": r.get("recipe", ""),                        # da quale ricetta viene
        })
        # un alimento puo' contare in piu' quote: il latte intero e' latticino e
        # animale, un cornetto e' vegetale (frumento) e ultra-processato. Sono
        # quote sovrapposte, non una torta — e vanno lette cosi'.
        if f["plant"]:
            src_kcal[d]["plant"] += kcal
        if f["group"] == "latticini":
            src_kcal[d]["dairy"] += kcal
        if f["group"] in ("proteine", "latticini"):
            src_kcal[d]["animal"] += kcal
        if f["plant"]:
            plants_of[d].add(f["plant"])
        if f["fermented"]:
            ferm_days.add(d)
        if f["upf"]:
            upf_kcal[d] += kcal
        for key, (_lab, ids) in TALLY.items():
            if r["food_id"] in ids:
                tally[d][key] += qty / ids[r["food_id"]]

    if unknown:
        print(f"  ! alimenti sconosciuti, ignorati: {sorted(unknown)}", file=sys.stderr)

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

        tss = tss_of.get(k, 0.0)
        g_per_kg = max(3.0, min(10.0, 3.0 + 0.03 * tss))
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
               for q in ("plant", "dairy", "animal")},
            "pct_upf": round(100.0 * upf_kcal.get(k, 0.0) / (t["kcal"] or 1), 1),
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
                prof = {
                    "recipes": sorted({it["r"] for m in detail[k]
                                       for it in detail[k][m] if it["r"]}),
                    "tot": {n: round(t[n], 1) for n in common.NUTRIENTS},
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
                "tot": {n: round(t[n], 1) for n in common.NUTRIENTS},
                "pct": {n: round(100.0 * t[n] / rda[n]) for n in common.NUTRIENTS
                        if rda.get(n)},
                "cap": {n: round(100.0 * t[n] / v)
                        for n, v in profile["limits_abs"].items() if v},
                "obs": r["kcal_observed"], "asm": r["kcal_assumed"],
            }
        # le forme dedotte tornano indietro come oggetti veri, indicizzati per id
        days["_p"] = {pid: json.loads(sig) for sig, pid in profiles.items()}
        p = Path(args.export_days)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(days, ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")
        print(f"-> {p}  ({len(days)} giorni, {p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
