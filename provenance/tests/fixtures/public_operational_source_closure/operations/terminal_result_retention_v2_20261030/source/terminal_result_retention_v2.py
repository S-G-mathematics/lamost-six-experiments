#!/usr/bin/env python3
"""Prospective terminal E3-E6 outcome retention; independent 10 GiB storage budget."""
import argparse,contextlib,hashlib,json,os,pathlib,shutil,sqlite3,stat,subprocess,sys,tempfile,time,zipfile
SCHEMA="lamost-terminal-result-retention-plan/2"; INDEX="lamost-terminal-result-retention-index/2"; APPROVAL="lamost-terminal-result-retention-approval/2"; GIB=1<<30; MAX_TARGET=10*GIB; SUPPORTED_EXPERIMENTS=(3,4,5,6); STANDARD_RETIRE_PROFILE="scientific-floor-20gib-v1"; CLEANUP_RETIRE_PROFILE="verified-terminal-eval-outcomes-cleanup-6gib-v1"
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
def registry_records_for(p,keys):
 expected=list(dict.fromkeys(keys))
 if not expected or any(not isinstance(k,str) or not k for k in expected):raise RetentionError("inode owner key set is missing or malformed")
 placeholders=",".join("?" for _ in expected)
 c=sqlite3.connect("file:"+str(pathlib.Path(p).resolve())+"?mode=ro",uri=True)
 try:rows=c.execute("select key,record from tasks where key in ("+placeholders+")",expected).fetchall()
 finally:c.close()
 if len(rows)!=len(expected) or {k for k,_ in rows}!=set(expected):raise RetentionError("inode owner record missing or duplicated")
 out={}
 for key,raw in rows:
  try:record=json.loads(raw)
  except (TypeError,ValueError):raise RetentionError("inode owner record is malformed")
  if not isinstance(record,dict):raise RetentionError("inode owner record is not an object")
  out[key]=record
 return out

def registry(p):
 c=sqlite3.connect("file:"+str(pathlib.Path(p).resolve())+"?mode=ro",uri=True)
 try:return {k:json.loads(v) for k,v in c.execute("select key,record from tasks")}
 finally:c.close()
def taskkey(s):
 pre="runtime_20261025/artifacts/";suf="/test_outcomes.npz"
 if not isinstance(s,str) or not s.startswith(pre) or not s.endswith(suf):return None
 k=s[len(pre):]
 if "/attempts/" in k:
  base,tail=k.split("/attempts/",1);parts=tail.split("/")
  if len(parts)!=2 or parts[1]!="test_outcomes.npz" or not parts[0] or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in parts[0]):return None
  k=base
 else:k=k[:-len(suf)]
 family=k.split("/",1)[0]
 return k if family in ("e3","e4","e5","e6") and ("/eval/" in k or k.endswith("/eval")) else None

def retirement_profile_for(floor,cleanup_profile=None):
 if floor==20*GIB and cleanup_profile in (None,STANDARD_RETIRE_PROFILE):return STANDARD_RETIRE_PROFILE
 if floor==6*GIB and cleanup_profile==CLEANUP_RETIRE_PROFILE:return CLEANUP_RETIRE_PROFILE
 raise RetentionError("retirement requires the explicit 6 GiB cleanup profile or the 20 GiB standard profile")

def has_nonterminal_reference(registry,owner_keys,physical_paths):
 """Ignore only exact validated-terminal consumers; fail closed otherwise."""
 owners=set(owner_keys); paths=set(physical_paths)
 def references(value):
  if isinstance(value,str):return value in owners or value in paths
  if isinstance(value,dict):return any(references(v) for v in value.values())
  if isinstance(value,(list,tuple)):return any(references(v) for v in value)
  return False
 for key,record in registry.items():
  if key in owners:continue
  if not isinstance(record,dict):return True
  if record.get("status")!="validated_terminal" and references(record):return True
 return False

def valid_task(t,k):
 if not t or not k or t.get("key")!=k or t.get("kind")!="eval" or t.get("status")!="validated_terminal" or t.get("outcome")!="successful" or t.get("validation_state")!="validated" or t.get("scientific_case") is not True:return False
 try:exp=int(k.split("/",1)[0][1:])
 except (ValueError,IndexError):return False
 return exp in SUPPORTED_EXPERIMENTS and t.get("experiment")==exp
def validation_evidence(root,s,t,sha0):
 k=taskkey(s);rel="runtime_20261025/artifacts/"+str(k)+"/validation.json"
 try:
  vp=path(root,rel);raw=vp.read_bytes();v=json.loads(raw)
 except (OSError,ValueError,RetentionError):return None
 if v.get("status")!="validated" or v.get("task_key")!=k or v.get("files",{}).get("test_outcomes.npz")!=sha0:return None
 return rel,hashlib.sha256(raw).hexdigest()
def valid_manifest_binding(root,s,t,sha0):
 return validation_evidence(root,s,t,sha0) is not None

def _project_evidence(root, path_value, digest, memo):
 if not isinstance(path_value,str) or not isinstance(digest,str) or len(digest)!=64:return False
 try:
  p=pathlib.Path(path_value)
  if not p.is_absolute():p=pathlib.Path(root)/path_value
  st=p.lstat()
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):return False
  p=p.resolve(strict=True);p.relative_to(pathlib.Path(root).resolve())
  got=memo.get(str(p))
  if got is None:got=sha(p);memo[str(p)]=got
  return got==digest
 except (OSError,ValueError,RetentionError):return False

