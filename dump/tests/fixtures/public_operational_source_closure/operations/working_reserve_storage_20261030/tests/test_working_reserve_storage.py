import ast
import copy
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest

CONTROLLER = pathlib.Path(__file__).resolve().parents[1] / "source" / "controller.py"
TREE = ast.parse(CONTROLLER.read_text())
NAMES = {"retention_restore_budget", "storage_required_bytes", "fit_limited_ready", "storage_allow", "sha", "_controller_dispatch_ast_sha256", "_storage_operational_amendment_valid", "_storage_expected_campaign", "retention_budget_matches_policy"}
NODES = []
for node in TREE.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"WORKING_STORAGE_POLICY", "STORAGE_DRAIN_OUTPUT_RESERVE_BYTES"} for t in node.targets):
        NODES.append(node)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES:
        NODES.append(node)
ENV = {"pathlib": pathlib, "hashlib": hashlib, "json": json, "ast": ast, "GIB": 1024**3, "shutil": shutil, "atomic": lambda *args, **kwargs: None, "now": lambda: "fixture"}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(CONTROLLER), "exec"), ENV)
BUDGET = ENV["retention_restore_budget"]
REQUIRED = ENV["storage_required_bytes"]
FIT_FILTER = ENV["fit_limited_ready"]
POLICY = ENV["WORKING_STORAGE_POLICY"]
MATCH_POLICY = ENV["retention_budget_matches_policy"]

def good_row(key="e4/rep_1/eval/direct/arf/A_half", size=1234):
    source=f"runtime_20261025/artifacts/{key}/test_outcomes.npz"
    alias=f"runtime_20261025/artifacts/{key}/attempts/123_abcd/test_outcomes.npz"
    return {
        "task_key":key,"task_family":int(key[1]),"source_path":source,"source_bytes":size,"source_sha256":"a"*64,
        "asset_name":"results-01.zip","asset_bytes":10000,"asset_sha256":"b"*64,
        "native_paths":[source,alias],"unlinked_paths":[source,alias],"link_count":2,
        "retirement_kind":"complete_inode_group","fresh_native_inventory_verified":True,
        "asset_remote_evidence_path":"/project/remote.json","asset_remote_evidence_sha256":"c"*64,
        "member_record_evidence_path":"/project/members.json","member_record_evidence_sha256":"d"*64,
        "manifest_sha256":"e"*64,"physical_inventory_sha256":"f"*64,"plan_sha256":"0"*64,
        "archive_member":source,"archive_crc32":"1234abcd"
    }

def write_index(path, rows=None, restore=True):
    doc={"schema":POLICY["restore_index_schema"],"restore_required":restore,"retired":rows if rows is not None else [good_row()]}
    path.write_text(json.dumps(doc))
    return doc

