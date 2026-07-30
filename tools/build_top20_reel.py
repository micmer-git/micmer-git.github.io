#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_top20_reel.py — the one GIF: twenty days, one continuous flight.

This is the LinkedIn deliverable. Unlike build_top20_gif.py (a flat contact-sheet
of twenty separate cards) this is a single sequential reel: every path draws on a
real map, and between one day and the next the camera pulls back to an
orthographic globe, rotates, and dives into the next place. The globe keeps the
dots of everywhere already visited, so it doubles as the progress bar.

    python build_top20_reel.py                    # tutto il reel
    python build_top20_reel.py --only 1,17,18     # solo alcune storie (numerate da 1)
    python build_top20_reel.py --probe 17         # un provino PNG a sei riquadri
    python build_top20_reel.py --size 560 --ms 90   # piu grande, oltre 5 MB

Reads `top-20/_data.js` — the same data as the page and the contact sheet, so the
three cannot disagree. Basemap tiles and the globe come from tools/basemap.py, and
carry its attribution; do not remove the credit line from the corner.

Two things worth knowing before changing it:

* **One caption per leg, not five.** The page gives every day five beats. Twenty
  days times five beats is a hundred sentences, and a sentence needs two seconds
  to read: that reel would run three and a half minutes. The reel shows each
  leg's `line` instead, which is why the multi-day stories (the clavicle's four
  legs, Bologna's two) carry the most text — the text follows the camera moves.
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


def plain(t):
    """Il testo senza emoji, per le righe piccole della barra dei dati."""
    return "".join(c for c in t if not is_emoji(c)).replace("  ", " ").strip(" —·-")


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
              total=20, follow=None):
    """One map frame: the leg `li` of `story` drawn to fraction `p`, at zoom `zoomf`."""
    legs = story["legs"]
    act = legs[li]
    img, to_px = act["mos"]
    la0, la1, lo0, lo1 = act["box"]
    ac = AC.get(story["st"]["accent"], AC["stone"])

    # riquadro pieno in pixel di mosaico, poi stretto di zoomf attorno al puntino
    x0, y0 = to_px(la1, lo0)
    x1, y1 = to_px(la0, lo1)
    full_w, full_h = x1 - x0, y1 - y0
    side = min(full_w, full_h)
    i, h = head_at(act["pts"], act["cum"], p)
    hx, hy = to_px(*h)
    cw = side / zoomf
    fo = follow if follow is not None else (zoomf - 1) / max(zoomf, 1e-6)
    cx = lerp((x0 + x1) / 2, hx, fo)
    cy = lerp((y0 + y1) / 2, hy, fo)
    cx = min(max(cx, x0 + cw / 2), x1 - cw / 2) if full_w > cw else (x0 + x1) / 2
    cy = min(max(cy, y0 + cw / 2), y1 - cw / 2) if full_h > cw else (y0 + y1) / 2
    box = (int(cx - cw / 2), int(cy - cw / 2), int(cx + cw / 2), int(cy + cw / 2))

    crop = img.crop(box).convert("RGBA")
    K = crop.size[0] / float(S)                     # da pixel finali a pixel di crop
    lay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    off = lambda q: (to_px(*q)[0] - box[0], to_px(*q)[1] - box[1])

    def stroke(pts, colour, w, a):
        if len(pts) > 1:
            dr.line(pts, fill=colour + (a,), width=max(1, int(round(w * K))), joint="curve")

    for j, l in enumerate(legs):                    # i tratti già fatti restano a terra
        if j == li:
            continue
        stroke([off(q) for q in l["pts"]], ac if j < li else INK3, 2.0,
               150 if j < li else 45)
    stroke([off(q) for q in act["pts"]], INK3, 1.6, 60)          # il tratto intero
    done = [off(q) for q in act["pts"][:i + 1]] + [off(h)]
    stroke(done, ac, 6.5, 55)                                    # alone
    stroke(done, ac, 2.8, 255)                                   # traccia

    sx, sy = off(act["pts"][0])
    r = 3.4 * K
    dr.ellipse([sx - r, sy - r, sx + r, sy + r], fill=BG + (255,), outline=ac + (255,),
               width=max(1, int(round(1.6 * K))))
    dx, dy = off(h)
    for rad, a in ((11 * K, 60), (6.0 * K, 130)):
        dr.ellipse([dx - rad, dy - rad, dx + rad, dy + rad], fill=ac + (a,))
    r = 4.3 * K
    dr.ellipse([dx - r, dy - r, dx + r, dy + r], fill=ac + (255,),
               outline=(255, 255, 255, 255), width=max(1, int(round(1.7 * K))))

    frame = Image.alpha_composite(crop, lay).resize((S, S), Image.LANCZOS)
    place_labels(frame, act, box, to_px, S, fonts, ac)
    if chrome:
        chrome_over(frame, story, li, S, fonts, cap_alpha, total)
    return frame.convert("RGB")


