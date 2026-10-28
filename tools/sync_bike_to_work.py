#!/usr/bin/env python3
"""GPS-based incremental commute sync; original archive is never rewritten.
Only confirmed home/work legs and cropped/downsampled routes are published.
Network failure aborts before writing; recent 14 days are rechecked for edits.
"""
import argparse,base64,json,math,os,re,sys
from pathlib import Path
from datetime import date,datetime,timedelta
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
from sync_intervals import haversine,get_api_key
HERE=Path(__file__).resolve().parent

def const(text,name):
    m=re.search(r'const\s+'+re.escape(name)+r'\s*=\s*',text)
    if not m:raise ValueError('Missing '+name)
    return json.JSONDecoder().raw_decode(text[m.end():])[0]

def stream_columns(raw):
    out={}
    for s in raw:
        key=s['type'];data=s.get('data',[])
        if key=='latlng' and s.get('data2') is not None:data=list(zip(data,s['data2']))
        out[key]=data
    return out

def recognize(activity,st,cfg,places):
    tm=st.get('time',[]);gps=st.get('latlng',[]);dist=st.get('distance',[])
    if not tm or len(gps)!=len(tm) or len(dist)!=len(tm):return None
    if any(not isinstance(t,(int,float)) for t in tm) or any(b<a for a,b in zip(tm,tm[1:])):raise ValueError('Invalid time stream')
    zones=[]
    for p in gps:
        if not isinstance(p,(list,tuple)) or len(p)!=2 or any(v is None for v in p):zones.append(None);continue
        near=[(haversine(p,places[k]),k) for k in ('home','work')]
        metres,zone=min(near);zones.append(zone if metres<=cfg['radius_m'] else None)
    # Only endpoint-confirmed journeys. Merely passing the office during a ride is insufficient.
    if zones[0] is None or zones[-1] is None:return None
    visits=[]
    for i,z in enumerate(zones):
        if z is None:continue
        if visits and visits[-1][0]==z:visits[-1][2]=i
        else:visits.append([z,i,i])
    if len(visits)<2:return None
    if zones[0]==zones[-1]:
        work=[v for v in visits if v[0]=='work']
        if not work or max(tm[v[2]]-tm[v[1]] for v in work)<cfg['minimum_work_dwell_s']:return None
    stamp=datetime.fromisoformat(activity['start_date_local']);clock=stamp.hour*3600+stamp.minute*60+stamp.second
    legs={};segments=[]
    def val(key,i):
        series=st.get(key,[]);return series[i] if i<len(series) and isinstance(series[i],(int,float)) else None
    for a,b in zip(visits,visits[1:]):
        if a[0]==b[0]:continue
        i,j=a[2],b[1];elapsed=tm[j]-tm[i]
        if not isinstance(dist[i],(int,float)) or not isinstance(dist[j],(int,float)):continue
        metres=dist[j]-dist[i]
        if not(cfg['minimum_leg_m']<=metres<=cfg['maximum_leg_m'] and cfg['minimum_leg_s']<=elapsed<=cfg['maximum_leg_s']):continue
        direction='tw' if a[0]=='home' else 'th'
        if direction in legs:continue # existing page represents at most one leg each way per day
        moving=ascent=0;weighted={'heartrate':[0,0],'watts':[0,0]}
        for k in range(i+1,j+1):
            dt=tm[k]-tm[k-1]
            if dt<=0:continue
            if dist[k] is None or dist[k-1] is None:return None
            speed=(dist[k]-dist[k-1])/dt
            if speed>.5:moving+=dt
            aa,bb=val('altitude',k-1),val('altitude',k)
            if aa is not None and bb is not None:ascent+=max(0,bb-aa)
            for key in weighted:
                v=val(key,k)
                if v is not None:weighted[key][0]+=v*dt;weighted[key][1]+=dt
        avg=lambda key:round(weighted[key][0]/weighted[key][1]) if weighted[key][1] else 0
        legs[direction]={'elapsed':round(elapsed),'moving':round(moving),'dist':round(metres),'ascent':round(ascent),'hr':avg('heartrate'),'w':avg('watts'),'c0':clock+tm[i],'c1':clock+tm[j]}
        segments.append((i,j))
    if not legs:return None
    track=[]
    for i,j in segments:
        last=-1e9
        for k in range(i,j+1):
            if k!=j and tm[k]-last<40:continue
            if zones[k] is None and (not isinstance(gps[k],(list,tuple)) or any(v is None for v in gps[k])):continue
            track.append([clock+tm[k],round(gps[k][0],5),round(gps[k][1],5),round(val('altitude',k) or 0)])
            last=tm[k]
    day=stamp.date().isoformat()
    row={'d':day,'wd':stamp.weekday(),'legs':legs,'cal':round(activity.get('calories') or activity.get('icu_calories') or 0),'km':round(float(activity.get('distance') or dist[-1])/1000,1),'gain':round(activity.get('total_elevation_gain') or 0),'name':str(activity.get('name') or 'Commute'),'acts':[str(activity['id'])]}
    return {'id':str(activity['id']),'sport':activity.get('type'),'day':row,'track':track}

