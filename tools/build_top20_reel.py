#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_top20_reel.py — the one GIF: twenty days, one continuous flight.

This is the LinkedIn deliverable. Unlike build_top20_gif.py (a flat contact-sheet
of twenty separate cards) this is a single sequential reel: every path draws on a
real map, and between one day and the next the camera pulls back to an
orthographic globe, rotates, and dives into the next place. The globe keeps the
dots of everywhere already visited, so it doubles as the progress bar.

**Ogni blocco di testo resta in campo almeno cinque secondi.** Venti cartoline
piu' venticinque note fanno da sole 3'45" di testo fermo: e' il vincolo che decide
la durata, non l'animazione. Il taglio lungo dura 6'21" (1.216 frame, 380 px,
5,7 MB), quello corto — nove giorni, `--only 1,8,9,13,15,17,18,19,20 --intro` —
dura 3'21" e pesa 3,5 MB, ed e' quello che ha senso su LinkedIn.

Tenere fermo un frame non costa niente, quindi la lentezza e' gratis; aggiungere
frame no. Di qui i due orologi: `--ms` (105 ms) e' il passo del disegno GPS e non
si tocca, `--ms-move` (80 ms) e' tutto quello che collega — globo, zoom,
dissolvenze — perche' e' collegamento e non racconto.

Ogni giorno apre su una cartolina in prosa (`card` nel config, scritta a mano) e
non sul titolo dell'attivita', che messo in colonna coi suoi campi si leggeva come
un dump di database. Poi, mentre la traccia corre, le `note` compaiono in margine:
senza `zoom` costano il rettangolo del testo e basta, quindi ce ne sono molte; con
`zoom` la camera scende sul puntino, e quelle sono otto. In entrambi i casi il
disegno si ferma sulla nota per il tempo di leggerla. E la Maratona dles Dolomites
non e' un giorno ma cinque: `mode: "race"` le fa partire insieme, ognuna col passo
di quell'anno.

    python build_top20_reel.py                    # tutto il reel
    python build_top20_reel.py --only 1,17,18     # solo alcune storie (numerate da 1)
    python build_top20_reel.py --probe 17         # un provino PNG a sei riquadri
    python build_top20_reel.py --card 3500        # cartoline piu lente, stesso peso

Reads `top-20/_data.js` — the same data as the page and the contact sheet, so the
three cannot disagree. Basemap tiles and the globe come from tools/basemap.py, and
carry its attribution; do not remove the credit line from the corner.

Three things worth knowing before changing it:

* **One caption per leg, not five.** The page gives every day five beats. Twenty
  days times five beats is a hundred sentences, and a sentence needs two seconds
  to read: that reel would run three and a half minutes. The reel shows each
  leg's `line` instead, which is why the multi-day stories (the clavicle's four
  legs, Bologna's two) carry the most text — the text follows the camera moves.
* **Solo i frame che contengono la basemap a una scala nuova costano.** Un frame
  di globo e una cartolina di testo stanno a 5 kB, un frame di mappa a scala nuova
  a 40. Per questo il tratto graduale dello zoom lo fa il globo, che cresce da un
  puntino e ruota, mentre la mappa entra negli ultimi tre frame. Misurare prima di
  cambiare: `python gifweigh.py <file>`.
* **Tracks are drawn at mosaic resolution and downscaled.** Pillow does not
  antialias lines, and an aliased track over a photographic basemap looks like a
  mistake. Drawing into the full-resolution crop and resizing at the end is what
  makes the line look drawn rather than pasted, so line widths are specified in
  final pixels and scaled up by the crop ratio.
"""
import argparse
import io
import json
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import basemap as BM                                                  # noqa: E402
from build_top20_gif import (AC, BG, INK, INK2, INK3, RULE, blend,     # noqa: E402
                             draw_text, font, is_emoji, load_stories, text_w, wrap)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = os.path.join(HERE, "..", "top-20", "top-20-reel.gif")
# Nel reel gli sport si scrivono, non si disegnano: a 96 colori un emoji di venti
# pixel diventa una macchia scura, e la tavolozza serve alla mappa e agli accenti.
SPORT = {"bike": "in bici", "run": "di corsa", "swim": "a nuoto"}

# Le tinte della gara: cinque edizioni sulla stessa mappa devono distinguersi fra
# loro E sulla carta crema. Sono riservate in tavolozza come gli accenti, o la
# median-cut le fonde in due grigi (e' quello che era successo a Malaga).
RACE_TINTS = [(194, 118, 26), (59, 91, 181), (77, 114, 56), (138, 90, 60), (150, 60, 110)]

# La rampa di quota del laboratorio (V05 votata 9, poi la "candidata" S01): la
# linea si scurisce salendo, verde valle → verde passo. Sei gradini DISCRETI e
# non un gradiente: ogni gradino e' uno slot di tavolozza riservato in
# fixed_palette, e sei bastano a leggere una salita. Si usa solo dove il giorno
# ha dislivello vero (vedi la soglia in build_top20_video); in pianura la quota
# non racconta niente e resta il colore d'accento.
RAMP = [(207, 224, 189), (172, 198, 148), (137, 171, 108),
        (103, 144, 71), (68, 106, 42), (34, 64, 15)]


def ramp_col(u):
    return RAMP[min(len(RAMP) - 1, max(0, int(u * len(RAMP))))]


def plain(t):
    """Il testo senza emoji, per le righe piccole della barra dei dati."""
    return "".join(c for c in t if not is_emoji(c)).replace("  ", " ").strip(" —·-")


# ------------------------------------------------------------------ tipografia
#
# Tre cose fanno la differenza fra "testo su un'immagine" e una pagina composta:
# le maiuscolette spaziate per le etichette, un filetto che separa invece di uno
# spazio vuoto, e il corsivo per le citazioni. Pillow non ha nulla di tutto
# questo, quindi sono tre funzioni qui sotto.

def tracked_w(dr, text, fnt, track):
    return sum(dr.textlength(c, font=fnt) for c in text) + track * max(0, len(text) - 1)


def draw_tracked(dr, xy, text, fnt, fill, track):
    """Maiuscolette spaziate. Senza spaziatura una riga tutta in maiuscolo si
    legge come un blocco pieno; con due pixel fra le lettere diventa un'etichetta."""
    x, y = xy
    for c in text:
        dr.text((x, y), c, font=fnt, fill=fill)
        x += dr.textlength(c, font=fnt) + track
    return x


def rule(dr, x0, y, x1, colour, w=1):
    dr.rectangle([x0, y, x1, y + w - 1], fill=colour)


def is_quote(t):
    return t.lstrip().startswith(("«", '"', "“"))


# ------------------------------------------------------------------ geometria

def decode(leg):
    pts, x, y, d = [], 0, 0, leg["d"]
    for i in range(0, len(d), 2):
        x += d[i]
        y += d[i + 1]
        pts.append((leg["lat0"] + x * 1e-5, leg["lng0"] + y * 1e-5))
    return pts


def arclen_ll(pts):
    """Cumulative metres along a lat/lng polyline."""
    cum = [0.0]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        kx = 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
        cum.append(cum[-1] + math.hypot((b[1] - a[1]) * kx, (b[0] - a[0]) * 110540.0))
    return cum


def head_at(pts, cum, p):
    total = cum[-1] or 1.0
    target = total * min(1.0, max(0.0, p))
    lo, hi = 0, len(cum) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum[mid] <= target:
            lo = mid
        else:
            hi = mid
    span = cum[hi] - cum[lo]
    f = (target - cum[lo]) / span if span > 0 else 0.0
    return lo, (pts[lo][0] + (pts[hi][0] - pts[lo][0]) * f,
                pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f)


def bounds(list_of_pts):
    lats = [q[0] for pts in list_of_pts for q in pts]
    lngs = [q[1] for pts in list_of_pts for q in pts]
    return min(lats), max(lats), min(lngs), max(lngs)


ease = lambda t: t * t * (3 - 2 * t)
lerp = lambda a, b, t: a + (b - a) * t


