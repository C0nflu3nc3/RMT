# ResNet-50 through epoch 40

The three runs start from the saved epoch-1 ResNet weights for seeds 42, 43 and 44. At epoch 2, the follow-up initializes a new Adam optimizer because the original weights contain no optimizer state. The follow-up uses the same audited image splits, preprocessing, batch size of 16 and learning rate of 0.0001. The comparison uses the final ResNet checkpoint at epoch 40 and the original validation-selected CLIP checkpoints.

- [Per-seed ResNet summary](metrics_epoch40.csv) and [training histories](histories/)
- [Paired results, absolute intervals and error counts](evaluation/)
- [Paper tables](tables/) and [figures](figures/)
- [Original continuation script](continue_resnet.py), used with the training bundle containing the manifest, epoch-1 weights and image cache

## Rebuild the tables and figures

From the repository root, install `requirements-analysis.txt`, then run:

```bash
python experiments/resnet40/reproduce.py
```

This rebuilds the tables and figures from the published aggregate results. To recompute the statistics from the original exports, add `--score-dir /path/to/followup`. The directory must contain `seed42`, `seed43` and `seed44`, each with its six `epoch40_*.csv` files. The script matches test IDs with the archived CLIP scores. The original ResNet epoch-40 scores are required for that step.

The follow-up uses a fixed threshold of 0.50. The separate validation-threshold experiment in `experiments/full35k` applies to the original checkpoints.
