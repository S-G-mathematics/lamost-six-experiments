import ast
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"source"/"controller.py"
TREE=ast.parse(SOURCE.read_text())
NODES={n.name:n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
NS={"GIB":1024**3,"worker_resource_class":lambda t:t["_class"],"worker_reservation_bytes":lambda t:t.get("_reservation",10*1024**3)}
e6_constant=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="E6_V2" for t in n.targets))
needed=[e6_constant,NODES["_is_e6_v2_ensemble"],NODES["_is_e4_et_control_fit"],NODES["_dispatch_stage_priority"],NODES["order_ready_for_admission"]]
exec(compile(ast.Module(body=needed,type_ignores=[]),str(SOURCE),"exec"),NS)

def task(key,exp,kind,method,cls="heavy",reservation=None):
    x={"key":key,"experiment":exp,"kind":kind,"method":method,"_class":cls}
    if reservation is not None:x["_reservation"]=reservation*1024**3
    return x

class DependencyPackingDispatchTests(unittest.TestCase):
 def ordered(self,running,ready):
  return NS["order_ready_for_admission"](running,ready)

 def test_global_stage_priority_precedes_experiment_order_within_heavy_lane(self):
  rf=task("e4-rf-fit",4,"fit","random_forest")
  e5eval=task("e5-rf-eval",5,"eval","random_forest")
  gen=task("e4-arf-gen",4,"generate","arf")
  arf_fit=task("e5-arf-fit",5,"fit","arf",reservation=6)
  running=[task("active-rf",4,"fit","random_forest")]
  self.assertEqual([x["key"] for x in self.ordered(running,[rf,e5eval,gen,arf_fit])],["e5-rf-eval","e4-arf-gen","e5-arf-fit","e4-rf-fit"])

 def test_light_first_is_retained_when_heavy_lane_is_active(self):
  active=task("active-rf",4,"fit","random_forest")
  heavy_eval=task("e5-rf-eval",5,"eval","random_forest")
  light_fit=task("e4-logit",4,"fit","logistic","light")
  self.assertEqual([x["key"] for x in self.ordered([active],[heavy_eval,light_fit])],["e4-logit","e5-rf-eval"])

 def test_no_rf_lane_preserves_same_stage_fit_order_even_for_arf6(self):
  rf=task("ordinary-rf",4,"fit","random_forest")
  arf=task("eligible-arf",5,"fit","arf",reservation=6)
  self.assertEqual([x["key"] for x in self.ordered([],[rf,arf])],["ordinary-rf","eligible-arf"])

 def test_only_gate_eligible_arf6_is_promoted_when_rf_heavy_is_active(self):
  active=task("active-rf",4,"fit","random_forest")
  rf=task("ordinary-rf",4,"fit","random_forest")
  arf6=task("eligible-arf6",5,"fit","arf",reservation=6)
  arf10=task("unproven-arf10",4,"fit","arf",reservation=10)
  self.assertEqual([x["key"] for x in self.ordered([active],[rf,arf6,arf10])],["eligible-arf6","ordinary-rf","unproven-arf10"])

 def test_arf_gate_checks_stop_after_first_valid_6gib_candidate(self):
  active=task("active-rf",4,"fit","random_forest")
  rf=task("ordinary-rf",4,"fit","random_forest")
  a=task("arf-unproven",4,"fit","arf")
  b=task("arf6-first",5,"fit","arf")
  d=task("arf6-second",5,"fit","arf")
  calls=[]
  def reservation(t):
   calls.append(t["key"])
   return 10*NS["GIB"] if t["key"]=="arf-unproven" else 6*NS["GIB"]
  with patch.dict(NS,{"worker_reservation_bytes":reservation}):
   got=NS["order_ready_for_admission"]([active],[rf,a,b,d])
  self.assertEqual(calls,["arf-unproven","arf6-first"])
  self.assertEqual([x["key"] for x in got],["arf6-first","ordinary-rf","arf-unproven","arf6-second"])

 def test_other_heavy_worker_does_not_activate_rf_specific_arf_boost(self):
  active=task("active-extra",4,"fit","extra_trees")
  rf=task("ordinary-rf",4,"fit","random_forest")
  arf=task("eligible-arf",5,"fit","arf",reservation=6)
  self.assertEqual([x["key"] for x in self.ordered([active],[rf,arf])],["ordinary-rf","eligible-arf"])

 def test_stable_ties_queue_completeness_and_no_task_mutation(self):
  a=task("a",4,"eval","logistic","light");b=task("b",5,"eval","logistic","light")
  items=[dict(a),dict(b)];before=[dict(x) for x in items];got=self.ordered([],items)
  self.assertEqual([x["key"] for x in got],["a","b"])
  self.assertEqual(sorted(x["key"] for x in got),sorted(x["key"] for x in items))
  self.assertEqual(items,before)

 def test_policy_metadata_is_outside_scientific_task_and_limits_unchanged(self):
  cfg=next(n for n in ast.walk(TREE) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="cfg" for t in n.targets) and isinstance(n.value,ast.Dict) and any(isinstance(k,ast.Constant) and k.value=="task" for k in n.value.keys))
  pairs={k.value:v for k,v in zip(cfg.value.keys,cfg.value.values) if isinstance(k,ast.Constant)}
  self.assertEqual(pairs["task"].id,"definition")
  self.assertIn("dispatch_policy_id",pairs)
  attempt_dicts=[n for n in ast.walk(TREE) if isinstance(n,ast.Dict) and any(isinstance(k,ast.Constant) and k.value=="dispatch_policy_id" for k in n.keys)]
  self.assertGreaterEqual(len(attempt_dicts),2)
  policy=next(n.value for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="ADAPTIVE_POLICY" for t in n.targets))
  policy=ast.literal_eval(policy)
  self.assertEqual(policy["worker_memory_limit_gib"],10)
  self.assertEqual(policy["trial_timeout_seconds"],600);self.assertEqual(policy["phase_timeout_seconds"],600)
  self.assertEqual(policy["nested_threads"],1);self.assertEqual(policy["host_os_harbor_reserve_gib"],6)
  self.assertEqual(policy["commitment_growth_margin_gib"],2)
  rev=next(n.value for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="ADAPTIVE_REVISION" for t in n.targets))
  self.assertEqual(ast.literal_eval(rev),"adaptive-concurrency-20261025-v1.1")
  pid=next(n.value for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="DISPATCH_POLICY_ID" for t in n.targets))
  self.assertEqual(ast.literal_eval(pid),"cross-exp-stage-arf6-e4-et-control-critical-path-20261028-v1")

if __name__=="__main__":unittest.main(verbosity=2)
