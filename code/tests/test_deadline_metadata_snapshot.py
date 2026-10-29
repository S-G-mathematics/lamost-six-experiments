import importlib.util,sqlite3,tempfile,unittest
from pathlib import Path
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025'
P=R/'staging/deadline_reporting_20261029/deadline_snapshot_runner.py'
spec=importlib.util.spec_from_file_location('deadline_snapshot_runner_under_test',P)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class MetadataSnapshotTests(unittest.TestCase):
 def test_captures_all_dag_rows_but_counts_only_scientific_rows(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'registry.sqlite';c=sqlite3.connect(db);c.execute('create table tasks(key text,record text)')
   rows=[
    ('e4/a',{'key':'e4/a','scientific_case':True,'experiment':4,'status':'successful','outcome':'successful'}),
    ('fit/a',{'key':'fit/a','scientific_case':False,'experiment':4,'kind':'fit','status':'successful','outcome':'successful','pid':999}),
    ('eval/a',{'key':'eval/a','scientific_case':False,'experiment':4,'kind':'evaluation','status':'user_stopped','outcome':'user_stopped'}),
   ]
   import json
   c.executemany('insert into tasks values (?,?)',[(k,json.dumps(v)) for k,v in rows]);c.commit();c.close()
   snap,n=mod.capture_registry(db,now_fn=lambda:'2026-10-29T10:00:00+00:00')
   self.assertEqual(n,3);self.assertEqual(len(snap['tasks']),3)
   self.assertEqual(sum(bool(x.get('scientific_case')) for x in snap['tasks']),1)
   self.assertNotIn('pid',snap['tasks'][1])
   self.assertEqual(snap['scientific_counts'],{'4':{'successful':1}})
 def test_metadata_copies_bind_canonical_paths_and_reject_drift(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);source=root/'source';target=root/'copy'
   rels=('manifests/tasks.json','manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json','reports/deadline_submission_20261029/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md')
   for rel in rels:
    p=source/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(rel.encode())
   records=mod.snapshot_metadata_inputs(source,target)
   self.assertEqual(len(records),4);mod.verify_metadata_inputs(source,target,records)
   self.assertEqual(mod.canonical_amendment_source_path(source),(source/rels[1]).resolve())
   (source/rels[0]).write_bytes(b'drift')
   with self.assertRaises(RuntimeError):mod.verify_metadata_inputs(source,target,records)
if __name__=='__main__':unittest.main()
