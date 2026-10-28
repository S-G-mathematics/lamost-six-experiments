import sys, unittest, json, tempfile, hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'source'))
import admission_evidence as ae
import controller

class ProfileGateTests(unittest.TestCase):
    def test_arf_domain_is_narrow_and_count_aware(self):
        p={'num_trees':300,'min_samples_leaf':5,'max_depth':10,'density_dist':'truncnorm','finite_bounds':'no'}
        self.assertTrue(ae._arf_selected_params_in_domain(p,[200]*7))
        self.assertFalse(ae._arf_selected_params_in_domain({**p,'num_trees':500},[200]*7))
        self.assertFalse(ae._arf_selected_params_in_domain({**p,'min_samples_leaf':20},[10]*7))
        self.assertFalse(ae._arf_selected_params_in_domain({**p,'finite_bounds':'yes'},[200]*7))

    def test_e4_eval_rejects_attempted_and_wrong_route_before_artifact_access(self):
        definition={'key':'e4/rep_1/eval/direct/arf/A_half','experiment':4,'kind':'eval','route':'direct','method':'arf','rep':1,'condition':'A_half'}
        with patch.object(ae,'_valid_cohort',side_effect=AssertionError('unexpected artifact access')):
            self.assertEqual(ae.eligible_e4_direct_arf_eval_2gib({'key':definition['key'],'attempts':[{}]},definition,'/nonexistent'),(False,None))
            wrong={**definition,'route':'treatment'}
            self.assertEqual(ae.eligible_e4_direct_arf_eval_2gib({'key':definition['key']},wrong,'/nonexistent'),(False,None))

    def test_e4_generation_rejects_wrong_key_or_attempt_before_artifact_access(self):
        definition={'key':'e4/rep_1/generate/A_half/arf','experiment':4,'kind':'generate','generator':'arf','rep':1,'condition':'A_half','dependencies':['fit','cohort'],'fit_key':'fit','cohort_key':'cohort','target_class':0,'added_count':1000,'restored_share':'original_target_share','shared_across_learners':True}
        with patch.object(ae,'_valid_cohort',side_effect=AssertionError('unexpected artifact access')):
            self.assertEqual(ae.eligible_e4_arf_generation_2gib({'key':definition['key'],'attempts':[{}]},definition,'/nonexistent'),(False,None))
            wrong={**definition,'key':'e4/rep_1/generate/A_half/extra_trees'}
            self.assertEqual(ae.eligible_e4_arf_generation_2gib({'key':wrong['key']},wrong,'/nonexistent'),(False,None))

    def test_e5_generation_rejects_unknown_condition_and_attempt(self):
        definition={'key':'e5/rep_1/generate/feature_noise_05/arf','experiment':5,'kind':'generate','generator':'arf','rep':1,'condition':'feature_noise_05','mechanism':'feature_noise','rate':0.05,'dependencies':['fit'],'fit_key':'fit','n_rows':400000,'shared_across_learners':True}
        self.assertEqual(ae.eligible_e5_arf_generation_2gib({'key':definition['key'],'attempts':[{}]},definition,'/nonexistent'),(False,None))
        wrong={**definition,'condition':'label_noise_20'}
        self.assertEqual(ae.eligible_e5_arf_generation_2gib({'key':definition['key']},wrong,'/nonexistent'),(False,None))

    def test_controller_only_assigns_new_generation_profile_when_gate_passes(self):
        t={'key':'e4/rep_1/generate/A_half/arf','kind':'generate','experiment':4,'generator':'arf'}
        evidence={'profile_id':ae.E4_ARF_GENERATION_2G_PROFILE_ID,'reservation_gib':2}
        with patch.object(controller,'_rf4_fit_eligible',return_value=None), patch.object(controller,'DEFINITIONS',{t['key']:{}}), patch.object(controller,'R','/tmp'), patch.object(ae,'eligible_e4_arf_generation_2gib',return_value=(True,evidence)), patch.object(ae,'eligible_e5_arf_generation_2gib',return_value=(False,None)):
            self.assertEqual(controller.worker_reservation_bytes(t),2*controller.GIB)
            self.assertEqual(controller.worker_resource_class(t),'light')

    def test_attempted_promoted_and_non_arf_keep_heavy_reservation(self):
        promoted={'kind':'generate','experiment':4,'generator':'arf','adaptive_promoted_heavy':True}
        attempted={'kind':'generate','experiment':4,'generator':'arf','attempts':[{}]}
        unrelated={'kind':'generate','experiment':4,'generator':'extra_trees'}
        self.assertEqual(controller.worker_reservation_bytes(promoted),10*controller.GIB)
        self.assertEqual(controller.worker_reservation_bytes(attempted),10*controller.GIB)
        self.assertEqual(controller.worker_reservation_bytes(unrelated),10*controller.GIB)


    def _e5_positive_fixture(self):
        td=tempfile.TemporaryDirectory()
        root=Path(td.name)
        fit='e5/rep_1/fit/direct/arf/feature_noise_05'
        train='e5/rep_1/corruption/feature_noise_05'
        clean='e3/rep_1/fit/arf'
        for key in (fit,train,clean):
            (root/'artifacts'/key).mkdir(parents=True,exist_ok=True)
        data=root/'artifacts'/train/'data.npz'
        data.write_bytes(b'tiny fixture payload')
        pipeline=root/'artifacts'/fit/'pipeline.joblib'
        pipeline.write_bytes(b'tiny pipeline fixture')
        counts=[12000,12000,12000,12000,12000,10000,10000]
        params={'num_trees':300,'min_samples_leaf':5,'max_depth':10,'density_dist':'truncnorm','finite_bounds':'no'}
        (root/'artifacts'/train/'validation.json').write_text('{}')
        (root/'artifacts'/clean/'selection.json').write_text(json.dumps({'selected_params':params}))
        clean_doc={'task':{'route':'generator','train_key':'e3/rep_1/fit/generator/arf'},'result':{'params':params}}
        (root/'artifacts'/clean/'fit_result.json').write_text(json.dumps(clean_doc))
        fr={'task':{'key':fit,'experiment':5,'rep':1,'kind':'fit','method':'arf','route':'direct','condition':'feature_noise_05',
                    'selection_mode':'fixed','selection_policy':'frozen_clean_selected_params_no_retuning','trials':0,
                    'train_key':train,'selection_key':clean,'dependencies':[train,clean],'generator':None,'treatment':None,
                    'mechanism':'feature_noise','rate':0.05},
            'result':{'class_counts':counts,'params':params,'source_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
                      'pipeline_sha256':hashlib.sha256(pipeline.read_bytes()).hexdigest()}}
        (root/'artifacts'/fit/'fit_result.json').write_text(json.dumps(fr))
        definition={'key':'e5/rep_1/generate/feature_noise_05/arf','experiment':5,'rep':1,'kind':'generate',
                    'generator':'arf','condition':'feature_noise_05','mechanism':'feature_noise','rate':0.05,
                    'dependencies':[fit],'fit_key':fit,'n_rows':400000,'shared_across_learners':True,
                    'target_class':None,'added_count':None,'cohort_key':None,'ratio':None}
        task={'key':definition['key'],'status':'planned','attempts':[]}
        return td,root,fit,train,counts,params,definition,task

    def _run_e5_gate(self,root,train,counts,definition,task,shapes=None):
        meta={'task_key':train,'kind':'e5_corruption','rep':1,'mechanism':'feature_noise','rate':0.05}
        shape=shapes or {'X':(80000,6),'y':(80000,),'ids':(80000,)}
        audit={'review_sha256':ae.E4_E5_ARF_GENERATION_2G_AUDIT_SHA256,
               'bindings_sha256':ae.E4_E5_ARF_GENERATION_BINDINGS_SHA256}
        with patch.multiple(ae, _valid_published_fit=unittest.mock.DEFAULT,
                            _valid_npz_artifact=unittest.mock.DEFAULT,
                            _npz_label_counts=unittest.mock.DEFAULT,
                            _arf_generation_audit=unittest.mock.DEFAULT) as mocks:
            mocks['_valid_published_fit'].return_value=True
            mocks['_valid_npz_artifact'].return_value=(meta,shape)
            mocks['_npz_label_counts'].return_value=counts
            mocks['_arf_generation_audit'].return_value=audit
            result=ae.eligible_e5_arf_generation_2gib(task,definition,root)
            return result

    def test_e5_positive_context_and_provenance_mutations(self):
        td,root,fit,train,counts,params,definition,task=self._e5_positive_fixture()
        try:
            ok,evidence=self._run_e5_gate(root,train,counts,definition,task)
            self.assertTrue(ok)
            self.assertTrue(evidence['analogy_only'])
            self.assertEqual(evidence['training_class_counts'],counts)
        finally:
            td.cleanup()
        for case in ('selected_params_mismatch','source_data_sha_mismatch','wrong_shape','missing_mechanism'):
            with self.subTest(case=case):
                td,root,fit,train,counts,params,definition,task=self._e5_positive_fixture()
                try:
                    fit_path=root/'artifacts'/fit/'fit_result.json'
                    fit_doc=json.loads(fit_path.read_text())
                    clean_sel=root/'artifacts'/'e3/rep_1/fit/arf'/'selection.json'
                    shape=None
                    if case=='selected_params_mismatch':
                        bad=dict(params);bad['num_trees']=100
                        clean_sel.write_text(json.dumps({'selected_params':bad}))
                    elif case=='source_data_sha_mismatch':
                        fit_doc['result']['source_sha256']='0'*64
                        fit_path.write_text(json.dumps(fit_doc))
                    elif case=='wrong_shape':
                        shape={'X':(79999,6),'y':(79999,),'ids':(79999,)}
                    elif case=='missing_mechanism':
                        definition.pop('mechanism')
                    ok,_=self._run_e5_gate(root,train,counts,definition,task,shape)
                    self.assertFalse(ok)
                finally:
                    td.cleanup()


    def test_positive_e4_fit_and_eval_routes_for_knn_and_rbf(self):
        for method in ('knn','rbf_svm'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);condition='A_half';train=f'e4/rep_1/cohort/{condition}'
                fit=f'e4/rep_1/fit/direct/{method}/{condition}'
                art=root/'artifacts'/train;art.mkdir(parents=True)
                counts=[12000,12000,12000,12000,12000,10000,10000]
                (art/'metadata.json').write_text(json.dumps({'realized_counts':counts,'N':80000}))
                (art/'validation.json').write_text(json.dumps({'files':{'data.npz':'a'*64}}))
                d={'key':fit,'experiment':4,'rep':1,'kind':'fit','route':'direct','method':method,
                   'condition':condition,'train_key':train,'dependencies':[train],
                   'selection_mode':'tune','selection_policy':'tune_on_matching_altered_cohort',
                   'trials':5,'selection_key':None,'selection_source':None,'reuse_pipeline':None,
                   'generator':None,'treatment':None}
                task={'key':fit,'status':'planned','attempts':[]}
                evidence={'v2_sha256':ae.KNN_RBF_V2_AUDIT_SHA256}
                roles={'role_npz_sha256':'b'*64,'test_rows':500000,'calibration_shape':[10000,6],
                       'prediction_chunk_rows':50000,'role_membership_sha256':'c'*64}
                with patch.object(ae,'_knn_rbf_resource_audit',return_value=evidence), \
                     patch.object(ae,'_valid_cohort',return_value=True), \
                     patch.object(ae,'_knn_rbf_role_context',return_value=roles):
                    ok,fit_ev=ae.eligible_knn_rbf_resource_profile(task,d,root)
                self.assertTrue(ok);self.assertEqual(fit_ev['method'],method)
                eval_key=f'e4/rep_1/eval/direct/{method}/{condition}'
                ed={'key':eval_key,'experiment':4,'rep':1,'kind':'eval','route':'direct','method':method,
                    'condition':condition,'fit_key':fit,'dependencies':[fit],'train_key':None,
                    'scientific_case':True,'generator':None,'treatment':None}
                et={'key':eval_key,'status':'waiting_for_dependency','attempts':[]}
                fitted={'pipeline_sha256':'d'*64,'pipeline_bytes':1234,'roles':roles}
                with patch.object(ae,'_knn_rbf_resource_audit',return_value=evidence), \
                     patch.object(ae,'_knn_rbf_fit_artifact_context',return_value=fitted):
                    ok,eval_ev=ae.eligible_knn_rbf_resource_profile(et,ed,root)
                self.assertTrue(ok);self.assertEqual(eval_ev['method'],method)
                self.assertEqual(eval_ev['pipeline_sha256'],'d'*64)

    def test_profile_gate_rejects_attempted_promoted_and_wrong_method_route(self):
        d={'key':'e4/rep_1/fit/direct/knn/A_half','experiment':4,'rep':1,'kind':'fit','route':'direct',
           'method':'knn','condition':'A_half'}
        with patch.object(ae,'_knn_rbf_resource_audit',side_effect=AssertionError('should reject before evidence')):
            self.assertEqual(ae.eligible_knn_rbf_resource_profile({'key':d['key'],'status':'planned','attempts':[{}]},d,'/none'),(False,None))
            self.assertEqual(ae.eligible_knn_rbf_resource_profile({'key':d['key'],'status':'planned','attempts':[],'adaptive_promoted_heavy':True},d,'/none'),(False,None))
            wrong={**d,'route':'treatment'}
            self.assertEqual(ae.eligible_knn_rbf_resource_profile({'key':d['key'],'status':'planned','attempts':[]},wrong,'/none'),(False,None))


    def test_controller_admission_reservation_for_knn_and_rbf_profiles(self):
        for method,gib,profile in (('knn',2,ae.KNN_RBF_KNN_PROFILE_ID),('rbf_svm',3,ae.KNN_RBF_RBF_PROFILE_ID)):
            with self.subTest(method=method):
                key=f'e4/rep_1/fit/direct/{method}/A_half'
                task={'key':key,'experiment':4,'rep':1,'kind':'fit','method':method,'route':'direct',
                      'condition':'A_half','status':'planned','attempts':[]}
                evidence={'profile_id':profile,'reservation_gib':gib,
                          'resource_audit':{'v2_sha256':ae.KNN_RBF_V2_AUDIT_SHA256}}
                with patch.object(controller,'_rf4_fit_eligible',return_value=None), patch.object(controller,'DEFINITIONS',{key:task}), patch.object(controller,'R','/tmp'), \
                     patch.object(ae,'eligible_knn_rbf_resource_profile',return_value=(True,evidence)):
                    self.assertEqual(controller.worker_reservation_bytes(task),gib*controller.GIB)
                    self.assertEqual(controller.worker_resource_class(task),'light')
                promoted={**task,'adaptive_promoted_heavy':True}
                self.assertEqual(controller.worker_reservation_bytes(promoted),10*controller.GIB)
                self.assertEqual(controller.worker_resource_class(promoted),'heavy')


    def test_frozen_knn_control_selection_source_is_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            migration=Path(temp);root=migration/'runtime_20261025';root.mkdir()
            src=migration/'project'/'benchmark'/'results'/'e1'/'rep_1'/'n_100000'/'knn'/'complete.json'
            src.parent.mkdir(parents=True)
            params={'n_neighbors':5,'weights':'distance'}
            src.write_text(json.dumps({'status':'complete','selected_params':params}))
            sh=__import__('hashlib').sha256(src.read_bytes()).hexdigest()
            selection_dir=root/'manifests'/'imported_selections'/'e1_100000'/'rep_1'/'knn'
            selection_dir.mkdir(parents=True)
            (selection_dir/'selection.json').write_text(json.dumps({
                'selected_params':params,'source_status':'complete','source_sha256':sh,'source_path':str(src)}))
            d={'key':'e4/rep_1/fit/direct/knn/control','experiment':4,'rep':1,'kind':'fit',
               'route':'direct','method':'knn','condition':'control','train_key':None,'dependencies':[],
               'selection_source':str(selection_dir),'selection_mode':'fixed','trials':0,
               'selection_policy':'import_successful_E1_params_or_tune_if_unavailable'}
            roles={'role_npz_sha256':'a'*64}
            with patch.object(ae,'_knn_rbf_role_context',return_value=roles):
                self.assertIsNotNone(ae._knn_rbf_e4_case(d,'knn',1,'control',root))
                wrong={**d,'selection_source':str(selection_dir/'selection.json')}
                self.assertIsNone(ae._knn_rbf_e4_case(wrong,'knn',1,'control',root))
                (src).write_text(json.dumps({'status':'complete','selected_params':{'n_neighbors':3,'weights':'uniform'}}))
                self.assertIsNone(ae._knn_rbf_e4_case(d,'knn',1,'control',root))


    def test_e5_fit_provenance_matches_e4_control_for_knn_and_rbf(self):
        for method in ('knn','rbf_svm'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temp:
                migration=Path(temp);root=migration/'runtime_20261025';root.mkdir()
                rep=1;condition='feature_noise_05'
                base=f'e4/rep_{rep}/fit/direct/{method}/control'
                train=f'e5/rep_{rep}/corruption/{condition}'
                base_dir=root/'artifacts'/base;base_dir.mkdir(parents=True)
                train_dir=root/'artifacts'/train;train_dir.mkdir(parents=True)
                data=train_dir/'data.npz';data.write_bytes(b'tiny corruption fixture')
                data_sha=__import__('hashlib').sha256(data.read_bytes()).hexdigest()
                (train_dir/'validation.json').write_text(json.dumps({'files':{'data.npz':data_sha}}))
                params=({'n_neighbors':5,'weights':'distance'} if method=='knn'
                        else {'C':1.0,'gamma':0.1,'cache_size_mb':512})
                selection=base_dir/'selection.json';selection.write_text(json.dumps({'selected_params':params}))
                roles={'role_npz_sha256':'a'*64}
                selection_source=None
                if method=='knn':
                    imported_dir=root/'manifests'/'imported_selections'/'e1_100000'/f'rep_{rep}'/'knn'
                    imported_dir.mkdir(parents=True)
                    canonical=migration/'project'/'benchmark'/'results'/'e1'/f'rep_{rep}'/'n_100000'/'knn'/'complete.json'
                    canonical.parent.mkdir(parents=True)
                    canonical.write_text(json.dumps({'status':'complete','selected_params':params}))
                    source_sha=__import__('hashlib').sha256(canonical.read_bytes()).hexdigest()
                    (imported_dir/'selection.json').write_text(json.dumps({
                        'selected_params':params,'source_status':'complete','source_sha256':source_sha,'source_path':str(canonical)}))
                    selection_source=str(imported_dir)
                parent={'task':{'key':base,'kind':'fit','experiment':4,'rep':rep,'method':method,
                                'route':'direct','condition':'control','train_key':None,'dependencies':[],
                                'selection_policy':'import_successful_E1_params_or_tune_if_unavailable',
                                'selection_mode':'fixed' if method=='knn' else 'tune',
                                'trials':0 if method=='knn' else 5,'selection_source':selection_source},
                        'result':{'status':'success','source_sha256':roles['role_npz_sha256'],'params':params}}
                (base_dir/'fit_result.json').write_text(json.dumps(parent))
                (base_dir/'validation.json').write_text(json.dumps({'files':{'selection.json':__import__('hashlib').sha256(selection.read_bytes()).hexdigest()}}))
                d={'key':f'e5/rep_{rep}/fit/direct/{method}/{condition}','experiment':5,'rep':rep,
                   'kind':'fit','route':'direct','method':method,'condition':condition,
                   'mechanism':'feature_noise','rate':0.05,'train_key':train,'selection_key':base,
                   'dependencies':[train,base],'selection_mode':'fixed','trials':0,
                   'selection_policy':'frozen_clean_selected_params_no_retuning','selection_source':None}
                meta={'kind':'e5_corruption','rep':rep,'mechanism':'feature_noise','rate':0.05}
                shapes={'X':(80000,6),'y':(80000,),'ids':(80000,)}
                with patch.object(ae,'_valid_cohort',return_value=True), \
                     patch.object(ae,'_valid_npz_artifact',return_value=(meta,shapes)), \
                     patch.object(ae,'_valid_published_fit',return_value=True), \
                     patch.object(ae,'_knn_rbf_role_context',return_value=roles):
                    ctx=ae._knn_rbf_e5_case(d,method,rep,condition,root)
                self.assertIsNotNone(ctx);self.assertEqual(ctx['params'],params)
                bad={**d,'selection_key':f'e4/rep_2/fit/direct/{method}/control'}
                with patch.object(ae,'_valid_cohort',return_value=True), \
                     patch.object(ae,'_valid_npz_artifact',return_value=(meta,shapes)), \
                     patch.object(ae,'_valid_published_fit',return_value=True), \
                     patch.object(ae,'_knn_rbf_role_context',return_value=roles):
                    self.assertIsNone(ae._knn_rbf_e5_case(bad,method,rep,condition,root))
                if method=='knn':
                    wrong_parent=json.loads((base_dir/'fit_result.json').read_text())
                    wrong_parent['task']['selection_source']=str((root/'manifests'/'imported_selections'/'e1_100000'/f'rep_{rep}'/'knn'/'selection.json'))
                    (base_dir/'fit_result.json').write_text(json.dumps(wrong_parent))
                    with patch.object(ae,'_valid_cohort',return_value=True), \
                         patch.object(ae,'_valid_npz_artifact',return_value=(meta,shapes)), \
                         patch.object(ae,'_valid_published_fit',return_value=True), \
                         patch.object(ae,'_knn_rbf_role_context',return_value=roles):
                        self.assertIsNone(ae._knn_rbf_e5_case(d,method,rep,condition,root))

if __name__=='__main__': unittest.main()
