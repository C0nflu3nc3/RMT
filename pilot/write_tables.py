"""Write the six article tables from saved three-seed pilot exports."""
import csv,json,statistics
from pathlib import Path
P=Path(__file__).resolve().parent
T=P.parent/'tables';T.mkdir(exist_ok=True)
read=lambda n:list(csv.DictReader((P/'evaluation'/n).open()))
fmt=lambda x:f'{(0.0 if abs(float(x))<0.0005 else float(x)):.3f}'
name=lambda m:'ResNet-50' if m=='resnet50' else 'CLIP linear'
cond={'original':'Original','jpeg65':'JPEG 65','resize112':'Resize 112'}
meta=json.loads((P/'run_metadata.json').read_text())
seeds=tuple(meta['training_seeds'])
def stack(a,b):return r'\shortstack{'+str(a)+r'\\{'+str(b)+'}}'
def mean_sd(values):
    values=[float(x) for x in values]
    return stack(fmt(statistics.mean(values)),'('+fmt(statistics.stdev(values))+')')
def tabular(cols,header,rows):
    return (r'\begin{tabularx}{\linewidth}{@{}'+cols+r'@{}}'+'\n'+r'\toprule'+'\n'+' & '.join(header)+r'\\'+'\n'+r'\midrule'+'\n'+'\n'.join(' & '.join(map(str,row))+r'\\' for row in rows)+'\n'+r'\bottomrule'+'\n'+r'\end{tabularx}'+'\n')
def table(file,caption,label,cols,header,rows,small=True,extra=''):
    text=r'\begin{table}[!htbp]'+'\n'+r'\caption{'+caption+'}\n'+r'\label{'+label+'}\n'+r'\centering'+'\n'
    text+=(r'\small' if small else r'\fontsize{8.5}{10.5}\selectfont')+'\n'
    text+=r'\setlength{\tabcolsep}{3.2pt}\renewcommand{\arraystretch}{1.10}'+'\n'
    text+=tabular(cols,header,rows)+extra+r'\end{table}'+'\n'
    (T/file).write_text(text)

table('dataset.tex','Preliminary sample actually used. Full-study targets are separate. The same 480 readable, exactly deduplicated images are reused for all three training seeds. Source: Tiny-GenImage mirror, accessed 17 October 2026.','tab:dataset','Yrrrr',
      ['Partition','Full target','Pilot $n$','Real','Generated'],
      [['Training','12,000',240,120,120],['Validation','2,000',80,40,40],['Seen test','2,000',80,40,40],['Unseen test','4,000',80,40,40],['Total','20,000',480,240,240]])
metrics=read('per_run_metrics.csv');main=[x for x in metrics if x['condition']=='original']
rows=[]
for split in ['seen','unseen']:
    for model in ['resnet50','clip_linear']:
        group=[x for x in main if x['split']==split and x['model']==model]
        rows.append([name(model),split.title()]+[mean_sd([x[k] for x in group]) for k in ['accuracy','precision','recall','f1','fpr','auroc','ap']])
counts=[[name(x['model']),x['seed']]+[x[k] for k in ['tp','fp','tn','fn']] for x in main if x['split']=='unseen']
extra=r'\medskip'+'\n'+tabular('Yrrrrr',['Unseen counts: model','Seed','TP','FP','TN','FN'],counts)
table('main_results.tex','Original-image metrics at threshold 0.5. Upper cells show mean with sample SD in parentheses over training seeds 42, 43 and 44; lower rows show unseen confusion counts for each run. Each test has 40 real and 40 generated images, reused across seeds. P and R are precision and recall; AUC is AUROC.','tab:main-results','ll'+'C'*7,
      ['Model','Test','Acc.','P','R','F1','FPR','AUC','AP'],rows,small=False,extra=extra)
paired=read('paired_model_differences.csv')
table('paired.tex','Paired differences in mean F1, CLIP minus ResNet, across three fixed training runs. Intervals use 1,000 paired image resamples; p-values use 9,999 paired permutations. Original unseen images are primary; other p-values are descriptive and unadjusted.','tab:paired','lYccc',
      ['Test','Condition','$\\Delta F_1$','95\\% CI','$p$'],
      [[x['split'].title(),cond[x['condition']],fmt(x['delta_f1']),f"[{fmt(x['ci_low'])}, {fmt(x['ci_high'])}]",f"{float(x['permutation_p']):.4f}"] for x in paired])
