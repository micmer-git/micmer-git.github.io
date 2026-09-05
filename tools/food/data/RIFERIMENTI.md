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

## 1. `orac.csv` — 68 alimenti su 182

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
| `high` | 25 | voce USDA diretta, ben documentata, alimento che corrisponde a quello del catalogo |
| `medium` | 34 | voce USDA diretta ma con un'ambiguita' dichiarata (varieta', crudo contro cotto, mix), oppure analogia esplicita con un alimento molto simile |
| `low` | 9 | stima ricavata da un valore noto, con la derivazione scritta per intero nella colonna `fonte` |

(Conteggi al 05/09/2026: `grep -v '^#' orac.csv | awk -F, '{print $NF}' | sort | uniq -c`.)

Le nove stime `low` non sono numeri usciti dal nulla: sei sono della forma *«valore USDA
del secco, riscalato per la reidratazione col rapporto di densita' calorica del catalogo»*
(ceci in scatola, fagioli neri, cannellini, fagioli stufati, dal, passata), due sono casi
di analogia (porcini sui champignon, zucchine), e una — il caffe' — e' l'unica riga del file
che **non parte da una voce USDA**: parte dal caffe' filtro e arriva all'espresso per tre
strade, vedi «I buchi che pesano davvero». Le prime otto **ignorano quanto la cottura ne
distrugge**, quindi tirano verso l'alto. La piu' debole e' `fagioli_stufati`, che ha due
passaggi di analogia in fila: se un giorno servisse tagliare, quella e' la prima.

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
| bevande | 1 | 7 | solo il caffe', ed e' una stima dichiarata (vedi sotto) |
| integratori | 0 | 5 | ❌ scoperto |

### I buchi che pesano davvero

Tre, e vanno detti perche' distorcono il grafico in modo prevedibile:

1. **Il caffe' — chiuso il 05/09/2026 (ordine MC #83), con una stima dichiarata.** In una
   dieta reale il caffe' e' spesso il primo contributore di ORAC della giornata, e fino al
   05/09 valeva zero: il catalogo ha `caffe_espresso` a unita' da 30 ml, il valore che
   circola come «USDA» (2780 µmol TE/100 ml) e' del caffe' filtro e **non sta nel PDF
   della Release 2**, riletto per intero il 03/09. Il fattore di concentrazione fra filtro
   ed espresso, che il 04/09 «non sapevo ricostruire con onesta'», si ricostruisce per tre
   strade indipendenti, e la riga le scrive tutte in `fonte`:
   - la **dose di polvere per ml** (7 g in 30 ml contro 60 g/L del filtro, fattore 3,9)
     da' 10.800; Sanchez-Gonzalez 2005 (*Food Chem* 90:133) trova la stessa resa
     antiossidante per grammo di polvere fra filtro ed espresso, quindi il fattore e' quello;
   - il **rapporto FRAP** espresso/filtro di Carlsen 2010 (*Nutr J* 9:3, la tabella dei
     3100 alimenti: 14,2 contro 2,5 mmol/100 g, fattore 5,7) da' 15.800;
   - il **TEAC dell'espresso** (36,5 mmol Trolox/L, Yashin 2013, *Antioxidants* 2:230)
     per il rapporto ORAC/TEAC tipico degli alimenti, 2-3x, da' 7.300-11.000.
   Si tiene **10.000 µmol TE/100 ml**, cifra tonda perche' e' una stima con un margine di
   circa il 50 %: una tazzina vale 3.000, quanto 100 g di mela. E' l'unica riga del file
   che non viene dall'USDA, sta a `low`, e `check_vita.cjs` pretende che resti `low` finche'
   nessuno porta un ORAC misurato sull'espresso. La regola resta quella di prima — un
   numero sbagliato sposta il grafico piu' di un buco — ma qui il buco era il numero
   sbagliato: zero, sul primo contributore della giornata.
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

Aggiornato il **05/09/2026** (ordine #83); prima il 04/09, chiudendo gli ordini #31 e #32.

**Fatto:**

- **Il caffe' e' nel file** (05/09/2026, ordine #83): `caffe_espresso` a 10.000 µmol TE/100 ml,
  `low`, stima a tre strade dal caffe' filtro — la derivazione intera sta nella sezione
  «I buchi che pesano davvero» e nella colonna `fonte`. Il piede del grafico non dice piu'
  che il caffe' manca: dice che e' l'unica riga stimata. Il catalogo ORAC passa da 67 a
  **68 voci**, e la casella bevande da 0/7 a 1/7.

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
