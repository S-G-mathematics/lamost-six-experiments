import json, os, pathlib, tempfile, time, unittest, zipfile
from unittest.mock import patch
import cold_model_storage as cold
from cold_model_storage import AmbiguousState
from test_cold_model_storage import setup_store, sha, np

POLICY={'schema':'bounded-intent-batch/1','max_aliases':48}
class UnlinkCheckpointBatchTests(unittest.TestCase):
    def _direct_journal(self,td,group_count=1):
        root,rt,store,key,src,alias,obj,digest,records,item=setup_store(td)
        payload=src.read_bytes(); archive_member='retained/unique-fixture.bin'
        with zipfile.ZipFile(store.archive,'a',compression=zipfile.ZIP_STORED) as z:z.writestr(archive_member,payload)
        rows=[]
        for gi in range(group_count):
            if gi==0:base=src
            else:
                base=root/'runtime_20261025'/'batch_fixture'/f'g{gi:04d}'/'pipeline.joblib';base.parent.mkdir(parents=True);base.write_bytes(payload)
            if gi==0:
                aliases=[base,alias,root/'runtime_20261025'/'artifacts'/key/'checkpoints'/records[key]['result']['task_sha256']/'pipeline.joblib']
            elif group_count>1:
                aliases=[base]
            else:
                aliases=[base]
                for ai in range(1,3):
                    q=base.with_name(f'{base.name}.alias{ai}');os.link(base,q);aliases.append(q)
            st=base.stat()
            rows.append({'task_key':f'fixture{gi}','task_sha256':'0'*64,'sha256':digest,
                         'aliases':[q.relative_to(root).as_posix() for q in aliases],
                         'removed_aliases':[],'unlink_intents':[],'device':st.st_dev,'inode':st.st_ino})
        tx='fixture_'+('a'*24);d=store._journal_dir(tx);d.mkdir(parents=True,exist_ok=True)
        j={'transaction_id':tx,'state':'archive_committed','items':rows,'unlink_checkpoint_policy':dict(POLICY)}
        return root,store,src,payload,archive_member,j,d/'journal.json'

    def test_crashes_at_0_1_2_and_47_recover_without_losing_archived_bytes(self):
        for after in (0,1,2):
            with self.subTest(after=after), tempfile.TemporaryDirectory() as td:
                root,store,src,payload,member,j,jp=self._direct_journal(td)
                with self.assertRaises(RuntimeError):store._unlink_aliases(j,fail_after_unlinks=after)
                disk=json.loads(jp.read_text());row=disk['items'][0]
                self.assertEqual(len(row['unlink_intents']),3)
                self.assertEqual(row['removed_aliases'],[])
                self.assertEqual(sum((root/r).exists() for r in row['aliases']),3-max(after,0))
                # Recovery replays intent-bearing missing paths and completes the group.
                self.assertIsNone(store._unlink_aliases(disk))
                done=json.loads(jp.read_text());self.assertEqual(done['state'],'complete')
                self.assertEqual(set(done['items'][0]['removed_aliases']),set(done['items'][0]['aliases']))
                with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

    def test_48_alias_checkpoint_has_bounded_full_journal_rewrites(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td)
            # Add 45 in-root hardlinks to make exactly one full 48-alias checkpoint.
            for i in range(45):
                q=root/'runtime_20261025'/'artifacts'/j['items'][0]['task_key']/f'extra{i:02d}.joblib';q.parent.mkdir(parents=True,exist_ok=True);os.link(src,q);j['items'][0]['aliases'].append(q.relative_to(root).as_posix())
            j['items'][0]['inode']=src.stat().st_ino;j['items'][0]['device']=src.stat().st_dev
            original=cold._atomic_json
            with patch.object(cold,'_atomic_json',wraps=original) as writes:
                with self.assertRaises(RuntimeError):store._unlink_aliases(j,fail_after_unlinks=47)
            self.assertEqual(writes.call_count,2) # state + all 48 durable intents
            disk=json.loads(jp.read_text());self.assertEqual(len(disk['items'][0]['unlink_intents']),48)
            self.assertEqual(disk['items'][0]['removed_aliases'],[])
            self.assertEqual(sum((root/r).exists() for r in disk['items'][0]['aliases']),1)
            with patch.object(cold,'_atomic_json',wraps=original) as writes:
                store._unlink_aliases(disk)
            self.assertEqual(writes.call_count,3) # recovery start + batch completion + complete
            self.assertLessEqual(writes.call_count+2,2*((48+47)//48)+3)
            self.assertEqual(len(json.loads(jp.read_text())['items'][0]['removed_aliases']),48)
            with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

    def test_missing_alias_without_durable_intent_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td)
            victim=root/j['items'][0]['aliases'][1];victim.unlink()
            with self.assertRaises(AmbiguousState):store._unlink_aliases(j)
            disk=json.loads(jp.read_text());self.assertEqual(disk['items'][0]['unlink_intents'],[])
            self.assertEqual(sum((root/r).exists() for r in disk['items'][0]['aliases']),2)
            with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

    def test_tampered_present_alias_after_intent_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td);fired={'x':False};orig=cold._atomic_json
            def write_then_mutate(path,obj):
                result=orig(path,obj)
                if not fired['x'] and obj.get('items') and obj['items'][0]['unlink_intents']:
                    fired['x']=True;src.write_bytes(b'Z'+payload[1:])
                return result
            with patch.object(cold,'_atomic_json',side_effect=write_then_mutate):
                with self.assertRaises(AmbiguousState):store._unlink_aliases(j)
            self.assertTrue(fired['x']);self.assertTrue(src.exists());src.write_bytes(payload)
            recovered=json.loads(jp.read_text());store._unlink_aliases(recovered)
            with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

    def test_external_hardlink_after_intent_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td);fired={'x':False};orig=cold._atomic_json;extra=root/'external-hardlink'
            def write_then_link(path,obj):
                result=orig(path,obj)
                if not fired['x'] and obj.get('items') and obj['items'][0]['unlink_intents']:
                    fired['x']=True;os.link(src,extra)
                return result
            with patch.object(cold,'_atomic_json',side_effect=write_then_link):
                with self.assertRaises(AmbiguousState):store._unlink_aliases(j)
            self.assertTrue(fired['x']);self.assertTrue(all((root/r).exists() for r in j['items'][0]['aliases']))
            extra.unlink();store._unlink_aliases(json.loads(jp.read_text()))
            with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

    def test_legacy_journal_without_policy_keeps_per_alias_checkpointing(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td)
            j.pop('unlink_checkpoint_policy')
            with patch.object(cold,'_atomic_json',wraps=cold._atomic_json) as writes:store._unlink_aliases(j)
            self.assertEqual(writes.call_count,8) # unlinking + 2 writes per alias + complete

    def test_commit_journal_opts_in_and_recovery_finishes_0_1_2(self):
        for n in (0,1,2):
            with self.subTest(n=n),tempfile.TemporaryDirectory() as td:
                root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
                with self.assertRaises(RuntimeError):s.commit_models([item],records,fail_after_unlinks=n)
                jps=list(s.journals.glob('*/journal.json'));self.assertEqual(len(jps),1)
                j=json.loads(jps[0].read_text());self.assertEqual(j['unlink_checkpoint_policy'],POLICY)
                self.assertEqual(s.recover(j['transaction_id'],records),'complete')
                loaded=s.load_joblib(item['source_relpath'],digest);self.assertEqual(loaded['fixture'],obj['fixture']);np.testing.assert_array_equal(loaded['array'],obj['array'])

    def test_actual_1238_item_3714_alias_metadata_rewrite_count_and_time(self):
        with tempfile.TemporaryDirectory() as td:
            root,store,src,payload,member,j,jp=self._direct_journal(td,group_count=1238)
            # Add two aliases per group; total 3,714 paths and 1,238 logical items.
            for i,row in enumerate(j['items']):
                base=root/row['aliases'][0]
                # _direct_journal already made three aliases for group zero only.
                if i==0:continue
                for ai in (1,2):
                    q=base.with_name(f'{base.name}.extra{ai}');os.link(base,q);row['aliases'].append(q.relative_to(root).as_posix())
                row['device']=base.stat().st_dev;row['inode']=base.stat().st_ino
            self.assertEqual(len(j['items']),1238);self.assertEqual(sum(len(x['aliases']) for x in j['items']),3714)
            # Add normalized receipt/central-directory metadata to approximate
            # the full live transaction journal without reading source payloads.
            old_records=[]
            for i in range(273):
                old_records.append({'member':f'old/member/{i:04d}/pipeline.joblib','crc32':i,'file_size':123456,'compressed_size':123456,'compress_type':0,'header_offset':i*128000,'flag_bits':0,'external_attr':2175008768,'date_time':[2026,1,1,0,0,0],'extra_sha256':'0'*64,'comment_sha256':'0'*64})
            records=list(old_records);required=[]
            for i,row in enumerate(j['items']):
                key=row['task_key'];cons=[f'e3/rep_{i:04d}/eval/a','e3/rep_{i:04d}/eval/b'];required.extend([key]+cons)
                row.update({'task_sha256':'4'*64,'experiment':3,'method':'random_forest','logical_path':row['aliases'][0],
                            'source_relpath':row['aliases'][0],'archive_member':'runtime_20261025/cold_models/'+key+'.zipmember',
                            'source_mtime_ns':123456789,'bytes':len(payload),'source_sha256':'5'*64,'crc32':123456789,'header_offset':0,'consumer_tasks':cons,
                            'alias_owner_task_keys':[key]+cons})
                row['alias_owners']=[{'alias_path':a,'task_key':key,'task_sha256':'4'*64,'consumer_tasks':cons,
                                      'owner_kind':kind,'attempt_id':'attempt-'+str(i),'publication_sha256':'1'*64,
                                      'fit_result_sha256':'2'*64,'selection_sha256':'3'*64}
                                     for a,kind in zip(row['aliases'],['canonical_pipeline','attempt_publication','task_checkpoint'])]
                records.append({'member':row['archive_member'],'crc32':row['crc32'],'file_size':row['bytes'],'compressed_size':row['bytes'],'compress_type':0,'header_offset':0,'flag_bits':0,'external_attr':2175008768,'date_time':[2026,1,1,0,0,0],'extra_sha256':'0'*64,'comment_sha256':'0'*64})
            j.update({'schema_version':'lamost-cold-model-store/1','archive_relpath':'packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip',
                      'archive_sha256_before':'0'*64,'archive_size_before':43_489_579_894,'archive_device':1,'archive_inode':2,
                      'central_directory_offset':43_400_000_000,'old_zip_records':old_records,'old_zip_records_sha256':'0'*64,
                      'required_task_keys':sorted(required),'process_inventory_complete':True,'created_utc':'2026-10-28T09:00:00Z',
                      'member_records_after':records,'archive_sha256_after':'1'*64,'archive_bytes_after':43_500_000_000,
                      'tail_sha256':'0'*64,'prefix_sha256':'0'*64})
            started=time.monotonic()
            with patch.object(cold,'_atomic_json',wraps=cold._atomic_json) as writes:store._unlink_aliases(j)
            elapsed=time.monotonic()-started;expected=2*((3714+47)//48)+2
            self.assertEqual(writes.call_count,expected)
            print(f'benchmark items=1238 aliases=3714 journal_bytes={jp.stat().st_size} writes={writes.call_count} seconds={elapsed:.3f}')
            with zipfile.ZipFile(store.archive) as z:self.assertEqual(z.read(member),payload)

if __name__=='__main__':unittest.main()
