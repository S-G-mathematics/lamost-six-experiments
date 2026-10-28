from pathlib import Path
import importlib.util,sys,unittest

HERE=Path(__file__).resolve().parent
if HERE.parent.parent.name=='staging':
    STAGE=HERE.parent; R=STAGE.parents[1]
else:
    R=HERE.parent; STAGE=R

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

sys.path.insert(0,str(R/'source'))
child=load('io_profile_child',STAGE/'source/commit_batch_child.py')
wrapper=load('io_profile_run_batch',STAGE/'source/run_batch.py')
driver=load('io_profile_auto',STAGE/'source/cold_auto_compaction.py')

class StorageArchiveIOProfileTests(unittest.TestCase):
    def test_legacy_child_and_driver_profiles_remain_unchanged(self):
        self.assertEqual(child.validate_storage_policy('initial',None)['wall_seconds'],180)
        self.assertEqual(child.validate_storage_policy('storage-followup',None)['wall_seconds'],600)
        self.assertEqual(child.validate_storage_policy('storage-followup-codec','reversible-xz-v1')['wall_seconds'],600)
        self.assertEqual(driver.batch_config(None)['wall_seconds'],600)
        self.assertEqual(driver.batch_config('reversible-xz-v1')['wall_seconds'],600)
        self.assertEqual(wrapper.resolve_batch_policy('storage-followup',None)['wall_seconds'],600)
        self.assertEqual(wrapper.resolve_batch_policy('storage-followup-codec','reversible-xz-v1')['wall_seconds'],600)

    def test_bounded_profile_is_raw_followup_only_and_exactly_1800(self):
        cp=child.validate_storage_policy('storage-followup',None,'bounded-1800')
        wp=wrapper.resolve_batch_policy('storage-followup',None,'bounded-1800')
        dp=driver.batch_config(None,'bounded-1800')
        self.assertEqual(cp['wall_seconds'],1800);self.assertEqual(wp['wall_seconds'],1800);self.assertEqual(dp['wall_seconds'],1800)
        self.assertEqual(wp['max_bytes'],wrapper.MAX_LATER_BYTES);self.assertEqual(wp['max_groups'],wrapper.MAX_LATER_GROUPS)
        self.assertIsNone(wp['storage_codec_policy']);self.assertEqual(wp['archive_io_profile'],'bounded-1800')
        self.assertEqual(driver.outer_wrapper_wall_seconds('bounded-1800'),1860)
        self.assertEqual(driver.outer_wrapper_wall_seconds(None),driver.MAX_WRAPPER_WALL)

    def test_profile_cannot_be_used_for_initial_codec_or_unknown_policy(self):
        bad=[lambda:child.validate_storage_policy('initial',None,'bounded-1800'),
             lambda:child.validate_storage_policy('storage-followup-codec','reversible-xz-v1','bounded-1800'),
             lambda:child.validate_storage_policy('storage-followup',None,'other'),
             lambda:wrapper.resolve_batch_policy('initial',None,'bounded-1800'),
             lambda:wrapper.resolve_batch_policy('storage-followup-codec','reversible-xz-v1','bounded-1800'),
             lambda:driver.batch_config('reversible-xz-v1','bounded-1800'),
             lambda:driver.batch_config(None,'other')]
        for call in bad:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):call()

    def test_profile_flag_propagates_driver_to_wrapper_to_child(self):
        wrapper_argv=['python','/runtime/source/run_batch.py','--batch-policy','storage-followup']
        wrapper_argv.extend(driver.codec_policy_args(None));wrapper_argv.extend(driver.archive_io_profile_args('bounded-1800'))
        self.assertIn('--archive-io-profile',wrapper_argv);self.assertEqual(wrapper_argv[wrapper_argv.index('--archive-io-profile')+1],'bounded-1800')
        child_argv=['python','/runtime/source/commit_batch_child.py','--batch-policy','storage-followup']
        child_argv.extend(wrapper.codec_policy_args(None));child_argv.extend(wrapper.archive_io_profile_args('bounded-1800'))
        self.assertIn('--archive-io-profile',child_argv);self.assertEqual(child_argv[child_argv.index('--archive-io-profile')+1],'bounded-1800')
        self.assertEqual(driver.archive_io_profile_args(None),[]);self.assertEqual(wrapper.archive_io_profile_args(None),[])

    def test_scientific_and_memory_limits_are_unchanged(self):
        self.assertEqual(wrapper.CHILD_WALL_SECONDS,180)
        self.assertEqual(wrapper.FOLLOWUP_CHILD_WALL_SECONDS,600)
        self.assertEqual(wrapper.CHILD_AGGREGATE_RSS_BYTES,1<<30)
        self.assertEqual(wrapper.CHILD_ADDRESS_SPACE_BYTES,896<<20)
        self.assertEqual(driver.MAX_BATCH_WALL,600);self.assertEqual(driver.WRAPPER_RSS_LIMIT,1536*1024**2)
        self.assertEqual(driver.WRAPPER_AS_LIMIT,1536*1024**2)

if __name__=='__main__':unittest.main(verbosity=2)
