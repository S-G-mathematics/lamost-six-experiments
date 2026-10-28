from __future__ import annotations
import contextlib
import ast
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

SRC=Path(__file__).resolve().parents[1]/'source'

def module_from(name,path,stubs=None):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    saved={k:sys.modules.get(k) for k in (stubs or {})}
    try:
        if stubs:sys.modules.update(stubs)
        spec.loader.exec_module(mod)
    finally:
        for k,v in saved.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v
    return mod

def stub_batch_plan():
    m=types.ModuleType('batch_plan')
    m.MAX_INITIAL_BYTES=1<<30;m.MAX_INITIAL_GROUPS=8;m.MAX_LATER_BYTES=2<<30;m.MAX_LATER_GROUPS=16
    m.RAW_WIDE_MAX_BYTES=8<<30;m.RAW_WIDE_MAX_GROUPS=64;m.RAW_WIDE_PROFILE='bounded-1800-wide8gib';m.RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES=6<<30
    m.resource_admission_ready=lambda *a: True
    for n in ('build_candidates','select_batch','public_candidate_summary','require_reviewed_baseline','validate_operation_directory','verify_alias_resolution'):
        setattr(m,n,lambda *a,**k:None)
    return m

def fake_cold():
    m=types.ModuleType('cold_model_storage')
    m.sha256_file=lambda p:'0'*64
    m._stream_hash=lambda f: _stream_hash(f)
    m._manifest_load=lambda p:json.loads(Path(p).read_text())
    m._IMPORTED_SOURCE_SHA256='v'*64
    m._CODEC_PROOF_PROTOCOL='exact-original-byte-roundtrip-and-unchanged-prefix/1'
    m._sha_bytes=lambda b:__import__('hashlib').sha256(b).hexdigest()
    return m

def _stream_hash(f):
    import hashlib,zlib
    h=hashlib.sha256();n=0;c=0
    while True:
        b=f.read(65536)
        if not b:break
        h.update(b);n+=len(b);c=zlib.crc32(b,c)
    return h.hexdigest(),n,c&0xffffffff

class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bp=stub_batch_plan()
        cls.wrapper=module_from('codec_test_run_batch',SRC/'run_batch.py',{'controller':types.ModuleType('controller'),'batch_plan':bp})
        cls.child=module_from('codec_test_commit_child',SRC/'commit_batch_child.py',{'cold_model_storage':fake_cold(),'batch_plan':bp})
        cls.driver=module_from('codec_test_auto_compaction',SRC/'cold_auto_compaction.py')

    def test_wrapper_default_and_opt_in_policy_are_isolated(self):
        self.assertIsNone(self.wrapper.BATCH_POLICIES['storage-followup']['storage_codec_policy'])
        self.assertEqual(self.wrapper.BATCH_POLICIES['storage-followup']['max_bytes'],2<<30)
        self.assertEqual(self.wrapper.BATCH_POLICIES['storage-followup']['max_groups'],16)
        self.assertEqual(self.wrapper.codec_policy_args(None),[])
        p=self.wrapper.BATCH_POLICIES['storage-followup-codec']
        self.assertEqual((p['storage_codec_policy'],p['max_bytes'],p['max_groups'],p['wall_seconds']),('reversible-xz-v1',1<<30,1,600))
        self.assertEqual(self.wrapper.codec_policy_args('reversible-xz-v1'),['--storage-codec-policy','reversible-xz-v1'])

    def test_child_policy_pairing_rejects_implicit_or_mismatched_codec(self):
        self.assertIsNone(self.child.validate_storage_policy('storage-followup',None)['storage_codec_policy'])
        self.assertEqual(self.child.validate_storage_policy('storage-followup-codec','reversible-xz-v1')['max_bytes'],1<<30)
        for pair in [('storage-followup-codec',None),('storage-followup','reversible-xz-v1'),('initial','reversible-xz-v1')]:
            with self.assertRaises(ValueError):self.child.validate_storage_policy(*pair)

    def test_driver_defaults_to_raw_and_codec_flag_is_explicit(self):
        raw=self.driver.batch_config(None);encoded=self.driver.batch_config('reversible-xz-v1')
        self.assertEqual((raw['batch_policy'],raw['max_bytes'],raw['max_groups'],raw['storage_codec_policy']),('storage-followup',2<<30,16,None))
        self.assertEqual((encoded['batch_policy'],encoded['max_bytes'],encoded['max_groups'],encoded['wall_seconds']),('storage-followup-codec',1<<30,1,600))
        self.assertEqual(self.driver.codec_policy_args(None),[])
        self.assertEqual(self.driver.codec_policy_args('reversible-xz-v1'),['--storage-codec-policy','reversible-xz-v1'])
        with self.assertRaises(ValueError):self.driver.batch_config('other')

class EncodedAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.child=module_from('codec_test_alias_child',SRC/'commit_batch_child.py',{'cold_model_storage':fake_cold(),'batch_plan':stub_batch_plan()})

    def _alias_fixture(self, *, tamper=None, creator_proof=True, physical_alias=False):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);root=Path(td.name)
        canonical='runtime_20261025/artifacts/task/pipeline.joblib'
        aliases=[canonical,'runtime_20261025/artifacts/task/attempts/a/pipeline.joblib','runtime_20261025/artifacts/task/checkpoints/b/pipeline.joblib']
        tx='c'*32;logical_sha='a'*64;logical_bytes=321;logical_crc=12345
        desc={'codec_version':'reversible-xz-v1','original_sha256':logical_sha,'original_size_bytes':logical_bytes,'original_crc32':logical_crc,'encoded_sha256':'b'*64,'encoded_size_bytes':100,'encoded_crc32':9876,'recipe':'fixture'}
        proof={'protocol':self.child.cold._CODEC_PROOF_PROTOCOL,'verifier_source_sha256':self.child.cold._IMPORTED_SOURCE_SHA256,'logical_sha256':logical_sha,'logical_bytes':logical_bytes,'logical_crc32':logical_crc,'storage_descriptor_sha256':self.child.cold._sha_bytes(json.dumps(desc,sort_keys=True,separators=(',',':')).encode())}
        item={'logical_path':canonical,'archive_member':'runtime_20261025/cold_models/test.zipmember','sha256':logical_sha,'bytes':logical_bytes,'crc32':logical_crc,'header_offset':64,'storage_encoding':desc,'aliases':aliases,'logical_verification':proof if creator_proof else None}
        journals=root/'journals';(journals/tx).mkdir(parents=True);(journals/tx/'journal.json').write_text(json.dumps({'transaction_id':tx,'state':'complete','items':[item]}))
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'transaction_id':tx,'members':[{'logical_path':canonical,'transaction_id':tx,'storage_encoding':desc}]}))
        cache={'backing':'cold_zip_codec','archive_sha256':'d'*64,'archive_ctime_ns':5,'member':item['archive_member'],'header_offset':64,'payload_crc32':9876,'payload_bytes':100,'payload_sha256':'b'*64,'logical_crc32':logical_crc,'logical_bytes':logical_bytes,'logical_sha256':logical_sha,'recipe_sha256':'e'*64}
        base={'canonical_logical_path':canonical,'size':logical_bytes,'mtime_ns':10,'sha256':logical_sha,'logical_crc32':logical_crc,'backing':'cold_zip','archive_path':'/fake/archive.zip','archive_sha256':'d'*64,'archive_size_bytes':1000,'archive_mtime_ns':5,'archive_ctime_ns':5,'archive_member':item['archive_member'],'member_crc32':9876,'member_header_offset':64,'member_size':100,'member_sha256':'b'*64,'storage_format':'reversible-xz-v1','payload_crc32':9876,'payload_size':100,'payload_sha256':'b'*64,'storage_encoding':desc,'cache_identity':cache}
        stats={}
        for alias in aliases:
            stats[alias]={**base,'logical_path':alias,'requested_logical_path':alias,'resolved_from_alias':alias!=canonical}
        if tamper=='member':stats[aliases[1]]['member_sha256']='f'*64
        if tamper=='recipe':stats[aliases[1]]['storage_encoding']={**desc,'recipe':'other'}
        if physical_alias:(root/aliases[1]).parent.mkdir(parents=True);(root/aliases[1]).write_bytes(b'physical-copy')
        proofrow={'logical_sha256':logical_sha,'logical_bytes':logical_bytes,'logical_crc32':logical_crc,'storage_format':'reversible-xz-v1','physical_sha256':'b'*64,'physical_bytes':100,'physical_crc32':9876}
        evidence={'exact_logical_verifications':[{'logical_path':canonical,**proofrow}]}
        class Store:
            def __init__(self):self.journals=journals;self.manifest=manifest;self.stats_calls=[];self.full_sha_calls=0
            def _has_completed_logical_verification(self,row):return creator_proof and row.get('transaction_id')==tx and row.get('storage_encoding')==desc
            def artifact_stat(self,path,expected_sha256=None):
                self.stats_calls.append(path);row=stats[path]
                if expected_sha256!=logical_sha:raise AssertionError('wrong expected logical SHA')
                return row
            def sha256(self,*a,**k):self.full_sha_calls+=1;raise AssertionError('full decode/hash of encoded alias is prohibited in this fixture')
        return root,Store(),[item],tx,evidence,aliases

    def test_encoded_aliases_use_stat_identity_after_one_creator_logical_proof(self):
        root,store,items,tx,evidence,aliases=self._alias_fixture()
        self.child.verify_encoded_alias_resolution(root,store,items,tx,evidence)
        self.assertEqual(store.stats_calls,aliases)
        self.assertEqual(store.full_sha_calls,0)

    def test_wrong_encoded_physical_member_identity_rejected(self):
        root,store,items,tx,evidence,_=self._alias_fixture(tamper='member')
        with self.assertRaises(RuntimeError):self.child.verify_encoded_alias_resolution(root,store,items,tx,evidence)

    def test_wrong_codec_recipe_rejected(self):
        root,store,items,tx,evidence,_=self._alias_fixture(tamper='recipe')
        with self.assertRaises(RuntimeError):self.child.verify_encoded_alias_resolution(root,store,items,tx,evidence)

    def test_missing_creator_proof_or_remaining_alias_rejected(self):
        root,store,items,tx,evidence,_=self._alias_fixture(creator_proof=False)
        with self.assertRaises(RuntimeError):self.child.verify_encoded_alias_resolution(root,store,items,tx,evidence)
        root2,store2,items2,tx2,evidence2,aliases=self._alias_fixture(physical_alias=True)
        with self.assertRaises(RuntimeError):self.child.verify_encoded_alias_resolution(root2,store2,items2,tx2,evidence2)

class SourceClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bp=stub_batch_plan()
        cls.wrapper=module_from('codec_test_closure_run_batch',SRC/'run_batch.py',{'controller':types.ModuleType('controller'),'batch_plan':bp})
        cls.driver=module_from('codec_test_closure_auto_compaction',SRC/'cold_auto_compaction.py')

    def test_all_policy_dependency_pins_match_the_staged_sources(self):
        for filename,variable in [('run_batch.py','SOURCE_PINS'),('commit_batch_child.py','PINS'),('cold_auto_compaction.py','PINS')]:
            tree=ast.parse((SRC/filename).read_text())
            node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets))
            pins=ast.literal_eval(node.value)
            for name,digest in pins.items():
                path=SRC/name
                self.assertTrue(path.is_file(),f'{filename} pins missing {name}')
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest,f'{filename} pin mismatch for {name}')

    def test_codec_flag_flows_through_the_three_script_boundaries(self):
        wrapper=ast.unparse(ast.parse((SRC/'run_batch.py').read_text()))
        child=ast.unparse(ast.parse((SRC/'commit_batch_child.py').read_text()))
        driver=ast.unparse(ast.parse((SRC/'cold_auto_compaction.py').read_text()))
        self.assertIn('child_argv.extend(codec_policy_args(a.storage_codec_policy))',wrapper)
        self.assertIn('cmd.extend(codec_policy_args(storage_codec_policy))',driver)
        self.assertGreaterEqual(child.count('storage_codec_policy=args.storage_codec_policy'),2)
        self.assertIn("store.commit_models(batch, rec)",child)

    def test_resource_limits_stay_fixed_and_raw_followup_is_unchanged(self):
        self.assertEqual((self.wrapper.CHILD_WALL_SECONDS,self.wrapper.FOLLOWUP_CHILD_WALL_SECONDS), (180,600))
        self.assertEqual((self.wrapper.CHILD_AGGREGATE_RSS_BYTES,self.wrapper.CHILD_ADDRESS_SPACE_BYTES),(1<<30,896<<20))
        self.assertEqual((self.driver.TERM_GRACE,self.driver.MAX_BATCH_WALL), (30,600))
        self.assertEqual((self.driver.WRAPPER_RSS_LIMIT,self.driver.WRAPPER_AS_LIMIT),(1536<<20,1536<<20))
        raw=self.wrapper.BATCH_POLICIES['storage-followup']
        self.assertEqual((raw['max_bytes'],raw['max_groups'],raw['packing'],raw['storage_codec_policy']),(2<<30,16,'largest_first',None))

class PayloadReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.child=module_from('codec_test_payload_child',SRC/'commit_batch_child.py',{'cold_model_storage':fake_cold(),'batch_plan':stub_batch_plan()})

    def _fixture(self, *, policy, physical, logical, encoded):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);root=Path(td.name)
        archive=root/'building.zip';member='runtime_20261025/cold_models/test.zipmember'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(member,physical)
        with zipfile.ZipFile(archive,'r') as z:info=z.getinfo(member)
        import hashlib,zlib
        lsha=hashlib.sha256(logical).hexdigest();lc=zlib.crc32(logical)&0xffffffff
        psha=hashlib.sha256(physical).hexdigest();pc=zlib.crc32(physical)&0xffffffff
        desc=None
        if encoded:desc={'codec_version':'reversible-xz-v1','encoded_sha256':psha,'encoded_size_bytes':len(physical),'encoded_crc32':pc}
        item={'logical_path':'runtime_20261025/artifacts/fake/pipeline.joblib','archive_member':member,'sha256':lsha,'bytes':len(logical),'crc32':lc,'header_offset':info.header_offset,'storage_encoding':desc}
        if policy:item['storage_decision']={'selected':'reversible-xz-v1' if encoded else 'raw-v1','reason':'fixture verified codec' if encoded else 'verified no size benefit'}
        tx='t1';before='a'*64;after='b'*64
        j={'state':'complete','archive_sha256_before':before,'archive_sha256_after':after,'archive_size_before':0,'archive_bytes_after':archive.stat().st_size,'storage_codec_policy':policy,'items':[item]}
        journals=root/'journals';(journals/tx).mkdir(parents=True);(journals/tx/'journal.json').write_text(json.dumps(j))
        row={'logical_path':item['logical_path'],'sha256':lsha,'bytes':len(logical),'crc32':lc,'storage_encoding':desc}
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'transaction_id':tx,'archive_sha256':after,'archive_bytes':archive.stat().st_size,'members':[row]}))
        class Store:
            def __init__(self):self.archive=archive;self.journals=journals;self.manifest=manifest;self.storage_codec_policy=policy
            @contextlib.contextmanager
            def open_verified(self,path,expected):
                if expected!=lsha:raise RuntimeError('expected hash mismatch')
                yield io.BytesIO(logical)
        batch=[{'bytes':len(logical)}]
        return Store(),tx,batch,before

    def test_codec_receipt_separates_logical_and_physical_byte_counts(self):
        store,tx,batch,before=self._fixture(policy='reversible-xz-v1',physical=b'xzpayload',logical=b'original model payload is longer',encoded=True)
        ev=self.child._verify_batch_payloads(Path('/unused'),store,tx,batch,before)
        self.assertEqual(ev['codec_policy'],'reversible-xz-v1')
        self.assertEqual(ev['logical_source_bytes'],len(b'original model payload is longer'))
        self.assertEqual(ev['physical_payload_bytes'],len(b'xzpayload'))
        self.assertLess(ev['physical_payload_bytes'],ev['logical_source_bytes'])
        self.assertGreaterEqual(ev['archive_bytes_delta'],ev['physical_payload_bytes'])
        self.assertEqual(ev['encoded_model_count'],1)

    def test_explicit_raw_fallback_is_counted_under_codec_policy(self):
        payload=b'not compressible fixture bytes'
        store,tx,batch,before=self._fixture(policy='reversible-xz-v1',physical=payload,logical=payload,encoded=False)
        ev=self.child._verify_batch_payloads(Path('/unused'),store,tx,batch,before)
        self.assertEqual(ev['raw_fallback_count'],1);self.assertEqual(ev['encoded_model_count'],0)
        self.assertEqual(ev['logical_source_bytes'],ev['physical_payload_bytes'])

    def test_raw_legacy_receipt_remains_valid_without_codec_decision(self):
        payload=b'legacy raw member'
        store,tx,batch,before=self._fixture(policy=None,physical=payload,logical=payload,encoded=False)
        ev=self.child._verify_batch_payloads(Path('/unused'),store,tx,batch,before)
        self.assertIsNone(ev['codec_policy']);self.assertEqual(ev['raw_fallback_count'],0)

    def test_journal_policy_and_physical_corruption_fail_closed(self):
        store,tx,batch,before=self._fixture(policy='reversible-xz-v1',physical=b'xzpayload',logical=b'original longer',encoded=True)
        with zipfile.ZipFile(store.archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr('runtime_20261025/cold_models/test.zipmember',b'bad')
        with self.assertRaises(RuntimeError):self.child._verify_batch_payloads(Path('/unused'),store,tx,batch,before)

    def test_journal_policy_mismatch_fails_closed(self):
        payload=b'legacy raw member'
        store,tx,batch,before=self._fixture(policy='reversible-xz-v1',physical=payload,logical=payload,encoded=False)
        jpath=store.journals/tx/'journal.json';j=json.loads(jpath.read_text());j['storage_codec_policy']=None;jpath.write_text(json.dumps(j))
        with self.assertRaises(RuntimeError):self.child._verify_batch_payloads(Path('/unused'),store,tx,batch,before)

if __name__=='__main__':unittest.main()
