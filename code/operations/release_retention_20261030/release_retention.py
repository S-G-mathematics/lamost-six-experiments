#!/usr/bin/env python3
"""Bounded retention for already-published E4 outcome arrays."""
import argparse,contextlib,hashlib,json,os,pathlib,shutil,sqlite3,stat,subprocess,sys,tempfile,time,zipfile
SCHEMA="lamost-release-retention-plan/1"; INDEX="lamost-release-retention-index/1"; APPROVAL="lamost-release-retirement-approval/1"; GIB=1<<30
class RetentionError(RuntimeError):pass
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(4<<20),b""):h.update(b)
 return h.hexdigest()
def relpath(s):
 if not isinstance(s,str) or not s or "\\" in s:raise RetentionError("unsafe path")
 p=pathlib.PurePosixPath(s)
 if p.is_absolute() or any(x in ("",".","..") for x in p.parts):raise RetentionError("unsafe path")
 return p
def path(root,rel,missing=False):
 root=pathlib.Path(root).resolve();p=relpath(rel);cur=root
 for x in p.parts:
  cur=cur/x
  try:st=cur.lstat()
  except FileNotFoundError:
   if missing:continue
   raise RetentionError("missing path")
  if stat.S_ISLNK(st.st_mode):raise RetentionError("symlink path")
 try:cur.resolve(strict=not missing).relative_to(root)
 except (ValueError,FileNotFoundError):raise RetentionError("path escape")
 return root.joinpath(*p.parts)
def atomic(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=p.parent,prefix="."+p.name+".")
 try:
  with os.fdopen(fd,"w") as f:json.dump(obj,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
  os.replace(tmp,p);fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
 finally:
  with contextlib.suppress(FileNotFoundError):os.unlink(tmp)
def registry(p):
 c=sqlite3.connect("file:"+str(pathlib.Path(p).resolve())+"?mode=ro",uri=True)
 try:return {k:json.loads(v) for k,v in c.execute("select key,record from tasks")}
 finally:c.close()
def taskkey(s):
 pre="runtime_20261025/artifacts/";suf="/test_outcomes.npz"
 if not s.startswith(pre) or not s.endswith(suf):return None
 k=s[len(pre):]
 if "/attempts/" in k:
  base,tail=k.split("/attempts/",1);parts=tail.split("/")
  if len(parts)!=2 or parts[1]!="test_outcomes.npz" or not parts[0] or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in parts[0]):return None
  k=base
 else:k=k[:-len(suf)]
 return k if k.startswith("e4/") and "/eval/" in k else None

def valid_task(t,k):
 return bool(t and t.get("key")==k and t.get("experiment")==4 and t.get("kind")=="eval" and t.get("status")=="validated_terminal" and t.get("outcome")=="successful" and t.get("validation_state")=="validated" and t.get("scientific_case") is True and t.get("condition")!="control" and t.get("route") in ("direct","treatment"))
def validation_evidence(root,s,t,sha0):
 k=taskkey(s);rel="runtime_20261025/artifacts/"+str(k)+"/validation.json"
 try:
  vp=path(root,rel);raw=vp.read_bytes();v=json.loads(raw)
 except (OSError,ValueError,RetentionError):return None
 if v.get("status")!="validated" or v.get("task_key")!=k or v.get("files",{}).get("test_outcomes.npz")!=sha0:return None
 return rel,hashlib.sha256(raw).hexdigest()
def valid_manifest_binding(root,s,t,sha0):
 return validation_evidence(root,s,t,sha0) is not None

