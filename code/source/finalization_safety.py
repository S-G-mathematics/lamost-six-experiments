from __future__ import annotations
import datetime,hashlib,json,os,re,resource,signal,subprocess,time,uuid
from pathlib import Path,PurePosixPath

PORTABLE_SCHEMA="lamost-terminal-portable-tests/1"
LATCH_SCHEMA="lamost-finalization-retry-latch/1"
WALL_LIMIT=60
RSS_LIMIT=1024**3
TERM_GRACE=30
RESOURCE_HOLD_LIMIT=3
FAILURE_LIMIT=2
OVERLAY_SUFFIX=[Path("/home/ubuntu/.local/lib/python3.12/site-packages"),Path("/usr/lib/python3/dist-packages")]
REQUIRED_SOURCES={"runtime_20261025/source/finalize_project.py","runtime_20261025/source/reporting.py","runtime_20261025/source/finalization_safety.py","runtime_20261025/source/final_review.py","runtime_20261025/source/audit_artifacts.py","runtime_20261025/source/calibration_replay.py","runtime_20261025/source/calibration_replay_supervisor.py"}
REQUIRED_TESTS={"runtime_20261025/tests/test_finalization_safety.py","runtime_20261025/tests/test_reporting_environment_policy.py","runtime_20261025/tests/test_calibration_replay.py","runtime_20261025/tests/test_calibration_replay_finalization_gate.py","runtime_20261025/tests/test_calibration_replay_supervisor.py"}

class PortableBundleError(RuntimeError): pass
class PortableTestFailure(RuntimeError):
    def __init__(self,message,resource_kind=None,receipt=None):
        super().__init__(message);self.resource_kind=resource_kind;self.receipt=receipt

def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):h.update(block)
    return h.hexdigest()

def _canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _native_file(root,member):
    p=PurePosixPath(member)
    if p.is_absolute() or "\\" in member or any(x in {"","..","."} for x in p.parts) or not p.parts or p.parts[0]!="runtime_20261025":
        raise PortableBundleError("portable bundle contains an unsafe native path: "+str(member))
    dest=Path(root).joinpath(*p.parts).resolve()
    if Path(root).resolve() not in dest.parents or not dest.is_file() or dest.is_symlink():
        raise PortableBundleError("portable bundle member is missing or escapes root: "+str(member))
    return dest

