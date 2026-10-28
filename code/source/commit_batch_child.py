from pathlib import Path
import argparse, datetime, hashlib, json, sqlite3, stat, sys, time, zipfile
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023'); R=ROOT/'runtime_20261025'; D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cold_model_storage as cold
from batch_plan import build_candidates, select_batch, public_candidate_summary, require_reviewed_baseline, validate_operation_directory, verify_alias_resolution, MAX_INITIAL_BYTES, MAX_INITIAL_GROUPS, MAX_LATER_BYTES, MAX_LATER_GROUPS, RAW_WIDE_MAX_BYTES, RAW_WIDE_MAX_GROUPS, RAW_WIDE_PROFILE, RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES, RAW_MIXED_SMALL_MAX_BYTES, RAW_MIXED_SMALL_MAX_GROUPS, RAW_MIXED_SMALL_PROFILE, RAW_MIXED_SMALL_TRANSIENT_DISK_RESERVE_BYTES
PINS={'cold_model_storage.py': '889a4083ca575fc7afa1f4bedd240c3f59a912c41549098cbd920a4a5ff543ec', 'cold_codec_storage.py': '9318ee513b923ff1c959e989569fe24549f11f6eb6d0b338cae390e3651cb76c', 'reversible_joblib_codec.py': '189b5ab887f47931638cf65aa183239ce077931de0673fc690fcf2c1c86355ca', 'cold_storage_safety.py': '7dff7f8dc256f8252d41b6fd370b7624bfe8841fa7c5c13dbe86747ccc456273', 'controller.py': 'db792edc3d855a5c052c0c2408bd56d292efa2e9051f27d89237571c874c78ae', 'batch_plan.py': 'a46eea100f5046eaf6166f01b0ee8ecf21999d928fb4c38dc54f217a65f82c7b', 'archive_fit_admission.py': 'ad54590034b336482efc91f4960ac20474923e18ac317b197d02ebeb2f331030', 'metadata_only_contract.py': '1d4e9f78bf3b0062effb3bc218fb5135aae0dba2375b2602773d21bf49d333a1', 'admission_evidence.py': 'f2369fb24c39dde7241f12f6cb7831358168897a76810809d3f72cc351dc86b9'}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return cold.sha256_file(p)
def snapshot():
    db=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True)
    db.execute('PRAGMA query_only=ON')
    mem=sqlite3.connect(':memory:')
    db.backup(mem); db.close()
    rec={x['key']:x for (s,) in mem.execute('select record from tasks') for x in [json.loads(s)]}
    mem.close(); return rec

CODEC_FOLLOWUP_MAX_BYTES=1<<30
CODEC_FOLLOWUP_MAX_GROUPS=1
ARCHIVE_IO_PROFILE='bounded-1800'
RAW_WIDE_PROFILE='bounded-1800-wide8gib'
ARCHIVE_IO_PROFILES=(ARCHIVE_IO_PROFILE,RAW_WIDE_PROFILE,RAW_MIXED_SMALL_PROFILE)
ARCHIVE_IO_WALL_SECONDS=1800
POLICIES={"initial":{"max_bytes":MAX_INITIAL_BYTES,"max_groups":MAX_INITIAL_GROUPS,"wall_seconds":180,"packing":"smallest_first","storage_codec_policy":None,"transient_disk_reserve_bytes":0},"storage-followup":{"max_bytes":MAX_LATER_BYTES,"max_groups":MAX_LATER_GROUPS,"wall_seconds":600,"packing":"largest_first","storage_codec_policy":None,"transient_disk_reserve_bytes":0},"storage-followup-codec":{"max_bytes":CODEC_FOLLOWUP_MAX_BYTES,"max_groups":CODEC_FOLLOWUP_MAX_GROUPS,"wall_seconds":600,"packing":"largest_first","storage_codec_policy":"reversible-xz-v1","transient_disk_reserve_bytes":0}}
def validate_storage_policy(batch_policy,storage_codec_policy,archive_io_profile=None):
    if batch_policy not in POLICIES: raise ValueError('unknown batch policy')
    expected=POLICIES[batch_policy]['storage_codec_policy']
    if storage_codec_policy!=expected: raise ValueError('batch/storage codec policy mismatch')
    if archive_io_profile is None:return POLICIES[batch_policy]
    if archive_io_profile not in ARCHIVE_IO_PROFILES:raise ValueError('unknown archive I/O profile')
    if batch_policy!='storage-followup' or storage_codec_policy is not None:
        raise ValueError('bounded archive I/O profiles are only valid for raw storage-followup')
    policy=dict(POLICIES[batch_policy]);policy['wall_seconds']=ARCHIVE_IO_WALL_SECONDS
    policy['archive_io_profile']=archive_io_profile
    if archive_io_profile==RAW_WIDE_PROFILE:
        policy.update({'max_bytes':RAW_WIDE_MAX_BYTES,'max_groups':RAW_WIDE_MAX_GROUPS,'transient_disk_reserve_bytes':RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES})
    elif archive_io_profile==RAW_MIXED_SMALL_PROFILE:
        policy.update({'max_bytes':RAW_MIXED_SMALL_MAX_BYTES,'max_groups':RAW_MIXED_SMALL_MAX_GROUPS,'transient_disk_reserve_bytes':RAW_MIXED_SMALL_TRANSIENT_DISK_RESERVE_BYTES})
    return policy

