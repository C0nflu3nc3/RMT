"""Generate six main-paper tables for the 800-image tests."""
import csv,json,statistics
from pathlib import Path
P=Path(__file__).resolve().parent
PROJECT=P.parent
T=PROJECT/'tables';T.mkdir(exist_ok=True)
read=lambda n:list(csv.DictReader((P/'evaluation'/n).open()))
fmt=lambda x:f'{(0.0 if abs(float(x))<.0005 else float(x)):.3f}'
name=lambda m:'ResNet-50' if m=='resnet50' else 'CLIP linear'
cond={'original':'Original','jpeg65':'JPEG 65','resize112':'Resize 112'}
def stack(a,b):return r'\shortstack{'+str(a)+r'\\{'+str(b)+'}}'
def mean_sd(values):
 v=[float(x) for x in values];return stack(fmt(statistics.mean(v)),'('+fmt(statistics.stdev(v))+')')
def table(file,caption,label,cols,header,rows,small=True,first_panel=None):
 text=r'\begin{table}[!htbp]'+'\n'+r'\caption{'+caption+'}\n'+r'\label{'+label+'}\n'+r'\centering'+'\n'
 text+=(r'\small' if small else r'\fontsize{8.5}{10.5}\selectfont')+'\n'
 text+=r'\setlength{\tabcolsep}{3.2pt}\renewcommand{\arraystretch}{1.10}'+'\n'
 text+=r'\begin{tabularx}{\linewidth}{@{}'+cols+r'@{}}'+'\n'+r'\toprule'+'\n'+' & '.join(header)+r'\\'+'\n'+r'\midrule'+'\n'
 if first_panel:
  marker=r'\toprule'+'\n'
  heading=r'\multicolumn{'+str(len(header))+r'}{l}{\textbf{'+first_panel+r'}}\\'+'\n'
  text=text.replace(marker,marker+heading,1)
 text+='\n'.join(' & '.join(map(str,row))+r'\\' for row in rows)+'\n'+r'\bottomrule'+'\n'+r'\end{tabularx}'+'\n'+r'\end{table}'+'\n'
 (T/file).write_text(text)
def append_panel(file,title,cols,header,rows,header_latex=None):
 text=r'\par\medskip\small\noindent\textbf{'+title+r'}\par\smallskip'+'\n'
 text+=r'\begin{tabularx}{\linewidth}{@{}'+cols+r'@{}}'+'\n'+r'\toprule'+'\n'
 text+=(header_latex if header_latex else ' & '.join(header)+r'\\')+'\n'+r'\midrule'+'\n'
 text+='\n'.join(' & '.join(map(str,row))+r'\\' for row in rows)+'\n'+r'\bottomrule'+'\n'+r'\end{tabularx}'+'\n'
 path=T/file;source=path.read_text()
 path.write_text(source.replace(r'\end{table}',text+r'\end{table}'))
table('dataset.tex','Panel A compares full-study targets with the images used for training and later testing, excluding the initial 160 test images. Panel B gives mean F1 and FPR for the initial and later tests over seeds 42, 43 and 44 at threshold 0.5. Each initial test contains 40 real and 40 generated images; each later test contains 400 of each. The cohorts are disjoint and use different sampling frames.','tab:dataset','Yrrrr',
 ['Partition','Full target','Observed $n$','Real','Generated'],
 [['Training','12,000',240,120,120],['Validation','2,000',80,40,40],['Later seen test','2,000',800,400,400],['Later unseen test','4,000',800,400,400],['Total','20,000','1,920',960,960]],first_panel='A. Full-study targets and observed counts')
cohorts=read('cohort_comparison.csv');comparison=[]
for split in ['seen','unseen']:
 for model in ['resnet50','clip_linear']:
  row=[name(model),split.title()]
  for cohort in ['initial','later']:
   x=next(x for x in cohorts if x['cohort']==cohort and x['split']==split and x['model']==model)
   row.extend([fmt(x['f1_mean']),fmt(x['fpr_mean'])])
  comparison.append(row)
append_panel('dataset.tex','B. Initial and later tests: original-image scores','llCCCC',
 ['Model','Test','Initial F1','Initial FPR','Later F1','Later FPR'],comparison)
metrics=read('per_run_metrics.csv');main=[x for x in metrics if x['condition']=='original'];rows=[]
for split in ['seen','unseen']:
 for model in ['resnet50','clip_linear']:
  group=[x for x in main if x['split']==split and x['model']==model]
  rows.append([name(model),split.title()]+[mean_sd([x[k] for x in group]) for k in ['accuracy','precision','recall','f1','fpr','auroc','ap']])
table('main_results.tex','Results on later original images at threshold 0.5. Panel A gives means and sample SDs (in parentheses) across seeds 42, 43 and 44. P denotes precision, R recall and AUC AUROC. Panel B gives unseen confusion counts per seed, with generated images as positive. Each test contains 400 real and 400 generated images; the same images are reused across seeds.','tab:main-results','ll'+'C'*7,
 ['Model','Test','Acc.','P','R','F1','FPR','AUC','AP'],rows,small=False,first_panel='A. Mean metrics and variation across training seeds')
