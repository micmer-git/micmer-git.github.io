#!/usr/bin/env python3
"""
build_signore.py — Il Signore dei kJ: una routine sola, il mese come unità.

Prima c'erano due pagine tenute a mano e mai allineate: `signore-dei-kj.html`
(otto "anelli" da 100.000 kJ) e `signore-dei-kj-weekly.html` (55 capitoli
settimanali). Stessa fonte, due impaginazioni, due verità — e infatti al momento
della fusione divergevano (vedi `--check`). Questo script le sostituisce
entrambe con **una sola tirata di dati e un solo percorso di codice**.

L'unità della pagina è il **mese di calendario**. Le settimane sopravvivono come
scene dentro il loro mese; gli anelli sopravvivono come pietre miliari, piantate
nel mese in cui il contatore cumulativo ha davvero tagliato la soglia — data
calcolata, non editoriale.

Cosa produce
------------
  signore-dei-kj.html          la saga mensile completa (pagina canonica)
  signore-dei-kj-weekly.html   alias: reindirizza alla mensile, l'URL resta vivo

L'URL settimanale è linkato da /vita, da /diario-di-un-unno e da
/sogni-di-un-unno: non può sparire, ma non ha più contenuto proprio — "tutto
mensile" era la richiesta, e due pagine con due strutture erano il problema.

Come sta insieme il testo
-------------------------
La prosa non si genera: sta in `tools/signore.json`, come le storie di /top-20
stanno in `top-20.json`. `--harvest` la estrae una volta sola dalle due pagine
esistenti (55 settimane + 18 capitoli d'anello + la Compagnia) e non va più
rieseguito, se non per riassorbire una modifica fatta a mano sulle vecchie
pagine. Tutti i **numeri** invece si ricalcolano a ogni build da Intervals.icu:
nel JSON editoriale non ne resta nessuno che possa invecchiare.

Uso
---
    set INTERVALS_API_KEY=...            (o --api-key, o tools/.intervals_key)

    python tools/build_signore.py --check      # cosa dicono i dati, non scrive
    python tools/build_signore.py --dry-run    # costruisce tutto, non scrive
    python tools/build_signore.py              # scrive le due pagine
    python tools/build_signore.py --offline    # dalla cache, senza rete
    python tools/build_signore.py --harvest    # riestrae la prosa dalle pagine

Quello che sovrascrive finisce prima in `*.bak`.
"""
import argparse
import collections
import datetime
import html as htmlmod
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_intervals import api, get_api_key  # noqa: E402  (Cloudflare-safe GET)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
CACHE = os.path.join(HERE, ".signore_cache.json")
EDIT = os.path.join(HERE, "signore.json")
PAGE = os.path.join(ROOT, "signore-dei-kj.html")
ALIAS = os.path.join(ROOT, "signore-dei-kj-weekly.html")

ATHLETE = "i302515"
RING_KJ = 100_000          # un anello ogni centomila kJ — la scala della saga
GAP_DAYS = 45              # oltre questo, un vuoto è un vuoto d'archivio

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESE_N = {m: i + 1 for i, m in enumerate(MESI)}
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


# ---------------------------------------------------------------- dati grezzi

