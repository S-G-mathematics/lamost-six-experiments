import importlib.util,pathlib,tempfile,zipfile,hashlib,os,sys,unittest
from unittest import mock
H=pathlib.Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location("rr",H/"release_retention.py");rr=importlib.util.module_from_spec(s);sys.modules["rr"]=rr;s.loader.exec_module(rr)
class Tests(unittest.TestCase):
 def fx(self):
  t=tempfile.TemporaryDirectory();b=pathlib.Path(t.name);root=b/"root";root.mkdir();data=b"tiny arrays"
  rel="runtime_20261025/artifacts/e4/rep_1/eval/direct/rf/A_half/test_outcomes.npz";p=root/rel;p.parent.mkdir(parents=True);p.write_bytes(data);row={"source_path":rel,"archive_member":rel,"source_bytes":len(data),"source_sha256":hashlib.sha256(data).hexdigest(),"archive_crc32":"%08x"%__import__("zlib").crc32(data),"asset":"a.zip","aliases":[]};cache=root/"cache";cache.mkdir();z=cache/"a.zip"
  with zipfile.ZipFile(z,"w",zipfile.ZIP_STORED) as q:q.writestr(rel,data)
  asset={"bytes":z.stat().st_size,"sha256":rr.sha(z)};return t,b,root,p,data,row,z,asset
 def test_roundtrip_exact(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   rr.check_zip(z,a,row);p.unlink();i=b/"state.json";rr.atomic(i,{"schema":rr.INDEX,"retired":[{**row,"asset_bytes":a["bytes"],"asset_sha256":a["sha256"],"verified_copy_path":str(z)}],"restore_required":True});rr.restore(type("A",(),{"root":str(r),"state":str(i),"cache":str(r/"cache")})());self.assertEqual(p.read_bytes(),d)
  finally:t.cleanup()
 def test_two_members_of_one_asset_verify_whole_zip_once(self):
  import unittest.mock
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);one=b"first payload";two=b"second payload";n1="runtime_20261025/artifacts/e4/rep_1/eval/direct/rf/A_half/test_outcomes.npz";n2="runtime_20261025/artifacts/e4/rep_1/eval/direct/rf/F_half/test_outcomes.npz";z=root/"asset.zip"
   with zipfile.ZipFile(z,"w",zipfile.ZIP_STORED) as f:f.writestr(n1,one);f.writestr(n2,two)
   asset={"name":"asset.zip","bytes":z.stat().st_size,"sha256":rr.sha(z)}
   rows=[]
   for name,data in ((n1,one),(n2,two)):
    rows.append({"archive_member":name,"source_bytes":len(data),"source_sha256":hashlib.sha256(data).hexdigest(),"archive_crc32":"%08x"%__import__("zlib").crc32(data)})
   cached=None
   with unittest.mock.patch.object(rr,"verify_asset",wraps=rr.verify_asset) as whole:
    for row in rows:
     witness,cached=rr.verified_asset_once(z,asset,cached);rr.check_member(z,row,witness)
    self.assertEqual(whole.call_count,1)

 def test_wrong_zip_hash(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   with self.assertRaises(rr.RetentionError):rr.check_zip(z,{"bytes":a["bytes"],"sha256":"0"*64},row)
  finally:t.cleanup()
 def test_unsafe_path(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   q=b/"bad.zip"
   with zipfile.ZipFile(q,"w") as f:f.writestr("../escape",d)
   with self.assertRaises(rr.RetentionError):rr.check_zip(q,{"bytes":q.stat().st_size,"sha256":rr.sha(q)},dict(row,archive_member="../escape"))
  finally:t.cleanup()
 def test_member_sha_and_missing(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   with self.assertRaises(rr.RetentionError):rr.check_zip(z,a,dict(row,source_sha256="0"*64))
   with self.assertRaises(rr.RetentionError):rr.check_zip(z,a,dict(row,archive_member="absent"))
  finally:t.cleanup()
 def test_conflict_never_overwrites(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   i=b/"s.json";rr.atomic(i,{"schema":rr.INDEX,"retired":[{**row,"asset_bytes":a["bytes"],"asset_sha256":a["sha256"],"verified_copy_path":str(z)}],"restore_required":True})
   p.write_bytes(b"conflicting bytes")
   with self.assertRaises(rr.RetentionError):rr.restore(type("A",(),{"root":str(r),"state":str(i),"cache":str(r/"cache")})())
   self.assertEqual(p.read_bytes(),b"conflicting bytes")
  finally:t.cleanup()
 def test_alias_group_is_not_retirable(self):
  t,b,r,p,d,row,z,a=self.fx()
  try:
   alias=p.parent/"attempts"/"id"/"test_outcomes.npz";alias.parent.mkdir(parents=True,exist_ok=True);os.link(p,alias);self.assertEqual(p.stat().st_nlink,2);self.assertEqual(row["aliases"],[])
  finally:t.cleanup()

 def test_complete_inode_group_restore_recreates_links(self):
  t,b,root,p,data,row,z,asset=self.fx()
  try:
   alias=p.parent/"attempts"/"id"/"test_outcomes.npz";alias.parent.mkdir(parents=True,exist_ok=True);os.link(p,alias)
   row.update(native_paths=[row["source_path"],str(alias.relative_to(root))],link_count=2,review_only=True)
   rr.check_zip(z,asset,row);p.unlink();alias.unlink()
   entry={**row,"retirement_kind":"complete_inode_group","original_mode":0o644,"asset_bytes":asset["bytes"],"asset_sha256":asset["sha256"],"verified_copy_path":str(z)}
   idx=b/"group.json";rr.atomic(idx,{"schema":rr.INDEX,"retired":[entry],"restore_required":True})
   out=rr.restore(type("A",(),{"root":str(root),"state":str(idx),"cache":str(root/"cache")})())
   self.assertEqual(out["restored"],[row["source_path"]]);self.assertEqual(p.read_bytes(),data);self.assertEqual(alias.read_bytes(),data)
   self.assertEqual((p.stat().st_dev,p.stat().st_ino),(alias.stat().st_dev,alias.stat().st_ino));self.assertEqual(p.stat().st_nlink,2)
  finally:t.cleanup()
 def test_unknown_hardlink_blocks_group(self):
  t,b,root,p,data,row,z,asset=self.fx()
  try:
   alias=p.parent/"attempts"/"id"/"test_outcomes.npz";extra=p.parent/"attempts"/"other"/"test_outcomes.npz";alias.parent.mkdir(parents=True,exist_ok=True);extra.parent.mkdir(parents=True,exist_ok=True);os.link(p,alias);os.link(p,extra)
   group={**row,"native_paths":[row["source_path"],str(alias.relative_to(root))],"link_count":2}
   with self.assertRaises(rr.RetentionError):rr._check_group(root,group)
  finally:t.cleanup()


 def test_plan_target_cap_is_exactly_four_gib(self):
  with tempfile.TemporaryDirectory() as td:
   b=pathlib.Path(td);root=b/"root";root.mkdir();mp=b/"manifest.json";mp.write_text(__import__("json").dumps({"schema":"lamost-scientific-array-release/1","assets":[],"files":[]}))
   db=b/"registry.sqlite";c=__import__("sqlite3").connect(db);c.execute("create table tasks(key text,record text)");c.commit();c.close()
   accepted=rr.make_plan(root,mp,db,target=4*rr.GIB);self.assertEqual(accepted["target_bytes"],4*rr.GIB);self.assertEqual(accepted["selected_count"],0)
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db,target=4*rr.GIB+1)
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db,target=-1)

 def test_plan_flags_exact_complete_group_review_only(self):
  t,b,root,p,data,row,z,asset=self.fx()
  try:
   alias=p.parent/"attempts"/"id"/"test_outcomes.npz";alias.parent.mkdir(parents=True,exist_ok=True);os.link(p,alias)
   relalias=str(alias.relative_to(root));key="e4/rep_1/eval/direct/rf/A_half"
   valdir=root/"runtime_20261025/artifacts"/key;valdir.mkdir(parents=True,exist_ok=True)
   rr.atomic(valdir/"validation.json",{"status":"validated","task_key":key,"files":{"test_outcomes.npz":row["source_sha256"]}})
   manifest={"schema":"lamost-scientific-array-release/1","assets":[{"name":"a.zip"}],"files":[{"category":"runtime_test_outcomes",**row,"aliases":[relalias]}]}
   mp=b/"manifest.json";rr.atomic(mp,manifest)
   rec={"key":key,"experiment":4,"kind":"eval","status":"validated_terminal","outcome":"successful","validation_state":"validated","scientific_case":True,"condition":"A_half","route":"direct","dependencies":["e4/rep_1/fit/direct/rf/A_half"]}
   db=b/"registry.sqlite";c=__import__("sqlite3").connect(db);c.execute("create table tasks(key text,record text)");c.execute("insert into tasks values(?,?)",(key,__import__("json").dumps(rec)));c.commit();c.close()
   plan=rr.make_plan(root,mp,db,target=100000)
   self.assertEqual(plan["strict_single_link_eligible_count"],0)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],1)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["selected_count"],1)
   self.assertFalse(plan["complete_known_inode_group_review_only"]["retirement_enabled"])
  finally:t.cleanup()


 def test_restore_two_assets_with_single_asset_cache(self):
  t,b,root,p1,d1,row1,z1,a1=self.fx()
  try:
   p1.unlink()
   d2=b"second tiny array";rel2="runtime_20261025/artifacts/e4/rep_1/eval/direct/rf/F_half/test_outcomes.npz";p2=root/rel2;p2.parent.mkdir(parents=True);p2.write_bytes(d2)
   row2={"source_path":rel2,"archive_member":rel2,"source_bytes":len(d2),"source_sha256":hashlib.sha256(d2).hexdigest(),"archive_crc32":"%08x"%__import__("zlib").crc32(d2),"asset":"b.zip","aliases":[]}
   z2=b/"remote-b.zip"
   with zipfile.ZipFile(z2,"w",zipfile.ZIP_STORED) as q:q.writestr(rel2,d2)
   a2={"bytes":z2.stat().st_size,"sha256":rr.sha(z2)}
   p2.unlink()
   e1={**row1,"asset_name":"a.zip","asset_bytes":a1["bytes"],"asset_sha256":a1["sha256"],"verified_copy_path":str(z1),"repo":"test/repo","tag":"test-tag","retirement_kind":"single_link","original_mode":0o644}
   e2={**row2,"asset_name":"b.zip","asset_bytes":a2["bytes"],"asset_sha256":a2["sha256"],"verified_copy_path":str(root/"cache"/"b.zip"),"repo":"test/repo","tag":"test-tag","retirement_kind":"single_link","original_mode":0o644}
   idx=b/"multi.json";rr.atomic(idx,{"schema":rr.INDEX,"retired":[e1,e2],"restore_required":True})
   original=rr.download
   def fake_download(repo,tag,name,dest):
    self.assertEqual((repo,tag),("test/repo","test-tag"));target=pathlib.Path(dest)/name
    import shutil;shutil.copyfile(z2,target);return target
   rr.download=fake_download
   try:out=rr.restore(type("A",(),{"root":str(root),"state":str(idx),"cache":str(root/"cache"),"repo":None,"tag":None,"disk_floor":0})())
   finally:rr.download=original
   self.assertEqual(out["restored"],[rel1:=row1["source_path"],rel2]);self.assertEqual(p1.read_bytes(),d1);self.assertEqual(p2.read_bytes(),d2)
   self.assertEqual([x.name for x in (root/"cache").iterdir()],["b.zip"])
  finally:t.cleanup()


 def test_native_source_mismatch_blocks_retirement_preflight(self):
  t,b,root,p,data,row,z,asset=self.fx()
  try:
   p.write_bytes(b"changed native bytes")
   with self.assertRaises(rr.RetentionError):rr.verify_native_single(root,row)
  finally:t.cleanup()


 def test_verified_worker_source_binds_freeze_sha(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime";src=rt/"source/parallel_rf";src.mkdir(parents=True);p=src/"worker.py";p.write_bytes(b"fixture worker")
   (rt/"manifests").mkdir();freeze=rt/"manifests/freeze.json";digest=hashlib.sha256(p.read_bytes()).hexdigest();freeze.write_text(__import__("json").dumps({"source_sha256":{"parallel_rf/worker.py":digest}}))
   self.assertEqual(rr._verified_worker_source(rt,"parallel_rf/worker.py"),p.resolve())
   freeze.write_text(__import__("json").dumps({"source_sha256":{"parallel_rf/worker.py":"0"*64}}))
   with self.assertRaisesRegex(rr.RetentionError,"frozen source binding"):rr._verified_worker_source(rt,"parallel_rf/worker.py")

 def test_project_relative_script_identity(self):
  rt=pathlib.Path("/project/runtime")
  self.assertTrue(rr._script_matches(["python","-u","source/controller.py","run"],rt,rt,("controller.py",)))
  self.assertTrue(rr._script_matches(["python","source/parallel_rf/worker.py"],rt,rt,("parallel_rf/worker.py",)))
  self.assertFalse(rr._script_matches(["python","source/controller.py"],pathlib.Path("/other"),rt,("controller.py",)))
  self.assertFalse(rr._script_matches(["python","-c","source/controller.py"],rt,rt,("controller.py",)))


 def test_hold_cleanup_requires_exact_owner_nonce(self):
  with tempfile.TemporaryDirectory() as td:
   hp=pathlib.Path(td)/"ADMISSION_HOLD.json";doc={"owner_operation":"release_retention_20261030","nonce":"n1","operation_id":"op1"};hp.write_text(__import__("json").dumps(doc))
   old=(rr._HOLD_DOC,rr._HOLD_PATH,rr._OWNER_SNAPSHOT,rr._controller_identity)
   try:
    rr._HOLD_DOC=doc;rr._HOLD_PATH=hp;rr._OWNER_SNAPSHOT={"owner":"expected"};rr._controller_identity=lambda rt:{"owner":"expected"};rr.release_guard()
    self.assertFalse(hp.exists())
   finally:rr._HOLD_DOC,rr._HOLD_PATH,rr._OWNER_SNAPSHOT,rr._controller_identity=old
 def test_foreign_hold_is_never_removed(self):
  with tempfile.TemporaryDirectory() as td:
   hp=pathlib.Path(td)/"ADMISSION_HOLD.json";foreign={"owner_operation":"other","nonce":"foreign","operation_id":"foreign"};hp.write_text(__import__("json").dumps(foreign))
   own={"owner_operation":"release_retention_20261030","nonce":"mine","operation_id":"mine"};old=(rr._HOLD_DOC,rr._HOLD_PATH,rr._OWNER_SNAPSHOT,rr._controller_identity)
   try:
    rr._HOLD_DOC=own;rr._HOLD_PATH=hp;rr._OWNER_SNAPSHOT={"owner":"expected"};rr._controller_identity=lambda rt:{"owner":"expected"};rr.release_guard()
    self.assertEqual(__import__("json").loads(hp.read_text()),foreign)
   finally:rr._HOLD_DOC,rr._HOLD_PATH,rr._OWNER_SNAPSHOT,rr._controller_identity=old


 def test_waits_under_owned_hold_while_verified_phase_drains(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime";rt.mkdir();hold=rt/"ADMISSION_HOLD.json";own={"owner_operation":"release_retention_20261030","nonce":"own","operation_id":"op"};hold.write_text(__import__("json").dumps(own))
   owner={"pid":123,"process_start_ticks":"9","code_sha256":"abc"};old=(rr._HOLD_DOC,rr._controller_identity,rr.time.sleep);checks=[]
   def observe(path,pid):
    self.assertEqual(__import__("json").loads(hold.read_text()),own);checks.append(pid)
    return {"busy":len(checks)==1,"active_registry_tasks":1 if len(checks)==1 else 0}
   try:
    rr._HOLD_DOC=own;rr._controller_identity=lambda path:owner;rr.time.sleep=lambda seconds:None
    state=rr._wait_for_science_drain(rt,owner,timeout=10,poll=1,observe=observe)
    self.assertEqual(checks,[123,123]);self.assertFalse(state["busy"]);self.assertTrue(hold.exists())
   finally:rr._HOLD_DOC,rr._controller_identity,rr.time.sleep=old

 def test_science_drain_timeout_is_bounded_and_leaves_owned_hold_for_caller_cleanup(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime";rt.mkdir();hold=rt/"ADMISSION_HOLD.json";own={"owner_operation":"release_retention_20261030","nonce":"own","operation_id":"op"};hold.write_text(__import__("json").dumps(own))
   owner={"pid":123,"process_start_ticks":"9","code_sha256":"abc"};old=(rr._HOLD_DOC,rr._controller_identity,rr.time.monotonic,rr.time.sleep)
   try:
    rr._HOLD_DOC=own;rr._controller_identity=lambda path:owner;rr.time.monotonic=lambda:0 if not hasattr(rr,"_timeout_tick") else 2;rr._timeout_tick=False
    def monotonic():return 0 if not rr._timeout_tick else 2
    rr.time.monotonic=monotonic;rr.time.sleep=lambda seconds:setattr(rr,"_timeout_tick",True)
    with self.assertRaisesRegex(rr.RetentionError,"690 second bound"):
     rr._wait_for_science_drain(rt,owner,timeout=1,poll=1,observe=lambda path,pid:{"busy":True})
    self.assertEqual(__import__("json").loads(hold.read_text()),own)
   finally:
    rr.__dict__.pop("_timeout_tick",None);rr._HOLD_DOC,rr._controller_identity,rr.time.monotonic,rr.time.sleep=old

 def test_quiet_timeout_cleans_only_its_own_hold(self):
  import fcntl
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime";(rt/"locks").mkdir(parents=True);(rt/"finalize.lock").write_text("")
   owner={"pid":123,"process_start_ticks":"9","code_sha256":"abc"};tick=[0]
   def fake_flock(fd,op):
    if op & fcntl.LOCK_UN:return None
    try:name=pathlib.Path(os.readlink("/proc/self/fd/"+str(fd))).name
    except OSError:name=""
    if name=="finalize.lock":raise BlockingIOError()
    return None
   def advance(seconds):tick[0]+=seconds
   with mock.patch.object(rr,"_controller_identity",return_value=owner),mock.patch.object(rr,"_quiescence_observation",return_value={"busy":True,"active_registry_tasks":1}),mock.patch.object(rr,"_check_quiescent"),mock.patch.object(rr.shutil,"disk_usage",return_value=type("Usage",(),{"free":100*rr.GIB})()),mock.patch.object(rr.time,"monotonic",side_effect=lambda:tick[0]),mock.patch.object(rr.time,"sleep",side_effect=advance),mock.patch.object(rr,"SCIENCE_DRAIN_MAX_SECONDS",1),mock.patch.object(rr,"SCIENCE_DRAIN_POLL_SECONDS",1),mock.patch("fcntl.flock",side_effect=fake_flock):
    with self.assertRaisesRegex(rr.RetentionError,"690 second bound"):rr.quiet(rt,20*rr.GIB)
   self.assertFalse((rt/"ADMISSION_HOLD.json").exists());self.assertIsNone(rr._HOLD_DOC);self.assertEqual(rr._GUARD_FDS,[])

 def test_stopped_controller_restore_requires_terminal_registry(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime";(rt/"source").mkdir(parents=True);controller=rt/"source/controller.py";controller.write_text("immutable fixture")
   owner={"pid":99999999,"process_start_ticks":"1","code_sha256":hashlib.sha256(controller.read_bytes()).hexdigest(),"instance_id":"fixture"};(rt/"owner.json").write_text(__import__("json").dumps(owner))
   (rt/"EXECUTION_TERMINAL.json").write_text(__import__("json").dumps({"tasks":2,"observed_utc":"fixture"}))
   db=__import__("sqlite3").connect(rt/"registry.sqlite");db.execute("create table tasks(key text,record text)")
   for i in range(2):db.execute("insert into tasks values(?,?)",(str(i),__import__("json").dumps({"status":"validated_terminal"})))
   db.commit();db.close();self.assertEqual(rr.terminal_evidence(rt,2)["tasks"],2)
   db=__import__("sqlite3").connect(rt/"registry.sqlite");db.execute("update tasks set record=? where key='1'",(__import__("json").dumps({"status":"running"}),));db.commit();db.close()
   with self.assertRaises(rr.RetentionError):rr.terminal_evidence(rt,2)

if __name__=="__main__":unittest.main()
