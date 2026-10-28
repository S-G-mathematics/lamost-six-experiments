#!/usr/bin/env python3
"""Render three metadata-only E4 direct-kernel figures from already-validated CSVs."""
from pathlib import Path
import csv,importlib.util,json,statistics,time,os,sys
D=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/e4_direct_kernel_block_20261027')
def read(name):
 with (D/name).open() as f:return list(csv.DictReader(f))
def resource_gate():
 R=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025');sys.path.insert(0,str(R/'source'))
 import cold_auto_compaction as comp, observe_progress as progress
 comp.verify_instance();controller=comp.load_controller();comp.verify_source_set(controller);records,meta=comp.records_readonly();allowed,profile=comp.running_worker_profile(controller,records);obs=progress.observe(False)
 if not allowed:raise RuntimeError('Reviewed worker-memory admission denies plot')
 if not obs.get('controller_actual_verified') or obs.get('registry_running_unverified_at_observation'):raise RuntimeError('Controller/worker identity incomplete')
 if len(obs.get('workers_actual_verified',[]))!=profile.get('running'):raise RuntimeError('Worker identity count mismatch')
 before=controller.cpu_idle_cores();time.sleep(1);after=controller.cpu_idle_cores();idle=max(before,after)
 if idle<1:raise RuntimeError('CPU idle headroom below one core')
 free=os.statvfs(R);disk=free.f_bavail*free.f_frsize
 if disk<2*1024**3:raise RuntimeError('Disk headroom below2GiB')
 busy=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:argv=[x for x in (p/'cmdline').read_bytes().decode(errors='replace').split('\0') if x]
  except OSError:continue
  found={Path(x).name for x in argv if '/' in x}&{'report_cli.py','cold_auto_compactor.py','cold_store_auditor.py','audit_selected_models.py','finalize_project.py'}
  if found:busy.extend(found)
 if busy:raise RuntimeError('Another heavy report/audit helper is active')
 return {'observed_utc':obs['observed_utc'],'available_ram_bytes':profile['available_bytes'],'commitments':profile['commitments'],'helper_reservation_bytes':profile['helper_reservation_bytes'],'host_reserve_bytes':6*1024**3,'growth_margin_bytes':2*1024**3,'required_postcommitment_headroom_bytes':805306368,'memory_admission_passed':True,'running_worker_count':profile['running'],'workers_identity_verified':len(obs['workers_actual_verified']),'controller_identity_verified':True,'cpu_idle_cores':idle,'storage_free_bytes':disk,'active_report_audit_helpers':False,'plot_address_space_limit_bytes':1024**3}
gate=resource_gate()
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import resource
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
rows=read('E4_DIRECT_KERNEL_90_OUTCOMES.csv')
order=['control']+[f'{t}_{s}' for t in ['A','F','G','K','M','GALAXY','QSO'] for s in ['half','tenth']]
labels=['control']+[f'{t} {s}' for t in ['A','F','G','K','M','GALAXY','QSO'] for s in ['half','tenth']]
methods=['rbf_svm','kde'];names={'rbf_svm':'RBF-SVM','kde':'KDE'};statuscolors={'successful':'#238b45','scientific_failure':'#cb181d','unavailable_dependency':'#969696','unsupported':'#6a51a3'}
repcolors={1:'#2878b5',2:'#e07a1f',3:'#25855a'};repmk={1:'o',2:'s',3:'^'}
index={(x['method'],x['condition'],int(x['rep'])):x for x in rows}
def validvals(m,cond,metric):
 return [(int(r),float(index[m,cond,int(r)][metric])) for r in (1,2,3) if index[m,cond,int(r)]['outcome']=='successful' and index[m,cond,int(r)][metric]!='']
# 1. Full cell availability, all conditions and both methods, fixed denominator 3.
fig,axes=plt.subplots(1,2,figsize=(14,8),sharex=True,sharey=True)
for ax,m in zip(axes,methods):
 for yi,c in enumerate(order):
  counts={s:sum(index[m,c,r]['outcome']==s for r in (1,2,3)) for s in statuscolors}
  left=0
  for s,color in statuscolors.items():
   n=counts[s]
   if n: ax.barh(yi,n,left=left,color=color,edgecolor='white',height=.72,label=s.replace('_',' ') if yi==0 else None)
   left+=n
  # Exact success/failure/unavailable triplet is also printed to avoid reliance on color.
  ax.text(3.04,yi,f"{counts['successful']}/{counts['scientific_failure']}/{counts['unavailable_dependency']}",va='center',fontsize=7)
 ax.set_title(names[m]);ax.set_xlim(0,3.8);ax.set_yticks(range(len(order)),labels);ax.invert_yaxis();ax.set_xlabel('Cases per condition (3 planned)');ax.grid(axis='x',alpha=.2)