def portable_bundle_snapshot(root,runtime):
    root=Path(root).resolve();runtime=Path(runtime).resolve();tests=runtime/"tests"
    manifest_path=tests/"PORTABLE_TEST_BUNDLE.json";runner_rel="runtime_20261025/tests/run_portable_tests.sh"
    if not manifest_path.is_file():raise PortableBundleError("current portable test manifest is missing")
    raw=manifest_path.read_bytes()
    try:doc=json.loads(raw)
    except Exception as exc:raise PortableBundleError("portable test manifest is malformed") from exc
    if doc.get("schema")!="archive-native-installed-portable-tests/1" or doc.get("runtime_staging_present") is not False:
        raise PortableBundleError("portable test manifest schema or staging-isolation gate differs")
    if doc.get("runner")!=runner_rel or doc.get("source_directory")!="runtime_20261025/source" or doc.get("test_directory")!="runtime_20261025/tests":
        raise PortableBundleError("portable test bundle native paths differ from the deployed runtime")
    sources=doc.get("sources");test_rows=doc.get("tests")
    if not isinstance(sources,list) or not isinstance(test_rows,list) or not sources or not test_rows:
        raise PortableBundleError("portable test manifest lacks source/test hash inventories")
    source_hashes={}
    for row in sources:
        member=row.get("runtime_member");expected=row.get("source_sha256")
        if not isinstance(member,str) or not isinstance(expected,str) or len(expected)!=64 or member in source_hashes:
            raise PortableBundleError("portable source hash record is malformed or duplicated")
        p=_native_file(root,member);actual=_sha(p)
        if actual!=expected or row.get("bundle_sha256") not in (None,actual):
            raise PortableBundleError("portable source differs from test manifest: "+member)
        source_hashes[member]=actual
    test_hashes={}
    for row in test_rows:
        member=row.get("test_member");expected=row.get("portable_sha256")
        if not isinstance(member,str) or not isinstance(expected,str) or len(expected)!=64 or member in test_hashes:
            raise PortableBundleError("portable test hash record is malformed or duplicated")
        p=_native_file(root,member);actual=_sha(p)
        if actual!=expected:raise PortableBundleError("portable test differs from test manifest: "+member)
        test_hashes[member]=actual
    if not REQUIRED_SOURCES.issubset(source_hashes):raise PortableBundleError("portable bundle omits current finalizer/reporting/calibration gate source coverage")
    if not REQUIRED_TESTS.issubset(test_hashes):raise PortableBundleError("portable bundle omits required finalizer/report-environment/calibration gate fixtures")
    runner=_native_file(root,runner_rel);runner_sha=_sha(runner)
    runner_text=runner.read_text(encoding="utf-8")
    runner_tests=set()
    for line in runner_text.splitlines():
        if "$R/tests/" in line:
            member=line.split("$R/tests/",1)[1].split(chr(34),1)[0].strip()
            if member.endswith(".py"):runner_tests.add(member)
    manifest_tests={PurePosixPath(member).relative_to("runtime_20261025/tests").as_posix() for member in test_hashes}
    if runner_tests!=manifest_tests:raise PortableBundleError("portable runner test list differs from manifest test hashes")
    proof_records=[]
    for row in doc.get("resource_review_proofs",[]):
        src_member=row.get("archive_member");fixture_member=row.get("fixture_member")
        expected=row.get("expected_source_sha256");fixture_expected=row.get("sha256")
        if not all(isinstance(x,str) and len(x)==64 for x in (expected,fixture_expected)):
            raise PortableBundleError("portable resource proof hash is malformed")
        src=_native_file(root,src_member);fixture=_native_file(root,fixture_member)
        source_sha=_sha(src);fixture_sha=_sha(fixture)
        if source_sha!=expected or fixture_sha!=fixture_expected or source_sha!=fixture_sha:
            raise PortableBundleError("portable resource proof differs from exact source/fixture hash: "+str(src_member))
        if int(row.get("bytes",-1))!=src.stat().st_size:raise PortableBundleError("portable resource proof byte count differs: "+str(src_member))
        proof_records.append({"archive_member":src_member,"source_sha256":source_sha,"fixture_member":fixture_member,"fixture_sha256":fixture_sha,"bytes":src.stat().st_size})
    plan=doc.get("test_count_plan")
    if not isinstance(plan,dict) or not plan or any(not isinstance(v,int) or v<0 for v in plan.values()):
        raise PortableBundleError("portable test count plan is malformed")
    expected_count=sum(plan.values())
    if expected_count<1:raise PortableBundleError("portable test plan has no planned tests")
    identity={"manifest_sha256":hashlib.sha256(raw).hexdigest(),"runner_sha256":runner_sha,
        "source_hashes":dict(sorted(source_hashes.items())),"test_hashes":dict(sorted(test_hashes.items())),
        "resource_proofs":sorted(proof_records,key=lambda x:x["archive_member"]),"expected_test_count":expected_count,
        "test_count_plan":plan,"environment_policy_sha256":_sha(runtime/"source/reporting_support_environment_20261026.json")}
    identity["bundle_fingerprint_sha256"]=_canonical_sha(identity)
    return {"manifest_path":str(manifest_path),"runner_path":str(runner),"manifest_sha256":identity["manifest_sha256"],
        "runner_sha256":runner_sha,"source_hashes":identity["source_hashes"],"test_hashes":identity["test_hashes"],
        "resource_proofs":identity["resource_proofs"],"expected_test_count":expected_count,
        "test_count_plan":plan,"environment_policy_sha256":identity["environment_policy_sha256"],
        "bundle_fingerprint_sha256":identity["bundle_fingerprint_sha256"]}

