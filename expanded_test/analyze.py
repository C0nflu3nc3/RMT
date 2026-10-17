"""Reproduce expanded-test metrics and visualizations from saved scores only."""
import csv
import importlib.util
import json
import hashlib
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('report_results', HERE.parent/'code/report_results.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
read = lambda path: list(csv.DictReader(path.open()))
original = read(HERE.parent/'pilot/manifest.csv')
manifest = read(HERE/'manifest.csv')
assert len({x['image_id'] for x in manifest}) == len(manifest)
assert len({x['sha256'] for x in manifest}) == len(manifest)
assert len({x['pixel_sha256'] for x in manifest}) == len(manifest)
assert not {x['image_id'] for x in original}.intersection(x['image_id'] for x in manifest)
assert not {x['sha256'] for x in original}.intersection(x['sha256'] for x in manifest)
if '--check' in sys.argv:
    checks = {}
    with tempfile.TemporaryDirectory(prefix='expanded-score-check-') as directory:
        out = Path(directory)
        r.report(HERE/'predictions.csv',out,resamples=1000,permutations=9999)
        for name in ['per_run_metrics.csv','main_metrics_all_conditions.csv',
                     'paired_model_differences.csv','robustness_changes.csv','source_group_errors.csv']:
            expected = (HERE/'evaluation'/name).read_bytes()
            actual = (out/name).read_bytes()
            if actual != expected:
                raise ValueError('Reproduction mismatch: '+name)
            checks[name] = {'status':'exact match','sha256':hashlib.sha256(actual).hexdigest()}
    (HERE/'reproduction_check.json').write_text(json.dumps(checks,indent=2)+'\n')
    print('All five expanded-test statistical exports reproduced exactly.')
    raise SystemExit(0)
r.report(HERE/'predictions.csv', HERE/'evaluation', resamples=1000, permutations=9999)
groups,identity = r.load_predictions(HERE/'predictions.csv')
assert set(identity) == {x['image_id'] for x in manifest}
intervals = {}
rng = np.random.default_rng(42)
for split in ['seen','unseen']:
    for condition in r.CONDITIONS:
        ids,y,strata,scores = r.aligned(groups,identity,split,condition)
        for model in r.MODELS:
            values = {'f1': [], 'fpr': []}
            for _ in range(1000):
                ix = r.draw_indices(strata,rng)
                f1,fpr = r.f1_fpr(y[ix],scores[model][:,ix])
                values['f1'].append(float(f1.mean()))
                values['fpr'].append(float(fpr.mean()))
            f1,fpr = r.f1_fpr(y,scores[model])
            for metric,point in [('f1',f1.mean()),('fpr',fpr.mean())]:
                intervals[f'{split}_{model}_{condition}_{metric}'] = [float(point),*r.interval(values[metric])]
(HERE/'evaluation/absolute_metric_intervals.json').write_text(json.dumps(intervals,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,
                     'axes.spines.top':False,'axes.spines.right':False})
fig,axes = plt.subplots(1,2,figsize=(7.0,2.65))
colors = ['#17334D','#087F82']
for j,metric in enumerate(['f1','fpr']):
    for mi,model in enumerate(r.MODELS):
        points = [intervals[f'unseen_{model}_{c}_{metric}'] for c in r.CONDITIONS]
        values = [x[0] for x in points]
        errors = [[max(0,x[0]-x[1]) for x in points],[max(0,x[2]-x[0]) for x in points]]
        axes[j].bar(np.arange(3)+(mi-.5)*.34,values,.32,color=colors[mi],yerr=errors,capsize=2,
                    label='ResNet-50' if mi==0 else 'CLIP linear')
    target = .80 if metric=='f1' else .10
    axes[j].axhline(target,color='#A54527',ls='--',lw=1)
    axes[j].text(2.40,target+.025,f'Target {target:.2f}',ha='right',fontsize=8,color='#A54527')
    axes[j].set(xticks=np.arange(3),xticklabels=['Original','JPEG 65','112 px'],ylim=(0,1.07),
                ylabel='F1 score (0-1)' if metric=='f1' else 'False-positive rate (0-1)',xlabel='Image condition')
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=2,frameon=False,bbox_to_anchor=(.5,1.04))
fig.tight_layout(rect=(0,0,1,.94))
fig.savefig(HERE/'unseen_conditions.png',dpi=180,bbox_inches='tight')
fig.savefig(HERE/'unseen_conditions.pdf',bbox_inches='tight')
plt.close(fig)
print('Expanded test analysis complete:',len(identity),'independent test images')
for row in read(HERE/'evaluation/main_metrics_all_conditions.csv'):
    if row['condition']=='original':
        print(row['split'],row['model'],'F1',row['f1_mean'],'FPR',row['fpr_mean'],'AUROC',row['auroc_mean'])
