from __future__ import annotations
import hashlib, json, zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

SCHEMA = "frozen-e1-primary-retained-assets/1"
LOCATOR_REL = "manifests/FROZEN_E1_PRIMARY_ARCHIVED_ASSETS_20261030.json"
LOCATOR_SHA256 = "0c1f7d99c63dc8094fd470151188e4b9f93f38482fc8d564d3b4d02b396611f4"
ARCHIVE_REL = "packages/LAMOST_E1_WRAPUP_20261024T080232_571618+0000.zip"
ARCHIVE_NAME = "LAMOST_E1_WRAPUP_20261024T080232_571618+0000.zip"
ARCHIVE_SHA256 = "bd4834a15d491844203ff7baf07b3b21dcdf972de97af68a744d8d2c042e7d34"
ARCHIVE_STAT5 = (66305, 2441647, 4976984354, 1792829285346854837, 1792829285346854837)
RECEIPT_SHA256 = "931e73b91998dab23b8773312e91accdf4e53bdba8a26bd029eb4e25a518b446"
ASSET_COUNT = 160
KIND_COUNTS = {"primary_model": 80, "test_prediction_array": 80}
EXTENSION_COUNTS = {".joblib": 80, ".npz": 80}
PREFIX = "project/benchmark/results/e1/"

class FrozenPrimaryArchiveError(RuntimeError): pass

def _stat5(path):
    st=Path(path).stat()
    return (int(st.st_dev),int(st.st_ino),int(st.st_size),int(st.st_mtime_ns),int(st.st_ctime_ns))

def _hash_file(path):
    h=hashlib.sha256();crc=0;n=0
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(4<<20),b""):
            h.update(b);crc=zipfile.crc32(b,crc);n+=len(b)
    return h.hexdigest(),n,crc&0xffffffff

def _crc(value):
    try:return int(str(value),16)
    except (TypeError,ValueError) as e:raise FrozenPrimaryArchiveError("malformed frozen E1 primary CRC32") from e

class PrimaryZipMemberSource:
    """Stream one pinned archive member; no model deserialization or inference."""
    _lamost_external_zip_member_source=True
    def __init__(self,archive_path,member,row,expected_stat5):
        self.archive_path=Path(archive_path);self.member=member;self.expected_stat5=tuple(expected_stat5)
        self.expected_size=int(row["bytes"]);self.expected_sha256=row["sha256"];self.expected_crc32=_crc(row["crc32"]);self._verified=False
    def _assert_archive(self):
        if self.archive_path.is_symlink() or not self.archive_path.is_file() or _stat5(self.archive_path)!=self.expected_stat5:
            raise FrozenPrimaryArchiveError("pinned E1 archive stat identity changed")
    def stat(self):
        self._assert_archive()
        return {"size":self.expected_size,"sha256":self.expected_sha256,"crc32":self.expected_crc32,"archive_stat5":list(self.expected_stat5),"source_member":self.member}
    @contextmanager
    def open(self):
        self._assert_archive()
        try:
            with zipfile.ZipFile(self.archive_path,"r",allowZip64=True) as z:
                matches=[i for i in z.infolist() if i.filename==self.member]
                if len(matches)!=1:raise FrozenPrimaryArchiveError("pinned E1 member missing or duplicated: "+self.member)
                info=matches[0]
                if int(info.file_size)!=self.expected_size or int(info.CRC)!=self.expected_crc32:
                    raise FrozenPrimaryArchiveError("pinned E1 member central metadata mismatch: "+self.member)
                with z.open(info,"r") as f:yield f
        except (zipfile.BadZipFile,RuntimeError,EOFError) as e:
            raise FrozenPrimaryArchiveError("pinned E1 member ZIP stream failed: "+self.member) from e
        self._assert_archive()
    def sha256(self):
        if self._verified:self._assert_archive();return self.expected_sha256
        h=hashlib.sha256();crc=0;n=0
        with self.open() as f:
            for b in iter(lambda:f.read(4<<20),b""):
                h.update(b);crc=zipfile.crc32(b,crc);n+=len(b)
        if n!=self.expected_size or (crc&0xffffffff)!=self.expected_crc32 or h.hexdigest()!=self.expected_sha256:
            raise FrozenPrimaryArchiveError("pinned E1 member bytes differ from locator: "+self.member)
        self._verified=True;return h.hexdigest()