counts=read('unseen_confusion_counts.csv');count_rows=[]
for seed in [42,43,44]:
 row=[seed]
 for model in ['resnet50','clip_linear']:
  x=next(x for x in counts if int(x['seed'])==seed and x['model']==model)
  row.extend(int(x[k]) for k in ['tp','fp','tn','fn'])
 count_rows.append(row)
append_panel('main_results.tex','B. Later unseen test: individual confusion counts','CCCCCCCCC',[],count_rows,
 header_latex=r'Seed & \multicolumn{4}{c}{ResNet-50} & \multicolumn{4}{c}{CLIP linear}\\'+
 '\n'+r' & TP & FP & TN & FN & TP & FP & TN & FN\\')
paired=read('paired_model_differences.csv')
table('paired.tex','Mean F1 differences (CLIP minus ResNet), with paired 95\\% intervals. The original-unseen test is the main exploratory comparison; secondary p-values are unadjusted.','tab:paired','lYccc',
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
table('robustness.tex','Changes from original to processed images, averaged across seeds. Paired image-bootstrap 95\\% intervals appear below the estimates. Negative $\\Delta F_1$ and positive $\\Delta\\mathrm{FPR}$ indicate deterioration. Each comparison uses the same 800 IDs per test and conditions on the three fitted checkpoint pairs.','tab:robustness','ll'+'C'*4,
 ['Model','Test','JPEG $\\Delta F_1$','JPEG $\\Delta$FPR','112 $\\Delta F_1$','112 $\\Delta$FPR'],rows,small=False)
sens=read('threshold_sensitivity.csv');rows=[]
for model in ['resnet50','clip_linear']:
 for split in ['seen','unseen']:
  for setting in ['Fixed','Validation']:
   group=sorted([x for x in sens if x['model']==model and x['split']==split and x['setting']==setting],key=lambda x:int(x['seed']))
   ts=', '.join(f"{float(x['threshold']):.2f}" for x in group)
   stats=[fmt(z) for k in ['f1','fpr'] for z in (statistics.mean(float(x[k]) for x in group),statistics.stdev(float(x[k]) for x in group))]
   rows.append([name(model),split.title(),setting,ts]+stats)
table('sensitivity.tex','Threshold comparison on the later original images. Thresholds are listed for seeds 42, 43 and 44 in that order, with separate columns for means and sample SDs. Validation thresholds were chosen on the original 80-image validation set and kept for the later tests.','tab:sensitivity','llYccccc',
 ['Model','Test','Rule','$t_{42},t_{43},t_{44}$','F1','SD','FPR','SD'],rows,small=False)
meta=json.loads((PROJECT/'pilot/run_metadata.json').read_text());v=json.loads((PROJECT/'pilot/software_versions.json').read_text());new=json.loads((PROJECT/'expanded_test/inference_metadata.json').read_text());runs=meta['per_seed']
training=lambda m:statistics.mean(runs[str(s)]['training_including_preparation_seconds'][m] for s in [42,43,44])
revision=json.loads((PROJECT/'SOURCE_REVISION.json').read_text())['evidence_commit'][:12]
table('reproducibility.tex','Hardware and software for the completed experiment. Training and later inference used the same CPU type, without a GPU. Training times are means over the three initial runs; inference covers all seeds and conditions. Timings on the shared host are descriptive.','tab:reproducibility','lY',
 ['Item','Observed setting'],
 [['Source and revision',r'\texttt{TheKernel01/Tiny-GenImage}; '+r'\texttt{89c4fe9efd0e}'],
 ['Device','AMD EPYC 9V74; six PyTorch threads; 8 GiB container'],
 ['Software',meta['python']+'; PyTorch '+v['torch']+'; torchvision '+v['torchvision']+'; CLIP '+v['openai-clip']],
 ['Analysis','NumPy '+v['numpy']+'; scikit-learn '+v['scikit-learn']+'; SciPy '+v['scipy']],
 ['Sampling / training seeds','Initial 42; later test 20261017 / training 42, 43, 44'],
 ['Training','Adam; ResNet 1 epoch, batch 8, '+r'$10^{-4}$; CLIP head 40 epochs, batch 32, $10^{-3}$'],
 ['Preparation and training',f"ResNet {training('resnet50'):.2f} s; CLIP {training('clip_linear'):.2f} s"],
 ['Later test inference',f"ResNet {new['resnet50_evaluation_seconds']:.2f} s; CLIP {new['clip_linear_evaluation_seconds']:.2f} s; batch 8"],
 ['Prediction evidence',f"{new['prediction_rows']:,} rows; 1,600 distinct new test images"],
 ['Repository',r'\url{https://github.com/C0nflu3nc3/RMT} (public evidence); current article source in ZIP'],
 ['Numerical exports',r'ZIP, \path{article/evaluation/}: \nolinkurl{absolute_metric_intervals.json}, \nolinkurl{per_run_metrics.csv}, \nolinkurl{source_group_errors.csv}, \nolinkurl{processing_transitions.csv}, \nolinkurl{prose_details.json}'],
 ['Reproduction',r'ZIP: \texttt{python reproduce\_tables.py}; Tables 1 to 5 and 11 numerical exports'],
 ['Test-evidence revision',r'\texttt{'+revision+'}; checkpoint hashes, manifests, scores and statistical exports']])
print('Six article tables written, including both cohorts and all unseen counts.')
