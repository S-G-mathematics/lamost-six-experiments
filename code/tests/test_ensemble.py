from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import joblib
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
sys.path.insert(0,str(ROOT.parent/'project'))
import ensemble

class Identity:
    def transform(self,x): return np.asarray(x,dtype=float)
class FixedPosterior:
    score_kind='probability'
    def __init__(self,offset=0): self.offset=offset
    def score_matrix(self,X):
        x=np.full((len(X),7),.01,dtype=float); x[:,self.offset]=.94; return x

def test_posterior_validation_rejects_bad_order_shape_or_normalization():
    good=np.full((3,7),1/7)
    assert ensemble._posterior(good,'fixture').shape==(3,7)
    with pytest.raises(ValueError): ensemble._posterior(np.ones((3,6))/6,'bad-shape')
    bad=good.copy(); bad[0,0]=.2
    with pytest.raises(ValueError): ensemble._posterior(bad,'bad-sum')

def test_protocol_weight_helper_ties_prefer_equal_vector():
    from benchmark.ensembles import fit_ensemble_weights
    y=np.arange(7,dtype=np.int64)
    onehot=np.eye(7,dtype=float)
    scores={m:onehot.copy() for m in ensemble.MEMBERS}
    selected=fit_ensemble_weights(scores,y,seed=19,dirichlet_candidates=30,candidate_cap=300)
    np.testing.assert_allclose(selected['weights'],np.full(5,.2),atol=0,rtol=0)
    assert selected['selected_candidate']==0
    assert selected['candidate_count']<=2000

def test_finite_sample_conformal_order_statistic():
    from benchmark.evaluation import conformal_threshold
    # n=9, alpha=.1 gives k=ceil(10*.9)=9, the largest calibration nonconformity.
    y=np.zeros(9,dtype=int); p=np.full((9,7),1/7,dtype=float); p[:,0]=np.linspace(.1,.9,9); p[:,1:]*=((1-p[:,0])/p[:,1:].sum(1))[:,None]
    q=conformal_threshold(p,y,alpha=.1)
    assert q==pytest.approx(1-.1)
    # n=8 gives k=ceil(9*.9)=9>n, so threshold is +infinity.
    assert np.isinf(conformal_threshold(p[:8],y[:8],alpha=.1))

def member_reference_gate():
    refs={m:f'e3/rep_1/eval/direct/{m}' for m in ensemble.MEMBERS}
    observations={k:{'status':'validated_terminal','outcome':'successful'} for k in refs.values()}
    return refs,observations

def test_execute_equal_mode_checks_roles_and_writes_compact_outcomes(tmp_path):
    runtime=tmp_path/'runtime'; (runtime/'cache/roles').mkdir(parents=True); (runtime/'artifacts').mkdir()
    fit_ids=np.arange(70,dtype=np.int64); tune_ids=np.arange(100,107,dtype=np.int64); cal_ids=np.arange(200,209,dtype=np.int64); test_ids=np.arange(300,307,dtype=np.int64)
    def features(n): return np.arange(n*6,dtype=float).reshape(n,6)/10
    np.savez_compressed(runtime/'cache/roles/rep_1.npz',fit_ids=fit_ids,X_tune=features(7),y_tune=np.arange(7,dtype=np.int8),tuning_ids=tune_ids,X_cal=features(9),y_cal=np.zeros(9,dtype=np.int8),calibration_ids=cal_ids)
    np.savez_compressed(runtime/'cache/test.npz',X=features(7),y=np.arange(7,dtype=np.int8),ids=test_ids)
    fit_hash=hashlib.sha256(np.ascontiguousarray(fit_ids).tobytes()).hexdigest()
    members={}
    for i,name in enumerate(ensemble.MEMBERS):
        key=f'fit/{name}'; d=runtime/'artifacts'/key; d.mkdir(parents=True)
        joblib.dump({'model':FixedPosterior(i),'imputer':Identity(),'scaler':Identity(),'method':name,'training_ids_sha256':fit_hash},d/'pipeline.joblib')
        members[name]=key
    refs,observations=member_reference_gate()
    task={'key':'e6/rep_1/equal','kind':'ensemble','rep':1,'mode':'equal','members':members,'member_evaluations':refs,'member_evaluation_dependency_observations':observations}
    result=ensemble.execute(task,runtime)
    assert result['status']=='success'
    assert result['evaluation']['weights']==[.2]*5
    assert result['evaluation']['calibration_n']==9
    out=runtime/'artifacts/e6/rep_1/equal'
    for name in ('evaluation.json','frozen_weights.json','tuning_posteriors.npz','test_outcomes.npz'):
        assert (out/name).is_file()
    with np.load(out/'test_outcomes.npz',allow_pickle=False) as z:
        assert {'sample_id','y_pred','set_mask','covered','set_size','y_true'}<=set(z.files)
        assert np.array_equal(z['sample_id'],test_ids)
    # Re-executing a mode must reuse the atomically written shared member-score cache.
    result2=ensemble.execute({**task,'key':'e6/rep_1/learned','mode':'learned','weight_search':{'seed':991,'dirichlet_candidates':30,'maximum_candidates':300}},runtime)
    assert result2['status']=='success'
    assert all(result2['evaluation']['phase_times_seconds'][f'{stage}_cache_hit'] is True for stage in ('tune','cal','test'))
    learned_out=runtime/'artifacts/e6/rep_1/learned'
    assert (learned_out/'candidate_ledger.json').is_file()
    ledger=json.loads((learned_out/'candidate_ledger.json').read_text())
    assert 6 <= ledger['candidate_count'] <= 300
    assert ledger['seed']==991
    assert json.loads((learned_out/'frozen_weights.json').read_text())['weight_search_seed']==991
    assert sum(result2['evaluation']['weights'])==pytest.approx(1.0)
    assert result2['evaluation']['class_order']==list(range(7))

def test_missing_member_is_unavailable_not_a_partial_ensemble():
    refs,observations=member_reference_gate()
    result=ensemble.execute({'key':'e6/missing','rep':1,'mode':'equal','members':{},'member_evaluations':refs,'member_evaluation_dependency_observations':observations},Path('/tmp/unused-runtime'))
    assert result['status']=='unavailable_dependency'
    assert set(result['missing_members'])==set(ensemble.MEMBERS)
