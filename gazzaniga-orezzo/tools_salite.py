#!/usr/bin/env python3
"""Costruisce _salite.js: le salite di casa, ricavate dalle tracce vere.

Nessun catalogo scritto a mano. Per ogni salita si parte dal nome che ricorre
nelle sue attività (Miragolo, Ganda, Selvino…), si scaricano un paio di quelle
attività da Intervals.icu e si cerca dentro la traccia **la salita vera**: il
tratto in cui si sale senza mai riperdere più di 30 metri. Se due attività
diverse trovano la stessa rampa, quella è la salita buona.

I punti di controllo — fondo, cima e quattro intermedi al 20/40/60/80% misurati
lungo il percorso — si ricavano dalla geometria, mai a occhio.

    python tools_salite.py
"""
import io
import json
import math
import os
import re
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
OROBICO = r"C:\Users\Alessandro Merelli\atlante-orobico"
sys.path.insert(0, os.path.join(OROBICO, "tools"))
from fetch_tracce import load_env, get  # noqa: E402

CACHE = os.path.join(OROBICO, "data", "_intervals_activities.json")
STREAMS = os.path.join(QUI, "_streams")

# nome che compare nelle attività -> come si chiama la salita
NOMI = {
    "miragolo":    ("Miragolo", "San Pellegrino, il muro che sveglia"),
    "ganda":       ("La Ganda", "il passo di casa, quello di tutti i giorni"),
    "selvino":     ("Selvino", "l'altopiano, dai tornanti di Nembro"),
    "zambla":      ("Passo Zambla", "verso Oltre il Colle, la valle lunga"),
    "farno":       ("Monte Farno", "Gandino verso l'alpe, il più duro"),
    "pighet":      ("Il Pighet", "la scorciatoia cattiva"),
    "parafulmine": ("Parafulmine", "da Gandino al rifugio"),
}

TETTO = 3          # quante attività guardare per salita
MIN_DSL = 170      # sotto questo dislivello non è una salita, è un dosso
MIN_KM = 1.2
PENDENZA = 0.045   # sotto il 4,5% non e' salita, e' avvicinamento
VICINANZA = 3500   # quanto puo' stare lontana la cima dal posto che da' il nome


def metri(a, b):
    g = math.pi / 180
    dlat, dlon = (b[0] - a[0]) * g, (b[1] - a[1]) * g
    x = math.sin(dlat / 2) ** 2 + math.cos(a[0] * g) * math.cos(b[0] * g) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(x))


def lunghezza(pts):
    tot = [0.0]
    for i in range(1, len(pts)):
        tot.append(tot[-1] + metri(pts[i - 1], pts[i]))
    return tot


def a_frazione(pts, cum, f):
    bersaglio = cum[-1] * f
    for i in range(1, len(cum)):
        if cum[i] >= bersaglio:
            return [round(pts[i][0], 6), round(pts[i][1], 6)]
    return [round(pts[-1][0], 6), round(pts[-1][1], 6)]


def snellisci(pts, quanti=140):
    if len(pts) <= quanti:
        return pts
    passo = len(pts) / quanti
    fuori = [pts[int(i * passo)] for i in range(quanti)]
    if fuori[-1] != pts[-1]:
        fuori.append(pts[-1])
    return fuori


