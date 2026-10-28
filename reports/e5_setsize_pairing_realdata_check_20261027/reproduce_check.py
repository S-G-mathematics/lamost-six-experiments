#!/usr/bin/env python3
import csv, hashlib, importlib.util, json, math, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/ubuntu/lamost_e1_migration_20261023')
RT = ROOT/'runtime_20261025'
OUT = RT/'reports'/'e5_setsize_pairing_realdata_check_20261027'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = RT/'source'/'reporting.py'
SOURCE_SHA_BEFORE = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
sys.path.insert(0, str(RT/'source'))
spec=importlib.util.spec_from_file_location('reporting_pairing_crosscheck', SOURCE)
reporting=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporting)
sys.path.remove(str(RT/'source'))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def read_csv(p):
    with Path(p).open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))

def fnum(v):
    if v in ('',None): return None
    return float(v)

def close(a,b):
    if a is None or b is None: return a is None and b is None
    return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)

reg=json.loads((RT/'registry.json').read_text())
registry={str(t.get('key')):t for t in reg['tasks'] if isinstance(t,dict) and t.get('key')}
outputs=[]
summary_outputs=[]
input_hashes={'registry.json':sha(RT/'registry.json'),'source/reporting.py':SOURCE_SHA_BEFORE}
blocks=[
    ('knn','knn','reports/e5_direct_knn_block_20261027',
     'E5_DIRECT_KNN_210_PER_CLASS_METRICS.csv','E5_DIRECT_KNN_189_PER_CLASS_PAIRED.csv',
     'E5_DIRECT_KNN_63_PER_CLASS_SUMMARY.csv'),
    ('random_forest','random_forest','reports/e5_direct_rf_block_20261027',
     'E5_DIRECT_RF_210_PER_CLASS_METRICS.csv','E5_DIRECT_RF_189_PER_CLASS_PAIRED.csv',
     'E5_DIRECT_RF_63_PER_CLASS_SUMMARY.csv')
]
pair_mismatches=[]
summary_mismatches=[]
block_counts={}
for method,route,dirname,metrics_name,paired_name,summary_name in blocks:
    base=RT/dirname
    metrics_path=base/metrics_name; paired_path=base/paired_name; summary_path=base/summary_name
    input_hashes[str(metrics_path.relative_to(RT))]=sha(metrics_path)
    input_hashes[str(paired_path.relative_to(RT))]=sha(paired_path)
    input_hashes[str(summary_path.relative_to(RT))]=sha(summary_path)
    metrics=read_csv(metrics_path); block_pairs=read_csv(paired_path); block_summary=read_csv(summary_path)
    keys={r['task_key'] for r in metrics}
    task_records=[registry[k] for k in sorted(keys) if k in registry]
    if len(task_records)!=30 or len(keys)!=30: raise RuntimeError(f'{method}: expected 30 actual registry tasks, got records={len(task_records)} unique keys={len(keys)}')
    cases=[]
    for rec in task_records:
        outcome=reporting._effective_status(rec)
        cases.append({'key':rec.get('key'),'scientific_case':rec.get('scientific_case'),
          'experiment':rec.get('experiment'),'rep':rec.get('rep'),'method':rec.get('method'),
          'route':rec.get('route'),'generator':rec.get('generator'),
          'condition':rec.get('condition'),'mechanism':rec.get('mechanism') or ('clean' if rec.get('condition')=='clean' else None),
          'rate':rec.get('rate'),'outcome':outcome})
    class_rows=[{'key':r['task_key'],'class_id':str(r['class_index']),
       'recall':fnum(r['recall']),'coverage':fnum(r['coverage']),
       'set_size':fnum(r['mean_set_size'])} for r in metrics]
    actual_pairs=reporting._paired_per_class(cases,class_rows)
    if len(actual_pairs)!=189: raise RuntimeError(f'{method}: expected 189 computed class pairs, got {len(actual_pairs)}')
    if len(block_pairs)!=189: raise RuntimeError(f'{method}: expected 189 block pair rows, got {len(block_pairs)}')
    expected_by={(r['corrupted_task_key'],str(r['class_index'])):r for r in block_pairs}
    computed_by={(str(r['corrupted_key']),str(r['class_id'])):r for r in actual_pairs}
    if set(expected_by)!=set(computed_by): raise RuntimeError(f'{method}: pair key membership mismatch {len(set(expected_by)^set(computed_by))}')
    n_available=0
    for ident in sorted(computed_by):
        c=computed_by[ident]; b=expected_by[ident]
        expected_identity=(str(b['rep']),b['condition'],str(b['class_index']),b['clean_task_key'],b['corrupted_task_key'])
        actual_identity=(str(c['rep']),str(c['mechanism'])+'_'+str(int(round(float(c['rate'])*100))),str(c['class_id']),str(c['clean_key']),str(c['corrupted_key']))
        # condition aliases in source task keys are authoritative; compare the complete task-key identity below.
        identity_ok=(actual_identity[2]==expected_identity[2] and actual_identity[3:]==expected_identity[3:]
                     and str(c['rep'])==str(b['rep']) and str(c['mechanism'])==str(b['mechanism'])
                     and close(float(c['rate'])*100,float(b['rate_percent'])))
        if not identity_ok: pair_mismatches.append({'method':method,'identity':ident,'field':'identity'})
        if bool(c['paired_available']) != (str(b['paired_available']).lower()=='true'):
            pair_mismatches.append({'method':method,'identity':ident,'field':'paired_available'})
        if c['paired_available']: n_available+=1
        compare_fields=[
          ('recall_difference_a_minus_b','difference_recall_corrupted_minus_clean'),
          ('coverage_difference_a_minus_b','difference_coverage_corrupted_minus_clean'),
          ('set_size_difference_a_minus_b','difference_mean_set_size_corrupted_minus_clean')]
        for cf,bf in compare_fields:
            ev=fnum(b[bf]); av=c.get(cf)
            if not close(av,ev):
                pair_mismatches.append({'method':method,'identity':ident,'field':cf,'computed':av,'block':ev})
        outputs.append({'method':method,'rep':c['rep'],'mechanism':c['mechanism'],'rate':c['rate'],
          'class_id':c['class_id'],'clean_key':c['clean_key'],'corrupted_key':c['corrupted_key'],
          'paired_available':c['paired_available'],'computed_recall_delta':c['recall_difference_a_minus_b'],
          'block_recall_delta':fnum(b['difference_recall_corrupted_minus_clean']),
          'computed_coverage_delta':c['coverage_difference_a_minus_b'],
          'block_coverage_delta':fnum(b['difference_coverage_corrupted_minus_clean']),
          'computed_set_size_delta':c['set_size_difference_a_minus_b'],
          'block_set_size_delta':fnum(b['difference_mean_set_size_corrupted_minus_clean'])})
    if n_available!=189: raise RuntimeError(f'{method}: expected all 189 class pairs available, got {n_available}')
    keysum=('method','route','generator','mechanism','rate','class_id')
    computed_summary=reporting._condition_paired_summary(actual_pairs,keysum,
       ('recall_difference_a_minus_b','coverage_difference_a_minus_b','set_size_difference_a_minus_b'))
    if len(computed_summary)!=63 or len(block_summary)!=63: raise RuntimeError(f'{method}: summary row count mismatch')
    block_sum={(r['mechanism'],float(r['rate_percent']),str(r['class_index'])):r for r in block_summary}
    for s in computed_summary:
        key=(str(s['mechanism']),float(s['rate'])*100,str(s['class_id']))
        b=block_sum.get(key)
        if b is None:
            summary_mismatches.append({'method':method,'identity':key,'field':'summary_key'})
            continue
        for metric,mean_field,sd_field,n_field in [
          ('recall','recall_difference_a_minus_b_mean','recall_difference_a_minus_b_sample_sd','recall_difference_a_minus_b_n'),
          ('coverage','coverage_difference_a_minus_b_mean','coverage_difference_a_minus_b_sample_sd','coverage_difference_a_minus_b_n'),
          ('set_size','set_size_difference_a_minus_b_mean','set_size_difference_a_minus_b_sample_sd','set_size_difference_a_minus_b_n')]:
            blockmean=fnum(b[f'mean_difference_{"mean_set_size" if metric=="set_size" else metric}'])
            blocksd=fnum(b[f'sample_sd_difference_{"mean_set_size" if metric=="set_size" else metric}'])
            blockn=int(b['matched_n'])
            if int(s[n_field])!=blockn: summary_mismatches.append({'method':method,'identity':key,'field':n_field,'computed':s[n_field],'block':blockn})
            if not close(s[mean_field],blockmean): summary_mismatches.append({'method':method,'identity':key,'field':mean_field,'computed':s[mean_field],'block':blockmean})
            if not close(s[sd_field],blocksd): summary_mismatches.append({'method':method,'identity':key,'field':sd_field,'computed':s[sd_field],'block':blocksd})
        summary_outputs.append({'method':method,'mechanism':s['mechanism'],'rate':s['rate'],'class_id':s['class_id'],
          'recall_n':s['recall_difference_a_minus_b_n'],'recall_mean':s['recall_difference_a_minus_b_mean'],'recall_sample_sd':s['recall_difference_a_minus_b_sample_sd'],
          'coverage_n':s['coverage_difference_a_minus_b_n'],'coverage_mean':s['coverage_difference_a_minus_b_mean'],'coverage_sample_sd':s['coverage_difference_a_minus_b_sample_sd'],
          'set_size_n':s['set_size_difference_a_minus_b_n'],'set_size_mean':s['set_size_difference_a_minus_b_mean'],'set_size_sample_sd':s['set_size_difference_a_minus_b_sample_sd']})
    block_counts[method]={'task_keys':len(keys),'class_metrics':len(metrics),'computed_pairs':len(actual_pairs),
      'block_pairs':len(block_pairs),'available_pairs':n_available,'computed_summaries':len(computed_summary),
      'block_summaries':len(block_summary)}

