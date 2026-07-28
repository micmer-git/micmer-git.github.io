#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build gazzaniga-orezzo/_tracks.js — the real GPS of every effort on the climb.

The ghost race on esplora.html used to slide four markers along one reference
ROUTE at constant pace. This emits the actual recorded trace of every single
effort, cropped to the segment, so the ghost can animate all of them at once
the way bike-to-work animates all its mornings.

Reuses sync_intervals.py's detection verbatim (35 m geofence on the segment
start/end, plausible duration, altitude gain must match) so the efforts here are
the same ones already in _data.js.

Each track is resampled to N points evenly in time and stored as integer
offsets of 1e-5 deg (~1.1 m) from a shared origin, delta-encoded — a raw float
dump would be several megabytes.

    python build_go_tracks.py                 # scan everything
    python build_go_tracks.py --ids ids.json  # only these activity ids
"""
import argparse, io, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_intervals as SI                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(io.open(os.path.join(HERE, "gazzaniga-orezzo.json"), encoding="utf-8"))
OUT = os.path.join(HERE, "..", "gazzaniga-orezzo", "_tracks.js")

# Il ghost e' una gara: tutti devono correre lo STESSO tratto. I due target in
# gazzaniga-orezzo.json sono due segmenti Strava diversi (bici 3,36 km, corsa
# 4,29 km), quindi qui si usa la salita intera per entrambi gli sport e il tempo
# si misura davvero sul GPS, invece di riscalare il segmento bici come fa
# index.html. Le due misure vanno confrontate: vedi --check.
_RUN = next(t for t in CFG["targets"] if t["layout"] == "run")
FULL = {"start": _RUN["start"], "end": _RUN["end"], "gain_m": _RUN["gain_m"],
        "dist_km": _RUN["dist_km"]}
# finestre di durata sulla salita INTERA, per sport (quelle in config sono sui
# due segmenti Strava piu corti)
SECS = {"bike": [620, 1900], "run": [1050, 2800]}
# la lunghezza percorsa deve somigliare alla salita: scarta gli accoppiamenti
# start/end che tagliano (un pezzo di salita fatto due volte, un buco GPS)
LEN_TOL = (0.85, 1.15)


def sport_of(a):
    """Non fidarsi di `type`: alcune uscite in bici sono registrate come Run.

    Tre casi reali qui: 43,6 km a 3:21/km, 36,2 km a 2:52/km e 98,8 km a
    2:27/km, tutti etichettati "Run". Passavano la finestra di durata e
    finivano nella corsa dei fantasmi come record impossibili. La velocita
    media dell'attivita separa i due sport senza ambiguita: la maratona piu
    veloce di Michele viaggia a 12,5 km/h, le uscite in bici stanno sopra 15.
    """
    dist, mov = a.get("distance") or 0, a.get("moving_time") or 0
    if dist > 3000 and mov > 300:
        return "bike" if (dist / mov) * 3.6 > 15.0 else "run"
    return {"Ride": "bike", "Run": "run"}.get(a.get("type"))


def path_len(lat, lng, i0, i1):
    """Metri effettivamente percorsi fra due indici, a piena risoluzione."""
    tot, prev = 0.0, None
    for i in range(i0, i1 + 1):
        if lat[i] is None or lng[i] is None:
            continue
        if prev is not None:
            tot += SI.haversine(prev, (lat[i], lng[i]))
        prev = (lat[i], lng[i])
    return tot

N_PTS = 60          # punti per traccia: sotto i 60 le curve dei tornanti si spezzano
QUANT = 1e-5        # ~1,1 m

# sync_intervals.api_text swallows a 429 and returns None, so a plain retry loop
# can't see it. Pace the calls ourselves and retry anything that comes back
# empty — a few hundred stream downloads in a row will otherwise get throttled.
_gate = threading.Lock()
_next_at = [0.0]
MIN_GAP = 0.28      # secondi fra due richieste, su tutti i thread


def throttled_streams(act_id, key, tries=6):
    for attempt in range(tries):
        with _gate:
            wait = _next_at[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _next_at[0] = time.monotonic() + MIN_GAP
        st = SI.fetch_streams(act_id, key)
        if st and "lat" in st and "lng" in st:
            return st
        if st is not None and st != {}:
            return st                     # attivita senza GPS: inutile riprovare
        time.sleep(1.5 + attempt * 2.5)   # quasi sempre un 429
    return None


def crop(st, i0, i1, n=N_PTS):
    """Resample one effort's fixes to n points evenly spaced in time."""
    lat, lng, tm = st["lat"], st["lng"], st.get("time") or list(range(len(st["lat"])))
    t0, t1 = tm[i0], tm[i1]
    if t1 <= t0:
        return None
    pts = [(tm[i], lat[i], lng[i]) for i in range(i0, i1 + 1)
           if lat[i] is not None and lng[i] is not None and tm[i] is not None]
    if len(pts) < 8:
        return None
    out, j = [], 0
    for k in range(n):
        want = t0 + (t1 - t0) * k / (n - 1)
        while j < len(pts) - 2 and pts[j + 1][0] < want:
            j += 1
        a, b = pts[j], pts[min(j + 1, len(pts) - 1)]
        f = 0 if b[0] == a[0] else (want - a[0]) / (b[0] - a[0])
        f = max(0.0, min(1.0, f))
        out.append((a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f))
    return out


