"""Create the preliminary tables and vector figures from saved pilot predictions."""
import csv,importlib.util,json,os,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
WORK=Path(os.environ.get('PILOT_WORK', str(ROOT/'cache')))
spec=importlib.util.spec_from_file_location('report_results',PROJECT/'code/report_results.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
r.SEEDS=(42,)
if '--reuse-metrics' not in sys.argv:
    r.report(ROOT/'predictions.csv',ROOT/'evaluation',resamples=1000,permutations=9999)
read=lambda p:list(csv.DictReader(p.open()))
pred=read(ROOT/'predictions.csv');val=read(ROOT/'validation_predictions.csv')
manifest=read(ROOT/'manifest.csv');meta=json.loads((ROOT/'run_metadata.json').read_text())
groups,identity=r.load_predictions(ROOT/'predictions.csv')

def at_threshold(rows,threshold):
    return r.measures([int(x['label']) for x in rows],[float(float(x['score'])>=threshold) for x in rows])

sensitivity=[]
thresholds={}
for model in r.MODELS:
    vr=[x for x in val if x['model']==model]
    ranked=[(at_threshold(vr,t)['f1'],t) for t in np.round(np.arange(.05,1,.05),2)]
    best,t=max(ranked);thresholds[model]=float(t)
    for split in ['seen','unseen']:
        rows=[x for x in pred if x['model']==model and x['split']==split and x['condition']=='original']
        for setting,threshold in [('Fixed',.5),('Validation',t)]:
            m=at_threshold(rows,threshold)
            sensitivity.append(dict(model=model,split=split,setting=setting,threshold=float(threshold),
                                    f1=m['f1'],fpr=m['fpr'],accuracy=m['accuracy'],n=m['n']))
r.write_csv(ROOT/'evaluation/threshold_sensitivity.csv',sensitivity)
(ROOT/'validation_thresholds.json').write_text(json.dumps(thresholds,indent=2))

figdir=PROJECT/'figures';figdir.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(6.0,2.65))
labels=['Original','JPEG 65','112 px'];colors=['#17334D','#087F82'];rng=np.random.default_rng(42)
intervals={}
for j,metric in enumerate(['f1','fpr']):
    for mi,model in enumerate(r.MODELS):
        means=[];lo=[];hi=[]
        for condition in r.CONDITIONS:
            ids,y,strata,scores=r.aligned(groups,identity,'unseen',condition)
            f,fp=r.f1_fpr(y,scores[model]);mean=float((f if metric=='f1' else fp).mean())
            vals=[]
            for _ in range(1000):
                ix=r.draw_indices(strata,rng);f,fp=r.f1_fpr(y[ix],scores[model][:,ix]);vals.append(float((f if metric=='f1' else fp).mean()))
            low,high=r.interval(vals);intervals[f'{model}_{condition}_{metric}']=[mean,low,high]
            means.append(mean);lo.append(max(0,mean-low));hi.append(max(0,high-mean))
        x=np.arange(3)+(mi-.5)*.34
        axes[j].bar(x,means,width=.32,color=colors[mi],label='ResNet-50' if mi==0 else 'CLIP linear',yerr=[lo,hi],capsize=2)
    target=.80 if metric=='f1' else .10
    axes[j].axhline(target,color='#A54527',ls='--',lw=1,label=f'Full-study target {target:.2f}')
    axes[j].text(2.45,target+.025,f'Target {target:.2f}',ha='right',fontsize=7,color='#A54527',bbox=dict(facecolor='white',edgecolor='none',pad=.8))
    axes[j].set(xticks=np.arange(3),xticklabels=labels,ylim=(0,1.06),ylabel=('F1 score (0–1)' if metric=='f1' else 'False-positive rate (0–1)'),xlabel='Image condition')
    axes[j].text(.02,.98,chr(65+j),transform=axes[j].transAxes,va='top',fontweight='bold')
from matplotlib.patches import Patch
fig.legend([Patch(color=colors[0]),Patch(color=colors[1])],['ResNet-50','CLIP linear'],loc='upper center',ncol=2,frameon=False,bbox_to_anchor=(.5,1.04))
fig.tight_layout(rect=(0,0,1,.93));fig.savefig(figdir/'pilot_condition_comparison.pdf',bbox_inches='tight');plt.close(fig)
(ROOT/'evaluation/absolute_metric_intervals.json').write_text(json.dumps(intervals,indent=2))

fig,axes=plt.subplots(2,2,figsize=(6.0,5.0),gridspec_kw={'height_ratios':[1,1.4]})
for j,model in enumerate(r.MODELS):
    rows=[x for x in pred if x['model']==model and x['split']=='unseen' and x['condition']=='original']
    m=r.measures([int(x['label']) for x in rows],[float(x['score']) for x in rows])
    cm=np.array([[m['tn'],m['fp']],[m['fn'],m['tp']]])
    axes[0,j].imshow(cm,cmap='Blues',vmin=0,vmax=max(m['n']//2,1))
    for y in range(2):
        for x in range(2):axes[0,j].text(x,y,str(cm[y,x]),ha='center',va='center',color='white' if cm[y,x]>20 else 'black',fontsize=12)
    axes[0,j].set(xticks=[0,1],xticklabels=['Real','Generated'],yticks=[0,1],yticklabels=['Real','Generated'],xlabel='Predicted class',ylabel='Actual class',title='ResNet-50' if j==0 else 'CLIP linear')
    wrong=[x for x in rows if int(float(x['score'])>=.5)!=int(x['label'])]
    indicated=[x for x in wrong if x['label']==('1' if model=='resnet50' else '0')]
    if indicated:wrong=indicated
    if wrong:
        wrong.sort(key=lambda x:abs(float(x['score'])-.5),reverse=True)
        ex=wrong[0];record=next(x for x in manifest if x['image_id']==ex['image_id'])
        path=WORK/(ex['image_id']+'.bin')
        if not path.exists():path=figdir/f'{model}_error_example.jpg'
        with Image.open(path) as im:axes[1,j].imshow(im.convert('RGB'))
        error='FP' if ex['label']=='0' else 'FN'
        axes[1,j].set_title(f"{error}  score={float(ex['score']):.4f}\n{ex['image_id']}",fontsize=8)
        axes[1,j].axis('off')
        if path.suffix=='.bin':
            Image.open(path).convert('RGB').save(figdir/f'{model}_error_example.jpg',quality=95)
    else:
        axes[1,j].text(.5,.5,'No errors in this set',ha='center',va='center');axes[1,j].axis('off')
fig.tight_layout();fig.savefig(figdir/'pilot_errors.pdf',bbox_inches='tight');plt.close(fig)
print('Analysis complete. Main metrics:',flush=True)
for x in read(ROOT/'evaluation/per_run_metrics.csv'):
    if x['condition']=='original':print(x,flush=True)
print('Paired comparisons',read(ROOT/'evaluation/paired_model_differences.csv'),flush=True)
print('Sensitivity',sensitivity,flush=True)
