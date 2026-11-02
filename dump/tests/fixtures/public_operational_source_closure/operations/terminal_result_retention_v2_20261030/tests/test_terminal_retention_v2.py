import hashlib,json,os,sqlite3,tempfile,unittest,zlib
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
SRC=HERE.parent/"source";sys.path.insert(0,str(SRC))
import terminal_result_retention_v2 as rr

def write_json(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,sort_keys=True))

class PlanTests(unittest.TestCase):
 def fixture(self):
  td=tempfile.TemporaryDirectory();base=Path(td.name);root=base/"root";root.mkdir()
  db=root/"runtime_20261025/registry.sqlite";db.parent.mkdir(parents=True)
  c=sqlite3.connect(db);c.execute("create table tasks(key text,record text)");c.commit();c.close()
  rt=root/"runtime_20261025";src=rt/"source";src.mkdir()
  pins={}
  for name in ("worker.py","science.py"):
   body=("# fixture "+name+"\n").encode();(src/name).write_bytes(body);pins[name]=hashlib.sha256(body).hexdigest()
  write_json(rt/"manifests/freeze.json",{"source_sha256":pins})
  return td,root,base
 def add_eval(self,root,case,*,status="validated_terminal",kind="eval",outcome="successful",condition=None,aliases=None,data=None):
  data=data or (("payload-"+case).encode())
  rel=f"runtime_20261025/artifacts/{case}/test_outcomes.npz";p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  exp=int(case.split("/")[0][1:]);task={"key":case,"experiment":exp,"kind":kind,"status":status,"outcome":outcome,"validation_state":"validated","scientific_case":True,"route":"direct","dependencies":[]}
  if condition is not None:task["condition"]=condition
  v=p.parent/"validation.json";write_json(v,{"status":"validated","task_key":case,"files":{"test_outcomes.npz":hashlib.sha256(data).hexdigest()}})
  crc=f"{zlib.crc32(data):08x}"
  row={"category":"runtime_test_outcomes","source_path":rel,"archive_member":rel,"asset":"a.zip","source_bytes":len(data),"source_sha256":hashlib.sha256(data).hexdigest(),"archive_crc32":crc,"aliases":aliases or [],"asset_member_evidence_status":"exact_member_verified"}
  return task,row,p,data
 def save_catalog(self,base,tasks,rows,target=rr.MAX_TARGET):
  db=base/"runtime_20261025/registry.sqlite";db.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(db);c.execute("create table tasks(key text,record text)")
  c.executemany("insert into tasks values(?,?)",[(t["key"],json.dumps(t)) for t in tasks]);c.commit();c.close()
  # Each fixture asset is explicitly remote+member verified.
  doc={"schema":"lamost-scientific-array-release/1","release":{"repo":"fixture/repo","tag":"fixture"},"assets":[{"name":"a.zip","bytes":100000,"sha256":"a"*64,"remote_verified":True}],"files":rows}
  mp=base/"catalog.json";write_json(mp,doc);return mp,db
 def test_plans_terminal_e3_e6_eval_outcomes_and_includes_control(self):
  td,root,b=self.fixture()
  try:
   tasks=[];rows=[]
   for k,c in [("e3/rep_1/eval/direct/gmm",None),("e4/rep_1/eval/direct/rf/control","control"),("e5/rep_1/eval/direct/rf/clean",None),("e6/rep_1/ensemble/equal/eval",None)]:
    t,r,_,_=self.add_eval(root,k,condition=c);tasks.append(t);rows.append(r)
   mp,db=self.save_catalog(b,tasks,rows)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["scope_experiments"],[3,4,5,6])
   self.assertEqual(plan["validated_success_terminal_rows"],4)
   self.assertEqual(plan["selected_count"],4)
   self.assertEqual({x["task_family"] for x in plan["selected"]},{3,4,5,6})
   self.assertTrue(plan["storage_target_is_not_scientific_resource_limit"])
  finally:td.cleanup()
 def test_fit_pending_and_out_of_scope_rows_not_selected(self):
  td,root,b=self.fixture()
  try:
   tasks=[];rows=[]
   good,gr,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean");tasks.append(good);rows.append(gr)
   bad,br,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/feature_noise_10",status="waiting_for_dependency");tasks.append(bad);rows.append(br)
   fit,fr,_,_=self.add_eval(root,"e5/rep_1/fit/direct/rf/clean",kind="fit");tasks.append(fit);rows.append(fr)
   mp,db=self.save_catalog(b,tasks,rows);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],1)
   self.assertEqual(plan["selected"][0]["task_key"],good["key"])
  finally:td.cleanup()
 def test_alias_group_requires_all_terminal_owners_and_deduplicates_inode(self):
  td,root,b=self.fixture()
  try:
   k1="e4/rep_1/eval/direct/rf/A_half";k2="e4/rep_1/eval/direct/rf/F_half";data=b"identical held-out outcomes"
   t1,r1,p1,_=self.add_eval(root,k1,data=data);t2,r2,p2,_=self.add_eval(root,k2,data=data)
   p2.unlink();os.link(p1,p2)
   r1["aliases"]=[r2["source_path"]];r2["aliases"]=[r1["source_path"]]
   tasks=[t1,t2];rows=[r1,r2];mp,db=self.save_catalog(b,tasks,rows);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],1)
   grp=plan["complete_known_inode_group_review_only"]["groups"][0]
   self.assertEqual(set(grp["owner_task_keys"]),{k1,k2})
   self.assertFalse(grp["retirement_enabled"])
  finally:td.cleanup()
 def test_group_owner_query_is_fresh_exact_and_fail_closed(self):
  td,root,b=self.fixture()
  try:
   k1="e4/rep_1/eval/direct/rf/A_half";k2="e4/rep_1/eval/direct/rf/F_half";data=b"owner query fixture"
   t1,r1,p1,_=self.add_eval(root,k1,data=data);t2,r2,p2,_=self.add_eval(root,k2,data=data)
   p2.unlink();os.link(p1,p2);r1["aliases"]=[r2["source_path"]];r2["aliases"]=[r1["source_path"]]
   mp,db=self.save_catalog(b,[t1,t2],[r1,r2]);plan=rr.make_plan(root,mp,db);group=plan["complete_known_inode_group_review_only"]["groups"][0]
   owner_db=sqlite3.connect(root/"runtime_20261025/registry.sqlite");owner_db.executemany("insert into tasks values(?,?)",[(t1["key"],json.dumps(t1)),(t2["key"],json.dumps(t2)),("unrelated-malformed",json.dumps(["not a task object"]))]);owner_db.commit();owner_db.close()
   self.assertTrue(rr._check_group(root,group,hash_payload=False))
   missing={**group,"owner_task_keys":group["owner_task_keys"]+["missing-owner"]}
   with self.assertRaises(rr.RetentionError):rr._check_group(root,missing,hash_payload=False)
   c=sqlite3.connect(root/"runtime_20261025/registry.sqlite");c.execute("update tasks set record=? where key=?",(json.dumps(["malformed owner"]),k1));c.commit();c.close()
   with self.assertRaises(rr.RetentionError):rr._check_group(root,group,hash_payload=False)
  finally:td.cleanup()

 def test_unknown_hardlink_owner_fails_closed(self):
  td,root,b=self.fixture()
  try:
   k1="e4/rep_1/eval/direct/rf/A_half";k2="e5/rep_1/eval/direct/rf/clean";data=b"same bytes"
   t1,r1,p1,_=self.add_eval(root,k1,data=data);t2,r2,p2,_=self.add_eval(root,k2,data=data)
   p2.unlink();extra=root/"runtime_20261025/artifacts/e6/rep_1/eval/direct/rf/extra/test_outcomes.npz";extra.parent.mkdir(parents=True);os.link(p1,extra)
   r1["aliases"]=[r2["source_path"]]
   mp,db=self.save_catalog(b,[t1,t2],[r1,r2]);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],0)
  finally:td.cleanup()
 def test_missing_member_metadata_is_excluded(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean");r.pop("archive_crc32")
   mp,db=self.save_catalog(b,[t],[r]);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["published_member_evidence_missing"],1)
  finally:td.cleanup()
 def test_duplicate_member_is_rejected(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean")
   mp,db=self.save_catalog(b,[t],[r,r])
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db)
  finally:td.cleanup()
 def test_ten_gib_ceiling_and_independent_storage_semantics(self):
  td,root,b=self.fixture()
  try:
   mp,db=self.save_catalog(b,[],[])
   self.assertEqual(rr.make_plan(root,mp,db,target=10*rr.GIB)["target_bytes"],10*rr.GIB)
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db,target=10*rr.GIB+1)
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db,target=-1)
  finally:td.cleanup()
 def test_only_experiments_3_through_6_allowed(self):
  td,root,b=self.fixture()
  try:
   mp,db=self.save_catalog(b,[],[])
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db,experiments=(2,3,4,5,6))
  finally:td.cleanup()
 def test_asset_member_requires_catalog_asset_integrity(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean")
   mp,db=self.save_catalog(b,[t],[r])
   doc=json.loads(mp.read_text());doc["assets"][0]["remote_verified"]=False;write_json(mp,doc)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["published_member_evidence_missing"],1)
  finally:td.cleanup()

 def save_v2_catalog(self,root,base,tasks,rows,*,remote=True):
  base=root/"catalog_fixture";base.mkdir(parents=True,exist_ok=True)
  db=root/"runtime_20261025/registry.sqlite";c=sqlite3.connect(db)
  c.executemany("insert into tasks values(?,?)",[(t["key"],json.dumps(t)) for t in tasks]);c.commit();c.close()
  remote_doc=base/"remote_verification.json";write_json(remote_doc,{"schema":"lamost-remote-verified-release-asset-locator/1","asset_id":12345,"asset_name":"a.zip","bytes":100000,"sha256":"a"*64,"github_digest":"sha256:"+"a"*64,"repo":"S-G-mathematics/lamost-six-experiments","release_tag":"fixture","local_zip_crc_checked":True})
  member_doc=base/"release_manifest.json";write_json(member_doc,{"schema":"fixture-member-manifest/1"})
  payload_csv=base/"payloads.csv";payload_csv.write_text("fixture\n")
  cases_csv=base/"cases.csv";cases_csv.write_text("fixture\n")
  assets=[{"asset_name":"a.zip","asset_bytes":100000,"asset_sha256":"a"*64,"asset_remote_verified":remote,"asset_remote_evidence_path":str(remote_doc),"asset_remote_evidence_sha256":hashlib.sha256(remote_doc.read_bytes()).hexdigest()}]
  catalog_rows=[]
  for row in rows:
   item={**row,"task_key":row.get("task_key") or rr.taskkey(row["source_path"]),"canonical_source_task_key":row.get("task_key") or rr.taskkey(row["source_path"]),"source_kind":"canonical_validated_test_outcomes","asset_name":"a.zip","asset_bytes":100000,"asset_sha256":"a"*64,"asset_remote_verified":remote,"asset_remote_evidence_path":str(remote_doc),"asset_remote_evidence_sha256":hashlib.sha256(remote_doc.read_bytes()).hexdigest(),"member_record_evidence_path":str(member_doc),"member_record_evidence_sha256":hashlib.sha256(member_doc.read_bytes()).hexdigest(),"native_inode_links_accounted":False}
   item.setdefault("native_path_present",True);item.setdefault("retention_status","native_present");item.setdefault("restore_required",False)
   catalog_rows.append(item)
  doc={"schema":"lamost-terminal-result-retention-catalog/1","release":{"repo":"fixture/repo","tag":"fixture"},"assets":assets,"payload_records":catalog_rows}
  mp=base/"catalog.json";write_json(mp,doc)
  receipt={"schema":"lamost-terminal-result-retention-catalog-receipt/1","catalog_path":str(mp),"catalog_sha256":hashlib.sha256(mp.read_bytes()).hexdigest(),"payloads_csv_path":str(payload_csv),"payloads_csv_sha256":hashlib.sha256(payload_csv.read_bytes()).hexdigest(),"cases_csv_path":str(cases_csv),"cases_csv_sha256":hashlib.sha256(cases_csv.read_bytes()).hexdigest()}
  write_json(base/"CATALOG_RECEIPT.json",receipt)
  return mp,db
 def test_shared_asset_evidence_inherits_only_after_identity_match_for_attempt_group(self):
  td,root,b=self.fixture()
  try:
   key="e4/rep_1/eval/direct/rf/A_half";t,r,p,_=self.add_eval(root,key)
   alias_rel=f"runtime_20261025/artifacts/{key}/attempts/attempt_001/test_outcomes.npz";alias=root/alias_rel;alias.parent.mkdir(parents=True);os.link(p,alias)
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r])
   doc=json.loads(mp.read_text());row=doc["payload_records"][0]
   row.pop("asset_remote_evidence_path");row.pop("asset_remote_evidence_sha256")
   write_json(mp,doc)
   receipt=mp.parent/"CATALOG_RECEIPT.json";rd=json.loads(receipt.read_text());rd["catalog_sha256"]=hashlib.sha256(mp.read_bytes()).hexdigest();write_json(receipt,rd)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["validated_success_terminal_rows"],1)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],1)
   group=plan["complete_known_inode_group_review_only"]["groups"][0]
   self.assertEqual(set(group["native_paths"]),{r["source_path"],alias_rel})
   self.assertEqual(group["asset_remote_evidence_path"],doc["assets"][0]["asset_remote_evidence_path"])
   self.assertTrue(group["asset_remote_evidence_inherited_from_asset_record"])
  finally:td.cleanup()
 def test_actual_catalog_asset_evidence_inherits_for_small_native_attempt_fixture(self):
  actual_root=Path("/home/ubuntu/lamost_e1_migration_20261023")
  actual_path=actual_root/"operations/terminal_result_retention_catalog_20261030/catalog_v2_verified104.json"
  actual=json.loads(actual_path.read_text())
  payload=next(x for x in actual["payload_records"] if x.get("source_kind")=="canonical_validated_test_outcomes")
  actual_asset=next(x for x in actual["assets"] if x.get("asset_name")==payload["asset_name"])
  td,root,b=self.fixture()
  try:
   key="e4/rep_1/eval/direct/rf/A_half";task,row,p,_=self.add_eval(root,key)
   alias_rel=f"runtime_20261025/artifacts/{key}/attempts/attempt_001/test_outcomes.npz";alias=root/alias_rel;alias.parent.mkdir(parents=True);os.link(p,alias)
   base=root/"catalog_fixture";base.mkdir()
   remote_source=actual_root/actual_asset["asset_remote_evidence_path"].replace(str(actual_root)+"/","")
   remote_copy=base/"remote_asset_evidence.json";remote_copy.write_bytes(remote_source.read_bytes())
   member=base/"member_record.json";write_json(member,{"fixture":"local member row"})
   csv1=base/"payloads.csv";csv1.write_text("source_path\\n")
   csv2=base/"cases.csv";csv2.write_text("task_key\\n")
   row.update({"task_key":key,"canonical_source_task_key":key,"source_kind":"canonical_validated_test_outcomes","asset_name":actual_asset["asset_name"],"asset_bytes":actual_asset["asset_bytes"],"asset_sha256":actual_asset["asset_sha256"],"asset_remote_verified":True,"asset_member_evidence_status":"exact_member_sha_size_crc_verified","member_record_evidence_path":str(member),"member_record_evidence_sha256":hashlib.sha256(member.read_bytes()).hexdigest()})
   row.pop("asset_remote_evidence_path",None);row.pop("asset_remote_evidence_sha256",None)
   asset={**actual_asset,"asset_remote_evidence_path":str(remote_copy),"asset_remote_evidence_sha256":hashlib.sha256(remote_copy.read_bytes()).hexdigest()}
   catalog={"schema":"lamost-terminal-result-retention-catalog/1","release":actual.get("release",{}),"assets":[asset],"payload_records":[row]}
   mp=base/"catalog.json";write_json(mp,catalog)
   receipt={"schema":"lamost-terminal-result-retention-catalog-receipt/1","catalog_path":str(mp),"catalog_sha256":hashlib.sha256(mp.read_bytes()).hexdigest(),"payloads_csv_path":str(csv1),"payloads_csv_sha256":hashlib.sha256(csv1.read_bytes()).hexdigest(),"cases_csv_path":str(csv2),"cases_csv_sha256":hashlib.sha256(csv2.read_bytes()).hexdigest()}
   write_json(base/"CATALOG_RECEIPT.json",receipt)
   db=root/"runtime_20261025/registry.sqlite";c=sqlite3.connect(db);c.execute("insert into tasks values(?,?)",(key,json.dumps(task)));c.commit();c.close()
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["validated_success_terminal_rows"],1)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],1)
   group=plan["complete_known_inode_group_review_only"]["groups"][0]
   self.assertEqual(set(group["native_paths"]),{row["source_path"],alias_rel})
   self.assertEqual(group["asset_remote_evidence_path"],asset["asset_remote_evidence_path"])
   self.assertTrue(group["asset_remote_evidence_inherited_from_asset_record"])
  finally:td.cleanup()
 def test_shared_asset_evidence_mismatch_or_fake_identity_is_blocked(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean");r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);doc=json.loads(mp.read_text())
   # A payload-level conflicting claim cannot override the authoritative asset record.
   row=doc["payload_records"][0];row["asset_remote_evidence_path"]="/tmp/fake-remote.json"
   write_json(mp,doc);receipt=mp.parent/"CATALOG_RECEIPT.json";rd=json.loads(receipt.read_text());rd["catalog_sha256"]=hashlib.sha256(mp.read_bytes()).hexdigest();write_json(receipt,rd)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["validated_success_terminal_rows"],0)
   self.assertEqual(plan["excluded_counts"]["published_asset_evidence_missing"],1)
   # Even a freshly hash-bound fake proof is rejected when it names another asset.
   doc=json.loads(mp.read_text());row=doc["payload_records"][0];row.pop("asset_remote_evidence_path",None)
   remote=Path(doc["assets"][0]["asset_remote_evidence_path"]);write_json(remote,{"schema":"lamost-remote-verified-release-asset-locator/1","asset_id":12345,"asset_name":"other.zip","bytes":100000,"sha256":"a"*64,"github_digest":"sha256:"+"a"*64,"repo":"S-G-mathematics/lamost-six-experiments","release_tag":"fixture","local_zip_crc_checked":True})
   digest=hashlib.sha256(remote.read_bytes()).hexdigest();doc["assets"][0]["asset_remote_evidence_sha256"]=digest
   row.pop("asset_remote_evidence_sha256",None)
   write_json(mp,doc);rd=json.loads(receipt.read_text());rd["catalog_sha256"]=hashlib.sha256(mp.read_bytes()).hexdigest();write_json(receipt,rd)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["validated_success_terminal_rows"],0)
   self.assertEqual(plan["excluded_counts"]["published_asset_evidence_missing"],1)
  finally:td.cleanup()
 def test_catalog_v1_exact_member_record_is_selected(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e6/rep_1/ensemble/equal/eval")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r])
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],1)
   self.assertEqual(plan["selected"][0]["asset"],"a.zip")
   self.assertEqual(plan["catalog_receipt_sha256"],hashlib.sha256((mp.parent/"CATALOG_RECEIPT.json").read_bytes()).hexdigest())
   self.assertIn("_physical_inode_inventory",plan)
  finally:td.cleanup()
 def test_catalog_crc_missing_and_alias_reuse_are_excluded(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e5/rep_1/eval/direct/rf/clean")
   rows=[]
   for status in ("remote_asset_verified_member_crc_missing","alias_reuses_source_payload"):
    rows.append({**r,"archive_member":r["archive_member"]+"."+status,"asset_member_evidence_status":status})
   mp,db=self.save_v2_catalog(root,b,[t],rows)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["published_member_evidence_missing"],2)
  finally:td.cleanup()
 def test_v2_physical_inventory_accepts_complete_attempt_hardlink_group(self):
  td,root,b=self.fixture()
  try:
   key="e4/rep_1/eval/direct/rf/A_half";t,r,p,data=self.add_eval(root,key)
   alias_rel=f"runtime_20261025/artifacts/{key}/attempts/attempt_001/test_outcomes.npz";alias=root/alias_rel;alias.parent.mkdir(parents=True);os.link(p,alias)
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["strict_single_link_eligible_count"],0)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],1)
   grp=plan["complete_known_inode_group_review_only"]["groups"][0]
   self.assertEqual(set(grp["native_paths"]),{r["source_path"],alias_rel})
   self.assertEqual(grp["link_count"],2);self.assertFalse(grp["retirement_enabled"])
   self.assertEqual(grp["aliases"],[alias_rel])
   self.assertEqual(grp["owner_task_keys"],[key])
  finally:td.cleanup()
 def test_v2_physical_inventory_rejects_unaccounted_external_link(self):
  td,root,b=self.fixture()
  try:
   key="e5/rep_1/eval/direct/rf/clean";t,r,p,data=self.add_eval(root,key)
   alias_rel=f"runtime_20261025/artifacts/{key}/attempts/attempt_001/test_outcomes.npz";alias=root/alias_rel;alias.parent.mkdir(parents=True);os.link(p,alias)
   outside=root/"runtime_20261025/unscanned/test_outcomes.npz";outside.parent.mkdir(parents=True);os.link(p,outside)
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["strict_single_link_eligible_count"],0)
   self.assertEqual(plan["complete_known_inode_group_review_only"]["count"],0)
   self.assertEqual(plan["excluded_counts"]["incomplete_inode_group"],1)
  finally:td.cleanup()
 def test_v2_catalog_receipt_mismatch_rejected(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e3/rep_1/eval/direct/rf/A_half")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);receipt=mp.parent/"CATALOG_RECEIPT.json";d=json.loads(receipt.read_text());d["catalog_sha256"]="0"*64;write_json(receipt,d)
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db)
  finally:td.cleanup()
 def test_catalog_restore_required_native_row_is_excluded(self):
  td,root,b=self.fixture()
  try:
   t,r,p,_=self.add_eval(root,"e4/rep_1/eval/direct/rf/clean")
   row={**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified","native_path_present":False,"retention_status":"restore_required","restore_required":True}
   p.unlink()
   mp,db=self.save_v2_catalog(root,b,[t],[row])
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["incomplete_inode_group"],1)
  finally:td.cleanup()

 def test_restored_native_path_overrides_stale_catalog_retired_flag(self):
  td,root,b=self.fixture()
  try:
   t,r,p,_=self.add_eval(root,"e4/rep_1/eval/direct/rf/clean")
   row={**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified","native_path_present":False,"retention_status":"restore_required","restore_required":True}
   mp,db=self.save_v2_catalog(root,b,[t],[row]);plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],1)
   selected=plan["selected"][0]
   self.assertTrue(selected["fresh_native_inventory_verified"])
   self.assertFalse(selected["catalog_native_path_present_at_snapshot"])
   self.assertTrue(selected["catalog_restore_required_at_snapshot"])
  finally:td.cleanup()

 def test_validated_terminal_consumer_reference_does_not_block_retirement_plan(self):
  td,root,b=self.fixture()
  try:
   key="e5/rep_1/eval/direct/rf/clean";t,r,_,_=self.add_eval(root,key)
   terminal={"key":"e6/rep_1/eval/ensemble/equal","experiment":6,"kind":"eval","status":"validated_terminal","dependencies":[key],"provenance":{"source_task_key":key}}
   mp,db=self.save_catalog(b,[t],[{**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified"}])
   c=sqlite3.connect(db);c.execute("insert into tasks values(?,?)",(terminal["key"],json.dumps(terminal)));c.commit();c.close()
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],1)
   self.assertEqual(plan["excluded_counts"].get("active_or_future_consumer",0),0)
  finally:td.cleanup()

 def test_unknown_status_consumer_reference_still_blocks_retirement_plan(self):
  td,root,b=self.fixture()
  try:
   key="e5/rep_1/eval/direct/rf/clean";t,r,_,_=self.add_eval(root,key)
   unknown={"key":"e6/rep_1/eval/ensemble/equal","experiment":6,"kind":"eval","dependencies":[],"inputs":{"test_outcomes":key}}
   mp,db=self.save_catalog(b,[t],[{**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified"}])
   c=sqlite3.connect(db);c.execute("insert into tasks values(?,?)",(unknown["key"],json.dumps(unknown)));c.commit();c.close()
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["active_or_future_consumer"],1)
  finally:td.cleanup()

 def test_malformed_nonowner_registry_record_blocks_retirement_plan(self):
  td,root,b=self.fixture()
  try:
   key="e5/rep_1/eval/direct/rf/clean";t,r,_,_=self.add_eval(root,key)
   mp,db=self.save_catalog(b,[t],[{**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified"}])
   c=sqlite3.connect(db);c.execute("insert into tasks values(?,?)",("unparseable-shape",json.dumps(["unknown registry record"])));c.commit();c.close()
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["active_or_future_consumer"],1)
  finally:td.cleanup()

 def test_pending_task_input_reference_blocks_terminal_outcome_retirement(self):
  td,root,b=self.fixture()
  try:
   key="e5/rep_1/eval/direct/rf/clean";t,r,_,_=self.add_eval(root,key)
   pending={"key":"e5/rep_2/fit/direct/rf/feature_noise_05","experiment":5,"kind":"fit","status":"waiting_for_dependency","dependencies":[],"train_key":key}
   mp,db=self.save_catalog(b,[t],[{**r,"asset_member_evidence_status":"exact_member_sha_size_crc_verified"}])
   c=sqlite3.connect(db);c.execute("insert into tasks values(?,?)",(pending["key"],json.dumps(pending)));c.commit();c.close()
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["selected_count"],0)
   self.assertEqual(plan["excluded_counts"]["active_or_future_consumer"],1)
  finally:td.cleanup()

 def test_cleanup_approval_requires_exact_profile_and_floor(self):
  good={"cleanup_profile":rr.CLEANUP_RETIRE_PROFILE,"cleanup_disk_floor_bytes":6*rr.GIB}
  self.assertTrue(rr.validate_cleanup_approval(good,rr.CLEANUP_RETIRE_PROFILE))
  for bad in ({},{"cleanup_profile":rr.CLEANUP_RETIRE_PROFILE,"cleanup_disk_floor_bytes":20*rr.GIB},{"cleanup_profile":"other","cleanup_disk_floor_bytes":6*rr.GIB}):
   with self.assertRaises(rr.RetentionError):rr.validate_cleanup_approval(bad,rr.CLEANUP_RETIRE_PROFILE)
  self.assertTrue(rr.validate_cleanup_approval({},rr.STANDARD_RETIRE_PROFILE))

 def test_cleanup_retirement_profile_is_explicit_and_standard_floor_stays_20gib(self):
  self.assertEqual(rr.retirement_profile_for(20*rr.GIB),rr.STANDARD_RETIRE_PROFILE)
  self.assertEqual(rr.retirement_profile_for(6*rr.GIB,rr.CLEANUP_RETIRE_PROFILE),rr.CLEANUP_RETIRE_PROFILE)
  for floor,profile in ((6*rr.GIB,None),(6*rr.GIB,rr.STANDARD_RETIRE_PROFILE),(5*rr.GIB,rr.CLEANUP_RETIRE_PROFILE),(10*rr.GIB,rr.CLEANUP_RETIRE_PROFILE)):
   with self.assertRaises(rr.RetentionError):rr.retirement_profile_for(floor,profile)

 def test_cleanup_capacity_reserves_full_restore_and_largest_asset(self):
  td,root,b=self.fixture()
  try:
   rel="runtime_20261025/artifacts/e5/rep_1/eval/direct/rf/clean/test_outcomes.npz"
   p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"x"*2048);st=p.stat()
   row={"source_path":rel,"source_bytes":2048,"native_dev":st.st_dev,"native_ino":st.st_ino,"asset":"asset-a"}
   assets={"asset-a":{"bytes":4096}}
   actual=rr.shutil.disk_usage(root);kind=type(actual)
   original=rr.shutil.disk_usage
   try:
    rr.shutil.disk_usage=lambda _:kind(100*rr.GIB,0,6*rr.GIB+2048+4096-st.st_blocks*512)
    proof=rr.cleanup_capacity(root,[row],assets,6*rr.GIB)
    self.assertEqual(proof["required_post_retirement_free_bytes"],6*rr.GIB+2048+4096)
    rr.shutil.disk_usage=lambda _:kind(100*rr.GIB,0,6*rr.GIB+2048+4096-st.st_blocks*512-1)
    with self.assertRaises(rr.RetentionError):rr.cleanup_capacity(root,[row],assets,6*rr.GIB)
   finally:rr.shutil.disk_usage=original
  finally:td.cleanup()

 def test_catalog_asset_rows_normalize_for_retirement_api(self):
  doc={"schema":"lamost-terminal-result-retention-catalog/1","assets":[{"asset_name":"release.zip","asset_bytes":42,"asset_sha256":"a"*64}]}
  asset=rr._asset_map(doc)["release.zip"]
  self.assertEqual((asset["name"],asset["bytes"],asset["sha256"]),("release.zip",42,"a"*64))

 def test_v2_requires_frozen_worker_and_science_source_pins(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e4/rep_1/eval/direct/rf/A_half")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r])
   self.assertEqual(rr.make_plan(root,mp,db)["selected_count"],1)
   worker=root/"runtime_20261025/source/worker.py";worker.write_text("# changed\n")
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db)
  finally:td.cleanup()

 def test_plan_output_separates_and_hashes_physical_inventory(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e3/rep_1/eval/direct/rf/A_half")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);plan=rr.make_plan(root,mp,db)
   output=root/"operations/retention_plan.json"
   saved=rr.write_plan_output(root,output,plan)
   doc=json.loads(output.read_text());inv=root/doc["physical_inode_inventory_path"]
   self.assertTrue(inv.is_file());self.assertEqual(rr.sha(inv),doc["physical_inode_inventory_file_sha256"])
   self.assertNotIn("_physical_inode_inventory",doc)
   self.assertEqual(doc["physical_inode_inventory_sha256"],saved["physical_inode_inventory_sha256"])
   with self.assertRaises(rr.RetentionError):rr.write_plan_output(root,root.parent/"escape.json",rr.make_plan(root,mp,db))
  finally:td.cleanup()

 def test_retirement_preflight_rechecks_published_member_evidence(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e6/rep_1/ensemble/equal/eval")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);plan=rr.make_plan(root,mp,db)
   m=json.loads(mp.read_text());rr._recheck_catalog_bindings(root,mp,plan,m)
   member=Path(plan["selected"][0]["member_record_evidence_path"]);member.write_text('{"changed":true}')
   with self.assertRaises(rr.RetentionError):rr._recheck_catalog_bindings(root,mp,plan,m)
  finally:td.cleanup()

 def test_v2_named_catalog_receipt_is_discovered_and_bound(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e4/rep_1/eval/direct/rf/A_half")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r])
   rp=mp.parent/"CATALOG_RECEIPT.json";alt=mp.parent/"CATALOG_V2_RECEIPT.json";rp.rename(alt)
   plan=rr.make_plan(root,mp,db)
   self.assertEqual(plan["catalog_receipt_path"],str(alt))
   rr._recheck_catalog_bindings(root,mp,plan,json.loads(mp.read_text()))
   duplicate=mp.parent/"ANOTHER_RECEIPT.json";duplicate.write_bytes(alt.read_bytes())
   with self.assertRaises(rr.RetentionError):rr.make_plan(root,mp,db)
  finally:td.cleanup()

 def test_retirement_preflight_rechecks_frozen_science_sources(self):
  td,root,b=self.fixture()
  try:
   t,r,_,_=self.add_eval(root,"e3/rep_1/eval/direct/rf/A_half")
   r["asset_member_evidence_status"]="exact_member_sha_size_crc_verified"
   mp,db=self.save_v2_catalog(root,b,[t],[r]);plan=rr.make_plan(root,mp,db);m=json.loads(mp.read_text())
   rr._recheck_catalog_bindings(root,mp,plan,m)
   (root/"runtime_20261025/source/science.py").write_text("# changed\n")
   with self.assertRaises(rr.RetentionError):rr._recheck_catalog_bindings(root,mp,plan,m)
  finally:td.cleanup()

 def test_actual_verified104_catalog_schema2_receipt_metadata_preflight(self):
  root=Path("/home/ubuntu/lamost_e1_migration_20261023")
  mp=root/"operations/terminal_result_retention_catalog_20261030/catalog_v2_verified104.json"
  expected="0465458a375384ca303d47afc868735db2879e189143c3e2966511590a129f48"
  receipt_sha="7a148c069a930674966968a22ca0d0c08876c6ca92e34bb96f58b7afd8de49be"
  self.assertTrue(mp.is_file());self.assertEqual(rr.sha(mp),expected)
  doc=json.loads(mp.read_text())
  rp,got,receipt=rr.validate_catalog_receipt(root,mp,doc,expected)
  self.assertEqual(rp.name,"CATALOG_V2_RECEIPT.json")
  self.assertEqual(got,receipt_sha)
  self.assertEqual(receipt["schema"],"lamost-terminal-result-retention-catalog-receipt/2")
  self.assertEqual(receipt["member_evidence_status_counts"],{"exact_member_sha_size_crc_verified":2322})

if __name__=="__main__":unittest.main()
