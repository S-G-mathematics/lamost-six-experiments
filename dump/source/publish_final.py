#!/usr/bin/env python3
"""Final-only publisher. Staged for review; never install or run before approval."""
import argparse, contextlib, csv, datetime as dt, fcntl, hashlib, json, os, pathlib, re, subprocess, zipfile
ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'
REPO=ROOT/'github_delivery_20261028'
REMOTE={'https://github.com/S-G-mathematics/lamost-six-experiments.git','git@github.com:S-G-mathematics/lamost-six-experiments.git','ssh://git@github.com/S-G-mathematics/lamost-six-experiments.git'}
PLAN={'3':69,'4':1773,'5':960,'6':21}
CATS={'reports_tables_figures','frozen_E1_report_tables','E2_report_tables','execution_manifest','protocol_config_summary','curated_E3_incident_provenance','full_archive_location','reproduction_instructions'}
PRIVATE={'pid','pgid','worker_pid','controller_pid','owner_pid','parent_pid','process_id','process_start_ticks','cmdline','argv','env','environ','env_vars','environment_variables','hold_nonce','nonce','process_inventory','phase_supervision','request_path','result_path','worker_log_path','uid','gid','access_token','refresh_token','token','secret','password','credential','private_key','ssh_key'}
BAD={'.joblib','.pkl','.pickle','.npz','.npy','.parquet','.fits','.fit','.log','.sqlite','.db','.pem','.key','.gz'}
class Waiting(RuntimeError): pass
class Invalid(RuntimeError): pass
class TransientGit(RuntimeError): pass
def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def load(p):
 try:
  x=json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
 except FileNotFoundError as e: raise Waiting('finalizer evidence not ready') from e
 except Exception as e: raise Invalid('malformed finalizer evidence') from e
 if not isinstance(x,dict): raise Invalid('evidence object expected')
 return x
def private_keys(x):
 out=[]
 if isinstance(x,dict):
  for k,v in x.items():
   n=str(k).lower().replace('-','_')
   if n in PRIVATE or n.endswith('_pid') or n.endswith('_start_ticks') or n.endswith('_token') or n.endswith('_secret'): out.append(n)
   else: out+=private_keys(v)
 elif isinstance(x,list):
  for v in x: out+=private_keys(v)
 return out
def workers(runtime, proc='/proc'):
 targets={(runtime/'source'/n).resolve() for n in ('controller.py','worker.py','phase_worker.py','parallel_rf/worker.py','parallel_rf/phase_worker.py','svm_margin/worker.py','svm_margin/phase_worker.py','e6_phase_supervisor.py','finalize_project.py')}
 found=0
 for p in pathlib.Path(proc).iterdir():
  if not p.name.isdigit(): continue
  try: args=(p/'cmdline').read_bytes().split(b'\0'); cwd=pathlib.Path(os.readlink(p/'cwd'))
  except OSError: continue
  for raw in args:
   if not raw: continue
   try:
    q=pathlib.Path(os.fsdecode(raw)); q=q if q.is_absolute() else cwd/q
    if q.resolve() in targets: found+=1; break
   except (OSError,RuntimeError,ValueError): pass
 return found
def public_content_check(member,data):
 low=data.lower()
 if any(q in low for q in (b'supervision={',b'process_start_ticks',b'worker_pid',b'pgid=',b"'pid':",b'\"pid\":',b"'pgid':",b'\"pgid\":',b'-----begin private key-----',b'-----begin openssh private key-----',b'-----begin rsa private key-----',b'aws_secret_access_key',b'aws_access_key_id',b'ghp_',b'github_pat_')):
  raise Invalid('private process or credential marker in report member')
 if member.lower().endswith('.json'):
  if private_keys(json.loads(data)): raise Invalid('private process keys in public JSON')
 if member.lower().endswith('.csv'):
  try: headers=next(csv.reader(data.decode('utf-8-sig').splitlines()))
  except Exception: raise Invalid('malformed public CSV')
  for h in headers:
   n=h.strip().lower().replace('-','_').replace(' ','_')
   if n in PRIVATE or n.endswith('_pid') or n.endswith('_start_ticks') or n.endswith('_token') or n.endswith('_secret') or any(k in n for k in ('password','credential','private_key','ssh_key','api_key','access_key')):
    raise Invalid('private process or credential column in public CSV')
def terminal_ok(t):
 if not isinstance(t,dict) or t.get('total_tasks')!=6270: raise Waiting('finalizer has not recorded all 6,270 terminal tasks')
 if t.get('scientific_counts')!=PLAN: raise Invalid('frozen E3-E6 denominator mismatch')
 if not re.fullmatch(r'[0-9a-f]{64}',str(t.get('plan_file_sha256',''))): raise Invalid('terminal plan hash missing')
 if not re.fullmatch(r'[0-9a-f]{64}',str(t.get('plan_sha256',''))): raise Invalid('terminal plan identity missing')
 outcomes=t.get('outcomes')
 if not isinstance(outcomes,dict): raise Invalid('terminal outcomes missing')
 for e,n in PLAN.items():
  row=outcomes.get(e)
  if not isinstance(row,dict) or sum(int(v) for v in row.values())!=n: raise Waiting('terminal outcomes do not reconcile')
 return t
