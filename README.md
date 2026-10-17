# AI-generated image detection: Assignment 3

This article continues Assignments 1 and 2 in the original Springer Nature single-column template. It now reports a completed **480-image CPU pilot**, with saved predictions and measured results. The larger matched 20,000-image experiment remains planned.

## Main findings

At threshold 0.5, original unseen Midjourney F1 was 0.095 for ResNet-50 and 0.276 for the frozen CLIP encoder with a trained linear head. Their false-positive rates were 0.000 and 0.250. The primary paired permutation test gave p = 0.0662; neither detector met all project success criteria. After downsampling, both unseen FPRs reached 1.000. These findings concern one small, unmatched subset and one seed.

The article includes six populated tables and two measured figures: F1/FPR by processing condition, and actual confusion matrices with inspected failure images. The figures have labelled axes, score scales and captions. Threshold sensitivity compares 0.5 with thresholds selected from validation predictions.

The final PDF has 14 pages. Results occupies pages 5–12, with approximately 2,050 words of prose and eight figures/tables in total.

## Build the article

Upload the source ZIP to Overleaf, select `main.tex` and pdfLaTeX. The archive includes the original `sn-jnl.cls`. DOI and URL wrapping uses `xurl`. A local build is:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

`methods.tex` is the shortened Methods section. `results.tex` contains the preliminary Results. `tables/` and `figures/` hold the generated numeric tables and vector plots. `references.bib` retains the previous literature and adds the pilot mirror citation.

## Reproduce the saved analysis

Use Python 3.12 and install `requirements-pilot.txt` in a separate environment. This file records the actual pilot versions, including CPU PyTorch. Regenerate the paired statistics, sensitivity results, plots and LaTeX tables with:

```bash
python pilot/analyze_pilot.py
python pilot/write_tables.py
```

`--reuse-metrics` skips recalculating the 1,000 bootstrap resamples and 9,999 permutations when only redrawing figures. Existing error-example JPEGs let the saved figure be regenerated without downloading the image subset again. The score-based analyses use the original saved predictions, not those display JPEGs.

The main evidence files are:

| File | Contents |
| --- | --- |
| `pilot/manifest.csv` | All 480 IDs, source labels, mirror rows, dimensions, codecs and original-byte SHA256 hashes |
| `pilot/predictions.csv` | 960 model/condition predictions on 160 distinct reserved images |
| `pilot/validation_predictions.csv` | Validation scores used for checkpoint and threshold decisions |
| `pilot/training_history.json` | Loss and validation F1 by epoch |
| `pilot/run_metadata.json` | Actual hardware, timings, configuration and dataset revision |
| `pilot/software_versions.json` | Exact observed software versions |
| `pilot/evaluation/` | Per-run metrics, paired tests, robustness changes, group rates and individual errors |
| `SOURCE_SHA256SUMS.txt` | Hashes of the archived source and evidence files |

The paired statistics resample the same image IDs across both models. The primary comparison is original unseen F1. Other p-values are descriptive and unadjusted. The bootstrap interval and permutation test give different decisions on that primary comparison; both are reported, and the prespecified permutation test governs the statistical conclusion.

## Repeat training

```bash
python pilot/run_pilot.py
python pilot/analyze_pilot.py
python pilot/write_tables.py
```

Training downloads image assets and pretrained model weights. Its default cache is `pilot/cache/`; set `PILOT_WORK` to use another directory. Re-running training overwrites the pilot exports, so copy the supplied evidence first. Model checkpoints and the 480-image cache are excluded from this archive.

The image source is [TheKernel01/Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), observed revision `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69`, accessed 17 October 2026. The sampling frame was the first 1,200 training and 600 validation metadata rows, followed by within-source selection with seed 42. The public row API can change; verify its revision and compare all retrieved bytes with the supplied manifest hashes before treating a new run as a reproduction. The two display examples are attributed in the figure caption; consult the upstream dataset's license and original-image terms before redistributing images. This project does not assign a new license to third-party data, model weights or the journal class.

The CPU pilot uses BigGAN and GLIDE for development and Midjourney for the unseen test. It has no native-size/JPEG-table or category matching, no perceptual duplicate audit, and only one training seed. All downloaded assets were JPEG. Thus it cannot establish performance on the official GenImage release or prove that shortcut cues were removed. The reported training budgets are one ResNet epoch and 40 linear-head epochs, not a tuned compute-matched contest.

## Full study and repository

`planned_config.json` separates full-study targets from the completed pilot. `code/audit_release.py` can count and inspect extracted official archives; it was not run on those archives. The nominal published Midjourney test capacity supports feasibility of a 2,000-generated-image target before filtering, but the final matched counts remain conditional on an archive audit.

Repository: [C0nflu3nc3/RMT](https://github.com/C0nflu3nc3/RMT). It contains the article source, code and measured pilot exports. Dataset caches and model weights are excluded. Access follows the repository settings; reviewers need access to this private repository.
