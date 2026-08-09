# tools/

Eleven scripts. The sync/build ones need nothing beyond the Python standard
library; the three that make images (`build_top20_gif.py`, `build_top20_reel.py`,
`basemap.py`) want Pillow, and `build_top20_video.py` additionally wants OpenCV,
which is the only thing here that can write a video. Every one takes `--dry-run`
and backs up what it overwrites to `*.bak`.

```
python tools/sync_intervals.py --config tools/gazzaniga-orezzo.json   # new efforts -> _data.js
python tools/sync_sogni.py                                            # new weeks   -> data.json + load.json
python tools/sync_diario.py                                           # refresh the monthly chapter numbers
python tools/build_cruscotto.py                                       # rebuild /vita/cruscotto from Intervals
node   tools/check_cruscotto.cjs                                      # smoke-test it, no browser needed
python tools/build_vita.py                                            # rebuild /vita from all of the above
python tools/build_top20.py                                           # rebuild /top-20 data from Intervals
python tools/build_top20_gif.py                                       # the twenty square cards
python tools/build_top20_reel.py                                      # the one reel, on a real map
python tools/build_top20_video.py --gif                               # v3: lo stesso racconto in video (+GIF)
python tools/gifweigh.py <file.gif>                                   # dove sono i byte
node   tools/check_top20_page.cjs                                     # smoke-test /top-20 without a browser
```

The weekly GitHub Action (`.github/workflows/weekly-vita.yml`) runs the three syncs
plus both builds on Monday morning, smoke-tests the cruscotto, and commits whatever
moved. It needs the repo secret
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

The hub also carries the band linking to `/vita/cruscotto`. That band lives in
`build_vita.py`, not in the generated HTML — editing `vita/index.html` by hand gets
it wiped by the next Monday run.

---

## build_cruscotto.py

Builds `/vita/cruscotto`: 22 compact charts over everything Intervals.icu holds.
Unlike the rest of `tools/`, it does **not** read a published page — it pulls the
whole wellness history and the whole activity list straight from the API, packs
them into one payload and inlines it. The page is a flat 320 KB file with no runtime
fetch and no key on the client. `--offline` rebuilds from `tools/.cruscotto_cache.json`
(gitignored), which makes iterating on the layout free.

**What the archive actually holds** — measured, and re-measured by every run, which
is the whole point of `--check`:

| field | from | n |
|---|---|---|
| ctl / atl | 2015-03-29 (every day) | 4.152 |
| training load | **2019-06-19** | 1.738 non-zero |
| sleep, sleepScore, hrv | **2025-01-21** | 548 |
| restingHR, steps | 2025-01-20 | 566 |
| vo2max | 2025-01-22 | 279 |
| weight / bodyFat | 2025-01-21 / 2025-06-27 | 65 / 53 |

Three traps live in that table, and every one of them produces a *plausible* chart
if ignored:

- **ctl/atl exist for days that have no training behind them.** Intervals fills the
  whole calendar, so "first non-null" says 2015 for a series that is flat zero until
  2019 — the 2015-2018 Strava imports carry no HR or power, hence no load. The load
  tiles start at the first day whose next 28 carry more than a token amount, which
  lands on 2019-06-19. Do not replace that with `first non-null`.
- **2021-10-18 → 2023-04-09 is a hole in the archive, not a break from training.**
  CTL decays smoothly across it and reads exactly like eighteen months of detraining.
  Every run of ≥45 days with no activity at all is detected and drawn as a shaded
  "nessun dato" band, and paths break over nulls rather than bridging them. Six such
  runs exist; the early ones are real gaps in the record too.
- **Sleep and HRV are 18 months of a page that otherwise spans eleven years.** Each
  tile resolves "sempre" against *its own* first day, so no tile can imply coverage
  it doesn't have, and its footer prints the window it actually drew.

