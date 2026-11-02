from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
if HERE.parent.parent.name=='staging':
    STAGE=HERE.parent; R=STAGE.parents[1]; CHILD=STAGE/'source/commit_batch_child.py'
else:
    R=HERE.parent; CHILD=R/'source/commit_batch_child.py'
sys.path.insert(0,str(R/'source'))
spec=importlib.util.spec_from_file_location('staged_commit_batch_child',CHILD)
child=importlib.util.module_from_spec(spec);sys.modules[spec.name]=child;spec.loader.exec_module(child)
cold=child.cold

def make_group(suffix='ok'):
    key=f'e5/rep_2/fit/direct/random_forest/label_noise_20/{suffix}'
    task_sha=('a' if suffix=='ok' else 'b')*64
    attempt='attempt_123'
    canonical=f'runtime_20261025/artifacts/{key}/pipeline.joblib'
    aliases=[canonical,f'runtime_20261025/artifacts/{key}/attempts/{attempt}/pipeline.joblib',f'runtime_20261025/artifacts/{key}/checkpoints/{task_sha}/pipeline.joblib']
    record={'key':key,'result':{'attempt_id':attempt,'task_sha256':task_sha}}
    item={'producer_task':key,'source_relpath':canonical,'source_sha256':'c'*64,'recorded_artifact_sha256':'c'*64,'aliases':aliases}
    return item,{key:record},key

class Store:
    def __init__(self,fail=None):
        self.calls=[];self.fail=fail;self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def _physical_path(self,rel):return self.root/rel
    def close(self):self.temp.cleanup()
    def seed(self,records,omit=(),malformed=()):
        omit=set(omit)
        for key,owner in records.items():
            result=owner.get('result') or {};attempt=result.get('attempt_id');task_sha=result.get('task_sha256')
            base=f'runtime_20261025/artifacts/{key}'
            rels=[f'{base}/fit_publication.json',f'{base}/fit_result.json',f'{base}/selection.json']
            if attempt:rels += [f'{base}/attempts/{attempt}/fit_publication.json',f'{base}/attempts/{attempt}/attempt.json',f'{base}/attempts/{attempt}/selection.json']
            if task_sha:rels += [f'{base}/checkpoints/{task_sha}/selection.json']
            for rel in rels:
                if rel in omit:continue
                q=self._physical_path(rel);q.parent.mkdir(parents=True,exist_ok=True)
                if rel in malformed:q.write_text('[]')
                elif rel.endswith('/fit_result.json'):q.write_text(json.dumps({'result':{}}))
                else:q.write_text('{}')
    def _alias_publication_evidence(self,owner,alias,digest):
        self.calls.append((owner['key'],alias,digest))
        if self.fail:
            kind,needle=self.fail
            if needle in alias:
                if kind=='ambiguous':raise cold.AmbiguousState('selection receipt missing or binding differs')
                if kind=='unsafe':raise cold.UnsafePlan('alias publication metadata is invalid')
                if kind=='json':raise json.JSONDecodeError('malformed selection receipt','{',0)
                if kind=='io':raise OSError('receipt storage unavailable')
                if kind=='structure':raise AttributeError('unexpected core validation defect')
        return {'owner_kind':'canonical_pipeline' if alias.endswith('/pipeline.joblib') else 'attempt_or_checkpoint'}

