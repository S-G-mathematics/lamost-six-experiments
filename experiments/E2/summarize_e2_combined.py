import csv,datetime,json,pathlib,collections,math
import numpy as np
from scipy.stats import spearmanr
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e2_20261024')
with (B/'E2_artifact_availability_270.csv').open(newline='') as f: audit=list(csv.DictReader(f))
methods=['gmm','copula','arf','kde','chow_liu']
rows=[]
for x in audit:
 if x['family_set']!='primary':continue
 b=int(x['budget']);r=int(x['repetition']);m=x['method']
 original=B/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json'
 reconstructed=B/'reconstruction_fidelity'/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json'
 if original.exists():p=original;provenance='original_saved_frozen_E1_fit'
 elif reconstructed.exists():p=reconstructed;provenance='E2_reconstructed_selected_fit'
 else:p=None;provenance='unavailable'
 result=json.loads(p.read_text()) if p else {}
 fidelity=result.get('class_balanced_fidelity') if result.get('status')=='fidelity_complete' else None
 ba=result.get('direct_classification_balanced_accuracy',result.get('classification_balanced_accuracy_from_frozen_e1'))
 paired_status='paired' if fidelity is not None and ba is not None else ('classification_pending' if fidelity is not None else 'unavailable')
 rows.append({'budget':b,'repetition':r,'method':m,'provenance':provenance,'original_e1_classification':x['e1_classification'],'fidelity_status':result.get('status','unavailable'),'class_balanced_fidelity':fidelity,'classification_balanced_accuracy':ba,'classification_source':result.get('classification_source','frozen_e1_test_evaluation' if provenance=='original_saved_frozen_E1_fit' else 'unavailable'),'reproduction_gate_status':result.get('reproduction_gate_status','not_applicable' if provenance=='original_saved_frozen_E1_fit' else 'pending'),'paired_status':paired_status})
assert len(rows)==150
with (B/'E2_combined_points_150.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
strata=[]
for b in [3000,10000,30000,100000,300000,1000000]:
 for r in range(1,6):
  selected=[x for x in rows if x['budget']==b and x['repetition']==r]
  paired=[x for x in selected if x['paired_status']=='paired']
  full=len(paired)==5
  rho=float(spearmanr([x['class_balanced_fidelity'] for x in paired],[x['classification_balanced_accuracy'] for x in paired]).statistic) if full else None
  strata.append({'budget':b,'repetition':r,'paired_families':len(paired),'fidelity_families':sum(x['class_balanced_fidelity'] is not None for x in selected),'full_five_family_spearman':rho,'status':'full_five_family' if full else 'incomplete','missing_methods':','.join(x['method'] for x in selected if x['paired_status']!='paired')})
with (B/'E2_combined_spearman_30.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(strata[0]));w.writeheader();w.writerows(strata)
summary={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'primary_planned':150,'primary_fidelity_complete':sum(x['class_balanced_fidelity'] is not None for x in rows),'primary_paired_fidelity_and_accuracy':sum(x['paired_status']=='paired' for x in rows),'original_saved_fit_fidelity':sum(x['provenance']=='original_saved_frozen_E1_fit' and x['class_balanced_fidelity'] is not None for x in rows),'reconstructed_fit_fidelity':sum(x['provenance']=='E2_reconstructed_selected_fit' and x['class_balanced_fidelity'] is not None for x in rows),'full_five_family_strata':sum(x['status']=='full_five_family' for x in strata),'incomplete_strata':sum(x['status']=='incomplete' for x in strata),'no_bootstrap':True,'no_TSTR':True,'original_and_reconstructed_provenance_separate':True}
(B/'E2_combined_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