def pull(key, offline=False):
    """Tutte le attività dell'archivio, ordinate. La cache è gitignorata."""
    if offline:
        if not os.path.exists(CACHE):
            sys.exit("--offline ma la cache non esiste: gira una volta con la rete.")
        acts = json.load(open(CACHE, encoding="utf-8"))
    else:
        acts = api(f"athlete/{ATHLETE}/activities"
                   f"?oldest=2015-01-01&newest={datetime.date.today().isoformat()}", key)
        if not acts:
            sys.exit("Intervals.icu non ha risposto — controlla la chiave.")
        json.dump(acts, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return normalise(sorted(acts, key=lambda a: a.get("start_date_local") or ""))


def normalise(acts):
    """Arrotonda una volta sola, all'ingresso, le misure che la pagina somma.

    Il payload inline porta i kJ interi e i metri interi; se i totali in testata
    venissero invece dai float grezzi, la somma dei valori mostrati non farebbe
    il totale mostrato — per una manciata di unità, ma abbastanza da rendere la
    pagina non verificabile. `check_signore.cjs` rifà i totali dal payload e
    pretende che tornino alla cifra: questo è ciò che glielo permette.
    """
    for a in acts:
        # Diciannove voci dell'archivio (18 dentro la saga) sono segnaposto:
        # Intervals le elenca e poi risponde
        # «STRAVA activities are not available via the API» — niente tipo, niente
        # nome, niente numeri. Il loro `id` però non è un id Intervals (`i…`): è
        # l'id Strava, come si vede dall'ordine di grandezza confrontato con le
        # attività vicine. Quindi il link a Intervals non esiste e quello a
        # Strava sì, ed è l'unico modo di non lasciarle come righe cieche.
        if a.get("source") == "STRAVA" and str(a.get("id") or "").isdigit():
            a["strava_id"] = a.get("strava_id") or a["id"]
            a["id"] = None
            a["type"] = a.get("type") or "Strava"
            a["name"] = a.get("name") or "attività non esposta dall'API di Intervals"
        for f, q in (("icu_joules", 1000), ("total_elevation_gain", 1),
                     ("total_elevation_loss", 1), ("distance", 1),
                     ("moving_time", 1), ("elapsed_time", 1), ("icu_training_load", 1)):
            v = a.get(f)
            if isinstance(v, (int, float)):
                a[f] = int(round(v / q)) * q
    return acts


def day(a):
    return (a.get("start_date_local") or "")[:10]


def num(a, f):
    v = a.get(f)
    return v if isinstance(v, (int, float)) else 0


def find_gaps(acts):
    """Ogni intervallo di ≥GAP_DAYS senza una singola attività.

    Serve a una cosa sola: un vuoto d'archivio non è riposo. Il buco
    2021-10-18 → 2023-04-11 legge esattamente come diciotto mesi di
    detraining e non lo è; va nominato, mai attraversato con una linea.
    """
    days = sorted({day(a) for a in acts if day(a)})
    out, prev = [], None
    for d in days:
        dd = datetime.date.fromisoformat(d)
        if prev and (dd - prev).days >= GAP_DAYS:
            out.append((prev.isoformat(), d, (dd - prev).days))
        prev = dd
    return out


# ------------------------------------------------------------- il carico vero

def first_real_load(acts):
    """Il primo giorno da cui `icu_training_load` significa qualcosa.

    Non è il primo valore non nullo: le importazioni Strava 2015-2018 arrivano
    senza FC né potenza, quindi con load 0, e qualche gara isolata invece ce
    l'ha. La regola è la stessa di build_vita.py — il primo giorno le cui 28
    *giornate di calendario* successive portano più di un carico simbolico — e
    dev'essere la stessa, o due pagine dello stesso sito daterebbero in modo
    diverso lo stesso fatto. Il calendario va riempito prima di scorrerlo: su una
    lista dei soli giorni con attività una finestra di 28 coprirebbe anni.
    Presentare il 2015-2018 come "nessun allenamento" sarebbe falso, ed è
    l'errore che questa funzione impedisce.
    """
    byday = collections.Counter()
    for a in acts:
        byday[day(a)] += num(a, "icu_training_load")
    if not byday:
        return None
    d0 = datetime.date.fromisoformat(min(byday))
    d1 = datetime.date.fromisoformat(max(byday))
    days = [(d0 + datetime.timedelta(days=i)).isoformat()
            for i in range((d1 - d0).days + 1)]
    for i in range(len(days) - 28):
        if sum(byday.get(d, 0) for d in days[i:i + 28]) > 100:
            return days[i]
    return days[0]


# ------------------------------------------------------------------ payload

# Ogni riga di attività è questa lista, nell'ordine. Il payload è inline nella
# pagina (niente fetch a runtime), quindi ogni campo costa ~1 KB ogni mille
# attività: sono qui solo quelli che si leggono davvero in scheda. Misurato:
# 1.384 attività × 45 campi = 437 KB non compressi, ~180 KB gzippati da Pages
# sulla pagina intera.
KEYS = [
    "id",      # i161386165  -> intervals.icu/activities/i161386165
    "sid",     # strava_id   -> strava.com/activities/19118913846 (non su tutte: vedi `sid_from`)
    "date", "time", "name", "type", "desc",
    "mov", "ela", "dist", "up", "down", "altmin", "altmax",
    "spd", "spdmax", "cad", "hr", "hrmax", "hrrest", "lthr",
    "w", "np", "ftp", "vi", "ef", "dec", "pol",
    "kj", "kjftp", "kcal", "carb",
    "tl", "int", "trimp", "strain", "ctl", "atl",
    "temp", "dev", "src", "gear", "race", "commute", "hrz",
]
FROM = {
    "id": "id", "sid": "strava_id", "name": "name", "type": "type",
    "desc": "description", "mov": "moving_time", "ela": "elapsed_time",
    "dist": "distance", "up": "total_elevation_gain", "down": "total_elevation_loss",
    "altmin": "min_altitude", "altmax": "max_altitude",
    "spd": "average_speed", "spdmax": "max_speed", "cad": "average_cadence",
    "hr": "average_heartrate", "hrmax": "max_heartrate", "hrrest": "icu_resting_hr",
    "lthr": "lthr", "w": "icu_average_watts", "np": "icu_weighted_avg_watts",
    "ftp": "icu_ftp", "vi": "icu_variability_index", "ef": "icu_efficiency_factor",
    "dec": "decoupling", "pol": "polarization_index",
    "kj": "icu_joules", "kjftp": "icu_joules_above_ftp", "kcal": "calories",
    "carb": "carbs_used", "tl": "icu_training_load", "int": "icu_intensity",
    "trimp": "trimp", "strain": "strain_score", "ctl": "icu_ctl", "atl": "icu_atl",
    "temp": "average_temp", "dev": "device_name", "src": "source",
    "race": "race", "commute": "commute", "hrz": "icu_hr_zone_times",
}
ROUND = {"spd": 2, "spdmax": 2, "cad": 0, "vi": 3, "ef": 3, "dec": 1, "pol": 2,
         "ctl": 1, "atl": 1, "temp": 1, "trimp": 0, "strain": 0,
         "altmin": 0, "altmax": 0, "up": 0, "down": 0, "dist": 0}


def row(a):
    """Un'attività -> una riga del payload. I None restano None, non 0.

    Distinguere "non misurato" da "zero" è la ragione per cui questa funzione
    non usa `num()`: una pedalata invernale senza misuratore ha 0 kJ *registrati*,
    non 0 kJ prodotti, e la scheda deve poterlo dire con un trattino.
    """
    out = []
    for k in KEYS:
        if k == "date":
            out.append(day(a))
            continue
        if k == "time":
            out.append((a.get("start_date_local") or "")[11:16])
            continue
        if k == "gear":
            # `gear` è un oggetto e il suo `name` è quasi sempre null: quello che
            # resta identificabile è l'id, che è comunque una bici diversa da un'altra
            gr = a.get("gear") or {}
            out.append(gr.get("name") or gr.get("id"))
            continue
        v = a.get(FROM[k])
        if isinstance(v, float):
            v = round(v, ROUND.get(k, 2))
            if v == int(v):
                v = int(v)
        if k == "sid" and v is not None:
            v = str(v)
        if k == "kj" and isinstance(v, (int, float)):
            v = int(round(v / 1000))          # joule -> kJ, una volta sola, qui
        if k == "kjftp" and isinstance(v, (int, float)):
            v = int(round(v / 1000))
        out.append(v)
    return out


# ---------------------------------------------------------------- aggregati

class Bucket:
    __slots__ = ("key", "acts", "n", "dist", "up", "mov", "kj", "tl", "types")

    def __init__(self, key):
        self.key, self.acts = key, []
        self.n = self.dist = self.up = self.mov = self.kj = self.tl = 0
        self.types = collections.Counter()

    def add(self, a):
        self.acts.append(a)
        self.n += 1
        self.dist += num(a, "distance")
        self.up += num(a, "total_elevation_gain")
        self.mov += num(a, "moving_time")
        self.kj += num(a, "icu_joules")
        self.tl += num(a, "icu_training_load")
        self.types[a.get("type") or "?"] += 1


def bucket_by(acts, keyfn):
    out = collections.OrderedDict()
    for a in acts:
        k = keyfn(a)
        if k not in out:
            out[k] = Bucket(k)
        out[k].add(a)
    return out


def months_span(first, last):
    """Tutti i mesi di calendario fra due date, compresi quelli vuoti.

    Saltare un mese senza attività lo cancellerebbe dalla storia; qui esiste,
    con zero dentro e detto.
    """
    y, m = first.year, first.month
    out = []
    while (y, m) <= (last.year, last.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def ring_crossings(acts):
    """(n, data, kJ cumulativi, id attività) per ogni soglia da 100.000 kJ.

    L'anello N si chiude il giorno in cui il contatore *taglia* N×100.000 kJ.
    È una data calcolata: la vecchia pagina assegnava gli anelli a occhio e
    infatti sbagliava di un anello intero (ne dichiarava otto, ne erano nove).
    """
    out, c, n = [], 0.0, 1
    for a in acts:
        c += num(a, "icu_joules")
        while c >= n * RING_KJ * 1000:
            out.append((n, day(a), round(c / 1000), a.get("id"), a.get("name") or ""))
            n += 1
    return out


# ----------------------------------------------------------- prosa editoriale

STORY_RE = re.compile(
    r'<article class="story reveal" id="week-(\d+)".*?'
    r'<span class="week-mood">(.*?)</span>.*?'
    r'<h2 class="story-title">(.*?)</h2>\s*'
    r'<p class="story-subtitle">(.*?)</p>\s*'
    r'<div class="story-body">(.*?)</div>\s*'
    r'<div class="stat-strip">(.*?)</div>', re.S)

BOOK_RE = re.compile(
    r'<section class="book reveal" data-anello="(\d+)">.*?'
    r'<h2 class="book-title">(.*?)</h2>(.*?)</section>', re.S)

CHAP_RE = re.compile(
    r'<h3 class="chapter-title">(.*?)</h3>\s*<div class="chapter-body">(.*?)</div>', re.S)

RANGE_TOK = re.compile(r"(\d{1,2})(?:\s*([a-zà-ù]+))?(?:\s+(\d{4}))?")


def parse_range(s):
    """"27 luglio – 2 agosto 2026" / "13–19 luglio 2026" -> (lunedì, domenica).

    Quattro forme diverse convivono nella pagina settimanale, e l'anno compare
    una volta sola in fondo: il mese e l'anno mancanti si ereditano all'indietro
    dalla fine dell'intervallo, che è l'unico estremo sempre completo.
    """
    s = re.sub(r"<[^>]+>", "", s).replace("–", "-").replace("—", "-")
    a, b = [x.strip() for x in s.split("-", 1)]
    mb, ma = RANGE_TOK.match(b), RANGE_TOK.match(a)
    d2, m2, y2 = int(mb.group(1)), MESE_N[mb.group(2)], int(mb.group(3))
    d1 = int(ma.group(1))
    m1 = MESE_N[ma.group(2)] if ma.group(2) else m2
    y1 = int(ma.group(3)) if ma.group(3) else (y2 - 1 if m1 > m2 else y2)
    return datetime.date(y1, m1, d1), datetime.date(y2, m2, d2)


def harvest():
    """Estrae la prosa dalle due pagine pubblicate in tools/signore.json.

    Si esegue una volta. Le settimane conservano data d'inizio e fine (parsate
    dal sottotitolo italiano e *verificate* lunedì→domenica: se una non torna,
    esce invece di scriverla storta); le strisce di statistiche NON si
    conservano, perché si ricalcolano — anzi, il vecchio valore viene tenuto da
    parte solo per `--check`, che confronta il pubblicato col ricalcolato.
    """
    weeks, rings = [], []
    src_w = open(ALIAS, encoding="utf-8").read()
    # Il primo build sovrascrive proprio le pagine da cui si raccoglie: da lì in
    # poi --harvest troverebbe le pagine generate e svuoterebbe signore.json
    # senza dire niente. Meglio rifiutarsi e dire dove sta l'originale.
    if "build_signore.py" in src_w or "build_signore.py" in open(PAGE, encoding="utf-8").read():
        sys.exit("Le pagine sono già quelle generate: non c'è più nulla da raccogliere.\n"
                 "La prosa sta in tools/signore.json. Per rifare l'estrazione servono le\n"
                 "pagine originali:  git show 377fe8d:signore-dei-kj-weekly.html")
    for n, mood, title, sub, body, strip in STORY_RE.findall(src_w):
        a, b = parse_range(sub)
        if a.weekday() != 0 or b.weekday() != 6 or (b - a).days != 6:
            sys.exit(f"settimana {n}: '{sub}' non è un lunedì→domenica ({a}→{b})")
        weeks.append({"n": int(n), "mood": mood.strip(), "title": title.strip(),
                      "start": a.isoformat(), "end": b.isoformat(),
                      "html": body.strip(), "published_strip": strip.strip()})
    weeks.sort(key=lambda w: w["start"])

    src_a = open(PAGE, encoding="utf-8").read()
    for n, title, rest in BOOK_RE.findall(src_a):
        rings.append({"n": int(n), "title": title.strip(),
                      "chapters": [{"title": t.strip(), "html": h.strip()}
                                   for t, h in CHAP_RE.findall(rest)]})
    rings.sort(key=lambda r: r["n"])

    # La Compagnia: si tengono le persone, si buttano le discipline. Le voci
    # "La Ride, 548 uscite, 35.641 km…" sono una tabella travestita da prosa e
    # invecchiano a ogni uscita; la tabella vera la rigenera questo script.
    comp = []
    m = re.search(r'<h3>La Compagnia</h3>\s*<ul>(.*?)</ul>', src_a, re.S)
    disc = re.compile(r"^(La Ride|La Run|Lo Swim|Il BackcountrySki|La VirtualRide|"
                      r"L'Hike|L'OpenWaterSwim|L'AlpineSki|Il TrailRun)\b")
    if m:
        for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S):
            li = li.strip()
            if li and not disc.match(re.sub(r"<[^>]+>", "", li)):
                comp.append(li)

    ed = {"_": "Prosa editoriale del Signore dei kJ. I numeri NON stanno qui: "
               "li ricalcola build_signore.py a ogni build.",
          "era_start": "2023-04-11", "ring_kj": RING_KJ,
          "rings": rings, "weeks": weeks, "compagnia": comp, "months": {}}
    json.dump(ed, open(EDIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"harvest -> {EDIT}: {len(weeks)} settimane, {len(rings)} anelli "
          f"({sum(len(r['chapters']) for r in rings)} capitoli), "
          f"{len(comp)} voci di Compagnia")
    return ed


# ------------------------------------------------- link nella prosa: verifica

LINK_RE = re.compile(r'href="https://www\.strava\.com/activities/(\d+)"')
KM_RE = re.compile(r"(\d{1,3})[,.](\d)\s*(?:km|chilometri)")


def fix_prose_links(txt, by_sid, in_window):
    """Ogni link Strava nella prosa deve puntare a un'attività che esiste.

    Tre non ci puntavano (16615, 16630, 16645: id troncati, mai stati validi).
    Quando l'id non risolve si prova a ricostruirlo dai chilometri citati nel
    testo del link, cercati fra le attività di quella settimana; se nemmeno
    quello basta, il link viene tolto e il testo resta — un rimando che porta
    a una 404 di Strava è peggio di una frase senza rimando.
    """
    report = []

    def one(m):
        sid = m.group(1)
        if sid in by_sid:
            return m.group(0)
        seg = txt[m.end():m.end() + 400]
        km = KM_RE.search(seg)
        if km:
            want = float(f"{km.group(1)}.{km.group(2)}")
            for a in in_window:
                if abs(num(a, "distance") / 1000 - want) < 0.12:
                    good = a.get("strava_id")
                    report.append((sid, "riparato", str(good or a.get("id")), want))
                    if good:
                        return f'href="https://www.strava.com/activities/{good}"'
                    return f'href="https://intervals.icu/activities/{a["id"]}"'
        report.append((sid, "rimosso", "", 0))
        return 'data-broken="' + sid + '" href="#"'

    out = LINK_RE.sub(one, txt)
    # un href="#" residuo vuol dire anchor da smontare: si tiene solo il testo
    if 'data-broken' in out:
        out = re.sub(r'<a class="strava-inline" data-broken="\d+" href="#"[^>]*>(.*?)'
                     r'<span class="strava-mark">.*?</span></a>', r"\1", out, flags=re.S)
    return out, report


def annotate_links(txt, by_sid):
    """Aggiunge al link il titolo dell'attività: data, tipo, km, kJ.

    Il testo del link è prosa ("i 34,3 km dell'Oude Farnomont"); il `title` è il
    dato. Sono due cose diverse e la prima non deve fingere di essere la seconda.
    """
    def one(m):
        a = by_sid.get(m.group(1))
        if not a:
            return m.group(0)
        bits = [day(a), a.get("type") or "?"]
        if num(a, "distance"):
            bits.append(f"{num(a, 'distance') / 1000:.1f} km".replace(".", ","))
        if num(a, "total_elevation_gain"):
            bits.append(f"{int(num(a, 'total_elevation_gain'))} m")
        if num(a, "icu_joules"):
            bits.append(f"{int(round(num(a, 'icu_joules') / 1000))} kJ")
        return m.group(0) + ' title="' + htmlmod.escape(" · ".join(bits)) + '"'
    return LINK_RE.sub(one, txt)


# -------------------------------------------------------------- formattazione

def it(n, dec=0):
    """1234.5 -> '1.234,5' — punto migliaia, virgola decimale."""
    s = f"{n:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def hhmm(secs):
    h, m = divmod(int(secs) // 60, 60)
    return f"{h}h{m:02d}"


def data_it(iso):
    """'2023-04-11' -> '11 aprile 2023'. La pagina è in italiano, le date pure."""
    y, m, d = iso.split("-")
    return f"{int(d)} {MESI[int(m) - 1]} {y}"


def mese_it(key):
    y, m = key.split("-")
    return f"{MESI[int(m) - 1].capitalize()} {y}"


def esc(s):
    return htmlmod.escape(s or "", quote=True)


# --------------------------------------------------------------- costruzione

def build(acts, ed, args):
    era0 = ed["era_start"]
    era = [a for a in acts if day(a) >= era0]
    pre = [a for a in acts if day(a) < era0]
    gaps = find_gaps(acts)
    hole = max(gaps, key=lambda g: g[2]) if gaps else None
    rings = ring_crossings(era)
    load0 = first_real_load(acts)

    first = datetime.date.fromisoformat(day(era[0]))
    last = datetime.date.fromisoformat(day(era[-1]))
    mkeys = months_span(first, last)
    mb = bucket_by(era, lambda a: day(a)[:7])

    tot = Bucket("tot")
    for a in era:
        tot.add(a)

    # settimane -> mese di appartenenza. Una settimana a cavallo di due mesi va
    # al mese che ne contiene il lunedì: la scena parla di quella settimana, e
    # spezzarla in due sarebbe peggio che assegnarla una volta sola.
    weeks_by_month = collections.defaultdict(list)
    for w in ed["weeks"]:
        weeks_by_month[w["start"][:7]].append(w)

    rings_by_month = collections.defaultdict(list)
    for r in rings:
        rings_by_month[r[1][:7]].append(r)

    by_sid = {str(a["strava_id"]): a for a in acts if a.get("strava_id")}
    link_report = []

    # prosa: link verificati, riparati o smontati, poi annotati
    for w in ed["weeks"]:
        win = [a for a in era if w["start"] <= day(a) <= w["end"]]
        w["_html"], rep = fix_prose_links(w["html"], by_sid, win)
        w["_html"] = annotate_links(w["_html"], by_sid)
        link_report += [(w["n"],) + r for r in rep]
    for r in ed["rings"]:
        for c in r["chapters"]:
            c["_html"], rep = fix_prose_links(c["html"], by_sid, era)
            c["_html"] = annotate_links(c["_html"], by_sid)
            link_report += [("anello %d" % r["n"],) + x for x in rep]

    return dict(acts=acts, era=era, pre=pre, gaps=gaps, hole=hole, rings=rings,
                load0=load0, mkeys=mkeys, mb=mb, tot=tot, ed=ed,
                weeks_by_month=weeks_by_month, rings_by_month=rings_by_month,
                by_sid=by_sid, link_report=link_report, era0=era0,
                first=first, last=last)


# ------------------------------------------------------------------ la pagina

CSS = """
:root{
  --bg:#faf6ed; --paper:#fffdf6; --ink:#2a2317; --gold:#b8860b;
  --gold-soft:rgba(184,134,11,.12); --rule:#d4c8a8; --muted:#6b5f48; --accent:#8b2e1f;
  /* Due sole tinte portano dato: oro (energia, distanza, tutto ciò che si accumula)
     e amaranto (carico). Validate con lo script del riferimento dataviz contro
     --paper #fffdf6: banda di luminosità, croma, separazione CVD, contrasto — tutte
     passate. Una terza serie non entra: i grafici sono piccoli multipli a una serie
     ciascuno, apposta per non doverne mai cercare una. */
  --s1:#b8860b; --s2:#8b2e1f;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:var(--bg);color:var(--ink)}
body{font-family:'EB Garamond',Georgia,serif;font-size:19px;line-height:1.7;
  max-width:760px;margin:0 auto;padding:56px 24px 100px}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:-1;
  background-image:radial-gradient(circle at 25% 30%,rgba(184,134,11,.04) 0,transparent 40%),
    radial-gradient(circle at 75% 70%,rgba(139,46,31,.03) 0,transparent 35%)}
h1.book-main{font-family:'Cinzel',serif;font-size:2.6rem;font-weight:700;letter-spacing:.04em;
  text-align:center;line-height:1.15}
h1.book-main .accent{color:var(--gold);display:block;font-size:.6em;letter-spacing:.18em;
  text-transform:uppercase;margin-bottom:8px}
.subtitle{font-style:italic;text-align:center;color:var(--muted);font-size:1.08rem;
  margin:18px auto 40px;max-width:620px}
.ornament{text-align:center;color:var(--gold);margin:30px 0 20px;font-size:1.3rem;letter-spacing:1em}
.card{background:var(--paper);border:1px solid var(--rule);border-radius:4px;padding:26px 24px;margin:34px 0}
.card>h2,.card>h3{font-family:'Cinzel',serif;font-size:.85rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--gold);text-align:center;margin-bottom:20px;font-weight:600}
.feat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:18px 22px}
.feat{text-align:center}
.feat .num{font-family:'Cinzel',serif;font-size:1.9rem;color:var(--gold);font-weight:700;line-height:1}
.feat .label{font-family:'IBM Plex Mono',monospace;font-size:.68rem;text-transform:uppercase;
  letter-spacing:.1em;color:var(--muted);margin-top:6px}
.feat .note{font-size:.82rem;color:var(--muted);font-style:italic;margin-top:4px}
.ring-bar{display:flex;gap:9px;justify-content:center;margin-top:14px;flex-wrap:wrap}
.ring-pill{width:36px;height:36px;border-radius:50%;border:2px solid var(--gold);display:flex;
  align-items:center;justify-content:center;font-family:'Cinzel',serif;font-size:.8rem;
  color:var(--gold);background:var(--paper);position:relative}
.ring-pill.forged{background:linear-gradient(135deg,var(--gold) 0,#d4a843 50%,var(--gold) 100%);color:var(--paper)}
.ring-pill.partial{background:conic-gradient(var(--gold) calc(var(--p)*1%),var(--paper) 0)}
.ring-pill.partial::after{content:attr(data-pct) "%";font-size:.55rem;position:absolute;
  bottom:-16px;color:var(--muted);letter-spacing:.05em}
.nota{border-left:3px solid var(--accent);padding:4px 0 4px 20px;margin:34px 0;
  font-size:.95rem;color:#3a3220}
.nota strong{font-family:'Cinzel',serif;font-size:.8rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--accent);display:block;margin-bottom:6px}
.nota ul{margin:8px 0 0 18px}
.nota li{margin-bottom:6px}
.prologue{font-style:italic;border-left:3px solid var(--gold);padding:8px 0 8px 22px;margin:34px 0;color:#3a3220}
/* indice dei mesi: una riga per anno, un quadretto per mese, scuro = mese pieno */
.year-index{margin:8px 0 0}
.year-row{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.year-row .y{font-family:'IBM Plex Mono',monospace;font-size:.72rem;color:var(--muted);width:38px}
a.mchip{font-family:'IBM Plex Mono',monospace;font-size:.66rem;text-decoration:none;
  color:var(--muted);border:1px solid var(--rule);border-radius:3px;padding:2px 5px;background:var(--paper)}
a.mchip:hover{border-color:var(--gold);color:var(--gold)}
a.mchip.on{background:var(--gold-soft);color:#6b4a05;border-color:var(--gold)}
a.mchip.ring{border-color:var(--gold);box-shadow:inset 0 -2px 0 var(--gold)}
a.mchip.void{opacity:.4}
/* grafici */
.chart{margin:22px 0 6px}
.chart h4{font-family:'Cinzel',serif;font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin-bottom:2px;font-weight:600}
.chart .sub{font-size:.8rem;color:var(--muted);font-style:italic;margin-bottom:6px}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart details{margin-top:4px}
.chart summary{font-family:'IBM Plex Mono',monospace;font-size:.66rem;color:var(--muted);cursor:pointer}
table.data{width:100%;border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:.66rem;margin-top:6px}
table.data th,table.data td{border-bottom:1px solid var(--rule);padding:2px 4px;text-align:right}
table.data th:first-child,table.data td:first-child{text-align:left}
/* mese */
.month{margin:54px 0 0;scroll-margin-top:14px}
.month>h2{font-family:'Cinzel',serif;font-size:1.5rem;letter-spacing:.06em;color:var(--accent);
  border-bottom:2px solid var(--gold);padding-bottom:8px;display:flex;justify-content:space-between;
  align-items:baseline;gap:12px;flex-wrap:wrap}
.month>h2 .mkj{font-family:'IBM Plex Mono',monospace;font-size:.72rem;letter-spacing:.1em;color:var(--gold)}
.month.void>h2{color:var(--muted);border-bottom-color:var(--rule)}
.strip{font-family:'IBM Plex Mono',monospace;font-size:.72rem;letter-spacing:.04em;color:var(--muted);
  background:var(--paper);border:1px solid var(--rule);border-radius:3px;padding:8px 10px;margin:12px 0}
.strip b{color:var(--ink);font-weight:600}
.ring-mark{background:var(--gold-soft);border:1px solid var(--gold);border-radius:4px;
  padding:14px 18px;margin:20px 0}
.ring-mark .lede{font-family:'Cinzel',serif;font-size:.76rem;letter-spacing:.14em;
  text-transform:uppercase;color:#6b4a05;margin-bottom:8px}
.ring-mark h3{font-family:'Cinzel',serif;font-size:1.05rem;color:var(--accent);margin-bottom:10px}
.scene{margin:22px 0}
.scene .head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
  border-bottom:1px dotted var(--rule);padding-bottom:4px;margin-bottom:8px}
.scene .wk{font-family:'IBM Plex Mono',monospace;font-size:.66rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted)}
.scene h3{font-family:'Cinzel',serif;font-size:1.08rem;color:var(--ink);margin-bottom:6px}
.scene .body p{margin-bottom:12px}
.scene .wstrip{font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:var(--muted);
  border-left:2px solid var(--gold);padding-left:10px}
h3.chapter-title{font-family:'Cinzel',serif;font-size:1.05rem;color:var(--ink);margin:14px 0 6px}
a.strava-inline{color:var(--accent);text-decoration:none;
  background-image:linear-gradient(transparent 60%,var(--gold-soft) 60%);padding:0 1px}
a.strava-inline:hover{color:var(--gold)}
a.strava-inline .strava-mark{font-family:'IBM Plex Mono',monospace;font-size:.7em;color:var(--gold);
  margin-left:2px;opacity:.6}
/* attività */
details.acts{margin:16px 0 0}
details.acts>summary{font-family:'Cinzel',serif;font-size:.78rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--gold);cursor:pointer;padding:6px 0;border-top:1px solid var(--rule)}
details.act{border-bottom:1px solid var(--rule);background:var(--paper)}
details.act>summary{cursor:pointer;padding:6px 8px;font-size:.84rem;display:flex;gap:8px;
  align-items:baseline;flex-wrap:wrap;list-style:none}
details.act>summary::-webkit-details-marker{display:none}
details.act>summary:hover{background:var(--gold-soft)}
details.act .d{font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:var(--muted);width:78px;flex:0 0 auto}
details.act .t{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--accent);width:96px;flex:0 0 auto}
details.act .nm{flex:1 1 180px;min-width:0}
details.act .q{font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:var(--muted);flex:0 0 auto}
details.act[open]>summary{background:var(--gold-soft)}
.actbody{padding:10px 12px 16px}
.statgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px 14px;
  font-family:'IBM Plex Mono',monospace;font-size:.68rem}
.statgrid div{display:flex;justify-content:space-between;gap:6px;border-bottom:1px dotted var(--rule);padding:1px 0}
.statgrid .k{color:var(--muted)}
.statgrid .v{color:var(--ink);font-weight:600;text-align:right}
.actnote{font-style:italic;font-size:.88rem;color:#3a3220;margin:10px 0 0;white-space:pre-wrap}
.actlinks{margin-top:10px;display:flex;gap:12px;flex-wrap:wrap}
.actlinks a{font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:var(--accent);
  text-decoration:none;border:1px solid var(--rule);border-radius:3px;padding:3px 8px;background:var(--bg)}
.actlinks a:hover{border-color:var(--gold);color:var(--gold)}
.zbar{display:flex;height:8px;margin:10px 0 2px;border-radius:2px;overflow:hidden;gap:2px}
.zbar i{display:block;height:100%}
.compagnia li{padding:7px 0;border-bottom:1px dashed var(--rule);list-style:none;font-size:.94rem}
.colophon{margin-top:60px;padding-top:16px;border-top:1px solid var(--rule);
  font-family:'IBM Plex Mono',monospace;font-size:.66rem;color:var(--muted);text-align:center}
.colophon a{color:var(--accent)}
.reveal{opacity:0;transform:translateY(18px);
  transition:opacity .7s cubic-bezier(.16,1,.3,1),transform .7s cubic-bezier(.16,1,.3,1)}
.reveal.in{opacity:1;transform:none}
@media (max-width:560px){
  body{font-size:17px;padding:34px 14px 70px}
  h1.book-main{font-size:1.9rem}
  details.act .t{width:auto}
}
"""


def stat_strip(b, cmp_prev=None):
    """La riga di numeri di un mese. Solo misure, nessun aggettivo."""
    bits = [f"<b>{b.n}</b> attività"]
    if b.dist:
        bits.append(f"<b>{it(b.dist / 1000, 1)}</b> km")
    if b.up:
        bits.append(f"<b>{it(b.up)}</b> m D+")
    if b.mov:
        bits.append(f"<b>{hhmm(b.mov)}</b>")
    if b.kj:
        bits.append(f"<b>{it(b.kj / 1000)}</b> kJ")
    if b.tl:
        bits.append(f"TL <b>{it(b.tl)}</b>")
    top = " · ".join(f"{k} {v}" for k, v in b.types.most_common(4))
    return f'<div class="strip">{" · ".join(bits)}<br>{esc(top)}</div>'


def month_section(mkey, D):
    b = D["mb"].get(mkey)
    void = b is None
    rings_here = D["rings_by_month"].get(mkey, [])
    weeks_here = sorted(D["weeks_by_month"].get(mkey, []), key=lambda w: w["start"])
    out = [f'<section class="month{" void" if void else ""} reveal" id="m-{mkey}">']
    kjnote = f'<span class="mkj">{it(b.kj / 1000)} kJ</span>' if b and b.kj else ""
    out.append(f'<h2>{mese_it(mkey)}{kjnote}</h2>')
    if void:
        out.append('<p class="strip">Nessuna attività registrata in questo mese. '
                   'Il mese resta in pagina: cancellarlo darebbe una continuità che non c\'è.</p>')
        out.append("</section>")
        return "\n".join(out)

    out.append(stat_strip(b))

    for n, date, cum, aid, aname in rings_here:
        ed_ring = next((r for r in D["ed"]["rings"] if r["n"] == n), None)
        out.append('<div class="ring-mark">')
        out.append(f'<div class="lede">Anello {ROMAN[n] if n < len(ROMAN) else n} '
                   f'— forgiato il {data_it(date)}, a {it(n * RING_KJ)} kJ '
                   f'(contatore: {it(cum)} kJ)</div>')
        if ed_ring:
            out.append(f'<h3>{esc(ed_ring["title"].split("—", 1)[-1].strip())}</h3>')
            for c in ed_ring["chapters"]:
                out.append(f'<h3 class="chapter-title">{esc(c["title"])}</h3>')
                out.append(c.get("_html", c["html"]))
        else:
            out.append('<p>Anello chiuso: il racconto di questo tratto non è ancora scritto.</p>')
        out.append("</div>")

    for w in weeks_here:
        a, bd = w["start"], w["end"]
        wa = [x for x in D["era"] if a <= day(x) <= bd]
        wb = Bucket(a)
        for x in wa:
            wb.add(x)
        span = f"{int(a[8:10])}–{int(bd[8:10])} {MESI[int(bd[5:7]) - 1]} {bd[:4]}"
        out.append('<article class="scene reveal">')
        out.append(f'<div class="head"><span class="wk">Settimana {w["n"]} · {span}</span>'
                   f'<span>{w["mood"]}</span></div>')
        out.append(f'<h3>{esc(w["title"])}</h3>')
        out.append(f'<div class="body">{w.get("_html", w["html"])}</div>')
        st = [f"{wb.n} attività"]
        if wb.dist:
            st.append(f"{it(wb.dist / 1000, 1)} km")
        if wb.up:
            st.append(f"{it(wb.up)} m D+")
        if wb.mov:
            st.append(hhmm(wb.mov))
        if wb.kj:
            st.append(f"{it(wb.kj / 1000)} kJ")
        if wb.tl:
            st.append(f"TL {it(wb.tl)}")
        out.append(f'<div class="wstrip">{" · ".join(st)}</div>')
        out.append("</article>")

    out.append(f'<details class="acts" data-month="{mkey}">'
               f'<summary>Tutte le {b.n} attività di {mese_it(mkey).lower()}, '
               f'con ogni statistica che Intervals espone</summary>'
               f'<div class="actlist"></div></details>')
    out.append("</section>")
    return "\n".join(out)


PAGE_JS = r"""
(function(){
  var D = SIGNORE, K = {};
  D.keys.forEach(function(k,i){ K[k]=i; });
  var g = function(r,k){ return r[K[k]]; };
  var it0 = function(v){ return v==null?"—":Number(v).toLocaleString("it-IT"); };
  var it1 = function(v){ return v==null?"—":Number(v).toLocaleString("it-IT",{minimumFractionDigits:1,maximumFractionDigits:1}); };
  var it2 = function(v){ return v==null?"—":Number(v).toLocaleString("it-IT",{minimumFractionDigits:2,maximumFractionDigits:2}); };
  var hm  = function(s){ if(s==null) return "—"; s=Math.round(s); var h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;
                         return h? h+"h"+String(m).padStart(2,"0") : m+"'"+String(x).padStart(2,"0")+"\""; };
  var SVG = "http://www.w3.org/2000/svg";
  function el(t,a,txt){ var n=document.createElementNS(SVG,t); for(var k in a) n.setAttribute(k,a[k]);
                        if(txt!=null) n.textContent=txt; return n; }

  /* ---------------------------------------------------------------- grafici
     Piccoli multipli a una serie sola: ogni misura ha il suo riquadro, così
     nessun grafico ha mai bisogno di due assi né di una tavolozza categorica.
     La gronda dell'asse y si calcola dall'etichetta più larga (~4.85px per
     glifo IBM Plex Mono a 8px): fissarla taglia "50.000" o spreca un decimo
     della larghezza sui numeri a due cifre. */
  var GLYPH = 4.85, W = 720, H = 150, PAD_B = 20, PAD_T = 10;
  function ticks(max){
    if(max<=0) return [0];
    var step = Math.pow(10, Math.floor(Math.log10(max)));
    if(max/step < 2) step/=5; else if(max/step < 5) step/=2;
    var out=[], v=0; while(v<=max+1e-9){ out.push(v); v+=step; }
    if(out.length>7){ out=out.filter(function(_,i){ return i%2===0; }); }
    return out;
  }
  function bars(host, spec){
    var vals = spec.values, max = Math.max.apply(null, vals.concat([0]));
    var tk = ticks(max), lab = tk.map(spec.fmt);
    var gut = Math.max.apply(null, lab.map(function(s){ return s.length*GLYPH; })) + 6;
    var svg = el("svg",{viewBox:"0 0 "+W+" "+H, role:"img", "aria-label":spec.title});
    var x0 = gut, x1 = W-2, y0 = PAD_T, y1 = H-PAD_B;
    var sx = function(i){ return x0 + (x1-x0)*i/vals.length; };
    var sy = function(v){ return max? y1-(y1-y0)*v/max : y1; };
    tk.forEach(function(t,i){
      svg.appendChild(el("line",{x1:x0,x2:x1,y1:sy(t),y2:sy(t),stroke:"#d4c8a8","stroke-width":t?0.5:1}));
      svg.appendChild(el("text",{x:x0-4,y:sy(t)+3,"text-anchor":"end","font-size":8,
        "font-family":"IBM Plex Mono, monospace",fill:"#6b5f48"}, lab[i]));
    });
    var bw = Math.max(1,(x1-x0)/vals.length - 2);
    vals.forEach(function(v,i){
      if(v==null||v<=0) return;
      var h = y1-sy(v);
      var r = el("rect",{x:sx(i)+1,y:sy(v),width:bw,height:Math.max(h,0.6),
                         fill:spec.color||"#b8860b",rx:Math.min(2,bw/2)});
      r.appendChild(el("title",null, spec.labels[i]+" — "+spec.fmt(v)+" "+(spec.unit||"")));
      svg.appendChild(r);
    });
    (spec.marks||[]).forEach(function(m){
      var ln = el("line",{x1:sx(m.i)+bw/2,x2:sx(m.i)+bw/2,y1:y0,y2:y1,stroke:"#8b2e1f",
                          "stroke-width":1,"stroke-dasharray":"2 3"});
      ln.appendChild(el("title",null,m.label)); svg.appendChild(ln);
    });
    /* etichette x: una ogni sei mesi, che è il passo più fitto che non si tocca */
    for(var i=0;i<vals.length;i+=6){
      svg.appendChild(el("text",{x:sx(i)+bw/2,y:H-6,"text-anchor":"middle","font-size":8,
        "font-family":"IBM Plex Mono, monospace",fill:"#6b5f48"}, spec.labels[i]));
    }
    host.appendChild(svg);
    var d = document.createElement("details");
    var s = document.createElement("summary"); s.textContent = "i numeri di questo grafico";
    var t = document.createElement("table"); t.className="data";
    var rows = ["<tr><th>mese</th><th>"+spec.title+"</th></tr>"];
    vals.forEach(function(v,i){ rows.push("<tr><td>"+spec.labels[i]+"</td><td>"+(v==null?"—":spec.fmt(v))+"</td></tr>"); });
    t.innerHTML = rows.join("");
    d.appendChild(s); d.appendChild(t); host.appendChild(d);
    return svg;
  }
  function line(host, spec){
    var vals = spec.values, max = Math.max.apply(null, vals.concat([0]));
    var tk = ticks(max), lab = tk.map(spec.fmt);
    var gut = Math.max.apply(null, lab.map(function(s){ return s.length*GLYPH; })) + 6;
    var svg = el("svg",{viewBox:"0 0 "+W+" "+H, role:"img", "aria-label":spec.title});
    var x0=gut, x1=W-2, y0=PAD_T, y1=H-PAD_B;
    var sx=function(i){ return vals.length<2? x0 : x0+(x1-x0)*i/(vals.length-1); };
    var sy=function(v){ return max? y1-(y1-y0)*v/max : y1; };
    tk.forEach(function(t,i){
      svg.appendChild(el("line",{x1:x0,x2:x1,y1:sy(t),y2:sy(t),stroke:"#d4c8a8","stroke-width":t?0.5:1}));
      svg.appendChild(el("text",{x:x0-4,y:sy(t)+3,"text-anchor":"end","font-size":8,
        "font-family":"IBM Plex Mono, monospace",fill:"#6b5f48"}, lab[i]));
    });
    (spec.thresholds||[]).forEach(function(t){
      if(t.v>max) return;
      svg.appendChild(el("line",{x1:x0,x2:x1,y1:sy(t.v),y2:sy(t.v),stroke:"#8b2e1f",
        "stroke-width":0.5,"stroke-dasharray":"3 3",opacity:0.5}));
    });
    var d = vals.map(function(v,i){ return (i?"L":"M")+sx(i).toFixed(1)+" "+sy(v).toFixed(1); }).join(" ");
    svg.appendChild(el("path",{d:d,fill:"none",stroke:spec.color||"#b8860b","stroke-width":2,
      "stroke-linejoin":"round"}));
    (spec.points||[]).forEach(function(p){
      var c = el("circle",{cx:sx(p.i),cy:sy(p.v),r:3.2,fill:"#fffdf6",stroke:"#8b2e1f","stroke-width":2});
      c.appendChild(el("title",null,p.label)); svg.appendChild(c);
    });
    for(var i=0;i<vals.length;i+=6){
      svg.appendChild(el("text",{x:sx(i),y:H-6,"text-anchor":"middle","font-size":8,
        "font-family":"IBM Plex Mono, monospace",fill:"#6b5f48"}, spec.labels[i]));
    }
    host.appendChild(svg);
    var det = document.createElement("details");
    var s = document.createElement("summary"); s.textContent="i numeri di questo grafico";
    var t = document.createElement("table"); t.className="data";
    var rows=["<tr><th>mese</th><th>"+spec.title+"</th></tr>"];
    vals.forEach(function(v,i){ rows.push("<tr><td>"+spec.labels[i]+"</td><td>"+spec.fmt(v)+"</td></tr>"); });
    t.innerHTML = rows.join("");
    det.appendChild(s); det.appendChild(t); host.appendChild(det);
    return svg;
  }

  /* ------------------------------------------------------ la scheda attività
     Ogni voce che l'API riempie davvero, con la sua unità. Chi non c'è non
     compare: una griglia piena di trattini fa sembrare rotto un archivio che
     invece semplicemente non misurava la potenza nel 2023. */
  var FIELDS = [
    ["Ora di partenza", function(r){ return g(r,"time")||null; }],
    ["Tempo in movimento", function(r){ return hm(g(r,"mov")); }, "mov"],
    ["Tempo trascorso",  function(r){ return hm(g(r,"ela")); }, "ela"],
    ["Distanza", function(r){ return it2(g(r,"dist")/1000)+" km"; }, "dist"],
    ["Dislivello +", function(r){ return it0(g(r,"up"))+" m"; }, "up"],
    ["Dislivello −", function(r){ return it0(g(r,"down"))+" m"; }, "down"],
    ["Quota min", function(r){ return it0(g(r,"altmin"))+" m"; }, "altmin"],
    ["Quota max", function(r){ return it0(g(r,"altmax"))+" m"; }, "altmax"],
    ["Velocità media", function(r){ return it1(g(r,"spd")*3.6)+" km/h"; }, "spd"],
    ["Velocità max", function(r){ return it1(g(r,"spdmax")*3.6)+" km/h"; }, "spdmax"],
    ["Passo medio", function(r){ var s=g(r,"spd"); if(!s) return null;
        var p=1000/s; return Math.floor(p/60)+"'"+String(Math.round(p%60)).padStart(2,"0")+"\"/km"; }, "spd"],
    ["Cadenza media", function(r){ return it0(g(r,"cad")); }, "cad"],
    ["FC media", function(r){ return it0(g(r,"hr"))+" bpm"; }, "hr"],
    ["FC max", function(r){ return it0(g(r,"hrmax"))+" bpm"; }, "hrmax"],
    ["FC a riposo", function(r){ return it0(g(r,"hrrest"))+" bpm"; }, "hrrest"],
    ["LTHR", function(r){ return it0(g(r,"lthr"))+" bpm"; }, "lthr"],
    ["Potenza media", function(r){ return it0(g(r,"w"))+" W"; }, "w"],
    ["Potenza normalizzata", function(r){ return it0(g(r,"np"))+" W"; }, "np"],
    ["FTP del giorno", function(r){ return it0(g(r,"ftp"))+" W"; }, "ftp"],
    ["Indice di variabilità", function(r){ return it2(g(r,"vi")); }, "vi"],
    ["Efficienza (EF)", function(r){ return it2(g(r,"ef")); }, "ef"],
    ["Decoupling", function(r){ return it1(g(r,"dec"))+" %"; }, "dec"],
    ["Indice di polarizzazione", function(r){ return it2(g(r,"pol")); }, "pol"],
    ["Lavoro", function(r){ return it0(g(r,"kj"))+" kJ"; }, "kj"],
    ["Lavoro sopra FTP", function(r){ return it0(g(r,"kjftp"))+" kJ"; }, "kjftp"],
    ["Calorie", function(r){ return it0(g(r,"kcal"))+" kcal"; }, "kcal"],
    ["Carboidrati usati", function(r){ return it0(g(r,"carb"))+" g"; }, "carb"],
    ["Carico (TL)", function(r){ return it0(g(r,"tl")); }, "tl"],
    ["Intensità", function(r){ return it0(g(r,"int"))+" %"; }, "int"],
    ["TRIMP", function(r){ return it0(g(r,"trimp")); }, "trimp"],
    ["Strain", function(r){ return it0(g(r,"strain")); }, "strain"],
    ["Forma (CTL)", function(r){ return it1(g(r,"ctl")); }, "ctl"],
    ["Fatica (ATL)", function(r){ return it1(g(r,"atl")); }, "atl"],
    ["Temperatura media", function(r){ return it1(g(r,"temp"))+" °C"; }, "temp"],
    ["Dispositivo", function(r){ return g(r,"dev"); }, "dev"],
    ["Sorgente", function(r){ return g(r,"src"); }, "src"],
    ["Attrezzatura", function(r){ return g(r,"gear"); }, "gear"],
    ["Gara", function(r){ return g(r,"race")?"sì":null; }, "race"],
    ["Casa-lavoro", function(r){ return g(r,"commute")?"sì":null; }, "commute"]
  ];
  var ZC = ["#e8dcc0","#d9c88f","#c9ad55","#b8860b","#a1651a","#8b2e1f","#6d2318"];

  function card(r){
    var box = document.createElement("div"); box.className="actbody";
    var grid = document.createElement("div"); grid.className="statgrid";
    var shown = 0;
    FIELDS.forEach(function(f){
      if(f[2]!==undefined){ var raw=g(r,f[2]); if(raw==null||raw==="") return; }
      var v; try { v = f[1](r); } catch(e){ v = null; }
      if(v==null||v==="") return;
      var d=document.createElement("div");
      var a=document.createElement("span"); a.className="k"; a.textContent=f[0];
      var b=document.createElement("span"); b.className="v"; b.textContent=v;
      d.appendChild(a); d.appendChild(b); grid.appendChild(d); shown++;
    });
    box.appendChild(grid);
    box.dataset.stats = shown;
    var z = g(r,"hrz");
    if(z && z.length){
      var tot = z.reduce(function(a,b){ return a+b; },0);
      if(tot>0){
        var bar=document.createElement("div"); bar.className="zbar";
        z.forEach(function(s,i){
          if(!s) return;
          var i2=document.createElement("i");
          i2.style.width=(100*s/tot)+"%"; i2.style.background=ZC[i]||ZC[6];
          i2.title="Zona FC "+(i+1)+": "+hm(s);
          bar.appendChild(i2);
        });
        box.appendChild(bar);
        var cap=document.createElement("div"); cap.className="statgrid";
        var d2=document.createElement("div");
        var k2=document.createElement("span"); k2.className="k"; k2.textContent="Tempo in zona FC";
        var v2=document.createElement("span"); v2.className="v"; v2.textContent="Z1→Z7 · "+hm(tot);
        d2.appendChild(k2); d2.appendChild(v2); cap.appendChild(d2); box.appendChild(cap);
      }
    }
    var desc = g(r,"desc");
    if(desc){ var p=document.createElement("p"); p.className="actnote"; p.textContent=desc; box.appendChild(p); }
    var id = g(r,"id"), sid = g(r,"sid");
    if(!id){
      var w=document.createElement("p"); w.className="actnote";
      w.textContent="Intervals.icu elenca questa attività ma non ne espone i dati "+
        "(«STRAVA activities are not available via the API»): resta in pagina, con il suo link, "+
        "e non aggiunge nulla ai totali.";
      box.appendChild(w);
    }
    var links=document.createElement("div"); links.className="actlinks";
    function link(href,txt,dim){
      var a=document.createElement("a"); a.href=href; a.target="_blank"; a.rel="noopener";
      a.textContent=txt; if(dim) a.style.opacity=".55"; links.appendChild(a);
    }
    if(id)  link("https://intervals.icu/activities/"+id, "intervals.icu ↗");
    if(sid) link("https://www.strava.com/activities/"+sid, "Strava ↗");
    if(id && !sid) link("https://intervals.icu/activities/"+id,
                        "nessun id Strava su questa attività", true);
    box.appendChild(links);
    return box;
  }
  function actRow(r){
    var d = document.createElement("details"); d.className="act";
    var s = document.createElement("summary");
    var a=document.createElement("span"); a.className="d"; a.textContent=g(r,"date").slice(5);
    var b=document.createElement("span"); b.className="t"; b.textContent=g(r,"type");
    var c=document.createElement("span"); c.className="nm"; c.textContent=g(r,"name")||"(senza nome)";
    var q=document.createElement("span"); q.className="q";
    var bits=[];
    if(g(r,"dist")) bits.push(it1(g(r,"dist")/1000)+" km");
    if(g(r,"up"))   bits.push(it0(g(r,"up"))+" m");
    if(g(r,"kj"))   bits.push(it0(g(r,"kj"))+" kJ");
    if(g(r,"tl"))   bits.push("TL "+it0(g(r,"tl")));
    q.textContent = bits.join(" · ");
    s.appendChild(a); s.appendChild(b); s.appendChild(c); s.appendChild(q);
    d.appendChild(s);
    var filled=false;
    d.addEventListener("toggle", function(){ if(d.open && !filled){ filled=true; d.appendChild(card(r)); } });
    d._fill = function(){ if(!filled){ filled=true; d.appendChild(card(r)); } return d; };
    return d;
  }

  /* ------------------------------------------------------------------ mount */
  var MOUNTED = {}, CHARTS = [];
  function mountMonths(){
    D.months.forEach(function(m){
      var host = document.querySelector('details.acts[data-month="'+m[0]+'"] .actlist');
      if(!host) return;
      var list = [];
      for(var i=m[1]; i<=m[2]; i++){ var n=actRow(D.acts[i]); host.appendChild(n); list.push(n); }
      MOUNTED[m[0]] = list;
    });
  }
  function mountCharts(){
    var lab = D.months.map(function(m){ return m[0]; });
    var kj  = D.months.map(function(m){ return m[3]; });
    var km  = D.months.map(function(m){ return m[4]; });
    var up  = D.months.map(function(m){ return m[5]; });
    var hrs = D.months.map(function(m){ return m[6]; });
    var tl  = D.months.map(function(m){ return m[7]; });
    var cum = [], s=0; kj.forEach(function(v){ s+=v; cum.push(s); });
    var idx = {}; lab.forEach(function(k,i){ idx[k]=i; });
    /* punti e linee vengono dallo stesso passaggio: se un anello cadesse fuori
       dall'arco dei mesi, sparirebbe da entrambi invece di disallinearli */
    var pts = [], marks = [];
    D.rings.forEach(function(r){
      var i = idx[r[1].slice(0,7)]; if(i===undefined) return;
      var t = "Anello "+r[0]+" — "+r[1]+" ("+Number(r[0]*D.ring_kj).toLocaleString("it-IT")+" kJ)";
      pts.push({i:i, v:cum[i], label:t}); marks.push({i:i, label:t});
    });
    var specs = [
      ["c-kj",  {title:"kJ per mese", values:kj, labels:lab, unit:"kJ", fmt:it0, marks:marks}],
      ["c-cum", {title:"kJ cumulativi", values:cum, labels:lab, fmt:it0, points:pts,
                 thresholds:D.rings.map(function(r){ return {v:r[0]*D.ring_kj}; })}, "line"],
      ["c-km",  {title:"chilometri per mese", values:km, labels:lab, unit:"km", fmt:it0}],
      ["c-up",  {title:"dislivello per mese", values:up, labels:lab, unit:"m", fmt:it0}],
      ["c-h",   {title:"ore in movimento per mese", values:hrs, labels:lab, unit:"h", fmt:it0}],
      ["c-tl",  {title:"carico (TL) per mese", values:tl, labels:lab, fmt:it0, color:"#8b2e1f"}]
    ];
    specs.forEach(function(sp){
      var host = document.getElementById(sp[0]); if(!host) return;
      var svg = (sp[2]==="line"? line : bars)(host, sp[1]);
      CHARTS.push([sp[1].title, svg, sp[1]]);
    });
  }
  mountMonths(); mountCharts();

  var io = window.IntersectionObserver ? new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add("in"); io.unobserve(e.target); } });
  },{rootMargin:"0px 0px -40px 0px",threshold:0.02}) : null;
  if(io) document.querySelectorAll(".reveal").forEach(function(n){ io.observe(n); });
  else document.querySelectorAll(".reveal").forEach(function(n){ n.classList.add("in"); });

  window.SIGNORE_VIEW = {D:D, K:K, MOUNTED:MOUNTED, CHARTS:CHARTS, card:card, actRow:actRow, g:g};
})();
"""


def render(D, gen):
    ed = D["ed"]
    tot, rings = D["tot"], D["rings"]
    forged = len(rings)
    kj_tot = tot.kj / 1000
    partial = int(round(100 * (kj_tot - forged * RING_KJ) / RING_KJ))
    hole = D["hole"]

    # payload: attività in ordine, e per ogni mese l'intervallo di indici + i suoi totali
    rows = [row(a) for a in D["era"]]
    idx = {}
    for i, a in enumerate(D["era"]):
        idx.setdefault(day(a)[:7], [i, i])[1] = i
    months = []
    for k in D["mkeys"]:
        b = D["mb"].get(k)
        i0, i1 = idx.get(k, [-1, -2])
        months.append([k, i0, i1,
                       int(round(b.kj / 1000)) if b else 0,
                       int(round(b.dist / 1000)) if b else 0,
                       int(round(b.up)) if b else 0,
                       int(round(b.mov / 3600)) if b else 0,
                       int(round(b.tl)) if b else 0])
    payload = {
        "gen": gen, "era": D["era0"], "ring_kj": RING_KJ, "keys": KEYS,
        "acts": rows, "months": months,
        "rings": [[n, d, c, i] for n, d, c, i, _ in rings],
        "gaps": D["gaps"], "hole": hole,
        "pre": [len(D["pre"]), day(D["pre"][0]) if D["pre"] else None,
                day(D["pre"][-1]) if D["pre"] else None],
        "load0": D["load0"],
        "sid_n": sum(1 for a in D["era"] if a.get("strava_id")),
        "ghost_n": sum(1 for a in D["era"] if not a.get("id")),
        # la prima attività *vera* che porta uno strava_id: le righe cieche non
        # contano, il loro id è uno strava_id per costruzione e falserebbe la data
        "sid_from": min((day(a) for a in D["acts"]
                         if a.get("strava_id") and a.get("id")), default=None),
    }

    # feature: cose che si contano, non che si sostengono
    everest, equator = 8848.0, 40075.0
    feats = [
        (str(forged), "Anelli forgiati", f"{it(kj_tot)} kJ · 1 anello / {it(RING_KJ)} kJ"),
        (it(tot.up / everest, 1) + "×", "Volte l'Everest", f"{it(tot.up)} m saliti"),
        (it(tot.dist / 1000 / equator, 2) + "×", "Giri equatoriali", f"{it(tot.dist / 1000)} km"),
        (str(len(D["mkeys"])), "Mesi di saga", f"{D['mkeys'][0]} → {D['mkeys'][-1]}"),
        (it(tot.mov / 86400, 1), "Giorni di moto", f"{it(tot.mov / 3600)} ore in movimento"),
        (it(tot.n), "Attività", f"{it(len({day(a) for a in D['era']}))} giorni con almeno un'uscita"),
    ]

    ring_pills = "".join(
        f'<div class="ring-pill forged" title="Anello {n}: forgiato il {d}">{ROMAN[n] if n < len(ROMAN) else n}</div>'
        for n, d, _c, _i, _nm in rings)
    ring_pills += (f'<div class="ring-pill partial" style="--p:{partial}" data-pct="{partial}" '
                   f'title="Anello {forged + 1} in forgiatura">⚒</div>')

    # indice: una riga per anno
    years = collections.OrderedDict()
    for k in D["mkeys"]:
        years.setdefault(k[:4], []).append(k)
    ring_months = {r[1][:7] for r in rings}
    index = []
    for y, ks in years.items():
        chips = []
        for k in ks:
            b = D["mb"].get(k)
            cls = "mchip" + (" on" if b else " void") + (" ring" if k in ring_months else "")
            ttl = (f"{b.n} attività · {it(b.kj / 1000)} kJ" if b else "nessuna attività")
            chips.append(f'<a class="{cls}" href="#m-{k}" title="{ttl}">{MESI[int(k[5:7]) - 1][:3]}</a>')
        index.append(f'<div class="year-row"><span class="y">{y}</span>{"".join(chips)}</div>')

    # discipline, ricalcolate: la tabella che nella vecchia pagina era prosa
    disc = collections.OrderedDict()
    for a in D["era"]:
        t = a.get("type") or "?"
        d = disc.setdefault(t, Bucket(t))
        d.add(a)
    drows = "".join(
        f"<tr><td>{esc(t)}</td><td>{it(b.n)}</td><td>{it(b.dist / 1000)}</td>"
        f"<td>{it(b.up)}</td><td>{it(b.mov / 3600)}</td><td>{it(b.kj / 1000)}</td></tr>"
        for t, b in sorted(disc.items(), key=lambda kv: -kv[1].n))

    # anni, ricalcolati
    yb = bucket_by(D["era"], lambda a: day(a)[:4])
    yrows = "".join(
        f"<tr><td>{y}</td><td>{it(b.n)}</td><td>{it(b.dist / 1000)}</td><td>{it(b.up)}</td>"
        f"<td>{it(b.mov / 3600)}</td><td>{it(b.kj / 1000)}</td><td>{it(b.tl)}</td></tr>"
        for y, b in yb.items())

    parts = [
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>Il Signore dei kJ · Michele Merelli</title>",
        f'<meta name="description" content="{esc(f"Dal {D['era0']} al {day(D['era'][-1])}: {it(tot.n)} attività, {it(kj_tot)} kJ, {it(tot.dist / 1000)} km e {it(tot.up)} m di dislivello, mese per mese, con ogni statistica e ogni link.")}">',
        '<link rel="canonical" href="https://micmer-git.github.io/signore-dei-kj.html">',
        '<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400'
        '&family=IBM+Plex+Mono:wght@400;600&family=Cinzel:wght@600;700&display=swap" rel="stylesheet">',
        f"<style>{CSS}</style>\n</head>\n<body>",
        '<h1 class="book-main"><span class="accent">la saga, mese per mese</span>Il Signore dei kJ</h1>',
        f'<p class="subtitle">Dall\'{data_it(D["era0"])} al {data_it(day(D["era"][-1]))} Michele Merelli ha forgiato '
        f'{it(kj_tot)} kJ in {it(tot.n)} sortite, {it(tot.dist / 1000)} km e {it(tot.up)} m di dislivello, '
        f'in {it(tot.mov / 3600)} ore. {forged} Anelli pieni, uno ogni {it(RING_KJ)} kJ. '
        f'Qui sotto ci sono tutti i {len(D["mkeys"])} mesi, tutte le attività e tutte le loro statistiche.</p>',
        '<div class="ornament">⚜ · ⚜ · ⚜</div>',
        '<section class="card reveal"><h2>Gli anelli e i sigilli</h2>',
        f'<div class="ring-bar" aria-label="{forged} anelli forgiati">{ring_pills}</div>',
        '<div class="feat-grid" style="margin-top:34px">',
    ]
    for n, lab, note in feats:
        parts.append(f'<div class="feat"><div class="num">{n}</div>'
                     f'<div class="label">{lab}</div><div class="note">{note}</div></div>')
    parts.append("</div></section>")

    # la nota d'archivio: prima dei grafici, perché condiziona come si leggono
    hole_txt = ""
    if hole:
        hole_txt = (f"<li><strong>{hole[0]} → {hole[1]}</strong> non contiene una sola attività: "
                    f"{hole[2]} giorni di <em>buco d'archivio</em>, non una pausa dall'allenamento. "
                    f"Per questo la saga comincia il {D['era0']}, il giorno in cui l'archivio riparte: "
                    f"nessun grafico di questa pagina attraversa quel vuoto.</li>")
    pre_n, pre_a, pre_b = len(D["pre"]), day(D["pre"][0]), day(D["pre"][-1])
    parts += [
        '<div class="nota"><strong>Che cosa c\'è dentro questi numeri</strong><ul>',
        hole_txt,
        f"<li>Prima del buco l'archivio tiene <strong>{it(pre_n)} attività</strong>, dal {pre_a} al {pre_b}. "
        f"Non sono contate qui e non vanno lette come zero: il <em>training load</em> diventa un dato "
        f"vero solo dal <strong>{D['load0']}</strong>, perché le importazioni Strava più vecchie arrivano "
        f"senza frequenza cardiaca né potenza e quindi con carico 0. Quegli anni sono allenamento non misurato, "
        f"non allenamento mancato.</li>",
        f"<li>Il campo <code>strava_id</code> compare solo da <strong>{payload['sid_from']}</strong>, "
        f"e nemmeno su tutte quelle dopo: "
        f"{it(payload['sid_n'])} delle {it(tot.n)} attività della saga hanno un link a Strava, "
        f"le altre linkano solo a Intervals.icu. Non è una scelta editoriale, è quello che l'API espone.</li>",
        f"<li><strong>{payload['ghost_n']} attività</strong> della saga sono righe cieche: "
        f"Intervals.icu le elenca ma risponde «STRAVA activities are not available via the API». "
        f"Non hanno tipo, nome né numeri, quindi contano come uscite ma non aggiungono un solo kJ "
        f"ai totali. Restano in pagina — cancellarle sarebbe più pulito e meno vero — e linkano "
        f"a Strava, che è dove i loro dati stanno davvero.</li>",
        f"<li>I <strong>{len(D['mkeys'])} mesi</strong> sono tutti in pagina"
        + (f", compresi i {len(D['mkeys']) - len(D['mb'])} senza una sola attività"
           if len(D["mkeys"]) > len(D["mb"]) else
           ", uno per uno, e in questo arco nessuno è vuoto")
        + f". L'anello si chiude nel giorno in cui il contatore cumulativo taglia la soglia: "
          f"è una data calcolata a ogni build, non assegnata a mano.</li>",
        "</ul></div>",
    ]

    parts += [
        '<section class="card reveal"><h2>La saga in sei misure, mese per mese</h2>',
        '<div class="chart"><h4>kJ per mese</h4><div class="sub">Le linee tratteggiate sono i mesi '
        'in cui si è chiuso un anello.</div><div id="c-kj"></div></div>',
        '<div class="chart"><h4>kJ cumulativi</h4><div class="sub">Ogni riga orizzontale è una soglia '
        'da 100.000 kJ; ogni punto è l\'anello nel mese in cui si è chiuso.</div><div id="c-cum"></div></div>',
        '<div class="chart"><h4>Chilometri per mese</h4><div id="c-km"></div></div>',
        '<div class="chart"><h4>Dislivello per mese</h4><div id="c-up"></div></div>',
        '<div class="chart"><h4>Ore in movimento per mese</h4><div id="c-h"></div></div>',
        '<div class="chart"><h4>Carico per mese</h4><div class="sub">Il carico è l\'unica misura '
        'in amaranto: non è un\'energia e non si somma alle altre.</div><div id="c-tl"></div></div>',
        "</section>",
        '<section class="card reveal"><h2>I mesi</h2>',
        '<div class="year-index">' + "".join(index) + "</div>",
        '<p style="font-size:.82rem;color:var(--muted);font-style:italic;margin-top:12px">'
        'Il bordo dorato segna i mesi in cui si è chiuso un anello; i mesi sbiaditi non hanno attività.</p>',
        "</section>",
    ]

    if ed["weeks"]:
        w0, w1 = ed["weeks"][0], ed["weeks"][-1]
        parts.append(
            f'<div class="prologue"><p>La saga si legge dall\'alto verso il basso, dal primo mese '
            f'all\'ultimo. Dentro ogni mese ci sono, in quest\'ordine: i suoi numeri, l\'anello se '
            f'in quel mese se n\'è chiuso uno, le scene settimanali che gli appartengono '
            f'({len(ed["weeks"])} in tutto, dal {w0["start"]} al {w1["end"]}), e infine tutte le sue '
            f'attività, ognuna apribile su ogni statistica che Intervals.icu registra. I mesi senza '
            f'racconto hanno comunque tutti i numeri e tutte le attività: il silenzio è del narratore, '
            f'non dell\'archivio.</p></div>')

    for k in D["mkeys"]:
        parts.append(month_section(k, D))

    if ed.get("compagnia"):
        parts.append('<section class="card reveal"><h3>La Compagnia</h3><ul class="compagnia">')
        parts += [f"<li>{li}</li>" for li in ed["compagnia"]]
        parts.append("</ul></section>")

    parts += [
        '<section class="card reveal"><h3>Per disciplina</h3>',
        '<table class="data"><thead><tr><th>Disciplina</th><th>Att.</th><th>km</th>'
        "<th>D+ m</th><th>ore</th><th>kJ</th></tr></thead><tbody>" + drows + "</tbody></table>",
        "</section>",
        '<section class="card reveal"><h3>Per anno</h3>',
        '<table class="data"><thead><tr><th>Anno</th><th>Att.</th><th>km</th><th>D+ m</th>'
        "<th>ore</th><th>kJ</th><th>TL</th></tr></thead><tbody>" + yrows + "</tbody></table>",
        "</section>",
        f'<div class="colophon">Generato il {gen} da <code>tools/build_signore.py</code> · '
        f'dati: <a href="https://intervals.icu" target="_blank" rel="noopener">intervals.icu</a> · '
        f'{it(tot.n)} attività, {len(KEYS)} campi ciascuna, tutto inline: nessuna richiesta a runtime. · '
        f'La vecchia pagina settimanale ora reindirizza qui.</div>',
        "<script>const SIGNORE=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";</script>",
        "<script>" + PAGE_JS + "</script>",
        "</body>\n</html>",
    ]
    return "\n".join(p for p in parts if p)


def render_alias(D, gen):
    """L'URL settimanale resta vivo, il contenuto no.

    È linkato da /vita, /diario-di-un-unno e /sogni-di-un-unno: toglierlo
    farebbe tre 404. Ma "tutto mensile" era la richiesta, e una seconda
    struttura è esattamente ciò che aveva fatto divergere le due pagine.
    """
    idx = "".join(f'<li><a href="signore-dei-kj.html#m-{k}">{mese_it(k)}</a></li>'
                  for k in D["mkeys"] if k in D["mb"])
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Il Signore dei kJ · settimanale → mensile</title>
<meta http-equiv="refresh" content="0; url=signore-dei-kj.html">
<link rel="canonical" href="https://micmer-git.github.io/signore-dei-kj.html">
<meta name="robots" content="noindex">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;1,400&family=Cinzel:wght@600&display=swap" rel="stylesheet">
<style>
 body{{background:#faf6ed;color:#2a2317;font-family:'EB Garamond',Georgia,serif;font-size:19px;
   line-height:1.7;max-width:640px;margin:0 auto;padding:80px 24px}}
 h1{{font-family:'Cinzel',serif;font-size:1.6rem;color:#8b2e1f;margin-bottom:18px}}
 a{{color:#8b2e1f}}
 ul{{columns:2;font-size:.85rem;margin-top:18px;list-style:none;padding:0}}
 li{{margin-bottom:2px}}
</style>
</head>
<body>
<h1>Il settimanale è diventato mensile</h1>
<p>Le {len(D['ed']['weeks'])} settimane non sono sparite: ora vivono dentro il mese a cui
appartengono, in <a href="signore-dei-kj.html"><strong>Il Signore dei kJ</strong></a>, insieme ai
numeri di quel mese e a tutte le sue attività. Una pagina sola, una sola routine che la costruisce
({len(D['mkeys'])} mesi, {D['mkeys'][0]} → {D['mkeys'][-1]}).</p>
<p>Se il browser non ti ha già portato là: <a href="signore-dei-kj.html">vai alla saga mensile ↗</a>.</p>
<ul>{idx}</ul>
<p style="font-size:.7rem;color:#6b5f48;margin-top:40px">Generato il {gen} da <code>tools/build_signore.py</code>.</p>
</body>
</html>
"""


# ------------------------------------------------------------------- --check

STRIP_NUM = re.compile(r"([\d.]+(?:,\d+)?)\s*(km|m\b|kJ|h\b|attività)")


def report(D):
    tot, rings = D["tot"], D["rings"]
    print(f"\narchivio          {len(D['acts'])} attività, "
          f"{day(D['acts'][0])} → {day(D['acts'][-1])}")
    print(f"saga (era)        dal {D['era0']}: {tot.n} attività, "
          f"{it(tot.kj / 1000)} kJ, {it(tot.dist / 1000)} km, {it(tot.up)} m, "
          f"{it(tot.mov / 3600)} h, TL {it(tot.tl)}")
    print(f"mesi              {len(D['mkeys'])} ({D['mkeys'][0]} → {D['mkeys'][-1]}), "
          f"{len(D['mkeys']) - len(D['mb'])} senza attività")
    print(f"anelli            {len(rings)} chiusi")
    for n, d, c, _i, nm in rings:
        print(f"   anello {n:>2}      {d}  a {it(c)} kJ  ({nm[:42]})")
    print(f"carico reale da   {D['load0']}")
    ghosts = [a for a in D["acts"] if not a.get("id")]
    print(f"strava_id         {sum(1 for a in D['acts'] if a.get('strava_id') and a.get('id'))} "
          f"su {len(D['acts']) - len(ghosts)} attività vere; primo il "
          f"{min((day(a) for a in D['acts'] if a.get('strava_id') and a.get('id')), default='—')}")
    print(f"righe cieche      {len(ghosts)} ('STRAVA activities are not available via the API'), "
          f"{sum(1 for a in ghosts if day(a) >= D['era0'])} dentro la saga")
    print(f"buchi ≥{GAP_DAYS}g        " + ", ".join(f"{a}→{b} ({n}g)" for a, b, n in D["gaps"]))

    # Le due pagine di partenza dicevano il vero? Confronto fra la striscia
    # pubblicata a mano e quella ricalcolata: è il motivo per cui la fusione
    # serviva.
    print("\nsettimane pubblicate contro settimane ricalcolate:")
    bad = 0
    for w in D["ed"]["weeks"]:
        win = [a for a in D["era"] if w["start"] <= day(a) <= w["end"]]
        n = len(win)
        pub = w.get("published_strip", "")
        m = re.search(r"(\d+)\s*attività", pub)
        if m and int(m.group(1)) != n:
            print(f"   sett. {w['n']:>2} {w['start']}: pubblicate {m.group(1)} attività, "
                  f"nell'archivio {n}")
            bad += 1
    print(f"   {bad} strisce settimanali non tornano su {len(D['ed']['weeks'])}")

    covered = {w["start"] for w in D["ed"]["weeks"]}
    d0 = datetime.date.fromisoformat(D["ed"]["weeks"][0]["start"])
    d1 = datetime.date.fromisoformat(D["ed"]["weeks"][-1]["end"])
    missing = []
    d = d0
    while d <= d1:
        if d.isoformat() not in covered:
            win = [a for a in D["era"] if d.isoformat() <= day(a)
                   <= (d + datetime.timedelta(days=6)).isoformat()]
            if win:
                missing.append((d.isoformat(), len(win),
                                round(sum(num(a, "icu_joules") for a in win) / 1000)))
        d += datetime.timedelta(days=7)
    print(f"\nsettimane con attività ma senza capitolo, dentro l'arco raccontato: {len(missing)}")
    for a, n, k in missing:
        print(f"   {a}: {n} attività, {it(k)} kJ — mai raccontata dalla pagina settimanale")

    print(f"\nlink Strava nella prosa: {len(D['link_report'])} da sistemare")
    for who, sid, what, good, kmv in D["link_report"]:
        print(f"   {who}: {sid} {what}" + (f" -> {good} ({kmv} km)" if good else ""))


# ---------------------------------------------------------------------- main

def write(path, text, dry):
    if dry:
        print(f"--dry-run: {path} NON scritto ({len(text.encode('utf-8')) / 1024:.0f} KB)")
        return
    if os.path.exists(path):
        shutil.copyfile(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"scritto {path}  ({len(text.encode('utf-8')) / 1024:.0f} KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--api-key")
    ap.add_argument("--offline", action="store_true", help="usa tools/.signore_cache.json")
    ap.add_argument("--harvest", action="store_true",
                    help="riestrae la prosa dalle pagine attuali in tools/signore.json")
    ap.add_argument("--check", action="store_true", help="stampa cosa dicono i dati, non scrive")
    ap.add_argument("--dry-run", action="store_true", help="costruisce tutto, non scrive")
    args = ap.parse_args()

    if args.harvest:
        harvest()
        return
    if not os.path.exists(EDIT):
        sys.exit(f"manca {EDIT}: gira una volta con --harvest.")
    ed = json.load(open(EDIT, encoding="utf-8"))

    key = None if args.offline else get_api_key(args.api_key)
    acts = pull(key, args.offline)
    D = build(acts, ed, args)
    gen = datetime.date.today().isoformat()

    if args.check:
        report(D)
        return

    report(D)
    write(PAGE, render(D, gen), args.dry_run)
    write(ALIAS, render_alias(D, gen), args.dry_run)


if __name__ == "__main__":
    main()
