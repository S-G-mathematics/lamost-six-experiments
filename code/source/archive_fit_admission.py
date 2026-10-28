from __future__ import annotations
import ast
import hashlib
import json
import os
import pathlib
import re
import stat
import time

POLICY_FIELD = 'archive_native_fit_overlap_sha256'
WORKER_REAPER_FIELD = 'worker_reaper_source_sha256'
QUALIFICATION_FIELD = 'archive_native_fit_overlap_qualification_sha256'
POLICY_REL = pathlib.Path('manifests/ARCHIVE_NATIVE_FIT_OVERLAP_20261028.json')
QUALIFICATION_SCHEMA = 'lamost-archive-native-fit-overlap-qualification/1'
POLICY_SCHEMA = 'lamost-archive-native-fit-overlap-policy/1'
GIB = 1024 ** 3
HELPER_RESERVATION_BYTES = int(1.5 * GIB)
HELPER_CPU_UNITS = 1
OWNER_OPERATION = 'rf_cold_batch_wrapper_20261026'
IO_PROFILE = 'bounded-1800-mixedsmall4gib2048'
BATCH_POLICY = 'storage-followup'
CACHE_SHA_MEMO = {}
COLD_MEMBER_REF_CACHE = {}
COLD_MEMBER_REF_CACHE_MAX = 2

def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def _json_regular(path):
    p=pathlib.Path(path)
    st=p.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ValueError('not_regular')
    return json.loads(p.read_text(encoding='utf-8'))

def _safe_file(root, rel):
    root=pathlib.Path(root).resolve()
    p=root/pathlib.Path(rel)
    current=p
    while current != root and root in current.parents:
        if current.is_symlink(): raise ValueError('symlink_path')
        current=current.parent
    if current != root: raise ValueError('path_escape')
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode): raise ValueError('not_regular')
    return p

def _identity(path):
    p=pathlib.Path(path)
    st=p.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):raise ValueError('unsafe_input')
    return (str(p.resolve()),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def _cached_sha(path, expected=None):
    p=pathlib.Path(path)
    before=_identity(p)
    memo=CACHE_SHA_MEMO.get(str(p.resolve()))
    if memo and memo[0]==before:
        digest=memo[1]
    else:
        digest=sha256_file(p)
        after=_identity(p)
        if before!=after:raise ValueError('input_changed_during_hash')
        CACHE_SHA_MEMO[str(p.resolve())]=(after,digest)
    if expected is not None and digest!=expected:raise ValueError('input_hash_mismatch')
    return digest

def _cold_model_manifest_refs(root):
    """Return the exact logical paths already represented in the cold index.

    The native fit output must be absent both on disk and from the current cold
    archive index; an old archived alias is not permission to refit/recreate it.
    Cache only by verified file identity and digest.
    """
    root=pathlib.Path(root).resolve()
    path=_safe_file(root,pathlib.Path('manifests/cold_model_store_manifest.json'))
    identity=_identity(path);digest=_cached_sha(path)
    cache_key=str(path.resolve())
    cached=COLD_MEMBER_REF_CACHE.get(cache_key)
    if cached and cached[0]==identity and cached[1]==digest:
        return digest,cached[2]
    doc=_json_regular(path)
    if doc.get('schema_version')!='lamost-cold-model-store/1' or not isinstance(doc.get('members'),list):
        raise ValueError('cold_manifest_schema')
    refs=set()
    def add_safe(value):
        if not isinstance(value,str) or not value or '\\' in value:
            raise ValueError('cold_manifest_logical_path')
        rel=pathlib.PurePosixPath(value)
        if rel.is_absolute() or rel.as_posix()!=value or any(x in ('','.','..') for x in rel.parts):
            raise ValueError('cold_manifest_logical_path')
        refs.add(value)
    for row in doc['members']:
        if not isinstance(row,dict) or not isinstance(row.get('aliases'),list):
            raise ValueError('cold_manifest_member')
        add_safe(row.get('logical_path'))
        for alias in row['aliases']:add_safe(alias)
    if len(COLD_MEMBER_REF_CACHE)>=COLD_MEMBER_REF_CACHE_MAX:COLD_MEMBER_REF_CACHE.clear()
    COLD_MEMBER_REF_CACHE[cache_key]=(identity,digest,refs)
    return digest,refs

def _source_pin_dict(path, assignment):
    tree=ast.parse(pathlib.Path(path).read_text(encoding='utf-8'),filename=str(path))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==assignment for t in node.targets):
            value=ast.literal_eval(node.value)
            if isinstance(value,dict):return value
    raise ValueError('source_pin_map_missing')

