# Current manuscript

`manuscript.pdf` is the current paper for the completed 6 November 2026 full-mirror refit: 34,998 distinct images, six development generators and Midjourney held out from training and validation. Its experimental evidence is pinned to commit `f9624d9cce60113b8bd7fea98286068e78a99534`.

`manuscript.tex` is self-contained. All prose, five tables, two vector figures and 39 references are inline. Upload that one file to Overleaf or run `pdflatex manuscript.tex` twice. No separate images or bibliography files are required.

The tables use the current full-mirror exports. The inline vector figures plot the same exported means, conditional image-bootstrap intervals and seed-42 confusion counts as `experiments/full35k/figures/`.

Other analysis scripts and the `evaluation/` and `legacy_tables/` directories in this folder belong to the historical pilot. The current experiment's code and saved scores are under `experiments/full35k/`. Run `python reproduce_tables.py` at the repository root to reproduce that experiment's published numerical exports, tables and standalone figures.

The paper documents unequal fitting budgets, possible reuse of previously inspected pilot content, unmatched source characteristics and failure to meet the combined performance targets.
