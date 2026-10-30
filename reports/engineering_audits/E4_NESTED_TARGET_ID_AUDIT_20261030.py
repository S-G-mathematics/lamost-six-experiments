#!/usr/bin/env python3
"""Read-only E4 nested cohort ID/label audit; intentionally never accesses X members."""
import collections
import datetime as dt
import hashlib
import json
import os
import resource
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/lamost_e1_migration_20261023")
R = ROOT / "runtime_20261025"
REPORT_DIR = R / "reports" / "engineering_audits"
SCRIPT_PATH = REPORT_DIR / "E4_NESTED_TARGET_ID_AUDIT_20261030.py"
RECEIPT_PATH = REPORT_DIR / "E4_NESTED_TARGET_ID_AUDIT_20261030.json"
THREAD_KEYS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def arr_sha(array):
    a = np.ascontiguousarray(array)
    return sha_bytes(memoryview(a).cast("B"))


def producer_array_sha(array):
    # E4 cohort metadata uses cohorts._dig: dtype + shape + raw array bytes.
    a = np.ascontiguousarray(array)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode())
    h.update(str(a.shape).encode())
    h.update(a.view(np.uint8))
    return h.hexdigest()


def json_sha(path):
    return sha_bytes(Path(path).read_bytes())


def load_registry_e4():
    db = sqlite3.connect(f"file:{R / 'registry.sqlite'}?mode=ro", uri=True)
    try:
        rows = {}
        for key, raw in db.execute("SELECT key, record FROM tasks WHERE key LIKE 'e4/%'"):
            rows[key] = json.loads(raw)
        return rows
    finally:
        db.close()


def load_npz_members(path, *names):
    # Access only explicitly named NPZ members. No X or prediction members are read.
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name] for name in names}


