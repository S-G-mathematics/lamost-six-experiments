import hashlib
import json
import tempfile
import tracemalloc
import unittest
from pathlib import Path

import batch_plan
import cold_auto_compaction as auto
import commit_batch_child as child
import run_batch

PROFILE = "bounded-1800-mixedsmall4gib2048"
GIB = 1 << 30


def synthetic_items(count, each_bytes=16 << 20):
    return [{"producer_task":f"e4/rep_1/fit/direct/hist_gb/model_{i}","method":"hist_gb",
             "source_relpath":f"runtime_20261025/artifacts/e4/rep_1/fit/direct/hist_gb/model_{i}/pipeline.joblib",
             "aliases":[f"runtime_20261025/artifacts/e4/rep_1/fit/direct/hist_gb/model_{i}/{suffix}/pipeline.joblib" for suffix in ("canonical","attempts/a","checkpoints/t")],
             "consumer_tasks":[f"e4/rep_1/eval/direct/hist_gb/model_{i}"],"source_sha256":"a"*64,
             "alias_owners":[{"alias_path":f"runtime_20261025/artifacts/e4/rep_1/fit/direct/hist_gb/model_{i}/{suffix}/pipeline.joblib",
                 "task_key":f"e4/rep_1/fit/direct/hist_gb/model_{i}","task_sha256":"b"*64,
                 "consumer_tasks":[f"e4/rep_1/eval/direct/hist_gb/model_{i}"],"owner_kind":"attempt_publication",
                 "publication_sha256":"c"*64,"attempt_publication_sha256":"d"*64,"fit_result_sha256":"e"*64,
                 "selection_sha256":"f"*64} for suffix in ("canonical","attempts/a","checkpoints/t")],
             "bytes":each_bytes,"inode_identity":[1,i]} for i in range(count)]


