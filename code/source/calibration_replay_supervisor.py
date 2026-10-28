import datetime,hashlib,json,math,os,signal,subprocess,time,uuid
from pathlib import Path
GIB=1024**3; PHASE_LIMIT=600; TREE_LIMIT=10*GIB; GRACE=30; POLL=.1
def load(p): return json.loads(Path(p).read_text())
def atomic_json(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+".tmp."+str(os.getpid()))
 with tmp.open("w") as f: json.dump(d,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(p.parent,os.O_RDONLY)
 try: os.fsync(fd)
 finally: os.close(fd)
def proc(pid):
 b=Path("/proc")/str(int(pid))
 try:
  stat=b.joinpath("stat").read_text();tail=stat[stat.rfind(")")+1:].split()
  status=b.joinpath("status").read_text()
  uid=int(next(x.split()[1] for x in status.splitlines() if x.startswith("Uid:")))
  rss=int(next(x.split()[1] for x in status.splitlines() if x.startswith("VmRSS:")))*1024
  cmd=[x.decode(errors="replace") for x in b.joinpath("cmdline").read_bytes().split(b"\0") if x]
  return {"pid":int(pid),"ppid":int(tail[1]),"pgrp":int(tail[2]),"ticks":int(tail[19]),"uid":uid,"rss":rss,"cmd":cmd}
 except (OSError,StopIteration,ValueError,IndexError): return None
def identity(pid,ticks,uid,runtime,script,python):
 x=proc(pid)
 if not (x and x["ticks"]==ticks and x["uid"]==uid and str(script) in x["cmd"] and str(runtime) in x["cmd"] and "--require-calibration-replay" in x["cmd"] and "--replay-run-nonce" in x["cmd"]):return False
 try:exe=os.readlink("/proc/"+str(pid)+"/exe")
 except OSError:return False
 return x["cmd"][0]==str(python) and Path(exe).resolve()==Path(python).resolve()
def process_identity_state(p,pid,ticks,uid,runtime,script,python):
 if identity(pid,ticks,uid,runtime,script,python):return "valid"
 # A poll at loop entry can race with normal child exit before /proc is sampled.
 # Re-poll before classifying the vanished /proc identity as an unexpected change.
 return "exited" if p.poll() is not None else "invalid"

# Popen may return before the forked child has completed exec and published its
# final /proc cmdline/executable/RSS. Startup is bounded separately from the
# scientific phase clock; no signal is sent until full identity is verified.
STARTUP_IDENTITY_GRACE=2.0
STARTUP_IDENTITY_POLL=.02
def proc_seed(pid):
 b=Path("/proc")/str(int(pid))
 try:
  stat=b.joinpath("stat").read_text();tail=stat[stat.rfind(")")+1:].split()
  status=b.joinpath("status").read_text()
  uid=int(next(x.split()[1] for x in status.splitlines() if x.startswith("Uid:")))
  return int(tail[19]),uid
 except (OSError,StopIteration,ValueError,IndexError):return None
def wait_for_startup_identity(p,pid,runtime,script,python,grace=STARTUP_IDENTITY_GRACE):
 expected_uid=os.getuid();deadline=time.monotonic()+grace;seed=None
 while True:
  if p.poll() is not None:raise RuntimeError("auditor exited before startup identity verified")
  current=proc_seed(pid)
  if current is not None:
   if seed is None:
    if current[1]!=expected_uid:raise RuntimeError("auditor UID differs from launching supervisor during startup")
    seed=current
   elif current!=seed:raise RuntimeError("auditor PID/start-tick/UID changed during startup")
   if identity(pid,seed[0],seed[1],runtime,script,python):
    try:group=os.getpgid(pid)
    except OSError:group=None
    if group!=pid:raise RuntimeError("auditor process group is invalid after startup identity verification")
    return seed
  now=time.monotonic()
  if now>=deadline:raise RuntimeError("auditor startup identity was not verified within %.3f seconds; no signal sent"%grace)
  time.sleep(min(STARTUP_IDENTITY_POLL,deadline-now))

def expected_replay_rows(audit):
 """Normalize ordinary replay rows and native E6 member rows for external phase binding."""
 rows=[r for r in audit.get("records",[]) if isinstance(r,dict) and r.get("fit_key") and "source_key" not in r]
 for r in audit.get("e6_member_calibration_records",[]):
  if not isinstance(r,dict):raise RuntimeError("E6 member replay record is not an object")
  if r.get("status")!="validated":continue
  required=("task_key","fit_key","native_replay_identity","native_replay_metadata_sha256","native_replay_vector_file_sha256")
  if any(not isinstance(r.get(k),str) or len(r[k])!=64 for k in required[2:]) or not all(isinstance(r.get(k),str) and r[k] for k in required[:2]):
   raise RuntimeError("validated E6 member replay lacks task/fit/vector identity")
  rows.append({"task_key":r["task_key"],"fit_key":r["fit_key"],"identity":r["native_replay_identity"],
    "metadata_sha256":r["native_replay_metadata_sha256"],"nonconformity_file_sha256":r["native_replay_vector_file_sha256"],
    "supervision_mode":"replayed","e6_member":r.get("member")})
 return rows

def audit_coverage_rejects(audit):
 # E6-v2 adds supplemental q coverage. Legacy reports have no E6 scope and
 # retain the original generic replay contract; explicit false always fails.
 e6_scope=(int(audit.get("required_e6_ensembles") or 0)>0
           or bool(audit.get("e6_member_calibration_records"))
           or bool(audit.get("e6_ensemble_calibration_records")))
 if "q_replay_coverage_complete" in audit:
  return audit.get("q_replay_coverage_complete") is not True
 return e6_scope

def tree_rss(root):
 allp={}
 for e in Path("/proc").iterdir():
  if e.name.isdigit():
   x=proc(int(e.name))
   if x: allp[x["pid"]]=x
 if root not in allp:return 0
 ids={root}|{pid for pid,x in allp.items() if x.get("pgrp")==root}
 while True:
  more={pid for pid,x in allp.items() if x["ppid"] in ids}; nxt=ids|more
  if nxt==ids:break
  ids=nxt
 return sum(allp[n]["rss"] for n in ids if n in allp)
def stop_verified(p,pid,ticks,uid,runtime,script,python):
 if not identity(pid,ticks,uid,runtime,script,python):return False
 try:
  if os.getpgid(pid)!=pid:return False
  os.killpg(pid,signal.SIGTERM)
 except OSError:return False
 until=time.monotonic()+GRACE
 while time.monotonic()<until:
  if not identity(pid,ticks,uid,runtime,script,python):return True
  time.sleep(.1)
 if not identity(pid,ticks,uid,runtime,script,python):return True
 try:os.killpg(pid,signal.SIGKILL);return True
 except OSError:return False
def run(runtime,python,script,run_nonce=None,accepted_prior_index=None):
 runtime=Path(runtime).resolve();python=Path(os.path.abspath(python));script=Path(script).resolve()
 reports=runtime/"reports";ops=runtime/"logs"/"operational";reports.mkdir(parents=True,exist_ok=True);ops.mkdir(parents=True,exist_ok=True)
 audit_path=reports/"CALIBRATION_REPLAY_AUDIT.json";beacon=ops/"calibration_replay_supervisor_beacon.json"
 run_nonce=run_nonce or uuid.uuid4().hex
 if not isinstance(run_nonce,str) or len(run_nonce)<16 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in run_nonce):raise RuntimeError("supervisor run nonce is invalid")
 ledger=ops/("calibration_replay_phase_ledger_"+run_nonce+".jsonl")
 if ledger.exists():raise RuntimeError("unique phase ledger path already exists")
 old=hashlib.sha256(audit_path.read_bytes()).hexdigest() if audit_path.is_file() else None
 if ledger.exists():raise RuntimeError("unique phase ledger path already exists")
 env=os.environ.copy();env["LAMOST_CAL_REPLAY_RUN_NONCE"]=run_nonce
 for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):env[k]="1"
 logfile=ops/("calibration_replay_auditor_"+uuid.uuid4().hex+".log")
 phases=[];active=None;nonce=run_nonce;peak=0;failure=None;term="none"
 with logfile.open("wb") as log:
  argv=[str(python),str(script),"--runtime",str(runtime),"--require-calibration-replay","--replay-run-nonce",run_nonce]
  if accepted_prior_index is not None:
   accepted_prior_index=Path(accepted_prior_index).resolve()
   if runtime/"reports" not in accepted_prior_index.parents or not accepted_prior_index.is_file():raise RuntimeError("accepted prior replay index is missing or outside reports")
   argv.extend(["--accepted-prior-replay-receipts",str(accepted_prior_index)])
  p=subprocess.Popen(argv,stdout=log,stderr=log,env=env,start_new_session=True,close_fds=True)
  pid=p.pid
  try:
   ticks,uid=wait_for_startup_identity(p,pid,runtime,script,python)
  except Exception:
   # The child has not passed the exact identity gate, so never signal its PID.
   # Allow its normal startup/exit path a short bounded interval and leave any
   # still-live, unverifiable child explicit for operator recovery.
   if p.poll() is None:
    try:p.wait(timeout=STARTUP_IDENTITY_GRACE)
    except subprocess.TimeoutExpired:raise RuntimeError("startup identity remained unverifiable; child not signaled")
   raise
  begin=time.monotonic()
  def finish(at,termination="none"):
   nonlocal active
   if active is None:return
   d=max(0.,at-active["start"]);active["duration_seconds"]=d
   active["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
   active["status"]="passed" if termination=="none" and d<=PHASE_LIMIT and active["peak_process_tree_rss_bytes"]<=TREE_LIMIT else "failed"
   active["termination"]=termination;phases.append(active);active=None
  while p.poll() is None:
   now=time.monotonic()
   identity_state=process_identity_state(p,pid,ticks,uid,runtime,script,python)
   if identity_state=="exited":break
   if identity_state=="invalid":failure="auditor process identity changed";term="identity_failure";break
   rss=tree_rss(pid);peak=max(peak,rss)
   if rss>TREE_LIMIT:failure="auditor process tree exceeded 10 GiB sampled RSS";term="rss_limit";break
   try:b=load(beacon)
   except Exception:b=None
   now=time.monotonic()
   valid=isinstance(b,dict) and b.get("schema_version")=="lamost-calibration-replay-private-beacon/1" and b.get("pid")==pid and b.get("process_start_ticks")==ticks
   if valid:
    if b.get("run_nonce")!=nonce:failure="beacon run nonce changed";term="identity_failure";break
    if nonce and b.get("state")=="running":
     fit=b.get("current_fit_key");task=b.get("current_task_key")
     try:phase_start=float(b.get("phase_started_monotonic"))
     except Exception:phase_start=None
     if not isinstance(fit,str) or phase_start is None or not math.isfinite(phase_start) or phase_start>now:failure="invalid running phase beacon";term="identity_failure";break
     if active is None or active["fit_key"]!=fit or active["phase_start"]!=phase_start:
      finish(now);active={"fit_key":fit,"run_nonce":nonce,"phase_start":phase_start,"start":phase_start,"started_utc":b.get("phase_started_utc"),"task_keys":set(),"peak_process_tree_rss_bytes":0}
     if task:active["task_keys"].add(task)
     active["peak_process_tree_rss_bytes"]=max(active["peak_process_tree_rss_bytes"],rss)
     if now-active["start"]>PHASE_LIMIT:failure="scoring phase exceeded 600 seconds";term="timeout";break
     if rss>TREE_LIMIT:failure="process tree exceeded 10 GiB sampled RSS";term="rss_limit";break
    elif nonce and b.get("state")=="idle":finish(now)
   if now-begin>72*3600:failure="auditor exceeded operational bound";term="operational_timeout";break
   time.sleep(POLL)
  if failure:
   stopped=stop_verified(p,pid,ticks,uid,runtime,script,python)
   if stopped:p.wait(timeout=GRACE+5)
   finish(time.monotonic(),term)
   if p.poll() is None:raise RuntimeError("verified auditor did not stop within grace")
  else:
   p.wait();finish(time.monotonic())
  remaining=[x["pid"] for x in (proc(int(e.name)) for e in Path("/proc").iterdir() if e.name.isdigit()) if x and x.get("pgrp")==pid]
  if remaining:failure="auditor process group retained descendants after exit";term="identity_failure"
  if nonce is None:raise RuntimeError("no private beacon matched launched auditor")
  audit=load(audit_path) if audit_path.is_file() else {}
  audit_sha=hashlib.sha256(audit_path.read_bytes()).hexdigest() if audit_path.is_file() else None
  if audit_sha==old or audit.get("replay_run_nonce")!=nonce:
   raise RuntimeError(f"no qualified calibration replay report; no checks skipped; parent_failure={failure!r}; termination={term}; auditor_exit={p.returncode}")
  if audit_coverage_rejects(audit):
   raise RuntimeError("auditor calibration replay coverage is incomplete; external supervision cannot qualify it")
  if audit.get("phase_ledger_path")!=ledger.relative_to(runtime).as_posix():raise RuntimeError("audit phase-ledger path does not bind this run")
  ledger_bytes=ledger.read_bytes();ledger_sha=hashlib.sha256(ledger_bytes).hexdigest()
  if audit.get("phase_ledger_sha256")!=ledger_sha:raise RuntimeError("audit phase-ledger digest mismatch")
  events={}
  for raw in ledger_bytes.splitlines():
   if not raw:continue
   event=json.loads(raw)
   if event.get("schema_version")!="lamost-calibration-replay-phase-ledger/1" or event.get("run_nonce")!=nonce:raise RuntimeError("phase ledger schema/nonce mismatch")
   if event.get("pid")!=pid or event.get("process_start_ticks")!=ticks:raise RuntimeError("phase ledger PID/start-tick differs from launched auditor")
   if json.dumps(event,sort_keys=True,separators=(",",":")).encode()!=raw:raise RuntimeError("phase ledger line is not canonical JSON")
   phase_id=event.get("phase_id");event_type=event.get("event")
   if not isinstance(phase_id,str) or event_type not in {"start","finish"}:raise RuntimeError("phase ledger event ID/type is invalid")
   key=(phase_id,event_type)
   if key in events:raise RuntimeError("duplicate phase ledger event")
   events[key]={"event":event,"sha256":hashlib.sha256(raw).hexdigest()}
  phases_by_id={}
  for (phase_id,event_type),record in events.items():phases_by_id.setdefault(phase_id,{})[event_type]=record
  if not phases_by_id or any(set(pair)!={"start","finish"} for pair in phases_by_id.values()):raise RuntimeError("phase ledger is missing a start or finish event")
  byfit={}
  audit_physical=expected_replay_rows(audit)
  for r in audit_physical:
   if r.get("identity") and r.get("supervision_mode") in {"replayed","cache_reuse"}:
    byfit.setdefault(r["fit_key"],[]).append(r)
  phase_records=[]
  sample_by_fit={}
  for z in phases:sample_by_fit[z["fit_key"]]=max(sample_by_fit.get(z["fit_key"],0),z.get("peak_process_tree_rss_bytes",0))
  for phase_id,pair in sorted(phases_by_id.items(),key=lambda item:float(item[1]["start"]["event"]["monotonic"])):
   a=pair["start"]["event"];b=pair["finish"]["event"]
   for key in ("mode","phase","fit_key","task_keys","prior_receipts"):
    if a.get(key)!=b.get(key):raise RuntimeError("phase ledger start/finish fields disagree: "+key)
   try:start_mono=float(a["monotonic"]);finish_mono=float(b["monotonic"])
   except Exception as exc:raise RuntimeError("phase ledger monotonic fields invalid") from exc
   duration=finish_mono-start_mono
   if not math.isfinite(duration) or duration<0:raise RuntimeError("phase duration invalid")
   mode=a.get("mode");fitkey=a.get("fit_key")
   if mode not in {"replayed","cache_reuse"} or not isinstance(fitkey,str):raise RuntimeError("phase mode/fit key invalid")
   rows=sorted(byfit.get(fitkey,[]),key=lambda x:x["task_key"])
   bindings=[]
   for row in rows:
    bind={"task_key":row["task_key"],"fit_key":fitkey,"identity":row["identity"],"metadata_sha256":row["metadata_sha256"],
      "nonconformity_file_sha256":row["nonconformity_file_sha256"]}
    if mode=="cache_reuse":bind["prior_receipt_sha256"]=row.get("prior_receipt_sha256")
    bindings.append(bind)
   expected_tasks=sorted(x["task_key"] for x in audit_physical if x.get("fit_key")==fitkey and x.get("task_key"))
   if sorted(a.get("task_keys",[]))!=expected_tasks:raise RuntimeError("ledger task membership differs from all audited evaluations")
   measured=sample_by_fit.get(fitkey,peak)
   prior_receipts=a.get("prior_receipts") or {}
   phase={"phase_id":phase_id,"mode":mode,"phase":"calibration_score_replay" if mode=="replayed" else "cache_reuse",
     "fit_key":fitkey,"task_keys":expected_tasks,"run_nonce":nonce,"status":"passed" if duration<=PHASE_LIMIT and measured<=TREE_LIMIT else "failed",
     "started_utc":a.get("utc"),"finished_utc":b.get("utc"),"duration_seconds":duration,
     "measurement_method":"sampled /proc process-tree VmRSS every 100ms; whole-audit peak used when a phase is shorter than the sample interval",
     "peak_process_tree_rss_bytes":measured,"process_identity_verified":True,
     "cap_enforced":duration<=PHASE_LIMIT and measured<=TREE_LIMIT,"exit_code":p.returncode,
     "phase_start_event_sha256":pair["start"]["sha256"],"phase_finish_event_sha256":pair["finish"]["sha256"],
     "identity_bindings":bindings}
   if mode=="cache_reuse":
    prior_values=set(prior_receipts.values());phase["prior_receipt_sha256"]=next(iter(prior_values)) if len(prior_values)==1 else None
    phase["artifact_integrity_verified"]=bool(bindings)
   phase_records.append(phase)
  expected={(row.get("task_key"),row.get("fit_key")) for row in audit_physical if row.get("identity") and row.get("supervision_mode") in {"replayed","cache_reuse"}}
  observed={(bind.get("task_key"),bind.get("fit_key")) for phase in phase_records for bind in phase.get("identity_bindings",[])}
  ok=not failure and p.returncode==0 and observed==expected and bool(phase_records) and all(z["status"]=="passed" for z in phase_records)
  receipt={"schema_version":"lamost-calibration-replay-supervision/1","status":"complete" if ok else "partial",
   "generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"run_nonce":nonce,"audit_sha256":audit_sha,
   "registry_snapshot_sha256":audit.get("registry_snapshot_sha256"),"phase_ledger_sha256":ledger_sha,
   "accepted_prior_receipts_index_sha256":audit.get("accepted_prior_receipts_index_sha256"),
   "audit_process_exit_code":p.returncode,"audit_process_exit_verified":p.poll() is not None,
   "finalized_after_audit_exit":p.poll() is not None,"limits":{"wall_seconds":PHASE_LIMIT,"rss_bytes":TREE_LIMIT},
   "process_tree_peak_rss_bytes":peak,"termination":term,"failure_reason":failure,"phase_records":phase_records}
  atomic_json(reports/"CALIBRATION_REPLAY_SUPERVISION.json",receipt)
  if not ok:raise RuntimeError("external replay supervision did not pass: "+str(failure or p.returncode))
  return receipt

