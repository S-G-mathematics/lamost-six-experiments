"""Staged, evidence-gated prospective admission estimates. Scientific inputs and hard limits are unchanged."""
import json
import pathlib
import hashlib
import zipfile
import numpy as np

GIB = 1024**3
GEN_METHODS = {'gmm', 'copula', 'chow_liu'}
E4_CONDITIONS = {f'{label}_{sev}' for label in ('A','F','G','K','M','GALAXY','QSO') for sev in ('half','tenth')}
E5_CONDITIONS = {f'{mechanism}_{rate}' for mechanism in ('feature_noise','missingness','label_noise') for rate in ('05','10','20')}
PROFILE_ID = 'verified-80k-generator-and-e4-rf-eval-4gib-20261026'
GENERATOR_2G_PROFILE_ID = 'verified-80k-e4-e5-gmm-copula-chow-direct-fit-2gib-20261026'
GENERATOR_PHASE_MAX_KIB = {'gmm':229596,'copula':203764,'chow_liu':203744}
GENERATOR_PHASE_RECEIPTS_PER_METHOD = {'gmm':462,'copula':210,'chow_liu':168}
GENERATOR_OUTER_TREE_GMM_OBSERVED_TASKS = 20
GENERATOR_OUTER_TREE_GMM_MAX_BYTES = 422480*1024
_SHA_CACHE = {}

def _sha256_cached(path):
    """Stream a file hash and memoize only while its full stat identity is unchanged."""
    p = pathlib.Path(path).resolve()
    try:
        st = p.stat()
        identity = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        old = _SHA_CACHE.get(str(p))
        if old and old[0] == identity: return old[1]
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
        after = p.stat()
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if identity_after != identity: return None
        value = h.hexdigest()
        _SHA_CACHE[str(p)] = (identity, value)
        return value
    except OSError: return None

def _json(path):
    try: return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError, TypeError): return None

def _header_shapes(path):
    """Read only NPZ NPY headers; never decompress or load scientific arrays."""
    out = {}
    try:
        with zipfile.ZipFile(path) as z:
            for name in ('X.npy','y.npy','ids.npy'):
                with z.open(name) as f:
                    version = np.lib.format.read_magic(f)
                    if version == (1,0): shape, _, _ = np.lib.format.read_array_header_1_0(f)
                    elif version in ((2,0),(3,0)): shape, _, _ = np.lib.format.read_array_header_2_0(f)
                    else: return None
                    out[name[:-4]] = tuple(shape)
        return out
    except Exception: return None

def _valid_cohort(root, key, exp, rep, condition):
    if not key: return False
    p = pathlib.Path(root)/'artifacts'/key
    meta, val = _json(p/'metadata.json'), _json(p/'validation.json')
    if not isinstance(meta,dict) or not isinstance(val,dict): return False
    expected_kind = 'e4_cohort' if exp == 4 else 'e5_corruption'
    if meta.get('task_key') != key or meta.get('kind') != expected_kind or int(meta.get('rep',-1)) != rep: return False
    if val.get('status') != 'validated' or val.get('task_key') != key or 'data.npz' not in val.get('files',{}): return False
    if exp == 4 and meta.get('condition') not in (None, condition): return False
    if exp == 5:
        try: derived = meta.get('mechanism')+'_'+str(int(round(float(meta.get('rate'))*100))).zfill(2)
        except (TypeError,ValueError): return False
        if derived != condition: return False
    rows = meta.get('fit_count') if exp == 5 else meta.get('N',meta.get('n_rows',meta.get('fit_count')))
    if int(rows or -1) != 80000: return False
    return _header_shapes(p/'data.npz') == {'X':(80000,6),'y':(80000,),'ids':(80000,)}

def _valid_published_fit(root, key, exp, rep, method, train_key, require_publication=False, expected_rows=80000):
    p = pathlib.Path(root)/'artifacts'/key
    r, pub, val = (_json(p/f) for f in ('fit_result.json','fit_publication.json','validation.json'))
    if not isinstance(r,dict) or not isinstance(val,dict) or (pub is not None and not isinstance(pub,dict)): return False
    task, result = r.get('task') or {}, r.get('result') or {}
    if r.get('status') != 'successful' or result.get('status') != 'success': return False
    if task.get('key') != key or int(task.get('experiment',-1)) != exp or int(task.get('rep',-1)) != rep or task.get('method') != method: return False
    if task.get('train_key') != train_key or result.get('training_rows',task.get('training_rows')) != expected_rows: return False
    counts = result.get('class_counts',task.get('training_counts'))
    if not isinstance(counts,list) or len(counts) != 7 or any(type(x) is not int or x < 0 for x in counts) or sum(counts) != expected_rows: return False
    pipeline = result.get('pipeline_sha256') or r.get('artifact_sha256')
    if not isinstance(pipeline,str) or len(pipeline) != 64: return False
    if require_publication and not pub: return False
    if pub:
        if pub.get('stage') != 'validated_publication' or pub.get('attempt_id') != r.get('attempt_id') or pub.get('task_sha256') != r.get('task_sha256') or pub.get('pipeline_sha256') != pipeline: return False
        if pathlib.Path(pub.get('published_path','')).resolve() != (p/'pipeline.joblib').resolve(): return False
    if val.get('status') != 'validated' or val.get('task_key') != key or val.get('files',{}).get('pipeline.joblib') != pipeline: return False
    pipeline_path=p/'pipeline.joblib'
    if not pipeline_path.is_file() or _sha256_cached(pipeline_path) != pipeline: return False
    if exp == 3:
        selection = p/'selection.json'
        expected = val.get('files',{}).get('selection.json')
        if not expected or not selection.is_file() or _sha256_cached(selection) != expected: return False
    return True

def _never_attempted(t):
    if t.get('attempts') or t.get('admission_reservation_bytes') is not None: return False
    if t.get('status') not in ('planned','waiting_dependency','waiting_for_dependency'): return False
    return not any(t.get(k) is not None for k in ('pid','process_start_ticks','request_path','result_path'))

def _eligible_4gib_checked(t, definition, root):
    """Return (eligible, evidence); unproven cases fail closed to default policy."""
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    key, method, cond = definition.get('key'), definition.get('method'), definition.get('condition')
    if t.get('key') != key or not key: return False,None
    try: rep, exp = int(definition.get('rep')), int(definition.get('experiment'))
    except (TypeError,ValueError): return False,None
    kind, route = definition.get('kind'), definition.get('route')
    if exp == 4 and kind == 'fit' and method in GEN_METHODS and route == 'direct' and rep in (1,2,3) and cond in E4_CONDITIONS:
        train = f'e4/rep_{rep}/cohort/{cond}'
        if key != f'e4/rep_{rep}/fit/direct/{method}/{cond}' or definition.get('train_key') != train or definition.get('dependencies') != [train]: return False,None
        if not _valid_cohort(root,train,4,rep,cond): return False,None
        return True,{'profile_id':PROFILE_ID,'reason':'validated 80k E4 direct flexible-generator fit cohort','train_key':train,'npz_header_shapes':{'X':[80000,6],'y':[80000],'ids':[80000]}}
    if exp == 5 and kind == 'fit' and method in GEN_METHODS and route == 'direct' and rep in (1,2,3) and cond in E5_CONDITIONS:
        train, base = f'e5/rep_{rep}/corruption/{cond}', f'e3/rep_{rep}/fit/{method}'
        if key != f'e5/rep_{rep}/fit/direct/{method}/{cond}' or definition.get('train_key') != train or definition.get('dependencies') != [train,base]: return False,None
        if not _valid_cohort(root,train,5,rep,cond): return False,None
        base_result = _json(pathlib.Path(root)/'artifacts'/base/'fit_result.json') or {}
        base_train = (base_result.get('task') or {}).get('train_key')
        if not _valid_published_fit(root,base,3,rep,method,base_train): return False,None
        return True,{'profile_id':PROFILE_ID,'reason':'validated 80k E5 generator fit cohort and matching published clean generator','train_key':train,'dependency_fit_key':base,'npz_header_shapes':{'X':[80000,6],'y':[80000],'ids':[80000]}}
    if exp == 4 and kind == 'eval' and method == 'random_forest' and route == 'direct' and rep in (1,2,3) and cond in E4_CONDITIONS:
        fit, train = f'e4/rep_{rep}/fit/direct/random_forest/{cond}', f'e4/rep_{rep}/cohort/{cond}'
        if key != f'e4/rep_{rep}/eval/direct/random_forest/{cond}' or definition.get('fit_key') != fit or definition.get('dependencies') != [fit]: return False,None
        if definition.get('train_key') not in (None,train): return False,None
        if not _valid_cohort(root,train,4,rep,cond) or not _valid_published_fit(root,fit,4,rep,'random_forest',train,require_publication=True): return False,None
        return True,{'profile_id':PROFILE_ID,'reason':'validated published 80k E4 direct random-forest fit and matching cohort','fit_key':fit,'train_key':train,'npz_header_shapes':{'X':[80000,6],'y':[80000],'ids':[80000]}}
    return False,None


def eligible_4gib(t, definition, root):
    """Fail closed for malformed, incomplete, or unreadable eligibility evidence."""
    try:
        return _eligible_4gib_checked(t, definition, root)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, EOFError, zipfile.BadZipFile):
        return False, None


def eligible_2gib_generator_fit(t, definition, root):
    """Evidence gate for never-attempted 80k direct E4/E5 GMM-family fits only."""
    try:
        if not isinstance(definition, dict): return False, None
        if definition.get('kind') != 'fit' or definition.get('method') not in GEN_METHODS or definition.get('route') != 'direct': return False, None
        exp = int(definition.get('experiment', 0))
        method = definition.get('method')
        if exp == 4:
            if definition.get('selection_mode') != 'tune' or definition.get('trials') != 10 or definition.get('selection_policy') != 'tune_on_matching_altered_cohort' or definition.get('selection_key') is not None or definition.get('reuse_pipeline'):
                return False, None
        elif exp == 5:
            rep = int(definition.get('rep', 0)); expected_base = f'e3/rep_{rep}/fit/{method}'
            if definition.get('selection_key') != expected_base or definition.get('selection_mode') != 'fixed' or definition.get('trials') != 0 or definition.get('selection_policy') != 'frozen_clean_selected_params_no_retuning' or definition.get('reuse_pipeline'):
                return False, None
            selection = _json(pathlib.Path(root)/'artifacts'/expected_base/'selection.json')
            if not isinstance(selection,dict) or not isinstance(selection.get('selected_params'),dict): return False, None
        else: return False, None
        ok, evidence = _eligible_4gib_checked(t, definition, root)
        if not ok: return False, None
        evidence = dict(evidence)
        evidence.update({'profile_id':GENERATOR_2G_PROFILE_ID,'reservation_gib':2,'resource_evidence':{'receipt':'reports/engineering_audits/GENERATOR_FIT_AND_E4_RF_RESOURCE_ADMISSION_AUDIT_20261026.json','receipt_sha256':'fd3c4923561cd1007b481fb66fc7a1783e0dd9ccaf5eab63073181d27c074d75','method_phase_max_rss_kib':GENERATOR_PHASE_MAX_KIB[method],'method_phase_receipt_count':GENERATOR_PHASE_RECEIPTS_PER_METHOD[method],'rss_scope':'phase worker process plus descendants, RSS sampled at 250 ms; excludes outer task-worker parent and is not PSS','outer_tree_observation_scope':'controller sampled full outer-worker process tree for 20 of 42 E4 GMM tasks only','outer_tree_gmm_observed_max_bytes':GENERATOR_OUTER_TREE_GMM_MAX_BYTES,'outer_tree_gmm_observed_max_gib':GENERATOR_OUTER_TREE_GMM_MAX_BYTES/(1024**3),'interpretation':'Provisional reservation estimate, not a worst-case bound; 10 GiB per-worker hard limit and dynamic promotion/admission guards remain active.'}})
        return True, evidence
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, EOFError, zipfile.BadZipFile):
        return False, None


E5_RF_4G_PROFILE_ID = 'e5-direct-rf-fixed-80k-admission-4gib-20261026'
E4_TREATMENT_RF_6G_PROFILE_ID = 'e4-nonweighted-treatment-rf-up-to-82394-admission-6gib-20261026'
E4_TREATMENT_RF_MAX_ROWS = 82394
E4_RF_FIT_5G_PROFILE_ID = 'e4-nonweighted-treatment-rf-observed-80611-84310-admission-5gib-20261026'
E4_GENERATED_RF_6G_PROFILE_ID = 'e4-generated-restoration-rf-observed-through-125934-admission-6gib-20261027-v2'
E4_GENERATED_RF_6G_AUDIT_PATH = 'reports/engineering_audits/E4_GENERATED_RF_ADMISSION_REVIEW_20261027_V2.json'
E4_GENERATED_RF_6G_AUDIT_SHA256 = '77688543c3e2ad7aa5b9f174c391aa0b357a94f86fa5be0b8e020c5b02254b62'
E4_GENERATED_RF_6G_RECEIPT_PATH = 'reports/engineering_audits/E4_GENERATED_RF_ADMISSION_REVIEW_20261027_V2_RECEIPTS.json'
E4_GENERATED_RF_6G_RECEIPT_SHA256 = '5cd4a7c73df658aea359ecb917cd21e9b32122492c588dd7cf129b56616f2abb'
E4_GENERATED_RF_6G_FILE_MANIFEST_SHA256 = 'f2e85e7050c1a4db2b0841de2b5b9e2ae2d879bb10ec412d3d96711ee6c9117b'
E4_GENERATED_RF_6G_PLAN_SUMMARY_SHA256 = '09caf33a226c48f431f5a16c7fe0acb50b97487a1a1ecfecb8f170fc655f1306'
E4_GENERATED_RF_6G_CACHE_MANIFEST_SHA256 = 'bbcc195e0564066d541fbd483896935d7471e8893e6db34ca6184dfe90ee9720'
E4_GENERATED_RF_6G_TASKS_SHA256 = '42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb'
E4_GENERATED_RF_6G_MAX_ROWS = 125934
E4_GENERATED_RF_6G_GENERATOR_TRIALS = {'gmm':10,'copula':10,'arf':5,'kde':5,'chow_liu':10}
E4_GENERATED_RF_6G_ROLE_SOURCE_SHA = {
    1:'e3ef78cddd5c23acebe8ff1a8fe8760e653da194cceebd45c5051416b329d334',
    2:'30f7d5d361a6563309f102f0d9ab9c676c630eee30f314bd49b64785b6ab4efc',
    3:'1bc8859b0fee37c49ba92661e83a635c63564705968d294b61f19e55adacf63e'}
E4_GENERATED_RF_6G_ROLE_CACHE_SHA = {
    1:'7bd1b5df13a4639dbffc7960d1403494d80655fc1b36f05604eda7a1773563de',
    2:'336faab22e3bb100ce56bf15ed713385f81fa8e3e6b781d13e5d77987b0239fc',
    3:'c149e76882c6c978d1fa1fd2cbe4dd98374c6cdfc716331e73f6f7f9998f46e7'}
E4_GENERATED_RF_6G_TEST_CACHE_SHA = 'bf1d00bffc75d32484243b65aed4e2b8b43492bd4857f7c30ab819fc8ab6579b'
E4_GENERATED_RF_6G_FROZEN_SCIENCE_SHA = '9937104e3e2d56eab25bb9596b39dcadbdefcd677ffa941cd1a635ae4ba58bd3'
E4_GENERATED_RF_6G_FROZEN_WORKER_SHA = 'f158d2bed12072da661af9195cc3a1b7e0367ff7cb2fe3ad24111e076dd29b18'
E4_GENERATED_RF_6G_FROZEN_PHASE_SHA = '03df2cf1208d7a0a14ceda002f7f16291e0e08ee7308f967980d9519d05cc8de'
E4_GENERATED_RF_6G_FROZEN_COHORTS_SHA = '5d5988b365613966778abc7438926d9e1b26ec36b779df98586aa600a3d20a1d'
E4_RF_FIT_5G_MIN_ROWS = 80611
E4_RF_FIT_5G_MAX_ROWS = 84310
E4_RF_FIT_5G_KDE_CONDITIONS = {'A_half','GALAXY_half','GALAXY_tenth','QSO_half','QSO_tenth'}
E4_RF_FIT_5G_AUDIT_PATH = 'staging/e4_rf_fit_reservation_review_20261026/E4_RF_FIT_RESERVATION_RESOURCE_REVIEW_20261026.json'
E4_RF_FIT_5G_AUDIT_SHA256 = '2e6356dac0be320eb5e57c3537b3c4dff01e8943d5f1490424f117e4b332e1b6'
E4_RF_FIT_5G_MODELS_BASIC_SHA256 = '5c0079097f90339c452e48cba178f8f22bc5012882097fad23715f425e4ec8b2'
E4_RF_EXTENSION_PATH='staging/nonrf_heavy_resource_readiness_20261026/HEAVY_METHOD_RESOURCE_READINESS_AUDIT_20261026.json'
E4_RF_EXTENSION_SHA='b3530fd93a17095fa6d3e8b7071b4df943cceea829ecad4415513ac06bf11c49'
E4_WEIGHTED_RF_5G_PROFILE_ID='e4-weighted-treatment-rf-80k-admission-5gib-20261026'
E4_ARF_6G_PROFILE_ID='e4-direct-arf-80k-tuned-admission-6gib-20261026'
E5_ARF_6G_PROFILE_ID='e5-direct-arf-80k-fixed-admission-6gib-20261026'
E4_E5_ARF_MODELS_SHA='082d789fb6a645d3c336ff725462a5f2d53cf82ce138289c8281e99dd8f6c8cb'
E5_RF_EXPECTED_SELECTED_PARAMS = {'max_depth':None,'max_features':1.0,'min_samples_leaf':1,'n_estimators':200}
E4_LABELS = ('A','F','G','K','M','GALAXY','QSO')
E4_TREATMENT_BASES = {f'{label}_{severity}' for label in E4_LABELS for severity in ('half','tenth')}

