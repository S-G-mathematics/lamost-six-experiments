import importlib.util, json, pathlib, tempfile, sys, types, unittest
HERE=pathlib.Path(__file__).resolve().parent
SOURCE=HERE.parent/'source'/'controller.py'
HELPER=HERE.parent/'source'/'archive_fit_admission.py'
spec_h=importlib.util.spec_from_file_location('archive_fit_helper_wrong_policy_fixture',HELPER)
helper=importlib.util.module_from_spec(spec_h);spec_h.loader.exec_module(helper)
class ArchiveFitLaunchGateCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._had='admission_evidence' in sys.modules
        cls._old=sys.modules.get('admission_evidence')
        sys.modules['admission_evidence']=types.ModuleType('admission_evidence')
        spec=importlib.util.spec_from_file_location('staged_controller_gate_fixture',SOURCE)
        cls.controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.controller)
    @classmethod
    def tearDownClass(cls):
        if cls._had:sys.modules['admission_evidence']=cls._old
        else:sys.modules.pop('admission_evidence',None)
    def test_absent_overlap_policy_returns_before_db_or_resource_access(self):
        c=self.controller;old_context=c.archive_fit_overlap_context;old_load=c.load
        try:
            c.archive_fit_overlap_context=lambda:{'mode':'inactive','reason':'no_archive_helper'}
            def forbidden(_db):raise AssertionError('legacy path unexpectedly scanned DB')
            c.load=forbidden
            self.assertIsNone(c._archive_fit_launch_gate(None,{'key':'legacy'},0))
        finally:c.archive_fit_overlap_context=old_context;c.load=old_load
    def test_blocked_declared_overlap_never_falls_back_to_legacy(self):
        c=self.controller;old_context=c.archive_fit_overlap_context;old_load=c.load
        try:
            c.archive_fit_overlap_context=lambda:{'mode':'blocked','reason':'overlap_policy_invalid'}
            def forbidden(_db):raise AssertionError('blocked path unexpectedly scanned DB')
            c.load=forbidden
            self.assertIs(c._archive_fit_launch_gate(None,{'key':'legacy'},0),False)
        finally:c.archive_fit_overlap_context=old_context;c.load=old_load
    def test_wrong_declared_policy_with_owned_hold_is_blocked_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proc:
            root=pathlib.Path(tmp);hold=root/'ADMISSION_HOLD.json'
            hold.write_text(json.dumps({'owner_operation':helper.OWNER_OPERATION,
                'batch_policy':helper.BATCH_POLICY,'operation_id':'auto_storage_20261028T010000Z_12345678',
                'nonce':'a'*32,'reason':'one-shot bounded cold-model archive batch; pause new admissions only'}))
            before=hold.read_bytes()
            state=helper.inspect_runtime(root,{helper.POLICY_FIELD:'a'*64,
                helper.QUALIFICATION_FIELD:'b'*64},proc_root=proc,uid=123)
            self.assertEqual(state['mode'],'blocked')
            self.assertEqual(state['reason'],'overlap_policy_invalid')
            self.assertEqual(hold.read_bytes(),before)
if __name__=='__main__':unittest.main()
