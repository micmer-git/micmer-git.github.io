#!/usr/bin/env python3
"""Temperatura delle uscite, FatMax e "momento metabolico", giorno per giorno.

Da leggere PRIMA di guardare qualunque grafico che esca di qui, come per
`microbiome_model.py`:

    **Una sola delle tre cose qui dentro e' una misura.** La temperatura e'
    misurata (male, vedi sotto). Il FatMax e' un MODELLO: nessuno ha mai messo
    questo atleta sotto una maschera metabolica, non esiste una calorimetria
    indiretta, non esiste un test incrementale con analisi dei gas. Il "momento
    metabolico" e' un INDICE COMPOSITO inventato qui, con i pesi in chiaro,
    costruito perche' l'unica cosa interessante nel marketing di Hume — guardare
    la DERIVATA invece del livello — non richiede di comprare niente.

    Quello che segue serve a vedere una tendenza e a rendere visibile un
    ragionamento. Non e' un referto.


================================================================================
1. TEMPERATURA  —  misurata, ma dal polso
================================================================================

L'API di Intervals.icu espone due famiglie di campi di temperatura:

  * sensore del dispositivo:  `average_temp`, `min_temp`, `max_temp`
  * meteo ricostruito:        `average_weather_temp`, `min_weather_temp`,
                              `max_weather_temp`, `average_feels_like`,
                              `min_feels_like`, `max_feels_like`, `has_weather`

Su QUESTO archivio (2.257 attivita', cache al 2026-08-10) **tutti i campi meteo
sono vuoti: 2257 valori `None` su 2257, e `has_weather` e' `False` ovunque.**
Il meteo non e' mai stato agganciato alle attivita'. Fare un grafico
"temperatura percepita" da questi campi darebbe una pagina bianca, o peggio, un
grafico bello e falso costruito su qualche default.

Il sensore del dispositivo invece c'e', e copre bene (percentuali reali, per
anno, stampate da `--check`): ~25% nel 2018 e ~45% nel 2016 — anni Strava, prima
del Garmin — e poi **fra l'85% e il 95% dal 2019 in avanti**.

Il limite vero non e' la copertura, e' COSA misura: e' il termometro di un
orologio da polso (FR935, fenix 6) o di un ciclocomputer al manubrio. Legge
l'aria vicino a un corpo che produce calore, al sole o all'ombra a seconda di
dove punta il braccio. **Legge sistematicamente piu' caldo dell'aria.** Si vede
nel dato stesso: la mediana di gennaio su questo archivio e' 14 °C, che in
Bergamasca all'alba non e' l'aria. E' una misura di *esposizione termica
percepita dal dispositivo*, ottima per confrontare un'uscita con un'altra e per
il ciclo stagionale, inutile come dato meteo.

Le attivita' indoor (`trainer=True`, `VirtualRide`) sono ESCLUSE dalla serie:
12 rulli hanno un `average_temp`, ma e' la temperatura del garage.


================================================================================
2. FATMAX  —  modello, con le assunzioni numerate
================================================================================

FatMax = l'intensita' a cui l'ossidazione dei grassi tocca il massimo. Sotto,
si va piano e si bruciano pochi grassi in valore assoluto; sopra, il glicogeno
prende il sopravvento e l'ossidazione dei grassi crolla.

Cosa serve per misurarlo davvero: un test incrementale con analisi dei gas
espirati e le equazioni stechiometriche di Frayn (1983), che dai volumi di O2
consumato e CO2 prodotta ricavano i grammi di substrato:

    grassi (g/min) = 1.67 · VO2 − 1.67 · VCO2
    CHO    (g/min) = 4.55 · VCO2 − 3.21 · VO2       [VO2, VCO2 in L/min]

  (Frayn KN, J Appl Physiol 1983;55(2):628-634, PMID 6618956 — forma con
   azoto urinario trascurato, standard nella fisiologia dell'esercizio.)

**Qui non c'e' nessun VCO2.** Non c'e' mai stato. Quindi le equazioni sopra
sono citate per dire cosa NON abbiamo, non per usarle. Quello che abbiamo e'
la frequenza cardiaca: `icu_hr_zone_times` (l'istogramma del tempo passato in
7 zone), `average_heartrate`, `lthr` e `athlete_max_hr`. Il modello parte da li'.

--- Assunzione 1: dove sta il FatMax, in %FCmax ---------------------------------

  Achten J, Gleeson M, Jeukendrup AE, "Determination of the exercise intensity
  that elicits maximal fat oxidation", Med Sci Sports Exerc 2002;34(1):92-97,
  PMID 11782653. 18 ciclisti maschi moderatamente allenati, cicloergometro:

      FatMax          = 64 ± 4 %VO2max  =  74 ± 3 %FCmax
      zona FatMax     = 55–72 %VO2max   =  68–79 %FCmax
        (la "zona" e' definita come l'intervallo in cui l'ossidazione dei
         grassi resta entro il 10% del picco)
      Fatmin          = 89 ± 3 %VO2max  =  92 ± 1 %FCmax

Si sceglie la coorte "allenati" e non la popolazione generale (Venables 2005,
n=300: FatMax 48.3 %VO2max = 61.5 %FCmax) perche' questo atleta e' allenato:
LTHR 168, FCmax 185, CTL a tre cifre, 400+ attivita' l'anno. Usare il valore
della popolazione generale qui sposterebbe il FatMax di 13 punti di %FCmax
verso il basso senza motivo.

Motivo per cui si lavora in %FCmax e non in %VO2max, che e' il modo in cui la
letteratura riporta quasi tutto:

  Chávez-Guevara IA et al., Sports Med 2023;53(12):2399-2416, PMID 37584843
  (meta-regressione, 64 studi, ~7.474 partecipanti): **la FC al FatMax e' molto
  piu' stabile fra soggetti del VO2 al FatMax — CV 8.8% contro 17.2%** — e gli
  autori raccomandano esplicitamente di usare la frequenza cardiaca relativa e
  non il consumo di ossigeno relativo per fissare i riferimenti di FatMax.

Onesta' obbligatoria: **Maunder, Plews & Kilding (Front Physiol 2018;9:599)
scrivono che non esistono dati normativi di FatMax espressi in %FCmax o in
%FCriserva.** I 74 / 68–79 %FCmax di Achten 2002 sono di UN singolo studio su
18 uomini. Sono il miglior aggancio disponibile, non un consenso.

--- Assunzione 2: la forma della curva ------------------------------------------

Serve una funzione ossidazione-grassi(FC). Se ne assume una parabola:

    fatox(fc) = MFO · max(0, 1 − ((fc − fc_fatmax) / W)² )

con W fissato dalla definizione stessa di zona FatMax di Achten: ai bordi della
zona (±5.5 %FCmax, cioe' ±10 bpm con FCmax 185) l'ossidazione vale il 90% del
picco. Da 1 − (10/W)² = 0.9 segue W = 31.6 bpm.

**Questa e' una verifica, non un parametro libero**: con quel W la parabola si
annulla a fc_fatmax ± 31.6 bpm = 137 ± 32 = **169 bpm**, e il Fatmin misurato da
Achten sta a 92 %FCmax = **170 bpm**. Due punti indipendenti dello stesso studio,
un solo grado di liberta', e tornano a 1 bpm. `--check` ristampa questo
controllo ogni volta: se un giorno smettesse di tornare, il modello e' rotto.

--- Assunzione 3: il picco, MFO -------------------------------------------------

  Achten J, Jeukendrup AE, Int J Sports Med 2003;24(8):603-608, PMID 14598198,
  n=55 uomini di endurance a digiuno: **MFO = 0.52 ± 0.15 g/min**. Coerente con
  Maunder 2018 (endurance-trained lean males, n=201: 0.53 ± 0.16 g/min).

**Lo stato di allenamento NON sposta il FatMax, sposta l'MFO.** E' uno dei
pochi punti su cui la letteratura e' concorde:

  * Stisen AB et al., Eur J Appl Physiol 2006;98(5):497-506, PMID 17006714:
    8 allenate vs 9 non allenate, ossidazione dei grassi +22%/+35%, ma
    FatMax 56 ± 3 vs 53 ± 2 %VO2max — la stessa intensita' relativa.
  * Lima-Silva AE et al., J Sports Sci Med 2010;9(1):31-35: MFO 0.47 vs 0.29
    g/min (p<0.05), FatMax 61.6 vs 64.4 %VO2max (n.s.).
  * Maunder 2018 conclude lo stesso.

Quindi il modello **non** muove il FatMax con la forma. E non muove nemmeno
l'MFO con essa: servirebbe una pendenza pubblicata in g·min⁻¹ per punto di
VO2max, e non esiste. L'MFO resta al valore di riferimento per maschio
allenato. **L'asse "forma" e' deliberatamente non modellato**, ed e' meglio
dirlo che fingere una calibrazione.

--- Assunzione 4: i carboidrati spostano il FatMax ------------------------------

Questo e' l'unico posto in cui il diario alimentare entra nel modello, ed e'
**l'anello piu' debole di tutta la catena**. Lo si dichiara qui, non in nota.

  Volek JS et al., "Metabolic characteristics of keto-adapted ultra-endurance
  runners" (studio FASTER), Metabolism 2016;65(3):100-110. 20 atleti d'élite,
  gruppo low-carb (10% E da CHO) vs high-carb (59% E da CHO), ~20 mesi di
  abitudine:
      picco di ossidazione dei grassi  1.54 ± 0.18  vs  0.67 ± 0.14 g/min
      FatMax                           70.3 ± 6.3   vs  54.9 ± 7.8  %VO2max

Da questi due punti si ricavano due pendenze, entrambe INTERNE allo stesso
studio (mescolare laboratori diversi darebbe pendenze 3× piu' ripide e
insensate):

      d(FatMax)/d(CHO%)  = (70.3 − 54.9) / (10 − 59) = −0.314 %VO2max per punto
      d(ln MFO)/d(CHO%)  = ln(1.54/0.67) / (10 − 59) = −0.0170 per punto

**E dal 2026-08-17 anche l'asse dei GRASSI** (chiesto da Michele: "cerca di
capire se puoi migliorare quel modello anche in base ai grassi assunti durante
quel periodo specifico"). Non e' un parametro nuovo: e' lo stesso studio letto
sull'altra macro. I due bracci di FASTER stavano a **69% vs 25% dell'energia da
grassi**, e arrivavano agli stessi due valori di MFO e FatMax:

      d(FatMax)/d(FAT%)  = (70.3 − 54.9) / (69 − 25) = +0.350 %VO2max per punto
      d(ln MFO)/d(FAT%)  = ln(1.54/0.67) / (69 − 25) = +0.0189 per punto

I due assi pesano meta' ciascuno, sulla stessa finestra di 60 giorni. **Perche'
non basta il carboidrato**: usando solo il CHO si assume implicitamente che
tutto quello che non e' carboidrato sia grasso, cioe' che le proteine siano
costanti. Con proteine costanti i due termini danno lo stesso identico numero
(gli scostamenti dalle rispettive dieta di riferimento — 50% CHO e 35% grassi —
sono uguali e opposti), quindi il secondo asse non sposta niente dove non c'e'
niente da sapere: **agisce solo nei mesi in cui la quota proteica si muove**, e
in questo diario si muove. `--check` stampa l'escursione delle proteine
residue, che e' esattamente la misura di quanto valga la differenza.

La conversione da %VO2max a %FCmax usa la pendenza ricavata dai bordi della zona
di Achten 2002 stessa — (79−68)/(72−55) = **0.647 %FCmax per %VO2max** — che per
inciso coincide con la relazione di Swain (1994), 0.64. Autoconsistente.

Ancoraggio: 50% dell'energia da carboidrati = dieta occidentale non
manipolata = il FatMax di Achten. Su questo archivio la quota abituale sta
intorno al 55-58%, quindi lo spostamento risulta di **1-3 %VO2max, cioe' 1-2
bpm**. Piccolo, come dev'essere: e' giusto che due mesi di dieta normale non
producano l'effetto di venti mesi di chetogenica.

**Quattro cose che questo pezzo non fa, e che vanno sapute:**

  a) FASTER e' CROSS-SECTIONAL, non randomizzato: quei venti atleti erano gia'
     diversi prima. Estrapolare la sua pendenza su una finestra mobile di 60
     giorni di dieta e' un salto, non una deduzione.
  b) L'effetto ACUTO del pasto pre-uscita **non e' modellato**, pur essendo il
     piu' documentato: Achten & Jeukendrup, J Sports Sci 2003;21(12):1017-1025,
     75 g di glucosio 45 minuti prima → MFO 0.33 vs 0.46 g/min (−30%) e FatMax
     52 vs 60 %VO2max. Non e' modellato perche' **il diario registra il pasto
     (colazione/pranzo/cena) ma non l'ora**, e senza l'ora non si sa se
     un'uscita delle 6:20 sia a digiuno o dopo colazione. Un effetto del 30%
     agganciato a un'ipotesi sull'orario sarebbe la parte piu' visibile del
     risultato e la meno fondata.
  c) La finestra mobile e' di 60 giorni perche' l'adattamento della macchina
     ossidativa e' lento (FASTER parla di mesi), non perche' 60 sia calibrato.
  d) Il diario copre **dal 2024-08-11**. Prima di quella data non c'e' ne' asse
     carboidrati ne' asse grassi: il FatMax resta al valore nudo di Achten, e la
     colonna `fatmax_shift_bpm` e' 0 per costruzione, non perche' la dieta fosse
     neutra.
  e) Meta' delle calorie del diario sono RICOSTRUITE (`fill_defaults.py`) e non
     osservate. Il secondo asse legge la stessa sorgente del primo, quindi non
     aggiunge incertezza — ma nemmeno la toglie: dove la giornata e' ricostruita,
     la quota di grassi e' quella dei pasti abituali, non di quello che e' stato
     mangiato. Sui giorni Cronometer e' misurata.

--- Assunzione 5: come si ricava un istogramma di FC da 7 numeri ---------------

`icu_hr_zone_times` da' i secondi in 7 zone; `icu_hr_zones` da' i 7 estremi
SUPERIORI. Gli estremi inferiori delle zone 2..7 sono l'estremo superiore della
precedente. **Il pavimento della zona 1 non e' noto**, e conta molto: la banda
FatMax (126-146 bpm) taglia proprio dentro la zona 1 di una Ride (0-135).

Invece di inventarlo, lo si RICAVA dal dato. Si assume tempo distribuito in modo
uniforme dentro ogni zona, e si risolve per il pavimento f della zona 1 che fa
tornare la media ricostruita esattamente a `average_heartrate`, che e' un dato
misurato:

    Σ tempo_i · centro_i / Σ tempo_i  =  average_heartrate

E' una calibrazione vincolata dai dati, non un parametro. **Funziona su 1.727
attivita' su 1.884 (92%)**, con pavimento mediano 108 bpm — che e' un valore da
sgambata/riscaldamento, cioe' plausibile. Nel restante 8% la soluzione cade
fuori da [40, cima della zona 1] e viene tagliata al bordo; quelle attivita'
portano `hr_fit=0` nel CSV e vanno guardate con sospetto.

Resta comunque un'approssimazione grossolana: dentro una zona il tempo non e'
affatto uniforme, e sette bidoni non sono una distribuzione.

--- Cosa esce, e quanto ci si puo' credere ------------------------------------

`fat_g_est` = Σ sui bidoni di (minuti · fatox(centro del bidone)). Con tutto
quello che c'e' scritto sopra, l'incertezza vera su quel numero e' facilmente
del ±40%. **Il suo valore assoluto non significa niente. La sua variazione nel
tempo, a parita' di modello, e' l'unica cosa che vale.**

`cho_g_est` = (kcal − 9 · fat_g_est) / 4, proteine trascurate.
`--check` lo confronta con `carbs_used`, la stima indipendente di Intervals.icu
(presente su 230 attivita'): non e' una validazione — sono due modelli, non un
modello e una misura — ma se divergessero di un ordine di grandezza vorrebbe
dire che qualcosa qui e' rotto.


================================================================================
3. "MOMENTO METABOLICO"  —  ovvero: cosa ho trovato davvero su Hume
================================================================================

Domanda di partenza: cos'e' lo "User Gain" del Hume Band, e c'e' un concetto
pubblicato di "metabolic momentum"? Cercato. Risposta:

  * **"User Gain" non e' un modello e non e' una metrica.** E' una riga di
    marketing sul sito Hume, con un refuso: "Hume Band User Gain an average 2
    years 5 days of extra life from better habits" — cioe' "users gain". Nel
    catalogo metriche ufficiale di Hume (25 metriche) "User Gain" non compare.
    [humehealth.com — blogs/hume-blogs/comprehensive-hume-band-metrics-catalog]

  * **Quello che esiste davvero si chiama "Metabolic Momentum"**, ed e' una
    metrica proprietaria Hume su scala **−20..+20**, descritta come "direction
    and velocity of metabolic health changes", "the trend line of your health
    habits… your body's health speedometer", espressa in *giorni di vita
    guadagnati o persi*, da sonno, movimento, stress, nutrizione, recupero.
    [humehealth.com — blogs/hume-blogs/metabolic-momentum-the-hidden-force-behind-longevity]

  * **Dietro non c'e' niente di pubblicato.** Nessun articolo peer-reviewed,
    nessun whitepaper, nessun brevetto, nessuna documentazione tecnica: la
    metodologia e' dichiarata proprietaria e non e' divulgata. La copertura
    stampa e' comunicati a pagamento (GlobeNewswire, AccessNewswire) risindacati
    su Yahoo Finance, non giornalismo. Le cifre di longevita' (39 giorni, 129
    giorni, 2 anni e 5 giorni) risalgono a **un sondaggio interno su n=60 di
    efficacia auto-percepita**. L'unico studio serio dell'ecosistema Hume
    (Tinsley GM et al., medRxiv 2026.07.17.26358337, n=67 vs modello a 4
    compartimenti e DXA) **valida la bilancia Hume Pod, non il Band**, non
    tocca il Metabolic Momentum, ed e' comunque un preprint.

  * **"Metabolic momentum" non e' un termine scientifico.** PubMed sulla frase
    esatta risponde *"Quoted phrase not found in phrase index"*. Europe PMC ne
    trova 4 occorrenze, e nessuna e' il concetto: una preprint di genetica del
    riso, una review sul microambiente tumorale, un lavoro sull'acquacoltura dei
    gamberi e gli atti del congresso BMA del **1900**. Sono artefatti di
    indicizzazione. L'uso reale del termine e' blog di medicina funzionale,
    integratori e marketing.
    Da non confondere con concetti pubblicati che suonano simili e non lo sono:
    *metabolic memory* / *legacy effect* (Lachin & Nathan, DCCT/EDIC, Diabetes
    Care 2021;44(10):2216-2224) riguarda il rischio persistente di complicanze
    da esposizione glicemica pregressa, non un punteggio giornaliero;
    *adaptive thermogenesis*, *EPOC* e *metabolic flexibility* sono campi a se',
    e nessuno usa "momentum" come termine tecnico.

**Conclusione: e' marketing senza sostanza pubblicata.** Detto che e' un
risultato utile quanto il contrario, resta pero' un'idea buona sotto — e non e'
di Hume, e' della fisiologia dell'allenamento, dove la derivata si guarda da
sempre (il *ramp rate* del CTL). L'idea e': **il livello dice dove sei, la
derivata dice dove stai andando, e per decidere cosa fare domani serve la
seconda.**

Quindi qui si costruisce un indicatore analogo, sulla stessa scala −20..+20 per
rendere esplicito il debito, ma con **i pesi in chiaro** e con dentro solo dati
che questo archivio ha davvero. Non e' il Metabolic Momentum di Hume: quello non
si puo' replicare, perche' non e' pubblicato.

Definizione: per ogni componente, z = (media 7 giorni − media 28 giorni) diviso
la deviazione standard della componente su tutto l'archivio. E' una derivata
normalizzata: risponde a "questa cosa sta salendo o scendendo rispetto a com'era
il mese scorso", non a "questa cosa e' alta". Poi somma pesata, tanh per
comprimere le code, ×20.

I pesi sono in `PESI` sotto, uno per riga, con scritto perche'. La somma dei
moduli fa 1. Il segno di ogni componente e' scelto dalla direzione fisiologica,
non dai dati.

**Copertura, che qui e' tutto il problema.** Le componenti fisiologiche
(sonno, HRV, FC a riposo) esistono **solo dal 2025-01-20**; quelle alimentari
**dal 2024-08-11**; il carico e' reale **dal 2019-06-19** (prima le attivita'
vengono da Strava senza FC ne' potenza) e **dal 2021-10-18 al 2023-04-09 non
c'e' NESSUNA attivita' — e' un buco d'archivio, non una pausa**. Il composito
si emette **solo se sono disponibili almeno 3 componenti su 6**, e la colonna
`mm_n` dice sempre quante ne sono entrate: un −8 con `mm_n=3` e un −8 con
`mm_n=6` non sono lo stesso numero. I pesi delle componenti mancanti vengono
rinormalizzati sulle presenti, il che e' comodo e discutibile: significa che
prima del 2025 il "momento metabolico" e' quasi solo carico e dieta.

Conseguenza pratica di quella soglia di 3: **`mm` esiste solo dal 2024-08-11**,
cioe' dal primo giorno di diario — 731 giorni sui 4.154 dell'archivio. Prima le
componenti disponibili sono due, carico e fatica, e due non bastano. E' una
scelta, ed e' la piu' onesta possibile: un "momento metabolico" fatto di solo
CTL e ATL sarebbe il ramp rate con un altro nome e l'aria di dire molto di piu'.
Meglio una colonna vuota che un numero che finge.


    python tools/food/metabolismo.py --check
    python tools/food/metabolismo.py --export <path.csv>
"""
import argparse
import collections
import csv
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