def _preflight_publication_receipt_files(owner,alias,store):
    key=owner.get('key');result=owner.get('result') or {};attempt_id=result.get('attempt_id');task_sha=result.get('task_sha256')
    base=f'runtime_20261025/artifacts/{key}'
    canonical=f'{base}/pipeline.joblib'
    if alias==canonical:return
    if isinstance(attempt_id,str) and attempt_id and alias==f'{base}/attempts/{attempt_id}/pipeline.joblib':
        rels=[f'{base}/fit_publication.json',f'{base}/fit_result.json',f'{base}/selection.json',
              f'{base}/attempts/{attempt_id}/fit_publication.json',f'{base}/attempts/{attempt_id}/attempt.json',
              f'{base}/attempts/{attempt_id}/selection.json']
    elif isinstance(task_sha,str) and len(task_sha)==64 and alias==f'{base}/checkpoints/{task_sha}/pipeline.joblib':
        rels=[f'{base}/fit_publication.json',f'{base}/fit_result.json',f'{base}/selection.json',
              f'{base}/checkpoints/{task_sha}/selection.json']
    else:
        return
    for rel in rels:
        path=store._physical_path(rel)
        try:info=path.lstat()
        except FileNotFoundError as exc:raise cold.AmbiguousState('publication receipt file missing: '+rel) from exc
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise cold.UnsafePlan('publication receipt is not a regular owned file: '+rel)
        if rel.endswith('/fit_publication.json') or rel.endswith('/fit_result.json'):
            try:doc=json.loads(path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:raise
            if not isinstance(doc,dict):raise cold.UnsafePlan('publication receipt JSON root is not an object: '+rel)
            if rel.endswith('/fit_result.json') and not isinstance(doc.get('result'),dict):
                raise cold.UnsafePlan('fit-result nested result is not an object: '+rel)

def filter_candidate_publication_aliases(items,records,store):
    # Import the private owner resolver only when this new path runs so older test stubs remain compatible.
    from batch_plan import _alias_owner
    eligible=[]; exclusions=[]
    for item in items:
        try:
            digest=item.get('recorded_artifact_sha256') or item.get('source_sha256')
            aliases=item.get('aliases')
            if not isinstance(aliases,list) or not aliases:
                raise cold.UnsafePlan('candidate group has no complete alias list')
            for alias in aliases:
                owner_key=_alias_owner(alias,records)
                if owner_key is None:
                    raise cold.UnsafePlan('candidate alias has no unambiguous validated owner: '+str(alias))
                owner=records.get(owner_key)
                if owner is None:
                    raise cold.UnsafePlan('candidate alias owner is absent from registry: '+str(owner_key))
                _preflight_publication_receipt_files(owner,alias,store)
                store._alias_publication_evidence(owner,alias,digest)
        except (cold.AmbiguousState,cold.UnsafePlan,json.JSONDecodeError) as exc:
            exclusions.append({'producer_task':item.get('producer_task'),'source_relpath':item.get('source_relpath'),
                'source_sha256':item.get('source_sha256'),'aliases':list(item.get('aliases') or []),
                'reason_type':type(exc).__name__,'reason':str(exc)[:1000]})
            continue
        eligible.append(item)
    receipt={'schema':'cold-candidate-publication-filter/1','input_group_count':len(items),
        'eligible_group_count':len(eligible),'excluded_group_count':len(exclusions),
        'exclusions':exclusions}
    return eligible,receipt

def _adopt_verified_core_cache(store,store2,j):
    """Copy the creator's digest/index receipt only for the identical archive identity."""
    cached=getattr(store,'_archive_identity_cache',None)
    if not (cached and getattr(store,'root',None)==getattr(store2,'root',None)
        and getattr(store,'archive',None)==getattr(store2,'archive',None)
        and getattr(store,'manifest',None)==getattr(store2,'manifest',None)
        and cached.get('sha256')==j.get('archive_sha256_after')
        and cached.get('zip_records')==j.get('member_records_after')):
        return False
    try:
        st=store2.archive.stat()
        identity=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    except OSError:
        return False
    if cached.get('identity')!=identity:return False
    store2._archive_identity_cache=dict(cached)
    return True

def _bind_completed_core_payload_evidence(root,store,tx,batch,baseline):
    """Bind child receipt to the core's already-completed byte verification.

    commit_models() returns only after the pinned core has verified appended
    physical bytes, exact logical bytes (including codec round-trips), manifest,
    and alias removal. Reuse the exact-identity digest cache where available;
    otherwise _check_archive_manifest performs a fresh digest. ZIP index and
    transaction bindings are still checked below.
    """
    jp=store.journals/tx/'journal.json';j=json.loads(jp.read_text())
    if j.get('transaction_id')!=tx or j.get('state')!='complete' or j.get('archive_sha256_before')!=baseline or j.get('storage_codec_policy')!=store.storage_codec_policy:
        raise RuntimeError('completed transaction identity/policy mismatch')
    if j.get('codec_verifier_source_sha256')!=cold._IMPORTED_SOURCE_SHA256:
        raise RuntimeError('completed transaction verifier source pin mismatch')
    archive=store.archive
    expected_archive_rel=archive.relative_to(root).as_posix()
    if j.get('archive_relpath')!=expected_archive_rel:
        raise RuntimeError('completed transaction archive path differs from active store')
    if archive.is_symlink() or not archive.is_file(): raise RuntimeError('committed archive is not a regular file')
    st0=archive.stat()
    if (st0.st_dev,st0.st_ino)!=(j.get('archive_device'),j.get('archive_inode')) or st0.st_size!=j.get('archive_bytes_after'):
        raise RuntimeError('committed archive inode/size differs from transaction receipt')
    m=cold._manifest_load(store.manifest)
    cache_identity=(st0.st_dev,st0.st_ino,st0.st_size,st0.st_mtime_ns,st0.st_ctime_ns)
    cache=getattr(store,'_archive_identity_cache',None)
    digest_cache_hit=bool(cache and cache.get('identity')==cache_identity)
    actual_sha,checked_stat,checked_records=store._check_archive_manifest(m)
    if actual_sha!=j.get('archive_sha256_after'):
        raise RuntimeError('post-commit archive SHA differs from core transaction receipt')
    if (checked_stat.st_dev,checked_stat.st_ino,checked_stat.st_size,checked_stat.st_mtime_ns,checked_stat.st_ctime_ns)!=cache_identity:
        raise RuntimeError('archive identity changed during committed manifest check')
    if store.manifest.is_symlink() or not store.manifest.is_file(): raise RuntimeError('committed manifest is not a regular file')
    if j.get('archive_sha256_after') is None or j.get('manifest_sha256') is None:
        raise RuntimeError('completed transaction lacks archive/manifest identity receipts')
    if cold.sha256_file(store.manifest)!=j.get('manifest_sha256'):
        raise RuntimeError('committed manifest bytes differ from transaction receipt')
    m=cold._manifest_load(store.manifest)
    if m.get('archive_path')!=expected_archive_rel or m.get('transaction_id')!=tx or m.get('archive_sha256')!=j.get('archive_sha256_after') or m.get('archive_bytes')!=j.get('archive_bytes_after') or m.get('zip_records')!=j.get('member_records_after'):
        raise RuntimeError('committed manifest does not bind completed transaction')
    with zipfile.ZipFile(archive,'r',allowZip64=True) as z:
        records=cold._zip_records_all(z)
    st1=archive.stat()
    if (st0.st_dev,st0.st_ino,st0.st_size,st0.st_mtime_ns,st0.st_ctime_ns)!=(st1.st_dev,st1.st_ino,st1.st_size,st1.st_mtime_ns,st1.st_ctime_ns):
        raise RuntimeError('archive changed while reading committed ZIP index')
    if records!=j.get('member_records_after'):
        raise RuntimeError('committed ZIP index differs from core transaction receipt')
    planned={x.get('source_relpath'):x for x in batch}
    rows={x.get('logical_path'):x for x in m.get('members',[])}
    infos={x['member']:x for x in records}
    out=[];encoded=raw_fallback=logical_bytes=physical_bytes=0
    digest_basis='verified_identity_cache' if digest_cache_hit else 'fresh_manifest_digest_fallback'
    for item in j.get('items',[]):
        path=item['logical_path']; row=rows.get(path); info=infos.get(item.get('archive_member')); plan=planned.get(item.get('source_relpath'))
        if not row or not info or not plan: raise RuntimeError('committed transaction item missing from plan/manifest/index')
        if (plan.get('recorded_artifact_sha256'),plan.get('bytes'),plan.get('aliases'))!=(item.get('sha256'),item.get('bytes'),item.get('aliases')):
            raise RuntimeError('completed transaction item differs from selected batch')
        if row.get('sha256')!=item.get('sha256') or row.get('bytes')!=item.get('bytes') or row.get('crc32')!=item.get('crc32') or row.get('storage_encoding')!=item.get('storage_encoding') or row.get('transaction_id')!=tx:
            raise RuntimeError('committed logical/physical manifest row mismatch')
        if info.get('compress_type')!=zipfile.ZIP_STORED or info.get('header_offset')!=item.get('header_offset'):
            raise RuntimeError('committed member ZIP record mismatch')
        desc=item.get('storage_encoding')
        if desc:
            if not store.storage_codec_policy or info.get('file_size')!=desc.get('encoded_size_bytes') or info.get('crc32')!=desc.get('encoded_crc32') or item.get('storage_decision',{}).get('selected')!=desc.get('codec_version'):
                raise RuntimeError('encoded payload descriptor/decision mismatch')
            proof=item.get('logical_verification')
            expected={'protocol':cold._CODEC_PROOF_PROTOCOL,'verifier_source_sha256':cold._IMPORTED_SOURCE_SHA256,'logical_sha256':item['sha256'],'logical_bytes':int(item['bytes']),'logical_crc32':int(item['crc32']),'storage_descriptor_sha256':cold._sha_bytes(json.dumps(desc,sort_keys=True,separators=(',',':')).encode())}
            if proof!=expected or not store._has_completed_logical_verification(row):
                raise RuntimeError('encoded logical bytes lack completed core verification proof')
            physical_sha=desc['encoded_sha256']; physical_size=int(desc['encoded_size_bytes']); physical_crc=int(desc['encoded_crc32']); fmt=desc['codec_version']; encoded+=1
        else:
            decision=item.get('storage_decision')
            if store.storage_codec_policy and (not isinstance(decision,dict) or decision.get('selected')!='raw-v1' or not decision.get('reason')):
                raise RuntimeError('encoded-policy raw fallback lacks explicit reason')
            if item.get('storage_codec_policy') not in (None,store.storage_codec_policy) or info.get('file_size')!=item['bytes'] or info.get('crc32')!=item['crc32']:
                raise RuntimeError('raw payload descriptor/policy mismatch')
            if store.storage_codec_policy: raw_fallback+=1
            physical_sha=item['sha256']; physical_size=int(item['bytes']); physical_crc=int(item['crc32']); fmt='raw-v1'
        aliases=item.get('aliases')
        if not isinstance(aliases,list) or len(aliases)!=len(set(aliases)) or path not in aliases or row.get('aliases')!=aliases:
            raise RuntimeError('completed transaction alias inventory mismatch')
        for alias in aliases:
            physical=Path(root)/alias
            if physical.exists() or physical.is_symlink(): raise RuntimeError('post-commit physical alias remains: '+alias)
            resolved=store._member_entry(m,alias)
            if not resolved or resolved.get('canonical_logical_path')!=path or resolved.get('resolved_from_alias')!=(alias!=path):
                raise RuntimeError('committed alias does not resolve to its canonical manifest row: '+alias)
        logical_bytes+=int(item['bytes']);physical_bytes+=physical_size
        out.append({'logical_path':path,'logical_sha256':item['sha256'],'logical_bytes':int(item['bytes']),'logical_crc32':int(item['crc32']),'storage_format':fmt,'physical_sha256':physical_sha,'physical_bytes':physical_size,'physical_crc32':physical_crc,'verification_basis':'pinned_core_complete_transaction'})
    if len(planned)!=len(out): raise RuntimeError('batch and completed transaction item counts differ')
    delta=int(j['archive_bytes_after'])-int(j['archive_size_before'])
    if delta<physical_bytes: raise RuntimeError('archive size delta smaller than appended payload bytes')
    return {'codec_policy':store.storage_codec_policy,'model_count':len(out),'encoded_model_count':encoded,'raw_fallback_count':raw_fallback,'logical_source_bytes':logical_bytes,'physical_payload_bytes':physical_bytes,'archive_bytes_delta':delta,'exact_logical_verifications':out,'verification_basis':'pinned_core_complete_transaction_journal','archive_digest_basis':digest_basis}

def _verify_completed_alias_metadata(root,store,items,tx,storage_evidence):
    """Metadata-only alias binding; payload bytes were verified by the core."""
    jp=store.journals/tx/'journal.json';j=json.loads(jp.read_text())
    if j.get('transaction_id')!=tx or j.get('state')!='complete': raise RuntimeError('alias verification requires completed creator transaction')
    manifest=cold._manifest_load(store.manifest)
    if manifest.get('transaction_id')!=tx: raise RuntimeError('alias manifest is not bound to creator transaction')
    rows={x.get('logical_path'):x for x in manifest.get('members',[])}
    proofs={x.get('logical_path'):x for x in storage_evidence.get('exact_logical_verifications',[])}
    for item in items:
        canonical=item['logical_path']; row=rows.get(canonical); proof=proofs.get(canonical); desc=item.get('storage_encoding')
        if not row or row.get('transaction_id')!=tx or row.get('aliases')!=item.get('aliases') or row.get('sha256')!=item.get('sha256'):
            raise RuntimeError('alias manifest identity mismatch')
        for alias in item['aliases']:
            physical=Path(root)/alias
            if physical.exists() or physical.is_symlink(): raise RuntimeError('post-commit physical alias remains: '+alias)
            resolved=store._member_entry(manifest,alias)
            if not resolved or resolved.get('canonical_logical_path')!=canonical or resolved.get('resolved_from_alias')!=(alias!=canonical):
                raise RuntimeError('alias resolution metadata mismatch: '+alias)
        if desc:
            expected={'protocol':cold._CODEC_PROOF_PROTOCOL,'verifier_source_sha256':cold._IMPORTED_SOURCE_SHA256,'logical_sha256':item['sha256'],'logical_bytes':int(item['bytes']),'logical_crc32':int(item['crc32']),'storage_descriptor_sha256':cold._sha_bytes(json.dumps(desc,sort_keys=True,separators=(',',':')).encode())}
            if item.get('logical_verification')!=expected or not proof or (proof.get('logical_sha256'),proof.get('logical_bytes'),proof.get('logical_crc32'),proof.get('storage_format'),proof.get('physical_sha256'),proof.get('physical_bytes'),proof.get('physical_crc32'))!=(item['sha256'],item['bytes'],item['crc32'],desc.get('codec_version'),desc.get('encoded_sha256'),desc.get('encoded_size_bytes'),desc.get('encoded_crc32')) or not store._has_completed_logical_verification(row):
                raise RuntimeError('encoded alias lacks completed core logical proof')
        elif row.get('crc32')!=item.get('crc32') or row.get('bytes')!=item.get('bytes'):
            raise RuntimeError('raw alias row identity mismatch')

def _verify_batch_payloads(root,store,tx,batch,baseline):
    jp=store.journals/tx/'journal.json';j=json.loads(jp.read_text())
    if j.get('state')!='complete' or j.get('archive_sha256_before')!=baseline or j.get('storage_codec_policy')!=store.storage_codec_policy:
        raise RuntimeError('completed transaction identity/policy mismatch')
    m=cold._manifest_load(store.manifest)
    if m.get('transaction_id')!=tx or m.get('archive_sha256')!=j.get('archive_sha256_after') or m.get('archive_bytes')!=j.get('archive_bytes_after'):
        raise RuntimeError('committed manifest does not bind transaction')
    bylogical={x.get('logical_path'):x for x in m.get('members',[])}
    rows=[];encoded=raw_fallback=0;logical_bytes=physical_bytes=0
    with zipfile.ZipFile(store.archive,'r',allowZip64=True) as z:
        infos={i.filename:i for i in z.infolist()}
        for item in j.get('items',[]):
            path=item['logical_path'];row=bylogical.get(path);info=infos.get(item.get('archive_member'))
            if not row or not info or row.get('sha256')!=item.get('sha256') or row.get('bytes')!=item.get('bytes') or row.get('crc32')!=item.get('crc32') or row.get('storage_encoding')!=item.get('storage_encoding'):
                raise RuntimeError('committed logical/physical manifest row mismatch')
            if info.compress_type!=zipfile.ZIP_STORED or info.header_offset!=item.get('header_offset'):
                raise RuntimeError('committed member ZIP record mismatch')
            desc=item.get('storage_encoding')
            if desc:
                if not store.storage_codec_policy:raise RuntimeError('encoded payload appeared under raw storage policy')
                if info.file_size!=desc.get('encoded_size_bytes') or info.CRC!=desc.get('encoded_crc32') or item.get('storage_decision',{}).get('selected')!=desc.get('codec_version'):
                    raise RuntimeError('encoded payload descriptor/decision mismatch')
                encoded+=1;physical_bytes+=int(desc['encoded_size_bytes'])
            else:
                decision=item.get('storage_decision')
                if store.storage_codec_policy and (not isinstance(decision,dict) or decision.get('selected')!='raw-v1' or not decision.get('reason')):
                    raise RuntimeError('encoded-policy raw fallback lacks explicit reason')
                if item.get('storage_codec_policy') not in (None,store.storage_codec_policy):raise RuntimeError('item codec policy mismatch')
                if store.storage_codec_policy:raw_fallback+=1
                if info.file_size!=item['bytes'] or info.CRC!=item['crc32']:raise RuntimeError('raw payload descriptor mismatch')
                physical_bytes+=int(item['bytes'])
            with z.open(info,'r') as f:
                ph,pn,pc=cold._stream_hash(f)
            if desc and (ph,pn,pc)!=(desc.get('encoded_sha256'),desc.get('encoded_size_bytes'),desc.get('encoded_crc32')):
                raise RuntimeError('encoded ZIP payload hash/size/CRC mismatch')
            if not desc and (ph,pn,pc)!=(item['sha256'],item['bytes'],item['crc32']):
                raise RuntimeError('raw ZIP payload hash/size/CRC mismatch')
            with store.open_verified(path,item['sha256']) as f:
                lh,ln,lc=cold._stream_hash(f)
            if (lh,ln,lc)!=(item['sha256'],item['bytes'],item['crc32']):raise RuntimeError('logical restored bytes differ from source identity')
            logical_bytes+=int(item['bytes'])
            rows.append({'logical_path':path,'logical_sha256':lh,'logical_bytes':ln,'logical_crc32':lc,'storage_format':desc.get('codec_version') if desc else 'raw-v1','physical_sha256':ph,'physical_bytes':pn,'physical_crc32':pc})
    delta=int(j['archive_bytes_after'])-int(j['archive_size_before'])
    if delta<physical_bytes:raise RuntimeError('archive size delta smaller than appended payload bytes')
    return {'codec_policy':store.storage_codec_policy,'model_count':len(rows),'encoded_model_count':encoded,'raw_fallback_count':raw_fallback,'logical_source_bytes':logical_bytes,'physical_payload_bytes':physical_bytes,'archive_bytes_delta':delta,'exact_logical_verifications':rows}

def verify_encoded_alias_resolution(root,store,items,tx,storage_evidence):
    """Verify encoded aliases by shared physical identity after one canonical logical read."""
    jp=store.journals/tx/'journal.json';j=json.loads(jp.read_text())
    if j.get('transaction_id')!=tx or j.get('state')!='complete':raise RuntimeError('encoded alias verification requires completed creator transaction')
    manifest=cold._manifest_load(store.manifest)
    if manifest.get('transaction_id')!=tx:raise RuntimeError('encoded alias manifest is not bound to creator transaction')
    rows={x.get('logical_path'):x for x in manifest.get('members',[])}
    proofs={x.get('logical_path'):x for x in storage_evidence.get('exact_logical_verifications',[])}
    compare=('canonical_logical_path','size','mtime_ns','sha256','logical_crc32','backing','archive_path','archive_sha256','archive_size_bytes','archive_mtime_ns','archive_ctime_ns','archive_member','member_crc32','member_header_offset','member_size','member_sha256','storage_format','payload_crc32','payload_size','payload_sha256','storage_encoding','cache_identity')
    for item in items:
        expected=item['sha256'];canonical=item['logical_path'];desc=item.get('storage_encoding')
        aliases=item.get('aliases')
        if not isinstance(aliases,list) or len(aliases)!=len(set(aliases)) or canonical not in aliases:raise RuntimeError('creator alias inventory is invalid')
        if not desc:
            for alias in aliases:
                physical=Path(root)/alias
                if physical.exists() or physical.is_symlink():raise RuntimeError('post-commit physical alias remains: '+alias)
                if store.sha256(alias,expected_sha256=expected)!=expected:raise RuntimeError('post-commit raw alias SHA mismatch: '+alias)
            continue
        row=rows.get(canonical);proof=proofs.get(canonical)
        if not row or row.get('storage_encoding')!=desc or row.get('transaction_id')!=tx:raise RuntimeError('encoded manifest row lacks exact creator identity')
        if not proof or (proof.get('logical_sha256'),proof.get('logical_bytes'),proof.get('logical_crc32'),proof.get('storage_format'),proof.get('physical_sha256'),proof.get('physical_bytes'),proof.get('physical_crc32'))!=(item['sha256'],item['bytes'],item['crc32'],desc.get('codec_version'),desc.get('encoded_sha256'),desc.get('encoded_size_bytes'),desc.get('encoded_crc32')):
            raise RuntimeError('canonical full logical verification evidence is missing or inconsistent')
        expected_proof={'protocol':cold._CODEC_PROOF_PROTOCOL,'verifier_source_sha256':cold._IMPORTED_SOURCE_SHA256,'logical_sha256':item['sha256'],'logical_bytes':int(item['bytes']),'logical_crc32':int(item['crc32']),'storage_descriptor_sha256':cold._sha_bytes(json.dumps(desc,sort_keys=True,separators=(',',':')).encode())}
        if item.get('logical_verification')!=expected_proof or not store._has_completed_logical_verification(row):
            raise RuntimeError('encoded aliases lack a valid completed core logical-verification proof')
        canonical_stat=store.artifact_stat(canonical,expected_sha256=expected)
        if canonical_stat.get('resolved_from_alias') is not False or canonical_stat.get('archive_member')!=item.get('archive_member') or canonical_stat.get('member_header_offset')!=item.get('header_offset'):
            raise RuntimeError('canonical encoded stat identity mismatch')
        if canonical_stat.get('sha256')!=item['sha256'] or canonical_stat.get('size')!=item['bytes'] or canonical_stat.get('logical_crc32')!=item['crc32'] or canonical_stat.get('storage_encoding')!=desc:
            raise RuntimeError('canonical encoded logical/recipe metadata mismatch')
        for alias in aliases:
            physical=Path(root)/alias
            if physical.exists() or physical.is_symlink():raise RuntimeError('post-commit physical alias remains: '+alias)
            if alias==canonical:continue
            stat=store.artifact_stat(alias,expected_sha256=expected)
            if stat.get('resolved_from_alias')!=(alias!=canonical):raise RuntimeError('alias resolution flag mismatch: '+alias)
            if any(stat.get(k)!=canonical_stat.get(k) for k in compare):raise RuntimeError('encoded alias physical/recipe identity differs from canonical: '+alias)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--operation-dir',required=True,type=Path)
    ap.add_argument('--baseline-sha256',required=True)
    ap.add_argument('--operation-id',required=True)
    ap.add_argument('--hold-nonce',required=True)
    ap.add_argument('--batch-policy',choices=tuple(POLICIES),default='initial')
    ap.add_argument('--storage-codec-policy',choices=('reversible-xz-v1',))
    ap.add_argument('--archive-io-profile',choices=ARCHIVE_IO_PROFILES)
    args=ap.parse_args(); policy=validate_storage_policy(args.batch_policy,args.storage_codec_policy,args.archive_io_profile); child_started=time.monotonic()
    op=args.operation_dir.resolve()
    validate_operation_directory(op,D/'runs',args.operation_id,{'supervisor_state.json','private_admission.json','child.log','private_child_identity.json'},{'child_result.json','private_candidate_plan.json'})
    hold_doc=json.loads((R/'ADMISSION_HOLD.json').read_text())
    if hold_doc.get('owner_operation')!='rf_cold_batch_wrapper_20261026' or hold_doc.get('nonce')!=args.hold_nonce or hold_doc.get('operation_id')!=args.operation_id:
        raise RuntimeError('active admission hold identity does not match supervisor invocation')
    baseline=args.baseline_sha256.lower()
    if len(baseline)!=64 or any(c not in '0123456789abcdef' for c in baseline): raise ValueError('explicit 64-hex reviewed baseline SHA required')
    for name,digest in PINS.items():
        if sha(R/'source'/name)!=digest: raise RuntimeError('pinned source changed: '+name)
    if 'i-095641a281a4038b9' not in Path('/sys/devices/virtual/dmi/id/board_asset_tag').read_text():
        raise RuntimeError('EC2 identity mismatch')
    archive=ROOT/'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip'
    store=cold.ColdModelStore.from_runtime(ROOT,R,archive_path=archive,storage_codec_policy=args.storage_codec_policy)
    if archive.is_symlink() or not archive.is_file() or not store.manifest.is_file():
        raise RuntimeError('existing regular archive and committed manifest are required; never initialize or adopt')
    manifest=cold._manifest_load(store.manifest)
    store._check_reviewed_baseline(manifest,baseline)
    rec=snapshot()
    raw_items=build_candidates(ROOT,R,rec,{x['logical_path'] for x in manifest.get('members',[])},cold._safety,cold,packing=policy['packing'])
    items,candidate_filter=filter_candidate_publication_aliases(raw_items,rec,store)
    candidate_filter['observed_utc']=now()
    batch=select_batch(items,max_bytes=policy['max_bytes'],max_groups=policy['max_groups'])
    if not batch:
        result={'schema':'lamost-rf-cold-batch/1','status':'no_eligible_candidates','observed_utc':now(),'baseline_archive_sha256':baseline,'candidate_count':len(items),'candidate_filter':candidate_filter,'batch':public_candidate_summary(batch),'batch_policy':args.batch_policy,'storage_codec_policy':args.storage_codec_policy,'storage_evidence':{'codec_policy':args.storage_codec_policy,'model_count':0,'encoded_model_count':0,'raw_fallback_count':0,'logical_source_bytes':0,'physical_payload_bytes':0,'archive_bytes_delta':0,'exact_logical_verifications':[]},'batch_max_bytes':policy['max_bytes'],'batch_max_inode_groups':policy['max_groups'],'transient_disk_reserve_bytes':policy['transient_disk_reserve_bytes'],'batch_packing':policy['packing'],'child_wall_limit_seconds':policy['wall_seconds'],**({'archive_io_profile':args.archive_io_profile} if args.archive_io_profile else {}),'child_elapsed_seconds':round(time.monotonic()-child_started,3),'archive_mutated':False,'model_paths_removed':False,'operation_id':args.operation_id,'scientific_fits_started':0}
        cold._atomic_json(op/'child_result.json',result); return 0
    # Keep private candidate path/process evidence inside this unique operation directory.
    (op/'private_candidate_plan.json').write_text(json.dumps({'observed_utc':now(),'items':batch,'candidate_filter':candidate_filter,'private':True},indent=2,sort_keys=True)+'\n')
    tx=store.commit_models(batch,rec)
    j=json.loads((store.journals/tx/'journal.json').read_text())
    if j.get('state')!='complete': raise RuntimeError('core journal not complete; hold must remain for explicit recovery')
    store2=cold.ColdModelStore.from_runtime(ROOT,R,storage_codec_policy=args.storage_codec_policy)
    with store2._write_lock():
        _adopt_verified_core_cache(store,store2,j)
        j=json.loads((store2.journals/tx/'journal.json').read_text())
        new_manifest=cold._manifest_load(store2.manifest)
        storage_evidence=_bind_completed_core_payload_evidence(ROOT,store2,tx,batch,baseline)
        if storage_evidence['codec_policy']!=args.storage_codec_policy: raise RuntimeError('post-commit codec policy evidence mismatch')
        _verify_completed_alias_metadata(ROOT,store2,j['items'],tx,storage_evidence)
        result={'schema':'lamost-rf-cold-batch/1','status':'committed_and_resolved','observed_utc':now(),'transaction_id':tx,'archive_path':'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip','baseline_archive_sha256':baseline,'archive_sha256_after':new_manifest['archive_sha256'],'archive_bytes_after':archive.stat().st_size,'zip_crc_verified':True,'zip_crc_verification_basis':'pinned_core_transaction_item_verification','fresh_archive_sha_verified':storage_evidence.get('archive_digest_basis')=='fresh_manifest_digest_fallback','archive_digest_basis':storage_evidence.get('archive_digest_basis'),'verification_basis':'pinned_core_complete_transaction_journal_plus_archive_manifest_digest_and_zip_index','candidate_filter':candidate_filter,'batch':public_candidate_summary(batch),'batch_policy':args.batch_policy,'storage_codec_policy':args.storage_codec_policy,'storage_evidence':storage_evidence,'batch_max_bytes':policy['max_bytes'],'batch_max_inode_groups':policy['max_groups'],'transient_disk_reserve_bytes':policy['transient_disk_reserve_bytes'],'batch_packing':policy['packing'],'child_wall_limit_seconds':policy['wall_seconds'],**({'archive_io_profile':args.archive_io_profile} if args.archive_io_profile else {}),'child_elapsed_seconds':round(time.monotonic()-child_started,3),'archive_mutated':True,'model_paths_removed':True,'scientific_fits_started':0,'operation_id':args.operation_id,'source_pins':PINS}
        cold._atomic_json(op/'child_result.json',result)
    print(json.dumps(result),flush=True)
    return 0
if __name__=='__main__': raise SystemExit(main())








