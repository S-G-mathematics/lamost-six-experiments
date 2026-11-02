import sys, unittest
from pathlib import Path
STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import admission_evidence as ae

class WeightedMeanRoundoffGateTests(unittest.TestCase):
    def test_unit_mean_and_floating_roundoff_pass(self):
        for value in (1.0, 1.0000000000000002, 0.9999999999999998, 1.0+1e-13, 1.0-1e-13):
            with self.subTest(value=value): self.assertTrue(ae._unit_mean_sample_weight_mean(value))
    def test_material_nonfinite_boolean_and_non_numeric_fail(self):
        for value in (1.0001, 0.9999, float('nan'), float('inf'), -float('inf'), True, False, '1.0', None):
            with self.subTest(value=value): self.assertFalse(ae._unit_mean_sample_weight_mean(value))

if __name__=='__main__': unittest.main()
