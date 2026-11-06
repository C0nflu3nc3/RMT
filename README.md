# AI-generated image detection

Afanasyev Kirill and Amangeldi Beksultan · AITU, BDA-2403.

The completed 6 November 2026 experiment refits ResNet-50 and a linear classifier on frozen CLIP ViT-B/32 features using the entire Tiny-GenImage mirror. Two exact duplicates were removed, leaving **34,998 images**. Each model has three fitted variants, seeds 42, 43 and 44.

| Partition | Real | Generated | Total |
|---|---:|---:|---:|
| Training | 9,998 | 10,000 | 19,998 |
| Validation | 2,000 | 2,000 | 4,000 |
| Seen test | 3,000 | 3,000 | 6,000 |
| Unseen test | 2,500 | 2,500 | 5,000 |

Midjourney is absent from training and validation. Development generators are ADM, BigGAN, GLIDE, SD15, VQDM and Wukong. Splits have disjoint IDs and exact file/pixel hashes. Previous pilot content can be included in this new full-mirror split.

## Completed results

Original images, decision threshold 0.5; values are means over three fitted variants.

| Model | Seen F1 | Unseen F1 | Seen FPR | Unseen FPR |
|---|---:|---:|---:|---:|
| ResNet-50 | 0.910 | 0.310 | 0.098 | 0.096 |
| Frozen CLIP + linear head | 0.949 | 0.746 | 0.059 | 0.061 |

Neither model reached the unseen-F1 target of 0.80. CLIP's unseen F1 is 0.687 after JPEG quality-65 recompression and 0.733 after downsampling to 112×112. Downsampling also raises its unseen FPR to about 0.56; ResNet's FPR approaches 0.97. F1 alone therefore does not establish processing robustness.

![Unseen-generator F1 and false-positive rates](experiments/full35k/figures/unseen_robustness.png)

![Unseen confusion matrices, seed 42](experiments/full35k/figures/unseen_confusion_seed42.png)

## Reproduce without training

Use Python 3.12:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce_tables.py
```

This regenerates metrics and uncertainty estimates from the saved scores in an isolated temporary project, then compares numerical exports, five LaTeX result tables and both PNG/PDF figures. No images, fitted weights, GPU or network are needed for the check.

The **198,000 prediction rows** evaluate the same **11,000 test images** across two models, three seeds and three processing conditions. Validation predictions contain a further 24,000 scores over 4,000 validation images. These score counts are not counts of unique images.

## Manuscript

The [updated paper (PDF)](article/manuscript.pdf) reports the completed 34,998-image experiment. The [self-contained LaTeX source](article/manuscript.tex) includes all text, five tables, two figures and 39 references; compile it twice with pdfLaTeX, including in Overleaf. The manuscript uses evidence snapshot `f9624d9cce60` and replaces the earlier 1,920-image paper as the current report.

## Files

| Path | Contents |
|---|---|
| `experiments/full35k/` | Completed protocol, manifest, audit, training/evaluation code and saved scores |
| `experiments/full35k/evaluation/` | Metrics, confusion counts, bootstrap intervals, paired comparisons, threshold sensitivity and success checks |
| `experiments/full35k/figures/` | Current publication figures in PNG and PDF |
| `tables/` | Current five LaTeX result tables |
| `experiments/full35k/checkpoints.json` | Selected epochs and SHA256 digests of all six fitted checkpoints |
| `article/manuscript.tex`, `article/manuscript.pdf` | Current full-mirror paper, source and compiled PDF |
| `pilot/`, `expanded_test/`, `article/evaluation/`, `visualizations/` | Historical pilot data, analysis and visuals; these are not the current 35k results |

Training used a CPU. ResNet-50 was fine-tuned for one epoch; the CLIP encoder was frozen and its linear head trained for 40 epochs. The highest validation F1 selected each checkpoint, with the earliest epoch winning ties. The two architectures had unequal fitting budgets. Encoders used CPU bfloat16 autocast, with float32 parameters, optimizer state, CLIP-head training and stored features/scores. Separate metadata files record parallel preprocessing and fitting stages.

To repeat training from source, install `experiments/full35k/requirements.txt`, run `collect.py`, then `train.py` in that directory. These commands download pinned source data and pretrained weights and perform a new fit. `train_cuda.py --require-cuda --workers 0` is a Windows-compatible CUDA entry point; the CUDA path has not been executed in this CPU environment. Install CUDA-enabled torch/torchvision separately, then `requirements_cuda_extra.txt`.

Source photographs, image caches, CLIP feature caches and large fitted weights are kept outside Git. The fitted weights and feature caches were delivered separately; `checkpoints.json` identifies the selected weights. Exact metric reproduction from the committed scores does not require them.

## Scope and citation

The source is the [Tiny-GenImage mirror](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage) pinned at `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69`. Native size, content category and previous compression were audited but not matched. Image-bootstrap intervals condition on the fitted checkpoints. Exact deduplication does not establish absence of perceptual near-duplicates. This is a new full-mirror split and refit, not an independent cohort excluding previously inspected pilot content.

The code uses the [MIT licence](LICENSE). Dataset and pretrained-model licences remain separate. [CITATION.cff](CITATION.cff) records the authors and this version. No DOI has been assigned. The previous 1,920-image study remains in the Git history, including commit `02ca9ae7cc01aae8dae1040964a0e75c32a48010`.
