import csv,hashlib,json,pathlib,collections,datetime,importlib.metadata,joblib
base=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
root=base/'project'
import sys
sys.path.insert(0,str(root))
out=base/'e2_20261024';out.mkdir(exist_ok=True)
report=json.loads((root/'benchmark/results/e1_report_validated_no_bootstrap.json').read_text())
lookup={(c['budget'],c['repetition'],c['method']):c for c in report['cells']}
budgets=[3000,10000,30000,100000,300000,1000000]
primary=['gmm','copula','arf','kde','chow_liu']
reference=['gaussian_nb','shared_diagonal','lda','qda']
rows=[]
for budget in budgets:
 for rep in range(1,6):
  for method in primary+reference:
   c=lookup[(budget,rep,method)]
   cell=root/'benchmark/results/e1'/f'rep_{rep}'/f'n_{budget}'/method
   pipe=cell/'pipeline.joblib'
   done=cell/'complete.json'
   pred=cell/'test_predictions.npz'
   role=cell/'role_positions.npz'
   if c['classification']=='successful_test_evaluation':
    status='ready' if pipe.exists() and role.exists() else 'missing_historical_pipeline'
   elif pipe.exists():
    status='e1_failure_pipeline_present_not_primary'
   else:
    status='e1_terminal_failure_or_unsupported'
   row={'budget':budget,'repetition':rep,'method':method,'family_set':'primary' if method in primary else 'classical_reference','e1_classification':c['classification'],'e1_status':c['status'],'pipeline_available':pipe.exists(),'pipeline_bytes':pipe.stat().st_size if pipe.exists() else None,'saved_test_predictions_available':pred.exists(),'roles_available':role.exists(),'e2_availability':status,'e1_balanced_accuracy':(c.get('metrics') or {}).get('balanced_accuracy'),'path':str(cell)}
   if status=='ready':
    obj=joblib.load(pipe)
    assert all(x in obj for x in ['model','imputer','scaler','params'])
    assert hasattr(obj['model'],'sample_class') or method in reference
    selected=json.loads(done.read_text())['selected_params']
    assert obj['params']==selected,(budget,rep,method)
    row['pipeline_sha256']=hashlib.sha256(pipe.read_bytes()).hexdigest()
    row['selected_params_match']=True
   rows.append(row)
assert len(rows)==270
fields=list(rows[0])+['pipeline_sha256','selected_params_match']
with (out/'E2_artifact_availability_270.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
counts={}
for kind in ['primary','classical_reference']:
 subset=[r for r in rows if r['family_set']==kind]
 counts[kind]=dict(collections.Counter(r['e2_availability'] for r in subset))
by_budget={}
for budget in budgets:
 subset=[r for r in rows if r['budget']==budget and r['family_set']=='primary']
 by_budget[str(budget)]={m:sum(r['e2_availability']=='ready' for r in subset if r['method']==m) for m in primary}
metadata={'audited_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'primary_counts':counts['primary'],'classical_reference_counts':counts['classical_reference'],'primary_ready_by_budget_method':by_budget,'sdmetrics_version':importlib.metadata.version('sdmetrics'),'primary_total':150,'reference_total':120,'artifact_policy':'Only complete frozen E1 cells with saved selected pipeline and roles are ready; recovery pipelines excluded; missing historical pipelines are artifact gaps, not algorithm failures.'}
(out/'E2_artifact_availability_summary.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+chr(10))
print(json.dumps(metadata,sort_keys=True))
