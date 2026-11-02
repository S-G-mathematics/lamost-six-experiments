import hashlib,json,pathlib,tempfile,unittest,zipfile,zlib,sys
from unittest.mock import patch

STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import joblib.compressor
import reversible_joblib_codec as codec
import cold_codec_storage as adapter
import cold_model_storage as core

def sha(data):return hashlib.sha256(data).hexdigest()
def z3(raw):
 c=zlib.compressobj(3,zlib.DEFLATED,zlib.MAX_WBITS,zlib.DEF_MEM_LEVEL,0)
 return c.compress(raw)+c.flush()

class ColdModelStoreReaderTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.td.name)
  self.runtime=self.root/'runtime_20261025';self.runtime.mkdir()
  self.temp=self.root/'scratch';self.temp.mkdir()
  self.source=self.root/'pipeline.joblib';self.raw=(b'core fixture only\n'*500)+bytes(range(256));self.original=z3(self.raw);self.source.write_bytes(self.original)
  self.compressor=pathlib.Path(joblib.compressor.__file__)
  self.patch=patch.object(codec,'SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256',sha(self.compressor.read_bytes()));self.patch.start();self.addCleanup(self.patch.stop)
  self.logical='runtime_20261025/artifacts/e3/rep_1/fit/random_forest/pipeline.joblib'
  self.member='runtime_20261025/cold_models/e3/rep_1/pipeline.joblib.'+sha(self.original)+'.zipmember'
  self.payload,self.fields=adapter.encode_entry_payload(self.source,archive_member=self.member,
      temp_root=self.temp,joblib_compressor_source_path=self.compressor,
      max_payload_bytes=1_000_000,max_file_bytes=1_000_000,chunk_bytes=512)
  self.row={'task_key':'e3/rep_1/fit/random_forest','task_sha256':'a'*64,'experiment':3,
      'method':'random_forest','logical_path':self.logical,'source_relpath':self.logical,
      'archive_member':self.member,'sha256':self.fields['sha256'],'bytes':self.fields['bytes'],
      'crc32':self.fields['crc32'],'source_mtime_ns':1,'consumer_tasks':[],
      'aliases':[],'alias_owners':[],'backing':'cold_zip','transaction_id':'fixture',
      'storage_encoding':self.fields['storage_encoding']}
  self.archive=self.root/'packages/cold.zip';self.archive.parent.mkdir()
  with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_STORED) as z:
   adapter.append_encoded_payload(z,self.payload,self.row)
  with zipfile.ZipFile(self.archive) as z:
   info=z.getinfo(self.member);self.row['header_offset']=info.header_offset
   records=core._zip_records_all(z)
  self.manifest=self.runtime/'manifests/cold_model_store_manifest.json';self.manifest.parent.mkdir()
  doc={'schema_version':core.SCHEMA,'archive_path':self.archive.relative_to(self.root).as_posix(),
       'archive_sha256':core.sha256_file(self.archive),'archive_bytes':self.archive.stat().st_size,
       'members':[self.row],'zip_records':records}
  self.manifest.write_text(json.dumps(doc))
  self.store=core.ColdModelStore(self.root,self.runtime,self.archive,self.manifest,
                                 self.runtime/'journals/cold_model_store')
  self.addCleanup(self.td.cleanup)
 def test_core_open_verified_returns_logical_joblib_bytes(self):
  with self.store.open_verified(self.logical,self.row['sha256']) as f:self.assertEqual(f.read(),self.original)
 def test_core_stat_separates_logical_and_physical_identities(self):
  s=self.store.artifact_stat(self.logical,self.row['sha256'])
  d=self.row['storage_encoding']
  self.assertEqual((s['sha256'],s['size'],s['logical_crc32']),
                   (sha(self.original),len(self.original),self.row['crc32']))
  self.assertEqual((s['payload_sha256'],s['payload_size'],s['payload_crc32']),
                   (d['encoded_sha256'],d['encoded_size_bytes'],d['encoded_crc32']))
  self.assertEqual(s['storage_encoding'],d)
 def test_core_rejects_physical_metadata_tampering(self):
  doc=json.loads(self.manifest.read_text());doc['members'][0]['storage_encoding']['encoded_crc32']^=1
  self.manifest.write_text(json.dumps(doc))
  with self.assertRaises(core.AmbiguousState):self.store.artifact_stat(self.logical)
 def test_core_keeps_legacy_raw_rows_readable(self):
  rawmember='runtime_20261025/cold_models/legacy.joblib'
  rawarchive=self.root/'packages/raw.zip'
  with zipfile.ZipFile(rawarchive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(rawmember,self.original)
  with zipfile.ZipFile(rawarchive) as z:
   info=z.getinfo(rawmember);records=core._zip_records_all(z)
  row={'logical_path':self.logical,'archive_member':rawmember,'sha256':sha(self.original),
       'bytes':len(self.original),'crc32':info.CRC,'header_offset':info.header_offset,
       'source_mtime_ns':1,'aliases':[]}
  man=self.runtime/'manifests/raw_manifest.json'
  man.write_text(json.dumps({'schema_version':core.SCHEMA,'archive_path':rawarchive.relative_to(self.root).as_posix(),
      'archive_sha256':core.sha256_file(rawarchive),'archive_bytes':rawarchive.stat().st_size,
      'members':[row],'zip_records':records}))
  st=core.ColdModelStore(self.root,self.runtime,rawarchive,man,self.runtime/'journals/raw')
  with st.open_verified(self.logical,row['sha256']) as f:self.assertEqual(f.read(),self.original)
  self.assertEqual(st.artifact_stat(self.logical)['storage_format'],'raw-v1')

if __name__=='__main__':unittest.main()