def portable_receipt_matches(receipt,snapshot):
    if not isinstance(receipt,dict) or receipt.get("schema_version")!=PORTABLE_SCHEMA or receipt.get("status")!="passed":return False
    for key in ("bundle_fingerprint_sha256","manifest_sha256","runner_sha256","source_hashes","test_hashes","resource_proofs","environment_policy_sha256","expected_test_count"):
        if receipt.get(key)!=snapshot.get(key):return False
    return receipt.get("exit_code")==0 and receipt.get("passed_test_count")==snapshot.get("expected_test_count")

def _proc(pid):
    base=Path("/proc")/str(int(pid))
    try:
        stat=base.joinpath("stat").read_text();tail=stat[stat.rfind(")")+1:].split()
        status=base.joinpath("status").read_text()
        uid=int(next(x.split()[1] for x in status.splitlines() if x.startswith("Uid:")))
        rss=int(next(x.split()[1] for x in status.splitlines() if x.startswith("VmRSS:")))*1024
        cmd=[x.decode(errors="replace") for x in base.joinpath("cmdline").read_bytes().split(b"\0") if x]
        return {"pid":int(pid),"ppid":int(tail[1]),"pgrp":int(tail[2]),"ticks":int(tail[19]),"uid":uid,"rss":rss,"cmd":cmd}
    except (OSError,StopIteration,ValueError,IndexError):return None

def _tree_rss(root_pid):
    procs={}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            item=_proc(int(entry.name))
            if item:procs[item["pid"]]=item
    if root_pid not in procs:return 0
    ids={root_pid}|{pid for pid,item in procs.items() if item["pgrp"]==root_pid}
    while True:
        more={pid for pid,item in procs.items() if item["ppid"] in ids};updated=ids|more
        if updated==ids:break
        ids=updated
    return sum(procs[pid]["rss"] for pid in ids if pid in procs)

def _owned(p,pid,ticks,uid,runner):
    item=_proc(pid)
    if not item:return False
    command=" ".join(item["cmd"])
    return (item["ticks"]==ticks and item["uid"]==uid and item["pgrp"]==pid and
        (str(runner) in command or "pytest" in command))

def _terminate(p,pid,ticks,uid,runner):
    if not _owned(p,pid,ticks,uid,runner):return False
    try:
        if os.getpgid(pid)!=pid:return False
        os.killpg(pid,signal.SIGTERM)
    except OSError:return False
    deadline=time.monotonic()+TERM_GRACE
    while time.monotonic()<deadline:
        if p.poll() is not None:return True
        if not _owned(p,pid,ticks,uid,runner):return False
        time.sleep(.1)
    if p.poll() is not None:return True
    if not _owned(p,pid,ticks,uid,runner):return False
    try:os.killpg(pid,signal.SIGKILL);return True
    except OSError:return False

def _preexec_limits():
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS,(RSS_LIMIT,RSS_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU,(WALL_LIMIT,WALL_LIMIT))

def portable_pass_receipt_path(runtime,snapshot):
    return Path(runtime)/"reports"/("PORTABLE_TEST_PASS_"+snapshot["bundle_fingerprint_sha256"]+".json")

