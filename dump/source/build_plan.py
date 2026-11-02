#!/usr/bin/env python3
"""Build and freeze the no-fit E3-E6 task DAG for runtime_20261025.

This builder only reads prior evidence and emits plans/selection provenance. It never fits,
generates, evaluates, or starts a queue. A frozen plan is immutable on subsequent runs.
"""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, sys
from pathlib import Path
import numpy as np

ROOT = Path('/home/ubuntu/lamost_e1_migration_20261023')
RUNTIME = ROOT / 'runtime_20261025'
PROJECT = ROOT / 'project'
E1 = PROJECT / 'benchmark/results/e1'
E2 = ROOT / 'e2_20261024'
MANIFESTS = RUNTIME / 'manifests'
PLAN_PATH = MANIFESTS / 'tasks.json'
METHODS = ['gaussian_nb','shared_diagonal','lda','qda','gmm','copula','arf','kde','chow_liu','logistic','linear_svm','rbf_svm','knn','cart','random_forest','extra_trees','hist_gb']
GENERATORS = ['gmm','copula','arf','kde','chow_liu']
LEARNERS = ['logistic','random_forest','hist_gb']
LABELS = ['A','F','G','K','M','GALAXY','QSO']
LABEL_INDEX = {name:i for i,name in enumerate(LABELS)}
BASE_SEED = 271828
POLICY = {'max_workers':2,'worker_rss_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'nested_threads':1,'bootstrap':False}

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def load(path):
    with open(path,encoding='utf-8') as f: return json.load(f)
def stable_seed(*bits):
    raw='|'.join(map(str,(BASE_SEED,*bits))).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:4],'big') & 0x7fffffff

def audit_inputs():
    files = [RUNTIME/'manifests/startup_audit.json', RUNTIME/'cache/cache_manifest.json', PROJECT/'benchmark/protocol_source.txt', PROJECT/'benchmark/dependencies.freeze.txt', PROJECT/'benchmark/results/master_run_config.json', PROJECT/'benchmark/results/e1_report_validated_no_bootstrap.json', E2/'E2_CURRENT_REPORT.md', E2/'E2_RECONSTRUCTION_AMENDMENT.md', E2/'E2_missing_primary_42.csv', E2/'E2_INTEGRITY_AUDIT.json']
    return {str(p.relative_to(ROOT)):sha(p) for p in files if p.is_file()}

def e1_selection(rep, method):
    p=E1/f'rep_{rep}/n_100000/{method}/complete.json'
    if not p.is_file(): return None
    try: d=load(p)
    except Exception: return None
    if d.get('status')!='complete' or not isinstance(d.get('selected_params'),dict): return None
    return {'params':d['selected_params'],'path':str(p),'sha256':sha(p),'status':d.get('status'),'tuning_score':d.get('best_tuning_balanced_accuracy')}

def import_selection(rep, method, record):
    dest=MANIFESTS/'imported_selections'/'e1_100000'/f'rep_{rep}'/method
    dest.mkdir(parents=True,exist_ok=True)
    payload={'selected_params':record['params'],'provenance':'frozen E1 selected parameters; classifier refit belongs to this later experiment','source_path':record['path'],'source_sha256':record['sha256'],'source_status':record['status'],'source_tuning_balanced_accuracy':record.get('tuning_score'),'imported_utc_policy':'source evidence timestamp retained in source file; plan generation time is in plan metadata','bootstrap':False}
    path=dest/'selection.json'
    raw=(json.dumps(payload,sort_keys=True,indent=2)+'\n').encode()
    if path.exists() and path.read_bytes()!=raw: raise RuntimeError(f'refusing to overwrite imported selection: {path}')
    if not path.exists(): path.write_bytes(raw)
    return str(dest)

