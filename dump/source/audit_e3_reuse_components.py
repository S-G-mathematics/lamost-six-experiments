#!/usr/bin/env python3
"""Bounded read-only component comparison for the nine E2->E3 reused GMM/copula/Chow-Liu fits.
No fit, prediction, sampling or artifact writes. Pipeline files are loaded only if resource/code bounds pass.
"""
from __future__ import annotations
import csv, datetime, hashlib, importlib.metadata, json, math, os, sys
from pathlib import Path
os.environ.update({'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'})

ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023')
# Pickle references use the migrated project's benchmark package; import modules only.
sys.path.insert(0,str(ROOT/'project'))
R=ROOT/'runtime_20261025'
PLAN=R/'manifests/tasks.json'
FREEZE=R/'manifests/freeze.json'
E1MASTER=ROOT/'project/benchmark/results/master_run_config.json'
DEPS=ROOT/'project/benchmark/dependencies.freeze.txt'
E2CSV=ROOT/'e2_20261024/E2_all_generators_270.csv'
CACHEMAN=R/'cache/cache_manifest.json'
OUTCSV=R/'reports/E3_REUSED_E2_PREDICTIVE_COMPONENTS.csv'
OUTDIR=R/'reports/engineering_audits'
EXPECTED_METHODS={'gmm','copula','chow_liu'}
MAX_FILE=32*1024*1024
MIN_AVAILABLE=12*1024**3

