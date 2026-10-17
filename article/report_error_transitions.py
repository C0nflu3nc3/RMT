"""Export decision transitions from saved scores; no images or model weights needed."""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
groups = {}
with (ROOT / "expanded_test/predictions.csv").open(newline="") as handle:
    for row in csv.DictReader(handle):
        key = (row["split"], row["model"], row["seed"], row["condition"])
        group = groups.setdefault(key, {})
        image_id = row["image_id"]
        if image_id in group:
            raise ValueError(f"Duplicate prediction: {key}, {image_id}")
        group[image_id] = (int(row["label"]), float(row["score"]) >= 0.5)

rows = []
for split, model, seed, condition in sorted(groups):
    if condition == "original":
        continue
    original = groups[(split, model, seed, "original")]
    processed = groups[(split, model, seed, condition)]
    if original.keys() != processed.keys():
        raise ValueError("Original and processed image IDs differ")
    counts = dict(tn_to_fp=0, fp_to_tn=0, fn_to_tp=0, tp_to_fn=0)
    for image_id, (label, before) in original.items():
        after_label, after = processed[image_id]
        if label != after_label:
            raise ValueError("Label changed between conditions")
        if label == 0:
            counts["tn_to_fp"] += int(not before and after)
            counts["fp_to_tn"] += int(before and not after)
        else:
            counts["fn_to_tp"] += int(not before and after)
            counts["tp_to_fn"] += int(before and not after)
    rows.append(dict(split=split, model=model, seed=seed, condition=condition,
                     paired_n=len(original), **counts))

target = ROOT / "article/evaluation/processing_transitions.csv"
with target.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(f"Exported {len(rows)} paired condition/seed groups.")
