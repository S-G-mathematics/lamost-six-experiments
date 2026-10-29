#!/usr/bin/env python3
import argparse,csv,datetime as dt,fcntl,hashlib,json,os,re,shutil,sqlite3,subprocess,sys,tempfile,zipfile
from pathlib import Path
from collections import Counter
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025'
REPO=ROOT/'github_delivery_20261028';BUILDER=R/'reports/deadline_submission_20261029/build_deadline_report.py'
BUILDER_SHA='cbf3bc851f585370235e778a744a1e4690572604a6a38a1d6231277efa9f86f3'
EXPECTED={3:69,4:1773,5:960,6:21}
SUFFIXES={'.md','.csv','.json','.png','.svg','.html','.sha256'}
EXCLUDE={'engineering_audits','staging','operational','private','history','overall_case_index','__pycache__'}
FORBIDDEN={'.npz','.npy','.parquet','.joblib','.pkl','.pickle','.fits','.log','.db'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def state(t):
 x=t.get('outcome') or t.get('status')
 if t.get('status')=='validated_terminal' and isinstance(x,dict):return x.get('status') or x.get('outcome') or 'validated_terminal'
 return x
def validate_rows(rows):
 c={e:Counter() for e in EXPECTED}
 for r in rows:
  e=int(r['experiment'])
  if e not in c or not r.get('scientific_case'):raise ValueError('Unexpected row in scientific ledger')
  c[e][state(r)]+=1
 for e,n in EXPECTED.items():
  if sum(c[e].values())!=n:raise ValueError(f'E{e} has {sum(c[e].values())}/{n} planned cases: {dict(c[e])}')
  bad=set(c[e])-{'successful','scientific_failure','unsupported','unavailable_dependency','waiting_for_dependency','planned','running','operationally_interrupted','operationally_invalid','user_stopped','packaging_pending'}
  if bad:raise ValueError(f'E{e} has unrecognized states: {sorted(bad)}')
 return c
SAFE_TASK_FIELDS=('key','scientific_case','experiment','kind','rep','budget','method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator','status','outcome','validation_state','dependencies')
def normalized_task(raw):
 t={k:raw[k] for k in SAFE_TASK_FIELDS if k in raw}
 if not t.get('scientific_case'):return None
 if t.get('status')=='waiting_dependency':t['status']='waiting_for_dependency'
 if isinstance(t.get('outcome'),dict):
  x=t['outcome'];t['outcome']=x.get('status') or x.get('outcome') or t.get('status')
 return t
def capture_registry(db_path,now_fn=None):
 now_fn=now_fn or (lambda:dt.datetime.now(dt.timezone.utc).isoformat())
 conn=sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True,timeout=30)
 try:
  conn.execute('BEGIN')
  conn.execute('SELECT count(*) FROM tasks').fetchone()  # establishes the WAL snapshot before timestamping
  observed=now_fn()
  records=conn.execute('SELECT key,record FROM tasks ORDER BY key').fetchall()
  tasks=[]
  for key,raw in records:
   item=normalized_task(json.loads(raw))
   if item is None:continue
   if item.get('key')!=key:raise ValueError('SQLite key/record mismatch')
   if '..' in Path(key).parts or Path(key).is_absolute():raise ValueError('Unsafe task key')
   tasks.append(item)
  counts={}
  for t in tasks:
   group=counts.setdefault(str(t['experiment']),Counter());group[t.get('outcome') or t.get('status')]+=1
  return {'schema_version':1,'observed_utc':observed,'tasks':tasks,'scientific_counts':{k:dict(v) for k,v in counts.items()}},len(records)
 finally:
  conn.rollback();conn.close()
