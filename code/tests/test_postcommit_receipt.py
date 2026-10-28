import hashlib, importlib.util, json, sys, tempfile, unittest, zipfile
from unittest import mock
from pathlib import Path
HERE=Path(__file__).resolve().parent
if HERE.parent.parent.name=='staging':
 STAGE=HERE.parent; R=STAGE.parents[1]; CHILD=STAGE/'source/commit_batch_child.py'
else:
 R=HERE.parent; CHILD=R/'source/commit_batch_child.py'
sys.path.insert(0,str(R/'source'))
_spec=importlib.util.spec_from_file_location('staged_commit_batch_child',CHILD)
child=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(child)
cold=child.cold

class Store:
 def __init__(self,root,policy=None):
  self.root=root;self.runtime=root/'runtime';self.archive=root/'store.zip';self.manifest=self.runtime/'manifest.json';self.journals=self.runtime/'journals';self.storage_codec_policy=policy;self._archive_identity_cache=None
  self.journals.mkdir(parents=True)
 def open_verified(self,*a,**k): raise AssertionError('unexpected logical read')
 def artifact_stat(self,*a,**k): raise AssertionError('unexpected rehashing stat')
 def sha256(self,*a,**k): raise AssertionError('unexpected artifact SHA read')
 def _check_archive_manifest(self,m):
  return cold.ColdModelStore._check_archive_manifest(self,m)
 def _member_entry(self,m,logical):
  return cold.ColdModelStore._member_entry(self,m,logical)
 def _has_completed_logical_verification(self,row):
  return cold.ColdModelStore._has_completed_logical_verification(self,row)

