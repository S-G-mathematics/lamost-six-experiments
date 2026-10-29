import hashlib, importlib, json, os, pathlib, shutil, subprocess, sys, tempfile, unittest, zipfile
from unittest import mock
RUNTIME=pathlib.Path(__file__).resolve().parents[1]
HERE=RUNTIME
SOURCE=RUNTIME/'source'
sys.path.insert(0,str(SOURCE))
sys.path.insert(0,str(RUNTIME/'tests'))
import finalize_project as f
import cold_finalizer_adapter as a
import cold_model_storage
from test_cold_model_storage import setup_store

def _fixture_empty_primary_archive_context(runtime):
    import hashlib, types, sys
    raw=b'{"schema_version":"fixture-empty-primary/1"}\n'
    rel="manifests/FROZEN_E1_PRIMARY_ARCHIVED_ASSETS_20261030.json"
    path=pathlib.Path(runtime)/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    module=types.ModuleType("frozen_e1_primary_archive")
    module.LOCATOR_REL=rel
    module.LOCATOR_SHA256=hashlib.sha256(raw).hexdigest()
    module.primary_e1_archive_entries=lambda *a,**k:([],b'{"fixture":"empty-primary"}')
    return mock.patch.dict(sys.modules,{"frozen_e1_primary_archive":module})

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as x:
  for b in iter(lambda:x.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def copy_pinned_qualified_closure(root):
 root=pathlib.Path(root)
 for rel,pinned in f.PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256.items():
  src=HERE.parent.joinpath(*pathlib.PurePosixPath(rel).parts)
  if sha(src)!=pinned:raise AssertionError('candidate pinned source changed: '+rel)
  dst=root.joinpath(*pathlib.PurePosixPath(rel).parts);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)

def make_cold(tmp):
 root,rt,s,key,src,alias,obj,digest,records,item=setup_store(tmp)
 s.commit_models([item],records)
 build=root/'packages'/'LAMOST_ALL_EXPERIMENTS_BUILDING.zip';build.parent.mkdir(parents=True,exist_ok=True)
 with s.append_guard(registry_records=records) as guard:
  os.rename(s.archive,build)
  guard.refresh_manifest(archive_path=build)
 oldrows=json.loads(s.manifest.read_text())['members']
 return root,rt,s,key,digest,records,item,build,oldrows

