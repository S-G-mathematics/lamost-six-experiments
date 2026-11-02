#!/usr/bin/env python3
"""Independent, read-only verification of already-saved E2 tables; no fitting/inference."""
import os
for env_key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"): os.environ[env_key]="1"
from pathlib import Path
import csv,json,math,hashlib,collections,datetime
from scipy.stats import spearmanr
ROOT=Path("/home/ubuntu/lamost_e1_migration_20261023")
RT=ROOT/"runtime_20261025";E2=ROOT/"e2_20261024"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 with p.open() as f:return list(csv.DictReader(f))
def key(x):return (x["budget"],x["repetition"],x["method"])
def num(x):
 try:v=float(x);return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None
def write(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+".tmp")
 with tmp.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["status"]);w.writeheader();w.writerows(rows)
 tmp.replace(p)
def main():
 names=("E2_all_generators_270.csv","E2_artifact_availability_270.csv","E2_all_class_reports_1596.csv","E2_within_stratum_descriptive_30.csv","E2_missing_primary_42.csv","E2_INTEGRITY_AUDIT.json","E2_RECONSTRUCTION_AMENDMENT.md","E2_CURRENT_REPORT.md","E2_combined_spearman_30.csv")
 paths=[E2/n for n in names]+[ROOT/"e1_wrapup_20261024/E1_frozen_cells_765.csv"]
 before={str(p):sha(p) for p in paths}
 allrows=read(paths[0]);availability=read(paths[1]);classes=read(paths[2]);correlations=read(paths[3]);missing=read(paths[4]);e1=read(paths[-1])
 issues=[]
 def check(ok,msg):
  if not ok:issues.append(msg)
 check(len(allrows)==270 and len({key(x) for x in allrows})==270,"E2 270 unique planned keys")
 check(len(availability)==270 and len({key(x) for x in availability})==270,"availability 270 unique keys")
 av={key(x):x for x in availability};original={key(x):x for x in e1}
 allkeys={key(x) for x in allrows};check(allkeys==set(av),"availability key set")
 check(len(e1)==765 and len(original)==765,"frozen E1 ledger 765 unique keys")
 differences=[];original_fit_exact=0;references_checked=0
 for x in allrows:
  k=key(x);a=num(x["balanced_accuracy"]);reference=num(original[k]["balanced_accuracy"]);aref=num(av[k]["e1_balanced_accuracy"])
  check(aref==reference,"E2 availability E1 BA mismatch: "+str(k));references_checked+=1
  if x["provenance"]=="original_saved_fit":
   check(a==reference and a is not None,"original saved-fit classification mismatch: "+str(k));original_fit_exact+=int(a==reference and a is not None)
  if x["provenance"]!="E2_reconstructed_fit":continue
  check(a is not None and reference is not None,"missing reconstruction/original BA: "+str(k))
  if a is None or reference is None:continue
  d=a-reference;exact=d==0
  expected="reproduced_original_test_balanced_accuracy" if exact else "classification_not_reproduced"
  check(x["reproduction_gate"]==expected,"reconstruction gate/difference mismatch: "+str(k))
  differences.append(dict(budget=k[0],repetition=k[1],method=k[2],family_set=x["family_set"],provenance=x["provenance"],frozen_E1_balanced_accuracy=reference,reconstructed_balanced_accuracy=a,signed_difference=d,absolute_difference=abs(d),exact_float_match=exact,recorded_gate=x["reproduction_gate"]))
 check(len(differences)==185,"185 reconstructed classifications")
 check(sum(x["exact_float_match"] for x in differences)==154,"154 exact reconstruction gates")
 check(sum(not x["exact_float_match"] for x in differences)==31,"31 nonzero reconstruction differences")
 check(original_fit_exact==43,"43 original saved-fit scores equal frozen E1")
 maxdiff=max((x["absolute_difference"] for x in differences),default=None)
 check(maxdiff is not None and abs(maxdiff-0.000031739351391335546)<1e-15,"maximum reconstruction difference")
 classgroups=collections.defaultdict(list)
 for x in classes:classgroups[key(x)].append(x)
 fidelity_checked=0
 for x in allrows:
  k=key(x);f=num(x["fidelity"]);g=classgroups.get(k,[])
  if f is None:
   check(not g,"class reports for unavailable cell: "+str(k));continue
  check(len(g)==7 and {z["class_id"] for z in g}=={str(j) for j in range(7)},"seven distinct classes: "+str(k))
  scores=[num(z["sdmetrics_score"]) for z in g]
  check(all(s is not None for s in scores),"missing class quality score: "+str(k))
  if len(scores)==7 and all(s is not None for s in scores):
   check(abs(math.fsum(scores)/7-f)<1e-12,"equal-class fidelity mean mismatch: "+str(k));fidelity_checked+=1
  for z in g:
   a,b=num(z["column_shapes_score"]),num(z["column_pair_trends_score"])
   check(a is not None and b is not None and abs((a+b)/2-num(z["sdmetrics_score"]))<1e-12,"quality component mean mismatch: "+str(k)+"/"+z["class_id"])
   check(z["status"] in {"valid","valid_low_precision"} and int(z["diagnostic_n"])>0,"invalid diagnostic class status/count")
   check((z["status"]=="valid_low_precision")==(int(z["diagnostic_n"])<20),"low-precision flag/n threshold mismatch: "+str(k)+"/"+z["class_id"])
 check(len(classes)==1596 and len(classgroups)==228,"1596 reports across228 evaluated cells")
 low=sum(z["status"]=="valid_low_precision" for z in classes);check(low==210,"210 low-precision class reports retained")
 primary=[x for x in allrows if x["family_set"]=="primary"];reference_rows=[x for x in allrows if x["family_set"]!="primary"]
 check(len(primary)==150 and sum(num(x["fidelity"]) is not None and num(x["balanced_accuracy"]) is not None for x in primary)==108,"108/150 primary coverage")
 check(len(reference_rows)==120 and all(num(x["fidelity"]) is not None and num(x["balanced_accuracy"]) is not None for x in reference_rows),"120/120 classical references")
 unavailable=[x for x in primary if num(x["fidelity"]) is None or num(x["balanced_accuracy"]) is None]
 check(len(unavailable)==42 and {key(x) for x in unavailable}=={key(x) for x in missing},"42 missing primary key identities")
 strata=collections.defaultdict(list)
 for x in primary:
  if num(x["fidelity"]) is not None and num(x["balanced_accuracy"]) is not None:strata[(x["budget"],x["repetition"])].append(x)
 corrrows=[]
 combined={(x["budget"],x["repetition"]):x for x in read(E2/"E2_combined_spearman_30.csv")}
 for c in correlations:
  k=(c["budget"],c["repetition"]);g=sorted(strata[k],key=lambda x:x["method"]);n=len(g)
  rho=float(spearmanr([float(x["fidelity"]) for x in g],[float(x["balanced_accuracy"]) for x in g]).statistic) if n>=2 else None
  complete=n==5 and {x["method"] for x in g}=={"gmm","copula","arf","kde","chow_liu"}
  stored=num(c["full_five_family_spearman"]);exploratory=num(c["available_only_spearman_exploratory"])
  check(int(c["paired_primary_families"])==n,"correlation available-n mismatch: "+str(k))
  check((c["protocol_full_five_family"]=="True")==complete,"complete-stratum indicator mismatch: "+str(k))
  check((stored is not None)==complete,"primary correlation availability mismatch: "+str(k))
  if complete:
   check(stored is not None and rho is not None and abs(stored-rho)<1e-12,"complete-stratum Spearman mismatch: "+str(k))
   check(exploratory is None,"exploratory field should stay separate/blank for complete primary stratum: "+str(k))
  else:check(exploratory is not None and rho is not None and abs(exploratory-rho)<1e-12,"exploratory within-stratum Spearman mismatch: "+str(k))
  cc=combined.get(k,{})
  check(int(cc.get("paired_families",-1))==n,"combined correlation available-n mismatch: "+str(k))
  crho=num(cc.get("full_five_family_spearman"))
  check((crho is not None)==complete,"combined primary correlation availability mismatch: "+str(k))
  if complete:check(crho is not None and rho is not None and abs(crho-rho)<1e-12,"combined complete-stratum Spearman mismatch: "+str(k))
  corrrows.append(dict(budget=k[0],repetition=k[1],available_primary_families=n,methods=";".join(x["method"] for x in g),primary_complete_five=complete,recomputed_primary_rho=rho if complete else "",recorded_primary_rho=stored if stored is not None else "",exploratory_available_only_rho=rho if not complete else "",recorded_exploratory_available_only_rho=exploratory if exploratory is not None else ""))
 check(len(correlations)==30 and len({(x["budget"],x["repetition"]) for x in correlations})==30,"30 unique budget/repetition strata")
 check(sum(x["primary_complete_five"] for x in corrrows)==4,"4 complete five-family strata")
 after={str(p):sha(p) for p in paths};check(before==after,"source tables changed during read-only audit")
 write(RT/"reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv",differences);write(RT/"reports/E2_CORRELATIONS_INDEPENDENTLY_VERIFIED.csv",corrrows)
 doc=dict(generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),purpose="Independent verification of saved E2 evidence; no fits, generation, tuning, inference or new campaign",source_sha256_before=before,source_sha256_after=after,sources_unchanged=before==after,script_sha256=sha(Path(__file__)),planned_primary=len(primary),evaluated_primary=sum(num(x['fidelity']) is not None and num(x['balanced_accuracy']) is not None for x in primary),unavailable_primary=len(unavailable),classical_reference_evaluated=sum(num(x['fidelity']) is not None and num(x['balanced_accuracy']) is not None for x in reference_rows),total_evaluated=sum(num(x['fidelity']) is not None and num(x['balanced_accuracy']) is not None for x in allrows),original_saved_fit_scores_verified=original_fit_exact,E1_reference_rows_checked=references_checked,reconstructed=len(differences),exact_accuracy_matches=sum(x['exact_float_match'] for x in differences),nonzero_accuracy_differences=sum(not x['exact_float_match'] for x in differences),max_absolute_reconstruction_difference=maxdiff,equal_class_means_verified=fidelity_checked,class_reports=len(classes),low_precision_class_reports_retained=low,complete_five_family_strata=sum(x["primary_complete_five"] for x in corrrows),total_strata=len(corrrows),all_correlations_within_budget_repetition=True,bootstrap=False,significance_claims=False,issue_count=len(issues),issues=issues,historical_table_note="E2_spearman_within_budget_repetition.csv is the earlier saved-fit-only stage. This audit uses the combined and within-stratum tables named by E2_CURRENT_REPORT.md.",scope_limitations="Exact accuracy equality does not establish original model identity or per-row prediction equality. Verifies already-saved numerical tables and their frozen E1 links; does not restore historical pipelines/predictions, rerun SDMetrics, or certify original membership sampling independently of existing integrity evidence.")
 p=RT/"reports/engineering_audits/E2_saved_tables_independent_reaudit_20261025.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(doc,indent=2)+"\n")
 print(json.dumps({k:v for k,v in doc.items() if not k.startswith("source_") and k!="scope_limitations"},indent=2))
 return 0 if not issues else 2
if __name__=="__main__":raise SystemExit(main())
