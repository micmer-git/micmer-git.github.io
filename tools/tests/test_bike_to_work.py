import sys,unittest,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sync_bike_to_work import recognize,merge_records,stream_columns
CFG=json.loads((Path(__file__).resolve().parents[1]/'bike-to-work.json').read_text(encoding='utf-8-sig'))
PLACES={'home':[45.8057,9.82316],'work':[45.66074,9.65227]}
A={'id':'test','type':'Ride','start_date_local':'2026-10-28T06:00:00','distance':54000,'calories':1500,'total_elevation_gain':600}
H,W=PLACES['home'],PLACES['work'];M=[45.73,9.74]
def stream():return {'time':[0,100,2500,2600,20000,20100,22500,22600],'latlng':[H,H,M,W,W,M,H,H],'distance':[0,0,25000,27000,27000,28000,54000,54000],'altitude':[500,500,220,220,220,225,500,500]}
class CommuteTests(unittest.TestCase):
 def test_combined_commute_requires_work_dwell_and_gets_both_directions(self):
  r=recognize(A,stream(),CFG,PLACES);self.assertEqual(set(r['day']['legs']),{'tw','th'});self.assertEqual(r['day']['legs']['tw']['elapsed'],2500);self.assertEqual(r['day']['legs']['tw']['c0'],21700);self.assertEqual(r['day']['cal'],1500)
 def test_merely_passing_work_does_not_count(self):
  s=stream();s['time']=[0,100,2500,2600,2700,2800,5200,5300];self.assertIsNone(recognize(A,s,CFG,PLACES))
 def test_one_way_and_run_supported(self):
  s={k:v[:4] for k,v in stream().items()};r=recognize({**A,'type':'Run'},s,CFG,PLACES);self.assertEqual(list(r['day']['legs']),['tw']);self.assertEqual(r['sport'],'Run')
 def test_wrong_endpoints_and_missing_gps_rejected(self):
  s=stream();s['latlng']=[M]*8;self.assertIsNone(recognize({**A,'name':'Bike to work'},s,CFG,PLACES));self.assertIsNone(recognize(A,{},CFG,PLACES))
 def test_short_or_wrong_direction_times_rejected(self):
  s={k:v[:4] for k,v in stream().items()};s['distance']=[0,0,1000,2000];self.assertIsNone(recognize(A,s,CFG,PLACES))
 def test_replay_upsert_and_edited_nonmatch(self):
  r=recognize(A,stream(),CFG,PLACES);self.assertEqual(merge_records([r],{'test'},[r]),[r]);self.assertEqual(merge_records([r],{'test'},[None]),[]);self.assertEqual(merge_records([r],set(),[]),[r])
 def test_latitude_longitude_split_stream(self):
  self.assertEqual(stream_columns([{'type':'latlng','data':[45,46],'data2':[9,10]}])['latlng'],[(45,9),(46,10)])
if __name__=='__main__':unittest.main()