def e2_reuse(rep, method):
    base=E2/f'reconstruction/n_100000/rep_{rep}/{method}'
    pipe=base/'pipeline.joblib'; rec=base/'reconstruction.json'; gate=base/'test_reproduction_gate.json'
    if not all(p.is_file() for p in (pipe,rec,gate)): return None
    try: r=load(rec); g=load(gate)
    except Exception: return None
    cache=load(RUNTIME/'cache/cache_manifest.json')
    expected=cache['roles'][str(rep)]['source_sha256']
    good=(r.get('status')=='reconstructed_tuning_checked' and r.get('budget')==100000 and r.get('repetition')==rep and r.get('method')==method and r.get('fit_rows')==80000 and r.get('tuning_rows')==10000 and r.get('calibration_rows')==10000 and r.get('source_role_sha256')==expected and r.get('same_selected_params') is True and r.get('reconstructed_not_original') is True and r.get('reconstructed_pipeline_sha256')==sha(pipe) and g.get('status') in ('reproduced_original_test_balanced_accuracy','test_balanced_accuracy_difference','classification_not_reproduced'))
    if not good: return None
    # Reuse only when the actual reconstructed artifact still exposes a matching E1 selection and fit-only preprocessing.
    try:
        import joblib, numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        sys.path.insert(0,str(PROJECT))
        fitted=joblib.load(pipe)
        original=load(E1/f'rep_{rep}/n_100000/{method}/complete.json')
        role=np.load(RUNTIME/'cache/roles'/f'rep_{rep}.npz',allow_pickle=False)
        required={'model','imputer','scaler','params','seed'}
        if not isinstance(fitted,dict) or not required.issubset(fitted): return None
        if fitted.get('seed')!=r.get('fit_seed') or fitted.get('params')!=original.get('selected_params'): return None
        if len(role['X_fit'])!=80000 or len(role['X_tune'])!=10000 or len(role['X_cal'])!=10000: return None
        imp=SimpleImputer(strategy='median',keep_empty_features=True); transformed=imp.fit_transform(np.asarray(role['X_fit'],float))
        scaler=StandardScaler(); scaler.fit(transformed)
        if not np.allclose(fitted['imputer'].statistics_,imp.statistics_,rtol=0,atol=1e-12,equal_nan=True): return None
        if not np.allclose(fitted['scaler'].mean_,scaler.mean_,rtol=0,atol=1e-12,equal_nan=True): return None
        if not np.allclose(fitted['scaler'].scale_,scaler.scale_,rtol=0,atol=1e-12,equal_nan=True): return None
    except Exception: return None
    return {'path':str(pipe),'provenance':'E2 reconstructed fit; exact matching role-membership hash, selected parameters and reconstructed pipeline hash validated; not the omitted original E1 pipeline','reconstruction':str(rec),'reconstruction_sha256':sha(rec),'gate':str(gate),'gate_sha256':sha(gate),'gate_status':g.get('status'),'source_role_sha256':expected,'fit_seed':r.get('fit_seed'),'selected_params_match':True,'preprocessing_note':'actual imputer medians and scaler mean/scale match recomputation on the exact cached 80k fitting rows (absolute tolerance 1e-12); 10k tuning and 10k calibration counts validated; no test rows in preprocessing'}

TASKS=[]; BYKEY={}
def add(key,kind,exp,rep,*,method=None,condition=None,route=None,target_class=None,ratio=None,treatment=None,mechanism=None,rate=None,generator=None,scientific=False,deps=(),**extra):
    if key in BYKEY: raise ValueError('duplicate task '+key)
    rec={'key':key,'kind':kind,'experiment':exp,'rep':rep,'method':method,'condition':condition,'route':route,'target_class':target_class,'ratio':ratio,'treatment':treatment,'mechanism':mechanism,'rate':rate,'generator':generator,'scientific_case':bool(scientific),'dependencies':list(dict.fromkeys([x for x in deps if x])),'artifact_dir':f'artifacts/{key}'}
    rec.update(extra); BYKEY[key]=rec; TASKS.append(rec); return key

def fit(key,exp,rep,method,*,condition=None,route=None,train_key=None,selection_key=None,selection_source=None,reuse=None,source_metadata=None,seed=None,optimizer_seed=None,trials=None,scientific=False,dependencies=(),**extra):
    deps=list(dependencies)
    if train_key: deps.append(train_key)
    if selection_key: deps.append(selection_key)
    args={'train_key':train_key,'selection_key':selection_key,'selection_source':selection_source,'seed':seed if seed is not None else stable_seed(exp,rep,method,condition,'fit'),'optimizer_seed':optimizer_seed if optimizer_seed is not None else stable_seed(exp,rep,method,condition,'optimizer'),'trials':trials if trials is not None else (5 if method in ('arf','kde','knn','rbf_svm') else 10),'selection_mode':'fixed' if (selection_key or selection_source) else 'tune'}
    if reuse:
        role=np.load(RUNTIME/'cache/roles'/f'rep_{rep}.npz',allow_pickle=False)
        idhash=hashlib.sha256(np.ascontiguousarray(role['fit_ids']).tobytes()).hexdigest()
        args.update({'reuse_pipeline':reuse['path'],'source_metadata':reuse,'source_sha256':sha(reuse['path']),
                     'training_ids_sha256':idhash,'training_counts':CACHE['roles'][str(rep)]['fit_counts'],
                     'training_rows':80000,'role_membership_sha256':CACHE['roles'][str(rep)]['source_sha256']})
    return add(key,'fit',exp,rep,method=method,condition=condition,route=route,scientific=scientific,deps=deps,**args,**extra)
