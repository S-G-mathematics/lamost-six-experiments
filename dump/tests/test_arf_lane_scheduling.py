import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

SRC=pathlib.Path(__file__).resolve().parents[1]/"source"/"controller.py"
stub=types.ModuleType("admission_evidence")
with mock.patch.dict(sys.modules,{"admission_evidence":stub}):
    spec=importlib.util.spec_from_file_location("staged_controller",SRC)
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
G=c.GIB

def task(key,kind="fit",method="logistic",experiment=4,status="waiting_for_dependency",**extra):
    d={"key":key,"kind":kind,"method":method,"experiment":experiment,"route":"direct" if method=="arf" else None,"status":status,"attempts":[]}
    d.update(extra);return d

class ArfLaneSchedulingTests(unittest.TestCase):
    def run_candidate(self,running,ready,available,credits,idle=10,reservations=None,classes=None,total_cpus=16):
        reservations=reservations or {};classes=classes or {}
        def reservation(t):return reservations.get(t["key"],10*G)
        def resource_class(t):return classes.get(t["key"],"heavy")
        peaks=list(credits)
        with mock.patch.object(c,"worker_reservation_bytes",side_effect=reservation), \
             mock.patch.object(c,"worker_resource_class",side_effect=resource_class), \
             mock.patch.object(c,"candidate_cpu_reservation_units",return_value=1), \
             mock.patch.object(c,"bracketed_worker_memory",return_value=(available,list(credits),peaks)), \
             mock.patch.object(c.os,"cpu_count",return_value=total_cpus), \
             mock.patch.object(c.archive_fit_admission,"inspect_runtime",return_value={"mode":"inactive"}), \
             mock.patch.object(c,"atomic"):
            return c.admission_candidate(None,running,ready,idle,available)
    def fixture_workers(self):
        running=[task("rf",method="random_forest",status="running"),
                 task("rbf1",method="rbf_svm",status="running"),
                 task("rbf2",method="rbf_svm",status="running"),
                 task("rbf3",method="rbf_svm",status="running"),
                 task("rbf4",method="rbf_svm",status="running")]
        reservations={"rf":6*G,**{f"rbf{i}":3*G for i in range(1,5)}}
        classes={"rf":"heavy",**{f"rbf{i}":"light" for i in range(1,5)}}
        credits=[G]*5
        return running,reservations,classes,credits
    def test_preserves_arf_headroom_and_allows_fast_nonfit_sink(self):
        running,reservations,classes,credits=self.fixture_workers()
        arf=task("arf-ready",method="arf",experiment=4)
        light=task("light-fit",method="logistic",experiment=4)
        alias=task("alias-fast",kind="alias",method="arf")
        reservations.update({"arf-ready":6*G,"light-fit":2*G,"alias-fast":G//4})
        classes.update({"arf-ready":"heavy","light-fit":"light","alias-fast":"light"})
        chosen=self.run_candidate(running,[light,alias,arf],26*G,credits,reservations=reservations,classes=classes)
        self.assertEqual(chosen["key"],"alias-fast")
    def test_admits_arf_after_natural_worker_completion(self):
        running=[];credits=[]
        reservations={"arf-ready":6*G,"light-fit":2*G}
        classes={"arf-ready":"heavy","light-fit":"light"}
        arf=task("arf-ready",method="arf",experiment=4)
        light=task("light-fit",method="logistic")
        chosen=self.run_candidate(running,[light,arf],26*G,credits,reservations=reservations,classes=classes)
        self.assertIsNotNone(chosen,c.LAST_MEMORY_ADMISSION)
        self.assertEqual(chosen["key"],"arf-ready")
    def test_non_direct_arf_fit_is_not_special_lane_eligible(self):
        running,reservations,classes,credits=self.fixture_workers()
        running=[];credits=[]
        arf_treatment=task("arf-treatment",method="arf",experiment=4,route="treatment")
        light=task("light-fit",method="logistic")
        reservations.update({"arf-treatment":6*G,"light-fit":2*G})
        classes.update({"arf-treatment":"heavy","light-fit":"light"})
        self.assertIsNone(c._eligible_waiting_arf6_fit([arf_treatment]))
        chosen=self.run_candidate(running,[arf_treatment,light],26*G,credits,reservations=reservations,classes=classes)
        self.assertIsNotNone(chosen)
    def test_rbf_or_rf_generator_named_arf_is_not_arf_lane(self):
        rf_gen=task("rf-generator-arf",method="random_forest",experiment=4,generator="arf")
        chosen=self.run_candidate([], [rf_gen],30*G,[],reservations={rf_gen["key"]:10*G},classes={rf_gen["key"]:"heavy"})
        self.assertEqual(chosen["key"],rf_gen["key"])
    def test_existing_arf_lane_preserves_normal_light_packing(self):
        active=task("active-arf",method="arf",experiment=5,status="running")
        light=task("light-fit",kind="alias",method="logistic")
        arf2=task("second-arf",method="arf",experiment=4)
        chosen=self.run_candidate([active],[light,arf2],30*G,[G],reservations={"active-arf":6*G,"light-fit":2*G,"second-arf":6*G},
                                  classes={"active-arf":"heavy","light-fit":"light","second-arf":"heavy"})
        self.assertEqual(chosen["key"],"light-fit")
    def test_no_arf_ready_or_eligible_keeps_normal_admission(self):
        running=[];credits=[]
        reservations={"light-fit":2*G};classes={"light-fit":"light"}
        light=task("light-fit",method="logistic")
        self.assertEqual(self.run_candidate(running,[light],26*G,credits,reservations=reservations,classes=classes)["key"],"light-fit")
        arf_attempted=task("arf-old-attempt",method="arf",experiment=4,attempts=[{"attempt_id":"old"}])
        reservations[arf_attempted["key"]]=6*G;classes[arf_attempted["key"]]="heavy"
        self.assertIsNone(c._eligible_waiting_arf6_fit([arf_attempted]))
        self.assertIsNotNone(self.run_candidate(running,[light,arf_attempted],26*G,credits,reservations=reservations,classes=classes))
    def test_does_not_hold_new_fits_when_no_work_can_release_memory(self):
        arf=task("arf-ready",method="arf",experiment=4)
        light=task("light-fit",method="logistic")
        chosen=self.run_candidate([], [arf,light],11*G,[],reservations={"arf-ready":6*G,"light-fit":2*G},
                                  classes={"arf-ready":"heavy","light-fit":"light"})
        self.assertEqual(chosen["key"],"light-fit")
    def test_cpu_and_memory_caps_still_bind(self):
        arf=task("arf-ready",method="arf",experiment=4)
        self.assertIsNone(self.run_candidate([], [arf],7*G,[],reservations={"arf-ready":6*G},total_cpus=2,idle=1))
        running,reservations,classes,credits=self.fixture_workers()
        arf=task("arf-ready",method="arf",experiment=4)
        reservations["arf-ready"]=6*G;classes["arf-ready"]="heavy"
        self.assertIsNone(self.run_candidate(running,[arf],7*G,credits,reservations=reservations,classes=classes))
    def test_prioritizes_arf_only_when_its_six_gib_admission_is_valid(self):
        arf=task("arf-ready",method="arf",experiment=4)
        light=task("light-fit",method="logistic")
        chosen=self.run_candidate([], [light,arf],16*G,[],reservations={"arf-ready":6*G,"light-fit":2*G},
                                  classes={"arf-ready":"heavy","light-fit":"light"})
        self.assertIsNotNone(chosen,c.LAST_MEMORY_ADMISSION)
        self.assertEqual(chosen["key"],"arf-ready")

if __name__=="__main__":unittest.main(verbosity=2)

