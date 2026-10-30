"""Staged per-entry reversible codec adapter; no archive transaction orchestration.

Legacy rows without storage_encoding are read as raw ZIP_STORED artifacts.
Encoded rows keep the original artifact identity at top level and put physical
payload identity plus a pinned reversible codec recipe in storage_encoding.
The caller owns the cold-store reader/writer lease and transaction journal.
"""
from __future__ import annotations
import contextlib, hashlib, json, os, pathlib, tempfile, zipfile
from contextlib import contextmanager
from pathlib import PurePosixPath
import reversible_joblib_codec as codec

class StorageFormatError(ValueError):
    pass

LEGACY_STORAGE_CODEC_POLICY = "reversible-xz-v1"
PAYLOAD12_STORAGE_CODEC_POLICY = "reversible-xz-v1-payload12"
LEGACY_MAX_PAYLOAD_BYTES = 2 << 30
PAYLOAD12_MAX_PAYLOAD_BYTES = 12 << 30

def codec_payload_limit(policy=None, descriptor_cap=None):
    """Resolve a persisted per-entry raw-payload limit without widening legacy rows.

    Descriptors predating policy tags remain bound to the 2-GiB v1 limit.
    New tagged descriptors must carry the exact cap assigned to their policy.
    """
    if policy is None:
        if descriptor_cap is not None:
            raise StorageFormatError("payload cap is present without a storage codec policy")
        return LEGACY_MAX_PAYLOAD_BYTES
    limits = {
        LEGACY_STORAGE_CODEC_POLICY: LEGACY_MAX_PAYLOAD_BYTES,
        PAYLOAD12_STORAGE_CODEC_POLICY: PAYLOAD12_MAX_PAYLOAD_BYTES,
    }
    if policy not in limits:
        raise StorageFormatError("unknown storage codec policy")
    expected = limits[policy]
    if descriptor_cap is not None and (type(descriptor_cap) is not int or descriptor_cap != expected):
        raise StorageFormatError("persisted payload cap does not match storage codec policy")
    return expected

def _resolve_requested_payload_limit(policy, requested):
    cap = codec_payload_limit(policy)
    if requested is None:
        return cap
    if type(requested) is not int or requested <= 0 or requested > cap:
        raise StorageFormatError("requested payload cap exceeds or mismatches storage codec policy")
    if policy is not None and requested != cap:
        raise StorageFormatError("tagged storage policy requires its exact payload cap")
    return requested

def _sha_stream(f, chunk=1 << 20):
    h=hashlib.sha256(); n=0; crc=0
    while True:
        b=f.read(chunk)
        if not b: break
        h.update(b); n+=len(b); crc=zipfile.crc32(b,crc)
    return h.hexdigest(),n,crc & 0xffffffff

def _safe_rel(value):
    if not isinstance(value,str) or not value or "\\" in value:
        raise StorageFormatError("invalid relative path")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ("",".","..") for x in p.parts):
        raise StorageFormatError("unsafe relative path")
    return p.as_posix()

def _dir(path):
    p=pathlib.Path(path)
    if p.is_symlink() or not p.is_dir():
        raise StorageFormatError("temporary root must be an existing regular directory")
    return p.resolve(strict=True)

def _crc_file(path):
    c=0; n=0
    with open(path,"rb") as f:
        while True:
            b=f.read(1 << 20)
            if not b: break
            c=zipfile.crc32(b,c);n+=len(b)
    return c & 0xffffffff,n