def run_portable_test_bundle(root,runtime,snapshot=None):
    root=Path(root).resolve();runtime=Path(runtime).resolve()
    snapshot=snapshot or portable_bundle_snapshot(root,runtime)
    reports=runtime/"reports";reports.mkdir(parents=True,exist_ok=True)
    receipt_path=portable_pass_receipt_path(runtime,snapshot)
    if receipt_path.exists():
        old=json.loads(receipt_path.read_text())
        if not portable_receipt_matches(old,snapshot):
            raise PortableBundleError("immutable portable pass receipt is malformed or differs from its content-addressed bundle")
        return {"status":"passed","reused":True,"receipt_path":str(receipt_path),"receipt_sha256":_sha(receipt_path),"receipt":old}
    nonce=uuid.uuid4().hex;ops=runtime/"logs"/"operational";ops.mkdir(parents=True,exist_ok=True)
    run_history=ops/"portable_test_runs";run_history.mkdir(parents=True,exist_ok=True)
    logfile=ops/("terminal_portable_tests_"+nonce+".log")
    venv_python=root/"venv"/"bin"/"python"
    if not venv_python.is_file():raise PortableBundleError("exact project venv interpreter is missing for portable tests")
    env=os.environ.copy();site=root/"venv"/"lib"/"python3.12"/"site-packages"
    env["PYTHONPATH"]=os.pathsep.join([str(site),str(OVERLAY_SUFFIX[0]),str(OVERLAY_SUFFIX[1])])
    env["LAMOST_TEST_PYTHON"]=str(venv_python)
    for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):env[name]="1"
    command=["/bin/bash",snapshot["runner_path"]]
    started=_utc();begin=time.monotonic();peak=0;resource_kind=None;failure=None;exit_code=None
    with logfile.open("wb") as log:
        try:p=subprocess.Popen(command,cwd=runtime/"tests",env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True,preexec_fn=_preexec_limits)
        except Exception as exc:raise PortableTestFailure("portable test runner could not start: "+type(exc).__name__,resource_kind="operational") from exc
        pid=p.pid;first=_proc(pid)
        if first is None:
            p.wait(timeout=5)
            raise PortableTestFailure("portable test process identity could not be recorded",resource_kind="operational")
        ticks=first["ticks"];uid=first["uid"]
        while p.poll() is None:
            item=_proc(pid)
            if not item:
                # Re-poll to distinguish normal completion racing the /proc snapshot.
                if p.poll() is not None:break
                failure="portable test process identity disappeared";resource_kind="operational";break
            if not _owned(p,pid,ticks,uid,snapshot["runner_path"]):
                if p.poll() is not None:break
                failure="portable test process identity changed";resource_kind="operational";break
            rss=_tree_rss(pid);peak=max(peak,rss)
            if rss>RSS_LIMIT:failure="portable test process tree exceeded 1 GiB sampled RSS";resource_kind="memory";break
            if time.monotonic()-begin>WALL_LIMIT:failure="portable test suite exceeded 60 seconds";resource_kind="timeout";break
            time.sleep(.1)
        if failure:
            stopped=_terminate(p,pid,ticks,uid,snapshot["runner_path"])
            if stopped and p.poll() is None:p.wait(timeout=TERM_GRACE+5)
            exit_code=p.poll()
        else:
            exit_code=p.wait()
    duration=max(0.,time.monotonic()-begin)
    try:tail=logfile.read_bytes()[-65536:].decode("utf-8","replace")
    except OSError:tail=""
    matches=list(re.finditer(r"(\d+) passed(?:,|\s|$)",tail))
    passed=int(matches[-1].group(1)) if matches else None
    status="passed" if failure is None and exit_code==0 and passed==snapshot["expected_test_count"] else "failed"
    if status=="failed" and failure is None:failure=f"portable tests returned {exit_code}; expected {snapshot['expected_test_count']} passed, observed {passed}"
    receipt={"schema_version":PORTABLE_SCHEMA,"status":status,"observed_utc":_utc(),"run_nonce":nonce,
        "started_utc":started,"duration_seconds":duration,"exit_code":exit_code,"failure_reason":failure,
        "command":command,"environment_policy_sha256":snapshot["environment_policy_sha256"],
        "resource_limits":{"wall_seconds":WALL_LIMIT,"address_space_bytes_per_process":RSS_LIMIT,"process_tree_sampled_rss_bytes":RSS_LIMIT,"sample_interval_seconds":.1,"termination_grace_seconds":TERM_GRACE,"nice":10,"native_threads":1},
        "measurement_method":"process-tree /proc VmRSS sampled every 100ms; short spikes between samples may be missed",
        "peak_process_tree_rss_bytes":peak,"runner_sha256":snapshot["runner_sha256"],"manifest_sha256":snapshot["manifest_sha256"],
        "source_hashes":snapshot["source_hashes"],"test_hashes":snapshot["test_hashes"],"resource_proofs":snapshot["resource_proofs"],
        "bundle_fingerprint_sha256":snapshot["bundle_fingerprint_sha256"],"expected_test_count":snapshot["expected_test_count"],
        "passed_test_count":passed,"test_count_plan":snapshot["test_count_plan"],"log_sha256":_sha(logfile)}
    attempt_path=run_history/(nonce+".json");atomic_json(attempt_path,receipt)
    if status!="passed":
        kind=resource_kind or ("operational" if failure and ("identity" in failure or "start" in failure) else "deterministic")
        raise PortableTestFailure(failure or "portable test suite failed",resource_kind=kind,receipt=receipt)
    public_receipt={k:receipt[k] for k in ("schema_version","status","observed_utc","started_utc","duration_seconds","exit_code",
        "environment_policy_sha256","resource_limits","measurement_method","peak_process_tree_rss_bytes","runner_sha256","manifest_sha256",
        "source_hashes","test_hashes","resource_proofs","bundle_fingerprint_sha256","expected_test_count","passed_test_count","test_count_plan")}
    if receipt_path.exists():raise PortableBundleError("refuse to overwrite an immutable portable pass receipt")
    atomic_json(receipt_path,public_receipt)
    return {"status":"passed","reused":False,"receipt_path":str(receipt_path),"receipt_sha256":_sha(receipt_path),"receipt":public_receipt}