def public_members():
 names=subprocess.check_output(['git','-C',str(REPO),'ls-files','-z'],text=False).split(b'\0')
 out=[];excluded=Counter()
 for raw in names:
  if not raw:continue
  n=raw.decode();p=Path(n)
  if n.startswith('reports/deadline_submission_20261029/'):
   excluded['fresh_snapshot_replaces_existing']+=1;continue
  if set(p.parts)&EXCLUDE:
   excluded['private_or_superseded_path']+=1;continue
  if n in {'README.md','LATEST_PROGRESS.md'}:
   excluded['regenerated_top_level_status']+=1;continue
  if n.startswith(('reports/','experiments/','provenance/manifests/','provenance/identity/')):
   if p.suffix.lower() not in SUFFIXES or p.suffix.lower() in FORBIDDEN:
    excluded['not_report_table_figure_or_manifest']+=1;continue
   out.append(n)
  else:excluded['outside_allowlist']+=1
 return sorted(set(out)),dict(excluded)
def safe_member(name):
 p=Path(name)
 if p.is_absolute() or '..' in p.parts or p.suffix.lower() in FORBIDDEN or set(p.parts)&EXCLUDE:
  raise ValueError('Unsafe ZIP member: '+name)
def self_test():
 with tempfile.TemporaryDirectory() as td:
  db=Path(td)/'fixture.sqlite'
  c=sqlite3.connect(db);c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE tasks(key TEXT PRIMARY KEY,record TEXT NOT NULL)')
  c.execute('INSERT INTO tasks VALUES (?,?)',('e3/fixture',json.dumps({'key':'e3/fixture','scientific_case':True,'experiment':3,'status':'waiting_dependency','pid':1234,'process_start_ticks':99})));c.commit();c.close()
  def concurrent_update():
   writer=sqlite3.connect(db)
   writer.execute('UPDATE tasks SET record=? WHERE key=?',(json.dumps({'key':'e3/fixture','scientific_case':True,'experiment':3,'status':'successful'}),'e3/fixture'));writer.commit();writer.close()
   return '2026-10-29T10:45:00+00:00'
  snapshot,dbcount=capture_registry(db,concurrent_update)
  safe=snapshot['tasks'][0]
  assert dbcount==1 and snapshot['observed_utc']=='2026-10-29T10:45:00+00:00'
  assert safe['status']=='waiting_for_dependency' and 'pid' not in safe and 'process_start_ticks' not in safe
  check=sqlite3.connect(db);assert json.loads(check.execute('SELECT record FROM tasks').fetchone()[0])['status']=='successful';check.close()
 toy=[]
 for e,n,st in [(3,69,'successful'),(4,1773,'waiting_for_dependency'),(5,960,'waiting_for_dependency'),(6,21,'waiting_for_dependency')]:
  toy.extend({'experiment':e,'scientific_case':True,'outcome':st} for _ in range(n))
 c=validate_rows(toy);assert c[3]['successful']==69 and c[4]['waiting_for_dependency']==1773
 mixed=visible_states(Counter({'successful':1,'scientific_failure':1,'operationally_interrupted':1,'operationally_invalid':1,'user_stopped':1,'unsupported':1,'unavailable_dependency':1,'waiting_for_dependency':1,'packaging_pending':1}))
 assert mixed=={'successful':1,'scientific_failures':1,'unsupported':1,'unavailable':1,'user_stopped':1,'operationally_interrupted':1,'operationally_invalid':1,'packaging_pending':1,'waiting_or_active':1}
 assert repository_payload_provenance('abc123','')['payload_commit_reference']=='abc123'
 dirty=repository_payload_provenance('abc123',' M README.md')
 assert not dirty['repo_worktree_clean'] and dirty['payload_commit_reference'] is None and 'member_sha256' in dirty['repo_payload_basis']
 try:validate_rows(toy[:-1])
 except ValueError:pass
 else:raise AssertionError('incomplete planned cases accepted')
 for x in ('../x.csv','models/a.joblib','reports/engineering_audits/private.json'):
  try:safe_member(x)
  except ValueError:pass
  else:raise AssertionError('unsafe member accepted')
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import deadline_snapshot_timer
 deadline_snapshot_timer.self_test()
 print('SQLite transaction snapshot, post-cutoff update isolation, privacy, case-accounting, and timer-identity fixtures passed')
