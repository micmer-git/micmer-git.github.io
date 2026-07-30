#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""basemap.py — raster basemaps and an orthographic globe, in the site's palette.

Used by build_top20_reel.py. Two jobs:

* **Local basemap** — stitches CARTO Positron tiles into one image covering a
  bounding box, then recolours it. Positron ships cool light grey; the pages are
  warm cream (#faf8f3), and a grey map under a cream caption band looks like two
  different documents. The recolour keeps land warm and water cool, so the coast
  at Sanremo, Barcelona, Malaga and Boston still reads as coast.
* **Globe** — orthographic projection of Natural Earth's 110 m land polygons, for
  the transitions that cross an ocean.

Tiles and the land file are cached under `tools/.cache_tiles/` (gitignored) and
fetched at most once. **Attribution is not optional**: anything drawn on these
tiles must carry "© OpenStreetMap · © CARTO", and CREDIT below is that string.

    python basemap.py --demo        # scrive tools/.basemap_demo.png
"""
import io
import json
import math
import os
import sys
import time
import urllib.request

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache_tiles")
TILE_URL = "https://a.basemaps.cartocdn.com/{style}/{z}/{x}/{y}{r}.png"
LAND_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
UA = "micmer-top20/1.0 (personal one-off map render; contact michelemerelli.8@gmail.com)"
CREDIT = "© OpenStreetMap · © CARTO"
TS = 256

# ------------------------------------------------------------------ palette
PAPER = (250, 248, 243)
INK = (20, 21, 15)
INK2 = (92, 95, 82)
INK3 = (143, 147, 130)
RULE = (228, 225, 214)

# land: dal segno più scuro (strade, etichette) alla carta
LAND_RAMP = [(0.00, (150, 140, 122)), (0.45, (214, 206, 188)),
             (0.72, (235, 230, 216)), (1.00, (250, 248, 243))]
# acqua: tenuta fredda, o la costa scompare
WATER_RAMP = [(0.00, (150, 168, 176)), (0.55, (198, 214, 219)),
              (1.00, (222, 233, 236))]


def _ramp(ramp, t):
    t = max(0.0, min(1.0, t))
    for i in range(len(ramp) - 1):
        a, ca = ramp[i]
        b, cb = ramp[i + 1]
        if a <= t <= b:
            f = 0.0 if b == a else (t - a) / (b - a)
            return tuple(int(round(ca[j] + (cb[j] - ca[j]) * f)) for j in range(3))
    return ramp[-1][1]


def _luts():
    """Two 256-entry lookup tables, so recolouring is a per-channel map."""
    land = [_ramp(LAND_RAMP, i / 255.0) for i in range(256)]
    water = [_ramp(WATER_RAMP, i / 255.0) for i in range(256)]
    return land, water


LUT_LAND, LUT_WATER = _luts()


def _colorize(lum, lut):
    """Map an L-mode image through a 256-entry RGB table, in C not in Python."""
    return Image.merge("RGB", tuple(
        lum.point([lut[i][ch] for i in range(256)]) for ch in range(3)))


def recolour(im):
    """Positron grey -> the site's cream, with water still cool.

    Water in Positron is a desaturated blue, land and roads are neutral: the blue
    channel running ahead of the red is a reliable enough separator, and it is the
    only one available without a second vector layer.

    Done with channel operations rather than a per-pixel loop: the reel needs
    twenty mosaics of a couple of megapixels each, and in pure Python that was
    minutes of wall clock for something Pillow does in C.
    """
    im = im.convert("RGB")
    r, g, b = im.split()
    lum = im.convert("L")
    # b - r >= 6  ->  acqua
    wet = ImageChops.subtract(b, r).point(lambda v: 255 if v >= 6 else 0)
    return Image.composite(_colorize(lum, LUT_WATER), _colorize(lum, LUT_LAND), wet)


# ------------------------------------------------------------- slippy tiles

def lon2x(lon, z):
    return (lon + 180.0) / 360.0 * (1 << z)


def lat2y(lat, z):
    lat = max(-85.05112878, min(85.05112878, lat))
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * (1 << z)


def x2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0


def y2lat(y, z):
    n = math.pi - 2.0 * math.pi * y / (1 << z)
    return math.degrees(math.atan(math.sinh(n)))


def fetch_tile(z, x, y, style="light_all", retina=True):
    n = 1 << z
    if not (0 <= y < n):
        return None
    x %= n
    r = "@2x" if retina else ""
    p = os.path.join(CACHE, "%s_%d_%d_%d%s.png" % (style, z, x, y, "@2x" if retina else ""))
    if os.path.exists(p):
        try:
            return Image.open(p).convert("RGB")
        except OSError:
            os.remove(p)
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    url = TILE_URL.format(style=style, z=z, x=x, y=y, r=r)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
            io.open(p, "wb").write(data)
            time.sleep(0.06)                     # gentile col server
            return Image.open(p).convert("RGB")
        except Exception:
            if attempt == 3:
                return None
            time.sleep(1.2 + 2 * attempt)
    return None


def zoom_for(span_deg_x, span_deg_y, px, lat0, zmax=15):
    """Deepest zoom whose tile mosaic still covers the span within px pixels."""
    for z in range(zmax, 1, -1):
        wx = (lon2x(180, z) - lon2x(180 - span_deg_x, z)) * TS
        wy = abs(lat2y(lat0 + span_deg_y / 2, z) - lat2y(lat0 - span_deg_y / 2, z)) * TS
        if max(wx, wy) <= px:
            return z
    return 2


def mosaic(lat_min, lat_max, lon_min, lon_max, px=1400, style="light_all",
           retina=True, warm=True, zmax=15):
    """One recoloured image covering the box, plus the transform to place points.

    Returns (image, to_px) where to_px(lat, lng) -> (x, y) in that image. The
    image is deliberately bigger than any frame that will be cropped out of it:
    the reel zooms by cropping this, so its resolution sets how deep the zoom can
    go before it turns to mush.
    """
    lat0 = (lat_min + lat_max) / 2
    z = zoom_for(max(lon_max - lon_min, 1e-4), max(lat_max - lat_min, 1e-4), px, lat0, zmax)
    scale = 2 if retina else 1
    ts = TS * scale

    x0, x1 = lon2x(lon_min, z), lon2x(lon_max, z)
    y0, y1 = lat2y(lat_max, z), lat2y(lat_min, z)
    tx0, tx1 = int(math.floor(x0)), int(math.ceil(x1))
    ty0, ty1 = int(math.floor(y0)), int(math.ceil(y1))

    W = (tx1 - tx0) * ts
    H = (ty1 - ty0) * ts
    canvas = Image.new("RGB", (max(W, ts), max(H, ts)), (248, 248, 248))
    for tx in range(tx0, tx1):
        for ty in range(ty0, ty1):
            t = fetch_tile(z, tx, ty, style, retina)
            if t is None:
                continue
            if t.size != (ts, ts):
                t = t.resize((ts, ts), Image.LANCZOS)
            canvas.paste(t, ((tx - tx0) * ts, (ty - ty0) * ts))
    if warm:
        canvas = recolour(canvas)

    def to_px(lat, lng):
        return ((lon2x(lng, z) - tx0) * ts, (lat2y(lat, z) - ty0) * ts)

    return canvas, to_px


# -------------------------------------------------------------------- globe

def land_polys():
    p = os.path.join(CACHE, "ne_110m_land.geojson")
    if not os.path.exists(p):
        if not os.path.isdir(CACHE):
            os.makedirs(CACHE)
        req = urllib.request.Request(LAND_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            io.open(p, "wb").write(r.read())
    gj = json.load(io.open(p, encoding="utf-8"))
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in parts:
            if poly:
                out.append([(c[1], c[0]) for c in poly[0]])   # (lat, lng), outer ring
    return out


_LAND = None


def globe(S, lat0, lon0, radius_frac=0.86, ocean=(226, 236, 238),
          land=(238, 233, 220), edge=(197, 205, 200), bg=PAPER):
    """Orthographic globe centred on (lat0, lon0), on an S x S canvas.

    Returns (image, project) where project(lat, lng) -> (x, y, visible). The
    hemisphere test is what makes it a globe and not a disc with the far side
    showing through, so callers must honour `visible`.
    """
    global _LAND
    if _LAND is None:
        _LAND = land_polys()
    im = Image.new("RGB", (S, S), bg)
    dr = ImageDraw.Draw(im)
    R = S * radius_frac / 2.0
    cx = cy = S / 2.0
    dr.ellipse([cx - R, cy - R, cx + R, cy + R], fill=ocean, outline=edge, width=1)

    p0 = math.radians(lat0)
    l0 = math.radians(lon0)
    sin0, cos0 = math.sin(p0), math.cos(p0)

    def project(lat, lng):
        p = math.radians(lat)
        dl = math.radians(lng) - l0
        cosc = sin0 * math.sin(p) + cos0 * math.cos(p) * math.cos(dl)
        x = cx + R * (math.cos(p) * math.sin(dl))
        y = cy - R * (cos0 * math.sin(p) - sin0 * math.cos(p) * math.cos(dl))
        return x, y, cosc > 0

    # I punti oltre l'orizzonte si spingono sul bordo del disco invece di scartare
    # il poligono. Scartarlo era la prima versione ed era sbagliata in modo
    # spettacolare: l'Eurasia e l'Africa sono un unico anello che l'orizzonte
    # taglia sempre, quindi il globo mostrava quattro isole e niente continenti.
    # Spingere sul bordo non è un vero ritaglio sferico, ma per una terra di
    # sfondo a 110 m di risoluzione il risultato combacia col limbo.
    for ring in _LAND:
        pts, seen = [], False
        for lat, lng in ring:
            x, y, vis = project(lat, lng)
            if vis:
                seen = True
            else:
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy) or 1.0
                x, y = cx + dx / d * R, cy + dy / d * R
            pts.append((x, y))
        # Un anello con NESSUN punto visibile va scartato, non spinto sul bordo:
        # spingendolo, tutti i suoi vertici finiscono sulla circonferenza e il
        # poligono che ne esce riempie il disco intero. Girando il globo verso
        # l'Atlantico l'ultimo frame diventava tutto terra per colpa di questo.
        if seen and len(pts) > 2:
            dr.polygon(pts, fill=land, outline=edge)
    return im, project


# --------------------------------------------------------------------- demo

def _square(im, S):
    """Centre crop to a square, then scale — squashing a wide mosaic to a square
    was distorting the coastline in the first demo."""
    w, h = im.size
    k = min(w, h)
    im = im.crop(((w - k) // 2, (h - k) // 2, (w - k) // 2 + k, (h - k) // 2 + k))
    return im.resize((S, S), Image.LANCZOS)


def _demo():
    S = 520
    out = Image.new("RGB", (S * 3, S), PAPER)
    im, _ = mosaic(43.75, 44.45, 7.55, 8.60, px=S * 2, style="light_all")
    out.paste(_square(im, S), (0, 0))
    g1, _ = globe(S, 45.0, 9.5)
    out.paste(g1, (S, 0))
    g2, _ = globe(S, 42.0, -55.0)
    out.paste(g2, (S * 2, 0))
    p = os.path.join(HERE, ".basemap_demo.png")
    out.save(p)
    print("scritto", p)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        print(__doc__)
