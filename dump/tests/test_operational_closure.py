import ast
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest

BASE=next(parent for parent in pathlib.Path(__file__).resolve().parents if (parent/"runtime_20261025").is_dir())
RUNTIME=BASE/"runtime_20261025"
POLICY_REL=pathlib.Path("operations/working_reserve_storage_1gib_20261031/WORKING_STORAGE_POLICY_20261031.json")
RECEIPT_REL=pathlib.Path("operations/working_reserve_storage_1gib_20261031/FOCUSED_QUALIFICATION_20261031.json")
APPROVAL_REL=pathlib.Path("operations/root_storage6gib_deploy_20261030/USER_RESOURCE_DECISION.json")
BASELINE="7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b"

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def literal_assignment(path,name):
    tree=ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("missing literal "+name)

def load_policy_functions(controller_path,runtime):
    tree=ast.parse(controller_path.read_text())
    wanted={"GIB","STORAGE_DRAIN_OUTPUT_RESERVE_BYTES","WORKING_STORAGE_POLICY"}
    assigns=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in wanted for t in n.targets)]
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    env={"pathlib":pathlib,"hashlib":hashlib,"json":json,"ast":ast,"R":runtime,"__file__":str(controller_path),"sha":sha}
    exec(compile(ast.Module(body=assigns,type_ignores=[]),str(controller_path),"exec"),env)
    selected=[functions[n] for n in ("_controller_dispatch_ast_sha256","_storage_operational_amendment_valid")]
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(controller_path),"exec"),env)
    return env

class OperationalClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="storage-allowance-closure-")
        self.project=pathlib.Path(self.tmp.name);self.runtime=self.project/"runtime_20261025"
        (self.runtime/"source").mkdir(parents=True);(self.runtime/"manifests").mkdir()
        shutil.copyfile(RUNTIME/"source/controller.py",self.runtime/"source/controller.py")
        shutil.copyfile(RUNTIME/"manifests/freeze.json",self.runtime/"manifests/freeze.json")
        for rel in (POLICY_REL,RECEIPT_REL,APPROVAL_REL):
            src=BASE/rel;dst=self.project/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        (self.project/"tests").mkdir()
        shutil.copyfile(BASE/"tests/run_storage_allowance_qualification.py",self.project/"tests/run_storage_allowance_qualification.py")
        self.env=load_policy_functions(self.runtime/"source/controller.py",self.runtime)
        self.freeze=json.loads((self.runtime/"manifests/freeze.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_operational_amendment_validates_exact_staged_files(self):
        self.assertTrue(self.env["_storage_operational_amendment_valid"](self.freeze,BASELINE))

    def test_receipt_tamper_rejects_amendment(self):
        p=self.project/RECEIPT_REL;d=json.loads(p.read_text());d["tests_failed"]=1;p.write_text(json.dumps(d))
        self.assertFalse(self.env["_storage_operational_amendment_valid"](self.freeze,BASELINE))

    def test_wrapper_pin_cascade_matches_candidate_sources(self):
        controller=sha(RUNTIME/"source/controller.py")
        child=sha(RUNTIME/"source/commit_batch_child.py")
        run=sha(RUNTIME/"source/run_batch.py")
        auto_pins=literal_assignment(RUNTIME/"source/cold_auto_compaction.py","PINS")
        run_pins=literal_assignment(RUNTIME/"source/run_batch.py","SOURCE_PINS")
        child_pins=literal_assignment(RUNTIME/"source/commit_batch_child.py","PINS")
        self.assertEqual(auto_pins["controller.py"],controller)
        self.assertEqual(auto_pins["commit_batch_child.py"],child)
        self.assertEqual(auto_pins["run_batch.py"],run)
        self.assertEqual(run_pins["controller.py"],controller)
        self.assertEqual(run_pins["commit_batch_child.py"],child)
        self.assertEqual(child_pins["controller.py"],controller)
        frozen=json.loads((RUNTIME/"manifests/freeze.json").read_text())
        self.assertEqual(frozen["operational_source_sha256"]["cold_auto_compaction.py"],sha(RUNTIME/"source/cold_auto_compaction.py"))
        self.assertEqual(frozen["operational_source_sha256"]["run_batch.py"],run)
        self.assertEqual(frozen["operational_source_sha256"]["commit_batch_child.py"],child)

    def test_watchdog_policy_and_enable_record_match_candidate(self):
        source=BASE/"operations/root_storage6gib_deploy_20261030/safe_watchdog.py"
        enable=json.loads((BASE/"operations/root_storage6gib_deploy_20261030/watchdog_enable_candidate.json").read_text())
        freeze=json.loads((RUNTIME/"manifests/freeze.json").read_text())
        self.assertIn('POLICY="working-reserve-6gib-one-fit-1gib-output-v1"',source.read_text())
        self.assertEqual(enable["storage_policy_id"],freeze["storage_admission_policy"]["policy_id"])
        self.assertEqual(enable["controller_sha256"],sha(RUNTIME/"source/controller.py"))
        self.assertEqual(enable["freeze_sha256"],sha(RUNTIME/"manifests/freeze.json"))

    def test_public_finalizer_closure_pins_new_storage_evidence_and_watchdog(self):
        finalizer=RUNTIME/"source/finalize_project.py"
        pins=literal_assignment(finalizer,"PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256")
        expected={
            "operations/working_reserve_storage_1gib_20261031/WORKING_STORAGE_POLICY_20261031.json":
                "40d68b9904a768cc24d9607f31ee7a02af6d0812e8034e12751514c1b047a8c3",
            "operations/working_reserve_storage_1gib_20261031/FOCUSED_QUALIFICATION_20261031.json":
                "b7e771e10da6811b8e28d1ceabea9ade91178c3cb6b72c9b9bd98091370d20d5",
            "operations/working_reserve_storage_1gib_20261031/STARTUP_CLOSURE_QUALIFICATION_20261031.json":
                "e327a07b3f650b89ca98119a0e07e27d061fb33586531f13957d028fee7892d4",
        }
        self.assertEqual(len(pins),16)
        for rel,digest in expected.items():
            self.assertEqual(pins[rel][0],digest)
            self.assertEqual(sha(BASE/rel),digest)

    def test_freeze_keeps_scientific_source_inventory_unchanged_except_controller(self):
        live=json.loads((BASE.parents[1]/"manifests/freeze.json").read_text())
        cand=json.loads((RUNTIME/"manifests/freeze.json").read_text())
        old=dict(cand["source_sha256"]);old["controller.py"]=live["source_sha256"]["controller.py"]
        self.assertEqual(old,live["source_sha256"])
        self.assertEqual(cand["storage_admission_policy"]["working_reserve_bytes"],6*1024**3)
        self.assertEqual(cand["storage_admission_policy"]["maximum_concurrent_fit_tasks"],1)

if __name__=="__main__":
    unittest.main()
