import importlib.util
from pathlib import Path
import unittest
import tempfile
import sys

SRC=Path(__file__).parents[1]/"source"/"reporting.py"
sys.path.insert(0,str(SRC.parent))
spec=importlib.util.spec_from_file_location("staged_reporting",SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ReportingCompletionTests(unittest.TestCase):
    def test_e5_pairs_exact_keys_and_exposes_missing_comparators(self):
        cases=[
          {"key":"clean1","scientific_case":True,"experiment":5,"rep":1,"method":"lr","route":"synthetic","generator":"gmm","condition":"clean_control","status":"successful","outcome":"successful"},
          {"key":"corr1","scientific_case":True,"experiment":5,"rep":1,"method":"lr","route":"synthetic","generator":"gmm","condition":"feature_noise_5","mechanism":"feature_noise","rate":0.05,"status":"successful","outcome":"successful"},
          {"key":"corr2","scientific_case":True,"experiment":5,"rep":2,"method":"lr","route":"synthetic","generator":"gmm","condition":"feature_noise_5","mechanism":"feature_noise","rate":0.05,"status":"unavailable_dependency","reason":"clean dependency unavailable","outcome":"unavailable_dependency"},
          {"key":"wrongmethod","scientific_case":True,"experiment":5,"rep":1,"method":"rf","route":"synthetic","generator":"gmm","condition":"clean_control","status":"successful","outcome":"successful"},
          {"key":"helper","experiment":5,"scientific_case":False,"rep":1,"method":"lr","route":"synthetic","generator":"gmm","condition":"feature_noise_5","mechanism":"feature_noise","rate":0.05,"status":"successful","outcome":"successful"},
        ]
        cls=[
          {"key":"clean1","class_id":"0","recall":0.8,"coverage":0.9},
          {"key":"corr1","class_id":"0","recall":0.6,"coverage":0.8},
          {"key":"wrongmethod","class_id":"0","recall":0.95,"coverage":1.0},
        ]
        out=mod._paired_per_class(cases,cls)
        r=next(x for x in out if x["corrupted_key"]=="corr1" and x["class_id"]=="0")
        self.assertEqual(r["pair_status"],"paired")
        self.assertEqual(r["corrupted_status"],"successful")
        self.assertEqual(r["clean_status"],"successful")
        self.assertAlmostEqual(r["recall_difference_a_minus_b"],-.2)
        self.assertAlmostEqual(r["coverage_difference_a_minus_b"],-.1)
        missing=next(x for x in out if x["corrupted_key"]=="corr2" and x["class_id"]=="0")
        self.assertFalse(missing["paired_available"])
        self.assertEqual(missing["pair_status"],"no_unique_clean_reference")
        self.assertIsNone(missing["recall_difference_a_minus_b"])
        self.assertEqual(len(out),2*7)

    def test_e4_pairs_target_and_method_without_cross_repetition(self):
        rows=[
          {"key":"base","experiment":4,"rep":1,"method":"logistic","condition":"control","route":"direct","target_class":None,"ratio":None,"balanced_accuracy":0.7,"coverage":0.9,"set_size":2,"outcome":"successful"},
          {"key":"alter","experiment":4,"rep":1,"method":"logistic","condition":"A_half","route":"direct","target_class":0,"ratio":0.5,"balanced_accuracy":0.6,"coverage":0.8,"set_size":3,"outcome":"successful"},
          {"key":"weight","experiment":4,"rep":1,"method":"logistic","condition":"A_half_weighted","route":"treatment","treatment":"weighted","target_class":0,"ratio":0.5,"balanced_accuracy":0.65,"coverage":0.85,"set_size":2.5,"outcome":"successful"},
          {"key":"wrongrep","experiment":4,"rep":2,"method":"logistic","condition":"control","route":"direct","target_class":None,"ratio":None,"balanced_accuracy":0.8,"coverage":0.95,"set_size":1,"outcome":"successful"},
        ]
        classes=[{"key":"base","class_id":"0","recall":.75,"coverage":.88},{"key":"alter","class_id":"0","recall":.55,"coverage":.72},{"key":"weight","class_id":"0","recall":.65,"coverage":.81}]
        out=mod._e4_paired_controls(rows,classes)
        alter=next(x for x in out if x["case_key"]=="alter")
        weight_rows=[x for x in out if x["case_key"]=="weight"]
        self.assertEqual(alter["pair_status"],"paired")
        self.assertAlmostEqual(alter["paired_balanced_accuracy_difference_a_minus_b"],-.1)
        self.assertAlmostEqual(alter["paired_target_class_recall_difference_a_minus_b"],-.20)
        self.assertAlmostEqual(alter["paired_target_class_coverage_difference_a_minus_b"],-.16)
        self.assertEqual({x["comparison"] for x in weight_rows},{"treatment_minus_untreated_altered","treatment_minus_unchanged_control"})
        self.assertTrue(all(x["control_key"]!="wrongrep" for x in weight_rows))
        self.assertTrue(all(x["paired_available"] for x in weight_rows))

    def test_e4_e5_figure_smoke_contains_control_and_repetition_labels(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); rt=root/"runtime"; out=root/"reports"; rt.mkdir(); out.mkdir()
            rows=[
              {"experiment":4,"scientific_case":True,"balanced_accuracy":.7,"coverage":.9,"set_size":2,"rep":1,"target_class":None,"condition":"control","method":"lr","route":"direct","ratio":None,"treatment":None},
              {"experiment":4,"scientific_case":True,"balanced_accuracy":.6,"coverage":.8,"set_size":3,"rep":1,"target_class":0,"condition":"A_half","method":"lr","route":"direct","ratio":.5,"treatment":None},
              {"experiment":5,"scientific_case":True,"balanced_accuracy":.7,"coverage":.9,"set_size":2,"rep":1,"condition":"clean_control","method":"lr","route":"direct","generator":None,"mechanism":None,"rate":None},
              {"experiment":5,"scientific_case":True,"balanced_accuracy":.6,"coverage":.8,"set_size":3,"rep":1,"condition":"noise","method":"lr","route":"direct","generator":None,"mechanism":"feature_noise","rate":.05},
            ]
            made=mod._figures(rt,out,rows)
            self.assertTrue((out/"E4_balanced_accuracy_target_treatment.png").exists())
            self.assertTrue((out/"E5_balanced_accuracy_corruption_sweeps.png").exists())
            self.assertEqual(len(made),6)

    def test_condition_summary_keeps_exact_strata_and_unmatched_denominator(self):
        rows=[
          {"rep":1,"method":"lr","route":"direct","generator":"gmm","mechanism":"feature_noise","rate":.05,"class_id":"0","paired_available":True,"recall_difference_a_minus_b":-.1,"coverage_difference_a_minus_b":-.05},
          {"rep":2,"method":"lr","route":"direct","generator":"gmm","mechanism":"feature_noise","rate":.05,"class_id":"0","paired_available":True,"recall_difference_a_minus_b":-.3,"coverage_difference_a_minus_b":-.15},
          {"rep":3,"method":"lr","route":"direct","generator":"gmm","mechanism":"feature_noise","rate":.05,"class_id":"0","paired_available":False,"recall_difference_a_minus_b":None,"coverage_difference_a_minus_b":None},
          {"rep":1,"method":"rf","route":"direct","generator":"gmm","mechanism":"feature_noise","rate":.05,"class_id":"0","paired_available":True,"recall_difference_a_minus_b":.2,"coverage_difference_a_minus_b":.1},
        ]
        out=mod._condition_paired_summary(rows,("method","route","generator","mechanism","rate","class_id"),("recall_difference_a_minus_b","coverage_difference_a_minus_b"))
        lr=next(x for x in out if x["method"]=="lr")
        rf=next(x for x in out if x["method"]=="rf")
        self.assertEqual((lr["planned_repetitions"],lr["available_repetitions"],lr["unmatched_repetitions"]),(3,2,1))
        self.assertAlmostEqual(lr["recall_difference_a_minus_b_mean"],-.2)
        self.assertAlmostEqual(lr["recall_difference_a_minus_b_sample_sd"],(0.02)**.5)
        self.assertEqual(rf["available_repetitions"],1)
        self.assertIsNone(rf["recall_difference_a_minus_b_sample_sd"])
        self.assertEqual(len(out),2)

    def test_main_heatmaps_emit_requested_figures_with_sparse_support(self):
        rows=[]
        def e4(key,condition,route,target,ratio,treatment,ba,recall):
            rows.append({"key":key,"experiment":4,"scientific_case":True,"rep":1,"method":"logistic","condition":condition,"route":route,"target_class":target,"ratio":ratio,"treatment":treatment,"outcome":"successful","balanced_accuracy":ba,"coverage":.9,"set_size":2})
        e4("c","control","direct",None,None,None,.7,None)
        e4("d","A_half","direct",0,.5,None,.6,.5)
        e4("t","A_half_weighted","treatment",0,.5,"weighted",.65,.6)
        rows.extend([
          {"key":"ec","experiment":5,"scientific_case":True,"rep":1,"method":"logistic","route":"direct","generator":None,"condition":"clean_control","outcome":"successful","balanced_accuracy":.7,"coverage":.9,"set_size":2},
          {"key":"en","experiment":5,"scientific_case":True,"rep":1,"method":"logistic","route":"direct","generator":None,"condition":"feature_noise_5","mechanism":"feature_noise","rate":.05,"outcome":"successful","balanced_accuracy":.6,"coverage":.8,"set_size":2.2},
          {"key":"sc","experiment":5,"scientific_case":True,"rep":1,"method":"logistic","route":"synthetic","generator":"gmm","condition":"clean_control","outcome":"successful","balanced_accuracy":.65,"coverage":.88,"set_size":2.1},
          {"key":"sn","experiment":5,"scientific_case":True,"rep":1,"method":"logistic","route":"synthetic","generator":"gmm","condition":"feature_noise_5","mechanism":"feature_noise","rate":.05,"outcome":"successful","balanced_accuracy":.55,"coverage":.78,"set_size":2.3},
        ])
        classes=[{"key":"c","class_id":"0","recall":.9,"coverage":.9},{"key":"d","class_id":"0","recall":.1,"coverage":.8},{"key":"t","class_id":"0","recall":.3,"coverage":.85}]
        captured=[]; colorbars=[]
        orig_heat=mod._annotated_heatmap;orig_bar=mod._add_heatmap_colorbar
        def capture_heat(*args,**kwargs):
            image=orig_heat(*args,**kwargs);captured.append((args[4],image.get_clim()));return image
        def capture_bar(fig,axes,mappable,label,**kwargs):
            colorbars.append((label,mappable.get_clim()))
            return orig_bar(fig,axes,mappable,label,**kwargs)
        mod._annotated_heatmap=capture_heat;mod._add_heatmap_colorbar=capture_bar
        try:
            with tempfile.TemporaryDirectory() as td:
                paths=mod._main_heatmaps(Path(td),Path(td),rows,classes)
                self.assertEqual(len(paths),5)
                self.assertTrue(all(Path(p).stat().st_size>1000 for p in paths))
        finally:
            mod._annotated_heatmap=orig_heat;mod._add_heatmap_colorbar=orig_bar
        ba=[v for k,v in captured if k.startswith("BA: restoration")]
        recall=[v for k,v in captured if k.startswith("Target-class recall: restoration")]
        self.assertEqual(len(ba),2);self.assertEqual(ba[0],ba[1])
        self.assertEqual(len(recall),2);self.assertEqual(recall[0],recall[1])
        direct_ba=[v for k,v in captured if k.startswith("Direct BA:")]
        direct_recall=[v for k,v in captured if k.startswith("Direct Target-class recall:")]
        self.assertEqual(len(direct_ba),2);self.assertEqual(direct_ba[0],direct_ba[1])
        self.assertEqual(len(direct_recall),2);self.assertEqual(direct_recall[0],direct_recall[1])
        self.assertNotEqual(ba[0],recall[0]);self.assertNotEqual(direct_ba[0],direct_recall[0])
        self.assertEqual(len(colorbars),9)
        for label,clim in colorbars:
            if label.startswith("BA paired") or label.startswith("Target-class recall"):
                self.assertIsInstance(clim,tuple)
        e5clims=[clim for _,clim in captured[12:]]
        self.assertEqual(len(e5clims),12)
        for start in (0,4,8): self.assertTrue(all(x==e5clims[start] for x in e5clims[start:start+4]))
        e5bars=[clim for label,clim in colorbars if label=="Mean paired delta balanced accuracy"]
        self.assertEqual(len(e5bars),3)
        self.assertEqual(e5bars,[e5clims[3],e5clims[7],e5clims[11]])

    def test_eval_lookup_prefers_relocated_artifact_key_over_stale_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); runtime=root/"extracted"/"runtime"; key="e5/rep_1/eval/direct/logistic/clean"
            relocated=runtime/"artifacts"/key;relocated.mkdir(parents=True)
            original=root/"old_ec2"/"artifacts"/key;original.mkdir(parents=True)
            (relocated/"evaluation.json").write_text('{"balanced_accuracy":0.42,"coverage":0.9,"set_size":2.0}')
            (original/"evaluation.json").write_text('{"balanced_accuracy":0.99,"coverage":1.0,"set_size":1.0}')
            rec={"key":key,"artifact_dir":str(original),"scientific_case":True,"status":"validated_terminal","outcome":"successful","validation_state":"valid"}
            ev=mod._find_eval(runtime,rec)
            self.assertAlmostEqual(ev["balanced_accuracy"],0.42)

    def test_eval_lookup_never_falls_back_to_original_path_and_alias_uses_own_key(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);runtime=root/"extracted"/"runtime";key="e5/rep_1/eval/direct/logistic/clean"
            original=root/"old_ec2"/"artifacts"/key;original.mkdir(parents=True)
            (original/"evaluation.json").write_text('{"balanced_accuracy":0.99}')
            rec={"key":key,"artifact_dir":str(original),"scientific_case":True,"status":"validated_terminal","outcome":"successful","validation_state":"valid","kind":"alias","source_key":"e4/rep_1/eval/direct/logistic/control"}
            self.assertIsNone(mod._find_eval(runtime,rec))
            aliasdir=runtime/"artifacts"/key;aliasdir.mkdir(parents=True)
            (aliasdir/"evaluation.json").write_text('{"balanced_accuracy":0.55,"coverage":0.88,"set_size":2.2}')
            self.assertAlmostEqual(mod._find_eval(runtime,rec)["balanced_accuracy"],0.55)
            rec["key"]="../escape"
            self.assertIsNone(mod._find_eval(runtime,rec))

    def test_heatmap_panels_share_metric_limits_and_colorbar_mappable(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        low=[[-.15,.01],[float("nan"),0.0]]
        high=[[-.85,.05],[.12,float("nan")]]
        limits=mod._symmetric_heatmap_limits([low,high])
        self.assertEqual(limits,(-.85,.85))
        fig,axs=plt.subplots(1,2)
        a=mod._annotated_heatmap(axs[0],low,["a","b"],["x","y"],"low",limits=limits)
        b=mod._annotated_heatmap(axs[1],high,["a","b"],["x","y"],"high",limits=limits)
        self.assertEqual(a.get_clim(),(-.85,.85))
        self.assertEqual(b.get_clim(),(-.85,.85))
        bar=mod._add_heatmap_colorbar(fig,axs.tolist(),a,"shared metric delta")
        self.assertIs(bar.mappable,a)
        self.assertEqual(bar.mappable.get_clim(),b.get_clim())
        plt.close(fig)

    def test_single_rep_sd_is_undefined(self):
        self.assertEqual(mod._mean_sd([0.4]),(0.4,None))
        mean,sd=mod._mean_sd([0.2,0.4,0.6])
        self.assertAlmostEqual(mean,0.4)
        self.assertGreater(sd,0)

if __name__=="__main__": unittest.main()
