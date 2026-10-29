import hashlib, importlib.util, json, sys
from pathlib import Path
import pytest

R = Path(__file__).resolve().parents[1]
SOURCE = R / "source" / "finalize_project.py"
RUNTIME_SOURCE = R / "source"
sys.path.insert(0, str(RUNTIME_SOURCE))
spec = importlib.util.spec_from_file_location("staged_finalize_project_et4", SOURCE)
fp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fp
spec.loader.exec_module(fp)

def policy():
    return {
        "schema": "lamost-later-et4-execution-policy/1",
        "status": "qualified",
        "policy_id": "et4-fit_n_jobs4-v1",
        "fit_n_jobs": 4,
        "prediction_n_jobs": 1,
        "native_threads": 1,
        "worker_memory_limit_gib": 10,
        "trial_timeout_seconds": 600,
        "phase_timeout_seconds": 600,
        "termination_grace_seconds": 30,
        "scope": {"experiments": [4, 5], "kind": "fit", "methods": ["extra_trees"],
                  "never_attempted": True, "reuse_pipeline": False},
    }

def write_policy(runtime, doc=None):
    path = runtime / "manifests" / "EXTRA_TREES4_EXECUTION_POLICY_20261029.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(doc or policy(), sort_keys=True), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()

def test_legacy_freeze_without_et4_pointer_keeps_output_empty(tmp_path):
    assert fp._et4_execution_disclosure(tmp_path, {}) == []

def test_valid_et4_policy_disclosure_has_limits_scope_and_comparability_caveat(tmp_path):
    path, digest = write_policy(tmp_path)
    lines = fp._et4_execution_disclosure(tmp_path, {"et4_execution_policy_sha256": digest})
    text = " ".join(lines)
    assert len(lines) == 2
    for phrase in ("four estimator fit jobs", "one prediction job", "one native-library thread",
                   "10 GiB", "600-second", "30-second", "E4/E5 ExtraTrees fits",
                   "frozen ET1 controls", "identical tuning completion", "not an isolated speed comparison",
                   "each attempt's captured profile is authoritative", "removal of the fixed two-worker ceiling",
                   "three Random Forest fits were observed concurrently", "not a universal cap"):
        assert phrase in text
    assert digest in text

def test_missing_or_tampered_pointer_target_fails_closed(tmp_path):
    with pytest.raises(fp.EvidenceError, match="missing or differs"):
        fp._et4_execution_disclosure(tmp_path, {"et4_execution_policy_sha256": "a" * 64})
    path, digest = write_policy(tmp_path)
    path.write_text(path.read_text() + " ", encoding="utf-8")
    with pytest.raises(fp.EvidenceError, match="missing or differs"):
        fp._et4_execution_disclosure(tmp_path, {"et4_execution_policy_sha256": digest})

@pytest.mark.parametrize("field,value", [
    ("fit_n_jobs", 1), ("prediction_n_jobs", 4), ("native_threads", 4),
    ("worker_memory_limit_gib", 6), ("trial_timeout_seconds", 180),
    ("scope", {"experiments": [4], "kind": "fit", "methods": ["extra_trees"],
               "never_attempted": True, "reuse_pipeline": False}),
])
def test_wrong_policy_details_fail_closed(tmp_path, field, value):
    doc = policy()
    doc[field] = value
    _, digest = write_policy(tmp_path, doc)
    with pytest.raises(fp.EvidenceError, match="not the reviewed qualified"):
        fp._et4_execution_disclosure(tmp_path, {"et4_execution_policy_sha256": digest})
