#!/usr/bin/env python3
from pathlib import Path
import math,csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
BASE=Path(__file__).resolve().parent
CSV=BASE/"E1_method_budget_summary_153.csv"
METHODS=["arf","cart","chow_liu","copula","extra_trees","gaussian_nb","gmm","hist_gb","kde","knn","lda","linear_svm","logistic","qda","random_forest","rbf_svm","shared_diagonal"]
GENERATIVE=["arf","chow_liu","copula","gaussian_nb","gmm","kde","lda","qda","shared_diagonal"]
DISCRIMINATIVE=["cart","extra_trees","hist_gb","knn","linear_svm","logistic","random_forest","rbf_svm"]
BUDGETS=[100,300,1000,3000,10000,30000,100000,300000,1000000]
METRICS=[("balanced_accuracy_mean","balanced_accuracy_sample_sd","balanced_accuracy","Balanced accuracy"),
("coverage_mean","coverage_sample_sd","coverage","Conformal coverage"),
("mean_set_size_mean","mean_set_size_sample_sd","mean_set_size","Mean prediction set size")]
with CSV.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
lookup={(r["method"],int(r["budget"])):r for r in rows}
if len(rows)!=153 or len(lookup)!=153: raise SystemExit("expected one row for each of 17 methods x 9 budgets")
colors=plt.get_cmap("tab20")
for mean_col,sd_col,suffix,title in METRICS:
 fig,axes=plt.subplots(1,2,figsize=(18,10),sharex=True)
 handles=[]; labels=[]
 for ax,group,panel in [(axes[0],GENERATIVE,"Generative / probabilistic (9 methods)"),(axes[1],DISCRIMINATIVE,"Discriminative (8 methods)")]:
  for method in group:
   means=[]; sds=[]; counts=[]
   for budget in BUDGETS:
    row=lookup[(method,budget)]; n=int(row["successful_repetitions"]); counts.append(n)
    means.append(float(row[mean_col]) if row[mean_col].strip() else np.nan)
    sds.append(float(row[sd_col]) if row[sd_col].strip() else np.nan)
   x=np.asarray(BUDGETS,dtype=float); y=np.asarray(means,dtype=float); sd=np.asarray(sds,dtype=float)
   color=colors(METHODS.index(method)%20); yerr=np.where(np.asarray(counts)>=2,sd,np.nan)
   line=ax.errorbar(x,y,yerr=yerr,fmt="o-",lw=1.15,ms=3.4,capsize=2.0,color=color,alpha=.92)
   handles.append(line); labels.append(method.replace("_"," "))
   yrange=7.0 if suffix=="mean_set_size" else 1.0
   for j,(budget,n,val) in enumerate(zip(BUDGETS,counts,means)):
    if n>=5: continue
    ypos=(0.035*yrange) if math.isnan(val) else val
    ax.annotate(f"{n}/5",(budget,ypos),xytext=(2,5+(j%2)*3),textcoords="offset points",fontsize=6,color=color,ha="left",va="bottom",bbox=dict(boxstyle="round,pad=.08",fc="white",ec="none",alpha=.72))
  ax.set_xscale("log"); ax.set_xticks(BUDGETS); ax.set_xticklabels([f"{v:g}" for v in BUDGETS],rotation=35,ha="right")
  ax.set_title(panel,fontsize=12); ax.grid(True,which="major",axis="both",alpha=.22)
  ax.set_ylim(0,7 if suffix=="mean_set_size" else 1); ax.set_ylabel(title)
  if suffix=="coverage": ax.axhline(.90,color="black",ls="--",lw=1.2)
 fig.suptitle(f"E1 frozen benchmark: {title} by training budget\nMeans and sample SD across successful repetitions only",fontsize=15,y=.985)
 fig.supxlabel("Frozen training-sample budget (log scale)",y=.145)
 fig.text(.5,.105,"Point labels show successful repetitions / 5 where n < 5; n=0 is a gap, and n=1 has no SD.",ha="center",fontsize=9)
 if suffix=="coverage":
  from matplotlib.lines import Line2D
  handles.append(Line2D([0],[0],color="black",ls="--",lw=1.2)); labels.append("90% nominal target")
 fig.legend(handles,labels,loc="lower center",bbox_to_anchor=(.5,.012),ncol=6,fontsize=8,frameon=False)
 fig.subplots_adjust(left=.07,right=.99,top=.89,bottom=.24,wspace=.16)
 fig.savefig(BASE/f"E1_frozen_{suffix}_learning_curves.png",dpi=150,bbox_inches="tight"); plt.close(fig)
