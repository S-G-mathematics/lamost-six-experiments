"""Resumable byte-range download of public DR10 v2 FITS academic mirror."""
from pathlib import Path
import urllib.request, concurrent.futures as cf, os, time, json, hashlib
ROOT=Path(__file__).resolve().parents[1]
URL='https://users.flatironinstitute.org/~apricewhelan/data/surveys/LAMOST/dr10_v2.0_LRS_catalogue.fits'
DEST=ROOT/'raw/dr10_v2.0_LRS_catalogue.fits'
CHUNK=8*1024*1024

def main():
    DEST.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(URL,method='HEAD')
    with urllib.request.urlopen(req,timeout=60) as r:
        size=int(r.headers['Content-Length']); headers=dict(r.headers)
    assert size==3455202240, (size, 'unexpected source size')
    progress=DEST.with_suffix('.chunks.json')
    done=set(json.loads(progress.read_text()) if progress.exists() else [])
    fd=os.open(DEST,os.O_CREAT|os.O_RDWR,0o600);os.ftruncate(fd,size)
    t=time.time();initial=len(done); total=(size+CHUNK-1)//CHUNK
    def fetch(i):
        start=i*CHUNK; end=min(start+CHUNK,size)-1
        for retry in range(6):
            try:
                rq=urllib.request.Request(URL,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
                with urllib.request.urlopen(rq,timeout=120) as r:
                    if r.status!=206:raise RuntimeError(f'Range ignored: {r.status}')
                    cr=r.headers.get('Content-Range','')
                    if cr!=f'bytes {start}-{end}/{size}':raise RuntimeError(f'Bad range: {cr}')
                    data=r.read()
                if len(data)!=end-start+1:raise RuntimeError('Incomplete range')
                os.pwrite(fd,data,start);return i
            except Exception:
                if retry==5:raise
                time.sleep(min(2**retry,16))
    print(f'Downloading {size:,} bytes in {total} chunks; {len(done)} resumed',flush=True)
    last=0
    with cf.ThreadPoolExecutor(max_workers=40) as ex:
        futures=[ex.submit(fetch,i) for i in range(total) if i not in done]
        for f in cf.as_completed(futures):
            done.add(f.result())
            if time.time()-last>15 or len(done)==total:
                progress.write_text(json.dumps(sorted(done)))
                elapsed=time.time()-t; transferred=(len(done)-initial)*CHUNK
                print(f'{len(done)}/{total} chunks, {100*len(done)/total:.1f}%, {transferred/max(elapsed,1)/1e6:.2f} MB/s, {elapsed:.0f}s',flush=True)
                last=time.time()
    os.fsync(fd);os.close(fd)
    h=hashlib.sha256()
    with DEST.open('rb') as f:
        for b in iter(lambda:f.read(16*1024*1024),b''):h.update(b)
    prov={'url':URL,'source_role':'public academic mirror; semantically checked against official catalog, not bytewise authenticated','size_bytes':size,'sha256':h.hexdigest(),'headers':headers,'downloaded_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT/'audit/source_provenance.json').write_text(json.dumps(prov,indent=2))
    print('Complete SHA256',h.hexdigest(),flush=True)
if __name__=='__main__':main()