def _policy(runtime, frozen):
    if not isinstance(frozen,dict):raise ValueError('freeze_malformed')
    declared=frozen.get(POLICY_FIELD)
    qdeclared=frozen.get(QUALIFICATION_FIELD)
    if declared is None and qdeclared is None:return None
    if not _hex(declared) or not _hex(qdeclared):raise ValueError('policy_freeze_binding_malformed')
    root=pathlib.Path(runtime)
    policy_path=_safe_file(root,POLICY_REL)
    raw=policy_path.read_bytes()
    if _sha256_bytes(raw)!=declared:raise ValueError('policy_sha_mismatch')
    doc=json.loads(raw)
    if not isinstance(doc,dict) or doc.get('schema')!=POLICY_SCHEMA or doc.get('status')!='qualified':
        raise ValueError('policy_not_qualified')
    if doc.get('policy_id')!='archive-native-fit-overlap-1.5gib-cpu1-v1':
        raise ValueError('policy_id')
    expected_scope={'experiments':[4,5],'kind':'fit','never_attempted':True,'reuse_pipeline':False,
                    'routes':{'4':['direct','treatment'],'5':['direct','synthetic']},
                    'require_successful_dependencies':True,'no_existing_same_task_pipeline_or_checkpoint':True}
    if doc.get('scope')!=expected_scope:raise ValueError('policy_scope')
    expected_resources={'helper_reservation_gib':1.5,'helper_cpu_reservation_units':1,
       'host_os_harbor_reserve_gib':6,'commitment_growth_margin_gib':2,
       'admission_only_safety_buffer_gib':1,'worker_memory_limit_gib':10,
       'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,
       'archive_wall_seconds':1800,'archive_wrapper_wall_seconds':1860,'archive_child_rss_limit_bytes':1073741824,
       'archive_child_address_space_limit_bytes':939524096,'archive_wrapper_rss_limit_bytes':1610612736,
       'native_threads':1,'nested_threads':1}
    if doc.get('resources')!=expected_resources:raise ValueError('policy_resources')
    if doc.get('archive_operation')!={'owner_operation':OWNER_OPERATION,'batch_policy':BATCH_POLICY,
          'archive_io_profile':IO_PROFILE,'storage_codec_policy':None}:
        raise ValueError('policy_archive_operation')
    source_map=doc.get('source_sha256')
    required={'controller.py','archive_fit_admission.py','cold_auto_compaction.py','run_batch.py',
       'commit_batch_child.py','cold_model_storage.py','cold_codec_storage.py','reversible_joblib_codec.py',
       'cold_storage_safety.py','batch_plan.py','admission_evidence.py'}
    if not isinstance(source_map,dict) or set(source_map)!=required or any(not _hex(v) for v in source_map.values()):
        raise ValueError('policy_source_inventory')
    current={name:_cached_sha(root/'source'/name, source_map[name]) for name in sorted(required)}
    freeze_sources=frozen.get('source_sha256')
    if not isinstance(freeze_sources,dict) or freeze_sources.get('controller.py')!=current['controller.py'] or freeze_sources.get('archive_fit_admission.py')!=current['archive_fit_admission.py']:
        raise ValueError('freeze_source_binding')
    cold_pins=_source_pin_dict(root/'source/cold_auto_compaction.py','PINS')
    run_pins=_source_pin_dict(root/'source/run_batch.py','SOURCE_PINS')
    for pins in (cold_pins,run_pins):
        for name,digest in pins.items():
            if name in current and current[name]!=digest:raise ValueError('operation_source_pin_mismatch:'+name)
    native=doc.get('native_input_manifests')
    expected_native={'cache/cache_manifest.json','manifests/E4_MANIFEST.json','manifests/E5_MANIFEST.json'}
    if not isinstance(native,dict) or set(native)!=expected_native or any(not _hex(x) for x in native.values()):
        raise ValueError('native_input_manifest_inventory')
    native_actual={name:_cached_sha(root/name,native[name]) for name in sorted(native)}
    qpath_value=doc.get('qualification_path')
    if not isinstance(qpath_value,str):raise ValueError('qualification_path')
    qrel=pathlib.PurePosixPath(qpath_value)
    if qrel.is_absolute() or '..' in qrel.parts:raise ValueError('qualification_path_unsafe')
    qpath=_safe_file(root,qrel)
    qraw=qpath.read_bytes()
    if _sha256_bytes(qraw)!=qdeclared:raise ValueError('qualification_sha_mismatch')
    qdoc=json.loads(qraw)
    if not isinstance(qdoc,dict) or qdoc.get('schema')!=QUALIFICATION_SCHEMA or qdoc.get('status')!='passed':
        raise ValueError('qualification_not_passed')
    if qdoc.get('policy_sha256')!=declared or qdoc.get('source_sha256')!=current or qdoc.get('native_input_manifests')!=native_actual:
        raise ValueError('qualification_binding_mismatch')
    suite=qdoc.get('portable_suite')
    if not isinstance(suite,dict) or suite.get('status')!='passed' or suite.get('exit_code')!=0 or suite.get('failed_test_count')!=0 or not isinstance(suite.get('expected_test_count'),int) or suite.get('passed_test_count')!=suite.get('expected_test_count'):
        raise ValueError('qualification_suite_missing')
    harness=qdoc.get('controller_harness')
    if not isinstance(harness,dict) or harness.get('status')!='passed' or harness.get('fit_attempts_started')!=0 or harness.get('archive_helper_fixture_only') is not True:
        raise ValueError('qualification_harness_missing')
    return {'document':doc,'policy_sha256':declared,'qualification_sha256':qdeclared,
            'source_sha256':current,'native_input_manifests':native_actual}

