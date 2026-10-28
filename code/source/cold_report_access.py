"""Data-only access to validated RF pipeline artifacts, physical or cold-ZIP."""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path, PurePosixPath

class ArtifactIdentityError(RuntimeError): pass

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''): h.update(block)
    return h.hexdigest()

def _safe_task_key(key):
    if not isinstance(key,str) or not key or chr(92) in key:
        raise ArtifactIdentityError('invalid task key')
    p=PurePosixPath(key)
    if p.is_absolute() or any(x in ('','.','..') for x in p.parts):
        raise ArtifactIdentityError('unsafe task key')
    return p.as_posix()

def logical_pipeline_path(runtime, task):
    rt=Path(runtime).resolve()
    key=_safe_task_key(task.get('key'))
    return f'{rt.name}/artifacts/{key}/pipeline.joblib'

def expected_pipeline_sha(task):
    result=task.get('result') or {}
    validation=result.get('validation') or {}
    files=validation.get('files') or {}
    digest=files.get('pipeline.joblib')
    nested=(result.get('result') or {}).get('pipeline_sha256')
    if task.get('kind')!='fit' or task.get('outcome')!='successful':
        raise ArtifactIdentityError('pipeline producer is not a successful fit')
    if task.get('status')!='validated_terminal' or task.get('validation_state')!='validated':
        raise ArtifactIdentityError('pipeline producer is not validated terminal')
    if validation.get('status')!='validated' or validation.get('task_key')!=task.get('key'):
        raise ArtifactIdentityError('pipeline validation identity mismatch')
    if not isinstance(digest,str) or len(digest)!=64:
        raise ArtifactIdentityError('validated pipeline SHA missing')
    if nested and nested!=digest:
        raise ArtifactIdentityError('pipeline SHA fields disagree')
    return digest

