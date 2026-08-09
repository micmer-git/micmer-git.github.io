#!/usr/bin/env python3
"""Banco di prova del conta-salite.

Attività finte costruite da tracce vere, date in pasto alla pagina vera dentro
Chrome headless. Serve un server locale (i fetch non funzionano da file://):

    python -m http.server 8898 --bind 127.0.0.1
    python tools_prova.py
"""
import io
import json
import os
import re
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
STORIA = os.path.join(os.path.dirname(QUI), "gazzaniga-orezzo")
LIB = r"C:\Users\Alessandro Merelli\pettorale\public\attivita.js"
TRACCE = r"C:\Users\Alessandro Merelli\atlante-orobico\data\tracce"
CHROME = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
CHIUDI = "</" + "script>"


def codifica(punti):
    out, prec = [], [0, 0]
    for p in punti:
        for i, v in enumerate(p[:2]):
            x = round(v * 1e5)
            d = x - prec[i]
            prec[i] = x
            d = ~(d << 1) if d < 0 else (d << 1)
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
    return "".join(out)


def att(i, giorno, nome, tipo, punti):
    return {"i": i, "d": giorno, "n": nome, "t": tipo, "km": 5, "ds": 300, "s": 1800,
            "ll": [round(punti[0][0], 5), round(punti[0][1], 5)], "p": codifica(punti)}


def main():
    s = io.open(os.path.join(STORIA, "_data.js"), encoding="utf-8").read()
    route = [p[:2] for p in json.loads(re.search(r"const\s+ROUTE\s*=\s*(\[.*?\]);", s, re.S).group(1))]
    poieto = json.load(io.open(os.path.join(TRACCE, "i62693758.json"), encoding="utf-8"))["punti"]
    valzurio = json.load(io.open(os.path.join(TRACCE, "i62693435.json"), encoding="utf-8"))["punti"]
    parallela = [[p[0], p[1] + 0.0064] for p in route]      # la stessa rampa 500 m più a est

    prove = [
        ("salita Orezzo",     att(1, "2024-05-01", "su", "Ride", route),          ["orezzo"]),
        # la discesa non è una salita: da adesso non conta
        ("discesa Orezzo",    att(2, "2023-05-02", "giù", "Run", route[::-1]),    []),
        # il 521 passa davvero sopra Orezzo: quel giorno le hai salite tutt'e due
        ("521 verso Poieto",  att(3, "2023-10-08", "521", "Run", poieto),         ["orezzo", "poieto"]),
        ("un trail altrove",  att(4, "2023-04-29", "Valzurio", "Run", valzurio),  []),
        ("strada parallela",  att(5, "2022-06-01", "di fianco", "Ride", parallela), []),
    ]

    lib = io.open(LIB, encoding="utf-8").read().replace(CHIUDI, "<\\/" + "script>")
    assert CHIUDI not in lib
    stub = ("<" + "script>" + lib + "\n"
            "Pettorale.leggiPettorale = () => ({access_token:'finto'});\n"
            "window.A = " + json.dumps([p[1] for p in prove], ensure_ascii=False) + ";\n"
            "Pettorale.tutte = async () => window.A;\n"
            "setTimeout(() => {\n"
            "  const o = {};\n"
            "  for (const id in esiti) for (const p of esiti[id]) (o[p.a.i] = o[p.a.i] || []).push(id);\n"
            "  console.log('ESITO ' + JSON.stringify(o));\n"
            "}, 5000);\n" + CHIUDI)

    pagina = io.open(os.path.join(QUI, "index.html"), encoding="utf-8").read()
    pagina = pagina.replace('<script src="https://pettorale.pages.dev/attivita.js">' + CHIUDI, stub)
    io.open(os.path.join(QUI, "_prova.html"), "w", encoding="utf-8").write(pagina)

    p = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--enable-logging=stderr",
                        "--virtual-time-budget=22000", "--dump-dom",
                        "http://127.0.0.1:8898/_prova.html"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"ESITO (\{.*?\})\"", p.stderr)
    if not m:
        print("nessun esito.", *[l for l in p.stderr.splitlines() if "CONSOLE" in l][:3], sep="\n  ")
        sys.exit(1)
    avuto = json.loads(m.group(1))

    bene = True
    for nome, a, atteso in prove:
        ris = sorted(avuto.get(str(a["i"]), []))
        ok = ris == sorted(atteso)
        bene &= ok
        print(f"  {'OK ' if ok else 'NO '} {nome:20} atteso {atteso}  avuto {ris}")
    print("\ntutto a posto" if bene else "\nqualcosa non torna")
    sys.exit(0 if bene else 1)


if __name__ == "__main__":
    main()
