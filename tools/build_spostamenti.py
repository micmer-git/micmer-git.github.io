#!/usr/bin/env python3
"""Build the privacy-safe /vita/spostamenti data set from Google Timeline.

The Takeout file is deliberately never copied into the repository.  The output
contains rounded city/airport coordinates, aggregate mileage and dated trips;
home, work and raw GPS paths remain local.

    pip install geonamescache
    python tools/build_spostamenti.py \
      --timeline /path/to/Timeline.json --airports /path/to/airports.csv

Airports data: https://ourairports.com/data/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import geonamescache

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vita" / "spostamenti" / "data" / "travel.json"
VITA = ROOT / "vita" / "index.html"

# Deliberately coarse origin: enough to separate travel from ordinary local days,
# but not a home coordinate (roughly the centre of the Bergamo area).
HOME = (45.70, 9.67)
# Public venue coordinate from OpenStreetMap/Nominatim, node 9502728424.
SORSI = (45.7572403, 9.7916211)
HOME_AIRPORTS = {"LIME", "LIMC", "LIML"}  # Bergamo, Malpensa, Linate
CO2_KG_PER_PKM = 0.14253
# UK Government 2026, average car with unknown fuel: direct emissions plus
# well-to-tank. Timeline identifies a passenger-vehicle movement, not its fuel.
CAR_CO2_KG_PER_KM = 0.16591 + 0.04399
CO2_SOURCE = (
    "https://www.gov.uk/government/publications/"
    "greenhouse-gas-reporting-conversion-factors-2026"
)
COUNTRY_IT = {
    "AT": "Austria", "AZ": "Azerbaigian", "BA": "Bosnia ed Erzegovina", "BE": "Belgio", "CH": "Svizzera",
    "CN": "Cina", "CU": "Cuba", "CZ": "Cechia", "DE": "Germania",
    "DK": "Danimarca", "EE": "Estonia", "ES": "Spagna", "FR": "Francia",
    "GB": "Regno Unito", "GR": "Grecia", "HK": "Hong Kong", "HU": "Ungheria",
    "IN": "India", "IT": "Italia", "JP": "Giappone", "KR": "Corea del Sud",
    "NP": "Nepal", "NL": "Paesi Bassi", "PT": "Portogallo", "RO": "Romania",
    "TH": "Thailandia", "US": "Stati Uniti",
}
AIRPORT_CITY = {
    "LIME": "Bergamo", "LIMC": "Milano", "LIML": "Milano",
    "LFPG": "Parigi", "LFPB": "Parigi", "LFOB": "Parigi",
    "EGLL": "Londra", "EDLV": "Düsseldorf", "EBCI": "Bruxelles",
    "GCLP": "Gran Canaria", "GCFV": "Fuerteventura", "EGPH": "Edimburgo",
    "LROP": "Bucarest", "LGAV": "Atene", "RJTT": "Tokyo",
    "RJBB": "Osaka", "RKSI": "Seul", "VHHH": "Hong Kong",
}
CITY_IT = {
    "Athens": "Atene", "Bucharest": "Bucarest", "Copenhagen": "Copenaghen",
    "Edinburgh": "Edimburgo", "Florence": "Firenze", "Frankfurt am Main": "Francoforte",
    "Gent": "Gand", "Lisbon": "Lisbona", "Naples": "Napoli",
    "Havana": "L'Avana", "New York City": "New York", "Padua": "Padova", "Sevilla": "Siviglia",
    "The Hague": "L'Aia", "Turin": "Torino", "Zürich": "Zurigo",
}
TRIP_FOCUS = {
    "2018-08-02": ("New York", "Stati Uniti", "US", 40.71, -74.01),
    "2021-10-01": ("Barcellona", "Spagna", "ES", 41.39, 2.17),
    "2023-08-11": ("L'Avana", "Cuba", "CU", 23.11, -82.37),
    "2023-10-26": ("Tokyo", "Giappone", "JP", 35.68, 139.76),
    "2024-04-11": ("New York", "Stati Uniti", "US", 40.71, -74.01),
}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def coord(value: str | None):
    nums = re.findall(r"-?\d+(?:\.\d+)?", value or "")
    return tuple(map(float, nums[:2])) if len(nums) >= 2 else None


def haversine(a, b, metres=False):
    radius = 6_371_000 if metres else 6_371
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    q = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(q))


def month_range(first: date, last: date):
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def slugify(value: str):
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


class Gazetteer:
    def __init__(self):
        gc = geonamescache.GeonamesCache()
        self.countries = gc.get_countries()
        self.cities = []
        for c in gc.get_cities().values():
            pop = int(c.get("population") or 0)
            if pop >= 15_000:
                self.cities.append((float(c["latitude"]), float(c["longitude"]), c, pop))

    def nearest(self, point):
        nearby = []
        for lat, lon, c, pop in self.cities:
            if abs(lat - point[0]) > 2.2 or abs(lon - point[1]) > 3.2:
                continue
            d = haversine(point, (lat, lon))
            if d <= 180:
                nearby.append((d, -pop, c, pop))
        if not nearby:
            nearby = [(haversine(point, (lat, lon)), -pop, c, pop)
                      for lat, lon, c, pop in self.cities]
        # Prefer a nearby real city over one of GeoNames' named neighbourhoods.
        # If no 200k+ city is within 45 km, keep the genuinely nearest smaller town.
        metropolitan = [x for x in nearby if x[0] <= 45 and x[3] >= 200_000]
        _, _, c, _ = min(metropolitan or nearby)
        cc = c.get("countrycode", "")
        country = COUNTRY_IT.get(cc) or self.countries.get(cc, {}).get("name", cc)
        return {"city": CITY_IT.get(c["name"], c["name"]), "country": country, "cc": cc,
                "lat": round(point[0], 2), "lon": round(point[1], 2)}


def load_airports(path: Path):
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["type"] not in {"large_airport", "medium_airport"}:
                continue
            if r["scheduled_service"] != "yes":
                continue
            rows.append({
                "id": r["ident"], "lat": float(r["latitude_deg"]),
                "lon": float(r["longitude_deg"]), "city": r["municipality"] or r["name"],
                "country": r["iso_country"], "name": r["name"],
            })
    return rows


def nearest_airport(point, airports):
    airport = min(airports, key=lambda a: haversine(point, (a["lat"], a["lon"])))
    return airport, haversine(point, (airport["lat"], airport["lon"]))


def airport_label(a, gazetteer):
    g = gazetteer.nearest((a["lat"], a["lon"]))
    return {
        "id": a["id"], "city": AIRPORT_CITY.get(a["id"], a["city"] or g["city"]),
        "country": COUNTRY_IT.get(a["country"], g["country"]), "cc": a["country"],
        "lat": round(a["lat"], 2), "lon": round(a["lon"], 2),
    }


def extract_flights(segments, airports, gazetteer):
    flights = []
    for s in segments:
        a = s.get("activity", {})
        if a.get("topCandidate", {}).get("type") != "FLYING":
            continue
        km = float(a.get("distanceMeters") or 0) / 1000
        p = coord(a.get("start", {}).get("latLng"))
        q = coord(a.get("end", {}).get("latLng"))
        if not p or not q or not 100 <= km <= 15_000:
            continue
        aa, da = nearest_airport(p, airports)
        bb, db = nearest_airport(q, airports)
        flights.append({
            "start": parse_dt(s["startTime"]), "end": parse_dt(s["endTime"]),
            "km": km, "a": airport_label(aa, gazetteer),
            "b": airport_label(bb, gazetteer), "da": da, "db": db,
        })
    flights.sort(key=lambda f: f["start"])
    # Timeline occasionally places the first point of a connecting leg hundreds
    # of kilometres away. Continuity with the previous airport is stronger evidence.
    for before, current in zip(flights, flights[1:]):
        gap = (current["start"] - before["end"]).total_seconds() / 3600
        if 0 <= gap <= 14 and current["a"]["id"] != before["b"]["id"]:
            if haversine((current["a"]["lat"], current["a"]["lon"]),
                         (before["b"]["lat"], before["b"]["lon"])) > 150:
                current["a"] = dict(before["b"])
    return flights


def visit_index(segments):
    visits, by_place = [], defaultdict(list)
    for s in segments:
        v = s.get("visit", {}).get("topCandidate", {})
        p = coord(v.get("placeLocation", {}).get("latLng"))
        if not p:
            continue
        item = {"start": parse_dt(s["startTime"]), "end": parse_dt(s["endTime"]),
                "point": p, "place": v.get("placeId") or ""}
        visits.append(item)
        if item["place"]:
            by_place[item["place"]].append(p)
    return visits, {k: v[0] for k, v in by_place.items()}


def trip_places(start, end, visits, gazetteer):
    durations = defaultdict(float)
    counts = Counter()
    points = {}
    for v in visits:
        if v["end"] < start or v["start"] > end:
            continue
        if haversine(HOME, v["point"]) < 90:
            continue
        g = gazetteer.nearest(v["point"])
        key = (g["city"], g["country"], g["cc"])
        durations[key] += max(5, (v["end"] - v["start"]).total_seconds() / 60)
        counts[key] += 1
        points[key] = g
    ranked = sorted(durations, key=lambda k: durations[k], reverse=True)
    return [{**points[k], "visits": counts[k], "minutes": round(durations[k])}
            for k in ranked[:8]]


def trip_record(start, end, distance, places, legs, fallback, kind="memory"):
    if not places:
        places = [fallback]
    focus = places[0]
    alias = TRIP_FOCUS.get(start.date().isoformat())
    if alias:
        city, country, cc, lat, lon = alias
        focus = {"city": city, "country": country, "cc": cc, "lat": lat, "lon": lon}
    clean_places = []
    seen_places = set()
    for p in [focus, *places]:
        key = (p["city"], p["country"])
        if key in seen_places:
            continue
        seen_places.add(key)
        clean_places.append({
            "city": p["city"], "country": p["country"], "cc": p["cc"],
            "lat": round(p["lat"], 2), "lon": round(p["lon"], 2),
            "visits": int(p.get("visits", 0)), "minutes": int(p.get("minutes", 0)),
        })
    places = clean_places
    km = sum(f["km"] for f in legs)
    co2 = km * CO2_KG_PER_PKM
    cities = [focus["city"]]
    for p in places:
        if p["city"] not in cities:
            cities.append(p["city"])
    routes = [{"a": [f["a"]["lon"], f["a"]["lat"]],
               "b": [f["b"]["lon"], f["b"]["lat"]]} for f in legs]
    if not routes:
        routes = [{"a": [9.67, 45.70], "b": [focus["lon"], focus["lat"]]}]
    return {
        "id": f"{start:%Y%m%d}-{slugify(focus['city'])}",
        "start": start.date().isoformat(), "end": end.date().isoformat(),
        "year": start.year, "city": focus["city"], "country": focus["country"],
        "cc": focus["cc"], "lat": focus["lat"], "lon": focus["lon"],
        "cities": cities, "places": places, "distanceFromHomeKm": round(distance),
        "flightKm": round(km), "co2Kg": round(co2),
        "mode": "volo" if legs else "terra", "routes": routes, "kind": kind,
    }


def memory_trips(segments, visits, places_by_id, flights, gazetteer):
    trips = []
    for s in segments:
        memory = s.get("timelineMemory", {}).get("trip")
        if not memory or float(memory.get("distanceFromOriginKms") or 0) < 120:
            continue
        start, end = parse_dt(s["startTime"]), parse_dt(s["endTime"])
        places = trip_places(start, end, visits, gazetteer)
        if not places:
            coords = [places_by_id.get(x.get("identifier", {}).get("placeId", ""))
                      for x in memory.get("destinations", [])]
            places = [gazetteer.nearest(p) for p in coords if p]
        if not places:
            # A memory may carry only an opaque Place ID that never appears in a
            # visit. Publishing a nearby home town as its destination would be a
            # confident-looking invention, so leave that memory out.
            continue
        legs = [f for f in flights if f["start"] <= end and f["end"] >= start]
        fallback = places[0]
        trips.append(trip_record(start, end, memory.get("distanceFromOriginKms") or 0,
                                 places, legs, fallback))
    return trips


def flight_groups(flights, visits, gazetteer, since_year=2025):
    groups, current = [], []
    for f in (x for x in flights if x["start"].year >= since_year):
        if current:
            gap = (f["start"] - current[-1]["end"]).days
            if gap > 45 or (f["a"]["id"] in HOME_AIRPORTS
                            and current[-1]["b"]["id"] not in HOME_AIRPORTS):
                groups.append(current); current = []
        current.append(f)
        if f["b"]["id"] in HOME_AIRPORTS:
            groups.append(current); current = []
    if current:
        groups.append(current)
    out = []
    for legs in groups:
        start, end = legs[0]["start"], legs[-1]["end"]
        places = trip_places(start, end + timedelta(days=2), visits, gazetteer)
        away = [f["b"] for f in legs if f["b"]["id"] not in HOME_AIRPORTS]
        fallback = max(away, key=lambda p: haversine((45.70, 9.67), (p["lat"], p["lon"])),
                       default=legs[-1]["b"])
        distance_point = places[0] if places else fallback
        distance = haversine((45.70, 9.67), (distance_point["lat"], distance_point["lon"]))
        out.append(trip_record(start, end, distance, places, legs, fallback, "flight"))
    return out


def validated_car(segments):
    total, accepted, rejected, years = 0.0, 0, 0, defaultdict(float)
    for s in segments:
        a = s.get("activity", {})
        if a.get("topCandidate", {}).get("type") != "IN_PASSENGER_VEHICLE":
            continue
        km = float(a.get("distanceMeters") or 0) / 1000
        hours = (parse_dt(s["endTime"]) - parse_dt(s["startTime"])).total_seconds() / 3600
        p, q = coord(a.get("start", {}).get("latLng")), coord(a.get("end", {}).get("latLng"))
        direct = haversine(p, q) if p and q else 0
        value = None
        if hours > 0 and .05 <= km <= 1500 and km / hours <= 180 and (direct < 1 or km >= direct * .7):
            value = km
        elif hours > 0 and direct >= .5 and direct / hours <= 180:
            value = direct * 1.2
        if value is None:
            rejected += 1
            continue
        accepted += 1; total += value; years[s["startTime"][:4]] += value
    return round(total), accepted, rejected, [
        {"year": int(y), "km": round(v), "co2Kg": round(v * CAR_CO2_KG_PER_KM)}
        for y, v in sorted(years.items())
    ]


def location_heatmap(trips):
    grouped = {}
    for trip in trips:  # newest first; the first id is the click target
        for place in trip["places"]:
            key = (place["city"], place["country"])
            item = grouped.setdefault(key, {
                "city": place["city"], "country": place["country"],
                "lat": place["lat"], "lon": place["lon"], "visits": 0,
                "tripIds": [],
            })
            item["visits"] += place.get("visits", 0)
            if trip["id"] not in item["tripIds"]:
                item["tripIds"].append(trip["id"])
    return [{**item, "trips": len(item["tripIds"]),
             "latestTripId": item["tripIds"][0]}
            for item in sorted(grouped.values(), key=lambda x: (-len(x["tripIds"]), x["city"]))]


def half_marathons(vita_path: Path):
    text = vita_path.read_text(encoding="utf-8")
    match = re.search(r"<script>\s*const D = (\{.*?\});\s*\n", text, re.S)
    if not match:
        raise RuntimeError("Cannot find the embedded Vita data")
    data = json.loads(match.group(1)); d0 = date.fromisoformat(data["d0"])
    counts, runs = Counter(), []
    for i, a in enumerate(data["acts"]):
        if a[1] != 1 or not 21_000 <= a[3] <= 60_000:
            continue
        when = d0 + timedelta(days=a[0]); counts[when.strftime("%Y-%m")] += 1
        runs.append({"date": when.isoformat(), "km": round(a[3] / 1000, 1),
                     "name": data.get("anames", [[""]])[i][0]})
    first = date.fromisoformat(runs[0]["date"]).replace(day=1) if runs else d0
    last = date.fromisoformat(runs[-1]["date"]) if runs else date.today()
    monthly = [{"month": m, "count": counts[m]} for m in month_range(first, last)]
    return runs, monthly


def special_place(segments):
    nearby = Counter()
    all_visits = []
    for s in segments:
        v = s.get("visit", {}).get("topCandidate", {})
        p = coord(v.get("placeLocation", {}).get("latLng"))
        if p and haversine(p, SORSI, metres=True) <= 25:
            nearby[v.get("placeId") or ""] += 1
            all_visits.append((s, v.get("placeId") or ""))
    place_id = nearby.most_common(1)[0][0] if nearby else ""
    dates = sorted({s["startTime"][:10] for s, pid in all_visits if pid == place_id})
    years = Counter(d[:4] for d in dates)
    return {"name": "Sorsi e Bocconi", "city": "Albino", "count": len(dates),
            "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
            "years": [{"year": int(y), "count": n} for y, n in sorted(years.items())]}


def update_vita_track(vita_path: Path, totals):
    text = vita_path.read_text(encoding="utf-8")
    match = re.search(r"(<script>\s*const D = )(\{.*?\})(;\s*\n)", text, re.S)
    if not match:
        raise RuntimeError("Cannot update Vita track")
    data = json.loads(match.group(2))
    track = {
        "key": "spostamenti", "title": "Spostamenti", "href": "spostamenti/",
        "eyebrow": "la geografia",
        "blurb": "Dodici anni di città, voli, strada e luoghi che ritornano — su un globo da scorrere.",
        "accent": "#8b7cf6", "last": date.today().isoformat(),
        "stats": [
            {"v": str(totals["trips"]), "l": "viaggi"},
            {"v": str(totals["countries"]), "l": "paesi esteri"},
            {"v": f"{totals['transportCo2T']:.1f}".replace(".", ",") + " t", "l": "CO₂e mobilità"},
        ],
    }
    data["tracks"] = [x for x in data.get("tracks", []) if x.get("key") != "spostamenti"] + [track]
    replacement = match.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + match.group(3)
    vita_path.write_text(text[:match.start()] + replacement + text[match.end():], encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True, type=Path)
    ap.add_argument("--airports", required=True, type=Path)
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--vita", type=Path, default=VITA)
    ap.add_argument("--manifest", type=Path,
                    default=OUT.parent / "source-manifest.json")
    args = ap.parse_args()

    raw = json.loads(args.timeline.read_text(encoding="utf-8"))
    segments = raw["semanticSegments"]
    gazetteer = Gazetteer(); airports = load_airports(args.airports)
    visits, places_by_id = visit_index(segments)
    flights = extract_flights(segments, airports, gazetteer)
    trips = memory_trips(segments, visits, places_by_id, flights, gazetteer)
    trips += flight_groups(flights, visits, gazetteer)
    # Remove overlapping duplicates and keep the richer memory record.
    unique = {}
    for t in sorted(trips, key=lambda x: (x["start"], x["kind"] != "memory")):
        unique.setdefault((t["start"], t["city"]), t)
    trips = sorted(unique.values(), key=lambda x: x["start"], reverse=True)

    car_km, car_ok, car_bad, car_years = validated_car(segments)
    runs, half_monthly = half_marathons(args.vita)
    sorsi = special_place(segments)
    countries = sorted({p["country"] for t in trips for p in t["places"] if p["cc"] != "IT"})
    cities = sorted({(p["city"], p["country"]) for t in trips for p in t["places"]})
    flight_km = round(sum(f["km"] for f in flights))
    flight_co2_t = round(flight_km * CO2_KG_PER_PKM / 1000, 2)
    car_co2_t = round(car_km * CAR_CO2_KG_PER_KM / 1000, 2)
    totals = {
        "trips": len(trips), "countries": len(countries), "cities": len(cities),
        "flightLegs": len(flights), "flightKm": flight_km,
        "co2T": flight_co2_t, "flightCo2T": flight_co2_t,
        "carCo2T": car_co2_t,
        "transportCo2T": round(flight_co2_t + car_co2_t, 2),
        "carKm": car_km, "halfMarathons": len(runs), "sorsi": sorsi["count"],
    }
    payload = {
        "meta": {"built": date.today().isoformat(),
                 "from": min(s["startTime"] for s in segments)[:10],
                 "to": max(s["endTime"] for s in segments)[:10],
                 "privacy": "GPS grezzo, casa e lavoro non sono pubblicati."},
        "totals": totals, "countries": countries, "trips": trips,
        "heatmap": location_heatmap(trips),
        "flightByYear": [{"year": int(y), "km": round(v)} for y, v in sorted(
            ((y, sum(f["km"] for f in flights if f["start"].year == y))
             for y in sorted({f["start"].year for f in flights})))],
        "carByYear": car_years,
        "halfMarathons": {"thresholdKm": 21.0, "runs": runs, "monthly": half_monthly},
        "specialPlaces": [sorsi],
        "method": {
            "co2KgPerPassengerKm": CO2_KG_PER_PKM, "co2Source": CO2_SOURCE,
            "co2Label": "UK Government 2026 · international average passenger · with RF",
            "carCo2KgPerKm": CAR_CO2_KG_PER_KM,
            "carCo2Label": "UK Government 2026 · average car, fuel unknown · direct + well-to-tank",
            "carAcceptedSegments": car_ok, "carRejectedSegments": car_bad,
            "airportsSource": "https://ourairports.com/data/",
            "mapSource": "https://github.com/topojson/world-atlas",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    digest = hashlib.sha256(args.timeline.read_bytes()).hexdigest()
    source_manifest = {
        "source": args.timeline.name, "sha256": digest,
        "bytes": args.timeline.stat().st_size, "semanticSegments": len(segments),
        "coverage": {"from": payload["meta"]["from"], "to": payload["meta"]["to"]},
        "publishedInstead": args.output.name,
        "omitted": ["raw GPS", "home", "work", "precise paths", "place IDs"],
        "reason": "The source export is intentionally kept local because this repository is public.",
    }
    args.manifest.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    update_vita_track(args.vita, totals)
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    print(f"wrote {args.output} ({args.output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
