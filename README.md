# AI-generated image detection: Assignment 3

This article continues Assignments 1 and 2 in the original Springer Nature single-column template. It reports a **480-image CPU pilot with training seeds 42, 43 and 44**. All three reported runs use the same AMD CPU type and the same image manifest. The matched 20,000-image study remains planned.

## Results and files

Original unseen mean F1 was 0.047 (sample SD 0.047) for ResNet-50 and 0.225 (SD 0.046) for a frozen CLIP encoder with a trained linear head. Mean unseen FPR was 0.017 and 0.242. The primary paired permutation p-value was 0.0261. CLIP exceeded the practical FPR target, and neither detector met all project success goals. These are preliminary results on 80 unseen test images, reused across training seeds.

The report includes six tables and two figures. Table 2 has mean/SD metrics and individual unseen confusion counts. Table 4 shows paired 95% intervals for every processing change. The figures show F1/FPR by condition and illustrative seed-42 confusion matrices with actual errors. Results occupies eight pages and about 2,000 words of prose.

The final PDF and Overleaf ZIP are in [`exports/`](exports/). Repository: [C0nflu3nc3/RMT](https://github.com/C0nflu3nc3/RMT). The repository is public. **The source ZIP also contains everything needed to reproduce Tables 2–5 from saved scores, without GitHub or dataset access**. The analysis commit is recorded in `SOURCE_REVISION.json` and Table 6.

## Reproduce Tables 2–5

Use Python 3.12 in a separate environment:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce_tables.py
```

This command copies the project to a temporary directory, recalculates the metrics, 1,000 paired bootstrap resamples, 9,999 paired permutations, validation-selected thresholds and LaTeX tables. It checks Tables 2–5 against the supplied tables byte for byte, prints each match and writes `pilot/reproduction_check.json`. It leaves the original predictions, figures and tables unchanged. No images, model weights, PyTorch, dataset service or GitHub connection are needed for this score-only check; package installation requires access to a package index unless the dependencies are already installed.

To regenerate the analysis in place:

```bash
python pilot/analyze_pilot.py
python pilot/write_tables.py
```

Use `--reuse-metrics` on `analyze_pilot.py` only when redrawing figures from existing statistical exports. Existing attributed example JPEGs support the illustrative figure without downloading the image sample.

## Evidence in the archive

| File | Contents |
| --- | --- |
| `pilot/manifest.csv` | All 480 IDs, source labels, mirror rows, dimensions, codecs and original-byte SHA256 hashes |
| `pilot/predictions.csv` | 2,880 model/condition/seed predictions on 160 distinct reserved images |
| `pilot/validation_predictions.csv` | Validation scores for independent per-run threshold decisions |
| `pilot/runs/seed42/`, `seed43/`, `seed44/` | Individual predictions, metadata and training histories |
| `pilot/run_metadata.json` | Combined configuration and original per-run hardware/timing records |
| `pilot/training_history.json` | Actual loss and validation F1 by epoch and seed |
| `pilot/evaluation/` | Metrics, paired differences, processing intervals, group rates and individual errors |
| `pilot/reproduction_check.json` | Successful table matches and table SHA256 hashes |
| `pilot/legacy_seed42_intel/` | Earlier Intel feasibility run, excluded from current aggregates |
| `SOURCE_SHA256SUMS.txt` | Hashes of the archived source and evidence files |

The same 80 image IDs are used in each test run. The earlier Intel seed-42 ResNet run had three seen and zero unseen false positives, compared with four and one in the reported AMD seed-42 run. The cause was not isolated. The archived Intel run is excluded from the reported aggregates.

Three seeds provide a sample SD across training runs; they do not triple the number of independent test images. Bootstrap intervals concern image sampling conditional on the fitted models. The original unseen comparison is primary; secondary p-values are unadjusted.

## Build the article

Upload the ZIP to Overleaf, select `main.tex` and pdfLaTeX. The archive includes `sn-jnl.cls`, the bibliography, all six tables and both vector figures. DOI and URL wrapping uses `xurl`. For a local build:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Repeat training

Install `requirements-pilot.txt` for training. With the provided manifest and original image cache, run sequentially:

```bash
python pilot/run_pilot.py --offline --seed 42
python pilot/run_pilot.py --offline --seed 43
python pilot/run_pilot.py --offline --seed 44
python pilot/aggregate_runs.py
python pilot/analyze_pilot.py
python pilot/write_tables.py
```

`--offline` skips dataset API calls and verifies every cached image against the manifest. The shared default cache is `pilot/cache/`; set `PILOT_WORK` to use another directory. Training still needs pretrained model weights, which may require downloading if absent. Without `--offline`, the script queries the original sampling frame and downloads image assets into the cache. Re-running training overwrites that seed's exports, so preserve the supplied evidence first. Dataset images and model weights are excluded from the ZIP.

The source is [TheKernel01/Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), observed revision `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69`, accessed 17 October 2026. The frame was the first 1,200 training and 600 validation metadata rows, followed by within-source selection with sampling seed 42. The row API can change. Compare the revision and all retrieved byte hashes with the supplied manifest before treating a new download as a reproduction. Figure captions attribute the two display examples; upstream data and original-image terms still apply. No new license is assigned here to third-party data, model weights or the journal class.

The current pilot has no native-size/JPEG-table or category matching and no perceptual duplicate audit. All retrieved assets were JPEG. BigGAN, GLIDE and Midjourney differ in native size. The pilot does not establish size-independent detection or performance on the official release. The ResNet budget is one epoch and the CLIP head budget is 40 epochs; this is not a tuned, compute-matched ranking.

`planned_config.json` records full-study targets. `code/audit_release.py` supports a later audit of extracted official archives. Nominal published Midjourney capacity makes the planned test count plausible before filtering; actual matched counts still require that audit.
