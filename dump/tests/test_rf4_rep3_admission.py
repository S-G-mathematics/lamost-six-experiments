import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
import numpy as np

SOURCE = pathlib.Path(__file__).parents[1] / "source" / "rf4_e4_rep3_admission.py"
spec = importlib.util.spec_from_file_location("rf4_rep3_gate", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def put(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, sort_keys=True))
    return path

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

class GateFixture(unittest.TestCase):
    def setup_case(self, treatment="ros", rows=90000):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        (root / "source/parallel_rf").mkdir(parents=True)
        source_pins = {}
        for name in ("parallel_rf/worker.py", "parallel_rf/phase_worker.py", "parallel_rf/science.py"):
            rel = pathlib.Path("source") / name
            put(root / rel, f"pin:{name}".encode())
            source_pins[name] = sha(root / rel)
        (root / "cache/roles").mkdir(parents=True)
        role_sha = hashlib.sha256(b"role-cache").hexdigest()
        put(root / "cache/roles/rep_3.npz", b"role-cache")
        role_source = put(root.parent / "project/benchmark/results/e1/rep_3/n_100000/role_membership.npz", b"role-source")
        role_source_sha = sha(role_source)
        cache = {
            "cache_files": {"roles/rep_3.npz": role_sha},
            "roles": {"3": {"source_sha256": role_source_sha, "id_hashes": {"fit_ids":"a"},
                             "fit_counts":[10000,20000,10000,10000,10000,10000,10000]}},
            "features": ["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"],
            "labels": ["A","F","G","K","M","GALAXY","QSO"],
        }
        put(root / "cache/cache_manifest.json", cache)
        tasks = {"plan": "same"}
        tasks_sha = sha(put(root / "manifests/tasks.json", tasks))
        role_membership_hash = role_source_sha
        put(root / "manifests/plan_summary.json", {"role_membership_hashes":{"rep_3":role_membership_hash}})
        (root / "artifacts").mkdir()
        condbase = "F_half"
        cohort_key=f"e4/rep_3/cohort/{condbase}"
        cohort_counts=[10000,20000,10000,10000,10000,10000,10000]
        put(root/"artifacts"/cohort_key/"metadata.json",{"task_key":cohort_key,"kind":"e4_cohort","rep":3,"condition":condbase,"N":80000,"tune_calibration_reserved":True,"realized_counts":cohort_counts})
        put(root/"artifacts"/cohort_key/"validation.json",{"task_key":cohort_key,"status":"validated"})
        if treatment == "weighted":
            train = f"e4/rep_3/treatment/{condbase}/weighted"
            metadata = {"task_key":train,"kind":"e4_treatment","treatment":"weighted",
                        "parent":str(root/"artifacts"/f"e4/rep_3/cohort/{condbase}"),
                        "counts":[10000,20000,10000,10000,10000,10000,10000],
                        "added_count":0,"sample_weight_mean":1.0}
        elif treatment in ("ros","smote"):
            train = f"e4/rep_3/treatment/{condbase}/{treatment}"
            added=rows-80000
            after=list(cohort_counts);after[1]+=added
            metadata = {"task_key":train,"kind":"e4_treatment","treatment":treatment,
                        "parent":str(root/"artifacts"/f"e4/rep_3/cohort/{condbase}"),
                        "counts_before":cohort_counts,"counts_after":after,"added_count":added}
        else:
            gen=treatment.removeprefix("generated_")
            train=f"e4/rep_3/append/{condbase}/{gen}"
            before=[10000,20000,10000,10000,10000,10000,10000]
            added=rows-80000
            after=list(before);after[1]+=added
            metadata={"task_key":train,"kind":"e4_append","target_class":1,"parent":str(root/"artifacts"/f"e4/rep_3/cohort/{condbase}"),
                "generated_artifact":str(root/"artifacts"/f"e4/rep_3/generate/{condbase}/{gen}"),
                "counts_before":before,"counts_after":after,"added_count":added}
            gkey=f"e4/rep_3/generate/{condbase}/{gen}"
            gdir=root/"artifacts"/gkey
            data_sha=hashlib.sha256(b"generated").hexdigest()
            put(gdir/"generation_result.json",{"status":"successful","task":{"key":gkey,"fit_key":f"e4/rep_3/fit/direct/{gen}/{condbase}","cohort_key":f"e4/rep_3/cohort/{condbase}","target_class":1,"restored_share":"original_target_share"},"result":{"status":"success","n_rows":added,"data_sha256":data_sha}})
            put(gdir/"validation.json",{"status":"validated","task_key":gkey,"files":{"data.npz":data_sha}})
        depdir=root/"artifacts"/train
        put(depdir/"data.npz",b"npz-header-placeholder")
        data_sha=hashlib.sha256(b"npz-header-placeholder").hexdigest()
        validation={"status":"validated","task_key":train,"files":{"data.npz":data_sha}}
        put(depdir/"metadata.json",metadata); put(depdir/"validation.json",validation)
        metasha=sha(depdir/"metadata.json"); valsha=sha(depdir/"validation.json")
        shapes={"X":[rows,6],"y":[rows],"ids":[rows]}
        if treatment=="weighted": shapes["sample_weight"]=[80000]
        resource_files=[]
        for n in range(2):
            rel=f"reports/resource{n}.json"
            put(root/rel,{"ref":n})
            resource_files.append({"path":rel,"sha256":sha(root/rel)})
        evidence={
            "schema_version":"lamost-e4-rep3-rf4-admission-evidence/1",
            "tasks_sha256":tasks_sha,"plan_sha256":tasks_sha,"plan_summary_sha256":sha(root/"manifests/plan_summary.json"),
            "source_pins":source_pins,
            "role_evidence":{"role_cache_sha256":role_sha,"role_cache_manifest_sha256":role_sha,
                "role_source_sha256":role_source_sha,"role_source_actual_sha256":role_source_sha,
                "role_source_path":str(role_source),"role_id_hashes":{"fit_ids":"a"}},
            "tasks":[{"task_key":f"e4/rep_3/fit/treatment/random_forest/{condbase}_{treatment}",
                "train_key":train,"treatment":treatment,"condition":f"{condbase}_{treatment}",
                "eligible_candidate":True,"attempt_count":0,"metadata_sha256":metasha,
                "validation_sha256":valsha,"data_validation_sha256":data_sha,"data_size_bytes":len(b"npz-header-placeholder"),
                "data_header_shapes":shapes}]
        }
        ep=root/gate.EVIDENCE_REL;put(ep,evidence)
        policy={
            "schema_version":"lamost-rf4-e4-rep3-admission-policy/1","status":"qualified","profile_id":gate.PROFILE_ID,
            "supplement_module_sha256": sha(SOURCE),
            "reservation_gib":6,"hard_rss_limit_gib":10,"trial_timeout_seconds":600,"phase_timeout_seconds":600,
            "termination_grace_seconds":30,"dynamic_promotion_to_hard_limit":True,
            "plan_sha256":tasks_sha,"tasks_sha256":tasks_sha,"plan_summary_sha256":sha(root/"manifests/plan_summary.json"),
            "role_cache_sha256":role_sha,"role_source_sha256":role_source_sha,"cache_manifest_sha256":sha(root/"cache/cache_manifest.json"),
            "source_pins":source_pins,"evidence_path":gate.EVIDENCE_REL.as_posix(),"evidence_sha256":sha(ep),
            "resource_evidence_path":"reports/resource0.json","resource_evidence_sha256":sha(root/"reports/resource0.json"),
            "empirical_resource_evidence_sources":resource_files}
        pp=root/gate.POLICY_REL;put(pp,policy)
        frozen={"plan_sha256":tasks_sha,gate.FREEZE_POLICY_FIELD:sha(pp),"source_sha256":source_pins}
        task={
            "key":f"e4/rep_3/fit/treatment/random_forest/{condbase}_{treatment}","experiment":4,"rep":3,"kind":"fit","method":"random_forest","route":"treatment",
            "condition":f"{condbase}_{treatment}","treatment":treatment,"generator":treatment.removeprefix("generated_") if treatment.startswith("generated_") else None,
            "train_key":train,"dependencies":[train],"selection_mode":"tune","selection_policy":"tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget",
            "selection_key":None,"selection_source":None,"trials":10,"seed":123,"optimizer_seed":456,"status":"waiting_for_dependency","attempts":[]}
        definition=dict(task)
        dep={"key":train,"status":"validated_terminal"}
        def validator(path, expected):
            if getattr(self,"wrong_header",False):
                return {"X":(rows,5),"y":(rows,),"ids":(rows,)}
            return expected
        return root,task,definition,dep,frozen,validator,pp,ep,depdir

    def check(self,treatment,rows=90000):
        root,task,definition,dep,frozen,validator,*rest=self.setup_case(treatment,rows)
        return gate.eligible(task,definition,dep,frozen,root,validator), (root,task,definition,dep,frozen,validator,*rest)

    def test_all_major_treatment_shapes_are_eligible(self):
        for treatment in ("ros","smote","weighted","generated_arf"):
            with self.subTest(treatment=treatment):
                result,_=self.check(treatment,80000 if treatment=="weighted" else 90000)
                self.assertEqual(result["profile_id"],gate.PROFILE_ID)
                self.assertEqual(result["reservation_gib"],6)
                self.assertEqual(result["hard_rss_limit_gib"],10)

    def test_ros_smote_producer_histogram_schema_without_counts_alias(self):
        for treatment in ("ros", "smote"):
            with self.subTest(treatment=treatment):
                result, ctx = self.check(treatment, 90000)
                root, task, definition, dep, frozen, validator, *rest = ctx
                metadata = json.loads((root / "artifacts" / dep["key"] / "metadata.json").read_text())
                self.assertNotIn("counts", metadata)
                self.assertNotIn("target_class", metadata)
                self.assertEqual(metadata["counts_before"], [10000,20000,10000,10000,10000,10000,10000])
                self.assertEqual(sum(metadata["counts_after"]), 90000)
                self.assertEqual([a-b for a,b in zip(metadata["counts_after"],metadata["counts_before"])],
                                 [0,10000,0,0,0,0,0])
                self.assertEqual(result["training_rows"], 90000)

    def test_max_row_limit_fails_closed(self):
        result,_=self.check("ros",125956)
        self.assertIsNone(result)

    def test_wrong_rep_or_method_fails_closed(self):
        result,ctx=self.check("ros")
        _,task,definition,dep,frozen,validator,*_=ctx
        definition["rep"]=2;task["rep"]=2
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,ctx[0],validator))
        definition["rep"]=3;task["rep"]=3;definition["method"]="extra_trees";task["method"]="extra_trees"
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,ctx[0],validator))

    def test_attempt_reuse_reservation_and_output_directory_denied(self):
        result,ctx=self.check("ros");root,task,definition,dep,frozen,validator,*_=ctx
        task["attempts"]=[{"attempt":1}]
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))
        task["attempts"]=[];task["reuse_pipeline"]=True;definition["reuse_pipeline"]=True
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))
        task["reuse_pipeline"]=None;definition["reuse_pipeline"]=None
        (root/"artifacts"/pathlib.Path(*pathlib.PurePosixPath(task["key"]).parts)).mkdir(parents=True)
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

    def test_stale_policy_or_dependency_hash_denied(self):
        result,ctx=self.check("ros");root,task,definition,dep,frozen,validator,pp,ep,depdir=ctx
        frozen[gate.FREEZE_POLICY_FIELD]="0"*64
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))
        frozen[gate.FREEZE_POLICY_FIELD]=sha(pp)
        (depdir/"metadata.json").write_text("{}")
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

    def test_stale_source_and_resource_pin_denied(self):
        result,ctx=self.check("ros");root,task,definition,dep,frozen,validator,*_=ctx
        (root/"source/parallel_rf/science.py").write_text("changed")
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

    def test_wrong_header_or_dependency_denied(self):
        result,ctx=self.check("ros");root,task,definition,dep,frozen,validator,*_=ctx
        self.wrong_header=True
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))
        self.wrong_header=False
        dep["key"]="different"
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

    def test_header_reader_exact_nonweighted_and_weighted_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); f=root/"nonweighted.npz"
            np.savez(f,X=np.zeros((5,6),dtype=np.float64),y=np.zeros(5,dtype=np.int64),ids=np.arange(5,dtype=np.int64))
            self.assertEqual(gate.header_shapes(f,{"X":(5,6),"y":(5,),"ids":(5,)}),{"X":(5,6),"y":(5,),"ids":(5,)})
            self.assertNotEqual(gate.header_shapes(f,{"X":(5,5),"y":(5,),"ids":(5,)}),{"X":(5,5),"y":(5,),"ids":(5,)})
            w=root/"weighted.npz"
            np.savez(w,X=np.zeros((5,6),dtype=np.float64),y=np.zeros(5,dtype=np.int64),ids=np.arange(5,dtype=np.int64),sample_weight=np.ones(5))
            self.assertEqual(gate.header_shapes(w,{"X":(5,6),"y":(5,),"ids":(5,),"sample_weight":(5,)})["sample_weight"],(5,))
            link=root/"link.npz";link.symlink_to(w)
            self.assertIsNone(gate.header_shapes(link,{"X":(5,6),"y":(5,),"ids":(5,),"sample_weight":(5,)}))

    def test_unqualified_candidate_policy_fails_closed(self):
        result,ctx=self.check("ros");root,task,definition,dep,frozen,validator,pp,ep,depdir=ctx
        policy=json.loads(pp.read_text());policy["status"]="candidate_pending_root_qualification";put(pp,policy)
        frozen[gate.FREEZE_POLICY_FIELD]=sha(pp)
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

    def test_weighted_mean_guard(self):
        result,ctx=self.check("weighted",80000);root,task,definition,dep,frozen,validator,*_=ctx
        self.assertIsNotNone(result)
        metap=root/"artifacts"/definition["train_key"]/"metadata.json"
        metadata=json.loads(metap.read_text());metadata["sample_weight_mean"]=1.0001;put(metap,metadata)
        self.assertIsNone(gate.eligible(task,definition,dep,frozen,root,validator))

if __name__ == "__main__":
    unittest.main()
