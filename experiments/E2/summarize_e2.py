import csv,json,pathlib,collections,datetime,statistics,math
import numpy as np
from scipy.stats import spearmanr
import plotly.graph_objects as go
from plotly.subplots import make_subplots
base=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
out=base/'e2_20261024'
audit=json.loads((out/'E2_artifact_availability_summary.json').read_text())
files=list((out/'cells').rglob('complete.json'))
cells=[json.loads(p.read_text()) for p in files]
assert len(cells)==43
assert sum(c['primary_family'] for c in cells)==19
assert sum(not c['primary_family'] for c in cells)==24
assert all(c['status']=='fidelity_complete' for c in cells)
lookup={(c['budget'],c['repetition'],c['method']):c for c in cells}
primary=['gmm','copula','arf','kde','chow_liu']
reference=['gaussian_nb','shared_diagonal','lda','qda']
budgets=[3000,10000,30000,100000,300000,1000000]
def write_csv(name,rows,fields):
 with (out/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
point_rows=[]
class_rows=[]
for c in sorted(cells,key=lambda x:(x['budget'],x['repetition'],x['method'])):
 point_rows.append({'budget':c['budget'],'repetition':c['repetition'],'method':c['method'],'family_set':'primary' if c['primary_family'] else 'classical_reference','class_balanced_fidelity':c['class_balanced_fidelity'],'frozen_e1_balanced_accuracy':c['classification_balanced_accuracy_from_frozen_e1'],'valid_class_reports':sum(z['status'] in ['valid','valid_low_precision'] for z in c['class_reports']),'low_precision_classes':sum(z['low_precision'] for z in c['class_reports']),'status':c['status']})
 for z in c['class_reports']:
  class_rows.append({'budget':c['budget'],'repetition':c['repetition'],'method':c['method'],'family_set':'primary' if c['primary_family'] else 'classical_reference','class_id':z['class_id'],'diagnostic_n':z['diagnostic_n'],'low_precision':z['low_precision'],'status':z['status'],'quality_score':z.get('sdmetrics_score'),'column_shapes_score':z.get('column_shapes_score'),'column_pair_trends_score':z.get('column_pair_trends_score'),'reference_ids_sha256':z.get('real_reference_ids_sha256')})
write_csv('E2_fidelity_classification_points.csv',point_rows,list(point_rows[0]))
write_csv('E2_class_reports_301.csv',class_rows,list(class_rows[0]))
correlations=[]
for budget in budgets:
 for rep in range(1,6):
  found=[lookup[(budget,rep,m)] for m in primary if (budget,rep,m) in lookup]
  missing=[m for m in primary if (budget,rep,m) not in lookup]
  rho=None
  if len(found)>=3:
   x=[c['class_balanced_fidelity'] for c in found]
   y=[c['classification_balanced_accuracy_from_frozen_e1'] for c in found]
   val=spearmanr(x,y).statistic
   if math.isfinite(float(val)):rho=float(val)
  correlations.append({'budget':budget,'repetition':rep,'primary_families_required':5,'primary_families_available':len(found),'available_methods':','.join(c['method'] for c in found),'missing_methods':','.join(missing),'five_family_spearman_rho':rho if len(found)==5 else None,'five_family_status':'complete' if len(found)==5 and rho is not None else 'unavailable_missing_primary_families','available_only_spearman_rho_descriptive':rho,'available_only_n':len(found)})
write_csv('E2_spearman_within_budget_repetition.csv',correlations,list(correlations[0]))
summaries=[]
for budget in budgets:
 for method in primary+reference:
  group=[c for c in cells if c['budget']==budget and c['method']==method]
  summaries.append({'budget':budget,'method':method,'family_set':'primary' if method in primary else 'classical_reference','successful_fidelity_repetitions':len(group),'expected_repetitions':5,'mean_fidelity':statistics.fmean(c['class_balanced_fidelity'] for c in group) if group else None,'fidelity_sample_sd':statistics.stdev(c['class_balanced_fidelity'] for c in group) if len(group)>1 else None,'mean_frozen_e1_balanced_accuracy_same_reps':statistics.fmean(c['classification_balanced_accuracy_from_frozen_e1'] for c in group) if group else None})
write_csv('E2_method_budget_summary.csv',summaries,list(summaries[0]))
fig=make_subplots(rows=1,cols=2,subplot_titles=['300K rows','1M rows'])
colors={'gmm':'#1f77b4','copula':'#ff7f0e','arf':'#2ca02c','kde':'#d62728','chow_liu':'#9467bd'}
for i,budget in enumerate([300000,1000000],1):
 for method in primary:
  group=[x for x in point_rows if x['budget']==budget and x['method']==method]
  if not group:continue
  fig.add_trace(go.Scatter(x=[x['class_balanced_fidelity'] for x in group],y=[x['frozen_e1_balanced_accuracy'] for x in group],mode='markers+text',text=['r'+str(x['repetition']) for x in group],textposition='top center',name=method,legendgroup=method,showlegend=i==1,marker={'size':10,'color':colors[method]},customdata=[[x['repetition'],x['valid_class_reports']] for x in group],hovertemplate='method='+method+'<br>rep=%{customdata[0]}<br>fidelity=%{x:.4f}<br>E1 balanced accuracy=%{y:.4f}<br>valid class reports=%{customdata[1]}<extra></extra>'),row=1,col=i)
fig.update_xaxes(title_text='Class-balanced SDMetrics fidelity',row=1,col=1)
fig.update_xaxes(title_text='Class-balanced SDMetrics fidelity',row=1,col=2)
fig.update_yaxes(title_text='Frozen E1 balanced accuracy',row=1,col=1)
fig.update_layout(title='E2 fidelity versus direct classification, saved primary fits only; no pooled correlation',template='plotly_white')
fig.write_html(str(out/'E2_fidelity_vs_accuracy.html'),include_plotlyjs=True,full_html=True)
metadata={'summarized_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'primary_ready':audit['primary_counts']['ready'],'primary_completed':19,'classical_reference_completed':24,'class_reports':len(class_rows),'complete_five_family_strata':sum(x['five_family_status']=='complete' for x in correlations),'available_only_three_or_more_strata':sum(x['available_only_n']>=3 for x in correlations),'bootstrap':False,'TSTR':False,'interpretation':'Five-family Spearman is unavailable in every stratum because ARF/KDE or historical pipelines are missing. Available-only rho values are descriptive and have at most three families. No cross-budget pooling.'}
(out/'E2_PROGRESS_SUMMARY.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+chr(10))
note=f"""# E2 progress and evidence limits

As of {metadata['summarized_utc']}, E2 has {metadata['primary_completed']} fidelity-complete primary selected fits and {metadata['classical_reference_completed']} separately labeled classical reference fits. All {metadata['class_reports']} class reports were valid. These are reused frozen E1 selected models: no E1 refit/re-tune and no recovery models.

The primary grid has 150 planned budget/repetition/method cells. Artifact audit: 19 ready, 89 otherwise successful E1 cells missing historical selected pipelines, 40 E1 failures without a pipeline, and 2 E1 failed cells with a staged pipeline that lack valid frozen classification outcomes. Missing pipelines are artifact gaps, not model failures.

Fidelity uses the six native predictors, SDMetrics {audit['sdmetrics_version']} Quality Reports per class, and an equal average of all seven class scores. Real reference rows come only from frozen E1 calibration membership after model selection; each class has min(2000, available rows), with the same deterministic real IDs across methods at a budget/repetition. Generated samples use the frozen selected model and its original preprocessing. No test rows entered the fidelity reference frame. Column-shape and column-pair details and samples are saved per class.

No budget/repetition has all five primary methods available, so all 30 protocol five-family Spearman values are unavailable. Six strata have three available primary methods and an explicitly descriptive available-only rho. Do not pool budgets or claim a precise universal relationship. The four classical generators are a separate sensitivity set. Bootstrap was dropped at user request; TSTR belongs to E3 and was not run. Experiments 3-6 remain unauthorized.
"""
(out/'E2_PROGRESS.md').write_text(note)
print(json.dumps(metadata,sort_keys=True))