def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+".tmp."+uuid.uuid4().hex)
    with tmp.open("w",encoding="utf-8") as f:json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def _load_latch(runtime):
    path=Path(runtime)/"logs"/"operational"/"finalization_retry_latch.json"
    if path.is_file():
        doc=json.loads(path.read_text())
        if doc.get("schema_version")!=LATCH_SCHEMA:raise RuntimeError("finalization retry latch schema mismatch")
        return path,doc
    return path,{"schema_version":LATCH_SCHEMA,"generation":0,"clear_events":[],"attempts":[]}

def finalization_fingerprint(root,runtime,bundle_snapshot):
    root=Path(root).resolve();runtime=Path(runtime).resolve()
    members=[runtime/"source/finalize_project.py",runtime/"source/finalization_safety.py",runtime/"source/reporting.py",
        runtime/"manifests/freeze.json",runtime/"manifests/tasks.json",runtime/"registry.json",
        root/"project/benchmark/results/master_run_config.json",root/"project/benchmark/dependencies.freeze.txt",
        runtime/"source/reporting_support_environment_20261026.json"]
    hashes={}
    for path in members:
        if not path.is_file() or path.is_symlink():raise RuntimeError("finalization fingerprint input missing/unsafe: "+str(path))
        hashes[path.relative_to(root).as_posix()]=_sha(path)
    payload={"schema_version":"lamost-finalization-failure-fingerprint/1","inputs":hashes,"portable_bundle_fingerprint_sha256":bundle_snapshot["bundle_fingerprint_sha256"]}
    return _canonical_sha(payload),payload

def _attempts_for(doc,fingerprint,generation):
    return [x for x in doc["attempts"] if x.get("fingerprint_sha256")==fingerprint and x.get("generation")==generation]

def begin_finalization_attempt(runtime,fingerprint,payload):
    path,doc=_load_latch(runtime);generation=int(doc.get("generation",0));rows=_attempts_for(doc,fingerprint,generation)
    failures=sum(x.get("status")=="failed" for x in rows);holds=sum(x.get("status")=="operational_backoff" for x in rows)
    if failures>=FAILURE_LIMIT:return {"status":"FINALIZATION_REVIEW_REQUIRED","reason":"two attempts failed under unchanged code/config/terminal-registry fingerprint","failure_count":failures,"fingerprint_sha256":fingerprint}
    if holds>=RESOURCE_HOLD_LIMIT:return {"status":"FINALIZATION_REVIEW_REQUIRED","reason":"operational resource/backoff limit reached; no scientific failure was recorded","operational_hold_count":holds,"fingerprint_sha256":fingerprint}
    running=[x for x in rows if x.get("status")=="running"]
    if running:
        for row in running:
            row.update({"status":"operational_backoff","finished_utc":_utc(),"reason":"prior finalizer attempt ended without a completion receipt","resource_kind":"interrupted","next_retry_epoch":time.time()+900})
            _write_attempt_receipt(Path(runtime),row)
        atomic_json(path,doc)
        return {"status":"finalization_resource_backoff","reason":"interrupted finalizer attempt preserved; retry after 15-minute operational backoff","fingerprint_sha256":fingerprint}
    latest=max((x for x in rows if x.get("status")=="operational_backoff"),key=lambda x:x.get("finished_utc",""),default=None)
    if latest and float(latest.get("next_retry_epoch",0))>time.time():
        return {"status":"finalization_resource_backoff","reason":"operational resource backoff is active","next_retry_epoch":latest["next_retry_epoch"],"fingerprint_sha256":fingerprint}
    attempt={"attempt_id":uuid.uuid4().hex,"fingerprint_sha256":fingerprint,"fingerprint_inputs":payload,
        "generation":generation,"started_utc":_utc(),"status":"running"}
    doc["attempts"].append(attempt);atomic_json(path,doc)
    return {"status":"started","attempt_id":attempt["attempt_id"],"fingerprint_sha256":fingerprint,"attempt_number":failures+1}

