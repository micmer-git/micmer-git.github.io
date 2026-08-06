#!/usr/bin/env python3
"""Banco di prova del conta-passaggi.

Attività finte costruite da tracce vere, date in pasto alla pagina vera dentro
Chrome headless. Serve un server locale (i fetch non funzionano da file://):

    python -m http.server 8898 --bind 127.0.0.1
    python tools_prova_salite.py
"""
import io
import json
import os
import re
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
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
    s = io.open(os.path.join(QUI, "_data.js"), encoding="utf-8").read()
    route = [p[:2] for p in json.loads(re.search(r"const\s+ROUTE\s*=\s*(\[.*?\]);", s, re.S).group(1))]
    poieto = json.load(io.open(os.path.join(TRACCE, "i62693758.json"), encoding="utf-8"))["punti"]
    valzurio = json.load(io.open(os.path.join(TRACCE, "i62693435.json"), encoding="utf-8"))["punti"]
    # una strada parallela: la stessa salita spostata di ~500 m a est
    parallela = [[p[0], p[1] + 0.0064] for p in route]

    prove = [
        ("orezzo su",      att(1, "2024-05-01", "salita Orezzo", "Ride", route),        {"orezzo": "su"}),
        ("orezzo giu",     att(2, "2023-05-02", "discesa Orezzo", "Run", route[::-1]),  {"orezzo": "giù"}),
        # il 521 parte dallo stesso fondo e passa a 98 m dalla cima di Orezzo:
        # chi sale al Poieto ha salito anche Orezzo, quindi contarlo due volte e' giusto
        ("poieto su",      att(3, "2023-10-08", "521 Vertical", "Run", poieto),
         {"poieto": "su", "orezzo": "su"}),
        ("valzurio",       att(4, "2023-04-29", "Valzurio Trail", "Run", valzurio),     {}),
        ("strada parallela", att(5, "2022-06-01", "quella di fianco", "Ride", parallela), {}),
    ]

    lib = io.open(LIB, encoding="utf-8").read().replace(CHIUDI, "<\\/" + "script>")
    assert CHIUDI not in lib
    attivita = [p[1] for p in prove]
    stub = ("<" + "script>" + lib + "\n"
            "Pettorale.leggiPettorale = () => ({access_token:'finto'});\n"
            "window.A = " + json.dumps(attivita, ensure_ascii=False) + ";\n"
            "Pettorale.tutte = async () => window.A;\n"
            "setTimeout(() => {\n"
            "  const o = {};\n"
            "  for (const id in esiti) for (const p of esiti[id]) (o[p.a.i] = o[p.a.i] || {})[id] = p.verso;\n"
            "  console.log('ESITO ' + JSON.stringify(o));\n"
            "}, 5000);\n" + CHIUDI)

    pagina = io.open(os.path.join(QUI, "tua.html"), encoding="utf-8").read()
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
        ris = avuto.get(str(a["i"]), {})
        ok = ris == atteso
        bene &= ok
        print(f"  {'OK ' if ok else 'NO '} {nome:20} atteso {atteso or '{}'}  avuto {ris or '{}'}")
    print("\ntutto a posto" if bene else "\nqualcosa non torna")
    sys.exit(0 if bene else 1)


if __name__ == "__main__":
    main()