comparison=OUT/'paired_row_comparison.csv'
with comparison.open('w',newline='',encoding='utf-8') as f:
    fields=list(outputs[0]); w=csv.DictWriter(f,fieldnames=fields); w.writeheader();w.writerows(outputs)
summary_path=OUT/'paired_summary_comparison.csv'
with summary_path.open('w',newline='',encoding='utf-8') as f:
    fields=list(summary_outputs[0]); w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(summary_outputs)
source_sha_after=sha(SOURCE)
if source_sha_after!=SOURCE_SHA_BEFORE: raise RuntimeError('reporting source changed during check')
qa={'schema':'lamost-e5-setsize-pairing-realdata-check/1','observed_utc':datetime.now(timezone.utc).isoformat(),
    'mode':'read-only saved CSV and registry metadata algebra; no model/NPZ/prediction loads',
    'source_reporting_sha256_before':SOURCE_SHA_BEFORE,'source_reporting_sha256_after':source_sha_after,
    'registry_sha256':input_hashes['registry.json'],'input_sha256':input_hashes,
    'block_counts':block_counts,'paired_row_count_total':len(outputs),'summary_group_count_total':len(summary_outputs),
    'paired_mismatches':pair_mismatches,'summary_mismatches':summary_mismatches,
    'paired_mismatch_count':len(pair_mismatches),'summary_mismatch_count':len(summary_mismatches),
    'summary_n_histogram':dict(Counter(str(r['set_size_n']) for r in summary_outputs)),
    'summary_group_n_all_three':all(r['set_size_n']==3 and r['recall_n']==3 and r['coverage_n']==3 for r in summary_outputs),
    'comparison_csv':'paired_row_comparison.csv','summary_comparison_csv':'paired_summary_comparison.csv',
    'status':'passed' if not pair_mismatches and not summary_mismatches and all(r['set_size_n']==3 and r['recall_n']==3 and r['coverage_n']==3 for r in summary_outputs) else 'failed'}
qa['reproduction_script_sha256']=sha(Path(__file__))
qa_path=OUT/'QA.json'; qa_path.write_text(json.dumps(qa,indent=2,sort_keys=True)+'\n')
qa['paired_row_comparison_sha256']=sha(comparison); qa['paired_summary_comparison_sha256']=sha(summary_path); qa_path.write_text(json.dumps(qa,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':qa['status'],'summary_n_histogram':qa['summary_n_histogram'],'block_counts':block_counts,
 'paired_mismatches':len(pair_mismatches),'summary_mismatches':len(summary_mismatches),
 'qa':str(qa_path),'comparison':str(comparison),'summaries':str(summary_path)},indent=2))

