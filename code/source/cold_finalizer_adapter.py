from __future__ import annotations
import hashlib,io,json,os,pathlib,shutil,tempfile,uuid,zipfile
from contextlib import contextmanager
from pathlib import Path,PurePosixPath

class ColdFinalizerError(RuntimeError): pass

def _cold_source(source):
    return not isinstance(source,(Path,str,bytes,bytearray)) and all(callable(getattr(source,n,None)) for n in ('open','stat','sha256')) and hasattr(source,'logical_path')

def _source_size(source):
    if isinstance(source,bytes): return len(source)
    if _cold_source(source): return int(source.stat()['size'])
    return Path(source).stat().st_size

def _source_sha(source):
    if isinstance(source,bytes): return hashlib.sha256(source).hexdigest()
    if _cold_source(source): return source.stat()['sha256']
    h=hashlib.sha256()
    with Path(source).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def _source_stream(source):
    if isinstance(source,bytes): return io.BytesIO(source)
    if _cold_source(source): raise ColdFinalizerError('cold member source must be deduplicated against its existing ZIP member, not appended as a second payload')
    return Path(source).open('rb')

def _safe_archive_member(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '\\' in name or any(x in ('','.','..') for x in p.parts):raise ColdFinalizerError('unsafe archive member '+name)
    return p.as_posix()

def _cold_manifest_records(store):
    return json.loads(Path(store.manifest).read_text(encoding='utf-8'))

def _registry_pipeline_sha(task):
    result=task.get('result') or {}
    val=result.get('validation') or {}
    if val.get('status')!='validated' or val.get('task_key')!=task.get('key'):return None
    files=val.get('files') or {}; digest=files.get('pipeline.joblib')
    if not isinstance(digest,str) or len(digest)!=64:return None
    nested=(result.get('result') or {}).get('pipeline_sha256')
    if nested and nested!=digest:return None
    return digest

def _review_cold_projection(review_manifest):
    snapshot=review_manifest.get('snapshot') or {}
    inputs=snapshot.get('inputs') or {}
    value=inputs.get('cold_archived_artifact_members')
    if value is None: raise ColdFinalizerError('review candidate lacks cold_archived_artifact_members')
    if not isinstance(value,list):raise ColdFinalizerError('cold archived artifact projection is not a list')
    return value

def _projection_for_entry(row,task,source,requested_path,stat=None):
    st=stat or source.stat();desc=row.get('storage_encoding')
    physical_sha=st.get('member_sha256',st.get('payload_sha256',st.get('sha256')))
    physical_size=int(st.get('member_size',st.get('payload_size',st.get('size',0))))
    physical_crc=int(st.get('member_crc32',st.get('payload_crc32',row.get('crc32',-1))))
    base={'logical_source_path':requested_path,
          'canonical_logical_path':st.get('canonical_logical_path',row.get('logical_path')),
          'resolved_from_alias':bool(st.get('resolved_from_alias',requested_path!=row.get('logical_path'))),
          'task_key':row.get('task_key'),'task_sha256':(task.get('result') or {}).get('task_sha256'),
          'archive_member':st.get('archive_member',row.get('archive_member')),
          'member_sha256':physical_sha,'member_bytes':physical_size,'member_crc32':physical_crc,
          'member_header_offset':int(st.get('header_offset',st.get('member_header_offset',row.get('header_offset',-1)))),
          'source_mtime_ns':int(st.get('mtime_ns',row.get('source_mtime_ns',-1))),
          'aliases':sorted(set(row.get('aliases') or []))}
    if not desc:return base
    base.update({'logical_sha256':st.get('sha256',row.get('sha256')),
       'logical_bytes':int(st.get('size',row.get('bytes',0))),
       'logical_crc32':int(st.get('logical_crc32',row.get('crc32',-1))),
       'storage_format':st.get('storage_format',desc.get('codec_version')),
       'storage_encoding':desc,
       'recipe_sha256':hashlib.sha256(json.dumps({k:v for k,v in desc.items() if k not in {'encoded_sha256','encoded_size_bytes','encoded_crc32'}},sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    return base


def cold_artifact_entries(finalizer,root,runtime,store,registry_records,expected_source_sha256=None,review_manifest=None):
    from cold_model_storage import ZipMemberSource
    root=Path(root).resolve();runtime=Path(runtime).resolve();expected_source_sha256=expected_source_sha256 or {}
    manifest=_cold_manifest_records(store);rows=manifest.get('members',[])
    registry_records=registry_records or {}
    entries={};projection=[];source_stats={};accepted_paths=set();accepted_rows=[]
    if review_manifest is not None:
        accepted=_review_cold_projection(review_manifest)
        for item in accepted:
            if not isinstance(item,dict) or not isinstance(item.get('logical_source_path'),str):
                raise ColdFinalizerError('reviewed cold identity lacks a logical source path')
            req=_safe_archive_member(item['logical_source_path'])
            if req in accepted_paths:raise ColdFinalizerError('review candidate contains a duplicate cold source identity')
            accepted_paths.add(req);accepted_rows.append(item)
    elif rows:
        raise ColdFinalizerError('cold model rows exist but no report-review candidate projection was supplied')
    else:accepted_rows=[]
    for row in sorted(rows,key=lambda r:r.get('logical_path','')):
        task_key=row.get('task_key');task=registry_records.get(task_key)
        logical=row.get('logical_path');digest=row.get('sha256')
        if not task or task.get('status')!='validated_terminal' or finalizer._out(task)!='successful' or task.get('validation_state') not in {'validated','valid','passed','success'}:
            raise ColdFinalizerError('cold model producer is not validated terminal successful: '+str(task_key))
        if row.get('experiment') not in (3,4,5,6) or row.get('method')!='random_forest':
            raise ColdFinalizerError('cold model row outside RF E3-E6 archive scope')
        required=f'runtime_20261025/artifacts/{task_key}/pipeline.joblib'
        if logical!=required or _registry_pipeline_sha(task)!=digest:
            raise ColdFinalizerError('cold model row disagrees with the validated registry pipeline identity: '+str(task_key))
        task_sha=(task.get('result') or {}).get('task_sha256')
        if row.get('task_sha256') and row.get('task_sha256')!=task_sha:
            raise ColdFinalizerError('cold model task SHA differs from terminal registry')
        requested=list(dict.fromkeys([logical]+sorted(set(row.get('aliases') or []))))
        audited={x.get('logical_source_path') for x in accepted_rows if x.get('task_key')==task_key}
        if logical not in audited:raise ColdFinalizerError('review candidate did not audit the canonical cold model path: '+str(logical))
        if not audited.issubset(set(requested)):raise ColdFinalizerError('review candidate audited a path not present in cold alias inventory: '+str(task_key))
        for req in requested:
            req=_safe_archive_member(req)
            if req in entries:raise ColdFinalizerError('duplicate cold logical artifact alias '+req)
            src=ZipMemberSource(store,req,digest)
            st=src.stat();source_stats[req]=st
            if st.get('sha256')!=digest or int(st.get('size',-1))!=int(row.get('bytes',-2)) or st.get('archive_member')!=row.get('archive_member'):
                raise ColdFinalizerError('verified cold member logical identity differs from immutable manifest record')
            desc=row.get('storage_encoding')
            expected_payload_sha=desc.get('encoded_sha256') if isinstance(desc,dict) else digest
            expected_payload_size=int(desc.get('encoded_size_bytes')) if isinstance(desc,dict) else int(row.get('bytes',-1))
            expected_payload_crc=int(desc.get('encoded_crc32')) if isinstance(desc,dict) else int(row.get('crc32',-1))
            if (st.get('payload_sha256',st.get('sha256'))!=expected_payload_sha or
                int(st.get('payload_size',st.get('size',-1)))!=expected_payload_size or
                int(st.get('payload_crc32',st.get('crc32',-1)))!=expected_payload_crc):
                raise ColdFinalizerError('verified cold member physical payload identity differs from immutable manifest record')
            if desc and st.get('storage_format')!=desc.get('codec_version'):
                raise ColdFinalizerError('verified cold member storage format differs from immutable manifest record')
            expected=expected_source_sha256.get(str((root/req).resolve()))
            if expected and expected!=digest:raise finalizer.EvidenceError('reviewed model source SHA differs from cold member '+req)
            entries[req]=finalizer.Entry(src,req,'scientific_models_data_outcomes_trials')
            if req in audited:projection.append(_projection_for_entry(row,task,src,req,st))
    if accepted_paths!={x['logical_source_path'] for x in projection}:
        raise ColdFinalizerError('reviewed cold identities include unmatched or unvalidated artifacts')
    if review_manifest is not None:
        canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        if sorted(map(canon,accepted_rows))!=sorted(map(canon,projection)):
            raise ColdFinalizerError('fresh cold member projection differs from passed report-review candidate')

    snapshot={'schema_version':'lamost-cold-model-membership-snapshot/1','members':projection,
              'curation_note':'Immutable member-level projection only. Mutable archive path, whole-ZIP SHA/size/mtime and central-directory snapshot are intentionally excluded.'}
    payload=(json.dumps(snapshot,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
    return entries,payload

def _hash_zip_member(z,info):
    h=hashlib.sha256();n=0;crc=0
    with z.open(info,'r') as src:
        for b in iter(lambda:src.read(4*1024*1024),b''):
            h.update(b);n+=len(b);crc=zipfile.crc32(b,crc)
    return h.hexdigest(),n,crc&0xffffffff

def existing_member_inventory(store):
    manifest=_cold_manifest_records(store);cold={r['archive_member']:r for r in manifest.get('members',[])}
    rows=[];names=set()
    with zipfile.ZipFile(store.archive,'r',allowZip64=True) as z:
        for info in z.infolist():
            if info.filename in names:raise ColdFinalizerError('duplicate existing ZIP member '+info.filename)
            names.add(info.filename)
            row=cold.get(info.filename)
            if row:
                desc=row.get('storage_encoding')
                if desc:
                    if (info.file_size!=int(desc['encoded_size_bytes']) or info.CRC!=int(desc['encoded_crc32']) or info.header_offset!=int(row['header_offset'])):
                        raise ColdFinalizerError('encoded cold model physical record differs from manifest')
                    physical_sha,n,crc=_hash_zip_member(z,info)
                    if (n,crc,physical_sha)!=(int(desc['encoded_size_bytes']),int(desc['encoded_crc32']),desc['encoded_sha256']):
                        raise ColdFinalizerError('encoded cold model physical bytes fail SHA/size/CRC')
                    digest=row['sha256'];logical_n=int(row['bytes']);category='retained_cold_model'
                    rows.append({'path':info.filename,'bytes':logical_n,'sha256':digest,'category':category,
                        'crc32':int(row['crc32']),'header_offset':int(info.header_offset),
                        'physical_bytes':int(info.file_size),'physical_sha256':physical_sha,'physical_crc32':int(info.CRC),
                        'storage_encoding':desc})
                    continue
                if (info.file_size!=int(row['bytes']) or info.CRC!=int(row['crc32']) or info.header_offset!=int(row['header_offset'])):
                    raise ColdFinalizerError('cold model member record differs from the existing ZIP')
                digest=row['sha256'];category='retained_cold_model'
            else:
                digest,n,crc=_hash_zip_member(z,info)
                if n!=info.file_size or crc!=info.CRC:raise ColdFinalizerError('pre-existing member failed stream CRC/size verification')
                category='preexisting_archive_member'
            rows.append({'path':info.filename,'bytes':int(info.file_size),'sha256':digest,'category':category,'crc32':int(info.CRC),'header_offset':int(info.header_offset),
                'physical_bytes':int(info.file_size),'physical_sha256':digest,'physical_crc32':int(info.CRC)})
    if set(cold)-names:raise ColdFinalizerError('cold manifest references absent ZIP members')
    return rows,names

def _dedup(finalizer,entries,expected_source_sha256,existing):
    physical=[];aliases=[];paths=set();hashes={}
    for row in sorted(existing,key=lambda x:x['path']):
        hashes.setdefault((int(row['bytes']),row['sha256']),row['path'])
    for e in sorted(entries,key=lambda x:x.member):
        member=_safe_archive_member(e.member)
        if member in paths:raise ColdFinalizerError('duplicate requested full-archive member '+member)
        paths.add(member);src=e.source;n=_source_size(src);h=_source_sha(src)
        if _cold_source(src):
            logical=src.logical_path
            source_path=str((src.store.root/logical).resolve())
        else:source_path=None if isinstance(src,bytes) else str(Path(src).resolve())
        expected=(expected_source_sha256 or {}).get(source_path) if source_path else None
        if expected and h!=expected:raise finalizer.EvidenceError('reviewed source changed before full-archive append: '+source_path)
        canonical=hashes.get((n,h))
        if canonical:
            if member!=canonical:aliases.append({'alias_path':member,'canonical_path':canonical,'bytes':n,'sha256':h,'category':e.category})
        else:
            if _cold_source(src):raise ColdFinalizerError('cold model member is absent from the retained archive inventory')
            hashes[(n,h)]=member;physical.append((e,n,h))
    return physical,aliases

def _prepare_append(finalizer,entries,generated,omissions,preexisting,expected_source_sha256,review_proof):
    phys,aliases=_dedup(finalizer,entries,expected_source_sha256,preexisting)
    alias_doc={'schema_version':'lamost-aliases/1','aliases':aliases,'restore':'extract then run python3 restore_archive_aliases.py; hashes verified and output confined to extraction root'}
    alias_bytes=(json.dumps(alias_doc,indent=2,sort_keys=True)+'\n').encode()
    restorer_path=Path(__file__).with_name('restore_archive_aliases_codec_template.py')
    if not restorer_path.is_file():raise ColdFinalizerError('staged codec-aware alias restorer template is missing')
    generated=[*generated,finalizer.Entry(alias_bytes,'archive_aliases.json','alias_manifest'),finalizer.Entry(restorer_path.read_bytes(),'restore_archive_aliases.py','safe_alias_restorer')]
    if review_proof is not None:generated.append(finalizer.Entry((json.dumps(review_proof,indent=2,sort_keys=True)+'\n').encode(),'REPORT_REVIEW_PROOF.json','internal_report_review_proof'))
    gp,ga=_dedup(finalizer,generated,{},[])
    if ga:raise ColdFinalizerError('unexpected duplicate generated full-archive members')
    additions=phys+gp
    allnames=[x[0].member for x in additions]
    if len(set(allnames))!=len(allnames):raise ColdFinalizerError('duplicate appended member name')
    manifest={'schema_version':'lamost-member-manifest/1','created_utc':finalizer.now(),'unique_physical_members':[
        {'path':x['path'],'bytes':int(x.get('physical_bytes',x['bytes'])),'sha256':x.get('physical_sha256',x['sha256']),
         'category':x['category'],'logical_bytes':int(x['bytes']),'logical_sha256':x['sha256'],
         'physical_crc32':int(x.get('physical_crc32',x.get('crc32',-1))),
         **({'storage_encoding':x['storage_encoding']} if x.get('storage_encoding') else {})} for x in preexisting]+[
        {'path':e.member,'bytes':n,'sha256':h,'category':e.category,'logical_bytes':n,'logical_sha256':h,
         'physical_crc32':None} for e,n,h in additions],
        'alias_manifest_sha256':finalizer.sha_bytes(alias_bytes),'alias_count':len(aliases),
        'alias_bytes_elided':sum(x['bytes'] for x in aliases),'omissions':omissions,
        'report_review_proof':review_proof,
        'self_reference':'physical bytes/SHA describe ZIP member stream; logical fields preserve original artifact identity. Manifest covers physical members preceding itself; archive size/SHA/CRC are in external receipt'}
    mb=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    additions.append((finalizer.Entry(mb,'archive_member_manifest.json','member_manifest'),len(mb),finalizer.sha_bytes(mb)))
    if len({e.member for e,_,_ in additions})!=len(additions):raise ColdFinalizerError('archive member collision')
    return additions,aliases,manifest

def _tail_backup(finalizer,path,journal_dir):
    with zipfile.ZipFile(path,'r',allowZip64=True) as z:
        start=int(z.start_dir)
    size=Path(path).stat().st_size
    tail=Path(journal_dir)/'old_central_directory_tail.bin'
    with open(path,'rb') as src,tail.open('xb') as dst:
        src.seek(start);shutil.copyfileobj(src,dst,4*1024*1024);dst.flush();os.fsync(dst.fileno())
    return {'old_size':size,'central_directory_start':start,'tail_path':str(tail),'tail_bytes':tail.stat().st_size,'tail_sha256':finalizer.sha_file(tail)}

def _rollback(finalizer,path,final_path,old_path,old_sha,journal,record):
    path=Path(path);final_path=Path(final_path);old_path=Path(old_path)
    target=final_path if final_path.exists() and not old_path.exists() else old_path
    if target==final_path:os.rename(final_path,old_path);target=old_path
    tail=Path(record['tail_path'])
    if not tail.is_file() or tail.stat().st_size!=int(record['tail_bytes']) or finalizer.sha_file(tail)!=record['tail_sha256']:
        raise ColdFinalizerError('saved old central-directory tail is missing or corrupt')
    with target.open('r+b') as f:
        f.truncate(int(record['central_directory_start']))
        f.seek(int(record['central_directory_start']))
        with tail.open('rb') as src:shutil.copyfileobj(src,f,4*1024*1024)
        f.truncate(int(record['old_size']));f.flush();os.fsync(f.fileno())
    if finalizer.sha_file(target)!=old_sha:raise ColdFinalizerError('rollback failed to restore original cold ZIP bytes')
    with target.open('rb') as f:
        f.seek(int(record['central_directory_start']));actual=f.read()
    if hashlib.sha256(actual).hexdigest()!=record['tail_sha256']:raise ColdFinalizerError('rollback old central-directory tail differs from saved journal')
    with zipfile.ZipFile(target,'r',allowZip64=True) as z:
        if z.testzip() is not None:raise ColdFinalizerError('rollback ZIP failed CRC validation')
    j=finalizer.load(journal);j.update({'state':'rolled_back','rollback_utc':finalizer.now(),'archive_sha256_after_rollback':old_sha});finalizer.atomic_json(journal,j)
    return target

def _validate_existing_full(finalizer,store,review_proof):
    path=Path(store.archive)
    with zipfile.ZipFile(path,'r',allowZip64=True) as z:
        if z.testzip() is not None:raise ColdFinalizerError('existing full archive failed ZIP CRC')
        names=set(z.namelist())
        if not {'archive_member_manifest.json','archive_aliases.json','restore_archive_aliases.py','REPORT_REVIEW_PROOF.json'}.issubset(names):return None
        proof=json.loads(z.read('REPORT_REVIEW_PROOF.json'))
        if proof!=review_proof:raise ColdFinalizerError('existing final archive is bound to a different report-review candidate')
        manifest=json.loads(z.read('archive_member_manifest.json'))
        h=finalizer.sha_file(path);n=path.stat().st_size
        return {'path':str(path),'bytes':n,'sha256':h,'mtime_ns':path.stat().st_mtime_ns,'zip_crc_passed':True,'member_count':len(z.infolist()),'alias_count':manifest.get('alias_count',0),'alias_bytes_elided':manifest.get('alias_bytes_elided',0),'uncompressed_bytes':sum(int(i.file_size) for i in z.infolist()),'member_manifest_sha256':hashlib.sha256(z.read('archive_member_manifest.json')).hexdigest(),'report_review_proof':review_proof}

def recover_uncommitted_renames(finalizer,root,runtime):
    root=Path(root).resolve();runtime=Path(runtime).resolve();journal_root=runtime/'journals'/'full_archive_append'
    if not journal_root.exists():return []
    mod=load_cold_api(runtime);recovered=[]
    for jp in sorted(journal_root.glob('*/append_journal.json')):
        j=finalizer.load(jp)
        if j.get('state') in ('complete','rolled_back','rollback_blocked'):continue
        building=Path(j['building_path']);final=Path(j['final_path']);old_sha=j['archive_sha256_before'];tail=j.get('central_tail_backup')
        if not tail:continue
        manifest_path=runtime/'manifests'/'cold_model_store_manifest.json'
        if not manifest_path.is_file():raise ColdFinalizerError('cold manifest unavailable during append recovery')
        manifest=json.loads(manifest_path.read_text());manifest_archive=manifest.get('archive_path')
        final_rel=final.relative_to(root).as_posix()
        if manifest_archive==final_rel and manifest.get('archive_sha256')==j.get('archive_sha256_after_append'):
            q=finalizer.load(jp);q.update({'state':'complete','recovered_after_manifest_refresh_utc':finalizer.now()});finalizer.atomic_json(jp,q)
            recovered.append({'transaction_id':j['transaction_id'],'state':'manifest_refreshed'});continue
        current=final if final.exists() and not building.exists() else building
        if not current.exists():raise ColdFinalizerError('both BUILDING and final ZIP are missing during append recovery')
        explicit=mod.ColdModelStore(root,runtime,current,manifest_path,runtime/'journals'/'cold_model_store')
        with explicit._write_lock():
            if final.exists() and manifest_archive!=final_rel:
                # Rename intent did not reach the cold manifest; restore the BUILDING locator before truncation.
                if building.exists():raise ColdFinalizerError('both archive paths exist during rename recovery')
                os.rename(final,building);current=building
            if finalizer.sha_file(current)!=old_sha:
                _rollback(finalizer,current,final,building,old_sha,jp,tail)
            else:
                q=finalizer.load(jp);q.update({'state':'rolled_back','rollback_utc':finalizer.now(),'archive_sha256_after_rollback':old_sha});finalizer.atomic_json(jp,q)
            recovered.append({'transaction_id':j['transaction_id'],'state':'rolled_back'})
    return recovered

def load_cold_api(runtime):
    runtime=Path(runtime).resolve()
    adapter_path=Path(__file__).resolve()
    candidates=[runtime/'source'/'cold_model_storage.py',adapter_path.parent/'cold_model_storage.py']
    # Production layout has the installed core beside the adapter. The staging fallback is
    # deliberately available only when this adapter itself lives in its named fixture tree.
    is_engineering_fixture=('cold_finalizer_integration_20261026' in adapter_path.parts and 'staging' in adapter_path.parts)
    selected=next((p for p in candidates if p.exists()),None)
    if selected is None and is_engineering_fixture:
        fallback=runtime/'staging'/'cold_model_storage_20261026'/'source'/'cold_model_storage.py'
        if fallback.exists():selected=fallback
        else:
            paired=adapter_path.parents[2]/'cold_model_storage_20261026'/'source'/'cold_model_storage.py'
            if paired.exists():selected=paired
    if selected is None:
        raise ColdFinalizerError('installed cold model storage API is missing from runtime/source and adapter sibling')
    # Never fall through to staging if an installed candidate exists but is invalid.
    import importlib.util,sys
    module_dir=selected.parent
    if str(module_dir) not in sys.path:sys.path.insert(0,str(module_dir))
    spec=importlib.util.spec_from_file_location('cold_model_storage',selected)
    if spec is None or spec.loader is None:raise ColdFinalizerError('cannot load selected cold model storage API')
    module=importlib.util.module_from_spec(spec);sys.modules['cold_model_storage']=module
    try:spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop('cold_model_storage',None)
        raise ColdFinalizerError(f'selected cold model storage API is invalid: {selected}: {type(exc).__name__}: {exc}') from exc
    if not all(hasattr(module,n) for n in ('ColdModelStore','ZipMemberSource')):
        raise ColdFinalizerError(f'selected cold model storage API has an incompatible interface: {selected}')
    return module

def append_full_archive(finalizer,store,building_path,final_path,entries,generated,omissions,registry_records,expected_archive_sha256,expected_source_sha256,review_proof,min_free=512*1024*1024,_fault_after_members=None):
    building=Path(building_path);final=Path(final_path);runtime=Path(store.runtime);root=Path(store.root)
    if Path(store.archive).resolve()==final.resolve():
        existing=_validate_existing_full(finalizer,store,review_proof)
        if existing:return existing
        raise ColdFinalizerError('final-name ZIP exists without the matching reviewed append manifest')
    if Path(store.archive).resolve()!=building.resolve():raise ColdFinalizerError('cold store locator does not resolve to configured BUILDING archive')
    if building.parent.resolve()!=root/'packages' or 'BUILDING' not in building.name.upper() or building.suffix.lower()!='.zip':
        raise ColdFinalizerError('cold archive must be an explicit ROOT/packages BUILDING ZIP')
    if final.parent.resolve()!=root/'packages' or final.exists() or final.suffix.lower()!='.zip':
        raise ColdFinalizerError('dated final archive path must be a new ZIP under ROOT/packages')
    if not building.is_file():raise ColdFinalizerError('configured BUILDING cold archive is missing')
    prior_sha=finalizer.sha_file(building)
    if expected_archive_sha256 and prior_sha!=expected_archive_sha256:raise ColdFinalizerError('cold archive changed after finalizer snapshot')
    preexisting,oldnames=existing_member_inventory(store)
    additions,aliases,member_manifest=_prepare_append(finalizer,entries,generated,omissions,preexisting,expected_source_sha256,review_proof)
    newnames={e.member for e,_,_ in additions}
    collision=oldnames&newnames
    if collision:raise ColdFinalizerError('refuse duplicate archive member names: '+', '.join(sorted(collision)[:5]))
    needed=sum(n for _,n,_ in additions)+min_free;free=shutil.disk_usage(building.parent).free
    if free<needed:raise finalizer.InsufficientSpace(needed,free)
    journal_root=runtime/'journals'/'full_archive_append';journal_root.mkdir(parents=True,exist_ok=True)
    txid=uuid.uuid4().hex;jdir=journal_root/txid;jdir.mkdir()
    journal=jdir/'append_journal.json'
    guard=None;renamed=False;journal_created=False
    try:
        with store.append_guard(expected_archive_sha256=prior_sha,registry_records=registry_records) as guard:
            current_records=store._records()
            if len(current_records)!=len(oldnames):raise ColdFinalizerError('cold archive member count changed before append')
            current_inventory,current_names=existing_member_inventory(store)
            if current_names!=oldnames or current_inventory!=preexisting:raise ColdFinalizerError('cold archive inventory changed after source verification')
            tail_record=_tail_backup(finalizer,building,jdir)
            j={'schema_version':'lamost-full-archive-append/1','transaction_id':txid,'state':'append_started','candidate_id':review_proof.get('candidate_id'),'report_review_proof':review_proof,'building_path':str(building),'final_path':str(final),'archive_sha256_before':prior_sha,'preexisting_member_count':len(oldnames),'appended_member_names':sorted(newnames),'append_members':[{'member':e.member,'bytes':n,'sha256':h} for e,n,h in additions],'central_tail_backup':tail_record,'created_utc':finalizer.now()}
            finalizer.atomic_json(journal,j);journal_created=True
            with building.open('r+b') as raw:
                with zipfile.ZipFile(raw,'a',allowZip64=True) as z:
                    current_names=set(z.namelist())
                    if current_names!=oldnames:raise ColdFinalizerError('cold archive members changed before append')
                    for ix,(entry,n,h) in enumerate(additions,1):
                        info=zipfile.ZipInfo(entry.member,date_time=(2026,10,26,0,0,0));info.compress_type=finalizer.compression(entry.member);info.external_attr=(0o100644&0xffff)<<16
                        copied=0;digest=hashlib.sha256()
                        with _source_stream(entry.source) as src,z.open(info,'w',force_zip64=True) as dst:
                            for chunk in iter(lambda:src.read(4*1024*1024),b''):
                                copied+=len(chunk);digest.update(chunk);dst.write(chunk)
                        if copied!=n or digest.hexdigest()!=h:raise finalizer.EvidenceError('archive source mutated during append: '+entry.member)
                        if _fault_after_members is not None and ix>=_fault_after_members:raise RuntimeError('injected append interruption')
                raw.flush();os.fsync(raw.fileno())
            with zipfile.ZipFile(building,'r',allowZip64=True) as z:
                if z.testzip() is not None:raise finalizer.EvidenceError('appended archive CRC validation failed')
                if set(z.namelist())!=oldnames|newnames:raise ColdFinalizerError('appended archive member inventory differs from plan')
                for entry,n,h in additions:
                    with z.open(entry.member,'r') as src:
                        sh=hashlib.sha256();count=0
                        for chunk in iter(lambda:src.read(4*1024*1024),b''):sh.update(chunk);count+=len(chunk)
                    if count!=n or sh.hexdigest()!=h:raise finalizer.EvidenceError('appended member SHA/size validation failed: '+entry.member)
                new_records=store._records()
            old_records=json.loads(Path(store.manifest).read_text(encoding='utf-8')).get('zip_records',[])
            if new_records[:len(old_records)]!=old_records:raise ColdFinalizerError('old central-directory records changed during append')
            after_sha=finalizer.sha_file(building);after_bytes=building.stat().st_size
            j=finalizer.load(journal);j.update({'state':'archive_verified','archive_sha256_after_append':after_sha,'archive_bytes_after_append':after_bytes,'zip_member_count_after_append':len(new_records),'zip_crc_passed':True});finalizer.atomic_json(journal,j)
            before_inode=(building.stat().st_dev,building.stat().st_ino)
            os.rename(building,final)
            renamed=True;store.archive=final
            after_inode=(final.stat().st_dev,final.stat().st_ino)
            if before_inode!=after_inode:raise ColdFinalizerError('final archive rename changed inode')
            dfd=os.open(final.parent,os.O_RDONLY);os.fsync(dfd);os.close(dfd)
            j=finalizer.load(journal);j.update({'state':'renamed_before_manifest_refresh','final_archive_sha256':after_sha,'final_archive_bytes':after_bytes,'final_archive_device':after_inode[0],'final_archive_inode':after_inode[1]});finalizer.atomic_json(journal,j)
            updated=guard.refresh_manifest(archive_path=final)
            j=finalizer.load(journal);j.update({'state':'manifest_refreshed','cold_manifest_archive_path':updated.get('archive_path'),'cold_manifest_archive_sha256':updated.get('archive_sha256')});finalizer.atomic_json(journal,j)
            result={'path':str(final),'bytes':after_bytes,'sha256':after_sha,'mtime_ns':final.stat().st_mtime_ns,'zip_crc_passed':True,'member_count':len(new_records),'alias_count':len(aliases),'alias_bytes_elided':sum(x['bytes'] for x in aliases),'uncompressed_bytes':sum(n for _,n,_ in additions)+sum(int(x['bytes']) for x in preexisting),'member_manifest_sha256':hashlib.sha256((json.dumps(member_manifest,indent=2,sort_keys=True)+'\n').encode()).hexdigest(),'report_review_proof':review_proof}
            finalizer.atomic_json(Path(str(final)+'.receipt.json'),result)
            j=finalizer.load(journal);j.update({'state':'complete','result':result,'completed_utc':finalizer.now()});finalizer.atomic_json(journal,j)
        return result
    except Exception:
        try:
            if not journal_created:raise
            current_manifest=json.loads(Path(store.manifest).read_text())
            committed=current_manifest.get('archive_sha256')==finalizer.sha_file(store.archive) and current_manifest.get('archive_path')==Path(store.archive).relative_to(root).as_posix()
            if not committed:
                _rollback(finalizer,building,final,building,prior_sha,journal,tail_record)
                store.archive=building
        except Exception as rollback_error:
            j=finalizer.load(journal);j.update({'state':'rollback_blocked','rollback_error':f'{type(rollback_error).__name__}: {rollback_error}','observed_utc':finalizer.now()});finalizer.atomic_json(journal,j)
            raise ColdFinalizerError('append failure rollback could not be verified; preserved evidence: '+str(rollback_error))
        raise
