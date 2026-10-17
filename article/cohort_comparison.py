"""Compare the two disjoint test cohorts using their unchanged saved scores."""
import csv
import importlib.util
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUT = ROOT / "evaluation"
spec = importlib.util.spec_from_file_location(
    "cohort_metrics", PROJECT / "code/report_results.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def read(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def build():
    cohorts = {
        "initial": read(PROJECT / "pilot/predictions.csv"),
        "later": read(PROJECT / "expanded_test/predictions.csv"),
    }
    ids = {key: {r["image_id"] for r in rows} for key, rows in cohorts.items()}
    assert not ids["initial"].intersection(ids["later"])
    summary, counts = [], []
    for cohort, predictions in cohorts.items():
        for split in ["seen", "unseen"]:
            for model in metrics.MODELS:
                runs, id_sets, class_counts = [], [], []
                for seed in metrics.SEEDS:
                    rows = [r for r in predictions if r["split"] == split
                            and r["model"] == model and int(r["seed"]) == seed
                            and r["condition"] == "original"]
                    image_ids = {r["image_id"] for r in rows}
                    assert len(image_ids) == len(rows)
                    labels = [int(r["label"]) for r in rows]
                    real, generated = labels.count(0), labels.count(1)
                    expected = 40 if cohort == "initial" else 400
                    assert real == generated == expected
                    result = metrics.measures(labels, [float(r["score"]) for r in rows])
                    runs.append(result)
                    id_sets.append(image_ids)
                    class_counts.append((real, generated))
                    if cohort == "later" and split == "unseen":
                        counts.append(dict(model=model, seed=seed, n=len(rows),
                                           tp=result["tp"], fp=result["fp"],
                                           tn=result["tn"], fn=result["fn"]))
                assert id_sets[0] == id_sets[1] == id_sets[2]
                assert len(set(class_counts)) == 1
                summary.append(dict(
                    cohort=cohort, split=split, model=model,
                    n=sum(class_counts[0]), real=class_counts[0][0],
                    generated=class_counts[0][1],
                    f1_mean=statistics.mean(r["f1"] for r in runs),
                    f1_sd=statistics.stdev(r["f1"] for r in runs),
                    fpr_mean=statistics.mean(r["fpr"] for r in runs),
                    fpr_sd=statistics.stdev(r["fpr"] for r in runs)))
    OUT.mkdir(exist_ok=True)
    metrics.write_csv(OUT / "cohort_comparison.csv", summary)
    metrics.write_csv(OUT / "unseen_confusion_counts.csv", counts)
    print("Initial/later cohort comparison and six unseen count rows written.")


if __name__ == "__main__":
    build()