class MixedSmallProfileTests(unittest.TestCase):
    def test_profile_config_agrees_in_planner_child_driver_wrapper(self):
        self.assertEqual(PROFILE,batch_plan.RAW_MIXED_SMALL_PROFILE)
        self.assertEqual(PROFILE,child.RAW_MIXED_SMALL_PROFILE)
        self.assertIn(PROFILE,run_batch.ARCHIVE_IO_PROFILES)
        self.assertIn(PROFILE,auto.ARCHIVE_IO_PROFILES)
        policies=[run_batch.resolve_batch_policy("storage-followup",None,PROFILE),
                  child.validate_storage_policy("storage-followup",None,PROFILE),
                  auto.batch_config(None,PROFILE)]
        for p in policies:
            self.assertEqual(p["max_bytes"],4*GIB)
            self.assertEqual(p["max_groups"],2048)
            self.assertEqual(p["wall_seconds"],1800)
            self.assertEqual(p["transient_disk_reserve_bytes"],6*GIB)
            self.assertIsNone(p["storage_codec_policy"])
        self.assertEqual(run_batch.resolve_batch_policy("storage-followup",None,batch_plan.RAW_WIDE_PROFILE)["max_groups"],64)
        self.assertEqual(run_batch.resolve_batch_policy("storage-followup",None,batch_plan.RAW_WIDE_PROFILE)["max_bytes"],8*GIB)
        self.assertEqual(run_batch.resolve_batch_policy("storage-followup",None)["max_groups"],16)
        with self.assertRaises(ValueError):run_batch.resolve_batch_policy("storage-followup-codec","reversible-xz-v1",PROFILE)
        with self.assertRaises(ValueError):child.validate_storage_policy("storage-followup-codec","reversible-xz-v1",PROFILE)
        self.assertEqual(auto.outer_wrapper_wall_seconds(PROFILE),1860)
        self.assertEqual(run_batch.CHILD_ADDRESS_SPACE_BYTES,896<<20)
        self.assertEqual(run_batch.CHILD_AGGREGATE_RSS_BYTES,1<<30)
        self.assertEqual(run_batch.archive_io_profile_args(PROFILE),["--archive-io-profile",PROFILE])
        self.assertEqual(auto.archive_io_profile_args(PROFILE),["--archive-io-profile",PROFILE])
        self.assertTrue(run_batch.transient_disk_headroom_ok(10*GIB,policies[0]))
        self.assertFalse(run_batch.transient_disk_headroom_ok((10*GIB)-1,policies[0]))

    def test_wrapper_keeps_profile_fit_overlap_fail_closed(self):
        self.assertTrue(auto.wide_overlap_policy_allowed(PROFILE,{}))
        self.assertFalse(auto.wide_overlap_policy_allowed(PROFILE,{"archive_native_fit_overlap_sha256":"a"*64}))
        self.assertFalse(auto.wide_overlap_policy_allowed(PROFILE,{"archive_native_fit_overlap_qualification_sha256":"b"*64}))

    def test_2048_group_planner_cap_and_four_gib_byte_bound(self):
        rows=synthetic_items(2048,2<<20)
        selected=batch_plan.select_batch(rows,max_bytes=4*GIB,max_groups=2048)
        self.assertEqual(len(selected),2048)
        self.assertEqual(sum(x["bytes"] for x in selected),4*GIB)
        self.assertEqual(len({tuple(x["inode_identity"]) for x in selected}),2048)
        smaller=batch_plan.select_batch(rows,max_bytes=(4*GIB)-1,max_groups=2048)
        self.assertLessEqual(sum(x["bytes"] for x in smaller),4*GIB-1)
        self.assertLessEqual(len(smaller),2048)

    def test_2048_group_three_alias_metadata_journal_stays_bounded(self):
        rows=synthetic_items(2048,1<<20)
        journal={"schema_version":"fixture/1","state":"prepared","archive_sha256_before":"b"*64,
                 "central_directory_offset":123456789,"required_task_keys":[],"items":rows}
        for row in rows:
            journal["required_task_keys"].append(row["producer_task"]);journal["required_task_keys"].extend(row["consumer_tasks"])
        tracemalloc.start()
        encoded=json.dumps(journal,sort_keys=True,separators=(",",":" )).encode()
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"journal.json";path.write_bytes(encoded)
            self.assertEqual(path.stat().st_size,len(encoded))
        self.assertEqual(sum(len(x["aliases"]) for x in rows),2048*3)
        self.assertLess(len(encoded),16<<20)
        self.assertLess(peak,256<<20)

    def test_policy_binds_measured_inventory_and_2048_fixture_evidence(self):
        evidence=json.loads((Path(__file__).resolve().parent/"fixtures/archive_io/RAW_MIXED_SMALL_PROFILE_2048_EVIDENCE.json").read_text())
        measurement=json.loads((Path(__file__).resolve().parent/"fixtures/archive_io/metadata_inode_walk_benchmark.json").read_text())
        self.assertEqual(evidence["profile"],PROFILE)
        policy=evidence["policy"]
        self.assertEqual(policy["max_bytes"],4*GIB)
        self.assertEqual(policy["max_groups"],2048)
        self.assertEqual(policy["child_wall_seconds"],1800)
        self.assertEqual(policy["wrapper_wall_seconds"],1860)
        self.assertEqual(policy["transient_disk_reserve_bytes"],6*GIB)
        self.assertTrue(policy["reject_declared_fit_overlap"])
        walk=evidence["metadata_walk"]
        self.assertEqual(walk["measurement_source_sha256"],hashlib.sha256((Path(__file__).resolve().parent/"fixtures/archive_io/metadata_inode_walk_benchmark.json").read_bytes()).hexdigest())
        self.assertEqual(measurement["inventory_entries"],walk["inventory_entries"])
        self.assertEqual(measurement["inventory_dirs"],walk["inventory_dirs"])
        self.assertAlmostEqual(measurement["mean_wall_seconds"],walk["mean_wall_seconds"])
        self.assertTrue(walk["shared_single_inventory_walk_per_batch"])
        fixture=evidence["bounded_fixture"]
        self.assertEqual(fixture["groups"],2048)
        self.assertEqual(fixture["aliases_per_group"],3)
        self.assertEqual(fixture["max_encoded_journal_bytes"],16<<20)
        self.assertEqual(fixture["max_traced_memory_bytes"],256<<20)
        self.assertEqual(fixture["fixture_member"],"runtime_20261025/tests/test_batch_inode_inventory_fixture.py")
        self.assertEqual(batch_plan.RAW_MIXED_SMALL_MAX_GROUPS,2048)

    def test_actual_cli_accepts_profile_as_archive_only_option(self):
        import subprocess,sys
        command=[sys.executable,str(Path(run_batch.__file__)),"--archive-io-profile",PROFILE,"--help"]
        result=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(PROFILE,result.stdout)
        self.assertIn("archive-io-profile",result.stdout)

if __name__=="__main__":unittest.main()
