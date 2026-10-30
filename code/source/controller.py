from __future__ import annotations
import argparse,collections,datetime,fcntl,hashlib,json,os,pathlib,signal,sqlite3,subprocess,sys,time,uuid,shutil,importlib.util,stat,zipfile,struct,ast,copy
try:
 import admission_evidence
except ModuleNotFoundError:
 _spec=importlib.util.spec_from_file_location("admission_evidence",pathlib.Path(__file__).resolve().with_name("admission_evidence.py"));admission_evidence=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(admission_evidence)
try:
 import archive_fit_admission
except ModuleNotFoundError:
 _spec=importlib.util.spec_from_file_location("archive_fit_admission",pathlib.Path(__file__).resolve().with_name("archive_fit_admission.py"));archive_fit_admission=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(archive_fit_admission)
try:
 import rf4_e4_rep3_admission
except ModuleNotFoundError:
 _spec=importlib.util.spec_from_file_location("rf4_e4_rep3_admission",pathlib.Path(__file__).resolve().with_name("rf4_e4_rep3_admission.py"));rf4_e4_rep3_admission=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(rf4_e4_rep3_admission)
R=pathlib.Path(__file__).resolve().parents[1]
SUCCESS='successful'
TERMINAL={'successful','scientific_failure','unsupported','unavailable_dependency','user_stopped'}
THREADS={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'}
STOP=False
DEFINITIONS={}
STORAGE_ESTIMATE=(0.0,0)
CPU_PREVIOUS=None
LAST_IDLE_CORES=0.0
DISPATCH_POLICY_ID='cross-exp-stage-arf6-e4-et-control-critical-path-20261028-v1'
ADAPTIVE_REVISION='adaptive-concurrency-20261025-v1.1'
E4_RF_80K_PROFILE_VERSION='e4-direct-rf-80k-admission-4gib-20261026'
E4_RF_80K_REPS={1,2,3}
E4_RF_80K_CONDITIONS={f'{label}_{severity}' for label in ('A','F','G','K','M','GALAXY','QSO') for severity in ('half','tenth')}
GIB=1024**3
ADMISSION_SAFETY_BUFFER_BYTES=GIB
HOST_RESERVE=6*GIB
ADMISSION_FLOOR=8*GIB
EMERGENCY_FLOOR=6*GIB
EMERGENCY_BACKOFF_UNTIL=0.0
ADAPTIVE_POLICY={'worker_count_ceiling':'cpu-derived','queue_packing':'retain one heavy fitting lane and prefer admissible light work before additional heavy fits','cpu_reserve_cores':2,'worker_memory_limit_gib':10,'worker_admission_reservation_gib_by_class':{'light':2,'heavy':10},'bounded_helper_reservation_gib':1,'alias_reservation_gib':0.25,'host_os_harbor_reserve_gib':6,'admission_pause_below_gib':8,'commitment_growth_margin_gib':2,'admission_only_safety_buffer_gib':1,'admission_condition':'new launches require existing 2 GiB growth margin plus 1 GiB admission-only safety buffer','reclaim_condition':'MemAvailable < host reserve + unspent worker reservations + 2 GiB growth margin','trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'nested_threads':1,'worker_nice':10,'prediction_chunk_rows':50000,'emergency_backoff_seconds':60,'max_operational_recoveries':2,'retry_cooldown_seconds':[60,120,300]}
ADMISSION_REQUIRED_MARGIN_BYTES=int(ADAPTIVE_POLICY['commitment_growth_margin_gib']*GIB)+ADMISSION_SAFETY_BUFFER_BYTES
E6_OVERLAY_REL='manifests/E6_EXECUTION_OVERLAY_V2.json'
E6_V2='E6-v2'
E6_OVERLAY_SHA256=None
E6_OVERLAY_DOC=None
RF4_POLICY_REL='manifests/RF4_EXECUTION_POLICY_20261028.json'
RF4_POLICY_FIELD='rf4_execution_policy_sha256'
RF4_E4_6G_POLICY_FIELD='rf4_e4_treatment_6g_admission_sha256'
RF4_E4_6G_POLICY_REL='manifests/RF4_E4_TREATMENT_6GIB_ADMISSION_20261028.json'
RF4_E4_6G_PROFILE_ID='rf4-e4-rep2-treatment-fit-6gib-admission-20261028'
RF4_E4_6G_EVIDENCE_REL='reports/engineering_audits/RF4_E4_6GIB_PROSPECTIVE_ADMISSION_EVIDENCE_20261028.json'
RF4_E4_6G_EVIDENCE_SHA='28716b215c993cd5a8830fbfd423ba4254cb547427c048c9abc1641644a16dd5'
RF4_E4_REP3_POLICY_FIELD='rf4_e4_rep3_treatment_6g_admission_sha256'
RF4_E4_REP3_POLICY_REL='manifests/RF4_E4_REP3_TREATMENT_6GIB_ADMISSION_20261028.json'
RF4_E4_REP3_PROFILE_ID=rf4_e4_rep3_admission.PROFILE_ID
RF4_EXECUTION_POLICY='rf4-fit_n_jobs4-v1'
RF4_RESOURCE_PROFILE='rf-fit_n_jobs4'
RF4_PROFILE_ID=RF4_RESOURCE_PROFILE
RF4_CPU_UNITS=4
RF4_SOURCE_NAMES=('parallel_rf/worker.py','parallel_rf/phase_worker.py','parallel_rf/science.py')
ET4_EXECUTION_POLICY='et4-fit_n_jobs4-v1'
ET4_RESOURCE_PROFILE='et-fit_n_jobs4'
ET4_PROFILE_ID='et4-fit-n_jobs4-10gib-e45-never-attempted-v1'
ET4_POLICY_FIELD='et4_execution_policy_sha256'
ET4_POLICY_REL='manifests/EXTRA_TREES4_EXECUTION_POLICY_20261029.json'
ET4_SOURCE_NAMES=('parallel_extra_trees/worker.py','parallel_extra_trees/phase_worker.py','parallel_extra_trees/science.py')
ET4_CPU_UNITS=4
ARCHIVE_FIT_POLICY_FIELD=archive_fit_admission.POLICY_FIELD
ARCHIVE_FIT_OVERLAP_PROFILE='archive-native-fit-overlap-1.5gib-cpu1-v1'
RF4_POLICY_CACHE_SIGNATURE=None
RF4_POLICY_CACHE_VALUE=None
RF4_ENGINE_HASH_CACHE=None
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+'\n');os.replace(t,p)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return h.hexdigest()
def start_ticks(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()[19]
 except Exception:return None
def alive(pid,ticks,needle='worker.py'):
 try:
  return bool(pid and ticks and start_ticks(pid)==str(ticks) and needle in pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace'))
 except OSError:return False
def process_table():
 rows={}
 for p in pathlib.Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   lines=(p/'status').read_text().splitlines();pp=int(next(x.split()[1] for x in lines if x.startswith('PPid:')));rss=int(next(x.split()[1] for x in lines if x.startswith('VmRSS:')))*1024
   rows[int(p.name)]=(pp,rss)
  except Exception:pass
 return rows
def tree_rss(pid,rows):
 ids={int(pid)}
 for _ in range(12):
  more={p for p,(pp,rss) in rows.items() if pp in ids}
  if more<=ids:break
  ids|=more
 return sum(rows.get(p,(0,0))[1] for p in ids),ids
def memory_available():
 for l in pathlib.Path('/proc/meminfo').read_text().splitlines():
  if l.startswith('MemAvailable:'):return int(l.split()[1])*1024
 return 0
def source_hashes():
 names=['controller.py','worker.py','science.py','phase_worker.py','cohorts.py','ensemble.py','ensemble_maintenance_patch.py','e6_phase_supervisor.py','svm_margin/science.py','svm_margin/worker.py','svm_margin/phase_worker.py','admission_evidence.py']
 freeze_path=R/'manifests/freeze.json'
 if freeze_path.is_file():
  try: freeze_doc=json.loads(freeze_path.read_text())
  except (OSError,ValueError,AttributeError): freeze_doc={}
  if isinstance(freeze_doc,dict) and (RF4_POLICY_FIELD in freeze_doc or RF4_E4_6G_POLICY_FIELD in freeze_doc or RF4_E4_REP3_POLICY_FIELD in freeze_doc):names.extend(RF4_SOURCE_NAMES)
  if isinstance(freeze_doc,dict) and ET4_POLICY_FIELD in freeze_doc:names.extend(ET4_SOURCE_NAMES)
  if isinstance(freeze_doc,dict) and (ARCHIVE_FIT_POLICY_FIELD in freeze_doc or archive_fit_admission.WORKER_REAPER_FIELD in freeze_doc):names.append('archive_fit_admission.py')
 return {n:sha(R/'source'/n) for n in names}
def _rf4_manifest_and_freeze(frozen=None):
 frozen=frozen if isinstance(frozen,dict) else {}
 if RF4_POLICY_FIELD not in frozen:return None
 declared=frozen.get(RF4_POLICY_FIELD)
 if not isinstance(declared,str) or len(declared)!=64 or any(c not in '0123456789abcdef' for c in declared):
  raise RuntimeError('declared RF4 policy SHA is malformed')
 manifest_path=R/RF4_POLICY_REL
 try:
  if not manifest_path.is_file() or manifest_path.is_symlink():raise RuntimeError('declared RF4 policy manifest missing or unsafe')
  manifest_bytes=manifest_path.read_bytes()
  manifest_sha=hashlib.sha256(manifest_bytes).hexdigest()
  if manifest_sha!=declared:raise RuntimeError('declared RF4 policy manifest SHA mismatch')
  doc=json.loads(manifest_bytes)
 except (OSError,ValueError,TypeError) as exc:
  raise RuntimeError('declared RF4 policy manifest is unreadable') from exc
 if not isinstance(doc,dict) or doc.get('schema')!='lamost-later-rf4-execution-policy/1' or doc.get('policy_id')!=RF4_EXECUTION_POLICY or doc.get('resource_profile_id')!=RF4_RESOURCE_PROFILE or doc.get('status')!='qualified':
  raise RuntimeError('declared RF4 policy is not a qualified supported manifest')
 expected_scope={'experiments':[4,5],'kind':'fit','methods':['random_forest'],'never_attempted':True,'reuse_pipeline':False}
 if doc.get('scope')!=expected_scope:raise RuntimeError('RF4 policy scope mismatch')
 limits={'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1,'admission_reservation_gib':10,'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30}
 if any(doc.get(k)!=v for k,v in limits.items()):raise RuntimeError('RF4 execution/resource limits mismatch')
 source_map=doc.get('source_sha256')
 if not isinstance(source_map,dict) or set(source_map)!=set(RF4_SOURCE_NAMES):raise RuntimeError('RF4 adapter source inventory mismatch')
 members={name:R/'source'/name for name in RF4_SOURCE_NAMES}
 if any(path.is_symlink() or not path.is_file() for path in members.values()):
  raise RuntimeError('RF4 adapter source path is missing or unsafe')
 current={name:sha(path) for name,path in members.items()}
 if source_map!=current:raise RuntimeError('RF4 adapter source hashes mismatch')
 frozen_sources=frozen.get('source_sha256')
 if not isinstance(frozen_sources,dict) or any(frozen_sources.get(name)!=current[name] for name in RF4_SOURCE_NAMES):
  raise RuntimeError('RF4 adapters are not bound by the frozen source inventory')
 qualification=doc.get('qualification')
 if not isinstance(qualification,dict) or not isinstance(qualification.get('path'),str) or not isinstance(qualification.get('sha256'),str):
  raise RuntimeError('RF4 qualification evidence binding missing')
 qraw=pathlib.Path(qualification['path'])
 if qraw.is_absolute() or '..' in qraw.parts:raise RuntimeError('RF4 qualification path is unsafe')
 qmember=R/qraw
 if qmember.is_symlink():raise RuntimeError('RF4 qualification evidence is symlinked')
 qpath=qmember.resolve()
 if R.resolve() not in qpath.parents or not qpath.is_file():raise RuntimeError('RF4 qualification evidence mismatch')
 cache_paths=[R/'manifests/freeze.json',manifest_path,*members.values(),qmember]
 before=tuple(_rf4_file_identity(x,'bound') for x in cache_paths)
 if sha(manifest_path)!=manifest_sha:raise RuntimeError('RF4 manifest changed during verification')
 current={name:sha(path) for name,path in members.items()}
 if source_map!=current:raise RuntimeError('RF4 adapter source hashes mismatch')
 try:
  qualification_bytes=qpath.read_bytes()
  if hashlib.sha256(qualification_bytes).hexdigest()!=qualification['sha256']:raise RuntimeError('RF4 qualification evidence mismatch')
  qdoc=json.loads(qualification_bytes)
 except (OSError,ValueError,TypeError) as exc:raise RuntimeError('RF4 qualification evidence is malformed') from exc
 _validate_rf4_qualification(qdoc,current,frozen)
 after=tuple(_rf4_file_identity(x,'bound') for x in cache_paths)
 if before!=after:raise RuntimeError('RF4 policy inputs changed during verification')
 return {'manifest_sha256':manifest_sha,'document':doc,'source_sha256':current,'_cache_paths':cache_paths}
def _rf4_hex_sha(value):
 return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def _controller_dispatch_ast_sha256(path,names):
 try:
  tree=ast.parse(pathlib.Path(path).read_text())
  functions={node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
  result={}
  for name in names:
   node=functions.get(name)
   if node is None:return None
   result[name]=hashlib.sha256(ast.dump(node,annotate_fields=True,include_attributes=False).encode()).hexdigest()
  return result
 except (OSError,SyntaxError,ValueError,TypeError):return None
def _storage_operational_amendment_valid(frozen,legacy_controller_sha):
 # This narrowly accepts the old RF4/ET4 controller pin only for the exact
 # reviewed storage-only amendment; all worker, request, profile and resource
 # checks in their original qualification readers remain active.
 if not isinstance(frozen,dict) or legacy_controller_sha!='7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b':return False
 amendment=frozen.get('storage_admission_amendment')
 if not isinstance(amendment,dict) or amendment.get('schema')!='lamost-controller-operational-source-amendment/1':return False
 current=sha(pathlib.Path(__file__))
 if amendment.get('baseline_controller_sha256')!=legacy_controller_sha or amendment.get('candidate_controller_sha256')!=current:return False
 expected_policy=WORKING_STORAGE_POLICY
 if frozen.get('storage_admission_policy')!=expected_policy:return False
 project=R.parent
 def bound_file(field,sha_field):
  rel=amendment.get(field);digest=amendment.get(sha_field)
  if not isinstance(rel,str) or not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):return None
  member=pathlib.Path(rel)
  if member.is_absolute() or '..' in member.parts:return None
  path=project/member
  try:
   if path.is_symlink() or not path.is_file() or project.resolve() not in path.resolve().parents:return None
   raw=path.read_bytes()
   if hashlib.sha256(raw).hexdigest()!=digest:return None
   return path,json.loads(raw)
  except (OSError,ValueError,TypeError):return None
 policy_pair=bound_file('policy_path','policy_sha256')
 receipt_pair=bound_file('focused_receipt_path','focused_receipt_sha256')
 approval_pair=bound_file('approval_path','approval_sha256')
 if not policy_pair or not receipt_pair or not approval_pair:return False
 policy_path,policy=policy_pair;receipt_path,receipt=receipt_pair;approval_path,approval=approval_pair
 if policy.get('schema')!='lamost-working-storage-admission-policy/1' or policy.get('policy_id')!=expected_policy['policy_id']:return False
 if policy.get('controller_baseline_sha256')!=legacy_controller_sha or policy.get('controller_candidate_sha256')!=current:return False
 if policy.get('freeze_binding_value')!=expected_policy or policy.get('approval_record_sha256')!=amendment.get('approval_sha256'):return False
 if policy.get('approval_record')!=amendment.get('approval_path'):return False
 expected_scientific_limits={'worker_hard_limit_bytes':10*GIB,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'nested_threads':1}
 if policy.get('unchanged_scientific_resource_limits')!=expected_scientific_limits or policy.get('maximum_concurrent_fit_tasks')!=1:return False
 if not approval.get('authorized') or approval.get('user_answer')!='Use 6 GiB reserve and one fit':return False
 names=('_rf4_fit_eligible','_et4_fit_eligible','worker_script_for_task','worker_request_definition','worker_resource_class','worker_reservation_bytes','candidate_cpu_reservation_units')
 actual_dispatch=_controller_dispatch_ast_sha256(pathlib.Path(__file__),names)
 dispatch=policy.get('protected_dispatch_function_ast_sha256')
 if not isinstance(dispatch,dict) or actual_dispatch!=dispatch:return False
 if amendment.get('protected_dispatch_function_ast_sha256')!=dispatch:return False
 if receipt.get('schema')!='lamost-working-storage-admission-focused-qualification/1' or receipt.get('result')!='passed' or receipt.get('tests_passed')!=13 or receipt.get('tests_failed')!=0:return False
 if receipt.get('controller_sha256')!=current or receipt.get('policy_sha256')!=amendment.get('policy_sha256') or receipt.get('py_compile')!='passed':return False
 test_rel=receipt.get('test_path');test_sha=receipt.get('test_sha256')
 if not isinstance(test_rel,str) or not isinstance(test_sha,str) or len(test_sha)!=64:return False
 test_member=pathlib.Path(test_rel)
 if test_member.is_absolute() or '..' in test_member.parts:return False
 test_path=project/test_member
 try:
  if test_path.is_symlink() or not test_path.is_file() or sha(test_path)!=test_sha:return False
 except OSError:return False
 return (amendment.get('policy_path')==policy_path.relative_to(project).as_posix()
         and amendment.get('focused_receipt_path')==receipt_path.relative_to(project).as_posix()
         and amendment.get('approval_path')==approval_path.relative_to(project).as_posix())
def _validate_rf4_qualification(doc,source_map,frozen=None):
 if not isinstance(doc,dict) or doc.get('schema')!='lamost-rf4-execution-qualification/1' or doc.get('status')!='passed':
  raise RuntimeError('RF4 qualification record is not passed/supported')
 if doc.get('source_sha256')!=source_map:raise RuntimeError('RF4 qualification source hashes mismatch')
 if 'controller_sha256' in doc and doc.get('controller_sha256')!=sha(pathlib.Path(__file__)):
  if not _storage_operational_amendment_valid(frozen,doc.get('controller_sha256')):
   raise RuntimeError('RF4 qualification controller source hash mismatch')
 required={'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1,'admission_reservation_gib':10,'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'cpu_reservation_units':4,'cpu_reserve_cores':2}
 if any(doc.get(k)!=v for k,v in required.items()):raise RuntimeError('RF4 qualification execution/resource settings mismatch')
 harness=doc.get('harness')
 if not isinstance(harness,dict) or harness.get('status')!='passed' or harness.get('source_sha256')!=source_map:
  raise RuntimeError('RF4 engineering harness result/source binding missing')
 if not all(_rf4_hex_sha(harness.get(k)) for k in ('harness_source_sha256','report_sha256','guard_log_sha256')):
  raise RuntimeError('RF4 engineering harness hashes missing')
 harness_expected={'guard_exit_code':0,'models_are_synthetic_only':True,'fit_n_jobs':4,'prediction_n_jobs':1,'serialized_estimator_n_jobs':1}
 if any(harness.get(k)!=v for k,v in harness_expected.items()):raise RuntimeError('RF4 engineering harness result mismatch')
 guard=harness.get('harness_guard')
 if not isinstance(guard,dict) or guard.get('wall_limit_seconds')!=120 or guard.get('rss_limit_bytes')!=1610612736 or guard.get('address_space_limit_bytes')!=2147483648 or guard.get('exit_code')!=0:
  raise RuntimeError('RF4 engineering guard limits/result mismatch')
 try:
  wall=float(guard['wall_seconds']);peak=int(guard['peak_process_tree_rss_bytes'])
 except (KeyError,TypeError,ValueError):raise RuntimeError('RF4 engineering guard measurements missing')
 if not 0<=wall<=120 or not 0<=peak<=1610612736:raise RuntimeError('RF4 engineering harness exceeded qualification limits')
 suite=doc.get('portable_suite')
 if not isinstance(suite,dict) or suite.get('status')!='passed' or suite.get('exit_code')!=0 or not _rf4_hex_sha(suite.get('bundle_fingerprint_sha256')):
  raise RuntimeError('RF4 portable suite proof missing')
 try:expected=int(suite['expected_test_count']);passed=int(suite['passed_test_count']);failed=int(suite['failed_test_count'])
 except (KeyError,TypeError,ValueError):raise RuntimeError('RF4 portable suite counts missing')
 if expected<=0 or passed!=expected or failed!=0:raise RuntimeError('RF4 portable suite counts do not prove full pass')
def _rf4_file_identity(path,label):
 path=pathlib.Path(path)
 try:st=path.lstat()
 except OSError as exc:raise RuntimeError('RF4 '+label+' file is missing') from exc
 if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
  raise RuntimeError('RF4 '+label+' file is not a regular non-symlink file')
 return (str(path),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def _rf4_policy():
 global RF4_POLICY_CACHE_SIGNATURE,RF4_POLICY_CACHE_VALUE
 frozen_path=R/'manifests/freeze.json'
 if not frozen_path.exists():return None
 freeze_identity=_rf4_file_identity(frozen_path,'freeze')
 if RF4_POLICY_CACHE_SIGNATURE is not None:
  cached_paths=RF4_POLICY_CACHE_SIGNATURE[1]
  cached_identities=RF4_POLICY_CACHE_SIGNATURE[2]
  try:current_signature=(freeze_identity,tuple(_rf4_file_identity(x,'bound') for x in cached_paths))
  except RuntimeError:current_signature=None
  if current_signature is not None and current_signature==(RF4_POLICY_CACHE_SIGNATURE[0],cached_identities):
   return RF4_POLICY_CACHE_VALUE
 try:frozen=json.loads(frozen_path.read_bytes())
 except (OSError,ValueError,TypeError) as exc:
  raise RuntimeError('existing freeze manifest is malformed; RF4 state cannot be checked') from exc
 if not isinstance(frozen,dict):raise RuntimeError('existing freeze manifest is malformed; RF4 state cannot be checked')
 policy=_rf4_manifest_and_freeze(frozen)
 if policy is None:
  RF4_POLICY_CACHE_SIGNATURE=(freeze_identity,(),())
  RF4_POLICY_CACHE_VALUE=None
  return None
 paths=policy.pop('_cache_paths')
 after_freeze=_rf4_file_identity(frozen_path,'freeze')
 identities=tuple(_rf4_file_identity(x,'bound') for x in paths)
 if after_freeze!=freeze_identity:raise RuntimeError('RF4 policy inputs changed during verification')
 signature=(after_freeze,tuple(paths),identities)
 RF4_POLICY_CACHE_SIGNATURE=signature
 RF4_POLICY_CACHE_VALUE=policy
 return policy

def _rf4_e4_6g_policy(frozen=None):
 frozen=frozen if isinstance(frozen,dict) else {}
 digest=frozen.get(RF4_E4_6G_POLICY_FIELD)
 if digest is None:return None
 if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
  raise RuntimeError('declared E4 RF 6 GiB policy SHA is malformed')
 p=R/RF4_E4_6G_POLICY_REL
 if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise RuntimeError('declared E4 RF 6 GiB policy hash/path mismatch')
 try:doc=json.loads(p.read_bytes())
 except (OSError,ValueError,TypeError) as exc:raise RuntimeError('declared E4 RF 6 GiB policy malformed') from exc
 scope={'experiments':[4],'kind':'fit','methods':['random_forest'],'never_attempted':True,'reuse_pipeline':False,'route':'treatment','rep':2,'max_training_rows':125955}
 limits={'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1,'admission_reservation_gib':6,'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'cpu_reservation_units':4}
 if not isinstance(doc,dict) or doc.get('schema')!='lamost-e4-rf4-treatment-6gib-policy/1' or doc.get('status')!='qualified' or doc.get('scope')!=scope or any(doc.get(k)!=v for k,v in limits.items()):
  raise RuntimeError('declared E4 RF 6 GiB policy scope/limits unsupported')
 if doc.get('evidence_path')!=RF4_E4_6G_EVIDENCE_REL or doc.get('evidence_sha256')!=RF4_E4_6G_EVIDENCE_SHA:
  raise RuntimeError('declared E4 RF 6 GiB evidence binding mismatch')
 try:evidence=json.loads((R/RF4_E4_6G_EVIDENCE_REL).read_bytes())
 except (OSError,ValueError,TypeError) as exc:raise RuntimeError('E4 RF 6 GiB public evidence unreadable') from exc
 if sha(R/RF4_E4_6G_EVIDENCE_REL)!=RF4_E4_6G_EVIDENCE_SHA or evidence.get('schema_version')!='lamost-rf4-e4-prospective-admission-evidence/1':
  raise RuntimeError('E4 RF 6 GiB evidence hash/schema mismatch')
 obs=evidence.get('observed',{});fits=obs.get('fits') if isinstance(obs,dict) else None
 if not isinstance(fits,list) or len(fits)!=10:raise RuntimeError('E4 RF 6 GiB evidence does not contain ten observations')
 seen=set()
 for fit in fits:
  if not isinstance(fit,dict):raise RuntimeError('E4 RF 6 GiB observation malformed')
  key=fit.get('key');fr=fit.get('fit_result',{})
  if (not isinstance(key,str) or key in seen or not key.startswith('e4/rep_2/fit/treatment/random_forest/')
      or not isinstance(fr,dict) or not 80000<=int(fr.get('training_rows',0))<=125955
      or fit.get('final_fit_phase_count')!=1 or int(fit.get('max_phase_tree_rss_kib',10**20))>6*1024*1024):
   raise RuntimeError('E4 RF 6 GiB observation scope/measurement mismatch')
  seen.add(key)
 evidence_sources={x.get('path'):x.get('sha256') for x in evidence.get('inputs',{}).get('source_files',[]) if isinstance(x,dict)}
 policy_sources=doc.get('source_sha256')
 if not isinstance(policy_sources,dict) or set(policy_sources)!=set(RF4_SOURCE_NAMES):raise RuntimeError('E4 RF 6 GiB adapter source map invalid')
 for name in RF4_SOURCE_NAMES:
  expected=evidence_sources.get('source/'+name)
  current=sha(R/'source'/name)
  if expected!=current or policy_sources.get(name)!=current or _rf4_policy_freeze_doc().get('source_sha256',{}).get(name)!=current:
   raise RuntimeError('E4 RF 6 GiB source evidence mismatch')
 return {'policy_sha256':digest,'document':doc,'evidence_sha256':RF4_E4_6G_EVIDENCE_SHA}
def _safe_profile_json(path):
 path=pathlib.Path(path)
 try:
  if path.is_symlink() or not path.is_file():return None
  return json.loads(path.read_bytes())
 except (OSError,ValueError,TypeError):return None
def load_registry_record_for_profile(key):
 try:
  db=sqlite3.connect(f'file:{R / "registry.sqlite"}?mode=ro',uri=True,timeout=1)
  try:row=db.execute('SELECT record FROM tasks WHERE key=?',(key,)).fetchone()
  finally:db.close()
  return json.loads(row[0]) if row else None
 except (OSError,sqlite3.Error,ValueError,TypeError):return None
def _e4_treatment_rf4_rep3_6g_eligible(task):
 if not isinstance(task,dict):return None
 try:
  if (int(task.get('experiment',0))!=4 or int(task.get('rep',0))!=3 or task.get('kind')!='fit'
      or task.get('method')!='random_forest' or task.get('route')!='treatment'):
   return None
 except (TypeError,ValueError):return None
 definition=DEFINITIONS.get(task.get('key'))
 if not isinstance(definition,dict):return None
 frozen=_rf4_policy_freeze_doc()
 if RF4_E4_REP3_POLICY_FIELD not in frozen:return None
 train_key=definition.get('train_key')
 if not isinstance(train_key,str):return None
 dep=load_registry_record_for_profile(train_key)
 if not isinstance(dep,dict):return None
 return rf4_e4_rep3_admission.eligible(task,definition,dep,frozen,R,rf4_e4_rep3_admission.header_shapes)

def _e4_treatment_rf4_6g_eligible(task):
 if not isinstance(task,dict) or task.get('attempts') or task.get('reuse_pipeline'):return None
 try:rep=int(task.get('rep'));exp=int(task.get('experiment'))
 except (TypeError,ValueError):return None
 if (exp,rep,task.get('kind'),task.get('method'),task.get('route'))!=(4,2,'fit','random_forest','treatment'):return None
 if task.get('status') not in ('planned','waiting_dependency','waiting_for_dependency'):return None
 definition=DEFINITIONS.get(task.get('key'))
 if not isinstance(definition,dict) or any(definition.get(k)!=task.get(k) for k in ('key','experiment','rep','kind','method','route','condition','train_key')):return None
 policy=_rf4_e4_6g_policy(_rf4_policy_freeze_doc())
 if policy is None:return None
 train_key=task.get('train_key')
 if not isinstance(train_key,str) or train_key not in task.get('dependencies',[]):return None
 dep=load_registry_record_for_profile(train_key)
 if not isinstance(dep,dict) or dep.get('status') not in ('successful','validated_terminal') or dep.get('validation_state') not in ('validated','validated_terminal'):return None
 result=dep.get('result') if isinstance(dep.get('result'),dict) else {}
 if result.get('status')!='successful' or result.get('key')!=train_key:return None
 artifact=result.get('artifact_path') or dep.get('artifact_dir')
 if not isinstance(artifact,str) or dep.get('key')!=train_key or dep.get('kind') not in ('e4_treatment','e4_append') or dep.get('experiment')!=4 or dep.get('rep')!=2:return None
 artifact_path=pathlib.Path(artifact)
 try:artifact_path=artifact_path.relative_to(R) if artifact_path.is_absolute() else artifact_path
 except ValueError:return None
 if '..' in artifact_path.parts:return None
 probe=R
 for component in artifact_path.parts:
  probe=probe/component
  if probe.is_symlink():return None
 meta_path=R/artifact_path/'metadata.json';val_path=R/artifact_path/'validation.json'
 meta=_safe_profile_json(meta_path);val=_safe_profile_json(val_path)
 if not isinstance(meta,dict) or not isinstance(val,dict):return None
 counts=meta.get('counts_after')
 if not isinstance(counts,list) or len(counts)!=7 or any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in counts):return None
 rows=sum(counts)
 if not 80000<=rows<=125955:return None
 if meta.get('kind') not in ('e4_treatment','e4_append') or meta.get('task_key')!=train_key:return None
 depmeta=dep.get('result',{}).get('metadata',{})
 if not isinstance(depmeta,dict) or meta.get('parent')!=depmeta.get('parent'):return None
 parent=pathlib.Path(meta['parent'])
 try:
  if parent.resolve()!= (R/'artifacts'/str(dep.get('cohort_key',''))).resolve() or parent.is_symlink():return None
 except (OSError,RuntimeError):return None
 if val.get('status')!='validated' or val.get('task_key')!=train_key:return None
 dep_validation=dep.get('result',{}).get('validation',{})
 if not isinstance(dep_validation,dict) or dep_validation.get('status')!='validated' or dep_validation.get('task_key')!=train_key:return None
 dep_files=dep_validation.get('files')
 files=val.get('files');data_sha=files.get('data.npz') if isinstance(files,dict) else None
 if not isinstance(dep_files,dict) or dep_files.get('data.npz')!=data_sha:return None
 if not isinstance(data_sha,str) or len(data_sha)!=64 or any(c not in '0123456789abcdef' for c in data_sha):return None
 data_path=R/artifact_path/'data.npz'
 if not _e4_rf_npz_headers_match(data_path,rows):return None
 key=task.get('key');task_sha=task.get('task_sha256')
 if not isinstance(task_sha,str) or len(task_sha)!=64:
  task_sha=_rf4_task_hash(definition)
 candidates=[R/'artifacts'/key/'pipeline.joblib',R/'artifacts'/key/'fit_result.json']
 if task_sha:candidates.append(R/'artifacts'/key/'checkpoints'/task_sha/'pipeline.joblib')
 for candidate in candidates:
  if candidate.exists() or candidate.is_symlink():return None
 return {'profile_id':RF4_E4_6G_PROFILE_ID,'reservation_gib':6,'cpu_reservation_units':RF4_CPU_UNITS,
         'execution_policy':RF4_EXECUTION_POLICY,'resource_profile':RF4_RESOURCE_PROFILE,
         'policy_sha256':policy['policy_sha256'],'evidence_sha256':policy['evidence_sha256'],
         'train_key':train_key,'train_rows':rows,'train_metadata_sha256':sha(meta_path),'train_validation_sha256':sha(val_path)}
def _rf4_task_hash(definition):
 global RF4_ENGINE_HASH_CACHE
 if not isinstance(definition,dict):return None
 files=[R/'source'/'parallel_rf'/'science.py',R/'source'/'parallel_rf'/'phase_worker.py']
 try:
  sig=tuple((p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in files)
  if RF4_ENGINE_HASH_CACHE and RF4_ENGINE_HASH_CACHE[0]==sig:engine=RF4_ENGINE_HASH_CACHE[1]
  else:
   engine=hashlib.sha256((sha(files[0])+sha(files[1])).encode()).hexdigest()
   RF4_ENGINE_HASH_CACHE=(sig,engine)
  excluded={'attempt_id','worker_pid','started_at','observed_at','observed_utc','artifact_dir','controller_pid','status','attempts','attempt_number','queue_state','controller_state'}
  identity={k:v for k,v in definition.items() if k not in excluded}
  identity['engine_code_sha256']=engine
  return hashlib.sha256(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()
 except (OSError,TypeError,ValueError):return None
def _e4_rf_npz_headers_match(path,rows):
 path=pathlib.Path(path)
 try:
  if path.is_symlink() or not path.is_file():return False
  before=path.stat()
  expected={'X.npy':(rows,6),'y.npy':(rows,),'ids.npy':(rows,)}
  with zipfile.ZipFile(path,'r') as archive:
   if set(archive.namelist())!=set(expected):return False
   for name,shape in expected.items():
    with archive.open(name,'r') as stream:
     prefix=stream.read(8)
     if len(prefix)<8 or prefix[:6]!=(bytes([0x93])+b'NUMPY'):return False
     major,minor=prefix[6],prefix[7]
     if major==1:
      header_len=struct.unpack('<H',stream.read(2))[0]
     elif major in (2,3):
      header_len=struct.unpack('<I',stream.read(4))[0]
     else:return False
     if header_len<=0 or header_len>65536:return False
     header=ast.literal_eval(stream.read(header_len).decode('latin1').strip())
     if tuple(header.get('shape',()))!=shape or header.get('fortran_order') not in (True,False):return False
  after=path.stat()
  return (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,struct.error,SyntaxError):
  return False
def _rf4_policy_freeze_doc():
 p=R/'manifests/freeze.json'
 return _safe_profile_json(p) or {}
def _recorded_e4_treatment_rf6_profile_id(task):
 profiles=[task.get('admission_resource_policy')]
 if task.get('attempts'):profiles.append(task['attempts'][-1].get('resource_profile'))
 for profile in profiles:
  if isinstance(profile,dict) and profile.get('admission_profile_id') in (RF4_E4_6G_PROFILE_ID,RF4_E4_REP3_PROFILE_ID):
   try:
    if int(profile.get('admission_reservation_bytes')) in (6*GIB,10*GIB):return profile['admission_profile_id']
   except (TypeError,ValueError):pass
 return None
def _has_recorded_e4_treatment_rf6_profile(task):
 return _recorded_e4_treatment_rf6_profile_id(task) is not None
def _has_recorded_rf4_profile(task):
 profiles=[task.get('admission_resource_policy')]
 if task.get('attempts'):profiles.append(task['attempts'][-1].get('resource_profile'))
 return any(isinstance(x,dict) and x.get('execution_policy')==RF4_EXECUTION_POLICY and x.get('resource_profile')==RF4_RESOURCE_PROFILE and x.get('admission_profile_id') not in (RF4_E4_6G_PROFILE_ID,RF4_E4_REP3_PROFILE_ID) for x in profiles)
def _rf4_fit_eligible(task):
 policy=_rf4_policy()
 if policy is None or not isinstance(task,dict):return None
 if task.get('kind')!='fit' or task.get('method')!='random_forest':return None
 try:experiment=int(task.get('experiment'))
 except (TypeError,ValueError):return None
 if experiment not in (4,5) or task.get('reuse_pipeline') or task.get('attempts'):return None
 if task.get('admission_reservation_bytes') is not None or task.get('status') not in ('planned','waiting_dependency','waiting_for_dependency'):return None
 key=task.get('key');definition=DEFINITIONS.get(key)
 if not isinstance(definition,dict) or definition.get('key')!=key:return None
 if any(definition.get(k)!=task.get(k) for k in ('key','experiment','kind','method')) or definition.get('reuse_pipeline'):return None
 return {'profile_id':RF4_PROFILE_ID,'reservation_gib':10,'cpu_reservation_units':RF4_CPU_UNITS,'execution_policy':RF4_EXECUTION_POLICY,'resource_profile':RF4_RESOURCE_PROFILE,'policy_sha256':policy['manifest_sha256'],'source_sha256':dict(policy['source_sha256'])}
def _et4_policy(frozen=None):
 frozen=frozen if isinstance(frozen,dict) else _safe_profile_json(R/"manifests"/"freeze.json") or {}
 if ET4_POLICY_FIELD not in frozen:return None
 declared=frozen.get(ET4_POLICY_FIELD)
 if not isinstance(declared,str) or len(declared)!=64 or any(c not in "0123456789abcdef" for c in declared):raise RuntimeError("declared ET4 policy SHA is malformed")
 manifest=R/ET4_POLICY_REL
 if manifest.is_symlink() or not manifest.is_file():raise RuntimeError("declared ET4 policy manifest missing or unsafe")
 raw=manifest.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
 if digest!=declared:raise RuntimeError("declared ET4 policy SHA mismatch")
 doc=json.loads(raw)
 if not isinstance(doc,dict) or doc.get("schema")!="lamost-later-et4-execution-policy/1" or doc.get("policy_id")!=ET4_EXECUTION_POLICY or doc.get("resource_profile_id")!=ET4_RESOURCE_PROFILE or doc.get("status")!="qualified":
  raise RuntimeError("declared ET4 policy is not qualified")
 scope={"experiments":[4,5],"kind":"fit","methods":["extra_trees"],"never_attempted":True,"reuse_pipeline":False}
 if doc.get("scope")!=scope:raise RuntimeError("ET4 task scope mismatch")
 limits={"fit_n_jobs":4,"prediction_n_jobs":1,"native_threads":1,"admission_reservation_gib":10,"worker_memory_limit_gib":10,"trial_timeout_seconds":600,"phase_timeout_seconds":600,"termination_grace_seconds":30,"cpu_reservation_units":4}
 if any(doc.get(k)!=v for k,v in limits.items()):raise RuntimeError("ET4 resource policy mismatch")
 sources=doc.get("source_sha256")
 if not isinstance(sources,dict) or set(sources)!=set(ET4_SOURCE_NAMES):raise RuntimeError("ET4 adapter source inventory mismatch")
 files={name:R/"source"/name for name in ET4_SOURCE_NAMES}
 if any(x.is_symlink() or not x.is_file() for x in files.values()):raise RuntimeError("ET4 source missing or unsafe")
 current={name:sha(path) for name,path in files.items()}
 frozen_sources=frozen.get("source_sha256")
 if sources!=current or not isinstance(frozen_sources,dict) or any(frozen_sources.get(k)!=v for k,v in current.items()):
  raise RuntimeError("ET4 adapter pins differ from frozen source map")
 q=doc.get("qualification")
 if not isinstance(q,dict) or not isinstance(q.get("path"),str) or not isinstance(q.get("sha256"),str):raise RuntimeError("ET4 qualification evidence missing")
 qrel=pathlib.Path(q["path"])
 if qrel.is_absolute() or ".." in qrel.parts:raise RuntimeError("ET4 qualification path unsafe")
 qpath=R/qrel
 if qpath.is_symlink() or not qpath.is_file() or R.resolve() not in qpath.resolve().parents:raise RuntimeError("ET4 qualification path invalid")
 qraw=qpath.read_bytes()
 if hashlib.sha256(qraw).hexdigest()!=q["sha256"]:raise RuntimeError("ET4 qualification evidence SHA mismatch")
 qdoc=json.loads(qraw)
 if not isinstance(qdoc,dict) or qdoc.get("schema")!="lamost-et4-execution-qualification/1" or qdoc.get("status")!="passed" or qdoc.get("source_sha256")!=current:
  raise RuntimeError("ET4 qualification evidence not bound/passed")
 if qdoc.get("controller_sha256")!=sha(pathlib.Path(__file__)):
  if not _storage_operational_amendment_valid(frozen,qdoc.get("controller_sha256")):
   raise RuntimeError("ET4 qualification controller pin mismatch")
 expected_execution={"fit_n_jobs":4,"prediction_n_jobs":1,"serialized_estimator_n_jobs":1,"native_threads":1,"admission_reservation_gib":10,"worker_memory_limit_gib":10,"trial_timeout_seconds":600,"phase_timeout_seconds":600,"termination_grace_seconds":30,"cpu_reservation_units":4}
 if qdoc.get("execution")!=expected_execution:raise RuntimeError("ET4 qualification execution limits mismatch")
 fixture=qdoc.get("synthetic_thread_equivalence")
 if (not isinstance(fixture,dict) or fixture.get("status")!="passed" or fixture.get("models_are_synthetic_only") is not True
     or fixture.get("scientific_fits_started")!=0 or fixture.get("exit_code")!=0 or fixture.get("test_count")<1
     or fixture.get("serialized_estimator_n_jobs")!=1
     or not all(fixture.get(k) is True for k in ("tree_structures_identical_single_vs_four","validation_scores_identical_single_vs_four","same_selected_candidate_single_vs_four","prediction_probabilities_identical_single_vs_four"))):
  raise RuntimeError("ET4 synthetic parallel-equivalence evidence is incomplete")
 test_rel=pathlib.Path(str(fixture.get("test_path","")))
 if test_rel.is_absolute() or ".." in test_rel.parts:raise RuntimeError("ET4 fixture test path unsafe")
 test_path=R/test_rel
 if test_path.is_symlink() or not test_path.is_file() or sha(test_path)!=fixture.get("test_sha256"):
  raise RuntimeError("ET4 fixture test pin mismatch")
 contract=qdoc.get("controller_contract")
 if (not isinstance(contract,dict) or contract.get("status")!="passed"
     or contract.get("exit_code")!=0 or contract.get("test_count")<1):
  raise RuntimeError("ET4 focused controller-contract evidence is incomplete")
 contract_rel=pathlib.Path(str(contract.get("test_path","")))
 if contract_rel.is_absolute() or ".." in contract_rel.parts:raise RuntimeError("ET4 contract test path unsafe")
 contract_path=R/contract_rel
 if contract_path.is_symlink() or not contract_path.is_file() or sha(contract_path)!=contract.get("test_sha256"):
  raise RuntimeError("ET4 focused controller-contract test pin mismatch")
 return {"policy_sha256":digest,"source_sha256":current,"document":doc,"qualification_sha256":q["sha256"]}

def _has_recorded_et4_profile(task):
 profiles=[task.get("admission_resource_policy")]
 if task.get("attempts"):profiles.append(task["attempts"][-1].get("resource_profile"))
 return any(isinstance(x,dict) and x.get("execution_policy")==ET4_EXECUTION_POLICY and x.get("resource_profile")==ET4_RESOURCE_PROFILE and x.get("admission_profile_id")==ET4_PROFILE_ID for x in profiles)
def _et4_fit_eligible(task):
 if not isinstance(task,dict):return None
 if task.get("kind")!="fit" or task.get("method")!="extra_trees":return None
 try: experiment=int(task.get("experiment"))
 except (TypeError,ValueError):return None
 if experiment not in (4,5) or task.get("reuse_pipeline") or task.get("attempts"):return None
 if task.get("admission_reservation_bytes") is not None or task.get("status") not in ("planned","waiting_dependency","waiting_for_dependency"):return None
 key=task.get("key");definition=DEFINITIONS.get(key)
 if not isinstance(definition,dict) or definition.get("key")!=key:return None
 if any(definition.get(k)!=task.get(k) for k in ("key","experiment","kind","method")) or definition.get("reuse_pipeline"):return None
 policy=_et4_policy()
 if policy is None:return None
 return {"profile_id":ET4_PROFILE_ID,"reservation_gib":10,"cpu_reservation_units":ET4_CPU_UNITS,"execution_policy":ET4_EXECUTION_POLICY,"resource_profile":ET4_RESOURCE_PROFILE,"policy_sha256":policy["policy_sha256"],"source_sha256":dict(policy["source_sha256"])}

def lock_project():
 f=(R/'owner.lock').open('a+')
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Project controller ownership lock already held')
 return f
def connect():
 db=sqlite3.connect(R/'registry.sqlite',timeout=30)
 db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
 db.execute('CREATE TABLE IF NOT EXISTS tasks(key TEXT PRIMARY KEY, record TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, kind TEXT, record TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
 db.commit();return db
def event(db,kind,record):
 db.execute('INSERT INTO events(timestamp,kind,record) VALUES (?,?,?)',(now(),kind,json.dumps(record,sort_keys=True,default=str)));db.commit()
def put(db,t):
 db.execute('INSERT OR REPLACE INTO tasks(key,record) VALUES (?,?)',(t['key'],json.dumps(t,sort_keys=True,default=str)));db.commit()
def load(db):return {k:json.loads(v) for k,v in db.execute('SELECT key,record FROM tasks')}
def export(db,tasks):
 counts=collections.defaultdict(collections.Counter)
 for t in tasks.values():
  if t.get('scientific_case'):counts[str(t['experiment'])][t.get('outcome') or t['status']]+=1
 atomic(R/'registry.json',{'schema_version':1,'observed_utc':now(),'tasks':list(tasks.values()),'scientific_counts':dict(counts)})
 atomic(R/'status.json',{'observed_utc':now(),'scientific_counts':dict(counts),'task_counts':dict(collections.Counter(t['status'] for t in tasks.values())),'owner_pid':os.getpid(),'active':[{'key':t['key'],'pid':t.get('pid'),'process_start_ticks':t.get('process_start_ticks'),'started_utc':t.get('started_utc')} for t in tasks.values() if t['status']=='running']})
def human_checkpoint(tasks):
 counts=collections.defaultdict(collections.Counter)
 for t in tasks.values():
  if t.get('scientific_case'):counts[str(t['experiment'])][t.get('outcome') or t['status']]+=1
 lines=['# Airbag project checkpoint','', 'Observed UTC: '+now(),'', 'Read status.json, registry.json, manifests/freeze.json and RUN_RESUME_REPRODUCE.md before resuming.','', 'Do not restart terminal scientific failures or use heartbeats as proof of liveness.','']
 for e,c in sorted(counts.items()):lines.append('E'+e+': '+json.dumps(dict(c),sort_keys=True))
 (R/'AIRBAG_STATE.md').write_text('\n'.join(lines)+'\n')
def maybe_report(db,tasks):
 for e in (3,4,5,6):
  cases=[t for t in tasks.values() if t.get('experiment')==e and t.get('scientific_case')]
  marker=R/'reports'/('E'+str(e)+'_EXECUTION_TERMINAL.json')
  if cases and all(t['status']=='validated_terminal' for t in cases) and not marker.exists():
   export(db,tasks)
   atomic(marker,{'observed_utc':now(),'planned':len(cases),'outcomes':dict(collections.Counter(t.get('outcome') for t in cases))})
   event(db,'experiment_terminal',{'experiment':e,'planned':len(cases)})
   if (R/'source/report_cli.py').exists():
    with (R/'logs/reporting.log').open('a') as log:subprocess.Popen(['/usr/bin/python3',str(R/'source/report_cli.py')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)


def _canonical_sha256(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
def _read_regular_json(path):
 p=pathlib.Path(path)
 st=p.lstat()
 if not pathlib.Path(path).is_file() or p.is_symlink():raise RuntimeError('expected regular JSON file: '+str(p))
 return json.loads(p.read_text(encoding='utf-8'))
def _overlay_fit_evidence_valid(evidence,fit_key,rep,method,definitions,e3_manifest,runtime_root):
 root=pathlib.Path(runtime_root).resolve()
 if not isinstance(evidence,dict):return False
 needed={'fit_key','pipeline_sha256','selection_sha256','fit_result_sha256','validation_sha256','role_membership_sha256','training_ids_sha256','training_rows','method','class_order','feature_order','provenance_group'}
 if not needed<=set(evidence) or evidence.get('fit_key')!=fit_key or evidence.get('method')!=method:return False
 fit_definition=definitions.get(fit_key)
 if not isinstance(fit_definition,dict) or fit_definition.get('kind')!='fit' or int(fit_definition.get('experiment',0) or 0)!=3 or int(fit_definition.get('rep',0) or 0)!=rep or fit_definition.get('method')!=method:return False
 artifact=root/'artifacts'/fit_key
 paths={name:artifact/name for name in ('fit_result.json','selection.json','validation.json','pipeline.joblib')}
 try:
  if not all(x.is_file() and not x.is_symlink() for x in paths.values()):return False
  fit=_read_regular_json(paths['fit_result.json']);selection=_read_regular_json(paths['selection.json']);validation=_read_regular_json(paths['validation.json'])
  if sha(paths['fit_result.json'])!=evidence['fit_result_sha256'] or sha(paths['selection.json'])!=evidence['selection_sha256'] or sha(paths['validation.json'])!=evidence['validation_sha256']:return False
  if fit.get('status')!='successful' or fit.get('task',{}).get('key')!=fit_key:return False
  if validation.get('status')!='validated' or validation.get('task_key')!=fit_key or validation.get('bootstrap') is not False:return False
  if validation.get('files',{}).get('pipeline.joblib')!=evidence['pipeline_sha256'] or fit.get('artifact_sha256')!=evidence['pipeline_sha256']:return False
  if validation.get('files',{}).get('selection.json')!=evidence['selection_sha256']:return False
  result=fit.get('result',{})
  counts=result.get('class_counts')
  if not isinstance(counts,list) or len(counts)!=7 or sum(counts)!=80000 or evidence.get('training_rows')!=80000:return False
  if result.get('training_ids_sha256')!=evidence['training_ids_sha256']:return False
  if selection.get('selected_params')!=result.get('params'):return False
  role=e3_manifest.get('role_hashes',{}).get(str(rep),{})
  role_sha=role.get('source_sha256')
  role_fit_hash=role.get('id_hashes',{}).get('fit_ids')
  if evidence.get('role_membership_sha256')!=role_sha or evidence.get('training_ids_sha256')!=role_fit_hash:return False
  if evidence.get('class_order')!=[0,1,2,3,4,5,6] or evidence.get('feature_order')!=e3_manifest.get('features'):return False
  expected_group='e2_reconstructed' if fit_definition.get('reuse_pipeline') else 'e3_new_fit'
  if evidence.get('provenance_group')!=expected_group:return False
  if evidence.get('selected_params_sha256')!=_canonical_sha256(selection.get('selected_params')):return False
  if evidence.get('class_counts')!=counts:return False
  return True
 except (OSError,ValueError,TypeError,KeyError):return False
def validate_e6_execution_overlay(plan,overlay,runtime_root=R):
 root=pathlib.Path(runtime_root).resolve()
 if not isinstance(overlay,dict) or overlay.get('schema_version')!='lamost-e6-execution-overlay/2' or overlay.get('protocol_version')!=E6_V2:return False,'overlay_schema'
 if overlay.get('source_plan_sha256')!=sha(root/'manifests/tasks.json'):return False,'overlay_plan_hash'
 if overlay.get('source_e6_manifest_sha256')!=sha(root/'manifests/E6_MANIFEST.json') or overlay.get('source_e3_manifest_sha256')!=sha(root/'manifests/E3_MANIFEST.json') or overlay.get('source_build_plan_sha256')!=sha(root/'source/build_plan.py'):return False,'overlay_protocol_source_hash'
 try:e3_manifest=_read_regular_json(root/'manifests/E3_MANIFEST.json')
 except Exception:return False,'overlay_role_manifest'
 definitions={t['key']:dict(t) for t in plan}
 required={k for k,t in definitions.items() if int(t.get('experiment',0) or 0)==6 and t.get('kind')=='ensemble'}
 rows=overlay.get('tasks')
 if len(required)!=6 or not isinstance(rows,list) or len(rows)!=6:return False,'overlay_task_count'
 by={x.get('task_key'):x for x in rows if isinstance(x,dict)}
 if set(by)!=required:return False,'overlay_task_keys'
 for key in sorted(required):
  original=definitions[key];row=by[key];members=original.get('members',{});refs=original.get('member_evaluations',{})
  if row.get('e6_protocol_version')!=E6_V2 or row.get('original_task_definition_sha256')!=_canonical_sha256(original):return False,'overlay_original_definition'
  if row.get('rep')!=original.get('rep') or row.get('mode')!=original.get('mode') or row.get('members')!=members or row.get('member_evaluations')!=refs:return False,'overlay_original_members'
  fitdeps=sorted(set(members.values()))
  if row.get('effective_dependencies')!=fitdeps or sorted(original.get('dependencies',[]))!=fitdeps:return False,'overlay_fit_dependencies'
  fits=row.get('member_fit_evidence')
  if not isinstance(fits,dict) or set(fits)!=set(members):return False,'overlay_member_evidence'
  for method,fit_key in members.items():
   if not _overlay_fit_evidence_valid(fits[method],fit_key,int(original['rep']),method,definitions,e3_manifest,root):return False,'overlay_fit_evidence_'+method
  if row.get('prior_status')!='validated_terminal' or row.get('prior_outcome')!='unavailable_dependency' or row.get('prior_attempt_count')!=0:return False,'overlay_supersession_state'
  if not isinstance(row.get('prior_registry_record_sha256'),str) or len(row['prior_registry_record_sha256'])!=64:return False,'overlay_prior_record_hash'
 return True,'validated'

def _validate_existing_e6_v1_supersession(db,overlay_sha,history,manifest,names):
 if history.is_symlink() or not history.is_dir():raise RuntimeError('E6 supersession history directory is unsafe')
 if manifest.is_symlink() or not manifest.is_file():raise RuntimeError('E6 supersession manifest is not a regular file')
 raw=manifest.read_bytes()
 doc=_read_regular_json(manifest)
 if raw!=(json.dumps(doc,indent=2,sort_keys=True)+'\n').encode():raise RuntimeError('E6 supersession manifest is not canonical')
 prior={'planned':21,'outcomes':{'successful':12,'unavailable_dependency':9}}
 if doc.get('schema_version')!='lamost-e6-v1-report-supersession/1' or doc.get('overlay_sha256')!=overlay_sha or doc.get('prior_terminal_state')!=prior or doc.get('superseded_as_current') is not True:
  raise RuntimeError('existing E6 supersession manifest has wrong schema, overlay, or v1 state')
 files=doc.get('files')
 if not isinstance(files,list):raise RuntimeError('existing E6 supersession manifest files are malformed')
 allowed=set(names);seen=set()
 for row in files:
  if not isinstance(row,dict) or set(row)!={'source_path','history_path','sha256','bytes'}:raise RuntimeError('existing E6 supersession file row is malformed')
  source=row.get('source_path')
  if not isinstance(source,str) or not source.startswith('reports/'):raise RuntimeError('existing E6 supersession source path is invalid')
  name=source.removeprefix('reports/')
  expected_history='reports/history/'+history.name+'/'+name
  if name not in allowed or source!='reports/'+name or row.get('history_path')!=expected_history or name in seen:
   raise RuntimeError('existing E6 supersession file membership/path is invalid')
  seen.add(name)
  digest=row.get('sha256');size=row.get('bytes')
  if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or isinstance(size,bool) or not isinstance(size,int) or size<0:
   raise RuntimeError('existing E6 supersession file digest/size is invalid')
  archived=history/name
  if archived.is_symlink() or not archived.is_file():raise RuntimeError('existing E6 supersession history member is missing or unsafe: '+name)
  if archived.stat().st_size!=size or sha(archived)!=digest:raise RuntimeError('existing E6 supersession history member changed: '+name)
  if name=='E6_EXECUTION_TERMINAL.json':
   marker_doc=_read_regular_json(archived)
   if marker_doc.get('planned')!=21 or marker_doc.get('outcomes')!=prior['outcomes']:raise RuntimeError('archived E6 marker is not the audited v1 availability state')
   if digest!=doc.get('prior_terminal_marker_sha256'):raise RuntimeError('archived E6 marker digest differs from supersession manifest')
 if 'E6_EXECUTION_TERMINAL.json' not in seen or 'E6_FINAL_CELL_LEDGER_21.csv' not in seen:
  raise RuntimeError('existing E6 supersession history omits required v1 marker or final ledger')
 marker_sha=doc.get('prior_terminal_marker_sha256')
 if not isinstance(marker_sha,str) or len(marker_sha)!=64 or any(c not in '0123456789abcdef' for c in marker_sha):
  raise RuntimeError('existing E6 supersession marker digest is invalid')
 manifest_sha=sha(manifest)
 meta=db.execute("SELECT value FROM meta WHERE key='e6_v2_report_supersession_sha256'").fetchone()
 if meta and meta[0]!=manifest_sha:raise RuntimeError('registry E6 supersession reference differs from canonical history manifest')
 if not meta:
  db.execute("INSERT INTO meta(key,value) VALUES ('e6_v2_report_supersession_sha256',?)",(manifest_sha,))
  db.commit()
 return {'history_path':str(history),'manifest_sha256':manifest_sha,'prior_terminal_marker_sha256':marker_sha,'archived_files':len(files)}

def archive_e6_v1_outputs(db,overlay_sha):
 reports=R/'reports';history=reports/'history'/('e6_v1_availability_gate_'+overlay_sha[:16])
 if reports.is_symlink() or (reports/'history').is_symlink() or history.is_symlink():raise RuntimeError('E6 report history root is unsafe')
 history.mkdir(parents=True,exist_ok=True)
 marker=reports/'E6_EXECUTION_TERMINAL.json';archived_marker=history/'E6_EXECUTION_TERMINAL.json'
 names=(
  'E6_EXECUTION_TERMINAL.json','E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv',
  'E6_ENSEMBLE_MEMBER_PAIRED.csv','E6_FINAL_CELL_LEDGER_21.csv',
  'E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json','E6_FINAL_DESCRIPTIVE_REPORT.md',
  'E6_MEMBER_PER_REPETITION.csv','E6_candidate_ledger.csv','E6_weights.csv',
  'E6_balanced_accuracy_member_ensemble.png','E6_coverage_member_ensemble.png',
  'E6_set_size_member_ensemble.png')
 manifest=history/'SUPERSESSION_MANIFEST.json'
 if manifest.is_symlink():raise RuntimeError('E6 supersession manifest is a symlink')
 if manifest.exists():
  return _validate_existing_e6_v1_supersession(db,overlay_sha,history,manifest,names)
 if marker.exists():
  old=_read_regular_json(marker)
  if old.get('planned')!=21 or old.get('outcomes')!={'successful':12,'unavailable_dependency':9}:raise RuntimeError('current E6 terminal marker is not the audited v1 availability state')
  marker_sha=sha(marker)
 elif archived_marker.exists():
  old=_read_regular_json(archived_marker)
  if old.get('planned')!=21 or old.get('outcomes')!={'successful':12,'unavailable_dependency':9}:raise RuntimeError('archived E6 marker is not the audited v1 availability state')
  marker_sha=sha(archived_marker)
 else:raise RuntimeError('cannot supersede E6-v1 reports without preserving the audited terminal marker')
 files=[]
 for name in names:
  src=reports/name;dst=history/name
  if src.exists():
   if src.is_symlink() or not src.is_file():raise RuntimeError('refuse non-regular E6 report output: '+str(src))
   source_sha=sha(src);size=src.stat().st_size
   if dst.exists():
    if dst.is_symlink() or not dst.is_file() or sha(dst)!=source_sha:raise RuntimeError('E6 history destination conflict: '+str(dst))
    src.unlink()
   else:
    os.replace(src,dst)
    if sha(dst)!=source_sha or dst.stat().st_size!=size:raise RuntimeError('E6 historical report move verification failed: '+name)
   files.append({'source_path':'reports/'+name,'history_path':'reports/history/'+history.name+'/'+name,'sha256':source_sha,'bytes':size})
  elif dst.exists():
   if dst.is_symlink() or not dst.is_file():raise RuntimeError('invalid existing E6 history entry: '+str(dst))
   files.append({'source_path':'reports/'+name,'history_path':'reports/history/'+history.name+'/'+name,'sha256':sha(dst),'bytes':dst.stat().st_size})
 if not any(x['source_path']=='reports/E6_EXECUTION_TERMINAL.json' for x in files) or not any(x['source_path']=='reports/E6_FINAL_CELL_LEDGER_21.csv' for x in files):
  raise RuntimeError('required E6-v1 marker/final ledger not preserved')
 doc={'schema_version':'lamost-e6-v1-report-supersession/1','overlay_sha256':overlay_sha,'prior_terminal_marker_sha256':marker_sha,'prior_terminal_state':{'planned':21,'outcomes':{'successful':12,'unavailable_dependency':9}},'files':files,'superseded_as_current':True,'note':'Historical E6-v1 availability-gate outputs preserved; E6-v2 outputs must be regenerated from the superseding execution.'}
 encoded=(json.dumps(doc,indent=2,sort_keys=True)+'\n').encode()
 if manifest.exists():
  if manifest.is_symlink() or not manifest.is_file() or manifest.read_bytes()!=encoded:raise RuntimeError('E6 supersession manifest differs from expected history')
 else:atomic(manifest,doc)
 manifest_sha=sha(manifest)
 db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('e6_v2_report_supersession_sha256',?)",(manifest_sha,));db.commit()
 if marker.exists():raise RuntimeError('stale E6-v1 terminal marker remains current after archival')
 return {'history_path':str(history),'manifest_sha256':manifest_sha,'prior_terminal_marker_sha256':marker_sha,'archived_files':len(files)}

def apply_e6_v2_execution_overlay(db,tasks,frozen):
 global DEFINITIONS,E6_OVERLAY_SHA256,E6_OVERLAY_DOC
 path=R/E6_OVERLAY_REL
 if not path.exists():
  if frozen.get('e6_execution_overlay_sha256'):raise RuntimeError('freeze requires a missing E6-v2 execution overlay')
  return tasks
 if path.is_symlink() or not path.is_file():raise RuntimeError('E6-v2 overlay must be a regular non-symlink file')
 overlay_sha=sha(path)
 if frozen.get('e6_execution_overlay_sha256')!=overlay_sha:raise RuntimeError('E6-v2 overlay SHA does not match amended freeze')
 overlay=_read_regular_json(path)
 plan_doc=_read_regular_json(R/'manifests/tasks.json');plan=plan_doc['tasks'] if isinstance(plan_doc,dict) else plan_doc
 ok,reason=validate_e6_execution_overlay(plan,overlay,R)
 if not ok:raise RuntimeError('E6-v2 overlay rejected: '+reason)
 if overlay.get('original_plan_freeze_utc')!=frozen.get('frozen_utc'):raise RuntimeError('E6-v2 overlay original freeze timestamp mismatch')
 meta=db.execute("SELECT value FROM meta WHERE key='e6_v2_overlay_sha256'").fetchone()
 if meta and meta[0]!=overlay_sha:raise RuntimeError('registry was initialized with a different E6-v2 overlay')
 rows={x['task_key']:x for x in overlay['tasks']}
 v2_states=[t.get('e6_protocol_version')==E6_V2 for k,t in tasks.items() if k in rows]
 if any(v2_states) and not all(v2_states):raise RuntimeError('partial E6-v2 registry migration; manual review required')
 if all(v2_states):
  for key,row in rows.items():
   current=tasks[key]
   if current.get('e6_execution_overlay_sha256')!=overlay_sha or current.get('member_fit_evidence')!=row['member_fit_evidence']:raise RuntimeError('active E6-v2 task does not match frozen overlay')
  DEFINITIONS.update({k:{**DEFINITIONS[k],'e6_protocol_version':E6_V2,'e6_execution_overlay_sha256':overlay_sha,'member_fit_evidence':rows[k]['member_fit_evidence']} for k in rows})
  E6_OVERLAY_SHA256=overlay_sha;E6_OVERLAY_DOC=overlay
  archive_e6_v1_outputs(db,overlay_sha)
  return tasks
 pending=[]
 for key,row in rows.items():
  current=tasks[key]
  if current.get('status')!='validated_terminal' or current.get('outcome')!='unavailable_dependency' or len(current.get('attempts',[]))!=0:raise RuntimeError('E6-v2 may supersede only the audited zero-attempt unavailable rows: '+key)
  if _canonical_sha256(current)!=row['prior_registry_record_sha256']:raise RuntimeError('E6-v2 prior registry record changed since overlay review: '+key)
  pending.append((key,row,current))
 now_utc=now()
 db.execute('BEGIN IMMEDIATE')
 try:
  for key,row,prior in pending:
   prior_hash=row['prior_registry_record_sha256']
   event_doc={'protocol':'E6-v1-amended-member-evaluation-gate','superseded_by':'E6-v2','overlay_sha256':overlay_sha,'task_key':key,'prior_record_sha256':prior_hash,'prior_task_record':prior,'observed_utc':now_utc,'scientific_attempt_started':False}
   db.execute('INSERT INTO events(timestamp,kind,record) VALUES (?,?,?)',(now_utc,'e6_protocol_supersession',json.dumps(event_doc,sort_keys=True,default=str)))
   event_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
   active=dict(prior)
   active.update(status='planned',outcome=None,reason=None,validation_state='pending',observed_utc=now_utc,e6_protocol_version=E6_V2,e6_execution_overlay_sha256=overlay_sha,member_fit_evidence=row['member_fit_evidence'],supersedes_protocol_record={'event_id':event_id,'prior_record_sha256':prior_hash,'prior_outcome':'unavailable_dependency'})
   active.pop('finished_utc',None);active.pop('result',None)
   db.execute('INSERT OR REPLACE INTO tasks(key,record) VALUES (?,?)',(key,json.dumps(active,sort_keys=True,default=str)))
  db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('e6_v2_overlay_sha256',?)",(overlay_sha,))
  db.commit()
 except Exception:
  db.rollback();raise
 DEFINITIONS.update({k:{**DEFINITIONS[k],'e6_protocol_version':E6_V2,'e6_execution_overlay_sha256':overlay_sha,'member_fit_evidence':rows[k]['member_fit_evidence']} for k in rows})
 E6_OVERLAY_SHA256=overlay_sha;E6_OVERLAY_DOC=overlay
 tasks=load(db)
 archive_e6_v1_outputs(db,overlay_sha)
 return tasks

def initialize(db):
 global DEFINITIONS
 p=R/'manifests/tasks.json';plan=json.loads(p.read_text());tasks=plan['tasks'] if isinstance(plan,dict) else plan
 assert len({t['key'] for t in tasks})==len(tasks)
 DEFINITIONS={t['key']:dict(t) for t in tasks}
 keys={t['key'] for t in tasks}
 for t in tasks:
  assert set(t.get('dependencies',[]))<=keys,(t['key'],'unknown dependency')
  assert set(effective_dependencies(t))<=keys,(t['key'],'unknown effective dependency')
  assert not t['key'].startswith('/') and '..' not in t['key'].split('/')
 plan_sha=sha(p);old=db.execute("SELECT value FROM meta WHERE key='plan_sha256'").fetchone()
 if old and old[0]!=plan_sha:raise RuntimeError('Frozen plan differs from initialized registry; explicit amendment required')
 if not old:
  for t in tasks:
   t=dict(t);t.update(status='planned',outcome=None,validation_state='pending',attempts=[],observed_utc=now(),artifact_dir=str(R/'artifacts'/t['key']))
   put(db,t)
  db.execute("INSERT INTO meta VALUES ('plan_sha256',?)",(plan_sha,));db.commit()
  event(db,'plan_initialized',{'plan_sha256':plan_sha,'tasks':len(tasks)})
 return load(db)
def freeze():
 p=R/'manifests/freeze.json';actual=source_hashes()
 if p.exists():
  f=json.loads(p.read_text())
  _rf4_manifest_and_freeze(f)
  if f['source_sha256']!=actual:raise RuntimeError('Execution source changed after freeze; reviewed amendment required')
  if f.get('storage_admission_policy')!=WORKING_STORAGE_POLICY:raise RuntimeError('storage admission policy is not explicitly frozen')
  return f
 f={'protocol_version':'LAMOST-later-v1-20261025','frozen_utc':now(),'source_sha256':actual,'plan_sha256':sha(R/'manifests/tasks.json'),'bootstrap':False,'test_information_history':'E1/E2 fixed test results already observed; later plans frozen before new test evaluations','resource_policy':dict(ADAPTIVE_POLICY),'storage_admission_policy':dict(WORKING_STORAGE_POLICY),'airbag_method':'ownership lock, atomic checkpoints, actual-process supervision, bounded recovery, five-minute watchdog','airbag_skill_available':False}
 atomic(p,f);return f
def terminalize(db,t,outcome,reason=None,result=None):
 t.update(status='validated_terminal',outcome=outcome,reason=reason,finished_utc=now(),observed_utc=now(),validation_state='validated' if outcome=='successful' else 'validated_terminal_outcome')
 if result is not None:t['result']=result
 put(db,t);event(db,'task_terminal',{'key':t['key'],'outcome':outcome,'reason':reason})
E6_ORPHAN_IDENTITIES={}
def _proc_identity(pid):
 try:
  proc=pathlib.Path('/proc')/str(int(pid));tail=proc.joinpath('stat').read_text().rpartition(')')[2].split()
  uid=int(next(x.split()[1] for x in proc.joinpath('status').read_text().splitlines() if x.startswith('Uid:')))
  return {'state':tail[0],'ppid':int(tail[1]),'pgid':int(tail[2]),'start_ticks':str(tail[19]),'uid':uid}
 except (OSError,ValueError,StopIteration,IndexError):return None
def _e6_request_digest(cfg):
 task=dict(cfg.get('task') or {});task.pop('_controller_request_sha256',None)
 payload={'task':task,'attempt_id':cfg.get('attempt_id'),'result_path':cfg.get('result_path'),'dispatch_policy_id':cfg.get('dispatch_policy_id')}
 return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
def _validate_e6_phase_state(t,p,z):
 try:
  if not isinstance(z,dict) or z.get('schema_version')!='lamost-e6-phase-process/1' or z.get('role')!='e6_prediction_phase':return 'invalid_schema'
  if t.get('e6_protocol_version')!=E6_V2 or int(t.get('experiment',0) or 0)!=6:return 'not_e6_v2'
  attempt=str(t.get('attempts',[])[-1].get('attempt_id','')) if t.get('attempts') else ''
  if not attempt or z.get('attempt_id')!=attempt or p.parent.name!=attempt:return 'attempt_mismatch'
  if z.get('task_key')!=t.get('key') or z.get('stage') not in {'tune','cal','test'}:return 'task_or_stage_mismatch'
  if z.get('status') not in {'starting','running','successful','scientific_failure','operationally_interrupted','operationally_invalid'}:return 'unknown_status'
  required=('phase_id','parent_pid','parent_start_ticks','child_pid','child_start_ticks','child_uid','child_pgid','started_epoch','timeout_seconds','rss_limit_kib','termination_grace_seconds','request_path','request_sha256','worker_script_sha256')
  if any(z.get(k) is None for k in required):return 'missing_phase_identity'
  if int(z['timeout_seconds'])!=600 or int(z['termination_grace_seconds'])!=30:return 'policy_mismatch'
  if int(z['parent_pid'])!=int(t.get('pid') or -1) or str(z['parent_start_ticks'])!=str(t.get('process_start_ticks')):return 'parent_identity_mismatch'
  request=pathlib.Path(t.get('request_path',''))
  if not request.is_file() or request.is_symlink() or str(request)!=str(pathlib.Path(z['request_path'])) or not request.resolve().is_relative_to(R.resolve()):return 'request_path_mismatch'
  cfg=_read_regular_json(request);task=cfg.get('task',{})
  if cfg.get('attempt_id')!=attempt or task.get('key')!=t.get('key') or task.get('_controller_attempt_id')!=attempt:return 'request_attempt_mismatch'
  if task.get('_controller_request_path')!=str(request) or task.get('_controller_request_sha256')!=z.get('request_sha256') or _e6_request_digest(cfg)!=z.get('request_sha256'):return 'request_hash_mismatch'
  script=worker_script_for_task(task)
  if script.is_symlink() or not script.resolve().is_relative_to((R/'source').resolve()) or task.get('_controller_worker_script_path')!=str(script) or task.get('_controller_worker_script_sha256')!=z.get('worker_script_sha256') or sha(script)!=z.get('worker_script_sha256'):return 'worker_script_mismatch'
  if p.stem!='e6_phase_'+str(z.get('stage')) or not str(z.get('phase_id','')):return 'phase_id_mismatch'
  if int(z['rss_limit_kib'])!=10*1024*1024:return 'policy_mismatch'
  if int(z['child_uid'])!=os.getuid() or int(z['child_pgid'])!=int(z['child_pid']):return 'child_group_or_uid_mismatch'
  ident=_proc_identity(z['child_pid'])
  if ident is None or ident['state'] in {'Z','X','x'} or ident['start_ticks']!=str(z['child_start_ticks']):return 'child_gone'
  if ident['uid']!=int(z['child_uid']) or ident['pgid']!=int(z['child_pgid']):return 'child_live_identity_mismatch'
  parent=_proc_identity(z['parent_pid'])
  if parent and parent['start_ticks']==str(z['parent_start_ticks']) and ident['ppid']!=int(z['parent_pid']):return 'child_parent_mismatch'
  return {'pid':int(z['child_pid']),'ticks':str(z['child_start_ticks']),'pgid':int(z['child_pgid']),'uid':int(z['child_uid'])}
 except (OSError,ValueError,TypeError,KeyError,IndexError):return 'malformed_state'
def orphan_phases(t):
 out=R/'artifacts'/t['key'];found=[];E6_ORPHAN_IDENTITIES.clear();t.pop('_e6_orphan_blocked',None)
 if int(t.get('experiment',0) or 0)==6 and t.get('e6_protocol_version')==E6_V2 and t.get('kind')=='ensemble':
  attempts=out/'attempts'
  current_id=str(t.get('attempts',[])[-1].get('attempt_id','')) if t.get('attempts') else ''
  current_dir=attempts/current_id if current_id else None
  if current_id and current_dir.exists():
   if current_dir.is_symlink() or not current_dir.is_dir():
    t.setdefault('_e6_orphan_blocked',[]).append({'path':str(current_dir),'reason':'unsafe_attempt_directory'})
   else:
    for p in sorted(current_dir.glob('e6_phase_*.json')):
     try:
      checked=_validate_e6_phase_state(t,p,_read_regular_json(p))
      if isinstance(checked,dict):
       E6_ORPHAN_IDENTITIES[(checked['pid'],checked['ticks'])]=checked;found.append((checked['pid'],checked['ticks'],p))
      elif checked!='child_gone':t.setdefault('_e6_orphan_blocked',[]).append({'path':str(p),'reason':checked})
     except Exception:t.setdefault('_e6_orphan_blocked',[]).append({'path':str(p),'reason':'malformed_state'})
 for p in out.glob('attempts/**/phase_*_state.json'):
  try:
   z=json.loads(p.read_text());pid=z.get('pid');ticks=z.get('process_start_ticks')
   if not ticks and pid:ticks=start_ticks(pid)
   if alive(pid,ticks,'phase_worker.py'):found.append((int(pid),str(ticks),p))
  except Exception:pass
 return found
def terminate_verified(pid,ticks,needle='worker.py',force=False):
 checked=E6_ORPHAN_IDENTITIES.get((int(pid),str(ticks))) if needle=='phase_worker.py' else None
 if checked:
  ident=_proc_identity(pid)
  if not ident or ident['state'] in {'Z','X','x'} or ident['start_ticks']!=str(ticks) or ident['uid']!=checked['uid'] or ident['pgid']!=checked['pgid'] or checked['pgid']!=int(pid):return False
  try:os.killpg(checked['pgid'],signal.SIGKILL if force else signal.SIGTERM);return True
  except ProcessLookupError:return False
 if not alive(pid,ticks,needle):return False
 try:os.killpg(int(pid),signal.SIGKILL if force else signal.SIGTERM);return True
 except ProcessLookupError:return False
def recover(db,t,reason):
 orphan=orphan_phases(t)
 if t.get('_e6_orphan_blocked'):
  details=list(t['_e6_orphan_blocked'])
  t.update(status='operationally_interrupted',reason='E6-v2 phase ownership/state could not be verified; no process was signaled; manual review required',observed_utc=now())
  t.pop('_e6_orphan_blocked',None);put(db,t);event(db,'e6_phase_recovery_blocked',{'key':t['key'],'phase_states':details});return
 if orphan:
  if not t.get('orphan_term_epoch'):
   for pid,ticks,p in orphan:terminate_verified(pid,ticks,'phase_worker.py')
   t['orphan_term_epoch']=time.time();put(db,t);event(db,'orphan_phase_term',{'key':t['key'],'phase_pids':[x[0] for x in orphan]})
  elif time.time()-t['orphan_term_epoch']>30:
   for pid,ticks,p in orphan:terminate_verified(pid,ticks,'phase_worker.py',True)
  return
 n=int(t.get('operational_recoveries',0))
 if n>=2:
  t.update(status='operationally_interrupted',reason=reason+'; automatic recovery limit reached',observed_utc=now());put(db,t);return
 delays=ADAPTIVE_POLICY['retry_cooldown_seconds'];delay=int(delays[min(n,len(delays)-1)])
 history=list(t.get('adaptive_incident_history',[]));history.append({'observed_utc':now(),'reason':reason,'recovery_number':n+1,'checkpoint_preserved':True})
 t.update(status='planned',outcome=None,reason=reason,operational_recoveries=n+1,retry_after_epoch=time.time()+delay,pid=None,process_start_ticks=None,observed_utc=now(),adaptive_incident_history=history)
 for field in ('forced_reason','forced_outcome','forced_term_epoch','orphan_term_epoch','adaptive_emergency_term_epoch','adaptive_emergency_reason','adaptive_emergency_available_bytes'):
  t.pop(field,None)
 put(db,t);event(db,'operational_recovery',{'key':t['key'],'reason':reason,'recovery_number':n+1,'checkpoint_preserved':True})
def worker_script_for_task(task,execution_policy=None,resource_profile=None):
 if execution_policy==ET4_EXECUTION_POLICY or resource_profile==ET4_RESOURCE_PROFILE:
  try:experiment=int(task.get('experiment'))
  except (TypeError,ValueError):experiment=-1
  if (execution_policy!=ET4_EXECUTION_POLICY or resource_profile!=ET4_RESOURCE_PROFILE
      or _et4_policy() is None or task.get('kind')!='fit' or task.get('method')!='extra_trees'
      or experiment not in (4,5) or task.get('reuse_pipeline')):
   raise RuntimeError('ET4 worker dispatch metadata is invalid or not qualified')
  return R/'source'/'parallel_extra_trees'/'worker.py'
 if execution_policy is not None or resource_profile is not None:
  try:experiment=int(task.get('experiment'))
  except (TypeError,ValueError):experiment=-1
  if (execution_policy!=RF4_EXECUTION_POLICY or resource_profile!=RF4_RESOURCE_PROFILE
      or _rf4_policy() is None or task.get('kind')!='fit' or task.get('method')!='random_forest'
      or experiment not in (4,5) or task.get('reuse_pipeline')):
   raise RuntimeError('RF4 worker dispatch metadata is invalid or not qualified')
  return R/'source'/'parallel_rf'/'worker.py'
 if task.get('kind') in {'fit','eval','alias'} and task.get('method') in {'linear_svm','rbf_svm'}:
  return R/'source'/'svm_margin'/'worker.py'
 return R/'source'/'worker.py'

def _execution_worker_profile_fields(profile_id):
 if profile_id==ET4_PROFILE_ID:return {"execution_policy":ET4_EXECUTION_POLICY,"resource_profile":ET4_RESOURCE_PROFILE}
 if profile_id in (RF4_PROFILE_ID,RF4_E4_6G_PROFILE_ID,RF4_E4_REP3_PROFILE_ID):return {"execution_policy":RF4_EXECUTION_POLICY,"resource_profile":RF4_RESOURCE_PROFILE}
 return {}

def worker_request_definition(task):
 # Keep the scientific task exactly as frozen; only resolve its artifact output path.
 definition=dict(DEFINITIONS[task['key']])
 definition['artifact_dir']=str(R/'artifacts'/task['key'])
 return definition

def e5_rf_eval_profile_for_admission(task,reservation):
 if int(reservation)!=4*GIB:return None,None
 eligible,evidence=admission_evidence.eligible_e5_direct_rf_eval(task,DEFINITIONS.get(task.get('key'),{}),R)
 if (eligible and isinstance(evidence,dict)
     and evidence.get('profile_id')==admission_evidence.E5_RF_EVAL_4G_PROFILE_ID
     and evidence.get('reservation_gib')==4):
  return evidence['profile_id'],evidence
 return None,None

def e4_rf_eval_profile_for_admission(task,reservation):
 if int(reservation)!=6*GIB:return None,None
 eligible,evidence=admission_evidence.eligible_e4_treatment_rf_eval(task,DEFINITIONS.get(task.get('key'),{}),R)
 if (eligible and isinstance(evidence,dict)
     and evidence.get('profile_id')==admission_evidence.E4_RF_EVAL_6G_PROFILE_ID
     and evidence.get('reservation_gib')==6):
  return evidence['profile_id'],evidence
 return None,None

def e4_rf_fit_5g_profile_for_admission(task,reservation):
 if int(reservation)!=5*GIB:return None,None
 eligible,evidence=admission_evidence.eligible_e4_treatment_rf_fit_5gib(task,DEFINITIONS.get(task.get('key'),{}),R)
 if (eligible and isinstance(evidence,dict)
     and evidence.get('profile_id')==admission_evidence.E4_RF_FIT_5G_PROFILE_ID
     and evidence.get('reservation_gib')==5):
  return evidence['profile_id'],evidence
 return None,None

def _is_e6_v2_ensemble(task):
 try:return int(task.get('experiment',0) or 0)==6 and task.get('kind')=='ensemble' and task.get('e6_protocol_version')==E6_V2
 except (TypeError,ValueError):return False

def _dispatch_stage_priority(task):
 if task.get('reuse_pipeline'):return 0
 if _is_e6_v2_ensemble(task):return 2
 return {'alias':0,'e4_cohort':1,'e5_corruption':1,'e4_treatment':2,'e4_append':2,'eval':2,'generate':3,'fit':4,'ensemble':6}.get(task.get('kind'),7)

def _e6_v2_lane_waiting(running,ordered_ready,available,charges):
 # When a selected E6-v2 ensemble is ready but its unchanged reservation is not
 # admissible, let current workers drain and keep sinks available; do not add fits.
 if any(_is_e6_v2_ensemble(t) for t in running):return False
 candidates=[t for t in ordered_ready if _is_e6_v2_ensemble(t)]
 if not candidates:return False
 reservations=[(x['reservation_bytes'],x['credited_pss_bytes']) for x in charges]
 return not any(memory_admission_ok(available,reservations,worker_reservation_bytes(t)) for t in candidates)

def _is_e45_arf_fit(task):
 try:
  return task.get('kind')=='fit' and task.get('method')=='arf' and task.get('route')=='direct' and int(task.get('experiment',0)) in (4,5)
 except (TypeError,ValueError):
  return False

def _eligible_waiting_arf6_fit(ready):
 for task in ready:
  if not _is_e45_arf_fit(task):continue
  if task.get('attempts') or task.get('admission_reservation_bytes') is not None:continue
  if task.get('status') not in ('planned','waiting_dependency','waiting_for_dependency'):continue
  if worker_reservation_bytes(task)==6*GIB:return task
 return None

def _is_e4_et_control_fit(task):
 # One-time dependency lane for the three E5 ExtraTrees clean baselines.
 # Match only the frozen E4 direct control keys; never promote attempted work.
 try:
  rep=int(task.get('rep'))
  if rep not in (1,2,3):return False
  if (int(task.get('experiment',0) or 0)!=4 or task.get('kind')!='fit'
      or task.get('method')!='extra_trees' or task.get('route')!='direct'
      or task.get('condition')!='control'
      or task.get('key')!=f"e4/rep_{rep}/fit/direct/extra_trees/control"
      or task.get('attempts') or task.get('admission_reservation_bytes') is not None):
   return False
  status=task.get('status')
  return status is None or status in ('planned','waiting_for_dependency')
 except (TypeError,ValueError):
  return False

def order_ready_for_admission(running,ready):
 # Keep light work ahead of heavy work while a heavy lane is occupied.
 heavy_lane=any(worker_resource_class(t)=='heavy' for t in running)
 rf_heavy=any(t.get('kind')=='fit' and t.get('method')=='random_forest' and worker_resource_class(t)=='heavy' for t in running)
 preferred_arf_key=None
 if rf_heavy:
  # Check only until the first actually eligible 6 GiB ARF fit; the regular
  # admission pass rechecks its reservation and all other candidates unchanged.
  for candidate in ready:
   if candidate.get('kind')=='fit' and candidate.get('method')=='arf' and worker_resource_class(candidate)=='heavy':
    if worker_reservation_bytes(candidate)==6*GIB:
     preferred_arf_key=candidate.get('key');break
 decorated=[]
 for index,t in enumerate(ready):
  light_first=0 if heavy_lane and worker_resource_class(t)=='light' else 1
  stage=_dispatch_stage_priority(t)
  # Preserve the existing ARF6 lane; otherwise, advance only the three
  # untouched E4 ExtraTrees controls that unlock E5 fit dependencies.
  if preferred_arf_key is not None and t.get('key')==preferred_arf_key:
   packing=0
  elif _is_e4_et_control_fit(t):
   packing=1
  else:
   packing=2
  decorated.append(((light_first,stage,packing,index),t))
 return [t for _,t in sorted(decorated,key=lambda x:x[0])]

def light_fit_blocked(task,heavy_fit_waiting):
 return bool(heavy_fit_waiting and task.get('kind')=='fit' and worker_resource_class(task)=='light')

def admit(db,t,idle_hint=None,storage_drain_evidence=None):
 # Keep the verified scientific candidate immutable across operational metadata updates.
 pristine_candidate=copy.deepcopy(t)
 overlap_evidence=_archive_fit_launch_gate(db,pristine_candidate,idle_hint)
 if overlap_evidence is False:return False
 aid=uuid.uuid4().hex;attempt=R/'attempts'/t['key']/aid;attempt.mkdir(parents=True,exist_ok=True)
 request=attempt/'request.json';result=attempt/'worker_result.json';log=attempt/'worker.log'
 reservation=worker_reservation_bytes(t)
 profile_id=t.get('admission_profile_id') if t.get('admission_reservation_bytes') is not None and not t.get('adaptive_promoted_heavy') else None
 profile_evidence=t.get('admission_profile_evidence') if profile_id and not t.get('adaptive_promoted_heavy') else None
 rf6_rep3_evidence=_e4_treatment_rf4_rep3_6g_eligible(t) if not t.get('attempts') else None
 rf6_evidence=_e4_treatment_rf4_6g_eligible(t) if not t.get('attempts') else None
 rf4_evidence=_rf4_fit_eligible(t) if not t.get('attempts') else None
 et4_evidence=_et4_fit_eligible(t) if not t.get('attempts') else None
 if rf6_rep3_evidence is not None:
  if reservation!=6*GIB:raise RuntimeError('qualified E4 rep3 treatment RF4 task lacks 6 GiB reservation')
  profile_id=RF4_E4_REP3_PROFILE_ID;profile_evidence=rf6_rep3_evidence
 elif rf6_evidence is not None:
  if reservation!=6*GIB:raise RuntimeError('qualified E4 treatment RF4 task lacks 6 GiB reservation')
  profile_id=RF4_E4_6G_PROFILE_ID;profile_evidence=rf6_evidence
 elif rf4_evidence is not None:
  if reservation!=10*GIB:raise RuntimeError('qualified RF4 task lacks required 10 GiB reservation')
  profile_id=RF4_PROFILE_ID;profile_evidence=rf4_evidence
 elif et4_evidence is not None:
  if reservation!=10*GIB:raise RuntimeError('qualified ET4 task lacks required 10 GiB reservation')
  profile_id=ET4_PROFILE_ID;profile_evidence=et4_evidence
 elif _has_recorded_rf4_profile(t):
  if reservation!=10*GIB or profile_id not in (None,RF4_PROFILE_ID):
   raise RuntimeError('recorded RF4 operational resume profile is inconsistent')
  profile_id=RF4_PROFILE_ID
  profile_evidence=t.get('admission_profile_evidence')
  if not profile_evidence and t.get('attempts'):
   profile_evidence=t['attempts'][-1].get('resource_profile',{}).get('admission_profile_evidence')
 elif _has_recorded_et4_profile(t):
  if reservation!=10*GIB or profile_id not in (None,ET4_PROFILE_ID):
   raise RuntimeError('recorded ET4 operational resume profile is inconsistent')
  profile_id=ET4_PROFILE_ID
  profile_evidence=t.get('admission_profile_evidence')
  if not profile_evidence and t.get('attempts'):
   profile_evidence=t['attempts'][-1].get('resource_profile',{}).get('admission_profile_evidence')
 elif _has_recorded_e4_treatment_rf6_profile(t):
  recorded_rf6_profile=_recorded_e4_treatment_rf6_profile_id(t)
  if reservation not in (6*GIB,10*GIB) or (reservation==10*GIB and not t.get('adaptive_promoted_heavy')) or profile_id not in (None,RF4_E4_6G_PROFILE_ID,RF4_E4_REP3_PROFILE_ID):
   raise RuntimeError('recorded E4 RF6 operational resume profile is inconsistent')
  profile_id=recorded_rf6_profile
  profile_evidence=t.get('admission_profile_evidence')
  if not profile_evidence and t.get('attempts'):
   profile_evidence=t['attempts'][-1].get('resource_profile',{}).get('admission_profile_evidence')
 if not profile_id:
  eval_profile_id,eval_evidence=e5_rf_eval_profile_for_admission(t,reservation)
  if eval_profile_id:
   profile_id=eval_profile_id;profile_evidence=eval_evidence
  else:
   e4_eval_profile_id,e4_eval_evidence=e4_rf_eval_profile_for_admission(t,reservation)
   if e4_eval_profile_id:
    profile_id=e4_eval_profile_id;profile_evidence=e4_eval_evidence
   else:
    e4_fit_profile_id,e4_fit_evidence=e4_rf_fit_5g_profile_for_admission(t,reservation)
    if e4_fit_profile_id:
     profile_id=e4_fit_profile_id;profile_evidence=e4_fit_evidence
    elif is_e4_direct_rf_80k(t) and reservation==4*GIB: profile_id=E4_RF_80K_PROFILE_VERSION
    else:
     eligible,evidence=admission_evidence.eligible_2gib_resource_profile(t,DEFINITIONS.get(t.get('key'),{}),R)
     allowed_2g={admission_evidence.GENERATOR_2G_PROFILE_ID,admission_evidence.E5_GENERATION_2G_PROFILE_ID}
     if (eligible and reservation==2*GIB and isinstance(evidence,dict)
         and evidence.get('reservation_gib')==2 and evidence.get('profile_id') in allowed_2g):
      profile_id=evidence['profile_id'];profile_evidence=evidence
     else:
      eligible,evidence=admission_evidence.eligible_4gib(t,DEFINITIONS.get(t.get('key'),{}),R)
      if eligible and reservation==4*GIB: profile_id=admission_evidence.PROFILE_ID;profile_evidence=evidence
      else:
       eligible,evidence=admission_evidence.eligible_rf_resource_profiles(t,DEFINITIONS.get(t.get('key'),{}),R)
       known_rf={admission_evidence.E5_RF_4G_PROFILE_ID:4,admission_evidence.E4_GENERATED_RF_6G_PROFILE_ID:6,admission_evidence.E4_TREATMENT_RF_6G_PROFILE_ID:6,
                 admission_evidence.E4_RF_FIT_5G_PROFILE_ID:5,admission_evidence.E4_WEIGHTED_RF_5G_PROFILE_ID:5,
                 admission_evidence.E4_ARF_6G_PROFILE_ID:6,admission_evidence.E5_ARF_6G_PROFILE_ID:6}
       if (eligible and isinstance(evidence,dict) and evidence.get('profile_id') in known_rf
           and evidence.get('reservation_gib')==known_rf[evidence['profile_id']]
           and reservation==known_rf[evidence['profile_id']]*GIB):
        profile_evidence=evidence;profile_id=evidence['profile_id']
       else: profile_id='adaptive-concurrency-20261025-v1.1-default'
 if profile_id=='adaptive-concurrency-20261025-v1.1-default' and reservation==2*GIB:
  arf_eligible,arf_evidence=admission_evidence.eligible_e4_direct_arf_eval_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if (arf_eligible and isinstance(arf_evidence,dict) and arf_evidence.get('profile_id')==admission_evidence.E4_ARF_EVAL_2G_PROFILE_ID
      and arf_evidence.get('reservation_gib')==2 and arf_evidence.get('resource_audit',{}).get('sha256')==admission_evidence.E4_ARF_EVAL_2G_AUDIT_SHA256):
   profile_id=arf_evidence['profile_id'];profile_evidence=arf_evidence
 if profile_id=='adaptive-concurrency-20261025-v1.1-default' and reservation==2*GIB:
  for gate in (admission_evidence.eligible_e4_arf_generation_2gib,admission_evidence.eligible_e5_arf_generation_2gib):
   gen_eligible,gen_evidence=gate(t,DEFINITIONS.get(t.get('key'),{}),R)
   if (gen_eligible and isinstance(gen_evidence,dict) and gen_evidence.get('reservation_gib')==2
       and gen_evidence.get('resource_audit',{}).get('bindings_sha256')==admission_evidence.E4_E5_ARF_GENERATION_BINDINGS_SHA256):
    expected=(admission_evidence.E4_ARF_GENERATION_2G_PROFILE_ID if gate==admission_evidence.eligible_e4_arf_generation_2gib else admission_evidence.E5_ARF_GENERATION_2G_PROFILE_ID)
    if gen_evidence.get('profile_id')==expected:
     profile_id=expected;profile_evidence=gen_evidence;break
 if profile_id=='adaptive-concurrency-20261025-v1.1-default' and reservation in (2*GIB,3*GIB):
  eligible,evidence=admission_evidence.eligible_knn_rbf_resource_profile(t,DEFINITIONS.get(t.get('key', ''),{}),R)
  if (eligible and isinstance(evidence,dict)
      and evidence.get('reservation_gib')*GIB==reservation
      and evidence.get('resource_audit',{}).get('v2_sha256')==admission_evidence.KNN_RBF_V2_AUDIT_SHA256):
   profile_id=evidence['profile_id'];profile_evidence=evidence
 resource_profile=dict(ADAPTIVE_POLICY);resource_profile.update({'admission_profile_id':profile_id,'admission_reservation_bytes':reservation})
 if storage_drain_evidence is not None:resource_profile['storage_drain_policy']=dict(storage_drain_evidence)
 if profile_id in (RF4_PROFILE_ID,RF4_E4_6G_PROFILE_ID,RF4_E4_REP3_PROFILE_ID):
  resource_profile.update({'execution_policy':RF4_EXECUTION_POLICY,'resource_profile':RF4_RESOURCE_PROFILE,'cpu_reservation_units':RF4_CPU_UNITS,'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1})
 if profile_id==ET4_PROFILE_ID:
  resource_profile.update({'execution_policy':ET4_EXECUTION_POLICY,'resource_profile':ET4_RESOURCE_PROFILE,'cpu_reservation_units':ET4_CPU_UNITS,'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1})
 if profile_evidence:resource_profile['admission_profile_evidence']=dict(profile_evidence)
 if overlap_evidence:resource_profile['archive_native_fit_overlap_admission']=overlap_evidence
 t['admission_reservation_bytes']=reservation;t['admission_profile_id']=profile_id
 if profile_evidence:t['admission_profile_evidence']=dict(profile_evidence)
 definition=worker_request_definition(t)
 if int(definition.get('experiment',0) or 0)==6 and definition.get('kind')=='ensemble' and definition.get('e6_protocol_version')==E6_V2:
  script=worker_script_for_task(definition)
  definition['_controller_attempt_id']=aid
  definition['_controller_request_path']=str(request)
  definition['_controller_worker_script_path']=str(script)
  definition['_controller_worker_script_sha256']=sha(script)
  definition['e6_execution_overlay_sha256']=E6_OVERLAY_SHA256
 if int(definition.get('experiment',0) or 0)==6 and definition.get('kind')=='ensemble':
  allstates=load(db);eff=effective_dependencies(definition);t['effective_dependencies']=eff;put(db,t)
  definition['effective_dependencies']=eff
  definition['member_evaluation_dependency_observations']={k:{'status':allstates[k]['status'],'outcome':allstates[k].get('outcome'),'reason':allstates[k].get('reason')} for k in definition.get('member_evaluations',{}).values()}
 cfg={'task':definition,'attempt_id':aid,'result_path':str(result),'dispatch_policy_id':DISPATCH_POLICY_ID}
 cfg.update(_execution_worker_profile_fields(profile_id))
 worker_script=worker_script_for_task(definition,cfg.get('execution_policy'),cfg.get('resource_profile'))
 if definition.get('e6_protocol_version')==E6_V2 and int(definition.get('experiment',0) or 0)==6:
  definition['_controller_request_sha256']=_e6_request_digest(cfg)
 atomic(request,cfg)
 env=os.environ.copy();env.update(THREADS);env['PYTHONUNBUFFERED']='1'
 final_overlap_evidence=_archive_fit_launch_gate(db,pristine_candidate,idle_hint)
 if (final_overlap_evidence is False or _archive_overlap_evidence_identity(final_overlap_evidence)!=_archive_overlap_evidence_identity(overlap_evidence)):
  shutil.rmtree(attempt)
  return False
 if final_overlap_evidence:
  resource_profile['archive_native_fit_overlap_admission']=final_overlap_evidence
  t['admission_resource_policy']=dict(resource_profile)
 with log.open('w') as f:
  p=subprocess.Popen(['/usr/bin/nice','-n',str(ADAPTIVE_POLICY['worker_nice']),sys.executable,str(worker_script),str(request)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env=env)
 t.update(status='running',pid=p.pid,process_start_ticks=start_ticks(p.pid),started_utc=now(),started_epoch=time.time(),result_path=str(result),request_path=str(request),observed_utc=now())
 t['adaptive_policy_revision']=ADAPTIVE_REVISION;t['admission_resource_policy']=dict(resource_profile);t['dispatch_policy_id']=DISPATCH_POLICY_ID
 t['admission_resource_observation']=dict(LAST_MEMORY_ADMISSION)
 t.setdefault('attempts',[]).append({'attempt_id':aid,'request_path':str(request),'result_path':str(result),'started_utc':t['started_utc'],'reason':t.get('reason','initial planned attempt'),'resource_profile':dict(resource_profile),'dispatch_policy_id':DISPATCH_POLICY_ID})
 t.pop('_archive_native_fit_overlap_proof',None)
 put(db,t);event(db,'worker_started',{'key':t['key'],'attempt_id':aid,'pid':p.pid,'process_start_ticks':t['process_start_ticks']})
 return True
def job_limit(t):
 if t['kind']=='fit':return (int(t.get('trials',10))+3)*660+120
 if t['kind']=='eval':return 2*660+120
 if t['kind']=='ensemble':return 6*660+120
 return 660+120

def verified_adaptive_worker(t):
 if t.get('adaptive_policy_revision')!=ADAPTIVE_REVISION or not t.get('attempts'):return False
 if not alive(t.get('pid'),t.get('process_start_ticks')):return False
 try:
  argv=pathlib.Path('/proc',str(t['pid']),'cmdline').read_bytes().decode(errors='replace').split('\0')
  request=pathlib.Path(t['request_path']);cfg=json.loads(request.read_text())
  cfg_task=cfg.get('task',{})
  return str(worker_script_for_task(cfg_task,cfg.get('execution_policy'),cfg.get('resource_profile'))) in argv and str(request) in argv and cfg.get('attempt_id')==t['attempts'][-1].get('attempt_id') and cfg_task.get('key')==t['key']
 except Exception:return False

def pending_reclaim_in_grace(tasks,available_bytes,observed_epoch=None):
 """Recent recorded TERM is cleanup-state reservation debt, not a liveness claim."""
 if int(available_bytes)<EMERGENCY_FLOOR:return []
 observed=time.time() if observed_epoch is None else float(observed_epoch)
 grace=float(ADAPTIVE_POLICY['termination_grace_seconds'])
 pending=[]
 for t in tasks.values():
  term=t.get('adaptive_emergency_term_epoch')
  if t.get('status')!='running' or term is None:continue
  try:age=observed-float(term)
  except (TypeError,ValueError):continue
  if 0<=age<=grace:pending.append(t['key'])
 return sorted(pending)

def emergency_interrupt_one(db,tasks):
 """At critical memory pressure TERM only a verified task admitted by this staged policy."""
 global EMERGENCY_BACKOFF_UNTIL
 running=[t for t in tasks.values() if t.get('status')=='running']
 available,credits,peaks=bracketed_worker_memory(running)
 growth_debt=0;promoted_keys=[]
 for t,pss,peak in zip(running,credits,peaks):
  res=worker_reservation_bytes(t)
  if peak>res and not t.get('adaptive_promoted_heavy'):
   t['adaptive_promoted_heavy']=True;t['adaptive_promotion_reason']='observed process-tree PSS exceeded provisional reservation';t['adaptive_promoted_utc']=now();put(db,t);res=10*GIB;promoted_keys.append(t['key'])
  growth_debt+=max(0,res-min(res,pss))
 archive_context=archive_fit_overlap_context()
 if archive_context.get('mode')=='active':
  helper_measurement=_bracketed_archive_helper(archive_context)
  if helper_measurement is None:growth_debt+=archive_fit_admission.HELPER_RESERVATION_BYTES
  else:growth_debt+=max(0,archive_fit_admission.HELPER_RESERVATION_BYTES-min(archive_fit_admission.HELPER_RESERVATION_BYTES,helper_measurement['credited_pss_bytes']))
 # At 8 GiB, pause admissions; reclaim only when observed free memory plus headroom cannot honor current reservations.
 if not promoted_keys and not needs_resource_reclaim(available,growth_debt):return None
 if promoted_keys and not needs_resource_reclaim(available,growth_debt):
  atomic(R/'memory_emergency_observation.json',{'observed_utc':now(),'available_bytes':available,'growth_commitment_bytes':growth_debt,'promoted_keys':promoted_keys,'interrupted_key':None,'reason':'light worker promoted to 10 GiB; admissions paused for one measurement cycle'})
  return {'promoted_keys':promoted_keys,'interrupted_key':None}
 pending=pending_reclaim_in_grace(tasks,available)
 if pending:
  EMERGENCY_BACKOFF_UNTIL=max(EMERGENCY_BACKOFF_UNTIL,time.time()+int(ADAPTIVE_POLICY['emergency_backoff_seconds']))
  atomic(R/'memory_emergency_observation.json',{'observed_utc':now(),'available_bytes':available,'growth_commitment_bytes':growth_debt,'pending_termination_keys':pending,'interrupted_key':None,'reason':'previous recorded TERM awaits controller cleanup within grace; defer another noncritical interruption without claiming process liveness'})
  return {'available_bytes':available,'interrupted_key':None,'pending_termination_keys':pending,'reason':'recorded reclaim cleanup-state grace'}
 EMERGENCY_BACKOFF_UNTIL=max(EMERGENCY_BACKOFF_UNTIL,time.time()+int(ADAPTIVE_POLICY['emergency_backoff_seconds']))
 candidates=[t for t in tasks.values() if adaptive_task_eligible(t) and not pathlib.Path(t.get('result_path','/nonexistent')).is_file() and verified_adaptive_worker(t)]
 candidates.sort(key=lambda t:(t['key'] not in promoted_keys,-float(t.get('started_epoch',0))))
 if not candidates:
  atomic(R/'memory_emergency_observation.json',{'observed_utc':now(),'available_bytes':available,'growth_commitment_bytes':growth_debt,'interrupted_key':None,'reason':'headroom guard; no eligible newly admitted task; existing original workers preserved','backoff_until_epoch':EMERGENCY_BACKOFF_UNTIL})
  return {'available_bytes':available,'interrupted_key':None,'reason':'no eligible new adaptive task'}
 t=candidates[0]
 if pathlib.Path(t.get('result_path','/nonexistent')).is_file():
  return {'available_bytes':available,'interrupted_key':None,'reason':'current attempt result appeared before signal; result processing has priority'}
 if not verified_adaptive_worker(t):
  atomic(R/'memory_emergency_observation.json',{'observed_utc':now(),'available_bytes':available,'growth_commitment_bytes':growth_debt,'interrupted_key':None,'reason':'target process failed strict adaptive ownership verification; no signal sent'})
  return None
 terminate_verified(t['pid'],t['process_start_ticks'])
 t['adaptive_emergency_term_epoch']=time.time();t['adaptive_emergency_reason']='resource headroom guard; checkpoint-preserving adaptive operational interruption';t['adaptive_emergency_available_bytes']=available;put(db,t);event(db,'adaptive_resource_reclaim_requested',{'key':t['key'],'attempt_id':t['attempts'][-1]['attempt_id'],'available_bytes':available,'growth_commitment_bytes':growth_debt})
 # Persist through caller on next check_running pass; no scientific failure is assigned.
 atomic(R/'memory_emergency_observation.json',{'observed_utc':now(),'available_bytes':available,'interrupted_key':t['key'],'attempt_id':t['attempts'][-1]['attempt_id'],'pid':t['pid'],'process_start_ticks':t['process_start_ticks'],'reason':t['adaptive_emergency_reason'],'backoff_until_epoch':EMERGENCY_BACKOFF_UNTIL})
 return t['key']

def check_running(db,tasks):
 procs=process_table()
 for t in list(tasks.values()):
  if t['status']!='running':continue
  if t.get('adaptive_emergency_term_epoch') and not pathlib.Path(t.get('result_path','/nonexistent')).is_file():
   orphan=orphan_phases(t)
   for pid,ticks,p in orphan:terminate_verified(pid,ticks,'phase_worker.py',time.time()-t['adaptive_emergency_term_epoch']>30)
   if not alive(t.get('pid'),t.get('process_start_ticks')) and not orphan:
    recover(db,t,t.get('adaptive_emergency_reason','adaptive memory guard interruption'));continue
   if time.time()-t['adaptive_emergency_term_epoch']>30 and verified_adaptive_worker(t):
    terminate_verified(t['pid'],t['process_start_ticks'],force=True)
   continue
  if t.get('forced_reason') and not alive(t.get('pid'),t.get('process_start_ticks')):
   orphan=orphan_phases(t)
   for pid,ticks,p in orphan:terminate_verified(pid,ticks,'phase_worker.py',time.time()-t.get('forced_term_epoch',0)>30)
   if not orphan:
    if t.get('forced_outcome','scientific_failure')=='scientific_failure':terminalize(db,t,'scientific_failure',t['forced_reason'])
    else:
     t.update(status='operationally_invalid',reason=t['forced_reason'],observed_utc=now());put(db,t);event(db,'outer_supervision_invalid',{'key':t['key'],'reason':t['reason']})
   continue
  result=pathlib.Path(t.get('result_path','/nonexistent'))
  if result.is_file():
   try:r=json.loads(result.read_text())
   except Exception:continue
   if r.get('controller_attempt_id')!=t['attempts'][-1]['attempt_id']:
    t.update(status='operationally_invalid',reason='worker attempt identity mismatch');put(db,t);continue
   st=r.get('status')
   if st in TERMINAL:
    if st=='successful' and not r.get('validation'):
     t.update(status='operationally_invalid',reason='successful worker lacks artifact validation',result=r);put(db,t)
    else:terminalize(db,t,st,r.get('reason'),r)
   elif st=='operationally_interrupted':recover(db,t,r.get('reason','worker-reported operational interruption'))
   else:
    t.update(status='operationally_invalid',reason=r.get('reason','worker returned invalid state'),result=r,observed_utc=now());put(db,t);event(db,'operational_invalid',{'key':t['key'],'reason':t['reason']})
   continue
  if not alive(t.get('pid'),t.get('process_start_ticks')):
   # Reap only a zombie whose PID, start ticks, and direct-parent identity still match.
   # Adopted children and live/reused PIDs are never waited on or signalled here.
   archive_fit_admission.reap_zombie_child(t.get('pid'),t.get('process_start_ticks'),os.getpid())
   recover(db,t,'verified worker process absent without terminal result');continue
  rss,ids=tree_rss(t['pid'],procs)
  t['peak_tree_rss_bytes']=max(t.get('peak_tree_rss_bytes',0),rss)
  exceeded=rss>10*1024**3 or time.time()-t.get('started_epoch',time.time())>job_limit(t)
  if exceeded:
   if not t.get('forced_term_epoch'):
    terminate_verified(t['pid'],t['process_start_ticks'])
    for pid,ticks,p in orphan_phases(t):terminate_verified(pid,ticks,'phase_worker.py')
    t['forced_term_epoch']=time.time();t['forced_reason']='worker process-tree memory policy exceeded' if rss>10*1024**3 else 'worker outer supervision deadline exceeded; phase supervisor defect requires review';t['forced_outcome']='scientific_failure' if rss>10*1024**3 else 'operationally_invalid';put(db,t)
   elif time.time()-t['forced_term_epoch']>30:
    terminate_verified(t['pid'],t['process_start_ticks'],force=True)
    for pid,ticks,p in orphan_phases(t):terminate_verified(pid,ticks,'phase_worker.py',True)
    if t.get('forced_outcome','scientific_failure')=='scientific_failure':terminalize(db,t,'scientific_failure',t['forced_reason'])
    else:
     t.update(status='operationally_invalid',reason=t['forced_reason'],observed_utc=now());put(db,t)
def effective_dependencies(t):
 """V1 keeps the historical reference gate; V2 waits on selected fits only."""
 deps=list(t.get('dependencies',[]))
 if int(t.get('experiment',0) or 0)==6 and t.get('kind')=='ensemble':
  if t.get('e6_protocol_version')==E6_V2:return deps
  refs=t.get('member_evaluations',{})
  if isinstance(refs,dict):
   for key in refs.values():
    if key not in deps: deps.append(key)
 return deps
def dependency_readiness(t,tasks):
 deps=effective_dependencies(t)
 failed=[tasks[k] for k in deps if tasks[k]['status']=='validated_terminal' and tasks[k].get('outcome')!='successful']
 waiting=[tasks[k] for k in deps if tasks[k]['status']!='validated_terminal']
 return deps,failed,waiting
def ready_tasks(db,tasks):
 ready=[]
 for t in tasks.values():
  if t['status'] not in ['planned','waiting_for_dependency']:continue
  if float(t.get('retry_after_epoch',0))>time.time():continue
  deps,failed,waiting=dependency_readiness(t,tasks)
  if int(t.get('experiment',0) or 0)==6 and t.get('kind')=='ensemble':
   t['effective_dependencies']=deps
  if failed:
   terminalize(db,t,'unavailable_dependency','; '.join(d['key']+': '+str(d.get('outcome')) for d in failed));continue
  if not waiting:ready.append(t)
  elif t['status']!='waiting_for_dependency':
   t['status']='waiting_for_dependency';put(db,t)

 priority={'alias':0,'e4_cohort':1,'e5_corruption':1,'e4_treatment':2,'e4_append':2,'generate':3,'fit':4,'eval':2,'ensemble':6}
 methods={'gmm':0,'copula':1,'chow_liu':2,'gaussian_nb':3,'lda':4,'qda':5,'shared_diagonal':6,'logistic':7,'hist_gb':8,'cart':9,'random_forest':10,'extra_trees':11,'linear_svm':12,'knn':13,'arf':14,'kde':15,'rbf_svm':16}
 return sorted(ready,key=lambda t:(t['experiment'],0 if t.get('reuse_pipeline') else priority.get(t['kind'],7),methods.get(t.get('method'),0),t['key']))
LAST_MEMORY_ADMISSION={}
def worker_resource_class(t):
 method=str(t.get('method','')).lower();kind=str(t.get('kind','')).lower()
 light_methods={'gaussian_nb','lda','qda','shared_diagonal','logistic','cart','linear_svm','kde','hist_gb'}
 heavy_methods={'random_forest','extra_trees','arf','rbf_svm','knn'}
 if t.get('adaptive_promoted_heavy'):return 'heavy'
 if (admission_evidence.has_e5_direct_rf_eval_profile(t) or admission_evidence.has_e4_treatment_rf_eval_profile(t) or admission_evidence.has_e4_direct_arf_eval_profile(t) or admission_evidence.has_e4_arf_generation_profile(t) or admission_evidence.has_e5_arf_generation_profile(t)):return 'light'
 if admission_evidence.has_knn_rbf_resource_profile(t):return 'light'
 if kind=='eval' and int(t.get('experiment',0) or 0)==5 and method=='random_forest' and t.get('route')=='direct':
  eligible,_evidence=admission_evidence.eligible_e5_direct_rf_eval(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 'light'
 if kind=='eval' and int(t.get('experiment',0) or 0)==4 and method=='random_forest' and t.get('route')=='treatment':
  eligible,_evidence=admission_evidence.eligible_e4_treatment_rf_eval(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 'light'
 if kind=='eval' and int(t.get('experiment',0) or 0)==4 and method=='arf' and t.get('route')=='direct':
  eligible,_evidence=admission_evidence.eligible_e4_direct_arf_eval_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 'light'
 if kind=='generate' and int(t.get('experiment',0) or 0)==4 and t.get('generator')=='arf':
  eligible,_evidence=admission_evidence.eligible_e4_arf_generation_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 'light'
 if kind=='generate' and int(t.get('experiment',0) or 0)==5 and t.get('generator')=='arf':
  eligible,_evidence=admission_evidence.eligible_e5_arf_generation_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 'light'
 if not t.get('attempts') and kind in {'fit','eval'} and method in {'knn','rbf_svm'}:
  eligible,_evidence=admission_evidence.eligible_knn_rbf_resource_profile(t,DEFINITIONS.get(t.get('key',''),{}),R)
  if eligible:return 'light'
 if method in heavy_methods:return 'heavy'
 if method in {'gmm','copula','chow_liu'}:return 'heavy' if kind=='fit' else 'light'
 if method in light_methods:return 'light'
 if kind in {'alias','e4_cohort','e5_corruption','e4_treatment','e4_append'}:return 'light'
 if kind=='generate':return 'heavy' if method=='arf' else ('light' if method in {'gmm','copula','chow_liu','kde'} else 'heavy')
 if kind=='eval' and method in light_methods:return 'light'
 return 'heavy'
def is_e4_direct_rf_80k(t):
 try:
  rep=int(t.get('rep'))
  return (int(t.get('experiment',0) or 0)==4 and t.get('kind')=='fit' and
   t.get('method')=='random_forest' and t.get('route')=='direct' and
   rep in E4_RF_80K_REPS and t.get('condition') in E4_RF_80K_CONDITIONS and
   t.get('train_key')==f"e4/rep_{rep}/cohort/{t.get('condition')}")
 except (TypeError,ValueError):return False
def worker_reservation_bytes(t):
 if t.get('adaptive_promoted_heavy'):return 10*GIB
 # A recorded RF4 attempt always carries the full hard-limit reservation;
 # malformed historical metadata must not lower its memory commitment.
 if _has_recorded_rf4_profile(t):return 10*GIB
 if _has_recorded_et4_profile(t):return 10*GIB
 if _has_recorded_e4_treatment_rf6_profile(t):return 6*GIB
 recorded=t.get('admission_reservation_bytes')
 if recorded is not None:
  try:return min(10*GIB,max(0,int(recorded)))
  except (TypeError,ValueError):return 10*GIB
 # Narrow E4 treatment RF4 estimate; historical attempts remain at recorded reservations.
 if not t.get('attempts'):
  rf6_rep3=_e4_treatment_rf4_rep3_6g_eligible(t)
  if rf6_rep3 is not None and rf6_rep3.get('reservation_gib')==6:return 6*GIB
  rf6=_e4_treatment_rf4_6g_eligible(t)
  if rf6 is not None and rf6.get('reservation_gib')==6:return 6*GIB
 # RF4 is prospective only and needs a freeze-bound qualified policy.
 if not t.get('attempts'):
  rf4=_rf4_fit_eligible(t)
  if rf4 is not None and rf4.get('reservation_gib')==10:return 10*GIB
  et4=_et4_fit_eligible(t)
  if et4 is not None and et4.get('reservation_gib')==10:return 10*GIB
 # Prospective only: tasks with any prior attempt keep their historical
 # reservation unless explicitly persisted on the task itself.
 if not t.get('attempts') and is_e4_direct_rf_80k(t):return 4*GIB
 if not t.get('attempts'):
  eligible,evidence=admission_evidence.eligible_e4_direct_arf_eval_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E4_ARF_EVAL_2G_PROFILE_ID and evidence.get('reservation_gib')==2 and evidence.get('resource_audit',{}).get('sha256')==admission_evidence.E4_ARF_EVAL_2G_AUDIT_SHA256:return 2*GIB
 if not t.get('attempts') and t.get('kind') in ('fit','eval') and t.get('method') in ('knn','rbf_svm'):
  eligible,evidence=admission_evidence.eligible_knn_rbf_resource_profile(t,DEFINITIONS.get(t.get('key',''),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('resource_audit',{}).get('v2_sha256')==admission_evidence.KNN_RBF_V2_AUDIT_SHA256:
   return int(evidence['reservation_gib'])*GIB
 if not t.get('attempts') and t.get('kind')=='generate':
  eligible,evidence=admission_evidence.eligible_e4_arf_generation_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E4_ARF_GENERATION_2G_PROFILE_ID and evidence.get('reservation_gib')==2:return 2*GIB
  eligible,evidence=admission_evidence.eligible_e5_arf_generation_2gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E5_ARF_GENERATION_2G_PROFILE_ID and evidence.get('reservation_gib')==2:return 2*GIB
 if not t.get('attempts'):
  eligible,evidence=admission_evidence.eligible_e5_direct_rf_eval(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E5_RF_EVAL_4G_PROFILE_ID and evidence.get('reservation_gib')==4:return 4*GIB
  eligible,evidence=admission_evidence.eligible_e4_treatment_rf_eval(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E4_RF_EVAL_6G_PROFILE_ID and evidence.get('reservation_gib')==6:return 6*GIB
  eligible,evidence=admission_evidence.eligible_e4_treatment_rf_fit_5gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible and isinstance(evidence,dict) and evidence.get('profile_id')==admission_evidence.E4_RF_FIT_5G_PROFILE_ID and evidence.get('reservation_gib')==5:return 5*GIB
  eligible,_evidence=admission_evidence.eligible_2gib_resource_profile(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 2*GIB
  eligible,_evidence=admission_evidence.eligible_4gib(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return 4*GIB
  eligible,_evidence=admission_evidence.eligible_rf_resource_profiles(t,DEFINITIONS.get(t.get('key'),{}),R)
  if eligible:return int(_evidence['reservation_gib'])*GIB
 kind=str(t.get('kind','')).lower()
 if kind=='alias':return int(0.25*GIB)
 if kind in {'e4_cohort','e5_corruption','e4_treatment','e4_append'}:return GIB
 return (2 if worker_resource_class(t)=='light' else 10)*GIB
def promoted_reservation_bytes(t,observed_pss_bytes):
 reservation=worker_reservation_bytes(t)
 return 10*GIB if int(observed_pss_bytes)>reservation else reservation
def cpu_admission_slots(active_workers,total_cpus,idle_cores,reserve_cores=2):
 extra=max(0,int(idle_cores)-int(reserve_cores))
 ceiling=min(max(0,int(total_cpus)-int(reserve_cores)),int(active_workers)+extra)
 return max(0,ceiling-int(active_workers))
def worker_cpu_reservation_units(t):
 if _has_recorded_rf4_profile(t) or _has_recorded_et4_profile(t) or _has_recorded_e4_treatment_rf6_profile(t):
  profiles=[t.get('admission_resource_policy')]
  if t.get('attempts'):profiles.append(t['attempts'][-1].get('resource_profile'))
  for profile in profiles:
   if isinstance(profile,dict) and profile.get('execution_policy')==RF4_EXECUTION_POLICY and profile.get('resource_profile')==RF4_RESOURCE_PROFILE:
    try:
     units=int(profile.get('cpu_reservation_units',RF4_CPU_UNITS))
     return RF4_CPU_UNITS if units!=RF4_CPU_UNITS else units
    except (TypeError,ValueError):return RF4_CPU_UNITS
   if isinstance(profile,dict) and profile.get('execution_policy')==ET4_EXECUTION_POLICY and profile.get('resource_profile')==ET4_RESOURCE_PROFILE:
    try:
     units=int(profile.get('cpu_reservation_units',ET4_CPU_UNITS))
     return ET4_CPU_UNITS if units!=ET4_CPU_UNITS else units
    except (TypeError,ValueError):return ET4_CPU_UNITS
 return 1
def candidate_cpu_reservation_units(t):
 # Operational retries retain the execution profile already recorded on the task.
 if worker_cpu_reservation_units(t)==RF4_CPU_UNITS:return RF4_CPU_UNITS
 return RF4_CPU_UNITS if (_rf4_fit_eligible(t) is not None or _et4_fit_eligible(t) is not None or _e4_treatment_rf4_rep3_6g_eligible(t) is not None or _e4_treatment_rf4_6g_eligible(t) is not None) else 1
def cpu_admission_units(running,total_cpus,idle_cores,reserve_cores=2):
 occupied=sum(worker_cpu_reservation_units(t) for t in running)
 extra=max(0,int(idle_cores)-int(reserve_cores))
 capacity=min(max(0,int(total_cpus)-int(reserve_cores)),occupied+extra)
 return occupied,capacity
def memory_admission_ok(available_bytes,running_reservations,candidate_reservation,host_reserve=HOST_RESERVE,minimum_available=ADMISSION_FLOOR,margin=ADMISSION_REQUIRED_MARGIN_BYTES):
 if int(available_bytes)<int(minimum_available):return False
 unused=sum(max(0,int(res)-min(int(res),max(0,int(pss)))) for res,pss in running_reservations)
 return int(available_bytes)-int(host_reserve)-unused-int(candidate_reservation)>=int(margin)
def needs_resource_reclaim(available_bytes,growth_commitment,host_reserve=HOST_RESERVE,margin=int(ADAPTIVE_POLICY['commitment_growth_margin_gib']*GIB)):
 return int(available_bytes)<int(host_reserve)+int(growth_commitment)+int(margin)
def adaptive_task_eligible(t,revision=ADAPTIVE_REVISION):
 return bool(t.get('status')=='running' and t.get('adaptive_policy_revision')==revision and t.get('attempts') and not t.get('adaptive_emergency_term_epoch'))
def bracketed_worker_memory(running,rows_reader=None,available_reader=None,charge_reader=None):
 rows_reader=rows_reader or process_table
 available_reader=available_reader or memory_available
 charge_reader=charge_reader or charged_worker_memory
 rows_before=rows_reader()
 before=[max(0,int(charge_reader(t,rows_before) or 0)) for t in running]
 available=int(available_reader())
 rows_after=rows_reader()
 after=[max(0,int(charge_reader(t,rows_after) or 0)) for t in running]
 # Conservatively credit only memory observed both before and after the free-memory sample.
 credited=[min(a,b) for a,b in zip(before,after)]
 peak=[max(a,b) for a,b in zip(before,after)]
 return available,credited,peak

def _archive_overlap_freeze():
 try:
  value=json.loads((R/'manifests/freeze.json').read_text())
  return value if isinstance(value,dict) else None
 except (OSError,ValueError,TypeError):return None
def archive_fit_overlap_context():
 return archive_fit_admission.inspect_runtime(R,_archive_overlap_freeze())
def _bracketed_archive_helper(context):
 frozen=_archive_overlap_freeze()
 before=archive_fit_admission.inspect_runtime(R,frozen)
 if before.get('mode')!='active' or before.get('evidence',{}).get('context_sha256')!=context.get('evidence',{}).get('context_sha256'):return None
 pss_before=archive_fit_admission.helper_tree_pss_bytes(before)
 available=memory_available()
 pss_after=archive_fit_admission.helper_tree_pss_bytes(before)
 after=archive_fit_admission.inspect_runtime(R,frozen)
 if (after.get('mode')!='active' or after.get('evidence',{}).get('context_sha256')!=before.get('evidence',{}).get('context_sha256')
     or pss_before is None or pss_after is None):return None
 return {'available_bytes':available,'credited_pss_bytes':min(int(pss_before),int(pss_after)),
         'observed_peak_pss_bytes':max(int(pss_before),int(pss_after)),'context':after}
def _archive_overlap_evidence_identity(value):
 if value is None:return None
 helper=value.get('helper',{});inputs=value.get('task_input_proof',{})
 return (value.get('profile_id'),helper.get('context_sha256'),inputs.get('proof_sha256'))
def _archive_fit_launch_gate(db,t,idle_hint=None):
 context=archive_fit_overlap_context()
 if context.get('mode')=='blocked':return False
 # Keep legacy callers/admission behavior untouched unless an explicitly qualified
 # archive-overlap operation is active. The overlap gate must not inspect the DB
 # or worker resources in the default-disabled state.
 if context.get('mode')=='inactive':return None
 overlap=None
 if context.get('mode')=='active':
  all_tasks=load(db)
  overlap=archive_fit_admission.qualify_candidate(R,t,DEFINITIONS.get(t.get('key'),{}),all_tasks,_archive_overlap_freeze())
  if overlap is None:return False
 running=[x for x in load(db).values() if x.get('status')=='running']
 available,credits,peaks=bracketed_worker_memory(running)
 charges=[]
 for worker,credit,peak in zip(running,credits,peaks):
  reservation=worker_reservation_bytes(worker)
  if peak>reservation and not worker.get('adaptive_promoted_heavy'):return False
  charges.append((reservation,credit))
 if context.get('mode')=='active':
  helper=_bracketed_archive_helper(context)
  if helper is None or helper['observed_peak_pss_bytes']>archive_fit_admission.HELPER_RESERVATION_BYTES:return False
  available=min(available,helper['available_bytes'])
  charges.append((archive_fit_admission.HELPER_RESERVATION_BYTES,helper['credited_pss_bytes']))
 else:helper=None
 reservation=worker_reservation_bytes(t)
 if not memory_admission_ok(available,charges,reservation):return False
 idle_now=LAST_IDLE_CORES if idle_hint is None else float(idle_hint)
 occupied,capacity=cpu_admission_units(running,os.cpu_count() or 1,idle_now,ADAPTIVE_POLICY['cpu_reserve_cores'])
 helper_units=archive_fit_admission.HELPER_CPU_UNITS if helper is not None else 0
 candidate_units=candidate_cpu_reservation_units(t)
 if occupied+helper_units+candidate_units>capacity:return False
 if helper is None:return None
 return {'profile_id':ARCHIVE_FIT_OVERLAP_PROFILE,'task_input_proof':overlap,
  'helper':helper['context']['evidence'],'helper_reservation_bytes':archive_fit_admission.HELPER_RESERVATION_BYTES,
  'helper_pss_credit_bytes':helper['credited_pss_bytes'],'helper_observed_peak_pss_bytes':helper['observed_peak_pss_bytes'],
  'helper_cpu_reservation_units':archive_fit_admission.HELPER_CPU_UNITS,'available_bytes':available,
  'worker_reservation_bytes':reservation,'candidate_cpu_reservation_units':candidate_units}
def admission_candidate(db,running,ready,idle_cores,available_bytes=None,archive_context=None):
 """Return one dependency-ready candidate; admission reservation is not a process cap."""
 global LAST_MEMORY_ADMISSION
 frozen_doc=_archive_overlap_freeze()
 archive_context=archive_context or archive_fit_admission.inspect_runtime(R,frozen_doc)
 if archive_context.get('mode')=='blocked':
  LAST_MEMORY_ADMISSION={'observed_utc':now(),'admission_paused_reason':'archive overlap state is ambiguous or unqualified','archive_overlap_block_reason':archive_context.get('reason')}
  atomic(R/'memory_admission_observation.json',LAST_MEMORY_ADMISSION);return None
 total_cpus=os.cpu_count() or 1
 active=len(running)
 occupied_cpu_units,cpu_unit_capacity=cpu_admission_units(running,total_cpus,idle_cores,ADAPTIVE_POLICY['cpu_reserve_cores'])
 helper_units=archive_fit_admission.HELPER_CPU_UNITS if archive_context.get('mode')=='active' else 0
 occupied_cpu_units+=helper_units
 cpu_slots=max(0,cpu_unit_capacity-occupied_cpu_units)
 total_cap=cpu_unit_capacity
 available_sample,credited_pss,peak_pss=bracketed_worker_memory(running) if available_bytes is None else bracketed_worker_memory(running,available_reader=lambda:int(available_bytes))
 available=available_sample;charges=[];unused=0;promoted=[]
 for t,credit,peak in zip(running,credited_pss,peak_pss):
  res=worker_reservation_bytes(t)
  # Promotion uses the larger bracketed observation; commitment credit uses the smaller.
  if peak>res and not t.get('adaptive_promoted_heavy'):
   t['adaptive_promoted_heavy']=True;t['adaptive_promotion_reason']='observed process-tree PSS exceeded provisional reservation';t['adaptive_promoted_utc']=now();put(db,t);promoted.append(t)
   res=10*GIB
  charges.append({'key':t['key'],'credited_pss_bytes':credit,'observed_peak_pss_bytes':peak,'reservation_bytes':res,'promoted_this_observation':t in promoted})
  unused+=max(0,res-min(res,credit))
 helper_measurement=None
 if archive_context.get('mode')=='active':
  helper_measurement=_bracketed_archive_helper(archive_context)
  if helper_measurement is None or helper_measurement['observed_peak_pss_bytes']>archive_fit_admission.HELPER_RESERVATION_BYTES:
   LAST_MEMORY_ADMISSION={'observed_utc':now(),'admission_paused_reason':'archive helper identity/PSS bracket unavailable or above reservation'}
   atomic(R/'memory_admission_observation.json',LAST_MEMORY_ADMISSION);return None
  available=min(available,helper_measurement['available_bytes'])
  helper_unused=max(0,archive_fit_admission.HELPER_RESERVATION_BYTES-min(archive_fit_admission.HELPER_RESERVATION_BYTES,helper_measurement['credited_pss_bytes']))
  unused+=helper_unused
  charges.append({'key':'__verified_archive_helper__','credited_pss_bytes':helper_measurement['credited_pss_bytes'],
   'observed_peak_pss_bytes':helper_measurement['observed_peak_pss_bytes'],'reservation_bytes':archive_fit_admission.HELPER_RESERVATION_BYTES,
   'promoted_this_observation':False})
 observation={'observed_utc':now(),'available_bytes':available,'running_workers':charges,'per_worker_hard_limit_bytes':10*GIB,'OS_Harbor_reserve_bytes':HOST_RESERVE,'admission_floor_bytes':ADMISSION_FLOOR,'admission_safety_buffer_bytes':ADMISSION_SAFETY_BUFFER_BYTES,'admission_required_margin_bytes':ADMISSION_REQUIRED_MARGIN_BYTES,'idle_cores':idle_cores,'cpu_total_cap':total_cap,'additional_cpu_slots':cpu_slots,'occupied_cpu_reservation_units':occupied_cpu_units,'cpu_admission_capacity_units':cpu_unit_capacity,'archive_helper_cpu_reservation_units':helper_units,
  'archive_helper_context':archive_context.get('evidence') if archive_context.get('mode')=='active' else None,
  'archive_helper_pss_credit_bytes':helper_measurement['credited_pss_bytes'] if helper_measurement else 0,
  'adaptive_revision':ADAPTIVE_REVISION}
 LAST_MEMORY_ADMISSION=observation
 if promoted:
  observation['admission_paused_reason']='light worker exceeded provisional reservation; promoted to 10 GiB and remeasured before further admissions'
  atomic(R/'memory_admission_observation.json',observation);return None
 growth_commitment=sum(max(0,x['reservation_bytes']-min(x['reservation_bytes'],x['credited_pss_bytes'])) for x in charges)
 if time.time()<EMERGENCY_BACKOFF_UNTIL or available<ADMISSION_FLOOR or cpu_slots<=0:return None
 heavy_lane=any(worker_resource_class(t)=='heavy' for t in running)
 ordered_ready=fit_limited_ready(running,order_ready_for_admission(running,ready))
 native_overlap_proofs={}
 if archive_context.get('mode')=='active':
  all_tasks=load(db)
  for possible in ordered_ready:
   proof=archive_fit_admission.qualify_candidate(R,possible,DEFINITIONS.get(possible.get('key'),{}),all_tasks,frozen_doc)
   if proof is not None:native_overlap_proofs[possible['key']]=proof
  ordered_ready=[x for x in ordered_ready if x.get('key') in native_overlap_proofs]
  observation['archive_overlap_eligible_ready_count']=len(ordered_ready)
 arf_lane_active=any(_is_e45_arf_fit(t) for t in running)
 arf_lane_waiting=False
 arf_candidate=None
 if not arf_lane_active:
  arf_candidate=_eligible_waiting_arf6_fit(ordered_ready)
  if arf_candidate is not None:
   arf_reservation=worker_reservation_bytes(arf_candidate)
   if memory_admission_ok(available,[(x['reservation_bytes'],x['credited_pss_bytes']) for x in charges],arf_reservation):
    ordered_ready=[arf_candidate]+[x for x in ordered_ready if x.get('key')!=arf_candidate.get('key')]
   elif running:
    # Preserve a single ready ARF fit lane while currently active work releases
    # reservations naturally. Do not stop existing workers or block non-fit sinks.
    arf_lane_waiting=True
 heavy_fit_waiting=(not heavy_lane and any(t.get('kind')=='fit' and worker_resource_class(t)=='heavy' and not (arf_candidate is not None and t.get('key')==arf_candidate.get('key')) for t in ordered_ready))
 e6_lane_waiting=_e6_v2_lane_waiting(running,ordered_ready,available,charges)
 observation['e6_v2_ready_lane_waiting']=e6_lane_waiting
 for t in ordered_ready:
  reservation=worker_reservation_bytes(t)
  cpu_units=candidate_cpu_reservation_units(t)
  if occupied_cpu_units+cpu_units>cpu_unit_capacity:continue
  if (arf_lane_waiting or e6_lane_waiting) and t.get('kind')=='fit':
   continue
  if light_fit_blocked(t,heavy_fit_waiting):
   continue
  if not memory_admission_ok(available,[(x['reservation_bytes'],x['credited_pss_bytes']) for x in charges],reservation):continue
  projected=HOST_RESERVE+unused+reservation
  observation.update({'selected_key':t['key'],'selected_class':worker_resource_class(t),'selected_reservation_bytes':reservation,'selected_cpu_reservation_units':cpu_units,'projected_headroom_bytes':available-projected})
  if archive_context.get('mode')=='active':
   t['_archive_native_fit_overlap_proof']=native_overlap_proofs[t['key']]
   observation['selected_native_input_proof_sha256']=native_overlap_proofs[t['key']]['proof_sha256']
  LAST_MEMORY_ADMISSION=observation
  atomic(R/'memory_admission_observation.json',observation)
  return t
 atomic(R/'memory_admission_observation.json',observation)
 return None
def charged_worker_memory(t,rows):
 if not alive(t.get('pid'),t.get('process_start_ticks')) or t.get('forced_reason'):return 0
 rss,ids=tree_rss(t['pid'],rows);pss=0
 try:
  for pid in ids:
   data=pathlib.Path('/proc',str(pid),'smaps_rollup').read_text().splitlines()
   pss+=int(next(x.split()[1] for x in data if x.startswith('Pss:')))*1024
 except (OSError,StopIteration,ValueError):return 0
 return min(rss,pss,10*GIB)
def cpu_idle_cores():
 global CPU_PREVIOUS,LAST_IDLE_CORES
 vals=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
 point=(sum(vals),vals[3])
 if CPU_PREVIOUS is None:LAST_IDLE_CORES=0.0
 else:
  total=point[0]-CPU_PREVIOUS[0];idle=point[1]-CPU_PREVIOUS[1]
  if total>0:LAST_IDLE_CORES=(os.cpu_count() or 1)*idle/total
  else:LAST_IDLE_CORES=0.0
 CPU_PREVIOUS=point
 return LAST_IDLE_CORES
STORAGE_DRAIN_POLICY_ID='nonfit-e4e5-eval-only-20261028-v1'
STORAGE_DRAIN_OUTPUT_RESERVE_BYTES=2*GIB
# Operational disk admission amendment; separate from scientific worker limits
# and from the full archive verification performed by finalization.
WORKING_STORAGE_POLICY={
 'policy_id':'working-reserve-6gib-one-fit-v1',
 'working_reserve_bytes':6*GIB,
 'maximum_restore_bytes':10*GIB,
 'maximum_single_restore_asset_bytes':GIB,
 'per_active_or_new_task_output_reserve_bytes':STORAGE_DRAIN_OUTPUT_RESERVE_BYTES,
 'maximum_concurrent_fit_tasks':1,
 'restore_index_rel':'operations/terminal_result_retention_v2_20261030/guardian/retention_index.json',
 'restore_index_schema':'lamost-terminal-result-retention-index/2',
 'full_archive_verification':'finalization_only'
}
def retention_budget_matches_policy(budget,policy):
 if not isinstance(budget,dict) or not isinstance(policy,dict):return False
 expected={'index_sha256':policy.get('retention_index_sha256'),
           'row_count':policy.get('retention_row_count'),
           'restore_bytes':policy.get('retention_restore_bytes'),
           'largest_asset_bytes':policy.get('largest_restore_asset_bytes'),
           'restore_required':policy.get('retention_restore_required')}
 return (all(expected[k] is not None for k in expected)
         and budget==expected
         and expected['restore_required'] is True)
def _storage_expected_campaign(frozen):
 if not isinstance(frozen,dict) or frozen.get('storage_admission_policy')!=WORKING_STORAGE_POLICY:return None
 amendment=frozen.get('storage_admission_amendment')
 if not isinstance(amendment,dict) or amendment.get('schema')!='lamost-controller-operational-source-amendment/1':return None
 current=sha(pathlib.Path(__file__))
 if amendment.get('candidate_controller_sha256')!=current:return None
 rel=amendment.get('policy_path');digest=amendment.get('policy_sha256')
 if not isinstance(rel,str) or not isinstance(digest,str) or len(digest)!=64:return None
 member=pathlib.Path(rel)
 if member.is_absolute() or '..' in member.parts:return None
 project=R.parent;path=project/member
 try:
  if path.is_symlink() or not path.is_file() or project.resolve() not in path.resolve().parents:return None
  raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=digest:return None
  policy=json.loads(raw)
 except (OSError,ValueError,TypeError):return None
 if (not isinstance(policy,dict) or policy.get('schema')!='lamost-working-storage-admission-policy/1'
     or policy.get('controller_candidate_sha256')!=current
     or policy.get('freeze_binding_value')!=WORKING_STORAGE_POLICY
     or policy.get('policy_id')!=WORKING_STORAGE_POLICY['policy_id']):return None
 if policy.get('retention_index_path')!=WORKING_STORAGE_POLICY['restore_index_rel'] or policy.get('retention_index_schema')!=WORKING_STORAGE_POLICY['restore_index_schema']:return None
 if policy.get('maximum_concurrent_fit_tasks')!=WORKING_STORAGE_POLICY['maximum_concurrent_fit_tasks'] or policy.get('per_active_or_new_task_output_reserve_bytes')!=WORKING_STORAGE_POLICY['per_active_or_new_task_output_reserve_bytes']:return None
 return policy
def retention_restore_budget(index_path):
 """Validate the bounded restore index and return conservative reserve inputs."""
 p=pathlib.Path(index_path)
 try:
  if p.is_symlink() or not p.is_file():return None
  st=p.stat()
  if st.st_size<=0 or st.st_size>32*1024*1024:return None
  raw=p.read_bytes()
  digest=hashlib.sha256(raw).hexdigest()
  doc=json.loads(raw)
 except (OSError,ValueError,TypeError):
  return None
 if not isinstance(doc,dict) or doc.get('schema')!=WORKING_STORAGE_POLICY['restore_index_schema']:return None
 restore=doc.get('restore_required');rows=doc.get('retired')
 if not isinstance(restore,bool) or not isinstance(rows,list) or (restore and not rows):return None
 total=0;largest=0;seen_paths=set();seen_sources=set()
 root_prefix='runtime_20261025/artifacts/'
 for row in rows:
  if not isinstance(row,dict):return None
  key=row.get('task_key');source=row.get('source_path')
  if not isinstance(key,str) or not isinstance(source,str):return None
  parts=key.split('/')
  if len(parts)<5 or parts[0] not in ('e3','e4','e5','e6') or any(x in ('','.','..') for x in parts):return None
  if source!=root_prefix+key+'/test_outcomes.npz':return None
  if row.get('task_family')!=int(parts[0][1:]):return None
  if row.get('asset') is not None and row.get('asset')!=row.get('asset_name',row.get('asset')):return None
  if source in seen_sources:return None
  seen_sources.add(source)
  size=row.get('source_bytes');sh=row.get('source_sha256')
  if not isinstance(size,int) or isinstance(size,bool) or size<=0:return None
  if not isinstance(sh,str) or len(sh)!=64 or any(c not in '0123456789abcdef' for c in sh):return None
  assetsize=row.get('asset_bytes');assetsha=row.get('asset_sha256');assetname=row.get('asset_name',row.get('asset'))
  if not isinstance(assetsize,int) or isinstance(assetsize,bool) or assetsize<=0 or assetsize>WORKING_STORAGE_POLICY['maximum_single_restore_asset_bytes']:return None
  if not isinstance(assetsha,str) or len(assetsha)!=64 or any(c not in '0123456789abcdef' for c in assetsha):return None
  if not isinstance(assetname,str) or not assetname or '/' in assetname or chr(92) in assetname or assetname in ('.','..'):return None
  native=row.get('native_paths');unlinked=row.get('unlinked_paths')
  if not isinstance(native,list) or not isinstance(unlinked,list) or not native:return None
  link_count=row.get('link_count',row.get('native_nlink'))
  if not isinstance(link_count,int) or isinstance(link_count,bool) or link_count!=len(native):return None
  if source not in native or set(native)!=set(unlinked) or len(unlinked)!=len(set(unlinked)) or len(native)!=len(set(native)):return None
  if row.get('retirement_kind')!='complete_inode_group' or row.get('fresh_native_inventory_verified') is not True:return None
  for evidence_sha_field in ('asset_remote_evidence_sha256','member_record_evidence_sha256','manifest_sha256','physical_inventory_sha256','plan_sha256'):
   evidence_sha=row.get(evidence_sha_field)
   if not isinstance(evidence_sha,str) or len(evidence_sha)!=64 or any(c not in '0123456789abcdef' for c in evidence_sha):return None
  if not isinstance(row.get('asset_remote_evidence_path'),str) or not row['asset_remote_evidence_path']:return None
  if not isinstance(row.get('member_record_evidence_path'),str) or not row['member_record_evidence_path']:return None
  crc=row.get('archive_crc32');member=row.get('archive_member')
  if not isinstance(crc,str) or len(crc)!=8 or any(c not in '0123456789abcdef' for c in crc):return None
  if not isinstance(member,str) or not member.startswith(root_prefix) or '..' in member.split('/'):return None
  expected_alias_prefix=root_prefix+key+'/attempts/'
  for alias in native:
   if not isinstance(alias,str) or alias in seen_paths:return None
   if alias!=source and (not alias.startswith(expected_alias_prefix) or not alias.endswith('/test_outcomes.npz')):return None
   if '..' in alias.split('/') or chr(92) in alias:return None
   seen_paths.add(alias)
  total+=size;largest=max(largest,assetsize)
  if total>WORKING_STORAGE_POLICY['maximum_restore_bytes']:return None
 if not restore:total=largest=0
 return {'index_sha256':digest,'restore_required':restore,'restore_bytes':total,'largest_asset_bytes':largest,'row_count':len(rows)}
def storage_required_bytes(restore_bytes,largest_asset_bytes,active_count):
 if any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in (restore_bytes,largest_asset_bytes,active_count)):return None
 if restore_bytes>WORKING_STORAGE_POLICY['maximum_restore_bytes'] or largest_asset_bytes>WORKING_STORAGE_POLICY['maximum_single_restore_asset_bytes']:return None
 return (WORKING_STORAGE_POLICY['working_reserve_bytes']+restore_bytes+largest_asset_bytes+
         WORKING_STORAGE_POLICY['per_active_or_new_task_output_reserve_bytes']*(active_count+1))
def fit_limited_ready(running,ready):
 """Enforce one global fit lane while retaining ready evaluations and aliases."""
 fit_limit=WORKING_STORAGE_POLICY['maximum_concurrent_fit_tasks']
 running_fits=sum(1 for t in running if isinstance(t,dict) and t.get('kind')=='fit')
 if running_fits>=fit_limit:
  return [t for t in ready if not (isinstance(t,dict) and t.get('kind')=='fit')]
 return list(ready)
_STORAGE_DRAIN_HASH_CACHE={}
_STORAGE_DRAIN_HASH_CACHE_MAX=256

def _storage_drain_artifact_file(runtime,key,filename):
 # Resolve only canonical project-owned artifact paths and reject symlinks at
 # every component. The task's artifact_dir is checked by the caller.
 if not isinstance(key,str) or not key or key.startswith('/') or '\\' in key:return None
 if filename not in {'pipeline.joblib','fit_result.json','validation.json','evaluation.json'}:return None
 parts=key.split('/')
 if any(x in ('','.','..') for x in parts):return None
 root=pathlib.Path(runtime)/'artifacts'
 try:
  root_st=root.lstat()
  if stat.S_ISLNK(root_st.st_mode) or not stat.S_ISDIR(root_st.st_mode):return None
  cur=root
  for part in parts:
   if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in part):return None
   cur=cur/part
   st=cur.lstat()
   if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):return None
  p=cur/filename;st=p.lstat()
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size<=0:return None
  resolved=p.resolve(strict=True)
  if not resolved.is_relative_to(root.resolve(strict=True)):return None
  return p,st
 except (OSError,ValueError,RuntimeError):return None

def _storage_drain_small_json(path,maximum=4*1024*1024):
 try:
  st=path.lstat()
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size<=0 or st.st_size>maximum:return None
  with path.open('r',encoding='utf-8') as f:
   value=json.load(f)
  return value if isinstance(value,dict) else None
 except (OSError,ValueError,TypeError):return None

def _storage_drain_stream_sha256(path,observed_stat):
 # Hash one selected physical artifact in bounded chunks; cache by inode and
 # full stat identity so repeat scheduler polls do not reread the same model.
 key=str(path); sig=(observed_stat.st_dev,observed_stat.st_ino,observed_stat.st_size,observed_stat.st_mtime_ns,observed_stat.st_ctime_ns)
 cached=_STORAGE_DRAIN_HASH_CACHE.get(key)
 if cached is not None and cached[0]==sig:return cached[1]
 h=hashlib.sha256()
 try:
  fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
  with os.fdopen(fd,'rb',closefd=True) as f:
   st=os.fstat(f.fileno())
   current=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
   if current!=sig or not stat.S_ISREG(st.st_mode):return None
   while True:
    block=f.read(4*1024*1024)
    if not block:break
    h.update(block)
  after=path.lstat()
  if stat.S_ISLNK(after.st_mode) or (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=sig:return None
 except OSError:return None
 digest=h.hexdigest()
 if len(_STORAGE_DRAIN_HASH_CACHE)>=_STORAGE_DRAIN_HASH_CACHE_MAX:_STORAGE_DRAIN_HASH_CACHE.clear()
 _STORAGE_DRAIN_HASH_CACHE[key]=(sig,digest)
 return digest

def _storage_drain_valid_hash(value):
 return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def _storage_drain_task_evidence(task,tasks,runtime,require_ready=True):
 # Only frozen E4/E5 RF/ExtraTrees evaluations with exactly one validated fit
 # dependency, or an E5 clean alias to its same-repetition E4 control eval.
 status=task.get('status')
 if require_ready and status not in ('planned','waiting_for_dependency'):return None
 if require_ready and task.get('attempts'):return None
 if not require_ready and status!='running':return None
 exp=task.get('experiment');rep=task.get('rep')
 try:exp=int(exp);rep=int(rep)
 except (TypeError,ValueError):return None
 if rep not in (1,2,3):return None
 method=task.get('method')
 if method not in ('random_forest','extra_trees'):return None
 key=task.get('key')
 if task.get('artifact_dir')!=str(pathlib.Path(runtime)/'artifacts'/str(key)):return None
 if task.get('kind')=='eval':
  route=task.get('route');condition=task.get('condition')
  if exp==4 and route not in ('direct','treatment'):return None
  if exp==5 and route not in ('direct','synthetic'):return None
  if exp not in (4,5) or not isinstance(condition,str) or not condition:return None
  if key!=f'e{exp}/rep_{rep}/eval/{route}/{method}/{condition}':return None
  fit_key=task.get('fit_key');deps=task.get('dependencies',[])
  if not isinstance(fit_key,str) or deps!=[fit_key]:return None
  fit=tasks.get(fit_key)
  if not isinstance(fit,dict) or fit.get('key')!=fit_key:return None
  if (fit.get('kind')!='fit' or fit.get('experiment')!=exp or fit.get('rep')!=rep
      or fit.get('method')!=method or fit.get('route')!=route or fit.get('condition')!=condition
      or fit.get('status')!='validated_terminal' or fit.get('outcome')!='successful'
      or fit.get('validation_state')!='validated'):return None
  if fit.get('artifact_dir')!=str(pathlib.Path(runtime)/'artifacts'/fit_key):return None
  result=fit.get('result')
  if not isinstance(result,dict):return None
  expected=result.get('artifact_sha256');inner=result.get('result')
  if not isinstance(inner,dict) or not _storage_drain_valid_hash(expected) or inner.get('pipeline_sha256')!=expected:return None
  fit_result_file=_storage_drain_artifact_file(runtime,fit_key,'fit_result.json')
  validation_file=_storage_drain_artifact_file(runtime,fit_key,'validation.json')
  model_file=_storage_drain_artifact_file(runtime,fit_key,'pipeline.joblib')
  if not fit_result_file or not validation_file or not model_file:return None
  fr=_storage_drain_small_json(fit_result_file[0]);val=_storage_drain_small_json(validation_file[0])
  if not isinstance(fr,dict) or fr.get('artifact_sha256')!=expected:return None
  fr_inner=fr.get('result')
  if not isinstance(fr_inner,dict) or fr_inner.get('pipeline_sha256')!=expected:return None
  if not isinstance(val,dict) or val.get('status')!='validated' or val.get('task_key')!=fit_key:return None
  if not isinstance(val.get('files'),dict) or val['files'].get('pipeline.joblib')!=expected:return None
  actual=_storage_drain_stream_sha256(model_file[0],model_file[1])
  if actual!=expected:return None
  return {'storage_drain_policy_id':STORAGE_DRAIN_POLICY_ID,'drain_task_key':key,'drain_kind':'evaluation',
          'fit_key':fit_key,'pipeline_sha256':expected,'fit_validation_manifest_sha256':sha(validation_file[0]),
          'physical_pipeline_bytes':model_file[1].st_size,'no_model_fit_or_serialization':True}
 if task.get('kind')=='alias':
  if exp!=5 or task.get('route')!='direct' or task.get('condition')!='clean':return None
  if key!=f'e5/rep_{rep}/eval/direct/{method}/clean':return None
  source_key=f'e4/rep_{rep}/eval/direct/{method}/control'
  if task.get('source_key')!=source_key or task.get('dependencies')!=[source_key]:return None
  source=tasks.get(source_key)
  if not isinstance(source,dict) or (source.get('kind') not in ('eval','alias') or source.get('experiment')!=4
      or source.get('rep')!=rep or source.get('method')!=method or source.get('route')!='direct'
      or source.get('condition')!='control' or source.get('status')!='validated_terminal'
      or source.get('outcome')!='successful' or source.get('validation_state')!='validated'):return None
  src_file=_storage_drain_artifact_file(runtime,source_key,'evaluation.json')
  src_val_file=_storage_drain_artifact_file(runtime,source_key,'validation.json')
  if not src_file or not src_val_file:return None
  val=_storage_drain_small_json(src_val_file[0])
  if not isinstance(val,dict) or val.get('status')!='validated' or val.get('task_key')!=source_key:return None
  if not isinstance(val.get('files'),dict):return None
  expected=val['files'].get('evaluation.json')
  if not _storage_drain_valid_hash(expected) or sha(src_file[0])!=expected:return None
  return {'storage_drain_policy_id':STORAGE_DRAIN_POLICY_ID,'drain_task_key':key,'drain_kind':'clean_evaluation_alias',
          'source_evaluation_key':source_key,'source_evaluation_sha256':expected,
          'source_validation_manifest_sha256':sha(src_val_file[0]),'no_model_fit_or_serialization':True}
 return None

def storage_drain_candidate(tasks,ready,running,free_bytes,runtime,archive_mode='inactive',admission_hold=False,frozen=None):
 # Only bounded E4/E5 evaluation sinks may bypass ordinary fit admission.
 # Their disk floor still includes every pending verified restore and output
 # reservation; no archive overlap or operator hold may be bypassed.
 if admission_hold or archive_mode!='inactive':return None
 try:free=int(free_bytes)
 except (TypeError,ValueError):return None
 expected_campaign=_storage_expected_campaign(frozen)
 index_path=pathlib.Path(runtime).resolve().parent/WORKING_STORAGE_POLICY['restore_index_rel']
 budget=retention_restore_budget(index_path)
 if expected_campaign is None or not retention_budget_matches_policy(budget,expected_campaign):return None
 active_evidence=[]
 for t in running:
  evidence=_storage_drain_task_evidence(t,tasks,runtime,require_ready=False)
  if evidence is None:return None
  active_evidence.append(evidence)
 required=storage_required_bytes(budget['restore_bytes'],budget['largest_asset_bytes'],len(active_evidence))
 if required is None or free<required:return None
 # Preserve the established ready ordering and inspect candidates one at a
 # time. Hash at most the selected candidate's model per scheduler pass.
 for selected in order_ready_for_admission(running,ready):
  proof=_storage_drain_task_evidence(selected,tasks,runtime,require_ready=True)
  if proof is None:continue
  proof=dict(proof)
  proof.update({'free_bytes_at_admission_check':free,'hard_free_floor_bytes':WORKING_STORAGE_POLICY['working_reserve_bytes']+budget['restore_bytes']+budget['largest_asset_bytes'],
                'reserved_output_bytes_per_active_or_new_task':STORAGE_DRAIN_OUTPUT_RESERVE_BYTES,
                'active_drain_task_count':len(active_evidence),
                'reserved_output_total_bytes':STORAGE_DRAIN_OUTPUT_RESERVE_BYTES*(len(active_evidence)+1),
                'required_free_bytes':required,'retention_index_sha256':budget['index_sha256'],'restore_bytes_reserved':budget['restore_bytes'],'largest_restore_asset_bytes_reserved':budget['largest_asset_bytes'],'archive_overlap_mode':'inactive','operator_admission_hold_absent':True,
                'normal_future_space_forecast_gate_passed':False})
  return selected,proof
 return None

def storage_allow(running=(),frozen=None):
 free=shutil.disk_usage(R).free
 if frozen is None:
  try:frozen=json.loads((R/'manifests/freeze.json').read_text())
  except (OSError,ValueError,TypeError):frozen=None
 expected_campaign=_storage_expected_campaign(frozen)
 index_path=R.parent/WORKING_STORAGE_POLICY['restore_index_rel']
 budget=retention_restore_budget(index_path)
 campaign_match=retention_budget_matches_policy(budget,expected_campaign)
 active_count=sum(1 for t in running if isinstance(t,dict) and t.get('status')=='running')
 required=None if budget is None or not campaign_match else storage_required_bytes(budget['restore_bytes'],budget['largest_asset_bytes'],active_count)
 allowed=bool(required is not None and free>=required)
 atomic(R/'storage_observation.json',{'observed_utc':now(),'policy_id':WORKING_STORAGE_POLICY['policy_id'],
  'free_bytes':free,'working_reserve_bytes':WORKING_STORAGE_POLICY['working_reserve_bytes'],
  'retention_index_path':str(index_path),'retention_index_sha256':budget.get('index_sha256') if budget else None,
  'restore_required':budget.get('restore_required') if budget else None,'retention_index_matches_approved_campaign':campaign_match,
  'restore_bytes_reserved':budget.get('restore_bytes') if budget else None,
  'largest_restore_asset_bytes_reserved':budget.get('largest_asset_bytes') if budget else None,
  'active_running_task_count':active_count,'per_active_or_new_task_output_reserve_bytes':WORKING_STORAGE_POLICY['per_active_or_new_task_output_reserve_bytes'],
  'required_free_bytes':required,'admission_allowed':allowed,
  'full_archive_verification':'finalization_only','no_unique_artifacts_deleted':True})
 return allowed,free

def stop_handler(sig,frame):
 global STOP;STOP=True
def admission_hold_active():
 return (R/'ADMISSION_HOLD.json').exists()

def run():
 global STOP
 lock=lock_project();db=connect();tasks=initialize(db);frozen=freeze();REAPER_ENABLED=archive_fit_admission.worker_reaper_enabled(frozen,sha(R/'source/archive_fit_admission.py'));tasks=apply_e6_v2_execution_overlay(db,tasks,frozen)
 atomic(R/'owner.json',{'pid':os.getpid(),'process_start_ticks':start_ticks(os.getpid()),'started_utc':now(),'instance_id':pathlib.Path('/sys/devices/virtual/dmi/id/board_asset_tag').read_text().strip(),'code_sha256':sha(pathlib.Path(__file__))})
 signal.signal(signal.SIGTERM,stop_handler);signal.signal(signal.SIGINT,stop_handler)
 event(db,'controller_started',{'pid':os.getpid(),'tasks':len(tasks),'plan_sha256':frozen['plan_sha256']})
 last_export=last_report=last_source=0
 while not STOP:
  # Refresh the registry snapshot before reaping/checking workers. The storage
  # drain path may admit a worker through a local snapshot; the next loop must
  # observe it for liveness checks and progress exports.
  tasks=load(db)
  if REAPER_ENABLED:archive_fit_admission.reap_recorded_zombies(tasks,R,os.getpid())
  check_running(db,tasks)
  if time.monotonic()-last_source>60:
   if source_hashes()!=frozen['source_sha256']:
    atomic(R/'CODE_CHANGE_HOLD.json',{'observed_utc':now(),'reason':'execution source changed without reviewed freeze amendment'});event(db,'source_change_hold',{});STOP=True;break
   last_source=time.monotonic()
  ready=ready_tasks(db,tasks);running=[t for t in tasks.values() if t['status']=='running']
  guard=emergency_interrupt_one(db,tasks)
  storage,free=storage_allow(running,frozen)
  idle=cpu_idle_cores()
  # Re-sample process PSS and MemAvailable after every launch; never trust a batch reservation.
  if storage and archive_fit_overlap_context().get('mode')!='blocked':
   for _ in range(max(0,(os.cpu_count() or 1)-int(ADAPTIVE_POLICY['cpu_reserve_cores']))):
    if archive_fit_overlap_context().get('mode')=='blocked':break
    tasks=load(db);running=[t for t in tasks.values() if t['status']=='running']
    if isinstance(guard,dict) and guard.get('promoted_keys'):break
    tasks=load(db);running=[t for t in tasks.values() if t['status']=='running']
    candidate=admission_candidate(db,running,ready_tasks(db,tasks),idle)
    if candidate is None:break
    if archive_fit_overlap_context().get('mode')=='blocked':break
    storage,free=storage_allow(running,frozen)
    if not storage:break
    admitted_cpu_units=candidate_cpu_reservation_units(candidate)
    if not admit(db,candidate,idle):break
    idle=max(0.0,idle-float(admitted_cpu_units))
    tasks=load(db);guard=emergency_interrupt_one(db,tasks)
  elif ready and not storage:
   storage_observation={}
   try:storage_observation=json.loads((R/'storage_observation.json').read_text())
   except (OSError,ValueError,TypeError):pass
   atomic(R/'STORAGE_HOLD.json',{'observed_utc':now(),'free_bytes':free,
    'minimum_free_bytes':storage_observation.get('required_free_bytes'),
    'policy_id':storage_observation.get('policy_id'),
    'reason':'working reserve or verified-retention restore budget unavailable; unique artifacts preserved'})
   # Drain only already-fitted E4/E5 RF/ET evaluation sinks and E5 clean aliases.
   # This path never changes the ordinary fit/generation forecast admission.
   if not admission_hold_active():
    drain_archive=archive_fit_overlap_context()
    if drain_archive.get('mode')=='inactive':
     fresh_tasks=load(db);fresh_ready=ready_tasks(db,fresh_tasks)
     fresh_running=[x for x in fresh_tasks.values() if x.get('status')=='running']
     drain=storage_drain_candidate(fresh_tasks,fresh_ready,fresh_running,shutil.disk_usage(R).free,R,
                                   drain_archive.get('mode'),admission_hold_active(),frozen=frozen)
     if drain is not None:
      drain_task,drain_proof=drain
      candidate=admission_candidate(db,fresh_running,[drain_task],idle,archive_context=drain_archive)
      if candidate is not None:
       # Recheck disk, dependencies, physical input, archive mode and operator hold
       # immediately before launch; actual RAM/CPU checks remain in admission_candidate.
       latest=load(db);latest_ready=ready_tasks(db,latest)
       latest_running=[x for x in latest.values() if x.get('status')=='running']
       latest_archive=archive_fit_overlap_context();latest_free=shutil.disk_usage(R).free
       latest_drain=storage_drain_candidate(latest,latest_ready,latest_running,latest_free,R,
                                            latest_archive.get('mode'),admission_hold_active(),frozen=frozen)
       if latest_drain is not None and latest_drain[0].get('key')==candidate.get('key'):
        admit(db,candidate,idle,storage_drain_evidence=latest_drain[1])
  if time.monotonic()-last_export>10:
   export(db,tasks);human_checkpoint(tasks);maybe_report(db,tasks);last_export=time.monotonic()
  remaining=[t for t in tasks.values() if t['status']!='validated_terminal']
  if not remaining:
   export(db,tasks);atomic(R/'EXECUTION_TERMINAL.json',{'observed_utc':now(),'tasks':len(tasks),'counts':dict(collections.Counter(t.get('outcome') for t in tasks.values()))})
   event(db,'execution_terminal',{'tasks':len(tasks)})
   if (R/'source/finalize_project.py').exists():
    proc=subprocess.run(['tmux','new-session','-d','-s','lamost-finalize','/bin/bash',str(R/'run_finalizer.sh')],capture_output=True,text=True)
    if proc.returncode:atomic(R/'PACKAGING_PENDING.json',{'observed_utc':now(),'reason':proc.stderr})
   else:atomic(R/'PACKAGING_PENDING.json',{'observed_utc':now(),'reason':'finalizer implementation not yet installed'})
   break
  if time.monotonic()-last_report>300:
   event(db,'progress',{'remaining':len(remaining),'active':len([t for t in tasks.values() if t['status']=='running']),'ready':len(ready),'free_disk_bytes':free,'available_memory_bytes':memory_available()});last_report=time.monotonic()
  time.sleep(2)
 export(db,tasks);event(db,'controller_stopped',{'stop_signal':STOP})
def watchdog():
 if not (R/'READY_TO_START.json').exists():return
 try:owner=json.loads((R/'owner.json').read_text())
 except Exception:owner={}
 if alive(owner.get('pid'),owner.get('process_start_ticks'),'controller.py'):return
 if (R/'PROJECT_COMPLETE.json').exists() or (R/'EC2_COMPLETE_DELIVERY_PENDING.json').exists():return
 if (R/'EXECUTION_TERMINAL.json').exists():
  if (R/'source/finalize_project.py').exists():subprocess.run(['tmux','new-session','-d','-s','lamost-finalize','/bin/bash',str(R/'run_finalizer.sh')],capture_output=True)
  return
 if (R/'CODE_CHANGE_HOLD.json').exists() or (R/'WATCHDOG_START_HOLD.json').exists():return
 hp=R/'watchdog_history.json'
 try:history=json.loads(hp.read_text())
 except Exception:history=[]
 recent=[x for x in history if time.time()-x['epoch']<3600]
 if len(recent)>=3:
  atomic(R/'WATCHDOG_START_HOLD.json',{'observed_utc':now(),'reason':'three verified controller restart attempts in one hour; review deterministic startup failure'})
  return
 proc=subprocess.run(['tmux','new-session','-d','-s','lamost-project','/bin/bash',str(R/'run_controller.sh')],capture_output=True,text=True)
 history.append({'epoch':time.time(),'observed_utc':now(),'returncode':proc.returncode,'reason':'verified prior controller absent'})
 atomic(hp,history[-30:])
def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','run','status','watchdog']);a=p.parse_args()
 if a.command=='run':run()
 elif a.command=='watchdog':watchdog()
 elif a.command=='init':
  lock=lock_project();db=connect();tasks=initialize(db);frozen=freeze();tasks=apply_e6_v2_execution_overlay(db,tasks,frozen);export(db,tasks);print(json.dumps({'tasks':len(tasks),'scientific_cases':dict(collections.Counter(t['experiment'] for t in tasks.values() if t.get('scientific_case')))}))
 else:
  print((R/'status.json').read_text() if (R/'status.json').exists() else '{"status":"not_initialized"}')
if __name__=='__main__':main()
