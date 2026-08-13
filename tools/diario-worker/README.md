# vita-diario — il pezzo di /vita che sa scrivere

`/vita` è un file statico su GitHub Pages: sa mostrare una giornata, non sa
registrarne una. Questo Worker è la metà mancante.

- **Live:** https://vita-diario.micmer-recastello.workers.dev
- **Database:** D1 `vita-diario` (`4232de15-73b4-485a-a13c-f77e1282e5e0`), una
  tabella sola, `ops`.

## Non è un secondo registro

Il registro del cibo è `tools/food/data/food_log.csv`, e resta uno solo. Qui dentro
le operazioni vivono al massimo un'ora: la Action oraria chiama
`tools/apply_diary_ops.py`, che le scrive nel CSV e le marca `applied`. Da quel
momento la pagina le legge dalla build. Due registri che dicono la stessa cosa sono
due registri che divergono — questo ha una scadenza apposta.

## Le tre operazioni

| `kind` | cosa fa | cosa porta |
|---|---|---|
| `add` | una riga nuova | `meal`, `food_id`, `qty` |
| `set` | corregge una quantità | `row_key`, `qty` |
| `del` | toglie una riga | `row_key` |

`row_key` è `<pasto>|<food_id>|<ordinale>`, dove l'ordinale conta le righe con
quello stesso `food_id` dentro quel pasto, nell'ordine del file. È la stessa chiave
che la pagina usa su `days.json` e che `apply_diary_ops.py` ricostruisce sul CSV.

Una `row_key` che nel CSV non trova niente — una ricostruzione di
`fill_defaults.py`, una riga misurata da Cronometer — viene **saltata e riferita**,
mai forzata: correggere una ricostruzione vorrebbe dire scrivere nel diario
qualcosa che Michele non ha mai raccontato.

## Le due chiavi

| segreto | header | chi la usa |
|---|---|---|
| `VITA_DIARY_KEY` | `X-Vita-Key` | il browser. La digita Michele nel diario, resta nel suo `localStorage` |
| `VITA_DIARY_ADMIN` | `X-Vita-Admin` | la GitHub Action, per `/api/pending` e `/api/applied` |

Sono separate apposta: la chiave del browser vive in un `localStorage` e non deve
poter marcare niente come "già finito nel repo". **Nessuna delle due sta in questo
repository, che è pubblico.** Le copie vere: i secret del Worker, il secret
`VITA_DIARY_ADMIN` su GitHub, `agents/secrets/api-keys.md`, e `.dev.vars` in
locale (gitignorato).

## Endpoint

```
GET    /api/health          pubblico — ok, quante ops, quante pendenti
GET    /api/day/:date       X-Vita-Key    le operazioni non ancora travasate
POST   /api/ops             X-Vita-Key    annota
DELETE /api/ops/:id         X-Vita-Key    disfa, solo se ancora pendente
GET    /api/pending         X-Vita-Admin  tutto quello che c'è da travasare
POST   /api/applied         X-Vita-Admin  {"ids": [...]} — fatto, sono nel repo
```

## Comandi

```bash
npx wrangler deploy                                   # dalla cartella di questo file
npx wrangler d1 execute vita-diario --remote --file=schema.sql
npx wrangler secret put VITA_DIARY_KEY                # ⚠️ vedi sotto
python ../../tools/diario-worker/check_worker.py      # 18 controlli sull'istanza vera
python ../apply_diary_ops.py --check                  # cosa travaserebbe, senza scrivere
```

⚠️ `echo chiave | wrangler secret put` attacca un a capo al segreto (su Windows un
CRLF), e il risultato è un 401 su una chiave giusta senza niente nei log che lo
spieghi. Il Worker fa `trim()` su entrambi i lati del confronto proprio per questo.

## Trappole già pagate

- **Cloudflare risponde 403 allo user-agent di `urllib`**, anche su `/api/health`.
  Ogni client Python qui dentro manda uno `User-Agent` esplicito. Senza, la
  diagnosi è sviante: sembra una chiave sbagliata e invece la richiesta al Worker
  non è mai arrivata.
- Le `add` si accumulano (due banane sono due), `set` e `del` no: l'ultima parola
  sulla stessa riga sostituisce la precedente, e un indice unico parziale lo rende
  un fatto del database invece che una speranza del codice.
