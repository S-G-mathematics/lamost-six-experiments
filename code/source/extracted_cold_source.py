"""Fail-closed resolver for codec-backed model members in an extracted full archive."""
from __future__ import annotations
import contextlib, hashlib, importlib.util, json, os, pathlib, tempfile, zipfile
from pathlib import PurePosixPath

class ExtractedColdError(RuntimeError): pass

_LEGACY_STORAGE_CODEC_POLICY="reversible-xz-v1"
_PAYLOAD12_STORAGE_CODEC_POLICY="reversible-xz-v1-payload12"
_LEGACY_MAX_PAYLOAD_BYTES=2<<30
_PAYLOAD12_MAX_PAYLOAD_BYTES=12<<30

def _codec_policy_manifest(encoded):
    """Validate storage metadata while keeping this extractor codec-only/standalone."""
    if not isinstance(encoded,dict):
        raise ExtractedColdError("encoded descriptor is malformed")
    has_policy="storage_codec_policy" in encoded
    has_cap="max_payload_bytes" in encoded
    if has_policy != has_cap:
        raise ExtractedColdError("encoded descriptor has an incomplete storage policy/cap")
    if not has_policy:
        cap=_LEGACY_MAX_PAYLOAD_BYTES
    else:
        policy=encoded.get("storage_codec_policy")
        expected={_LEGACY_STORAGE_CODEC_POLICY:_LEGACY_MAX_PAYLOAD_BYTES,
                  _PAYLOAD12_STORAGE_CODEC_POLICY:_PAYLOAD12_MAX_PAYLOAD_BYTES}.get(policy)
        if expected is None:
            raise ExtractedColdError("encoded descriptor has an unknown storage codec policy")
        stored=encoded.get("max_payload_bytes")
        if type(stored) is not int or stored!=expected:
            raise ExtractedColdError("encoded descriptor payload cap differs from its policy")
        cap=expected
    manifest={k:v for k,v in encoded.items()
              if k not in ("original_crc32","encoded_crc32","storage_codec_policy","max_payload_bytes")}
    return manifest,cap

def _sha_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def _crc_file(path):
    c=n=0
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): c=zipfile.crc32(b,c); n+=len(b)
    return c&0xffffffff,n

def _safe_rel(value):
    if not isinstance(value,str) or not value or "\\" in value: raise ExtractedColdError("invalid member path")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ("",".","..") for x in p.parts): raise ExtractedColdError("unsafe member path")
    return p.as_posix()

def _safe_file(root, rel):
    root=pathlib.Path(root).resolve(strict=True)
    p=root.joinpath(*PurePosixPath(_safe_rel(rel)).parts)
    cur=p
    while cur!=root:
        if cur.is_symlink(): raise ExtractedColdError("extracted payload path contains symlink")
        cur=cur.parent
    try: p.relative_to(root)
    except ValueError as e: raise ExtractedColdError("payload escapes extraction root") from e
    if not p.is_file(): raise FileNotFoundError(str(p))
    return p

