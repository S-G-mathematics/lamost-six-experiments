"""Pinned process/dependency/hardlink safety helpers vendored for cold storage."""
import datetime,os,pathlib,stat
class StorageError(RuntimeError):pass
class UnsafePlan(StorageError):pass
class AmbiguousState(StorageError):pass
def now_utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
_REF_FIELDS={'task_key','fit_key','train_key','selection_key','cohort_key','source_key','producer_task','evaluation_key','eval_key','member_task','model_task','artifact_task','pipeline_task','evaluation_task_key','eval_task_key','dependency_key','evaluation','evaluation_task','task'}

_SAFE_REF_METADATA={'member','member_name','generator','method','family','model_name','route','condition','mechanism','role','metric','metric_name','score','score_name','status','description','label','weight','seed','sha256','hash','bytes','rows','available','reason'}

def _extract_declared_refs(value,known,where):
 out=set()
 if value is None:return out
 if isinstance(value,str):
  if value in known:return {value}
  raise UnsafePlan(f'ambiguous external task/model reference in {where}: {value!r}')
 if isinstance(value,(list,tuple,set)):
  for x in value:out|=_extract_declared_refs(x,known,where)
  return out
 if isinstance(value,dict):
  for k,v in value.items():
   if k in _REF_FIELDS:
    if v is not None:out|=_extract_declared_refs(v,known,f'{where}.{k}')
   elif k in known:out.add(k)
   elif isinstance(v,(dict,list,tuple,set)):
    out|=_extract_declared_refs(v,known,f'{where}.{k}')
   elif isinstance(v,str):
    if v in known:out.add(v)
    elif str(k).lower() not in _SAFE_REF_METADATA:raise UnsafePlan(f'ambiguous external model/task reference in {where}.{k}: {v!r}')
  return out
 if isinstance(value,(int,float,bool)):return out
 raise UnsafePlan(f'unsupported task reference structure in {where}')

def _edges(t,known):
 out=set()
 deps=t.get('dependencies') or []
 if not isinstance(deps,(list,tuple,set)):raise UnsafePlan(f'dependencies must be task-key list: {t.get("key")}')
 for dep in deps:
  if not isinstance(dep,str) or dep not in known:raise UnsafePlan(f'missing/ambiguous dependency key in {t.get("key")}: {dep!r}')
  out.add(dep)
 for k in ('fit_key','train_key','selection_key','cohort_key','source_key'):
  v=t.get(k)
  if v is None:continue
  if not isinstance(v,str) or v not in known:raise UnsafePlan(f'missing/ambiguous {k} reference in {t.get("key")}: {v!r}')
  out.add(v)
 for k in ('member_evaluations','model_references','model_refs','model_keys','member_keys','artifact_references'):
  if k in t and t[k] is not None:
   refs=_extract_declared_refs(t[k],known,f'{t.get("key")}.{k}')
   if t[k] and not refs:raise UnsafePlan(f'ambiguous nonempty model-reference field {k} in {t.get("key")}')
   out|=refs
 return out

def consumer_closure(producer,records):
 if producer not in records:raise UnsafePlan(f'missing producer task {producer}')
 known=set(records);closure=set();front={producer}
 while front:
  nxt=set()
  for k,t in records.items():
   if k!=producer and k not in closure and _edges(t,known)&front:closure.add(k);nxt.add(k)
  front=nxt
 return closure

def _ticks(proc_root,pid):
 try:
  s=(pathlib.Path(proc_root)/str(pid)/'stat').read_text();return int(s[s.rfind(')')+2:].split()[19])
 except Exception:return None

def _proc_rows(proc_root):
 rows={}
 try:dirs=list(pathlib.Path(proc_root).iterdir())
 except OSError as e:raise AmbiguousState(f'cannot enumerate proc: {e}') from e
 for d in dirs:
  if not d.name.isdigit():continue
  try:
   s=(d/'stat').read_text();tail=s[s.rfind(')')+2:].split();pp=int(tail[1]);ticks=int(tail[19]);cmd=(d/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ');rows[int(d.name)]={'ppid':pp,'ticks':ticks,'cmd':cmd}
  except FileNotFoundError:continue
  except PermissionError as e:raise AmbiguousState(f'cannot inspect process {d.name}') from e
  except Exception:continue
 return rows

def _task_markers(root,t):
 out=[]
 if t.get('artifact_dir'):out.append(str(pathlib.Path(t['artifact_dir']).resolve(strict=False)))
 if t.get('key'):out.append(str((pathlib.Path(root)/'runtime_20261025'/'artifacts'/t['key']).resolve(strict=False)))
 for a in t.get('attempts') or []:
  if isinstance(a,dict):
   for k in ('request_path','result_path'):
    if a.get(k):out.append(str(pathlib.Path(a[k]).resolve(strict=False)))
 return sorted(set(out),key=len,reverse=True)

def verify_no_matching_processes(root,task_keys,records,proc_root=pathlib.Path('/proc')):
 checked=[]
 for k in sorted(task_keys):
  t=records[k]
  if t.get('status')=='running':raise UnsafePlan(f'task remains marked running: {k}')
  pid=t.get('pid');ticks=t.get('process_start_ticks')
  if pid is not None and ticks is not None:
   cur=_ticks(proc_root,pid);live=cur is not None and cur==int(ticks)
   checked.append({'task_key':k,'pid':int(pid),'recorded_start_ticks':int(ticks),'same_process_alive':live})
   if live:raise UnsafePlan(f'recorded task process remains live or identity is ambiguous: {k}')
 rows=_proc_rows(proc_root);markers={k:_task_markers(root,records[k]) for k in task_keys};found=[]
 for pid,r in rows.items():
  for k,paths in markers.items():
   if any(x and x in r['cmd'] for x in paths):found.append((pid,k));break
 if found:raise UnsafePlan(f'{len(found)} process(es) still reference selected task artifacts/request paths')
 return {'observed_utc':now_utc(),'task_count':len(task_keys),'matching_processes':0,'complete':True,'checked_task_process_identities':checked}

def inode_paths_within_root(root,source,exclude=()):
 root=pathlib.Path(root).resolve();source=pathlib.Path(source).resolve(strict=True);st=source.stat(follow_symlinks=False)
 if not stat.S_ISREG(st.st_mode):raise UnsafePlan(f'not a regular source: {source}')
 excluded={pathlib.Path(x).resolve(strict=False) for x in exclude};found=[];stack=[root]
 while stack:
  d=stack.pop()
  if d in excluded:continue
  try:entries=list(os.scandir(d))
  except OSError as e:raise AmbiguousState(f'hardlink scan failed at {d}: {e}') from e
  for ent in entries:
   p=pathlib.Path(ent.path)
   try:
    if ent.is_symlink():continue
    if ent.is_dir(follow_symlinks=False):stack.append(p);continue
    x=ent.stat(follow_symlinks=False)
    if stat.S_ISREG(x.st_mode) and (x.st_dev,x.st_ino)==(st.st_dev,st.st_ino):found.append(p.resolve())
   except OSError as e:raise AmbiguousState(f'hardlink scan entry unreadable: {p}') from e
 found=sorted(set(found))
 if len(found)!=st.st_nlink:raise UnsafePlan(f'hardlink count incomplete in migration root: found={len(found)} nlink={st.st_nlink}')
 return found,st.st_nlink