class WorkingReserveStorageTests(unittest.TestCase):
    def _bridge_fixture(self, temp_root):
        project=pathlib.Path(temp_root)
        runtime=project/"runtime_20261025"
        source_dir=runtime/"source";source_dir.mkdir(parents=True)
        candidate=source_dir/"controller.py";shutil.copy2(CONTROLLER,candidate)
        operation=project/"operations"/"working_reserve_storage_20261030"
        test_dir=operation/"tests";test_dir.mkdir(parents=True)
        test_file=test_dir/"test_working_reserve_storage.py";shutil.copy2(pathlib.Path(__file__),test_file)
        policy_file=operation/"WORKING_STORAGE_POLICY_20261030.json"
        receipt_file=operation/"FOCUSED_QUALIFICATION_20261030.json"
        approval_file=project/"operations"/"root_storage6gib_deploy_20261030"/"USER_RESOURCE_DECISION.json"
        approval_file.parent.mkdir(parents=True)
        approval={"authorized":True,"user_answer":"Use 6 GiB reserve and one fit"}
        approval_file.write_text(json.dumps(approval,sort_keys=True,indent=2))
        index_file=project/"operations"/"terminal_result_retention_v2_20261030"/"guardian"/"retention_index.json"
        index_file.parent.mkdir(parents=True)
        write_index(index_file,[good_row()])
        index_budget=BUDGET(index_file)
        candidate_sha=hashlib.sha256(candidate.read_bytes()).hexdigest()
        dispatch_names=("_rf4_fit_eligible","_et4_fit_eligible","worker_script_for_task","worker_request_definition","worker_resource_class","worker_reservation_bytes","candidate_cpu_reservation_units")
        dispatch=ENV["_controller_dispatch_ast_sha256"](candidate,dispatch_names)
        policy={"schema":"lamost-working-storage-admission-policy/1","policy_id":POLICY["policy_id"],
            "controller_baseline_sha256":"7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b",
            "controller_candidate_sha256":candidate_sha,"approval_record_sha256":hashlib.sha256(approval_file.read_bytes()).hexdigest(),
            "approval_record":"operations/root_storage6gib_deploy_20261030/USER_RESOURCE_DECISION.json",
            "retention_index_path":POLICY["restore_index_rel"],"retention_index_schema":POLICY["restore_index_schema"],
            "retention_index_sha256":index_budget["index_sha256"],"retention_row_count":index_budget["row_count"],
            "retention_restore_required":index_budget["restore_required"],"retention_restore_bytes":index_budget["restore_bytes"],
            "largest_restore_asset_bytes":index_budget["largest_asset_bytes"],
            "maximum_concurrent_fit_tasks":1,
            "per_active_or_new_task_output_reserve_bytes":POLICY["per_active_or_new_task_output_reserve_bytes"],
            "unchanged_scientific_resource_limits":{"worker_hard_limit_bytes":10*1024**3,"trial_timeout_seconds":600,"phase_timeout_seconds":600,"termination_grace_seconds":30,"nested_threads":1},
            "freeze_binding_value":POLICY,"protected_dispatch_function_ast_sha256":dispatch}
        policy_file.write_text(json.dumps(policy,sort_keys=True,indent=2))
        policy_sha=hashlib.sha256(policy_file.read_bytes()).hexdigest()
        test_rel=test_file.relative_to(project).as_posix()
        receipt={"schema":"lamost-working-storage-admission-focused-qualification/1","result":"passed",
            "tests_passed":13,"tests_failed":0,"controller_sha256":candidate_sha,"policy_sha256":policy_sha,
            "py_compile":"passed","test_path":test_rel,"test_sha256":hashlib.sha256(test_file.read_bytes()).hexdigest()}
        receipt_file.write_text(json.dumps(receipt,sort_keys=True,indent=2))
        amendment={"schema":"lamost-controller-operational-source-amendment/1",
            "baseline_controller_sha256":"7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b",
            "candidate_controller_sha256":candidate_sha,
            "policy_path":policy_file.relative_to(project).as_posix(),"policy_sha256":policy_sha,
            "focused_receipt_path":receipt_file.relative_to(project).as_posix(),
            "focused_receipt_sha256":hashlib.sha256(receipt_file.read_bytes()).hexdigest(),
            "approval_path":approval_file.relative_to(project).as_posix(),
            "approval_sha256":hashlib.sha256(approval_file.read_bytes()).hexdigest(),
            "protected_dispatch_function_ast_sha256":dispatch}
        frozen={"storage_admission_policy":POLICY,"storage_admission_amendment":amendment}
        ENV["R"]=runtime;ENV["__file__"]=str(candidate)
        return project,runtime,candidate,policy_file,receipt_file,amendment,frozen,dispatch,index_file,index_budget

    def test_retention_index_must_match_pinned_sha_count_and_restore_state(self):
        with tempfile.TemporaryDirectory() as td:
            _,_,_,_,_,_,frozen,_,index_file,budget=self._bridge_fixture(td)
            expected=ENV["_storage_expected_campaign"](frozen)
            self.assertTrue(MATCH_POLICY(budget,expected))
            ENV["shutil"].disk_usage=lambda path:type("Usage",(),{"free":10**12})()
            self.assertTrue(ENV["storage_allow"]([],frozen)[0])
            write_index(index_file,[good_row()],restore=False)
            self.assertFalse(MATCH_POLICY(BUDGET(index_file),expected))
            self.assertFalse(ENV["storage_allow"]([],frozen)[0])
            changed=good_row(size=1235)
            write_index(index_file,[changed],restore=True)
            self.assertFalse(MATCH_POLICY(BUDGET(index_file),expected))
            wrong_sha=dict(budget);wrong_sha["index_sha256"]="0"*64
            self.assertFalse(MATCH_POLICY(wrong_sha,expected))
            wrong_count=dict(budget);wrong_count["row_count"]+=1
            self.assertFalse(MATCH_POLICY(wrong_count,expected))

    def test_storage_amendment_accepts_exact_legacy_pin_with_new_focused_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            _,_,_,_,_,_,frozen,_,_,_=self._bridge_fixture(td)
            self.assertTrue(ENV["_storage_operational_amendment_valid"](frozen,"7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b"))

    def test_storage_amendment_rejects_wrong_controller_binding_and_wrong_legacy_pin(self):
        with tempfile.TemporaryDirectory() as td:
            _,_,_,_,_,amendment,frozen,_,_,_=self._bridge_fixture(td)
            changed=copy.deepcopy(frozen);changed["storage_admission_amendment"]["candidate_controller_sha256"]="0"*64
            self.assertFalse(ENV["_storage_operational_amendment_valid"](changed,"7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b"))
            self.assertFalse(ENV["_storage_operational_amendment_valid"](frozen,"1"*64))

    def test_storage_amendment_rejects_changed_dispatch_ast_proof(self):
        with tempfile.TemporaryDirectory() as td:
            project,runtime,candidate,policy_file,receipt_file,amendment,frozen,dispatch,_,_=self._bridge_fixture(td)
            policy=json.loads(policy_file.read_text())
            policy["protected_dispatch_function_ast_sha256"]["worker_script_for_task"]="0"*64
            policy_file.write_text(json.dumps(policy,sort_keys=True,indent=2))
            policy_sha=hashlib.sha256(policy_file.read_bytes()).hexdigest()
            receipt=json.loads(receipt_file.read_text());receipt["policy_sha256"]=policy_sha
            receipt_file.write_text(json.dumps(receipt,sort_keys=True,indent=2))
            amendment["policy_sha256"]=policy_sha
            amendment["focused_receipt_sha256"]=hashlib.sha256(receipt_file.read_bytes()).hexdigest()
            amendment["protected_dispatch_function_ast_sha256"]=policy["protected_dispatch_function_ast_sha256"]
            self.assertFalse(ENV["_storage_operational_amendment_valid"](frozen,"7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b"))

    def test_budget_reads_index_and_counts_one_shared_restore_asset(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"index.json"
            write_index(p,[good_row(size=500),good_row("e5/rep_2/eval/synthetic/random_forest/B_half",700)])
            result=BUDGET(p)
            self.assertEqual(result["restore_bytes"],1200)
            self.assertEqual(result["largest_asset_bytes"],10000)
            self.assertTrue(result["restore_required"])
            self.assertEqual(result["index_sha256"],hashlib.sha256(p.read_bytes()).hexdigest())

    def test_real_policy_formula_reserves_restore_asset_output_and_working_floor(self):
        gib=1024**3
        reserve=5_595_808_572
        largest=729_545_227
        self.assertEqual(REQUIRED(reserve,largest,0),6*gib+reserve+largest+2*gib)
        self.assertEqual(REQUIRED(reserve,largest,1),6*gib+reserve+largest+4*gib)
        self.assertIsNone(REQUIRED(10*gib+1,0,0))
        self.assertIsNone(REQUIRED(0,gib+1,0))

    def test_missing_nonregular_symlink_and_malformed_indexes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); missing=root/"missing.json"
            self.assertIsNone(BUDGET(missing))
            d=root/"dir";d.mkdir();self.assertIsNone(BUDGET(d))
            target=root/"target";write_index(target)
            link=root/"link.json"
            try: link.symlink_to(target)
            except (OSError,NotImplementedError): self.skipTest("symlinks unavailable")
            self.assertIsNone(BUDGET(link))
            bad=root/"bad.json";bad.write_text('{"schema":"wrong","restore_required":true,"retired":[]}')
            self.assertIsNone(BUDGET(bad))
            empty=root/"empty-restore.json";write_index(empty,[],restore=True)
            self.assertIsNone(BUDGET(empty))

    def test_duplicate_alias_bad_source_asset_and_over_cap_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"index.json"
            r=good_row()
            variants=[]
            x=copy.deepcopy(r);x["source_path"]="runtime_20261025/artifacts/e4/rep_1/eval/direct/arf/A_half/../../oops.npz";variants.append(x)
            x=copy.deepcopy(r);x["asset_name"]="../bad.zip";variants.append(x)
            x=copy.deepcopy(r);x["native_paths"].append(x["native_paths"][1]);variants.append(x)
            x=copy.deepcopy(r);x["source_bytes"]=10*1024**3+1;variants.append(x)
            x=copy.deepcopy(r);x["asset_bytes"]=1024**3+1;variants.append(x)
            x=copy.deepcopy(r);x["link_count"]=3;variants.append(x)
            x=copy.deepcopy(r);x.pop("asset_remote_evidence_sha256");variants.append(x)
            for row in variants:
                write_index(p,[row])
                self.assertIsNone(BUDGET(p),row)

    def test_same_asset_rows_restore_sum_bounded_and_clear_index_reserves_none(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"index.json"
            write_index(p,[good_row(size=10)],restore=False)
            result=BUDGET(p)
            self.assertFalse(result["restore_required"])
            self.assertEqual(result["restore_bytes"],0)
            self.assertEqual(result["largest_asset_bytes"],0)

    def test_one_fit_lane_filters_fits_but_keeps_evaluations(self):
        running=[{"kind":"fit","status":"running","key":"fit/a"}]
        ready=[{"kind":"fit","key":"fit/b"},{"kind":"eval","key":"eval/a"},{"kind":"alias","key":"alias/a"}]
        self.assertEqual([x["kind"] for x in FIT_FILTER(running,ready)],["eval","alias"])
        self.assertEqual(FIT_FILTER([],ready),ready)

    def test_scheduler_rechecks_disk_after_candidate_and_before_admit(self):
        run=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="run")
        calls=[n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="storage_allow"]
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(all(len(c.args)==2 and isinstance(c.args[0],ast.Name) and c.args[0].id=="running" and isinstance(c.args[1],ast.Name) and c.args[1].id=="frozen" for c in calls))
        candidate_line=next(n.lineno for n in ast.walk(run) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="candidate" for x in n.targets) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=="admission_candidate")
        admit_line=next(n.lineno for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="admit")
        self.assertTrue(any(candidate_line < n.lineno < admit_line for n in calls))

    def test_sink_drain_uses_same_restore_liability_and_output_budget(self):
        drain=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="storage_drain_candidate")
        calls={n.func.id for n in ast.walk(drain) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertIn("retention_restore_budget",calls)
        self.assertIn("storage_required_bytes",calls)
        self.assertIn("admission_hold", {n.id for n in ast.walk(drain) if isinstance(n,ast.Name)})

    def test_freeze_binds_storage_policy_without_changing_worker_limits(self):
        freeze=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="freeze")
        names={n.value for n in ast.walk(freeze) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertIn("storage_admission_policy",names)
        self.assertTrue(any(isinstance(n,ast.Name) and n.id=="WORKING_STORAGE_POLICY" for n in ast.walk(freeze)))
        adaptive=next(n.value for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="ADAPTIVE_POLICY" for x in n.targets))
        values=ast.literal_eval(adaptive)
        self.assertEqual(values["worker_memory_limit_gib"],10)
        self.assertEqual(values["trial_timeout_seconds"],600)
        self.assertEqual(values["phase_timeout_seconds"],600)
        self.assertEqual(values["termination_grace_seconds"],30)

if __name__=="__main__":unittest.main()
