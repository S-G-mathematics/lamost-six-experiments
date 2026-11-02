import ast
import json
import os
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).parents[1]/'source/e6_v2_reporting.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf-8'))
FN=next(n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='_artifact_dir')
ns={'Path':Path,'E6V2ReportError':ValueError}
exec(compile(ast.Module(body=[FN],type_ignores=[]),str(SOURCE),'exec'),ns)
artifact_dir=ns['_artifact_dir']

class ArtifactResolutionTests(unittest.TestCase):
 def test_native_archive_path_from_unrelated_cwd(self):
  with tempfile.TemporaryDirectory() as d:
   extraction=Path(d)/'extract'; rt=extraction/'runtime_20261025'; task={'key':'e6/rep_1/eval/member/gmm','artifact_dir':'runtime_20261025/artifacts/e6/rep_1/eval/member/gmm'}
   expected=rt/'artifacts'/task['key']; expected.mkdir(parents=True)
   (expected/'evaluation.json').write_text(json.dumps({'origin':'extracted tree'}))
   cwd=os.getcwd()
   try:
    os.chdir(d)
    resolved=artifact_dir(rt,task['key'])
    self.assertEqual(resolved.resolve(),expected.resolve())
    self.assertEqual(json.loads((resolved/'evaluation.json').read_text())['origin'],'extracted tree')
   finally: os.chdir(cwd)

 def test_legacy_absolute_is_remapped_without_consulting_source_path(self):
  with tempfile.TemporaryDirectory() as d:
   rt=Path(d)/'copy/runtime_20261025'; task={'key':'e6/rep_2/eval/member/arf','artifact_dir':'/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/artifacts/e6/rep_2/eval/member/arf'}
   expected=rt/'artifacts'/task['key']; expected.mkdir(parents=True)
   payload=expected/'evaluation.json'; payload.write_text(json.dumps({'marker':'archive-copy-only'}))
   got=artifact_dir(rt,task['key'])
   self.assertEqual(got.resolve(),expected.resolve())
   self.assertEqual(json.loads((got/'evaluation.json').read_text())['marker'],'archive-copy-only')
   self.assertNotEqual(str(got),task['artifact_dir'])

 def test_canonical_only_when_legacy_artifact_missing(self):
  with tempfile.TemporaryDirectory() as d:
   rt=Path(d)/'runtime_20261025'; task={'key':'e6/rep_3/eval/member/kde','artifact_dir':'/original/host/path'}
   self.assertEqual(artifact_dir(rt,task['key']), (rt/'artifacts'/task['key']).resolve())

 def test_rejects_key_escape(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError): artifact_dir(Path(d)/'runtime_20261025','../../outside')

if __name__=='__main__': unittest.main()