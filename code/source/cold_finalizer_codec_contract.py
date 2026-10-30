"""Staged finalizer helpers for per-member logical/physical codec identity.

This module is isolated staging. It does not append archives or touch live source.
"""
from __future__ import annotations
import hashlib, os, pathlib, tempfile, zipfile, uuid
from reversible_joblib_codec import open_verified, sha_file
from cold_codec_storage import logical_stat, StorageFormatError, codec_payload_limit, _codec_manifest

class FinalizerCodecError(ValueError): pass

def stat_projection(row, stat):
    """Stable review projection: legacy keys mean physical member; logical fields explicit."""
    desc=row.get("storage_encoding")
    logical_sha=stat.get("sha256")
    logical_size=int(stat.get("size",-1))
    payload_sha=stat.get("payload_sha256",logical_sha)
    payload_size=int(stat.get("payload_size",logical_size))
    payload_crc=int(stat.get("payload_crc32",stat.get("crc32",-1)))
    if logical_sha!=row.get("sha256") or logical_size!=int(row.get("bytes",-2)):
        raise FinalizerCodecError("logical stat disagrees with cold row")
    if desc:
        if (payload_sha!=desc.get("encoded_sha256") or payload_size!=int(desc.get("encoded_size_bytes",-1))
            or payload_crc!=int(desc.get("encoded_crc32",-1))
            or stat.get("storage_format")!=desc.get("codec_version")):
            raise FinalizerCodecError("physical stat disagrees with encoded descriptor")
    elif (payload_sha!=logical_sha or payload_size!=logical_size
          or payload_crc!=int(row.get("crc32",-1))):
        raise FinalizerCodecError("legacy raw physical identity differs from logical identity")
    return {"logical_sha256":logical_sha,"logical_bytes":logical_size,
            "logical_crc32":int(stat.get("logical_crc32",row.get("crc32",-1))),
            "member_sha256":payload_sha,"member_bytes":payload_size,
            "member_crc32":payload_crc,"storage_format":stat.get("storage_format","raw-v1"),
            "storage_encoding":desc,"archive_member":stat.get("archive_member",row.get("archive_member")),
            "header_offset":int(stat.get("header_offset",row.get("header_offset",-1)))}

def inventory_member(info, row, physical_sha256):
    """Validate one archive record and return distinct logical/physical manifest fields."""
    desc=row.get("storage_encoding")
    if desc:
        physical=(int(info.file_size),physical_sha256,int(info.CRC),int(info.header_offset))
        expected=(int(desc["encoded_size_bytes"]),desc["encoded_sha256"],
                  int(desc["encoded_crc32"]),int(row["header_offset"]))
        if physical!=expected: raise FinalizerCodecError("encoded ZIP record differs from descriptor")
        return {"path":info.filename,"bytes":physical[0],"sha256":physical[1],
            "physical_crc32":physical[2],"logical_bytes":int(row["bytes"]),
            "logical_sha256":row["sha256"],"category":"retained_cold_model",
            "storage_encoding":desc}
    physical=(int(info.file_size),physical_sha256,int(info.CRC),int(info.header_offset))
    expected=(int(row["bytes"]),row["sha256"],int(row["crc32"]),int(row["header_offset"]))
    if physical!=expected: raise FinalizerCodecError("legacy raw ZIP record differs from row")
    return {"path":info.filename,"bytes":physical[0],"sha256":physical[1],
        "physical_crc32":physical[2],"logical_bytes":physical[0],
        "logical_sha256":physical[1],"category":"retained_cold_model"}

def _safe_dest(root, dest):
    root=pathlib.Path(root).resolve(strict=True)
    raw=pathlib.Path(dest)
    target=raw if raw.is_absolute() else root/raw
    target=pathlib.Path(os.path.abspath(target))
    try: target.relative_to(root)
    except ValueError as e: raise FinalizerCodecError("destination escapes extraction root") from e
    if target == root: raise FinalizerCodecError("destination must be a file")
    cur=target.parent
    while cur!=root:
        if cur.is_symlink(): raise FinalizerCodecError("destination parent is a symlink")
        cur=cur.parent
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.parent.resolve()!=target.parent: raise FinalizerCodecError("destination parent changed")
    return root,target

