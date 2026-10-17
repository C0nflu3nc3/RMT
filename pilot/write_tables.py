"""Write LaTeX tables directly from measured pilot exports."""
import csv,json
from pathlib import Path
P=Path(__file__).resolve().parent
T=P.parent/'tables';T.mkdir(exist_ok=True)
read=lambda n:list(csv.DictReader((P/'evaluation'/n).open()))
fmt=lambda x:f'{float(x):.3f}'
name=lambda m:'ResNet-50' if m=='resnet50' else 'CLIP linear'
cond={'original':'Original','jpeg65':'JPEG 65','resize112':'Resize 112'}
meta=json.loads((P/'run_metadata.json').read_text())

def table(file,caption,label,cols,header,rows,small=True):
    text='\\begin{table}[!htbp]\n\\caption{'+caption+'}\n\\label{'+label+'}\n\\centering\n'
    text+=('\\small\n' if small else '\\fontsize{8.5}{10.5}\\selectfont\n')
    text+='\\setlength{\\tabcolsep}{3.5pt}\\renewcommand{\\arraystretch}{1.15}\n'
    text+='\\begin{tabularx}{\\linewidth}{@{}'+cols+'@{}}\n\\toprule\n'
    text+=' & '.join(header)+'\\\\\n\\midrule\n'
    text+='\n'.join(' & '.join(map(str,row))+'\\\\' for row in rows)
    text+='\n\\bottomrule\n\\end{tabularx}\n\\end{table}\n'
    (T/file).write_text(text)

table('dataset.tex','Preliminary sample actually used. Full-study targets are shown separately. All pilot rows were readable; no exact duplicate group was found among the 480 selected files. Source: Tiny-GenImage mirror, accessed 17 October 2026.','tab:dataset','Yrrrr',
      ['Partition','Full target','Pilot $n$','Real','Generated'],
      [['Training','12,000',240,120,120],['Validation','2,000',80,40,40],['Seen test','2,000',80,40,40],['Unseen test','4,000',80,40,40],['Total','20,000',480,240,240]])
metrics=read('per_run_metrics.csv')
main=[x for x in metrics if x['condition']=='original']
table('main_results.tex','Preliminary original-image metrics at threshold 0.5, seed 42. Each test contains 80 images, half generated. P and R are precision and recall; AUC is AUROC. Scores are on a 0--1 scale. There is one run per model, so no across-seed standard deviation is estimated.','tab:main-results','ll'+'C'*7,
      ['Model','Test','Acc.','P','R','F1','FPR','AUC','AP'],
      [[name(x['model']),x['split'].title()]+[fmt(x[k]) for k in ['accuracy','precision','recall','f1','fpr','auroc','ap']] for x in main],small=False)
paired=read('paired_model_differences.csv')
table('paired.tex','Preliminary paired F1 differences, CLIP minus ResNet. Intervals use 1,000 image resamples and p-values use 9,999 paired permutations. Original unseen images are the primary comparison; remaining p-values are descriptive and unadjusted.','tab:paired','lYccc',
      ['Test','Condition','$\\Delta F_1$','95\\% CI','$p$'],
      [[x['split'].title(),cond[x['condition']],fmt(x['delta_f1']),f"[{fmt(x['ci_low'])}, {fmt(x['ci_high'])}]",f"{float(x['permutation_p']):.4f}"] for x in paired])
rob=read('robustness_changes.csv')
table('robustness.tex','Preliminary robustness changes, processed minus original. Negative $\\Delta F_1$ and positive $\\Delta\\mathrm{FPR}$ indicate deterioration. All comparisons contain the same 80 image IDs per test. Full paired intervals are in the evaluation export; values use score units on a 0--1 scale.','tab:robustness','ll'+'C'*4,
      ['Model','Test','JPEG $\\Delta F_1$','JPEG $\\Delta$FPR','112 $\\Delta F_1$','112 $\\Delta$FPR'],
      [[name(m),s.title()]+[fmt(next(x for x in rob if x['model']==m and x['split']==s and x['condition']==c)[k]) for c in ['jpeg65','resize112'] for k in ['delta_f1','fpr_increase']] for s in ['seen','unseen'] for m in ['resnet50','clip_linear']])
sens=read('threshold_sensitivity.csv')
table('sensitivity.tex','Preliminary threshold sensitivity on original images. Validation-selected thresholds are frozen before test scoring; the selection rule is in Methods. Fixed-threshold rows reproduce the primary results. Each row evaluates 80 images.','tab:sensitivity','llYccc',
      ['Model','Test','Threshold rule','$t$','F1','FPR'],
      [[name(x['model']),x['split'].title(),x['setting'],f"{float(x['threshold']):.2f}",fmt(x['f1']),fmt(x['fpr'])] for x in sens])
v=json.loads((P/'software_versions.json').read_text())
table('reproducibility.tex','Observed preliminary-run setup. Training times include tensor preparation and, for CLIP, development feature extraction. Prediction times are warmed model-only medians for one image. No GPU was used.','tab:reproducibility','lY',
      ['Item','Observed setting'],
      [['Source and revision',r'\texttt{TheKernel01/Tiny-GenImage}, revision '+r'\texttt{'+meta['dataset_revision'][:12]+'}'],
       ['Device','Intel Xeon Platinum 8573C; six PyTorch threads; 8 GiB container'],
       ['Python and core libraries',meta['python']+'; PyTorch '+v['torch']+'; torchvision '+v['torchvision']],
       ['Other libraries','CLIP '+v['openai-clip']+'; NumPy '+v['numpy']+'; Pillow '+v['Pillow']+'; scikit-learn '+v['scikit-learn']+'; SciPy '+v['scipy']],
       ['Seed and optimizers','Global seed 42; Adam; learning rates '+r'$10^{-4}$ (ResNet), $10^{-3}$ (head)'],
       ['Epochs and batch sizes','ResNet: 1 epoch, batch 8; CLIP head: 40 epochs, batch 32'],
       ['Preparation and training',f"ResNet {meta['training_including_preparation_seconds']['resnet50']:.2f} s; CLIP {meta['training_including_preparation_seconds']['clip_linear']:.2f} s"],
       ['Prediction median',f"ResNet {meta['forward_median_ms_per_image']['resnet50']:.2f} ms/image; CLIP {meta['forward_median_ms_per_image']['clip_linear']:.2f} ms/image"],
       ['End-to-end pilot',f"{meta['total_seconds']:.2f} s including data access and model loading"],
       ['Repository',r'\url{https://github.com/C0nflu3nc3/RMT}; scripts, manifest, predictions, versions and training logs']])
print('Six measured-result tables written')