def make_plan(root,mp,rp,target=2*GIB):
 if target<0 or target>4*GIB:raise RetentionError("plan target is capped at 4 GiB")
 root=pathlib.Path(root).resolve();m=json.loads(pathlib.Path(mp).read_text())
 if m.get("schema")!="lamost-scientific-array-release/1":raise RetentionError("bad release manifest schema")
 reg=registry(rp);singles=[];groups=[];exclude={};seen=set();e4_rows=0;e4_bytes=0;control_rows=0;eligible_rows=0;eligible_bytes=0
 for r in m["files"]:
  if r.get("category")!="runtime_test_outcomes":continue
  if r["archive_member"] in seen:raise RetentionError("duplicate manifest member")
  seen.add(r["archive_member"]);s=r["source_path"];k=taskkey(s);t=reg.get(k or "")
  if k and k.startswith("e4/"):e4_rows+=1;e4_bytes+=int(r.get("source_bytes",0))
  if t and t.get("condition")=="control":control_rows+=1;exclude["control"]=exclude.get("control",0)+1;continue
  ve=validation_evidence(root,s,t,r["source_sha256"])
  if not valid_task(t,k) or ve is None:continue
  eligible_rows+=1;eligible_bytes+=int(r["source_bytes"])
  if any(k in (x.get("dependencies") or []) for kk,x in reg.items() if kk!=k):
   exclude["consumer"]=exclude.get("consumer",0)+1;continue
  try:p=path(root,s);st=p.lstat()
  except Exception:exclude["missing_unsafe"]=exclude.get("missing_unsafe",0)+1;continue
  if not stat.S_ISREG(st.st_mode) or st.st_size!=r["source_bytes"]:exclude["native_size_type"]=exclude.get("native_size_type",0)+1;continue
  x={q:r.get(q) for q in ("source_path","archive_member","asset","source_bytes","source_sha256","archive_crc32","aliases")};x["task_key"]=k;x["validation_path"],x["validation_sha256"]=ve
  if st.st_nlink==1 and not x["aliases"]:singles.append(x);continue
  paths=[s]+list(x["aliases"] or []);ok=len(paths)==st.st_nlink and len(set(paths))==len(paths)
  # Review-only complete group: aliases all resolve to same successful task/inode.
  for a in paths:
   if taskkey(a)!=k or not valid_manifest_binding(root,a,t,r["source_sha256"]):ok=False;break
   try:
    ap=path(root,a);ast=ap.lstat()
    if not stat.S_ISREG(ast.st_mode) or (ast.st_dev,ast.st_ino,ast.st_size)!=(st.st_dev,st.st_ino,st.st_size):ok=False;break
   except Exception:ok=False;break
  if ok:groups.append({**x,"native_paths":paths,"link_count":st.st_nlink,"review_only":True,"retirement_enabled":False})
  else:exclude["incomplete_inode_group"]=exclude.get("incomplete_inode_group",0)+1
 order={a["name"]:i for i,a in enumerate(m["assets"])};singles.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]));groups.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]))
 chosen=[];n=0
 for x in singles:
  if n+x["source_bytes"]<=target:chosen.append(x);n+=x["source_bytes"]
 review=[];rn=0
 for x in groups:
  if rn+x["source_bytes"]<=target:review.append(x);rn+=x["source_bytes"]
 return {"schema":SCHEMA,"root":str(root),"release":{"repo":"S-G-mathematics/lamost-six-experiments","tag":"results-2026-10-28"},"manifest_sha256":sha(mp),"e4_outcome_manifest_rows":e4_rows,"e4_outcome_manifest_bytes":e4_bytes,"excluded_control_rows":control_rows,"validated_success_noncontrol_rows":eligible_rows,"validated_success_noncontrol_bytes":eligible_bytes,"target_bytes":target,"selection_rule":"release asset/member order then size cap only","strict_single_link_eligible_count":len(singles),"strict_single_link_eligible_bytes":sum(x["source_bytes"] for x in singles),"selected":chosen,"selected_bytes":n,"selected_count":len(chosen),"complete_known_inode_group_review_only":{"count":len(groups),"bytes":sum(x["source_bytes"] for x in groups),"selected_count":len(review),"selected_bytes":rn,"groups":groups,"selected":review,"retirement_enabled":False},"excluded_counts":exclude,"payload_hashes_recomputed":False}
def _witness(st):
 return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def verify_asset(zp,asset):
 p=pathlib.Path(zp);before=p.lstat()
 if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):raise RetentionError("release asset is not a regular file")
 if before.st_size!=asset["bytes"] or sha(p)!=asset["sha256"]:raise RetentionError("release ZIP size/SHA mismatch")
 with zipfile.ZipFile(p) as z:
  ii=z.infolist();names=[i.filename for i in ii]
  if len(names)!=len(set(names)):raise RetentionError("duplicate members")
  for i in ii:
   relpath(i.filename);typ=stat.S_IFMT((i.external_attr>>16)&0xffff)
   if typ not in (0,stat.S_IFREG,stat.S_IFDIR):raise RetentionError("unsafe ZIP member mode")
  if z.testzip() is not None:raise RetentionError("ZIP CRC failure")
 after=p.lstat()
 if _witness(before)!=_witness(after):raise RetentionError("release asset changed during whole-file verification")
 return _witness(after)
