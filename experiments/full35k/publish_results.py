"""Build the paper's tables and figures from the completed image-level scores."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from report_results import (CONDITIONS, MODELS, SEEDS, aligned, draw_indices,
                            f1_fpr, interval, load_predictions, measures, write_csv)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAMES = {"resnet50": "ResNet-50", "clip_linear": "CLIP linear"}
CONDITION_NAMES = {"original": "Original", "jpeg65": "JPEG 65", "resize112": "Resize 112"}
COLORS = {"resnet50": "#0072B2", "clip_linear": "#D55E00"}


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(value):
    return f"{float(value):.3f}"


def pm(row, metric):
    return rf"${f(row[metric + '_mean'])}\pm {f(row[metric + '_sd'])}$"


def ci(low, high):
    return f"[{f(low)}, {f(high)}]"


def table(caption, label, columns, header, rows, note=""):
    body = "\n".join(" & ".join(map(str, row)) + r"\\" for row in rows)
    return (rf"\begin{{table}}[!htbp]\centering\resulttable" + "\n"
            + rf"\caption{{{caption}}}\label{{{label}}}" + "\n"
            + rf"\begin{{tabularx}}{{\linewidth}}{{@{{}}{columns}@{{}}}}\toprule" + "\n"
            + " & ".join(header) + r"\\\midrule" + "\n" + body + "\n"
            + r"\bottomrule\end{tabularx}" + "\n"
            + (r"\par\smallskip\parbox{\linewidth}{\footnotesize " + note + "}\n" if note else "")
            + "\\end{table}\n")


def validate_scores(groups, identity, manifest):
    test_rows = {r["image_id"]: r for r in manifest if r["split"] in ("seen", "unseen")}
    if set(identity) != set(test_rows):
        raise ValueError("Test predictions do not cover exactly the audited manifest")
    for image_id, row in test_rows.items():
        if identity[image_id] != (int(row["label"]), row["generator"], row["split"]):
            raise ValueError("Prediction/manifest identity mismatch: " + image_id)
    for split in ("seen", "unseen"):
        for condition in CONDITIONS:
            ids, *_ = aligned(groups, identity, split, condition)
            if set(ids) != {i for i, r in test_rows.items() if r["split"] == split}:
                raise ValueError("Unequal image coverage across conditions")


def build(out, tables_dir, figures_dir):
    out.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_csv(HERE / "manifest.csv")
    audit = json.loads((HERE / "sample_audit.json").read_text())
    config = json.loads((HERE / "config.json").read_text())
    if len(manifest) != audit["unique_selected"]:
        raise ValueError("Manifest count differs from the data audit")
    groups, identity = load_predictions(HERE / "predictions.csv")
    validate_scores(groups, identity, manifest)
    summaries = read_csv(out / "main_metrics_all_conditions.csv")
    summary = {(r["split"], r["condition"], r["model"]): r for r in summaries}
    original = lambda split, model: summary[(split, "original", model)]
    rng = np.random.default_rng(20261106)
    absolute = []
    for split in ("seen", "unseen"):
        for condition in CONDITIONS:
            ids, y, strata, scores = aligned(groups, identity, split, condition)
            samples = {model: {metric: [] for metric in ("f1", "fpr")} for model in MODELS}
            for _ in range(config["bootstrap_resamples"]):
                ix = draw_indices(strata, rng)
                for model in MODELS:
                    a, b = f1_fpr(y[ix], scores[model][:, ix])
                    samples[model]["f1"].append(float(a.mean()))
                    samples[model]["fpr"].append(float(b.mean()))
            for model in MODELS:
                record = dict(split=split, condition=condition, model=model)
                for metric in ("f1", "fpr"):
                    low, high = interval(samples[model][metric])
                    record[metric + "_low"], record[metric + "_high"] = low, high
                absolute.append(record)
    write_csv(out / "absolute_metric_intervals.csv", absolute)
    abs_lookup = {(r["split"], r["condition"], r["model"]): r for r in absolute}

    validation = read_csv(HERE / "validation_predictions.csv")
    expected_val = {r["image_id"]: r for r in manifest if r["split"] == "validation"}
    thresholds, sensitivities, transitions = [], [], []
    for model in MODELS:
        for seed in SEEDS:
            rows = [r for r in validation if r["model"] == model and int(r["seed"]) == seed]
            if len(rows) != len(expected_val) or {r["image_id"] for r in rows} != set(expected_val):
                raise ValueError("Incomplete or duplicate validation scores")
            if any(int(r["label"]) != int(expected_val[r["image_id"]]["label"]) for r in rows):
                raise ValueError("Validation labels differ from manifest")
            y = np.array([int(r["label"]) for r in rows])
            score = np.array([float(r["score"]) for r in rows])
            choices = []
            for threshold in np.arange(1, 20) / 20:
                p = score >= threshold
                tp, fp, fn = np.sum(p & (y == 1)), np.sum(p & (y == 0)), np.sum(~p & (y == 1))
                choices.append((2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0., float(threshold)))
            selected = max(choices)[1]
            thresholds.append(dict(model=model, seed=seed, threshold=selected))
            for split in ("seen", "unseen"):
                ids = sorted(groups[(split, "original", model, seed)])
                actual = np.array([identity[i][0] for i in ids])
                raw = np.array([groups[(split, "original", model, seed)][i] for i in ids])
                for rule, threshold in (("fixed", .5), ("validation", selected)):
                    p = raw >= threshold
                    tp, fp, fn = np.sum(p & (actual == 1)), np.sum(p & (actual == 0)), np.sum(~p & (actual == 1))
                    sensitivities.append(dict(model=model, seed=seed, split=split, rule=rule, threshold=threshold,
                        f1=float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else 0.,
                        fpr=float(fp / np.sum(actual == 0))))
                before = raw >= .5
                for condition in ("jpeg65", "resize112"):
                    after = np.array([groups[(split, condition, model, seed)][i] >= .5 for i in ids])
                    transitions.append(dict(model=model, seed=seed, split=split, condition=condition,
                        real_correct_to_fp=int(np.sum((actual == 0) & ~before & after)),
                        real_fp_to_correct=int(np.sum((actual == 0) & before & ~after)),
                        generated_miss_to_tp=int(np.sum((actual == 1) & ~before & after)),
                        generated_tp_to_miss=int(np.sum((actual == 1) & before & ~after))))
    write_csv(out / "validation_thresholds.csv", thresholds)
    write_csv(out / "threshold_sensitivity.csv", sensitivities)
    write_csv(out / "processing_transitions.csv", transitions)

    run_rows = read_csv(out / "per_run_metrics.csv")
    confusion = [r for r in run_rows if r["split"] == "unseen" and r["condition"] == "original"]
    write_csv(out / "unseen_confusion_counts.csv", confusion)
    successes = []
    for model in MODELS:
        for seed in SEEDS:
            seen = next(r for r in run_rows if r["split"] == "seen" and r["condition"] == "original" and r["model"] == model and int(r["seed"]) == seed)
            unseen = next(r for r in confusion if r["model"] == model and int(r["seed"]) == seed)
            checks = dict(unseen_f1=float(unseen["f1"]) >= .8, seen_fpr=float(seen["fpr"]) <= .1,
                unseen_fpr=float(unseen["fpr"]) <= .1, f1_drop=float(seen["f1"])-float(unseen["f1"]) <= .1)
            successes.append(dict(model=model, seed=seed, **checks, all_targets=all(checks.values())))
    write_csv(out / "success_checks.csv", successes)
    details = dict(counts=dict(Counter(r["split"] for r in manifest)),
                   unique_images=len(manifest), unique_test_images=len(identity),
                   prediction_rows=sum(len(v) for v in groups.values()), thresholds=thresholds,
                   success_checks=successes, absolute_intervals=absolute)
    (out / "paper_details.json").write_text(json.dumps(details, indent=2) + "\n")

    render_publication(out, tables_dir, figures_dir)


def render_publication(out, tables_dir, figures_dir):
    """Render current tables and figures without recalculating the saved statistics."""
    out.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    audit = json.loads((HERE / "sample_audit.json").read_text())
    config = json.loads((HERE / "config.json").read_text())
    summaries = read_csv(out / "main_metrics_all_conditions.csv")
    summary = {(r["split"], r["condition"], r["model"]): r for r in summaries}
    original = lambda split, model: summary[(split, "original", model)]
    absolute = read_csv(out / "absolute_metric_intervals.csv")
    abs_lookup = {(r["split"], r["condition"], r["model"]):
                  {k: (float(v) if k.endswith(("_low", "_high")) else v) for k, v in r.items()}
                  for r in absolute}
    sensitivities = read_csv(out / "threshold_sensitivity.csv")
    confusion = read_csv(out / "unseen_confusion_counts.csv")
    dataset_rows = []
    for split, label in (("train", "Training"), ("validation", "Validation"), ("seen", "Seen test"), ("unseen", "Unseen test")):
        n = audit["counts"][split]
        dataset_rows.append([label, f"{config['target_counts'][split]:,}", f"{n:,}",
                             f"{audit['groups'][split + '/0']:,}", f"{audit['groups'][split + '/1']:,}"])
    dataset_rows.append(["Total", "35,000", "34,998", "17,498", "17,500"])
    texts = {}
    texts["dataset.tex"] = table("Study partitions before and after exact-file, decoded-RGB and common-encoding duplicate screening.",
        "tab:dataset", "Yrrrr", ["Partition", "Nominal", "Retained", "Real", "Generated"], dataset_rows,
        "Two duplicate photographs were removed before splitting. Midjourney occurs only in the unseen test; six other generators supply development and seen-test images. The cohort includes previously inspected pilot images.")
    metric_rows = []
    for split in ("seen", "unseen"):
        for model in MODELS:
            r = original(split, model)
            a = abs_lookup[(split, "original", model)]
            metric_rows.append([NAMES[model], split.title(), pm(r,"accuracy"), pm(r,"precision"), pm(r,"recall"), pm(r,"f1")])
    first = table("Original-image metrics at threshold 0.5. Values are means $\\pm$ sample SD over seeds 42, 43 and 44. P is precision and R is recall.",
        "tab:main", "llCCCC", ["Model", "Test", "Accuracy", "P", "R", "F1"], metric_rows)
    extra = []
    for split in ("seen", "unseen"):
        for model in MODELS:
            r, a = original(split, model), abs_lookup[(split,"original",model)]
            extra.append([NAMES[model], split.title(), pm(r,"fpr"), pm(r,"auroc"), ci(a["f1_low"],a["f1_high"]), ci(a["fpr_low"],a["fpr_high"])])
    body = "\n".join(" & ".join(row) + r"\\" for row in extra)
    panel = (r"\par\medskip\begin{tabularx}{\linewidth}{@{}llCCCC@{}}\toprule" + "\n"
             + r"Model & Test & FPR & AUROC & F1 95\% CI & FPR 95\% CI\\\midrule" + "\n" + body + "\n"
             + r"\bottomrule\end{tabularx}" + "\n"
             + r"\par\smallskip\parbox{\linewidth}{\footnotesize Seen test: 3,000 images per class. Unseen test: 2,500 per class. Confidence intervals resample images within label/source strata and condition on fitted checkpoints.}" + "\n")
    texts["main_results.tex"] = first.replace("\\end{table}\n", panel + "\\end{table}\n")
    paired = read_csv(out / "paired_model_differences.csv")
    texts["paired.tex"] = table("Paired F1 differences (CLIP minus ResNet-50), with image-bootstrap 95\\% intervals. The original-unseen comparison is primary; other p-values are exploratory and unadjusted.",
        "tab:paired", "llrCr", ["Test", "Condition", r"$\Delta$F1", "95\\% CI", "$p$"],
        [[r["split"].title(), CONDITION_NAMES[r["condition"]], f(r["delta_f1"]), ci(r["ci_low"],r["ci_high"]), f"{float(r['permutation_p']):.4f}"] for r in paired],
        "The Monte Carlo permutation resolution is 0.0001 (9,999 swaps plus the observed sample). An F1 advantage also needs an acceptable false-positive rate to meet the practical comparison rule.")
    robust = read_csv(out / "robustness_changes.csv")
    panels = []
    for condition, title in (("jpeg65", "JPEG recompression, quality 65"),
                             ("resize112", r"Downsampling to $112\times112$ pixels")):
        body = []
        for r in robust:
            if r["condition"] != condition:
                continue
            values = [NAMES[r["model"]], r["split"].title(),
                      "$" + f"{float(r['delta_f1']):+.3f}" + r"\;" + ci(r["f1_ci_low"], r["f1_ci_high"]) + "$",
                      "$" + f"{float(r['fpr_increase']):+.4f}" + r"\;" + f"[{float(r['fpr_ci_low']):.4f}, {float(r['fpr_ci_high']):.4f}]" + "$"]
            body.append(" & ".join(values) + r"\\")
        panels.append(r"\par\smallskip\noindent\textbf{" + title + r"}\par\smallskip" + "\n"
            + r"\begin{tabularx}{\linewidth}{@{}Ylrr@{}}\toprule" + "\n"
            + r"Model & Test & $\Delta F_1$ [95\% CI] & $\Delta$FPR [95\% CI]\\\midrule" + "\n"
            + "\n".join(body) + "\n" + r"\bottomrule\end{tabularx}\par\medskip" + "\n")
    texts["robustness.tex"] = (r"\begin{table}[!htbp]\centering\resulttable" + "\n"
        + r"\caption{Paired processing minus original changes, averaged over seeds, with 95\% image-bootstrap intervals. Compression and downsampling are applied independently to the common quality-75 baseline.}\label{tab:robustness}" + "\n"
        + "".join(panels)
        + r"\parbox{\linewidth}{\footnotesize Each comparison uses identical IDs within the 6,000-image seen or 5,000-image unseen test. $\Delta$FPR is shown to four decimals: the ResNet JPEG estimates differ before rounding. An F1 rise does not establish robustness when false positives increase.}\end{table}" + "\n")
    sensitivity_rows = []
    for model in MODELS:
        for split in ("seen", "unseen"):
            for rule in ("fixed", "validation"):
                selected = [r for r in sensitivities if r["model"] == model and r["split"] == split and r["rule"] == rule]
                values = {m + "_mean":float(np.mean([float(r[m]) for r in selected])) for m in ("f1","fpr")}
                values.update({m + "_sd":float(np.std([float(r[m]) for r in selected],ddof=1)) for m in ("f1","fpr")})
                sensitivity_rows.append([NAMES[model],split.title(),rule.title(),pm(values,"f1"),pm(values,"fpr")])
    texts["sensitivity.tex"] = table("Threshold sensitivity on original images: fixed threshold 0.5 versus the threshold maximizing F1 on the 4,000-image validation split. Values are means $\\pm$ sample SD.",
        "tab:sensitivity", "lllCC", ["Model","Test","Rule","F1","FPR"], sensitivity_rows,
        "Thresholds are selected separately per model/seed from 0.05 to 0.95 in steps of 0.05, with the larger threshold winning ties. Test labels never select the threshold.")
    for name, text in texts.items():
        (tables_dir / name).write_text(text)

    plt.rcParams.update({"font.size": 14, "axes.spines.top": False,
        "axes.spines.right": False, "pdf.fonttype": 42, "ps.fonttype": 42,
        "figure.facecolor": "white", "savefig.facecolor": "white"})
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.0))
    fig.subplots_adjust(left=.07, right=.985, bottom=.18, top=.82, wspace=.28)
    for ax, metric, target, label in zip(axes, ("f1", "fpr"), (.8, .1),
                                       ("F1 score", "False-positive rate")):
        x = np.arange(3)
        for j, model in enumerate(MODELS):
            means = np.array([float(summary[("unseen", c, model)][metric + "_mean"]) for c in CONDITIONS])
            lows = np.array([abs_lookup[("unseen", c, model)][metric + "_low"] for c in CONDITIONS])
            highs = np.array([abs_lookup[("unseen", c, model)][metric + "_high"] for c in CONDITIONS])
            positions = x + (j - .5) * .13
            ax.errorbar(positions, means,
                yerr=np.maximum(0, np.array([means-lows, highs-means])),
                fmt="o-", capsize=4, markersize=5, color=COLORS[model],
                label=NAMES[model], linewidth=1.8)
            offset = (-17 if j == 0 else 10) if metric == "f1" else (11 if j == 0 else -18)
            for xx, yy in zip(positions, means):
                ax.annotate(f"{yy:.3f}", (xx, yy), xytext=(0, offset),
                    textcoords="offset points", ha="center", fontsize=11, color=COLORS[model])
        ax.axhline(target, color="#666666", linestyle="--", linewidth=1)
        ax.set_title(f"Target {target:.2f}", loc="left", fontsize=11,
                     color="#555555", pad=9)
        ax.set(xticks=x, xticklabels=[CONDITION_NAMES[c] for c in CONDITIONS],
               ylim=(-.12, 1.07), xlim=(-.3, 2.3), yticks=np.arange(0,1.01,.2), ylabel=label, xlabel="Image condition")
        ax.grid(axis="y", alpha=.2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, 1.01),
               ncol=2, frameon=False, fontsize=14)
    for suffix in ("png", "pdf"):
        fig.savefig(figures_dir / ("unseen_robustness." + suffix), dpi=240,
            **({"metadata": {"CreationDate": None, "ModDate": None}} if suffix == "pdf" else {}))
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))
    fig.subplots_adjust(left=.10, right=.98, bottom=.20, top=.88, wspace=.55)
    for ax, model in zip(axes, MODELS):
        r = next(r for r in confusion if r["model"] == model and int(r["seed"]) == 42)
        matrix = np.array([[int(r["tn"]), int(r["fp"])], [int(r["fn"]), int(r["tp"])]])
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=2500)
        for (i, j), value in np.ndenumerate(matrix):
            color = "white" if value > 1250 else "#111111"
            ax.text(j, i, f"{value:,}", ha="center", va="center", fontsize=17, color=color)
        ax.set(title=NAMES[model], xticks=[0, 1], yticks=[0, 1],
            xticklabels=["Real", "Generated"], yticklabels=["Real", "Generated"],
            xlabel="Predicted class", ylabel="Actual class")
        ax.tick_params(length=0, pad=7)
        for spine in ax.spines.values():
            spine.set_visible(False)
    for suffix in ("png", "pdf"):
        fig.savefig(figures_dir / ("unseen_confusion_seed42." + suffix), dpi=240,
            **({"metadata": {"CreationDate": None, "ModDate": None}} if suffix == "pdf" else {}))
    plt.close(fig)

    # Preserve checksums for exports not materialized during a render-only run.
    checksum_path = out / "publication_checksums.json"
    hashes = json.loads(checksum_path.read_text()) if checksum_path.exists() else {}
    outputs = [p for p in out.iterdir() if p.is_file() and p.name != "publication_checksums.json"]
    outputs += [tables_dir / name for name in texts]
    outputs += list(figures_dir.glob("*.png")) + list(figures_dir.glob("*.pdf"))
    hashes.update({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in outputs})
    checksum_path.write_text(json.dumps(dict(sorted(hashes.items())), indent=2) + "\n")
    print("Rendered five tables and two PNG/PDF figure pairs from archived numerical exports.")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=HERE/"evaluation")
    parser.add_argument("--tables",type=Path,default=ROOT/"tables")
    parser.add_argument("--figures",type=Path,default=HERE/"figures")
    parser.add_argument("--render-only", action="store_true", help="Refresh tables and figures from archived numerical exports, without images or weights")
    args=parser.parse_args()
    if args.render_only:
        render_publication(args.out,args.tables,args.figures)
    else:
        build(args.out,args.tables,args.figures)
