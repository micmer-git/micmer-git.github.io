#!/usr/bin/env python3
"""Costruisce _salite.js: le salite di casa con i loro punti di controllo.

I punti che servono a riconoscere un passaggio — fondo, cima e gli intermedi —
non si scrivono a mano: si ricavano dalla traccia, misurando lungo il percorso.
Così restano *sulla* salita anche quando la rampa gira, e se un domani cambia la
traccia cambiano da soli.

    python tools_salite.py
"""
import io
import json
import math
import os
import re

QUI = os.path.dirname(os.path.abspath(__file__))
TRACCE = r"C:\Users\Alessandro Merelli\atlante-orobico\data\tracce"


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
    """Il punto che sta al f% della salita, misurato lungo il percorso."""
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


def salita(id, nome, sotto, punti, quote=None):
    pts = [[round(p[0], 6), round(p[1], 6)] for p in punti]
    cum = lunghezza(pts)
    dsl = 0
    if quote:
        for i in range(1, len(quote)):
            d = quote[i] - quote[i - 1]
            if d > 0:
                dsl += d
    return {
        "id": id, "nome": nome, "sotto": sotto,
        "pts": snellisci(pts),
        "fondo": [round(pts[0][0], 6), round(pts[0][1], 6)],
        "cima": [round(pts[-1][0], 6), round(pts[-1][1], 6)],
        # quattro guardiani lungo la strada: chi ne tocca almeno tre è passato di qui
        "mezzi": [a_frazione(pts, cum, f) for f in (0.2, 0.4, 0.6, 0.8)],
        "km": round(cum[-1] / 1000, 2),
        "dsl": round(dsl) if quote else None,
        "qmin": round(min(quote)) if quote else None,
        "qmax": round(max(quote)) if quote else None,
    }


def main():
    salite = []

    # 1. Gazzaniga → Orezzo: la traccia sta già nel _data.js della storia
    s = io.open(os.path.join(QUI, "_data.js"), encoding="utf-8").read()
    route = json.loads(re.search(r"const\s+ROUTE\s*=\s*(\[.*?\]);", s, re.S).group(1))
    salite.append(salita("orezzo", "Gazzaniga → Orezzo", "la rampa di casa, quella dei 607 passaggi",
                         [p[:2] for p in route], [p[2] for p in route]))

    # 2. Gazzaniga → Monte Poieto: la traccia del 521 Vertical 2023
    f = os.path.join(TRACCE, "i62693758.json")
    if os.path.exists(f):
        t = json.load(io.open(f, encoding="utf-8"))
        salite.append(salita("poieto", "Gazzaniga → Monte Poieto", "il sentiero CAI 521, quello del Vertical",
                             t["punti"]))
        salite[-1]["qmin"], salite[-1]["qmax"] = t.get("quota_min"), t.get("quota_max")
        if salite[-1]["qmin"] is not None:
            salite[-1]["dsl"] = salite[-1]["qmax"] - salite[-1]["qmin"]

    js = "// generato da tools_salite.py — non modificare a mano\n"
    js += "const SALITE=" + json.dumps(salite, ensure_ascii=False, separators=(",", ":")) + ";\n"
    io.open(os.path.join(QUI, "_salite.js"), "w", encoding="utf-8").write(js)

    for x in salite:
        print(f"  {x['nome']:30} {x['km']:5.2f} km  +{x['dsl'] or 0:4} m  "
              f"{len(x['pts'])} punti  intermedi {[[round(m[0],4),round(m[1],4)] for m in x['mezzi']]}")
    print(f"{len(salite)} salite -> _salite.js ({len(js)/1024:.0f} kB)")


if __name__ == "__main__":
    main()
