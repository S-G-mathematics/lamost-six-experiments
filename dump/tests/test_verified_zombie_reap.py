import hashlib, importlib.util, json, pathlib, tempfile, unittest
MODULE=pathlib.Path(__file__).resolve().parents[1]/'source/archive_fit_admission.py'
sp=importlib.util.spec_from_file_location('admission_test',MODULE); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
def statline(state='Z',ppid=41,ticks='123456'):
    return '77 (worker.py) '+' '.join([state,str(ppid),'77']+['0']*16+[ticks])
class ReapTests(unittest.TestCase):
    def proc(self,state='Z',ppid=41,ticks='123456',uid=1000):
        t=tempfile.TemporaryDirectory(); root=pathlib.Path(t.name); p=root/'77';p.mkdir()
        (p/'stat').write_text(statline(state,ppid,ticks));(p/'status').write_text('Name:\tpython\nUid:\t%d\t%d\t%d\t%d\n'%(uid,uid,uid,uid))
        (p/'cmdline').write_bytes(b'python3\0worker.py\0');(p/'cwd').symlink_to(root/'runtime',target_is_directory=True)
        (root/'runtime').mkdir()
        return t,root
    def test_exact_owned_zombie_uses_nonblocking_waitpid_only(self):
        t,r=self.proc(); calls=[]
        try:
            self.assertTrue(m.reap_zombie_child(77,'123456',41,proc_root=r,waitpid=lambda p,f:(calls.append((p,f)) or (p,0))))
            self.assertEqual(calls,[(77,1)])
        finally:t.cleanup()
    def test_live_foreign_parent_or_reused_pid_is_never_waited(self):
        for state,ppid,ticks in [('S',41,'123456'),('Z',42,'123456'),('Z',41,'999999')]:
            t,r=self.proc(state,ppid,ticks);calls=[]
            try:
                self.assertFalse(m.reap_zombie_child(77,'123456',41,proc_root=r,waitpid=lambda p,f:calls.append(p)))
                self.assertEqual(calls,[])
            finally:t.cleanup()
    def test_adopted_or_nonblocking_wait_is_not_claimed_reaped(self):
        t,r=self.proc()
        try:
            self.assertFalse(m.reap_zombie_child(77,'123456',41,proc_root=r,waitpid=lambda p,f:(0,0)))
            self.assertFalse(m.reap_zombie_child(77,'123456',41,proc_root=r,waitpid=lambda p,f:(_ for _ in ()).throw(ChildProcessError())))
        finally:t.cleanup()
    def _record(self,r,status='validated_terminal',ppid=41,ticks='123456'):
        runtime=r/'runtime'; req=runtime/'requests/a.json'; req.parent.mkdir(parents=True)
        (runtime/'requests').mkdir(exist_ok=True)
        req.write_text(json.dumps({'attempt_id':'attempt-1','task':{'key':'e4/rep_1/eval/direct/rf'}}))
        task={'key':'e4/rep_1/eval/direct/rf','status':status,'pid':77,'process_start_ticks':ticks,
              'request_path':str(req),'result_path':str(runtime/'results/a.json'),
              'attempts':[{'attempt_id':'attempt-1','request_path':str(req),'result_path':str(runtime/'results/a.json')}]}
        # Caller chooses fake proc PPID/ticks when constructing fixture.
        return task
    def test_terminal_recorded_worker_zombie_is_still_reaped(self):
        t,r=self.proc();calls=[]
        try:
            task=self._record(r)
            result=m.reap_recorded_zombies({task['key']:task},r/'runtime',41,proc_root=r,uid=1000,waitpid=lambda p,f:(calls.append((p,f)) or (p,0)))
            self.assertEqual(result,[{'key':task['key'],'attempt_id':'attempt-1','pid':77}])
            self.assertEqual(calls,[(77,1)])
        finally:t.cleanup()
    def test_terminal_recorded_zombie_reaps_without_cwd_or_cmdline(self):
        t,r=self.proc();calls=[]
        try:
            task=self._record(r)
            (r/'77'/'cwd').unlink(); (r/'77'/'cmdline').unlink()
            result=m.reap_recorded_zombies({task['key']:task},r/'runtime',41,proc_root=r,uid=1000,waitpid=lambda p,f:(calls.append((p,f)) or (p,0)))
            self.assertEqual(result,[{'key':task['key'],'attempt_id':'attempt-1','pid':77}])
            self.assertEqual(calls,[(77,1)])
        finally:t.cleanup()
    def test_active_process_identity_still_requires_cwd_and_cmdline(self):
        t,r=self.proc(state='S');
        try:
            (r/'77'/'cwd').unlink(); (r/'77'/'cmdline').unlink()
            with self.assertRaises(FileNotFoundError):m._proc_record(77,r)
        finally:t.cleanup()

    def test_terminal_record_wrong_process_identity_is_untouched(self):
        t,r=self.proc(state='Z',ppid=88);calls=[]
        try:
            task=self._record(r)
            result=m.reap_recorded_zombies({task['key']:task},r/'runtime',41,proc_root=r,uid=1000,waitpid=lambda p,f:calls.append(p))
            self.assertEqual(result,[]);self.assertEqual(calls,[])
        finally:t.cleanup()

    def test_reaper_disabled_for_legacy_freeze_without_binding(self):
        self.assertFalse(m.worker_reaper_enabled({'source_sha256':{}},'a'*64))

    def test_malformed_or_wrong_binding_fails_closed(self):
        for freeze, digest in [({'worker_reaper_source_sha256':'bad'},'a'*64),
                               ({'worker_reaper_source_sha256':'a'*64,'source_sha256':{}},'a'*64),
                               ({'worker_reaper_source_sha256':'a'*64,'source_sha256':{'archive_fit_admission.py':'a'*64}},'b'*64)]:
            with self.subTest(freeze=freeze):
                with self.assertRaises(ValueError):m.worker_reaper_enabled(freeze,digest)

    def test_matching_separate_freeze_binding_enables_reaper(self):
        digest='a'*64
        self.assertTrue(m.worker_reaper_enabled({'worker_reaper_source_sha256':digest,
            'source_sha256':{'archive_fit_admission.py':digest}},digest))

    def test_candidate_freeze_reaper_binding_matches_current_helper(self):
        digest=hashlib.sha256(MODULE.read_bytes()).hexdigest()
        freeze_path=MODULE.parents[1]/'manifests'/'freeze.json'
        frozen=json.loads(freeze_path.read_text())
        self.assertTrue(m.worker_reaper_enabled(frozen,digest))

if __name__=='__main__':unittest.main()