import common

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# La cache grezza di Intervals.icu vive accanto agli script, non dentro food/.
# E' un artefatto di build: se manca, questo script non deve fare rete, deve
# uscire dicendo che manca (vedi build_food.py, che lo salta senza rompersi).
CACHE = common.ROOT.parent / ".cruscotto_cache.json"
SERIES = common.DERIVED / "nutrition_series.csv"
OUT = common.DERIVED / "metabolismo.csv"

# --- fatti dell'archivio, non ipotesi: servono a marcare i giorni ------------
LOAD_REAL_FROM = "2019-06-19"   # prima: attivita' Strava senza FC ne' potenza
# Il "buco d'archivio" era il 2022, che su Intervals non esiste. Dal 2026-08-13 non e'
# piu' un buco: tools/strava_backfill.py ha rimesso dentro le 394 attivita' di quell'anno
# dall'export Strava, e la CTL di quei giorni si ricalcola invece di decadere a zero.
# Le due date restano perche' li' la forma e' RICOSTRUITA e non misurata, e per marcarla
# come tale; il carico pero' c'e', quindi non si esclude piu' dalle componenti.
GAP_START, GAP_END = "2021-10-18", "2023-04-09"   # ricostruito da Strava, non misurato
PHYSIO_FROM = "2025-01-20"      # sonno / HRV / FC riposo / VO2max
DIET_FROM = "2024-08-11"        # inizio del diario alimentare