def archive_record(root,rec,proof,small=False):
 if not isinstance(rec,dict) or not rec.get('path'): raise Waiting('final archive record missing')
 p=pathlib.Path(rec['path']).resolve(); pkg=(root/'packages').resolve()
 if pkg not in p.parents or not p.is_file(): raise Waiting('final archive is not present in packages')
 st=p.stat()
 if st.st_size!=int(rec.get('bytes',-1)): raise Invalid('final archive size changed')
 if rec.get('zip_crc_passed') is not True or rec.get('report_review_proof')!=proof: raise Invalid('archive finalizer binding missing')
 receipt=load(str(p)+'.receipt.json')
 for k in ('path','bytes','sha256','zip_crc_passed','report_review_proof'):
  if receipt.get(k)!=rec.get(k): raise Invalid('archive receipt mismatch')
 if rec.get('mtime_ns') is not None:
  if st.st_mtime_ns!=int(rec['mtime_ns']) or receipt.get('mtime_ns')!=rec.get('mtime_ns'): raise Invalid('archive mtime binding mismatch')
 if not re.fullmatch(r'[0-9a-f]{64}',str(rec.get('sha256',''))): raise Invalid('archive SHA malformed')
 if small:
  if st.st_size>512*1024*1024: raise Waiting('compact archive over bounded validation limit')
  if file_sha(p)!=rec['sha256']: raise Invalid('compact archive SHA mismatch')
  with zipfile.ZipFile(p) as z:
   if z.testzip() is not None: raise Invalid('compact archive CRC failure')
 return {'path':str(p),'bytes':st.st_size,'sha256':rec['sha256'],'mtime_ns':st.st_mtime_ns}
def portable_tests_ok(runtime,repo):
 bp=runtime/'tests/PORTABLE_TEST_BUNDLE.json'; bundle=load(bp)
 if not (repo/'code/tests/PORTABLE_TEST_BUNDLE.json').is_file() or file_sha(repo/'code/tests/PORTABLE_TEST_BUNDLE.json')!=file_sha(bp): raise Invalid('Git test bundle differs from finalizer-tested bundle')
 prefix='runtime_20261025/tests/'; runner=bundle.get('runner','')
 if not isinstance(runner,str) or not runner.startswith(prefix): raise Invalid('portable runner path is unsafe')
 rel=runner[len(prefix):]; rp=pathlib.PurePosixPath(rel); expected=bundle.get('runner_sha256')
 if rp.is_absolute() or '..' in rp.parts: raise Invalid('portable runner path traversal')
 if file_sha(runtime/'tests'/pathlib.Path(*rp.parts))!=expected or file_sha(repo/'code/tests'/pathlib.Path(*rp.parts))!=expected: raise Invalid('portable runner hash mismatch')
 rows=bundle.get('tests')
 if not isinstance(rows,list) or not rows: raise Invalid('portable test list is empty')
 for row in rows:
  member=row.get('test_member','')
  if not isinstance(member,str) or not member.startswith(prefix): raise Invalid('portable test path is unsafe')
  rel=member[len(prefix):]; rp=pathlib.PurePosixPath(rel); expected=row.get('portable_sha256')
  if rp.is_absolute() or '..' in rp.parts: raise Invalid('portable test path traversal')
  if not expected or file_sha(runtime/'tests'/pathlib.Path(*rp.parts))!=expected or file_sha(repo/'code/tests'/pathlib.Path(*rp.parts))!=expected: raise Invalid('Git test differs from passed portable bundle')
 sources=bundle.get('sources')
 if not isinstance(sources,list) or not sources: raise Invalid('portable source qualification list is empty')
 checked=[]
 for row in sources:
  member=row.get('runtime_member',''); expected=row.get('source_sha256')
  if not isinstance(member,str) or not member.startswith('runtime_20261025/') or not re.fullmatch(r'[0-9a-f]{64}',str(expected)): raise Invalid('portable source qualification row malformed')
  rel=pathlib.PurePosixPath(member).relative_to('runtime_20261025')
  if rel.is_absolute() or '..' in rel.parts: raise Invalid('unsafe portable source path')
  src=runtime/pathlib.Path(*rel.parts)
  if runtime.resolve() not in src.resolve().parents: raise Invalid('portable source symlink escapes runtime')
  if not src.is_file() or file_sha(src)!=expected: raise Invalid('runtime source differs from portable qualification bundle')
  checked.append((member,expected))
 return file_sha(bp),len(rows),checked
