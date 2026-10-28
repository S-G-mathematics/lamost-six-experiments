from __future__ import annotations
import json,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import science
cfg=json.loads(Path(sys.argv[1]).read_text())
try:
    result=science.worker(cfg)
    p=Path(cfg["out"])/"phase_result.json"
    t=p.with_suffix(".tmp"); t.write_text(json.dumps(result,sort_keys=True,indent=2,default=science._json_default)); t.replace(p)
except BaseException as e:
    trace=traceback.format_exc()
    Path(cfg["out"],"phase_traceback.txt").write_text(trace)
    category="scientific_failure" if isinstance(e,science.ScientificFitFailure) else "operationally_invalid"
    Path(cfg["out"],"phase_exception.json").write_text(json.dumps({"phase":cfg.get("phase"),"exception_type":type(e).__name__,"category":category,"message":str(e),"traceback":trace},sort_keys=True,indent=2))
    raise