def encode_entry_payload(source_path, *, archive_member, temp_root,
                         joblib_compressor_source_path,
                         storage_codec_policy=None,
                         max_payload_bytes=None,
                         max_file_bytes=codec.DEFAULT_MAX_FILE_BYTES,
                         chunk_bytes=codec.DEFAULT_CHUNK_BYTES,
                         max_encoded_temp_bytes=None):
    """Return (encoded temporary path, additive identity fields).

    The caller appends payload_path as ZIP_STORED within its existing journaled
    transaction. This function never changes or removes source_path.
    """
    member=_safe_rel(archive_member); root=_dir(temp_root)
    payload_limit=_resolve_requested_payload_limit(storage_codec_policy,max_payload_bytes)
    payload=root/("candidate-"+os.urandom(12).hex()+".xz")
    m=codec.encode_file(source_path,payload,output_root=root,
        joblib_compressor_source_path=joblib_compressor_source_path,
        max_payload_bytes=payload_limit,max_file_bytes=max_file_bytes,
        chunk_bytes=chunk_bytes,max_encoded_temp_bytes=max_encoded_temp_bytes)
    logical_crc,logical_n=_crc_file(source_path)
    payload_crc,payload_n=_crc_file(payload)
    if logical_n!=m["original_size_bytes"] or payload_n!=m["encoded_size_bytes"]:
        payload.unlink(missing_ok=True)
        raise StorageFormatError("writer byte counts disagree with codec manifest")
    descriptor=dict(m)
    descriptor.update({"original_crc32":logical_crc,"encoded_crc32":payload_crc})
    if storage_codec_policy is not None:
        descriptor.update({"storage_codec_policy":storage_codec_policy,
                           "max_payload_bytes":payload_limit})
    fields={"archive_member":member,"sha256":m["original_sha256"],
            "bytes":m["original_size_bytes"],"crc32":logical_crc,
            "storage_encoding":descriptor}
    return payload,fields

def _codec_manifest(row):
    d=row.get("storage_encoding")
    if not isinstance(d,dict):
        return None
    expected={"codec_version","format","original_sha256","original_size_bytes",
      "original_zlib_header_hex","raw_payload_sha256","raw_payload_size_bytes",
      "encoded_sha256","encoded_size_bytes","encoded_xz_header_hex",
      "zlib_compile_version","zlib_runtime_version","zlib_params",
      "joblib_compressor_source_sha256","lzma_format","lzma_preset",
      "original_crc32","encoded_crc32"}
    tagged=expected|{"storage_codec_policy","max_payload_bytes"}
    if set(d) not in (expected,tagged):
        raise StorageFormatError("codec descriptor fields differ from the supported contract")
    policy=d.get("storage_codec_policy")
    cap=d.get("max_payload_bytes")
    if policy is None and ({"storage_codec_policy","max_payload_bytes"} & set(d)):
        raise StorageFormatError("incomplete storage codec policy descriptor")
    if policy == PAYLOAD12_STORAGE_CODEC_POLICY and cap is None:
        raise StorageFormatError("payload12 descriptor is missing its persisted payload cap")
    codec_payload_limit(policy,cap)
    if d.get("codec_version")!=codec.CODEC_VERSION:
        raise codec.UnsupportedCodec("unknown storage codec")
    if (d.get("original_sha256")!=row.get("sha256") or
        d.get("original_size_bytes")!=row.get("bytes") or
        d.get("original_crc32")!=row.get("crc32")):
        raise StorageFormatError("logical artifact identity disagrees with codec descriptor")
    out={k:v for k,v in d.items() if k not in {"original_crc32","encoded_crc32","storage_codec_policy","max_payload_bytes"}}
    return out

def _archive_stamp(path):
    p=pathlib.Path(path)
    if p.is_symlink() or not p.is_file():
        raise StorageFormatError("archive must be a regular non-symlink file")
    s=p.stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def _verify_zip_record(info, row):
    if info.compress_type!=zipfile.ZIP_STORED:
        raise StorageFormatError("cold model ZIP members must be ZIP_STORED")
    if "storage_encoding" not in row:
        if info.file_size!=int(row["bytes"]) or info.CRC!=int(row["crc32"]):
            raise StorageFormatError("legacy raw ZIP record differs from logical identity")
        if info.header_offset!=int(row["header_offset"]):
            raise StorageFormatError("legacy raw header offset mismatch")
        return
    d=row["storage_encoding"]
    if (info.file_size!=int(d["encoded_size_bytes"]) or
        info.CRC!=int(d["encoded_crc32"]) or
        info.header_offset!=int(row["header_offset"])):
        raise StorageFormatError("encoded ZIP record differs from physical identity")

