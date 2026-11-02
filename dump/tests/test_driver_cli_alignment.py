import ast,importlib.util
from pathlib import Path
import unittest

STAGE=Path(__file__).resolve().parents[1]
SOURCE=STAGE/"source/archive_fit_admission.py"
HERE=Path(__file__).resolve()
RUNTIME=next(p for p in HERE.parents if (p/"source/cold_auto_compaction.py").is_file())
spec=importlib.util.spec_from_file_location("staged_archive_fit_admission",SOURCE)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

class DriverCliAlignmentTests(unittest.TestCase):
 def setUp(self):
  self.python=RUNTIME.parent/"venv/bin/python"
  self.script=RUNTIME/"source/cold_auto_compaction.py"
 def test_codec_driver_argv_matches_real_supported_cli(self):
  argv=[str(self.python),str(self.script),"--storage-codec-policy","reversible-xz-v1","--archive-io-profile","bounded-5400-codec4gib64"]
  self.assertTrue(M.driver_command_matches(argv,python=self.python,script=self.script,batch_policy="storage-followup-codec",storage_codec="reversible-xz-v1",io_profile="bounded-5400-codec4gib64"))
 def test_raw_driver_argv_remains_unchanged(self):
  argv=[str(self.python),str(self.script),"--archive-io-profile","bounded-1800-mixedsmall4gib2048"]
  self.assertTrue(M.driver_command_matches(argv,python=self.python,script=self.script,batch_policy="storage-followup",storage_codec=None,io_profile="bounded-1800-mixedsmall4gib2048"))
 def test_wrong_profile_policy_or_extra_cli_flag_rejected(self):
  base=[str(self.python),str(self.script),"--storage-codec-policy","reversible-xz-v1","--archive-io-profile","bounded-5400-codec4gib64"]
  for argv,batch,codec,profile in (
   (base,"storage-followup","reversible-xz-v1","bounded-5400-codec4gib64"),
   (base,"storage-followup-codec","reversible-xz-v1","bounded-1800-codec1gib64"),
   (base+["--batch-policy","storage-followup-codec"],"storage-followup-codec","reversible-xz-v1","bounded-5400-codec4gib64"),
   (base[:-1]+["wrong"],"storage-followup-codec","reversible-xz-v1","bounded-5400-codec4gib64"),
   (base+["--unknown"],"storage-followup-codec","reversible-xz-v1","bounded-5400-codec4gib64")):
   with self.subTest(argv=argv):
    self.assertFalse(M.driver_command_matches(argv,python=self.python,script=self.script,batch_policy=batch,storage_codec=codec,io_profile=profile))
 def test_cold_auto_argparse_exposes_only_real_codec_and_profile_options(self):
  tree=ast.parse((RUNTIME/"source/cold_auto_compaction.py").read_text())
  opts=set()
  for n in ast.walk(tree):
   if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="add_argument":
    for a in n.args:
     if isinstance(a,ast.Constant) and isinstance(a.value,str) and a.value.startswith("--"):opts.add(a.value)
  self.assertIn("--storage-codec-policy",opts);self.assertIn("--archive-io-profile",opts)
  self.assertNotIn("--batch-policy",opts)

if __name__=="__main__":unittest.main()
