#!/usr/bin/env python3
"""Durable internal review gate for the final scientific report and package inputs."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,sys,shutil,tempfile,importlib.util
from pathlib import Path

ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023')
RUNTIME=ROOT/'runtime_20261025'
REPORTS=RUNTIME/'reports'
AUDIT_DIR=RUNTIME/'review_audit'
READY=RUNTIME/'REPORT_READY_FOR_AUDIT.json'
RECEIPT=RUNTIME/'REPORT_AUDIT_RECEIPT.json'
INVALIDATED=RUNTIME/'REPORT_AUDIT_INVALIDATED.json'
REQUIRED_CSVS=('all_task_ledger.csv','planned_case_ledger.csv','experiment_outcome_coverage.csv','per_repetition_metrics.csv','per_class_metrics.csv','matched_paired_differences.csv','matched_paired_summary.csv')
REQUIRED_FROZEN=('project/benchmark/protocol_source.txt','project/benchmark/dependencies.freeze.txt','project/benchmark/results/master_run_config.json','project/benchmark/results/e1_report_validated_no_bootstrap.json','project/benchmark/results/e1_run_summary.json','project/lamost_baseline/audit/source_provenance.json','runtime_20261025/manifests/baseline_identity_boundary_audit.json','e1_wrapup_20261024/E1_frozen_cells_765.csv','e1_wrapup_20261024/E1_WRAPUP.md','e1_recovery_20261024/recovery_index.json','e2_20261024/E2_CURRENT_REPORT.md','e2_20261024/E2_RECONSTRUCTION_AMENDMENT.md','e2_20261024/E2_INTEGRITY_AUDIT.json','e2_20261024/E2_missing_primary_42.csv')
class ReviewError(RuntimeError):pass
class ReviewInvalidated(ReviewError):pass

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def canon(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode('utf-8')
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def atomic_json(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with tmp.open('w',encoding='utf-8') as f:json.dump(d,f,indent=2,sort_keys=True,ensure_ascii=False,default=str);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def safe_under(p,base):
 p=Path(p).resolve();b=Path(base).resolve()
 if b!=p and b not in p.parents:raise ReviewError(f'path outside expected project root: {p}')
 return p
_REASON_SANITIZER=None
def sanitize_review_reason(value):
 global _REASON_SANITIZER
 if _REASON_SANITIZER is None:
  candidates=(RUNTIME/'source'/'reason_text_curation.py',RUNTIME/'staging'/'reason_text_curation_20261026'/'source'/'reason_text_curation.py')
  for index,candidate in enumerate(candidates):
   if candidate.is_file():
    spec=importlib.util.spec_from_file_location('lamost_reason_text_curation',candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    _REASON_SANITIZER=module.sanitize_reason_text;break
  if _REASON_SANITIZER is None:raise ReviewError('shared reason-text curation helper is unavailable')
  if Path(__file__).resolve().parent==RUNTIME/'source' and candidates[0]!=candidate:raise ReviewError('shared reason-text curation helper must be installed as a runtime source module')
 return _REASON_SANITIZER(value)

def registry_projection(runtime):
 reg=load(Path(runtime)/'registry.json');tasks=reg.get('tasks',[])
 if len(tasks)!=6270:raise ReviewError(f'registry contains {len(tasks)} entries; expected 6,270')
 rows=[]
 for t in sorted(tasks,key=lambda z:z.get('key','')):
  if t.get('status')!='validated_terminal':raise ReviewError(f"task not validated terminal: {t.get('key')}={t.get('status')}")
  outcome=t.get('outcome');outcome=outcome.get('status') or outcome.get('outcome') if isinstance(outcome,dict) else outcome
  if outcome not in {'successful','scientific_failure','unsupported','unavailable_dependency','user_stopped'}:raise ReviewError(f"invalid outcome for {t.get('key')}: {outcome}")
  attempts=[]
  for a in t.get('attempts',[]):
   if isinstance(a,dict):attempts.append({k:a.get(k) for k in ('attempt_id','attempt_number','started_utc','finished_utc','reason','status','outcome','validation_state','resource_profile','peak_tree_rss_bytes') if k in a})
  def privacy_view(x):
   banned={'pid','pgid','process_start_ticks','worker_pid','controller_pid','owner_pid','request_path','result_path','worker_log_path','stdout','stderr','phase_supervision','private_process_receipt','process_inventory','processes','cmdline','command_line','argv'}
   if isinstance(x,dict):return {k:privacy_view(v) for k,v in x.items() if str(k).lower() not in banned and 'pid' not in str(k).lower()}
   if isinstance(x,list):return [privacy_view(v) for v in x]
   if isinstance(x,str):return sanitize_review_reason(x)
   return x
  rows.append(privacy_view({k:t.get(k) for k in ('key','experiment','scientific_case','kind','status','validation_state','result','resource_profile','source_metadata','artifact_dir','dependencies','seed','optimizer_seed') if k in t}|{'outcome':outcome,'attempts':attempts}))
 if len({x.get('key') for x in rows})!=6270:raise ReviewError('registry task keys are not unique')
 return {'task_count':len(rows),'source_registry_sha256':sha_file(Path(runtime)/'registry.json'),'scientific_task_outcomes_sha256':sha_bytes(canon(rows)),'tasks':rows,'sanitization':{'private process identifiers, phase-supervision receipts, process inventory and operational paths removed':'true','scientific outcomes, result metrics, attempts, resource profiles and reasons retained':'true'}}
def resolve_cold_store(root,runtime,cold_store=None):
 if cold_store is not None:return cold_store
 root=Path(root).resolve();runtime=Path(runtime).resolve()
 manifest=runtime/'manifests/cold_model_store_manifest.json'
 if not manifest.is_file():return None
 module_path=runtime/'source/cold_model_storage.py'
 if not module_path.is_file():raise ReviewError('cold model manifest exists but deployed cold storage resolver is missing')
 journals=runtime/'journals/cold_model_store'
 try:
  spec=importlib.util.spec_from_file_location('lamost_cold_model_storage_for_review',module_path)
  module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
  return module.ColdModelStore.from_runtime(root,runtime,manifest_path=manifest,journal_root=journals)
 except Exception as exc:raise ReviewError(f'cold model storage resolver initialization failed: {exc}') from exc

def _cold_codec_recipe_sha(desc):
 recipe={k:v for k,v in desc.items() if k not in {'encoded_sha256','encoded_size_bytes','encoded_crc32'}}
 return sha_bytes(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode('utf-8'))

def cold_member_index(cold_store):
 if cold_store is None:return {}
 try:doc=load(cold_store.manifest)
 except Exception as exc:raise ReviewError(f'cold model-store manifest is unreadable: {exc}') from exc
 if doc.get('schema_version')!='lamost-cold-model-store/1' or not isinstance(doc.get('members'),list):
  raise ReviewError('cold model-store manifest schema is invalid')
 rows={}
 for row in doc.get('members',[]):
  logical=row.get('logical_path');aliases=row.get('aliases')
  required=('task_key','task_sha256','archive_member','sha256','bytes','crc32','header_offset')
  if not isinstance(logical,str) or not isinstance(aliases,list) or any(row.get(k) in (None,'') for k in required):
   raise ReviewError('cold manifest member lacks required identity or alias inventory')
  if len(str(row.get('sha256'))) != 64:raise ReviewError('cold manifest member SHA-256 is invalid')
  desc=row.get('storage_encoding')
  if desc is not None:
   if not isinstance(desc,dict) or not desc.get('codec_version') or not isinstance(desc.get('encoded_sha256'),str) or len(desc['encoded_sha256'])!=64:
    raise ReviewError('encoded cold manifest lacks codec, physical hash, or recipe identity')
   if desc.get('original_sha256')!=row.get('sha256') or desc.get('original_size_bytes')!=row.get('bytes') or desc.get('original_crc32')!=row.get('crc32'):
    raise ReviewError('encoded cold manifest logical identity differs from model row')
   if type(desc.get('encoded_size_bytes')) is not int or desc['encoded_size_bytes']<=0 or type(desc.get('encoded_crc32')) is not int:
    raise ReviewError('encoded cold manifest physical size/CRC is invalid')
   if type(row.get('header_offset')) is not int or row['header_offset']<0:
    raise ReviewError('encoded cold manifest ZIP offset is invalid')
   _cold_codec_recipe_sha(desc)
  for name in [logical,*aliases]:
   if not isinstance(name,str) or not name:raise ReviewError('cold manifest has invalid or ambiguous logical alias')
   if name in rows and rows[name]!=row:raise ReviewError('cold manifest has invalid or ambiguous logical alias')
   rows[name]=row
 return rows

def cold_member_identity(info,row,requested):
 identity={
  'logical_source_path':requested,
  'canonical_logical_path':info.get('canonical_logical_path',row.get('logical_path')),
  'resolved_from_alias':bool(info.get('resolved_from_alias',requested!=row.get('logical_path'))),
  'task_key':row.get('task_key'),
  'task_sha256':row.get('task_sha256'),
  'archive_member':info.get('archive_member',row.get('archive_member')),
  'member_sha256':info.get('member_sha256',info.get('sha256')),
  'member_bytes':int(info.get('member_size',info.get('size'))),
  'member_crc32':int(info.get('member_crc32',row.get('crc32'))),
  'member_header_offset':int(info.get('member_header_offset',row.get('header_offset'))),
  'source_mtime_ns':int(info.get('mtime_ns',row.get('source_mtime_ns'))),
  'aliases':sorted(set(row.get('aliases',[]))),
 }
 desc=row.get('storage_encoding')
 if desc is not None:
  identity.update({'logical_sha256':row['sha256'],'logical_bytes':int(row['bytes']),
   'logical_crc32':int(row['crc32']),'storage_format':desc['codec_version'],
   'storage_encoding':desc,'recipe_sha256':_cold_codec_recipe_sha(desc)})
 return identity

def file_record(path,root,kind,expected_hashes=None,verify_stat=True,cold_store=None,cold_members=None,expected_sha256=None,cache_observation=None):
 p=safe_under(path,root)
 logical=p.relative_to(Path(root).resolve()).as_posix()
 row=(cold_members or {}).get(logical)
 if row is not None:
  if cold_store is None:raise ReviewError('cold member row exists without an active verified resolver')
  if not isinstance(expected_sha256,str) or len(expected_sha256)!=64:raise ReviewError(f'cold audited artifact lacks expected SHA-256: {logical}')
  if expected_sha256!=row.get('sha256'):raise ReviewError(f'cold logical source SHA differs from expected validation: {logical}')
  try:info=cold_store.artifact_stat(logical,expected_sha256)
  except Exception as exc:raise ReviewError(f'cold member verification failed for {logical}: {exc}') from exc
  if info.get('sha256')!=expected_sha256 or info.get('size')!=int(row.get('bytes',-1)):raise ReviewError(f'cold artifact differs from logical audit cache/member record: {logical}')
  if cache_observation is not None:
   if int(cache_observation.get('size',-1))!=int(info['size']) or int(cache_observation.get('mtime_ns',-1))!=int(info['mtime_ns']) or cache_observation.get('sha256')!=info.get('sha256'):
    raise ReviewError(f'audit-cache source identity differs from verified cold member: {logical}')
  desc=row.get('storage_encoding')
  if desc is None:
   # Preserve the existing raw-member contract and serialized identity shape.
   member=cold_member_identity(info,row,logical)
   if not member['archive_member'] or not member['task_key'] or not member['task_sha256'] or member['member_sha256']!=expected_sha256 or member['member_bytes']!=int(info['size']):
    raise ReviewError(f'cold member semantic identity is incomplete: {logical}')
  else:
   recipe_sha=_cold_codec_recipe_sha(desc);cache=info.get('cache_identity') or {}
   if info.get('storage_encoding')!=desc:raise ReviewError(f'cold codec descriptor differs from source inventory: {logical}')
   if info.get('archive_member')!=row.get('archive_member') or int(info.get('member_header_offset',-1))!=int(row.get('header_offset',-2)):
    raise ReviewError(f'cold encoded archive member identity differs from source inventory: {logical}')
   physical=(info.get('member_sha256'),int(info.get('member_size',-1)),int(info.get('member_crc32',-1)))
   declared=(desc.get('encoded_sha256'),int(desc.get('encoded_size_bytes',-2)),int(desc.get('encoded_crc32',-3)))
   if physical!=declared or info.get('storage_format')!=desc.get('codec_version'):
    raise ReviewError(f'cold encoded physical member differs from source inventory: {logical}')
   if cache.get('recipe_sha256')!=recipe_sha:
    raise ReviewError(f'cold codec recipe/cache binding differs from source inventory: {logical}')
   member=cold_member_identity(info,row,logical)
   if not member['task_key'] or not member['task_sha256'] or member['logical_sha256']!=expected_sha256 or member['logical_bytes']!=int(info['size']):
    raise ReviewError(f'cold encoded logical identity is incomplete: {logical}')
  if expected_hashes is not None:expected_hashes[str(p)]=expected_sha256
  return {'path':logical,'bytes':int(info['size']),'mtime_ns':int(info['mtime_ns']),'sha256':expected_sha256,'kind':kind,'backing':'cold_zip','cold_member_identity':member}
 if not p.is_file():raise ReviewError(f'review-bound file missing: {p}')
 st=p.stat();h=sha_file(p)
 if expected_hashes is not None:expected_hashes[str(p)]=h
 return {'path':p.relative_to(root).as_posix(),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':h,'kind':kind}

def auditcache_file_record(name,observation,root,expected_hashes,cold_store=None,cold_members=None):
 p=safe_under(name,root);h=observation.get('sha256')
 if not h:raise ReviewError(f'audited input lacks SHA-256: {p}')
 logical=p.relative_to(Path(root).resolve()).as_posix();row=(cold_members or {}).get(logical)
 if row is not None:
  return file_record(p,root,'audited_artifact',expected_hashes,cold_store=cold_store,cold_members=cold_members,expected_sha256=h,cache_observation=observation)
 if not p.is_file():raise ReviewError(f'audited scientific input disappeared: {p}')
 st=p.stat()
 if st.st_size!=int(observation.get('size',-1)) or st.st_mtime_ns!=int(observation.get('mtime_ns',-1)):raise ReviewError(f'audited input metadata changed; rerun artifact audit before review: {p}')
 expected_hashes[str(p)]=h
 return {'path':p.relative_to(root).as_posix(),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':h}
def current_frozen_e1_e2_figures(runtime):
 runtime=Path(runtime)
 folder=runtime/'reports'/'frozen_e1_e2_figures'
 return sorted(p for p in folder.glob('*.png') if p.is_file()) if folder.is_dir() else []

PUBLIC_PROVENANCE_INVENTORY='manifests/public_scientific_provenance_manifest.json'
PUBLIC_PROVENANCE_ARCHIVE_MEMBERS=(
 'manifests/incidents/e4_weight_schema_20261025_summary.json',
 'manifests/incidents/svm_native_margin_api_20261026_summary.json',
)

def runtime_python_paths(runtime):
 runtime=Path(runtime)
 found=[]
 for base in (runtime/'source',runtime/'tests'):
  if not base.is_dir():continue
  for p in base.rglob('*.py'):
   if not p.is_file() or any(x in {'__pycache__','staging'} for x in p.relative_to(base).parts):continue
   found.append(p)
 return sorted(set(found),key=lambda p:p.relative_to(runtime).as_posix())

def _public_provenance_finalizer(runtime,finalizer_path=None):
 runtime=Path(runtime)
 production=Path(__file__).resolve().parent==runtime/'source'
 if finalizer_path is not None:candidates=[Path(finalizer_path)]
 elif production:candidates=[runtime/'source'/'finalize_project.py']
 else:candidates=[runtime/'source'/'finalize_project.py',runtime/'staging'/'archive_resume_doc_audit_20261026'/'finalize_project.py']
 for candidate in candidates:
  if not candidate.is_file():continue
  spec=importlib.util.spec_from_file_location('lamost_public_provenance_finalizer',candidate)
  module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
  if hasattr(module,'_add_public_provenance'):return module
 raise ReviewError('public provenance collector _add_public_provenance is unavailable from the production finalizer')

def public_provenance_records(root,runtime,expected_hashes=None,finalizer_path=None):
 root=Path(root).resolve();runtime=Path(runtime).resolve()
 collector=_public_provenance_finalizer(runtime,finalizer_path)
 entries=[];collector._add_public_provenance(root,runtime,entries,expected_hashes)
 archive_views={}
 for entry in entries:
  payload=entry.source if isinstance(entry.source,bytes) else Path(entry.source).read_bytes()
  archive_views[entry.member]={'bytes':len(payload),'sha256':sha_bytes(payload),'category':entry.category}
 inventory_member='runtime_20261025/manifests/public_scientific_provenance_manifest.json'
 invview=archive_views.get(inventory_member)
 if invview is None:raise ReviewError('public provenance collector omitted its in-memory inventory')
 inventry=next(e for e in entries if e.member==inventory_member)
 invpayload=inventry.source if isinstance(inventry.source,bytes) else Path(inventry.source).read_bytes()
 try:inventory=json.loads(invpayload)
 except Exception as exc:raise ReviewError('public provenance collector emitted invalid inventory JSON') from exc
 if inventory.get('schema_version')!='lamost-public-execution-provenance/1' or not isinstance(inventory.get('included'),list):
  raise ReviewError('public scientific provenance inventory schema invalid')
 records=inventory['included'];by_archive={str(x.get('archive_member')):x for x in records}
 if len(by_archive)!=len(records):raise ReviewError('public provenance inventory contains duplicate archive members')
 required={
  (runtime/'manifests/baseline_identity_boundary_audit.json').relative_to(root).as_posix(),
  (runtime/'manifests/concurrency_user_authorization_20261025.json').relative_to(root).as_posix(),
 }
 required.update(p.relative_to(root).as_posix() for p in sorted((runtime/'manifests').glob('freeze_before_*.json')))
 required.update((runtime/rel).relative_to(root).as_posix() for rel in PUBLIC_PROVENANCE_ARCHIVE_MEMBERS)
 qualified_closure=set(getattr(collector,'PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256',{}))
 required.update(qualified_closure)
 operational_source_closure=set(getattr(collector,'PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256',{}))
 required.update(operational_source_closure)
 if set(by_archive)!=required:raise ReviewError('public provenance inventory archive-member allowlist mismatch')
 curated_map={
  (runtime/'manifests/incidents/e4_weight_schema_20261025.json').relative_to(root).as_posix():(runtime/'manifests/incidents/e4_weight_schema_20261025_summary.json').relative_to(root).as_posix(),
  (runtime/'manifests/incidents/svm_native_margin_api_20261026.json').relative_to(root).as_posix():(runtime/'manifests/incidents/svm_native_margin_api_20261026_summary.json').relative_to(root).as_posix(),
 }
 allowed_sources=required|set(curated_map)
 source_records=[]
 for item in records:
  source_member=item.get('source_member');archive_member=item.get('archive_member')
  if source_member not in allowed_sources or archive_member not in required:
   raise ReviewError('public provenance inventory contains a non-allowlisted source/member')
  expected_archive=curated_map.get(source_member,source_member)
  if source_member in qualified_closure:
   expected_curation='exact_sha_pinned_policy_bytes' if source_member.endswith('.json') else 'exact_sha_pinned_reviewed_safe_log_bytes'
  elif source_member in operational_source_closure:
   operational_row=getattr(collector,'PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256',{})[source_member]
   expected_curation=operational_row[2]
  else:expected_curation='allowlisted_source_sha_bound_projection' if source_member in curated_map else 'archive_json_entry'
  if archive_member!=expected_archive or item.get('curation')!=expected_curation:
   raise ReviewError('public provenance source/member curation mapping is invalid')
  if not item.get('source_sha256') or not item.get('archive_sha256'):
   raise ReviewError('public provenance entry lacks source/archive hashes')
  source=safe_under(root/source_member,root)
  if not source.is_file() or sha_file(source)!=item['source_sha256']:
   raise ReviewError('public provenance source hash mismatch: '+str(source_member))
  view=archive_views.get(archive_member)
  if not view or view['sha256']!=item['archive_sha256'] or view['bytes']<0:
   raise ReviewError('public provenance in-memory archive view hash mismatch: '+str(archive_member))
  if expected_hashes is not None:
   # Raw sources are mutation guards; curated raw incident payloads remain excluded archive members.
   expected_hashes[str(source.resolve())]=item['source_sha256']
  source_records.append({'source_member':source.relative_to(root).as_posix(),'source_sha256':item['source_sha256'],'archive_member':archive_member,'archive_sha256':item['archive_sha256'],'curation':item['curation']})
 if set(archive_views)!=(required|{inventory_member}):
  raise ReviewError('public provenance collector emitted unexpected or missing archive entries')
 return {'source_records':source_records,'archive_views':archive_views,'inventory_sha256':invview['sha256'],'inventory_bytes':invview['bytes']}

def runtime_code_records(root,runtime,expected_hashes=None):
 root=Path(root);runtime=Path(runtime);records=[]
 for p in runtime_python_paths(runtime):
  kind='runtime_source_module' if p.is_relative_to(runtime/'source') else 'runtime_engineering_test'
  records.append(file_record(p,root,kind,expected_hashes))
 return records

def calibration_replay_review_inputs(root,runtime,expected_hashes,reviewed_files):
 from finalize_project import _calibration_replay_validation
 root=Path(root).resolve();runtime=Path(runtime).resolve()
 proof=_calibration_replay_validation(runtime)
 audit_path=runtime/'reports'/'CALIBRATION_REPLAY_AUDIT.json'
 reviewed_files.append(file_record(audit_path,root,'report_validation',expected_hashes))
 for item in proof.get('evidence_files',[]):
  p=safe_under(runtime/item['path'],runtime)
  reviewed_files.append(file_record(p,root,'report_validation',expected_hashes))
 return proof

def build_snapshot(root=ROOT,runtime=RUNTIME,cold_store=None):
 root=Path(root).resolve();runtime=Path(runtime).resolve(); expected={};files=[]
 cold_store=resolve_cold_store(root,runtime,cold_store)
 cold_members=cold_member_index(cold_store)
 # Exact report, tables, plots, and report validation ledger.
 for n in REQUIRED_CSVS:
  p=runtime/'reports'/n
  files.append(file_record(p,root,'main_table',expected))
 for n in ('FINAL_SCIENTIFIC_REPORT.md','report_result.json','figure_denominators.csv','INCREMENTAL_ARTIFACT_AUDIT.json','INCREMENTAL_ARTIFACT_ISSUES.csv'):
  files.append(file_record(runtime/'reports'/n,root,'report_validation' if n!='FINAL_SCIENTIFIC_REPORT.md' else 'final_report',expected))
 calibration_replay=calibration_replay_review_inputs(root,runtime,expected,files)
 result=load(runtime/'reports/report_result.json')
 if result.get('status')!='success' or result.get('planned_scientific_cases')!=2823:raise ReviewError('report_result is not a validated 2,823-case report')
 for p in sorted((runtime/'reports').iterdir()):
  if p.is_file() and p.suffix.lower() in {'.png','.svg','.html'} and p.name not in {x['path'].split('/')[-1] for x in files}:
   files.append(file_record(p,root,'figure',expected))
 for p in current_frozen_e1_e2_figures(runtime):
  files.append(file_record(p,root,'figure',expected))
 for p in sorted((runtime/'reports').glob('*.csv')):
  if p.name not in {x['path'].split('/')[-1] for x in files}:files.append(file_record(p,root,'report_table',expected))
 # Frozen plan, controller protocol, role identity, and source hashes.
 fixed=[]
 for rel in ('manifests/tasks.json','manifests/freeze.json','manifests/startup_audit.json','manifests/authorization_and_decisions.json','manifests/plan_amendments.json','manifests/E3_MANIFEST.json','manifests/E4_MANIFEST.json','manifests/E5_MANIFEST.json','manifests/E6_MANIFEST.json','auditcache.json'):
  fixed.append(file_record(runtime/rel,root,'execution_manifest',expected))
 freeze=load(runtime/'manifests/freeze.json')
 for rel,h in sorted(freeze.get('source_sha256',{}).items()):
  p=runtime/'source'/rel
  rec=file_record(p,root,'frozen_execution_source',expected)
  if rec['sha256']!=h:raise ReviewError(f'execution source no longer matches freeze: {rel}')
  fixed.append(rec)
 fixed.extend(runtime_code_records(root,runtime,expected))
 public_provenance=public_provenance_records(root,runtime,expected)
 for rel in ('FINAL_REVIEW_RUNBOOK.md','FINAL_COMPLETION_EVIDENCE_CHECKLIST.md','RUN_RESUME_REPRODUCE.md'):
  fixed.append(file_record(runtime/rel,root,'review_and_reproduction_instructions',expected))
 # Frozen E1/E2 references and their current project files.
 frozen=[];seen_frozen=set()
 for rel in REQUIRED_FROZEN:
  p=root/rel;rec=file_record(p,root,'frozen_E1_E2_provenance',expected);frozen.append(rec);seen_frozen.add(rec['path'])
 master=load(root/'project/benchmark/results/master_run_config.json')
 for name,want in sorted(master.get('benchmark_python_source_sha256',{}).items()):
  p=root/'project/benchmark'/name;rec=file_record(p,root,'frozen_E1_source',expected)
  if rec['sha256']!=want:raise ReviewError(f'frozen E1 source hash mismatch: {name}')
  frozen.append(rec)
 # E2 is compact enough to bind every report/provenance file, excluding transient logs.
 for p in sorted((root/'e2_20261024').rglob('*')):
  if p.is_file() and p.suffix.lower() not in {'.log','.out','.err','.tmp','.pyc'} and '__pycache__' not in p.parts:
   rel=p.relative_to(root).as_posix()
   if rel not in seen_frozen:frozen.append(file_record(p,root,'E2_provenance',expected));seen_frozen.add(rel)
 # Bind every exact artifact hash validated by the incremental auditor. Validate cached size/mtime now;
 # the archive streaming pass will compare actual content SHA against these recorded hashes.
 master_doc=load(runtime/'master_index.json');master_semantic=dict(master_doc);master_semantic.pop('exported_utc',None);master_semantic.pop('observed_utc',None)
 cache=load(runtime/'auditcache.json');audited=[]
 cold_audited=[]
 for name,v in sorted(cache.get('files',{}).items()):
  rec=auditcache_file_record(name,v,root,expected,cold_store=cold_store,cold_members=cold_members)
  audited.append(rec)
  if rec.get('cold_member_identity') is not None:cold_audited.append(rec['cold_member_identity'])
 audit=load(runtime/'reports/INCREMENTAL_ARTIFACT_AUDIT.json')
 if int(audit.get('issue_count',-1))!=0:raise ReviewError('incremental artifact audit has unresolved issues')
 state=load(runtime/'finalizer_state.json');evidence=state.get('frozen_evidence')
 if not isinstance(evidence,dict):raise ReviewError('finalizer cached frozen evidence is absent')
 inputs={'plan_sha256':sha_file(runtime/'manifests/tasks.json'),'freeze_sha256':sha_file(runtime/'manifests/freeze.json'),'scientific_terminal_registry':registry_projection(runtime),'reviewed_files':files,'calibration_replay_proof':calibration_replay,'execution_and_report_sources':fixed,'scientific_provenance_sources':public_provenance['source_records'],'public_provenance_archive_views':public_provenance['archive_views'],'public_provenance_inventory_sha256':public_provenance['inventory_sha256'],'public_provenance_inventory_bytes':public_provenance['inventory_bytes'],'frozen_E1_E2_inputs':frozen,'audited_artifact_files':audited,'artifact_audit_sha256':sha_file(runtime/'reports/INCREMENTAL_ARTIFACT_AUDIT.json'),'artifact_audit_issues_sha256':sha_file(runtime/'reports/INCREMENTAL_ARTIFACT_ISSUES.csv'),'master_index_semantic_sha256':sha_bytes(canon(master_semantic)),'frozen_evidence':evidence}
 if cold_audited:inputs['cold_archived_artifact_members']=cold_audited
 # Add non-auditor-reviewed report/protocol inputs to expected source hashes for package-stream verification.
 for group in (files,fixed,frozen):
  for r in group:expected[str(root/r['path'])]=r['sha256']
 return {'schema_version':'lamost-report-review-inputs/1','inputs':inputs,'archive_expected_source_sha256':expected}
def manifest_id(snapshot):return sha_bytes(canon(snapshot.get('inputs',snapshot)))
def update_cached_review_state(runtime,ready):
 runtime=Path(runtime);sp=runtime/'finalizer_state.json'
 if not sp.is_file():return False
 state=load(sp);report=Path(state.get('final_report_path',runtime/'reports/FINAL_SCIENTIFIC_REPORT.md'))
 if not report.is_file() or 'frozen_evidence' not in state:return False
 state.update({'status':'report_ready_for_internal_audit','phase':'awaiting_report_audit','observed_utc':utc(),'review_candidate_id':ready['candidate_id'],'review_manifest_path':ready['manifest_path'],'review_manifest_sha256':ready['manifest_sha256'],'final_report_path':str(report),'final_report_sha256':sha_file(report)})
 atomic_json(sp,state);return True

def write_candidate(root=ROOT,runtime=RUNTIME,reason=None,cold_store=None):
 runtime=Path(runtime).resolve();review=runtime/'review_audit';review.mkdir(parents=True,exist_ok=True)
 snap=build_snapshot(root,runtime,cold_store=cold_store);cid=manifest_id(snap)
 manifests=review/'manifests';manifests.mkdir(parents=True,exist_ok=True);mp=manifests/f'candidate_{cid}.json'
 stage_dir=review/'candidates'/cid;stage_dir.mkdir(parents=True,exist_ok=True);stage_master=stage_dir/'master_index.json'
 if mp.exists():
  doc=load(mp);mi=doc.get('master_index_snapshot',{})
  if not stage_master.is_file() or sha_file(stage_master)!=mi.get('sha256'):raise ReviewError('immutable reviewed master-index snapshot is missing or changed; preserve manifest and investigate')
 else:
  raw=(Path(runtime)/'master_index.json').read_bytes();parsed=json.loads(raw);semantic=dict(parsed);semantic.pop('exported_utc',None);semantic.pop('observed_utc',None)
  if sha_bytes(canon(semantic))!=snap['inputs']['master_index_semantic_sha256']:raise ReviewError('master index changed during review snapshot staging; retry preparation')
  fd,tmp=tempfile.mkstemp(prefix='.master_index_',dir=stage_dir)
  try:
   with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
   os.replace(tmp,stage_master)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  stage_record={'path':str(stage_master.relative_to(Path(root).resolve()).as_posix()),'bytes':stage_master.stat().st_size,'sha256':sha_file(stage_master),'semantic_sha256':snap['inputs']['master_index_semantic_sha256']}
  snap['archive_expected_source_sha256'][str(stage_master.resolve())]=stage_record['sha256']
  doc={'candidate_id':cid,'created_utc':utc(),'refresh_reason':reason,'snapshot':snap,'master_index_snapshot':stage_record}
  doc['manifest_content_sha256']=sha_bytes(canon(doc));atomic_json(mp,doc)
 doc=load(mp);msha=sha_file(mp)
 ready={'schema_version':'lamost-report-ready/1','status':'waiting_for_internal_report_review','candidate_id':cid,'manifest_path':str(mp),'manifest_sha256':msha,'created_or_refreshed_utc':utc(),'refresh_reason':reason,'pass_receipt_path':str(runtime/'REPORT_AUDIT_RECEIPT.json')}
 atomic_json(runtime/'REPORT_READY_FOR_AUDIT.json',ready)
 update_cached_review_state(runtime,ready)
 try:(runtime/'REPORT_AUDIT_INVALIDATED.json').unlink()
 except FileNotFoundError:pass
 history=review/'refresh_history.jsonl'
 if reason:
  with history.open('a',encoding='utf-8') as f:f.write(json.dumps({'utc':utc(),'candidate_id':cid,'reason':reason},sort_keys=True)+'\n')
 return ready,doc

def quick_wait(runtime=RUNTIME):
 runtime=Path(runtime);ready_path=runtime/'REPORT_READY_FOR_AUDIT.json'
 if not ready_path.is_file():return None
 try:
  ready=load(ready_path);receipt=load(runtime/'REPORT_AUDIT_RECEIPT.json')
  mp=Path(ready['manifest_path'])
  if not mp.is_file() or sha_file(mp)!=ready.get('manifest_sha256'):return {'status':'waiting_for_review_manifest_repair','candidate_id':ready.get('candidate_id')}
  manifest=load(mp)
  if ready.get('status')=='review_pass_recorded' and receipt.get('decision')=='pass' and receipt.get('candidate_id')==ready.get('candidate_id') and receipt.get('manifest_sha256')==ready.get('manifest_sha256') and manifest.get('candidate_id')==ready.get('candidate_id'):
   return None
  return {'status':'waiting_for_internal_report_review','candidate_id':ready.get('candidate_id'),'manifest_path':str(mp),'manifest_sha256':ready.get('manifest_sha256')}
 except FileNotFoundError:
  try:ready=load(ready_path);return {'status':'waiting_for_internal_report_review','candidate_id':ready.get('candidate_id'),'manifest_path':ready.get('manifest_path'),'manifest_sha256':ready.get('manifest_sha256')}
  except Exception:return {'status':'waiting_for_report_review_manifest'}

def verify_pass(root=ROOT,runtime=RUNTIME,cold_store=None):
 runtime=Path(runtime);wait=quick_wait(runtime)
 if wait:raise ReviewError(wait['status']+': '+str(wait.get('candidate_id','')))
 ready=load(runtime/'REPORT_READY_FOR_AUDIT.json');mp=Path(ready['manifest_path']);manifest=load(mp);receipt=load(runtime/'REPORT_AUDIT_RECEIPT.json')
 if sha_file(mp)!=ready.get('manifest_sha256') or manifest.get('manifest_content_sha256')!=sha_bytes(canon({k:v for k,v in manifest.items() if k!='manifest_content_sha256'})):
  raise ReviewError('review manifest checksum is invalid')
 if receipt.get('decision')!='pass' or receipt.get('candidate_id')!=ready.get('candidate_id') or receipt.get('manifest_sha256')!=ready.get('manifest_sha256'):
  raise ReviewError('root-agent audit receipt does not pass this exact review candidate')
 current=build_snapshot(root,runtime,cold_store=cold_store);cid=manifest_id(current)
 if cid!=ready.get('candidate_id'):
  invalid={'schema_version':'lamost-report-audit-invalidated/1','observed_utc':utc(),'old_candidate_id':ready.get('candidate_id'),'new_candidate_id':cid,'reason':'plan, source, terminal outcomes, artifacts, or reviewed report/table/figure hashes changed after review; refresh and review the new candidate'}
  atomic_json(runtime/'REPORT_AUDIT_INVALIDATED.json',invalid)
  ready['status']='review_invalidated_refresh_required';ready['invalidated_utc']=utc();ready['invalidation_reason']=invalid['reason'];atomic_json(runtime/'REPORT_READY_FOR_AUDIT.json',ready)
  raise ReviewInvalidated('reviewed inputs changed; candidate invalidated; run final_review.py refresh after addressing the change')
 expected=dict(manifest['snapshot'].get('archive_expected_source_sha256',{}))
 expected[str((runtime/'REPORT_AUDIT_RECEIPT.json').resolve())]=sha_file(runtime/'REPORT_AUDIT_RECEIPT.json')
 expected[str((runtime/'REPORT_READY_FOR_AUDIT.json').resolve())]=sha_file(runtime/'REPORT_READY_FOR_AUDIT.json')
 expected[str(mp.resolve())]=sha_file(mp)
 mi=manifest.get('master_index_snapshot',{});mip=Path(root)/mi.get('path','')
 if not mip.is_file() or sha_file(mip)!=mi.get('sha256'):raise ReviewInvalidated('immutable reviewed master-index snapshot changed')
 proof={'candidate_id':ready['candidate_id'],'manifest_sha256':ready['manifest_sha256'],'audit_receipt_sha256':sha_file(runtime/'REPORT_AUDIT_RECEIPT.json'),'reviewer':receipt['reviewer'],'reviewed_utc':receipt['reviewed_utc'],'decision':'pass','review_manifest_path':str(mp),'report_file_count':len(manifest['snapshot']['inputs']['reviewed_files']),'scientific_terminal_registry_sha256':manifest['snapshot']['inputs']['scientific_terminal_registry']['scientific_task_outcomes_sha256'],'review_inputs_sha256':sha_bytes(canon(manifest['snapshot']['inputs'])),'master_index_snapshot_path':str(mip),'master_index_snapshot_sha256':mi.get('sha256')}
 return proof,expected

def verify_report_files(runtime=RUNTIME,root=ROOT,manifest=None):
 runtime=Path(runtime);root=Path(root);ready=load(runtime/'REPORT_READY_FOR_AUDIT.json')
 if manifest is None:manifest=load(ready['manifest_path'])
 for r in manifest.get('snapshot',{}).get('inputs',{}).get('reviewed_files',[]):
  if r.get('kind') not in {'main_table','report_validation','final_report','figure','report_table'}:continue
  p=safe_under(root/r['path'],root)
  if not p.is_file() or p.stat().st_size!=int(r['bytes']) or sha_file(p)!=r['sha256']:
   return False
 return True

def record_pass(runtime=RUNTIME,candidate_id=None,reviewer=None,notes=None):
 runtime=Path(runtime);ready=load(runtime/'REPORT_READY_FOR_AUDIT.json')
 if not candidate_id or candidate_id!=ready.get('candidate_id'):raise ReviewError('candidate ID does not match current REPORT_READY_FOR_AUDIT.json')
 if not reviewer or len(reviewer.strip())<3:raise ReviewError('reviewer identity is required')
 if not notes or len(notes.strip())<30:raise ReviewError('review notes must describe the actual findings/denominators/figures checked')
 mp=Path(ready.get('manifest_path',''))
 if not mp.is_file() or sha_file(mp)!=ready.get('manifest_sha256'):raise ReviewError('current review manifest file hash does not match ready marker')
 manifest=load(mp)
 if manifest.get('candidate_id')!=candidate_id or manifest.get('manifest_content_sha256')!=sha_bytes(canon({k:v for k,v in manifest.items() if k!='manifest_content_sha256'})):raise ReviewError('current review manifest is invalid or stale')
 receipt={'schema_version':'lamost-internal-report-audit/1','decision':'pass','candidate_id':ready['candidate_id'],'manifest_sha256':ready['manifest_sha256'],'reviewer':reviewer.strip(),'reviewed_utc':utc(),'review_notes':notes.strip(),'automatic_review':False}
 atomic_json(runtime/'REPORT_AUDIT_RECEIPT.json',receipt)
 ready.update({'status':'review_pass_recorded','pass_receipt_sha256':sha_file(runtime/'REPORT_AUDIT_RECEIPT.json')});atomic_json(runtime/'REPORT_READY_FOR_AUDIT.json',ready)
 return receipt


def mark_invalidated(runtime=RUNTIME,reason='reviewed inputs changed'):
 runtime=Path(runtime);ready=load(runtime/'REPORT_READY_FOR_AUDIT.json');ready['status']='review_invalidated_refresh_required';ready['invalidated_utc']=utc();ready['invalidation_reason']=reason;atomic_json(runtime/'REPORT_READY_FOR_AUDIT.json',ready)
 payload={'schema_version':'lamost-report-audit-invalidated/1','observed_utc':utc(),'candidate_id':ready.get('candidate_id'),'reason':reason}
 atomic_json(runtime/'REPORT_AUDIT_INVALIDATED.json',payload);return payload

def self_test():
 import tempfile
 with tempfile.TemporaryDirectory(prefix='lamost_review_gate_test_') as td:
  rt=Path(td);(rt/'review_audit/manifests').mkdir(parents=True);m={'candidate_id':'a'*64,'manifest_content_sha256':'b'*64};atomic_json(rt/'review_audit/manifests/c.json',m);msha=sha_file(rt/'review_audit/manifests/c.json');atomic_json(rt/'REPORT_READY_FOR_AUDIT.json',{'candidate_id':m['candidate_id'],'manifest_path':str(rt/'review_audit/manifests/c.json'),'manifest_sha256':msha})
  assert quick_wait(rt)['status']=='waiting_for_internal_report_review'
  receipt={'decision':'pass','candidate_id':m['candidate_id'],'manifest_sha256':msha};atomic_json(rt/'REPORT_AUDIT_RECEIPT.json',receipt);rdy=load(rt/'REPORT_READY_FOR_AUDIT.json');rdy['status']='review_pass_recorded';atomic_json(rt/'REPORT_READY_FOR_AUDIT.json',rdy);assert quick_wait(rt) is None
  original=b'# reviewed final report\n';f=rt/'FINAL_SCIENTIFIC_REPORT.md';f.write_bytes(original);before=f.stat().st_mtime_ns;old=manifest_id({'report_sha256':sha_file(f)});assert f.read_bytes()==original and f.stat().st_mtime_ns==before
  atomic_json(rt/'finalizer_state.json',{'phase':'full_archive','review_candidate_id':'older','final_report_path':str(f),'final_report_sha256':'stale','frozen_evidence':{'checked':True}})
  refreshed={'candidate_id':'new-review-id','manifest_path':str(rt/'review_audit/manifests/new.json'),'manifest_sha256':'manifest-hash'};atomic_json(rt/'review_audit/manifests/new.json',{'fixture':True})
  assert update_cached_review_state(rt,refreshed);cached=load(rt/'finalizer_state.json');assert cached['phase']=='awaiting_report_audit' and cached['review_candidate_id']=='new-review-id' and f.read_bytes()==original and f.stat().st_mtime_ns==before
  file_row={'path':'FINAL_SCIENTIFIC_REPORT.md','bytes':len(original),'mtime_ns':f.stat().st_mtime_ns,'sha256':sha_file(f),'kind':'final_report'};mini={'snapshot':{'inputs':{'reviewed_files':[file_row]}}};assert verify_report_files(rt,rt,mini)
  f.write_bytes(b'# changed report\n');assert manifest_id({'report_sha256':sha_file(f)})!=old and not verify_report_files(rt,rt,mini)
  scans={'n':0}
  def counted():scans['n']+=1
  # The waiting-path primitive consults only stage/receipt files; no snapshot builder is called.
  if quick_wait(rt):pass
  assert scans['n']==0
  return {'status':'self_test_passed','missing_pass_receipt_blocks':True,'changed_reviewed_hash_changes_candidate_and_file_invalidates':True,'waiting_gate_uses_cached_marker_without_snapshot_rescan':True,'valid_receipt_reuses_report_bytes_without_overwrite':True,'explicit_refresh_updates_cached_candidate_without_regenerating_report':True}

def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True);sub.add_parser('prepare')
 r=sub.add_parser('refresh');r.add_argument('--reason',required=True)
 p=sub.add_parser('record-pass');p.add_argument('--candidate-id',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--notes',required=True)
 sub.add_parser('show');sub.add_parser('self-test')
 a=ap.parse_args()
 try:
  if a.cmd=='prepare':res=write_candidate()
  elif a.cmd=='refresh':res=write_candidate(reason=a.reason)
  elif a.cmd=='record-pass':res=record_pass(candidate_id=a.candidate_id,reviewer=a.reviewer,notes=a.notes)
  elif a.cmd=='show':res=quick_wait() or verify_pass()[0]
  else:res=self_test()
  print(json.dumps(res,indent=2,default=str));return 0
 except Exception as e:print(json.dumps({'status':'review_gate_blocked','error':f'{type(e).__name__}: {e}'},indent=2));return 2
if __name__=='__main__':raise SystemExit(main())
