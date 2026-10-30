#!/usr/bin/env python3
"""Render an E6-only descriptive figure refresh from the current read-only task registry and saved E6 evaluation JSON.

This script reads only registry rows and evaluation/validation JSON files. It does not open prediction arrays,
role NPZ files, fitted models, or generate predictions. Run with /usr/bin/python3 on the EC2 project tree.
"""
import csv, hashlib, json, pathlib, sqlite3, sys, datetime, math
BASE=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=BASE/'runtime_20261025'
OUT=R/'reports/E6_FIGURE_REFRESH_20261030T030121Z'
EXPECTED_REPORTING='b9f7d431d6cdc30e347530a9b4de217b14e2f04650066f4cef155f29b58eda08'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load_json(p):
    return json.loads(p.read_text(encoding='utf-8'))
def finite(x):
    return isinstance(x,(int,float)) and math.isfinite(float(x))
source=R/'source/reporting.py'
if sha(source)!=EXPECTED_REPORTING:
    raise SystemExit('live reporting.py changed; refusing to use an unreviewed plot implementation')
sys.path.insert(0,str(R/'source'))
import reporting
OUT.mkdir(parents=True,exist_ok=True)
db=R/'registry.sqlite'
con=sqlite3.connect(f'file:{db}?mode=ro',uri=True)
con.execute('PRAGMA query_only=ON')
con.execute('BEGIN')
records=[]
for key, raw in con.execute('SELECT key, record FROM tasks'):
    rec=json.loads(raw)
    if rec.get('experiment')==6:
        rec['key']=key
        records.append(rec)
if len(records)!=21:
    raise SystemExit(f'expected 21 E6 terminal/planned ledger rows, found {len(records)}')
records.sort(key=lambda r:r['key'])
snapshot_observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
registry_e6_records_sha256=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
summary=[]
plot_rows=[]
eval_inputs=[]
for rec in records:
    key=rec['key']; parts=key.split('/')
    if len(parts)<4 or parts[0]!='e6': raise SystemExit(f'unexpected E6 key {key}')
    rep=int(parts[1].removeprefix('rep_'))
    kind=rec.get('kind')
    outcome=rec.get('outcome')
    if not isinstance(outcome,str):
        outcome=outcome.get('status') or outcome.get('outcome') if isinstance(outcome,dict) else None
    row={'key':key,'experiment':6,'scientific_case':bool(rec.get('scientific_case')),'rep':rep,
         'kind':kind,'outcome':outcome,'status':rec.get('status'),
         'validation_state':rec.get('validation_state'),'balanced_accuracy':None,'coverage':None,'set_size':None}
    if key.startswith('e6/rep_') and '/eval/member/' in key:
        family=parts[-1]
        row.update({'generator':family,'route':'member','condition':'member_reference','method':family})
        if outcome=='successful':
            art=R/'artifacts'/key
            ep=art/'evaluation.json'; vp=art/'validation.json'
            if not ep.is_file() or not vp.is_file(): raise SystemExit(f'missing validated alias JSON for {key}')
            ev=load_json(ep); val=load_json(vp)
            evsha=sha(ep); valsha=sha(vp)
            if val.get('task_key')!=key or val.get('status')!='validated' or val.get('files',{}).get('evaluation.json')!=evsha:
                raise SystemExit(f'alias validation hash/task mismatch for {key}')
            if ev.get('task_key')!=key or ev.get('experiment')!=6 or ev.get('reused_from') is None:
                raise SystemExit(f'alias provenance mismatch for {key}')
            if ev.get('calibration_n')!=10000 or ev.get('test_n')!=500000 or ev.get('score_kind')!='probability':
                raise SystemExit(f'alias cohort/score metadata mismatch for {key}')
            for metric in ('balanced_accuracy','coverage','set_size'):
                if not finite(ev.get(metric)): raise SystemExit(f'nonfinite {metric} for {key}')
                row[metric]=float(ev[metric])
            eval_inputs.append({'task_key':key,'evaluation_sha256':evsha,'validation_sha256':valsha,
                                'reused_from':ev['reused_from'],'pipeline_sha256':ev.get('pipeline_sha256'),
                                'calibration_n':ev['calibration_n'],'test_n':ev['test_n']})
        else:
            if row['balanced_accuracy'] is not None: raise SystemExit('failed alias cannot carry metrics')
    elif key.startswith('e6/rep_') and '/ensemble/' in key:
        mode=parts[-1]
        row.update({'mode':mode,'method':mode,'route':mode,'condition':mode})
        if outcome=='successful':
            raise SystemExit(f'no E6 primary success expected in this refresh; review new status before plotting: {key}')
    else:
        raise SystemExit(f'unrecognized E6 row {key}')
    plot_rows.append(row)
    summary.append({'task_key':key,'rep':rep,'kind':kind,'outcome':outcome,
                    'validation_state':rec.get('validation_state'),'method':row.get('method'),
                    'condition':row.get('condition'),'route':row.get('route'),
                    'balanced_accuracy':row['balanced_accuracy'],'coverage':row['coverage'],'set_size':row['set_size']})