def git_command(*args,timeout=60):
 env=os.environ.copy();env['GIT_TERMINAL_PROMPT']='0'
 return subprocess.run(['git','-C',str(REPO),*args],text=True,capture_output=True,timeout=timeout,env=env)
def repository_payload_provenance(head,porcelain,command_ok=True):
 clean=bool(command_ok and head and not porcelain)
 return {'repo_head_reference':head or None,'repo_worktree_clean':clean,
  'repo_payload_basis':'clean_head_worktree' if clean else 'allowlisted_working_tree_files_bound_by_member_sha256',
  'payload_commit_reference':head if clean else None}
def visible_states(c):
 return {'successful':c.get('successful',0),'scientific_failures':c.get('scientific_failure',0),'unsupported':c.get('unsupported',0),'unavailable':c.get('unavailable_dependency',0),'user_stopped':c.get('user_stopped',0),'operationally_interrupted':c.get('operationally_interrupted',0),'operationally_invalid':c.get('operationally_invalid',0),'packaging_pending':c.get('packaging_pending',0),'waiting_or_active':c.get('waiting_for_dependency',0)+c.get('running',0)+c.get('planned',0)}
def table_status(e,c):
 v=visible_states(c)
 return f'{v["successful"]:,} successful, {v["scientific_failures"]:,} recorded scientific failures, {v["unsupported"]:,} unsupported, {v["unavailable"]:,} unavailable, {v["user_stopped"]:,} user-stopped, {v["operationally_interrupted"]:,} operationally interrupted, {v["operationally_invalid"]:,} operationally invalid, {v["packaging_pending"]:,} packaging-pending, {v["waiting_or_active"]:,} waiting/active / {EXPECTED[e]:,}'
def refresh_readme(path,stamp,counts,rows):
 text=path.read_text(encoding='utf-8')
 m=re.search(r'(?<=read-only registry observed )([^ ]+)(?= UTC)',text)
 if m:text=text.replace(m.group(1),stamp)
 for e in (3,4,5):
  lines=text.splitlines()
  for i,line in enumerate(lines):
   if line.startswith(f'| E{e} |'):
    bits=line.split('|');bits[3]=' '+table_status(e,counts[e])+' ';lines[i]='|'.join(bits);break
  text='\n'.join(lines)+'\n'
 primary=[r for r in rows if int(r['experiment'])==6 and r.get('kind')=='ensemble']
 refs=[r for r in rows if int(r['experiment'])==6 and (r.get('kind')=='alias' or r.get('condition')=='member_reference')]
 def count(rows,state):return sum((r.get('outcome') or r.get('status'))==state for r in rows)
 lines=text.splitlines()
 for i,line in enumerate(lines):
  if line.startswith('| E6 |'):
   bits=line.split('|');bits[3]=f' {count(refs,"successful")} successful member-reference aliases, {count(refs,"unavailable_dependency")} unavailable references; {count(primary,"scientific_failure")} ensemble failures, {count(primary,"unavailable_dependency")} unavailable ensembles; 0/6 successful primary test evaluations ';lines[i]='|'.join(bits);break
 text='\n'.join(lines)+'\n'
 waiting=counts[4].get('waiting_for_dependency',0)+counts[4].get('running',0)+counts[4].get('planned',0)+counts[5].get('waiting_for_dependency',0)+counts[5].get('running',0)+counts[5].get('planned',0)
 text=re.sub(r'At the registry snapshot .*?E4/E5 have \d+ waiting scientific cases \([^)]+\)\.',f'At the registry snapshot {stamp}, E4/E5 have {waiting} waiting or active scientific cases ({counts[4].get("waiting_for_dependency",0)} E4; {counts[5].get("waiting_for_dependency",0)} E5).',text,count=1)
 summary=f'Read-only registry snapshot {stamp} UTC: E3: {table_status(3,counts[3])}; E4: {table_status(4,counts[4])}; E5: {table_status(5,counts[5])}. Operational interruptions/invalidations, user-stopped work, and packaging-pending work are counted separately from scientific failures. E6 has {count(refs,"successful")} successful member-reference aliases and {count(primary,"successful")}/6 successful primary ensembles. E1 remains frozen at 674 successful, 81 failed (55 resource; 26 supervisor-terminal manifests remained started) and 10 unsupported; E2 remains 108/150 primary and 120/120 classical references. The E3-E6 ledger accounts for all 2,823 planned cases in this snapshot. This is interim; final calibration replay and full artifact validation remain pending.'
 text=re.sub(r'(?m)^Read-only registry snapshot .*$',summary,text,count=1)
 path.write_text(text,encoding='utf-8')
