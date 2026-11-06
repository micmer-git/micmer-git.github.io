"""Run from any directory: python vita/spostamenti/guide/check.py [--live BASE_URL]."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote,urljoin
from urllib.request import urlopen
import json,zipfile,xml.etree.ElementTree as ET,csv,subprocess,sys,hashlib

B=Path(__file__).resolve().parent;ROOT=B.parents[2]
class Page(HTMLParser):
 def __init__(self,s):self.links=[];self.ids=set();self.h1=0;super().__init__();self.feed(s)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id'in a:self.ids.add(a['id'])
  if tag=='h1':self.h1+=1
  for key in ['src','href']:
   if key in a:self.links.append(a[key])

tracked=set(subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--name-only','HEAD'],text=True).splitlines())
def exists(p):return p.exists() or p.relative_to(ROOT).as_posix() in tracked
reg=json.loads((B/'index.json').read_text(encoding='utf-8'));travel=json.loads((B.parent/'data/travel.json').read_text(encoding='utf-8'));tripids={t['id'] for t in travel['trips']}
assert len(reg)==3 and {g['id'] for g in reg}=={'hong-kong-shenzhen','cuba','kyoto'}
totalTracks=0;totalStops=0
for g in reg:
 assert g['featured'] is True and g['tripId'] in tripids
 d=B/g['id'];data=json.loads((d/'data.json').read_text(encoding='utf-8'));rs=data['routes'];ss=data['stops'];totalTracks+=len(rs);totalStops+=len(ss)
 assert [r['id'] for r in rs]==g['activityIds'];assert data['totals']==g['totals']
 runs=[r for r in rs if 'Run' in r['sport']];tot=data['totals']
 assert tot['runs']==len(runs) and round(sum(r['km'] for r in runs),2)==tot['km']
 assert sum(r['ascent_m'] for r in runs)==tot['ascent_m'] and sum(r['moving_seconds'] for r in runs)==tot['moving_seconds']
 assert round(sum(r['km'] for r in rs if r['sport']=='Swim'),2)==tot['swim_km']
 assert len(ss)==g['stops'] and len({s['id'] for s in ss})==len(ss)
 geo=json.loads((d/'stops.geojson').read_text(encoding='utf-8'));assert len(geo['features'])==len(ss)
 csvrows=list(csv.DictReader((d/'stops.csv').open(encoding='utf-8-sig')));assert len(csvrows)==len(ss)
 kml=ET.parse(d/'stops.kml');assert sum(x.tag.endswith('Placemark') for x in kml.getroot().iter())==len(ss)
 for s,f,row in zip(ss,geo['features'],csvrows):
  assert f['geometry']['coordinates']==[s['lon'],s['lat']]
  assert float(row['Latitude'])==s['lat'] and float(row['Longitude'])==s['lon']
  assert s['kind'] in ['food','place'] and (d/s['photo']).is_file()
 hashes=set()
 for r in rs:
  p=d/r['gpx'];raw=p.read_bytes();hashes.add(hashlib.sha256(raw).hexdigest());elements=list(ET.fromstring(raw).iter());points=[e for e in elements if e.tag.endswith('trkpt')]
  assert len(points)>20 and not any(e.tag.endswith(('time','hr','cad','extensions')) for e in elements)
  assert len(r['points'])>20 and all(-180<p[0]<180 and -90<p[1]<90 for p in r['points'])
  assert 'gpx/'+r['id']+'.gpx'==r['gpx'] and r['url']=='https://www.strava.com/activities/'+r['id']
 assert len(hashes)==len(rs)==len(list((d/'gpx').glob('*.gpx')))
 with zipfile.ZipFile(d/(g['id']+'-gpx-soste.zip')) as z:
  assert z.testzip()is None and sum(n.startswith('gpx/')for n in z.namelist())==len(rs)
  assert set(z.namelist())=={r['gpx'] for r in rs}|{'stops.geojson','stops.kml','stops.csv','LEGGIMI.txt'}
  for n in z.namelist():assert z.read(n)==(d/n).read_bytes()
 html=(d/'index.html').read_text(encoding='utf-8');assert 'guide-data' in html and len(Page(html).ids)>=len(rs)+len(ss)
for p in B.rglob('*.html'):
 s=p.read_text(encoding='utf-8');page=Page(s);assert page.h1==1
 assert not any(bad in s for bad in ['Ã','â€','Â·','PRIVATE','photo.google','michelemerelli.8@']),p
 for link in page.links:
  u=urlsplit(link)
  if u.scheme or u.netloc:continue
  path=unquote(u.path);target=(ROOT/path.lstrip('/')) if path.startswith('/') else p.parent/path
  target=target.resolve()
  if not path:target=p
  if path.endswith('/'):target=target/'index.html'
  assert exists(target),(p,link,target)
  if not path and u.fragment:assert u.fragment in page.ids,(p,link)
for p in B.rglob('*'):
 if p.is_file():assert p.suffix.lower() in {'.html','.css','.js','.json','.webp','.gpx','.geojson','.kml','.csv','.txt','.zip','.py'},p
assert totalTracks==18 and totalStops==21
app=(B.parent/'app.js').read_text(encoding='utf-8');assert 'data-featured' in app and 'filter === "selezionati"'in app and 'guide/index.json' in app
assert 'data-filter="selezionati"'in(B.parent/'index.html').read_text(encoding='utf-8')
if '--live'in sys.argv:
 base=sys.argv[sys.argv.index('--live')+1].rstrip('/')+'/'
 for f in [B/'index.html',B/'index.json']+[B/g['id']/n for g in reg for n in ['index.html','data.json',g['id']+'-gpx-soste.zip']]:
  rel=f.relative_to(B).as_posix();remote=urlopen(base+rel).read();assert remote==f.read_bytes(),rel
 print('Live content matches the verified local guide files.')
print(f'PASS: {len(reg)} guides, {totalTracks} recorded tracks, {totalStops} consistent stop pins; links, stats, GPX privacy and ZIP contents verified.')
