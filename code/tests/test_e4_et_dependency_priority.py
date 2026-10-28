import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"source"/"controller.py"
TREE=ast.parse(SOURCE.read_text())
NODES={n.name:n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
NS={"GIB":1024**3,"worker_resource_class":lambda t:t["_class"],
    "worker_reservation_bytes":lambda t:t.get("_reservation",10*1024**3)}
e6_constant=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="E6_V2" for t in n.targets))
needed=[e6_constant,NODES["_is_e6_v2_ensemble"],NODES["_is_e4_et_control_fit"],
        NODES["_dispatch_stage_priority"],NODES["order_ready_for_admission"]]
exec(compile(ast.Module(body=needed,type_ignores=[]),str(SOURCE),"exec"),NS)

def task(key,exp,kind,method,cls="heavy",reservation=None,**extra):
    x={"key":key,"experiment":exp,"kind":kind,"method":method,"_class":cls}
    x.update(extra)
    if reservation is not None:x["_reservation"]=reservation*1024**3
    return x

def control(rep):
    return task(f"e4/rep_{rep}/fit/direct/extra_trees/control",4,"fit","extra_trees",
                route="direct",condition="control",rep=rep,status="planned",attempts=[])

class ExtraTreesDependencyPriorityTests(unittest.TestCase):
    def ordered(self,running,ready):
        return NS["order_ready_for_admission"](running,ready)

    def test_three_untouched_controls_precede_rf_fit_without_preempting_active_worker(self):
        active=task("active-rf",4,"fit","random_forest")
        rf=task("ordinary-e4-rf",4,"fit","random_forest")
        ctrls=[control(1),control(2),control(3)]
        before=[dict(t) for t in [active,rf,*ctrls]]
        got=self.ordered([active],[rf,*ctrls])
        self.assertEqual([t["key"] for t in got],[t["key"] for t in ctrls]+[rf["key"]])
        self.assertEqual([active,rf,*ctrls],before)

    def test_only_exact_unattempted_e4_direct_control_keys_are_promoted(self):
        rf=task("ordinary-rf",4,"fit","random_forest")
        good=control(1)
        bad=[
            task("e4/rep_4/fit/direct/extra_trees/control",4,"fit","extra_trees",route="direct",condition="control",rep=4,status="planned",attempts=[]),
            task("e4/rep_1/fit/synthetic/extra_trees/control",4,"fit","extra_trees",route="synthetic",condition="control",rep=1,status="planned",attempts=[]),
            task("e4/rep_1/fit/direct/extra_trees/control",4,"fit","extra_trees",route="direct",condition="half",rep=1,status="planned",attempts=[]),
            task("e4/rep_1/fit/direct/extra_trees/control",4,"fit","extra_trees",route="direct",condition="control",rep=1,status="running",attempts=[]),
            task("e4/rep_1/fit/direct/extra_trees/control",4,"fit","extra_trees",route="direct",condition="control",rep=1,status="planned",attempts=[{"attempt_id":"old"}]),
            task("e4/rep_1/fit/direct/extra_trees/control",4,"fit","extra_trees",route="direct",condition="control",rep=1,status="planned",attempts=[],admission_reservation_bytes=10*1024**3),
        ]
        self.assertTrue(NS["_is_e4_et_control_fit"](good))
        self.assertTrue(all(not NS["_is_e4_et_control_fit"](t) for t in bad))
        self.assertEqual([t["key"] for t in self.ordered([], [rf,*bad])],[rf["key"]]+[t["key"] for t in bad])

    def test_evaluations_and_aliases_keep_their_existing_sink_priority(self):
        rf=task("rf-fit",4,"fit","random_forest")
        ctl=control(1)
        ev=task("et-control-eval",4,"eval","extra_trees",route="direct",condition="control",rep=1)
        alias=task("et-clean-alias",5,"alias","extra_trees")
        got=self.ordered([], [rf,ctl,ev,alias])
        self.assertEqual([t["key"] for t in got],["et-clean-alias","et-control-eval",ctl["key"],rf["key"]])

    def test_existing_eligible_arf6_lane_stays_ahead_of_control_lane(self):
        active=task("active-rf",4,"fit","random_forest")
        rf=task("ordinary-rf",4,"fit","random_forest")
        ctl=control(2)
        arf6=task("eligible-arf6",5,"fit","arf",reservation=6)
        arf10=task("unproven-arf10",4,"fit","arf",reservation=10)
        got=self.ordered([active],[rf,ctl,arf6,arf10])
        self.assertEqual([t["key"] for t in got],["eligible-arf6",ctl["key"],"ordinary-rf","unproven-arf10"])

    def test_method_order_is_unchanged_when_no_control_dependency_is_ready(self):
        rf=task("e4-rf-fit",4,"fit","random_forest")
        et=task("e4-et-treatment",4,"fit","extra_trees",route="direct",condition="half",rep=1,status="planned",attempts=[])
        self.assertEqual([t["key"] for t in self.ordered([], [rf,et])],["e4-rf-fit","e4-et-treatment"])

    def test_resource_and_scientific_policy_literals_remain_frozen(self):
        def literal(name):
            node=next(n for n in TREE.body if isinstance(n,ast.Assign) and len(n.targets)==1
                      and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name)
            return ast.literal_eval(node.value)
        policy=literal("ADAPTIVE_POLICY")
        self.assertEqual(literal("DISPATCH_POLICY_ID"),"cross-exp-stage-arf6-e4-et-control-critical-path-20261028-v1")
        self.assertEqual(policy["worker_memory_limit_gib"],10)
        self.assertEqual(policy["trial_timeout_seconds"],600)
        self.assertEqual(policy["phase_timeout_seconds"],600)
        self.assertEqual(policy["nested_threads"],1)
        self.assertEqual(policy["host_os_harbor_reserve_gib"],6)
        self.assertEqual(policy["commitment_growth_margin_gib"],2)

if __name__=="__main__":unittest.main(verbosity=2)