**Colour.** Slots 1-4 of the dataviz reference palette, dark steps, validated as a
set against this page's card surface `#211d16` — not against the reference surface,
which is a different colour and would have passed things that fail here. Adjacent
worst CVD ΔE 8.4, normal-vision 19.3, all four ≥3:1 on the card. The one scatter
with more than one group carries **two** of them: four hues cannot clear the
all-pairs floor, and yellow beside orange is exactly the failing pair — which is why
"distanza contro dislivello" plots bike and run only. `check_cruscotto.cjs` asserts
the four hexes are still in the CSS, so a casual re-colour trips a test instead of
silently shipping.

**The y-axis gutter is computed, not fixed.** A five-figure tick ("50.000") needs
38px where a two-figure one needs 20; a fixed 34px either clips the big numbers or
wastes a tenth of a 320px tile. Both axes size themselves from the widest label at
~4.85px per mono glyph, and the check measures with the same constant.

---

## check_cruscotto.cjs

The cruscotto's smoke test, and the substitute for a pair of eyes: there is no
browser on this machine and jsdom does not install through the proxy, so the DOM
here is a fifty-line shim. It works because the page builds its nodes one at a time
and keeps a reference to each, instead of writing `innerHTML` and querying it back —
if the page ever returns to that, this stops running, and that is the correct signal.

It runs the page's own script and checks: every tile draws on **all four** time
windows (a renderer that throws is caught by the page but leaves its reason in
`data-err`, which is a failure here, not an empty tile); no NaN or Infinity in any
of ~36.000 SVG attributes; nothing drawn outside its viewBox; no y label clipped by
its gutter; no two x labels overlapping; the headline totals re-derived from the
payload independently; a data table under every tile and a legend on every
multi-series one; the palette still in the CSS; and the 2022 hole still declared.

`--verbose` prints what each tile *says* — its headline figure and its footer, with
window, n and correlation. That is how you read the page without opening it, and how
the captions get checked against the numbers instead of against expectations. It
earned its keep immediately: a caption asserting VO₂max rises with fitness went in
before the fit was run, and the actual r is **0.00**.

Every run appends to `tools/cruscotto_tests.md`, alongside what each build found.

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
the progress bar. Two cuts come out of the same tool: the **full one, 6'31",
1.336 frames, 6,0 MB** at the defaults (380 px, 40 colours), and a **short one,
3'25", 3,6 MB** — `--only 1,8,9,13,15,17,18,19,20 --intro --size 420 --colors 44`
— which is the one that makes sense on LinkedIn.

**Text is the cheap thing, so text is what moves.** Two places earn their frames
without touching the basemap, which is the only expensive thing in the file:

- **`story_card()`** — the day's opening page assembles itself instead of cutting
  in whole: date, then a rule opening from the centre, then the lead a line at a
  time, then the body, then the numbers **counting up from zero**. `--cardin` (12)
  buys that; twelve flat pages of type cost about what one map frame costs, and
  the measured price of the whole device across twenty days was 0,3 MB.
- **`side_column()`** — the day's line used to sit in the bottom bar. It now
  stands in a column beside the route and **writes itself at the pace of the dot**
  (`reveal = p / 0.7`, so the sentence lands just before the track does). Notes
  arrive under it, below a rule, and stay. The bottom bar keeps only the numbers.

**The column picks its own side, once per leg, from the whole route.**
`free_column()` scores both halves by how much of the *entire* track falls in
them and takes the emptier; `leg_column()` calls it once per leg, before drawing.
Both details are load-bearing. Scoring the drawn-so-far portion would let the
panel jump sides mid-leg, and pinning it right — which is what it did first —
put the sentence on top of the thing it was describing on half the days.

**A panel over a map covers something, and one of those somethings matters.** The
panel is painted after the place names, so on the Gavia day it swallowed *Passo
dello Stelvio*, which is the one name that day is about. `place_labels()` now
takes the reserved rect and, in order: flips the name to the other side of its dot
(the same move it already makes at the frame edge); or, if the dot itself is under
the column, lifts the name clear above the panel; or, failing both, **drops it**.
The third branch is the point — a name sliced in half by a panel edge reads as a
bug, a missing name reads as a map.

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

