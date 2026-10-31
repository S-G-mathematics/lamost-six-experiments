from __future__ import annotations
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'
GIB=1024**3
HELPER_RESERVATION= int(1.5*GIB)
STORAGE_TRIGGER_HEADROOM=2*GIB
OBSERVATION_MAX_AGE=300
ARCHIVE_TRANSACTION_COOLDOWN_SECONDS=360
MAX_FAILURES_PER_HOUR=3
MAX_BATCH_WALL=600
MAX_WRAPPER_WALL=660
ARCHIVE_IO_PROFILE='bounded-1800'
RAW_WIDE_PROFILE='bounded-1800-wide8gib'
RAW_MIXED_SMALL_PROFILE='bounded-1800-mixedsmall4gib2048'
CODEC_MULTIGROUP_PROFILE='bounded-1800-codec1gib64'
CODEC_MULTIGROUP_MAX_BYTES=1*GIB
CODEC_MULTIGROUP_MAX_GROUPS=64
CODEC_MULTIGROUP_TEMP_MAX_BYTES=4*GIB
CODEC_MULTIGROUP_TRANSIENT_DISK_RESERVE_BYTES=10*GIB
CODEC_LARGE_TRANSIENT_DISK_RESERVE_BYTES=14*GIB
CODEC_MULTIGROUP_DISK_MARGIN_BYTES=2*GIB
CODEC_LARGE_PROFILE='bounded-5400-codec4gib64'
CODEC_LARGE_MAX_BYTES=4*GIB
CODEC_LARGE_MAX_GROUPS=64
CODEC_LARGE_TEMP_MAX_BYTES=8*GIB
CODEC_LARGE_WALL_SECONDS=5400
CODEC_LARGE_WRAPPER_WALL_SECONDS=5460
CODEC_PAYLOAD12_PROFILE='bounded-5400-codec4gib64-payload12'
CODEC_PAYLOAD12_NARROW_PROFILE='bounded-5400-codec1gib64-payload12'
CODEC_PAYLOAD12_POLICY='reversible-xz-v1-payload12'
CODEC_PAYLOAD12_MAX_BYTES=CODEC_LARGE_MAX_BYTES
CODEC_PAYLOAD12_NARROW_MAX_BYTES=1*GIB
CODEC_PAYLOAD12_MAX_PAYLOAD_BYTES=12*GIB
CODEC_PAYLOAD12_MAX_GROUPS=CODEC_LARGE_MAX_GROUPS
CODEC_PAYLOAD12_NARROW_MAX_GROUPS=64
CODEC_PAYLOAD12_TEMP_MAX_BYTES=CODEC_LARGE_TEMP_MAX_BYTES
CODEC_PAYLOAD12_NARROW_TEMP_MAX_BYTES=CODEC_LARGE_TEMP_MAX_BYTES
CODEC_PAYLOAD12_WALL_SECONDS=CODEC_LARGE_WALL_SECONDS
CODEC_PAYLOAD12_NARROW_WALL_SECONDS=CODEC_LARGE_WALL_SECONDS
CODEC_ARCHIVE_IO_PROFILES=(CODEC_MULTIGROUP_PROFILE,CODEC_LARGE_PROFILE,CODEC_PAYLOAD12_PROFILE,CODEC_PAYLOAD12_NARROW_PROFILE)
ARCHIVE_IO_PROFILES=(ARCHIVE_IO_PROFILE,RAW_WIDE_PROFILE,RAW_MIXED_SMALL_PROFILE,*CODEC_ARCHIVE_IO_PROFILES)
RAW_WIDE_MAX_BYTES=8*GIB
RAW_WIDE_MAX_GROUPS=64
RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES=6*GIB
RAW_MIXED_SMALL_MAX_BYTES=4*GIB
RAW_MIXED_SMALL_MAX_GROUPS=2048
RAW_MIXED_SMALL_TRANSIENT_DISK_RESERVE_BYTES=6*GIB
RAW_ARCHIVE_IO_PROFILES=(RAW_WIDE_PROFILE,RAW_MIXED_SMALL_PROFILE)
STORAGE_ARCHIVE_IO_PROFILES=RAW_ARCHIVE_IO_PROFILES+CODEC_ARCHIVE_IO_PROFILES
ARCHIVE_IO_WALL_SECONDS=1800
ARCHIVE_IO_WRAPPER_WALL_SECONDS=1860
WRAPPER_RSS_LIMIT=1536*1024**2
WRAPPER_AS_LIMIT=1536*1024**2
TERM_GRACE=30
EXPECTED_INSTANCE='i-095641a281a4038b9'
PINS={'controller.py': 'd09f18c367a0e51dead494a09e07b529673e41d1fdc615665d3fc49c83e0070a',
 'cold_model_storage.py': '48fb2a2c52acdeb0a15fe36419676dbadc99d0ebdb46a3121e527471ffc45c57',
 'cold_codec_storage.py': '424e3df9e48029a30e3efbb437a314e94fda126f3835910194a25e94d6602430',
 'reversible_joblib_codec.py': 'f2d9653ce093cf65ae6268734b73e91504c519f6b7b2bdc0bcc551a21296256c',
 'admission_evidence.py': 'f2369fb24c39dde7241f12f6cb7831358168897a76810809d3f72cc351dc86b9',
 'run_batch.py': '01f9e306e59749eba98654346144280ba91b724a9b170d6396ba80f2d2258d5e',
 'commit_batch_child.py': '607ed83ac7acc4a9490fb7e094871ef81c97f449897db0c2bf5c80f0f92798cf',
 'batch_plan.py': '653ae3ff46e433ce102939e1a635f2a9374f8387b4e59abfc7681d5243dbe0f5',
 'cold_storage_safety.py': '7dff7f8dc256f8252d41b6fd370b7624bfe8841fa7c5c13dbe86747ccc456273',
 'archive_fit_admission.py': '93ce1cc5948d451dfbc0a6b397561a62a76992a3ca2c9e5e3300a8758e14d3b9',
 'metadata_only_contract.py': '1d4e9f78bf3b0062effb3bc218fb5135aae0dba2375b2602773d21bf49d333a1',
 'metadata_access_contract_v2.py': '3cf04ce36ba65b70b5ee68bf82aecf18ae405948c3cc36b5a7c678439b6d5bf8'}
PRIVATE=R/'logs/private/cold_auto_compaction'
PUBLIC=R/'reports/engineering_audits/cold_auto_compaction'
JOURNALS=R/'journals/cold_model_store'
ARCHIVE=ROOT/'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip'
MANIFEST=R/'manifests/cold_model_store_manifest.json'
DRIVER_LOCK=R/'locks/cold_auto_compaction.lock'
BATCH_LOCK=R/'batch-wrapper.lock'
HOLD=R/'ADMISSION_HOLD.json'

