"""Fail-closed prospective RF4 reservation gate for E4 repetition 3.

This module only estimates scheduler admission reservation. It never changes
scientific limits, models, task definitions, or results.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import stat
import zipfile
import numpy as np

PROFILE_ID = "e4-rep3-rf4-treatment-fit-admission-6gib-20261028-v1"
FREEZE_POLICY_FIELD = "rf4_e4_rep3_treatment_6g_admission_sha256"
POLICY_REL = pathlib.Path("manifests/RF4_E4_REP3_TREATMENT_6GIB_ADMISSION_20261028.json")
EVIDENCE_REL = pathlib.Path("reports/RF4_E4_REP3_TREATMENT_6GIB_ADMISSION_EVIDENCE_20261028.json")
EXPECTED_METHOD = "random_forest"
EXPECTED_TRIALS = 10
MIN_ROWS = 80000
MAX_ROWS = 125955
SOURCE_PATHS = {
    "parallel_rf/worker.py": pathlib.Path("source/parallel_rf/worker.py"),
    "parallel_rf/phase_worker.py": pathlib.Path("source/parallel_rf/phase_worker.py"),
    "parallel_rf/science.py": pathlib.Path("source/parallel_rf/science.py"),
}

def _sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def _json(path):
    try:
        value = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None



def header_shapes(npz_path, expected_shapes):
    """Bounded NPZ/NPY-header reader; never materializes predictor/label arrays.

    Return {name: tuple(shape)} only when the ZIP member set is exact, every
    NPY header is supported and <=64 KiB, and the file identity is stable over
    the read. The caller compares returned shapes with its expected shapes.
    """
    try:
        path = pathlib.Path(npz_path).absolute()
        # Refuse symlinks at the artifact path or any ancestor.
        cursor = path
        while cursor != cursor.parent:
            if cursor.is_symlink():
                return None
            cursor = cursor.parent
        before = path.stat(follow_symlinks=False)
        ident = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if not stat.S_ISREG(before.st_mode):
            return None
        if not isinstance(expected_shapes, dict) or not expected_shapes:
            return None
        names = {str(name) + ".npy" for name in expected_shapes}
        out = {}
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            actual_names = [i.filename for i in infos]
            if len(actual_names) != len(names) or set(actual_names) != names or len(set(actual_names)) != len(actual_names):
                return None
            for name in expected_shapes:
                with zf.open(str(name) + ".npy", "r") as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, _ = np.lib.format.read_array_header_1_0(stream, max_header_size=65536)
                    elif version in ((2, 0), (3, 0)):
                        shape, _, _ = np.lib.format.read_array_header_2_0(stream, max_header_size=65536)
                    else:
                        return None
                    out[str(name)] = tuple(shape)
        after = path.stat(follow_symlinks=False)
        ident_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if ident_after != ident:
            return None
        return out
    except (OSError, ValueError, TypeError, KeyError, EOFError, zipfile.BadZipFile, OverflowError):
        return None

def _safe_artifact(runtime, key):
    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key:
        return None
    parts = pathlib.PurePosixPath(key).parts
    if any(p in ("", ".", "..") for p in parts):
        return None
    base = (pathlib.Path(runtime) / "artifacts").resolve()
    path = base / pathlib.Path(*parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(base)
        cursor = base
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return None
    except (OSError, ValueError):
        return None
    if not resolved.is_dir():
        return None
    return resolved

def _never_attempted(task):
    if not isinstance(task, dict):
        return False
    if task.get("status") not in ("planned", "waiting_dependency", "waiting_for_dependency"):
        return False
    if task.get("attempts") or task.get("admission_reservation_bytes") is not None:
        return False
    if any(task.get(k) is not None for k in ("pid", "process_start_ticks", "request_path", "result_path", "controller_attempt_id")):
        return False
    return True

def eligible(task, definition, dep, frozen, runtime, header_validator):
    """Return evidence dict for a prospective 6-GiB admission, else None.

    dep is the current registry record for the exact train_key dependency.
    header_validator(npz_path, expected_shapes) must inspect NPZ headers only
    and return actual shapes or a falsey value on any mismatch/error.
    Root/controller must install the qualified policy and bind its SHA in
    freeze.json[FREEZE_POLICY_FIELD] before this can admit work.
    """
    try:
        root = pathlib.Path(runtime).resolve()
        if not all(isinstance(x, dict) for x in (task, definition, dep, frozen)):
            return None
        if not _never_attempted(task):
            return None
        key = definition.get("key")
        train_key = definition.get("train_key")
        condition = definition.get("condition")
        treatment = definition.get("treatment")
        if (definition.get("experiment") != 4 or definition.get("rep") != 3
            or definition.get("kind") != "fit" or definition.get("route") != "treatment"
            or definition.get("method") != EXPECTED_METHOD
            or not isinstance(key, str) or task.get("key") != key
            or not isinstance(condition, str) or not isinstance(treatment, str)):
            return None
        if key != f"e4/rep_3/fit/treatment/random_forest/{condition}":
            return None
        expected_train = train_key
        if not isinstance(expected_train, str) or definition.get("dependencies") != [expected_train]:
            return None
        if definition.get("selection_mode") != "tune" or definition.get("trials") != EXPECTED_TRIALS:
            return None
        if definition.get("selection_policy") != "tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget":
            return None
        if (definition.get("selection_key") is not None or definition.get("selection_source") is not None
            or definition.get("reuse_pipeline") not in (None, False)
            or definition.get("checkpoint") not in (None, False)):
            return None
        for field in ("experiment", "rep", "kind", "method", "route", "condition",
                      "treatment", "generator", "train_key", "dependencies",
                      "selection_mode", "selection_policy", "selection_key",
                      "selection_source", "trials", "seed", "optimizer_seed"):
            if task.get(field) != definition.get(field):
                return None
        if task.get("attempts") or task.get("admission_reservation_bytes") is not None:
            return None
        if dep.get("key", dep.get("task_key")) != expected_train:
            return None
        if dep.get("status") not in ("validated_terminal", "successful", "success"):
            return None

        policy_path = root / POLICY_REL
        policy_sha = _sha(policy_path)
        if frozen.get(FREEZE_POLICY_FIELD) != policy_sha:
            return None
        policy = _json(policy_path)
        if (not policy or policy.get("schema_version") != "lamost-rf4-e4-rep3-admission-policy/1"
            or policy.get("supplement_module_sha256") != _sha(pathlib.Path(__file__))):
            return None
        resource_rel = pathlib.Path(policy.get("resource_evidence_path", ""))
        if (resource_rel.is_absolute() or ".." in resource_rel.parts
            or _sha(root / resource_rel) != policy.get("resource_evidence_sha256")):
            return None
        if policy.get("status") != "qualified" or policy.get("profile_id") != PROFILE_ID:
            return None
        if policy.get("reservation_gib") != 6 or policy.get("hard_rss_limit_gib") != 10:
            return None
        if policy.get("trial_timeout_seconds") != 600 or policy.get("phase_timeout_seconds") != 600:
            return None
        if policy.get("termination_grace_seconds") != 30 or policy.get("dynamic_promotion_to_hard_limit") is not True:
            return None
        if policy.get("plan_sha256") != frozen.get("plan_sha256"):
            return None
        plan_summary_path = root / "manifests/plan_summary.json"
        if _sha(plan_summary_path) != policy.get("plan_summary_sha256"):
            return None
        plan_summary = _json(plan_summary_path)
        if not plan_summary or (plan_summary.get("role_membership_hashes") or {}).get("rep_3") != policy.get("role_source_sha256"):
            return None
        plan_path = root / "manifests/tasks.json"
        if _sha(plan_path) != policy.get("tasks_sha256") or frozen.get("plan_sha256") != policy.get("tasks_sha256"):
            return None
        source_map = frozen.get("source_sha256") or {}
        policy_sources = policy.get("source_pins") or {}
        if not isinstance(source_map, dict) or set(policy_sources) != set(SOURCE_PATHS):
            return None
        for name, rel in SOURCE_PATHS.items():
            expected = policy_sources.get(name)
            frozen_hash = source_map.get(name)
            if not isinstance(expected, str) or frozen_hash != expected:
                return None
            actual_path = root / rel
            if _sha(actual_path) != expected:
                return None

        evidence_rel = pathlib.Path(policy.get("evidence_path", ""))
        if evidence_rel != EVIDENCE_REL:
            return None
        evidence_path = root / evidence_rel
        if _sha(evidence_path) != policy.get("evidence_sha256"):
            return None
        evidence = _json(evidence_path)
        if (not evidence or evidence.get("schema_version") != "lamost-e4-rep3-rf4-admission-evidence/1"
            or evidence.get("tasks_sha256") != policy.get("tasks_sha256")
            or evidence.get("plan_sha256") != policy.get("plan_sha256")
            or evidence.get("source_pins") != policy_sources):
            return None
        role = evidence.get("role_evidence") or {}
        role_path = root / "cache" / "roles/rep_3.npz"
        cache_manifest_path = root / "cache/cache_manifest.json"
        if _sha(cache_manifest_path) != policy.get("cache_manifest_sha256"):
            return None
        cache_manifest = _json(cache_manifest_path)
        cache_role = ((cache_manifest or {}).get("roles") or {}).get("3") or {}
        if ((cache_manifest or {}).get("features") != ["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"]
            or (cache_manifest or {}).get("labels") != ["A","F","G","K","M","GALAXY","QSO"]
            or sum(cache_role.get("fit_counts", [])) != 80000
            or _sha(role_path) != policy.get("role_cache_sha256")
            or role.get("role_cache_sha256") != policy.get("role_cache_sha256")
            or role.get("role_cache_manifest_sha256") != policy.get("role_cache_sha256")
            or (cache_manifest or {}).get("cache_files", {}).get("roles/rep_3.npz") != policy.get("role_cache_sha256")
            or cache_role.get("source_sha256") != policy.get("role_source_sha256")
            or role.get("role_source_sha256") != policy.get("role_source_sha256")
            or role.get("role_source_actual_sha256") != policy.get("role_source_sha256")
            or cache_role.get("id_hashes") != role.get("role_id_hashes")):
            return None
        role_source = pathlib.Path(role.get("role_source_path", ""))
        expected_role_source = root.parent / "project/benchmark/results/e1/rep_3/n_100000/role_membership.npz"
        if (role_source.resolve() != expected_role_source.resolve()
            or not role_source.is_file() or _sha(role_source) != policy.get("role_source_sha256")):
            return None
        for resource in policy.get("empirical_resource_evidence_sources", []):
            if not isinstance(resource, dict):
                return None
            resource_path = pathlib.Path(resource.get("path", ""))
            if resource_path.is_absolute() or ".." in resource_path.parts:
                return None
            if _sha(root / resource_path) != resource.get("sha256"):
                return None

        entries = [x for x in evidence.get("tasks", []) if isinstance(x, dict) and x.get("task_key") == key]
        if len(entries) != 1:
            return None
        row = entries[0]
        if not row.get("eligible_candidate") or row.get("attempt_count") != 0 or row.get("train_key") != expected_train:
            return None
        if row.get("treatment") != treatment or row.get("condition") != condition:
            return None
        dep_dir = _safe_artifact(root, expected_train)
        if dep_dir is None:
            return None
        meta_path, val_path, data_path = dep_dir / "metadata.json", dep_dir / "validation.json", dep_dir / "data.npz"
        if _sha(meta_path) != row.get("metadata_sha256") or _sha(val_path) != row.get("validation_sha256"):
            return None
        metadata, validation = _json(meta_path), _json(val_path)
        if (not metadata or not validation or validation.get("status") != "validated"
            or validation.get("task_key") != expected_train
            or metadata.get("task_key") != expected_train):
            return None
        base = condition.removesuffix("_" + treatment)
        if not base or base.split("_", 1)[0] not in ("A", "F", "G", "K", "M", "GALAXY", "QSO"):
            return None
        cohort_key = f"e4/rep_3/cohort/{base}"
        cohort_dir = _safe_artifact(root, cohort_key)
        if cohort_dir is None:
            return None
        cohort_meta, cohort_validation = _json(cohort_dir / "metadata.json"), _json(cohort_dir / "validation.json")
        cohort_counts = (cohort_meta or {}).get("realized_counts")
        if (not cohort_meta or not cohort_validation or cohort_meta.get("kind") != "e4_cohort"
            or cohort_meta.get("task_key") != cohort_key or cohort_validation.get("status") != "validated"
            or cohort_validation.get("task_key") != cohort_key or cohort_meta.get("N") != 80000
            or cohort_meta.get("tune_calibration_reserved") is not True
            or not isinstance(cohort_counts, list) or len(cohort_counts) != 7
            or any(type(x) is not int or x < 0 for x in cohort_counts) or sum(cohort_counts) != 80000):
            return None
        target = ("A", "F", "G", "K", "M", "GALAXY", "QSO").index(base.split("_", 1)[0])
        if treatment == "weighted" or treatment in ("ros", "smote"):
            if metadata.get("kind") != "e4_treatment" or metadata.get("treatment") != treatment:
                return None
            if pathlib.Path(str(metadata.get("parent", ""))).resolve() != (root / "artifacts" / cohort_key).resolve():
                return None
            expected_count = 80000 if treatment == "weighted" else (row.get("data_header_shapes") or {}).get("X", [None])[0]
            if treatment == "weighted":
                counts = metadata.get("counts")
                if (not isinstance(counts, list) or len(counts) != 7
                    or any(type(x) is not int or x < 0 for x in counts)
                    or sum(counts) != expected_count or counts != cohort_counts
                    or metadata.get("added_count") != 0):
                    return None
            else:
                before, after, added = metadata.get("counts_before"), metadata.get("counts_after"), metadata.get("added_count")
                if (not isinstance(before, list) or len(before) != 7
                    or any(type(x) is not int or x < 0 for x in before)
                    or before != cohort_counts
                    or not isinstance(after, list) or len(after) != 7
                    or any(type(x) is not int or x < 0 for x in after)
                    or type(added) is not int or added < 0
                    or (metadata.get("target_class") is not None and metadata.get("target_class") != target)):
                    return None
                expected_after = list(cohort_counts)
                expected_after[target] += added
                if after != expected_after or sum(after) != expected_count:
                    return None
        elif treatment.startswith("generated_"):
            generator = treatment[len("generated_"):]
            if generator not in ("gmm", "copula", "arf", "kde", "chow_liu") or metadata.get("kind") != "e4_append":
                return None
            if pathlib.Path(str(metadata.get("parent", ""))).resolve() != (root / "artifacts" / cohort_key).resolve():
                return None
            gkey = f"e4/rep_3/generate/{base}/{generator}"
            if metadata.get("generated_artifact") != str(root / "artifacts" / gkey):
                return None
            before, after, added = metadata.get("counts_before"), metadata.get("counts_after"), metadata.get("added_count")
            if (not isinstance(before, list) or len(before) != 7 or any(type(x) is not int for x in before)
                or not isinstance(after, list) or len(after) != 7 or any(type(x) is not int for x in after)
                or type(added) is not int or added < 0 or metadata.get("target_class") != target):
                return None
            expected_after = list(before)
            expected_after[target] += added
            if before != cohort_counts or after != expected_after or sum(after) != (row.get("data_header_shapes") or {}).get("X", [None])[0]:
                return None
            gdir = _safe_artifact(root, gkey)
            if gdir is None:
                return None
            gr, gv = _json(gdir / "generation_result.json"), _json(gdir / "validation.json")
            if (not gr or not gv or gr.get("status") != "successful" or (gr.get("result") or {}).get("status") != "success"
                or gv.get("status") != "validated" or gv.get("task_key") != gkey
                or gv.get("files", {}).get("data.npz") != (gr.get("result") or {}).get("data_sha256")
                or (gr.get("task") or {}).get("key") != gkey
                or (gr.get("task") or {}).get("fit_key") != f"e4/rep_3/fit/direct/{generator}/{base}"
                or (gr.get("task") or {}).get("cohort_key") != cohort_key
                or (gr.get("task") or {}).get("target_class") != target
                or (gr.get("task") or {}).get("restored_share") != "original_target_share"
                or (gr.get("result") or {}).get("n_rows") != added):
                return None
        else:
            return None
        if validation.get("files", {}).get("data.npz") != row.get("data_validation_sha256"):
            return None
        st = data_path.stat()
        if not data_path.is_file() or st.st_size != row.get("data_size_bytes"):
            return None
        shapes = row.get("data_header_shapes") or {}
        rows = (shapes.get("X") or [None])[0]
        if type(rows) is not int or rows < MIN_ROWS or rows > MAX_ROWS:
            return None
        if shapes.get("X") != [rows, 6] or shapes.get("y") != [rows] or shapes.get("ids") != [rows]:
            return None
        expected_shapes = {"X": (rows, 6), "y": (rows,), "ids": (rows,)}
        if treatment == "weighted":
            if rows != 80000 or shapes.get("sample_weight") != [80000]:
                return None
            expected_shapes["sample_weight"] = (80000,)
            mean = metadata.get("sample_weight_mean")
            if isinstance(mean, bool) or not isinstance(mean, (int, float)) or abs(float(mean) - 1.0) > 1e-12:
                return None
        elif "sample_weight" in shapes:
            return None
        actual_shapes = header_validator(data_path, expected_shapes) if header_validator is not None else header_shapes(data_path, expected_shapes)
        if not isinstance(actual_shapes, dict) or actual_shapes != expected_shapes:
            return None

        fit_dir = root / "artifacts" / pathlib.Path(*pathlib.PurePosixPath(key).parts)
        if fit_dir.exists():
            return None
        return {
            "profile_id": PROFILE_ID, "reservation_gib": 6,
            "reason": "prospective rep3 RF4 reservation; dependency and source identities are pinned; estimate only",
            "experiment": 4, "rep": 3, "condition": condition, "treatment": treatment,
            "train_key": expected_train, "training_rows": rows,
            "training_header_shapes": {k: list(v) for k, v in actual_shapes.items()},
            "dependency_metadata_sha256": row["metadata_sha256"],
            "dependency_validation_sha256": row["validation_sha256"],
            "dependency_data_sha256_from_validation": row["data_validation_sha256"],
            "parent_cohort_key": cohort_key, "parent_class_counts": list(cohort_counts),
            "role_cache_sha256": policy["role_cache_sha256"],
            "resource_evidence_sha256": policy["resource_evidence_sha256"],
            "policy_sha256": policy_sha, "evidence_sha256": policy["evidence_sha256"],
            "hard_rss_limit_gib": 10, "trial_timeout_seconds": 600,
            "phase_timeout_seconds": 600, "termination_grace_seconds": 30,
            "dynamic_promotion_to_hard_limit": True,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None
