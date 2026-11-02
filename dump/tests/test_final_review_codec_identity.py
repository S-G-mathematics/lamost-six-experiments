import json,sys,tempfile,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"source"))
import final_review as fr

class FakeStore:
    def __init__(self,manifest,info): self.manifest=manifest;self.info=info
    def artifact_stat(self,logical,expected):
        if expected!=self.info["sha256"]: raise ValueError("expected logical SHA mismatch")
        return dict(self.info)

class ReviewCodecTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.logical="runtime_20261025/artifacts/k/pipeline.joblib"
        self.desc={"codec_version":"lamost-reversible-joblib-xz/1","format":"xz-preset-3-of-raw-zlib-joblib-payload",
          "original_sha256":"a"*64,"original_size_bytes":100,"original_zlib_header_hex":"785e",
          "raw_payload_sha256":"b"*64,"raw_payload_size_bytes":300,"encoded_sha256":"c"*64,
          "encoded_size_bytes":40,"encoded_xz_header_hex":"fd377a585a00","zlib_compile_version":"1.3",
          "zlib_runtime_version":"1.3","zlib_params":{"level":3,"method":8,"wbits":15,"memlevel":8,"strategy":0},
          "joblib_compressor_source_sha256":"d"*64,"lzma_format":"FORMAT_XZ","lzma_preset":3,
          "original_crc32":11,"encoded_crc32":22}
        self.row={"logical_path":self.logical,"task_key":"k","task_sha256":"t"*64,
          "archive_member":self.logical,"sha256":"a"*64,"bytes":100,"crc32":11,"header_offset":31,
          "aliases":["runtime_20261025/artifacts/alias/pipeline.joblib"],"storage_encoding":self.desc}
        self.info={"logical_path":self.logical,"canonical_logical_path":self.logical,"requested_logical_path":self.logical,
          "resolved_from_alias":False,"size":100,"mtime_ns":123,"sha256":"a"*64,"logical_crc32":11,
          "backing":"cold_zip","archive_member":self.logical,"member_sha256":"c"*64,"member_size":40,
          "member_crc32":22,"member_header_offset":31,"storage_format":self.desc["codec_version"],
          "payload_sha256":"c"*64,"payload_size":40,"payload_crc32":22,"storage_encoding":self.desc,
          "cache_identity":{"recipe_sha256":fr._cold_codec_recipe_sha(self.desc)}}
        self.manifest=self.root/"cold.json";self.write_manifest([self.row])
    def write_manifest(self,members):
        self.manifest.write_text(json.dumps({"schema_version":"lamost-cold-model-store/1","members":members}))
    def call(self,row=None,info=None,expected=None,cache=None):
        path=self.root/self.logical
        return fr.file_record(path,self.root,"artifact",{},cold_store=FakeStore(self.manifest,info or self.info),
            cold_members={self.logical:row or self.row},expected_sha256=expected or "a"*64,cache_observation=cache)
    def test_01_encoded_valid_binds_logical_and_physical(self):
        out=self.call();m=out["cold_member_identity"]
        self.assertEqual((out["sha256"],out["bytes"]),("a"*64,100))
        self.assertEqual((m["member_sha256"],m["member_bytes"]),("c"*64,40))
        self.assertEqual((m["logical_sha256"],m["logical_bytes"]),("a"*64,100))
    def test_02_expected_sha_is_logical(self):
        with self.assertRaises(fr.ReviewError):self.call(expected="c"*64)
    def test_03_tampered_source_descriptor_candidate_binding_fails(self):
        bad=dict(self.desc);bad["encoded_sha256"]="f"*64
        row=dict(self.row,storage_encoding=bad)
        with self.assertRaises(fr.ReviewError):self.call(row=row)
    def test_04_tampered_physical_sha_fails(self):
        info=dict(self.info,member_sha256="f"*64)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_05_tampered_physical_size_fails(self):
        info=dict(self.info,member_size=41)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_06_tampered_physical_crc_fails(self):
        info=dict(self.info,member_crc32=23)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_07_tampered_zip_header_fails(self):
        info=dict(self.info,member_header_offset=32)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_08_tampered_recipe_cache_binding_fails(self):
        info=dict(self.info,cache_identity={"recipe_sha256":"e"*64})
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_09_changed_descriptor_from_store_fails(self):
        info=dict(self.info,storage_encoding={**self.desc,"lzma_preset":2})
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_10_logical_sha_from_store_fails(self):
        info=dict(self.info,sha256="f"*64)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_11_logical_size_from_store_fails(self):
        info=dict(self.info,size=101)
        with self.assertRaises(fr.ReviewError):self.call(info=info)
    def test_12_audit_cache_logical_mismatch_fails(self):
        cache={"size":40,"mtime_ns":123,"sha256":"c"*64}
        with self.assertRaises(fr.ReviewError):self.call(cache=cache)
    def test_13_audit_cache_logical_identity_passes(self):
        cache={"size":100,"mtime_ns":123,"sha256":"a"*64}
        self.assertEqual(self.call(cache=cache)["sha256"],"a"*64)
    def test_14_alias_request_is_preserved(self):
        alias=self.row["aliases"][0]
        info=dict(self.info,requested_logical_path=alias,canonical_logical_path=self.logical,resolved_from_alias=True)
        out=fr.cold_member_identity(info,self.row,alias)
        self.assertEqual(out["logical_source_path"],alias)
        self.assertEqual(out["canonical_logical_path"],self.logical)
        self.assertTrue(out["resolved_from_alias"])
    def test_15_cold_index_rejects_descriptor_logical_mismatch(self):
        row=dict(self.row,storage_encoding={**self.desc,"original_sha256":"f"*64})
        self.write_manifest([row])
        with self.assertRaises(fr.ReviewError):fr.cold_member_index(FakeStore(self.manifest,self.info))
    def test_16_raw_member_identity_keeps_legacy_shape(self):
        row={k:v for k,v in self.row.items() if k!="storage_encoding"}
        info={k:v for k,v in self.info.items() if k not in {"storage_encoding","storage_format"}}
        info.update({"sha256":"a"*64,"size":100,"member_sha256":"a"*64,"member_size":100,"member_crc32":11})
        out=fr.cold_member_identity(info,row,self.logical)
        self.assertNotIn("logical_sha256",out);self.assertNotIn("storage_encoding",out)
        self.assertEqual(out["member_sha256"],"a"*64)
    def test_17_missing_encoded_descriptor_recipe_fails_closed(self):
        row=dict(self.row);row.pop("storage_encoding")
        info=dict(self.info);info.pop("storage_encoding")
        with self.assertRaises(fr.ReviewError):self.call(row=row,info=info)

if __name__=="__main__":
 import unittest
 unittest.main()
