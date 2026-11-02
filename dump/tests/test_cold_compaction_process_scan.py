import tempfile
import unittest
from pathlib import Path
import cold_auto_compaction as driver

class ProcessScannerFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='busy_script_scan_')
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.runtime=base/'runtime';self.proc=base/'proc'
        (self.runtime/'source').mkdir(parents=True);self.proc.mkdir()
        for rel in ('source/run_batch.py','source/commit_batch_child.py','source/finalize_project.py','run_finalizer.sh'):
            p=self.runtime/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# fixture\n')
        self.finalizer=str(self.runtime/'source/finalize_project.py')
        self.runner=str(self.runtime/'run_finalizer.sh')

    def add_proc(self,pid,args):
        d=self.proc/str(pid);d.mkdir()
        (d/'cmdline').write_bytes(b'\0'.join(str(x).encode() for x in args)+b'\0')

    def scan(self):
        return driver.scan_busy_scripts(proc_root=self.proc,runtime_root=self.runtime)

    def test_bash_c_compound_text_ending_in_finalizer_path_is_ignored(self):
        self.add_proc(101,['/usr/bin/bash','-lc',f'rg --files {self.finalizer} | tail'])
        self.assertEqual(self.scan(),[])

    def test_rg_file_argument_is_ignored(self):
        self.add_proc(102,['/usr/bin/rg','-n',self.finalizer])
        self.assertEqual(self.scan(),[])

    def test_python_c_string_is_ignored(self):
        self.add_proc(103,['/opt/venv/bin/python','-c',f"print('{self.finalizer}')"])
        self.assertEqual(self.scan(),[])

    def test_python_u_direct_script_is_recognized(self):
        self.add_proc(104,['/opt/venv/bin/python','-u',self.finalizer,'--input',self.runner])
        self.add_proc(109,['/usr/bin/python3.12',str(self.runtime/'source'/'run_batch.py')])
        self.add_proc(110,['/usr/bin/python3',str(self.runtime/'source'/'commit_batch_child.py')])
        found=self.scan()
        self.assertEqual(sorted((pid,target) for pid,target,_ in found),[(104,'finalize_project.py'),(109,'run_batch.py'),(110,'commit_batch_child.py')])

    def test_bash_direct_finalizer_script_is_recognized(self):
        self.add_proc(105,['/bin/bash',self.runner])
        found=self.scan()
        self.assertEqual([(pid,target) for pid,target,_ in found],[(105,'run_finalizer.sh')])

    def test_option_and_data_arguments_are_not_scanned_as_scripts(self):
        self.add_proc(106,['/opt/venv/bin/python','/tmp/ordinary.py','--watch',self.finalizer])
        self.add_proc(107,['/bin/bash','-e','/tmp/ordinary.sh','--file',self.runner])
        self.assertEqual(self.scan(),[])

if __name__=='__main__':unittest.main(verbosity=2)
