# RMT v2.0.0 — 6 November 2026

Completed the full Tiny-GenImage mirror refit after exact deduplication: 34,998 unique images, six fitted model variants and 198,000 saved test scores. Added the full protocol, train/validation/test manifests, validation scores, checkpoint digests, current metrics and uncertainty estimates, five LaTeX result tables, two PNG/PDF figures and an offline reproduction check.

This is a new split and refit, including previously studied mirror content. The unseen generator is Midjourney. Model fitting budgets remain unequal: one ResNet-50 epoch and 40 CLIP-head epochs. Both models miss the unseen-F1 target. Large weights, source images and feature caches remain separate from Git.

## Historical v1.0 notes

# RMT v1.0

Exploratory ResNet-50 and CLIP comparison with three training seeds, common test IDs, saved scores and paired uncertainty estimates.

This version adds an MIT code licence and citation metadata. It includes the existing 1,920-image study manifests, archived predictions and analysis scripts. No model training or numerical results have been changed. The later tests were selected after the initial pilot was inspected.

Run `python reproduce_tables.py` after installing `requirements-analysis.txt` to reproduce five table files and 11 numerical exports from saved scores. Source images and fitted checkpoints are not bundled. The source-image licence is separate from the code licence.

Before publishing the GitHub release, enable `C0nflu3nc3/RMT` in the Zenodo GitHub integration. After Zenodo archives tag `v1.0`, copy the actual version DOI into `CITATION.cff`, the README, and both availability statements in the paper. No DOI has been assigned to this prepared version yet.
