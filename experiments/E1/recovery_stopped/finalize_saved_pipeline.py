import argparse, datetime, hashlib, json, pathlib, time
import joblib
import numpy as np
from benchmark.engine import FEATURES, _canonical_frame, _predict_chunks, load_data
from benchmark.evaluation import conformal_threshold, conformal_evaluate

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-cell',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    parser.add_argument('--baseline',type=pathlib.Path,required=True)
    parser.add_argument('--validate-against-source',action='store_true')
    args=parser.parse_args()
    source=args.source_cell
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source/'manifest.json').read_text())
    pipeline_path=source/'pipeline.joblib'
    if not pipeline_path.exists():
        raise RuntimeError('saved fitted pipeline missing')
    pipe=joblib.load(pipeline_path)
    model=pipe['model']
    imputer=pipe['imputer']
    scaler=pipe['scaler']
    frame,split_col=load_data(args.baseline,include_test=True)
    frame=_canonical_frame(frame)
    mask=frame[split_col].astype(str).str.lower().eq('test').to_numpy()
    test_pos=np.flatnonzero(mask)
    role_file=source.parent/'role_positions.npz'
    with np.load(role_file) as roles:
        cal_idx=roles['calibration']
    ids=frame['sample_id'].to_numpy()[test_pos]
    labels=frame['label_id'].to_numpy(dtype=np.int64)
    Xraw=frame[FEATURES].to_numpy(dtype=np.float64)
    Xcal=scaler.transform(imputer.transform(Xraw[cal_idx]))
    _,cal_scores,_=_predict_chunks(model,Xcal,50000,diagnostics=True)
    score_kind=getattr(model,'score_kind','probability')
    threshold=conformal_threshold(cal_scores,labels[cal_idx],score_kind=score_kind,alpha=0.10)
    Xtest=scaler.transform(imputer.transform(Xraw[test_pos]))
    chunks=out/'chunks'
    chunks.mkdir(exist_ok=True)
    pred_parts=[];score_parts=[];fallback_parts=[]
    for start in range(0,len(Xtest),50000):
        stop=min(start+50000,len(Xtest))
        chunk_file=chunks/('rows_'+str(start)+'_'+str(stop)+'.npz')
        if chunk_file.exists():
            with np.load(chunk_file) as saved:
                pred=saved['pred'];scores=saved['scores'];fallback=saved['fallback']
        else:
            started=time.monotonic()
            pred,scores,fallback=_predict_chunks(model,Xtest[start:stop],50000,diagnostics=True)
            np.savez_compressed(chunk_file,pred=pred.astype(np.int16),scores=scores.astype(np.float32),fallback=fallback.astype(np.uint8))
            print('chunk',start,stop,'seconds',round(time.monotonic()-started,2),flush=True)
        if len(pred)!=stop-start or scores.shape!=(stop-start,7) or len(fallback)!=stop-start:
            raise RuntimeError('invalid saved chunk shape')
        pred_parts.append(pred.astype(np.int16))
        score_parts.append(scores.astype(np.float32))
        fallback_parts.append(fallback.astype(np.uint8))
    pred=np.concatenate(pred_parts);scores=np.concatenate(score_parts);fallback=np.concatenate(fallback_parts)
    outcome=conformal_evaluate(scores,labels[test_pos],threshold,score_kind=score_kind)
    sets=outcome['sets'].astype(np.uint8)
    result={'status':'saved_pipeline_finalized','method':manifest['method'],'budget':manifest['budget'],'repetition':manifest['repetition'],'source_cell':str(source),'source_pipeline_sha256':sha256(pipeline_path),'threshold':float(threshold),'balanced_accuracy':float(outcome['balanced_accuracy']),'coverage':float(outcome['coverage']),'mean_prediction_set_size':float(outcome['set_size']),'test_rows':len(test_pos),'score_kind':score_kind,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'no_refit':True}
    if args.validate_against_source:
        complete=json.loads((source/'complete.json').read_text())
        original=source/'test_predictions.npz'
        if not original.exists():
            raise RuntimeError('source prediction arrays missing for validation')
        with np.load(original) as reference:
            actual={'sample_id':ids,'y_pred':pred,'scores':scores,'prediction_sets':sets,'invalid_support_fallback':fallback}
            checks={k:np.array_equal(reference[k],v) for k,v in actual.items()}
        checks['threshold']=bool(np.isclose(complete['conformal_nonconformity_threshold'],threshold,rtol=0,atol=1e-12))
        checks['balanced_accuracy']=bool(np.isclose(complete['test_metrics']['balanced_accuracy'],result['balanced_accuracy'],rtol=0,atol=1e-12))
        checks['coverage']=bool(np.isclose(complete['test_coverage'],result['coverage'],rtol=0,atol=1e-12))
        checks['set_size']=bool(np.isclose(complete['mean_prediction_set_size'],result['mean_prediction_set_size'],rtol=0,atol=1e-12))
        result['validation_checks']=checks
        if not all(checks.values()):
            (out/'validation_failed.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
            raise RuntimeError('saved pipeline finalizer did not reproduce source result')
    np.savez_compressed(out/'test_predictions.npz',sample_id=ids,y_pred=pred,scores=scores,prediction_sets=sets,invalid_support_fallback=fallback)
    temp=out/'finalization.json.tmp'
    temp.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    temp.replace(out/'finalization.json')
    print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__':
    main()