def merge_records(previous,scanned_ids,results):
    # Replace re-scanned matches, including removing an edited activity that no longer matches.
    keep={r['id']:r for r in previous if r['id'] not in scanned_ids}
    keep.update({r['id']:r for r in results if r is not None})
    return sorted(keep.values(),key=lambda r:(r['day']['d'],r['id']))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',default=str(HERE/'bike-to-work.json'));ap.add_argument('--since');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    config=Path(args.config).resolve();cfg=json.loads(config.read_text(encoding='utf-8-sig'));source=(config.parent/cfg['data_file']).resolve();output=(config.parent/cfg['output_file']).resolve()
    text=source.read_text(encoding='utf-8');places=const(text,'CFG');days=const(text,'DAYS');runs=const(text,'RUNS')
    previous=const(output.read_text(encoding='utf-8'),'AUTO_SYNC') if output.exists() else {'records':[]}
    today=date.today();anchor=previous.get('checkedThrough') or max(r['d'] for r in days)
    since=args.since or (date.fromisoformat(anchor)-timedelta(days=cfg['lookback_days'])).isoformat()
    key=get_api_key();auth=base64.b64encode(('API_KEY:'+key).encode()).decode()
    def get(path):
        req=Request('https://intervals.icu/api/v1/'+path,headers={'Authorization':'Basic '+auth,'User-Agent':'micmer-bike-commute-sync/1.0'})
        with urlopen(req,timeout=60) as response:return json.load(response)
    activities=get(f"athlete/{cfg['athlete_id']}/activities?oldest={since}&newest={today}")
    if not isinstance(activities,list):raise ValueError('Unexpected activity response')
    baseids={aid for d in days+runs for aid in d['acts']}
    known_strava={str(aid)[1:] for aid in baseids if str(aid).startswith(('s','r'))}
    def candidate(a):
        if str(a['id']) in baseids or str(a.get('strava_id')) in known_strava:return False
        return a.get('type') in ('Ride','Run') and float(a.get('distance') or 0)>=cfg['minimum_leg_m']
    candidates=[a for a in activities if candidate(a)]
    def process(a):
        types=a.get('stream_types')
        if types is not None and 'latlng' not in types:return None
        # Endpoint metadata can reject far-away races without downloading their GPS.
        for field in ('start_latlng','end_latlng'):
            p=a.get(field)
            if isinstance(p,list) and len(p)==2 and all(isinstance(v,(float,int)) for v in p):
                if min(haversine(p,places[z]) for z in ('home','work'))>cfg['radius_m']:return None
        raw=get(f"activity/{a['id']}/streams.json?types=time,latlng,distance,altitude,heartrate,watts")
        if not isinstance(raw,list):raise ValueError('Unexpected streams response')
        record=recognize(a,stream_columns(raw),cfg,places)
        if record and not (a.get('calories') or a.get('icu_calories')):
            detail=get(f"activity/{a['id']}")
            calories=detail.get('calories') or detail.get('icu_calories')
            if calories is not None:record['day']['cal']=round(calories)
            else:record['day']['missingCalories']=True
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(process,candidates))
    scanned={str(a['id']) for a in activities}
    # Also remove deleted matches only inside the successfully fetched date window.
    scanned.update(r['id'] for r in previous['records'] if since<=r['day']['d']<=today.isoformat())
    records=merge_records(previous['records'],scanned,results)
    payload={'schemaVersion':1,'checkedThrough':today.isoformat(),'source':'Intervals.icu GPS','radiusM':cfg['radius_m'],'records':records}
    encoded='// Automatic GPS-confirmed commute additions. Original archive remains in _data.js.\nconst AUTO_SYNC='+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n'
    print(json.dumps({'since':since,'through':str(today),'activities':len(activities),'candidates':len(candidates),'matchedNow':len([r for r in results if r]),'totalMatched':len(records),'dates':[r['day']['d'] for r in records]},ensure_ascii=True))
    if not args.dry_run and (not output.exists() or output.read_text(encoding='utf-8')!=encoded):
        temporary=output.with_suffix('.tmp');temporary.write_text(encoded,encoding='utf-8');temporary.replace(output)
if __name__=='__main__':main()
