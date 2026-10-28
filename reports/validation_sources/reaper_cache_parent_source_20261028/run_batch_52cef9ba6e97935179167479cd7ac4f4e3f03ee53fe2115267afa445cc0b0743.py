from pathlib import Path
import sys,os,json,hashlib,datetime,time,sqlite3,subprocess,signal,fcntl,traceback,argparse
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025';D=Path(__file__).resolve().parent.parent;H=R/'ADMISSION_HOLD.json'
sys.path.insert(0,str(R/'source'));import controller as c
from batch_plan import MAX_INITIAL_BYTES,MAX_INITIAL_GROUPS,MAX_LATER_BYTES,MAX_LATER_GROUPS,resource_admission_ready
CHILD_WALL_SECONDS=180
FOLLOWUP_CHILD_WALL_SECONDS=600
ARCHIVE_IO_PROFILE='bounded-1800'
ARCHIVE_IO_WALL_SECONDS=1800
CODEC_FOLLOWUP_MAX_BYTES=1<<30
CODEC_FOLLOWUP_MAX_GROUPS=1
SOURCE_PINS={
 'commit_batch_child.py':'4c4cbd301a09dadeada3da4f1a489d8452af09aa09d9d145e78d63fa2dd0d183',
 'controller.py':'68b081487afd8f7572362d33601b276b245150d9bca587aca5bf3b9cace75c10',
 'batch_plan.py':'d1a74d154e279947d5cf1138b8d5b90fea25a9d7fda93cfd90d0a238c3d1d870',
 'admission_evidence.py':'f2369fb24c39dde7241f12f6cb7831358168897a76810809d3f72cc351dc86b9',
 'cold_model_storage.py':'ba909e9f55f5f8020f165a5ac42f4159eed4c8c4b69b64f95f7313fd82430943',
 'cold_codec_storage.py':'9318ee513b923ff1c959e989569fe24549f11f6eb6d0b338cae390e3651cb76c',
 'reversible_joblib_codec.py':'189b5ab887f47931638cf65aa183239ce077931de0673fc690fcf2c1c86355ca',
 'cold_storage_safety.py':'6b9f012d55f0f2b80ab818477d2bd7cd9deca2bbba5a4288786c93c39a4842f1',
 'batch_plan.py':'d1a74d154e279947d5cf1138b8d5b90fea25a9d7fda93cfd90d0a238c3d1d870',
}
BATCH_POLICIES={"initial":{"max_bytes":MAX_INITIAL_BYTES,"max_groups":MAX_INITIAL_GROUPS,"wall_seconds":CHILD_WALL_SECONDS,"packing":"smallest_first","storage_codec_policy":None},"storage-followup":{"max_bytes":MAX_LATER_BYTES,"max_groups":MAX_LATER_GROUPS,"wall_seconds":FOLLOWUP_CHILD_WALL_SECONDS,"packing":"largest_first","storage_codec_policy":None},"storage-followup-codec":{"max_bytes":CODEC_FOLLOWUP_MAX_BYTES,"max_groups":CODEC_FOLLOWUP_MAX_GROUPS,"wall_seconds":FOLLOWUP_CHILD_WALL_SECONDS,"packing":"largest_first","storage_codec_policy":"reversible-xz-v1"}}
def resolve_batch_policy(batch_policy,storage_codec_policy,archive_io_profile=None):
 if batch_policy not in BATCH_POLICIES:raise ValueError('unknown batch policy')
 base=BATCH_POLICIES[batch_policy]
 if storage_codec_policy!=base['storage_codec_policy']:raise ValueError('batch/storage codec policy mismatch')
 if archive_io_profile is None:return base
 if archive_io_profile!=ARCHIVE_IO_PROFILE:raise ValueError('unknown archive I/O profile')
 if batch_policy!='storage-followup' or storage_codec_policy is not None:
  raise ValueError('bounded archive I/O profile is only valid for raw storage-followup')
 result=dict(base);result['wall_seconds']=ARCHIVE_IO_WALL_SECONDS;result['archive_io_profile']=archive_io_profile
 return result

def archive_io_profile_args(profile):
 if profile is None:return []
 if profile!=ARCHIVE_IO_PROFILE:raise ValueError('unknown archive I/O profile')
 return ['--archive-io-profile',profile]