axes[0].set_ylabel('Target / condition')

fig.suptitle('E4 direct-kernel availability: success / failure / unavailable by condition',y=.995)
fig.legend(handles=[Patch(facecolor=statuscolors['successful'],label='successful'),Patch(facecolor=statuscolors['scientific_failure'],label='scientific failure'),Patch(facecolor=statuscolors['unavailable_dependency'],label='unavailable dependency')],loc='upper center',bbox_to_anchor=(.5,.955),ncol=3,fontsize=8,frameon=False)
fig.text(.5,.01,'Rows show all 3 repetitions. KDE control cells are aliases to unavailable E3 evaluations. No metric is imputed for failed or unavailable cells.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.04,1,.89));fig.savefig(D/'E4_DIRECT_KERNEL_AVAILABILITY.png',dpi=135);plt.close(fig)
if '--availability-only' in sys.argv:
 import resource as _resource,hashlib as _hashlib
 peak=_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
 gate['numpy_version_for_plot']=np.__version__;gate['matplotlib_version']=matplotlib.__version__;gate['python_address_space_limit_applied']=True;gate['plot_peak_rss_kib']=peak
 (D/'plot_resource_gate.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')
 if peak>512*1024:
  raise SystemExit(f'Availability render peak RSS exceeded 512 MiB: {peak} KiB')
 print(json.dumps({'figure':'E4_DIRECT_KERNEL_AVAILABILITY.png','bytes':(D/'E4_DIRECT_KERNEL_AVAILABILITY.png').stat().st_size,'sha256':_hashlib.sha256((D/'E4_DIRECT_KERNEL_AVAILABILITY.png').read_bytes()).hexdigest(),'resource_gate_utc':gate['observed_utc'],'peak_rss_kib':peak,'address_space_limit_bytes':gate['plot_address_space_limit_bytes']},indent=2))
 sys.exit(0)
# 2. Balanced accuracy, metrics only for validated successful evaluations. Shared honest 0..1 scale.
fig,axes=plt.subplots(1,2,figsize=(15,5.8),sharey=True)
for ax,m in zip(axes,methods):
 for xi,c in enumerate(order):
  vals=validvals(m,c,'balanced_accuracy')
  for rep,v in vals: ax.scatter(xi+(rep-2)*.12,v,color=repcolors[rep],marker=repmk[rep],s=30,zorder=3,label=f'rep {rep}' if xi==0 else None)
  if vals:
   ys=[v for _,v in vals];mean=statistics.mean(ys);sd=statistics.stdev(ys) if len(ys)>1 else None
   ax.errorbar(xi,mean,yerr=sd,color='black',marker='D',markersize=4,capsize=3,linewidth=1,zorder=4,label='mean +/- sample SD' if xi==0 else None)
 ax.set_title(names[m]);ax.set_ylim(0,1);ax.set_xticks(range(len(order)),[f'{lab}\n{len(validvals(m,c,"balanced_accuracy"))}/3' for lab,c in zip(labels,order)],rotation=55,ha='right',fontsize=8);ax.grid(axis='y',alpha=.25);ax.set_ylabel('Balanced accuracy')
 if not any(index[m,c,r]['outcome']=='successful' for c in order for r in (1,2,3)):
  ax.text(.5,.5,'No validated evaluation metrics\n(0/45 successful)',transform=ax.transAxes,ha='center',va='center',bbox={'facecolor':'white','alpha':.85,'edgecolor':'#777'})
axes[0].legend(handles=[Line2D([0],[0],marker=repmk[r],color='none',markerfacecolor=repcolors[r],label=f'rep {r}') for r in (1,2,3)]+[Line2D([0],[0],marker='D',color='black',label='mean +/- sample SD')],loc='lower left',fontsize=8)
fig.suptitle('E4 direct-kernel balanced accuracy, conditional on successful evaluation')
fig.text(.5,.01,'Labels give successful repetitions / 3. Points are individual repetitions; black diamonds are means, with sample SD only for n > 1. Failures have no score.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.05,1,.93));fig.savefig(D/'E4_DIRECT_KERNEL_BALANCED_ACCURACY.png',dpi=135);plt.close(fig)
# 3. Coverage + set size for each method, same conditions/denominators; show nominal target.
fig,axes=plt.subplots(2,2,figsize=(15,8),sharex='col')
for col,m in enumerate(methods):
 for row,metric in enumerate(['coverage','mean_set_size']):
  ax=axes[row,col]
  for xi,c in enumerate(order):
   vals=validvals(m,c,metric)
   for rep,v in vals:ax.scatter(xi+(rep-2)*.12,v,color=repcolors[rep],marker=repmk[rep],s=28,zorder=3,label=f'rep {rep}' if xi==0 and row==0 else None)
   if vals:
    yy=[v for _,v in vals];mu=statistics.mean(yy);sd=statistics.stdev(yy) if len(yy)>1 else None
    ax.errorbar(xi,mu,yerr=sd,color='black',marker='D',markersize=4,capsize=3,linewidth=1,zorder=4,label='mean +/- sample SD' if xi==0 and row==0 else None)
  ax.set_title(names[m]+' - '+('coverage' if metric=='coverage' else 'mean prediction-set size'))
  ax.set_xticks(range(len(order)),[f'{lab}\n{len(validvals(m,c,metric))}/3' for lab,c in zip(labels,order)],rotation=55,ha='right',fontsize=7)
  ax.grid(axis='y',alpha=.22)
  if metric=='coverage':ax.set_ylim(0,1);ax.axhline(.9,color='#777',linestyle='--',linewidth=1,label='nominal 90%')
  else:ax.set_ylim(0,7)
  ax.set_ylabel('Coverage' if metric=='coverage' else 'Mean set size')
  if not any(index[m,c,r]['outcome']=='successful' for c in order for r in (1,2,3)):
   ax.text(.5,.5,'No validated evaluation metrics\n(0/45 successful)',transform=ax.transAxes,ha='center',va='center',bbox={'facecolor':'white','alpha':.85,'edgecolor':'#777'})
axes[0,0].legend(handles=[Line2D([0],[0],marker=repmk[r],color='none',markerfacecolor=repcolors[r],label=f'rep {r}') for r in (1,2,3)]+[Line2D([0],[0],marker='D',color='black',label='mean +/- sample SD'),Line2D([0],[0],color='#777',linestyle='--',label='nominal 90% coverage')],loc='lower left',fontsize=7)
fig.suptitle('E4 direct-kernel conformal coverage and set size, conditional on successful evaluation')
fig.text(.5,.01,'Labels give successful repetitions / 3. Points are individual repetitions; black diamonds are means, with sample SD only for n > 1. Coverage is paired with set size; no threshold was recomputed.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.05,1,.93));fig.savefig(D/'E4_DIRECT_KERNEL_COVERAGE_AND_SET_SIZE.png',dpi=135);plt.close(fig)
# Store only public resource summary and output figure hashes; no worker identities or process receipts.
gate['numpy_version_for_plot']=np.__version__;gate['matplotlib_version']=matplotlib.__version__;gate['python_address_space_limit_applied']=True
(D/'plot_resource_gate.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')
import resource as rs
print(json.dumps({'figures':[{'name':n,'bytes':(D/n).stat().st_size,'sha256':__import__('hashlib').sha256((D/n).read_bytes()).hexdigest()} for n in ['E4_DIRECT_KERNEL_AVAILABILITY.png','E4_DIRECT_KERNEL_BALANCED_ACCURACY.png','E4_DIRECT_KERNEL_COVERAGE_AND_SET_SIZE.png']],'gate_observed_utc':gate['observed_utc'],'worker_count':gate['running_worker_count'],'available_gib':round(gate['available_ram_bytes']/1024**3,2),'idle_cores':gate['cpu_idle_cores'],'plot_as_limit':gate['plot_address_space_limit_bytes'],'maxrss_kib':rs.getrusage(rs.RUSAGE_SELF).ru_maxrss,'numpy':np.__version__,'matplotlib':matplotlib.__version__},indent=2))
