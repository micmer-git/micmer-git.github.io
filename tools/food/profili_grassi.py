# -*- coding: utf-8 -*-
"""Di che grasso e' fatto ogni alimento del catalogo.

Il database interno conosceva solo `satfat_g`. Mono, poli e trans esistevano solo nei
giorni pesati su Cronometer — quattro al mese — quindi il riquadro «Di che grasso»
viveva su un pugno di giornate e restava vuoto in tutte le altre.

Qui si ricostruiscono, e la parola giusta e' RICOSTRUITI: non sono misure. Ogni voce
porta le frazioni del grasso TOTALE che sono monoinsature, polinsature e trans, prese
dai profili noti di quell'alimento o della sua famiglia. I saturi restano quelli che
c'erano: non si toccano.

Tre scelte che tengono onesto il conto:
  1. La somma sat+mono+poli+trans NON viene forzata a 1. Il grasso alimentare e'
     trigliceridi: circa il 5% della massa e' glicerolo e non e' un acido grasso.
     Quel resto resta «non classificato», che e' anche il posto dove finisce
     l'imprecisione del profilo, invece di essere spalmato sugli insaturi.
  2. Se sat + mono + poli + trans sfora il grasso totale, mono e poli si scalano
     insieme fino a rientrare — mai i saturi, che sono il dato di partenza.
  3. I trans dei ruminanti (burro, formaggi, manzo, agnello) NON sono zero e non
     vanno confusi con quelli industriali: sono il 3-6% del grasso, sono naturali,
     e toglierli avrebbe detto una cosa falsa in nome di un numero piu' bello.
"""

# (mono, poli, trans) come frazioni del grasso TOTALE
PROFILI = {
    "olio_evo":                 (.73, .11, .000),
    "burro":                    (.26, .04, .040),   # trans di ruminante, naturali
    "noci":                     (.14, .72, .000),
    "mandorle":                 (.63, .25, .000),
    "pesto_genovese":           (.60, .14, .000),   # quasi tutto olio d'oliva
    "avocado":                  (.67, .12, .000),
    "olive":                    (.73, .08, .000),
    "cioccolato_fondente_85":   (.33, .03, .000),   # stearico e palmitico
    "cioccolato_fondente_50":   (.33, .03, .000),
    "cacao_100":                (.33, .03, .000),
    "guanciale":                (.45, .10, .005),
    "bacon":                    (.45, .10, .005),
    "salame":                   (.45, .10, .005),
    "salsiccia":                (.45, .10, .005),
    "carne_maiale":             (.45, .10, .005),
    "prosciutto_crudo":         (.45, .10, .005),
    "prosciutto_cotto":         (.45, .10, .005),
    "bistecca_manzo":           (.44, .04, .050),   # ruminante
    "carne_macinata_manzo":     (.44, .04, .050),
    "arrosticini":              (.40, .06, .060),   # pecora, ruminante
    "bresaola":                 (.44, .04, .050),
    "ragu_cervo":               (.44, .06, .020),
    "petto_pollo":              (.40, .20, .000),
    "uovo_intero":              (.38, .14, .000),
    "salmone":                  (.35, .30, .000),
    "salmone_affumicato":       (.35, .30, .000),
    "pesce_bianco":             (.28, .34, .000),
    "tonno_scatola":            (.25, .35, .000),
    "vitello_tonnato":          (.45, .35, .000),   # la salsa e' maionese: olio di semi
    "patatine_fritte":          (.35, .45, .000),   # olio di semi
    "granola":                  (.35, .35, .000),
    "cumino_semi":              (.55, .30, .000),
    "curry_polvere":            (.45, .35, .000),
    "burro_arachidi_sgrassato": (.50, .30, .000),
    "croissant_vuoto":          (.35, .12, .020),
    "cornetto_crema":           (.35, .12, .020),
    "cinnamon_roll":            (.35, .12, .020),
    "panettone":                (.35, .12, .020),
    "babka_mandorle":           (.38, .14, .015),
    "cheesecake":               (.30, .05, .035),   # base latticini
    "panna_montata":            (.28, .04, .040),
    "filetto_crosta":           (.42, .08, .030),
}

# quando l'alimento non e' in elenco, la sua famiglia
PER_GRUPPO = {
    "grassi":      (.60, .20, .000),
    "latticini":   (.28, .04, .040),   # ruminante
    "proteine":    (.42, .14, .010),
    "cereali":     (.30, .35, .005),
    "legumi":      (.20, .45, .000),
    "verdura":     (.25, .35, .000),
    "frutta":      (.35, .25, .000),
    "dolci":       (.34, .12, .015),
    "spezie":      (.45, .35, .000),
    "bevande":     (.28, .05, .030),
    "integratori": (.30, .30, .000),
}
DEFAULT = (.35, .25, .005)


def spezza(food_id, gruppo, fat_g, satfat_g):
    """Torna (mono_g, poli_g, trans_g) per 100 g, coerenti col grasso totale."""
    if not fat_g or fat_g <= 0:
        return 0.0, 0.0, 0.0
    mo, po, tr = PROFILI.get(food_id) or PER_GRUPPO.get(gruppo) or DEFAULT
    mono, poli, trans = fat_g * mo, fat_g * po, fat_g * tr
    sat = max(0.0, satfat_g or 0.0)
    # il tetto: gli acidi grassi non possono superare il 96% della massa del grasso,
    # il resto e' glicerolo. Se si sfora, si scalano mono e poli, mai i saturi.
    tetto = fat_g * 0.96 - sat - trans
    somma = mono + poli
    if tetto < 0:
        mono = poli = 0.0
    elif somma > tetto:
        k = tetto / somma
        mono, poli = mono * k, poli * k
    return round(mono, 2), round(poli, 2), round(trans, 3)