def update_file_manifests(repo_paths,stamp,source_root):
 fm=REPO/'file_manifest.csv'
 with fm.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f));fields=list(rows[0])
 by={r['destination']:r for r in rows}
 for dest in repo_paths:
  p=REPO/dest;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
  if dest not in by:
   row={k:'' for k in fields};row['destination']=dest;rows.append(row);by[dest]=row
  row=by[dest];row.update(size_bytes=str(len(raw)),sha256=h,destination_sha256=h)
  if dest in ('README.md','LATEST_PROGRESS.md'):row.update(source='generated_registry_snapshot_'+stamp,source_size_bytes=str(len(raw)),source_sha256=h)
  else:
   rel=dest.removeprefix('reports/deadline_submission_20261029/')
   if dest=='reports/CURRENT_CELL_LEDGER.csv':rel='planned_case_ledger.csv'
   row.update(source=str(Path(source_root)/rel),source_size_bytes=str(len(raw)),source_sha256=h)
 with fm.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\r\n');w.writeheader();w.writerows(rows)
 smp=REPO/'snapshot_manifest.json';sm=json.loads(smp.read_text());entries={x['path']:x for x in sm['entries']}
 for dest in repo_paths+['file_manifest.csv']:
  p=REPO/dest;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
  if dest not in entries:entries[dest]={'path':dest,'size_bytes':len(raw),'sha256':h};sm['entries'].append(entries[dest])
  else:entries[dest].update(size_bytes=len(raw),sha256=h)
 sm['entries']=sorted(sm['entries'],key=lambda x:x['path']);smp.write_text(json.dumps(sm,indent=2,sort_keys=True)+'\n')
 return ['file_manifest.csv','snapshot_manifest.json']
