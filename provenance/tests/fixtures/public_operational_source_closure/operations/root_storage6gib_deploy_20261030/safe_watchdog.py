#!/usr/bin/env python3
"""Fail-closed staged 5-minute recovery wrapper; no signals or direct fitting."""
import contextlib,fcntl,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]; R=ROOT/"runtime_20261025"; O=ROOT/"operations/root_storage6gib_deploy_20261030"
DEPLOY=O/"state.json"; ENABLE=O/"watchdog_enable.json"; HOLD=R/"WATCHDOG_START_HOLD.json"
COUNTER=O/"safe_watchdog_state.json"; LOCK=O/"safe_watchdog.instance.lock"; LOG=O/"safe_watchdog.log"
HELPER=ROOT/"operations/terminal_result_retention_v2_20261030/source/terminal_result_retention_v2.py"
HELPER_SHA="91250c7ff7d6da84dbbe03bda7161d9f6b02e974312f9b7e0d2c636d1f28c010"
CTRL=R/"source/controller.py"; FREEZE=R/"manifests/freeze.json"; OWNER=R/"owner.json"; OWNER_LOCK=R/"owner.lock"; RUN=R/"run_controller.sh"
GIB=1<<30; MAX_RECOVERIES=2; POLICY="working-reserve-6gib-one-fit-v1"
CTRL_NAMES=("controller.py","run_controller.py"); EXTRA_WORKERS=("e6_phase_supervisor.py",)
STORAGE={"policy_id":POLICY,"working_reserve_bytes":6*GIB,"maximum_concurrent_fit_tasks":1}
SCIENCE={"worker_memory_limit_gib":10,"trial_timeout_seconds":600,"phase_timeout_seconds":600,"termination_grace_seconds":30,"nested_threads":1,"prediction_chunk_rows":50000}
NONTERMINAL={"planned","waiting_dependency","waiting_for_dependency","queued","dispatching","running","worker_active","validating","operationally_interrupted"}

class Backoff(RuntimeError): pass

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def readj(p):
 p=pathlib.Path(p)
 if p.is_symlink() or not p.is_file():raise Backoff("missing/unsafe "+p.name)
 try:v=json.loads(p.read_text())
 except Exception as e:raise Backoff("malformed "+p.name) from e
 if not isinstance(v,dict):raise Backoff("non-object "+p.name)
 return v

