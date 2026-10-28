import csv,json,pathlib,datetime,collections
import pandas as pd
import plotly.express as px
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e2_20261024')
audit=list(csv.DictReader((B/'E2_artifact_availability_270.csv').open(newline='')))
rows=[];classes=[]
for a in audit:
 b=int(a['budget']);r=int(a['repetition']);m=a['method']
 p=B/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json';origin='original_saved_fit'
 if not p.exists():
  p=B/'reconstruction_fidelity'/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json';origin='E2_reconstructed_fit'
 z=json.loads(p.read_text()) if p.exists() else {}
 rows.append({'family_set':a['family_set'],'budget':b,'repetition':r,'method':m,'provenance':origin if z else 'unavailable','fidelity':z.get('class_balanced_fidelity'),'balanced_accuracy':z.get('direct_classification_balanced_accuracy',z.get('classification_balanced_accuracy_from_frozen_e1')),'fidelity_status':z.get('status','unavailable'),'reproduction_gate':z.get('reproduction_gate_status','not_applicable'),'classification_source':z.get('classification_source','frozen_E1' if origin=='original_saved_fit' else 'unavailable')})
 for c in z.get('class_reports',[]):
  classes.append({'family_set':a['family_set'],'budget':b,'repetition':r,'method':m,'provenance':origin,'class_id':c['class_id'],'status':c['status'],'diagnostic_n':c['diagnostic_n'],'sdmetrics_score':c.get('sdmetrics_score'),'column_shapes_score':c.get('column_shapes_score'),'column_pair_trends_score':c.get('column_pair_trends_score')})
df=pd.DataFrame(rows);cl=pd.DataFrame(classes)
assert len(df)==270 and df.fidelity.notna().sum()==228 and len(cl)==1596
df.to_csv(B/'E2_all_generators_270.csv',index=False)
cl.to_csv(B/'E2_all_class_reports_1596.csv',index=False)
g=df.groupby(['family_set','budget','method'],sort=True).agg(paired_repetitions=('fidelity','count'),mean_fidelity=('fidelity','mean'),mean_balanced_accuracy=('balanced_accuracy','mean')).reset_index()
g.to_csv(B/'E2_all_method_budget_summary.csv',index=False)
p=df[(df.family_set=='primary') & df.fidelity.notna()].copy()
p['budget_label']=p.budget.map({3000:'3k',10000:'10k',30000:'30k',100000:'100k',300000:'300k',1000000:'1m'})
fig=px.scatter(p,x='fidelity',y='balanced_accuracy',color='method',symbol='provenance',facet_col='budget_label',facet_col_wrap=3,hover_data=['repetition','reproduction_gate'],title='E2 generator fidelity versus direct classification')
fig.update_layout(height=850,width=1350)
fig.write_html(B/'E2_combined_fidelity_vs_accuracy.html',include_plotlyjs=True)
strata=pd.read_csv(B/'E2_combined_spearman_30.csv');full=strata[strata.status=='full_five_family']
gates=collections.Counter(x['reproduction_gate'] for x in rows if x['provenance']=='E2_reconstructed_fit')
states=collections.Counter(cl.status)
lines=['# Experiment 2 current report','',f"Updated: {datetime.datetime.now(datetime.timezone.utc).isoformat()} (UTC).",'','## Results','',
'Primary grid: **108/150** paired fidelity and direct classification cells (19 original saved selected fits; 89 reconstructed selected fits). The remaining 42 primary cells failed frozen E1 and have no valid selected classification outcome.','',
'Separate classical generative reference set: **120/120** paired cells (24 original saved fits; 96 reconstructed fits). It is not part of the five-family primary rank comparison.','',
f"Saved per-class Quality Reports: **{len(cl)}**, seven per evaluated fit. Class report statuses: {dict(states)}.",'',
'Each class uses the six native predictors and a fixed calibration-role reference, with matched generated/real diagnostic sizes capped at 2,000. Seven SDMetrics 0.32.0 scores are averaged equally.','',
'## Complete primary five-family strata','',
f"**{len(full)}/30** budget/repetition strata have all five primary generators:",'',
'| Budget | Repetition | Spearman rho |','|---:|---:|---:|']
for _,x in full.iterrows():lines.append(f"| {int(x.budget):,} | {int(x.repetition)} | {x.full_five_family_spearman:.3f} |")
lines+=['','These correlations are descriptive within each stratum. The other 26 five-family comparisons are unavailable, mostly because ARF or KDE had no successful E1 selected outcome at larger budgets. No cross-budget correlation is claimed.','',
'## Provenance','',
'At user request, missing saved models from successful E1 cells were reconstructed on EC2 using original fit-role IDs, selected parameters, preprocessing and seed formula. No retuning occurred. Each reconstructed fit uses its own fixed-test balanced accuracy in E2; E1 results were not overwritten. Original saved fits and reconstructed fits remain marked separately.','',
f"Reconstruction equality gate versus frozen E1 balanced accuracy, absolute tolerance 1e-10: {dict(gates)}.",'',
'The frozen E1 ledger and recovery cutoff are unchanged. No bootstrap, test-based model selection, TSTR, or Experiment 3-6 runs were performed.','',
'## Deliverables','',
'See E2_all_generators_270.csv, E2_all_class_reports_1596.csv, E2_all_method_budget_summary.csv, E2_combined_spearman_30.csv, and E2_combined_fidelity_vs_accuracy.html. Full cell-level samples, Quality Report details, and pipelines remain in the EC2 E2 directory.','']
(B/'E2_CURRENT_REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'primary_paired':108,'reference_paired':120,'class_reports':len(cl),'complete_five_family_strata':len(full),'reconstruction_gates':dict(gates),'class_statuses':dict(states)}))
