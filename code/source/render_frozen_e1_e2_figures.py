import csv,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from PIL import Image
RT=Path("/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025");ROOT=RT.parent
OUT=RT/"reports/frozen_e1_e2_figures";E1=ROOT/"e1_wrapup_20261024";E2=ROOT/"e2_20261024"
L=E1/"E1_frozen_cells_765.csv";S=E1/"E1_method_budget_summary_153.csv";P=E2/"E2_combined_points_150.csv";R=E2/"E2_combined_spearman_30.csv";V=RT/"reports/E2_CORRELATIONS_INDEPENDENTLY_VERIFIED.csv";C=E2/"E2_all_class_reports_1596.csv";D=RT/"reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv";M=E2/"E2_missing_primary_42.csv"
def read(p):
 with open(p,newline="") as f:return list(csv.DictReader(f))
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def num(x):
 try:return float(x) if x not in ("",None) else np.nan
 except:return np.nan
def ir(x):
 try:return int(x) if x not in ("",None) else 0
 except:return 0
def rank(x):
 x=np.asarray(x,float);o=np.argsort(x,kind="stable");r=np.empty(len(x));i=0
 while i<len(x):
  j=i+1
  while j<len(x) and x[o[j]]==x[o[i]]:j+=1
  r[o[i:j]]=(i+j-1)/2;i=j
 return r
def rho(x,y):return float(np.corrcoef(rank(x),rank(y))[0,1])
def contrast_color(cmap,value,limits):
 rgb=np.asarray(plt.get_cmap(cmap)(np.clip((float(value)-limits[0])/(limits[1]-limits[0]),0,1))[:3],float)
 linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
 luminance=float(np.dot(linear,[.2126,.7152,.0722]))
 return "black" if luminance>=.179 else "white"