def _hex(x):
    return isinstance(x,str) and len(x)==64 and all(c in '0123456789abcdef' for c in x)

def native_fit_proof(runtime, task, definition, tasks):
    root=pathlib.Path(runtime).resolve()
    if not isinstance(task,dict) or not isinstance(definition,dict) or task.get('key')!=definition.get('key'):return None
    if task.get('kind')!='fit' or task.get('reuse_pipeline') or task.get('attempts') not in ([],None):return None
    if task.get('admission_reservation_bytes') is not None or task.get('adaptive_promoted_heavy'):return None
    if task.get('status') not in ('planned','waiting_dependency','waiting_for_dependency'):return None
    try:experiment=int(task.get('experiment'))
    except (TypeError,ValueError):return None
    route=task.get('route')
    allowed={4:{'direct','treatment'},5:{'direct','synthetic'}}
    if route not in allowed.get(experiment,set()):return None
    if any(task.get(k)!=v for k,v in definition.items() if k!='artifact_dir'):return None
    deps=task.get('dependencies')
    if not isinstance(deps,list) or len(deps)!=len(set(deps)):return None
    train_key=task.get('train_key')
    if train_key and train_key not in deps:return None
    if route in ('treatment','synthetic') and not isinstance(train_key,str):return None
    dep_evidence={}
    for key in deps:
        dep=tasks.get(key)
        if not isinstance(dep,dict) or dep.get('status')!='validated_terminal' or dep.get('outcome')!='successful' or dep.get('validation_state')!='validated':return None
        result_path=dep.get('result_path')
        if not isinstance(result_path,str):return None
        rp=pathlib.Path(result_path)
        if not rp.is_absolute() or root not in rp.resolve().parents:return None
        rp=_safe_file(root,rp.relative_to(root))
        try:
            result=json.loads(rp.read_text(encoding='utf-8'))
            if result.get('status')!='successful' or result.get('key')!=key:return None
            validation=result.get('validation')
            if not isinstance(validation,dict) or validation.get('status')!='validated' or validation.get('task_key')!=key:return None
            file_hashes=validation.get('files')
            if not isinstance(file_hashes,dict):return None
            data_sha=None
            if 'data.npz' in file_hashes:
                data_path=_safe_file(root,pathlib.Path('artifacts')/key/'data.npz')
                data_sha=_cached_sha(data_path,file_hashes['data.npz'])
            if key==task.get('train_key') and data_sha is None:return None
            selection_sha=None
            if 'selection.json' in file_hashes:
                selection_sha=_cached_sha(_safe_file(root,pathlib.Path('artifacts')/key/'selection.json'),file_hashes['selection.json'])
            if key==task.get('selection_key') and selection_sha is None:return None
            dep_evidence[key]={'worker_result_sha256':_cached_sha(rp),'data_sha256':data_sha,'selection_sha256':selection_sha}
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return None
    rep=task.get('rep')
    try:rep=int(rep)
    except (TypeError,ValueError):return None
    cache_manifest_path=root/'cache/cache_manifest.json'
    try:
        cache_manifest_path=_safe_file(root,pathlib.Path('cache/cache_manifest.json'))
        cm=json.loads(cache_manifest_path.read_text(encoding='utf-8'))
        expected_role=cm['cache_files'][f'roles/rep_{rep}.npz']
        role_path=_safe_file(root,pathlib.Path('cache/roles')/f'rep_{rep}.npz')
        role_sha=_cached_sha(role_path,expected_role)
        role_meta=cm['roles'][str(rep)]
        e4=json.loads((root/'manifests/E4_MANIFEST.json').read_text(encoding='utf-8'))['role_hashes'][str(rep)]
        e5=json.loads((root/'manifests/E5_MANIFEST.json').read_text(encoding='utf-8'))['role_hashes'][str(rep)]
        if role_meta.get('source_sha256')!=e4.get('source_sha256') or role_meta.get('source_sha256')!=e5.get('source_sha256') or role_meta.get('id_hashes')!=e4.get('id_hashes') or role_meta.get('id_hashes')!=e5.get('id_hashes'):return None
        role_proof={'path':f'cache/roles/rep_{rep}.npz','sha256':role_sha,'role_manifest_sha256':_cached_sha(cache_manifest_path),'source_sha256':role_meta['source_sha256'],'id_hashes':role_meta['id_hashes']}
    except (OSError,ValueError,KeyError,TypeError):return None
    selection_proof=None
    selection_key=task.get('selection_key')
    selection_source=task.get('selection_source')
    if selection_key:
        if selection_key not in deps:return None
        dp=tasks.get(selection_key);rp=pathlib.Path(dp.get('result_path',''))
        try:
            result=json.loads(rp.read_text(encoding='utf-8'))
            expected=result['validation']['files']['selection.json']
            sp=_safe_file(root,pathlib.Path('artifacts')/selection_key/'selection.json')
            selection_proof={'key':selection_key,'sha256':_cached_sha(sp,expected)}
        except (OSError,ValueError,KeyError,TypeError):return None
    elif selection_source:
        sp=pathlib.Path(selection_source)/'selection.json'
        try:
            resolved=sp.resolve(strict=True)
            imported=(root/'manifests/imported_selections').resolve()
            if imported not in resolved.parents:return None
            cur=sp
            while cur!=imported and imported in cur.parents:
                if cur.is_symlink():return None
                cur=cur.parent
            if cur!=imported:return None
            d=json.loads(sp.read_text(encoding='utf-8'))
            if not isinstance(d,dict) or not any(k in d for k in ('selected_params','params')):return None
            selection_proof={'source':str(sp.resolve()),'sha256':_cached_sha(sp)}
        except (OSError,ValueError,TypeError):return None
    key=task.get('key')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',key):return None
    archive_target=(pathlib.PurePosixPath(root.name)/'artifacts'/key/'pipeline.joblib').as_posix()
    try:
        cold_manifest_sha,cold_model_refs=_cold_model_manifest_refs(root)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return None
    if archive_target in cold_model_refs:return None
    artifact_root=root/'artifacts';out=artifact_root/key
    cur=out
    while cur!=artifact_root and artifact_root in cur.parents:
        if cur.is_symlink():return None
        cur=cur.parent
    if cur!=artifact_root or artifact_root.is_symlink():return None
    for path in (out/'pipeline.joblib',out/'fit_result.json',out/'checkpoints'):
        if path.is_symlink() or path.exists():return None
    attempts_dir=out/'attempts'
    if attempts_dir.is_symlink() or attempts_dir.exists():return None
    proof={'schema':'lamost-native-fit-input-proof/1','task_key':task['key'],'experiment':experiment,
           'route':route,'method':task.get('method'),'rep':rep,
           'definition_sha256':_sha256_bytes(json.dumps(definition,sort_keys=True,separators=(',',':'),default=str).encode()),
           'dependency_evidence':dep_evidence,'role_cache':role_proof,'selection':selection_proof,
           'cold_model_manifest_sha256':cold_manifest_sha,'candidate_pipeline_logical_path':archive_target,
           'no_existing_same_task_model_or_checkpoint':True}
    proof['proof_sha256']=_sha256_bytes(json.dumps(proof,sort_keys=True,separators=(',',':'),default=str).encode())
    return proof

