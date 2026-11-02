import json, os, tempfile, tracemalloc, unittest
from pathlib import Path
import cold_storage_safety as safety

class BatchInodeInventoryFixtureTests(unittest.TestCase):
    def test_2048_groups_three_aliases_inventory_and_journal_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);sources=[]
            for i in range(2048):
                d=root/('g%04d'%i);d.mkdir();src=d/'pipeline.joblib';src.write_bytes(b'fixture')
                os.link(src,d/'attempt.joblib');os.link(src,d/'checkpoint.joblib');sources.append(src)
            tracemalloc.start();inventory=safety.inode_paths_within_root_many(root,sources)
            journal={'items':[{'identity':[dev,ino],'aliases':[p.relative_to(root).as_posix() for p in row['paths']],
                               'link_count':row['link_count']} for (dev,ino),row in inventory.items()]}
            encoded=json.dumps(journal,separators=(',',':')).encode();_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            self.assertEqual(len(inventory),2048);self.assertTrue(all(len(row['paths'])==3 for row in inventory.values()))
            self.assertLess(len(encoded),16<<20);self.assertLess(peak,256<<20)

if __name__=='__main__':unittest.main()
