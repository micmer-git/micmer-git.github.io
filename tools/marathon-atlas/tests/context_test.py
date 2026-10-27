import importlib.util,unittest
from datetime import date,timedelta
from pathlib import Path
spec=importlib.util.spec_from_file_location('context',Path(__file__).parents[1]/'scripts/fetch-context.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class ContextTests(unittest.TestCase):
 def test_window_excludes_race_day_deduplicates_and_uses_eight_weeks(self):
  race={'date':'2026-10-25','avgHr':165,'maxHr':185}
  first={'id':'a','type':'Run','start_date_local':'2026-08-30T10:00:00','distance':10000}
  last={'id':'b','type':'Run','start_date_local':'2026-10-24T10:00:00','distance':5000}
  excluded=[{'id':'c','type':'Run','start_date_local':'2026-10-25T10:00:00','distance':42000},{'id':'d','type':'Ride','start_date_local':'2026-10-24T10:00:00','distance':90000}]
  c=module.aggregate([first,first,last]+excluded,[{'id':'2026-10-23','weight':74}],race,{})
  self.assertEqual(c['runCount8w'],2);self.assertEqual(c['runKmWeeksPrior8'],[10,0,0,0,0,0,0,5]);self.assertEqual(c['weightDaysBefore'],2);self.assertIsNone(c['restingHrMorning'])
if __name__=='__main__':unittest.main()
