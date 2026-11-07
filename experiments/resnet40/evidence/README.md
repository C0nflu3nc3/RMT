# Grouped evidence

These files support reproduction of the ResNet-50 epoch-40 and frozen-CLIP comparison. The exports group decisions and rank totals. They contain no image IDs, image files or per-image scores.

- `joint_decision_counts.csv` counts each pattern within a test split, processing condition, label and source. A pattern contains three ResNet decisions followed by three CLIP decisions, with seeds in the order 42, 43, 44. For a processed condition, the first six bits are the original decisions on the same images. The last six bits are the processed decisions. Each bit is 1 when the model score is at least 0.50. The public script resamples these counts and preserves the paired decisions.
- `auroc_rank_totals.csv` records twice the number of correctly ranked positive-negative pairs. A tie contributes one to this doubled count. Divide by twice the product of the class counts to reproduce AUROC. Average precision is retained in the archived score-based summaries.
- `unseen_threshold_counts.csv` contains positive calls and false alarms for each seed at seven cutoffs from 0.05 to 0.80 on original unseen images. It supports a descriptive sweep.

Source: [Tiny-GenImage revision 89c4fe9](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage/tree/89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69). The derived evaluation data use [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The repository licence covers code.
