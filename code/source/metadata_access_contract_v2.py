"""Bounded v2 artifact-access contract for pending E4/E5 RF/ET tasks.

The producer's model payload is never a waived task dependency. Only a
validated producer selection.json may remain pending, and only for fresh,
frozen-plan-bound fit/eval tasks whose model reads target their own new fit.
"""
import hashlib
import json
import stat
from pathlib import Path

import cold_storage_safety as _safety
import metadata_only_contract as _legacy

LEGACY_CONTRACT_SHA256 = "1d4e9f78bf3b0062effb3bc218fb5135aae0dba2375b2602773d21bf49d333a1"
SAFETY_SOURCE_SHA256 = "7dff7f8dc256f8252d41b6fd370b7624bfe8841fa7c5c13dbe86747ccc456273"


POLICY = "producer-selection-json-access-v2"
LEGACY_PRODUCER = "e3/rep_2/fit/synthetic/random_forest/copula"
FROZEN_TASKS_JSON_SHA256 = "42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb"
PINNED_CODE = {
    "worker.py": "f158d2bed12072da661af9195cc3a1b7e0367ff7cb2fe3ad24111e076dd29b18",
    "science.py": "9937104e3e2d56eab25bb9596b39dcadbdefcd677ffa941cd1a635ae4ba58bd3",
    "phase_worker.py": "03df2cf1208d7a0a14ceda002f7f16291e0e08ee7308f967980d9519d05cc8de",
    "parallel_rf/worker.py": "5741d1f60b513a6da0023e508b8d17d28e8f6e4355f30c08d5cfb81f1f233ab9",
    "parallel_rf/science.py": "e36c8040c7dca254fc7e16a53ffe860872df31a77868a7bc6480162f32d253c6",
    "parallel_rf/phase_worker.py": "6bbc631629227aa5113badefac6206884187ce01fa2d9d77edf66b477d6c08a3",
}
PRODUCER_METHODS = frozenset({
    "arf", "cart", "chow_liu", "copula", "gaussian_nb", "gmm", "hist_gb",
    "kde", "knn", "lda", "linear_svm", "logistic", "qda", "random_forest",
    "rbf_svm", "shared_diagonal",
})
CONSUMER_METHODS = frozenset({"random_forest"})
DATA_TASK_KINDS = frozenset({"generate"})
_DATA_SHA_CACHE = {}
_FORBIDDEN_MODEL_FIELDS = (
    "source_key", "model_key", "model_task", "pipeline_task", "artifact_task",
    "producer_task", "member_task", "model_references", "model_refs",
    "model_keys", "member_keys", "artifact_references",
)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _stable_sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("bound JSON/policy file is not a regular file")
    before = path.stat(follow_symlinks=False)
    digest = _sha(path)
    after = path.stat(follow_symlinks=False)
    ident = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if ident(before) != ident(after):
        raise ValueError("bound JSON/policy file changed while hashing")
    return digest


def _json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _tasks(records):
    if isinstance(records, dict):
        rows = records.get("tasks") if isinstance(records.get("tasks"), list) else records.values()
    else:
        rows = records
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str) or row["key"] in result:
            raise ValueError("registry task inventory is malformed or duplicated")
        result[row["key"]] = row
    return result


def _frozen_definitions(root):
    root = Path(root).resolve()
    runtime = root / "runtime_20261025"
    plan_path = runtime / "manifests" / "tasks.json"
    freeze_path = runtime / "manifests" / "freeze.json"
    plan_sha = _stable_sha(plan_path)
    freeze_before = _stable_sha(freeze_path)
    if plan_sha != FROZEN_TASKS_JSON_SHA256:
        raise ValueError("frozen task plan differs from qualified v2 contract")
    plan_doc = json.loads(plan_path.read_text())
    freeze_doc = json.loads(freeze_path.read_text())
    if freeze_doc.get("plan_sha256") != plan_sha:
        raise ValueError("freeze does not bind the exact task plan")
    if _stable_sha(plan_path) != plan_sha or _stable_sha(freeze_path) != freeze_before:
        raise ValueError("frozen task policy changed during contract validation")
    source_map = freeze_doc.get("source_sha256")
    if not isinstance(source_map, dict):
        raise ValueError("freeze lacks the source hash map")
    legacy_path = runtime / "source" / "metadata_only_contract.py"
    if legacy_path.is_symlink() or not legacy_path.is_file():
        raise ValueError("legacy v1 contract is not a regular file")
    legacy_sha = _stable_sha(legacy_path)
    if legacy_sha != LEGACY_CONTRACT_SHA256:
        raise ValueError("legacy v1 contract bytes changed")
    safety_path = runtime / "source" / "cold_storage_safety.py"
    if safety_path.is_symlink() or not safety_path.is_file() or _stable_sha(safety_path) != SAFETY_SOURCE_SHA256:
        raise ValueError("consumer-closure safety helper changed")
    
    for rel, expected in PINNED_CODE.items():
        path = runtime / "source" / rel
        if path.is_symlink() or not path.is_file() or _stable_sha(path) != expected:
            raise ValueError("consumer source pin mismatch: " + rel)
        if source_map.get(rel) != expected:
            raise ValueError("freeze source pin mismatch: " + rel)
    rows = plan_doc.get("tasks")
    if not isinstance(rows, list):
        raise ValueError("frozen plan has no task list")
    definitions = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str) or row["key"] in definitions:
            raise ValueError("frozen task plan has malformed/duplicate definitions")
        definitions[row["key"]] = row
    return definitions, plan_sha, legacy_sha


