"""Fail-closed XZ wrapper for one pinned zlib-compressed joblib byte stream.

No model is deserialized. The reader reconstructs the original compressed bytes,
checks all hashes/sizes, and yields only a verified read-only temporary file.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import lzma
import os
import pathlib
import tempfile
import zlib

CODEC_VERSION = "lamost-reversible-joblib-xz/1"
SUPPORTED_ZLIB_COMPILE_VERSION = "1.3"
SUPPORTED_ZLIB_RUNTIME_VERSION = "1.3"
SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256 = "1830d526678e06a7ed73ab4c903ba9af2a231e193f8c857c5ab3683224f14dd4"
ZLIB_HEADER = b"\x78\x5e"
XZ_MAGIC = b"\xfd7zXZ\x00"
DEFAULT_CHUNK_BYTES = 1 << 20
DEFAULT_MAX_PAYLOAD_BYTES = 2 << 30
DEFAULT_MAX_FILE_BYTES = 4 << 30
ZLIB_PARAMS = {"level": 3, "method": zlib.DEFLATED, "wbits": zlib.MAX_WBITS,
               "memlevel": zlib.DEF_MEM_LEVEL, "strategy": 0}

class CodecError(ValueError):
    """Malformed input or metadata, integrity mismatch, or unsafe path."""
class UnsupportedCodec(CodecError):
    """Runtime or stream falls outside the pinned codec contract."""
class CodecLimitError(CodecError):
    """Fixed storage-stream bound reached; original source remains untouched."""
class AggregateTempBudgetExceeded(CodecError):
    """Transaction-wide encoded temporary budget reached; never raw-fallback."""

def sha_file(path, chunk_bytes=DEFAULT_CHUNK_BYTES):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk_bytes), b""):
            h.update(block)
    return h.hexdigest()

def _int(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise CodecError(name + " is outside the permitted integer range")
    return value

def _versions():
    if zlib.ZLIB_VERSION != SUPPORTED_ZLIB_COMPILE_VERSION:
        raise UnsupportedCodec("unsupported zlib compile version")
    if zlib.ZLIB_RUNTIME_VERSION != SUPPORTED_ZLIB_RUNTIME_VERSION:
        raise UnsupportedCodec("unsupported zlib runtime version")

def _source_sha(path, expected=None):
    p = pathlib.Path(path)
    if p.is_symlink() or not p.is_file():
        raise CodecError("compressor source must be a regular non-symlink file")
    got = sha_file(p)
    if got != SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256:
        raise UnsupportedCodec("joblib BinaryZlibFile source differs from supported pin")
    if expected is not None and got != expected:
        raise UnsupportedCodec("joblib compressor source changed since encoding")
    return got

def _root(root):
    p = pathlib.Path(root)
    if p.is_symlink() or not p.is_dir():
        raise CodecError("output root must be an existing non-symlink directory")
    return p.resolve(strict=True)

def _new_output(root, path):
    root = _root(root)
    raw = pathlib.Path(path)
    if ".." in raw.parts:
        raise CodecError("parent traversal is forbidden")
    target = raw if raw.is_absolute() else root / raw
    target = pathlib.Path(os.path.abspath(target))
    try:
        target.relative_to(root)
        target.parent.resolve(strict=True).relative_to(root)
    except (ValueError, OSError) as e:
        raise CodecError("output path or parent escapes root or is missing") from e
    cur = target.parent
    while cur != root:
        if cur.is_symlink():
            raise CodecError("symlink output parent is forbidden")
        cur = cur.parent
    if target.exists() or target.is_symlink():
        raise FileExistsError(str(target))
    return target

def _input(path):
    p = pathlib.Path(path)
    if p.is_symlink() or not p.is_file():
        raise CodecError("input must be a regular non-symlink file")
    return p.resolve(strict=True)

def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _tmp(parent, prefix):
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=parent)
    return os.fdopen(fd, "wb"), pathlib.Path(name)

def _hash_update(h, f, data):
    f.write(data)
    h.update(data)

def encode_file(source_path, encoded_path, *, output_root, joblib_compressor_source_path,
                max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,
                max_file_bytes=DEFAULT_MAX_FILE_BYTES, chunk_bytes=DEFAULT_CHUNK_BYTES,
                max_encoded_temp_bytes=None):
    """Encode one pinned zlib joblib stream into XZ. Never replaces/deletes source/output."""
    _versions()
    _int(max_payload_bytes, "max_payload_bytes", 1)
    _int(max_file_bytes, "max_file_bytes", 1)
    if max_encoded_temp_bytes is not None: _int(max_encoded_temp_bytes, "max_encoded_temp_bytes", 1, max_file_bytes)
    _int(chunk_bytes, "chunk_bytes", 1, 8 << 20)
    src = _input(source_path)
    dst = _new_output(output_root, encoded_path)
    if src == dst:
        raise CodecError("source and destination must differ")
    source_sha = _source_sha(joblib_compressor_source_path)
    before = src.stat()
    if before.st_size > max_file_bytes:
        raise CodecLimitError("source file exceeds configured maximum")
    with src.open("rb") as f:
        zhead = f.read(2)
    if zhead != ZLIB_HEADER:
        raise UnsupportedCodec("unsupported zlib header/level")
    dec = zlib.decompressobj(zlib.MAX_WBITS)
    enc = lzma.LZMACompressor(format=lzma.FORMAT_XZ, preset=3)
    hsrc, hraw, henc = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    nsrc = nraw = nenc = 0
    out, tmp = _tmp(dst.parent, ".codec-xz-")
    try:
        with src.open("rb") as f:
            while True:
                block = f.read(chunk_bytes)
                if not block:
                    break
                hsrc.update(block); nsrc += len(block)
                if nsrc > max_file_bytes:
                    raise CodecLimitError("source exceeds configured maximum")
                pending = block
                while pending:
                    raw = dec.decompress(pending, chunk_bytes)
                    pending = dec.unconsumed_tail
                    if dec.unused_data:
                        raise CodecError("trailing bytes after zlib stream")
                    if raw:
                        nraw += len(raw)
                        if nraw > max_payload_bytes:
                            raise CodecLimitError("raw payload exceeds configured maximum")
                        hraw.update(raw)
                        part = enc.compress(raw)
                        if part:
                            if max_encoded_temp_bytes is not None and nenc + len(part) > max_encoded_temp_bytes:
                                raise AggregateTempBudgetExceeded("transaction encoded temporary budget exceeded")
                            if nenc + len(part) > max_file_bytes:
                                raise CodecLimitError("encoded output exceeds configured maximum size")
                            _hash_update(henc, out, part); nenc += len(part)
            tail = dec.flush()
            if tail:
                nraw += len(tail)
                if nraw > max_payload_bytes:
                    raise CodecLimitError("raw payload exceeds configured maximum")
                hraw.update(tail)
                part = enc.compress(tail)
                if part:
                    if max_encoded_temp_bytes is not None and nenc + len(part) > max_encoded_temp_bytes:
                        raise AggregateTempBudgetExceeded("transaction encoded temporary budget exceeded")
                    if nenc + len(part) > max_file_bytes:
                        raise CodecLimitError("encoded output exceeds configured maximum size")
                    _hash_update(henc, out, part); nenc += len(part)
            part = enc.flush()
            if part:
                if max_encoded_temp_bytes is not None and nenc + len(part) > max_encoded_temp_bytes:
                    raise AggregateTempBudgetExceeded("transaction encoded temporary budget exceeded")
                if nenc + len(part) > max_file_bytes:
                    raise CodecLimitError("encoded output exceeds configured maximum size")
                _hash_update(henc, out, part); nenc += len(part)
            out.flush(); os.fsync(out.fileno())
        if not dec.eof or dec.unused_data:
            raise CodecError("truncated or trailing zlib stream")
        after = src.stat()
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (
            after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise CodecError("source changed during encoding")
        if nenc > max_file_bytes or tmp.stat().st_size != nenc:
            raise CodecError("encoded output exceeds bound or byte count differs")
        with tmp.open("rb") as f:
            if f.read(len(XZ_MAGIC)) != XZ_MAGIC:
                raise CodecError("generated XZ header mismatch")
        out.close()
        os.link(tmp, dst, follow_symlinks=False)
        _fsync_dir(dst.parent)
    except (zlib.error, lzma.LZMAError) as e:
        raise CodecError("invalid compression stream") from e
    finally:
        if not out.closed:
            out.close()
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return {
        "codec_version": CODEC_VERSION,
        "format": "xz-preset-3-of-raw-zlib-joblib-payload",
        "original_sha256": hsrc.hexdigest(), "original_size_bytes": nsrc,
        "original_zlib_header_hex": zhead.hex(),
        "raw_payload_sha256": hraw.hexdigest(), "raw_payload_size_bytes": nraw,
        "encoded_sha256": henc.hexdigest(), "encoded_size_bytes": nenc,
        "encoded_xz_header_hex": XZ_MAGIC.hex(),
        "zlib_compile_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        "zlib_params": dict(ZLIB_PARAMS),
        "joblib_compressor_source_sha256": source_sha,
        "lzma_format": "FORMAT_XZ", "lzma_preset": 3,
    }

def write_manifest_json(manifest_path, manifest, *, output_root):
    """Write a new manifest sidecar atomically; refuses all existing paths."""
    target = _new_output(output_root, manifest_path)
    data = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    f, tmp = _tmp(target.parent, ".codec-manifest-")
    try:
        with f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.link(tmp, target, follow_symlinks=False); _fsync_dir(target.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return target

def _manifest(m, source_path, max_payload, max_file):
    if not isinstance(m, dict) or m.get("codec_version") != CODEC_VERSION:
        raise UnsupportedCodec("unknown codec version")
    _versions()
    if m.get("zlib_compile_version") != zlib.ZLIB_VERSION or m.get("zlib_runtime_version") != zlib.ZLIB_RUNTIME_VERSION:
        raise UnsupportedCodec("zlib version mismatch")
    params = m.get("zlib_params")
    if (not isinstance(params, dict) or set(params) != set(ZLIB_PARAMS)
        or any(type(params[k]) is not int or params[k] != ZLIB_PARAMS[k] for k in ZLIB_PARAMS)):
        raise UnsupportedCodec("unsupported zlib parameters or level")
    for key in ("original_sha256","raw_payload_sha256","encoded_sha256","joblib_compressor_source_sha256"):
        val=m.get(key)
        if not isinstance(val,str) or len(val)!=64 or any(c not in "0123456789abcdef" for c in val):
            raise CodecError("invalid hash field " + key)
    if m.get("original_zlib_header_hex") != ZLIB_HEADER.hex():
        raise UnsupportedCodec("unsupported zlib header")
    if m.get("encoded_xz_header_hex") != XZ_MAGIC.hex() or m.get("lzma_format")!="FORMAT_XZ" or m.get("lzma_preset")!=3:
        raise UnsupportedCodec("unsupported XZ settings")
    osize=_int(m.get("original_size_bytes"),"original_size_bytes",1,max_file)
    rsize=_int(m.get("raw_payload_size_bytes"),"raw_payload_size_bytes",1,max_payload)
    esize=_int(m.get("encoded_size_bytes"),"encoded_size_bytes",1,max_file)
    _source_sha(source_path,m["joblib_compressor_source_sha256"])
    return osize,rsize,esize

@contextlib.contextmanager
def open_verified(encoded_path, manifest, *, temp_root, joblib_compressor_source_path,
                  max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,
                  max_file_bytes=DEFAULT_MAX_FILE_BYTES, chunk_bytes=DEFAULT_CHUNK_BYTES):
    """Reconstruct to a confined temp file; yield read-only only after exact verification."""
    _int(max_payload_bytes,"max_payload_bytes",1)
    _int(max_file_bytes,"max_file_bytes",1)
    _int(chunk_bytes,"chunk_bytes",1,8 << 20)
    osize,rsize,esize=_manifest(manifest,joblib_compressor_source_path,max_payload_bytes,max_file_bytes)
    encoded=_input(encoded_path)
    if encoded.stat().st_size!=esize:
        raise CodecError("encoded size differs from manifest")
    root=_root(temp_root)
    out,tmp=_tmp(root,".codec-original-")
    eh,rh,oh=hashlib.sha256(),hashlib.sha256(),hashlib.sha256()
    ne=nr=no=0
    dec=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=128*1024*1024)
    comp=zlib.compressobj(3,zlib.DEFLATED,zlib.MAX_WBITS,zlib.DEF_MEM_LEVEL,0)
    try:
        with encoded.open("rb") as f:
            if f.read(len(XZ_MAGIC))!=XZ_MAGIC:
                raise CodecError("invalid XZ header")
            f.seek(0)
            while True:
                block=f.read(chunk_bytes)
                if not block:
                    break
                if dec.eof:
                    raise CodecError("trailing bytes after XZ stream")
                eh.update(block);ne+=len(block)
                pending=block
                while True:
                    try:
                        raw=dec.decompress(pending,max_length=chunk_bytes)
                    except lzma.LZMAError as e:
                        raise CodecError("invalid XZ stream") from e
                    pending=b""
                    if raw:
                        nr+=len(raw)
                        if nr>max_payload_bytes:
                            raise CodecLimitError("raw payload exceeds configured maximum")
                        rh.update(raw)
                        part=comp.compress(raw)
                        if part:
                            if no + len(part) > max_file_bytes:
                                raise CodecError("reconstructed file exceeds configured maximum")
                            _hash_update(oh,out,part);no+=len(part)
                    if dec.unused_data:
                        raise CodecError("trailing bytes after XZ stream")
                    if dec.eof or dec.needs_input:
                        break
            if not dec.eof:
                raise CodecError("truncated XZ stream")
            if ne!=esize or eh.hexdigest()!=manifest["encoded_sha256"]:
                raise CodecError("encoded SHA-256/size mismatch")
            if nr!=rsize or rh.hexdigest()!=manifest["raw_payload_sha256"]:
                raise CodecError("raw payload SHA-256/size mismatch")
            part=comp.flush()
            if part:
                if no + len(part) > max_file_bytes:
                    raise CodecError("reconstructed file exceeds configured maximum")
                _hash_update(oh,out,part);no+=len(part)
            out.flush();os.fsync(out.fileno())
        if no!=osize or oh.hexdigest()!=manifest["original_sha256"]:
            raise CodecError("reconstructed original SHA-256/size mismatch")
        with tmp.open("rb") as check:
            if check.read(2)!=ZLIB_HEADER:
                raise CodecError("reconstructed zlib header mismatch")
        out.close();_fsync_dir(root)
        verified=open(tmp,"rb")
        try:
            yield verified
        finally:
            verified.close()
    finally:
        if not out.closed:
            out.close()
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