def _validate_manifest(doc,pins):
    if not isinstance(doc,dict) or doc.get("schema")!=SCHEMA:raise FrozenPrimaryArchiveError("unsupported frozen E1 primary manifest schema")
    arc=doc.get("retained_archive")
    if not isinstance(arc,dict) or arc.get("path")!=pins["archive_rel"] or arc.get("expected_sha256")!=pins["archive_sha256"]:
        raise FrozenPrimaryArchiveError("frozen E1 primary archive path/SHA pin mismatch")
    try:stat5=tuple(int(arc["stat"][k]) for k in ("dev","ino","size","mtime_ns","ctime_ns"))
    except Exception as e:raise FrozenPrimaryArchiveError("frozen E1 archive stat pin missing") from e
    if stat5!=tuple(pins["archive_stat5"]):raise FrozenPrimaryArchiveError("frozen E1 archive stat pin mismatch")
    counts=doc.get("counts",{})
    ver=doc.get("verification",{})
    if ver.get("all_outcomes_successful") is not True or ver.get("final_reverification_all_160_exact_sha_size_crc_and_stable_stats") is not True:
        raise FrozenPrimaryArchiveError("frozen E1 primary verification summary incomplete")
    rows=doc.get("assets")
    if not isinstance(rows,list) or len(rows)!=pins["asset_count"]:raise FrozenPrimaryArchiveError("frozen E1 primary asset count mismatch")
    kinds={};exts={};cells={};names=set();out=[]
    for r in rows:
        if not isinstance(r,dict):raise FrozenPrimaryArchiveError("malformed frozen E1 primary row")
        kind=r.get("kind");src=r.get("source_path");member=r.get("archive_member");cell=r.get("ledger_cell_path");p=PurePosixPath(src or "")
        if kind not in pins["kind_counts"] or not isinstance(src,str) or not src.startswith(PREFIX) or src!=member or p.is_absolute() or "\\" in src or any(x in ("",".","..") for x in p.parts):
            raise FrozenPrimaryArchiveError("unsafe/out-of-scope E1 primary path")
        suffix="/pipeline.joblib" if kind=="primary_model" else "/test_predictions.npz"
        if not isinstance(cell,str) or not cell.startswith(PREFIX[8:]) or any(x in ("", ".", "..") for x in PurePosixPath(cell).parts) or src!="project/"+cell+suffix:raise FrozenPrimaryArchiveError(member)
        if r.get("frozen_outcome")!="successful_test_evaluation" or r.get("retained_copy_verified") is not True:raise FrozenPrimaryArchiveError("E1 row is not a verified successful outcome")
        size=r.get("bytes");sha=r.get("sha256")
        if not isinstance(size,int) or size<0 or not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha.lower()):raise FrozenPrimaryArchiveError("E1 row lacks valid size/SHA")
        crc=_crc(r.get("crc32"));proof=r.get("final_reverification",{})
        if proof.get("exact_match") is not True or proof.get("size")!=size or proof.get("source_sha256")!=sha or proof.get("archive_member_sha256")!=sha or _crc(proof.get("source_crc32"))!=crc or _crc(proof.get("archive_member_crc32"))!=crc:
            raise FrozenPrimaryArchiveError("E1 row lacks exact final SHA/size/CRC proof")
        ss=r.get("source_stat",{});br=r.get("verification_stat_bracket",{})
        if int(ss.get("size",-1))!=size or br.get("stable") is not True or br.get("before")!=br.get("after"):
            raise FrozenPrimaryArchiveError("E1 source stat bracket invalid")
        if src in names:raise FrozenPrimaryArchiveError("duplicate E1 primary member path")
        names.add(src);kinds[kind]=kinds.get(kind,0)+1;ext=p.suffix.lower();exts[ext]=exts.get(ext,0)+1;cells.setdefault(cell,set()).add(kind);out.append(r)
    if kinds!=pins["kind_counts"] or exts!=pins["extension_counts"] or len(cells)!=80 or any(v!=set(pins["kind_counts"]) for v in cells.values()):
        raise FrozenPrimaryArchiveError("E1 primary 80-cell pair or kind/extension profile mismatch")
    return out

