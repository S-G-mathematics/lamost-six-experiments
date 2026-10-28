"""Independently validate frozen LAMOST baseline artifacts without model training."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = ROOT / ".deps"
if LOCAL_DEPS.is_dir() and str(LOCAL_DEPS) not in sys.path:
    sys.path.insert(0, str(LOCAL_DEPS))

import duckdb

FEATURES = [
    "mag_ps_g",
    "mag_ps_r",
    "mag_ps_i",
    "mag_ps_z",
    "mag_ps_y",
    "gaia_g_mean_mag",
]
LABELS = ["A", "F", "G", "K", "M", "GALAXY", "QSO"]
EXPECTED = {
    "test": 500_000,
    "development": 1_000_000,
    "reference_fit": 800_000,
    "reference_tune": 200_000,
}
BOUNDS = (-30.0, 50.0)
REPORT_PATH = ROOT / "audit" / "independent_validation.json"


def _sql_path(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    rows = con.execute(sql).fetchall()
    if not rows:
        raise RuntimeError("scalar query returned no rows")
    return rows[0][0]


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    return con.execute(sql).fetchall()


def _add(checks: dict[str, Any], name: str, passed: bool, observed: Any,
         expected: Any = None, detail: str | None = None) -> None:
    checks[name] = {
        "passed": bool(passed),
        "observed": observed,
        "expected": expected,
        **({"detail": detail} if detail else {}),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _manifest_entries(manifest: Any) -> dict[str, str]:
    """Accept the common dict or list forms of a SHA256 artifact manifest."""
    entries: dict[str, str] = {}
    payload = manifest.get("files", manifest) if isinstance(manifest, dict) else manifest
    if isinstance(payload, dict):
        for name, value in payload.items():
            if isinstance(value, str) and len(value) == 64:
                entries[str(name)] = value.lower()
            elif isinstance(value, dict):
                digest = value.get("sha256") or value.get("hash")
                if isinstance(digest, str) and len(digest) == 64:
                    entries[str(name)] = digest.lower()
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                name = item.get("path") or item.get("file") or item.get("name")
                digest = item.get("sha256") or item.get("hash")
                if isinstance(name, str) and isinstance(digest, str) and len(digest) == 64:
                    entries[name] = digest.lower()
    return entries


def _check_manifest(checks: dict[str, Any]) -> dict[str, Any]:
    candidates = [ROOT / "manifest.json", ROOT / "audit" / "manifest.json", ROOT / "data" / "manifest.json"]
    manifests = [path for path in candidates if path.is_file()]
    if not manifests:
        _add(checks, "manifest_sha256", True, "no manifest found", "validate if present")
        return {"present": False, "validated_files": 0}

    outcomes: list[dict[str, Any]] = []
    all_ok = True
    for path in manifests:
        try:
            entries = _manifest_entries(_read_json(path))
            if not entries:
                outcomes.append({"manifest": str(path.relative_to(ROOT)), "passed": False,
                                 "detail": "manifest contains no SHA256 entries"})
                all_ok = False
                continue
            file_results = []
            for rel, expected_hash in entries.items():
                artifact = (ROOT / rel).resolve()
                # Never let a manifest hash paths outside this project.
                if ROOT.resolve() not in artifact.parents and artifact != ROOT.resolve():
                    actual_hash = None
                    ok = False
                    detail = "manifest path resolves outside project root"
                elif not artifact.is_file():
                    actual_hash = None
                    ok = False
                    detail = "manifest artifact is missing"
                else:
                    actual_hash = _sha256(artifact)
                    ok = actual_hash == expected_hash
                    detail = None if ok else "SHA256 mismatch"
                file_results.append({"path": rel, "expected_sha256": expected_hash,
                                    "actual_sha256": actual_hash, "passed": ok,
                                    **({"detail": detail} if detail else {})})
                all_ok = all_ok and ok
            outcomes.append({"manifest": str(path.relative_to(ROOT)), "passed": all(x["passed"] for x in file_results),
                             "files": file_results})
        except Exception as exc:
            all_ok = False
            outcomes.append({"manifest": str(path.relative_to(ROOT)), "passed": False,
                             "detail": f"{type(exc).__name__}: {exc}"})
    _add(checks, "manifest_sha256", all_ok, outcomes, "all listed files match SHA256")
    return {"present": True, "manifests": outcomes,
            "validated_files": sum(len(x.get("files", [])) for x in outcomes)}


def validate(root: Path = ROOT, report_path: Path | None = None) -> dict[str, Any]:
    """Run independent checks, write a JSON report, and return the report object."""
    root = Path(root).resolve()
    report_path = Path(report_path) if report_path else root / "audit" / "independent_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, Any] = {}
    report: dict[str, Any] = {
        "validator": "verify_baseline.py",
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "checks": checks,
    }
    paths = {
        "baseline": root / "data" / "baseline.parquet",
        "metadata": root / "data" / "metadata.parquet",
        "splits": root / "data" / "splits.parquet",
        "standardized": root / "data" / "reference_standardized.parquet",
        "outlier_flags": root / "data" / "outlier_flags.parquet",
        "cleaning_audit": root / "audit" / "cleaning_audit.json",
        "label_mapping": root / "audit" / "label_mapping.json",
        "standard_scaler": root / "audit" / "reference_standard_scaler.json",
    }
    missing = [str(p.relative_to(root)) for p in paths.values() if not p.is_file()]
    _add(checks, "required_artifacts_exist", not missing, {k: p.is_file() for k, p in paths.items()},
         "all required Parquet and JSON artifacts present", ", ".join(missing) if missing else None)
    if missing:
        report["status"] = "failed"
        report["manifest"] = _check_manifest(checks)
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return report

    try:
        cleaning = _read_json(paths["cleaning_audit"])
        label_mapping = _read_json(paths["label_mapping"])
        scaler = _read_json(paths["standard_scaler"])
        con = duckdb.connect(database=":memory:")
        con.execute("SET threads=4")
        for name, path in paths.items():
            if path.suffix == ".parquet":
                con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({_sql_path(path)})")

        # Baseline layout, prescribed features, labels, and row counts.
        baseline_columns = [r[0] for r in _rows(con, "DESCRIBE SELECT * FROM baseline")]
        baseline_feature_order = [name for name in baseline_columns if name in FEATURES]
        _add(checks, "feature_order", baseline_feature_order == FEATURES, baseline_feature_order, FEATURES)
        mapping = label_mapping.get("label_to_id", {})
        mapping_ok = list(mapping.keys()) == LABELS and list(mapping.values()) == list(range(7))
        _add(checks, "seven_class_mapping", mapping_ok, mapping,
             {label: idx for idx, label in enumerate(LABELS)})
        mapping_features_ok = label_mapping.get("features") == FEATURES
        _add(checks, "label_mapping_feature_order", mapping_features_ok,
             label_mapping.get("features"), FEATURES)
        baseline_n = int(_scalar(con, "SELECT count(*) FROM baseline"))
        expected_baseline_n = cleaning.get("baseline_rows")
        _add(checks, "baseline_count_matches_cleaning_audit", baseline_n == expected_baseline_n,
             baseline_n, expected_baseline_n)
        baseline_class_counts = dict(_rows(con, "SELECT label, count(*) FROM baseline GROUP BY label ORDER BY label"))
        expected_classes = set(LABELS)
        _add(checks, "baseline_contains_exactly_seven_classes", set(baseline_class_counts) == expected_classes,
             baseline_class_counts, sorted(expected_classes))
        expected_class_counts = {
            item["target"]: int(item["n"])
            for item in cleaning.get("baseline_class_counts", [])
        }
        _add(checks, "baseline_class_counts_match_cleaning_audit",
             baseline_class_counts == expected_class_counts, baseline_class_counts, expected_class_counts)
        case_sql = "CASE label " + " ".join(
            f"WHEN '{label}' THEN {idx}" for idx, label in enumerate(LABELS)
        ) + " ELSE -1 END"
        wrong_label_ids = int(_scalar(con,
            f"SELECT count(*) FROM baseline WHERE label_id <> ({case_sql}) OR label_id IS NULL"))
        _add(checks, "label_ids_match_mapping", wrong_label_ids == 0, wrong_label_ids, 0)

        # Feature data quality and duplicate identity/vector checks.
        valid_sql = " AND ".join(
            f"{f} IS NOT NULL AND isfinite({f}) AND {f} BETWEEN {BOUNDS[0]} AND {BOUNDS[1]}"
            for f in FEATURES
        )
        bad_features = int(_scalar(con, f"SELECT count(*) FROM baseline WHERE NOT ({valid_sql})"))
        _add(checks, "finite_bounded_features", bad_features == 0, bad_features,
             f"zero invalid rows; every feature in [{BOUNDS[0]}, {BOUNDS[1]}]")
        repeated_ids = {
            table: int(_scalar(con, f"SELECT count(*) - count(DISTINCT sample_id) FROM {table}"))
            for table in ("baseline", "metadata", "splits", "standardized", "outlier_flags")
        }
        _add(checks, "sample_id_uniqueness", all(count == 0 for count in repeated_ids.values()),
             repeated_ids, "zero duplicates in all sample-indexed artifacts")
        duplicate_vectors = int(_scalar(con,
            f"SELECT count(*) FROM (SELECT {', '.join(FEATURES)} FROM baseline GROUP BY {', '.join(FEATURES)} HAVING count(*) > 1)"))
        _add(checks, "exact_feature_vectors_unique", duplicate_vectors == 0, duplicate_vectors, 0)

        # Every baseline sample must have exactly one metadata and split row.
        crossfile = {}
        for table in ("metadata", "splits", "outlier_flags"):
            crossfile[f"baseline_missing_{table}"] = int(_scalar(con,
                f"SELECT count(*) FROM baseline b LEFT JOIN {table} x USING(sample_id) WHERE x.sample_id IS NULL"))
            crossfile[f"{table}_missing_baseline"] = int(_scalar(con,
                f"SELECT count(*) FROM {table} x LEFT JOIN baseline b USING(sample_id) WHERE b.sample_id IS NULL"))
        expected_scaled = int(_scalar(con,
            "SELECT count(*) FROM splits WHERE reference_partition IN ('reference_fit','reference_tune','test')"))
        crossfile["standardized_missing_expected_partition"] = int(_scalar(con,
            "SELECT count(*) FROM splits s LEFT JOIN standardized z USING(sample_id) "
            "WHERE s.reference_partition IN ('reference_fit','reference_tune','test') AND z.sample_id IS NULL"))
        crossfile["standardized_has_unexpected_sample"] = int(_scalar(con,
            "SELECT count(*) FROM standardized z LEFT JOIN splits s USING(sample_id) "
            "WHERE s.sample_id IS NULL OR s.reference_partition NOT IN ('reference_fit','reference_tune','test')"))
        _add(checks, "cross_file_sample_ids_complete", all(v == 0 for v in crossfile.values()),
             crossfile, "all expected IDs present with no extras")

        # Required sizes and split-level identifier/entity disjointness.
        partition_rows = dict(_rows(con,
            "SELECT reference_partition, count(*) FROM splits GROUP BY reference_partition"))
        expected_sizes = {**EXPECTED, "scaled_expected_rows": expected_scaled}
        split_membership_counts = {str(k): int(v) for k, v in _rows(
            con, "SELECT split, count(*) FROM splits GROUP BY split"
        )}
        size_results = {
            "test": split_membership_counts.get("test", 0),
            "development": split_membership_counts.get("development", 0),
            "reference_fit": int(partition_rows.get("reference_fit", 0)),
            "reference_tune": int(partition_rows.get("reference_tune", 0)),
        }
        _add(checks, "required_partition_sizes",
             all(size_results[k] == v for k, v in EXPECTED.items()), size_results, EXPECTED)
        split_sizes = {str(k): int(v) for k, v in _rows(con, "SELECT split, count(*) FROM splits GROUP BY split")}
        expected_split_sizes = cleaning.get("split_sizes", {})
        _add(checks, "split_sizes_match_cleaning_audit", split_sizes == expected_split_sizes,
             split_sizes, expected_split_sizes)
        leakage = {
            "uid_across_splits": int(_scalar(con,
                "SELECT count(*) FROM (SELECT m.uid FROM metadata m JOIN splits s USING(sample_id) "
                "GROUP BY m.uid HAVING count(DISTINCT s.split) > 1)")),
            "entity_id_across_splits": int(_scalar(con,
                "SELECT count(*) FROM (SELECT m.entity_id FROM metadata m JOIN splits s USING(sample_id) "
                "GROUP BY m.entity_id HAVING count(DISTINCT s.split) > 1)")),
            "gaia_source_id_across_splits": int(_scalar(con,
                "SELECT count(*) FROM (SELECT m.gaia_source_id FROM metadata m JOIN splits s USING(sample_id) "
                "WHERE try_cast(m.gaia_source_id AS HUGEINT) > 0 GROUP BY m.gaia_source_id "
                "HAVING count(DISTINCT s.split) > 1)")),
            "ps_id_across_splits": int(_scalar(con,
                "SELECT count(*) FROM (SELECT m.ps_id FROM metadata m JOIN splits s USING(sample_id) "
                "WHERE try_cast(m.ps_id AS HUGEINT) > 0 GROUP BY m.ps_id "
                "HAVING count(DISTINCT s.split) > 1)")),
        }
        _add(checks, "no_uid_or_entity_leakage_across_splits",
             all(count == 0 for count in leakage.values()), leakage, "zero repeated identities across splits")

        # Reference scaler JSON describes exactly the 800k fit partition.
        scaler_ok = (
            scaler.get("scaler") == "standard"
            and scaler.get("feature_columns") == FEATURES
            and scaler.get("n_fit_rows") == EXPECTED["reference_fit"]
            and len(scaler.get("centers", [])) == len(FEATURES)
            and len(scaler.get("scales", [])) == len(FEATURES)
            and all(math.isfinite(float(v)) for v in scaler.get("centers", []))
            and all(math.isfinite(float(v)) and float(v) > 0 for v in scaler.get("scales", []))
        )
        _add(checks, "standard_scaler_fit_metadata", scaler_ok,
             {"scaler": scaler.get("scaler"), "n_fit_rows": scaler.get("n_fit_rows"),
              "feature_columns": scaler.get("feature_columns"), "scales_positive": all(
                  isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                  for v in scaler.get("scales", []))},
             {"scaler": "standard", "n_fit_rows": EXPECTED["reference_fit"], "feature_columns": FEATURES})
        scaled_feature_order = [name for name in [r[0] for r in _rows(con, "DESCRIBE SELECT * FROM standardized")] if name in FEATURES]
        _add(checks, "standardized_feature_order", scaled_feature_order == FEATURES,
             scaled_feature_order, FEATURES)
        standardized_invalid = int(_scalar(con,
            "SELECT count(*) FROM standardized WHERE NOT (" + " AND ".join(
                f"{f} IS NOT NULL AND isfinite({f})" for f in FEATURES) + ")"))
        _add(checks, "standardized_features_finite", standardized_invalid == 0,
             standardized_invalid, 0)
        agg_exprs = []
        for feature in FEATURES:
            agg_exprs.extend([
                f"avg({feature}) FILTER (WHERE reference_partition='reference_fit') AS mean_{feature}",
                f"stddev_pop({feature}) FILTER (WHERE reference_partition='reference_fit') AS std_{feature}",
            ])
        aggregate = _rows(con, "SELECT " + ", ".join(agg_exprs) + " FROM standardized")[0]
        scale_checks = {}
        for i, feature in enumerate(FEATURES):
            mean = float(aggregate[2 * i])
            std = float(aggregate[2 * i + 1])
            scale_checks[feature] = {"mean": mean, "std": std,
                                    "mean_abs_le_1e-6": abs(mean) <= 1e-6,
                                    "std_within_1e-6": abs(std - 1.0) <= 1e-6}
        _add(checks, "reference_standardized_fit_mean_zero_std_one",
             all(v["mean_abs_le_1e-6"] and v["std_within_1e-6"] for v in scale_checks.values()),
             scale_checks, "fit means within 1e-6 of 0 and population std within 1e-6 of 1")
        _add(checks, "standardized_row_count_matches_expected_partitions",
             int(_scalar(con, "SELECT count(*) FROM standardized")) == expected_scaled,
             int(_scalar(con, "SELECT count(*) FROM standardized")), expected_scaled)

        # The frozen builder's audit should agree with independently recomputed checks.
        recorded_checks = cleaning.get("integrity_checks", {})
        audit_crosschecks = {
            "n_rows": baseline_n,
            "duplicate_sample_ids": repeated_ids["baseline"],
            "nonfinite_or_invalid_features": bad_features,
            "classes": len(baseline_class_counts),
            "duplicate_feature_vectors": duplicate_vectors,
            "uids_in_multiple_splits": leakage["uid_across_splits"],
            "entities_in_multiple_splits": leakage["entity_id_across_splits"],
        }
        audit_match = all(recorded_checks.get(k) == v for k, v in audit_crosschecks.items())
        _add(checks, "cleaning_audit_integrity_crosscheck", audit_match,
             audit_crosschecks, {k: recorded_checks.get(k) for k in audit_crosschecks})
        con.close()
    except Exception as exc:
        _add(checks, "validator_runtime", False, f"{type(exc).__name__}: {exc}", "all checks completed")

    report["manifest"] = _check_manifest(checks)
    failed = [name for name, value in checks.items() if not value["passed"]]
    report["failed_checks"] = failed
    report["status"] = "passed" if not failed else "failed"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = validate()
    print(json.dumps({"status": report["status"], "failed_checks": report.get("failed_checks", []),
                      "report": str(REPORT_PATH)}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
