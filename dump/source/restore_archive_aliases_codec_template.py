"""Opt-in alias restorer template for extracted codec-aware full archives.

Legacy raw aliases retain the old hardlink/copy behavior. Encoded model members are
not eagerly expanded; callers request one logical path at a time with materialize().
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parent/"runtime_20261025"/"source"))

def safe(root,name):
    if not isinstance(name,str) or not name or "\\" in name: raise ValueError("unsafe path")
    rel=PurePosixPath(name)
    if rel.is_absolute() or any(x in ("",".","..") for x in rel.parts): raise ValueError("unsafe path")
    root=Path(root).resolve(strict=True); p=root.joinpath(*rel.parts)
    if root not in p.resolve(strict=False).parents: raise ValueError("path escapes extraction root")
    cur=p.parent
    while cur!=root:
        if cur.is_symlink(): raise ValueError("path crosses symlink")
        cur=cur.parent
    return p

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def _hardlink_or_copy(src,dst,size,digest):
    if dst.exists() or dst.is_symlink():
        if dst.is_file() and not dst.is_symlink() and dst.stat().st_size==size and sha(dst)==digest:return "already_present"
        raise FileExistsError("refusing to overwrite a different alias")
    dst.parent.mkdir(parents=True,exist_ok=True)
    try: os.link(src,dst,follow_symlinks=False); mode="hardlinked"
    except OSError:
        fd,tmp=tempfile.mkstemp(prefix=".restore_alias_",dir=dst.parent)
        try:
            with os.fdopen(fd,"wb") as out,open(src,"rb") as inp: shutil.copyfileobj(inp,out,1<<20);out.flush();os.fsync(out.fileno())
            if Path(tmp).stat().st_size!=size or sha(tmp)!=digest: raise ValueError("alias copy failed verification")
            if dst.exists(): raise FileExistsError("destination appeared before publish")
            os.link(tmp,dst,follow_symlinks=False);mode="copied"
        finally:
            try:os.unlink(tmp)
            except FileNotFoundError:pass
    if dst.stat().st_size!=size or sha(dst)!=digest: raise ValueError("published alias failed verification")
    return mode

def restore(root, logical_path=None, joblib_compressor_source_path=None):
    root=Path(root).resolve(strict=True)
    mm=json.loads((root/"archive_member_manifest.json").read_text())
    aliases=json.loads((root/"archive_aliases.json").read_text()).get("aliases",[])
    members={r["path"]:r for r in mm.get("unique_physical_members",[])}
    encoded={p:r for p,r in members.items() if r.get("storage_encoding")}
    if logical_path is None:
        # Preserve legacy behavior without expanding encoded members into raw copies.
        todo=[a for a in aliases if a.get("canonical_path") not in encoded]
        results=[{"alias":a["alias_path"],"status":_hardlink_or_copy(
            safe(root,a["canonical_path"]),safe(root,a["alias_path"]),int(a["bytes"]),a["sha256"])} for a in todo]
        return {"restored_aliases":len(results),"skipped_encoded_aliases":len(aliases)-len(todo),
                "next_step":"pass --materialize <logical path> to restore one encoded model and its aliases"}
    if not joblib_compressor_source_path: raise ValueError("pinned joblib compressor source path is required")
    selected=safe(root,logical_path);member_name=PurePosixPath(logical_path).as_posix()
    row=members.get(member_name)
    if row is None:
        match=next((a for a in aliases if a["alias_path"]==member_name),None)
        if not match: raise FileNotFoundError(member_name)
        member_name=match["canonical_path"];selected=safe(root,member_name);row=members.get(member_name)
    if row is None or not row.get("storage_encoding"): raise ValueError("selected path is not a codec-encoded model member")
    source=safe(root,member_name)
    from cold_finalizer_codec_contract import materialize_encoded_alias
    logical_row={"sha256":row["logical_sha256"],"bytes":int(row["logical_bytes"]),
                 "crc32":int(row["storage_encoding"]["original_crc32"]),
                 "storage_encoding":row["storage_encoding"]}
    temp_root=root/".codec_restore_tmp";temp_root.mkdir(exist_ok=True)
    materialize_encoded_alias(source,source,logical_row,output_root=root,temp_root=temp_root,
        joblib_compressor_source_path=joblib_compressor_source_path)
    restored=[]
    for alias in aliases:
        if alias.get("canonical_path")!=member_name: continue
        dst=safe(root,alias["alias_path"])
        mode=_hardlink_or_copy(source,dst,int(logical_row["bytes"]),logical_row["sha256"])
        restored.append({"alias":alias["alias_path"],"status":mode})
    try:temp_root.rmdir()
    except OSError:pass
    return {"canonical_path":member_name,"logical_sha256":logical_row["sha256"],
            "logical_bytes":logical_row["bytes"],"restored_aliases":len(restored),"aliases":restored}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".");ap.add_argument("--materialize")
    ap.add_argument("--joblib-compressor-source",default=None);a=ap.parse_args()
    if a.joblib_compressor_source is None:
        try:
            import joblib.compressor
            import inspect
            a.joblib_compressor_source=inspect.getsourcefile(joblib.compressor.BinaryZlibFile)
        except Exception: pass
    print(json.dumps(restore(a.root,a.materialize,a.joblib_compressor_source),indent=2))
if __name__=="__main__": main()
