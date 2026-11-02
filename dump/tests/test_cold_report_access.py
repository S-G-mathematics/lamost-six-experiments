import hashlib, importlib.util, json, tempfile, unittest, sys
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]/'source'
sys.path.insert(0,str(HERE))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
access=load('cold_report_access',HERE/'cold_report_access.py')
reporting=load('staged_reporting',HERE/'reporting.py')

def sha(b): return hashlib.sha256(b).hexdigest()
def fit(key,digest):
 return {'key':key,'kind':'fit','status':'validated_terminal','outcome':'successful','validation_state':'validated',
   'result':{'validation':{'status':'validated','task_key':key,'files':{'pipeline.joblib':digest}},
             'result':{'pipeline_sha256':digest}}}

class FakeStore:
 def __init__(self,digest): self.digest=digest;self.calls=[]
 def artifact_stat(self,path,expected):
  self.calls.append((path,expected))
  if expected!=self.digest: raise AssertionError('wrong expected digest')
  return {'backing':'cold_zip','sha256':self.digest,'size':41,
          'cache_identity':{'backing':'cold_zip','archive_sha256':'a'*64,'member':'runtime_20261025/artifacts/e3/rep_1/fit/direct/gmm/pipeline.joblib','header_offset':0,'crc32':77,'bytes':41,'sha256':self.digest}}

class ColdReportAccessTests(unittest.TestCase):
 def setup(self):
  td=tempfile.TemporaryDirectory();root=Path(td.name)/'migration';rt=root/'runtime_20261025';rt.mkdir(parents=True)
  key='e3/rep_1/fit/direct/gmm';blob=b'pipeline-bytes';t=fit(key,sha(blob))
  p=root/'runtime_20261025'/'artifacts'/key/'pipeline.joblib'
  return td,root,rt,key,blob,t,p
 def test_physical_pipeline_verified_and_logical_path_is_runtime_relative(self):
  td,root,rt,key,blob,t,p=self.setup()
  try:
   p.parent.mkdir(parents=True);p.write_bytes(blob)
   x=access.inspect_pipeline(t,rt)
   self.assertTrue(x['available']);self.assertEqual(x['backing'],'physical');self.assertEqual(x['sha256'],sha(blob))
   self.assertEqual(x['logical_path'],f'{rt.name}/artifacts/{key}/pipeline.joblib')
  finally: td.cleanup()
 def test_missing_physical_uses_verified_cold_member(self):
  td,root,rt,key,blob,t,p=self.setup();store=FakeStore(sha(blob))
  try:
   x=access.inspect_pipeline(t,rt,store)
   self.assertTrue(x['available']);self.assertEqual(x['backing'],'cold_zip');self.assertEqual(x['size_bytes'],41)
   self.assertEqual(store.calls,[(f'{rt.name}/artifacts/{key}/pipeline.joblib',sha(blob))])
  finally: td.cleanup()
 def test_invalid_present_physical_never_falls_back(self):
  td,root,rt,key,blob,t,p=self.setup();store=FakeStore(sha(blob))
  try:
   p.parent.mkdir(parents=True);p.write_bytes(b'wrong bytes')
   with self.assertRaises(access.ArtifactIdentityError): access.inspect_pipeline(t,rt,store)
   self.assertEqual(store.calls,[])
  finally: td.cleanup()
 def test_missing_without_manifest_is_unavailable(self):
  td,root,rt,key,blob,t,p=self.setup()
  try:
   x=access.inspect_pipeline(t,rt)
   self.assertFalse(x['available']);self.assertEqual(x['backing'],'missing')
  finally: td.cleanup()
 def test_unsafe_key_and_symlink_rejected(self):
  td,root,rt,key,blob,t,p=self.setup()
  try:
   bad=dict(t,key='../escape')
   with self.assertRaises(access.ArtifactIdentityError): access.inspect_pipeline(bad,rt)
   p.parent.mkdir(parents=True);target=Path(td.name)/'outside';target.write_bytes(blob);p.symlink_to(target)
   with self.assertRaises(access.ArtifactIdentityError): access.inspect_pipeline(t,rt,FakeStore(sha(blob)))
  finally: td.cleanup()
 def test_e6_alias_resolves_member_pipeline_via_e3_eval_reference(self):
  td,root,rt,key,blob,fit_task,p=self.setup()
  try:
   p.parent.mkdir(parents=True);p.write_bytes(blob)
   eval_key='e3/rep_1/eval/direct/kde'
   eval_task={'key':eval_key,'kind':'eval','fit_key':key,'dependencies':[key]}
   alias={'key':'e6/rep_1/eval/member/kde','kind':'alias','dependencies':[eval_key]}
   result=access.fit_reference(alias,rt,{key:fit_task},all_tasks={eval_key:eval_task,alias['key']:alias})
   self.assertTrue(result['pipeline_available'])
   self.assertEqual(result['pipeline_backing'],'physical')
   self.assertEqual(result['pipeline_sha256'],sha(blob))
  finally: td.cleanup()
 def test_report_artifact_dir_uses_explicit_runtime_not_legacy_absolute_path(self):
  td,root,rt,key,blob,t,p=self.setup()
  try:
   task={'key':key,'artifact_dir':'/old/migration/runtime_20261025/artifacts/'+key}
   resolved=reporting._task_artifact(rt,task)
   self.assertEqual(resolved,rt/'artifacts'/key)
   self.assertTrue(resolved.is_relative_to(rt))
  finally: td.cleanup()

if __name__=='__main__': unittest.main()
