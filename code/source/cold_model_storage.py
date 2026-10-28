"""Cold ZIP model storage prototype; staging only, no FUSE and no live compaction."""
from __future__ import annotations
import contextlib, fcntl, hashlib, importlib.util, io, json, os, pathlib, shutil, stat, tempfile, time, uuid, zipfile, sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import cold_codec_storage as _codec_storage

SAFETY_PATH=Path(__file__).resolve().with_name("cold_storage_safety.py")
SAFETY_SHA256="7dff7f8dc256f8252d41b6fd370b7624bfe8841fa7c5c13dbe86747ccc456273"
if not SAFETY_PATH.is_file() or hashlib.sha256(SAFETY_PATH.read_bytes()).hexdigest()!=SAFETY_SHA256:
    raise RuntimeError("pinned self-contained cold storage safety helper missing or changed")
_spec=importlib.util.spec_from_file_location("cold_store_safety",SAFETY_PATH)
_safety=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_safety)
AmbiguousState=_safety.AmbiguousState;UnsafePlan=_safety.UnsafePlan
SCHEMA="lamost-cold-model-store/1"
DEFAULT_ARCHIVE_REL="packages/LAMOST_COLD_RF_MODELS.zip"
DEFAULT_MANIFEST_REL="runtime_20261025/manifests/cold_model_store_manifest.json"
DEFAULT_JOURNALS_REL="runtime_20261025/journals/cold_model_store"
_IMPORTED_SOURCE_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_CODEC_PROOF_PROTOCOL="exact-original-byte-roundtrip-and-unchanged-prefix/1"
_LEGACY_CORE_SHA256="ba909e9f55f5f8020f165a5ac42f4159eed4c8c4b69b64f95f7313fd82430943"
_LEGACY_HISTORY_SHA256="594eebc2140060a48219394d48fb3fd15ee6b357cdc91c776f7c96bd1013b33f"
_LEGACY_PASS_SHA256="c101e8486ffcf6e54f9eadd11a5c0ffebddcb378a6b6886ff8505f1a0d1e8d51"
_LEGACY_HISTORY_ENTRY_COUNT=54
_ARCHIVABLE_FIT_METHODS=frozenset(("arf", "cart", "chow_liu", "copula", "gaussian_nb", "gmm", "hist_gb", "kde", "knn", "lda", "linear_svm", "logistic", "qda", "random_forest", "rbf_svm", "shared_diagonal"))


def _sha_bytes(data):return hashlib.sha256(data).hexdigest()
def _archive_stat_identity(st):return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def sha256_file(path,chunk=8<<20):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(chunk),b""):h.update(b)
    return h.hexdigest()
def sha256_file_and_prefixes(path,prefix_bytes,chunk=8<<20):
    """Hash a complete file and selected leading prefixes in one bounded-memory pass."""
    lengths=tuple(dict.fromkeys(prefix_bytes if isinstance(prefix_bytes,(tuple,list,set)) else (prefix_bytes,)))
    if not lengths or any(not isinstance(n,int) or n<0 for n in lengths):raise ValueError("invalid prefix lengths")
    full=hashlib.sha256();prefixes={n:hashlib.sha256() for n in lengths};remaining={n:n for n in lengths};total=0
    with open(path,"rb") as f:
        while True:
            b=f.read(chunk)
            if not b:break
            full.update(b)
            for n,h in prefixes.items():
                if remaining[n]:
                    take=b[:remaining[n]];h.update(take);remaining[n]-=len(take)
            total+=len(b)
    if any(remaining.values()):raise AmbiguousState("requested archive prefix exceeds file size")
    return full.hexdigest(),{n:h.hexdigest() for n,h in prefixes.items()},total
def sha256_file_and_prefix(path,prefix_bytes,chunk=8<<20):
    whole,prefixes,total=sha256_file_and_prefixes(path,prefix_bytes,chunk)
    return whole,prefixes[prefix_bytes],total
def _stream_hash(stream):
    h=hashlib.sha256();n=0;crc=0
    while True:
        b=stream.read(8<<20)
        if not b:break
        h.update(b);n+=len(b);crc=zipfile.crc32(b,crc)
    return h.hexdigest(),n,crc&0xffffffff
def _atomic_json(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+".tmp."+uuid.uuid4().hex)
    with open(tmp,"x",encoding="utf-8") as f:
        json.dump(obj,f,indent=2,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(tmp,p);_fsync_dir(p.parent)
def _fsync_dir(p):
    fd=os.open(p,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def _safe_rel(value):
    if not isinstance(value,str) or not value or "\\" in value:raise UnsafePlan("invalid logical artifact path")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ("",".","..") for x in p.parts) or ":" in p.parts[0]:raise UnsafePlan("unsafe logical artifact path")
    return p.as_posix()
def _archive_member_for(logical_path,digest):
    logical=_safe_rel(logical_path)
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):raise UnsafePlan("invalid content-addressed model SHA")
    prefix="runtime_20261025/artifacts/"
    if not logical.startswith(prefix):raise UnsafePlan("cold model logical path outside runtime artifacts")
    relative=logical[len(prefix):]
    return f"runtime_20261025/cold_models/{relative}.{digest}.zipmember"
def _zip_records_all(z):
    out=[];seen=set()
    for i in z.infolist():
        if i.filename in seen:raise UnsafePlan("duplicate ZIP member "+i.filename)
        seen.add(i.filename)
        out.append({"member":i.filename,"crc32":i.CRC,"file_size":i.file_size,"compressed_size":i.compress_size,"compress_type":i.compress_type,"header_offset":i.header_offset,"flag_bits":i.flag_bits,"external_attr":i.external_attr,"date_time":list(i.date_time),"extra_sha256":_sha_bytes(i.extra),"comment_sha256":_sha_bytes(i.comment)})
    return out
def _record_sha(records):return _sha_bytes(json.dumps(records,sort_keys=True,separators=(",",":")).encode())
def _successful(t):
    return t.get("status")=="validated_terminal" and t.get("outcome")=="successful" and t.get("validation_state")=="validated"
def _pipeline_hash(t):
    result=t.get("result") or {};validation=result.get("validation") or {};files=validation.get("files") or {}
    h=files.get("pipeline.joblib")
    nested=(result.get("result") or {}).get("pipeline_sha256")
    if not isinstance(h,str) or not h:raise UnsafePlan("fit lacks validated pipeline.joblib SHA")
    if nested and nested!=h:raise AmbiguousState("fit result and validation pipeline hashes differ")
    if validation.get("task_key")!=t.get("key") or validation.get("status")!="validated":raise UnsafePlan("fit validation identity invalid")
    return h
def _consumer_closure(task_key,records):return _safety.consumer_closure(task_key,records)
def _verify_records(records):
    known=set(records)
    for k,t in records.items():
        if t.get("key",k)!=k:raise UnsafePlan("registry key mismatch")
        _safety._edges(t,known)
def _manifest_load(path):
    p=Path(path)
    if not p.exists():return {"schema_version":SCHEMA,"members":[],"archive_sha256":None,"archive_bytes":0,"zip_records":[]}
    d=json.loads(p.read_text())
    if d.get("schema_version")!=SCHEMA or not isinstance(d.get("members"),list):raise AmbiguousState("cold store manifest schema invalid")
    return d

class ZipMemberSource:
    """Finalizer source adapter; open_verified supplies a locked verified stream."""
    def __init__(self,store,logical_path,expected_sha256=None):self.store=store;self.logical_path=_safe_rel(logical_path);self.expected_sha256=expected_sha256
    def open(self):return self.store.open_verified(self.logical_path,self.expected_sha256)
    def stat(self):return self.store.artifact_stat(self.logical_path,self.expected_sha256)
    def read_bytes(self):
        with self.open() as f:return f.read()
    def sha256(self):
        with self.open() as f:return _stream_hash(f)[0]

