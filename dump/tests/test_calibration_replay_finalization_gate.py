import hashlib, json, math, pathlib, tempfile, unittest
from unittest import mock
import numpy as np
import finalize_project as f
import final_review as review
import calibration_replay as cr
HERE=pathlib.Path(__file__).resolve().parents[1]

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as stream:
  for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
 return h.hexdigest()

def make_fixture(base):
 root=pathlib.Path(base);rt=root/'runtime_20261025';reports=rt/'reports';reports.mkdir(parents=True)
 physical_key='e3/rep_1/eval/direct/gmm';fit_key='e3/rep_1/fit/gmm';alias_key='e5/rep_1/eval/direct/gmm/clean'
 tasks=[{'key':physical_key,'experiment':3,'kind':'eval','scientific_case':True,'fit_key':fit_key,'rep':1,'status':'validated_terminal','outcome':'successful'},
        {'key':alias_key,'experiment':5,'kind':'alias','scientific_case':True,'source_key':physical_key,'rep':1,'status':'validated_terminal','outcome':'successful'}]
 reg={'schema_version':'fixture','observed_utc':'fixture','tasks':tasks};reg_path=rt/'registry.json';reg_path.write_text(json.dumps(reg,sort_keys=True)+'\n')
 role_path=rt/'cache'/'roles'/'rep_1.npz';role_path.parent.mkdir(parents=True);role_path.write_bytes(b'fixture-role-data');role_sha=sha(role_path)
 y=np.arange(70,dtype=np.int64)%7;ids=np.arange(1000,1070,dtype=np.int64);X=np.arange(420,dtype=np.float64).reshape(70,6)
 scores=np.full((70,7),.05,dtype=np.float64);scores[np.arange(70),y]=.7
 derived=cr.derive(scores,y,'probability')
 eval_doc={'fit_key':fit_key,'pipeline_sha256':'a'*64,'threshold':derived['threshold'],'calibration_n':70,'score_kind':'probability','calibration_score_kind':'probability','prediction_rule':'argmax_class_score','nonconformity_rule':'1-p_true','class_order':list(range(7))}
 physical_dir=rt/'artifacts'/physical_key;physical_dir.mkdir(parents=True)
 eval_path=physical_dir/'evaluation.json';eval_path.write_text(json.dumps(eval_doc,sort_keys=True)+'\n')
 cal_doc={'fit_key':fit_key,'pipeline_sha256':'a'*64,'threshold':derived['threshold'],'calibration_n':70,'score_kind':'probability'}
 cal_path=physical_dir/'calibration.json';cal_path.write_text(json.dumps(cal_doc,sort_keys=True)+'\n')
 alias_dir=rt/'artifacts'/alias_key;alias_dir.mkdir(parents=True);(alias_dir/'evaluation.json').write_text(json.dumps(eval_doc,sort_keys=True)+'\n')
 eval_sha=sha(eval_path);cal_sha=sha(cal_path)
 identity,doc=cr.make_identity(pipeline_sha256='a'*64,role_file_sha256=role_sha,ids=ids,X=X,y=y,kind='probability',helper_sha256=sha(HERE/'source/calibration_replay.py'),dependencies={'numpy':np.__version__,'source_evaluation_sha256':eval_sha,'calibration_json_sha256':cal_sha})
 meta={**doc,'task_key':physical_key,'fit_key':fit_key,'role_path':role_path.relative_to(rt).as_posix(),'pipeline_path':'artifacts/'+fit_key+'/pipeline.joblib','source_evaluation_sha256':eval_sha,'calibration_json_sha256':cal_sha,'threshold_comparison_reasons':[]}
 dest=cr.save_replay(rt/'artifacts'/'calibration_replay',identity,derived,meta)
 mpath=dest/'metadata.json';vpath=dest/'nonconformity.npz'
 row={'task_key':physical_key,'fit_key':fit_key,'status':'validated','pipeline_sha256':'a'*64,'role_file_sha256':role_sha,
      'calibration_ids_sha256':cr.typed_sha(ids),'X_cal_sha256':cr.typed_sha(X),'y_cal_sha256':cr.typed_sha(y),
      'score_kind':'probability','nonconformity_rule':'1-p_true','alpha':.1,'class_order':list(range(7)),
      'class_order_source':'frozen models_flexible._FlexibleModel class_models indexed 0..6','supervision_mode':'replayed','saved_threshold':derived['threshold'],'recomputed_threshold':derived['threshold'],
      'calibration_n':70,'rank_k':64,'identity':identity,'metadata_path':mpath.relative_to(rt).as_posix(),
      'nonconformity_path':vpath.relative_to(rt).as_posix(),'metadata_sha256':sha(mpath),
      'nonconformity_file_sha256':sha(vpath),'nonconformity_sha256':cr.typed_sha(derived['nonconformity']),'reasons':[]}
 alias={'task_key':alias_key,'source_key':physical_key,'physical_source_key':physical_key,'status':'inherited',
        'source_identity':identity,'threshold_match':True,'calibration_role_match':True,'score_kind_match':True,
        'nonconformity_rule_match':True,'class_order_match':True,'alpha_match':True,
        'inherited_from_physical':True,'reasons':[]}
 nonce='a'*32;phase_id='phase-fixture';ledger_rel='logs/operational/calibration_replay_phase_ledger_'+nonce+'.jsonl'
 ledger_path=rt/ledger_rel;ledger_path.parent.mkdir(parents=True,exist_ok=True)
 events=[{'schema_version':'lamost-calibration-replay-phase-ledger/1','run_nonce':nonce,'phase_id':phase_id,'event':'start','mode':'replayed','phase':'calibration_score_replay','fit_key':fit_key,'task_keys':[physical_key],'prior_receipts':{},'pid':99999,'process_start_ticks':123,'monotonic':1.0,'utc':'fixture-start'},
         {'schema_version':'lamost-calibration-replay-phase-ledger/1','run_nonce':nonce,'phase_id':phase_id,'event':'finish','mode':'replayed','phase':'calibration_score_replay','fit_key':fit_key,'task_keys':[physical_key],'prior_receipts':{},'pid':99999,'process_start_ticks':123,'monotonic':2.0,'utc':'fixture-end'}]
 ledger_bytes=b''.join((json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode() for x in events);ledger_path.write_bytes(ledger_bytes)
 audit={'schema_version':'lamost-calibration-replay-audit/1','generated_utc':'fixture','replay_run_nonce':nonce,'registry_snapshot_sha256':sha(reg_path),
        'phase_ledger_path':ledger_rel,'phase_ledger_sha256':hashlib.sha256(ledger_bytes).hexdigest(),
        'required_physical':1,'successful_physical':1,'mismatch_physical':0,'unavailable_physical':0,
        'required_aliases':1,'inherited_aliases':1,'mismatch_aliases':0,'unavailable_aliases':0,
        'q_replay_coverage_complete':True,'complete':False,'complete_requires_external_supervision_receipt':True,
        'independent_q_recomputed':True,'records':[row,alias],
        'policy':{'alpha':.1,'class_order':list(range(7)),'replay_reads_test_rows':False,'supervision':{'wall_seconds':600,'rss_limit_bytes':10*1024**3,'enforced_by_auditor':False,'external_supervision_required':True}}}
 audit_path=reports/'CALIBRATION_REPLAY_AUDIT.json';audit_path.write_text(json.dumps(audit,sort_keys=True)+'\n')
 audit_sha=sha(audit_path);bindings=[{'task_key':physical_key,'fit_key':fit_key,'identity':identity,'metadata_sha256':row['metadata_sha256'],'nonconformity_file_sha256':row['nonconformity_file_sha256']}]
 receipt={'schema_version':'lamost-calibration-replay-supervision/1','status':'complete','run_nonce':nonce,'audit_sha256':audit_sha,
  'registry_snapshot_sha256':audit['registry_snapshot_sha256'],'phase_ledger_sha256':audit['phase_ledger_sha256'],'accepted_prior_receipts_index_sha256':None,
  'audit_process_exit_code':0,'audit_process_exit_verified':True,'finalized_after_audit_exit':True,
  'limits':{'wall_seconds':600,'rss_bytes':10*1024**3},
  'phase_records':[{'phase_id':phase_id,'mode':'replayed','phase':'calibration_score_replay','run_nonce':nonce,'fit_key':fit_key,'task_keys':[physical_key],'status':'passed',
   'phase_start_event_sha256':hashlib.sha256(ledger_bytes.splitlines()[0]).hexdigest(),'phase_finish_event_sha256':hashlib.sha256(ledger_bytes.splitlines()[1]).hexdigest(),
   'started_utc':'fixture-start','finished_utc':'fixture-end','measurement_method':'fixture sampled RSS',
   'duration_seconds':1.0,'peak_process_tree_rss_bytes':100,'process_identity_verified':True,'cap_enforced':True,'exit_code':0,
   'identity_bindings':bindings}]}
 (reports/'CALIBRATION_REPLAY_SUPERVISION.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
 return root,rt,audit_path,audit,row,alias

class CalibrationReplayFinalizationGateTests(unittest.TestCase):
 def test_valid_replay_binds_all_q_threshold_and_role_evidence(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td)
   info=f._calibration_replay_validation(rt)
   self.assertTrue(info['complete']);self.assertTrue(info['independent_q_recomputed'])
   self.assertEqual(info['counts']['successful_physical'],1);self.assertEqual(info['counts']['inherited_aliases'],1)
   expected={};files=[];review_info=review.calibration_replay_review_inputs(root,rt,expected,files)
   self.assertEqual(review_info,info);self.assertEqual(len(files),5)
   self.assertIn(str(audit_path.resolve()),expected)
   for item in info['evidence_files']:self.assertIn(str((rt/item['path']).resolve()),expected)
   self.assertEqual(len(info['physical_records']),1);self.assertEqual(info['physical_records'][0]['rank_k'],64)

 def test_missing_or_subset_replay_rows_fail_closed(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);audit_path.unlink()
   with self.assertRaisesRegex(f.EvidenceError,'audit is missing'):f._calibration_replay_validation(rt)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);audit['records']=[alias];audit_path.write_text(json.dumps(audit))
   with self.assertRaisesRegex(f.EvidenceError,'physical coverage differs'):f._calibration_replay_validation(rt)

 def test_saved_recomputed_or_vector_threshold_mismatch_fails(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);audit['records'][0]['saved_threshold']+=.02;audit_path.write_text(json.dumps(audit))
   with self.assertRaisesRegex(f.EvidenceError,'threshold'):f._calibration_replay_validation(rt)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);p=rt/row['nonconformity_path'];p.write_bytes(p.read_bytes()+b'tamper')
   with self.assertRaisesRegex(f.EvidenceError,'file hash mismatch'):f._calibration_replay_validation(rt)

 def test_rehashed_tampered_identity_metadata_is_rejected(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td)
   metadata=rt/row['metadata_path'];doc=json.loads(metadata.read_text());doc['dependencies']['source_evaluation_sha256']='d'*64
   metadata.write_text(json.dumps(doc,sort_keys=True)+'\n');row['metadata_sha256']=sha(metadata);audit_path.write_text(json.dumps(audit,sort_keys=True)+'\n')
   with self.assertRaisesRegex(f.EvidenceError,'identity does not bind'):f._calibration_replay_validation(rt)

 def test_external_replay_supervision_policy_is_recorded_but_not_overclaimed(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td)
   audit['policy']['supervision']['rss_limit_bytes']=1*1024**3;audit_path.write_text(json.dumps(audit))
   with self.assertRaisesRegex(f.EvidenceError,'external 600-second/10-GiB supervision policy'):
    f._calibration_replay_validation(rt)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td)
   proof=f._calibration_replay_validation(rt)
   self.assertEqual(proof['external_supervision_policy']['wall_seconds'],600)
   self.assertEqual(proof['external_supervision_policy']['rss_bytes'],10*1024**3)
   self.assertTrue(proof['external_supervision_policy']['enforced_by_external_supervisor'])
   self.assertFalse(proof['external_supervision_policy']['enforced_by_auditor'])

 def test_alias_wrong_source_or_threshold_inheritance_fails(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);audit['records'][1]['source_identity']='f'*64;audit_path.write_text(json.dumps(audit))
   with self.assertRaisesRegex(f.EvidenceError,'alias provenance'):f._calibration_replay_validation(rt)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);audit['records'][1]['threshold_match']=False;audit_path.write_text(json.dumps(audit))
   with self.assertRaisesRegex(f.EvidenceError,'alias provenance'):f._calibration_replay_validation(rt)

 def test_reviewer_rejects_mutated_q_artifact_after_candidate_projection(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);expected={};files=[]
   review.calibration_replay_review_inputs(root,rt,expected,files)
   (rt/row['metadata_path']).write_text('{}')
   with self.assertRaises(f.EvidenceError):review.calibration_replay_review_inputs(root,rt,{},[])

 def test_cached_full_report_requires_a_current_replay_proof(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);report=rt/'reports'/'FINAL_SCIENTIFIC_REPORT.md';report.write_text('# fixture\n')
   proof={'candidate_id':'fixture'};frozen=f.validate_condition_findings;f.validate_condition_findings=lambda *a,**k:True
   try:
    state={'phase':'awaiting_report_audit','review_candidate_id':'fixture','final_report_path':str(report),'final_report_sha256':sha(report),
           'artifact_audit':{'full_calibration_replay_pass':True,'calibration_replay':f._calibration_replay_validation(rt)}}
    (rt/'finalizer_state.json').write_text(json.dumps(state));self.assertIsNotNone(f._resume_reviewed_report_state(rt,proof))
    state['artifact_audit']={};(rt/'finalizer_state.json').write_text(json.dumps(state));self.assertIsNone(f._resume_reviewed_report_state(rt,proof))
   finally:f.validate_condition_findings=frozen

 def test_pending_delivery_cache_without_replay_proof_is_rejected(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);proof={'decision':'pass','candidate_id':'fixture','manifest_sha256':'m'}
   (rt/'REPORT_READY_FOR_AUDIT.json').write_text(json.dumps({'candidate_id':'fixture','manifest_sha256':'m','manifest_path':str(rt/'review.json')}));(rt/'review.json').write_text('{}')
   (rt/'finalizer_state.json').write_text(json.dumps({'phase':'delivery_pending_on_laptop','report_validation':{},'artifact_audit':{'full_calibration_replay_pass':False}}))
   pending=rt/'EC2_COMPLETE_DELIVERY_PENDING.json';pending.write_text(json.dumps({'report_review':proof}))
   old_wait,old_verify,old_condition=review.quick_wait,review.verify_report_files,f.validate_condition_findings
   review.quick_wait=lambda runtime:None;review.verify_report_files=lambda *args:True;f.validate_condition_findings=lambda *args,**kwargs:True
   try:self.assertIsNone(f._valid_pending(pending,rt))
   finally:review.quick_wait,review.verify_report_files,f.validate_condition_findings=old_wait,old_verify,old_condition

 def test_review_required_marker_filters_private_failure_details(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   runtime=pathlib.Path(td)/'runtime_20261025';runtime.mkdir()
   result={'status':'FINALIZATION_REVIEW_REQUIRED','observed_utc':'2026-10-26T00:00:00+00:00','reason':'private /var/tmp/worker receipt','failure_count':2,'fingerprint_sha256':'a'*64,'worker_pid':1234}
   payload=f._write_review_required_marker(runtime,result)
   saved=json.loads((runtime/'FINALIZATION_REVIEW_REQUIRED.json').read_text())
   self.assertEqual(saved,payload);self.assertEqual(saved['failure_count'],2);self.assertEqual(saved['fingerprint_sha256'],'a'*64)
   self.assertNotIn('reason',saved);self.assertNotIn('worker_pid',saved);self.assertNotIn('/var/tmp',json.dumps(saved))

 def test_generated_archive_readme_documents_closeout_retry_latch(self):
  text=f.package_readme('/migration/packages/archive.zip',{'e1_archive':{'path':'/migration/packages/e1.zip','sha256':'a'*64}},cold_models=False).decode()
  self.assertIn('read-only scientific reproduction snapshot',text)
  self.assertIn('at most two deterministic attempts',text)
  self.assertIn('runtime_20261025/logs/operational/finalization_retry_latch.json',text)
  self.assertIn('FINALIZATION_REVIEW_REQUIRED.json',text)
  self.assertIn('--clear-failure-latch --reason',text)
  self.assertIn('preserves the attempt history',text)

 def test_artifact_audit_invocation_requires_calibration_replay(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,audit_path,audit,row,alias=make_fixture(td);rd=rt/'reports';(rd/'INCREMENTAL_ARTIFACT_AUDIT.json').write_text('{"issue_count":0,"calibration_replay_required":true,"threshold_quantile_recomputed":true}')
   (rd/'INCREMENTAL_ARTIFACT_ISSUES.csv').write_text('task_key,kind,check,severity,evidence\n')
   import calibration_replay_supervisor as supervisor
   run=supervisor.run;validate=f._calibration_replay_validation;seen=[]
   def fake(runtime,py,script,**kwargs):seen.append((runtime,py,script,kwargs));return {'audit_sha256':'fixture-audit','receipt_sha256':'fixture-receipt'}
   supervisor.run=fake;f._calibration_replay_validation=lambda runtime:{'complete':True,'independent_q_recomputed':True}
   try:result=f._run_artifact_audit(rt)
   finally:supervisor.run=run;f._calibration_replay_validation=validate
   self.assertEqual(len(seen),1);self.assertTrue(result['full_calibration_replay_pass'])

if __name__=='__main__':unittest.main(verbosity=2)