def sha256_file(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def atomic_json(path,obj,mode=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
 with tmp.open('w',encoding='utf-8') as f:
  json.dump(obj,f,sort_keys=True,indent=2,default=str);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
 if mode is not None:os.chmod(path,mode)

def parse_utc(value):
 if not isinstance(value,str):raise ValueError('timestamp is not text')
 d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('timestamp lacks timezone')
 return d.timestamp()

def _working_reserve_observation_valid(doc,policy,runtime_root,approved_campaign,restore_budget):
 if not isinstance(policy,dict) or policy.get('policy_id')!='working-reserve-6gib-one-fit-v1':return False
 expected={'working_reserve_bytes':6*(1<<30),'maximum_restore_bytes':10*(1<<30),
           'maximum_single_restore_asset_bytes':1<<30,'per_active_or_new_task_output_reserve_bytes':2<<30,
           'maximum_concurrent_fit_tasks':1,
           'full_archive_verification':'finalization_only','restore_index_schema':'lamost-terminal-result-retention-index/2'}
 if any(policy.get(k)!=v for k,v in expected.items()):return False
 try:
  if (doc.get('policy_id')!=policy['policy_id'] or doc.get('working_reserve_bytes')!=policy['working_reserve_bytes']
      or doc.get('full_archive_verification')!=policy['full_archive_verification']
      or doc.get('active_running_task_count')!=0 or doc.get('restore_required') is not True
      or doc.get('retention_index_matches_approved_campaign') is not True
      or doc.get('no_unique_artifacts_deleted') is not True):return False
  vals=['free_bytes','required_free_bytes','restore_bytes_reserved','largest_restore_asset_bytes_reserved',
        'per_active_or_new_task_output_reserve_bytes']
  if any(type(doc.get(k)) is not int or doc[k]<0 for k in vals):return False
  if doc['restore_bytes_reserved']<=0 or doc['restore_bytes_reserved']>policy['maximum_restore_bytes']:return False
  if doc['largest_restore_asset_bytes_reserved']<=0 or doc['largest_restore_asset_bytes_reserved']>policy['maximum_single_restore_asset_bytes']:return False
  if doc['per_active_or_new_task_output_reserve_bytes']!=policy['per_active_or_new_task_output_reserve_bytes']:return False
  expected_required=policy['working_reserve_bytes']+doc['restore_bytes_reserved']+doc['largest_restore_asset_bytes_reserved']+policy['per_active_or_new_task_output_reserve_bytes']
  if doc['required_free_bytes']!=expected_required:return False
  if type(doc.get('admission_allowed')) is not bool or doc['admission_allowed']!=(doc['free_bytes']>=expected_required):return False
  rel=Path(policy['restore_index_rel'])
  if rel.is_absolute() or '..' in rel.parts or policy.get('restore_index_schema')!='lamost-terminal-result-retention-index/2':return False
  root=Path(runtime_root).resolve();index=(root/rel).resolve()
  if root not in index.parents or Path(doc.get('retention_index_path','')).resolve()!=index:return False
  if not isinstance(approved_campaign,dict) or approved_campaign.get('policy_id')!=policy['policy_id']:return False
  expected={'index_sha256':approved_campaign.get('retention_index_sha256'),
            'row_count':approved_campaign.get('retention_row_count'),
            'restore_bytes':approved_campaign.get('retention_restore_bytes'),
            'largest_asset_bytes':approved_campaign.get('largest_restore_asset_bytes'),
            'restore_required':approved_campaign.get('retention_restore_required')}
  if any(v is None for v in expected.values()) or expected['restore_required'] is not True:return False
  if restore_budget!=expected:return False
  if (doc.get('retention_index_sha256')!=expected['index_sha256']
      or doc['restore_bytes_reserved']!=expected['restore_bytes']
      or doc['largest_restore_asset_bytes_reserved']!=expected['largest_asset_bytes']):return False
  return True
 except Exception:return False

def should_trigger_storage(observation,free_bytes,now_epoch,*,max_age=OBSERVATION_MAX_AGE,headroom=STORAGE_TRIGGER_HEADROOM,storage_policy=None,archive_io_profile=None,runtime_root=None,approved_campaign=None,restore_budget=None):
 if not isinstance(observation,dict):return False,'storage_observation_missing'
 try:age=float(now_epoch)-parse_utc(observation['observed_utc'])
 except Exception:return False,'storage_observation_invalid'
 if age<0:return False,'storage_observation_from_future'
 if age>max_age:return False,'storage_observation_stale'
 if archive_io_profile==CODEC_PAYLOAD12_NARROW_PROFILE:
  if (observation.get('policy_id')!='working-reserve-6gib-one-fit-v1'
      or not _working_reserve_observation_valid(observation,storage_policy,runtime_root or ROOT,approved_campaign,restore_budget)):
   return False,'storage_observation_invalid'
  minimum=int(observation['required_free_bytes'])
 else:
  if 'policy_id' in observation:return False,'storage_observation_invalid'
  try:minimum=int(observation['minimum_free_bytes'])
  except Exception:return False,'storage_observation_invalid'
 gap=int(free_bytes)-minimum
 if gap<0:return True,'storage_below_controller_minimum'
 if gap<headroom:return True,'storage_headroom_below_trigger'
 return False,'storage_headroom_sufficient'

def preflight_decision(*,storage_trigger,observation_fresh,queue_complete,finalizer_busy,
                       admission_hold,pending_journal,batch_busy,reader_busy,
                       driver_lock_acquired,running_verified,resource_admission_ok,
                       source_io_ok,baseline_ok,failures_last_hour):
 if not driver_lock_acquired:return 'backoff','driver_lock_busy'
 if queue_complete:return 'exit','scientific_queue_terminal'
 if finalizer_busy:return 'backoff','finalizer_owns_archive'
 if not source_io_ok:return 'backoff','source_or_manifest_io_unavailable'
 if not baseline_ok:return 'backoff','archive_manifest_journal_identity_mismatch'
 if pending_journal:return 'backoff','pending_cold_transaction_requires_review'
 if admission_hold:return 'backoff','admission_hold_present'
 if batch_busy:return 'backoff','manual_or_other_batch_active'
 if reader_busy:return 'backoff','cold_store_lease_busy'
 if not observation_fresh:return 'backoff','storage_observation_unavailable_or_stale'
 if not storage_trigger:return 'idle','storage_headroom_sufficient'
 if not running_verified:return 'backoff','running_process_identity_unresolved'
 if not resource_admission_ok:return 'backoff','helper_memory_admission_denied'
 if failures_last_hour>=MAX_FAILURES_PER_HOUR:return 'review_required','three_failed_operations_in_last_hour'
 return 'run','storage_triggered_and_preflight_passed'

def file_lock_probe(path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a+') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return False
  finally:
   try:fcntl.flock(f,fcntl.LOCK_UN)
   except Exception:pass
 return True

def acquire_driver_lock(path=DRIVER_LOCK):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);f=path.open('a+')
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:f.close();return None
 return f

def load_controller():
 if str(R/'source') not in sys.path:sys.path.insert(0,str(R/'source'))
 import controller
 return controller

def verify_instance():
 tag=Path('/sys/devices/virtual/dmi/id/board_asset_tag').read_text().strip()
 if EXPECTED_INSTANCE not in tag:raise RuntimeError('EC2 identity mismatch')
 return tag

def verify_source_set(c):
 for name,digest in PINS.items():
  if sha256_file(R/'source'/name)!=digest:raise RuntimeError('pinned source mismatch: '+name)
 freeze=json.loads((R/'manifests/freeze.json').read_text())
 if freeze.get('source_sha256')!=c.source_hashes():raise RuntimeError('live source set differs from frozen controller source set')
 return freeze

def proc_cmd(pid,proc_root=Path('/proc')):
 try:
  raw=(Path(proc_root)/str(pid)/'cmdline').read_bytes().decode(errors='replace')
  return [x for x in raw.split('\0') if x]
 except Exception:return []

def process_start_ticks(pid,proc_root=Path('/proc')):
 try:return (Path(proc_root)/str(pid)/'stat').read_text().rpartition(')')[2].split()[19]
 except Exception:return None

def process_is_exact(pid,ticks,script,*,python_path=None,pgid=None,proc_root=Path('/proc')):
 if process_start_ticks(pid,proc_root)!=str(ticks):return False
 args=proc_cmd(pid,proc_root)
 if not args or str(Path(script)) not in args:return False
 if python_path and args[0]!=str(python_path):return False
 try:
  if pgid is not None and os.getpgid(int(pid))!=int(pgid):return False
 except Exception:return False
 return True

def actual_interpreter_script(args):
 if not args:return None
 exe=Path(args[0]).name
 if exe in {'python','python3','python3.12'}:
  i=1
  if i<len(args) and args[i]=='-u':i+=1
  if i>=len(args) or args[i] in {'-c','-m'} or args[i].startswith('-'):return None
  return args[i]
 if exe in {'bash','bash5'}:
  i=1
  while i<len(args):
   arg=args[i]
   if arg=='--':return args[i+1] if i+1<len(args) else None
   if arg in {'-c','--command'} or (arg.startswith('-') and 'c' in arg[1:]):return None
   if arg in {'-o','--rcfile','--init-file'}:
    i+=2;continue
   if arg.startswith('-'):
    i+=1;continue
   return arg
 return None

def _absolute_script_argument(pid,arg,proc_root):
 if not arg:return None
 path=Path(arg)
 if not path.is_absolute():
  try:cwd=Path(os.readlink(Path(proc_root)/str(pid)/'cwd'))
  except OSError:return None
  path=cwd/path
 try:return path.resolve(strict=False)
 except OSError:return None

def scan_busy_scripts(proc_root=Path('/proc'),runtime_root=R):
 runtime=Path(runtime_root).resolve(strict=False)
 targets={
  (runtime/'source'/'run_batch.py').resolve(strict=False):'run_batch.py',
  (runtime/'source'/'commit_batch_child.py').resolve(strict=False):'commit_batch_child.py',
  (runtime/'run_finalizer.sh').resolve(strict=False):'run_finalizer.sh',
  (runtime/'source'/'finalize_project.py').resolve(strict=False):'finalize_project.py',
 }
 found=[]
 try:entries=list(Path(proc_root).iterdir())
 except Exception:return ['proc_inventory_unavailable']
 for ent in entries:
  if not ent.name.isdigit():continue
  args=proc_cmd(ent.name,proc_root);script=actual_interpreter_script(args)
  if script is None:continue
  path=_absolute_script_argument(ent.name,script,proc_root)
  target=targets.get(path)
  if target:found.append((int(ent.name),target,args))
 return found

def verify_controller_owner(c):
 owner=json.loads((R/'owner.json').read_text());pid=int(owner['pid'])
 if c.start_ticks(pid)!=str(owner.get('process_start_ticks')):raise RuntimeError('controller owner PID ticks mismatch')
 if owner.get('instance_id')!=EXPECTED_INSTANCE:raise RuntimeError('controller owner instance mismatch')
 args=proc_cmd(pid)
 if args[:2]!=[str(ROOT/'venv/bin/python'),'-u']:raise RuntimeError('unexpected controller argv')
 if len(args)<3 or (Path(os.readlink(f'/proc/{pid}/cwd'))/args[2]).resolve()!=(R/'source/controller.py').resolve():raise RuntimeError('controller source/cwd identity mismatch')
 if sha256_file(R/'source/controller.py')!=PINS['controller.py']:raise RuntimeError('controller code SHA mismatch')
 return owner

def records_readonly(db_path=R/'registry.sqlite'):
 db=sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True,isolation_level=None)
 db.execute('PRAGMA query_only=ON')
 db.execute('BEGIN')
 try:
  row=db.execute("SELECT COUNT(*), SUM(CASE WHEN COALESCE(json_extract(record,'$.status'),'')!='validated_terminal' THEN 1 ELSE 0 END) FROM tasks").fetchone()
  total=int(row[0] or 0);nonterminal=int(row[1] or 0)
  running=[json.loads(x[0]) for x in db.execute("SELECT record FROM tasks WHERE json_extract(record,'$.status')='running'")]
  meta=dict(db.execute('select key,value from meta'))
  db.execute('COMMIT')
 except BaseException:
  db.execute('ROLLBACK');db.close();raise
 db.close()
 return {x['key']:x for x in running},{**meta,'task_count':total,'nonterminal_count':nonterminal,'running_count':len(running)}

def registry_complete(meta):
 return int(meta.get('task_count',0))>0 and int(meta.get('nonterminal_count',1))==0

def journal_requires_review(doc):
 return doc.get('state') not in {'complete','rolled_back'}

def pending_journal():
 states=[]
 for path in JOURNALS.glob('*/journal.json'):
  try:
   doc=json.loads(path.read_text())
   if journal_requires_review(doc):states.append({'path':str(path),'state':doc.get('state')})
  except Exception:states.append({'path':str(path),'state':'unreadable'})
 return states

def validate_archive_chain(doc,journal,archive_stat,approved_relpath='packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip'):
 if doc.get('schema_version')!='lamost-cold-model-store/1':raise RuntimeError('cold manifest schema mismatch')
 rel=Path(doc.get('archive_path',''))
 if rel.is_absolute() or '..' in rel.parts or rel.as_posix()!=approved_relpath:raise RuntimeError('archive manifest path invalid')
 if int(doc.get('archive_bytes',-1))!=int(archive_stat.st_size):raise RuntimeError('archive size differs from current manifest')
 txid=doc.get('transaction_id')
 if not isinstance(txid,str) or len(txid)!=32 or any(c not in '0123456789abcdef' for c in txid):raise RuntimeError('manifest transaction id invalid')
 if journal.get('transaction_id')!=txid or journal.get('state')!='complete':raise RuntimeError('manifest transaction is not the exact completed journal')
 current=doc.get('archive_sha256')
 if current!=journal.get('archive_sha256_after'):raise RuntimeError('manifest SHA does not match its recorded completed transaction')
 if journal.get('archive_bytes_after')!=int(archive_stat.st_size):raise RuntimeError('archive bytes differ from manifest transaction')
 tail=None;prefix=journal.get('archive_prefix_bytes_after');identity=journal.get('archive_identity_after')
 expected=[archive_stat.st_dev,archive_stat.st_ino,archive_stat.st_size,archive_stat.st_mtime_ns,archive_stat.st_ctime_ns]
 prefix_sha=journal.get('archive_prefix_sha256_after')
 if type(prefix) is int and 0<=prefix<=archive_stat.st_size and identity==expected and isinstance(prefix_sha,str) and len(prefix_sha)==64 and all(c in '0123456789abcdef' for c in prefix_sha):
  tail=int(archive_stat.st_size)-prefix
 return {'archive_sha256':current,'archive_bytes':int(archive_stat.st_size),'archive_inode':int(archive_stat.st_ino),'archive_mtime_ns':int(archive_stat.st_mtime_ns),'archive_tail_backup_bytes':tail,'latest_transaction_id':txid,'latest_journal_transaction_id':journal.get('transaction_id'),'latest_journal_state':journal.get('state'),'latest_transaction_completed_utc':journal.get('completed_utc')}

def baseline_identity():
 if pending_journal():raise RuntimeError('pending cold transaction')
 doc=json.loads(MANIFEST.read_text())
 rel=Path(doc.get('archive_path',''))
 if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('archive manifest path invalid')
 archive=(ROOT/rel).resolve()
 if archive!=ARCHIVE.resolve() or archive.is_symlink() or not archive.is_file():raise RuntimeError('archive path is not the approved regular archive')
 txid=doc.get('transaction_id')
 if not isinstance(txid,str) or len(txid)!=32 or any(c not in '0123456789abcdef' for c in txid):raise RuntimeError('manifest transaction id invalid')
 journal_path=JOURNALS/txid/'journal.json'
 if not journal_path.is_file() or journal_path.is_symlink():raise RuntimeError('manifest transaction journal missing or unsafe')
 journal=json.loads(journal_path.read_text())
 if journal_path.parent.name!=txid:raise RuntimeError('journal path does not match manifest transaction')
 base=validate_archive_chain(doc,journal,archive.stat())
 ms=MANIFEST.stat()
 base.update({'manifest_sha256':sha256_file(MANIFEST),'manifest_inode':int(ms.st_ino),'manifest_mtime_ns':int(ms.st_mtime_ns)})
 return base

def archive_transaction_cooldown_reason(baseline,now_epoch,cooldown_seconds=ARCHIVE_TRANSACTION_COOLDOWN_SECONDS):
 txid=baseline.get('latest_transaction_id')
 if (not isinstance(txid,str) or len(txid)!=32 or any(c not in '0123456789abcdef' for c in txid)
     or baseline.get('latest_journal_transaction_id')!=txid or baseline.get('latest_journal_state')!='complete'):
  return 'archive_transaction_identity_invalid'
 completed=baseline.get('latest_transaction_completed_utc')
 if isinstance(completed,bool) or not isinstance(completed,(int,float)) or not math.isfinite(float(completed)):
  return 'archive_transaction_completion_time_invalid'
 if isinstance(now_epoch,bool) or not isinstance(now_epoch,(int,float)) or not math.isfinite(float(now_epoch)):
  return 'current_epoch_invalid'
 age=float(now_epoch)-float(completed)
 if age<0:return 'archive_transaction_completion_time_in_future'
 if age<float(cooldown_seconds):return 'recent_archive_transaction_cooldown'
 return None

def lock_available(path):
 return file_lock_probe(path)

def storage_freshness(observation_path,free_bytes,now_epoch,*,storage_policy=None,archive_io_profile=None,runtime_root=None,approved_campaign=None,restore_budget=None):
 try:doc=json.loads(Path(observation_path).read_text())
 except Exception:return False,False,'storage_observation_missing'
 try:age=float(now_epoch)-parse_utc(doc['observed_utc'])
 except Exception:return False,False,'storage_observation_invalid'
 fresh=0<=age<=OBSERVATION_MAX_AGE
 if not fresh:return False,False,'storage_observation_stale_or_future'
 trig,reason=should_trigger_storage(doc,free_bytes,now_epoch,storage_policy=storage_policy,
                                   archive_io_profile=archive_io_profile,runtime_root=runtime_root,approved_campaign=approved_campaign,restore_budget=restore_budget)
 return True,trig,reason

def failure_count_last_hour(private_dir,now_epoch):
 count=0
 for p in Path(private_dir).glob('*/driver_result.json'):
  try:
   d=json.loads(p.read_text());stamp=parse_utc(d['observed_utc'])
   if 0<=now_epoch-stamp<=3600 and d.get('status') in {'wrapper_failed','wrapper_timeout','helper_rss_limit'}:count+=1
  except Exception:continue
 return count

def running_worker_profile(c,records):
 running=[t for t in records.values() if t.get('status')=='running']
 unresolved=[t.get('key') for t in running if not c.alive(t.get('pid'),t.get('process_start_ticks'))]
 if unresolved:return False,{'running':len(running),'unresolved':unresolved,'available_bytes':c.memory_available(),'commitments':[]}
 avail,credited,peaks=c.bracketed_worker_memory(running)
 commitments=[(c.promoted_reservation_bytes(t,p),cr) for t,p,cr in zip(running,peaks,credited)]
 allowed=c.memory_admission_ok(avail,commitments,HELPER_RESERVATION)
 return allowed,{'running':len(running),'unresolved':[],'available_bytes':avail,'commitments':[[int(a),int(b)] for a,b in commitments],'helper_reservation_bytes':HELPER_RESERVATION}

def finalizer_active(records,proc_rows):
 if registry_complete(records):return True
 return any(target in {'run_finalizer.sh','finalize_project.py'} for _pid,target,_argv in proc_rows)

def process_identity_is_gone(pid,ticks,script,proc_root=Path('/proc')):
 current=process_start_ticks(pid,proc_root)
 if current!=str(ticks):return True
 args=proc_cmd(pid,proc_root)
 return False

def child_process_gone(op):
 identity=json.loads((Path(op)/'private_child_identity.json').read_text())
 pid=int(identity['pid']);ticks=str(identity['process_start_ticks'])
 script=R/'source/commit_batch_child.py'
 if Path(identity.get('script','')).resolve()!=script.resolve() or int(identity.get('pgid',-1))!=pid:return False
 return process_identity_is_gone(pid,ticks,script)

def _preexec_address_limit():
 resource.setrlimit(resource.RLIMIT_AS,(WRAPPER_AS_LIMIT,WRAPPER_AS_LIMIT))

def _wrapper_identity(proc):
 return process_is_exact(proc.pid,proc._lamost_ticks, R/'source/run_batch.py',python_path=ROOT/'venv/bin/python',pgid=proc.pid)

def _signal_wrapper(proc,sig):
 if not _wrapper_identity(proc):raise RuntimeError('wrapper identity uncertain; do not signal')
 os.kill(proc.pid,sig)

def launch_permitted(preflight_only):
 return not bool(preflight_only)

CODEC_POLICY='reversible-xz-v1'
CODEC_BATCH_MAX_BYTES=1<<30
CODEC_BATCH_MAX_GROUPS=1
def codec_policy_args(storage_codec_policy):
 return [] if storage_codec_policy is None else ['--storage-codec-policy',storage_codec_policy]
def outer_wrapper_wall_seconds(archive_io_profile=None):
 if archive_io_profile is None:return MAX_WRAPPER_WALL
 if archive_io_profile not in ARCHIVE_IO_PROFILES:raise ValueError('unknown archive I/O profile')
 if archive_io_profile in (CODEC_LARGE_PROFILE,CODEC_PAYLOAD12_PROFILE,CODEC_PAYLOAD12_NARROW_PROFILE):return CODEC_LARGE_WRAPPER_WALL_SECONDS
 return ARCHIVE_IO_WRAPPER_WALL_SECONDS

def archive_io_profile_args(profile):
 if profile is None:return []
 if profile not in ARCHIVE_IO_PROFILES:raise ValueError('unknown archive I/O profile')
 return ['--archive-io-profile',profile]

def batch_config(storage_codec_policy,archive_io_profile=None):
 if storage_codec_policy not in (None,CODEC_POLICY,CODEC_PAYLOAD12_POLICY):raise ValueError('unknown storage codec policy')
 if archive_io_profile not in (None,*ARCHIVE_IO_PROFILES):raise ValueError('unknown archive I/O profile')
 if storage_codec_policy==CODEC_PAYLOAD12_POLICY and archive_io_profile not in (CODEC_PAYLOAD12_PROFILE,CODEC_PAYLOAD12_NARROW_PROFILE):raise ValueError('payload12 policy requires its dedicated archive profile')
 if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES:
  payload12=archive_io_profile in (CODEC_PAYLOAD12_PROFILE,CODEC_PAYLOAD12_NARROW_PROFILE)
  expected_policy=CODEC_PAYLOAD12_POLICY if payload12 else CODEC_POLICY
  if storage_codec_policy!=expected_policy:raise ValueError('codec profile/storage policy mismatch')
  large=archive_io_profile in (CODEC_LARGE_PROFILE,CODEC_PAYLOAD12_PROFILE)
  narrow=archive_io_profile==CODEC_PAYLOAD12_NARROW_PROFILE
  return {'batch_policy':'storage-followup-codec','max_bytes':CODEC_PAYLOAD12_NARROW_MAX_BYTES if narrow else (CODEC_LARGE_MAX_BYTES if large else CODEC_MULTIGROUP_MAX_BYTES),'max_groups':CODEC_PAYLOAD12_NARROW_MAX_GROUPS if narrow else (CODEC_LARGE_MAX_GROUPS if large else CODEC_MULTIGROUP_MAX_GROUPS),'wall_seconds':CODEC_PAYLOAD12_NARROW_WALL_SECONDS if narrow else (CODEC_LARGE_WALL_SECONDS if large else ARCHIVE_IO_WALL_SECONDS),'packing':'largest_first','storage_codec_policy':storage_codec_policy,'max_payload_bytes':(CODEC_PAYLOAD12_MAX_PAYLOAD_BYTES if payload12 else 2*GIB),'transient_disk_reserve_bytes':CODEC_MULTIGROUP_TRANSIENT_DISK_RESERVE_BYTES if narrow or not large else CODEC_LARGE_TRANSIENT_DISK_RESERVE_BYTES,'transient_disk_margin_bytes':CODEC_MULTIGROUP_DISK_MARGIN_BYTES,'codec_temp_budget_bytes':CODEC_PAYLOAD12_NARROW_TEMP_MAX_BYTES if narrow else (CODEC_LARGE_TEMP_MAX_BYTES if large else CODEC_MULTIGROUP_TEMP_MAX_BYTES),'archive_io_profile':archive_io_profile}
 if archive_io_profile and storage_codec_policy is not None:raise ValueError('bounded archive I/O profiles are raw-only')
 wide=archive_io_profile==RAW_WIDE_PROFILE
 mixed_small=archive_io_profile==RAW_MIXED_SMALL_PROFILE
 raw_max_bytes=RAW_WIDE_MAX_BYTES if wide else (RAW_MIXED_SMALL_MAX_BYTES if mixed_small else 2*GIB)
 raw_max_groups=RAW_WIDE_MAX_GROUPS if wide else (RAW_MIXED_SMALL_MAX_GROUPS if mixed_small else 16)
 raw_disk_reserve=RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES if wide else (RAW_MIXED_SMALL_TRANSIENT_DISK_RESERVE_BYTES if mixed_small else 0)
 config={'batch_policy':'storage-followup-codec' if storage_codec_policy else 'storage-followup','max_bytes':CODEC_BATCH_MAX_BYTES if storage_codec_policy else raw_max_bytes,'max_groups':CODEC_BATCH_MAX_GROUPS if storage_codec_policy else raw_max_groups,'wall_seconds':ARCHIVE_IO_WALL_SECONDS if archive_io_profile else MAX_BATCH_WALL,'packing':'largest_first','storage_codec_policy':storage_codec_policy,'transient_disk_reserve_bytes':raw_disk_reserve}
 if archive_io_profile:config['archive_io_profile']=archive_io_profile
 return config
def codec_multigroup_overlap_policy_allowed(c,freeze,profile=CODEC_MULTIGROUP_PROFILE):
 try:
  fn=getattr(getattr(c,'archive_fit_admission',None),'native_codec_overlap_policy_allowed',None)
  if not callable(fn):return False
  policy=CODEC_PAYLOAD12_POLICY if profile in (CODEC_PAYLOAD12_PROFILE,CODEC_PAYLOAD12_NARROW_PROFILE) else CODEC_POLICY
  return fn(R,freeze,archive_io_profile=profile,batch_policy='storage-followup-codec',storage_codec_policy=policy) is True
 except Exception:return False
def wide_overlap_policy_allowed(profile, freeze):
 if profile in CODEC_ARCHIVE_IO_PROFILES:return codec_multigroup_overlap_policy_allowed(load_controller(),freeze,profile)
 if profile not in RAW_ARCHIVE_IO_PROFILES:return True
 return not (freeze.get('archive_native_fit_overlap_sha256') or freeze.get('archive_native_fit_overlap_qualification_sha256'))

def current_storage_observation_epoch():
 # Validate storage telemetry against the time it is read, not the earlier driver start.
 return dt.datetime.now(dt.timezone.utc).timestamp()

def run_once(preflight_only=False,storage_codec_policy=None,archive_io_profile=None):
 config=batch_config(storage_codec_policy,archive_io_profile)
 wrapper_wall_seconds=outer_wrapper_wall_seconds(archive_io_profile)
 started=dt.datetime.now(dt.timezone.utc);now_epoch=started.timestamp();opid='auto_storage_'+started.strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
 lock=acquire_driver_lock()
 if lock is None:return {'status':'backoff','reason':'driver_lock_busy','operation_id':opid}
 lock.__enter__ if False else None
 private_dir=PRIVATE/opid;private_dir.mkdir(parents=True,exist_ok=False,mode=0o700);private_dir.chmod(0o700)
 private={'operation_id':opid,'started_utc':started.isoformat(),'host_instance_id':None,'wrapper_identity':None,'driver_identity':{'pid':os.getpid(),'process_start_ticks':process_start_ticks(os.getpid()),'source_sha256':sha256_file(Path(__file__).resolve())},**({'archive_io_profile':archive_io_profile} if archive_io_profile else {})}
 proc=None;wrapper_ticks=None;hold_nonce=None;result_status='backoff'
 def early(status,reason,**fields):
  nonlocal result_status
  result_status=status;private.update({'status':status,'reason':reason,'decision_utc':dt.datetime.now(dt.timezone.utc).isoformat(),**fields})
  return {'status':status,'reason':reason,'operation_id':opid,'private_receipt_path':str(private_dir/'driver_result.json'),**fields}
 try:
  instance=verify_instance();private['host_instance_id']=instance
  c=load_controller();freeze=verify_source_set(c);owner=verify_controller_owner(c);private['controller_owner']={'pid':int(owner['pid']),'process_start_ticks':str(owner['process_start_ticks']),'instance_id':owner['instance_id'],'source_set_sha256':sha256_file(R/'manifests/freeze.json')}
  if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES:
   if not wide_overlap_policy_allowed(archive_io_profile,freeze):
    return early('backoff','codec_multigroup_overlap_policy_not_qualified')
  elif archive_io_profile==RAW_WIDE_PROFILE:
   if not wide_overlap_policy_allowed(archive_io_profile,freeze):
    raise RuntimeError('wide raw profile refuses any declared archive overlap policy until it explicitly qualifies this profile')
  records,meta=records_readonly()
  if int(meta.get('task_count',0))==0:raise RuntimeError('registry is empty/unavailable')
  if registry_complete(meta):return early('exit','scientific_queue_terminal',task_count=meta['task_count'])
  processes=scan_busy_scripts()
  if processes==['proc_inventory_unavailable']:return early('backoff','process_inventory_unavailable')
  if any(x[1] in {'run_finalizer.sh','finalize_project.py'} for x in processes):return early('backoff','finalizer_owns_archive')
  if (R/'ADMISSION_HOLD.json').exists():return early('backoff','admission_hold_present')
  if pending_journal():return early('backoff','pending_cold_transaction_requires_review')
  if any(x[1] in {'run_batch.py','commit_batch_child.py'} for x in processes):return early('backoff','manual_or_other_batch_active')
  if not lock_available(BATCH_LOCK):return early('backoff','batch_wrapper_lock_busy')
  if not lock_available(R/'locks/cold_model_store.writer.lock') or not lock_available(R/'locks/cold_model_store.readers.lock'):
   return early('backoff','cold_store_reader_or_writer_lease_busy')
  baseline=baseline_identity()
  cooldown_reason=archive_transaction_cooldown_reason(baseline,now_epoch)
  if cooldown_reason:return early('backoff',cooldown_reason)
  free=shutil.disk_usage(R).free
  storage_policy=freeze.get('storage_admission_policy') if archive_io_profile==CODEC_PAYLOAD12_NARROW_PROFILE else None
  storage_campaign=None;restore_budget=None
  if archive_io_profile==CODEC_PAYLOAD12_NARROW_PROFILE:
   storage_campaign=c._storage_expected_campaign(freeze)
   if storage_campaign is None:return early('backoff','working_storage_campaign_policy_unavailable')
   rel=Path(storage_campaign.get('retention_index_path',''))
   if rel.is_absolute() or '..' in rel.parts:return early('backoff','working_storage_index_path_unsafe')
   index_path=(ROOT/rel).resolve()
   if ROOT.resolve() not in index_path.parents:return early('backoff','working_storage_index_path_unsafe')
   restore_budget=c.retention_restore_budget(index_path)
   if not c.retention_budget_matches_policy(restore_budget,storage_campaign):return early('backoff','working_storage_restore_budget_unverified')
  fresh,trigger,storage_reason=storage_freshness(R/'storage_observation.json',free,current_storage_observation_epoch(),
      storage_policy=storage_policy,archive_io_profile=archive_io_profile,runtime_root=ROOT,
      approved_campaign=storage_campaign,restore_budget=restore_budget)
  if not fresh:return early('backoff',storage_reason)
  if not trigger and not preflight_only:return early('idle',storage_reason,free_bytes=free)
  archive_tail_bytes=baseline.get('archive_tail_backup_bytes',0) or 0
  if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES and (type(baseline.get('archive_tail_backup_bytes')) is not int or archive_tail_bytes<0):
   return early('backoff','codec_archive_tail_witness_missing')
  disk_required=config['max_bytes']+config['transient_disk_reserve_bytes']+config.get('transient_disk_margin_bytes',0)+(archive_tail_bytes if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES else 0)
  if config['transient_disk_reserve_bytes'] and not (free>=disk_required):
   return early('backoff','wide_profile_transient_disk_headroom_insufficient',free_bytes=free,required_free_bytes=disk_required,batch_max_bytes=config['max_bytes'],disk_reserve_bytes=config['transient_disk_reserve_bytes'])
  running_ok,resource_doc=running_worker_profile(c,records)
  if resource_doc['unresolved']:return early('backoff','running_process_identity_unresolved',running_count=resource_doc['running'])
  if not running_ok:return early('backoff','helper_memory_admission_denied',available_bytes=resource_doc['available_bytes'])
  if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES and resource_doc['running']!=0:
   return early('backoff','codec_multigroup_waits_for_current_workers_before_new_qualified_overlap',running_count=resource_doc['running'])
  fails=failure_count_last_hour(PRIVATE,now_epoch)
  if fails>=MAX_FAILURES_PER_HOUR:return early('review_required','three_failed_operations_in_last_hour')
  # Revalidate immediately before child launch; never create the global hold ourselves.
  verify_controller_owner(c)
  if (R/'ADMISSION_HOLD.json').exists() or pending_journal():return early('backoff','state_changed_before_wrapper_launch')
  if not lock_available(BATCH_LOCK):return early('backoff','batch_wrapper_lock_raced_preflight')
  baseline=baseline_identity()
  cooldown_reason=archive_transaction_cooldown_reason(baseline,now_epoch)
  if cooldown_reason:return early('backoff',cooldown_reason)
  free=shutil.disk_usage(R).free
  archive_tail_bytes=baseline.get('archive_tail_backup_bytes',0) or 0
  if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES and (type(baseline.get('archive_tail_backup_bytes')) is not int or archive_tail_bytes<0):
   return early('backoff','codec_archive_tail_witness_missing')
  disk_required=config['max_bytes']+config['transient_disk_reserve_bytes']+config.get('transient_disk_margin_bytes',0)+(archive_tail_bytes if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES else 0)
  if config['transient_disk_reserve_bytes'] and not (free>=disk_required):
   return early('backoff','wide_profile_transient_disk_headroom_insufficient_before_wrapper',free_bytes=free,required_free_bytes=disk_required,batch_max_bytes=config['max_bytes'],disk_reserve_bytes=config['transient_disk_reserve_bytes'])
  private['preflight']={'queue_task_count':meta['task_count'],'queue_nonterminal_count':meta['nonterminal_count'],'running_count':meta['running_count'],'storage_free_bytes':free,'storage_trigger_reason':storage_reason,'available_memory_bytes':resource_doc['available_bytes'],'helper_reservation_bytes':HELPER_RESERVATION,'baseline':baseline,'batch_policy':config['batch_policy'],'storage_codec_policy':storage_codec_policy,'batch_max_bytes':config['max_bytes'],'batch_max_inode_groups':config['max_groups'],'transient_disk_reserve_bytes':config['transient_disk_reserve_bytes'],'transient_disk_margin_bytes':config.get('transient_disk_margin_bytes',0),'codec_temp_budget_bytes':config.get('codec_temp_budget_bytes'),'transient_disk_required_bytes':disk_required,'archive_tail_backup_bytes':archive_tail_bytes,**({'archive_io_profile':archive_io_profile} if archive_io_profile else {})}
  if preflight_only:return early('preflight_ready' if trigger else 'idle','all_read_only_preflight_gates_passed' if trigger else 'storage_headroom_sufficient',task_count=meta['task_count'],nonterminal_count=meta['nonterminal_count'],running_count=meta['running_count'],free_bytes=free,available_memory_bytes=resource_doc['available_bytes'],baseline_transaction_id=baseline['latest_transaction_id'])
  env=os.environ.copy()
  for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[name]='1'
  script=R/'source/run_batch.py'
  cmd=[str(ROOT/'venv/bin/python'),str(script),'--baseline-sha256',baseline['archive_sha256'],'--operation-id',opid,'--batch-policy',config['batch_policy']]
  cmd.extend(codec_policy_args(storage_codec_policy))
  cmd.extend(archive_io_profile_args(archive_io_profile))
  run_dir=R/'runs';run_dir.mkdir(exist_ok=True)
  log_path=private_dir/'wrapper.log'
  with log_path.open('xb') as log:
   proc=subprocess.Popen(cmd,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=_preexec_address_limit)
   wrapper_ticks=c.start_ticks(proc.pid);proc._lamost_ticks=wrapper_ticks
   private['wrapper_identity']={'pid':proc.pid,'process_start_ticks':wrapper_ticks,'pgid':os.getpgid(proc.pid),'argv':cmd,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
   atomic_json(private_dir/'private_process_inventory.json',private,0o600)
   child_elapsed=None;stop_reason=None;wrapper_start=time.monotonic();peak=0
   while proc.poll() is None:
    if not _wrapper_identity(proc):raise RuntimeError('wrapper identity lost; preserve admission hold')
    rows=c.process_table();rss,ids=c.tree_rss(proc.pid,rows);peak=max(peak,rss)
    if rss>WRAPPER_RSS_LIMIT:
     stop_reason='wrapper tree RSS exceeded 1.5 GiB';_signal_wrapper(proc,signal.SIGINT);break
    if time.monotonic()-wrapper_start>wrapper_wall_seconds+TERM_GRACE:
     stop_reason='outer wrapper observation limit exceeded';_signal_wrapper(proc,signal.SIGINT);break
    verify_controller_owner(c)
    time.sleep(.5)
   if proc.poll() is None:
    try:proc.wait(timeout=TERM_GRACE+10)
    except subprocess.TimeoutExpired:
     raise RuntimeError('wrapper did not finish SIGINT cleanup; preserve admission hold')
   private['wrapper_finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
   private['wrapper_returncode']=proc.returncode;private['wrapper_peak_tree_rss_bytes']=peak;private['stop_reason']=stop_reason
  op=R/'runs'/opid
  sr=json.loads((op/'supervisor_result.json').read_text())
  child=json.loads((op/'child_result.json').read_text())
  if proc.returncode!=0 or sr.get('status')!='successful' or sr.get('returncode')!=0:result_status='wrapper_failed';raise RuntimeError('batch wrapper failed; leave any admission hold/journal intact')
  if not child_process_gone(op):result_status='wrapper_failed';raise RuntimeError('recorded batch child still appears live; preserve admission hold')
  if child.get('batch_policy')!=config['batch_policy'] or child.get('storage_codec_policy')!=storage_codec_policy or child.get('archive_io_profile')!=archive_io_profile or child.get('batch_max_bytes')!=config['max_bytes'] or child.get('batch_max_inode_groups')!=config['max_groups'] or child.get('transient_disk_reserve_bytes')!=config['transient_disk_reserve_bytes'] or child.get('child_wall_limit_seconds')!=config['wall_seconds']:
   result_status='wrapper_failed';raise RuntimeError('batch receipt policy identity mismatch')
  if archive_io_profile in CODEC_ARCHIVE_IO_PROFILES and (child.get('codec_temp_budget_bytes')!=config['codec_temp_budget_bytes'] or child.get('transient_disk_required_bytes')!=private['preflight']['transient_disk_required_bytes'] or child.get('archive_tail_backup_bytes')!=archive_tail_bytes or child.get('max_payload_bytes',2*GIB)!=config.get('max_payload_bytes',2*GIB)):
   result_status='wrapper_failed';raise RuntimeError('codec multigroup disk/temp receipt mismatch')
  elapsed=child.get('child_elapsed_seconds')
  if not isinstance(elapsed,(int,float)) or elapsed<0 or elapsed>config['wall_seconds']:result_status='wrapper_failed';raise RuntimeError('child actual elapsed receipt invalid')
  if sr.get('batch_policy')!=config['batch_policy'] or sr.get('storage_codec_policy')!=storage_codec_policy or sr.get('archive_io_profile')!=archive_io_profile or sr.get('elapsed_seconds') is None:result_status='wrapper_failed';raise RuntimeError('supervisor receipt policy/time missing')
  if abs(float(elapsed)-float(sr['elapsed_seconds']))>2.0:result_status='wrapper_failed';raise RuntimeError('child/supervisor elapsed receipts disagree')
  if HOLD.exists():result_status='wrapper_failed';raise RuntimeError('admission hold remains after successful wrapper; preserve for review')
  if pending_journal():result_status='wrapper_failed';raise RuntimeError('pending journal remains after wrapper; preserve for review')
  manifest=json.loads(MANIFEST.read_text());st=ARCHIVE.stat()
  if child.get('status')=='committed_and_resolved':
   ev=child.get('storage_evidence')
   if not isinstance(ev,dict) or ev.get('codec_policy')!=storage_codec_policy or ev.get('model_count')!=child.get('batch',{}).get('candidate_count') or ev.get('logical_source_bytes')!=child.get('batch',{}).get('source_bytes') or ev.get('archive_bytes_delta',0)<ev.get('physical_payload_bytes',0):result_status='wrapper_failed';raise RuntimeError('storage logical/physical evidence mismatch')
   if storage_codec_policy and ev.get('encoded_model_count',0)+ev.get('raw_fallback_count',0)!=ev.get('model_count'):result_status='wrapper_failed';raise RuntimeError('codec fallback accounting mismatch')
   if child.get('archive_mutated') is not True or child.get('zip_crc_verified') is not True:result_status='wrapper_failed';raise RuntimeError('child did not verify archive CRC/commit')
   if manifest.get('archive_sha256')!=child.get('archive_sha256_after'):result_status='wrapper_failed';raise RuntimeError('archive manifest SHA differs from child receipt')
   if st.st_size!=manifest.get('archive_bytes'):result_status='wrapper_failed';raise RuntimeError('archive/manifest bytes differ after committed wrapper')
   if child.get('transaction_id')!=manifest.get('transaction_id'):result_status='wrapper_failed';raise RuntimeError('child transaction does not match current manifest')
   tx=json.loads((JOURNALS/child['transaction_id']/'journal.json').read_text())
   if tx.get('state')!='complete' or tx.get('archive_sha256_before')!=baseline['archive_sha256'] or tx.get('archive_sha256_after')!=child.get('archive_sha256_after'):
    result_status='wrapper_failed';raise RuntimeError('committed transaction provenance mismatch')
  elif child.get('status')=='no_eligible_candidates':
   if child.get('archive_mutated') is not False or child.get('model_paths_removed') is not False or child.get('storage_evidence',{}).get('codec_policy')!=storage_codec_policy or child.get('storage_evidence',{}).get('model_count')!=0:
    result_status='wrapper_failed';raise RuntimeError('no-candidate receipt inconsistent')
   after=baseline_identity()
   if (after['archive_sha256']!=baseline['archive_sha256'] or after['archive_bytes']!=baseline['archive_bytes'] or
       after['archive_inode']!=baseline['archive_inode'] or after['archive_mtime_ns']!=baseline['archive_mtime_ns'] or
       sha256_file(MANIFEST)!=baseline['manifest_sha256']):
    result_status='wrapper_failed';raise RuntimeError('archive or manifest changed during no-op child')
  else:result_status='wrapper_failed';raise RuntimeError('unrecognized child terminal state')
  finished=dt.datetime.now(dt.timezone.utc)
  safe={'schema':'lamost-cold-auto-compaction/1','operation_id':opid,'observed_utc':finished.isoformat(),'status':child.get('status'),'batch_policy':config['batch_policy'],'storage_codec_policy':storage_codec_policy,'batch_max_bytes':config['max_bytes'],'batch_max_inode_groups':config['max_groups'],'transient_disk_reserve_bytes':config['transient_disk_reserve_bytes'],'transient_disk_margin_bytes':config.get('transient_disk_margin_bytes',0),'codec_temp_budget_bytes':config.get('codec_temp_budget_bytes'),'max_payload_bytes':config.get('max_payload_bytes',2*GIB),'transient_disk_required_bytes':private['preflight']['transient_disk_required_bytes'],'archive_tail_backup_bytes':archive_tail_bytes,'packing':child.get('batch_packing'),'child_wall_limit_seconds':config['wall_seconds'],**({'archive_io_profile':archive_io_profile} if archive_io_profile else {}),'child_elapsed_seconds':elapsed,'supervisor_elapsed_seconds':sr.get('elapsed_seconds'),'peak_wrapper_tree_rss_bytes':peak,'models_in_batch':child.get('batch',{}).get('candidate_count'),'batch_source_bytes':child.get('batch',{}).get('source_bytes'),'storage_evidence':child.get('storage_evidence'),'transaction_id':child.get('transaction_id'),'archive_sha256_before':baseline['archive_sha256'],'archive_sha256_after':child.get('archive_sha256_after'),'archive_bytes_after':child.get('archive_bytes_after'),'zip_crc_verified':child.get('zip_crc_verified'),'scientific_fits_started':0,'no_scientific_attempts':True}
  if child.get('status')=='committed_and_resolved':
   pub=PUBLIC/(finished.strftime('%Y%m%dT%H%M%SZ')+'_'+opid+'.json');atomic_json(pub,safe)
  result_status='successful';private['status']='successful';private['public_receipt_path']=str(pub) if child.get('status')=='committed_and_resolved' else None
  private['child_result_sha256']=sha256_file(op/'child_result.json');private['supervisor_result_sha256']=sha256_file(op/'supervisor_result.json')
  return safe
 except BaseException as exc:
  result_status='wrapper_failed' if private.get('wrapper_identity') is not None else 'backoff'
  private.update({'status':result_status,'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()})
  raise
 finally:
  if proc is not None and proc.poll() is None:
   try:
    if _wrapper_identity(proc):_signal_wrapper(proc,signal.SIGINT);proc.wait(timeout=TERM_GRACE+10)
   except Exception:pass
  private.setdefault('status',result_status)
  private['finalized_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
  atomic_json(private_dir/'driver_result.json',private,0o600)
  lock.close()

def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--preflight-only',action='store_true');ap.add_argument('--storage-codec-policy',choices=(CODEC_POLICY,CODEC_PAYLOAD12_POLICY));ap.add_argument('--archive-io-profile',choices=ARCHIVE_IO_PROFILES);args=ap.parse_args()
 try:print(json.dumps(run_once(preflight_only=args.preflight_only,storage_codec_policy=args.storage_codec_policy,archive_io_profile=args.archive_io_profile),sort_keys=True,default=str),flush=True)
 except Exception as e:
  print(json.dumps({'status':'backoff','reason':type(e).__name__+': '+str(e)},sort_keys=True),flush=True)
  raise SystemExit(2)

if __name__=='__main__':main()
