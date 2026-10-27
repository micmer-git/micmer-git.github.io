# Marathon Atlas source

Published site: `/marathons/`. `npm ci`, `npm test`, `python tests/context_test.py`, then `npm run build`. Prebuild copies the canonical sanitized snapshot from `../../marathons/data/races.json`. Copy `dist/index.html` and `dist/assets/` into `../../marathons/`; keep the canonical data there.

`node qa.mjs` checks Edge at 390/1440px against port 5195 (or `QA_URL`). Local screenshots go to ignored `artifacts/`.

## Context refresh

Set `INTERVALS_KEY_FILE` (or `INTERVALS_API_KEY`) privately, then `python scripts/fetch-context.py i201415820`. This fetches activity and wellness data in memory and updates only that race's aggregated context. Training volume covers the exact preceding 56 days, excludes race day, deduplicates activity IDs, and includes only Run activities. Missing fields stay null. Raw provider records and credentials are never written to the repository.

Venice context was fetched 2026-10-27: 35 runs from 2026-08-30 through 2026-10-24; 80.3 km/week, peak 117.4 km. Weekly totals are rounded to 0.1 km; the average uses unrounded totals. Temperature is device-recorded, not weather. Weight is a scale record two days before the race. The race's 2:47:23 remains recorded elapsed, not a verified official result.

## Charts

- Non-overlapping 5 km means, final 40–42.195 km segment. Pace = elapsed seconds / distance; HR = time-weighted integral. Missing endpoints, HR or >1 km recording gaps remain unavailable.
- Race effort overlays pace (left, solid blue) and HR (right, dashed rust) with independent axes. Crossings have no numerical equality meaning.
- Overlay switches between pace, BPM and pace versus BPM. Both distance charts use shared global mean domains by default. Selection does not change them. Focus mode uses the selected race, explicitly allowing other traces to be clipped.
- Faint recordings sample distance at 250m and appear behind means; they may be clipped by the mean-based domains. Toggle available. The scatter shows selected-race faint raw points, not a fitted causal relationship.
- Scatter dots represent 5 km bins. Selected-race dots can be tapped or activated with Enter/Space. The readout reports metres per beat = 60000 / (sec/km × bpm), a descriptive ratio influenced by terrain, temperature and sensor quality, not a physiological fitness score.
- Ghost retains its recorded-time gap and trailing 5 km comparison.
