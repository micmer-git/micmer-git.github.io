# tools/

Eight scripts. The sync/build ones need nothing beyond the Python standard
library; the three that make images (`build_top20_gif.py`, `build_top20_reel.py`,
`basemap.py`) want Pillow. Every one takes `--dry-run` and backs up what it
overwrites to `*.bak`.

```
python tools/sync_intervals.py --config tools/gazzaniga-orezzo.json   # new efforts -> _data.js
python tools/sync_sogni.py                                            # new weeks   -> data.json + load.json
python tools/sync_diario.py                                           # refresh the monthly chapter numbers
python tools/build_vita.py                                            # rebuild /vita from all of the above
python tools/build_top20.py                                           # rebuild /top-20 data from Intervals
python tools/build_top20_gif.py                                       # the twenty square cards
python tools/build_top20_reel.py                                      # the one reel, on a real map
python tools/gifweigh.py <file.gif>                                   # dove sono i byte
node   tools/check_top20_page.cjs                                     # smoke-test /top-20 without a browser
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

---

## build_top20.py

Builds `top-20/_data.js` — the twenty days of `/top-20`, each one animated on its
real GPS. The twenty stories, their five captions apiece, and their timing all
live in **`top-20.json`**; this script only resolves them against Intervals.icu.
Streams are cached under `tools/.cache_streams/` (gitignored), so re-running after
an editorial change costs no network at all. `--refetch` ignores the cache,
`--facts` prints the fact sheet and writes nothing.

**Every number in a caption was checked against the fact sheet before being
written**, and a few were wrong on the first pass — the animation is 9h28 not
"nove ore e mezza", Malaga was 2h39 not 2h40, and 6.182 m is one Mont Blanc and a
quarter, not "seven hundred metres above" one. Run `--facts` and re-read the
captions whenever the ids change.

Two decisions inside are load-bearing:

- **Douglas-Peucker, not even resampling.** Spacing points evenly along the
  distance starves the hairpins: at 260 points the Maratona dles Dolomites came
  out 23 % short of its real length and the Mortirolo looked like a gentle arc.
  Thinning at a 12 m tolerance holds the same route within 2 % on 989 points.
  The cost is that points are no longer evenly spaced, so anything animating them
  must walk the polyline **by arc length** — both the page and the GIF do.
- **The timeline is computed here, not in the two renderers.** Each leg gets a
  `t0`/`dt` and each story a `beat_at`, written into `_data.js`. `pace` picks the
  split: `"km"` (sqrt of the distance — right *inside* one day, or the Ironman's
  3,9 km swim would last seven hundredths of the animation) or `"chapters"`
  (equal share — right when the legs are *different days*). `beat_at` pins each
  caption to a fraction of the timeline. Both exist because the first version
  weighted legs in the page and in the GIF separately, and the clavicle's
  captions talked about the 17th of May while the dot ran the 29th of June.

**Swapping a story:** edit `top-20.json` — `legs` takes Intervals activity ids —
then re-run. Anything with no GPS stream is skipped with a warning rather than
silently dropped: Intervals has **no 2022 at all** and nothing before March 2015,
so days from those windows can be described but not animated.

## build_top20_gif.py

Rebuilds `top-20/top-20.gif` from the same `_data.js` the page reads, so the two
cannot drift apart. Needs Pillow. `--story <slug> --png` writes a six-frame
contact sheet to `tools/.gif_check.png` instead — the fast way to look at one
story.

Three things it gets right on purpose: the frame **follows the leg, not the
story** (the clavicle's four legs sit in two valleys eighty kilometres apart, and
one shared bounding box made every day a thumbnail in a corner); the map is drawn
into its own image and pasted, because otherwise a distant leg's faint trace runs
straight through the captions; and text is drawn in runs so emoji can go to Segoe
UI Emoji with `embedded_color=True` — the captions quote titles like 🩻 and ❤️‍🩹
where the emoji *is* the title. The GIF palette is quantized (RGB was 3 MB) and
sampled across **all twenty** stories: taking it from a single frame collapsed
the four accent colours onto the same olive grey.

## basemap.py + build_top20_reel.py

`top-20-reel.gif` is the one to post: twenty days in sequence, each day opening on
a full-screen narration card that fades in and away, then the path drawing on a
real map, with the camera pulling back to an orthographic globe between one day
and the next. The globe keeps a dot for everywhere already visited, so it is also
the progress bar. Two cuts come out of the same tool: the **full one, 6'21",
1.216 frames, 5,7 MB** at the defaults (380 px, 40 colours), and a **short one,
3'21", 3,5 MB** — `--only 1,8,9,13,15,17,18,19,20 --intro --size 420 --colors 44`
— which is the one that makes sense on LinkedIn.

**Every block of text holds for at least five seconds.** That single rule sets the
length: twenty cards plus twenty-five notes is 3'45" of held text before a single
route is drawn. It is affordable because holding a frame is free — but it is why
the full cut is six minutes, and why the short cut exists.

**The length does not come from the frames.** The first cut ran the twenty days in
42 seconds and was unreadable — a caption had a second and a half on screen. Five
times the frames would have been twenty-four megabytes, so the pacing comes from
the two things GIF gives away: **holding a frame is free**, and a full-screen page
of type costs one 5 kB frame however long it sits there.

**There are two clocks, and only one of them may be touched.** `--ms` (105 ms) is
the pace of the GPS drawing, which is the thing being watched; `--ms-move` (70 ms)
is everything that only connects — globe, zooms, dissolves, cards. When the reel
needed to be half as long without the routes drawing any faster, all of the cut
came out of the second clock and the holds: 3'26" to 2'12" with the drawing
untouched.

Three narrative devices are worth keeping straight:

- **The cards are prose**, written by hand per story in `card`. They used to be
  kicker + activity title + one line, which is three database fields stacked in a
  column and reads like one.
- **`notes` annotate the route while it draws.** Twenty-five of them, at least one
  per day. Without `zoom` the note simply appears in the margin with the camera
  held still, which changes only the rectangle the text occupies — that is why
  there can be many. With `zoom` the camera also dives onto the dot, which costs a
  scale change, so those are the eight moments worth it: the flat at km 136 of the
  Ironman bike, the stomach at km 15 of its marathon, the crash in the first
  hundred metres at Barcelona, the highest fix on the Stelvio, and the evening
  ride that simply stops ten kilometres from home. A note exists only where the
  data or that day's own description actually places the moment; anywhere else it
  would be invention.
- **Typography does the rest.** Pillow has no letterspacing, no rules and no
  italic switching, so `draw_tracked()`, `rule()` and `is_quote()` supply them: the
  dates are letterspaced small caps under a short accent rule, the leads are large
  serif with tight leading, and anything the archive actually said is set in
  italic, because it is that day's voice and not ours.
- **`mode: "race"`** draws every leg at once from a common start, each at the pace
  it actually held that year. It exists for the Maratona dles Dolomites, which is
  not a day but five: two short courses, one middle, two long. Giving each the
  same *fraction* of its own route made them all finish together, which is not a
  race; and because short, middle and long share the opening climbs, the last
  track drawn hid the other four until each got a couple of pixels of offset.

`basemap.py` supplies the map: CARTO Positron **no-labels** tiles stitched to a
bounding box and recoloured to the site's cream, plus the globe from Natural
Earth's 110 m land. Tiles cache in `tools/.cache_tiles/` and are fetched once.
**The credit line in the corner is a licence condition, not decoration** — CARTO
and OpenStreetMap both require attribution.

Places are named by hand, in `top-20.json` under each leg's `places`
(`from`/`to`/`top`): the basemap ships without labels, so these are the only place
names on it. `top` is placed at the highest GPS fix of that leg, which is the pass
the day was about — Passo Gavia, lo Stelvio, il Col de l'Iseran, il Manghen. Only
points the coordinates identify beyond doubt are named; a wrongly named pass would
be the most visible mistake in the whole thing.

**Everything about this file's size was measured, not guessed, and three of the
four guesses were wrong.** For the record, since the temptation to "improve" it
will recur:

- *The labels are the expensive part.* No: dropping them saved 4 %.
- *Write only the pixels that changed.* Already true — 0,3 % of pixels differ
  between consecutive drawing frames, and Pillow's `optimize` already crops to
  that rectangle. The explicit transparency pass in `punch_holes` changed nothing
  measurable; it is kept because it is correct and costs one palette slot.
- *A smooth downscale is fine for the flight frames.* Nearest is better and
  invisible at that speed, but it bought only 2 %.
- *Only the count of camera moves matters.* Half-right: what matters is how many
  frames contain **the basemap at a scale it was not at in the previous frame**.
  A globe frame and a text card cost 5 kB; one of those costs 40. That measurement
  is why the gradual part of every flight is the globe growing from a dot and
  rotating, while the map itself enters over three frames — and why the pull-out
  and the dissolve to paper were merged into one move instead of two.
- What actually mattered: **the camera must hold still while a path draws**
  (5,8 MB → 2,2 MB on a three-story test), and **cross-dissolving a street map
  into a globe is unaffordable** — scaling the map back onto the cream page
  instead took that test to 1,2 MB. `gifweigh.py` walks the GIF's blocks and
  prints what every frame cost, which is how each of these was settled. Use it
  rather than reasoning: the current reel is a 2,9 kB median with 101 frames over
  10 kB carrying 45 % of the file.

One more trap, this one visual: median-cut spends the palette on whatever covers
the most pixels, which is the basemap, so a two-pixel-wide track gets merged into
the nearest grey — the Malaga marathon came out **drawn in grey instead of green**,
and so did its dot on the globe. `fixed_palette()` reserves the four accents, the
inks and the paper before median-cut is allowed to spend the rest. For the same
reason the reel writes sports as words and strips emoji from the data bar: a
twenty-pixel emoji at 72 colours is a dark smudge.

## gifweigh.py

Prints the encoded size of every frame in a GIF, by walking the block structure.
Exists because guessing what makes an animation heavy has a poor record here —
see the list above. `--runs` groups consecutive frames so a cut's phases show up
as blocks.

## check_top20_page.cjs

There is no browser on this machine, so `/top-20`'s own script is extracted from
`index.html` and run against a stub DOM with a recording canvas. It drives all
twenty animations to completion and fails on an exception, a non-finite
coordinate, a missing caption, or `undefined` reaching the markup. Run it after
touching the page's script — it catches what a syntax check cannot.