class CandidateFilterTests(unittest.TestCase):
    def test_valid_complete_publication_alias_group_retained(self):
        item,records,key=make_group();store=Store();self.addCleanup(store.close);store.seed(records)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[item]);self.assertEqual(len(store.calls),3)
        self.assertEqual(receipt['input_group_count'],1);self.assertEqual(receipt['eligible_group_count'],1)
        self.assertEqual(receipt['excluded_group_count'],0);self.assertEqual(receipt['exclusions'],[])

    def test_missing_attempt_selection_receipt_excludes_only_that_group(self):
        bad,bad_records,bad_key=make_group('missing')
        good,good_records,_=make_group('good')
        records={**bad_records,**good_records}
        omitted=[f'runtime_20261025/artifacts/{bad_key}/attempts/attempt_123/selection.json']
        store=Store();self.addCleanup(store.close);store.seed(records,omit=omitted)
        got,receipt=child.filter_candidate_publication_aliases([bad,good],records,store)
        self.assertEqual(got,[good]);self.assertEqual(receipt['input_group_count'],2)
        self.assertEqual(receipt['eligible_group_count'],1);self.assertEqual(receipt['excluded_group_count'],1)
        exc=receipt['exclusions'][0]
        self.assertEqual(exc['producer_task'],bad_key);self.assertEqual(exc['reason_type'],'UnsafePlan')
        self.assertEqual(exc['aliases'],bad['aliases']);self.assertEqual(exc['reason'],'selection fallback lacks authoritative validation SHA')

    def test_malformed_selection_json_is_recorded_as_known_bad_metadata(self):
        item,records,key=make_group('malformed');store=Store(('json','/attempts/'));self.addCleanup(store.close);store.seed(records)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[]);self.assertEqual(receipt['excluded_group_count'],1)
        self.assertEqual(receipt['exclusions'][0]['reason_type'],'JSONDecodeError')
        self.assertEqual(receipt['exclusions'][0]['producer_task'],key)

    def test_malformed_receipt_json_shape_is_recorded_as_unsafe(self):
        item,records,key=make_group('badshape');store=Store();self.addCleanup(store.close)
        malformed=[f'runtime_20261025/artifacts/{key}/fit_publication.json'];store.seed(records,malformed=malformed)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[]);self.assertEqual(receipt['excluded_group_count'],1)
        self.assertEqual(receipt['exclusions'][0]['reason_type'],'UnsafePlan')
        self.assertEqual(receipt['exclusions'][0]['producer_task'],key)

    def test_unexpected_core_validation_exception_propagates(self):
        item,records,_=make_group('unexpected');store=Store(('structure','/attempts/'));self.addCleanup(store.close);store.seed(records)
        with self.assertRaises(AttributeError):child.filter_candidate_publication_aliases([item],records,store)

    def test_wrong_publication_binding_excludes_group(self):
        item,records,key=make_group('mismatch');store=Store(('unsafe','/checkpoints/'));self.addCleanup(store.close);store.seed(records)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[]);self.assertEqual(receipt['exclusions'][0]['reason_type'],'UnsafePlan')
        self.assertEqual(receipt['exclusions'][0]['producer_task'],key)

    def test_unknown_alias_owner_is_recorded_not_committed(self):
        item,records,key=make_group('unknown')
        item['aliases']=item['aliases']+['runtime_20261025/artifacts/foreign/pipeline.joblib']
        store=Store();self.addCleanup(store.close);store.seed(records)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[]);self.assertEqual(receipt['excluded_group_count'],1)
        self.assertEqual(receipt['exclusions'][0]['reason_type'],'UnsafePlan')
        self.assertEqual(receipt['exclusions'][0]['producer_task'],key)

    def test_infrastructure_io_error_aborts_instead_of_filtering(self):
        item,records,_=make_group('io');store=Store(('io','/attempts/'));self.addCleanup(store.close);store.seed(records)
        with self.assertRaises(OSError):
            child.filter_candidate_publication_aliases([item],records,store)

    def test_empty_alias_evidence_is_explicit_bad_group(self):
        item,records,key=make_group('empty');item['aliases']=[]
        store=Store();self.addCleanup(store.close);store.seed(records)
        got,receipt=child.filter_candidate_publication_aliases([item],records,store)
        self.assertEqual(got,[]);self.assertEqual(receipt['excluded_group_count'],1)
        self.assertEqual(receipt['exclusions'][0]['producer_task'],key)
        self.assertEqual(receipt['exclusions'][0]['reason_type'],'UnsafePlan')

if __name__=='__main__':unittest.main(verbosity=2)
