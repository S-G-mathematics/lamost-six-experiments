#!/usr/bin/env python3
"""Staged finalize.lock guardian for release-backed temporary NPZ retention."""
import argparse,contextlib,fcntl,hashlib,json,os,pathlib,signal,sqlite3,stat,subprocess,sys,tempfile,time,uuid
ROOT_PIN=pathlib.Path("/home/ubuntu/lamost_e1_migration_20261023")
SCHEMA="lamost-release-retention-guardian/1"
CONFIG="lamost-release-retention-guardian-config/1"
RESUME="lamost-release-retention-resume/1"
TERMINAL={"validated_terminal"}
TERM_REQUESTED=False
AUDIT={"finalize_project.py","audit_artifacts.py","calibration_replay_supervisor.py","final_review.py","run_finalizer.sh"}
WORKERS={"phase_worker.py","worker.py","parallel_rf/worker.py","parallel_extra_trees/worker.py","controller.py"}
class GuardianError(RuntimeError):pass
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def _term_handler(signum,frame):
 global TERM_REQUESTED
 TERM_REQUESTED=True
def sha_file(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def atomic(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=p.parent,prefix="."+p.name+".")
 try:
  with os.fdopen(fd,"w") as f:json.dump(obj,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600);os.replace(tmp,p);d=os.open(p.parent,os.O_RDONLY);os.fsync(d);os.close(d)
 finally:
  with contextlib.suppress(FileNotFoundError):os.unlink(tmp)
def ident(pid):
 d=pathlib.Path("/proc")/str(pid)
 try:
  tail=(d/"stat").read_text().split(")",1)[1].split();u=int(next(x for x in (d/"status").read_text().splitlines() if x.startswith("Uid:")).split()[1]);a=(d/"cmdline").read_bytes()
  return {"pid":int(pid),"start_ticks":int(tail[19]),"uid":u,"pgid":int(tail[2]),"state":tail[0],"argv_sha256":sha_bytes(a)}
 except Exception:return None
def script_match(args,cwd,paths):
 cwd=pathlib.Path(cwd).resolve(strict=False)
 for arg in args:
  try:
   q=pathlib.Path(arg);q=(cwd/q) if not q.is_absolute() else q
   resolved=q.resolve(strict=False)
   if resolved in paths:return paths[resolved]
  except Exception:pass
 return None
def pid_runs_script(pid,script):
 try:
  args=(pathlib.Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\0")
  expected=pathlib.Path(script).resolve(strict=True)
  return any(x and pathlib.Path(x.decode(errors="replace")).is_absolute() and pathlib.Path(x.decode(errors="replace")).resolve(strict=False)==expected for x in args)
 except Exception:return False
def process_rows(runtime):
 runtime=pathlib.Path(runtime).resolve();paths={}
 for n in AUDIT|WORKERS:
  paths[(runtime/n if n=="run_finalizer.sh" else runtime/"source"/n).resolve(strict=False)]=n
 rows=[]
 for d in pathlib.Path("/proc").iterdir():
  if not d.name.isdigit() or int(d.name)==os.getpid():continue
  try:
   args=[x.decode(errors="replace") for x in (d/"cmdline").read_bytes().split(b"\0") if x]
   cwd=(d/"cwd").resolve(strict=True)
  except OSError:continue
  match=script_match(args,cwd,paths)
  if match:
   z=ident(int(d.name))
   if z and z["state"] not in ("Z","X","x"):rows.append({"script":match,**z})
 return rows
def registry(runtime,n):
 c=sqlite3.connect("file:"+str(pathlib.Path(runtime,"registry.sqlite").resolve())+"?mode=ro",uri=True,timeout=5);counts={};total=0
 try:
  for (s,) in c.execute("select record from tasks"):
   t=json.loads(s);k=t.get("status","<missing>");counts[k]=counts.get(k,0)+1;total+=1
 finally:c.close()
 return {"total":total,"expected":n,"status_counts":dict(sorted(counts.items())),"all_terminal":total==n and bool(counts) and set(counts)<=TERMINAL}
def cfgload(p):
 p=pathlib.Path(p).resolve(strict=True);c=json.loads(p.read_text());root=pathlib.Path(c.get("root","")).resolve(strict=True)
 if c.get("schema")!=CONFIG or root!=ROOT_PIN.resolve():raise GuardianError("config schema/root mismatch")
 op=root/"operations"/"release_guardian_20261030"
 if p.parent!=op.resolve():raise GuardianError("config outside guardian operation directory")
 if op.is_symlink():raise GuardianError("guardian directory symlink")
 expected={"utility_path":root/"operations/release_retention_20261030/release_retention.py","manifest_path":root/"github_release_results_20261028/release_manifest.json","plan_path":root/"operations/release_retention_20261030/ACTUAL_METADATA_PLAN.json","approval_path":root/"operations/release_retention_20261030/RETIREMENT_APPROVAL.json"}
 for k,q in expected.items():
  if pathlib.Path(c.get(k,"")).resolve(strict=True)!=q.resolve(strict=True):raise GuardianError(k+" path mismatch")
  hk=k.replace("_path","_sha256")
  if c.get(hk)!=sha_file(q):raise GuardianError(k+" SHA mismatch")
 if c.get("plan_sha256")!=sha_file(expected["plan_path"]) or int(c.get("expected_registry_rows",0))!=6270:raise GuardianError("plan/count binding mismatch")
 for k in ("retention_state_path","cache_dir","helper_log_path"):
  if pathlib.Path(c[k]).resolve(strict=False).is_relative_to(root) is False:raise GuardianError(k+" escapes ROOT")
 if pathlib.Path(c["retention_state_path"]).resolve(strict=False)!=(root/"operations/release_retention_20261030/release_retention_index.json").resolve(strict=False):raise GuardianError("wrong retention index path")
 if c.get("repo_slug")!="S-G-mathematics/lamost-six-experiments" or not isinstance(c.get("release_tag"),str) or not c["release_tag"]:
  raise GuardianError("release identity missing")
 try:
  q=subprocess.run(["gh","release","view",c["release_tag"],"--repo",c["repo_slug"],"--json","tagName"],capture_output=True,text=True,timeout=15)
  actual=json.loads(q.stdout).get("tagName") if q.returncode==0 else None
 except Exception:actual=None
 if actual!=c["release_tag"]:raise GuardianError("configured tag does not match an existing GitHub release")
 if int(c.get("retire_disk_floor_bytes",20*(1<<30)))!=20*(1<<30) or int(c.get("restore_disk_floor_bytes",6*(1<<30)))!=6*(1<<30):
  raise GuardianError("retirement/restore disk floors must be exactly 20/6 GiB")
 return c,root,root/"runtime_20261025",op
def lock_finalize(runtime):
 p=pathlib.Path(runtime)/"finalize.lock"
 if p.is_symlink():raise GuardianError("finalize.lock is symlink")
 f=p.open("a+")
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:f.close();raise GuardianError("finalize.lock busy")
 return f
def archive_preflight_busy(runtime):
 # Same nonblocking gates as release_retention.quiet(), before launching it.
 rt=pathlib.Path(runtime).resolve();hold=rt/"ADMISSION_HOLD.json"
 if hold.exists() or hold.is_symlink():return "ADMISSION_HOLD.json present"
 for p in (rt/"locks/cold_auto_compaction.lock",rt/"batch-wrapper.lock"):
  p.parent.mkdir(parents=True,exist_ok=True)
  if p.is_symlink():raise GuardianError("archive lock path is a symlink")
  fd=os.open(p,os.O_RDWR|os.O_CREAT,0o600)
  try:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:return str(p)+" busy"
   finally:
    with contextlib.suppress(OSError):fcntl.flock(fd,fcntl.LOCK_UN)
  finally:os.close(fd)
 return None
def read_index(p):
 p=pathlib.Path(p)
 if not p.exists():return {"schema":"lamost-release-retention-index/1","retired":[],"restore_required":False}
 d=json.loads(p.read_text())
 if d.get("schema")!="lamost-release-retention-index/1" or not isinstance(d.get("retired"),list):raise GuardianError("retention index invalid")
 return d
def save_state(p,s,**kw):s.update(kw);s["observed_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime());atomic(p,s)
def helper(c,mode,s,sp,guard_lock):
 args=[sys.executable,c["utility_path"],"restore","--root",c["root"],"--state",c["retention_state_path"],"--cache",c["cache_dir"],"--repo",c["repo_slug"], "--tag",c["release_tag"],"--disk-floor",str(c.get("restore_disk_floor_bytes",6*(1<<30)))]
 if mode=="retire":
  args=[sys.executable,c["utility_path"],"verify-retire","--root",c["root"],"--manifest",c["manifest_path"],"--plan",c["plan_path"],"--state",c["retention_state_path"],"--cache",c["cache_dir"],"--log",c["helper_log_path"],"--repo",c["repo_slug"],"--tag",c["release_tag"],"--approval",c["approval_path"],"--disk-floor",str(c.get("retire_disk_floor_bytes",20*(1<<30))),"--execute","--include-groups"]
 log=pathlib.Path(c["helper_log_path"]);log.parent.mkdir(parents=True,exist_ok=True)
 with log.open("ab",buffering=0) as out:
  p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,close_fds=True,pass_fds=(guard_lock.fileno(),),start_new_session=True)
  end=time.monotonic()+5;z=None;verified=False
  while p.poll() is None and time.monotonic()<end:
   z=ident(p.pid)
   if z and z["uid"]==os.getuid() and z["pgid"]==p.pid and pid_runs_script(p.pid,c["utility_path"]):
    verified=True;break
   time.sleep(.05)
  if not verified:
   save_state(sp,s,status="restore_required",error="helper identity unverifiable; no signal sent",helper_pid=p.pid)
   try:p.wait(timeout=630)
   except subprocess.TimeoutExpired:
    save_state(sp,s,status="restore_required",error="helper identity still unverifiable after 630s; waiting without signaling",helper_pid=p.pid)
    p.wait()
   raise GuardianError("helper identity unverifiable; child waited, not signaled")
  save_state(sp,s,status=mode+"_running",helper_identity={k:z[k] for k in ("pid","start_ticks","uid","pgid","argv_sha256")})
  identity_bad=False
  while p.poll() is None:
   now=ident(p.pid)
   if z and (not now or any(now.get(k)!=z.get(k) for k in ("pid","start_ticks","uid","pgid","argv_sha256")) or not pid_runs_script(p.pid,c["utility_path"])):
    identity_bad=True;save_state(sp,s,status="restore_required",error="helper process identity changed; no signal sent")
   time.sleep(.25)
  rc=p.wait()
 if identity_bad:raise GuardianError("helper identity changed; no signal sent")
 if rc:raise GuardianError(f"{mode} helper exit={rc}; inspect private helper log")
def planned_sources(c):
 p=json.loads(pathlib.Path(c["plan_path"]).read_text());rows=p.get("selected",[])+p.get("complete_known_inode_group_review_only",{}).get("selected",[])
 return {x["source_path"]:x["source_sha256"] for x in rows}
def check_plan_index(c,d):
 allow=planned_sources(c)
 for x in d["retired"]:
  if x.get("source_path") not in allow or x.get("source_sha256")!=allow[x["source_path"]]:raise GuardianError("retirement index exceeds pinned plan")
def check_native(c,d):
 root=pathlib.Path(c["root"])
 for x in d["retired"]:
  ps=x.get("native_paths") if x.get("retirement_kind")=="complete_inode_group" else [x["source_path"]]
  ss=[]
  for r in ps:
   p=root/r
   if p.is_symlink() or not p.is_file() or p.stat().st_size!=x["source_bytes"]:return False
   ss.append(p.stat())
  if len(ps)>1 and (len({(z.st_dev,z.st_ino) for z in ss})!=1 or ss[0].st_nlink!=len(ps)):return False
 return True
def make_resume(root,nonce,plan_sha,reason):
 op=pathlib.Path(root)/"operations/release_guardian_20261030";s=json.loads((op/"guardian_state.json").read_text())
 if s.get("operation_nonce")!=nonce or s.get("plan_sha256")!=plan_sha:raise GuardianError("resume binding mismatch")
 p=op/("resume_"+nonce+".json")
 if p.exists() or p.is_symlink():raise GuardianError("resume marker exists")
 atomic(p,{"schema":RESUME,"operation_nonce":nonce,"plan_sha256":plan_sha,"action":"restore","reason":str(reason)[:300],"request_uid":os.getuid(),"requested_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
 return p
def wait_resume(op,s,sp):
 p=op/("resume_"+s["operation_nonce"]+".json")
 while True:
  if p.is_file():
   try:
    m=json.loads(p.read_text())
    if m.get("schema")!=RESUME or m.get("action")!="restore" or m.get("operation_nonce")!=s["operation_nonce"] or m.get("plan_sha256")!=s["plan_sha256"] or m.get("request_uid")!=os.getuid():raise GuardianError("invalid explicit resume marker")
    p.unlink();return
   except Exception as e:
    with contextlib.suppress(Exception):save_state(sp,s,status="restore_required",restore_required=True,resume_marker_error=type(e).__name__+":"+str(e))
  time.sleep(2)
def release_authorized(state,index,native_ok):
 return bool(state.get("status") in ("complete","no_retirement") and not index.get("restore_required") and native_ok)
def restore_after_resume(config,c,s,sp,op,guard_lock):
 # Every retry requires a new nonce/plan-bound operator marker. The guardian
 # retains finalize.lock throughout and never retries a failed helper itself.
 while True:
  try:
   wait_resume(op,s,sp)
   c,root,rt,op=cfgload(config)
   while True:
    procs=process_rows(rt);bad=[x for x in procs if x["script"] in AUDIT]
    workers=[x for x in procs if x["script"] in WORKERS]
    reg=registry(rt,6270)
    if reg["all_terminal"] and not workers and not bad:break
    save_state(sp,s,status="restore_required",restore_required=True,registry=reg,worker_identities=workers,audit_processes=bad)
    time.sleep(max(1,int(c.get("poll_seconds",15))))
   helper(c,"restore",s,sp,guard_lock)
   idx=read_index(c["retention_state_path"]);check_plan_index(c,idx)
   if idx.get("restore_required") or not check_native(c,idx):raise GuardianError("helper did not verify complete native restoration")
   save_state(sp,s,status="complete",restored_count=len(idx["retired"]),restore_utc=idx.get("last_restore_utc"),complete_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
   return s
  except Exception as e:
   with contextlib.suppress(Exception):
    idx=read_index(c["retention_state_path"])
    save_state(sp,s,status="restore_required",restore_required=True,error_type=type(e).__name__,error=str(e))
   time.sleep(2)
def run(config,resume=False):
 c,root,rt,op=cfgload(config);op.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(op,0o700);sp=op/"guardian_state.json";lf=lock_finalize(rt);release=False;helper_started=False
 old=json.loads(sp.read_text()) if sp.exists() else None
 idx_before=read_index(c["retention_state_path"])
 if old and resume and (old.get("plan_sha256")!=c["plan_sha256"] or not idx_before.get("restore_required")):
  raise GuardianError("existing operation is not eligible for explicit restore resume")
 if old and not resume and (old.get("status")!="backoff_before_retirement" or old.get("plan_sha256")!=c["plan_sha256"] or idx_before.get("retired") or idx_before.get("restore_required")):
  raise GuardianError("existing operation requires explicit restore resume or clean backoff review")
 n=(old["operation_nonce"] if resume else uuid.uuid4().hex) if old else uuid.uuid4().hex
 if old and not resume:old=None
 signal.signal(signal.SIGTERM,_term_handler);signal.signal(signal.SIGINT,_term_handler)
 me=ident(os.getpid())
 if not me:raise GuardianError("cannot verify guardian identity")
 s=old or {"schema":SCHEMA,"operation_nonce":n,"created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"plan_sha256":c["plan_sha256"],"manifest_sha256":c["manifest_sha256"],"approval_sha256":c["approval_sha256"],"utility_sha256":c["utility_sha256"],"retention_state_path":c["retention_state_path"]}
 s["guardian"]={k:me[k] for k in ("pid","start_ticks","uid","pgid","argv_sha256")};save_state(sp,s,status="preflight")
 try:
  procs=process_rows(rt);bad=[x for x in procs if x["script"] in AUDIT]
  if bad:save_state(sp,s,status="restore_required" if read_index(c["retention_state_path"]).get("restore_required") else "blocked_before_retirement",processes=bad);raise GuardianError("audit/finalizer/replay process active")
  idx=read_index(c["retention_state_path"]);check_plan_index(c,idx)
  if resume:
   if not idx.get("restore_required") and idx.get("retired"):
    raise GuardianError("retention index has entries but restoration is not marked required")
   if not idx.get("restore_required") and not idx.get("retired"):
    save_state(sp,s,status="no_retirement",retired_count=0,complete_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    release=True;return s
  else:
   if idx.get("retired") or idx.get("restore_required"):raise GuardianError("existing retention state requires review/resume")
   while True:
    busy=archive_preflight_busy(rt)
    if not busy:break
    save_state(sp,s,status="waiting_for_archive_quiescence",archive_preflight_busy=busy)
    if TERM_REQUESTED:
     save_state(sp,s,status="backoff_before_retirement",backoff_reason="stop requested while archive operation remained busy")
     release=True;return s
    time.sleep(max(1,int(c.get("poll_seconds",15))))
   save_state(sp,s,status="retirement_starting");helper_started=True
   helper(c,"retire",s,sp,lf)
   idx=read_index(c["retention_state_path"]);check_plan_index(c,idx)
   if not idx.get("restore_required"):
    save_state(sp,s,status="no_retirement",retired_count=0,complete_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()));release=True;return s
   save_state(sp,s,status="retired_waiting",retired_count=len(idx["retired"]),retired_bytes=sum(int(x["source_bytes"]) for x in idx["retired"]))
  while True:
   if TERM_REQUESTED and read_index(c["retention_state_path"]).get("restore_required"):
    save_state(sp,s,status="restore_required",restore_required=True,stop_requested=True)
    wait_resume(op,s,sp)
   bad=[x for x in process_rows(rt) if x["script"] in AUDIT]
   if bad:save_state(sp,s,status="retired_waiting",audit_processes=bad)
   reg=registry(rt,6270);workers=[x for x in process_rows(rt) if x["script"] in WORKERS]
   if reg["all_terminal"] and not workers and not bad:break
   save_state(sp,s,status="retired_waiting",registry=reg,worker_identities=workers,audit_processes=bad)
   time.sleep(max(1,int(c.get("poll_seconds",15))))
  save_state(sp,s,status="restore_started",registry_final=reg)
  helper(c,"restore",s,sp,lf)
  idx=read_index(c["retention_state_path"]);check_plan_index(c,idx)
  if idx.get("restore_required") or not check_native(c,idx):raise GuardianError("helper did not verify complete native restoration")
  save_state(sp,s,status="complete",restored_count=len(idx["retired"]),restore_utc=idx.get("last_restore_utc"),complete_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
  release=True;return s
 except Exception as e:
  idx=read_index(c["retention_state_path"])
  if idx.get("restore_required"):
   save_state(sp,s,status="restore_required",restore_required=True,error_type=type(e).__name__,error=str(e))
   s=restore_after_resume(config,c,s,sp,op,lf)
   release=True
   return s
  if s.get("status") not in ("no_retirement","complete"):save_state(sp,s,status="blocked_before_retirement",error_type=type(e).__name__,error=str(e))
  raise
 finally:
  if release:
   with contextlib.suppress(Exception):fcntl.flock(lf,fcntl.LOCK_UN)
   lf.close()
  # On any missing-native/error state, retain finalize.lock until explicit recovery or process death.
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);r=s.add_parser("run");r.add_argument("--config",required=True);r.add_argument("--execute",action="store_true");r.add_argument("--resume",action="store_true")
 q=s.add_parser("status");q.add_argument("--state",required=True)
 m=s.add_parser("request-resume");m.add_argument("--nonce",required=True);m.add_argument("--plan-sha256",required=True);m.add_argument("--reason",required=True);m.add_argument("--root",default=str(ROOT_PIN))
 a=p.parse_args()
 try:
  if a.cmd=="run":
   if not a.execute:raise GuardianError("explicit --execute required; this is not a dry run")
   print(json.dumps(run(a.config,a.resume),sort_keys=True));return 0
  if a.cmd=="status":print(json.dumps(json.loads(pathlib.Path(a.state).read_text()),sort_keys=True));return 0
  print(json.dumps({"resume_marker":str(make_resume(a.root,a.nonce,a.plan_sha256,a.reason))}));return 0
 except Exception as e:
  print(json.dumps({"status":"blocked","error_type":type(e).__name__,"reason":str(e)},sort_keys=True),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())