def salite_dentro(lat, lon, alt, quante=3):
    """I tratti in salita continua: si sale, e non si riperdono mai più di CALO metri."""
    # il GPS ogni tanto perde il segnale e lascia buchi: quei campioni si buttano
    puliti = [(a, o, q) for a, o, q in zip(lat, lon, alt)
              if a is not None and o is not None and q is not None]
    if len(puliti) < 10:
        return []
    lat = [p[0] for p in puliti]
    lon = [p[1] for p in puliti]
    alt = [p[2] for p in puliti]
    n = len(alt)
    # Il punteggio di ogni passo: quanto sale meno quanto costerebbe salire alla
    # pendenza minima. Così un avvicinamento in piano abbassa il punteggio e resta
    # fuori: si tiene solo il cuore ripido, non tutta la strada da casa.
    passo = [0.0] * n
    for k in range(1, n):
        d = metri((lat[k - 1], lon[k - 1]), (lat[k], lon[k]))
        passo[k] = (alt[k] - alt[k - 1]) - PENDENZA * d

    fuori = []
    presi = [False] * n
    for _ in range(quante):
        # il tratto continuo di punteggio più alto (Kadane), saltando quel che
        # è già stato assegnato a una salita trovata prima
        meglio = (0.0, 0, 0)
        corrente, inizio = 0.0, 0
        for k in range(1, n):
            if presi[k]:
                corrente, inizio = 0.0, k
                continue
            if corrente <= 0:
                corrente, inizio = passo[k], k - 1
            else:
                corrente += passo[k]
            if corrente > meglio[0]:
                meglio = (corrente, inizio, k)
        _, i, j = meglio
        if j <= i:
            break
        for k in range(i, j + 1):
            presi[k] = True
        pts = [[lat[k], lon[k]] for k in range(i, j + 1)]
        if len(pts) < 5:
            continue
        cum = lunghezza(pts)
        dsl = alt[j] - alt[i]
        if dsl >= MIN_DSL and cum[-1] >= MIN_KM * 1000:
            fuori.append({"i": i, "j": j, "dsl": round(dsl), "km": round(cum[-1] / 1000, 2),
                          "pts": pts, "qmin": round(alt[i]), "qmax": round(alt[j])})
    fuori.sort(key=lambda s: -s["dsl"])
    return fuori


def stream(iid, key):
    os.makedirs(STREAMS, exist_ok=True)
    dest = os.path.join(STREAMS, iid + ".json")
    if os.path.exists(dest):
        return json.load(io.open(dest, encoding="utf-8"))
    d = get(f"https://intervals.icu/api/v1/activity/{iid}/streams?types=latlng,altitude", key)
    lat = lon = alt = None
    for s in d or []:
        if s.get("type") == "latlng":
            lat, lon = s.get("data"), s.get("data2")
        elif s.get("type") == "altitude":
            alt = s.get("data")
    if not (lat and lon and alt):
        return None
    fuori = {"lat": lat, "lon": lon, "alt": alt}
    json.dump(fuori, io.open(dest, "w", encoding="utf-8"))
    time.sleep(0.4)
    return fuori


def stessa(a, b, tol=450):
    return metri(a["pts"][0], b["pts"][0]) < tol and metri(a["pts"][-1], b["pts"][-1]) < tol


LUOGHI = os.path.join(QUI, "_luoghi.json")


