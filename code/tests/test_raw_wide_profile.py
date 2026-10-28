import importlib.util, sys, types
from pathlib import Path
from unittest.mock import patch
STAGE=Path(__file__).resolve().parents[1]
SRC=STAGE / "source"
sys.path.insert(0,str(SRC))
def load(name):
 spec=importlib.util.spec_from_file_location("staged_"+name,SRC/(name+".py")); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def _actual_profile_configs_and_rejections():
 bp=load("batch_plan"); sys.modules["batch_plan"]=bp; run=load("run_batch"); child=load("commit_batch_child"); auto=load("cold_auto_compaction")
 for config in (run.resolve_batch_policy("storage-followup",None,"bounded-1800"), child.validate_storage_policy("storage-followup",None,"bounded-1800"), auto.batch_config(None,"bounded-1800")):
  assert config["max_bytes"]==2<<30 and config["max_groups"]==16 and config["wall_seconds"]==1800
 for config in (run.resolve_batch_policy("storage-followup",None,bp.RAW_WIDE_PROFILE), child.validate_storage_policy("storage-followup",None,bp.RAW_WIDE_PROFILE), auto.batch_config(None,bp.RAW_WIDE_PROFILE)):
  assert config["max_bytes"]==8<<30 and config["max_groups"]==64 and config["wall_seconds"]==1800 and config["transient_disk_reserve_bytes"]==6<<30
 assert auto.outer_wrapper_wall_seconds(bp.RAW_WIDE_PROFILE)==1860
 for f,args in ((run.resolve_batch_policy,("initial",None,bp.RAW_WIDE_PROFILE)),(run.resolve_batch_policy,("storage-followup-codec","reversible-xz-v1",bp.RAW_WIDE_PROFILE)),(child.validate_storage_policy,("initial",None,bp.RAW_WIDE_PROFILE)),(child.validate_storage_policy,("storage-followup-codec","reversible-xz-v1",bp.RAW_WIDE_PROFILE)),(auto.batch_config,("reversible-xz-v1",bp.RAW_WIDE_PROFILE))):
  try:f(*args)
  except ValueError:pass
  else:raise AssertionError("unsupported policy accepted")
 assert not run.transient_disk_headroom_ok((14<<30)-1,run.resolve_batch_policy("storage-followup",None,bp.RAW_WIDE_PROFILE))
 assert run.transient_disk_headroom_ok(14<<30,run.resolve_batch_policy("storage-followup",None,bp.RAW_WIDE_PROFILE))
 assert auto.wide_overlap_policy_allowed(bp.RAW_WIDE_PROFILE,{})
 assert not auto.wide_overlap_policy_allowed(bp.RAW_WIDE_PROFILE,{"archive_native_fit_overlap_sha256":"a"*64})
def _planner_selects_wide_metadata_caps_only():
 bp=load("batch_plan")
 rows=[{"bytes":3<<30,"inode_identity":[1,i]} for i in range(64)]
 rows.append({"bytes":9<<30,"inode_identity":[1,65]})
 assert len(bp.select_batch(rows,max_bytes=8<<30,max_groups=64))==2
 assert len(bp.select_batch(rows,max_bytes=2<<30,max_groups=16))==0
 assert len(bp.select_batch([{ "bytes":1,"inode_identity":[2,i]} for i in range(65)],max_bytes=8<<30,max_groups=64))==64

def test_actual_profile_configs_and_rejections():
 with patch.dict(sys.modules):
  _actual_profile_configs_and_rejections()

def test_planner_selects_wide_metadata_caps_only():
 with patch.dict(sys.modules):
  _planner_selects_wide_metadata_caps_only()
