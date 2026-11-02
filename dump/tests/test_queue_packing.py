import importlib.util,pathlib,tempfile,unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parents[1]/'source/controller.py'
spec=importlib.util.spec_from_file_location('packing_controller',p);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class PackingTests(unittest.TestCase):
 def test_light_work_uses_headroom_while_one_heavy_fit_continues(self):
  heavy={'kind':'fit','method':'gmm','key':'newheavy'}
  light={'kind':'fit','method':'gaussian_nb','key':'light'}
  active={'kind':'fit','method':'random_forest','key':'originalRF'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[c.GIB],[c.GIB])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,[active],[heavy,light],8)['key'],'light')
 def test_first_heavy_lane_keeps_original_ready_order(self):
  heavy={'kind':'fit','method':'gmm','key':'newheavy'}
  light={'kind':'fit','method':'gaussian_nb','key':'light'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[],[])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,[],[heavy,light],8)['key'],'newheavy')
 def test_waiting_heavy_drains_new_light_fits_when_lane_is_empty(self):
  running=[{'kind':'fit','method':'logistic','key':'light-'+str(i)} for i in range(3)]
  heavy={'kind':'fit','method':'random_forest','key':'heavy'}
  light={'kind':'fit','method':'gaussian_nb','key':'light-next'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(16*c.GIB,[c.GIB]*3,[c.GIB]*3)),patch.object(c.os,'cpu_count',return_value=16):
   self.assertIsNone(c.admission_candidate(None,running,[heavy,light],13))
 def test_empty_lane_admits_heavy_before_ready_light(self):
  heavy={'kind':'fit','method':'random_forest','key':'heavy'}
  light={'kind':'fit','method':'gaussian_nb','key':'light'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[],[])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,[],[light,heavy],13)['key'],'heavy')
 def test_active_heavy_lane_preserves_light_packing_order(self):
  active={'kind':'eval','method':'random_forest','key':'heavy-eval'}
  heavy={'kind':'fit','method':'random_forest','key':'heavy-next'}
  light={'kind':'fit','method':'gaussian_nb','key':'light-next'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[4*c.GIB],[4*c.GIB])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,[active],[heavy,light],12)['key'],'light-next')
 def test_no_heavy_ready_keeps_light_admission(self):
  active=[{'kind':'fit','method':'logistic','key':'light-running'}]
  light={'kind':'fit','method':'gaussian_nb','key':'light-next'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[c.GIB],[c.GIB])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,active,[light],12)['key'],'light-next')

 def test_four_gib_e4_rf_still_counts_as_heavy_fit_lane(self):
  active={'kind':'fit','experiment':4,'method':'random_forest','route':'direct','rep':1,'condition':'A_half','train_key':'e4/rep_1/cohort/A_half','admission_reservation_bytes':4*c.GIB,'key':'active-e4-rf'}
  heavy={'kind':'fit','method':'random_forest','key':'next-heavy'}
  light={'kind':'fit','method':'gaussian_nb','key':'light'}
  with tempfile.TemporaryDirectory() as d,patch.object(c,'R',pathlib.Path(d)),patch.object(c,'bracketed_worker_memory',return_value=(30*c.GIB,[c.GIB],[c.GIB])),patch.object(c.os,'cpu_count',return_value=16):
   self.assertEqual(c.admission_candidate(None,[active],[heavy,light],12)['key'],'light')

if __name__=='__main__':unittest.main()
