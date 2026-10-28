#!/usr/bin/env python3
"""Render only the three existing E5 route-summary figures; no input or metrics are changed."""
import csv, math, os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/e5_completed_generator_routes_20261027')
with (ROOT/'matched_route_degradation_summary.csv').open(newline='',encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
families=('gmm','copula','chow_liu')
colors={'gmm':'#2563eb','copula':'#e8790c','chow_liu':'#16834a'}
display_family={'gmm':'GMM','copula':'Copula','chow_liu':'Chow-Liu'}
display_route={'direct':'Direct Bayes','logistic':'Synthetic Logistic','hist_gb':'Synthetic HistGB'}
style={'direct':'-','logistic':'--','hist_gb':':'}
for metric,title,filename in (
 ('balanced_accuracy','Balanced accuracy change from route-matched clean control','E5_balanced_accuracy_degradation.png'),
 ('coverage','Conformal coverage change from route-matched clean control','E5_coverage_degradation.png'),
 ('set_size','Mean conformal set-size change from route-matched clean control','E5_set_size_degradation.png')):
    fig,axes=plt.subplots(1,3,figsize=(16,7),sharey=True)
    for ax,mechanism in zip(axes,('feature_noise','missingness','label_noise')):
        for family in families:
            for learner in ('direct','logistic','hist_gb'):
                xs=[]; ys=[]
                for rate in (.05,.10,.20):
                    comparison_learner='logistic' if learner=='direct' else learner
                    row=next((r for r in rows if r['generator_family']==family
                       and r['downstream_learner']==comparison_learner
                       and r['mechanism']==mechanism
                       and math.isclose(float(r['rate']),rate)),None)
                    if row is None: continue
                    field=f'direct_corruption_change_{metric}_mean' if learner=='direct' else f'synthetic_corruption_change_{metric}_mean'
                    value=row.get(field)
                    if value in ('',None): continue
                    xs.append(int(round(rate*100))); ys.append(float(value))
                if xs:
                    label=f'{display_family[family]} {display_route[learner]}'
                    ax.plot(xs,ys,marker='o',linestyle=style[learner],color=colors[family],label=label)
        ax.axhline(0,color='black',linewidth=.7)
        ax.set_title(mechanism.replace('_',' '))
        ax.set_xticks([5,10,20]); ax.set_xlabel('Affected fitting rows (%)')
    axes[0].set_ylabel('Corrupted - clean')
    fig.suptitle(title+' (means across n=3 paired repetitions per point)')
    fig.text(.5,.01,'Each mean uses n=3 paired repetitions. Tables report achieved coverage; companion coverage plot shows change from clean.',ha='center',fontsize=8)
    handles,labels=axes[-1].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.065),ncol=3,fontsize=8)
    fig.tight_layout(rect=[0,.30,1,.92])
    fig.savefig(ROOT/filename,dpi=140); plt.close(fig)