def atomic(p,v):
 p=pathlib.Path(p)
 if p.is_symlink():raise Backoff("watchdog state symlink")
 fd,t=tempfile.mkstemp(prefix="."+p.name+".",dir=p.parent)
 try:
  with os.fdopen(fd,"w") as f:json.dump(v,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
  os.replace(t,p);d=os.open(p.parent,os.O_RDONLY)
  try:os.fsync(d)
  finally:os.close(d)
 finally:
  with contextlib.suppress(FileNotFoundError):os.unlink(t)

def counter(p=COUNTER):
 if not pathlib.Path(p).exists():return {"schema_version":1,"recovery_count":0,"history":[]}
 x=readj(p);n=x.get("recovery_count")
 if x.get("schema_version")!=1 or type(n)is not int or not 0<=n<=MAX_RECOVERIES or not isinstance(x.get("history"),list):raise Backoff("malformed/over-limit recovery counter")
 return x

def helper_load():
 if HELPER.is_symlink() or not HELPER.is_file() or sha(HELPER)!=HELPER_SHA:raise Backoff("pinned identity helper missing/changed")
 s=importlib.util.spec_from_file_location("lamost_retention_identity_helper",HELPER)
 if s is None or s.loader is None:raise Backoff("cannot load identity helper")
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def inside(p):
 try:pathlib.Path(p).resolve().relative_to(R.resolve());return True
 except (ValueError,OSError):return False

def unknown_controller(p):
 argv,cwd=p.get("argv",[]),p.get("cwd")
 if not isinstance(argv,list):return False
 text=" ".join(map(str,argv)).lower()
 if isinstance(cwd,pathlib.Path) and inside(cwd):return any(x in text for x in ("controller.py","run_controller.py","source.controller"))
 for token in argv:
  t=str(token).lower()
  if any(x in t for x in ("controller.py","run_controller.py","source.controller")):
   q=pathlib.Path(str(token));q=q if q.is_absolute() else (cwd/q if isinstance(cwd,pathlib.Path) else q)
   if inside(q):return True
 return False

def unknown_worker(p):
 argv,cwd=p.get("argv",[]),p.get("cwd")
 if not isinstance(argv,list):return False
 text=" ".join(map(str,argv)).lower()
 names=("worker.py","phase_worker","e6_phase_supervisor","parallel_rf.worker","parallel_extra_trees.worker","svm_margin.worker")
 if isinstance(cwd,pathlib.Path) and inside(cwd) and any(x in text for x in names):return True
 for token in argv:
  t=str(token).lower()
  if any(x in t for x in names):
   q=pathlib.Path(str(token));q=q if q.is_absolute() else (cwd/q if isinstance(cwd,pathlib.Path) else q)
   if inside(q):return True
 return False

def processes(h,controller_sha):
 try:ps=h._proc_snapshot()
 except Exception as e:raise Backoff("process inventory failed") from e
 ctrls=[];workers=[];unknown=[];stores=[];wn=tuple(getattr(h,"WORKER_NAMES",()))+EXTRA_WORKERS;sn=tuple(getattr(h,"STORAGE_NAMES",()))
 for pid,p in ps.items():
  try:
   argv,cwd=p["argv"],pathlib.Path(p["cwd"]);uid=int(p["uid"]);ticks=str(p["ticks"])
   if h._script_matches(argv,cwd,R,CTRL_NAMES):
    own=None
    if OWNER.exists() and not OWNER.is_symlink():
     try:own=readj(OWNER)
     except Backoff:pass
    ok=bool(own and int(own.get("pid",-1))==int(pid) and str(own.get("process_start_ticks"))==ticks
       and int(own.get("uid",uid))==uid==os.getuid() and own.get("code_sha256")==controller_sha
       and cwd.resolve()==R.resolve() and "run" in argv)
    ctrls.append({"verified":ok,"pid":int(pid),"ticks":ticks,"uid":uid})
   elif h._script_matches(argv,cwd,R,wn):workers.append({"pid":int(pid),"ticks":ticks,"uid":uid})
   elif unknown_controller(p):unknown.append({"pid":int(pid),"ticks":ticks,"uid":uid})
   elif unknown_worker(p):workers.append({"pid":int(pid),"ticks":ticks,"uid":uid})
   elif sn and h._script_matches(argv,cwd,R,sn):stores.append({"pid":int(pid),"ticks":ticks,"uid":uid})
  except (KeyError,TypeError,ValueError,OSError) as e:raise Backoff("incomplete process identity") from e
 return {"controllers":ctrls,"workers":workers,"unknown_controllers":unknown,"storage":stores}

def authorize(d,e,h,f,source_sha,freeze_sha,run_sha):
 if e.get("schema_version")!="lamost-safe-watchdog-enable/1" or e.get("enabled") is not True:raise Backoff("not explicitly enabled")
 if d.get("phase")!="watchdog_ready" or d.get("qualification_status")!="qualified":raise Backoff("not qualified/watchdog_ready")
 nonce=h.get("nonce");hd=d.get("hold_document")
 if not isinstance(hd,dict) or not isinstance(nonce,str) or nonce!=hd.get("nonce") or e.get("hold_nonce")!=nonce:raise Backoff("start-hold nonce mismatch")
 installed=d.get("installed_controller_sha256")
 source_map=f.get("source_sha256")
 if not isinstance(source_map,dict) or not isinstance(installed,str) or not (source_sha==source_map.get("controller.py")==installed==e.get("controller_sha256")):raise Backoff("controller source/freeze/installed pin mismatch")
 if not (freeze_sha==d.get("freeze_sha256")==e.get("freeze_sha256")):raise Backoff("freeze pin mismatch")
 if RUN.is_symlink() or not RUN.is_file():raise Backoff("controller launch script missing/unsafe")
 if not isinstance(run_sha,str) or not (run_sha==d.get("run_script_sha256")==e.get("run_script_sha256")):raise Backoff("run_controller.sh actual/state/enable SHA mismatch")
 if d.get("storage_policy_id")!=POLICY or e.get("storage_policy_id")!=POLICY:raise Backoff("storage policy id mismatch")
 sp,rp=f.get("storage_admission_policy"),f.get("resource_policy")
 if not isinstance(sp,dict) or any(sp.get(k)!=v for k,v in STORAGE.items()):raise Backoff("freeze lacks 6GiB/one-fit policy")
 if not isinstance(rp,dict) or any(rp.get(k)!=v for k,v in SCIENCE.items()):raise Backoff("science limits differ")
 if e.get("max_recoveries")!=MAX_RECOVERIES:raise Backoff("recovery cap differs")
 if h.get("owner_operation")!="user_approved_working_storage_policy_20261030":raise Backoff("start-hold owner mismatch")

def decide(d,e,h,f,source_sha,freeze_sha,run_sha,holds,proc,reg,count,owner_free,tmux):
 try:
  if not all(isinstance(x,dict) for x in (d,e,h,f,holds,proc,reg,count)):raise Backoff("malformed decision input")
  authorize(d,e,h,f,source_sha,freeze_sha,run_sha)
  if holds.get("ADMISSION_HOLD") or holds.get("CODE_CHANGE_HOLD"):raise Backoff("source hold active")
  ctrls,workers,unknown,stores=proc.get("controllers"),proc.get("workers"),proc.get("unknown_controllers"),proc.get("storage",[])
  if not all(isinstance(x,list) for x in (ctrls,workers,unknown,stores)):raise Backoff("malformed process inventory")
  if unknown:raise Backoff("unknown project controller candidate")
  if len(ctrls)>1:raise Backoff("multiple project controllers")
  if ctrls:
   if ctrls[0].get("verified") is True:return {"action":"noop_controller_verified","reason":"qualified controller alive"}
   raise Backoff("controller present; owner unknown")
  if workers or stores:raise Backoff("orphan worker/phase/E6 supervisor or storage process present")
  statuses=reg.get("status_counts")
  if not isinstance(statuses,dict) or any(type(v)is not int or v<0 for v in statuses.values()):raise Backoff("malformed registry statuses")
  if any(k not in NONTERMINAL and k!="validated_terminal" for k in statuses):raise Backoff("unknown registry status")
  total=reg.get("total")
  if type(total)is not int or sum(statuses.values())!=total:raise Backoff("registry counts do not reconcile")
  if sum(v for k,v in statuses.items() if k!="validated_terminal")==0:return {"action":"all_terminal_no_model_restart","reason":"registry fully validated terminal"}
  n=count.get("recovery_count")
  if type(n)is not int or not 0<=n<=MAX_RECOVERIES:raise Backoff("malformed recovery counter")
  if n>=MAX_RECOVERIES:raise Backoff("two automatic recoveries already used")
  if owner_free is not True:raise Backoff("project ownership lock held/unavailable")
  if tmux is not False:raise Backoff("tmux session exists without verified controller")
  return {"action":"launch_controller","reason":"controller absent; registry work pending"}
 except Backoff as x:return {"action":"backoff","reason":str(x)}
 except (AttributeError,KeyError,TypeError,ValueError):return {"action":"backoff","reason":"malformed authorization or process state"}

def registry(h):
 try:rows=h.registry(R/"registry.sqlite")
 except Exception as e:raise Backoff("read-only registry scan failed") from e
 if not isinstance(rows,dict) or not rows:raise Backoff("empty/malformed registry")
 c={}
 for r in rows.values():
  if not isinstance(r,dict) or not isinstance(r.get("status"),str):raise Backoff("malformed task row")
  c[r["status"]]=c.get(r["status"],0)+1
 return {"total":len(rows),"status_counts":c}

def owner_lock_free():
 if OWNER_LOCK.is_symlink() or not OWNER_LOCK.is_file():return False
 try:
  with OWNER_LOCK.open("r") as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(f,fcntl.LOCK_UN)
  return True
 except OSError:return False

def tmux_session():
 if shutil.which("tmux") is None:raise Backoff("tmux command unavailable")
 return subprocess.run(["tmux","has-session","-t","lamost-project"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False).returncode==0

def log(s):
 with LOG.open("a") as f:f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+" "+s+"\n");f.flush();os.fsync(f.fileno())

def run_once():
 O.mkdir(parents=True,exist_ok=True)
 if LOCK.is_symlink():return {"action":"backoff","reason":"wrapper lock symlink"}
 lock=LOCK.open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:lock.close();return {"action":"noop_wrapper_locked","reason":"another invocation owns lock"}
 try:
  h=helper_load();d,e,hold=readj(DEPLOY),readj(ENABLE),readj(HOLD);f=readj(FREEZE)
  s,fh,rh=sha(CTRL),sha(FREEZE),sha(RUN);authorize(d,e,hold,f,s,fh,rh)
  holds={"ADMISSION_HOLD":(R/"ADMISSION_HOLD.json").exists() or (R/"ADMISSION_HOLD.json").is_symlink(),"CODE_CHANGE_HOLD":(R/"CODE_CHANGE_HOLD.json").exists() or (R/"CODE_CHANGE_HOLD.json").is_symlink()}
  proc=processes(h,s);reg=registry(h);cnt=counter()
  ownfree=owner_lock_free();sess=tmux_session() if not proc["controllers"] and not proc["unknown_controllers"] else False
  ans=decide(d,e,hold,f,s,fh,rh,holds,proc,reg,cnt,ownfree,sess)
  if ans["action"]=="launch_controller":
   if RUN.is_symlink() or not RUN.is_file():raise Backoff("controller launch script missing/unsafe")
   hist=list(cnt["history"])[-19:]+[{"observed_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"reason":"controller absent; pending registry"}]
   atomic(COUNTER,{"schema_version":1,"recovery_count":cnt["recovery_count"]+1,"history":hist})
   p=subprocess.run(["tmux","new-session","-d","-s","lamost-project","/bin/bash",str(RUN)],cwd=str(R),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
   if p.returncode:ans={"action":"launch_dispatch_failed","reason":"tmux nonzero; attempt counted"}
   else:
    time.sleep(1);after=processes(h,s);live=after["controllers"]
    ans=({"action":"controller_launched_verified","reason":"detached controller owner identity verified"} if len(live)==1 and live[0]["verified"]
      else {"action":"launch_dispatched_unverified","reason":"detached; later polls fail closed until identity proof"})
  log(ans["action"]+": "+ans["reason"]);return ans
 except Backoff as x:
  ans={"action":"backoff","reason":str(x)}
  with contextlib.suppress(Exception):log(ans["action"]+": "+ans["reason"])
  return ans
 except Exception as x:
  ans={"action":"backoff","reason":"unexpected observation error: "+type(x).__name__}
  with contextlib.suppress(Exception):log(ans["action"]+": "+ans["reason"])
  return ans
 finally:
  with contextlib.suppress(Exception):fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

if __name__=="__main__":print(json.dumps(run_once(),sort_keys=True))