def _e5_mechanism_rate_matches(definition, condition):
    if not isinstance(condition,str) or '_' not in condition: return False
    mechanism,rate_text=condition.rsplit('_',1)
    expected={'05':0.05,'10':0.10,'20':0.20}.get(rate_text)
    return expected is not None and definition.get('mechanism')==mechanism and definition.get('rate')==expected

def _valid_npz_artifact(root, key):
    p = pathlib.Path(root)/'artifacts'/key
    meta, val = _json(p/'metadata.json'), _json(p/'validation.json')
    if not isinstance(meta,dict) or not isinstance(val,dict): return None
    if meta.get('task_key') != key or val.get('task_key') != key or val.get('status') != 'validated': return None
    expected_hash = (val.get('files') or {}).get('data.npz')
    if not isinstance(expected_hash,str) or len(expected_hash) != 64: return None
    npz=p/'data.npz'
    if not npz.is_file() or _sha256_cached(npz) != expected_hash: return None
    return meta,_header_shapes(npz)

def _eligible_e5_direct_rf_4gib(t, definition, root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    try:
        rep=int(definition.get('rep')); cond=definition.get('condition'); key=definition.get('key')
        train=f'e5/rep_{rep}/corruption/{cond}'; base=f'e3/rep_{rep}/fit/real/random_forest'
    except (TypeError,ValueError): return False,None
    if (rep not in (1,2,3) or definition.get('experiment') != 5 or definition.get('kind') != 'fit'
        or definition.get('route') != 'direct' or definition.get('method') != 'random_forest'
        or cond not in E5_CONDITIONS or not _e5_mechanism_rate_matches(definition,cond) or key != f'e5/rep_{rep}/fit/direct/random_forest/{cond}'
        or t.get('key') != key or definition.get('train_key') != train
        or definition.get('dependencies') != [train,base]
        or definition.get('selection_key') != base or definition.get('selection_mode') != 'fixed'
        or definition.get('selection_policy') != 'frozen_clean_selected_params_no_retuning'
        or definition.get('trials') != 0 or definition.get('reuse_pipeline')
        or definition.get('selection_source') is not None):
        return False,None
    if not _valid_npz_artifact(root,train) or not _valid_cohort(root,train,5,rep,cond): return False,None
    base_result=_json(pathlib.Path(root)/'artifacts'/base/'fit_result.json') or {}
    base_task=base_result.get('task') or {}
    if base_task.get('method') != 'random_forest' or base_task.get('route') != 'real': return False,None
    if not _valid_published_fit(root,base,3,rep,'random_forest',base_task.get('train_key')): return False,None
    selection=_json(pathlib.Path(root)/'artifacts'/base/'selection.json')
    if not isinstance(selection,dict) or selection.get('selected_params') != E5_RF_EXPECTED_SELECTED_PARAMS: return False,None
    return True,{'profile_id':E5_RF_4G_PROFILE_ID,'reservation_gib':4,'reason':'80k direct E5 RF fixed/no-retune cell with matching validated E3 real RF fit','train_key':train,'fit_key':base,'selected_params':selection['selected_params'],'selected_fit_selection_sha256':_sha256_cached(pathlib.Path(root)/'artifacts'/base/'selection.json'),'npz_header_shapes':{'X':[80000,6],'y':[80000],'ids':[80000]}}

def _eligible_e4_treatment_rf_6gib(t, definition, root, max_rows=None):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    try:
        rep=int(definition.get('rep')); treatment=definition.get('treatment')
        cond=definition.get('condition'); key=definition.get('key'); train=definition.get('train_key')
    except (TypeError,ValueError): return False,None
    if (rep not in (1,2,3) or definition.get('experiment') != 4 or definition.get('kind') != 'fit'
        or definition.get('route') != 'treatment' or definition.get('method') != 'random_forest'
        or t.get('key') != key or not isinstance(cond,str) or not isinstance(treatment,str)):
        return False,None
    if treatment in ('ros','smote'):
        base=cond.removesuffix('_'+treatment); expected_train=f'e4/rep_{rep}/treatment/{base}/{treatment}'; expected_kind='e4_treatment'
    elif treatment.startswith('generated_'):
        gen=treatment[len('generated_'):]
        if gen not in ('gmm','copula','arf','kde','chow_liu'): return False,None
        base=cond.removesuffix('_'+treatment); expected_train=f'e4/rep_{rep}/append/{base}/{gen}'; expected_kind='e4_append'
        if definition.get('generator') != gen: return False,None
    else: return False,None
    if (base not in E4_TREATMENT_BASES or cond != base+'_'+treatment or train != expected_train
        or definition.get('dependencies') != [expected_train]
        or key != f'e4/rep_{rep}/fit/treatment/random_forest/{cond}'
        or definition.get('selection_mode') != 'tune' or definition.get('trials') != 10
        or definition.get('selection_key') is not None
        or definition.get('selection_policy') != 'tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget'):
        return False,None
    valid=_valid_npz_artifact(root,expected_train)
    if not valid: return False,None
    meta,shapes=valid
    if meta.get('kind') != expected_kind: return False,None
    parent=f'e4/rep_{rep}/cohort/{base}'
    if pathlib.Path(str(meta.get('parent',''))).resolve() != (pathlib.Path(root)/'artifacts'/parent).resolve(): return False,None
    if not _valid_cohort(root,parent,4,rep,base): return False,None
    parent_meta=_json(pathlib.Path(root)/'artifacts'/parent/'metadata.json') or {}
    before=meta.get('counts_before'); counts=meta.get('counts_after') or meta.get('counts')
    if not isinstance(before,list) or before != parent_meta.get('realized_counts'): return False,None
    if not isinstance(counts,list) or len(counts)!=7 or any(type(x) is not int or x<0 for x in counts): return False,None
    target_index=E4_LABELS.index(base.split('_')[0])
    added=meta.get('added_count')
    if type(added) is not int or added < 0: return False,None
    expected_after=list(before);expected_after[target_index]+=added
    if counts != expected_after: return False,None
    if expected_kind=='e4_treatment':
        if meta.get('treatment') != treatment: return False,None
    elif meta.get('target_class') != target_index: return False,None
    rows=sum(counts)
    if max_rows not in (None,E4_RF_FIT_5G_MAX_ROWS):return False,None
    validation_max=E4_TREATMENT_RF_MAX_ROWS if max_rows is None else max_rows
    if type(validation_max)is not int or rows > validation_max or rows < 80000:return False,None
    expected_shapes={'X':(rows,6),'y':(rows,),'ids':(rows,)}
    if shapes != expected_shapes: return False,None
    return True,{'profile_id':E4_TREATMENT_RF_6G_PROFILE_ID,'reservation_gib':6,'reason':'validated non-weighted E4 RF treatment artifact at or below the measured 82,394-row envelope','train_key':expected_train,'parent_cohort_key':parent,'treatment':treatment,'training_rows':rows,'npz_header_shapes':{'X':[rows,6],'y':[rows],'ids':[rows]},'memory_evidence':'Legacy profile envelope through 82,394 rows; larger inputs require the separate extension audit and profile.'}


def _eligible_e4_treatment_rf_fit_5gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t):return False,None
    ok,evidence=_eligible_e4_treatment_rf_6gib(t,definition,root)
    if not ok:
        ok,evidence=_eligible_e4_treatment_rf_6gib(t,definition,root,max_rows=E4_RF_FIT_5G_MAX_ROWS)
    if not ok or not isinstance(evidence,dict):return False,None
    if evidence.get('profile_id')!=E4_TREATMENT_RF_6G_PROFILE_ID or evidence.get('reservation_gib')!=6:return False,None
    treatment=definition.get('treatment')
    if treatment not in ('ros','smote','generated_gmm','generated_copula','generated_chow_liu','generated_kde'):return False,None
    if treatment=='generated_kde':
        rep=definition.get('rep'); condition=definition.get('condition')
        base_condition=condition[:-len('_generated_kde')] if isinstance(condition,str) and condition.endswith('_generated_kde') else None
        expected_key=f'e4/rep_{rep}/fit/treatment/random_forest/{condition}'
        if (rep not in (1,2,3) or base_condition not in E4_RF_FIT_5G_KDE_CONDITIONS
            or definition.get('method')!='random_forest' or definition.get('route')!='treatment'
            or definition.get('generator')!='kde' or definition.get('key')!=expected_key):
            return False,None
    rows=evidence.get('training_rows')
    if type(rows)is not int or rows<E4_RF_FIT_5G_MIN_ROWS or rows>E4_RF_FIT_5G_MAX_ROWS:return False,None
    shape=evidence.get('npz_header_shapes') or {}
    if shape!={'X':[rows,6],'y':[rows],'ids':[rows]}:return False,None
    root=pathlib.Path(root)
    audit=root/E4_RF_FIT_5G_AUDIT_PATH
    models_basic=root.parent/'project'/'benchmark'/'models_basic.py'
    if _sha256_cached(audit)!=E4_RF_FIT_5G_AUDIT_SHA256:return False,None
    if _sha256_cached(models_basic)!=E4_RF_FIT_5G_MODELS_BASIC_SHA256:return False,None
    audit_doc=_json(audit) or {}
    assessment=audit_doc.get('assessment') or {}
    fits=audit_doc.get('current_counts') or {}
    trial_receipts=audit_doc.get('tuning_trials') or {}
    final_receipts=audit_doc.get('final_fit_phases') or {}
    if ('provisional 5 GiB admission'.lower() not in str(assessment.get('verdict','')).lower()
        or fits.get('successful')!=25 or trial_receipts.get('actual_trial_phase_receipts')!=202
        or final_receipts.get('receipt_count')!=25
        or (audit_doc.get('frozen_domain') or {}).get('fit_rows_max_observed')!=82394):
        return False,None
    extension_audit_sha=None
    if rows>E4_TREATMENT_RF_MAX_ROWS:
        ext=root/E4_RF_EXTENSION_PATH
        if _sha256_cached(ext)!=E4_RF_EXTENSION_SHA:return False,None
        ed=_json(ext) or {};src=ed.get('source_sha256') or {};rf=ed.get('random_forest_evidence') or {}
        nm=rf.get('new_max_row_success') or {};counts=rf.get('E4_treatment_successes') or {}
        if (src.get('project/benchmark/models_basic.py')!=E4_RF_FIT_5G_MODELS_BASIC_SHA256
            or nm.get('key')!='e4/rep_1/fit/treatment/random_forest/A_tenth_generated_copula'
            or nm.get('outcome')!='successful' or nm.get('rows')!=84310 or nm.get('X_shape')!=[84310,6]
            or nm.get('sample_weight') is not False or nm.get('final_peak_rss_kib')!=2538164
            or nm.get('trial_max_peak_rss_kib')!=1790228 or nm.get('trial_phase_receipts')!=8
            or counts.get('nonweighted_rows_max')!=84310 or rf.get('no_success_above_84310') is not True):return False,None
        extension_audit_sha=E4_RF_EXTENSION_SHA
    out=dict(evidence)
    out.update({'profile_id':E4_RF_FIT_5G_PROFILE_ID,'reservation_gib':5,
        'validation_base_profile_id':E4_TREATMENT_RF_6G_PROFILE_ID,
        'prior_profile_id':E4_TREATMENT_RF_6G_PROFILE_ID if rows<=E4_TREATMENT_RF_MAX_ROWS else None,
        'prior_reservation_gib':6 if rows<=E4_TREATMENT_RF_MAX_ROWS else None,
        'previous_default_reservation_gib':10 if rows>E4_TREATMENT_RF_MAX_ROWS else None,
        'reason':'narrow provisional admission reservation for never-attempted nonweighted E4 treatment RF fits within the observed 80,611-84,310 row envelope; generated-KDE route is limited to the five measured condition types; applying the measured resource envelope to future repetitions is an admission estimate, not a hard bound',
        'treatment':treatment,'training_rows':rows,'npz_header_shapes':shape,
        'resource_audit_path':E4_RF_FIT_5G_AUDIT_PATH,'resource_audit_sha256':E4_RF_FIT_5G_AUDIT_SHA256,
        'frozen_model_search_source':'../project/benchmark/models_basic.py',
        'frozen_model_search_source_sha256':E4_RF_FIT_5G_MODELS_BASIC_SHA256,
        'frozen_n_estimators_domain':[200,500],'frozen_max_n_estimators':500,
        'observed_training_rows_min':E4_RF_FIT_5G_MIN_ROWS,'observed_training_rows_max':E4_RF_FIT_5G_MAX_ROWS,
        'observed_max_phase_rss_kib':3907392,'reservation_margin_over_observed_max_phase_rss_gib':1.27362060546875,
        'worker_hard_rss_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,
        'admission_only_estimate_not_hard_limit':True,'dynamic_promotion_to_10gib_retained':True})
    if extension_audit_sha is not None:
        out.update({'row_extension_audit_path':E4_RF_EXTENSION_PATH,'row_extension_audit_sha256':extension_audit_sha})
    return True,out



def _extra_audit(root,source_rel,source_sha=None):
    p=pathlib.Path(root)/E4_RF_EXTENSION_PATH
    if _sha256_cached(p)!=E4_RF_EXTENSION_SHA:return None
    d=_json(p)
    if not isinstance(d,dict):return None
    if source_sha is not None and (d.get('source_sha256') or {}).get(source_rel)!=source_sha:return None
    return d

