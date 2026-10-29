import pathlib, hashlib, json, sys, tempfile, unittest
STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import cold_model_storage as cold
from commit_batch_child import filter_candidate_publication_aliases

class Store:
    def __init__(self,root):
        self.root=pathlib.Path(root)
        self.runtime=self.root/'runtime_20261025'
        self.archive=self.runtime/'packages'/'cold.zip'
        self.manifest=self.runtime/'manifests'/'manifest.json'
        self.journals=self.runtime/'journals'/'cold'
        self.store=cold.ColdModelStore(self.root,self.runtime,self.archive,self.manifest,self.journals)
    def _physical_path(self,rel):
        p=(self.root/rel).resolve(strict=False)
        p.relative_to(self.root.resolve())
        return p
    def __getattr__(self,name):return getattr(self.store,name)

class SelectionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.store=Store(self.root)
        self.key='e5/rep_2/fit/direct/random_forest/label_noise_20'
        self.base=f'runtime_20261025/artifacts/{self.key}'
        self.attempt='1792980174_46ff4143';self.task_sha='a'*64;self.digest='b'*64
        self.canonical=f'{self.base}/pipeline.joblib'
        self.attempt_alias=f'{self.base}/attempts/{self.attempt}/pipeline.joblib'
        self.checkpoint_alias=f'{self.base}/checkpoints/{self.task_sha}/pipeline.joblib'
        self.params={'max_depth':None,'max_features':1.0,'min_samples_leaf':1,'n_estimators':200}
        self.selection_bytes=(json.dumps({'selected_params':self.params},sort_keys=True,separators=(',',':'))+'\n').encode()
        self.selection_sha=hashlib.sha256(self.selection_bytes).hexdigest()
        self.result_doc={'task_sha256':self.task_sha,'attempt_id':self.attempt,
            'result':{'pipeline_sha256':self.digest,'status':'success','params':self.params}}
        result_bytes=(json.dumps(self.result_doc,sort_keys=True,separators=(',',':'))+'\n').encode()
        pub={'stage':'validated_publication','attempt_id':self.attempt,'task_sha256':self.task_sha,
             'pipeline_sha256':self.digest,'published_path':str((self.root/self.canonical).resolve())}
        pub_bytes=(json.dumps(pub,sort_keys=True,separators=(',',':'))+'\n').encode()
        for rel,data in [
          (f'{self.base}/selection.json',self.selection_bytes),
          (f'{self.base}/fit_result.json',result_bytes),
          (f'{self.base}/fit_publication.json',pub_bytes),
          (f'{self.base}/attempts/{self.attempt}/attempt.json',result_bytes),
          (f'{self.base}/attempts/{self.attempt}/fit_publication.json',pub_bytes),
          (f'{self.base}/checkpoints/{self.task_sha}/selection.json',self.selection_bytes)]:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.owner={'key':self.key,'kind':'fit','status':'validated_terminal','method':'random_forest',
          'experiment':5,'artifact_dir':str((self.root/'runtime_20261025/artifacts'/self.key).resolve()),
          'result':{'task_sha256':self.task_sha,'attempt_id':self.attempt,
            'validation':{'files':{'selection.json':self.selection_sha}}}}
        self.records={self.key:self.owner}
        self.item={'producer_task':self.key,'source_relpath':self.canonical,'source_sha256':self.digest,
          'recorded_artifact_sha256':self.digest,'aliases':[self.canonical,self.attempt_alias,self.checkpoint_alias]}
    def filter(self):return filter_candidate_publication_aliases([self.item],self.records,self.store)
    def test_missing_attempt_and_checkpoint_selection_use_only_canonical_validated_bytes(self):
        (self.root/f'{self.base}/checkpoints/{self.task_sha}/selection.json').unlink()
        evidence=self.store.store._alias_publication_evidence(self.owner,self.attempt_alias,self.digest)
        self.assertEqual(evidence['selection_binding'],'canonical_validation_sha_fallback/1')
        self.assertEqual(evidence['selection_missing_copies'],['attempt','checkpoint'])
        eligible,receipt=self.filter()
        self.assertEqual(eligible,[self.item]);self.assertEqual(receipt['excluded_group_count'],0)
        self.assertFalse((self.root/f'{self.base}/attempts/{self.attempt}/selection.json').exists())
        self.assertFalse((self.root/f'{self.base}/checkpoints/{self.task_sha}/selection.json').exists())
    def test_missing_publication_receipt_still_excludes_legacy_e3_style_group(self):
        (self.root/f'{self.base}/fit_publication.json').unlink()
        (self.root/f'{self.base}/attempts/{self.attempt}/fit_publication.json').unlink()
        eligible,receipt=self.filter()
        self.assertEqual(eligible,[]);self.assertEqual(receipt['excluded_group_count'],1)
        self.assertIn('fit_publication.json',receipt['exclusions'][0]['reason'])
    def test_validation_hash_or_result_params_mismatch_rejects_fallback(self):
        self.owner['result']['validation']['files']['selection.json']='c'*64
        eligible,receipt=self.filter();self.assertEqual(eligible,[])
        self.owner['result']['validation']['files']['selection.json']=self.selection_sha
        fit_path=self.root/f'{self.base}/fit_result.json'
        bad=dict(self.result_doc);bad['result']=dict(bad['result'],params={'n_estimators':999})
        fit_path.write_text(json.dumps(bad,sort_keys=True,separators=(',',':'))+'\n')
        (self.root/f'{self.base}/attempts/{self.attempt}/attempt.json').write_text(json.dumps(bad,sort_keys=True,separators=(',',':'))+'\n')
        eligible,receipt=self.filter();self.assertEqual(eligible,[])
        self.assertIn('selection parameters differ',receipt['exclusions'][0]['reason'])
    def test_present_mismatched_copy_is_never_replaced_by_fallback(self):
        p=self.root/f'{self.base}/attempts/{self.attempt}/selection.json'
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'selected_params':{'n_estimators':999}})+'\n')
        eligible,receipt=self.filter();self.assertEqual(eligible,[])
        self.assertIn('attempt selected configuration SHA differs',receipt['exclusions'][0]['reason'])
    def test_missing_attempt_result_and_symlink_copy_remain_rejected(self):
        attempt_result=self.root/f'{self.base}/attempts/{self.attempt}/attempt.json';attempt_result.unlink()
        eligible,receipt=self.filter();self.assertEqual(eligible,[])
        attempt_result.write_text(json.dumps(self.result_doc,sort_keys=True,separators=(',',':'))+'\n')
        p=self.root/f'{self.base}/attempts/{self.attempt}/selection.json'
        p.symlink_to(self.root/f'{self.base}/selection.json')
        eligible,receipt=self.filter();self.assertEqual(eligible,[])
        self.assertIn('symlink',receipt['exclusions'][0]['reason'])

if __name__=='__main__':unittest.main(verbosity=2)
