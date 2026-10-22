"""Validate the public diary export without reading or printing raw diary text."""
import datetime as dt
import json
import re
from pathlib import Path
from reflections_context import ROOT, TOPICS, EMOTIONS, WORDS

def check():
    data=json.loads((ROOT/'vita/come-sto/data.json').read_text(encoding='utf-8'))
    assert set(data)=={'method','model','generated','minimumEntries','topics','emotions','years','sportYears','audit','overall','literalWords'}, 'Unexpected public top-level fields'
    assert data['method']=='contextual-it-v2'
    assert data['model']=='Qwen3.5-9B Q4_K_M · locale'
    assert re.fullmatch(r'20\d{2}-\d{2}-\d{2}',data['generated'])
    assert data['minimumEntries']==3
    assert set(data['audit'])<={'documents','sourceWords','documentsWithoutText','duplicatesRemoved','pdfPages','pdfSourceWords','pdfDuplicateSections','pdfAddedSections','retainedWords','invalidDates','ambiguousHeadings','entries','analysedPassages','analysedWords','undatedWords','elapsedSeconds'}
    assert all(type(v) in (int,float) and v>=0 for v in data['audit'].values())
    assert data['topics']==TOPICS and data['emotions']==EMOTIONS
    assert data['audit']['analysedWords']==data['audit']['retainedWords'], 'Retained prose not fully analysed'
    assert data['audit']['analysedPassages']>=data['audit']['entries']
    assert '2019' in {r['period'] for r in data['years']}, '2019 must be recovered from the PDF'
    assert '2013' in {r['period'] for r in data['years']}, '2013 PDF supplement lost'
    assert '2023' in {r['period'] for r in data['years']}, 'English date headings lost'
    assert data['years']==sorted(data['years'],key=lambda r:r['period'])
    allowed_keys={'period','entries','passages','words','valence','activation','tonePassages','confidence','valenceRange','topics','emotions','keywords','literalWords'}
    assert 'months' not in data, 'Unneeded monthly detail must not be exported'
    for row in [data['overall'],*data['years']]:
        assert set(row)<=allowed_keys, 'Unexpected public fields'
        assert row['period']=='all' or re.fullmatch(r'20\d{2}(?:-\d{2})?',row['period'])
        assert row['entries']>=3
        assert row['valence'] is None or -1<=row['valence']<=1
        assert row['activation'] is None or 0<=row['activation']<=1
        for field,allowed in [('topics',TOPICS),('emotions',EMOTIONS),('keywords',WORDS)]:
            assert set(row[field])<=set(allowed)
            assert all(type(v) in (int,float) and 0<=v<=100 for v in row[field].values())
        if row['valence'] is not None:
            lo,hi=row['valenceRange'];assert -1<=lo<=row['valence']<=hi<=1
        assert set(row.get('literalWords',{}))<=set(WORDS)
    assert set(data['literalWords'])<=set(WORDS)
    for row in [data,*data['years']]:
        for value in row['literalWords'].values():
            assert set(value)=={'count','per1000'}
            assert type(value['count']) is int and value['count']>0
            assert type(value['per1000']) in (int,float) and 0<=value['per1000']<=1000
    for year,value in data['sportYears'].items():
        assert re.fullmatch(r'20\d{2}',year)
        assert set(value)=={'hours','activities'}
        assert all(type(v) in (int,float) and v>=0 for v in value.values())
    assert sum(r['words'] for r in data['years'])+data['audit']['undatedWords']==data['audit']['analysedWords']
    html=(ROOT/'vita/come-sto/index.html').read_text(encoding='utf-8')
    assert '<select' not in html and 'trends.js' in html and 'trends.css' in html
    assert 'come-sto/' in (ROOT/'tools/build_vita.py').read_text(encoding='utf-8')
    for name in ('trends.css','trends.js','data.json'):
        assert (ROOT/'vita/come-sto'/name).is_file()
    result=f"PASS: full retained-text coverage ({data['audit']['analysedWords']} words), {len(data['years'])} annual aggregates including PDF 2013/2019 and English-timestamp 2023, fixed-label public schema, score bounds, no period selector, generator navigation."
    with (ROOT/'REFLECTIONS_CHECKS.md').open('a',encoding='utf-8') as report:
        report.write(f'\n## {dt.date.today()} · public export verification\n- Command: `python tools/check_reflections.py`\n- {result}\n')
    print(result)

if __name__=='__main__':check()