def place_labels(frame, act, box, to_px, S, fonts, ac):
    """The only place names on the map, drawn after the downscale so they stay crisp.

    The basemap is the no-labels build: CARTO's own labels were the most expensive
    detail in the GIF and half of them were illegible at this size anyway, so the
    map is named by hand instead — start, finish, and the highest point, which is
    the pass the day was about. `places` in the config carries the names; the
    coordinates come from the track itself.
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


def chrome_over(frame, story, li, S, fonts, cap_alpha, total):
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

    # didascalia + statistiche in basso
    line = story["legs"][li]["leg"].get("line") or ""
    cl = wrap(dr, line, f_cap, f_emo, S - 2 * pad)[:2]
    lg = story["legs"][li]["leg"]
    if len(story["legs"]) > 1:
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
    band_h = int(S * 0.048) + len(cl) * int(S * 0.046) + int(S * 0.030)
    top = S - pad - band_h
    scrim(frame, (pad - int(S * .022), top - int(S * .020), S - pad + int(S * .022),
                  S - pad + int(S * .016)), int(S * 0.020))
    dr = ImageDraw.Draw(frame)
    draw_text(dr, (pad, top - int(S * .006)), stat, f_stat, f_emos, blend(ac, .18))
    a = max(0.0, min(1.0, cap_alpha))
    col = tuple(int(round(BG[j] + (INK[j] - BG[j]) * a)) for j in range(3))
    for k, l in enumerate(cl):
        draw_text(dr, (pad, top + int(S * 0.036) + k * int(S * 0.046)), l, f_cap, f_emo, col)

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


def on_paper(im, k, S):
    """The frame, scaled by k, centred on the page.

    Resampled with NEAREST rather than LANCZOS on purpose. A smooth downscale
    invents intermediate tones that are in no other frame, and these are the
    frames the file can least afford; nearest reuses colours the palette already
    has. At two frames per flight, moving fast, the aliasing is not visible.
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

# ------------------------------------------------------------------ montaggio

