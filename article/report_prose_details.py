"""Export supplementary prose details from regenerated scores and saved history."""
from pathlib import Path
import csv, json
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "article/evaluation"
def read(name):
    with (ROOT / name).open(newline="") as handle:
        return list(csv.DictReader(handle))

groups = defaultdict(list)
for row in read("article/evaluation/per_run_metrics.csv"):
    groups[(row["split"], row["condition"], row["model"])].append(row)
ranges = []
for (split, condition, model), rows in sorted(groups.items()):
    ranges.append(dict(split=split, condition=condition, model=model,
                       seeds=[int(r["seed"]) for r in rows],
                       ranges={metric: [min(float(r[metric]) for r in rows),
                                        max(float(r[metric]) for r in rows)]
                               for metric in ("f1", "fpr")}))
misses = []
for row in read("article/evaluation/source_group_errors.csv"):
    if row["condition"] != "original" or row["rate_name"] != "fnr":
        continue
    count = float(row["rate"]) * int(row["n"])
    if abs(count - round(count)) > 1e-8:
        raise ValueError("Noninteger miss count")
    misses.append(dict(split=row["split"], model=row["model"],
                       seed=int(row["seed"]), generator=row["group"].split(":", 1)[1],
                       n=int(row["n"]), misses=int(round(count))))
history = json.loads((ROOT / "pilot/training_history.json").read_text())
checkpoints = []
for seed, models in sorted(history.items()):
    for model, epochs in sorted(models.items()):
        best = max(sorted(epochs, key=lambda r: r["epoch"]),
                   key=lambda r: r["validation_f1"])
        checkpoints.append(dict(seed=int(seed), model=model, epoch=best["epoch"],
                                validation_f1=best["validation_f1"]))
manifest = read("expanded_test/manifest.csv")
real_ids = {split: {r["image_id"] for r in manifest
                    if r["split"] == split and int(r["label"]) == 0}
            for split in ("seen", "unseen")}
details = dict(per_seed_ranges=ranges, original_per_generator_misses=misses,
               selected_checkpoints=checkpoints,
               real_image_cohorts=dict(seen=len(real_ids["seen"]),
                                      unseen=len(real_ids["unseen"]),
                                      shared_ids=len(real_ids["seen"] & real_ids["unseen"])))
(OUT / "prose_details.json").write_text(json.dumps(details, indent=2) + "\n")
print("Prose details exported: ranges, source misses, checkpoints and cohort IDs.")
