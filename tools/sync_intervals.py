#!/usr/bin/env python3
"""
sync_intervals.py — pull new climb efforts from Intervals.icu into a climb-story `_data.js`.

Replaces the copy/paste-the-Strava-leaderboard step: reads the last date already in
`_data.js`, asks Intervals.icu for activities since then, finds the efforts on the
configured segment, and appends the new rows in place.

How an effort is extracted from an activity:

  1. **GPS geofence** (the one that actually works) — download the activity streams
     and time the passage between the segment's start and end coordinates. Needs
     nothing but GPS. The numbers land within a second or two of Strava's, but they
     are *our* timings, not Strava's — Strava interpolates across the exact start/end
     lines, we snap to the nearest 1 Hz fix.
  2. **segment efforts** — tried first, but as of 2026-07 the Intervals.icu v1 API has
     no segment endpoint at all: /activity/{id}/segment-efforts, /segments,
     /athlete/{id}/segments etc. all 404 on the router (while /activity/{id} and
     /activity/{id}/streams.json 401, i.e. they exist). The probe also scans the
     activity detail payload in case segments ever show up there. Costs three wasted
     calls on the first activity, then switches itself off for the run.
     Run with `--probe` to re-check whether Intervals has added one.

If you want Strava's own segment times rather than ours, that needs the Strava API
(`GET /segments/{id}/all_efforts`) and an OAuth token with activity:read_all — not
this script.

Usage
-----
    set INTERVALS_API_KEY=...            (or --api-key, or tools/.intervals_key)

    python sync_intervals.py --config tools/gazzaniga-orezzo.json --dry-run
    python sync_intervals.py --config tools/gazzaniga-orezzo.json
    python sync_intervals.py --config tools/gazzaniga-orezzo.json --probe
    python sync_intervals.py --config tools/gazzaniga-orezzo.json --since 2026-06-01

Nothing is written unless at least one new row was found; the previous `_data.js`
is copied to `_data.js.bak` first.
"""
import argparse
import base64
import csv
import io
import json
import math
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://intervals.icu/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))

# activity names carry accents; a cp1252 console must not kill the sync
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- auth / http

