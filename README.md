# AI-generated image detection

Afanasyev Kirill and Amangeldi Beksultan · AITU, BDA-2403.

[Current paper (PDF)](article/manuscript.pdf) · [LaTeX source](article/manuscript.tex)

The completed 6 November 2026 experiment refits ResNet-50 and a linear classifier on frozen CLIP ViT-B/32 features. Exact deduplication of the entire Tiny-GenImage mirror leaves **34,998 images**.

| Partition | Real | Generated | Total |
|---|---:|---:|---:|
| Training | 9,998 | 10,000 | 19,998 |
| Validation | 2,000 | 2,000 | 4,000 |
| Seen test | 3,000 | 3,000 | 6,000 |
| Unseen test | 2,500 | 2,500 | 5,000 |

Midjourney is excluded from training and validation. Development uses ADM, BigGAN, GLIDE, SD15, VQDM and Wukong. Both models use seeds 42, 43 and 44.

| Model | Seen F1 | Unseen F1 | Seen FPR | Unseen FPR |
|---|---:|---:|---:|---:|
| ResNet-50 | 0.910 | 0.310 | 0.098 | 0.096 |
| Frozen CLIP + linear head | 0.949 | 0.746 | 0.059 | 0.061 |

Values are means across three fitted variants at threshold 0.5. Neither model meets the unseen-F1 target of 0.80. Downsampling increases unseen FPR to 0.971 for ResNet and 0.561 for CLIP.

![Unseen F1 and false-positive rates](experiments/full35k/figures/unseen_robustness.png)

![Unseen confusion matrices, seed 42](experiments/full35k/figures/unseen_confusion_seed42.png)

## Reproduce

On Python 3.12:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce_tables.py
```

The score-based check rebuilds numerical exports, five tables and both PNG/PDF figure pairs without images, weights or a GPU. To refresh only the presentation from archived numerical exports:

```bash
python experiments/full35k/publish_results.py --render-only
```

Current table and figure rendering was repeated in separate directories and matched byte for byte. The earlier complete score-based numerical check is retained in `experiments/full35k/reproduction_check.json`.

## Files and paper source

| Path | Contents |
|---|---|
| `article/manuscript.pdf`, `article/manuscript.tex` | Current paper and one LaTeX source containing all prose, tables and references |
| `tables/` | Five current LaTeX tables, including F1/FPR confidence intervals |
| `experiments/full35k/figures/` | The exact two figures used by the paper, in PDF and PNG |
| `experiments/full35k/evaluation/` | Metrics, intervals, error counts, paired comparisons and threshold checks |
| `experiments/full35k/` | Protocol, manifest, saved scores, model histories and training/evaluation code |
| `pilot/`, `expanded_test/`, `article/evaluation/` | Historical pilot evidence, separate from the current results |

Compile `manuscript.tex` twice with pdfLaTeX from `article/`. Its two figure PDFs are resolved from `experiments/full35k/figures/`. For Overleaf, upload the source and the two PDFs in a `figures/` folder. The source tables match `tables/` exactly.

## Training and scope

Install `experiments/full35k/requirements.txt`, then run `collect.py` and `train.py` there. These download pinned source data and pretrained weights. Training used a CPU: one ResNet epoch and 40 CLIP-head epochs, with the highest validation F1 selecting each checkpoint. Encoder computation used bfloat16 autocast; parameters, Adam state, CLIP-head fitting and stored features/scores used float32. CUDA support is in `train_cuda.py`; it was not used for the reported results.

The source is [Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), revision `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69`. The new split can include previously inspected pilot content. Native size, categories and prior compression remain unmatched; intervals condition on fitted checkpoints. The 198,000 test scores are repeated evaluations of 11,000 test images. Source images, feature caches and large fitted weights stay outside Git; `checkpoints.json` records the selected weight digests.

Code: [MIT licence](LICENSE). Dataset and pretrained-model licences are separate. Authors and version are in [CITATION.cff](CITATION.cff).
