import sys
import unittest
import csv
import json
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from e6_v2_reporting import (
    MEMBER_ORDER, E6V2ReportError, validate_member_comparisons,
    v2_availability_rows, superseded_gate_history, summarize_comparisons,
    load_bound_member_comparisons, export_v2_outputs, _partial_tuning_evidence,
)

def metrics(value):
    return {
        'balanced_accuracy': value,
        'coverage': 0.90 + value/100,
        'set_size': 2.0 + value,
        'per_class': {str(i): {'recall': value, 'coverage': 0.9, 'set_size': 2.0} for i in range(7)},
        'confusion_matrix': [[1]*7 for _ in range(7)],
    }

def fixture(mode='equal', rep=1, key=None):
    key=key or f'e6/rep_{rep}/ensemble/{mode}'
    weights={m:0.2 for m in MEMBER_ORDER} if mode=='equal' else dict(zip(MEMBER_ORDER,[.4,.2,.15,.1,.15]))
    members={}
    for i,m in enumerate(MEMBER_ORDER):
        members[m]={
            'fit_key':f'e3/rep_{rep}/fit/{m}',
            'pipeline_sha256':f'{i+1:064x}',
            'fit_ids_sha256':'a'*64,
            'conformal_threshold':0.2+i/10,
            'calibration_n':10000,'test_n':500000,'score_kind':'probability',
            'tuning_balanced_accuracy':0.5+i/100,
            'evaluation':metrics(.5+i/100),
        }
    return {
        'schema_version':'lamost-e6-member-comparisons/1','protocol_version':'E6-v2',
        'rep':rep,'comparison_source_task_key':key,'mode':mode,'member_order':list(MEMBER_ORDER),
        'members':members,'posterior_fingerprint':f'{rep:064x}',
        'fit_ids_sha256':'a'*64,'tuning_ids_sha256':'b'*64,
        'calibration_ids_sha256':'c'*64,'test_ids_sha256':'d'*64,
        'score_rule':'probability_nonconformity_1_minus_p_true',
        'quantile_rule':'k=ceil((n_cal+1)*0.90); kth order statistic from calibration scores',
        'weights_frozen_before_calibration_and_test':True,
        'tuning_best_member':'arf','tuning_best_balanced_accuracy':0.53,
        'selected_weights':weights,'ensemble_evaluation':metrics(.61),
        'candidate_ledger_path':'candidate_ledger.json' if mode=='learned' else None,
        'candidate_ledger_sha256':'e'*64 if mode=='learned' else None,
        'phase_costs':[{'phase':'test_posterior','seconds':33.5,'peak_tree_rss_kib':1200000,'source_task_key':key,'pid':123}],
    }