def _default_store(runtime, migration_root):
    rt=Path(runtime).resolve()
    manifest=rt/'manifests/cold_model_store_manifest.json'
    if not manifest.is_file(): return None
    doc=json.loads(manifest.read_text(encoding='utf-8'))
    rel=doc.get('archive_path')
    if not isinstance(rel,str): raise ArtifactIdentityError('cold store manifest lacks archive path')
    archive=(Path(migration_root)/rel).resolve()
    try: archive.relative_to(Path(migration_root).resolve())
    except ValueError: raise ArtifactIdentityError('cold archive escapes migration root')
    candidates=[rt/'source/cold_model_storage.py',rt/'staging/cold_model_storage_20261026/source/cold_model_storage.py']
    source=next((x for x in candidates if x.is_file()),None)
    if source is None: raise ArtifactIdentityError('cold store reader module missing')
    spec=importlib.util.spec_from_file_location('_lamost_cold_model_storage',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.ColdModelStore(Path(migration_root),rt,archive,manifest,rt/'journals/cold_model_store')

def _default_extracted_source(runtime, root):
    rt=Path(runtime).resolve()
    projection=rt/'manifests/cold_archived_artifact_members.json'
    if not projection.is_file(): return None
    source=rt/'source/extracted_cold_source.py'
    codec=rt/'source/reversible_joblib_codec.py'
    if not source.is_file() or not codec.is_file():
        raise ArtifactIdentityError('extracted cold resolver or codec source missing')
    try:
        import joblib.compressor as jc
        compressor=Path(jc.__file__).resolve()
    except Exception as e:
        raise ArtifactIdentityError('pinned joblib compressor source is unavailable') from e
    spec=importlib.util.spec_from_file_location('_lamost_extracted_cold_source',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    temp=rt/'cache'
    if not temp.is_dir() or temp.is_symlink():
        raise ArtifactIdentityError('runtime cache is unavailable as bounded codec temp root')
    try:
        return module.ExtractedColdSource(root,rt,temp,codec,compressor,projection)
    except Exception as e:
        raise ArtifactIdentityError('extracted cold membership projection is invalid: '+str(e)) from e

def inspect_pipeline(task, runtime, store=None, extracted_source=None):
    """Return verified availability/provenance only; never deserialize a model."""
    rt=Path(runtime).resolve();root=rt.parent.resolve();key=_safe_task_key(task.get('key'))
    digest=expected_pipeline_sha(task);logical=logical_pipeline_path(rt,task)
    physical=root.joinpath(*PurePosixPath(logical).parts)
    cursor=physical
    while cursor!=root.parent:
        if cursor.is_symlink(): raise ArtifactIdentityError('physical pipeline path contains a symlink')
        if cursor==root: break
        cursor=cursor.parent
    if physical.exists():
        if not physical.is_file(): raise ArtifactIdentityError('physical pipeline is not a regular file')
        got=_sha(physical)
        if got!=digest:
            raise ArtifactIdentityError('present physical pipeline SHA differs from validated identity')
        st=physical.stat()
        return {'available':True,'backing':'physical','logical_path':logical,'sha256':got,
                'size_bytes':st.st_size,'cache_identity':{'backing':'physical','size_bytes':st.st_size,'sha256':got}}
    cold=store if store is not None else _default_store(rt,root)
    if cold is not None:
        try: meta=cold.artifact_stat(logical,digest)
        except FileNotFoundError: meta=None
        if meta is not None:
            if meta.get('sha256')!=digest: raise ArtifactIdentityError('cold model SHA differs from validated identity')
            physical_id={'storage_format':meta.get('storage_format','raw-v1'),
              'member_sha256':meta.get('member_sha256',meta.get('payload_sha256',digest)),
              'member_size_bytes':meta.get('member_size',meta.get('payload_size',meta.get('size'))),
              'member_crc32':meta.get('member_crc32',meta.get('payload_crc32',meta.get('logical_crc32'))),
              'archive_member':meta.get('archive_member'),'header_offset':meta.get('header_offset',meta.get('member_header_offset'))}
            return {'available':True,'backing':meta.get('backing','cold_zip'),'logical_path':logical,
              'sha256':digest,'size_bytes':meta.get('size'),'logical_crc32':meta.get('logical_crc32'),
              'storage_identity':physical_id,'cache_identity':meta.get('cache_identity')}
    extracted=extracted_source if extracted_source is not None else _default_extracted_source(rt,root)
    if extracted is not None:
        try: meta=extracted.stat(logical,digest)
        except FileNotFoundError: meta=None
        except Exception as e: raise ArtifactIdentityError('extracted cold member failed verification: '+str(e)) from e
        if meta is not None:
            return {'available':True,'backing':'cold_extracted','logical_path':logical,'sha256':digest,
                    'size_bytes':meta['size'],'logical_crc32':meta['logical_crc32'],
                    'storage_identity':{'archive_member':meta['archive_member'],'storage_format':meta['storage_format']},
                    'cache_identity':meta['cache_identity']}
    if physical.exists():
        raise ArtifactIdentityError('physical pipeline exists but matches neither validated logical identity nor extracted payload projection')
    return {'available':False,'backing':'missing','logical_path':logical,'sha256':digest,'size_bytes':None,'cache_identity':None}

def fit_reference(task, runtime, fit_tasks, store=None, all_tasks=None):
    tasks=all_tasks or {}
    seen=set()
    def find_fit(rec):
        if not isinstance(rec,dict): return None
        key=rec.get('key')
        if key in seen: return None
        if key: seen.add(key)
        for candidate in (rec.get('fit_key'),rec.get('source_key')):
            if candidate in fit_tasks: return fit_tasks[candidate]
        result=rec.get('result') or {}
        for candidate in (result.get('fit_key'),result.get('source_key')):
            if candidate in fit_tasks: return fit_tasks[candidate]
        for candidate in (rec.get('members') or {}).values():
            if candidate in fit_tasks: return fit_tasks[candidate]
        refs=list(rec.get('dependencies') or [])
        refs.extend((rec.get('member_evaluations') or {}).values())
        for ref in refs:
            if ref in fit_tasks: return fit_tasks[ref]
        for ref in refs:
            child=tasks.get(ref)
            found=find_fit(child)
            if found: return found
        return None
    fit=find_fit(task)
    if not fit:
        return {'pipeline_available':False,'pipeline_backing':'unavailable_dependency','pipeline_logical_path':'','pipeline_sha256':''}
    x=inspect_pipeline(fit,runtime,store)
    return {'pipeline_available':x['available'],'pipeline_backing':x['backing'],
            'pipeline_logical_path':x['logical_path'],'pipeline_sha256':x['sha256'],
            'pipeline_size_bytes':x['size_bytes'],
            'pipeline_cache_identity':json.dumps(x['cache_identity'],sort_keys=True) if x['cache_identity'] else ''}
