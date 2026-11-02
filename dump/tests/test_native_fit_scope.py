import hashlib, importlib.util, json, pathlib, tempfile, unittest
MODULE=pathlib.Path(__file__).resolve().parents[1]/'source/archive_fit_admission.py'
sp=importlib.util.spec_from_file_location('native_fit_admission_test',MODULE); m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return hashlib.sha256(data).hexdigest()
def jwrite(path,obj):
    return write(path,json.dumps(obj,sort_keys=True).encode())
class NativeFitScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.tasks={}
        jwrite(self.root/"manifests/cold_model_store_manifest.json",{"schema_version":"lamost-cold-model-store/1","members":[]})
        source='a'*64;ids={k:('%064x'%(i+1)) for i,k in enumerate(('fit','tune','cal','test'))}
        rolehash=write(self.root/'cache/roles/rep_1.npz',b'tiny role-membership fixture')
        jwrite(self.root/'cache/cache_manifest.json',{'cache_files':{'roles/rep_1.npz':rolehash},'roles':{'1':{'source_sha256':source,'id_hashes':ids}}})
        for exp in ('E4','E5'):jwrite(self.root/f'manifests/{exp}_MANIFEST.json',{'role_hashes':{'1':{'source_sha256':source,'id_hashes':ids}}})
        dep='e4/rep_1/cohort/clean';datahash=write(self.root/'artifacts'/dep/'data.npz',b'tiny input fixture')
        depresult=self.root/'artifacts'/dep/'fit_result.json'
        jwrite(depresult,{'key':dep,'status':'successful','validation':{'status':'validated','task_key':dep,'files':{'data.npz':datahash}}})
        self.tasks[dep]={'key':dep,'status':'validated_terminal','outcome':'successful','validation_state':'validated','result_path':str(depresult)}
        selection=self.root/'manifests/imported_selections/clean/selection.json'
        jwrite(selection,{'selected_params':{'n_estimators':7}})
        self.task={'key':'e4/rep_1/fit/direct/rf','experiment':4,'kind':'fit','route':'direct','method':'random_forest','rep':1,'status':'planned','attempts':[],'dependencies':[dep],'selection_source':str(selection.parent)}
        self.definition={k:self.task[k] for k in ('key','experiment','kind','route','method','rep','selection_source')}
        self.tasks[self.task['key']]=self.task
    def tearDown(self):self.tmp.cleanup()
    def test_matching_inputs_yield_content_bound_native_proof(self):
        proof=m.native_fit_proof(self.root,self.task,self.definition,self.tasks)
        self.assertIsNotNone(proof);self.assertEqual(proof['schema'],'lamost-native-fit-input-proof/1')
        self.assertEqual(proof['role_cache']['sha256'],m._cached_sha(self.root/'cache/roles/rep_1.npz'))
    def test_attempt_reuse_and_non_fit_route_are_excluded(self):
        for changes in ({'attempts':[{'attempt_id':'old'}]},{'reuse_pipeline':True},{'route':'eval'}):
            with self.subTest(changes=changes):self.assertIsNone(m.native_fit_proof(self.root,{**self.task,**changes},self.definition,self.tasks))
    def test_failed_dependency_and_mutated_npz_are_excluded(self):
        depkey=self.task['dependencies'][0];old=self.tasks[depkey]
        self.tasks[depkey]={**old,'outcome':'scientific_failure'}
        self.assertIsNone(m.native_fit_proof(self.root,self.task,self.definition,self.tasks))
        self.tasks[depkey]=old
        write(self.root/'artifacts'/depkey/'data.npz',b'different bytes')
        self.assertIsNone(m.native_fit_proof(self.root,self.task,self.definition,self.tasks))
    def test_existing_same_task_model_result_checkpoint_or_attempt_blocks(self):
        for name in ('pipeline.joblib','fit_result.json','checkpoints/model','attempts/prior/request.json'):
            p=self.root/'artifacts'/self.task['key']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'old')
            try:self.assertIsNone(m.native_fit_proof(self.root,self.task,self.definition,self.tasks),name)
            finally:
                p.unlink()
                parent=p.parent
                while parent!=self.root/'artifacts'/self.task['key'] and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir();parent=parent.parent
    def test_symlinked_input_is_rejected(self):
        depkey=self.task['dependencies'][0];p=self.root/'artifacts'/depkey/'data.npz';p.unlink()
        target=self.root/'outside.npz';target.write_bytes(b'tiny input fixture');p.symlink_to(target)
        self.assertIsNone(m.native_fit_proof(self.root,self.task,self.definition,self.tasks))
if __name__=='__main__':unittest.main()
