"""Refresh one race's start-line context from Intervals.icu; publish aggregates only.
Usage: INTERVALS_KEY_FILE=... python scripts/fetch-context.py i201415820
The other races and all race streams are preserved. Race day is excluded from volume.
"""
import base64,json,os,sys,urllib.request
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
ROOT=Path(__file__).resolve().parents[1]

def aggregate(activities,wellness,race,detail):
    rd=date.fromisoformat(race['date']); start=rd-timedelta(days=56)
    runs={a['id']:a for a in activities if (a.get('type') or a.get('sport_type'))=='Run' and start.isoformat()<=str(a.get('start_date_local',''))[:10]<rd.isoformat()}
    totals=[0.0]*8
    for a in runs.values():
        ix=(date.fromisoformat(a['start_date_local'][:10])-start).days//7
        metres=a.get('distance') if a.get('distance') is not None else a.get('icu_distance')
        if metres is None: raise ValueError('Run distance missing; cannot claim complete volume')
        totals[ix]+=float(metres)/1000
    days={str(w['id']):w for w in wellness}
    def vals(field,a,b):
        return [float(v) for i in range(a,b+1) if (v:=days.get((rd-timedelta(days=i)).isoformat(),{}).get(field)) is not None]
    def mean(field,a,b):
        vs=vals(field,a,b);return round(sum(vs)/len(vs),1) if vs else None
    weight=weight_back=weight_source=None
    for i in range(8):
        w=days.get((rd-timedelta(days=i)).isoformat(),{}).get('weight')
        if w and float(w)>0:weight=round(float(w),2);weight_back=i;weight_source='wellness';break
    if weight is None and detail.get('icu_weight'):
        weight=detail['icu_weight'];weight_source='activity_profile'
    exact=days.get(rd.isoformat(),{})
    return {'raceDate':race['date'],'weightKg':weight,'weightDaysBefore':weight_back,'weightSource':weight_source,
      'restingHrMorning':exact.get('restingHR'),'restingHr7d':mean('restingHR',0,6),'restingHrBaseline28d':mean('restingHR',7,34),
      'hrvMorning':exact.get('hrv'),'hrv7d':mean('hrv',0,6),'hrvBaseline28d':mean('hrv',7,34),
      'temperatureC':detail.get('average_temp'),'temperatureSource':'device' if detail.get('average_temp') is not None else None,
      'runKmWeeksPrior8':[round(t,1) for t in totals],'runKmPerWeek8w':round(sum(totals)/8,1),'peakRunKmWeek8w':round(max(totals),1),
      'trainingVolumeSource':'Intervals.icu','runCount8w':len(runs),'raceAvgHr':race['avgHr'],'raceMaxHr':race['maxHr'],
      'earlyPaceSecKm':None,'latePaceSecKm':None,'lateFadeSecKm':None,'earlyHr':None,'lateHr':None,'lateHrDrift':None,
      'provenance':{'fetchedAt':datetime.now(timezone.utc).isoformat(),'windowStart':start.isoformat(),'windowEnd':(rd-timedelta(days=1)).isoformat(),'days':56,'raceDayExcluded':True,
        'restingHr7dSamples':len(vals('restingHR',0,6)),'hrv7dSamples':len(vals('hrv',0,6))}}

def main():
    rid=sys.argv[1];path=ROOT/'../../marathons/data/races.json';snapshot=json.loads(path.read_text(encoding='utf-8'));race=next(r for r in snapshot['races'] if r['id']==rid)
    key=os.environ.get('INTERVALS_API_KEY') or Path(os.environ['INTERVALS_KEY_FILE']).read_text(encoding='utf-8').strip()
    auth=base64.b64encode(('API_KEY:'+key).encode()).decode()
    def get(path):
        req=urllib.request.Request('https://intervals.icu/api/v1/'+path,headers={'Authorization':'Basic '+auth,'User-Agent':'marathon-atlas/1.0'})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    rd=date.fromisoformat(race['date']);query=f'oldest={rd-timedelta(days=56)}&newest={rd}'
    activities=get('athlete/0/activities?'+query);wellness=get('athlete/0/wellness?'+query);detail=get('activity/'+str(race.get('providerId') or rid))
    assert isinstance(activities,list) and isinstance(wellness,list)
    context=aggregate(activities,wellness,race,detail)
    assert len(context['runKmWeeksPrior8'])==8 and context['runCount8w']>0
    race['context']=context
    path.write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'race':race['city'],'context':context},indent=2))
if __name__=='__main__':main()