def get_api_key(explicit=None):
    if explicit:
        return explicit
    key = os.environ.get("INTERVALS_API_KEY")
    if key:
        return key.strip()
    for p in (os.path.join(HERE, ".intervals_key"),
              os.path.expanduser("~/.intervals_key")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                k = f.read().strip()
            if k:
                return k
    sys.exit("No API key. Set INTERVALS_API_KEY, pass --api-key, or put it in "
             "tools/.intervals_key (Intervals.icu ▸ Settings ▸ Developer).")


def api_text(path, key, quiet=False):
    """GET {BASE}/{path} with Intervals.icu basic auth. Returns the raw body or None."""
    creds = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    req = Request(f"{BASE}/{path}", headers={
        "Authorization": f"Basic {creds}",
        # Cloudflare fronts intervals.icu and answers the default python-urllib
        # agent with "error code: 1010" (banned browser signature) before the
        # request reaches the API. Any ordinary UA gets through.
        "User-Agent": "micmer-vita-sync/1.0 (+https://micmer-git.github.io/vita/)",
    })
    try:
        with urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        if not quiet:
            print(f"    ! {e} on /{path}", file=sys.stderr)
        return None


def api(path, key, quiet=False):
    """GET {BASE}/{path} with Intervals.icu basic auth. Returns parsed JSON or None."""
    creds = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    req = Request(f"{BASE}/{path}", headers={
        "Authorization": f"Basic {creds}",
        "Accept": "application/json",
        # Cloudflare sits in front of intervals.icu and answers the default
        # python-urllib agent with "error code: 1010" (banned browser signature)
        # before the request ever reaches the API. Any ordinary UA gets through.
        "User-Agent": "micmer-vita-sync/1.0 (+https://micmer-git.github.io/vita/)",
    })
    try:
        with urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if not quiet:
            print(f"    ! HTTP {e.code} on /{path}", file=sys.stderr)
        return None
    except (URLError, json.JSONDecodeError) as e:
        if not quiet:
            print(f"    ! {e} on /{path}", file=sys.stderr)
        return None


# ------------------------------------------------------------------ geometry

def haversine(a, b):
    """Metres between two (lat, lng) pairs."""
    E = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * E * math.asin(math.sqrt(h))


# ------------------------------------------------------------- _data.js I/O

ARRAY_RE = r"const %s\s*=\s*(\[.*?\])\s*;"


def read_array(text, name):
    """Parse `const NAME=[[...],[...]];` out of a _data.js into a list of lists."""
    m = re.search(ARRAY_RE % re.escape(name), text, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def write_array(text, name, rows):
    """Replace `const NAME=[...]` in place, keeping the file's one-row-per-comma style."""
    body = ",".join("[" + ",".join(fmt_num(v) for v in r) + "]" for r in rows)
    repl = f"const {name}=[\n{body}\n]"
    return re.sub(ARRAY_RE % re.escape(name),
                  lambda _m: repl + ";", text, count=1, flags=re.S)


def fmt_num(v):
    if isinstance(v, float):
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def row_date(row):
    return date(row[0], row[1], row[2])


# ------------------------------------------------------- segment-effort path

# No segment endpoint exists in the v1 API today (all of these 404 on the router).
# Kept as a one-shot probe so the day Intervals adds one, this starts using it.
SEGMENT_ENDPOINTS = [
    "activity/{id}/segment-efforts",
    "activity/{id}/segments",
    "activity/{id}",          # in case segments ride along in the detail payload
]

_endpoint_cache = {"path": None, "resolved": False}


def fetch_segment_efforts(act_id, key, probe=False):
    """Return a list of segment-effort dicts for an activity, or None if unsupported."""
    if _endpoint_cache["resolved"] and _endpoint_cache["path"] is None:
        return None
    paths = ([_endpoint_cache["path"]] if _endpoint_cache["path"]
             else SEGMENT_ENDPOINTS)
    for p in paths:
        data = api(p.format(id=act_id), key, quiet=not probe)
        if probe:
            print(f"    probe /{p.format(id=act_id)} -> "
                  f"{type(data).__name__} {json.dumps(data)[:400] if data else data}")
        if isinstance(data, list) and data:
            _endpoint_cache["path"] = p
            _endpoint_cache["resolved"] = True
            return data
        if isinstance(data, dict):
            for k in ("segment_efforts", "segmentEfforts", "efforts", "segments"):
                if isinstance(data.get(k), list) and data[k]:
                    _endpoint_cache["path"] = p
                    _endpoint_cache["resolved"] = True
                    return data[k]
    _endpoint_cache["resolved"] = True
    _endpoint_cache["path"] = None
    return None


def dig(d, *names):
    """First non-None value among several possible key spellings, nested-safe."""
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    seg = d.get("segment") if isinstance(d, dict) else None
    if isinstance(seg, dict):
        for n in names:
            if seg.get(n) is not None:
                return seg[n]
    return None


def match_segment(effort, target):
    """Does this segment effort belong to the segment we track?"""
    sid = dig(effort, "strava_id", "stravaId", "segment_id", "segmentId", "id")
    want = target.get("segment_id")
    if want and sid and str(sid) == str(want):
        return True
    name = dig(effort, "name", "segment_name", "segmentName")
    want_name = (target.get("segment_name") or "").lower()
    return bool(want_name and name and want_name in str(name).lower())


def effort_from_segment(effort):
    """(secs, hr, watts) from a segment-effort dict, or None."""
    secs = dig(effort, "elapsed_time", "elapsedTime", "moving_time", "movingTime",
               "duration", "time")
    if not secs:
        return None
    hr = dig(effort, "average_heartrate", "averageHeartrate", "avg_hr", "icu_average_hr")
    w = dig(effort, "average_watts", "averageWatts", "avg_watts", "icu_average_watts")
    return int(round(secs)), int(round(hr)) if hr else 0, int(round(w)) if w else 0


# ------------------------------------------------------------- geofence path

def fetch_streams(act_id, key):
    """Columns of the activity's stream table.

    CSV, not JSON: the JSON `latlng` stream returns a flat array of *latitudes*
    only — the longitudes are dropped. streams.csv emits proper lat and lng columns.
    """
    text = api_text(f"activity/{act_id}/streams.csv"
                    "?types=time,latlng,altitude,heartrate,watts", key)
    if not text:
        return None
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if len(rows) < 3:
        return None
    head = [h.strip() for h in rows[0]]
    out = {h: [] for h in head}
    for r in rows[1:]:
        if len(r) != len(head):
            continue
        for h, v in zip(head, r):
            try:
                out[h].append(float(v))
            except ValueError:
                out[h].append(None)
    return out


def passes(lat, lng, point, radius):
    """Index of the closest fix in each *distinct* visit to `point`.

    A ride can touch the segment start several times (repeats, or descending
    through it before climbing), so this returns one index per visit rather than
    the single global best.
    """
    out, inside, best_d, best_i = [], False, None, None
    for i in range(len(lat)):
        if lat[i] is None or lng[i] is None:
            continue
        d = haversine((lat[i], lng[i]), point)
        if d <= radius:
            if not inside or d < best_d:
                best_d, best_i = d, i
            inside = True
        elif inside:
            out.append(best_i)
            inside, best_d, best_i = False, None, None
    if inside:
        out.append(best_i)
    return out


def efforts_from_streams(act_id, key, target, radius):
    """Every clean passage of the segment in one activity: [(secs, hr, watts), ...].

    A candidate start/end pair only counts if the elapsed time is plausible *and*
    the altitude actually gained matches the segment — that is what rejects the
    descent-then-climb pairing, which would otherwise time the whole loop.
    """
    st = fetch_streams(act_id, key)
    if not st or "lat" not in st or "lng" not in st:
        return []
    lat, lng = st["lat"], st["lng"]
    tm = st.get("time") or list(range(len(lat)))
    alt = st.get("altitude") or []
    lo, hi = target.get("secs_range", [0, 10 ** 6])
    want_gain = target["gain_m"]

    cands = []
    for i0 in passes(lat, lng, target["start"], radius):
        for i1 in passes(lat, lng, target["end"], radius):
            if i1 <= i0:
                continue
            secs = tm[i1] - tm[i0]
            if not (lo <= secs <= hi):
                continue
            if alt and alt[i0] is not None and alt[i1] is not None:
                if abs((alt[i1] - alt[i0]) - want_gain) > 0.3 * want_gain:
                    continue
            cands.append((i0, i1, int(round(secs))))

    # shortest first, then keep only non-overlapping passages (a repeat is real,
    # a longer pair spanning the same climb is the same effort measured sloppily)
    cands.sort(key=lambda c: c[2])
    kept = []
    for i0, i1, secs in cands:
        if all(i1 <= k0 or i0 >= k1 for k0, k1, _ in kept):
            kept.append((i0, i1, secs))
    kept.sort()

    def mean(series, i0, i1):
        if not series:
            return 0
        vals = [v for v in series[i0:i1 + 1] if isinstance(v, (int, float))]
        return int(round(sum(vals) / len(vals))) if vals else 0

    return [(secs, mean(st.get("heartrate"), i0, i1), mean(st.get("watts"), i0, i1))
            for i0, i1, secs in kept]


# ------------------------------------------------------------- row assembly

def build_row(d, secs, hr, watts, target):
    """Shape an effort into the row layout the target array uses."""
    dist_km = target["dist_km"]
    gain_m = target["gain_m"]
    vam = int(round(gain_m * 3600 / secs))
    if target["layout"] == "bike":
        speed = round(dist_km * 3600 / secs, 1)
        return [d.year, d.month, d.day, secs, hr, watts, vam, speed]
    pace = int(round(secs / dist_km))
    return [d.year, d.month, d.day, secs, hr, vam, pace]


def is_duplicate(row, existing, tol=3):
    d = row_date(row)
    for e in existing:
        if row_date(e) == d and abs(e[3] - row[3]) <= tol:
            return True
    return False


# ------------------------------------------------------------------- main

def sync_target(text, target, activities, key, args):
    name = target["array"]
    rows = read_array(text, name)
    if rows is None:
        print(f"  {name}: not found in _data.js — skipped")
        return text, []
    last = row_date(rows[-1]) if rows else date(2000, 1, 1)
    print(f"\n  {name} ({target['sport']}): {len(rows)} rows, last {last.isoformat()}")

    wanted = [a for a in activities
              if (a.get("type") or "").lower() == target["sport"].lower()]
    print(f"    {len(wanted)} {target['sport']} activities in range")

    new = []
    for a in wanted:
        aid = a.get("id")
        ad = a.get("start_date_local", "")[:10]
        if not aid or not ad:
            continue
        d = datetime.strptime(ad, "%Y-%m-%d").date()

        got, how = [], ""
        efforts = fetch_segment_efforts(aid, key, probe=args.probe)
        if efforts:
            for e in efforts:
                if match_segment(e, target):
                    one = effort_from_segment(e)
                    if one:
                        got.append(one)
                    how = "segment"
        if not got and not args.no_geofence:
            got = efforts_from_streams(aid, key, target, args.radius)
            how = "gps"
        if not got:
            continue

        for secs, hr, watts in got:
            row = build_row(d, secs, hr, watts, target)
            if is_duplicate(row, rows + new):
                print(f"    = {ad}  {secs // 60}:{secs % 60:02d}  già presente")
                continue
            new.append(row)
            print(f"    + {ad}  {secs // 60}:{secs % 60:02d}  hr={hr or '—'}  "
                  f"w={watts or '—'}  [{how}]")

    if not new:
        print("    no new efforts")
        return text, []
    merged = sorted(rows + new, key=lambda r: (r[0], r[1], r[2]))
    return write_array(text, name, merged), new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="JSON config (see gazzaniga-orezzo.json)")
    ap.add_argument("--api-key")
    ap.add_argument("--since", help="YYYY-MM-DD; default = day after the last row")
    ap.add_argument("--until", help="YYYY-MM-DD; default = today")
    ap.add_argument("--radius", type=float, default=35.0,
                    help="geofence radius in metres (default 35)")
    ap.add_argument("--no-geofence", action="store_true",
                    help="only accept real segment efforts, never GPS timing")
    ap.add_argument("--probe", action="store_true",
                    help="print what the segment endpoints return, then continue")
    ap.add_argument("--dry-run", action="store_true", help="don't write _data.js")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    key = get_api_key(args.api_key)
    data_path = cfg["data_file"]
    if not os.path.isabs(data_path):
        data_path = os.path.normpath(os.path.join(os.path.dirname(args.config), data_path))
    with open(data_path, encoding="utf-8") as f:
        text = f.read()

    # widest window across all targets
    starts = []
    for t in cfg["targets"]:
        rows = read_array(text, t["array"]) or []
        starts.append(row_date(rows[-1]) + timedelta(days=1) if rows else date(2016, 1, 1))
    oldest = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else min(starts)
    newest = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else date.today()
    if oldest > newest:
        print(f"Nothing to do — already synced through {newest.isoformat()}.")
        return

    print(f"Intervals.icu athlete {cfg['athlete_id']}: "
          f"{oldest.isoformat()} → {newest.isoformat()}")
    acts = api(f"athlete/{quote(cfg['athlete_id'])}/activities"
               f"?oldest={oldest.isoformat()}&newest={newest.isoformat()}", key)
    if acts is None:
        sys.exit("Could not list activities — check the API key and athlete id.")
    print(f"  {len(acts)} activities")

    total = []
    for t in cfg["targets"]:
        text, new = sync_target(text, t, acts, key, args)
        total += new

    if not total:
        print("\nNothing new.")
        return
    if args.dry_run:
        print(f"\n--dry-run: {len(total)} new rows NOT written.")
        return
    shutil.copyfile(data_path, data_path + ".bak")
    with open(data_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nWrote {len(total)} new rows -> {data_path}  (backup: _data.js.bak)")

    # the same climb is served from two places (GitHub Pages + Cloudflare) — keep them level
    for mirror in cfg.get("mirrors", []):
        mp = mirror if os.path.isabs(mirror) else os.path.normpath(
            os.path.join(os.path.dirname(args.config), mirror))
        if os.path.exists(os.path.dirname(mp)):
            shutil.copyfile(data_path, mp)
            print(f"  mirrored -> {mp}")
        else:
            print(f"  ! mirror target missing, skipped: {mp}")


if __name__ == "__main__":
    main()
