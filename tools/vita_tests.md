# /vita/cruscotto — report cumulativo dei build

Ogni run di `tools/build_cruscotto.py` appende qui cosa ha trovato nei dati
Intervals.icu e cosa ha scritto. Si aggiunge, non si sovrascrive: la storia
è il punto — un campo che smette di arrivare si vede come uno scalino.

## 2026-08-09 18:04 — --check

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal —
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: NON scritta

## 2026-08-09 18:05 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (320 KB)

## 2026-08-09 18:14 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (321 KB)

## 2026-08-09 16:14 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (21/21)
ok   almeno 20 riquadri (21)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (32908 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (28 ok)

## 2026-08-09 18:31 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (321 KB)

## 2026-08-09 16:31 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (21/21)
ok   almeno 20 riquadri (21)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (32898 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-09 16:32 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (21/21)
ok   almeno 20 riquadri (21)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (32898 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-09 16:32 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (21/21)
ok   almeno 20 riquadri (21)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (32898 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-09 18:33 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (322 KB)

## 2026-08-09 16:33 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (22/22)
ok   almeno 20 riquadri (22)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (36017 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-09 18:35 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (322 KB)

## 2026-08-09 16:35 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (22/22)
ok   almeno 20 riquadri (22)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (36017 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-09 18:35 — build

```
span: 2015-03-29 → 2026-08-09  (4152 giorni)
  ctl        4152 valori (2430 non nulli)  dal 2015-03-29
  load       4152 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (322 KB)

## 2026-08-09 16:35 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (22/22)
ok   almeno 20 riquadri (22)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (36017 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-10 06:05 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1738 non nulli)  dal 2019-06-19
  sleep       548 valori (548 non nulli)  dal 2025-01-21
  score       548 valori (548 non nulli)  dal 2025-01-21
  hrv         548 valori (548 non nulli)  dal 2025-01-21
  rhr         566 valori (566 non nulli)  dal 2025-01-20
  steps       566 valori (566 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2256 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:279
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (321 KB)

## 2026-08-10 06:05 — check_cruscotto.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (22/22)
ok   almeno 20 riquadri (22)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   finestra "12m": nessun renderer solleva eccezioni
info  finestra "12m": 0 riquadri senza dati
ok   finestra "ytd": nessun renderer solleva eccezioni
info  finestra "ytd": 0 riquadri senza dati
ok   finestra "90g": nessun renderer solleva eccezioni
info  finestra "90g": 2 riquadri senza dati (Peso, Massa grassa)
ok   nessuna coordinata NaN/Infinity negli SVG (35995 nodi controllati)
ok   ogni <path> ha un tracciato reale (72 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2256 (ricalcolato dal payload)
ok   testata: chilometri = 76.350 (ricalcolato dal payload)
ok   testata: ore in movimento = 3864 (ricalcolato dal payload)
ok   testata: notti misurate = 548 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.482.961 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (3 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-19→2023-04-10)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-10 13:09 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (346 KB)

## 2026-08-10 11:09 — check_vita.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (31/31)
ok   almeno 30 riquadri (31)
ok   finestra "2a": nessun renderer solleva eccezioni
info  finestra "2a": 0 riquadri senza dati
ok   finestra "1a": nessun renderer solleva eccezioni
info  finestra "1a": 0 riquadri senza dati
ok   finestra "3m": nessun renderer solleva eccezioni
info  finestra "3m": 2 riquadri senza dati (Peso, Massa grassa)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   nessuna coordinata NaN/Infinity negli SVG (43875 nodi controllati)
ok   ogni <path> ha un tracciato reale (144 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.257 (ricalcolato dal payload)
ok   testata: chilometri = 76.437 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.868 (ricalcolato dal payload)
ok   testata: notti misurate = 549 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.484.881 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (7 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-10 13:11 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (572 KB)

## 2026-08-10 13:15 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (587 KB)

## 2026-08-10 11:15 — check_vita.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (32/32)
ok   almeno 30 riquadri (32)
ok   finestra "2a": nessun renderer solleva eccezioni
info  finestra "2a": 0 riquadri senza dati
ok   finestra "1a": nessun renderer solleva eccezioni
info  finestra "1a": 0 riquadri senza dati
ok   finestra "3m": nessun renderer solleva eccezioni
info  finestra "3m": 2 riquadri senza dati (Peso, Massa grassa)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   nessuna coordinata NaN/Infinity negli SVG (48861 nodi controllati)
ok   ogni <path> ha un tracciato reale (144 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.257 (ricalcolato dal payload)
ok   testata: chilometri = 76.437 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.868 (ricalcolato dal payload)
ok   testata: notti misurate = 549 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.484.881 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (7 riquadri)
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (31 ok)

## 2026-08-10 13:15 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (587 KB)

## 2026-08-10 13:16 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (587 KB)

## 2026-08-10 11:16 — check_vita.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (32/32)
ok   almeno 32 riquadri (32)
ok   finestra "2a": nessun renderer solleva eccezioni
info  finestra "2a": 0 riquadri senza dati
ok   finestra "1a": nessun renderer solleva eccezioni
info  finestra "1a": 0 riquadri senza dati
ok   finestra "3m": nessun renderer solleva eccezioni
info  finestra "3m": 2 riquadri senza dati (Peso, Massa grassa)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   nessuna coordinata NaN/Infinity negli SVG (48861 nodi controllati)
ok   ogni <path> ha un tracciato reale (144 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.257 (ricalcolato dal payload)
ok   testata: chilometri = 76.437 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.868 (ricalcolato dal payload)
ok   testata: notti misurate = 549 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.484.881 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (7 riquadri)
ok   openDay() esiste
ok   il dettaglio giornaliero e' inlineato (92 giorni)
ok   il popup si riempie (40/40 giorni provati)
ok   il popup mostra la sezione "corpo" su almeno un giorno
ok   il popup mostra la sezione "allenamento" su almeno un giorno
ok   il popup mostra la sezione "tavola" su almeno un giorno
ok   il popup mostra la sezione "micro" su almeno un giorno
ok   openDay() regge un giorno senza diario alimentare
ok   almeno un'attivita' nel popup linka a intervals.icu con un id vero
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (40 ok)

## 2026-08-10 11:16 — check_vita.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (32/32)
ok   almeno 32 riquadri (32)
ok   finestra "2a": nessun renderer solleva eccezioni
info  finestra "2a": 0 riquadri senza dati
ok   finestra "1a": nessun renderer solleva eccezioni
info  finestra "1a": 0 riquadri senza dati
ok   finestra "3m": nessun renderer solleva eccezioni
info  finestra "3m": 2 riquadri senza dati (Peso, Massa grassa)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   nessuna coordinata NaN/Infinity negli SVG (48861 nodi controllati)
ok   ogni <path> ha un tracciato reale (144 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.257 (ricalcolato dal payload)
ok   testata: chilometri = 76.437 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.868 (ricalcolato dal payload)
ok   testata: notti misurate = 549 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.484.881 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (7 riquadri)
ok   openDay() esiste
ok   il dettaglio giornaliero e' inlineato (92 giorni)
ok   il popup si riempie (40/40 giorni provati)
ok   il popup mostra la sezione "corpo" su almeno un giorno
ok   il popup mostra la sezione "allenamento" su almeno un giorno
ok   il popup mostra la sezione "tavola" su almeno un giorno
ok   il popup mostra la sezione "micro" su almeno un giorno
ok   openDay() regge un giorno senza diario alimentare
ok   almeno un'attivita' nel popup linka a intervals.icu con un id vero
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (40 ok)

## 2026-08-10 13:16 — build

```
span: 2015-03-29 → 2026-08-10  (4153 giorni)
  ctl        4153 valori (2431 non nulli)  dal 2015-03-29
  load       4153 valori (1739 non nulli)  dal 2019-06-19
  sleep       549 valori (549 non nulli)  dal 2025-01-21
  score       549 valori (549 non nulli)  dal 2025-01-21
  hrv         549 valori (549 non nulli)  dal 2025-01-21
  rhr         567 valori (567 non nulli)  dal 2025-01-20
  steps       567 valori (567 non nulli)  dal 2025-01-20
  vo2         279 valori (279 non nulli)  dal 2025-01-22
  weight       65 valori (65 non nulli)  dal 2025-01-21
  bodyfat      53 valori (53 non nulli)  dal 2025-06-27
  acts       2257 attività
  attività per anno: 2015:3 2016:33 2017:39 2018:44 2019:105 2020:349 2021:300 2023:255 2024:378 2025:471 2026:280
  buchi ≥45 giorni senza attività: 6 → 2015-03-30→2015-09-22, 2015-09-24→2016-02-03, 2016-08-18→2017-01-28, 2017-12-04→2018-02-16, 2018-11-21→2019-01-14, 2021-10-19→2023-04-10
```

pagina: scritta (587 KB)

## 2026-08-10 11:16 — check_vita.cjs

```
ok   lo script inline gira senza eccezioni
ok   window.CRUSCOTTO esposto
ok   ogni riquadro dichiarato e' montato (32/32)
ok   almeno 32 riquadri (32)
ok   finestra "2a": nessun renderer solleva eccezioni
info  finestra "2a": 0 riquadri senza dati
ok   finestra "1a": nessun renderer solleva eccezioni
info  finestra "1a": 0 riquadri senza dati
ok   finestra "3m": nessun renderer solleva eccezioni
info  finestra "3m": 2 riquadri senza dati (Peso, Massa grassa)
ok   finestra "sempre": nessun renderer solleva eccezioni
ok   finestra "sempre": nessun riquadro vuoto
ok   nessuna coordinata NaN/Infinity negli SVG (48861 nodi controllati)
ok   ogni <path> ha un tracciato reale (144 path)
ok   nessun segno fuori dal proprio viewBox
ok   nessuna etichetta dell'asse y tagliata dalla gronda
ok   nessuna sovrapposizione fra etichette dell'asse x
ok   testata: attività = 2.257 (ricalcolato dal payload)
ok   testata: chilometri = 76.437 (ricalcolato dal payload)
ok   testata: ore in movimento = 3.868 (ricalcolato dal payload)
ok   testata: notti misurate = 549 (ricalcolato dal payload)
ok   dislivello totale plausibile: 1.484.881 m
ok   ogni riquadro ha la tabella di ripiego
ok   ogni riquadro multi-serie ha la legenda (7 riquadri)
ok   openDay() esiste
ok   il dettaglio giornaliero e' inlineato (92 giorni)
ok   il popup si riempie (40/40 giorni provati)
ok   il popup mostra la sezione "corpo" su almeno un giorno
ok   il popup mostra la sezione "allenamento" su almeno un giorno
ok   il popup mostra la sezione "tavola" su almeno un giorno
ok   il popup mostra la sezione "micro" su almeno un giorno
ok   openDay() regge un giorno senza diario alimentare
ok   almeno un'attivita' nel popup linka a intervals.icu con un id vero
ok   il buco che copre tutto il 2022 e' dichiarato (2021-10-18→2023-04-09)
ok   6 buchi ≥45 giorni dichiarati: 2015-03-29→2015-09-21, 2015-09-23→2016-02-02, 2016-08-17→2017-01-27, 2017-12-03→2018-02-15, 2018-11-20→2019-01-13, 2021-10-18→2023-04-09
ok   CSS --s1 = #3987e5 (slot validato)
ok   CSS --s2 = #d95926 (slot validato)
ok   CSS --s3 = #199e70 (slot validato)
ok   CSS --s4 = #c98500 (slot validato)
ok   CSS --paper = #211d16 (il fondo su cui la tavolozza e' stata validata)
```

esito: tutti passati (40 ok)
