#!/usr/bin/env python3
"""top-20, v3/v4: lo stesso racconto come **video**, non piu' come GIF.

La v4 applica i voti del laboratorio 2 (top-20/lab2.html, 31/07/2026):

- **i commenti stanno al centro, sopra la mappa velata** (P05 = 10, "non solo i
  passi, ma tutti i commenti") — non piu' pagine di carta piena: la mappa resta
  visibile sotto il testo, al 74% di velo;
- **i numeri vivi negli angoli in contrappunto** (N02 = 9 dentro T05 = 7): km e
  tempo in basso a sinistra, dislivello a destra, cifra grande in Georgia ed
  etichetta in maiuscoletto, contano su mentre il puntino corre. Via la barra
  dei dati ferma;
- **la quota come colore, ma solo dove si sale** ("questa mappa quando
  dislivello, se non dislivello solo path"): sopra i 12 m/km il tratto si
  disegna con la rampa verde del laboratorio (RAMP in build_top20_reel), in
  pianura resta il colore d'accento;
- **la riga di ogni tratto** (dal secondo in poi) passa anche lei al centro.

Perche' un file diverso e non una bandiera in piu' su `build_top20_reel.py`: quel
tool e' costruito attorno a un vincolo che qui non esiste. In una GIF **tenere un
frame e' gratis** e **cambiare la scala della mappa costa 40 kB**, e da quelle due
frasi discende tutto il montaggio: camera bloccata mentre la traccia si disegna,
zoom ridotti a due frame, note spinte in una colonna di lato perche' una pagina a
tutto schermo in piu' voleva dire una dissolvenza in piu' da pagare. In un video
non e' vero niente di tutto cio': i fermo-immagine costano (sono frame veri) e il
movimento e' quasi gratis, perche' h264 — o qui MPEG-4 — comprime bene proprio
quello che la GIF comprimeva male. Sono due montaggi opposti, e tenerli nello
stesso file avrebbe voluto dire un `if` a ogni riga. Le primitive di disegno,
quelle si', sono le stesse: si importano da `build_top20_reel`.

Cosa cambia rispetto al reel:

1. **La durata di un testo si stima dalla sua lunghezza.** Nella GIF ogni blocco
   stava cinque secondi, lungo o corto che fosse: una regola sola perche' tenere
   costava zero e non valeva la pena distinguere. Qui una pausa sono trenta frame
   al secondo di file, quindi `read_ms()` conta le parole e paga il giusto.

2. **Le note vanno a tutto schermo.** Erano in una colonna di fianco alla traccia
   perche' era l'unico posto gratis. Ora il montaggio e' quello chiesto: la mappa
   si dissolve nel commento, il commento si legge, si torna sulla mappa **e la
   traccia riparte da dove si era fermata**, fino alla nota dopo.

3. **La camera segue il puntino, da vicino.** Il divieto di cambiare scala mentre
   si disegna era una regola di budget GIF, non di racconto. Qui il tratto si apre
   sull'inquadratura intera, stringe sul puntino e lo segue, e alla fine allarga a
   rivelare la forma completa del giro.

4. **Le dissolvenze respirano.** Mezzo secondo con una deriva di scala minima
   (1,00 → 1,04) invece del taglio in due frame: e' la differenza fra "cambio
   pagina" e "stacco".

Il video si scrive con OpenCV, che ha ffmpeg dentro. **Il codec e' `mp4v`
(MPEG-4 Part 2) e non h264**: OpenCV pretende `openh264-*.dll` per l'avc1 vero,
sul portatile non c'e', e senza quella libreria `avc1` non fallisce — ripiega in
silenzio su un intra-only da 61 kB/frame, cioe' cinque volte tanto. Misurato:
mp4v fa 45 MB per 6'28" a 760 px, e sul testo non si vede un artefatto. Se un
giorno serve h264 vero, la conversione si fa a valle da questo file.

    python tools/build_top20_video.py                       # tutto, 760 px
    python tools/build_top20_video.py --only 1,19 --size 640 --probe-sec 0
"""
import argparse
import os
import sys
import time

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import basemap as BM                                                  # noqa: E402
import build_top20_reel as R                                          # noqa: E402
from build_top20_gif import AC, BG, INK, INK2, INK3, font             # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = os.path.join(HERE, "..", "top-20", "top-20-reel.mp4")


# ------------------------------------------------------------------ il tempo

