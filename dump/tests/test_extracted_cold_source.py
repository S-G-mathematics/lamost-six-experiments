import hashlib, importlib.util, json, pathlib, sys, tempfile, zlib, zipfile
import pytest
STAGE=pathlib.Path(__file__).resolve().parents[1]/'source'
sys.path.insert(0,str(STAGE))
import extracted_cold_source as ecs
import reversible_joblib_codec as codec

def crc(b): return zipfile.crc32(b)&0xffffffff

def fixture(tmp_path, encoded=False):
    root=tmp_path; rt=root/'runtime_20261025'; (rt/'manifests').mkdir(parents=True); (rt/'source').mkdir(); (rt/'cache').mkdir()
    rel='runtime_20261025/artifacts/task-1/pipeline.joblib'; payload=root/rel; payload.parent.mkdir(parents=True)
    logical=zlib.compress(b'fixture-model-bytes'*80,3)
    compressor=pathlib.Path(__import__('joblib.compressor',fromlist=['x']).__file__).resolve()
    desc=None
    if encoded:
        temp=root/'tmp';temp.mkdir()
        desc=codec.encode_file_from_bytes if False else None
        source=root/'logical.joblib';source.write_bytes(logical)
        desc=codec.encode_file(source,payload,output_root=root,joblib_compressor_source_path=compressor)
        physical=payload.read_bytes()
    else:
        payload.write_bytes(logical);physical=logical
    row={'logical_source_path':rel,'canonical_logical_path':rel,'resolved_from_alias':False,
      'task_key':'task-1','task_sha256':'a'*64,'archive_member':'cold/task-1/pipeline.joblib',
      'member_sha256':hashlib.sha256(physical).hexdigest(),'member_bytes':len(physical),'member_crc32':crc(physical),
      'member_header_offset':0,'aliases':[]}
    if desc:
        row.update(logical_sha256=hashlib.sha256(logical).hexdigest(),logical_bytes=len(logical),logical_crc32=crc(logical),
          storage_format=desc['codec_version'],storage_encoding={**desc,'original_crc32':crc(logical),'encoded_crc32':crc(physical)})
    projection=rt/'manifests/cold_archived_artifact_members.json'
    projection.write_text(json.dumps({'schema_version':'lamost-cold-model-membership-snapshot/1','members':[row]}))
    source_module=STAGE/'extracted_cold_source.py'; codec_module=STAGE/'reversible_joblib_codec.py'
    resolver=ecs.ExtractedColdSource(root,rt,rt/'cache',codec_module,compressor,projection)
    return resolver,rel,logical,payload,row,projection

def test_raw_lookup_and_open(tmp_path):
    r,key,logical,*_=fixture(tmp_path)
    st=r.stat(key,hashlib.sha256(logical).hexdigest())
    assert st['backing']=='cold_extracted'
    with r.open(key) as f: assert f.read()==logical

def test_encoded_decode_and_cache_identity(tmp_path):
    r,key,logical,*_=fixture(tmp_path,True)
    st=r.stat(key,hashlib.sha256(logical).hexdigest())
    assert st['cache_identity']['projection_sha256']
    with r.open(key) as f: assert f.read()==logical
    assert not list((tmp_path/'runtime_20261025/cache').glob('.codec-original-*'))

def test_wrong_expected_sha_and_physical_tamper_fail_closed(tmp_path):
    r,key,logical,payload,*_=fixture(tmp_path,True)
    with pytest.raises(ecs.ExtractedColdError): r.stat(key,'0'*64)
    payload.write_bytes(payload.read_bytes()+b'x')
    with pytest.raises(ecs.ExtractedColdError): r.stat(key)

def test_duplicate_projection_identity_fails(tmp_path):
    r,key,logical,payload,row,projection=fixture(tmp_path)
    d=json.loads(projection.read_text());d['members'].append(dict(row));projection.write_text(json.dumps(d))
    compressor=pathlib.Path(__import__('joblib.compressor',fromlist=['x']).__file__).resolve()
    with pytest.raises(ecs.ExtractedColdError):
        ecs.ExtractedColdSource(tmp_path,tmp_path/'runtime_20261025',tmp_path/'runtime_20261025/cache',
          STAGE/'reversible_joblib_codec.py',compressor,projection)

def test_symlinked_payload_fails(tmp_path):
    r,key,logical,payload,*_=fixture(tmp_path)
    other=tmp_path/'other';other.write_bytes(payload.read_bytes());payload.unlink();payload.symlink_to(other)
    with pytest.raises(ecs.ExtractedColdError): r.stat(key)