def append_encoded_payload(zip_writer, payload_path, row, *, chunk_bytes=1 << 20):
    """Append a preverified codec payload through an existing ZIP writer.

    Caller must already hold its exclusive lease, have a durable transaction
    journal, and be prepared to roll back the archive if this raises. The
    returned header offset is finalized after the ZipInfo write closes.
    """
    member=_safe_rel(row.get("archive_member"))
    if "storage_encoding" not in row:
        raise StorageFormatError("codec writer requires a versioned storage_encoding descriptor")
    _codec_manifest(row)
    d=row["storage_encoding"];p=pathlib.Path(payload_path)
    if p.is_symlink() or not p.is_file():
        raise StorageFormatError("payload must be a regular non-symlink file")
    before=p.stat();pre=_crc_file(p);pre_sha=codec.sha_file(p,chunk_bytes)
    if pre!=(int(d["encoded_crc32"]),int(d["encoded_size_bytes"])) or pre_sha!=d["encoded_sha256"]:
        raise StorageFormatError("candidate payload differs from declared physical identity")
    info=zipfile.ZipInfo(member);info.compress_type=zipfile.ZIP_STORED
    info.external_attr=(0o100444 & 0xffff) << 16
    h=hashlib.sha256();n=0;crc=0
    with p.open("rb") as src,zip_writer.open(info,"w",force_zip64=True) as dst:
        while True:
            b=src.read(chunk_bytes)
            if not b:break
            dst.write(b);h.update(b);n+=len(b);crc=zipfile.crc32(b,crc)
    after=p.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise StorageFormatError("payload changed during ZIP append")
    if (h.hexdigest(),n,crc & 0xffffffff)!=(d["encoded_sha256"],int(d["encoded_size_bytes"]),int(d["encoded_crc32"])):
        raise StorageFormatError("payload bytes changed during ZIP append")
    return {"archive_member":member,"header_offset":int(info.header_offset),
            "payload_sha256":h.hexdigest(),"payload_size":n,"payload_crc32":crc & 0xffffffff}

