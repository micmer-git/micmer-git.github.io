# `orac.csv` e `daily_dozen.csv` — da dove vengono, e cosa non dicono

Due tabelle di riferimento aggiunte il **22/08/2026** per l'ordine #27 di Michele:
mostrare l'ORAC nel tempo, e vedere se e quando i Daily Dozen del dottor Greger
vengono rispettati.

> **AGGANCIATE il 04/09/2026** (ordini MC #31 e #32). Per dodici giorni sono state
> quello che questa riga diceva: solo dati, che nessuno leggeva. Adesso le legge
> `tools/food/common.py` (`load_orac`, `load_daily_dozen`), le somma
> `build_nutrition_series.py` in quindici colonne nuove di `nutrition.csv` — `orac`,
> `orac_cov_pct` e dodici `dd_*` — e le disegna `build_vita.py` in tre riquadri della
> sezione Tavola: **ORAC**, **Quanto dell'ORAC si vede** e **I dodici del dottor
> Greger**, una griglia 12 x 7.

Le due tabelle si agganciano a `foods.csv` per `food_id`. Ogni id e' stato verificato
contro il catalogo: **zero id fantasma** in entrambi i file.

---

## 1. `orac.csv` — 58 alimenti su 182

### La fonte

USDA *Database for the Oxygen Radical Absorbance Capacity (ORAC) of Selected Foods,
Release 2*, maggio 2010. Valore **ORAC totale** (idrofilo + lipofilo), in micromol
Trolox equivalenti per 100 g dell'alimento come descritto nella voce USDA.

### Il limite, che va detto prima del numero

**L'USDA ha ritirato quella tabella nel 2012.** La motivazione, sua, e' che i valori
in vitro non predicono l'effetto in vivo: i polifenoli che generano quei numeri in
provetta vengono in gran parte metabolizzati o non assorbiti, e la tabella era diventata
un argomento di vendita per succhi e integratori. Da allora non esiste un aggiornamento
ufficiale, e l'R2 del 2010 resta il riferimento piu' citato **proprio perche' non c'e'
altro**, non perche' sia stato confermato.

Quindi il grafico dell'ORAC va letto come si legge il contatore delle piante diverse:
una spia di quanto la dieta pesca da vegetali colorati e ricchi di polifenoli, **non un
punteggio da massimizzare**. Un cucchiaino di cumino da 76 800 non vale un piatto di
verdure, e il file lo dice riga per riga. Lo stesso avvertimento e' scritto in testa a
`orac.csv`, perche' chi apre il CSV senza passare di qui deve incontrarlo lo stesso.

### Cosa e' verificato e cosa e' derivato

| confidence | quante | cosa vuol dire |
|---|---|---|
| `high` | 22 | voce USDA diretta, ben documentata, alimento che corrisponde a quello del catalogo |
| `medium` | 28 | voce USDA diretta ma con un'ambiguita' dichiarata (varieta', crudo contro cotto, mix), oppure analogia esplicita con un alimento molto simile |
| `low` | 8 | stima ricavata da un valore noto, con la derivazione scritta per intero nella colonna `fonte` |

Le otto stime `low` non sono numeri usciti dal nulla: sono tutte della forma *«valore USDA
del secco, riscalato per la reidratazione col rapporto di densita' calorica del catalogo»*
(ceci in scatola, fagioli neri, cannellini, fagioli stufati, dal, passata) piu' due casi
di analogia (porcini sui champignon, zucchine). **Ignorano quanto la cottura ne distrugge**,
quindi tirano verso l'alto. La piu' debole e' `fagioli_stufati`, che ha due passaggi di
analogia in fila: se un giorno servisse tagliare, quella e' la prima.

### Copertura per gruppo del catalogo

| gruppo | coperti | totale | |
|---|---|---|---|
| frutta | 16 | 16 | ✅ completo |
| spezie | 5 | 5 | ✅ completo |
| verdura | 25 | 33 | quasi tutto |
| legumi | 7 | 16 | i secchi e le scatole; mancano i derivati |
| dolci | 3 | 17 | solo cacao e i due fondenti |
| grassi | 2 | 6 | solo mandorle e noci |
| cereali | 0 | 40 | ❌ scoperto |
| proteine | 0 | 21 | ❌ scoperto |
| latticini | 0 | 16 | ❌ scoperto |
| bevande | 0 | 7 | ❌ scoperto |
| integratori | 0 | 5 | ❌ scoperto |

### I buchi che pesano davvero

Tre, e vanno detti perche' distorcono il grafico in modo prevedibile:

1. **Il caffe'.** In una dieta reale il caffe' e' spesso il primo contributore di ORAC
   della giornata. Non c'e' nel file perche' il catalogo ha `caffe_espresso` a unita' da
   30 ml, mentre il valore che ricordo dalla tabella USDA e' per il caffe' filtro: fra i
   due c'e' un fattore di concentrazione di 3-5x che non so ricostruire con onesta'.
   Metterci un numero sbagliato per il tipo di caffe' sbagliato avrebbe spostato il
   grafico piu' di quanto lo sposti lasciarlo fuori. **Il totale giornaliero e' quindi
   sottostimato, e sistematicamente**: chi disegna il grafico lo scriva sotto.
2. **I cereali, tutti e 40.** Avena, pane integrale, quinoa, farro hanno un ORAC modesto
   ma non nullo, e non ho un valore R2 che sappia citare per nome. Il buco e' grande in
   numero di voci ma piccolo in contributo.
3. **I pomodori secchi.** Ho tolto la riga a lavoro fatto: la derivazione per
   disidratazione dava oltre 5000, che e' plausibile ma e' anche il tipo di numero
   grosso che una volta in un grafico non se ne va piu'. Meglio un buco.

Fuori dal file per costruzione: carne, pesce, uova, latticini, integratori. Non e' una
dimenticanza — nella tabella USDA gli alimenti animali non ci sono, e il loro contributo
e' vicino allo zero. Nel grafico compariranno come zero, che e' la risposta giusta.

---

## 2. `daily_dozen.csv` — 84 mappature su 82 alimenti distinti

### La fonte

Michael Greger, *How Not to Die* (2015), capitolo finale, e l'app **Dr. Greger's Daily
Dozen**. Le dodici caselle e le porzioni sono le sue; la conversione in grammi e' mia,
perche' Greger parla in *cup* e *tablespoon* e il catalogo pesa in grammi. Le porzioni
per categoria stanno in testa a `daily_dozen.csv`.

Le dodici categorie ci sono **tutte e dodici**, nell'ordine di Greger.

### Quante voci per casella

| categoria | food_id | porzione |
|---|---|---|
| fagioli | 17 | 130 g cotti · 3/giorno |
| frutti di bosco | 3 | 70 g · 1/giorno |
| altra frutta | 12 | 1 frutto o 80 g · 3/giorno |
| crucifere | 5 | 45 g · 1/giorno |
| verdure a foglia verde | 4 | 30 g crude / 90 g cotte · 2/giorno |
| altre verdure | 21 | 80 g · 2/giorno |
| **semi di lino** | **0** | 10 g macinati · 1/giorno |
| noci e semi | 3 | 30 g · 1/giorno |
| erbe e spezie | 5 | 1 g di curcuma + altre · 1/giorno |
| cereali integrali | 11 | 40-50 g · 3/giorno |
| bevande | 3 | 340 ml · 5/giorno |
| **esercizio** | **0** | 90 min moderati o 40 vigorosi |

Due alimenti compaiono in **due caselle diverse**, ed e' voluto: il **cavolo nero** e la
**rucola** sono insieme crucifere e foglie verdi. Spuntano una casella per ciascuna, mai
due volte la stessa. Sono le 84 righe con id contro 82 id distinti.

### Le due caselle scoperte, e perche'

- **Semi di lino: zero.** Non e' che Michele non li mangi: **non esistono nel catalogo**.
  Serve una voce `semi_lino` in `foods.csv` — e va detto che contano solo **macinati**,
  perche' i semi interi passano interi. Finche' la voce non c'e', questa casella nel
  grafico sara' vuota per costruzione, e va etichettata «dato assente», non «zero».
- **Esercizio: nessun food_id, ed e' corretto.** Non e' un alimento. Il dato per spuntarla
  pero' **esiste gia' in `/vita`**, solo da un'altra parte: sono le attivita' di
  intervals.icu in `tools/food/data/activities.csv`. Chi disegna il grafico se lo prende
  di li' e non dal diario alimentare.

### Le caselle deboli

- **Bevande (3 voci).** Greger conta cinque bicchieri da 340 ml, e il primo di tutti e'
  **l'acqua — che nel catalogo non c'e'**. Restano caffe', chai e cappuccino, che sono
  proprio quelli su cui lui e' piu' tiepido. Questa casella risultera' sempre quasi vuota,
  e sara' un difetto del catalogo, non della dieta.
- **Erbe e spezie (5 voci).** Greger chiede **un quarto di cucchiaino di curcuma** al
  giorno, e la curcuma pura non e' a catalogo: la voce piu' vicina e' `curry_polvere`, che
  la contiene fra le altre. Mancano anche cannella, zenzero e pepe nero (che serve ad
  assorbire la curcumina). Aggiungere `curcuma` a `foods.csv` sistemerebbe la casella.
- **Frutti di bosco (3 voci).** Poche voci ma centrate. Le marmellate **non contano**.
- **Noci e semi (3 voci).** Il burro d'arachidi del catalogo e' **sgrassato in polvere**:
  l'ho contato a meta' porzione, perche' le proteine ci sono ma i grassi buoni no.

### Cosa e' fuori per scelta di Greger, non per dimenticanza

Succhi di frutta (anche al 100%), **patate bianche** (la patata dolce invece conta),
fritti, cereali raffinati — pasta di semola, riso bianco, pane bianco, focaccia, piadina,
naan, couscous, gallette, cereali da colazione — dolci, alcolici, e tutto quello che viene
dagli animali. Dove il caso e' al limite sta scritto nella nota della riga.

Tre scelte di questo file che **non sono regole di Greger** e vanno riviste se qualcuno
la pensa diversamente: l'**avocado** messo fra le altre verdure (il catalogo lo tiene
li', Greger lo elenca fra i frutti), l'**aglio** messo fra le erbe e spezie (Greger lo
mette fra le altre verdure), e i **compositi** — `zuppa_vellutata`, `sformato_verdure`,
`polpette_legumi` — contati per la loro parte vegetale, che e' la maggioranza ma non il
totale.

---

## 3. Cosa serve per chiudere il cerchio

Aggiornato il **04/09/2026**, chiudendo gli ordini #31 e #32.

**Fatto:**

- Il grafico ORAC porta addosso la sua avvertenza — tabella ritirata dall'USDA nel 2012,
  misura in vitro — e accanto ha un **secondo riquadro che dice quanto ne copre il
  catalogo**: sugli ultimi mesi e' il **57 % delle calorie**, e sotto quella riga il primo
  grafico non sta misurando la dieta ma la parte di dieta che si sa leggere. Il buco del
  caffe' e dei cereali raffinati e' scritto nel piede, non dedotto.
- Il PDF della *Release 2* e' stato **riletto per intero** e otto voci nuove citano il
  numero NDB della tabella: pane integrale (1421), pane di avena ai semi (1318), pane di
  segale (1963), fiocchi d'avena (1708), granola (2294), rucola (1904), olio extravergine
  (372), mais dolce (728). `burro_arachidi` e' passato dall'analogia con l'arachide cruda
  (3166) alla voce diretta *Peanut butter, smooth* (3432), e la sua confidenza da `medium`
  a `high`. Il catalogo ORAC passa da 58 a **67 voci**.
- Le porzioni del Daily Dozen sono state **verificate su nutritionfacts.org/daily-dozen**:
  le dodici caselle e i loro numeri tornano tutti; la porzione di bevanda era 340 ml ed e'
  355 (12 oz, 60 oz al giorno in tutto).
- **Tre porzioni erano girate al contrario.** Le note dicevano «conta a meta'» ma il numero
  faceva contare doppio, perche' `porzione_g` e' il peso che vale UNA porzione: burro
  d'arachidi sgrassato 16 -> 64, cappuccino 150 -> 710, crusca d'avena 20 -> 80. Sul
  sgrassato era un fattore quattro, e nel verso di far sembrare piena una casella vuota.
- **`grammi_pezzo` in `foods.csv`.** ORAC e Daily Dozen ragionano in grammi, il diario in
  pezzi: senza, una banana valeva 1 g di banana. Il peso e' ricavato dal catalogo stesso —
  kcal del pezzo diviso kcal per 100 g dell'USDA — quindi non e' un numero in piu' da
  credere sulla parola. Dove manca, l'alimento resta fuori dai due conti invece di valere
  un grammo.
- La regola delle caselle multiple e' **dichiarata** in testa a `daily_dozen.csv`: un
  alimento puo' stare in piu' caselle e ne spunta una per ciascuna, mai due volte la stessa.

**Resta da fare:**

1. `semi_lino` e `curcuma` in `foods.csv`. La riga dei semi di lino sulla griglia e' oggi
   **vuota, non a zero**, ed e' la lettura giusta finche' la voce non esiste — ma resta una
   casella su dodici che non si puo' spuntare per un difetto del catalogo.
2. Una voce `acqua`, o un modo di registrarla: la casella bevande sta a zero perche' l'acqua
   non si annota, non perche' Michele non la beva.
3. Il **caffe'** in `orac.csv`. E' spesso il primo contributore di ORAC di una giornata e
   manca ancora: il catalogo tiene `caffe_espresso` a 30 ml e il valore USDA e' del caffe'
   filtro, con un fattore di concentrazione fra i due che nessuno qui sa ricostruire.
4. Distinguere `high`/`medium` da `low` **nel disegno**, non solo nel CSV. Oggi il riquadro
   ORAC dichiara la copertura in calorie ma non la qualita' della fonte voce per voce.
5. La **varieta' della mela**. Il catalogo ne tiene una sola e generica; l'USDA va da 2589
   (fuji) a 4275 (red delicious). Il 03/09/2026 Michele ha dichiarato una renetta, e il
   registro non ha avuto dove metterla.