class ColdModelStore:
    def __init__(self,migration_root,runtime_root,archive_path,manifest_path,journal_root,writer_lock=None,reader_lock=None,joblib_compressor_source_path=None,storage_codec_policy=None):
        self.root=Path(migration_root).resolve();self.runtime=Path(runtime_root).resolve();self.archive=Path(archive_path).resolve(strict=False);self.manifest=Path(manifest_path).resolve(strict=False);self.journals=Path(journal_root).resolve(strict=False)
        self.joblib_compressor_source_path=Path(joblib_compressor_source_path) if joblib_compressor_source_path is not None else None
        if storage_codec_policy not in (None,"reversible-xz-v1"):raise UnsafePlan("unknown storage codec write policy")
        self.storage_codec_policy=storage_codec_policy
        self.writer_lock=Path(writer_lock or self.runtime/"locks"/"cold_model_store.writer.lock");self.reader_lock=Path(reader_lock or self.runtime/"locks"/"cold_model_store.readers.lock");self._archive_identity_cache=None
        for p in (self.runtime,self.archive,self.manifest,self.journals,self.writer_lock,self.reader_lock):
            try:p.resolve(strict=False).relative_to(self.root)
            except ValueError:raise UnsafePlan("cold store path escapes migration root")
    @classmethod
    def from_runtime(cls,migration_root,runtime_root,archive_path=None,manifest_path=None,journal_root=None,joblib_compressor_source_path=None,storage_codec_policy=None):
        root=Path(migration_root).resolve();runtime=Path(runtime_root).resolve()
        manifest=Path(manifest_path) if manifest_path is not None else runtime/"manifests"/"cold_model_store_manifest.json"
        if archive_path is not None:archive=Path(archive_path)
        elif manifest.is_file():
            doc=_manifest_load(manifest);rel=_safe_rel(doc.get("archive_path"))
            archive=root.joinpath(*PurePosixPath(rel).parts)
            try:archive.resolve(strict=False).relative_to(root)
            except ValueError as e:raise AmbiguousState("manifest archive path escapes migration root") from e
            q=archive
            while q!=root:
                if q.is_symlink():raise AmbiguousState("manifest archive path crosses symlink")
                q=q.parent
            if archive.is_symlink():raise AmbiguousState("manifest archive path is a symlink")
        else:archive=root/DEFAULT_ARCHIVE_REL
        journals=Path(journal_root) if journal_root is not None else runtime/"journals"/"cold_model_store"
        return cls(root,runtime,archive,manifest,journals,joblib_compressor_source_path=joblib_compressor_source_path,storage_codec_policy=storage_codec_policy)
    def _assert_no_pending_transactions(self):
        if not self.journals.exists():return
        for d in self.journals.iterdir():
            p=d/"journal.json"
            if p.is_file():
                state=json.loads(p.read_text()).get("state")
                if state not in ("complete","rolled_back"):raise AmbiguousState("pending cold archive transaction must be recovered first: "+d.name)
    @contextmanager
    def _write_lock(self):
        self.writer_lock.parent.mkdir(parents=True,exist_ok=True);self.reader_lock.parent.mkdir(parents=True,exist_ok=True)
        w=open(self.writer_lock,"a+");r=open(self.reader_lock,"a+")
        try:
            try:fcntl.flock(w,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(r,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:raise AmbiguousState("cold-store reader or writer lease active") from e
            yield
        finally:
            with contextlib.suppress(Exception):fcntl.flock(r,fcntl.LOCK_UN)
            with contextlib.suppress(Exception):fcntl.flock(w,fcntl.LOCK_UN)
            r.close();w.close()
    @contextmanager
    def _read_lock(self):
        self.reader_lock.parent.mkdir(parents=True,exist_ok=True);r=open(self.reader_lock,"a+")
        try:
            try:fcntl.flock(r,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError as e:raise AmbiguousState("cold-store writer lease active") from e
            yield
        finally:
            with contextlib.suppress(Exception):fcntl.flock(r,fcntl.LOCK_UN)
            r.close()
    def _alias_publication_evidence(self,owner,alias_path,digest):
        key=owner["key"];task_sha=(owner.get("result") or {}).get("task_sha256");attempt_id=(owner.get("result") or {}).get("attempt_id")
        artifact_dir=(self.root/"runtime_20261025"/"artifacts"/key).resolve(strict=False)
        def safe_file(rel):
            q=self._physical_path(rel)
            if not q.is_file():raise AmbiguousState("publication receipt file missing: "+rel)
            return q
        canonical=f"runtime_20261025/artifacts/{key}/pipeline.joblib"
        attempt_alias=f"runtime_20261025/artifacts/{key}/attempts/{attempt_id}/pipeline.joblib"
        checkpoint_alias=f"runtime_20261025/artifacts/{key}/checkpoints/{task_sha}/pipeline.joblib"
        if alias_path==canonical:return {"owner_kind":"canonical_pipeline"}
        if not isinstance(task_sha,str) or len(task_sha)!=64 or not isinstance(attempt_id,str) or not attempt_id:raise UnsafePlan("published alias lacks task/attempt identity")
        if alias_path==attempt_alias:kind="attempt_publication"
        elif alias_path==checkpoint_alias:kind="task_checkpoint"
        else:raise UnsafePlan("pipeline hardlink alias is not canonical or bound to a validated publication: "+alias_path)
        result=owner["result"];validation=result.get("validation") or {};files=validation.get("files") or {}
        selection_expected=files.get("selection.json")
        if not isinstance(selection_expected,str) or not selection_expected:raise UnsafePlan("published alias lacks validated selection identity")
        fitpub_rel=f"runtime_20261025/artifacts/{key}/fit_publication.json"
        fitresult_rel=f"runtime_20261025/artifacts/{key}/fit_result.json"
        selection_rel=f"runtime_20261025/artifacts/{key}/selection.json"
        fitpub_path=safe_file(fitpub_rel);fitresult_path=safe_file(fitresult_rel);selection_path=safe_file(selection_rel)
        publication=json.loads(fitpub_path.read_text());fit_result=json.loads(fitresult_path.read_text())
        canonical_abs=str((self.root/canonical).resolve(strict=False))
        if publication.get("stage")!="validated_publication" or publication.get("attempt_id")!=attempt_id or publication.get("task_sha256")!=task_sha or publication.get("pipeline_sha256")!=digest or Path(str(publication.get("published_path",""))).resolve(strict=False)!=Path(canonical_abs):
            raise AmbiguousState("fit_publication receipt does not bind current validated pipeline")
        if fit_result.get("task_sha256")!=task_sha or fit_result.get("attempt_id")!=attempt_id or (fit_result.get("result") or {}).get("pipeline_sha256")!=digest or (fit_result.get("result") or {}).get("status")!="success":
            raise AmbiguousState("fit_result receipt does not bind current validated pipeline")
        if sha256_file(selection_path)!=selection_expected:raise AmbiguousState("selected configuration SHA differs from validation record")
        attempt_prefix=f"runtime_20261025/artifacts/{key}/attempts/{attempt_id}"
        attempt_pub=safe_file(attempt_prefix+"/fit_publication.json");attempt_result=safe_file(attempt_prefix+"/attempt.json");attempt_selection=safe_file(attempt_prefix+"/selection.json")
        attempt_publication=json.loads(attempt_pub.read_text())
        for field in ("stage","attempt_id","task_sha256","pipeline_sha256","published_path"):
            if attempt_publication.get(field)!=publication.get(field):raise AmbiguousState("attempt and canonical publication receipts disagree")
        if sha256_file(attempt_result)!=sha256_file(fitresult_path):raise AmbiguousState("attempt fit-result receipt differs from canonical fit result")
        if sha256_file(attempt_selection)!=selection_expected:raise AmbiguousState("attempt selected configuration SHA differs")
        checkpoint_prefix=f"runtime_20261025/artifacts/{key}/checkpoints/{task_sha}"
        checkpoint_selection=safe_file(checkpoint_prefix+"/selection.json")
        if sha256_file(checkpoint_selection)!=selection_expected:raise AmbiguousState("checkpoint selected configuration SHA differs")
        return {"owner_kind":kind,"attempt_id":attempt_id,"task_sha256":task_sha,"publication_sha256":sha256_file(fitpub_path),"attempt_publication_sha256":sha256_file(attempt_pub),"fit_result_sha256":sha256_file(fitresult_path),"selection_sha256":selection_expected}
    def _consumer_contract(self,key,closure,records,claimed):
        pending=[k for k in closure if records[k].get("status")!="validated_terminal"]
        if not pending and claimed is None:
            return None
        if pending and not isinstance(claimed,dict): raise UnsafePlan("nonterminal consumers require an explicit metadata-only contract")
        if claimed is None: return None
        import metadata_only_contract as contract_module
        if sha256_file(Path(contract_module.__file__))!="1d4e9f78bf3b0062effb3bc218fb5135aae0dba2375b2602773d21bf49d333a1": raise UnsafePlan("metadata-only contract module pin mismatch")
        try: expected=contract_module.build_contract(self.root,key,records,closure)
        except Exception as exc: raise AmbiguousState("metadata-only consumer contract no longer validates") from exc
        if claimed!=expected: raise AmbiguousState("metadata-only consumer contract changed")
        return expected
    def _validate_alias_owner_records(self,aliases,owner_rows,digest,records):
        if not isinstance(aliases,list) or not isinstance(owner_rows,list):raise AmbiguousState("stored model lacks alias ownership evidence")
        owner_by_path={};required=set()
        for owner_row in owner_rows:
            alias_path=_safe_rel(owner_row.get("alias_path"));owner_key=owner_row.get("task_key")
            if alias_path in owner_by_path:raise AmbiguousState("duplicate stored alias owner path")
            owner=records.get(owner_key)
            if not owner or not _successful(owner) or owner.get("kind")!="fit" or owner.get("method") not in _ARCHIVABLE_FIT_METHODS or int(owner.get("experiment",0)) not in (3,4,5,6):raise UnsafePlan("stored alias owner is not a validated runtime RF fit")
            if _pipeline_hash(owner)!=digest:raise AmbiguousState("stored alias owner pipeline SHA changed")
            expected_dir=(self.root/"runtime_20261025"/"artifacts"/owner_key).resolve(strict=False)
            if Path(str(owner.get("artifact_dir", ""))).resolve(strict=False)!=expected_dir:raise AmbiguousState("alias owner artifact_dir does not match its canonical path")
            owner_task_sha=(owner.get("result") or {}).get("task_sha256")
            if owner_row.get("task_sha256") and owner_task_sha!=owner_row["task_sha256"]:raise AmbiguousState("stored alias owner task identity changed")
            closure=sorted(_consumer_closure(owner_key,records))
            if closure!=sorted(owner_row.get("consumer_tasks") or []):raise AmbiguousState("stored alias owner consumer closure changed")
            contract=self._consumer_contract(owner_key,closure,records,owner_row.get("metadata_only_consumer_contract"))
            metadata_tasks={x["task_key"] for x in (contract or {}).get("pending_metadata_fit_tasks",[]) if records[x["task_key"]].get("status")!="validated_terminal"}
            metadata_tasks|={x["task_key"] for x in (contract or {}).get("pending_own_fit_evaluations",[]) if records[x["task_key"]].get("status")!="validated_terminal"}
            expected_evidence=self._alias_publication_evidence(owner,alias_path,digest)
            for field,value in expected_evidence.items():
                if owner_row.get(field)!=value:raise AmbiguousState("stored alias publication evidence changed: "+field)
            owner_by_path[alias_path]=owner_row;required|={owner_key}|(set(closure)-metadata_tasks)
        if set(owner_by_path)!=set(aliases):raise AmbiguousState("stored aliases and their owner records differ")
        return required
    def _validate_existing_members(self,manifest,records,verify_payload=True):
        _verify_records(records);required=set()
        for row in manifest.get("members",[]):
            key=row.get("task_key")
            task=records.get(key)
            if not task or not _successful(task):raise UnsafePlan("stored-model producer is no longer validated successful: "+str(key))
            logical=_safe_rel(row.get("logical_path"));expected=f"runtime_20261025/artifacts/{key}/pipeline.joblib"
            if logical!=expected or row.get("method") not in _ARCHIVABLE_FIT_METHODS or row.get("method")!=task.get("method") or int(row.get("experiment",0)) not in (3,4,5,6):raise AmbiguousState("stored cold member outside approved runtime RF scope")
            if _pipeline_hash(task)!=row.get("sha256"):raise AmbiguousState("stored-model producer validation SHA changed: "+str(key))
            if _safe_rel(row.get("archive_member"))!=_archive_member_for(logical,row["sha256"]):raise AmbiguousState("stored model member name does not bind logical identity and content SHA")
            recorded_task_sha=(task.get("result") or {}).get("task_sha256")
            if row.get("task_sha256") and recorded_task_sha!=row.get("task_sha256"):raise AmbiguousState("stored-model producer task identity changed: "+str(key))
            closure=sorted(_consumer_closure(key,records))
            if closure!=sorted(row.get("consumer_tasks") or []):raise AmbiguousState("stored-model consumer closure changed: "+str(key))
            contract=self._consumer_contract(key,closure,records,row.get("metadata_only_consumer_contract"))
            metadata_tasks={x["task_key"] for x in (contract or {}).get("pending_metadata_fit_tasks",[]) if records[x["task_key"]].get("status")!="validated_terminal"}
            metadata_tasks|={x["task_key"] for x in (contract or {}).get("pending_own_fit_evaluations",[]) if records[x["task_key"]].get("status")!="validated_terminal"}
            required|=self._validate_alias_owner_records(row.get("aliases"),row.get("alias_owners"),row["sha256"],records)
            if verify_payload:self._verified_member_metadata(logical,row)
            required|={key}|(set(closure)-metadata_tasks)
        return required
    @contextmanager
    def append_guard(self,expected_archive_sha256=None,registry_records=None):
        """Hold exclusive writer+reader locks while an append-only finalizer transaction runs."""
        self.writer_lock.parent.mkdir(parents=True,exist_ok=True);self.reader_lock.parent.mkdir(parents=True,exist_ok=True)
        w=open(self.writer_lock,"a+");r=open(self.reader_lock,"a+");entered=False
        try:
            try:fcntl.flock(w,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(r,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:raise AmbiguousState("cold-store reader/writer lease active") from e
            self._assert_no_pending_transactions()
            manifest=_manifest_load(self.manifest);before,_,records=self._check_archive_manifest(manifest)
            if manifest.get("members") and registry_records is None:raise UnsafePlan("registry required to validate existing cold member consumers before append")
            if registry_records is not None:
                required=self._validate_existing_members(manifest,registry_records)
                if required:_safety.verify_no_matching_processes(self.root,required,registry_records)
            if expected_archive_sha256 and before!=expected_archive_sha256:raise AmbiguousState("append source archive differs from reviewed snapshot")
            archive_stat=self.archive.stat()
            session={"archive_sha256_before":before,"records_before":records,"refreshed":False,"archive_device":archive_stat.st_dev,"archive_inode":archive_stat.st_ino}
            class Guard:
                def refresh_manifest(inner,archive_path=None):
                    if archive_path is not None:
                        relocated,rel=self._validated_archive_path(archive_path)
                        if not relocated.is_file():raise AmbiguousState("relocated archive is missing")
                        moved=relocated.stat()
                        if (moved.st_dev,moved.st_ino)!=(session["archive_device"],session["archive_inode"]):raise AmbiguousState("archive relocation did not preserve the original inode")
                        self.archive=relocated
                    current_sha,st,new_records=inner._read_archive_identity()
                    old=session["records_before"]
                    if new_records[:len(old)]!=old:raise AmbiguousState("append changed a pre-existing ZIP record")
                    inner._verify_all_members(manifest,new_records)
                    updated=dict(manifest);updated.update({"archive_path":self.archive.relative_to(self.root).as_posix(),"archive_sha256":current_sha,"archive_bytes":st.st_size,"zip_records":new_records,"previous_archive_sha256":before,"updated_utc":time.time()})
                    _atomic_json(self.manifest,updated);session["refreshed"]=True
                    self._archive_identity_cache={"identity":(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns),"sha256":current_sha,"zip_records":new_records}
                    return updated
                def _read_archive_identity(inner):
                    current_sha=sha256_file(self.archive);st=self.archive.stat()
                    with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:records=_zip_records_all(z)
                    return current_sha,st,records
                def _verify_all_members(inner,old_manifest,new_records):
                    by={x["member"]:x for x in new_records}
                    for entry in old_manifest.get("members",[]):
                        rec=by.get(entry["archive_member"])
                        if not rec or rec["header_offset"]!=entry["header_offset"]:
                            raise AmbiguousState("append changed a committed cold member record")
                        if "storage_encoding" in entry:
                            desc=entry["storage_encoding"]
                            if rec["crc32"]!=int(desc["encoded_crc32"]) or rec["file_size"]!=int(desc["encoded_size_bytes"]):
                                raise AmbiguousState("append changed a committed encoded member record")
                        elif rec["crc32"]!=entry["crc32"] or rec["file_size"]!=entry["bytes"]:
                            raise AmbiguousState("append changed a committed raw member record")
                        self._verified_member_metadata(entry["logical_path"],entry)
            guard=Guard();entered=True
            yield guard
            current=sha256_file(self.archive)
            if current!=before and not session["refreshed"]:raise AmbiguousState("archive changed during append guard without refreshing cold manifest")
        finally:
            with contextlib.suppress(Exception):fcntl.flock(r,fcntl.LOCK_UN)
            with contextlib.suppress(Exception):fcntl.flock(w,fcntl.LOCK_UN)
            r.close();w.close()
    def initialize_empty_archive(self):
        with self._write_lock():
            if self.archive.exists():raise UnsafePlan("refusing to overwrite existing archive")
            self.archive.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(self.archive,"x",compression=zipfile.ZIP_STORED,allowZip64=True):pass
            fd=os.open(self.archive,os.O_RDONLY);os.fsync(fd);os.close(fd);_fsync_dir(self.archive.parent)
            return {"sha256":sha256_file(self.archive),"bytes":self.archive.stat().st_size}
    def _validated_archive_path(self,value):
        p=Path(value)
        if not p.is_absolute():p=self.root/p
        lexical=Path(os.path.abspath(p))
        try:lexical_rel=lexical.relative_to(self.root)
        except ValueError as e:raise UnsafePlan("archive path escapes migration root") from e
        q=self.root
        for part in lexical_rel.parts:
            q=q/part
            if q.is_symlink():raise AmbiguousState("archive path crosses symlink")
        try:resolved=lexical.resolve(strict=False);rel=resolved.relative_to(self.root).as_posix()
        except ValueError as e:raise UnsafePlan("resolved archive path escapes migration root") from e
        return resolved,rel
    def _physical_path(self,logical):
        logical=_safe_rel(logical);raw=self.root.joinpath(*PurePosixPath(logical).parts)
        try:raw.relative_to(self.root)
        except ValueError:raise UnsafePlan("logical path escapes migration root")
        q=raw
        while q!=self.root:
            if q.is_symlink():raise AmbiguousState("physical artifact path crosses a symlink")
            q=q.parent
        resolved=raw.resolve(strict=False)
        try:resolved.relative_to(self.root)
        except ValueError:raise AmbiguousState("physical artifact path resolves outside migration root")
        return resolved
    def _records(self):
        with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:return _zip_records_all(z)
    @staticmethod
    def _stat_identity(st):return _archive_stat_identity(st)
    def _check_reviewed_baseline(self,manifest,reviewed_sha256):
        """Bind the explicit reviewed digest, manifest, ZIP index and prefix in one fresh read."""
        expected=reviewed_sha256.lower() if isinstance(reviewed_sha256,str) else ""
        if len(expected)!=64 or any(c not in "0123456789abcdef" for c in expected):
            raise UnsafePlan("explicit 64-hex reviewed baseline SHA required")
        actual,st,records=self._check_archive_manifest(manifest)
        if actual!=expected:raise AmbiguousState("archive does not match explicit reviewed baseline")
        return actual,st,records
    def _check_archive_manifest(self,manifest):
        if not self.archive.is_file() or self.archive.is_symlink():raise AmbiguousState("cold ZIP missing or not regular")
        before=self.archive.stat();identity=_archive_stat_identity(before)
        cached=getattr(self,"_archive_identity_cache",None)
        cached_prefix_valid=(isinstance(cached,dict)
            and isinstance(cached.get("prefix_bytes"),int) and cached.get("prefix_bytes")>=0
            and isinstance(cached.get("zip_start_dir"),int) and cached.get("zip_start_dir")==cached.get("prefix_bytes")
            and isinstance(cached.get("prefix_sha256"),str) and len(cached.get("prefix_sha256"))==64
            and all(c in "0123456789abcdef" for c in cached.get("prefix_sha256")))
        if cached and cached.get("identity")==identity and cached_prefix_valid:
            actual=cached["sha256"];records=cached["zip_records"];prefix_sha=cached["prefix_sha256"];start=cached["zip_start_dir"]
        else:
            with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:
                records=_zip_records_all(z);start=z.start_dir
            actual,prefix_sha,total=sha256_file_and_prefix(self.archive,start)
            if total!=before.st_size:raise AmbiguousState("cold ZIP size changed while hashing")
            self._archive_identity_cache={"identity":identity,"sha256":actual,"zip_records":records,
                "prefix_bytes":start,"prefix_sha256":prefix_sha,"zip_start_dir":start}
        after=self.archive.stat();after_identity=_archive_stat_identity(after)
        if after_identity!=identity:raise AmbiguousState("cold ZIP changed while hashing/indexing")
        st=after
        if manifest.get("archive_sha256")!=actual or manifest.get("archive_bytes")!=st.st_size or manifest.get("zip_records")!=records:
            raise AmbiguousState("cold ZIP differs from committed member manifest")
        return actual,st,records
    def _verified_prefix_digest(self,expected_sha256,prefix_bytes):
        """Return a prefix SHA bound to the current whole-file identity; fail closed on drift."""
        if not self.archive.is_file() or self.archive.is_symlink():raise AmbiguousState("cold ZIP missing or not regular")
        before=self.archive.stat();identity=_archive_stat_identity(before);cached=getattr(self,"_archive_identity_cache",None)
        cached_prefix_valid=(isinstance(cached,dict)
            and isinstance(cached.get("prefix_bytes"),int) and cached.get("prefix_bytes")>=0
            and isinstance(cached.get("zip_start_dir"),int) and cached.get("zip_start_dir")==cached.get("prefix_bytes")
            and isinstance(cached.get("prefix_sha256"),str) and len(cached.get("prefix_sha256"))==64
            and all(c in "0123456789abcdef" for c in cached.get("prefix_sha256")))
        if (cached and cached.get("identity")==identity and cached.get("sha256")==expected_sha256
                and cached_prefix_valid and cached.get("prefix_bytes")==prefix_bytes):
            return cached["prefix_sha256"]
        actual,prefix_sha,total=sha256_file_and_prefix(self.archive,prefix_bytes)
        after=self.archive.stat()
        if _archive_stat_identity(after)!=identity or total!=before.st_size:raise AmbiguousState("cold ZIP changed while verifying prefix")
        if actual!=expected_sha256:raise AmbiguousState("archive changed after cold-store prepare")
        return prefix_sha
    def _member_entry(self,manifest,logical):
        matches=[]
        for row in manifest.get("members",[]):
            canonical=_safe_rel(row.get("logical_path"))
            aliases=row.get("aliases")
            if not isinstance(aliases,list):raise AmbiguousState("cold member lacks alias inventory")
            safe_aliases={_safe_rel(x) for x in aliases}
            if canonical==logical or logical in safe_aliases:matches.append(row)
        if len(matches)>1:raise AmbiguousState("logical path or alias is ambiguous in cold manifest")
        if not matches:return None
        result=dict(matches[0]);canonical=_safe_rel(result["logical_path"])
        result["canonical_logical_path"]=canonical
        result["requested_logical_path"]=logical
        result["resolved_from_alias"]=logical!=canonical
        return result
    def _codec_options(self):
        source=self.joblib_compressor_source_path
        if source is None:
            candidates=[Path(sys.prefix)/"lib"/"python3.12"/"site-packages"/"joblib"/"compressor.py",
                        self.root/"venv"/"lib"/"python3.12"/"site-packages"/"joblib"/"compressor.py",
                        Path("/usr/lib/python3/dist-packages/joblib/compressor.py")]
            source=next((p for p in candidates if p.is_file() and not p.is_symlink()),None)
            if source is None:
                import joblib.compressor
                source=Path(joblib.compressor.__file__)
        source=Path(source)
        if source.is_symlink() or not source.is_file():raise AmbiguousState("pinned joblib compressor source must be a regular file")
        temp_root=self.runtime/"tmp"/"cold_codec_read"
        # Check every existing ancestor before mkdir can follow any symlink.
        try:temp_root.resolve(strict=False).relative_to(self.runtime)
        except ValueError as e:raise AmbiguousState("codec temporary root escapes runtime") from e
        ancestor=temp_root
        while ancestor!=self.runtime:
            if ancestor.is_symlink():raise AmbiguousState("codec temporary path crosses symlink")
            ancestor=ancestor.parent
        temp_root.mkdir(parents=True,exist_ok=True)
        if temp_root.is_symlink() or not temp_root.is_dir():raise AmbiguousState("codec temporary root must be a regular directory")
        return {"temp_root":temp_root,"joblib_compressor_source_path":source}
    def _has_completed_logical_verification(self,entry):
        """Metadata-only shortcut; actual open always reconstructs exact bytes.

        Only a complete creator journal made by this exact imported verifier is
        accepted. Its immutable logical/physical descriptor must match this row.
        Physical bytes are still hashed against that descriptor by the caller.
        Missing/private-omitted/old-version proof falls back to full decoding.
        """
        tx=entry.get("transaction_id")
        if not isinstance(tx,str) or len(tx)!=32 or any(c not in "0123456789abcdef" for c in tx):
            return False
        p=self._journal_dir(tx)/"journal.json"
        if p.is_symlink() or p.parent.is_symlink() or not p.is_file():return False
        try:
            p.resolve(strict=True).relative_to(self.journals)
            j=json.loads(p.read_text())
        except (OSError,ValueError):return False
        if not isinstance(j,dict) or not isinstance(j.get("items"),list) or any(not isinstance(x,dict) for x in j["items"]):return False
        verifier=j.get("codec_verifier_source_sha256")
        if j.get("transaction_id")!=tx or j.get("state")!="complete":
            return False
        if verifier not in (_IMPORTED_SOURCE_SHA256,_LEGACY_CORE_SHA256):
            return False
        items=[x for x in j.get("items",[]) if x.get("logical_path")==entry.get("logical_path")]
        if len(items)!=1:return False
        old=items[0]
        keys=("logical_path","archive_member","sha256","bytes","crc32","header_offset","storage_encoding")
        if any(old.get(k)!=entry.get(k) for k in keys):return False
        desc=entry.get("storage_encoding")
        if not isinstance(desc,dict):return False
        try:
            manifest=_codec_storage._codec_manifest(entry)
            opts=self._codec_options()
            _codec_storage.codec._manifest(manifest,opts["joblib_compressor_source_path"],
                _codec_storage.codec.DEFAULT_MAX_PAYLOAD_BYTES,_codec_storage.codec.DEFAULT_MAX_FILE_BYTES)
        except Exception:return False
        proof={"protocol":_CODEC_PROOF_PROTOCOL,"verifier_source_sha256":_IMPORTED_SOURCE_SHA256,
            "logical_sha256":entry["sha256"],"logical_bytes":int(entry["bytes"]),
            "logical_crc32":int(entry["crc32"]),
            "storage_descriptor_sha256":_sha_bytes(json.dumps(desc,sort_keys=True,separators=(",",":")).encode())}
        if verifier==_IMPORTED_SOURCE_SHA256:
            return old.get("logical_verification")==proof
        legacy_proof=dict(proof);legacy_proof["verifier_source_sha256"]=_LEGACY_CORE_SHA256
        if old.get("logical_verification")!=legacy_proof:return False
        return self._has_bound_historical_logical_verification(entry,old)
    def _has_bound_historical_logical_verification(self,entry,journal_item):
        # Historical verifier proofs are accepted only through one immutable,
        # qualified metadata receipt. Any mismatch falls through to full decode.
        legacy=_LEGACY_CORE_SHA256
        history_sha=_LEGACY_HISTORY_SHA256
        pass_sha=_LEGACY_PASS_SHA256
        runtime=self.runtime
        hp=runtime/"manifests"/"COLD_VERIFIER_HISTORY_20261028.json"
        sp=runtime/"reports"/"validation_sources"/"storage_core_history"/("cold_model_storage_"+legacy+".py")
        pp=runtime/"reports"/"PORTABLE_TEST_PASS_908e78202071352c0a9798b714f1704b2e7e19fd9bb2252e477f9deebeed7465.json"
        try:
            for q in (hp,sp,pp):
                if q.is_symlink() or not q.is_file():return False
            if sha256_file(hp)!=history_sha or sha256_file(sp)!=legacy or sha256_file(pp)!=pass_sha:return False
            history=json.loads(hp.read_text());passed=json.loads(pp.read_text())
            expected_keys={"schema","historical_core_sha256","qualified_pass_sha256","qualified_pass_bundle_fingerprint","qualified_pass_count","entries"}
            if set(history)!=expected_keys or history.get("schema")!="cold-model-legacy-logical-proof-history/1" or history.get("historical_core_sha256")!=legacy or history.get("qualified_pass_sha256")!=pass_sha or history.get("qualified_pass_bundle_fingerprint")!="908e78202071352c0a9798b714f1704b2e7e19fd9bb2252e477f9deebeed7465" or history.get("qualified_pass_count")!=509:return False
            if not isinstance(history.get("entries"),list) or len(history["entries"])!=_LEGACY_HISTORY_ENTRY_COUNT:return False
            if passed.get("schema_version")!="lamost-terminal-portable-tests/1" or passed.get("status")!="passed" or passed.get("exit_code")!=0 or passed.get("expected_test_count")!=509 or passed.get("passed_test_count")!=509 or passed.get("bundle_fingerprint_sha256")!=history.get("qualified_pass_bundle_fingerprint") or passed.get("source_hashes",{}).get("runtime_20261025/source/cold_model_storage.py")!=legacy:return False
            matches=[x for x in history.get("entries",[]) if isinstance(x,dict) and x.get("logical_path")==entry.get("logical_path")]
            if len(matches)!=1:return False
            h=matches[0]
            if set(h)!={"logical_path","transaction_id","verifier_source_sha256","journal_sha256","entry_sha256","logical_verification_sha256"}:return False
            jp=self._journal_dir(entry.get("transaction_id"))/"journal.json"
            jb=jp.read_bytes();j=json.loads(jb)
            if (_sha_bytes(jb)!=h.get("journal_sha256") or j.get("transaction_id")!=entry.get("transaction_id")
                or j.get("state")!="complete" or j.get("codec_verifier_source_sha256")!=legacy
                or h.get("transaction_id")!=entry.get("transaction_id") or h.get("verifier_source_sha256")!=legacy):return False
            canon=lambda x:json.dumps(x,sort_keys=True,separators=(",",":")).encode()
            if _sha_bytes(canon(entry))!=h.get("entry_sha256"):return False
            if _sha_bytes(canon(journal_item.get("logical_verification")))!=h.get("logical_verification_sha256"):return False
            return True
        except (OSError,ValueError,TypeError,KeyError):return False
    def _verified_member_metadata(self,logical,entry):
        with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:
            try:i=z.getinfo(entry["archive_member"])
            except KeyError as e:raise AmbiguousState("manifest member absent from cold ZIP") from e
            if i.compress_type!=zipfile.ZIP_STORED:raise AmbiguousState("model member must be ZIP_STORED")
            if "storage_encoding" in entry:
                desc=entry["storage_encoding"]
                if (i.file_size!=int(desc.get("encoded_size_bytes",-1)) or i.CRC!=int(desc.get("encoded_crc32",-1)) or i.header_offset!=int(entry["header_offset"])):
                    raise AmbiguousState("encoded ZIP physical identity differs from cold manifest")
                if self._has_completed_logical_verification(entry):
                    with z.open(i,"r") as f:h,n,crc=_stream_hash(f)
                    if (h,n,crc)!=(desc["encoded_sha256"],int(desc["encoded_size_bytes"]),int(desc["encoded_crc32"])):
                        raise AmbiguousState("encoded physical payload differs from completed logical proof")
                    return i
            else:
                if i.file_size!=int(entry["bytes"]) or i.CRC!=int(entry["crc32"]) or i.header_offset!=int(entry["header_offset"]):
                    raise AmbiguousState("ZIP central-directory identity differs from cold manifest")
                with z.open(i,"r") as f:h,n,crc=_stream_hash(f)
                if h!=entry["sha256"] or n!=int(entry["bytes"]) or crc!=int(entry["crc32"]):
                    raise AmbiguousState("cold member stream SHA/size/CRC mismatch")
                return i
        try:
            with _codec_storage.open_logical_member(self.archive,entry,**self._codec_options()) as f:
                while f.read(8<<20):pass
        except Exception as e:
            raise AmbiguousState("encoded cold member failed logical round-trip verification") from e
        return i
    @contextmanager
    def open_verified(self,logical_path,expected_sha256=None):
        logical=_safe_rel(logical_path)
        with self._read_lock():
            physical=self._physical_path(logical)
            if physical.exists() or physical.is_symlink():
                if physical.is_symlink() or not physical.is_file():raise AmbiguousState("physical artifact exists but is not a regular file")
                manifest=_manifest_load(self.manifest);entry=self._member_entry(manifest,logical)
                expected=entry["sha256"] if entry else expected_sha256
                if not expected:raise UnsafePlan("physical artifact read requires a committed or caller-provided SHA-256")
                if sha256_file(physical)!=expected:raise AmbiguousState("physical artifact hash mismatch; refusing archive fallback")
                if expected_sha256 and expected_sha256!=expected:raise AmbiguousState("caller artifact SHA differs from manifest")
                with physical.open("rb") as f:yield f
                return
            manifest=_manifest_load(self.manifest);archive_sha,_,_=self._check_archive_manifest(manifest);entry=self._member_entry(manifest,logical)
            if not entry:raise FileNotFoundError(logical)
            if expected_sha256 and expected_sha256!=entry["sha256"]:raise AmbiguousState("caller artifact SHA differs from archive manifest")
            if "storage_encoding" in entry:
                try:
                    with _codec_storage.open_logical_member(self.archive,entry,**self._codec_options()) as f:
                        yield f
                except Exception as e:
                    raise AmbiguousState("encoded cold member failed logical round-trip verification") from e
            else:
                self._verified_member_metadata(logical,entry)
                with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:
                    with z.open(entry["archive_member"],"r") as f:yield f
    def read_bytes(self,logical_path,expected_sha256=None):
        with self.open_verified(logical_path,expected_sha256) as f:return f.read()
    def sha256(self,logical_path,expected_sha256=None):
        with self.open_verified(logical_path,expected_sha256) as f:return _stream_hash(f)[0]
    def load_joblib(self,logical_path,expected_sha256=None):
        import joblib
        with self.open_verified(logical_path,expected_sha256) as f:return joblib.load(f)
    def artifact_stat(self,logical_path,expected_sha256=None):
        logical=_safe_rel(logical_path)
        with self._read_lock():
            p=self._physical_path(logical);m=_manifest_load(self.manifest);entry=self._member_entry(m,logical)
            if p.exists() or p.is_symlink():
                if p.is_symlink() or not p.is_file():raise AmbiguousState("physical artifact is not regular")
                h=sha256_file(p);st=p.stat()
                if entry and h!=entry["sha256"]:raise AmbiguousState("physical artifact hash mismatch")
                if expected_sha256 and h!=expected_sha256:raise AmbiguousState("physical artifact differs from requested SHA")
                if not entry and not expected_sha256:raise UnsafePlan("physical artifact stat requires a committed or caller-provided SHA-256")
                return {"logical_path":logical,"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":h,"backing":"physical","cache_identity":{"backing":"physical","size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":h}}
            if not entry:raise FileNotFoundError(logical)
            if expected_sha256 and entry["sha256"]!=expected_sha256:raise AmbiguousState("archive artifact differs from requested SHA")
            archive_sha,ast,_=self._check_archive_manifest(m);info=self._verified_member_metadata(logical,entry)
            if "storage_encoding" in entry:
                desc=entry["storage_encoding"]
                physical_sha=desc["encoded_sha256"];physical_size=int(desc["encoded_size_bytes"]);physical_crc=int(desc["encoded_crc32"])
                recipe_sha=_sha_bytes(json.dumps({k:v for k,v in desc.items() if k not in {"encoded_sha256","encoded_size_bytes","encoded_crc32"}},sort_keys=True,separators=(",",":")).encode())
                cache={"backing":"cold_zip_codec","archive_sha256":archive_sha,"archive_ctime_ns":ast.st_ctime_ns,"member":entry["archive_member"],"header_offset":int(entry["header_offset"]),"payload_crc32":physical_crc,"payload_bytes":physical_size,"payload_sha256":physical_sha,"logical_crc32":int(entry["crc32"]),"logical_bytes":int(entry["bytes"]),"logical_sha256":entry["sha256"],"recipe_sha256":recipe_sha}
            else:
                physical_sha=entry["sha256"];physical_size=int(entry["bytes"]);physical_crc=int(entry["crc32"])
                cache={"backing":"cold_zip","archive_sha256":archive_sha,"archive_ctime_ns":ast.st_ctime_ns,"member":entry["archive_member"],"header_offset":int(entry["header_offset"]),"crc32":physical_crc,"bytes":physical_size,"sha256":physical_sha}
            return {"logical_path":logical,"canonical_logical_path":entry["canonical_logical_path"],"requested_logical_path":logical,"resolved_from_alias":entry["resolved_from_alias"],"size":int(entry["bytes"]),"mtime_ns":int(entry["source_mtime_ns"]),"sha256":entry["sha256"],"logical_crc32":int(entry["crc32"]),"backing":"cold_zip","archive_path":str(self.archive),"archive_sha256":archive_sha,"archive_size_bytes":ast.st_size,"archive_mtime_ns":ast.st_mtime_ns,"archive_ctime_ns":ast.st_ctime_ns,"archive_member":entry["archive_member"],"member_crc32":physical_crc,"member_header_offset":int(info.header_offset),"member_size":physical_size,"member_sha256":physical_sha,"storage_format":entry.get("storage_encoding",{}).get("codec_version","raw-v1"),"payload_crc32":physical_crc,"payload_size":physical_size,"payload_sha256":physical_sha,"cache_identity":cache,**({"storage_encoding":entry["storage_encoding"]} if "storage_encoding" in entry else {})}
    def _normalize(self,items,records):
        _verify_records(records);out=[];used=set()
        # Capture all requested inode aliases with one root walk. Per-item
        # validation below still checks task, publication, SHA, closure, and
        # every alias owner independently.
        source_paths=[]
        for item in items:
            key=str(item["producer_task"]);expected=f"runtime_20261025/artifacts/{key}/pipeline.joblib"
            src_rel=_safe_rel(str(item["source_relpath"]))
            if src_rel!=expected or _safe_rel(str(item["source_path"]))!=expected:
                raise UnsafePlan("RF pipeline logical path must be canonical task path")
            source=self._physical_path(src_rel)
            if source.is_symlink() or not source.is_file():raise UnsafePlan("candidate source must be a regular pipeline file")
            source_paths.append(source)
        inode_inventory=_safety.inode_paths_within_root_many(self.root,source_paths) if source_paths else {}
        for item in items:
            if "storage_encoding" in item:
                raise UnsafePlan("staged reader supports encoded rows, but raw commit_models writer does not accept encoded items")
            key=str(item["producer_task"]);t=records.get(key)
            if not t or not _successful(t):raise UnsafePlan("RF producer is not validated successful")
            if item.get("method") is not None and item.get("method")!=t.get("method"):
                raise AmbiguousState("candidate method differs from validated task record")
            if t.get("kind")!="fit" or t.get("method") not in _ARCHIVABLE_FIT_METHODS or int(t.get("experiment",0)) not in (3,4,5,6):raise UnsafePlan("cold store scope is unsupported or out-of-scope validated fit")
            expected=f"runtime_20261025/artifacts/{key}/pipeline.joblib"
            expected_dir=(self.root/"runtime_20261025"/"artifacts"/key).resolve(strict=False)
            if Path(str(t.get("artifact_dir", ""))).resolve(strict=False)!=expected_dir:raise UnsafePlan("producer artifact_dir does not match canonical task path")
            src_rel=_safe_rel(str(item["source_relpath"]));source_rel=_safe_rel(str(item["source_path"]))
            if src_rel!=expected or source_rel!=expected or _safe_rel(str(item["archive_member"]))!=expected:raise UnsafePlan("RF pipeline logical path must be canonical task path")
            recorded=_pipeline_hash(t);src=self._physical_path(source_rel).resolve(strict=True)
            if src.is_symlink() or not src.is_file():raise UnsafePlan("candidate source must be a regular pipeline file")
            actual=sha256_file(src)
            if actual!=recorded or item.get("source_sha256")!=actual or item.get("recorded_artifact_sha256")!=actual:raise UnsafePlan("source/validation pipeline SHA mismatch")
            inode=(src.stat().st_dev,src.stat().st_ino);snapshot=inode_inventory.get(inode)
            if snapshot is None:raise AmbiguousState("source inode was not present in batch inventory")
            aliases=snapshot["paths"];nlink=snapshot["link_count"]
            alias_rels=sorted(p.relative_to(self.root).as_posix() for p in aliases)
            source_st=src.stat(follow_symlinks=False)
            if snapshot["source_identity"]!=(source_st.st_dev,source_st.st_ino,source_st.st_size,source_st.st_mtime_ns,source_st.st_ctime_ns,source_st.st_nlink):
                raise AmbiguousState("source identity changed after batch inode inventory")
            if set(item.get("aliases",[]))!=set(alias_rels):raise UnsafePlan("hardlink alias inventory incomplete or changed")
            closure=sorted(_consumer_closure(key,records))
            if set(item.get("consumer_tasks",[]))!=set(closure):raise UnsafePlan("declared consumer closure differs from effective graph")
            metadata_contract=self._consumer_contract(key,closure,records,item.get("metadata_only_consumer_contract"))
            alias_owners=[];owner_required=set()
            for alias_rel in alias_rels:
                matched=[]
                for candidate in records.values():
                    candidate_key=candidate.get("key")
                    if alias_rel==f"runtime_20261025/artifacts/{candidate_key}/pipeline.joblib":matched.append(candidate)
                    elif candidate_key and candidate.get("artifact_dir"):
                        attempt_id=(candidate.get("result") or {}).get("attempt_id");task_sha=(candidate.get("result") or {}).get("task_sha256")
                        if attempt_id and alias_rel==f"runtime_20261025/artifacts/{candidate_key}/attempts/{attempt_id}/pipeline.joblib":matched.append(candidate)
                        if task_sha and alias_rel==f"runtime_20261025/artifacts/{candidate_key}/checkpoints/{task_sha}/pipeline.joblib":matched.append(candidate)
                if len(matched)!=1:raise UnsafePlan("hardlink alias is not an exact canonical/publication-bound task pipeline: "+alias_rel)
                owner=matched[0];owner_key=owner["key"]
                if not _successful(owner) or owner.get("kind")!="fit" or owner.get("method") not in _ARCHIVABLE_FIT_METHODS or int(owner.get("experiment",0)) not in (3,4,5,6):
                    raise UnsafePlan("hardlink alias owner is not a validated runtime RF fit: "+alias_rel)
                if _pipeline_hash(owner)!=actual:raise UnsafePlan("hardlink alias owner records a different pipeline SHA: "+alias_rel)
                owner_closure=sorted(_consumer_closure(owner_key,records))
                owner_contract=self._consumer_contract(owner_key,owner_closure,records,
                    item.get("metadata_only_consumer_contract") if owner_key==key else None)
                receipt=self._alias_publication_evidence(owner,alias_rel,actual)
                alias_owners.append({"alias_path":alias_rel,"task_key":owner_key,"task_sha256":(owner.get("result") or {}).get("task_sha256"),"consumer_tasks":owner_closure,**({"metadata_only_consumer_contract":owner_contract} if owner_contract else {}),**receipt})
                contract_tasks={x["task_key"] for x in (owner_contract or {}).get("pending_metadata_fit_tasks",[])}
                contract_tasks|={x["task_key"] for x in (owner_contract or {}).get("pending_own_fit_evaluations",[])}
                owner_required|={owner_key}|(set(owner_closure)-contract_tasks)
            owner_required=self._validate_alias_owner_records(alias_rels,alias_owners,actual,records)
            if key in used:raise UnsafePlan("duplicate producer in batch")
            used.add(key)
            out.append({"task_key":key,"task_sha256":t.get("result",{}).get("task_sha256"),"experiment":int(t["experiment"]),"method":t["method"],"logical_path":expected,"source_relpath":expected,"archive_member":_archive_member_for(expected,actual),"sha256":actual,"bytes":src.stat().st_size,"source_mtime_ns":src.stat().st_mtime_ns,"crc32":None,"header_offset":None,"consumer_tasks":closure,**({"metadata_only_consumer_contract":metadata_contract} if metadata_contract else {}),"aliases":alias_rels,"alias_owners":alias_owners,"alias_owner_task_keys":sorted(owner_required),"device":src.stat().st_dev,"inode":src.stat().st_ino,"source_ctime_ns":src.stat().st_ctime_ns,"link_count":nlink,"removed_aliases":[],"unlink_intents":[]})
        return out
    def _journal_dir(self,tx):return self.journals/tx
    def _backup_tail(self,j):
        tail=self._journal_dir(j["transaction_id"])/"old_central_tail.bin"
        tail.parent.mkdir(parents=True,exist_ok=True)
        with open(self.archive,"rb") as src,open(tail,"xb") as dst:
            src.seek(j["central_directory_offset"]);shutil.copyfileobj(src,dst,8<<20);dst.flush();os.fsync(dst.fileno())
        _fsync_dir(tail.parent)
        return tail
    def _verify_transaction_item(self,item,rec,z):
        if not rec or rec["compress_type"]!=zipfile.ZIP_STORED:
            raise AmbiguousState("transaction model ZIP record invalid")
        if int(rec["header_offset"])!=int(item["header_offset"]):
            raise AmbiguousState("transaction model header offset changed")
        if "storage_encoding" in item:
            desc=item["storage_encoding"]
            if int(rec["file_size"])!=int(desc["encoded_size_bytes"]) or int(rec["crc32"])!=int(desc["encoded_crc32"]):
                raise AmbiguousState("transaction encoded physical record mismatch")
            # This verifies encoded bytes, then reconstructs and verifies every
            # original logical byte before any source alias can be removed.
            try:
                with _codec_storage.open_logical_member(self.archive,item,**self._codec_options()) as f:
                    while f.read(1<<20):pass
            except Exception as e:
                raise AmbiguousState("transaction encoded logical round trip failed") from e
            item["logical_verification"]={"protocol":_CODEC_PROOF_PROTOCOL,"verifier_source_sha256":_IMPORTED_SOURCE_SHA256,
                "logical_sha256":item["sha256"],"logical_bytes":int(item["bytes"]),
                "logical_crc32":int(item["crc32"]),
                "storage_descriptor_sha256":_sha_bytes(json.dumps(desc,sort_keys=True,separators=(",",":")).encode())}
        else:
            if int(rec["file_size"])!=int(item["bytes"]):
                raise AmbiguousState("transaction raw size mismatch")
            with z.open(item["archive_member"]) as f:h,n,crc=_stream_hash(f)
            if (h,n,crc)!=(item["sha256"],item["bytes"],item["crc32"]) or crc!=rec["crc32"]:
                raise AmbiguousState("transaction raw payload SHA/size/CRC mismatch")
    def _verify_live_alias_snapshot(self,items):
        for item in items:
            # Low-level append callers may supply synthetic raw rows; only
            # normalized commit transactions carry an alias snapshot.
            if "aliases" not in item:continue
            expected=len(item["aliases"])
            for rel in item["aliases"]:
                p=self._physical_path(rel)
                if p.is_symlink() or not p.is_file():raise AmbiguousState("alias changed before archive commit: "+rel)
                st=p.stat(follow_symlinks=False)
                if (st.st_dev,st.st_ino)!=(item["device"],item["inode"]):raise AmbiguousState("alias inode changed before archive commit: "+rel)
                if st.st_nlink!=expected:raise AmbiguousState("hardlink count changed before archive commit: "+rel)
                # Legacy journal/test rows predate source_ctime_ns. Preserve their inode, alias, and link-count checks; new normalized commits also bind ctime to catch write-and-restore mutations.
                if "source_ctime_ns" in item and st.st_ctime_ns!=item["source_ctime_ns"]:raise AmbiguousState("source inode metadata changed before archive commit: "+rel)

    def _append_locked(self,j,fault_after_bytes=None):
        st=self.archive.stat();identity=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        cached=self._archive_identity_cache
        if not (cached and cached.get("identity")==identity and cached.get("sha256")==j["archive_sha256_before"]):
            if sha256_file(self.archive)!=j["archive_sha256_before"]:
                raise AmbiguousState("archive changed after cold-store prepare")
        if j.get("storage_codec_policy") not in (None,"reversible-xz-v1"):
            raise AmbiguousState("unsupported journal storage policy")
        jp=self._journal_dir(j["transaction_id"])/"journal.json"
        # Temporary payloads are reproducible derivatives only. The journal,
        # source aliases, old central tail and old archive remain retained.
        with tempfile.TemporaryDirectory(prefix="encoding-",dir=jp.parent) as td:
            payloads={}
            for item in j["items"]:
                source=self._physical_path(item["source_relpath"])
                if sha256_file(source)!=item["sha256"]:
                    raise AmbiguousState("source changed before payload preparation")
                if j.get("storage_codec_policy")=="reversible-xz-v1":
                    opts=self._codec_options();opts["temp_root"]=Path(td)
                    try:
                        payload,fields=_codec_storage.encode_entry_payload(source,archive_member=item["archive_member"],**opts)
                    except (_codec_storage.codec.UnsupportedCodec,_codec_storage.codec.CodecLimitError) as exc:
                        # A known unsupported codec is a storage fallback, never
                        # a new scientific failure or permission to alter data.
                        if sha256_file(source)!=item["sha256"]:
                            raise AmbiguousState("unsupported-codec source changed") from exc
                        item["storage_decision"]={"selected":"raw-v1","reason":"unsupported pinned codec or fixed storage-stream bound","detail":str(exc),"exception_type":type(exc).__name__}
                    else:
                        if fields["sha256"]!=item["sha256"] or fields["bytes"]!=item["bytes"]:
                            raise AmbiguousState("prepared codec logical identity differs from selected fit")
                        # Always prove a round trip even if this encoding gives
                        # no space benefit. No unverifiable derivative is used.
                        descriptor=fields["storage_encoding"]
                        manifest={k:v for k,v in descriptor.items() if k not in {"original_crc32","encoded_crc32"}}
                        with _codec_storage.codec.open_verified(payload,manifest,temp_root=td,joblib_compressor_source_path=opts["joblib_compressor_source_path"]) as f:
                            h,n,crc=_stream_hash(f)
                        if (h,n,crc)!=(item["sha256"],item["bytes"],fields["crc32"]):
                            raise AmbiguousState("preappend codec logical verification failed")
                        if descriptor["encoded_size_bytes"]<item["bytes"]:
                            item.update(fields);payloads[item["archive_member"]]=payload
                            item["storage_decision"]={"selected":descriptor["codec_version"],"reason":"verified exact original-byte restoration and smaller physical payload"}
                        else:
                            item["storage_decision"]={"selected":"raw-v1","reason":"verified encoding has no size benefit"}
                _atomic_json(jp,j)
            # A crash during preparation has not modified the archive; ordinary
            # precommit recovery restores the exact retained central directory.
            j["state"]="appending";_atomic_json(jp,j);written=0
            with zipfile.ZipFile(self.archive,"a",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
                for item in j["items"]:
                    encoded="storage_encoding" in item
                    source=payloads[item["archive_member"]] if encoded else self._physical_path(item["source_relpath"])
                    expected_size=int(item["storage_encoding"]["encoded_size_bytes"]) if encoded else int(item["bytes"])
                    info=zipfile.ZipInfo(item["archive_member"]);info.compress_type=zipfile.ZIP_STORED
                    info.file_size=expected_size;info.external_attr=(0o100444&0xffff)<<16
                    h=hashlib.sha256();n=0;crc=0
                    with open(source,"rb") as inp,z.open(info,"w",force_zip64=True) as dest:
                        while True:
                            b=inp.read(1<<20)
                            if not b:break
                            if fault_after_bytes is not None:
                                left=fault_after_bytes-written
                                if left<=0:raise RuntimeError("injected append interruption")
                                if len(b)>left:b=b[:left]
                            dest.write(b);h.update(b);n+=len(b);crc=zipfile.crc32(b,crc);written+=len(b)
                            if fault_after_bytes is not None and written>=fault_after_bytes:raise RuntimeError("injected append interruption")
                    if encoded:
                        d=item["storage_encoding"]
                        if (h.hexdigest(),n,crc&0xffffffff)!=(d["encoded_sha256"],d["encoded_size_bytes"],d["encoded_crc32"]):
                            raise AmbiguousState("encoded payload changed during ZIP append")
                    elif (h.hexdigest(),n)!=(item["sha256"],item["bytes"]):
                        raise AmbiguousState("raw source changed during ZIP append")
            fd=os.open(self.archive,os.O_RDONLY);os.fsync(fd);os.close(fd);_fsync_dir(self.archive.parent)
            with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:
                records=_zip_records_all(z);by={r["member"]:r for r in records};final_zip_start=z.start_dir
                if records[:len(j["old_zip_records"])]!=j["old_zip_records"]:
                    raise AmbiguousState("old ZIP records changed")
                for item in j["items"]:
                    rec=by.get(item["archive_member"])
                    if not rec:raise AmbiguousState("new transaction member absent")
                    item["header_offset"]=rec["header_offset"]
                    if "storage_encoding" not in item:item["crc32"]=rec["crc32"]
                    self._verify_transaction_item(item,rec,z)
            j["member_records_after"]=records
            before_hash=self.archive.stat();before_identity=_archive_stat_identity(before_hash)
            final_sha,prefix_hashes,final_size=sha256_file_and_prefixes(self.archive,(j["central_directory_offset"],final_zip_start))
            final_st=self.archive.stat();final_identity=_archive_stat_identity(final_st)
            if before_identity!=final_identity or final_size!=final_st.st_size:
                self._archive_identity_cache=None
                raise AmbiguousState("cold ZIP changed while computing final digest")
            if prefix_hashes[j["central_directory_offset"]]!=j["prefix_sha256"]:
                raise AmbiguousState("preexisting archive payload prefix changed during append")
            self._verify_live_alias_snapshot(j["items"])
            j["archive_sha256_after"]=final_sha
            self._archive_identity_cache={"identity":final_identity,"sha256":j["archive_sha256_after"],"zip_records":records,
                "prefix_bytes":final_zip_start,"prefix_sha256":prefix_hashes[final_zip_start],"zip_start_dir":final_zip_start}
            j["archive_bytes_after"]=final_st.st_size;j["state"]="archive_committed"
            j["archive_committed_utc"]=_safety.now_utc();_atomic_json(jp,j)
        return j
    def _write_manifest(self,j):
        previous=_manifest_load(self.manifest);current_sha=sha256_file(self.manifest) if self.manifest.exists() else None
        if previous.get("transaction_id")==j["transaction_id"] and previous.get("archive_sha256")==j["archive_sha256_after"]:
            j["manifest_sha256"]=current_sha;j["state"]="manifest_committed";_atomic_json(self._journal_dir(j["transaction_id"])/"journal.json",j);return
        if current_sha!=j.get("public_manifest_before_sha256"):raise AmbiguousState("cold public manifest changed during transaction")
        if previous.get("archive_sha256") not in (None,j["archive_sha256_before"]):raise AmbiguousState("cold public manifest is not bound to pre-append archive")
        if previous.get("archive_sha256") is not None and previous.get("zip_records")!=j["old_zip_records"]:raise AmbiguousState("cold public member records changed before append")
        all_members=list(previous.get("members",[]));existing={x["logical_path"]:x for x in all_members}
        for x in j["items"]:
            row={k:x[k] for k in ("task_key","task_sha256","experiment","method","logical_path","source_relpath","archive_member","sha256","bytes","source_mtime_ns","crc32","header_offset","consumer_tasks","aliases","alias_owners")}
            if "metadata_only_consumer_contract" in x:row["metadata_only_consumer_contract"]=x["metadata_only_consumer_contract"]
            if "storage_encoding" in x:row["storage_encoding"]=x["storage_encoding"]
            row.update({"backing":"cold_zip","transaction_id":j["transaction_id"]})
            if row["logical_path"] in existing and existing[row["logical_path"]]!=row:raise AmbiguousState("logical artifact already bound to conflicting ZIP member")
            if row["logical_path"] not in existing:all_members.append(row)
        doc={"schema_version":SCHEMA,"archive_path":self.archive.relative_to(self.root).as_posix(),"archive_sha256":j["archive_sha256_after"],"archive_bytes":j["archive_bytes_after"],"updated_utc":_safety.now_utc(),"members":sorted(all_members,key=lambda x:x["logical_path"]),"zip_records":j["member_records_after"],"previous_archive_sha256":j["archive_sha256_before"],"transaction_id":j["transaction_id"]}
        _atomic_json(self.manifest,doc);j["manifest_sha256"]=_sha_bytes(self.manifest.read_bytes());j["public_manifest_after_sha256"]=j["manifest_sha256"];j["state"]="manifest_committed";_atomic_json(self._journal_dir(j["transaction_id"])/"journal.json",j)
    def _verify_committed_manifest(self,j):
        if not self.manifest.is_file() or sha256_file(self.manifest)!=j.get("manifest_sha256"):raise AmbiguousState("committed public cold manifest changed or missing")
        doc=_manifest_load(self.manifest)
        if doc.get("transaction_id")!=j["transaction_id"] or doc.get("archive_sha256")!=j["archive_sha256_after"] or doc.get("zip_records")!=j["member_records_after"]:raise AmbiguousState("committed public manifest does not bind transaction/archive")
        members={x.get("logical_path"):x for x in doc.get("members",[])}
        for item in j["items"]:
            row=members.get(item["logical_path"])
            if not row or row.get("sha256")!=item["sha256"] or row.get("archive_member")!=item["archive_member"] or row.get("crc32")!=item["crc32"] or row.get("header_offset")!=item["header_offset"]:raise AmbiguousState("committed public manifest omits or mismatches model")
            if row.get("storage_encoding")!=item.get("storage_encoding"):raise AmbiguousState("committed codec descriptor differs from transaction")
    def _unlink_aliases(self,j,fail_after_unlinks=None):
        policy=j.get("unlink_checkpoint_policy")
        if policy is None:
            # Journals written before checkpoint batching retain byte-for-byte
            # legacy per-alias recovery behavior.
            return self._unlink_aliases_legacy(j,fail_after_unlinks)
        if policy!={"schema":"bounded-intent-batch/1","max_aliases":48}:
            raise AmbiguousState("unknown or malformed unlink checkpoint policy")
        return self._unlink_aliases_checkpointed(j,fail_after_unlinks)
    def _unlink_aliases_checkpointed(self,j,fail_after_unlinks=None):
        policy=j["unlink_checkpoint_policy"]
        jp=self._journal_dir(j["transaction_id"])/"journal.json"
        j["state"]="unlinking";_atomic_json(jp,j);done=0;seen=set();pending=[]
        for item in j["items"]:
            if not isinstance(item.get("aliases"),list) or not isinstance(item.get("unlink_intents"),list) or not isinstance(item.get("removed_aliases"),list):
                raise AmbiguousState("checkpointed item lacks alias journal state")
            for rel in item["aliases"]:
                rel=_safe_rel(rel)
                if rel in seen:raise AmbiguousState("duplicate alias path across checkpointed items: "+rel)
                seen.add(rel)
                if rel not in item["removed_aliases"]:pending.append((item,rel))
        max_aliases=policy["max_aliases"]
        for offset in range(0,len(pending),max_aliases):
            batch=pending[offset:offset+max_aliases];new_intents=[]
            # Publish intent for every still-present alias in this bounded
            # batch before unlinking any. Missing entries require an earlier
            # durable intent. Content, inode and link-count checks run once in
            # the existing verified unlink step below, immediately before use.
            for item,rel in batch:
                p=self._physical_path(rel)
                if not p.exists() and not p.is_symlink():
                    if rel not in item["unlink_intents"]:raise AmbiguousState("untracked alias disappeared after archive commit: "+rel)
                    if rel not in item["removed_aliases"]:item["removed_aliases"].append(rel)
                    continue
                if rel not in item["unlink_intents"]:
                    item["unlink_intents"].append(rel);new_intents.append(rel)
            if new_intents:_atomic_json(jp,j)
            # A zero-count injected crash models loss immediately after durable
            # intent publication and before the first filesystem unlink.
            if fail_after_unlinks==0 and done==0:raise RuntimeError("injected interruption after unlink intent batch")
            for item,rel in batch:
                if rel in item["removed_aliases"]:continue
                p=self._physical_path(rel)
                if not p.exists() and not p.is_symlink():
                    if rel not in item["unlink_intents"]:raise AmbiguousState("untracked alias disappeared after archive commit: "+rel)
                    item["removed_aliases"].append(rel);continue
                if p.is_symlink() or not p.is_file() or sha256_file(p)!=item["sha256"]:
                    raise AmbiguousState("alias changed after archive commit: "+rel)
                st=p.stat()
                if (st.st_dev,st.st_ino)!=(item["device"],item["inode"]):
                    raise AmbiguousState("alias inode changed after archive commit: "+rel)
                expected_links=len(item["aliases"])-len(item["removed_aliases"])
                if st.st_nlink!=expected_links:raise AmbiguousState("hardlink count changed after archive commit: "+rel)
                if rel not in item["unlink_intents"]:raise AmbiguousState("alias lacks durable unlink intent: "+rel)
                p.unlink();_fsync_dir(p.parent);item["removed_aliases"].append(rel);done+=1
                if fail_after_unlinks is not None and done>=fail_after_unlinks:
                    raise RuntimeError("injected interruption during alias removal")
            # One durable checkpoint records all completed or recovered-missing
            # aliases in this bounded batch.
            _atomic_json(jp,j)
        j["state"]="complete";j["completed_utc"]=time.time();_atomic_json(jp,j)
    def _unlink_aliases_legacy(self,j,fail_after_unlinks=None):
        jp=self._journal_dir(j["transaction_id"])/"journal.json";done=0
        j["state"]="unlinking";_atomic_json(jp,j)
        for item in j["items"]:
            for rel in item["aliases"]:
                if rel in item["removed_aliases"]:continue
                rel=_safe_rel(rel);p=self._physical_path(rel)
                if not p.exists() and not p.is_symlink():
                    if rel in item["unlink_intents"]:
                        item["removed_aliases"].append(rel);_atomic_json(jp,j);continue
                    raise AmbiguousState("untracked alias disappeared after archive commit: "+rel)
                if p.is_symlink() or not p.is_file() or sha256_file(p)!=item["sha256"]:raise AmbiguousState("alias changed after archive commit: "+rel)
                st=p.stat()
                if (st.st_dev,st.st_ino)!=(item["device"],item["inode"]):raise AmbiguousState("alias inode changed after archive commit: "+rel)
                expected_links=len(item["aliases"])-len(item["removed_aliases"])
                if st.st_nlink!=expected_links:raise AmbiguousState("hardlink count changed after archive commit: "+rel)
                item["unlink_intents"].append(rel);_atomic_json(jp,j)
                p.unlink();_fsync_dir(p.parent);item["removed_aliases"].append(rel);_atomic_json(jp,j);done+=1
                if fail_after_unlinks is not None and done>=fail_after_unlinks:raise RuntimeError("injected interruption during alias removal")
        j["state"]="complete";j["completed_utc"]=time.time();_atomic_json(jp,j)
    def commit_models(self,items,registry_records,fail_after_unlinks=None,fault_after_bytes=None):
        with self._write_lock():
            self._assert_no_pending_transactions()
            normalized=self._normalize(items,registry_records)
            required=set()
            for x in normalized:
                contract=x.get("metadata_only_consumer_contract") or {}
                metadata_tasks={v["task_key"] for v in contract.get("pending_metadata_fit_tasks",[]) if registry_records[v["task_key"]].get("status")!="validated_terminal"}
                metadata_tasks|={v["task_key"] for v in contract.get("pending_own_fit_evaluations",[]) if registry_records[v["task_key"]].get("status")!="validated_terminal"}
                required|=(set(x["consumer_tasks"])-metadata_tasks)|{x["task_key"]}|set(x.get("alias_owner_task_keys",[]))
            self.archive.parent.mkdir(parents=True,exist_ok=True);self.journals.mkdir(parents=True,exist_ok=True)
            if not self.archive.is_file() or self.archive.is_symlink():raise UnsafePlan("cold archive must be pre-created as regular ZIP")
            old_stat=self.archive.stat();old_identity=_archive_stat_identity(old_stat);oldsize=old_stat.st_size
            with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:oldrec=_zip_records_all(z);start=z.start_dir
            current=_manifest_load(self.manifest)
            if current.get("archive_sha256") is None:
                oldsha,old_prefix_sha,total=sha256_file_and_prefix(self.archive,start)
                after_identity=_archive_stat_identity(self.archive.stat())
                if after_identity!=old_identity or total!=oldsize:raise AmbiguousState("cold ZIP changed while establishing empty baseline")
                if oldrec:raise AmbiguousState("nonempty cold archive lacks committed manifest")
                self._archive_identity_cache={"identity":old_identity,"sha256":oldsha,"zip_records":oldrec,
                    "prefix_bytes":start,"prefix_sha256":old_prefix_sha,"zip_start_dir":start}
            else:oldsha,_,_=self._check_archive_manifest(current)
            required|=self._validate_existing_members(current,registry_records)
            private_receipt=_safety.verify_no_matching_processes(self.root,required,registry_records)
            existing={r["member"] for r in oldrec};new={x["archive_member"] for x in normalized}
            if existing&new:raise UnsafePlan("cold ZIP member already exists")
            tx=uuid.uuid4().hex;d=self._journal_dir(tx);d.mkdir(parents=True,exist_ok=False)
            manifest_before_sha=sha256_file(self.manifest) if self.manifest.exists() else None
            j={"schema_version":SCHEMA,"transaction_id":tx,"state":"creating_backup","archive_relpath":self.archive.relative_to(self.root).as_posix(),"archive_sha256_before":oldsha,"archive_size_before":oldsize,"archive_device":self.archive.stat().st_dev,"archive_inode":self.archive.stat().st_ino,"central_directory_offset":start,"old_zip_records":oldrec,"old_zip_records_sha256":_record_sha(oldrec),"items":normalized,"required_task_keys":sorted(required),"process_inventory_complete":private_receipt.get("complete") is True,"created_utc":_safety.now_utc(),"public_manifest_before_sha256":manifest_before_sha,"member_records_after":None,"archive_sha256_after":None,"last_error":None}
            j["storage_codec_policy"]=self.storage_codec_policy
            j["codec_verifier_source_sha256"]=_IMPORTED_SOURCE_SHA256
            j["unlink_checkpoint_policy"]={"schema":"bounded-intent-batch/1","max_aliases":48}
            jp=d/"journal.json";_atomic_json(jp,j)
            _atomic_json(d/"private_process_inventory.json",{"observed_utc":private_receipt.get("observed_utc"),"task_count":private_receipt.get("task_count"),"matching_processes":private_receipt.get("matching_processes"),"complete":private_receipt.get("complete"),"checked_task_process_identities":private_receipt.get("checked_task_process_identities",[]),"private_operational_evidence":True})
            tail=self._backup_tail(j)
            j["tail_sha256"]=sha256_file(tail);j["prefix_sha256"]=self._verified_prefix_digest(oldsha,start);j["state"]="prepared";_atomic_json(jp,j)
            try:
                j=self._append_locked(j,fault_after_bytes);self._write_manifest(j);self._unlink_aliases(j,fail_after_unlinks)
            except BaseException as e:
                with contextlib.suppress(Exception):
                    j=json.loads(jp.read_text());j["last_error"]={"type":type(e).__name__,"message":str(e)};_atomic_json(jp,j)
                raise
            return tx
    def recover(self,txid,registry_records,fail_after_unlinks=None):
        with self._write_lock():
            jp=self._journal_dir(txid)/"journal.json";j=json.loads(jp.read_text())
            if j.get("transaction_id")!=txid:raise AmbiguousState("transaction ID mismatch")
            if j["state"]=="complete":return "complete"
            required=set(j["required_task_keys"])
            _verify_records(registry_records)
            for item in j["items"]:
                t=registry_records.get(item["task_key"])
                if not t or not _successful(t) or _pipeline_hash(t)!=item["sha256"]:raise UnsafePlan("producer evidence changed during recovery")
                if sorted(_consumer_closure(item["task_key"],registry_records))!=item["consumer_tasks"]:raise AmbiguousState("consumer closure changed during recovery")
                self._consumer_contract(item["task_key"],item["consumer_tasks"],registry_records,item.get("metadata_only_consumer_contract"))
                required|=self._validate_alias_owner_records(item.get("aliases"),item.get("alias_owners"),item["sha256"],registry_records)
            current_manifest=_manifest_load(self.manifest)
            precommit=j["state"] in ("creating_backup","prepared","appending")
            # A killed ZIP append may leave no readable central directory. Validate registry provenance
            # and consumer closure first, but do not open existing ZIP members until rollback restores it.
            existing_required=self._validate_existing_members(current_manifest,registry_records,verify_payload=not precommit)
            required|=existing_required
            _safety.verify_no_matching_processes(self.root,required,registry_records)
            if precommit:
                if any(x["removed_aliases"] for x in j["items"]):raise AmbiguousState("aliases removed before durable commit")
                if j["state"]=="creating_backup" and sha256_file(self.archive)==j["archive_sha256_before"]:
                    j["state"]="rolled_back";j["rolled_back_utc"]=time.time();_atomic_json(jp,j)
                else:self._rollback(j)
                # Only now is the pre-append archive guaranteed to be restored and safe to parse.
                if current_manifest.get("archive_sha256") is not None:
                    self._check_archive_manifest(current_manifest)
                    self._validate_existing_members(current_manifest,registry_records,verify_payload=True)
                elif current_manifest.get("members"):
                    raise AmbiguousState("pre-append manifest has members but no committed archive identity")
                return "rolled_back"
            if j["state"] in ("archive_committed","manifest_committed","unlinking"):
                # A caller may already have verified the whole-file digest and
                # seeded the exact five-stat cache. Otherwise this check hashes once.
                # Reuse only through the manifest checker, which rechecks the
                # same identity before/after and recomputes on any stat drift.
                if j["state"]=="archive_committed" and current_manifest.get("archive_sha256")!=j["archive_sha256_after"]:
                    # A crash before public-manifest publication retains the old
                    # manifest; verify the committed archive against the journal.
                    recovered_sha=sha256_file(self.archive)
                    with zipfile.ZipFile(self.archive,"r",allowZip64=True) as recovered_zip:
                        recovered_records=_zip_records_all(recovered_zip)
                else:
                    recovered_sha,_,recovered_records=self._check_archive_manifest(current_manifest)
                if recovered_sha!=j["archive_sha256_after"]:raise AmbiguousState("committed ZIP changed")
                if recovered_records!=j["member_records_after"]:raise AmbiguousState("committed ZIP records differ from transaction")
                with zipfile.ZipFile(self.archive,"r",allowZip64=True) as z:
                    by={x["member"]:x for x in recovered_records}
                    for item in j["items"]:
                        self._verify_transaction_item(item,by.get(item["archive_member"]),z)
                if j["state"]=="archive_committed":self._write_manifest(j)
                self._verify_committed_manifest(j)
                self._unlink_aliases(j,fail_after_unlinks);return "complete"
            raise AmbiguousState("unknown transaction state")
    def _rollback(self,j):
        for item in j["items"]:
            for rel in item["aliases"]:
                p=self.root/rel
                if not p.is_file() or p.is_symlink() or sha256_file(p)!=item["sha256"]:raise AmbiguousState("source alias changed before rollback")
        st=self.archive.stat()
        if (st.st_dev,st.st_ino)!=(j["archive_device"],j["archive_inode"]):raise AmbiguousState("archive identity changed; cannot rollback")
        tail=self._journal_dir(j["transaction_id"])/"old_central_tail.bin"
        if sha256_file(tail)!=j["tail_sha256"] or sha256_file_prefix(self.archive,j["central_directory_offset"])!=j["prefix_sha256"]:raise AmbiguousState("rollback tail/prefix verification failed")
        with open(self.archive,"r+b") as dst,open(tail,"rb") as src:
            dst.seek(j["central_directory_offset"]);shutil.copyfileobj(src,dst,8<<20);dst.truncate(j["archive_size_before"]);dst.flush();os.fsync(dst.fileno())
        _fsync_dir(self.archive.parent)
        if sha256_file(self.archive)!=j["archive_sha256_before"]:raise AmbiguousState("rollback archive SHA mismatch")
        j["state"]="rolled_back";j["rolled_back_utc"]=time.time();_atomic_json(self._journal_dir(j["transaction_id"])/"journal.json",j)
def sha256_file_prefix(path,nbytes):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        left=int(nbytes)
        while left:
            b=f.read(min(8<<20,left))
            if not b:raise AmbiguousState("archive prefix truncated")
            h.update(b);left-=len(b)
    return h.hexdigest()
