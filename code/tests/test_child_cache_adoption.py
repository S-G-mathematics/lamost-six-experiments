import pathlib,tempfile,zipfile,json,os,unittest
from types import SimpleNamespace
import commit_batch_child as child
import cold_model_storage as cold
HERE=pathlib.Path(__file__).resolve().parent
class CacheAdoptionTests(unittest.TestCase):
 def make_store(self,tmp):
  root=pathlib.Path(tmp)/"migration";runtime=root/"runtime_20261025";runtime.mkdir(parents=True)
  archive=runtime/"packages"/"small.zip";archive.parent.mkdir()
  store=cold.ColdModelStore(root,runtime,archive,runtime/"manifests"/"cold.json",runtime/"journals"/"store")
  with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED) as z:z.writestr("one",b"tiny payload")
  records=store._records();sha=cold.sha256_file(archive)
  manifest={"archive_sha256":sha,"archive_bytes":archive.stat().st_size,"zip_records":records}
  store._check_archive_manifest(manifest)
  j={"archive_sha256_after":sha,"member_records_after":records}
  return store,manifest,j
 def clone(self,s,**changes):
  attrs={"root":s.root,"archive":s.archive,"manifest":s.manifest,"_archive_identity_cache":dict(s._archive_identity_cache)}
  attrs.update(changes);return SimpleNamespace(**attrs)
 def test_adopts_only_matching_store_and_journal_bindings(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   s,manifest,j=self.make_store(td);s2=self.clone(s,_archive_identity_cache=None)
   self.assertTrue(child._adopt_verified_core_cache(s,s2,j))
   self.assertEqual(s2._archive_identity_cache,s._archive_identity_cache)
   cases=[
    (self.clone(s,root=s.root/"foreign"),self.clone(s,_archive_identity_cache=None),j),
    (s,self.clone(s,_archive_identity_cache=None),dict(j,archive_sha256_after="0"*64)),
    (s,self.clone(s,_archive_identity_cache=None),dict(j,member_records_after=[])),
    (s,self.clone(s,archive=s.archive.with_name("foreign.zip"),_archive_identity_cache=None),j),
    (self.clone(s,_archive_identity_cache=dict(s._archive_identity_cache,identity=(0,0,0,0,0))),self.clone(s,_archive_identity_cache=None),j),
   ]
   for source,target,journal in cases:
    self.assertFalse(child._adopt_verified_core_cache(source,target,journal))
    self.assertIsNone(target._archive_identity_cache)
 def test_same_size_tamper_refuses_cache_and_fresh_manifest_check_detects_it(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   s,manifest,j=self.make_store(td);target=self.clone(s,_archive_identity_cache=None)
   with zipfile.ZipFile(s.archive) as z:info=z.getinfo("one")
   offset=info.header_offset+30+len(info.filename.encode())
   before=s.archive.stat();data=bytearray(s.archive.read_bytes());data[offset]^=1;s.archive.write_bytes(data)
   os.utime(s.archive,ns=(before.st_atime_ns,before.st_mtime_ns))
   self.assertFalse(child._adopt_verified_core_cache(s,target,j))
   self.assertIsNone(target._archive_identity_cache)
   with self.assertRaises(cold.AmbiguousState):target_check(s,manifest)
def target_check(store,manifest):
 fresh=cold.ColdModelStore(store.root,store.runtime,store.archive,store.manifest,store.journals)
 return fresh._check_archive_manifest(manifest)
if __name__=="__main__":unittest.main(verbosity=2)
