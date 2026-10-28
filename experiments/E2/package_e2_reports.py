import datetime,hashlib,json,pathlib,zipfile
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
E=B/'e2_20261024'
P=B/'packages';P.mkdir(exist_ok=True)
name='LAMOST_E2_REPORTS_TABLES_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip'
out=P/name
files=['E2_CURRENT_REPORT.md','E2_RECONSTRUCTION_AMENDMENT.md','E2_all_generators_270.csv','E2_all_class_reports_1596.csv','E2_all_method_budget_summary.csv','E2_combined_points_150.csv','E2_combined_spearman_30.csv','E2_combined_summary.json','E2_combined_fidelity_vs_accuracy.html','E2_artifact_availability_270.csv','E2_artifact_availability_summary.json','E2_reconstruction_progress_89.csv','E2_reconstruction_progress.json','E2_INTEGRITY_AUDIT.json','E2_missing_primary_42.csv','E2_within_stratum_descriptive_30.csv','audit_e2_integrity.py','extend_e2_report.py','E2_CONFIG.json','finalize_e2_report.py','run_e2_fidelity.py','reconstruct_missing.py','validate_reconstruction.py']
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for n in files:
  p=E/n
  if not p.exists():raise FileNotFoundError(p)
  z.write(p,arcname=n)
 z.write(B/'project/benchmark/protocol_source.txt',arcname='protocol_source.txt')
with zipfile.ZipFile(out) as z:
 bad=z.testzip();count=len(z.namelist())
 if bad:raise RuntimeError('ZIP CRC error: '+bad)
h=hashlib.sha256()
with out.open('rb') as f:
 for x in iter(lambda:f.read(1<<20),b''):h.update(x)
print(json.dumps({'path':str(out),'size_bytes':out.stat().st_size,'sha256':h.hexdigest(),'entries':count,'zip_crc':'passed'}))
