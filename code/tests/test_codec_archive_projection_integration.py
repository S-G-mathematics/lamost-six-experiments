import copy, hashlib, json, os, sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
SOURCE = STAGE / "source"
sys.path.insert(0, str(SOURCE))

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def test_auditor_review_export_projection_recipe_binding(tmp_path):
    import joblib, joblib.compressor
    import cold_model_storage as core
    import cold_finalizer_adapter as adapter
    import finalize_project as finalizer
    import final_review
    from audit_artifacts import Auditor
    from cold_finalizer_adapter import ColdFinalizerError

    root = tmp_path / "project"
    runtime = root / "runtime_20261025"
    (runtime / "manifests").mkdir(parents=True)
    (runtime / "journals").mkdir()
    (runtime / "artifacts").mkdir()
    archive = root / "packages" / "cold.zip"
    archive.parent.mkdir(parents=True)
    store = core.ColdModelStore(
        root, runtime, archive, runtime / "manifests/cold_model_store_manifest.json",
        runtime / "journals/cold",
        joblib_compressor_source_path=Path(joblib.compressor.__file__),
        storage_codec_policy="reversible-xz-v1",
    )
    store.initialize_empty_archive()

    key = "e3/rep_1/fit/real/random_forest"
    consumer_key = "e3/rep_1/eval/direct/random_forest/gmm"
    out = runtime / "artifacts" / key
    out.mkdir(parents=True)
    pipeline = out / "pipeline.joblib"
    obj = {"fixture": "no-classifier", "payload": b"codec-proof-" * 200000, "n": 7}
    joblib.dump(obj, pipeline, compress=3)
    digest = sha(pipeline)
    task_sha = hashlib.sha256(("smoke-task:" + key).encode()).hexdigest()
    attempt = out / "attempts/smoke-attempt"
    attempt.mkdir(parents=True)
    checkpoint = out / "checkpoints" / task_sha
    checkpoint.mkdir(parents=True)
    alias1, alias2 = attempt / "pipeline.joblib", checkpoint / "pipeline.joblib"
    os.link(pipeline, alias1)
    os.link(pipeline, alias2)
    sel = b'{"selected_params":{"n_estimators":1}}'
    selsha = hashlib.sha256(sel).hexdigest()
    for d in (out, attempt, checkpoint):
        (d / "selection.json").write_bytes(sel)
    fit_result = {"attempt_id":"smoke-attempt","task_sha256":task_sha,
                  "result":{"pipeline_sha256":digest,"status":"success"}}
    fr = json.dumps(fit_result, sort_keys=True).encode()
    (out / "fit_result.json").write_bytes(fr)
    (attempt / "attempt.json").write_bytes(fr)
    publication = {"attempt_id":"smoke-attempt","pipeline_sha256":digest,
                   "published_path":str(pipeline.resolve()),"stage":"validated_publication",
                   "task_sha256":task_sha}
    pb = json.dumps(publication, sort_keys=True).encode()
    (out / "fit_publication.json").write_bytes(pb)
    (attempt / "fit_publication.json").write_bytes(pb)
    fit = {"key":key,"experiment":3,"kind":"fit","method":"random_forest",
           "status":"validated_terminal","outcome":"successful","validation_state":"validated",
           "artifact_dir":str(out),"dependencies":[],
           "result":{"attempt_id":"smoke-attempt","task_sha256":task_sha,
                     "result":{"pipeline_sha256":digest},
                     "validation":{"status":"validated","task_key":key,
                                   "files":{"pipeline.joblib":digest,"selection.json":selsha}}}}
    consumer = {"key":consumer_key,"experiment":3,"kind":"eval","method":"random_forest",
                "status":"validated_terminal","outcome":"successful","validation_state":"validated",
                "dependencies":[key],"artifact_dir":str(runtime/"artifacts"/consumer_key),"result":{}}
    records = {key:fit, consumer_key:consumer}
    rel = pipeline.relative_to(root).as_posix()
    item = {"producer_task":key,"source_path":rel,"source_relpath":rel,
            "archive_member":rel,"source_sha256":digest,"recorded_artifact_sha256":digest,
            "consumer_tasks":[consumer_key],
            "aliases":[rel,alias1.relative_to(root).as_posix(),alias2.relative_to(root).as_posix()]}
    store.commit_models([item], records)
    row = json.loads((runtime/"manifests/cold_model_store_manifest.json").read_text())["members"][0]

    auditor = Auditor(runtime, cold_store=store)
    members = final_review.cold_member_index(store)
    projection = []
    for req in dict.fromkeys([row["logical_path"], *row.get("aliases", [])]):
        logical = root / req
        assert auditor.file_hash(logical, force=True) == digest
        cache = auditor.cache["files"][str(logical)]
        record = final_review.file_record(
            logical, root, "audited_artifact", {}, cold_store=store, cold_members=members,
            expected_sha256=digest, cache_observation=cache)
        projection.append(record["cold_member_identity"])
    assert len(projection) == 3
    assert all(x.get("recipe_sha256") for x in projection)

    review = {"snapshot":{"inputs":{"cold_archived_artifact_members":projection}},
              "candidate_id":"fixture","decision":"engineering_fixture_only"}
    entries, payload = adapter.cold_artifact_entries(finalizer, root, runtime, store, records, {}, review)
    assert payload
    exported = json.loads(payload)["members"]
    assert exported == projection

    bad_review = copy.deepcopy(review)
    for member in bad_review["snapshot"]["inputs"]["cold_archived_artifact_members"]:
        member.pop("recipe_sha256", None)
    try:
        adapter.cold_artifact_entries(finalizer, root, runtime, store, records, {}, bad_review)
    except ColdFinalizerError:
        pass
    else:
        raise AssertionError("candidate missing recipe identity was accepted")

    raw = {"logical_path":"runtime_20261025/artifacts/raw/pipeline.joblib",
           "aliases":[],"task_key":"raw","task_sha256":"b"*64,
           "archive_member":"runtime_20261025/cold_models/raw","sha256":"a"*64,
           "bytes":10,"crc32":123,"header_offset":0,"source_mtime_ns":123}
    raw_identity = final_review.cold_member_identity(
        {"sha256":"a"*64,"size":10,"archive_member":raw["archive_member"],"mtime_ns":123},
        raw, raw["logical_path"])
    assert "recipe_sha256" not in raw_identity
    assert "storage_encoding" not in raw_identity
    assert "logical_sha256" not in raw_identity
