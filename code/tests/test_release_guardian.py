import importlib.util,json,os,pathlib,sqlite3,tempfile,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("release_guardian",HERE/"release_guardian.py")
g=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(g)

class GuardianTests(unittest.TestCase):
 def test_finalize_lock_excludes_second_guardian(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime_20261025";rt.mkdir()
   a=g.lock_finalize(rt)
   try:
    with self.assertRaises(g.GuardianError):g.lock_finalize(rt)
   finally:
    import fcntl;fcntl.flock(a,fcntl.LOCK_UN);a.close()
   b=g.lock_finalize(rt);b.close()
 def test_release_denied_until_restored_and_verified(self):
  idx={"restore_required":True,"retired":[{"source_path":"runtime_20261025/artifacts/e4/x/test_outcomes.npz"}]}
  self.assertFalse(g.release_authorized({"status":"restore_required"},idx,True))
  self.assertFalse(g.release_authorized({"status":"complete"},idx,True))
  self.assertFalse(g.release_authorized({"status":"complete"},{"restore_required":False,"retired":[]},False))
  self.assertTrue(g.release_authorized({"status":"complete"},{"restore_required":False,"retired":[]},True))
 def test_registry_requires_all_6270_terminal(self):
  with tempfile.TemporaryDirectory() as td:
   db=pathlib.Path(td)/"registry.sqlite";c=sqlite3.connect(db)
   c.execute("create table tasks(key text, record text)")
   c.executemany("insert into tasks values(?,?)",[("a",json.dumps({"status":"validated_terminal"})),("b",json.dumps({"status":"waiting_for_dependency"}))]);c.commit();c.close()
   r=g.registry(td,2);self.assertFalse(r["all_terminal"])
   c=sqlite3.connect(db);c.execute("update tasks set record=? where key='b'",(json.dumps({"status":"validated_terminal"}),));c.commit();c.close()
   self.assertTrue(g.registry(td,2)["all_terminal"])
 def test_relative_proc_script_argument_is_resolved_exactly(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);expected=(root/"runtime_20261025/source/controller.py").resolve()
   paths={expected:"controller.py"}
   self.assertEqual(g.script_match(["python3","source/controller.py"],root/"runtime_20261025",paths),"controller.py")
   self.assertIsNone(g.script_match(["python3","source/controller.py.backup"],root/"runtime_20261025",paths))
 def test_actual_process_identity_has_startticks_uid_and_argv_digest(self):
  x=g.ident(os.getpid());self.assertIsNotNone(x)
  self.assertGreater(x["start_ticks"],0);self.assertEqual(x["uid"],os.getuid());self.assertEqual(len(x["argv_sha256"]),64)
 def test_resume_marker_binds_plan_and_nonce(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);op=root/"operations/release_guardian_20261030";op.mkdir(parents=True)
   g.atomic(op/"guardian_state.json",{"schema":g.SCHEMA,"operation_nonce":"n1","plan_sha256":"a"*64})
   p=g.make_resume(root,"n1","a"*64,"reviewed")
   d=json.loads(p.read_text());self.assertEqual(d["action"],"restore")
   with self.assertRaises(g.GuardianError):g.make_resume(root,"bad","a"*64,"bad")
 def test_restore_verifier_rejects_missing_native_path(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);c={"root":str(root)}
   d={"retired":[{"retirement_kind":"single_link","source_path":"runtime_20261025/artifacts/e4/x/test_outcomes.npz","source_bytes":2}]}
   self.assertFalse(g.check_native(c,d))
 def test_failed_restore_waits_for_new_marker_without_releasing_finalize_lock(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);rt=root/"runtime_20261025";rt.mkdir();op=root/"operations/release_guardian_20261030";op.mkdir(parents=True)
   sp=op/"guardian_state.json";state={"schema":g.SCHEMA,"operation_nonce":"nonce","plan_sha256":"a"*64,"status":"restore_required"};g.atomic(sp,state);lf=g.lock_finalize(rt)
   idx={"schema":"lamost-release-retention-index/1","restore_required":False,"retired":[{"source_path":"runtime_20261025/artifacts/x/a.npz","source_sha256":"b"*64,"source_bytes":1}],"last_restore_utc":"now"}
   cfg={"root":str(root),"retention_state_path":str(op/"index.json"),"poll_seconds":1};calls=[];waits=[]
   marker_path=op/"resume_nonce.json"
   def put_marker():g.atomic(marker_path,{"schema":g.RESUME,"action":"restore","operation_nonce":"nonce","plan_sha256":"a"*64,"request_uid":os.getuid()})
   put_marker();original_wait=g.wait_resume
   def wait(directory,current,stat_path):
    waits.append(1)
    if len(waits)==2:
     with self.assertRaises(g.GuardianError):g.lock_finalize(rt)
     put_marker()
    return original_wait(directory,current,stat_path)
   def helper(_cfg,mode,*args):
    calls.append(mode)
    if len(calls)==1:raise g.GuardianError("injected restore failure")
   try:
    with mock.patch.object(g,"cfgload",return_value=(cfg,root,rt,op)), mock.patch.object(g,"process_rows",return_value=[]), mock.patch.object(g,"registry",return_value={"all_terminal":True}), mock.patch.object(g,"helper",side_effect=helper), mock.patch.object(g,"read_index",return_value=idx), mock.patch.object(g,"check_plan_index"), mock.patch.object(g,"check_native",return_value=True), mock.patch.object(g,"wait_resume",side_effect=wait):
     out=g.restore_after_resume("unused",cfg,state,sp,op,lf)
    self.assertEqual(calls,["restore","restore"]);self.assertEqual(len(waits),2);self.assertEqual(out["status"],"complete")
   finally:
    import fcntl;fcntl.flock(lf,fcntl.LOCK_UN);lf.close()
 def test_archive_preflight_defers_on_foreign_hold_or_writer_lock(self):
  with tempfile.TemporaryDirectory() as td:
   rt=pathlib.Path(td)/"runtime_20261025";rt.mkdir()
   hold=rt/"ADMISSION_HOLD.json";hold.write_text("{}")
   self.assertEqual(g.archive_preflight_busy(rt),"ADMISSION_HOLD.json present")
   hold.unlink();lock=rt/"locks/cold_auto_compaction.lock";lock.parent.mkdir();fd=os.open(lock,os.O_RDWR|os.O_CREAT,0o600)
   import fcntl;fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   try:self.assertEqual(g.archive_preflight_busy(rt),str(lock)+" busy")
   finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
   self.assertIsNone(g.archive_preflight_busy(rt))
 def test_terminal_restore_waits_for_controller_exit(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);rt=root/"runtime_20261025";rt.mkdir();op=root/"operations/release_guardian_20261030";op.mkdir(parents=True)
   sp=op/"guardian_state.json";state={"schema":g.SCHEMA,"operation_nonce":"nonce","plan_sha256":"a"*64,"status":"restore_required"};g.atomic(sp,state);lf=g.lock_finalize(rt)
   marker=op/"resume_nonce.json";g.atomic(marker,{"schema":g.RESUME,"action":"restore","operation_nonce":"nonce","plan_sha256":"a"*64,"request_uid":os.getuid()})
   idx={"schema":"lamost-release-retention-index/1","restore_required":False,"retired":[{"source_path":"runtime_20261025/artifacts/x/a.npz","source_sha256":"b"*64,"source_bytes":1}],"last_restore_utc":"now"}
   cfg={"root":str(root),"retention_state_path":str(op/"index.json"),"poll_seconds":1};controller={"script":"controller.py","pid":123,"start_ticks":55,"uid":1000,"pgid":123,"state":"S","argv_sha256":"c"*64};rows=[ [controller], [] ];calls=[]
   def scan(_rt):return rows.pop(0) if rows else []
   def helper(_cfg,mode,*args):calls.append(mode)
   try:
    with mock.patch.object(g,"cfgload",return_value=(cfg,root,rt,op)), mock.patch.object(g,"process_rows",side_effect=scan), mock.patch.object(g,"registry",return_value={"all_terminal":True}), mock.patch.object(g,"helper",side_effect=helper), mock.patch.object(g,"read_index",return_value=idx), mock.patch.object(g,"check_plan_index"), mock.patch.object(g,"check_native",return_value=True), mock.patch.object(g.time,"sleep",return_value=None):
     out=g.restore_after_resume("unused",cfg,state,sp,op,lf)
    self.assertEqual(calls,["restore"]);self.assertEqual(out["status"],"complete")
   finally:
    import fcntl;fcntl.flock(lf,fcntl.LOCK_UN);lf.close()
 def test_run_entrypoint_initializes_and_releases_lock_on_empty_retirement(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);rt=root/"runtime_20261025";rt.mkdir();op=root/"operations/release_guardian_20261030";op.mkdir(parents=True)
   statepath=op/"guardian_state.json";idxpath=op/"index.json";cfg={"root":str(root),"retention_state_path":str(idxpath),"poll_seconds":1,"plan_sha256":"a"*64,"manifest_sha256":"b"*64,"approval_sha256":"c"*64,"utility_sha256":"d"*64}
   def fake_cfg(_):return cfg,root,rt,op
   empty={"schema":"lamost-release-retention-index/1","restore_required":False,"retired":[]}
   with mock.patch.object(g,"cfgload",side_effect=fake_cfg), mock.patch.object(g,"process_rows",return_value=[]), mock.patch.object(g,"read_index",return_value=empty), mock.patch.object(g,"check_plan_index"), mock.patch.object(g,"archive_preflight_busy",return_value=None), mock.patch.object(g,"helper"):
    result=g.run(str(op/"unused.json"),False)
   self.assertEqual(result["status"],"no_retirement");self.assertTrue(statepath.is_file())
   lock=g.lock_finalize(rt);lock.close()
if __name__=="__main__":unittest.main()