# --- FatMax: costanti pubblicate (vedi il docstring per le citazioni) --------
FATMAX_PCT_HRMAX = 0.74         # Achten 2002: 74 ± 3 %FCmax
ZONE_LO_PCT, ZONE_HI_PCT = 0.68, 0.79   # zona FatMax, 68-79 %FCmax
FATMIN_PCT_HRMAX = 0.92         # Achten 2002: 92 ± 1 %FCmax
ZONE_EDGE_FRACTION = 0.90       # "entro il 10% del picco" = definizione di zona
MFO_BASE = 0.52                 # g/min, Achten 2003, maschi endurance a digiuno
FATMAX_BASE_PCT_VO2 = 64.0      # Achten 2002, la stessa coorte

# Achten 2002 da' la zona in entrambe le unita': la pendenza fra le due esce
# dai suoi stessi estremi. (79-68)/(72-55) = 0.647, ~ Swain 1994 (0.64).
HRMAX_PER_VO2MAX = (79.0 - 68.0) / (72.0 - 55.0)

# FASTER (Volek 2016), pendenze RICAVATE DENTRO LO STESSO STUDIO: 10% vs 59% E
# da carboidrati -> FatMax 70.3 vs 54.9 %VO2max, MFO 1.54 vs 0.67 g/min.
CHO_REF_PCT = 50.0              # ancoraggio: dieta occidentale non manipolata
D_FATMAX_D_CHO = (70.3 - 54.9) / (10.0 - 59.0)          # -0.314 %VO2max/punto
D_LNMFO_D_CHO = math.log(1.54 / 0.67) / (10.0 - 59.0)   # -0.0170 /punto
CHO_WIN = 60                    # giorni: l'adattamento ossidativo e' lento