def sha_path(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def maybe_sha(p):
    p=Path(p)
    return sha_path(p) if p.is_file() else None
def readj(p):
    with Path(p).open(encoding='utf-8') as f:return json.load(f)
def utc():return datetime.datetime.now(datetime.timezone.utc)
def mem_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
    return 0
def typename(x):return f'{type(x).__module__}.{type(x).__qualname__}'
def norm(x,opaque,active,depth=0):
    if depth>80:
        opaque.append('depth_limit');return {'opaque':'depth_limit'}
    if x is None or isinstance(x,(str,bool,int)):
        return x
    if isinstance(x,float):
        if math.isnan(x):return {'float':'nan'}
        if math.isinf(x):return {'float':'inf' if x>0 else '-inf'}
        return {'float_hex':x.hex()}
    try:
        import numpy as np
        if isinstance(x,np.generic):return norm(x.item(),opaque,active,depth+1)
        if isinstance(x,np.dtype):return {'numpy_dtype':x.str,'name':x.name,'descr':x.descr}
        if isinstance(x,np.ndarray):
            if x.dtype.hasobject:
                return {'ndarray_object':{'shape':list(x.shape),'items':norm(x.tolist(),opaque,active,depth+1)}}
            a=np.ascontiguousarray(x)
            return {'ndarray':{'dtype':a.dtype.str,'shape':list(a.shape),'sha256':hashlib.sha256(a.view(np.uint8)).hexdigest()}}
    except ImportError:pass
    oid=id(x)
    if oid in active:return {'cycle':typename(x)}
    active.add(oid)
    try:
        if isinstance(x,dict):
            return {'dict':{str(k):norm(v,opaque,active,depth+1) for k,v in sorted(x.items(),key=lambda kv:str(kv[0]))}}
        if isinstance(x,(list,tuple)):
            return {('tuple' if isinstance(x,tuple) else 'list'):[norm(v,opaque,active,depth+1) for v in x]}
        if isinstance(x,(set,frozenset)):
            vals=[norm(v,opaque,active,depth+1) for v in x]
            vals.sort(key=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')))
            return {'set':vals}
        if isinstance(x,type):return {'class':f'{x.__module__}.{x.__qualname__}'}
        try:d=vars(x)
        except Exception:d=None
        if isinstance(d,dict):
            return {'object':typename(x),'attrs':norm(d,opaque,active,depth+1)}
        slots=getattr(type(x),'__slots__',())
        if isinstance(slots,str):slots=(slots,)
        if slots:
            vals={}
            for name in slots:
                if hasattr(x,name):
                    try:vals[name]=norm(object.__getattribute__(x,name),opaque,active,depth+1)
                    except Exception:opaque.append(f'{typename(x)}.{name}')
            return {'slotted_object':typename(x),'attrs':vals}
        opaque.append(typename(x))
        return {'opaque_type':typename(x)}
    finally:active.remove(oid)
def digest(x,opaque):
    tree=norm(x,opaque,set())
    return hashlib.sha256(json.dumps(tree,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def rolehash_from_task(t):return t.get('role_membership_sha256')
def job_versions():
    out={'python':sys.version.split()[0]}
    for pkg in ('joblib','numpy','scikit-learn','scipy'):
        try:out[pkg]=importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:out[pkg]=None
    return out
def get_class_signature(model):
    state=getattr(model,'__dict__',{})
    keys=('classes_','classes','class_ids_','label_order','class_order_','score_kind','priors_','priors')
    out={}
    for k in keys:
        if k in state:
            op=[];out[k]={'sha256':digest(state[k],op),'opaque':op}
    out['type']=typename(model)
    out['class_score_kind']=getattr(type(model),'score_kind',None)
    return out

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True); OUTCSV.parent.mkdir(parents=True,exist_ok=True)
    plan_doc=readj(PLAN); tasks=plan_doc.get('tasks',[])
    chosen=[t for t in tasks if t.get('experiment')==3 and t.get('kind')=='fit' and t.get('reuse_pipeline') and t.get('method') in EXPECTED_METHODS]
    freeze_doc=readj(FREEZE); master=readj(E1MASTER); cache_doc=readj(CACHEMAN)
    frozen_runtime=freeze_doc.get('source_sha256',{}).get('science.py')
    science_path=R/'source/science.py'; science_sha=maybe_sha(science_path)
    frozen_benchmark=master.get('benchmark_python_source_sha256',{}).get('models_flexible.py')
    model_source=ROOT/'project/benchmark/models_flexible.py'; model_source_sha=maybe_sha(model_source)
    code_gate={'runtime_science_expected_sha256':frozen_runtime,'runtime_science_actual_sha256':science_sha,'runtime_science_matches_freeze':bool(frozen_runtime and science_sha==frozen_runtime),'models_flexible_expected_sha256':frozen_benchmark,'models_flexible_actual_sha256':model_source_sha,'models_flexible_matches_frozen_E1':bool(frozen_benchmark and model_source_sha==frozen_benchmark)}
    # No pickle loading is allowed unless source/dependency code identity can be anchored.
    frozen_ok=code_gate['runtime_science_matches_freeze'] and code_gate['models_flexible_matches_frozen_E1']
    inputs={str(p) for p in (PLAN,FREEZE,E1MASTER,DEPS,E2CSV,CACHEMAN,science_path,model_source)}
    pairs=[]
    for t in chosen:
        md=t.get('source_metadata') or {}
        for k in ('path','reconstruction','gate'):
            if md.get(k):inputs.add(str(Path(md[k])))
        inputs.add(str(Path(t['reuse_pipeline'])))
        inputs.add(str(R/'cache/roles'/f"rep_{t['rep']}.npz"))
        base=R/'artifacts'/t['key']
        for rel in ('pipeline.joblib','fit_result.json','selection.json'):
            inputs.add(str(base/rel))
        inputs.add(str(R/'artifacts/e3'/f"rep_{t['rep']}"/'eval/direct'/t['method']/'evaluation.json'))
        pairs.append((t,base))
    before={p:maybe_sha(p) for p in sorted(inputs)}
    rows=[]; load_start_utc=utc().isoformat(); deferred=[]
    if not frozen_ok:
        deferred=['frozen-code identity gate failed; component unpickling not attempted']
    else:
        import numpy as np
        import joblib
        role_ids_sha={}; role_id_counts={}
        for rep in sorted({int(t['rep']) for t in chosen}):
            role_path=R/'cache/roles'/f'rep_{rep}.npz'
            with np.load(role_path,allow_pickle=False) as role:
                fit_ids=np.asarray(role['fit_ids'])
            role_ids_sha[rep]=hashlib.sha256(np.ascontiguousarray(fit_ids).tobytes()).hexdigest()
            role_id_counts[rep]=len(fit_ids)
            del fit_ids
        try:
            from threadpoolctl import threadpool_limits
            threadpool_limits(limits=1)
        except Exception:pass
        for t,base in sorted(pairs,key=lambda x:(int(x[0]['rep']),x[0]['method'])):
            rep=int(t['rep']);method=t['method'];e2p=Path(t['reuse_pipeline']);e3p=base/'pipeline.joblib'
            e2size=e2p.stat().st_size if e2p.is_file() else None;e3size=e3p.stat().st_size if e3p.is_file() else None
            avail=mem_available()
            row={'repetition':rep,'method':method,'e2_bytes':e2size,'e3_bytes':e3size,'mem_available_before_pair_bytes':avail,'pair_status':'deferred','components_equal':False,'component_differences':'','opaque_components':'','e2_component_sha256':'','e3_component_sha256':'','e2_file_sha256':maybe_sha(e2p),'e3_file_sha256':maybe_sha(e3p)}
            if not e2p.is_file() or not e3p.is_file():row['defer_reason']='one or both pipeline files missing'
            elif e2size>MAX_FILE or e3size>MAX_FILE:row['defer_reason']='pipeline exceeds 32 MiB bound'
            elif avail<MIN_AVAILABLE:row['defer_reason']='MemAvailable below 12 GiB bound'
            else:
                # One pair at a time; no estimator method is called.
                a=joblib.load(e2p);b=joblib.load(e3p)
                comp_names=('model','imputer','scaler','params','seed','method')
                comps={};different=[];opaque_all=[]
                for name in comp_names:
                    oa=[];ob=[]
                    ah=digest(a.get(name),oa);bh=digest(b.get(name),ob)
                    comps[name]={'e2_sha256':ah,'e3_sha256':bh,'equal':ah==bh and not oa and not ob}
                    if not comps[name]['equal']:different.append(name)
                    opaque_all.extend([f'E2.{name}:{x}' for x in oa]+[f'E3.{name}:{x}' for x in ob])
                # These fields are data/provenance identity, not the fitted predictive object.
                meta_fields=('training_ids_sha256','training_rows','class_counts','train_path','source_sha256','source_metadata')
                metadata={}
                for name in meta_fields:
                    oa=[];ob=[];av=a.get(name);bv=b.get(name)
                    ah=digest(av,oa);bh=digest(bv,ob)
                    metadata[name]={'e2_present':name in a,'e3_present':name in b,'equal_when_both_present':(ah==bh) if name in a and name in b else None,'e3_added_or_changed':name not in a or ah!=bh,'e2_sha256':ah if name in a else None,'e3_sha256':bh if name in b else None}
                    opaque_all.extend([f'E2.metadata.{name}:{x}' for x in oa]+[f'E3.metadata.{name}:{x}' for x in ob])
                e2model=a.get('model');e3model=b.get('model')
                cls2=get_class_signature(e2model);cls3=get_class_signature(e3model)
                sel=readj(base/'selection.json') if (base/'selection.json').is_file() else {}
                fit=readj(base/'fit_result.json') if (base/'fit_result.json').is_file() else {}
                fit_result=fit.get('result',{})
                cache_role=cache_doc.get('roles',{}).get(str(rep),{})
                metadata_checks={'source_sha256_matches_E2_file':b.get('source_sha256')==row['e2_file_sha256'],'source_metadata_matches_frozen_plan':b.get('source_metadata')==t.get('source_metadata'),'training_ids_hash_matches_fit_ids_array':b.get('training_ids_sha256')==role_ids_sha.get(rep),'fit_ids_count_is_80000':role_id_counts.get(rep)==80000,'planned_role_source_hash_matches_cache_manifest':rolehash_from_task(t)==cache_role.get('source_sha256'),'reconstruction_role_source_hash_matches_cache_manifest':readj(Path((t.get('source_metadata') or {}).get('reconstruction','{}'))).get('source_role_sha256')==cache_role.get('source_sha256'),'class_counts_match_fit_receipt':b.get('class_counts')==fit_result.get('class_counts'),'training_ids_hash_matches_fit_receipt':b.get('training_ids_sha256')==fit_result.get('training_ids_sha256')}
                metadata_checks['all_checked']=all(metadata_checks.values())
                modelcomponent=comps['model']['equal']
                preprocess_equal=comps['imputer']['equal'] and comps['scaler']['equal']
                params_equal=comps['params']['equal']
                seed_equal=comps['seed']['equal']
                class_sig_equal=cls2==cls3
                source_record_ok=(b.get('source_sha256')==row['e2_file_sha256'] and fit.get('result',{}).get('source_sha256')==row['e2_file_sha256'] and sel.get('source_sha256')==row['e2_file_sha256'])
                selection_ok=(sel.get('reused') is True and sel.get('seed')==t.get('seed') and sel.get('selected_params')==b.get('params'))
                fit_self_hash_ok=fit.get('artifact_sha256')==row['e3_file_sha256']
                eval_path=R/'artifacts/e3'/f'rep_{rep}'/'eval/direct'/method/'evaluation.json'
                ev=readj(eval_path) if eval_path.is_file() else {}
                eval_link_ok=bool(ev and ev.get('fit_key')==t.get('key') and ev.get('pipeline_sha256')==row['e3_file_sha256'])
                all_components_equal=(modelcomponent and preprocess_equal and params_equal and seed_equal and class_sig_equal)
                row.update({'pair_status':'loaded_and_compared','components_equal':all_components_equal,'fitted_model_state_equal':modelcomponent,'imputer_state_equal':comps['imputer']['equal'],'scaler_state_equal':comps['scaler']['equal'],'params_equal':params_equal,'seed_equal':seed_equal,'class_order_and_prior_signature_equal':class_sig_equal,'fixed_class_order_from_frozen_source':plan_doc.get('implementation_defaults',{}).get('class_order'),'e2_class_signature':cls2,'e3_class_signature':cls3,'e2_component_sha256':hashlib.sha256(json.dumps({k:comps[k]['e2_sha256'] for k in comp_names},sort_keys=True).encode()).hexdigest(),'e3_component_sha256':hashlib.sha256(json.dumps({k:comps[k]['e3_sha256'] for k in comp_names},sort_keys=True).encode()).hexdigest(),'all_predictive_components_equal':all_components_equal,'component_details':comps,'root_metadata_comparison':metadata,'root_metadata_consistency_checks':metadata_checks,'e2_to_e3_pipeline_file_byte_equal':row['e2_file_sha256']==row['e3_file_sha256'],'e3_source_metadata_matches_e2_hash':source_record_ok,'e3_selection_record_consistent':selection_ok,'e3_fit_artifact_hash_consistent':fit_self_hash_ok,'e3_evaluation_points_to_e3_pipeline':eval_link_ok,'component_differences':';'.join(different),'opaque_components':';'.join(opaque_all),'defer_reason':''})
                if opaque_all: row['pair_status']='comparison_incomplete_opaque_component'
                rows.append(row)
                del a,b,e2model,e3model
    after={p:maybe_sha(p) for p in sorted(inputs)}
    changed=[p for p in before if before[p]!=after[p]]
    stamp=utc().strftime('%Y%m%dT%H%M%SZ')
    fields=[]
    for row in rows:
        for k in row:
            if k not in fields:fields.append(k)
    if not fields:fields=['repetition','method','pair_status','defer_reason']
    with OUTCSV.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:
            w.writerow({k:(json.dumps(v,sort_keys=True,separators=(',',':')) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
    audit_path=OUTDIR/f'E3_reused_E2_components_{stamp}.json'
    versions=job_versions()
    audit={'schema_version':'e3-reused-e2-components/1.3','supersedes_prior_component_audit':'E3_reused_E2_components_20261025T135249Z.json','supersession_note':'This receipt verifies fit-ID hashes directly from the small role-cache fit_ids arrays; role source hashes and fit-ID array hashes are distinct identities and are checked separately.','observed_utc':utc().isoformat(),'plan_sha256':before.get(str(PLAN)),'e2_csv_sha256':before.get(str(E2CSV)),'code_gate':code_gate,'dependency_lock_sha256':before.get(str(DEPS)),'role_fit_ids_sha256':{str(k):v for k,v in role_ids_sha.items()},'role_fit_id_counts':{str(k):v for k,v in role_id_counts.items()},'runtime_versions':versions,'planned_pair_count':len(chosen),'loaded_pair_count':sum(r.get('pair_status')=='loaded_and_compared' for r in rows),'component_equal_pair_count':sum(r.get('all_predictive_components_equal') is True and r.get('pair_status')=='loaded_and_compared' for r in rows),'comparison_incomplete_count':sum(r.get('pair_status')!='loaded_and_compared' for r in rows),'deferred_reasons':deferred+[r.get('defer_reason') for r in rows if r.get('defer_reason')],'pair_summaries':[{'repetition':r.get('repetition'),'method':r.get('method'),'status':r.get('pair_status'),'all_predictive_components_equal':r.get('all_predictive_components_equal'),'e2_to_e3_pipeline_file_byte_equal':r.get('e2_to_e3_pipeline_file_byte_equal'),'model_state_equal':r.get('fitted_model_state_equal'),'preprocessing_equal':bool(r.get('imputer_state_equal') and r.get('scaler_state_equal')),'params_equal':r.get('params_equal'),'seed_equal':r.get('seed_equal'),'selection_consistent':r.get('e3_selection_record_consistent'),'source_hash_consistent':r.get('e3_source_metadata_matches_e2_hash'),'root_metadata_consistent':(r.get('root_metadata_consistency_checks') or {}).get('all_checked')} for r in rows],'input_hashes_before':before,'input_hashes_after':after,'input_changed_during_audit':changed,'audit_script_path':str(Path(__file__).resolve()),'audit_script_sha256':sha_path(__file__),'csv_path':str(OUTCSV),'csv_sha256':sha_path(OUTCSV),'no_fit_predict_sample_generation_or_artifact_rewrite':True,'scope':'Component-state comparison only. Root metadata additions source_sha256, source_metadata, training_ids_sha256 and class_counts are checked against the E2 source hash, frozen plan role hash and E3 fit receipt. The frozen model source declares LABELS=np.arange(7), using canonical task class order. No calls to fit, predict_proba, score_matrix, predict, sample_class, generation, calibration or test inference. Exact component equality does not prove equal predictions.'}
    audit['audit_json_sha256_excluded_from_self_hash']=True
    audit_path.write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'audit_path':str(audit_path),'csv_path':str(OUTCSV),'planned':len(chosen),'loaded':audit['loaded_pair_count'],'equal':audit['component_equal_pair_count'],'incomplete':audit['comparison_incomplete_count'],'deferred':audit['deferred_reasons'],'inputs_changed':changed,'script_sha256':audit['audit_script_sha256'],'csv_sha256':audit['csv_sha256']},sort_keys=True))

if __name__=='__main__':main()