class ExtractedColdSource:
    def __init__(self, migration_root, runtime, temp_root, codec_module_path,
                 compressor_source_path, projection_path=None):
        self.root=pathlib.Path(migration_root).resolve(strict=True)
        self.runtime=pathlib.Path(runtime).resolve(strict=True)
        self.temp_root=pathlib.Path(temp_root).resolve(strict=True)
        try: self.temp_root.relative_to(self.root)
        except ValueError as e: raise ExtractedColdError("temporary directory must be under extracted root") from e
        if self.temp_root.is_symlink() or not self.temp_root.is_dir(): raise ExtractedColdError("unsafe temporary directory")
        self.codec_path=pathlib.Path(codec_module_path).resolve(strict=True)
        self.compressor=pathlib.Path(compressor_source_path).resolve(strict=True)
        self.projection_path=pathlib.Path(projection_path) if projection_path else self.runtime/"manifests/cold_archived_artifact_members.json"
        self.projection_path=pathlib.Path(os.path.abspath(self.projection_path))
        self._check_projection_path()
        self.projection_stat=self.projection_path.stat()
        self.projection_sha=_sha_file(self.projection_path)
        try: doc=json.loads(self.projection_path.read_text(encoding="utf-8"))
        except Exception as e: raise ExtractedColdError("projection JSON is unreadable") from e
        if not isinstance(doc,dict) or doc.get("schema_version")!="lamost-cold-model-membership-snapshot/1" or not isinstance(doc.get("members"),list):
            raise ExtractedColdError("unsupported or malformed membership projection")
        self.rows={}
        for row in doc["members"]:
            if not isinstance(row,dict): raise ExtractedColdError("malformed projection member")
            logical=_safe_rel(row.get("logical_source_path"))
            if logical in self.rows: raise ExtractedColdError("ambiguous duplicate logical source path")
            self.rows[logical]=row
        physical_groups={}
        for logical,row in self.rows.items():
            member=_safe_rel(row.get("archive_member"))
            canonical=_safe_rel(row.get("canonical_logical_path") or logical)
            identity=(row.get("task_key"),row.get("task_sha256"),canonical,row.get("member_sha256"),
                row.get("member_bytes"),row.get("member_crc32"),row.get("logical_sha256"),row.get("logical_bytes"),
                row.get("logical_crc32"),json.dumps(row.get("storage_encoding"),sort_keys=True,separators=(",",":")))
            if member in physical_groups and physical_groups[member]!=identity:
                raise ExtractedColdError("ambiguous aliases disagree on physical member identity")
            physical_groups[member]=identity
        spec=importlib.util.spec_from_file_location("_lamost_reversible_codec_extracted",self.codec_path)
        if not spec or not spec.loader: raise ExtractedColdError("codec module cannot be loaded")
        self.codec=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.codec)

    def _check_projection_path(self):
        try: rel=self.projection_path.relative_to(self.root)
        except ValueError as e: raise ExtractedColdError("projection escapes extraction root") from e
        cur=self.root
        for part in rel.parts:
            cur=cur/part
            if cur.is_symlink(): raise ExtractedColdError("membership projection path contains a symlink")
        if not self.projection_path.is_file(): raise ExtractedColdError("membership projection disappeared or is not a regular file")

    def _check_projection_unchanged(self):
        self._check_projection_path()
        current=self.projection_path.stat(); initial=self.projection_stat
        if ((current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)!=(initial.st_dev,initial.st_ino,initial.st_size,initial.st_mtime_ns,initial.st_ctime_ns)
            or _sha_file(self.projection_path)!=self.projection_sha):
            raise ExtractedColdError("membership projection changed after resolver initialization")

    def _row(self, logical_path, expected_sha256=None):
        self._check_projection_unchanged()
        rel=_safe_rel(logical_path)
        row=self.rows.get(rel)
        if row is None: raise FileNotFoundError(rel)
        # Bind alias to canonical source and archive member; no fallback by basename.
        canonical=_safe_rel(row.get("canonical_logical_path") or rel)
        archive_member=_safe_rel(row.get("archive_member"))
        if row.get("logical_source_path")!=rel or not row.get("task_key") or not row.get("task_sha256"):
            raise ExtractedColdError("projection identity fields missing")
        if row.get("resolved_from_alias") not in (True,False): raise ExtractedColdError("invalid alias identity")
        aliases=row.get("aliases")
        if not isinstance(aliases,list) or any(not isinstance(x,str) for x in aliases): raise ExtractedColdError("invalid alias list")
        if rel!=canonical and rel not in aliases: raise ExtractedColdError("alias is not listed by canonical row")
        encoded=row.get("storage_encoding")
        logical_sha=row.get("logical_sha256")
        logical_size=row.get("logical_bytes")
        logical_crc=row.get("logical_crc32")
        if encoded is None:
            logical_sha=logical_sha or row.get("member_sha256")
            logical_size=logical_size if logical_size is not None else row.get("member_bytes")
            logical_crc=logical_crc if logical_crc is not None else row.get("member_crc32")
        if not isinstance(logical_sha,str) or len(logical_sha)!=64 or type(logical_size) is not int or logical_size<1 or type(logical_crc) is not int:
            raise ExtractedColdError("logical identity is missing")
        if expected_sha256 is not None and expected_sha256!=logical_sha:
            raise ExtractedColdError("logical SHA differs from caller's validated identity")
        physical_sha=row.get("member_sha256"); physical_size=row.get("member_bytes"); physical_crc=row.get("member_crc32")
        if not isinstance(physical_sha,str) or len(physical_sha)!=64 or type(physical_size) is not int or physical_size<1 or type(physical_crc) is not int:
            raise ExtractedColdError("physical identity is missing")
        if encoded:
            if not isinstance(encoded,dict) or row.get("storage_format")!=encoded.get("codec_version"):
                raise ExtractedColdError("encoded descriptor/version mismatch")
            if (encoded.get("encoded_sha256"),encoded.get("encoded_size_bytes"),encoded.get("encoded_crc32"))!=(physical_sha,physical_size,physical_crc):
                raise ExtractedColdError("encoded descriptor differs from physical projection")
            if (encoded.get("original_sha256"),encoded.get("original_size_bytes"),encoded.get("original_crc32"))!=(logical_sha,logical_size,logical_crc):
                raise ExtractedColdError("encoded descriptor differs from logical projection")
            _codec_policy_manifest(encoded)
        else:
            if (physical_sha,physical_size,physical_crc)!=(logical_sha,logical_size,logical_crc):
                raise ExtractedColdError("raw member physical/logical identities disagree")
        row=dict(row)
        row.setdefault("logical_sha256",logical_sha); row.setdefault("logical_bytes",logical_size); row.setdefault("logical_crc32",logical_crc)
        return rel,row,archive_member,encoded

    def _physical(self, rel,row,archive_member,encoded):
        # Full archive writes logical path aliases; canonical payload path may be used only
        # when the alias path is absent and the exact same member identity is present.
        # The full archive retains the unique physical ZIP-member payload;
        # encoded aliases are skipped by the default restorer.
        candidates=[archive_member]
        canonical=row.get("canonical_logical_path")
        for candidate in (rel,canonical):
            if candidate and candidate not in candidates: candidates.append(_safe_rel(candidate))
        found=[]
        for candidate in candidates:
            try: p=_safe_file(self.root,candidate)
            except FileNotFoundError: continue
            if _sha_file(p)==row["member_sha256"] and p.stat().st_size==row["member_bytes"]:
                crc,n=_crc_file(p)
                if n==row["member_bytes"] and crc==row["member_crc32"]: found.append(p)
        if not found: raise ExtractedColdError("no extracted payload matches the physical projection")
        # If both alias and canonical exist, they must be identical files or byte-identical.
        if any(_sha_file(x)!=row["member_sha256"] for x in found): raise ExtractedColdError("ambiguous extracted payloads")
        return found[0]

    def member_for(self, logical_path):
        self._check_projection_unchanged()
        rel=_safe_rel(logical_path)
        try: return dict(self.rows[rel])
        except KeyError as e: raise FileNotFoundError(rel) from e

    def stat(self, logical_path, expected_sha256=None):
        rel,row,member,encoded=self._row(logical_path,expected_sha256)
        p=self._physical(rel,row,member,encoded); st=p.stat()
        return {"sha256":row["logical_sha256"],"size":row["logical_bytes"],"logical_crc32":row["logical_crc32"],
                "backing":"cold_extracted","archive_member":member,"storage_format":row.get("storage_format","raw-v1"),
                "cache_identity":{"backing":"cold_extracted","projection_sha256":self.projection_sha,
                    "logical_path":rel,"logical_sha256":row["logical_sha256"],"logical_size":row["logical_bytes"],
                    "member_sha256":row["member_sha256"],"member_size":row["member_bytes"],"member_crc32":row["member_crc32"],
                    "device":st.st_dev,"inode":st.st_ino,"mtime_ns":st.st_mtime_ns,"ctime_ns":st.st_ctime_ns,
                    "recipe_sha256":hashlib.sha256(json.dumps(encoded,sort_keys=True,separators=(",",":")).encode()).hexdigest() if encoded else "raw-v1"}}

    artifact_stat = stat

    @contextlib.contextmanager
    def open(self, logical_path, expected_sha256=None):
        rel,row,member,encoded=self._row(logical_path,expected_sha256)
        p=self._physical(rel,row,member,encoded)
        before=p.stat()
        if not encoded:
            sha=_sha_file(p); crc,n=_crc_file(p)
            if (sha,n,crc)!=(row["logical_sha256"],row["logical_bytes"],row["logical_crc32"]): raise ExtractedColdError("raw logical identity mismatch")
            self._check_projection_unchanged()
            with p.open("rb") as raw:
                yield raw
            self._check_projection_unchanged()
            return
        try:
            codec_manifest,payload_limit=_codec_policy_manifest(encoded)
            with self.codec.open_verified(p,codec_manifest,temp_root=self.temp_root,
                    joblib_compressor_source_path=self.compressor,
                    max_payload_bytes=payload_limit) as logical:
                logical.seek(0); h=hashlib.sha256();crc=n=0
                while True:
                    b=logical.read(1<<20)
                    if not b: break
                    h.update(b);n+=len(b);crc=zipfile.crc32(b,crc)
                if (h.hexdigest(),n,crc&0xffffffff)!=(row["logical_sha256"],row["logical_bytes"],row["logical_crc32"]):
                    raise ExtractedColdError("decoded logical payload identity mismatch")
                after=p.stat()
                if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                    raise ExtractedColdError("physical payload changed during decode")
                logical.seek(0)
                self._check_projection_unchanged()
                yield logical
                self._check_projection_unchanged()
        except self.codec.CodecError as e:
            raise ExtractedColdError("encoded payload verification failed: "+str(e)) from e

    def load_joblib(self, logical_path, expected_sha256=None):
        import joblib
        with self.open(logical_path,expected_sha256) as f:
            return joblib.load(f)