def gate(root=ROOT,runtime=R,repo=REPO,worker_probe=workers):
 m=load(runtime/'EC2_COMPLETE_DELIVERY_PENDING.json')
 if m.get('status') not in {'delivery_pending_on_laptop','validated_pending_delivery_reused'}: raise Waiting('finalizer has not passed report/archive gates')
 if m.get('project_complete') is not False or m.get('laptop_copy_verified') is not False: raise Invalid('unexpected finalizer delivery state')
 proof=m.get('report_review')
 if not isinstance(proof,dict) or proof.get('decision')!='pass' or not all(proof.get(k) for k in ('candidate_id','manifest_sha256','audit_receipt_sha256')): raise Waiting('final report review not accepted')
 t=terminal_ok(m.get('terminal_registry'))
 taskfile=runtime/'manifests/tasks.json'
 if not taskfile.is_file() or file_sha(taskfile)!=t['plan_file_sha256']: raise Invalid('frozen task plan SHA mismatch')
 bundle_sha,bundle_count,bundle_sources=portable_tests_ok(runtime,repo)
 e1config=load(root/'project/benchmark/results/master_run_config.json')
 e1hashes=e1config.get('benchmark_python_source_sha256')
 if not isinstance(e1hashes,dict) or len(e1hashes)!=19: raise Invalid('frozen E1 source hash map missing')
 with (repo/'file_manifest.csv').open(newline='',encoding='utf-8') as mf: frows=list(csv.DictReader(mf))
 fmap={row['source']:row['destination'] for row in frows}
 for name,h in e1hashes.items():
  src=root/'project/benchmark'/name; rel='project/benchmark/'+name; dest=fmap.get(rel)
  if not dest or not src.is_file() or file_sha(src)!=h or not (repo/dest).is_file() or file_sha(repo/dest)!=h: raise Invalid('Git E1 source differs from frozen 19-file source map')
 ev=m.get('frozen_evidence') or {}; e1=ev.get('e1_ledger') or {}; e2=ev.get('e2') or {}
 if (e1.get('rows'),e1.get('successful'),e1.get('failed'),e1.get('unsupported'))!=(765,674,81,10): raise Invalid('frozen E1 evidence mismatch')
 if (e2.get('primary_evaluated'),e2.get('primary_planned'),e2.get('unavailable'),e2.get('classical_evaluated'),e2.get('classical_planned'),e2.get('low_precision'))!=(108,150,42,120,120,210): raise Invalid('frozen E2 evidence mismatch')
 rec=ev.get('e1_recovery_counts')
 if rec!={'successful_test_evaluation':24,'failed':10,'user_stopped':2,'not_attempted_user_stopped':55}: raise Invalid('stopped E1 recovery supplement evidence mismatch')
 sf=m.get('runtime_source_freeze') or {}; freeze_path=runtime/'manifests/freeze.json'
 if not freeze_path.is_file() or file_sha(freeze_path)!=sf.get('freeze_sha256'): raise Invalid('runtime freeze receipt mismatch')
 fr=load(freeze_path); srcs=fr.get('source_sha256')
 if not isinstance(srcs,dict) or len(srcs)!=sf.get('source_files_verified'): raise Invalid('source-freeze file count mismatch')
 for n,h in srcs.items():
  q=pathlib.PurePosixPath(n)
  if q.is_absolute() or '..' in q.parts or q.suffix!='.py': raise Invalid('unsafe frozen source path')
  f=runtime/'source'/pathlib.Path(*q.parts)
  if not f.is_file() or file_sha(f)!=h: raise Invalid('frozen source SHA mismatch')
 state=load(runtime/'finalizer_state.json')
 if state.get('status') not in {'delivery_pending_on_laptop','validated_pending_delivery_reused'} or state.get('report_review_proof')!=proof: raise Waiting('finalizer state not at accepted checkpoint')
 full=archive_record(root,m.get('full_archive'),proof,False); small=archive_record(root,m.get('small_delivery_zip'),proof,True)
 if state.get('full_archive',{}).get('sha256')!=full['sha256']: raise Invalid('finalizer state/full archive mismatch')
 rpt=m.get('final_report') or {}; rp=pathlib.Path(str(rpt.get('path',''))).resolve()
 if runtime.resolve() not in rp.parents or not rp.is_file() or rp.stat().st_size!=rpt.get('bytes') or file_sha(rp)!=rpt.get('sha256'): raise Invalid('final report changed')
 if worker_probe(runtime): raise Waiting('project workers are still active')
 identity={'plan_sha256':t['plan_file_sha256'],'freeze_sha256':sf['freeze_sha256'],'report_sha256':rpt['sha256'],'full_sha256':full['sha256'],'small_sha256':small['sha256']}
 fingerprint=sha(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())
 return {'ready':True,'fingerprint':fingerprint,'terminal':t,'evidence':ev,'freeze':fr,'source_freeze':sf,'full':full,'small':small,'report':rpt,'proof':proof,'portable_tests_sha256':bundle_sha,'portable_test_file_count':bundle_count,'portable_sources':bundle_sources}
@contextlib.contextmanager
def lockfile(path):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a+') as f:
  try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError: raise Waiting('publisher lock busy')
  yield
def once(gate_fn, already_fn, publish_fn, lock):
 with lockfile(lock):
  try: x=gate_fn()
  except Waiting as e: return {'status':'waiting','reason':str(e),'git_touched':False}
  if not x.get('ready'): return {'status':'waiting','git_touched':False}
  prior=already_fn(x)
  if prior: return {'status':'already_published','fingerprint':x['fingerprint'],'git_touched':False,**(prior if isinstance(prior,dict) else {})}
  return {'status':'published',**publish_fn(x)}