def _remote_asset_identity_matches(doc,name,nbytes,digest):
 if not isinstance(doc,dict) or not isinstance(name,str) or not isinstance(nbytes,int) or not isinstance(digest,str) or len(digest)!=64:return False
 schema=doc.get("schema")
 if isinstance(doc.get("assets"),list):
  matches=[x for x in doc["assets"] if isinstance(x,dict) and x.get("name")==name]
  return (doc.get("published") is True and doc.get("all_remote_sizes_and_sha256_match") is True
          and doc.get("all_member_sizes_and_crc_metadata_match") is True and len(matches)==1
          and matches[0].get("bytes")==nbytes and matches[0].get("sha256")==digest)
 if schema=="lamost-remote-verified-release-asset-locator/1":
  return (doc.get("asset_name")==name and doc.get("bytes")==nbytes and doc.get("sha256")==digest
          and doc.get("github_digest")=="sha256:"+digest and doc.get("repo")=="S-G-mathematics/lamost-six-experiments"
          and doc.get("local_zip_crc_checked") is True and isinstance(doc.get("asset_id"),int))
 if schema=="lamost-release-asset-verification/1":
  return (doc.get("asset_name")==name and doc.get("bytes")==nbytes and doc.get("sha256")==digest
          and doc.get("downloaded_remote_asset_sha256_matches_local") is True and doc.get("remote_asset_size_matches") is True
          and doc.get("zip_crc_pass") is True)
 if schema=="lamost-terminal-result-array-delta-remote-verification/1":
  return (doc.get("asset_name")==name and doc.get("asset_bytes")==nbytes and doc.get("asset_sha256")==digest
          and doc.get("github_api_digest")=="sha256:"+digest and doc.get("remote_download_sha256")==digest
          and doc.get("remote_download_bytes")==nbytes and doc.get("remote_download_zip_crc_test") is True
          and doc.get("member_sha_size_crc_verified") is True and doc.get("asset_state")=="uploaded"
          and doc.get("repository")=="S-G-mathematics/lamost-six-experiments")
 return False

def _verified_asset_evidence(root,evidence_path,evidence_sha,name,nbytes,digest,memo):
 if not _project_evidence(root,evidence_path,evidence_sha,memo):return False
 try:
  p=pathlib.Path(evidence_path)
  if not p.is_absolute():p=pathlib.Path(root)/p
  doc=json.loads(p.read_text())
 except (OSError,ValueError):return False
 return _remote_asset_identity_matches(doc,name,nbytes,digest)

def _future_input_source_proof(root):
 rt=pathlib.Path(root).resolve()/"runtime_20261025"
 fp=rt/"manifests/freeze.json"
 if fp.is_symlink() or not fp.is_file():raise RetentionError("execution freeze is unavailable for future-input proof")
 freeze=json.loads(fp.read_text());pins=freeze.get("source_sha256",{});bindings=[]
 for rel in ("worker.py","science.py"):
  expected=pins.get(rel);src=rt/"source"/rel
  if not isinstance(expected,str) or len(expected)!=64 or src.is_symlink() or not src.is_file() or sha(src)!=expected:
   raise RetentionError("scientific input/output source differs from frozen binding: "+rel)
  bindings.append({"runtime_member":"runtime_20261025/source/"+rel,"sha256":expected})
 return {"schema":"lamost-terminal-result-input-safety/1","source_bindings":bindings,
         "consumer_scan":"exact task-key and physical outcome-path references across every registry record; candidates referenced by future fit/eval inputs are excluded",
         "payload_policy":"test_outcomes.npz only; model/data/role/selection artifacts are never candidates"}

def build_physical_outcome_inventory(root):
 root=pathlib.Path(root).resolve();base=root/"runtime_20261025/artifacts"
 records=[];by_inode={};unsafe_symlink={}
 if not base.is_dir():raise RetentionError("artifact tree missing for physical alias inventory")
 for dirpath,dirs,files in os.walk(base,followlinks=False):
  dirs.sort();files.sort()
  for name in files:
   if name!="test_outcomes.npz":continue
   p=pathlib.Path(dirpath)/name
   rel=p.relative_to(root).as_posix()
   st=p.lstat()
   if stat.S_ISLNK(st.st_mode):
    try:
     target=p.resolve(strict=True);tst=target.stat()
     if stat.S_ISREG(tst.st_mode):unsafe_symlink.setdefault((tst.st_dev,tst.st_ino),[]).append(rel)
    except OSError:pass
    records.append({"path":rel,"kind":"symlink","mode":stat.S_IMODE(st.st_mode)})
    continue
   if not stat.S_ISREG(st.st_mode):
    records.append({"path":rel,"kind":"nonregular","mode":stat.S_IMODE(st.st_mode)})
    continue
   row={"path":rel,"kind":"regular","dev":st.st_dev,"ino":st.st_ino,"size":st.st_size,"nlink":st.st_nlink,"mtime_ns":st.st_mtime_ns}
   records.append(row);by_inode.setdefault((st.st_dev,st.st_ino),[]).append(row)
 normalized={f"{dev}:{ino}":{"paths":sorted(x["path"] for x in rows),"nlink":rows[0]["nlink"],"size":rows[0]["size"],"unsafe_symlink_paths":sorted(unsafe_symlink.get((dev,ino),[]))} for (dev,ino),rows in by_inode.items()}
 doc={"schema":"lamost-terminal-result-physical-inode-inventory/1","runtime_member":"runtime_20261025/artifacts","file_count":len(records),"regular_inode_count":len(by_inode),"records":records,"inode_groups":normalized,"payload_bytes_read":0}
 raw=json.dumps(doc,sort_keys=True,separators=(",",":")).encode()
 return doc,hashlib.sha256(raw).hexdigest()

def validate_catalog_receipt(root,mp,catalog_doc,catalog_sha):
 root=pathlib.Path(root).resolve();mp=pathlib.Path(mp).resolve(strict=True)
 matches=[]
 for receiptp in sorted(mp.parent.glob("*RECEIPT*.json")):
  if receiptp.is_symlink() or not receiptp.is_file():continue
  try:receipt=json.loads(receiptp.read_text());bound=pathlib.Path(receipt.get("catalog_path","")).resolve()
  except (OSError,ValueError):continue
  if (receipt.get("schema") in {"lamost-terminal-result-retention-catalog-receipt/1","lamost-terminal-result-retention-catalog-receipt/2"} and
      bound==mp and receipt.get("catalog_sha256")==catalog_sha):matches.append((receiptp,receipt))
 if len(matches)!=1:raise RetentionError("exactly one safe receipt must bind the catalog")
 receiptp,receipt=matches[0];memo={}
 for pk,sk in (("payloads_csv_path","payloads_csv_sha256"),("cases_csv_path","cases_csv_sha256")):
  cp0=pathlib.Path(receipt.get(pk,""))
  if cp0.is_symlink():raise RetentionError("catalog CSV path is a symlink")
  cp=cp0.resolve(strict=True)
  if cp.parent!=mp.parent or not _project_evidence(root,str(cp),receipt.get(sk),memo):raise RetentionError("catalog CSV receipt binding mismatch")
 return receiptp,sha(receiptp),receipt

