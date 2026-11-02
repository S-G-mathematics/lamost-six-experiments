import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

RUNTIME=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025')
ENGINE=RUNTIME/'staging/e6_feature_order_fix_20261028/source'
sys.path.insert(0,str(ENGINE))
sys.path.insert(0,str(RUNTIME.parent/'project'))

import ensemble as e6
import e6_phase_supervisor as supervisor
from benchmark import evaluation

def _successful_phase(conn):
    conn.send({'status':'success','rows':7})

def _slow_phase(conn):
    time.sleep(5)
    conn.send({'status':'success'})

def _posterior(y, correct_probability, shift=0):
    out=np.full((len(y),7),(1.0-correct_probability)/6,dtype=float)
    pred=(np.asarray(y,dtype=int)+int(shift))%7
    out[np.arange(len(y)),pred]=correct_probability
    return out

class E6ProtocolCorrectionTests(unittest.TestCase):
    def test_v2_fit_dependencies_ignore_historical_e3_eval_failures(self):
        members={name:f'e3/rep_1/fit/{name}' for name in e6.MEMBERS}
        task={'e6_protocol_version':'E6-v2','members':members,
              'member_evaluations':{name:f'e3/rep_1/eval/direct/{name}' for name in e6.MEMBERS},
              'member_evaluation_dependency_observations':{
                  f'e3/rep_1/eval/direct/{name}':{'status':'validated_terminal','outcome':'scientific_failure'}
                  for name in e6.MEMBERS}}
        self.assertEqual(e6._member_evaluation_preflight(task)['state'],'ready')
        task['members'].pop('kde')
        result=e6._member_evaluation_preflight(task)
        self.assertEqual(result['state'],'unavailable')
        self.assertIn('kde',result['missing_members'])

    def test_v1_historical_gate_is_unchanged(self):
        task={'member_evaluations':{'kde':'e3/rep_1/eval/direct/kde'},
              'member_evaluation_dependency_observations':{
                  'e3/rep_1/eval/direct/kde':{'status':'validated_terminal','outcome':'scientific_failure'}}}
        self.assertEqual(e6._member_evaluation_preflight(task)['state'],'unavailable')
        self.assertIn('scientific_failure',e6._member_evaluation_preflight(task)['reason'])

    def test_member_metrics_use_tune_best_then_individual_calibration(self):
        yt=np.repeat(np.arange(7,dtype=np.int64),10)
        yc=yt.copy(); ytest=yt.copy()
        tune={'gmm':_posterior(yt,.80),'copula':_posterior(yt,.95,1),
              'arf':_posterior(yt,.75),'kde':_posterior(yt,.70),'chow_liu':_posterior(yt,.65)}
        cal={name:_posterior(yc,p) for name,p in zip(e6.MEMBERS,[.90,.82,.75,.68,.61])}
        test={'gmm':_posterior(ytest,.60,1),'copula':_posterior(ytest,.95),
              'arf':_posterior(ytest,.75),'kde':_posterior(ytest,.68),'chow_liu':_posterior(ytest,.61)}
        fits={name:f'e3/rep_1/fit/{name}' for name in e6.MEMBERS}
        hashes={name:(name*64)[:64] for name in e6.MEMBERS}
        fit_hashes={name:'fitids-'+name for name in e6.MEMBERS}
        evidence={name:{'role_membership_sha256':'roles','provenance_group':'e2_reconstructed',
                        'selection_sha256':'sel-'+name,'fit_result_sha256':'fit-'+name,
                        'validation_sha256':'val-'+name,'selected_params_sha256':'params-'+name}
                  for name in e6.MEMBERS}
        payload=e6._member_comparison_payload(
            task={'key':'e6/rep_1/ensemble/learned','rep':1},members=fits,
            model_hashes=hashes,fit_hashes=fit_hashes,member_fit_evidence=evidence,
            fingerprint={'identity':'fixture'},tune_ids=np.arange(70),cal_ids=np.arange(100,170),
            test_ids=np.arange(200,270),phase_times={'tune_cache_hit':False},
            tune_scores=tune,cal_scores=cal,test_scores=test,y_tune=yt,y_cal=yc,y_test=ytest,
            weights=np.array([.2]*5),mode='learned',weights_obj={'weights':[.2]*5},
            ensemble_threshold=.3,ensemble_result=evaluation.conformal_evaluate(
                _posterior(ytest,.8),ytest,.3,'probability'),evaluator=evaluation,
            candidate_ledger_path='candidate_ledger.json',candidate_ledger_sha256='ledgerhash',
            weights_frozen_utc='2026-10-27T00:00:00+00:00')
        self.assertEqual(payload['tuning_best_member'],'gmm')
        self.assertGreater(payload['members']['copula']['evaluation']['balanced_accuracy'],payload['members']['gmm']['evaluation']['balanced_accuracy'])
        self.assertEqual(payload['weights_frozen_before_calibration_and_test'],True)
        self.assertEqual(payload['comparison_source_task_key'],'e6/rep_1/ensemble/learned')
        self.assertEqual(payload['selected_weights'],[.2]*5)
        self.assertEqual(payload['candidate_ledger_sha256'],'ledgerhash')
        self.assertEqual(payload['member_order'],list(e6.MEMBERS))
        self.assertEqual(payload['members']['gmm']['calibration_n'],70)
        self.assertEqual(payload['members']['gmm']['test_n'],70)
        self.assertIn('coverage',payload['members']['kde']['evaluation'])
        self.assertIn('set_size',payload['ensemble_evaluation'])

    def test_selected_fit_evidence_binds_pipeline_selection_validation_and_roles(self):
        with tempfile.TemporaryDirectory() as d:
            runtime=Path(d); key='e3/rep_1/fit/gmm'; base=runtime/'artifacts'/key; base.mkdir(parents=True)
            fit_ids=np.arange(80000,dtype=np.int64)
            fit_y=(fit_ids%7).astype(np.int8)
            ids_sha=e6._sha(fit_ids); counts=np.bincount(fit_y,minlength=7).tolist()
            params={'n_components':2,'covariance_type':'full'}
            import hashlib
            params_sha=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            pipeline=base/'pipeline.joblib'; pipeline.write_bytes(b'tiny-pipeline-byte-fixture')
            selection=base/'selection.json'; selection.write_text(json.dumps({'selected_params':params},sort_keys=True))
            pipeline_sha=e6._member_comparison_file_sha(pipeline); selection_sha=e6._member_comparison_file_sha(selection)
            fit_result={'status':'successful','artifact_sha256':pipeline_sha,'task':{'key':key},
                        'result':{'status':'success','training_ids_sha256':ids_sha,'class_counts':counts,'params':params}}
            fr=base/'fit_result.json'; fr.write_text(json.dumps(fit_result,sort_keys=True))
            validation={'status':'validated','task_key':key,'files':{'pipeline.joblib':pipeline_sha,'selection.json':selection_sha}}
            val=base/'validation.json'; val.write_text(json.dumps(validation,sort_keys=True))
            order=['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']
            evidence={'fit_key':key,'method':'gmm','pipeline_sha256':pipeline_sha,
                      'selection_sha256':selection_sha,'fit_result_sha256':e6._member_comparison_file_sha(fr),
                      'validation_sha256':e6._member_comparison_file_sha(val),'role_membership_sha256':'rolehash',
                      'training_ids_sha256':ids_sha,'training_rows':80000,'class_order':list(range(7)),
                      'feature_order':order,'provenance_group':'e2_reconstructed',
                      'selected_params_sha256':params_sha,'class_counts':counts}
            all_evidence={m:{**evidence,'fit_key':f'e3/rep_1/fit/{m}','method':m} for m in e6.MEMBERS}
            # Frozen manifest trio ties the six-column order and role receipt to this tiny fixture.
            manifest_dir=runtime/'manifests'; manifest_dir.mkdir(parents=True)
            cache_dir=runtime/'cache'; cache_dir.mkdir(parents=True)
            e3_manifest={'features':order,'role_hashes':{'1':{'source_sha256':'rolehash'}}}
            e3_path=manifest_dir/'E3_MANIFEST.json'; e3_path.write_text(json.dumps(e3_manifest,sort_keys=True))
            e3_sha=e6._member_comparison_file_sha(e3_path)
            overlay={'schema_version':'lamost-e6-execution-overlay/2','protocol_version':'E6-v2','source_e3_manifest_sha256':e3_sha}
            (manifest_dir/'E6_EXECUTION_OVERLAY_V2.json').write_text(json.dumps(overlay,sort_keys=True))
            (cache_dir/'cache_manifest.json').write_text(json.dumps({'features':order},sort_keys=True))
            task={'rep':1,'member_fit_evidence':all_evidence}
            pipe={'params':params,'method':'gmm','training_ids_sha256':ids_sha,'training_rows':80000,'feature_order':order}
            verified=e6._e6_v2_validate_member_artifacts(runtime,task,'gmm',key,pipe,pipeline,fit_ids,fit_y)
            self.assertEqual(verified['pipeline_sha256'],pipeline_sha)
            self.assertEqual(verified['provenance_group'],'e2_reconstructed')
            selection.write_text(json.dumps({'selected_params':{'n_components':4}},sort_keys=True))
            with self.assertRaises(ValueError):
                e6._e6_v2_validate_member_artifacts(runtime,task,'gmm',key,pipe,pipeline,fit_ids,fit_y)

    def test_posterior_receipt_binds_fingerprint_file_and_arrays(self):
        scores={name:_posterior(np.arange(7),.8) for name in e6.MEMBERS}
        fingerprint={'pipeline_sha256':{'gmm':'a'},'ids':'roles'}
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/'tune.npz'
            np.savez_compressed(cache,**scores)
            loaded=e6._load_scores(cache)
            receipt=e6._posterior_receipt('tune',cache,loaded,fingerprint)
            recpath=Path(d)/'tune.receipt.json'
            recpath.write_text(json.dumps(receipt))
            e6._verify_posterior_receipt('tune',cache,recpath,loaded,fingerprint)
            changed=dict(receipt); changed['fingerprint_sha256']='0'*64
            recpath.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                e6._verify_posterior_receipt('tune',cache,recpath,loaded,fingerprint)

    def test_supervisor_ready_identity_durable_state_and_verified_group(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'phase.json'; events=Path(d)/'events.jsonl'
            result=supervisor.run_phase(target=_successful_phase,args=(),state_path=state,
                event_path=events,task_key='e6/rep_1/ensemble/equal',attempt_id='attempt_fixture',
                stage='tune',request_path='request.json',request_sha256='0'*64,worker_script_sha256='1'*64,timeout_seconds=10,rss_limit_kib=1024*1024,grace_seconds=1)
            self.assertEqual(result['status'],'successful')
            self.assertEqual(result['child_pid'],result['child_pgid'])
            self.assertEqual(result['child_uid'],__import__('os').getuid())
            saved=json.loads(state.read_text())
            self.assertEqual(saved['attempt_id'],'attempt_fixture')
            self.assertEqual(saved['role'],'e6_prediction_phase')
            self.assertEqual(saved['request_sha256'],'0'*64)
            self.assertEqual(saved['status'],'successful')
            self.assertEqual([json.loads(x)['event'] for x in events.read_text().splitlines()],
                             ['starting','running','finished'])

    def test_supervisor_timeout_is_terminal_and_reaps_own_group(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'phase.json'; events=Path(d)/'events.jsonl'
            result=supervisor.run_phase(target=_slow_phase,args=(),state_path=state,
                event_path=events,task_key='e6/rep_1/ensemble/equal',attempt_id='attempt_timeout',
                stage='test',request_path='request.json',request_sha256='0'*64,worker_script_sha256='1'*64,timeout_seconds=.25,rss_limit_kib=1024*1024,grace_seconds=1)
            self.assertEqual(result['status'],'scientific_failure')
            self.assertEqual(result['reason'],'timeout')
            self.assertEqual(supervisor._group_pids(result['child_pgid']),[])

if __name__=='__main__':
    unittest.main()
