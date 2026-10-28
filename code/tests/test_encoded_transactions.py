import contextlib,hashlib,json,os,pathlib,tempfile,unittest,zipfile,sys,io
from unittest.mock import patch
STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import joblib,joblib.compressor
import cold_model_storage as core
import reversible_joblib_codec as codec

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

class EncodedTransactionTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory(dir=STAGE/'tests');self.addCleanup(self.td.cleanup)
  self.root=pathlib.Path(self.td.name)/'migration';self.runtime=self.root/'runtime_20261025';self.runtime.mkdir(parents=True)
  self.archive=self.root/'packages'/'cold.zip';self.manifest=self.runtime/'manifests'/'cold_model_store_manifest.json';self.journals=self.runtime/'journals'/'cold_model_store'
  self.compressor=pathlib.Path(joblib.compressor.__file__)
  self.pin=patch.object(codec,'SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256',sha_file(self.compressor));self.pin.start();self.addCleanup(self.pin.stop)
  self.store=core.ColdModelStore(self.root,self.runtime,self.archive,self.manifest,self.journals,joblib_compressor_source_path=self.compressor,storage_codec_policy='reversible-xz-v1')
  self.store.initialize_empty_archive();self.records={};self.items={};self.sources={};self.digests={};self.originals={}
  self.add_fit('e3/rep_1/fit/real/random_forest','e3/rep_1/eval/direct/random_forest/gmm',3,'rep_1')
 def add_fit(self,key,consumer_key,experiment,rep,payload=None):
  out=self.runtime/'artifacts'/key;out.mkdir(parents=True);source=out/'pipeline.joblib'
  payload=payload if payload is not None else b'codec transaction byte fixture|'*12000
  joblib.dump({'fixture':'no-model-bytes-only','payload':payload,'params':{'n_estimators':1}},source,compress=3)
  original=source.read_bytes();digest=sha_bytes(original);attempt_id='attempt_'+rep;task_sha=sha_bytes(('task-identity:'+key).encode())
  attempt_dir=out/'attempts'/attempt_id;attempt_dir.mkdir(parents=True);checkpoint_dir=out/'checkpoints'/task_sha;checkpoint_dir.mkdir(parents=True)
  attempt_alias=attempt_dir/'pipeline.joblib';os.link(source,attempt_alias);checkpoint_alias=checkpoint_dir/'pipeline.joblib';os.link(source,checkpoint_alias)
  selection=json.dumps({'selected_params':{'n_estimators':1}},sort_keys=True).encode();selection_sha=sha_bytes(selection)
  for q in (out/'selection.json',attempt_dir/'selection.json',checkpoint_dir/'selection.json'):q.write_bytes(selection)
  fit_result={'attempt_id':attempt_id,'task_sha256':task_sha,'result':{'pipeline_sha256':digest,'status':'success'}}
  fit_result_bytes=json.dumps(fit_result,sort_keys=True).encode();(out/'fit_result.json').write_bytes(fit_result_bytes);(attempt_dir/'attempt.json').write_bytes(fit_result_bytes)
  publication={'attempt_id':attempt_id,'pipeline_sha256':digest,'published_path':str(source.resolve()),'stage':'validated_publication','task_sha256':task_sha}
  publication_bytes=json.dumps(publication,sort_keys=True).encode();(out/'fit_publication.json').write_bytes(publication_bytes);(attempt_dir/'fit_publication.json').write_bytes(publication_bytes)
  fit={'key':key,'experiment':experiment,'kind':'fit','method':'random_forest','status':'validated_terminal','outcome':'successful','validation_state':'validated','artifact_dir':str(out),'dependencies':[],
       'result':{'attempt_id':attempt_id,'task_sha256':task_sha,'result':{'pipeline_sha256':digest},'validation':{'status':'validated','task_key':key,'files':{'pipeline.joblib':digest,'selection.json':selection_sha}}}}
  consumer={'key':consumer_key,'experiment':experiment,'kind':'eval','method':'random_forest','status':'validated_terminal','outcome':'successful','validation_state':'validated','dependencies':[key],'artifact_dir':str(self.runtime/'artifacts'/consumer_key),'result':{}}
  self.records[key]=fit;self.records[consumer_key]=consumer;rel=source.relative_to(self.root).as_posix()
  item={'producer_task':key,'source_path':rel,'source_relpath':rel,'archive_member':rel,'source_sha256':digest,'recorded_artifact_sha256':digest,'consumer_tasks':[consumer_key],
        'aliases':[rel,attempt_alias.relative_to(self.root).as_posix(),checkpoint_alias.relative_to(self.root).as_posix()]}
  self.items[key]=item;self.sources[key]=source;self.digests[key]=digest;self.originals[key]=original;return item
 def journal(self,tx):return json.loads((self.journals/tx/'journal.json').read_text())
 def only_tx(self):
  paths=list(self.journals.glob('*/journal.json'))
  self.assertEqual(len(paths),1,'only_tx requires exactly one transaction journal')
  return paths[0].parent.name
 def test_successful_encoded_transaction_restores_exact_bytes_and_records_physical_identity(self):
  key=next(iter(self.items));src=self.sources[key];expected=self.originals[key];tx=self.store.commit_models([self.items[key]],self.records)
  row=json.loads(self.manifest.read_text())['members'][0];desc=row['storage_encoding']
  self.assertEqual((row['sha256'],row['bytes']),(self.digests[key],len(expected)));self.assertLess(desc['encoded_size_bytes'],len(expected))
  self.assertFalse(src.exists());self.assertEqual(self.store.read_bytes(row['logical_path'],row['sha256']),expected)
  with zipfile.ZipFile(self.archive) as z:
   info=z.getinfo(row['archive_member']);self.assertEqual(info.compress_type,zipfile.ZIP_STORED);self.assertEqual((info.file_size,info.CRC),(desc['encoded_size_bytes'],desc['encoded_crc32']))
  j=self.journal(tx);self.assertEqual(j['state'],'complete');self.assertEqual(j['items'][0]['storage_decision']['selected'],codec.CODEC_VERSION)
 def test_default_policy_keeps_raw_payload_and_legacy_row(self):
  key=next(iter(self.items));self.store.storage_codec_policy=None;tx=self.store.commit_models([self.items[key]],self.records)
  row=json.loads(self.manifest.read_text())['members'][0];self.assertNotIn('storage_encoding',row);self.assertEqual(self.store.read_bytes(row['logical_path'],row['sha256']),self.originals[key])
  with zipfile.ZipFile(self.archive) as z:self.assertEqual(z.read(row['archive_member']),self.originals[key])
  self.assertIsNone(self.journal(tx)['items'][0].get('storage_decision'))
 def _assert_raw_fallback(self,exc_type,patcher):
  key=next(iter(self.items));src=self.sources[key];expected=self.originals[key]
  with patcher:tx=self.store.commit_models([self.items[key]],self.records)
  row=json.loads(self.manifest.read_text())['members'][0];decision=self.journal(tx)['items'][0]['storage_decision']
  self.assertEqual((decision['selected'],decision['exception_type']),('raw-v1',exc_type));self.assertNotIn('storage_encoding',row)
  self.assertEqual(self.store.read_bytes(row['logical_path'],row['sha256']),expected);self.assertFalse(src.exists())
 def test_unsupported_codec_uses_explicit_raw_fallback(self):
  p=patch.object(core._codec_storage,'encode_entry_payload',side_effect=codec.UnsupportedCodec('fixture unknown pinned compressor'));self._assert_raw_fallback('UnsupportedCodec',p)
 def test_typed_fixed_bound_uses_raw_fallback_without_allocating_large_buffers(self):
  p=patch.object(core._codec_storage,'encode_entry_payload',side_effect=codec.CodecLimitError('fixture fixed encoded-stream bound'));self._assert_raw_fallback('CodecLimitError',p)
 def test_codec_roundtrip_mismatch_fails_closed_and_preserves_all_sources(self):
  key=next(iter(self.items));before=sha_file(self.archive);expected=self.originals[key]
  @contextlib.contextmanager
  def wrong_roundtrip(*args,**kwargs):yield io.BytesIO(b'wrong logical bytes')
  with patch.object(core._codec_storage.codec,'open_verified',wrong_roundtrip):
   with self.assertRaises(core.AmbiguousState):self.store.commit_models([self.items[key]],self.records)
  tx=self.only_tx();self.assertEqual(self.journal(tx)['state'],'prepared');self.assertEqual(sha_file(self.archive),before)
  for alias in self.items[key]['aliases']:self.assertEqual((self.root/alias).read_bytes(),expected)
  self.assertNotIn('storage_decision',self.journal(tx)['items'][0]);self.assertEqual(self.store.recover(tx,self.records),'rolled_back')
 def test_mixed_existing_raw_and_new_encoded_rows_remain_readable(self):
  first=next(iter(self.items));self.store.storage_codec_policy=None;self.store.commit_models([self.items[first]],self.records)
  second='e4/rep_2/fit/direct/random_forest/A_half';consumer='e4/rep_2/eval/direct/random_forest/A_half'
  item=self.add_fit(second,consumer,4,'rep_2',payload=b'mixed raw plus encoded transaction|'*12000)
  self.store.storage_codec_policy='reversible-xz-v1';self.store.commit_models([item],self.records)
  rows={r['task_key']:r for r in json.loads(self.manifest.read_text())['members']}
  self.assertNotIn('storage_encoding',rows[first]);self.assertIn('storage_encoding',rows[second])
  for key in (first,second):self.assertEqual(self.store.read_bytes(rows[key]['logical_path'],rows[key]['sha256']),self.originals[key])
 def test_interrupted_physical_append_rolls_back_exact_zip_and_keeps_sources(self):
  key=next(iter(self.items));before=sha_file(self.archive)
  with self.assertRaises(RuntimeError):self.store.commit_models([self.items[key]],self.records,fault_after_bytes=24)
  tx=self.only_tx();self.assertEqual(self.store.recover(tx,self.records),'rolled_back');self.assertEqual(sha_file(self.archive),before)
  for alias in self.items[key]['aliases']:self.assertEqual((self.root/alias).read_bytes(),self.originals[key])
  self.assertEqual(json.loads(self.manifest.read_text())['members'] if self.manifest.exists() else [],[])
 def test_archive_commit_before_manifest_is_recovered(self):
  key=next(iter(self.items))
  with patch.object(self.store,'_write_manifest',side_effect=RuntimeError('injected before manifest write')):
   with self.assertRaises(RuntimeError):self.store.commit_models([self.items[key]],self.records)
  tx=self.only_tx();self.assertEqual(self.journal(tx)['state'],'archive_committed');self.assertEqual(self.store.recover(tx,self.records),'complete')
  row=json.loads(self.manifest.read_text())['members'][0];self.assertIn('storage_encoding',row);self.assertEqual(self.store.read_bytes(row['logical_path'],row['sha256']),self.originals[key])
 def test_manifest_commit_before_unlink_is_recovered(self):
  key=next(iter(self.items))
  with patch.object(self.store,'_unlink_aliases',side_effect=RuntimeError('injected before unlink')):
   with self.assertRaises(RuntimeError):self.store.commit_models([self.items[key]],self.records)
  tx=self.only_tx();self.assertEqual(self.journal(tx)['state'],'manifest_committed')
  for alias in self.items[key]['aliases']:self.assertTrue((self.root/alias).exists())
  self.assertEqual(self.store.recover(tx,self.records),'complete')
  for alias in self.items[key]['aliases']:self.assertFalse((self.root/alias).exists())
 def test_partial_alias_unlink_resumes_idempotently(self):
  key=next(iter(self.items))
  with self.assertRaises(RuntimeError):self.store.commit_models([self.items[key]],self.records,fail_after_unlinks=1)
  tx=self.only_tx();j=self.journal(tx);self.assertEqual(j['state'],'unlinking');self.assertTrue(j['items'][0]['unlink_intents'])
  missing=[p for p in j['items'][0]['aliases'] if not (self.store.root/p).exists()]
  self.assertTrue(missing);self.assertTrue(set(missing)<=set(j['items'][0]['unlink_intents']))
  self.assertEqual(self.store.recover(tx,self.records),'complete')
  for alias in self.items[key]['aliases']:self.assertFalse((self.root/alias).exists())
 def test_codec_temp_root_rejects_symlinked_parent_without_writing_outside_runtime(self):
  outside=self.root/'outside';outside.mkdir();tmp=self.runtime/'tmp';tmp.symlink_to(outside,target_is_directory=True)
  with self.assertRaises((core.AmbiguousState,core.UnsafePlan)):
   self.store._codec_options()
  self.assertFalse((outside/'cold_codec_read').exists())
 def test_old_archive_prefix_mutation_during_postappend_verification_fails_closed(self):
  first=next(iter(self.items));self.store.storage_codec_policy=None
  self.store.commit_models([self.items[first]],self.records)
  first_row=json.loads(self.manifest.read_text())['members'][0]
  second='e4/rep_2/fit/direct/random_forest/A_half';consumer='e4/rep_2/eval/direct/random_forest/A_half'
  item=self.add_fit(second,consumer,4,'rep_2',payload=b'new encoded transaction|'*12000)
  prior_txids={p.parent.name for p in self.journals.glob('*/journal.json')}
  self.store.storage_codec_policy='reversible-xz-v1'
  original_verify=self.store._verify_transaction_item
  mutated={'done':False}
  def verify_then_mutate(txitem,rec,z):
   original_verify(txitem,rec,z)
   if not mutated['done']:
    mutated['done']=True
    with zipfile.ZipFile(self.archive) as oldzip:
     oldrec=next(r for r in core._zip_records_all(oldzip) if r['member']==first_row['archive_member'])
    raw=bytearray(self.archive.read_bytes())
    offset=oldrec['header_offset']
    name_len=int.from_bytes(raw[offset+26:offset+28],'little');extra_len=int.from_bytes(raw[offset+28:offset+30],'little')
    data_offset=offset+30+name_len+extra_len
    raw[data_offset]^=1
    self.archive.write_bytes(raw)
  with patch.object(self.store,'_verify_transaction_item',side_effect=verify_then_mutate):
   with self.assertRaises(core.AmbiguousState):self.store.commit_models([item],self.records)
  self.assertTrue(mutated['done'])
  current_txids={p.parent.name for p in self.journals.glob('*/journal.json')}
  new_txids=current_txids-prior_txids
  self.assertEqual(len(new_txids),1,'failed second append must have one new journal')
  tx=new_txids.pop();failed_journal=self.journal(tx)
  self.assertEqual(failed_journal['items'][0]['task_key'],second)
  self.assertEqual(failed_journal['state'],'appending')
  for alias in item['aliases']:self.assertEqual((self.root/alias).read_bytes(),self.originals[second])
  self.assertNotIn(second,[r['task_key'] for r in json.loads(self.manifest.read_text())['members']])
  self.assertTrue(self.sources[second].exists())
 def _commit_one_encoded(self):
  key=next(iter(self.items));self.store.commit_models([self.items[key]],self.records)
  row=json.loads(self.manifest.read_text())['members'][0]
  journal_path=self.journals/self.only_tx()/'journal.json'
  return row,journal_path
 def test_valid_creator_proof_uses_physical_stream_hash_without_redecoding(self):
  row,jp=self._commit_one_encoded()
  journal=json.loads(jp.read_text())
  self.assertEqual(journal['state'],'complete')
  self.assertEqual(journal.get('codec_verifier_source_sha256'),core._IMPORTED_SOURCE_SHA256)
  self.assertTrue(self.store._has_completed_logical_verification(row))
  with patch.object(core._codec_storage,'open_logical_member',side_effect=AssertionError('valid proof should avoid repeat decode')):
   info=self.store._verified_member_metadata(row['logical_path'],row)
  self.assertEqual(info.filename,row['archive_member'])
 def test_missing_old_incomplete_and_tampered_proofs_force_full_decode(self):
  row,jp=self._commit_one_encoded();original=jp.read_bytes();decoded=core._codec_storage.open_logical_member
  mutations={
   'missing':lambda j:j['items'][0].pop('logical_verification',None),
   'old_verifier':lambda j:j.__setitem__('codec_verifier_source_sha256','0'*64),
   'incomplete':lambda j:j.__setitem__('state','appending'),
   'tampered_logical_binding':lambda j:j['items'][0]['logical_verification'].__setitem__('logical_bytes',-1),
  }
  for name,mutate in mutations.items():
   with self.subTest(proof=name):
    j=json.loads(original);mutate(j);jp.write_text(json.dumps(j,sort_keys=True))
    with patch.object(core._codec_storage,'open_logical_member',wraps=decoded) as opened:
     self.store._verified_member_metadata(row['logical_path'],row)
     self.assertGreater(opened.call_count,0)
  jp.write_bytes(original)
 def test_encoded_payload_tampering_rejects_even_when_creator_proof_is_valid(self):
  row,jp=self._commit_one_encoded();self.assertTrue(self.store._has_completed_logical_verification(row))
  with zipfile.ZipFile(self.archive) as z:
   info=z.getinfo(row['archive_member']);offset=info.header_offset
  raw=bytearray(self.archive.read_bytes());name_len=int.from_bytes(raw[offset+26:offset+28],'little');extra_len=int.from_bytes(raw[offset+28:offset+30],'little')
  raw[offset+30+name_len+extra_len]^=1;self.archive.write_bytes(raw)
  with self.assertRaises((core.AmbiguousState,zipfile.BadZipFile,RuntimeError)):
   self.store._verified_member_metadata(row['logical_path'],row)
 def test_open_verified_always_performs_logical_decode_despite_creator_proof(self):
  row,jp=self._commit_one_encoded();self.assertTrue(self.store._has_completed_logical_verification(row))
  original=core._codec_storage.open_logical_member
  with patch.object(core._codec_storage,'open_logical_member',wraps=original) as opened:
   with self.store.open_verified(row['logical_path'],row['sha256']) as f:
    logical=f.read()
   self.assertGreater(opened.call_count,0)
  self.assertEqual(sha_bytes(logical),row['sha256'])
 def test_logical_and_physical_descriptor_tampering_fail_closed(self):
  key=next(iter(self.items));self.store.commit_models([self.items[key]],self.records);original=self.manifest.read_bytes();doc=json.loads(original);row=doc['members'][0]
  doc['members'][0]['sha256']='f'*64;self.manifest.write_text(json.dumps(doc))
  with self.assertRaises(core.AmbiguousState):self.store.read_bytes(row['logical_path'],row['sha256'])
  self.manifest.write_bytes(original);doc=json.loads(original);doc['members'][0]['storage_encoding']['encoded_crc32']^=1;self.manifest.write_text(json.dumps(doc))
  with self.assertRaises(core.AmbiguousState):self.store.artifact_stat(row['logical_path'],row['sha256'])
if __name__=='__main__':unittest.main(verbosity=2)