@contextmanager
def open_logical_member(archive_path, row, *, temp_root,
                        joblib_compressor_source_path,
                        max_payload_bytes=None,
                        max_file_bytes=codec.DEFAULT_MAX_FILE_BYTES,
                        chunk_bytes=codec.DEFAULT_CHUNK_BYTES):
    """Yield exact logical artifact bytes from either legacy raw or encoded row.

    Caller must hold its store's shared reader lease until the context exits.
    The source ZIP is checked for identity changes during validation. Encoded
    payload and reconstructed logical output are bounded by the codec limits.
    """
    archive=pathlib.Path(archive_path); root=_dir(temp_root)
    member=_safe_rel(row.get("archive_member")); before=_archive_stamp(archive)
    with zipfile.ZipFile(archive,"r",allowZip64=True) as z:
        try: info=z.getinfo(member)
        except KeyError as e: raise FileNotFoundError(member) from e
        _verify_zip_record(info,row)
        if "storage_encoding" not in row:
            with z.open(info,"r") as f:
                h,n,crc=_sha_stream(f,chunk_bytes)
            if (h,n,crc)!=(row.get("sha256"),int(row["bytes"]),int(row["crc32"])):
                raise StorageFormatError("legacy raw payload SHA/size/CRC mismatch")
            if _archive_stamp(archive)!=before:
                raise StorageFormatError("archive changed during raw member validation")
            with z.open(info,"r") as f:
                yield f
            if _archive_stamp(archive)!=before:
                raise StorageFormatError("archive changed while raw member was open")
            return
        manifest=_codec_manifest(row)
        desc=row["storage_encoding"]
        payload_limit=codec_payload_limit(desc.get("storage_codec_policy"),
                                          desc.get("max_payload_bytes"))
        if max_payload_bytes is not None:
            if type(max_payload_bytes) is not int or max_payload_bytes <= 0 or max_payload_bytes > payload_limit:
                raise StorageFormatError("reader payload cap exceeds persisted descriptor limit")
            payload_limit=max_payload_bytes
        if int(desc["encoded_size_bytes"])>max_file_bytes:
            raise StorageFormatError("encoded payload exceeds configured limit")
        with tempfile.TemporaryDirectory(prefix="cold-codec-member-",dir=root) as td:
            payload=pathlib.Path(td)/"payload.xz"
            h=hashlib.sha256(); n=0; crc=0
            with z.open(info,"r") as inp, payload.open("xb") as out:
                while True:
                    b=inp.read(chunk_bytes)
                    if not b: break
                    n+=len(b)
                    if n>max_file_bytes: raise StorageFormatError("encoded payload exceeds configured limit")
                    h.update(b);crc=zipfile.crc32(b,crc);out.write(b)
                out.flush();os.fsync(out.fileno())
            if (h.hexdigest()!=desc["encoded_sha256"] or n!=desc["encoded_size_bytes"] or
                (crc&0xffffffff)!=desc["encoded_crc32"]):
                raise StorageFormatError("encoded payload SHA/size/CRC mismatch")
            if _archive_stamp(archive)!=before:
                raise StorageFormatError("archive changed during encoded-member staging")
            with codec.open_verified(payload,manifest,temp_root=td,
                joblib_compressor_source_path=joblib_compressor_source_path,
                max_payload_bytes=payload_limit,max_file_bytes=max_file_bytes,
                chunk_bytes=chunk_bytes) as logical:
                logical.seek(0); lh=hashlib.sha256(); ln=0; lc=0
                while True:
                    b=logical.read(chunk_bytes)
                    if not b: break
                    lh.update(b);ln+=len(b);lc=zipfile.crc32(b,lc)
                if (lh.hexdigest()!=row["sha256"] or ln!=int(row["bytes"]) or
                    (lc&0xffffffff)!=int(row["crc32"])):
                    raise StorageFormatError("decoded logical SHA/size/CRC mismatch")
                if _archive_stamp(archive)!=before:
                    raise StorageFormatError("archive changed during logical verification")
                logical.seek(0)
                yield logical
            if _archive_stamp(archive)!=before:
                raise StorageFormatError("archive changed while logical member was open")

def logical_stat(row, *, member_info=None):
    """Stable logical-facing stat plus explicit physical-member identity."""
    result={"sha256":row["sha256"],"size":int(row["bytes"]),
            "logical_crc32":int(row["crc32"]),
            "archive_member":_safe_rel(row["archive_member"])}
    d=row.get("storage_encoding")
    if d is None:
        result.update({"storage_format":"raw-v1","payload_sha256":row["sha256"],
            "payload_size":int(row["bytes"]),"payload_crc32":int(row["crc32"])})
    else:
        _codec_manifest(row)
        result.update({"storage_format":d["codec_version"],
            "payload_sha256":d["encoded_sha256"],
            "payload_size":int(d["encoded_size_bytes"]),
            "payload_crc32":int(d["encoded_crc32"]),
            "recipe_sha256":hashlib.sha256(json.dumps(
                {k:v for k,v in d.items() if k not in {"encoded_sha256","encoded_size_bytes","encoded_crc32"}},
                sort_keys=True,separators=(",",":")).encode()).hexdigest()})
    if member_info is not None:
        result["header_offset"]=int(member_info.header_offset)
        if member_info.file_size!=result["payload_size"] or member_info.CRC!=result["payload_crc32"]:
            raise StorageFormatError("ZIP member differs from physical stat")
    return result

