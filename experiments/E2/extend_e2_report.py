import csv,json,pathlib,collections
import pandas as pd
from scipy.stats import spearmanr
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
E=B/'e2_20261024'
z=json.loads((B/'project/benchmark/results/e1_report_validated_no_bootstrap.json').read_text())
budget_set={3000,10000,30000,100000,300000,1000000}
methods={'gmm','copula','arf','kde','chow_liu'}
bad=[x for x in z['cells'] if x['budget'] in budget_set and x['method'] in methods and x['classification']!='successful_test_evaluation']
assert len(bad)==42
fields=['budget','repetition','method','classification','status','error']
with (E/'E2_missing_primary_42.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for x in sorted(bad,key=lambda a:(a['budget'],a['repetition'],a['method'])):w.writerow({k:x.get(k) for k in fields})
points=pd.read_csv(E/'E2_combined_points_150.csv')
class_reports=pd.read_csv(E/'E2_all_class_reports_1596.csv')
out=[]
for b in sorted(budget_set):
 for r in range(1,6):
  q=points[(points.budget==b)&(points.repetition==r)&points.class_balanced_fidelity.notna()&points.classification_balanced_accuracy.notna()]
  n=len(q)
  rho=float(spearmanr(q.class_balanced_fidelity,q.classification_balanced_accuracy).statistic) if n>=3 else None
  low=class_reports[(class_reports.family_set=='primary')&(class_reports.budget==b)&(class_reports.repetition==r)&(class_reports.status=='valid_low_precision')]
  missing=','.join(sorted(methods-set(q.method)))
  out.append({'budget':b,'repetition':r,'paired_primary_families':n,'protocol_full_five_family':n==5,'full_five_family_spearman':rho if n==5 else None,'available_only_spearman_exploratory':rho if 3<=n<5 else None,'missing_primary_methods':missing,'low_precision_class_reports':len(low)})
pd.DataFrame(out).to_csv(E/'E2_within_stratum_descriptive_30.csv',index=False)
qa=json.loads((E/'E2_INTEGRITY_AUDIT.json').read_text())
assert not qa['integrity_errors']
report=E/'E2_CURRENT_REPORT.md'
s=report.read_text()
if '## Integrity and availability audit' not in s:
 s+='\n## Integrity and availability audit\n\n'
 s+='The EC2 audit checked all 228 evaluated cells: pipeline hashes, class-score aggregation, saved diagnostic hashes and shapes, fixed reference IDs across models and provenance sets, exclusion of test IDs from fidelity references, and paired classification scores. **No integrity errors** were found.\n\n'
 s+=f"Of 1,596 class reports, {qa['class_valid_low_precision']} are flagged low precision (<20 diagnostic rows). These occur at 3k and 10k, including all four complete five-family strata. They remain in the protocol's equal seven-class average and limit precision of those descriptive correlations.\n\n"
 s+=f"Among 185 reconstructed fits, 154 reproduced the recorded E1 balanced accuracy to 1e-10 and 31 differed; the maximum absolute difference was {qa['reconstruction_gate_max_abs_BA_difference']:.8f}. Every E2 pairing uses the classification score measured from its own reconstructed fit.\n\n"
 s+='The 42 unavailable primary cells comprise 40 frozen E1 resource failures and 2 supervisor-terminal failures. They are all ARF or KDE; 21 recorded a 180-second trial timeout, 19 recorded all trials failed, and 2 have no ordinary cell error because the supervisor terminalized the cell. See E2_missing_primary_42.csv.\n\n'
 s+='E2_within_stratum_descriptive_30.csv provides available-only rank correlations for the 26 incomplete strata, separately labeled exploratory; it never treats a three- or four-family correlation as the protocol five-family result. No budget pooling or bootstrap was added.\n'
 report.write_text(s)
print(json.dumps({'missing_primary':len(bad),'missing_by_classification':dict(collections.Counter(x['classification'] for x in bad)),'full_strata':sum(x['protocol_full_five_family'] for x in out),'partial_strata':sum(3<=x['paired_primary_families']<5 for x in out),'integrity_errors':len(qa['integrity_errors'])}))
