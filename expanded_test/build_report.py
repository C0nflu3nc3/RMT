"""Make a one-page summary after collection and genuine checkpoint inference."""
import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

HERE=Path(__file__).resolve().parent
OUTPUT=HERE/'Expanded_Test_Samples_and_Results.pdf'
audit=json.loads((HERE/'sample_audit.json').read_text())
meta=json.loads((HERE/'inference_metadata.json').read_text())
read=lambda p:list(csv.DictReader(p.open()))
metrics=read(HERE/'evaluation/main_metrics_all_conditions.csv')
paired=next(x for x in read(HERE/'evaluation/paired_model_differences.csv')
            if x['split']=='unseen' and x['condition']=='original')
intervals=json.loads((HERE/'evaluation/absolute_metric_intervals.json').read_text())
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body',fontName='Helvetica',fontSize=9.2,leading=12,spaceAfter=7))
styles.add(ParagraphStyle(name='SmallNote',fontName='Helvetica',fontSize=8.1,leading=10.4,spaceAfter=6))
styles['Title'].fontName='Helvetica-Bold';styles['Title'].fontSize=19;styles['Title'].leading=23
styles['Title'].textColor=colors.HexColor('#17334D');styles['Title'].spaceAfter=8
styles['Heading2'].fontSize=11;styles['Heading2'].leading=14;styles['Heading2'].spaceBefore=10
P=lambda text:Paragraph(text,styles['Body'])
def make_table(rows,widths):
    table=Table(rows,colWidths=widths,hAlign='LEFT')
    table.setStyle(TableStyle([
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
        ('FONTSIZE',(0,0),(-1,-1),8.5),('LEADING',(0,0),(-1,-1),10.5),
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9F0F4')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#17334D')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),7),
        ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#B0C2CD')),
        ('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#B0C2CD')),
        ('ALIGN',(2,0),(-1,-1),'RIGHT')]))
    return table
count=audit['source_counts'];n=int(count['unseen/real'])
story=[Paragraph('Expanded held-out test sample',styles['Title']),
       P(f"Downloaded and audited <b>{audit['new_unique_images']:,} new images</b> from Tiny-GenImage. "
         f"Each new test contains {n} real and {n} generated images, compared with 40 + 40 in the original pilot. "
         "All original training, validation and test images were excluded."),
       make_table([['New test','Generated sources','Real','Generated','Total'],
                   ['Seen',f"BigGAN {count['seen/BigGAN']} + GLIDE {count['seen/GLIDE']}",n,n,2*n],
                   ['Unseen','Midjourney',n,n,2*n]],[65,205,65,85,90]),
       Spacer(1,8),
       P(f"File hashes and decoded RGB pixel hashes are unique across the new sample and disjoint from the "
         f"480-image pilot. One decision now changes a run's FPR by {1/n:.4f}, compared with 0.025 previously. "
         "The same six fitted checkpoints and the original threshold 0.5 were used; there was no retraining."),
       Paragraph('Measured results on the new original images',styles['Heading2'])]
table=[['Model','Test','F1 (SD)','FPR (SD)','AUROC (SD)']]
for split in ['seen','unseen']:
 for model in ['resnet50','clip_linear']:
  row=next(x for x in metrics if x['split']==split and x['model']==model and x['condition']=='original')
  table.append(['ResNet-50' if model=='resnet50' else 'CLIP linear',split.title(),
                *[f"{float(row[m+'_mean']):.3f} ({float(row[m+'_sd']):.3f})" for m in ['f1','fpr','auroc']]])
story += [make_table(table,[90,60,120,120,120]),Spacer(1,7),
          Image(str(HERE/'unseen_conditions.png'),width=510,height=510*2.65/7.0),
          Paragraph(f"Figure 1. New unseen test, n = {2*n}; means over seeds 42, 43 and 44. Error bars are "
                    "95% stratified image-bootstrap intervals conditional on the three checkpoint pairs. "
                    "JPEG 65 and 112 px are separate processing conditions.",styles['SmallNote']),
          P(f"On original unseen images, mean F1 differed by {float(paired['delta_f1']):.3f} "
            f"(CLIP minus ResNet; 95% CI [{float(paired['ci_low']):.3f}, {float(paired['ci_high']):.3f}]; "
            f"paired permutation p = {float(paired['permutation_p']):.4f}). "
            "This later test was collected after inspecting the first pilot. It increases the sample size; "
            "native-size, compression and category confounds remain unresolved."),
          P("The original pilot sampled the first 600 validation rows; this draw uses the full 7,000-row frame. "
            "Neither model reaches unseen F1 0.80, and CLIP's mean FPR of 0.255 exceeds the 0.10 target."),
          Paragraph('Source: <link href="https://huggingface.co/datasets/TheKernel01/Tiny-GenImage">TheKernel01/Tiny-GenImage, Hugging Face</link>; revision 89c4fe9efd0e. '
                    "The complete 7,000-row validation split was audited before random selection with seed 20261017. "
                    "The evidence ZIP contains the manifest, predictions, audit, scripts and full per-run statistics. "
                    "Dataset images retain the upstream CC BY-NC-SA 4.0 terms.",styles['SmallNote'])]
doc=SimpleDocTemplate(str(OUTPUT),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=34,bottomMargin=30,
                      title='Expanded held-out test sample',author='Afanasyev Kirill and Amangeldi Beksultan')
doc.build(story)
print(OUTPUT)
