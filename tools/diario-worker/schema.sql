-- Il diario di /vita, lato server.
--
-- Qui NON vive il diario alimentare: vive `tools/food/data/food_log.csv`, nel repo.
-- Questa tabella e' una **casella di posta**: raccoglie quello che Michele annota dal
-- telefono, lo serve subito alla pagina (cosi' l'annotazione si vede all'istante e da
-- qualunque dispositivo), e la Action oraria lo travasa nel CSV e lo marca `applied`.
-- Due registri che dicono la stessa cosa sono due registri che divergono: questo ha
-- una vita di al massimo un'ora, poi la verita' torna a essere una sola.
--
-- `kind`:
--   add  una riga nuova           -> food_id + qty + meal
--   set  correggi una quantita'   -> row_key della riga base + qty nuova
--   del  togli una riga           -> row_key della riga base
--
-- `row_key` e' `<pasto>|<food_id>|<ordinale nel pasto>`, cioe' esattamente la chiave
-- con cui la pagina identifica una riga di `days.json`. Vale solo per set/del.

CREATE TABLE IF NOT EXISTS ops (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  day        TEXT    NOT NULL,            -- 2026-08-13
  kind       TEXT    NOT NULL CHECK (kind IN ('add', 'set', 'del')),
  meal       TEXT    NOT NULL DEFAULT '',
  food_id    TEXT    NOT NULL DEFAULT '',
  qty        REAL,
  row_key    TEXT,
  note       TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL,
  applied_at TEXT                          -- NULL = non ancora nel repo
);

CREATE INDEX IF NOT EXISTS ops_day ON ops (day);
CREATE INDEX IF NOT EXISTS ops_pending ON ops (applied_at, id);

-- Una riga base non puo' avere due correzioni pendenti: la seconda sostituisce la
-- prima, e l'indice unico parziale lo rende un fatto del database invece che una
-- speranza del codice.
CREATE UNIQUE INDEX IF NOT EXISTS ops_one_pending_per_row
  ON ops (day, kind, row_key) WHERE applied_at IS NULL AND row_key IS NOT NULL;
