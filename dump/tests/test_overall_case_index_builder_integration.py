import csv,json,shutil,sqlite3,subprocess,tempfile,unittest
from pathlib import Path
BASE=Path('/home/ubuntu/lamost_e1_migration_20261023')
R=BASE/'runtime_20261025'
STAGE=R/'source'
BUILDER=STAGE/'build_overall_case_index.py'
def read_rows(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
class CaseIndexBuilderIntegrationTests(unittest.TestCase):
 def test_versioned_cli_uses_current_sqlite_outcomes_and_manifest_budgets(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'project';rt=root/'runtime_20261025'
   for rel in ['e1_wrapup_20261024','e2_20261024','runtime_20261025/reports','runtime_20261025/source','runtime_20261025/manifests']:
    (root/rel).mkdir(parents=True,exist_ok=True)
   for src,dst in [
    (BASE/'e1_wrapup_20261024/E1_frozen_cells_765.csv',root/'e1_wrapup_20261024/E1_frozen_cells_765.csv'),
    (BASE/'e1_wrapup_20261024/E1_recovery_cutoff_91.csv',root/'e1_wrapup_20261024/E1_recovery_cutoff_91.csv'),
    (BASE/'e2_20261024/E2_all_generators_270.csv',root/'e2_20261024/E2_all_generators_270.csv'),
    (BASE/'e2_20261024/E2_artifact_availability_270.csv',root/'e2_20261024/E2_artifact_availability_270.csv'),
    (BASE/'e2_20261024/E2_missing_primary_42.csv',root/'e2_20261024/E2_missing_primary_42.csv'),
    (R/'reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv',rt/'reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv'),
    (R/'source/reason_text_curation.py',rt/'source/reason_text_curation.py'),
    (R/'master_index.json',rt/'master_index.json')]:shutil.copy2(src,dst)
   for e in (3,4,5,6):shutil.copy2(R/f'manifests/E{e}_MANIFEST.json',rt/f'manifests/E{e}_MANIFEST.json')
   src=sqlite3.connect(f'file:{R/"registry.sqlite"}?mode=ro',uri=True);src.execute('BEGIN')
   records=[(k,raw) for k,raw in src.execute('select key,record from tasks order by key')]
   src.execute('ROLLBACK');src.close()
   changed=False;new=[]
   for key,raw in records:
    t=json.loads(raw)
    if not changed and t.get('experiment')==3 and t.get('scientific_case') and t.get('outcome')=='successful':
     t['outcome']='scientific_failure';raw=json.dumps(t,sort_keys=True,separators=(',',':'));changed=True
    new.append((key,raw))
   self.assertTrue(changed)
   db=sqlite3.connect(rt/'registry.sqlite');db.execute('create table tasks(key text primary key,record text not null)')
   db.executemany('insert into tasks values(?,?)',new);db.commit();db.close()
   out=rt/'reports/overall_case_index/fixture_refresh'
   subprocess.run(['/usr/bin/python3',str(BUILDER),'--root',str(root),'--runtime',str(rt),'--output',str(out)],check=True,capture_output=True,text=True)
   summary=json.loads((out/'OVERALL_SCIENTIFIC_CASE_INDEX_SUMMARY.json').read_text())
   self.assertEqual(summary['later_current_status_counts']['3']['successful'],63)
   self.assertEqual(summary['later_current_status_counts']['3']['scientific_failure'],4)
   self.assertEqual(summary['master_scientific_case_status_mismatches_diagnostic_only'],1)
   self.assertEqual(summary['main_scientific_case_rows'],3858)
   self.assertTrue((rt/'reports/overall_case_index/CURRENT.json').is_file())
   rows=read_rows(out/'OVERALL_SCIENTIFIC_CASE_INDEX.csv')
   for e in ('3','4','5','6'):
    self.assertEqual({x['budget'] for x in rows if x['experiment']==e},{'100000'})
   alias=next(x for x in rows if x['task_kind']=='alias')
   self.assertTrue(alias['model_provenance'].startswith('evaluation_alias_of:'))
   self.assertNotIn('pid',alias['resource_profile_json'].lower())
   stage_out=rt/'staging/overall_case_index_20261026/fixture_refresh'
   subprocess.run(['/usr/bin/python3',str(BUILDER),'--root',str(root),'--runtime',str(rt),'--output',str(stage_out)],check=True,capture_output=True,text=True)
   self.assertTrue((rt/'staging/overall_case_index_20261026/CURRENT.json').is_file())
   denied=Path(td)/'outside_output'
   result=subprocess.run(['/usr/bin/python3',str(BUILDER),'--root',str(root),'--runtime',str(rt),'--output',str(denied)],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertFalse(denied.exists())
if __name__=='__main__':unittest.main()

