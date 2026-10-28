import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import cold_model_storage as cold
from cold_model_storage import AmbiguousState, ColdModelStore
from test_cold_model_storage import setup_store

class RecoveryArchiveDigestReuseTests(unittest.TestCase):
    def _committed_unlinking(self,td):
        root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
        with self.assertRaises(RuntimeError):s.commit_models([item],records,fail_after_unlinks=0)
        jp=next((rt/'journals'/'cold_store').glob('*/journal.json'));tx=jp.parent.name
        restarted=ColdModelStore(root,rt,s.archive,s.manifest,s.journals)
        return root,rt,s,restarted,tx,jp,records,item,digest

    def test_recovery_reuses_one_fresh_whole_sha_for_same_archive_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,restarted,tx,jp,records,item,digest=self._committed_unlinking(td)
            archive=restarted.archive;whole=[];ordinary=[]
            orig_prefix=cold.sha256_file_and_prefix;orig_sha=cold.sha256_file
            def count_prefix(path,*args,**kwargs):
                if Path(path)==archive:whole.append(1)
                return orig_prefix(path,*args,**kwargs)
            def count_sha(path,*args,**kwargs):
                if Path(path)==archive:ordinary.append(1)
                return orig_sha(path,*args,**kwargs)
            with patch.object(cold,'sha256_file_and_prefix',side_effect=count_prefix),patch.object(cold,'sha256_file',side_effect=count_sha):
                self.assertEqual(restarted.recover(tx,records),'complete')
            self.assertEqual(len(whole),1);self.assertEqual(ordinary,[])
            self.assertEqual(restarted.load_joblib(item['source_relpath'],digest)['fixture'],'joblib-stream')

    def test_transaction_record_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,restarted,tx,jp,records,item,digest=self._committed_unlinking(td)
            j=json.loads(jp.read_text());j['member_records_after'][0]['external_attr']^=1;jp.write_text(json.dumps(j))
            with self.assertRaises(AmbiguousState):restarted.recover(tx,records)

    def test_archive_payload_change_after_member_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,restarted,tx,jp,records,item,digest=self._committed_unlinking(td)
            original=restarted._validate_existing_members
            def validate_then_mutate(*args,**kwargs):
                result=original(*args,**kwargs)
                with open(restarted.archive,'ab') as f:f.write(b'archive-tamper')
                return result
            with patch.object(restarted,'_validate_existing_members',side_effect=validate_then_mutate):
                with self.assertRaises(AmbiguousState):restarted.recover(tx,records)

    def test_stat_drift_forces_fresh_hash_and_accepts_unchanged_archive_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,restarted,tx,jp,records,item,digest=self._committed_unlinking(td)
            original=restarted._validate_existing_members;counts=[];hashfn=cold.sha256_file_and_prefix
            def validate_then_touch(*args,**kwargs):
                result=original(*args,**kwargs);st=restarted.archive.stat()
                os.utime(restarted.archive,ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
                return result
            def count_hash(path,*args,**kwargs):
                if Path(path)==restarted.archive:counts.append(1)
                return hashfn(path,*args,**kwargs)
            with patch.object(restarted,'_validate_existing_members',side_effect=validate_then_touch),patch.object(cold,'sha256_file_and_prefix',side_effect=count_hash):
                self.assertEqual(restarted.recover(tx,records),'complete')
            self.assertEqual(len(counts),1)

    def test_archive_identity_change_during_fresh_rehash_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,writer,restarted,tx,jp,records,item,digest=self._committed_unlinking(td)
            original=restarted._validate_existing_members;counts=[];hashfn=cold.sha256_file_and_prefix
            def validate_then_touch(*args,**kwargs):
                result=original(*args,**kwargs);st=restarted.archive.stat()
                os.utime(restarted.archive,ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
                return result
            def hash_then_touch(path,*args,**kwargs):
                result=hashfn(path,*args,**kwargs)
                if Path(path)==restarted.archive:
                    counts.append(1)
                    if len(counts)==1:
                        st=restarted.archive.stat();os.utime(restarted.archive,ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
                return result
            with patch.object(restarted,'_validate_existing_members',side_effect=validate_then_touch),patch.object(cold,'sha256_file_and_prefix',side_effect=hash_then_touch):
                with self.assertRaises(AmbiguousState):restarted.recover(tx,records)
            self.assertEqual(len(counts),1)

if __name__=='__main__':unittest.main()
