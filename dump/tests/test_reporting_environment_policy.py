import csv, json, os, pathlib, tempfile, types, unittest
from test_label_rate_gate import valid_rows, write_table
from unittest import mock
import finalize_project as f
import reporting
HERE=pathlib.Path(__file__).resolve().parents[1]
EXPECTED={'3':69,'4':1773,'5':960,'6':21}

class ReportingEnvironmentPolicyTests(unittest.TestCase):
 def test_report_cli_uses_recorded_venv_and_ordered_overlay(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);runtime=root/'runtime_20261025';reports=runtime/'reports';reports.mkdir(parents=True)
   (root/'venv'/'bin').mkdir(parents=True);python=root/'venv'/'bin'/'python';python.touch()
   (runtime/'source').mkdir();script=runtime/'source'/'report_cli.py';script.touch()
   capture={}
   def fake_run(args,**kwargs):
    capture.update(args=args,kwargs=kwargs)
    result={'status':'success','planned_scientific_cases':sum(EXPECTED.values()),'figure_paths':[],'evidence_table_counts':{'E5_label_noise_source_class_rate_rows':63}}
    (reports/'report_result.json').write_text(json.dumps(result))
    required=('all_task_ledger.csv','planned_case_ledger.csv','experiment_outcome_coverage.csv','per_repetition_metrics.csv','per_class_metrics.csv','matched_paired_differences.csv','matched_paired_summary.csv','dataset_inventory.csv','E4_class_histograms.csv','E5_corruption_realization_summary.csv','label_transition_counts.csv','E5_label_noise_source_class_rates.csv','model_selection_ledger.csv','evaluation_support_fallbacks.csv','evaluation_support_fallbacks_per_class.csv','E6_weights.csv','E6_candidate_ledger.csv','resource_failure_ledger.csv','resource_failure_summary.csv','terminal_trial_cutoffs.csv','terminal_trial_cutoffs.json','figure_denominators.csv','E3_SHARED_REAL_PAIRED.csv','E4_CONTROL_TREATMENT_PAIRED.csv','E5_CLEAN_CORRUPTED_PAIRED.csv','E6_ENSEMBLE_MEMBER_PAIRED.csv')
    for name in required:
     path=reports/name
     if name=='planned_case_ledger.csv':
      with path.open('w',newline='') as out:
       writer=csv.DictWriter(out,fieldnames=['experiment','outcome']);writer.writeheader()
       for experiment,count in EXPECTED.items():
        writer.writerows({'experiment':experiment,'outcome':'successful'} for _ in range(count))
     elif name=='E5_label_noise_source_class_rates.csv':write_table(path,valid_rows())
     elif name.endswith('.json'):path.write_text('{}\n')
     else:path.write_text('fixture\n')
    return types.SimpleNamespace(returncode=0,stderr='')
   with mock.patch.object(f.subprocess,'run',side_effect=fake_run), mock.patch.object(f,'figure_denominators',return_value=[]), mock.patch.object(f,'expanded_pairs',return_value={}):
    validated=f.report_cli_and_validate(root,runtime,{})
   self.assertEqual(validated['validated_E5_label_noise_source_class_rate_rows'],63)
   self.assertIn('E5_label_noise_source_class_rates.csv',validated['required_csvs'])
   self.assertEqual(capture['args'],[str(python),str(script)])
   env=capture['kwargs']['env']
   expected=[root/'venv'/'lib'/'python3.12'/'site-packages',pathlib.Path('/home/ubuntu/.local/lib/python3.12/site-packages'),pathlib.Path('/usr/lib/python3/dist-packages')]
   self.assertEqual(env['PYTHONPATH'],os.pathsep.join(map(str,expected)))
   self.assertEqual(env['MPLBACKEND'],'Agg')
   for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):self.assertEqual(env[name],'1')

 def test_finalizer_figure_import_uses_frozen_numpy_site_first(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);runtime=root/'runtime_20261025';reports=runtime/'reports';reports.mkdir(parents=True)
   overlay=[root/'venv'/'lib'/'python3.12'/'site-packages',pathlib.Path('/home/ubuntu/.local/lib/python3.12/site-packages'),pathlib.Path('/usr/lib/python3/dist-packages')]
   for path in overlay[:1]:path.mkdir(parents=True)
   before=list(__import__('sys').path);captured={}
   original_import=__import__
   def stop_at_matplotlib(name,*args,**kwargs):
    if name=='matplotlib':
     captured['path']=__import__('sys').path[:3]
     raise ImportError('fixture captures plotting import path')
    return original_import(name,*args,**kwargs)
   try:
    with mock.patch('builtins.__import__',side_effect=stop_at_matplotlib):
     with self.assertRaisesRegex(ImportError,'captures plotting import path'):f.figure_denominators(reports)
    self.assertEqual(captured['path'],list(map(str,overlay)))
   finally:
    __import__('sys').path[:]=before

 def test_static_plot_subprocess_receives_same_ordered_overlay(self):
  original_import=__import__
  def no_matplotlib(name,*args,**kwargs):
   if name=='matplotlib':raise ImportError('fixture forces plotting fallback')
   return original_import(name,*args,**kwargs)
  captured={}
  def fake_run(args,**kwargs):
   captured.update(args=args,kwargs=kwargs)
   return types.SimpleNamespace(returncode=0,stdout='[]\n')
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);source=root/'runtime_20261025'/'source';source.mkdir(parents=True)
   fake_site=root/'venv'/'lib'/'python3.12'/'site-packages';fake_site.mkdir(parents=True)
   out=root/'reports'
   with mock.patch('builtins.__import__',side_effect=no_matplotlib),mock.patch.object(reporting,'__file__',str(source/'reporting.py')),mock.patch.object(reporting.subprocess,'run',side_effect=fake_run):
    result=reporting._figures(root/'runtime_20261025',out,[])
   self.assertEqual(result,[])
   self.assertEqual(captured['args'][0],'/usr/bin/python3')
   env=captured['kwargs']['env']
   expected=[fake_site,pathlib.Path('/home/ubuntu/.local/lib/python3.12/site-packages'),pathlib.Path('/usr/lib/python3/dist-packages')]
   self.assertEqual(env['PYTHONPATH'],os.pathsep.join(map(str,expected)))
   self.assertEqual(env['MPLBACKEND'],'Agg')
   for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):self.assertEqual(env[name],'1')

if __name__=='__main__':unittest.main()