def hm(secs):
    secs = int(secs)
    if secs < 3600:
        return "%d min" % (secs // 60)
    return "%dh%02d" % (secs // 3600, secs % 3600 // 60)


def thou(n):
    return format(int(round(n)), ",").replace(",", ".")


# ------------------------------------------------------------------ preparazione

def prepare(stories, px, style, margin=1.62):
    """Per-leg polylines, per-leg (or per-story) basemap mosaics, globe centres.

    `margin` is generous on purpose. The header panel and the caption band together
    cover about the top and bottom sixth of the frame, so a route fitted to the
    full square gets its start and finish hidden under the text — in the first
    Bologna probe the ride's start in Bergamo sat under the title. 1.5 keeps the
    whole route inside the clear middle.
    """
    out = []
    for n, st in enumerate(stories, 1):
        legs = []
        for lg in st["legs"]:
            pts = decode(lg)
            legs.append({"pts": pts, "cum": arclen_ll(pts), "leg": lg})
        all_pts = [l["pts"] for l in legs]

        def boxfor(sel):
            la0, la1, lo0, lo1 = bounds(sel)
            dla = max(la1 - la0, 0.004) * margin
            dlo = max(lo1 - lo0, 0.004) * margin
            cla, clo = (la0 + la1) / 2, (lo0 + lo1) / 2
            # il riquadro si tiene quadrato in gradi corretti per la latitudine,
            # o una traccia nord-sud viene schiacciata dentro un frame quadrato
            k = math.cos(math.radians(cla)) or 1.0
            half = max(dla, dlo * k) / 2
            return cla - half, cla + half, clo - half / k, clo + half / k

        story_box = boxfor(all_pts)
        story_mos = None
        for l in legs:
            if l["leg"].get("frame") == "all":
                if story_mos is None:
                    story_mos = BM.mosaic(*story_box, px=px, style=style)
                l["mos"], l["box"] = story_mos, story_box
            else:
                box = boxfor([l["pts"]])
                l["mos"], l["box"] = BM.mosaic(*box, px=px, style=style), box
        la0, la1, lo0, lo1 = story_box
        out.append({"st": st, "n": n, "legs": legs,
                    "clat": (la0 + la1) / 2, "clon": (lo0 + lo1) / 2})
        print("  %02d %-22s %d tratti" % (n, st["slug"], len(legs)))
    return out


# ------------------------------------------------------------------ disegno

def map_frame(story, li, p, zoomf, S, fonts, cap_alpha=1.0, chrome=True,
              total=20, follow=None, caption=None, note=None, note_alpha=1.0,
              side=None, elev=False, counters=None):
    """One map frame: the leg `li` of `story` drawn to fraction `p`, at zoom `zoomf`."""
    legs = story["legs"]
    act = legs[li]
    race = story["st"].get("mode") == "race"
    img, to_px = act["mos"]
    la0, la1, lo0, lo1 = act["box"]
    ac = AC.get(story["st"]["accent"], AC["stone"])

    # riquadro pieno in pixel di mosaico, poi stretto di zoomf attorno al puntino
    x0, y0 = to_px(la1, lo0)
    x1, y1 = to_px(la0, lo1)
    full_w, full_h = x1 - x0, y1 - y0
    span = min(full_w, full_h)          # non "side": e' il nome del parametro
    i, h = head_at(act["pts"], act["cum"], p)
    hx, hy = to_px(*h)
    cw = span / zoomf
    fo = follow if follow is not None else (zoomf - 1) / max(zoomf, 1e-6)
    cx = lerp((x0 + x1) / 2, hx, fo)
    cy = lerp((y0 + y1) / 2, hy, fo)
    cx = min(max(cx, x0 + cw / 2), x1 - cw / 2) if full_w > cw else (x0 + x1) / 2
    cy = min(max(cy, y0 + cw / 2), y1 - cw / 2) if full_h > cw else (y0 + y1) / 2
    box = (int(cx - cw / 2), int(cy - cw / 2), int(cx + cw / 2), int(cy + cw / 2))
    # ...e poi dentro il mosaico. Il vincolo sopra tiene la camera dentro il
    # riquadro del percorso, che NON e' la stessa cosa: il riquadro ha un margine
    # attorno (`prepare(margin=)`) e su una traccia stretta e lunga puo' sporgere
    # dal mosaico. Fuori dai bordi `crop()` riempie di NERO, che su carta crema si
    # vede da un chilometro. Non capitava finche' la camera stava ferma al centro;
    # con l'inseguimento del video capita a ogni tratto che finisca sul bordo.
    mw, mh = img.size
    dx = min(0, mw - box[2]) - min(0, box[0])
    dy = min(0, mh - box[3]) - min(0, box[1])
    box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)

    crop = img.crop(box).convert("RGBA")
    K = crop.size[0] / float(S)                     # da pixel finali a pixel di crop
    lay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    off = lambda q: (to_px(*q)[0] - box[0], to_px(*q)[1] - box[1])

    def stroke(pts, colour, w, a):
        if len(pts) > 1:
            dr.line(pts, fill=colour + (a,), width=max(1, int(round(w * K))), joint="curve")

    def dot(px, py, colour, scale=1.0):
        for rad, a in ((11 * K * scale, 60), (6.0 * K * scale, 130)):
            dr.ellipse([px - rad, py - rad, px + rad, py + rad], fill=colour + (a,))
        r = 4.3 * K * scale
        dr.ellipse([px - r, py - r, px + r, py + r], fill=colour + (255,),
                   outline=(255, 255, 255, 255), width=max(1, int(round(1.7 * K))))

    if race:
        # Cinque edizioni della stessa corsa, partite nello stesso istante.
        #
        # Due cose la rendono leggibile come una gara. La prima: l'orologio e' uno
        # per tutte. Dando a ognuna la stessa FRAZIONE del proprio percorso
        # arrivavano tutte insieme, che non e' una gara — qui ognuna avanza col
        # passo che aveva quell'anno, quindi i due percorsi corti finiscono a un
        # terzo dell'animazione e restano fermi ad aspettare i lunghi.
        # La seconda: uno scostamento di un paio di pixel per edizione. Corto,
        # medio e lungo condividono le prime salite, quindi sulla stessa strada
        # l'ultima disegnata copriva le altre quattro e si vedevano solo due tracce.
        tmax = max((l["leg"]["secs"] or 1) for l in legs)
        for j, l in enumerate(legs):
            tint = RACE_TINTS[j % len(RACE_TINTS)]
            ang = 2 * math.pi * j / float(len(legs))
            ox, oy = math.cos(ang) * 3.2 * K, math.sin(ang) * 3.2 * K
            shift = lambda q: (off(q)[0] + ox, off(q)[1] + oy)
            stroke([shift(q) for q in l["pts"]], INK3, 1.2, 38)
            jp = min(1.0, p * tmax / float(l["leg"]["secs"] or 1))
            ji, jh = head_at(l["pts"], l["cum"], jp)
            dn = [shift(q) for q in l["pts"][:ji + 1]] + [shift(jh)]
            stroke(dn, tint, 2.3, 240)
            hx2, hy2 = shift(jh)
            dot(hx2, hy2, tint, 0.72 if jp < 1.0 else 0.55)
    else:
        for j, l in enumerate(legs):                # i tratti già fatti restano a terra
            if j == li:
                continue
            stroke([off(q) for q in l["pts"]], ac if j < li else INK3, 2.0,
                   150 if j < li else 45)
        stroke([off(q) for q in act["pts"]], INK3, 1.6, 60)      # il tratto intero
        done = [off(q) for q in act["pts"][:i + 1]] + [off(h)]
        alt = act["leg"].get("alt") or []
        if elev and len(alt) >= 2:
            # la quota come colore (lab: V05→S01): l'alone resta uno, la traccia
            # si disegna a segmenti col gradino di rampa della quota locale
            amin, amax = min(alt), max(alt)
            rng = max(1.0, amax - amin)
            stroke(done, RAMP[2], 6.5, 45)
            wpx = max(1, int(round(2.8 * K)))
            for j in range(1, len(done)):
                u = (alt[min(j, len(alt) - 1)] - amin) / rng
                dr.line([done[j - 1], done[j]], fill=ramp_col(u) + (255,),
                        width=wpx, joint="curve")
            hc = ramp_col((alt[min(i, len(alt) - 1)] - amin) / rng)
        else:
            stroke(done, ac, 6.5, 55)                            # alone
            stroke(done, ac, 2.8, 255)                           # traccia
            hc = ac
        sx, sy = off(act["pts"][0])
        r = 3.4 * K
        dr.ellipse([sx - r, sy - r, sx + r, sy + r], fill=BG + (255,), outline=ac + (255,),
                   width=max(1, int(round(1.6 * K))))
        dot(*off(h), hc)

    frame = Image.alpha_composite(crop, lay).resize((S, S), Image.LANCZOS)
    if not race:
        place_labels(frame, act, box, to_px, S, fonts, ac,
                     reserve=side["rect"] if side else None)
    if chrome:
        chrome_over(frame, story, li, S, fonts, cap_alpha, total, caption, race,
                    counters)
    if side:
        side_column(frame, S, fonts, ac, side["rect"], side.get("line"),
                    side.get("reveal", 1.0), note, note_alpha)
    return frame.convert("RGB")


def free_column(pts_frame, S):
    """Which side of the frame the text can occupy without sitting on the route.

    Notes used to be pinned to the right, centred, and on half the days that is
    exactly where the track is — the sentence landed on top of the thing it was
    about. Here both halves are scored by how much of the drawn route falls inside
    them, and the emptier one wins; ties go right, which reads better. Returns the
    column rect, computed once per leg from the *whole* route so the panel cannot
    drift from frame to frame while the dot moves.
    """
    pad = int(S * 0.045)
    w = int(S * 0.40)
    top, bot = int(S * 0.20), int(S * 0.845)      # sotto la testata, sopra la barra
    cands = [(S - pad - w, "destra"), (pad, "sinistra")]
    best, best_hits = None, None
    for x, side in cands:
        hits = sum(1 for (px, py) in pts_frame
                   if x - S * .02 < px < x + w + S * .02 and top - S * .02 < py < bot)
        if best_hits is None or hits < best_hits:
            best, best_hits = (x, top, w, side), hits
    return best


def side_column(frame, S, fonts, ac, rect, line=None, reveal=1.0,
                note=None, note_alpha=1.0):
    """The text column beside the route: the day's line, then any note.

    The line writes itself as the dot advances — `reveal` is the fraction of its
    words to show — so the sentence and the track finish together and there is
    something to follow in both halves of the frame at once. The note arrives
    later, under a rule, and stays.
    """
    f_kick, f_title, f_cap, f_stat, f_leg, f_emo, f_emos, f_big, f_sub = fonts[:9]
    f_ital = fonts[10]
    x, top, w, _side = rect
    # 0,080 = i 0,050 di rientro a sinistra (filetto d'accento compreso) piu' i
    # 0,030 a destra dove finisce la riga sopra la nota. Con 0,062 il testo
    # arrivava oltre il proprio filetto e a un pelo dal bordo del pannello.
    tx = x + int(S * 0.050)
    inner = w - int(S * 0.080)

    panel = frame.copy()
    dr = ImageDraw.Draw(panel)
    blocks = []
    if line:
        words = line.split()
        shown = " ".join(words[:max(1, int(round(len(words) * max(0.0, min(1.0, reveal)))))])
        f = f_ital if is_quote(line) else f_cap
        blocks.append(("line", wrap(dr, shown, f, f_emo, inner), f))
    if note and note_alpha > 0.02:
        f = f_ital if is_quote(note) else f_cap
        blocks.append(("note", wrap(dr, note, f, f_emo, inner)[:6], f))
    if not blocks:
        return

    lh = int(S * 0.047)
    h = int(S * 0.030)
    for kind, ls, _f in blocks:
        h += len(ls) * lh + (int(S * 0.046) if kind == "note" else int(S * 0.014))
    y = top

    scrim(panel, (x, y, x + w, y + h), int(S * 0.016), 234)
    dr = ImageDraw.Draw(panel)
    dr.rectangle([x + int(S * .022), y + int(S * .022),
                  x + int(S * .022) + max(2, int(S * 0.005)), y + h - int(S * .022)], fill=ac)
    ty = y + int(S * 0.020)
    for kind, ls, f in blocks:
        if kind == "note":
            rule(dr, tx, ty + int(S * 0.010), x + w - int(S * 0.030), RULE)
            draw_tracked(dr, (tx, ty + int(S * 0.020)), "NOTA", f_leg, ac, S * 0.006)
            ty += int(S * 0.046)
        for l in ls:
            draw_text(dr, (tx, ty), l, f, f_emo, INK if kind == "note" else INK2)
            ty += lh
        ty += int(S * 0.014)
    a = 1.0 if not note else max(0.0, min(1.0, max(note_alpha, 0.35 if line else 0.0)))
    frame.paste(Image.blend(frame.convert("RGB"), panel.convert("RGB"),
                            1.0 if line else a).convert("RGBA"))


def race_legend(frame, S, fonts, legs, ac):
    """Which colour is which year — the only way the race reads as a race."""
    f_kick, f_title, f_cap, f_stat, f_leg = fonts[:5]
    dr = ImageDraw.Draw(frame)
    pad = int(S * 0.050)
    rows = [(RACE_TINTS[j % len(RACE_TINTS)], plain(l["leg"]["label"]))
            for j, l in enumerate(legs)]
    lh = int(S * 0.042)
    w = int(S * 0.30)
    h = len(rows) * lh + int(S * 0.028)
    y = int(S * 0.30)
    scrim(frame, (pad, y, pad + w, y + h), int(S * 0.018), 226)
    dr = ImageDraw.Draw(frame)
    ty = y + int(S * 0.014)
    for tint, label in rows:
        r = S * 0.008
        cy = ty + lh * 0.32
        dr.ellipse([pad + int(S * .026) - r, cy - r, pad + int(S * .026) + r, cy + r], fill=tint)
        draw_text(dr, (pad + int(S * 0.050), ty), label, f_stat, fonts[6], INK2)
        ty += lh


def place_labels(frame, act, box, to_px, S, fonts, ac, reserve=None):
    """The only place names on the map, drawn after the downscale so they stay crisp.

    The basemap is the no-labels build: CARTO's own labels were the most expensive
    detail in the GIF and half of them were illegible at this size anyway, so the
    map is named by hand instead — start, finish, and the highest point, which is
    the pass the day was about. `places` in the config carries the names; the
    coordinates come from the track itself.

    `reserve` is the rect the text column will take. The panel is painted after
    these names and would simply bury them — on the Gavia day it swallowed "Passo
    dello Stelvio", which is the one word that day is about. So the name flips to
    the other side of its dot, exactly as it already does at the frame's edge.
    """
    f_leg, f_place = fonts[4], fonts[9]
    pl = act["leg"].get("places") or {}
    if not pl:
        return
    pts, alt = act["pts"], act["leg"]["alt"]
    marks = []
    if pl.get("from"):
        marks.append((pts[0], pl["from"], "start"))
    if pl.get("to"):
        marks.append((pts[-1], pl["to"], "end"))
    if pl.get("top") and alt:
        ti = max(range(len(alt)), key=lambda i: alt[i])
        marks.append((pts[min(ti, len(pts) - 1)], pl["top"], "top"))

    dr = ImageDraw.Draw(frame)
    K = (box[2] - box[0]) / float(S)
    for (lat, lng), name, kind in marks:
        mx, my = to_px(lat, lng)
        x, y = (mx - box[0]) / K, (my - box[1]) / K
        if not (-20 < x < S + 20 and -20 < y < S + 20):
            continue
        f = f_place
        w = dr.textlength(name, font=f)
        tx, ty = x + int(S * 0.018), y - int(S * 0.028)
        if tx + w > S - int(S * 0.05):                 # non uscire dal bordo destro
            tx = x - int(S * 0.018) - w
        ty = min(max(ty, int(S * 0.02)), S - int(S * 0.06))
        if reserve:
            rx, rtop, rw, _ = reserve
            lh = int(S * 0.032)
            hit = lambda a, b: a + w > rx and a < rx + rw and b + lh > rtop
            if hit(tx, ty):
                # 1. si ribalta dall'altra parte del puntino, come gia' fa al bordo
                alt = (x - int(S * 0.018) - w) if tx >= x else (x + int(S * 0.018))
                if not hit(alt, ty) and alt > int(S * 0.01):
                    tx = alt
                # 2. se nemmeno il puntino ha spazio — lo Stelvio sta proprio li' —
                #    il nome sale sopra la colonna, che e' a pochi pixel
                elif y - lh - int(S * 0.012) > int(S * 0.02) and y < rtop + S * 0.10:
                    ty = rtop - lh - int(S * 0.004)
                # 3. altrimenti non si disegna: mezza parola tagliata dal bordo del
                #    pannello si legge come un errore, un nome mancante no
                else:
                    continue
        # alone di carta: il nome deve leggersi anche sopra una città
        for ox in (-2, -1, 0, 1, 2):
            for oy in (-2, -1, 0, 1, 2):
                if ox or oy:
                    dr.text((tx + ox, ty + oy), name, font=f, fill=BG)
        dr.text((tx, ty), name, font=f, fill=INK if kind != "top" else blend(ac, .12))
        r = S * 0.0075
        dr.ellipse([x - r, y - r, x + r, y + r], fill=BG, outline=INK3, width=1)


def scrim(im, box, radius, alpha=214):
    """A soft paper panel, so text stays legible over any map."""
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(box, radius, fill=BG + (alpha,))
    im.alpha_composite(lay)


def corner_stats(frame, S, fonts, c):
    """I numeri vivi negli angoli in basso, in contrappunto (lab2: N02 dentro T05):
    la cifra grande in Georgia, l'etichetta in maiuscoletto spaziato sotto. Contano
    su mentre il puntino corre — km e tempo a sinistra, dislivello a destra — e
    prendono il posto della barra dei dati, che diceva le stesse cose ma da ferma."""
    f_leg, f_num = fonts[4], fonts[11]
    dr = ImageDraw.Draw(frame)
    pad = int(S * 0.050)
    for big, small, right in ((c["km"], c["kml"], False),
                              (c["gain"], c["gainl"], True)):
        w = dr.textlength(big, font=f_num)
        lw = tracked_w(dr, small, f_leg, S * 0.005)
        bw = max(w, lw)
        x = S - pad - bw if right else pad
        top = S - pad - int(S * 0.100)
        scrim(frame, (x - int(S * .020), top - int(S * .012),
                      x + bw + int(S * .020), S - pad + int(S * .016)),
              int(S * 0.018), 226)
        d2 = ImageDraw.Draw(frame)
        d2.text((x + bw - w if right else x, top), big, font=f_num, fill=INK)
        draw_tracked(d2, (x + bw - lw if right else x, top + int(S * 0.072)),
                     small, f_leg, INK3, S * 0.005)


def chrome_over(frame, story, li, S, fonts, cap_alpha, total, caption=None,
                race=False, counters=None):
    f_kick, f_title, f_cap, f_stat, f_leg, f_emo, f_emos, f_big, f_sub = fonts[:9]
    st = story["st"]
    ac = AC.get(st["accent"], AC["stone"])
    dr = ImageDraw.Draw(frame)
    pad = int(S * 0.050)

    # testata
    label = "%02d" % story["n"]
    kick = label + "  ·  " + st["kicker"].upper()
    tl = wrap(dr, st["title"], f_title, f_emo, S - 2 * pad - int(S * 0.10))[:2]
    h = int(S * 0.040) + len(tl) * int(S * 0.052) + int(S * 0.030)
    scrim(frame, (pad - int(S * .022), pad - int(S * .020),
                  pad + int(S * .022) + max(text_w(dr, kick, f_kick, f_emos),
                                            max(text_w(dr, t, f_title, f_emo) for t in tl)),
                  pad + h), int(S * 0.020))
    dr = ImageDraw.Draw(frame)
    x = draw_text(dr, (pad, pad), label, f_kick, f_emos, ac)
    draw_text(dr, (x, pad), "  ·  " + st["kicker"].upper(), f_kick, f_emos, INK3)
    for k, line in enumerate(tl):
        draw_text(dr, (pad, pad + int(S * 0.036) + k * int(S * 0.052)), line,
                  f_title, f_emo, INK)

    # avanzamento: venti tacche in alto a destra
    tw, gap = int(S * 0.013), int(S * 0.0065)
    bx = S - pad - (total * (tw + gap) - gap)
    for k in range(total):
        c = ac if k < story["n"] else RULE
        dr.rounded_rectangle([bx + k * (tw + gap), pad, bx + k * (tw + gap) + tw - 1,
                              pad + int(S * 0.010)], 2, fill=c)

    # In basso: o i contatori vivi negli angoli (v4, dal laboratorio 2) o la
    # vecchia barra dei dati. Mai tutti e due: direbbero le stesse cose.
    if counters is not None:
        corner_stats(frame, S, fonts, counters)
        if race:
            race_legend(frame, S, fonts, story["legs"], ac)
        credit(frame, S, f_leg)
        return

    # didascalia + statistiche in basso. La riga del PRIMO tratto l'ha già detta la
    # scheda a schermo pieno un attimo prima, quindi qui resta vuota: ripeterla
    # faceva leggere due volte la stessa frase e sembrava un errore di montaggio.
    # Dal secondo tratto in poi invece serve, ed è l'unico posto dove appare.
    # La riga del giorno non sta piu' qui ma nella colonna di fianco alla traccia,
    # dove si scrive mentre il puntino avanza. In basso restano solo i numeri.
    cl = []
    lg = story["legs"][li]["leg"]
    if race:
        stat = "cinque edizioni · tre percorsi · partenza insieme"
    elif len(story["legs"]) > 1:
        # I nomi dei tratti spesso contengono già i chilometri ("sabato — 234 km fino
        # a Bologna"): ripeterli subito dopo faceva "234 km · 234 km".
        lab = plain(lg["label"])
        km = ("%.1f" % lg["km"]).replace(".", ",") if lg["km"] < 100 else thou(lg["km"])
        bits = [lab] + ([] if " km" in lab else ["%s km" % km])
        bits += ["%s m D+" % thou(lg["gain"]), hm(lg["secs"])]
        stat = "   ·   ".join(bits)
    else:
        stat = "%s km   ·   %s m D+   ·   %s" % (thou(st["km"]), thou(st["gain"]),
                                                 hm(st["secs"]))
    band_h = int(S * 0.048) + int(S * 0.014)
    top = S - pad - band_h
    scrim(frame, (pad - int(S * .022), top - int(S * .020), S - pad + int(S * .022),
                  S - pad + int(S * .016)), int(S * 0.020))
    dr = ImageDraw.Draw(frame)
    draw_text(dr, (pad, top - int(S * .006)), stat, f_stat, f_emos, blend(ac, .18))
    a = max(0.0, min(1.0, cap_alpha))
    col = tuple(int(round(BG[j] + (INK[j] - BG[j]) * a)) for j in range(3))
    for k, l in enumerate(cl):
        draw_text(dr, (pad, top + int(S * 0.036) + k * int(S * 0.046)), l, f_cap, f_emo, col)

    if race:
        race_legend(frame, S, fonts, story["legs"], ac)
    credit(frame, S, f_leg)


def credit(frame, S, f):
    dr = ImageDraw.Draw(frame)
    t = BM.CREDIT
    w = dr.textlength(t, font=f)
    dr.text((S - int(S * 0.016) - w, S - int(S * 0.026)), t, font=f, fill=blend(INK3, .35))


def globe_frame(S, lat, lon, dots, fonts, upto, radius=0.86, title=None, sub=None,
                current=True):
    """The globe, with a dot for every day already visited."""
    f_kick, f_title, f_cap, f_stat, f_leg, f_emo, f_emos, f_big, f_sub = fonts[:9]
    im, project = BM.globe(S, lat, lon, radius_frac=radius)
    im = im.convert("RGBA")
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for k, (dlat, dlon, ac) in enumerate(dots):
        if k > upto:
            break
        x, y, vis = project(dlat, dlon)
        if not vis:
            continue
        cur = current and (k == upto)
        r = S * (0.013 if cur else 0.0075)
        if cur:
            dr.ellipse([x - r * 2.6, y - r * 2.6, x + r * 2.6, y + r * 2.6], fill=ac + (70,))
        dr.ellipse([x - r, y - r, x + r, y + r], fill=ac + (255,),
                   outline=(255, 255, 255, 220), width=2 if cur else 1)
    out = Image.alpha_composite(im, lay).convert("RGB")
    if title:
        dr = ImageDraw.Draw(out)
        pad = int(S * 0.050)
        for k, l in enumerate(wrap(dr, title, f_big, f_emo, S - 2 * pad)[:3]):
            draw_text(dr, (pad, pad + k * int(S * 0.085)), l, f_big, f_emo, INK)
        if sub:
            y = pad + int(S * 0.085) * len(wrap(dr, title, f_big, f_emo, S - 2 * pad)[:3]) + int(S * .01)
            for k, l in enumerate(wrap(dr, sub, f_sub, f_emo, S - 2 * pad)[:4]):
                draw_text(dr, (pad, y + k * int(S * 0.044)), l, f_sub, f_emo, INK2)
    credit(out, S, f_leg)
    return out


def ticks(im, n, total, S, ac, fonts):
    dr = ImageDraw.Draw(im)
    pad = int(S * 0.050)
    tw, gap = int(S * 0.013), int(S * 0.0065)
    bx = S - pad - (total * (tw + gap) - gap)
    for k in range(total):
        dr.rounded_rectangle([bx + k * (tw + gap), pad, bx + k * (tw + gap) + tw - 1,
                              pad + int(S * 0.010)], 2, fill=ac if k < n else RULE)


def text_card(S, fonts, alpha, lines, ac=None, n=None, total=20, credit_too=False):
    """A full-screen page of centred text, faded in by `alpha`.

    These carry the narration between one day and the next, and they are the
    cheapest frames in the reel: flat paper plus a block of type, so a two-and-a-
    half second pause on one costs a single frame's worth of bytes. That is what
    pays for the whole thing being slow enough to read — holding a frame is free,
    adding frames is not.

    `lines` is a list of (text, kind) with kind in {kicker, big, body, small}.
    """
    f_kick, f_title, f_cap, f_stat, f_leg, f_emo, f_emos, f_big, f_sub = fonts[:9]
    f_ital = fonts[10]
    # ogni riga: font, colore, interlinea, spazio dopo, spaziatura fra lettere
    SPEC = {"kicker": (f_kick, INK3, 0.048, 0.030, S * 0.006),
            "big": (f_big, INK, 0.092, 0.026, 0),
            "body": (f_sub, INK2, 0.050, 0.018, 0),
            "small": (f_stat, INK3, 0.040, 0.014, S * 0.004)}
    im = Image.new("RGB", (S, S), BG)
    lay = Image.new("RGBA", (S, S), BG + (0,))
    dr = ImageDraw.Draw(lay)
    pad = int(S * 0.115)
    RULE_H = int(S * 0.030)                 # aria attorno ai filetti

    laid, h = [], 0
    for text, kind in lines:
        f, col, lh, gap, track = SPEC[kind]
        # una citazione va in corsivo: e' la voce di quel giorno, non la nostra
        if kind == "body" and is_quote(text):
            f = f_ital
        ws = wrap(dr, text, f, f_emo, S - 2 * pad) if text else [""]
        laid.append((ws, f, col, int(S * lh), int(S * gap), track, kind))
        h += len(ws) * int(S * lh) + int(S * gap)
        if kind == "kicker":
            h += RULE_H
    y = (S - h) // 2
    for ws, f, col, lh, gap, track, kind in laid:
        for w in ws:
            tw = tracked_w(dr, w, f, track) if track else text_w(dr, w, f, f_emo)
            if track:
                draw_tracked(dr, ((S - tw) // 2, y), w, f, col, track)
            else:
                draw_text(dr, ((S - tw) // 2, y), w, f, f_emo, col)
            y += lh
        y += gap
        if kind == "kicker":
            # un filetto corto sotto la data: separa senza aggiungere parole
            rule(dr, S // 2 - int(S * 0.030), y + RULE_H // 2 - 1,
                 S // 2 + int(S * 0.030), (ac or INK3) + (255,))
            y += RULE_H

    a = max(0.0, min(1.0, alpha))
    out = Image.blend(im, Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB"), a)
    if n is not None:
        ticks(out, n, total, S, ac or INK3, fonts)
    if credit_too:
        credit(out, S, f_leg)
    return out


def story_card(S, fonts, st, n, total, prog, ac):
    """The day's opening page: date, the prose, and the numbers — full screen.

    Everything arrives in sequence rather than all at once, and the numbers count
    up to their value instead of being printed. That is what "animated text" can
    mean without adding a single expensive frame: these are flat pages of type, so
    a dozen of them cost what one map frame costs.
    """
    f_kick, f_title, f_cap, f_stat, f_leg, f_emo, f_emos, f_big, f_sub = fonts[:9]
    f_ital, f_num = fonts[10], fonts[11]
    im = Image.new("RGB", (S, S), BG)
    lay = Image.new("RGBA", (S, S), BG + (0,))
    dr = ImageDraw.Draw(lay)
    pad = int(S * 0.105)

    # ogni elemento ha la sua finestra dentro `prog`: entrano uno dopo l'altro
    def alpha(a0, a1):
        return max(0.0, min(1.0, (prog - a0) / max(1e-6, a1 - a0)))

    def ink(col, a):
        return tuple(int(round(BG[i] + (col[i] - BG[i]) * a)) for i in range(3))

    card = st.get("card") or [["date", st["kicker"]], ["lead", st["title"]]]
    date = next((t for k, t in card if k == "date"), st["kicker"])
    lead = next((t for k, t in card if k == "lead"), st["title"])
    body = next((t for k, t in card if k == "body"), "")

    # --- misure
    d_txt = "%02d · %s" % (n, date.upper())
    lead_ls = wrap(dr, lead, f_big, f_emo, S - 2 * pad)
    body_ls = wrap(dr, body, f_sub, f_emo, S - 2 * pad) if body else []
    stats = card_stats(st)
    h = (int(S * 0.048) + int(S * 0.030) + len(lead_ls) * int(S * 0.092)
         + int(S * 0.026) + len(body_ls) * int(S * 0.048)
         + int(S * 0.056) + int(S * 0.096))
    y = (S - h) // 2

    a = alpha(0.00, 0.18)
    tw = tracked_w(dr, d_txt, f_kick, S * 0.006)
    draw_tracked(dr, ((S - tw) // 2, y), d_txt, f_kick, ink(INK3, a), S * 0.006)
    y += int(S * 0.048)
    # il filetto si apre da centro verso i lati invece di comparire
    rw = int(S * 0.032 * alpha(0.10, 0.30))
    if rw:
        rule(dr, S // 2 - rw, y + int(S * 0.014), S // 2 + rw, ac + (255,))
    y += int(S * 0.030)
    for i, l in enumerate(lead_ls):
        a = alpha(0.16 + i * 0.07, 0.40 + i * 0.07)
        tw = text_w(dr, l, f_big, f_emo)
        draw_text(dr, ((S - tw) // 2, y), l, f_big, f_emo, ink(INK, a))
        y += int(S * 0.092)
    y += int(S * 0.026)
    fb = f_ital if is_quote(body) else f_sub
    for i, l in enumerate(body_ls):
        a = alpha(0.42 + i * 0.05, 0.62 + i * 0.05)
        tw = text_w(dr, l, fb, f_emo)
        draw_text(dr, ((S - tw) // 2, y), l, fb, f_emo, ink(INK2, a))
        y += int(S * 0.048)
    y += int(S * 0.056)

    # --- i numeri, che salgono fino al loro valore
    cu = alpha(0.55, 0.97)
    if stats:
        colw = (S - 2 * pad) // len(stats)
        for i, (label, value, kind) in enumerate(stats):
            cx = pad + colw * i + colw // 2
            shown = count_up(value, kind, cu)
            tw = dr.textlength(shown, font=f_num)
            dr.text((cx - tw / 2, y), shown, font=f_num, fill=ink(INK, min(1.0, cu * 1.4)))
            lw = tracked_w(dr, label.upper(), f_leg, S * 0.005)
            # 0,072 e non 0,058: i numeri sono Georgia a 0,062·S e l'etichetta
            # finiva dentro le cifre. Sotto la discendente, non addosso.
            draw_tracked(dr, (cx - lw / 2, y + int(S * 0.072)), label.upper(), f_leg,
                         ink(INK3, min(1.0, cu * 1.4)), S * 0.005)
    out = Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB")
    ticks(out, n, total, S, ac, fonts)
    return out


def card_stats(st):
    """The three or four numbers that describe the day, for its opening page."""
    if st.get("mode") == "race":
        return [("edizioni", len(st["legs"]), "int"),
                ("percorsi", 3, "int"),
                ("il più lungo", max(l["km"] for l in st["legs"]), "km")]
    days = len(set(l["date"] for l in st["legs"]))
    out = [("chilometri", st["km"], "km"), ("dislivello", st["gain"], "m"),
           ("in movimento", st["secs"], "hm")]
    if days > 1:
        out.append(("giorni" if days < 4 else "uscite", days, "int"))
    return out


def count_up(value, kind, t):
    """The value at `t` of its way up from zero, formatted as it will end."""
    t = max(0.0, min(1.0, t))
    v = value * t
    if kind == "km":
        return ("%.0f" % v) if value >= 100 else ("%.1f" % v).replace(".", ",")
    if kind == "m":
        return thou(v)
    if kind == "hm":
        return hm(v)
    return "%d" % round(v)


def to_paper(im, t, S):
    """The map dissolving into the page, so a card can take over from it."""
    return Image.blend(im, Image.new("RGB", (S, S), BG), max(0.0, min(1.0, t)))


def on_paper(im, k, S):
    """The frame, scaled by k, centred on the page.

    Resampled with NEAREST rather than LANCZOS on purpose. A smooth downscale
    invents intermediate tones that are in no other frame, and these are the
    frames the file can least afford; nearest reuses colours the palette already
    has.
    """
    k = max(0.02, k)
    w = max(1, int(round(S * k)))
    c = Image.new("RGB", (S, S), BG)
    c.paste(im.resize((w, w), Image.NEAREST if k < 0.98 else Image.LANCZOS),
            ((S - w) // 2, (S - w) // 2))
    return c


"""Why the flight is a scale move on cream and not a cross-dissolve.

The first version cross-faded the street map into the globe while scaling both. It
looked good and it was 77 % of the file: blending a detailed map with a globe
invents colours that exist in neither, so every one of those frames compressed
badly and none of them resembled its neighbour. Pulling the map back onto the
cream page instead leaves a growing border of one flat colour, which costs almost
nothing, and the globe — flat land on flat ocean — is the cheapest picture in the
whole reel. The globe then grows from roughly the size the map shrank to, so the
eye reads one continuous move out and back in rather than a cut.
"""

def note_at(leg, note):
    """Where along the leg a note sits: a fraction, or "top" = its highest fix.

    "top" is resolved from the altitude the GPS actually recorded, so the note
    about the Stelvio lands on the Stelvio and not on a guess.
    """
    at = note.get("at")
    if at == "top":
        alt = leg["leg"]["alt"]
        if not alt:
            return 0.5
        ti = max(range(len(alt)), key=lambda i: alt[i])
        return leg["cum"][min(ti, len(leg["cum"]) - 1)] / (leg["cum"][-1] or 1.0)
    return max(0.02, min(1.0, float(at)))


def leg_column(story, li, S):
    """Where this leg's text column goes, decided once, from the whole route.

    Projects the leg's points into the frame the drawing will use, then asks
    free_column() which half the route leaves emptier. Deciding it per leg rather
    than per frame matters twice: the panel does not jump while the dot moves, and
    the answer is about the whole track rather than the bit drawn so far.
    """
    act = story["legs"][li]
    img, to_px = act["mos"]
    la0, la1, lo0, lo1 = act["box"]
    x0, y0 = to_px(la1, lo0)
    x1, y1 = to_px(la0, lo1)
    side = min(x1 - x0, y1 - y0)
    bx, by = (x0 + x1) / 2 - side / 2, (y0 + y1) / 2 - side / 2
    K = side / float(S)
    pts = []
    for l in (story["legs"] if story["st"].get("mode") == "race" else [act]):
        for q in l["pts"][::3]:
            qx, qy = to_px(*q)
            pts.append(((qx - bx) / K, (qy - by) / K))
    return free_column(pts, S)


# ------------------------------------------------------------------ montaggio

def build(stories, S, fonts, args):
    """The cut.

    The first version ran the twenty days in 42 seconds and it was unreadable: a
    caption had a second and a half on screen and every camera move was two
    frames. Five times slower is what was asked for, and five times the frames is
    twenty-four megabytes, so the length comes from the two things that are free
    or nearly free instead — **holding** a frame costs nothing at all, and a
    full-screen page of type costs one cheap frame however long it sits there.
    So each day now opens on a narration card that fades in, holds, and fades out,
    and the flights got the frames they needed to actually feel like a zoom.

    What still costs real bytes is any frame where the whole picture changes, so
    the drawing itself keeps a locked camera. See tools/README.md.
    """
    frames, durs = [], []
    total = len(stories)
    dots = [(s["clat"], s["clon"], AC.get(s["st"]["accent"], AC["stone"])) for s in stories]

    def add(im, ms=None):
        """`args.ms` e' il passo del disegno GPS e non si tocca: e' la cosa che si
        guarda. Tutto il resto — globo, dissolvenze, zoom, cartoline — va a
        `args.ms_move`, piu' veloce, perche' e' collegamento e non racconto."""
        frames.append(im.convert("RGB"))
        durs.append(ms or args.ms_move)

    def fade_card(lines, ac=None, n=None, hold=None, out=True):
        """Type fading up on the page, holding long enough to be read, fading away."""
        for k in range(args.fade):
            add(text_card(S, fonts, (k + 1) / float(args.fade), lines, ac, n, total))
        durs[-1] = hold or args.card
        if out:
            for k in range(args.fade - 1):
                add(text_card(S, fonts, 1.0 - (k + 1) / float(args.fade), lines, ac, n, total))

    # --- apertura: prima il testo, poi il mondo
    if args.intro or not args.only:
        fade_card([("micmer · archivio 2015 – 2026", "kicker"),
                   ("Venti giorni", "big"),
                   ("su 2.923", "big"),
                   ("Undici anni di GPS. Ogni traccia è quella vera.", "body")],
                  hold=args.card + 700)
        fade_card([("98.830 chilometri. 1.843.198 metri di dislivello.", "body"),
                   ("4.928 ore in movimento.", "body"),
                   ("Venti giorni raccontati, uno alla volta.", "body")])
        for k in range(7):
            t = k / 6.0
            add(globe_frame(S, 46, 9, dots, fonts, upto=int(t * (total - 1)),
                            radius=lerp(0.30, 0.86, ease(t))),
                args.ms if k < 6 else 900)

    prev_map = None
    for si, story in enumerate(stories):
        st = story["st"]
        ac = AC.get(st["accent"], AC["stone"])
        target = map_frame(story, 0, 0.0, 1.0, S, fonts, cap_alpha=0.0, total=total)
        plat, plon = (stories[si - 1]["clat"], stories[si - 1]["clon"]) if si else (46, 9)
        hop = math.hypot((story["clat"] - plat) * 111, (story["clon"] - plon) * 78)
        far = hop > 400

        # --- uscita: la mappa si allontana E si scioglie nella carta, un movimento
        # solo. Erano due (cinque frame di zoom out piu cinque di dissolvenza) e
        # costavano 220 kB per storia: un frame che contiene la basemap a una scala
        # nuova e' l'unica cosa cara di tutto il reel — il globo e le cartoline
        # stanno a 5 kB, questi a 45.
        if prev_map is not None:
            for k in range(args.zout):
                t = (k + 1) / float(args.zout)
                add(to_paper(on_paper(prev_map, lerp(1.0, 0.40, ease(t)), S),
                             ease(t), S))

        # --- la scheda: la narrazione, non il titolo dell'attivita'.
        # Prima erano kicker + titolo + riga, cioe' tre campi di un database messi
        # in colonna: si leggeva come un elenco, non come un racconto. Ora il testo
        # arriva da `card` nel config, scritto a mano storia per storia.
        for k in range(args.cardin):
            add(story_card(S, fonts, st, si + 1, total, (k + 1) / float(args.cardin), ac),
                args.card if k == args.cardin - 1 else None)
        for k in range(args.fade - 1):
            u = 1.0 - (k + 1) / float(args.fade)
            add(Image.blend(Image.new("RGB", (S, S), BG),
                            story_card(S, fonts, st, si + 1, total, 1.0, ac), u))

        # --- il volo. Il tratto graduale lo fa il GLOBO, che cresce da un puntino
        # e ruota fino al posto nuovo: sono i frame piu economici del reel, quindi
        # qui il tempo si puo' spendere. La mappa entra negli ultimi quattro frame,
        # ed e' la parte che si paga.
        SMALL = 0.38
        n_rot = args.rot if far else max(6, args.rot // 2)
        for k in range(n_rot):
            t = k / max(1.0, n_rot - 1.0)
            add(globe_frame(S, lerp(plat, story["clat"], ease(t)),
                            lerp(plon, story["clon"], ease(t)), dots, fonts,
                            upto=si if t > .45 else max(0, si - 1),
                            radius=lerp(0.26, 0.90, ease(min(1, t * 1.25)))))
        for k in range(args.zin):
            t = (k + 1) / float(args.zin)
            add(on_paper(target, lerp(SMALL, 1.0, ease(t)), S))

        # --- i tratti, a camera ferma
        race = st.get("mode") == "race"
        for li, l in enumerate(story["legs"]):
            if race and li > 0:
                break                      # in gara si disegna tutto in un passaggio
            # la gara si guarda piu' a lungo: e' l'unico momento in cui c'e'
            # qualcosa da confrontare mentre le tracce corrono
            n = (int(args.draw * 1.6) if race else
                 args.draw if len(story["legs"]) == 1 else
                 max(12, int(args.draw * 0.72)))
            notes = sorted(l["leg"].get("notes") or [],
                           key=lambda x: note_at(l, x))
            done_notes = set()
            # La colonna del testo si decide una volta per tratto, sulla traccia
            # intera: cosi' non salta da un lato all'altro mentre il puntino va, e
            # soprattutto non finisce mai sopra la traccia.
            rect = leg_column(story, li, S)
            shown_note = [None]
            for k in range(n):
                p = (k + 1) / float(n)
                ca = min(1.0, (k + 1) / 4.0)
                last = (k == n - 1)
                # il testo si scrive col passo del puntino: finiscono insieme
                add(map_frame(story, li, p, 1.0, S, fonts, cap_alpha=ca, total=total,
                              follow=0.0, caption="",
                              note=shown_note[0],
                              side={"rect": rect, "line": l["leg"].get("line"),
                                    "reveal": min(1.0, p / 0.7)}),
                    (args.hold if li == len(story["legs"]) - 1 else args.hold_leg)
                    if last else args.ms)
                # --- le note.
                #
                # Senza zoom la nota compare a lato con la camera ferma: cambia
                # solo il rettangolo del testo, quindi costa quanto un frame di
                # disegno e se ne possono avere molte. Con `zoom` la camera scende
                # sul puntino, e quello si paga come ogni cambio di scala — sono
                # otto in tutto il reel, sui momenti che se lo meritano.
                #
                # In entrambi i casi il disegno si FERMA sulla nota: cinque secondi
                # su un frame gia' disegnato non costano niente, e sono il tempo
                # che serve a leggerla.
                for ni, nt in enumerate(notes):
                    at = note_at(l, nt)
                    if ni in done_notes or p < at:
                        continue
                    done_notes.add(ni)
                    if not nt.get("zoom"):
                        for z in range(args.nfade):
                            u = (z + 1) / float(args.nfade)
                            add(map_frame(story, li, max(p, at), 1.0, S, fonts,
                                          total=total, follow=0.0, caption="",
                                          note=nt["text"], note_alpha=u,
                                          side={"rect": rect,
                                                "line": l["leg"].get("line"),
                                                "reveal": 1.0}),
                                args.note_hold if z == args.nfade - 1 else None)
                        shown_note[0] = nt["text"]   # la nota resta a terra
                        continue
                    for z in range(args.znote):
                        u = (z + 1) / float(args.znote)
                        add(map_frame(story, li, at, lerp(1.0, args.zoom, ease(u)), S,
                                      fonts, total=total, follow=ease(u), caption="",
                                      note=nt["text"], note_alpha=min(1.0, u * 1.6),
                                      side={"rect": rect, "line": None}),
                            args.note_hold if z == args.znote - 1 else None)
                    for z in range(args.znote):
                        u = (z + 1) / float(args.znote)
                        add(map_frame(story, li, at, lerp(args.zoom, 1.0, ease(u)), S,
                                      fonts, total=total, follow=1.0 - ease(u),
                                      caption="", note=nt["text"],
                                      note_alpha=1.0 - ease(u),
                                      side={"rect": rect, "line": None}))
                    shown_note[0] = nt["text"]
            prev_map = frames[-1]

    # --- finale
    if args.intro or not args.only:
        for k in range(args.zout):
            t = (k + 1) / float(args.zout)
            add(to_paper(on_paper(prev_map, lerp(1.0, 0.40, ease(t)), S),
                         ease(t), S))
        # Il globo gira verso l'Atlantico: centrato sull'Europa, Boston sta dietro
        # l'orizzonte e il giorno piu lontano dei venti non si vedrebbe. Nessun punto
        # "corrente": qui contano tutti uguali, e l'alone grosso sull'ultimo sembrava
        # una macchia grigia sull'Italia.
        for k in range(9):
            t = k / 8.0
            add(globe_frame(S, 42, lerp(8, -34, ease(t)), dots, fonts, upto=total - 1,
                            current=False, radius=lerp(0.86, 0.82, ease(t))),
                args.ms if k < 8 else 1000)
        fade_card([("2.923 attività. Venti raccontate.", "body"),
                   ("98.830 km", "big"),
                   ("micmer-git.github.io/top-20", "small")],
                  hold=args.card + 1400, out=False)
    return frames, durs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=380)
    ap.add_argument("--ms", type=int, default=105,
                    help="passo del disegno GPS: e' la cosa che si guarda, non si tocca")
    ap.add_argument("--ms-move", type=int, default=80,
                    help="passo dei collegamenti: globo, zoom, dissolvenze, cartoline")
    ap.add_argument("--card", type=int, default=5000, help="quanto resta ferma una scheda")
    ap.add_argument("--fade", type=int, default=6, help="frame di dissolvenza")
    ap.add_argument("--cardin", type=int, default=12,
                    help="frame di entrata animata della scheda del giorno")
    ap.add_argument("--rot", type=int, default=5, help="frame di rotazione del globo")
    ap.add_argument("--zin", type=int, default=2, help="frame dello zoom in ingresso")
    ap.add_argument("--zout", type=int, default=2, help="frame dello zoom in uscita")
    ap.add_argument("--hold-leg", type=int, default=450, help="pausa a fine tratto")
    ap.add_argument("--hold", type=int, default=1600, help="pausa sull'ultimo frame di una storia")
    ap.add_argument("--draw", type=int, default=24, help="frame per tratto")
    ap.add_argument("--zoom", type=float, default=2.4, help="zoom sulle note")
    ap.add_argument("--znote", type=int, default=4, help="frame di zoom su una nota")
    ap.add_argument("--nfade", type=int, default=4, help="frame di dissolvenza di una nota a lato")
    ap.add_argument("--note-hold", type=int, default=5000, help="quanto resta una nota")
    ap.add_argument("--punch", type=int, default=0,
                    help="frame dell'affondo finale su ogni storia. Zero per scelta: "
                         "a cinque frame per storia costava piu di sei megabyte, e le "
                         "storie a piu tratti cambiano scala da sole perche ogni tratto "
                         "ha la sua inquadratura")
    ap.add_argument("--transparent", type=int, default=1,
                    help="1 = scrive solo i pixel cambiati (vedi punch_holes)")
    ap.add_argument("--disposal", type=int, default=1,
                    help="1 = lascia in posa, lascia scrivere al GIF solo il rettangolo "
                         "cambiato; 2 = ridisegna tutto (molto piu grande)")
    ap.add_argument("--colors", type=int, default=40,
                    help="400 px e 44 colori sono il punto in cui il reel lento sta "
                         "sotto i cinque megabyte senza differenza visibile: 14 "
                         "slot sono riservati (accenti, accenti sbiaditi, "
                         "inchiostri, carta), gli altri vanno alla mappa")
    ap.add_argument("--px", type=int, default=1500, help="lato del mosaico basemap")
    ap.add_argument("--style", default="light_nolabels")
    ap.add_argument("--only", help="solo queste storie, numerate da 1: 1,17,18")
    ap.add_argument("--intro", action="store_true",
                    help="tieni apertura e finale anche con --only (per il taglio corto)")
    ap.add_argument("--probe", type=int, help="provino a sei riquadri di una storia")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    S = args.size
    allst = load_stories()
    fonts = (font("arialbd.ttf", int(S * 0.023)),      # kicker
             font("georgia.ttf", int(S * 0.050)),      # titolo
             font("arial.ttf", int(S * 0.0335)),       # didascalia
             font("arialbd.ttf", int(S * 0.0225)),     # statistiche
             font("arial.ttf", int(S * 0.0165)),       # credito
             font("seguiemj.ttf", int(S * 0.034)),     # emoji nel testo
             font("seguiemj.ttf", int(S * 0.022)),     # emoji piccoli
             font("georgia.ttf", int(S * 0.078)),      # titolo del globo
             font("arial.ttf", int(S * 0.031)),       # sottotitolo del globo
             font("arialbd.ttf", int(S * 0.0245)),    # nomi dei luoghi sulla mappa
             font("georgiai.ttf", int(S * 0.0345)),   # corsivo, per le citazioni
             font("georgia.ttf", int(S * 0.062)))      # i numeri delle statistiche

    pick = allst
    if args.probe:
        pick = [allst[args.probe - 1]]
    elif args.only:
        idx = [int(x) for x in args.only.split(",")]
        pick = [allst[i - 1] for i in idx]

    print("mosaici basemap (%d px, %s):" % (args.px, args.style))
    stories = prepare(pick, args.px, args.style)

    if args.probe:
        st = stories[0]
        grid = Image.new("RGB", (S * 3, S * 2), BG)
        shots = [(0, 0.10, 1.0), (0, 0.45, args.zoom), (0, 0.99, 1.0)]
        li = len(st["legs"]) - 1
        shots += [(li, 0.35, args.zoom), (li, 0.99, 1.0)]
        for k, (l, p, z) in enumerate(shots):
            grid.paste(map_frame(st, l, p, z, S, fonts, total=20), ((k % 3) * S, (k // 3) * S))
        grid.paste(globe_frame(S, st["clat"], st["clon"],
                               [(st["clat"], st["clon"], AC.get(st["st"]["accent"], AC["stone"]))],
                               fonts, upto=0), (2 * S, S))
        p = os.path.join(HERE, ".reel_probe.png")
        grid.save(p)
        print("scritto", p)
        return

    frames, durs = build(stories, S, fonts, args)
    print("\n%d frame, %.1f s" % (len(frames), sum(durs) / 1000.0))

    # tavolozza su un campione sparso per tutto il reel: presa da un frame solo,
    # i quattro accenti collassano sullo stesso grigio (già visto in build_top20_gif)
    step = max(1, len(frames) // 40)
    sample = Image.new("RGB", (S, S * len(frames[::step])), BG)
    for i, f in enumerate(frames[::step]):
        sample.paste(f, (0, i * S))
    pal = fixed_palette(sample, args.colors)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    if args.transparent:
        q = punch_holes(q, args.colors)
        q[0].save(args.out, save_all=True, append_images=q[1:], loop=0,
                  duration=durs, optimize=False, disposal=1,
                  transparency=args.colors)
    else:
        q[0].save(args.out, save_all=True, append_images=q[1:], loop=0,
                  duration=durs, optimize=True, disposal=args.disposal)
    print("scritto %s — %.1f MB (%.0f kB/frame)"
          % (args.out, os.path.getsize(args.out) / 1e6,
             os.path.getsize(args.out) / 1024.0 / len(frames)))


def fixed_palette(sample, colors):
    """Quantize the basemap, then force the ink and accent colours back in.

    Left to itself, median-cut spends the palette on what covers the most pixels —
    which is the basemap's pastel gradients — and a two-pixel-wide track gets
    merged into whatever grey is nearest. That is not a subtle degradation: the
    Malaga marathon came out drawn in grey instead of green, and so did its dot on
    the globe. The four accents, the three inks and the paper are therefore
    reserved before median-cut is allowed to spend the rest.
    """
    # Anche gli accenti SBIADITI vanno riservati: i tratti dei giorni precedenti si
    # disegnano a blend(ac, .60) e senza slot loro finivano nel grigio piu' vicino —
    # a Bologna il giro del sabato diventava grigio invece che arancio pallido.
    keep = ([BG, INK, INK2, INK3, RULE, (255, 255, 255)]
            + [AC[k] for k in sorted(AC)]
            + [blend(AC[k], .60) for k in sorted(AC)]
            + RACE_TINTS
            + RAMP)          # i sei gradini della quota-colore (giorni di dislivello)
    base = sample.quantize(colors=max(8, colors - len(keep)), method=Image.MEDIANCUT)
    raw = base.getpalette()[: max(8, colors - len(keep)) * 3]
    for c in keep:
        raw += list(c)
    raw += [0, 0, 0] * (256 - len(raw) // 3)
    pal = Image.new("P", (1, 1))
    pal.putpalette(raw[:768])
    return pal


def punch_holes(q, idx):
    """Replace every pixel identical to the previous frame with a transparent one.

    This is what makes the reel shareable. Pillow's own `optimize` crops each frame
    to the rectangle that changed, but inside that rectangle it still re-encodes
    pixels that did not move — and since a track grows right across the frame, that
    rectangle is nearly the whole picture. With the camera held still during a draw
    the basemap under it is bit-identical frame to frame, so marking those pixels
    transparent and leaving the previous frame in place (disposal=1) means only the
    line, the dot and the caption get written.

    Costs one palette slot for the transparent index, which is why the palette is
    quantized to `colors` and index `colors` is left free.
    """
    from PIL import ImageChops
    pal = q[0].getpalette()
    size = q[0].size
    # gli indici di tavolozza si confrontano come byte, non come colori: due indici
    # diversi possono avere la stessa luminanza, e trattarli da uguali lascia
    # sporco in sovrimpressione. Tutto in L mode così il confronto lo fa Pillow.
    asL = lambda im: Image.frombytes("L", size, im.tobytes())
    hole = Image.new("L", size, idx)
    out = [q[0].copy()]
    prev = asL(q[0])
    for f in q[1:]:
        cur = asL(f)
        changed = ImageChops.difference(cur, prev).point(lambda v: 255 if v else 0)
        merged = Image.composite(cur, hole, changed)
        g = Image.frombytes("P", size, merged.tobytes())
        g.putpalette(pal)
        out.append(g)
        prev = cur
    return out


if __name__ == "__main__":
    main()
