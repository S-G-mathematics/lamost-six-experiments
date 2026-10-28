import hashlib, json, os, pathlib
import joblib, numpy as np
from cold_model_storage import ColdModelStore

def setup_store(tmp, method="extra_trees", experiment=3):
    root=pathlib.Path(tmp)/"migration"; runtime=root/"runtime_20261025"; runtime.mkdir(parents=True)
    archive=root/"packages"/"cold.zip"; archive.parent.mkdir(parents=True)
    store=ColdModelStore(root,runtime,archive,runtime/"manifests"/"cold_store.json",runtime/"journals"/"cold_store")
    store.initialize_empty_archive()
    key=f"e{experiment}/rep_1/fit/real/{method}"; out=runtime/"artifacts"/key;out.mkdir(parents=True)
    source=out/"pipeline.joblib"; obj={"fixture":"synthetic-test-payload","array":np.arange(7,dtype=np.int16),"params":{"n_estimators":1}}
    joblib.dump(obj,source,compress=0); digest=hashlib.sha256(source.read_bytes()).hexdigest()
    attempt_id="fixture_attempt_01"; task_sha=hashlib.sha256(("task-sha-"+method).encode()).hexdigest()
    attempt_dir=out/"attempts"/attempt_id;attempt_dir.mkdir(parents=True)
    checkpoint_dir=out/"checkpoints"/task_sha;checkpoint_dir.mkdir(parents=True)
    alias=attempt_dir/"pipeline.joblib";os.link(source,alias)
    checkpoint_alias=checkpoint_dir/"pipeline.joblib";os.link(source,checkpoint_alias)
    selection_bytes=json.dumps({"selected_params":{"n_estimators":1}},sort_keys=True).encode();selection_sha=hashlib.sha256(selection_bytes).hexdigest()
    (out/"selection.json").write_bytes(selection_bytes);(attempt_dir/"selection.json").write_bytes(selection_bytes);(checkpoint_dir/"selection.json").write_bytes(selection_bytes)
    fit_result={"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest,"status":"success"}}
    fit_result_bytes=json.dumps(fit_result,sort_keys=True).encode();(out/"fit_result.json").write_bytes(fit_result_bytes);(attempt_dir/"attempt.json").write_bytes(fit_result_bytes)
    publication={"attempt_id":attempt_id,"pipeline_sha256":digest,"published_path":str(source),"stage":"validated_publication","task_sha256":task_sha}
    publication_bytes=json.dumps(publication,sort_keys=True).encode();(out/"fit_publication.json").write_bytes(publication_bytes);(attempt_dir/"fit_publication.json").write_bytes(publication_bytes)
    fit={"key":key,"experiment":experiment,"kind":"fit","method":method,"route":"direct","status":"validated_terminal","outcome":"successful","validation_state":"validated","artifact_dir":str(out),"dependencies":[],"result":{"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest},"validation":{"status":"validated","task_key":key,"files":{"pipeline.joblib":digest,"selection.json":selection_sha}}}}
    consumer_key=f"e{experiment}/rep_1/eval/direct/{method}/control"
    consumer={"key":consumer_key,"experiment":experiment,"kind":"eval","method":method,"route":"direct","status":"validated_terminal","outcome":"successful","validation_state":"validated","dependencies":[key],"artifact_dir":str(runtime/"artifacts"/consumer_key),"result":{}}
    records={key:fit,consumer_key:consumer}
    item={"producer_task":key,"source_path":source.relative_to(root).as_posix(),"source_relpath":source.relative_to(root).as_posix(),"archive_member":source.relative_to(root).as_posix(),"source_sha256":digest,"recorded_artifact_sha256":digest,"consumer_tasks":[consumer_key],"aliases":[source.relative_to(root).as_posix(),alias.relative_to(root).as_posix(),checkpoint_alias.relative_to(root).as_posix()]}
    return root,runtime,store,key,source,alias,obj,digest,records,item