# --- e i GRASSI assunti, dallo stesso studio (chiesto il 2026-08-17) ---------
# Fino a qui il modello leggeva UNA SOLA macro: i carboidrati. Non era una svista —
# la disponibilita' di carboidrati e' il regolatore vero — ma era un'assunzione
# nascosta: usando solo il CHO si sta implicitamente dicendo che tutto quello che
# non e' carboidrato e' grasso, cioe' che le PROTEINE sono costanti. Nel diario di
# Michele non lo sono: la quota proteica si muove di parecchi punti fra un mese di
# carico e uno di scarico, e in quei mesi la stessa quota di carboidrati corrisponde
# a diete di grasso diverse.
#
# I due bracci di FASTER danno anche l'asse dei grassi, e sono gli STESSI soggetti e
# gli STESSI due numeri di arrivo: il gruppo low-carb stava a 69 %E di grassi, quello
# high-carb a 25 %E. Quindi la pendenza sul grasso non e' un parametro nuovo da
# tarare, e' la stessa evidenza letta sull'altro asse.
FAT_REF_PCT = 35.0              # 50 CHO + 35 grassi + 15 proteine = 100, la dieta di riferimento
D_FATMAX_D_FAT = (70.3 - 54.9) / (69.0 - 25.0)          # +0.350 %VO2max/punto
D_LNMFO_D_FAT = math.log(1.54 / 0.67) / (69.0 - 25.0)   # +0.0189 /punto
# I due assi pesano la meta' ciascuno. Con proteine costanti la media dei due da'
# ESATTAMENTE quello che dava il carboidrato da solo (i due scostamenti sono uguali e
# opposti per costruzione), quindi il cambio non sposta niente dove non c'e' niente
# da sapere: agisce solo nei mesi in cui le proteine si muovono, che sono l'unica
# informazione che prima si buttava via.
W_CHO, W_FAT = 0.5, 0.5
# Il diario e' corto e la pendenza viene da un cross-sectional: si tiene lo
# spostamento dentro il range di FatMax davvero osservato in letteratura.
FATMAX_CLAMP_VO2 = (45.0, 75.0)

# --- momento metabolico: i pesi, uno per riga, col perche' ------------------
# Segno = direzione fisiologica, non correlazione trovata nei dati. La somma dei
# moduli fa 1. Ogni componente e' uno z-score di (media 7g - media 28g).
PESI = [
    # (chiave, peso, etichetta, perche')
    ("fitness", +0.22, "forma (CTL)",
     "il CTL che sale e' l'unica cosa qui che sia davvero un accumulo"),
    ("fatica",  -0.16, "fatica (ATL su CTL)",
     "l'acuto che scappa al cronico anticipa il buco, quindi pesa negativo"),
    ("sonno",   +0.20, "sonno",
     "la variabile con il rapporto effetto/costo piu' alto, e la piu' sua"),
    ("hrv",     +0.14, "HRV",
     "rumorosa sul giorno singolo, informativa sulla settimana: media, non spot"),
    ("rhr",     -0.12, "FC a riposo",
     "sale quando qualcosa non va (carico, sonno, infezione): segno invertito"),
    ("dieta",   +0.16, "dieta (fibra, piante, meno UPF)",
     "qualita', non quantita': le kcal le decide gia' il bilancio energetico"),
]


# ---------------------------------------------------------------------------
# caricamento
# ---------------------------------------------------------------------------
def load_cache():
    if not CACHE.exists():
        return None
    with CACHE.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_series():
    if not SERIES.exists():
        return {}
    with SERIES.open(encoding="utf-8", newline="") as fh:
        return {r["date"]: r for r in csv.DictReader(fh) if r.get("date")}


