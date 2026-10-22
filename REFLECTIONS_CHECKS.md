
## 2026-10-22 · local extraction
- Command: `python tools/build_reflections.py <local ZIP>`
- DOCX: 12; dated entries: 232; displayed months: 39; suppressed months: 51; duplicates removed: 0.
- Verdict: only fixed topic labels/counts and monthly lexical tone exported; no names, quotations, raw text, document names or entry dates. PDF not processed (possible duplicate). Dates inferred from single-year filenames only when explicit headings agree; ambiguous sections excluded. Historical prose and sparse headings limit accuracy.

## 2026-10-22 · local extraction
- Command: `python tools/build_reflections.py <local ZIP>`
- DOCX: 12; dated entries: 232; displayed months: 39; suppressed months: 51; duplicates removed: 0.
- Verdict: only fixed topic labels/counts and monthly lexical tone exported; no names, quotations, raw text, document names or entry dates. PDF not processed (possible duplicate). Dates inferred from single-year filenames only when explicit headings agree; ambiguous sections excluded. Historical prose and sparse headings limit accuracy.

## 2026-10-22 · structural verification
- Python compilation and Node JavaScript syntax: PASS.
- Export schema, >=3-section privacy floor, tone coverage gate, 39 displayed months, generator navigation: PASS.
- Chronology and semantic sentiment accuracy remain unverified; no correlation reported.

## 2026-10-22 · browser verification
- Local browser at `/vita/come-sto/`: loaded 39 months / 157 included sections.
- Year filter 2025: 4 months / 17 sections; chart bars updated. PASS.
- Layout visually checked at 550 px viewport; no horizontal clipping in the visible section.

## 2026-10-22 · delivery state
- Git: code and sanitized aggregates backed up on `codex/vita-come-sto`.
- Published site: unchanged; draft review before production.
- Index: navigation updated in generated page and generator.
- Memory: `vita/WORKFLOW.md` updated; handoff captured.
- Initial diff whitespace check found a trailing blank line in the new handoff; removed before final check.

## 2026-10-22 · contextual model probes
- Local Qwen3.5-9B, JSON schema and allowlist validation. Synthetic negative negation phrase: valence -0.8, Recupero, riposo/fatica. Synthetic serene nature phrase: valence +0.8, nature/cammino concepts. PASS for polarity and no free-form output.
- Initial probe assigned unsupported topics; prompt revised with explicit definitions/example before corpus run. Labels remain model interpretations; no claim of calibrated accuracy.

## 2026-10-22 · chronology and layout corrections
- Inventory after adding English Notion timestamps: 279 sections, 298 passages, 216455 retained words; 2023 recovered (20 sections), 2022 22 sections. One 2019 DOCX has no text and no embedded document payload.
- Python compilation and Node syntax: PASS. Private preview with 105 cached real annotations rendered the complete chart layout; never published the partial preview. Desktop visual layout checked. Annual chart SVG changed to group role so focusable year readouts are available to assistive technology.

## 2026-10-22 · PDF supplement audit
- Read all 505 PDF pages in memory. PDF has 220216 words; 12-word sequence comparison against DOCX confirms large overlap.
- 208 PDF sections excluded at >=65% overlap; 39 new sections retained: 33 in 2013, 5 in 2019, 1 undated. No other dated year gained PDF duplicates.
- Combined inventory: 318 sections / 337 passages / 239619 retained words. A future 2028 date inside prose is ignored as a heading. Earlier assumption that the PDF was wholly redundant was incorrect and superseded.
- Browser interaction: clicking 2021 preserves all 11 years of the partial preview; clicking missing 2019 reports absence without a neutral score; zero comboboxes. Desktop body scroll width equals viewport (1265 px). PASS. Final PDF-backed export replaces this partial preview.

## 2026-10-22 · chart legibility
- Heatmap label contrast checked at all 101 integer prevalence values: minimum 4.61:1 after switching black/white text by cell luminance. PASS >=4.5:1.
- Chart labels enlarged; narrow layouts use contained horizontal chart scrolling. Literal-word sparklines explicitly disclose independent vertical scales.

## 2026-10-22 · contextual local model pass
- Model Qwen3.5-9B Q4_K_M, loopback llama.cpp, contextual-it-v2.
- 12 DOCX; 1 without extractable text; 279 sections; 298 passages; 216455 words analysed; 303 without a reliable year.
- 12 annual and 44 monthly aggregates, >=3 sections each. All retained words analysed; no truncation/sampling.
- Strict allowlist schema validated for every model output. No excerpts, names, event descriptions, entry IDs or exact dates exported. Cache outside git. Chronology is automatic; scores are contextual interpretations, not measured wellbeing.

## 2026-10-22 · contextual local model pass
- Model Qwen3.5-9B Q4_K_M, loopback llama.cpp, contextual-it-v2.
- 12 DOCX; 1 without extractable text; 318 sections; 337 passages; 239619 words analysed; 306 without a reliable year.
- 14 annual aggregates, >=3 sections each; no monthly export. All retained words analysed; no truncation/sampling.
- Strict allowlist schema validated for every model output. No excerpts, names, event descriptions, entry IDs or exact dates exported. Cache outside git. Chronology is automatic; scores are contextual interpretations, not measured wellbeing.

## 2026-10-22 · public export verification
- Command: `python tools/check_reflections.py`
- PASS: full retained-text coverage (239619 words), 14 annual aggregates including PDF 2013/2019 and English-timestamp 2023, fixed-label public schema, score bounds, no period selector, generator navigation.

## 2026-10-22 · final syntax and corpus checks
- Python compilation (`reflections_context`, CLI, checker) and Node `--check trends.js`: PASS.
- Local model completed all 337 passages, 239619 retained words; 14 annual groups (2013–2026); 306 undated words included only in overall frequencies. No monthly details exported.

## 2026-10-22 · public export verification
- Command: `python tools/check_reflections.py`
- PASS: full retained-text coverage (239619 words), 14 annual aggregates including PDF 2013/2019 and English-timestamp 2023, fixed-label public schema, score bounds, no period selector, generator navigation.

## 2026-10-22 · final browser and delivery verification
- Full public export loaded at `/vita/come-sto/`: 239619 words / 337 passages / 14 year controls / 0 period selectors / 12 literal-word trend rows / 126 topic cells / 26 sport-fatigue bars. PASS.
- Recovered 2019: 5 sections / 3363 words; clicking its year preserves all 14 controls. PASS.
- Narrow app pane: body 547/547 px, timeline 477/477 px, viewBox 0 0 477 440. All 14 years fit without horizontal timeline scrolling. Desktop: body 1265/1265 px, timeline 1106/1106 px. PASS.
- Git backup: updated existing branch and draft PR 54; no raw source/cache added. Production site unchanged. Index/generator navigation preserved; operating memory updated.