def render_e1(ledger,summary,path):
 bs=sorted({int(x["budget"]) for x in ledger});ms=sorted({x["method"] for x in ledger});mi={m:i for i,m in enumerate(ms)};bi={b:i for i,b in enumerate(bs)}
 st=np.zeros((len(ms),len(bs),4),int)
 clas={"successful_test_evaluation":0,"resource_failure":1,"supervisor_terminal_failure_without_cell_completion":2,"scientific_model_or_support_failure":3}
 for x in ledger:st[mi[x["method"]],bi[int(x["budget"])],clas[x["classification"]]]+=1
 sm={(int(x["budget"]),x["method"]):x for x in summary};ns=np.zeros(st.shape[:2],int)
 cols=[("balanced_accuracy_mean","balanced_accuracy_sample_sd","Balanced accuracy",(.25,.9),"viridis"),("coverage_mean","coverage_sample_sd","90% conformal coverage",(.5,1),"viridis"),("mean_set_size_mean","mean_set_size_sample_sd","Mean prediction-set size",(1,7),"magma")]
 mats=[];sds=[]
 for mean,sd,title,lim,cmap in cols:
  mats.append(np.full(st.shape[:2],np.nan));sds.append(np.full(st.shape[:2],np.nan))
 for m,i in mi.items():
  for b,j in bi.items():
   x=sm[b,m];ns[i,j]=ir(x["successful_repetitions"])
   if (st[i,j,0]!=ns[i,j] or st[i,j,1]+st[i,j,2]!=ir(x["failed_repetitions"]) or st[i,j,3]!=ir(x["unsupported_repetitions"])):raise ValueError(f"E1 summary mismatch {b}/{m}")
   for q,(mean,sd,_,_,_) in enumerate(cols):mats[q][i,j]=num(x[mean]);sds[q][i,j]=num(x[sd])
 fig,axs=plt.subplots(4,1,figsize=(19,17.5),gridspec_kw={"height_ratios":[1,1,1,1.12]},constrained_layout=True)
 for ax,(mean,sd,title,lim,cmap),mat,sdev in zip(axs[:3],cols,mats,sds):
  im=ax.imshow(mat,aspect="auto",cmap=cmap,vmin=lim[0],vmax=lim[1])
  ax.set_title(title+" - mean +/- sample SD; conditional on success",loc="left",fontsize=11,fontweight="bold")
  ax.set_xticks(range(len(bs)),[f"{b:,}" for b in bs],fontsize=8);ax.set_xlabel("Development budget (rows)");ax.set_yticks(range(len(ms)),ms,fontsize=8)
  for i in range(len(ms)):
   for j in range(len(bs)):
    v=mat[i,j];txt="--\nn=0" if not np.isfinite(v) else f"{v:.3f} +/- {sdev[i,j]:.3f}\nn={ns[i,j]}/5"
    ax.text(j,i,txt,ha="center",va="center",fontsize=6,color=contrast_color(cmap,v,lim) if np.isfinite(v) else "black")
  ax.set_xticks(np.arange(-.5,len(bs)),minor=True);ax.set_yticks(np.arange(-.5,len(ms)),minor=True);ax.grid(which="minor",color="white",lw=.4);ax.tick_params(which="minor",bottom=False,left=False);fig.colorbar(im,ax=ax,shrink=.74,pad=.008)
 axs[3].imshow(st[:,:,0],aspect="auto",cmap="Blues",vmin=0,vmax=5)
 axs[3].set_title("All 765 cells: successes / failures / unsupported out of five",loc="left",fontsize=11,fontweight="bold")
 axs[3].set_xticks(range(len(bs)),[f"{b:,}" for b in bs],fontsize=8);axs[3].set_xlabel("Development budget (rows)");axs[3].set_yticks(range(len(ms)),ms,fontsize=8)
 for i in range(len(ms)):
  for j in range(len(bs)):
   a,b,c,d=st[i,j];axs[3].text(j,i,f"S{a} F{b+c} U{d}",ha="center",va="center",fontsize=6,color=contrast_color("Blues",a,(0,5)))
 axs[3].set_xticks(np.arange(-.5,len(bs)),minor=True);axs[3].set_yticks(np.arange(-.5,len(ms)),minor=True);axs[3].grid(which="minor",color="white",lw=.4);axs[3].tick_params(which="minor",bottom=False,left=False)
 fig.suptitle("Frozen Experiment 1 - 765 planned cells across all budgets",fontsize=17,fontweight="bold")
 fig.text(.5,-.012,"Totals: 674 successful; 81 failed (55 resource; 26 supervisor-terminal, manifest still started); 10 unsupported. n=successful reps/5. Blanks are unavailable, never zero. Recovery excluded. Development budget split: 80% fit / 10% tune / 10% calibration.",ha="center",fontsize=9)
 fig.savefig(path,dpi=240,bbox_inches="tight",facecolor="white");plt.close(fig)
 return {"planned":len(ledger),"budgets":bs,"methods":ms,"counts":{"success":int(st[:,:,0].sum()),"resource_failure":int(st[:,:,1].sum()),"supervisor_terminal_started":int(st[:,:,2].sum()),"unsupported":int(st[:,:,3].sum())}}