from cold_report_access import inspect_pipeline, ArtifactIdentityError
import shutil

def _report_fixture(tmp_path, encoded=True):
    _,rel,logical,payload,row,projection=fixture(tmp_path,encoded)
    rt=tmp_path/'runtime_20261025'
    if encoded:
        unique=tmp_path/row['archive_member'];unique.parent.mkdir(parents=True,exist_ok=True);payload.rename(unique)
    shutil.copy(STAGE/'extracted_cold_source.py',rt/'source/extracted_cold_source.py')
    shutil.copy(STAGE/'reversible_joblib_codec.py',rt/'source/reversible_joblib_codec.py')
    task={'key':'task-1','kind':'fit','outcome':'successful','status':'validated_terminal','validation_state':'validated',
      'result':{'validation':{'status':'validated','task_key':'task-1','files':{'pipeline.joblib':hashlib.sha256(logical).hexdigest()}},
                'result':{'pipeline_sha256':hashlib.sha256(logical).hexdigest()}}}
    return task,rt,logical

def test_report_access_resolves_encoded_extracted_payload(tmp_path):
    task,rt,logical=_report_fixture(tmp_path,True)
    info=inspect_pipeline(task,rt)
    assert info['available'] and info['backing']=='cold_extracted'
    assert info['sha256']==hashlib.sha256(logical).hexdigest()

def test_report_access_keeps_raw_physical_fast_path(tmp_path):
    task,rt,logical=_report_fixture(tmp_path,False)
    info=inspect_pipeline(task,rt)
    assert info['available'] and info['backing']=='physical'
def test_projection_change_after_init_rejected_by_lookup_and_open(tmp_path):
    r,key,logical,payload,row,projection=fixture(tmp_path,True)
    projection.write_text(projection.read_text()+' ')
    with pytest.raises(ecs.ExtractedColdError): r.stat(key)
    with pytest.raises(ecs.ExtractedColdError):
        with r.open(key): pass
def test_archive_payload_at_unique_member_path_resolves_after_alias_skip(tmp_path):
    r,key,logical,payload,row,projection=fixture(tmp_path,True)
    unique=tmp_path/row['archive_member'];unique.parent.mkdir(parents=True,exist_ok=True);payload.rename(unique)
    assert not payload.exists()
    with r.open(key) as f: assert f.read()==logical
def test_archive_member_preferred_over_existing_encoded_alias(tmp_path):
    r,key,logical,payload,row,projection=fixture(tmp_path,True)
    unique=tmp_path/row['archive_member'];unique.parent.mkdir(parents=True,exist_ok=True);unique.write_bytes(payload.read_bytes())
    st=r.stat(key,hashlib.sha256(logical).hexdigest())
    assert st['cache_identity']['inode']==unique.stat().st_ino
class _ForbiddenFallback:
    def __init__(self): self.calls=0
    def artifact_stat(self,*args): self.calls+=1; raise AssertionError('cold-store fallback must not run')
class _ForbiddenExtracted:
    def __init__(self): self.calls=0
    def stat(self,*args): self.calls+=1; raise AssertionError('extracted fallback must not run')

def _assert_present_native_rejected(tmp_path, mutation):
    task,rt,logical=_report_fixture(tmp_path,False)
    physical=rt/'artifacts'/task['key']/'pipeline.joblib'
    other=tmp_path/'other-payload';other.write_bytes(b'foreign pipeline')
    if mutation=='mismatch': physical.write_bytes(b'wrong logical content')
    elif mutation=='symlink': physical.unlink();physical.symlink_to(other)
    elif mutation=='nonfile': physical.unlink();physical.mkdir()
    store=_ForbiddenFallback();extracted=_ForbiddenExtracted()
    with pytest.raises(ArtifactIdentityError): inspect_pipeline(task,rt,store=store,extracted_source=extracted)
    assert store.calls==0 and extracted.calls==0

def test_present_native_hash_mismatch_never_falls_back(tmp_path):
    _assert_present_native_rejected(tmp_path,'mismatch')
def test_present_native_symlink_never_falls_back(tmp_path):
    _assert_present_native_rejected(tmp_path,'symlink')
def test_present_native_nonfile_never_falls_back(tmp_path):
    _assert_present_native_rejected(tmp_path,'nonfile')
