import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

WRAPPER=Path(__file__).resolve().parents[1]/'source'/'export_e6_descriptive.py'

class TestE6ExporterDispatch(unittest.TestCase):
    def test_v2_flag_routes_only_to_versioned_data_exporter(self):
        ns=runpy.run_path(str(WRAPPER),run_name='candidate_module')
        with patch.object(ns['runpy'],'run_path') as call, patch.object(ns['sys'],'argv',['export_e6_descriptive.py']):
            ns['main'](['--e6-v2','--runtime','runtime_20261025','--output','new-output','--superseded-ledger','old.csv'])
            forwarded=list(ns['sys'].argv[1:])
        target=Path(call.call_args.args[0])
        self.assertEqual(target.name,'export_e6_v2_descriptive.py')
        self.assertEqual(forwarded,['--runtime','runtime_20261025','--output','new-output','--superseded-ledger','old.csv'])

    def test_default_preserves_v1_exporter(self):
        ns=runpy.run_path(str(WRAPPER),run_name='candidate_module')
        with patch.object(ns['runpy'],'run_path') as call, patch.object(ns['sys'],'argv',['export_e6_descriptive.py']):
            ns['main'](['--runtime','runtime_20261025'])
        self.assertEqual(Path(call.call_args.args[0]).name,'export_e6_descriptive_v1.py')

if __name__=='__main__':unittest.main()