def ev(key,exp,rep,fitkey,*,method=None,condition=None,route='direct',scientific=True,**extra):
    return add(key,'eval',exp,rep,method=method,condition=condition,route=route,scientific=scientific,deps=[fitkey],fit_key=fitkey,**extra)
def gen(key,exp,rep,fitkey,*,n_rows=None,condition=None,target_class=None,added_count=None,cohort_key=None,generator=None,scientific=False,seed=None,**extra):
    deps=[fitkey]
    if cohort_key: deps.append(cohort_key)
    return add(key,'generate',exp,rep,condition=condition,generator=generator,scientific=scientific,deps=deps,fit_key=fitkey,n_rows=n_rows,target_class=target_class,added_count=added_count,cohort_key=cohort_key,seed=(seed if seed is not None else stable_seed(exp,rep,condition,generator,'generate')),**extra)
def alias(key,exp,rep,source,*,method=None,condition=None,route='direct',scientific=True,**extra):
    return add(key,'alias',exp,rep,method=method,condition=condition,route=route,scientific=scientific,deps=[source],source_key=source,**extra)
def eval_key(exp,rep,method,route='direct',condition=None):
    suffix=f'/{condition}' if condition else ''
    return f'{exp}/rep_{rep}/eval/{route}/{method}{suffix}'
def fit_key(exp,rep,method,route=None,condition=None):
    pieces=[exp,f'rep_{rep}','fit']
    if route: pieces.append(route)
    pieces.append(method)
    if condition: pieces.append(condition)
    return '/'.join(pieces)

# Fixed baseline evidence and exact E2 reuse validation.
INPUTS=audit_inputs(); CACHE=load(RUNTIME/'cache/cache_manifest.json')
E2_REUSES={(r,m):e2_reuse(r,m) for r in (1,2,3) for m in ('gmm','copula','chow_liu')}
E1_IMPORTS={}
for r in (1,2,3):
    for m in METHODS:
        x=e1_selection(r,m)
        if x: E1_IMPORTS[(r,m)]=import_selection(r,m,x)

def exp3():
    learners=LEARNERS
    # Generator fits and direct Bayes evaluations; only exact validated E2 matches are reused.
    for r in (1,2,3):
        for g in GENERATORS:
            fk=fit_key('e3',r,g)
            reuse=E2_REUSES.get((r,g))
            fit(fk,3,r,g,route='generator',reuse=reuse,source_metadata=reuse,seed=(reuse or {}).get('fit_seed',stable_seed(3,r,g,'fit')),optimizer_seed=stable_seed(3,r,g,'optimizer'),trials=(5 if g in ('arf','kde') else 10))
            ev(eval_key('e3',r,g,'direct'),3,r,fk,method=g,route='direct',generator=g)
            gen(f'e3/rep_{r}/generate/{g}',3,r,fk,n_rows=400000,generator=g,condition='primary',label_allocation='largest_remainder_from_real_fit_proportions',same_dataset_for_all_learners=True)
        # Shared real-only baselines.
        for l in learners:
            fk=fit_key('e3',r,l,'real')
            fit(fk,3,r,l,route='real',trials=10)
            ev(eval_key('e3',r,l,'real'),3,r,fk,method=l,route='real')
        # One synthetic-only fit per generator x learner; generated data shared.
        for g in GENERATORS:
            for l in learners:
                fk=fit_key('e3',r,l,'synthetic',g)
                gk=f'e3/rep_{r}/generate/{g}'
                fit(fk,3,r,l,route='synthetic',condition=g,train_key=gk,trials=10,dependencies=[gk],sample_count=400000,generator=g)
                ev(eval_key('e3',r,l,'synthetic',g),3,r,fk,method=l,route='synthetic',condition=g,generator=g)

