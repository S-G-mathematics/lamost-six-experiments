from __future__ import annotations
import hashlib, json, os, signal, tempfile, time, uuid
from pathlib import Path
import multiprocessing as mp

def _proc_identity(pid):
    base=Path('/proc')/str(int(pid))
    raw=(base/'stat').read_text(); tail=raw[raw.rfind(')')+2:].split()
    status=(base/'status').read_text().splitlines()
    uid=int(next(x.split()[1] for x in status if x.startswith('Uid:')))
    return {'pid':int(pid),'ppid':int(tail[1]),'pgid':int(tail[2]),'start_ticks':int(tail[19]),'uid':uid}

def _atomic_json(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
        dfd=os.open(p.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def _append_event(path,row):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf-8') as f:
        f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())

def _hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def _child_entry(conn,target,args,identity):
    try:
        os.setpgid(0,0)
        actual=_proc_identity(os.getpid())
        conn.send({'event':'ready',**actual,'phase_id':identity['phase_id'],'task_key':identity['task_key'],'attempt_id':identity['attempt_id'],'stage':identity['stage']})
        ack=conn.recv()
        if not isinstance(ack,dict) or ack.get('event')!='start' or ack.get('phase_id')!=identity['phase_id']: return
        target(conn,*args)
    except BaseException as exc:
        try: conn.send({'status':'error','error':f'{type(exc).__name__}: {exc}'})
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass

def _tree_rss_kib(root_pid):
    rows={}
    for d in Path('/proc').iterdir():
        if not d.name.isdigit(): continue
        try:
            lines=(d/'status').read_text().splitlines()
            ppid=int(next(x.split()[1] for x in lines if x.startswith('PPid:')))
            rss=int(next(x.split()[1] for x in lines if x.startswith('VmRSS:')))
            rows[int(d.name)]=(ppid,rss)
        except Exception: pass
    tree={int(root_pid)}; changed=True
    while changed:
        changed=False
        for child,(parent,_) in rows.items():
            if parent in tree and child not in tree: tree.add(child); changed=True
    return sum(rows[x][1] for x in tree if x in rows)

def _group_pids(pgid):
    found=[]
    for d in Path('/proc').iterdir():
        if not d.name.isdigit(): continue
        try:
            raw=(d/'stat').read_text(); tail=raw[raw.rfind(')')+2:].split()
            if int(tail[2])==int(pgid): found.append(int(d.name))
        except Exception: pass
    return found

def _terminate_group(proc,identity,grace):
    pid=identity.get('pid'); pgid=identity.get('pgid'); ticks=identity.get('start_ticks')
    try: current=_proc_identity(pid)
    except Exception: current=None
    if current and current['start_ticks']==ticks and current['uid']==identity['uid'] and current['pgid']==pgid and pgid==pid:
        os.killpg(pgid,signal.SIGTERM)
        deadline=time.monotonic()+float(grace)
        while time.monotonic()<deadline and _group_pids(pgid): time.sleep(.1)
        if _group_pids(pgid): os.killpg(pgid,signal.SIGKILL)
    else:
        try:
            current=_proc_identity(proc.pid)
            if current['start_ticks']==identity.get('launch_start_ticks') and current['uid']==identity.get('uid') and current['ppid']==os.getpid():
                proc.terminate(); proc.join(float(grace))
                if proc.is_alive(): proc.kill()
        except Exception: pass
    proc.join(float(grace))
    if proc.is_alive(): proc.kill(); proc.join()

def run_phase(*, target, args, state_path, event_path, task_key, attempt_id, stage, request_path, request_sha256, worker_script_sha256,
              timeout_seconds=600, rss_limit_kib=10*1024*1024, grace_seconds=30,
              output_path=None):
    if not isinstance(attempt_id,str) or not attempt_id or Path(attempt_id).name!=attempt_id or attempt_id in {'.','..'}:
        raise ValueError('E6-v2 phase requires a safe controller attempt_id')
    if not isinstance(request_path,str) or not request_path or not all(isinstance(x,str) and len(x)==64 for x in (request_sha256,worker_script_sha256)):
        raise ValueError('E6-v2 phase requires request path and SHA-256 identities')
    try: bytes.fromhex(request_sha256); bytes.fromhex(worker_script_sha256)
    except ValueError as exc: raise ValueError('E6-v2 phase request identities must be hexadecimal SHA-256') from exc
    phase_id=uuid.uuid4().hex
    identity={'phase_id':phase_id,'task_key':str(task_key),'attempt_id':attempt_id,'stage':str(stage)}
    ctx=mp.get_context('fork'); parent,child=ctx.Pipe(duplex=True)
    proc=ctx.Process(target=_child_entry,args=(child,target,args,identity),name='lamost-e6-posterior-'+str(stage))
    t0=time.monotonic(); start_utc=time.time()
    proc.start(); child.close()
    try: launch=_proc_identity(proc.pid)
    except Exception as exc:
        parent.close()
        raise RuntimeError(f'E6 phase child identity unavailable before ready: {exc}') from exc
    if launch['ppid']!=os.getpid() or launch['uid']!=os.getuid():
        parent.close(); _terminate_group(proc,{'pid':proc.pid,'launch_start_ticks':launch['start_ticks'],'uid':launch['uid']},grace_seconds)
        raise RuntimeError('E6 phase child launch identity mismatch')
    parent_ident=_proc_identity(os.getpid())
    state={'schema_version':'lamost-e6-phase-process/1','role':'e6_prediction_phase','status':'starting',**identity,
           'request_path':str(request_path),'request_sha256':request_sha256,'worker_script_sha256':worker_script_sha256,
           'parent_pid':os.getpid(),'parent_start_ticks':parent_ident['start_ticks'],
           'child_pid':proc.pid,'child_start_ticks':launch['start_ticks'],'child_uid':launch['uid'],
           'child_pgid':None,'started_epoch':start_utc,'timeout_seconds':int(timeout_seconds),
           'rss_limit_kib':int(rss_limit_kib),'termination_grace_seconds':int(grace_seconds)}
    _atomic_json(state_path,state); _append_event(event_path,{**state,'event':'starting'})
    ready=None
    while time.monotonic()-t0<float(timeout_seconds):
        if parent.poll(.1):
            msg=parent.recv()
            if isinstance(msg,dict) and msg.get('event')=='ready': ready=msg
            break
        if not proc.is_alive(): break
    if ready is None:
        _terminate_group(proc,{'pid':proc.pid,'launch_start_ticks':launch['start_ticks'],'uid':launch['uid']},grace_seconds)
        state.update(status='operationally_interrupted',reason='phase child failed ready handshake',finished_epoch=time.time())
        _atomic_json(state_path,state); _append_event(event_path,{**state,'event':'finished'}); parent.close()
        raise RuntimeError('E6 phase child failed ready handshake before scientific work')
    observed=_proc_identity(proc.pid)
    valid=(ready.get('pid')==proc.pid and ready.get('start_ticks')==launch['start_ticks']==observed['start_ticks']
           and ready.get('uid')==os.getuid()==observed['uid'] and ready.get('pgid')==proc.pid==observed['pgid']
           and observed['ppid']==os.getpid() and ready.get('phase_id')==phase_id
           and ready.get('task_key')==str(task_key) and ready.get('attempt_id')==attempt_id and ready.get('stage')==str(stage))
    if not valid:
        _terminate_group(proc,{'pid':proc.pid,'pgid':observed['pgid'],'start_ticks':observed['start_ticks'],'launch_start_ticks':launch['start_ticks'],'uid':observed['uid']},grace_seconds)
        state.update(status='operationally_invalid',reason='phase child ready identity did not verify',finished_epoch=time.time())
        _atomic_json(state_path,state); _append_event(event_path,{**state,'event':'finished'}); parent.close()
        raise RuntimeError('E6 phase child ready identity mismatch')
    state.update(status='running',child_pgid=ready['pgid'],ready_epoch=time.time(),ready_monotonic=time.monotonic())
    _atomic_json(state_path,state); _append_event(event_path,{**state,'event':'running'})
    parent.send({'event':'start','phase_id':phase_id})
    peak=0; reason=None
    while proc.is_alive():
        peak=max(peak,_tree_rss_kib(os.getpid()))
        if peak>int(rss_limit_kib): reason='rss_limit'; break
        if time.monotonic()-t0>float(timeout_seconds): reason='timeout'; break
        proc.join(.2)
    if reason: _terminate_group(proc,{'pid':proc.pid,'pgid':ready['pgid'],'start_ticks':launch['start_ticks'],'uid':ready['uid']},grace_seconds)
    else: proc.join()
    try: msg=parent.recv() if parent.poll() else {'status':'error','error':f'phase child exited {proc.exitcode} without a result'}
    except EOFError: msg={'status':'error','error':f'phase child exited {proc.exitcode} without a result'}
    parent.close()
    elapsed=time.monotonic()-t0
    status='successful' if reason is None and proc.exitcode==0 and msg.get('status')=='success' else ('scientific_failure' if reason in {'timeout','rss_limit'} else 'operationally_invalid')
    result={**state,'status':status,'finished_epoch':time.time(),'seconds':elapsed,'peak_tree_rss_kib':int(peak),
            'reason':reason,'exit_code':proc.exitcode,'result':msg}
    if output_path and status=='successful':
        result['output_path']=str(output_path); result['output_sha256']=_hash(output_path)
    _atomic_json(state_path,result); _append_event(event_path,{**result,'event':'finished'})
    return result