## build_top20_video.py

v3: the same twenty days as **video**, which is a different edit rather than the
same edit in a different container. The GIF montage descends from two facts —
holding a frame is free, changing the map's scale costs 40 kB — and neither is
true here, so the camera decisions invert. It is a separate file for that reason;
the drawing primitives are imported from `build_top20_reel.py`, not duplicated.

What changes, and why each was worth doing:

- **A text's hold is computed from its length** (`read_ms()`), 205 wpm plus a flat
  700 ms for the eye to find the line after a dissolve. In the GIF every block sat
  five seconds regardless, because holding cost nothing and distinguishing wasn't
  worth it; here a pause is thirty real frames a second. Two corrections that
  mattered more than the rate: **the date is excluded** (you recognise "5 giugno
  2016", you don't read it) and **the card's build-in is subtracted**, since the
  text is already legible while it assembles. Counting both is what left the
  Ironman card sitting 11,6 s. The 8 s ceiling was found the same way — past about
  27 words a page reads as a frozen video, so the text wants cutting, not holding.
- **Notes go full screen.** The map dissolves into the comment, the comment is
  read, and on the way back **the track resumes from exactly where it stopped**.
  That resumption is the whole trick: without it the day is a set of clips.
- **The camera follows the dot.** It opens wide, tightens within the first 18 % of
  the leg, follows, and releases over the last 12 %, so each route reads three
  times — shape, detail, finished shape.

**A bug this found in the GIF tool.** With a following camera the crop window can
run past the edge of the basemap mosaic, and Pillow fills out-of-bounds with
**black**, which on cream paper is unmissable. The existing clamp kept the camera
inside the *route's* bounding box — not the same thing, because that box carries a
margin. `map_frame()` now clamps to the mosaic as well.

**The codec question is settled; do not re-open it by guessing.** There is no
ffmpeg on this machine, so the encoder is whatever OpenCV's bundled one exposes,
and **everything modern silently fails soft rather than erroring**:

- `avc1` / `H264` / `X264`, and the `CAP_MSMF` backend too, all *open fine* and
  then produce a ~61 kB/frame intra-only stream, because `openh264-*.dll` is
  absent. Five times the size of the fallback, with no warning.
- `VP80` / `VP90` into `.webm` and `av01` also fall back, and measured on the same
  120 frames come out **larger** than the fallback (1,54 MB vs 1,04 MB).
- `mp4v` (MPEG-4 Part 2) is therefore the best available, and its text holds up.

The consequence is a **147 MB master for the full cut**, which is over GitHub's
100 MB per-file limit — `top-20/*.mp4` is gitignored, regenerate it and upload it
by hand. Real H.264 needs the OpenH264 DLL and would land near 25–35 MB.

**A GIF of this montage is not a conversion of the video file.** Transcoding the
mp4 would recompress compressed data and, worse, start from a constant 30 fps —
full price for every second nothing moves. The `Gif` writer intercepts the same
frames before the encoder and inverts the video's logic: holds collapse back to
one long-duration frame, motion decimates to `--gif-fps`, identical neighbours
merge. 17.977 video frames become 3.033 GIF frames over the identical 599 s.

**But the GIF cannot carry the following camera**, and this is the one number to
remember: on the same story, same montage, locking the camera took the GIF from
**6,5 MB to 1,4 MB** — 4,6×. Resolution and frame rate barely moved it. A camera
that follows rewrites the whole basemap every frame, which is exactly what this
format punishes and exactly why the reel's camera was locked to begin with. So
the GIF is rendered as its own pass at `--zdraw 1.0`, and the two deliverables are
deliberately different edits: the video has the zoom, the GIF has everything else
new. Full cut, measured: **9'59", 3.033 frames, 18,4 MB** at 440 px — heavier than
the reel's 6,0 MB because the montage is both longer and larger. If it needs to
fit LinkedIn's ~8 MB, cut days (`--only`), don't compress harder.

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
