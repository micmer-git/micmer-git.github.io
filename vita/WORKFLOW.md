# /vita operating memory

This file is the durable handoff for every agent working on `/vita`.

## Sources and cadence

- Intervals.icu supplies activities and wellness (sleep, HRV, resting HR, steps,
  weight, CTL/ATL). `.github/workflows/weekly-vita.yml` refreshes the dashboard
  hourly; the historic filename is retained to avoid breaking workflow links.
- `tools/food/data/food_log.csv` is the food source of truth. Generated public
  aggregates live under `vita/cibo/data/`.
- Never publish API keys or raw private health exports.

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

## Review policy

Twice-daily reviews compare the latest three days with the preceding 14-day
baseline and consider training load, upcoming/recent sessions, sleep, HRV, resting
HR, energy, carbohydrates, protein, fibre, micronutrient coverage, hydration/sodium,
and data confidence. Output one concise summary and one realistic next action.
It is decision support, not diagnosis or medical treatment.