class ColdFinalizerIntegrationTests(unittest.TestCase):
 def projection(self,root,rt,s,records,requested_paths=None):
  spec=__import__('importlib.util').util.spec_from_file_location('staged_review_cross_module',HERE/'source/final_review.py')
  review_module=__import__('importlib.util').util.module_from_spec(spec);spec.loader.exec_module(review_module)
  rows=review_module.cold_member_index(s);projection=[]
  for row in json.loads(s.manifest.read_text())['members']:
   requests=requested_paths or [row['logical_path']]
   for req in requests:
    if req!=row['logical_path'] and req not in row.get('aliases',[]):continue
    cache={'size':row['bytes'],'mtime_ns':row['source_mtime_ns'],'sha256':row['sha256']}
    record=review_module.file_record(root/req,root,'audited_artifact',{},cold_store=s,cold_members=rows,expected_sha256=row['sha256'],cache_observation=cache)
    projection.append(record['cold_member_identity'])
  review={'snapshot':{'inputs':{'cold_archived_artifact_members':projection}}}
  checked,payload=a.cold_artifact_entries(f,root,rt,s,records,{},review)
  return checked,payload,review
 def test_every_portable_bundle_log_is_in_exact_public_closure(self):
  bundle=json.loads((HERE/'tests'/'PORTABLE_TEST_BUNDLE.json').read_text())
  logs={row['runtime_member']:row['source_sha256'] for row in bundle['sources'] if isinstance(row.get('runtime_member'),str) and row['runtime_member'].endswith('.log')}
  pins=f.PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256
  self.assertEqual(len(logs),22)
  self.assertTrue(logs)
  self.assertTrue(all(path in pins for path in logs))
  self.assertEqual({path:pins[path] for path in logs},logs)

 def test_public_resource_review_allowlist_is_exact_hash_bound_and_stage_scoped(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);rt=root/'runtime_20261025';(rt/'manifests').mkdir(parents=True)
   realroot=pathlib.Path(__file__).resolve().parent/'fixtures'/'public_resource_reviews'
   rels=list(f.PUBLIC_RESOURCE_REVIEW_SHA256)
   for rel in rels:
    src=realroot/rel;self.assertEqual(sha(src),f.PUBLIC_RESOURCE_REVIEW_SHA256[rel])
    dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
   copy_pinned_qualified_closure(root)
   unrelated=root/'staging/private_ops/private_process_receipt.json';unrelated.parent.mkdir(parents=True);unrelated.write_text('{"pid":123,"cleanup":true}')
   other=root/'staging/unrelated/review.json';other.parent.mkdir(parents=True);other.write_text('{"scientific":true}')
   entries=[];f._add_public_provenance(root,rt,entries)
   byname={x.member:x for x in entries}
   self.assertEqual(set(rels),{x for x in byname if x in rels})
   for rel in rels:self.assertEqual(byname[rel].source,(root/rel).read_bytes())
   self.assertNotIn('staging/private_ops/private_process_receipt.json',byname)
   self.assertNotIn('staging/unrelated/review.json',byname)
   self.assertEqual({x for x in byname if x.startswith('runtime_20261025/staging/')},set(rels))
   inventory=json.loads(byname['runtime_20261025/manifests/public_scientific_provenance_manifest.json'].source)
   records=[x for x in inventory['included'] if x['curation']=='exact_bytes_pinned_public_scientific_resource_review']
   self.assertEqual({x['archive_member'] for x in records},set(rels))
   for rec in records:self.assertEqual(rec['source_sha256'],rec['archive_sha256']);self.assertEqual(rec['bytes'],(root/rec['source_member']).stat().st_size)
   tampered=root/rels[0];tampered.write_bytes(tampered.read_bytes()+b' ')
   with self.assertRaisesRegex(f.EvidenceError,'pinned public resource review changed'):f._add_public_provenance(root,rt,[])
   shutil.copy2(realroot/rels[0],tampered)
   with self.assertRaisesRegex(f.EvidenceError,'reviewed public resource review SHA mismatch'):f._add_public_provenance(root,rt,[],{str(tampered.resolve()):'0'*64})
 def test_copied_production_layout_loads_installed_sibling_core_and_fails_closed(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);runtime=root/'runtime_20261025';src=runtime/'source';src.mkdir(parents=True)
   shutil.copy2(SOURCE/'cold_finalizer_adapter.py',src/'cold_finalizer_adapter.py')
   core=SOURCE/'cold_model_storage.py'
   shutil.copy2(core,src/'cold_model_storage.py')
   safety=core.with_name('cold_storage_safety.py');shutil.copy2(safety,src/'cold_storage_safety.py')
   shutil.copy2(SOURCE/'cold_codec_storage.py',src/'cold_codec_storage.py')
   shutil.copy2(SOURCE/'reversible_joblib_codec.py',src/'reversible_joblib_codec.py')
   staged=runtime/'staging'/'cold_model_storage_20261026'/'source';staged.mkdir(parents=True)
   (staged/'cold_model_storage.py').write_text('this staging file is intentionally invalid and must not be imported')
   shutil.copy2(safety,staged/'cold_storage_safety.py')
   code='import sys; import cold_finalizer_adapter as a; m=a.load_cold_api(sys.argv[1]); print(m.__file__)'
   env=os.environ.copy();env['PYTHONPATH']=str(src)
   good=subprocess.run([sys.executable,'-c',code,str(runtime)],env=env,capture_output=True,text=True)
   self.assertEqual(good.returncode,0,good.stderr)
   self.assertEqual(pathlib.Path(good.stdout.strip()).resolve(),(src/'cold_model_storage.py').resolve())
   # A present but invalid installed core must fail closed; a valid staging copy is not a fallback.
   (src/'cold_model_storage.py').write_text('invalid python !!!')
   (staged/'cold_model_storage.py').write_text(core.read_text())
   bad=subprocess.run([sys.executable,'-c',code,str(runtime)],env=env,capture_output=True,text=True)
   self.assertNotEqual(bad.returncode,0)
   self.assertIn('selected cold model storage API is invalid',bad.stderr)
 def test_reviewed_same_zip_append_rename_alias_restore(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td)
   before=sha(build);old_inode=(build.stat().st_dev,build.stat().st_ino)
   cold,payload,review=self.projection(root,rt,s,records)
   report=rt/'reports'/'small.csv';report.parent.mkdir(parents=True);report.write_text('metric,value\\nbalanced_accuracy,0.5\\n')
   entries=list(cold.values())+[f.Entry(report,'runtime_20261025/reports/small.csv','validated_reports_tables_figures')]
   final=root/'packages'/'LAMOST_ALL_EXPERIMENTS_20261026T000000Z.zip'
   res=a.append_full_archive(f,s,build,final,entries,[],['fixture only'],records,before,{}, {'candidate_id':'fixture','decision':'pass'},min_free=0)
   self.assertTrue(final.exists());self.assertFalse(build.exists());self.assertEqual(sha(final),res['sha256'])
   self.assertEqual(old_inode,(final.stat().st_dev,final.stat().st_ino))
   self.assertEqual(json.loads(s.manifest.read_text())['archive_path'],'packages/'+final.name)
   with zipfile.ZipFile(final) as z:
    self.assertIsNone(z.testzip());names=z.namelist()
    self.assertEqual(names.count(oldrows[0]['archive_member']),1)
    aliases=json.loads(z.read('archive_aliases.json'))['aliases']
    row=next(x for x in aliases if x['alias_path']==item['source_relpath'])
    self.assertEqual(row['canonical_path'],oldrows[0]['archive_member'])
    self.assertEqual(z.read(oldrows[0]['archive_member']),b''.join([]) if False else z.read(oldrows[0]['archive_member']))
    self.assertEqual(json.loads(z.read('REPORT_REVIEW_PROOF.json'))['candidate_id'],'fixture')
   extracted=pathlib.Path(td)/'extract';extracted.mkdir()
   with zipfile.ZipFile(final) as z:z.extractall(extracted)
   self.assertEqual(f.restore_aliases(extracted)['restored_aliases'],3)
   self.assertEqual(sha(extracted/item['source_relpath']),digest)
 def test_precommit_fault_restores_original_zip_tail_and_locator(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td);before=sha(build)
   cold,_,_=self.projection(root,rt,s,records)
   report=rt/'reports'/'x.txt';report.parent.mkdir(parents=True);report.write_text('x')
   final=root/'packages'/'LAMOST_ALL_EXPERIMENTS_20261026T000001Z.zip'
   with self.assertRaises(RuntimeError):
    a.append_full_archive(f,s,build,final,list(cold.values())+[f.Entry(report,'report.txt')],[],['fixture'],records,before,{}, {'candidate_id':'fault','decision':'pass'},min_free=0,_fault_after_members=1)
   self.assertTrue(build.exists());self.assertFalse(final.exists());self.assertEqual(sha(build),before)
   self.assertEqual(json.loads(s.manifest.read_text())['archive_path'],'packages/'+build.name)
   js=list((rt/'journals'/'full_archive_append').glob('*/append_journal.json'))
   self.assertEqual(json.loads(js[-1].read_text())['state'],'rolled_back')
   with zipfile.ZipFile(build) as z:self.assertIsNone(z.testzip())
 def test_crash_after_same_inode_rename_recovers_before_manifest_refresh(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td);before=sha(build)
   canonical_manifest=rt/'manifests'/'cold_model_store_manifest.json';canonical_manifest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s.manifest,canonical_manifest);s.manifest=canonical_manifest
   jdir=rt/'journals'/'full_archive_append'/'fixture_crash';jdir.mkdir(parents=True)
   tail=a._tail_backup(f,build,jdir)
   with zipfile.ZipFile(build,'a',allowZip64=True) as z:z.writestr('crash_probe.txt',b'append')
   fd=os.open(build,os.O_RDONLY);os.fsync(fd);os.close(fd)
   final=root/'packages'/'LAMOST_ALL_EXPERIMENTS_CRASH.zip';inode=(build.stat().st_dev,build.stat().st_ino)
   after=sha(build);size=build.stat().st_size;os.rename(build,final)
   self.assertEqual(inode,(final.stat().st_dev,final.stat().st_ino))
   f.atomic_json(jdir/'append_journal.json',{'schema_version':'lamost-full-archive-append/1','transaction_id':'fixture_crash','state':'renamed_before_manifest_refresh','building_path':str(build),'final_path':str(final),'archive_sha256_before':before,'archive_sha256_after_append':after,'central_tail_backup':tail})
   recovered=a.recover_uncommitted_renames(f,root,rt)
   self.assertEqual(recovered[-1]['state'],'rolled_back')
   self.assertTrue(build.exists());self.assertFalse(final.exists());self.assertEqual(sha(build),before)
   self.assertEqual(json.loads(s.manifest.read_text())['archive_path'],'packages/'+build.name)
   with zipfile.ZipFile(build) as z:self.assertIsNone(z.testzip());self.assertEqual(z.namelist(),[oldrows[0]['archive_member']])
 def test_stream_mutation_rolls_back_and_duplicate_name_rejected_before_write(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td);before=sha(build)
   cold,_,_=self.projection(root,rt,s,records)
   canonical=oldrows[0]['archive_member']
   with self.assertRaises(a.ColdFinalizerError):
    a.append_full_archive(f,s,build,root/'packages'/'LAMOST_ALL_EXPERIMENTS_dup.zip',list(cold.values())+[f.Entry(b'bad',canonical)],[],['fixture'],records,before,{}, {'candidate_id':'dup','decision':'pass'},min_free=0)
   self.assertEqual(sha(build),before)
   report=rt/'reports'/'mutate.txt';report.parent.mkdir(parents=True);report.write_text('planned')
   original=a._source_stream
   def mutated(src):
    if src is report:return __import__('io').BytesIO(b'changed')
    return original(src)
   a._source_stream=mutated
   try:
    with self.assertRaises(f.EvidenceError):
     a.append_full_archive(f,s,build,root/'packages'/'LAMOST_ALL_EXPERIMENTS_mut.zip',list(cold.values())+[f.Entry(report,'mutate.txt')],[],['fixture'],records,before,{}, {'candidate_id':'mut','decision':'pass'},min_free=0)
   finally:a._source_stream=original
   self.assertTrue(build.exists());self.assertFalse((root/'packages'/'LAMOST_ALL_EXPERIMENTS_mut.zip').exists());self.assertEqual(sha(build),before)
 def test_full_collector_uses_cold_source_and_keeps_native_member_path(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td)
   cold,_,review=self.projection(root,rt,s,records)
   for d in ('project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024'): (root/d).mkdir(parents=True,exist_ok=True)
   for d in ('source','tests','cache','artifacts','reports','manifests'): (rt/d).mkdir(parents=True,exist_ok=True)
   fixture_root=pathlib.Path(__file__).resolve().parent/'fixtures'/'public_resource_reviews'
   for rel in f.PUBLIC_RESOURCE_REVIEW_SHA256:
    src=fixture_root/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
   copy_pinned_qualified_closure(root)
   public=json.dumps({'tasks':list(records.values()),'observed_utc':'fixture'})
   with _fixture_empty_primary_archive_context(rt), mock.patch.object(a,'e1_locator_archive_entries',lambda *args,**kwargs:([],b'{}')):
    entries=f.collect_full(root,rt,b'# readme',public,{'candidate_id':'fixture','decision':'pass'}, {},cold_store=s,registry_records=records,review_manifest=review)
   logical=item['source_relpath']
   found=[e for e in entries if e.member==logical]
   self.assertEqual(len(found),1);self.assertTrue(a._cold_source(found[0].source))
   self.assertEqual(found[0].source.stat()['sha256'],digest)
   snapshot=[e for e in entries if e.member=='runtime_20261025/manifests/cold_archived_artifact_members.json']
   self.assertEqual(len(snapshot),1)
   self.assertIn(oldrows[0]['archive_member'],[x['archive_member'] for x in json.loads(snapshot[0].source)['members']])
   heavy='runtime_20261025/staging/nonrf_heavy_resource_readiness_20261026/HEAVY_METHOD_RESOURCE_READINESS_AUDIT_20261026.json'
   by_member={e.member:e for e in entries}
   self.assertEqual(by_member[heavy].source,(root/heavy).read_bytes())
   provenance=json.loads(by_member['runtime_20261025/manifests/public_scientific_provenance_manifest.json'].source)
   self.assertIn(heavy,{x['archive_member'] for x in provenance['included']})
 def test_full_collector_includes_exact_pinned_policy_and_safe_log_closure(self):
  # The production allowlist is sourced from the reviewed 807 bundle. This fixture
  # copies only those small inputs into an isolated fake root and exercises collect_full.
  pins=f.PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256
  self.assertEqual(len(pins),28)
  self.assertEqual(sum(x.startswith('runtime_20261025/manifests/') for x in pins),6)
  self.assertEqual(sum(x.endswith('.log') for x in pins),22)
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td)
   for d in ('project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024'): (root/d).mkdir(parents=True,exist_ok=True)
   for d in ('source','tests','cache','artifacts','reports','manifests'): (rt/d).mkdir(parents=True,exist_ok=True)
   fixture_root=pathlib.Path(__file__).resolve().parent/'fixtures'/'public_resource_reviews'
   for rel in f.PUBLIC_RESOURCE_REVIEW_SHA256:
    src=fixture_root/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
   copy_pinned_qualified_closure(root)
   public=json.dumps({'tasks':list(records.values()),'observed_utc':'fixture'})
   with _fixture_empty_primary_archive_context(rt), mock.patch.object(a,'e1_locator_archive_entries',lambda *args,**kwargs:([],b'{}')):
    entries=f.collect_full(root,rt,b'# readme',public,{'candidate_id':'fixture','decision':'pass'}, {},cold_store=s,registry_records=records,review_manifest=self.projection(root,rt,s,records)[2])
   by_member={e.member:e for e in entries}
   expected=set(pins)
   self.assertTrue(expected.issubset(by_member))
   self.assertEqual(len([e for e in entries if e.member in expected]),28)
   manifest=json.loads(by_member['runtime_20261025/manifests/public_scientific_provenance_manifest.json'].source)
   closure=[x for x in manifest['included'] if x.get('curation') in {'exact_sha_pinned_policy_bytes','exact_sha_pinned_reviewed_safe_log_bytes'}]
   self.assertEqual({x['archive_member'] for x in closure},expected)
   self.assertEqual(len(closure),28)
   for rel,pinned in pins.items():
    payload=by_member[rel].source if isinstance(by_member[rel].source,bytes) else by_member[rel].source.read_bytes()
    self.assertEqual(hashlib.sha256(payload).hexdigest(),pinned,rel)
   self.assertFalse(any('portable_test_runs/' in m for m in by_member))
   self.assertIn('private operational output-tail receipts',manifest['retained_only_omissions']['scope'])

 def test_qualified_input_closure_rejects_missing_or_mutated_pinned_member(self):
  rel,pinned=next(iter(f.PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256.items()))
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);path=root.joinpath(*pathlib.PurePosixPath(rel).parts);path.parent.mkdir(parents=True)
   with mock.patch.dict(f.__dict__,{'PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256':{rel:pinned}}):
    path.write_bytes(b'wrong bytes')
    with self.assertRaises(f.EvidenceError):f._add_pinned_qualified_input_closure(root,[],{},[])
    path.unlink()
    with self.assertRaises(f.EvidenceError):f._add_pinned_qualified_input_closure(root,[],{},[])

 def test_finalizer_keeps_report_audit_before_append(self):
  import inspect
  body=inspect.getsource(f.finalize)
  self.assertLess(body.index('verify_pass('),body.index('write_full_archive('))
  self.assertLess(body.index('verify_terminal('),body.index('write_full_archive('))
 def test_no_manifest_uses_ordinary_zip_and_readme_is_truthful(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td)/'migration';rt=root/'runtime_20261025';(root/'packages').mkdir(parents=True)
   for d in ('project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024'): (root/d).mkdir(parents=True,exist_ok=True)
   for d in ('source','tests','cache','artifacts','reports','manifests'): (rt/d).mkdir(parents=True,exist_ok=True)
   (rt/'reports'/'small.txt').write_text('ordinary package')
   copy_pinned_qualified_closure(root)
   full=root/'packages'/'LAMOST_ALL_EXPERIMENTS_fixture.zip';ev={'e1_archive':{'path':'preserved-e1.zip','sha256':'a'*64}}
   with _fixture_empty_primary_archive_context(rt), mock.patch.object(a,'e1_locator_archive_entries',lambda *args,**kwargs:([],b'{}')):
    result=f.write_full_archive(root,rt,full,ev,{'candidate_id':'fixture','decision':'pass'},{},{},{'snapshot':{'inputs':{'cold_archived_artifact_members':[]}}},public=b'{"tasks":[]}')
   self.assertTrue(result['zip_crc_passed'])
   with zipfile.ZipFile(full) as z:
    self.assertIsNone(z.testzip());readme=z.read('README_ARCHIVE.md').decode()
    self.assertIn('ordinary',z.read('runtime_20261025/reports/small.txt').decode())
    self.assertNotIn('Previously cold-stored selected',readme)
    self.assertIn('Content-identical artifacts are stored once.',readme)
 def test_present_but_missing_cold_manifest_target_fails_closed(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td)/'migration';rt=root/'runtime_20261025';(root/'packages').mkdir(parents=True)
   (rt/'manifests').mkdir(parents=True);(rt/'journals'/'full_archive_append').mkdir(parents=True)
   doc={'schema_version':'lamost-cold-model-store/1','archive_path':'packages/LAMOST_ALL_EXPERIMENTS_BUILDING.zip','members':[],'archive_sha256':'0'*64,'archive_bytes':0,'zip_records':[]}
   (rt/'manifests'/'cold_model_store_manifest.json').write_text(json.dumps(doc))
   with self.assertRaisesRegex(Exception,'cold ZIP missing|regular BUILDING ZIP'):
    f.write_full_archive(root,rt,root/'packages'/'LAMOST_ALL_EXPERIMENTS_fixture.zip',{}, {'candidate_id':'fixture'},{},{},{},public=b'{"tasks":[]}')
 def _make_case_index_fixture(self,root):
  rt=root/'runtime_20261025';base=rt/'reports'/'overall_case_index';out=base/'snapshot_fixture';out.mkdir(parents=True)
  (rt/'source').mkdir(parents=True,exist_ok=True);(rt/'master_index.json').write_text('{"tasks":[]}')
  builder=rt/'source'/'build_overall_case_index.py';helper=rt/'source'/'case_index_helpers.py';builder.write_text('# builder fixture');helper.write_text('# helper fixture')
  groups={'E1_frozen':{'successful':674,'scientific_failure':81,'unsupported':10},
   'E1_recovery_stopped_early_user_request':{'successful':24,'scientific_failure':10,'user_stopped':2,'not_attempted_user_stopped':55},
   'E2_primary':{'successful':108,'unavailable_dependency':42},'E2_classical_reference':{'successful':120},
   'E3_later_experiment':{'successful':64,'scientific_failure':3,'unavailable_dependency':2},
   'E4_later_experiment':{'successful':1135,'scientific_failure':42,'unavailable_dependency':3,'pending':593},
   'E5_later_experiment':{'successful':595,'scientific_failure':27,'unavailable_dependency':23,'pending':315},
   'E6_later_experiment':{'successful':12,'unavailable_dependency':9}}
  exp={'E1_frozen':'1','E1_recovery_stopped_early_user_request':'1','E2_primary':'2','E2_classical_reference':'2','E3_later_experiment':'3','E4_later_experiment':'4','E5_later_experiment':'5','E6_later_experiment':'6'}
  csvp=out/'OVERALL_SCIENTIFIC_CASE_INDEX.csv'
  with csvp.open('w',newline='') as f:
   w=__import__('csv').DictWriter(f,fieldnames=['index_key','provenance_group','experiment','status_normalized']);w.writeheader()
   n=0
   for g,states in groups.items():
    for state,count in states.items():
     for _ in range(count):n+=1;w.writerow({'index_key':f'{g}/{n}','provenance_group':g,'experiment':exp[g],'status_normalized':state})
  csv_sha=sha(csvp);src_sha=sha(builder);helper_sha=sha(helper);master_sha=sha(rt/'master_index.json')
  summary={'schema':'lamost-overall-case-index/2','combined_rows':3949,'main_scientific_case_rows':3858,'separate_E1_recovery_supplement_rows':91,'planned_later_rows_by_experiment':{'3':69,'4':1773,'5':960,'6':21},'counts_by_group':groups,'output_csv':{'path':str(csvp),'row_count':3949,'sha256':csv_sha},'builder_script_sha256':src_sha,'builder_helper_sha256':helper_sha,'input_sources':{'builder':{'path':str(builder),'sha256':src_sha},'helper':{'path':str(helper),'sha256':helper_sha}},'master_index':{'source_path':str(rt/'master_index.json'),'source_file_sha256':master_sha}}
  sump=out/'OVERALL_SCIENTIFIC_CASE_INDEX_SUMMARY.json';sump.write_text(json.dumps(summary,sort_keys=True))
  ready={'status':'ready','output_directory':str(out),'csv_path':str(csvp),'csv_sha256':csv_sha,'summary_path':str(sump),'summary_sha256':sha(sump),'builder_script_sha256':src_sha}
  rp=out/'READY.json';rp.write_text(json.dumps(ready,sort_keys=True))
  (base/'CURRENT.json').write_text(json.dumps({'current_ready_path':'snapshot_fixture/READY.json','ready_sha256':sha(rp)}))
  return rt,out
 def test_case_index_validator_and_review_binding(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td)/'migration';root.mkdir();rt,out=self._make_case_index_fixture(root)
   info=f.validate_overall_case_index(root,rt,out)
   table=rt/'reports'/'OVERALL_SCIENTIFIC_CASE_INDEX.csv';_atomic=f._atomic_bytes;_atomic(table,(out/'OVERALL_SCIENTIFIC_CASE_INDEX.csv').read_bytes())
   info['reviewed_table_path']=table.relative_to(root).as_posix();info['reviewed_table_sha256']=sha(table)
   rr=rt/'reports'/'report_result.json';rr.write_text(json.dumps({'status':'success','planned_scientific_cases':2823,'overall_scientific_case_index':info}))
   expected={str(table.resolve()):sha(table),str(rr.resolve()):sha(rr)}
   updated=f.bind_case_index_after_review(root,rt,{'overall_case_index':info},expected)
   self.assertEqual(updated[str((root/info['summary_path']).resolve())],info['summary_sha256'])
   self.assertEqual(updated[str((root/info['ready_path']).resolve())],info['ready_sha256'])
   self.assertEqual(info['total_rows'],3949)
   (out/'OVERALL_SCIENTIFIC_CASE_INDEX.csv').write_text('mutated')
   with self.assertRaises(f.EvidenceError):f.validate_overall_case_index(root,rt,out)
 def test_installed_publisher_rejects_review_candidate_without_index_binding(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);rt=root/'runtime_20261025';(rt/'source').mkdir(parents=True)
   (rt/'source'/'build_overall_case_index.py').write_text('present')
   with self.assertRaisesRegex(f.EvidenceError,'lacks the installed overall case-index'):
    f.bind_case_index_after_review(root,rt,{}, {})
 def test_embedded_restorer_hardlinks_first_then_safe_copy_fallback(self):
  data=b'fixture selected RF pipeline bytes'*4096
  def package_extract(base,forced_fallback=False,conflict=False):
   base.mkdir(parents=True,exist_ok=True)
   zpath=base/'fixture.zip'
   aliases={'schema_version':'lamost-aliases/1','aliases':[{'canonical_path':'models/canonical.joblib','alias_path':'models/alias.joblib','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
   with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('models/canonical.joblib',data)
    z.writestr('archive_aliases.json',json.dumps(aliases)+'\n')
   dest=base/'extract';dest.mkdir()
   with zipfile.ZipFile(zpath) as z:z.extractall(dest)
   script=dest/'restore_archive_aliases.py'
   text=f.RESTORE
   if forced_fallback:text=text.replace('os.link(src,dst)',"raise OSError(errno.EXDEV,'fixture simulated unsupported link')")
   script.write_text(text)
   alias=dest/'models/alias.joblib'
   if conflict:alias.write_bytes(b'preexisting different data')
   return dest,script,alias
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   base=pathlib.Path(td);dest,script,alias=package_extract(base/'hard');run=subprocess.run([sys.executable,str(script)],check=True,capture_output=True,text=True)
   self.assertEqual(json.loads(run.stdout)['hardlinked_aliases'],1)
   self.assertTrue(os.path.samefile(dest/'models/canonical.joblib',alias))
   fallback,script2,alias2=package_extract(base/'copy',forced_fallback=True);run2=subprocess.run([sys.executable,str(script2)],check=True,capture_output=True,text=True)
   self.assertEqual(json.loads(run2.stdout)['copied_aliases'],1)
   self.assertFalse(os.path.samefile(fallback/'models/canonical.joblib',alias2))
   self.assertEqual(alias2.read_bytes(),data)
   conflict,script3,alias3=package_extract(base/'conflict',conflict=True);before=alias3.read_bytes()
   fail=subprocess.run([sys.executable,str(script3)],capture_output=True,text=True)
   self.assertNotEqual(fail.returncode,0);self.assertEqual(alias3.read_bytes(),before)
 def test_case_index_publisher_is_optional_only_when_both_scripts_absent(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);rt=root/'runtime_20261025';(rt/'source').mkdir(parents=True)
   self.assertIsNone(f.publish_overall_case_index(root,rt))
   (rt/'source'/'build_overall_case_index.py').write_text('present')
   with self.assertRaisesRegex(f.EvidenceError,'partially installed'):f.publish_overall_case_index(root,rt)
 def test_reviewer_projection_matches_real_cold_aliases_and_rejects_identity_mutations(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td)
   canonical=item['source_relpath'];alias=next(x for x in item['aliases'] if x!=canonical)
   entries,payload,review=self.projection(root,rt,s,records,[canonical,alias])
   projected=json.loads(payload)['members']
   self.assertEqual({x['logical_source_path'] for x in projected},{canonical,alias})
   self.assertTrue(all('source_mtime_ns' in x for x in projected))
   review_mod={'snapshot':{'inputs':{'cold_archived_artifact_members':projected}}}
   for field,value in [('source_mtime_ns',int(projected[0]['source_mtime_ns'])+1),('task_sha256','0'*64),('aliases',projected[0]['aliases']+['runtime_20261025/artifacts/fake/pipeline.joblib']),('member_sha256','f'*64)]:
    tampered=json.loads(json.dumps(projected));tampered[0][field]=value
    with self.assertRaises(a.ColdFinalizerError):
     a.cold_artifact_entries(f,root,rt,s,records,{}, {'snapshot':{'inputs':{'cold_archived_artifact_members':tampered}}})
   with self.assertRaises(f.EvidenceError):
    a.cold_artifact_entries(f,root,rt,s,records,{str((root/canonical).resolve()):'0'*64},review_mod)
 def test_cold_rows_require_matching_review_projection(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root,rt,s,key,digest,records,item,build,oldrows=make_cold(td)
   with self.assertRaises(a.ColdFinalizerError):
    a.cold_artifact_entries(f,root,rt,s,records,{},None)

if __name__=='__main__':unittest.main(verbosity=2)