def check_member(zp,row,witness=None):
 p=pathlib.Path(zp);before=p.lstat()
 if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):raise RetentionError("member source is not regular")
 if witness is not None and _witness(before)!=witness:raise RetentionError("release asset changed after verification")
 with zipfile.ZipFile(p) as z:
  found=[i for i in z.infolist() if i.filename==row["archive_member"]]
  if len(found)!=1:raise RetentionError("missing/duplicate member")
  i=found[0]
  if i.file_size!=row["source_bytes"] or "%08x"%i.CRC!=row["archive_crc32"].lower():raise RetentionError("member size/CRC mismatch")
  h=hashlib.sha256();n=0
  with z.open(i) as f:
   for b in iter(lambda:f.read(4<<20),b""):h.update(b);n+=len(b)
 after=p.lstat()
 if _witness(before)!=_witness(after) or (witness is not None and _witness(after)!=witness):raise RetentionError("release asset changed during member verification")
 if n!=row["source_bytes"] or h.hexdigest()!=row["source_sha256"]:raise RetentionError("member SHA mismatch")
def check_zip(zp,asset,row):
 witness=verify_asset(zp,asset);check_member(zp,row,witness);return witness

def state(p):
 p=pathlib.Path(p)
 if not p.exists():return {"schema":INDEX,"retired":[],"restore_required":False}
 x=json.loads(p.read_text())
 if x.get("schema")!=INDEX:raise RetentionError("bad state")
 return x
_GUARD_FDS=[];_HOLD_DOC=None;_HOLD_PATH=None;_OWNER_SNAPSHOT=None
def _proc_start(pid):
 text=pathlib.Path("/proc/%d/stat"%pid).read_text();tail=text[text.rfind(")")+2:].split()
 return tail[19]
def _script_matches(argv,cwd,rt,names):
 rt=pathlib.Path(rt).resolve();cwd=pathlib.Path(cwd).resolve()
 if "-c" in argv or "-m" in argv:return False
 for token in argv:
  if not token.endswith((".py",".sh")):continue
  q=pathlib.Path(token)
  if not q.is_absolute():q=cwd/q
  try:q=q.resolve()
  except OSError:continue
  targets={(rt/n).resolve() if n.endswith(".sh") else (rt/"source"/n).resolve() for n in names}
  if q in targets:return True
 return False
def _controller_identity(rt):
 rt=pathlib.Path(rt).resolve();owner=json.loads((rt/"owner.json").read_text());pid=int(owner["pid"])
 if _proc_start(pid)!=str(owner["process_start_ticks"]):raise RetentionError("controller PID/start ticks changed")
 if os.stat("/proc/%d"%pid).st_uid!=os.getuid():raise RetentionError("controller UID mismatch")
 if sha(rt/"source/controller.py")!=owner["code_sha256"]:raise RetentionError("controller source hash mismatch")
 cmd=pathlib.Path("/proc/%d/cmdline"%pid).read_bytes().split(b"\0")
 argv=[x.decode(errors="replace") for x in cmd if x]
 cwd=pathlib.Path(os.readlink("/proc/%d/cwd"%pid))
 if not _script_matches(argv,cwd,rt,("controller.py",)):raise RetentionError("controller argv/cwd identity mismatch")
 return {"pid":pid,"process_start_ticks":str(owner["process_start_ticks"]),"code_sha256":owner["code_sha256"],"instance_id":owner.get("instance_id"),"uid":os.stat("/proc/%d"%pid).st_uid}