def e4_control_source(r,m):
    # Reuse E3's verified clean generator/real-learner fits where the exact cohort matches.
    if m in GENERATORS: return fit_key('e3',r,m)
    if m in LEARNERS: return fit_key('e3',r,m,'real')
    return None

def restoration_count(rep, target, ratio):
    counts=CACHE['roles'][str(rep)]['fit_counts']; N=80000; orig=int(counts[target]); n=int(math.floor(ratio*orig+0.5)); den=N-orig; num=N*(orig-n)
    return 0 if num<=0 else (2*num+den)//(2*den)

def exp4():
    altered=[]
    for r in (1,2,3):
        # Control outcomes share compatible E3 generator/real learner fits; remaining clean controls are E4-owned.
        for m in METHODS:
            src=e4_control_source(r,m)
            ek=eval_key('e4',r,m,'direct','control')
            if src:
                se=eval_key('e3',r,m,'direct') if m in GENERATORS else eval_key('e3',r,m,'real')
                alias(ek,4,r,se,method=m,condition='control',route='direct',comparison_label='unchanged_control_shared_fit')
            else:
                old=E1_IMPORTS.get((r,m)); fk=fit_key('e4',r,m,'direct','control')
                fit(fk,4,r,m,route='direct',condition='control',selection_source=old,
                    seed=stable_seed(4,r,m,'control','fit'),optimizer_seed=stable_seed(4,r,m,'control','opt'),
                    trials=(0 if old else None),selection_policy='import_successful_E1_params_or_tune_if_unavailable')
                ev(ek,4,r,fk,method=m,condition='control',route='direct')
        for cls in LABELS:
            for ratio,tag in ((0.5,'half'),(0.1,'tenth')):
                cond=f'{cls}_{tag}'; ck=f'e4/rep_{r}/cohort/{cond}'; cidx=LABEL_INDEX[cls]
                add(ck,'e4_cohort',4,r,condition=cond,target_class=cidx,target_label=cls,ratio=ratio,
                    scientific=False,deps=[],seed=stable_seed(4,r,'cohort'),membership_policy='reserve_tuning_calibration_before_alteration',
                    nested_target_subsets=True,shared_other_class_permutations=True,population_evaluation=True,control_fit_size=80000)
                altered.append((r,cls,ratio,tag,cond,ck))
                # The 17 direct methods are tuned on this exact altered fit cohort and the frozen tuning role.
                for m in METHODS:
                    fk=fit_key('e4',r,m,'direct',cond)
                    fit(fk,4,r,m,route='direct',condition=cond,train_key=ck,seed=stable_seed(4,r,m,cond,'fit'),
                        optimizer_seed=stable_seed(4,r,m,cond,'opt'),selection_policy='tune_on_matching_altered_cohort')
                    ev(eval_key('e4',r,m,'direct',cond),4,r,fk,method=m,condition=cond,route='direct',target_class=cidx,target_label=cls,ratio=ratio)
                # One generator fit/output per generator and condition, shared among all three learners.
                generated={}
                for g in GENERATORS:
                    gf=fit_key('e4',r,g,'direct',cond); gk=f'e4/rep_{r}/generate/{cond}/{g}'
                    gen(gk,4,r,gf,generator=g,condition=cond,target_class=cidx,added_count=restoration_count(r,cidx,ratio),
                        cohort_key=ck,restored_share='original_target_share',shared_across_learners=True)
                    ak=f'e4/rep_{r}/append/{cond}/{g}'
                    add(ak,'e4_append',4,r,condition=cond,target_class=cidx,target_label=cls,ratio=ratio,treatment='generated',generator=g,
                        scientific=False,deps=[ck,gk],cohort_key=ck,generated_key=gk,identical_target_add_count_across_treatments=True)
                    generated[g]=ak
                # Base rebalancing treatments are materialized once per altered cohort, then shared by learner fits.
                treatment_keys={}
                for tr in ('weighted','ros','smote'):
                    tk=f'e4/rep_{r}/treatment/{cond}/{tr}'
                    add(tk,'e4_treatment',4,r,condition=cond,target_class=cidx,target_label=cls,ratio=ratio,treatment=tr,
                        scientific=False,deps=[ck],cohort_key=ck,weighting_target='original_share',same_final_class_histogram=True,
                        smote_neighbor_rule='min(5,n_target-1)',unsupported_if_target_rows_lt=2,seed=stable_seed(4,r,cond,tr,'treatment'))
                    treatment_keys[tr]=tk
                for l in LEARNERS:
                    treatment_map={**treatment_keys,**{f'generated_{g}':ak for g,ak in generated.items()}}
                    for tr,train_key in treatment_map.items():
                        g=tr[len('generated_'):] if tr.startswith('generated_') else None
                        fk=fit_key('e4',r,l,'treatment',cond+'_'+tr)
                        fit(fk,4,r,l,route='treatment',condition=cond+'_'+tr,train_key=train_key,
                            seed=stable_seed(4,r,l,cond,tr,'fit'),optimizer_seed=stable_seed(4,r,l,cond,tr,'opt'),trials=10,
                            selection_policy='tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget',
                            treatment=tr,generator=g,clean_control_key=e4_control_source(r,l) or fit_key('e4',r,l,'direct','control'))
                        ev(eval_key('e4',r,l,'treatment',cond+'_'+tr),4,r,fk,method=l,condition=cond+'_'+tr,route='treatment',
                           target_class=cidx,target_label=cls,ratio=ratio,treatment=tr,generator=g)
    return altered