rob=read('robustness_changes.csv');rows=[]
for split in ['seen','unseen']:
    for model in ['resnet50','clip_linear']:
        row=[name(model),split.title()]
        for c in ['jpeg65','resize112']:
            x=next(x for x in rob if x['split']==split and x['model']==model and x['condition']==c)
            row.extend([stack(fmt(x['delta_f1']),f"[{fmt(x['f1_ci_low'])}, {fmt(x['f1_ci_high'])}]"),stack(fmt(x['fpr_increase']),f"[{fmt(x['fpr_ci_low'])}, {fmt(x['fpr_ci_high'])}]")])
        rows.append(row)
table('robustness.tex','Processing changes: mean across training seeds, with paired image-bootstrap 95\\% CI below each value. Both changes are processed minus original; negative $\\Delta F_1$ and positive $\\Delta\\mathrm{FPR}$ indicate deterioration. Each comparison uses the same 80 image IDs per test. Intervals condition on the three trained checkpoints.','tab:robustness','ll'+'C'*4,
      ['Model','Test','JPEG $\\Delta F_1$','JPEG $\\Delta$FPR','112 $\\Delta F_1$','112 $\\Delta$FPR'],rows,small=False)
sens=read('threshold_sensitivity.csv');rows=[]
for model in ['resnet50','clip_linear']:
    for split in ['seen','unseen']:
        for setting in ['Fixed','Validation']:
            group=sorted([x for x in sens if x['model']==model and x['split']==split and x['setting']==setting],key=lambda x:int(x['seed']))
            ts=', '.join(f"{float(x['threshold']):.2f}" for x in group)
            rows.append([name(model),split.title(),setting,ts,mean_sd([x['f1'] for x in group]),mean_sd([x['fpr'] for x in group])])
table('sensitivity.tex','Original-image threshold sensitivity. Thresholds are listed for seeds 42, 43 and 44, in that order. F1 and FPR show mean with sample SD in parentheses. Each validation threshold is selected independently using only validation predictions. Each run evaluates the same 80 images per test.','tab:sensitivity','llYccc',
      ['Model','Test','Rule','$t_{42},t_{43},t_{44}$','F1','FPR'],rows,small=False)
v=json.loads((P/'software_versions.json').read_text());runs=meta['per_seed']
mean_time=lambda field,model:statistics.mean([runs[str(s)][field][model] for s in seeds])
revision=json.loads((P.parent/'SOURCE_REVISION.json').read_text())['analysis_commit'][:12]
table('reproducibility.tex','Observed three-seed setup. Preparation/training times are averaged across runs; prediction medians show the observed range. CLIP preparation includes development feature extraction. All three reported runs reuse the hash-verified image cache on the same CPU type. Times are descriptive shared-host observations; no GPU was used.','tab:reproducibility','lY',
      ['Item','Observed setting'],
      [['Source and revision',r'\texttt{TheKernel01/Tiny-GenImage}, revision '+r'\texttt{'+meta['dataset_revision'][:12]+'}'],
       ['Device','AMD EPYC 9V74; six PyTorch threads; 8 GiB container'],
       ['Python and libraries',meta['python']+'; PyTorch '+v['torch']+'; torchvision '+v['torchvision']+'; CLIP '+v['openai-clip']],
       ['Analysis libraries','NumPy '+v['numpy']+'; Pillow '+v['Pillow']+'; scikit-learn '+v['scikit-learn']+'; SciPy '+v['scipy']],
       ['Seeds and optimizers','Sampling 42; training 42, 43, 44; Adam; learning rates '+r'$10^{-4}$ (ResNet), $10^{-3}$ (head)'],
       ['Epochs and batches','ResNet: 1 epoch, batch 8; CLIP head: 40 epochs, batch 32'],
       ['Preparation and training',f"ResNet {mean_time('training_including_preparation_seconds','resnet50'):.2f} s; CLIP {mean_time('training_including_preparation_seconds','clip_linear'):.2f} s"],
       ['Prediction median',"; ".join(("ResNet" if model=="resnet50" else "CLIP")+f" {min(runs[str(s)]['forward_median_ms_per_image'][model] for s in seeds):.2f} to {max(runs[str(s)]['forward_median_ms_per_image'][model] for s in seeds):.2f} ms/image" for model in ["resnet50","clip_linear"])],
       ['Pilot elapsed by seed','; '.join(f"{s}: {runs[str(s)]['total_seconds']:.2f} s" for s in seeds)],
       ['Repository',r'\url{https://github.com/C0nflu3nc3/RMT} (private); complete score-reproduction files in ZIP'],
       ['Analysis revision',r'\texttt{'+revision+'}; code, manifest, predictions and statistical exports']])
print('Six measured-result tables written')