def terminal_evidence(rt,expected_tasks=6270):
 rt=pathlib.Path(rt).resolve()
 marker=json.loads((rt/"EXECUTION_TERMINAL.json").read_text())
 records=registry(rt/"registry.sqlite")
 if marker.get("tasks")!=expected_tasks or len(records)!=expected_tasks or any(x.get("status")!="validated_terminal" for x in records.values()):
  raise RetentionError("terminal marker does not bind all planned terminal tasks")
 owner=json.loads((rt/"owner.json").read_text())
 if owner.get("code_sha256")!=sha(rt/"source/controller.py"):raise RetentionError("terminal controller source binding mismatch")
 return {"tasks":len(records),"terminal_marker_utc":marker.get("observed_utc")}
def _check_quiescent(rt,controller_pid):
 rt=pathlib.Path(rt).resolve();reg=registry(rt/"registry.sqlite")
 if any(x.get("status") in ("dispatching","running","worker_active","validating") for x in reg.values()):
  raise RetentionError("active registry task exists")
 worker_names=("run_controller.py","controller.py","phase_worker.py","worker.py","parallel_rf/worker.py","run_batch.py","commit_batch_child.py","cold_auto_compaction.py","finalize_project.py","run_finalizer.sh","audit_artifacts.py","calibration_replay.py","calibration_replay_supervisor.py")
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit() or int(proc.name)==os.getpid() or (controller_pid is not None and int(proc.name)==controller_pid):continue
  try:
   argv=[x.decode(errors="replace") for x in (proc/"cmdline").read_bytes().split(b"\0") if x]
   cwd=pathlib.Path(os.readlink(proc/"cwd"))
  except OSError:continue
  if _script_matches(argv,cwd,rt,worker_names):raise RetentionError("project worker/storage/finalizer process is active")
