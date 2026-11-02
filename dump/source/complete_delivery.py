#!/usr/bin/env python3
"""Complete LAMOST delivery only after validating finalizer artifacts and laptop transfer evidence."""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023')
RUNTIME=ROOT/'runtime_20261025'
PENDING=RUNTIME/'EC2_COMPLETE_DELIVERY_PENDING.json'
TAG_AIRBAG='LAMOST_PROJECT_AIRBAG'; TAG_INDEX='LAMOST_MASTER_INDEX'
TAG_COLD='LAMOST_COLD_STORAGE_AIRBAG'

class DeliveryError(RuntimeError):pass

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def atomic_json(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def sha_file(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def zip_check(path,required):
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None:raise DeliveryError(f'ZIP CRC check failed: {path}')
  names=set(z.namelist())
  if not set(required).issubset(names):raise DeliveryError(f'ZIP missing required members: {set(required)-names}')
  return names
def confined_package(path,project_root=ROOT):
 p=Path(path).resolve();base=(Path(project_root)/'packages').resolve()
 if base not in p.parents:raise DeliveryError(f'archive path is outside packages/: {p}')
 if not p.is_file():raise DeliveryError(f'archive is missing: {p}')
 return p
def artifact_record(marker,key,receipt_suffix='.receipt.json',required=(),project_root=ROOT,review_proof=None):
 rec=marker.get(key)
 if not isinstance(rec,dict) or not rec.get('path'):raise DeliveryError(f'marker has no valid {key} record')
 p=confined_package(rec['path'],project_root);n=int(rec['bytes']);h=str(rec['sha256'])
 if p.stat().st_size!=n or sha_file(p)!=h:raise DeliveryError(f'{key} size/SHA differs from finalizer marker')
 receipt_path=Path(str(p)+receipt_suffix)
 if not receipt_path.is_file():raise DeliveryError(f'{key} finalizer receipt is missing')
 receipt=load(receipt_path)
 if Path(receipt.get('path','')).resolve()!=p or int(receipt.get('bytes',-1))!=n or receipt.get('sha256')!=h or receipt.get('zip_crc_passed') is not True:
  raise DeliveryError(f'{key} receipt does not match archive identity')
 if review_proof is not None and receipt.get('report_review_proof')!=review_proof:raise DeliveryError(f'{key} receipt is not bound to the accepted report review')
 names=zip_check(p,required)
 if review_proof is not None:
  if 'REPORT_REVIEW_PROOF.json' not in names:raise DeliveryError(f'{key} is missing REPORT_REVIEW_PROOF.json')
  with zipfile.ZipFile(p) as z:
   if json.loads(z.read('REPORT_REVIEW_PROOF.json'))!=review_proof:raise DeliveryError(f'{key} contains a different report review proof')
   if key=='full_archive':
    mm=json.loads(z.read('archive_member_manifest.json'))
    if mm.get('report_review_proof')!=review_proof:raise DeliveryError('full archive member manifest is not bound to accepted report review')
 return {'path':str(p),'bytes':n,'sha256':h,'receipt_path':str(receipt_path)}
def validate_finalizer(runtime=RUNTIME,project_root=ROOT,verify_review=True):
 runtime=Path(runtime);project_root=Path(project_root)
 pending=load(runtime/'EC2_COMPLETE_DELIVERY_PENDING.json')
 if pending.get('status') not in {'delivery_pending_on_laptop','validated_pending_delivery_reused'}:
  raise DeliveryError('finalizer is not in valid full-archive delivery-pending state')
 if pending.get('project_complete') is not False:raise DeliveryError('finalizer marker unexpectedly claims completion')
 if pending.get('laptop_copy_verified') is not False:raise DeliveryError('unexpected laptop verification state in finalizer marker')
 proof=pending.get('report_review')
 if not isinstance(proof,dict) or proof.get('decision')!='pass' or not proof.get('candidate_id') or not proof.get('manifest_sha256') or not proof.get('audit_receipt_sha256'):
  raise DeliveryError('finalizer marker lacks the exact accepted internal report-review proof')
 if verify_review:
  workers=no_project_workers()
  if workers:raise DeliveryError(f'project controller/worker still active: {workers[:6]}')
  ready=load(runtime/'REPORT_READY_FOR_AUDIT.json');receipt=load(runtime/'REPORT_AUDIT_RECEIPT.json')
  if ready.get('status')!='review_pass_recorded' or ready.get('candidate_id')!=proof.get('candidate_id') or ready.get('manifest_sha256')!=proof.get('manifest_sha256'):
   raise DeliveryError('REPORT_READY_FOR_AUDIT does not match package review proof')
  if sha_file(runtime/'REPORT_AUDIT_RECEIPT.json')!=proof.get('audit_receipt_sha256') or receipt.get('decision')!='pass' or receipt.get('candidate_id')!=proof.get('candidate_id') or receipt.get('manifest_sha256')!=proof.get('manifest_sha256'):
   raise DeliveryError('agent audit receipt does not match package review proof')
  from final_review import verify_pass
  observed,_=verify_pass(project_root,runtime)
  if observed!=proof:raise DeliveryError('current terminal/report/source snapshot differs from accepted review proof')
 full=artifact_record(pending,'full_archive',required=('archive_member_manifest.json','archive_aliases.json','restore_archive_aliases.py','REPORT_REVIEW_PROOF.json'),project_root=project_root,review_proof=proof)
 small=artifact_record(pending,'small_delivery_zip',required=('small_delivery_manifest.json','FULL_ARCHIVE_LOCATION.md','REPORT_REVIEW_PROOF.json'),project_root=project_root,review_proof=proof)
 with zipfile.ZipFile(small['path']) as z:sm=json.loads(z.read('small_delivery_manifest.json'))
 if not isinstance(sm.get('full_archive'),dict) or sm['full_archive'].get('sha256')!=full['sha256'] or int(sm['full_archive'].get('bytes',-1))!=full['bytes']:
  raise DeliveryError('small delivery ZIP points at a different full archive')
 if sm.get('report_review')!=proof:raise DeliveryError('small delivery manifest is not bound to accepted report review')
 if not isinstance(sm.get('files'),list):raise DeliveryError('small delivery manifest file table missing')
 return pending,full,small

def no_project_workers():
 found=[]
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:cmd=(proc/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
  except Exception:continue
  if any(x in cmd for x in ('source/controller.py','source/worker.py','source/phase_worker.py')):
   found.append({'pid':int(proc.name),'role':'controller_or_worker'})
 return found

def expected_cron_lines(root=ROOT):
 base=str(root);rt=base+'/runtime_20261025'
 return {TAG_AIRBAG:f"*/5 * * * * {base}/venv/bin/python {rt}/source/controller.py watchdog >> {rt}/logs/watchdog.log 2>&1 # {TAG_AIRBAG}",TAG_INDEX:f"*/5 * * * * {base}/venv/bin/python {rt}/source/export_master_index.py >> {rt}/logs/master_index.log 2>&1 # {TAG_INDEX}",TAG_COLD:f"*/5 * * * * {base}/venv/bin/python {rt}/source/cold_auto_compaction.py >/dev/null 2>&1 # {TAG_COLD}"}
def expected_cold_cron_lines(root=ROOT):
 raw=expected_cron_lines(root)[TAG_COLD]
 command,redirect=raw.split(' >/dev/null 2>&1 ',1)
 return (raw,command+' --storage-codec-policy reversible-xz-v1 >/dev/null 2>&1 '+redirect,command+' --archive-io-profile bounded-1800 >/dev/null 2>&1 '+redirect)
def cron_filter(lines,root=ROOT):
 kept=[];removed=[];unrecognized=[];expected=expected_cron_lines(root);cold_variants=expected_cold_cron_lines(root)
 for line in lines:
  plain=line.rstrip('\r\n')
  tag=next((t for t in (TAG_AIRBAG,TAG_INDEX,TAG_COLD) if plain.endswith('# '+t)),None)
  exact=(plain in cold_variants) if tag==TAG_COLD else (tag is not None and plain==expected[tag])
  if tag and exact:removed.append(line);continue
  if tag:unrecognized.append(line)
  kept.append(line)
 return kept,removed,unrecognized

def clean_crontab():
 p=subprocess.run(['crontab','-l'],capture_output=True,text=True)
 if p.returncode not in (0,1):raise DeliveryError('cannot inspect current crontab: '+p.stderr[-1000:])
 lines=p.stdout.splitlines(keepends=True) if p.returncode==0 else []
 kept,removed,unrecognized=cron_filter(lines)
 if removed:
  q=subprocess.run(['crontab','-'],input=''.join(kept),capture_output=True,text=True)
  if q.returncode:raise DeliveryError('failed to update crontab safely: '+q.stderr[-1000:])
  verify=subprocess.run(['crontab','-l'],capture_output=True,text=True)
  if verify.returncode not in (0,1):raise DeliveryError('cannot verify resulting crontab')
  current=verify.stdout.splitlines(keepends=True) if verify.returncode==0 else []
  if any(x in current for x in removed):raise DeliveryError('tagged crontab entries remain after cleanup')
 return {'removed_entries':len(removed),'removed_tags':[x.rstrip().rsplit('# ',1)[-1] for x in removed],'unrecognized_tagged_entries_preserved':len(unrecognized)}

def tagged_systemd_units(user_base=None,system_base=None):
 """Find only unit files carrying our literal ownership tags; no name-based guesses."""
 candidates=[]
 for base in (Path(user_base) if user_base else Path.home()/'.config/systemd/user',Path(system_base) if system_base else Path('/etc/systemd/system')):
  if not base.exists():continue
  for p in base.rglob('*'):
   if not p.is_file() or p.suffix not in {'.service','.timer'}:continue
   try:txt=p.read_text(encoding='utf-8',errors='ignore')
   except Exception:continue
   tags=[t for t in (TAG_AIRBAG,TAG_INDEX,TAG_COLD) if t in txt]
   if tags:candidates.append((p.name,tags,base==Path('/etc/systemd/system')))
 return candidates

def clean_tagged_systemd():
 units=tagged_systemd_units();done=[]
 for name,tags,system in units:
  cmd=['systemctl']+([] if system else ['--user'])+['disable','--now',name]
  p=subprocess.run(cmd,capture_output=True,text=True)
  if p.returncode:raise DeliveryError(f'could not stop/disable tagged systemd unit {name}: {p.stderr[-1000:]}')
  done.append({'unit':name,'tags':tags,'scope':'system' if system else 'user'})
 if units:
  for system in {x[2] for x in units}:
   subprocess.run(['systemctl']+([] if system else ['--user'])+['daemon-reload'],capture_output=True,text=True)
 return {'disabled_tagged_units':done}

def local_delivery_matches(pending,small,filename,byte_count,sha256,destination):
 expected=Path(small['path']).name
 if filename!=expected or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.zip',filename):raise DeliveryError('delivered filename does not match the finalizer artifact')
 if int(byte_count)!=small['bytes'] or sha256!=small['sha256']:raise DeliveryError('local byte count/SHA differs from compact ZIP')
 expected_dir=pending.get('laptop_delivery_directory')
 if not expected_dir or str(destination).rstrip('\\/')!=str(expected_dir).rstrip('\\/'):
  raise DeliveryError('destination differs from the finalizer-established laptop directory')
 return {'filename':filename,'bytes':small['bytes'],'sha256':small['sha256'],'destination':destination}

def complete(mode,filename=None,byte_count=None,sha256=None,destination=None,reason=None,runtime=RUNTIME):
 lock_path=Path(runtime)/'delivery_completion.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
 with lock_path.open('a+') as lock:
  import fcntl
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return {'status':'delivery_completion_already_running'}
  pending,full,small=validate_finalizer(runtime)
  if mode=='delivered':delivery=local_delivery_matches(pending,small,filename,byte_count,sha256,destination)
  elif mode=='inaccessible':
   if not reason or len(reason.strip())<12:raise DeliveryError('record-inaccessible requires a specific reason')
   destination=pending.get('laptop_delivery_directory')
   cmd=pending.get('laptop_copy_command')
   if not destination or not cmd:raise DeliveryError('pending marker lacks destination and transfer command')
   delivery={'destination':destination,'transfer_command':cmd,'reason':reason.strip(),'laptop_copy_verified':False}
  else:raise DeliveryError('unknown delivery mode')
  workers=no_project_workers()
  if workers:raise DeliveryError(f'project controller/worker still active; retry after stopping: {workers[:6]}')
  cron=clean_crontab();systemd=clean_tagged_systemd()
  if no_project_workers():raise DeliveryError('project workers appeared during cleanup; completion not written')
  record={'schema_version':'lamost-project-delivery/1','status':'complete_laptop_delivery_verified' if mode=='delivered' else 'complete_transfer_pending_laptop_inaccessible','project_complete_for_ec2_archive':True,'observed_utc':utc(),'delivery_mode':mode,'full_archive':full,'small_delivery_zip':small,'delivery':delivery,'cleanup':{'cron':cron,'systemd':systemd},'project_workers_stopped':True,'finalizer_marker':str(Path(runtime)/'EC2_COMPLETE_DELIVERY_PENDING.json'),'note':'Completion applies to the validated EC2 archive. Laptop transfer is only verified in delivered mode.'}
 atomic_json(Path(runtime)/'PROJECT_COMPLETE.json',record)
 return record

def self_test():
 with tempfile.TemporaryDirectory(prefix='lamost_delivery_test_') as td:
  root=Path(td);expected=expected_cron_lines();lines=[expected[TAG_AIRBAG]+'\n',expected[TAG_INDEX]+'\n',expected[TAG_COLD]+'\n','*/5 * * * * /opt/harbor/watch # HARBOR\n','*/5 * * * * /tmp/unrelated # LAMOST_PROJECT_AIRBAG\n','*/5 * * * * /tmp/unrelated # LAMOST_COLD_STORAGE_AIRBAG\n']
  kept,removed,unknown=cron_filter(lines)
  assert len(removed)==3 and len(unknown)==2 and kept==[lines[3],lines[4],lines[5]]
  ud=root/'systemd_user';sd=root/'systemd_system';ud.mkdir();sd.mkdir();(ud/'owned.timer').write_text('[Unit]\n# LAMOST_PROJECT_AIRBAG\n');(ud/'harbor.service').write_text('[Unit]\nDescription=Harbor\n')
  found=tagged_systemd_units(ud,sd);assert len(found)==1 and found[0][0]=='owned.timer' and found[0][1]==[TAG_AIRBAG]
  (root/'payload.zip').write_bytes(b'fixture');n=(root/'payload.zip').stat().st_size;h=sha_file(root/'payload.zip')
  assert n==7 and h==hashlib.sha256(b'fixture').hexdigest()
  # Build temporary full/small archives and matching finalizer receipts; test the validation gate without EC2 state.
  pkg=root/'packages';pkg.mkdir();full=pkg/'full.zip';small=pkg/'small.zip';runtime=root/'runtime';runtime.mkdir()
  proof={'decision':'pass','candidate_id':'c'*64,'manifest_sha256':'m'*64,'audit_receipt_sha256':'r'*64}
  with zipfile.ZipFile(full,'w') as z:
   z.writestr('archive_member_manifest.json',json.dumps({'report_review_proof':proof}));z.writestr('archive_aliases.json','{}');z.writestr('restore_archive_aliases.py','');z.writestr('REPORT_REVIEW_PROOF.json',json.dumps(proof))
  fullrec={'path':str(full),'bytes':full.stat().st_size,'sha256':sha_file(full),'zip_crc_passed':True,'report_review_proof':proof};(Path(str(full)+'.receipt.json')).write_text(json.dumps(fullrec))
  with zipfile.ZipFile(small,'w') as z:
   z.writestr('FULL_ARCHIVE_LOCATION.md','fixture');z.writestr('REPORT_REVIEW_PROOF.json',json.dumps(proof));z.writestr('small_delivery_manifest.json',json.dumps({'full_archive':fullrec,'files':[],'report_review':proof}))
  smallrec={'path':str(small),'bytes':small.stat().st_size,'sha256':sha_file(small),'zip_crc_passed':True,'report_review_proof':proof};(Path(str(small)+'.receipt.json')).write_text(json.dumps(smallrec))
  marker={'status':'delivery_pending_on_laptop','project_complete':False,'laptop_copy_verified':False,'report_review':proof,'full_archive':fullrec,'small_delivery_zip':smallrec,'laptop_delivery_directory':r'D:\\LAMOST_Overall_EC2_Handoff_20261023'}
  (runtime/'EC2_COMPLETE_DELIVERY_PENDING.json').write_text(json.dumps(marker))
  got,fr,sr=validate_finalizer(runtime,root,verify_review=False);identity=local_delivery_matches(got,sr,'small.zip',sr['bytes'],sr['sha256'],marker['laptop_delivery_directory'])
  assert identity['sha256']==sr['sha256']
  return {'status':'self_test_passed','only_exact_project_cron_lines_removed':True,'all_three_owned_cron_entries_removed':True,'unrelated_same_tag_lines_preserved':True,'Harbor_and_unknown_tagged_lines_preserved':True,'only_tagged_systemd_units_detected':True,'finalizer_receipts_archives_review_proof_and_zip_crc_validated':True,'local_transfer_identity_hash_and_bytes_checked':True,'no_live_completion_or_cleanup_performed':True}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--self-test',action='store_true');g=ap.add_mutually_exclusive_group();g.add_argument('--commit-delivery',action='store_true');g.add_argument('--record-inaccessible',action='store_true');ap.add_argument('--filename');ap.add_argument('--bytes',type=int);ap.add_argument('--sha256');ap.add_argument('--destination');ap.add_argument('--reason')
 a=ap.parse_args()
 try:
  if a.self_test:result=self_test()
  elif a.commit_delivery:result=complete('delivered',a.filename,a.bytes,a.sha256,a.destination)
  elif a.record_inaccessible:result=complete('inaccessible',reason=a.reason)
  else:
   pending,full,small=validate_finalizer();result={'status':'ready_or_waiting_marker_validated','full_archive':full,'small_delivery_zip':small,'project_workers':no_project_workers()}
  print(json.dumps(result,indent=2));return 0
 except Exception as e:
  print(json.dumps({'status':'delivery_not_completed','error':type(e).__name__+': '+str(e)},indent=2));return 2
if __name__=='__main__':raise SystemExit(main())