def try_publish_git(snapshot,stamp,counts,rows):
 status={'attempted':True,'published':False,'auth_probe':'not_checked','blocker':None,'commit':None,'remote_verified':False}
 remote=git_command('remote','get-url','origin',timeout=10)
 if remote.returncode or remote.stdout.strip().rstrip('/')!='https://github.com/S-G-mathematics/lamost-six-experiments.git':
  status.update(blocker='origin_unavailable_or_unexpected');return status
 auth=git_command('ls-remote','--heads','origin','main','results/snapshot-2026-10-28',timeout=20)
 status['auth_probe']='available' if auth.returncode==0 else 'unavailable_or_network_blocked'
 if auth.returncode:return status
 refs={z.split()[1]:z.split()[0] for z in auth.stdout.splitlines() if len(z.split())==2}
 if set(refs)!={'refs/heads/main','refs/heads/results/snapshot-2026-10-28'}:
  status.update(blocker='expected_remote_branches_missing');return status
 head=git_command('rev-parse','HEAD').stdout.strip()
 if any(v!=head for v in refs.values()):status.update(blocker='remote_heads_advanced');return status
 if git_command('branch','--show-current').stdout.strip()!='main' or git_command('status','--porcelain').stdout.strip():
  status.update(blocker='worktree_not_clean_main');return status
 changed=[]
 try:
  for q in sorted(snapshot.rglob('*')):
   if q.is_file():
    if q.name=='git_publication.json':continue
    dest='reports/deadline_submission_20261029/'+str(q.relative_to(snapshot))
    d=REPO/dest;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(q,d);changed.append(dest)
  cp=snapshot/'planned_case_ledger.csv';dest='reports/CURRENT_CELL_LEDGER.csv';shutil.copy2(cp,REPO/dest);changed.append(dest)
  refresh_readme(REPO/'README.md',stamp,counts,rows);changed.append('README.md')
  refresh_readme(REPO/'LATEST_PROGRESS.md',stamp,counts,rows);changed.append('LATEST_PROGRESS.md')
  changed+=update_file_manifests(changed,stamp,'runtime_20261025/reports/deadline_snapshot_'+stamp.replace(':','').replace('-',''))
  if git_command('-c','core.whitespace=cr-at-eol','diff','--check').returncode:
   status.update(blocker='git_diff_check_failed');return status
  if git_command('add','--',*sorted(set(changed))).returncode:
   status.update(blocker='git_add_failed');return status
  co=git_command('commit','-m','Refresh deadline interim report from SQLite snapshot',timeout=60)
  if co.returncode:status.update(blocker='git_commit_failed');return status
  commit=git_command('rev-parse','HEAD').stdout.strip();status['commit']=commit
  if git_command('push','origin','main',timeout=45).returncode:
   status.update(blocker='git_push_main_failed');return status
  if git_command('push','origin','HEAD:refs/heads/results/snapshot-2026-10-28',timeout=45).returncode:
   status.update(blocker='git_push_results_failed');return status
  verify=git_command('ls-remote','--heads','origin','main','results/snapshot-2026-10-28',timeout=20)
  verified_refs={z.split()[1]:z.split()[0] for z in verify.stdout.splitlines() if len(z.split())==2} if verify.returncode==0 else {}
  status['remote_verified']=set(verified_refs)=={'refs/heads/main','refs/heads/results/snapshot-2026-10-28'} and all(v==commit for v in verified_refs.values())
  status.update(published=status['remote_verified'],blocker=None if status['remote_verified'] else 'remote_ref_verification_failed')
  return status
 except Exception:
  status.update(blocker='git_publication_failed_after_preflight')
  return status
