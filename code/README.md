# Evaluate paired predictions

The archive includes actual pilot predictions in `pilot/predictions.csv`. This evaluation script also supports the planned three-seed study.

Input CSV columns are `image_id,label,generator,split,condition,model,seed,score`. Labels are 0 (real) and 1 (generated). Use `real` for the real source; split is `seen` or `unseen`; condition is `original`, `jpeg65` or `resize112`; model is `resnet50` or `clip_linear`. Scores are continuous generated-class sigmoid outputs between 0 and 1. IDs must remain stable across models, seeds and conditions.

Run the one-seed pilot analysis directly:

```bash
python code/report_results.py pilot/predictions.csv --out pilot/evaluation --seeds 42
```

For the full comparison, omit `--seeds 42` to require seeds 42, 43 and 44. Each model and seed must cover identical IDs within a test condition. Seen and unseen IDs must be disjoint, and labels and source groups cannot change across conditions. An explicitly counted original/processed intersection is used for robustness comparisons. Incomplete paired model exports raise an error.

Outputs include confusion counts, seven metrics, mean and sample standard deviation across seeds, paired F1 differences and permutation p-values, paired processing changes, group rates and individual errors. A one-seed run leaves across-seed standard deviation undefined. It is not reported as zero.

Bootstrap intervals use 1,000 label-by-source stratified resamples. Paired permutations use 9,999 within-image exchanges of the complete score vectors across seeds. Both analyses retain the pairing. Original unseen F1 is the primary comparison; secondary p-values are unadjusted. The CSV practical flag checks that row's model gap and FPR. Overall project success additionally requires the article's cross-test FPR and transfer-drop criteria.

Robustness changes use **processed minus original** for both ΔF1 and ΔFPR. Lower F1 and higher FPR indicate deterioration. Source sizes are retained in the manifest; this pilot does not supply a completed size-matched or encoding-controlled comparison.

`audit_release.py` separately audits files from an extracted official GenImage archive. See its `--help`; it cannot infer retained counts after matching from published nominal capacities.