if len(eval_inputs)!=12: raise SystemExit(f'expected 12 validated member references, found {len(eval_inputs)}')
con.commit(); con.close()
# Preserve a compact status/metric denominator ledger for this figure refresh.
fields=list(summary[0])
with (OUT/'E6_CURRENT_21_CELL_LEDGER.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); w.writeheader(); w.writerows(summary)
made=reporting._figures(str(R),str(OUT),plot_rows)
expected={f'E6_{m}_member_ensemble.png' for m in ('balanced_accuracy','coverage','set_size')}
if {pathlib.Path(p).name for p in made}!=expected:
    raise SystemExit(f'expected exactly three E6 figures, got {made}')
metrics=[]
for p in sorted(OUT.glob('E6_*.png')):
    metrics.append({'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
ledger=OUT/'E6_CURRENT_21_CELL_LEDGER.csv'
script_path=OUT/'render_e6_figures.py'
script_path.write_text(pathlib.Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
manifest={
 'schema':'lamost-e6-figure-refresh/1','observed_utc':now,
 'source_reporting_path':'runtime_20261025/source/reporting.py','source_reporting_sha256':sha(source),
 'plot_generation':'reporting._figures called with exactly 21 E6 scientific case rows',
 'scope':'E6-only static plotting; no source edits, no calibration replay, no model/NPZ/prediction reads',
 'registry_source':'runtime_20261025/registry.sqlite (read-only transaction; only E6 task records selected)',
 'registry_snapshot_observed_utc':snapshot_observed_utc,
 'registry_e6_records_sha256':registry_e6_records_sha256,
 'registry_e6_rows':21,'validated_member_reference_rows':12,'planned_member_reference_rows':15,
 'successful_primary_ensemble_rows':0,'planned_primary_ensemble_rows':6,
 'outcome_counts':{k:sum(1 for r in records if ((r.get('outcome') if isinstance(r.get('outcome'),str) else (r.get('outcome') or {}).get('status'))==k)) for k in ('successful','scientific_failure','unavailable_dependency')},
 'member_metric_inputs':eval_inputs,
 'current_cell_ledger':{'file':ledger.name,'bytes':ledger.stat().st_size,'sha256':sha(ledger)},
 'figures':metrics,
 'reproduction':'/usr/bin/python3 reports/E6_FIGURE_REFRESH_20261030T030121Z/render_e6_figures.py'
}
manifest_path=OUT/'MANIFEST.json'; manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
readme=(
 '# E6 figure refresh (interim)\n\n'
 f'Generated {now}. This is an E6-only rendering refresh from the current read-only 21-row registry slice.\n\n'
 '- 12/15 member-reference rows have validated saved evaluation JSON; these are reused E3 evaluation references, not new model-scoring runs.\n'
 '- 0/6 primary ensemble test evaluations are successful in this snapshot. Equal-weight rows are terminal failures; learned rows are unavailable dependencies. No ensemble test performance or benefit is inferred.\n'
 '- KDE member test evaluations remain unavailable; the other four member families have three validated references each.\n'
 '- Figures use only successful saved metrics. Missing metric groups are shown as unavailable and are not assigned zero scores.\n'
 '- This refresh does not change scientific results or run calibration replay. Final calibration/artifact validation remains pending.\n\n'
 'Files: the three metric figures, a 21-row current cell ledger, this source script, and MANIFEST.json. Input evaluation and validation hashes are listed in the manifest.\n'
)
(OUT/'README.md').write_text(readme,encoding='utf-8')
# Rebind manifest to all generated files except itself.
manifest['files']=[]
for p in sorted(OUT.iterdir()):
    if p.is_file() and p.name!='MANIFEST.json':
        manifest['files'].append({'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps({'outdir':str(OUT),'manifest_sha256':sha(manifest_path),'files':manifest['files'],'counts':manifest['outcome_counts'],'member_refs':len(eval_inputs),'figures':metrics},indent=2))
