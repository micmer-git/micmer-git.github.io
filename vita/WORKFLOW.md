# /vita operating memory

This file is the durable handoff for every agent working on `/vita`.

## Sources and cadence

- Intervals.icu supplies activities and wellness (sleep, HRV, resting HR, steps,
  weight, CTL/ATL). `.github/workflows/weekly-vita.yml` refreshes the dashboard
  hourly; the historic filename is retained to avoid breaking workflow links.
- **Intervals is not complete, and 2022 is the proof.** Compared against a Strava
  export it is missing 709 activities — including all 394 of 2022, a year that showed
  in the page as a twelve-month "nessun dato" band with CTL decaying to zero, which
  reads exactly like a year off. It was not. `tools/strava_backfill.py` diffs an export
  against the current pull and writes the missing activities to
  `tools/food/data/activities_backfill.csv`, which `build_vita.py` merges back in
  before recomputing load and CTL/ATL. It lives in its own file because
  `--sync-source` rewrites `activities.csv` every hour and would silently eat it.
  Rerun it by hand when a fresh export arrives; it is not part of the hourly job.
- That backfilled load is **estimated, never measured**. Strava does not export
  Intervals' training load, so it is fitted on the ~2.169 activities present in both
  sources: TRIMP (duration × exponential of heart rate), median absolute error 7,1 %
  running, 12,3 % swimming, 21,2 % cycling. Coefficients and provenance land in
  `activities_backfill.json`. The page marks these spans "carico ricostruito" (distinct
  from "nessun dato") and labels their TSS "stim." in the day popup. Matching between
  the two platforms keys on **distance**, not name or sport: Michele renames rides on
  Strava and Intervals sometimes reclassifies the sport, but the metres agree.
- Sleep, HRV, resting HR and steps genuinely start 2025-01-21 — that is the watch
  arriving, not a sync gap. Strava exports contain no sleep data of any kind, so
  earlier sleep can only come from Garmin Connect / Google Fit / Apple Health. Do not
  go looking for it in Strava again.
- The hourly order is strict: `build_vita.py --sync-source` refreshes the raw cache
  and `tools/food/data/activities.csv`; `build_food.py` recalculates nutrition and
  carbohydrate targets from that current load; `build_vita.py --offline` composes
  the final page; `check_vita.cjs` verifies it. Do not move food before source sync.
- `tools/food/data/food_log.csv` is the food source of truth for days Michele has
  narrated. Generated public aggregates live under `vita/cibo/data/`.
- **Cronometer outranks all of it.** `tools/food/data/cronometer/` holds an export
  (`dailysummary.csv` + `servings.csv`) covering 265 days actually weighed and logged,
  2024-06-04 → 2026-08-06, with ~60 nutrients per day. `tools/food/cronometer.py` turns
  it into `data/derived/cronometer_days.json`, and `build_nutrition_series.py` uses it
  to *replace* the reconstruction wherever it exists. This is a correction, not a
  refinement: on the 74 comparable days the reconstruction ran 471 kcal, 37 g protein,
  106 g carbohydrate, 13 g fibre and 498 mg sodium below the truth — biased low, not
  noisy. The observed share of the whole series went from 41 % to 49 %, and coverage
  starts 33 days earlier.
- The full/partial rule matters and must not be flattened. Cronometer's own `Completed`
  column is `false` on all 2.175 rows and is worthless. A day counts as **full** at
  ≥3 meal groups and ≥1.500 kcal (101 days) and replaces the day outright, becoming
  100 % observed. The other 164 are **partial** — often a single logged meal — and
  replace only the reconstruction slots they cover (`SLOT_OF` in `cronometer.py`),
  leaving the rest reconstructed. Taken as whole days they would erase 1.618 median
  kcal of real dinners. To refresh: drop new exports in that folder and rerun.
- Food statements may arrive in other Codex/ChatGPT tasks or in the private
  `micmer-git/agents` day-by-day diary. Reconcile those into `food_log.csv` before
  rebuilding, keep their original provenance, and never convert a planned meal
  ("stasera") into an observed one until the user confirms eating it.
- Never publish API keys or raw private health exports.
- The clickable 14-day food averages are a provenance-aware view: every metric
  shows its mean against the target/limit from `tools/food/profile.json`, while
  `days.json._14foods` groups equal food IDs across the latest 14 days. Keep grams,
  millilitres and units distinct; show total quantity and eating occasions, and
  always separate observed from reconstructed intake.

## Receipt estimates

When Michele attaches a receipt:

1. Extract product, purchased quantity, purchase date, and confidence.
2. For ordinary foods, estimate that 70% of the purchased edible amount is eaten
   across the following three days. Distribute portions plausibly and
   deterministically from receipt date + product name so rebuilds do not move meals.
3. Do not apply that rule blindly to pantry or multi-use products (for example
   honey, jam, oils, condiments, bulk staples) or anything whose likely consumption
   window is clearly longer. Bread and other short-lived staples require a specific
   consumption-window estimate based on quantity rather than an arbitrary random day.
4. Every derived row must carry provenance `receipt_estimate`, confidence, receipt
   identifier, and the assumption used. It must never appear as observed food.
5. Avoid double counting when a meal/photo/log already covers the same food and day.

The same rule applies to cycling fuel: an explicit note containing the observed
panini in bici suppresses the automatic hourly bread/jam/PB reconstruction for that
day. An ordinary bread-and-jam snack at home does not suppress it.

## Review policy

Twice-daily reviews compare the latest three days with the preceding 14-day
baseline and consider training load, upcoming/recent sessions, sleep, HRV, resting
HR, energy, carbohydrates, protein, fibre, micronutrient coverage, hydration/sodium,
and data confidence. Output one concise summary and one realistic next action.
It is decision support, not diagnosis or medical treatment.

## Exploratory relationships

- The free comparator in the Incroci section uses raw daily values, never smoothed
  lines. It reports the Pearson `r`, sample size and `R²`, with either same-day
  alignment or X today against Y tomorrow.
- Correlation is not causation. Treat food relationships as especially tentative:
  most nutrition days are reconstructed, and correlations between a nutrient and
  an index built from that nutrient merely reveal model wiring.
- Always surface provenance/observed share beside a nutrition inference. Prefer
  repeated effects, sensible lags and adequate overlap over the largest absolute
  `r` found by searching many pairs.
