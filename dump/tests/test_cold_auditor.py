import contextlib,hashlib,importlib.util,json,os,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

BASE=Path(__file__).resolve().parents[1]
SRC=BASE/"source/audit_artifacts.py"
spec=importlib.util.spec_from_file_location("cold_staged_auditor",SRC)
aud=importlib.util.module_from_spec(spec);spec.loader.exec_module(aud)
COLD_SRC=BASE/"source"/"cold_model_storage.py"
cspec=importlib.util.spec_from_file_location("cold_staged_storage",COLD_SRC)
cold=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(cold)

class ColdAuditorTests(unittest.TestCase):
 def fixture(self,archived=True,mutate_role=False):
  td=tempfile.TemporaryDirectory();root=Path(td.name);rt=root/"runtime_20261025"
  (rt/"cache/roles").mkdir(parents=True);out=rt/"artifacts/e3/rep_1/fit/logistic"
  if not archived:out.mkdir(parents=True)
  X=np.arange(84,dtype=float).reshape(14,6);y=np.repeat(np.arange(7,dtype=np.int64),2);ids=np.arange(100,114,dtype=np.int64)
  if mutate_role:y=y.copy();y[0]=1
  np.savez(rt/"cache/roles/rep_1.npz",X_fit=X,y_fit=y,fit_ids=ids,tuning_ids=np.arange(200,210),calibration_ids=np.arange(300,310))
  imputer=SimpleImputer(strategy="median",keep_empty_features=True).fit(X);Xi=imputer.transform(X);scaler=StandardScaler().fit(Xi)
  counts=([2]*7 if mutate_role else np.bincount(y,minlength=7).tolist())
  pipe={"imputer":imputer,"scaler":scaler,"class_counts":counts,"training_rows":len(y),"training_ids_sha256":aud.sha256_ids(ids),"seed":17,"params":{}}
  import joblib
  b=joblib.dump(pipe,root/"pipe.tmp",compress=0);pipepath=root/"pipe.tmp"
  import hashlib
  ph=hashlib.sha256(pipepath.read_bytes()).hexdigest()
  key="e3/rep_1/fit/logistic"
  task={"key":key,"kind":"fit","experiment":3,"rep":1,"method":"logistic_regression","status":"validated_terminal","outcome":"successful","seed":17,"trials":0,
        "result":{"result":{"class_counts":counts,"training_ids_sha256":aud.sha256_ids(ids),"seed":17,"params":{},"pipeline_sha256":ph}}}
  if archived:
   archive=rt/"packages/LAMOST_COLD_RF_MODELS.zip";archive.parent.mkdir(parents=True)
   member=f"runtime_20261025/artifacts/{key}/pipeline.joblib"
   archive_member=cold._archive_member_for(member,ph)
   with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:z.write(pipepath,archive_member)
   with zipfile.ZipFile(archive) as z:
    info=z.getinfo(archive_member);records=cold._zip_records_all(z)
   manifest=rt/"manifests/cold_model_store_manifest.json";manifest.parent.mkdir(parents=True)
   doc={"schema_version":cold.SCHEMA,"archive_path":"runtime_20261025/packages/LAMOST_COLD_RF_MODELS.zip","archive_sha256":cold.sha256_file(archive),"archive_bytes":archive.stat().st_size,"zip_records":records,
        "members":[{"task_key":key,"task_sha256":"a"*64,"logical_path":member,"archive_member":archive_member,"aliases":[member],"consumer_tasks":[],"sha256":ph,"bytes":info.file_size,"crc32":info.CRC,"header_offset":info.header_offset,"source_mtime_ns":pipepath.stat().st_mtime_ns}]}
   manifest.write_text(json.dumps(doc))
   store=cold.ColdModelStore(root,rt,archive,manifest,rt/"journals/cold_model_store")
  else:
   out.mkdir(parents=True,exist_ok=True);(out/"pipeline.joblib").write_bytes(pipepath.read_bytes());store=None
  return td,root,rt,task,store,archive if archived else None,manifest if archived else None,member if archived else None,ph,pipepath
 def test_plain_and_cold_archived_fit_audits_match(self):
  f=self.fixture(False);g=self.fixture(True)
  try:
   *_,rt1,t1,store1,ar1,m1,mem1,sha1,pp1=f
   *_,rt2,t2,store2,ar2,m2,mem2,sha2,pp2=g
   a=aud.Auditor(rt1);a.fit_audit(t1,{t1["key"]:t1})
   b=aud.Auditor(rt2,cold_store=store2);b.fit_audit(t2,{t2["key"]:t2})
   self.assertEqual(a.issues,b.issues);self.assertEqual(a.issues,[])
  finally:f[0].cleanup();g[0].cleanup()
 def test_resolver_autodetect_absent_manifest_does_not_create_archive(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);rt=root/"runtime_20261025";rt.mkdir()
   self.assertIsNone(aud.resolve_cold_store(rt))
   self.assertFalse((root/"packages/LAMOST_COLD_RF_MODELS.zip").exists())
 def test_resolver_fails_closed_when_manifest_exists_without_deployed_sibling(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);rt=root/"runtime_20261025";(rt/"manifests").mkdir(parents=True)
   (rt/"manifests/cold_model_store_manifest.json").write_text("{}")
   with self.assertRaisesRegex(RuntimeError,"deployed sibling resolver is missing"):aud.resolve_cold_store(rt)
   self.assertFalse((root/"packages/LAMOST_COLD_RF_MODELS.zip").exists())
 def test_resolver_uses_deployed_sibling_and_manifest_locator(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);rt=root/"runtime_20261025";(rt/"source").mkdir(parents=True);(rt/"manifests").mkdir()
   (rt/"manifests/cold_model_store_manifest.json").write_text(json.dumps({"archive_path":"packages/reviewed.zip"}))
   (rt/"source/cold_model_storage.py").write_text("class ColdModelStore:\n @classmethod\n def from_runtime(cls,root,runtime,manifest_path=None):\n  return {'root':str(root),'runtime':str(runtime),'manifest':str(manifest_path)}\n")
   got=aud.resolve_cold_store(rt)
   self.assertEqual(got,{"root":str(root),"runtime":str(rt),"manifest":str(rt/"manifests/cold_model_store_manifest.json")})
   self.assertFalse((root/"packages/reviewed.zip").exists())

 def test_archive_mutation_is_rechecked_and_changed_member_rejected(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x;a=aud.Auditor(rt,store)
   first=a.file_hash(rt/"artifacts"/task["key"]/"pipeline.joblib");self.assertEqual(first,sha)
   with zipfile.ZipFile(archive,"a",compression=zipfile.ZIP_STORED) as z:z.writestr("diagnostic/append.bin",b"x")
   with zipfile.ZipFile(archive) as z:records=cold._zip_records_all(z)
   doc=json.loads(manifest.read_text());doc["archive_sha256"]=cold.sha256_file(archive);doc["archive_bytes"]=archive.stat().st_size;doc["zip_records"]=records;manifest.write_text(json.dumps(doc))
   second=a.file_hash(rt/"artifacts"/task["key"]/"pipeline.joblib");self.assertEqual(second,first)
   # Corrupt committed bytes without changing member manifest; archive identity changes and must fail closed.
   raw=archive.read_bytes();archive.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
   with self.assertRaises(Exception):a.file_hash(rt/"artifacts"/task["key"]/"pipeline.joblib",force=True)
  finally:x[0].cleanup()
 def test_present_physical_mismatch_does_not_fallback(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x
   p=rt/"artifacts"/task["key"]/"pipeline.joblib";p.parent.mkdir(parents=True);p.write_bytes(b"wrong")
   a=aud.Auditor(rt,store)
   with self.assertRaises(Exception):a.file_hash(p,force=True)
  finally:x[0].cleanup()
 def test_cold_aliases_are_mapped_and_resolved_with_entry_sha(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x
   alias="runtime_20261025/artifacts/e3/source_alias/pipeline.joblib"
   doc=json.loads(manifest.read_text());doc["members"][0]["aliases"].append(alias);manifest.write_text(json.dumps(doc))
   a=aud.Auditor(rt,store);p=root/alias
   self.assertEqual(a._logical_artifact(p),alias)
   self.assertTrue(a.file_exists(p));self.assertEqual(a.file_hash(p),sha)
  finally:x[0].cleanup()

 def test_alias_conflict_fails_closed(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x
   alias="runtime_20261025/artifacts/shared/pipeline.joblib"
   doc=json.loads(manifest.read_text());doc["members"][0]["aliases"].append(alias)
   second=dict(doc["members"][0],task_key="other",logical_path="runtime_20261025/artifacts/other/pipeline.joblib",aliases=[alias])
   doc["members"].append(second);manifest.write_text(json.dumps(doc))
   a=aud.Auditor(rt,store)
   with self.assertRaisesRegex(ValueError,"ambiguous"):a._logical_artifact(root/alias)
  finally:x[0].cleanup()

 def test_real_cold_reader_lease_allows_nested_artifact_checks_in_run(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x
   task["validation_state"]="validated"
   (rt/"registry.json").write_text(json.dumps({"tasks":[task]}))
   report=aud.Auditor(rt,store).run()
   self.assertEqual(report["audited_entries"],1)
   self.assertEqual(report["issue_count"],0)
  finally:x[0].cleanup()

 def test_reader_lease_spans_run_and_refreshes_alias_map_before_scan(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);rt=root/"runtime_20261025";rt.mkdir()
   manifest=rt/"manifests/cold_model_store_manifest.json";manifest.parent.mkdir()
   logical="runtime_20261025/artifacts/canonical/pipeline.joblib";alias="runtime_20261025/artifacts/new_alias/pipeline.joblib"
   row={"logical_path":logical,"aliases":[logical],"sha256":"a"*64,"task_key":"t","task_sha256":"b"*64}
   manifest.write_text(json.dumps({"schema_version":"lamost-cold-model-store/1","members":[row]}))
   class ProbeStore:
    def __init__(self):self.manifest=manifest;self.lock=threading.Lock()
    @contextlib.contextmanager
    def _read_lock(self):
     if not self.lock.acquire(False):raise RuntimeError("lock already held")
     try:yield
     finally:self.lock.release()
   store=ProbeStore();a=aud.Auditor(rt,store);row["aliases"].append(alias);manifest.write_text(json.dumps({"schema_version":"lamost-cold-model-store/1","members":[row]}))
   def body(evaluation_only=False):
    self.assertIn(alias,a.cold_members)
    self.assertFalse(store.lock.acquire(False))
    return {"leased":True}
   a._run_snapshot=body
   self.assertEqual(a.run(),{"leased":True})
   self.assertTrue(store.lock.acquire(False));store.lock.release()

 def test_reused_archived_source_pipeline_is_loaded_for_params_seed_hash_check(self):
  x=self.fixture(True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x
   alias="runtime_20261025/artifacts/e3/source_alias/pipeline.joblib"
   doc=json.loads(manifest.read_text());doc["members"][0]["aliases"].append(alias);manifest.write_text(json.dumps(doc))
   meta=task["result"]["result"];meta.update({"reused":True,"source":alias,"source_sha256":sha})
   task["source_metadata"]={"path":alias,"selected_params_match":True}
   a=aud.Auditor(rt,store);seen=[];load=a.load_joblib
   def spy(path):seen.append(str(path));return load(path)
   a.load_joblib=spy
   a.fit_audit(task,{task["key"]:task})
   self.assertIn(str(root/alias),seen)
   self.assertFalse(any(i["check"]=="source_pipeline_unavailable" for i in a.issues))
  finally:x[0].cleanup()

 def test_role_provenance_guard_stays_active_for_archived_fit(self):
  x=self.fixture(True,mutate_role=True)
  try:
   td,root,rt,task,store,archive,manifest,member,sha,pipe=x;a=aud.Auditor(rt,store)
   a.fit_audit(task,{task["key"]:task})
   self.assertIn("pipeline_class_counts",{i["check"] for i in a.issues})
  finally:x[0].cleanup()

if __name__=="__main__":unittest.main()