def num(row, key):
    v = (row or {}).get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1. temperatura
# ---------------------------------------------------------------------------
def is_indoor(a):
    """Rulli e uscite virtuali: il sensore c'e' ma misura il garage."""
    return bool(a.get("trainer")) or a.get("type") in ("VirtualRide", "VirtualRun")


def temp_coverage(acts):
    """Copertura reale per anno dei due gruppi di campi. Serve a --check e al
    README: e' esattamente il numero che impedisce di fare un grafico falso."""
    dev = ("average_temp", "min_temp", "max_temp")
    wx = ("average_weather_temp", "min_weather_temp", "max_weather_temp",
          "average_feels_like", "min_feels_like", "max_feels_like")
    per = collections.defaultdict(lambda: {"n": 0, "dev": 0, "wx": 0, "out": 0,
                                           "out_dev": 0})
    for a in acts:
        y = (a.get("start_date_local") or a.get("start_date") or "????")[:4]
        p = per[y]
        p["n"] += 1
        has_dev = a.get("average_temp") is not None
        if has_dev:
            p["dev"] += 1
        if any(a.get(f) is not None for f in wx):
            p["wx"] += 1
        if not is_indoor(a):
            p["out"] += 1
            if has_dev:
                p["out_dev"] += 1
    return per


# ---------------------------------------------------------------------------
# 2. FatMax
# ---------------------------------------------------------------------------
def zone_width(hrmax):
    """W della parabola, dedotto dalla definizione di zona FatMax di Achten.

    Ai bordi (±(FATMAX-ZONE_LO) di %FCmax) l'ossidazione vale ZONE_EDGE_FRACTION
    del picco. Non e' un parametro libero: e' un vincolo, e il fatto che poi la
    parabola si annulli dove Achten misura il Fatmin e' la verifica del modello.
    """
    half = (FATMAX_PCT_HRMAX - ZONE_LO_PCT) * hrmax        # bpm, meta' zona
    return half / math.sqrt(1.0 - ZONE_EDGE_FRACTION)


def fatox(hr, hr_fatmax, w, mfo):
    """g/min di grassi a una data FC. Parabola, vedi Assunzione 2."""
    x = (hr - hr_fatmax) / w
    return max(0.0, mfo * (1.0 - x * x))


def hr_histogram(a):
    """Da `icu_hr_zone_times` + `icu_hr_zones` a bidoni (lo, hi, secondi).

    Il pavimento della zona 1 e' incognito e conta: lo si ricava imponendo che
    la media ricostruita coincida con `average_heartrate`, che e' misurata.
    Ritorna (bidoni, fit) dove fit=1 se il pavimento e' uscito plausibile.
    """
    z, t = a.get("icu_hr_zones"), a.get("icu_hr_zone_times")
    avg = a.get("average_heartrate")
    if not z or not t or not avg or len(z) != len(t):
        return None, 0
    tot = sum(t)
    if tot <= 0 or t[0] <= 0:
        return None, 0

    upper = list(z)
    rest = sum(t[i] * ((upper[i - 1] + upper[i]) / 2.0) for i in range(1, len(z)))
    # media ricostruita = avg  ->  t0*(f + z0)/2 + rest = avg*tot
    floor = 2.0 * (avg * tot - rest) / t[0] - upper[0]
    fit = 1 if 40.0 <= floor <= upper[0] else 0
    floor = min(max(floor, 40.0), upper[0] - 1.0)

    bins = [(floor, upper[0], t[0])]
    for i in range(1, len(z)):
        bins.append((upper[i - 1], upper[i], t[i]))
    return bins, fit


def cho_pct_of_energy(row):
    """% dell'energia da carboidrati in un giorno di diario. 4 kcal/g."""
    kcal, carb = num(row, "kcal"), num(row, "carb_g")
    if not kcal or carb is None:
        return None
    return 100.0 * 4.0 * carb / kcal


def fat_pct_of_energy(row):
    """% dell'energia da grassi in un giorno di diario. 9 kcal/g."""
    kcal, fat = num(row, "kcal"), num(row, "fat_g")
    if not kcal or fat is None:
        return None
    return 100.0 * 9.0 * fat / kcal


def fatmax_for(hrmax, cho_pct, fat_pct=None):
    """FatMax (bpm), MFO (g/min) e lo spostamento, data la dieta abituale.

    Legge DUE macro, non una: i carboidrati abituali e i grassi abituali, ognuno col
    proprio scostamento dalla dieta di riferimento e con la pendenza che i due bracci
    di FASTER danno sul proprio asse. Vedi il blocco di costanti: con proteine
    costanti i due termini coincidono, e la differenza compare solo quando le
    proteine si muovono — che e' esattamente il caso che la versione a un asse sola
    non poteva vedere.

    Se `cho_pct` e' None (nessun diario) si resta sui valori nudi di Achten e lo
    spostamento e' 0 PER COSTRUZIONE, non perche' la dieta fosse neutra. Se c'e' il
    carboidrato ma non il grasso — non capita, escono dalla stessa riga di diario, ma
    non e' un motivo per non reggerlo — si ricade sul solo asse disponibile invece di
    dimezzare lo scostamento, che sarebbe una diluizione silenziosa.
    """
    base_hr = FATMAX_PCT_HRMAX * hrmax
    if cho_pct is None and fat_pct is None:
        return base_hr, MFO_BASE, 0.0
    terms = []                       # (peso, d_vo2, d_lnmfo)
    if cho_pct is not None:
        d = cho_pct - CHO_REF_PCT
        terms.append((W_CHO, D_FATMAX_D_CHO * d, D_LNMFO_D_CHO * d))
    if fat_pct is not None:
        d = fat_pct - FAT_REF_PCT
        terms.append((W_FAT, D_FATMAX_D_FAT * d, D_LNMFO_D_FAT * d))
    wtot = sum(t[0] for t in terms)
    d_vo2 = sum(t[0] * t[1] for t in terms) / wtot
    d_lnmfo = sum(t[0] * t[2] for t in terms) / wtot
    vo2 = min(max(FATMAX_BASE_PCT_VO2 + d_vo2, FATMAX_CLAMP_VO2[0]), FATMAX_CLAMP_VO2[1])
    shift = (vo2 - FATMAX_BASE_PCT_VO2) * HRMAX_PER_VO2MAX / 100.0 * hrmax
    return base_hr + shift, MFO_BASE * math.exp(d_lnmfo), shift