def materialize_encoded_alias(encoded_path, destination, row, *, output_root, temp_root,
                              joblib_compressor_source_path, max_file_bytes=4<<30,
                              max_payload_bytes=None, chunk_bytes=1<<20):
    """Decode and verify before atomic publish. Never overwrites a different file."""
    desc=row.get("storage_encoding")
    if not isinstance(desc,dict): raise FinalizerCodecError("encoded descriptor required")
    try:
        manifest=_codec_manifest(row)
        payload_limit=codec_payload_limit(desc.get("storage_codec_policy"),
                                          desc.get("max_payload_bytes"))
        if max_payload_bytes is not None:
            if type(max_payload_bytes) is not int or max_payload_bytes <= 0 or max_payload_bytes > payload_limit:
                raise StorageFormatError("materializer cap exceeds persisted descriptor limit")
            payload_limit=max_payload_bytes
    except Exception as exc:
        raise FinalizerCodecError("encoded descriptor has an invalid storage policy/cap") from exc
    root,target=_safe_dest(output_root,destination)
    src=pathlib.Path(encoded_path)
    if src.is_symlink() or not src.is_file(): raise FinalizerCodecError("encoded source is not a regular file")
    try: src.resolve(strict=True).relative_to(root)
    except ValueError as e: raise FinalizerCodecError("encoded source escapes extraction root") from e
    tmp_root=pathlib.Path(temp_root).resolve(strict=True)
    try: tmp_root.relative_to(root)
    except ValueError as e: raise FinalizerCodecError("temporary root escapes extraction root") from e
    encoded_before=src.stat();backup=None
    # If already materialized, accept only the exact logical artifact.
    in_place=False
    if target.exists() or target.is_symlink():
        if target.is_file() and not target.is_symlink() and target.stat().st_size==int(row["bytes"]) and sha_file(target)==row["sha256"]:
            return {"status":"already_present","path":str(target)}
        try: same_path=src.resolve(strict=True)==target.resolve(strict=True)
        except OSError: same_path=False
        if same_path and target.is_file() and not target.is_symlink() and sha_file(target)==desc.get("encoded_sha256"):
            in_place=True
        else: raise FileExistsError("refusing to overwrite a different alias")
    codec_manifest=manifest
    fd,tmp_name=tempfile.mkstemp(prefix=".codec_alias_",dir=target.parent)
    tmp=pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd,"wb") as dst, open_verified(src,codec_manifest,temp_root=temp_root,
             joblib_compressor_source_path=joblib_compressor_source_path,
             max_file_bytes=max_file_bytes,max_payload_bytes=payload_limit,chunk_bytes=chunk_bytes) as logical:
            h=hashlib.sha256();n=0;crc=0
            while True:
                block=logical.read(chunk_bytes)
                if not block: break
                dst.write(block);h.update(block);n+=len(block);crc=zipfile.crc32(block,crc)
            dst.flush();os.fsync(dst.fileno())
        after=src.stat()
        if (encoded_before.st_dev,encoded_before.st_ino,encoded_before.st_size,encoded_before.st_mtime_ns,encoded_before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise FinalizerCodecError("encoded source changed during alias materialization")
        if (h.hexdigest(),n,crc&0xffffffff)!=(row["sha256"],int(row["bytes"]),int(row["crc32"])):
            raise FinalizerCodecError("materialized logical bytes do not match row identity")
        if in_place:
            current=target.stat()
            if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)!=(encoded_before.st_dev,encoded_before.st_ino,encoded_before.st_size,encoded_before.st_mtime_ns,encoded_before.st_ctime_ns):
                raise FinalizerCodecError("encoded destination changed before replacement")
            backup=target.with_name(".codec_backup_"+uuid.uuid4().hex)
            os.link(target,backup,follow_symlinks=False)
            os.replace(tmp,target)
        else:
            if target.exists() or target.is_symlink(): raise FileExistsError("destination appeared before publish")
            os.link(tmp,target,follow_symlinks=False)
        if (target.stat().st_size,sha_file(target))!=(int(row["bytes"]),row["sha256"]):
            if backup is not None and backup.exists():
                os.replace(backup,target);backup=None
            elif target.exists() and os.path.samefile(tmp,target): target.unlink()
            raise FinalizerCodecError("published alias failed final verification")
        if backup is not None:
            backup.unlink();backup=None
        dfd=os.open(target.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
        return {"status":"materialized","path":str(target),"bytes":n,"sha256":h.hexdigest()}
    finally:
        if backup is not None and backup.exists():
            try:
                if target.exists() and not os.path.samefile(backup,target): os.replace(backup,target)
                else: backup.unlink()
            except FileNotFoundError: pass
        try: tmp.unlink()
        except FileNotFoundError: pass