def exp5():
    mechanisms=('feature_noise','missingness','label_noise'); rates=(0.05,0.10,0.20)
    for r in (1,2,3):
        # Clean control aliases: 17 direct + 15 synthetic routes per repetition.
        for m in METHODS:
            src=eval_key('e4',r,m,'direct','control')
            alias(f'e5/rep_{r}/eval/direct/{m}/clean',5,r,src,method=m,condition='clean',route='direct',comparison_label='clean_control_alias')
        for g in GENERATORS:
            for l in LEARNERS:
                src=eval_key('e3',r,l,'synthetic',g)
                alias(f'e5/rep_{r}/eval/synthetic/{g}/{l}/clean',5,r,src,method=l,condition='clean',route='synthetic',generator=g,comparison_label='clean_control_alias')
        for mech in mechanisms:
            for rate in rates:
                tag=str(int(rate*100)).zfill(2); cond=f'{mech}_{tag}'
                ck=f'e5/rep_{r}/corruption/{cond}'
                add(ck,'e5_corruption',5,r,condition=cond,mechanism=mech,rate=rate,scientific=False,seed=stable_seed(5,r,mech,'corruption_mask'),fit_rows=80000,nested_across_rates=True,shared_across_methods=True,tuning_calibration_test_clean=True,feature_noise_scale='clean_fitting_IQR/1.349_with_protocol_fallbacks',missing_indicator=False,label_noise='uniform_among_other_six_and_force_change')
                # All direct methods, including flexible generators, are refit on the corrupted fit cohort with clean-frozen config.
                for m in METHODS:
                    sel=(e4_control_source(r,m) or fit_key('e4',r,m,'direct','control'))
                    fk=fit_key('e5',r,m,'direct',cond)
                    fit(fk,5,r,m,route='direct',condition=cond,train_key=ck,selection_key=sel,seed=BYKEY[sel]['seed'],optimizer_seed=stable_seed(5,r,m,cond,'opt'),trials=0,selection_policy='frozen_clean_selected_params_no_retuning',mechanism=mech,rate=rate)
                    ev(eval_key('e5',r,m,'direct',cond),5,r,fk,method=m,condition=cond,route='direct',mechanism=mech,rate=rate)
                # The same corrupted generator fits produce shared synthetic data; all 3 learners use frozen E3 synthetic configs.
                for g in GENERATORS:
                    gf=fit_key('e5',r,g,'direct',cond)
                    gk=f'e5/rep_{r}/generate/{cond}/{g}'
                    gen(gk,5,r,gf,n_rows=400000,generator=g,condition=cond,seed=BYKEY[f'e3/rep_{r}/generate/{g}']['seed'],shared_across_learners=True,mechanism=mech,rate=rate)
                    for l in LEARNERS:
                        synfit=fit_key('e5',r,l,'synthetic',cond+'_'+g)
                        clean_syn=fit_key('e3',r,l,'synthetic',g)
                        fit(synfit,5,r,l,route='synthetic',condition=cond+'_'+g,train_key=gk,selection_key=clean_syn,seed=BYKEY[clean_syn]['seed'],optimizer_seed=stable_seed(5,r,l,cond,g,'synopt'),trials=0,selection_policy='frozen_clean_selected_params_no_retuning',sample_count=400000,generator=g,mechanism=mech,rate=rate)
                        ev(eval_key('e5',r,l,'synthetic',cond+'_'+g),5,r,synfit,method=l,condition=cond+'_'+g,route='synthetic',generator=g,mechanism=mech,rate=rate)

