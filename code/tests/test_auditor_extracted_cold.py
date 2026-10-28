import contextlib,hashlib,importlib.util,json,pathlib,tempfile,unittest,zipfile
from unittest.mock import patch
import sys

STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import joblib
import joblib.compressor
import reversible_joblib_codec as codec
import cold_codec_storage as adapter
import extracted_cold_source as extracted_mod
import audit_artifacts as auditor_mod

def sha_file(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def crc_file(p):
 c=n=0
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):c=zipfile.crc32(b,c);n+=len(b)
 return c&0xffffffff,n

class ExtractedAuditorTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.td.name)
  self.runtime=self.root/'runtime_20261025';(self.runtime/'manifests').mkdir(parents=True)
  (self.runtime/'source').mkdir();(self.runtime/'cache').mkdir();(self.root/'project').mkdir()
  self.compressor=pathlib.Path(joblib.compressor.__file__).resolve()
  self.source_file=self.root/'tiny.joblib';joblib.dump({'fixture':'tiny','value':17},self.source_file,compress=3)
  self.logical='runtime_20261025/artifacts/e3/rep_1/fit/direct/random_forest/pipeline.joblib'
  self.member='runtime_20261025/cold_models/e3/rep_1/pipeline.joblib.'+sha_file(self.source_file)+'.zipmember'
  self.payload,self.fields=adapter.encode_entry_payload(self.source_file,archive_member=self.member,
      temp_root=self.runtime/'cache',joblib_compressor_source_path=self.compressor,
      max_payload_bytes=1_000_000,max_file_bytes=1_000_000,chunk_bytes=512)
  self.physical=self.root/self.logical;self.physical.parent.mkdir(parents=True);self.physical.write_bytes(self.payload.read_bytes())
  d=self.fields['storage_encoding'];plcrc,pln=crc_file(self.physical)
  self.row={'logical_source_path':self.logical,'canonical_logical_path':self.logical,
      'resolved_from_alias':False,'task_key':'e3/rep_1/fit/direct/random_forest',
      'task_sha256':'a'*64,'archive_member':self.member,
      'member_sha256':sha_file(self.physical),'member_bytes':self.physical.stat().st_size,
      'member_crc32':plcrc,'member_header_offset':0,
      'logical_sha256':sha_file(self.source_file),'logical_bytes':self.source_file.stat().st_size,
      'logical_crc32':self.fields['crc32'],'storage_format':d['codec_version'],
      'storage_encoding':d,'aliases':[],'source_mtime_ns':self.physical.stat().st_mtime_ns}
  self.projection=self.runtime/'manifests/cold_archived_artifact_members.json'
  self.projection.write_text(json.dumps({'schema_version':'lamost-cold-model-membership-snapshot/1','members':[self.row]},sort_keys=True))
  self.codec_copy=self.runtime/'source/reversible_joblib_codec.py';self.codec_copy.write_bytes((STAGE/'source/reversible_joblib_codec.py').read_bytes())
  self.resolver=extracted_mod.ExtractedColdSource(self.root,self.runtime,self.runtime/'cache',
      self.codec_copy,self.compressor,self.projection)
  self.auditor=auditor_mod.Auditor(self.runtime,extracted_cold_source=self.resolver)
  self.addCleanup(self.td.cleanup)
 def test_extracted_path_is_discovered_by_auditor(self):
  self.assertEqual(self.auditor._logical_artifact(self.physical),self.logical)
  self.assertTrue(self.auditor.file_exists(self.physical))
 def test_file_hash_is_exact_logical_pipeline_sha(self):
  self.assertEqual(self.auditor.file_hash(self.physical),self.row['logical_sha256'])
 def test_open_artifact_yields_recreated_joblib_bytes(self):
  with self.auditor.open_artifact(self.physical) as f:
   self.assertEqual(f.read(),self.source_file.read_bytes())
 def test_load_joblib_only_reads_tiny_fixture_object(self):
  self.assertEqual(self.auditor.load_joblib(self.physical),{'fixture':'tiny','value':17})
 def test_hash_cache_reuses_only_same_projection_and_payload_identity(self):
  count={'n':0};original=self.resolver.open
  @contextlib.contextmanager
  def counted(*a,**kw):
   count['n']+=1
   with original(*a,**kw) as f:yield f
  self.resolver.open=counted
  self.assertEqual(self.auditor.file_hash(self.physical),self.row['logical_sha256'])
  self.assertEqual(self.auditor.file_hash(self.physical),self.row['logical_sha256'])
  self.assertEqual(count['n'],1)
  with self.physical.open('ab') as f:f.write(b'x')
  with self.assertRaises(extracted_mod.ExtractedColdError):
   self.auditor.file_hash(self.physical,force=True)
 def test_valid_native_raw_pipeline_takes_precedence_over_extracted_xz(self):
  self.physical.write_bytes(self.source_file.read_bytes())
  @contextlib.contextmanager
  def forbidden(*a,**kw):raise AssertionError('resolver should not be used when native logical bytes are valid');yield
  self.resolver.open=forbidden
  self.assertEqual(self.auditor.file_hash(self.physical),self.row['logical_sha256'])
  with self.auditor.open_artifact(self.physical) as f:self.assertEqual(f.read(),self.source_file.read_bytes())
 def test_projection_mutation_after_auditor_initialization_fails_closed(self):
  with self.projection.open('a') as f:f.write(' ')
  with self.assertRaises(ValueError):self.auditor.file_hash(self.physical,force=True)
 def test_projection_or_payload_tamper_fails_closed(self):
  with self.physical.open('ab') as f:f.write(b'tamper')
  with self.assertRaises(extracted_mod.ExtractedColdError):
   self.auditor.file_hash(self.physical,force=True)
 def test_expected_sha_mismatch_fails_closed(self):
  with self.assertRaises(extracted_mod.ExtractedColdError):
   with self.resolver.open(self.logical,'0'*64):pass
 def test_descriptor_and_logical_projection_must_agree(self):
  bad=dict(self.row);bad['logical_sha256']='f'*64
  self.projection.write_text(json.dumps({'schema_version':'lamost-cold-model-membership-snapshot/1','members':[bad]}))
  r=extracted_mod.ExtractedColdSource(self.root,self.runtime,self.runtime/'cache',self.codec_copy,self.compressor,self.projection)
  with self.assertRaises(extracted_mod.ExtractedColdError):r.stat(self.logical)
 def test_ambiguous_duplicate_projection_is_rejected(self):
  self.projection.write_text(json.dumps({'schema_version':'lamost-cold-model-membership-snapshot/1','members':[self.row,self.row]}))
  with self.assertRaises(extracted_mod.ExtractedColdError):
   extracted_mod.ExtractedColdSource(self.root,self.runtime,self.runtime/'cache',self.codec_copy,self.compressor,self.projection)
 def test_symlink_payload_is_rejected(self):
  self.physical.unlink();self.physical.symlink_to(self.source_file)
  with self.assertRaises(extracted_mod.ExtractedColdError):self.resolver.stat(self.logical)
 def test_legacy_raw_projection_remains_readable(self):
  self.row.pop('storage_encoding');self.row['storage_format']='raw-v1'
  self.row['member_sha256']=self.row['logical_sha256'];self.row['member_bytes']=self.row['logical_bytes']
  self.row['member_crc32']=self.row['logical_crc32']
  self.physical.write_bytes(self.source_file.read_bytes())
  self.projection.write_text(json.dumps({'schema_version':'lamost-cold-model-membership-snapshot/1','members':[self.row]}))
  raw=extracted_mod.ExtractedColdSource(self.root,self.runtime,self.runtime/'cache',self.codec_copy,self.compressor,self.projection)
  a=auditor_mod.Auditor(self.runtime,extracted_cold_source=raw)
  self.assertEqual(a.file_hash(self.physical),self.row['logical_sha256'])
  with a.open_artifact(self.physical) as f:self.assertEqual(f.read(),self.source_file.read_bytes())
 def test_live_cold_backend_precedes_extracted_backend(self):
  self.physical.write_bytes(self.source_file.read_bytes())
  class FakeCold:
   def __init__(self,row,root):
    self.row=row;self.root=root;self.manifest=root/'cold_manifest.json';self.archive=root/'cold.zip'
    self.manifest.write_text(json.dumps({'schema_version':'lamost-cold-model-store/1','members':[{'logical_path':row['logical_source_path'],'aliases':[],'sha256':row['logical_sha256']}]}))
    self.archive.write_bytes(b'fixture')
   @contextlib.contextmanager
   def _read_lock(self):yield
   def artifact_stat(self,logical,expected=None):
    if expected!=self.row['logical_sha256']:raise ValueError('wrong expected SHA')
    return {'sha256':expected,'size':self.row['logical_bytes'],'logical_crc32':self.row['logical_crc32'],'cache_identity':{'backing':'fake-live'}}
   @contextlib.contextmanager
   def open_verified(self,logical,expected=None):yield open(self.root/'live-bytes','rb')
   def load_joblib(self,logical,expected=None):return {'live':True}
  live_bytes=self.root/'live-bytes';live_bytes.write_bytes(self.source_file.read_bytes())
  fake=FakeCold(self.row,self.root)
  a=auditor_mod.Auditor(self.runtime,cold_store=fake,extracted_cold_source=self.resolver)
  self.assertEqual(a.file_hash(self.physical),self.row['logical_sha256'])
  self.assertIs(a._artifact_backend(self.logical),fake)

if __name__=='__main__':unittest.main()

