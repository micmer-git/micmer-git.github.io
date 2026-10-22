"""Local-only diary analysis. Raw text never written; only allowlisted aggregates leave memory."""
import argparse, collections, csv, datetime as dt, hashlib, io, json, re, statistics, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MONTHS = 'gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre'.split()
THEMES = {
    'Movimento': 'sport corsa correre bici bicicletta ciclismo nuoto nuotare allenamento palestra camminata passeggiata gara',
    'Recupero': 'riposo recupero dormire sonno stanchezza stanco stanca fatica riposare',
    'Nutrizione': 'cibo mangiare colazione pranzo cena alimentazione fame cucina cucinare',
    'Lavoro e studio': 'lavoro lavorare ufficio progetto progetti studio studiare imparare ricerca',
    'Relazioni': 'amici amicizia famiglia insieme compagnia incontro incontri affetto',
    'Natura e tempo libero': 'montagna mare natura viaggio viaggi vacanza vacanze musica leggere libro libri',
    'Riflessione': 'pensare pensiero pensieri riflettere cambiamento futuro scelta scelte obiettivo obiettivi',
}
POS = set('felice felicità contento contenta sereno serena serenità gioia entusiasmo soddisfatto soddisfatta gratitudine tranquillo tranquilla'.split())
NEG = set('triste tristezza ansia ansioso ansiosa paura preoccupato preoccupata rabbia arrabbiato arrabbiata deluso delusa frustrato frustrata'.split())
DATE = re.compile(r'\b(\d{1,2})\s+('+'|'.join(MONTHS)+r')(?:\s+(20\d{2}))?\b', re.I)

def build(source):
    entries, seen = [], set()
    audit = collections.Counter()
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            if not name.lower().endswith('.docx'): continue
            audit['documents'] += 1
            years = re.findall(r'20\d{2}', name)
            default_year = int(years[0]) if len(years) == 1 else None
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as doc:
                tree = ET.fromstring(doc.read('word/document.xml'))
            paragraphs = [''.join(t.text or '' for t in p.findall('.//{*}t')).strip() for p in tree.findall('.//{*}p')]
            explicit = {int(m.group(3)) for p in paragraphs if len(p)<100 for m in DATE.finditer(p) if m.group(3)}
            # A file title is not a reliable year when explicit headings disagree.
            if explicit and default_year and explicit != {default_year}: default_year = None
            current, parts = None, []
            def flush():
                text = ' '.join(parts).lower()
                if not current or len(text.split()) < 20: return
                digest = hashlib.sha256(text.encode()).hexdigest()
                if digest in seen:
                    audit['duplicates_removed'] += 1
                    return
                seen.add(digest)
                tokens = re.findall(r"[a-zàèéìòù]+", text)
                counts = collections.Counter(tokens)
                positive = sum(counts[w] for w in POS)
                negative = sum(counts[w] for w in NEG)
                entries.append({'date': current, 'themes': {k: sum(counts[w] for w in v.split()) for k,v in THEMES.items()}, 'positive':positive,'negative':negative})
            for p in paragraphs:
                m = DATE.search(p) if len(p)<100 else None
                if m:
                    year = int(m.group(3)) if m.group(3) else default_year
                    if year:
                        try: date = dt.date(year, MONTHS.index(m.group(2).lower())+1,int(m.group(1)))
                        except ValueError: continue
                        flush(); current = date; parts = []; continue
                    flush(); current=None; parts=[]; audit['ambiguous_headings']+=1
                elif re.search(r'\b20\d{2}\b',p) and len(p)<12:
                    flush(); current=None; parts=[]
                parts.append(p)
            flush()
    monthly = collections.defaultdict(list)
    for e in entries: monthly[e['date'].strftime('%Y-%m')].append(e)
    activities = collections.defaultdict(list)
    for filename in ('activities.csv','activities_backfill.csv'):
        with (ROOT/'tools/food/data'/filename).open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f): activities[row['date'][:7]].append(row)
    rows=[]
    for month, group in sorted(monthly.items()):
        if len(group)<3: audit['months_suppressed']+=1; continue
        signals=[(e['positive']-e['negative'])/(e['positive']+e['negative']) for e in group if e['positive']+e['negative']>=2]
        sport=activities.get(month,[])
        rows.append({'month':month,'entries':len(group),'themes':{k:round(100*sum(e['themes'][k]>0 for e in group)/len(group),1) for k in THEMES},'tone':round(statistics.mean(signals),3) if len(signals)>=3 else None,'toneEntries':len(signals),'sportHours':round(sum(float(a['moving_time_s'] or 0) for a in sport)/3600,1) if sport else None})
    result={'method':'allowlist-it-v1','minimumEntries':3,'themes':list(THEMES),'keywords':{k:v.split() for k,v in THEMES.items()},'months':rows,'audit':dict(audit),'datedEntries':len(entries)}
    out=ROOT/'vita/come-sto/data.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=ROOT/'REFLECTIONS_CHECKS.md'
    with report.open('a',encoding='utf-8') as f:
        f.write(f'\n## {dt.date.today()} · local extraction\n- Command: `python tools/build_reflections.py <local ZIP>`\n- DOCX: {audit["documents"]}; dated entries: {len(entries)}; displayed months: {len(rows)}; suppressed months: {audit["months_suppressed"]}; duplicates removed: {audit["duplicates_removed"]}.\n- Verdict: only fixed topic labels/counts and monthly lexical tone exported; no names, quotations, raw text, document names or entry dates. PDF not processed (possible duplicate). Dates inferred from single-year filenames only when explicit headings agree; ambiguous sections excluded. Historical prose and sparse headings limit accuracy.\n')
    print(json.dumps({'documents':audit['documents'],'datedEntries':len(entries),'months':len(rows),'toneMonths':sum(r['tone'] is not None for r in rows)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);build(parser.parse_args().source)