def _proc_record(pid, proc_root):
    base=pathlib.Path(proc_root)/str(int(pid))
    statline=(base/'stat').read_text(encoding='utf-8')
    fields=statline[statline.rfind(')')+2:].split()
    status=(base/'status').read_text(encoding='utf-8').splitlines()
    uid=int(next(line.split()[1] for line in status if line.startswith('Uid:')))
    argv=[x.decode(errors='strict') for x in (base/'cmdline').read_bytes().split(b'\0') if x]
    cwd=os.readlink(base/'cwd')
    return {'pid':int(pid),'ppid':int(fields[1]),'pgid':int(fields[2]),'start_ticks':str(fields[19]),
            'uid':uid,'argv':argv,'cwd':cwd}

def _scan_archive_processes(runtime, proc_root):
    runtime=pathlib.Path(runtime).resolve()
    expected={str((runtime/'source'/name).resolve()):name for name in ('cold_auto_compaction.py','run_batch.py','commit_batch_child.py')}
    found=[]; suspicious=[]
    try: entries=list(pathlib.Path(proc_root).iterdir())
    except OSError:return None,True
    for entry in entries:
        if not entry.name.isdigit():continue
        try:record=_proc_record(int(entry.name),proc_root)
        except (OSError,ValueError,StopIteration,IndexError):continue
        argv=record['argv']
        script_index=1 if len(argv)>1 else -1
        if script_index<0:continue
        arg=argv[script_index]
        basename=pathlib.Path(arg).name
        if basename not in ('cold_auto_compaction.py','run_batch.py','commit_batch_child.py'):continue
        resolved=str(pathlib.Path(record['cwd'],arg).resolve()) if not pathlib.Path(arg).is_absolute() else str(pathlib.Path(arg).resolve())
        role=expected.get(resolved)
        if role is None:suspicious.append(record)
        else:found.append((role,record))
    return found,bool(suspicious)

