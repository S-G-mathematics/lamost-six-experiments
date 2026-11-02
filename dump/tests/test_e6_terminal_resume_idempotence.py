import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE=Path(__file__).resolve().parent
CONTROLLER_PATH=HERE.parent/'source'/'controller.py'
stub=types.ModuleType('admission_evidence')
with mock.patch.dict(sys.modules,{'admission_evidence':stub}):
    spec=importlib.util.spec_from_file_location('e6_terminal_resume_controller',CONTROLLER_PATH)
    controller=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)

DEFAULT_OVERLAY='a'*64
PRIOR={'planned':21,'outcomes':{'successful':12,'unavailable_dependency':9}}
NAMES=('E6_EXECUTION_TERMINAL.json','E6_FINAL_CELL_LEDGER_21.csv')

def write_bytes(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)

def write_json(path,value):
    write_bytes(path,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def make_history(root,overlay_sha,meta='valid'):
    reports=root/'reports'
    history=reports/'history'/('e6_v1_availability_gate_'+overlay_sha[:16])
    write_json(history/NAMES[0],{'planned':21,'outcomes':PRIOR['outcomes'],'observed_utc':'historical-v1'})
    write_bytes(history/NAMES[1],b'legacy v1 final ledger\n')
    files=[]
    for name in NAMES:
        path=history/name
        files.append({'source_path':'reports/'+name,
                      'history_path':'reports/history/'+history.name+'/'+name,
                      'sha256':digest(path),'bytes':path.stat().st_size})
    doc={'schema_version':'lamost-e6-v1-report-supersession/1',
         'overlay_sha256':overlay_sha,
         'prior_terminal_marker_sha256':digest(history/NAMES[0]),
         'prior_terminal_state':PRIOR,
         'files':files,'superseded_as_current':True,
         'note':'Historical E6-v1 availability-gate outputs preserved.'}
    manifest=history/'SUPERSESSION_MANIFEST.json'
    write_json(manifest,doc)
    write_json(reports/'E6_EXECUTION_TERMINAL.json',{'protocol':'E6-v2','planned':21,'outcomes':{
        'successful':12,'scientific_failure':3,'unavailable_dependency':6}})
    write_bytes(reports/'E6_FINAL_CELL_LEDGER_21.csv',b'current v2 ledger\n')
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
    db.execute('CREATE TABLE tasks(key TEXT PRIMARY KEY,record TEXT)')
    db.execute('CREATE TABLE events(timestamp TEXT,kind TEXT,record TEXT)')
    task={'key':'e6/rep_1/ensemble/equal','attempts':[{'attempt_id':'existing-attempt'}],
          'status':'successful'}
    db.execute('INSERT INTO tasks VALUES (?,?)',(task['key'],json.dumps(task,sort_keys=True)))
    db.execute('INSERT INTO events VALUES (?,?,?)',('t0','existing','prior event'))
    if meta=='valid':
        db.execute('INSERT INTO meta VALUES (?,?)',('e6_v2_report_supersession_sha256',digest(manifest)))
    elif meta=='wrong':
        db.execute('INSERT INTO meta VALUES (?,?)',('e6_v2_report_supersession_sha256','f'*64))
    db.commit()
    return db,history,manifest,reports,task

class E6TerminalResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='e6-terminal-resume-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.old_r=controller.R
        controller.R=self.root
        self.addCleanup(setattr,controller,'R',self.old_r)

    def test_overlay_restart_preserves_v2_reports_history_and_attempts(self):
        overlay={'original_plan_freeze_utc':'2026-10-27T20:00:00Z','tasks':[]}
        fit_evidence={'gmm':{'pipeline_sha256':'a'*64}}
        for rep in (1,2,3):
            for mode in ('equal','learned'):
                key=f'e6/rep_{rep}/ensemble/{mode}'
                overlay['tasks'].append({'task_key':key,'member_fit_evidence':fit_evidence})
        overlay_path=self.root/controller.E6_OVERLAY_REL
        write_json(self.root/'manifests'/'tasks.json',{'tasks':[]})
        write_json(overlay_path,overlay); overlay_sha=digest(overlay_path)
        db,history,manifest,reports,db_task=make_history(self.root,overlay_sha)
        db.execute('INSERT INTO meta VALUES (?,?)',('e6_v2_overlay_sha256',overlay_sha));db.commit()
        current_tasks={}
        for row in overlay['tasks']:
            key=row['task_key']
            current_tasks[key]={'key':key,'status':'successful','attempts':[{'attempt_id':'prior-'+key}],
                                'e6_protocol_version':controller.E6_V2,
                                'e6_execution_overlay_sha256':overlay_sha,
                                'member_fit_evidence':fit_evidence}
        controller.DEFINITIONS={k:{'key':k} for k in current_tasks}
        frozen={'e6_execution_overlay_sha256':overlay_sha,'frozen_utc':overlay['original_plan_freeze_utc']}
        before={p.relative_to(self.root).as_posix():p.read_bytes()
                for p in list(history.iterdir())+[
                    reports/'E6_EXECUTION_TERMINAL.json',
                    reports/'E6_FINAL_CELL_LEDGER_21.csv']}
        task_rows_before=db.execute('SELECT key,record FROM tasks').fetchall()
        event_rows_before=db.execute('SELECT timestamp,kind,record FROM events').fetchall()
        with mock.patch.object(controller,'validate_e6_execution_overlay',return_value=(True,'validated')) as validate:
            result=controller.apply_e6_v2_execution_overlay(db,current_tasks,frozen)
        validate.assert_called_once()
        after={p.relative_to(self.root).as_posix():p.read_bytes()
               for p in list(history.iterdir())+[
                    reports/'E6_EXECUTION_TERMINAL.json',
                    reports/'E6_FINAL_CELL_LEDGER_21.csv']}
        self.assertEqual(result,current_tasks)
        self.assertEqual(before,after)
        self.assertEqual(db.execute('SELECT key,record FROM tasks').fetchall(),task_rows_before)
        self.assertEqual(db.execute('SELECT timestamp,kind,record FROM events').fetchall(),event_rows_before)
        self.assertEqual(sum(len(t['attempts']) for t in result.values()),6)
        self.assertEqual(db_task['attempts'],[{'attempt_id':'existing-attempt'}])
        self.assertEqual(db.execute('SELECT value FROM meta WHERE key=?',('e6_v2_report_supersession_sha256',)).fetchone()[0],digest(manifest))

    def test_tampered_historical_member_is_refused_without_touching_v2_reports(self):
        db,history,manifest,reports,_=make_history(self.root,DEFAULT_OVERLAY)
        current=(reports/'E6_EXECUTION_TERMINAL.json').read_bytes()
        with (history/NAMES[1]).open('ab') as f:f.write(b'tampered')
        tampered=(history/NAMES[1]).read_bytes()
        with self.assertRaisesRegex(RuntimeError,'history member changed'):
            controller.archive_e6_v1_outputs(db,DEFAULT_OVERLAY)
        self.assertEqual((reports/'E6_EXECUTION_TERMINAL.json').read_bytes(),current)
        self.assertEqual((history/NAMES[1]).read_bytes(),tampered)

    def test_wrong_overlay_or_registry_manifest_reference_is_refused(self):
        db,history,manifest,reports,_=make_history(self.root,DEFAULT_OVERLAY)
        doc=json.loads(manifest.read_text());doc['overlay_sha256']='b'*64;write_json(manifest,doc)
        db.execute('UPDATE meta SET value=? WHERE key=?',(digest(manifest),'e6_v2_report_supersession_sha256'));db.commit()
        with self.assertRaisesRegex(RuntimeError,'wrong schema, overlay, or v1 state'):
            controller.archive_e6_v1_outputs(db,DEFAULT_OVERLAY)
        db.close()
        second=self.root/'second'
        db,history,manifest,reports,_=make_history(second,DEFAULT_OVERLAY,meta='wrong')
        controller.R=second
        with self.assertRaisesRegex(RuntimeError,'registry E6 supersession reference differs'):
            controller.archive_e6_v1_outputs(db,DEFAULT_OVERLAY)

    def test_missing_meta_reference_recovers_same_manifest_without_new_attempts(self):
        db,history,manifest,reports,task=make_history(self.root,DEFAULT_OVERLAY,meta='missing')
        manifest_bytes=manifest.read_bytes();current=(reports/'E6_EXECUTION_TERMINAL.json').read_bytes()
        attempts_before=db.execute('SELECT record FROM tasks').fetchall()
        events_before=db.execute('SELECT timestamp,kind,record FROM events').fetchall()
        result=controller.archive_e6_v1_outputs(db,DEFAULT_OVERLAY)
        self.assertEqual(result['manifest_sha256'],hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(db.execute('SELECT value FROM meta WHERE key=?',('e6_v2_report_supersession_sha256',)).fetchone()[0],result['manifest_sha256'])
        self.assertEqual(manifest.read_bytes(),manifest_bytes)
        self.assertEqual((reports/'E6_EXECUTION_TERMINAL.json').read_bytes(),current)
        self.assertEqual(db.execute('SELECT record FROM tasks').fetchall(),attempts_before)
        self.assertEqual(db.execute('SELECT timestamp,kind,record FROM events').fetchall(),events_before)
        active=json.loads(db.execute('SELECT record FROM tasks').fetchone()[0])
        self.assertEqual(active['attempts'],task['attempts'])

if __name__=='__main__':
    unittest.main()