def exp6():
    for r in (1,2,3):
        members={g:fit_key('e3',r,g) for g in GENERATORS}
        for g in GENERATORS:
            alias(f'e6/rep_{r}/eval/member/{g}',6,r,eval_key('e3',r,g,'direct'),method=g,route='member',condition='member_reference',generator=g,comparison_label='E3_direct_member_alias')
        for mode in ('equal','learned'):
            key=f'e6/rep_{r}/ensemble/{mode}'
            deps=list(members.values())
            add(key,'ensemble',6,r,condition=mode,route='posterior_ensemble',scientific=True,deps=deps,members=members,mode=mode,member_evaluations={g:eval_key('e3',r,g,'direct') for g in GENERATORS},seed=stable_seed(6,r,'dirichlet')-r,weight_search={'equal_weights':[0.2]*5,'vertices':5,'dirichlet_candidates':1000,'seed':stable_seed(6,r,'dirichlet'),'refine_top':10,'pairwise_transfers':[0.10,0.05,0.01],'maximum_candidates':2000,'tie_break':['euclidean_distance_to_equal','deterministic_order']},selection_metric='tuning_balanced_accuracy',global_weights_only=True,posterior_average=True,requires_all_five=True,freeze_weights_before_calibration_test=True)

def validate_contract():
    by=BYKEY
    e4_treat=[t for t in TASKS if t['experiment']==4 and t['kind']=='e4_treatment']
    e4_append=[t for t in TASKS if t['experiment']==4 and t['kind']=='e4_append']
    e4_cohort=[t for t in TASKS if t['experiment']==4 and t['kind']=='e4_cohort']
    if (len(e4_cohort),len(e4_treat),len(e4_append))!=(42,126,210): raise RuntimeError(f'E4 helper node counts invalid: {len(e4_cohort)}/{len(e4_treat)}/{len(e4_append)}')
    if {t.get('treatment') for t in e4_treat}!={'weighted','ros','smote'}: raise RuntimeError('E4 treatment labels mismatch cohorts.execute')
    for t in TASKS:
        if t['kind'] in ('e4_cohort','e4_treatment','e4_append') or (t['experiment']==4 and t['kind']=='generate'):
            if not isinstance(t.get('target_class'),int) or t['target_class'] not in range(7): raise RuntimeError(f'E4 numeric target_class invalid: {t["key"]}')
        if t['kind']=='generate' and t['experiment']==4:
            if not t.get('cohort_key') or not isinstance(t.get('added_count'),int) or t.get('n_rows') is not None: raise RuntimeError(f'E4 generated target contract invalid: {t["key"]}')
        if t['kind']=='e4_append' and (not t.get('cohort_key') or not t.get('generated_key')): raise RuntimeError('E4 append requires shared cohort/generated keys')
        if t['kind']=='fit' and t.get('train_key'):
            src=by[t['train_key']]
            if src['kind'] not in ('generate','e4_cohort','e4_treatment','e4_append','e5_corruption'): raise RuntimeError(f'unsupported train_key source {t["key"]}->{src["kind"]}')
        if t['kind']=='fit' and t.get('selection_source'):
            if not isinstance(t['selection_source'],str) or not (Path(t['selection_source'])/'selection.json').is_file(): raise RuntimeError(f'selection_source must be directory with selection.json: {t["key"]}')
        if t['kind']=='fit' and t.get('selection_key') and by[t['selection_key']]['kind']!='fit': raise RuntimeError(f'selection_key must reference fit task: {t["key"]}')
        if t['experiment']==4 and t['kind']=='fit' and t.get('route')=='treatment':
            if t.get('selection_key') is not None or t.get('trials')!=10: raise RuntimeError(f'E4 treatment must retune with 10 trials: {t["key"]}')
        if t['experiment']==3 and t['kind']=='fit' and t.get('route') in ('real','synthetic') and t.get('trials')!=10: raise RuntimeError(f'E3 real/synthetic budget mismatch: {t["key"]}')
        if t['experiment']==5 and t['kind']=='fit':
            sel=t.get('selection_key');
            if not sel or t.get('seed')!=by[sel].get('seed'): raise RuntimeError(f'E5 refit seed/config pairing invalid: {t["key"]}')
        if t['kind']=='ensemble':
            if int(t.get('seed',-100000))+int(t['rep'])!=int(t['weight_search']['seed']): raise RuntimeError('E6 ensemble task seed must align with weight search seed')
    for t in e4_append:
        if t.get('method') is not None: raise RuntimeError('E4 append must be generated once shared across learners')
    return {'e4_cohorts':len(e4_cohort),'e4_base_treatments':len(e4_treat),'e4_shared_generated_appends':len(e4_append),'numeric_target_ids_validated':True,'train_and_selection_edges_validated':True,'e5_clean_seed_inheritance_validated':True,'e6_search_seed_alignment_validated':True}