def _bound(root, record, frozen):
    return _legacy._bound_definition(root, record, frozen)


def _selection_binding(root, producer, source):
    root = Path(root).resolve()
    rel = f"runtime_20261025/artifacts/{producer}/selection.json"
    path = root / rel
    if path.resolve(strict=True).relative_to(root) != Path(rel):
        raise ValueError("selection JSON escaped canonical producer path")
    expected = ((source.get("result") or {}).get("validation") or {}).get("files", {}).get("selection.json")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("producer lacks validated selection JSON SHA")
    actual = _stable_sha(path)
    if actual != expected:
        raise ValueError("producer selection JSON differs from its validated SHA")
    value = json.loads(path.read_text())
    if _stable_sha(path) != actual:
        raise ValueError("selection JSON changed while parsing")
    if not isinstance(value, dict):
        raise ValueError("selection JSON root is not an object")
    params = value.get("selected_params", value.get("params", value.get("best_params")))
    if not isinstance(params, dict) or not params:
        raise ValueError("selection JSON lacks a fixed parameter object")
    return rel, actual


def _no_direct_model_refs(task):
    return not any(task.get(field) for field in _FORBIDDEN_MODEL_FIELDS)


def _training_data_binding(root, task, frozen, definitions):
    if (task.get("kind") not in DATA_TASK_KINDS or task.get("status") != "validated_terminal"
            or task.get("outcome") != "successful" or task.get("validation_state") != "validated"):
        raise ValueError("fit training artifact is not a successful terminal validated generate task")
    result = task.get("result")
    validation = result.get("validation") if isinstance(result, dict) else None
    files = validation.get("files") if isinstance(validation, dict) else None
    if (not isinstance(validation, dict) or validation.get("status") != "validated"
            or not isinstance(files, dict)):
        raise ValueError("training data lacks a validated artifact manifest")
    expected_sha = files.get("data.npz")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
        raise ValueError("training data lacks its validated data.npz SHA256")
    bound_definition = _bound(root, task, frozen)
    train_key = task["key"]
    expected_dir = (Path(root) / "runtime_20261025" / "artifacts" / train_key).resolve(strict=True)
    artifact_dir = task.get("artifact_dir")
    if not isinstance(artifact_dir, str) or Path(artifact_dir).resolve(strict=True) != expected_dir:
        raise ValueError("training artifact directory differs from canonical task path")
    data_path = expected_dir / "data.npz"
    if data_path.is_symlink() or not data_path.is_file():
        raise ValueError("validated training data.npz is not a regular file")
    resolved = data_path.resolve(strict=True)
    if resolved != data_path or not resolved.is_relative_to(Path(root)):
        raise ValueError("training data.npz escaped the canonical runtime")
    st = data_path.stat(follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("training data.npz is not a regular file")
    identity = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    cache_key = (str(data_path), identity)
    actual_sha = _DATA_SHA_CACHE.get(cache_key)
    if actual_sha is None:
        actual_sha = _stable_sha(data_path)
        st_after = data_path.stat(follow_symlinks=False)
        if identity != (st_after.st_dev, st_after.st_ino, st_after.st_size,
                        st_after.st_mtime_ns, st_after.st_ctime_ns):
            raise ValueError("training data.npz changed while verifying its SHA")
        _DATA_SHA_CACHE[cache_key] = actual_sha
    if actual_sha != expected_sha:
        raise ValueError("training data.npz differs from its validated SHA256")
    return {
        "train_key": train_key,
        "train_task_definition_sha256": _json_sha(bound_definition),
        "data_npz_path": str(data_path.relative_to(root)),
        "data_npz_sha256": expected_sha,
    }


def _fresh_selection_fit(task, producer, tasks, definitions, closure, root):
    key = task.get("key")
    if not isinstance(key, str) or key not in closure or definitions.get(key) is None:
        raise ValueError("fresh selection fit is not a frozen closure task")
    _bound(root, task, definitions[key])
    if (task.get("kind") != "fit" or int(task.get("experiment", 0)) not in (4, 5)
            or task.get("method") not in CONSUMER_METHODS):
        raise ValueError("selection consumer is not an E4/E5 RF fit")
    if task.get("selection_key") != producer or task.get("selection_mode") != "fixed":
        raise ValueError("fit does not consume the producer's fixed selection JSON")
    if task.get("selection_policy") != "frozen_clean_selected_params_no_retuning":
        raise ValueError("fit selection policy is not frozen and fixed")
    if task.get("reuse_pipeline") not in (None, False) or task.get("fit_key") not in (None, ""):
        raise ValueError("fit reuses or directly reads a model pipeline")
    if not _no_direct_model_refs(task):
        raise ValueError("fit has a direct physical model reference")
    train = task.get("train_key")
    if not isinstance(train, str) or train == producer or train not in tasks:
        raise ValueError("fit training data key is absent or aliases the producer")
    if train not in set(task.get("dependencies") or []):
        raise ValueError("fit training data is not an explicit frozen dependency")
    if train not in definitions:
        raise ValueError("fit training data is absent from frozen plan")
    return _training_data_binding(root, tasks[train], definitions[train], definitions)


def build_contract(root, producer, records, closure):
    """Return a fully bound contract or reject the pending consumer closure."""
    root = Path(root).resolve()
    tasks = _tasks(records)
    if producer == LEGACY_PRODUCER:
        raise ValueError("legacy E3 rep2 producer remains bound to v1 contract")
    source = tasks.get(producer)
    if not source or source.get("key") != producer:
        raise ValueError("producer is absent from registry")
    if (source.get("kind") != "fit" or int(source.get("experiment", 0)) not in (3, 4, 5, 6)
            or source.get("method") not in PRODUCER_METHODS
            or source.get("status") != "validated_terminal"
            or source.get("outcome") != "successful"
            or source.get("validation_state") != "validated"):
        raise ValueError("producer is not a successful validated allowlisted fit")
    declared = set(closure)
    if producer in declared or any(not isinstance(k, str) for k in declared):
        raise ValueError("consumer closure is malformed")
    actual = set(_safety.consumer_closure(producer, tasks))
    if actual != declared:
        raise ValueError("consumer closure does not match the complete task graph")
    definitions, plan_sha, legacy_sha = _frozen_definitions(root)
    stable_definitions = {}
    for key in sorted({producer} | declared):
        task = tasks.get(key)
        frozen = definitions.get(key)
        if task is None or frozen is None:
            raise ValueError("task absent from registry or frozen plan: " + str(key))
        stable_definitions[key] = _bound(root, task, frozen)

    selection_path, selection_sha = _selection_binding(root, producer, source)
    contract_fits = {}
    contract_evals = {}
    pending_keys = set()

    def bind_own_eval(task):
        fit_key = task.get("fit_key")
        if not isinstance(fit_key, str) or fit_key == producer or fit_key not in declared:
            raise ValueError("evaluation does not reference its own fit in the closure")
        if set(task.get("dependencies") or []) != {fit_key}:
            raise ValueError("evaluation has dependencies beyond its own fresh fit")
        fit_task = tasks.get(fit_key)
        if not fit_task:
            raise ValueError("evaluation's own fit is missing")
        data_binding = _fresh_selection_fit(fit_task, producer, tasks, definitions, declared, root)
        if (int(fit_task.get("experiment", 0)) != int(task.get("experiment", 0))
                or fit_task.get("method") != task.get("method")):
            raise ValueError("evaluation and own fit definitions disagree")
        return fit_key, data_binding

    for key in sorted(declared):
        task = tasks[key]
        status = task.get("status")
        if status == "validated_terminal":
            # Preserve proof rows across lifecycle changes when their validated data
            # inputs still exist. A controller-terminal unavailable_dependency row
            # with no generated input is no longer a reader and needs no payload proof.
            if task.get("outcome") == "unavailable_dependency":
                try:
                    if task.get("kind") == "fit" and task.get("selection_key") == producer:
                        _fresh_selection_fit(task, producer, tasks, definitions, declared, root)
                    elif task.get("kind") == "eval":
                        fit_key = task.get("fit_key")
                        fit_task = tasks.get(fit_key) if isinstance(fit_key, str) else None
                        if fit_task and fit_task.get("selection_key") == producer:
                            bind_own_eval(task)
                except ValueError:
                    continue
            # Preserve the same binding as pending fits/evaluations transition
            # to terminal whenever the validated training input is available.
            if task.get("kind") == "fit" and task.get("selection_key") == producer:
                data_binding = _fresh_selection_fit(task, producer, tasks, definitions, declared, root)
                contract_fits[key] = {
                    "task_key": key,
                    "definition_sha256": _json_sha(stable_definitions[key]),
                    "selection_json_path": selection_path,
                    "selection_json_sha256": selection_sha,
                    **data_binding,
                }
            elif task.get("kind") == "eval":
                fit_key = task.get("fit_key")
                fit_task = tasks.get(fit_key) if isinstance(fit_key, str) else None
                if fit_task and fit_task.get("selection_key") == producer:
                    bound_fit_key, data_binding = bind_own_eval(task)
                    contract_evals[key] = {
                        "task_key": key,
                        "definition_sha256": _json_sha(stable_definitions[key]),
                        "fit_key": bound_fit_key,
                        **data_binding,
                    }
            continue
        if status not in ("waiting_for_dependency", "pending", "running"):
            raise ValueError("nonterminal consumer has unsupported lifecycle status")
        if int(task.get("experiment", 0)) not in (4, 5) or task.get("method") not in CONSUMER_METHODS:
            raise ValueError("nonterminal consumer is outside the E4/E5 RF scope")
        if task.get("reuse_pipeline") not in (None, False) or not _no_direct_model_refs(task):
            raise ValueError("nonterminal consumer may read a producer model payload")
        if task.get("kind") == "fit":
            data_binding = _fresh_selection_fit(task, producer, tasks, definitions, declared, root)
            if producer not in set(task.get("dependencies") or []):
                raise ValueError("fixed selection source is not an explicit dependency")
            contract_fits[key] = {
                "task_key": key,
                "definition_sha256": _json_sha(stable_definitions[key]),
                "selection_json_path": selection_path,
                "selection_json_sha256": selection_sha,
                **data_binding,
            }
            pending_keys.add(key)
        elif task.get("kind") == "eval":
            fit_key, data_binding = bind_own_eval(task)
            contract_evals[key] = {
                "task_key": key,
                "definition_sha256": _json_sha(stable_definitions[key]),
                "fit_key": fit_key,
                **data_binding,
            }
            pending_keys.add(key)
        else:
            raise ValueError("unknown nonterminal task kind in consumer closure")

    if not (contract_fits or contract_evals):
        raise ValueError("v2 contract applies only to pending metadata/data consumers")
    pending_fits = [contract_fits[k] for k in sorted(contract_fits)]
    pending_evals = [contract_evals[k] for k in sorted(contract_evals)]
    payload = {
        "policy": POLICY,
        "producer_task": producer,
        "producer_method": source.get("method"),
        "producer_experiment": int(source.get("experiment", 0)),
        "producer_pipeline_sha256": (((source.get("result") or {}).get("validation") or {}).get("files") or {}).get("pipeline.joblib"),
        "selection_json_path": selection_path,
        "selection_json_sha256": selection_sha,
        "frozen_tasks_json_sha256": plan_sha,
        "consumer_code_sha256": {**dict(PINNED_CODE), "metadata_only_contract.py": legacy_sha,
                                 "cold_storage_safety.py": SAFETY_SOURCE_SHA256},
        "v2_contract_module_sha256": _stable_sha(Path(__file__)),
        "pending_metadata_fit_tasks": pending_fits,
        "pending_own_fit_evaluations": pending_evals,
        "full_consumer_closure": sorted(declared),
        "pending_access_roles": "fixed selection.json for fit; own fit pipeline for eval; validated generate data.npz remains physical and SHA-bound",
    }
    return {**payload, "contract_sha256": _json_sha(payload)}
