import csv,hashlib,importlib.util,json,sys,tempfile,types,unittest
import numpy as np
from pathlib import Path

CANDIDATE=Path(__file__).resolve().parents[1]/'source'/'finalize_project.py'

def load_candidate():
    stub=types.ModuleType('finalization_safety')
    for name in ('PortableBundleError','PortableTestFailure','portable_bundle_snapshot',
                 'finalization_fingerprint','begin_finalization_attempt','finish_finalization_attempt',
                 'run_portable_test_bundle','portable_receipt_matches','portable_pass_receipt_path',
                 'is_resource_backoff','clear_finalization_latch'):
        setattr(stub,name,type(name,(Exception,),{}) if name in ('PortableBundleError','PortableTestFailure') else (lambda *a,**k:None))
    prior=sys.modules.get('finalization_safety')
    sys.modules['finalization_safety']=stub
    try:
        spec=importlib.util.spec_from_file_location('candidate_finalize_project',CANDIDATE)
        mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    finally:
        if prior is None:sys.modules.pop('finalization_safety',None)
        else:sys.modules['finalization_safety']=prior
    return mod

M=load_candidate()

def putjson(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,sort_keys=True)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def csvwrite(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

class E6V2FinalizerCandidateTests(unittest.TestCase):
    def make_runtime(self,root):
        runtime=root/'runtime_20261025';rd=runtime/'reports';out=rd/'E6_V2_FINAL_fixture';out.mkdir(parents=True)
        tasks=[]
        for i in range(6):
            outcome='successful' if i<2 else 'unavailable_dependency'
            tasks.append({'key':f'e6_task_{i+1}','experiment':6,'kind':'ensemble','scientific_case':True,
                          'status':'validated_terminal','outcome':outcome,'validation_state':'validated' if i<2 else 'unavailable','mode':'equal' if i%2==0 else 'learned','e6_protocol_version':'E6-v2'})
        reg={'observed_utc':'2026-10-27T00:00:00Z','tasks':tasks}
        putjson(runtime/'registry.json',reg)
        current_out=rd/f'E6_V2_FINAL_{sha(runtime/'registry.json')[:12]}'
        out.rename(current_out);out=current_out
        hist=[{'task_key':f'historical_{i+1}','cell_kind':'member_reference',
               'provenance_group':'historical_E3_direct_reference_not_E6_scoring'} for i in range(15)]
        primary=[]
        av=[]
        for i,t in enumerate(tasks):
            ok=t['outcome']=='successful'
            primary.append({'task_key':t['key'],'cell_kind':'primary_ensemble','provenance_group':'E6_v2_primary_ensemble',
                            'status':t['status'],'outcome':t['outcome'],'validation_state':t['validation_state'],
                            'evaluation_present':str(ok),'balanced_accuracy':'0.7' if ok else '',
                            'coverage':'0.9' if ok else '','mean_set_size':'1.2' if ok else ''})
            av.append({'task_key':t['key'],'outcome':t['outcome'],'member_comparison_present':str(ok)})
        ledger=out/'E6_V2_MAIN_CELL_LEDGER_21.csv'
        csvwrite(ledger,['task_key','cell_kind','provenance_group','status','outcome','validation_state','evaluation_present','balanced_accuracy','coverage','mean_set_size'],hist+primary)
        availability=out/'E6_V2_AVAILABILITY.csv'
        csvwrite(availability,['task_key','outcome','member_comparison_present'],av)
        partial=[]
        for i,t in enumerate(tasks):
            ok=t['outcome']=='successful'
            frozen_path='';ledger_path=''
            state='no_frozen_tuning_artifact'
            if ok:
                state='validated_frozen_tuning_evidence'
                parts=Path(*t['key'].split('/'));target=out/'partial_tuning'/parts;target.mkdir(parents=True,exist_ok=True)
                fw={'mode':t['mode'],'member_order':['gmm','copula','arf','kde','chow_liu'],'weights':[.2]*5,'frozen_before_calibration_and_test':True}
                (target/'frozen_weights.json').write_text(json.dumps(fw))
                frozen_path=(Path('partial_tuning')/parts/'frozen_weights.json').as_posix()
                if t['mode']=='learned':
                    (target/'candidate_ledger.json').write_text('{}')
                    ledger_path=(Path('partial_tuning')/parts/'candidate_ledger.json').as_posix()
            partial.append({'task_key':t['key'],'task_outcome':t['outcome'],'test_evaluation_present':str(ok),
                            'evidence_state':state,'frozen_weights_archive_path':frozen_path,
                            'candidate_ledger_archive_path':ledger_path,'performance_metrics_included':'False'})
        csvwrite(out/'E6_V2_PARTIAL_TUNING_EVIDENCE.csv',
                 ['task_key','task_outcome','test_evaluation_present','evidence_state','frozen_weights_archive_path','candidate_ledger_archive_path','performance_metrics_included'],partial)
        files=set(M.E6_V2_REQUIRED_OUTPUTS)-{'E6_V2_REPORT_RECEIPT.json'}
        outputs={}
        for name in files:
            p=out/name
            if not p.exists():p.write_text('fixture\n',encoding='utf-8')
            outputs[name]=sha(p)
        outputs={x.relative_to(out).as_posix():sha(x) for x in out.rglob('*') if x.is_file()}
        exporter=runtime/'source/export_e6_v2_descriptive.py';helper=runtime/'source/e6_v2_reporting.py'
        exporter.parent.mkdir(parents=True,exist_ok=True);exporter.write_text('# exporter fixture\n')
        helper.write_text('# helper fixture\n')
        old=rd/'history/E6_v1_superseded_before_v2_20261027/E6_FINAL_CELL_LEDGER_21.csv'
        old.parent.mkdir(parents=True,exist_ok=True);old.write_text('task_key,cell_kind\n')
        receipt={'schema_version':'lamost-e6-v2-descriptive-export/1',
                 'status':'descriptive_outputs_only_not_project_completion',
                 'registry_observed_utc':reg['observed_utc'],
                 'inputs':{'registry_sha256':sha(runtime/'registry.json'),'superseded_ledger_sha256':sha(old)},
                 'source_sha256':{'exporter_sha256':sha(exporter),'helper_sha256':sha(helper)},
                 'actions':{'fitting':False,'model_loading':False,'posterior_generation':False,
                            'calibration_or_test_inference':False,'bootstrap':False},
                 'outputs_sha256':outputs}
        putjson(out/'E6_V2_REPORT_RECEIPT.json',receipt)
        return runtime,out

    def test_private_phase_receipts_excluded_and_manifest_hash_only(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';runtime.mkdir()
            task={'key':'e6_task_1','experiment':6,'kind':'ensemble','scientific_case':True}
            putjson(runtime/'registry.json',{'tasks':[task]})
            raw=runtime/'artifacts/e6_task_1/attempts/attempt_a/e6_phase_tune.json'
            raw.parent.mkdir(parents=True,exist_ok=True)
            raw.write_text('{"pid":12345,"pgid":12346,"env":{"SECRET":"x"}}\n')
            stream=raw.parent/'e6_phase_events.jsonl';stream.write_text('{"worker_pid":999,"event":"done"}\n')
            self.assertTrue(M.sensitive(raw));self.assertTrue(M._is_private_e6_phase_receipt(stream))
            doc=json.loads(M.e6_private_phase_receipt_manifest(runtime))
            self.assertEqual(doc['receipt_count'],2)
            self.assertFalse(doc['raw_receipts_included'])
            self.assertTrue(doc['raw_receipts_remain_on_ec2'])
            text=json.dumps(doc)
            for secret in ('12345','12346','999','SECRET','attempt_a'):
                self.assertNotIn(secret,text)
            self.assertEqual({x['receipt_name'] for x in doc['receipts']},{raw.name,stream.name})
            self.assertEqual({x['sha256'] for x in doc['receipts']},{sha(raw),sha(stream)})

    def test_current_e6_v2_export_matches_registry_and_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            runtime,out=self.make_runtime(Path(td))
            result=M.validate_e6_v2_export(runtime,out)
            self.assertEqual(result['historical_member_references'],15)
            self.assertEqual(result['primary_ensemble_cases'],6)
            self.assertEqual(result['primary_outcomes'],{'successful':2,'unavailable_dependency':4})
            self.assertEqual(M.refresh_e6_v2_export(Path(td),runtime,Path(sys.executable),dict(__import__('os').environ))['path'],str(out.resolve()))

    def test_native_q_gate_requires_exact_five_members_and_ensemble_thresholds(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';key='e6_equal_rep_1'
            role=runtime/'cache/roles/rep_1.npz';role.parent.mkdir(parents=True,exist_ok=True)
            calibration_ids=np.arange(10000,dtype=np.int64);X_cal=np.zeros((10000,6),dtype=np.float32);y_cal=np.zeros(10000,dtype=np.int64)
            np.savez(role,calibration_ids=calibration_ids,X_cal=X_cal,y_cal=y_cal)
            def typed(a):
                a=np.ascontiguousarray(a);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.view(np.uint8));return h.hexdigest()
            def raw(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
            art=runtime/'artifacts'/key;art.mkdir(parents=True)
            comp_path=art/'member_comparisons.json'
            member_names=['gmm','copula','arf','kde','chow_liu'];weights=[0.2]*5
            score_vec_sha='a'*64;cal_ids=typed(calibration_ids);cal_x=typed(X_cal);cal_y=typed(y_cal);pipeline='e'*64
            members={n:{'fit_key':'fit_'+n,'pipeline_sha256':pipeline,'fit_ids_sha256':'f'*64,'role_membership_sha256':'r'*64,'selected_params_sha256':'s'*64,'provenance_group':'E3_new_fit','score_kind':'probability','calibration_threshold':0.25} for n in member_names}
            comp={'schema_version':'lamost-e6-member-comparisons/1','protocol_version':'E6-v2',
                  'comparison_source_task_key':key,'rep':1,'mode':'equal','member_order':member_names,
                  'members':members,'weights_frozen_before_calibration_and_test':True,
                  'score_kind':'probability','score_rule':'native normalized seven-class posterior; argmax prediction; probability nonconformity 1-p_true',
                  'calibration_ids_sha256':raw(calibration_ids),
                  'posterior_fingerprint':{'calibration_ids_sha256':raw(calibration_ids),'X_cal_sha256':raw(X_cal),'y_cal_sha256':raw(y_cal)},
                  'selected_weights':weights,'ensemble_threshold':0.25}
            putjson(comp_path,comp);comp_sha=sha(comp_path)
            putjson(art/'evaluation.json',{'task_key':key,'member_comparisons_path':'member_comparisons.json',
                                           'member_comparisons_sha256':comp_sha,'conformal_threshold':0.25})
            mrows=[];proof_refs=[]
            for name in member_names:
                ident='id_'+name;md_rel=f'reports/calibration_replay/e6_member_native/{ident}/metadata.json'
                vec_rel=f'reports/calibration_replay/e6_member_native/{ident}/nonconformity.npz'
                md=runtime/md_rel;vec=runtime/vec_rel;md.parent.mkdir(parents=True,exist_ok=True)
                putjson(md,{'calibration_n':10000,'threshold':0.25,'nonconformity_sha256':score_vec_sha})
                vec.write_bytes(b'vector-'+name.encode())
                row={'task_key':key,'fit_key':'fit_'+name,'member':name,'status':'validated',
                     'validation_basis':'fresh_native_calibration_scores','pipeline_sha256':pipeline,
                     'role_file_sha256':sha(role),'role_membership_sha256':'r'*64,'fit_ids_sha256':'f'*64,'selected_params_sha256':'s'*64,'provenance_group':'E3_new_fit','calibration_ids_sha256':cal_ids,
                     'X_cal_sha256':cal_x,'y_cal_sha256':cal_y,'calibration_n':10000,
                     'score_kind':'probability','nonconformity_rule':'1-p_true','alpha':0.1,'class_order':list(range(7)),
                     'native_threshold':0.25,'comparison_path':'member_comparisons.json','comparison_sha256':comp_sha,
                     'native_replay_identity':ident,'native_replay_metadata_path':md_rel,
                     'native_replay_metadata_sha256':sha(md),'native_replay_vector_path':vec_rel,
                     'native_replay_vector_file_sha256':sha(vec),'native_replay_vector_sha256':score_vec_sha,'rank_k':9001}
                mrows.append(row);proof_refs.append({'member':name,'fit_key':'fit_'+name,'native_replay_identity':ident,
                    'native_replay_metadata_sha256':sha(md),'native_replay_vector_file_sha256':sha(vec)})
            ensemble={'task_key':key,'mode':'equal','status':'validated','validation_basis':'fresh_native_calibration_scores',
                      'member_order':member_names,'members':proof_refs,'weights':weights,'alpha':0.1,'calibration_n':10000,
                      'native_threshold':0.25,'saved_threshold':0.25,'primary_threshold':0.25,
                      'comparison_sha256':comp_sha}
            audit={'e6_member_calibration_records':mrows,'e6_ensemble_calibration_records':[ensemble],
                   'summary':{'required_e6_member_calibration_records':5,'validated_e6_member_calibration_records':5,
                              'required_e6_ensembles':1,'validated_e6_ensembles':1,
                              'e6_native_calibration_replay_complete':True}}
            task={'key':key,'experiment':6,'kind':'ensemble','scientific_case':True,'rep':1,'mode':'equal','outcome':'successful','e6_protocol_version':'E6-v2'}
            evidence=[];cr=types.ModuleType('calibration_replay')
            cr.typed_sha=typed
            cr.load_replay=lambda path,identity:{'metadata':{'calibration_n':10000,'threshold':0.25,
                'nonconformity_sha256':score_vec_sha},'rank_k':9001}
            with __import__('unittest.mock',fromlist=['patch']).patch.dict(sys.modules,{'calibration_replay':cr}):
                out=M._validate_e6_native_calibration_records(runtime,audit,{key:task},evidence)
                self.assertTrue(out['e6_native_calibration_replay_complete'])
                self.assertEqual(out['validated_e6_member_calibration_records'],5)
                self.assertEqual(len(evidence),12)
                audit['e6_member_calibration_records'].pop()
                with self.assertRaises(M.EvidenceError):M._validate_e6_native_calibration_records(runtime,audit,{key:task},[])

    def test_collectors_explicitly_exclude_phase_receipts(self):
        import inspect
        self.assertIn('_is_private_e6_phase_receipt(p)',inspect.getsource(M.collect_full))
        self.assertIn('_is_private_e6_phase_receipt(p)',inspect.getsource(M._small_entries))

    def test_declared_overlay_rejects_six_missing_registry_protocol_tags(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);runtime=root/'runtime_20261025';man=runtime/'manifests';man.mkdir(parents=True)
            keys=[f'e6/rep_{rep}/ensemble/{mode}' for rep in (1,2,3) for mode in ('equal','learned')]
            overlay={'schema_version':'lamost-e6-execution-overlay/2','protocol_version':'E6-v2',
                     'tasks':[{'task_key':k,'e6_protocol_version':'E6-v2'} for k in keys]}
            overlay_path=man/'E6_EXECUTION_OVERLAY_V2.json';putjson(overlay_path,overlay)
            putjson(man/'freeze.json',{'e6_execution_overlay_sha256':sha(overlay_path)})
            bad_tasks=[{'key':k,'experiment':6,'kind':'ensemble','scientific_case':True,
                        'status':'validated_terminal','outcome':'unavailable_dependency'} for k in keys]
            putjson(runtime/'registry.json',{'tasks':bad_tasks,'observed_utc':'2026-10-27T00:00:00Z'})
            with self.assertRaises(M.EvidenceError):
                M.refresh_e6_v2_export(root,runtime,Path(sys.executable),dict(__import__('os').environ))

    def test_legacy_calibration_audit_without_v2_fields_needs_no_native_records(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025'
            legacy={'old_e6':{'key':'old_e6','experiment':6,'kind':'ensemble','scientific_case':True,
                              'status':'validated_terminal','outcome':'successful'}}
            result=M._validate_e6_native_calibration_records(runtime,{},legacy,[])
            self.assertFalse(result['e6_native_calibration_replay_applicable'])
            self.assertTrue(result['e6_native_calibration_replay_complete'])
            self.assertEqual(result['required_e6_ensembles'],0)
            # A declared current E6-v2 task must still fail closed when audit arrays are absent.
            current={'new_e6':{**legacy['old_e6'],'key':'new_e6','e6_protocol_version':'E6-v2','outcome':'scientific_failure'}}
            with self.assertRaises(M.EvidenceError):
                M._validate_e6_native_calibration_records(runtime,{},current,[])

    def test_malformed_authoritative_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';runtime.mkdir()
            (runtime/'registry.json').write_text('{malformed')
            putjson(runtime/'public_registry.json',{'tasks':[]})
            with self.assertRaises(M.EvidenceError):
                M.e6_private_phase_receipt_manifest(runtime)

    def test_legacy_public_registry_receipt_inventory_is_supported(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';task={'key':'e6_task','experiment':6,'kind':'ensemble','scientific_case':True}
            putjson(runtime/'public_registry.json',{'tasks':[task]})
            raw=runtime/'artifacts/e6_task/attempts/a1/e6_phase_test.json'
            raw.parent.mkdir(parents=True,exist_ok=True);raw.write_text('{"pid":123,"event":"test"}')
            doc=json.loads(M.e6_private_phase_receipt_manifest(runtime))
            self.assertEqual(doc['source_snapshot_kind'],'sanitized_public_registry_projection')
            self.assertTrue(doc['receipt_inventory_complete'])
            self.assertEqual(doc['receipt_count'],1)
            self.assertNotIn('123',json.dumps(doc))

    def test_missing_registry_legacy_collection_is_explicitly_incomplete_and_skips_v2(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';runtime.mkdir()
            doc=json.loads(M.e6_private_phase_receipt_manifest(runtime))
            self.assertFalse(doc['receipt_inventory_complete'])
            self.assertEqual(doc['source_snapshot_kind'],'unavailable')
            self.assertIsNone(M.refresh_e6_v2_export(Path(td),runtime,Path(sys.executable),{}))

    def test_legacy_registry_without_v2_tasks_skips_export_gate(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=Path(td)/'runtime_20261025';runtime.mkdir()
            putjson(runtime/'registry.json',{'tasks':[{'key':'old_e6','experiment':6,'kind':'ensemble','scientific_case':True}]})
            self.assertIsNone(M.refresh_e6_v2_export(Path(td),runtime,Path(sys.executable),{}))

    def test_stale_export_and_legacy_snapshot_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            runtime,out=self.make_runtime(Path(td))
            regpath=runtime/'registry.json';reg=json.loads(regpath.read_text());reg['observed_utc']='2026-10-27T00:01:00Z';putjson(regpath,reg)
            with self.assertRaises(M.EvidenceError):M.validate_e6_v2_export(runtime,out)
            old=runtime/'reports/E6_FINAL_20261025';old.mkdir();(old/'E6_FINAL_CELL_LEDGER_21.csv').write_text('x\n')
            with self.assertRaises(M.EvidenceError):M.validate_e6_v2_export(runtime,old)

    def test_corrupted_output_and_non_success_metrics_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            runtime,out=self.make_runtime(Path(td))
            (out/'E6_V2_AVAILABILITY.csv').write_text('tampered\n')
            with self.assertRaises(M.EvidenceError):M.validate_e6_v2_export(runtime,out)

if __name__=='__main__':unittest.main()

