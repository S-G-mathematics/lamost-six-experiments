#!/usr/bin/env python3
import datetime, json, os, pathlib, signal, subprocess, sys, time

def proc_info(pid, proc_root=pathlib.Path('/proc')):
    try:
        p=pathlib.Path(proc_root)/str(pid)
        text=(p/'stat').read_text()
        tail=text[text.rfind(')')+2:].split()
        state=tail[0]; ppid=int(tail[1]); pgrp=int(tail[2]); ticks=tail[19]
        status=(p/'status').read_text().splitlines()
        rss_line=next((x for x in status if x.startswith('VmRSS:')),None)
        if rss_line is None:
            if state not in {'Z','X','x'}:
                return None
            rss=0
        else:
            rss=int(rss_line.split()[1])*1024
        return ppid,pgrp,ticks,rss
    except (OSError,ValueError,IndexError):
        return None

def confirm_process_exit(proc, timeout_seconds=0.15):
    try:
        return proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None

def tree_rss(root_pid):
    rows={}
    for entry in pathlib.Path('/proc').iterdir():
        if entry.name.isdigit():
            info=proc_info(int(entry.name))
            if info is not None: rows[int(entry.name)]=info
    members={root_pid}
    for _ in range(20):
        more={pid for pid,row in rows.items() if row[0] in members}
        if more<=members: break
        members|=more
    return sum(rows[pid][3] for pid in members if pid in rows),members,rows

def main():
    if '--' not in sys.argv: raise SystemExit('usage: run_guarded_tests.py --rss-bytes N --wall-seconds N --grace-seconds N -- COMMAND...')
    sep=sys.argv.index('--'); args=sys.argv[1:sep]; command=sys.argv[sep+1:]
    rss_cap=int(args[args.index('--rss-bytes')+1]); wall=float(args[args.index('--wall-seconds')+1]); grace=float(args[args.index('--grace-seconds')+1])
    if not command: raise SystemExit('missing command')
    proc=subprocess.Popen(command,start_new_session=True)
    identity=proc_info(proc.pid)
    if identity is None or identity[1]!=proc.pid: raise SystemExit('launched child identity could not be verified')
    ticks=identity[2]; start=time.monotonic(); peak=0; reason=None; terminated=False
    while proc.poll() is None:
        info=proc_info(proc.pid)
        if info is not None and (info[2]!=ticks or info[1]!=proc.pid):
            reason='child_identity_changed'
            break
        if info is None:
            code=proc.poll()
            if code is not None: break
            reason='child_identity_missing'
            break
        usage,_,_=tree_rss(proc.pid); peak=max(peak,usage)
        if usage>rss_cap: reason='process_tree_rss_cap'; break
        if time.monotonic()-start>wall: reason='wall_timeout'; break
        time.sleep(.1)
    if reason:
        now=proc_info(proc.pid)
        if now is not None and now[2]==ticks and now[1]==proc.pid:
            try: os.killpg(proc.pid,signal.SIGTERM); terminated=True
            except ProcessLookupError: pass
            try: proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                now=proc_info(proc.pid)
                if now is not None and now[2]==ticks and now[1]==proc.pid:
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                proc.wait()
        else:
            confirmed=confirm_process_exit(proc,0.15)
            if confirmed is None:
                reason='child_identity_unverified_live'
            elif reason=='child_identity_missing' and confirmed==0:
                reason=None
    if proc.poll() is None:
        if reason=='child_identity_unverified_live':
            code=-1
        else:
            confirmed=confirm_process_exit(proc,grace)
            if confirmed is None:
                if reason is None: reason='child_identity_unverified_live'
                code=-1
            else:
                code=confirmed
    else:
        code=proc.returncode
    result={'schema':'lamost-bounded-test-run/1','finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':code,'reason':reason,'peak_process_tree_rss_bytes':peak,'rss_cap_bytes':rss_cap,'wall_seconds':round(time.monotonic()-start,3),'graceful_termination_sent':terminated}
    print(json.dumps(result,sort_keys=True))
    return 0 if reason is None and code==0 else 1

if __name__=='__main__': raise SystemExit(main())
