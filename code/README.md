# Evaluate paired predictions

The archive includes actual pilot predictions in `pilot/predictions.csv`. The current pilot contains training seeds 42, 43 and 44 on one fixed image sample.

Input CSV columns are `image_id,label,generator,split,condition,model,seed,score`. Labels are 0 (real) and 1 (generated). Use `real` for the real source; split is `seen` or `unseen`; condition is `original`, `jpeg65` or `resize112`; model is `resnet50` or `clip_linear`. Scores are continuous generated-class sigmoid outputs between 0 and 1. IDs must remain stable across models, seeds and conditions.

Run the three-seed pilot analysis directly:

```bash
python code/report_results.py pilot/predictions.csv --out pilot/evaluation
```

To evaluate one individual run instead, use its `pilot/runs/seed42/predictions.csv` and add `--seeds 42`. Each model and seed must cover identical IDs within a test condition. Seen and unseen IDs must be disjoint, and labels and source groups cannot change across conditions. An explicitly counted original/processed intersection is used for robustness comparisons. Incomplete paired model exports raise an error.

Outputs include confusion counts, seven metrics, mean and sample standard deviation across seeds, paired F1 differences and permutation p-values, paired processing changes, group rates and individual errors. A one-seed run leaves across-seed standard deviation undefined. It is not reported as zero.

Bootstrap intervals use 1,000 label-by-source stratified resamples. Paired permutations use 9,999 within-image exchanges of the complete score vectors across seeds. Both analyses retain the pairing. Original unseen F1 is the primary comparison; secondary p-values are unadjusted. The CSV practical flag checks that row's model gap and FPR. Overall project success additionally requires the article's cross-test FPR and transfer-drop criteria.

Robustness changes use **processed minus original** for both ΔF1 and ΔFPR. Lower F1 and higher FPR indicate deterioration. Source sizes are retained in the manifest; this pilot does not supply a completed size-matched or encoding-controlled comparison.

`audit_release.py` separately audits files from an extracted official GenImage archive. See its `--help`; it cannot infer retained counts after matching from published nominal capacities.

For a complete score-only check of Tables 2–5, install `requirements-analysis.txt` and run `python reproduce_tables.py`. This works without GitHub, dataset downloads, model weights or PyTorch. The script compares regenerated LaTeX table bytes with the supplied tables.
