import importlib.util,pathlib,tempfile,json,subprocess,sys,time,os,pytest
SRC=pathlib.Path(__file__).resolve().parents[1]/'source'
def module(name):
 s=importlib.util.spec_from_file_location(name,SRC/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_lock_and_identity(tmp_path):
 c=module('controller');c.R=tmp_path
 lock=c.lock_project()
 with pytest.raises(SystemExit):c.lock_project()
 script=tmp_path/'worker.py';script.write_text('import time; time.sleep(20)\n')
 p=subprocess.Popen([sys.executable,str(script)],start_new_session=True)
 try:
  ticks=c.start_ticks(p.pid);assert c.alive(p.pid,ticks)
  assert not c.alive(p.pid,str(int(ticks)+1))
  assert c.terminate_verified(p.pid,ticks);p.wait(timeout=5)
 finally:
  if p.poll() is None:os.killpg(p.pid,9)
def test_dependency_failure_and_bounded_recovery(tmp_path):
 c=module('controller');c.R=tmp_path;(tmp_path/'artifacts').mkdir();db=c.connect()
 a={'key':'a','experiment':3,'kind':'fit','dependencies':[],'status':'validated_terminal','outcome':'scientific_failure','scientific_case':False}
 b={'key':'b','experiment':3,'kind':'eval','dependencies':['a'],'status':'planned','outcome':None,'scientific_case':True}
 for t in [a,b]:c.put(db,t)
 assert c.ready_tasks(db,{'a':a,'b':b})==[]
 assert b['status']=='validated_terminal' and b['outcome']=='unavailable_dependency'
 d={'key':'d','experiment':3,'kind':'fit','status':'running','outcome':None,'attempts':[]}
 checkpoint=tmp_path/'artifacts/d/keep.txt';checkpoint.parent.mkdir();checkpoint.write_text('retained')
 for n in range(3):c.recover(db,d,'verified process absent')
 assert d['status']=='operationally_interrupted' and d['operational_recoveries']==2
 assert checkpoint.read_text()=='retained'
def test_eval_artifact_validation(tmp_path):
 import numpy as np
 w=module('worker');w.R=tmp_path;(tmp_path/'cache').mkdir()
 y=np.repeat(np.arange(7),3);ids=np.arange(len(y));X=np.zeros((len(y),6))
 np.savez_compressed(tmp_path/'cache/test.npz',X=X,y=y,ids=ids)
 out=tmp_path/'artifacts/check';out.mkdir(parents=True)
 masks=(1<<y).astype(np.uint8)
 np.savez_compressed(out/'test_outcomes.npz',sample_id=ids,y_pred=y,set_mask=masks,covered=np.ones(len(y),bool),set_size=np.ones(len(y),int))
 task={'key':'check','experiment':3,'rep':1}
 metrics={'balanced_accuracy':1.0,'coverage':1.0,'set_size':1.0,'per_class':{str(i):{'n':3,'recall':1.,'coverage':1.,'set_size':1.} for i in range(7)}}
 w.check_evaluation(task,out,metrics)
 assert (out/'evaluation.json').exists()
 np.savez_compressed(out/'test_outcomes.npz',sample_id=ids[::-1],y_pred=y,set_mask=masks,covered=np.ones(len(y),bool),set_size=np.ones(len(y),int))
 with pytest.raises(ValueError,match='ID/order'):w.check_evaluation(task,out,metrics)