def activity_fat(a, hr_fatmax, mfo, hrmax):
    """Grammi di grassi e di CHO stimati per una attivita'."""
    bins, fit = hr_histogram(a)
    if not bins:
        return None
    w = zone_width(hrmax)
    lo_hr = (FATMAX_PCT_HRMAX - (FATMAX_PCT_HRMAX - ZONE_LO_PCT)) * hrmax
    hi_hr = (FATMAX_PCT_HRMAX + (ZONE_HI_PCT - FATMAX_PCT_HRMAX)) * hrmax
    # la banda si sposta con il FatMax: si trasla, non si deforma
    shift = hr_fatmax - FATMAX_PCT_HRMAX * hrmax
    lo_hr, hi_hr = lo_hr + shift, hi_hr + shift

    fat_g, in_zone_s = 0.0, 0.0
    for lo, hi, secs in bins:
        if secs <= 0:
            continue
        mid = (lo + hi) / 2.0
        fat_g += fatox(mid, hr_fatmax, w, mfo) * secs / 60.0
        # sovrapposizione del bidone con la banda FatMax, distribuzione uniforme
        ov = max(0.0, min(hi, hi_hr) - max(lo, lo_hr))
        if hi > lo:
            in_zone_s += secs * ov / (hi - lo)

    kcal = a.get("calories")
    cho_g = None
    if kcal:
        # proteine trascurate: durante l'esercizio contano pochi punti percentuali
        cho_g = max(0.0, (kcal - 9.0 * fat_g) / 4.0)
    return {"fat_g": fat_g, "cho_g": cho_g, "zone_s": in_zone_s, "fit": fit,
            "secs": sum(b[2] for b in bins)}


# ---------------------------------------------------------------------------
# 3. momento metabolico
# ---------------------------------------------------------------------------
def rolling(vals, d, win):
    """Media della componente sui `win` giorni fino a `d` compreso."""
    cur = date.fromisoformat(d)
    got = [vals[(cur - timedelta(days=j)).isoformat()]
           for j in range(win)
           if vals.get((cur - timedelta(days=j)).isoformat()) is not None]
    return (sum(got) / len(got)) if got else None


def momentum(components, days):
    """z(7g − 28g) per componente, somma pesata, tanh, ×20.

    Perche' la derivata e non il livello: e' l'unica idea difendibile dentro il
    "Metabolic Momentum" di Hume, e non e' di Hume — e' il ramp rate del CTL.
    """
    sd = {}
    for k, vals in components.items():
        got = [v for v in vals.values() if v is not None]
        sd[k] = statistics.pstdev(got) if len(got) > 2 else 0.0

    out = {}
    for d in days:
        parts, wsum, n = {}, 0.0, 0
        for key, weight, _label, _why in PESI:
            vals = components.get(key, {})
            if not sd.get(key):
                continue
            fast = rolling(vals, d, 7)
            slow = rolling(vals, d, 28)
            if fast is None or slow is None:
                continue
            z = (fast - slow) / sd[key]
            parts[key] = z
            wsum += abs(weight)
            n += 1
        if n < 3:      # sotto le 3 componenti il composito non si emette
            out[d] = (None, parts, n)
            continue
        # i pesi mancanti si rinormalizzano sui presenti: comodo e discutibile,
        # significa che prima del 2025 e' quasi solo carico e dieta
        raw = sum(w * parts[k] for k, w, _l, _p in PESI if k in parts) / wsum
        out[d] = (20.0 * math.tanh(raw), parts, n)
    return out


# ---------------------------------------------------------------------------
def build():
    cache = load_cache()
    if cache is None:
        return None
    acts = cache.get("activities") or []
    well = {w["id"]: w for w in (cache.get("wellness") or []) if w.get("id")}
    series = load_series()

    # --- temperatura, per giorno, solo outdoor, pesata sul tempo di movimento
    tmp = collections.defaultdict(list)
    for a in acts:
        d = (a.get("start_date_local") or a.get("start_date") or "")[:10]
        if not d or is_indoor(a) or a.get("average_temp") is None:
            continue
        tmp[d].append((a["average_temp"], a.get("min_temp"), a.get("max_temp"),
                       a.get("moving_time") or 0))

    # --- carboidrati abituali: media mobile a 60 giorni della quota di energia
    cho_day = {d: cho_pct_of_energy(r) for d, r in series.items()}
    # --- e i grassi abituali, stessa finestra: escono dalla stessa riga di diario
    fat_day = {d: fat_pct_of_energy(r) for d, r in series.items()}

    # --- FCmax: non e' una misura, e' l'impostazione dell'atleta su Intervals,
    # riapplicata all'indietro su tutto l'archivio (185 su 2.238 attivita' su
    # 2.238 che ce l'hanno: un solo valore, mai cambiato). Sui giorni senza
    # attivita' si porta avanti l'ultimo noto, che e' l'unica cosa sensata.
    hrmax_day = {}
    for a in acts:
        d = (a.get("start_date_local") or a.get("start_date") or "")[:10]
        if d and a.get("athlete_max_hr"):
            hrmax_day[d] = float(a["athlete_max_hr"])
    if not hrmax_day:
        return None

    # --- FatMax e ossidazione, per attivita' poi per giorno
    fat = collections.defaultdict(lambda: {"fat_g": 0.0, "cho_g": 0.0,
                                           "zone_s": 0.0, "secs": 0.0,
                                           "n": 0, "fit": 0, "kcal": 0.0})
    checks = []      # (cho_g stimato, carbs_used di Intervals) per --check
    for a in acts:
        d = (a.get("start_date_local") or a.get("start_date") or "")[:10]
        hrmax = a.get("athlete_max_hr")
        if not d or not hrmax:
            continue
        cho = rolling(cho_day, d, CHO_WIN)
        fatp = rolling(fat_day, d, CHO_WIN)
        hr_fm, mfo, _shift = fatmax_for(hrmax, cho, fatp)
        r = activity_fat(a, hr_fm, mfo, hrmax)
        if not r:
            continue
        f = fat[d]
        f["fat_g"] += r["fat_g"]
        f["cho_g"] += r["cho_g"] or 0.0
        f["zone_s"] += r["zone_s"]
        f["secs"] += r["secs"]
        f["kcal"] += a.get("calories") or 0.0
        f["n"] += 1
        f["fit"] += r["fit"]
        if a.get("carbs_used") is not None and r["cho_g"]:
            checks.append((r["cho_g"], a["carbs_used"]))

    # --- CTL/ATL con dentro il carico ricostruito da Strava -------------------
    # `well` porta i valori di Intervals, e nel 2022 sono una decrescita verso zero
    # sopra un anno di allenamenti che Intervals non ha. Rifacendo la media
    # esponenziale sul carico giornaliero PIU' il backfill, la forma di quell'anno
    # torna quella vera. Stessa funzione che usa build_vita.py, cosi' la pagina e
    # questo modello non possono raccontare due 2022 diversi.
    extra = common.backfill_load_by_day()
    ctl_of, atl_of = {}, {}
    if extra:
        wd = sorted(well)
        loads = [(well[d].get("ctlLoad") or 0) + extra.get(d, 0.0) for d in wd]
        seed = next((well[d].get("ctl") for d in wd if well[d].get("ctl") is not None), 0.0)
        rc, ra = common.recompute_ctl_atl(loads, seed, seed)
        ctl_of = dict(zip(wd, rc))
        atl_of = dict(zip(wd, ra))

    # --- componenti del momento metabolico ----------------------------------
    comp = {k: {} for k, *_ in PESI}
    for d, w in well.items():
        ctl = ctl_of.get(d, w.get("ctl"))
        atl = atl_of.get(d, w.get("atl"))
        if ctl is not None and d >= LOAD_REAL_FROM:
            comp["fitness"][d] = float(ctl)
            if atl is not None and ctl > 0:
                # rapporto, non differenza: 10 punti di ATL pesano diversamente
                # su un CTL di 30 e su uno di 90
                comp["fatica"][d] = float(atl) / float(ctl)
        if w.get("sleepSecs"):
            comp["sonno"][d] = w["sleepSecs"] / 3600.0
        if w.get("hrv"):
            comp["hrv"][d] = float(w["hrv"])
        if w.get("restingHR"):
            comp["rhr"][d] = float(w["restingHR"])
    for d, r in series.items():
        fib, pl, upf = num(r, "fiber_g"), num(r, "plants_7d"), num(r, "pct_upf")
        if fib is None or pl is None:
            continue
        # qualita' su tre assi noti, scalati sui pieni gia' usati altrove nella
        # pipeline (45 g di fibra, 30 piante/settimana, 35% di UPF come tetto)
        comp["dieta"][d] = (min(1.0, fib / 45.0) + min(1.0, pl / 30.0)
                            - min(1.0, (upf or 0.0) / 35.0))

    all_days = set(tmp) | set(fat) | set(well) | set(series)
    all_days = sorted(d for d in all_days if d and len(d) == 10)
    mm = momentum(comp, all_days)

    rows = []
    # il primo giorno dell'archivio puo' precedere la prima attivita': si parte
    # dal valore piu' vecchio noto invece che da un numero scritto qui dentro
    last_hrmax = hrmax_day[min(hrmax_day)]
    for d in all_days:
        row = {"date": d}

        # --- temperatura (misurata: sensore da polso, outdoor, pesata) -------
        ts = tmp.get(d)
        if ts:
            wt = sum(x[3] for x in ts) or len(ts)
            row["temp_c"] = round(sum(x[0] * (x[3] or 1) for x in ts) / wt, 1)
            mins = [x[1] for x in ts if x[1] is not None]
            maxs = [x[2] for x in ts if x[2] is not None]
            row["temp_min_c"] = round(min(mins), 1) if mins else ""
            row["temp_max_c"] = round(max(maxs), 1) if maxs else ""
            row["temp_n"] = len(ts)
        else:
            row.update({"temp_c": "", "temp_min_c": "", "temp_max_c": "", "temp_n": 0})

        # --- FatMax (modello) -------------------------------------------------
        cho = rolling(cho_day, d, CHO_WIN)
        fatp = rolling(fat_day, d, CHO_WIN)
        hrmax = last_hrmax = hrmax_day.get(d, last_hrmax)
        hr_fm, mfo, shift = fatmax_for(hrmax, cho, fatp)
        row["cho_pct_60d"] = round(cho, 1) if cho is not None else ""
        row["fat_pct_60d"] = round(fatp, 1) if fatp is not None else ""
        row["fatmax_hr"] = round(hr_fm)
        row["fatmax_lo_hr"] = round(hr_fm - (FATMAX_PCT_HRMAX - ZONE_LO_PCT) * hrmax)
        row["fatmax_hi_hr"] = round(hr_fm + (ZONE_HI_PCT - FATMAX_PCT_HRMAX) * hrmax)
        row["fatmax_shift_bpm"] = round(shift, 1)
        row["mfo_g_min"] = round(mfo, 3)
        f = fat.get(d)
        if f and f["n"]:
            row["fat_g_est"] = round(f["fat_g"], 1)
            row["cho_g_est"] = round(f["cho_g"], 0) if f["cho_g"] else ""
            row["fatmax_min"] = round(f["zone_s"] / 60.0, 1)
            row["train_min"] = round(f["secs"] / 60.0, 1)
            row["n_act"] = f["n"]
            # 1 solo se il pavimento della zona 1 e' uscito plausibile ovunque
            row["hr_fit"] = 1 if f["fit"] == f["n"] else 0
        else:
            row.update({"fat_g_est": "", "cho_g_est": "", "fatmax_min": "",
                        "train_min": "", "n_act": 0, "hr_fit": ""})

        # --- momento metabolico (indice composito, pesi in PESI) --------------
        val, parts, n = mm.get(d, (None, {}, 0))
        row["mm"] = round(val, 1) if val is not None else ""
        row["mm_n"] = n
        for key, *_ in PESI:
            row["mm_" + key] = round(parts[key], 2) if key in parts else ""

        rows.append(row)
    return {"rows": rows, "acts": acts, "checks": checks, "comp": comp}


