# 2026-10-27 — context and effort comparison

Base: 651f8be. Existing paper/ink identity, race rail, shared distance control and Ghost preserved.

Race detail: answer how the race developed and what preceded it. Training bars supply the missing context; solid pace and dashed HR share distance and separate named axes. Primary action: select race/scrub. Secondary: shared/focused scales and faint recording toggle. Risk: dual-axis crossings; explained in the chart note.

Comparison: answer how efforts differ at the same distance or HR. Primary action: Pace / BPM / Pace × BPM, then select a race. Selected means stay foreground; other races and raw samples remain restrained. Scale defaults to common bounds so selection cannot visually exaggerate improvements. Scatter displays a descriptive relationship and per-bin m/beat, not a readiness/fitness verdict.

Verification: mathematical tests cover weighted bins, gaps, partial finish, readable axes and metres/beat. Python test covers exact window, duplicate runs, race-day exclusion and missing wellness. JSON comparison verifies original eight races unchanged and Venice changed only in context. Edge at 320/390/1440px: no horizontal overflow, no runtime errors; volume bars, independent axes, scale toggles, recording visibility, BPM values, scatter keyboard selection, distance endpoints, Ghost and missing-stream fallback verified. Screenshots for context, race effort, focus, pace, BPM and relationship inspected. npm audit: zero known vulnerabilities in Marathon Atlas.

## Checkpoint page follow-up

Added #splits: compare nine efforts at 10K / HM / 30K / 35K. Desktop table exposes four checkpoints at once; phone shows the selected checkpoint at readable width. Primary action is ranking by a checkpoint, secondary is highlighting a race. Time, approximate steps and gap-to-best share each cell. Method stays collapsed; approximate steps and recorded GPS times are labeled at entry.

Six math tests pass including cadence integration, partial boundaries, missing channels and zeros. All 36 times/counts checked in Edge at 320, 390 and 1440px; four rankings, race selection shared with detail, direct hash/reload/Back pass. Screenshots inspected. Existing dual-axis, context, comparison and Ghost browser suite passed. No race records changed.