def gate_signature(root,runtime,repo):
 paths=[runtime/'EC2_COMPLETE_DELIVERY_PENDING.json',runtime/'finalizer_state.json',runtime/'manifests/freeze.json',runtime/'manifests/tasks.json',runtime/'tests/PORTABLE_TEST_BUNDLE.json',root/'project/benchmark/results/master_run_config.json',repo/'file_manifest.csv',pathlib.Path(__file__)]
 try:
  m=json.loads(paths[0].read_text())
 except Exception: m={}
 try:
  fr=json.loads((runtime/'manifests/freeze.json').read_text())
  paths += [runtime/'source'/pathlib.Path(*pathlib.PurePosixPath(k).parts) for k in fr.get('source_sha256',{})]
 except Exception: pass
 try:
  pb=json.loads((runtime/'tests/PORTABLE_TEST_BUNDLE.json').read_text())
  for row in pb.get('sources',[]):
   member=row.get('runtime_member','')
   if isinstance(member,str) and member.startswith('runtime_20261025/'):
    rel=pathlib.PurePosixPath(member).relative_to('runtime_20261025')
    if not rel.is_absolute() and '..' not in rel.parts: paths.append(runtime/pathlib.Path(*rel.parts))
  for member in [pb.get('runner','')]+[r.get('test_member','') for r in pb.get('tests',[]) if isinstance(r,dict)]:
   if isinstance(member,str) and member.startswith('runtime_20261025/tests/'):
    rel=pathlib.PurePosixPath(member).relative_to('runtime_20261025')
    if not rel.is_absolute() and '..' not in rel.parts: paths.append(repo/'code'/pathlib.Path(*rel.parts))
 except Exception: pass
 rpt=m.get('final_report') or {}
 if rpt.get('path'): paths.append(pathlib.Path(rpt['path']))
 archive_meta=[]
 for k in ('full_archive','small_delivery_zip'):
  rec=m.get(k) or {}
  if rec.get('path'):
   ap=pathlib.Path(rec['path'])
   receipt=pathlib.Path(str(ap)+'.receipt.json')
   try:
    st=ap.stat()
    archive_meta.append((k,str(ap),st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_dev,st.st_ino,file_sha(receipt) if receipt.is_file() else None))
   except OSError: archive_meta.append((k,str(ap),None,None,None,None,None,file_sha(receipt) if receipt.is_file() else None))
   if k=='small_delivery_zip': paths.append(ap)
 for name in ('master_run_config.json',):
  try:
   cfg=json.loads((root/'project/benchmark/results'/name).read_text())
   fmap={}
   try:
    with (repo/'file_manifest.csv').open(newline='',encoding='utf-8') as mf:fmap={r['source']:r['destination'] for r in csv.DictReader(mf)}
   except Exception:pass
   for n in cfg.get('benchmark_python_source_sha256',{}):
    paths.append(root/'project/benchmark'/n)
    d=fmap.get('project/benchmark/'+n)
    if d:paths.append(repo/d)
  except Exception: pass
 rows=[]
 for p in paths:
  try: rows.append((str(p),p.stat().st_size,file_sha(p)))
  except OSError: rows.append((str(p),None,None))
 return sha(json.dumps({'paths':rows,'archives':archive_meta},separators=(',',':')).encode())
def state_path(runtime):
 return runtime/'logs/operational/final_github_publisher_state.json'
def state_load(path):
 try:
  x=json.loads(path.read_text())
  return x if isinstance(x,dict) else {}
 except FileNotFoundError:return {}
 except Exception:raise Invalid('publisher state file is malformed')
 if not isinstance(x,dict):raise Invalid('publisher state file is malformed')
def state_save(path,state):
 atomic(path,(json.dumps(state,sort_keys=True,indent=2)+'\n').encode())
