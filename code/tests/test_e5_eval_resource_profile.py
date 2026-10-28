import copy
import hashlib
import importlib
import io
import json
import sys
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

STAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STAGE / "source"))
import admission_evidence as ae
import controller as ctl

EXPECTED = {"max_depth": None, "max_features": 1.0, "min_samples_leaf": 1, "n_estimators": 200}
FIT_IDS = "1" * 64
CAL_IDS = "2" * 64
MEMBERSHIP = "3" * 64
E5_COND = "feature_noise_05"
E5_BASE = "e3/rep_1/fit/real/random_forest"
E5_TRAIN = "e5/rep_1/corruption/feature_noise_05"
E5_FIT = "e5/rep_1/fit/direct/random_forest/feature_noise_05"
E5_EVAL = "e5/rep_1/eval/direct/random_forest/feature_noise_05"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def header_npy(shape, descr="<f8"):
    raw = repr({"descr": descr, "fortran_order": False, "shape": tuple(shape)}).encode("latin1")
    pad = (16 - ((10 + len(raw) + 1) % 16)) % 16
    header = raw + b" " * pad + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header



def write_headers(path, arrays):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        for name, shape in arrays.items():
            z.writestr(name + ".npy", header_npy(shape, "<i8" if name.startswith("y") else "<f8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True) + "\n")


class E5DirectRfEvalProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.build_valid_fixture()
        ctl.R = self.root
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        ae.E5_RF_EVAL_4G_RECEIPT = "staging/test_resource_receipt.json"
        receipt = self.make_receipt()
        write_json(self.root / ae.E5_RF_EVAL_4G_RECEIPT, receipt)
        ae.E5_RF_EVAL_4G_RECEIPT_SHA256 = digest(self.root / ae.E5_RF_EVAL_4G_RECEIPT)
        ae._SHA_CACHE.clear()
        ae._E5_FROZEN_PLAN_CACHE.clear()
        self.task = {**self.definition, "status": "waiting_for_dependency", "attempts": []}

    def tearDown(self):
        self.temp.cleanup()

    def make_receipt(self):
        fits = []
        for i in range(ae.E5_RF_EVAL_FIT_RECEIPTS_N):
            fits.append({
                "fit_rows": 80000, "params": EXPECTED,
                "fit_phase": {"peak_tree_rss_kib": ae.E5_RF_EVAL_MAX_FIT_RSS_KIB - i},
                "matches_E3_clean": {
                    "same_selected_params_as_E3_clean_real": True,
                    "same_training_ids_as_E3_clean_real": True,
                    "matching_E3_config_n_estimators": True,
                    "published_pipeline_sha_matches_fit_result": True,
                },
            })
        e3 = []
        for rep in (1, 2, 3):
            e3.append({
                "rep": rep, "fit_rows": 80000, "params": EXPECTED,
                "eval_phase": {"peak_tree_rss_kib": ae.E5_RF_EVAL_MAX_CLEAN_EVAL_RSS_KIB - rep,
                               "exit_code": 0},
                "eval_pipeline_identity": {"pipeline_sha256": str(rep) * 64, "test_n": 500000},
            })
        return {
            "e5_direct_rf": {"successful_fit_resource_receipts": fits},
            "e3_clean_real_rf_reference": {"matching_fit_and_eval_repetitions": e3},
            "prospective_assessment": {"E5_direct_RF_eval_4GiB": {"decision": "UNPROVEN until actual E5 phase receipt"}},
        }

    def build_valid_fixture(self):
        source = self.root / "source" / "science.py"
        source.parent.mkdir(parents=True)
        source.write_text("def _chunks_with_support(model,X,size=50000):\\n    for i in range(0,len(X),size):\\n        pass\\n")
        science_sha = digest(source)

        test_path = self.root / "cache" / "test.npz"
        role_path = self.root / "cache" / "roles" / "rep_1.npz"
        write_headers(test_path, {"X": (500000, 6), "y": (500000,), "ids": (500000,)})
        write_headers(role_path, {
            "X_fit": (80000, 6), "y_fit": (80000,), "fit_ids": (80000,),
            "X_tune": (10000, 6), "y_tune": (10000,), "tuning_ids": (10000,),
            "X_cal": (10000, 6), "y_cal": (10000,), "calibration_ids": (10000,),
        })
        cache = {
            "cache_files": {"test.npz": digest(test_path), "roles/rep_1.npz": digest(role_path)},
            "test_rows": 500000,
            "features": ["mag_ps_g", "mag_ps_r", "mag_ps_i", "mag_ps_z", "mag_ps_y", "gaia_g_mean_mag"],
            "labels": ["A", "F", "G", "K", "M", "GALAXY", "QSO"],
            "roles": {"1": {"source_sha256": MEMBERSHIP, "id_hashes": {"fit_ids": FIT_IDS, "calibration_ids": CAL_IDS}}},
        }
        cache_path = self.root / "cache" / "cache_manifest.json"
        write_json(cache_path, cache)
        baseline_definition = {
            "key": E5_BASE, "experiment": 3, "kind": "fit", "rep": 1,
            "method": "random_forest", "route": "real", "train_key": None, "dependencies": [],
        }
        plan = {"cache_manifest_sha256": digest(cache_path), "role_membership_hashes": {"rep_1": MEMBERSHIP},
                "tasks": [baseline_definition]}
        write_json(self.root / "manifests" / "tasks.json", plan)
        write_json(self.root / "manifests" / "freeze.json", {
            "resource_policy": {"prediction_chunk_rows": 50000},
            "source_sha256": {"science.py": science_sha},
        })

        train_path = self.root / "artifacts" / E5_TRAIN / "data.npz"
        write_headers(train_path, {"X": (80000, 6), "y": (80000,), "ids": (80000,)})
        train_sha = digest(train_path)
        write_json(train_path.parent / "metadata.json", {
            "task_key": E5_TRAIN, "kind": "e5_corruption", "rep": 1,
            "mechanism": "feature_noise", "rate": 0.05, "fit_count": 80000,
        })
        write_json(train_path.parent / "validation.json", {
            "task_key": E5_TRAIN, "status": "validated", "files": {"data.npz": train_sha},
        })
        self.write_fit_artifact(E5_BASE, 3, "real", [], FIT_IDS, baseline=True)
        self.write_fit_artifact(E5_FIT, 5, "direct", [E5_TRAIN, E5_BASE], FIT_IDS, baseline=False, source_sha=train_sha)
        self.definition = {
            "key": E5_EVAL, "experiment": 5, "kind": "eval", "rep": 1,
            "method": "random_forest", "route": "direct", "condition": E5_COND,
            "mechanism": "feature_noise", "rate": 0.05, "fit_key": E5_FIT,
            "dependencies": [E5_FIT],
        }

    def write_fit_artifact(self, key, experiment, route, dependencies, ids_sha, baseline, source_sha=None):
        art = self.root / "artifacts" / key
        art.mkdir(parents=True, exist_ok=True)
        pipe = art / "pipeline.joblib"
        pipe.write_bytes(("unpickled-never-" + key).encode())
        pipe_sha = digest(pipe)
        selection = {"selected_params": EXPECTED}
        write_json(art / "selection.json", selection)
        selection_sha = digest(art / "selection.json")
        task = {
            "key": key, "experiment": experiment, "rep": 1, "method": "random_forest",
            "route": "real" if baseline else route, "train_key": None if baseline else E5_TRAIN,
            "dependencies": [] if baseline else dependencies,
        }
        if not baseline:
            task.update({"condition": E5_COND, "mechanism": "feature_noise", "rate": 0.05,
                         "selection_key": E5_BASE, "selection_mode": "fixed",
                         "selection_policy": "frozen_clean_selected_params_no_retuning", "trials": 0})
        result = {
            "status": "success", "training_rows": 80000, "params": EXPECTED,
            "class_counts": [4519, 17848, 31159, 17127, 6913, 1230, 1204],
            "training_ids_sha256": ids_sha, "training_X_sha256": "4"*64, "training_y_sha256": "5"*64,
            "pipeline_sha256": pipe_sha,
        }
        if source_sha is not None:
            result["source_sha256"] = source_sha
        attempt_id = "attempt-" + ("base" if baseline else "e5")
        task_sha = "6"*64 if baseline else "7"*64
        write_json(art / "fit_result.json", {
            "status": "successful", "attempt_id": attempt_id, "task_sha256": task_sha,
            "task": task, "result": result,
        })
        write_json(art / "fit_publication.json", {
            "stage": "validated_publication", "attempt_id": attempt_id,
            "task_sha256": task_sha, "pipeline_sha256": pipe_sha,
            "published_path": str(pipe),
        })
        write_json(art / "validation.json", {
            "status": "validated", "task_key": key,
            "files": {"pipeline.joblib": pipe_sha, "selection.json": selection_sha},
        })

    def eligible(self, task=None, definition=None):
        return ae.eligible_e5_direct_rf_eval(task or self.task, definition or self.definition, self.root)

    def test_valid_exact_unattempted_e5_eval_gets_provisional_four_gib_profile(self):
        ok, evidence = self.eligible()
        self.assertTrue(ok)
        self.assertEqual(evidence["profile_id"], ae.E5_RF_EVAL_4G_PROFILE_ID)
        self.assertEqual(evidence["reservation_gib"], 4)
        self.assertFalse(evidence["e5_inference_rss_observed"])
        self.assertEqual(evidence["worker_hard_rss_limit_gib"], 10)
        self.assertEqual(ctl.worker_reservation_bytes(self.task), 4 * ctl.GIB)
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        self.assertEqual(ctl.worker_resource_class(self.task), "light")
        self.assertEqual(ctl.e5_rf_eval_profile_for_admission(self.task, 4 * ctl.GIB)[0], ae.E5_RF_EVAL_4G_PROFILE_ID)

    def test_attempted_or_malformed_evaluations_fall_back_to_ten_gib_heavy(self):
        attempted = {**self.task, "attempts": [{"attempt_id": "old"}]}
        self.assertFalse(self.eligible(task=attempted)[0])
        self.assertEqual(ctl.worker_reservation_bytes(attempted), 10 * ctl.GIB)
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        self.assertEqual(ctl.worker_resource_class(attempted), "heavy")
        for field, value in (("kind", "fit"), ("route", "synthetic"), ("method", "arf"), ("condition", "label_noise_10"), ("rate", 0.20), ("rep", 2)):
            changed = copy.deepcopy(self.definition)
            changed[field] = value
            self.assertFalse(self.eligible(definition=changed)[0], field)

    def test_fit_and_cache_integrity_fail_closed(self):
        fit_result = self.root / "artifacts" / E5_FIT / "fit_result.json"
        d = json.loads(fit_result.read_text())
        d["result"]["params"]["n_estimators"] = 500
        write_json(fit_result, d)
        self.assertFalse(self.eligible()[0])

    def test_corrupt_artifact_and_role_or_test_shape_fail_closed(self):
        data = self.root / "artifacts" / E5_TRAIN / "data.npz"
        data.write_bytes(data.read_bytes() + b"changed")
        self.assertFalse(self.eligible()[0])

    def test_profile_class_persists_after_admission_but_promotion_restores_heavy(self):
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        _, evidence = self.eligible()
        persisted = {
            **self.task, "status": "running", "admission_profile_id": ae.E5_RF_EVAL_4G_PROFILE_ID,
            "admission_reservation_bytes": 4*ctl.GIB, "admission_profile_evidence": evidence,
            "attempts": [{"resource_profile": {"admission_profile_id": ae.E5_RF_EVAL_4G_PROFILE_ID,
                                                   "admission_reservation_bytes": 4*ctl.GIB}}],
        }
        self.assertEqual(ctl.worker_resource_class(persisted), "light")
        promoted = {**persisted, "adaptive_promoted_heavy": True}
        self.assertEqual(ctl.worker_resource_class(promoted), "heavy")

    def test_admission_profile_does_not_change_frozen_worker_request(self):
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        task_record = {**self.task, "admission_profile_id": ae.E5_RF_EVAL_4G_PROFILE_ID,
                       "admission_reservation_bytes": 4*ctl.GIB, "attempts": [{"reason": "audit"}]}
        request_task = ctl.worker_request_definition(task_record)
        expected = {**self.definition, "artifact_dir": str(self.root / "artifacts" / E5_EVAL)}
        self.assertEqual(request_task, expected)
        self.assertNotIn("admission_profile_id", request_task)
        self.assertNotIn("admission_reservation_bytes", request_task)

    def test_e5_eval_light_work_can_fill_slot_while_heavy_fit_lane_is_occupied(self):
        ctl.DEFINITIONS = {E5_EVAL: copy.deepcopy(self.definition)}
        running = [{"kind": "fit", "method": "arf", "experiment": 4}]
        heavy_fit = {"kind": "fit", "method": "random_forest", "experiment": 4}
        ordered = ctl.order_ready_for_admission(running, [heavy_fit, self.task])
        self.assertEqual(ordered[0]["kind"], "eval")
        self.assertEqual(ctl.worker_resource_class(ordered[0]), "light")
        self.assertTrue(ctl.light_fit_blocked({"kind": "fit", "method": "logistic"}, True))
        self.assertFalse(ctl.light_fit_blocked(self.task, True))

    def test_baseline_fit_publication_and_selection_manifest_are_required(self):
        base_dir = self.root / "artifacts" / E5_BASE
        fit_path = base_dir / "fit_result.json"
        pub_path = base_dir / "fit_publication.json"
        validation_path = base_dir / "validation.json"
        selection_path = base_dir / "selection.json"
        originals = {p: p.read_bytes() for p in (fit_path, pub_path, validation_path, selection_path)}
        try:
            baseline_fit = json.loads(originals[fit_path])
            baseline_fit["task"]["train_key"] = "wrong/provenance/key"
            write_json(fit_path, baseline_fit)
            self.assertFalse(self.eligible()[0], "baseline train_key must match the frozen task definition")
            fit_path.write_bytes(originals[fit_path])

            pub_path.unlink()
            self.assertFalse(self.eligible()[0], "baseline must have a valid published-fit receipt")
            pub_path.write_bytes(originals[pub_path])

            bad_pub = json.loads(originals[pub_path])
            bad_pub["pipeline_sha256"] = "f" * 64
            write_json(pub_path, bad_pub)
            self.assertFalse(self.eligible()[0], "baseline publication must bind the selected pipeline")
            pub_path.write_bytes(originals[pub_path])

            selection = json.loads(originals[selection_path])
            selection["selected_params"] = {**EXPECTED, "n_estimators": 500}
            write_json(selection_path, selection)
            self.assertFalse(self.eligible()[0], "baseline selected configuration must match E5 fixed selection")
            selection_path.write_bytes(originals[selection_path])

            validation = json.loads(originals[validation_path])
            validation["files"]["selection.json"] = "0" * 64
            write_json(validation_path, validation)
            self.assertFalse(self.eligible()[0], "baseline selection checksum must match its validation manifest")
            validation_path.write_bytes(originals[validation_path])

            selection_path.unlink()
            self.assertFalse(self.eligible()[0], "missing baseline selection must fail closed")
        finally:
            for path, payload in originals.items():
                path.write_bytes(payload)



class E4TreatmentRfEvalProfileTests(unittest.TestCase):
    def setUp(self):
        self.base = E5DirectRfEvalProfileTests()
        self.base.setUp()
        self.root = self.base.root
        receipt_path = self.root / ae.E5_RF_EVAL_4G_RECEIPT
        receipt = json.loads(receipt_path.read_text())
        params500 = {"max_depth": None, "max_features": "sqrt", "min_samples_leaf": 1, "n_estimators": 500}
        params200 = EXPECTED
        rows = []
        conditions = [
            ("A_half_generated_gmm", "generated_gmm", params500, 3869900),
            ("A_half_generated_copula", "generated_copula", params500, 3860524),
            ("A_half_generated_kde", "generated_kde", params200, 1301368),
            ("A_half_generated_chow_liu", "generated_chow_liu", params500, 3860524),
        ]
        for condition, treatment, params, peak in conditions:
            rows.append({
                "eval_key": "e4/rep_1/eval/treatment/random_forest/" + condition,
                "fit_key": "e4/rep_1/fit/treatment/random_forest/" + condition,
                "rep": 1, "condition": condition, "treatment": treatment,
                "fit_rows": 82394, "fit_params": params, "pipeline_match": True,
                "evaluation_test_n": 500000,
                "eval_phase": {"exit_code": 0, "peak_tree_rss_kib": peak, "seconds": 50.0},
            })
        receipt["e4_treatment_rf"] = {"eligible_completed_pairs": rows}
        write_json(receipt_path, receipt)
        ae.E5_RF_EVAL_4G_RECEIPT_SHA256 = digest(receipt_path)
        self.rep = 1
        self.base_counts = [4519, 17848, 31159, 17127, 6913, 1230, 1204]
        self.after_counts = [6913, 17848, 31159, 17127, 6913, 1230, 1204]
        self.train_key = "e4/rep_1/append/A_half/gmm"
        self.fit_key = "e4/rep_1/fit/treatment/random_forest/A_half_generated_gmm"
        self.eval_key = "e4/rep_1/eval/treatment/random_forest/A_half_generated_gmm"
        self.params = params500
        self.build_e4_artifacts()
        self.definition = {
            "key": self.eval_key, "experiment": 4, "kind": "eval", "rep": 1,
            "method": "random_forest", "route": "treatment", "condition": "A_half_generated_gmm",
            "fit_key": self.fit_key, "dependencies": [self.fit_key], "treatment": "generated_gmm",
            "generator": "gmm", "target_label": "A", "target_class": 0, "ratio": 0.5,
        }
        self.task = {**self.definition, "status": "waiting_for_dependency", "attempts": []}
        ctl.R = self.root
        ctl.DEFINITIONS = {self.eval_key: copy.deepcopy(self.definition)}

    def tearDown(self):
        self.base.tearDown()

    def build_e4_artifacts(self):
        parent_key = "e4/rep_1/cohort/A_half"
        parent = self.root / "artifacts" / parent_key
        write_headers(parent / "data.npz", {"X": (80000, 6), "y": (80000,), "ids": (80000,)})
        parent_meta = {"task_key": parent_key, "kind": "e4_cohort", "rep": 1, "condition": "A_half",
                       "N": 80000, "realized_counts": self.base_counts}
        write_json(parent / "metadata.json", parent_meta)
        write_json(parent / "validation.json", {"task_key": parent_key, "status": "validated",
                    "files": {"data.npz": digest(parent / "data.npz")}})

        train = self.root / "artifacts" / self.train_key
        write_headers(train / "data.npz", {"X": (82394, 6), "y": (82394,), "ids": (82394,)})
        train_meta = {"task_key": self.train_key, "kind": "e4_append", "rep": 1,
                      "parent": str(parent), "counts_before": self.base_counts,
                      "counts_after": self.after_counts, "added_count": 2394,
                      "target_class": 0,
                      "generated_artifact": str(self.root / "artifacts/e4/rep_1/generate/A_half/gmm")}
        write_json(train / "metadata.json", train_meta)
        write_json(train / "validation.json", {"task_key": self.train_key, "status": "validated",
                    "files": {"data.npz": digest(train / "data.npz")}})

        art = self.root / "artifacts" / self.fit_key
        art.mkdir(parents=True, exist_ok=True)
        pipe = art / "pipeline.joblib"
        pipe.write_bytes(b"opaque model bytes; never deserialized")
        pipeline_sha = digest(pipe)
        selection = {"selected_params": self.params}
        write_json(art / "selection.json", selection)
        selection_sha = digest(art / "selection.json")
        attempt_id, task_sha = "e4fitattempt", "8" * 64
        fit_task = {"key": self.fit_key, "experiment": 4, "rep": 1, "method": "random_forest",
                    "route": "treatment", "condition": "A_half_generated_gmm", "treatment": "generated_gmm",
                    "generator": "gmm", "train_key": self.train_key, "dependencies": [self.train_key],
                    "selection_mode": "tune", "trials": 10, "selection_key": None,
                    "selection_policy": "tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget"}
        fit_result = {"status": "success", "training_rows": 82394, "class_counts": self.after_counts,
                      "params": self.params, "pipeline_sha256": pipeline_sha,
                      "source_sha256": digest(train / "data.npz"),
                      "training_ids_sha256": "9"*64, "training_X_sha256": "a"*64,
                      "training_y_sha256": "b"*64,
                      "phase_supervision": {"exit_code": 0, "reason": None,
                                            "peak_tree_rss_kib": 3800000, "seconds": 300.0}}
        write_json(art / "fit_result.json", {"status": "successful", "attempt_id": attempt_id,
                    "task_sha256": task_sha, "task": fit_task, "result": fit_result})
        write_json(art / "fit_publication.json", {"stage": "validated_publication", "attempt_id": attempt_id,
                    "task_sha256": task_sha, "pipeline_sha256": pipeline_sha, "published_path": str(pipe)})
        write_json(art / "validation.json", {"task_key": self.fit_key, "status": "validated",
                    "files": {"pipeline.joblib": pipeline_sha, "selection.json": selection_sha}})

    def eligible(self, task=None, definition=None):
        return ae.eligible_e4_treatment_rf_eval(task or self.task, definition or self.definition, self.root)

    def test_exact_published_fit_and_input_receipts_get_narrow_six_gib_light_profile(self):
        ok, evidence = self.eligible()
        self.assertTrue(ok)
        self.assertEqual(evidence["profile_id"], ae.E4_RF_EVAL_6G_PROFILE_ID)
        self.assertEqual(evidence["reservation_gib"], 6)
        self.assertFalse(evidence["this_fit_inference_rss_observed"])
        self.assertEqual(evidence["training_rows"], 82394)
        self.assertEqual(evidence["training_data"]["counts_after"], self.after_counts)
        self.assertEqual(ctl.worker_reservation_bytes(self.task), 6 * ctl.GIB)
        self.assertEqual(ctl.worker_resource_class(self.task), "light")
        self.assertEqual(ctl.e4_rf_eval_profile_for_admission(self.task, 6 * ctl.GIB)[0], ae.E4_RF_EVAL_6G_PROFILE_ID)

    def test_weighted_arf_kde_and_prior_attempts_stay_at_default(self):
        for treatment in ("weighted", "generated_arf", "generated_kde"):
            definition = copy.deepcopy(self.definition)
            definition["treatment"] = treatment
            definition["condition"] = "A_half_" + treatment
            definition["key"] = "e4/rep_1/eval/treatment/random_forest/" + definition["condition"]
            definition["fit_key"] = "e4/rep_1/fit/treatment/random_forest/" + definition["condition"]
            definition["dependencies"] = [definition["fit_key"]]
            record = {**definition, "status": "waiting_for_dependency", "attempts": []}
            self.assertFalse(self.eligible(task=record, definition=definition)[0])
        attempted = {**self.task, "attempts": [{"attempt_id": "prior"}]}
        self.assertFalse(self.eligible(task=attempted)[0])

    def test_missing_or_oversized_final_fit_phase_and_histogram_mismatch_fail_closed(self):
        path = self.root / "artifacts" / self.fit_key / "fit_result.json"
        original = json.loads(path.read_text())
        for phase in (None, {"exit_code": 0, "reason": None, "peak_tree_rss_kib": ae.E4_RF_EVAL_MAX_FIT_PHASE_KIB + 1}):
            doc = copy.deepcopy(original)
            if phase is None:
                doc["result"].pop("phase_supervision", None)
            else:
                doc["result"]["phase_supervision"] = phase
            write_json(path, doc)
            self.assertFalse(self.eligible()[0])
        bad = copy.deepcopy(original)
        bad["result"]["class_counts"][0] -= 1
        write_json(path, bad)
        self.assertFalse(self.eligible()[0])

    def test_request_definition_stays_frozen_and_eval_can_fill_light_slot(self):
        request = ctl.worker_request_definition({**self.task, "admission_profile_id": ae.E4_RF_EVAL_6G_PROFILE_ID,
                                                  "admission_reservation_bytes": 6*ctl.GIB})
        self.assertEqual(request, {**self.definition, "artifact_dir": str(self.root / "artifacts" / self.eval_key)})
        ready = [{"kind": "fit", "experiment": 4, "method": "random_forest"}, self.task]
        ordered = ctl.order_ready_for_admission([{"kind": "fit", "method": "arf"}], ready)
        self.assertEqual(ordered[0]["kind"], "eval")



if __name__ == "__main__":
    unittest.main()
