"""Rebuild the epoch-40 comparisons from the archived scores."""
import argparse
import csv
import hashlib
import json
import math
import sys
from statistics import mean, stdev
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / "full35k"
sys.path.insert(0, str(BASELINE))

from publish_results import build, pm, read_csv, render_publication, table
from report_results import CONDITIONS, SEEDS, report
from public_evidence import calculate, export_evidence


def read_scores(directory):
    scores = {}
    for seed in SEEDS:
        for split in ("seen", "unseen"):
            for condition in CONDITIONS:
                path = directory / f"seed{seed}" / f"epoch40_{split}_{condition}.csv"
                for row in read_csv(path):
                    key = seed, split, condition, row["image_id"]
                    if key in scores:
                        raise ValueError(f"Duplicate prediction {key}")
                    scores[key] = row["label"], row["score"]
    return scores


def comparison_input(path, directory):
    """Join the new ResNet scores to the archived test IDs and keep the CLIP scores."""
    resnet = read_scores(directory)
    with (BASELINE / "predictions.csv").open(newline="", encoding="utf-8") as source, path.open(
            "w", newline="", encoding="utf-8") as destination:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(destination, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row["model"] == "resnet50":
                key = int(row["seed"]), row["split"], row["condition"], row["image_id"]
                label, score = resnet.pop(key)
                if label != row["label"]:
                    raise ValueError(f"Changed label for {key}")
                row["score"] = score
            writer.writerow(row)
    if resnet:
        raise ValueError(f"{len(resnet)} scores had no matching test ID")


def verify_summary(output):
    inputs = read_csv(HERE / "metrics_epoch40.csv")
    actual = [r for r in read_csv(output / "per_run_metrics.csv") if r["model"] == "resnet50"]
    original = [r for r in read_csv(BASELINE / "evaluation/per_run_metrics.csv") if r["model"] == "resnet50"]
    key = lambda r: (r["seed"], r["split"], r["condition"])
    baseline = {key(r):r for r in original}
    inputs_by_key = {key(r):r for r in inputs}
    if len(inputs) != len(inputs_by_key) or set(inputs_by_key) != {key(r) for r in actual}:
        raise ValueError("Summary and prediction groups differ")
    for row in actual:
        reference = inputs_by_key[key(row)]
        prior = baseline[key(row)]
        if reference["epoch"] != "40":
            raise ValueError("Expected epoch 40")
        for field in ("tp", "tn", "fp", "fn", "f1", "fpr"):
            if not math.isclose(float(row[field]), float(reference[field]), abs_tol=1e-12):
                raise ValueError(f"Summary mismatch for {key(row)} and {field}")
        for field in ("f1", "fpr"):
            if not math.isclose(float(prior[field]), float(reference["epoch1_"+field]), abs_tol=1e-12):
                raise ValueError(f"Baseline mismatch for {key(row)} and {field}")
            if not math.isclose(float(row[field])-float(prior[field]), float(reference["delta_"+field]), abs_tol=1e-12):
                raise ValueError(f"Change mismatch for {key(row)} and {field}")


def epoch_table(tables, output):
    def read(directory):
        return {(r["split"], r["condition"], r["model"]):r
                for r in read_csv(directory / "main_metrics_all_conditions.csv")}
    baseline, final = read(BASELINE / "evaluation"), read(output)
    rows = []
    for split in ("seen", "unseen"):
        for condition, label in zip(CONDITIONS, ("Original", "JPEG 65", "Resize 112")):
            before = baseline[split, condition, "resnet50"]
            after = final[split, condition, "resnet50"]
            rows.append([split.title(), label, *(f"{float(r[m+'_mean']):.3f}" for m in ("f1", "fpr") for r in (before, after))])
    (tables / "epochs.tex").write_text(table(
        "ResNet-50 results at epochs 1 and 40. Values are means across the same three seeds at threshold 0.50.",
        "tab:epochs", "llCCCC", ["Test", "Condition", "F1 (epoch 1)", "F1 (epoch 40)", "FPR (epoch 1)", "FPR (epoch 40)"],
        rows, "The follow-up starts from the epoch-1 weights and initializes a new Adam optimizer. Both evaluations use the same test images."
    ))


def sensitivity_table(tables, output):
    baseline = read_csv(BASELINE / "evaluation/threshold_sensitivity.csv")
    final = {(r["split"], r["model"]): r for r in read_csv(output / "main_metrics_all_conditions.csv")
             if r["condition"] == "original"}

    def baseline_cells(model, split, rule):
        runs = [r for r in baseline if (r["model"], r["split"], r["rule"]) == (model, split, rule)]
        if sorted(int(r["seed"]) for r in runs) != list(SEEDS):
            raise ValueError(f"Incomplete threshold data for {model}, {split}, {rule}")
        values = {}
        for metric in ("f1", "fpr"):
            scores = [float(r[metric]) for r in runs]
            values[metric + "_mean"], values[metric + "_sd"] = mean(scores), stdev(scores)
        return [pm(values, metric) for metric in ("f1", "fpr")]

    rows = []
    for split in ("seen", "unseen"):
        rows.append(["ResNet-50 (epoch 1)", split.title(),
                     *baseline_cells("resnet50", split, "fixed"),
                     *baseline_cells("resnet50", split, "validation")])
        epoch40 = final[split, "resnet50"]
        rows.append(["ResNet-50 (epoch 40)", split.title(),
                     pm(epoch40, "f1"), pm(epoch40, "fpr"), "--", "--"])
        rows.append(["CLIP linear (selected)", split.title(),
                     *baseline_cells("clip_linear", split, "fixed"),
                     *baseline_cells("clip_linear", split, "validation")])
    (tables / "sensitivity.tex").write_text(table(
        "Threshold sensitivity on original images. Values are means $\\pm$ sample SD across three seeds.",
        "tab:sensitivity", "llCCCC",
        ["Checkpoint", "Test", "F1 at 0.50", "FPR at 0.50", "F1 at val. cutoff", "FPR at val. cutoff"],
        rows, "The validation cutoff maximizes F1 on the original validation set. "
              "Dashes indicate that per-image validation scores are unavailable for epoch 40."
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-dir", type=Path, help="Local followup directory with the per-image exports")
    args = parser.parse_args()
    output = HERE / "evaluation"
    tables = HERE / "tables"
    figures = HERE / "figures"
    names = {"resnet50": "ResNet-50 (epoch 40)", "clip_linear": "CLIP linear"}
    evidence = HERE / "evidence"
    evidence.mkdir(exist_ok=True)
    tables.mkdir(exist_ok=True)
    if args.score_dir:
        with TemporaryDirectory(prefix="rmt-resnet40-") as temp:
            scores = Path(temp) / "paired_scores.csv"
            comparison_input(scores, args.score_dir)
            report(scores, output)
            (output / "error_records.csv").unlink()
            build(output, tables, figures, predictions_path=scores, fixed_only=True, names=names)
            export_evidence(scores, evidence)
    verify_summary(output)
    calculate(evidence, output, tables)
    metadata_path = output / "evaluation_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata.update(public_seed=20261107,
                    bootstrap="multinomial draws within each label and source stratum",
                    permutation="binomial swaps within each joint decision pattern",
                    evidence="grouped decision counts and AUROC rank totals")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    details_path = output / "paper_details.json"
    details = json.loads(details_path.read_text())
    details["absolute_intervals"] = [
        {k: float(v) if k.endswith(("_low", "_high")) else v for k, v in row.items()}
        for row in read_csv(output / "absolute_metric_intervals.csv")
    ]
    details_path.write_text(json.dumps(details, indent=2) + "\n")
    render_publication(output, tables, figures, fixed_only=True, names=names)
    epoch_table(tables, output)
    sensitivity_table(tables, output)
    print("Verified the 18 ResNet groups and rebuilt paired statistics from joint counts.")
    checksums = output / "publication_checksums.json"
    values = json.loads(checksums.read_text())
    values.pop("experiments/resnet40/evaluation/error_records.csv", None)
    extra = [tables / "epochs.tex", tables / "epoch40_thresholds.tex", tables / "sensitivity.tex", *evidence.glob("*.csv")]
    for path in extra:
        key = str(path.relative_to(HERE.parents[1]))
        values[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    checksums.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
