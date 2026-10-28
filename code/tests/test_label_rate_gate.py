from __future__ import annotations
import csv
import sys
import tempfile
import unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'source'))
import finalize_project as finalizer

LABELS=('A','F','G','K','M','GALAXY','QSO')
RATES=(0.05,0.1,0.2)
SUFFIX={0.05:'05',0.1:'10',0.2:'20'}
CHANGES={0.05:4000,0.1:8000,0.2:16000}
FIELDS=('task_key','rep','planned_corruption_rate','realized_corruption_rate','source_class_id','source_class_label','original_source_class_count','affected_source_class_count','changed_label_count','realized_source_class_corruption_rate','rate_status')

def valid_rows():
    rows=[]
    original=[11429,11429,11429,11429,11429,11429,11426]
    for rep in (1,2,3):
        for rate in RATES:
            total=CHANGES[rate];base,extra=divmod(total,7)
            for cls,label in enumerate(LABELS):
                changed=base+(1 if cls<extra else 0)
                support=original[cls]
                rows.append({'task_key':f'e5/rep_{rep}/corruption/label_noise_{SUFFIX[rate]}','rep':str(rep),'planned_corruption_rate':str(rate),'realized_corruption_rate':str(rate),'source_class_id':str(cls),'source_class_label':label,'original_source_class_count':str(support),'affected_source_class_count':str(changed),'changed_label_count':str(changed),'realized_source_class_corruption_rate':repr(changed/support),'rate_status':'available'})
    return rows

def write_table(path,rows):
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)

class LabelNoiseRateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'rates.csv';self.rows=valid_rows();write_table(self.path,self.rows)
    def tearDown(self):self.temp.cleanup()
    def result(self,count=63):return {'evidence_table_counts':{'E5_label_noise_source_class_rate_rows':count}}
    def assertGateRejects(self,path=None,result=None):
        with self.assertRaises(finalizer.EvidenceError):
            finalizer.validate_e5_label_noise_source_class_rates(path or self.path,result or self.result())
    def test_valid_complete_63_row_grid_passes_actual_finalizer_helper(self):
        self.assertEqual(finalizer.validate_e5_label_noise_source_class_rates(self.path,self.result()),63)
    def test_missing_table_is_rejected(self):
        self.assertGateRejects(Path(self.temp.name)/'missing.csv')
    def test_missing_row_is_rejected(self):
        write_table(self.path,self.rows[:-1]);self.assertGateRejects()
    def test_duplicate_class_row_is_rejected_even_when_row_count_is_63(self):
        rows=list(self.rows);rows[-1]=dict(rows[-2]);write_table(self.path,rows);self.assertGateRejects()
    def test_bad_original_support_denominator_is_rejected(self):
        rows=[dict(x) for x in self.rows];rows[0]['original_source_class_count']='0';write_table(self.path,rows);self.assertGateRejects()
    def test_inconsistent_class_rate_is_rejected(self):
        rows=[dict(x) for x in self.rows];rows[0]['realized_source_class_corruption_rate']='0.9';write_table(self.path,rows);self.assertGateRejects()
    def test_report_result_count_must_be_63(self):
        self.assertGateRejects(result=self.result(62))

if __name__=='__main__':unittest.main()