def build(stories, S, fonts, args):
    frames, durs = [], []
    total = len(stories)
    dots = [(s["clat"], s["clon"], AC.get(s["st"]["accent"], AC["stone"])) for s in stories]

    def add(im, ms=None):
        frames.append(im.convert("RGB"))
        durs.append(ms or args.ms)

    # --- apertura
    if not args.only:
        km = sum(s["st"]["km"] for s in stories)
        for k in range(10):
            t = k / 9.0
            g = globe_frame(S, 46, 9, dots, fonts, upto=int(t * (total - 1)),
                            radius=lerp(0.62, 0.86, ease(t)),
                            title="Venti giorni\nsu 2.923",
                            sub="Undici anni di GPS, dal 2015 a oggi.\nOgni traccia è quella vera.")
            add(g, args.ms if k < 9 else 1100)

    prev_map = None
    for si, story in enumerate(stories):
        st = story["st"]
        first = story["legs"][0]

        # --- volo: indietro sulla pagina, globo che ruota, dentro alla mappa nuova
        target = map_frame(story, 0, 0.0, 1.0, S, fonts, cap_alpha=0.0, total=total)
        plat, plon = (stories[si - 1]["clat"], stories[si - 1]["clon"]) if si else (46, 9)
        hop = math.hypot((story["clat"] - plat) * 111, (story["clon"] - plon) * 78)
        far = hop > 400
        n_out, n_rot, n_in = (2, 5, 2) if far else (2, 2, 2)
        SMALL = 0.46

        if prev_map is not None:
            for k in range(n_out):
                t = (k + 1) / float(n_out)
                add(on_paper(prev_map, lerp(1.0, SMALL, ease(t)), S))
        for k in range(n_rot):
            t = k / max(1.0, n_rot - 1.0)
            add(globe_frame(S, lerp(plat, story["clat"], ease(t)),
                            lerp(plon, story["clon"], ease(t)), dots, fonts,
                            upto=si if t > .45 else max(0, si - 1),
                            radius=lerp(SMALL, 0.86, ease(min(1, t * 1.6)))))
        for k in range(n_in):
            t = (k + 1) / float(n_in)
            add(on_paper(target, lerp(SMALL, 1.0, ease(t)), S))

        # --- i tratti
        #
        # La camera sta FERMA mentre la traccia si disegna, e lo zoom arriva alla
        # fine del tratto, sull'arrivo. La prima versione zoomava dentro e fuori
        # durante tutto il disegno: si vedeva bene ma in GIF costava 50 kB per
        # frame — nessun frame somigliava al precedente, quindi ogni frame era
        # intero. A camera ferma cambiano solo la traccia, il puntino e la
        # didascalia, e il formato può scrivere solo quel rettangolo. Il grande
        # zoom out/in ce l'hanno già le transizioni sul globo.
        for li, l in enumerate(story["legs"]):
            n = args.draw if len(story["legs"]) == 1 else max(8, int(args.draw * 0.74))
            for k in range(n):
                p = (k + 1) / float(n)
                ca = min(1.0, (k + 1) / 3.0)
                add(map_frame(story, li, p, 1.0, S, fonts, cap_alpha=ca, total=total,
                              follow=0.0))
            last_leg = (li == len(story["legs"]) - 1)
            if last_leg and args.zoom > 1.01:
                for k in range(args.punch):
                    t = (k + 1) / float(args.punch)
                    add(map_frame(story, li, 1.0, lerp(1.0, args.zoom, ease(t)), S,
                                  fonts, total=total, follow=ease(t)),
                        args.hold if k == args.punch - 1 else None)
            prev_map = frames[-1]

    # --- finale
    if not args.only:
        # Il finale gira verso l'Atlantico: centrato sull'Europa, Boston sta dietro
        # l'orizzonte e il giorno piu lontano dei venti non si vedrebbe. Nessun punto
        # "corrente": qui contano tutti uguali, e l'alone grosso sull'ultimo sembrava
        # una macchia grigia sull'Italia.
        for k in range(10):
            t = k / 9.0
            add(globe_frame(S, 42, lerp(8, -34, ease(t)), dots, fonts, upto=total - 1,
                            current=False, radius=lerp(0.86, 0.82, ease(t)),
                            title="98.830 km",
                            sub="1.843.198 metri di dislivello.\n4.928 ore in movimento.\n2.923 attività. Venti raccontate."),
                args.ms if k < 7 else 1600)
    return frames, durs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=520)
    ap.add_argument("--ms", type=int, default=75)
    ap.add_argument("--hold", type=int, default=550, help="pausa sull'ultimo frame di una storia")
    ap.add_argument("--draw", type=int, default=13, help="frame per tratto")
    ap.add_argument("--zoom", type=float, default=2.1, help="zoom dell'affondo finale")
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
    ap.add_argument("--colors", type=int, default=72,
                    help="72 e 520 px sono il punto in cui il file scende sotto i "
                         "cinque megabyte senza differenza visibile da 96 e 560")
    ap.add_argument("--px", type=int, default=1500, help="lato del mosaico basemap")
    ap.add_argument("--style", default="light_nolabels")
    ap.add_argument("--only", help="solo queste storie, numerate da 1: 1,17,18")
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
             font("arialbd.ttf", int(S * 0.0245)))     # nomi dei luoghi sulla mappa

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
    keep = [BG, INK, INK2, INK3, RULE, (255, 255, 255)] + [AC[k] for k in sorted(AC)]
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