def read_ms(*texts, base=700, wpm=205, lo=1700, hi=8000):
    """Quanto tenere un blocco di testo, dalle parole che contiene.

    205 parole al minuto e' lettura attenta, non scorrimento: e' testo grande,
    centrato, letto una volta sola e senza poter tornare indietro. `base` sono i
    decimi che servono all'occhio per trovare l'inizio della riga dopo una
    dissolvenza — non dipendono dalla lunghezza, quindi stanno fuori dal conto.

    Il tetto a otto secondi e' stato misurato al contrario, dal primo montaggio:
    senza tetto la scheda dell'Ironman (33 parole) restava 11,6 s, e undici secondi
    fermi su una pagina non si leggono come lentezza, si leggono come un video
    bloccato. Oltre le ~27 parole il testo va tagliato, non tenuto di piu'.
    """
    words = sum(len(t.split()) for t in texts if t)
    return int(min(hi, max(lo, base + words * 60000.0 / wpm)))


def card_ms(st, minus=0):
    """La scheda del giorno. Due correzioni sul conto crudo delle parole.

    La **data non si legge**, si riconosce: "5 giugno 2016" sono tre parole che
    costano un decimo di secondo, non un secondo, quindi il kicker resta fuori dal
    conto. E `minus` toglie il tempo del montaggio della scheda, durante il quale
    il testo e' gia' in pagina e gia' si sta leggendo: contarlo due volte era quel
    che rendeva le schede interminabili.
    """
    card = st.get("card") or [["date", st["kicker"]], ["lead", st["title"]]]
    body = [t for k, t in card if k != "date"]
    return max(1600, read_ms(*body, base=900) - minus)


# ------------------------------------------------------------------ le pagine

_CT_CACHE = {}


