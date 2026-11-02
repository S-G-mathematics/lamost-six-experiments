import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
import joblib
import numpy as np
import cold_model_storage as cold
from test_cold_model_storage import setup_store

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _second_fit(root,runtime,records):
    key="e3/rep_2/fit/real/random_forest"
    out=runtime/"artifacts"/key
    out.mkdir(parents=True)
    src=out/"pipeline.joblib"
    joblib.dump({"fixture":"second-joblib-stream","array":np.arange(11,dtype=np.int32)},src,compress=0)
    digest=_sha(src)
    attempt_id="fixture_attempt_02"
    task_sha=hashlib.sha256(b"task-sha-rep_2").hexdigest()
    attempt_dir=out/"attempts"/attempt_id;attempt_dir.mkdir(parents=True)
    checkpoint_dir=out/"checkpoints"/task_sha;checkpoint_dir.mkdir(parents=True)
    alias=attempt_dir/"pipeline.joblib";os.link(src,alias)
    checkpoint_alias=checkpoint_dir/"pipeline.joblib";os.link(src,checkpoint_alias)
    selection=json.dumps({"selected_params":{"n_estimators":1}},sort_keys=True).encode()
    selection_sha=hashlib.sha256(selection).hexdigest()
    (out/"selection.json").write_bytes(selection)
    (attempt_dir/"selection.json").write_bytes(selection)
    (checkpoint_dir/"selection.json").write_bytes(selection)
    fit_result={"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest,"status":"success"}}
    fit_result_bytes=json.dumps(fit_result,sort_keys=True).encode()
    (out/"fit_result.json").write_bytes(fit_result_bytes)
    (attempt_dir/"attempt.json").write_bytes(fit_result_bytes)
    publication={"attempt_id":attempt_id,"pipeline_sha256":digest,"published_path":str(src),
                 "stage":"validated_publication","task_sha256":task_sha}
    publication_bytes=json.dumps(publication,sort_keys=True).encode()
    (out/"fit_publication.json").write_bytes(publication_bytes)
    (attempt_dir/"fit_publication.json").write_bytes(publication_bytes)
    fit={"key":key,"experiment":3,"kind":"fit","method":"random_forest","status":"validated_terminal",
         "outcome":"successful","validation_state":"validated","artifact_dir":str(out),"dependencies":[],
         "result":{"attempt_id":attempt_id,"task_sha256":task_sha,"result":{"pipeline_sha256":digest},
                   "validation":{"status":"validated","task_key":key,"files":{"pipeline.joblib":digest,"selection.json":selection_sha}}}}
    consumer_key="e3/rep_2/eval/direct/random_forest/gmm"
    consumer={"key":consumer_key,"experiment":3,"kind":"eval","method":"random_forest",
              "status":"validated_terminal","outcome":"successful","validation_state":"validated",
              "dependencies":[key],"artifact_dir":str(runtime/"artifacts"/consumer_key),"result":{}}
    merged=dict(records);merged[key]=fit;merged[consumer_key]=consumer
    logical=src.relative_to(root).as_posix()
    item={"producer_task":key,"source_path":logical,"source_relpath":logical,"archive_member":logical,
          "source_sha256":digest,"recorded_artifact_sha256":digest,"consumer_tasks":[consumer_key],
          "aliases":[logical,alias.relative_to(root).as_posix(),checkpoint_alias.relative_to(root).as_posix()]}
    return merged,item,logical

class MemberPayloadProofTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.root,self.runtime,self.store,self.key,self.src,self.alias,self.obj,self.digest,self.records,self.item=setup_store(self.td.name)
        self.store.commit_models([self.item],self.records)
    def tearDown(self):
        self.td.cleanup()
    def _monitor(self):
        calls=[]
        original=self.store._verified_member_metadata
        def wrapped(logical,entry):
            calls.append(logical)
            return original(logical,entry)
        self.store._verified_member_metadata=wrapped
        return calls
    def test_inductive_append_skips_old_stream_and_still_verifies_new_payload(self):
        receipt=json.loads(self.store._baseline_cache_path().read_text())
        self.assertIn("member_payload_verification",receipt)
        records,item,newlogical=_second_fit(self.root,self.runtime,self.records)
        scanned=self._monitor()
        verified=[]
        original=self.store._verify_transaction_item
        def verify(item,record,z):
            verified.append(item["logical_path"])
            return original(item,record,z)
        self.store._verify_transaction_item=verify
        self.store.commit_models([item],records)
        self.assertNotIn(self.item["source_relpath"],scanned)
        self.assertIn(newlogical,verified)
        manifest=json.loads(self.store.manifest.read_text())
        self.assertEqual(len(manifest["members"]),2)
        self.assertEqual(self.store._baseline_cache_path().exists(),True)
    def test_missing_member_proof_falls_back_to_full_old_payload_scan(self):
        cache=json.loads(self.store._baseline_cache_path().read_text())
        cache.pop("member_payload_verification")
        self.store._baseline_cache_path().write_text(json.dumps(cache,sort_keys=True))
        scanned=self._monitor()
        self.store.commit_models([],self.records)
        self.assertIn(self.item["source_relpath"],scanned)
    def test_tampered_member_proof_falls_back_to_full_old_payload_scan(self):
        cache=json.loads(self.store._baseline_cache_path().read_text())
        cache["member_payload_verification"]["members_sha256"]="0"*64
        self.store._baseline_cache_path().write_text(json.dumps(cache,sort_keys=True))
        scanned=self._monitor()
        self.store.commit_models([],self.records)
        self.assertIn(self.item["source_relpath"],scanned)
    def test_changed_completed_journal_invalidates_cache_proof_and_falls_back(self):
        journal_path=next(self.store.journals.glob("*/journal.json"))
        journal=json.loads(journal_path.read_text())
        journal["member_payload_verification"]["members_sha256"]="0"*64
        journal_path.write_text(json.dumps(journal,sort_keys=True))
        scanned=self._monitor()
        self.store.commit_models([],self.records)
        self.assertIn(self.item["source_relpath"],scanned)
    def test_new_source_mutation_after_normalization_still_fails_before_append(self):
        records,item,newlogical=_second_fit(self.root,self.runtime,self.records)
        archive_sha=cold.sha256_file(self.store.archive)
        original=self.store._backup_tail
        def mutate_after_prepare(j):
            value=original(j)
            path=self.root/newlogical
            path.write_bytes(path.read_bytes()+b"tamper")
            return value
        self.store._backup_tail=mutate_after_prepare
        with self.assertRaises(cold.AmbiguousState):
            self.store.commit_models([item],records)
        self.assertEqual(cold.sha256_file(self.store.archive),archive_sha)
        pending=[p for p in self.store.journals.glob("*/journal.json") if json.loads(p.read_text()).get("state")!="complete"]
        self.assertEqual(len(pending),1)
        self.assertNotIn("member_payload_verification",json.loads(pending[0].read_text()))
    def test_tampered_predecessor_journal_breaks_inductive_reuse(self):
        records,item2,logical2=_second_fit(self.root,self.runtime,self.records)
        self.store.commit_models([item2],records)
        journals=sorted(self.store.journals.glob("*/journal.json"),key=lambda p:p.stat().st_mtime_ns)
        self.assertEqual(len(journals),2)
        prior=json.loads(journals[0].read_text())
        prior["member_payload_verification"]["members_sha256"]="0"*64
        journals[0].write_text(json.dumps(prior,sort_keys=True))
        scanned=self._monitor()
        self.store.commit_models([],records)
        self.assertIn(self.item["source_relpath"],scanned)
        self.assertIn(logical2,scanned)
    def test_metadata_validation_still_runs_with_valid_member_proof(self):
        changed=copy.deepcopy(self.records)
        changed[self.key]["result"]["result"]["pipeline_sha256"]="0"*64
        with self.assertRaises((cold.AmbiguousState,cold.UnsafePlan)):
            self.store.commit_models([],changed)
    def test_bad_new_payload_identity_does_not_reuse_old_proof_to_accept_it(self):
        records,item,_=_second_fit(self.root,self.runtime,self.records)
        item["source_sha256"]="0"*64
        with self.assertRaises((cold.AmbiguousState,cold.UnsafePlan)):
            self.store.commit_models([item],records)
    def test_incomplete_journal_blocks_append_before_proof_reuse(self):
        pending=self.store.journals/"pending-fixture";pending.mkdir()
        (pending/"journal.json").write_text(json.dumps({"state":"prepared","transaction_id":"pending-fixture"}))
        with self.assertRaises(cold.AmbiguousState):
            self.store.commit_models([],self.records)

if __name__=="__main__":
    unittest.main()
