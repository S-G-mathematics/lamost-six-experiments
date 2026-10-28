import csv,hashlib,json,pathlib,collections,math
import numpy as np,pandas as pd
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
E=B/'e2_20261024'
audit=list(csv.DictReader((E/'E2_artifact_availability_270.csv').open(newline='')))
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return h.hexdigest()
errors=[];counts=collections.Counter();gate_diff=[];low=[]
split=pd.read_parquet(B/'project/lamost_baseline/data/splits.parquet')
split_col=next(c for c in ('reference_partition','partition','split') if c in split.columns)
test_ids=set(split.loc[split[split_col].astype(str).str.lower().eq('test'),'sample_id'].tolist())
del split
for a in audit:
 b=int(a['budget']);r=int(a['repetition']);m=a['method'];key=f'{b}/{r}/{m}'
 original=E/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json'
 recon=E/'reconstruction_fidelity'/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json'
 if original.exists():p=original;source='original'
 elif recon.exists():p=recon;source='reconstructed'
 else:
  counts['unavailable']+=1;continue
 z=json.loads(p.read_text());counts[source]+=1
 cls=z.get('class_reports',[])
 if len(cls)!=7:errors.append(key+': class count')
 vals=[]
 for c in cls:
  cid=c['class_id'];status=c['status'];counts['class_'+status]+=1
  if status not in ('valid','valid_low_precision'):errors.append(key+': class status '+status)
  n=c['diagnostic_n']
  if status=='valid_low_precision':low.append((b,r,m,cid,n))
  if (status=='valid_low_precision')!=(n<20):errors.append(key+': low precision flag mismatch')
  vals.append(c.get('sdmetrics_score'))
  class_dir=p.parent/f'class_{cid}'
  diag=class_dir/'diagnostic_samples.npz'
  if not diag.exists():errors.append(key+': missing diagnostic '+str(cid));continue
  if sha(diag)!=c.get('synthetic_sample_sha256'):errors.append(key+': diagnostic hash '+str(cid))
  with np.load(diag) as zz:
   ids=zz['real_sample_id']
   if len(ids)!=n or zz['real_native'].shape!=(n,6) or zz['synthetic_native'].shape!=(n,6):errors.append(key+': diagnostic shape '+str(cid))
   if any(int(v) in test_ids for v in ids):errors.append(key+': test ID in reference '+str(cid))
  refroot=E/'references' if source=='original' else E/'reconstruction_fidelity'/'references'
  ref=refroot/f'n_{b}'/f'rep_{r}'/f'class_{cid}_ids.npz'
  with np.load(ref) as rr:
   if not np.array_equal(ids,rr['sample_id']):errors.append(key+': reference ID mismatch '+str(cid))
 if vals and not math.isclose(sum(vals)/7,z['class_balanced_fidelity'],rel_tol=0,abs_tol=1e-12):errors.append(key+': mean fidelity mismatch')
 if z.get('direct_classification_balanced_accuracy') is None:errors.append(key+': missing paired BA')
 if source=='reconstructed':
  gp=E/'reconstruction'/f'n_{b}'/f'rep_{r}'/m
  g=json.loads((gp/'test_reproduction_gate.json').read_text())
  if g['status'] not in ('reproduced_original_test_balanced_accuracy','classification_not_reproduced'):errors.append(key+': bad gate')
  if not math.isclose(z['direct_classification_balanced_accuracy'],g['reconstructed_balanced_accuracy'],rel_tol=0,abs_tol=1e-12):errors.append(key+': paired BA mismatch')
  if z.get('classification_balanced_accuracy_from_frozen_e1') is not None:errors.append(key+': misleading frozen BA')
  if sha(gp/'pipeline.joblib')!=z['source_pipeline_sha256']:errors.append(key+': pipeline hash mismatch')
  gate_diff.append((b,r,m,g['absolute_difference'],g['status']))
 else:
  if not math.isclose(z['direct_classification_balanced_accuracy'],float(a['e1_balanced_accuracy']),rel_tol=0,abs_tol=1e-12):errors.append(key+': original BA mismatch')
for b in [3000,10000,30000,100000,300000,1000000]:
 for r in range(1,6):
  for c in range(7):
   x=E/'references'/f'n_{b}'/f'rep_{r}'/f'class_{c}_ids.npz'
   y=E/'reconstruction_fidelity'/'references'/f'n_{b}'/f'rep_{r}'/f'class_{c}_ids.npz'
   if x.exists() and y.exists():
    with np.load(x) as xx,np.load(y) as yy:
     if not np.array_equal(xx['sample_id'],yy['sample_id']):errors.append(f'{b}/{r}/class{c}: cross-provenance reference mismatch')
summary={'evaluated_cells':counts['original']+counts['reconstructed'],'original_cells':counts['original'],'reconstructed_cells':counts['reconstructed'],'unavailable_cells':counts['unavailable'],'class_valid':counts['class_valid'],'class_valid_low_precision':counts['class_valid_low_precision'],'low_precision_by_budget_class':{f'{b}/class_{c}':sum(x[0]==b and x[3]==c for x in low) for b,c in sorted(set((x[0],x[3]) for x in low))},'reconstruction_gate_exact':sum(x[4]=='reproduced_original_test_balanced_accuracy' for x in gate_diff),'reconstruction_gate_mismatch':sum(x[4]=='classification_not_reproduced' for x in gate_diff),'reconstruction_gate_max_abs_BA_difference':max((x[3] for x in gate_diff),default=None),'integrity_errors':errors}
(E/'E2_INTEGRITY_AUDIT.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='low_precision_by_budget_class'}))
