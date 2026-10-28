import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"source"))
from cold_finalizer_codec_contract import stat_projection, inventory_member, FinalizerCodecError
import cold_finalizer_adapter as adapter
import restore_archive_aliases_codec_template as restorer

class Info:
    filename="runtime_20261025/artifacts/k/pipeline.joblib"
    def __init__(self,size,crc,offset=27): self.file_size=size;self.CRC=crc;self.header_offset=offset

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.raw={"sha256":"a"*64,"bytes":100,"crc32":10,"archive_member":Info.filename,"header_offset":27}
        self.enc={"codec_version":"lamost-reversible-joblib-xz/1","encoded_sha256":"b"*64,
          "encoded_size_bytes":40,"encoded_crc32":20,"original_crc32":10}
    def test_01_legacy_projection(self):
        x=stat_projection(self.raw,{"sha256":"a"*64,"size":100,"logical_crc32":10,
          "payload_sha256":"a"*64,"payload_size":100,"payload_crc32":10,"archive_member":Info.filename})
        self.assertEqual(x["storage_format"],"raw-v1");self.assertEqual(x["logical_sha256"],x["member_sha256"])
    def test_02_encoded_projection(self):
        row={**self.raw,"storage_encoding":self.enc}
        x=stat_projection(row,{"sha256":"a"*64,"size":100,"logical_crc32":10,
          "payload_sha256":"b"*64,"payload_size":40,"payload_crc32":20,
          "storage_format":self.enc["codec_version"],"archive_member":Info.filename})
        self.assertEqual((x["logical_bytes"],x["member_bytes"]),(100,40))
    def test_03_logical_sha_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection(self.raw,{"sha256":"x","size":100})
    def test_04_logical_size_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection(self.raw,{"sha256":"a"*64,"size":101})
    def test_05_encoded_payload_sha_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection({**self.raw,"storage_encoding":self.enc},
          {"sha256":"a"*64,"size":100,"payload_sha256":"x","payload_size":40,"payload_crc32":20,"storage_format":self.enc["codec_version"]})
    def test_06_encoded_payload_size_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection({**self.raw,"storage_encoding":self.enc},
          {"sha256":"a"*64,"size":100,"payload_sha256":"b"*64,"payload_size":41,"payload_crc32":20,"storage_format":self.enc["codec_version"]})
    def test_07_encoded_payload_crc_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection({**self.raw,"storage_encoding":self.enc},
          {"sha256":"a"*64,"size":100,"payload_sha256":"b"*64,"payload_size":40,"payload_crc32":21,"storage_format":self.enc["codec_version"]})
    def test_08_encoded_codec_mismatch(self):
        with self.assertRaises(FinalizerCodecError):stat_projection({**self.raw,"storage_encoding":self.enc},
          {"sha256":"a"*64,"size":100,"payload_sha256":"b"*64,"payload_size":40,"payload_crc32":20,"storage_format":"other"})
    def test_09_encoded_inventory(self):
        x=inventory_member(Info(40,20),{**self.raw,"storage_encoding":self.enc},"b"*64)
        self.assertEqual((x["bytes"],x["logical_bytes"]),(40,100))
    def test_10_encoded_inventory_bad_length(self):
        with self.assertRaises(FinalizerCodecError):inventory_member(Info(41,20),{**self.raw,"storage_encoding":self.enc},"b"*64)
    def test_11_encoded_inventory_bad_sha(self):
        with self.assertRaises(FinalizerCodecError):inventory_member(Info(40,20),{**self.raw,"storage_encoding":self.enc},"c"*64)
    def test_12_encoded_inventory_bad_crc(self):
        with self.assertRaises(FinalizerCodecError):inventory_member(Info(40,21),{**self.raw,"storage_encoding":self.enc},"b"*64)
    def test_13_legacy_inventory(self):
        x=inventory_member(Info(100,10),self.raw,"a"*64);self.assertEqual(x["logical_sha256"],"a"*64)
    def test_14_legacy_inventory_bad_offset(self):
        with self.assertRaises(FinalizerCodecError):inventory_member(Info(100,10,28),self.raw,"a"*64)
    def test_15_destination_escape(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):restorer.safe(td,"../outside")
    def test_16_restorer_alias_exact_copy_or_link(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/"canonical";dst=root/"alias";src.write_bytes(b"same")
            mode=restorer._hardlink_or_copy(src,dst,4,__import__("hashlib").sha256(b"same").hexdigest())
            self.assertIn(mode,{"hardlinked","copied"});self.assertEqual(dst.read_bytes(),b"same")
    def test_17_restorer_conflicting_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/"canonical";dst=root/"alias";src.write_bytes(b"same");dst.write_bytes(b"other")
            with self.assertRaises(FileExistsError):restorer._hardlink_or_copy(src,dst,4,__import__("hashlib").sha256(b"same").hexdigest())


    def _encoded_fixture(self,td):
        import zlib,zipfile
        from cold_codec_storage import encode_entry_payload
        from reversible_joblib_codec import ZLIB_PARAMS
        root=Path(td);plain=(b"payload-for-codec-alias-fixture-"*1000)
        c=zlib.compressobj(3,zlib.DEFLATED,zlib.MAX_WBITS,zlib.DEF_MEM_LEVEL,0)
        original=c.compress(plain)+c.flush()
        source=root/"logical.joblib";source.write_bytes(original)
        compressor="/home/ubuntu/lamost_e1_migration_20261023/venv/lib/python3.12/site-packages/joblib/compressor.py"
        payload,fields=encode_entry_payload(source,archive_member="runtime_20261025/artifacts/k/pipeline.joblib",
            temp_root=root,joblib_compressor_source_path=compressor)
        row={"sha256":fields["sha256"],"bytes":fields["bytes"],"crc32":fields["crc32"],
             "storage_encoding":fields["storage_encoding"]}
        return payload,row,original,compressor
    def test_18_encoded_materialize_in_place_verifies_before_publish(self):
        from cold_finalizer_codec_contract import materialize_encoded_alias
        with tempfile.TemporaryDirectory() as td:
            payload,row,original,compressor=self._encoded_fixture(td)
            result=materialize_encoded_alias(payload,payload,row,output_root=td,temp_root=td,
                joblib_compressor_source_path=compressor)
            self.assertEqual(result["status"],"materialized")
            self.assertEqual(payload.read_bytes(),original)
    def test_19_encoded_materialize_refuses_conflict(self):
        from cold_finalizer_codec_contract import materialize_encoded_alias
        with tempfile.TemporaryDirectory() as td:
            payload,row,original,compressor=self._encoded_fixture(td)
            dest=Path(td)/"alias";dest.write_bytes(b"conflict")
            with self.assertRaises(FileExistsError):
                materialize_encoded_alias(payload,dest,row,output_root=td,temp_root=td,
                    joblib_compressor_source_path=compressor)
            self.assertTrue(payload.is_file());self.assertEqual(dest.read_bytes(),b"conflict")
    def test_20_logical_mismatch_does_not_publish(self):
        from cold_finalizer_codec_contract import materialize_encoded_alias
        with tempfile.TemporaryDirectory() as td:
            payload,row,original,compressor=self._encoded_fixture(td);dest=Path(td)/"logical"
            row=dict(row);row["sha256"]="f"*64
            with self.assertRaises(Exception):
                materialize_encoded_alias(payload,dest,row,output_root=td,temp_root=td,
                    joblib_compressor_source_path=compressor)
            self.assertFalse(dest.exists());self.assertTrue(payload.exists())


    def test_21_raw_review_projection_preserves_legacy_shape(self):
        row={**self.raw,"logical_path":Info.filename,"aliases":["alias/pipeline.joblib"],"task_key":"k"}
        st={"sha256":"a"*64,"size":100,"archive_member":Info.filename,"member_sha256":"a"*64,
            "member_size":100,"member_crc32":10,"member_header_offset":27,"mtime_ns":5}
        got=adapter._projection_for_entry(row,{"result":{"task_sha256":"t"*64}},None,Info.filename,st)
        self.assertEqual(set(got),{"logical_source_path","canonical_logical_path","resolved_from_alias","task_key",
          "task_sha256","archive_member","member_sha256","member_bytes","member_crc32","member_header_offset",
          "source_mtime_ns","aliases"})
        self.assertEqual(got["member_sha256"],"a"*64)
    def test_22_encoded_review_projection_keeps_both_identities(self):
        row={**self.raw,"logical_path":Info.filename,"aliases":[],"task_key":"k","storage_encoding":self.enc}
        st={"sha256":"a"*64,"size":100,"archive_member":Info.filename,"member_sha256":"b"*64,
            "member_size":40,"member_crc32":20,"member_header_offset":27,"mtime_ns":5,
            "logical_crc32":10,"storage_format":self.enc["codec_version"]}
        got=adapter._projection_for_entry(row,{"result":{"task_sha256":"t"*64}},None,Info.filename,st)
        self.assertEqual((got["logical_sha256"],got["logical_bytes"],got["member_sha256"],got["member_bytes"]),
                         ("a"*64,100,"b"*64,40))

if __name__ == "__main__": unittest.main()