def setup_case(root,alias_extra=False):
 store=Store(root); tx='a'*32; path='runtime_20261025/artifacts/e4/rep_1/fit/random_forest/pipeline.joblib'; alias=path
 payload=b'fixture pipeline bytes only'; digest=hashlib.sha256(payload).hexdigest(); archive_member='models/tiny.zipmember'
 with zipfile.ZipFile(store.archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(archive_member,payload)
 with zipfile.ZipFile(store.archive) as z: records=cold._zip_records_all(z); info=z.getinfo(archive_member)
 aliases=[path]
 if alias_extra: aliases.append('runtime_20261025/artifacts/e4/rep_1/attempts/tiny/pipeline.joblib')
 item={'logical_path':path,'source_relpath':path,'archive_member':archive_member,'sha256':digest,'bytes':len(payload),'crc32':info.CRC,'header_offset':info.header_offset,'storage_encoding':None,'aliases':aliases,'storage_decision':None}
 st=store.archive.stat(); archive_sha=hashlib.sha256(store.archive.read_bytes()).hexdigest(); before='b'*64
 manifest={'schema_version':cold.SCHEMA,'archive_path':store.archive.relative_to(root).as_posix(),'transaction_id':tx,'archive_sha256':archive_sha,'archive_bytes':st.st_size,'zip_records':records,'members':[{'logical_path':path,'archive_member':archive_member,'sha256':digest,'bytes':len(payload),'crc32':info.CRC,'header_offset':info.header_offset,'storage_encoding':None,'aliases':aliases,'transaction_id':tx}]}
 store.manifest.parent.mkdir(parents=True,exist_ok=True); store.manifest.write_text(json.dumps(manifest,sort_keys=True))
 msha=hashlib.sha256(store.manifest.read_bytes()).hexdigest(); (store.journals/tx).mkdir()
 j={'transaction_id':tx,'state':'complete','archive_relpath':store.archive.relative_to(root).as_posix(),'archive_sha256_before':before,'archive_sha256_after':archive_sha,'archive_bytes_after':st.st_size,'archive_size_before':0,'archive_device':st.st_dev,'archive_inode':st.st_ino,'storage_codec_policy':None,'codec_verifier_source_sha256':cold._IMPORTED_SOURCE_SHA256,'manifest_sha256':msha,'member_records_after':records,'items':[item]}
 (store.journals/tx/'journal.json').write_text(json.dumps(j,sort_keys=True))
 return store,tx,before,item

class MetadataReceiptTests(unittest.TestCase):
 def test_raw_receipt_uses_completed_core_proof_without_payload_reads(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td),True)
   plan=[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}]
   real_sha=cold.sha256_file_and_prefix; real_file_sha=cold.sha256_file; hashed=[]
   def tracked_sha(path,prefix_bytes,*a,**k):
    hashed.append(Path(path)); return real_sha(path,prefix_bytes,*a,**k)
   def tracked_file_sha(path,*a,**k):
    hashed.append(Path(path)); return real_file_sha(path,*a,**k)
   with mock.patch.object(cold,'sha256_file_and_prefix',side_effect=tracked_sha), mock.patch.object(cold,'sha256_file',side_effect=tracked_file_sha), mock.patch.object(cold,'_stream_hash',side_effect=AssertionError('member payload streamed')), mock.patch.object(store,'open_verified',side_effect=AssertionError('logical payload opened')), mock.patch.object(store,'artifact_stat',side_effect=AssertionError('artifact stat rehashed')):
    ev=child._bind_completed_core_payload_evidence(store.root,store,tx,plan,baseline)
    child._verify_completed_alias_metadata(store.root,store,[item],tx,ev)
   self.assertEqual(hashed.count(store.archive),1)
   self.assertEqual(hashed.count(store.manifest),1)
   self.assertEqual(ev['verification_basis'],'pinned_core_complete_transaction_journal')
   self.assertEqual(ev['exact_logical_verifications'][0]['logical_sha256'],item['sha256'])
   self.assertEqual(ev['exact_logical_verifications'][0]['verification_basis'],'pinned_core_complete_transaction')
 def test_encoded_receipt_binds_persisted_logical_proof_without_redecode(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td),True)
   encoded=b'encoded fixture payload'; eh=hashlib.sha256(encoded).hexdigest(); desc={'codec_version':'reversible-xz-v1','encoded_sha256':eh,'encoded_size_bytes':len(encoded),'encoded_crc32':zipfile.crc32(encoded)&0xffffffff,'recipe_id':'fixture'}
   with zipfile.ZipFile(store.archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(item['archive_member'],encoded)
   with zipfile.ZipFile(store.archive) as z: records=cold._zip_records_all(z); info=z.getinfo(item['archive_member'])
   item.update({'storage_encoding':desc,'storage_decision':{'selected':'reversible-xz-v1','reason':'fixture'},'logical_verification':{'protocol':cold._CODEC_PROOF_PROTOCOL,'verifier_source_sha256':cold._IMPORTED_SOURCE_SHA256,'logical_sha256':item['sha256'],'logical_bytes':item['bytes'],'logical_crc32':item['crc32'],'storage_descriptor_sha256':cold._sha_bytes(json.dumps(desc,sort_keys=True,separators=(',',':')).encode())},'header_offset':info.header_offset})
   manifest=json.loads(store.manifest.read_text());manifest['zip_records']=records;manifest['archive_bytes']=store.archive.stat().st_size;manifest['archive_sha256']=hashlib.sha256(store.archive.read_bytes()).hexdigest();manifest['members'][0].update({'storage_encoding':desc,'header_offset':info.header_offset});store.manifest.write_text(json.dumps(manifest,sort_keys=True))
   j=json.loads((store.journals/tx/'journal.json').read_text());j.update({'storage_codec_policy':'reversible-xz-v1','member_records_after':records,'archive_bytes_after':store.archive.stat().st_size,'manifest_sha256':hashlib.sha256(store.manifest.read_bytes()).hexdigest(),'archive_sha256_after':manifest['archive_sha256']});j['items']=[item];(store.journals/tx/'journal.json').write_text(json.dumps(j,sort_keys=True));store.storage_codec_policy='reversible-xz-v1'
   plan=[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}]
   with mock.patch.object(store,'_has_completed_logical_verification',return_value=True), mock.patch.object(cold,'_stream_hash',side_effect=AssertionError('member payload streamed')), mock.patch.object(store,'open_verified',side_effect=AssertionError('logical payload decoded')), mock.patch.object(store,'artifact_stat',side_effect=AssertionError('archive rehashed')):
    ev=child._bind_completed_core_payload_evidence(store.root,store,tx,plan,baseline);child._verify_completed_alias_metadata(store.root,store,[item],tx,ev)
   self.assertEqual(ev['encoded_model_count'],1);self.assertEqual(ev['exact_logical_verifications'][0]['physical_sha256'],eh)
 def test_unfinished_journal_rejected(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td)); p=store.journals/tx/'journal.json';j=json.loads(p.read_text());j['state']='archive_committed';p.write_text(json.dumps(j))
   with self.assertRaises(RuntimeError): child._bind_completed_core_payload_evidence(store.root,store,tx,[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}],baseline)
 def test_manifest_member_mutation_rejected(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td));m=json.loads(store.manifest.read_text());m['members'][0]['sha256']='d'*64;store.manifest.write_text(json.dumps(m,sort_keys=True));j=json.loads((store.journals/tx/'journal.json').read_text());j['manifest_sha256']=hashlib.sha256(store.manifest.read_bytes()).hexdigest();(store.journals/tx/'journal.json').write_text(json.dumps(j))
   with self.assertRaises(RuntimeError): child._bind_completed_core_payload_evidence(store.root,store,tx,[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}],baseline)
 def test_alias_must_be_absent_and_bound(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td),True);ev=child._bind_completed_core_payload_evidence(store.root,store,tx,[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}],baseline)
   alias=store.root/item['aliases'][1];alias.parent.mkdir(parents=True);alias.write_bytes(b'leftover')
   with self.assertRaises(RuntimeError): child._verify_completed_alias_metadata(store.root,store,[item],tx,ev)
 def test_same_size_member_bitflip_is_detected_by_fresh_archive_sha(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td));
   with zipfile.ZipFile(store.archive) as z: before=cold._zip_records_all(z); info=z.getinfo(item['archive_member']); data_offset=info.header_offset+30+len(info.filename.encode())+len(info.extra)
   with open(store.archive,'r+b') as f:
    f.seek(data_offset); old=f.read(1); f.seek(data_offset); f.write(bytes([old[0]^1])); f.flush()
   with zipfile.ZipFile(store.archive) as z: self.assertEqual(cold._zip_records_all(z),before)
   with self.assertRaisesRegex(RuntimeError,'cold ZIP differs from committed member manifest|fresh post-commit archive SHA'):
    child._bind_completed_core_payload_evidence(store.root,store,tx,[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}],baseline)
 def test_candidate_identity_mismatches_are_rejected(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td));base={'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}
   mutations=[{'recorded_artifact_sha256':'f'*64},{'source_relpath':'runtime_20261025/artifacts/wrong/pipeline.joblib'},{'aliases':[]}]
   for mutation in mutations:
    with self.subTest(mutation=mutation):
     candidate=dict(base);candidate.update(mutation)
     with self.assertRaises(RuntimeError): child._bind_completed_core_payload_evidence(store.root,store,tx,[candidate],baseline)
 def test_unindexed_archive_change_rejected(self):
  with tempfile.TemporaryDirectory(prefix='postcommit-fixture-') as td:
   store,tx,baseline,item=setup_case(Path(td));
   with open(store.archive,'ab') as f:f.write(b'changed')
   with self.assertRaises((RuntimeError,zipfile.BadZipFile)): child._bind_completed_core_payload_evidence(store.root,store,tx,[{'source_relpath':item['logical_path'],'recorded_artifact_sha256':item['sha256'],'bytes':item['bytes'],'aliases':item['aliases']}],baseline)
if __name__=='__main__':unittest.main(verbosity=2)
