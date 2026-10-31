import collections,hashlib,json,pathlib,sqlite3
ROOT=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
R=ROOT/'runtime_20261025'
op='auto_storage_20261028T203121Z_cd9a9cc9'
child=R/'runs'/op/'child_result.json'
child_sha=hashlib.sha256(child.read_bytes()).hexdigest()
doc=json.loads(child.read_text())
db=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True)
db.execute('PRAGMA query_only=ON')
records={x['key']:x for (raw,) in db.execute('select record from tasks') for x in [json.loads(raw)]}
db.close()
exclusions=doc['candidate_filter']['exclusions']
selection_rows=[x for x in exclusions if x.get('reason','').endswith('/selection.json')]
pub_rows=[x for x in exclusions if x.get('reason','').endswith('/fit_publication.json')]
assert len(exclusions)==605 and len(selection_rows)==578 and len(pub_rows)==27
group_receipts=[]
failures=[]
for x in selection_rows:
    key=x['producer_task'];source_sha=x['source_sha256'];base=R/'artifacts'/key
    attempt=next(a.split('/attempts/',1)[1].split('/',1)[0] for a in x['aliases'] if '/attempts/' in a)
    task_sha=next(a.split('/checkpoints/',1)[1].split('/',1)[0] for a in x['aliases'] if '/checkpoints/' in a)
    paths={
      'canonical_selection':base/'selection.json',
      'validation':base/'validation.json',
      'fit_result':base/'fit_result.json',
      'canonical_publication':base/'fit_publication.json',
      'attempt_result':base/'attempts'/attempt/'attempt.json',
      'attempt_publication':base/'attempts'/attempt/'fit_publication.json',
      'attempt_selection':base/'attempts'/attempt/'selection.json',
      'checkpoint_selection':base/'checkpoints'/task_sha/'selection.json'
    }
    hashes={}
    for name in ('canonical_selection','validation','fit_result','canonical_publication','attempt_result','attempt_publication'):
        hashes[name+'_sha256']=hashlib.sha256(paths[name].read_bytes()).hexdigest()
    sel=json.loads(paths['canonical_selection'].read_text())
    val=json.loads(paths['validation'].read_text())
    fitb=paths['fit_result'].read_bytes();fit=json.loads(fitb)
    attemptb=paths['attempt_result'].read_bytes();attempt_doc=json.loads(attemptb)
    pub=json.loads(paths['canonical_publication'].read_text())
    apub=json.loads(paths['attempt_publication'].read_text())
    record=records[key];rr=record.get('result') or {};validation=rr.get('validation') or {}
    result=fit.get('result') or {};params=result.get('params')
    canonical_selection_sha=hashes['canonical_selection_sha256']
    expected_published_path=str((base/'pipeline.joblib').resolve(strict=False))
    local_copy_states={}
    for name in ('attempt_selection','checkpoint_selection'):
        p=paths[name]
        try:
            st=p.lstat();local_copy_states[name]='present_symlink' if p.is_symlink() else 'present_regular' if p.is_file() else 'present_nonregular'
        except FileNotFoundError:local_copy_states[name]='missing'
    checks={
      'selection_sha_matches_validation_file':val.get('files',{}).get('selection.json')==canonical_selection_sha,
      'selection_sha_matches_registry_validation':validation.get('files',{}).get('selection.json')==canonical_selection_sha,
      'selection_params_match_fit_result':isinstance(params,dict) and sel.get('selected_params')==params,
      'fit_result_success':result.get('status')=='success',
      'fit_result_pipeline_sha_matches_candidate':result.get('pipeline_sha256')==source_sha and fit.get('artifact_sha256')==source_sha,
      'attempt_and_canonical_fit_result_bytes_equal':attemptb==fitb,
      'registry_attempt_task_identity_matches':rr.get('attempt_id')==attempt and rr.get('task_sha256')==task_sha,
      'fit_result_attempt_task_identity_matches':fit.get('attempt_id')==attempt and fit.get('task_sha256')==task_sha,
      'publications_bind_same_validated_model':all(
        z.get('stage')=='validated_publication' and z.get('attempt_id')==attempt and
        z.get('task_sha256')==task_sha and z.get('pipeline_sha256')==source_sha and
        z.get('published_path')==expected_published_path for z in (pub,apub)
      ),
      'both_local_selection_copies_missing':local_copy_states=={'attempt_selection':'missing','checkpoint_selection':'missing'},
      'record_is_validated_fit':record.get('status')=='validated_terminal' and record.get('kind')=='fit'
    }
    passed=all(checks.values())
    entry={'task_key':key,'attempt_id':attempt,'task_sha256':task_sha,'candidate_pipeline_sha256':source_sha,
      'metadata_sha256':hashes,'local_selection_copy_states':local_copy_states,'checks':checks,'passed':passed}
    group_receipts.append(entry)
    if not passed:failures.append({'task_key':key,'failed_checks':[k for k,v in checks.items() if not v]})
missing_publications=[]
for x in pub_rows:
    key=x['producer_task'];missing=x['reason'].split('publication receipt file missing: ',1)[1]
    p=ROOT/missing
    try:st=p.lstat();absent=False
    except FileNotFoundError:absent=True
    missing_publications.append({'task_key':key,'candidate_pipeline_sha256':x['source_sha256'],'missing_path':missing,'path_is_absent':absent})
counts=collections.Counter(x.get('reason','').split('publication receipt file missing: ',1)[-1].split('/')[-1] for x in exclusions)
assert not failures, failures[:2]
assert all(x['path_is_absent'] for x in missing_publications)
assert all(x['missing_path'].endswith('/fit_publication.json') for x in missing_publications)
script_path=pathlib.Path(__file__)
result={
 'schema':'archive-candidate-publication-metadata-audit/1','status':'passed',
 'operation_id':op,'child_result_path':child.relative_to(ROOT).as_posix(),'child_result_sha256':child_sha,
 'candidate_exclusion_count':len(exclusions),'reason_counts':dict(sorted(counts.items())),
 'canonical_selection_fallback_candidates':len(group_receipts),'fallback_binding_pass_count':sum(1 for x in group_receipts if x['passed']),
 'missing_publication_excluded_count':len(missing_publications),'missing_publication_excluded_path':'fit_publication.json',
 'model_payloads_opened':0,'archive_payloads_opened':0,
 'registry_path':(R/'registry.sqlite').relative_to(ROOT).as_posix(),
 'script_path':script_path.relative_to(ROOT).as_posix(),'script_sha256':hashlib.sha256(script_path.read_bytes()).hexdigest(),
 'groups':group_receipts,'missing_publications':missing_publications
}
out=R/'staging'/'missing_attempt_selection_compat_20261029'/'runtime_20261025'/'reports'/'selection_receipt_metadata_audit_20261029.json'
out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({'receipt_path':str(out),'receipt_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
 'child_result_sha256':child_sha,'pass_groups':result['fallback_binding_pass_count'],
 'missing_publication_excluded':len(missing_publications),'reason_counts':dict(counts),
 'script_sha256':result['script_sha256']},sort_keys=True))
