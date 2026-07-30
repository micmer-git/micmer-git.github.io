#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build top-20/top-20.gif — the shareable square version of the twenty stories.

Reads the same `top-20/_data.js` the page reads, so the GIF can never disagree
with what the page shows. Each story gets FRAMES frames: the route draws itself
under the dot while its story advances one line at a time underneath.

Two things were learned the hard way and are worth keeping:

* **The frame follows the leg, not the story.** Framing all of a story's legs in
  one box works for Bergamo-Bologna, where the ride and the marathon overlap,
  and fails completely for the clavicle, whose four legs sit in two different
  valleys eighty kilometres apart — everything ended up a thumbnail in a corner.
  Each leg now gets the whole canvas while it is the active one, so the shape of
  every single day stays readable.
* **Arial has no emoji.** The captions quote activity titles like 🩻 and ❤️‍🩹,
  where the emoji *is* the title, so dropping them would gut the sentence. Text
  is drawn in runs, handing the emoji runs to Segoe UI Emoji with
  `embedded_color=True` (which Pillow does render for this font).

    python build_top20_gif.py
    python build_top20_gif.py --frames 20 --size 560     # più lento, più grande
    python build_top20_gif.py --story mdd-2021 --png     # provino a sei riquadri

Needs Pillow. Writes nothing but the GIF (or tools/.gif_check.png with --png).
"""
import argparse
import io
import json
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "top-20", "_data.js")
OUT = os.path.join(HERE, "..", "top-20", "top-20.gif")

BG = (250, 248, 243)
INK = (20, 21, 15)
INK2 = (92, 95, 82)
INK3 = (143, 147, 130)
RULE = (228, 225, 214)
AC = {"dawn": (194, 118, 26), "dusk": (59, 91, 181),
      "green": (77, 114, 56), "stone": (138, 90, 60)}
F_DIR = r"C:\Windows\Fonts"


def blend(c, t):
    """c mixed t of the way towards the paper."""
    return tuple(int(c[i] + (BG[i] - c[i]) * t) for i in range(3))


def font(name, size):
    for cand in (name, "arial.ttf"):
        p = os.path.join(F_DIR, cand)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


# ------------------------------------------------------------ testo con emoji

def is_emoji(ch):
    o = ord(ch)
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or
            0x2B00 <= o <= 0x2BFF or o in (0xFE0F, 0x200D, 0x20E3) or
            0x1F1E6 <= o <= 0x1F1FF or 0x2190 <= o <= 0x21FF)


def runs(text):
    """Split into (chunk, is_emoji) runs so each can go to its own font."""
    out = []
    for ch in text:
        e = is_emoji(ch)
        if out and out[-1][1] == e:
            out[-1][0] += ch
        else:
            out.append([ch, e])
    return [(c, e) for c, e in out]


def text_w(dr, text, fnt, efnt):
    return sum(dr.textlength(c, font=(efnt if e else fnt)) for c, e in runs(text))


def draw_text(dr, xy, text, fnt, efnt, fill):
    x, y = xy
    for c, e in runs(text):
        f = efnt if e else fnt
        if e:
            # gli emoji di Segoe siedono più alti dei glifi di testo
            dr.text((x, y - 1), c, font=f, fill=fill, embedded_color=True)
        else:
            dr.text((x, y), c, font=f, fill=fill)
        x += dr.textlength(c, font=f)
    return x


def wrap(dr, text, fnt, efnt, width):
    out, line = [], ""
    for word in text.split():
        t = (line + " " + word).strip()
        if text_w(dr, t, fnt, efnt) <= width or not line:
            line = t
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    return out


# ------------------------------------------------------------------ geometria

def load_stories():
    """Parse the STORIES array straight out of _data.js — one source of truth."""
    src = io.open(DATA, encoding="utf-8").read()
    m = re.search(r"const\s+STORIES\s*=\s*(\[.*\]);", src, re.S)
    if not m:
        sys.exit("non trovo STORIES in %s" % DATA)
    return json.loads(m.group(1))


def decode(leg):
    pts, x, y, d = [], 0, 0, leg["d"]
    for i in range(0, len(d), 2):
        x += d[i]
        y += d[i + 1]
        pts.append((leg["lat0"] + x * 1e-5, leg["lng0"] + y * 1e-5))
    return pts


def project(pts):
    latm = sum(p[0] for p in pts) / len(pts)
    k = math.cos(math.radians(latm))
    return [(p[1] * k, -p[0]) for p in pts]


def arclen(xy):
    cum = [0.0]
    for i in range(1, len(xy)):
        cum.append(cum[-1] + math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]))
    return cum


def head_at(xy, cum, p):
    """Point at fraction p of the polyline's length, plus the index behind it."""
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
    return lo, (xy[lo][0] + (xy[hi][0] - xy[lo][0]) * f,
                xy[lo][1] + (xy[hi][1] - xy[lo][1]) * f)


