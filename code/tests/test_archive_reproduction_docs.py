import importlib.util,tempfile,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'source'
spec=importlib.util.spec_from_file_location('staged_finalizer',BASE/'finalize_project.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def test_collect_small_generated_docs():
 old_small=m.small_report_files;old_iter=m.iterfiles;old_inc=m._small_e3_incident_summary
 m.small_report_files=lambda _:[];m.iterfiles=lambda *a,**k:[];m._small_e3_incident_summary=lambda *a,**k:None
 try:
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);runtime=root/'runtime_20261025';runtime.mkdir()
   full={'path':'/ec2/packages/full.zip','bytes':123,'sha256':'abc'}
   entries=m._small_entries(root,runtime,full,None,'/ec2/packages/small.zip')
   docs={e.member:e.source for e in entries}
   loc=docs['FULL_ARCHIVE_LOCATION.md'].decode()
   repro=docs['RUN_RESUME_REPRODUCE.md'].decode()
   assert '\\n' not in loc and '\\n' not in repro
   assert 'Full archive on EC2:' in loc and '\nSize: 123 bytes\n' in loc
   assert 'scp w7-ec2:/ec2/packages/small.zip "D:\\LAMOST_Overall_EC2_Handoff_20261023"' in loc
   assert '**Archive safety:**' in repro and '\n\nThe full archive includes' in repro
   assert 'Do not initialize, watchdog, or resume' in repro and 'retained controller SQLite state' in repro
   assert 'report_cli.py' in repro
 finally:
  m.small_report_files=old_small;m.iterfiles=old_iter;m._small_e3_incident_summary=old_inc
def test_actual_package_readme():
 doc=m.package_readme('/ec2/packages/full.zip',{'e1_archive':{'path':'/ec2/packages/e1.zip','sha256':'def'}}).decode()
 assert '\\n' not in doc and '\n\nCreated ' in doc
 assert '**Archive safety:**' in doc and 'not the controller database' in doc
 assert 'Do not initialize, watchdog, or resume' in doc and 'do not rerun terminal cells' in doc
 assert 'runtime_20261025/registry.json' in doc
if __name__=='__main__':
 test_collect_small_generated_docs();test_actual_package_readme();print('2 generated-document integration checks passed')
