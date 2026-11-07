"""Recompute test statistics from joint decision counts without image-level records."""
from collections import Counter, defaultdict

import numpy as np
from scipy.stats import rankdata

from publish_results import read_csv, table
from report_results import CONDITIONS, MODELS, SEEDS, aligned, interval, load_predictions, write_csv

SPLITS = ("seen", "unseen")
THRESHOLDS = (0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80)
SEED_COUNT = len(SEEDS)
MODEL_WIDTH = SEED_COUNT * len(MODELS)


def export_evidence(path, destination):
    """Aggregate locally held scores. Exports contain counts, without IDs or scores."""
    groups, identity = load_predictions(path)
    joint, ranking, thresholds = [], [], []
    for split in SPLITS:
        for condition in CONDITIONS:
            ids, y, _, scores = aligned(groups, identity, split, condition)
            decision = np.concatenate([scores[m].T >= .50 for m in MODELS], axis=1)
            if condition == "original":
                original = decision
            paired = decision if condition == "original" else np.column_stack((original, decision))
            counts = Counter((int(label), identity[img][1], "".join("1" if d else "0" for d in bits))
                             for img, label, bits in zip(ids, y, paired))
            for (label, source, pattern), n in sorted(counts.items()):
                joint.append(dict(split=split, condition=condition, label=label, source=source,
                                  pattern=pattern, count=n))
            positives = int(y.sum())
            for model, matrix in scores.items():
                for seed, score in zip(SEEDS, matrix):
                    wins_twice = round(2 * rankdata(score)[y == 1].sum() - positives * (positives + 1))
                    ranking.append(dict(split=split, condition=condition, model=model, seed=seed,
                                        positives=positives, negatives=len(y) - positives, pair_wins_twice=wins_twice))
                    if split == "unseen" and condition == "original" and model == "resnet50":
                        for threshold in THRESHOLDS:
                            pred = score >= threshold
                            thresholds.append(dict(seed=seed, threshold=f"{threshold:.2f}",
                                                   tp=int(pred[y == 1].sum()), fp=int(pred[y == 0].sum()),
                                                   positives=positives, negatives=len(y) - positives))
    write_csv(destination / "joint_decision_counts.csv", joint)
    write_csv(destination / "auroc_rank_totals.csv", ranking)
    write_csv(destination / "unseen_threshold_counts.csv", thresholds)


def confusion(weights, labels, decisions):
    """Return arrays with one column per model/seed and one row per draw."""
    p = labels == 1
    tp = weights[:, p] @ decisions[p]
    fp = weights[:, ~p] @ decisions[~p]
    fn = weights[:, p].sum(axis=1, keepdims=True) - tp
    tn = weights[:, ~p].sum(axis=1, keepdims=True) - fp
    return tp, fp, fn, tn


def rate(numerator, denominator):
    return np.divide(numerator, denominator, out=np.zeros_like(numerator, dtype=float), where=denominator != 0)


def metrics(counts):
    tp, fp, fn, tn = counts
    return dict(accuracy=rate(tp+tn, tp+tn+fp+fn), precision=rate(tp, tp+fp),
                recall=rate(tp, tp+fn), f1=rate(2*tp, 2*tp+fp+fn), fpr=rate(fp, fp+tn))


def groups_mean(result):
    return result.reshape(-1, len(MODELS), SEED_COUNT).mean(axis=2)


