#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build top-20/_data.js — the twenty activities that tell the eleven years.

Where bike-to-work animates one repeated commute, this animates twenty different
days: the dot runs each route while five captions land in sequence beside it.

Each leg (an Intervals.icu activity) is downloaded once, thinned with
Douglas-Peucker at a 12 m tolerance (see simplify() for why not even
resampling), and stored as integer offsets of 1e-5 deg (~1.1 m) from the leg's
own south-west corner, delta-encoded. The page derives each leg's frame from the
points themselves, so every story zooms on its own without a shared projection.

    python build_top20.py                # fetch what's missing, write _data.js
    python build_top20.py --facts        # print the fact sheet, write nothing
    python build_top20.py --dry-run      # build everything, write nothing
    python build_top20.py --refetch      # ignore the stream cache
    python build_top20.py --tol 20       # coarser tracks, smaller _data.js

Needs INTERVALS_API_KEY (env, --api-key, or tools/.intervals_key — gitignored),
same as sync_intervals.py. `_data.js` is backed up to `_data.js.bak` first.
"""
import argparse
import base64
import io
import json
import math
import os
import shutil
import sys
import time
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://intervals.icu/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache_streams")
QUANT = 1e-5          # ~1,1 m — sotto questa soglia il dot non si muove di un pixel
TOL_M = 12.0          # tolleranza Douglas-Peucker: vedi simplify()
UA = "Mozilla/5.0 (micmer-tools) top20"   # senza UA Cloudflare risponde 1010


# ---------------------------------------------------------------- intervals

def api_key(cli=None):
    if cli:
        return cli
    for k in ("INTERVALS_API_KEY",):
        if os.environ.get(k):
            return os.environ[k]
    for p in (os.path.join(HERE, ".intervals_key"),
              os.path.expanduser("~/health-log/.env")):
        if os.path.exists(p):
            txt = io.open(p, encoding="utf-8").read()
            if "=" in txt:
                for line in txt.splitlines():
                    if line.startswith("INTERVALS_API_KEY"):
                        return line.split("=", 1)[1].strip()
            else:
                return txt.strip()
    sys.exit("manca INTERVALS_API_KEY (env, --api-key, o tools/.intervals_key)")


def api(path, key, tries=4):
    for n in range(tries):
        req = Request(BASE + path)
        req.add_header("Authorization", "Basic " +
                       base64.b64encode(("API_KEY:" + key).encode()).decode())
        req.add_header("User-Agent", UA)
        try:
            with urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if e.code in (429, 500, 502, 503) and n < tries - 1:
                time.sleep(2 + 3 * n)
                continue
            raise
        except URLError:
            if n < tries - 1:
                time.sleep(2 + 3 * n)
                continue
            raise


def streams(aid, key, refetch=False):
    """lat + lng + altitude + time for one activity, cached on disk.

    Intervals splits a paired stream across two fields: the `latlng` stream
    carries the latitudes in `data` and the longitudes in `data2`. Reading only
    `data` gives a list of plausible-looking floats that are all latitude — it
    fails as a shape, not as an error, so keep the two apart explicitly.
    """
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    p = os.path.join(CACHE, aid + ".json")
    if os.path.exists(p) and not refetch:
        return json.load(io.open(p, encoding="utf-8"))
    raw = api("/activity/%s/streams.json?types=latlng,altitude,time" % aid, key)
    out = {}
    for s in raw:
        if s["type"] == "latlng":
            out["lat"] = s.get("data") or []
            out["lng"] = s.get("data2") or []
        else:
            out[s["type"]] = s.get("data") or []
    json.dump(out, io.open(p, "w", encoding="utf-8"))
    return out


def activity(aid, key, refetch=False):
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    p = os.path.join(CACHE, aid + ".meta.json")
    if os.path.exists(p) and not refetch:
        return json.load(io.open(p, encoding="utf-8"))
    a = api("/activity/%s" % aid, key)
    json.dump(a, io.open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return a


# ---------------------------------------------------------------- geometry

def haversine(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def simplify(lat, lng, alt, tol_m=TOL_M):
    """Douglas-Peucker, keeping the altitude of every surviving fix.

    Resampling evenly along the distance was the obvious first move and it is
    the wrong one: it spends points on the straight of the Padana and starves
    the hairpins, so at 260 points the Maratona dles Dolomites came out 23 %
    short and the Mortirolo looked like a gentle arc. Douglas-Peucker puts the
    points where the curvature actually is — the same 136 km route holds within
    2 % of its real length on 989 points, where 1.200 even ones lost 8 %.

    Points therefore come out unevenly spaced, so whoever animates them has to
    walk the polyline by arc length rather than by index. The page does.
    """
    n = min(len(lat), len(lng))
    keep0 = [i for i in range(n) if lat[i] is not None and lng[i] is not None]
    pts = [(lat[i], lng[i]) for i in keep0]
    # gli open-water swim tornano con latlng buono e altitude tutta null
    if alt and len(alt) >= n:
        alts = [alt[i] if alt[i] is not None else 0.0 for i in keep0]
    else:
        alts = [0.0] * len(pts)
    if len(pts) < 2:
        return [], []

    m = len(pts)
    lat0 = sum(p[0] for p in pts) / m
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    P = [(p[1] * kx, p[0] * ky) for p in pts]          # metri locali, piatti
    keep = [False] * m
    keep[0] = keep[-1] = True
    stack = [(0, m - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = P[a]
        bx, by = P[b]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = P[i]
            if L2 <= 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > best:
                best, bi = d, i
        if best > tol_m:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    idx = [i for i in range(m) if keep[i]]
    return [pts[i] for i in idx], [alts[i] for i in idx]


def encode(pts):
    """Delta-encoded integer offsets from the leg's own south-west corner."""
    lat0 = min(p[0] for p in pts)
    lng0 = min(p[1] for p in pts)
    q = [(int(round((p[0] - lat0) / QUANT)), int(round((p[1] - lng0) / QUANT))) for p in pts]
    d, prev = [], (0, 0)
    for x in q:
        d.append(x[0] - prev[0])
        d.append(x[1] - prev[1])
        prev = x
    return round(lat0, 6), round(lng0, 6), d