def _build_entries(finalizer,root,runtime,locator_path,pins):
    root=Path(root).resolve();runtime=Path(runtime).resolve();packages=root/"packages"
    if root.is_symlink() or packages.is_symlink() or packages.resolve().parent!=root:raise FrozenPrimaryArchiveError("unsafe ROOT/packages")
    expected_locator=runtime/pins["locator_rel"]
    if locator_path.is_symlink() or not locator_path.is_file() or locator_path.resolve()!=expected_locator.resolve():raise FrozenPrimaryArchiveError("locator path is not the pinned staging locator")
    raw=locator_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pins["locator_sha256"]:raise FrozenPrimaryArchiveError("frozen E1 primary locator SHA mismatch")
    rows=_validate_manifest(json.loads(raw),pins)
    archive=root/pins["archive_rel"]
    if archive.is_symlink() or not archive.is_file() or archive.name!=pins["archive_name"] or archive.resolve().parent!=packages.resolve():raise FrozenPrimaryArchiveError("unsafe frozen E1 source archive path")
    stat5=_stat5(archive)
    if stat5!=tuple(pins["archive_stat5"]):raise FrozenPrimaryArchiveError("current frozen E1 archive stat differs from pin")
    receipt_path=archive.with_name(archive.stem+".receipt.json")
    if receipt_path.is_symlink() or not receipt_path.is_file():raise FrozenPrimaryArchiveError("frozen E1 archive receipt missing/unsafe")
    receipt_raw=receipt_path.read_bytes()
    if hashlib.sha256(receipt_raw).hexdigest()!=pins["receipt_sha256"]:raise FrozenPrimaryArchiveError("frozen E1 archive receipt SHA mismatch")
    receipt=json.loads(receipt_raw)
    if receipt.get("archive_sha256")!=pins["archive_sha256"] or Path(receipt.get("archive","")).resolve()!=archive.resolve() or receipt.get("zip_crc_passed") is not True or int(receipt.get("archive_bytes",-1))!=stat5[2]:
        raise FrozenPrimaryArchiveError("frozen E1 archive receipt identity mismatch")
    # Exactly one whole-archive digest per collection; individual streams below verify members.
    whole_sha=finalizer.sha_file(archive)
    if whole_sha!=pins["archive_sha256"] or _stat5(archive)!=stat5:raise FrozenPrimaryArchiveError("frozen E1 archive full SHA/stat verification failed")
    entries=[];prov=[]
    with zipfile.ZipFile(archive,"r",allowZip64=True) as z:
        by_name={}
        for info in z.infolist():by_name.setdefault(info.filename,[]).append(info)
        for row in rows:
            member=row["archive_member"];matches=by_name.get(member,[])
            if len(matches)!=1:raise FrozenPrimaryArchiveError("frozen E1 member missing/duplicated: "+member)
            info=matches[0]
            if int(info.file_size)!=int(row["bytes"]) or int(info.CRC)!=_crc(row["crc32"]):raise FrozenPrimaryArchiveError("frozen E1 member central size/CRC mismatch: "+member)
            mode=(int(info.external_attr)>>16)&0xffff
            if mode&0o170000==0o120000:raise FrozenPrimaryArchiveError("frozen E1 ZIP member is symlink: "+member)
            local=root.joinpath(*PurePosixPath(row["source_path"]).parts);backing="frozen_primary_zip"
            if local.exists() or local.is_symlink():
                if local.is_symlink() or not local.is_file():raise FrozenPrimaryArchiveError("local E1 primary path is not a regular file: "+member)
                local_before=_stat5(local)
                local_sha,local_n,local_crc=_hash_file(local)
                if _stat5(local)!=local_before: raise FrozenPrimaryArchiveError(member)
                if (local_n,local_crc,local_sha)!=(int(row["bytes"]),_crc(row["crc32"]),row["sha256"]):raise FrozenPrimaryArchiveError("present local E1 primary copy differs from frozen archive copy: "+member)
                backing="verified_local_copy"
            else:
                entries.append(finalizer.Entry(PrimaryZipMemberSource(archive,member,row,stat5),member,"frozen_E1_primary_retained_asset"))
            prov.append({"archive_member":member,"source_path":row["source_path"],"bytes":int(row["bytes"]),"sha256":row["sha256"],"crc32":row["crc32"],"kind":row["kind"],"frozen_outcome":row["frozen_outcome"],"backing":backing})
    if _stat5(archive)!=stat5:raise FrozenPrimaryArchiveError("frozen E1 archive changed during locator inventory")
    provenance={"schema_version":"lamost-e1-primary-archive-provenance/1","status":"archived_primary_assets_available","source_archive":pins["archive_rel"],"source_archive_sha256":whole_sha,"source_archive_stat5":list(stat5),"source_archive_receipt_sha256":pins["receipt_sha256"],"locator_path":locator_path.relative_to(runtime).as_posix(),"locator_sha256":pins["locator_sha256"],"asset_count":len(prov),"primary_model_count":80,"test_prediction_array_count":80,"logical_bytes":sum(x["bytes"] for x in prov),"assets":prov,"scientific_note":"Retained copies of frozen successful E1 primary pipelines and saved test predictions. This records archived availability only; it changes no E1 ledger, fit, inference, or metric. Historical omitted E1 models and predictions remain omitted."}
    return entries,(json.dumps(provenance,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()

def primary_e1_archive_entries(finalizer,root,runtime):
    """Return missing retained-primary ZIP members plus a provenance manifest."""
    pins={"locator_rel":LOCATOR_REL,"locator_sha256":LOCATOR_SHA256,"archive_rel":ARCHIVE_REL,"archive_name":ARCHIVE_NAME,"archive_sha256":ARCHIVE_SHA256,"archive_stat5":ARCHIVE_STAT5,"receipt_sha256":RECEIPT_SHA256,"asset_count":ASSET_COUNT,"kind_counts":KIND_COUNTS,"extension_counts":EXTENSION_COUNTS}
    runtime=Path(runtime).resolve()
    return _build_entries(finalizer,Path(root),runtime,runtime/LOCATOR_REL,pins)
