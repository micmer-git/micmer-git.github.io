# Spostamenti

Pagina statica e scrollytelling di `/vita/spostamenti/`.

## Rigenerare i dati

Il Takeout Google Timeline resta locale e non va copiato nel repository. Servono
anche l'elenco aeroporti di [OurAirports](https://ourairports.com/data/) e Python
con `geonamescache`:

```powershell
pip install -r vita/spostamenti/requirements.txt
python tools/build_spostamenti.py --timeline C:\percorso\Timeline.json --airports C:\percorso\airports.csv
```

Il comando scrive `data/travel.json`, il manifest di provenienza
`data/source-manifest.json` e aggiorna la tessera nell'indice `/vita/`.
Il globo usa `data/countries-110m.json`, una copia di world-atlas/Natural Earth.

## Definizioni

- **CO₂e voli:** km delle tratte Timeline × 0,14253 kg CO₂e/passeggero-km,
  fattore UK Government 2026 “international average passenger, with RF”.
- **CO₂e auto:** km validati × 0,20990 kg CO₂e/km. È la somma del fattore
  diretto per auto media a carburante ignoto (0,16591) e del well-to-tank
  (0,04399), UK Government 2026.
- **Auto:** soli segmenti `IN_PASSENGER_VEHICLE` compatibili con durata,
  velocità e distanza tra gli estremi; gli errori impossibili sono scartati.
- **Mezze:** attività Intervals/Strava di corsa da almeno 21,0 km e non oltre
  60 km, aggregate per mese.
- **Sorsi e Bocconi:** date distinte associate allo stesso Place ID entro 25 m
  dal punto pubblico del locale.
- **Viaggi:** memorie di viaggio Google da almeno 120 km, più gruppi di voli dal
  2025 (quando le memorie non sono più presenti nell'export).

## Privacy

`Timeline.json`, casa, lavoro, Place ID e percorsi GPS non vengono pubblicati. Le
coordinate in `travel.json` sono città o aeroporti pubblici e sono arrotondate a
due decimali. Il manifest conserva hash, dimensione e copertura del file sorgente
senza esporne il contenuto.
