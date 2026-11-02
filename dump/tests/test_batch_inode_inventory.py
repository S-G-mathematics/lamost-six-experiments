import json, os, tempfile, unittest
from unittest.mock import patch
import cold_model_storage as cold
from cold_model_storage import AmbiguousState
from test_cold_model_storage import setup_store, sha

class BatchInodeInventoryTests(unittest.TestCase):
    def test_core_uses_one_targeted_inventory_for_a_batch(self):
        with tempfile.TemporaryDirectory() as td:
            root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
            original=cold._safety.inode_paths_within_root_many
            with patch.object(cold._safety,'inode_paths_within_root_many',wraps=original) as scan:
                tx=s.commit_models([item],records)
            self.assertEqual(scan.call_count,1)
            self.assertEqual(json.loads((s.journals/tx/'journal.json').read_text())['state'],'complete')

    def _mutation_is_rejected_before_commit_then_rolls_back(self, mutation, restore):
        with tempfile.TemporaryDirectory() as td:
            root,rt,s,key,src,alias,obj,digest,records,item=setup_store(td)
            before=sha(s.archive); fired={'v':False}; original=s._verify_transaction_item
            def injected(*args,**kwargs):
                result=original(*args,**kwargs)
                if not fired['v']:
                    fired['v']=True; mutation(root,src,alias)
                return result
            s._verify_transaction_item=injected
            with self.assertRaises(AmbiguousState):s.commit_models([item],records)
            self.assertTrue(fired['v'])
            restore(root,src,alias)
            journals=list(s.journals.iterdir()); self.assertEqual(len(journals),1)
            self.assertEqual(s.recover(journals[0].name,records),'rolled_back')
            self.assertEqual(sha(s.archive),before)
            self.assertTrue(src.is_file()); self.assertTrue(alias.is_file())

    def test_new_external_hardlink_after_snapshot_is_rejected(self):
        self._mutation_is_rejected_before_commit_then_rolls_back(lambda root,src,alias:os.link(src,root/'external-link'),lambda root,src,alias:(root/'external-link').unlink())

    def test_alias_rename_after_snapshot_is_rejected(self):
        moved='pipeline.joblib.moved'
        self._mutation_is_rejected_before_commit_then_rolls_back(lambda root,src,alias:alias.rename(alias.with_name(moved)),lambda root,src,alias:alias.with_name(moved).rename(alias))

    def test_alias_deletion_after_snapshot_is_rejected(self):
        self._mutation_is_rejected_before_commit_then_rolls_back(lambda root,src,alias:alias.unlink(),lambda root,src,alias:os.link(src,alias))

    def test_same_path_replaced_by_equal_bytes_different_inode_is_rejected(self):
        def mutate(root,src,alias):
            data=alias.read_bytes();alias.unlink();alias.write_bytes(data)
        def restore(root,src,alias):alias.unlink();os.link(src,alias)
        self._mutation_is_rejected_before_commit_then_rolls_back(mutate,restore)

    def test_alias_symlink_substitution_is_rejected(self):
        def mutate(root,src,alias):alias.unlink();alias.symlink_to(src)
        def restore(root,src,alias):alias.unlink();os.link(src,alias)
        self._mutation_is_rejected_before_commit_then_rolls_back(mutate,restore)

    def test_source_write_and_restore_after_snapshot_is_rejected_by_ctime(self):
        def mutate(root,src,alias):
            original=src.read_bytes();src.write_bytes(b'X'+original[1:]);src.write_bytes(original)
        self._mutation_is_rejected_before_commit_then_rolls_back(mutate,lambda root,src,alias:None)

if __name__=='__main__':unittest.main()
