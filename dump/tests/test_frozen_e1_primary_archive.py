import hashlib, json, os, sys, zipfile
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from source import frozen_e1_primary_archive as mod

class Entry:
    def __init__(self,source,member,category):self.source=source;self.member=member;self.category=category
class Finalizer:
    Entry=Entry
    @staticmethod
    def sha_file(p):
        h=hashlib.sha256()
        with open(p,"rb") as f:
            for b in iter(lambda:f.read(1<<20),b""):h.update(b)
        return h.hexdigest()

def sha(b):return hashlib.sha256(b).hexdigest()
def stat5(p):
    s=p.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def crc(b):return "%08x"%(zipfile.crc32(b)&0xffffffff)

@pytest.fixture
def fixture_world(tmp_path):
    root=tmp_path;runtime=root/"runtime";locrel=Path(mod.LOCATOR_REL);loc=runtime/locrel;loc.parent.mkdir(parents=True)
    archive=root/mod.ARCHIVE_REL;archive.parent.mkdir(parents=True)
    rows=[];payloads=[]
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED) as z:
        for i in range(80):
            cell=f"benchmark/results/e1/rep_{i%5+1}/n_1000000/method_{i:02d}"
            for kind,suffix,data in (("primary_model","pipeline.joblib",f"model-{i}".encode()),("test_prediction_array","test_predictions.npz",f"pred-{i}".encode())):
                path="project/"+cell+"/"+suffix;z.writestr(path,data);payloads.append((path,data))
                s=stat5(archive) if archive.exists() else (1,1,len(data),1,1)
                row={"archive_member":path,"source_path":path,"bytes":len(data),"sha256":sha(data),"crc32":crc(data),"kind":kind,"frozen_outcome":"successful_test_evaluation","ledger_cell_path":cell,"retained_copy_verified":True,"source_stat":{"size":len(data),"dev":1,"ino":1,"mtime_ns":1,"ctime_ns":1},"verification_stat_bracket":{"stable":True,"before":{"size":len(data)},"after":{"size":len(data)}},"final_reverification":{"exact_match":True,"size":len(data),"source_sha256":sha(data),"archive_member_sha256":sha(data),"source_crc32":crc(data),"archive_member_crc32":crc(data)}}
                rows.append(row)
    astat=stat5(archive);archive_sha=Finalizer.sha_file(archive)
    receipt={"archive":str(archive),"archive_sha256":archive_sha,"archive_bytes":astat[2],"zip_crc_passed":True}
    receipt_path=archive.with_name(archive.stem+".receipt.json");receipt_path.write_text(json.dumps(receipt,sort_keys=True));receipt_sha=sha(receipt_path.read_bytes())
    doc={"schema":mod.SCHEMA,"retained_archive":{"path":mod.ARCHIVE_REL,"expected_sha256":archive_sha,"stat":dict(zip(("dev","ino","size","mtime_ns","ctime_ns"),astat))},"counts":{"files":160,"primary_models":80,"test_prediction_arrays":80,"logical_bytes":sum(x["bytes"] for x in rows)},"verification":{"all_outcomes_successful":True,"final_reverification_all_160_exact_sha_size_crc_and_stable_stats":True},"assets":rows}
    loc.write_text(json.dumps(doc,sort_keys=True))
    pins={"locator_rel":mod.LOCATOR_REL,"locator_sha256":sha(loc.read_bytes()),"archive_rel":mod.ARCHIVE_REL,"archive_name":mod.ARCHIVE_NAME,"archive_sha256":archive_sha,"archive_stat5":astat,"receipt_sha256":receipt_sha,"asset_count":160,"kind_counts":{"primary_model":80,"test_prediction_array":80},"extension_counts":{".joblib":80,".npz":80},"logical_bytes":sum(x["bytes"] for x in rows)}
    return root,runtime,loc,doc,pins,payloads

def build(world):
    root,runtime,loc,doc,pins,_=world
    return mod._build_entries(Finalizer,root,runtime,loc,pins)

def test_stream_sources_preserve_all_160_original_members(fixture_world):
    entries,prov=build(fixture_world)
    assert len(entries)==160
    assert all(e.member.startswith("project/benchmark/results/e1/") for e in entries)
    assert json.loads(prov)["status"]=="archived_primary_assets_available"
    source=entries[0].source
    assert source.sha256()==source.expected_sha256
    with source.open() as f:assert f.read()

