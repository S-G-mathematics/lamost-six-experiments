#!/usr/bin/env python3
"""Data-only E6-v2 descriptive export. Does not fit, load, or score models."""
import argparse,csv,hashlib,json
from pathlib import Path
from e6_v2_reporting import export_v2_outputs, render_status_section, superseded_gate_history

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--superseded-ledger',type=Path,required=True,
                   help='preserved pre-v2 E6_FINAL_CELL_LEDGER_21.csv')
    p.add_argument('--output',type=Path,required=True,
                   help='new versioned output directory; must not contain previous report outputs')
    a=p.parse_args()
    rt=a.runtime.resolve();out=a.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit('refusing to overwrite a nonempty report directory')
    registry=json.loads((rt/'registry.json').read_text(encoding='utf-8'))
    tasks=registry.get('tasks')
    if not isinstance(tasks,list):raise SystemExit('registry tasks missing')
    with a.superseded_ledger.open(newline='',encoding='utf-8') as f:
        old=list(csv.DictReader(f))
    historical=superseded_gate_history(old,[t for t in tasks if t.get('experiment')==6 and t.get('kind')=='ensemble' and t.get('scientific_case')])
    counts=export_v2_outputs(rt,tasks,a.superseded_ledger,out)
    with (out/'E6_V2_AVAILABILITY.csv').open(newline='',encoding='utf-8') as f:
        availability=list(csv.DictReader(f))
    with (out/'E6_V2_PARTIAL_TUNING_EVIDENCE.csv').open(newline='',encoding='utf-8') as f:
        partial=list(csv.DictReader(f))
    (out/'E6_V2_STATUS.md').write_text(render_status_section(availability,historical,partial),encoding='utf-8',newline='\n')
    inputs={'registry_sha256':sha(rt/'registry.json'),'superseded_ledger_sha256':sha(a.superseded_ledger)}
    source_hashes={'exporter_sha256':sha(Path(__file__)),'helper_sha256':sha(Path(__file__).with_name('e6_v2_reporting.py'))}
    output_hashes={x.relative_to(out).as_posix():sha(x) for x in sorted(out.rglob('*')) if x.is_file()}
    receipt={'schema_version':'lamost-e6-v2-descriptive-export/1',
             'status':'descriptive_outputs_only_not_project_completion',
             'registry_observed_utc':registry.get('observed_utc'),
             'inputs':inputs,'source_sha256':source_hashes,'output_rows':counts,'outputs_sha256':output_hashes,
             'actions':{'fitting':False,'model_loading':False,'posterior_generation':False,
                        'calibration_or_test_inference':False,'bootstrap':False}}
    (out/'E6_V2_REPORT_RECEIPT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'status':receipt['status'],'output_rows':counts,
                      'receipt_sha256':sha(out/'E6_V2_REPORT_RECEIPT.json')}))

if __name__=='__main__':main()
