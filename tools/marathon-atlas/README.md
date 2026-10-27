# Marathon Atlas source
Recovered from the existing local Marathon Atlas project; published site: `/marathons/`.

Run `npm ci`, `npm test`, then `npm run build`. The prebuild copies the canonical sanitized snapshot from `../../marathons/data/races.json`; it never reads private provider caches or rewrites race context. Copy `dist/index.html` and `dist/assets/` into `../../marathons/` for publication. Preserve the canonical race data.

`node qa.mjs` checks the preview at port 5194 (or QA_URL) with Edge at 390 and 1440 px. Screenshots are local artifacts.

Charts show non-overlapping 5 km means, with a final 40–42.195 km segment. Pace is elapsed seconds divided by recorded distance; HR integrates interpolated samples weighted by elapsed time. Missing endpoints, missing HR and recording gaps over 1 km remain unavailable. Each panel's Y range follows its plotted means, with padding. Numeric labels belong only to the selected race, directly beside its mean segments; no arbitrary Y ticks. Ghost retains trailing 5 km comparisons.

Venice 2026 remains recorded elapsed (2:47:23), not a verified official result; pre-race context is unavailable in the supplied snapshot.