def dove(nome):
    """Dove sta davvero quel posto, chiesto a Nominatim (una volta sola).

    Serve perché prendere la salita più forte dell'attività non basta: un giro
    che si chiama “Monte Farno” parte da casa, e la rampa più dura potrebbe
    essere quella sotto casa. La cima deve stare vicino al posto che dà il nome.
    """
    cache = json.load(io.open(LUOGHI, encoding="utf-8")) if os.path.exists(LUOGHI) else {}
    if nome in cache:
        return cache[nome]
    import urllib.parse
    import urllib.request
    u = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
         + urllib.parse.quote(nome + ", provincia di Bergamo, Italia"))
    req = urllib.request.Request(u, headers={"User-Agent": "signoredellecime/1.0 (michelemerelli.8@gmail.com)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        cache[nome] = [float(d[0]["lat"]), float(d[0]["lon"])] if d else None
    except Exception:
        cache[nome] = None
    json.dump(cache, io.open(LUOGHI, "w", encoding="utf-8"))
    time.sleep(1.2)          # la buona educazione con Nominatim: una al secondo
    return cache[nome]


def confeziona(id, nome, sotto, pts, qmin=None, qmax=None, dsl=None):
    pts = [[round(p[0], 6), round(p[1], 6)] for p in pts]
    cum = lunghezza(pts)
    return {
        "id": id, "nome": nome, "sotto": sotto,
        "pts": snellisci(pts),
        "fondo": [round(pts[0][0], 6), round(pts[0][1], 6)],
        "cima": [round(pts[-1][0], 6), round(pts[-1][1], 6)],
        "mezzi": [a_frazione(pts, cum, f) for f in (0.2, 0.4, 0.6, 0.8)],
        "km": round(cum[-1] / 1000, 2),
        "dsl": dsl, "qmin": qmin, "qmax": qmax,
    }


def main():
    env = load_env()
    key = env["INTERVALS_API_KEY"]
    att = json.load(io.open(CACHE, encoding="utf-8"))
    salite = []

    # 1. Gazzaniga → Orezzo: la traccia canonica sta nella storia
    s = io.open(os.path.join(QUI, "_data.js"), encoding="utf-8").read()
    route = json.loads(re.search(r"const\s+ROUTE\s*=\s*(\[.*?\]);", s, re.S).group(1))
    salite.append(confeziona("orezzo", "Gazzaniga → Orezzo", "la rampa di casa, quella dei 607 passaggi",
                             [p[:2] for p in route], 393, 675, 282))

    # 2. Gazzaniga → Monte Poieto: la traccia del 521 Vertical
    f = os.path.join(OROBICO, "data", "tracce", "i62693758.json")
    if os.path.exists(f):
        t = json.load(io.open(f, encoding="utf-8"))
        salite.append(confeziona("poieto", "Gazzaniga → Monte Poieto", "il sentiero CAI 521, quello del Vertical",
                                 t["punti"], t.get("quota_min"), t.get("quota_max"),
                                 (t.get("quota_max") or 0) - (t.get("quota_min") or 0)))

    # 3. le altre: si trovano dentro le attività che le nominano
    for chiave, (nome, sotto) in NOMI.items():
        cand = [a for a in att
                if chiave in (a.get("name") or "").lower()
                and (a.get("total_elevation_gain") or 0) > 200
                and a.get("type") in ("Ride", "Run", "VirtualRide", "Hike")]
        cand.sort(key=lambda a: a.get("icu_distance") or 1e9)
        posto = dove(nome.replace("Il ", "").replace("La ", ""))
        tutte = []
        for a in cand[:TETTO]:
            st = stream(a["id"], key)
            if not st:
                continue
            for c in salite_dentro(st["lat"], st["lon"], st["alt"], quante=6):
                c["da"] = a.get("name")
                tutte.append(c)
        # Il posto si usa solo se i dati lo confermano: Nominatim ha messo il
        # Parafulmine in Val Brembana invece che sopra Gandino, e un indirizzo
        # sbagliato non deve buttare via una salita che c'è davvero.
        vicine = [c for c in tutte if posto and metri(c["pts"][-1], posto) <= VICINANZA]
        if vicine:
            trovate = vicine
        else:
            trovate = tutte
            if posto:
                print(f"  ~    {nome}: il posto trovato online non torna con le tracce, vado di sole tracce")
        if not trovate:
            print(f"  --   {nome}: nessuna salita nelle sue attività")
            continue
        # la rampa che due attività diverse hanno in comune è quella giusta
        gruppi = []
        for c in trovate:
            for g in gruppi:
                if stessa(g[0], c):
                    g.append(c)
                    break
            else:
                gruppi.append([c])
        gruppi.sort(key=lambda g: (-len(g), -g[0]["dsl"]))
        scelta = max(gruppi[0], key=lambda c: len(c["pts"]))
        gia = next((x for x in salite
                    if metri(x["fondo"], scelta["pts"][0]) < 300 and metri(x["cima"], scelta["pts"][-1]) < 300), None)
        if gia:
            print(f"  --   {nome}: e' la stessa rampa di {gia['nome']}, la lascio stare")
            continue
        salite.append(confeziona(chiave, nome, sotto, scelta["pts"],
                                 scelta["qmin"], scelta["qmax"], scelta["dsl"]))
        print(f"  ok   {nome}: {scelta['km']} km +{scelta['dsl']} m "
              f"({len(gruppi[0])} attività d'accordo, da “{scelta['da']}”)")

    salite.sort(key=lambda s: -(s["dsl"] or 0))
    js = "// generato da tools_salite.py — non modificare a mano\n"
    js += "const SALITE=" + json.dumps(salite, ensure_ascii=False, separators=(",", ":")) + ";\n"
    io.open(os.path.join(QUI, "_salite.js"), "w", encoding="utf-8").write(js)
    fuori = os.path.join(os.path.dirname(QUI), "signoredellecime")
    if os.path.isdir(fuori):
        io.open(os.path.join(fuori, "_salite.js"), "w", encoding="utf-8").write(js)
    print(f"\n{len(salite)} salite -> _salite.js ({len(js)/1024:.0f} kB)")
    for x in salite:
        print(f"  {x['nome']:26} {x['km']:5.2f} km  +{x['dsl'] or 0:4} m  fino a {x['qmax'] or '?'} m")


if __name__ == "__main__":
    main()
