import hashlib, json, os, pathlib, subprocess, sys, tempfile, time, unittest, zipfile
import joblib, numpy as np
from unittest.mock import patch
import cold_model_storage as cold
from cold_model_storage import ColdModelStore, UnsafePlan, AmbiguousState

HERE=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def setup_store(tmp,rep="rep_1",method="random_forest"):
    root=pathlib.Path(tmp)/"migration";runtime=root/"runtime_20261025";runtime.mkdir(parents=True)
    archive=runtime/"packages"/"cold.zip";archive.parent.mkdir()
    store=ColdModelStore(root,runtime,archive,runtime/"manifests"/"cold_store.json",runtime/"journals"/"cold_store")
    store.initialize_empty_archive()
    key=f"e3/{rep}/fit/real/{method}";out=runtime/"artifacts"/key;out.mkdir(parents=True)
    source=out/"pipeline.joblib";obj={"fixture":"joblib-stream","array":np.arange(7,dtype=np.int16),"params":{"n_estimators":1}}
    joblib.dump(obj,source,compress=0);digest=sha(source)
    attempt_id="fixture_attempt_01";task_sha=hashlib.sha256(("task-sha-"+rep).encode()).hexdigest()
    attempt_dir=out/"attempts"/attempt_id;attempt_dir.mkdir(parents=True)
    checkpoint_dir=out/"checkpoints"/task_sha;checkpoint_dir.mkdir(parents=True)
    alias=attempt_dir/"pipeline.joblib";os.link(source,alias)
    checkpoint_alias=checkpoint_dir/"pipeline.joblib";os.link(source,checkpoint_alias)
    selection_bytes=json.dumps({"selected_params":{"n_estimators":1}},sort_keys=True).encode();selection_sha=hashlib.sha256(selection_bytes).hexdigest()
    (out/"selection.json").write_bytes(selection_bytes);(attempt_dir/"selection.json").write_bytes(selection_bytes);(checkpoint_dir/"selection.json").write_bytes(selection_bytes)
    fit_result={"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest,"status":"success"}}
    fit_result_bytes=json.dumps(fit_result,sort_keys=True).encode();(out/"fit_result.json").write_bytes(fit_result_bytes);(attempt_dir/"attempt.json").write_bytes(fit_result_bytes)
    publication={"attempt_id":attempt_id,"pipeline_sha256":digest,"published_path":str(source),"stage":"validated_publication","task_sha256":task_sha}
    publication_bytes=json.dumps(publication,sort_keys=True).encode();(out/"fit_publication.json").write_bytes(publication_bytes);(attempt_dir/"fit_publication.json").write_bytes(publication_bytes)
    fit={"key":key,"experiment":3,"kind":"fit","method":method,"status":"validated_terminal","outcome":"successful","validation_state":"validated","artifact_dir":str(out),"dependencies":[],"result":{"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest},"validation":{"status":"validated","task_key":key,"files":{"pipeline.joblib":digest,"selection.json":selection_sha}}}}
    consumer_key=f"e3/{rep}/eval/direct/random_forest/gmm"
    consumer={"key":consumer_key,"experiment":3,"kind":"eval","method":method,"status":"validated_terminal","outcome":"successful","validation_state":"validated","dependencies":[key],"artifact_dir":str(runtime/"artifacts"/consumer_key),"result":{}}
    records={key:fit,consumer_key:consumer}
    item={"producer_task":key,"source_path":source.relative_to(root).as_posix(),"source_relpath":source.relative_to(root).as_posix(),"archive_member":source.relative_to(root).as_posix(),"source_sha256":digest,"recorded_artifact_sha256":digest,"consumer_tasks":[consumer_key],"aliases":[source.relative_to(root).as_posix(),alias.relative_to(root).as_posix(),checkpoint_alias.relative_to(root).as_posix()]}
    return root,runtime,store,key,source,alias,obj,digest,records,item
class ColdStoreTests(unittest.TestCase):
 def test_actual_joblib_model_loads_from_verified_cold_stream(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   tx=s.commit_models([item],records)
   self.assertTrue(tx);self.assertFalse(src.exists());self.assertFalse(alias.exists());self.assertFalse(src.is_symlink())
   public=json.loads(s.manifest.read_text());self.assertNotIn("pid",json.dumps(public).lower());self.assertNotIn("process_start_ticks",json.dumps(public))
   member=public["members"][0]["archive_member"]
   self.assertTrue(member.startswith("runtime_20261025/cold_models/"));self.assertIn(digest,member)
   self.assertTrue((s.journals/tx/"private_process_inventory.json").is_file())
   loaded=s.load_joblib(item["source_relpath"],digest)
   self.assertEqual(loaded["fixture"],obj["fixture"]);np.testing.assert_array_equal(loaded["array"],obj["array"])
   self.assertEqual(s.sha256(item["source_relpath"],digest),digest)
   stat=s.artifact_stat(item["source_relpath"],digest)
   self.assertEqual(stat["backing"],"cold_zip");self.assertEqual(stat["sha256"],digest)
   self.assertEqual(stat["cache_identity"]["archive_sha256"],stat["archive_sha256"])
   self.assertEqual(s.recover(tx,records),"complete")
 def test_physical_hash_mismatch_refuses_archive_fallback(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   src.parent.mkdir(parents=True,exist_ok=True);src.write_bytes(b"tampered physical file")
   with self.assertRaises(AmbiguousState):s.read_bytes(item["source_relpath"],digest)
 def test_symlinked_physical_path_is_rejected(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   moved=src.with_name("real.pipeline");src.rename(moved);src.symlink_to(moved)
   with self.assertRaises(AmbiguousState):s.read_bytes(item["source_relpath"],digest)
 def test_precommit_interrupted_append_rolls_back_and_keeps_originals(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);before=sha(s.archive)
   with self.assertRaises(RuntimeError):s.commit_models([item],records,fault_after_bytes=20)
   tx=next((rt/"journals"/"cold_store").glob("*/journal.json")).parent.name
   self.assertEqual(s.recover(tx,records),"rolled_back");self.assertEqual(sha(s.archive),before)
   self.assertTrue(src.is_file() and alias.is_file());self.assertEqual(sha(src),digest)
 def test_partial_postcommit_unlink_recovers_and_streams_model(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   with self.assertRaises(RuntimeError):s.commit_models([item],records,fail_after_unlinks=1)
   tx=next((rt/"journals"/"cold_store").glob("*/journal.json")).parent.name
   j=json.loads((rt/"journals"/"cold_store"/tx/"journal.json").read_text())
   self.assertEqual(j["state"],"unlinking");self.assertTrue(j["items"][0]["unlink_intents"])
   missing=[p for p in j["items"][0]["aliases"] if not (root/p).exists()]
   self.assertTrue(missing);self.assertTrue(set(missing)<=set(j["items"][0]["unlink_intents"]))
   with self.assertRaises(AmbiguousState):
    with s.append_guard():pass
   committed_manifest=s.manifest.read_bytes()
   bad=json.loads(committed_manifest);bad["archive_sha256"]="0"*64;s.manifest.write_text(json.dumps(bad))
   with self.assertRaises(AmbiguousState):s.recover(tx,records)
   s.manifest.write_bytes(committed_manifest)
   self.assertEqual(s.recover(tx,records),"complete")
   self.assertFalse(src.exists());self.assertFalse(alias.exists())
   self.assertEqual(s.load_joblib(item["source_relpath"],digest)["fixture"],obj["fixture"])
 def test_external_hardlink_refuses_before_archive_mutation(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);external=pathlib.Path(td)/"outside-link";os.link(src,external);before=sha(s.archive)
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   self.assertEqual(sha(s.archive),before);self.assertTrue(src.exists())
 def test_nonterminal_transitive_consumer_refuses(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);records[item["consumer_tasks"][0]]["status"]="waiting_for_dependency";before=sha(s.archive)
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   self.assertEqual(sha(s.archive),before)
 def test_e1_and_non_random_forest_sources_are_out_of_scope(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   records[key]["experiment"]=1
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   records[key]["experiment"]=3;records[key]["method"]="unsupported_method"
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   self.assertTrue(src.exists())
 def test_physical_read_without_expected_or_manifest_hash_refuses(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   with self.assertRaises(UnsafePlan):s.read_bytes(item["source_relpath"])
 def test_reader_lease_blocks_cold_writer(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   with s._read_lock():
    with self.assertRaises(AmbiguousState):s.commit_models([item],records)
   self.assertTrue(src.exists())
 def test_incorrect_item_hash_fails_closed(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);bad=dict(item,source_sha256="0"*64);before=sha(s.archive)
   with self.assertRaises(UnsafePlan):s.commit_models([bad],records)
   self.assertEqual(sha(s.archive),before)
 def test_finalizer_same_zip_append_refreshes_manifest_and_keeps_model_readable(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   before_stat=s.artifact_stat(item["source_relpath"],digest);before=before_stat["archive_sha256"]
   with s.append_guard(expected_archive_sha256=before,registry_records=records) as guard:
    with zipfile.ZipFile(s.archive,"a",compression=zipfile.ZIP_DEFLATED,allowZip64=True) as z:z.writestr("runtime_20261025/reports/tiny.txt","fixture")
    fd=os.open(s.archive,os.O_RDONLY);os.fsync(fd);os.close(fd)
    guard.refresh_manifest()
   after=s.artifact_stat(item["source_relpath"],digest)
   self.assertNotEqual(before,after["archive_sha256"])
   self.assertEqual(before_stat["member_header_offset"],after["member_header_offset"])
   self.assertEqual(s.load_joblib(item["source_relpath"],digest)["fixture"],obj["fixture"])
   self.assertEqual(s.sha256(item["source_relpath"],digest),digest)
   with zipfile.ZipFile(s.archive) as z:self.assertEqual(z.read("runtime_20261025/reports/tiny.txt"),b"fixture")
 def test_same_zip_append_invalidates_backing_cache_identity(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records);a=s.artifact_stat(item["source_relpath"],digest)
   key2="e4/rep_2/fit/direct/random_forest/A_half";out2=rt/"artifacts"/key2;out2.mkdir(parents=True);src2=out2/"pipeline.joblib";joblib.dump({"fixture":"second"},src2,compress=0);d2=sha(src2)
   ev2={"key":"e4/rep_2/eval/direct/random_forest/A_half","experiment":4,"kind":"eval","status":"validated_terminal","outcome":"successful","validation_state":"validated","dependencies":[key2]}
   fit2={"key":key2,"experiment":4,"kind":"fit","method":"random_forest","status":"validated_terminal","outcome":"successful","validation_state":"validated","artifact_dir":str(out2),"dependencies":[],"result":{"task_sha256":"fit2","result":{"pipeline_sha256":d2},"validation":{"status":"validated","task_key":key2,"files":{"pipeline.joblib":d2}}}}
   records[key2]=fit2;records[ev2["key"]]=ev2
   item2={"producer_task":key2,"source_path":src2.relative_to(root).as_posix(),"source_relpath":src2.relative_to(root).as_posix(),"archive_member":src2.relative_to(root).as_posix(),"source_sha256":d2,"recorded_artifact_sha256":d2,"consumer_tasks":[ev2["key"]],"aliases":[src2.relative_to(root).as_posix()]}
   s.commit_models([item2],records);b=s.artifact_stat(item["source_relpath"],digest)
   self.assertEqual(a["member_header_offset"],b["member_header_offset"]);self.assertNotEqual(a["archive_sha256"],b["archive_sha256"]);self.assertNotEqual(a["cache_identity"],b["cache_identity"])
   self.assertEqual(s.load_joblib(item["source_relpath"],digest)["fixture"],obj["fixture"])

 def test_alias_resolves_to_canonical_cold_member(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   alias_logical=item["aliases"][1]
   self.assertEqual(s.read_bytes(alias_logical,digest),s.read_bytes(item["source_relpath"],digest))
   stat=s.artifact_stat(alias_logical,digest)
   self.assertTrue(stat["resolved_from_alias"]);self.assertEqual(stat["canonical_logical_path"],item["source_relpath"])
   self.assertEqual(stat["requested_logical_path"],alias_logical)
 def test_tampered_alias_refuses_archive_fallback(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   alias_path=root/item["aliases"][1];alias_path.parent.mkdir(parents=True,exist_ok=True);alias_path.write_bytes(b"tampered alias")
   with self.assertRaises(AmbiguousState):s.read_bytes(item["aliases"][1],digest)
 def test_archive_payload_mutation_with_restored_mtime_is_detected(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   s.artifact_stat(item["source_relpath"],digest)
   old=s.archive.stat();mtime=old.st_mtime_ns
   with zipfile.ZipFile(s.archive,"r") as z:info=z.getinfo(json.loads(s.manifest.read_text())["members"][0]["archive_member"])
   with open(s.archive,"r+b") as f:
    f.seek(info.header_offset);hdr=f.read(30);nlen=int.from_bytes(hdr[26:28],"little");elen=int.from_bytes(hdr[28:30],"little")
    pos=info.header_offset+30+nlen+elen;f.seek(pos);b=f.read(1);f.seek(pos);f.write(bytes([b[0]^1]));f.flush();os.fsync(f.fileno())
   os.utime(s.archive,ns=(old.st_atime_ns,mtime))
   with self.assertRaises(AmbiguousState):s.artifact_stat(item["source_relpath"],digest)
 def test_existing_member_consumer_closure_revalidated_before_append(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   records[item["consumer_tasks"][0]]["status"]="waiting_for_dependency"
   before=sha(s.archive)
   with self.assertRaises(UnsafePlan):
    with s.append_guard(registry_records=records):pass
   self.assertEqual(sha(s.archive),before)
 def test_existing_member_pipeline_sha_revalidated_before_append(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   records[key]["result"]["validation"]["files"]["pipeline.joblib"]="0"*64
   with self.assertRaises(AmbiguousState):
    with s.append_guard(registry_records=records):pass


 def test_defaults_use_migration_packages_without_creating_it(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root=pathlib.Path(td)/"migration";runtime=root/"runtime_20261025";runtime.mkdir(parents=True)
   store=ColdModelStore.from_runtime(root,runtime)
   self.assertEqual(store.archive,root/"packages"/"LAMOST_COLD_RF_MODELS.zip")
   self.assertFalse(store.archive.parent.exists())
 def test_safety_helper_is_sibling_pinned_not_staging_import(self):
  import cold_model_storage
  self.assertEqual(cold_model_storage.SAFETY_PATH.parent,cold_model_storage.Path(cold_model_storage.__file__).resolve().parent)
  self.assertEqual(sha(cold_model_storage.SAFETY_PATH),cold_model_storage.SAFETY_SHA256)


 def test_truncated_central_directory_recovers_before_parsing_old_members(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   old_sha=sha(s.archive);old_public=json.loads(s.manifest.read_text());old_member=old_public["members"][0]["archive_member"]
   key2="e4/rep_2/fit/direct/random_forest/A_half";out2=rt/"artifacts"/key2;out2.mkdir(parents=True)
   src2=out2/"pipeline.joblib";joblib.dump({"fixture":"interrupted-second"},src2,compress=0);d2=sha(src2)
   consumer2=f"e4/rep_2/eval/direct/random_forest/A_half"
   fit2={"key":key2,"experiment":4,"kind":"fit","method":"random_forest","status":"validated_terminal","outcome":"successful","validation_state":"validated","artifact_dir":str(out2),"dependencies":[],"result":{"task_sha256":"task-sha-second","result":{"pipeline_sha256":d2},"validation":{"status":"validated","task_key":key2,"files":{"pipeline.joblib":d2}}}}
   ev2={"key":consumer2,"experiment":4,"kind":"eval","status":"validated_terminal","outcome":"successful","validation_state":"validated","dependencies":[key2]}
   records[key2]=fit2;records[consumer2]=ev2
   item2={"producer_task":key2,"source_path":src2.relative_to(root).as_posix(),"source_relpath":src2.relative_to(root).as_posix(),"archive_member":src2.relative_to(root).as_posix(),"source_sha256":d2,"recorded_artifact_sha256":d2,"consumer_tasks":[consumer2],"aliases":[src2.relative_to(root).as_posix()]}
   with self.assertRaises(RuntimeError):s.commit_models([item2],records,fault_after_bytes=30)
   pending=[]
   for candidate in (rt/"journals"/"cold_store").glob("*/journal.json"):
    candidate_doc=json.loads(candidate.read_text())
    if candidate_doc.get("state") not in ("complete","rolled_back"):pending.append((candidate,candidate_doc))
   self.assertEqual(len(pending),1);jp,j=pending[0];tx=jp.parent.name
   self.assertIn(j["state"],["appending","prepared"])
   self.assertEqual(sha(s.archive) != old_sha,True)
   # Emulate abrupt process death with a truncated central directory/EOCD, not a clean ZipFile close.
   with open(s.archive,"r+b") as f:f.truncate(j["central_directory_offset"]+32);f.flush();os.fsync(f.fileno())
   with self.assertRaises(zipfile.BadZipFile):
    with zipfile.ZipFile(s.archive,"r"):pass
   self.assertEqual(s.recover(tx,records),"rolled_back")
   self.assertEqual(sha(s.archive),old_sha)
   self.assertEqual(s.load_joblib(item["source_relpath"],digest)["fixture"],obj["fixture"])
   with zipfile.ZipFile(s.archive,"r") as z:self.assertIn(old_member,z.namelist())
   self.assertTrue(src2.is_file())


 def test_runtime_locator_follows_verified_same_inode_archive_rename(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   old=s.archive;old_stat=old.stat();new=root/"packages"/"LAMOST_ALL_EXPERIMENTS_20261026T120000Z.zip";new.parent.mkdir(parents=True,exist_ok=True)
   with s.append_guard(expected_archive_sha256=json.loads(s.manifest.read_text())["archive_sha256"],registry_records=records) as guard:
    os.replace(old,new)
    self.assertEqual((new.stat().st_dev,new.stat().st_ino),(old_stat.st_dev,old_stat.st_ino))
    guard.refresh_manifest(archive_path=new)
   reopened=ColdModelStore.from_runtime(root,rt,manifest_path=s.manifest)
   self.assertEqual(reopened.archive,new)
   self.assertEqual(reopened.load_joblib(item["source_relpath"],digest)["fixture"],obj["fixture"])
 def test_runtime_locator_rejects_manifest_escape_and_symlink(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td);s.commit_models([item],records)
   doc=json.loads(s.manifest.read_text());doc["archive_path"]="../outside.zip";s.manifest.write_text(json.dumps(doc))
   with self.assertRaises(UnsafePlan):ColdModelStore.from_runtime(root,rt,manifest_path=s.manifest)
   doc["archive_path"]="runtime_20261025/packages/alias.zip";s.manifest.write_text(json.dumps(doc))
   target=rt/"packages"/"cold.zip";link=rt/"packages"/"alias.zip";link.symlink_to(target)
   with self.assertRaises(AmbiguousState):ColdModelStore.from_runtime(root,rt,manifest_path=s.manifest)


 def test_foreign_e2_hardlink_alias_refuses_without_archive_mutation(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   foreign=root/"project"/"e2_20261024"/"artifacts"/"old_fit"/"pipeline.joblib";foreign.parent.mkdir(parents=True);os.link(src,foreign)
   item["aliases"].append(foreign.relative_to(root).as_posix());before=sha(s.archive)
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   self.assertEqual(sha(s.archive),before);self.assertTrue(foreign.exists())
 def test_alias_owner_nonterminal_consumer_refuses(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   records[item["consumer_tasks"][0]]["status"]="running"
   before=sha(s.archive)
   with self.assertRaises(UnsafePlan):s.commit_models([item],records)
   self.assertEqual(sha(s.archive),before);self.assertTrue(src.exists())


 def test_other_producer_live_alias_process_refuses_commit(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   other_key="e3/rep_9/fit/real/random_forest";other_out=rt/"artifacts"/other_key;other_out.mkdir(parents=True)
   other_alias=other_out/"pipeline.joblib";os.link(src,other_alias)
   other={"key":other_key,"experiment":3,"kind":"fit","method":"random_forest","status":"validated_terminal","outcome":"successful","validation_state":"validated","artifact_dir":str(other_out),"dependencies":[],"result":{"task_sha256":"b"*64,"result":{"pipeline_sha256":digest},"validation":{"status":"validated","task_key":other_key,"files":{"pipeline.joblib":digest}}}}
   records[other_key]=other;item["aliases"].append(other_alias.relative_to(root).as_posix())
   proc=subprocess.Popen([sys.executable,"-c","import sys,time;time.sleep(20)",str(other_out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    time.sleep(0.05);before=sha(s.archive)
    with self.assertRaises(UnsafePlan):s.commit_models([item],records)
    self.assertEqual(sha(s.archive),before);self.assertTrue(other_alias.exists())
   finally:
    proc.terminate();proc.wait(timeout=5)

 def test_committed_digest_cache_is_seeded_and_same_size_tamper_invalidates(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   tx=s.commit_models([item],records)
   j=json.loads((s.journals/tx/"journal.json").read_text())
   self.assertEqual(s._archive_identity_cache["sha256"],j["archive_sha256_after"])
   self.assertEqual(s._archive_identity_cache["zip_records"],j["member_records_after"])
   manifest=json.loads(s.manifest.read_text());archive=s.archive;before=archive.stat()
   data=bytearray(archive.read_bytes());data[0]^=1;archive.write_bytes(data)
   os.utime(archive,ns=(before.st_atime_ns,before.st_mtime_ns))
   with self.assertRaises(AmbiguousState):s._check_archive_manifest(manifest)


 def test_archive_mutation_during_final_hash_refuses_cache_seed_and_rolls_back(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
   real_hash=cold.sha256_file_and_prefixes;mutated=[False]
   def hash_then_mutate(path,prefix_bytes,chunk=8<<20):
    result=real_hash(path,prefix_bytes,chunk)
    appending=any(json.loads(j.read_text()).get("state")=="appending" for j in s.journals.glob("*/journal.json"))
    if pathlib.Path(path)==s.archive and appending and not mutated[0]:
     mutated[0]=True
     with open(s.archive,"ab") as f:f.write(b"race")
    return result
   with patch.object(cold,"sha256_file_and_prefixes",side_effect=hash_then_mutate):
    with self.assertRaises(AmbiguousState):s.commit_models([item],records)
   self.assertTrue(mutated[0]);self.assertIsNone(s._archive_identity_cache)
   self.assertTrue(src.is_file());self.assertTrue(alias.is_file())
   tx=next((rt/"journals"/"cold_store").glob("*/journal.json")).parent.name
   self.assertEqual(s.recover(tx,records),"rolled_back")
   self.assertTrue(src.is_file());self.assertTrue(alias.is_file())


 def _legacy_history_fixture(self,td):
  root,rt,store,key,src,alias,obj,digest,records,item=setup_store(td)
  joblib.dump(obj,src,compress=3);digest=sha(src)
  legacy_src=b"legacy source fixture";legacy=hashlib.sha256(legacy_src).hexdigest();tx="b"*32;logical=item["source_relpath"]
  temp=rt/"codec-fixture";temp.mkdir()
  opts=store._codec_options();opts["temp_root"]=temp
  payload,fields=cold._codec_storage.encode_entry_payload(src,archive_member="fixture/member",**opts)
  entry={"logical_path":logical,"transaction_id":tx,"header_offset":0,**fields}
  desc=entry["storage_encoding"]
  proof={"verifier_source_sha256":legacy,"logical_sha256":entry["sha256"],"logical_bytes":entry["bytes"],"logical_crc32":entry["crc32"],"protocol":cold._CODEC_PROOF_PROTOCOL,"storage_descriptor_sha256":hashlib.sha256(json.dumps(desc,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
  ji={k:entry[k] for k in ("logical_path","archive_member","sha256","bytes","crc32","header_offset","storage_encoding")};ji["logical_verification"]=proof
  jp=store._journal_dir(tx)/"journal.json";jp.parent.mkdir(parents=True)
  journal={"transaction_id":tx,"state":"complete","codec_verifier_source_sha256":legacy,"items":[ji]}
  jb=json.dumps(journal,sort_keys=True,separators=(",",":")).encode();jp.write_bytes(jb)
  canon=lambda x:json.dumps(x,sort_keys=True,separators=(",",":")).encode()
  oldsrc=rt/"reports/validation_sources/storage_core_history"/("cold_model_storage_"+legacy+".py");oldsrc.parent.mkdir(parents=True);oldsrc.write_bytes(legacy_src)
  pp=rt/"reports/PORTABLE_TEST_PASS_908e78202071352c0a9798b714f1704b2e7e19fd9bb2252e477f9deebeed7465.json";pp.parent.mkdir(parents=True,exist_ok=True)
  passdoc={"schema_version":"lamost-terminal-portable-tests/1","status":"passed","exit_code":0,"expected_test_count":509,"passed_test_count":509,"bundle_fingerprint_sha256":"908e78202071352c0a9798b714f1704b2e7e19fd9bb2252e477f9deebeed7465","source_hashes":{"runtime_20261025/source/cold_model_storage.py":legacy}}
  pb=json.dumps(passdoc).encode();pp.write_bytes(pb);ps=hashlib.sha256(pb).hexdigest()
  history={"schema":"cold-model-legacy-logical-proof-history/1","historical_core_sha256":legacy,"qualified_pass_sha256":ps,"qualified_pass_bundle_fingerprint":"908e78202071352c0a9798b714f1704b2e7e19fd9bb2252e477f9deebeed7465","qualified_pass_count":509,"entries":[{"logical_path":logical,"transaction_id":tx,"verifier_source_sha256":legacy,"journal_sha256":hashlib.sha256(jb).hexdigest(),"entry_sha256":hashlib.sha256(canon(entry)).hexdigest(),"logical_verification_sha256":hashlib.sha256(canon(proof)).hexdigest()}]}
  hp=rt/"manifests/COLD_VERIFIER_HISTORY_20261028.json";hp.parent.mkdir(parents=True);hb=json.dumps(history,sort_keys=True,separators=(",",":")).encode();hp.write_bytes(hb)
  return store,entry,ji,oldsrc,pp,hp,legacy,hashlib.sha256(hb).hexdigest(),ps,jb,hb,pb,legacy_src
 def test_historical_bound_proof_accepts_and_rejects_tampered_bindings(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   store,entry,ji,oldsrc,pp,hp,legacy,hs,ps,jb,hb,pb,srcbytes=self._legacy_history_fixture(td)
   with patch.object(cold,"_LEGACY_CORE_SHA256",legacy),patch.object(cold,"_LEGACY_HISTORY_SHA256",hs),patch.object(cold,"_LEGACY_PASS_SHA256",ps),patch.object(cold,"_LEGACY_HISTORY_ENTRY_COUNT",1):
    self.assertTrue(store._has_completed_logical_verification(entry))
    cases=[(oldsrc,b"bad"),(pp,b"{}"),(hp,b"{}")]
    jp=store._journal_dir(entry["transaction_id"])/"journal.json"
    for path,bad in cases:
     original=path.read_bytes();path.write_bytes(bad)
     self.assertFalse(store._has_completed_logical_verification(entry))
     path.write_bytes(original)
    jd=json.loads(jb);jd["codec_verifier_source_sha256"]="d"*64;jp.write_text(json.dumps(jd))
    self.assertFalse(store._has_completed_logical_verification(entry));jp.write_bytes(jb)
    changed=dict(entry);changed["header_offset"]=7
    self.assertFalse(store._has_completed_logical_verification(changed))
    badpolicy=json.loads(hb);badpolicy["schema"]="unrecognized"
    hp.write_text(json.dumps(badpolicy,sort_keys=True,separators=(",",":")))
    self.assertFalse(store._has_completed_logical_verification(entry))

if __name__=="__main__":unittest.main(verbosity=2)
