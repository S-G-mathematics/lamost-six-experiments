import hashlib, json, pathlib, tempfile, unittest, zipfile, zlib
from unittest.mock import patch
import sys

STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/"source"))
import reversible_joblib_codec as codec
import cold_codec_storage as storage
import cold_model_storage as cold
import joblib, joblib.compressor
sys.path.insert(0,str(STAGE/"tests"))
from test_cold_model_storage import setup_store
from cold_finalizer_codec_contract import materialize_encoded_alias
from extracted_cold_source import ExtractedColdSource, ExtractedColdError

class CodecPayload12DataPlaneTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.td.name)
        self.temp=self.root/"tmp";self.temp.mkdir()
        self.source=self.root/"fixture.joblib"
        raw=(b"small deterministic synthetic fixture\n"*2048)+bytes(range(256))
        self.original=zlib.compress(raw,level=3)
        self.source.write_bytes(self.original)
        self.compressor=self.root/"compressor.py"
        self.compressor.write_text("tiny pinned compressor fixture")
        sha=hashlib.sha256(self.compressor.read_bytes()).hexdigest()
        self.patch=patch.object(codec,"SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256",sha)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.td.cleanup)

    def test_payload12_descriptor_archive_readback_and_alias_are_lossless(self):
        member="runtime_20261025/cold_models/e3/rep_1/pipeline.joblib.member"
        payload,row=storage.encode_entry_payload(
            self.source,archive_member=member,temp_root=self.temp,
            joblib_compressor_source_path=self.compressor,
            storage_codec_policy=storage.PAYLOAD12_STORAGE_CODEC_POLICY,
            chunk_bytes=1024)
        desc=row["storage_encoding"]
        self.assertEqual(desc["storage_codec_policy"],storage.PAYLOAD12_STORAGE_CODEC_POLICY)
        self.assertEqual(desc["max_payload_bytes"],12<<30)
        self.assertEqual(row["sha256"],hashlib.sha256(self.original).hexdigest())
        archive=self.root/"models.zip"
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED) as z:
            storage.append_encoded_payload(z,payload,row,chunk_bytes=1024)
        with zipfile.ZipFile(archive) as z:
            row["header_offset"]=z.getinfo(member).header_offset
        with storage.open_logical_member(
            archive,row,temp_root=self.temp,
            joblib_compressor_source_path=self.compressor,chunk_bytes=1024) as logical:
            self.assertEqual(logical.read(),self.original)
        result=materialize_encoded_alias(
            payload,"restored.joblib",row,output_root=self.root,
            temp_root=self.temp,joblib_compressor_source_path=self.compressor,
            chunk_bytes=1024)
        self.assertEqual(result["status"],"materialized")
        self.assertEqual((self.root/"restored.joblib").read_bytes(),self.original)

    def test_extracted_reader_uses_persisted_payload12_cap_and_manifest_projection(self):
        member="runtime_20261025/cold_models/e3/rep_1/pipeline.joblib.member"
        pinned_compressor=pathlib.Path(joblib.compressor.__file__)
        pinned_sha=hashlib.sha256(pinned_compressor.read_bytes()).hexdigest()
        with patch.object(codec,"SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256",pinned_sha):
            payload,fields=storage.encode_entry_payload(
                self.source,archive_member=member,temp_root=self.temp,
                joblib_compressor_source_path=pinned_compressor,
                storage_codec_policy=storage.PAYLOAD12_STORAGE_CODEC_POLICY,
                chunk_bytes=1024)
        extracted_payload=self.root/member
        extracted_payload.parent.mkdir(parents=True,exist_ok=True)
        payload.rename(extracted_payload)
        physical=extracted_payload.read_bytes()
        logical=fields["storage_encoding"]
        projection=self.root/"members.json"
        row={"logical_source_path":member,"archive_member":member,
             "canonical_logical_path":member,"task_key":"e3/rep_1/fit/real/random_forest",
             "task_sha256":"a"*64,"member_sha256":hashlib.sha256(physical).hexdigest(),
             "member_bytes":len(physical),"member_crc32":zlib.crc32(physical)&0xffffffff,
             "logical_sha256":fields["sha256"],"logical_bytes":fields["bytes"],
             "logical_crc32":fields["crc32"],"storage_encoding":logical,
             "storage_format":logical["codec_version"],"resolved_from_alias":False,
             "aliases":[]}
        projection.write_text(json.dumps({"schema_version":"lamost-cold-model-membership-snapshot/1",
                                          "members":[row]}))
        extracted=ExtractedColdSource(
            self.root,self.root,self.temp,
            STAGE/"source"/"reversible_joblib_codec.py",pinned_compressor,
            projection_path=projection)
        with extracted.open(member,fields["sha256"]) as decoded:
            self.assertEqual(decoded.read(),self.original)
        row["storage_encoding"]["max_payload_bytes"]=2<<30
        projection.write_text(json.dumps({"schema_version":"lamost-cold-model-membership-snapshot/1",
                                          "members":[row]}))
        with self.assertRaises(ExtractedColdError):
            with ExtractedColdSource(
                self.root,self.root,self.temp,
                STAGE/"source"/"reversible_joblib_codec.py",pinned_compressor,
                projection_path=projection).open(member,fields["sha256"]):
                self.fail("mismatched persisted cap was accepted")

    def test_cold_store_commit_persists_and_reads_payload12_descriptor(self):
        with tempfile.TemporaryDirectory(dir=STAGE/"tests") as td:
            root,runtime,base_store,key,source,alias,obj,digest,records,item=setup_store(td)
            joblib.dump({"fixture":"payload12-store","blob":b"A"*(1<<20)},source,compress=3)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            for result_path in [source.parent/"fit_result.json",
                                source.parent/"attempts"/"fixture_attempt_01"/"attempt.json"]:
                result=json.loads(result_path.read_text())
                result["result"]["pipeline_sha256"]=digest
                result_path.write_text(json.dumps(result,sort_keys=True))
            publication_path=source.parent/"fit_publication.json"
            attempt_publication_path=source.parent/"attempts"/"fixture_attempt_01"/"fit_publication.json"
            publication=json.loads(publication_path.read_text())
            publication["pipeline_sha256"]=digest
            publication_path.write_text(json.dumps(publication,sort_keys=True))
            attempt_publication=json.loads(attempt_publication_path.read_text())
            attempt_publication["pipeline_sha256"]=digest
            attempt_publication_path.write_text(json.dumps(attempt_publication,sort_keys=True))
            fit=records[key]
            fit["result"]["result"]["pipeline_sha256"]=digest
            fit["result"]["validation"]["files"]["pipeline.joblib"]=digest
            item["source_sha256"]=digest
            item["recorded_artifact_sha256"]=digest
            compressor=pathlib.Path(joblib.compressor.__file__)
            pinned_sha=hashlib.sha256(compressor.read_bytes()).hexdigest()
            with patch.object(codec,"SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256",pinned_sha):
                store=cold.ColdModelStore(
                    root,runtime,base_store.archive,base_store.manifest,base_store.journals,
                    joblib_compressor_source_path=compressor,
                    storage_codec_policy=storage.PAYLOAD12_STORAGE_CODEC_POLICY)
                tx=store.commit_models([item],records)
                manifest=json.loads(store.manifest.read_text())
                saved=manifest["members"][0]
                self.assertEqual(saved["storage_encoding"]["storage_codec_policy"],
                                 storage.PAYLOAD12_STORAGE_CODEC_POLICY)
                self.assertEqual(saved["storage_encoding"]["max_payload_bytes"],12<<30)
                self.assertFalse(source.exists());self.assertFalse(alias.exists())
                with store.open_verified(item["source_relpath"],digest) as logical:
                    self.assertEqual(hashlib.sha256(logical.read()).hexdigest(),digest)
                self.assertEqual(store.load_joblib(item["source_relpath"],digest)["fixture"],
                                 "payload12-store")
                self.assertEqual(store.recover(tx,records),"complete")

    def test_legacy_and_payload12_policy_bounds_are_separate(self):
        self.assertEqual(storage.codec_payload_limit(),2<<30)
        self.assertEqual(storage.codec_payload_limit(storage.LEGACY_STORAGE_CODEC_POLICY),2<<30)
        self.assertEqual(storage.codec_payload_limit(
            storage.PAYLOAD12_STORAGE_CODEC_POLICY,12<<30),12<<30)
        for policy,cap in [
            ("unknown-policy",None),
            (storage.LEGACY_STORAGE_CODEC_POLICY,12<<30),
            (storage.PAYLOAD12_STORAGE_CODEC_POLICY,2<<30),
            (storage.PAYLOAD12_STORAGE_CODEC_POLICY,13<<30),
        ]:
            with self.subTest(policy=policy,cap=cap),self.assertRaises(storage.StorageFormatError):
                storage.codec_payload_limit(policy,cap)

    def test_default_and_legacy_encoded_limit_cannot_be_widened(self):
        with self.assertRaises(storage.StorageFormatError):
            storage.encode_entry_payload(
                self.source,archive_member="x/member",temp_root=self.temp,
                joblib_compressor_source_path=self.compressor,
                max_payload_bytes=(2<<30)+1)
        with self.assertRaises(storage.StorageFormatError):
            storage.encode_entry_payload(
                self.source,archive_member="x/member",temp_root=self.temp,
                joblib_compressor_source_path=self.compressor,
                storage_codec_policy=storage.LEGACY_STORAGE_CODEC_POLICY,
                max_payload_bytes=1<<30)
        with self.assertRaises(storage.StorageFormatError):
            storage.encode_entry_payload(
                self.source,archive_member="x/member",temp_root=self.temp,
                joblib_compressor_source_path=self.compressor,
                storage_codec_policy=storage.PAYLOAD12_STORAGE_CODEC_POLICY,
                max_payload_bytes=13<<30)

if __name__=="__main__":
    unittest.main()
