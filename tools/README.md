# tools/

Four scripts, no dependencies beyond the Python standard library. Every one takes
`--dry-run` and backs up what it overwrites to `*.bak`.

```
python tools/sync_intervals.py --config tools/gazzaniga-orezzo.json   # new efforts -> _data.js
python tools/sync_sogni.py                                            # new weeks   -> data.json + load.json
python tools/sync_diario.py                                           # refresh the monthly chapter numbers
python tools/build_vita.py                                            # rebuild /vita from all of the above
```

The weekly GitHub Action (`.github/workflows/weekly-vita.yml`) runs all four on
Monday morning and commits whatever moved. It needs the repo secret
**`INTERVALS_API_KEY`** (Intervals.icu ▸ Settings ▸ Developer ▸ API key). Locally the
scripts read `INTERVALS_API_KEY`, `--api-key`, or `tools/.intervals_key` (gitignored).

**Every window was pinned empirically, not assumed.** Before trusting a formula, each
script's aggregation was replayed against already-published values until it matched
to the digit — the Mon–Sun activity week and the M+1…M+7 sleep week in sogni, the
calendar-month chapter in diario (38 of 39 reproduce exactly), the segment distance
and gain in the climb. If a page's numbers ever stop reproducing, that is a real
signal, not a rounding artefact.

**Cloudflare note:** intervals.icu sits behind Cloudflare, which answers the default
`python-urllib` User-Agent with `error code: 1010` before the request reaches the
API. All requests go through `sync_intervals.api()`, which sets an ordinary UA — reuse
it rather than calling `urlopen` directly.

---

## sync_intervals.py

Replaces the old "select the Strava leaderboard, copy, paste, run `parse_efforts.py`"
step. Reads the last date already in `gazzaniga-orezzo/_data.js`, asks Intervals.icu
for activities since then, and appends the new efforts.

**How an effort gets timed.** Intervals.icu has *no* segment endpoint —
`/activity/{id}/segment-efforts`, `/activity/{id}/segments` and
`/athlete/{id}/segments` all 404 on the router, while `/activity/{id}` and
`/activity/{id}/streams.json` 401 (i.e. they exist and just want auth). So the
script downloads the activity's GPS stream and times the passage between the
segment's start and end coordinates. It still probes for a segment endpoint on the
first activity of each run — if Intervals ever ships one, this starts using it and
says `[segment]` instead of `[gps]` in the log.

That means **the times are ours, not Strava's**: Strava interpolates across the
exact start/end lines, we snap to the nearest GPS fix. Expect a second or two of
difference on a ~14-minute effort. If you want Strava's own numbers, that needs the
Strava API (`GET /segments/{id}/all_efforts`) and an OAuth token with
`activity:read_all` — a different tool.

**Config** (`gazzaniga-orezzo.json`) tracks two segments in one file: `RAW` (the
3.36 km bike segment) and `RUN` (the 4.29 km run segment). `dist_km` / `gain_m` are
each *segment's own* numbers, not the 4.25 km full climb the page presents —
`index.html` rescales `RAW` by 4.24/3.36 itself. Both were recovered from the
existing rows (`vam × secs / 3600` and `speed × secs / 3600` are constant across all
407 + 200 efforts) and cross-checked against `ROUTE`. `secs_range` throws out
anything that can't be a real effort.

Useful flags: `--dry-run` (find and print, write nothing), `--probe` (dump what the
segment endpoints return), `--since YYYY-MM-DD`, `--radius` (geofence metres,
default 35), `--no-geofence` (accept only real segment efforts — currently finds
nothing, kept for when the API grows one).

`_data.js` is backed up to `_data.js.bak` before every write, and mirrored to the
Cloudflare copy listed under `mirrors` when that path exists.

**Adding another climb:** copy the config, point `data_file` at the new `_data.js`,
and fill in `start` / `end` / `dist_km` / `gain_m` for its segment.

---

## sync_sogni.py

Appends completed weeks to `sogni-di-un-unno/data.json` (sleep) and `load.json`
(training), then rewrites the figures the page hardcodes — week counts, date span,
mean score — so the hero can't claim "260 settimane" over 271 weeks of data. Each
substitution must match exactly once; if the markup moves, it exits loudly rather
than leaving a stale number on screen.

Two things it will not do. **Bedtime and wake time cannot be refreshed** — the
Intervals.icu wellness schema has no sleep start/end field, only `sleepSecs`,
`sleepScore` and `sleepQuality`. New weeks carry `bed`/`wake` as null and
`bedStr`/`wakeStr` as "—"; the page already guards on `d.bed !== null`, so the
bedtime charts simply stop at the last week with real values. Refilling them needs
whatever exported the originals (Garmin). And the stat-bar's **`±10.5 dev.std` is
left alone**: the weekly scores give 6.8, so that figure is computed over some other
population and overwriting it would quietly change its meaning.

---

## sync_diario.py

Recomputes every monthly chapter's stat strip and the cover totals. It touches
numbers only. Two things stay editorial and are *reported* at the end of each run
instead of being invented:

- a month still marked "— in corso" once it has ended;
- a month with activities and no chapter at all.

The `W104–W107` week labels are also left alone — no epoch and weekday reproduces
more than 15 of the 25 published ranges, so any generated range would be a guess.

---

## build_vita.py

Regenerates `/vita`, the hub over every tracker, reading each tracker's *own*
published data so the hub can't drift from the pages it links to:

| source | what comes out |
|---|---|
| `gazzaniga-orezzo/_data.js` | ascents, Everests, PR, ascents-per-month |
| `diario-di-un-unno/index.html` | cover stats + km per monthly chapter |
| `sogni-di-un-unno/data.json` | weeks tracked, mean sleep, weekly hours |
| `git log` | the "Cronaca" changelog, newest 5 per tracker |

Everything is inlined into `vita/index.html` — one self-contained file, no runtime
fetch. `--check` reports what it found and writes nothing.

Each card carries one single-series plot (bars for counts, a line for weekly hours),
so the card title names the series and no legend is needed. The three accents are
categorical slots 1–3 of the dataviz reference palette stepped for a dark surface;
that trio passes lightness, chroma, CVD, normal-vision and contrast on all pairs.
Colour never carries identity on its own — every chip and card sits next to the
tracker's name.

**Adding a tracker:** write a `load_*()` returning the same dict shape, add it to
the list in `main()` and to `TRACKED` (for the changelog), and give it an accent —
re-validate the set if you go past three.