FIELDS = (["date", "temp_c", "temp_min_c", "temp_max_c", "temp_n",
           "cho_pct_60d", "fat_pct_60d", "fatmax_hr", "fatmax_lo_hr", "fatmax_hi_hr",
           "fatmax_shift_bpm", "mfo_g_min", "fat_g_est", "cho_g_est",
           "fatmax_min", "train_min", "n_act", "hr_fit", "mm", "mm_n"]
          + ["mm_" + k for k, *_ in PESI])


def report(res):
    rows, acts = res["rows"], res["acts"]
    print(f"{len(rows)} giorni, {rows[0]['date']} → {rows[-1]['date']}")
    print("  temperatura = MISURATA (sensore da polso) · FatMax = MODELLO · "
          "momento metabolico = INDICE COMPOSITO")

    print("\n1. TEMPERATURA — copertura reale per anno")
    print(f"  {'anno':<6}{'attivita':>9}{'sensore':>9}{'%':>7}"
          f"{'outdoor':>9}{'sens.out':>9}{'%':>7}{'meteo':>8}")
    cov = temp_coverage(acts)
    for y in sorted(cov):
        c = cov[y]
        p = 100.0 * c["dev"] / c["n"] if c["n"] else 0
        po = 100.0 * c["out_dev"] / c["out"] if c["out"] else 0
        print(f"  {y:<6}{c['n']:>9}{c['dev']:>9}{p:>6.1f}%"
              f"{c['out']:>9}{c['out_dev']:>9}{po:>6.1f}%{c['wx']:>8}")
    tw = sum(c["wx"] for c in cov.values())
    tn = sum(c["n"] for c in cov.values())
    print(f"  → i campi meteo (weather_temp, feels_like) sono popolati su "
          f"{tw}/{tn} attivita'.")
    print("    Vuoti su tutto l'archivio: has_weather e' False ovunque, il meteo")
    print("    non e' mai stato agganciato. Non ci si puo' fare NIENTE.")
    tv = [float(r["temp_c"]) for r in rows if r["temp_c"] != ""]
    print(f"  → sensore: {len(tv)} giorni con un valore, mediana {statistics.median(tv):.1f} °C, "
          f"min {min(tv):.1f}, max {max(tv):.1f}")
    print("    La mediana di gennaio su questo archivio e' ~14 °C: e' il polso,")
    print("    non l'aria. Buono per confronti relativi, non come dato meteo.")

    print("\n2. FATMAX — modello (Achten 2002/2003, Volek 2016), non una misura")
    hrmax = max(float(a["athlete_max_hr"]) for a in acts if a.get("athlete_max_hr"))
    zero = FATMAX_PCT_HRMAX * hrmax + zone_width(hrmax)
    fatmin = FATMIN_PCT_HRMAX * hrmax
    print(f"  FCmax {hrmax:.0f} (impostazione dell'atleta su Intervals, non una "
          f"misura, la stessa su tutto l'archivio)")
    print(f"  → FatMax {FATMAX_PCT_HRMAX * hrmax:.0f} bpm ({FATMAX_PCT_HRMAX:.0%} FCmax), "
          f"banda {ZONE_LO_PCT * hrmax:.0f}–{ZONE_HI_PCT * hrmax:.0f} bpm")
    print(f"  verifica interna: la parabola calibrata sulla larghezza di banda "
          f"si annulla a {zero:.0f} bpm;")
    print(f"                    il Fatmin misurato da Achten sta a {fatmin:.0f} bpm "
          f"({FATMIN_PCT_HRMAX:.0%} FCmax).  scarto {abs(zero - fatmin):.1f} bpm")
    print("                    → un grado di liberta', due punti indipendenti "
          "dello stesso studio: torna.")
    sh = [float(r["fatmax_shift_bpm"]) for r in rows if r["cho_pct_60d"] != ""]
    chos = [float(r["cho_pct_60d"]) for r in rows if r["cho_pct_60d"] != ""]
    fats = [float(r["fat_pct_60d"]) for r in rows if r.get("fat_pct_60d") not in ("", None)]
    if sh:
        print(f"  carboidrati abituali ({CHO_WIN} gg): {min(chos):.0f}–{max(chos):.0f} %E "
              f"(mediana {statistics.median(chos):.0f}) → spostamento del FatMax "
              f"{min(sh):+.1f}…{max(sh):+.1f} bpm")
        if fats:
            print(f"  grassi abituali ({CHO_WIN} gg): {min(fats):.0f}–{max(fats):.0f} %E "
                  f"(mediana {statistics.median(fats):.0f}) — dal 2026-08-17 il modello "
                  f"legge questo asse insieme al carboidrato")
            # quanto vale davvero il secondo asse: le proteine sono il residuo
            pr = [100.0 - c - f for c, f in zip(chos, fats)]
            print(f"  → proteine residue {min(pr):.0f}–{max(pr):.0f} %E: e' l'escursione "
                  f"che la versione a un asse solo assumeva costante")
        print(f"  ma solo su {len(sh)} giorni su {len(rows)}: il diario parte dal "
              f"{DIET_FROM}, prima lo spostamento e' 0 per costruzione.")
    fg = [float(r["fat_g_est"]) for r in rows if r["fat_g_est"] != ""]
    print(f"  grassi stimati: {len(fg)} giorni con allenamento, mediana "
          f"{statistics.median(fg):.0f} g, max {max(fg):.0f} g")
    print("  incertezza reale su quel numero: dell'ordine del ±40%. Vale la sua")
    print("  VARIAZIONE nel tempo, non il valore assoluto.")
    ck = res["checks"]
    if ck:
        rr = sorted(a / b for a, b in ck if b)
        n = len(rr)
        print(f"  confronto con `carbs_used` di Intervals.icu ({n} attivita'): "
              f"rapporto p10/mediana/p90 = "
              f"{rr[n // 10]:.2f} / {rr[n // 2]:.2f} / {rr[9 * n // 10]:.2f}")
        print("  **Questo controllo vale poco e va detto**: entrambe le stime "
              "partono dallo stesso")
        print("  campo `calories`, quindi l'accordo e' in buona parte circolare. "
              "Dimostra solo che")
        print("  la quota di grassi che il modello sottrae e' dello stesso ordine "
              "di quella di")
        print("  Intervals — non che uno dei due abbia ragione. Non esiste qui "
              "nessuna misura")
        print("  indipendente di ossidazione dei substrati contro cui validare.")
    nf = sum(1 for r in rows if r["hr_fit"] == 0)
    print(f"  ricostruzione dell'istogramma di FC: {nf} giorni con almeno "
          f"un'attivita' in cui il pavimento")
    print("  della zona 1 e' finito fuori range e va tagliato (hr_fit=0).")

    print("\n3. MOMENTO METABOLICO — indice composito costruito qui")
    print("  Hume 'User Gain' non esiste: e' una riga di marketing con un refuso.")
    print("  La metrica vera si chiama 'Metabolic Momentum', scala −20..+20, e non")
    print("  ha NIENTE di pubblicato dietro (metodologia proprietaria, cifre di")
    print("  longevita' da un sondaggio interno n=60). 'metabolic momentum' non e'")
    print("  in PubMed: 'Quoted phrase not found in phrase index'. E' marketing.")
    print("  Si tiene solo l'idea sotto — guardare la derivata, non il livello —")
    print("  che comunque non e' di Hume: e' il ramp rate del CTL.")
    print(f"  {'componente':<32}{'giorni':>8}{'peso':>7}   perche'")
    for key, weight, label, why in PESI:
        got = sum(1 for r in rows if r["mm_" + key] != "")
        print(f"  {label:<32}{got:>8}{weight:>+7.2f}   {why}")
    mrows = [r for r in rows if r["mm"] != ""]
    if mrows:
        mv = [float(r["mm"]) for r in mrows]
        print(f"  composito su {len(mv)} giorni di {len(rows)}, "
              f"{mrows[0]['date']} → {mrows[-1]['date']}, "
              f"{min(mv):+.1f}…{max(mv):+.1f}, ultimo {rows[-1]['mm']}")
        print("  Comincia col diario e non prima: fino ad allora le uniche "
              "componenti sono carico e")
        print("  fatica, cioe' due, e sotto le tre il composito non si emette. "
              "E' una scelta, ed e'")
        print("  la piu' onesta: un 'momento metabolico' fatto di solo CTL e ATL "
              "sarebbe il ramp")
        print("  rate con un altro nome e un'aria di dire molto di piu'.")
    byn = collections.Counter(r["mm_n"] for r in rows if r["mm"] != "")
    print("  componenti disponibili: " +
          " · ".join(f"{k} su 6 → {v} giorni" for k, v in sorted(byn.items())))
    print(f"  un mm con mm_n=3 e uno con mm_n=6 non sono lo stesso numero: prima "
          f"del {PHYSIO_FROM}")
    print("  sonno, HRV e FC a riposo non esistono, quindi resta quasi solo "
          "carico e dieta.")
    print(f"  {GAP_START} → {GAP_END}: su Intervals non c'e' niente, ma le attivita'")
    print("  esistono e arrivano dall'export Strava. Il carico li' e' STIMATO da durata")
    print("  e cardio, e la CTL e' ricalcolata: e' ricostruito, non misurato.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="riporta, non scrive")
    ap.add_argument("--export", help="copia il CSV anche qui")
    args = ap.parse_args()

    res = build()
    if res is None:
        # niente rete, mai: se la cache non c'e' si esce dicendolo, e chi chiama
        # (build_food.py) salta questo passo invece di rompersi.
        sys.exit(f"cache assente: {CACHE}\n"
                 f"  rigenerala con tools/sync_intervals.py (richiede rete e "
                 f"la chiave in ~/health-log/.env)")
    report(res)

    if args.check:
        print("\n(--check: niente scritto)")
        return
    common.write_csv(OUT, FIELDS, res["rows"])
    print(f"\n-> {OUT}")
    if args.export:
        p = Path(args.export)
        p.parent.mkdir(parents=True, exist_ok=True)
        common.write_csv(p, FIELDS, res["rows"])
        print(f"-> {p}")


if __name__ == "__main__":
    main()
