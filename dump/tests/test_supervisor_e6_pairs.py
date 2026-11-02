import importlib.util
import unittest
from pathlib import Path

_VALIDATION = Path(__file__).resolve().parents[1] / "source"
_spec = importlib.util.spec_from_file_location("staged_calibration_replay_supervisor", _VALIDATION / "calibration_replay_supervisor.py")
_supervisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_supervisor)
expected_replay_rows = _supervisor.expected_replay_rows

class E6SupervisorBindingTests(unittest.TestCase):
    def test_native_member_replay_rows_join_exact_fit_task_pairs(self):
        members=("gmm","copula","arf","kde","chow_liu")
        audit={"records":[{"task_key":"e4/eval/1","fit_key":"fit/a","identity":"i","supervision_mode":"replayed"}],
          "e6_member_calibration_records":[
            {"task_key":"e6/rep_1/equal","fit_key":"fit/"+m,"member":m,"status":"validated",
             "native_replay_identity":("a"*63+str(i+1)),
             "native_replay_metadata_sha256":("b"*63+str(i+1)),
             "native_replay_vector_file_sha256":("c"*63+str(i+1))}
            for i,m in enumerate(members)]}
        rows=expected_replay_rows(audit)
        self.assertEqual(len(rows),6)
        self.assertEqual({(r["task_key"],r["fit_key"]) for r in rows if r.get("e6_member")},
          {("e6/rep_1/equal","fit/"+m) for m in members})
        for r in rows:
            if r.get("e6_member"):
                self.assertEqual(r["supervision_mode"],"replayed")
                self.assertIn("identity",r);self.assertIn("metadata_sha256",r);self.assertIn("nonconformity_file_sha256",r)

    def test_legacy_reports_without_e6_scope_keep_generic_supervision_contract(self):
        from importlib.util import spec_from_file_location, module_from_spec
        path = Path(__file__).resolve().parents[1] / "source" / "calibration_replay_supervisor.py"
        spec = spec_from_file_location("staged_supervisor_coverage_gate", path)
        module = module_from_spec(spec); spec.loader.exec_module(module)
        self.assertFalse(module.audit_coverage_rejects({"records":[{"task_key":"eval","fit_key":"fit"}]}))
        self.assertTrue(module.audit_coverage_rejects({"records":[],"required_e6_ensembles":1}))
        self.assertTrue(module.audit_coverage_rejects({"records":[],"q_replay_coverage_complete":False}))
        self.assertFalse(module.audit_coverage_rejects({"records":[],"q_replay_coverage_complete":True}))

    def test_nonvalidated_or_malformed_e6_rows_cannot_add_supervision_bindings(self):
        audit={"records":[],"e6_member_calibration_records":[
          {"task_key":"e6/x","fit_key":"fit/x","status":"unavailable"},
          {"task_key":"e6/y","fit_key":"fit/y","status":"validated","native_replay_identity":"short",
           "native_replay_metadata_sha256":"b"*64,"native_replay_vector_file_sha256":"c"*64}]}
        with self.assertRaises(RuntimeError):expected_replay_rows(audit)

if __name__=="__main__":unittest.main()
