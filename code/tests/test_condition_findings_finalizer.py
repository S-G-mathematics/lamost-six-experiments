import hashlib, json, os, pathlib, shutil, tempfile, unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parents[1]
import finalize_project as f

def _fixture_empty_primary_archive_context(runtime):
 import hashlib, sys, types
 raw=b'{"schema_version":"fixture-empty-primary/1"}\n'
 rel="manifests/FROZEN_E1_PRIMARY_ARCHIVED_ASSETS_20261030.json"
 path=pathlib.Path(runtime)/rel
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 module=types.ModuleType("frozen_e1_primary_archive")
 module.LOCATOR_REL=rel;module.LOCATOR_SHA256=hashlib.sha256(raw).hexdigest()
 module.primary_e1_archive_entries=lambda *a,**k:([],b'{"fixture":"empty-primary"}')
 return mock.patch.dict(sys.modules,{"frozen_e1_primary_archive":module})

INPUTS=f.CONDITION_FINDINGS_INPUTS
COUNTS=f._condition_findings_expected_counts()

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as x:
  for b in iter(lambda:x.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def fixture_builder(runtime,wrong_counts=False):
 runtime=pathlib.Path(runtime);src=runtime/'source';rd=runtime/'reports';src.mkdir(parents=True,exist_ok=True);rd.mkdir(parents=True,exist_ok=True)
 for name in INPUTS:(rd/name).write_text('fixture-only input '+name+'\n')
 counts=dict(COUNTS)
 if wrong_counts:counts['E4_summary_strata']=909
 code='''import hashlib,json\nfrom pathlib import Path\nINPUTS=INPUTS\nCOUNTS=COUNTS\ndef sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\ndef build(reports,output):\n reports=Path(reports);output=Path(output);output.mkdir(parents=True,exist_ok=True)\n names=("E4_CONDITION_FINDINGS.md","E5_CONDITION_FINDINGS.md","CONDITION_FINDINGS_INDEX.md")\n for name in names:(output/name).write_text("fixture-only descriptive appendix: "+name+"\\n")\n manifest={"status":"descriptive_appendices_built","project_state":"terminal_snapshot_requires_final_validation","created_from_existing_csvs_only":True,"input_sha256":{n:sha(reports/n) for n in INPUTS},"counts":COUNTS,"outputs":{n:sha(output/n) for n in names}}\n p=output/"CONDITION_FINDINGS_MANIFEST.json";p.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\\n")\n manifest["manifest_sha256"]=sha(p)\n return manifest\n'''.replace('INPUTS=INPUTS',f'INPUTS={INPUTS!r}').replace('COUNTS=COUNTS',f'COUNTS={counts!r}')
 (src/'build_condition_findings.py').write_text(code)
 return runtime

class ConditionFindingsFinalizerTests(unittest.TestCase):
 def test_report_phase_runs_builder_after_cli_and_binds_result(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=fixture_builder(pathlib.Path(td)/'runtime_20261025');rp=rt/'reports'/'report_result.json';rp.write_text(json.dumps({'status':'success','planned_scientific_cases':2823}))
   events=[];original_cli=f.report_cli_and_validate;original_builder=f.build_condition_findings
   def cli(root,runtime,terminal):
    events.append('report_cli');result={'status':'success','planned_scientific_cases':2823};rp.write_text(json.dumps(result));return {'report_result':result,'required_csvs':[],'figures':[],'expanded_pairing_rows':{}}
   def builder(runtime):events.append('condition_findings_builder');return original_builder(runtime)
   f.report_cli_and_validate=cli;f.build_condition_findings=builder
   try:info=f.prepare_report_phase(rt.parent,rt,{'outcomes':{}})
   finally:f.report_cli_and_validate=original_cli;f.build_condition_findings=original_builder
   self.assertEqual(events,['report_cli','condition_findings_builder'])
   saved=json.loads(rp.read_text());self.assertEqual(saved['condition_findings'],info['condition_findings'])
   self.assertEqual(info['condition_findings']['counts'],COUNTS)
   self.assertEqual(info['report_result_sha256'],sha(rp))
   self.assertIn('builder_sha256',saved['condition_findings'])

 def test_bad_grid_and_mutated_input_are_rejected(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=fixture_builder(pathlib.Path(td)/'bad_runtime',wrong_counts=True)
   (rt/'reports'/'report_result.json').write_text(json.dumps({'status':'success','planned_scientific_cases':2823}))
   with self.assertRaisesRegex(f.EvidenceError,'grid counts'):
    f.build_condition_findings(rt)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=fixture_builder(pathlib.Path(td)/'runtime_20261025');rp=rt/'reports'/'report_result.json';rp.write_text('{}')
   info=f.build_condition_findings(rt);result=json.loads(rp.read_text());result['condition_findings']=info;rp.write_text(json.dumps(result))
   (rt/'reports'/INPUTS[0]).write_text('mutated fixture input')
   with self.assertRaisesRegex(f.EvidenceError,'source CSV changed'):
    f.validate_condition_findings(rt)

 def test_reviewed_cache_requires_findings_binding_and_detects_output_change(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=fixture_builder(pathlib.Path(td)/'runtime_20261025');reports=rt/'reports';rp=reports/'report_result.json';info=f.build_condition_findings(rt)
   result={'status':'success','planned_scientific_cases':2823,'condition_findings':info};rp.write_text(json.dumps(result))
   final=reports/'FINAL_SCIENTIFIC_REPORT.md';final.write_text('# fixture final report\n')
   proof={'candidate_id':'fixture-candidate'};state={'phase':'awaiting_report_audit','review_candidate_id':'fixture-candidate','final_report_path':str(final),'final_report_sha256':sha(final),'report_validation':{'condition_findings':info}}
   (rt/'finalizer_state.json').write_text(json.dumps(state))
   # The production resume gate independently requires a valid Q replay audit.
   # This focused test isolates condition-findings cache binding and mocks only that unrelated gate.
   self.assertIsNone(f._resume_reviewed_report_state(rt,proof))
   state['artifact_audit']={'full_calibration_replay_pass':True,'calibration_replay':{'fixture':'validated by dedicated replay-gate tests'}}
   (rt/'finalizer_state.json').write_text(json.dumps(state))
   expected={str(rp.resolve()):sha(rp)};bound=f.bind_condition_findings_after_review(rt,{'condition_findings':info},expected)
   for name,record in info['outputs'].items():self.assertEqual(bound[str((rt.parent/record['path']).resolve())],record['sha256'])
   with mock.patch.object(f,'_calibration_replay_validation',return_value={'valid':True}) as q_gate:
    self.assertIsNotNone(f._resume_reviewed_report_state(rt,proof));q_gate.assert_called_once()
    (reports/'E4_CONDITION_FINDINGS.md').write_text('changed after review')
    with self.assertRaisesRegex(f.EvidenceError,'output changed or is missing'):f.bind_condition_findings_after_review(rt,{'condition_findings':info},expected)
    self.assertIsNone(f._resume_reviewed_report_state(rt,proof))
   result.pop('condition_findings');rp.write_text(json.dumps(result));state['report_validation']={};(rt/'finalizer_state.json').write_text(json.dumps(state))
   self.assertIsNone(f._resume_reviewed_report_state(rt,proof))

 def test_valid_pending_rejects_legacy_cache_without_condition_binding(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=pathlib.Path(td)/'runtime_20261025';rt.mkdir();proof={'decision':'pass','candidate_id':'legacy','manifest_sha256':'m'}
   ready={'candidate_id':'legacy','manifest_sha256':'m','manifest_path':str(rt/'review.json')}
   (rt/'REPORT_READY_FOR_AUDIT.json').write_text(json.dumps(ready));(rt/'review.json').write_text('{}')
   (rt/'finalizer_state.json').write_text(json.dumps({'phase':'delivery_pending_on_laptop','report_validation':{}}))
   pending=rt/'EC2_COMPLETE_DELIVERY_PENDING.json';pending.write_text(json.dumps({'report_review':proof}))
   import final_review
   old_wait,old_verify=final_review.quick_wait,final_review.verify_report_files
   final_review.quick_wait=lambda runtime:None;final_review.verify_report_files=lambda *args:True
   try:self.assertIsNone(f._valid_pending(pending,rt))
   finally:final_review.quick_wait,final_review.verify_report_files=old_wait,old_verify

 def test_main_report_links_all_condition_appendices_and_full_denominators(self):
  lines=f.condition_findings_reference_lines({'counts':COUNTS});text='\n'.join(lines)
  for name in ('CONDITION_FINDINGS_INDEX.md','E4_CONDITION_FINDINGS.md','E5_CONDITION_FINDINGS.md'):self.assertIn(name,text)
  for n in ('910','2730','288','864','2016','6048'):self.assertIn(n,text)

 def test_condition_appendices_and_builder_enter_full_and_compact_member_lists(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);rt=root/'runtime_20261025';
   for d in ('project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024'):(root/d).mkdir(parents=True,exist_ok=True)
   (rt/'source').mkdir(parents=True);(rt/'tests').mkdir();(rt/'cache').mkdir();(rt/'artifacts').mkdir();(rt/'reports').mkdir();(rt/'manifests').mkdir()
   for name in ('build_condition_findings.py','reporting.py'):(rt/'source'/name).write_text('fixture source '+name)
   for name in ('E4_CONDITION_FINDINGS.md','E5_CONDITION_FINDINGS.md','CONDITION_FINDINGS_INDEX.md','CONDITION_FINDINGS_MANIFEST.json'):(rt/'reports'/name).write_text('fixture report '+name)
   from test_cold_finalizer_adapter import copy_pinned_qualified_closure
   copy_pinned_qualified_closure(root)
   with _fixture_empty_primary_archive_context(rt), mock.patch('cold_finalizer_adapter.e1_locator_archive_entries',lambda *a,**k:([],b'{}')):
    entries=f.collect_full(root,rt,b'#fixture',json.dumps({'tasks':[]}))
   members={x.member for x in entries}
   self.assertIn('runtime_20261025/source/build_condition_findings.py',members)
   for name in ('E4_CONDITION_FINDINGS.md','E5_CONDITION_FINDINGS.md','CONDITION_FINDINGS_INDEX.md','CONDITION_FINDINGS_MANIFEST.json'):
    self.assertIn('runtime_20261025/reports/'+name,members)
    self.assertIn(rt/'reports'/name,f.small_report_files(rt/'reports'))

 def test_real_builder_refuses_missing_source_csvs(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   rt=pathlib.Path(td)/'runtime_20261025';(rt/'source').mkdir(parents=True);(rt/'reports').mkdir()
   builder=HERE/'source'/'build_condition_findings.py'
   shutil.copy2(builder,rt/'source'/'build_condition_findings.py')
   with self.assertRaises(FileNotFoundError):f.build_condition_findings(rt)

if __name__=='__main__':unittest.main(verbosity=2)
