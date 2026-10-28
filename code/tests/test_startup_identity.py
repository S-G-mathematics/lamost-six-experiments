import unittest
from unittest.mock import patch
import calibration_replay_supervisor as sup

class Child:
 def __init__(self,values=(None,)):self.values=list(values);self.calls=0
 def poll(self):
  self.calls+=1
  return self.values[0] if len(self.values)==1 else self.values.pop(0)
 def wait(self,timeout=None):return self.poll()

class StartupIdentityTests(unittest.TestCase):
 def run_wait(self,seeds,identities,child=None,grace=0.06,group=77):
  c=child or Child()
  tick=[0.0]
  def monotonic():return tick[0]
  def sleep(n):tick[0]+=n
  with patch.object(sup,"proc_seed",side_effect=seeds),patch.object(sup,"identity",side_effect=identities),patch.object(sup.os,"getpgid",return_value=group),patch.object(sup.os,"getuid",return_value=1000),patch.object(sup.time,"monotonic",side_effect=monotonic),patch.object(sup.time,"sleep",side_effect=sleep):
   return sup.wait_for_startup_identity(c,77,"/runtime","/script.py","/python",grace=grace)
 def test_transient_exec_metadata_then_exact_identity(self):
  self.assertEqual(self.run_wait([(123,1000),(123,1000)],[False,True]),(123,1000))
 def test_initial_proc_seed_unavailable_then_exact_identity(self):
  self.assertEqual(self.run_wait([None,(123,1000)],[True]),(123,1000))
 def test_foreign_initial_uid_rejected_immediately(self):
  with self.assertRaisesRegex(RuntimeError,"UID differs from launching supervisor"):
   self.run_wait([(123,999)],[True])
 def test_wrong_process_group_after_exact_identity_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"process group is invalid"):
   self.run_wait([(123,1000)],[True],group=88)
 def test_changed_start_ticks_rejected_before_second_identity_probe(self):
  with self.assertRaisesRegex(RuntimeError,"PID/start-tick/UID changed"):
   self.run_wait([(123,1000),(124,1000)],[False])
 def test_changed_uid_rejected_before_second_identity_probe(self):
  with self.assertRaisesRegex(RuntimeError,"PID/start-tick/UID changed"):
   self.run_wait([(123,1000),(123,1001)],[False])
 def test_child_exit_before_identity_is_terminal(self):
  with self.assertRaisesRegex(RuntimeError,"exited before startup identity"):
   self.run_wait([],[],Child((17,)))
 def test_startup_timeout_is_bounded_and_never_signals(self):
  c=Child()
  with patch.object(sup.os,"kill") as kill,patch.object(sup.os,"killpg") as killpg:
   with self.assertRaisesRegex(RuntimeError,"not verified within"):
    self.run_wait([(123,1000)]*10,[False]*10,c,grace=.04)
   kill.assert_not_called();killpg.assert_not_called()
  self.assertTrue(c.calls>1)

if __name__=="__main__":unittest.main(verbosity=2)
