"""Rebuild the article's larger-test results from saved prediction scores."""
import csv
import hashlib
import importlib.util
import json
import os
import runpy
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
DATA=PROJECT/'expanded_test'
FIG=PROJECT/'figures'
OUT=ROOT/'evaluation'
OUT.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True)
read=lambda p:list(csv.DictReader(p.open()))
spec=importlib.util.spec_from_file_location('report_results',PROJECT/'code/report_results.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
original=read(PROJECT/'pilot/manifest.csv')
test=read(DATA/'manifest.csv')
assert len(test)==len({x['image_id'] for x in test})==len({x['sha256'] for x in test})==len({x['pixel_sha256'] for x in test})==1600
assert not {x['image_id'] for x in original}.intersection(x['image_id'] for x in test)
assert not {x['sha256'] for x in original}.intersection(x['sha256'] for x in test)
development=[x for x in original if x['split'] in ['train','validation']]
combined=development+test
fields=list(dict.fromkeys(k for row in combined for k in row))
with (ROOT/'manifest.csv').open('w',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(combined)
assert len(combined)==len({x['image_id'] for x in combined})==1920
r.report(DATA/'predictions.csv',OUT,resamples=1000,permutations=9999)
pred=read(DATA/'predictions.csv');val=read(PROJECT/'pilot/validation_predictions.csv')
groups,identity=r.load_predictions(DATA/'predictions.csv')
assert set(identity)=={x['image_id'] for x in test}

def at_threshold(rows,t):
    return r.measures([int(x['label']) for x in rows],[float(float(x['score'])>=t) for x in rows])

sens=[];thresholds={}
for model in r.MODELS:
    thresholds[model]={}
    for seed in r.SEEDS:
        values=[x for x in val if x['model']==model and int(x['seed'])==seed]
        _,threshold=max((at_threshold(values,t)['f1'],t) for t in np.round(np.arange(.05,1,.05),2))
        thresholds[model][str(seed)]=float(threshold)
        for split in ['seen','unseen']:
            rows=[x for x in pred if x['model']==model and int(x['seed'])==seed and x['split']==split and x['condition']=='original']
            for setting,t in [('Fixed',.5),('Validation',threshold)]:
                metrics=at_threshold(rows,t)
                sens.append(dict(model=model,seed=seed,split=split,setting=setting,threshold=float(t),
                                 f1=metrics['f1'],fpr=metrics['fpr'],accuracy=metrics['accuracy'],n=metrics['n']))
r.write_csv(OUT/'threshold_sensitivity.csv',sens)
(ROOT/'validation_thresholds.json').write_text(json.dumps(thresholds,indent=2)+'\n')
runpy.run_path(str(ROOT/'cohort_comparison.py'),run_name='__main__')

rng=np.random.default_rng(42);intervals={}
for split in ['seen','unseen']:
    for condition in r.CONDITIONS:
        ids,y,strata,scores=r.aligned(groups,identity,split,condition)
        for model in r.MODELS:
            values={'f1':[],'fpr':[]}
            for _ in range(1000):
                ix=r.draw_indices(strata,rng)
                f1,fpr=r.f1_fpr(y[ix],scores[model][:,ix])
                values['f1'].append(float(f1.mean()));values['fpr'].append(float(fpr.mean()))
            f1,fpr=r.f1_fpr(y,scores[model])
            for metric,point in [('f1',f1.mean()),('fpr',fpr.mean())]:
                intervals[f'{split}_{model}_{condition}_{metric}']=[float(point),*r.interval(values[metric])]
(OUT/'absolute_metric_intervals.json').write_text(json.dumps(intervals,indent=2)+'\n')
if os.environ.get("ARTICLE_SCORES_ONLY") == "1":
    print("Score exports complete; figures skipped.")
    raise SystemExit(0)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,
                     'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(6.0,2.65));colors=['#17334D','#087F82']
for j,metric in enumerate(['f1','fpr']):
    for mi,model in enumerate(r.MODELS):
        points=[intervals[f'unseen_{model}_{c}_{metric}'] for c in r.CONDITIONS]
        means=[x[0] for x in points]
        errors=[[max(0,x[0]-x[1]) for x in points],[max(0,x[2]-x[0]) for x in points]]
        axes[j].bar(np.arange(3)+(mi-.5)*.34,means,.32,color=colors[mi],yerr=errors,capsize=2,
                    label='ResNet-50' if mi==0 else 'CLIP linear')
    target=.80 if metric=='f1' else .10
    axes[j].axhline(target,color='#A54527',ls='--',lw=1)
    axes[j].text(2.45,target+.025,f'Target {target:.2f}',ha='right',fontsize=7,color='#A54527',
                 bbox=dict(facecolor='white',edgecolor='none',pad=.8))
    axes[j].set(xticks=np.arange(3),xticklabels=['Original','JPEG 65','112 px'],ylim=(0,1.06),
                ylabel='F1 score (0-1)' if metric=='f1' else 'False-positive rate (0-1)',xlabel='Image condition')
    axes[j].text(.02,.98,chr(65+j),transform=axes[j].transAxes,va='top',fontweight='bold')
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=2,frameon=False,bbox_to_anchor=(.5,1.04))
fig.tight_layout(rect=(0,0,1,.93));fig.savefig(FIG/'pilot_condition_comparison.pdf',bbox_inches='tight');plt.close(fig)

fig,axes=plt.subplots(2,2,figsize=(6.0,5.0),gridspec_kw={'height_ratios':[1,1.4]})
examples={};image_dir=Path(os.environ['ARTICLE_IMAGE_DIR']) if os.environ.get('ARTICLE_IMAGE_DIR') else None
existing=json.loads((ROOT/'error_examples.json').read_text()) if (ROOT/'error_examples.json').exists() else {}
for j,model in enumerate(r.MODELS):
    rows=[x for x in pred if x['model']==model and int(x['seed'])==42 and x['split']=='unseen' and x['condition']=='original']
    metrics=r.measures([int(x['label']) for x in rows],[float(x['score']) for x in rows])
    matrix=np.array([[metrics['tn'],metrics['fp']],[metrics['fn'],metrics['tp']]])
    axes[0,j].imshow(matrix,cmap='Blues',vmin=0,vmax=400)
    for y in range(2):
        for x in range(2):axes[0,j].text(x,y,str(matrix[y,x]),ha='center',va='center',color='white' if matrix[y,x]>200 else 'black',fontsize=12)
    axes[0,j].set(xticks=[0,1],xticklabels=['Real','Generated'],yticks=[0,1],yticklabels=['Real','Generated'],
                  xlabel='Predicted class',ylabel='Actual class',title='ResNet-50' if j==0 else 'CLIP linear')
    indicated=[x for x in rows if int(float(x['score'])>=.5)!=int(x['label']) and x['label']==('1' if model=='resnet50' else '0')]
    ex=max(indicated,key=lambda x:abs(float(x['score'])-.5))
    record=next(x for x in test if x['image_id']==ex['image_id'])
    cached=FIG/f'{model}_error_example.jpg'
    if image_dir:
        source=image_dir/(ex['image_id']+'.jpg')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
        shutil.copyfile(source,cached)
    elif not cached.exists() or existing.get(model,{}).get('image_id')!=ex['image_id']:
        raise FileNotFoundError('Set ARTICLE_IMAGE_DIR for the first error-example build')
    assert hashlib.sha256(cached.read_bytes()).hexdigest()==record['sha256']
    with Image.open(cached) as image:axes[1,j].imshow(image.convert('RGB'))
    error='FN' if ex['label']=='1' else 'FP'
    axes[1,j].set_title(f"{error}  score={float(ex['score']):.4f}\n{ex['image_id']}",fontsize=8)
    axes[1,j].axis('off')
    examples[model]=dict(image_id=ex['image_id'],error=error,score=float(ex['score']),sha256=record['sha256'])
(ROOT/'error_examples.json').write_text(json.dumps(examples,indent=2)+'\n')
fig.tight_layout();fig.savefig(FIG/'pilot_errors.pdf',bbox_inches='tight');plt.close(fig)
print('Article analysis complete: 1,920 study images, 1,600 distinct test images, 28,800 predictions.')
print('Validation thresholds:',thresholds)
print('New example IDs:',examples)
