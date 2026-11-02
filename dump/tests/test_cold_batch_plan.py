import importlib.util, json, os, tempfile, unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/'source'
spec=importlib.util.spec_from_file_location('batch_plan',SRC/'batch_plan.py');bp=importlib.util.module_from_spec(spec);spec.loader.exec_module(bp)

class FakeCold:
    @staticmethod
    def _pipeline_hash(row): return row['result']['validation']['files']['pipeline.joblib']
    @staticmethod
    def _consumer_closure(key,records): return records[key].get('closure',[])

class PlannerTests(unittest.TestCase):
    def record(self,key,status='validated_terminal',outcome='successful',validation_state='validated',closure=()):
        return {'key':key,'kind':'fit','method':'random_forest','experiment':4,'status':status,'outcome':outcome,'validation_state':validation_state,'artifact_dir':str(self.runtime/'artifacts'/key),'closure':list(closure),'result':{'attempt_id':'a1','task_sha256':'b'*64,'validation':{'task_key':key,'status':'validated','files':{'pipeline.joblib':'a'*64}}}}
    def setup_group(self,key):
        paths=[self.artifacts/key/'pipeline.joblib',self.artifacts/key/'attempts/a1/pipeline.joblib',self.artifacts/key/'checkpoints'/('b'*64)/'pipeline.joblib']
        paths[0].parent.mkdir(parents=True);paths[0].write_bytes(b'fixture-only')
        for p in paths[1:]:
            p.parent.mkdir(parents=True,exist_ok=True);os.link(paths[0],p)
        return paths
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name);self.runtime=self.root/'runtime_20261025';self.artifacts=self.runtime/'artifacts';self.artifacts.mkdir(parents=True)
    def tearDown(self): self.tmp.cleanup()
    def test_valid_owned_group_selected_without_payload_hashing(self):
        key='e4/rep_1/fit/direct/random_forest/A_half';self.setup_group(key);records={key:self.record(key)}
        items=bp.build_candidates(self.root,self.runtime,records,set(),None,FakeCold)
        self.assertEqual(len(items),1);self.assertEqual(items[0]['producer_task'],key);self.assertEqual(len(items[0]['aliases']),3)
        self.assertEqual(items[0]['source_sha256'],'a'*64)
    def test_nonterminal_consumer_excludes_group(self):
        key='e4/rep_1/fit/direct/random_forest/A_half';self.setup_group(key);records={key:self.record(key,closure=['e4/eval'])};records['e4/eval']={'key':'e4/eval','status':'running'}
        self.assertEqual(bp.build_candidates(self.root,self.runtime,records,set(),None,FakeCold),[])
    def test_failed_or_unvalidated_producer_excludes_group(self):
        key='e4/rep_1/fit/direct/random_forest/A_half';self.setup_group(key);records={key:self.record(key,outcome='scientific_failure')}
        self.assertEqual(bp.build_candidates(self.root,self.runtime,records,set(),None,FakeCold),[])
    def test_external_hardlink_excludes_group(self):
        key='e4/rep_1/fit/direct/random_forest/A_half';paths=self.setup_group(key);external=self.root/'outside.bin';os.link(paths[0],external);records={key:self.record(key)}
        self.assertEqual(bp.build_candidates(self.root,self.runtime,records,set(),None,FakeCold),[])
    def test_existing_archive_member_excludes_group(self):
        key='e4/rep_1/fit/direct/random_forest/A_half';self.setup_group(key);records={key:self.record(key)};logical=f'runtime_20261025/artifacts/{key}/pipeline.joblib'
        self.assertEqual(bp.build_candidates(self.root,self.runtime,records,{logical},None,FakeCold),[])
    def test_batch_byte_and_group_caps(self):
        rows=[{'bytes':600,'inode_identity':[1,i],'producer_task':str(i)} for i in range(10)]
        chosen=bp.select_batch(rows,max_bytes=2000,max_groups=3)
        self.assertEqual([x['producer_task'] for x in chosen],['0','1','2'])
        self.assertLessEqual(sum(x['bytes'] for x in chosen),2000)
    def test_duplicate_inode_input_is_rejected(self):
        with self.assertRaises(ValueError): bp.select_batch([{'bytes':1,'inode_identity':[1,2]},{'bytes':2,'inode_identity':[1,2]}])
    def test_unknown_running_owner_blocks_admission(self):
        self.assertFalse(bp.resource_admission_ready(1,99,[],1,lambda *args:True))
    def test_resource_policy_result_is_respected(self):
        self.assertTrue(bp.resource_admission_ready(0,99,[],1,lambda *args:True))
        self.assertFalse(bp.resource_admission_ready(0,0,[],1,lambda *args:False))
    def test_operation_dir_accepts_supervisor_files_and_rejects_child_or_unknown_files(self):
        runs=self.root/'runs';op=runs/'run1';op.mkdir(parents=True)
        for name in ('supervisor_state.json','private_admission.json','child.log','private_child_identity.json'):(op/name).write_text('fixture')
        allowed={'supervisor_state.json','private_admission.json','child.log','private_child_identity.json'};child={'child_result.json','private_candidate_plan.json'}
        bp.validate_operation_directory(op,runs,'run1',allowed,child)
        (op/'child_result.json').write_text('old')
        with self.assertRaises(RuntimeError):bp.validate_operation_directory(op,runs,'run1',allowed,child)
        (op/'child_result.json').unlink();(op/'unknown.tmp').write_text('x')
        with self.assertRaises(RuntimeError):bp.validate_operation_directory(op,runs,'run1',allowed,child)
    def test_each_alias_must_be_absent_and_resolve_to_expected_sha(self):
        alias1='runtime_20261025/artifacts/x/pipeline.joblib';alias2='runtime_20261025/artifacts/x/attempts/a/pipeline.joblib'
        class Resolver:
            def sha256(self,path,expected_sha256=None):return expected_sha256
        item={'sha256':'a'*64,'aliases':[alias1,alias2]}
        bp.verify_alias_resolution(self.root,Resolver(),[item])
        physical=self.root/alias2;physical.parent.mkdir(parents=True);physical.write_bytes(b'leftover')
        with self.assertRaises(RuntimeError):bp.verify_alias_resolution(self.root,Resolver(),[item])
    def test_reviewed_baseline_requires_existing_manifest_and_hash(self):
        f=self.root/'a.zip';f.write_bytes(b'fixture zip bytes');import hashlib;h=hashlib.sha256(f.read_bytes()).hexdigest()
        self.assertEqual(bp.require_reviewed_baseline(f,{'archive_sha256':h},h,lambda p:hashlib.sha256(p.read_bytes()).hexdigest()),h)
        with self.assertRaises(RuntimeError):bp.require_reviewed_baseline(f,{'archive_sha256':'0'*64},h,lambda p:hashlib.sha256(p.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):bp.require_reviewed_baseline(f,{'archive_sha256':h},'bad',lambda p:hashlib.sha256(p.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()



