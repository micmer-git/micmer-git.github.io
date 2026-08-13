# Istruzioni per gli agenti che lavorano su questa repo

## Prima regola: **fai `git pull`.**

Una GitHub Action gira **ogni ora** e committa da sola (`hourly: sync intervals.icu +
rebuild /vita`). Un clone lasciato lì due giorni è già decine di commit indietro, e ci
si accorge tardi: i file generati esistono, sembrano a posto, e sono vecchi. Il
2026-08-13 un agente ha trovato la repo 64 commit indietro e ha creduto che `vita/`
fosse un solo `index.html`.

Se hai rigenerato dei file e nel frattempo l'Action ha committato, **non risolvere i
conflitti dentro i CSV generati**: committa prima le sorgenti, fai rebase, poi
rigenera. I file sotto `vita/cibo/data/`, `vita/index.html` e `tools/vita_tests.md`
sono output, non lavoro: si riproducono con un comando.

## Seconda regola: prima di chiudere, guarda se ci sono dati nuovi da prendere

Questa repo è fatta di tracker che vivono di dati che arrivano da fuori. **Qualunque
sia il compito con cui sei entrato**, prima di dire che hai finito controlla se le
sorgenti hanno roba nuova che i workflow sanno già digerire — e se sì, digeriscila.
Costa un comando, ed è il motivo per cui i contatori restano veri.

| tracker | come si aggiorna | cadenza |
|---|---|---|
| `/vita` + cibo | `build_vita.py --sync-source` → `build_food.py` → `build_vita.py --offline` → `check_vita.cjs` | oraria, automatica |
| `gazzaniga-orezzo/` | `sync_intervals.py --config tools/gazzaniga-orezzo.json` | oraria, automatica |
| `diario-di-un-unno/` | `sync_diario.py` | oraria, automatica |
| `sogni-di-un-unno/` | `sync_sogni.py` | oraria, automatica |
| `signoredellecime/` | `build_signore.py` | oraria, automatica (dal 2026-08-13) |
| `top-20/` | `build_top20.py` | oraria, automatica (dal 2026-08-13) |
| attività mancanti a Intervals | `strava_backfill.py <export.zip>` | **a mano**, quando arriva un export |
| `vita/cibo/` da Cronometer | metti i CSV in `tools/food/data/cronometer/`, poi `build_food.py` | **a mano**, quando arriva un export |
| `vita/spostamenti/` | archivio Google Timeline cifrato | **a mano**: non esiste un'API |
| `bike-to-work/` | nessun builder: `_data.js` è costruito a mano | — |

L'ordine della pipeline di `/vita` è vincolato e sta scritto in `vita/WORKFLOW.md`:
il cibo legge il carico, quindi il sync delle attività va **prima** di `build_food.py`.

## Terza regola: osservato, ricostruito e stimato non sono la stessa cosa

È il principio che tiene insieme tutta la repo, e va difeso in ogni superficie nuova.
Un numero misurato e uno ricostruito da un modello non si disegnano uguali, non si
etichettano uguali e non si mescolano in una media senza dirlo.

Esempi vivi da cui copiare il tono:
- il 2022 ha le sue attività vere ma il **carico è stimato** da durata e cardio: la
  banda dice "carico ricostruito" invece di "nessun dato", e il TSS dice "stim.";
- i giorni Cronometer sono **osservati**, quelli di `fill_defaults.py` **ricostruiti**,
  e `kcal_observed` / `kcal_assumed` tengono il conto separato;
- il "momento metabolico" non si emette sotto le tre componenti disponibili, perché
  con due sarebbe il ramp rate del CTL con un nome più importante.

Se aggiungi una serie, aggiungi anche il modo in cui dichiara la propria provenienza.

## Quarta regola: i registri sono uno solo

Se scrivi un elenco di serie/corsie/opzioni accanto a un elenco che esiste già,
quello nuovo resterà indietro. È già successo due volte: i CSV del cibo copiati a mano
in `vita/` mentre la sorgente viveva in un'altra repo, e il menu del correlatore
scritto a mano accanto al registro della ridgeline (heat strain e momento metabolico
non si potevano incrociare perché nessuno sapeva che c'era un secondo posto da
toccare). Deriva il secondo elenco dal primo.

## Prima di dire che hai finito

```bash
python tools/build_vita.py --offline   # se hai toccato /vita o il cibo
node tools/check_vita.cjs              # 170+ controlli, niente rete, pochi secondi
```

`check_vita.cjs` è l'unica cosa fra un grafico rotto e un'ora di quel grafico in
produzione: la pagina è un file solo e nient'altro se ne accorgerebbe. Quando un
controllo diventa falso perché la realtà è cambiata (il buco del 2022 che si riempie),
**giralo, non toglierlo**: deve restare un controllo, sul fatto nuovo.
