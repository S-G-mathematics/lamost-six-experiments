from pathlib import Path
import sys,json,fcntl,platform,datetime,importlib.metadata
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'source'))
lock=(R/'reports/report.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX)
import reporting
res=reporting.report(R)
versions={}
for n in ['matplotlib','numpy']:
 try:versions[n]=importlib.metadata.version(n)
 except importlib.metadata.PackageNotFoundError:pass
(R/'reports/report_environment.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'packages':versions,'purpose':'descriptive reporting only; model fitting uses frozen project venv','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
(R/'reports/report_result.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
print(json.dumps(res))
