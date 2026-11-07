# ResNet-50 through epoch 40

The three runs start from the saved epoch-1 ResNet weights for seeds 42, 43 and 44. At epoch 2, the follow-up initializes a new Adam optimizer because the original weights contain no optimizer state. The follow-up uses the same audited image splits, preprocessing, batch size of 16 and learning rate of 0.0001. The comparison uses the final ResNet checkpoint at epoch 40 and the original validation-selected CLIP checkpoints.

- [Per-seed ResNet summary](metrics_epoch40.csv) and [training histories](histories/)
- [Public reproduction evidence](evidence/) and [evaluation outputs](evaluation/)
- [Paper tables](tables/) and [figures](figures/)
- [Original continuation script](continue_resnet.py), used with the training bundle containing the manifest, epoch-1 weights and image cache

## Rebuild the tables and figures

From the repository root, install `requirements-analysis.txt`, then run:

```bash
python experiments/resnet40/reproduce.py
```

The script recomputes the fixed-threshold metrics, AUROC, paired intervals, permutation tests and the threshold sweep from the public evidence. It checks the submitted summary and rebuilds the tables and figures. Decision counts contain no image IDs or individual model scores.

Add `--score-dir /path/to/followup` to rebuild the grouped evidence from local exports. That directory must contain `seed42`, `seed43` and `seed44`, each with its six `epoch40_*.csv` files. The script matches those test IDs with the archived CLIP scores. Image-level exports are needed for this separate check.

The epoch-40 main comparison uses threshold 0.50. The test-set threshold sweep is descriptive and includes cutoffs of 0.05 and 0.10. The [threshold comparison table](tables/sensitivity.tex) separates ResNet epochs 1 and 40. Validation-selected cutoffs are available for the original checkpoints.

The Tiny-GenImage mirror declares [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The derived evaluation data in `evidence/` and `evaluation/` use those terms. The MIT licence covers the analysis code.
