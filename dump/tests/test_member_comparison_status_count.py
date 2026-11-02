import importlib.util
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'source'/'e6_v2_reporting.py'
spec=importlib.util.spec_from_file_location('staged_e6_v2_reporting',SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class MemberAvailabilityNarrativeTests(unittest.TestCase):
    def render(self,rows):
        return module.render_status_section(rows,[{} for _ in range(6)],[])

    def rows(self, n_valid, invalid_values=None):
        invalid_values=invalid_values or {}
        result=[]
        for i in range(6):
            if i<n_valid:
                result.append({'outcome':'successful','member_comparison_present':'True',
                               'member_comparisons_sha256':hex(i+1)[2:].zfill(64)})
            else:
                value=invalid_values.get(i,('False',''))
                result.append({'outcome':'scientific_failure' if i%2==0 else 'unavailable_dependency',
                               'member_comparison_present':value[0],
                               'member_comparisons_sha256':value[1]})
        return result

    def test_zero_valid_artifacts_does_not_count_csv_false_strings(self):
        report=self.render(self.rows(0,{1:('True','bad')}))
        self.assertIn('0 of 6 have a successful validation-bound member_comparisons artifact',report)

    def test_mixed_artifact_rows_count_only_true_with_sha256(self):
        report=self.render(self.rows(2,{2:('True','') ,3:('True','z'*64)}))
        self.assertIn('2 of 6 have a successful validation-bound member_comparisons artifact',report)

    def test_all_successful_validated_artifacts_are_counted(self):
        report=self.render(self.rows(6))
        self.assertIn('6 of 6 have a successful validation-bound member_comparisons artifact',report)

if __name__=='__main__':
    unittest.main()
