import importlib.util, json, os, tempfile, time, unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/'source'
spec=importlib.util.spec_from_file_location('cold_auto_compaction',SRC/'cold_auto_compaction.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Stat:
 def __init__(self,size=100,inode=7,mtime=9):self.st_size=size;self.st_ino=inode;self.st_mtime_ns=mtime

class CompactorPreflightTests(unittest.TestCase):
 def fresh_observation(self,minimum=100):
  import datetime
  return {'observed_utc':datetime.datetime.fromtimestamp(time.time(),datetime.timezone.utc).isoformat(),'minimum_free_bytes':minimum}

 def test_storage_trigger_below_two_gib_or_below_minimum(self):
  obs=self.fresh_observation()
  self.assertEqual(m.should_trigger_storage(obs,100+m.STORAGE_TRIGGER_HEADROOM-1,time.time())[0],True)
  self.assertEqual(m.should_trigger_storage(obs,99,time.time())[1],'storage_below_controller_minimum')
  self.assertEqual(m.should_trigger_storage(obs,100+m.STORAGE_TRIGGER_HEADROOM,time.time())[0],False)

 def test_stale_observation_backoffs(self):
  obs=self.fresh_observation();self.assertEqual(m.should_trigger_storage(obs,0,time.time()+301)[1],'storage_observation_stale')

 def test_unknown_running_owner_blocks_before_hold(self):
  decision,reason=m.preflight_decision(storage_trigger=True,observation_fresh=True,queue_complete=False,finalizer_busy=False,admission_hold=False,pending_journal=False,batch_busy=False,reader_busy=False,driver_lock_acquired=True,running_verified=False,resource_admission_ok=False,source_io_ok=True,baseline_ok=True,failures_last_hour=0)
  self.assertEqual((decision,reason),('backoff','running_process_identity_unresolved'))

 def test_driver_lock_prevents_duplicate_invocation(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'lock';held=m.acquire_driver_lock(path)
   try:self.assertIsNone(m.acquire_driver_lock(path))
   finally:held.close()
   other=m.acquire_driver_lock(path);self.assertIsNotNone(other);other.close()

 def test_manual_batch_lock_busy_is_observed_without_breaking_lock(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'batch-wrapper.lock'
   with path.open('a+') as held:
    import fcntl
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    self.assertFalse(m.file_lock_probe(path))
    self.assertEqual(m.preflight_decision(storage_trigger=True,observation_fresh=True,queue_complete=False,finalizer_busy=False,admission_hold=False,pending_journal=False,batch_busy=True,reader_busy=False,driver_lock_acquired=True,running_verified=True,resource_admission_ok=True,source_io_ok=True,baseline_ok=True,failures_last_hour=0)[0],'backoff')

 def test_batch_and_reader_leases_backoff(self):
  base=dict(storage_trigger=True,observation_fresh=True,queue_complete=False,finalizer_busy=False,admission_hold=False,pending_journal=False,batch_busy=False,reader_busy=False,driver_lock_acquired=True,running_verified=True,resource_admission_ok=True,source_io_ok=True,baseline_ok=True,failures_last_hour=0)
  self.assertEqual(m.preflight_decision(**{**base,'batch_busy':True})[0],'backoff')
  self.assertEqual(m.preflight_decision(**{**base,'reader_busy':True})[0],'backoff')
  self.assertEqual(m.preflight_decision(**{**base,'resource_admission_ok':False})[0],'backoff')

 def test_complete_queue_or_finalizer_never_compacts(self):
  base=dict(storage_trigger=True,observation_fresh=True,queue_complete=False,finalizer_busy=False,admission_hold=False,pending_journal=False,batch_busy=False,reader_busy=False,driver_lock_acquired=True,running_verified=True,resource_admission_ok=True,source_io_ok=True,baseline_ok=True,failures_last_hour=0)
  self.assertEqual(m.preflight_decision(**{**base,'queue_complete':True})[0],'exit')
  self.assertEqual(m.preflight_decision(**{**base,'finalizer_busy':True})[1],'finalizer_owns_archive')

 def test_wrong_archive_hash_blocks_and_preserves_models(self):
  with tempfile.TemporaryDirectory() as td:
   model=Path(td)/'unique-model.joblib';model.write_bytes(b'preserve-me')
   manifest={'schema_version':'lamost-cold-model-store/1','archive_path':'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip','archive_bytes':100,'archive_sha256':'b'*64,'transaction_id':'a'*32}
   journal={'state':'complete','created_utc':'2099-01-01T00:00:00Z','archive_sha256_after':'a'*64,'archive_bytes_after':100,'transaction_id':'a'*32}
   with self.assertRaises(RuntimeError):m.validate_archive_chain(manifest,journal,Stat(100))
   self.assertEqual(model.read_bytes(),b'preserve-me')

 def test_pending_or_failed_journal_blocks(self):
  self.assertTrue(m.journal_requires_review({'state':'incomplete'}))
  self.assertFalse(m.journal_requires_review({'state':'rolled_back'}))
  self.assertFalse(m.journal_requires_review({'state':'complete'}))
  doc={'schema_version':'lamost-cold-model-store/1','archive_path':'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip','archive_bytes':100,'archive_sha256':'a'*64,'transaction_id':'a'*32}
  wrong={'state':'complete','archive_sha256_after':'a'*64,'archive_bytes_after':100,'transaction_id':'b'*32}
  with self.assertRaises(RuntimeError):m.validate_archive_chain(doc,wrong,Stat(100))

 def test_pending_task_with_no_running_worker_is_not_complete(self):
  meta={'task_count':3,'nonterminal_count':1,'running_count':0}
  self.assertFalse(m.registry_complete(meta))
  self.assertTrue(m.registry_complete({'task_count':3,'nonterminal_count':0,'running_count':0}))

 def test_readonly_registry_snapshot_returns_aggregate_and_running_only(self):
  with tempfile.TemporaryDirectory() as td:
   db=__import__('sqlite3').connect(Path(td)/'registry.sqlite')
   db.execute('CREATE TABLE tasks(key TEXT PRIMARY KEY, record TEXT NOT NULL)')
   db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
   rows=[('done',{'key':'done','status':'validated_terminal'}),('wait',{'key':'wait','status':'planned'}),('run',{'key':'run','status':'running','pid':42})]
   db.executemany('INSERT INTO tasks VALUES (?,?)',[(k,json.dumps(v)) for k,v in rows])
   db.execute("INSERT INTO meta VALUES ('sample','fixture')");db.commit();db.close()
   running,meta=m.records_readonly(Path(td)/'registry.sqlite')
   self.assertEqual(set(running),{'run'})
   self.assertEqual((meta['task_count'],meta['nonterminal_count'],meta['running_count']),(3,2,1))
   self.assertEqual(meta['sample'],'fixture')

 def test_preflight_only_cannot_launch_and_receipt_json_roundtrips(self):
  self.assertFalse(m.launch_permitted(True));self.assertTrue(m.launch_permitted(False))
  source=(SRC/'cold_auto_compaction.py').read_text()
  self.assertLess(source.index('if preflight_only:return early'),source.index('subprocess.Popen'))
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'receipt.json';m.atomic_json(p,{'status':'preflight_ready','reason':'read_only'});self.assertEqual(json.loads(p.read_text()),{'reason':'read_only','status':'preflight_ready'})

 def test_real_proc_cmdline_uses_nul_delimiters(self):
  raw=Path('/proc/self/cmdline').read_bytes().decode(errors='replace')
  expected=[x for x in raw.split(chr(0)) if x]
  self.assertEqual(m.proc_cmd(os.getpid()),expected)
  self.assertTrue(expected)

 def test_three_failed_operations_require_review(self):
  import datetime
  stamp=datetime.datetime.fromtimestamp(time.time(),datetime.timezone.utc).isoformat()
  d={f'{i}/driver_result.json':{'observed_utc':stamp,'status':'wrapper_failed'} for i in range(3)}
  with tempfile.TemporaryDirectory() as td:
   for name,row in d.items():
    p=Path(td)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(row))
   self.assertEqual(m.failure_count_last_hour(Path(td),time.time()),3)
  self.assertEqual(m.preflight_decision(storage_trigger=True,observation_fresh=True,queue_complete=False,finalizer_busy=False,admission_hold=False,pending_journal=False,batch_busy=False,reader_busy=False,driver_lock_acquired=True,running_verified=True,resource_admission_ok=True,source_io_ok=True,baseline_ok=True,failures_last_hour=3)[0],'review_required')

 def test_same_child_pid_ticks_means_not_gone(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'123';p.mkdir();(p/'stat').write_text('123 (py) '+' '.join(['S']+['0']*18+['77']+['0']*5))
   (p/'cmdline').write_bytes(b'/usr/bin/python\\0/x/commit_batch_child.py\\0')
   self.assertFalse(m.process_identity_is_gone(123,'77','/x/commit_batch_child.py',Path(td)))
   self.assertTrue(m.process_identity_is_gone(123,'76','/x/commit_batch_child.py',Path(td)))

if __name__=='__main__':unittest.main()
