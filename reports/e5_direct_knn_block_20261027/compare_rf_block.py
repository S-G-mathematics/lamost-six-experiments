#!/usr/bin/env python3
"""Pair validated direct-KNN E5 changes against the completed direct-RF block."""
import csv,hashlib,json,math,statistics,datetime
from pathlib import Path
OUT=Path(__file__).resolve().parent
RF=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/e5_direct_rf_block_20261027')
metrics=['balanced_accuracy','coverage','mean_set_size']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(p,rs):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]),lineterminator='\n');w.writeheader();w.writerows(rs)
def main():
 knn=rows(OUT/'E5_DIRECT_KNN_27_PAIRED_CORRUPT_MINUS_CLEAN.csv')
 rf=rows(RF/'E5_DIRECT_RF_27_PAIRED_CORRUPT_MINUS_CLEAN.csv')
 if len(knn)!=27 or len(rf)!=27: raise RuntimeError('Expected 27 paired corruption rows for each completed classifier block')
 byrf={(int(x['rep']),x['condition']):x for x in rf}
 if len(byrf)!=27: raise RuntimeError('RF paired table has duplicate rep-condition rows')
 out=[]
 for k in knn:
  key=(int(k['rep']),k['condition'])
  if key not in byrf: raise RuntimeError(f'Missing paired RF row: {key}')
  r=byrf[key]
  z={'rep':key[0],'mechanism':k['mechanism'],'rate_percent':k['rate_percent'],'condition':k['condition'],'knn_task_key':k['corrupted_task_key'],'rf_task_key':r['corrupted_task_key'],'matched_representation':'same repetition and corruption condition; each classifier paired to its own clean control'}
  for m in metrics:
   kd=float(k[f'difference_{m}_corrupted_minus_clean']); rd=float(r[f'difference_{m}_corrupted_minus_clean'])
   z[f'knn_difference_{m}']=kd;z[f'rf_difference_{m}']=rd;z[f'knn_minus_rf_difference_{m}']=kd-rd
  out.append(z)
 write(OUT/'E5_DIRECT_KNN_VS_RF_27_PAIRED_DEGRADATION_DIFFERENCE.csv',out)
 sums=[]
 for cond in sorted({x['condition'] for x in out}):
  rr=sorted([x for x in out if x['condition']==cond],key=lambda x:x['rep'])
  z={'condition':cond,'mechanism':rr[0]['mechanism'],'rate_percent':rr[0]['rate_percent'],'planned_pairs':3,'matched_n':len(rr),'repetitions':';'.join(str(x['rep']) for x in rr)}
  for m in metrics:
   vals=[x[f'knn_minus_rf_difference_{m}'] for x in rr]
   z[f'mean_knn_minus_rf_paired_change_{m}']=statistics.mean(vals) if vals else None
   z[f'sample_sd_knn_minus_rf_paired_change_{m}']=statistics.stdev(vals) if len(vals)>1 else None
   z[f'individual_rep_values_{m}']=';'.join(f"{x['rep']}:{x[f'knn_minus_rf_difference_{m}']:.12g}" for x in rr)
  sums.append(z)
 write(OUT/'E5_DIRECT_KNN_VS_RF_9_CONDITION_SUMMARY.csv',sums)
 rp=OUT/'E5_DIRECT_KNN_BLOCK_REPORT.md'; base=rp.read_text(encoding='utf-8').split('\n## Matched comparison with direct RF')[0].rstrip()
 sec=['','## Matched comparison with direct RF','','For each repetition and corruption condition, each classifier's change is first calculated against its own clean control. The table below reports the KNN change minus the RF change for the same repetition and condition; n is the number of matched repetition pairs. These contrasts are descriptive and do not imply universal superiority. Individual repetition values are in the linked CSV.','', '| Mechanism | Rate | Matched n/3 | KNN minus RF paired change in balanced accuracy | SD | KNN minus RF paired change in coverage | SD | KNN minus RF paired change in mean set size | SD |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for x in sums:
  sec.append(f"| {x['mechanism']} | {x['rate_percent']}% | {x['matched_n']}/3 | {x['mean_knn_minus_rf_paired_change_balanced_accuracy']:.6f} | {x['sample_sd_knn_minus_rf_paired_change_balanced_accuracy']:.6f} | {x['mean_knn_minus_rf_paired_change_coverage']:.6f} | {x['sample_sd_knn_minus_rf_paired_change_coverage']:.6f} | {x['mean_knn_minus_rf_paired_change_mean_set_size']:.6f} | {x['sample_sd_knn_minus_rf_paired_change_mean_set_size']:.6f} |")
 rp.write_text(base+'\n'+'\n'.join(sec)+'\n',encoding='utf-8')
 files=['E5_DIRECT_KNN_VS_RF_27_PAIRED_DEGRADATION_DIFFERENCE.csv','E5_DIRECT_KNN_VS_RF_9_CONDITION_SUMMARY.csv','E5_DIRECT_KNN_BLOCK_REPORT.md']
 receipt={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'paired direct-KNN vs direct-RF corruption changes by exact repetition and condition; descriptive only','paired_rows':len(out),'condition_summary_rows':len(sums),'bootstrap':False,'significance_tests':False,'inputs':{str(q):sha(q) for q in [OUT/'E5_DIRECT_KNN_27_PAIRED_CORRUPT_MINUS_CLEAN.csv',RF/'E5_DIRECT_RF_27_PAIRED_CORRUPT_MINUS_CLEAN.csv',OUT/'evidence_manifest.json',RF/'evidence_manifest.json']},'outputs':{name:{'sha256':sha(OUT/name),'bytes':(OUT/name).stat().st_size} for name in files},'analysis_script_sha256':sha(Path(__file__)),'knn_analyzer_sha256':sha(OUT/'analyze_block.py')}
 (OUT/'comparison_evidence_manifest.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'paired_rows':len(out),'summary_rows':len(sums),'summary':sums},indent=2))
if __name__=='__main__':main()
