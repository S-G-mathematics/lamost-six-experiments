"""Read-only lightweight EC2 progress observation; no heartbeat-based liveness."""
from pathlib import Path
import json,sqlite3,datetime,zoneinfo,os,hashlib,argparse
import controller as controller_api
R=Path(__file__).resolve().parents[1]
controller_api.R=R
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(t):
 try:
  p=Path('/proc')/str(t['pid']);tail=(p/'stat').read_text().rpartition(')')[2].split()
  args=[x for x in (p/'cmdline').read_bytes().decode(errors='replace').split('\0') if x]
  if tail[19]!=str(t.get('process_start_ticks')):return False
  cwd=(p/'cwd').resolve()
  scripts=[(cwd/a).resolve() for a in args[1:] if a.endswith('.py')]
  if tail[0] in ('Z','X','x'):return False
  uid=int(next(x.split()[1] for x in (p/'status').read_text().splitlines() if x.startswith('Uid:')))
  if uid!=os.getuid() or t.get('request_path') not in args:return False
  request=Path(t['request_path'])
  if request.is_symlink() or not request.is_file():return False
  cfg=json.loads(request.read_text())
  expected=controller_api.worker_script_for_task(cfg['task'],cfg.get('execution_policy'),cfg.get('resource_profile'))
  if expected not in scripts or cfg.get('result_path')!=t.get('result_path'):return False
  return cfg['task']['key']==t['key'] and cfg['attempt_id']==t['attempts'][-1]['attempt_id']
 except (OSError,KeyError,ValueError,IndexError,TypeError,RuntimeError):return False
def observe(by_rep=False):
 db=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True)
 db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
 # Aggregate JSON in SQLite so the observer does not materialize all 6,270 nested records.
 state="CASE WHEN json_extract(record,'$.status')='validated_terminal' THEN coalesce(json_extract(record,'$.outcome'),'validated_terminal') ELSE json_extract(record,'$.status') END"
 out={}
 for e,s,n in db.execute("SELECT json_extract(record,'$.experiment'),"+state+",count(*) FROM tasks WHERE json_extract(record,'$.scientific_case')=1 GROUP BY 1,2"):
  out.setdefault(str(e),{})[s]=n
 running=[json.loads(v) for (v,) in db.execute("SELECT record FROM tasks WHERE json_extract(record,'$.status')='running'")]
 count=db.execute('select count(*) from tasks').fetchone()[0]
 reps={}
 if by_rep:
  for e,rep,s,n in db.execute("SELECT json_extract(record,'$.experiment'),json_extract(record,'$.rep'),"+state+",count(*) FROM tasks WHERE json_extract(record,'$.scientific_case')=1 GROUP BY 1,2,3"):
   reps.setdefault(str(e),{}).setdefault(str(rep),{})[s]=n
 db.close()
 workers=[];unverified=[]
 for t in running:
  if identity(t):
   workers.append({'key':t['key'],'kind':t.get('kind'),'elapsed_s':round(datetime.datetime.now().timestamp()-float(t.get('started_epoch',datetime.datetime.now().timestamp())),1),'admission_profile_id':t.get('admission_profile_id'),'reservation_gib':int(t.get('admission_reservation_bytes',0))/1024**3})
  else:unverified.append(t['key'])
 owner=json.loads((R/'owner.json').read_text());verified=False
 try:
  p=Path('/proc')/str(owner['pid']);args=(p/'cmdline').read_bytes().decode().split('\0');cwd=(p/'cwd').resolve()
  verified=((p/'stat').read_text().rpartition(')')[2].split()[19]==str(owner['process_start_ticks']) and any((cwd/a).resolve()==R/'source/controller.py' for a in args[1:] if a.endswith('.py')) and owner.get('code_sha256')==sha(R/'source/controller.py'))
 except (OSError,KeyError,IndexError):pass
 mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
 disk=os.statvfs(R);now=datetime.datetime.now(datetime.timezone.utc)
 result={'observed_utc':now.isoformat(),'observed_ist':now.astimezone(zoneinfo.ZoneInfo('Asia/Kolkata')).isoformat(),'instance_dmi':Path('/sys/devices/virtual/dmi/id/board_asset_tag').read_text().strip(),'dag_tasks':count,'scientific_outcomes':out,'controller_actual_verified':verified,'controller_sha256':owner.get('code_sha256'),'workers_actual_verified':workers,'registry_running_unverified_at_observation':unverified,'available_ram_gib':round(mem/1024**3,2),'disk_free_gib':round(disk.f_bavail*disk.f_frsize/1024**3,2),'holds':[p.name for p in R.glob('*HOLD*')]}
 storage={'status':'unknown','hold_marker_present':(R/'STORAGE_HOLD.json').exists(),'note':'Storage marker is historical evidence, not a scheduling lock; controller uses free bytes and its current conservative input estimate.'}
 try:
  so=json.loads((R/'storage_observation.json').read_text());age=(now-datetime.datetime.fromisoformat(so['observed_utc'])).total_seconds();minimum=int(so['minimum_free_bytes']);free=disk.f_bavail*disk.f_frsize
  storage.update({'observed_utc':so['observed_utc'],'observation_age_seconds':round(age,2),'free_bytes_now':free,'minimum_free_bytes_from_controller':minimum,'headroom_bytes':free-minimum,'estimate_refresh_interval_seconds':300,'status':'allowed_by_current_recorded_estimate' if 0<=age<=15 and free>=minimum else 'backoff_by_current_recorded_estimate' if 0<=age<=15 else 'observation_stale_or_future'})
 except (OSError,ValueError,KeyError,TypeError):pass
 result['storage_admission_observation']=storage
 if by_rep:result['per_repetition_scientific_outcomes']=reps
 return result
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--by-rep',action='store_true');args=ap.parse_args()
 print(json.dumps(observe(args.by_rep),sort_keys=True))
