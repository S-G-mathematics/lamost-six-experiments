"""Freeze a complete-case, source-deduplicated seven-class photometric cohort.

No classifiers are trained. All fitted preprocessing uses reference_fit only.
Run after download_source.py and ingest_source.py, from any working directory.
"""
from pathlib import Path
import sys, json, time, hashlib, gc
import numpy as np
import pandas as pd
import duckdb, pyarrow as pa, pyarrow.parquet as pq
from sklearn.model_selection import train_test_split
import joblib
from preprocessing import FEATURE_COLUMNS, TrainOnlyPreprocessor
ROOT=Path(__file__).resolve().parents[1]
F=list(FEATURE_COLUMNS); FS=', '.join(F); LABELS=['A','F','G','K','M','GALAXY','QSO']; SEED=20261022
LABEL_SQL="""CASE WHEN class='GALAXY' THEN 'GALAXY' WHEN class='QSO' THEN 'QSO'
 WHEN class='STAR' AND (subclass LIKE 'dM%' OR subclass LIKE 'gM%' OR subclass LIKE 'sdM%' OR subclass LIKE 'M%') THEN 'M'
 WHEN class='STAR' AND left(subclass,1) IN ('A','F','G','K') THEN left(subclass,1) ELSE 'OTHER' END"""
VALID=' AND '.join(f'(isfinite({x}) AND {x} BETWEEN -30 AND 50)' for x in F)
ZERO_PS=' AND '.join(f'{x}=0' for x in F[:5])
PLACEHOLDER=f'(({ZERO_PS}) AND coalesce(try_cast(ps_id AS HUGEINT),0)<=0)'
Q="CASE WHEN isfinite(snri) AND snri>=0 THEN snri ELSE NULL END"
AUD={}
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def save_json(name,obj):
    (ROOT/'audit'/name).write_text(json.dumps(obj,indent=2,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
def run(q):return con.execute(q).fetchall()
def query(q):return con.sql(q).df()
def records(q):return query(q).to_dict('records')
def copy(q,path):
    run(f"COPY ({q}) TO '{ROOT/path}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 200000)")
def scalar(q):return run(q)[0][0]
def main():
    global con
    for d in ('data','audit','docs'): (ROOT/d).mkdir(exist_ok=True)
    con=duckdb.connect(str(ROOT/'audit/work.duckdb'))
    run("SET memory_limit='3GB'; SET threads=4; SET preserve_insertion_order=false")
    run(f"SET temp_directory='{ROOT/'audit/tmp'}'")
    run(f"CREATE OR REPLACE VIEW raw AS SELECT * EXCLUDE(obsid), CAST(obsid AS BIGINT) obsid, {LABEL_SQL} AS target FROM read_parquet('{ROOT/'raw/catalog.parquet'}')")
    log('Full-source structural audit')
    AUD['raw_rows']=scalar('SELECT count(*) FROM raw')
    assert AUD['raw_rows']==11441011, AUD['raw_rows']
    AUD['raw_class_counts']=records('SELECT class,count(*) n FROM raw GROUP BY class ORDER BY class')
    assert {r['class']:r['n'] for r in AUD['raw_class_counts']}=={'STAR':11100139,'GALAXY':261381,'QSO':79491}, 'Official release class counts mismatch'
    AUD['raw_target_counts']=records('SELECT target,count(*) n,count(DISTINCT uid) n_uid FROM raw GROUP BY target ORDER BY target')
    expected={'A':654495,'F':2682008,'G':4630751,'K':2226756,'M':858985,'GALAXY':261381,'QSO':79491,'OTHER':47144}
    assert {r['target']:r['n'] for r in AUD['raw_target_counts']}==expected, 'Official target aggregate mismatch'
    AUD['duplicate_obsid_rows']=scalar('SELECT count(*)-count(DISTINCT obsid) FROM raw')
    # If repeated spectrum IDs occur, resolve the source problem explicitly before proceeding.
    assert AUD['duplicate_obsid_rows']==0, 'Duplicate spectrum IDs need conflict-aware review'
    AUD['invalid_uid_rows']=scalar("SELECT count(*) FROM raw WHERE uid IS NULL OR trim(uid)=''")
    AUD['invalid_obsid_rows']=scalar('SELECT count(*) FROM raw WHERE obsid IS NULL OR obsid<=0')
    feature_audit=[]
    for c in F:
        row=records(f"SELECT '{c}' feature,min({c}) minimum,max({c}) maximum,count(*) FILTER(WHERE {c} IS NULL) nulls,count(*) FILTER(WHERE NOT isfinite({c})) nonfinite,count(*) FILTER(WHERE {c}=0) zeros,count(*) FILTER(WHERE isfinite({c}) AND {c} BETWEEN -30 AND 50) broad_valid FROM raw")[0]
        row['sentinels']={str(v):scalar(f'SELECT count(*) FROM raw WHERE {c}={v}') for v in (-9999,-999,-99,99,99.99,100,999,9999)}
        feature_audit.append(row)
    AUD['raw_feature_audit']=feature_audit
    AUD['raw_zero_ps_without_counterpart']=scalar(f'SELECT count(*) FROM raw WHERE {PLACEHOLDER}')
    # Cross-check a previously exported official SQL pilot by ID. ID strings never pass through float.
    p=ROOT/'raw/query_speed_preview.csv'
    if p.exists():
        pilot=pd.read_csv(p,encoding='utf-8-sig',dtype={'uid':str,'ps_id':str,'gaia_source_id':str})
        con.register('official_pilot',pilot)
        check=records('SELECT count(*) n, '+', '.join(f'max(abs(CAST(r.{c} AS DOUBLE)-CAST(p.{c} AS DOUBLE))) AS {c}' for c in F)+" FROM raw r JOIN official_pilot p ON r.obsid=p.obsid")[0]
        check['uid_mismatches']=scalar('SELECT count(*) FROM raw r JOIN official_pilot p ON r.obsid=p.obsid WHERE r.uid<>p.uid')
        check['ps_id_mismatches']=scalar("SELECT count(*) FROM raw r JOIN official_pilot p ON r.obsid=p.obsid WHERE trim(r.ps_id)<>trim(p.ps_id)")
        check['gaia_id_mismatches']=scalar("SELECT count(*) FROM raw r JOIN official_pilot p ON r.obsid=p.obsid WHERE trim(r.gaia_source_id)<>trim(p.gaia_source_id)")
        check['class_mismatches']=scalar('SELECT count(*) FROM raw r JOIN official_pilot p ON r.obsid=p.obsid WHERE r.class<>p.class OR r.subclass<>p.subclass')
        AUD['official_pilot_check']=check
        assert check['n']==len(pilot) and max(check[c] for c in F)<1e-4 and sum(check[k] for k in ('uid_mismatches','ps_id_mismatches','gaia_id_mismatches','class_mismatches'))==0, check
        con.unregister('official_pilot');del pilot
    save_json('cleaning_audit.json',AUD)
    log('Materializing eligible seven-class observations')
    run(f"CREATE OR REPLACE TABLE eligible AS SELECT *, {Q} quality_snri FROM raw WHERE target<>'OTHER' AND uid IS NOT NULL AND trim(uid)<>'' AND obsid>0 AND {VALID} AND NOT ({PLACEHOLDER})")
    AUD['eligible_spectra']=scalar('SELECT count(*) FROM eligible')
    AUD['eligible_source_count']=scalar('SELECT count(DISTINCT uid) FROM eligible')
    AUD['eligible_counts']=records('SELECT target,count(*) n_spectra,count(DISTINCT uid) n_sources FROM eligible GROUP BY target ORDER BY target')
    assert AUD['eligible_source_count']==2330850, 'Official complete-case source union mismatch'
    run("""CREATE OR REPLACE TABLE uid_stats AS SELECT uid,count(*) n_eligible_spectra,count(DISTINCT target) n_eligible_labels,
      count(DISTINCT CASE WHEN try_cast(gaia_source_id AS HUGEINT)>0 THEN gaia_source_id END) n_gaia_ids,
      count(DISTINCT CASE WHEN try_cast(ps_id AS HUGEINT)>0 THEN ps_id END) n_ps_ids FROM eligible GROUP BY uid""")
    run("CREATE OR REPLACE TABLE all_uid_stats AS SELECT uid,count(*) n_all_spectra,count(DISTINCT target) n_all_seven_labels FROM raw WHERE target<>'OTHER' GROUP BY uid")
    AUD['eligible_conflicting_sources']=scalar('SELECT count(*) FROM uid_stats WHERE n_eligible_labels>1')
    assert AUD['eligible_conflicting_sources']==132734
    AUD['all_observation_conflicting_eligible_sources']=scalar('SELECT count(*) FROM uid_stats JOIN all_uid_stats USING(uid) WHERE n_all_seven_labels>1')
    run("CREATE OR REPLACE TABLE source_selected AS SELECT * EXCLUDE(rn) FROM (SELECT *,row_number() OVER(PARTITION BY uid ORDER BY quality_snri DESC NULLS LAST,obsid) rn FROM eligible) WHERE rn=1")
    log('Linking shared positive Gaia/PanSTARRS counterpart IDs')
    uids=query('SELECT uid FROM uid_stats ORDER BY uid')['uid'].to_numpy()
    uid_index={s:i for i,s in enumerate(uids)}
    parents=np.arange(len(uids),dtype=np.int32)
    sizes=np.ones(len(uids),dtype=np.int32)
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=int(parents[i])
        return i
    def union(a,b):
        x,y=find(a),find(b)
        if x==y:return
        if sizes[x]<sizes[y]:x,y=y,x
        parents[y]=x;sizes[x]+=sizes[y]
    link_stats={}
    for col in ('gaia_source_id','ps_id'):
        links=query(f"WITH shared AS (SELECT {col} counterpart,min(uid) representative,count(DISTINCT uid) n FROM eligible WHERE try_cast({col} AS HUGEINT)>0 GROUP BY {col} HAVING count(DISTINCT uid)>1) SELECT DISTINCT e.uid,s.representative FROM eligible e JOIN shared s ON e.{col}=s.counterpart WHERE e.uid<>s.representative")
        link_stats[col]={'uid_to_representative_edges':len(links),'shared_ids':scalar(f'SELECT count(*) FROM (SELECT {col} FROM eligible WHERE try_cast({col} AS HUGEINT)>0 GROUP BY {col} HAVING count(DISTINCT uid)>1)')}
        for a,b in links.itertuples(index=False,name=None):union(uid_index[a],uid_index[b])
        del links;gc.collect()
    roots=np.fromiter((find(i) for i in range(len(uids))),dtype=np.int32,count=len(uids))
    # Stable group ID is lexicographically smallest UID, independent of union order.
    minidx=np.full(len(uids),len(uids),dtype=np.int32)
    np.minimum.at(minidx,roots,np.arange(len(uids),dtype=np.int32))
    membership=pa.table({'uid':uids,'entity_id':uids[minidx[roots]],'n_linked_uids':sizes[roots]})
    pq.write_table(membership,ROOT/'audit/source_entity_membership.parquet',compression='zstd')
    con.register('members',membership)
    run('CREATE OR REPLACE TABLE membership AS SELECT * FROM members')
    con.unregister('members');del membership,uids,uid_index,parents,sizes,roots,minidx;gc.collect()
    AUD['linkage']=link_stats
    AUD['linked_entities']=scalar('SELECT count(DISTINCT entity_id) FROM membership')
    AUD['linkage_group_sizes']=records('SELECT n_linked_uids,count(DISTINCT entity_id) n_entities FROM membership GROUP BY n_linked_uids ORDER BY n_linked_uids')
    run('CREATE OR REPLACE TABLE entity_stats AS SELECT entity_id,count(DISTINCT target) n_entity_labels FROM eligible JOIN membership USING(uid) GROUP BY entity_id')
    run('CREATE OR REPLACE TABLE candidates AS SELECT s.*,m.entity_id,m.n_linked_uids,u.n_eligible_spectra,u.n_eligible_labels,u.n_gaia_ids,u.n_ps_ids,a.n_all_spectra,a.n_all_seven_labels,e.n_entity_labels FROM source_selected s JOIN membership m USING(uid) JOIN uid_stats u USING(uid) JOIN all_uid_stats a USING(uid) JOIN entity_stats e USING(entity_id)')
    run('CREATE OR REPLACE TABLE entity_selected AS SELECT * EXCLUDE(rn) FROM (SELECT *,row_number() OVER(PARTITION BY entity_id ORDER BY quality_snri DESC NULLS LAST,obsid) rn FROM candidates) WHERE rn=1')
    log('Auditing exact feature-vector duplicates and contradictory targets')
    run(f'CREATE OR REPLACE TABLE vector_stats AS SELECT {FS},count(*) n_exact_vector_entities,count(DISTINCT target) n_exact_vector_labels FROM entity_selected GROUP BY {FS}')
    AUD['exact_duplicate_vectors']=records('SELECT n_exact_vector_entities,n_exact_vector_labels,count(*) n_vectors FROM vector_stats WHERE n_exact_vector_entities>1 GROUP BY ALL ORDER BY 1,2')
    AUD['contradictory_vector_rows']=scalar('SELECT coalesce(sum(n_exact_vector_entities),0) FROM vector_stats WHERE n_exact_vector_labels>1')
    run(f'CREATE OR REPLACE TABLE vector_ranked AS SELECT e.*,v.n_exact_vector_entities,v.n_exact_vector_labels,row_number() OVER(PARTITION BY {", ".join("e."+f for f in F)} ORDER BY quality_snri DESC NULLS LAST,obsid) vector_rank FROM entity_selected e JOIN vector_stats v USING({FS})')
    run('CREATE OR REPLACE TABLE baseline AS SELECT * FROM vector_ranked WHERE n_exact_vector_labels=1 AND vector_rank=1')
    AUD['same_label_exact_vector_reductions']=scalar('SELECT count(*) FROM vector_ranked WHERE n_exact_vector_labels=1 AND vector_rank>1')
    AUD['baseline_rows']=scalar('SELECT count(*) FROM baseline')
    AUD['baseline_class_counts']=records('SELECT target,count(*) n FROM baseline GROUP BY target ORDER BY target')
    AUD['baseline_quality_flags']=records('SELECT count(*) FILTER(WHERE n_eligible_labels>1) within_uid_label_disagreement,count(*) FILTER(WHERE n_all_seven_labels>1) all_observation_label_disagreement,count(*) FILTER(WHERE n_entity_labels>1) linked_entity_label_disagreement,count(*) FILTER(WHERE n_gaia_ids>1 OR n_ps_ids>1) changing_counterpart_ids,count(*) FILTER(WHERE quality_snri IS NULL) invalid_quality_snri,count(*) FILTER(WHERE fibermask<>0) nonzero_fibermask FROM baseline')[0]
    assert AUD['baseline_rows']>=1500000
    labels_case='CASE target '+ ' '.join(f"WHEN '{v}' THEN {i}" for i,v in enumerate(LABELS))+' END'
    copy(f'SELECT obsid::BIGINT sample_id,{FS},target label,({labels_case})::TINYINT label_id FROM baseline ORDER BY obsid','data/baseline.parquet')
    metadata=['uid','entity_id','gaia_source_id','ps_id','class','subclass','quality_snri','snru','snrg','snrr','snri','snrz','n_all_spectra','n_eligible_spectra','n_all_seven_labels','n_eligible_labels','n_entity_labels','n_linked_uids','n_gaia_ids','n_ps_ids','n_exact_vector_entities','fibermask','fibertype','planid','mjd','ra','dec','offsets','offsets_v']
    copy('SELECT obsid::BIGINT sample_id,'+', '.join(metadata)+', (n_all_seven_labels=1 AND n_entity_labels=1) strict_consensus FROM baseline ORDER BY obsid','data/metadata.parquet')
    copy(f'SELECT obsid::BIGINT sample_id,uid,entity_id,{FS},target label,quality_snri,n_eligible_labels,n_all_seven_labels,n_entity_labels,n_linked_uids,n_gaia_ids,n_ps_ids FROM candidates ORDER BY obsid','data/source_candidates.parquet')
    copy('SELECT obsid::BIGINT sample_id,uid,entity_id,target label,n_exact_vector_entities,n_exact_vector_labels FROM vector_ranked WHERE n_exact_vector_labels>1','audit/contradictory_vectors.parquet')
    copy("""SELECT r.obsid::BIGINT sample_id,r.uid,r.target label,CASE
      WHEN r.target='OTHER' THEN 'outside_seven_class_taxonomy'
      WHEN r.uid IS NULL OR trim(r.uid)='' OR r.obsid IS NULL OR r.obsid<=0 THEN 'invalid_identifier'
      WHEN (r.mag_ps_g=0 AND r.mag_ps_r=0 AND r.mag_ps_i=0 AND r.mag_ps_z=0 AND r.mag_ps_y=0 AND coalesce(try_cast(r.ps_id AS HUGEINT),0)<=0) THEN 'zero_photometry_missing_counterpart'
      WHEN NOT ("""+' AND '.join(f'(isfinite(r.{c}) AND r.{c} BETWEEN -30 AND 50)' for c in F)+""") OR """+' OR '.join(f'r.{c} IS NULL' for c in F)+""" THEN 'incomplete_or_invalid_photometry'
      WHEN r.obsid<>s.obsid THEN 'repeat_observation_same_uid'
      WHEN r.obsid<>es.obsid THEN 'shared_counterpart_other_uid'
      WHEN v.n_exact_vector_labels>1 THEN 'contradictory_exact_feature_vector'
      WHEN v.vector_rank>1 THEN 'same_label_exact_feature_vector'
      ELSE 'retained' END reason FROM raw r LEFT JOIN source_selected s ON r.uid=s.uid
      LEFT JOIN membership m ON r.uid=m.uid LEFT JOIN entity_selected es ON m.entity_id=es.entity_id
      LEFT JOIN vector_ranked v ON es.obsid=v.obsid""",'audit/row_disposition.parquet')
    AUD['row_disposition']=records(f"SELECT reason,count(*) n FROM read_parquet('{ROOT/'audit/row_disposition.parquet'}') GROUP BY reason ORDER BY n DESC")
    assert sum(r['n'] for r in AUD['row_disposition'])==11441011
    assert next(r['n'] for r in AUD['row_disposition'] if r['reason']=='retained')==AUD['baseline_rows']
    save_json('cleaning_audit.json',AUD)
    log('Freezing stratified source-disjoint test/development/reserve memberships')
    df=pq.read_table(ROOT/'data/baseline.parquet').to_pandas()
    idx=np.arange(len(df)); y=df.label_id.to_numpy()
    pool,test=train_test_split(idx,test_size=500000,stratify=y,random_state=SEED)
    reserve,dev=train_test_split(pool,test_size=1000000,stratify=y[pool],random_state=SEED+1)
    fit,tune=train_test_split(dev,test_size=200000,stratify=y[dev],random_state=SEED+2)
    split=np.full(len(df),'reserve',dtype=object);split[test]='test';split[dev]='development'
    ref=np.full(len(df),'reserve',dtype=object);ref[test]='test';ref[fit]='reference_fit';ref[tune]='reference_tune'
    splits=pd.DataFrame({'sample_id':df.sample_id,'split':split,'reference_partition':ref})
    pq.write_table(pa.Table.from_pandas(splits,preserve_index=False),ROOT/'data/splits.parquet',compression='zstd')
    AUD['split_class_counts']=pd.crosstab(pd.Series(y).map(dict(enumerate(LABELS))),split).to_dict()
    AUD['split_sizes']={s:int(np.sum(split==s)) for s in ('development','test','reserve')}
    save_json('label_mapping.json',{'label_to_id':dict(zip(LABELS,range(7))),'features':F,'seed':SEED})
    Xfit=df.iloc[fit][F]
    correlation=Xfit.corr(); correlation.to_csv(ROOT/'audit/reference_fit_pearson.csv')
    Xfit.corr(method='spearman').to_csv(ROOT/'audit/reference_fit_spearman.csv')
    Xfit.describe(percentiles=[.001,.01,.25,.5,.75,.99,.999]).to_csv(ROOT/'audit/reference_fit_feature_profile.csv')
    AUD['reference_fit_constant_features']=[f for f in F if Xfit[f].nunique()<=1]
    AUD['reference_fit_identical_columns']=[[a,b] for i,a in enumerate(F) for b in F[i+1:] if np.array_equal(Xfit[a].to_numpy(),Xfit[b].to_numpy())]
    AUD['reference_fit_largest_abs_pearson']=float(np.max(np.abs(correlation.to_numpy()-np.eye(6))))
    assert not AUD['reference_fit_constant_features'] and not AUD['reference_fit_identical_columns']
    log('Fitting reference scalers only on 800,000 reference-fit rows')
    prep=TrainOnlyPreprocessor('standard').fit(Xfit)
    robust=TrainOnlyPreprocessor('robust').fit(Xfit)
    joblib.dump(prep,ROOT/'data/reference_standard_scaler.joblib');joblib.dump(robust,ROOT/'data/reference_robust_scaler.joblib')
    save_json('reference_standard_scaler.json',prep.summary());save_json('reference_robust_scaler.json',robust.summary())
    flags=prep.outlier_mask(df[F]);pq.write_table(pa.table({'sample_id':df.sample_id,'marginal_8sigma_flag':flags}),ROOT/'data/outlier_flags.parquet',compression='zstd')
    flag_df=pd.DataFrame({'partition':ref,'label':df.label,'flag':flags})
    AUD['outlier_flags']=flag_df.groupby(['partition','label']).agg(n=('flag','size'),n_flagged=('flag','sum')).reset_index().to_dict('records')
    # Convenient standard-scaled snapshot for the reference 800k/200k/500k setup only.
    chosen=np.sort(np.concatenate([fit,tune,test])); standard=prep.transform(df.iloc[chosen][F])
    out=pd.DataFrame(standard,columns=F);out.insert(0,'sample_id',df.iloc[chosen].sample_id.to_numpy());out['label_id']=y[chosen];out['reference_partition']=ref[chosen]
    pq.write_table(pa.Table.from_pandas(out,preserve_index=False),ROOT/'data/reference_standardized.parquet',compression='zstd')
    train_transformed=prep.transform(Xfit)
    AUD['reference_scaling_check']={'n_fit':prep.n_fit_rows_,'max_abs_fit_mean':float(np.max(np.abs(train_transformed.mean(axis=0)))),'max_abs_fit_std_minus_one':float(np.max(np.abs(train_transformed.std(axis=0)-1))),'heldout_rows_removed':0,'valid_outlier_rows_removed':0}
    del out,standard,train_transformed,Xfit;gc.collect()
    log('Checking immutable membership, finite features, and cross-split counterpart leakage')
    run(f"CREATE OR REPLACE VIEW frozen AS SELECT b.*,s.split,s.reference_partition FROM read_parquet('{ROOT/'data/baseline.parquet'}') b JOIN read_parquet('{ROOT/'data/splits.parquet'}') s USING(sample_id)")
    checks={
      'n_rows':scalar('SELECT count(*) FROM frozen'),
      'duplicate_sample_ids':scalar('SELECT count(*)-count(DISTINCT sample_id) FROM frozen'),
      'nonfinite_or_invalid_features':scalar('SELECT count(*) FROM frozen WHERE NOT ('+VALID+')'),
      'classes':scalar('SELECT count(DISTINCT label) FROM frozen'),
      'duplicate_feature_vectors':scalar(f'SELECT count(*) FROM (SELECT {FS} FROM frozen GROUP BY {FS} HAVING count(*)>1)'),
      'uids_in_multiple_splits':scalar('SELECT count(*) FROM (SELECT uid FROM baseline b JOIN frozen f ON b.obsid=f.sample_id GROUP BY uid HAVING count(DISTINCT split)>1)'),
      'entities_in_multiple_splits':scalar('SELECT count(*) FROM (SELECT entity_id FROM baseline b JOIN frozen f ON b.obsid=f.sample_id GROUP BY entity_id HAVING count(DISTINCT split)>1)')}
    # Test all eligible observations linked to retained entities, not merely selected counterparts.
    for col in ('gaia_source_id','ps_id'):
        checks[col+'_across_splits']=scalar(f'SELECT count(*) FROM (SELECT e.{col} FROM eligible e JOIN membership m USING(uid) JOIN baseline b USING(entity_id) JOIN frozen f ON b.obsid=f.sample_id WHERE try_cast(e.{col} AS HUGEINT)>0 GROUP BY e.{col} HAVING count(DISTINCT split)>1)')
    checks['source_level_disjointness_only']='Sky, plate and survey-selection effects are not eliminated by source deduplication.'
    for k,v in checks.items():
        if k not in ('n_rows','classes','source_level_disjointness_only'):assert v==0,(k,v)
    assert checks['classes']==7 and checks['n_rows']==len(df)
    AUD['integrity_checks']=checks
    AUD['reference_seed']=SEED
    AUD['protocol']={'fixed_magnitude_bounds':[-30,50],'outlier_policy':'retain valid rows; training-reference marginal 8 robust-sigma flag only','label_policy':'highest valid i-band SNR eligible observation, obsid ascending tie-break; retain label-disagreement flags','test_n':500000,'development_n':1000000,'reference_fit_n':800000,'reference_tune_n':200000,'conformal_partition':'not allocated; reference 80/20 matches prior development plan','learned_preprocessing':'refit on each experiment fit subset; never use this reference scaler for smaller fit budgets','strong_correlations':'retained; audit reference-fit only','density_model_note':'Standard and robust transforms available; no covariance regularization or model tuning performed'}
    save_json('cleaning_audit.json',AUD)
    con.close()
    log('Complete. No classifier experiments have run.')
if __name__=='__main__':main()