def calculate(evidence, output, tables):
    grouped = defaultdict(list)
    for row in read_csv(evidence / "joint_decision_counts.csv"):
        grouped[row["split"], row["condition"]].append(row)
    run_rows = {(r["split"], r["condition"], r["model"], int(r["seed"])): r
                for r in read_csv(output / "per_run_metrics.csv")}
    summaries = {(r["split"], r["condition"], r["model"]): r
                 for r in read_csv(output / "main_metrics_all_conditions.csv")}
    rank_rows = {(r["split"], r["condition"], r["model"], int(r["seed"])): r
                 for r in read_csv(evidence / "auroc_rank_totals.csv")}
    rng = np.random.default_rng(20261107)
    intervals, paired, robust = [], [], []
    for split in SPLITS:
        for condition in CONDITIONS:
            records = grouped[split, condition]
            labels = np.array([int(r["label"]) for r in records])
            weights = np.array([int(r["count"]) for r in records], dtype=np.int64)
            decisions = np.array([[int(c) for c in r["pattern"]] for r in records], dtype=np.int64)
            expected_n = 6000 if split == "seen" else 5000
            if weights.sum() != expected_n or weights[labels == 1].sum() != expected_n // 2:
                raise ValueError("Joint counts do not match the audited split")
            current = decisions[:, -MODEL_WIDTH:]
            obs_counts = confusion(weights[None, :], labels, current)
            observed = metrics(obs_counts)
            aucs = []
            for j, (model, seed) in enumerate((m, s) for m in MODELS for s in SEEDS):
                key = split, condition, model, seed
                actual = run_rows[key]
                counts = [int(c[0, j]) for c in obs_counts]
                if counts != [int(actual[f]) for f in ("tp", "fp", "fn", "tn")]:
                    raise ValueError(f"Confusion counts differ for {key}")
                for name, value in observed.items():
                    if not np.isclose(value[0, j], float(actual[name]), atol=1e-12, rtol=0):
                        raise ValueError(f"{name} differs for {key}")
                rank = rank_rows[key]
                auc = int(rank["pair_wins_twice"]) / (2 * int(rank["positives"]) * int(rank["negatives"]))
                if not np.isclose(auc, float(actual["auroc"]), atol=1e-12, rtol=0):
                    raise ValueError(f"AUROC differs for {key}")
                aucs.append(auc)
            for j, model in enumerate(MODELS):
                summary = summaries[split, condition, model]
                part = slice(j*SEED_COUNT, (j+1)*SEED_COUNT)
                for name, values in {**observed, "auroc": np.array([aucs])}.items():
                    series = values[0, part]
                    mean_sd = series.mean(), series.std(ddof=1)
                    saved = float(summary[name+"_mean"]), float(summary[name+"_sd"])
                    if not np.allclose(mean_sd, saved, atol=1e-12, rtol=0):
                        raise ValueError(f"{name} summary differs for {split}, {condition}, {model}")

            strata = [(int(r["label"]), r["source"]) for r in records]
            draws = np.empty((1000, len(records)), dtype=np.int64)
            for stratum in sorted(set(strata)):
                idx = [i for i, key in enumerate(strata) if key == stratum]
                n = int(weights[idx].sum())
                draws[:, idx] = rng.multinomial(n, weights[idx] / n, size=len(draws))
            boot = {k: groups_mean(v) for k, v in metrics(confusion(draws, labels, current)).items()}
            point = {k: groups_mean(v)[0] for k, v in observed.items()}

            for j, model in enumerate(MODELS):
                f1_low, f1_high = interval(boot["f1"][:, j])
                fpr_low, fpr_high = interval(boot["fpr"][:, j])
                intervals.append(dict(split=split, condition=condition, model=model,
                                      f1_low=f1_low, f1_high=f1_high, fpr_low=fpr_low, fpr_high=fpr_high))

            delta = float(point["f1"][1] - point["f1"][0])
            low, high = interval(boot["f1"][:, 1] - boot["f1"][:, 0])
            exchanged = np.roll(current, SEED_COUNT, axis=1)
            swaps = rng.binomial(weights, .5, size=(9999, len(weights)))
            perm_counts = tuple(a+b for a, b in zip(confusion(weights-swaps, labels, current),
                                                   confusion(swaps, labels, exchanged)))
            perm_f1 = groups_mean(metrics(perm_counts)["f1"])
            extreme = np.count_nonzero(np.abs(perm_f1[:, 1] - perm_f1[:, 0]) >= abs(delta)-1e-12)
            winner = int(delta > 0)
            paired.append(dict(split=split, condition=condition, delta_f1=delta, ci_low=low, ci_high=high,
                               practical_rule_met=bool(abs(delta)>=.03 and (low>0 or high<0) and point["fpr"][winner]<=.10),
                               permutation_p=float((extreme+1)/10000), primary=split=="unseen" and condition=="original"))
            if condition == "original":
                continue
            before = decisions[:, :MODEL_WIDTH]
            before_boot = {k: groups_mean(v) for k, v in metrics(confusion(draws, labels, before)).items()}
            before_point = {k: groups_mean(v)[0] for k, v in metrics(confusion(weights[None, :], labels, before)).items()}
            for j, model in enumerate(MODELS):
                f1_low, f1_high = interval(boot["f1"][:, j]-before_boot["f1"][:, j])
                fpr_low, fpr_high = interval(boot["fpr"][:, j]-before_boot["fpr"][:, j])
                robust.append(dict(split=split, condition=condition, model=model, paired_n=expected_n,
                                   excluded_original_n=0, delta_f1=float(point["f1"][j]-before_point["f1"][j]),
                                   f1_ci_low=f1_low, f1_ci_high=f1_high,
                                   fpr_increase=float(point["fpr"][j]-before_point["fpr"][j]),
                                   fpr_ci_low=fpr_low, fpr_ci_high=fpr_high))

    write_csv(output / "absolute_metric_intervals.csv", intervals)
    write_csv(output / "paired_model_differences.csv", paired)
    write_csv(output / "robustness_changes.csv", robust)
    threshold_table(evidence, tables)


def threshold_table(evidence, tables):
    counts = read_csv(evidence / "unseen_threshold_counts.csv")
    rows = []
    for threshold in THRESHOLDS:
        runs = [r for r in counts if float(r["threshold"]) == threshold]
        if sorted(int(r["seed"]) for r in runs) != list(SEEDS):
            raise ValueError(f"Missing seeds at threshold {threshold}")
        tp, fp, p, n = (np.array([int(r[key]) for r in runs]) for key in ("tp", "fp", "positives", "negatives"))
        means = (rate(tp, p).mean(), rate(fp, n).mean(), rate(2*tp, tp+p+fp).mean())
        rows.append([f"{threshold:.2f}", *(f"{x:.3f}" for x in means)])
    (tables / "epoch40_thresholds.tex").write_text(table(
        "ResNet-50 at epoch 40 on original unseen images. Values are means across three seeds.",
        "tab:threshold40", "YCCC", ["Threshold", "Recall", "FPR", "F1"], rows,
        "This sweep describes the test set. Choose an operating cutoff on separate validation data."
    ))