def test_present_local_exact_copy_is_reused_not_duplicated(fixture_world):
    root,_,_,doc,_,payloads=fixture_world
    p=root/payloads[0][0];p.parent.mkdir(parents=True);p.write_bytes(payloads[0][1])
    entries,prov=build(fixture_world)
    assert len(entries)==159
    assert json.loads(prov)["assets"][0]["backing"]=="verified_local_copy"

def test_present_local_mismatch_fails_closed(fixture_world):
    root,_,_,_,_,payloads=fixture_world
    p=root/payloads[0][0];p.parent.mkdir(parents=True);p.write_bytes(b"different")
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="differs from frozen archive copy"):build(fixture_world)

def test_out_of_scope_path_rejected(fixture_world):
    root,runtime,loc,doc,pins,_=fixture_world
    doc["assets"][0]["source_path"]="e1_recovery_20261024/x/pipeline.joblib";doc["assets"][0]["archive_member"]=doc["assets"][0]["source_path"]
    loc.write_text(json.dumps(doc,sort_keys=True));pins["locator_sha256"]=sha(loc.read_bytes())
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="unsafe/out-of-scope"):mod._build_entries(Finalizer,root,runtime,loc,pins)

def test_failed_or_unverified_outcome_rejected(fixture_world):
    root,runtime,loc,doc,pins,_=fixture_world
    doc["assets"][0]["frozen_outcome"]="failed";loc.write_text(json.dumps(doc,sort_keys=True));pins["locator_sha256"]=sha(loc.read_bytes())
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="not a verified successful"):mod._build_entries(Finalizer,root,runtime,loc,pins)

def test_archive_stat_change_rejected(fixture_world):
    root,runtime,loc,doc,pins,_=fixture_world
    pins["archive_stat5"]=(1,2,3,4,5)
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="archive stat pin mismatch"):mod._build_entries(Finalizer,root,runtime,loc,pins)

def test_manifest_hash_change_rejected(fixture_world):
    root,runtime,loc,doc,pins,_=fixture_world
    pins["locator_sha256"]="0"*64
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="locator SHA mismatch"):mod._build_entries(Finalizer,root,runtime,loc,pins)

def test_duplicate_zip_member_rejected(fixture_world):
    root,runtime,loc,doc,pins,payloads=fixture_world
    # Rebuild same archive with one extra duplicate central-directory name and rebind fixture pins.
    archive=root/mod.ARCHIVE_REL
    with zipfile.ZipFile(archive,"a",compression=zipfile.ZIP_STORED) as z:z.writestr(payloads[0][0],payloads[0][1])
    astat=stat5(archive);archive_sha=Finalizer.sha_file(archive)
    doc["retained_archive"]["expected_sha256"]=archive_sha;doc["retained_archive"]["stat"]=dict(zip(("dev","ino","size","mtime_ns","ctime_ns"),astat))
    loc.write_text(json.dumps(doc,sort_keys=True));pins.update(archive_sha256=archive_sha,archive_stat5=astat,locator_sha256=sha(loc.read_bytes()))
    rp=archive.with_name(archive.stem+".receipt.json");receipt={"archive":str(archive),"archive_sha256":archive_sha,"archive_bytes":astat[2],"zip_crc_passed":True};rp.write_text(json.dumps(receipt,sort_keys=True));pins["receipt_sha256"]=sha(rp.read_bytes())
    with pytest.raises(mod.FrozenPrimaryArchiveError,match="missing/duplicated"):mod._build_entries(Finalizer,root,runtime,loc,pins)


def test_real_sealed_manifest_parses_all_160_metadata_rows():
    path=HERE/"manifests"/"FROZEN_E1_PRIMARY_ARCHIVED_ASSETS_20261030.json"
    doc=json.loads(path.read_text())
    arc=doc["retained_archive"]
    st=arc["stat"]
    pins={"archive_rel":mod.ARCHIVE_REL,"archive_sha256":mod.ARCHIVE_SHA256,"archive_stat5":tuple(st[k] for k in ("dev","ino","size","mtime_ns","ctime_ns")),"asset_count":160,"kind_counts":{"primary_model":80,"test_prediction_array":80},"extension_counts":{".joblib":80,".npz":80}}
    rows=mod._validate_manifest(doc,pins)
    assert len(rows)==160
    assert sum(r["kind"]=="primary_model" for r in rows)==80
    assert sum(r["kind"]=="test_prediction_array" for r in rows)==80
    assert all(r["source_path"]=="project/"+r["ledger_cell_path"]+("/pipeline.joblib" if r["kind"]=="primary_model" else "/test_predictions.npz") for r in rows)