def _unit_mean_sample_weight_mean(value):
    """Accept finite numeric normalization roundoff within 1e-12 absolute of 1."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(np.isfinite(number) and abs(number - 1.0) <= 1e-12)


def _eligible_e4_weighted_rf_5g(t,d,root):
    if not isinstance(t,dict) or not isinstance(d,dict) or not _never_attempted(t):return False,None
    try:r=int(d.get('rep'));c=d.get('condition');k=d.get('key');train=d.get('train_key')
    except (ValueError,TypeError):return False,None
    base=c[:-9] if isinstance(c,str) and c.endswith('_weighted') else None
    expect=f'e4/rep_{r}/treatment/{base}/weighted'
    if (r not in (1,2,3) or d.get('experiment')!=4 or d.get('kind')!='fit' or d.get('route')!='treatment'
      or d.get('method')!='random_forest' or d.get('treatment')!='weighted' or base not in E4_TREATMENT_BASES
      or c!=base+'_weighted' or k!=f'e4/rep_{r}/fit/treatment/random_forest/{c}' or t.get('key')!=k
      or train!=expect or d.get('dependencies')!=[train] or d.get('selection_mode')!='tune' or d.get('trials')!=10
      or d.get('selection_key') is not None or d.get('selection_policy')!='tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget'):return False,None
    v=_valid_npz_artifact(root,train)
    if not v:return False,None
    meta,_=v;parent=f'e4/rep_{r}/cohort/{base}'
    if meta.get('kind')!='e4_treatment' or meta.get('treatment')!='weighted' or pathlib.Path(str(meta.get('parent',''))).resolve()!=(pathlib.Path(root)/'artifacts'/parent).resolve() or not _valid_cohort(root,parent,4,r,base):return False,None
    parent_meta=_json(pathlib.Path(root)/'artifacts'/parent/'metadata.json') or {}
    if meta.get('counts')!=parent_meta.get('realized_counts') or parent_meta.get('sample_weight_included') is not False:return False,None
    hdr=_all_npz_header_shapes(pathlib.Path(root)/'artifacts'/train/'data.npz');counts=meta.get('counts')
    if hdr!={'X':(80000,6),'y':(80000,),'ids':(80000,),'sample_weight':(80000,)} or not isinstance(counts,list) or len(counts)!=7 or any(type(x)is not int or x<0 for x in counts) or sum(counts)!=80000 or not _unit_mean_sample_weight_mean(meta.get('sample_weight_mean')) or meta.get('added_count')!=0:return False,None
    if _sha256_cached(pathlib.Path(root).parent/'project'/'benchmark'/'models_basic.py')!=E4_RF_FIT_5G_MODELS_BASIC_SHA256:return False,None
    audit=_extra_audit(root,'project/benchmark/models_basic.py',E4_RF_FIT_5G_MODELS_BASIC_SHA256)
    ev=((audit or {}).get('random_forest_evidence') or {}).get('E4_weighted_treatment_80k') or {}
    if (not audit or ev.get('rows')!=80000 or ev.get('sample_weight_shape')!=[80000] or ev.get('final_rss_kib')!=1127528 or ev.get('trial_receipts')!=8 or ev.get('trial_max_rss_kib')!=1820804 or ev.get('selected_params')!={'n_estimators':200,'max_depth':20,'min_samples_leaf':1,'max_features':1.0}):return False,None
    return True,{'profile_id':E4_WEIGHTED_RF_5G_PROFILE_ID,'reservation_gib':5,'train_key':train,'rows':80000,'sample_weight_shape':[80000],'counts':counts,'resource_audit_sha256':E4_RF_EXTENSION_SHA,'reason':'one matching weighted 80k RF fit; provisional admission estimate only; 10 GiB hard limit and promotion retained'}

def _eligible_arf_6g(t,d,root,exp):
    if not isinstance(t,dict) or not isinstance(d,dict) or not _never_attempted(t):return False,None
    try:r=int(d.get('rep'));c=d.get('condition');k=d.get('key');train=d.get('train_key')
    except (TypeError,ValueError):return False,None
    if r not in (1,2,3) or d.get('experiment')!=exp or d.get('kind')!='fit' or d.get('route')!='direct' or d.get('method')!='arf' or t.get('key')!=k:return False,None
    if exp==4:
        expect=f'e4/rep_{r}/cohort/{c}'
        if (c not in E4_CONDITIONS or k!=f'e4/rep_{r}/fit/direct/arf/{c}' or train!=expect or d.get('dependencies')!=[expect]
          or d.get('selection_mode')!='tune' or d.get('trials')!=5 or d.get('selection_key') is not None or d.get('selection_source') is not None or d.get('reuse_pipeline') or d.get('generator') is not None or d.get('treatment') is not None or d.get('selection_policy')!='tune_on_matching_altered_cohort'
          or not _valid_cohort(root,expect,4,r,c)):return False,None
        cohort_meta=_json(pathlib.Path(root)/'artifacts'/expect/'metadata.json') or {}
        cohort_counts=cohort_meta.get('realized_counts')
        if not isinstance(cohort_counts,list) or len(cohort_counts)!=7 or any(type(x)is not int or x<120 for x in cohort_counts) or sum(cohort_counts)!=80000:return False,None
        base=None
    else:
        if c not in E5_CONDITIONS or not _e5_mechanism_rate_matches(d,c):return False,None
        expect=f'e5/rep_{r}/corruption/{c}';base=f'e3/rep_{r}/fit/arf'
        if (k!=f'e5/rep_{r}/fit/direct/arf/{c}' or train!=expect or d.get('dependencies')!=[expect,base] or d.get('selection_key')!=base
          or d.get('selection_mode')!='fixed' or d.get('trials')!=0 or d.get('selection_source') is not None or d.get('reuse_pipeline') or d.get('generator') is not None or d.get('treatment') is not None or d.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
          or not _valid_cohort(root,expect,5,r,c)):return False,None
        br=_json(pathlib.Path(root)/'artifacts'/base/'fit_result.json') or {};bt=br.get('task') or {}
        if bt.get('route')!='generator' or not _valid_published_fit(root,base,3,r,'arf',bt.get('train_key')):return False,None
        sel=_json(pathlib.Path(root)/'artifacts'/base/'selection.json') or {}
        if not isinstance(sel.get('selected_params'),dict) or br.get('result',{}).get('params')!=sel.get('selected_params'):return False,None
    v=_valid_npz_artifact(root,expect)
    if not v or v[1]!={'X':(80000,6),'y':(80000,),'ids':(80000,)}:return False,None
    if _sha256_cached(pathlib.Path(root).parent/'project'/'benchmark'/'models_arf.py')!=E4_E5_ARF_MODELS_SHA:return False,None
    audit=_extra_audit(root,'project/benchmark/models_arf.py',E4_E5_ARF_MODELS_SHA)
    arf=(audit or {}).get('arf_evidence') or {};fits=arf.get('fits') or [];tune=arf.get('tuning') or {}
    if not audit or len(fits)!=3 or any(x.get('rows')!=80000 or not x.get('pipeline_sha256') for x in fits) or tune.get('planned_trial_slots')!=15 or tune.get('executed_phase_receipts')!=13 or tune.get('max_peak_rss_kib')!=3697924:return False,None
    if exp==4:
        ev=arf.get('E4_altered_cohorts') or {}
        if ev.get('rows_each')!=80000 or ev.get('trials_per_task')!=5:return False,None
        pid=E4_ARF_6G_PROFILE_ID
    else:
        ev=arf.get('E5_direct_ARF') or {}
        if ev.get('ready_fixed_refits')!=27 or ev.get('trials_per_task')!=0 or ev.get('input_shape_each')!=[80000,6]:return False,None
        pid=E5_ARF_6G_PROFILE_ID
    return True,{'profile_id':pid,'reservation_gib':6,'train_key':expect,'dependency_fit_key':base,'shape':[80000,6],'resource_audit_sha256':E4_RF_EXTENSION_SHA,'observed_max_phase_rss_kib':3697924,'reason':'same-family 80k ARF resource analogy; estimate only; 10 GiB hard limit, timeout and promotion retained'}

def eligible_e4_weighted_rf_fit_5gib(t,d,root):
    try:return _eligible_e4_weighted_rf_5g(t,d,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None
def eligible_e4_arf_fit_6gib(t,d,root):
    try:return _eligible_arf_6g(t,d,root,4)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None
def eligible_e5_arf_fit_6gib(t,d,root):
    try:return _eligible_arf_6g(t,d,root,5)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None

def eligible_e4_treatment_rf_fit_5gib(t,definition,root):
    try:return _eligible_e4_treatment_rf_fit_5gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None


def _e4_generated_rf_npz_shapes(path, members):
    out={}
    try:
        with zipfile.ZipFile(path) as z:
            for name in members:
                with z.open(name+'.npy') as f:
                    version=np.lib.format.read_magic(f)
                    if version==(1,0): shape,_,_=np.lib.format.read_array_header_1_0(f)
                    elif version in ((2,0),(3,0)): shape,_,_=np.lib.format.read_array_header_2_0(f)
                    else:return None
                    out[name]=tuple(shape)
        return out
    except Exception:return None

def _e4_generated_rf_role_context(root,rep):
    root=pathlib.Path(root); plan_path=root/'manifests/plan_summary.json'
    tasks_path=root/'manifests/tasks.json'; freeze_path=root/'manifests/freeze.json'
    cache_path=root/'cache/cache_manifest.json'
    if (_sha256_cached(plan_path)!=E4_GENERATED_RF_6G_PLAN_SUMMARY_SHA256
        or _sha256_cached(tasks_path)!=E4_GENERATED_RF_6G_TASKS_SHA256
        or _sha256_cached(cache_path)!=E4_GENERATED_RF_6G_CACHE_MANIFEST_SHA256):
        return None
    plan,cache,freeze=_json(plan_path),_json(cache_path),_json(freeze_path)
    if not isinstance(plan,dict) or not isinstance(cache,dict) or not isinstance(freeze,dict):return None
    if (freeze.get('plan_sha256')!=E4_GENERATED_RF_6G_TASKS_SHA256
        or plan.get('cache_manifest_sha256')!=E4_GENERATED_RF_6G_CACHE_MANIFEST_SHA256
        or cache.get('test_rows')!=500000
        or cache.get('features')!=['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']
        or cache.get('labels')!=['A','F','G','K','M','GALAXY','QSO']):
        return None
    src=freeze.get('source_sha256') or {}
    if (src.get('science.py')!=E4_GENERATED_RF_6G_FROZEN_SCIENCE_SHA
        or src.get('worker.py')!=E4_GENERATED_RF_6G_FROZEN_WORKER_SHA
        or src.get('phase_worker.py')!=E4_GENERATED_RF_6G_FROZEN_PHASE_SHA
        or src.get('cohorts.py')!=E4_GENERATED_RF_6G_FROZEN_COHORTS_SHA):
        return None
    role_key=f'roles/rep_{rep}.npz'; role_path=root/'cache'/role_key
    role_sha=E4_GENERATED_RF_6G_ROLE_CACHE_SHA.get(rep)
    source_sha=E4_GENERATED_RF_6G_ROLE_SOURCE_SHA.get(rep)
    role_meta=(cache.get('roles') or {}).get(str(rep)) or {}
    role_file_sha=(cache.get('cache_files') or {}).get(role_key)
    expected_role_hash=(plan.get('role_membership_hashes') or {}).get(f'rep_{rep}')
    if (not role_sha or role_file_sha!=role_sha or expected_role_hash!=source_sha
        or role_meta.get('source_sha256')!=source_sha
        or sum(role_meta.get('fit_counts',[]))!=80000
        or _sha256_cached(role_path)!=role_sha):
        return None
    role_source=pathlib.Path(str(role_meta.get('source','')))
    if not role_source.is_file() or _sha256_cached(role_source)!=source_sha:return None
    role_shapes=_e4_generated_rf_npz_shapes(role_path,('X_fit','y_fit','fit_ids','X_tune','y_tune','tuning_ids','X_cal','y_cal','calibration_ids'))
    expected_role_shapes={'X_fit':(80000,6),'y_fit':(80000,),'fit_ids':(80000,),
        'X_tune':(10000,6),'y_tune':(10000,),'tuning_ids':(10000,),
        'X_cal':(10000,6),'y_cal':(10000,),'calibration_ids':(10000,)}
    if role_shapes!=expected_role_shapes:return None
    test_sha=E4_GENERATED_RF_6G_TEST_CACHE_SHA
    if ((cache.get('cache_files') or {}).get('test.npz')!=test_sha
        or _sha256_cached(root/'cache'/'test.npz')!=test_sha):
        return None
    test_shapes=_e4_generated_rf_npz_shapes(root/'cache'/'test.npz',('X','y','ids'))
    if test_shapes!={'X':(500000,6),'y':(500000,),'ids':(500000,)}:return None
    model_basic=pathlib.Path(root).parent/'project'/'benchmark'/'models_basic.py'
    if _sha256_cached(model_basic)!=E4_RF_FIT_5G_MODELS_BASIC_SHA256:return None
    return {'role_cache_sha256':role_sha,'role_source_sha256':source_sha,
        'role_id_hashes':dict(role_meta.get('id_hashes') or {}),
        'fit_counts':list(role_meta.get('fit_counts') or []),
        'cache_manifest_sha256':E4_GENERATED_RF_6G_CACHE_MANIFEST_SHA256,
        'plan_summary_sha256':E4_GENERATED_RF_6G_PLAN_SUMMARY_SHA256,
        'tasks_sha256':E4_GENERATED_RF_6G_TASKS_SHA256,
        'test_cache_sha256':test_sha,'feature_order':list(cache['features']),
        'role_shapes':{k:list(v) for k,v in role_shapes.items()},
        'test_shape':{'X':[500000,6],'y':[500000],'ids':[500000]},
        'models_basic_sha256':E4_RF_FIT_5G_MODELS_BASIC_SHA256}

def _e4_generated_rf_review_provenance(root,fit_key,train_key):
    root=pathlib.Path(root)
    ap=root/E4_GENERATED_RF_6G_AUDIT_PATH
    rp=root/E4_GENERATED_RF_6G_RECEIPT_PATH
    if _sha256_cached(ap)!=E4_GENERATED_RF_6G_AUDIT_SHA256 or _sha256_cached(rp)!=E4_GENERATED_RF_6G_RECEIPT_SHA256:return None
    audit,receipt=_json(ap),_json(rp)
    if not isinstance(audit,dict) or not isinstance(receipt,dict):return None
    if (audit.get('schema_version')!='lamost-e4-generated-restoration-rf-admission-review/2'
        or audit.get('registry_snapshot',{}).get('plan_sha256')!=E4_GENERATED_RF_6G_TASKS_SHA256
        or audit.get('receipt_manifest',{}).get('path')!='runtime_20261025/'+E4_GENERATED_RF_6G_RECEIPT_PATH
        or audit.get('receipt_manifest',{}).get('sha256')!=E4_GENERATED_RF_6G_RECEIPT_SHA256
        or audit.get('receipt_manifest',{}).get('item_count')!=len(receipt.get('items',[]))
        or audit.get('receipt_manifest',{}).get('source_hashes',{}).get('science.py')!=E4_GENERATED_RF_6G_FROZEN_SCIENCE_SHA
        or audit.get('prior_reviews',{}).get('immutable_v1_sha256')!='50a7d36aef1577afab5d99b763bd9eef4c462a6aa604284f1ec7f8511fe80711'):
        return None
    if audit.get('prior_reviews',{}).get('immutable_v1_file_manifest_sha256')!=E4_GENERATED_RF_6G_FILE_MANIFEST_SHA256:return None
    if receipt.get('schema_version')!='lamost-e4-generated-rf-receipt-index/2' or receipt.get('registry_plan_sha256')!=E4_GENERATED_RF_6G_TASKS_SHA256:return None
    items=receipt.get('items') or []
    found={}
    for category,filename in (('append_metadata','metadata.json'),('append_validation','validation.json')):
        rel=(pathlib.Path('artifacts')/train_key/filename).as_posix()
        matches=[x for x in items if x.get('path')==f'runtime_20261025/{rel}' and x.get('task_key')==fit_key and x.get('dependency_key')==train_key and x.get('category')==category]
        if len(matches)!=1:return None
        live_path=root/'artifacts'/train_key/filename
        if _sha256_cached(live_path)!=matches[0].get('sha256'):return None
        found[category]=matches[0].get('sha256')
    return {'audit_sha256':E4_GENERATED_RF_6G_AUDIT_SHA256,
        'receipt_sha256':E4_GENERATED_RF_6G_RECEIPT_SHA256,
        'file_manifest_sha256':E4_GENERATED_RF_6G_FILE_MANIFEST_SHA256,
        'append_metadata_sha256':found['append_metadata'],
        'append_validation_sha256':found['append_validation']}

def _e4_generated_rf_generated_artifact_valid(root,definition,rep,base,generator,target_index,added):
    root=pathlib.Path(root)
    key=f'e4/rep_{rep}/generate/{base}/{generator}'
    fit_key=f'e4/rep_{rep}/fit/direct/{generator}/{base}'
    cohort_key=f'e4/rep_{rep}/cohort/{base}'
    p=root/'artifacts'/key
    result,validation=(_json(p/name) for name in ('generation_result.json','validation.json'))
    if not isinstance(result,dict) or not isinstance(validation,dict):return None
    task=result.get('task') or {};out=result.get('result') or {}
    if (result.get('status')!='successful' or out.get('status')!='success'
        or task.get('key')!=key or task.get('experiment')!=4 or int(task.get('rep',-1))!=rep
        or task.get('kind')!='generate' or task.get('generator')!=generator
        or task.get('condition')!=base or task.get('cohort_key')!=cohort_key
        or task.get('fit_key')!=fit_key or task.get('target_class')!=target_index
        or task.get('restored_share')!='original_target_share' or task.get('added_count')!=added
        or out.get('n_rows')!=added or out.get('generation_seed')!=task.get('seed')):
        return None
    counts=out.get('class_counts')
    if not isinstance(counts,list) or len(counts)!=7 or any(type(x)is not int for x in counts):return None
    if counts!=[added if i==target_index else 0 for i in range(7)]:return None
    expected=(validation.get('files') or {}).get('data.npz')
    data=root/'artifacts'/key/'data.npz'
    if (validation.get('status')!='validated' or validation.get('task_key')!=key
        or not isinstance(expected,str) or out.get('data_sha256')!=expected
        or _sha256_cached(data)!=expected):
        return None
    shapes=_e4_generated_rf_npz_shapes(data,('X','y'))
    if shapes!={'X':(added,6),'y':(added,)}:return None
    # Bind generation to the exact selected generator fit trained on the altered cohort.
    ok=_valid_published_fit(root,fit_key,4,rep,generator,cohort_key,expected_rows=80000)
    if not ok:return None
    fit_art=root/'artifacts'/fit_key
    fit_result=_json(fit_art/'fit_result.json') or {}
    fit_task=fit_result.get('task') or {};fit_out=fit_result.get('result') or {}
    fit_validation=_json(fit_art/'validation.json') or {};fit_selection=_json(fit_art/'selection.json') or {}
    if (fit_task.get('kind')!='fit' or fit_task.get('route')!='direct'
        or fit_task.get('selection_mode')!='tune' or fit_task.get('trials')!=E4_GENERATED_RF_6G_GENERATOR_TRIALS.get(generator)
        or fit_task.get('selection_policy')!='tune_on_matching_altered_cohort'
        or fit_task.get('seed') is None or fit_task.get('optimizer_seed') is None
        or fit_validation.get('files',{}).get('selection.json')!=_sha256_cached(fit_art/'selection.json')
        or fit_selection.get('selected_params')!=fit_out.get('params')
        or fit_out.get('training_rows')!=80000):
        return None
    return {'generation_key':key,'generator_fit_key':fit_key,'generation_data_sha256':expected,
        'generation_rows':added,'generation_seed':out.get('generation_seed')}

def _eligible_e4_generated_restoration_rf_6gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t):return False,None
    try:
        rep=int(definition.get('rep'));cond=definition.get('condition');treatment=definition.get('treatment')
        key=definition.get('key');train=definition.get('train_key')
    except (TypeError,ValueError):return False,None
    if (rep not in (1,2,3) or definition.get('experiment')!=4 or definition.get('kind')!='fit'
        or definition.get('method')!='random_forest' or definition.get('route')!='treatment'
        or t.get('key')!=key or not isinstance(cond,str) or not isinstance(treatment,str)
        or not treatment.startswith('generated_')):
        return False,None
    generator=treatment[len('generated_'):]
    if generator not in ('gmm','copula','arf','kde','chow_liu') or definition.get('generator')!=generator:return False,None
    base=cond.removesuffix('_'+treatment)
    expected_train=f'e4/rep_{rep}/append/{base}/{generator}'
    parent=f'e4/rep_{rep}/cohort/{base}'
    if (base not in E4_TREATMENT_BASES or cond!=base+'_'+treatment
        or key!=f'e4/rep_{rep}/fit/treatment/random_forest/{cond}'
        or train!=expected_train or definition.get('dependencies')!=[expected_train]
        or definition.get('selection_mode')!='tune' or definition.get('trials')!=10
        or definition.get('selection_key') is not None or definition.get('selection_source') is not None
        or definition.get('selection_policy')!='tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget'):
        return False,None
    match_fields=('key','experiment','rep','kind','method','route','condition','treatment','generator','train_key',
        'dependencies','selection_mode','selection_policy','selection_key','selection_source','trials','seed','optimizer_seed')
    if any(t.get(f)!=definition.get(f) for f in match_fields):return False,None
    # Confirm the task remains never-attempted even if a caller passed a stale candidate copy.
    if t.get('attempts') or t.get('admission_reservation_bytes') is not None:return False,None
    cohort_ok=_valid_cohort(root,parent,4,rep,base)
    cohort_meta=_json(pathlib.Path(root)/'artifacts'/parent/'metadata.json') or {}
    cohort_artifact=_valid_npz_artifact(root,parent)
    if (not cohort_ok or not cohort_artifact or cohort_artifact[1]!={'X':(80000,6),'y':(80000,),'ids':(80000,)}
        or cohort_meta.get('tune_calibration_reserved') is not True
        or cohort_meta.get('sample_weight_included') is not False
        or cohort_meta.get('target_class')!=E4_LABELS.index(str(cond).split('_')[0])):
        return False,None
    train_valid=_valid_npz_artifact(root,expected_train)
    if not train_valid:return False,None
    append_meta,shapes=train_valid
    if append_meta.get('kind')!='e4_append' or append_meta.get('task_key')!=expected_train:return False,None
    if pathlib.Path(str(append_meta.get('parent',''))).resolve()!=(pathlib.Path(root)/'artifacts'/parent).resolve():return False,None
    if append_meta.get('generated_artifact')!=str(pathlib.Path(root)/'artifacts'/f'e4/rep_{rep}/generate/{base}/{generator}'):return False,None
    before=append_meta.get('counts_before');after=append_meta.get('counts_after')
    if not isinstance(before,list) or before!=cohort_meta.get('realized_counts') or not isinstance(after,list) or len(after)!=7:return False,None
    target_index=E4_LABELS.index(base.split('_')[0]);added=append_meta.get('added_count')
    if type(added)is not int or added<=0 or append_meta.get('target_class')!=target_index:return False,None
    expected_after=list(before);expected_after[target_index]+=added
    if after!=expected_after:return False,None
    rows=sum(after)
    if rows<80000 or rows>E4_GENERATED_RF_6G_MAX_ROWS:return False,None
    if shapes!={'X':(rows,6),'y':(rows,),'ids':(rows,)}:return False,None
    role_evidence=_e4_generated_rf_role_context(root,rep)
    if not role_evidence or cohort_meta.get('source_fit_counts')!=role_evidence.get('fit_counts'):return False,None
    receipt_evidence=_e4_generated_rf_review_provenance(root,key,expected_train)
    if not receipt_evidence:return False,None
    generated=_e4_generated_rf_generated_artifact_valid(root,definition,rep,base,generator,target_index,added)
    if not generated:return False,None
    return True,{'profile_id':E4_GENERATED_RF_6G_PROFILE_ID,'reservation_gib':6,
        'reason':'prospective admission estimate for never-attempted E4 generated-restoration RF fits within the reviewed training-row envelope; retain 10 GiB hard cap and dynamic promotion',
        'training_rows':rows,'added_target_rows':added,'target_class':target_index,'condition':cond,
        'generator':generator,'train_key':expected_train,'cohort_key':parent,
        'npz_header_shapes':{'X':[rows,6],'y':[rows],'ids':[rows]},
        'role_evidence':role_evidence,'review_evidence':receipt_evidence,'generation_evidence':generated,
        'resource_audit_path':E4_GENERATED_RF_6G_AUDIT_PATH,'resource_audit_sha256':E4_GENERATED_RF_6G_AUDIT_SHA256,
        'receipt_manifest_path':E4_GENERATED_RF_6G_RECEIPT_PATH,'receipt_manifest_sha256':E4_GENERATED_RF_6G_RECEIPT_SHA256,
        'observed_rows_max':E4_GENERATED_RF_6G_MAX_ROWS,'worker_hard_rss_limit_gib':10,
        'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,
        'admission_only_estimate_not_hard_limit':True,'dynamic_promotion_to_10gib_retained':True}

def eligible_e4_generated_restoration_rf_fit_6gib(t,definition,root):
    try:return _eligible_e4_generated_restoration_rf_6gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):
        return False,None

def eligible_rf_resource_profiles(t, definition, root):
    try:
        ok,evidence=_eligible_e5_direct_rf_4gib(t,definition,root)
        if ok:return ok,evidence
        for fn in (_eligible_e4_weighted_rf_5g,lambda a,b,c:_eligible_arf_6g(a,b,c,4),lambda a,b,c:_eligible_arf_6g(a,b,c,5),_eligible_e4_treatment_rf_fit_5gib,_eligible_e4_treatment_rf_6gib,_eligible_e4_generated_restoration_rf_6gib):
            ok,evidence=fn(t,definition,root)
            if ok:return ok,evidence
        return False,None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, EOFError, zipfile.BadZipFile):
        return False,None


E5_GENERATION_2G_PROFILE_ID='e5-nonarf-400k-generation-admission-2gib-20261026'
E5_GENERATION_METHODS={'gmm','copula','chow_liu','kde'}
_E5_LABEL_COUNTS_CACHE={}

def _npz_label_counts(path, expected_sha):
    p=pathlib.Path(path).resolve()
    try:
        st=p.stat(); ident=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,expected_sha)
        old=_E5_LABEL_COUNTS_CACHE.get(str(p))
        if old and old[0]==ident: return old[1]
        if _sha256_cached(p)!=expected_sha: return None
        with np.load(p,allow_pickle=False) as z:
            arr=np.asarray(z['y'])
        if arr.shape!=(80000,) or not np.issubdtype(arr.dtype,np.integer): return None
        counts=np.bincount(arr.astype(np.int64,copy=False),minlength=7)
        if len(counts)!=7 or int(counts.sum())!=80000: return None
        after=p.stat();ident_after=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns,expected_sha)
        if ident_after!=ident or _sha256_cached(p)!=expected_sha: return None
        out=[int(x) for x in counts]
        _E5_LABEL_COUNTS_CACHE[str(p)]=(ident_after,out)
        return out
    except (OSError,ValueError,TypeError,KeyError,EOFError,zipfile.BadZipFile): return None

def _eligible_e5_nonarf_generation_2gib(t, definition, root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    try:
        rep=int(definition.get('rep')); gen=definition.get('generator')
        cond=definition.get('condition'); key=definition.get('key'); fit=definition.get('fit_key')
        train=f'e5/rep_{rep}/corruption/{cond}'; clean=f'e3/rep_{rep}/fit/{gen}'
    except (TypeError,ValueError): return False,None
    if (rep not in (1,2,3) or gen not in E5_GENERATION_METHODS
        or definition.get('experiment')!=5 or definition.get('kind')!='generate'
        or definition.get('method') is not None or definition.get('route') is not None
        or cond not in E5_CONDITIONS or not _e5_mechanism_rate_matches(definition,cond) or key!=f'e5/rep_{rep}/generate/{cond}/{gen}'
        or t.get('key')!=key or fit!=f'e5/rep_{rep}/fit/direct/{gen}/{cond}'
        or definition.get('dependencies')!=[fit] or definition.get('n_rows')!=400000
        or definition.get('cohort_key') is not None or definition.get('ratio') is not None):
        return False,None
    cohort=_valid_npz_artifact(root,train)
    if not cohort: return False,None
    cohort_meta,shapes=cohort
    if cohort_meta.get('kind')!='e5_corruption' or cohort_meta.get('rep')!=rep or cohort_meta.get('mechanism')+'_'+str(int(round(float(cohort_meta.get('rate'))*100))).zfill(2)!=cond:
        return False,None
    if shapes!={'X':(80000,6),'y':(80000,),'ids':(80000,)}: return False,None
    base_result=_json(pathlib.Path(root)/'artifacts'/clean/'fit_result.json') or {}
    base_task=base_result.get('task') or {}
    if base_task.get('method')!=gen or base_task.get('route')!='generator': return False,None
    if not _valid_published_fit(root,clean,3,rep,gen,base_task.get('train_key')): return False,None
    base_selection=_json(pathlib.Path(root)/'artifacts'/clean/'selection.json') or {}
    selected=base_selection.get('selected_params')
    if not isinstance(selected,dict) or base_result.get('result',{}).get('params')!=selected: return False,None
    fit_result=_json(pathlib.Path(root)/'artifacts'/fit/'fit_result.json') or {}
    fit_task=fit_result.get('task') or {};fit_res=fit_result.get('result') or {}
    if (fit_task.get('key')!=fit or fit_task.get('experiment')!=5 or fit_task.get('rep')!=rep
        or fit_task.get('method')!=gen or fit_task.get('route')!='direct'
        or fit_task.get('condition')!=cond or fit_task.get('mechanism')!=definition.get('mechanism') or fit_task.get('rate')!=definition.get('rate') or fit_task.get('train_key')!=train
        or fit_task.get('selection_key')!=clean or fit_task.get('selection_mode')!='fixed'
        or fit_task.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
        or fit_task.get('trials')!=0 or fit_task.get('dependencies')!=[train,clean]):
        return False,None
    if not _valid_published_fit(root,fit,5,rep,gen,train,require_publication=True): return False,None
    if fit_res.get('params')!=selected: return False,None
    train_path=pathlib.Path(root)/'artifacts'/train/'data.npz'
    train_sha=_sha256_cached(train_path)
    if not train_sha or fit_res.get('source_sha256')!=train_sha: return False,None
    counts=_npz_label_counts(train_path,train_sha)
    if counts is None or fit_res.get('class_counts')!=counts: return False,None
    return True,{'profile_id':E5_GENERATION_2G_PROFILE_ID,'reservation_gib':2,'reason':'validated exact E5 non-ARF 400k generation task with matching selected E3/E5 fit configuration and input labels','generator':gen,'fit_key':fit,'clean_selection_key':clean,'train_key':train,'training_rows':80000,'training_class_counts':counts,'n_rows':400000,'generation_ratio':5,'npz_header_shapes':{'X':[80000,6],'y':[80000],'ids':[80000]},'memory_evidence':'E3 family analogs: all 400k by six; non-ARF observed generation phase max under 0.30 GiB. E5 generation itself remains unmeasured; 2 GiB is provisional; hard limit and dynamic promotion remain unchanged.'}

def eligible_2gib_resource_profile(t, definition, root):
    try:
        if isinstance(definition,dict) and definition.get('kind')=='generate':
            return _eligible_e5_nonarf_generation_2gib(t,definition,root)
        return eligible_2gib_generator_fit(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):
        return False,None


# Narrow provisional admission estimate for never-attempted E5 direct RF evaluations.
# It is an analogy based on E5 fit RSS plus matching E3 clean RF inference receipts;
# no E5 corrupted-pipeline inference RSS has been observed. The process hard cap stays 10 GiB.
E5_RF_EVAL_4G_PROFILE_ID = 'e5-direct-rf-eval-analogy-4gib-20261026'
E5_RF_EVAL_4G_RECEIPT = 'staging/resource_followup_e5_e4_rf_20261026/E5_E4_RF_RESOURCE_FOLLOWUP_20261026.json'
E5_RF_EVAL_4G_RECEIPT_SHA256 = '9884af26a84d04e5be913d651d36f9b055dda7613a8e2f95b73a137626de4754'
E5_RF_EVAL_EXPECTED_PARAMS = dict(E5_RF_EXPECTED_SELECTED_PARAMS)
E5_RF_EVAL_FIT_RECEIPTS_N = 20
E5_RF_EVAL_MAX_FIT_RSS_KIB = 2016892
E5_RF_EVAL_CLEAN_EVAL_RECEIPTS_N = 3
E5_RF_EVAL_MAX_CLEAN_EVAL_RSS_KIB = 1299664
E5_RF_EVAL_TEST_ROWS = 500000
E5_RF_EVAL_CHUNK_ROWS = 50000
_E5_FROZEN_PLAN_CACHE = {}


def _all_npz_header_shapes(path):
    """Read member headers only; do not decompress or load NPZ arrays."""
    out = {}
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith('.npy'):
                    continue
                with z.open(name) as f:
                    version = np.lib.format.read_magic(f)
                    if version == (1,0): shape, _, _ = np.lib.format.read_array_header_1_0(f)
                    elif version in ((2,0),(3,0)): shape, _, _ = np.lib.format.read_array_header_2_0(f)
                    else: return None
                    out[name[:-4]] = tuple(shape)
        return out
    except Exception:
        return None


def _e5_frozen_cache_context(root):
    root=pathlib.Path(root)
    plan_path=root/'manifests/tasks.json'; cache_path=root/'cache/cache_manifest.json'
    try:
        st=plan_path.stat(); ident=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        cached=_E5_FROZEN_PLAN_CACHE.get(str(plan_path.resolve()))
        if cached and cached[0]==ident: plan=cached[1]
        else:
            plan=_json(plan_path)
            if not isinstance(plan,dict): return None
            _E5_FROZEN_PLAN_CACHE[str(plan_path.resolve())]=(ident,plan)
        if not isinstance(plan.get('cache_manifest_sha256'),str) or _sha256_cached(cache_path)!=plan['cache_manifest_sha256']:
            return None
        cache=_json(cache_path)
        if not isinstance(cache,dict): return None
        return plan,cache
    except (OSError,TypeError,ValueError):
        return None


def _valid_e5_rf_eval_role_caches(root, rep, baseline_ids_sha=None):
    context=_e5_frozen_cache_context(root)
    if not context: return None
    plan,cache=context; root=pathlib.Path(root); rep_key=f'rep_{rep}'
    if cache.get('features') != ['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']:
        return None
    if cache.get('labels') != ['A','F','G','K','M','GALAXY','QSO'] or int(cache.get('test_rows',-1)) != E5_RF_EVAL_TEST_ROWS:
        return None
    role=cache.get('roles',{}).get(str(rep)); expected_membership=(plan.get('role_membership_hashes') or {}).get(rep_key)
    if not isinstance(role,dict) or role.get('source_sha256') != expected_membership:
        return None
    id_hashes=role.get('id_hashes') or {}
    if (baseline_ids_sha is not None and id_hashes.get('fit_ids') != baseline_ids_sha) or not id_hashes.get('calibration_ids'):
        return None
    files=cache.get('cache_files') or {}
    test_path=root/'cache/test.npz'; role_path=root/'cache/roles'/f'rep_{rep}.npz'
    if _sha256_cached(test_path) != files.get('test.npz') or _sha256_cached(role_path) != files.get(f'roles/rep_{rep}.npz'):
        return None
    if _all_npz_header_shapes(test_path) != {'X':(E5_RF_EVAL_TEST_ROWS,6),'y':(E5_RF_EVAL_TEST_ROWS,),'ids':(E5_RF_EVAL_TEST_ROWS,)}:
        return None
    role_shapes=_all_npz_header_shapes(role_path)
    if not isinstance(role_shapes,dict): return None
    expected={'X_fit':(80000,6),'y_fit':(80000,),'fit_ids':(80000,),
              'X_tune':(10000,6),'y_tune':(10000,),'tuning_ids':(10000,),
              'X_cal':(10000,6),'y_cal':(10000,),'calibration_ids':(10000,)}
    if any(role_shapes.get(k)!=v for k,v in expected.items()): return None
    freeze=_json(root/'manifests/freeze.json') or {}
    policy=freeze.get('resource_policy') or {}
    frozen_sources=freeze.get('source_sha256') or {}
    science_path=root/'source/science.py'
    science_sha=_sha256_cached(science_path)
    if policy.get('prediction_chunk_rows') != E5_RF_EVAL_CHUNK_ROWS:
        return None
    if frozen_sources.get('science.py') != science_sha:
        return None
    try: source_text=science_path.read_text()
    except OSError: return None
    if 'def _chunks_with_support(model,X,size=50000):' not in source_text or 'for i in range(0,len(X),size):' not in source_text:
        return None
    return {'cache_manifest_sha256':plan['cache_manifest_sha256'],'test_npz_sha256':files['test.npz'],
            'test_header_shapes':{'X':[E5_RF_EVAL_TEST_ROWS,6],'y':[E5_RF_EVAL_TEST_ROWS],'ids':[E5_RF_EVAL_TEST_ROWS]},
            'role_npz_sha256':files[f'roles/rep_{rep}.npz'],'role_membership_sha256':expected_membership,
            'fit_ids_sha256':id_hashes['fit_ids'],'calibration_ids_sha256':id_hashes['calibration_ids'],
            'calibration_shape':[10000,6],'labels':cache['labels'],'features':cache['features'],
            'test_rows':E5_RF_EVAL_TEST_ROWS,'prediction_chunk_rows':E5_RF_EVAL_CHUNK_ROWS,
            'science_sha256':science_sha}


def _e5_rf_eval_historical_receipt(root):
    path=pathlib.Path(root)/E5_RF_EVAL_4G_RECEIPT
    if _sha256_cached(path) != E5_RF_EVAL_4G_RECEIPT_SHA256: return None
    doc=_json(path)
    if not isinstance(doc,dict): return None
    e5=doc.get('e5_direct_rf') or {}; rows=e5.get('successful_fit_resource_receipts') or []
    if len(rows) != E5_RF_EVAL_FIT_RECEIPTS_N: return None
    for r in rows:
        phase=r.get('fit_phase') or {}; match=r.get('matches_E3_clean') or {}
        if (r.get('fit_rows') != 80000 or r.get('params') != E5_RF_EVAL_EXPECTED_PARAMS
            or phase.get('peak_tree_rss_kib') is None or int(phase['peak_tree_rss_kib']) > E5_RF_EVAL_MAX_FIT_RSS_KIB
            or not match.get('same_selected_params_as_E3_clean_real')
            or not match.get('same_training_ids_as_E3_clean_real')
            or not match.get('matching_E3_config_n_estimators')
            or not match.get('published_pipeline_sha_matches_fit_result')):
            return None
    e3=(doc.get('e3_clean_real_rf_reference') or {}).get('matching_fit_and_eval_repetitions') or []
    if len(e3) != E5_RF_EVAL_CLEAN_EVAL_RECEIPTS_N: return None
    reps=set()
    for r in e3:
        ep=r.get('eval_phase') or {}; identity=r.get('eval_pipeline_identity') or {}
        if (r.get('rep') not in (1,2,3) or r.get('fit_rows') != 80000
            or r.get('params') != E5_RF_EVAL_EXPECTED_PARAMS
            or identity.get('test_n') != E5_RF_EVAL_TEST_ROWS
            or ep.get('peak_tree_rss_kib') is None
            or int(ep['peak_tree_rss_kib']) > E5_RF_EVAL_MAX_CLEAN_EVAL_RSS_KIB
            or ep.get('exit_code') != 0 or not identity.get('pipeline_sha256')):
            return None
        reps.add(r['rep'])
    assessment=doc.get('prospective_assessment') or {}
    if reps != {1,2,3} or 'UNPROVEN' not in str(assessment.get('E5_direct_RF_eval_4GiB',{}).get('decision','')).upper():
        return None
    return {'receipt_path':E5_RF_EVAL_4G_RECEIPT,'receipt_sha256':E5_RF_EVAL_4G_RECEIPT_SHA256,
            'e5_fit_receipts':len(rows),'e5_fit_max_phase_rss_kib':max(int(r['fit_phase']['peak_tree_rss_kib']) for r in rows),
            'e3_clean_eval_receipts':len(e3),'e3_clean_eval_max_phase_rss_kib':max(int(r['eval_phase']['peak_tree_rss_kib']) for r in e3),
            'e5_corrupted_inference_receipts':0,'interpretation':'Analogy only; no E5 corrupted-model evaluation RSS has been observed.'}


def _eligible_e5_direct_rf_eval_4gib(t, definition, root):
    """4 GiB admission estimate for exact, never-attempted E5 direct RF evals only."""
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    try:
        rep=int(definition.get('rep')); cond=definition.get('condition'); key=definition.get('key')
        train=f'e5/rep_{rep}/corruption/{cond}'; base=f'e3/rep_{rep}/fit/real/random_forest'
        fit=f'e5/rep_{rep}/fit/direct/random_forest/{cond}'
    except (TypeError,ValueError): return False,None
    if (rep not in (1,2,3) or definition.get('experiment')!=5 or definition.get('kind')!='eval'
        or definition.get('route')!='direct' or definition.get('method')!='random_forest'
        or cond not in E5_CONDITIONS or not _e5_mechanism_rate_matches(definition,cond)
        or key!=f'e5/rep_{rep}/eval/direct/random_forest/{cond}' or t.get('key')!=key
        or definition.get('fit_key')!=fit or definition.get('dependencies')!=[fit]):
        return False,None
    if not _valid_cohort(root,train,5,rep,cond): return False,None
    result_doc=_json(pathlib.Path(root)/'artifacts'/fit/'fit_result.json') or {}
    fit_task=result_doc.get('task') or {}; fit_result=result_doc.get('result') or {}
    expected_base=f'e3/rep_{rep}/fit/real/random_forest'
    if (fit_task.get('key')!=fit or fit_task.get('experiment')!=5 or fit_task.get('rep')!=rep
        or fit_task.get('method')!='random_forest' or fit_task.get('route')!='direct'
        or fit_task.get('condition')!=cond or fit_task.get('mechanism')!=definition.get('mechanism')
        or fit_task.get('rate')!=definition.get('rate') or fit_task.get('train_key')!=train
        or fit_task.get('dependencies')!=[train,expected_base]
        or fit_task.get('selection_key')!=expected_base or fit_task.get('selection_mode')!='fixed'
        or fit_task.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
        or fit_task.get('trials')!=0 or fit_task.get('reuse_pipeline')):
        return False,None
    if not _valid_published_fit(root,fit,5,rep,'random_forest',train,require_publication=True): return False,None
    if fit_result.get('params')!=E5_RF_EVAL_EXPECTED_PARAMS or fit_result.get('training_rows')!=80000:
        return False,None
    baseline_doc=_json(pathlib.Path(root)/'artifacts'/expected_base/'fit_result.json') or {}
    baseline_task=baseline_doc.get('task') or {}; baseline_result=baseline_doc.get('result') or {}
    frozen_context=_e5_frozen_cache_context(root)
    if not frozen_context:return False,None
    frozen_plan=frozen_context[0]
    baseline_definitions=[x for x in frozen_plan.get('tasks',[]) if isinstance(x,dict) and x.get('key')==expected_base]
    if len(baseline_definitions)!=1:return False,None
    baseline_definition=baseline_definitions[0]
    baseline_selection_path=pathlib.Path(root)/'artifacts'/expected_base/'selection.json'
    baseline_selection=_json(baseline_selection_path)
    baseline_validation=_json(pathlib.Path(root)/'artifacts'/expected_base/'validation.json') or {}
    baseline_train_key=baseline_definition.get('train_key')
    if (baseline_definition.get('experiment')!=3 or baseline_definition.get('kind')!='fit'
        or baseline_definition.get('rep')!=rep or baseline_definition.get('method')!='random_forest'
        or baseline_definition.get('route')!='real'
        or baseline_task.get('key')!=expected_base or baseline_task.get('experiment')!=baseline_definition.get('experiment')
        or baseline_task.get('rep')!=baseline_definition.get('rep') or baseline_task.get('method')!=baseline_definition.get('method')
        or baseline_task.get('route')!=baseline_definition.get('route')
        or baseline_task.get('train_key')!=baseline_train_key
        or baseline_task.get('dependencies')!=baseline_definition.get('dependencies')
        or baseline_result.get('params')!=E5_RF_EVAL_EXPECTED_PARAMS
        or not isinstance(baseline_selection,dict) or baseline_selection.get('selected_params')!=E5_RF_EVAL_EXPECTED_PARAMS
        or (baseline_validation.get('files') or {}).get('selection.json')!=_sha256_cached(baseline_selection_path)
        or not _valid_published_fit(root,expected_base,3,rep,'random_forest',baseline_train_key,require_publication=True)):
        return False,None
    ids_sha=fit_result.get('training_ids_sha256')
    if not ids_sha or ids_sha!=baseline_result.get('training_ids_sha256'):
        return False,None
    train_path=pathlib.Path(root)/'artifacts'/train/'data.npz'; train_sha=_sha256_cached(train_path)
    if not train_sha or fit_result.get('source_sha256')!=train_sha:
        return False,None
    # The selected E5 pipeline and selection record must be validated and published.
    val=_json(pathlib.Path(root)/'artifacts'/fit/'validation.json') or {}
    selpath=pathlib.Path(root)/'artifacts'/fit/'selection.json'; sel=_json(selpath)
    if (not isinstance(sel,dict) or sel.get('selected_params')!=E5_RF_EVAL_EXPECTED_PARAMS
        or (val.get('files') or {}).get('selection.json')!=_sha256_cached(selpath)):
        return False,None
    roles=_valid_e5_rf_eval_role_caches(root,rep,ids_sha)
    if not roles: return False,None
    history=_e5_rf_eval_historical_receipt(root)
    if not history: return False,None
    evidence={'profile_id':E5_RF_EVAL_4G_PROFILE_ID,'reservation_gib':4,
        'reason':'provisional analogy for never-attempted exact fixed 80k E5 direct RF evaluation; actual E5 corrupted-pipeline evaluation RSS is unobserved',
        'fit_key':fit,'clean_selection_key':expected_base,'train_key':train,'condition':cond,'rep':rep,
        'selected_params':dict(E5_RF_EVAL_EXPECTED_PARAMS),'training_rows':80000,
        'training_ids_sha256':ids_sha,'training_X_sha256':fit_result.get('training_X_sha256'),
        'training_y_sha256':fit_result.get('training_y_sha256'),'pipeline_sha256':fit_result.get('pipeline_sha256'),
        'role_cache_evidence':roles,'historical_resource_analogy':history,
        'analogy_only':True,'e5_inference_rss_observed':False,
        'worker_hard_rss_limit_gib':10,'phase_timeout_seconds':600,
        'reservation_caveat':'4 GiB is an admission reservation estimate only; it is not a process cap or proof of E5 inference RSS.'}
    return True,evidence


def eligible_e5_direct_rf_eval(t, definition, root):
    try:
        return _eligible_e5_direct_rf_eval_4gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):
        return False,None


def has_e5_direct_rf_eval_profile(t):
    """Persisted profile identity for already-admitted workers; promotions stay heavy."""
    if not isinstance(t,dict) or t.get('adaptive_promoted_heavy'): return False
    if t.get('admission_profile_id')!=E5_RF_EVAL_4G_PROFILE_ID or t.get('admission_reservation_bytes')!=4*GIB:
        return False
    evidence=t.get('admission_profile_evidence') or {}
    if evidence.get('profile_id')!=E5_RF_EVAL_4G_PROFILE_ID or evidence.get('reservation_gib')!=4 or evidence.get('e5_inference_rss_observed') is not False:
        return False
    attempts=t.get('attempts') or []
    if not attempts:return False
    profile=(attempts[-1].get('resource_profile') or {})
    return profile.get('admission_profile_id')==E5_RF_EVAL_4G_PROFILE_ID and profile.get('admission_reservation_bytes')==4*GIB


E4_RF_EVAL_6G_PROFILE_ID = 'e4-nonweighted-treatment-rf-eval-up-to-82394-analogy-6gib-20261026'
E4_RF_EVAL_MAX_TRAIN_ROWS = 82394
E4_RF_EVAL_MAX_FIT_PHASE_KIB = 4*1024*1024
E4_RF_EVAL_RECEIPT_MAX_KIB = 3869900
RF_FROZEN_N_ESTIMATORS = {200,500}
RF_FROZEN_MAX_DEPTH = {None,10,20}
RF_FROZEN_MIN_LEAF = {1,5,20}
RF_FROZEN_MAX_FEATURES = {'sqrt',1.0}


def _rf_params_in_frozen_domain(params):
    return (isinstance(params,dict)
        and params.get('n_estimators') in RF_FROZEN_N_ESTIMATORS
        and params.get('max_depth') in RF_FROZEN_MAX_DEPTH
        and params.get('min_samples_leaf') in RF_FROZEN_MIN_LEAF
        and params.get('max_features') in RF_FROZEN_MAX_FEATURES)


def _e4_rf_eval_historical_receipt(root):
    path=pathlib.Path(root)/E5_RF_EVAL_4G_RECEIPT
    if _sha256_cached(path)!=E5_RF_EVAL_4G_RECEIPT_SHA256:return None
    doc=_json(path)
    if not isinstance(doc,dict):return None
    e4=doc.get('e4_treatment_rf') or {}; rows=e4.get('eligible_completed_pairs') or []
    if len(rows)!=4:return None
    peaks=[]
    for r in rows:
        phase=r.get('eval_phase') or {}
        if (r.get('rep')!=1 or r.get('condition') not in {'A_half_generated_chow_liu','A_half_generated_copula','A_half_generated_gmm','A_half_generated_kde'}
            or not str(r.get('treatment','')).startswith('generated_') or r.get('fit_rows')!=82394
            or not r.get('pipeline_match') or r.get('evaluation_test_n')!=E5_RF_EVAL_TEST_ROWS
            or phase.get('exit_code')!=0 or phase.get('peak_tree_rss_kib') is None
            or int(phase['peak_tree_rss_kib'])>E4_RF_EVAL_RECEIPT_MAX_KIB
            or not _rf_params_in_frozen_domain(r.get('fit_params'))):
            return None
        peaks.append(int(phase['peak_tree_rss_kib']))
    if max(peaks)>E4_RF_EVAL_RECEIPT_MAX_KIB:return None
    return {'receipt_path':E5_RF_EVAL_4G_RECEIPT,'receipt_sha256':E5_RF_EVAL_4G_RECEIPT_SHA256,
        'completed_analog_eval_count':len(rows),'analog_eval_max_phase_rss_kib':max(peaks),
        'analog_fit_rows':82394,'analog_test_rows':E5_RF_EVAL_TEST_ROWS,
        'analog_scope':'rep 1, target A, half-share, generated GMM/copula/KDE/Chow-Liu only; this is not coverage of ROS, SMOTE, ARF, all classes, or all severities.'}


def _e4_treatment_rf_eval_data(root,rep,condition,treatment,fit_task):
    if treatment in ('ros','smote'):
        base=condition.removesuffix('_'+treatment); train=f'e4/rep_{rep}/treatment/{base}/{treatment}'; kind='e4_treatment';gen=None
    elif treatment.startswith('generated_'):
        gen=treatment[len('generated_'):]
        # ARF and KDE remain on the 10 GiB default profile; do not infer a new estimate for them.
        if gen not in ('gmm','copula','chow_liu'):return None
        base=condition.removesuffix('_'+treatment);train=f'e4/rep_{rep}/append/{base}/{gen}';kind='e4_append'
        if fit_task.get('generator')!=gen:return None
    else:return None
    if base not in E4_TREATMENT_BASES or condition!=base+'_'+treatment or fit_task.get('train_key')!=train or fit_task.get('dependencies')!=[train]:return None
    valid=_valid_npz_artifact(root,train)
    if not valid:return None
    meta,shapes=valid
    if meta.get('kind')!=kind:return None
    parent=f'e4/rep_{rep}/cohort/{base}'
    if pathlib.Path(str(meta.get('parent',''))).resolve()!=(pathlib.Path(root)/'artifacts'/parent).resolve():return None
    if not _valid_cohort(root,parent,4,rep,base):return None
    parent_meta=_json(pathlib.Path(root)/'artifacts'/parent/'metadata.json') or {}
    before=meta.get('counts_before');counts=meta.get('counts_after') or meta.get('counts')
    if not isinstance(before,list) or before!=parent_meta.get('realized_counts'):return None
    if not isinstance(counts,list) or len(counts)!=7 or any(type(x)is not int or x<0 for x in counts):return None
    target_index=E4_LABELS.index(base.split('_')[0]);added=meta.get('added_count')
    if type(added)is not int or added<0:return None
    expected=list(before);expected[target_index]+=added
    if counts!=expected:return None
    if kind=='e4_treatment':
        if meta.get('treatment')!=treatment:return None
    elif meta.get('target_class')!=target_index:return None
    rows=sum(counts)
    if rows<80000 or rows>E4_RF_EVAL_MAX_TRAIN_ROWS:return None
    if shapes!={'X':(rows,6),'y':(rows,),'ids':(rows,)}:return None
    return {'train_key':train,'parent_cohort_key':parent,'kind':kind,'treatment':treatment,'generator':gen,
            'training_rows':rows,'counts_before':before,'counts_after':counts,'added_count':added,
            'data_npz_sha256':_sha256_cached(pathlib.Path(root)/'artifacts'/train/'data.npz'),
            'npz_header_shapes':{'X':[rows,6],'y':[rows],'ids':[rows]}}


def _eligible_e4_treatment_rf_eval_6gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t):return False,None
    try:rep=int(definition.get('rep'));cond=definition.get('condition');treatment=definition.get('treatment');key=definition.get('key');fit=f'e4/rep_{rep}/fit/treatment/random_forest/{cond}'
    except (TypeError,ValueError):return False,None
    if (rep not in (1,2,3) or definition.get('experiment')!=4 or definition.get('kind')!='eval'
        or definition.get('route')!='treatment' or definition.get('method')!='random_forest'
        or t.get('key')!=key or not isinstance(cond,str) or not isinstance(treatment,str)
        or definition.get('fit_key')!=fit or definition.get('dependencies')!=[fit]
        or definition.get('target_label') not in E4_LABELS):return False,None
    fit_path=pathlib.Path(root)/'artifacts'/fit
    fit_doc=_json(fit_path/'fit_result.json') or {};ft=fit_doc.get('task') or {};fr=fit_doc.get('result') or {}
    if (fit_doc.get('status')!='successful' or fr.get('status')!='success'
        or ft.get('key')!=fit or ft.get('experiment')!=4 or int(ft.get('rep',-1))!=rep
        or ft.get('method')!='random_forest' or ft.get('route')!='treatment'
        or ft.get('condition')!=cond or ft.get('treatment')!=treatment
        or ft.get('selection_mode')!='tune' or ft.get('trials')!=10 or ft.get('selection_key') is not None
        or ft.get('selection_policy')!='tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget'):
        return False,None
    data=_e4_treatment_rf_eval_data(root,rep,cond,treatment,ft)
    if not data:return False,None
    if (fr.get('training_rows')!=data['training_rows'] or fr.get('class_counts')!=data['counts_after']
        or sum(fr.get('class_counts') or [])!=data['training_rows']
        or fr.get('source_sha256')!=data['data_npz_sha256']):return False,None
    phase=fr.get('phase_supervision') or {}
    if (phase.get('exit_code')!=0 or phase.get('reason') is not None or phase.get('peak_tree_rss_kib') is None
        or int(phase['peak_tree_rss_kib'])>E4_RF_EVAL_MAX_FIT_PHASE_KIB):return False,None
    if not _rf_params_in_frozen_domain(fr.get('params')):return False,None
    selection=_json(fit_path/'selection.json');validation=_json(fit_path/'validation.json') or {}
    if (not isinstance(selection,dict) or selection.get('selected_params')!=fr.get('params')
        or (validation.get('files') or {}).get('selection.json')!=_sha256_cached(fit_path/'selection.json')):return False,None
    if not _valid_published_fit(root,fit,4,rep,'random_forest',data['train_key'],require_publication=True,expected_rows=data['training_rows']):return False,None
    caches=_valid_e5_rf_eval_role_caches(root,rep,None)
    if not caches:return False,None
    history=_e4_rf_eval_historical_receipt(root)
    if not history:return False,None
    evidence={'profile_id':E4_RF_EVAL_6G_PROFILE_ID,'reservation_gib':6,
        'reason':'narrow per-model E4 RF evaluation admission estimate based on <=82,394-row published fit, exact histogram/input identity, <=4 GiB selected fit-phase RSS and four matched 500k-test evaluation analogs',
        'fit_key':fit,'train_key':data['train_key'],'condition':cond,'treatment':treatment,'rep':rep,
        'training_rows':data['training_rows'],'counts_before':data['counts_before'],'counts_after':data['counts_after'],
        'added_count':data['added_count'],'training_data':data,'selected_params':dict(fr['params']),
        'fit_pipeline_sha256':fr.get('pipeline_sha256'),'fit_phase_peak_tree_rss_kib':phase.get('peak_tree_rss_kib'),
        'fit_phase_seconds':phase.get('seconds'),'role_cache_evidence':caches,'historical_eval_analogy':history,
        'analogy_only':True,'this_fit_inference_rss_observed':False,'worker_hard_rss_limit_gib':10,
        'phase_timeout_seconds':600,'reservation_caveat':'6 GiB is a prospective admission reservation, not an RSS cap or proof of this fitted model inference peak.'}
    return True,evidence



E4_ARF_EVAL_2G_PROFILE_ID = 'e4-direct-arf-eval-80k-500k-admission-2gib-20261027'
E4_ARF_EVAL_2G_AUDIT_PATH = 'reports/engineering_audits/RESOURCE_THROUGHPUT_REVIEW_20261027.json'
E4_ARF_EVAL_2G_AUDIT_SHA256 = '5be794d336ea0e049643e1dd519418b4595ef41ed3955020b20cd0f69eb16fd9'
E4_ARF_EVAL_MAX_PIPELINE_BYTES = 34_000_000

def _arf_selected_params_in_domain(params, class_counts):
    return (isinstance(params, dict)
        and type(params.get('num_trees')) is int and params['num_trees'] in {100,300}
        and type(params.get('min_samples_leaf')) is int and params['min_samples_leaf'] in {5,20,100}
        and params['min_samples_leaf'] <= min(class_counts)
        and params.get('max_depth') in (None,10)
        and params.get('density_dist') == 'truncnorm'
        and params.get('finite_bounds') == 'no')

def _arf_eval_audit_evidence(root):
    path=pathlib.Path(root)/E4_ARF_EVAL_2G_AUDIT_PATH
    if _sha256_cached(path) != E4_ARF_EVAL_2G_AUDIT_SHA256: return None
    doc=_json(path)
    if not isinstance(doc,dict) or doc.get('audit_name') != 'resource_throughput_review_20261027': return None
    ev=((doc.get('historical_memory_evidence') or {}).get('arf_evaluation') or {})
    maxima=ev.get('phase_maxima_kib') or {}
    if (ev.get('successful_task_count') != 4 or ev.get('failed_or_incomplete_eval_attempts') != 0
        or maxima != {'calibrate':576476,'evaluate':805920,'all_phases':805920}
        or ev.get('test_rows') != 500000 or ev.get('calibration_rows') != 10000
        or ev.get('predictor_count') != 6 or ev.get('prediction_chunk_rows') != 50000
        or ev.get('largest_observed_pipeline_bytes') != 31485246
        or len(ev.get('receipts') or []) != 4): return None
    return {'path':E4_ARF_EVAL_2G_AUDIT_PATH,'sha256':E4_ARF_EVAL_2G_AUDIT_SHA256,
            'observed_eval_phase_max_rss_kib':maxima['evaluate'],
            'observed_calibration_phase_max_rss_kib':maxima['calibrate'],
            'observed_max_phase_seconds':ev.get('phase_durations_seconds',{}).get('evaluate_max'),
            'evaluations':ev['successful_task_count']}

def _eligible_e4_direct_arf_eval_2gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t): return False,None
    if t.get('adaptive_promoted_heavy'): return False,None
    try:
        rep=int(definition.get('rep')); cond=definition.get('condition'); key=definition.get('key')
    except (TypeError,ValueError): return False,None
    if (rep not in (1,2,3) or definition.get('experiment') != 4 or definition.get('kind') != 'eval'
        or definition.get('route') != 'direct' or definition.get('method') != 'arf'
        or cond not in E4_CONDITIONS or key != f'e4/rep_{rep}/eval/direct/arf/{cond}'
        or t.get('key') != key or definition.get('dependencies') != [f'e4/rep_{rep}/fit/direct/arf/{cond}']): return False,None
    if not definition.get('scientific_case',False) or definition.get('generator') is not None or definition.get('treatment') is not None: return False,None
    fit=f'e4/rep_{rep}/fit/direct/arf/{cond}'; train=f'e4/rep_{rep}/cohort/{cond}'
    if definition.get('fit_key') != fit or definition.get('train_key') not in (None,train): return False,None
    if not _valid_cohort(root,train,4,rep,cond): return False,None
    cohort_path=pathlib.Path(root)/'artifacts'/train
    cohort_meta=_json(cohort_path/'metadata.json') or {}
    cohort_val=_json(cohort_path/'validation.json') or {}
    counts=cohort_meta.get('realized_counts')
    data_sha=(cohort_val.get('files') or {}).get('data.npz')
    if (not isinstance(counts,list) or len(counts)!=7 or any(type(x) is not int or x<120 for x in counts)
        or sum(counts)!=80000 or not isinstance(data_sha,str)): return False,None
    fit_path=pathlib.Path(root)/'artifacts'/fit
    if not _valid_published_fit(root,fit,4,rep,'arf',train,require_publication=True,expected_rows=80000): return False,None
    fit_doc=_json(fit_path/'fit_result.json') or {}
    ft=fit_doc.get('task') or {}
    fr=fit_doc.get('result') or {}
    if (ft.get('kind')!='fit' or ft.get('route')!='direct' or ft.get('condition')!=cond
        or ft.get('selection_mode')!='tune' or ft.get('selection_policy')!='tune_on_matching_altered_cohort'
        or ft.get('trials')!=5 or ft.get('train_key')!=train or ft.get('selection_key') is not None
        or ft.get('selection_source') is not None or ft.get('reuse_pipeline') or ft.get('generator') is not None
        or ft.get('treatment') is not None or fr.get('source_sha256')!=data_sha
        or fr.get('training_rows')!=80000 or fr.get('class_counts')!=counts): return False,None
    val=_json(fit_path/'validation.json') or {}
    selection_path=fit_path/'selection.json'
    selection=_json(selection_path) or {}
    if ((val.get('files') or {}).get('selection.json')!=_sha256_cached(selection_path)
        or not isinstance(selection.get('selected_params'),dict)
        or selection.get('selected_params')!=fr.get('params')
        or not _arf_selected_params_in_domain(selection['selected_params'],counts)): return False,None
    pipeline_path=fit_path/'pipeline.joblib'
    pipeline_bytes=pipeline_path.stat().st_size if pipeline_path.is_file() else -1
    pipeline_sha=fr.get('pipeline_sha256')
    if pipeline_bytes<=0 or pipeline_bytes>E4_ARF_EVAL_MAX_PIPELINE_BYTES or _sha256_cached(pipeline_path)!=pipeline_sha: return False,None
    if _sha256_cached(pathlib.Path(root).parent/'project'/'benchmark'/'models_arf.py')!=E4_E5_ARF_MODELS_SHA: return False,None
    roles=_valid_e5_rf_eval_role_caches(root,rep,None)
    if not roles or roles.get('test_rows')!=500000 or roles.get('calibration_shape')!=[10000,6] or roles.get('prediction_chunk_rows')!=50000: return False,None
    if definition.get('role_membership_sha256') not in (None,roles.get('role_membership_sha256')): return False,None
    audit=_arf_eval_audit_evidence(root)
    if not audit:return False,None
    evidence={'profile_id':E4_ARF_EVAL_2G_PROFILE_ID,'reservation_gib':2,'fit_key':fit,'train_key':train,
        'condition':cond,'rep':rep,'training_rows':80000,'predictor_count':6,'class_counts':counts,
        'training_data_npz_sha256':data_sha,'training_ids_sha256':fr.get('training_ids_sha256'),
        'pipeline_sha256':pipeline_sha,'pipeline_bytes':pipeline_bytes,'selected_params':selection['selected_params'],
        'role_cache_identity':roles,'resource_audit':audit,'analogy_only':True,
        'this_pipeline_inference_rss_observed':False,'worker_hard_rss_limit_gib':10,
        'phase_timeout_seconds':600,'prediction_chunk_rows':50000,
        'reservation_caveat':'2 GiB is a provisional admission estimate based on four complete matching ARF calibration/test evaluations. It is not an RSS cap or worst-case guarantee; the 10 GiB hard cap and dynamic promotion remain active.'}
    return True,evidence

def eligible_e4_direct_arf_eval_2gib(t,definition,root):
    try:return _eligible_e4_direct_arf_eval_2gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None

def has_e4_direct_arf_eval_profile(t):
    if not isinstance(t,dict) or t.get('adaptive_promoted_heavy'):return False
    if t.get('admission_profile_id')!=E4_ARF_EVAL_2G_PROFILE_ID or t.get('admission_reservation_bytes')!=2*GIB:return False
    evidence=t.get('admission_profile_evidence') or {}
    if (evidence.get('profile_id')!=E4_ARF_EVAL_2G_PROFILE_ID or evidence.get('reservation_gib')!=2
        or evidence.get('resource_audit',{}).get('sha256')!=E4_ARF_EVAL_2G_AUDIT_SHA256):return False
    attempts=t.get('attempts') or []
    if not attempts:return False
    prof=attempts[-1].get('resource_profile') or {}
    ev=prof.get('admission_profile_evidence') or {}
    return (prof.get('admission_profile_id')==E4_ARF_EVAL_2G_PROFILE_ID
        and prof.get('admission_reservation_bytes')==2*GIB
        and ev.get('profile_id')==E4_ARF_EVAL_2G_PROFILE_ID
        and ev.get('resource_audit',{}).get('sha256')==E4_ARF_EVAL_2G_AUDIT_SHA256)


E4_E5_ARF_GENERATION_2G_AUDIT_PATH='reports/engineering_audits/ARF_GENERATION_ADMISSION_REVIEW_20261027.json'
E4_E5_ARF_GENERATION_2G_AUDIT_SHA256='7f632bde2863e9e3c4be95d19ec3395243bda8ad580d56a3f93528106a73ceaf'
E4_E5_ARF_GENERATION_BINDINGS_PATH='reports/engineering_audits/ARF_GENERATION_ADMISSION_EVIDENCE_BINDINGS_20261027.json'
E4_E5_ARF_GENERATION_BINDINGS_SHA256='198441f1493c4c9955305377112e2b28b52ffbd013fc659d98949cd110105221'
E4_ARF_GENERATION_2G_PROFILE_ID='e4-arf-target-generation-up-to-80k-admission-2gib-20261027'
E5_ARF_GENERATION_2G_PROFILE_ID='e5-arf-all-class-400k-generation-analogy-2gib-20261027'
E4_ARF_GENERATION_MAX_ROWS=45955
E5_ARF_GENERATION_ROWS=400000
_E4_E5_ARF_GENERATION_AUDIT_CACHE={}

def _arf_generation_audit(root):
    review=pathlib.Path(root)/E4_E5_ARF_GENERATION_2G_AUDIT_PATH
    bindings=pathlib.Path(root)/E4_E5_ARF_GENERATION_BINDINGS_PATH
    if (_sha256_cached(review)!=E4_E5_ARF_GENERATION_2G_AUDIT_SHA256
        or _sha256_cached(bindings)!=E4_E5_ARF_GENERATION_BINDINGS_SHA256):return None
    doc=_json(review);bind=_json(bindings)
    if not isinstance(doc,dict) or not isinstance(bind,dict):return None
    if doc.get('schema')!='arf-generation-admission-review/1' or bind.get('schema')!='arf-generation-admission-evidence-bindings/1':return None
    policy=doc.get('resource_policy_review') or {}; shape=doc.get('scientific_shape_context') or {}
    gen=doc.get('generation_outcomes') or {};e3=gen.get('e3') or {};e4=gen.get('e4') or {};e5=gen.get('e5') or {}
    e3sum=e3.get('phase_summary') or {};e4sum=e4.get('phase_summary') or {}
    if (policy.get('proposed_admission_reservation_gib')!=2 or policy.get('existing_scientific_hard_worker_memory_limit_gib')!=10
        or policy.get('existing_phase_timeout_seconds')!=600 or policy.get('existing_termination_grace_seconds')!=30
        or policy.get('dynamic_reservation_promotion_required') is not True
        or shape.get('common_predictor_count')!=6 or shape.get('e4_altered_fit_rows_per_condition')!=80000
        or shape.get('e4_restore_add_rows_min_max')!=[610,45955] or shape.get('e5_generation_rows_distribution')!={'400000':27}
        or e3.get('planned')!=3 or e3.get('failed_generation_attempts')!=0 or e3sum.get('rss_kib_max')!=659520
        or e3sum.get('n')!=3 or e4.get('planned')!=42 or e4.get('failed_generation_attempts')!=0
        or e4sum.get('n')!=1 or e4sum.get('rss_kib_max')!=223472
        or e5.get('planned')!=27 or e5.get('attempts_started')!=0 or e5.get('failed_generation_attempts')!=0):return None
    receipts=bind.get('generation_receipts') or []
    expected={'e3/rep_1/generate/arf':(400000,509120),'e3/rep_2/generate/arf':(400000,659520),
              'e3/rep_3/generate/arf':(400000,419740),'e4/rep_1/generate/A_half/arf':(2394,223472)}
    if len(receipts)!=4:return None
    seen={}
    for row in receipts:
        key=row.get('generation_task_key');phase=row.get('phase_summary') or {}
        if (key not in expected or row.get('generation_validation',{}).get('status')!='validated'
            or row.get('generation_validation',{}).get('task_key')!=key
            or phase.get('phase')!='generate' or phase.get('exit_code')!=0
            or phase.get('rows')!=expected[key][0] or phase.get('peak_tree_rss_kib')!=expected[key][1]
            or not row.get('worker_result_receipt',{}).get('sha256')
            or not row.get('generation_validation_receipt',{}).get('sha256')):return None
        seen[key]=row
    if set(seen)!=set(expected):return None
    plans=bind.get('frozen_plan_and_roles') or {}
    if (_sha256_cached(pathlib.Path(root)/'manifests/tasks.json')!=plans.get('freeze_plan_sha256')
        or _sha256_cached(pathlib.Path(root)/'source/science.py')!=((plans.get('freeze_source_sha256') or {}).get('science.py'))
        or _sha256_cached(pathlib.Path(root).parent/'project'/'benchmark'/'models_arf.py')!=E4_E5_ARF_MODELS_SHA):return None
    return {'review_path':E4_E5_ARF_GENERATION_2G_AUDIT_PATH,'review_sha256':E4_E5_ARF_GENERATION_2G_AUDIT_SHA256,
            'bindings_path':E4_E5_ARF_GENERATION_BINDINGS_PATH,'bindings_sha256':E4_E5_ARF_GENERATION_BINDINGS_SHA256,
            'e3_allclass_max_rss_kib':659520,'e4_target_max_rss_kib':223472,'receipt_count':4,
            'frozen_plan_sha256':plans.get('freeze_plan_sha256'),
            'science_sha256':(plans.get('freeze_source_sha256') or {}).get('science.py'),
            'models_arf_sha256':E4_E5_ARF_MODELS_SHA}

def _valid_arf_published_fit_context(root,fit,exp,rep,cond,train,require_fixed=False,definition=None):
    fpath=pathlib.Path(root)/'artifacts'/fit
    if not _valid_published_fit(root,fit,exp,rep,'arf',train,require_publication=True,expected_rows=80000):return None
    frdoc=_json(fpath/'fit_result.json') or {};ft=frdoc.get('task') or {};fr=frdoc.get('result') or {}
    counts=fr.get('class_counts')
    if not isinstance(counts,list) or len(counts)!=7 or any(type(x)is not int or x<=0 for x in counts) or sum(counts)!=80000:return None
    train_meta=None; train_validation=None; train_path=pathlib.Path(root)/'artifacts'/train
    if exp==4:
        if not _valid_cohort(root,train,4,rep,cond):return None
        train_meta=_json(train_path/'metadata.json') or {};train_validation=_json(train_path/'validation.json') or {}
        expected_counts=train_meta.get('realized_counts')
        if (train_meta.get('target_class') is None or train_meta.get('N')!=80000
            or expected_counts!=counts or fr.get('source_sha256')!=(train_validation.get('files') or {}).get('data.npz')):return None
        if (ft.get('kind')!='fit' or ft.get('route')!='direct' or ft.get('condition')!=cond
            or ft.get('selection_mode')!='tune' or ft.get('selection_policy')!='tune_on_matching_altered_cohort'
            or ft.get('trials')!=5 or ft.get('train_key')!=train or ft.get('selection_key') is not None
            or ft.get('selection_source') is not None or ft.get('reuse_pipeline') or ft.get('generator') is not None
            or ft.get('treatment') is not None):return None
        selection=_json(fpath/'selection.json') or {};val=_json(fpath/'validation.json') or {}
        selection_path=fpath/'selection.json';params=selection.get('selected_params')
        if ((val.get('files') or {}).get('selection.json')!=_sha256_cached(selection_path)
            or params!=fr.get('params') or not _arf_selected_params_in_domain(params,counts)):return None
    elif exp==5:
        artifact=_valid_npz_artifact(root,train)
        if not artifact:return None
        train_meta,shapes=artifact;train_validation=_json(train_path/'validation.json') or {}
        if (shapes!={'X':(80000,6),'y':(80000,),'ids':(80000,)} or train_meta.get('kind')!='e5_corruption' or train_meta.get('rep')!=rep
            or train_meta.get('mechanism')!=definition.get('mechanism')
            or abs(float(train_meta.get('rate',-1))-float(definition.get('rate',-2)))>1e-12):return None
        if (ft.get('kind')!='fit' or ft.get('route')!='direct' or ft.get('condition')!=cond
            or ft.get('selection_mode')!='fixed' or ft.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
            or ft.get('trials')!=0 or ft.get('train_key')!=train or ft.get('generator') is not None
            or ft.get('treatment') is not None or ft.get('mechanism')!=definition.get('mechanism')
            or ft.get('rate')!=definition.get('rate')):return None
        clean=f'e3/rep_{rep}/fit/arf';clean_doc=_json(pathlib.Path(root)/'artifacts'/clean/'fit_result.json') or {}
        clean_task=clean_doc.get('task') or {};clean_train=clean_task.get('train_key')
        if (ft.get('selection_key')!=clean or ft.get('dependencies')!=[train,clean]
            or clean_task.get('route')!='generator'
            or not _valid_published_fit(root,clean,3,rep,'arf',clean_train)):return None
        clean_sel=_json(pathlib.Path(root)/'artifacts'/clean/'selection.json') or {}
        params=clean_sel.get('selected_params')
        if (not isinstance(params,dict) or clean_doc.get('result',{}).get('params')!=params
            or fr.get('params')!=params or not _arf_selected_params_in_domain(params,counts)):return None
        data_path=train_path/'data.npz';data_sha=_sha256_cached(data_path)
        if not data_sha or fr.get('source_sha256')!=data_sha or _npz_label_counts(data_path,data_sha)!=counts:return None
    else:return None
    if ft.get('key')!=fit or ft.get('experiment')!=exp or ft.get('rep')!=rep or ft.get('method')!='arf' or ft.get('condition')!=cond:return None
    if require_fixed and exp!=5:return None
    data_sha=fr.get('source_sha256')
    pipeline=fpath/'pipeline.joblib';size=pipeline.stat().st_size if pipeline.is_file() else -1
    if size<=0 or size>E4_ARF_EVAL_MAX_PIPELINE_BYTES or _sha256_cached(pipeline)!=fr.get('pipeline_sha256'):return None
    return {'fit_result':fr,'fit_task':ft,'counts':counts,'params':params,'pipeline_sha256':fr.get('pipeline_sha256'),
            'pipeline_bytes':size,'training_data_npz_sha256':data_sha,'train_meta':train_meta,
            'train_validation':train_validation}

def _eligible_e4_arf_generation_2gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t):return False,None
    try:rep=int(definition.get('rep'));cond=definition.get('condition');key=definition.get('key')
    except (TypeError,ValueError):return False,None
    fit=f'e4/rep_{rep}/fit/direct/arf/{cond}';cohort=f'e4/rep_{rep}/cohort/{cond}'
    if (rep not in (1,2,3) or definition.get('experiment')!=4 or definition.get('kind')!='generate'
        or definition.get('generator')!='arf' or definition.get('method') is not None or definition.get('route') is not None
        or cond not in E4_CONDITIONS or key!=f'e4/rep_{rep}/generate/{cond}/arf' or t.get('key')!=key
        or definition.get('dependencies')!=[fit,cohort] or definition.get('fit_key')!=fit
        or definition.get('cohort_key')!=cohort or type(definition.get('target_class')) is not int or definition.get('target_class') not in range(7)
        or type(definition.get('added_count')) is not int or not 610<=definition['added_count']<=E4_ARF_GENERATION_MAX_ROWS
        or definition.get('n_rows') is not None or definition.get('ratio') is not None
        or definition.get('restored_share')!='original_target_share' or definition.get('shared_across_learners') is not True
        or definition.get('treatment') is not None):return False,None
    if not _valid_cohort(root,cohort,4,rep,cond):return False,None
    meta=_json(pathlib.Path(root)/'artifacts'/cohort/'metadata.json') or {}
    val=_json(pathlib.Path(root)/'artifacts'/cohort/'validation.json') or {}
    counts=meta.get('realized_counts');target=definition.get('target_class');added=definition.get('added_count')
    if (meta.get('target_class')!=target or meta.get('restore_added_count')!=added
        or not isinstance(counts,list) or len(counts)!=7 or sum(counts)!=80000
        or (meta.get('planned_counts') or [None]*7)[target]!=counts[target]):return False,None
    ctx=_valid_arf_published_fit_context(root,fit,4,rep,cond,cohort)
    if not ctx or ctx['counts']!=counts:return False,None
    audit=_arf_generation_audit(root)
    if not audit:return False,None
    return True,{'profile_id':E4_ARF_GENERATION_2G_PROFILE_ID,'reservation_gib':2,'fit_key':fit,'cohort_key':cohort,
        'condition':cond,'rep':rep,'target_class':target,'added_count':added,'training_rows':80000,
        'training_class_counts':counts,'training_data_npz_sha256':ctx['training_data_npz_sha256'],
        'pipeline_sha256':ctx['pipeline_sha256'],'pipeline_bytes':ctx['pipeline_bytes'],'selected_params':ctx['params'],
        'resource_audit':audit,'analogy_only':False,'this_generation_phase_observed':definition.get('key')=='e4/rep_1/generate/A_half/arf',
        'hard_worker_rss_limit_gib':10,'phase_timeout_seconds':600,
        'reservation_caveat':'2 GiB is a provisional admission estimate for target-class generation up to 45,955 rows; it is not an RSS cap or worst-case guarantee.'}

def _eligible_e5_arf_generation_2gib(t,definition,root):
    if not isinstance(t,dict) or not isinstance(definition,dict) or not _never_attempted(t):return False,None
    try:rep=int(definition.get('rep'));cond=definition.get('condition');key=definition.get('key')
    except (TypeError,ValueError):return False,None
    fit=f'e5/rep_{rep}/fit/direct/arf/{cond}';train=f'e5/rep_{rep}/corruption/{cond}'
    if (rep not in (1,2,3) or definition.get('experiment')!=5 or definition.get('kind')!='generate'
        or definition.get('generator')!='arf' or definition.get('method') is not None or definition.get('route') is not None
        or cond not in E5_CONDITIONS or not _e5_mechanism_rate_matches(definition,cond)
        or key!=f'e5/rep_{rep}/generate/{cond}/arf' or t.get('key')!=key or definition.get('fit_key')!=fit
        or definition.get('dependencies')!=[fit] or definition.get('n_rows')!=E5_ARF_GENERATION_ROWS
        or definition.get('cohort_key') is not None or definition.get('target_class') is not None
        or definition.get('added_count') is not None or definition.get('ratio') is not None
        or definition.get('shared_across_learners') is not True):return False,None
    ctx=_valid_arf_published_fit_context(root,fit,5,rep,cond,train,require_fixed=True,definition=definition)
    if not ctx:return False,None
    audit=_arf_generation_audit(root)
    if not audit:return False,None
    return True,{'profile_id':E5_ARF_GENERATION_2G_PROFILE_ID,'reservation_gib':2,'fit_key':fit,'train_key':train,
        'condition':cond,'rep':rep,'training_rows':80000,'training_class_counts':ctx['counts'],
        'training_data_npz_sha256':ctx['training_data_npz_sha256'],'pipeline_sha256':ctx['pipeline_sha256'],
        'pipeline_bytes':ctx['pipeline_bytes'],'selected_params':ctx['params'],'n_rows':E5_ARF_GENERATION_ROWS,
        'resource_audit':audit,'analogy_only':True,'e5_generation_phase_observed':False,
        'hard_worker_rss_limit_gib':10,'phase_timeout_seconds':600,
        'reservation_caveat':'E5 ARF 400k generation has no direct phase receipt; estimate is indirect from three E3 ARF all-class 400k generations and one E4 target generation. Preserve 10 GiB hard cap and promotion.'}

def eligible_e4_arf_generation_2gib(t,definition,root):
    try:return _eligible_e4_arf_generation_2gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile,IndexError):return False,None

def eligible_e5_arf_generation_2gib(t,definition,root):
    try:return _eligible_e5_arf_generation_2gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None

def has_e4_arf_generation_profile(t):
    return _has_arf_generation_profile(t,E4_ARF_GENERATION_2G_PROFILE_ID)

def has_e5_arf_generation_profile(t):
    return _has_arf_generation_profile(t,E5_ARF_GENERATION_2G_PROFILE_ID)

def _has_arf_generation_profile(t,profile):
    if not isinstance(t,dict) or t.get('adaptive_promoted_heavy') or t.get('admission_profile_id')!=profile or t.get('admission_reservation_bytes')!=2*GIB:return False
    evidence=t.get('admission_profile_evidence') or {}
    audit=evidence.get('resource_audit') or {}
    if (evidence.get('profile_id')!=profile or evidence.get('reservation_gib')!=2
        or audit.get('review_sha256')!=E4_E5_ARF_GENERATION_2G_AUDIT_SHA256
        or audit.get('bindings_sha256')!=E4_E5_ARF_GENERATION_BINDINGS_SHA256):return False
    attempts=t.get('attempts') or []
    if not attempts:return False
    resource=attempts[-1].get('resource_profile') or {};saved=resource.get('admission_profile_evidence') or {}
    return (resource.get('admission_profile_id')==profile and resource.get('admission_reservation_bytes')==2*GIB
        and saved.get('profile_id')==profile
        and (saved.get('resource_audit') or {}).get('bindings_sha256')==E4_E5_ARF_GENERATION_BINDINGS_SHA256)

def eligible_e4_treatment_rf_eval(t,definition,root):
    try:return _eligible_e4_treatment_rf_eval_6gib(t,definition,root)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None


def has_e4_treatment_rf_eval_profile(t):
    if not isinstance(t,dict) or t.get('adaptive_promoted_heavy'):return False
    if t.get('admission_profile_id')!=E4_RF_EVAL_6G_PROFILE_ID or t.get('admission_reservation_bytes')!=6*GIB:return False
    evidence=t.get('admission_profile_evidence') or {}
    if evidence.get('profile_id')!=E4_RF_EVAL_6G_PROFILE_ID or evidence.get('reservation_gib')!=6 or evidence.get('this_fit_inference_rss_observed') is not False:return False
    attempts=t.get('attempts') or []
    if not attempts:return False
    profile=attempts[-1].get('resource_profile') or {}
    return profile.get('admission_profile_id')==E4_RF_EVAL_6G_PROFILE_ID and profile.get('admission_reservation_bytes')==6*GIB


# Prospective, evidence-bound E4/E5 KNN and native-margin RBF-SVM reservations.
KNN_RBF_V1_AUDIT_PATH='reports/engineering_audits/KNN_RBF_ADMISSION_REVIEW_20261027.json'
KNN_RBF_V1_AUDIT_SHA256='95a125a3aef6c0cd7e6741749fd8a20d452fc31f564d63918c29d9aa08af15cf'
KNN_RBF_V2_AUDIT_PATH='reports/engineering_audits/KNN_RBF_ADMISSION_REVIEW_V2_20261027.json'
KNN_RBF_V2_AUDIT_SHA256='3f5c4fc2117665c3193852c2c457de07dcc19941ed14f86319deb9d0cf74046f'
KNN_RBF_KNN_PROFILE_ID='e4e5-direct-knn-80k-admission-2gib-20261027'
KNN_RBF_RBF_PROFILE_ID='e4e5-direct-rbf-svm-80k-admission-3gib-20261027'
KNN_RBF_MAX_PIPELINE_BYTES={'knn':64*1024*1024,'rbf_svm':256*1024*1024}
KNN_RBF_V2_SOURCE_IDENTITIES={
 'E1_master_config_sha256':'be5cdaf82de78e83cfcddb91858fb2eab2329bb793e7f5d0fe67d35c4aff9815',
 'E1_models_basic_sha256':'5c0079097f90339c452e48cba178f8f22bc5012882097fad23715f425e4ec8b2',
 'E4_manifest_sha256':'ad1b9e1fac7414d650d27e64094aaacd7113b856bf0c6e1d9604a41071c2c423',
 'E5_manifest_sha256':'ee27039ea1c16eea1cb5553f8107eaba7fad7432baaf2ac081e90c4c7de970c9',
 'runtime_science_sha256':'9937104e3e2d56eab25bb9596b39dcadbdefcd677ffa941cd1a635ae4ba58bd3',
 'runtime_worker_sha256':'f158d2bed12072da661af9195cc3a1b7e0367ff7cb2fe3ad24111e076dd29b18'}
_KNN_RBF_AUDIT_CACHE={}

def _knn_rbf_resource_audit(root):
    root=pathlib.Path(root)
    v1=root/KNN_RBF_V1_AUDIT_PATH;v2=root/KNN_RBF_V2_AUDIT_PATH
    if _sha256_cached(v1)!=KNN_RBF_V1_AUDIT_SHA256 or _sha256_cached(v2)!=KNN_RBF_V2_AUDIT_SHA256:return None
    d1=_json(v1);d2=_json(v2)
    if not isinstance(d1,dict) or not isinstance(d2,dict) or d2.get('schema')!='lamost-knn-rbf-admission-review/2':return None
    supersedes=d2.get('supersedes') or {}
    if (supersedes.get('original_json_relative_path')!='runtime_20261025/'+KNN_RBF_V1_AUDIT_PATH
        or supersedes.get('original_json_sha256')!=KNN_RBF_V1_AUDIT_SHA256):return None
    if d1.get('schema') not in ('lamost-knn-rbf-admission-review/1',None):return None
    source=d2.get('source_identities') or {}
    if source!=KNN_RBF_V2_SOURCE_IDENTITIES:return None
    bindings=d2.get('source_file_bindings') or []
    required={
      'project/benchmark/results/master_run_config.json':source['E1_master_config_sha256'],
      'project/benchmark/models_basic.py':source['E1_models_basic_sha256'],
      'runtime_20261025/source/science.py':source['runtime_science_sha256'],
      'runtime_20261025/source/worker.py':source['runtime_worker_sha256'],
      'runtime_20261025/manifests/E4_MANIFEST.json':source['E4_manifest_sha256'],
      'runtime_20261025/manifests/E5_MANIFEST.json':source['E5_manifest_sha256']}
    seen={x.get('path_relative_to_migration_root'):x.get('sha256') for x in bindings if isinstance(x,dict)}
    if any(seen.get(k)!=v for k,v in required.items()):return None
    checks={
      'project/benchmark/results/master_run_config.json':source['E1_master_config_sha256'],
      'project/benchmark/models_basic.py':source['E1_models_basic_sha256'],
      'runtime_20261025/source/science.py':source['runtime_science_sha256'],
      'runtime_20261025/source/worker.py':source['runtime_worker_sha256'],
      'runtime_20261025/source/phase_worker.py':'03df2cf1208d7a0a14ceda002f7f16291e0e08ee7308f967980d9519d05cc8de',
      'runtime_20261025/manifests/E4_MANIFEST.json':source['E4_manifest_sha256'],
      'runtime_20261025/manifests/E5_MANIFEST.json':source['E5_manifest_sha256']}
    for rel,expected in checks.items():
        path=root.parent/rel
        if _sha256_cached(path)!=expected:return None
    e1=d2.get('E1_frozen_context') or {};cfg=e1.get('config') or {};obs=e1.get('observations') or {}
    knn=obs.get('knn') or {};rbf=obs.get('rbf_svm') or {}
    if (cfg.get('memory_limit_gib')!=6.0 or cfg.get('trial_timeout_seconds')!=180
        or cfg.get('prediction_chunk_rows')!=50000 or knn.get('manifest_peak_rss_kib_max')!=1290012
        or rbf.get('trial_peak_rss_kib_max')!=1667924):return None
    current=d2.get('current_E4_E5_context') or {}
    for name in ('E4','E5'):
        c=current.get(name) or {};policy=c.get('resource_policy') or {}
        if (c.get('fit_rows')!=80000 or c.get('tuning_rows')!=10000 or c.get('calibration_rows')!=10000
            or c.get('test_rows')!=500000 or c.get('features')!=['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']
            or c.get('label_order')!=['A','F','G','K','M','GALAXY','QSO']
            or policy.get('worker_memory_limit_gib')!=10 or policy.get('trial_timeout_seconds')!=600
            or policy.get('phase_timeout_seconds')!=600 or policy.get('termination_grace_seconds')!=30
            or policy.get('nested_threads')!=1 or policy.get('prediction_chunk_rows')!=50000
            or policy.get('host_os_harbor_reserve_gib')!=6 or policy.get('admission_pause_below_gib')!=8
            or policy.get('commitment_growth_margin_gib')!=2 or policy.get('cpu_reserve_cores')!=2
            or policy.get('worker_admission_reservation_gib_by_class')!={'heavy':10,'light':2}):return None
    return {'v1_path':KNN_RBF_V1_AUDIT_PATH,'v1_sha256':KNN_RBF_V1_AUDIT_SHA256,
            'v2_path':KNN_RBF_V2_AUDIT_PATH,'v2_sha256':KNN_RBF_V2_AUDIT_SHA256,
            'e1_knn_max_rss_kib':1290012,'e1_rbf_trial_max_rss_kib':1667924,
            'e1_memory_limit_gib':6,'e1_trial_timeout_seconds':180,
            'later_hard_rss_limit_gib':10,'later_trial_phase_timeout_seconds':600,
            'later_termination_grace_seconds':30,'prediction_chunk_rows':50000,
            'e4_manifest_sha256':source['E4_manifest_sha256'],'e5_manifest_sha256':source['E5_manifest_sha256'],
            'science_sha256':source['runtime_science_sha256'],'worker_sha256':source['runtime_worker_sha256'],
            'models_basic_sha256':source['E1_models_basic_sha256']}

def _knn_rbf_params_valid(method,params):
    if not isinstance(params,dict):return False
    if method=='knn':
        return (set(params)=={'n_neighbors','weights'} and type(params.get('n_neighbors')) is int
            and params['n_neighbors'] in (3,5,15,50,100) and params.get('weights') in ('uniform','distance'))
    if method=='rbf_svm':
        try:c=float(params['C']);g=float(params['gamma']);cache=params['cache_size_mb']
        except (KeyError,TypeError,ValueError,OverflowError):return False
        return (set(params)=={'C','gamma','cache_size_mb'} and type(params.get('C')) in (int,float)
            and type(params.get('gamma')) in (int,float) and 1e-2<=c<=1e3 and 1e-3<=g<=1.0
            and type(cache) is int and cache==512)
    return False

def _knn_rbf_role_context(root,rep):
    return _valid_e5_rf_eval_role_caches(root,rep,None)

def _verified_imported_knn_selection(root,rep,selection_source):
    root=pathlib.Path(root)
    expected_dir=root/'manifests'/'imported_selections'/'e1_100000'/f'rep_{rep}'/'knn'
    summary_path=expected_dir/'selection.json'
    try:
        if pathlib.Path(selection_source or '').resolve()!=expected_dir.resolve():return None
    except (OSError,TypeError):return None
    summary=_json(summary_path) or {}
    canonical=root.parent/'project'/'benchmark'/'results'/'e1'/f'rep_{rep}'/'n_100000'/'knn'/'complete.json'
    try:source_path=pathlib.Path(summary.get('source_path','')).resolve()
    except (OSError,TypeError):return None
    if (source_path!=canonical.resolve() or not canonical.is_file()
        or summary.get('source_status')!='complete'
        or _sha256_cached(canonical)!=summary.get('source_sha256')):return None
    complete=_json(canonical) or {}
    params=summary.get('selected_params')
    if (complete.get('status')!='complete' or complete.get('selected_params')!=params
        or not _knn_rbf_params_valid('knn',params)):return None
    for field,expected in (('rep',rep),('repetition',rep),('budget',100000),('n',100000),('method','knn')):
        if field in complete and complete[field]!=expected:return None
    return {'selected_params':params,'summary_path':str(summary_path.relative_to(root)),
            'summary_sha256':_sha256_cached(summary_path),'source_path':str(canonical.relative_to(root.parent)),
            'source_sha256':summary.get('source_sha256'),'source_status':complete.get('status')}

def _knn_rbf_e4_case(d,method,rep,condition,root):
    fit=f'e4/rep_{rep}/fit/direct/{method}/{condition}'
    if condition=='control':
        if d.get('train_key') is not None or d.get('dependencies')!=[]:return None
        if method=='knn':
            imported=_verified_imported_knn_selection(root,rep,d.get('selection_source'))
            if not imported:return None
            params=imported['selected_params']
            mode='fixed';trials=0
        else:
            if d.get('selection_source') is not None: return None
            params=None;mode='tune';trials=5
        policy='import_successful_E1_params_or_tune_if_unavailable'
        if d.get('selection_policy')!=policy or d.get('selection_mode')!=mode or d.get('trials')!=trials:return None
        role=_knn_rbf_role_context(root,rep)
        if not role:return None
        train=None;counts=None;data_sha=role.get('role_npz_sha256')
    else:
        if condition not in E4_CONDITIONS:return None
        train=f'e4/rep_{rep}/cohort/{condition}'
        if d.get('train_key')!=train or d.get('dependencies')!=[train]:return None
        if d.get('selection_source') is not None:return None
        if d.get('selection_mode')!='tune' or d.get('trials')!=5:return None
        if d.get('selection_policy')!='tune_on_matching_altered_cohort':return None
        if not _valid_cohort(root,train,4,rep,condition):return None
        meta=_json(root/'artifacts'/train/'metadata.json') or {}
        val=_json(root/'artifacts'/train/'validation.json') or {}
        counts=meta.get('realized_counts');data_sha=(val.get('files') or {}).get('data.npz')
        if not isinstance(counts,list) or len(counts)!=7 or sum(counts)!=80000 or not isinstance(data_sha,str):return None
        role=_knn_rbf_role_context(root,rep)
        if not role:return None
        params=None
    return {'fit_key':fit,'train_key':train,'counts':counts,'data_sha256':data_sha,'roles':role,'params':params,'imported_selection':locals().get('imported')}

def _knn_rbf_e5_case(d,method,rep,condition,root):
    if condition not in E5_CONDITIONS or not _e5_mechanism_rate_matches(d,condition):return None
    fit=f'e5/rep_{rep}/fit/direct/{method}/{condition}'
    train=f'e5/rep_{rep}/corruption/{condition}'
    base=f'e4/rep_{rep}/fit/direct/{method}/control'
    if (d.get('train_key')!=train or d.get('selection_key')!=base or d.get('dependencies')!=[train,base]
        or d.get('selection_mode')!='fixed' or d.get('trials')!=0
        or d.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
        or d.get('selection_source') is not None):return None
    if not _valid_cohort(root,train,5,rep,condition):return None
    artifact=_valid_npz_artifact(root,train)
    if not artifact or artifact[1]!={'X':(80000,6),'y':(80000,),'ids':(80000,)}:return None
    meta,validation=artifact
    val=_json(root/'artifacts'/train/'validation.json') or {}
    data_sha=(val.get('files') or {}).get('data.npz')
    if not isinstance(data_sha,str):return None
    parent_path=root/'artifacts'/base
    if not _valid_published_fit(root,base,4,rep,method,None,require_publication=True,expected_rows=80000):return None
    parent_doc=_json(parent_path/'fit_result.json') or {}
    parent_task=parent_doc.get('task') or {};parent_result=parent_doc.get('result') or {}
    parent_roles=_knn_rbf_role_context(root,rep)
    expected_mode='fixed' if method=='knn' else 'tune'
    expected_trials=0 if method=='knn' else 5
    if (parent_task.get('key')!=base or parent_task.get('kind')!='fit' or parent_task.get('experiment')!=4
        or parent_task.get('rep')!=rep or parent_task.get('method')!=method
        or parent_task.get('route')!='direct' or parent_task.get('condition')!='control'
        or parent_task.get('train_key') is not None or parent_task.get('dependencies')!=[]
        or parent_task.get('selection_policy')!='import_successful_E1_params_or_tune_if_unavailable'
        or parent_task.get('selection_mode')!=expected_mode or parent_task.get('trials')!=expected_trials
        or parent_result.get('status')!='success' or not parent_roles
        or parent_result.get('source_sha256')!=parent_roles.get('role_npz_sha256')):return None
    if parent_task.get('train_path') and pathlib.Path(parent_task['train_path']).resolve()!=(root/'cache'/'roles'/f'rep_{rep}.npz').resolve():return None
    selection=_json(parent_path/'selection.json') or {}
    pv=_json(parent_path/'validation.json') or {}
    selected=selection.get('selected_params')
    if ((pv.get('files') or {}).get('selection.json')!=_sha256_cached(parent_path/'selection.json')
        or not _knn_rbf_params_valid(method,selected) or parent_result.get('params')!=selected):return None
    imported=None
    if method=='knn':
        imported=_verified_imported_knn_selection(root,rep,parent_task.get('selection_source'))
        if not imported or selected!=imported['selected_params']:return None
    role=_knn_rbf_role_context(root,rep)
    if not role:return None
    return {'fit_key':fit,'train_key':train,'base_fit_key':base,'counts':meta.get('counts',meta.get('realized_counts')),
            'data_sha256':data_sha,'roles':role,'params':selected,'imported_selection':imported}

def _knn_rbf_fit_eligibility(t,d,root,method):
    if not isinstance(t,dict) or not isinstance(d,dict) or t.get('adaptive_promoted_heavy') or not _never_attempted(t):return False,None
    try:exp=int(d.get('experiment'));rep=int(d.get('rep'));condition=d.get('condition');key=d.get('key')
    except (TypeError,ValueError):return False,None
    if (exp not in (4,5) or rep not in (1,2,3) or d.get('kind')!='fit' or d.get('route')!='direct'
        or d.get('method')!=method or d.get('generator') is not None or d.get('treatment') is not None
        or d.get('target_class') is not None or d.get('ratio') is not None
        or key!=f'e{exp}/rep_{rep}/fit/direct/{method}/{condition}' or t.get('key')!=key):return False,None
    if not _knn_rbf_resource_audit(root):return False,None
    if exp==4:
        ctx=_knn_rbf_e4_case(d,method,rep,condition,pathlib.Path(root))
        if not ctx:return False,None
        if condition=='control' and method=='knn':
            params=ctx['params']
        else:params=None
        if d.get('selection_key') is not None or d.get('reuse_pipeline'):return False,None
    else:
        ctx=_knn_rbf_e5_case(d,method,rep,condition,pathlib.Path(root))
        if not ctx:return False,None
        params=ctx['params']
    if params is not None and not _knn_rbf_params_valid(method,params):return False,None
    if method=='knn':
        profile=KNN_RBF_KNN_PROFILE_ID;gib=2;cap=KNN_RBF_MAX_PIPELINE_BYTES['knn']
    else:
        profile=KNN_RBF_RBF_PROFILE_ID;gib=3;cap=KNN_RBF_MAX_PIPELINE_BYTES['rbf_svm']
    audit=_knn_rbf_resource_audit(root)
    return True,{'profile_id':profile,'reservation_gib':gib,'method':method,'experiment':exp,'rep':rep,
        'condition':condition,'fit_key':key,'train_key':ctx['train_key'],'base_fit_key':ctx.get('base_fit_key'),
        'training_rows':80000,'features':6,'class_counts':ctx.get('counts'),'training_data_sha256':ctx.get('data_sha256'),
        'role_cache_identity':ctx['roles'],'selected_params_if_fixed':params,'max_pipeline_bytes_for_evaluation':cap,
        'resource_audit':audit,'training_inference_evidence':'admission reservation estimate only; selected-model E1 resource maxima and 80k six-feature shape; E4/E5 10 GiB hard cap and 600s policy remain distinct from E1 6 GiB/180s policy',
        'hard_rss_limit_gib':10,'trial_phase_timeout_seconds':600,'termination_grace_seconds':30}

def _knn_rbf_fit_artifact_context(root,fit,exp,rep,method,condition):
    p=pathlib.Path(root)/'artifacts'/fit
    doc=_json(p/'fit_result.json') or {};ft=doc.get('task') or {};fr=doc.get('result') or {}
    if fr.get('status')!='success' or doc.get('status')!='successful':return None
    if not _valid_published_fit(root,fit,exp,rep,method,ft.get('train_key'),require_publication=True,expected_rows=80000):return None
    if (ft.get('key')!=fit or ft.get('route')!='direct' or ft.get('condition')!=condition
        or ft.get('method')!=method or ft.get('kind')!='fit'):return None
    params=fr.get('params')
    if not _knn_rbf_params_valid(method,params):return None
    counts=fr.get('class_counts')
    if not isinstance(counts,list) or len(counts)!=7 or any(type(x)is not int or x<=0 for x in counts) or sum(counts)!=80000:return None
    selection=_json(p/'selection.json') or {};validation=_json(p/'validation.json') or {}
    if (selection.get('selected_params')!=params
        or (validation.get('files') or {}).get('selection.json')!=_sha256_cached(p/'selection.json')):return None
    size=(p/'pipeline.joblib').stat().st_size
    if size<=0 or size>KNN_RBF_MAX_PIPELINE_BYTES[method]:return None
    role=_knn_rbf_role_context(root,rep)
    if not role:return None
    if exp==4:
        train=ft.get('train_key')
        if condition=='control':
            if train is not None or ft.get('dependencies')!=[]:return None
            expected_mode='fixed' if method=='knn' else 'tune'
            expected_trials=0 if method=='knn' else 5
            if (ft.get('selection_policy')!='import_successful_E1_params_or_tune_if_unavailable'
                or ft.get('selection_mode')!=expected_mode or ft.get('trials')!=expected_trials):return None
            if method=='knn':
                imported=_verified_imported_knn_selection(root,rep,ft.get('selection_source'))
                if not imported or imported['selected_params']!=params:return None
            elif ft.get('selection_source') is not None:return None
            if ft.get('train_path') and pathlib.Path(ft['train_path']).resolve()!=(root/'cache'/'roles'/f'rep_{rep}.npz').resolve():return None
            if fr.get('source_sha256')!=role.get('role_npz_sha256'):return None
        else:
            expected=f'e4/rep_{rep}/cohort/{condition}'
            if (condition not in E4_CONDITIONS or train!=expected or ft.get('dependencies')!=[expected]
                or not _valid_cohort(root,expected,4,rep,condition)):return None
            if (ft.get('selection_mode')!='tune' or ft.get('trials')!=5
                or ft.get('selection_policy')!='tune_on_matching_altered_cohort'
                or ft.get('selection_key') is not None or ft.get('selection_source') is not None):return None
            val=_json(root/'artifacts'/expected/'validation.json') or {}
            if fr.get('source_sha256')!=(val.get('files') or {}).get('data.npz'):return None
            if ft.get('train_path') and pathlib.Path(ft['train_path']).resolve()!=(root/'artifacts'/expected/'data.npz').resolve():return None
    else:
        expected=f'e5/rep_{rep}/corruption/{condition}'
        base=f'e4/rep_{rep}/fit/direct/{method}/control'
        if (ft.get('train_key')!=expected or ft.get('selection_key')!=base or ft.get('dependencies')!=[expected,base]
            or not _valid_cohort(root,expected,5,rep,condition)):return None
        if (ft.get('selection_mode')!='fixed' or ft.get('trials')!=0
            or ft.get('selection_policy')!='frozen_clean_selected_params_no_retuning'
            or ft.get('selection_key')!=f'e4/rep_{rep}/fit/direct/{method}/control'
            or ft.get('dependencies')!=[expected,f'e4/rep_{rep}/fit/direct/{method}/control']
            or not _e5_mechanism_rate_matches(ft,condition)):return None
        val=_json(root/'artifacts'/expected/'validation.json') or {}
        if fr.get('source_sha256')!=(val.get('files') or {}).get('data.npz'):return None
        if ft.get('train_path') and pathlib.Path(ft['train_path']).resolve()!=(root/'artifacts'/expected/'data.npz').resolve():return None
        base_doc=_json(root/'artifacts'/base/'fit_result.json') or {}
        base_task=base_doc.get('task') or {};base_result=base_doc.get('result') or {}
        base_selection=_json(root/'artifacts'/base/'selection.json') or {}
        base_validation=_json(root/'artifacts'/base/'validation.json') or {}
        base_mode='fixed' if method=='knn' else 'tune';base_trials=0 if method=='knn' else 5
        if (base_task.get('key')!=base or base_task.get('kind')!='fit' or base_task.get('experiment')!=4
            or base_task.get('rep')!=rep or base_task.get('method')!=method or base_task.get('route')!='direct'
            or base_task.get('condition')!='control' or base_task.get('train_key') is not None
            or base_task.get('dependencies')!=[] or base_task.get('selection_mode')!=base_mode
            or base_task.get('trials')!=base_trials
            or base_task.get('selection_policy')!='import_successful_E1_params_or_tune_if_unavailable'
            or base_result.get('source_sha256')!=role.get('role_npz_sha256')
            or base_result.get('params')!=params or base_selection.get('selected_params')!=params
            or (base_validation.get('files') or {}).get('selection.json')!=_sha256_cached(root/'artifacts'/base/'selection.json')
            or not _valid_published_fit(root,base,4,rep,method,None,require_publication=True,expected_rows=80000)):return None
        if method=='knn':
            imported=_verified_imported_knn_selection(root,rep,base_task.get('selection_source'))
            if not imported or base_result.get('params')!=imported['selected_params'] or base_selection.get('selected_params')!=imported['selected_params']:return None
        if base_task.get('train_path') and pathlib.Path(base_task['train_path']).resolve()!=(root/'cache'/'roles'/f'rep_{rep}.npz').resolve():return None
    return {'fit_task':ft,'fit_result':fr,'params':params,'pipeline_sha256':fr.get('pipeline_sha256'),
            'pipeline_bytes':size,'roles':role}

def _knn_rbf_eval_eligibility(t,d,root,method):
    if not isinstance(t,dict) or not isinstance(d,dict) or t.get('adaptive_promoted_heavy') or not _never_attempted(t):return False,None
    try:exp=int(d.get('experiment'));rep=int(d.get('rep'));condition=d.get('condition');key=d.get('key')
    except (TypeError,ValueError):return False,None
    if (exp not in (4,5) or rep not in (1,2,3) or d.get('kind')!='eval' or d.get('route')!='direct'
        or d.get('method')!=method or d.get('generator') is not None or d.get('treatment') is not None
        or d.get('scientific_case') is not True or key!=f'e{exp}/rep_{rep}/eval/direct/{method}/{condition}'
        or t.get('key')!=key):return False,None
    fit=f'e{exp}/rep_{rep}/fit/direct/{method}/{condition}'
    if d.get('fit_key')!=fit or d.get('dependencies')!=[fit] or d.get('train_key') is not None:return False,None
    if exp==4 and condition!='control' and condition not in E4_CONDITIONS:return False,None
    if exp==5 and (condition not in E5_CONDITIONS or not _e5_mechanism_rate_matches(d,condition)):return False,None
    if not _knn_rbf_resource_audit(root):return False,None
    ctx=_knn_rbf_fit_artifact_context(pathlib.Path(root),fit,exp,rep,method,condition)
    if not ctx:return False,None
    return True,{'profile_id':KNN_RBF_KNN_PROFILE_ID if method=='knn' else KNN_RBF_RBF_PROFILE_ID,
        'reservation_gib':2 if method=='knn' else 3,'method':method,'experiment':exp,'rep':rep,'condition':condition,
        'fit_key':fit,'pipeline_sha256':ctx['pipeline_sha256'],'pipeline_bytes':ctx['pipeline_bytes'],
        'role_cache_identity':ctx['roles'],'prediction_chunk_rows':50000,'calibration_rows':10000,'test_rows':500000,
        'resource_audit':_knn_rbf_resource_audit(root),'hard_rss_limit_gib':10,'phase_timeout_seconds':600,
        'termination_grace_seconds':30,'reservation_caveat':'Provisional admission reservation, not a hard cap or worst-case bound; dynamic promotion remains active.'}

def eligible_knn_rbf_resource_profile(t,d,root):
    try:
        if not isinstance(d,dict):return False,None
        method=d.get('method')
        if method not in ('knn','rbf_svm'):return False,None
        if d.get('kind')=='fit':return _knn_rbf_fit_eligibility(t,d,root,method)
        if d.get('kind')=='eval':return _knn_rbf_eval_eligibility(t,d,root,method)
        return False,None
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,EOFError,zipfile.BadZipFile):return False,None

def has_knn_rbf_resource_profile(t):
    if not isinstance(t,dict) or t.get('adaptive_promoted_heavy'):return False
    evidence=t.get('admission_profile_evidence') or {};profile=evidence.get('profile_id')
    if profile not in (KNN_RBF_KNN_PROFILE_ID,KNN_RBF_RBF_PROFILE_ID):return False
    method='knn' if profile==KNN_RBF_KNN_PROFILE_ID else 'rbf_svm'
    gib=2 if method=='knn' else 3
    if (t.get('method')!=method or t.get('kind') not in ('fit','eval')
        or int(t.get('experiment',0) or 0) not in (4,5)
        or evidence.get('method')!=method or evidence.get('experiment')!=int(t.get('experiment',0) or 0)
        or evidence.get('rep')!=t.get('rep') or evidence.get('condition')!=t.get('condition')):return False
    resource=evidence.get('resource_audit') or {}
    if (evidence.get('reservation_gib')!=gib or resource.get('v1_sha256')!=KNN_RBF_V1_AUDIT_SHA256
        or resource.get('v2_sha256')!=KNN_RBF_V2_AUDIT_SHA256):return False
    if t.get('admission_profile_id')!=profile or t.get('admission_reservation_bytes')!=gib*GIB:return False
    attempts=t.get('attempts') or []
    if not attempts:return False
    saved=(attempts[-1].get('resource_profile') or {}).get('admission_profile_evidence') or {}
    return ((attempts[-1].get('resource_profile') or {}).get('admission_profile_id')==profile
        and (attempts[-1].get('resource_profile') or {}).get('admission_reservation_bytes')==gib*GIB
        and saved.get('profile_id')==profile
        and (saved.get('resource_audit') or {}).get('v2_sha256')==KNN_RBF_V2_AUDIT_SHA256)
