import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile
from dataclasses import dataclass
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
SOURCE=HERE/"source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location("e1_locator_adapter_fixture",SOURCE/"cold_finalizer_adapter.py")
adapter=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=adapter
spec.loader.exec_module(adapter)

@dataclass(frozen=True)
class Entry:
    source: object
    member: str
    category: str="fixture"

class Finalizer:
    Entry=Entry
    @staticmethod
    def sha_file(path):
        h=hashlib.sha256()
        with Path(path).open("rb") as f:
            for chunk in iter(lambda:f.read(65536),b""):
                h.update(chunk)
        return h.hexdigest()

def crc_hex(data):
    return f"{zipfile.crc32(data)&0xffffffff:08x}"

class E1LocatorArchiveStreamTests(unittest.TestCase):
    def make_fixture(self, rows_override=None, duplicate_zip=False):
        td=tempfile.TemporaryDirectory()
        root=Path(td.name)
        (root/"packages").mkdir()
        (root/"e1_recovery_20261024").mkdir()
        archive=root/"packages"/"frozen_e1.zip"
        payloads={
            "recovery/run1/model.joblib":b"small engineering-only model payload",
            "recovery/run1/test_predictions.npz":b"small engineering-only prediction payload",
        }
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED) as z:
            for name,data in payloads.items():
                z.writestr(name,data)
            if duplicate_zip:
                z.writestr("recovery/run1/model.joblib",payloads["recovery/run1/model.joblib"])
        archive_sha=Finalizer.sha_file(archive)
        rows=[]
        with zipfile.ZipFile(archive) as z:
            for name,data in payloads.items():
                info=z.getinfo(name)
                rows.append({"local_path":str(root/"e1_recovery_20261024"/"restored"/name),"archive_member":name,
                             "sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),
                             "crc32":f"{info.CRC:08x}"})
        if rows_override is not None:
            rows=rows_override(rows,payloads)
        locator={"schema":"retained-recovery-payload-locators/1","study_status":"fixture",
                 "archive_path":str(archive),"archive_sha256":archive_sha,"files":rows}
        locator_path=root/"e1_recovery_20261024"/"ARCHIVED_PAYLOAD_LOCATORS_20261028.json"
        locator_path.write_text(json.dumps(locator,sort_keys=True),encoding="utf-8")
        receipt={"archive":str(archive),"archive_bytes":archive.stat().st_size,
                 "archive_sha256":archive_sha,"zip_crc_passed":True}
        receipt_path=archive.with_name(archive.stem+".receipt.json")
        receipt_path.write_text(json.dumps(receipt,sort_keys=True),encoding="utf-8")
        args=(Finalizer,root,locator_path,Finalizer.sha_file(locator_path),archive_sha,
              adapter._stat5(archive),Finalizer.sha_file(receipt_path),archive.name)
        return td,root,archive,locator_path,payloads,args

    def build(self,args,**kwargs):
        kwargs.setdefault("expected_file_count",2)
        kwargs.setdefault("expected_extension_counts",{".joblib":1,".npz":1})
        return adapter.e1_locator_archive_entries(*args,**kwargs)

    def test_valid_members_stream_byte_exact_and_account_for_logical_sizes(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        entries,manifest=self.build(args)
        physical,aliases=adapter._dedup(Finalizer,entries,{},[])
        self.assertEqual(len(physical),2)
        self.assertEqual(aliases,[])
        self.assertEqual(sum(size for _,size,_ in physical),sum(map(len,payloads.values())))
        self.assertEqual(json.loads(manifest)["payload_count"],2)
        for entry,size,digest in physical:
            self.assertTrue(entry.member.startswith("e1_recovery_20261024/restored/"))
            with adapter._source_stream(entry.source) as src:
                raw=src.read()
            self.assertEqual(len(raw),size)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            self.assertEqual(raw,payloads[entry.source.member])

    def test_collect_full_adds_all_locator_members_at_original_logical_paths(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        runtime=root/"runtime_20261025";(runtime/"manifests").mkdir(parents=True)
        safety=types.ModuleType("finalization_safety")
        for name in ("PortableBundleError","PortableTestFailure","portable_bundle_snapshot","finalization_fingerprint",
                     "begin_finalization_attempt","finish_finalization_attempt","run_portable_test_bundle",
                     "portable_receipt_matches","portable_pass_receipt_path","is_resource_backoff","clear_finalization_latch"):
            setattr(safety,name,type(name,(Exception,),{}) if name.endswith("Error") or name.endswith("Failure") else (lambda *a,**k:None))
        histories=types.ModuleType("archive_scientific_histories")
        histories.collect_scientific_attempt_entries=lambda *a,**k:([],b"{}")
        with mock.patch.dict(sys.modules,{"finalization_safety":safety,"archive_scientific_histories":histories,
                                         "cold_finalizer_adapter":adapter}):
            spec=importlib.util.spec_from_file_location("e1_collect_fixture_finalizer",SOURCE/"finalize_project.py")
            finalizer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=finalizer
            spec.loader.exec_module(finalizer)
            finalizer.curated_tree_entries=lambda *a,**k:[]
            finalizer.iterfiles=lambda *a,**k:[]
            finalizer._add_public_provenance=lambda *a,**k:None
            finalizer.E1_ARCHIVED_PAYLOAD_LOCATOR="e1_recovery_20261024/ARCHIVED_PAYLOAD_LOCATORS_20261028.json"
            finalizer.E1_ARCHIVED_PAYLOAD_LOCATOR_SHA256=args[3]
            finalizer.E1_ARCHIVED_PAYLOAD_ARCHIVE_NAME=archive.name
            finalizer.E1_ARCHIVED_PAYLOAD_ARCHIVE_SHA256=args[4]
            finalizer.E1_ARCHIVED_PAYLOAD_ARCHIVE_STAT5=args[5]
            finalizer.E1_ARCHIVED_PAYLOAD_RECEIPT_SHA256=args[6]
            finalizer.E1_ARCHIVED_PAYLOAD_COUNTS={".joblib":1,".npz":1}
            finalizer.E1_ARCHIVED_PAYLOAD_FILE_COUNT=2
            entries=finalizer.collect_full(root,runtime,b"fixture readme",b'{"tasks":[]}',registry_records={})
            payload_entries=[e for e in entries if e.category=="E1_archived_recovery_payload"]
            self.assertEqual(len(payload_entries),2)
            self.assertIn("runtime_20261025/manifests/e1_recovery_archived_payload_provenance.json",
                          {e.member for e in entries})
            phys,_=adapter._dedup(finalizer,payload_entries,{},[])
            self.assertEqual(len(phys),2)
            for e,_,_ in phys:
                self.assertTrue(e.member.startswith("e1_recovery_20261024/restored/recovery/run1/"))
            sys.modules.pop(spec.name,None)

    def test_locator_sha_mismatch_fails_closed(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build((args[0],args[1],args[2],"0"*64,*args[4:]))

    def test_member_sha_mismatch_fails_before_append_stream(self):
        def alter(rows,payloads):
            rows[0]["sha256"]="0"*64
            return rows
        td,root,archive,locator,payloads,args=self.make_fixture(alter)
        self.addCleanup(td.cleanup)
        entries,_=self.build(args)
        with self.assertRaises(adapter.ColdFinalizerError):
            adapter._dedup(Finalizer,entries,{},[])

    def test_member_crc_mismatch_fails_closed(self):
        def alter(rows,payloads):
            rows[0]["crc32"]="00000000"
            return rows
        td,root,archive,locator,payloads,args=self.make_fixture(alter)
        self.addCleanup(td.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args)

    def test_member_size_mismatch_fails_closed(self):
        def alter(rows,payloads):
            rows[0]["bytes"]+=1
            return rows
        td,root,archive,locator,payloads,args=self.make_fixture(alter)
        self.addCleanup(td.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args)

    def test_traversal_and_duplicate_locator_paths_reject(self):
        def traverse(rows,payloads):
            rows[0]["archive_member"]="../escape.joblib"
            return rows
        td,root,archive,locator,payloads,args=self.make_fixture(traverse)
        self.addCleanup(td.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args)
        td2,root2,archive2,locator2,payloads2,args2=self.make_fixture(
            lambda rows,p: [rows[0],rows[0]])
        self.addCleanup(td2.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args2)
        def duplicate_destination(rows,payloads):
            rows[1]["local_path"]=rows[0]["local_path"]
            return rows
        td3,root3,archive3,locator3,payloads3,args3=self.make_fixture(duplicate_destination)
        self.addCleanup(td3.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args3)

    def test_corrupt_member_payload_crc_is_detected_during_stream_hash(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        with zipfile.ZipFile(archive) as z:
            info=z.getinfo("recovery/run1/model.joblib")
        with archive.open("r+b") as f:
            f.seek(info.header_offset+30+len(info.filename.encode("utf-8"))+len(info.extra))
            byte=f.read(1);f.seek(-1,1);f.write(bytes([byte[0]^1]))
        loc=json.loads(locator.read_text())
        loc["archive_sha256"]=Finalizer.sha_file(archive)
        locator.write_text(json.dumps(loc,sort_keys=True),encoding="utf-8")
        receipt_path=archive.with_name(archive.stem+".receipt.json")
        receipt=json.loads(receipt_path.read_text())
        receipt["archive_sha256"]=loc["archive_sha256"]
        receipt_path.write_text(json.dumps(receipt,sort_keys=True),encoding="utf-8")
        args=list(args);args[3]=Finalizer.sha_file(locator);args[4]=loc["archive_sha256"]
        args[5]=adapter._stat5(archive);args[6]=Finalizer.sha_file(receipt_path)
        entries,_=self.build(tuple(args))
        with self.assertRaises(adapter.ColdFinalizerError):
            adapter._dedup(Finalizer,entries,{},[])

    def test_missing_payload_and_duplicate_zip_member_reject(self):
        def missing(rows,payloads):
            rows[0]["archive_member"]="recovery/not_present.joblib"
            return rows
        td,root,archive,locator,payloads,args=self.make_fixture(missing)
        self.addCleanup(td.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args)
        td2,root2,archive2,locator2,payloads2,args2=self.make_fixture(duplicate_zip=True)
        self.addCleanup(td2.cleanup)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(args2)

    def test_symlink_archive_and_symlink_member_reject(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        target=archive.with_name("frozen_target.zip")
        archive.rename(target);archive.symlink_to(target)
        loc=json.loads(locator.read_text());loc["archive_path"]=str(archive)
        locator.write_text(json.dumps(loc,sort_keys=True),encoding="utf-8")
        receipt_path=archive.with_name(archive.stem+".receipt.json")
        receipt=json.loads(receipt_path.read_text());receipt["archive"]=str(archive)
        receipt_path.write_text(json.dumps(receipt,sort_keys=True),encoding="utf-8")
        args=list(args);args[3]=Finalizer.sha_file(locator);args[5]=adapter._stat5(target)
        args[6]=Finalizer.sha_file(receipt_path)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(tuple(args))
        td2,root2,archive2,locator2,payloads2,args2=self.make_fixture()
        self.addCleanup(td2.cleanup)
        with zipfile.ZipFile(archive2,"a") as z:
            info=zipfile.ZipInfo("recovery/run1/link.joblib")
            info.external_attr=(0o120777<<16)
            z.writestr(info,b"recovery/run1/model.joblib")
        loc2=json.loads(locator2.read_text())
        link=b"recovery/run1/model.joblib"
        loc2["files"].append({"local_path":str(root2/"e1_recovery_20261024"/"restored"/"recovery/run1/link.joblib"),
             "archive_member":"recovery/run1/link.joblib","sha256":hashlib.sha256(link).hexdigest(),
             "bytes":len(link),"crc32":crc_hex(link)})
        loc2["archive_sha256"]=Finalizer.sha_file(archive2)
        locator2.write_text(json.dumps(loc2,sort_keys=True),encoding="utf-8")
        recp=archive2.with_name(archive2.stem+".receipt.json")
        rec=json.loads(recp.read_text());rec["archive_sha256"]=loc2["archive_sha256"];rec["archive_bytes"]=archive2.stat().st_size
        recp.write_text(json.dumps(rec,sort_keys=True),encoding="utf-8")
        args2=list(args2);args2[3]=Finalizer.sha_file(locator2);args2[4]=loc2["archive_sha256"]
        args2[5]=adapter._stat5(archive2);args2[6]=Finalizer.sha_file(recp)
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(tuple(args2),expected_file_count=3,expected_extension_counts={".joblib":2,".npz":1})

    def test_outer_archive_sha_and_five_stat_pins_are_enforced(self):
        td,root,archive,locator,payloads,args=self.make_fixture()
        self.addCleanup(td.cleanup)
        wrong=list(args);wrong[4]="f"*64
        with self.assertRaises(adapter.ColdFinalizerError):
            self.build(tuple(wrong))
        entries,_=self.build(args)
        src=entries[0].source
        archive.touch()
        with self.assertRaises(adapter.ColdFinalizerError):
            src.stat()

if __name__=="__main__":
    unittest.main()