TERM_GRACE_SECONDS=30
CHILD_AGGREGATE_RSS_BYTES=1<<30
CHILD_ADDRESS_SPACE_BYTES=896<<20
def admission_ready(unresolved,available,commitments,helper_reservation):
 return resource_admission_ready(len(unresolved),available,commitments,helper_reservation,c.memory_admission_ok)

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(p,o):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');os.replace(t,p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def codec_policy_args(storage_codec_policy):
 return [] if storage_codec_policy is None else ['--storage-codec-policy',storage_codec_policy]
def verify_storage_source_pins():
 for name,digest in SOURCE_PINS.items():
  path=R/'source'/name
  if not path.is_file() or sha(path)!=digest:raise RuntimeError('storage batch source pin mismatch: '+name)
def records():
 db=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True)
 db.execute('PRAGMA query_only=ON')
 mem=sqlite3.connect(':memory:');db.backup(mem);db.close()
 v=[json.loads(x[0]) for x in mem.execute('select record from tasks')];mem.close();return v

def verify_controller():
 o=json.loads((R/'owner.json').read_text()); pid=int(o['pid']);p=Path('/proc')/str(pid)
 if not p.exists() or c.start_ticks(pid)!=str(o['process_start_ticks']):raise RuntimeError('controller process identity no longer matches owner record')
 args=(p/'cmdline').read_bytes().decode().split('\0');args=[x for x in args if x]
 if args[:2]!=[str(ROOT/'venv/bin/python'),'-u']:raise RuntimeError('unexpected controller argv prefix')
 if (Path(os.readlink(p/'cwd'))/args[2]).resolve()!=(R/'source/controller.py').resolve():raise RuntimeError('controller script/cwd identity mismatch')
 if o.get('instance_id')!='i-095641a281a4038b9':raise RuntimeError('controller owner instance mismatch')
 if sha(R/'source/controller.py')!='68b081487afd8f7572362d33601b276b245150d9bca587aca5bf3b9cace75c10':raise RuntimeError('controller source pin mismatch')
 f=json.loads((R/'manifests/freeze.json').read_text())
 if f.get('source_sha256')!=c.source_hashes():raise RuntimeError('frozen source set differs from live controller view')
 return o

def child_identity(child,ticks,script):
 if child is None or child.poll() is not None:return False
 p=Path('/proc')/str(child.pid)
 if not p.exists():return False
 args=(p/'cmdline').read_bytes().decode().split('\0');args=[x for x in args if x]
 return c.start_ticks(child.pid)==ticks and os.getpgid(child.pid)==child.pid and str(script) in args and args[0]==str(ROOT/'venv/bin/python')