def finish_finalization_attempt(runtime,attempt_id,status,reason=None,resource_kind=None,extra=None):
    path,doc=_load_latch(runtime)
    for attempt in reversed(doc["attempts"]):
        if attempt.get("attempt_id")==attempt_id:
            attempt["finished_utc"]=_utc();attempt["status"]=status
            if reason:attempt["reason"]=str(reason)[:2000]
            if resource_kind:attempt["resource_kind"]=resource_kind
            if status=="operational_backoff":attempt["next_retry_epoch"]=time.time()+900
            if extra:attempt["result"]=extra
            atomic_json(path,doc)
            _write_attempt_receipt(Path(runtime),attempt)
            rows=_attempts_for(doc,attempt["fingerprint_sha256"],attempt["generation"])
            failures=sum(x.get("status")=="failed" for x in rows);holds=sum(x.get("status")=="operational_backoff" for x in rows)
            if failures>=FAILURE_LIMIT:return {"status":"FINALIZATION_REVIEW_REQUIRED","failure_count":failures,"fingerprint_sha256":attempt["fingerprint_sha256"]}
            if holds>=RESOURCE_HOLD_LIMIT:return {"status":"FINALIZATION_REVIEW_REQUIRED","operational_hold_count":holds,"fingerprint_sha256":attempt["fingerprint_sha256"]}
            if status=="operational_backoff":return {"status":"finalization_resource_backoff","next_retry_epoch":attempt["next_retry_epoch"],"fingerprint_sha256":attempt["fingerprint_sha256"]}
            return {"status":status,"fingerprint_sha256":attempt["fingerprint_sha256"]}
    raise RuntimeError("finalization attempt ID is absent from retry latch")

def _write_attempt_receipt(runtime,attempt):
    base=runtime/"logs"/"operational"/"finalization_attempt_history"/attempt["fingerprint_sha256"]
    base.mkdir(parents=True,exist_ok=True);path=base/(attempt["attempt_id"]+".json")
    if not path.exists():atomic_json(path,attempt)

def clear_finalization_latch(runtime,reason):
    reason=str(reason or "").strip()
    if len(reason)<20:raise ValueError("manual latch clear requires a reason of at least 20 characters")
    path,doc=_load_latch(runtime);doc["generation"]=int(doc.get("generation",0))+1
    event={"generation":doc["generation"],"cleared_utc":_utc(),"reason":reason[:2000],"attempt_history_preserved":True}
    doc["clear_events"].append(event);atomic_json(path,doc)
    return {"status":"finalization_latch_cleared","generation":doc["generation"],"attempt_history_preserved":True}

def is_resource_backoff(exc):
    if isinstance(exc,PortableTestFailure):return exc.resource_kind in {"memory","timeout","operational"}
    if isinstance(exc,MemoryError):return True
    name=type(exc).__name__.lower();msg=str(exc).lower()
    return name in {"insufficientspace","timeoutexpired"} or any(x in msg for x in ("no space left","insufficient space","out of memory","memory limit","process tree exceeded 1 gib","exceeded 60 seconds"))
