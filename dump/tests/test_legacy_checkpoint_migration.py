import json
import tempfile
import unittest
import cold_model_storage as cold
from test_cold_model_storage import setup_store,sha

class LegacyCheckpointMigration(unittest.TestCase):
 def test_legacy_partial_unlink_with_pending_intent_migrates_safely(self):
  with tempfile.TemporaryDirectory() as td:
   root,rt,store,key,src,alias,obj,digest,records,item=setup_store(td)
   original=store._unlink_aliases
   def force_legacy(j,fail_after_unlinks=None):
    j.pop('unlink_checkpoint_policy',None)
    return original(j,fail_after_unlinks)
   store._unlink_aliases=force_legacy
   with self.assertRaises(RuntimeError):store.commit_models([item],records,fail_after_unlinks=1)
   jp=next(store.journals.glob('*/journal.json'));j=json.loads(jp.read_text())
   self.assertEqual(j['state'],'unlinking');self.assertNotIn('unlink_checkpoint_policy',j)
   remaining=[p for x in j['items'] for p in x['aliases'] if p not in x['removed_aliases']]
   self.assertTrue(remaining)
   for x in j['items']:
    for p in x['aliases']:
     if p in remaining and p not in x['unlink_intents']:x['unlink_intents'].append(p)
   before=sha(store.archive)
   j['unlink_checkpoint_policy']={'schema':'bounded-intent-batch/1','max_aliases':48}
   cold._atomic_json(jp,j)
   store._unlink_aliases=original
   self.assertEqual(store.recover(j['transaction_id'],records),'complete')
   final=json.loads(jp.read_text());self.assertEqual(final['state'],'complete')
   self.assertEqual(sha(store.archive),before)
   for x in final['items']:
    self.assertEqual(set(x['removed_aliases']),set(x['aliases']))
    for rel in x['aliases']:self.assertFalse((root/rel).exists())