def stop_child(child,ticks,script):
 if child is None or child.poll() is not None:return
 if not child_identity(child,ticks,script):raise RuntimeError('child identity uncertain; preserve hold')
 os.killpg(child.pid,signal.SIGTERM)
 try:child.wait(timeout=TERM_GRACE_SECONDS)
 except subprocess.TimeoutExpired:
  if not child_identity(child,ticks,script):raise RuntimeError('cannot reverify child before KILL; preserve hold')
  os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--baseline-sha256',required=True)
 ap.add_argument('--operation-id',required=True,help='unique safe name; must not already exist')
 ap.add_argument('--batch-policy',choices=tuple(BATCH_POLICIES),default='initial')
 ap.add_argument('--storage-codec-policy',choices=('reversible-xz-v1',))
 ap.add_argument('--archive-io-profile',choices=(ARCHIVE_IO_PROFILE,))
 a=ap.parse_args()
 policy=resolve_batch_policy(a.batch_policy,a.storage_codec_policy,a.archive_io_profile)
 verify_storage_source_pins()
 if '/' in a.operation_id or '..' in a.operation_id or not a.operation_id.replace('_','').replace('-','').isalnum():raise ValueError('operation id must be a simple unique token')
 runs=D/'runs';runs.mkdir(exist_ok=True)
 op=runs/a.operation_id;op.mkdir(exist_ok=False)
 lock=open(D/'batch-wrapper.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 child=None;ticks=None;hold=False;launched=False;accepted_success=False;nonce=os.urandom(16).hex()
 try:
  owner=verify_controller()
  H.parent.mkdir(parents=True,exist_ok=True)
  fd=os.open(H,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:
   json.dump({'owner_operation':'rf_cold_batch_wrapper_20261026','nonce':nonce,'operation_id':a.operation_id,'created_utc':now(),'reason':'one-shot bounded cold-model archive batch; pause new admissions only','batch_policy':a.batch_policy},f);f.flush();os.fsync(f.fileno())
  hold=True;time.sleep(6)
  deadline=time.monotonic()+3600;admission=None
  while time.monotonic()<deadline:
   verify_controller();ts=records();running=[t for t in ts if t.get('status')=='running']
   unresolved=[t.get('key') for t in running if not c.alive(t.get('pid'),t.get('process_start_ticks'))]
   avail,credit,peaks=c.bracketed_worker_memory(running)
   commitments=[(10*1024**3,0) if t.get('key') in unresolved else (c.promoted_reservation_bytes(t,p),cr) for t,p,cr in zip(running,peaks,credit)]
   admission={'observed_utc':now(),'available_bytes':avail,'running_task_count':len(running),'unresolved_running_task_count':len(unresolved),'worker_commitments_bytes':commitments,'helper_reservation_bytes':int(1.5*1024**3),'policy_host_reserve_bytes':6*1024**3,'policy_growth_margin_bytes':2*1024**3,'batch_policy':a.batch_policy,'storage_codec_policy':a.storage_codec_policy,'batch_max_bytes':policy['max_bytes'],'batch_max_inode_groups':policy['max_groups'],'batch_packing':policy['packing'],'child_wall_limit_seconds':policy['wall_seconds'],**({'archive_io_profile':a.archive_io_profile} if a.archive_io_profile else {})}
   if not unresolved and admission_ready(unresolved,avail,commitments,int(1.5*1024**3)):break
   atomic(op/'supervisor_state.json',{'status':'waiting_for_resource_headroom','admission':admission});time.sleep(10)
  else:raise RuntimeError('resource admission unavailable within one hour; no archive mutation')
  atomic(op/'private_admission.json',admission)
  env=os.environ.copy()
  for n in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:env[n]='1'
  script=D/'source'/'commit_batch_child.py'
  child_argv=[str(ROOT/'venv/bin/python'),str(script),'--operation-dir',str(op),'--baseline-sha256',a.baseline_sha256,'--operation-id',a.operation_id,'--hold-nonce',nonce,'--batch-policy',a.batch_policy]
  child_argv.extend(codec_policy_args(a.storage_codec_policy))
  child_argv.extend(archive_io_profile_args(a.archive_io_profile))
  with (op/'child.log').open('xb') as log:
   child=subprocess.Popen(child_argv,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda: __import__('resource').setrlimit(__import__('resource').RLIMIT_AS,(CHILD_ADDRESS_SPACE_BYTES,CHILD_ADDRESS_SPACE_BYTES)))
   launched=True;ticks=c.start_ticks(child.pid);start=time.monotonic();peak=0;reason=None
   atomic(op/'private_child_identity.json',{'pid':child.pid,'process_start_ticks':ticks,'pgid':os.getpgid(child.pid),'script':str(script),'started_utc':now(),'address_space_limit_bytes':CHILD_ADDRESS_SPACE_BYTES,'private':True})
   while child.poll() is None:
    rss,_=c.tree_rss(child.pid,c.process_table());peak=max(peak,rss)
    if rss>CHILD_AGGREGATE_RSS_BYTES:reason='child aggregate RSS exceeded 1 GiB'
    elif time.monotonic()-start>policy['wall_seconds']:reason=f"child wall limit exceeded {policy['wall_seconds']} seconds"
    elif c.memory_available()<8*1024**3:reason='host MemAvailable below 8 GiB'
    if reason:stop_child(child,ticks,script);break
    time.sleep(.5)
   result={'status':'successful' if child.returncode==0 else 'operationally_interrupted_requires_journal_review','finished_utc':now(),'returncode':child.returncode,'reason':reason,'elapsed_seconds':round(time.monotonic()-start,2),'peak_child_tree_rss_bytes':peak,'scientific_fits_started':0,'hold_nonce':nonce,'operation_id':a.operation_id,'batch_policy':a.batch_policy,'storage_codec_policy':a.storage_codec_policy,'batch_max_bytes':policy['max_bytes'],'batch_max_inode_groups':policy['max_groups'],'batch_packing':policy['packing'],'child_wall_limit_seconds':policy['wall_seconds'],**({'archive_io_profile':a.archive_io_profile} if a.archive_io_profile else {})}
   atomic(op/'supervisor_result.json',result)
   if child.returncode!=0:raise RuntimeError('batch child incomplete; hold is preserved for journal review')
   # Child success is only accepted with its own public receipt and matching successful status.
   child_result=json.loads((op/'child_result.json').read_text())
   if child_result.get('schema')!='lamost-rf-cold-batch/1' or child_result.get('operation_id')!=a.operation_id or child_result.get('baseline_archive_sha256')!=a.baseline_sha256.lower() or child_result.get('batch_policy')!=a.batch_policy or child_result.get('storage_codec_policy')!=a.storage_codec_policy or child_result.get('batch_max_bytes')!=policy['max_bytes'] or child_result.get('batch_max_inode_groups')!=policy['max_groups'] or child_result.get('child_wall_limit_seconds')!=policy['wall_seconds'] or child_result.get('archive_io_profile')!=a.archive_io_profile:
    raise RuntimeError('child receipt identity/baseline mismatch; preserve admission hold')
   child_elapsed=child_result.get('child_elapsed_seconds')
   if not isinstance(child_elapsed,(int,float)) or child_elapsed<0 or child_elapsed>policy['wall_seconds']:
    raise RuntimeError('child elapsed-time receipt is invalid; preserve admission hold')
   if child.returncode==0 and abs(float(child_elapsed)-float(result['elapsed_seconds']))>2.0:
    raise RuntimeError('child/supervisor elapsed-time receipts disagree; preserve admission hold')

   if child_result.get('status')=='committed_and_resolved':
    if child_result.get('archive_mutated') is not True or child_result.get('zip_crc_verified') is not True or not child_result.get('transaction_id') or len(child_result.get('archive_sha256_after',''))!=64:
     raise RuntimeError('child commit receipt is incomplete; preserve admission hold')
    ev=child_result.get('storage_evidence')
    if not isinstance(ev,dict) or ev.get('codec_policy')!=a.storage_codec_policy or ev.get('model_count')!=child_result.get('batch',{}).get('candidate_count') or ev.get('logical_source_bytes')!=child_result.get('batch',{}).get('source_bytes') or ev.get('archive_bytes_delta',0)<ev.get('physical_payload_bytes',0):
     raise RuntimeError('child logical/physical storage evidence is incomplete; preserve admission hold')
    if a.storage_codec_policy and ev.get('encoded_model_count',0)+ev.get('raw_fallback_count',0)!=ev.get('model_count'):
     raise RuntimeError('codec policy payload accounting is incomplete; preserve admission hold')
   elif child_result.get('status')=='no_eligible_candidates':
    if child_result.get('archive_mutated') is not False or child_result.get('model_paths_removed') is not False or child_result.get('archive_sha256_after') is not None or child_result.get('storage_codec_policy')!=a.storage_codec_policy or child_result.get('storage_evidence',{}).get('codec_policy')!=a.storage_codec_policy or child_result.get('storage_evidence',{}).get('model_count')!=0:
     raise RuntimeError('empty-batch receipt is inconsistent; preserve admission hold')
   else: raise RuntimeError('child result lacks a successful terminal state')
   accepted_success=True
   print(json.dumps(result),flush=True)
 except BaseException as e:
  atomic(op/'supervisor_exception.json',{'observed_utc':now(),'error_type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
  raise
 finally:
  if child is not None and child.poll() is None:
   try:stop_child(child,ticks,D/'source'/'commit_batch_child.py')
   except BaseException as e:atomic(op/'cleanup_unverified.json',{'observed_utc':now(),'error':str(e),'hold_preserved':True})
  # Never clear hold after an ambiguous child outcome; explicit journal review is required.
  if hold and (not launched or accepted_success):
   try:
    if json.loads(H.read_text()).get('nonce')==nonce:H.unlink()
   except FileNotFoundError:pass
if __name__=='__main__':main()