def prepare(st):
    legs = []
    for lg in st["legs"]:
        xy = project(decode(lg))
        xs = [q[0] for q in xy]
        ys = [q[1] for q in xy]
        legs.append({"xy": xy, "cum": arclen(xy), "leg": lg,
                     "w": max(max(xs) - min(xs), 1e-9), "h": max(max(ys) - min(ys), 1e-9),
                     "cx": (min(xs) + max(xs)) / 2, "cy": (min(ys) + max(ys)) / 2})
    # t0/dt li ha già decisi build_top20.py e sono dentro _data.js: la pagina
    # legge gli stessi numeri, così la GIF non può raccontare un'altra cronologia
    for l in legs:
        l["t0"] = l["leg"]["t0"]
        l["dt"] = l["leg"]["dt"]
    return legs


def render(st, p, S, fonts, n, legs=None):
    """One frame: story `st` at fraction `p` of its whole timeline."""
    f_kick, f_title, f_beat, f_stat, f_leg, f_emo, f_emos = fonts
    im = Image.new("RGB", (S, S), BG)
    dr = ImageDraw.Draw(im)
    ac = AC.get(st["accent"], AC["stone"])
    legs = legs or prepare(st)

    pad = int(S * 0.055)
    map_w = S - 2 * pad

    # L'altezza della testata si misura, non si assume: "Bergamo - Bologna, e la
    # maratona il giorno dopo" prende due righe e la seconda finiva sopra il nome
    # del tratto.
    title_lines = wrap(dr, st["title"], f_title, f_emo, map_w)[:2]
    head_bottom = int(S * 0.078) + len(title_lines) * int(S * 0.060)
    leg_y = head_bottom + int(S * 0.004)
    map_top = leg_y + (int(S * 0.040) if len(legs) > 1 else int(S * 0.010))
    foot_y = int(S * 0.770)
    map_h = foot_y - map_top - int(S * 0.020)

    li = len(legs) - 1
    for i, l in enumerate(legs):
        if l["t0"] <= p < l["t0"] + l["dt"]:
            li = i
            break
    act = legs[li]
    lp = min(1.0, max(0.0, (p - act["t0"]) / act["dt"]))

    # La mappa si disegna su un'immagine sua e poi si incolla: i tratti degli altri
    # giorni escono dal riquadro (il Manghen sta ottanta chilometri da Orezzo) e
    # senza ritaglio attraversavano le didascalie.
    mp = Image.new("RGB", (map_w, map_h), BG)
    md = ImageDraw.Draw(mp)
    s = min(map_w / act["w"], map_h / act["h"]) * 0.96
    T = lambda q: (map_w / 2 + (q[0] - act["cx"]) * s, map_h / 2 + (q[1] - act["cy"]) * s)

    for i, l in enumerate(legs):                     # i tratti vicini restano sotto
        if i == li:
            continue
        md.line([T(q) for q in l["xy"]], fill=blend(ac, .60) if i < li else RULE,
                width=2, joint="curve")
    md.line([T(q) for q in act["xy"]], fill=RULE, width=2, joint="curve")

    i, h = head_at(act["xy"], act["cum"], lp)
    done = [T(q) for q in act["xy"][:i + 1]] + [T(h)]
    if len(done) > 1:
        md.line(done, fill=ac, width=3, joint="curve")
    dot = T(h)
    r = max(4, S // 96)
    md.ellipse([dot[0] - r * 2.4, dot[1] - r * 2.4, dot[0] + r * 2.4, dot[1] + r * 2.4],
               fill=blend(ac, .55))
    md.ellipse([dot[0] - r, dot[1] - r, dot[0] + r, dot[1] + r], fill=ac, outline=BG, width=2)
    im.paste(mp, (pad, map_top))

    # testata — senza l'icona davanti al titolo: la ZWJ di ❤️‍🩹 non lega in Segoe
    # e si leggeva come due emoji staccate. Resta nelle didascalie, dov'è citazione.
    label = "%02d" % n
    x = draw_text(dr, (pad, int(S * 0.044)), label, f_kick, f_emos, ac)
    draw_text(dr, (x + dr.textlength("  ", font=f_kick), int(S * 0.044)),
              "· " + st["kicker"].upper(), f_kick, f_emos, INK3)
    for k, line in enumerate(title_lines):
        draw_text(dr, (pad, int(S * 0.078) + k * int(S * 0.060)), line, f_title, f_emo, INK)

    # quale tratto si sta vedendo, quando la storia ne ha più di uno
    if len(legs) > 1:
        draw_text(dr, (pad, leg_y), act["leg"]["label"].upper(),
                  f_leg, f_emos, blend(ac, .25))

    # statistiche e la riga di storia
    y = foot_y
    stat = "%s km   ·   %s m D+   ·   %s" % (
        format(round(st["km"]), ",").replace(",", "."),
        format(st["gain"], ",").replace(",", "."),
        "%dh%02d" % (st["secs"] // 3600, st["secs"] % 3600 // 60))
    draw_text(dr, (pad, y), stat, f_stat, f_emos, ac)
    dr.line([(pad, y + int(S * 0.044)), (S - pad, y + int(S * 0.044))], fill=RULE, width=1)

    b = 0                                        # la riga giusta per questo istante
    for i, a in enumerate(st["beat_at"]):
        if p >= a:
            b = i
    ty = y + int(S * 0.064)
    for line in wrap(dr, st["beats"][b], f_beat, f_emo, S - 2 * pad)[:3]:
        draw_text(dr, (pad, ty), line, f_beat, f_emo, INK2)
        ty += int(S * 0.042)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=13, help="frame per storia")
    ap.add_argument("--size", type=int, default=440)
    ap.add_argument("--ms", type=int, default=95, help="durata di un frame")
    ap.add_argument("--story", help="renderizza solo questa storia")
    ap.add_argument("--colors", type=int, default=128, help="colori della tavolozza")
    ap.add_argument("--png", action="store_true", help="scrivi il provino, non la GIF")
    args = ap.parse_args()

    S = args.size
    stories = load_stories()
    fonts = (font("arialbd.ttf", int(S * 0.025)),     # kicker
             font("georgia.ttf", int(S * 0.056)),     # titolo
             font("arial.ttf", int(S * 0.032)),       # riga di storia
             font("arialbd.ttf", int(S * 0.027)),     # statistiche
             font("arialbd.ttf", int(S * 0.023)),     # nome del tratto
             font("seguiemj.ttf", int(S * 0.034)),    # emoji nel testo
             font("seguiemj.ttf", int(S * 0.024)))    # emoji piccoli

    if args.story:
        st = next(x for x in stories if x["slug"] == args.story)
        n = [x["slug"] for x in stories].index(args.story) + 1
        legs = prepare(st)
        grid = Image.new("RGB", (S * 3, S * 2), BG)
        for k, p in enumerate([0.05, 0.28, 0.5, 0.72, 0.9, 1.0]):
            grid.paste(render(st, p, S, fonts, n, legs), ((k % 3) * S, (k // 3) * S))
        grid.save(os.path.join(HERE, ".gif_check.png"))
        print("scritto tools/.gif_check.png")
        return

    frames = []
    for n, st in enumerate(stories, 1):
        legs = prepare(st)
        for k in range(args.frames):
            frames.append(render(st, k / (args.frames - 1.0), S, fonts, n, legs))
        print("  %02d %s" % (n, st["slug"]))

    dur = [args.ms] * len(frames)
    for i in range(args.frames - 1, len(frames), args.frames):   # pausa sull'ultimo
        dur[i] = args.ms * 5

    # Una tavolozza sola per tutta la GIF: in RGB pesava 3 MB, che per una cosa da
    # mandare in chat è troppo, e il disegno usa una manciata di colori.
    #
    # La tavolozza va costruita su un campione che contenga TUTTE le storie. Prima
    # veniva dal singolo frame più ricco di colori, e il risultato è stato che i
    # quattro accenti — arancio, blu, verde, marrone — finivano tutti sullo stesso
    # grigio oliva, perché in quel frame ce n'era uno solo.
    sample = Image.new("RGB", (S, S * len(stories)), BG)
    for i in range(len(stories)):
        sample.paste(frames[i * args.frames + args.frames - 1], (0, i * S))
    pal = sample.quantize(colors=args.colors, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], loop=0,
              duration=dur, optimize=True, disposal=2)
    print("\nscritto %s — %d frame, %.1f s, %.0f kB"
          % (OUT, len(frames), sum(dur) / 1000.0, os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()
