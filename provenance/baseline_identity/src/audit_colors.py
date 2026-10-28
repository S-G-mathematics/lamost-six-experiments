"""Training-only color-tail diagnostic; flags are not an error verdict or deletion."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from preprocessing import FEATURE_COLUMNS
ROOT=Path(__file__).resolve().parents[1]
COLOR_PAIRS=[(0,1),(1,2),(2,3),(3,4),(1,5)]
COLOR_NAMES=['ps_g_minus_r','ps_r_minus_i','ps_i_minus_z','ps_z_minus_y','ps_r_minus_gaia_g']

def main():
    df=pq.read_table(ROOT/'data/baseline.parquet').to_pandas()
    splits=pq.read_table(ROOT/'data/splits.parquet').to_pandas()
    assert np.array_equal(df.sample_id.to_numpy(),splits.sample_id.to_numpy())
    fit=splits.reference_partition.eq('reference_fit').to_numpy()
    X=df[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float64)
    C=np.column_stack([X[:,a]-X[:,b] for a,b in COLOR_PAIRS]); T=C[fit]
    med=np.median(T,axis=0); sig=1.4826*np.median(np.abs(T-med),axis=0)
    q25,q75=np.quantile(T,[.25,.75],axis=0);sig=np.where(sig>0,sig,(q75-q25)/1.349)
    flags=np.abs(C-med)>8*sig
    per_row=flags.any(axis=1)
    result={'fit_partition':'reference_fit','n_fit':int(fit.sum()),'threshold_robust_sigma':8,'color_names':COLOR_NAMES,'fit_medians':med.tolist(),'fit_robust_sigma':sig.tolist(),'flagged_rows':int(per_row.sum()),'flagged_by_color':dict(zip(COLOR_NAMES,flags.sum(axis=0).astype(int).tolist())),'flagged_by_partition_and_class':pd.DataFrame({'label':df.label,'partition':splits.reference_partition,'flag':per_row}).groupby(['partition','label']).agg(n=('flag','size'),n_flagged=('flag','sum')).reset_index().to_dict('records'),'policy':'Diagnostic only. Global color tails can include valid rare stellar types, reddened sources, variability, or mismatches; do not label all flags as errors or remove held-out rows.'}
    cor=np.corrcoef(X[fit],rowvar=False);eig=np.linalg.eigvalsh(cor)
    result['fit_correlation_eigenvalues']=eig.tolist();result['fit_correlation_condition_number']=float(eig[-1]/eig[0]);result['fit_correlation_rank']=int(np.linalg.matrix_rank(cor))
    result['strict_consensus_by_partition']=None
    meta=pq.read_table(ROOT/'data/metadata.parquet',columns=['sample_id','strict_consensus']).to_pandas()
    assert np.array_equal(meta.sample_id.to_numpy(),df.sample_id.to_numpy())
    result['strict_consensus_rows']=int(meta.strict_consensus.sum())
    result['strict_consensus_by_partition']=pd.DataFrame({'partition':splits.reference_partition,'strict_consensus':meta.strict_consensus}).groupby('partition').strict_consensus.agg(['size','sum']).reset_index().to_dict('records')
    pq.write_table(pa.table({'sample_id':df.sample_id,'marginal_color_8sigma_flag':per_row,**{name+'_flag':flags[:,i] for i,name in enumerate(COLOR_NAMES)}}),ROOT/'data/color_tail_flags.parquet',compression='zstd')
    (ROOT/'audit/color_tail_audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('n_fit','flagged_rows','fit_correlation_condition_number','fit_correlation_rank','strict_consensus_rows')},indent=2))
if __name__=='__main__':main()