def encode(track, olat, olng):
    """Delta-encoded integer offsets from the shared origin."""
    q = [(int(round((la - olat) / QUANT)), int(round((ln - olng) / QUANT))) for la, ln in track]
    out, pa, pb = [], 0, 0
    for a, b in q:
        out.append(a - pa); out.append(b - pb)
        pa, pb = a, b
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--radius", type=float, default=35.0)
    ap.add_argument("--ids", help="JSON list/dict of activity ids to restrict the scan to")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    key = SI.get_api_key(args.key)

    acts = SI.api(f"athlete/{CFG['athlete_id']}/activities"
                  "?oldest=2015-01-01&newest=2026-12-31", key) or []
    acts = [a for a in acts if a.get("type") in ("Ride","Run") and a.get("source") != "STRAVA"]
    if args.ids:
        raw = json.load(io.open(args.ids, encoding="utf-8"))
        keep = set(raw if isinstance(raw, list) else raw.keys())
        acts = [a for a in acts if a["id"] in keep]
    print(f"{len(acts)} candidate activities", flush=True)

    results, errors = [], []

    def work(a):
        try:
            st = throttled_streams(a["id"], key)
        except Exception as e:                                       # pragma: no cover
            return ("err", a["id"], str(e)[:60])
        if st is None:
            return ("err", a["id"], "throttled out")
        if "lat" not in st or "lng" not in st:
            return None
        sport = sport_of(a)
        if not sport:
            return None
        found = []
        tgt = FULL
        lat, lng, tm = st["lat"], st["lng"], st.get("time") or list(range(len(st["lat"])))
        alt = st.get("altitude") or []
        lo, hi = SECS[sport]
        want_m = tgt["dist_km"] * 1000
        cands = []
        for i0 in SI.passes(lat, lng, tgt["start"], args.radius):
            for i1 in SI.passes(lat, lng, tgt["end"], args.radius):
                if i1 <= i0:
                    continue
                secs = tm[i1] - tm[i0]
                if not (lo <= secs <= hi):
                    continue
                if alt and alt[i0] is not None and alt[i1] is not None:
                    if abs((alt[i1] - alt[i0]) - tgt["gain_m"]) > 0.3 * tgt["gain_m"]:
                        continue
                L = path_len(lat, lng, i0, i1)
                if not (LEN_TOL[0] * want_m <= L <= LEN_TOL[1] * want_m):
                    continue
                cands.append((i0, i1, int(round(secs))))
        cands.sort(key=lambda c: c[2])
        kept = []
        for i0, i1, secs in cands:
            if all(i1 <= k0 or i0 >= k1 for k0, k1, _ in kept):
                kept.append((i0, i1, secs))
        for i0, i1, secs in kept:
            tr = crop(st, i0, i1)
            if tr:
                found.append({"d": a["start_date_local"][:10],
                              "h": round(int(a["start_date_local"][11:13])
                                         + int(a["start_date_local"][14:16]) / 60, 2),
                              "s": secs, "t": sport, "tr": tr,
                              "n": (a.get("name") or "")[:44]})
        return ("ok", found) if found else None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(work, acts)):
            if r and r[0] == "ok":
                results.extend(r[1])
            elif r and r[0] == "err":
                errors.append(r[1:])
            if i % 100 == 0:
                print(f"  {i}/{len(acts)} · {len(results)} efforts", flush=True)

    if not results:
        sys.exit("no efforts found")
    results.sort(key=lambda r: (r["d"], r["s"]))

    olat = min(min(p[0] for p in r["tr"]) for r in results)
    olng = min(min(p[1] for p in r["tr"]) for r in results)
    olat, olng = round(olat, 5), round(olng, 5)

    payload = {
        "meta": {
            "origin": [olat, olng], "quant": QUANT, "pts": N_PTS,
            "efforts": len(results),
            "section": {"dist_km": FULL["dist_km"], "gain_m": FULL["gain_m"],
                        "start": FULL["start"], "end": FULL["end"]},
            "bike": sum(1 for r in results if r["t"] == "bike"),
            "run": sum(1 for r in results if r["t"] == "run"),
            "note": "Tracce GPS reali, ritagliate sulla salita intera Gazzaniga-Orezzo "
                    "(stesso tratto per bici e corsa, tempo misurato sul GPS) e "
                    "ricampionate a %d punti equidistanti nel tempo. Offset interi "
                    "da origin, passo %g gradi (~1,1 m), delta-encoded." % (N_PTS, QUANT),
        },
        "efforts": [{"d": r["d"], "h": r["h"], "s": r["s"], "t": r["t"],
                     "n": r["n"], "p": encode(r["tr"], olat, olng)} for r in results],
    }
    js = ("// generated by tools/build_go_tracks.py — do not edit by hand\n"
          "const TRACKS=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    io.open(OUT, "w", encoding="utf-8").write(js)
    print(f"wrote {OUT}  {len(js)/1024:.0f} KB")
    print(f"efforts {len(results)} (bike {payload['meta']['bike']}, run {payload['meta']['run']})"
          f" · errors {len(errors)}")


if __name__ == "__main__":
    main()
