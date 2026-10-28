import datetime,hashlib,importlib.util,json,os,pathlib,sys,tempfile,time,unittest
from unittest.mock import patch
import calibration_replay_supervisor as sup

class BeaconClockRaceTests(unittest.TestCase):
 def _run_fixture(self,*,future=False,supervisor=None):
  parent=supervisor or sup
  td=tempfile.TemporaryDirectory(prefix='cal_beacon_clock_');self.addCleanup(td.cleanup)
  root=pathlib.Path(td.name);runtime=root/'runtime';(runtime/'reports').mkdir(parents=True);sync=runtime/'sync';sync.mkdir()
  trigger=sync/'tree_walk_finished';started=sync/'running_beacon_written';ack=sync/'parent_read_beacon';release=sync/'parent_read_idle'
  script=root/'fake_clock_auditor.py'
  template=r'''import datetime,hashlib,json,os,sys,time
from pathlib import Path
runtime=Path(sys.argv[sys.argv.index('--runtime')+1]).resolve();nonce=sys.argv[sys.argv.index('--replay-run-nonce')+1]
ops=runtime/'logs'/'operational';ops.mkdir(parents=True,exist_ok=True)
sync=runtime/'sync';trigger=sync/'tree_walk_finished';started=sync/'running_beacon_written';ack=sync/'parent_read_beacon';release=sync/'parent_read_idle'
def wait(path):
 end=time.monotonic()+15
 while not path.exists():
  if time.monotonic()>end:raise RuntimeError('fixture handshake timed out: '+str(path.name))
  time.sleep(.001)
def atomic(path,obj):
 tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(obj,sort_keys=True));os.replace(tmp,path)
pid=os.getpid();st=Path('/proc')/str(pid)/'stat';stat=st.read_text();ticks=int(stat[stat.rfind(')')+1:].split()[19])
wait(trigger)
start=time.monotonic()+__FUTURE_OFFSET__
start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
beacon={'schema_version':'lamost-calibration-replay-private-beacon/1','run_nonce':nonce,'pid':pid,'process_start_ticks':ticks,'phase_process_monotonic':start,'state':'running','phase':'calibration_score_replay','phase_started_monotonic':start,'phase_started_utc':start_utc,'current_fit_key':'e3/rep_1/fit/gmm','current_task_key':'e3/rep_1/eval/direct/gmm','updated_utc':start_utc}
atomic(ops/'calibration_replay_supervisor_beacon.json',beacon)
(sync/'identity.json').write_text(json.dumps({'pid':pid,'ticks':ticks,'phase_start':start}))
started.write_text('ready')
wait(ack)
wait(release)
if __FUTURE__:
 raise SystemExit(0)
fit='e3/rep_1/fit/gmm';task='e3/rep_1/eval/direct/gmm';phase='clock-race-phase'
common={'schema_version':'lamost-calibration-replay-phase-ledger/1','run_nonce':nonce,'phase_id':phase,'mode':'replayed','phase':'calibration_score_replay','fit_key':fit,'task_keys':[task],'prior_receipts':{},'pid':pid,'process_start_ticks':ticks}
finish=time.monotonic()+.02;finish_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
ledger=ops/('calibration_replay_phase_ledger_'+nonce+'.jsonl')
events=[dict(common,event='start',monotonic=start,utc=start_utc),dict(common,event='finish',monotonic=finish,utc=finish_utc)]
with ledger.open('wb') as f:
 for e in events:f.write((json.dumps(e,sort_keys=True,separators=(',',':'))+'\n').encode())
 f.flush();os.fsync(f.fileno())
ledger_sha=hashlib.sha256(ledger.read_bytes()).hexdigest()
audit={'schema_version':'lamost-calibration-replay-audit/1','generated_utc':'clock-fixture','registry_snapshot_sha256':'b'*64,'replay_run_nonce':nonce,'phase_ledger_path':ledger.relative_to(runtime).as_posix(),'phase_ledger_sha256':ledger_sha,'accepted_prior_receipts_index_sha256':None,'records':[{'task_key':task,'fit_key':fit,'status':'validated','supervision_mode':'replayed','identity':'a'*64,'metadata_sha256':'b'*64,'nonconformity_file_sha256':'c'*64}]}
(runtime/'reports'/'CALIBRATION_REPLAY_AUDIT.json').write_text(json.dumps(audit,sort_keys=True)+'\n')
atomic(ops/'calibration_replay_supervisor_beacon.json',dict(beacon,state='idle',phase='idle',phase_started_monotonic=None,current_fit_key=None,current_task_key=None))
wait(release)
'''
  script.write_text(template.replace('__FUTURE_OFFSET__','5.0' if future else '0.0').replace('__FUTURE__','True' if future else 'False'))
  real_tree=parent.tree_rss;real_load=parent.load;first={'value':True};tree_calls={'value':0};walk_sample={'value':None}
  beacon=runtime/'logs'/'operational'/'calibration_replay_supervisor_beacon.json'
  def wait_for(path):
   end=time.monotonic()+10
   while not path.exists():
    if time.monotonic()>end:raise AssertionError('handshake missing '+path.name)
    time.sleep(.001)
  def tree_rss_after_walk(pid):
   value=real_tree(pid);tree_calls['value']+=1
   if first['value']:
    first['value']=False;walk_sample['value']=time.monotonic();trigger.write_text('done');wait_for(started)
   elif tree_calls['value']==2 and not release.exists():
    release.write_text('second parent sample')
   return value
  def parent_read(path):
   obj=real_load(path)
   try:same=pathlib.Path(path).resolve()==beacon.resolve()
   except Exception:same=False
   if same and isinstance(obj,dict) and obj.get('run_nonce'):
    if obj.get('state')=='running' and not ack.exists():ack.write_text('read')
    elif obj.get('state')=='idle' and not release.exists():release.write_text('read')
   return obj
  nonce='deterministic-clock-race-0123456789'
  with patch.object(parent,'tree_rss',side_effect=tree_rss_after_walk),patch.object(parent,'load',side_effect=parent_read):
   try:receipt=parent.run(runtime,pathlib.Path(sys.executable),script,run_nonce=nonce)
   except Exception as exc:return {'error':exc,'runtime':runtime,'identity':json.loads((sync/'identity.json').read_text()),'walk_sample':walk_sample['value']}
  return {'receipt':receipt,'runtime':runtime,'identity':json.loads((sync/'identity.json').read_text()),'walk_sample':walk_sample['value']}

 def test_phase_started_after_pre_walk_now_is_accepted_and_old_source_failure_is_proven(self):
  result=self._run_fixture()
  self.assertNotIn('error',result,repr(result.get('error')))
  self.assertGreater(result['identity']['phase_start'],result['walk_sample'])
  self.assertEqual(result['receipt']['status'],'complete')
  self.assertTrue(result['receipt']['phase_records'][0]['process_identity_verified'])
  old_path=pathlib.Path(__file__).resolve().parent/'fixtures'/'calibration_replay_supervisor_pre_fix.py'
  spec=importlib.util.spec_from_file_location('calibration_replay_supervisor_pre_fix',old_path)
  old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
  counterfactual=self._run_fixture(supervisor=old)
  self.assertIn('error',counterfactual)
  self.assertGreater(counterfactual['identity']['phase_start'],counterfactual['walk_sample'])
  self.assertIn('audit report is not fresh for supervised run nonce',str(counterfactual['error']))

 def test_true_future_beacon_is_rejected_child_stopped_and_reason_retained(self):
  result=self._run_fixture(future=True)
  self.assertIn('error',result)
  message=str(result['error'])
  self.assertIn('invalid running phase beacon',message)
  self.assertIn('no qualified calibration replay report; no checks skipped',message)
  ident=result['identity'];proc=sup.proc(ident['pid'])
  self.assertFalse(proc and proc['ticks']==ident['ticks'],'verified child should be stopped after true future beacon')

if __name__=='__main__':unittest.main(verbosity=2)