def _sha_safe(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def inspect_runtime(runtime, frozen, *, proc_root='/proc', uid=None):
    root=pathlib.Path(runtime).resolve(); uid=os.getuid() if uid is None else int(uid)
    hold=root/'ADMISSION_HOLD.json'; descriptor=root/'BOUNDED_HELPER.json'
    try: hold_exists=hold.exists() or hold.is_symlink()
    except OSError:return {'mode':'blocked','reason':'hold_stat_failed'}
    processes,suspicious=_scan_archive_processes(root,proc_root)
    if processes is None:return {'mode':'blocked','reason':'proc_unavailable'}
    if suspicious:return {'mode':'blocked','reason':'unrecognized_archive_script_process'}
    if not hold_exists:
        if processes:return {'mode':'blocked','reason':'archive_process_without_hold'}
        return {'mode':'inactive','reason':'no_archive_helper'}
    if hold.is_symlink():return {'mode':'blocked','reason':'hold_symlink'}
    try:hd=_json_regular(hold)
    except (OSError,ValueError,TypeError,json.JSONDecodeError):return {'mode':'blocked','reason':'hold_malformed'}
    if hd.get('owner_operation')!=OWNER_OPERATION or hd.get('batch_policy')!=BATCH_POLICY:
        return {'mode':'blocked','reason':'foreign_or_wrong_policy_hold'}
    opid=hd.get('operation_id');nonce=hd.get('nonce')
    if not isinstance(opid,str) or not re.fullmatch(r'auto_storage_[A-Za-z0-9T_-]+_[0-9a-f]{8}',opid) or not isinstance(nonce,str) or not re.fullmatch(r'[0-9a-f]{32}',nonce):
        return {'mode':'blocked','reason':'hold_identity_malformed'}
    if descriptor.exists() or descriptor.is_symlink():return {'mode':'blocked','reason':'unexpected_helper_descriptor'}
    try:policy=_policy(root,frozen)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {'mode':'blocked','reason':'overlap_policy_invalid'}
    if policy is None:return {'mode':'blocked','reason':'overlap_policy_not_enabled'}
    if hd.get('reason')!='one-shot bounded cold-model archive batch; pause new admissions only':
        return {'mode':'blocked','reason':'hold_reason_mismatch'}
    if len(processes)!=3:return {'mode':'blocked','reason':'helper_process_chain_incomplete'}
    byrole={role:rec for role,rec in processes}
    if set(byrole)!={'cold_auto_compaction.py','run_batch.py','commit_batch_child.py'}:
        return {'mode':'blocked','reason':'helper_process_roles'}
    op=root/'runs'/opid
    if op.is_symlink() or not op.is_dir():return {'mode':'blocked','reason':'operation_directory_missing'}
    for p in (op/'child_result.json',op/'supervisor_result.json',op/'supervisor_exception.json'):
        if p.exists() or p.is_symlink():return {'mode':'blocked','reason':'operation_not_running'}
    private_dir=root/'logs/private/cold_auto_compaction'/opid
    inventory_path=private_dir/'private_process_inventory.json'
    child_path=op/'private_child_identity.json'
    admission_path=op/'private_admission.json'
    try:
        inventory=_json_regular(inventory_path);child=_json_regular(child_path);admission=_json_regular(admission_path)
    except (OSError,ValueError,TypeError,json.JSONDecodeError):return {'mode':'blocked','reason':'private_helper_receipt_missing'}
    driver=byrole['cold_auto_compaction.py'];wrapper=byrole['run_batch.py'];child_proc=byrole['commit_batch_child.py']
    if any(x['uid']!=uid for x in (driver,wrapper,child_proc)):return {'mode':'blocked','reason':'helper_uid_mismatch'}
    if driver['argv'][:2]!=[str(root.parent/'venv/bin/python'),str(root/'source/cold_auto_compaction.py')] or driver['argv'][2:]!=['--archive-io-profile',IO_PROFILE]:
        return {'mode':'blocked','reason':'driver_command_mismatch'}
    if driver['cwd']!=str(root):return {'mode':'blocked','reason':'driver_cwd_mismatch'}
    if inventory.get('operation_id')!=opid or inventory.get('archive_io_profile')!=IO_PROFILE:return {'mode':'blocked','reason':'driver_receipt_mismatch'}
    dr=inventory.get('driver_identity',{});wr=inventory.get('wrapper_identity',{})
    if dr.get('pid')!=driver['pid'] or str(dr.get('process_start_ticks'))!=driver['start_ticks'] or dr.get('source_sha256')!=policy['source_sha256']['cold_auto_compaction.py']:
        return {'mode':'blocked','reason':'driver_receipt_identity_mismatch'}
    if wr.get('pid')!=wrapper['pid'] or str(wr.get('process_start_ticks'))!=wrapper['start_ticks'] or wr.get('pgid')!=wrapper['pgid'] or wr.get('argv')!=wrapper['argv']:
        return {'mode':'blocked','reason':'wrapper_receipt_identity_mismatch'}
    if wrapper['ppid']!=driver['pid'] or wrapper['pgid']!=wrapper['pid'] or wrapper['cwd']!=str(root):
        return {'mode':'blocked','reason':'wrapper_process_tree_mismatch'}
    if wrapper['argv'][:2]!=[str(root.parent/'venv/bin/python'),str(root/'source/run_batch.py')]:
        return {'mode':'blocked','reason':'wrapper_command_mismatch'}
    flags=wrapper['argv'][2:]
    if flags!=['--baseline-sha256',flags[1] if len(flags)>1 else '', '--operation-id',opid,'--batch-policy',BATCH_POLICY,'--archive-io-profile',IO_PROFILE] or not _sha_safe(flags[1] if len(flags)>1 else None):
        return {'mode':'blocked','reason':'wrapper_arguments_mismatch'}
    if child.get('pid')!=child_proc['pid'] or str(child.get('process_start_ticks'))!=child_proc['start_ticks'] or child.get('pgid')!=child_proc['pgid'] or child.get('script')!=str(root/'source/commit_batch_child.py'):
        return {'mode':'blocked','reason':'child_receipt_identity_mismatch'}
    if child_proc['ppid']!=wrapper['pid'] or child_proc['pgid']!=child_proc['pid'] or child_proc['cwd']!=str(root):
        return {'mode':'blocked','reason':'child_process_tree_mismatch'}
    expected_child=[str(root.parent/'venv/bin/python'),str(root/'source/commit_batch_child.py'),
        '--operation-dir',str(op),'--baseline-sha256',flags[1],'--operation-id',opid,
        '--hold-nonce',nonce,'--batch-policy',BATCH_POLICY,'--archive-io-profile',IO_PROFILE]
    if child_proc['argv']!=expected_child:return {'mode':'blocked','reason':'child_command_mismatch'}
    if child.get('address_space_limit_bytes')!=policy['document']['resources']['archive_child_address_space_limit_bytes']:
        return {'mode':'blocked','reason':'child_address_limit_mismatch'}
    if admission.get('batch_policy')!=BATCH_POLICY or admission.get('archive_io_profile')!=IO_PROFILE or admission.get('storage_codec_policy') is not None:
        return {'mode':'blocked','reason':'admission_profile_mismatch'}
    if admission.get('helper_reservation_bytes')!=HELPER_RESERVATION_BYTES or admission.get('policy_host_reserve_bytes')!=6*GIB or admission.get('policy_growth_margin_bytes')!=2*GIB:
        return {'mode':'blocked','reason':'admission_resource_record_mismatch'}
    try:
        for name,digest in policy['source_sha256'].items():
            if _cached_sha(root/'source'/name,digest)!=digest:raise ValueError(name)
        inv_sha=_cached_sha(inventory_path);child_sha=_cached_sha(child_path);admission_sha=_cached_sha(admission_path);hold_sha=_cached_sha(hold)
    except (OSError,ValueError,TypeError):return {'mode':'blocked','reason':'source_or_receipt_mutated'}
    evidence={'operation_id':opid,'hold_nonce_sha256':_sha256_bytes(nonce.encode()),
       'policy_sha256':policy['policy_sha256'],'qualification_sha256':policy['qualification_sha256'],
       'source_sha256':policy['source_sha256'],'native_input_manifests':policy['native_input_manifests'],
       'private_inventory_sha256':inv_sha,'private_child_identity_sha256':child_sha,
       'private_admission_sha256':admission_sha,'hold_sha256':hold_sha,
       'helper_reservation_bytes':HELPER_RESERVATION_BYTES,'helper_cpu_reservation_units':HELPER_CPU_UNITS}
    evidence['context_sha256']=_sha256_bytes(json.dumps(evidence,sort_keys=True,separators=(',',':')).encode())
    return {'mode':'active','reason':'verified_raw_archive_helper','evidence':evidence,
            'operation_id':opid,'_private_processes':[driver,wrapper,child_proc],
            '_private_paths':[inventory_path,child_path,admission_path,hold]}

def helper_tree_pss_bytes(context, proc_root='/proc'):
    if not isinstance(context,dict) or context.get('mode')!='active':return None
    processes=context.get('_private_processes',[])
    if len(processes)!=3:return None
    pids={int(x['pid']) for x in processes}
    try:
        rows={}
        for entry in pathlib.Path(proc_root).iterdir():
            if not entry.name.isdigit():continue
            try:
                rec=_proc_record(int(entry.name),proc_root);rows[rec['pid']]=(rec['ppid'],0)
            except (OSError,ValueError,StopIteration,IndexError):continue
        root_pid=int(processes[0]['pid']);ids={root_pid}
        for _ in range(8):
            more={pid for pid,(ppid,_) in rows.items() if ppid in ids}
            if more<=ids:break
            ids|=more
        if not pids<=ids:return None
        total=0
        for pid in ids:
            lines=(pathlib.Path(proc_root)/str(pid)/'smaps_rollup').read_text().splitlines()
            total+=int(next(x.split()[1] for x in lines if x.startswith('Pss:')))*1024
        return total
    except (OSError,ValueError,StopIteration):return None

def reap_zombie_child(pid, expected_start_ticks, parent_pid, *, proc_root='/proc', waitpid=None):
    """Reap only an exited zombie that is still this controller's verified child."""
    import os
    import pathlib
    if waitpid is None:
        waitpid = os.waitpid
    try:
        pid = int(pid); parent_pid = int(parent_pid)
        base = pathlib.Path(proc_root) / str(pid)
        raw = (base / 'stat').read_text(encoding='utf-8')
        tail = raw[raw.rfind(')') + 2:].split()
        if len(tail) <= 19:
            return False
        state, actual_parent, ticks = tail[0], int(tail[1]), str(tail[19])
        if state not in {'Z', 'X', 'x'} or actual_parent != parent_pid or ticks != str(expected_start_ticks):
            return False
        waited, _status = waitpid(pid, os.WNOHANG)
        return int(waited) == pid
    except (OSError, ValueError, TypeError, IndexError, ChildProcessError):
        return False

def worker_reaper_enabled(frozen, actual_helper_sha256):
    if not isinstance(frozen, dict) or WORKER_REAPER_FIELD not in frozen:
        return False
    declared = frozen.get(WORKER_REAPER_FIELD)
    if not _hex(declared) or declared != actual_helper_sha256:
        raise ValueError('worker_reaper_binding_invalid')
    source_map = frozen.get('source_sha256')
    if not isinstance(source_map, dict) or source_map.get('archive_fit_admission.py') != declared:
        raise ValueError('worker_reaper_source_inventory_mismatch')
    return True

def reap_recorded_zombies(tasks, runtime, parent_pid, *, proc_root='/proc', uid=None, waitpid=None):
    """Reap only recorded worker PIDs still verifiably owned zombie children."""
    import json
    import os
    import pathlib
    if uid is None: uid = os.getuid()
    reaped = []
    root = pathlib.Path(runtime).resolve()
    for task in tasks.values():
        try:
            pid = task.get('pid'); ticks = task.get('process_start_ticks')
            attempts = task.get('attempts')
            if not pid or not ticks or not isinstance(attempts, list) or not attempts: continue
            current = attempts[-1]
            aid = current.get('attempt_id')
            request_value = task.get('request_path')
            if not isinstance(aid, str) or not isinstance(request_value, str): continue
            request = pathlib.Path(request_value)
            if not request.is_absolute() or request.is_symlink() or not request.resolve().is_relative_to(root): continue
            if current.get('request_path') != str(request): continue
            if current.get('result_path') != task.get('result_path'): continue
            cfg = json.loads(request.read_text(encoding='utf-8'))
            definition = cfg.get('task')
            if cfg.get('attempt_id') != aid or not isinstance(definition, dict) or definition.get('key') != task.get('key'): continue
            # A zombie has no usable cwd or command line in /proc. For the
            # reaper path, validate only the kernel identity fields needed to
            # authorize waitpid; active-process admission keeps _proc_record's
            # strict cwd/argv checks unchanged.
            proc = pathlib.Path(proc_root) / str(int(pid))
            raw = (proc / 'stat').read_text(encoding='utf-8')
            fields = raw[raw.rfind(')') + 2:].split()
            if len(fields) <= 19: continue
            state, actual_parent, actual_ticks = fields[0], int(fields[1]), str(fields[19])
            if state not in {'Z', 'X', 'x'} or actual_parent != int(parent_pid) or actual_ticks != str(ticks): continue
            status = (proc / 'status').read_text(encoding='utf-8').splitlines()
            actual_uid = int(next(line.split()[1] for line in status if line.startswith('Uid:')))
            if actual_uid != int(uid): continue
            if not reap_zombie_child(pid, ticks, parent_pid, proc_root=proc_root, waitpid=waitpid): continue
            reaped.append({'key': task.get('key'), 'attempt_id': aid, 'pid': int(pid)})
        except (OSError, ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError):
            continue
    return reaped

def qualify_candidate(runtime, task, definition, tasks, frozen):
    try:
        policy=_policy(runtime,frozen)
        if policy is None:return None
        proof=native_fit_proof(runtime,task,definition,tasks)
        if proof is None:return None
        proof.update({'policy_sha256':policy['policy_sha256'],'qualification_sha256':policy['qualification_sha256'],
                      'source_sha256':policy['source_sha256'],'native_input_manifests':policy['native_input_manifests']})
        proof['proof_sha256']=_sha256_bytes(json.dumps({k:v for k,v in proof.items() if k!='proof_sha256'},sort_keys=True,separators=(',',':'),default=str).encode())
        return proof
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return None