def main():
    MANIFESTS.mkdir(parents=True,exist_ok=True)
    exp3(); altered=exp4(); exp5(); exp6()
    counts={}
    for e in (3,4,5,6): counts[f'e{e}']=sum(t['experiment']==e and t['scientific_case'] for t in TASKS)
    expected={'e3':69,'e4':1773,'e5':960,'e6':21}
    if counts!=expected: raise RuntimeError(f'scientific outcome count mismatch: {counts} != {expected}')
    task_keys=set(BYKEY)
    contract_audit=validate_contract()
    for t in TASKS:
        missing=[d for d in t['dependencies'] if d not in task_keys]
        if missing: raise RuntimeError(f'{t["key"]} has missing dependencies {missing[:3]}')
        if t.get('kind')=='fit' and t.get('selection_key') and t['selection_key'] not in task_keys: raise RuntimeError('missing selection dependency')
    if '--check-only' in sys.argv:
        print(json.dumps({'status':'contract_check_only','tasks':len(TASKS),'scientific_cases':counts,'contract_audit':contract_audit,'e2_reuse_audit_count':sum(v is not None for v in E2_REUSES.values())},indent=2)); return
    # All planned tasks use a durable prospective policy and explicitly state prior test exposure.
    plan={'schema_version':'lamost-e3-e6-dag/1.1','created_utc_observation':'recorded by caller after generation','root':str(ROOT),'bootstrap':False,'policy':POLICY,'test_information_history':{'E1_E2_test_outcomes_already_observed':True,'remaining_plan_frozen_before_new_e3_e6_test_evaluations':True},'implementation_defaults':{'development_budget_rows':100000,'repetitions':3,'fit_tune_calibration_rows':[80000,10000,10000],'test_rows':500000,'class_order':LABELS,'feature_order':CACHE['features'],'nominal_conformal_coverage':0.90,'conformal_quantile_rule':'frozen benchmark helper','e3_synthetic_rows':400000,'e4_conditions':'one unchanged control and seven target classes x half-share / one-tenth-share','e4_control_parameters':'reuse exact compatible E3 generator/real-learner controls; for other clean controls import successful frozen E1 selected parameters and refit in E4, or tune an E4-owned control where E1 failed; altered direct methods tune on each altered fitting cohort; each restoration treatment is separately tuned with the same learner-specific domain, clean tuning rows, and fixed 10-trial budget','e4_oversampling':'restore target to original share; oversampling, SMOTE, generated methods receive same added target count and final histogram','e4_smote_neighbors':'min(5,n_target-1), unsupported below two target rows','e4_treatment_materialization':'one shared weighted/ros/smote cohort artifact per altered condition; one generated append per generator/condition shared across learners','e5_corruption':'only fitting rows; clean tuning/calibration/test; clean-selected hyperparameters frozen and each refit inherits the matching clean route seed','e6_weight_selection':'one global simplex vector per repetition, tuning balanced accuracy only'},'input_hashes':INPUTS,'cache_manifest_sha256':sha(RUNTIME/'cache/cache_manifest.json'),'role_membership_hashes':{f'rep_{r}':CACHE['roles'][str(r)]['source_sha256'] for r in (1,2,3)},'e2_reuse_audit':{f'rep_{r}/{m}':E2_REUSES[(r,m)] for r,m in E2_REUSES},'e1_imported_selection_count':len(E1_IMPORTS),'e1_imported_selection_sources':{f'rep_{r}/{m}':{'path':str(E1/f'rep_{r}/n_100000/{m}/complete.json'),'sha256':sha(E1/f'rep_{r}/n_100000/{m}/complete.json')} for r,m in E1_IMPORTS},'contract_audit':contract_audit,'counts':{'tasks':len(TASKS),'scientific_cases':counts,'planned_e4_altered_cohorts':len(altered),'e4_logical_comparison_rows_including_untreated_views':1899,'e5_clean_aliases':96,'e6_member_aliases':15},'tasks':TASKS}
    if PLAN_PATH.exists():
        prev=load(PLAN_PATH)
        if prev.get('supersedes_plan_sha256'): plan['supersedes_plan_sha256']=prev['supersedes_plan_sha256']
    canonical=json.dumps(plan,sort_keys=True,separators=(',',':')).encode(); plan['plan_sha256']=hashlib.sha256(canonical).hexdigest()
    raw=(json.dumps(plan,indent=2,sort_keys=True)+'\n').encode()
    superseded_hash=None
    if PLAN_PATH.exists():
        old=load(PLAN_PATH)
        if old.get('plan_sha256')==plan['plan_sha256']:
            print(json.dumps({'status':'existing_plan_validated','plan_sha256':old['plan_sha256'],'counts':old.get('counts')},indent=2)); return
        if '--supersede-prequeue' not in sys.argv:
            raise RuntimeError(f'frozen plan already exists with different hash ({old.get("plan_sha256")}); refusing overwrite without explicit prequeue supersession')
        if (RUNTIME/'registry.json').exists(): raise RuntimeError('refusing plan supersession after controller registry exists')
        active=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit(): continue
            try: argv=(proc/'cmdline').read_bytes().decode(errors='ignore').split('\0')
            except (OSError,ProcessLookupError): continue
            if any(a.endswith('/source/controller.py') or a.endswith('/source/phase_worker.py') for a in argv): active.append((proc.name,argv[:3]))
        if active: raise RuntimeError(f'refusing plan supersession while runtime worker/controller process exists: {active[:3]}')
        superseded_hash=old.get('plan_sha256')
        plan['supersedes_plan_sha256']=superseded_hash
        canonical=json.dumps({k:v for k,v in plan.items() if k!='plan_sha256'},sort_keys=True,separators=(',',':')).encode()
        plan['plan_sha256']=hashlib.sha256(canonical).hexdigest()
        raw=(json.dumps(plan,indent=2,sort_keys=True)+'\n').encode()
        archive=MANIFESTS/f'tasks_superseded_prequeue_{superseded_hash[:12]}.json'
        if archive.exists() and sha(archive)!=sha(PLAN_PATH): raise RuntimeError('superseded plan archive path already exists with different bytes')
        if not archive.exists(): shutil.copy2(PLAN_PATH,archive)
    tmp=PLAN_PATH.with_suffix('.json.tmp'); tmp.write_bytes(raw); os.replace(tmp,PLAN_PATH)
    if superseded_hash:
        amend=MANIFESTS/'plan_amendments.json'
        existing=load(amend) if amend.exists() else {'amendments':[]}
        existing['amendments'].append({'supersedes_plan_sha256':superseded_hash,'replacement_plan_sha256':plan['plan_sha256'],'reason':'pre-execution task-contract corrections: retain validated E2 reconstructed provenance despite disclosed test-score mismatch when exact role/parameter/seed/preprocessing/model hashes pass; use integer class IDs and ROS treatment label; share E4 treatment data once per cohort/generator with separate 10-trial treatment tuning; pair E5 refit seeds to clean configurations; align E6 task/search seeds','scientific_jobs_started':False})
        amend.write_text(json.dumps(existing,indent=2,sort_keys=True)+'\n')
    summary={k:v for k,v in plan.items() if k!='tasks'}
    sp=MANIFESTS/'plan_summary.json'; sp.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'frozen_no_fit_plan_created','plan_path':str(PLAN_PATH),'plan_sha256':plan['plan_sha256'],'task_count':len(TASKS),'scientific_case_counts':counts,'e2_exact_role_reuse_count':sum(v is not None for v in E2_REUSES.values()),'e1_selected_parameter_imports':len(E1_IMPORTS)},indent=2))

if __name__=='__main__': main()


