# ---------------------------------------------------------------- build

def hm(secs):
    secs = int(secs or 0)
    return "%dh%02d" % (secs // 3600, (secs % 3600) // 60)


def build(cfg, key, refetch=False, tol=None):
    tol = tol or TOL_M
    stories = []
    for s in cfg["stories"]:
        legs, tot_km, tot_gain, tot_secs, elapsed = [], 0.0, 0.0, 0.0, 0.0
        first_start = last_end = None
        for lg in s["legs"]:
            a = activity(lg["id"], key, refetch)
            st = streams(lg["id"], key, refetch)
            pts, alts = simplify(st.get("lat") or [], st.get("lng") or [],
                                 st.get("altitude") or [], tol)
            if not pts:
                print("  !! %s / %s: nessun GPS" % (s["slug"], lg["id"]))
                continue
            lat0, lng0, d = encode(pts)
            a0 = min(alts) if alts else 0
            legs.append({
                "sport": lg["sport"], "label": lg["label"],
                "lat0": lat0, "lng0": lng0, "d": d,
                "alt": [int(round(x - a0)) for x in alts], "alt0": int(round(a0)),
                "km": round((a.get("distance") or 0) / 1000.0, 2),
                "gain": int(round(a.get("total_elevation_gain") or 0)),
                "secs": int(a.get("moving_time") or 0),
                "date": a["start_date_local"][:10],
                "start": a["start_date_local"][11:16],
            })
            tot_km += (a.get("distance") or 0) / 1000.0
            tot_gain += a.get("total_elevation_gain") or 0
            tot_secs += a.get("moving_time") or 0
            t0 = datetime.fromisoformat(a["start_date_local"])
            t1 = t0.timestamp() + (a.get("elapsed_time") or a.get("moving_time") or 0)
            first_start = t0.timestamp() if first_start is None else min(first_start, t0.timestamp())
            last_end = t1 if last_end is None else max(last_end, t1)
        if not legs:
            continue

        # La linea del tempo si decide QUI, non nella pagina e non nella GIF: due
        # implementazioni dello stesso peso divergono al primo ritocco, e si è già
        # visto cosa succede — le didascalie della clavicola parlavano del 17
        # maggio mentre il puntino correva il Manghen del 29 giugno.
        #
        # pace "km" (default): il tempo va con la radice dei chilometri. Serve
        # dentro una giornata sola — a peso lineare il nuoto dell'Ironman (3,9 km
        # su 223) durerebbe sette centesimi di animazione.
        # pace "chapters": tempo uguale per tratto. Serve quando i tratti sono
        # giorni diversi, dove i chilometri non dicono quanto conta il capitolo.
        pace = s.get("pace", "km")
        if pace == "chapters":
            wts = [1.0] * len(legs)
        else:
            wts = [math.sqrt(max(l["km"], 0.4)) for l in legs]
        wsum = sum(wts) or 1.0
        acc = 0.0
        for l, w in zip(legs, wts):
            l["t0"] = round(acc, 5)
            l["dt"] = round(w / wsum, 5)
            acc += w / wsum

        # e quando ogni riga di storia appartiene a un tratto preciso, le due cose
        # si allineano invece di scorrere l'una sull'altra
        beat_at = s.get("beat_at")
        if not beat_at:
            beat_at = [round(i / len(s["beats"]), 4) for i in range(len(s["beats"]))]
        if len(beat_at) != len(s["beats"]):
            sys.exit("%s: %d beat_at per %d righe" % (s["slug"], len(beat_at), len(s["beats"])))

        stories.append({
            "pace": pace, "beat_at": beat_at,
            "slug": s["slug"], "year": s["year"], "title": s["title"],
            "kicker": s["kicker"], "icon": s["icon"], "accent": s["accent"],
            "beats": s["beats"], "legs": legs,
            "km": round(tot_km, 1), "gain": int(round(tot_gain)),
            "secs": int(tot_secs), "elapsed": int(round((last_end or 0) - (first_start or 0))),
        })
        print("  %-24s %2d leg  %7.1f km  %5d m  %s  %5d punti" %
              (s["slug"], len(legs), tot_km, tot_gain, hm(tot_secs),
               sum(len(l["alt"]) for l in legs)))
    return stories


def facts(stories):
    """Everything a caption might claim, checked against the numbers."""
    print("\n=== fact sheet ===")
    for s in stories:
        print("\n%s — %s (%s)" % (s["slug"], s["title"], s["kicker"]))
        print("   totale: %.1f km · %d m · %s in movimento · %s dal via all'arrivo"
              % (s["km"], s["gain"], hm(s["secs"]), hm(s["elapsed"])))
        for lg in s["legs"]:
            top = (lg["alt0"] + max(lg["alt"])) if lg["alt"] else 0
            print("   · %-38s %7.1f km  %5d m  %s  quota max %d m"
                  % (lg["label"], lg["km"], lg["gain"], hm(lg["secs"]), top))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "top-20.json"))
    ap.add_argument("--api-key")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--tol", type=float, help="tolleranza Douglas-Peucker in metri")
    args = ap.parse_args()

    cfg = json.load(io.open(args.config, encoding="utf-8"))
    key = api_key(args.api_key)
    print("costruisco %d storie" % len(cfg["stories"]))
    stories = build(cfg, key, args.refetch, args.tol)
    facts(stories)
    if args.facts or args.dry_run:
        print("\n(niente scritto)")
        return

    out = os.path.join(HERE, cfg["out_data"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        shutil.copy2(out, out + ".bak")
    body = ["// top-20 — generato %s da tools/build_top20.py" % date.today().isoformat(),
            "// tracce GPS da Intervals.icu, offset interi di 1e-5 deg, delta-encoded",
            "const QUANT=%r;" % QUANT,
            "const STORIES=" + json.dumps(stories, ensure_ascii=False, separators=(",", ":")) + ";"]
    io.open(out, "w", encoding="utf-8").write("\n".join(body) + "\n")
    print("\nscritto %s (%.0f kB)" % (out, os.path.getsize(out) / 1024.0))


if __name__ == "__main__":
    main()
