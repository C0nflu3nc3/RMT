"""Report real study predictions; this script does not train models or invent data.

CSV columns: image_id,label,generator,split,condition,model,seed,score
See README.md for the accepted values and scope of the confidence intervals.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np
import sklearn
from sklearn.metrics import average_precision_score, roc_auc_score

MODELS = ("resnet50", "clip_linear")
SEEDS = (42, 43, 44)
CONDITIONS = ("original", "jpeg65", "resize112")
METRICS = ("accuracy", "precision", "recall", "f1", "fpr", "auroc", "ap")


def measures(labels, scores):
    y = np.asarray(labels, dtype=int)
    pred = np.asarray(scores) >= 0.5
    tp = int(np.sum((y == 1) & pred))
    tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred))
    fn = int(np.sum((y == 1) & ~pred))
    ratio = lambda a, b: a / b if b else 0.0
    return dict(n=len(y), tp=tp, tn=tn, fp=fp, fn=fn,
                accuracy=ratio(tp + tn, len(y)), precision=ratio(tp, tp + fp),
                recall=ratio(tp, tp + fn), f1=ratio(2 * tp, 2 * tp + fp + fn),
                fpr=ratio(fp, fp + tn),
                auroc=float(roc_auc_score(y, scores)),
                ap=float(average_precision_score(y, scores)))


def f1_fpr(labels, score_matrix):
    """One metric per trained seed; columns correspond to the same images."""
    pred = score_matrix >= 0.5
    real, generated = labels == 0, labels == 1
    tp = np.sum(pred & generated, axis=1)
    fp = np.sum(pred & real, axis=1)
    fn = np.sum(~pred & generated, axis=1)
    denominator = 2 * tp + fp + fn
    f1 = np.divide(2 * tp, denominator, out=np.zeros(len(tp), float),
                   where=denominator != 0)
    return f1, fp / real.sum()


def load_predictions(path):
    groups = defaultdict(dict)
    identity = {}
    required = {"image_id", "label", "generator", "split", "condition", "model", "seed", "score"}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not required <= set(reader.fieldnames or []):
            raise ValueError("Missing prediction columns: " + str(required - set(reader.fieldnames or [])))
        for row in reader:
            label, seed, score = int(row["label"]), int(row["seed"]), float(row["score"])
            if label not in (0, 1) or not np.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Labels must be 0/1 and scores finite in [0,1].")
            if row["model"] not in MODELS or seed not in SEEDS:
                raise ValueError("Model or seed differs from the declared protocol.")
            if row["split"] not in ("seen", "unseen") or row["condition"] not in CONDITIONS:
                raise ValueError("Unsupported test split or condition.")
            image_id = row["image_id"].strip()
            if not image_id or not row["generator"].strip():
                raise ValueError("Image IDs and generator/source groups cannot be empty.")
            meta = (label, row["generator"], row["split"])
            if image_id in identity and identity[image_id] != meta:
                raise ValueError("Inconsistent label/source/split for image ID " + image_id)
            identity[image_id] = meta
            key = (row["split"], row["condition"], row["model"], seed)
            if image_id in groups[key]:
                raise ValueError("Duplicate image within a model/seed/test condition: " + image_id)
            groups[key][image_id] = score
    expected = {(split, cond, model, seed) for split in ("seen", "unseen")
                for cond in CONDITIONS for model in MODELS for seed in SEEDS}
    if set(groups) != expected:
        raise ValueError("Missing model/seed/condition combinations: " + str(expected - set(groups)))
    return groups, identity


def aligned(groups, identity, split, condition, selected_ids=None):
    keys = [(split, condition, model, seed) for model in MODELS for seed in SEEDS]
    ids = set(groups[keys[0]])
    if any(set(groups[key]) != ids for key in keys):
        raise ValueError("Models and seeds must evaluate identical IDs in each test condition.")
    if selected_ids is not None:
        if not set(selected_ids) <= ids:
            raise ValueError("Requested IDs are not present in this test condition.")
        ids = set(selected_ids)
    ids = sorted(ids)
    y = np.array([identity[i][0] for i in ids])
    if set(y) != {0, 1}:
        raise ValueError("Each paired evaluation needs both classes.")
    strata = np.array([str(identity[i][0]) + ":" + identity[i][1] for i in ids])
    scores = {model: np.array([[groups[(split, condition, model, seed)][i]
                               for i in ids] for seed in SEEDS]) for model in MODELS}
    return ids, y, strata, scores


def draw_indices(strata, rng):
    return np.concatenate([rng.choice(idx, size=len(idx), replace=True)
                           for group in np.unique(strata)
                           for idx in [np.flatnonzero(strata == group)]])


def interval(values):
    return [float(x) for x in np.quantile(values, [0.025, 0.975])]


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def report(path, out, resamples=1000, permutations=9999):
    groups, identity = load_predictions(path)
    out.mkdir(parents=True, exist_ok=True)
    runs, summaries, paired, robust, errors, group_results = [], [], [], [], [], []
    cache = {}
    rng = np.random.default_rng(42)
    for split in ("seen", "unseen"):
        for condition in CONDITIONS:
            ids, y, strata, scores = aligned(groups, identity, split, condition)
            cache[(split, condition)] = (ids, y, strata, scores)
            metrics = {}
            for model in MODELS:
                metrics[model] = [measures(y, s) for s in scores[model]]
                for seed, score, vals in zip(SEEDS, scores[model], metrics[model]):
                    runs.append(dict(split=split, condition=condition, model=model, seed=seed, **vals))
                    for image_id, actual, s in zip(ids, y, score):
                        predicted = int(s >= 0.5)
                        if predicted != actual:
                            errors.append(dict(image_id=image_id, split=split, condition=condition,
                                               model=model, seed=seed, label=int(actual), score=float(s),
                                               error="FP" if actual == 0 else "FN"))
                    for group in np.unique(strata):
                        ix = np.flatnonzero(strata == group)
                        label = int(y[ix[0]])
                        error = float(np.mean((score[ix] >= 0.5) != label))
                        group_results.append(dict(split=split, condition=condition, model=model,
                                                  seed=seed, group=group, n=len(ix),
                                                  rate_name="fpr" if label == 0 else "fnr", rate=error))
                row = dict(split=split, condition=condition, model=model, n=len(ids))
                for metric in METRICS:
                    values = [v[metric] for v in metrics[model]]
                    row[metric + "_mean"] = float(np.mean(values))
                    row[metric + "_sd"] = float(np.std(values, ddof=1)) if len(values)>1 else None
                summaries.append(row)
            observed = float(np.mean([m["f1"] for m in metrics["clip_linear"]]) -
                             np.mean([m["f1"] for m in metrics["resnet50"]]))
            boot = []
            for _ in range(resamples):
                ix = draw_indices(strata, rng)
                a, _ = f1_fpr(y[ix], scores["clip_linear"][:, ix])
                b, _ = f1_fpr(y[ix], scores["resnet50"][:, ix])
                boot.append(float(np.mean(a - b)))
            low, high = interval(boot)
            extreme = 0
            a0,b0 = scores["clip_linear"],scores["resnet50"]
            for _ in range(permutations):
                swap = rng.integers(0,2,size=(1,len(y))).astype(bool)
                a,_ = f1_fpr(y,np.where(swap,b0,a0))
                b,_ = f1_fpr(y,np.where(swap,a0,b0))
                extreme += abs(float(np.mean(a-b))) >= abs(observed)-1e-12
            perm_p = (extreme+1)/(permutations+1)
            winner = "clip_linear" if observed > 0 else "resnet50"
            fpr_ok = np.mean([m["fpr"] for m in metrics[winner]]) <= 0.10
            direction_supported = (observed > 0 and low > 0) or (observed < 0 and high < 0)
            qualifies = abs(observed) >= 0.03 and direction_supported and fpr_ok
            paired.append(dict(split=split, condition=condition, delta_f1=observed,
                               ci_low=low, ci_high=high, practical_rule_met=bool(qualifies),
                               permutation_p=perm_p,
                               primary=(split == "unseen" and condition == "original")))
        original_ids = set(cache[(split, "original")][0])
        for condition in ("jpeg65", "resize112"):
            selected_ids = original_ids & set(cache[(split, condition)][0])
            ids, y, strata, before = aligned(groups, identity, split, "original", selected_ids)
            _, _, _, after = aligned(groups, identity, split, condition, selected_ids)
            for model in MODELS:
                f0, r0 = f1_fpr(y, before[model])
                f1, r1 = f1_fpr(y, after[model])
                dboot, iboot = [], []
                for _ in range(resamples):
                    ix = draw_indices(strata, rng)
                    a, b = f1_fpr(y[ix], before[model][:, ix])
                    c, d = f1_fpr(y[ix], after[model][:, ix])
                    dboot.append(float(np.mean(a - c)))
                    iboot.append(float(np.mean(d - b)))
                dl, dh = interval(dboot)
                il, ih = interval(iboot)
                robust.append(dict(split=split, condition=condition, model=model, paired_n=len(ids),
                                   excluded_original_n=len(original_ids - selected_ids),
                                   delta_f1=float(np.mean(f1-f0)), f1_ci_low=-dh, f1_ci_high=-dl,
                                   fpr_increase=float(np.mean(r1-r0)), fpr_ci_low=il, fpr_ci_high=ih))
    write_csv(out / "per_run_metrics.csv", runs)
    write_csv(out / "main_metrics_all_conditions.csv", summaries)
    write_csv(out / "paired_model_differences.csv", paired)
    write_csv(out / "robustness_changes.csv", robust)
    write_csv(out / "source_group_errors.csv", group_results)
    if errors:
        write_csv(out / "error_records.csv", errors)
    else:
        (out / "error_records.csv").write_text("image_id,split,condition,model,seed,label,score,error\n")
    metadata = dict(python=platform.python_version(), numpy=np.__version__, sklearn=sklearn.__version__,
                    resamples=resamples, permutations=permutations,seeds=SEEDS, threshold=0.5,
                    interval_scope="image sampling conditional on trained models; not joint seed uncertainty")
    (out / "evaluation_metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evaluation"))
    parser.add_argument("--seeds",type=int,nargs='+',default=[42,43,44])
    args = parser.parse_args()
    SEEDS=tuple(args.seeds)
    report(args.predictions, args.out)