def center_text(base, S, fonts, text, ac, alpha, kicker=None, body=None):
    """Il testo al centro SOPRA un quadro vivo — il P05 del laboratorio 2, votato
    10 con la nota "non solo i passi, ma tutti i commenti".

    Non e' una pagina: e' una sovrimpressione. Lo scrim sta solo dietro il blocco
    del testo, il resto del quadro continua a muoversi (la traccia si disegna, il
    volo scorre) e si vede. Il testo breve va grande in Georgia, quello lungo in
    corpo; le citazioni dal diario in corsivo, come ovunque.
    """
    a = max(0.0, min(1.0, alpha))
    if a < 0.03 or not text:
        return base.convert("RGB")
    # NIENTE scatola (round 3 dei feedback): solo un alone di carta attorno alle
    # lettere, come i nomi dei luoghi. Il testo vive su un layer con la propria
    # trasparenza, cosi' la dissolvenza e' vera e sotto si vede tutto: la traccia
    # che avanza, il puntino, il volo.
    #
    # Il layer si mette in CACHE per (testo, alpha quantizzata): l'alone sono 24
    # passate di disegno per riga, e rifarle a ogni frame — il testo ora sta
    # sopra quadri in movimento — quintuplicava la resa. Comporre un layer
    # pronto costa quasi niente.
    a = round(a * 24) / 24.0
    out = base.convert("RGBA")
    key = (text, kicker, body, a, S)
    cached = _CT_CACHE.get(key)
    if cached is not None:
        out.alpha_composite(cached)
        return out.convert("RGB")
    lay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    f_kick, f_emo = fonts[0], fonts[5]
    big = len(R.plain(text)) <= 90 and not body
    f = fonts[7] if big else (fonts[10] if R.is_quote(text) else fonts[8])
    f = fonts[7] if body else f            # nell'intro il titolo va comunque grande
    pad = int(S * 0.115)
    ls = R.wrap(dr, text, f, f_emo, S - 2 * pad)
    lh = int(S * (0.092 if (big or body) else 0.050))
    bls = R.wrap(dr, body, fonts[8], f_emo, S - 2 * pad) if body else []
    h = (len(ls) * lh + len(bls) * int(S * 0.050)
         + (int(S * 0.048) + int(S * 0.030) if kicker else int(S * 0.010))
         + (int(S * 0.016) if body else 0))
    y = (S - h) // 2
    halo = BG + (int(235 * a),)
    aink = lambda c: c + (int(255 * a),)

    def puts(x, yy, txt, fnt, col, ring):
        for ox in range(-ring, ring + 1):
            for oy in range(-ring, ring + 1):
                if ox or oy:
                    R.draw_text(dr, (x + ox, yy + oy), txt, fnt, f_emo, halo)
        R.draw_text(dr, (x, yy), txt, fnt, f_emo, col)

    if kicker:
        tw = R.tracked_w(dr, kicker, f_kick, S * 0.006)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                if ox or oy:
                    R.draw_tracked(dr, ((S - tw) // 2 + ox, y + oy), kicker,
                                   f_kick, halo, S * 0.006)
        R.draw_tracked(dr, ((S - tw) // 2, y), kicker, f_kick, aink(INK3), S * 0.006)
        y += int(S * 0.048)
        dr.rectangle([S // 2 - int(S * 0.030), y + int(S * 0.010),
                      S // 2 + int(S * 0.030), y + int(S * 0.010) + 1],
                     fill=aink(ac))
        y += int(S * 0.030)
    for line in ls:
        w = R.text_w(dr, line, f, f_emo)
        puts((S - w) // 2, y, line, f, aink(INK if (big or body) else INK2), 2)
        y += lh
    if body:
        y += int(S * 0.016)
        fb = fonts[10] if R.is_quote(body) else fonts[8]
        for line in bls:
            w = R.text_w(dr, line, fb, f_emo)
            puts((S - w) // 2, y, line, fb, aink(INK2), 2)
            y += int(S * 0.050)
    if len(_CT_CACHE) > 500:
        _CT_CACHE.clear()
    _CT_CACHE[key] = lay
    out.alpha_composite(lay)
    return out.convert("RGB")


# ------------------------------------------------------------------ il volo basso

def make_flight(a, b, px, style):
    """La carta del trasferimento: un mosaico solo che contiene il giorno prima e
    il prossimo, con margine. Niente piu' ritorno al globo fra le storie: la
    camera resta "vicino a terra" e scorre da un posto all'altro su una mappa
    vera — il globo resta solo in apertura e in chiusura, dove e' un riassunto.
    """
    import math
    la0, la1 = sorted((a[0], b[0]))
    lo0, lo1 = sorted((a[1], b[1]))
    dla = max(la1 - la0, 0.35)
    dlo = max(lo1 - lo0, 0.35)
    la0 -= dla * .40; la1 += dla * .40
    lo0 -= dlo * .40; lo1 += dlo * .40
    cla, clo = (la0 + la1) / 2, (lo0 + lo1) / 2
    k = math.cos(math.radians(max(-80, min(80, cla)))) or 1.0
    half = max(la1 - la0, (lo1 - lo0) * k) / 2
    la0, la1 = cla - half, cla + half
    lo0, lo1 = clo - half / k, clo + half / k
    img, to_px = BM.mosaic(la0, la1, lo0, lo1, px=px, style=style, zmax=12)
    return {"img": img, "to_px": to_px, "a": to_px(*a), "b": to_px(*b)}


def flight_shot(fl, t, S):
    """Un frame del volo: pan da A a B, con la camera che si alza a meta' strada
    quanto basta a vedere tutti e due — mai fino allo spazio."""
    import math
    img = fl["img"]
    mw, mh = img.size
    span = min(mw, mh)
    z = 1.0 + 1.05 * abs(math.cos(math.pi * t))     # 2.05 → 1.0 → 2.05
    e = R.ease(t)
    cx = R.lerp(fl["a"][0], fl["b"][0], e)
    cy = R.lerp(fl["a"][1], fl["b"][1], e)
    w = span / z
    cx = min(max(cx, w / 2), mw - w / 2)
    cy = min(max(cy, w / 2), mh - w / 2)
    crop = img.crop((int(cx - w / 2), int(cy - w / 2),
                     int(cx + w / 2), int(cy + w / 2)))
    return crop.resize((S, S), Image.LANCZOS).convert("RGB")


# ------------------------------------------------------------------ i raccordi

def drift(im, S, k):
    """La stessa immagine con una deriva di scala minima attorno al centro.

    Serve solo alle dissolvenze: due pagine che si scambiano stando perfettamente
    ferme sembrano un errore di caricamento, le stesse due con un quarantesimo di
    scala addosso sembrano un movimento di macchina. Sotto l'1 % non si vede, sopra
    il 6 % si legge come uno zoom e distrae dal testo.
    """
    if abs(k - 1.0) < 0.002:
        return im
    w = max(1, int(round(S * k)))
    big = im.resize((w, w), Image.LANCZOS)
    if k >= 1.0:
        o = (w - S) // 2
        return big.crop((o, o, o + S, o + S))
    c = Image.new("RGB", (S, S), BG)
    c.paste(big, ((S - w) // 2, (S - w) // 2))
    return c


# ------------------------------------------------------------------ montaggio

def build(stories, S, fonts, args, emit):
    """Il taglio. `emit(im, ms)` incassa un frame e per quanto resta a schermo.

    Il montaggio e' quello chiesto: scheda del giorno a tutto schermo, volo sul
    globo, poi il tratto che si disegna **a segmenti**, e fra un segmento e
    l'altro il commento prende tutto lo schermo. Al ritorno la traccia non
    ricomincia: riparte dal punto esatto in cui l'aveva lasciata, che e' l'unica
    cosa che rende la sequenza un racconto invece che una serie di clip.
    """
    total = len(stories)
    dots = [(s["clat"], s["clon"], AC.get(s["st"]["accent"], AC["stone"])) for s in stories]
    FMS = 1000.0 / args.fps                       # un frame di video
    nf = lambda sec: max(1, int(round(sec * args.fps)))

    def moving(n, fn, ms=None):
        for k in range(n):
            emit(fn((k + 1) / float(n)), ms or FMS)

    def cross(a, b, sec, k0=1.0, k1=1.02):
        """Da una pagina all'altra, con la deriva addosso a tutte e due."""
        n = nf(sec)
        for k in range(n):
            t = R.ease((k + 1) / float(n))
            emit(Image.blend(drift(a, S, R.lerp(k0, k1, t)),
                             drift(b, S, R.lerp(2.0 - k1, 1.0, t)), t), FMS)

    def page(make, hold_ms, sec_in=0.45, sec_out=0.35, prev=None):
        """Una pagina di testo: entra, si legge, esce sulla carta."""
        full = make(1.0)
        if prev is not None:
            cross(prev, full, sec_in)
        else:
            moving(nf(sec_in), lambda t: make(R.ease(t)))
        emit(full, hold_ms)
        if sec_out:
            moving(nf(sec_out), lambda t: R.to_paper(full, R.ease(t), S))
        return full

    # --- apertura
    if args.intro or not args.only:
        page(lambda a: R.text_card(S, fonts, a,
                                   [("micmer · archivio 2015 – 2026", "kicker"),
                                    ("Venti giorni", "big"), ("su 2.923", "big"),
                                    ("Undici anni di GPS. Ogni traccia è quella vera.", "body")]),
             read_ms("Venti giorni su 2.923", "Undici anni di GPS. Ogni traccia è quella vera.",
                     base=1400))
        page(lambda a: R.text_card(S, fonts, a,
                                   [("98.830 chilometri. 1.843.198 metri di dislivello.", "body"),
                                    ("4.928 ore in movimento.", "body"),
                                    ("Venti giorni raccontati, uno alla volta.", "body")]),
             read_ms("98.830 chilometri. 1.843.198 metri di dislivello.",
                     "4.928 ore in movimento.", "Venti giorni raccontati, uno alla volta."))
        moving(nf(1.6), lambda t: R.globe_frame(S, 46, 9, dots, fonts,
                                                upto=int(t * (total - 1)),
                                                radius=R.lerp(0.30, 0.86, R.ease(t))))
        prev_globe = R.globe_frame(S, 46, 9, dots, fonts, upto=total - 1)
        emit(prev_globe, 900)
    else:
        prev_globe = None

    prev_map = None
    for si, story in enumerate(stories):
        st = story["st"]
        ac = AC.get(st["accent"], AC["stone"])
        race = st.get("mode") == "race"
        plat, plon = (stories[si - 1]["clat"], stories[si - 1]["clon"]) if si else (46, 9)

        # --- il trasferimento, "vicino a terra": niente piu' ritorno al globo fra
        # le storie. Dalla mappa di prima si passa alla carta del volo — un
        # mosaico vero che contiene tutti e due i posti — la camera scorre verso
        # il giorno nuovo, e l'INTRO della storia si legge al centro MENTRE sotto
        # si vola. Il globo resta solo in apertura e in chiusura, dove riassume.
        lg0 = story["legs"][0]["leg"]
        elev0 = (not race and bool(lg0.get("alt")) and lg0.get("km", 0) > 0
                 and lg0.get("gain", 0) / float(lg0["km"]) >= 12.0)
        target = R.map_frame(story, 0, 0.0, 1.0, S, fonts, cap_alpha=0.0, total=total,
                             elev=elev0,
                             counters=None if race else
                             {"km": "0 km", "kml": "PERCORSI",
                              "gain": "0 m", "gainl": "DI SALITA"})
        card = st.get("card") or [["date", st["kicker"]], ["lead", st["title"]]]
        date = next((t for k2, t in card if k2 == "date"), st["kicker"])
        lead = next((t for k2, t in card if k2 == "lead"), st["title"])
        body = next((t for k2, t in card if k2 == "body"), "")
        kick = "%02d · %s" % (si + 1, date.upper())
        fl = make_flight((plat, plon), (story["clat"], story["clon"]),
                         args.fly_px, args.style)
        first = flight_shot(fl, 0.0, S)
        if prev_map is not None:
            cross(prev_map, first, 0.45)
        elif prev_globe is not None:
            cross(prev_globe, first, 0.55)
        # il volo NON si ferma mai: l'intro entra presto, si legge in movimento
        # e se ne va prima dell'atterraggio. Niente frame tenuti (round 3:
        # "less still text and more text while other things happen")
        nfl = nf(args.fly_sec + 1.8)
        for k in range(nfl):
            t = (k + 1) / float(nfl)
            a = min(1.0, t / 0.16, max(0.0, (0.94 - t) / 0.10))
            fr = center_text(flight_shot(fl, t, S), S, fonts, lead, ac, a,
                             kicker=kick, body=body)
            R.ticks(fr, si + 1, total, S, ac, fonts)
            emit(fr, FMS)
        cross(flight_shot(fl, 1.0, S), target, 0.5)

        # i totali del giorno crescono attraverso i tratti: i contatori negli
        # angoli non ripartono da zero quando Bologna passa dalla bici alla corsa
        km_before, gain_before, secs_before = 0.0, 0.0, 0.0
        for li, l in enumerate(story["legs"]):
            if race and li > 0:
                break                     # in gara le cinque edizioni corrono insieme

            # quanto dura il disegno di questo tratto: la gara si guarda di piu',
            # i tratti di una giornata spezzata di meno
            sec = (args.draw_sec * 1.7 if race else
                   args.draw_sec if len(story["legs"]) == 1 else
                   max(3.5, args.draw_sec * 0.72))
            # la camera stringe solo se c'e' una traccia sola da seguire: in gara
            # servono tutte e cinque nell'inquadratura, o non c'e' confronto
            zmax = 1.0 if race else args.zdraw

            # quota-colore solo dove il giorno sale davvero: sotto i 12 m/km la
            # rampa direbbe "pianura" con sei verdi diversi, e resta l'accento
            lg = l["leg"]
            elev = (not race and bool(lg.get("alt"))
                    and lg.get("km", 0) > 0
                    and lg.get("gain", 0) / float(lg["km"]) >= 12.0)
            # dislivello cumulato lungo il tratto, per il contatore di destra
            alt = lg.get("alt") or []
            gc = [0.0]
            for j in range(1, len(alt)):
                d = alt[j] - alt[j - 1]
                gc.append(gc[-1] + (d if d > 0 else 0.0))

            def counters(p):
                if race:
                    return None
                i, _ = R.head_at(l["pts"], l["cum"], p)
                km = km_before + l["cum"][-1] * p / 1000.0
                gain = gain_before + (gc[min(i, len(gc) - 1)] if alt else
                                      lg.get("gain", 0) * p)
                secs = secs_before + p * (lg.get("secs") or 0)
                return {"km": ("%d km" % round(km)) if km >= 100
                               else ("%.1f km" % km).replace(".", ","),
                        "kml": "PERCORSI · " + R.hm(secs).upper(),
                        "gain": R.thou(gain) + " m", "gainl": "DI SALITA"}

            # --- i testi in corsa: LA STORIA, non i numeri (round 3). Le righe
            # del racconto (beats) cadono al loro momento della giornata, le
            # citazioni dal diario restano dove sono successe; ogni testo vive
            # un secondo e mezzo — di piu' solo se e' lungo — e NON ferma niente.
            if race:
                ovs = [(st["beat_at"][b], st["beats"][b])
                       for b in range(1, len(st["beats"]))]
            else:
                ovs = [((bt - lg["t0"]) / lg["dt"], st["beats"][b])
                       for b in range(1, len(st["beats"]))
                       for bt in [st["beat_at"][b]]
                       if lg["t0"] <= bt < lg["t0"] + lg["dt"] - 1e-9]
                # TUTTE le note, ognuna al suo ancoraggio vero ("top" = la vetta
                # registrata): il commento nasce nel punto di cui parla
                ovs += [(R.note_at(l, nt), nt["text"])
                        for nt in (l["leg"].get("notes") or [])]

            # dove sta il punto piu' alto del tratto, in frazione di percorso:
            # e' li' che la camera si tuffa, come la candidata S01 del laboratorio
            if alt:
                ti = max(range(len(alt)), key=lambda x: alt[x])
                topf = l["cum"][min(ti, len(l["cum"]) - 1)] / (l["cum"][-1] or 1.0)
            else:
                topf = 0.5
            dive_c = topf if elev else 0.5
            zpeak = min(args.zdraw, 2.0 if elev else 1.8)

            def cam(p):
                """Camera FERMA, con un solo tuffo calmo — la ricetta del
                laboratorio (S01), non l'inseguimento continuo della v3.

                Il tuffo e' una gaussiana attorno al punto piu' alto (o a meta',
                in pianura): 2× in vetta, 1,8× altrove, e per tutto il resto del
                tratto l'inquadratura non si muove. Oltre a essere la camera
                votata, e' quella che la GIF si puo' permettere: un frame a
                camera ferma scrive solo la linea che avanza e i contatori,
                uno a camera mobile riscrive l'intero quadro.
                """
                if zmax <= 1.0:
                    return 1.0, 0.0
                import math
                f = math.exp(-((p - dive_c) ** 2) / (2 * 0.06 ** 2))
                f = R.ease(min(1.0, f * 1.15))
                return R.lerp(1.0, zpeak, f), f

            def shot(p, fz=0.0, ztxt=1.8, cam_p=None):
                z, fo = cam(p)
                # lo stacco sul commento vince sul tuffo di vetta solo se stringe
                # di piu' (e mai in gara, dove servono tutte e cinque le tracce)
                if zmax > 1.0 and fz > 0.0:
                    z2 = R.lerp(1.0, ztxt, fz)
                    if z2 >= z:
                        return R.map_frame(story, li, p, z2, S, fonts,
                                           cap_alpha=1.0, total=total, follow=fz,
                                           caption="", elev=elev,
                                           counters=counters(p), cam_p=cam_p)
                return R.map_frame(story, li, p, z, S, fonts, cap_alpha=1.0,
                                   total=total, follow=fo, caption="",
                                   elev=elev, counters=counters(p))

            # la riga del tratto apre il flusso (la scheda l'ha gia' detta per il
            # primo tratto: solo dal secondo in poi)
            line = lg.get("line")
            if line and li > 0 and not race:
                ovs.append((0.04, line))
            ovs.sort(key=lambda x: x[0])
            # ogni testo vive il tempo che la sua lunghezza chiede (1,6–3,6 s);
            # gli ancoraggi restano i loro, la coda si gestisce da sola: se un
            # commento e' ancora in scena quando il puntino passa il prossimo
            # ancoraggio, il prossimo parte appena il primo ha finito
            timed, prev_at = [], -1.0
            for at, txt in ovs:
                # niente emoji in sovrimpressione: con l'alone a 24 passate un
                # glifo colorato diventa un francobollo scuro
                txt = R.plain(txt) or txt
                at = min(max(at, 0.03), 0.94)
                if at <= prev_at + 0.01:
                    at = prev_at + 0.01
                    if at > 0.94:
                        continue
                timed.append((at, max(1.6, min(3.6, 1.2 + 0.14 * len(txt.split()))), txt))
                prev_at = at

            # apertura del tratto sull'inquadratura intera, per leggere la forma
            emit(shot(0.005), 700 if li == 0 else 400)

            # --- il disegno, a orologio: piena velocita' quando la mappa parla da
            # sola, 45% quando c'e' un commento da leggere (round 4: "use slow
            # down needed for comments"). Sul commento la camera STACCA su dove il
            # commento e' nato — tanto piu' vicino quanto piu' il testo e' lungo —
            # resta ferma li' mentre si legge, poi riapre. Ferma, non a
            # inseguimento: e' la camera votata, ed e' quella che la GIF regge.
            TR = 0.30                          # transizione dello stacco, secondi
            base = 1.0 / (sec * args.fps)      # avanzamento p a piena velocita'
            p, oi, act = 0.004, 0, None
            guard = int(args.fps * 150)
            while p < 0.9995 and guard > 0:
                guard -= 1
                if act is not None and act["u"] >= act["dur"] + TR:
                    act = None
                if act is None and oi < len(timed) and p >= timed[oi][0]:
                    at, dur, txt = timed[oi]; oi += 1
                    act = {"txt": txt, "dur": dur, "u": 0.0, "lock": p,
                           "z": 1.55 + min(0.75, 0.04 * len(txt.split()))}
                if act is not None:
                    act["u"] += 1.0 / args.fps
                    u = act["u"]
                    fz = min(1.0, u / TR, max(0.0, (act["dur"] + TR - u) / TR))
                    a = min(1.0, u / 0.35, max(0.0, (act["dur"] - u) / 0.35))
                    p = min(1.0, p + base * 0.45)
                    fr = shot(p, fz=R.ease(fz), ztxt=act["z"], cam_p=act["lock"])
                    if a > 0:
                        fr = center_text(fr, S, fonts, act["txt"], ac, a)
                    emit(fr, FMS)
                else:
                    p = min(1.0, p + base)
                    emit(shot(p), FMS)

            # --- il giro finito, a inquadratura piena (la camera ci e' gia':
            # il tuffo si e' riassorbito da solo sulla coda della gaussiana)
            end = R.map_frame(story, li, 1.0, 1.0, S, fonts, total=total,
                              follow=0.0, caption="", elev=elev, counters=counters(1.0))
            emit(end, args.hold if li == len(story["legs"]) - 1 else args.hold_leg)
            prev_map = end
            km_before += l["cum"][-1] / 1000.0
            gain_before += gc[-1] if alt else lg.get("gain", 0)
            secs_before += lg.get("secs") or 0

    # --- finale
    moving(nf(0.5), lambda t: R.to_paper(prev_map, R.ease(t), S))
    page(lambda a: R.text_card(S, fonts, a,
                               [("2015 – 2026", "kicker"), ("Venti giorni", "big"),
                                ("su 2.923", "big"),
                                ("Il resto è nell'archivio: micmer-git.github.io", "body")],
                               credit_too=True),
         read_ms("Venti giorni su 2.923",
                 "Il resto è nell'archivio: micmer-git.github.io", base=1600),
         sec_out=0.6)


# ------------------------------------------------------------------ il file

class Video:
    """Frame + durata in ms → un mp4 a passo costante.

    Si rende una volta sola ogni immagine **diversa** e si riscrive tante volte
    quanti frame di video occupa: un fermo-immagine di cinque secondi sono 150
    frame nel file ma una sola resa, che e' la parte cara. Il resto del debito lo
    paga il codec, che su frame identici spende quasi niente.
    """

    def __init__(self, path, S, fps):
        import cv2
        import numpy as np
        self.cv2, self.np, self.S, self.fps = cv2, np, S, fps
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (S, S))
        if not self.w.isOpened():
            raise SystemExit("VideoWriter non si apre: %s" % path)
        self.path, self.n, self.uniq, self.carry = path, 0, 0, 0.0

    def __call__(self, im, ms):
        bgr = self.cv2.cvtColor(self.np.asarray(im.convert("RGB")),
                                self.cv2.COLOR_RGB2BGR)
        # il resto frazionario si porta avanti, o su un video lungo la somma degli
        # arrotondamenti sposta la fine di qualche secondo
        self.carry += ms / 1000.0 * self.fps
        reps = int(self.carry)
        self.carry -= reps
        for _ in range(max(1, reps)):
            self.w.write(bgr)
        self.n += max(1, reps)
        self.uniq += 1

    def close(self):
        self.w.release()
        mb = os.path.getsize(self.path) / 1e6
        print("\n%d frame di video (%d resi), %.0f s, %.1f MB — %s"
              % (self.n, self.uniq, self.n / float(self.fps), mb, self.path))


class Gif:
    """Lo stesso montaggio, riversato in GIF. Non e' una conversione del file.

    Convertire l'mp4 sarebbe il modo peggiore: si ricomprimerebbe roba gia'
    compressa, e soprattutto si partirebbe da 30 fps costanti, che in GIF vuol
    dire pagare per intero anche i cinque secondi in cui non si muove niente. Qui
    si intercettano gli **stessi frame** prima dell'encoder e si fa il contrario:

    - **le pause tornano un frame solo** con la durata giusta, che e' l'unica cosa
      che la GIF regala e il video no;
    - **il movimento si decima** a `gif_fps`, perche' trenta passi al secondo su
      una traccia che si disegna sono invisibili e costano un frame l'uno;
    - i frame identici di fila si fondono in uno.

    In piu' la GIF esce piu' piccola del video: il testo regge la riduzione, la
    mappa pure, e il conto dei byte no.
    """

    HOLD = 200          # oltre questa soglia un frame e' una pausa, non movimento

    def __init__(self, path, S, gif_fps, colors):
        self.path, self.S, self.colors = path, S, colors
        self.step = 1000.0 / gif_fps
        self.frames, self.durs = [], []
        self.buf, self.acc = None, 0.0

    def _push(self, im, ms):
        # frame identico al precedente: si allunga quello invece di aggiungerne uno
        if self.frames and im.tobytes() == self.frames[-1].tobytes():
            self.durs[-1] += ms
        else:
            self.frames.append(im)
            self.durs.append(ms)

    def __call__(self, im, ms):
        small = im if im.size == (self.S, self.S) else im.resize((self.S, self.S),
                                                                 Image.LANCZOS)
        if ms >= self.HOLD:
            if self.buf is not None:
                self._push(self.buf, self.acc)
                self.buf, self.acc = None, 0.0
            self._push(small, ms)
            return
        self.buf, self.acc = small, self.acc + ms
        if self.acc >= self.step:
            self._push(self.buf, self.acc)
            self.buf, self.acc = None, 0.0

    def close(self):
        if self.buf is not None:
            self._push(self.buf, self.acc)
        fr, du = self.frames, [max(20, int(round(d))) for d in self.durs]
        # la tavolozza si prende su un campione sparso su tutto il montaggio: da un
        # frame solo i quattro accenti collassano nello stesso grigio
        step = max(1, len(fr) // 40)
        sample = Image.new("RGB", (self.S, self.S * len(fr[::step])), BG)
        for i, f in enumerate(fr[::step]):
            sample.paste(f, (0, i * self.S))
        pal = R.fixed_palette(sample, self.colors)
        q = R.punch_holes([f.quantize(palette=pal, dither=Image.NONE) for f in fr],
                          self.colors)
        q[0].save(self.path, save_all=True, append_images=q[1:], loop=0, duration=du,
                  optimize=False, disposal=1, transparency=self.colors)
        print("%d frame di GIF, %.0f s, %.1f MB — %s"
              % (len(q), sum(du) / 1000.0, os.path.getsize(self.path) / 1e6, self.path))


class Both:
    """Un solo giro di resa, due file: il video pieno e la GIF ridotta."""

    def __init__(self, *targets):
        self.targets = [t for t in targets if t is not None]

    def __call__(self, im, ms):
        for t in self.targets:
            t(im, ms)

    def close(self):
        for t in self.targets:
            t.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=760, help="lato del video")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--px", type=int, default=2400,
                    help="lato del mosaico basemap. Deve stare sopra size*zdraw o "
                         "la mappa si ingrandisce da sola e sfoca")
    ap.add_argument("--style", default="light_nolabels")
    ap.add_argument("--draw-sec", type=float, default=8.0,
                    help="quanto ci mette una traccia intera a disegnarsi — otto "
                         "secondi, che ora sono anche il palco dei testi in corsa")
    ap.add_argument("--zdraw", type=float, default=2.2,
                    help="quanto stringe la camera mentre insegue il puntino")
    ap.add_argument("--cardin-sec", type=float, default=1.5,
                    help="quanto ci mette la scheda del giorno a montarsi")
    ap.add_argument("--fly-sec", type=float, default=1.8,
                    help="il volo basso fra due storie")
    ap.add_argument("--fly-px", type=int, default=1500,
                    help="lato del mosaico del volo di trasferimento")
    ap.add_argument("--hold-leg", type=int, default=700, help="pausa a fine tratto")
    ap.add_argument("--hold", type=int, default=1500, help="pausa a fine giornata")
    ap.add_argument("--only", help="solo queste storie, numerate da 1: 1,17,18")
    ap.add_argument("--intro", action="store_true",
                    help="tieni apertura e finale anche con --only")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--gif", nargs="?", const=OUT.replace(".mp4", "-v4.gif"),
                    help="scrivi anche la GIF, dagli stessi frame, ridotti")
    ap.add_argument("--gif-size", type=int, default=400, help="lato della GIF")
    ap.add_argument("--gif-fps", type=float, default=8.0,
                    help="passo del movimento in GIF: le pause restano lunghe comunque. "
                         "Otto e non dieci: nella v4 anche note e voli sono quadri in "
                         "movimento, e a dieci il file sfora i trenta MB")
    ap.add_argument("--colors", type=int, default=44)
    args = ap.parse_args()

    S = args.size
    allst = R.load_stories()
    fonts = (font("arialbd.ttf", int(S * 0.023)), font("georgia.ttf", int(S * 0.050)),
             font("arial.ttf", int(S * 0.0335)), font("arialbd.ttf", int(S * 0.0225)),
             font("arial.ttf", int(S * 0.0165)), font("seguiemj.ttf", int(S * 0.034)),
             font("seguiemj.ttf", int(S * 0.022)), font("georgia.ttf", int(S * 0.078)),
             font("arial.ttf", int(S * 0.031)), font("arialbd.ttf", int(S * 0.0245)),
             font("georgiai.ttf", int(S * 0.0345)), font("georgia.ttf", int(S * 0.062)))

    pick = allst
    if args.only:
        pick = [allst[int(x) - 1] for x in args.only.split(",")]

    if args.px < S * args.zdraw:
        print("attenzione: px %d < size*zdraw %d — la mappa sfochera' nello zoom"
              % (args.px, int(S * args.zdraw)))
    print("mosaici basemap (%d px, %s):" % (args.px, args.style))
    stories = R.prepare(pick, args.px, args.style)

    out = Both(Video(args.out, S, args.fps),
               Gif(args.gif, args.gif_size, args.gif_fps, args.colors) if args.gif else None)
    t0 = time.time()
    build(stories, S, fonts, args, out)
    out.close()
    print("resa in %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
