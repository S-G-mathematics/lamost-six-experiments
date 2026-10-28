import json, os, tempfile, unittest, zipfile, hashlib
from pathlib import Path
from unittest.mock import patch
import cold_model_storage as cold
from cold_model_storage import AmbiguousState, ColdModelStore
from test_cold_model_storage import setup_store

class DurableBaselineDigestCacheTests(unittest.TestCase):
    def _commit_and_reopen(self,td):
        root,rt,store,key,src,alias,obj,digest,records,item=setup_store(td)
        tx=store.commit_models([item],records)
        fresh=ColdModelStore(root,rt,store.archive,store.manifest,store.journals)
        return root,rt,store,fresh,tx,records,item,digest

    def _read_actual_index(self,store):
        with zipfile.ZipFile(store.archive,'r',allowZip64=True) as z:
            return cold._zip_records_all(z),z.start_dir

    def test_complete_commit_persists_receipt_and_fresh_process_skips_only_baseline_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,fresh,tx,records,item,digest=self._commit_and_reopen(td)
            cache_path=fresh._baseline_cache_path();self.assertTrue(cache_path.is_file());self.assertFalse(cache_path.is_symlink())
            self.assertEqual(cache_path.stat().st_mode & 0o777,0o600)
            receipt=json.loads(cache_path.read_text());self.assertEqual(receipt['transaction_id'],tx)
            self.assertEqual(receipt['schema'],'verified-cold-archive-baseline/1')
            manifest=cold._manifest_load(fresh.manifest);actual_records,start=self._read_actual_index(fresh)
            ident=cold._archive_stat_identity(fresh.archive.stat())
            self.assertTrue(fresh._seed_verified_baseline_cache(manifest,actual_records,start,ident))
            reads=[];fn=cold.sha256_file_and_prefix
            def count(path,*args,**kwargs):
                if Path(path)==fresh.archive:reads.append(Path(path).stat().st_size)
                return fn(path,*args,**kwargs)
            with patch.object(cold,'sha256_file_and_prefix',side_effect=count):
                actual,_,checked=fresh._check_archive_manifest(manifest)
            self.assertEqual(actual,manifest['archive_sha256']);self.assertEqual(checked,actual_records)
            self.assertEqual(reads,[]) # verified baseline witness avoids only this whole-file pass
            self.assertGreater(receipt['archive_bytes'],0)

    def test_production_review_then_commit_skips_baseline_but_keeps_fresh_final_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,first_key,src,alias,obj,digest,records,item=setup_store(td)
            writer.commit_models([item],records)
            store=ColdModelStore(root,rt,writer.archive,writer.manifest,writer.journals)
            manifest=cold._manifest_load(store.manifest)
            reviewed=manifest['archive_sha256']
            _,baseline_start=self._read_actual_index(store)
            baseline_calls=[];baseline_fn=cold.sha256_file_and_prefix
            raw_calls=[];raw_fn=cold.sha256_file
            final_calls=[];final_fn=cold.sha256_file_and_prefixes
            def count_baseline(path,*args,**kwargs):
                if Path(path)==store.archive:baseline_calls.append('review/commit baseline')
                return baseline_fn(path,*args,**kwargs)
            def count_raw(path,*args,**kwargs):
                if Path(path)==store.archive:raw_calls.append('whole-file baseline')
                return raw_fn(path,*args,**kwargs)
            def count_final(path,*args,**kwargs):
                if Path(path)==store.archive:final_calls.append(tuple(args[0]) if args else None)
                return final_fn(path,*args,**kwargs)
            with patch.object(cold,'sha256_file_and_prefix',side_effect=count_baseline), \
                 patch.object(cold,'sha256_file',side_effect=count_raw), \
                 patch.object(cold,'sha256_file_and_prefixes',side_effect=count_final):
                got,_,_=store._check_reviewed_baseline(manifest,reviewed)
                self.assertEqual(got,reviewed)
                # This follows the child's baseline-review then commit sequence;
                # an empty fixture batch keeps the archive payload unchanged.
                store.commit_models([],records)
            self.assertEqual(baseline_calls,[])
            self.assertEqual(raw_calls,[])
            self.assertEqual(len(final_calls),1)
            self.assertEqual(len(final_calls[0]),2)
            self.assertEqual(final_calls[0][0],baseline_start)
            self.assertEqual(cold.sha256_file(store.archive),json.loads(store.manifest.read_text())['archive_sha256'])

    def test_missing_or_tampered_receipt_falls_back_to_one_fresh_baseline_hash(self):
        for mutation in ('missing','sha_tamper','records_tamper','symlink'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                root,rt,writer,fresh,tx,records,item,digest=self._commit_and_reopen(td)
                cp=fresh._baseline_cache_path()
                if mutation=='missing':cp.unlink()
                elif mutation=='symlink':
                    target=cp.with_name('saved_receipt.json');cp.rename(target);cp.symlink_to(target.name)
                else:
                    doc=json.loads(cp.read_text())
                    if mutation=='sha_tamper':doc['archive_sha256']='0'*64
                    else:doc['zip_records_sha256']='0'*64
                    cp.write_text(json.dumps(doc))
                manifest=cold._manifest_load(fresh.manifest);actual_records,start=self._read_actual_index(fresh);ident=cold._archive_stat_identity(fresh.archive.stat())
                self.assertFalse(fresh._seed_verified_baseline_cache(manifest,actual_records,start,ident))
                calls=[];fn=cold.sha256_file_and_prefix
                def count(path,*args,**kwargs):
                    if Path(path)==fresh.archive:calls.append(1)
                    return fn(path,*args,**kwargs)
                with patch.object(cold,'sha256_file_and_prefix',side_effect=count):fresh._check_archive_manifest(manifest)
                self.assertEqual(len(calls),1)

    def test_stat_drift_falls_back_to_fresh_hash_even_if_bytes_match(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,fresh,tx,records,item,digest=self._commit_and_reopen(td)
            st=fresh.archive.stat();os.utime(fresh.archive,ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
            manifest=cold._manifest_load(fresh.manifest);actual_records,start=self._read_actual_index(fresh);ident=cold._archive_stat_identity(fresh.archive.stat())
            self.assertFalse(fresh._seed_verified_baseline_cache(manifest,actual_records,start,ident))
            calls=[];fn=cold.sha256_file_and_prefix
            def count(path,*args,**kwargs):
                if Path(path)==fresh.archive:calls.append(1)
                return fn(path,*args,**kwargs)
            with patch.object(cold,'sha256_file_and_prefix',side_effect=count):fresh._check_archive_manifest(manifest)
            self.assertEqual(len(calls),1)

    def test_source_pin_change_falls_back_to_fresh_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,fresh,tx,records,item,digest=self._commit_and_reopen(td)
            manifest=cold._manifest_load(fresh.manifest);actual_records,start=self._read_actual_index(fresh);ident=cold._archive_stat_identity(fresh.archive.stat())
            pins=fresh._baseline_cache_source_pins();pins['commit_batch_child.py']='0'*64
            with patch.object(fresh,'_baseline_cache_source_pins',return_value=pins):
                self.assertFalse(fresh._seed_verified_baseline_cache(manifest,actual_records,start,ident))

    def test_pending_or_incomplete_journal_disables_cache(self):
        for mode in ('pending','incomplete'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                root,rt,writer,fresh,tx,records,item,digest=self._commit_and_reopen(td)
                manifest=cold._manifest_load(fresh.manifest);actual_records,start=self._read_actual_index(fresh);ident=cold._archive_stat_identity(fresh.archive.stat())
                if mode=='pending':
                    p=fresh.journals/'unfinished'/'journal.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'state':'appending'}))
                else:
                    p=fresh._journal_dir(tx)/'journal.json';j=json.loads(p.read_text());j['state']='unlinking';p.write_text(json.dumps(j))
                self.assertFalse(fresh._seed_verified_baseline_cache(manifest,actual_records,start,ident))

    def test_final_append_hash_and_prefix_comparison_remain_fresh_after_cache_seed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);runtime=root/'runtime';runtime.mkdir();archive=root/'a.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr('old',b'unchanged-old-member')
            store=ColdModelStore(root,runtime,archive,runtime/'manifest.json',runtime/'journals')
            with zipfile.ZipFile(archive) as z:old_records=cold._zip_records_all(z);start=z.start_dir
            baseline=archive.read_bytes();old_sha=hashlib.sha256(baseline).hexdigest();old_prefix=hashlib.sha256(baseline[:start]).hexdigest()
            # A valid in-process baseline proof, as supplied by the durable loader.
            with zipfile.ZipFile(archive) as z:records=cold._zip_records_all(z);zip_start=z.start_dir
            store._archive_identity_cache={'identity':cold._archive_stat_identity(archive.stat()),'sha256':old_sha,'zip_records':records,
                'prefix_bytes':zip_start,'prefix_sha256':hashlib.sha256(baseline[:zip_start]).hexdigest(),'zip_start_dir':zip_start}
            src=root/'runtime_20261025'/'artifacts'/'fixture'/'pipeline.joblib';src.parent.mkdir(parents=True);payload=b'new-model-payload';src.write_bytes(payload)
            item={'archive_member':'runtime_20261025/cold_models/fixture/model.zipmember','source_relpath':src.relative_to(root).as_posix(),
                  'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'crc32':zipfile.crc32(payload)}
            tx='ab'*16;store._journal_dir(tx).mkdir(parents=True)
            j={'transaction_id':tx,'archive_sha256_before':old_sha,'central_directory_offset':start,'old_zip_records':old_records,
               'items':[item],'storage_codec_policy':None,'prefix_sha256':old_prefix}
            final_calls=[];fn=cold.sha256_file_and_prefixes
            def count_final(path,*args,**kwargs):
                if Path(path)==archive:final_calls.append(tuple(args[0]) if args else None)
                return fn(path,*args,**kwargs)
            with patch.object(cold,'sha256_file_and_prefixes',side_effect=count_final):
                result=store._append_locked(j)
            self.assertEqual(result['state'],'archive_committed');self.assertEqual(len(final_calls),1)
            with zipfile.ZipFile(archive) as z:final_start=z.start_dir
            self.assertEqual(final_calls[0],(start,final_start))
            self.assertEqual(result['archive_sha256_after'],hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_prior_body_bitrot_in_baseline_prefix_is_rejected_before_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);runtime=root/'runtime';runtime.mkdir();archive=root/'a.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr('old',b'old-immutable-body')
            store=ColdModelStore(root,runtime,archive,runtime/'manifest.json',runtime/'journals')
            with zipfile.ZipFile(archive) as z:old_records=cold._zip_records_all(z);start=z.start_dir;old_info=z.getinfo('old')
            baseline=archive.read_bytes();old_sha=hashlib.sha256(baseline).hexdigest();old_prefix=hashlib.sha256(baseline[:start]).hexdigest()
            src=root/'runtime_20261025'/'artifacts'/'fixture'/'pipeline.joblib';src.parent.mkdir(parents=True);payload=b'new-model-payload';src.write_bytes(payload)
            item={'archive_member':'runtime_20261025/cold_models/fixture/model.zipmember','source_relpath':src.relative_to(root).as_posix(),
                  'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'crc32':zipfile.crc32(payload)}
            tx='cd'*16;store._journal_dir(tx).mkdir(parents=True)
            j={'transaction_id':tx,'archive_sha256_before':old_sha,'central_directory_offset':start,'old_zip_records':old_records,
               'items':[item],'storage_codec_policy':None,'prefix_sha256':old_prefix}
            original=store._verify_transaction_item;changed={'v':False}
            def verify_then_flip(*args,**kwargs):
                out=original(*args,**kwargs)
                if not changed['v']:
                    changed['v']=True
                    # Flip a byte in the old local-member header/body prefix before the final fresh digest.
                    data=bytearray(archive.read_bytes());data[old_info.header_offset]^=1;archive.write_bytes(data)
                return out
            store._verify_transaction_item=verify_then_flip
            with self.assertRaises(AmbiguousState):store._append_locked(j)
            self.assertTrue(changed['v']);self.assertTrue(src.is_file())

if __name__=='__main__':unittest.main()
