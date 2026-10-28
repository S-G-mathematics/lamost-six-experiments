"""Manifest and archive the stable baseline deliverables (exclude raw/workfiles)."""
from pathlib import Path
import hashlib,json,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
def include(p):
    rel=p.relative_to(ROOT)
    if '__pycache__' in rel.parts or rel.parts[0].startswith('.'):return False
    if rel.parts[0]=='raw':return rel.as_posix()=='raw/query_speed_preview.csv'
    if rel.parts[0]=='data':return p.suffix in ('.parquet','.joblib')
    if rel.parts[0]=='audit':return len(rel.parts)==2 and p.suffix in ('.json','.csv','.parquet','.txt','.log')
    if rel.parts[0] in ('docs','src'):return p.suffix in ('.txt','.py')
    return rel.as_posix() in ('README.txt','requirements.txt','manifest.json')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and include(p))
    stable=[p for p in files if p.relative_to(ROOT).as_posix() not in ('manifest.json','audit/independent_validation.json')]
    manifest={'algorithm':'sha256','baseline_version':1,'files':{p.relative_to(ROOT).as_posix():{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in stable},'exclusions':'Manifest does not hash itself or the timestamped independent validation report.'}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    subprocess.run([sys.executable,str(ROOT/'src/verify_baseline.py')],check=True)
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and include(p))
    dest=ROOT.parent/'LAMOST_Clean_Baseline.zip'
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for p in files:z.write(p,'lamost_baseline/'+p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(dest) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('Archive failed CRC: '+bad)
    print(json.dumps({'archive':str(dest),'files':len(files),'bytes':dest.stat().st_size,'sha256':sha(dest)},indent=2))
if __name__=='__main__':main()
