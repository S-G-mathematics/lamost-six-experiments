#!/usr/bin/env python3
"""Quiescence-only maintenance patch for science.py.

Default is dry-run. Use --self-test to patch a temporary copy and compile it.
Only after the controller confirms no E3+ worker can import/run science.py, use --apply.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
TARGET = HERE / "science.py"

OLD_ATOMIC = '''def _atomic_copy(src,dst,prefer_link=False):
    src=Path(src); dst=Path(dst); dst.parent.mkdir(parents=True,exist_ok=True)
    temp=dst.with_name(dst.name+".tmp")
    try:
        if prefer_link: os.link(src,temp)
        else: raise OSError("copy requested")
    except OSError: shutil.copy2(src,temp)
    os.replace(temp,dst)
'''
NEW_ATOMIC = '''def _atomic_copy(src,dst,prefer_link=True):
    src=Path(src); dst=Path(dst); dst.parent.mkdir(parents=True,exist_ok=True)
    # Unique per-attempt temporary avoids collisions with stale/interrupted copies.
    temp=dst.with_name(dst.name+"."+uuid.uuid4().hex+".tmp")
    try:
        if prefer_link: os.link(src,temp)
        else: raise OSError("copy requested")
    except OSError: shutil.copy2(src,temp)
    os.replace(temp,dst)
'''
OLD_STUDY = '''                study=optuna.create_study(study_name=study_name,storage=storage,load_if_exists=True,direction="maximize",sampler=optuna.samplers.TPESampler(seed=int(task.get("optimizer_seed",task.get("seed",0))),n_startup_trials=3))
'''
NEW_STUDY = '''                import joblib
                sampler_file=checkpoints/"optuna_sampler.joblib"
                if sampler_file.exists():
                    sampler=joblib.load(sampler_file)
                else:
                    sampler=optuna.samplers.TPESampler(seed=int(task.get("optimizer_seed",task.get("seed",0))),n_startup_trials=3)
                study=optuna.create_study(study_name=study_name,storage=storage,load_if_exists=True,direction="maximize",sampler=sampler)
'''
OLD_SUGGEST = '''                        pp=mod.suggest_parameters(t,method,len(y),int(np.bincount(y,minlength=7).min()))
'''
NEW_SUGGEST = '''                        pp=mod.suggest_parameters(t,method,len(y),int(np.bincount(y,minlength=7).min()))
                        # Persist the advanced sampler RNG immediately after this trial's proposal.
                        _persist_sampler(sampler_file,study.sampler)
'''
OLD_DUP_TELL = '''                            study.tell(t,score)
'''
NEW_DUP_TELL = '''                            study.tell(t,score)
                            _persist_sampler(sampler_file,study.sampler)
'''
OLD_FIT_TELL = '''                            study.tell(t,float(r["score"]))
'''
NEW_FIT_TELL = '''                            study.tell(t,float(r["score"]))
                            _persist_sampler(sampler_file,study.sampler)
'''
OLD_FAIL_TELL = '''                        try: study.tell(t,state=optuna.trial.TrialState.FAIL)
'''
NEW_FAIL_TELL = '''                        try:
                            study.tell(t,state=optuna.trial.TrialState.FAIL)
                            _persist_sampler(sampler_file,study.sampler)
'''
OLD_UNIFORM_FALLBACK = '''                try: stored=np.bincount(np.asarray(_cache_roles(runtime,task.get("rep",0))["y_fit"],int),minlength=7)
                except Exception: stored=np.ones(7,dtype=int)
            counts=_alloc(stored,n)
'''
NEW_UNIFORM_FALLBACK = '''                try:
                    stored=np.bincount(np.asarray(_cache_roles(runtime,task.get("rep",0))["y_fit"],int),minlength=7)
                except FileNotFoundError as e:
                    return {"status":"unavailable_dependency","reason":f"generation needs class counts from matching fit roles: {e}"}
                if stored.sum()<=0:
                    return {"status":"unavailable_dependency","reason":"matching fit-role class counts are empty"}
            counts=_alloc(stored,n)
'''
OLD_GENERATE_STATUS = '''            if res.get("status")=="unsupported": return _finish(out,attempt,record,"unsupported",res.get("reason"),res)
'''
NEW_GENERATE_STATUS = '''            if res.get("status")!="success":
                state=res.get("status","operationally_invalid")
                return _finish(out,attempt,record,state,res.get("reason","generation phase did not produce a valid artifact"),res)
'''

def _persist_sampler(path, sampler):
    import joblib
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    try:
        joblib.dump(sampler,temp,compress=3)
        os.replace(temp,path)
    finally:
        try: temp.unlink()
        except FileNotFoundError: pass

def apply_to_text(text: str) -> str:
    # Ordered exact replacements fail closed if source changed or patch was already applied.
    pairs=[
        (OLD_ATOMIC,NEW_ATOMIC,1,"atomic copy"),
        (OLD_STUDY,NEW_STUDY,1,"sampler restore"),
        (OLD_SUGGEST,NEW_SUGGEST,1,"sampler proposal checkpoint"),
        (OLD_DUP_TELL,NEW_DUP_TELL,1,"sampler duplicate checkpoint"),
        (OLD_FIT_TELL,NEW_FIT_TELL,1,"sampler fit checkpoint"),
        (OLD_FAIL_TELL,NEW_FAIL_TELL,1,"sampler failure checkpoint"),
        (OLD_UNIFORM_FALLBACK,NEW_UNIFORM_FALLBACK,1,"class-count fallback"),
        (OLD_GENERATE_STATUS,NEW_GENERATE_STATUS,1,"generation outcome propagation"),
    ]
    for old,new,expected,label in pairs:
        count=text.count(old)
        if count!=expected:
            raise RuntimeError(f"{label}: expected {expected} source match(es), found {count}")
        text=text.replace(old,new)
    helper='''def _persist_sampler(path,sampler):
    import joblib
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    try:
        joblib.dump(sampler,temp,compress=3); os.replace(temp,path)
    finally:
        try: temp.unlink()
        except FileNotFoundError: pass

'''
    marker="def _json(path,obj):"
    if text.count(marker)!=1: raise RuntimeError("cannot locate JSON helper insertion point")
    text=text.replace(marker,helper+marker)
    return text

def _apply(source: Path, destination: Path):
    updated=apply_to_text(source.read_text())
    compile(updated,str(destination),"exec")
    destination.write_text(updated)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true",help="modify science.py; only after all workers are quiescent")
    parser.add_argument("--self-test",action="store_true",help="apply and compile only in a temporary copied fixture")
    args=parser.parse_args()
    original=TARGET.read_text()
    updated=apply_to_text(original)
    compile(updated,str(TARGET),"exec")
    before=hashlib.sha256(original.encode()).hexdigest()
    after=hashlib.sha256(updated.encode()).hexdigest()
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix="lamost-science-patch-") as td:
            root=Path(td)
            fixture=root/"source"/"science.py"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(original)
            _apply(fixture,fixture)
            if hashlib.sha256(fixture.read_bytes()).hexdigest()!=after:
                raise SystemExit("temporary fixture output does not match proposed patch")
            shutil.copy2(HERE/"phase_worker.py",fixture.parent/"phase_worker.py")
            tests=root/"tests"; tests.mkdir()
            shutil.copy2(HERE.parent/"tests"/"test_science.py",tests/"test_science.py")
            # Exercise sampler snapshot/restore independently of model fitting.
            import joblib, optuna
            sampler=optuna.samplers.TPESampler(seed=81173,n_startup_trials=2)
            study1=optuna.create_study(direction="maximize",sampler=sampler)
            for value in (0.3,0.8,1.4):
                trial=study1.ask()
                proposed=trial.suggest_float("x",0.001,2.0,log=True)
                study1.tell(trial,-(proposed-value)**2)
            snapshot=root/"sampler.joblib"
            _persist_sampler(snapshot,study1.sampler)
            restored=joblib.load(snapshot)
            study2=optuna.create_study(direction="maximize",sampler=restored)
            for prior in study1.get_trials(deepcopy=True):
                study2.add_trial(prior)
            next1=study1.ask(); proposal1=next1.suggest_float("x",0.001,2.0,log=True)
            next2=study2.ask(); proposal2=next2.suggest_float("x",0.001,2.0,log=True)
            if proposal1!=proposal2:
                raise SystemExit(f"sampler restore changed next proposal: {proposal1} != {proposal2}")
            env=os.environ.copy()
            env["PYTHONPATH"]=str(fixture.parent)+os.pathsep+env.get("PYTHONPATH","")
            proc=subprocess.run([sys.executable,"-m","pytest","-q",str(tests/"test_science.py")],
                                env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            if proc.returncode:
                raise SystemExit("temporary patched-engine fixture tests failed:\n"+proc.stdout)
            print(proc.stdout.strip())
        print(f"temporary-copy self-test passed; sampler next proposal={proposal1}; before={before}; after={after}")
        return
    if not args.apply:
        print(f"dry-run only; before={before}; proposed_after={after}; no source changed")
        print("Apply only after the controller confirms all workers are quiescent.")
        return
    backup=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".pre-maintenance")
    backup.write_bytes(original.encode())
    temp=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".tmp")
    temp.write_text(updated)
    os.replace(temp,TARGET)
    print(f"applied; backup={backup}; before={before}; after={after}")

if __name__=="__main__": main()
