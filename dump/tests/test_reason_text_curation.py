import csv, json, re, sys, unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/'source'
sys.path.insert(0,str(SRC))
from reason_text_curation import sanitize_reason_text
R=Path(__file__).resolve().parents[1]
class ReasonTextCurationTests(unittest.TestCase):
    def test_actual_arf_phase_exit_rows_preserve_science_and_sanitize_receipts(self):
        p=R/'reports/resource_failure_ledger.csv'
        with p.open(newline='',encoding='utf-8') as f:
            actual=[row for row in csv.DictReader(f) if row.get('task_key') in {'e3/rep_2/fit/arf','e3/rep_3/fit/arf'} and 'supervision=' in (row.get('raw_reason') or '')]
        self.assertEqual(len(actual),2)
        for row in actual:
            raw=row['raw_reason']; clean=sanitize_reason_text(raw)
            self.assertIn('ScientificFitFailure',clean)
            self.assertIn('UnsupportedARFError',clean)
            self.assertIn('singular FORDE continuous marginal',clean)
            self.assertIn('supervision=',clean)
            for field in ('phase','seconds','peak_tree_rss_kib','exit_code','finished_at'):
                self.assertIn('"'+field+'"',clean)
            self.assertNotRegex(clean,r'(?i)["\'](?:pid|pgid|stdout|stderr|cmdline|environ)["\']\s*:')
    def test_timeout_and_phase_exit_keep_scientific_and_resource_values(self):
        raw="phase_timeout: {'phase':'trial_9','reason':'timeout','seconds':600.0,'peak_tree_rss_kib':321,'exit_code':-15,'pid':123456,'pgid':123456,'cmdline':['python','private.py'],'stdout':'secret','stderr':'receipt'}"
        clean=sanitize_reason_text(raw)
        self.assertTrue(clean.startswith('phase_timeout:'))
        for keep in ('trial_9','timeout','600.0','321','-15'):self.assertIn(keep,clean)
        for private in ('pid','pgid','cmdline','stdout','stderr','123456','private.py','secret'):self.assertNotIn(private,clean)
        raw2="phase_exit_1: {'category':'scientific_failure','exception_type':'ValueError','message':'singular covariance'}; supervision={'phase':'trial_1','seconds':12.5,'peak_tree_rss_kib':44,'exit_code':1,'source_identity':{'source_key':'e4/x','source_sha256':'abc'},'attempt_identity':{'attempt_id':'att-1'},'pid':777,'stderr':'x'}"
        clean2=sanitize_reason_text(raw2)
        for keep in ('scientific_failure','ValueError','singular covariance','12.5','44','source_key','e4/x','source_sha256','abc','attempt_id','att-1'):self.assertIn(keep,clean2)
        for private in ('pid','777','stderr'):self.assertNotIn(private,clean2)
    def test_nested_json_changes_only_supervision_and_keeps_scientific_metric(self):
        raw=json.dumps({'error':{'exception_type':'LinAlgError','message':'matrix singular'},'balanced_accuracy':0.5940662422006586,'supervision':{'phase':'calibrate','seconds':4.5,'source_identity':{'source_key':'src-7'},'pid':888,'env':{'TOKEN':'x'},'stdout':'private'}})
        clean=json.loads(sanitize_reason_text(raw))
        self.assertEqual(clean['balanced_accuracy'],0.5940662422006586)
        self.assertEqual(clean['error'],{'exception_type':'LinAlgError','message':'matrix singular'})
        self.assertEqual(clean['supervision'],{'phase':'calibrate','seconds':4.5,'source_identity':{'source_key':'src-7'}})
    def test_nonprocess_text_and_json_are_byte_identical(self):
        for text in ('ordinary scientific exception path=/project/a.py:9','phase_timeout: timeout after 600 seconds','{"balanced_accuracy":0.5,"note":"valid scientific text"}'):
            self.assertEqual(sanitize_reason_text(text),text)
    def test_direct_json_phase_receipt_removes_expanded_process_fields(self):
        raw=json.dumps({'phase':'trial_4','seconds':23.5,'elapsed_seconds':23.5,'peak_tree_rss_kib':999,'exit_code':1,'reason':'fit ended','finished_at':'2026-10-26T00:00:00Z','worker_pid':101,'controller_pid':102,'owner_pid':103,'process_start_ticks':104,'request_path':'private/request.json','result_path':'private/result.json','worker_log_path':'private/log','process_inventory':[{'pid':105}],'balanced_accuracy':0.594,'attempt_id':'attempt-abc','source_identity':{'source_key':'source-xyz','source_sha256':'sha-1'},'environment':{'python':'3.12.3','packages':{'numpy':'2.0'}}})
        clean=json.loads(sanitize_reason_text(raw))
        for k in ('worker_pid','controller_pid','owner_pid','process_start_ticks','request_path','result_path','worker_log_path','process_inventory'):self.assertNotIn(k,clean)
        self.assertEqual(clean['phase'],'trial_4');self.assertEqual(clean['seconds'],23.5);self.assertEqual(clean['peak_tree_rss_kib'],999);self.assertEqual(clean['exit_code'],1);self.assertEqual(clean['reason'],'fit ended');self.assertEqual(clean['finished_at'],'2026-10-26T00:00:00Z')
        self.assertEqual(clean['balanced_accuracy'],0.594);self.assertEqual(clean['attempt_id'],'attempt-abc');self.assertEqual(clean['source_identity'],{'source_key':'source-xyz','source_sha256':'sha-1'});self.assertEqual(clean['environment'],{'python':'3.12.3','packages':{'numpy':'2.0'}})
    def test_phase_supervision_wrapper_is_scrubbed_but_scientific_environment_is_kept(self):
        raw=json.dumps({'error':{'message':'native fit failed'},'phase_supervision':{'phase':'trial_7','seconds':8,'worker_pid':321,'request_path':'private/request','environment':{'python':'3.12.3','packages':['numpy']}},'environment':{'python':'3.12.3','packages':['numpy']}})
        clean=json.loads(sanitize_reason_text(raw))
        self.assertEqual(clean['error'],{'message':'native fit failed'})
        self.assertEqual(clean['phase_supervision'],{'phase':'trial_7','seconds':8,'environment':{'python':'3.12.3','packages':['numpy']}})
        self.assertEqual(clean['environment'],{'python':'3.12.3','packages':['numpy']})
    def test_reporting_adapter_uses_shared_helper(self):
        import reporting
        self.assertEqual(reporting._sanitize_reason('ok scientific text'),'ok scientific text')
        self.assertNotIn('pid',reporting._sanitize_reason("phase_exit: {'message':'x'}; supervision={'phase':'fit','pid':999,'seconds':2}"))
if __name__=='__main__':unittest.main()
