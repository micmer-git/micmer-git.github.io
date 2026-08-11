# Lotti letti dagli screenshot

Un CSV per lotto, stessa intestazione di `food_log.csv`:

    date,meal,food_id,qty,note,source

`source` = `foto`. Vengono uniti a `food_log.csv` da `common.load_food_log()`;
i duplicati esatti (stessa data + pasto + alimento) vengono scartati.

**Un file per agente/mese**: se due processi scrivessero lo stesso file si
sovrascriverebbero, e il sintomo sarebbe un diario con dei buchi invece di un
errore. Nome consigliato: `2026-03.csv`.

**Regole di lettura, non negoziabili:**
- si registra solo un giorno con l'**intestazione di data visibile** nello
  screenshot; le sezioni senza data non si attribuiscono a occhio;
- si registra solo cibo **riconoscibile**; se non si capisce cosa sia, si salta —
  un buco dichiarato vale piu' di una giornata plausibile e sbagliata;
- le quantita' sono porzioni standard assunte, e la nota lo dice;
- alimento che non esiste in `foods.csv`? Va aggiunto **con tutti i 19 nutrienti**
  piu' `plant`/`fermented`/`upf`, altrimenti sparisce dai conteggi senza errore.