def overlap_count(a, b):
    return int(np.intersect1d(a, b, assume_unique=True).size)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(not RECEIPT_PATH.exists(), f"receipt already exists: {RECEIPT_PATH}")
    cache_manifest_path = R / "cache" / "cache_manifest.json"
    cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
    cache_manifest_hash = json_sha(cache_manifest_path)
    registry = load_registry_e4()
    e4_cohorts = {k: v for k, v in registry.items() if v.get("kind") == "e4_cohort"}
    require(len(e4_cohorts) == 42, f"expected 42 current E4 cohort records, found {len(e4_cohorts)}")

    # The test NPZ contributes only its ID vector. No X/y test member is read.
    test_npz = R / "cache" / "test.npz"
    test_ids = load_npz_members(test_npz, "ids")["ids"]
    require(test_ids.ndim == 1 and len(test_ids) == 500000, "test ID vector shape mismatch")
    require(len(np.unique(test_ids)) == len(test_ids), "duplicate test IDs")
    test_ids_hash = arr_sha(test_ids)

    rep_baselines = {}
    rep_receipts = {}
    for rep in (1, 2, 3):
        role_path = R / "cache" / "roles" / f"rep_{rep}.npz"
        members = load_npz_members(role_path, "fit_ids", "y_fit", "tuning_ids", "calibration_ids")
        fit_ids, y_fit = members["fit_ids"], members["y_fit"]
        tune_ids, cal_ids = members["tuning_ids"], members["calibration_ids"]
        require(len(fit_ids) == 80000 and len(y_fit) == 80000, f"rep {rep}: fit shape mismatch")
        require(len(tune_ids) == 10000 and len(cal_ids) == 10000, f"rep {rep}: tune/cal shape mismatch")
        for name, ids in (("fit", fit_ids), ("tuning", tune_ids), ("calibration", cal_ids), ("test", test_ids)):
            require(ids.ndim == 1 and len(np.unique(ids)) == len(ids), f"rep {rep}: {name} IDs are not unique")
        role_meta = cache_manifest["roles"][str(rep)]
        fit_counts = np.bincount(y_fit.astype(np.int64), minlength=7).astype(int).tolist()
        require(fit_counts == role_meta["fit_counts"], f"rep {rep}: fit-label counts disagree with cache manifest")
        role_id_hashes = role_meta["id_hashes"]
        require(arr_sha(fit_ids) == role_id_hashes["fit_ids"], f"rep {rep}: fit ID hash mismatch")
        require(arr_sha(tune_ids) == role_id_hashes["tuning_ids"], f"rep {rep}: tuning ID hash mismatch")
        require(arr_sha(cal_ids) == role_id_hashes["calibration_ids"], f"rep {rep}: calibration ID hash mismatch")
        role_overlap = {
            "fit_vs_tuning": overlap_count(fit_ids, tune_ids),
            "fit_vs_calibration": overlap_count(fit_ids, cal_ids),
            "fit_vs_test": overlap_count(fit_ids, test_ids),
            "tuning_vs_calibration": overlap_count(tune_ids, cal_ids),
            "tuning_vs_test": overlap_count(tune_ids, test_ids),
            "calibration_vs_test": overlap_count(cal_ids, test_ids),
        }
        require(all(v == 0 for v in role_overlap.values()), f"rep {rep}: role overlap: {role_overlap}")
        rep_baselines[rep] = {
            "fit_ids": fit_ids,
            "y_fit": y_fit,
            "fit_ids_by_class": {c: fit_ids[y_fit == c] for c in range(7)},
            "reserved_ids": {"tuning": tune_ids, "calibration": cal_ids, "test": test_ids},
            "fit_label_counts": fit_counts,
        }
        rep_receipts[rep] = {
            "role_cache_path": str(role_path),
            "role_cache_stat": {"size_bytes": role_path.stat().st_size, "mtime_ns": role_path.stat().st_mtime_ns},
            "expected_role_cache_sha256_from_cache_manifest": cache_manifest["cache_files"][f"roles/rep_{rep}.npz"],
            "fit_ids_sha256": arr_sha(fit_ids),
            "fit_y_sha256": arr_sha(y_fit),
            "tuning_ids_sha256": arr_sha(tune_ids),
            "calibration_ids_sha256": arr_sha(cal_ids),
            "role_id_hashes_match_cache_manifest": True,
            "fit_rows": len(fit_ids),
            "tuning_rows": len(tune_ids),
            "calibration_rows": len(cal_ids),
            "fit_label_counts": fit_counts,
            "role_overlap_counts": role_overlap,
        }
    require(cache_manifest["cache_files"]["test.npz"] != "", "cache manifest lacks test archive hash")

    cohort_receipts = []
    pair_receipts = []
    for rep in (1, 2, 3):
        baseline = rep_baselines[rep]
        seen_labels = {}
        cohorts = {}
        conditions_by_target_ratio = {}
        for key, record in e4_cohorts.items():
            if int(record.get("rep", -1)) != rep:
                continue
            condition = str(record.get("condition", ""))
            target_class = int(record["target_class"])
            ratio = float(record["ratio"])
            require(record.get("outcome") == "successful", f"{key}: current outcome not successful")
            require(record.get("status") == "validated_terminal" and record.get("validation_state") == "validated",
                    f"{key}: task is not validated terminal success")
            require(record.get("nested_target_subsets") is True, f"{key}: nested-target flag missing")
            require(record.get("shared_other_class_permutations") is True, f"{key}: shared-permutation flag missing")
            meta = record["result"]["metadata"]
            require(meta.get("N") == 80000 and meta.get("per_class_prefix_sampling") is True,
                    f"{key}: metadata does not declare 80k per-class prefix sampling")
            require(meta.get("tune_calibration_reserved") is True, f"{key}: reserved-role flag missing")
            require(meta.get("target_class") == target_class and meta.get("ratio") == ratio,
                    f"{key}: registry/metadata target or ratio mismatch")
            require(meta.get("source_fit_counts") == baseline["fit_label_counts"],
                    f"{key}: source fit class counts disagree with unchanged fit role")
            data_path = Path(record["artifact_dir"]) / "data.npz"
            meta_path = Path(record["artifact_dir"]) / "metadata.json"
            validation_path = Path(record["artifact_dir"]) / "validation.json"
            saved_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            require(saved_meta == meta, f"{key}: artifact metadata differs from current registry metadata")
            validation_sha = validation.get("files", {}).get("data.npz")
            registry_sha = record["result"].get("validation", {}).get("files", {}).get("data.npz")
            require(validation.get("status") == "validated" and validation.get("task_key") == key,
                    f"{key}: saved validation record invalid")
            require(validation_sha and validation_sha == registry_sha, f"{key}: validation SHA disagrees with registry")
            arrays = load_npz_members(data_path, "ids", "y")
            ids, labels = arrays["ids"], arrays["y"]
            require(ids.ndim == 1 and labels.ndim == 1 and len(ids) == len(labels) == 80000,
                    f"{key}: cohort ID/label shape mismatch")
            require(len(np.unique(ids)) == len(ids), f"{key}: duplicate cohort IDs")
            counts = np.bincount(labels.astype(np.int64), minlength=7).astype(int).tolist()
            require(counts == meta["realized_counts"] and counts == meta["planned_counts"],
                    f"{key}: cohort label counts disagree with metadata")
            require(producer_array_sha(ids) == meta["ids_sha256"], f"{key}: producer ID digest disagrees with metadata")
            require(len(np.unique(labels)) == 7, f"{key}: not all 7 labels present")
            reserve_overlap = {name: overlap_count(ids, rids) for name, rids in baseline["reserved_ids"].items()}
            require(all(v == 0 for v in reserve_overlap.values()), f"{key}: overlap with reserved IDs: {reserve_overlap}")

            # Altered target-class IDs must be drawn from the unchanged fit target pool.
            class_ids = {c: ids[labels == c] for c in range(7)}
            require(len(np.intersect1d(class_ids[target_class], baseline["fit_ids_by_class"][target_class],
                                       assume_unique=True)) == len(class_ids[target_class]),
                    f"{key}: altered target IDs are not a subset of unchanged fit target IDs")
            # All unchanged fit IDs for non-target classes remain, with added rows drawn only
            # from non-reserved IDs. Existing IDs retain their unchanged source label.
            fit_by_id = {int(i): int(y) for i, y in zip(baseline["fit_ids"], baseline["y_fit"])}
            for cls in range(7):
                if cls != target_class:
                    require(len(np.intersect1d(baseline["fit_ids_by_class"][cls], class_ids[cls],
                                                assume_unique=True)) == len(baseline["fit_ids_by_class"][cls]),
                            f"{key}: unchanged fit IDs for class {cls} were omitted")
            for i, y in zip(ids, labels):
                ii, yy = int(i), int(y)
                if ii in fit_by_id:
                    require(fit_by_id[ii] == yy, f"{key}: label changed for unchanged fit ID {ii}")
                prior = seen_labels.setdefault(ii, yy)
                require(prior == yy, f"{key}: same ID has inconsistent labels across cohorts")
            ratio_key = (target_class, ratio)
            require(ratio_key not in conditions_by_target_ratio, f"rep {rep}: duplicate target/ratio cohort")
            conditions_by_target_ratio[ratio_key] = key
            cohorts[key] = {"ids": ids, "labels": labels, "class_ids": class_ids,
                            "target_class": target_class, "ratio": ratio, "condition": condition}
            cohort_receipts.append({
                "task_key": key,
                "condition": condition,
                "target_class": target_class,
                "ratio": ratio,
                "rows": len(ids),
                "ids_unique": True,
                "label_counts": counts,
                "ids_component_sha256": arr_sha(ids),
                "labels_component_sha256": arr_sha(labels),
                "metadata_ids_sha256": meta["ids_sha256"],
                "producer_ids_digest_sha256": producer_array_sha(ids),
                "validation_path": str(validation_path),
                "validation_json_sha256": json_sha(validation_path),
                "validated_data_npz_sha256_from_saved_validation": validation_sha,
                "reserved_id_overlap_counts": reserve_overlap,
                "fit_target_subset_passed": True,
                "all_unchanged_non_target_fit_ids_retained": True,
                "shared_id_labels_consistent": True,
            })
        require(len(conditions_by_target_ratio) == 14, f"rep {rep}: expected 14 target/ratio cohorts")
        for target in range(7):
            half = cohorts[conditions_by_target_ratio[(target, 0.5)]]
            tenth = cohorts[conditions_by_target_ratio[(target, 0.1)]]
            half_target = half["class_ids"][target]
            tenth_target = tenth["class_ids"][target]
            target_intersection = overlap_count(tenth_target, half_target)
            require(target_intersection == len(tenth_target),
                    f"rep {rep} target {target}: tenth target IDs are not subset of half")
            non_target_checks = []
            for cls in range(7):
                if cls == target:
                    continue
                hids, tids = half["class_ids"][cls], tenth["class_ids"][cls]
                intersection = overlap_count(hids, tids)
                require(intersection == len(hids),
                        f"rep {rep} target {target} other class {cls}: half IDs not subset of tenth")
                non_target_checks.append({"class": cls, "half_rows": len(hids), "tenth_rows": len(tids),
                                          "half_in_tenth": intersection})
            pair_receipts.append({
                "rep": rep,
                "target_class": target,
                "half_key": conditions_by_target_ratio[(target, 0.5)],
                "tenth_key": conditions_by_target_ratio[(target, 0.1)],
                "target_tenth_rows": len(tenth_target),
                "target_tenth_ids_in_half": target_intersection,
                "non_target_half_subset_checks": non_target_checks,
                "row_order_prefix_tested": False,
                "row_order_note": "Cohort NPZ row order is not the saved per-class permutation order; set nesting was checked.",
            })

    # Public-safe projection of the audited cohort task records; excludes PID/PGID/process fields.
    projection = []
    for key in sorted(e4_cohorts):
        d = e4_cohorts[key]
        m = d["result"]["metadata"]
        projection.append({
            "key": key, "rep": d.get("rep"), "condition": d.get("condition"),
            "target_class": d.get("target_class"), "ratio": d.get("ratio"),
            "outcome": d.get("outcome"), "status": d.get("status"),
            "validation_state": d.get("validation_state"),
            "data_npz_sha256": d["result"]["validation"]["files"]["data.npz"],
            "metadata_ids_sha256": m.get("ids_sha256"),
        })
    projection_sha = sha_bytes(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode())
    peak_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    require(peak_rss_bytes < 2 * 1024**3, f"peak RSS exceeded 2 GiB: {peak_rss_bytes}")
    receipt = {
        "schema_version": "lamost-e4-nested-target-id-audit/1",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime": str(R),
        "audit_script_path": str(SCRIPT_PATH),
        "audit_script_sha256": json_sha(SCRIPT_PATH),
        "registry_path": str(R / "registry.sqlite"),
        "registry_projection_sha256": projection_sha,
        "e4_registry_record_count": len(registry),
        "e4_cohort_count": len(e4_cohorts),
        "cache_manifest_path": str(cache_manifest_path),
        "cache_manifest_sha256": cache_manifest_hash,
        "method": {
            "accessed_npz_members": ["cohort.ids", "cohort.y", "roles.fit_ids", "roles.y_fit",
                                     "roles.tuning_ids", "roles.calibration_ids", "test.ids"],
            "feature_arrays_accessed": False,
            "prediction_arrays_accessed": False,
            "models_loaded": False,
            "fitting_or_inference": False,
            "raw_id_values_in_receipt": False,
        },
        "resource_guard": {
            "requested_ram_limit_bytes": 2147483648,
            "observed_peak_rss_bytes": peak_rss_bytes,
            "cpu_threads": 1,
            "nice": 19,
            "wall_limit_seconds": 180,
            "openblas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "omp_threads": os.environ.get("OMP_NUM_THREADS"),
        },
        "test_ids": {"path": str(test_npz), "rows": len(test_ids), "ids_component_sha256": test_ids_hash,
                     "expected_archive_sha256_from_cache_manifest": cache_manifest["cache_files"]["test.npz"]},
        "role_replicates": rep_receipts,
        "cohort_records": sorted(cohort_receipts, key=lambda x: x["task_key"]),
        "nested_pairs": pair_receipts,
        "summary": {
            "cohorts": len(cohort_receipts),
            "half_tenth_pairs": len(pair_receipts),
            "target_subset_checks_passed": len(pair_receipts),
            "other_class_subset_checks_passed": sum(len(x["non_target_half_subset_checks"]) for x in pair_receipts),
            "reserved_role_overlap_checks_passed": len(cohort_receipts) * 3,
            "all_checks_passed": True,
        },
        "limitations": [
            "The selected NPZ members were read directly; feature members were not accessed.",
            "The check verifies ID-set nesting. Row order in the cohort NPZs is not the saved per-class permutation order, so it does not claim sequence-prefix identity.",
            "The audit binds cohort data to existing validation JSON hashes rather than rereading/hash-scanning full cohort NPZ files.",
        ],
    }
    tmp = RECEIPT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp, RECEIPT_PATH)
    print(json.dumps({"receipt_path": str(RECEIPT_PATH), "receipt_sha256": json_sha(RECEIPT_PATH),
                      "peak_rss_bytes": peak_rss_bytes, "summary": receipt["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()

