import hashlib, json, os, random, tempfile, unittest
from pathlib import Path
import joblib
import cold_model_storage as cold
from test_cold_model_storage import setup_store

def rewrite_source(group, obj):
    root,runtime,store,key,source,alias,old_obj,digest,records,item=group
    joblib.dump(obj,source,compress=3);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    fit=records[key];fit['result']['result']['pipeline_sha256']=digest
    fit['result']['validation']['files']['pipeline.joblib']=digest
    fit['result']['result']['status']='success'
    fit['result']['validation']['status']='validated'
    fit['result']['validation']['task_key']=key
    task_sha=fit['result']['task_sha256'];attempt=fit['result']['attempt_id']
    fit_result={'attempt_id':attempt,'task_sha256':task_sha,'result':{'pipeline_sha256':digest,'status':'success'}}
    (source.parent/'fit_result.json').write_text(json.dumps(fit_result,sort_keys=True))
    (source.parent/'attempts'/attempt/'attempt.json').write_text(json.dumps(fit_result,sort_keys=True))
    publication={'attempt_id':attempt,'pipeline_sha256':digest,'published_path':str(source),'stage':'validated_publication','task_sha256':task_sha}
    (source.parent/'fit_publication.json').write_text(json.dumps(publication,sort_keys=True))
    (source.parent/'attempts'/attempt/'fit_publication.json').write_text(json.dumps(publication,sort_keys=True))
    item['source_sha256']=digest;item['recorded_artifact_sha256']=digest
    return group

def add_second_group(root,runtime,records):
    key='e3/rep_2/fit/real/random_forest';out=runtime/'artifacts'/key
    out.mkdir(parents=True);source=out/'pipeline.joblib'
    block=random.Random(22).randbytes(65536)
    obj={'fixture':'large-repeated-fixture','payload':block*16,'array':[3,1,4,1,5]}
    joblib.dump(obj,source,compress=3);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    attempt='fixture_attempt_02';task_sha=hashlib.sha256(b'task-sha-rep_2').hexdigest()
    attempt_dir=out/'attempts'/attempt;attempt_dir.mkdir(parents=True)
    checkpoint_dir=out/'checkpoints'/task_sha;checkpoint_dir.mkdir(parents=True)
    os.link(source,attempt_dir/'pipeline.joblib');os.link(source,checkpoint_dir/'pipeline.joblib')
    selection=json.dumps({'selected_params':{'fixture':'second'}},sort_keys=True).encode()
    selection_sha=hashlib.sha256(selection).hexdigest()
    for d in (out,attempt_dir,checkpoint_dir):(d/'selection.json').write_bytes(selection)
    fit_result={'attempt_id':attempt,'task_sha256':task_sha,'result':{'pipeline_sha256':digest,'status':'success'}}
    publication={'attempt_id':attempt,'pipeline_sha256':digest,'published_path':str(source),'stage':'validated_publication','task_sha256':task_sha}
    (out/'fit_result.json').write_text(json.dumps(fit_result,sort_keys=True))
    (attempt_dir/'attempt.json').write_text(json.dumps(fit_result,sort_keys=True))
    (out/'fit_publication.json').write_text(json.dumps(publication,sort_keys=True))
    (attempt_dir/'fit_publication.json').write_text(json.dumps(publication,sort_keys=True))
    fit={'key':key,'experiment':3,'kind':'fit','method':'random_forest','status':'validated_terminal','outcome':'successful','validation_state':'validated','artifact_dir':str(out),'dependencies':[],
         'result':{'attempt_id':attempt,'task_sha256':task_sha,'result':{'pipeline_sha256':digest},
                   'validation':{'status':'validated','task_key':key,'files':{'pipeline.joblib':digest,'selection.json':selection_sha}}}}
    consumer_key='e3/rep_2/eval/direct/random_forest/gmm'
    consumer={'key':consumer_key,'experiment':3,'kind':'eval','method':'random_forest','status':'validated_terminal','outcome':'successful','validation_state':'validated','dependencies':[key],'artifact_dir':str(runtime/'artifacts'/consumer_key),'result':{}}
    records[key]=fit;records[consumer_key]=consumer
    rel=source.relative_to(root).as_posix()
    item={'producer_task':key,'source_path':rel,'source_relpath':rel,'archive_member':rel,'source_sha256':digest,'recorded_artifact_sha256':digest,'consumer_tasks':[consumer_key],
          'aliases':[rel,(attempt_dir/'pipeline.joblib').relative_to(root).as_posix(),(checkpoint_dir/'pipeline.joblib').relative_to(root).as_posix()]}
    return item,source

class AggregateCodecTempBudgetTests(unittest.TestCase):
    def test_multigroup_budget_exhaustion_preappend_recovers_without_losing_sources(self):
        with tempfile.TemporaryDirectory() as td:
            first=setup_store(td)
            root,runtime,store,key,source,alias,obj,digest,records,item=first
            block=random.Random(11).randbytes(65536)
            rewrite_source(first,{'fixture':'first-repeated-fixture','payload':block*8,'array':[2,7,1]})
            second_item,second_source=add_second_group(root,runtime,records)
            store.storage_codec_policy='reversible-xz-v1'
            opts=store._codec_options();fixture_temp=runtime/'tmp'/'budget-fixture';fixture_temp.mkdir(parents=True);opts['temp_root']=fixture_temp
            payload,fields=cold._codec_storage.encode_entry_payload(source,archive_member='fixture/first',**opts)
            first_source_bytes=source.stat().st_size;first_encoded_bytes=int(fields['storage_encoding']['encoded_size_bytes'])
            payload.unlink()
            second_source_bytes=second_source.stat().st_size
            self.assertLess(first_encoded_bytes,first_source_bytes)
            self.assertGreater(second_source_bytes,first_source_bytes)
            budget=first_encoded_bytes+second_source_bytes-1
            before=hashlib.sha256(store.archive.read_bytes()).hexdigest()
            all_aliases=[root/x for x in item['aliases']+second_item['aliases']]
            with self.assertRaises(cold._codec_storage.codec.AggregateTempBudgetExceeded):
                store.commit_models([item,second_item],records,codec_temp_budget_bytes=budget)
            self.assertEqual(hashlib.sha256(store.archive.read_bytes()).hexdigest(),before)
            self.assertTrue(all(p.is_file() for p in all_aliases))
            journals=list(store.journals.glob('*/journal.json'));self.assertEqual(len(journals),1)
            doc=json.loads(journals[0].read_text());self.assertEqual(doc['state'],'prepared')
            self.assertEqual(doc.get('codec_temp_budget_bytes'),budget)
            self.assertEqual(store.recover(doc['transaction_id'],records),'rolled_back')
            self.assertEqual(hashlib.sha256(store.archive.read_bytes()).hexdigest(),before)
            self.assertTrue(all(p.is_file() for p in all_aliases))

if __name__=='__main__':unittest.main()
