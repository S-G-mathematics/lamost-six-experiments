import hashlib,json,pathlib,subprocess,sys,tempfile,unittest
import calibration_replay as cr
import calibration_replay_supervisor as sup
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parents[1]
VENV=pathlib.Path(sys.executable)

class CalibrationReplaySupervisorTests(unittest.TestCase):
 def test_supervised_short_phase_uses_private_ledger_and_exact_parent_identity(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);runtime=root/'runtime_20261025';(runtime/'reports').mkdir(parents=True)
   script=root/'fake_auditor.py'
   script.write_text(r'''
import hashlib,json,os,sys,time,datetime
from pathlib import Path
runtime=Path(sys.argv[sys.argv.index("--runtime")+1]).resolve()
nonce=sys.argv[sys.argv.index("--replay-run-nonce")+1]
pid=os.getpid()
st=Path(f"/proc/{pid}/stat").read_text();ticks=int(st[st.rfind(")")+1:].split()[19])
ops=runtime/"logs"/"operational";ops.mkdir(parents=True,exist_ok=True)
ledger=ops/f"calibration_replay_phase_ledger_{nonce}.jsonl"
phase_id="tiny-phase";fit="e3/rep_1/fit/gmm";task="e3/rep_1/eval/direct/gmm"
start=time.monotonic();utc0=datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(p,obj):
 t=p.with_name(p.name+".tmp");t.write_text(json.dumps(obj,sort_keys=True));os.replace(t,p)
beacon={"schema_version":"lamost-calibration-replay-private-beacon/1","run_nonce":nonce,"pid":pid,"process_start_ticks":ticks,
 "phase_process_monotonic":time.monotonic(),"state":"running","phase":"calibration_score_replay","phase_started_monotonic":start,
 "phase_started_utc":utc0,"current_fit_key":fit,"current_task_key":task,"updated_utc":utc0}
atomic(ops/"calibration_replay_supervisor_beacon.json",beacon)
common={"schema_version":"lamost-calibration-replay-phase-ledger/1","run_nonce":nonce,"phase_id":phase_id,"mode":"replayed",
 "phase":"calibration_score_replay","fit_key":fit,"task_keys":[task],"prior_receipts":{},"pid":pid,"process_start_ticks":ticks}
events=[]
for ev,mono,utc in (("start",start,utc0),("finish",time.monotonic()+.02,datetime.datetime.now(datetime.timezone.utc).isoformat())):
 events.append(dict(common,event=ev,monotonic=mono,utc=utc))
with ledger.open("wb") as f:
 for e in events:f.write((json.dumps(e,sort_keys=True,separators=(",",":"))+"\n").encode())
 f.flush();os.fsync(f.fileno())
time.sleep(.02)
atomic(ops/"calibration_replay_supervisor_beacon.json",dict(beacon,state="idle",phase="idle",phase_started_monotonic=None,current_fit_key=None,current_task_key=None))
ledger_bytes=ledger.read_bytes();ledger_sha=hashlib.sha256(ledger_bytes).hexdigest()
audit={"schema_version":"lamost-calibration-replay-audit/1","generated_utc":"fixture","registry_snapshot_sha256":"b"*64,
 "replay_run_nonce":nonce,"phase_ledger_path":ledger.relative_to(runtime).as_posix(),"phase_ledger_sha256":ledger_sha,
 "accepted_prior_receipts_index_sha256":None,"q_replay_coverage_complete":True,"independent_q_recomputed":True,
 "complete":False,"complete_requires_external_supervision_receipt":True,"records":[{"task_key":task,"fit_key":fit,"status":"validated",
 "supervision_mode":"replayed","identity":"a"*64,"metadata_sha256":"b"*64,"nonconformity_file_sha256":"c"*64}]}
reports=runtime/"reports";(reports/"CALIBRATION_REPLAY_AUDIT.json").write_text(json.dumps(audit,sort_keys=True)+"\n")
''')
   nonce='fixture-parent-run-0123456789'
   receipt=sup.run(runtime,VENV,script,run_nonce=nonce)
   audit=json.loads((runtime/'reports'/'CALIBRATION_REPLAY_AUDIT.json').read_text())
   ledger=(runtime/audit['phase_ledger_path']).read_bytes()
   verified=cr.verify_supervision_receipt(audit,receipt,receipt['audit_sha256'],phase_ledger=ledger)
   self.assertTrue(verified['valid'],verified['reasons']);self.assertTrue(verified['qualified_complete'])
   self.assertEqual(receipt['phase_records'][0]['fit_key'],'e3/rep_1/fit/gmm')
   self.assertEqual(receipt['phase_records'][0]['peak_process_tree_rss_bytes'],receipt['process_tree_peak_rss_bytes'])

 def test_process_exit_between_poll_and_identity_check_is_normal_completion(self):
  class Child:
   def __init__(self,values):self.values=iter(values)
   def poll(self):return next(self.values)
  args=(123,456,1000,pathlib.Path("/tmp/runtime"),pathlib.Path("/tmp/auditor.py"),VENV)
  # The loop-entry poll sees a running child; it exits before /proc identity is read.
  child=Child([None,0])
  with patch.object(sup,"identity",return_value=False):
   self.assertEqual(child.poll(),None)
   self.assertEqual(sup.process_identity_state(child,*args),"exited")
  # A missing identity while the exact child is still alive remains a hard failure.
  child=Child([None,None])
  with patch.object(sup,"identity",return_value=False):
   self.assertEqual(child.poll(),None)
   self.assertEqual(sup.process_identity_state(child,*args),"invalid")

 def test_venv_executable_path_preserves_environment_imports(self):
  if not VENV.is_file():self.skipTest('established EC2 venv interpreter missing')
  probe=subprocess.run([str(VENV),'-c','import sys,numpy;print(sys.prefix);print(numpy.__file__)'],capture_output=True,text=True,check=True,timeout=10)
  lines=probe.stdout.strip().splitlines()
  prefix=pathlib.Path(lines[0]).resolve()
  numpy_path=pathlib.Path(lines[1]).resolve()
  self.assertEqual(prefix,pathlib.Path(sys.prefix).resolve())
  self.assertTrue(numpy_path.is_relative_to(prefix),f'numpy imported outside active venv: {numpy_path}')

if __name__=='__main__':unittest.main(verbosity=2)