def make_plan(root,mp,rp,target=10*GIB,experiments=SUPPORTED_EXPERIMENTS,retirement_profile=STANDARD_RETIRE_PROFILE):
 if retirement_profile not in (STANDARD_RETIRE_PROFILE,CLEANUP_RETIRE_PROFILE):raise RetentionError("unknown cleanup retirement profile")
 if not isinstance(target,int) or target<0 or target>MAX_TARGET:raise RetentionError("storage retention plan target is capped at 10 GiB")
 scope=tuple(sorted(set(int(x) for x in experiments)))
 if not scope or any(x not in SUPPORTED_EXPERIMENTS for x in scope):raise RetentionError("retention scope must be E3-E6 evaluation outcomes")
 root=pathlib.Path(root).resolve();mp=pathlib.Path(mp)
 if mp.is_symlink() or not mp.is_file():raise RetentionError("catalog/manifest path is unsafe")
 mp=mp.resolve(strict=True);catalog_sha=sha(mp);m=json.loads(mp.read_text());new_catalog=m.get("schema")=="lamost-terminal-result-retention-catalog/1"
 if m.get("schema")=="lamost-scientific-array-release/1":rows_in=m.get("files",[]);receipt_sha=None
 elif new_catalog:
  rows_in=m.get("payload_records",[])
  receiptp,receipt_sha,receipt=validate_catalog_receipt(root,mp,m,catalog_sha)
  rows_in=m.get("payload_records",[])
 else:raise RetentionError("unsupported published-member catalog schema")
 assets=m.get("assets",[])
 if not isinstance(rows_in,list) or not isinstance(assets,list):raise RetentionError("malformed release catalog")
 reg=registry(rp);asset_by_name={a.get("asset_name",a.get("name")):a for a in assets if isinstance(a,dict) and isinstance(a.get("asset_name",a.get("name")),str)}
 physical_inventory,physical_inventory_sha=build_physical_outcome_inventory(root) if new_catalog else (None,None)
 input_source_proof=_future_input_source_proof(root) if new_catalog else None
 physical_groups={}
 if new_catalog:
  physical_groups={(int(k.split(":")[0]),int(k.split(":")[1])):v for k,v in physical_inventory["inode_groups"].items()}
 singles=[];groups=[];exclude={};seen=set();seen_inodes=set();scope_rows=0;scope_bytes=0;eligible_rows=0;eligible_bytes=0;evmemo={}
 for r in rows_in:
  if not isinstance(r,dict):continue
  if not new_catalog and r.get("category","runtime_test_outcomes")!="runtime_test_outcomes":continue
  if new_catalog and r.get("source_kind")!="canonical_validated_test_outcomes":continue
  s=r.get("source_path");k=r.get("task_key") or taskkey(s);family=int(k.split("/",1)[0][1:]) if isinstance(k,str) and k.split("/",1)[0][1:].isdigit() else None
  if family not in scope:continue
  scope_rows+=1
  try:scope_bytes+=int(r.get("source_bytes"))
  except (ValueError,TypeError):exclude["bad_size"]=exclude.get("bad_size",0)+1;continue
  member=r.get("archive_member");status=r.get("asset_member_evidence_status")
  if new_catalog and status!="exact_member_sha_size_crc_verified":
   exclude["published_member_evidence_missing"]=exclude.get("published_member_evidence_missing",0)+1;continue
  if not isinstance(member,str) or not member:
   exclude["published_member_evidence_missing"]=exclude.get("published_member_evidence_missing",0)+1;continue
  if member in seen:raise RetentionError("duplicate release member")
  seen.add(member)
  # Catalog native/retired flags describe its snapshot only. The fresh physical
  # inode inventory below is authoritative after maintenance restoration.
  t=reg.get(k or "")
  if not valid_task(t,k) or taskkey(s)!=k:exclude["not_successful_validated_terminal_eval"]=exclude.get("not_successful_validated_terminal_eval",0)+1;continue
  asset_name=r.get("asset_name",r.get("asset"));asset_rec=asset_by_name.get(asset_name)
  if new_catalog:
   asset_bytes=r.get("asset_bytes");asset_sha=r.get("asset_sha256")
   asset_evidence_path=asset_rec.get("asset_remote_evidence_path") if isinstance(asset_rec,dict) else None
   asset_evidence_sha=asset_rec.get("asset_remote_evidence_sha256") if isinstance(asset_rec,dict) else None
   row_evidence_path=r.get("asset_remote_evidence_path");row_evidence_sha=r.get("asset_remote_evidence_sha256")
   row_evidence_absent=row_evidence_path is None and row_evidence_sha is None
   row_evidence_matches=row_evidence_path==asset_evidence_path and row_evidence_sha==asset_evidence_sha
   member_evidence_ok=_project_evidence(root,r.get("member_record_evidence_path"),r.get("member_record_evidence_sha256"),evmemo)
   remote_evidence_ok=_verified_asset_evidence(root,asset_evidence_path,asset_evidence_sha,asset_name,asset_bytes,asset_sha,evmemo)
   if (not isinstance(asset_rec,dict) or r.get("asset_remote_verified") is not True or asset_rec.get("asset_remote_verified") is not True
       or asset_rec.get("asset_name")!=asset_name or asset_rec.get("asset_bytes")!=asset_bytes or asset_rec.get("asset_sha256")!=asset_sha
       or not isinstance(asset_sha,str) or len(asset_sha)!=64 or not isinstance(asset_bytes,int) or asset_bytes<1
       or not (row_evidence_absent or row_evidence_matches) or not member_evidence_ok or not remote_evidence_ok):
    exclude["published_asset_evidence_missing"]=exclude.get("published_asset_evidence_missing",0)+1;continue
  else:
   asset_bytes=asset_rec.get("bytes") if isinstance(asset_rec,dict) else None
   asset_sha=asset_rec.get("sha256") if isinstance(asset_rec,dict) else None
  if (not isinstance(r.get("source_sha256"),str) or len(r["source_sha256"])!=64
      or not isinstance(r.get("archive_crc32"),str) or len(r["archive_crc32"])!=8
      or not isinstance(asset_rec,dict) or asset_rec.get("asset_remote_verified",asset_rec.get("remote_verified")) is not True
      or status not in ("exact_member_sha_size_crc_verified","exact_member_verified")
      or not isinstance(asset_sha,str) or len(asset_sha)!=64 or not isinstance(asset_bytes,int) or asset_bytes<1):
   exclude["published_member_evidence_missing"]=exclude.get("published_member_evidence_missing",0)+1;continue
  ve=validation_evidence(root,s,t,r["source_sha256"])
  if ve is None:exclude["validation_binding_missing_or_mismatch"]=exclude.get("validation_binding_missing_or_mismatch",0)+1;continue
  aliases=r.get("aliases") or []
  if not isinstance(aliases,list):exclude["bad_alias_metadata"]=exclude.get("bad_alias_metadata",0)+1;continue
  owner_keys=[k]
  if new_catalog:
   # The catalog alias values are logical task keys, not paths. Build the physical
   # group only from the independent artifacts-tree inode inventory.
   try:st0=path(root,s).lstat();g=physical_groups.get((st0.st_dev,st0.st_ino))
   except (OSError,RetentionError):st0=None;g=None
   if not st0 or not g or g.get("nlink")!=st0.st_nlink or len(g.get("paths",[]))!=st0.st_nlink or g.get("unsafe_symlink_paths"):
    exclude["incomplete_inode_group"]=exclude.get("incomplete_inode_group",0)+1;continue
   physical_paths=g["paths"]
   if s not in physical_paths:exclude["incomplete_inode_group"]=exclude.get("incomplete_inode_group",0)+1;continue
   for alias in physical_paths:
    ak=taskkey(alias);at=reg.get(ak or "")
    if not valid_task(at,ak) or validation_evidence(root,alias,at,r["source_sha256"]) is None:
     owner_keys=[];break
    owner_keys.append(ak)
   if not owner_keys:exclude["alias_owner_not_validated_terminal"]=exclude.get("alias_owner_not_validated_terminal",0)+1;continue
  else:
   if len(set([s]+aliases))!=len([s]+aliases):exclude["duplicate_alias"]=exclude.get("duplicate_alias",0)+1;continue
   physical_paths=[s]+aliases
   owner_keys=[]
   for alias in physical_paths:
    ak=taskkey(alias);at=reg.get(ak or "")
    if not valid_task(at,ak):owner_keys=[];break
    av=validation_evidence(root,alias,at,r["source_sha256"])
    if av is None:owner_keys=[];break
    owner_keys.append(ak)
   if not owner_keys:exclude["alias_owner_not_validated_terminal"]=exclude.get("alias_owner_not_validated_terminal",0)+1;continue
  owner_set=set(owner_keys)
  if has_nonterminal_reference(reg,owner_set,physical_paths):
   exclude["active_or_future_consumer"]=exclude.get("active_or_future_consumer",0)+1;continue
  try:p=path(root,s);st=p.lstat()
  except Exception:exclude["missing_or_unsafe_native_source"]=exclude.get("missing_or_unsafe_native_source",0)+1;continue
  if not stat.S_ISREG(st.st_mode) or st.st_size!=int(r["source_bytes"]):exclude["native_size_type"]=exclude.get("native_size_type",0)+1;continue
  inode=(st.st_dev,st.st_ino)
  if inode in seen_inodes:continue
  eligible_rows+=1;eligible_bytes+=int(r["source_bytes"])
  x={q:r.get(q) for q in ("source_path","archive_member","source_bytes","source_sha256","archive_crc32","aliases")}
  x.update({"asset":asset_name,"asset_bytes":asset_bytes,"asset_sha256":asset_sha,"task_key":k,"task_family":family,"owner_task_keys":sorted(set(owner_keys)),"validation_path":ve[0],"validation_sha256":ve[1],"native_dev":st.st_dev,"native_ino":st.st_ino,"native_nlink":st.st_nlink})
  if new_catalog:
   x["asset_remote_evidence_path"]=asset_evidence_path;x["asset_remote_evidence_sha256"]=asset_evidence_sha
   x["asset_remote_evidence_inherited_from_asset_record"]=row_evidence_absent
   x["member_record_evidence_path"]=r.get("member_record_evidence_path");x["member_record_evidence_sha256"]=r.get("member_record_evidence_sha256")
   x["catalog_alias_task_keys"]=list(aliases);x["native_paths"]=physical_paths
   x["catalog_native_path_present_at_snapshot"]=r.get("native_path_present")
   x["catalog_retention_status_at_snapshot"]=r.get("retention_status")
   x["catalog_restore_required_at_snapshot"]=r.get("restore_required")
   x["fresh_native_inventory_verified"]=True
   x["aliases"]=[q for q in physical_paths if q!=s]
   x["link_count"]=st.st_nlink;x["owner_task_keys"]=sorted(set(owner_keys))
   x["physical_inventory_sha256"]=physical_inventory_sha
   if st.st_nlink==1:
    singles.append(x);seen_inodes.add(inode)
   else:groups.append({**x,"review_only":True,"retirement_enabled":False});seen_inodes.add(inode)
   continue
  if st.st_nlink==1 and not aliases:singles.append(x);seen_inodes.add(inode);continue
  ok=len(physical_paths)==st.st_nlink
  for a in physical_paths:
   try:
    ap=path(root,a);ast=ap.lstat()
    if not stat.S_ISREG(ast.st_mode) or (ast.st_dev,ast.st_ino,ast.st_size)!=(st.st_dev,st.st_ino,st.st_size):ok=False;break
   except Exception:ok=False;break
  if ok:groups.append({**x,"native_paths":physical_paths,"link_count":st.st_nlink,"review_only":True,"retirement_enabled":False});seen_inodes.add(inode)
  else:exclude["incomplete_inode_group"]=exclude.get("incomplete_inode_group",0)+1
 order={a.get("asset_name",a.get("name")):i for i,a in enumerate(assets) if isinstance(a,dict)}
 singles.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]))
 groups.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]))
 chosen=[];n=0
 for x in singles:
  if n+x["source_bytes"]<=target:chosen.append(x);n+=x["source_bytes"]
 review=[];rn=0
 for x in groups:
  if rn+x["source_bytes"]<=target:review.append(x);rn+=x["source_bytes"]
 return {"schema":SCHEMA,"root":str(root),"release":m.get("release",{}),"catalog_sha256":catalog_sha,"catalog_receipt_sha256":receipt_sha,"catalog_receipt_path":str(receiptp) if new_catalog else None,"manifest_sha256":catalog_sha,"physical_inode_inventory_sha256":physical_inventory_sha,"_physical_inode_inventory":physical_inventory,"scope_experiments":list(scope),"target_bytes":target,"storage_target_is_not_scientific_resource_limit":True,"source_rows_in_scope":scope_rows,"source_bytes_in_scope":scope_bytes,"validated_success_terminal_rows":eligible_rows,"validated_success_terminal_bytes":eligible_bytes,"retirement_profile":retirement_profile,"selection_rule":"catalog asset/member order then byte ceiling; no performance or scientific-score selection","strict_single_link_eligible_count":len(singles),"strict_single_link_eligible_bytes":sum(x["source_bytes"] for x in singles),"selected":chosen,"selected_bytes":n,"selected_count":len(chosen),"complete_known_inode_group_review_only":{"count":len(groups),"bytes":sum(x["source_bytes"] for x in groups),"selected_count":len(review),"selected_bytes":rn,"groups":groups,"selected":review,"retirement_enabled":False},"excluded_counts":exclude,"payload_hashes_recomputed":False,"native_payloads_read":False,"future_input_source_proof":input_source_proof,"registry_records_scanned_for_consumers":len(reg)}
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
def verified_asset_once(zp,asset,cached):
 p=pathlib.Path(zp);st=p.lstat();marker=(asset["name"],st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
 if cached is None or marker!=cached[0]:
  witness=verify_asset(p,asset);cached=(marker,witness)
 else:witness=cached[1]
 return witness,cached

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
ACTIVE_STATUSES={"dispatching","running","worker_active","validating"}
WORKER_NAMES=("worker.py","parallel_rf/worker.py","parallel_extra_trees/worker.py","svm_margin/worker.py","phase_worker.py","parallel_rf/phase_worker.py","parallel_extra_trees/phase_worker.py","svm_margin/phase_worker.py")
STORAGE_NAMES=("run_batch.py","commit_batch_child.py","cold_auto_compaction.py","finalize_project.py","run_finalizer.sh","audit_artifacts.py","calibration_replay.py","calibration_replay_supervisor.py")
SCIENCE_DRAIN_MAX_SECONDS=690
SCIENCE_DRAIN_POLL_SECONDS=5

def _proc_snapshot():
 out={}
 for proc in pathlib.Path("/proc").iterdir():
  if not proc.name.isdigit():continue
  try:
   pid=int(proc.name);raw=(proc/"stat").read_text();tail=raw[raw.rfind(")")+2:].split();ppid=int(tail[1]);ticks=tail[19]
   argv=[x.decode(errors="replace") for x in (proc/"cmdline").read_bytes().split(b"\0") if x]
   cwd=pathlib.Path(os.readlink(proc/"cwd"));uid=proc.stat().st_uid
   out[pid]={"pid":pid,"ppid":ppid,"ticks":ticks,"argv":argv,"cwd":cwd,"uid":uid}
  except (OSError,ValueError,IndexError):continue
 return out

def _descendant(pid,roots,procs):
 seen=set()
 while pid in procs and pid not in seen:
  if pid in roots:return True
  seen.add(pid);pid=procs[pid]["ppid"]
 return False

def _verified_worker_source(rt,relative):
 rt=pathlib.Path(rt).resolve();rel=pathlib.PurePosixPath(relative)
 if rel.is_absolute() or any(x in ("",".","..") for x in rel.parts):raise RetentionError("unsafe worker source path")
 source=rt/"source"/pathlib.Path(*rel.parts);freeze_path=rt/"manifests"/"freeze.json"
 if source.is_symlink() or not source.is_file() or freeze_path.is_symlink() or not freeze_path.is_file():raise RetentionError("worker source/freeze binding is absent or unsafe")
 freeze=json.loads(freeze_path.read_text());expected=freeze.get("source_sha256",{}).get(rel.as_posix())
 if not isinstance(expected,str) or sha(source)!=expected:raise RetentionError("worker source differs from frozen source binding")
 return source.resolve()

def _expected_worker_script(cfg,rt):
 task=cfg.get("task")
 if not isinstance(task,dict):raise RetentionError("active worker request task is malformed")
 ep=cfg.get("execution_policy");rp=cfg.get("resource_profile")
 try:experiment=int(task.get("experiment",-1))
 except (TypeError,ValueError):raise RetentionError("active worker experiment is malformed")
 method=task.get("method");kind=task.get("kind")
 if ep is None and rp is None:
  if method in ("linear_svm","rbf_svm") and kind in ("fit","eval","alias"):rel="svm_margin/worker.py"
  else:rel="worker.py"
 elif ep=="rf4-fit_n_jobs4-v1" and rp=="rf-fit_n_jobs4" and experiment in (4,5) and kind=="fit" and method=="random_forest" and not task.get("reuse_pipeline"):
  rel="parallel_rf/worker.py"
 elif ep=="et4-fit_n_jobs4-v1" and rp=="et-fit_n_jobs4" and experiment in (4,5) and kind=="fit" and method=="extra_trees" and not task.get("reuse_pipeline"):
  rel="parallel_extra_trees/worker.py"
 else:raise RetentionError("active worker execution profile is not recognized")
 return _verified_worker_source(rt,rel)

def _quiescence_observation(rt,controller_pid):
 rt=pathlib.Path(rt).resolve();records=registry(rt/"registry.sqlite");active=[x for x in records.values() if x.get("status") in ACTIVE_STATUSES]
 procs=_proc_snapshot();verified=set();transition=False
 for task in active:
  status=task.get("status");pid=task.get("pid");ticks=task.get("process_start_ticks")
  if status=="dispatching" and not pid and not ticks:
   transition=True;continue
  if not pid or not ticks:raise RetentionError("active registry task lacks worker PID/start-ticks")
  pid=int(pid);request=pathlib.Path(str(task.get("request_path","")))
  if not request.is_absolute() or request.is_symlink() or not request.is_file() or not request.resolve().is_relative_to(rt):
   raise RetentionError("active worker request path is absent or unsafe")
  attempts=task.get("attempts")
  if not isinstance(attempts,list) or not attempts or attempts[-1].get("request_path")!=str(request):
   raise RetentionError("active task attempt/request identity is inconsistent")
  cfg=json.loads(request.read_text())
  task_cfg=cfg.get("task") if isinstance(cfg,dict) else None
  if not isinstance(task_cfg,dict) or cfg.get("attempt_id")!=attempts[-1].get("attempt_id") or cfg.get("result_path")!=task.get("result_path") or task_cfg.get("key")!=task.get("key"):
   raise RetentionError("active worker request does not bind registry task/attempt/result")
  expected=_expected_worker_script(cfg,rt);proc=procs.get(pid)
  if proc is None:
   transition=True;continue
  if str(proc["ticks"])!=str(ticks) or proc["uid"]!=os.getuid():
   raise RetentionError("active worker PID/start-ticks/UID identity mismatch")
  argv_paths=[]
  for token in proc["argv"]:
   if token.endswith(".py"):
    candidate=pathlib.Path(token)
    if not candidate.is_absolute():candidate=proc["cwd"]/candidate
    try:argv_paths.append(candidate.resolve())
    except OSError:pass
  if expected not in argv_paths or str(request) not in proc["argv"]:
   raise RetentionError("active worker argv does not bind expected script/request")
  verified.add(pid)
 for pid,proc in procs.items():
  if pid==os.getpid() or pid==controller_pid:continue
  if _script_matches(proc["argv"],proc["cwd"],rt,("controller.py","run_controller.py")):
   raise RetentionError("unmatched project controller process is active")
  if _script_matches(proc["argv"],proc["cwd"],rt,STORAGE_NAMES):
   raise RetentionError("project storage/finalizer/audit process is active")
  if _script_matches(proc["argv"],proc["cwd"],rt,WORKER_NAMES):
   if not _descendant(pid,verified,procs):raise RetentionError("unmatched project worker process is active")
   source_rel=None
   for token in proc["argv"]:
    if not token.endswith(".py"):continue
    candidate=pathlib.Path(token)
    if not candidate.is_absolute():candidate=proc["cwd"]/candidate
    try:candidate=candidate.resolve();source_rel=candidate.relative_to(rt/"source").as_posix()
    except (OSError,ValueError):continue
    if source_rel in WORKER_NAMES:break
    source_rel=None
   if source_rel is None:raise RetentionError("project worker source path is unrecognized")
   _verified_worker_source(rt,source_rel)
 return {"busy":bool(active or transition or verified),"active_registry_tasks":len(active),"verified_worker_roots":len(verified),"transition_pending":transition}

def _check_quiescent(rt,controller_pid):
 state=_quiescence_observation(rt,controller_pid)
 if state["busy"]:raise RetentionError("active verified scientific phase remains")

def _wait_for_science_drain(rt,owner,timeout=SCIENCE_DRAIN_MAX_SECONDS,poll=SCIENCE_DRAIN_POLL_SECONDS,observe=None):
 rt=pathlib.Path(rt).resolve();hold=rt/"ADMISSION_HOLD.json";deadline=time.monotonic()+timeout;obs=observe or _quiescence_observation
 while True:
  try:current=json.loads(hold.read_text())
  except (OSError,ValueError) as exc:raise RetentionError("owned admission hold disappeared or became malformed") from exc
  if current!=_HOLD_DOC:raise RetentionError("admission hold ownership changed during drain")
  if _controller_identity(rt)!=owner:raise RetentionError("controller identity changed during scientific drain")
  state=obs(rt,int(owner["pid"]))
  if not state.get("busy"):return state
  remaining=deadline-time.monotonic()
  if remaining<=0:raise RetentionError("verified scientific drain exceeded 690 second bound")
  time.sleep(min(poll,remaining))

def quiet(rt,floor,allow_terminal=False,cleanup_profile=None):
 global _HOLD_DOC,_HOLD_PATH,_OWNER_SNAPSHOT
 import fcntl,secrets
 rt=pathlib.Path(rt).resolve();hold=rt/"ADMISSION_HOLD.json"
 cleanup_mode=False
 if not (allow_terminal and floor==6*GIB and cleanup_profile is None):cleanup_mode=retirement_profile_for(floor,cleanup_profile)==CLEANUP_RETIRE_PROFILE
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
   _OWNER_SNAPSHOT=_controller_identity(rt);_wait_for_science_drain(rt,_OWNER_SNAPSHOT);_check_quiescent(rt,int(_OWNER_SNAPSHOT["pid"]))
  except Exception:
   if not allow_terminal:raise
   terminal_evidence(rt);_OWNER_SNAPSHOT=None;_check_quiescent(rt,None)
  if floor<20*GIB and not cleanup_mode:
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
 owner_list=row.get("owner_task_keys") or []
 if not isinstance(owner_list,list) or any(not isinstance(k,str) or not k for k in owner_list) or len(owner_list)!=len(set(owner_list)):raise RetentionError("inode group owner key list is malformed")
 owners=set(owner_list)
 reg=registry_records_for(pathlib.Path(root)/"runtime_20261025/registry.sqlite",owner_list)
 path_owners=set()
 for rel in paths:
  k=taskkey(rel)
  if not k or k not in owners or not valid_task(reg.get(k),k):raise RetentionError("inode group owner is not validated terminal")
  path_owners.add(k)
  if not valid_manifest_binding(root,rel,reg.get(k),row["source_sha256"]):raise RetentionError("inode group owner validation mismatch")
 if path_owners!=owners:raise RetentionError("inode owner keys do not exactly match the inode paths")
 return first
def verify_native_single(root,row):
 p=path(root,row["source_path"]);before=p.lstat()
 if before.st_nlink!=1 or not stat.S_ISREG(before.st_mode) or before.st_size!=row["source_bytes"] or sha(p)!=row["source_sha256"]:raise RetentionError("native source SHA/size/link mismatch")
 after=p.lstat()
 if _witness(before)!=_witness(after):raise RetentionError("native source changed during verification")
 return p,before
def _asset_map(m):
 out={}
 for x in m.get("assets",[]):
  if not isinstance(x,dict):continue
  name=x.get("asset_name",x.get("name"))
  if not isinstance(name,str):continue
  if "asset_name" in x:
   out[name]={**x,"name":name,"bytes":x.get("asset_bytes"),"sha256":x.get("asset_sha256")}
  else:out[name]=x
 return out

def _recheck_catalog_bindings(root,manifest_path,plan,m):
 if m.get("schema")!="lamost-terminal-result-retention-catalog/1":return
 receiptp=pathlib.Path(plan.get("catalog_receipt_path") or (pathlib.Path(manifest_path).parent/"CATALOG_RECEIPT.json"))
 expected=plan.get("catalog_receipt_sha256")
 if receiptp.parent.resolve()!=pathlib.Path(manifest_path).parent.resolve() or not expected or receiptp.is_symlink() or not receiptp.is_file() or sha(receiptp)!=expected:
  raise RetentionError("catalog receipt changed since planning")
 catalog=json.loads(pathlib.Path(manifest_path).read_text())
 _,receipt_sha,receipt=validate_catalog_receipt(root,manifest_path,catalog,sha(manifest_path))
 if receipt_sha!=expected:raise RetentionError("catalog receipt changed since planning")
 memo={}
 source_proof=plan.get("future_input_source_proof") or {}
 for item in source_proof.get("source_bindings",[]):
  rel=item.get("runtime_member")
  if not isinstance(rel,str) or not rel.startswith("runtime_20261025/source/"):raise RetentionError("future-input source binding is malformed")
  if sha(path(root,rel))!=item.get("sha256"):raise RetentionError("future-input source changed since planning")
 asset_records=_asset_map(catalog)
 for row in list(plan.get("selected",[]))+list(plan.get("complete_known_inode_group_review_only",{}).get("selected",[])):
  asset=asset_records.get(row.get("asset"))
  if (not isinstance(asset,dict) or asset.get("bytes")!=row.get("asset_bytes") or asset.get("sha256")!=row.get("asset_sha256")
      or asset.get("asset_remote_evidence_path")!=row.get("asset_remote_evidence_path")
      or asset.get("asset_remote_evidence_sha256")!=row.get("asset_remote_evidence_sha256")
      or not _verified_asset_evidence(root,row.get("asset_remote_evidence_path"),row.get("asset_remote_evidence_sha256"),row.get("asset"),row.get("asset_bytes"),row.get("asset_sha256"),memo)):
   raise RetentionError("selected remote asset evidence changed or no longer binds asset identity")
  if not _project_evidence(root,row.get("member_record_evidence_path"),row.get("member_record_evidence_sha256"),memo):
   raise RetentionError("selected member publication evidence changed since planning")

def validate_cleanup_approval(approval,profile):
 if profile==CLEANUP_RETIRE_PROFILE and (approval.get("cleanup_profile")!=CLEANUP_RETIRE_PROFILE or approval.get("cleanup_disk_floor_bytes")!=6*GIB):
  raise RetentionError("approval does not bind cleanup-only 6 GiB policy")
 return True

def cleanup_capacity(root,rows,assets,floor):
 """Require projected cleanup to preserve full restore and one largest asset download."""
 if floor!=6*GIB:raise RetentionError("cleanup capacity is defined only for the 6 GiB cleanup profile")
 seen=set();allocated=0;restore_bytes=0;per_row=[]
 for row in rows:
  if row.get("review_only"):
   st=_check_group(root,row,hash_payload=False)
   if (st.st_dev,st.st_ino,st.st_nlink)!=(row.get("native_dev"),row.get("native_ino"),row.get("native_nlink")):
    raise RetentionError("cleanup inode group differs from planned identity")
  else:
   p=path(root,row["source_path"]);st=p.lstat()
   if not stat.S_ISREG(st.st_mode) or st.st_size!=row["source_bytes"] or st.st_nlink!=1:raise RetentionError("cleanup source topology changed before capacity check")
   if (st.st_dev,st.st_ino)!=(row.get("native_dev"),row.get("native_ino")):raise RetentionError("cleanup source inode differs from plan")
  inode=(st.st_dev,st.st_ino)
  if inode in seen:per_row.append(0);continue
  if not hasattr(st,"st_blocks"):raise RetentionError("filesystem does not expose allocated block count")
  reclaimed=int(st.st_blocks)*512
  if reclaimed<0:raise RetentionError("invalid allocated byte count")
  seen.add(inode);allocated+=reclaimed;restore_bytes+=int(row["source_bytes"]);per_row.append(reclaimed)
 max_asset=max([int(assets[r["asset"]]["bytes"]) for r in rows] or [0])
 free=shutil.disk_usage(root).free;required=floor+restore_bytes+max_asset;projected=free+allocated
 if projected<required:raise RetentionError("projected post-retirement free space cannot cover cleanup floor, full restore set, and largest asset download")
 return {"floor_bytes":floor,"free_before_bytes":free,"selected_reclaimable_allocated_bytes":allocated,"selected_restore_logical_bytes":restore_bytes,"maximum_asset_download_bytes":max_asset,"projected_post_retirement_free_bytes":projected,"required_post_retirement_free_bytes":required,"per_row_reclaimable_allocated_bytes":per_row}

def retire(a):
 root=pathlib.Path(a.root).resolve();cleanup_profile=getattr(a,"cleanup_profile",None)
 retire_profile=retirement_profile_for(a.disk_floor,cleanup_profile)
 quiet(root/"runtime_20261025",a.disk_floor,cleanup_profile=cleanup_profile)
 m=json.loads(pathlib.Path(a.manifest).read_text());am=_asset_map(m);pl=json.loads(pathlib.Path(a.plan).read_text())
 if pl.get("schema")!=SCHEMA or pl.get("manifest_sha256")!=sha(a.manifest):raise RetentionError("plan manifest binding mismatch")
 if pl.get("retirement_profile",STANDARD_RETIRE_PROFILE)!=retire_profile:raise RetentionError("plan retirement profile mismatch")
 _recheck_catalog_bindings(root,a.manifest,pl,m)
 if a.execute:
  if not a.approval:raise RetentionError("root approval required")
  ap=json.loads(pathlib.Path(a.approval).read_text())
  if ap.get("schema")!=APPROVAL or ap.get("approved") is not True or ap.get("plan_sha256")!=sha(a.plan):raise RetentionError("approval binding mismatch")
  validate_cleanup_approval(ap,retire_profile)
  if a.include_groups and ap.get("allow_complete_known_groups") is not True:raise RetentionError("approval does not authorize inode groups")
 state0=state(a.state)
 if state0.get("restore_required"):raise RetentionError("prior retirement still requires restore")
 retired_paths={p for old in state0["retired"] for p in (old.get("native_paths") or [old["source_path"]])}
 cache=pathlib.Path(a.cache);cache.mkdir(parents=True,exist_ok=True);out={"status":"verified_only","verified":[],"retired":[]}
 rows=list(pl.get("selected",[]))
 if a.include_groups:rows+=list(pl.get("complete_known_inode_group_review_only",{}).get("selected",[]))
 order={x.get("asset_name",x.get("name")):i for i,x in enumerate(m["assets"]) if isinstance(x,dict)};rows.sort(key=lambda x:(order.get(x["asset"],999999),x["archive_member"]))
 verified_asset=None
 current_registry=registry(root/"runtime_20261025/registry.sqlite")
 if any(any(not valid_task(current_registry.get(owner),owner) for owner in (x.get("owner_task_keys") or [x["task_key"]]))
        or has_nonterminal_reference(current_registry,x.get("owner_task_keys") or [x["task_key"]],x.get("native_paths") or [x["source_path"]]) for x in rows):
  raise RetentionError("registry task/consumer eligibility changed")
 capacity=cleanup_capacity(root,rows,am,a.disk_floor) if retire_profile==CLEANUP_RETIRE_PROFILE else None
 if capacity:out["cleanup_capacity_projection"]={k:v for k,v in capacity.items() if k!="per_row_reclaimable_allocated_bytes"}
 for row_index,r in enumerate(rows):
  if capacity:
   remaining=sum(capacity["per_row_reclaimable_allocated_bytes"][row_index:])
   if shutil.disk_usage(root).free+remaining<capacity["required_post_retirement_free_bytes"]:raise RetentionError("cleanup restore/disk reserve projection no longer holds")
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
  asset_witness,verified_asset=verified_asset_once(z,asset,verified_asset)
  check_member(z,r,asset_witness);out["verified"].append(r["source_path"])
  if a.execute:
   rt=root/"runtime_20261025"
   if _controller_identity(rt)!=_OWNER_SNAPSHOT:raise RetentionError("controller identity changed during retention")
   if group:now=_check_group(root,r)
   else:p,now=verify_native_single(root,r)
   if _witness(now)!=_witness(before) or now.st_nlink!=before.st_nlink:raise RetentionError("native identity changed before unlink")
   if capacity:
    remaining=sum(capacity["per_row_reclaimable_allocated_bytes"][row_index:])
    if shutil.disk_usage(root).free+remaining<capacity["required_post_retirement_free_bytes"]:raise RetentionError("cleanup projected restore reserve changed before unlink")
   elif shutil.disk_usage(root).free<a.disk_floor:raise RetentionError("disk floor changed before unlink")
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

def write_plan_output(root,output,plan):
 root=pathlib.Path(root).resolve();dest=pathlib.Path(output)
 if dest.is_symlink():raise RetentionError("plan output is a symlink")
 dest=dest.resolve(strict=False)
 try:dest.relative_to(root)
 except ValueError:raise RetentionError("plan output must remain inside project")
 if plan.get("_physical_inode_inventory") is not None:
  inventory=plan.pop("_physical_inode_inventory")
  invpath=dest.with_name(dest.name+".inode_inventory.json")
  atomic(invpath,inventory)
  plan["physical_inode_inventory_path"]=invpath.relative_to(root).as_posix()
  plan["physical_inode_inventory_file_sha256"]=sha(invpath)
 atomic(dest,plan)
 return plan

def main():
 p=argparse.ArgumentParser();ss=p.add_subparsers(dest="cmd",required=True);q=ss.add_parser("plan")
 for x in ("root","manifest","registry","output"):q.add_argument("--"+x,required=True)
 q.add_argument("--target-bytes",type=int,default=10*GIB);q.add_argument("--experiments",default="3,4,5,6");q.add_argument("--retirement-profile",choices=(STANDARD_RETIRE_PROFILE,CLEANUP_RETIRE_PROFILE),default=STANDARD_RETIRE_PROFILE)
 q=ss.add_parser("verify-retire")
 for x in ("root","manifest","plan","state","cache","log","repo","tag"):q.add_argument("--"+x,required=True)
 q.add_argument("--disk-floor",type=int,default=20*GIB);q.add_argument("--cleanup-profile");q.add_argument("--approval");q.add_argument("--execute",action="store_true");q.add_argument("--include-groups",action="store_true")
 q=ss.add_parser("restore")
 for x in ("root","state","cache"):q.add_argument("--"+x,required=True)
 q.add_argument("--repo");q.add_argument("--tag");q.add_argument("--disk-floor",type=int,default=20*GIB)
 q=ss.add_parser("status");q.add_argument("--state",required=True);a=p.parse_args()
 try:
  if a.cmd=="plan":out=make_plan(a.root,a.manifest,a.registry,a.target_bytes,tuple(int(x) for x in a.experiments.split(",")),a.retirement_profile);out=write_plan_output(a.root,a.output,out)
  elif a.cmd=="verify-retire":out=retire(a)
  elif a.cmd=="restore":
   quiet(pathlib.Path(a.root)/"runtime_20261025",a.disk_floor,allow_terminal=True);out=restore(a)
  else:
   s=state(a.state);out={"retired_count":len(s["retired"]),"retired_bytes":sum(x["source_bytes"] for x in s["retired"]),"restore_required":s.get("restore_required",False)}
  print(json.dumps(out,sort_keys=True));return 0
 except (RetentionError,OSError,ValueError,KeyError,sqlite3.Error,zipfile.BadZipFile,RuntimeError) as e:print(json.dumps({"status":"blocked","reason":str(e)}),file=sys.stderr);return 2
 finally:release_guard()
if __name__=="__main__":raise SystemExit(main())