class TestE6V2Reporting(unittest.TestCase):
    def test_equal_and_learned_emit_all_member_and_tuning_best_comparisons(self):
        for mode in ('equal','learned'):
            task={'key':f'e6/rep_1/ensemble/{mode}','rep':1,'mode':mode}
            result=validate_member_comparisons(fixture(mode),task)
            self.assertEqual(len(result['members']),5)
            self.assertEqual(len(result['comparisons']),6)
            self.assertEqual(result['ensemble']['tuning_best_member'],'arf')
            self.assertEqual(result['weights']['weight_gmm'], .2 if mode=='equal' else .4)
            self.assertEqual(len(result['costs']),1)
            self.assertNotIn('pid',result['costs'][0])

    def test_mode_freeze_order_and_missing_member_are_rejected(self):
        task={'key':'e6/rep_1/ensemble/equal','rep':1,'mode':'equal'}
        d=fixture()
        d['weights_frozen_before_calibration_and_test']=False
        with self.assertRaises(E6V2ReportError):
            validate_member_comparisons(d,task)
        d=fixture();d.pop('weights_frozen_before_calibration_and_test')
        with self.assertRaises(E6V2ReportError):
            validate_member_comparisons(d,task)
        d=fixture();d['members'].pop('kde')
        with self.assertRaises(E6V2ReportError):
            validate_member_comparisons(d,task)

    def test_failed_e6_phase_emits_availability_only_no_scores(self):
        task={'key':'e6/rep_1/ensemble/equal','experiment':6,'scientific_case':True,
              'kind':'ensemble','rep':1,'mode':'equal','status':'validated_terminal',
              'outcome':'scientific_failure','validation_state':'validated_terminal'}
        with __import__('tempfile').TemporaryDirectory() as td:
            rows=v2_availability_rows([task],td,loader=lambda path: (_ for _ in ()).throw(AssertionError('must not load failed artifact')))
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['member_comparison_present'])
        self.assertNotIn('_normalized',rows[0])

    def test_artifact_binding_checks_eval_path_sha_and_candidate_ledger(self):
        import tempfile
        from pathlib import Path
        task={'key':'e6/rep_1/ensemble/learned','experiment':6,'scientific_case':True,
              'kind':'ensemble','rep':1,'mode':'learned','status':'validated_terminal',
              'outcome':'successful','validation_state':'validated'}
        with tempfile.TemporaryDirectory() as td:
            art=Path(td)/'artifacts'/task['key'];art.mkdir(parents=True)
            doc=fixture('learned',key=task['key'])
            (art/'candidate_ledger.json').write_text('{}',encoding='utf-8')
            doc['candidate_ledger_sha256']=hashlib.sha256((art/'candidate_ledger.json').read_bytes()).hexdigest()
            cp=art/'member_comparisons.json';cp.write_text(json.dumps(doc),encoding='utf-8')
            evaluation={'task_key':task['key'],'e6_protocol_version':'E6-v2',
                        'member_comparisons_path':'member_comparisons.json',
                        'member_comparisons_sha256':hashlib.sha256(cp.read_bytes()).hexdigest(),
                        'balanced_accuracy':.61}
            (art/'evaluation.json').write_text(json.dumps(evaluation),encoding='utf-8')
            loaded,normalized,digest=load_bound_member_comparisons(td,task)
            self.assertEqual(digest,evaluation['member_comparisons_sha256'])
            self.assertEqual(len(normalized['members']),5)
            evaluation['member_comparisons_sha256']='0'*64
            (art/'evaluation.json').write_text(json.dumps(evaluation),encoding='utf-8')
            with self.assertRaises(E6V2ReportError):
                load_bound_member_comparisons(td,task)

    def test_end_to_end_tables_keep_failed_cases_blank_and_historical_gate_separate(self):
        import tempfile
        from pathlib import Path
        tasks=[];old=[]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'artifacts').mkdir()
            for rep in (1,2,3):
                for mode in ('equal','learned'):
                    key=f'e6/rep_{rep}/ensemble/{mode}'
                    outcome='successful' if rep==1 else 'unavailable_dependency'
                    task={'key':key,'experiment':6,'scientific_case':True,'kind':'ensemble',
                          'rep':rep,'mode':mode,'status':'validated_terminal','outcome':outcome,
                          'validation_state':'validated' if outcome=='successful' else 'validated_terminal'}
                    tasks.append(task)
                    old.append({'task_key':key,'cell_kind':'primary_ensemble','rep':rep,
                                'method_or_mode':mode,'outcome':'unavailable_dependency',
                                'status':'validated_terminal','attempt_count':'0'})
                    if outcome!='successful':continue
                    art=root/'artifacts'/key;art.mkdir(parents=True)
                    d=fixture(mode,rep,key)
                    if mode=='learned':
                        (art/'candidate_ledger.json').write_text('{}',encoding='utf-8')
                        d['candidate_ledger_sha256']=hashlib.sha256((art/'candidate_ledger.json').read_bytes()).hexdigest()
                    cp=art/'member_comparisons.json';cp.write_text(json.dumps(d),encoding='utf-8')
                    ev={'task_key':key,'e6_protocol_version':'E6-v2',
                        'member_comparisons_path':'member_comparisons.json',
                        'member_comparisons_sha256':hashlib.sha256(cp.read_bytes()).hexdigest(),
                        'balanced_accuracy':.61}
                    (art/'evaluation.json').write_text(json.dumps(ev),encoding='utf-8')
            for rep in (1,2,3):
                for member in MEMBER_ORDER:
                    old.append({'task_key':f'e6/rep_{rep}/eval/member/{member}',
                                'cell_kind':'member_reference','rep':rep,'method_or_mode':member,
                                'family':member,'outcome':'successful','status':'validated_terminal',
                                'evaluation_present':'True','attempt_count':'1'})
            oldpath=root/'old.csv'
            with oldpath.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=sorted({k for row in old for k in row}));w.writeheader();w.writerows(old)
            counts=export_v2_outputs(root,tasks,oldpath,root/'out')
            self.assertEqual(counts['E6_V2_MAIN_CELL_LEDGER_21.csv'],21)
            self.assertEqual(counts['E6_V2_ENSEMBLE_REPETITIONS.csv'],2)
            self.assertEqual(counts['E6_V2_MEMBER_COMPARISONS.csv'],10)
            self.assertEqual(counts['E6_V2_PER_CLASS_COMPARISONS.csv'],84)
            self.assertEqual(counts['E6_SUPERSEDED_AVAILABILITY_GATE_HISTORY.csv'],6)
            self.assertEqual(counts['E6_V2_PARTIAL_TUNING_EVIDENCE.csv'],6)
            with (root/'out'/'E6_V2_MAIN_CELL_LEDGER_21.csv').open() as f:
                main=list(csv.DictReader(f))
            self.assertEqual(sum(r['provenance_group']=='historical_E3_direct_reference_not_E6_scoring' for r in main),15)
            self.assertEqual(sum(r['provenance_group']=='E6_v2_primary_ensemble' for r in main),6)
            with (root/'out'/'E6_V2_AVAILABILITY.csv').open() as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),6)
            self.assertEqual(sum(r['member_comparison_present']=='True' for r in rows),2)
            self.assertEqual(counts['E6_V2_MODE_PAIRED.csv'],1)

    def test_failed_test_phase_retains_valid_frozen_weights_and_candidate_ledger(self):
        with __import__('tempfile').TemporaryDirectory() as td:
            root=Path(td);key='e6/rep_2/ensemble/learned'
            task={'key':key,'experiment':6,'scientific_case':True,'kind':'ensemble','rep':2,
                  'mode':'learned','status':'validated_terminal','outcome':'scientific_failure',
                  'validation_state':'validated_terminal','reason':'test posterior phase timed out'}
            art=root/'artifacts'/key;art.mkdir(parents=True)
            weights=[.4,.2,.15,.1,.15]
            candidates=[{'candidate':0,'weights':weights,'balanced_accuracy':.72},
                        {'candidate':1,'weights':[.2]*5,'balanced_accuracy':.70}]
            ledger={'weights':weights,'tuning_balanced_accuracy':.72,'selected_candidate':0,
                    'candidate_count':2,'candidate_cap':2000,'member_order':list(MEMBER_ORDER),
                    'search':'fixture only','seed':44321,'candidates':candidates}
            (art/'candidate_ledger.json').write_text(json.dumps(ledger),encoding='utf-8')
            frozen={'mode':'learned','member_order':list(MEMBER_ORDER),'weights':weights,
                    'frozen_before_calibration_and_test':True,'weights_frozen_utc':'2026-10-27T12:00:00Z',
                    'weight_search_seed':44321,'fingerprint':{'fit_ids_sha256':'a'*64},
                    'candidate_ledger':'candidate_ledger.json'}
            (art/'frozen_weights.json').write_text(json.dumps(frozen),encoding='utf-8')
            out=root/'out';out.mkdir()
            rows,weight_rows=_partial_tuning_evidence(root,[task],out)
            self.assertEqual(len(rows),1)
            row=rows[0]
            self.assertEqual(row['evidence_state'],'validated_frozen_tuning_evidence')
            self.assertIn('calibration/test phases not evidenced',row['stage'])
            self.assertFalse(row['performance_metrics_included'])
            self.assertEqual(row['test_evaluation_present'],'False')
            self.assertEqual(row['candidate_count'],2)
            self.assertEqual(len(weight_rows),1)
            self.assertEqual(json.loads(row['weights_json']),weights)
            self.assertEqual((out/row['frozen_weights_archive_path']).read_bytes(),(art/'frozen_weights.json').read_bytes())
            self.assertEqual((out/row['candidate_ledger_archive_path']).read_bytes(),(art/'candidate_ledger.json').read_bytes())

    def test_success_requires_saved_comparison_artifact_and_validation(self):
        task={'key':'e6/rep_1/ensemble/equal','experiment':6,'scientific_case':True,
              'kind':'ensemble','rep':1,'mode':'equal','status':'validated_terminal',
              'outcome':'successful','validation_state':'validated'}
        with __import__('tempfile').TemporaryDirectory() as td:
            row=v2_availability_rows([task],td,loader=lambda path:fixture())[0]
        self.assertTrue(row['member_comparison_present'])
        self.assertEqual(len(row['_normalized']['members']),5)

    def test_old_zero_attempt_gate_rows_are_preserved_as_superseded_history(self):
        old=[];tasks=[]
        for rep in (1,2,3):
            for mode in ('equal','learned'):
                key=f'e6/rep_{rep}/ensemble/{mode}'
                old.append({'task_key':key,'cell_kind':'primary_ensemble','rep':rep,'method_or_mode':mode,
                            'outcome':'unavailable_dependency','status':'validated_terminal',
                            'attempt_count':'0'})
                tasks.append({'key':key,'outcome':'successful'})
        rows=superseded_gate_history(old,tasks)
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r['history_classification']=='superseded_runtime_gate_history_not_scientific_failure' for r in rows))
        self.assertTrue(all(r['current_outcome']=='successful' for r in rows))

    def test_summaries_keep_modes_separate_and_sample_sd_undefined_at_n1(self):
        rows=[]
        for mode,delta in (('equal',.1),):
            for comp_kind,comp in [('member','gmm'),('tuning_best','arf')]:
                rows.append({'mode':mode,'comparison_kind':comp_kind,'comparator':comp,'rep':1,
                             'ensemble_minus_comparator_balanced_accuracy':delta,
                             'ensemble_minus_comparator_coverage':-.01,
                             'ensemble_minus_comparator_set_size':.2})
        summary=summarize_comparisons(rows)
        gmm=next(x for x in summary if x['mode']=='equal' and x['comparator']=='gmm')
        self.assertEqual(gmm['matched_n'],1)
        self.assertEqual(gmm['balanced_accuracy_mean'],.1)
        self.assertEqual(gmm['balanced_accuracy_sample_sd'],'')
        self.assertEqual(len(summary),12)

if __name__=='__main__':
    unittest.main()