def quiet(rt,floor,allow_terminal=False):
 global _HOLD_DOC,_HOLD_PATH,_OWNER_SNAPSHOT
 import fcntl,secrets
 rt=pathlib.Path(rt).resolve();hold=rt/"ADMISSION_HOLD.json"
 if hold.exists():raise RetentionError("foreign admission hold present")
 # Serialize scheduled and manual storage drivers for the complete operation.
 for lockpath in (rt/"locks/cold_auto_compaction.lock",rt/"batch-wrapper.lock"):
  lockpath.parent.mkdir(parents=True,exist_ok=True)
  if lockpath.exists() and stat.S_ISLNK(lockpath.lstat().st_mode):raise RetentionError("archive lock path is a symlink")
  fd=os.open(lockpath,os.O_RDWR|os.O_CREAT,0o600)
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:os.close(fd);release_guard();raise RetentionError("archive driver lock busy")
  _GUARD_FDS.append(fd)
 # O_EXCL owns the pause marker; foreign holds are never changed.
 nonce=secrets.token_hex(16);op="release-retention-"+str(os.getpid())+"-"+nonce[:8]
 _HOLD_DOC={"owner_operation":"release_retention_20261030","nonce":nonce,"operation_id":op,"created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"reason":"short verified release-array retention or restore operation"}
 fd=os.open(hold,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);_HOLD_PATH=hold
 with os.fdopen(fd,"w") as f:json.dump(_HOLD_DOC,f);f.flush();os.fsync(f.fileno())
 hfd=os.open(hold.parent,os.O_RDONLY);os.fsync(hfd);os.close(hfd)
 try:
  try:
   _OWNER_SNAPSHOT=_controller_identity(rt);_check_quiescent(rt,int(_OWNER_SNAPSHOT["pid"]))
  except Exception:
   if not allow_terminal:raise
   terminal_evidence(rt);_OWNER_SNAPSHOT=None;_check_quiescent(rt,None)
  if floor<20*GIB:
   if not allow_terminal:raise RetentionError("sub-20 GiB floor is restore-only after terminal completion")
   terminal_evidence(rt);_check_quiescent(rt,None)
  # Root guardian owns this lock throughout the missing-native interval.
  guardpath=rt/"finalize.lock"
  if not guardpath.exists() or stat.S_ISLNK(guardpath.lstat().st_mode):raise RetentionError("finalize guardian lock is absent or unsafe")
  gfd=os.open(guardpath,os.O_RDWR)
  try:
   try:
    fcntl.flock(gfd,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(gfd,fcntl.LOCK_UN)
    raise RetentionError("finalize guardian lock is not held")
   except BlockingIOError:pass
  finally:os.close(gfd)
  if shutil.disk_usage(rt).free<floor:raise RetentionError("configured disk floor not met")
 except Exception:
  release_guard();raise

def release_guard():
 global _HOLD_DOC,_HOLD_PATH,_OWNER_SNAPSHOT
 import fcntl
 if _HOLD_PATH is not None and _HOLD_DOC is not None:
  try:
   current=json.loads(_HOLD_PATH.read_text())
   if current.get("owner_operation")==_HOLD_DOC["owner_operation"] and current.get("nonce")==_HOLD_DOC["nonce"] and current.get("operation_id")==_HOLD_DOC["operation_id"]:
    _HOLD_PATH.unlink();fd=os.open(_HOLD_PATH.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
  finally:_HOLD_PATH=None;_HOLD_DOC=None
 for fd in reversed(_GUARD_FDS):
  with contextlib.suppress(OSError):fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 _GUARD_FDS.clear()

def download(repo,tag,name,dest):
 p=subprocess.run(["gh","release","download",tag,"--repo",repo,"--pattern",name,"--dir",str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RetentionError("gh asset download failed")
 xs=[x for x in pathlib.Path(dest).iterdir() if x.is_file() and x.name==name]
 if len(xs)!=1:raise RetentionError("requested asset not uniquely downloaded")
 return xs[0]
def _check_group(root,row,hash_payload=True):
 paths=row.get("native_paths") or []
 if not paths or len(paths)!=row.get("link_count") or len(set(paths))!=len(paths):
  raise RetentionError("incomplete inode group")
 sts=[]
 for rel in paths:
  p=path(root,rel);st=p.lstat()
  if not stat.S_ISREG(st.st_mode) or st.st_size!=row["source_bytes"]:raise RetentionError("unsafe inode group member")
  sts.append(st)
 first=sts[0]
 if any((x.st_dev,x.st_ino,x.st_size,x.st_nlink,x.st_mtime_ns)!=(first.st_dev,first.st_ino,first.st_size,first.st_nlink,first.st_mtime_ns) for x in sts):raise RetentionError("inode group identity mismatch")
 if first.st_nlink!=len(paths):raise RetentionError("unaccounted hardlink in group")
 if hash_payload and sha(path(root,row["source_path"]))!=row["source_sha256"]:raise RetentionError("inode group source SHA mismatch")
 return first
def verify_native_single(root,row):
 p=path(root,row["source_path"]);before=p.lstat()
 if before.st_nlink!=1 or not stat.S_ISREG(before.st_mode) or before.st_size!=row["source_bytes"] or sha(p)!=row["source_sha256"]:raise RetentionError("native source SHA/size/link mismatch")
 after=p.lstat()
 if _witness(before)!=_witness(after):raise RetentionError("native source changed during verification")
 return p,before
def retire(a):
 root=pathlib.Path(a.root).resolve();quiet(root/"runtime_20261025",a.disk_floor)
 m=json.loads(pathlib.Path(a.manifest).read_text());am={x["name"]:x for x in m["assets"]};pl=json.loads(pathlib.Path(a.plan).read_text())
 if pl.get("schema")!=SCHEMA or pl.get("manifest_sha256")!=sha(a.manifest):raise RetentionError("plan manifest binding mismatch")
 if a.execute:
  if not a.approval:raise RetentionError("root approval required")
  ap=json.loads(pathlib.Path(a.approval).read_text())
  if ap.get("schema")!=APPROVAL or ap.get("approved") is not True or ap.get("plan_sha256")!=sha(a.plan):raise RetentionError("approval binding mismatch")
  if a.include_groups and ap.get("allow_complete_known_groups") is not True:raise RetentionError("approval does not authorize inode groups")
 state0=state(a.state)
 if state0.get("restore_required"):raise RetentionError("prior retirement still requires restore")
 retired_paths={p for old in state0["retired"] for p in (old.get("native_paths") or [old["source_path"]])}
 cache=pathlib.Path(a.cache);cache.mkdir(parents=True,exist_ok=True);out={"status":"verified_only","verified":[],"retired":[]}
 rows=list(pl.get("selected",[]))
 if a.include_groups:rows+=list(pl.get("complete_known_inode_group_review_only",{}).get("selected",[]))
 order={x["name"]:i for i,x in enumerate(m["assets"])};rows.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]))
 verified_asset=None
 current_registry=registry(root/"runtime_20261025/registry.sqlite")
 consumers={dep for kk,x in current_registry.items() for dep in (x.get("dependencies") or []) if kk!=dep}
 if any(not valid_task(current_registry.get(x["task_key"]),x["task_key"]) or x["task_key"] in consumers for x in rows):
  raise RetentionError("registry task/consumer eligibility changed")
 for r in rows:
  if r["source_path"] in retired_paths or any(p in retired_paths for p in r.get("native_paths",[])):raise RetentionError("source already appears in retirement history")
  group=bool(r.get("review_only"))
  task=current_registry.get(r["task_key"])
  vp=path(root,r["validation_path"])
  if sha(vp)!=r["validation_sha256"] or not valid_manifest_binding(root,r["source_path"],task,r["source_sha256"]):raise RetentionError("saved validation evidence changed")
  if group:
   if not a.include_groups:raise RetentionError("inode group requires explicit review mode")
   before=_check_group(root,r)
  else:
   if r.get("aliases"):raise RetentionError("strict retirement rejects aliases")
   p,before=verify_native_single(root,r)
  asset=am[r["asset"]]
  if asset["bytes"]>1*GIB:raise RetentionError("release asset exceeds one-GiB cache bound")
  z=cache/asset["name"]
  for old in list(cache.iterdir()):
   if old==z:continue
   oldmeta=am.get(old.name)
   if old.is_symlink() or not old.is_file() or not oldmeta or old.stat().st_size!=oldmeta["bytes"] or sha(old)!=oldmeta["sha256"]:raise RetentionError("unverified cache entry; refusing eviction")
   old.unlink()
  if not z.exists():
   if shutil.disk_usage(root).free < a.disk_floor+asset["bytes"]:raise RetentionError("download would cross 20 GiB disk floor")
   got=download(a.repo,a.tag,asset["name"],cache);os.replace(got,z)
  if len(list(cache.iterdir()))!=1:raise RetentionError("cache must contain at most one release asset")
  if z.is_symlink():raise RetentionError("cached asset is a symlink")
  ast=z.lstat()
  marker=(asset["name"],ast.st_dev,ast.st_ino,ast.st_size,ast.st_mtime_ns)
  if marker!=verified_asset:
   asset_witness=verify_asset(z,asset);verified_asset=(marker,asset_witness)
  else:asset_witness=verified_asset[1]
  check_member(z,r,asset_witness);out["verified"].append(r["source_path"])
  if a.execute:
   rt=root/"runtime_20261025"
   if _controller_identity(rt)!=_OWNER_SNAPSHOT:raise RetentionError("controller identity changed during retention")
   if group:now=_check_group(root,r)
   else:p,now=verify_native_single(root,r)
   if _witness(now)!=_witness(before) or now.st_nlink!=before.st_nlink:raise RetentionError("native identity changed before unlink")
   if shutil.disk_usage(root).free<a.disk_floor:raise RetentionError("disk floor changed before unlink")
   source_fd=os.open(path(root,r["source_path"]),os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
   try:
    opened=os.fstat(source_fd)
    if _witness(opened)!=_witness(before) or opened.st_nlink!=before.st_nlink:raise RetentionError("opened source identity changed")
    entry={**r,"retirement_kind":"complete_inode_group" if group else "single_link","original_mode":stat.S_IMODE(before.st_mode),"asset_name":asset["name"],"asset_bytes":asset["bytes"],"asset_sha256":asset["sha256"],"verified_copy_path":str(z),"repo":a.repo,"tag":a.tag,"plan_sha256":sha(a.plan),"manifest_sha256":pl["manifest_sha256"],"retirement_started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    state0["retired"].append(entry);state0["restore_required"]=True;atomic(a.state,state0)
    paths=( [x for x in r["native_paths"] if x!=r["source_path"]]+[r["source_path"]] ) if group else [r["source_path"]]
    # Remove aliases first, canonical pathname last. Durable index precedes every unlink.
    for removed,rel in enumerate(paths):
     if os.fstat(source_fd).st_nlink!=before.st_nlink-removed:raise RetentionError("unaccounted hardlink appeared during unlink")
     q=path(root,rel);st=q.lstat()
     if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns):raise RetentionError("group changed during unlink")
     q.unlink();fd=os.open(q.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
     state0["retired"][-1].setdefault("unlinked_paths",[]).append(rel);atomic(a.state,state0)
    if os.fstat(source_fd).st_nlink!=0:raise RetentionError("unaccounted hardlink remains after retirement")
   finally:os.close(source_fd)
   out["retired"].append(r["source_path"])
 if a.execute:out["status"]="retired"
 atomic(a.log,out);return out
def restore(a):
 root=pathlib.Path(a.root).resolve();st=state(a.state);done=[];cache=pathlib.Path(a.cache);verified_assets={}
 cache.mkdir(parents=True,exist_ok=True)
 try:cache.resolve().relative_to(root)
 except ValueError:raise RetentionError("cache must remain inside project root")
 if cache.is_symlink():raise RetentionError("cache path is a symlink")
 for r in st["retired"]:
  zp=cache/r.get("asset_name",pathlib.Path(r["verified_copy_path"]).name)
  paths=r.get("native_paths") if r.get("retirement_kind")=="complete_inode_group" else [r["source_path"]]
  missing_bytes=sum(x["source_bytes"] for x in st["retired"] if any(not path(root,y,True).exists() for y in (x.get("native_paths") or [x["source_path"]])))
  download_bytes=0 if zp.exists() else r["asset_bytes"]
  if shutil.disk_usage(root).free < getattr(a,"disk_floor",20*GIB)+missing_bytes+download_bytes:raise RetentionError("restore would cross configured disk floor")
  if not zp.exists():
   for old in list(cache.iterdir()):
    if old==zp:continue
    matches=[x for x in st["retired"] if x.get("asset_name")==old.name]
    if old.is_symlink() or not old.is_file() or not matches or old.stat().st_size!=matches[0]["asset_bytes"] or sha(old)!=matches[0]["asset_sha256"]:raise RetentionError("unverified cache entry; refusing eviction")
    old.unlink()
   repo=getattr(a,"repo",None) or r.get("repo");tag=getattr(a,"tag",None) or r.get("tag")
   if not repo or not tag:raise RetentionError("restore needs bound GitHub repo/tag")
   zp=download(repo,tag,zp.name,cache)
  if len(list(cache.iterdir()))!=1:raise RetentionError("cache must contain at most one release asset")
  if zp.is_symlink() or not zp.is_file():raise RetentionError("retained ZIP path unsafe")
  ast=zp.lstat();marker=(r.get("asset_name",zp.name),_witness(ast))
  if marker not in verified_assets:verified_assets[marker]=verify_asset(zp,{"bytes":r["asset_bytes"],"sha256":r["asset_sha256"]})
  witness=verified_assets[marker]
  check_member(zp,r,witness)
  if not paths:raise RetentionError("retired entry lacks paths")
  existing=[]
  for rel in paths:
   dst=path(root,rel,True)
   if dst.exists() or dst.is_symlink():
    ss=dst.lstat()
    if not stat.S_ISREG(ss.st_mode) or ss.st_size!=r["source_bytes"] or sha(dst)!=r["source_sha256"] or stat.S_IMODE(ss.st_mode)!=r.get("original_mode",stat.S_IMODE(ss.st_mode)):
     raise RetentionError("restore conflict; refusing overwrite")
    existing.append((rel,dst,ss))
  if len(existing)==len(paths):
   if len(paths)>1:
    if len({(x[2].st_dev,x[2].st_ino) for x in existing})!=1:raise RetentionError("existing inode group topology conflicts")
    _check_group(root,r)
   elif existing[0][2].st_nlink!=1:raise RetentionError("single-link restore has unexpected hardlinks")
   done.append(r["source_path"]);continue
  if r.get("retirement_kind")=="complete_inode_group" and existing:
   dev,ino=existing[0][2].st_dev,existing[0][2].st_ino
   if any((x[2].st_dev,x[2].st_ino)!=(dev,ino) for x in existing):raise RetentionError("partial restore inode topology conflict")
   if existing[0][2].st_nlink!=len(existing):raise RetentionError("partial restore has unaccounted hardlinks")
   source=existing[0][1]
   for rel in paths:
    dst=path(root,rel,True)
    if dst.exists() or dst.is_symlink():continue
    os.link(source,dst,follow_symlinks=False);fd=os.open(dst.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
  else:
   # Restore a single file (or the first group link) from the verified member.
   rel=next(x for x in paths if not path(root,x,True).exists())
   dst=path(root,rel,True);dst.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=dst.parent,prefix="."+dst.name+".")
   try:
    h=hashlib.sha256();n=0
    with zipfile.ZipFile(zp) as z, z.open(r["archive_member"]) as src, os.fdopen(fd,"wb") as out:
     for b in iter(lambda:src.read(4<<20),b""):out.write(b);h.update(b);n+=len(b)
     out.flush();os.fchmod(out.fileno(),r.get("original_mode",0o644));os.fsync(out.fileno())
    if n!=r["source_bytes"] or h.hexdigest()!=r["source_sha256"]:raise RetentionError("restored bytes mismatch")
    if dst.exists() or dst.is_symlink():raise RetentionError("restore target appeared")
    os.replace(tmp,dst);d=os.open(dst.parent,os.O_RDONLY);os.fsync(d);os.close(d)
   finally:
    with contextlib.suppress(FileNotFoundError):os.unlink(tmp)
   if r.get("retirement_kind")=="complete_inode_group":
    source=dst
    for rel2 in paths:
     d2=path(root,rel2,True)
     if d2==source:continue
     if d2.exists() or d2.is_symlink():raise RetentionError("restore target conflict")
     os.link(source,d2,follow_symlinks=False);fd=os.open(d2.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
  # Confirm complete exact group and source bytes after publication.
  if r.get("retirement_kind")=="complete_inode_group":
   _check_group(root,r)
  else:
   p=path(root,r["source_path"])
   if p.stat().st_size!=r["source_bytes"] or sha(p)!=r["source_sha256"]:raise RetentionError("restored file mismatch")
  done.append(r["source_path"])
 st["restore_required"]=False;st["last_restore_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime());atomic(a.state,st)
 return {"restored":done,"restore_required":False}

def main():
 p=argparse.ArgumentParser();ss=p.add_subparsers(dest="cmd",required=True);q=ss.add_parser("plan")
 for x in ("root","manifest","registry","output"):q.add_argument("--"+x,required=True)
 q.add_argument("--target-bytes",type=int,default=2*GIB)
 q=ss.add_parser("verify-retire")
 for x in ("root","manifest","plan","state","cache","log","repo","tag"):q.add_argument("--"+x,required=True)
 q.add_argument("--disk-floor",type=int,default=20*GIB);q.add_argument("--approval");q.add_argument("--execute",action="store_true");q.add_argument("--include-groups",action="store_true")
 q=ss.add_parser("restore")
 for x in ("root","state","cache"):q.add_argument("--"+x,required=True)
 q.add_argument("--repo");q.add_argument("--tag");q.add_argument("--disk-floor",type=int,default=20*GIB)
 q=ss.add_parser("status");q.add_argument("--state",required=True);a=p.parse_args()
 try:
  if a.cmd=="plan":out=make_plan(a.root,a.manifest,a.registry,a.target_bytes);atomic(a.output,out)
  elif a.cmd=="verify-retire":out=retire(a)
  elif a.cmd=="restore":
   quiet(pathlib.Path(a.root)/"runtime_20261025",a.disk_floor,allow_terminal=True);out=restore(a)
  else:
   s=state(a.state);out={"retired_count":len(s["retired"]),"retired_bytes":sum(x["source_bytes"] for x in s["retired"]),"restore_required":s.get("restore_required",False)}
  print(json.dumps(out,sort_keys=True));return 0
 except (RetentionError,OSError,ValueError,KeyError,sqlite3.Error,zipfile.BadZipFile,RuntimeError) as e:print(json.dumps({"status":"blocked","reason":str(e)}),file=sys.stderr);return 2
 finally:release_guard()
if __name__=="__main__":raise SystemExit(main())
