#!/usr/bin/env python3
"""
build_vita.py — build /vita: i tre tracker in cima, e sotto una colonna con ogni
serie misurabile della vita di Michele — carico, sonno, HRV, corpo, volume, tavola.

I grafici stanno **uno sopra l'altro**, non a griglia: condividono l'asse x, quindi
l'occhio puo' scendere lungo la pagina confrontando lo stesso mese fra serie diverse.
E' l'unica cosa che una griglia di riquadri non lascia fare, e il motivo per cui la
pagina e' fatta cosi'.

Where the other tools in here read a *published page* and keep the hub honest against
it, this one goes straight to the source: it pulls the whole wellness history and the
whole activity list from Intervals.icu, packs them into one compact payload, and
inlines that into a single self-contained HTML file. No runtime fetch, no API key on
the client, no dependency — the page is a flat file that happens to hold eleven years.

What the data actually is (measured 2026-08-09, not assumed — see --check):

  * wellness runs 2015-03-29 → today, 4.152 days, and *every* day carries ctl/atl.
  * but the load feeding them only becomes real in 2019: 2015-2018 activities came in
    from Strava without HR or power, so their training load is zero. Load charts
    therefore start where the load does, not where the record does.
  * **2022 is missing entirely** — no activities at all. CTL decays to zero across it,
    which reads like a year off the bike and is not what happened: it is a hole in the
    archive. Every long no-activity run is shaded and labelled rather than drawn
    through, because a smooth line across a gap is a lie a chart tells very well.
  * sleep, sleepScore, HRV, resting HR and steps start in **2025** (the watch), VO2max
    likewise. Weight is 65 points and body fat 53 over the same window — sparse enough
    that they are drawn as clouds with a fitted trend, never as a line.

Each tile states its own window, so no tile can imply coverage it does not have.

Usage
-----
    set INTERVALS_API_KEY=...          (or --api-key, or tools/.intervals_key)

    python tools/build_vita.py --check      # report coverage, write nothing
    python tools/build_vita.py --sync-source # pull cache + attività per il cibo
    python tools/build_vita.py              # pull + rebuild the page
    python tools/build_vita.py --offline    # rebuild from the cached pull

The raw pull is cached to `tools/.cruscotto_cache.json` (gitignored) so re-rendering
while working on the page costs nothing and cannot be rate-limited. `--dry-run` does
everything except write. The previous page is copied to `index.html.bak` first.
"""
import argparse
import csv
import io
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from sync_intervals import api, get_api_key  # noqa: E402  (same folder, shared auth)
import vita_trackers  # noqa: E402  (i tre tracker in cima alla pagina)
sys.path.insert(0, os.path.join(HERE, "food"))
import common as food_common  # noqa: E402  (backfill + ricalcolo CTL, in comune)

CACHE = os.path.join(HERE, ".cruscotto_cache.json")
OUT_DIR = os.path.join(ROOT, "vita")
OUT = os.path.join(OUT_DIR, "index.html")
REPORT = os.path.join(HERE, "vita_tests.md")
FOOD_DATA = os.path.join(OUT_DIR, "cibo", "data")
FOOD_ACTIVITIES = os.path.join(HERE, "food", "data", "activities.csv")
# Le attività che Intervals non ha, riprese dall'export Strava da tools/strava_backfill.py.
# Il 2022 intero sta qui dentro: su Intervals quell'anno ha zero attività, su Strava 394.
# Sta in un file SUO e non dentro activities.csv perché quello lo riscrive
# `--sync-source` a ogni ora, e si porterebbe via il backfill senza dirlo.
FOOD_BACKFILL = os.path.join(HERE, "food", "data", "activities_backfill.csv")

# Aggregati giornalieri di alimentazione, esportati da ~/health-log con
# `scripts/build_nutrition_series.py --export`. Vive qui perche' la GitHub Action
# non ha accesso a quella repo — e perche' quello che esce sono **solo** i totali
# del giorno: il diario dei pasti, con dentro dove e con chi ha mangiato, resta
# privato di la'.
NUTRITION = os.path.join(FOOD_DATA, "nutrition.csv")
# Dettaglio giorno per giorno per il popup: pasti, alimenti, % dei fabbisogni.
# Stesso esportatore, flag `--export-days`.
DAYS = os.path.join(FOOD_DATA, "days.json")
FOOD_PROFILE = os.path.join(HERE, "food", "profile.json")
# Il MODELLO della flora (scripts/microbiome_model.py). Non e' una misura: nessuno
# ha sequenziato niente, e la pagina lo dice a caratteri grandi.
MICROBES = os.path.join(FOOD_DATA, "microbiome.csv")
# Matrice alimento x genere: il modello della flora letto al contrario, cioe'
# quali cibi davvero mangiati muovono quali generi. Non e' una misura in piu',
# e' il cablaggio del modello reso visibile.
FLORA_FOODS = os.path.join(FOOD_DATA, "flora_foods.csv")
# Il modello metabolico: temperatura al polso durante l'uscita, banda FatMax,
# stime di ossidazione, e il "momento metabolico". Come la flora, e' in gran parte
# MODELLO e non misura — la temperatura invece e' un sensore vero, solo non del
# meteo. Ogni riquadro che ne esce lo dichiara nella propria didascalia.
METAB = os.path.join(FOOD_DATA, "metabolismo.csv")
# Le sole colonne che la pagina disegna. Il CSV ne ha 24 su undici anni: spedirle
# tutte costava 385 KB a ogni visita per serie che nessun riquadro guarda. Quando
# nasce un riquadro nuovo si aggiunge la sua colonna qui — non il contrario.
METAB_COLS = ("temp_c", "temp_min_c", "temp_max_c",
              "fatmax_hr", "fatmax_lo_hr", "fatmax_hi_hr", "fatmax_min",
              # i grammi: il modello li stima per giornata, e per giornata non si
              # confrontano — due ore e venti minuti fanno grammi diversi senza che
              # sia cambiato niente. La pagina li divide per `train_min` e disegna
              # il TASSO, g/min, che e' la grandezza di cui parla la letteratura.
              # `fat_pct_60d` e' il secondo asse della dieta, aggiunto il 17/08/2026:
              # il modello non legge piu' solo i carboidrati abituali ma anche i
              # grassi abituali. Serve in pagina per poter DIRE su cosa poggia la
              # stima, invece di lasciarlo scritto solo nel sorgente del modello.
              "fat_g_est", "train_min", "mfo_g_min", "cho_pct_60d", "fat_pct_60d",
              "mm", "mm_n")

# The athlete. Intervals.icu also accepts "0" for "whoever owns the key", but the
# explicit id keeps the CI logs readable when a key is swapped.
ATHLETE = os.environ.get("INTERVALS_ATHLETE_ID", "i302515")
OLDEST = "2012-01-01"

# Categorical slots 1-4, LIGHT steps: dal 16/08/2026 la scheda e' bianca, non piu'
# #211d16 (la pagina ha preso il vestito della home). I passi scuri di prima, nati per
# stagliarsi su una carta scura, sul bianco sbiadivano — quindi sono stati sostituiti
# coi passi chiari della stessa palette, quelli di Google I/O portati sopra il 4,5:1.
# Devono restare uguali a --s1..--s4 nel CSS del TEMPLATE: sono un registro solo, letto
# da due parti, e se divergono i grafici PNG e la pagina dicono due colori diversi.
# Resta vero il principio: il colore non porta MAI l'identita' da solo — ogni serie e'
# nominata nel proprio titolo o nella propria legenda.
# Dal 17/08/2026 sono i colori LETTERALI della home (io-blue, io-red, io-green),
# con i due scostamenti spiegati per esteso accanto a --s1..--s4 nel TEMPLATE:
# il verde e' portato a 4:1 perche' #34A853 sotto 3:1 non e' un tratto leggibile,
# e il quarto slot resta viola perche' il quarto colore della home e' un FONDO.
C = {
    "blue": "#4285f4",
    "orange": "#ea4335",
    "aqua": "#1e8e3e",
    "yellow": "#8430ce",    # non e' piu' giallo: il giallo I/O e' un fondo, e in mezzo ai dati si spacciava per una serie
    "red": "#ea4335",       # the negative arm of Forma — a diverging pole, not a series
}

# Sport buckets. Six raw types collapse to four so a stack never needs a fifth hue.
SPORTS = ["Bici", "Corsa", "Nuoto", "Altro"]
SPORT_OF = {
    "Ride": 0, "VirtualRide": 0, "GravelRide": 0, "MountainBikeRide": 0, "EBikeRide": 0,
    "Run": 1, "TrailRun": 1, "VirtualRun": 1,
    "Swim": 2, "OpenWaterSwim": 2,
}


# --------------------------------------------------------------------- fetching

def pull(key, use_cache=False):
    """Wellness + activities, whole history. Cached raw so re-renders are free."""
    if use_cache:
        if not os.path.exists(CACHE):
            sys.exit(f"--offline but no cache at {CACHE} — run once without it.")
        with open(CACHE, encoding="utf-8") as f:
            raw = json.load(f)
        print(f"  cache  {raw['pulled']}  "
              f"{len(raw['wellness'])} giorni · {len(raw['activities'])} attività")
        return raw

    today = date.today().isoformat()
    print(f"  GET wellness   {OLDEST} → {today}")
    wellness = api(f"athlete/{ATHLETE}/wellness?oldest={OLDEST}&newest={today}", key)
    print(f"  GET activities {OLDEST} → {today}")
    acts = api(f"athlete/{ATHLETE}/activities?oldest={OLDEST}&newest={today}", key)
    if not wellness or not acts:
        sys.exit("Intervals.icu returned nothing — check the API key and try again.")

    raw = {"pulled": today, "wellness": wellness, "activities": acts}
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    print(f"  cached {len(wellness)} giorni · {len(acts)} attività → "
          f"{os.path.basename(CACHE)}")
    return raw


def export_food_activities(raw):
    """Allinea il carico usato dal modello alimentare allo stesso pull di /vita.

    Il target carboidrati legge questo CSV. Se resta indietro, un allenamento appena
    arrivato su Intervals compare nei grafici ma vale zero nel modello del cibo: due
    verità diverse nella stessa pagina. Scriviamo solo se il contenuto cambia.
    """
    fields = ["date", "name", "type", "moving_time_s", "elapsed_time_s", "distance_m",
              "elevation_m", "calories", "training_load", "intensity", "avg_hr",
              "max_hr", "avg_power_w", "np_w"]
    rows = []
    for a in sorted(raw.get("activities") or [],
                    key=lambda x: (x.get("start_date_local") or "", str(x.get("id") or ""))):
        day = (a.get("start_date_local") or "")[:10]
        if not day:
            continue
        rows.append({
            "date": day, "name": a.get("name") or "", "type": a.get("type") or "",
            "moving_time_s": a.get("moving_time"), "elapsed_time_s": a.get("elapsed_time"),
            "distance_m": a.get("distance"), "elevation_m": a.get("total_elevation_gain"),
            "calories": a.get("calories"), "training_load": a.get("icu_training_load"),
            "intensity": a.get("icu_intensity"), "avg_hr": a.get("average_heartrate"),
            "max_hr": a.get("max_heartrate"),
            "avg_power_w": a.get("icu_average_watts") or a.get("average_watts"),
            "np_w": (a.get("icu_weighted_avg_watts") or a.get("weighted_average_watts")
                     or a.get("normalized_power")),
        })
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    new = buf.getvalue()
    old = ""
    if os.path.exists(FOOD_ACTIVITIES):
        with open(FOOD_ACTIVITIES, encoding="utf-8", newline="") as fh:
            old = fh.read()
    if new != old:
        os.makedirs(os.path.dirname(FOOD_ACTIVITIES), exist_ok=True)
        with open(FOOD_ACTIVITIES, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        print(f"  attività cibo: {len(rows)} righe → {os.path.relpath(FOOD_ACTIVITIES, ROOT)}")
    else:
        print(f"  attività cibo: già allineate ({len(rows)} righe)")


# ---------------------------------------------------------------- shaping

def r1(v):
    return None if v is None else round(float(v), 1)


def ri(v):
    return None if v is None else int(round(float(v)))


def csv_blocks(path, idx, n, label, keep=None):
    """A date-keyed CSV -> one series per column, on the shared daily index, each one
    squeezed to its contiguous block.

    Three files land here (alimentazione, flora, metabolismo) and they all cover a
    slice of a calendar that is eleven years long. Kept as full arrays they would
    ship tens of thousands of `null` — the page grew from 322 to 761 KB the one time
    it was done that way. Each column goes out as `{i0, v}` and the page re-expands
    it, so every consumer still indexes it by day and knows nothing about the
    compression.

    `keep`, when given, is the whitelist of columns to ship. A column nothing draws
    is not free: metabolismo.csv has 24 of them over eleven years, and sending all
    24 instead of the 9 the page reads cost 385 KB on every single visit. What is
    not drawn does not travel.

    Returns (blocks, first, last, rows) — `first`/`last` are the day indices where a
    column actually starts and stops, which is what keeps a tile from drawing an
    axis wider than its own coverage.
    """
    if not os.path.exists(path):
        print(f"  {label}: nessun {os.path.basename(path)}, riquadri saltati")
        return {}, {}, {}, 0
    import csv as _csv
    with open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in _csv.DictReader(fh) if r.get("date")]
    cols = [c for c in (rows[0].keys() if rows else []) if c != "date"
            and (keep is None or c in keep)]
    tmp = {c: [None] * n for c in cols}
    for r in rows:
        i = idx.get(r["date"])
        if i is None:
            continue                       # giorno fuori dal calendario wellness
        for c in cols:
            v = r.get(c)
            if v in (None, ""):
                continue
            # `137.0` e `137` disegnano lo stesso pixel e occupano due caratteri di
            # differenza per ognuno dei quattromila giorni di ognuna delle serie.
            f = round(float(v), 2)
            tmp[c][i] = int(f) if f == int(f) else f
    out, first, last = {}, {}, {}
    for c in cols:
        a = tmp[c]
        i0 = next((i for i, v in enumerate(a) if v is not None), None)
        if i0 is None:
            continue                       # colonna interamente vuota: non si spedisce
        i1 = len(a) - 1 - next(i for i, v in enumerate(reversed(a)) if v is not None)
        out[c] = {"i0": i0, "v": a[i0:i1 + 1]}
        first[c] = i0
        last[c] = i1
    print(f"  {label}: {len(rows)} giorni, {len(out)} serie")
    return out, first, last, len(rows)


def load_backfill():
    """Le attività ricostruite da Strava, nella forma in cui le dà Intervals.

    Restituisce una lista vuota se il file non c'è: il backfill è un artefatto che
    si rigenera da un export scaricato a mano, e chi clona la repo senza deve poter
    ricostruire la pagina lo stesso — con i buchi veri, che è la vecchia verità.
    """
    if not os.path.exists(FOOD_BACKFILL):
        return []
    out = []
    with open(FOOD_BACKFILL, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("date"):
                continue

            def n(k):
                try:
                    return float(r[k])
                except (KeyError, TypeError, ValueError):
                    return 0.0
            out.append({
                "start_date_local": r["date"], "name": r.get("name") or "",
                "type": r.get("type") or "", "moving_time": n("moving_time_s"),
                "distance": n("distance_m"), "total_elevation_gain": n("elevation_m"),
                "icu_training_load": n("training_load"), "id": "",
                "strava_id": (r.get("strava_id") or "").strip(),
                "_backfill": True, "_method": r.get("load_method") or "",
            })
    print(f"  backfill Strava: {len(out)} attività che Intervals non ha")
    return out


# --------------------------------------------------------------- il diario
# Il popup della giornata sa **mostrare** un pasto ma non sa proporne uno: legge
# `days.json`, che e' gia' cotto. Al diario serve in piu' il catalogo degli
# alimenti, per sapere in che unita' e' misurata ogni riga.
#
# Il Worker che riceve le annotazioni (tools/diario-worker/) non si chiama piu' da
# questa pagina: /vita e' pubblica, e una pagina pubblica che chiede una chiave per
# scrivere e' il posto sbagliato dove tenerne una. Dal 2026-08-14 si annota da
# Mission Control, che e' dietro login e parla con lo stesso Worker; qui il diario
# si legge soltanto. Il registro resta uno: tools/food/data/food_log.csv.
FOODS_CSV = os.path.join(HERE, "food", "data", "foods.csv")

# Le colonne che il diario usa davvero: nome, unita', e i macro. I 24
# micronutrienti restano fuori — li porta gia' la build vera, per giorno.
CAT_COLS = (("kcal", "k"), ("protein_g", "p"), ("carb_g", "c"),
            ("fiber_g", "fb"), ("fat_g", "ft"))


def build_food_catalog():
    """Il catalogo degli alimenti che la pagina inlina, per l'unita' di misura.

    Prima tornava anche ricette e preset, che servivano al diario quando si
    poteva scrivere da qui. Ora si annota da Mission Control, che ricalcola i
    preset per conto suo dagli stessi CSV: tenerne una seconda copia qui
    significherebbe due elenchi della stessa cosa, e uno dei due indietro.
    """
    import csv as _csv

    cat = {}
    if os.path.exists(FOODS_CSV):
        with open(FOODS_CSV, encoding="utf-8", newline="") as fh:
            for r in _csv.DictReader(fh):
                ref = float(r["ref_qty"] or 1) or 1
                e = {"n": r["name_it"], "u": r["unit"], "g": r["group"]}
                for src, dst in CAT_COLS:
                    # per unita' di misura, non per ref_qty: cosi' la pagina
                    # moltiplica e basta, senza sapere che il CSV e' per 100 g
                    e[dst] = round(float(r[src] or 0) / ref, 4)
                cat[r["id"]] = e

    print(f"  diario: {len(cat)} alimenti")
    return cat


def build_payload(raw):
    """Daily arrays on one shared index, plus the activity list. Nothing is smoothed
    or filled here — the page does its own rolling means so the range switch can
    recompute them over whatever window is on screen."""
    well = sorted(raw["wellness"], key=lambda r: r["id"])
    acts = list(raw["activities"]) + load_backfill()

    d0 = datetime.strptime(well[0]["id"], "%Y-%m-%d").date()
    dN = datetime.strptime(well[-1]["id"], "%Y-%m-%d").date()

    # L'asse arriva fino all'ultimo giorno CON DEL CIBO, non solo fino all'ultimo
    # giorno di Intervals.
    #
    # E' il bug del diario sfasato di un giorno, aperto dal 16/08/2026. Il cibo si
    # annota oggi; le attivita' arrivano da Intervals, che sul calendario wellness
    # puo' fermarsi a ieri. Quando il cibo corre piu' avanti, la sua data cade oltre
    # `n`: `diaryIdxOf` torna null, `diaryLastWithFood` non ci arriva mai perche'
    # parte da n-1, e il popup apre il giorno PRIMA di quello chiesto. In CI non si
    # vedeva perche' li' il sync di Intervals gira sempre prima e la serie arriva a
    # oggi; si vedeva solo a chi buildava `--offline`, cioe' proprio chi ci lavora.
    # Il 22/08/2026 e' scattato per davvero, appena registrata una colazione di oggi.
    #
    # I giorni in piu' hanno wellness a null, che la pagina gia' sa disegnare (le
    # serie si spezzano sui null invece di scavalcarli). Meglio un giorno senza
    # sonno che un giorno di cibo irraggiungibile.
    if os.path.exists(DAYS):
        try:
            with open(DAYS, encoding="utf-8") as fh:
                _giorni = [k for k in json.load(fh) if not k.startswith("_")]
            if _giorni:
                dCibo = datetime.strptime(max(_giorni), "%Y-%m-%d").date()
                if dCibo > dN:
                    print(f"  asse esteso al {dCibo}: il cibo corre {(dCibo - dN).days} "
                          f"giorno/i piu' avanti di Intervals")
                    dN = dCibo
        except (ValueError, json.JSONDecodeError, OSError):
            pass          # un days.json illeggibile non deve impedire la build

    n = (dN - d0).days + 1
    idx = {}
    for r in well:
        d = datetime.strptime(r["id"], "%Y-%m-%d").date()
        idx[r["id"]] = (d - d0).days

    def col(name, conv):
        out = [None] * n
        for r in well:
            i = idx[r["id"]]
            v = r.get(name)
            if v is not None:
                out[i] = conv(v)
        return out

    ctl = col("ctl", r1)
    atl = col("atl", r1)
    load = col("ctlLoad", ri)

    # ---- il carico ricostruito rientra nelle serie ---------------------------
    # `load` viene da Intervals e nel 2022 è zero per 365 giorni di fila, perché su
    # Intervals quell'anno non c'è. Con le attività di Strava rimesse dentro, il
    # carico di quei giorni esiste — e allora CTL e ATL vanno RICALCOLATE, se no la
    # fitness continua a decadere a zero sopra un anno di allenamenti veri.
    #
    # Il ricalcolo usa la solita media esponenziale (42 giorni la CTL, 7 l'ATL). Che
    # sia proprio quella di Intervals non è un'ipotesi: rifacendo i conti dal loro
    # `ctlLoad` si riottengono i loro `ctl` con un errore assoluto mediano di 0,03 su
    # una scala che sta attorno a 95, massimo 1,0. È la stessa formula.
    recon_load = defaultdict(float)
    for a in acts:
        if not a.get("_backfill"):
            continue
        sd = (a.get("start_date_local") or "")[:10]
        if sd in idx:
            recon_load[idx[sd]] += a.get("icu_training_load") or 0.0

    recon_days = sorted(recon_load)
    if recon_days:
        for i, extra in recon_load.items():
            load[i] = int(round((load[i] or 0) + extra))
        rc, ra = food_common.recompute_ctl_atl(load, ctl[0] or 0.0, atl[0] or 0.0)
        for i in range(n):
            ctl[i], atl[i] = r1(rc[i]), r1(ra[i])
        print(f"  carico ricostruito su {len(recon_days)} giorni → CTL/ATL rifatte "
              f"dal {(d0 + timedelta(days=recon_days[0])).isoformat()}")

    # Le fasce da marcare in pagina. Prima si uniscono i giorni ricostruiti che
    # distano meno di 30 giorni, se no un anno diventa novanta etichette.
    spans = []
    for i in recon_days:
        if spans and i - spans[-1][1] <= 30:
            spans[-1][1] = i
        else:
            spans.append([i, i])

    # Poi si tengono solo le fasce dove la ricostruzione è DAVVERO la sostanza del
    # periodo: almeno 45 giorni (la stessa soglia dei buchi) e più di metà del carico
    # ricostruito. Senza questo filtro il 2025, che Intervals ha sincronizzato bene e
    # a cui il backfill aggiunge 18 attività su 489, si prendeva una fascia
    # "carico ricostruito" larga due mesi: overclaim esattamente speculare al buco
    # del 2022, e sbagliato nello stesso modo.
    recon = []
    for a, b in spans:
        if b - a + 1 < 45:
            continue
        tot = sum(load[i] or 0 for i in range(a, b + 1))
        rec = sum(recon_load.get(i, 0.0) for i in range(a, b + 1))
        if tot > 0 and rec / tot >= 0.5:
            recon.append([a, b])
    sleep = col("sleepSecs", lambda v: int(round(v / 60.0)))   # minutes
    score = col("sleepScore", ri)
    hrv = col("hrv", r1)
    rhr = col("restingHR", ri)
    steps = col("steps", ri)
    weight = col("weight", r1)
    bodyfat = col("bodyFat", r1)

    # ctl/atl exist for every single day by construction (Intervals fills the calendar),
    # so "first non-null" would say 2015 for a series that is flat zero until 2019.
    # The honest start is where the load becomes sustained: the first day whose next
    # 28 days carry more than a token amount of it.
    load_i0 = 0
    for i in range(n - 28):
        if sum(load[j] or 0 for j in range(i, i + 28)) > 100:
            load_i0 = i
            break

    # activities -> [dayIdx, sport, movingSecs, metres, gainMetres, load, backfill,
    #                hr, gapCentesimi, tempDecimi]
    # piu' una lista parallela di nomi/id: il popup della giornata apre le attivita'
    # con il loro nome vero e il link a Intervals, e "Morning Ride" non e' un nome.
    #
    # Le tre code servono ai riquadri "passo contro battito": la domanda "come varia
    # la mia capacita' di ossidare grassi" si guarda per ATTIVITA', non per giorno —
    # una giornata con un lungo e una sgambata ha una media che non e' successa. Il
    # passo e' il GAP di Intervals (grade adjusted pace, m/s): senza correzione della
    # pendenza un'uscita in salita e una in piano non sono confrontabili, ed e' tutto
    # il punto. Zero = non misurato; non c'e' nessun caso reale con FC o passo a zero.
    arows, anames, act_days = [], [], set()
    for a in acts:
        sd = (a.get("start_date_local") or "")[:10]
        if not sd or sd not in idx:
            # an activity outside the wellness calendar cannot be placed on the axis
            continue
        i = idx[sd]
        indoor = bool(a.get("trainer")) or a.get("type") in ("VirtualRide", "VirtualRun")
        arows.append([
            i,
            SPORT_OF.get(a.get("type") or "", 3),
            int(a.get("moving_time") or 0),
            int(round(a.get("distance") or 0)),
            int(round(a.get("total_elevation_gain") or 0)),
            int(round(a.get("icu_training_load") or 0)),
            # 1 = attività ricostruita dall'export Strava, carico stimato non misurato
            1 if a.get("_backfill") else 0,
            int(round(a.get("average_heartrate") or 0)),
            int(round((a.get("gap") or 0) * 100)),
            # il termometro dell'orologio, e solo all'aperto: dentro misura il garage
            int(round((a.get("average_temp") or 0) * 10)) if not indoor else 0,
            # [10] le calorie dell'uscita, come le da' Intervals. Servono al diario
            # (ordine #22: «le calorie bruciate e i grammi di carboidrati che
            # dovrebbero essere assunti»). Zero = non misurate — capita sulle
            # attivita' ricostruite dall'export Strava — e in quel caso il diario
            # non scrive uno zero, non scrive niente.
            int(round(a.get("calories") or 0)),
        ])
        anames.append([a.get("name") or "", a.get("id") or "",
                       a.get("strava_id") or ""])
        act_days.add(i)
    order = sorted(range(len(arows)), key=lambda j: arows[j])
    arows = [arows[j] for j in order]
    anames = [anames[j] for j in order]

    # Long runs with no activity at all. 2022 is the big one; the early years have
    # their own. Drawn as shaded "nessun dato" bands instead of being interpolated
    # across, because CTL decaying through a hole looks exactly like detraining.
    gaps, run_start = [], None
    for i in range(n):
        if i in act_days:
            if run_start is not None and i - run_start >= 45:
                gaps.append([run_start, i - 1])
            run_start = None
        elif run_start is None:
            run_start = i
    if run_start is not None and n - run_start >= 45:
        gaps.append([run_start, n - 1])

    def first(a):
        for i, v in enumerate(a):
            if v is not None:
                return i
        return None

    # ---- alimentazione: aggregati giornalieri, se il CSV c'e' ----------------
    # Le colonne diventano array sullo stesso indice giornaliero di tutto il resto,
    # cosi' una serie di cibo e una di allenamento si possono incrociare senza
    # riallineare niente. Se il file manca, i riquadri del cibo semplicemente non
    # compaiono: meglio nessun grafico che un grafico vuoto.
    nutri, nutri_first, nutri_last, _ = csv_blocks(NUTRITION, idx, n, "alimentazione")

    # il modello della flora: stesse colonne -> stesse serie sull'indice giornaliero
    microbes, microbe_first, _, _ = csv_blocks(MICROBES, idx, n, "flora (modello)")

    # il modello metabolico: temperatura al polso, banda FatMax, momento metabolico.
    # Copre l'archivio intero (2015 →) ma a densita' molto diverse per colonna — la
    # temperatura esiste solo nei giorni con un'uscita, `mm` solo dal 2024-08-11 —
    # quindi ogni colonna porta il proprio first/last e ogni riquadro parte da li'.
    metab, metab_first, metab_last, _ = csv_blocks(
        METAB, idx, n, "metabolismo", keep=METAB_COLS)

    flora_foods = []
    if os.path.exists(FLORA_FOODS):
        import csv as _csv
        with open(FLORA_FOODS, encoding="utf-8", newline="") as fh:
            for r in _csv.DictReader(fh):
                flora_foods.append({k: (float(v) if k not in ("food_id", "name") else v)
                                    for k, v in r.items()})
        print(f"  flora x alimenti: {len(flora_foods)} alimenti")

    days_detail = {}
    if os.path.exists(DAYS):
        with open(DAYS, encoding="utf-8") as fh:
            days_detail = json.load(fh)
        print(f"  dettaglio giornaliero: {len(days_detail)} giorni")

    food_catalog = build_food_catalog()

    food_profile = {}
    if os.path.exists(FOOD_PROFILE):
        with open(FOOD_PROFILE, encoding="utf-8") as fh:
            source_profile = json.load(fh)
        # Solo i valori necessari alle barre: niente note o configurazione privata
        # superflua nel payload pubblico.
        food_profile = {k: source_profile.get(k) for k in
                        ("weight_kg", "reference_kcal", "protein_g_per_kg",
                         "rda", "limits")}
        # Il fabbisogno proteico non sta in profile.json: si DERIVA dal peso
        # (`weight_kg * protein_g_per_kg`), e finora quel calcolo viveva solo in
        # food/common.py, cioe' solo lato build. Da quando il diario mostra la
        # percentuale di fabbisogno per pasto (ordine #22) la pagina deve poterlo
        # dividere anche lei, e senza questa riga le proteine sarebbero l'unico
        # nutriente senza percentuale — proprio quello che si guarda per primo.
        if isinstance(food_profile.get("rda"), dict) and source_profile.get("weight_kg"):
            food_profile["rda"] = dict(food_profile["rda"])
            food_profile["rda"]["protein_g"] = round(
                source_profile["weight_kg"] * source_profile.get("protein_g_per_kg", 1.6), 1)

    payload = {
        "built": date.today().isoformat(),
        "nutri": nutri,
        "microbes": microbes,
        "metab": metab,
        "floraFoods": flora_foods,
        "days": days_detail,
        "foodProfile": food_profile,
        # Il catalogo serve ancora: la pagina ci legge l'unita' di misura di ogni
        # alimento. Ricette e preset no — servivano solo ad annotare, e da quando
        # si annota da Mission Control resterebbero nel payload senza che nessuno
        # li apra. Un elenco che nessuno legge e' un elenco che va indietro.
        "foodCat": food_catalog,
        "pulled": raw["pulled"],
        "d0": d0.isoformat(),
        "n": n,
        "sports": SPORTS,
        "gaps": gaps,
        "recon": recon,
        "ctl": ctl, "atl": atl, "load": load,
        "sleep": sleep, "score": score, "hrv": hrv, "rhr": rhr,
        "steps": steps, "weight": weight, "bodyfat": bodyfat,
        "acts": arows,
        "anames": anames,
        "first": {
            "load": load_i0,
            "act": arows[0][0] if arows else 0,
            "sleep": first(sleep), "score": first(score), "hrv": first(hrv),
            "rhr": first(rhr), "steps": first(steps),
            "weight": first(weight), "bodyfat": first(bodyfat),
            **{f"n_{c}": i for c, i in nutri_first.items() if i is not None},
            **{f"m_{c}": i for c, i in microbe_first.items()},
            **{f"mb_{c}": i for c, i in metab_first.items()},
        },
        # dove ogni serie del cibo SMETTE. Il diario si ferma prima di oggi, e un
        # asse che arriva comunque a oggi disegna una settimana di vuoto che si
        # legge come "non ha mangiato" invece che "non l'ha raccontato".
        "last": {**{f"n_{c}": i for c, i in nutri_last.items()},
                 **{f"mb_{c}": i for c, i in metab_last.items()}},
    }
    return payload


# ------------------------------------------------------------------ reporting

def coverage(p):
    """What the payload actually contains, per field and per year. Printed by every
    run and appended to the cumulative report, so a field quietly going empty at the
    source shows up as a step in the history rather than as a blank tile nobody
    thought to look at."""
    d0 = datetime.strptime(p["d0"], "%Y-%m-%d").date()
    lines = []
    lines.append(f"span: {p['d0']} → "
                 f"{(d0 + timedelta(days=p['n'] - 1)).isoformat()}  ({p['n']} giorni)")
    fields = ["ctl", "load", "sleep", "score", "hrv", "rhr", "steps",
              "weight", "bodyfat"]
    for f in fields:
        vals = [v for v in p[f] if v is not None]
        nz = [v for v in vals if v]
        # ctl/atl are filled for the whole calendar by Intervals itself, so they have
        # no "first" entry — their story is the load's, reported on its own row.
        i0 = 0 if f == "ctl" else p["first"].get(f)
        since = (d0 + timedelta(days=i0)).isoformat() if i0 is not None else "—"
        lines.append(f"  {f:9s} {len(vals):5d} valori ({len(nz)} non nulli)  dal {since}")
    # le colonne del metabolismo hanno densita' molto diverse fra loro (la temperatura
    # esiste solo nei giorni con un'uscita, `mm` solo dal 2024-08): riportarle una per
    # una e' l'unico modo di accorgersi che una si e' svuotata alla sorgente.
    for c in ("temp_c", "fatmax_hr", "fatmax_min", "mm", "mm_n"):
        b = (p.get("metab") or {}).get(c)
        if not b:
            lines.append(f"  metab.{c:11s}     — assente")
            continue
        vals = [v for v in b["v"] if v is not None]
        lines.append(f"  metab.{c:11s} {len(vals):5d} valori  "
                     f"dal {(d0 + timedelta(days=b['i0'])).isoformat()} "
                     f"al {(d0 + timedelta(days=b['i0'] + len(b['v']) - 1)).isoformat()}")
    lines.append(f"  {'acts':9s} {len(p['acts']):5d} attività")
    by = defaultdict(int)
    for a in p["acts"]:
        by[(d0 + timedelta(days=a[0])).year] += 1
    lines.append("  attività per anno: " +
                 " ".join(f"{y}:{by[y]}" for y in sorted(by)))
    lines.append(f"  buchi ≥45 giorni senza attività: {len(p['gaps'])} → " +
                 ", ".join(f"{(d0 + timedelta(days=a)).isoformat()}"
                           f"→{(d0 + timedelta(days=b)).isoformat()}"
                           for a, b in p["gaps"][:8]) +
                 (" …" if len(p["gaps"]) > 8 else ""))
    return "\n".join(lines)


def append_report(p, note, wrote):
    """Append, never overwrite: the trend across builds is the evidence."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    head = "" if os.path.exists(REPORT) else (
        "# /vita/cruscotto — report cumulativo dei build\n\n"
        "Ogni run di `tools/build_cruscotto.py` appende qui cosa ha trovato nei dati\n"
        "Intervals.icu e cosa ha scritto. Si aggiunge, non si sovrascrive: la storia\n"
        "è il punto — un campo che smette di arrivare si vede come uno scalino.\n")
    with open(REPORT, "a", encoding="utf-8") as f:
        if head:
            f.write(head)
        f.write(f"\n## {stamp} — {note}\n\n```\n{coverage(p)}\n```\n")
        f.write(f"\npagina: {'scritta' if wrote else 'NON scritta'}"
                f"{f' ({wrote} KB)' if wrote else ''}\n")


# ---------------------------------------------------------------------- page

def highlights():
    """Le tre pagine-racconto, in cima: titolo, tre numeri, l'ultima modifica.

    Nessun grafico qui — hanno le loro pagine per quello, e sotto c'e' una
    colonna di grafici che e' il vero contenuto di /vita. Sono un indice, e un
    indice deve stare in poche righe."""
    out = []
    for t in (vita_trackers.load_gazzaniga(), vita_trackers.load_diario(),
              vita_trackers.load_sogni(), vita_trackers.load_spostamenti()):
        out.append({
            "key": t["key"], "title": t["title"], "href": t["href"],
            "eyebrow": t["eyebrow"], "accent": t["accent"],   # `blurb` non serve piu': il 16/08 e' uscito dalla pagina
            "last": t["last"],
            "stats": [{"v": s["v"], "l": s["l"]} for s in t["stats"]],
        })
    return out


def build_html(p):
    js = json.dumps(p, separators=(",", ":"))
    return TEMPLATE.replace("__DATA__", js).replace("__BUILT__", p["built"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key")
    ap.add_argument("--offline", action="store_true",
                    help="rebuild from tools/.cruscotto_cache.json, no network")
    ap.add_argument("--sync-source", action="store_true",
                    help="pull cache + export food activities, then stop")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--dry-run", action="store_true", help="build but do not write")
    args = ap.parse_args()

    key = None if args.offline else get_api_key(args.api_key)
    raw = pull(key, use_cache=args.offline)
    if args.sync_source:
        export_food_activities(raw)
        return
    p = build_payload(raw)
    p["tracks"] = highlights()
    print()
    print(coverage(p))

    if args.check or args.dry_run:
        append_report(p, "--check" if args.check else "--dry-run", wrote=0)
        print(f"\n(niente scritto; report → {os.path.basename(REPORT)})")
        return

    export_food_activities(raw)
    html = build_html(p)
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        shutil.copyfile(OUT, OUT + ".bak")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"\nwrote {OUT} ({kb} KB)")
    append_report(p, "build", wrote=kb)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vita — Michele Merelli</title>
<meta name="description" content="Undici anni di dati in un pannello solo: carico, forma, sonno, HRV, frequenza a riposo, peso, volume. Da Intervals.icu.">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:url" content="https://micmer-git.github.io/vita/">
<meta property="og:title" content="Vita — Michele Merelli">
<meta property="og:description" content="Carico, forma, sonno, HRV, peso, volume: ogni serie che misuro, in un pannello solo.">
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=VT323&display=swap" rel="stylesheet">
<style>
  :root{
    /* LO STESSO VESTITO DELLA HOME (micmer-git.github.io/): pixel art, quadretti,
       ombre secche, palette Google I/O. Fino al 16/08/2026 questa pagina era scura
       e serif, e sembrava di un altro sito — chiesto da Michele (ordine #10).
       Quello che NON e' cambiato e' la disciplina: due valori qui dentro restano
       MISURATI, non scelti, e `node tools/check_vita.cjs` li rimisura a ogni run.
         --muted  e' il colore di OGNI piede, didascalia, etichetta d'asse e
                  intestazione di tabella: deve stare sopra 4,5:1 sulla scheda.
                  #5f6368 (il grigio I/O) sta a 5,9:1 sul bianco.
         --accent e' l'accento del sito e deve stare a ΔE >= 15 da OGNI slot dei
                  grafici, o si spaccia per una serie di dati. Si chiamava --gold ed
                  era oro: sul bianco NESSUN accento saturo passa piu' quel cancello,
                  perche' i quattro slot si prendono lo spazio cromatico — misurati,
                  i candidati migliori (ocra #a26401, teal #00695c, viola #6a1b9a)
                  stanno fra ΔE 7 e 14. Quindi l'accento e' il nero della home,
                  #202124: ΔE 27,4 dallo slot piu' vicino e 16:1 di contrasto. Non e'
                  una rinuncia, e' come e' fatta la home — li' l'accento sono i
                  riquadri neri con l'ombra secca, e il colore lo portano i FONDI
                  delle schede. Rinominato apposta: una variabile chiamata --gold che
                  contiene nero e' la prossima mezz'ora persa da qualcuno. */
    --bg:#f8f9fa; --paper:#ffffff; --paper-2:#f1f3f4;
    --ink:#202124; --ink-soft:#3c4043; --muted:#5f6368;
    --accent:#202124; --rule:rgba(32,33,36,.30);
    --grid:rgba(32,33,36,.10); --axis:rgba(32,33,36,.30);
    /* Categorical slots 1-4. Dal 17/08/2026 sono i colori LETTERALI della home
       (`tailwind.config` di index.html: io-blue #4285F4, io-red #EA4335,
       io-green #34A853), tranne due scostamenti misurati e voluti:
         --s3 e' #1e8e3e e non #34A853 perche' il verde I/O sta a 2,8:1 sul bianco
              e una linea da 2px sotto 3:1 non e' un oggetto grafico leggibile
              (WCAG 1.4.11). Stessa famiglia, quattro decimi di luminanza in meno.
         --s4 resta viola: il quarto colore della home e' il GIALLO, e il giallo
              I/O sta a 1,7:1 — li' e' un FONDO dietro testo nero, mai un tratto.
              Il giallo torna dov'e' nato, in --io-yellow, e fa da riempimento.
       Il registro dei colori resta uno: `SCH` in pagina legge queste variabili e
       `C` in build_vita.py disegna i PNG con gli stessi valori. */
    --s1:#4285f4; --s2:#ea4335; --s3:#1e8e3e; --s4:#8430ce; --neg:#ea4335;
    --io-yellow:#fbbc04; --io-green:#34a853;
    /* l'ombra secca della home: nessuna sfocatura, e' quella che fa lo stile */
    --neo:4px 4px 0 0 rgba(32,33,36,1); --neo-sm:2px 2px 0 0 rgba(32,33,36,1);
  }
  ::selection{background:var(--io-yellow); color:#000}
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth;max-width:100%;overflow-x:hidden;overflow-x:clip}
  body{
    background:var(--bg); color:var(--ink);
    font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif; font-size:17px; line-height:1.6;
    max-width:1280px; margin:0 auto; padding:44px 20px 90px;
    -webkit-text-size-adjust:100%; width:100%; overflow-x:hidden; overflow-x:clip;
  }
  /* i quadretti della home, che li' stanno solo in cima e poi sfumano */
  body::before{
    content:""; position:fixed; inset:0; pointer-events:none; z-index:-1;
    background-image:
      linear-gradient(to right,rgba(32,33,36,.075) 1px,transparent 1px),
      linear-gradient(to bottom,rgba(32,33,36,.075) 1px,transparent 1px);
    background-size:24px 24px;
    -webkit-mask-image:linear-gradient(to bottom,#000 0,transparent 62vh);
    mask-image:linear-gradient(to bottom,#000 0,transparent 62vh);
  }
  a{color:inherit}
  .mono{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace}
  /* VT323 e' il carattere pixel della home. Va bene grande: sotto i 15px le sue
     aste sottili spariscono, quindi le etichette minute restano mono di sistema. */
  .pixel{font-family:'VT323',ui-monospace,monospace; letter-spacing:.02em}

  /* ---------- hero ---------- */
  header{text-align:center}
  .eyebrow{font-family:'VT323',ui-monospace,monospace; font-size:1.15rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--accent)}
  .eyebrow a{text-decoration:none; border-bottom:1px solid var(--rule)}
  .eyebrow a:hover{color:var(--ink)}
  h1{font-family:'VT323',ui-monospace,monospace; font-size:clamp(3.2rem,12vw,5.6rem); font-weight:400;
    letter-spacing:.01em; line-height:.92; margin:10px 0 6px; text-transform:uppercase;
    display:inline-block; background:var(--paper); color:var(--ink);
    border:3px solid var(--ink); box-shadow:var(--neo); padding:2px 18px 0}
  .sub{color:var(--ink-soft); max-width:36em; margin:16px auto 0;
    font-size:1.08rem}

  /* ---------- headline numbers ---------- */
  .headline-stats{max-width:1000px; margin:30px auto 0; display:grid; gap:16px}
  .headline-group{border-top:1px solid var(--rule); padding-top:10px}
  .headline-label{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem;
    letter-spacing:.17em; text-transform:uppercase; color:var(--accent); text-align:center;
    margin-bottom:10px}
  .totals{display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
    gap:16px 10px; max-width:1000px}
  .total{text-align:center}
  .total .n{font-family:'VT323',ui-monospace,monospace; font-size:1.95rem; font-weight:700; color:var(--accent);
    font-variant-numeric:tabular-nums; line-height:1.1}
  .total .l{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.7rem; letter-spacing:.11em;
    text-transform:uppercase; color:var(--muted); margin-top:4px; overflow-wrap:anywhere}
  .total{border:0;background:transparent;color:inherit;font:inherit;padding:5px;min-width:0}
  button.total{cursor:pointer;border-radius:7px}
  button.total:hover{background:var(--paper);outline:1px solid var(--rule)}
  .total .d{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;font-size:.68rem;margin-top:3px;color:var(--ink-soft)}
  .total .d.up{color:var(--s3)} .total .d.down{color:var(--neg)}
  .fortnight{margin:15px auto 0;max-width:900px;text-align:center;color:var(--muted);font-size:.9rem}

  /* ---------- correlatore libero ---------- */
  .compare{max-width:1000px; margin:18px auto 22px; border:2px solid var(--ink);
    border-radius:0; box-shadow:var(--neo-sm); background:var(--paper);
    padding:16px 18px 13px}
  .compare-controls{display:flex; align-items:end; justify-content:center; flex-wrap:wrap;
    gap:10px 14px}
  .compare-controls label{display:grid; gap:4px; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted)}
  .compare-controls select{min-width:180px; max-width:280px; border:1px solid var(--rule);
    border-radius:6px; background:var(--paper-2); color:var(--ink); padding:7px 28px 7px 9px;
    font:500 .84rem ui-monospace,'SFMono-Regular',Menlo,monospace}
  .compare-controls select:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  .compare-body{display:grid; grid-template-columns:minmax(0,1fr) 160px; gap:14px;
    align-items:center; margin-top:14px}
  .compare-plot{min-height:280px}
  .compare-plot svg{display:block; width:100%; height:280px; overflow:hidden}
  .compare-result{border-left:1px solid var(--rule); padding-left:14px}
  .compare-result b{display:block; font:700 2.15rem 'VT323',ui-monospace,monospace; color:var(--accent)}
  .compare-result span{display:block; font:500 .72rem ui-monospace,'SFMono-Regular',Menlo,monospace;
    color:var(--ink-soft); margin:3px 0}
  .compare-result p{font-size:.87rem; line-height:1.45; color:var(--muted); margin-top:10px}
  /* i dieci preset: pastiglie, non un menu a tendina. Il titolo di ognuna e' la
     TESI, non i nomi delle due serie — "il caldo si paga il mattino dopo" dice
     perche' guardarla, "Heat strain contro FC a riposo" no. */
  .cx-presets{display:flex; flex-wrap:wrap; gap:6px; justify-content:center;
    margin:0 0 12px}
  .cx-presets button{white-space:nowrap}
  /* Sotto i 640 le pastiglie non vanno a capo: scorrono. Andando a capo, tre
     pastiglie facevano tre righe e spingevano il grafico sotto la piega proprio
     mentre lo si stava scegliendo. */
  @media(max-width:640px){
    .cx-presets{flex-wrap:nowrap; overflow-x:auto; justify-content:flex-start;
      scroll-snap-type:x proximity; -webkit-overflow-scrolling:touch;
      padding-bottom:4px; margin-left:-4px; margin-right:-4px; padding-left:4px}
    .cx-presets button{flex:none; scroll-snap-align:start}
  }
  .cx-presets button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem;
    letter-spacing:.05em; color:var(--ink-soft); background:transparent; cursor:pointer;
    border:1px solid var(--rule); border-radius:999px; padding:5px 11px; line-height:1.3}
  .cx-presets button:hover{border-color:var(--accent); color:var(--ink)}
  .cx-presets button[aria-pressed="true"]{border-color:var(--accent); color:var(--paper);
    background:var(--accent)}
  .cx-presets button.cx-add{border-style:dashed}
  .cx-presets button i{font-style:normal; opacity:.55; margin-left:6px}
  /* TRE PASTIGLIE A SCHERMO, NON TREDICI (17/08/2026, Michele: "ci sono un sacco di
     bottoni, c'e' un casino di test... qualcosa di un pochettino piu' curato e piu'
     compatto"). Le altre sette restano — sono il risultato del setaccio su 2.958
     combinazioni e buttarle sarebbe buttare il lavoro — ma dietro un bottone solo.
     Sono NASCOSTE, non smontate: restano nel DOM, nel Tab e nella ricerca di pagina,
     e la pastiglia attiva riapre il gruppo da sola se sta li' dentro. */
  .cx-presets .cx-hid{display:none}
  .cx-presets[data-open="1"] .cx-hid{display:inline-block}
  .cx-presets button.cx-tog{border-style:dotted; color:var(--muted)}
  .cx-presets button.cx-tog:hover{color:var(--ink)}
  .cx-presets button.cx-own{border-color:var(--accent)}
  /* i quattro menu a tendina: la strada lunga, e quindi chiusa. Chi arriva qui vuole
     leggere una tesi, non compilare un modulo a quattro campi. */
  .cx-pick{max-width:1000px; margin:0 auto 12px}
  .cx-pick > summary{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted);
    cursor:pointer; list-style:none; text-align:center}
  .cx-pick > summary::-webkit-details-marker{display:none}
  .cx-pick > summary::before{content:"▸ "}
  .cx-pick[open] > summary::before{content:"▾ "}
  .cx-pick > summary:hover{color:var(--ink)}
  .cx-pick .compare-controls{margin-top:11px}
  .cx-claim{max-width:70ch; margin:0 auto 12px; text-align:center; font-size:1rem;
    line-height:1.55; color:var(--ink-soft)}
  .cx-claim:empty{display:none}
  .cx-claim b{color:var(--accent); font-weight:500}
  .cx-claim em{color:var(--muted); font-style:italic}
  .compare-note{font-size:.85rem; line-height:1.5; color:var(--muted); margin-top:9px;
    text-align:center}
  /* L'avviso "e' solo trend" non e' un errore: e' il risultato. Prende l'arancio
     degli avvisi, quello di conferma resta muto — una conferma non deve gridare. */
  .compare-result .cmp-warn{color:var(--s2); border-left:2px solid var(--s2);
    padding-left:8px; margin-top:9px; font-size:.82rem}
  .compare-result .cmp-ok{color:var(--ink-soft); margin-top:9px; font-size:.82rem}
  .compare-result .cmp-warn strong{color:var(--s2); font-weight:600}

  /* ---------- range control ---------- */
  /* Due gruppi di comandi sulla stessa riga: la finestra temporale e la forma
     della vista. Stessa classe di bottone perche' sono la stessa cosa — due scelte
     che ridisegnano tutto — e due stili diversi avrebbero solo insinuato che una
     conta meno dell'altra. */
  /* LA BARRA RESTA APPESA IN CIMA (17/08/2026, Michele: "la divisione fra due anni e
     un anno sempre visibile come toggle anche se scrollo in basso"). La finestra
     temporale governa TUTTI i quaranta riquadri insieme: doverla andare a ricercare
     tremila pixel piu' su e' il motivo per cui la si cambiava una volta sola e poi si
     scorreva con quella. Il fondo e' quasi opaco apposta: sotto ci scorrono grafici, e
     una barra trasparente sopra un disegno in movimento non e' leggera, e' illeggibile.
     --bar-h e' l'altezza che questa barra si prende: la legge la striscia congelata
     della ridgeline per non finirci sotto. */
  :root{--bar-h:54px}
  .controls{position:sticky; top:0; z-index:8;
    display:flex; gap:8px 18px; justify-content:center; align-items:center;
    flex-wrap:wrap; margin:30px -20px 8px; padding:9px 20px;
    background:rgba(248,249,250,.95);
    -webkit-backdrop-filter:blur(7px); backdrop-filter:blur(7px);
    border-bottom:2px solid var(--ink)}
  .controls .ranges{margin:0}
  .viewsw{border-left:2px solid var(--ink); padding-left:18px}
  .ranges{display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:30px 0 6px}
  .ranges button{
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.78rem; letter-spacing:.12em;
    text-transform:uppercase; padding:8px 16px; border-radius:999px; cursor:pointer;
    background:transparent; border:1px solid var(--rule); color:var(--ink-soft);
    transition:border-color .15s,color .15s,background .15s;
  }
  .ranges button:hover{border-color:var(--accent); color:var(--ink)}
  .ranges button[aria-pressed="true"]{border-color:var(--accent); color:var(--bg);
    background:var(--accent); font-weight:600}
  .ranges button:focus-visible{outline:2px solid var(--accent); outline-offset:3px}

  /* ---------- vista compatta: ridgeline ----------
     La colonna estesa e' nascosta, non smontata: la compatta e' un modo in piu' di
     leggere le stesse serie, non un'altra pagina. Il fondo di default (nessun
     data-view sul body) e' la vista estesa, cosi' se lo script non parte resta in
     piedi quella che c'era prima invece di una sezione vuota. */
  #compact{display:none}
  body[data-view="compatta"] #compact{display:block}
  body[data-view="compatta"] .panel,
  body[data-view="compatta"] h2.band,
  body[data-view="compatta"] .band-sub{display:none}
  .cx-note{text-align:left; color:var(--muted); font-size:.92rem;
    max-width:56em; margin:14px auto 0; line-height:1.55; display:flex; gap:10px;
    align-items:baseline; flex-wrap:wrap}
  /* i gesti stanno accanto ai comandi, non in un paragrafo tre schermate piu' su */
  .cx-note .cx-gesti{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.74rem; letter-spacing:.04em; color:var(--muted);
    border-left:1px solid var(--rule); padding-left:10px}
  .cx-note .cx-gesti b{color:var(--ink-soft); font-weight:600}
  @media(max-width:640px){ .cx-note .cx-gesti{border-left:0; padding-left:0} }
  .cx-note strong{color:var(--ink-soft); font-weight:500}
  .cx-wrap{display:grid; grid-template-columns:minmax(0,1fr) 214px; gap:14px;
    align-items:start; margin-top:14px}
  .cx-main{min-width:0; background:var(--paper); border:2px solid var(--ink);
    border-radius:0; box-shadow:var(--neo-sm); padding:0 13px 9px}
  /* Le corsie congelate restano appiccicate in cima al pannello mentre il resto
     scorre: e' l'unico modo per confrontare una serie con una che sta ottocento
     pixel piu' in basso senza tenerla a memoria.
     Ma la striscia NON deve leggersi come un riquadro dentro il riquadro
     (2026-08-11: "maybe a little more transparent not big box"): niente bordo,
     niente intestazione su una riga propria, fondo velato invece che pieno e una
     sfumatura al posto del filetto. Il fondo resta comunque quasi opaco — sotto ci
     scorrono le corsie, e una striscia appiccicata trasparente sopra un disegno in
     movimento non e' leggera, e' illeggibile. */
  .cx-pin{position:sticky; top:var(--bar-h); z-index:4; background:rgba(255,255,255,.94);
    -webkit-backdrop-filter:blur(4px); backdrop-filter:blur(4px);
    box-shadow:0 7px 10px -9px rgba(32,33,36,.5); margin:0 -13px; padding:5px 13px 4px}
  .cx-pin.off{display:none}
  .cx-pin-top{display:flex; align-items:center; gap:9px; flex-wrap:wrap}
  .cx-pin-h{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--accent); opacity:.85}
  .cx-chips{display:flex; gap:5px; flex-wrap:wrap}
  .cx-chip{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.06em;
    padding:3px 9px; border-radius:999px; cursor:pointer; background:transparent;
    border:1px solid var(--rule); color:var(--ink-soft)}
  .cx-chip:hover{border-color:var(--accent); color:var(--ink)}
  .cx-chip:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  .cx-plot{padding-top:9px}
  .cx-plot rect:focus-visible,.cx-pin-plot rect:focus-visible{outline:2px solid var(--accent);
    outline-offset:-2px}
  .cx-foot{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.05em;
    color:var(--muted); margin-top:5px; line-height:1.5}
  .cx-rail{position:sticky; top:calc(var(--bar-h) + 8px);
    max-height:calc(100vh - var(--bar-h) - 20px); overflow:auto;
    background:var(--paper); border:2px solid var(--ink); border-radius:0;
    box-shadow:var(--neo-sm); padding:9px 10px 11px}
  /* I due comandi che governano gli interruttori stanno SOPRA gli interruttori, non
     in una didascalia: "somma" cambia cosa fa il click successivo, e un modo che non
     si vede mentre si clicca non esiste. */
  .cx-rail-h{display:flex; gap:5px; margin-bottom:8px}
  .cx-rail-h button{flex:1; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem;
    letter-spacing:.08em; padding:3px 6px; border-radius:4px; cursor:pointer;
    background:transparent; border:1px solid var(--rule); color:var(--ink-soft)}
  .cx-rail-h button:hover{border-color:var(--accent); color:var(--ink)}
  .cx-rail-h button[aria-pressed="true"]{border-color:var(--accent); background:var(--accent);
    color:var(--bg); font-weight:600}
  .cx-rail-h button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  .cx-grp{margin-bottom:9px}
  .cx-grp-h{font-family:'Plus Jakarta Sans',system-ui,sans-serif; font-weight:800; font-size:.72rem; letter-spacing:.15em;
    text-transform:uppercase; color:var(--accent); margin-bottom:4px}
  /* la voce isolata e' l'unica accesa: si marca, o "isola" e "ho spento tutto il
     resto a mano" hanno lo stesso aspetto */
  .cx-sw[data-iso="1"]{border-color:var(--accent); color:var(--ink)}
  .cx-sw{display:flex; align-items:center; gap:6px; width:100%; text-align:left;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem; letter-spacing:.02em;
    padding:4px 5px; border-radius:4px; cursor:pointer; background:transparent;
    border:1px solid transparent; color:var(--ink-soft);
    transition:color .15s,border-color .15s}
  .cx-sw::before{content:""; width:9px; height:9px; border-radius:2px; flex:none;
    background:var(--c,var(--muted))}
  .cx-sw[aria-pressed="false"]{color:var(--muted)}
  .cx-sw[aria-pressed="false"]::before{background:transparent;
    box-shadow:inset 0 0 0 1px var(--muted)}
  .cx-sw:hover{border-color:var(--rule); color:var(--ink)}
  .cx-sw:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  /* Sotto i 720px la colonna di interruttori non ci sta accanto al grafico: diventa
     una riga di chip sopra il pannello, scorrevole in orizzontale. */
  @media(max-width:720px){
    .cx-wrap{grid-template-columns:1fr}
    .cx-rail{position:static; order:-1; max-height:none; display:flex; gap:6px;
      flex-wrap:nowrap; overflow-x:auto; padding:8px 9px}
    .cx-rail-h{margin:0; flex:none}
    .cx-rail-h button{flex:none; white-space:nowrap; border-radius:999px}
    .cx-grp{margin:0; display:flex; align-items:center; gap:5px; flex:none}
    .cx-grp-h{margin:0 3px 0 0; white-space:nowrap}
    .cx-sw{width:auto; white-space:nowrap; border-color:var(--rule);
      border-radius:999px; padding:3px 9px}
  }

  /* ---------- la colonna di grafici ----------
     Uno sopra l'altro, non a griglia: cosi' tutti condividono lo stesso asse x e
     l'occhio puo' scendere lungo la pagina confrontando lo stesso mese fra serie
     diverse — che e' l'unica cosa che una griglia di riquadri non lascia fare.
     Il prezzo e' l'altezza, quindi ogni riquadro e' basso e il titolo, il numero
     di oggi e il grafico stanno sulla stessa riga dove c'e' spazio. */
  /* UNA COLONNA SUL TELEFONO, DUE SUL PORTATILE (18/08/2026, Michele: «si puo'
     migliorare quantita' di dati mostrati in un dato schermo Y, richiede troppo
     scroll»). Il motivo per cui era una colonna sola resta vero solo dentro la
     colonna: l'occhio scende confrontando lo stesso mese fra serie diverse. Con due
     colonne quel confronto vale ancora per le sei coppie verticali, e si dimezza
     l'altezza della pagina.
     La soglia e' 1080 e non 900: sotto, ogni colonna sta a ~430px e il riquadro —
     che ha 180px di intestazione a sinistra — lascerebbe 250px al disegno, cioe' 31
     per ottavo. I riquadri `wide` (fitness e fatica, temperatura, FatMax, momento
     metabolico) restano larghi: hanno una banda o due serie, e stretti non si
     leggono. */
  .panel{display:grid; grid-template-columns:minmax(0,1fr); gap:12px; margin:22px 0 0}
  @media(min-width:1080px){
    .panel{grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px}
    .tile.wide{grid-column:1/-1}
  }
  /* la sezione: e' un contenitore, non un riquadro. Serve solo a poterla nascondere
     tutta insieme quando si sceglie un tema. */
  .sec{display:block}
  .secsel{display:flex; align-items:center; gap:7px}
  .secsel span{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.66rem;
    letter-spacing:.12em; text-transform:uppercase; color:var(--muted)}
  .secsel select{border:2px solid var(--ink); border-radius:0; background:var(--paper);
    color:var(--ink); padding:5px 8px;
    font:600 .74rem ui-monospace,'SFMono-Regular',Menlo,monospace; cursor:pointer}
  .secsel select:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  /* Il riquadro e' una SCHEDA DELLA HOME: filetto nero da 2px, spigolo vivo, ombra
     secca. Prima era un rettangolo bianco con un bordo al 20 % e l'angolo stondato —
     onesto ma anonimo, e infatti dal telefono la pagina non sembrava di questo sito
     (Michele, 17/08/2026: "il background e i colori piu' vicini all'indice"). */
  .tile{
    /* Il fondo lascia passare i quadretti della pagina: Michele, 17/08, «grafici in bg
       piu' trasparenti». Non trasparente e basta — sotto un grafico serve comunque un
       piano chiaro, o le linee sottili si perdono sul reticolo. */
    position:relative; background:color-mix(in srgb, var(--paper) 74%, transparent);
    border:2px solid var(--ink);
    border-radius:0; box-shadow:var(--neo-sm);
    padding:10px 14px 8px; transition:box-shadow .16s,transform .16s,background .16s;
    min-width:0; display:grid; grid-template-columns:180px 1fr; gap:0 16px;
    align-items:center;
  }
  .tile:hover{border-color:var(--ink); background:var(--paper-2);
    box-shadow:var(--neo); transform:translate(-1px,-1px)}
  .t-side{min-width:0}
  .t-head{display:flex; align-items:baseline; gap:8px; flex-wrap:wrap}
  /* La pastiglia di provenienza. E' la terza regola di casa resa visibile: un numero
     misurato e uno ricostruito da un modello non si disegnano uguali. Prima lo diceva
     `dataNote`, con sette formulazioni diverse per tre concetti, e solo su 9 riquadri
     su 42. Ora e' un vocabolario chiuso, obbligatorio, e la stessa parola vuol sempre
     dire la stessa cosa. Non c'e' colore nuovo: sono gli slot dei grafici. */
  .t-src{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem;
    letter-spacing:.13em; text-transform:uppercase; font-weight:600; padding:2px 7px;
    border-radius:999px; border:1px solid currentColor; opacity:.85; white-space:nowrap;
    align-self:center; cursor:pointer; background:none}
  .t-src[data-src="misurato"]{color:var(--s3)}
  .t-src[data-src="ricostruito"]{color:var(--s4)}
  .t-src[data-src="modello"]{color:var(--s1)}
  .t-src[data-src="stima"]{color:var(--s2)}
  .t-src:hover,.t-src:focus-visible{opacity:1}
  .t-title{font-family:'VT323',ui-monospace,monospace; font-size:1.55rem; font-weight:600;
    letter-spacing:.02em; line-height:1.2}
  .t-now{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:1.3rem; font-weight:600;
    font-variant-numeric:tabular-nums; color:var(--accent); line-height:1.15; margin-top:3px}
  .t-now small{display:block; font-size:.68rem; letter-spacing:.08em;
    text-transform:uppercase; color:var(--muted); font-weight:400; margin-top:1px}
  .t-legend{display:flex; gap:9px; flex-wrap:wrap; margin:3px 0 0;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.05em;
    text-transform:uppercase; color:var(--ink-soft)}
  .t-legend i{display:inline-block; width:8px; height:8px; border-radius:2px;
    margin-right:4px; vertical-align:-1px}
  /* le leve dell'indice microbiota: l'emoji dice quale, il numero quanto e' tirata */
  .t-shift{display:flex; gap:11px; flex-wrap:wrap; margin-top:5px; font-size:.95rem}
  .t-shift b{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.8rem; font-weight:600}
  /* La parola accanto all'emoji. Prima stava solo dentro `title=`, e su un telefono
     non c'e' hover: quel testo non e' mai comparso a nessuno. */
  .t-shift .sh-l{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted); font-style:normal}
  svg.plot{width:100%; height:auto; display:block; touch-action:pan-y; overflow:hidden}
  /* La riga di sotto: provenienza della finestra a sinistra, «dati» a destra, sullo
     stesso rigo. Aperto, «dati» si riprende la larghezza intera. */
  .t-bottom{grid-column:1/-1; display:flex; flex-wrap:wrap; align-items:baseline;
    justify-content:space-between; gap:2px 12px; margin-top:3px}
  details.data[open]{flex:1 0 100%}
  .t-foot{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.05em;
    color:var(--muted); margin-top:0; line-height:1.45; min-width:0}
  .t-empty{font-style:italic; color:var(--muted); font-size:.92rem; padding:14px 0;
    text-align:center}

  /* ---------- data fallback ---------- */
  details.data{margin-top:0; min-width:0}
  details.data summary{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted); cursor:pointer;
    list-style:none}
  details.data summary::-webkit-details-marker{display:none}
  details.data summary::before{content:"▸ "; }
  details.data[open] summary::before{content:"▾ "; }
  details.data summary:hover{color:var(--ink-soft)}
  /* la didascalia sta qui dentro, non sotto il titolo: si legge quando si vuole */
  .d-cap{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.7rem; letter-spacing:.05em;
    color:var(--ink-soft); margin:6px 0 0; line-height:1.5}
  .d-cap:empty{display:none}
  .d-cap b{color:var(--muted); font-weight:500}
  /* la nota di metodo: piu' lunga, quindi corpo di testo e non monospazio */
  .d-note{display:block; margin-top:7px; font-family:'Plus Jakarta Sans',system-ui,sans-serif;
    font-size:.96rem; letter-spacing:0; line-height:1.55; color:var(--ink-soft);
    border-left:2px solid var(--rule); padding-left:11px}
  table.fallback{width:100%; border-collapse:collapse; margin-top:6px; font-size:.72rem;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-variant-numeric:tabular-nums}
  table.fallback th,table.fallback td{text-align:right; padding:2px 0 2px 8px;
    border-bottom:1px solid rgba(32,33,36,.14); color:var(--ink-soft); white-space:nowrap}
  table.fallback th:first-child,table.fallback td:first-child{text-align:left; padding-left:0}
  table.fallback th{color:var(--muted); font-weight:500}

  /* ---------- il popup della giornata ---------- */
  .sheet{position:fixed; inset:0; z-index:20; display:none; background:rgba(32,33,36,.55);
    backdrop-filter:blur(2px); padding:4vh 14px; overflow-y:auto}
  .sheet.on{display:block}
  .sheet-in{position:relative; max-width:760px; margin:0 auto; background:var(--paper);
    border:2px solid var(--ink); border-radius:0; padding:20px 22px 24px;
    box-shadow:6px 6px 0 0 rgba(32,33,36,1)}
  .sheet h3{font-family:'VT323',ui-monospace,monospace; font-size:1.95rem; font-weight:700; margin:0}
  .sheet .when{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--accent)}
  .sheet-x{position:absolute; top:12px; right:12px; background:none; border:0; cursor:pointer;
    color:var(--muted); font-size:1.5rem; line-height:1; padding:4px 8px}
  .sheet-x:hover{color:var(--ink)}
  .sheet-hd{padding-right:34px}
  .sheet h4{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--accent); font-weight:600; margin:20px 0 7px;
    border-top:1px solid var(--rule); padding-top:11px}
  .kv{display:grid; grid-template-columns:repeat(auto-fit,minmax(94px,1fr)); gap:10px 14px}
  .kv div b{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.95rem; color:var(--ink);
    font-variant-numeric:tabular-nums; display:block}
  .kv div span{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.65rem; letter-spacing:.08em;
    text-transform:uppercase; color:var(--muted)}
  .acts li{list-style:none; display:flex; justify-content:space-between; gap:12px;
    padding:6px 0; border-bottom:1px solid rgba(32,33,36,.14); flex-wrap:wrap}
  .acts a{color:var(--ink); text-decoration:none; border-bottom:1px solid var(--rule)}
  .acts a:hover{color:var(--accent)}
  .acts em{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.76rem; color:var(--muted);
    font-style:normal; white-space:nowrap}
  .meal{margin-bottom:9px}
  .meal .mname{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.12em;
    text-transform:uppercase; color:var(--ink-soft)}
  .meal ul{list-style:none; margin-top:3px}
  .meal li{display:flex; justify-content:space-between; gap:10px; font-size:.94rem;
    color:var(--ink-soft); padding:1px 0}
  .meal li i{font-style:normal; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.78rem;
    color:var(--muted); white-space:nowrap}
  .meal li.asm{opacity:.62}
  .meal li.asm::after{content:" ricostruito"; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.5rem; letter-spacing:.1em; text-transform:uppercase; color:var(--muted)}
  /* Il pasto si apre: in testa i suoi totali, dentro le voci e le percentuali.
     Chiuso di default — «se schiaccio vedo i singoli contributi» — cosi' la
     giornata si legge come cinque righe invece che come trenta. */
  details.meal>summary{list-style:none; cursor:pointer; display:flex; gap:10px;
    justify-content:space-between; align-items:baseline; padding:2px 0;
    border-bottom:1px solid rgba(32,33,36,.10)}
  details.meal>summary::-webkit-details-marker{display:none}
  details.meal>summary .mname::before{content:"▸ "}
  details.meal[open]>summary .mname::before{content:"▾ "}
  details.meal>summary em{font-style:normal; white-space:nowrap;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.76rem;
    color:var(--muted); font-variant-numeric:tabular-nums}
  /* la ricetta come sotto-gruppo delle sue voci, col proprio subtotale */
  .mrec{margin:5px 0 2px}
  .mrec>b{display:flex; justify-content:space-between; gap:10px; font-weight:500;
    font-size:.82rem; color:var(--ink-soft)}
  .mrec>b s{text-decoration:none; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.74rem; color:var(--muted); white-space:nowrap}
  .mrec ul{margin-left:11px; border-left:1px solid rgba(32,33,36,.13); padding-left:8px}
  /* La ripartizione dei macro come UNA striscia sola (ordine #27): tre blocchi
     larghi quanto la loro quota di energia. Si guarda come si guarda una torta,
     senza leggere tre numeri e sommarli con l'occhio. I colori sono quelli delle
     serie, cosi' proteine e carboidrati qui e nei grafici sono la stessa cosa. */
  .macro-striscia{display:flex; height:18px; border-radius:99px; overflow:hidden;
    margin:7px 0 2px; background:rgba(32,33,36,.06)}
  .macro-striscia b{display:flex; align-items:center; justify-content:center;
    font:500 .62rem ui-monospace,'SFMono-Regular',Menlo,monospace; color:var(--paper);
    min-width:0; overflow:hidden; white-space:nowrap}
  .macro-striscia b.p{background:var(--s1)}
  .macro-striscia b.c{background:var(--s2)}
  .macro-striscia b.g{background:var(--s4)}
  .mdens{margin-top:7px}
  .bar.dens{grid-template-columns:96px 1fr 46px 40px}
  .bar.dens s{text-decoration:none; text-align:right; color:var(--muted);
    font-variant-numeric:tabular-nums}
  .bars{display:grid; gap:4px}
  .bar{display:grid; grid-template-columns:96px 1fr 46px; gap:9px; align-items:center;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.74rem; color:var(--ink-soft)}
  .bar u{text-decoration:none; color:var(--muted)}
  .bar div{height:7px; border-radius:99px; background:rgba(32,33,36,.09); overflow:hidden}
  .bar div i{display:block; height:100%; border-radius:99px}
  .bar b{text-align:right; color:var(--ink); font-variant-numeric:tabular-nums;
    font-weight:500}
  .insight-list .bar{grid-template-columns:minmax(0,1fr) auto; border-bottom:1px solid rgba(32,33,36,.14);
    padding:7px 0; gap:4px 12px}
  .insight-list .bar b{min-width:118px; white-space:nowrap}
  .insight-list .bar .target-track{display:block; position:relative; grid-column:1/-1;
    width:100%; height:9px; overflow:visible; background:rgba(32,33,36,.09)}
  .insight-list .bar .target-track i{transition:width .18s ease}
  .insight-list .bar .target-track mark{position:absolute; top:-3px; bottom:-3px; width:2px;
    padding:0; background:var(--ink); box-shadow:0 0 0 1px rgba(255,255,255,.85)}
  .insight-list .bar small{grid-column:1/-1; color:var(--muted); font-size:.64rem;
    letter-spacing:.04em; text-align:right}
  .insight-list .bar.sel{background:rgba(251,188,4,.18); margin:0 -9px;
    padding-left:9px; padding-right:9px; border-left:2px solid var(--accent)}
  .insight-chart{margin:13px 0 8px; border:2px solid var(--ink); border-radius:0;
    background:var(--paper-2); padding:8px 9px 6px; overflow:hidden}
  .insight-chart svg{display:block; width:100%; height:auto; overflow:hidden}
  .insight-chart .legend{display:flex; justify-content:space-between; gap:12px;
    font:500 .65rem ui-monospace,'SFMono-Regular',Menlo,monospace; letter-spacing:.07em; color:var(--muted)}
  .food-intake{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px 14px}
  .food-intake .food-row{display:grid; grid-template-columns:minmax(0,1fr) auto;
    gap:1px 9px; padding:6px 0; border-bottom:1px solid rgba(32,33,36,.14)}
  .food-intake .food-row span{min-width:0; color:var(--ink-soft); font-size:.87rem;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
  .food-intake .food-row b{font:600 .78rem ui-monospace,'SFMono-Regular',Menlo,monospace; color:var(--ink);
    white-space:nowrap; font-variant-numeric:tabular-nums}
  .food-intake .food-row small{grid-column:1/-1; font:500 .61rem ui-monospace,'SFMono-Regular',Menlo,monospace;
    color:var(--muted); letter-spacing:.04em}
  .hint{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.66rem; letter-spacing:.08em;
    color:var(--muted); text-align:center; margin-top:9px}

  /* ---------- il diario: la giornata sfogliabile e annotabile ---------- */
  /* ---------- l'opinione del coach ----------
     Sta in cima e non in fondo apposta: e' la sola superficie della pagina che
     mette insieme tavola, motore e gamba in una lettura sola, e chi apre /vita
     nove volte su dieci vuole quella, non ventisette grafici. La scheda dice il
     verdetto; il rapporto intero e' dietro il bottone. */
  .coach-card{margin:26px 0 0; border:2px solid var(--ink); border-left:8px solid var(--io-yellow);
    border-radius:0; box-shadow:var(--neo); background:var(--paper); padding:17px 20px 18px}
  .coach-k{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.2em;
    text-transform:uppercase; color:var(--muted)}
  .coach-card h2{font-family:'VT323',ui-monospace,monospace; font-size:1.62rem; font-weight:700;
    letter-spacing:.01em; margin:3px 0 6px}
  .coach-lead{font-size:1.08rem; line-height:1.6; color:var(--ink-soft); max-width:74ch;
    margin:0 0 12px}
  .coach-lead b{color:var(--accent); font-weight:500}
  .coach-card button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.75rem;
    letter-spacing:.15em; text-transform:uppercase; color:var(--ink);
    background:var(--paper); border:1px solid var(--accent); border-radius:99px;
    padding:9px 20px; cursor:pointer; transition:background .16s,color .16s}
  .coach-card button:hover{background:var(--accent); color:#fff}
  /* il rapporto dentro il pannello */
  .cr-when{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--muted); padding-right:34px}
  .cr-verdict{font-size:1.06rem; line-height:1.62; margin:10px 0 4px; color:var(--ink)}
  .cr-verdict b{color:var(--accent); font-weight:500}
  .cr-sec{margin:24px 0 0; border-top:1px solid var(--rule); padding-top:15px}
  .cr-sec > h4{font-family:'VT323',ui-monospace,monospace; font-size:1.02rem; font-weight:700; margin:0 0 2px}
  .cr-sec > p.cr-sub{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted); margin:0 0 12px}
  .cr-item{margin:0 0 15px; padding-left:13px; border-left:2px solid var(--rule)}
  .cr-item.hot{border-left-color:var(--accent)}
  .cr-item.nil{border-left-color:var(--rule); opacity:.92}
  .cr-item h5{font-size:1rem; font-weight:500; margin:0 0 3px; color:var(--ink);
    font-family:'Plus Jakarta Sans',system-ui,sans-serif; line-height:1.35}
  .cr-item p{margin:0; font-size:.92rem; line-height:1.58; color:var(--ink-soft)}
  .cr-num{display:block; margin-top:5px; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.7rem; letter-spacing:.08em; color:var(--muted)}
  .cr-num b{color:var(--accent); font-weight:500}
  .cr-do{display:block; margin-top:6px; font-size:.9rem; line-height:1.5; color:var(--ink)}
  .cr-do::before{content:"→ "; color:var(--accent)}
  .cr-limits{margin:24px 0 0; border-top:1px solid var(--rule); padding-top:14px;
    font-size:.86rem; line-height:1.55; color:var(--muted)}
  .cr-limits h4{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--muted); margin:0 0 7px}
  .cr-limits li{margin:0 0 5px}
  .diary-open{display:flex; align-items:center; justify-content:center; gap:11px;
    flex-wrap:wrap; margin:16px 0 0}
  .diary-open button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.75rem;
    letter-spacing:.15em; text-transform:uppercase; color:var(--ink);
    background:var(--paper); border:1px solid var(--accent); border-radius:99px;
    padding:9px 20px; cursor:pointer; transition:background .16s,color .16s}
  .diary-open button:hover{background:var(--accent); color:#fff}
  .diary-open span{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.66rem;
    letter-spacing:.08em; color:var(--muted)}
  /* il selettore del periodo, e le due tabelle che ha portato con se' */
  .dper{display:flex; gap:7px; align-items:baseline; flex-wrap:wrap; margin:12px 0 4px}
  .dper button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem;
    letter-spacing:.08em; text-transform:uppercase; padding:5px 12px; cursor:pointer;
    background:var(--paper); color:var(--muted); border:2px solid var(--rule); border-radius:0}
  .dper button.on{background:var(--ink); color:var(--paper); border-color:var(--ink)}
  .dper button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  .dper .dper-n{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem;
    color:var(--muted); margin-left:4px}
  table.d-nutri, table.d-cibi{width:100%; border-collapse:collapse; margin-top:8px;
    font-size:.82rem; font-variant-numeric:tabular-nums}
  table.d-nutri th, table.d-cibi th{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.6rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted);
    text-align:left; font-weight:600; padding:0 8px 5px 0; border-bottom:1px solid var(--rule)}
  table.d-nutri td, table.d-cibi td{padding:4px 8px 4px 0;
    border-bottom:1px solid var(--rule-soft, rgba(32,33,36,.08))}
  table.d-nutri .num, table.d-cibi .num{text-align:right; white-space:nowrap}
  /* i tetti si leggono al contrario degli obiettivi: si marcano, non si colorano
     uguale — superare il potassio e superare il sodio sono due cose opposte */
  table.d-nutri tr.tetto td:first-child::before{content:"tetto · "; color:var(--muted);
    font-size:.7rem; letter-spacing:.06em}
  table.d-cibi tr.asm td{color:var(--muted); font-style:italic}
  .dnav{display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:12px 0 4px}
  .dnav button,.d-act{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.6rem;
    letter-spacing:.1em; color:var(--ink-soft); background:var(--paper-2);
    border:1px solid var(--rule); border-radius:5px; padding:6px 11px; cursor:pointer}
  .dnav button:hover,.d-act:hover{border-color:var(--accent); color:var(--ink)}
  .dnav input[type=date]{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem;
    color:var(--ink); background:var(--paper-2); border:1px solid var(--rule);
    border-radius:5px; padding:5px 8px; color-scheme:light}
  .dnav .grow{flex:1 1 auto}
  /* una riga del pasto: nome, quantita' modificabile, kcal, e il cestino */
  .d-row{display:grid; grid-template-columns:minmax(0,1fr) 74px 62px 26px; gap:8px;
    align-items:center; padding:4px 0; border-bottom:1px solid rgba(32,33,36,.12)}
  .d-row>span{min-width:0; font-size:.84rem; color:var(--ink-soft); overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap}
  .d-row input{width:100%; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.7rem;
    color:var(--ink); background:var(--paper-2); border:1px solid var(--rule);
    border-radius:4px; padding:4px 6px; text-align:right}
  .d-row input:focus{outline:none; border-color:var(--accent)}
  .d-row em{font-style:normal; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.66rem;
    color:var(--muted); text-align:right; font-variant-numeric:tabular-nums}
  .d-row button{background:none; border:0; color:var(--muted); cursor:pointer;
    font-size:.95rem; line-height:1; padding:2px}
  .d-row button:hover{color:var(--neg)}
  .d-row.asm{opacity:.6}
  .d-row.gone>span{text-decoration:line-through; color:var(--muted)}
  .d-row.edit em{color:var(--accent)}
  .d-row.new>span::after{content:" nuovo"; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.5rem; letter-spacing:.1em; text-transform:uppercase; color:var(--accent)}
  /* lo stato del collegamento: un pallino, una riga, e la chiave se manca */
  .dstate{display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:10px 0 2px;
    padding:8px 11px; border:1px solid var(--rule); border-radius:6px;
    background:var(--paper-2); font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.6rem}
  .dstate b{color:var(--ink); font-weight:600; letter-spacing:.08em; white-space:nowrap}
  .dstate b::before{content:"● "; color:var(--muted)}
  .dstate.on b::before{color:var(--s3)}
  .dstate.bad b::before{color:var(--neg)}
  .dstate.off b::before{color:var(--accent)}
  .dstate span{color:var(--muted); letter-spacing:.05em; flex:1 1 160px; min-width:0}
  .dstate input{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.66rem; color:var(--ink);
    background:var(--paper); border:1px solid var(--rule); border-radius:4px;
    padding:5px 8px; flex:0 1 180px; min-width:0}
  .dstate input:focus{outline:none; border-color:var(--accent)}
  .dstate button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.6rem; letter-spacing:.1em;
    color:#fff; background:var(--accent); border:0; border-radius:4px;
    padding:6px 12px; cursor:pointer}
  /* in che pasto finisce quello che aggiungi */
  .d-meal{display:flex; align-items:center; flex-wrap:wrap; gap:5px; margin:2px 0 6px}
  .d-meal u{text-decoration:none; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.53rem;
    letter-spacing:.14em; text-transform:uppercase; color:var(--muted); margin-right:3px}
  .d-meal button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.58rem; color:var(--muted);
    background:none; border:1px solid var(--rule); border-radius:99px; padding:4px 10px;
    cursor:pointer}
  .d-meal button:hover{color:var(--ink); border-color:var(--accent)}
  .d-meal button.on{color:#fff; background:var(--accent); border-color:var(--accent)}
  .d-pre{display:flex; flex-wrap:wrap; gap:6px; margin:7px 0 2px}
  .d-pre button{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem; color:var(--ink-soft);
    background:var(--paper-2); border:1px solid var(--rule); border-radius:99px;
    padding:5px 11px; cursor:pointer; white-space:nowrap}
  .d-pre button:hover{border-color:var(--accent); color:var(--ink)}
  .d-pre button b{font-weight:500; color:var(--muted); font-size:.56rem; margin-left:5px}
  .d-search{width:100%; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.72rem;
    color:var(--ink); background:var(--paper-2); border:1px solid var(--rule);
    border-radius:5px; padding:7px 9px; margin-top:8px}
  .d-search:focus{outline:none; border-color:var(--accent)}
  .d-out{width:100%; min-height:104px; font-family:ui-monospace,'SFMono-Regular',Menlo,monospace;
    font-size:.62rem; line-height:1.6; color:var(--ink-soft); background:var(--paper-2);
    border:1px solid var(--rule); border-radius:5px; padding:9px 10px; margin-top:8px;
    white-space:pre; overflow:auto; resize:vertical}
  .d-acts{display:flex; gap:8px; flex-wrap:wrap; margin-top:9px}
  .d-empty{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.62rem; color:var(--muted);
    padding:8px 0}
  @media (max-width:560px){
    .d-row{grid-template-columns:minmax(0,1fr) 62px 52px 24px; gap:6px}
    .d-row>span{white-space:normal}
  }

  /* ---------- tooltip ----------
     Era un riquadro NERO (#0e0d09) con dentro testo grigio scuro: nato per la carta
     scura, dopo il 16/08/2026 era rimasto li' a scrivere #3c4043 su quasi-nero,
     cioe' niente. Adesso e' una scheda della home: carta bianca, filetto nero da
     2px, ombra secca. */
  .tip{position:fixed; z-index:9; pointer-events:none; opacity:0; transition:opacity .1s;
    background:var(--paper); border:2px solid var(--ink); border-radius:0; padding:7px 11px;
    font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.8rem; line-height:1.55;
    color:var(--ink-soft); max-width:260px; box-shadow:var(--neo-sm)}
  .tip.on{opacity:1}
  .tip .v{color:var(--ink); font-weight:700}
  .tip .d{color:var(--muted); font-size:.72rem; letter-spacing:.06em}

  /* ---------- le tre pagine-racconto, in cima ---------- */
  .tracks{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
    gap:12px; margin:30px 0 0}
  .track{position:relative; display:block; text-decoration:none; border-radius:0;
    border:2px solid var(--ink); box-shadow:var(--neo-sm); background:var(--paper);
    padding:14px 16px 12px;
    transition:border-color .16s,background .16s,transform .16s; overflow:hidden}
  .track::before{content:""; position:absolute; inset:0 auto 0 0; width:3px; background:var(--a)}
  .track:hover{border-color:var(--a); background:var(--paper-2); transform:translateY(-2px)}
  .track:focus-visible{outline:2px solid var(--a); outline-offset:3px}
  .track .k{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.68rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--a)}
  .track h3{font-family:'VT323',ui-monospace,monospace; font-size:1.35rem; font-weight:700; margin:4px 0 0}
  .track p{color:var(--ink-soft); font-size:.94rem; line-height:1.5; margin-top:5px}
  .track .nums{display:flex; gap:14px; flex-wrap:wrap; margin-top:9px}
  .track .nums b{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.94rem; font-weight:600;
    color:var(--ink); font-variant-numeric:tabular-nums; display:block}
  .track .nums span{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.63rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted)}
  @media(prefers-reduced-motion:reduce){.track{transition:none}.track:hover{transform:none}}

  /* ---------- sections ----------
     Il titolo di sezione e' un blocco pieno col filetto nero e l'ombra secca, come i
     riquadri colorati della home. Il colore ruota fra i quattro della palette I/O e
     NON codifica niente: e' l'unico posto della pagina in cui un colore non e' un
     dato, ed e' anche il motivo per cui li' dentro il testo e' sempre nero. */
  h2.band{font-family:'VT323',ui-monospace,monospace; font-size:1.7rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--ink); text-align:center; font-weight:600;
    margin:40px auto 8px; display:block; width:max-content; max-width:100%;
    background:var(--band-c,var(--io-yellow)); border:2px solid var(--ink);
    box-shadow:var(--neo-sm); padding:3px 20px 0}
  h2.band[data-c="blu"]{--band-c:#aecbfa}
  h2.band[data-c="rosso"]{--band-c:#f6aea9}
  h2.band[data-c="verde"]{--band-c:#a8dab5}
  h2.band[data-c="viola"]{--band-c:#d7aefb}
  h2.band[data-c="giallo"]{--band-c:#fdd663}
  /* Una riga sola, a sinistra, sotto il titolo: e' un'ETICHETTA di sezione. Centrata e in
     corsivo su 52em era una didascalia da saggio, ed e' meta' dell'impressione che
     Michele ha fotografato dal telefono il 16/08/2026 ("quanto cavolo di testo"). */
  .band-sub{text-align:left; color:var(--ink-soft); font-size:.96rem;
    max-width:52em; margin:0 auto}

  /* ---------- ⓘ: il come si legge, dietro un tocco ----------
     Michele, ordine #11: «info simboli click = show pop up». E' un <button>, non uno
     <span>, cosi' entra nel Tab da solo; e non e' un title=, che dal telefono non
     esiste — non c'e' hover, e li' dentro finiva testo che nessuno ha mai letto. */
  .ico{display:inline-flex; align-items:center; justify-content:center; vertical-align:.06em;
    width:17px; height:17px; margin-left:0; padding:0; flex:0 0 auto;
    font:600 11px/1 'Plus Jakarta Sans',system-ui,sans-serif; font-style:italic;
    color:var(--muted); background:var(--paper-2); border:1px solid var(--rule);
    border-radius:50%; cursor:pointer; position:relative}
  .ico::after{content:""; position:absolute; inset:-13px}   /* bersaglio da pollice */
  .ico:hover,.ico:focus-visible{color:var(--ink); border-color:var(--ink)}
  @media(max-width:640px){ .ico{width:22px; height:22px; font-size:13px} }
  #info-in h3{font-size:1.5rem}
  #info-in p{margin:9px 0 0; font-size:.9rem; line-height:1.6; color:var(--ink-soft)}
  #info-in code{font-family:ui-monospace,'SFMono-Regular',Menlo,monospace; font-size:.82rem;
    background:var(--paper-2); padding:1px 5px; border-radius:4px}

  /* ---------- also / footer ---------- */
  .also{margin-top:44px; text-align:center}
  .also a{display:inline-block; margin:6px 6px; padding:7px 15px; border-radius:999px;
    border:2px solid var(--ink); color:var(--ink); text-decoration:none; font-size:.94rem;
    box-shadow:var(--neo-sm); background:var(--paper)}
  .also a:hover{border-color:var(--accent); color:var(--ink)}
  footer{margin-top:34px; text-align:center; color:var(--muted); font-size:.88rem;
    line-height:1.7}
  @media(prefers-reduced-motion:reduce){*{transition:none !important}}
  /* Sotto i 720px la colonna laterale del riquadro non ci sta piu' accanto al
     grafico: titolo e numero passano sopra, il grafico prende tutta la larghezza.
     E' l'unico punto in cui il layout cambia forma, non solo dimensione. */
  @media(max-width:720px){
    .tile{grid-template-columns:1fr; gap:5px 0; padding:11px 12px 8px}
    .t-side{display:flex; align-items:baseline; justify-content:space-between;
      gap:10px; flex-wrap:wrap}
    .t-now{font-size:1rem; margin-top:0; text-align:right}
    .t-now small{display:inline; margin-left:5px}
  }
  @media(max-width:760px){
    /* La barra appesa ha quattro finestre, due viste e il menu delle sezioni: a 360px
       andrebbero a capo due volte e la barra si prenderebbe novanta pixel fissi in
       cima, cioe' esattamente lo spazio che si sta cercando di recuperare. Una riga
       sola che scorre di lato. */
    .controls{flex-wrap:nowrap; overflow-x:auto; justify-content:flex-start;
      -webkit-overflow-scrolling:touch}
    .controls > *{flex:none}
    .ranges{flex-wrap:nowrap}
    .viewsw{padding-left:12px}
    .secsel span{display:none}
  }
  @media(max-width:560px){
    body{padding:16px 11px 60px; font-size:17px}
    /* TRE COLONNE, NON DUE (Michele, ordine #22 del 19/08/2026: «invece di due colonne
       magari tre per essere più compatto… insomma più compatto, più in linea»).
       A 390 px restano 368 di riga utile: tre colonne da 117 con 8 di gronda ci stanno,
       e le tre file che si risparmiano sono duecento pixel di pagina in cima. Il corpo
       delle cifre scende con loro, o «12.274» andrebbe a capo dentro la sua colonna —
       una cifra spezzata a meta' e' peggio di una cifra piccola. */
    .totals{grid-template-columns:repeat(3,minmax(0,1fr)); gap:11px 6px}
    .total{padding:3px 1px}
    .total .n{font-size:1.1rem}
    .total .l{font-size:.58rem; letter-spacing:.06em; margin-top:2px}
    .total .d{font-size:.58rem; margin-top:1px}
    .headline-stats{margin-top:18px; gap:12px}
    .headline-label{margin-bottom:7px}
    h1{font-size:clamp(2.6rem,13vw,5.6rem)}
    .sub{margin-top:10px; font-size:1rem}
    .fortnight{margin-top:9px}
    /* i titoli di sezione: quaranta pixel di aria sopra ognuno, per sette sezioni,
       sono duecentottanta pixel di scorrimento che non dicono niente */
    h2.band{margin:24px auto 6px}
    .panel{margin-top:14px; gap:10px}
    .tile{padding:8px 11px 7px}
    .coach-card{margin-top:18px; padding:12px 14px 13px}
    .coach-lead{font-size:1.02rem; line-height:1.5; margin-bottom:9px}
    /* la barra appesa segue il padding del telefono, o il suo fondo lascia scoperti
       undici pixel per parte e sotto ci passano i grafici */
    .controls{margin-left:-11px; margin-right:-11px; padding-left:11px; padding-right:11px}
    .ranges{gap:6px}
    .ranges button{padding:7px 13px; font-size:.72rem}
    /* i due gruppi vanno a capo: il filetto di separazione, in verticale, taglierebbe
       la riga sbagliata */
    .viewsw{border-left:0; padding-left:0}
    .compare{padding:13px 11px 11px}
    .compare-controls label,.compare-controls select{width:100%; max-width:none; min-width:0}
    .compare-body{grid-template-columns:1fr}
    .compare-result{border-left:0; border-top:1px solid var(--rule); padding:10px 0 0;
      display:grid; grid-template-columns:auto 1fr; column-gap:12px; align-items:baseline}
    .compare-result p{grid-column:1/-1}
    .sheet{padding:8vh 0 0; align-items:flex-end}
    .sheet.on{display:flex}
    /* dal telefono e' un foglio che sale dal basso: spigolo vivo come tutto il resto,
       e senza ombra secca — un'ombra sfalsata di 6px su un pannello a filo del bordo
       si vedrebbe solo come una striscia nera tagliata */
    .sheet-in{width:100%; max-height:92vh; overflow-y:auto; margin:auto 0 0;
      border-radius:0; border-bottom:0; box-shadow:none;
      padding:18px 15px calc(20px + env(safe-area-inset-bottom))}
    .sheet h3{font-size:1.22rem; line-height:1.2; padding-right:32px}
    .sheet .when{padding-right:34px; font-size:.66rem}
    .insight-list .bar{grid-template-columns:minmax(0,1fr) minmax(96px,auto); gap:4px 8px}
    .insight-list .bar b{text-align:right; min-width:0; white-space:normal; font-size:.7rem}
    .food-intake{grid-template-columns:1fr}
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">micmer · quadro di comando</div>
  <h1>Vita</h1>
  <p class="sub">Undici anni di dati, in una colonna sola.<span id="ico-testata"></span></p>
</header>

<div class="headline-stats" id="totals">
  <!-- Il corpo per primo, che e' la richiesta letterale dell'ordine #22 («le
       statistiche in alto di corpo»). Nasce nascosto: peso e massa grassa esistono
       solo se la bilancia ha parlato, e un gruppo con tre trattini in cima alla
       pagina sarebbe peggio di nessun gruppo. -->
  <section class="headline-group" id="grp-body" aria-labelledby="headline-body-label" hidden>
    <div class="headline-label" id="headline-body-label">Corpo</div>
    <div class="totals" id="totals-body"></div>
  </section>
  <section class="headline-group" aria-labelledby="headline-recovery-label">
    <div class="headline-label" id="headline-recovery-label">Sonno &amp; attività</div>
    <div class="totals" id="totals-recovery"></div>
  </section>
  <section class="headline-group" aria-labelledby="headline-food-label">
    <div class="headline-label" id="headline-food-label">Alimentazione</div>
    <div class="totals" id="totals-food"></div>
  </section>
</div>
<p class="fortnight">14 giorni · variazione sui 14 precedenti</p>

<section class="coach-card" aria-labelledby="coach-h">
  <div class="coach-k">il rapporto</div>
  <h2 id="coach-h">L'opinione del coach</h2>
  <p class="coach-lead" id="coach-lead"></p>
  <button type="button" id="coach-btn">Leggi il rapporto</button>
</section>

<div class="diary-open">
  <button type="button" id="diary-btn">Apri il diario</button>
</div>


<div class="controls">
  <div class="ranges" id="ranges" role="group" aria-label="Finestra temporale"></div>
  <div class="ranges viewsw" id="viewsw" role="group" aria-label="Forma della vista"></div>
  <label class="secsel"><span>Sezione</span><select id="secsel" aria-label="Sezione da mostrare"></select></label><!-- aria-label e non solo lo <span>: sotto i 760px lo span e' display:none, e un'etichetta nascosta cosi' esce anche dall'albero di accessibilita' -->
</div>

<section class="compact" id="compact" aria-label="Vista compatta"></section>

<section class="sec" id="sec-carico" data-sec="carico">
<h2 class="band" data-c="blu">Carico</h2>
<p class="band-sub">Quanto lavoro c'è addosso, e quanto ne è già stato smaltito.</p>
<main class="panel" id="panel-carico"></main>
</section>

<section class="sec" id="sec-notte" data-sec="notte">
<h2 class="band" data-c="viola">Notte</h2>
<p class="band-sub">Il sonno come lo misura l'orologio — dal 2025 in poi.</p>
<main class="panel" id="panel-notte"></main>
</section>

<section class="sec" id="sec-recupero" data-sec="recupero">
<h2 class="band" data-c="rosso">Recupero</h2>
<p class="band-sub">Cosa dice il cuore al mattino, prima che cominci qualsiasi cosa.</p>
<main class="panel" id="panel-recupero"></main>
</section>

<section class="sec" id="sec-metabolismo" data-sec="metabolismo">
<h2 class="band" data-c="verde">Metabolismo</h2>
<p class="band-sub">Un sensore vero, tre modelli, due misure — le stime valgono la loro
variazione, non il loro livello (±40 %).<span id="ico-band-metabolismo"></span></p>
<main class="panel" id="panel-metabolismo"></main>
</section>

<section class="sec" id="sec-volume" data-sec="volume">
<h2 class="band" data-c="giallo">Volume</h2>
<p class="band-sub">Le ore, il dislivello, e come si dividono fra gli sport.</p>
<main class="panel" id="panel-volume"></main>
</section>

<section class="sec" id="sec-incroci" data-sec="incroci">
<h2 class="band" data-c="blu">Incroci</h2>
<p class="band-sub">Dieci coppie uscite da <strong>2.958 combinazioni</strong> — quattro
sono zeri, e sono il risultato più solido che ci sia.<span id="ico-band-incroci"></span></p>
<section class="compare" aria-label="Confronta due misure">
  <div class="cx-presets" id="compare-presets" role="group" aria-label="Coppie notevoli"></div>
  <p class="cx-claim" id="compare-claim"></p>
  <details class="cx-pick">
    <summary>scegli tu le due misure</summary>
    <div class="compare-controls">
      <label>Asse X<select id="compare-x"></select></label>
      <label>Asse Y<select id="compare-y"></select></label>
      <label>Tempo<select id="compare-lag">
        <option value="0">stesso giorno</option>
        <option value="1">Y il giorno dopo</option>
      </select></label>
      <label>Come<select id="compare-mode">
        <option value="lv">livelli</option>
        <option value="d1">variazioni giorno su giorno</option>
        <option value="d7">variazioni settimana su settimana</option>
      </select></label>
    </div>
  </details>
  <div class="compare-body">
    <div class="compare-plot" id="compare-plot"></div>
    <div class="compare-result" id="compare-result"></div>
  </div>
  <p class="compare-note">Associazione, non causa.<span id="ico-incrocio"></span></p>
</section>
</section>

<section class="sec" id="sec-tavola" data-sec="tavola">
<h2 class="band" data-c="giallo" id="cibo">Tavola</h2>
<p class="band-sub">Cosa entra, contro cosa serve — <strong>ricostruito</strong> al
<strong>75 %</strong>, quindi una base, non un totale.<span id="ico-band-tavola"></span></p>
<main class="panel" id="panel-tavola"></main>
</section>

<nav class="tracks" id="tracks" aria-label="Le pagine"></nav>

<nav class="also">
  <a href="matrice/">La Matrice degli alimenti</a>
  <a href="../top-20/">Venti giorni su 2.923</a>
  <a href="../bike-to-work/">Al lavoro in bici</a>
  <a href="../signore-dei-kj.html">Il Signore dei kJ</a>
  <a href="../viaggi/">Viaggi</a>
  <a href="../league-of-strava/">League of Strava</a>
  <a href="../">Profilo</a>
</nav>

<footer>
  <span class="mono">__BUILT__</span> · <span class="mono">build_vita.py</span> ·
  Intervals.icu + diario alimentare · il 2022 è <strong>ricostruito</strong><span id="ico-provenienza"></span>
</footer>

<div class="tip" id="tip" role="status" aria-live="polite"></div>

<div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-t">
  <div class="sheet-in" id="sheet-in"></div>
</div>

<div class="sheet" id="coach" role="dialog" aria-modal="true" aria-labelledby="coach-t">
  <div class="sheet-in" id="coach-in"></div>
</div>

<div class="sheet" id="diary" role="dialog" aria-modal="true" aria-labelledby="diary-t">
  <div class="sheet-in" id="diary-in"></div>
</div>

<div class="sheet" id="info" role="dialog" aria-modal="true" aria-labelledby="info-t">
  <div class="sheet-in" id="info-in"></div>
</div>

<script>
const D = __DATA__;

/* Le serie del cibo viaggiano compresse come {i0, v}: qui tornano array lunghi
   quanto il calendario, cosi' ogni riquadro le indicizza per giorno come tutte
   le altre e non deve sapere niente della compressione. */
(function expandBlocks() {
  const wide = src => {
    const out = {};
    for (const k in (src || {})) {
      const b = src[k], a = new Array(D.n).fill(null);
      for (let i = 0; i < b.v.length; i++) a[b.i0 + i] = b.v[i];
      out[k] = a;
    }
    return out;
  };
  D.nutri = wide(D.nutri);
  D.microbes = wide(D.microbes);
  D.metab = wide(D.metab);
})();

/* ------------------------------------------------------------------ time */
const DAY = 86400000;
const D0 = new Date(D.d0 + "T00:00:00");
const dayDate = i => new Date(D0.getTime() + i * DAY);
const N = D.n;
const MON = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"];
const DOW = ["lun","mar","mer","gio","ven","sab","dom"];
const fmtDate = i => { const d = dayDate(i);
  return d.getDate() + " " + MON[d.getMonth()] + " " + d.getFullYear(); };

/* Ranges. "sempre" is resolved per tile against that series' own first day, so a
   tile can never imply coverage it does not have. */
const RANGES = [
  { key:"2a",     label:"2 anni",    days:730 },
  { key:"1a",     label:"1 anno",    days:365 },
  { key:"3m",     label:"trimestre", days:91 },
  { key:"sempre", label:"sempre",    days:null },
];
/* Due anni di default: e' la finestra in cui quasi tutte le serie esistono
   davvero (sonno e HRV partono nel 2025), quindi e' quella in cui la colonna si
   legge tutta. "sempre" resta raggiungibile perche' il carico ha undici anni di
   storia e buttarli via sarebbe un peccato. */
let range = "2a";

function windowFor(firstIdx, lastIdx) {
  const last = lastIdx === undefined || lastIdx === null ? N - 1 : lastIdx;
  const r = RANGES.find(r => r.key === range);
  const from = r.days === null ? firstIdx : last - r.days + 1;
  return [Math.max(from, firstIdx, 0), last];
}
/* media mobile letta dove la serie finisce davvero, non dove finisce il calendario:
   per il cibo le due cose non coincidono */
function lastMean(arr, w) {
  let e = -1;
  for (let i = N - 1; i >= 0; i--) if (arr[i] !== null && arr[i] !== undefined) { e = i; break; }
  if (e < 0) return null;
  const r = rolling(arr, Math.max(0, e - w + 1), e, w);
  return r[r.length - 1];
}

/* ------------------------------------------------------- number formatting */
const nf = (v, d = 0) => v === null || v === undefined || !isFinite(v) ? "—"
  : v.toLocaleString("it-IT", { minimumFractionDigits:d, maximumFractionDigits:d });
/* Si arrotondano i MINUTI, poi si divide. Arrotondando i minuti residui dopo la
   divisione, 299,7 minuti diventavano "4h 60'" — un orologio che non esiste, e che
   compariva ovunque ci fosse una media di durate. */
const hhmm = m => { if (m === null || m === undefined || !isFinite(m)) return "—";
  const t = Math.round(m);
  return Math.floor(t / 60) + "h " + String(t % 60).padStart(2, "0") + "'"; };
const FMT = {
  num0:v => nf(v,0), num1:v => nf(v,1), hhmm,
  hours:v => nf(v,1) + " h", km:v => nf(v,0) + " km", m:v => nf(v,0) + " m",
  kg:v => nf(v,1) + " kg", pct:v => nf(v,1) + " %", bpm:v => nf(v,0) + " bpm",
  ms:v => nf(v,0) + " ms", tss:v => nf(v,0) + " TSS",
};

/* ------------------------------------------------------------ aggregation */
/* Adaptive bucketing: a bar per day over eleven years is a smear, so the bucket
   widens until at most ~110 of them fit. The label says which width won. */
function bucketPlan(from, to) {
  const days = to - from + 1;
  if (days <= 110) return { step:"d", label:"al giorno" };
  if (days <= 780) return { step:"w", label:"a settimana" };
  /* the whole archive is 4.152 days = 137 months, which still draws as a dense but
     readable bar field; falling back to years there would answer eleven years of
     volume with twelve bars, which is a summary, not a chart */
  if (days <= 4800) return { step:"m", label:"al mese" };
  return { step:"y", label:"all'anno" };
}
/* Monday-based weeks, calendar months and years — the same conventions the other
   pages on this site aggregate by. */
function bucketKey(i, step) {
  const d = dayDate(i);
  if (step === "d") return i;
  if (step === "w") { const off = (d.getDay() + 6) % 7; return i - off; }
  if (step === "m") return -(d.getFullYear() * 12 + d.getMonth()) - 1;
  return -100000 - d.getFullYear();
}
function bucketLabel(k, step) {
  if (step === "d") return fmtDate(k);
  if (step === "w") return "sett. del " + fmtDate(k);
  if (step === "m") { const t = -(k + 1); return MON[t % 12] + " " + Math.floor(t / 12); }
  return String(-(k + 100000));
}
function bucketStartIdx(k, step) {
  if (step === "d" || step === "w") return k;
  if (step === "m") { const t = -(k + 1);
    return Math.round((new Date(Math.floor(t / 12), t % 12, 1) - D0) / DAY); }
  return Math.round((new Date(-(k + 100000), 0, 1) - D0) / DAY);
}
/* Sum or mean a daily array into buckets. `mean` skips nulls; `sum` treats them as 0
   only when the day is inside the series' own coverage — outside it, the bucket is
   dropped rather than counted as a zero. */
function aggregate(arr, from, to, how, step) {
  const acc = new Map();
  for (let i = from; i <= to; i++) {
    const v = arr[i];
    if (v === null || v === undefined) { if (how === "mean") continue; }
    const k = bucketKey(i, step);
    let a = acc.get(k); if (!a) { a = { s:0, n:0, k }; acc.set(k, a); }
    a.s += (v || 0); a.n += 1;
  }
  return [...acc.values()].sort((a, b) => bucketStartIdx(a.k, step) - bucketStartIdx(b.k, step))
    .map(a => ({ k:a.k, i:bucketStartIdx(a.k, step), v: how === "mean" ? (a.n ? a.s / a.n : null) : a.s, n:a.n }));
}
/* Trailing rolling mean — the same window an athlete reads on a watch. */
function rolling(arr, from, to, w) {
  const out = [];
  for (let i = from; i <= to; i++) {
    let s = 0, n = 0;
    for (let j = Math.max(from, i - w + 1); j <= i; j++) {
      const v = arr[j]; if (v !== null && v !== undefined) { s += v; n++; }
    }
    out.push(n >= Math.max(2, w / 3) ? s / n : null);
  }
  return out;
}
/* La stessa media mobile, ma su coppie [indice, valore] gia' prese. `rolling` lavora
   sugli array del payload e va bene finche' la serie e' una colonna; le serie di
   `rLines` arrivano invece dalla loro `get`, che puo' averle gia' derivate — uno
   scarto, una quota, una somma di due colonne — e in quel caso l'array grezzo da
   passare a `rolling` non esiste da nessuna parte. Stessa soglia (un terzo della
   finestra pieno, e almeno due giorni) perche' due medie mobili con due soglie
   diverse nella stessa pagina sarebbero due cose che si chiamano uguale. */
function rollPts(pts, w) {
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    let s = 0, n = 0;
    for (let j = Math.max(0, i - w + 1); j <= i; j++) {
      const v = pts[j][1];
      if (v !== null && v !== undefined && isFinite(v)) { s += v; n++; }
    }
    out.push([pts[i][0], n >= Math.max(2, w / 3) ? s / n : null]);
  }
  return out;
}
/* Media su una serie RADA, con la finestra CENTRATA.
   `rolling` chiede che un terzo della finestra sia pieno, ed e' giusto per un dato
   giornaliero: su una serie che esiste un giorno su sette non si accende mai. La
   scomposizione dei grassi e' cosi' — un centinaio di giornate pesate su settecento —
   e sceglierne la forma non e' un dettaglio: la somma del mese direbbe soprattutto
   quanti giorni sono stati misurati quel mese. Qui la finestra si conta in giorni ma
   la soglia si conta in MISURE, e sotto `minN` misure non si disegna niente invece di
   tirare una riga attraverso il vuoto. Centrata e non trascinata perche' questa non e'
   una lettura da orologio, e' la composizione di un periodo. */
function sparse(arr, from, to, win, minN) {
  const half = Math.floor((win || 90) / 2), soglia = minN || 4, out = [];
  for (let i = from; i <= to; i++) {
    let s = 0, n = 0;
    for (let j = Math.max(from, i - half); j <= Math.min(to, i + half); j++) {
      const v = arr[j];
      if (v !== null && v !== undefined && isFinite(v)) { s += v; n++; }
    }
    out.push(n >= soglia ? s / n : null);
  }
  return out;
}
function stats(vals) {
  const v = vals.filter(x => x !== null && x !== undefined && isFinite(x));
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b);
  return { n:v.length, min:s[0], max:s[s.length - 1],
    mean:v.reduce((a, b) => a + b, 0) / v.length,
    med:s[Math.floor(s.length / 2)] };
}
/* Least squares + Pearson r. Both are reported; a fitted line without its r invites
   the reader to see a relationship that the number would deny. */
function fit(pts) {
  const n = pts.length; if (n < 4) return null;
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  for (const [x, y] of pts) { sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; }
  const dx = n * sxx - sx * sx, dy = n * syy - sy * sy;
  if (!dx || !dy) return null;
  const m = (n * sxy - sx * sy) / dx, b = (sy - m * sx) / n;
  const r = (n * sxy - sx * sy) / Math.sqrt(dx * dy);
  return { m, b, r, n };
}

/* ------------------------------------------------------------------- svg */
const NS = "http://www.w3.org/2000/svg";
const el = (t, a = {}) => { const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const nice = (lo, hi) => {
  if (lo === hi) { lo -= 1; hi += 1; }
  const span = hi - lo, mag = Math.pow(10, Math.floor(Math.log10(span / 3)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= 5) || mag * 10;
  return { lo:Math.floor(lo / step) * step, hi:Math.ceil(hi / step) * step, step };
};

/* Room for the y labels, measured rather than assumed. Un glifo monospazio e' largo
   ~0.606 volte il corpo, quindi a font-size 10 sono ~6.05px: un tick da cinque cifre
   ("50.000") chiede 47px dove uno da due ne chiede 21 — una gronda fissa o taglia i
   numeri grandi o butta un decimo di una scheda da 320px su quelli piccoli. Ogni asse
   qui sotto si dimensiona la sua.

   IL CORPO E' 10 E NON PIU' 8 (17/08/2026, Michele: "non si legge quasi nulla dei
   sottotitoli e anche dei labels"). Otto pixel su uno schermo di telefono sono un
   grigio, non un numero. Chi lo cambia deve cambiare TRE cose insieme, o il disegno e
   il controllo smettono di misurare la stessa pagina:
     · AXIS_FS qui sotto, che e' il corpo vero degli assi;
     · TICKW, che e' 0.606 x AXIS_FS;
     · GLYPH in tools/check_vita.cjs, che deve valere quanto TICKW — e' il modo in cui
       il check vede le etichette tagliate e quelle che si sovrappongono. */
const AXIS_FS = 10;
/* Il numero sopra la barra della media non e' un'etichetta d'asse: e' la cosa che si
   legge. Michele, 17/08: «valori sopra medie orizzontali piu' grandi font». Sta a se'
   perche' gli assi devono restare piccoli — se crescono anche loro, il disegno si
   mangia lo spazio del disegno. */
const MEAN_FS = 12;
const TICKW = 6.05;
const yTicks = (yd, fmt) => {
  const out = [];
  for (let v = yd.lo; v <= yd.hi + 1e-9; v += yd.step) out.push([v, String(fmt(v))]);
  return out;
};
const padFor = ticks => Math.min(76, Math.max(26,
  Math.ceil(Math.max(...ticks.map(t => t[1].length)) * TICKW) + 9));
const axisText = (x, y, s, anchor) => el("text", { x, y, "text-anchor":anchor,
  fill:"var(--muted)", "font-size":String(AXIS_FS),
  "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace" });
function yAxis(svg, ticks, Y, l, right) {
  for (const [v, lab] of ticks) {
    const y = Y(v);
    svg.appendChild(el("line", { x1:l, x2:right, y1:y, y2:y,
      stroke:v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width":1 }));
    const t = axisText(l - 5, y + 3, lab, "end");
    t.textContent = lab; svg.appendChild(t);
  }
}

const tip = document.getElementById("tip");
function showTip(x, y, html) {
  tip.innerHTML = html; tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(Math.max(8, x - r.width / 2), innerWidth - r.width - 8) + "px";
  tip.style.top = Math.max(8, y - r.height - 12) + "px";
}
const hideTip = () => tip.classList.remove("on");
addEventListener("scroll", hideTip, { passive:true });

/* Le bande "nessun dato" e le date sull'asse x sono le uniche due cose che la vista
   compatta condivide con i riquadri estesi: la ridgeline non ha assi y, ma ha lo
   stesso asse x e gli stessi buchi d'archivio. Stanno qui fuori da frame() perche'
   due copie della stessa regola sarebbero derivate al primo ritocco — e un buco del
   2022 disegnato in una vista e non nell'altra e' esattamente il modo in cui una
   pagina comincia a mentire in una sola delle sue forme. */
function gapBands(svg, X, x0, x1, top, ih) {
  /* Due bande diverse, e la differenza conta. "nessun dato" e' un buco vero:
     li' non si sa. "carico ricostruito" e' il 2022 e gli altri tratti ripresi
     dall'export Strava: li' le attivita' ci sono davvero, ma il loro carico e'
     STIMATO da durata e cardio, non misurato — e la CTL che ci passa sopra e'
     ricalcolata. Disegnarle uguali rimetterebbe la bugia dall'altro lato. */
  const band = (a, b, label, fill, stroke) => {
    if (b < x0 || a > x1) return;
    const xa = X(Math.max(a, x0)), xb = X(Math.min(b, x1));
    if (xb - xa < 1.5) return;
    svg.appendChild(el("rect", { x:xa, y:top, width:xb - xa, height:ih, fill }));
    svg.appendChild(el("rect", { x:xa, y:top, width:xb - xa, height:ih,
      fill:"none", stroke, "stroke-width":1, "stroke-dasharray":"2 3" }));
    if (xb - xa > 46) {
      const t = el("text", { x:(xa + xb) / 2, y:top + 11, "text-anchor":"middle",
        fill:"var(--muted)", "font-size":"9", "letter-spacing":".08em",
        "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace" });
      t.textContent = label; svg.appendChild(t);
    }
  };
  for (const [a, b] of D.gaps)
    band(a, b, "nessun dato", "rgba(32,33,36,.05)", "rgba(32,33,36,.16)");
  for (const [a, b] of (D.recon || []))
    band(a, b, "carico ricostruito", "rgba(201,133,0,.055)", "rgba(201,133,0,.20)");
}
/* x ticks: 3-5 dates across the window, never overlapping */
function xDates(svg, X, W, H, x0, x1, iw) {
  const kmax = iw < 260 ? 3 : iw < 420 ? 4 : 5;
  for (let k = 0; k < kmax; k++) {
    const v = x0 + (x1 - x0) * k / (kmax - 1), d = dayDate(Math.round(v));
    const span = x1 - x0;
    const lab = span > 900 ? String(d.getFullYear())
      : span > 150 ? MON[d.getMonth()] + " " + String(d.getFullYear()).slice(2)
      : d.getDate() + " " + MON[d.getMonth()];
    const t = axisText(X(v), H - 4, lab,
      k === 0 ? "start" : k === kmax - 1 ? "end" : "middle");
    t.textContent = lab; svg.appendChild(t);
  }
}

/* A chart frame: axes, gridlines, the shaded no-data bands, and the scales. Every
   renderer below draws into one of these, so they cannot drift apart. */
function frame(svg, W, H, xdom, ydom, opts = {}) {
  const yd = nice(ydom[0], ydom[1]);
  const ticks = yTicks(yd, opts.ytick || (v => nf(v, yd.step < 1 ? 1 : 0)));
  /* b passa da 16 a 19: le date sull'asse x sono cresciute da 8 a 10 px e con 16
     l'ultima riga di glifi finiva a filo del viewBox.
     `strip` e' la fascia delle medie, quando il riquadro la chiede: sta FRA il disegno
     e le date, e si prende la sua altezza dal grafico invece di sovrapporsi. */
  const strip = opts.strip ? EIGHTH_H : 0;
  /* `rpad`: il posto per un asse secondario a destra — le medie di `rLines` ci
     scrivono i loro valori (ordine #23) e senza spazio finirebbero fuori viewBox. */
  const P = { l:padFor(ticks), r:opts.rpad || (opts.strip ? EIGHTH_RPAD : 6), t:8, b:19 + strip };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const [x0, x1] = xdom;
  const X = v => P.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;

  /* no-data bands first, under everything */
  if (opts.gaps !== false) gapBands(svg, X, x0, x1, P.t, ih);
  yAxis(svg, ticks, Y, P.l, W - P.r);
  if (opts.xticks !== false) xDates(svg, X, W, H, x0, x1, iw);
  return { X, Y, P, iw, ih, yd, strip, W };
}

/* ------------------------------------------------------------- gli otto ottavi
   Michele, 17/08/2026: «qualsiasi periodo che sto mostrando venga diviso in 8 frame.
   Ho una barra orizzontale in quel x + delta x, col valore medio e sopra il numerino
   che identifica qual e' il valore medio. Mi sembra che Whoop faccia una roba del
   genere in alcuni grafici.»

   E' la lettura che manca a una nuvola e a un istogramma: sono fatti per mostrare la
   FORMA, e la forma non risponde a "quanto, in questo pezzo di anno". La media mobile
   nemmeno — e' un valore che cambia tutti i giorni, quindi si legge dove sta, non
   quanto vale. Gli otto ottavi rispondono a quella domanda sola, con un numero solo
   per ottavo, e sono confrontabili fra loro perche' i tratti sono uguali per
   costruzione: la finestra si divide in ottavi di PIXEL, non di dati, quindi l'ottavo
   e' sempre un ottavo anche dove i giorni mancano.

   Tre scelte che vale la pena non ripensare da capo:
   · **la barra e' nera, non del colore della serie.** Non e' una sesta serie: e' una
     annotazione sopra le altre. Il nero e' l'accento del sito, ed e' l'unico colore
     della pagina che il check garantisce a ΔE >= 15 da ogni slot — cioe' l'unico che
     non si puo' scambiare per un dato;
   · **il numero ha un alone di carta** (paint-order:stroke): senza, cadendo sopra la
     nuvola di punti diventava illeggibile proprio negli ottavi piu' pieni;
   · **l'ottavo senza dati non disegna niente.** Una barra a zero li' sarebbe un buco
     travestito da zero, che e' la bugia contro cui e' costruita mezza pagina. */
const FRAMES = 8;
/* Altezza della fascia, e quanto spazio si prende a destra per i suoi due estremi. */
const EIGHTH_H = 34, EIGHTH_RPAD = 30;
/* L'asse secondario delle medie (ordine #23): il posto a destra basta a «100 %» a
   corpo MEDIE_FS piu' il trattino che ricongiunge un'etichetta spostata alla sua
   riga. Il corpo resta quello degli assi: e' un asse, non un'annotazione. */
const MEDIE_FS = 10, MEDIE_RPAD = 40;

/* Disegna la fascia delle otto medie sotto al grafico di `g`.
   `pts` sono coppie [indice giorno, valore] nella stessa unita' dell'asse y del
   riquadro; `fmt` le formatta. Torna l'elenco delle medie, o null se non ce n'e'
   nessuna — cosi' chi chiama puo' dirlo nel piede invece di far sparire la fascia
   in silenzio. */
/* Le otto medie di una serie, in ottavi di PIXEL. Sta a se' perche' la usano in due:
   `eighths` per la fascia sotto il grafico, e `rLines` con `medie:true` per la
   spezzata dentro il grafico. Un secondo conteggio scritto a fianco sarebbe la
   quarta regola di CLAUDE.md violata alla lettera: "ottavo" deve voler dire la
   stessa cosa nei due posti, e il modo di garantirlo e' che il conto sia uno solo. */
function eighthMeans(pts, from, to, n = FRAMES) {
  const span = (to - from + 1) / n;
  if (!(span >= 1)) return null;
  const acc = Array.from({ length:n }, () => ({ s:0, c:0 }));
  for (const [x, v] of pts) {
    if (v === null || v === undefined || !isFinite(v)) continue;
    let k = Math.floor((x - from) / span);
    if (k < 0) k = 0; if (k >= n) k = n - 1;
    acc[k].s += v; acc[k].c++;
  }
  const mean = acc.map(a => a.c ? a.s / a.c : null);
  return mean.some(v => v !== null && isFinite(v)) ? { mean, span } : null;
}

function eighths(svg, g, pts, from, to, fmt, opts = {}) {
  const n = FRAMES;
  if (!g.strip) return null;
  const e = eighthMeans(pts, from, to, n);
  if (!e) return null;
  const { mean, span } = e;
  const vals = mean.filter(v => v !== null && isFinite(v));

  /* ---- LA SCALA PROPRIA -------------------------------------------------
     Il secondo asse e' tutto il punto (Michele, 18/08/2026: «secondary axis for
     those cosi' vedo variazioni tra le medie in modo migliore»). Sull'asse del
     grafico otto medie che stanno fra 41 e 46 TSS occupano quattro pixel su
     centosettanta e sembrano identiche; qui la fascia si riscala sulle medie e
     basta, e quei cinque TSS diventano venti pixel di dislivello.
     Il prezzo e' che la fascia NON e' sulla scala del disegno sopra, e per questo
     sta in una fascia sua sotto il grafico invece che sopra i dati: sovrapposte a
     una scala diversa sarebbero una bugia grafica. I due estremi sono scritti a
     destra, cosi' la scala non e' un'informazione nascosta. */
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo) { const d = Math.abs(hi) * .05 || 1; lo -= d; hi += d; }
  const pad = (hi - lo) * .18;
  lo -= pad; hi += pad;
  const top = g.P.t + g.ih + 5, H2 = g.strip - 5;
  const Y2 = v => top + H2 - (v - lo) / (hi - lo) * H2;

  const w = g.iw / n;
  /* ---- «ROUND INTELLIGENTLY» (Michele, 22/08/2026, sul riquadro «raccontato») ----
     Il numero di un ottavo non serve a certificare una cifra: serve a leggere la
     differenza fra quell'ottavo e gli altri sette. Le cifre che DISTINGUONO sono
     quelle dell'AMPIEZZA fra le otto medie, non quelle del loro livello — fra 15.486
     e 16.732 l'informazione sta nella terza cifra, la quinta e' rumore che ruba
     larghezza e fa saltare le etichette vicine.
     Due mosse, e nessuna delle due inventa precisione che non c'e':
     · si tolgono i decimali che l'ampiezza non giustifica, ma **mai piu' di quanti
       ne porta il formato del riquadro**: quello resta la scelta editoriale, e
       aggiungerne uno per "precisione" farebbe diventare 32 piante un 31,6;
     · sopra le diecimila si passa alle migliaia con la «k», perche' li' la quinta
       cifra non la legge nessuno e la differenza fra due ottavi si vede lo stesso.
     Vale solo per i formati NUMERICI: "20h 35'" non si arrotonda a mano, e il test
     lo riconosce dal fatto che dopo il numero non viene uno spazio ma una lettera. */
  const numerico = /^-?[\d.]+(?:,\d+)?(?:\s|$)/.test(String(fmt(1234.5)));
  const parti = String(fmt(vals[0])).match(/^(-?[\d.]+(?:,\d+)?)(.*)$/);
  const suf = numerico && parti ? parti[2] : "";
  const dFmt = ((String(fmt(1 / 3)).split(",")[1] || "").match(/^\d*/) || [""])[0].length;
  const spanM = Math.max(...vals) - Math.min(...vals);
  const magn = Math.max(...vals.map(Math.abs));
  const dOk = Math.min(dFmt, spanM >= 20 ? 0 : spanM >= 2 ? 1 : 2);
  const kilo = magn >= 1e4;
  const corto = (v, unita) => (kilo ? nf(v / 1000, spanM >= 2000 ? 0 : 1) + "k"
                                    : nf(v, dOk)) + (unita ? suf : "");
  /* Le scritture possibili, dalla piu' ricca alla piu' spiccia. Si prende la prima
     che sta in due corsie; dove l'arrotondamento non morde (la maggior parte dei
     riquadri) la prima e' identica a quella di prima, e infatti non cambia niente. */
  const scritture = numerico ? [v => corto(v, true), v => corto(v, false)]
                             : [v => String(fmt(v))];
  let labs = null, wide = 0;
  for (const scrivi of scritture) {
    labs = mean.map(v => v === null ? "" : scrivi(v));
    wide = Math.max(...labs.map(x => x.length)) * TICKW * (MEAN_FS / AXIS_FS) + 5;
    if (wide <= 2 * w) break;
  }
  /* ---- NESSUN OTTAVO SENZA IL SUO NUMERO -----------------------------------
     Michele, stesso foglio: «non centrato tutti i valori (alcuni mancano?)».
     Mancavano davvero. Il passo delle etichette si calcolava (`every`) e chi non ci
     stava in fila veniva SALTATO — ma un ottavo senza numero, a vederlo, e' identico
     a un ottavo senza dati, e distinguere il vuoto dal nulla e' mezzo scopo di questa
     pagina. Adesso quando la riga non basta i numeri prendono DUE corsie, pari sul
     bordo alto della fascia e dispari sul basso: ognuno resta centrato sulla sua
     barra, e ci sono tutti e otto. Fra due pari consecutivi c'e' il doppio dello
     spazio, ed e' esattamente la condizione su cui la scelta della scrittura qui
     sopra si e' fermata — le due cose vanno lette insieme o nessuna delle due sta
     in piedi. `every` resta come ultimo ripiego per il caso che non si e' mai visto:
     un'etichetta piu' larga di due ottavi anche dopo essere stata accorciata. */
  const corsie = wide > w ? 2 : 1;
  const yHi = top + MEAN_FS - 1, yLo = top + g.strip - 3;
  const every = Math.max(1, Math.ceil(wide / (corsie * w)));

  /* il filetto che separa la fascia dal disegno: e' li' per dire "da qui in giu'
     e' un'altra scala", quindi non e' decorazione e non si toglie */
  svg.appendChild(el("line", { x1:g.P.l, x2:g.P.l + g.iw, y1:top - 3, y2:top - 3,
    stroke:"var(--rule)", "stroke-width":1 }));
  /* i due estremi della scala, a destra, piccoli */
  for (const [v, dy] of [[hi, 3], [lo, 0]]) {
    const t = axisText(g.P.l + g.iw + 4, Y2(v) + dy, "", "start");
    t.textContent = fmt(v); t.setAttribute("font-size", String(AXIS_FS - 1));
    svg.appendChild(t);
  }

  /* ---- E LE MEDIE TORNANO ANCHE SUL DISEGNO --------------------------------
     Michele, 22/08/2026: «Medie non su grafico principale». La fascia sotto non
     sparisce, e la ragione per cui esiste resta intera: la sua scala propria e'
     l'unica cosa che impedisce a otto medie fra 41 e 46 TSS di sembrare identiche
     (ordine #23, 18/08). Ma per sapere a che LIVELLO stava un ottavo bisognava
     saltare fra due disegni con due assi diversi, e quel salto e' il difetto.
     Quindi gli stessi otto valori tornano dove stanno i dati, sulla scala del
     grafico: otto trattini neri e tenui, uno per ottavo, larghi quanto il loro
     ottavo. Staccati e non uniti — sono otto letture di otto pezzi d'anno, non una
     serie che passa di li'; unirli li farebbe leggere come una nona curva.
     Il numero resta scritto una volta sola, nella fascia: due volte sarebbe rumore,
     e sarebbe anche il numero letto contro due scale diverse. */
  mean.forEach((v, k) => {
    if (v === null || !isFinite(v) || v < g.yd.lo || v > g.yd.hi) return;
    const y = g.Y(v), x = g.P.l + w * k;
    svg.appendChild(el("line", { x1:x + 1.5, x2:x + w - 1.5, y1:y, y2:y,
      stroke:"var(--ink)", "stroke-width":1.6, opacity:".42", "stroke-linecap":"round" }));
  });

  const out = [];
  mean.forEach((v, k) => {
    if (v === null) return;                 /* ottavo senza dati: niente, mai uno zero */
    const y = Y2(v), x = g.P.l + w * k;
    const r = el("rect", { x:x + 1.5, y:y - 1.5, width:Math.max(2, w - 3), height:3,
      fill:"var(--ink)", opacity:".85", style:"cursor:pointer" });
    const a0 = Math.round(from + k * span), a1 = Math.round(from + (k + 1) * span) - 1;
    r.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
      `<span class="d">ottavo ${k + 1} di ${n} · ${fmtDate(a0)} → ${fmtDate(Math.min(a1, to))}</span>` +
      `<br>media <span class="v">${fmt(v)}</span>`));
    r.addEventListener("pointerleave", hideTip);
    svg.appendChild(r);
    out.push({ k, v });
    if (k % every) return;
    /* Il numero sta SEMPRE sopra la sua barra, e sempre DENTRO la fascia: la riga di
       base si aggrappa al bordo alto quando la barra e' troppo in cima. Mettendolo
       sotto — com'era — un ottavo alto finiva a due pixel dalle date dell'asse x, e
       il check lo prendeva come sovrapposizione: aveva ragione.
       Su due corsie la riga non segue piu' la barra ma il bordo della fascia: e' il
       prezzo per averli tutti e otto, e si paga volentieri perche' l'altezza della
       barra e' gia' disegnata dalla barra — il numero deve solo essere leggibile e
       stare sopra la sua colonna. */
    const t = el("text", { x:x + w / 2,
      y:corsie === 2 ? (k % 2 ? yLo : yHi) : Math.max(yHi, y - 5),
      "text-anchor":"middle", fill:"var(--ink)", "font-size":String(MEAN_FS),
      "font-weight":"700", "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
      stroke:"var(--paper)", "stroke-width":"3.2", "paint-order":"stroke",
      "stroke-linejoin":"round" });
    t.textContent = labs[k]; svg.appendChild(t);
  });
  return out;
}

/* A path that BREAKS on nulls rather than bridging them. */
function pathOf(pts, X, Y) {
  let d = "", pen = false;
  for (const [x, y] of pts) {
    if (y === null || y === undefined || !isFinite(y)) { pen = false; continue; }
    d += (pen ? "L" : "M") + X(x).toFixed(1) + " " + Y(y).toFixed(1) + " ";
    pen = true;
  }
  return d.trim();
}

/* ------------------------------------------------------ il popup di un giorno
   Un click su un punto qualsiasi apre la giornata intera: sonno e recupero,
   le attività con il link a Intervals e a Strava, i pasti alimento per alimento,
   e le coperture dei fabbisogni. È il posto in cui una serie torna a essere una
   giornata — e in cui si vede subito se un valore strano viene da un dato strano
   o da una giornata strana. */
const sheet = document.getElementById("sheet");
const sheetIn = document.getElementById("sheet-in");
/* `merenda` e `integratori` mancavano, e senza il loro nome la scheda del giorno
   scriveva la chiave grezza. `integratori` e' un pasto nato il 03/09/2026 (ordine
   MC #80): un integratore non e' una colazione ne' uno spuntino, e la sua ora non
   e' quasi mai dichiarata. */
const MEAL_IT = { colazione:"Colazione", pranzo:"Pranzo", cena:"Cena",
  spuntino:"Spuntino", merenda:"Merenda", integratori:"Integratori",
  non_specificato:"Non specificato" };
const NUTRI_IT = { protein_g:"Proteine", carb_g:"Carboidrati", fiber_g:"Fibre",
  fat_g:"Grassi", omega3_g:"Omega 3", potassium_mg:"Potassio", calcium_mg:"Calcio",
  iron_mg:"Ferro", magnesium_mg:"Magnesio", zinc_mg:"Zinco", vitc_mg:"Vit. C",
  vita_ug:"Vit. A", vitd_ug:"Vit. D", b12_ug:"Vit. B12", folate_ug:"Folati" };
const CAP_IT = { sodium_mg:"Sodio", satfat_g:"Grassi saturi", sugar_g:"Zuccheri" };
/* l'unita' si legge dal NOME della colonna invece di stare in un secondo elenco che
   qualcuno dimentichera' di allineare: `_mg` -> mg, `_ug` -> µg, `_g` -> g */
const UNI_IT = k => { const u = k.split("_").pop(); return u === "ug" ? "µg" : u; };

function bar(label, pct, cap, dens) {
  const w = Math.max(0, Math.min(100, pct));
  /* oltre il 100 % la barra resta piena: misura una copertura. Sui tetti
     (sodio, saturi, zuccheri) il colore vira quando si sfonda. */
  const col = cap ? (pct > 100 ? "var(--neg)" : "var(--s4)")
                  : (pct >= 100 ? "var(--s3)" : pct >= 50 ? "var(--s4)" : "var(--s2)");
  /* `dens` e' la densita' del nutriente in quel pasto: quanta parte del fabbisogno
     ha dato per ogni parte di calorie che e' costato. E' la quarta colonna, e sta
     accanto alla percentuale perche' le due si leggono insieme: 30 % del ferro e'
     un buon 30 se e' costato il 10 delle calorie, ed e' un cattivo 30 se ne e'
     costato il 40. */
  return `<div class="bar${dens ? " dens" : ""}"><u>${label}</u>` +
    `<div><i style="width:${w}%;background:${col}"></i></div><b>${nf(pct, 0)}%</b>` +
    (dens ? `<s>${dens}</s>` : "") + `</div>`;
}

/* ---- la regola della densita' nutrizionale --------------------------------
   Sta scritta in tools/food/profile.json, campo `_note`, ed e' la stessa che
   regge lo score di densita' del catalogo:

       score = (% del fabbisogno soddisfatto) / (% delle kcal di riferimento)

   Su una dieta di riferimento da `reference_kcal`, 100 kcal valgono il 3,85 %:
   un alimento che copre il 3,85 % di un nutriente ha score 1, cioe' densita'
   media. Il doppio fa 2. Applicata a un PASTO risponde alla domanda vera — «per
   quello che mi e' costato in calorie, quanto mi ha dato?» — che la sola
   percentuale non risponde. */
/* IL SEMAFORO DELLA DENSITA' (ordine #27): «devi mettere le emoji di buon GPT,
   tipo verde, rosso, giallo, al posto dei 0,7 o quant'altro».

   Aveva ragione: «x0,7» chiede di sapere cos'e' uno, e chi apre il diario alle
   sette di sera non lo sa. Un pallino lo si legge senza istruzioni. Il numero non
   sparisce, si sposta nel `title`: chi lo vuole ce l'ha, chi non lo vuole non se
   lo trova davanti.

   Le soglie stanno attorno a UNO, che e' la densita' media della dieta di
   riferimento, con una banda di indifferenza in mezzo: sopra 1,5 il pasto ha dato
   di quel nutriente piu' di quanto sia costato in calorie, sotto 0,7 di meno. Fra
   i due e' nella media, e colorare di giallo un pasto normale sarebbe un allarme
   inventato. */
const SEMAFORO = [
  [1.5, '🟢', 'denso: ne da\u2019 piu\u2019 di quanto costa'],
  [0.7, '🟡', 'nella media'],
  [0,   '🔴', 'diluito: costa piu\u2019 di quanto ne da\u2019'],
];

function semaforo(d) {
  if (d === null || d === undefined || !isFinite(d)) return null;
  for (const s of SEMAFORO) if (d >= s[0]) return { emoji: s[1], che: s[2] };
  return null;
}

function densita(pctNutriente, kcalPasto, kcalRif) {
  if (!kcalPasto || !kcalRif) return null;
  const quotaKcal = 100 * kcalPasto / kcalRif;
  if (quotaKcal <= 0) return null;
  return pctNutriente / quotaKcal;
}

/* I nutrienti di un pasto: l'array compatto `mn` riletto con l'ordine dichiarato
   in `_mn`, e le percentuali di fabbisogno divise qui invece che nel payload —
   `rda` e' gia' in `foodProfile`, ed emetterle sarebbe un secondo elenco della
   stessa cosa. Torna null se quel pasto non ha numeri (le giornate ricostruite
   non ne hanno: hanno lo schema, non la misura). */
function mealStats(day, m) {
  const ord = (D.days || {})._mn, arr = ((day && day.mn) || {})[m];
  if (!ord || !arr) return null;
  const rda = ((D.foodProfile || {}).rda) || {};
  const rif = (D.foodProfile || {}).reference_kcal || 0;
  const tot = {}, pct = {}, den = {};
  ord.forEach((n, i) => { tot[n] = arr[i]; });
  for (const n of ord) {
    if (!rda[n]) continue;
    pct[n] = Math.round(100 * tot[n] / rda[n]);
    den[n] = densita(pct[n], tot.kcal, rif);
  }
  return { tot, pct, den };
}

/* La chiave di `days.json` e' una data di calendario, e va scritta con i campi
   LOCALI. `toISOString()` normalizza a UTC: `D0` e' mezzanotte locale, quindi da
   Roma (UTC+2) ogni giorno usciva da qui come quello PRIMA — cliccando su oggi si
   apriva la cena di ieri. Su GitHub Actions, che gira in UTC, il check non poteva
   vederlo: l'offset era zero. */
const isoOf = i => {
  const d = dayDate(i), p = v => String(v).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

/* "150 g", "1.2×", "1". La quantita' arriva come numero e l'unita' dal catalogo:
   la stringa la compone la pagina, cosi' non esiste in due posti che possono
   allontanarsi. Gli ingredienti dei giorni ricostruiti arrivano invece gia'
   formattati dal template, e passano di qui senza `f`. */
const unitOf = fid => {
  const e = fid ? (D.foodCat || {})[fid] : null;
  return e ? e.u : "g";
};
const qtxt = it => {
  if (it.q !== undefined) return it.q;
  const u = unitOf(it.f), q = +(+it.qn).toFixed(4);
  return u === "unit" ? (q === 1 ? "1" : `${q}×`) : `${q} ${u}`;
};

function openDay(i) {
  if (i < 0 || i >= N) return;
  const k = isoOf(i);
  /* Il dettaglio arriva in tre forme: un giorno con pasti veri, un puntatore a una
     "forma ricostruita" (le centinaia di giorni identici stanno in _p una volta
     sola), e niente. Le ricette ricostruite si ridistendono da _t, il template. */
  let day = (D.days || {})[k];
  if (typeof day === "string") day = ((D.days || {})._p || {})[day];
  const acts = D.acts.map((a, j) => [a, j]).filter(([a]) => a[0] === i);
  const sleep = D.sleep[i], hrv = D.hrv[i], rhr = D.rhr[i], steps = D.steps[i];
  const score = D.score[i], w = D.weight[i];
  const ctl = D.ctl[i], atl = D.atl[i];

  let h = `<div class="sheet-hd"><div class="when">${DOW[(dayDate(i).getDay() + 6) % 7]}</div>` +
    `<h3 id="sheet-t">${fmtDate(i)}</h3></div>`;

  const kv = [];
  if (sleep !== null) kv.push([hhmm(sleep), "sonno"]);
  if (score !== null) kv.push([nf(score), "punteggio"]);
  if (hrv !== null) kv.push([nf(hrv) + " ms", "hrv"]);
  if (rhr !== null) kv.push([nf(rhr), "fc riposo"]);
  if (steps !== null) kv.push([nf(steps), "passi"]);
  if (w !== null) kv.push([nf(w, 1) + " kg", "peso"]);
  if (ctl !== null) kv.push([nf(ctl, 0), "fitness"]);
  if (ctl !== null && atl !== null) kv.push([nf(ctl - atl, 0), "forma"]);
  if (kv.length) h += `<h4>Corpo</h4><div class="kv">` +
    kv.map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("") + `</div>`;

  if (acts.length) {
    h += `<h4>Allenamento</h4><ul class="acts">` + acts.map(([a, j]) => {
      const nm = (D.anames || [])[j] || ["", "", ""];
      const bits = [];
      if (a[2]) bits.push(hhmm(a[2] / 60));
      if (a[3]) bits.push(nf(a[3] / 1000, 1) + " km");
      if (a[4]) bits.push(nf(a[4]) + " m");
      /* a[6]: l'attivita' viene dall'export Strava, non da Intervals. Il TSS non e'
         il loro, e' stimato qui da durata e cardio: si dice, accanto al numero. */
      if (a[5]) bits.push(nf(a[5]) + (a[6] ? " TSS stim." : " TSS"));
      const links = [];
      if (nm[1]) links.push(`<a href="https://intervals.icu/activities/${nm[1]}" target="_blank" rel="noopener">Intervals</a>`);
      if (nm[2]) links.push(`<a href="https://www.strava.com/activities/${nm[2]}" target="_blank" rel="noopener">Strava</a>`);
      return `<li><span>${nm[0] || S[a[1]]}${links.length ? " · " + links.join(" · ") : ""}</span><em>${bits.join(" · ")}</em></li>`;
    }).join("") + `</ul>`;
  }

  if (day && day.recipes && !day.meals) {
    /* giornata interamente ricostruita: si dice, e si mostra da cosa */
    const tpl = (D.days || {})._t || {};
    h += `<h4>Tavola — ${nf(day.tot.kcal)} kcal · ricostruita</h4>`;
    h += `<p class="hint" style="text-align:left;margin:0 0 8px">Di questo giorno non hai raccontato niente: qui sotto c'è lo schema abituale.</p>`;
    for (const rn of day.recipes) {
      h += `<div class="meal"><div class="mname">${rn}</div><ul>` +
        (tpl[rn] || []).map(it => `<li class="asm"><span>${it.n}</span><i>${qtxt(it)} · ${nf(it.kcal)} kcal</i></li>`).join("") +
        `</ul></div>`;
    }
    h += `<h4>Macro e micro, in % del fabbisogno</h4><div class="bars">` +
      Object.keys(NUTRI_IT).filter(nn => day.pct[nn] !== undefined)
        .map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
      Object.keys(day.cap || {}).map(nn => bar(CAP_IT[nn] || nn, day.cap[nn], true)).join("") +
      `</div>`;
  } else if (day) {
    const meals = day.meals || {};
    const order = ["colazione", "spuntino", "pranzo", "merenda", "cena",
                   "integratori", "non_specificato"];
    const keys = order.filter(m => meals[m]).concat(
      Object.keys(meals).filter(m => !order.includes(m)));
    if (keys.length) {
      h += `<h4>Tavola — ${nf(day.tot.kcal)} kcal` +
        (day.asm ? ` · ${nf(Math.round(100 * day.obs / (day.obs + day.asm)))}% osservato` : "") +
        `</h4>`;
      for (const m of keys) {
        const st = mealStats(day, m);
        const voce = it => `<li class="${it.a ? "asm" : ""}"><span>${it.n}</span>` +
          `<i>${qtxt(it)} · ${nf(it.kcal)} kcal</i></li>`;

        /* Le voci di una stessa ricetta stanno INSIEME, sotto il suo nome e il suo
           subtotale — «scrivi fiocchi d'avena, porridge, banana, che mi ripeti la
           ricetta sotto ognuna». Prima il nome della ricetta era appiccicato a ogni
           riga, quindi «Porridge» compariva cinque volte di fila e non si capiva
           quanto pesasse tutto insieme. Le voci sciolte restano dove sono. */
        const gruppi = [];
        for (const it of meals[m]) {
          const capo = gruppi.length ? gruppi[gruppi.length - 1] : null;
          if (it.r && capo && capo.r === it.r) { capo.items.push(it); continue; }
          gruppi.push({ r: it.r || "", items: [it] });
        }
        const corpo = gruppi.map(g => {
          if (!g.r) return `<ul>${g.items.map(voce).join("")}</ul>`;
          const k = g.items.reduce((s, it) => s + (it.kcal || 0), 0);
          return `<div class="mrec"><b><span>${g.r}</span><s>${nf(k)} kcal</s></b>` +
            `<ul>${g.items.map(voce).join("")}</ul></div>`;
        }).join("");

        /* La testata: quanto pesa il pasto, prima di aprirlo. Se i numeri non ci
           sono (giornata senza `mn`) si mostra solo la somma delle kcal delle voci,
           che c'e' sempre — meglio un dato solo che una testata che mente. */
        const kcalVoci = meals[m].reduce((s, it) => s + (it.kcal || 0), 0);
        const cap = st
          ? `${nf(st.tot.kcal)} kcal · P ${nf(st.tot.protein_g, 0)} · C ${nf(st.tot.carb_g, 0)} · G ${nf(st.tot.fat_g, 0)}`
          : `${nf(kcalVoci)} kcal`;

        let dentro = corpo;
        if (st) {
          /* «che tipo di percentuale mi ha dato per ogni micro, macro, vitamine
             rispetto alle percentuali di calorie»: la percentuale di fabbisogno del
             pasto, e accanto la densita'. */
          const nn = Object.keys(st.pct);
          dentro += `<div class="mdens"><div class="bars">` +
            nn.map(n => {
              const d = st.den[n];
              return bar(NUTRI_IT[n] || n, st.pct[n], false,
                d === null ? "" : "×" + nf(d, d < 10 ? 1 : 0));
            }).join("") +
            `</div><p class="hint">La colonna a destra è la <b>densità</b>: quanta parte ` +
            `del fabbisogno questo pasto ha dato per ogni parte di calorie che è costato. ` +
            `×1 è la media della dieta di riferimento (${nf((D.foodProfile || {}).reference_kcal)} kcal), ` +
            `×2 il doppio.</p></div>`;
        }
        h += `<details class="meal"><summary><span class="mname">${MEAL_IT[m] || m}</span>` +
          `<em>${cap}</em></summary>${dentro}</details>`;
      }
      const macro = ["protein_g", "carb_g", "fiber_g", "fat_g"];
      h += `<h4>Macro e micro, in % del fabbisogno</h4><div class="bars">` +
        macro.filter(nn => day.pct[nn] !== undefined).map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
        Object.keys(NUTRI_IT).filter(nn => !macro.includes(nn) && day.pct[nn] !== undefined)
          .map(nn => bar(NUTRI_IT[nn], day.pct[nn])).join("") +
        Object.keys(day.cap || {}).map(nn => bar(CAP_IT[nn] || nn, day.cap[nn], true)).join("") +
        `</div><p class="hint">Sui tetti (sodio, saturi, zuccheri) il rosso segna uno sforamento.</p>`;
    }
  } else {
    h += `<h4>Tavola</h4><p class="t-empty">Nessun pasto per questo giorno.</p>`;
  }

  sheetIn.innerHTML = h;
  /* Il bottone di chiusura e' un nodo vero appeso dopo, non un pezzo della stringa
     qui sopra: interrogare all'indietro l'HTML appena scritto e' proprio la cosa
     che rende la pagina impossibile da pilotare senza browser — e che il check
     non saprebbe piu' fare. Vale anche per un solo bottone. */
  const x = mk("button", "sheet-x", sheetIn, "×");
  x.setAttribute("type", "button");
  x.setAttribute("aria-label", "Chiudi");
  x.addEventListener("click", closeDay);
  sheet.classList.add("on");
  document.body.style.overflow = "hidden";
}
function closeDay() {
  sheet.classList.remove("on");
  document.body.style.overflow = "";
}
sheet.addEventListener("click", ev => { if (ev.target === sheet) closeDay(); });

/* ------------------------------------------------------------------- ⓘ ----
   «info simboli click = show pop up» (Michele, ordine #11). Un registro solo:
   chi vuole un ⓘ scrive `infoReg(chiave, titolo, corpo)` e mette
   `data-info="chiave"` sul bottone. Non esiste un secondo elenco da tenere
   allineato — quarta regola di CLAUDE.md.

   UN listener solo, delegato su document: i riquadri si ridisegnano a ogni
   drawAll e a ogni resize, e un listener attaccato al singolo bottone si
   sfilerebbe in silenzio al primo ridisegno. */
const infoEl = document.getElementById("info"), infoIn = document.getElementById("info-in");
const INFO = new Map();
const infoReg = (k, titolo, corpo) => { INFO.set(k, { titolo, corpo }); return k; };
const infoAperto = () => infoEl.classList.contains("on");
function openInfo(k) {
  const v = INFO.get(k);
  if (!v) return;
  infoIn.innerHTML = `<div class="sheet-hd"><h3 id="info-t">${v.titolo}</h3></div>${v.corpo}`;
  const x = mk("button", "sheet-x", infoIn, "×");
  x.setAttribute("type", "button"); x.setAttribute("aria-label", "Chiudi");
  x.addEventListener("click", closeInfo);
  infoEl.classList.add("on");
  document.body.style.overflow = "hidden";
  x.focus();
}
function closeInfo() {
  infoEl.classList.remove("on");
  // il popup della giornata puo' essere sotto: gli si lascia il blocco dello scorrimento
  document.body.style.overflow = sheet.classList.contains("on") ? "hidden" : "";
}
infoEl.addEventListener("click", ev => { if (ev.target === infoEl) closeInfo(); });
document.addEventListener("click", ev => {
  const b = ev.target.closest && ev.target.closest("[data-info]");
  if (!b) return;
  // senza questo, un ⓘ dentro l'intestazione di un riquadro aprirebbe anche il riquadro
  ev.preventDefault(); ev.stopPropagation();
  openInfo(b.dataset.info);
});
/* L'Escape chiude UNA cosa per volta, la piu' in alto. Senza la guardia, un ⓘ aperto
   sopra il popup della giornata li chiudeva tutti e due con un tasto solo. */
addEventListener("keydown", ev => {
  if (ev.key !== "Escape") return;
  if (infoAperto()) { closeInfo(); return; }
  closeDay();
});
window.CRUSCOTTO = window.CRUSCOTTO || {};
window.CRUSCOTTO.info = { open:openInfo, close:closeInfo, reg:INFO, aperto:infoAperto };
/* il bottoncino, sempre uguale: si scrive una volta e si usa dappertutto */
/* Il &nbsp; davanti NON e' cosmesi (18/08/2026, Michele: «va stranamente a capo per
   via dell'I»). Il bottone e' un inline-flex: la riga puo' spezzarsi appena prima, e
   il tondino finisce da solo su una riga sua sotto un titolo. Lo spazio unificatore lo
   incolla all'ultima parola, cosi' o vanno a capo insieme o non ci va nessuno dei due.
   Per questo il margine sinistro e' 0 nel CSS: lo spazio ce l'ha gia' davanti. */
const ico = (k, che) =>
  `&nbsp;<button class="ico" type="button" data-info="${k}" aria-label="Come si legge: ${che}">i</button>`;
/* la stessa cosa come nodo, per quando si appende invece di comporre una stringa.
   Niente insertAdjacentHTML: il DOM finto di check_vita.cjs non ce l'ha, e un metodo
   che esiste solo nel browser vero rende il check cieco proprio dove serve. */
const icoNode = (parent, k, che) => {
  const b = mk("button", "ico", parent, "i");
  b.setAttribute("type", "button");
  b.setAttribute("data-info", k);
  b.setAttribute("aria-label", "Come si legge: " + che);
  if (b.dataset) b.dataset.info = k;
  return b;
};

/* Le tre intestazioni di sezione che erano paragrafi da 600-850 caratteri, centrati e
   in corsivo. Quello che resta a schermo e' una riga; il metodo sta qui dietro. Cio' che
   dichiara la PROVENIENZA non e' sceso qui: «ricostruito», «75 %» e «±40 %» sono rimasti
   sulla superficie, perche' l'ⓘ porta il come, non il che. */
infoReg("band:metabolismo", "Metabolismo — come si legge",
  `<p>La temperatura è quella dell'<strong>orologio al polso durante l'uscita</strong>:
   aria scaldata da un corpo, non meteo.</p>
   <p>FatMax, heat strain e momento metabolico sono <strong>costruiti</strong>, e ognuno
   dichiara la propria formula o la propria fonte — perché su un grafico un numero
   misurato e uno calcolato hanno esattamente lo stesso aspetto.</p>
   <p>La domanda vera è una sola: <strong>la capacità di bruciare grassi si sposta?</strong>
   Misurarla vorrebbe dire una maschera metabolica e un test a gradini, che in questo
   archivio non esistono: i grammi al minuto restano una stima, col suo ±40 %.</p>
   <p>Quello che invece è misurato ogni giorno è <strong>quanto si va forte a parità di
   battito</strong>: il passo corretto per la pendenza contro la frequenza cardiaca, una
   corsa alla volta. Non è la stessa cosa, ed è la cosa più vicina che ci sia.</p>`);
infoReg("band:incroci", "Incroci — da dove escono le dieci coppie",
  `<p>Non scelte a occhio: calcolando <strong>tutte le 2.958 combinazioni</strong> di
   serie, su due sfasamenti e su livelli e variazioni, e poi buttando via due cose.</p>
   <p>Quelle dentro la stessa sezione, che sono il cablaggio del database e non una
   scoperta — fibre contro magnesio stanno negli stessi cibi. E quelle il cui <em>r</em>
   si scioglie appena si guardano le variazioni, dove era solo il tempo a muovere tutte
   e due.</p>
   <p>Quattro delle dieci sono <strong>zeri</strong>, ed è il risultato più solido che ci
   sia: con cinquecento mattine e un <em>r</em> sotto 0,15, quel legame non c'è.</p>
   <p>Sotto le pastiglie i due assi restano liberi, e due slot sono da riempire con le
   proprie.</p>`);
infoReg("band:tavola", "Tavola — che cosa vuol dire «ricostruito»",
  `<p>Due anni di giornate rimesse insieme da quello che Michele ha dichiarato di
   mangiare: la colazione fissa, due avocado toast e due dahl a settimana, e i piatti che
   ogni mese ricorrevano nelle sue foto — ognuno una volta nella sua settimana, poi a
   rotazione.</p>
   <p>Per sua stessa stima quei piatti sono circa il <strong>75 %</strong> di cosa mangia.
   Il restante quarto — spuntini, avanzi, il resto — qui non c'è: le calorie sono una
   base, non un totale.</p>
   <p><strong>Osservato</strong> = un pasto raccontato. <strong>Ricostruito</strong> = lo
   schema mensile dichiarato. Il primo riquadro della sezione dice quanta parte di ogni
   giorno è osservata davvero.</p>`);
/* La cornice: testata e piede. Erano 682 caratteri sempre a schermo, di cui 204 prima di
   qualunque numero. Quello che resta in superficie e' cio' che dichiara la provenienza —
   «ricostruito», e la data di generazione; il resto e' metodo, e sta dietro il tocco. */
infoReg("testata", "Da dove arrivano questi numeri",
  `<p>Da <strong>Intervals.icu</strong> e dal diario alimentare, inseriti nella pagina
   <strong>quando viene generata</strong>: nessuna chiamata di rete, nessun dato che esce
   di qui mentre la guardi.</p>
   <p>Il carico è registrato dal 2019; sonno, HRV e passi dal 2025; la tavola da maggio
   2026.</p>`);
/* IL VOCABOLARIO DELLA PROVENIENZA — quattro parole, e non una di piu'.
   Prima c'era `dataNote`, testo libero: sette formulazioni per tre concetti
   («modello, non una misura», «indice, non una misura», «modello, non un test da
   laboratorio»…) e su 9 riquadri su 42. Le altre 33 non dichiaravano niente a colpo
   d'occhio. Questa e' la terza regola di casa — osservato, ricostruito e stimato non
   sono la stessa cosa — smessa di essere una raccomandazione e diventata un campo. */
const SRC_LAB = { misurato:"misurato", ricostruito:"ricostruito", modello:"modello", stima:"stima" };
infoReg("provenienza:misurato", "Misurato",
  `<p>Un sensore l'ha letto: l'orologio, il ciclocomputer, la bilancia. Resta vero che
   uno strumento ha la sua precisione — ma nessuno ha inventato il numero.</p>`);
infoReg("provenienza:ricostruito", "Ricostruito",
  `<p>Rimesso insieme da quello che Michele ha <strong>dichiarato</strong>, non pesato
   pasto per pasto: la colazione fissa, i piatti che ricorrono ogni mese. Copre circa il
   <strong>75 %</strong> di quello che mangia — il resto qui non c'è.</p>
   <p>Vuol dire che questi numeri sono una <strong>base</strong>, non un totale, e che
   una correlazione con la tavola può mostrare le regole della ricostruzione invece del
   corpo.</p>`);
infoReg("provenienza:modello", "Modello",
  `<p>Calcolato da una formula o da una curva di letteratura, non misurato: FatMax,
   heat strain, il momento metabolico, le medie esponenziali di fitness e fatica.</p>
   <p>Ogni riquadro di questo tipo dichiara la propria formula o la propria fonte sotto
   «dati» — perché su un grafico un numero misurato e uno calcolato hanno esattamente lo
   stesso aspetto.</p>`);
infoReg("provenienza:stima", "Stima",
  `<p>Un modello di cui si conosce anche l'errore, ed è grande: i grammi di grasso al
   minuto stanno a <strong>±40 %</strong> sul livello assoluto.</p>
   <p>Si legge la <strong>variazione</strong>, non il valore: se sale, qualcosa si è
   mosso; quanto valga davvero quel numero, questo archivio non lo sa.</p>`);
infoReg("provenienza:ignota", "Provenienza non dichiarata",
  `<p>Questo riquadro non dichiara da dove vengono i suoi numeri, ed è un difetto:
   andrebbe messo <code>src</code> nella sua definizione.</p>`);

infoReg("incrocio", "Come si legge la nuvola",
  `<p>Ogni punto è un giorno con <strong>entrambe</strong> le misure. La retta e
   l'<em>r</em> descrivono un'<strong>associazione, non una causa</strong>.</p>
   <p>Le serie alimentari <strong>ricostruite</strong> possono mostrare soprattutto le
   regole usate per ricostruirle: se uno dei due assi è la tavola, il legame che vedi
   può essere il modello, non il corpo.</p>`);
infoReg("provenienza", "Il 2022, e le zone tratteggiate",
  `<p>Il <strong>2022 non manca più</strong>: le sue 394 attività sono rientrate da un
   export Strava. Ma il loro carico è <strong>stimato</strong> da durata e frequenza
   cardiaca, non misurato — perciò quel tratto dice «carico ricostruito».</p>
   <p>Le zone tratteggiate rimaste <strong>non sono riposo: sono assenza di dati</strong>.
   Uno zero lì sarebbe un dato mancante travestito da zero.</p>
   <p>Generato da <code>tools/build_vita.py</code>, che rilegge le sorgenti a ogni ora.</p>`);

[["band:metabolismo", "ico-band-metabolismo", "Metabolismo"],
 ["band:incroci", "ico-band-incroci", "Incroci"],
 ["band:tavola", "ico-band-tavola", "Tavola"],
 ["testata", "ico-testata", "da dove arrivano i numeri"],
 ["provenienza", "ico-provenienza", "il 2022 e le zone tratteggiate"],
 ["incrocio", "ico-incrocio", "come si legge la nuvola"]].forEach(([k, id, che]) => {
  const s = document.getElementById(id);
  if (s) s.outerHTML = ico(k, che);
});

/* --------------------------------------------------------------- renderers */
/* Each returns {stats, table, foot} so the tile can print its own summary and its
   own data fallback without the renderer knowing about the DOM around it. */

function rLines(svg, W, H, t, from, to) {
  const series = t.series.map(s => ({ ...s, vals:s.get(from, to) }));
  const all = series.flatMap(s => s.vals.map(p => p[1])).filter(v => v !== null && isFinite(v));
  if (!all.length) return null;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (t.zero) lo = Math.min(0, lo);
  /* ---- LA COMPOSIZIONE SI LEGGE COL LIVELLO, NON COL TREMOLIO ---------------
     `medie:true` e' la forma chiesta da Michele il 19/08/2026 (ordine #23) per i
     riquadri di composizione — «di che grasso», «da dove arrivano le calorie» e
     quant'altro: «linea dietro un po' trasparente, poi media di ogni linea
     orizzontale». Non e' una forma nuova: e' la grammatica di casa, quella di
     valseriana (`site/_report.js`, dove la misura grezza sta a `w 0.7` e
     `opacita 0.35` e sopra ci passa la lettura) e quella che questa pagina usa
     gia' nel popup delle medie (`meanLine` in `totals()`).
     Cinque serie a piena opacita' su centosettanta pixel di telefono sono cinque
     tremolii sovrapposti: quello che si vuole sapere da una composizione e' a che
     ALTEZZA sta ognuna, e l'altezza e' la media. Quindi la serie va dietro, sottile
     e trasparente, e davanti resta una riga orizzontale per ognuna.
     I numeri stanno su un ASSE SECONDARIO a destra, uno per riga, centrati sulla
     propria riga — «devono essere nel grafico stesso, semplicemente sul secondario
     asse, non sotto» (Michele, 19/08, ordine #23; la prima versione li metteva in
     legenda). Due medie vicine si toccherebbero: le etichette si distanziano di
     quel tanto che serve, e un trattino ricongiunge ognuna alla sua riga vera. */
  const medie = t.medie === true;
  const g = frame(svg, W, H, [from, to], [lo, hi],
    { ytick:t.ytick, strip:t.frames !== false, rpad:medie ? MEDIE_RPAD : 0 });
  const fmtL = t.fmt || FMT.num0;
  for (const s of series) {
    /* `mm`: la media mobile davanti alla serie grezza. Michele, 22/08/2026, sul
       riquadro dei carboidrati: «Moving averages?? ;)». Aveva ragione a chiederlo
       li': due serie giornaliere di grammi sono due pettini che si attraversano, e
       l'unica cosa che si vede e' che si attraversano. Tutto il resto della sezione
       la lettura ce l'ha gia' — le nuvole con la loro trascinata, le composizioni
       con `medie:true` — e questo riquadro era rimasto indietro e basta.
       La grezza non si butta: resta dietro, sottile e trasparente, perche' e' li'
       che si vede quanto ballano i giorni. Davanti passa la lettura. E' la stessa
       grammatica di valseriana (`site/_report.js`, misura a `opacita 0.35`). */
    const mm = t.mm ? rollPts(s.vals, t.mm) : null;
    const testa = mm || s.vals;
    /* con le medie il riempimento sotto la prima serie non serve piu' a niente:
       era li' per dire "questa e' la fetta grossa", e adesso lo dice la riga
       orizzontale piu' in alto. Restando, coprirebbe di tinta le altre quattro. */
    if (s.area && !medie) {
      const base = g.Y(Math.max(g.yd.lo, 0));
      const d = pathOf(testa, g.X, g.Y);
      if (d) {
        const first = testa.find(p => p[1] !== null), last = [...testa].reverse().find(p => p[1] !== null);
        svg.appendChild(el("path", { d:d + " L" + g.X(last[0]) + " " + base +
          " L" + g.X(first[0]) + " " + base + " Z", fill:s.col, opacity:".14" }));
      }
    }
    if (mm) svg.appendChild(el("path", { d:pathOf(s.vals, g.X, g.Y), fill:"none",
      stroke:s.col, "stroke-width":.9, opacity:".26", "stroke-linejoin":"round",
      "stroke-linecap":"round" }));
    /* `dash`: per le serie che stanno su un ASSE DIVERSO dalle altre del riquadro.
       L'ultra-processato attraversa le quattro quote d'origine invece di essere la
       quinta, e il tratteggio lo dice prima della legenda. Non e' decorazione: una
       linea piena in mezzo a una composizione si legge come parte della somma. */
    svg.appendChild(el("path", Object.assign({ d:pathOf(testa, g.X, g.Y), fill:"none",
      stroke:s.col, "stroke-width":medie ? 1 : (s.w || 2), "stroke-linejoin":"round",
      "stroke-linecap":"round" },
      medie ? { opacity:".32" } : {},
      s.dash ? { "stroke-dasharray":s.dash } : {})));
  }
  const livelli = [];
  /* ---- LA MEDIA DEVE SEGUIRE IL MOVIMENTO ---------------------------------
     Michele, 22/08/2026, a matita rossa sopra «Di che grasso»: le righe erano
     ORIZZONTALI su tutta la finestra mentre le serie sotto salivano e scendevano, e
     i segni rossi indicavano dove la riga avrebbe dovuto muoversi. Una retta su due
     anni risponde a «quanto vale in media», che qui non e' la domanda: la domanda e'
     se la quota di saturi stia scendendo — e a quella una retta non puo' rispondere
     per costruzione, qualunque siano i dati sotto.
     Quindi la riga diventa la stessa spezzata a OTTAVI che il resto della pagina usa
     gia': otto tratti, uno per ottavo, e il confronto fra riquadri torna a funzionare
     («confronta con gli altri riquadri, dove le medie sono a ottavi»). Qui i tratti
     sono UNITI dai raccordi verticali, al contrario dei trattini staccati della
     fascia: li' sono otto letture separate di una serie sola, qui e' una sola quota
     di composizione che cambia livello, e spezzarla la farebbe sembrare intermittente.
     Il numero a destra e' quello dell'ULTIMO ottavo, non piu' la media dei due anni:
     e' il valore a cui la riga ARRIVA al bordo destro, cioe' l'unica cosa che
     un'etichetta appesa li' possa onestamente dire. Chi vuole la media intera la
     trova nella tabella DATI del riquadro. */
  if (medie) for (const s of series) {
    const e = eighthMeans(s.vals, from, to);
    if (!e) continue;
    const w8 = g.iw / FRAMES;
    let d = "", pen = false, ultimo = null;
    e.mean.forEach((v, k) => {
      if (v === null || !isFinite(v)) { pen = false; return; }
      const y = g.Y(Math.min(g.yd.hi, Math.max(g.yd.lo, v)));
      const xa = g.P.l + w8 * k, xb = xa + w8;
      d += (pen ? "L" : "M") + xa.toFixed(1) + " " + y.toFixed(1) +
           " L" + xb.toFixed(1) + " " + y.toFixed(1) + " ";
      pen = true; ultimo = v;
    });
    if (!d) continue;
    svg.appendChild(el("path", { d:d.trim(), fill:"none", stroke:s.col,
      "stroke-width":1.8, "stroke-linejoin":"round", "stroke-linecap":"round" }));
    if (ultimo !== null && ultimo >= g.yd.lo && ultimo <= g.yd.hi)
      livelli.push({ name:s.name, col:s.col, v:ultimo });
  }
  /* L'ASSE SECONDARIO: il valore di ogni media al bordo destro, centrato sulla sua
     riga. Due medie vicine si toccherebbero: ogni etichetta spinge la successiva di
     un corpo intero, il gruppo rientra se sfora il fondo, e quando una si stacca
     dalla sua altezza vera un trattino del suo colore la ricongiunge alla riga. */
  if (livelli.length) {
    const gap = MEDIE_FS + 1, xr = g.P.l + g.iw, low = g.P.t + g.ih;
    const lab = livelli.map(o => ({ ...o, y0:g.Y(o.v), y:g.Y(o.v) }))
      .sort((a, b) => a.y0 - b.y0);
    for (let i = 1; i < lab.length; i++)
      lab[i].y = Math.max(lab[i].y, lab[i - 1].y + gap);
    if (lab[lab.length - 1].y > low) {
      lab[lab.length - 1].y = low;
      for (let i = lab.length - 2; i >= 0; i--)
        lab[i].y = Math.min(lab[i].y, lab[i + 1].y - gap);
    }
    for (const o of lab) {
      if (Math.abs(o.y - o.y0) > 1.5)
        svg.appendChild(el("line", { x1:xr + 1, x2:xr + 5, y1:o.y0, y2:o.y,
          stroke:o.col, "stroke-width":1, opacity:".7" }));
      const tx = el("text", { x:xr + 7, y:o.y + MEDIE_FS * .36, fill:o.col,
        "font-size":String(MEDIE_FS), "font-weight":"700",
        "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
        stroke:"var(--paper)", "stroke-width":"3", "paint-order":"stroke",
        "stroke-linejoin":"round" });
      tx.textContent = fmtL(o.v); svg.appendChild(tx);
    }
  }
  crosshair(svg, g, W, H, from, to, i => series.map(s => {
    const p = s.vals[i - from]; return p && p[1] !== null
      ? `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${s.col};margin-right:5px"></i>${s.name} <span class="v">${(t.fmt || FMT.num0)(p[1])}</span>` : null;
  }).filter(Boolean).join("<br>"));
  /* Con piu' di una linea la fascia fa la media della PRIMA — quella che il riquadro
     mette per prima in legenda, cioe' quella di cui parla il titolo. Otto barre per
     serie sarebbero ventiquattro segni in una fascia da 34 px; una barra sola senza
     dire di chi sarebbe peggio ancora, e infatti la legenda lo dice: la voce della
     serie con la fascia porta il quadratino nero accanto al suo. */
  if (t.frames !== false)
    eighths(svg, g, series[0].vals, from, to, t.fmt || FMT.num0);
  return {
    stats:stats(series[0].vals.map(p => p[1])),
    table:tableOf(series, from, to, t.fmt),
  };
}

/* Diverging area around zero: the two arms are a polarity, not two series, so they
   take the diverging poles and the midpoint is the axis itself. */
function rDiverge(svg, W, H, t, from, to) {
  const vals = t.get(from, to);
  const nums = vals.map(p => p[1]).filter(v => v !== null && isFinite(v));
  if (!nums.length) return null;
  const m = Math.max(Math.abs(Math.min(...nums)), Math.abs(Math.max(...nums)));
  const g = frame(svg, W, H, [from, to], [-m, m], { ytick:t.ytick, strip:t.frames !== false });
  const zero = g.Y(0);
  for (const sign of [1, -1]) {
    const clipped = vals.map(([x, v]) => [x, v === null ? null : (sign > 0 ? Math.max(0, v) : Math.min(0, v))]);
    const d = pathOf(clipped, g.X, g.Y);
    if (!d) continue;
    const f = clipped.find(p => p[1] !== null), l = [...clipped].reverse().find(p => p[1] !== null);
    svg.appendChild(el("path", { d:d + " L" + g.X(l[0]) + " " + zero + " L" + g.X(f[0]) + " " + zero + " Z",
      fill:sign > 0 ? C_POS : C_NEG, opacity:".26" }));
  }
  svg.appendChild(el("path", { d:pathOf(vals, g.X, g.Y), fill:"none",
    stroke:"var(--ink-soft)", "stroke-width":1.2, opacity:".55" }));
  crosshair(svg, g, W, H, from, to, i => {
    const p = vals[i - from]; if (!p || p[1] === null) return null;
    const s = p[1] >= 0 ? "fresco" : "carico";
    return `${t.name} <span class="v">${(t.fmt || FMT.num0)(p[1])}</span><br><span class="d">${s}</span>`;
  });
  /* qui l'ottavo dice una cosa in piu' del solito: la media della forma su un ottavo
     e' il segno di quel periodo — sopra zero si e' stati in credito, sotto in debito */
  if (t.frames !== false) eighths(svg, g, vals, from, to, t.fmt || FMT.num0);
  return { stats:stats(vals.map(p => p[1])), table:tableOf([{ name:t.name, vals }], from, to, t.fmt) };
}
/* i due poli della Forma: non sono serie, sono un segno. Prendono gli stessi due
   colori della home che tutta la pagina usa per credito e debito. */
const C_POS = "var(--s1)", C_NEG = "var(--neg)";

function rBars(svg, W, H, t, from, to) {
  const plan = bucketPlan(from, to);
  const b = aggregate(t.arr, from, to, t.how || "sum", plan.step)
    .map(o => ({ ...o, v:t.scale ? t.scale(o.v) : o.v }))
    .filter(o => o.v !== null && isFinite(o.v));
  if (!b.length) return null;
  const hi = Math.max(...b.map(o => o.v));
  const g = frame(svg, W, H, [from, to], [0, hi], { ytick:t.ytick, strip:t.frames !== false });
  /* Barre. Una quantita' sommata su un intervallo e' un'area, non un punto: la
     barra dice "in questa settimana, tanto", la linea direbbe "in questo istante,
     tanto" — che di una somma non e' vero. */
  const bw = Math.max(1.2, Math.min(22, g.iw / b.length - 1.6));
  for (const o of b) {
    const x = g.X(o.i) - bw / 2, y = g.Y(o.v);
    const r = el("rect", { x, y, width:bw, height:Math.max(.8, g.Y(0) - y),
      rx:Math.min(2, bw / 2), fill:t.col, style:"cursor:pointer" });
    r.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
      `<span class="d">${bucketLabel(o.k, plan.step)}</span><br>${t.name} <span class="v">${(t.fmt || FMT.num0)(o.v)}</span>`));
    r.addEventListener("pointerleave", hideTip);
    r.addEventListener("click", () => openDay(o.i));
    svg.appendChild(r);
  }
  /* gli otto ottavi si calcolano sulle COLONNE, non sui giorni: l'asse y qui porta
     una somma per settimana o per mese, e la media dei giorni starebbe su un altro
     asse — un numero giusto letto contro la scala sbagliata. */
  if (t.frames !== false) eighths(svg, g, b.map(o => [o.i, o.v]), from, to,
    t.fmt || FMT.num0);
  return { stats:stats(b.map(o => o.v)), plan,
    table:`<tr><th>${plan.label}</th><th>${t.name}</th></tr>` +
      b.slice(-40).reverse().map(o => `<tr><td>${bucketLabel(o.k, plan.step)}</td><td>${(t.fmt || FMT.num0)(o.v)}</td></tr>`).join("") };
}

/* Stacked bars. A 2px surface gap between segments so adjacent fills never fuse. */
function rStack(svg, W, H, t, from, to) {
  const plan = bucketPlan(from, to);
  const cols = t.cols, names = t.names;
  /* `how` di solito e' "sum": una composizione di quantita' si somma. Ma dove la
     serie e' RADA — la scomposizione dei grassi esiste su un centinaio di giorni
     misurati — la somma del mese direbbe soprattutto quanti giorni sono stati
     misurati quel mese, e un mese con tre giorni sembrerebbe un mese di digiuno.
     Con "mean" ogni colonna e' "un giorno misurato di quel mese", che e' la sola
     cosa vera che si puo' dire quando la copertura non e' piena. */
  const per = t.arrs.map(a => aggregate(a, from, to, t.how || "sum", plan.step));
  /* Le colonne si appaiano per CHIAVE, non per posizione. Appaiandole per posizione
     — com'era fino al 17/08/2026 — si assumeva che ogni serie della pila producesse
     esattamente gli stessi bidoni nello stesso ordine: vero finche' tutte le pile
     erano somme su serie complete, falso appena una serie ha una copertura sua. La
     prima pila con una serie rada ha sollevato `p[j].v of undefined`, e l'ha presa
     `check_vita.cjs` invece della pagina viva. Si tiene l'INTERSEZIONE: una
     composizione a cui manca un pezzo non e' una composizione con un pezzo a zero. */
  const maps = per.map(p => new Map(p.map(o => [o.k, o])));
  const keys = (per[0] || []).map(o => o.k).filter(k => maps.every(m => m.has(k)));
  if (!keys.length) return null;
  const rows = keys.map(k => ({ k, i:maps[0].get(k).i,
    parts:maps.map(m => { const v = m.get(k).v;
      return (t.scale ? t.scale(v) : v) || 0; }) }));
  /* AL CENTO PER CENTO (`pct`): ogni colonna vale 100 e si guarda come si divide,
     non quanto e' alta. Michele, 17/08: «graph grassi magari 100% e mostra % dei vari
     con quei grafici a bande». E' la forma giusta quando la domanda e' la COMPOSIZIONE
     e il totale e' un'altra storia — qui i grammi di grasso al giorno cambiano col
     giorno, ma la quota di saturi e' quello che si vuole leggere.
     I grammi non si perdono: restano nel tooltip e nella tabella sotto «dati». */
  const grezze = rows.map(r => r.parts.slice());
  if (t.pct) rows.forEach(r => {
    const tot = r.parts.reduce((a, b) => a + b, 0);
    if (tot > 0) r.parts = r.parts.map(v => 100 * v / tot);
  });
  const hi = t.pct ? 100 : Math.max(...rows.map(r => r.parts.reduce((a, b) => a + b, 0)));
  if (!(hi > 0)) return null;
  const g = frame(svg, W, H, [from, to], [0, hi],
    { ytick:t.pct ? (v => nf(v, 0) + " %") : t.ytick, strip:t.frames !== false && !t.pct });
  /* Impilate: la domanda qui e' una composizione — quanto fa il totale e come si
     divide — e impilare e' l'unica forma che risponde a tutte e due insieme.
     2px di superficie fra un segmento e l'altro, o due colori adiacenti si
     fondono in una banda sola. */
  const bw = Math.max(1.6, Math.min(26, g.iw / rows.length - 1.8));
  rows.forEach((r, ri) => {
    let acc = 0;
    const total = r.parts.reduce((a, b) => a + b, 0);
    r.parts.forEach((v, si) => {
      if (!(v > 0)) return;
      const yTop = g.Y(acc + v), yBot = g.Y(acc);
      /* al 100% le bande si toccano quasi: un solco di 2px su una colonna piena
         mangia il segmento piu' sottile, che qui e' proprio quello che interessa */
      const h = Math.max(.8, yBot - yTop - (acc > 0 ? (t.pct ? 1 : 2) : 0));
      const rect = el("rect", { x:g.X(r.i) - bw / 2, y:yTop, width:bw, height:h,
        rx:Math.min(2, bw / 2), fill:cols[si], style:"cursor:pointer" });
      rect.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
        `<span class="d">${bucketLabel(r.k, plan.step)}</span><br>` +
        r.parts.map((p, k) => p > 0 ? `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${cols[k]};margin-right:5px"></i>${names[k]} <span class="v">${t.pct ? nf(p, 1) + " %" : (t.fmt || FMT.num1)(p)}</span>${t.pct ? ` <span class="d">${(t.fmt || FMT.num1)(grezze[ri][k])}</span>` : ""}` : null).filter(Boolean).join("<br>") +
        `<br><span class="d">totale ${(t.fmt || FMT.num1)(t.pct ? grezze[ri].reduce((a, b) => a + b, 0) : total)}</span>`));
      rect.addEventListener("pointerleave", hideTip);
      rect.addEventListener("click", () => openDay(r.i));
      svg.appendChild(rect);
      acc += v;
    });
  });
  /* La fascia fa la media del TOTALE della colonna, non di una fetta: in una pila la
     domanda "quanto" e' il totale, e "come si divide" la risponde gia' il disegno.
     Su una pila in percentuale non si disegna: li' il totale e' 100 per costruzione,
     e otto barre identiche non sono una lettura, sono rumore. */
  if (t.frames !== false && !t.pct)
    eighths(svg, g, rows.map(r => [r.i, r.parts.reduce((a, b) => a + b, 0)]), from, to,
      t.fmt || FMT.num1);
  return { stats:stats(grezze.map(p => p.reduce((a, b) => a + b, 0))), plan,
    table:`<tr><th>${plan.label}</th>${names.map(n => `<th>${n}</th>`).join("")}</tr>` +
      rows.map((r, ri) => [r, grezze[ri]]).slice(-30).reverse().map(([r, gz]) => `<tr><td>${bucketLabel(r.k, plan.step)}</td>${gz.map(p => `<td>${(t.fmt || FMT.num1)(p)}</td>`).join("")}</tr>`).join("") };
}

/* The cloud-and-trend form: every day is a dot, the line is the trailing mean, and
   an optional band marks the reference the dots should be read against. */
function rCloud(svg, W, H, t, from, to) {
  const arr = t.arr;
  const days = to - from + 1;
  const pts = [];
  for (let i = from; i <= to; i++) if (arr[i] !== null && arr[i] !== undefined) pts.push([i, arr[i]]);
  if (!pts.length) return null;
  const mean = rolling(arr, from, to, t.win || 7);
  const nums = pts.map(p => p[1]);

  /* Il dominio y lo detta la MEDIA MOBILE, non i picchi giornalieri.
     Scalando sugli estremi, una notte da tre ore o un giorno da trentamila passi
     si prende meta' dell'altezza e schiaccia la media in una riga piatta — che e'
     esattamente la serie che si voleva guardare. Qui la banda della media occupa
     il grosso dell'altezza, allargata quel tanto che basta a contenere il corpo
     centrale della nuvola (dal 10esimo al 90esimo percentile). I punti che
     restano fuori non si disegnano, e il piede della scheda li conta: meglio
     dichiararli che appiattire tutto per farceli stare. */
  const mvals = mean.filter(v => v !== null && isFinite(v));
  const q = (a, p) => { const s = [...a].sort((x, y) => x - y);
    return s[Math.max(0, Math.min(s.length - 1, Math.round(p * (s.length - 1))))]; };
  let lo, hi;
  if (mvals.length >= 2) {
    const mLo = Math.min(...mvals), mHi = Math.max(...mvals);
    const pad = Math.max((mHi - mLo) * .45, Math.abs(mHi) * .02, 1e-6);
    lo = Math.min(mLo - pad, q(nums, .10));
    hi = Math.max(mHi + pad, q(nums, .90));
  } else {
    lo = Math.min(...nums); hi = Math.max(...nums);
    const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
  }
  if (t.band) { lo = Math.min(lo, t.band[0]); hi = Math.max(hi, t.band[1]); }
  if (t.zero) lo = Math.max(0, lo);
  const outside = nums.filter(v => v < lo || v > hi).length;
  const g = frame(svg, W, H, [from, to], [lo, hi], { ytick:t.ytick, strip:t.frames !== false });
  const inRange = v => v >= g.yd.lo && v <= g.yd.hi;
  if (t.band) {
    const yA = g.Y(t.band[1]), yB = g.Y(t.band[0]);
    svg.appendChild(el("rect", { x:g.P.l, y:yA, width:g.iw, height:Math.max(1, yB - yA),
      fill:t.col, opacity:".07" }));
  }
  /* over ~800 days the dots stop being dots; the daily cloud becomes weekly means */
  if (days > 800) {
    const w = aggregate(arr, from, to, "mean", "w").filter(o => o.v !== null);
    for (const o of w) if (inRange(o.v))
      svg.appendChild(el("circle", { cx:g.X(o.i), cy:g.Y(o.v), r:1.6,
        fill:t.col, opacity:".5" }));
  } else {
    const r = days > 420 ? 1.5 : days > 200 ? 1.9 : days > 90 ? 2.4 : 3;
    for (const [x, y] of pts) if (inRange(y))
      svg.appendChild(el("circle", { cx:g.X(x), cy:g.Y(y), r,
        fill:t.col, opacity:".38" }));
  }
  /* La media mobile e' piu' trasparente di prima (17/08/2026: "magari le medie mobili
     un po' piu' trasparenti"). Non e' un ripensamento estetico: da quando sopra ci
     passano gli otto ottavi, la linea non e' piu' la lettura principale del riquadro
     ma il suo sfondo di andamento, e a piena opacita' litigava col numero nero. */
  svg.appendChild(el("path", { d:pathOf(mean.map((v, k) => [from + k, v]), g.X, g.Y),
    fill:"none", stroke:t.col, "stroke-width":2.2, opacity:".5",
    "stroke-linejoin":"round", "stroke-linecap":"round" }));
  crosshair(svg, g, W, H, from, to, i => {
    const v = arr[i], m = mean[i - from];
    if (v === null && m === null) return null;
    return `${t.name} <span class="v">${(t.fmt || FMT.num0)(v)}</span>` +
      (m !== null ? `<br><span class="d">media ${t.win || 7} gg ${(t.fmt || FMT.num0)(m)}</span>` : "");
  });
  /* DOPO il mirino, non prima: il mirino stende un rettangolo trasparente su tutto il
     grafico per catturare il puntatore, e qualunque cosa disegnata sotto smette di
     rispondere al passaggio del mouse. */
  if (t.frames !== false) eighths(svg, g, pts, from, to, t.fmt || FMT.num0);
  return { stats:stats(nums), outside,
    table:tableOf([{ name:t.name, vals:pts }], from, to, t.fmt, true) };
}

/* Una BANDA e la sua mediana: due serie che sono un intervallo, non due linee.
   Serve dove il dato nasce gia' come "da qui a qui" — il minimo e il massimo letti
   dal sensore in un'uscita, il basso e l'alto della finestra FatMax. Disegnarle come
   due tracciati separati direbbe "due misure"; disegnarle come un nastro dice
   "l'intervallo", che e' quello che sono, e lascia la linea centrale a portare la
   tendenza. Il nastro e' liscio come le linee (stessa finestra mobile) o il bordo
   superiore ballerebbe di giorno in giorno mentre la mediana e' calma, e la banda
   sembrerebbe rumore invece che ampiezza. */
function rBand(svg, W, H, t, from, to) {
  const w = t.win || 30;
  const mid = rolling(t.mid, from, to, w);
  const lo = rolling(t.lo, from, to, w);
  const hi = rolling(t.hi, from, to, w);
  const nums = mid.concat(lo, hi).filter(v => v !== null && isFinite(v));
  if (nums.length < 4) return null;
  const g = frame(svg, W, H, [from, to], [Math.min(...nums), Math.max(...nums)],
    { ytick:t.ytick, strip:t.frames !== false });

  /* il nastro si chiude solo sui tratti in cui ESISTONO tutte e tre le serie: dove
     una manca il nastro si interrompe, invece di chiudersi attraverso il buco */
  let run = [];
  const flush = () => {
    if (run.length >= 2) {
      const up = run.map((p, j) => (j ? "L" : "M") + g.X(p[0]).toFixed(1) + " " + g.Y(p[2]).toFixed(1)).join(" ");
      const dn = [...run].reverse().map(p => "L" + g.X(p[0]).toFixed(1) + " " + g.Y(p[1]).toFixed(1)).join(" ");
      svg.appendChild(el("path", { d:up + " " + dn + " Z", fill:t.col, opacity:".16" }));
    }
    run = [];
  };
  for (let k = 0; k < mid.length; k++) {
    const a = lo[k], b = hi[k];
    if (a === null || b === null || !isFinite(a) || !isFinite(b)) { flush(); continue; }
    run.push([from + k, a, b]);
  }
  flush();
  svg.appendChild(el("path", { d:pathOf(mid.map((v, k) => [from + k, v]), g.X, g.Y),
    fill:"none", stroke:t.col, "stroke-width":2.2, "stroke-linejoin":"round",
    "stroke-linecap":"round" }));

  crosshair(svg, g, W, H, from, to, i => {
    const k = i - from, m = mid[k], a = lo[k], b = hi[k];
    if (m === null && a === null) return null;
    const f = t.fmt || FMT.num0;
    return `${t.name} <span class="v">${f(m)}</span><br>` +
      `<span class="d">banda ${f(a)} → ${f(b)} · media ${w} gg</span>`;
  });
  const pts = mid.map((v, k) => [from + k, v]);
  /* la fascia fa la media della MEDIANA, non della banda: la banda e' un'ampiezza,
     e la media di un'ampiezza non e' una cosa che si legge */
  if (t.frames !== false) eighths(svg, g, pts, from, to, t.fmt || FMT.num0);
  return { stats:stats(mid), plan:{ label:`media mobile ${w} giorni` },
    table:tableOf([{ name:t.name, vals:pts },
      { name:"basso", vals:lo.map((v, k) => [from + k, v]) },
      { name:"alto", vals:hi.map((v, k) => [from + k, v]) }], from, to, t.fmt) };
}






/* Griglia generica: righe × colonne, un valore per cella, colore = valore.
   La usano la matrice alimenti × generi e la striscia temporale. Il colore e'
   divergente quando il valore ha un segno (blu sopra zero, rosso sotto, grigio in
   mezzo) e sequenziale a una tinta sola quando e' solo una grandezza — mai un
   arcobaleno, e mai una tinta al centro di una divergente. */
function rGrid(svg, W, H, t, from, to) {
  const rows = t.rows, cols = t.cols;
  if (!rows.length || !cols.length) return null;
  const labL = Math.min(t.labMax || 118, Math.max(46, Math.ceil(
    Math.max(...rows.map(r => r.name.length)) * TICKW) + 8));
  const labB = t.labB ?? 56, pad = 1.2, top = 6;
  const cw = (W - labL - 8) / cols.length;
  const ch = (H - labB - top) / rows.length;
  if (cw < 8 || ch < 9) return null;

  let hottest = null;
  const cells = [];
  rows.forEach((r, i) => {
    cols.forEach((c, j) => {
      const cell = t.cell(i, j);
      const x = labL + j * cw, y = top + i * ch;
      let fill = "rgba(32,33,36,.035)";
      if (cell && cell.v !== null && cell.v !== undefined) {
        const g = Math.min(1, Math.abs(cell.v) / (t.vmax || 1));
        fill = t.diverging === false
          ? `rgba(57,135,229,${(g * .80).toFixed(3)})`
          : (cell.v >= 0 ? `rgba(57,135,229,${(g * .80).toFixed(3)}`
                         : `rgba(230,103,103,${(g * .80).toFixed(3)}`) + ")";
        if (!hottest || Math.abs(cell.v) > Math.abs(hottest.v)) hottest = { ...cell, i, j };
        cells.push([r.name, c.name, cell]);
      }
      const rect = el("rect", { x:x + pad, y:y + pad, width:Math.max(1, cw - pad * 2),
        height:Math.max(1, ch - pad * 2), rx:2, fill,
        stroke:"rgba(32,33,36,.07)", "stroke-width":1 });
      if (cell && cell.tip) {
        rect.setAttribute("style", "cursor:pointer");
        rect.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY, cell.tip));
        rect.addEventListener("pointerleave", hideTip);
        if (cell.day !== undefined) rect.addEventListener("click", () => openDay(cell.day));
      }
      svg.appendChild(rect);
      if (cell && cell.txt && cw >= 26 && ch >= 15) {
        const tx = el("text", { x:x + cw / 2, y:y + ch / 2 + 3, "text-anchor":"middle",
          "font-size":"8", "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
          fill:Math.abs(cell.v) / (t.vmax || 1) > .55 ? "var(--ink)" : "var(--muted)" });
        tx.textContent = cell.txt; svg.appendChild(tx);
      }
    });
    const ty = axisText(labL - 5, top + i * ch + ch / 2 + 3, r.name, "end");
    ty.textContent = r.name; svg.appendChild(ty);
  });
  /* etichette di colonna ruotate: a orizzontale si sovrappongono, ed e' il
     difetto classico di ogni heatmap con piu' di cinque colonne */
  const every = Math.max(1, Math.ceil(cols.length / (t.maxColLabels || 14)));
  cols.forEach((c, j) => {
    if (j % every) return;
    const cx = labL + j * cw + cw / 2, cy = top + rows.length * ch + 7;
    const tx = el("text", { x:cx, y:cy, "text-anchor":"end", "font-size":"8",
      "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace", fill:"var(--muted)",
      transform:`rotate(-52 ${cx.toFixed(1)} ${cy.toFixed(1)})` });
    tx.textContent = c.name; svg.appendChild(tx);
  });
  return { best2:t.summary ? t.summary(hottest, cells) : null,
           table:t.table ? t.table(cells) : "" };
}


/* La nuvola X-Y. Non ha piu' nessun riquadro suo dopo la potatura del
   18/08/2026 — «distanza contro dislivello», «passo contro battito» e «il caldo»
   sono usciti tutti e tre — ma la usa il CORRELATORE, che e' l'unico posto della
   pagina in cui una nuvola x-y guadagna il suo spazio: li' le due serie le sceglie
   chi guarda, invece di essere una coppia decisa da qualcun altro mesi fa. */
function rXY(svg, W, H, t, from, to) {
  const groups = t.points(from, to);
  const all = groups.flatMap(g => g.pts);
  if (all.length < 4) return null;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const xd = nice(Math.min(...xs), Math.max(...xs)), yd = nice(Math.min(...ys), Math.max(...ys));
  const ticks = yTicks(yd, t.ytick || (v => nf(v, yd.step < 1 ? 1 : 0)));
  const P = { l:padFor(ticks), r:8, t:8, b:20 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X = v => P.l + (v - xd.lo) / (xd.hi - xd.lo) * iw;
  const Y = v => P.t + ih - (v - yd.lo) / (yd.hi - yd.lo) * ih;
  yAxis(svg, ticks, Y, P.l, W - P.r);
  /* x ticks thinned to whatever fits: a label is only drawn if it clears the last
     one it was placed beside, so the axis never turns into overlapping ink */
  let lastRight = -1e9;
  for (let v = xd.lo; v <= xd.hi + 1e-9; v += xd.step) {
    if (v < Math.min(...xs) - xd.step || v > Math.max(...xs) + xd.step) continue;
    const lab = String((t.xtick || (u => nf(u, xd.step < 1 ? 1 : 0)))(v));
    const half = lab.length * TICKW / 2;
    if (X(v) - half < lastRight + 6 || X(v) + half > W) continue;
    lastRight = X(v) + half;
    const tx = axisText(X(v), H - 6, lab, "middle");
    tx.textContent = lab; svg.appendChild(tx);
  }
  groups.forEach(gr => {
    for (const p of gr.pts) {
      const c = el("circle", { cx:X(p[0]), cy:Y(p[1]), r:t.r || 2.6, fill:gr.col,
        opacity:".45", stroke:"var(--paper)", "stroke-width":.6 });
      c.addEventListener("pointerenter", ev => showTip(ev.clientX, ev.clientY,
        (p[2] !== undefined ? `<span class="d">${fmtDate(p[2])}</span><br>` : "") +
        `${t.xname} <span class="v">${(t.xfmt || FMT.num0)(p[0])}</span><br>` +
        `${t.yname} <span class="v">${(t.yfmt || FMT.num0)(p[1])}</span>` +
        (groups.length > 1 ? `<br><span class="d">${gr.name}</span>` : "")));
      c.addEventListener("pointerleave", hideTip);
      if (p[2] !== undefined) { c.setAttribute("style", "cursor:pointer");
        c.addEventListener("click", () => openDay(p[2])); }
      svg.appendChild(c);
    }
  });
  const f = fit(all.map(p => [p[0], p[1]]));
  if (f) {
    const xa = Math.min(...xs), xb = Math.max(...xs);
    svg.appendChild(el("line", { x1:X(xa), y1:Y(f.m * xa + f.b), x2:X(xb), y2:Y(f.m * xb + f.b),
      stroke:"var(--ink-soft)", "stroke-width":1.6, "stroke-dasharray":"5 3", opacity:".8" }));
  }
  return { fit:f, stats:stats(ys),
    table:`<tr><th>${t.xname}</th><th>${t.yname}</th></tr>` +
      all.slice(-30).reverse().map(p => `<tr><td>${(t.xfmt || FMT.num0)(p[0])}</td><td>${(t.yfmt || FMT.num0)(p[1])}</td></tr>`).join("") };
}

/* One crosshair implementation for every day-indexed renderer. */
function crosshair(svg, g, W, H, from, to, describe) {
  const line = el("line", { y1:g.P.t, y2:g.P.t + g.ih, stroke:"var(--accent)",
    "stroke-width":1, opacity:"0", "pointer-events":"none" });
  svg.appendChild(line);
  const hit = el("rect", { x:g.P.l, y:g.P.t, width:g.iw, height:g.ih, fill:"transparent" });
  const at = ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const i = Math.round(from + (px - g.P.l) / g.iw * (to - from));
    if (i < from || i > to) return;
    const html = describe(i);
    line.setAttribute("x1", g.X(i)); line.setAttribute("x2", g.X(i));
    line.setAttribute("opacity", html ? ".55" : "0");
    if (html) showTip(ev.clientX, ev.clientY, `<span class="d">${fmtDate(i)}</span><br>${html}`);
    else hideTip();
  };
  hit.addEventListener("pointermove", at);
  hit.addEventListener("pointerenter", at);
  hit.addEventListener("pointerleave", () => { line.setAttribute("opacity", "0"); hideTip(); });
  /* un click sul grafico apre la giornata sotto il cursore */
  hit.setAttribute("style", "cursor:pointer");
  hit.addEventListener("click", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const i = Math.round(from + (px - g.P.l) / g.iw * (to - from));
    if (i >= from && i <= to) openDay(i);
  });
  svg.appendChild(hit);
}

function tableOf(series, from, to, fmt, sparse) {
  /* the fallback is a summary, not a dump: at most 30 rows, newest first */
  const rows = [];
  const s0 = series[0].vals;
  const step = Math.max(1, Math.ceil(s0.length / 30));
  for (let k = s0.length - 1; k >= 0; k -= step) {
    const p = s0[k]; if (!p || p[1] === null) continue;
    rows.push(`<tr><td>${fmtDate(p[0])}</td>` +
      series.map(s => { const q = s.vals.find(v => v[0] === p[0]);
        return `<td>${q && q[1] !== null ? (fmt || FMT.num0)(q[1]) : "—"}</td>`; }).join("") + "</tr>");
    if (rows.length >= 30) break;
  }
  return `<tr><th>data</th>${series.map(s => `<th>${s.name}</th>`).join("")}</tr>` + rows.join("");
}

/* ------------------------------------------------------------------ tiles */
const secsOf = (() => {                       /* daily activity aggregates, once */
  const secs = new Array(N).fill(0), dist = new Array(N).fill(0),
        gain = new Array(N).fill(0), cnt = new Array(N).fill(0);
  const bySport = D.sports.map(() => new Array(N).fill(0));
  for (const [i, sp, s, m, up] of D.acts) {
    secs[i] += s; dist[i] += m; gain[i] += up; cnt[i] += 1; bySport[sp][i] += s;
  }
  return { secs, dist, gain, cnt, bySport };
})();

const daysOf = f => D.first[f] ?? 0;
/* a day index on an x axis is meaningless as a number — label it as a month.
   Declared up here because TILES reads it while it is being built. */
const monthTick = v => { const d = dayDate(Math.round(v));
  return MON[d.getMonth()] + " " + String(d.getFullYear()).slice(2); };
const S = D.sports;
const SC = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
/* SCH ERA UN SECONDO ELENCO DI COLORI, e come ogni secondo elenco era rimasto
   indietro: conteneva ancora #d95926 / #199e70 / #c98500, cioe' i passi nati per la
   carta scura di prima del 16/08/2026. Meta' delle serie della pagina — fitness,
   fatica, temperatura, FatMax, le quote della tavola — usciva quindi in ocra e
   ruggine mentre i riquadri che leggevano `SC` uscivano nei colori nuovi: due
   tavolozze nella stessa colonna, ed e' la prima cosa che si vedeva scendendo.
   Ora e' lo STESSO array: un colore si cambia in :root e cambia in pagina. */
const SCH = SC;

/* ------------------------------------------------- due conteggi e un indice
   Non esistono come serie da nessuna parte: si costruiscono qui, una volta, dalla
   lista delle attivita' e dal modello metabolico, perche' li leggono piu' riquadri.
   Le soglie stanno in costanti con un nome, non sepolte in un `if`: sono scelte, e
   una scelta che non si vede non si puo' discutere. */

/* Una mezza maratona misura 21,0975 km. Una traccia GPS della stessa gara cade fra
   20,5 e 22: sotto e' un lungo, sopra ha smesso di essere una mezza. Con questa
   forbice l'archivio ne conta 58, dal 2019 a oggi — ventisei nel solo 2025. Il conto
   vero lo rifa' `feats` a ogni build e la didascalia legge quello. */
const HALF_LO = 20500, HALF_HI = 22000;
/* "Salita lunga": oltre un'ora, e dislivello importante. Importante rispetto a COSA
   e' la domanda vera, e la risposta viene dai dati: la mediana del dislivello di
   un'uscita oltre l'ora, in questo archivio, e' 647 m — cioe' 647 m e' l'ordinario,
   non un indicatore di sforzo. La soglia va sopra l'ordinario, e 1.000 m e' il primo
   numero leggibile che ci sta: seleziona 654 uscite su 2.027, circa una a settimana.
   I due conteggi si rifanno a ogni build (vedi `feats`): erano 541 su 1.603 finche'
   il 2022 mancava, e una didascalia con dentro un numero a mano sarebbe gia' falsa. */
const CLIMB_SECS = 3600, CLIMB_GAIN = 1000;
const feats = (() => {
  const half = new Array(N).fill(0), climb = new Array(N).fill(0), long = [];
  for (const [i, sp, s, m, up] of D.acts) {
    if (sp === 1 && m >= HALF_LO && m <= HALF_HI) half[i] += 1;
    if (s > CLIMB_SECS) {
      long.push(up);
      if (up >= CLIMB_GAIN) climb[i] += 1;
    }
  }
  /* La mediana del dislivello di un'uscita oltre l'ora e' la SOGLIA che giustifica
     CLIMB_GAIN, e va ricontata a ogni build: era 648 m su 1.603 uscite prima che il
     backfill rimettesse dentro il 2022, e un numero scritto a mano nella didascalia
     sarebbe gia' vecchio adesso. Le didascalie leggono queste, non delle costanti. */
  long.sort((a, b) => a - b);
  return { half, climb, long,
    medGain: long.length ? long[Math.floor(long.length / 2)] : 0,
    halfTot: half.reduce((a, b) => a + b, 0),
    climbTot: climb.reduce((a, b) => a + b, 0) };
})();

/* Somma mobile all'indietro: quanti ne sono caduti negli ultimi `win` giorni.
   Le mezze e le salite lunghe erano due istogrammi mensili, cioe' due file di
   picchi con dei buchi in mezzo — e un buco li' non vuol dire "niente", vuol dire
   "quel mese no" (2026-08-14: "devono essere quelle medie mobili, non spike").
   Un conteggio che scorre risponde alla domanda vera, che e' quanto fitto si va,
   non quale casella del calendario e' toccata.
   I primi `win` giorni restano vuoti invece di salire da zero: una somma mobile
   che comincia da meta' finestra disegna una rampa che non e' successa. */
const trailing = (arr, win, from0) => {
  const o = new Array(N).fill(null);
  let acc = 0;
  for (let i = 0; i < N; i++) {
    acc += arr[i] || 0;
    if (i >= win) acc -= arr[i - win] || 0;
    if (i >= (from0 || 0) + win) o[i] = acc;
  }
  return o;
};
const HALF_WIN = 365, CLIMB_WIN = 90;
/* calcolate una volta: il riquadro si ridisegna a ogni cambio di finestra */
const halfRoll = trailing(feats.half, HALF_WIN, daysOf("act"));
const climbRoll = trailing(feats.climb, CLIMB_WIN, daysOf("act"));

/* ------------------------------------------------- passo contro battito (misurato)
   La domanda vera dietro al FatMax non e' "dove sta la banda" — quella e' un numero
   di letteratura e si muove di due battiti — ma "la mia capacita' di bruciare grassi
   cambia?". Non c'e' modo di misurarla qui: servirebbe una maschera. C'e' pero' una
   cosa che le sta accanto e che l'archivio misura davvero, tutti i giorni:
   **quanto vado forte a parita' di battito**.

   L'unita' e' l'attivita', non la giornata: una giornata con un lungo e una sgambata
   ha una media che non e' successa in nessuno dei due. Il passo e' il GAP di
   Intervals (grade adjusted pace): senza correzione della pendenza un'uscita in
   salita e una in piano non si possono confrontare, e qui si confronta.

   Tre filtri, tutti per lo stesso motivo — togliere quello che non e' un'uscita
   aerobica continua:
     · almeno mezz'ora (sotto, la media della FC e' ancora il riscaldamento);
     · FC media fra 120 e 170 (fuori sono passeggiate o ripetute, e in entrambi i
       casi la media di un'attivita' polarizzata non descrive nessun momento di
       quell'attivita');
     · niente attivita' ricostruite dall'export Strava, che non hanno FC.

   Resta un limite che non si toglie con un filtro, ed e' il piu' grosso: **la FC
   media di un'uscita e' una media**. Due uscite con la stessa media possono essere
   una continua e una a strappi. Il fondo di questa nuvola e' quel rumore. */
const EF_MIN_SECS = 1800, EF_HR_LO = 120, EF_HR_HI = 170;
const aero = (() => {
  const acts = [], perDay = new Array(N).fill(null), cnt = new Array(N).fill(0);
  for (const a of D.acts) {
    const i = a[0], sp = a[1], secs = a[2], bf = a[6], hr = a[7] || 0,
          gap = (a[8] || 0) / 100, t = a[9] ? a[9] / 10 : null;
    if (bf || sp !== 1 || !hr || !gap) continue;
    if (secs < EF_MIN_SECS || hr < EF_HR_LO || hr > EF_HR_HI) continue;
    const ef = gap * 60 / hr;                 /* metri al minuto per battito */
    acts.push({ i, hr, kmh: gap * 3.6, ef, t, secs });
    perDay[i] = (perDay[i] || 0) + ef; cnt[i] += 1;
  }
  for (let i = 0; i < N; i++) if (cnt[i]) perDay[i] /= cnt[i];
  if (!acts.length) return null;
  const i0 = acts.reduce((m, a) => Math.min(m, a.i), N);
  D.first.ef = i0;
  /* le tre ere non sono decorative: nel 2022 l'archivio non ha FC (le attivita'
     arrivano dall'export Strava) e nel 2024 e' cambiato l'orologio, quindi il
     confronto onesto e' fra blocchi omogenei, non fra un anno e l'altro */
  const yearOf = i => dayDate(i).getFullYear();
  const era = i => yearOf(i) <= 2021 ? 0 : yearOf(i) <= 2024 ? 1 : 2;
  return { acts, day:perDay, era,
    eras:["fino al 2021", "2023–2024", "dal 2025"], i0 };
})();

/* g/min di grassi stimati: i grammi del giorno divisi per i minuti di allenamento
   del giorno. E' il modello, non una misura — eredita per intero il +/-40% di
   incertezza di metabolismo.py — ma e' il modello espresso nell'unita' in cui la
   letteratura parla di ossidazione dei grassi, e in cui un giorno da due ore e uno
   da venti minuti si possono mettere sullo stesso asse. */
const fatRate = (() => {
  const M = D.metab || {};
  if (!Array.isArray(M.fat_g_est) || !Array.isArray(M.train_min)) return null;
  const o = new Array(N).fill(null);
  let i0 = null;
  for (let i = 0; i < N; i++) {
    const g = M.fat_g_est[i], m = M.train_min[i];
    if (g === null || g === undefined || !m || m < 20) continue;
    o[i] = g / m;
    if (i0 === null) i0 = i;
  }
  if (i0 === null) return null;
  D.first.fat_rate = i0;
  return o;
})();

/* Quanto vale davvero il secondo asse della dieta: le PROTEINE residue, cioe' quello
   che il modello a un asse solo assumeva costante. Si calcola qui invece di scriverlo
   nel piede a mano — un numero congelato in una frase invecchia senza dirlo. */
function protResidue() {
  const M = D.metab || {};
  if (!Array.isArray(M.cho_pct_60d) || !Array.isArray(M.fat_pct_60d)) return "la quota proteica";
  const v = [];
  for (let i = 0; i < N; i++) {
    const c = M.cho_pct_60d[i], f = M.fat_pct_60d[i];
    if (c === null || c === undefined || f === null || f === undefined) continue;
    v.push(100 - c - f);
  }
  if (v.length < 30) return "la quota proteica";
  return `la quota proteica, che qui si muove fra il ${nf(Math.min(...v), 0)} e il ` +
    `${nf(Math.max(...v), 0)} % dell'energia`;
}

/* -------------------------------------------- i grammi bruciati DENTRO la banda
   Michele, 17/08/2026: «vorrei anche un grafico che, considerando i minuti dentro
   la banda, mostri i grassi bruciati ogni giorno».

   Si ricava dai due numeri che il modello metabolico gia' scrive, senza aggiungere
   nessuna ipotesi nuova:

       grammi in banda = minuti dentro la banda FatMax x MFO di quel giorno

   `mfo_g_min` e' il picco di ossidazione, cioe' quanto si brucia AL CENTRO della
   banda. Dentro la banda ma ai bordi si brucia meno — la parabola di `fatox` scende
   fino al 90 % del picco ai due estremi, che e' la definizione stessa di banda —
   quindi questo numero e' un **tetto**, non una media: sta entro il 10 % sopra il
   vero, e sopra, mai sotto. Sta scritto anche nel piede del riquadro, perche' un
   tetto letto come una media e' il modo in cui un modello diventa un vanto.

   Perche' tenerlo separato da `fat_g_est`, che sono i grammi di TUTTA la giornata:
   quello risponde a "quanto grasso ho ossidato", questo a "quanto ne ho ossidato
   nel posto in cui volevo ossidarlo". Sono la stessa fisiologia guardata da due
   parti, e la loro distanza e' quanto allenamento e' finito fuori banda. */
const fatBand = (() => {
  const M = D.metab || {};
  if (!Array.isArray(M.fatmax_min) || !Array.isArray(M.mfo_g_min)) return null;
  const o = new Array(N).fill(null);
  let i0 = null;
  for (let i = 0; i < N; i++) {
    const m = M.fatmax_min[i], r = M.mfo_g_min[i];
    if (m === null || m === undefined || r === null || r === undefined) continue;
    o[i] = m * r;
    if (i0 === null) i0 = i;
  }
  if (i0 === null) return null;
  D.first.fat_band = i0;
  return o;
})();

/* Heat strain. Non e' una misura: nessuno ha mai preso la temperatura interna di
   Michele. E' un INDICE costruito, e i pesi sono qui in chiaro apposta —
   c'e' gia' il precedente di microbiome_model.py, e la regola e' la stessa: un
   numero costruito si pubblica solo insieme alla sua formula.

       HS = (T − 22 °C)⁺ × ore in movimento × TSS del giorno / 100

   I due pesi. 22 °C: la temperatura e' quella del SENSORE AL POLSO durante
   l'uscita, non dell'aria — la mediana sull'archivio e' 19,7 °C e 22 taglia il
   terzo piu' caldo (37 % dei giorni misurati). TSS/100: cento e' una giornata di
   allenamento piena, quindi il fattore vale 1 su una giornata normale e scala di
   li'. Il prodotto sono gradi-ora di caldo pesati per quanto si stava lavorando
   dentro: due ore a 30 °C con 100 TSS fanno 16, quattro ore a 26 °C con 200 ne
   fanno 32.

   Prima del 2019-06-19 il carico non esiste (Strava senza HR ne' potenza): li' il
   prodotto verrebbe zero per assenza, non per freddo, quindi resta nullo. */
const HS_SOGLIA_C = 22, HS_TSS_RIF = 100;
const heat = (() => {
  const T = (D.metab || {}).temp_c;
  if (!Array.isArray(T)) return null;
  const load0 = daysOf("load");
  const o = new Array(N).fill(null);
  for (let i = load0; i < N; i++) {
    const t = T[i];
    if (t === null || t === undefined) continue;   /* niente sensore, niente indice */
    o[i] = Math.max(0, t - HS_SOGLIA_C) * (secsOf.secs[i] / 3600) *
           ((D.load[i] || 0) / HS_TSS_RIF);
  }
  return o;
})();

/* Momento metabolico: una scala −20..+20 che poggia su un massimo di sei componenti,
   e `mm_n` dice su quante poggia davvero quel giorno. Un −8 costruito su tre
   componenti e uno costruito su sei non sono lo stesso numero, e disegnarli con lo
   stesso tratto sarebbe la bugia piu' economica di tutta la pagina. Sotto quattro
   componenti non si disegna: meglio un pezzo di serie mancante che un pezzo di serie
   che finge. Il taglio cade in un punto solo — i giorni sotto soglia sono un blocco
   unico, dall'inizio del diario al giorno in cui e' arrivato l'orologio — quindi la
   linea non si sbriciola, comincia piu' tardi. */
const MM_MIN_COMP = 4;
const mmDraw = (() => {
  const M = (D.metab || {}).mm, C_ = (D.metab || {}).mm_n;
  if (!Array.isArray(M)) return null;
  const arr = new Array(N).fill(null);
  let drawn = 0, dropped = 0, i0 = null;
  for (let i = 0; i < N; i++) {
    const v = M[i];
    if (v === null || v === undefined) continue;
    if (!(C_ && C_[i] !== null && C_[i] >= MM_MIN_COMP)) { dropped++; continue; }
    arr[i] = v; drawn++;
    if (i0 === null) i0 = i;
  }
  if (!drawn) return null;
  /* il riquadro deve partire da dove la serie DISEGNATA comincia, non da dove
     comincia la colonna: altrimenti l'asse dichiara mezzo anno che non si vede */
  D.first.mm_drawn = i0;
  return { arr, drawn, dropped, i0 };
})();

const TILES = [
  /* ---- Carico ---- */
  { panel:"carico", cls:"wide", h:190, first:"load",
    src:"modello", title:"Fitness e fatica", cap:"CTL e ATL · giorno per giorno",
    legend:[["Fitness (CTL)", SCH[0]], ["Fatica (ATL)", SCH[1]]],
    now:() => D.ctl[N - 1], nowFmt:FMT.num0, nowUnit:"CTL oggi",
    kind:rLines, spec:{ zero:true, fmt:FMT.num0, series:[
      { name:"Fitness (CTL)", col:SCH[0], area:true, get:(a, b) => D.ctl.slice(a, b + 1).map((v, k) => [a + k, v]) },
      { name:"Fatica (ATL)", col:SCH[1], get:(a, b) => D.atl.slice(a, b + 1).map((v, k) => [a + k, v]) },
    ] },
    foot:"Arancio sopra blu: si sta scavando." },

  { panel:"carico", cls:"wide", h:150, first:"load",
    src:"modello", title:"Forma", cap:"CTL − ATL · sopra lo zero si è freschi",
    now:() => D.ctl[N - 1] - D.atl[N - 1], nowFmt:FMT.num0, nowUnit:"forma oggi",
    kind:rDiverge, spec:{ name:"Forma", fmt:FMT.num0,
      get:(a, b) => { const o = []; for (let i = a; i <= b; i++) o.push([i, D.ctl[i] === null || D.atl[i] === null ? null : D.ctl[i] - D.atl[i]]); return o; } },
    foot:"Blu credito, rosso debito." },

  { panel:"carico", h:170, first:"load", src:"misurato", title:"Carico", cap:"TSS sommato",
    now:() => D.load.slice(N - 7).reduce((a, b) => a + (b || 0), 0), nowFmt:FMT.num0, nowUnit:"TSS ultimi 7 gg",
    kind:rBars, spec:{ name:"Carico", arr:D.load, how:"sum", col:"var(--s1)", fmt:FMT.tss } },

  { panel:"carico", h:170, first:"act", src:"misurato", title:"Ore", cap:"tempo in movimento",
    now:() => secsOf.secs.slice(N - 7).reduce((a, b) => a + b, 0) / 3600, nowFmt:FMT.num1, nowUnit:"ore ultimi 7 gg",
    kind:rBars, spec:{ name:"Ore", arr:secsOf.secs, how:"sum", scale:v => v / 3600,
      col:"var(--s3)", fmt:FMT.hours } },

  /* ---- Notte ----
     Le nuvole di punti stanno su 150 px e non su 180 (2026-08-14: "i punti tipo HRV
     potrebbero essere un po' piu' compatti in Y"). Il dominio y non cambia — lo detta
     sempre la media mobile — quindi non si perde escursione: si perde spazio bianco,
     e la colonna intera diventa scorribile invece che da scorrere. */
  { panel:"notte", h:150, first:"sleep",
    src:"misurato", title:"Durata del sonno", cap:"ogni notte · media mobile 7 giorni",
    now:() => { const r = rolling(D.sleep, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.hhmm, nowUnit:"media 7 notti",
    kind:rCloud, spec:{ name:"Sonno", arr:D.sleep, col:"var(--s1)", fmt:FMT.hhmm,
      band:[420, 480], win:7, ytick:v => (v / 60).toFixed(0) + "h" },
    foot:"Fascia: 7–8 ore." },

  { panel:"notte", h:150, first:"score", src:"modello", title:"Punteggio del sonno",
    cap:"come lo valuta l'orologio · 0–100",
    now:() => { const r = rolling(D.score, N - 14, N - 1, 14); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"media 14 notti",
    kind:rCloud, spec:{ name:"Punteggio", arr:D.score, col:"var(--s3)", fmt:FMT.num0, win:14 } },

  /* ---- Recupero ---- */
  { panel:"recupero", h:150, first:"hrv",
    src:"misurato", title:"HRV", cap:"variabilità cardiaca al risveglio · media mobile 7 giorni",
    now:() => { const r = rolling(D.hrv, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"ms, media 7 gg",
    kind:rCloud, spec:{ name:"HRV", arr:D.hrv, col:"var(--s2)", fmt:FMT.ms, win:7 },
    foot:"Conta la media, non il singolo giorno." },

  { panel:"recupero", h:150, first:"rhr", src:"misurato", title:"Frequenza a riposo",
    cap:"battiti al minuto · media mobile 7 giorni",
    now:() => { const r = rolling(D.rhr, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"bpm, media 7 gg",
    kind:rCloud, spec:{ name:"FC a riposo", arr:D.rhr, col:"var(--s1)", fmt:FMT.bpm, win:7 } },

  { panel:"recupero", h:150, first:"steps", src:"misurato", title:"Passi", cap:"al giorno · media mobile 7 giorni",
    now:() => { const r = rolling(D.steps, N - 7, N - 1, 7); return r[r.length - 1]; },
    nowFmt:FMT.num0, nowUnit:"passi/giorno",
    kind:rCloud, spec:{ name:"Passi", arr:D.steps, col:"var(--s4)", fmt:FMT.num0, zero:true,
      ytick:v => v >= 1000 ? (v / 1000) + "k" : String(v) } },

  /* ---- Volume ---- */
  { panel:"volume", h:170, first:"act", src:"misurato", title:"Mix per sport",
    cap:"ore, impilate", legend:S.map((s, i) => [s, SCH[i]]),
    kind:rStack, spec:{ arrs:secsOf.bySport, names:S, cols:SC, scale:v => v / 3600,
      fmt:FMT.hours } },

  { panel:"volume", h:170, first:"act", src:"misurato", title:"Dislivello", cap:"metri di salita sommati",
    now:() => secsOf.gain.reduce((a, b) => a + b, 0), nowFmt:FMT.num0, nowUnit:"m in tutto",
    kind:rBars, spec:{ name:"Dislivello", arr:secsOf.gain, how:"sum", col:"var(--s4)",
      fmt:FMT.m, ytick:v => v >= 1000 ? (v / 1000) + "k" : String(v) } },

  { panel:"volume", h:150, first:"act", src:"misurato", title:"Mezze maratone",
    cap:`corse fra ${nf(HALF_LO / 1000, 1)} e ${nf(HALF_HI / 1000, 0)} km · quante negli ultimi ${HALF_WIN} giorni, giorno per giorno`,
    now:() => halfRoll[N - 1],
    nowFmt:FMT.num0, nowUnit:"nell'ultimo anno",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + (v === 1 ? " mezza" : " mezze"),
      series:[{ name:"Mezze, 12 mesi", col:SCH[0], area:true,
        get:(a, b) => halfRoll.slice(a, b + 1).map((v, k) => [a + k, v]) }] },
    foot:`La distanza vera è 21,0975 km: la forbice ${nf(HALF_LO / 1000, 1)}–${nf(HALF_HI / 1000, 0)} km ` +
      "tiene dentro la stessa gara misurata da GPS diversi e lascia fuori il lungo da venti e il trentino. " +
      `La linea è una <strong>somma mobile a ${HALF_WIN} giorni</strong>: quante ne sono cadute nei dodici ` +
      `mesi precedenti a quel giorno. Sono ${nf(feats.halfTot)} in tutto l'archivio, cioè in un istogramma ` +
      "mensile quasi altrettante colonne alte uno separate da buchi — e un buco lì si legge come una pausa " +
      "senza esserlo." },

  { panel:"volume", h:150, first:"act", src:"misurato", title:"Salite lunghe",
    cap:`oltre un'ora e almeno ${nf(CLIMB_GAIN, 0)} m di dislivello · quante negli ultimi ${CLIMB_WIN} giorni, giorno per giorno`,
    now:() => climbRoll[N - 1],
    nowFmt:FMT.num0, nowUnit:`negli ultimi ${CLIMB_WIN} giorni`,
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + (v === 1 ? " uscita" : " uscite"),
      series:[{ name:"Salite lunghe, 90 giorni", col:SCH[3], area:true,
        get:(a, b) => climbRoll.slice(a, b + 1).map((v, k) => [a + k, v]) }] },
    foot:`La soglia è misurata, non scelta a occhio: la <strong>mediana</strong> del dislivello di ` +
      `un'uscita oltre l'ora, qui dentro, è ${nf(feats.medGain, 0)} m — l'ordinario. ${nf(CLIMB_GAIN, 0)} m ` +
      `sta sopra l'ordinario e seleziona ${nf(feats.climbTot)} uscite su ${nf(feats.long.length)}, ` +
      "circa una a settimana. " +
      `Finestra di ${CLIMB_WIN} giorni e non di dodici mesi perché qui la densità cambia dentro la stagione, ` +
      "e una finestra lunga la spianerebbe proprio dove c'è qualcosa da vedere." },

  /* ---- Incroci: nessun riquadro fisso ----
     C'erano sei nuvole scelte a mano (sonno contro carico, HRV contro sonno, …) piu'
     peso e massa grassa. Sceglierle a mano era il problema: erano le sei coppie a cui
     qualcuno aveva pensato, non le sei che dicono qualcosa, e stavano li' anche quando
     il loro r era zero da due anni. Adesso la sezione e' UN grafico solo con dieci
     preset ricavati dai dati (2026-08-14), piu' due slot che Michele si riempie da se'.
     Le coppie sono scelte cosi': si calcolano tutte le 2.958 combinazioni, si buttano
     quelle dentro la stessa sezione (fibre x magnesio e' il cablaggio del database
     alimenti, non una scoperta), e di quelle che restano si tengono le dieci che
     dicono qualcosa di non ovvio — compresi gli zeri, che qui sono il risultato. */

  /* ---- Metabolismo: presenti solo se metabolismo.csv era sul disco al build ---- */
  ...metabTiles(),

  /* ---- Tavola: presenti solo se _nutrition.csv era sul disco al build ---- */
  ...nutriTiles(),
];

/* Stessa regola dei riquadri della tavola: se il CSV non c'era al build, la sezione
   non esiste invece di comparire vuota. Qui in piu' ogni riquadro deve dichiarare
   che cos'e' — la temperatura e' un sensore vero letto nel posto sbagliato, la
   banda FatMax e l'heat strain sono modelli — perche' un numero costruito e un
   numero misurato hanno lo stesso aspetto su un grafico. */
function metabTiles() {
  const M = D.metab || {};
  const has = k => Array.isArray(M[k]);
  const t = [];

  if (has("temp_c") && has("temp_min_c") && has("temp_max_c")) {
    t.push({ panel:"metabolismo", cls:"wide", h:190, first:"mb_temp_c",
      src:"misurato", title:"Temperatura", cap:"sensore al polso durante l'uscita · banda min–max del giorno, media mobile 30 giorni",
      legend:[["Media dell'uscita", SCH[1]], ["Fra minimo e massimo", "rgba(234,67,53,.35)"]],
      now:() => lastMean(M.temp_c, 30), nowFmt:v => nf(v, 1) + " °C", nowUnit:"media 30 gg",
      kind:rBand, spec:{ name:"Temperatura", mid:M.temp_c, lo:M.temp_min_c, hi:M.temp_max_c,
        col:SCH[1], win:30, fmt:v => nf(v, 1) + " °C" },
      dataNote:"solo i giorni con un'uscita",
      foot:"<strong>Non è il meteo.</strong> I campi meteo dell'API sono vuoti su tutte e 2.257 " +
        "le attività: questo è l'orologio, cioè l'aria a un centimetro da un corpo che " +
        "scalda. La mediana di gennaio è 13,8 °C, che in Bergamasca all'alba non è " +
        "l'aria di gennaio. Serve per il ciclo stagionale e per i confronti relativi — " +
        "luglio sta 12 °C sopra gennaio — e non serve a niente come temperatura esterna. " +
        "Esiste solo nei giorni in cui l'orologio era acceso a misurare qualcosa." });
  }

  if (heat) {
    t.push({ panel:"metabolismo", h:170, first:"load", src:"modello", title:"Heat strain",
      cap:`indice costruito · gradi-ora sopra ${HS_SOGLIA_C} °C pesati per il carico · sommati al mese`,
      now:() => heat.reduce((a, b) => a + (b || 0), 0), nowFmt:FMT.num0, nowUnit:"indice, in tutto",
      kind:rBars, spec:{ name:"Heat strain", arr:heat, how:"sum", col:"var(--s2)",
        fmt:v => nf(v, 0) },
      dataNote:"indice, non una misura",
      foot:`<strong>Indice costruito, non una misura fisiologica</strong>: nessuno ha mai preso ` +
        `la temperatura interna. La formula, pesi compresi, è <span class="mono">(T − ` +
        `${HS_SOGLIA_C} °C)⁺ × ore in movimento × TSS / ${HS_TSS_RIF}</span>. ` +
        `${HS_SOGLIA_C} °C perché taglia il terzo più caldo dei giorni misurati (mediana 19,7 °C) ` +
        `e ${HS_TSS_RIF} TSS perché è una giornata piena, quindi il fattore vale 1 su una ` +
        "giornata normale. Prima del giugno 2019 il carico non è registrato e l'indice resta vuoto: " +
        "uno zero lì sarebbe assenza di dati travestita da assenza di caldo." });
  }

  if (has("fatmax_hr") && has("fatmax_lo_hr") && has("fatmax_hi_hr")) {
    t.push({ panel:"metabolismo", cls:"wide", h:180, first:"mb_fatmax_hr",
      src:"modello", title:"FatMax", cap:"battiti al minuto · la banda in cui il modello mette il massimo consumo di grassi",
      legend:[["FatMax", SCH[2]], ["Banda", "rgba(30,142,62,.35)"]],
      now:() => lastMean(M.fatmax_hr, 45), nowFmt:FMT.num0, nowUnit:"bpm, media 45 gg",
      kind:rBand, spec:{ name:"FatMax", mid:M.fatmax_hr, lo:M.fatmax_lo_hr, hi:M.fatmax_hi_hr,
        col:SCH[2], win:45, fmt:FMT.bpm },
      dataNote:"modello, non un test da laboratorio",
      foot:"<strong>È un modello</strong>, ancorato ad Achten e Jeukendrup (2002) su una coorte " +
        "allenata: il FatMax vero si misura con una prova a gradini e l'analisi dei gas, e " +
        "quella prova non è mai stata fatta. Resta piatto a 137 bpm fino al 2024 perché fino a " +
        "lì il modello non aveva abbastanza dati per spostarsi dal valore della coorte: la " +
        "discesa verso 132 è la sola parte che dice qualcosa su Michele e non sulla letteratura." });
  }

  /* i minuti in banda diventano grammi: e' la domanda che i minuti da soli non
     chiudono — "e quindi quanto grasso e' andato via?" */
  if (fatBand) {
    t.push({ panel:"metabolismo", h:170, first:"fat_band",
      src:"modello", title:"Grassi bruciati in banda",
      cap:"minuti dentro il FatMax × MFO di quel giorno · grammi, sommati al mese",
      now:() => { const s = stats(fatBand.slice(N - 90).filter(v => v !== null));
        return s ? s.mean : null; },
      nowFmt:v => nf(v, 0), nowUnit:"g al giorno, ultimi 90 gg",
      kind:rBars, spec:{ name:"Grassi in banda", arr:fatBand, how:"sum",
        col:"var(--s3)", fmt:v => nf(v, 0) + " g" },
      dataNote:"modello, non una misura",
      foot:"<strong>È un tetto.</strong> <span class=\"mono\">mfo_g_min</span> è l'ossidazione " +
        "al <em>centro</em> della banda; ai bordi la parabola del modello scende al 90 % del " +
        "picco, quindi il vero sta fra questo numero e il suo 90 %. Eredita le ipotesi del " +
        "FatMax e i suoi ±40 %: <strong>vale la variazione</strong>. La distanza da «grassi al " +
        "minuto», che conta tutta la giornata, è l'allenamento finito fuori banda." });
  }

  /* --- i grammi, e la sola cosa misurata che ci gira intorno --------------- */

  if (fatRate) {
    t.push({ panel:"metabolismo", h:150, first:"fat_rate",
      src:"stima", title:"Grassi al minuto",
      cap:"grammi stimati diviso i minuti di allenamento di quel giorno · media mobile 45 giorni",
      now:() => lastMean(fatRate, 45), nowFmt:v => nf(v, 2), nowUnit:"g/min, media 45 gg",
      kind:rCloud, spec:{ name:"Grassi", arr:fatRate, col:SCH[2], win:45,
        fmt:v => nf(v, 2) + " g/min", ytick:v => nf(v, 2) },
      dataNote:"modello, non una misura",
      foot:"<strong>Vale la sua variazione</strong>: sul livello assoluto l'incertezza è " +
        "dell'ordine del ±40 %. Grammi stimati del giorno diviso i minuti di quel giorno; " +
        "i giorni sotto i venti minuti restano fuori. Il riferimento della letteratura è " +
        "0,52 g/min a digiuno (Achten 2003), e qui si sta sotto perché la media di un'uscita " +
        "comprende anche i tratti sopra la banda. Dal 17/08/2026 il modello legge <strong>due " +
        "macro</strong>, carboidrati e grassi abituali dei 60 giorni prima, con le due pendenze " +
        "dei due bracci di FASTER (Volek 2016). A proteine ferme i due assi coincidono; qui " +
        "la differenza la fa " + protResidue() + "." });
  }

  if (aero) {
    /* La nuvola che risponde alla domanda: a parita' di battito, vado piu' forte?
       Tre ere, un colore per era, e la retta unica sopra a dire la relazione media.
       Se le tre nuvole stanno una sopra l'altra qualcosa e' cambiato; se si
       sovrappongono, non e' cambiato niente — ed e' una risposta anche quella. */
    t.push({ panel:"metabolismo", h:150, first:"ef",
      src:"misurato", title:"Efficienza aerobica",
      cap:"metri al minuto per battito, media delle corse del giorno · media mobile 45 giorni",
      now:() => lastMean(aero.day, 45), nowFmt:v => nf(v, 2), nowUnit:"m/min per battito, media 45 gg",
      kind:rCloud, spec:{ name:"Efficienza", arr:aero.day, col:SCH[0], win:45,
        fmt:v => nf(v, 2), ytick:v => nf(v, 2) },
      dataNote:"misurato",
      foot:"Sale quando la macchina aerobica migliora, <strong>ma sale anche se si sceglie di " +
        "correre più forte</strong>: il numero da solo non sa distinguere le due cose. " +
        "È la nuvola di sopra ridotta a un numero al giorno: passo GAP in metri al minuto " +
        "diviso i battiti al minuto. Per distinguerle c'è la nuvola accanto: lì il battito è " +
        "sull'asse e la scelta si vede." });

  }

  if (mmDraw) {
    t.push({ panel:"metabolismo", cls:"wide", h:170, first:"mm_drawn",
      src:"modello", title:"Momento metabolico",
      cap:`scala −20 → +20 · disegnato solo dove poggia su almeno ${MM_MIN_COMP} componenti su 6`,
      now:() => lastMean(mmDraw.arr, 14), nowFmt:FMT.num1, nowUnit:"momento, media 14 gg",
      kind:rDiverge, spec:{ name:"Momento", fmt:FMT.num1,
        get:(a, b) => mmDraw.arr.slice(a, b + 1).map((v, k) => [a + k, v]) },
      dataNote:`${nf(mmDraw.drawn)} giorni disegnati, ${nf(mmDraw.dropped)} scartati`,
      foot:`Poggia su sei componenti — forma, fatica, sonno, HRV, frequenza a riposo, dieta — e ` +
        `<span class="mono">mm_n</span> dice su quante poggia davvero. Un −8 costruito su tre ` +
        `componenti e uno costruito su sei non sono lo stesso numero, quindi sotto ` +
        `${MM_MIN_COMP} non si disegna: ${nf(mmDraw.dropped)} giorni restano fuori, e sono un ` +
        `blocco solo — dall'inizio del diario al 20 gennaio 2025, cioè fino al giorno in cui ` +
        `l'orologio ha portato sonno, HRV e frequenza a riposo. La linea non comincia tardi ` +
        `per caso: comincia quando ha di che reggersi.` });
  }

  return t;
}

/* Le serie del cibo arrivano da una repo privata come aggregati giornalieri, e
   possono benissimo non esserci. Costruire i riquadri da una funzione, invece che
   scriverli a mano nella lista, fa sparire l'intera sezione quando il file manca —
   invece di lasciare in pagina otto rettangoli che dicono "nessun dato". */
function nutriTiles() {
  const N_ = D.nutri || {};
  if (!N_.kcal) return [];
  const has = k => Array.isArray(N_[k]);
  const t = [];
  /* Gli ultimi sette giorni con del cibo dentro la finestra. Non "gli ultimi sette
     giorni di calendario": i giorni scritti da Cronometer non portano food_id,
     quindi le dodici caselle lì sono vuote, e sette colonne per metà vuote sono
     peggio di sette colonne piene di una settimana un po' più indietro. */
  const ddGiorni = (a, b) => {
    if (!has("dd_fagioli")) return [];
    const lo = a === undefined ? 0 : a, hi = b === undefined ? N - 1 : b, out = [];
    for (let i = hi; i >= lo && out.length < 7; i--) {
      const v = N_.dd_fagioli[i];
      if (v !== null && v !== undefined) out.push(i);
    }
    return out.reverse();
  };
  const MICR = D.microbes || {};
  const GEN = [["Faecalibacterium", "🌾"], ["Bacteroides", "🥩"], ["Prevotella", "🌱"],
               ["Bifidobacterium", "🍶"], ["Roseburia", "🌾"], ["Blautia", "🌱"],
               ["Ruminococcus", "🥔"], ["Eubacterium", "🌾"], ["Akkermansia", "🫐"],
               ["Lactobacillus", "🍶"]].filter(([g]) => Array.isArray(MICR[g]));

  t.push({ panel:"tavola", h:146, first:"n_kcal", src:"misurato", title:"Quanto è raccontato",
    cap:"kcal osservate contro ricostruite · i piatti dichiarati sono ~75 % della dieta", legend:[["Osservate", SCH[2]], ["Ricostruite", SCH[3]]],
    now:() => { const a = N_.kcal_observed, b = N_.kcal_assumed; let o = 0, s = 0;
      for (let i = 0; i < N; i++) if (a[i] !== null) { o += a[i]; s += a[i] + (b[i] || 0); }
      return s ? 100 * o / s : null; },
    nowFmt:v => nf(v, 0) + " %", nowUnit:"osservato",
    kind:rStack, spec:{ arrs:[N_.kcal_observed, N_.kcal_assumed],
      names:["Osservate", "Ricostruite"], cols:["var(--s3)", "var(--s4)"], fmt:FMT.num0 },
    foot:"Osservato = un pasto raccontato. Ricostruito = lo schema mensile dichiarato, che copre circa tre quarti della dieta." });

  t.push({ panel:"tavola", h:146, first:"n_kcal", src:"ricostruito", title:"Energia",
    cap:"kcal al giorno · media mobile 7 giorni",
    now:() => lastMean(N_.kcal, 7),
    nowFmt:FMT.num0, nowUnit:"kcal, media 7 gg",
    kind:rCloud, spec:{ name:"Energia", arr:N_.kcal, col:"var(--s2)", fmt:FMT.num0,
      zero:true, win:7 } });

  t.push({ panel:"tavola", h:146, first:"n_fiber_g", src:"ricostruito", title:"Fibre",
    cap:"grammi al giorno · la fascia è l'obiettivo, 30 g",
    now:() => lastMean(N_.fiber_g, 7),
    nowFmt:FMT.num1, nowUnit:"g, media 7 gg",
    kind:rCloud, spec:{ name:"Fibre", arr:N_.fiber_g, col:"var(--s3)", fmt:v => nf(v, 1) + " g",
      band:[30, 45], zero:true, win:7 } });

  if (has("plants_7d")) t.push({ panel:"tavola", h:146, first:"n_plants_7d",
    src:"ricostruito", title:"Piante diverse", cap:"specie vegetali distinte negli ultimi 7 giorni · obiettivo 30",
    now:() => { for (let i = N - 1; i >= 0; i--) if (N_.plants_7d[i] !== null) return N_.plants_7d[i]; return null; },
    nowFmt:FMT.num0, nowUnit:"su 30",
    kind:rCloud, spec:{ name:"Piante", arr:N_.plants_7d, col:"var(--s1)", fmt:FMT.num0,
      band:[30, 30], zero:true, win:14 },
    foot:"Cereali, legumi, frutta secca, erbe e spezie contano." });

  t.push({ panel:"tavola", h:146, first:"n_carb_g", src:"ricostruito", title:"Carboidrati contro fabbisogno",
    cap:"ingeriti e stimati dal TSS del giorno · media mobile 7 giorni",
    legend:[["Ingeriti", SCH[0]], ["Stimati dal carico", SCH[1]]],
    now:() => lastMean(N_.carb_gap_g, 7),
    nowFmt:v => (v > 0 ? "+" : "") + nf(v, 0), nowUnit:"g di scarto, 7 gg",
    /* `mm:7` per l'annotazione di Michele del 22/08 («Moving averages?? ;)»). Sette
       giorni e non quattordici perche' e' la finestra che questo riquadro dichiara
       gia' nel suo numero grande — «g di scarto, 7 gg» — e due finestre diverse
       nello stesso riquadro sono due letture che non tornano fra loro. */
    kind:rLines, spec:{ zero:true, mm:7, fmt:v => nf(v, 0) + " g", series:[
      { name:"Ingeriti", col:SCH[0], area:true, get:(a, b) => N_.carb_g.slice(a, b + 1).map((v, k) => [a + k, v]) },
      { name:"Stimati dal carico", col:SCH[1], get:(a, b) => N_.carb_target_g.slice(a, b + 1).map((v, k) => [a + k, v]) },
    ] },
    foot:"Stima dal carico: 3 g/kg da fermo, ~6 a TSS 100, fino a 12. <strong>Verificata il 18/08/2026</strong> contro le fasce pubblicate (Burke 2011, linee guida ACSM), raggruppando gli 788 giorni per ore di movimento vere: la mediana del modello cade dentro tutte e quattro le fasce e sta sempre sul loro bordo basso. Quindi lo scarto qui sotto, se sbaglia, sbaglia per difetto. Il tetto è passato da 10 a 12 g/kg, il massimo della fascia oltre le tre ore: a 10 mordeva su 101 giorni su 788 e appiattiva proprio i più grossi." });

  t.push({ panel:"tavola", h:146, first:"n_sugar_g", src:"ricostruito", title:"Zuccheri",
    cap:"grammi al giorno · media mobile 7 giorni",
    now:() => lastMean(N_.sugar_g, 7),
    nowFmt:FMT.num1, nowUnit:"g, media 7 gg",
    kind:rCloud, spec:{ name:"Zuccheri", arr:N_.sugar_g, col:"var(--s4)",
      fmt:v => nf(v, 1) + " g", zero:true, win:7 } });

  t.push({ panel:"tavola", h:146, first:"n_magnesium_mg", src:"ricostruito", title:"Magnesio e potassio",
    cap:"% del fabbisogno coperta", legend:[["Magnesio", SCH[2]], ["Potassio", SCH[0]]],
    now:() => { const v = lastMean(N_.magnesium_mg, 7); return v === null ? null : 100 * v / 350; },
    nowFmt:v => nf(v, 0) + " %", nowUnit:"magnesio, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0) + " %", series:[
      { name:"Magnesio", col:SCH[2], get:(a, b) => rolling(N_.magnesium_mg, a, b, 7).map((v, k) => [a + k, v === null ? null : 100 * v / 350]) },
      { name:"Potassio", col:SCH[0], get:(a, b) => rolling(N_.potassium_mg, a, b, 7).map((v, k) => [a + k, v === null ? null : 100 * v / 3500]) },
    ] },
    foot:"100 % = fabbisogno coperto." });

  t.push({ panel:"tavola", h:146, first:"n_vit_index", src:"ricostruito", title:"Vitamine e minerali",
    cap:"indice 0-100 · media delle coperture, ognuna tagliata a 100",
    legend:[["Vitamine", SCH[1]], ["Minerali", SCH[2]]],
    now:() => lastMean(N_.vit_index, 7),
    nowFmt:FMT.num0, nowUnit:"vitamine, 7 gg",
    kind:rLines, spec:{ zero:true, fmt:v => nf(v, 0), series:[
      { name:"Vitamine", col:SCH[1], get:(a, b) => rolling(N_.vit_index, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Minerali", col:SCH[2], get:(a, b) => rolling(N_.min_index, a, b, 7).map((v, k) => [a + k, v]) },
    ] },
    foot:"Ogni nutriente tagliato al 100 % prima della media." });

  if (has("microbiome")) t.push({ panel:"tavola", h:146, first:"n_microbiome",
    src:"modello", title:"Indice microbiota", cap:"proxy 0-100 dal diario, non una misura",
    now:() => lastMean(N_.microbiome, 14),
    nowFmt:FMT.num0, nowUnit:"su 100, 14 gg",
    kind:rCloud, spec:{ name:"Microbiota", arr:N_.microbiome, col:"var(--s1)",
      fmt:FMT.num0, zero:true, win:14 },
    foot:"Proxy: piante 40 %, fibra 30 %, fermentati 15 %, ultra-processati −15 %.",
    /* le emoji dicono quali leve stanno spingendo l'indice, adesso, e quanto:
       il numero da solo non dice mai da dove viene */
    shifters:() => {
      const M = D.microbes || {};
      const at = a => { if (!a) return null;
        for (let i = N - 1; i >= 0; i--) if (a[i] !== null) return a[i]; return null; };
      return [["🌾", "fibra", at(M.drv_fiber)], ["🌱", "piante", at(M.drv_plants)],
              ["🍶", "fermentati", at(M.drv_ferment)], ["⚙️", "ultra-proc.", at(M.drv_upf), 1]]
        .filter(x => x[2] !== null);
    } });

  /* ---- ORAC: la densità di polifenoli, con la sua avvertenza attaccata -----
     Il numero da solo mente in due modi opposti, e tutti e due stanno nel piede:
     l'USDA ha ritirato la tabella perché l'in vitro non predice l'in vivo, e il
     catalogo copre meno di metà delle calorie, quindi il totale è basso per
     costruzione. Sono avvertenze su un numero, non spiegazioni dell'interfaccia. */
  if (has("orac")) t.push({ panel:"tavola", h:146, first:"n_orac",
    src:"ricostruito", title:"ORAC",
    cap:"µmol Trolox equivalenti al giorno · media mobile 7 giorni",
    now:() => lastMean(N_.orac, 7), nowFmt:FMT.num0, nowUnit:"µmol TE, media 7 gg",
    kind:rCloud, spec:{ name:"ORAC", arr:N_.orac, col:"var(--s2)", fmt:FMT.num0,
      zero:true, win:7 },
    dataNote:"misura in vitro, non un effetto",
    foot:"<strong>L'USDA ha ritirato questa tabella nel 2012</strong>, e la ragione conta: " +
      "l'ORAC si misura in provetta, i polifenoli che lo generano vengono in gran parte " +
      "metabolizzati o non assorbiti, e il numero era diventato un argomento di vendita per " +
      "succhi e integratori. Un ORAC alto <em>non</em> è una promessa di salute: si legge come " +
      "il contatore delle piante diverse, cioè come una spia di quanto la dieta peschi da " +
      "piante colorate. Valori da <em>USDA Database for the ORAC of Selected Foods, Release 2</em> " +
      "(2010), voce per voce in <span class=\"mono\">tools/food/data/orac.csv</span>. " +
      "<strong>Il totale è sottostimato per costruzione</strong>: la tabella USDA non ha caffè, " +
      "pasta, riso, pane bianco né latticini, e la copertura vera del giorno è la seconda " +
      "serie del riquadro qui sotto." });

  if (has("orac_cov_pct")) t.push({ panel:"tavola", h:146, first:"n_orac_cov_pct",
    src:"ricostruito", title:"Quanto dell'ORAC si vede",
    cap:"% delle calorie del giorno che viene da alimenti con un valore ORAC · media 7 giorni",
    now:() => lastMean(N_.orac_cov_pct, 7), nowFmt:v => nf(v, 0) + " %",
    nowUnit:"kcal coperte, 7 gg",
    kind:rCloud, spec:{ name:"Copertura", arr:N_.orac_cov_pct, col:"var(--s4)",
      fmt:v => nf(v, 0) + " %", zero:true, win:7 },
    dataNote:"quanto ne copre il catalogo",
    foot:"Sotto questa riga il grafico sopra non sta misurando la dieta: sta misurando la parte " +
      "di dieta che il catalogo sa leggere. Le due cose si allontanano nei giorni di pasta, pane " +
      "bianco e caffè, che valgono zero perché il dato non esiste, non perché non abbiano " +
      "antiossidanti." });

  /* ---- I dodici del dottor Greger, settimana per settimana -----------------
     Dodici righe e sette colonne: è la forma della domanda, che non è "quanto
     ORAC ho fatto" ma "quali caselle ho spuntato e quali no". Le prescritte sono
     di Greger, verificate su nutritionfacts.org; le porzioni in grammi sono la
     conversione dalle sue cup e tablespoon, e stanno in daily_dozen.csv. */
  const DDZ = [["fagioli", "Fagioli e legumi", 3], ["frutti_di_bosco", "Frutti di bosco", 1],
               ["altra_frutta", "Altra frutta", 3], ["crucifere", "Crucifere", 1],
               ["verdure_foglia_verde", "Foglie verdi", 2], ["altre_verdure", "Altre verdure", 2],
               ["semi_di_lino", "Semi di lino", 1], ["noci_e_semi", "Frutta secca e semi", 1],
               ["erbe_e_spezie", "Erbe e spezie", 1], ["cereali_integrali", "Cereali integrali", 3],
               ["bevande", "Bevande", 5], ["esercizio", "Esercizio", 1]];
  /* Le dodici righe ci sono SEMPRE tutte e dodici, anche quando la serie non
     esiste: `semi_di_lino` non ha un solo alimento nel catalogo, quindi la sua
     colonna in nutrition.csv e' vuota da cima a fondo. Filtrare via le righe senza
     dati farebbe sparire proprio la casella che ha piu' bisogno di essere vista —
     e l'elenco si chiama «i dodici». Le celle restano bianche, e il piede dice
     perche'. */
  if (has("dd_fagioli")) t.push({ panel:"tavola", cls:"wide", h:330, first:"n_dd_fagioli",
    src:"ricostruito", title:"I dodici del dottor Greger",
    cap:"porzioni del giorno contro quelle prescritte · gli ultimi 7 giorni con del cibo",
    dataNote:"dodici caselle, verificate sulla fonte",
    /* Il numero di testa e' «quante caselle rispetta NELLA SETTIMANA», non ieri:
       il Daily Dozen e' una routine, e un giorno solo la racconta male — il 4
       settembre, che e' un giorno tutto ricostruito, ne dice tre, la settimana
       cinque. La finestra e' la stessa che disegna la griglia qui sotto. */
    now:() => { const g = ddGiorni(); if (!g.length) return null;
      return DDZ.filter(([k, , tg]) => {
        const s = N_["dd_" + k]; if (!s) return false;
        const v = g.map(i => s[i]).filter(x => x !== null && x !== undefined);
        return v.length && v.reduce((a, b) => a + b, 0) / v.length >= tg;
      }).length; },
    nowFmt:FMT.num0, nowUnit:"caselle su 12, media 7 giorni",
    kind:(svg, W, H, spec, a, b) => {
      const g = ddGiorni(a, b);
      if (g.length < 2) return null;
      return rGrid(svg, W, H, {
        rows:DDZ.map(([, lab]) => ({ name:lab })),
        cols:g.map(i => ({ name:DOW[(dayDate(i).getDay() + 6) % 7] + " " + dayDate(i).getDate() })),
        vmax:1, diverging:false, labMax:130, labB:40, maxColLabels:7,
        cell:(i, j) => { const [k, lab, tg] = DDZ[i], s = N_["dd_" + k];
          const v = s ? s[g[j]] : null;
          if (v === null || v === undefined) return null;
          const q = Math.min(1, v / tg);
          return { v:q, day:g[j], txt:v >= 10 ? nf(v, 0) : nf(v, 1),
            tip:`<span class="d">${fmtDate(g[j])}</span><br>${lab} ` +
                `<span class="v">${nf(v, 1)}</span> su ${tg}` +
                (v >= tg ? "<br><span class=\"d\">casella piena</span>" : "") }; },
        summary:() => { let pieni = 0, tot = 0;
          DDZ.forEach(([k, , tg]) => g.forEach(i => { const s = N_["dd_" + k];
            const v = s ? s[i] : null;
            if (v !== null && v !== undefined) { tot++; if (v >= tg) pieni++; } }));
          return `${pieni} caselle piene su ${tot} · ${g.length} giorni`; },
        table:() => `<tr><th>casella</th><th>media</th><th>prescritte</th><th>giorni pieni</th></tr>` +
          DDZ.map(([k, lab, tg]) => { const s = N_["dd_" + k];
            const vs = (s ? g.map(i => s[i]) : [])
              .filter(v => v !== null && v !== undefined);
            if (!vs.length) return `<tr><td>${lab}</td><td>&mdash;</td><td>${tg}</td><td>nessun alimento a catalogo</td></tr>`;
            const m = vs.reduce((x, y) => x + y, 0) / vs.length;
            return `<tr><td>${lab}</td><td>${nf(m, 1)}</td><td>${tg}</td>` +
                   `<td>${vs.filter(v => v >= tg).length} / ${vs.length}</td></tr>`; }).join("") },
        a, b);
    }, spec:{},
    foot:"<strong>Due caselle non sono misurabili da qui</strong>: i <em>semi di lino</em> non " +
      "esistono nel catalogo — quella riga è vuota, non a zero — e le <em>bevande</em> " +
      "restano a zero perché l'acqua non si annota, non perché non la beva. " +
      "Un alimento può stare in più caselle e allora ne spunta una per ciascuna, mai " +
      "due volte la stessa: cavolo nero e rucola sono insieme crucifere e foglie verdi. " +
      "L'<em>esercizio</em> non viene dal diario ma da intervals.icu — 90 minuti moderati o 40 " +
      "vigorosi fanno una porzione, e la soglia fra i due è un intensity factor di 0,75. " +
      "Le porzioni in grammi sono la conversione dalle cup e tablespoon di Greger e stanno in " +
      "<span class=\"mono\">tools/food/data/daily_dozen.csv</span>, riga per riga." });

  /* ---- gli integratori, che fino al 3 settembre 2026 il registro non aveva --
     Il riquadro NON compare finche' non c'e' un mese di storia. Con due giorni una
     serie non e' un grafico: e' un picco solo, e la pagina ha gia' un controllo che
     boccia i riquadri che non disegnano niente — giustamente, perche' un riquadro
     vuoto e' peggio di un riquadro che non c'e'.
     Intanto gli integratori si vedono lo stesso, e nel posto dove si guardano: la
     scheda del giorno li apre come pasto suo, «Integratori», accanto a colazione e
     cena. Quando il mese c'e', il riquadro si accende da solo. */
  const supplGiorni = has("suppl_n")
    ? N_.suppl_n.reduce((a, v) => a + (v === null || v === undefined ? 0 : 1), 0) : 0;
  if (supplGiorni >= 28) t.push({ panel:"tavola", h:170, first:"n_suppl_n",
    src:"misurato", title:"Integratori",
    cap:"prese registrate · sommate al mese",
    now:() => { let s = 0; for (let i = 0; i < N; i++) s += N_.suppl_n[i] || 0; return s; },
    nowFmt:FMT.num0, nowUnit:"prese, in tutto",
    kind:rBars, spec:{ name:"Integratori", arr:N_.suppl_n, how:"sum", col:"var(--s3)",
      fmt:v => nf(v, 0) },
    foot:"Conta le prese, <strong>non quello che c'è dentro</strong>: di Orax Core e Daily Dose " +
      "non esiste una scheda pubblica da citare, quindi le celle dei nutrienti nel catalogo sono " +
      "vuote — un dato che manca, non uno zero. Con la foto dell'etichetta diventano vitamine e " +
      "minerali veri e rientrano negli indici. Si annotano dal pannello Vita di Mission Control, " +
      "come tutto il resto del diario." });

  /* La matrice 3×3: tre input della tavola contro tre uscite del recupero.
     Nove ipotesi guardate insieme — se ne mostrassi solo la più forte starei
     scegliendo il risultato dopo aver visto i dati. */
  /* Tutte contro tutte. Dodici serie fanno 66 coppie: 66 nuvole non si guardano,
     una griglia si. E' l'unico punto della pagina in cui una griglia e' la forma
     giusta — e lo e' perche' qui il colore porta un valore continuo con un segno. */
  /* I dieci generi di cui si parla, modellati. Il titolo dice "modello" e la
     didascalia lo ripete: qui non c'è nessun campione, nessuna sequenza, nessuna
     misura — solo le associazioni direzionali fra dieta e abbondanza relativa
     fatte girare su un modello log-lineare i cui pesi stanno nel sorgente. */

  /* ---- ORIGINE: quattro fette che fanno cento -----------------------------
     Prima erano tre etichette sovrapposte che sommavano 128 % e il piede doveva
     spiegare perche' non facevano cento. Adesso l'origine e' una partizione — ogni
     caloria in una fetta sola — e le quattro linee si leggono come una composizione,
     che e' come le si guardava comunque. L'ultra-processato NON e' una quinta fetta:
     attraversa tutte e quattro (un cornetto e' vegetale e ultra-processato insieme),
     quindi non prende uno slot categorico ma il grigio del testo secondario. Il
     colore dice "sono un'altra cosa" prima che lo dica la legenda. */
  if (has("pct_plant")) t.push({ panel:"tavola", h:170, first:"n_pct_plant",
    src:"ricostruito", title:"Da dove arrivano le calorie", cap:"% delle kcal · le quattro fanno cento",
    legend:[["Vegetale", SCH[2]], ["Latticini", SCH[0]], ["Animale", SCH[1]],
            ["Altro", SCH[3]], ["Ultra-processato", "var(--muted)"]],
    now:() => lastMean(N_.pct_plant, 7), nowFmt:v => nf(v, 0) + " %", nowUnit:"vegetale, 7 gg",
    kind:rLines, spec:{ zero:true, medie:true, frames:false, fmt:v => nf(v, 0) + " %", series:[
      { name:"Vegetale", col:SCH[2], area:true, get:(a, b) => rolling(N_.pct_plant, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Latticini", col:SCH[0], get:(a, b) => rolling(N_.pct_dairy, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Animale", col:SCH[1], get:(a, b) => rolling(N_.pct_animal, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Altro", col:SCH[3], get:(a, b) => rolling(N_.pct_other, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Ultra-processato", col:"var(--muted)", dash:"3 3", get:(a, b) => rolling(N_.pct_upf, a, b, 7).map((v, k) => [a + k, v]) },
    ] },
    foot:"Vegetale, latticini, animale e altro sono una partizione: ogni caloria sta in una fetta sola e le quattro fanno cento. L'ultra-processato è un altro asse e le attraversa tutte — un cornetto è vegetale e ultra-processato insieme — quindi non va sommato con loro. «Altro» è burro, miele, whey: se cresce, mancano dei `plant` in foods.csv." });

  /* ---- MACRO: di cosa erano fatte quelle calorie -------------------------
     Il denominatore sono le tre macro, non le kcal del giorno: vedi macro_split()
     in build_nutrition_series.py. Diviso per le kcal la somma ballava fra 97 e 122
     a seconda del giorno, che come composizione non si puo' guardare. */
  if (has("pct_kcal_carb")) t.push({ panel:"tavola", h:170, first:"n_pct_kcal_carb",
    src:"ricostruito", title:"Di cosa erano fatte", cap:"% dell'energia da macro · le tre fanno cento",
    legend:[["Carboidrati", SCH[0]], ["Grassi", SCH[3]], ["Proteine", SCH[2]]],
    now:() => lastMean(N_.pct_kcal_carb, 7), nowFmt:v => nf(v, 0) + " %", nowUnit:"carboidrati, 7 gg",
    kind:rLines, spec:{ zero:true, medie:true, frames:false, fmt:v => nf(v, 0) + " %", series:[
      { name:"Carboidrati", col:SCH[0], area:true, get:(a, b) => rolling(N_.pct_kcal_carb, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Grassi", col:SCH[3], get:(a, b) => rolling(N_.pct_kcal_fat, a, b, 7).map((v, k) => [a + k, v]) },
      { name:"Proteine", col:SCH[2], get:(a, b) => rolling(N_.pct_kcal_protein, a, b, 7).map((v, k) => [a + k, v]) },
    ] },
    foot:"Atwater: proteine e carboidrati 4 kcal/g, grassi 9. La quota è sul totale delle tre macro, non sulle kcal del giorno — le kcal arrivano dal database alimenti o da Cronometer e i due conti non tornano mai identici. È una composizione: uno sale solo se un altro scende." });

  /* ---- E DI CHE GRASSO SONO FATTI I GRASSI (chiesto il 17/08/2026) --------
     Il riquadro qui sopra dice quanta energia veniva dai grassi. Questo dice di che
     grassi si trattava, che e' la domanda dopo — e l'unica delle due che si possa
     collegare a qualcosa di clinico.

     Esiste SOLO sui giorni in cui Cronometer ha pesato la giornata intera, ed e'
     l'unico riquadro della Tavola marcato `misurato` invece che `ricostruito`:
     `foods.csv` ha `satfat_g` e basta, e mono, poli e trans non si possono riempire
     su quattrocento alimenti senza inventarli. Dove non c'e' la misura la serie e'
     vuota, non zero.

     La quarta fetta non e' un ripiego, e' il resto vero: la somma delle tre misurate
     sta sotto al grasso totale del giorno perche' il database di Cronometer non
     classifica ogni alimento, e quel divario si dichiara invece di spalmarlo sugli
     insaturi — spalmarlo li' sarebbe un dato mancante travestito da dato. */
  if (has("trans_g") && has("mono_g") && has("poly_g")) {
    const mono = N_.mono_g, poly = N_.poly_g, tr = N_.trans_g;
    /* tutte e quattro le fette vivono sugli STESSI giorni, e sono i giorni pesati.
       I saturi il database li conosce su tutti e 788 i giorni, ma prendere quelli
       qui dentro impilerebbe una media su tutto il mese sotto tre medie sui soli
       giorni misurati: la colonna sarebbe alta per un motivo e divisa per un altro. */
    const sat = new Array(N).fill(null), rest = new Array(N).fill(null);
    let nSplit = 0;
    for (let i = 0; i < N; i++) {
      if (tr[i] === null || tr[i] === undefined) continue;
      const m = mono[i] || 0, p = poly[i] || 0, s = N_.satfat_g[i] || 0, x = tr[i] || 0;
      sat[i] = s;
      rest[i] = Math.max(0, (N_.fat_g[i] || 0) - s - m - p - x);
      nSplit++;
    }
    /* Il denominatore e' la somma delle CINQUE fette di quel giorno, non `fat_g`:
       cosi' le quote fanno cento per costruzione anche nei giorni in cui il totale
       del database e le fette non tornano all'ultimo decimo, e nessuna riga
       orizzontale si mette a galleggiare per un errore di arrotondamento. */
    const quotaDi = arr => {
      const q = new Array(N).fill(null);
      for (let i = 0; i < N; i++) {
        if (sat[i] === null) continue;
        const tot = sat[i] + (mono[i] || 0) + (poly[i] || 0) + (tr[i] || 0) + rest[i];
        if (tot > 0) q[i] = 100 * ((arr[i] || 0) / tot);
      }
      return q;
    };
    const quotaSat = quotaDi(sat);
    const serieQuota = arr => { const q = quotaDi(arr);
      return (a, b) => sparse(q, a, b, 90, 4).map((v, k) => [a + k, v]); };
    t.push({ panel:"tavola", h:180, first:"n_trans_g", src:"ricostruito",
      title:"Di che grasso", cap:"quota del grasso del giorno · media su 90 giorni di misure",
      legend:[["Saturi", "var(--s2)"], ["Monoinsaturi", "var(--s3)"],
              ["Polinsaturi", "var(--s1)"], ["Trans", "var(--s4)"],
              ["Non classificato", "var(--muted)"]],
      /* Gli ULTIMI 30 GIORNI PESATI, non gli ultimi 30 giorni: una media mobile a
         finestra fissa qui non si accende mai, perche' i giorni misurati sono quattro
         al mese e `rolling` chiede almeno un terzo della finestra piena — per costruzione,
         e giustamente. Qui la finestra si conta in misure, che e' l'unita' vera di
         questa serie. */
      now:() => { const v = [];
        for (let i = N - 1; i >= 0 && v.length < 30; i--)
          if (quotaSat[i] !== null) v.push(quotaSat[i]);
        return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; },
      nowFmt:v => nf(v, 0) + " %", nowUnit:"saturi, ultimi 30 giorni pesati",
      /* Dal 19/08/2026 (ordine #23) non e' piu' una pila di centocinque colonne
         settimanali larghe due pixel: e' la forma di casa — la quota di ogni acido
         grasso come linea sottile e trasparente, e sopra la sua media come riga
         orizzontale. Su una pila in percentuale l'occhio deve misurare lo SPESSORE di
         una fascia che galleggia sopra le altre; qui ogni quota parte dallo stesso
         zero, e due quote si confrontano guardando due righe. */
      kind:rLines, spec:{ zero:true, medie:true, frames:false,
        fmt:v => nf(v, 0) + " %", series:[
          { name:"Saturi", col:"var(--s2)", get:serieQuota(sat) },
          { name:"Monoinsaturi", col:"var(--s3)", get:serieQuota(mono) },
          { name:"Polinsaturi", col:"var(--s1)", get:serieQuota(poly) },
          { name:"Trans", col:"var(--s4)", get:serieQuota(tr) },
          { name:"Non classificato", col:"var(--muted)", get:serieQuota(rest) },
        ] },
      foot:`<strong>${nf(nSplit)} giorni</strong> pesati. Ogni linea è la quota di quel giorno` + " sul grasso totale, spianata su una finestra di 90 giorni che si conta in misure e "
        + "non in giorni: sotto quattro giornate pesate nella finestra la linea si "
        + "interrompe invece di attraversare il vuoto. Dal 17/08/2026 il catalogo "
        + "porta anche mono, poli e trans, <strong>ricostruiti</strong> da profili di acidi "
        + "grassi noti: olio d'oliva per tre quarti monoinsaturo, noci per tre quarti "
        + "polinsature, burro e formaggio con un 4 % di trans di ruminante. Sui giorni "
        + "pesati da Cronometer la ricostruzione dà 34/32/18 % contro 31/31/17 misurati, "
        + "e 0,37 g di trans contro 0,34. «Non classificato» è il glicerolo, circa il 4 % "
        + "della massa di un trigliceride, più l'imprecisione del profilo. Tetto OMS per "
        + "i trans: 1 % dell'energia, circa 3 g." });
  }

  /* ---- quali cibi muovono la flora: heatmap alimenti × generi ------------ */
  const FF = D.floraFoods || [];
  if (FF.length && GEN.length >= 5) {
    const gens = GEN.map(([g, e]) => ({ name:`${e} ${g.slice(0, 9)}`, key:g }));
    const items = FF.slice(0, 16).map(f => ({ name:f.name.length > 20 ? f.name.slice(0, 19) + "…" : f.name, f }));
    const vmax = Math.max(...items.flatMap(it => gens.map(g => Math.abs(it.f[g.key] || 0)))) || 1;
    t.push({ panel:"tavola", cls:"wide", h:430, first:"m_Faecalibacterium",
      src:"modello", title:"Quali cibi muovono la flora", cap:"il modello letto al contrario · spinta di ogni alimento su ogni genere",
      kind:rGrid, spec:{ rows:items, cols:gens, vmax, labMax:150, labB:74,
        cell:(i, j) => { const v = items[i].f[gens[j].key];
          if (v === undefined) return null;
          return { v, txt:Math.abs(v) >= 1 ? v.toFixed(0) : "",
            tip:`${items[i].f.name}<br>${gens[j].key} <span class="v">${v >= 0 ? "+" : ""}${v.toFixed(2)}</span>` +
                `<br><span class="d">${items[i].f.share_pct.toFixed(1)} % delle kcal</span>` }; },
        summary:h => h && `spinge di più ${items[h.i].f.name} su ${gens[h.j].key}`,
        table:cells => `<tr><th>alimento</th><th>genere</th><th>spinta</th></tr>` +
          cells.filter(c => Math.abs(c[2].v) > .3).sort((a, b) => Math.abs(b[2].v) - Math.abs(a[2].v))
            .slice(0, 30).map(c => `<tr><td>${c[0]}</td><td>${c[1]}</td><td>${c[2].v >= 0 ? "+" : ""}${c[2].v.toFixed(2)}</td></tr>`).join("") },
      foot:"La spinta è quanto quell'alimento preme sul genere <em>per come pesa nella tua dieta</em>: un cibo ottimo ma mangiato di rado conta poco, ed è giusto così. Resta il modello, non una misura." });
  }

  /* ---- striscia temporale: molte serie, una riga ciascuna ---------------- */
  const STRIP = [
    ["Fibre", N_.fiber_g], ["Piante", N_.plants_7d], ["Vegetale %", N_.pct_plant],
    ["Ultra-proc. %", N_.pct_upf], ["Zuccheri", N_.sugar_g], ["Energia", N_.kcal],
    ["Microbiota", N_.microbiome], ["Sonno", D.sleep], ["HRV", D.hrv],
    ["FC riposo", D.rhr], ["Carico", D.load],
  ].filter(([, a]) => Array.isArray(a));
  if (STRIP.length >= 6) t.push({ panel:"tavola", cls:"wide", h:300, first:"n_fiber_g",
    src:"ricostruito", title:"Tutto, nel tempo", cap:"una riga per serie · il passo si adatta allo spazio: settimane, mesi, anni",
    kind:(svg, W, H, spec, a, b) => {
      /* Ogni riga ha unita' sue — grammi, ore, battiti — quindi il colore non puo'
         essere il valore: e' il PERCENTILE dentro la storia di quella riga. Cosi'
         le righe si possono confrontare fra loro, e si vede in che settimane tutto
         si muoveva insieme. */
      /* Il passo si sceglie dalla larghezza che c'e', non si spera che ci stia:
         con 104 settimane in una scheda stretta le colonne sarebbero da 2 px e il
         riquadro spariva. Settimane finche' ci stanno, poi mesi, poi anni. */
      const room = Math.max(6, Math.floor((W - 96 - 8) / 9));
      let step = "w";
      for (const s_ of ["w", "m", "y"]) {
        step = s_;
        if (aggregate(STRIP[0][1], a, b, "mean", s_).length <= room) break;
      }
      /* L'INDICE DEL GIORNO E LA CHIAVE DEL SECCHIO NON SONO LO STESSO NUMERO, e su
         passo settimanale sembravano esserlo (`bucketKey(i,"w")` torna proprio i).
         Da qui l'asse x scriveva "undefined -285" appena la finestra diventava larga
         abbastanza da passare ai mesi — cioe' su tre finestre su quattro — perche'
         `bucketLabel` riceveva un indice di giorno dove aspettava una chiave.
         Le celle si cercano per indice (`o.i`), le etichette si scrivono dalla chiave
         (`o.k`), e sono due liste parallele. */
      const secchi = aggregate(STRIP[0][1], a, b, "mean", step);
      const weeks = secchi.map(o => o.i), chiavi = secchi.map(o => o.k);
      if (weeks.length < 4) return null;
      const rowsData = STRIP.map(([name, arr]) => {
        const agg = aggregate(arr, a, b, "mean", step);
        const byI = new Map(agg.map(o => [o.i, o.v]));
        const vals = agg.map(o => o.v).filter(v => v !== null && isFinite(v)).sort((x, y) => x - y);
        return { name, byI, vals, arr };
      });
      return rGrid(svg, W, H, {
        rows:rowsData, cols:chiavi.map(k => ({ name:bucketLabel(k, step).replace("sett. del ", "") })),
        vmax:1, diverging:false, labMax:96, labB:70, maxColLabels:10,
        cell:(i, j) => { const r = rowsData[i], v = r.byI.get(weeks[j]);
          if (v === null || v === undefined || !r.vals.length) return null;
          const pos = r.vals.filter(x => x <= v).length / r.vals.length;
          return { v:pos, day:weeks[j],
            tip:`<span class="d">${bucketLabel(chiavi[j], step)}</span><br>${r.name} <span class="v">${nf(v, 1)}</span>` +
                `<br><span class="d">${nf(pos * 100, 0)}° percentile della sua storia</span>` }; },
        summary:() => `${rowsData.length} serie · ${weeks.length} ${step === "w" ? "settimane" : step === "m" ? "mesi" : "anni"}`,
        table:() => `<tr><th>serie</th><th>min</th><th>mediana</th><th>max</th></tr>` +
          rowsData.filter(r => r.vals.length).map(r => `<tr><td>${r.name}</td><td>${nf(r.vals[0], 1)}</td><td>${nf(r.vals[Math.floor(r.vals.length / 2)], 1)}</td><td>${nf(r.vals[r.vals.length - 1], 1)}</td></tr>`).join(""),
      }, a, b);
    }, spec:{},
    foot:"Il colore dice il percentile dentro la <em>propria</em> riga: righe con unità diverse diventano confrontabili, e si vedono le settimane in cui tutto si muoveva insieme. Chiaro = basso per quella serie, acceso = alto." });

  /* i conteggi: quante volte è entrato in casa un certo alimento */
  const TAL = [["cnt_avocado", "avocado", "🥑"], ["cnt_lenticchie", "porzioni di lenticchie", "🫘"],
               ["cnt_uova", "uova", "🥚"], ["cnt_banane", "banane", "🍌"],
               ["cnt_avena", "porzioni di avena", "🌾"], ["cnt_patate_dolci", "porzioni di patate dolci", "🍠"]]
    .filter(([k]) => has(k));
  if (TAL.length) t.push({ panel:"tavola", h:180, first:"n_cnt_avocado",
    src:"ricostruito", title:"Quanti ne sono passati", cap:"conteggio cumulato dall'inizio della finestra",
    legend:TAL.slice(0, 4).map(([, l, e], i) => [`${e} ${l}`, SCH[i % 4]]),
    kind:rLines, spec:{ zero:true, fmt:FMT.num0,
      series:TAL.slice(0, 4).map(([k, l, e], i) => ({ name:`${e} ${l}`, col:SCH[i % 4],
        get:(a, b) => { let acc = 0; const o = [];
          for (let j = a; j <= b; j++) { acc += N_[k][j] || 0; o.push([j, acc]); }
          return o; } })) },
    foot:"Cumulato, quindi la pendenza è il ritmo: una riga che si appiattisce è un alimento che ha smesso di entrare." });

  return t;
}

function sparsePts(arr, a, b) {
  const o = [];
  for (let i = a; i <= b; i++) if (arr[i] !== null && arr[i] !== undefined) o.push([i, arr[i], i]);
  return o;
}
function pairPts(fx, fy, a, b, keepX) {
  const o = [];
  for (let i = Math.max(a, 1); i <= b; i++) {
    const x = fx(i), y = fy(i);
    if (x === null || x === undefined || y === null || y === undefined) continue;
    if (keepX && !keepX(x)) continue;
    o.push([x, y, i]);
  }
  return o;
}

/* ============================================================ vista compatta
   La colonna estesa risponde a "quanto vale questa serie". Questa risponde a una
   domanda diversa — "cosa si muoveva insieme, e quando" — e per quella gli assi
   sono un costo: venti riquadri con venti gronde di etichette fanno tre schermate,
   e la forma di una serie non si ricorda fino alla successiva.
   Qui ogni serie e' UNA linea, l'identita' e' scritta sopra la linea (niente
   colonna laterale, niente legenda: con venti corsie il colore non puo' portare
   l'identita' comunque), e le corsie si sovrappongono.

   Il prezzo e' dichiarato in pagina e non e' negoziabile: grammi, ore, battiti e
   kcal non stanno sulla stessa scala, quindi OGNI corsia e' normalizzata sulla
   propria storia. Due corsie alte uguali non dicono valori uguali — dicono
   "ognuna al suo massimo". Si confrontano le forme e i tempi, mai i valori. */

/* Geometria. Le linee di base distano RIDGE_STEP; una corsia puo' salire fino a
   RIDGE_OVER passi, cioe' un quinto in piu' del passo — e quel quinto e' esattamente
   quanto una corsia sconfina in quella sopra. Con 84 px di passo e 100,8 px di
   escursione, in una schermata alta 900 px ci stanno dieci corsie intere
   ((900 − 100,8) / 84 + 1 = 10,5), nove tenendo conto della riga di congelate. */
const RIDGE_STEP = 84;
const RIDGE_OVER = 1.2;
const RIDGE_PIN_STEP = 46;      /* la striscia appiccicata sta piu' stretta: e' un promemoria */

/* Le somme giornaliere (ore, km, dislivello, TSS) valgono zero anche nei giorni in
   cui la serie non esisteva ancora: uno zero vero e uno zero per assenza si
   disegnano identici, e sarebbero quattro anni di linea piatta mai misurata. */
function maskBefore(arr, firstKey) {
  const f = daysOf(firstKey);
  if (!f) return arr;
  const o = arr.slice();
  for (let i = 0; i < f && i < o.length; i++) o[i] = null;
  return o;
}

/* Media mobile CENTRATA, con una soglia bassa di punti.
   Centrata perche' qui si confrontano i TEMPI fra corsie: due medie trascinate con
   finestre diverse (7 giorni per l'HRV, 120 per il peso) sposterebbero i picchi di
   quantita' diverse, e la domanda "si muovono insieme?" riceverebbe una risposta
   costruita dal filtro invece che dai dati. La soglia e' bassa per le serie rade:
   il peso ha sessantacinque pesate in undici anni, e con la soglia di rolling()
   (un terzo della finestra piena) non disegnerebbe un solo segmento.
   Una finestra tutta vuota resta null, quindi il buco del 2022 resta un buco.
   Somme prefisse e non una finestra che scorre sommando e sottraendo: con undicimila
   addizioni e sottrazioni di fila l'errore in virgola mobile si accumula, e una
   corsia che vale esattamente zero per quattro anni (le ore prima della prima
   attivita') finiva a −1e−13 — cioe' scriveva "escursione −0 → 174". La differenza
   fra due somme prefisse su un tratto di zeri e' zero esatto. */
function ridgeSmooth(arr, w) {
  const h = Math.floor(w / 2);
  const ps = new Array(N + 1).fill(0), pc = new Array(N + 1).fill(0);
  for (let i = 0; i < N; i++) {
    const v = arr[i], g = v !== null && v !== undefined && isFinite(v);
    ps[i + 1] = ps[i] + (g ? v : 0);
    pc[i + 1] = pc[i] + (g ? 1 : 0);
  }
  const out = new Array(N).fill(null);
  for (let i = 0; i < N; i++) {
    const a = Math.max(0, i - h), b = Math.min(N - 1, i + h);
    const n = pc[b + 1] - pc[a];
    out[i] = n > 0 ? (ps[b + 1] - ps[a]) / n : null;
  }
  return out;
}

const RIDGE = (() => {
  const NU = D.nutri || {}, MB = D.metab || {};
  const out = [];
  /* il colore raggruppa per sezione, mai per serie: quattro slot validati non
     possono identificare venti linee, e fingere che lo facciano sarebbe peggio che
     non colorarle affatto. L'identita' sta nell'etichetta sulla linea. */
  const add = (sec, col, key, name, arr, win, fmt, first) => {
    if (!Array.isArray(arr)) return;
    out.push({ sec, col, key, name, win, fmt: fmt || FMT.num0,
      arr: first ? maskBefore(arr, first) : arr });
  };
  const forma = D.ctl.map((v, i) =>
    v === null || v === undefined || D.atl[i] === null || D.atl[i] === undefined
      ? null : v - D.atl[i]);
  add("Carico", "var(--s1)", "ctl", "Fitness (CTL)", D.ctl, 7, FMT.num0, "load");
  add("Carico", "var(--s1)", "atl", "Fatica (ATL)", D.atl, 7, FMT.num0, "load");
  add("Carico", "var(--s1)", "forma", "Forma", forma, 7, FMT.num0, "load");
  add("Carico", "var(--s1)", "load", "Carico (TSS)", D.load, 14, FMT.tss, "load");
  add("Notte", "var(--s3)", "sleep", "Sonno", D.sleep, 7, FMT.hhmm);
  add("Notte", "var(--s3)", "score", "Punteggio del sonno", D.score, 14, FMT.num0);
  add("Recupero", "var(--s2)", "hrv", "HRV", D.hrv, 7, FMT.ms);
  add("Recupero", "var(--s2)", "rhr", "FC a riposo", D.rhr, 7, FMT.bpm);
  add("Recupero", "var(--s2)", "steps", "Passi", D.steps, 7, FMT.num0);
  add("Corpo", "var(--s4)", "weight", "Peso", D.weight, 120, FMT.kg);
  add("Corpo", "var(--s4)", "bodyfat", "Massa grassa", D.bodyfat, 120, FMT.pct);
  add("Volume", "var(--s1)", "hours", "Ore", secsOf.secs.map(v => v / 3600), 14,
      FMT.hours, "act");
  add("Volume", "var(--s1)", "km", "Chilometri", secsOf.dist.map(v => v / 1000), 14,
      FMT.km, "act");
  add("Volume", "var(--s1)", "gain", "Dislivello", secsOf.gain, 14, FMT.m, "act");
  add("Tavola", "var(--s3)", "kcal", "Energia", NU.kcal, 7, FMT.num0);
  add("Tavola", "var(--s3)", "fiber", "Fibre", NU.fiber_g, 7, v => nf(v, 1) + " g");
  add("Tavola", "var(--s3)", "plants", "Piante diverse", NU.plants_7d, 7, FMT.num0);
  add("Tavola", "var(--s3)", "sugar", "Zuccheri", NU.sugar_g, 7, v => nf(v, 1) + " g");
  add("Tavola", "var(--s3)", "plant", "Vegetale %", NU.pct_plant, 7, FMT.pct);
  add("Tavola", "var(--s3)", "upf", "Ultra-processato %", NU.pct_upf, 7, FMT.pct);
  add("Tavola", "var(--s3)", "magn", "Magnesio", NU.magnesium_mg, 7, v => nf(v, 0) + " mg");
  add("Tavola", "var(--s3)", "pota", "Potassio", NU.potassium_mg, 7, v => nf(v, 0) + " mg");
  add("Tavola", "var(--s3)", "micro", "Microbiota", NU.microbiome, 14, FMT.num0);
  /* Del metabolismo passano di qui solo le tre serie che hanno una FORMA nel tempo.
     La banda FatMax no: resta piatta a 137 bpm per nove anni e poi si muove di sei
     battiti, e la normalizzazione per corsia trasformerebbe quei sei battiti in
     un'escursione a tutta altezza — vera per costruzione, e illeggibile come segnale.
     Sta nella vista estesa, dove ha un asse che dice quanto vale. */
  add("Metabolismo", "var(--s2)", "temp", "Temperatura", MB.temp_c, 30,
      v => nf(v, 1) + " °C");
  add("Metabolismo", "var(--s2)", "heat", "Heat strain", heat, 30, FMT.num1);
  add("Metabolismo", "var(--s2)", "mm", "Momento metabolico",
      mmDraw && mmDraw.arr, 14, FMT.num1);
  /* Le due serie che servono a incrociare l'ossidazione dei grassi con la tavola:
     l'efficienza e' misurata, il tasso di grassi e' modellato, e nel comparatore
     si possono mettere contro la quota di carboidrati, le kcal, qualunque cosa.
     Attenzione a una circolarita' vera: `fatrate` scende da un modello che gia'
     contiene i carboidrati abituali (metabolismo.py, assunzione 4), quindi una
     correlazione fra quei due e' il cablaggio, non una scoperta. `ef` no: quella
     e' passo e battito, e con la tavola non ha nessun filo diretto. */
  add("Metabolismo", "var(--s2)", "ef", "Efficienza aerobica",
      aero && aero.day, 45, v => nf(v, 2));
  add("Metabolismo", "var(--s2)", "fatrate", "Grassi al minuto",
      fatRate, 45, v => nf(v, 2) + " g/min");
  /* i grammi in banda entrano nel registro come tutte le altre: da qui la corsia
     nella vista compatta e la voce nel menu del correlatore escono da sole. Stessa
     circolarita' di `fatrate` — nasce dal modello che gia' legge la dieta — quindi
     incrociarla con la tavola e' un controllo di coerenza, non una scoperta. */
  add("Metabolismo", "var(--s2)", "fatband", "Grassi bruciati in banda",
      fatBand, 30, v => nf(v, 0) + " g");
  return out;
})();

/* La scala di una corsia: dal 2° al 98° percentile della sua media mobile su TUTTO
   l'archivio, non sulla finestra mostrata. Su tutto l'archivio perche' cosi' la
   forma non cambia quando si cambia finestra — un trimestre basso resta basso
   invece di riespandersi a piena altezza e mentire. Percentili e non estremi perche'
   una notte da tre ore o un giorno da trentamila passi si prenderebbe tutta
   l'escursione e schiaccerebbe il resto in una riga piatta; quello che esce fuori
   viene tagliato ai bordi della corsia, non disegnato altrove. */
function ridgePrep(s) {
  if (s._sm) return s;
  s._sm = ridgeSmooth(s.arr, s.win);
  const v = s._sm.filter(x => x !== null && isFinite(x)).sort((a, b) => a - b);
  s._n = v.length;
  if (!v.length) { s._lo = 0; s._hi = 1; s._min = null; s._max = null; return s; }
  const q = p => v[Math.max(0, Math.min(v.length - 1, Math.round(p * (v.length - 1))))];
  let lo = q(.02), hi = q(.98);
  if (!(hi > lo)) { lo = v[0]; hi = v[v.length - 1]; }
  if (!(hi > lo)) { hi = lo + (Math.abs(lo) || 1); }
  s._lo = lo; s._hi = hi; s._min = v[0]; s._max = v[v.length - 1];
  return s;
}

/* Punti di una corsia, gia' normalizzati in [0,1] e diradati.
   Diradati perche' "sempre" sono oltre quattromila giorni: quattromila comandi per
   corsia per venti corsie e' un tracciato che il browser disegna e nessuno vede —
   la media e' gia' calcolata, la finestra e' gia' lisciata, e piu' di due punti per
   pixel non aggiungono un segno. */
function ridgePts(s, from, to, iw) {
  const span = to - from + 1;
  const k = Math.max(1, Math.ceil(span / Math.max(60, iw * 2)));
  const out = [];
  for (let i = from; i <= to; i += k) {
    let acc = 0, n = 0;
    for (let j = i; j < Math.min(i + k, to + 1); j++) {
      const v = s._sm[j]; if (v !== null && isFinite(v)) { acc += v; n++; }
    }
    const raw = n ? acc / n : null;
    const u = raw === null ? null
      : Math.max(0, Math.min(1, (raw - s._lo) / (s._hi - s._lo)));
    out.push([Math.min(to, i + (k - 1) / 2), u, raw]);
  }
  return out;
}

/* Segmenti contigui: una corsia con un buco non va chiusa attraverso il buco, o il
   riempimento salterebbe il 2022 come se fosse pieno. */
function ridgeRuns(pts) {
  const out = []; let cur = null;
  for (const p of pts) {
    if (p[1] === null) { cur = null; continue; }
    if (!cur) { cur = []; out.push(cur); }
    cur.push(p);
  }
  return out;
}

/* Disegna la ridgeline e restituisce l'SVG piu' i riferimenti a ogni corsia: il
   chiamante non deve ricercare niente nel documento che ha appena costruito. */
function drawRidge(lanes, W, from, to, step, showAxis, pinnedSet, nums) {
  const amp = step * RIDGE_OVER;
  const P = { l:10, r:10, t:5, b:showAxis ? 18 : 6 };
  const iw = Math.max(40, W - P.l - P.r);
  const H = Math.round(P.t + amp + Math.max(0, lanes.length - 1) * step + P.b);
  const X = v => P.l + (to === from ? iw / 2 : (v - from) / (to - from) * iw);
  const svg = el("svg", { class:"plot", viewBox:`0 0 ${W} ${H}`, role:"img",
    "aria-label":`Vista compatta: ${lanes.length} serie, una corsia ciascuna, ` +
      `ognuna riscalata sulla propria storia` });

  const refs = [];
  /* Quanto una corsia copre quella sotto. Era .88, ed e' il numero che l'utente ha
     visto come "scatola": a quel valore ogni corsia e' praticamente un foglio
     opaco appoggiato sopra il disegno, e la vista si legge come venti riquadri
     impilati invece che come un rilievo.
     Il pavimento non e' estetico, e' geometrico. Con RIDGE_OVER = 1.2 una corsia
     sale 1,2 passi mentre le basi ne distano 1: sconfina di 0,2 passi, e SOLO in
     quella immediatamente sopra (1,2 < 2, quindi non arriva mai alla seconda).
     Quindi in nessun punto si sommano piu' di DUE riempimenti — la "nebbia da
     ventiquattro velature" che l'88 % doveva evitare non e' mai stata possibile con
     questa geometria. A .62 lo stack piu' profondo lascia passare 1 − .62² ≈ 14 %
     del fondo, il tracciato di dietro traspare abbastanza da dire "sto dietro" e
     non abbastanza da confondersi con quello davanti. Sotto .5 le due linee
     cominciano a pesare uguale e la sovrapposizione smette di avere un davanti:
     e' li' che si e' fermata, non piu' in basso. */
  const OCCL = .62;
  const anyPin = lanes.some(L => pinnedSet.has(L.s.key));
  /* dall'alto verso il basso: ogni corsia viene disegnata DOPO quella che le sta
     sopra, quindi la copre — e' cosi' che una sovrapposizione si legge come
     profondita' invece che come due tracciati che si accavallano */
  lanes.forEach((L, k) => {
    const s = L.s, base = P.t + amp + k * step;
    const Y = u => base - u * amp;
    const g = el("g", {});
    g.dataset.series = s.key;
    g.dataset.pinned = pinnedSet.has(s.key) ? "1" : "";
    const on = pinnedSet.has(s.key);
    /* congelata = piu' contrasto, non un riquadro. Le altre si ritirano di un passo
       (piu' sottili, piu' trasparenti) e quella congelata prende un alone: e'
       l'evidenziazione che non aggiunge bordi al disegno. */
    const dim = anyPin && !on;

    /* dove la corsia comincia e dove finisce DAVVERO. Serve perche' quasi nessuna
       serie copre tutta la finestra: in "sempre" il carico parte al 37 % della
       larghezza, sonno e HRV all'86 %, la tavola all'82 %. Senza un segno, quei due
       terzi vuoti si leggono come un grafico che si e' rotto — ed e' esattamente il
       reclamo da cui nasce tutto questo ("some graphs stop in the middle"). */
    const runs = ridgeRuns(L.pts).filter(r => r.length >= 2);
    const i0 = runs.length ? runs[0][0][0] : null;
    const i1 = runs.length ? runs[runs.length - 1][runs[runs.length - 1].length - 1][0] : null;

    /* la linea di base attraversa TUTTA la corsia, tratteggiata dove non c'e' nulla:
       il vuoto smette di essere assenza di disegno e diventa disegno dell'assenza.
       Vale per i tre vuoti diversi, che a occhio erano lo stesso niente: prima che
       la serie cominci, dopo che ha smesso, e i buchi in mezzo — la temperatura al
       polso esiste solo nei giorni con un'uscita, quindi in "sempre" si spezza in
       sette tratti, ed erano proprio quelli a leggersi come un grafico interrotto. */
    const voids = [];
    let cur = from;
    for (const run of runs) { voids.push([cur, run[0][0]]); cur = run[run.length - 1][0]; }
    voids.push([cur, to]);
    let voidPx = 0;
    for (const [a, b] of voids) {
      if (X(b) - X(a) < 3) continue;   /* sotto i 3 px il tratteggio e' un puntino */
      voidPx += X(b) - X(a);
      g.appendChild(el("line", { x1:X(a), x2:X(b), y1:base, y2:base,
        stroke:"var(--muted)", "stroke-width":1, opacity:".28",
        "stroke-dasharray":"1 5" }));
    }
    const startGapPx = i0 === null ? X(to) - X(from) : X(i0) - X(from);

    for (const run of runs) {
      const d = run.map((p, j) => (j ? "L" : "M") + X(p[0]).toFixed(1) + " " +
        Y(p[1]).toFixed(1)).join(" ");
      const closed = d + " L" + X(run[run.length - 1][0]).toFixed(1) + " " +
        base.toFixed(1) + " L" + X(run[0][0]).toFixed(1) + " " + base.toFixed(1) + " Z";
      /* due riempimenti: l'occlusore, che decide quanto la corsia copre quella di
         sotto, e sopra una velatura del colore della sezione. Quello che l'occlusore
         lascia passare vale anche per le bande "nessun dato": coprirle sarebbe
         cancellarle, e con OCCL piu' basso adesso si vedono meglio di prima. */
      g.appendChild(el("path", { d:closed, fill:"var(--paper)", opacity:String(OCCL) }));
      g.appendChild(el("path", { d:closed, fill:s.col,
        opacity:on ? ".30" : dim ? ".07" : ".13" }));
      if (on) {
        /* l'alone: lo stesso tracciato, largo e trasparente, sotto quello vero */
        g.appendChild(el("path", { d, fill:"none", stroke:s.col, "stroke-width":7,
          "stroke-linejoin":"round", "stroke-linecap":"round", opacity:".22" }));
      }
      g.appendChild(el("path", { d, fill:"none", stroke:s.col,
        "stroke-width":on ? 2.8 : dim ? 1.3 : 1.7, "stroke-linejoin":"round",
        "stroke-linecap":"round", opacity:on ? "1" : dim ? ".45" : ".92" }));
    }

    /* ---- LE MEDIE A OTTAVI, ANCHE QUI (ordine #23, 19/08/2026) --------------
       «Questo tipo di grafico deve essere riprodotto poi nella compatta con le
       barre orizzontali, cosi' che io possa confrontare in modo visivo se uno e'
       sceso di un tot» — e l'esempio suo era proprio il punteggio del sonno.
       Sono le stesse barre di `eighths`: la finestra divisa in otto tratti uguali
       di pixel, una barra all'altezza della media di ogni tratto, nere perche'
       annotazione e non serie. Il numero NON si stampa su venti corsie — venti
       righe da otto numeri sarebbero la nebbia che questa vista esiste per
       evitare: sta nella striscia delle congelate (`nums`), dove le corsie sono
       poche e c'e' il posto, e nel tooltip di ogni corsia. */
    const span8 = (to - from + 1) / FRAMES;
    let ott = null, ottNums = 0;
    if (span8 >= 1 && s._min !== null) {
      const acc8 = Array.from({ length:FRAMES }, () => ({ s:0, c:0 }));
      for (const p of L.pts) {
        if (p[2] === null || !isFinite(p[2])) continue;
        let q = Math.floor((p[0] - from) / span8);
        if (q < 0) q = 0; if (q >= FRAMES) q = FRAMES - 1;
        acc8[q].s += p[2]; acc8[q].c++;
      }
      ott = acc8.map(a => a.c ? a.s / a.c : null);
      const w8 = iw / FRAMES;
      const labs8 = ott.map(v => v === null ? "" : String(s.fmt(v)));
      const wide8 = Math.max(...labs8.map(x => x.length)) * TICKW + 6;
      const every8 = Math.max(1, Math.ceil(wide8 / w8));
      ott.forEach((v, q) => {
        if (v === null) return;   /* ottavo senza dati: niente, mai uno zero */
        const u = Math.max(0, Math.min(1, (v - s._lo) / (s._hi - s._lo)));
        const y = Y(u), x8 = P.l + w8 * q;
        /* un tratto, non un rect: dentro una corsia l'unico rettangolo ammesso e'
           la zona sensibile trasparente (check «congelare non aggiunge riquadri») */
        g.appendChild(el("line", { x1:x8 + 1.5, x2:x8 + 1.5 + Math.max(2, w8 - 3),
          y1:y, y2:y, stroke:"var(--ink)", "stroke-width":2.5,
          opacity:on ? ".8" : dim ? ".12" : ".45", "pointer-events":"none" }));
        if (!nums || q % every8) return;
        const cx8 = x8 + w8 / 2;
        if (cx8 - wide8 / 2 < 2 || cx8 + wide8 / 2 > W - 2) return;
        const t8 = el("text", { x:cx8,
          y:Math.min(base - 2, Math.max(base - step + 9, y - 4)),
          "text-anchor":"middle", fill:"var(--ink)", "font-size":"10",
          "font-weight":"700",
          "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
          stroke:"var(--paper)", "stroke-width":"3", "paint-order":"stroke",
          "stroke-linejoin":"round", "pointer-events":"none" });
        t8.textContent = labs8[q]; g.appendChild(t8); ottNums++;
      });
    }

    /* una serie RADA: pochi punti veri distribuiti su tanti giorni, che la media
       mobile centrata unisce in una linea continua. La linea non e' falsa — e' una
       media — ma sembra una misura quotidiana, e non lo e': il peso sono 65 pesate
       in due anni. La parola sull'etichetta e' il modo piu' economico di dirlo. */
    let nRaw = 0;
    for (let i = from; i <= to; i++) {
      const v = s.arr[i]; if (v !== null && v !== undefined) nRaw++;
    }
    const cover = i0 === null ? 0 : (i1 - i0 + 1);
    const sparse = nRaw > 0 && cover > 30 && nRaw < cover * .33;

    /* l'etichetta sta SULLA linea, con un alone del colore della scheda sotto le
       lettere: e' l'unica identita' che la corsia ha, quindi deve restare leggibile
       anche quando la linea le passa attraverso */
    const labText = (on ? "❄ " : "") + s.name + (sparse ? " · rada" : "");
    const label = el("text", { x:P.l + 7, y:base - 5,
      fill:on ? "var(--accent)" : dim ? "var(--muted)" : "var(--ink)",
      "font-size":"10.5", "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
      "letter-spacing":".03em", stroke:"var(--paper)", "stroke-width":"3.4",
      "paint-order":"stroke", "pointer-events":"none" });
    label.textContent = labText;
    g.appendChild(label);
    const labRight = P.l + 7 + labText.length * TICKW * 1.28;

    /* la scala della corsia, scritta sulla corsia: e' l'unico posto in cui questa
       vista puo' dire quanto vale un'altezza, e senza sarebbe una forma senza unita' */
    let rngLeft = W - P.r;
    if (s._min !== null) {
      const rng = `${s.fmt(s._lo)} → ${s.fmt(s._hi)}`;
      const wRng = rng.length * TICKW;
      if (labRight + 14 < W - P.r - wRng) {
        rngLeft = W - P.r - wRng;
        const t = el("text", { x:W - P.r, y:base - 5, "text-anchor":"end",
          fill:"var(--muted)", "font-size":"8", "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
          stroke:"var(--paper)", "stroke-width":"3", "paint-order":"stroke",
          "pointer-events":"none" });
        t.textContent = rng; g.appendChild(t);
      }
    }

    /* il segno di inizio corsia: un trattino verticale sul primo giorno misurato, e
       l'anno accanto se ci sta fra il nome e l'escursione. Va messo solo quando c'e'
       davvero del vuoto prima, o su una corsia piena sarebbe una tacca senza motivo. */
    if (i0 !== null && startGapPx > 12) {
      g.appendChild(el("line", { x1:X(i0), x2:X(i0), y1:base, y2:base - 9,
        stroke:"var(--muted)", "stroke-width":1, opacity:".6" }));
      const lab = String(dayDate(Math.round(i0)).getFullYear());
      const w = lab.length * TICKW;
      if (X(i0) - 4 - w > labRight + 8 && X(i0) - 4 < rngLeft - 8) {
        const t = el("text", { x:X(i0) - 4, y:base - 5, "text-anchor":"end",
          fill:"var(--muted)", "font-size":"8", "font-family":"ui-monospace,'SFMono-Regular',Menlo,monospace",
          stroke:"var(--paper)", "stroke-width":"3", "paint-order":"stroke",
          "pointer-events":"none" });
        t.textContent = lab; g.appendChild(t);
      }
    }

    /* la zona sensibile e' la fascia della corsia, non il tracciato: cliccare una
       linea alta due pixel non e' un bersaglio. E' raggiungibile da tastiera perche'
       congelare e' un comando vero: gli interruttori laterali sono bottoni e si
       tabulano, e lasciare l'altro comando della vista solo al mouse avrebbe fatto
       una meta' di pagina pilotabile e una no. */
    const hit = el("rect", { x:P.l, y:base - step, width:iw, height:step,
      fill:"transparent", style:"cursor:pointer", tabindex:"0", role:"button",
      "aria-label":(on ? "Sgancia " : "Congela ") + s.name });
    hit.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); togglePin(s.key); }
    });
    hit.addEventListener("pointermove", ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width * W;
      const i = Math.round(from + (px - P.l) / iw * (to - from));
      let best = null;
      for (const p of L.pts) if (p[1] !== null &&
        (!best || Math.abs(p[0] - i) < Math.abs(best[0] - i))) best = p;
      if (!best) { hideTip(); return; }
      /* l'ottavo su cui sta il puntatore: il tooltip porta anche la sua media,
         perche' nella colonna delle venti corsie la barra c'e' ma il numero no */
      const q8 = ott ? Math.max(0, Math.min(FRAMES - 1,
        Math.floor((best[0] - from) / span8))) : -1;
      showTip(ev.clientX, ev.clientY,
        `<span class="d">${fmtDate(Math.round(best[0]))}</span><br>` +
        `${s.name} <span class="v">${s.fmt(best[2])}</span><br>` +
        `<span class="d">${nf(best[1] * 100, 0)} % della sua escursione` +
        (sparse ? ` · serie rada: ${nf(nRaw)} misure in ${nf(cover)} giorni, ` +
                  `la linea è la loro media mobile` : "") +
        `</span>` +
        (q8 >= 0 && ott && ott[q8] !== null
          ? `<br>media dell'ottavo ${q8 + 1}/8 <span class="v">${s.fmt(ott[q8])}</span>`
          : "") +
        `<br><span class="d">${pinnedSet.has(s.key) ? "clicca per sganciarla" : "clicca per congelarla"}` +
        `</span>`);
    });
    hit.addEventListener("pointerleave", hideTip);
    hit.addEventListener("click", () => togglePin(s.key));
    g.appendChild(hit);

    svg.appendChild(g);
    refs.push({ key:s.key, name:s.name, labelText:labText, sparse, nRaw,
      i0, i1, voidPx, startGapPx, g, label, base, pinned:on, ott, ottNums });
  });
  /* Le bande "nessun dato" vanno SOPRA le corsie, non sotto come nei riquadri
     estesi: qui i riempimenti sono opachi all'88 % e una banda sotto ventiquattro
     corsie sarebbe stata cancellata da tutte tranne la prima. Sopra, il 5 % di
     bianco schiarisce appena la colonna del 2022 lungo tutta l'altezza — che e'
     esattamente quello che quella colonna deve dire. */
  gapBands(svg, X, from, to, P.t, H - P.t - P.b);
  if (showAxis) xDates(svg, X, W, H, from, to, iw);
  return { svg, H, refs };
}

/* ------------------------------------------------------------------ render */
/* Built node by node rather than from an innerHTML blob, and every part kept on a
   reference: nothing here has to query the document back for something it just
   made, which is what lets tools/check_vita.cjs drive the whole page against a
   fifty-line DOM shim instead of pulling in a browser. */
const mk = (tag, cls, parent, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
};

function tileNode(t) {
  const art = mk("article", "tile" + (t.cls ? " " + t.cls : ""));
  const side = mk("div", "t-side", art);
  const head = mk("div", "t-head", side);
  mk("div", "t-title", head, t.title);
  /* Obbligatoria: se un riquadro nuovo nasce senza `src`, si vede subito invece di
     scivolare in pagina senza dire da dove vengono i suoi numeri. */
  const sp = mk("button", "t-src", head, SRC_LAB[t.src] || "??");
  sp.setAttribute("type", "button");
  sp.setAttribute("data-src", t.src || "");
  sp.setAttribute("data-info", "provenienza:" + (t.src || "ignota"));
  sp.setAttribute("aria-label", "Provenienza: " + (SRC_LAB[t.src] || "non dichiarata"));
  if (sp.dataset) { sp.dataset.src = t.src || ""; sp.dataset.info = "provenienza:" + (t.src || "ignota"); }
  const now = mk("div", "t-now", side);
  /* Niente sottotitolo sotto il titolo, e niente "media 7 gg" sotto il numero
     grande (2026-08-14: "non voglio sottotitoli ai grafici… in genere non voglio
     testi tipo media di 7 giorni"). Il titolo e il disegno bastano a guardare; la
     didascalia e cosa sia esattamente il numero grande stanno un clic sotto, in
     "dati", insieme alla tabella. Chi vuole leggere apre, chi vuole guardare no. */
  const shift = t.shifters ? mk("div", "t-shift", side) : null;
  let lg = null;
  if (t.legend) {
    lg = mk("div", "t-legend", side);
    lg.innerHTML = t.legend.map(([n, c]) =>
      `<span><i style="background:${c}"></i>${n}</span>`).join("");
  }
  const box = mk("div", "figbox", art);
  /* La riga della finestra e il bottone «dati» stanno nello STESSO rigo, non uno
     sotto l'altro: erano due righe da diciotto pixel per riquadro, cioe' oltre
     seicento pixel di pagina su trentacinque riquadri, spesi per due stringhe corte
     che ci stanno affiancate anche a 390 px (Michele, ordine #22: «più compatto, più
     in linea»). Quando «dati» si apre, la tabella riprende la riga intera da sola —
     `details.data[open]{flex-basis:100%}` — quindi non si comprime niente. */
  const bot = mk("div", "t-bottom", art);
  const foot = mk("div", "t-foot", bot);
  const det = mk("details", "data", bot);
  const sum = mk("summary", null, det, "dati");
  const cap = mk("p", "d-cap", det);
  const tbl = mk("table", "fallback", det);
  const tbody = mk("tbody", null, tbl);
  /* si tiene il riferimento, non lo si ricerca: `children` nel browser e' una
     HTMLCollection e non ha .find() — cercarlo li' uccideva l'intero script, cioe'
     la pagina senza nemmeno un grafico */
  return { art, head, now, box, foot, sum, cap, tbody, shift, lg };
}

/* Taglia una nota di metodo alla fine di una frase, entro il tetto, e solo se il pezzo
   che resta ha i tag bilanciati: meglio una nota lunga che un <strong> aperto e mai
   chiuso. Torna [quello che resta a schermo, quello che va dietro l'ⓘ]. */
const NOTA_MAX = 220;
function tagBilanciati(h) {
  const ap = {}, re = /<(\/?)([a-z][a-z0-9]*)[^>]*?(\/?)>/gi;
  let m;
  while ((m = re.exec(h))) {
    const [, chiude, tag, autoc] = m;
    if (autoc || /^(br|img|hr|input|meta|link)$/i.test(tag)) continue;
    const k = tag.toLowerCase();
    ap[k] = (ap[k] || 0) + (chiude ? -1 : 1);
    if (ap[k] < 0) return false;
  }
  return Object.values(ap).every(v => v === 0);
}
function tagliaNota(h) {
  if (!h || h.length <= NOTA_MAX) return [h, ""];
  let cut = -1;
  const re = /[.!?](\s|<)/g;
  let m, primo = -1;
  while ((m = re.exec(h))) {
    const fine = m.index + 1;
    if (primo < 0) primo = fine;
    if (fine <= NOTA_MAX) cut = fine; else break;
  }
  if (cut < 0) cut = primo;                 // mai meno della prima frase
  if (cut < 0 || cut >= h.length) return [h, ""];
  const corto = h.slice(0, cut).trim();
  if (!tagBilanciati(corto)) return [h, ""];
  return [corto, h.slice(cut).trim()];
}

function drawTile(n, t) {
  n.box.innerHTML = "";
  const W = Math.max(240, n.box.clientWidth || n.art.clientWidth - 32 || 360);
  /* Sul telefono il disegno e' piu' basso di un ottavo. Il viewBox e' largo quanto
     il contenitore, quindi il TESTO dentro al grafico non rimpicciolisce con lui —
     cambia solo quanta altezza si prende il tracciato, e quello che si guadagna e'
     un riquadro in piu' a schermata su trentacinque riquadri (ordine #22). Sotto i
     150 non si scende: li' dentro ci sono ancora i 34 pixel della fascia delle
     medie, e comprimerla la renderebbe illeggibile invece che compatta. */
  const H = W < 420 && t.h > 150 ? Math.max(150, Math.round(t.h * .86)) : t.h;
  const svg = el("svg", { class:"plot", viewBox:`0 0 ${W} ${H}`,
    role:"img", "aria-label":t.title + " — " + t.cap });
  const [from, to] = windowFor(t.first ? daysOf(t.first) : 0,
    t.first ? (D.last || {})[t.first] : undefined);
  let res = null, err = null;
  if (to - from >= 2) {
    /* a renderer that throws must not take the page down with it — but it must not
       masquerade as "no data" either, so the reason is kept where a check can see it */
    try { res = t.kind(svg, W, H, t.spec, from, to); }
    catch (e) { err = e; res = null; }
  }
  n.art.dataset.err = err ? String(err && err.message || err) : "";
  n.art.dataset.empty = res ? "" : "1";

  if (res) n.box.appendChild(svg);
  else mk("p", "t-empty", n.box, "Nessun dato in questa finestra.");

  if (t.shifters && n.shift) {
    n.shift.innerHTML = t.shifters().map(([e, lab, v, inv]) =>
      `<span aria-label="${lab}">${e} <i class="sh-l">${lab}</i> <b style="color:${(inv ? 1 - v : v) >= .6 ? "var(--s3)" : (inv ? 1 - v : v) >= .35 ? "var(--s4)" : "var(--neg)"}">${nf(v * 100, 0)}</b></span>`).join("");
  }
  if (t.now) {
    const v = t.now();
    n.now.innerHTML = v === null || v === undefined || !isFinite(v) ? ""
      : t.nowFmt(v);
    /* niente title=: dal telefono non esiste. Resta come etichetta accessibile,
       e NON dentro innerHTML — check_vita vieta di stampare l'unita' li' dentro. */
    n.now.removeAttribute && n.now.removeAttribute("title");
    if (t.nowUnit) n.now.setAttribute("aria-label", t.nowFmt(v) + " · " + t.nowUnit);
  }

  /* Sotto il grafico resta solo la riga CORTA: finestra, passo di aggregazione,
     n, r, punti fuori scala. Sono numeri, si leggono in un secondo, e cambiano
     come si guarda il disegno.
     La nota di metodo — i paragrafi sul perché quella soglia, cosa è misurato e
     cosa modellato — è andata sotto "dati" insieme alla didascalia (2026-08-14:
     "rimuovi dai sottografici info like…, metti nel toggle"). Non è sparita:
     sparita sarebbe stato pubblicare un indice costruito senza la sua formula,
     che è la cosa che questa pagina non fa. È a un clic. */
  const bits = [];
  if (res) {
    bits.push(`${fmtDate(from)} → ${fmtDate(to)}`);
    if (res.plan) bits.push(res.plan.label);
    if (res.stats) bits.push(`n ${nf(res.stats.n)}`);
    if (res.fit) bits.push(`r ${res.fit.r.toFixed(2)}`);
    if (res.best2) bits.push(res.best2);
    if (res.best) bits.push(`più alta ${res.best}`);
    if (res.outside) bits.push(`${res.outside} fuori scala`);
  }
  n.foot.innerHTML = t.noFoot ? "" : bits.join(" · ");
  n.sum.textContent = t.dataNote ? `dati · ${t.dataNote}` : "dati";
  /* LA NOTA DI METODO, TAGLIATA AL VERDETTO.
     Erano fino a 577 caratteri l'una, e nove riquadri su 42 (tutti nel metabolismo) si
     prendevano il 57 % di tutta la nota di metodo della pagina. Adesso sotto «dati»
     resta il verdetto — la prima frase, o le prime finche' ci stanno — e il resto
     (formula, fonte, il perche' di una soglia) va dietro l'ⓘ del riquadro.
     Non e' una potatura a occhio: il taglio cade a FINE FRASE e solo se il pezzo che
     resta ha i tag bilanciati, altrimenti non si taglia affatto. E le stringhe che
     check_vita cerca stanno nella prima frase apposta: se una finisse oltre il taglio,
     il controllo diventa rosso, che e' il modo giusto di accorgersene. */
  if (n.cap && t.foot) {
    const [corto, resto] = tagliaNota(t.foot);
    if (resto) {
      const k = "nota:" + t.panel + ":" + t.title;
      infoReg(k, t.title, `<p>${t.foot}</p>`);
      t._footCorto = corto;
      /* una volta sola: drawTile rigira a ogni cambio di finestra e a ogni resize, e
         senza questa guardia i bottoncini si accumulerebbero uno per ridisegno.
         Un flag sul nodo, non una querySelector: il DOM finto del check non ce l'ha. */
      if (n.head && !n._icoNota) { icoNode(n.head, k, t.title); n._icoNota = true; }
    }
  }
  /* la didascalia, la legenda del numero grande e la nota di metodo: tutto qui */
  if (n.cap) n.cap.innerHTML = [t.cap,
    /* solo quando aggiunge qualcosa: su dieci riquadri questa clausola ripeteva
       alla lettera il `cap` scritto due parole prima (Energia: «kcal al giorno ·
       media mobile 7 giorni» seguito da «Il numero grande: kcal al giorno»). */
    t.now && t.nowUnit && !String(t.cap || "").toLowerCase().includes(String(t.nowUnit).toLowerCase())
      ? `<b>Il numero grande</b>: ${t.nowUnit}.` : ""]
    .filter(Boolean).join(" · ") + (t.foot ? `<span class="d-note">${t._footCorto || t.foot}</span>` : "");
  n.tbody.innerHTML = res ? res.table : "";
}

const MOUNTED = [];
for (const t of TILES) {
  const host = document.getElementById("panel-" + t.panel);
  if (!host) continue;
  const n = tileNode(t);
  host.appendChild(n.art);
  MOUNTED.push([n, t]);
}

/* La scelta di vista sopravvive alla visita: chi legge questa pagina la apre cento
   volte, e ricominciare ogni volta dalla forma che non ha scelto e' un piccolo
   insulto ripetuto. In un contesto senza localStorage (il check gira in node) tutto
   torna al valore di default invece di sollevare. */
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; }
              catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};
let view = store.get("vita:view", "estesa") === "compatta" ? "compatta" : "estesa";
document.body.dataset.view = view;

/* Si disegna solo quello che si vede. Un riquadro esteso ridisegnato mentre la sua
   colonna e' display:none misura larghezza zero e si ridisegna a 240 px: tornando
   alla vista estesa si troverebbe una colonna di grafici stretti finche' non si
   ridimensiona la finestra. */
/* Lo stato delle sezioni sta QUI e non insieme al suo menu, trecento righe piu'
   giu': `drawAll` legge `secVisible`, e un `const` letto prima della sua riga non e'
   undefined — e' un ReferenceError che ferma tutto lo script. */
const SECS = [["tutte", "tutte"], ["carico", "Carico"], ["notte", "Notte"],
  ["recupero", "Recupero"], ["metabolismo", "Metabolismo"], ["volume", "Volume"],
  ["incroci", "Incroci"], ["tavola", "Tavola"]];
let sec = "tutte";
const secVisible = k => sec === "tutte" || sec === k;

const drawAll = () => {
  if (view === "compatta") drawCompact();
  /* Si disegna solo quello che e' VISIBILE, e si disegna DOPO averlo mostrato.
     E' la trappola gia' pagata una volta e scritta in state/open-loops.md: un
     riquadro ridisegnato mentre la sua sezione e' `display:none` misura larghezza
     zero, ricade sui 240px di sicurezza e resta largo 240 anche quando la sezione
     torna visibile. `setSec` mostra prima e ridisegna poi, e qui i nascosti si
     saltano — cosi' non esiste nemmeno il disegno sbagliato da correggere. */
  else for (const [n, t] of MOUNTED) { if (secVisible(t.panel)) drawTile(n, t); }
  drawCompare();
};
/* Object.assign, non un'assegnazione: `info` viene registrato molto piu' su, e una
   riassegnazione secca lo cancellerebbe senza che nessuno se ne accorga. */
Object.assign(window.CRUSCOTTO, { D, TILES, MOUNTED, drawAll, mm:mmDraw, mmMin:MM_MIN_COMP,
  setRange:k => { range = k; drawAll(); } });
window.openDay = openDay;   /* il check lo chiama per verificare il popup */

/* ------------------------------------------- il pannello della vista compatta */
const cxHost = document.getElementById("compact");
const cxNote = mk("p", "cx-note", cxHost);
/* Erano 1.139 caratteri, centrati e in corsivo, e in vista compatta il PRIMO blocco
   della pagina: piu' lunghi di qualunque intestazione di sezione. Facevano due mestieri
   incompatibili — dichiarare il metodo e insegnare i gesti.
   Quello che resta a schermo e' la riga che spiega perche' due corsie alte uguali NON
   valgono uguale: e' provenienza del disegno, e non va dietro un tocco.
   I gesti tornano dove si compiono, come chip accanto ai comandi: un'interazione che
   non si annuncia non esiste, e adesso si annuncia sul comando invece che in un
   paragrafo tre schermate piu' su. */
cxNote.innerHTML = "Ogni corsia sulla <strong>propria</strong> scala, dal 2° al 98° " +
  "percentile: si confrontano le forme, non i valori." +
  "<span class=\"cx-gesti\"><b>click</b> isola · <b>Ctrl</b>-click o <b>somma</b> " +
  "per piu' di una · <b>click sul grafico</b> congela</span>";
infoReg("compatta", "La vista compatta, per intero",
  `<p>Una corsia per serie, impilate con una sovrapposizione di un quinto. Ogni corsia è
   riscalata sulla <strong>propria</strong> storia — dal 2° al 98° percentile della sua
   media mobile su tutto l'archivio, non da zero: <strong>due corsie alte uguali non
   valgono uguale</strong>, dicono solo «ognuna al suo massimo». Qui si confrontano le
   forme e i tempi, mai i valori; per i valori c'è la vista estesa, che ha gli assi.</p>
   <p>Un click sul <strong>nome a lato isola</strong> quella serie; un click su un altro
   nome isola quello; lo stesso nome una seconda volta rimette tutto. Per accenderne e
   spegnerne <strong>più di una</strong>: ⌘ o Ctrl-click, oppure il modo
   <strong>somma</strong> in cima alla colonna, che fa la stessa cosa senza modificatore.
   <strong>Tutte</strong> rimette tutto. Un click <em>sul grafico</em> invece
   <strong>congela</strong> la corsia: resta in cima mentre il resto scorre, e nel
   disegno si distingue perché è più marcata, non perché sia in un riquadro.</p>
   <p>Dove una corsia è vuota resta il suo <strong>tratteggio</strong>: la serie non era
   ancora misurata. Il trattino verticale con l'anno segna il giorno in cui comincia —
   quasi nessuna comincia a sinistra. «Rada» accanto al nome vuol dire poche misure vere
   unite da una media mobile: la linea è continua, il dato no.</p>`);
const cxWrap = mk("div", "cx-wrap", cxHost);
const cxMain = mk("div", "cx-main", cxWrap);
const cxPinBox = mk("div", "cx-pin", cxMain);
cxPinBox.classList.add("off");
const cxPinTop = mk("div", "cx-pin-top", cxPinBox);
mk("div", "cx-pin-h", cxPinTop, "congelate");
const cxChips = mk("div", "cx-chips", cxPinTop);
const cxPinPlot = mk("div", "cx-pin-plot", cxPinBox);
const cxPlot = mk("div", "cx-plot", cxMain);
const cxFoot = mk("div", "cx-foot", cxMain);
const cxRail = mk("aside", "cx-rail", cxWrap);

const OFF = new Set((store.get("vita:off", "") || "").split(",").filter(Boolean));
const PIN = new Set((store.get("vita:pin", "") || "").split(",").filter(Boolean));
/* La serie ISOLATA: quella su cui un click ha spento tutte le altre. Si tiene a
   parte da OFF perche' "isolata" e "ho spento a mano tutto il resto" sono lo stesso
   insieme ma non lo stesso stato — solo la prima torna indietro al click successivo.
   Ripescandola da localStorage si verifica che il mondo la confermi ancora: se le
   serie sono cambiate fra una visita e l'altra, l'isolamento decade invece di
   lasciare una pagina con una corsia sola e nessuna spiegazione. */
let ISO = store.get("vita:iso", "") || null;
if (ISO && !(RIDGE.some(s => s.key === ISO) && !OFF.has(ISO) &&
             OFF.size === RIDGE.length - 1)) ISO = null;
/* Modo "somma": quando e' acceso ogni click accende/spegne una voce sola invece di
   isolarla. E' il gemello raggiungibile da tastiera di ⌘/Ctrl-click — un modificatore
   col mouse non esiste per chi naviga a tab, e mezza interazione non e' interazione. */
let MULTI = false;
let cxLast = null, cxPinLast = null;

/* Gli interruttori si costruiscono una volta sola e si tiene il riferimento a
   ognuno: cosi' un interruttore mosso via API (il check) e uno mosso col dito
   aggiornano lo stesso nodo, e nessuno deve ricercarlo nel documento. */
let cxAllBtn = null, cxMultiBtn = null;
(function buildRail() {
  const head = mk("div", "cx-rail-h", cxRail);
  cxAllBtn = mk("button", null, head, "tutte");
  cxAllBtn.type = "button";
  cxAllBtn.setAttribute("aria-label", "Mostra tutte le serie");
  cxAllBtn.addEventListener("click", showAll);
  cxMultiBtn = mk("button", null, head, "somma");
  cxMultiBtn.type = "button";
  /* il gesto si annuncia sul comando che lo compie, non in un paragrafo lontano */
  cxMultiBtn.setAttribute("aria-label", "Somma: accende piu' di una serie senza tenere premuto Ctrl");
  cxMultiBtn.setAttribute("aria-pressed", "false");
  cxMultiBtn.setAttribute("aria-label",
    "Selezione a somma: ogni click accende o spegne una serie invece di isolarla");
  cxMultiBtn.addEventListener("click", () => setMulti(!MULTI));

  const groups = [];
  for (const s of RIDGE) {
    let g = groups.find(x => x.name === s.sec);
    if (!g) { g = { name:s.sec, items:[] }; groups.push(g); }
    g.items.push(s);
  }
  for (const g of groups) {
    const box = mk("div", "cx-grp", cxRail);
    mk("div", "cx-grp-h", box, g.name);
    for (const s of g.items) {
      const b = mk("button", "cx-sw", box, s.name);
      b.type = "button";
      b.setAttribute("aria-pressed", String(!OFF.has(s.key)));
      /* anche al primo disegno, non solo dopo un click: un isolamento ripescato da
         localStorage deve arrivare gia' marcato, o alla riapertura la pagina mostra
         una corsia sola e nessun bottone che spieghi perche' */
      b.dataset.iso = ISO === s.key ? "1" : "";
      b.style.setProperty("--c", s.col);
      b.addEventListener("click", ev => railClick(s.key, ev));
      s._btn = b;
    }
  }
})();

/* L'unico posto che tocca OFF/ISO. Tutto il resto passa di qui, quindi non esiste
   un cammino che cambia le serie accese e si dimentica di aggiornare i bottoni o
   di salvare — che e' il modo in cui una selezione comincia a mentire. */
function syncRail() {
  for (const s of RIDGE) {
    if (!s._btn) continue;
    s._btn.setAttribute("aria-pressed", String(!OFF.has(s.key)));
    s._btn.dataset.iso = ISO === s.key ? "1" : "";
  }
  if (cxMultiBtn) cxMultiBtn.setAttribute("aria-pressed", String(MULTI));
  store.set("vita:off", [...OFF].join(","));
  store.set("vita:iso", ISO || "");
  if (view === "compatta") drawCompact();
}

/* Click semplice: ISOLA. Click su una voce gia' isolata: torna tutto.
   Click su un'altra voce: isola quella. Con il modificatore (o in modo "somma"):
   accende e spegne una voce sola, e l'isolamento decade — perche' da li' in poi
   l'insieme non e' piu' "quella serie", e' "quelle che ho scelto". */
/* Il cammino vero di un click su un interruttore: il modificatore si legge
   dall'evento e non dallo stato, cosi' ⌘/Ctrl-click funziona anche quando il modo
   "somma" e' spento — che e' il caso normale. Sta in una funzione con un nome
   perche' e' esattamente questa che il check deve poter chiamare: verificare
   selectSeries() direttamente proverebbe la regola e non il cablaggio. */
function railClick(key, ev) {
  selectSeries(key, MULTI || !!(ev && (ev.metaKey || ev.ctrlKey || ev.shiftKey)));
}
function selectSeries(key, additive) {
  if (additive) { ISO = null; setSeries(key, OFF.has(key)); return; }
  if (ISO === key) { ISO = null; OFF.clear(); }
  else { ISO = key; OFF.clear(); for (const s of RIDGE) if (s.key !== key) OFF.add(s.key); }
  syncRail();
}
function showAll() { ISO = null; OFF.clear(); syncRail(); }
function setMulti(on) { MULTI = !!on; syncRail(); }
function setSeries(key, on) {
  if (on) OFF.delete(key); else OFF.add(key);
  ISO = null;                 /* una voce mossa a mano scioglie l'isolamento */
  syncRail();
}
function togglePin(key) { setPin(key, !PIN.has(key)); }
function setPin(key, on) {
  if (on) PIN.add(key); else PIN.delete(key);
  store.set("vita:pin", [...PIN].join(","));
  if (view === "compatta") drawCompact();
}
function setView(v) {
  view = v === "compatta" ? "compatta" : "estesa";
  document.body.dataset.view = view;
  store.set("vita:view", view);
  for (const b of viewswEl.children) b.setAttribute("aria-pressed",
    String(b.dataset.view === view));
  drawAll();
}

function drawCompact() {
  const [from, to] = windowFor(0);
  const W = Math.max(280, cxPlot.clientWidth || 720);
  /* su schermo stretto il passo si accorcia: 84 px per corsia su un telefono
     farebbero venti corsie e cinque schermate di scorrimento */
  const step = W < 430 ? 62 : RIDGE_STEP;
  const iw = Math.max(40, W - 20);
  const all = RIDGE.filter(s => !OFF.has(s.key)).map(ridgePrep)
    .map(s => ({ s, pts:ridgePts(s, from, to, iw) }));
  const lanes = all.filter(L => L.pts.some(p => p[1] !== null));
  const mute = all.filter(L => !lanes.includes(L)).map(L => L.s.name);

  cxPlot.innerHTML = "";
  if (lanes.length) {
    cxLast = drawRidge(lanes, W, from, to, step, true, PIN);
    cxPlot.appendChild(cxLast.svg);
  } else {
    cxLast = null;
    mk("p", "t-empty", cxPlot, "Nessuna serie da mostrare in questa finestra.");
  }

  const pinned = lanes.filter(L => PIN.has(L.s.key));
  cxPinPlot.innerHTML = "";
  cxChips.innerHTML = "";
  if (pinned.length) {
    cxPinBox.classList.remove("off");
    /* `nums`: nella striscia i numeri delle medie a ottavi si stampano — le
       corsie congelate sono poche, e sono li' proprio per essere confrontate */
    cxPinLast = drawRidge(pinned, W, from, to, RIDGE_PIN_STEP, false, PIN, true);
    cxPinPlot.appendChild(cxPinLast.svg);
    for (const L of pinned) {
      const c = mk("button", "cx-chip", cxChips, "✕ " + L.s.name);
      c.type = "button";
      c.setAttribute("aria-label", "Sgancia " + L.s.name);
      c.addEventListener("click", () => setPin(L.s.key, false));
    }
  } else {
    cxPinBox.classList.add("off");
    cxPinLast = null;
  }

  const isoName = ISO ? (RIDGE.find(s => s.key === ISO) || {}).name : null;
  const rada = (cxLast ? cxLast.refs : []).filter(L => L.sparse).map(L => L.name);
  cxFoot.innerHTML = [
    `${fmtDate(from)} → ${fmtDate(to)}`,
    `${lanes.length} corsie su ${RIDGE.length}`,
    isoName ? `isolata: ${isoName}` : null,
    MULTI ? "modo somma acceso" : null,
    pinned.length ? `${pinned.length} congelate` : null,
    rada.length ? `rade: ${rada.join(", ")}` : null,
    mute.length ? `senza dati in questa finestra: ${mute.join(", ")}` : null,
  ].filter(Boolean).join(" · ") +
    "<br>Il numero a destra di ogni corsia è la sua escursione: quanto vale il fondo " +
    "corsia e quanto la cima. Fuori da quell'intervallo la linea viene tagliata al " +
    "bordo, non spostata altrove.";
}

window.CRUSCOTTO.compact = {
  series:RIDGE, setView, view:() => view,
  toggle:key => setSeries(key, OFF.has(key)),
  railClick, isolated:() => ISO, showAll,
  setMulti, multi:() => MULTI,
  allBtn:cxAllBtn, multiBtn:cxMultiBtn,
  enabled:() => RIDGE.filter(s => !OFF.has(s.key)).map(s => s.key),
  pin:key => setPin(key, true), unpin:key => setPin(key, false),
  pinned:() => [...PIN],
  lanes:() => cxLast ? cxLast.refs : [],
  pinLanes:() => cxPinLast ? cxPinLast.refs : [],
  svg:() => cxLast && cxLast.svg,
  pinSvg:() => cxPinLast && cxPinLast.svg,
  rail:cxRail, note:cxNote, foot:cxFoot,
};

/* ---------------------------------------------------------- range control */
const rangesEl = document.getElementById("ranges");
for (const r of RANGES) {
  const b = document.createElement("button");
  b.textContent = r.label; b.type = "button";
  b.setAttribute("aria-pressed", String(r.key === range));
  b.addEventListener("click", () => {
    range = r.key;
    for (const c of rangesEl.children) c.setAttribute("aria-pressed", String(c === b));
    drawAll();
  });
  rangesEl.appendChild(b);
}
/* ------------------------------------------------- le sezioni, per tema
   Michele, 18/08/2026: «si potrebbe avere uno slider o qualcosa per raccogliere i
   grafici per temi». E' un menu e non sette bottoni: sette bottoni in piu' nella
   barra appesa sarebbero due righe su un telefono, cioe' esattamente lo spazio che
   si stava cercando di recuperare.

   Parte da «tutte» apposta. Chi arriva su /vita non sa che ci sono sette sezioni:
   aprire su una sola vorrebbe dire nascondergli sei settimi della pagina prima che
   sappia che esistono. La scelta pero' resta fra una visita e l'altra, quindi chi
   guarda sempre e solo il carico se lo ritrova. */
/* per id e non con un querySelectorAll: e' l'unica cosa che sa fare anche il
   DOM finto di check_vita.cjs, e un elenco che il check non sa leggere e' un
   pezzo di pagina che nessuno prova piu' */
/* coppie [chiave, nodo], non `dataset.sec`: la chiave la sa gia' SECS, e leggerla
   dall'attributo vorrebbe dire fidarsi di un DOM che qui puo' essere finto. */
const secNodes = SECS.slice(1).map(([k]) => [k, document.getElementById("sec-" + k)])
  .filter(x => x[1]);
sec = store.get("vita:sec", "tutte");
if (!SECS.some(x => x[0] === sec)) sec = "tutte";
function setSec(k) {
  sec = k;
  for (const [key, n] of secNodes) n.style.display = secVisible(key) ? "" : "none";
  store.set("vita:sec", k);
  drawAll();                       /* DOPO: vedi il commento in drawAll */
}
const secSel = document.getElementById("secsel");
if (secSel) {
  secSel.innerHTML = SECS.map(([k, l]) =>
    `<option value="${k}"${k === sec ? " selected" : ""}>${l}</option>`).join("");
  secSel.addEventListener("change", () => setSec(secSel.value));
}
for (const [key, n] of secNodes) n.style.display = secVisible(key) ? "" : "none";
window.CRUSCOTTO.sections = { list:SECS, set:setSec, get:() => sec, nodes:secNodes };

/* ----------------------------------------------------------- forma della vista */
const viewswEl = document.getElementById("viewsw");
for (const v of [["estesa", "estesa"], ["compatta", "compatta"]]) {
  const b = document.createElement("button");
  b.textContent = v[1]; b.type = "button";
  b.dataset.view = v[0];
  b.setAttribute("aria-pressed", String(v[0] === view));
  b.addEventListener("click", () => setView(v[0]));
  viewswEl.appendChild(b);
}

/* Il paragrafo che stava qui — 110 caratteri fra i comandi e i grafici — mostrava la
   STESSA identica stringa su tre finestre su quattro. Adesso e' un ⓘ accanto ai
   bottoni, e porta tutte e due le varianti. Attenzione a non riesumare `noteEl`: il
   nodo non esiste piu', e lo shim del check ne inventa uno a chiunque lo chieda, quindi
   un `noteEl.textContent` di ritorno passerebbe il check e ucciderebbe la pagina vera. */
infoReg("finestra", "Che cosa cambia la finestra temporale",
  `<p>Con <strong>sempre</strong>, ogni riquadro parte da dove comincia la <em>sua</em>
   serie, non da dove comincia l'archivio: il carico dal 2019, sonno e HRV dal 2025. I
   riquadri della stessa schermata quindi <strong>non coprono lo stesso periodo</strong>.</p>
   <p>Con una finestra scelta, è la stessa su tutti. Dove la serie non arriva così
   indietro, il riquadro parte da dove può.</p>
   <p><strong>Le otto barre nere</strong> dividono in <strong>ottavi</strong> la finestra
   che stai guardando: ognuna sta all'altezza della media del suo ottavo, e il numero
   sopra è quella media. Cambiando finestra cambiano di significato — otto ottavi di due
   anni sono trimestri, otto ottavi di un trimestre sono undici giorni l'uno. Sono nere
   e non colorate perché <em>non sono una serie</em>: sono una nota sopra le altre.
   Un ottavo senza dati non disegna niente, e uno la cui media cade fuori dalla scala
   nemmeno.</p>`);
icoNode(document.getElementById("ranges"), "finestra", "la finestra temporale");

/* ------------------------------------------------------ confronto selezionabile
   Usa i valori giornalieri non smussati. Il ritardo di un giorno serve soprattutto
   per domande sensate come "carico o carboidrati oggi contro recupero domani". */
const compareX = document.getElementById("compare-x");
const compareY = document.getElementById("compare-y");
const compareLag = document.getElementById("compare-lag");
const compareMode = document.getElementById("compare-mode");
const comparePlot = document.getElementById("compare-plot");
const compareResult = document.getElementById("compare-result");
const CF = D.nutri || {};
/* Le serie confrontabili NON si scrivono a mano.
   Erano un elenco fisso, e come ogni elenco fisso accanto a un registro vivo era
   rimasto indietro: la ridgeline aveva ventisette corsie, il menu ventiquattro voci,
   e mancavano proprio quelle nuove — heat strain, temperatura, momento metabolico.
   Chi aggiungeva una corsia non aveva motivo di sapere che c'era un secondo posto da
   aggiornare. Adesso il menu ESCE da RIDGE, che e' gia' il registro di tutto quello
   che la pagina sa disegnare: una corsia nuova compare da sola anche qui, e i due
   elenchi non possono piu' divergere.
   Le voci qui sotto sono solo quelle che una corsia non ce l'hanno — nutrienti che
   nella vista compatta non stanno, ma che ha senso incrociare. */
const compareExtra = [
  ["protein","Tavola","Proteine",CF.protein_g,v=>nf(v,0)+" g"],
  ["carb","Tavola","Carboidrati",CF.carb_g,v=>nf(v,0)+" g"],
  ["fat","Tavola","Grassi",CF.fat_g,v=>nf(v,0)+" g"],
  ["satfat","Tavola","Grassi saturi",CF.satfat_g,v=>nf(v,1)+" g"],
  ["sodium","Tavola","Sodio",CF.sodium_mg,v=>nf(v,0)+" mg"],
  ["pctprot","Tavola","Quota kcal proteine",CF.pct_kcal_protein,FMT.pct],
  ["pctcarb","Tavola","Quota kcal carboidrati",CF.pct_kcal_carb,FMT.pct],
  ["pctfat","Tavola","Quota kcal grassi",CF.pct_kcal_fat,FMT.pct],
  ["dairy","Tavola","Quota latticini",CF.pct_dairy,FMT.pct],
  ["animal","Tavola","Quota animale",CF.pct_animal,FMT.pct],
  ["vit","Tavola","Indice vitamine",CF.vit_index,FMT.pct],
  ["min","Tavola","Indice minerali",CF.min_index,FMT.pct],
  ["carbgap","Tavola","Scarto carboidrati",CF.carb_gap_g,v=>nf(v,0)+" g"],
  ["plantsday","Tavola","Piante del giorno",CF.plants_day,FMT.num0],
  ["fatmax","Metabolismo","FatMax",(D.metab||{}).fatmax_hr,FMT.bpm],
  ["fatmaxmin","Metabolismo","Minuti in FatMax",(D.metab||{}).fatmax_min,FMT.num0],
];
const compareSeries = [
  ...RIDGE.map(l=>[l.key,l.sec,l.name,l.arr,l.fmt]),
  ...compareExtra,
].filter(s=>Array.isArray(s[3]) && s[3].some(v=>v!==null&&v!==undefined));
const compareByKey = new Map(compareSeries.map(s=>[s[0],s]));
const compareOptions = compareSeries.map(s=>`<option value="${s[0]}">${s[1]} · ${s[2]}</option>`).join("");
compareX.innerHTML = compareOptions; compareY.innerHTML = compareOptions;
compareX.value = compareByKey.has("sleep") ? "sleep" : compareSeries[0][0];
compareY.value = compareByKey.has("hrv") ? "hrv" : compareSeries[Math.min(1,compareSeries.length-1)][0];

/* Correlazione sulle VARIAZIONI, non solo sui livelli.
   In finanza non si correlano i prezzi, si correlano i rendimenti, e per un motivo
   che vale identico qui: due serie che salgono nello stesso periodo escono correlate
   anche quando non c'entrano niente l'una con l'altra: e' il tempo che le muove
   tutte e due. Fitness e peso salgono insieme per una stagione e r dice 0,8 — ma non
   e' il peso a fare la fitness. Sulle differenze il trend condiviso sparisce e resta
   solo "quando questa si muove, si muove anche quella?", che e' la domanda vera.
   d1 = differenza col giorno prima; d7 = con la settimana prima, che toglie anche il
   ritmo settimanale (il lungo della domenica, il riposo del lunedi'). */
const diffed=(arr,k)=>{
  if(!k) return arr;
  const out=new Array(arr.length).fill(null);
  for(let i=k;i<arr.length;i++){
    const a=arr[i],b=arr[i-k];
    if(a===null||a===undefined||b===null||b===undefined)continue;
    out[i]=a-b;
  }
  return out;
};
const pearson=pts=>{
  const n=pts.length; if(n<4) return null;
  let sx=0,sy=0; for(const p of pts){sx+=p[0];sy+=p[1];}
  const mx=sx/n,my=sy/n; let num=0,dx=0,dy=0;
  for(const p of pts){const a=p[0]-mx,b=p[1]-my;num+=a*b;dx+=a*a;dy+=b*b;}
  return (dx>0&&dy>0)?num/Math.sqrt(dx*dy):null;
};
const MODE_K={lv:0,d1:1,d7:7};
const MODE_LABEL={lv:"livelli",d1:"variazioni giorno su giorno",
  d7:"variazioni settimana su settimana"};

function pairsFor(sx,sy,k,lag,from,to){
  const ax=diffed(sx[3],k), ay=diffed(sy[3],k), pts=[];
  for(let i=from;i<=to-lag;i++){
    const x=ax[i], y=ay[i+lag];
    if(x===null||x===undefined||y===null||y===undefined||!isFinite(x)||!isFinite(y))continue;
    pts.push([x,y,i+lag]);
  }
  return pts;
}

function drawCompare(){
  if(!compareSeries.length) return;
  const sx=compareByKey.get(compareX.value), sy=compareByKey.get(compareY.value);
  const lag=Number(compareLag.value)||0, [from,to]=windowFor(0);
  const mode=compareMode.value||"lv", k=MODE_K[mode]||0;
  const pts=pairsFor(sx,sy,k,lag,from,to);
  comparePlot.innerHTML="";
  if(pts.length<4){
    comparePlot.innerHTML='<p class="t-empty">Meno di quattro giorni in comune in questa finestra.</p>';
    compareResult.innerHTML='<b>r = —</b><span>campione insufficiente</span>';
    return;
  }
  const W=Math.max(280,comparePlot.clientWidth||720),H=280;
  const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img",
    "aria-label":`${sx[2]} contro ${sy[2]}`});
  comparePlot.appendChild(svg);
  const unit=mode==="lv"?"":" (Δ)";
  const rendered=rXY(svg,W,H,{xname:sx[2]+unit,yname:sy[2]+unit,xfmt:sx[4],yfmt:sy[4],r:3,
    points:()=>[{name:lag?"Y il giorno dopo":"stesso giorno",col:"var(--s1)",pts}]},from,to);
  const f=rendered&&rendered.fit;
  if(!f){compareResult.innerHTML='<b>r = —</b><span>varianza insufficiente</span>';return;}
  const a=Math.abs(f.r), strength=a<.2?"molto debole":a<.4?"debole":a<.6?"moderata":a<.8?"forte":"molto forte";

  /* L'altro modo si calcola SEMPRE, anche quando non e' quello disegnato: e' il
     controllo che dice se un r alto e' una relazione o solo due trend paralleli. */
  const rLv=mode==="lv"?f.r:pearson(pairsFor(sx,sy,0,lag,from,to));
  const rD=mode==="lv"?pearson(pairsFor(sx,sy,1,lag,from,to)):f.r;

  /* Le due soglie sono tarate sui dati veri, non a caso: in questo archivio quasi
     tutte le associazioni stanno vicine a zero, e l'unica coppia con dell'andamento
     condiviso davvero grosso e' piante x microbiota (0,44 sui livelli, 0,26 sulle
     variazioni). Con una soglia di 0,25 di scarto non si sarebbe accesa proprio
     dove serviva. A 0,15 si accende li' e resta zitta su fitness x fatica, che sulle
     variazioni regge eccome (0,94 → 0,97). */
  let caveat="";
  if(rLv!==null&&rD!==null&&Math.abs(rLv)>=.3&&Math.abs(rLv)-Math.abs(rD)>=.15){
    caveat=`<p class="cmp-warn">Sui livelli r = ${nf(rLv,2)}, sulle variazioni `+
      `${nf(rD,2)}: quasi tutta l'associazione è <strong>andamento condiviso</strong>, `+
      `non le due serie che si muovono insieme. Le due cose salgono nello stesso `+
      `periodo — il che non vuol dire che una tiri l'altra.</p>`;
  }else if(rLv!==null&&rD!==null&&Math.abs(rD)>=.3&&Math.abs(rD)>=Math.abs(rLv)){
    caveat=`<p class="cmp-ok">Regge anche sulle variazioni (r = ${nf(rD,2)}): `+
      `non è solo trend condiviso.</p>`;
  }

  compareResult.innerHTML=`<b>r = ${nf(f.r,2)}</b><span>${f.n} giorni in comune</span>`+
    `<span>R² = ${nf(f.r*f.r,2)}</span><span>${MODE_LABEL[mode]}</span>`+
    `<p>Associazione ${strength}${f.r<0?", inversa":""}. `+
    `${lag?"X è il giorno precedente a Y.":"Le misure sono dello stesso giorno."}</p>`+
    caveat;
}
/* ------------------------------------------------------- le dieci coppie notevoli
   Non sono le coppie a cui qualcuno ha pensato: sono uscite calcolando TUTTE le
   2.958 combinazioni di serie per due sfasamenti (stesso giorno e giorno dopo), su
   livelli e su variazioni settimana su settimana. Poi tre filtri, in quest'ordine:

     1. via le coppie dentro la stessa sezione. Fibre x magnesio (r 0,79) o kcal x
        carboidrati (0,92) non sono scoperte: sono il database alimenti che si
        specchia. Lo stesso vale per ore x chilometri (0,93) e CTL x ATL (0,94).
     2. via quelle il cui r sui livelli crolla sulle variazioni: li' e' il tempo che
        muove tutte e due, non una che tira l'altra.
     3. di quello che resta, si tiene cio' che dice una cosa che non si sapeva gia' —
        **compresi gli zeri**. In questo archivio quattro delle dieci sono zeri, e
        sono il risultato piu' solido che ci sia: n intorno a 550 e r sotto 0,15
        non e' "non si e' trovato niente", e' "non c'e' niente da trovare".

   Ogni voce porta il suo r e il suo n scritti in chiaro: se un giorno cambiano, la
   frase accanto va riletta, e questo e' il punto. */
const CX_PRESETS = [
  { k:"caldo-rhr", doit:"Una giornata calda si paga il mattino dopo: se la FC a riposo è alta e ieri faceva caldo, è quello.", x:"heat", y:"rhr", lag:1, mode:"lv", tag:"·",
    t:"Il caldo si paga il mattino dopo", s:"caldo → FC riposo",
    why:"Fra tutte le cose che potrebbero muovere il recupero — carico, sonno, cibo — "+
      "l'unica che si vede davvero è il <b>caldo</b>. Un'uscita calda alza la frequenza "+
      "a riposo del giorno dopo, e regge anche sulle variazioni settimanali. È debole, "+
      "ma è l'unico segnale non nullo di tutta questa sezione." },
  { k:"passi-salita", doit:"Un giorno da pochi passi e tanto dislivello è un buon giorno. Il numero rosso sull'orologio, lì, non vuol dire niente.", x:"steps", y:"gain", lag:0, mode:"lv", tag:"·",
    t:"I passi non contano lo sport: lo sostituiscono", s:"passi → salita",
    why:"Più dislivello, <b>meno</b> passi — e non è un errore dell'orologio. Le giornate "+
      "grosse sono giornate in bici, e in bici i passi non si fanno. Il contatore misura "+
      "quanto ci si è mossi <em>fuori</em> dall'allenamento: leggerlo come «quanto sono "+
      "stato attivo oggi» lo legge al contrario." },
  { k:"hrv-rhr", x:"hrv", y:"rhr", lag:0, mode:"lv", tag:"zero",
    t:"Le due misure del recupero non si parlano", s:"HRV → FC riposo",
    why:"HRV e frequenza a riposo sono le due metriche che ogni orologio vende come "+
      "«recupero», e qui, sulla stessa persona e sullo stesso mattino, sono <b>scorrelate "+
      "a zero</b>. Non è che una sia sbagliata: misurano cose diverse, e usarle come se "+
      "fossero la stessa cosa è il modo più comune di sbagliarsi." },
  { k:"carico-hrv", doit:"Per sapere quanto è costata ieri, guardare ieri. Il cuore di stamattina non lo sa.", x:"load", y:"hrv", lag:1, mode:"lv", tag:"zero",
    t:"Il carico di ieri non arriva all'HRV di stamattina", s:"carico → HRV",
    why:"È la promessa implicita di ogni dashboard: alleni forte, l'HRV scende, il giorno "+
      "dopo lo sai. Su cinquecento mattine <b>non succede</b>. Se serve sapere quanto è "+
      "costata ieri, la risposta sta nel carico stesso, non nel cuore di stamattina." },
  { k:"sonno-hrv", x:"sleep", y:"hrv", lag:0, mode:"lv", tag:"zero",
    t:"Dormire di più non alza l'HRV di quella notte", s:"sonno → HRV",
    why:"Nemmeno la notte in cui si è dormito bene sposta la variabilità del mattino. "+
      "Vale la pena dirlo perché la direzione opposta — «HRV bassa? dormi di più» — è "+
      "consigliata ovunque, e qui dentro non ha nessun appiglio." },
  { k:"carbgap", x:"load", y:"carbgap", lag:0, mode:"lv", tag:"·",
    t:"Più alleni, più ti mancano i carboidrati", s:"carico → carboidrati",
    why:"Lo scarto è <b>ingeriti meno il fabbisogno</b>: negativo vuol dire sotto. E scende "+
      "proprio quando il carico sale — il fabbisogno cresce con i TSS e l'alimentazione non "+
      "lo insegue. È l'associazione più forte di tutta la tavola che non sia cablaggio, e "+
      "l'unica di questa lista su cui si possa fare qualcosa domani." },
  { k:"caldo-ef", doit:"", x:"temp", y:"ef", lag:0, mode:"lv", tag:"zero",
    t:"Il caldo non tocca il rapporto fra passo e battito", s:"caldo → efficienza",
    why:"Il costo del caldo non finisce qui: quando fa caldo si <b>rallenta</b>, e "+
      "rallentando la frequenza torna dov'era. Il caldo sposta il passo che si sceglie; "+
      "il prezzo in battiti di quel passo resta lo stesso. Da tenere accanto alla riga "+
      "qui sopra: il conto del caldo arriva il mattino dopo." },
  { k:"cibo-domani", doit:"", x:"kcal", y:"hours", lag:1, mode:"d7", tag:"zero",
    t:"Mangiare oggi non compra l'allenamento di domani", s:"cibo → ore",
    why:"Sulle variazioni settimanali il segno è perfino leggermente <b>negativo</b>: le "+
      "settimane in cui si è mangiato di più non sono quelle in cui si è allenato di più "+
      "il giorno dopo. Il verso della freccia è l'altro — è l'allenamento che tira il "+
      "cibo, e si vede scegliendo «stesso giorno»." },
  { k:"ef-grassi", x:"ef", y:"fatrate", lag:0, mode:"lv", tag:"cablaggio",
    t:"Efficienza e grammi di grasso: quanto è modello", s:"efficienza → grassi",
    why:"Le due serie della sezione Metabolismo si muovono insieme, ma <b>metà di questo "+
      "è cablaggio</b>: nascono dalle stesse uscite, una dal passo e una dall'istogramma "+
      "della frequenza. È qui apposta come promemoria — un r alto fra due numeri che "+
      "condividono la sorgente vale come controllo di coerenza." },
  { k:"peso-hrv", x:"weight", y:"hrv", lag:0, mode:"lv", tag:"poco n",
    t:"Il peso e l'HRV, su sessantacinque pesate", s:"peso → HRV",
    why:"L'unica associazione visibile che tocchi il peso, ed è <b>inversa</b>: mattine "+
      "con HRV più alta dove il peso è più basso. Sessantacinque punti in undici anni "+
      "sono pochissimi e il verso della causa qui non si può nemmeno ipotizzare — sta in "+
      "lista come cosa da riguardare fra un anno di pesate, non come conclusione." },
];
const cxHostP = document.getElementById("compare-presets");
const cxClaim = document.getElementById("compare-claim");
/* I due slot liberi: quello che Michele sta guardando diventa una pastiglia sua, e
   resta li' alla visita dopo. Due e non venti — una barra di pastiglie lunga il
   doppio della pagina non e' una scorciatoia, e' un secondo menu. */
const CX_MAX_MINE = 2;
const cxMine = (() => {
  try { const v = JSON.parse(store.get("vita:cxmine", "[]")); return Array.isArray(v) ? v.slice(0, CX_MAX_MINE) : []; }
  catch (e) { return []; }
})();
const cxSaveMine = () => store.set("vita:cxmine", JSON.stringify(cxMine));
let cxActive = null;

function cxApply(p){
  if(!compareByKey.has(p.x) || !compareByKey.has(p.y)) return false;
  compareX.value=p.x; compareY.value=p.y;
  compareLag.value=String(p.lag||0); compareMode.value=p.mode||"lv";
  cxActive=p.k; drawCompare(); cxPaint(); return true;
}
/* Quante pastiglie restano a schermo. Tre e non dieci: la barra era la prima cosa
   che si vedeva della sezione, e dieci tesi in fila non si leggono — si saltano.
   Le altre sette stanno dietro «altre 7», e il gruppo si apre da solo se quella
   attiva e' fra loro (arrivarci da un ⓘ o da un preferito e non vedersela accesa
   sarebbe peggio di non nasconderle affatto). */
const CX_SHOW = 3;
let cxOpen = false;

function cxPaint(){
  cxHostP.innerHTML="";
  const chip=(p,mine,hid)=>{
    /* LA PASTIGLIA PORTA LA COPPIA, NON LA TESI (18/08/2026: «i bottoni in incroci
       stacked one on top, si puo' fare di meglio, mobile first»). Una tesi lunga
       trentadue caratteri su uno schermo da 360 px e' larga quanto la riga: tre
       pastiglie diventavano tre righe impilate. «caldo → FC riposo» sta in mezza riga,
       e la tesi per esteso non si perde — e' la frase sotto, che cambia col tocco.
       Le tue restano col nome che gli hai dato tu. */
    const b=mk("button",[mine?"cx-own":null,hid?"cx-hid":null].filter(Boolean).join(" ")||null,cxHostP,p.s||p.t);
    b.setAttribute("type","button");
    b.setAttribute("aria-label",p.t);   /* niente title=: dal telefono non esiste */
    /* l'etichetta dice che RAZZA di risultato e', prima ancora di aprirlo: uno
       zero, un cablaggio e un campione piccolo si guardano in tre modi diversi */
    if(!mine&&p.tag&&p.tag!=="·") mk("i",null,b,p.tag);
    b.setAttribute("aria-pressed",cxActive===p.k?"true":"false");
    b.addEventListener("click",()=>cxApply(p));
    if(mine){
      const x=mk("i",null,b,"×");
      x.addEventListener("click",ev=>{ if(ev.stopPropagation) ev.stopPropagation();
        const j=cxMine.indexOf(p); if(j>=0) cxMine.splice(j,1); cxSaveMine(); cxPaint(); });
    }
    return b;
  };
  const live=CX_PRESETS.filter(p=>compareByKey.has(p.x)&&compareByKey.has(p.y));
  const hidden=live.slice(CX_SHOW);
  /* se quella accesa sta fra le nascoste, il gruppo si apre: una pastiglia premuta
     e invisibile e' un comando che dice il contrario di quello che sta facendo */
  if(hidden.some(p=>p.k===cxActive)) cxOpen=true;
  live.forEach((p,i)=>chip(p,false,i>=CX_SHOW));
  for(const p of cxMine) chip(p,true,false);
  if(hidden.length){
    const tog=mk("button","cx-tog",cxHostP,cxOpen?"− meno":`+ altre ${hidden.length}`);
    tog.setAttribute("type","button");
    tog.setAttribute("aria-pressed",cxOpen?"true":"false");
    tog.setAttribute("aria-controls","compare-presets");
    tog.addEventListener("click",()=>{ cxOpen=!cxOpen; cxPaint(); });
  }
  cxHostP.setAttribute("data-open",cxOpen?"1":"0");
  if(cxMine.length<CX_MAX_MINE){
    const add=mk("button","cx-add",cxHostP,"+ questa è mia");
    add.setAttribute("type","button");
    add.setAttribute("aria-pressed","false");
    add.addEventListener("click",()=>{
      const sx=compareByKey.get(compareX.value), sy=compareByKey.get(compareY.value);
      if(!sx||!sy) return;
      const lag=Number(compareLag.value)||0;
      /* il tetto si impone QUI e non solo nascondendo il bottone: il bottone puo'
         restare in mano a qualcuno (un vecchio riferimento, un doppio click) e due
         slot che diventano cinque sono una barra che non sta piu' su una riga */
      if(cxMine.length>=CX_MAX_MINE) return;
      cxMine.push({ k:"mia:"+sx[0]+">"+sy[0]+":"+lag+":"+compareMode.value,
        x:sx[0], y:sy[0], lag, mode:compareMode.value,
        t:sx[2]+" → "+sy[2]+(lag?" (domani)":""),
        s:sx[2]+" → "+sy[2], why:"" });
      cxSaveMine(); cxActive=cxMine[cxMine.length-1].k; cxPaint();
    });
  }
  const p=[...CX_PRESETS,...cxMine].find(q=>q.k===cxActive);
  /* A schermo la tesi e la PRIMA frase del perche', non tutte e tre-quattro: erano 321
     caratteri centrati che si riscrivevano a ogni pastiglia toccata, e sul telefono
     spingevano il grafico sotto la piega proprio mentre lo si stava scegliendo. Il resto
     entra nell'ⓘ, registrato qui accanto — un elenco solo, non due. */
  if (p && p.why) {
    const primo = (p.why.match(/^[^.]*\./) || [p.why])[0];
    const resto = p.why.slice(primo.length).trim();
    infoReg("cross:" + p.k, p.t, `<p>${p.why}</p>`);
    cxClaim.innerHTML = `<b>${p.t}.</b> ${primo}` +
      (resto ? ico("cross:" + p.k, p.t) : "");
  } else cxClaim.innerHTML = "";
}
/* cambiare una tendina a mano scioglie la pastiglia: quello che si guarda non e'
   piu' quello che la frase raccontava, e lasciare la frase li' sarebbe una bugia */
[compareX,compareY,compareLag,compareMode].forEach(x=>x.addEventListener("change",()=>{
  cxActive=null; cxPaint(); drawCompare();
}));
cxPaint();
if(!cxApply(CX_PRESETS[0])) drawCompare();
window.CRUSCOTTO.compare={series:compareSeries,draw:drawCompare,x:compareX,y:compareY,
  lag:compareLag,mode:compareMode,pearson,pairsFor,byKey:compareByKey,
  presets:CX_PRESETS,apply:cxApply,mine:cxMine,paint:cxPaint,claim:cxClaim,host:cxHostP};

/* ====================================================== l'opinione del coach
   Un rapporto solo che mette insieme le tre cose che la pagina misura — la tavola,
   il motore, la gamba — e dice cosa se ne ricava. Tre regole che lo tengono onesto:

     · **ogni numero e' calcolato qui, adesso.** Nessuna cifra scritta a mano nel
       testo: le medie a 14 giorni, gli r, gli n escono dagli stessi array che
       disegnano i grafici. Se domani il dato cambia, cambia la frase. Un rapporto
       con dentro un numero congelato invecchia senza dirlo, ed e' peggio di non
       averlo;
     · **le associazioni portano il loro n e il loro r**, anche quando sono zero.
       Gli zeri sono meta' di quello che c'e' da sapere qui dentro;
     · **cosa e' osservato e cosa e' ricostruito resta scritto.** Il rapporto parla
       di calorie che per meta' sono un modello, e non puo' fingere di no.

   Non e' un referto. Non c'e' nessun medico dietro, e le raccomandazioni sono
   quelle che si darebbe un allenatore guardando questi numeri, cioe' discutibili. */
const coachBtn = document.getElementById("coach-btn");
const coachLead = document.getElementById("coach-lead");
const coachSheet = document.getElementById("coach");
const coachIn = document.getElementById("coach-in");
/* variazione percentuale fra due medie: la usano sia i dati sia il testo */
const coachPc = (a, b) => (a == null || b == null || !b) ? null : 100 * (a - b) / Math.abs(b);

/* Radar corto, con un'ipotesi dichiarata prima di guardare i risultati: FC a
   riposo contro ogni altra misura. Quattro medie settimanali darebbero n=4 e r
   quasi arbitrari; usiamo invece la media mobile a 7 giorni dentro due finestre
   consecutive di 28 giorni. Le finestre sovrapposte autocorrelano i punti, quindi
   n non viene spacciato per 28 osservazioni indipendenti: il segnale entra nel
   diario solo se conserva il segno togliendo a turno ciascuna delle quattro
   settimane. E' uno screening esplorativo, non un test causale. */
const coachRoll7 = arr => {
  const out=new Array(N).fill(null);
  for(let i=6;i<N;i++){
    const v=[]; for(let j=i-6;j<=i;j++) if(arr&&arr[j]!=null&&isFinite(arr[j])) v.push(arr[j]);
    if(v.length>=4) out[i]=v.reduce((s,x)=>s+x,0)/v.length;
  }
  return out;
};
const coachCorrWindow = (a,b,lo,hi,skipWeek=-1) => {
  const pts=[];
  for(let i=Math.max(0,lo);i<=Math.min(N-1,hi);i++){
    if(skipWeek>=0 && Math.floor((i-lo)/7)===skipWeek) continue;
    if(a[i]!=null&&b[i]!=null&&isFinite(a[i])&&isFinite(b[i])) pts.push([a[i],b[i]]);
  }
  return {r:pearson(pts),n:pts.length};
};
function coachRhrRadar(observedFoodPct){
  if(!compareByKey.has("rhr") || N<56) return [];
  const anchor=coachRoll7(compareByKey.get("rhr")[3]), recentLo=N-28, recentHi=N-1;
  const priorLo=N-56, priorHi=N-29, out=[];
  for(const s of compareSeries){
    if(s[0]==="rhr" || (s[1]==="Tavola" && !(observedFoodPct>=70))) continue;
    const y=coachRoll7(s[3]);
    const now=coachCorrWindow(anchor,y,recentLo,recentHi);
    const before=coachCorrWindow(anchor,y,priorLo,priorHi);
    if(now.n<18 || before.n<18 || now.r==null || before.r==null) continue;
    const signs=[];
    for(let w=0;w<4;w++){
      const z=coachCorrWindow(anchor,y,recentLo,recentHi,w).r;
      if(z!=null && Math.abs(z)>=.15) signs.push(Math.sign(z)===Math.sign(now.r));
    }
    const stable=signs.filter(Boolean).length, delta=now.r-before.r;
    if(stable<3 || Math.abs(now.r)<.45) continue;
    out.push({key:s[0],name:s[2],section:s[1],r:now.r,prior:before.r,delta,
      n:now.n,priorN:before.n,stable,score:Math.abs(now.r)+Math.min(1,Math.abs(delta))*.45});
  }
  return out.sort((a,b)=>b.score-a.score).slice(0,3);
}

function coachData(){
  const F = D.nutri || {}, M = D.metab || {};
  const vals = a => (a || []).filter(v => v != null && isFinite(v)).sort((a,b) => a-b);
  const median = a => { const v=vals(a), n=v.length; return n ? (n%2 ? v[(n-1)/2] : (v[n/2-1]+v[n/2])/2) : null; };
  const robustZ = (v, a) => {
    const med=median(a); if(v==null || med==null) return null;
    const mad=median(vals(a).map(x=>Math.abs(x-med)));
    return mad ? .6745*(v-med)/mad : null;
  };
  const sumAligned = (a, b, lo, hi) => {
    let x=0, y=0, n=0;
    for(let i=Math.max(0,lo);i<=Math.min(N-1,hi);i++) if((b||[])[i]!=null && isFinite(b[i])) {
      x += ((a||[])[i]!=null && isFinite(a[i])) ? a[i] : 0; y += b[i]; n++;
    }
    return {x,y,n};
  };
  const mean = (a, lo, hi) => { const s = stats((a || []).slice(Math.max(0, lo), hi + 1));
    return s ? s.mean : null; };
  const m14 = a => mean(a, N - 14, N - 1), m28 = a => mean(a, N - 28, N - 15);
  const mins = new Array(N).fill(0);
  const tss = new Array(N).fill(0);
  D.acts.forEach(a => { if (a[0] >= 0 && a[0] < N) { mins[a[0]] += (a[2] || 0) / 60; tss[a[0]] += a[5] || 0; } });
  const obs = m14(F.kcal_observed), kcal = m14(F.kcal);
  const cov14=sumAligned(F.kcal_observed,F.kcal,N-14,N-1);
  const covAll=sumAligned(F.kcal_observed,F.kcal,0,N-1);
  const load7=tss.slice(Math.max(0,N-7)), load28=tss.slice(Math.max(0,N-35),Math.max(0,N-7));
  const sum=a=>a.reduce((s,v)=>s+(v||0),0), avg=a=>a.length?sum(a)/a.length:null;
  const sd=a=>{const m=avg(a);return m==null?null:Math.sqrt(avg(a.map(v=>(v-m)*(v-m))));};
  const latestWellness=(()=>{for(let i=N-1;i>=Math.max(0,N-3);i--){
    const n=[D.sleep[i],D.hrv[i],D.rhr[i]].filter(v=>v!=null&&isFinite(v)).length;
    if(n>=2)return i;
  } return null;})();
  const baseLo=latestWellness==null?0:Math.max(0,latestWellness-42), baseHi=latestWellness==null?0:latestWellness-1;
  const rz=(a,i)=>i==null?null:robustZ(a[i],a.slice(baseLo,baseHi+1));
  const foodPct=cov14.y ? 100*cov14.x/cov14.y : null;
  return {
    ctl:D.ctl[N - 1], atl:D.atl[N - 1],
    forma:(D.ctl[N - 1] == null || D.atl[N - 1] == null) ? null : D.ctl[N - 1] - D.atl[N - 1],
    ore14:m14(mins), ore28:m28(mins),
    half:halfRoll[N - 1], climb:climbRoll[N - 1],
    kcal, kcal28:m28(F.kcal), prot:m14(F.protein_g), fib:m14(F.fiber_g),
    carb:m14(F.carb_g), gap:m14(F.carb_gap_g), gapAll:mean(F.carb_gap_g, 0, N - 1),
    sug:m14(F.sugar_g), upf:m14(F.pct_upf), plant:m14(F.pct_plant),
    oss:foodPct, obsDays:cov14.n,
    sonno:m14(D.sleep), hrv:m14(D.hrv), rhr:m14(D.rhr), passi:m14(D.steps),
    fat:fatRate ? lastMean(fatRate, 45) : null,
    ef:aero ? lastMean(aero.day, 45) : null,
    fatmaxHr:M.fatmax_hr ? M.fatmax_hr[N - 1] : null,
    fatmaxMin:mean(M.fatmax_min, N - 90, N - 1),
    load7:sum(load7), load7eq:load28.length ? sum(load28)/load28.length*7 : null,
    ramp:load28.length && sum(load28) ? 100*(sum(load7)-sum(load28)/load28.length*7)/(sum(load28)/load28.length*7) : null,
    monotony:(load7.length>=6 && sd(load7)) ? avg(load7)/sd(load7) : null,
    wellnessDay:latestWellness,
    sleepNow:latestWellness==null?null:D.sleep[latestWellness],
    hrvNow:latestWellness==null?null:D.hrv[latestWellness],
    rhrNow:latestWellness==null?null:D.rhr[latestWellness],
    zSleep:rz(D.sleep,latestWellness), zHrv:rz(D.hrv,latestWellness), zRhr:rz(D.rhr,latestWellness),
    sleepBase:latestWellness==null?null:median(D.sleep.slice(baseLo,baseHi+1)),
    /* Somme sugli stessi giorni: il precedente rapporto divideva due medie con
       calendari non allineati e poteva alterare la quota osservata. */
    ossTot:covAll.y ? 100*covAll.x/covAll.y : null, ossTotDays:covAll.n,
    rhrRadar:coachRhrRadar(foodPct),
  };
}

function coachInsights(c){
  const n0=v=>v==null?"—":nf(v,0), n1=v=>v==null?"—":nf(v,1);
  const out=[];
  const zs=[c.zSleep==null?null:-c.zSleep,c.zHrv==null?null:-c.zHrv,c.zRhr]
    .filter(v=>v!=null&&isFinite(v));
  const bad=zs.filter(v=>v>=1).length, good=zs.filter(v=>v<=-1).length;
  const discordant=bad>0&&good>0;
  if(zs.length>=2 && (bad>0 || good>0)) out.push({priority:discordant?100:95,cls:bad>=2?"hot":"",
    h:discordant?"Il recupero è discordante":"I segnali di recupero si muovono insieme",
    p:discordant
      ? "Un indicatore rassicura e almeno uno segnala costo: <b>la sola HRV non è un via libera</b>."
      : bad>=2 ? "Almeno due segnali personali sono peggiori del consueto: il dato è più credibile del singolo numero."
      : "Almeno due segnali personali sono migliori del consueto: il recupero è coerente, non affidato a una sola metrica.",
    num:`sonno ${c.sleepNow==null?"—":hhmm(c.sleepNow)} (z ${n1(c.zSleep)}) · HRV ${n0(c.hrvNow)} (z ${n1(c.zHrv)}) · FC ${n0(c.rhrNow)} (z ${n1(c.zRhr)})`,
    doit:bad>0?"Oggi decidi l'intensità sul segnale peggiore, non sulla media.":"Il recupero consente il piano previsto; non aggiungere volume solo perché i numeri sono buoni."});
  if(c.ramp!=null && (Math.abs(c.ramp)>=15 || (c.monotony!=null&&c.monotony>=2))) out.push({
    priority:Math.abs(c.ramp)+(c.monotony||0)*10,cls:c.ramp>25||c.monotony>=2?"hot":"",
    h:c.monotony>=2?"Il carico è alto e poco variato":"Il carico ha cambiato marcia",
    p:c.monotony>=2
      ? "A parità di TSS, sette giorni simili lasciano meno spazio di recupero di una settimana alternata."
      : `<b>Gli ultimi 7 giorni sono ${c.ramp>=0?"sopra":"sotto"}</b> il ritmo delle quattro settimane precedenti.`,
    num:`7 gg <b>${n0(c.load7)} TSS</b> · equivalente precedente ${n0(c.load7eq)} · ${c.ramp>=0?"+":""}${n0(c.ramp)} % · monotonia ${n1(c.monotony)}`,
    doit:c.ramp>15||c.monotony>=2?"La prossima seduta deve creare contrasto: facile o riposo, non un altro giorno medio.":"Mantieni il carico; non compensare il calo in una sola seduta."});
  /* Il gap glucidico include una ricostruzione: diventa insight soltanto quando almeno
     il 70% dell'energia recente è osservato. Sotto soglia è provenance, non fisiologia. */
  if(c.oss>=70 && c.gap!=null && Math.abs(c.gap)>=30) out.push({priority:70+Math.min(20,Math.abs(c.gap)/10),cls:c.gap<0?"hot":"",
    h:c.gap<0?"Il carburante non segue il carico":"I carboidrati coprono il carico",
    p:c.gap<0?"Sui giorni abbastanza osservati, l'apporto resta sotto il fabbisogno stimato.":"La disponibilità glucidica recente è compatibile con il fabbisogno stimato.",
    num:`scarto 14 gg <b>${n0(c.gap)} g/g</b> · copertura osservata ${n0(c.oss)} %`,
    doit:c.gap<0?"Metti la quota mancante nel pasto prima o dopo la seduta più lunga.":"Non aumentare i carboidrati per inerzia: mantienili attorno alle sedute chiave."});
  const rc=(c.rhrRadar||[])[0];
  if(rc) out.push({priority:82+Math.abs(rc.delta)*20,cls:"",
    h:`FC a riposo: il legame corto più netto è con ${rc.name}`,
    p:`Sulle medie mobili a 7 giorni il segnale recente è <b>${rc.r<0?"inverso":"diretto"}</b> e ${Math.abs(rc.delta)>=.25?"diverso":"simile"} dal mese precedente.`,
    num:`ultime 4 sett. r ${nf(rc.r,2)} · 4 sett. prima ${nf(rc.prior,2)} · Δ ${rc.delta>=0?"+":""}${nf(rc.delta,2)} · stabile ${rc.stable}/4`,
    doit:Math.abs(rc.delta)>=.25
      ? `Osserva ${rc.name.toLowerCase()} insieme alla FC a riposo per un'altra settimana: il cambio di regime vale più del singolo mattino.`
      : `Usa ${rc.name.toLowerCase()} come contesto della FC a riposo, non come causa né soglia automatica.`});
  return out.sort((a,b)=>b.priority-a.priority).slice(0,3);
}

function coachHtml(){
  const c = coachData();
  const n1 = v => v == null ? "—" : nf(v, 1), n0 = v => v == null ? "—" : nf(v, 0);
  const rr = f => f ? `r ${nf(f.r, 2)} · n ${nf(f.n)}` : "dati insufficienti";
  const dOre = c.ore14 != null && c.ore28 ? (c.ore14 - c.ore28) / 60 : null;
  const item = (cls, h, p, num, doit) =>
    `<div class="cr-item ${cls}"><h5>${h}</h5><p>${p}` +
    (num ? `<span class="cr-num">${num}</span>` : "") +
    (doit ? `<span class="cr-do">${doit}</span>` : "") + `</p></div>`;

  /* Il diario ufficiale non e' un saggio: massimo tre segnali, ordinati per
     decision value. Tutto il resto resta nei grafici e nei metadati. */
  const insights=coachInsights(c);
  const top=insights[0];
  return `<button class="sheet-x" type="button" aria-label="Chiudi" onclick="closeCoach()">×</button>
<div class="cr-when">${fmtDate(N-1)} · aggiornamento automatico</div>
<h3 id="coach-t">L'opinione del coach</h3>
${top?`<p class="cr-verdict"><b>${top.h}.</b> ${top.doit}</p>`:`<p class="cr-verdict">Nessun segnale recente supera la soglia decisionale.</p>`}
<div class="cr-sec">${insights.map(x=>item(x.cls,x.h,x.p,x.num,x.doit)).join("")}</div>
<div class="cr-limits"><p><b>Provenienza</b> · alimentazione 14 gg ${c.oss==null?"—":n0(c.oss)+" % osservata"} · archivio ${c.ossTot==null?"—":n0(c.ossTot)+" % osservato"} (${n0(c.ossTotDays)} giorni allineati) · resto ricostruito. Grassi/min: modello ±40 %. Carico 2022: stimato. Radar FC: medie mobili 7 gg, ultime 4 settimane vs 4 precedenti, stabilità togliendo una settimana alla volta; esplorativo, non causale.</p></div>`;
}

function openCoach(){
  coachIn.innerHTML = coachHtml();
  coachSheet.classList.add("on");
  document.body.style.overflow = "hidden";
}
function closeCoach(){
  coachSheet.classList.remove("on");
  document.body.style.overflow = "";
}
window.openCoach = openCoach; window.closeCoach = closeCoach;
coachBtn.addEventListener("click", openCoach);
coachSheet.addEventListener("click", ev => { if (ev.target === coachSheet) closeCoach(); });
/* la riga in cima alla pagina e' il verdetto del rapporto, non un invito a leggerlo:
   se uno non apre niente, quella riga da sola deve gia' valere la visita */
(function coachLeadLine(){
  const c = coachData();
  const top=coachInsights(c)[0];
  coachLead.innerHTML=top ? `<b>${top.h}.</b> ${top.doit}` :
    "Nessun segnale recente supera la soglia decisionale.";
})();
window.CRUSCOTTO.coach = { data:coachData, html:coachHtml, open:openCoach, close:closeCoach };

/* ---------------------------------------------- le altre pagine, in fondo
   Erano in cima, a piena larghezza: su un telefono quattro schede da ~171px fanno
   750px fra il bottone del diario e i comandi — cioe' esattamente dove uno si aspetta
   il primo disegno, occupati da link che portano FUORI da /vita. Ora stanno accanto a
   `nav.also`, che fa gia' quel mestiere. Via anche i blurb: 377 caratteri che nessuno
   legge scorrendo, e il titolo coi tre numeri dice gia' cosa c'e' dall'altra parte. */
document.getElementById("tracks").innerHTML = (D.tracks || []).map(t => `
  <a class="track" href="${t.href}" style="--a:${t.accent}">
    <div class="k">${t.eyebrow}</div>
    <h3>${t.title}</h3>
    <div class="nums">${t.stats.map(s =>
      `<div><b>${s.v}</b><span>${s.l}</span></div>`).join("")}</div>
  </a>`).join("");

/* ------------------------------------------------------------- headline */
(function totals() {
  const F=D.nutri||{}, mean=(a,lo,hi)=>{const s=stats((a||[]).slice(Math.max(0,lo),hi+1));return s?s.mean:null;};
  /* Il cibo può correre avanti all'orologio. Se negli ultimi 14 giorni di calendario
     ci sono meno di sette misure wellness, la testata usa i 14 giorni che finiscono
     sull'ultima misura reale; non fa sparire sonno/HRV/FC solo perché il diario è più
     fresco. Allenamento e tavola restano invece ancorati a oggi. */
  const window14=(arr,anchorLast)=>{
    let hi=N-1;
    if(anchorLast){
      const recent=(arr||[]).slice(Math.max(0,N-14),N).filter(v=>v!=null&&isFinite(v));
      if(recent.length<7) for(let i=N-1;i>=0;i--) if(arr&&arr[i]!=null&&isFinite(arr[i])){hi=i;break;}
    }
    return {now:mean(arr,hi-13,hi),prior:mean(arr,hi-27,hi-14),hi};
  };
  const delta=(a,b)=>a==null||b==null||b===0?null:100*(a-b)/Math.abs(b);
  const fd=d=>d==null?"—":`${d>=0?"+":""}${nf(d,0)}%`;
  const km=new Array(N).fill(0), mins=new Array(N).fill(0), tss=new Array(N).fill(0);
  D.acts.forEach(a=>{if(a[0]>=0&&a[0]<N){mins[a[0]]+=(a[2]||0)/60;km[a[0]]+=(a[3]||0)/1000;tss[a[0]]+=a[5]||0;}});
  const defs=[["sonno",D.sleep,hhmm,0,0,1],["HRV",D.hrv,v=>nf(v,0)+" ms",0,0,1],
    ["FC riposo",D.rhr,v=>nf(v,0)+" bpm",1,0,1],["passi",D.steps,v=>nf(v,0),0,0,1],
    ["allenamento",mins,v=>nf(v,0)+" min/g",0,0],["chilometri",km,v=>nf(v,1)+" km/g",0,0],
    ["carico",tss,v=>nf(v,0)+" TSS/g",0,0],["kcal",F.kcal,v=>nf(v,0),0,1],
    ["proteine",F.protein_g,v=>nf(v,0)+" g",0,1],["carboidrati",F.carb_g,v=>nf(v,0)+" g",0,1],
    ["fibre",F.fiber_g,v=>nf(v,1)+" g",0,1],["vegetale",F.pct_plant,v=>nf(v,0)+"%",0,1]];
  const items=defs.map(([label,arr,fmt,invert,food,anchorLast])=>{const w=window14(arr,anchorLast);return{label,arr,now:w.now,prior:w.prior,d:delta(w.now,w.prior),fmt,invert,food,through:w.hi};}).filter(x=>x.now!=null);
  const render=xs=>xs.map(x=>{const good=x.d!=null&&(x.invert?x.d<0:x.d>0),tag=x.food?"button":"div";return `<${tag} class="total" ${x.food?`type="button" data-food="${x.label}"`:''}><div class="n">${x.fmt(x.now)}</div><div class="l">${x.label}</div><div class="d ${x.d==null||x.neutro?'':good?'up':'down'}">${fd(x.d)} vs prima</div></${tag}>`;}).join("");
  document.getElementById("totals-recovery").innerHTML=render(items.filter(x=>!x.food));
  document.getElementById("totals-food").innerHTML=render(items.filter(x=>x.food));

  /* ---- IL CORPO, IN CIMA (ordine #22) --------------------------------------
     Peso e massa grassa non si misurano come il resto di questa pagina: non li
     scrive un orologio ogni notte, li scrive una bilancia quando ci si sale. In
     undici anni sono sessantacinque pesate, e l'ultima puo' essere di un mese fa —
     quindi una media sugli ultimi quattordici giorni qui sarebbe vuota quasi
     sempre, e il gruppo non comparirebbe mai.
     Percio' il numero e' l'ULTIMA MISURA e lo scarto e' sulla pesata precedente,
     con la data scritta nell'etichetta del gruppo: cosi' nessuno legge un peso di
     cinque settimane fa credendolo di stanotte. La massa magra e' derivata dalle
     due misure dello stesso giorno, non da un'altra fonte. */
  (function corpo(){
    const ultima=arr=>{for(let i=N-1;i>=0;i--){const v=arr&&arr[i];if(v!=null&&isFinite(v))return{i,v};}return null;};
    const prima=(arr,pre)=>{for(let i=pre-1;i>=0;i--){const v=arr&&arr[i];if(v!=null&&isFinite(v))return{i,v};}return null;};
    const magra=(D.weight||[]).map((w,i)=>{const f=(D.bodyfat||[])[i];
      return w!=null&&f!=null&&isFinite(w)&&isFinite(f)?w*(1-f/100):null;});
    const defsC=[["peso",D.weight,v=>nf(v,1)+" kg"],["massa grassa",D.bodyfat,v=>nf(v,1)+"%"],
      ["massa magra",magra,v=>nf(v,1)+" kg"]];
    const xs=defsC.map(([label,arr,fmt])=>{const u=ultima(arr);if(!u)return null;
      const p=prima(arr,u.i);
      return{label,now:u.v,d:p?delta(u.v,p.v):null,fmt,neutro:1,i:u.i};}).filter(Boolean);
    if(!xs.length)return;
    const box=document.getElementById("totals-body");if(!box)return;
    box.innerHTML=render(xs);
    const grp=document.getElementById("grp-body");
    if(grp&&grp.removeAttribute)grp.removeAttribute("hidden");
    const lab=document.getElementById("headline-body-label");
    const q=Math.max(...xs.map(x=>x.i));
    if(lab)lab.textContent="Corpo · ultima misura "+
      new Date(D0.getTime()+q*DAY).toLocaleDateString("it-IT",{day:"numeric",month:"short",year:"numeric"});
  })();
  function insights(wanted){
    const extra=[["zuccheri",F.sugar_g,v=>nf(v,0)+" g"],["magnesio",F.magnesium_mg,v=>nf(v,0)+" mg"],
      ["potassio",F.potassium_mg,v=>nf(v,0)+" mg"],["sodio",F.sodium_mg,v=>nf(v,0)+" mg"],
      ["indice vitamine",F.vit_index,v=>nf(v,0)+"%"],["indice minerali",F.min_index,v=>nf(v,0)+"%"],
      ["piante / 7 giorni",F.plants_7d,v=>nf(v,1)],["indice microbiota",F.microbiome,v=>nf(v,0)+"/100"]];
    const all=items.filter(x=>x.food).concat(extra.map(([label,arr,fmt])=>{const now=mean(arr,N-14,N-1),prior=mean(arr,N-28,N-15);return{label,arr,now,prior,d:delta(now,prior),fmt,food:1};}).filter(x=>x.now!=null));
    const observed=mean(F.kcal_observed,N-14,N-1), total=mean(F.kcal,N-14,N-1);
    if(observed!=null&&total){const arr=(F.kcal||[]).map((v,i)=>v&&F.kcal_observed?100*(F.kcal_observed[i]||0)/v:null);all.push({label:"quota osservata",arr,now:100*observed/total,prior:null,d:null,fmt:v=>nf(v,0)+"%",food:1});}
    const P=D.foodProfile||{},rda=P.rda||{},limits=P.limits||{};
    const targetByLabel={
      "kcal":P.reference_kcal,
      "proteine":P.weight_kg&&P.protein_g_per_kg?P.weight_kg*P.protein_g_per_kg:null,
      "carboidrati":mean(F.carb_target_g,N-14,N-1),
      "fibre":rda.fiber_g,
      "zuccheri":P.reference_kcal&&limits.sugar_pct_kcal?P.reference_kcal*limits.sugar_pct_kcal/400:null,
      "magnesio":rda.magnesium_mg,"potassio":rda.potassium_mg,"sodio":limits.sodium_mg,
      "indice vitamine":100,"indice minerali":100,"piante / 7 giorni":30,
      "indice microbiota":100,"quota osservata":100
    };
    const ceiling=new Set(["zuccheri","sodio"]);
    all.forEach(x=>{x.target=Number.isFinite(targetByLabel[x.label])?targetByLabel[x.label]:null;x.ceiling=ceiling.has(x.label);});
    const selected=all.find(x=>x.label===wanted)||all[0];
    const line=x=>{
      const scale=x.target==null?100:Math.max(x.target*1.25,x.now||0.01),
        fill=Math.max(0,Math.min(100,100*x.now/scale)),
        marker=x.target==null?null:Math.max(0,Math.min(100,100*x.target/scale)),
        ratio=x.target?x.now/x.target:null,
        col=x.target==null?'var(--s1)':x.ceiling?(ratio<=1?'var(--s3)':'var(--neg)'):
          (ratio>=1?'var(--s3)':ratio>=.8?'var(--s1)':'var(--accent)'),
        target=x.target==null?'nessun target definito':`${x.ceiling?'limite':'target'} ${x.fmt(x.target)} · ${nf(100*ratio,0)}%`;
      return `<div class="bar ${x===selected?'sel':''}"><u>${x.label}</u><b>${x.fmt(x.now)} · ${fd(x.d)}</b>`+
        `<div class="target-track"><i style="width:${fill}%;background:${col}"></i>${marker==null?'':`<mark style="left:${marker}%" title="${target}"></mark>`}</div><small>${target}</small></div>`;
    };
    function chart(x){
      const vals=(x.arr||[]).slice(Math.max(0,N-28),N).map(v=>v==null||!isFinite(v)?null:Number(v));
      const good=vals.filter(v=>v!=null);if(good.length<4)return"";
      let lo=Math.min(...good),hi=Math.max(...good);if(!(hi>lo)){lo-=1;hi+=1;}const pad=(hi-lo)*.08;lo-=pad;hi+=pad;
      const W=660,H=112,P=10,X=i=>P+i*(W-2*P)/27,Y=v=>P+(hi-v)*(H-2*P)/(hi-lo);
      const segments=(a,b,col)=>{let out="",pts=[];for(let i=a;i<=b;i++){if(vals[i]==null){if(pts.length>1)out+=`<polyline points="${pts.join(' ')}"/>`;pts=[];}else pts.push(`${X(i)},${Y(vals[i])}`);}if(pts.length>1)out+=`<polyline points="${pts.join(' ')}"/>`;return `<g fill="none" stroke="${col}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${out}</g>`;};
      const av=(a,b)=>{const v=vals.slice(a,b+1).filter(v=>v!=null);return v.length?v.reduce((q,z)=>q+z,0)/v.length:null;};
      const p=av(0,13),n=av(14,27),meanLine=(v,a,b,col)=>v==null?"":`<line x1="${X(a)}" x2="${X(b)}" y1="${Y(v)}" y2="${Y(v)}" stroke="${col}" stroke-width="1.2" stroke-dasharray="5 4"/>`;
      return `<div class="insight-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${x.label}, ultimi 28 giorni">`+
        `<line x1="${X(13.5)}" x2="${X(13.5)}" y1="0" y2="${H}" stroke="var(--rule)"/>${meanLine(p,0,13,'var(--muted)')}${meanLine(n,14,27,'var(--accent)')}${segments(0,13,'var(--muted)')}${segments(14,27,'var(--accent)')}</svg>`+
        `<div class="legend"><span>14 precedenti · media ${x.fmt(p)}</span><span>ultimi 14 · media ${x.fmt(n)}</span></div></div>`;
    }
    const qty=f=>{const q=(f.qty_observed||0)+(f.qty_assumed||0),u=f.unit==='unit'?'×':` ${f.unit}`;return `${nf(q,q<10?1:0)}${u}`;};
    const recent=(D.days&&D.days._14foods||[]).map(f=>{const no=f.occ_observed||0,na=f.occ_assumed||0,n=no+na;
      return `<div class="food-row" title="${f.name}"><span>${f.name}</span><b>${n} ${n===1?'consumo':'consumi'} · ${qty(f)}</b>`+
        `<small>${no} osservati${na?` · ${na} ricostruiti`:''}</small></div>`;}).join("");
    const last=D.last&&D.last.n_kcal!=null?new Date(D0.getTime()+D.last.n_kcal*DAY).toLocaleDateString("it-IT"):"—";
    sheetIn.innerHTML=`<button class="sheet-x" type="button" aria-label="Chiudi" onclick="closeDay()">×</button><div class="when">ultimi 14 giorni vs 14 precedenti</div><h3>${selected.label.charAt(0).toUpperCase()+selected.label.slice(1)}</h3>${chart(selected)}<div class="insight-list">${all.map(line).join("")}</div>${recent?`<h4>Alimenti · ultime due settimane</h4><div class="food-intake">${recent}</div>`:''}<p class="t-foot">Diario aggiornato al ${last}. I totali sommano gli alimenti uguali; latte in ml e frutti in unità restano nelle loro unità reali. Le giornate ricostruite e quelle derivate da scontrino sono stime dichiarate, non pasti osservati.</p>`;
    sheet.classList.add("on");
  }
  document.getElementById("totals").onclick=e=>{const b=e.target.closest&&e.target.closest("[data-food]");if(b)insights(b.dataset.food);};
})();

/* ============================================================== il diario
   Il popup della giornata sa mostrare un giorno, ma ci si arriva solo colpendo un
   punto del grafico giusto: se non sai gia' che giorno cerchi, non lo trovi. Il
   diario e' la stessa giornata con una porta davanti — si sfoglia con le frecce o
   con una data — e con una differenza sostanziale: **si annota**.

   E l'annotazione e' vera. Fino al 2026-08-13 restava in `localStorage`, cioe' su
   un dispositivo solo, e la pagina sputava righe CSV da incollare a mano nel repo.
   Adesso c'e' un Worker (`tools/diario-worker/`) con un D1 dietro: la pagina gli
   parla, e quello che annoti dal telefono lo vedi dal portatile un istante dopo.

   Restano DUE registri e uno solo e' la verita'. Il Worker e' una casella di posta
   con un'ora di vita: la Action oraria la svuota dentro
   `tools/food/data/food_log.csv`, marca le operazioni `applied`, e da quel momento
   la pagina le legge dalla build. Per questo il diario mostra le operazioni
   pendenti come "in arrivo" e non come pasti gia' registrati — e per questo, se il
   Worker non risponde o la chiave non c'e', si torna alla bozza locale invece di
   perdere quello che stai scrivendo, dicendolo. */
const diaryEl = document.getElementById("diary");
const diaryIn = document.getElementById("diary-in");
const MEAL_SORT = ["colazione", "spuntino", "pranzo", "merenda", "cena",
                   "integratori", "non_specificato"];
/* I macro che il diario disegna a barre. Le kcal non ci sono: stanno gia' nel
   titolo della tavola, e ripeterle qui direbbe due volte la stessa cosa. */
const MACRO_BARRE = ["protein_g", "carb_g", "fiber_g", "fat_g"];
/* ------------------------------------------------------- la giornata, unita' */
/* Le righe della build, e basta: qui il diario si legge soltanto. Si scrive da
   Mission Control, che parla con lo stesso Worker `vita-diario` e finisce nello
   stesso `tools/food/data/food_log.csv`. Questa pagina e' pubblica, quella e'
   dietro login — e' li' che ha senso tenere una chiave, non qui.

   `row_key` resta nella riga anche se qui non serve a nessuno: e' la chiave che
   Mission Control manda e che apply_diary_ops.py ricostruisce sul CSV, e vederla
   nella stessa forma nei due posti e' quello che tiene onesto il confronto. */
function diaryRows(k) {
  let day = (D.days || {})[k];
  if (typeof day === "string") day = ((D.days || {})._p || {})[day];
  const rows = [];
  const meals = (day && day.meals) || {};
  for (const m of Object.keys(meals)) {
    const nth = {};
    (meals[m] || []).forEach(it => {
      const fid = it.f || "";
      /* l'ordinale conta le righe con quello STESSO food_id dentro il pasto: e'
         la chiave che apply_diary_ops.py ricostruisce sul CSV, dove le righe di
         alimenti diversi stanno mescolate */
      const j = nth[fid] = (nth[fid] === undefined ? 0 : nth[fid] + 1);
      const id = `${m}|${fid || it.n}|${j}`;
      rows.push({ id, meal: m, f: it.f || null, n: it.n, q: it.qn,
                  kcal: it.kcal, asm: !!it.a, recipe: it.r || "" });
    });
  }
  const rank = m => { const i = MEAL_SORT.indexOf(m); return i < 0 ? MEAL_SORT.length : i; };
  rows.sort((a, b) => rank(a.meal) - rank(b.meal));
  return { day, rows };
}

/* IL DIARIO SU PIU' GIORNI.
   Michele, 17/08: «un toggle che mi possa collassare non solo il giorno ma la settimana
   e le ultime due settimane, cosi' vedo le medie su quello. E ovviamente tutto deve
   essere mediato e pesato e sotto dovrei avere un riassunto delle somme in grammi di
   tutti gli alimenti su quel periodo».

   «Pesato» qui vuol dire una cosa precisa: la media si divide per i giorni CON DEL CIBO,
   non per i giorni di calendario. Dividere per sette quando due giorni non sono stati
   raccontati non da' «quanto mangio in media»: da' un numero piu' basso che non
   corrisponde a niente, ed e' lo stesso errore che il riquadro dei grassi evita con
   `how:"mean"`. I giorni vuoti si contano e si dichiarano, non si spalmano.

   I grammi invece si SOMMANO: la domanda «quanto pane ho mangiato in due settimane»
   vuole un totale, non una media. Per ogni alimento si tiene anche in quanti giorni
   e' comparso, che e' la differenza fra mangiarne tanto una volta e un po' sempre. */
let diarioGiorni = 1;
function diarioPeriodo(iEnd, n) {
  const tot = {}, cibi = new Map();
  let conCibo = 0, kcalOss = 0, kcalAsm = 0;
  const corpo = { sleep:[], score:[], hrv:[], rhr:[], steps:[], weight:[], ctl:[], tss:[] };
  const i0 = Math.max(0, iEnd - n + 1);
  for (let i = i0; i <= iEnd; i++) {
    ["sleep", "score", "hrv", "rhr", "steps", "weight", "ctl"].forEach(k => {
      const v = D[k] && D[k][i];
      if (v !== null && v !== undefined && isFinite(v)) corpo[k].push(v);
    });
    let t = 0, vista = false;
    D.acts.forEach(a => { if (a[0] === i) { t += a[5] || 0; vista = true; } });
    if (vista) corpo.tss.push(t);

    const { day, rows } = diaryRows(isoOf(i));
    if (!day || !day.tot) continue;
    conCibo++;
    kcalOss += day.obs || 0; kcalAsm += day.asm || 0;
    for (const k in day.tot) tot[k] = (tot[k] || 0) + (day.tot[k] || 0);
    for (const r of rows) {
      const key = r.f || r.n;
      const c = cibi.get(key) || { f:r.f, n:r.n, q:0, kcal:0, giorni:new Set(), asm:0 };
      c.q += (+r.q || 0); c.kcal += r.kcal || 0; c.giorni.add(i);
      if (r.asm) c.asm++;
      cibi.set(key, c);
    }
  }
  const media = {};
  for (const k in tot) media[k] = conCibo ? tot[k] / conCibo : 0;
  const mediaCorpo = {};
  for (const k in corpo) mediaCorpo[k] = corpo[k].length
    ? { v: corpo[k].reduce((a, b) => a + b, 0) / corpo[k].length, n: corpo[k].length } : null;
  return { i0, iEnd, giorni:iEnd - i0 + 1, conCibo, tot, media, mediaCorpo,
           obs:kcalOss, asm:kcalAsm,
           cibi:[...cibi.values()].map(c => ({ ...c, giorni:c.giorni.size }))
                  .sort((a, b) => b.kcal - a.kcal) };
}

/* Dichiarato qui, e non solo assegnato dentro openDiary/closeDiary come faceva prima:
   fino a quando il diario non veniva aperto una volta, `diaryIdx` non esisteva, e il
   gestore dell'Escape che lo legge sollevava un ReferenceError su OGNI Escape premuto
   in pagina. Non si vedeva perche' l'errore muore nel gestore e non ferma il resto —
   ma la console si riempiva e il tasto non chiudeva niente. */
let diaryIdx = null;

/* ----------------------------------------------------------------- disegno */
function diaryRender() {
  if (diaryIdx === null) return;
  const i = diaryIdx, k = isoOf(i);
  const { day, rows } = diaryRows(k);
  diaryIn.innerHTML = "";

  const x = mk("button", "sheet-x", diaryIn, "×");
  x.setAttribute("type", "button");
  x.setAttribute("aria-label", "Chiudi");
  x.addEventListener("click", closeDiary);

  const hd = mk("div", "sheet-hd", diaryIn);
  mk("div", "when", hd, DOW[(dayDate(i).getDay() + 6) % 7]);
  mk("h3", null, hd, fmtDate(i)).setAttribute("id", "diary-t");

  /* ---- navigazione ---- */
  const nav = mk("div", "dnav", diaryIn);
  const go = j => { if (j !== null && j >= 0 && j < N) { diaryIdx = j; diaryRender(); } };
  const prev = mk("button", null, nav, "‹ giorno prima");
  prev.setAttribute("type", "button");
  prev.addEventListener("click", () => go(i - 1));
  const picker = mk("input", null, nav);
  picker.setAttribute("type", "date");
  picker.value = k;
  picker.addEventListener("change", () => go(diaryIdxOf(picker.value)));
  const next = mk("button", null, nav, "giorno dopo ›");
  next.setAttribute("type", "button");
  next.addEventListener("click", () => go(i + 1));
  mk("span", "grow", nav);
  const last = mk("button", null, nav, "ultimo giorno");
  last.setAttribute("type", "button");
  last.addEventListener("click", () => go(N - 1));

  /* il periodo: un giorno, una settimana, due settimane */
  const per = mk("div", "dper", diaryIn);
  [[1, "il giorno"], [7, "7 giorni"], [14, "14 giorni"]].forEach(([n, lab]) => {
    const b2 = mk("button", diarioGiorni === n ? "on" : null, per, lab);
    b2.setAttribute("type", "button");
    b2.setAttribute("aria-pressed", String(diarioGiorni === n));
    b2.addEventListener("click", () => { diarioGiorni = n; diaryRender(); });
  });
  const P = diarioPeriodo(i, diarioGiorni);
  if (diarioGiorni > 1) mk("span", "dper-n", per,
    `${fmtDate(P.i0)} → ${fmtDate(P.iEnd)} · ${P.conCibo} giorni con del cibo su ${P.giorni}`);

  /* ---- le misure del giorno ---- */
  const kv = [];
  const push = (v, l) => { if (v !== null && v !== undefined) kv.push([v, l]); };
  if (diarioGiorni > 1) {
    /* sul periodo ogni misura porta su quanti giorni e' la media: due pesate e
       quattordici non valgono uguale, e nasconderlo sarebbe la stessa bugia della
       media divisa per i giorni di calendario */
    const M = P.mediaCorpo, su = m => m ? ` (${m.n})` : "";
    if (M.sleep)  push(hhmm(M.sleep.v), "sonno" + su(M.sleep));
    if (M.score)  push(nf(M.score.v), "punteggio" + su(M.score));
    if (M.hrv)    push(nf(M.hrv.v) + " ms", "hrv" + su(M.hrv));
    if (M.rhr)    push(nf(M.rhr.v), "fc riposo" + su(M.rhr));
    if (M.steps)  push(nf(M.steps.v), "passi" + su(M.steps));
    if (M.weight) push(nf(M.weight.v, 1) + " kg", "peso" + su(M.weight));
    if (M.ctl)    push(nf(M.ctl.v, 0), "fitness" + su(M.ctl));
    if (M.tss)    push(nf(M.tss.v, 0), `tss · ${M.tss.n} giorni con uscita`);
  } else {
    push(D.sleep[i] === null ? null : hhmm(D.sleep[i]), "sonno");
    push(D.score[i] === null ? null : nf(D.score[i]), "punteggio");
    push(D.hrv[i] === null ? null : nf(D.hrv[i]) + " ms", "hrv");
    push(D.rhr[i] === null ? null : nf(D.rhr[i]), "fc riposo");
    push(D.steps[i] === null ? null : nf(D.steps[i]), "passi");
    push(D.weight[i] === null ? null : nf(D.weight[i], 1) + " kg", "peso");
    push(D.ctl[i] === null ? null : nf(D.ctl[i], 0), "fitness");
    let tss = 0, nact = 0;
    D.acts.forEach(a => { if (a[0] === i) { nact++; tss += a[5] || 0; } });
    if (nact) push(nf(tss, 0), nact === 1 ? "tss · 1 uscita" : `tss · ${nact} uscite`);
  }

  /* ---- L'USCITA, e cosa chiede alla tavola (ordine #22, 21/08/2026) --------
     «Le informazioni dell'uscita dovrebbero essere in modo visibile: che tipo di
     uscita è stata, le statistiche, le calorie bruciate e i grammi di carboidrati
     che dovrebbero essere assunti, nel riassunto del diario.»

     Il fabbisogno di carboidrati e' gia' pesato sul carico e non da oggi: la serie
     `carb_target_g` lo stima dal TSS del giorno con `g/kg = 3 + 0,03 · TSS`,
     tagliata in [3, 10] — 3 g/kg da fermo, ~6 attorno a un TSS di 100, fino a 10
     nelle giornate grosse. Quello che mancava era mostrarlo QUI, accanto a cosa si
     e' mangiato, invece che solo dentro un riquadro in fondo alla pagina.

     Le calorie dell'uscita si mostrano solo se Intervals le ha misurate: sulle
     attivita' ricostruite dall'export Strava valgono zero, e uno zero scritto
     sembra un'uscita senza dispendio invece di un dato che non c'e'. */
  if (diarioGiorni === 1) {
    const uscite = D.acts.map((a, j) => [a, j]).filter(([a]) => a[0] === i);
    const NU = D.nutri || {};
    const tgt = NU.carb_target_g && NU.carb_target_g[i];
    if (uscite.length || (tgt !== null && tgt !== undefined && isFinite(tgt))) {
      mk("h4", null, diaryIn, uscite.length ? "L'uscita, e cosa chiede alla tavola"
                                            : "Cosa chiede la tavola");
      const ul = mk("ul", "acts", diaryIn);
      for (const [a, j] of uscite) {
        const li = mk("li", null, ul);
        const nome = ((D.anames || [])[j] || [])[0] || ((D.sports || [])[a[1]] || "uscita");
        mk("span", null, li, nome);
        const bits = [];
        if (a[2]) bits.push(hhmm(a[2] / 60));
        if (a[3]) bits.push(nf(a[3] / 1000, 1) + " km");
        if (a[4]) bits.push(nf(a[4]) + " m");
        if (a[5]) bits.push(nf(a[5], 0) + " tss");
        if (a[10]) bits.push(nf(a[10]) + " kcal");
        mk("em", null, li, bits.join(" · "));
      }
      if (tgt !== null && tgt !== undefined && isFinite(tgt)) {
        const avuti = day && day.tot ? day.tot.carb_g : null;
        const gap = avuti === null || avuti === undefined ? null : avuti - tgt;
        const p = mk("p", "hint", diaryIn);
        p.textContent =
          `Con questo carico il fabbisogno stimato è di ${nf(tgt, 0)} g di carboidrati` +
          (avuti === null || avuti === undefined ? "."
            : `, e ne risultano ${nf(avuti, 0)}: ` +
              (Math.abs(gap) < 15 ? "in linea."
                : gap > 0 ? `${nf(gap, 0)} g in più.` : `${nf(-gap, 0)} g in meno.`)) +
          " La stima è 3 g/kg da fermo e sale col TSS fino a 10 nelle giornate grosse:" +
          " è un ordine di grandezza per leggere lo scarto, non una prescrizione.";
      }
    }
  }
  if (kv.length) {
    mk("h4", null, diaryIn, diarioGiorni > 1 ? "Corpo, media al giorno" : "Corpo");
    const box = mk("div", "kv", diaryIn);
    for (const [v, l] of kv) {
      const c = mk("div", null, box);
      mk("b", null, c, v);
      mk("span", null, c, l);
    }
  }

  /* ---- la tavola ---- */
  if (diarioGiorni > 1) {
    const oss = P.obs + P.asm ? Math.round(100 * P.obs / (P.obs + P.asm)) : null;
    mk("h4", null, diaryIn, `Tavola — ${nf(P.media.kcal || 0)} kcal al giorno`
      + (oss !== null ? ` · ${nf(oss)}% osservato` : ""));
    if (!P.cibi.length) mk("p", "d-empty", diaryIn, "Niente di registrato in questo periodo.");
    else {
      /* IL RIASSUNTO IN GRAMMI, che e' la richiesta letterale. Somme, non medie:
         «quanto pane in due settimane» vuole un totale. `giorni` accanto distingue
         chi torna tutti i giorni da chi e' passato una volta sola. */
      const tb = mk("table", "d-cibi", diaryIn);
      tb.innerHTML = "<tr><th>alimento</th><th>totale</th><th>giorni</th><th>kcal</th></tr>"
        + P.cibi.map(c => {
            const u = unitOf(c.f) === "unit" ? "×" : (unitOf(c.f) || "g");
            return `<tr${c.asm ? ' class="asm"' : ""}><td>${c.n}</td>`
              + `<td class="num">${nf(c.q, c.q < 10 ? 1 : 0)} ${u}</td>`
              + `<td class="num">${c.giorni}</td>`
              + `<td class="num">${nf(c.kcal)}</td></tr>`;
          }).join("");
    }
  } else {
  mk("h4", null, diaryIn, `Tavola — ${nf(day && day.tot ? day.tot.kcal : 0)} kcal`
    + (day && day.asm ? ` · ${nf(Math.round(100 * day.obs / (day.obs + day.asm)))}% osservato` : ""));

  if (!rows.length) {
    mk("p", "d-empty", diaryIn, "Nessun pasto registrato per questo giorno.");
  } else {
    /* IL PASTO SI APRE, come su Chronometer (ordine #22, 21/08/2026):
       «magari fai una roba tipo chronometer che ci ha la colazione con le statistiche
       totali della colazione e le ricette. Se schiaccio vedo i singoli contributi».

       Chiuso di default: una giornata raccontata bene sono trenta righe, e trenta
       righe non si leggono. Chiusa e' cinque righe con sopra quanto pesa ognuna;
       aperta e' quello che c'era prima, piu' le percentuali di fabbisogno DEL PASTO.

       Le voci di una stessa ricetta stanno insieme sotto il suo nome e il suo
       subtotale, invece di ripetere «· Porridge» su cinque righe di fila senza mai
       dire quanto pesa il porridge. */
    /* Le voci si raggruppano per RICETTA dentro il pasto, e il gruppo si tiene
       tutte le sue righe anche se nel registro non sono contigue — bastava
       aggiungere un alimento in mezzo per spezzare il porridge in due porridge,
       ognuno col subtotale dell'altro. Qui l'ordine dei gruppi e' quello di prima
       comparsa, cosi' la giornata si legge ancora nell'ordine in cui e' successa. */
    const gruppiDi = pasto => {
      const ord = [], per = new Map();
      for (const r of rows) {
        if (r.meal !== pasto) continue;
        const k = r.recipe || ("#sciolta" + ord.length);   /* sciolta: gruppo per se' */
        if (!per.has(k)) { per.set(k, { r: r.recipe || "", items: [] }); ord.push(k); }
        per.get(k).items.push(r);
      }
      /* «Per quanto riguarda la lista degli ingredienti, metti quelli piu' calorici
         in cima» (ordine #27). Vale dentro il gruppo e fra i gruppi: quello che pesa
         si legge per primo, le briciole finiscono in fondo dove stanno bene. L'ordine
         di prima non diceva niente a nessuno — era quello in cui erano state scritte
         le righe nel registro. */
      const gr = ord.map(k => per.get(k));
      const kcalDi = g => g.items.reduce((s, x) => s + (x.kcal || 0), 0);
      for (const g of gr) g.items.sort((a, b) => (b.kcal || 0) - (a.kcal || 0));
      gr.sort((a, b) => kcalDi(b) - kcalDi(a));
      return gr;
    };

    let cur = null, box = null, det = null;
    for (const r of rows) {
      if (r.meal !== cur) {
        cur = r.meal;
        det = mk("details", "meal", diaryIn);
        const sum = mk("summary", null, det);
        mk("span", "mname", sum, MEAL_IT[cur] || cur);
        const st = mealStats(day, cur);
        const kcalPasto = rows.filter(x => x.meal === cur)
                              .reduce((s, x) => s + (x.kcal || 0), 0);
        mk("em", null, sum, st
          ? `${nf(st.tot.kcal)} kcal · P ${nf(st.tot.protein_g, 0)} · C ${nf(st.tot.carb_g, 0)} · G ${nf(st.tot.fat_g, 0)}`
          : `${nf(kcalPasto)} kcal`);
        box = det;
        /* le voci, gruppo per gruppo: la ricetta col suo nome e il suo subtotale,
           le sciolte da sole */
        for (const g of gruppiDi(cur)) {
          let dove = det;
          if (g.r) {
            const w = mk("div", "mrec", det);
            const cap = mk("b", null, w);
            mk("span", null, cap, g.r);
            mk("s", null, cap,
               `${nf(g.items.reduce((s, x) => s + (x.kcal || 0), 0))} kcal`);
            dove = mk("div", null, w);
          }
          for (const x of g.items) {
            const row = mk("div", ["d-row", x.asm ? "asm" : ""].filter(Boolean).join(" "), dove);
            mk("span", null, row, x.n);
            /* «Devi fare un rounding dei grammi» (ordine #27). 66.6667 g non e' una
               misura: e' l'aritmetica di una ricetta scalata, uscita allo scoperto.
               Un decimale sotto i 10 — mezza banana, 1,5 brioche — e nessuno sopra. */
            mk("b", null, row, nf(x.q, x.q < 10 ? 1 : 0));
            mk("em", null, row, `${unitOf(x.f) === "unit" ? "×" : unitOf(x.f)} · ${nf(x.kcal)} kcal`);
          }
        }
        if (st) {
          /* «Magari mi dai un overview piu' visuale della distribuzione proteina,
             carbo, grassi» (ordine #27). Una striscia sola, larga quanto il pasto:
             le tre quote si guardano come si guarda una torta, senza leggere tre
             numeri e sommarli con l'occhio. Le percentuali sono di ENERGIA, non di
             peso — 4 kcal al grammo per proteine e carboidrati, 9 per i grassi —
             perche' la domanda e' da dove arrivano le calorie, non quanto pesa
             quello che si e' mangiato. */
          const kp = st.tot.protein_g * 4, kc = st.tot.carb_g * 4, kg = st.tot.fat_g * 9;
          const tot3 = kp + kc + kg;
          if (tot3 > 0) {
            const macro = mk("div", "macro-striscia", det);
            for (const [q, cls, et] of [[kp, "p", "proteine"], [kc, "c", "carboidrati"],
                                        [kg, "g", "grassi"]]) {
              const parte = 100 * q / tot3;
              if (parte < 0.5) continue;
              const b = mk("b", cls, macro, Math.round(parte) + "%");
              b.setAttribute("style", "width:" + parte.toFixed(1) + "%");
              b.setAttribute("title", et + ": " + Math.round(parte) + "% delle calorie del pasto");
            }
          }
          const d = mk("div", "mdens", det);
          const bars = mk("div", "bars", d);
          bars.innerHTML = Object.keys(st.pct).map(n => {
            const q = st.den[n], sem = semaforo(q);
            return bar(NUTRI_IT[n] || n, st.pct[n], false, sem
              ? `<span title="densità ×${nf(q, q < 10 ? 1 : 0)} — ${sem.che}">${sem.emoji}</span>`
              : "");
          }).join("");
          mk("p", "hint", d, `A destra la densità: ${SEMAFORO[0][1]} il pasto ha dato `
            + `più di quel nutriente di quanto sia costato in calorie, ${SEMAFORO[1][1]} è `
            + `nella media, ${SEMAFORO[2][1]} costa più di quanto dia. Il numero esatto `
            + `sta sul pallino. Il metro è la dieta di riferimento da `
            + `${nf((D.foodProfile || {}).reference_kcal)} kcal.`);
          /* le barre stanno DOPO le voci, ed e' voluto: prima cosa si e' mangiato,
             poi cosa ha dato */
        }
      }
      /* le righe le ha gia' scritte `gruppiDi` quando il pasto e' nato: qui non
         resta niente da fare, e il ciclo serve solo a riconoscere il pasto dopo */
    }
  }
  }

  /* ---- micro e macro, TUTTI ----
     Michele, 17/08: «quando apro il diario voglio avere tutti i micro macro del giorno
     stesso». Prima c'erano quattro barre. Qui c'e' la tabella intera: quanto, e quanto
     e' del fabbisogno. Le tre voci col TETTO (sodio, saturi, zuccheri) restano marcate
     come tetti e non come obiettivi — superare il 100 % del potassio e superare il
     100 % del sodio sono due cose opposte. */
  {
    const base = diarioGiorni > 1 ? P.media : (day && day.tot);
    const rif = diarioGiorni > 1 ? null : (day && day.pct);
    const cap = day && day.cap;
    if (base && Object.keys(base).length) {
      mk("h4", null, diaryIn, diarioGiorni > 1
        ? `Micro e macro, media al giorno su ${P.conCibo} giorni`
        : "Micro e macro del giorno");
      const tb = mk("table", "d-nutri", diaryIn);
      const righe = [];
      const quota = k => {
        if (rif && rif[k] !== undefined) return rif[k];
        // sul periodo la percentuale si ricava dal rapporto misura/fabbisogno del
        // giorno aperto, che e' l'unico posto dove il fabbisogno e' scritto
        const dr = day && day.pct, dt = day && day.tot;
        if (dr && dt && dr[k] !== undefined && dt[k]) return base[k] * dr[k] / dt[k];
        return null;
      };
      for (const k of Object.keys(NUTRI_IT)) {
        if (base[k] === undefined) continue;
        const q = quota(k);
        righe.push(`<tr><td>${NUTRI_IT[k]}</td><td class="num">${nf(base[k], base[k] < 10 ? 1 : 0)} ${UNI_IT(k)}</td>`
          + `<td class="num">${q === null ? "—" : nf(q) + " %"}</td></tr>`);
      }
      for (const k of Object.keys(CAP_IT)) {
        if (base[k] === undefined) continue;
        const c2 = cap && cap[k];
        righe.push(`<tr class="tetto"><td>${CAP_IT[k]}</td><td class="num">${nf(base[k], base[k] < 10 ? 1 : 0)} ${UNI_IT(k)}</td>`
          + `<td class="num">${c2 === undefined || c2 === null ? "tetto" : nf(c2) + " % del tetto"}</td></tr>`);
      }
      tb.innerHTML = "<tr><th>nutriente</th><th>quanto</th><th>del fabbisogno</th></tr>" + righe.join("");
    }
  }

  /* ---- i macro, in barre ---- */
  if (day && day.pct) {
    const P = D.foodProfile || {}, rda = (P.rda || {});
    const need = { protein_g: P.weight_kg && P.protein_g_per_kg ? P.weight_kg * P.protein_g_per_kg : null,
                   fiber_g: rda.fiber_g || null };
    mk("h4", null, diaryIn, "Macro, in % del fabbisogno");
    const bars = mk("div", "bars", diaryIn);
    const html = [];
    for (const nut of MACRO_BARRE) {
      if (day.pct[nut] === undefined) continue;
      const basis = need[nut] || (day.tot[nut] && day.pct[nut]
        ? day.tot[nut] * 100 / day.pct[nut] : null);
      html.push(bar(NUTRI_IT[nut] || nut,
        basis ? 100 * (day.tot[nut] || 0) / basis : day.pct[nut]));
    }
    bars.innerHTML = html.join("");
  }

  mk("p", "hint", diaryIn, "Questo diario si legge soltanto. Si annota da Mission "
    + "Control, che scrive nello stesso registro: tools/food/data/food_log.csv.");
}

function diaryIdxOf(iso) {
  if (!iso || iso.length < 10) return null;
  const y = +iso.slice(0, 4), m = +iso.slice(5, 7), d = +iso.slice(8, 10);
  if (!isFinite(y) || !isFinite(m) || !isFinite(d)) return null;
  const j = Math.round((new Date(y, m - 1, d).getTime() - D0.getTime()) / DAY);
  return j >= 0 && j < N ? j : null;
}

/* Si apre sull'ultimo giorno che ha davvero del cibo: aprire su una giornata vuota
   farebbe sembrare rotto un diario che invece e' solo in pari. */
function diaryLastWithFood() {
  for (let i = N - 1; i >= 0 && i > N - 400; i--) if ((D.days || {})[isoOf(i)]) return i;
  return N - 1;
}

function openDiary(i) {
  diaryIdx = i === undefined || i === null ? diaryLastWithFood()
    : Math.max(0, Math.min(N - 1, i));
  diaryRender();
  diaryEl.classList.add("on");
  document.body.style.overflow = "hidden";
}
function closeDiary() {
  diaryEl.classList.remove("on");
  diaryIdx = null;
  document.body.style.overflow = "";
}
diaryEl.addEventListener("click", ev => { if (ev.target === diaryEl) closeDiary(); });
addEventListener("keydown", ev => {
  // se c'e' un ⓘ aperto sopra, l'Escape e' suo: lo chiude quello, e il diario resta
  if (ev.key === "Escape" && diaryIdx !== null && !window.CRUSCOTTO.info.aperto()) closeDiary();
});
document.getElementById("diary-btn").addEventListener("click", () => openDiary());
window.openDiary = openDiary;
window.CRUSCOTTO.diary = {
  open:openDiary, close:closeDiary, render:diaryRender, rows:diaryRows,
  idxOf:diaryIdxOf, iso:isoOf, lastWithFood:diaryLastWithFood, node:diaryIn,
};

drawAll();
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(drawAll, 160); });
</script>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "24fb0c5b538b4448b1281261e5e329a0"}'></script><!-- End Cloudflare Web Analytics -->
</body>
</html>
"""


if __name__ == "__main__":
    main()
