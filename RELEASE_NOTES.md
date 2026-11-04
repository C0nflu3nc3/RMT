# RMT v1.0

Exploratory ResNet-50 and CLIP comparison with three training seeds, common test IDs, saved scores and paired uncertainty estimates.

This version adds an MIT code licence and citation metadata. It includes the existing 1,920-image study manifests, archived predictions and analysis scripts. No model training or numerical results have been changed. The later tests were selected after the initial pilot was inspected.

Run `python reproduce_tables.py` after installing `requirements-analysis.txt` to reproduce five table files and 11 numerical exports from saved scores. Source images and fitted checkpoints are not bundled. The source-image licence is separate from the code licence.

Before publishing the GitHub release, enable `C0nflu3nc3/RMT` in the Zenodo GitHub integration. After Zenodo archives tag `v1.0`, copy the actual version DOI into `CITATION.cff`, the README, and both availability statements in the paper. No DOI has been assigned to this prepared version yet.
