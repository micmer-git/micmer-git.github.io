# Automatic commute updates

The existing GitHub Action `.github/workflows/weekly-vita.yml` (Hourly Vita sync, cron minute 17) now runs `tools/sync_bike_to_work.py` with the existing `INTERVALS_API_KEY` repository secret. GitHub can delay scheduled runs; `workflow_dispatch` also supports manual refresh.

## Data and matching

- `_data.js` is the reviewed historical archive and is not rewritten.
- `_auto.js` contains only new confirmed commute records, aggregate metrics and cropped/downsampled commute routes. `_merge-auto.js` merges these into both Story and Explore. New records replace previous versions by activity ID, not by title. Replaying the merge does not duplicate days, legs or totals.
- Home/work coordinates come from the existing CFG. `tools/bike-to-work.json` sets a 350m endpoint radius. Ride and Run activities must begin and finish in the home/work zones and contain an ordered crossing between them; legs must be 15–120 km and 20 minutes–6 hours. Round trips that merely pass work are rejected unless the GPS trace shows at least 30 minutes around work. This detects geographic commutes, not employment status.
- The model retains at most one outbound and one return leg per day, matching the original page contract. Additional matching activities contribute to the day's activity totals. Calorie totals and derived pizza equivalents are explicitly partial where the provider omits calories; no invented calorie estimate is added.
- Every run rechecks the last 14 days since the previous successful check, including edits/deletions in that window. Late imports older than the overlap need `--since YYYY-MM-DD`. The initial backfill scanned from 2026-07-13 to 2026-10-28.
- GPS data is fetched in memory; only matched commute routes sampled about every 40 seconds are published. Nonmatching activities and raw provider records are not saved. Endpoint prefilters reduce requests. Secrets are never logged or committed.
- Any API failure aborts before changing `_auto.js`. The last good data remains live. Other trackers continue, but the workflow finishes with a visible failure if the bike sync failed. A `checkedThrough` date in the page footer identifies the last successful check, not the date of the latest commute.

## Run / verify

Set `INTERVALS_API_KEY` privately, or use the existing ignored `tools/.intervals_key`, then:

```
python tools/sync_bike_to_work.py --dry-run
python tools/sync_bike_to_work.py
python tools/sync_bike_to_work.py --since 2026-07-13
python -m unittest discover -s tools/tests -p test_bike_to_work.py
node tools/check_bike_to_work.cjs
```

2026-10-28 initial verification: 8 new bike activities / days and 16 legs, total 153 bike days and 283 legs; 3 historical run days retained. Latest matching commute 2026-10-19. Seven matcher tests, real API replay with identical output hash, merge replay and browser Story/Explore at 390/1440px passed. The original 145 day objects were unchanged after this import. One new activity has no provider calorie value; page footer declares the calorie/food-equivalent totals partial.
