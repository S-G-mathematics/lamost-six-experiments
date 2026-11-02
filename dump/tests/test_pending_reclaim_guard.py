import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BASE=Path(__file__).resolve().parents[1]
SRC=BASE/"source"
sys.path.insert(0,str(SRC))
spec=importlib.util.spec_from_file_location("staged_cleanup_grace_controller",SRC/"controller.py")
c=importlib.util.module_from_spec(spec);sys.modules[spec.name]=c;spec.loader.exec_module(c)
G=c.GIB

def pending(key="pending",age=5):
 return {"key":key,"status":"running","adaptive_policy_revision":c.ADAPTIVE_REVISION,
  "adaptive_emergency_term_epoch":time.time()-age,"attempts":[{"attempt_id":"pending-attempt"}],
  "pid":123,"process_start_ticks":"100"}

def active(key="active"):
 return {"key":key,"status":"running","adaptive_policy_revision":c.ADAPTIVE_REVISION,
  "attempts":[{"attempt_id":"active-attempt"}],"pid":456,"process_start_ticks":"200"}

class PendingReclaimGuardTests(unittest.TestCase):
 def setUp(self):
  self.old_backoff=c.EMERGENCY_BACKOFF_UNTIL;c.EMERGENCY_BACKOFF_UNTIL=0
 def tearDown(self):c.EMERGENCY_BACKOFF_UNTIL=self.old_backoff

 def test_verified_pending_grace_defers_second_reclaim_above_critical_floor(self):
  prior=pending();candidate=active();tasks={prior["key"]:prior,candidate["key"]:candidate}
  with mock.patch.object(c,"bracketed_worker_memory",return_value=(7*G,[0,0],[0,0])), \
       mock.patch.object(c,"worker_reservation_bytes",return_value=10*G), \
       mock.patch.object(c,"needs_resource_reclaim",return_value=True), \
       mock.patch.object(c,"verified_adaptive_worker",return_value=True), \
       mock.patch.object(c,"terminate_verified") as terminate, \
       mock.patch.object(c,"atomic"),mock.patch.object(c,"put"),mock.patch.object(c,"event"):
   result=c.emergency_interrupt_one(object(),tasks)
  self.assertIsNone(result["interrupted_key"])
  self.assertEqual(result["pending_termination_keys"],[prior["key"]])
  terminate.assert_not_called()

 def test_critical_pressure_below_six_gib_allows_next_verified_target(self):
  prior=pending();candidate=active();tasks={prior["key"]:prior,candidate["key"]:candidate}
  with mock.patch.object(c,"bracketed_worker_memory",return_value=(5*G,[0,0],[0,0])), \
       mock.patch.object(c,"worker_reservation_bytes",return_value=10*G), \
       mock.patch.object(c,"needs_resource_reclaim",return_value=True), \
       mock.patch.object(c,"verified_adaptive_worker",return_value=True), \
       mock.patch.object(c,"terminate_verified") as terminate, \
       mock.patch.object(c,"atomic"),mock.patch.object(c,"put"),mock.patch.object(c,"event"):
   result=c.emergency_interrupt_one(object(),tasks)
  self.assertEqual(result,candidate["key"])
  terminate.assert_called_once_with(candidate["pid"],candidate["process_start_ticks"])

 def test_recent_cleanup_flag_defers_even_when_pid_is_stale(self):
  prior=pending();candidate=active()
  with mock.patch.object(c,"alive",return_value=False):
   self.assertFalse(c.verified_adaptive_worker(prior))
  tasks={prior["key"]:prior,candidate["key"]:candidate}
  with mock.patch.object(c,"bracketed_worker_memory",return_value=(7*G,[0,0],[0,0])), \
       mock.patch.object(c,"worker_reservation_bytes",return_value=10*G), \
       mock.patch.object(c,"needs_resource_reclaim",return_value=True), \
       mock.patch.object(c,"verified_adaptive_worker",return_value=False), \
       mock.patch.object(c,"orphan_phases",return_value=[]), \
       mock.patch.object(c,"terminate_verified") as terminate, \
       mock.patch.object(c,"atomic"),mock.patch.object(c,"put"),mock.patch.object(c,"event"):
   result=c.emergency_interrupt_one(object(),tasks)
  self.assertIsNone(result["interrupted_key"])
  self.assertEqual(result["pending_termination_keys"],[prior["key"]])
  terminate.assert_not_called()

 def test_without_pending_grace_normal_reclaim_still_selects_target(self):
  candidate=active();tasks={candidate["key"]:candidate}
  with mock.patch.object(c,"bracketed_worker_memory",return_value=(7*G,[0],[0])), \
       mock.patch.object(c,"worker_reservation_bytes",return_value=10*G), \
       mock.patch.object(c,"needs_resource_reclaim",return_value=True), \
       mock.patch.object(c,"verified_adaptive_worker",return_value=True), \
       mock.patch.object(c,"terminate_verified") as terminate, \
       mock.patch.object(c,"atomic"),mock.patch.object(c,"put"),mock.patch.object(c,"event"):
   result=c.emergency_interrupt_one(object(),tasks)
  self.assertEqual(result,candidate["key"])
  terminate.assert_called_once()

 def test_after_grace_check_running_force_kills_only_verified_pending_task(self):
  t=pending(age=31);t["result_path"]="/tmp/lamost-nonexistent-worker-result-fixture"
  with mock.patch.object(c,"process_table",return_value={}), \
       mock.patch.object(c,"orphan_phases",return_value=[]), \
       mock.patch.object(c,"alive",return_value=True), \
       mock.patch.object(c,"verified_adaptive_worker",return_value=True), \
       mock.patch.object(c,"terminate_verified") as terminate:
   c.check_running(object(),{t["key"]:t})
  terminate.assert_called_once_with(t["pid"],t["process_start_ticks"],force=True)


 def test_live_orphan_defers_with_parent_absent(self):
  t=pending();orphan=(789,"321",Path("/tmp/orphan"))
  with mock.patch.object(c,"verified_adaptive_worker",return_value=False), mock.patch.object(c,"orphan_phases",return_value=[orphan]), mock.patch.object(c,"alive",return_value=True):
   self.assertEqual(c.pending_reclaim_in_grace({"p":t},7*G,time.time()),["pending"])

 def test_stale_orphan_still_defers_during_cleanup_grace(self):
  t=pending();orphan=(789,"321",Path("/tmp/orphan"))
  with mock.patch.object(c,"verified_adaptive_worker",return_value=False), mock.patch.object(c,"orphan_phases",return_value=[orphan]), mock.patch.object(c,"alive",return_value=False):
   self.assertEqual(c.pending_reclaim_in_grace({"p":t},7*G,time.time()),["pending"])

 def test_live_orphan_does_not_defer_below_critical_floor(self):
  t=pending();orphan=(789,"321",Path("/tmp/orphan"))
  with mock.patch.object(c,"verified_adaptive_worker",return_value=False), mock.patch.object(c,"orphan_phases",return_value=[orphan]), mock.patch.object(c,"alive",return_value=True):
   self.assertEqual(c.pending_reclaim_in_grace({"p":t},5*G,time.time()),[])

 def test_parent_and_orphan_gone_but_registry_still_running_defers(self):
  t=pending()
  with mock.patch.object(c,"verified_adaptive_worker",return_value=False), mock.patch.object(c,"orphan_phases",return_value=[]):
   self.assertEqual(c.pending_reclaim_in_grace({"p":t},7*G,time.time()),["pending"])

 def test_no_flag_or_expired_flag_does_not_defer(self):
  noflag=active("no-flag");expired=pending(age=31)
  self.assertEqual(c.pending_reclaim_in_grace({"n":noflag,"e":expired},7*G,time.time()),[])

 def test_future_term_timestamp_does_not_defer(self):
  t=pending();t["adaptive_emergency_term_epoch"]=time.time()+1
  self.assertEqual(c.pending_reclaim_in_grace({"p":t},7*G,time.time()),[])

if __name__=="__main__":unittest.main()