def record_event(runtime,event):
 path=runtime/'logs/operational/final_github_publisher_attempts.jsonl'
 path.parent.mkdir(parents=True,exist_ok=True)
 row={'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),**event}
 with path.open('ab') as f:
  f.write((json.dumps(row,sort_keys=True)+'\n').encode());f.flush();os.fsync(f.fileno())
def run_once(root,runtime,repo,remove_cron=False):
 lock=runtime/'locks/final_github_publisher.lock'
 with lockfile(lock):
  statefile=state_path(runtime); sig=gate_signature(root,runtime,repo); now=dt.datetime.now(dt.timezone.utc).timestamp()
  try:state=state_load(statefile)
  except Invalid as e:
   state={'invalid_latch':sig,'invalid_recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':str(e),'publisher_sha256':file_sha(__file__)};state_save(statefile,state);record_event(runtime,{'status':'blocked_latched','reason':str(e),'input_fingerprint':sig});return {'status':'blocked_latched','git_touched':False,'reason':str(e)}
  if state.get('invalid_latch')==sig:
   return {'status':'blocked_latched','git_touched':False,'reason':'same publisher code and gate inputs remain latched after a deterministic invalid state'}
  if state.get('transient_gate_signature')==sig and float(state.get('next_retry_epoch',0))>now:
   return {'status':'waiting_backoff','git_touched':False,'retry_after_seconds':max(0,int(state['next_retry_epoch']-now))}
  try: x=gate(root,runtime,repo)
  except Waiting as e:return {'status':'waiting','git_touched':False,'reason':str(e)}
  except Invalid as e:
   state={'invalid_latch':sig,'invalid_recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':str(e),'publisher_sha256':file_sha(__file__)}
   state_save(statefile,state);record_event(runtime,{'status':'blocked_latched','reason':str(e),'input_fingerprint':sig})
   return {'status':'blocked_latched','git_touched':False,'reason':str(e)}
  except Exception as e:
   reason='unexpected gate error: '+type(e).__name__
   state={'invalid_latch':sig,'invalid_recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':reason,'publisher_sha256':file_sha(__file__)}
   state_save(statefile,state);record_event(runtime,{'status':'blocked_latched','reason':reason,'input_fingerprint':sig})
   return {'status':'blocked_latched','git_touched':False,'reason':reason}
  try:
   prior=_already(repo,x,root,runtime)
   if prior:
    result={'status':'already_published','fingerprint':x['fingerprint'],'git_touched':False,**prior}
   else: result={'status':'published',**publish(repo,root,runtime,x)}
  except TransientGit as e:
   n=int(state.get('transient_failures',0))+1 if state.get('transient_gate_signature')==sig else 1; delay=min(1800,60*(2**min(n-1,5)))
   state={'transient_gate_signature':sig,'transient_failures':n,'last_transient_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'next_retry_epoch':now+delay,'reason':str(e)}
   state_save(statefile,state);record_event(runtime,{'status':'waiting_backoff','reason':str(e),'input_fingerprint':sig,'retry_after_seconds':delay,'attempt':n})
   return {'status':'waiting_backoff','git_touched':False,'retry_after_seconds':delay}
  except Invalid as e:
   state={'invalid_latch':sig,'invalid_recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':str(e),'publisher_sha256':file_sha(__file__)}
   state_save(statefile,state);record_event(runtime,{'status':'blocked_latched','reason':str(e),'input_fingerprint':sig})
   return {'status':'blocked_latched','git_touched':False,'reason':str(e)}
  except Exception as e:
   reason='unexpected publisher error: '+type(e).__name__
   state={'invalid_latch':sig,'invalid_recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':reason,'publisher_sha256':file_sha(__file__)}
   state_save(statefile,state);record_event(runtime,{'status':'blocked_latched','reason':reason,'input_fingerprint':sig})
   return {'status':'blocked_latched','git_touched':False,'reason':reason}
  state={'last_verified_fingerprint':x['fingerprint'],'last_status':result['status'],'verified_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'publisher_sha256':file_sha(__file__)}
  state_save(statefile,state);record_event(runtime,{'status':result['status'],'fingerprint':x['fingerprint']})
  if remove_cron and result['status'] in ('published','already_published'):
   try:result['owned_cron_lines_removed']=remove_owned_cron()
   except (TransientGit,Invalid):result['owned_cron_cleanup']='pending_retry_on_next_run'
  return result
def remove_owned_cron():
 marker='LAMOST_FINAL_GITHUB_PUBLISHER_20261028'
 try:
  p=subprocess.run(['crontab','-l'],capture_output=True,text=True,timeout=10)
  if p.returncode:return 0
  old=p.stdout.splitlines(); new=[line for line in old if marker not in line]
  removed=len(old)-len(new)
  if removed:
   q=subprocess.run(['crontab','-'],input='\n'.join(new)+'\n',capture_output=True,text=True,timeout=10)
   if q.returncode:raise Invalid('failed to remove only tagged publisher cron lines')
   verify=subprocess.run(['crontab','-l'],capture_output=True,text=True,timeout=10)
   if verify.returncode==0 and any(marker in line for line in verify.stdout.splitlines()):raise Invalid('tagged publisher cron line remains after removal')
  return removed
 except FileNotFoundError:return 0
 except subprocess.TimeoutExpired:raise TransientGit('crontab operation timed out')
def git(repo,args,timeout=120):
 env=os.environ.copy();env.update({'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'Never','GIT_ASKPASS':'/bin/false'})
 try:p=subprocess.run(['git',*args],cwd=repo,env=env,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired as e:raise TransientGit('Git operation timed out') from e
 if p.returncode:
  err=(p.stderr or '').lower()
  if any(x in err for x in ('timed out','connection reset','connection refused','remote end hung up','http 502','http 503','http 504','temporary failure','could not resolve host','network is unreachable','connection timed out','early eof')): raise TransientGit('transient Git transport failure')
  raise Invalid('noninteractive Git operation failed; output suppressed')
 return p.stdout.strip()
def push_bounded(repo,refspec,branch,commit):
 for attempt in range(2):
  try:
   git(repo,['push','origin',refspec],180);return
  except TransientGit:
   if remote(repo).get(branch)==commit:return
   if attempt==1:raise
 raise Invalid('bounded Git push attempts exhausted')
def remote(repo):
 if git(repo,['remote','get-url','origin']) not in REMOTE: raise Invalid('origin is not the pinned LAMOST repository')
 out=git(repo,['ls-remote','--heads','origin','main','results/snapshot-2026-10-28'])
 d={}
 for line in out.splitlines():
  a=line.split()
  if len(a)==2:d[a[1].removeprefix('refs/heads/')]=a[0]
 return d
def ancestor(repo,a,b):
 return subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=repo,capture_output=True).returncode==0
def safe_target(member,category,tag):
 p=pathlib.PurePosixPath(member)
 if p.is_absolute() or '..' in p.parts or '\\' in member: raise Invalid('unsafe ZIP member path')
 if p.suffix.lower() in BAD or any(x.lower() in {'attempts','logs','credentials','private','operational','operations','process_receipts'} for x in p.parts): return None
 if category not in CATS:return None
 prefix=f'reports/FINAL_VALIDATED_{tag}/'
 if category=='reports_tables_figures' and p.parts[0]=='reports':return prefix+'/'.join(p.parts[1:])
 if category=='frozen_E1_report_tables' and p.parts[0]=='E1':return prefix+'E1/'+'/'.join(p.parts[1:])
 if category=='E2_report_tables' and p.parts[0]=='E2':return prefix+'E2/'+'/'.join(p.parts[1:])
 if category=='execution_manifest' and p.parts[0]=='manifests':return prefix+'manifests/'+'/'.join(p.parts[1:])
 if category=='protocol_config_summary' and p.parts[0]=='frozen_E1':return prefix+'frozen_E1/'+'/'.join(p.parts[1:])
 if category=='curated_E3_incident_provenance' and p.name.endswith('.json'):return prefix+'provenance/'+p.name
 if category=='full_archive_location' and p.name=='FULL_ARCHIVE_LOCATION.md':return prefix+p.name
 if category=='reproduction_instructions' and p.name=='RUN_RESUME_REPRODUCE.md':return prefix+p.name
 return None
def atomic(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
 with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def export_final(repo,root,runtime,x):
 tag=x['report']['sha256'][:12]; zpath=pathlib.Path(x['small']['path'])
 with zipfile.ZipFile(zpath) as z:
  names=set(z.namelist()); mn=next((n for n in names if n.endswith('small_delivery_manifest.json')),None)
  if not mn:raise Invalid('small archive manifest missing')
  sm=json.loads(z.read(mn)); files=sm.get('files')
  if not isinstance(files,list):raise Invalid('small archive file list malformed')
  added=[]; rows=[]
  for row in files:
   if not isinstance(row,dict):raise Invalid('malformed small archive row')
   m=row.get('path'); cat=row.get('category')
   if m not in names:raise Invalid('manifest member missing')
   target=safe_target(m,str(cat),tag)
   if target is None:continue
   if int(row.get('bytes',-1))>128*1024*1024:raise Invalid('report member exceeds size cap')
   data=z.read(m)
   if len(data)!=row['bytes'] or sha(data)!=row.get('sha256'):raise Invalid('report member hash mismatch')
   public_content_check(m,data)
   atomic(repo/target,data);added.append(target);rows.append({'source_member':m,'path':target,'bytes':len(data),'sha256':sha(data),'category':cat})
 if not added:raise Invalid('no allowlisted final report members')
 tagdir=repo/'reports'/f'FINAL_VALIDATED_{tag}'
 # Mirror the exact frozen Python sources only.
 source_rows=[]
 required={rel:h for rel,h in x['freeze']['source_sha256'].items()}
 required.update({pathlib.PurePosixPath(member).relative_to('runtime_20261025/source').as_posix():h for member,h in x.get('portable_sources',[]) if member.startswith('runtime_20261025/source/') and member.endswith('.py')})
 for rel,h in required.items():
  q=pathlib.PurePosixPath(rel);src=runtime/'source'/pathlib.Path(*q.parts);data=src.read_bytes()
  if sha(data)!=h:raise Invalid('qualified source changed while exporting')
  target='code/source/'+q.as_posix();atomic(repo/target,data);added.append(target)
  source_rows.append({'source':'runtime_20261025/source/'+q.as_posix(),'path':target,'bytes':len(data),'sha256':h,'category':'qualified_runtime_source'})
 for name in ('freeze.json','tasks.json','plan_summary.json','plan_amendments.json','E3_MANIFEST.json','E4_MANIFEST.json','E5_MANIFEST.json','E6_MANIFEST.json'):
  src=runtime/'manifests'/name
  if not src.is_file():raise Invalid('final configuration manifest missing')
  data=src.read_bytes()
  if name=='tasks.json' and sha(data)!=x['terminal']['plan_file_sha256']:raise Invalid('task plan changed while exporting')
  if name.endswith('.json') and private_keys(json.loads(data)):raise Invalid('private fields in execution manifest')
  target='provenance/manifests/'+name;atomic(repo/target,data);added.append(target)
  source_rows.append({'source':'runtime_20261025/manifests/'+name,'path':target,'bytes':len(data),'sha256':sha(data),'category':'execution_configuration'})
 e1_settings=[]
 for name in ('master_run_config.json','dependencies.freeze.txt','protocol_source.txt'):
  src=root/'project/benchmark/results'/name if name=='master_run_config.json' else root/'project/benchmark'/name
  if not src.is_file(): raise Invalid('frozen E1 configuration missing')
  data=src.read_bytes();target='provenance/final_E1/'+name;atomic(repo/target,data);added.append(target)
  e1_settings.append({'source':str(src.relative_to(root)),'path':target,'bytes':len(data),'sha256':sha(data),'category':'frozen_E1_configuration'})
 note={'schema':'lamost-final-github-export/1','fingerprint':x['fingerprint'],'final_report_sha256':x['report']['sha256'],'full_archive_bytes':x['full']['bytes'],'full_archive_sha256':x['full']['sha256'],'small_archive_sha256':x['small']['sha256'],'plan_file_sha256':x['terminal']['plan_file_sha256'],'freeze_sha256':x['source_freeze']['freeze_sha256'],'registry_observed_utc':x['terminal'].get('registry_observed_utc'),'E1':x['evidence']['e1_ledger'],'E2':x['evidence']['e2'],'terminal_outcomes':x['terminal']['outcomes'],'files':rows+source_rows+e1_settings,'portable_test_bundle_sha256':x['portable_tests_sha256'],'portable_test_file_count':x['portable_test_file_count'],'portable_qualified_source_files':sum(1 for member,h in x.get('portable_sources',[]) if member.startswith('runtime_20261025/source/') and member.endswith('.py')),'private_receipts_included':False,'models_or_datasets_included':False}
 b=(json.dumps(note,indent=2,sort_keys=True)+'\n').encode(); atomic(tagdir/'FINAL_PUBLICATION_MANIFEST.json',b);added.append((tagdir/'FINAL_PUBLICATION_MANIFEST.json').relative_to(repo).as_posix())
 _write_final_progress(repo,x,tag);added.extend(['README.md','LATEST_PROGRESS.md'])
 for rel in ('README.md','LATEST_PROGRESS.md'):
  f=repo/rel; data=f.read_bytes(); note['files'].append({'source':'generated final status from validated finalizer marker','path':rel,'bytes':len(data),'sha256':sha(data),'category':'final_status'})
 b=(json.dumps(note,indent=2,sort_keys=True)+'\n').encode()
 atomic(tagdir/'FINAL_PUBLICATION_MANIFEST.json',b);atomic(repo/'provenance/final_github_export.json',b)
 return sorted(set(added))
def _write_final_progress(repo,x,tag):
 t=x['terminal'];ev=x['evidence'];out=t['outcomes']
 rows=[]
 for e,n in PLAN.items():
  row=out[e];rows.append(f"| E{e} | {n} | {row.get('successful',0)} | {row.get('scientific_failure',0)} | {int(row.get('unsupported',0))+int(row.get('unavailable_dependency',0))} |")
 e1=ev['e1_ledger'];e2=ev['e2'];recovery=ev['e1_recovery_counts']
 report=f"reports/FINAL_VALIDATED_{tag}/FINAL_SCIENTIFIC_REPORT.md";full=f"reports/FINAL_VALIDATED_{tag}/FULL_ARCHIVE_LOCATION.md"
 common=[
  '# LAMOST Six Experiments: Final Validated Status','',
  f"Finalizer observation: {t.get('registry_observed_utc','unknown')} UTC.",
  'The final report and archive gates passed. The project remains pending verification of the laptop copy.','',
  f"Final report: [{report}]({report})",f"Full archive location and SHA: [{full}]({full})",'',
  '| Experiment | Planned | Successful | Scientific failures | Unsupported / unavailable |','|---|---:|---:|---:|---:|',*rows,'',
  f"Frozen E1: {e1['successful']} successful, {e1['failed']} failed, and {e1['unsupported']} unsupported across {e1['rows']} cells. The stopped recovery supplement remains separate: {recovery['successful_test_evaluation']} successful evaluations, {recovery['failed']} failures, {recovery['user_stopped']} user-stopped, and {recovery['not_attempted_user_stopped']} not attempted.",
  f"E2 primary: {e2['primary_evaluated']}/{e2['primary_planned']} evaluated, {e2['unavailable']} unavailable; classical references {e2['classical_evaluated']}/{e2['classical_planned']}. See the final report for reconstruction provenance and fidelity limitations.",
  'Repeated-run summaries are descriptive and report their actual matched denominators. No bootstrap or unsupported significance claims are included.',
  'The Git publication excludes fitted models, FITS, raw datasets, prediction arrays, credentials, and private process receipts. The full EC2 archive location is documented in the linked report.',
  'Previous dated interim reports and commits remain in project history; they are superseded by this final validated report.',''
 ]
 readme=[
  '# LAMOST Six Experiments','',
  '## Final validated publication','',
  f"Final report: [{report}]({report})",
  f"Full EC2 archive location and checksum: [{full}]({full})",
  'The finalizer validated the scientific report and both archives. The overall project is not marked complete until the laptop copy is verified.','',
  '## Final outcome counts','',
  '| Experiment | Planned | Successful | Scientific failures | Unsupported / unavailable |','|---|---:|---:|---:|---:|',*rows,'',
  f"Frozen E1 remains {e1['rows']} cells ({e1['successful']} successful, {e1['failed']} failed, {e1['unsupported']} unsupported). Its stopped recovery supplement is separate ({recovery['successful_test_evaluation']} successful, {recovery['failed']} failed, {recovery['user_stopped']} user-stopped, {recovery['not_attempted_user_stopped']} not attempted).",
  f"E2 primary coverage is {e2['primary_evaluated']}/{e2['primary_planned']}; {e2['unavailable']} primary cells are unavailable. Classical references are {e2['classical_evaluated']}/{e2['classical_planned']}. E2 fidelity and reconstruction caveats are detailed in the report.",
  '',
  '## Reproduction and scope','',
  'Use the source and dependency manifests in code/ and provenance/. The full archive contains the artifacts and data reconstruction instructions needed for reproduction; this Git repository intentionally excludes fitted models, FITS, raw datasets, prediction arrays, credentials, and private operational receipts.',
  'The portable test receipt describes tests run on the existing EC2 runtime. It is evidence of that qualification, not a claim that every test runs in an arbitrary local environment.',
  'Earlier interim snapshots remain available in Git history and dated report directories.','',
  '## Latest progress','',
  '[LATEST_PROGRESS.md](LATEST_PROGRESS.md)',''
 ]
 atomic(repo/'LATEST_PROGRESS.md',chr(10).join(common).encode())
 atomic(repo/'README.md',chr(10).join(readme).encode())
def _publication_receipt(root,x,head,refs):
 receipt={'schema':'lamost-final-github-publication-receipt/1','published_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'commit':head,'branches':refs,'fingerprint':x['fingerprint'],'final_report_sha256':x['report']['sha256'],'full_archive_bytes':x['full']['bytes'],'full_archive_sha256':x['full']['sha256'],'small_archive_bytes':x['small']['bytes'],'small_archive_sha256':x['small']['sha256'],'private_receipts_uploaded':False}
 out=root/'packages'/('FINAL_GITHUB_PUBLICATION_'+x['fingerprint'][:12]+'.json')
 atomic(out,(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode())
 return str(out)
def _read_marker(repo,commit):
 try:return json.loads(git(repo,['show',commit+':provenance/final_github_export.json']))
 except Exception:return {}
def _worktree_paths(runtime,fingerprint):
 token=fingerprint[:16]
 base=runtime/'logs/operational'
 return base/('final_github_publish_worktree_'+token),base/('final_github_publish_worktree_'+token+'.json')
def _cleanup_owned_worktree(repo,runtime,fingerprint):
 path,sidecar=_worktree_paths(runtime,fingerprint)
 if not sidecar.exists():
  if path.exists():raise Invalid('unowned publisher worktree path exists')
  return
 meta=load(sidecar)
 if meta.get('fingerprint')!=fingerprint or pathlib.Path(meta.get('path','')).resolve()!=path.resolve():raise Invalid('publisher worktree ownership receipt mismatch')
 if path.exists():
  listing=git(repo,['worktree','list','--porcelain'])
  registered='worktree '+str(path.resolve()) in listing.splitlines()
  if registered:git(repo,['worktree','remove','--force',str(path.resolve())],60)
  else:
   if (path/'.git').exists():raise Invalid('unregistered Git worktree found at owned path')
   import shutil
   shutil.rmtree(path)
 sidecar.unlink(missing_ok=True)
def _already(repo,x,root,runtime=R):
 if git(repo,['status','--porcelain']): return False
 refs=remote(repo); main=refs.get('main'); result=refs.get('results/snapshot-2026-10-28')
 if not main or not result:return False
 head=git(repo,['rev-parse','HEAD'])
 candidate=None
 for commit in (head,main,result):
  if _read_marker(repo,commit).get('fingerprint')==x['fingerprint']:
   candidate=commit;break
 if candidate is None:return False
 if not ancestor(repo,main,candidate) or not ancestor(repo,result,candidate):return False
 if main!=candidate:push_bounded(repo,f'{candidate}:refs/heads/main','main',candidate)
 if result!=candidate:push_bounded(repo,f'{candidate}:refs/heads/results/snapshot-2026-10-28','results/snapshot-2026-10-28',candidate)
 refs=remote(repo)
 if refs.get('main')!=candidate or refs.get('results/snapshot-2026-10-28')!=candidate:return False
 if head!=candidate:
  if not ancestor(repo,head,candidate):return False
  git(repo,['merge','--ff-only',candidate],60)
 receipt=_publication_receipt(root,x,candidate,refs)
 _cleanup_owned_worktree(repo,runtime,x['fingerprint'])
 return {'verified_receipt':receipt}
def publish(repo,root,runtime,x):
 if git(repo,['remote','get-url','origin']) not in REMOTE:raise Invalid('origin is not pinned')
 if git(repo,['branch','--show-current'])!='main' or git(repo,['status','--porcelain']):raise Invalid('Git checkout must be clean on main')
 refs=remote(repo);base=git(repo,['rev-parse','HEAD'])
 if refs.get('main')!=base:raise Invalid('local main is not current with remote')
 old_result=refs.get('results/snapshot-2026-10-28')
 if not old_result or not ancestor(repo,old_result,base):raise Invalid('results branch is not a fast-forward ancestor')
 wt,sidecar=_worktree_paths(runtime,x['fingerprint'])
 _cleanup_owned_worktree(repo,runtime,x['fingerprint'])
 sidecar.parent.mkdir(parents=True,exist_ok=True)
 atomic(sidecar,(json.dumps({'schema':'lamost-final-publisher-worktree/1','fingerprint':x['fingerprint'],'path':str(wt.resolve()),'base_commit':base},sort_keys=True)+'\n').encode())
 git(repo,['worktree','add','--detach',str(wt),base],60)
 paths=export_final(wt,root,runtime,x)
 git(wt,['add','--',*paths])
 if not git(wt,['diff','--cached','--name-only']):raise Invalid('no final changes staged')
 git(wt,['commit','-m','Publish final validated research report and results'],180)
 head=git(wt,['rev-parse','HEAD'])
 refs=remote(repo)
 if refs.get('main')!=base:raise Invalid('remote main moved during publication')
 push_bounded(repo,f'{head}:refs/heads/main','main',head)
 push_bounded(repo,f'{head}:refs/heads/results/snapshot-2026-10-28','results/snapshot-2026-10-28',head)
 refs=remote(repo)
 if refs.get('main')!=head or refs.get('results/snapshot-2026-10-28')!=head:raise Invalid('remote refs did not verify')
 if git(repo,['rev-parse','HEAD'])!=base or git(repo,['status','--porcelain']):raise Invalid('local main changed during publication')
 git(repo,['merge','--ff-only',head],60)
 receipt=_publication_receipt(root,x,head,refs)
 _cleanup_owned_worktree(repo,runtime,x['fingerprint'])
 return {'commit':head,'branches':refs,'receipt':receipt}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=pathlib.Path,default=ROOT);ap.add_argument('--runtime',type=pathlib.Path,default=R);ap.add_argument('--repo',type=pathlib.Path,default=REPO);ap.add_argument('--publish',action='store_true');ap.add_argument('--remove-owned-cron-on-success',action='store_true');a=ap.parse_args()
 if not a.publish:print(json.dumps({'status':'staged_check_only','published':False}));return 0
 try:
  result=run_once(a.root,a.runtime,a.repo,a.remove_owned_cron_on_success)
  print(json.dumps(result,sort_keys=True));return 2 if result['status']=='blocked_latched' else 0
 except Waiting as e:print(json.dumps({'status':'waiting','reason':str(e),'git_touched':False}));return 0
 except Invalid as e:print(json.dumps({'status':'blocked','reason':str(e),'git_touched':False}));return 2
 except Exception as e:print(json.dumps({'status':'blocked_latched','reason':'publisher runtime error: '+type(e).__name__,'git_touched':False}));return 2
if __name__=='__main__':raise SystemExit(main())