def build(args):
 now=dt.datetime.now(dt.timezone.utc);lo=dt.datetime(2026,10,29,10,45,tzinfo=dt.timezone.utc);hi=dt.datetime(2026,10,29,11,0,tzinfo=dt.timezone.utc)
 if not lo<=now<=hi:raise RuntimeError(f'Outside one-off window {lo.isoformat()}..{hi.isoformat()}; now={now.isoformat()}')
 if sha(BUILDER)!=BUILDER_SHA:raise RuntimeError('Pinned report builder changed; abort for review')
 lockpath=R/'locks/final_github_publisher.lock';lockfd=os.open(lockpath,os.O_RDWR|os.O_CREAT,0o600)
 try:fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('Existing Git publisher lock is held')
 registry,db_rows=capture_registry(R/'registry.sqlite')
 registry['registry_task_rows']=db_rows
 stamp=registry['observed_utc'];tag=dt.datetime.fromisoformat(stamp).astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 out=R/'reports'/('deadline_snapshot_'+tag)
 if out.exists():raise RuntimeError('Snapshot output already exists')
 safe_json=json.dumps(registry,sort_keys=True,separators=(',',':'))+'\n'
 safe_hash=hashlib.sha256(safe_json.encode()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='.deadline_work_'+tag+'_',dir=R/'reports') as td:
  work=Path(td);wr=work/'runtime_20261025';wr.mkdir()
  (wr/'source').symlink_to(R/'source',target_is_directory=True)
  (wr/'artifacts').symlink_to(R/'artifacts',target_is_directory=True)
  (wr/'reports').symlink_to(R/'reports',target_is_directory=True)
  (wr/'registry.json').write_text(safe_json,encoding='utf-8')
  if not (wr/'reports/deadline_submission_20261029/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md').is_file():
   raise RuntimeError('Pinned report template is unavailable in isolated builder runtime')
  source=BUILDER.read_text(encoding='utf-8');needle="R=ROOT/'runtime_20261025'"
  if source.count(needle)!=1:raise RuntimeError('Could not isolate pinned report builder runtime path')
  adapter=source.replace(needle,"R=Path(os.environ['LAMOST_REPORT_SNAPSHOT_RUNTIME'])",1)
  adapter_path=work/'report_builder_snapshot_adapter.py';adapter_path.write_text(adapter,encoding='utf-8')
  builder_env=os.environ.copy();builder_env['LAMOST_REPORT_SNAPSHOT_RUNTIME']=str(wr)
  subprocess.check_call([sys.executable,str(adapter_path),'--output',str(out)],env=builder_env)
  rp=out/'DEADLINE_INTERIM_SCIENTIFIC_REPORT.md';text=rp.read_text(encoding='utf-8')
  text=re.sub(r'\n\n### Snapshot history\n.*\Z','',text,flags=re.S)
  text+=f'\n\n### Snapshot provenance\nThis report uses one read-only SQLite task-table transaction observed at {stamp} UTC. Registry changes after this cutoff are not folded into this snapshot; subsequent evaluations remain later project progress.'
  rp.write_text(text,encoding='utf-8')
  rows=list(csv.DictReader((out/'planned_case_ledger.csv').open(newline='',encoding='utf-8')))
  counts=validate_rows(rows)
  rec=json.loads((out/'submission_receipt.json').read_text())
  if rec.get('planned_cases')!=sum(EXPECTED.values()) or rec.get('successful_cases_missing_metric_json'):raise RuntimeError('Report builder receipt gate failed')
  input_rows=list(csv.DictReader((out/'evaluation_input_hashes.csv').open(newline='',encoding='utf-8')))
  for row in input_rows:
   key=row['task_key']
   if '..' in Path(key).parts or Path(key).is_absolute():raise RuntimeError('Unsafe key in evaluation ledger')
   p=R/'artifacts'/key/'evaluation.json'
   if not p.is_file() or sha(p)!=row['sha256']:raise RuntimeError('Captured evaluation JSON mismatch: '+key)
  capture={'source_database':'runtime_20261025/registry.sqlite','read_mode':'read-only SQLite transaction on tasks','observed_utc':stamp,'database_task_rows':db_rows,'scientific_case_rows':len(registry['tasks']),'sanitized_registry_sha256':safe_hash,'process_receipts_in_snapshot':False,'post_cutoff_updates_allowed':True}
  side=out/'snapshot_provenance';side.mkdir()
  (side/'registry_snapshot_sanitized.json').write_text(safe_json,encoding='utf-8')
  (side/'report_builder_snapshot_adapter.py').write_text(adapter,encoding='utf-8')
  (side/'snapshot_capture.json').write_text(json.dumps(capture,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  rec['coherent_sqlite_snapshot']=capture;rec['report_builder_source_sha256']=BUILDER_SHA
  rec['runtime_adapter_sha256']=sha(side/'report_builder_snapshot_adapter.py')
  rec['outputs']=[]
  for p in sorted(out.rglob('*')):
   if p.is_file() and p.name!='submission_receipt.json':rec['outputs'].append({'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)})
  rec['successful_cases_missing_metric_json']=[]
  (out/'submission_receipt.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
  for row in input_rows:
   p=R/'artifacts'/row['task_key']/'evaluation.json'
   if not p.is_file() or sha(p)!=row['sha256']:raise RuntimeError('Captured evaluation changed during report build: '+row['task_key'])
  # Publish the authorized interim snapshot only if the existing private repo passes
  # noninteractive auth, clean-tree, publisher-lock, and fast-forward preconditions.
  gitpub=try_publish_git(out,stamp,counts,rows)
  (out/'git_publication.json').write_text(json.dumps(gitpub,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  rec['git_publication']=gitpub
  rec['outputs']=[]
  for p in sorted(out.rglob('*')):
   if p.is_file() and p.name!='submission_receipt.json':rec['outputs'].append({'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)})
  (out/'submission_receipt.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  headproc=git_command('rev-parse','HEAD');repo_head=headproc.stdout.strip() if headproc.returncode==0 else None
  statproc=git_command('status','--porcelain');repo_prov=repository_payload_provenance(repo_head,statproc.stdout,statproc.returncode==0)
  repo_clean=repo_prov['repo_worktree_clean'];payload_basis=repo_prov['repo_payload_basis']
  gitpub.update(repo_prov)
  (out/'git_publication.json').write_text(json.dumps(gitpub,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  rec['git_publication']=gitpub
  rec['outputs']=[]
  for p in sorted(out.rglob('*')):
   if p.is_file() and p.name!='submission_receipt.json':rec['outputs'].append({'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)})
  (out/'submission_receipt.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  commit=gitpub.get('commit') if repo_clean and gitpub.get('published') else None
  git_auth='available' if gitpub.get('auth_probe')=='available' else 'unavailable_or_network_blocked'
  names,exclusions=public_members();pkg=R/'packages';pkg.mkdir(exist_ok=True)
  package_ref=(commit or repo_head or 'workingtree')[:8]
  filename=f'LAMOST_SIX_EXPERIMENTS_DEADLINE_INTERIM_{tag}_{package_ref}.zip'
  zpath=pkg/filename
  if zpath.exists():raise RuntimeError('Package path exists')
  readme=pkg/('.'+filename+'.README.tmp')
  lines=['# LAMOST six-experiment deadline snapshot','',f'Registry snapshot: {stamp} UTC. Git publication commit: {commit or "none verified"}. HEAD reference: {repo_head or "unavailable"}. Payload commit reference: {repo_prov["payload_commit_reference"] or "none (dirty/unverified worktree)"}. Worktree clean at package capture: {repo_clean}. Payload basis: {payload_basis}; each included file is bound by SHA/size. Auth probe: {git_auth}.','**INTERIM DELIVERY - project completion and final validation are not claimed.**','',
   '| Experiment | Planned | Successful/evaluated | Scientific failures | Unsupported | Unavailable | User-stopped | Operationally interrupted | Operationally invalid | Packaging pending | Waiting/active |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
  for label,e in [('E3',3),('E4',4),('E5',5),('E6 all ledger rows',6)]:
   x=counts[e];v=visible_states(x);lines.append(f'| {label} | {EXPECTED[e]} | {v["successful"]} | {v["scientific_failures"]} | {v["unsupported"]} | {v["unavailable"]} | {v["user_stopped"]} | {v["operationally_interrupted"]} | {v["operationally_invalid"]} | {v["packaging_pending"]} | {v["waiting_or_active"]} |')
  lines+=['','Frozen E1 remains 765 terminal: 674 successful, 81 failed (55 resource; 26 supervisor-terminal manifests remained started), and 10 unsupported. Separate recovery remains stopped: 24 successful, 10 retry failures, 2 user-stopped, 55 not attempted.','E2 remains 108/150 primary with 42 unavailable and a separate 120/120 classical-reference set. Reconstruction provenance, low-precision class reports and four descriptive complete strata remain disclosed.','E6 member-reference aliases are separate from primary ensembles. Operational interruptions, invalid states, and user-stopped rows are not scientific failures. No bootstrap or unsupported significance claims are made.','Current snapshot includes the complete E3-E6 case ledger, validated metrics, paired tables, class metrics, confusion counts, status SVG, and sanitized SQLite snapshot provenance. Other component figures retain their documented cutoffs.','No fitted models, FITS, raw datasets, prediction/calibration arrays, credentials, private process receipts, operational logs or Harbor material are included.','The full EC2 archive and final native calibration/artifact audit remain pending.','']
  readme.write_text('\n'.join(lines),encoding='utf-8')
  sources=[]
  for p in sorted(out.rglob('*')):
   if p.is_file():sources.append((p,'current_snapshot/'+str(p.relative_to(out))))
  for name in names:sources.append((REPO/name,'repository/'+name))
  sources.append((readme,'README.md'))
  for source_path,dest in sources:safe_member(dest)
  members=[]
  for source_path,dest in sources:
   if source_path.stat().st_size>90*1024*1024:raise RuntimeError('Archive member exceeds 90 MiB: '+dest)
   members.append({'path':dest,'bytes':source_path.stat().st_size,'sha256':sha(source_path)})
  manifest={'schema':'lamost-deadline-interim-delivery/1','status':'interim','observed_utc':stamp,'sanitized_registry_sha256':safe_hash,'git_publication_commit':commit,'git_head_reference':repo_head,'repo_worktree_clean':repo_clean,'payload_commit_reference':repo_prov['payload_commit_reference'],'repository_payload_basis':payload_basis,'git_auth_probe':git_auth,'planned':EXPECTED,'states':{str(e):dict(counts[e]) for e in counts},'repository_payload_manifest_is_member_hash_list':True,'members':members,'excluded_categories':exclusions,'self_hash_note':'delivery_manifest.json is bound by external ZIP SHA receipt'}
  mp=pkg/('.'+filename+'.manifest.tmp');mp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');sources.append((mp,'delivery_manifest.json'))
  try:
   with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for source_path,dest in sources:z.write(source_path,dest)
   with zipfile.ZipFile(zpath) as z:
    bad=z.testzip()
    if bad:raise RuntimeError('ZIP CRC failure: '+bad)
    z_names=z.namelist()
    if len(z_names)!=len(set(z_names)):raise RuntimeError('Duplicate member paths')
    expected_members={m['path']:(m['bytes'],m['sha256']) for m in members}
    for info in z.infolist():
     if info.filename=='delivery_manifest.json':continue
     expected=expected_members.get(info.filename)
     if expected is None:raise RuntimeError('ZIP member missing from hash manifest: '+info.filename)
     h=hashlib.sha256();size=0
     with z.open(info,'r') as stream:
      for block in iter(lambda:stream.read(1024*1024),b''):
       h.update(block);size+=len(block)
     if (size,h.hexdigest())!=expected:raise RuntimeError('ZIP member does not match captured manifest: '+info.filename)
   if len(expected_members)!=len(z_names)-1:raise RuntimeError('ZIP manifest/member count mismatch')
   sidecar={'status':'verified_interim_snapshot','zip_path':str(zpath),'zip_bytes':zpath.stat().st_size,'zip_sha256':sha(zpath),'crc_test':'passed','member_count':len(z_names),'observed_utc':stamp,'sanitized_registry_sha256':safe_hash,'git_publication_commit':commit,'git_head_reference':repo_head,'repo_worktree_clean':repo_clean,'payload_commit_reference':repo_prov['payload_commit_reference'],'repository_payload_basis':payload_basis,'git_auth_probe':git_auth,'counts':{str(e):dict(counts[e]) for e in counts},'full_project_complete':False}
   Path(str(zpath)+'.receipt.json').write_text(json.dumps(sidecar,indent=2,sort_keys=True)+'\n')
   Path(str(zpath)+'.sha256').write_text(sidecar['zip_sha256']+'  '+zpath.name+'\n')
   print(json.dumps(sidecar,separators=(',',':')))
  finally:
   for q in (readme,mp):
    try:q.unlink()
    except FileNotFoundError:pass
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--self-test',action='store_true');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 if a.self_test:self_test();return
 if not a.execute:ap.error('Use --self-test or --execute')
 build(a)
if __name__=='__main__':main()
