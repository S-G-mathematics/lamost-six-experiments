import importlib.util
from pathlib import Path
import unittest

SRC=Path(__file__).parents[1]/"source"/"build_condition_findings.py"
spec=importlib.util.spec_from_file_location("findings",SRC)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class FindingsTests(unittest.TestCase):
    def test_summary_reconciles_mean_sample_sd_and_matched_denominator(self):
        raw=[
          {"rep":"1","group":"A","paired_available":"True","delta":"0.2"},
          {"rep":"2","group":"A","paired_available":"False","delta":""},
          {"rep":"3","group":"A","paired_available":"True","delta":"0.4"},
        ]
        summary=[{"group":"A","planned_repetitions":"3","rows":"3","available_repetitions":"2","unmatched_repetitions":"1",
                  "delta_n":"2","delta_mean":"0.3","delta_sample_sd":"0.1414213562373095"}]
        groups,_=mod.check_summary(raw,summary,("group",),{"delta":"delta"},"fixture")
        self.assertEqual(len(groups[("A",)]),3)

    def test_duplicate_repetition_cannot_replace_missing_rep_even_if_summary_matches(self):
        raw=[
          {"rep":"1","group":"A","paired_available":"True","delta":"0.2"},
          {"rep":"2","group":"A","paired_available":"False","delta":""},
          {"rep":"1","group":"A","paired_available":"True","delta":"0.2"},
        ]
        summary=[{"group":"A","planned_repetitions":"3","rows":"3","available_repetitions":"2","unmatched_repetitions":"1",
                  "delta_n":"2","delta_mean":"0.2","delta_sample_sd":"0"}]
        with self.assertRaisesRegex(ValueError,"exactly one repetition"):
            mod.check_summary(raw,summary,("group",),{"delta":"delta"},"fixture")

    def test_n_one_requires_blank_sample_sd(self):
        raw=[{"rep":"1","group":"A","paired_available":"True","delta":"-0.25"},
             {"rep":"2","group":"A","paired_available":"False","delta":""},
             {"rep":"3","group":"A","paired_available":"False","delta":""}]
        summary=[{"group":"A","planned_repetitions":"3","rows":"3","available_repetitions":"1","unmatched_repetitions":"2",
                  "delta_n":"1","delta_mean":"-0.25","delta_sample_sd":""}]
        mod.check_summary(raw,summary,("group",),{"delta":"delta"},"fixture")

    def test_n_zero_requires_blank_mean_and_sd(self):
        raw=[{"rep":"1","group":"A","paired_available":"False","delta":""},
             {"rep":"2","group":"A","paired_available":"False","delta":""},
             {"rep":"3","group":"A","paired_available":"False","delta":""}]
        good=[{"group":"A","planned_repetitions":"3","rows":"3","available_repetitions":"0","unmatched_repetitions":"3",
               "delta_n":"0","delta_mean":"","delta_sample_sd":""}]
        mod.check_summary(raw,good,("group",),{"delta":"delta"},"fixture")
        bad=[dict(good[0],delta_mean="0.0")]
        with self.assertRaises(ValueError):
            mod.check_summary(raw,bad,("group",),{"delta":"delta"},"fixture")

    def test_known_class_labels(self):
        self.assertEqual(mod.fmt_target("0"),"A")
        self.assertEqual(mod.fmt_target("6"),"QSO")

if __name__=="__main__":unittest.main()
