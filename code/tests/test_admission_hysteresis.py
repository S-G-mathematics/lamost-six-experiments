import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

SRC=pathlib.Path(__file__).resolve().parents[1]/"source"/"controller.py"
spec=importlib.util.spec_from_file_location("staged_controller",SRC)
c=importlib.util.module_from_spec(spec)
with mock.patch.dict(sys.modules,{"admission_evidence":types.ModuleType("admission_evidence")}):
    spec.loader.exec_module(c)
G=c.GIB

class AdmissionHysteresisTests(unittest.TestCase):
    def test_new_admission_requires_growth_margin_plus_one_gib_buffer(self):
        candidate=2*G
        old_boundary=c.HOST_RESERVE+candidate+2*G
        self.assertFalse(c.memory_admission_ok(old_boundary,[],candidate))
        self.assertTrue(c.memory_admission_ok(old_boundary+G,[],candidate))
        self.assertEqual(c.ADMISSION_REQUIRED_MARGIN_BYTES,3*G)
        self.assertEqual(c.ADMISSION_SAFETY_BUFFER_BYTES,G)
    def test_unspent_reservations_are_still_counted(self):
        commitments=[(2*G,G)]
        base=c.HOST_RESERVE+G+2*G+2*G
        self.assertFalse(c.memory_admission_ok(base,commitments,2*G))
        self.assertTrue(c.memory_admission_ok(base+G,commitments,2*G))
    def test_existing_host_admission_floor_remains_eight_gib(self):
        self.assertEqual(c.ADMISSION_FLOOR,8*G)
        self.assertFalse(c.memory_admission_ok(8*G-1,[],G))
    def test_reclaim_threshold_remains_host_plus_unspent_plus_two_gib(self):
        debt=4*G
        boundary=c.HOST_RESERVE+debt+2*G
        self.assertFalse(c.needs_resource_reclaim(boundary,debt))
        self.assertTrue(c.needs_resource_reclaim(boundary-1,debt))
        self.assertEqual(c.ADAPTIVE_POLICY["commitment_growth_margin_gib"],2)
        self.assertEqual(c.ADAPTIVE_POLICY["admission_only_safety_buffer_gib"],1)
    def test_policy_does_not_change_worker_hard_cap_or_recovery(self):
        self.assertEqual(c.ADAPTIVE_POLICY["worker_memory_limit_gib"],10)
        self.assertEqual(c.ADAPTIVE_POLICY["trial_timeout_seconds"],600)
        self.assertEqual(c.ADAPTIVE_POLICY["phase_timeout_seconds"],600)
        self.assertEqual(c.ADAPTIVE_POLICY["termination_grace_seconds"],30)
        self.assertEqual(c.ADAPTIVE_POLICY["nested_threads"],1)
        self.assertEqual(c.ADAPTIVE_POLICY["max_operational_recoveries"],2)

if __name__=="__main__":unittest.main(verbosity=2)