def render_e2(points,cor,ver,classes,diffs,missing,path):
 bs=sorted({int(x["budget"]) for x in points});fam=["gmm","copula","arf","kde","chow_liu"];cell={(int(x["budget"]),int(x["repetition"]),x["method"]):x for x in points}
 if len(cell)!=150:raise ValueError("E2 must contain 150 unique primary cells")
 verify={(int(x["budget"]),int(x["repetition"])):x for x in ver};full=[x for x in cor if x["status"]=="full_five_family" and x["full_five_family_spearman"]!=""]
 if len(full)!=4:raise ValueError(f"Need four full five-family strata; got {len(full)}")
 for x in cor:
  k=(int(x["budget"]),int(x["repetition"]));v=verify[k]
  if (x["status"]=="full_five_family")!=(str(v["primary_complete_five"]).lower()=="true"):raise ValueError(f"E2 completeness mismatch {k}")
  if x["status"]=="full_five_family" and not np.isclose(num(x["full_five_family_spearman"]),num(v["recomputed_primary_rho"]),atol=1e-12,rtol=0):raise ValueError(f"E2 rho mismatch {k}")
 av=np.zeros((30,5),int);lab=[]
 for ib,b in enumerate(bs):
  for rep in range(1,6):
   row=ib*5+rep-1;lab.append(f"{b:,} R{rep}")
   for j,m in enumerate(fam):
    x=cell[b,rep,m]
    if x["paired_status"]=="paired" and np.isfinite(num(x["class_balanced_fidelity"])):av[row,j]=1 if x["provenance"] in ("E2_original_selected_fit","original_saved_frozen_E1_fit") else 2 if x["provenance"]=="E2_reconstructed_selected_fit" else 3
 paired=[x for x in points if x["paired_status"]=="paired" and np.isfinite(num(x["class_balanced_fidelity"]))]
 from collections import Counter
 prov=dict(sorted(Counter(x["provenance"] for x in paired).items()))
 fig=plt.figure(figsize=(18.5,14),constrained_layout=False);outer=fig.add_gridspec(1,2,width_ratios=[.85,1.55],left=.07,right=.99,top=.91,bottom=.23,wspace=.08)
 ax=fig.add_subplot(outer[0,0]);cmap=ListedColormap(["#efb4b4","#4c78a8","#59a14f","#b8b8b8"]);norm=BoundaryNorm([-.5,.5,1.5,2.5,3.5],cmap.N);ax.imshow(av,aspect="auto",cmap=cmap,norm=norm)
 ax.set_xticks(range(5),["GMM","Copula","ARF","KDE","Chow-Liu"],rotation=30,ha="right",fontsize=8);ax.set_yticks(range(30),lab,fontsize=7);ax.set_title("Primary availability (150 planned cells)",loc="left",fontsize=11,fontweight="bold");ax.set_ylabel("Budget and repetition")
 for i in range(30):
  for j in range(5):ax.text(j,i,{0:"x",1:"O",2:"R",3:"?"}[int(av[i,j])],ha="center",va="center",fontsize=8,color="white" if av[i,j] in (1,2) else "#333")
 for cut in (4.5,9.5,14.5,19.5,24.5):ax.axhline(cut,color="white",lw=1)
 fig.legend(handles=[Patch(color="#4c78a8",label="Original saved fit"),Patch(color="#59a14f",label="Reconstructed fit"),Patch(color="#efb4b4",label="Unavailable")],loc="lower center",bbox_to_anchor=(.5,.065),ncol=3,frameon=False,fontsize=8)
 right=outer[0,1].subgridspec(2,2,wspace=.25,hspace=.32);colors={"gmm":"#4c78a8","copula":"#f28e2b","arf":"#e15759","kde":"#76b7b2","chow_liu":"#59a14f"};sc=[]
 for q,x in enumerate(full):
  b=int(x["budget"]);rep=int(x["repetition"]);rv=num(x["full_five_family_spearman"]);a=fig.add_subplot(right[q//2,q%2]);xx=[];yy=[]
  for m in fam:
   p=cell[b,rep,m];vx=num(p["class_balanced_fidelity"]);vy=num(p["classification_balanced_accuracy"])
   if not np.isfinite(vx+vy):raise ValueError(f"Missing E2 point {b}/{rep}/{m}")
   xx.append(vx);yy.append(vy);a.scatter(vx,vy,s=48,color=colors[m],edgecolor="white",linewidth=.5);a.annotate(m.replace("_","-"),(vx,vy),xytext=(4,3),textcoords="offset points",fontsize=7)
  calc=rho(xx,yy)
  if not np.isclose(calc,rv,atol=1e-12,rtol=0):raise ValueError(f"Scatter rho mismatch {b}/{rep}")
  dx=max(max(xx)-min(xx),1e-6);dy=max(max(yy)-min(yy),1e-6);a.set_xlim(min(xx)-.08*dx,max(xx)+.23*dx);a.set_ylim(min(yy)-.12*dy,max(yy)+.18*dy)
  a.set_title(f"{b:,} rows - R{rep}; rho={rv:.1f}, n=5",fontsize=9,fontweight="bold");a.set_xlabel("Class-balanced fidelity",fontsize=8);a.set_ylabel("Direct balanced accuracy",fontsize=8);a.grid(alpha=.2);a.tick_params(labelsize=8)
  sc.append({"budget":b,"repetition":rep,"rho":rv,"n":5,"recomputed_rho":calc,"methods":fam})
 bad=sum(str(x.get("exact_float_match","")).lower()!="true" for x in diffs);low=sum("low_precision" in json.dumps(x).lower() for x in classes)
 fig.suptitle("Experiment 2 - incomplete primary grid; within-stratum results only",fontsize=16,fontweight="bold")
 fig.text(.5,.022,f"Primary 108/150 paired; 42 unavailable. Provenance: {prov}. Separate classical references 120/120. Four complete five-family strata, n=5 each, descriptive; no pooling/significance. Low-precision reports {low}/1,596 retained. Reconstruction score differences {bad}/185 disclosed.",ha="center",fontsize=9,wrap=True)
 fig.savefig(path,dpi=240,bbox_inches="tight",facecolor="white");plt.close(fig)
 return {"primary_planned":len(points),"primary_paired":len(paired),"primary_unavailable":len(missing),"paired_provenance":prov,"class_reports":len(classes),"low_precision_reports":low,"reconstruction_comparisons":len(diffs),"nonexact_reconstruction_scores":bad,"classical_references":120,"complete_strata":sc}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 inputs=[L,S,E1/"E1_WRAPUP.md",P,R,V,C,D,M,E2/"E2_CURRENT_REPORT.md",E2/"E2_RECONSTRUCTION_AMENDMENT.md",E2/"E2_INTEGRITY_AUDIT.json"]
 code=[p for p in (ROOT/"project/benchmark").rglob("*.py") if "__pycache__" not in p.parts]+list(E2.glob("*.py"))
 inv=[ROOT/"e1_wrapup_20261024/E1_learning_curves_all_budgets.html",ROOT/"project/learning_curves_through_300000.png",ROOT/"project/analysis_100_to_100000_20261023/deliverables/LAMOST_E1_Learning_Curves_100_to_100000.png",E2/"E2_combined_fidelity_vs_accuracy.html",E2/"E2_fidelity_vs_accuracy.html"]
 prot=sorted(set(x for x in inputs+code+inv if x.is_file()));before={str(x):sha(x) for x in prot}
 ledger=read(L);summary=read(S)
 if len(ledger)!=765 or len(summary)!=153:raise ValueError("Unexpected E1 row counts")
 e1=render_e1(ledger,summary,OUT/"E1_frozen_all_budget_summary.png")
 e2=render_e2(read(P),read(R),read(V),read(C),read(D),read(M),OUT/"E2_primary_availability_and_strata.png")
 after={str(x):sha(x) for x in prot};changed=[x for x in before if before[x]!=after[x]]
 if changed:raise RuntimeError(f"Protected source/input changed: {changed}")
 outs=[]
 for x in sorted(OUT.glob("*.png")):
  with Image.open(x) as im:w,h=im.size
  outs.append({"path":str(x),"sha256":sha(x),"bytes":x.stat().st_size,"width_px":w,"height_px":h})
 rep={"generated_utc":datetime.now(timezone.utc).isoformat(),"scope":"E1/E2 descriptive delivery figures from saved tables only","execution":"EC2 system Python; no models/fits/predictions/calibration; protected inputs and source hashes unchanged","renderer_path":str(Path(__file__).resolve()),"renderer_sha256":sha(Path(__file__).resolve()),"input_source_hashes_before":before,"input_source_hashes_after":after,"changed_input_or_source_hashes":changed,"existing_figure_inventory":[{"path":str(x),"sha256":sha(x),"bytes":x.stat().st_size} for x in inv if x.is_file()],"e1":e1,"e2":e2,"outputs":outs,"limitations":["E1 means/sample SDs conditional on success; all five planned repetitions per method-budget accounted for.","E2 primary remains 108/150; 42 unavailable. Classical reference set is separate 120/120.","Only four complete five-family strata, n=5 each, descriptive, unpooled, with no significance or bootstrap."]}
 out=RT/"reports/FROZEN_E1_E2_FIGURE_AUDIT.json";out.write_text(json.dumps(rep,indent=2,sort_keys=True))
 print(json.dumps({"generated_utc":rep["generated_utc"],"outputs":outs,"e1":e1,"e2":{k:v for k,v in e2.items() if k!="complete_strata"},"report":str(out)},indent=2))
if __name__=="__main__":main()
