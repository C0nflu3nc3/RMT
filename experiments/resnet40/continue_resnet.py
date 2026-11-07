"""Continue each saved ResNet-50 from epoch 1 on the audited Tiny-GenImage split."""
import argparse
import csv
import io
import json
import math
import os
from contextlib import nullcontext
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch
from PIL import Image
from sklearn.metrics import confusion_matrix, f1_score
from torch import nn
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import models, transforms

from collect import atomic_json, sha_file, write_csv

ROOT = Path(__file__).resolve().parent
ORIGINAL_MANIFEST_SHA256 = "1d8fb1ab8e174d31802e6b904b4730f69930214abf100dc5aea992e6241b941e"
SPLITS = ("train", "validation", "seen", "unseen")
CONDITIONS = ("original", "jpeg65", "resize112")
TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BICUBIC),
    transforms.ToTensor(),
    transforms.Normalize((.485, .456, .406), (.229, .224, .225)),
])


class Images(Dataset):
    def __init__(self, rows, canonical, condition="original"):
        self.rows, self.canonical, self.condition = rows, canonical, condition

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(self.canonical / (row["image_id"] + ".jpg")) as image:
            image = image.convert("RGB")
        if self.condition == "jpeg65":
            with io.BytesIO() as buffer:
                image.save(buffer, format="JPEG", quality=65)
                buffer.seek(0)
                with Image.open(buffer) as jpeg:
                    image = jpeg.convert("RGB")
        elif self.condition == "resize112":
            image = image.resize((112, 112), Image.Resampling.BICUBIC)
        return TRANSFORM(image), row["label"]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def atomic_save(value, path):
    temp = path.with_suffix(".tmp")
    torch.save(value, temp)
    temp.replace(path)


def metric_row(rows, scores):
    if len(scores) != len(rows) or not all(map(math.isfinite, scores)):
        raise ValueError("Incomplete or non-finite scores")
    labels = [int(row["label"]) for row in rows]
    decisions = [float(score) >= .5 for score in scores]
    tn, fp, fn, tp = map(int, confusion_matrix(labels, decisions, labels=[0, 1]).ravel())
    return dict(f1=f1_score(labels, decisions, zero_division=0), fpr=fp / (fp + tn),
                tn=tn, fp=fp, fn=fn, tp=tp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "cache")
    parser.add_argument("--out", type=Path, default=ROOT / "followup")
    parser.add_argument("--additional-epochs", type=int, default=2)
    parser.add_argument("--seeds", type=int, choices=(42, 43, 44), nargs="+", default=[42, 43, 44])
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--precision", choices=("float32", "bfloat16"), default="bfloat16")
    parser.add_argument("--stop-after-batches", type=int, default=0,
                        help="Save and exit after this many optimizer steps in this invocation")
    args = parser.parse_args()
    if args.additional_epochs < 1:
        parser.error("--additional-epochs must be positive")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA unavailable. Install CUDA-enabled PyTorch and check the NVIDIA driver.")
    if args.device == "cuda" and args.precision == "bfloat16" and not torch.cuda.is_bf16_supported():
        parser.error("This GPU does not support bfloat16. Set --precision float32.")
    torch.set_num_threads(args.threads)
    torch.use_deterministic_algorithms(True)

    cfg = json.loads((ROOT / "config.json").read_text())
    settings = cfg["models"]["resnet50"]
    final_epoch = 1 + args.additional_epochs
    manifest = ROOT / "manifest.csv"
    manifest_hash = sha_file(manifest)
    audit = json.loads((ROOT / "sample_audit.json").read_text())
    if manifest_hash != ORIGINAL_MANIFEST_SHA256 or manifest_hash != audit["manifest_sha256"]:
        raise ValueError("Dataset split differs from the original experiment")
    rows = read_csv(manifest)
    canonical = args.cache.resolve() / "canonical"
    for row in rows:
        row["label"] = int(row["label"])
    if not canonical.is_dir() or sum(1 for _ in canonical.glob("*.jpg")) < len(rows):
        raise FileNotFoundError(f"Run collect.py first. Canonical images are missing in {canonical}")
    parts = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    train = Images(parts["train"], canonical)
    labels = [row["label"] for row in parts["train"]]
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(
        labels.count(0) / labels.count(1), device=args.device))

    def autocast():
        if args.precision == "bfloat16":
            return torch.autocast(args.device, dtype=torch.bfloat16)
        return nullcontext()

    def batches(data):
        return DataLoader(data, batch_size=settings["batch_size"], shuffle=False,
                          pin_memory=args.device == "cuda")

    def image_batch(x):
        return x.to(device=args.device, memory_format=torch.channels_last, non_blocking=True)

    def predict(model, data):
        model.eval()
        scores = []
        with torch.inference_mode():
            for x, _ in batches(data):
                with autocast():
                    logits = model(image_batch(x)).flatten()
                scores.extend(logits.float().sigmoid().cpu().tolist())
        return scores

    report = []
    trained_batches = 0
    for seed in sorted(set(args.seeds)):
        start = ROOT / "initial" / f"seed{seed}"
        output = args.out / f"seed{seed}"
        output.mkdir(parents=True, exist_ok=True)
        last = output / "last.pt"
        provenance = dict(seed=seed, manifest_sha256=manifest_hash,
                          config_sha256=sha_file(ROOT / "config.json"),
                          initial_sha256=sha_file(start / "best.pt"),
                          device=args.device, precision=args.precision,
                          torch_version=str(torch.__version__))
        torch.manual_seed(seed)
        model = models.resnet50(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 1)
        model = model.to(device=args.device, memory_format=torch.channels_last)
        optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"])
        epoch, cursor, loss_sum = 2, 0, 0.
        history = json.loads((start / "history.json").read_text())
        if last.exists():
            saved = torch.load(last, map_location="cpu", weights_only=True)
            if saved["provenance"] != provenance:
                raise ValueError(f"Checkpoint provenance mismatch for seed {seed}")
            model.load_state_dict(saved["model"])
            optimizer.load_state_dict(saved["optimizer"])
            epoch, cursor, loss_sum, history = (saved[key] for key in
                                                ("epoch", "cursor", "loss_sum", "history"))
            if epoch > final_epoch + 1 or (epoch == final_epoch + 1 and cursor):
                raise ValueError("Use a new output directory to run fewer epochs")
            del saved
        else:
            model.load_state_dict(torch.load(start / "best.pt", map_location="cpu", weights_only=True))

        def save():
            atomic_save(dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                             epoch=epoch, cursor=cursor, loss_sum=loss_sum, history=history,
                             provenance=provenance), last)

        while epoch <= final_epoch:
            generator = torch.Generator().manual_seed(seed + (epoch - 1) * 100003)
            order = torch.randperm(len(train), generator=generator).tolist()
            print(f"Seed {seed} | epoch {epoch}/{final_epoch} | {cursor}/{len(train)}", flush=True)
            model.train()
            for x, y in batches(Subset(train, order[cursor:])):
                y = y.to(device=args.device, dtype=torch.float32, non_blocking=True)
                optimizer.zero_grad(set_to_none=True)
                with autocast():
                    loss = criterion(model(image_batch(x)).flatten(), y)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                loss.backward()
                optimizer.step()
                cursor += len(y)
                loss_sum += float(loss.detach()) * len(y)
                trained_batches += 1
                stop = 0 < args.stop_after_batches == trained_batches
                if cursor % (settings["batch_size"] * 100) == 0 or cursor == len(train) or stop:
                    save()
                    print(f"Seed {seed} | epoch {epoch} | {cursor}/{len(train)}", flush=True)
                if stop:
                    return
            validation = Images(parts["validation"], canonical)
            metrics = metric_row(validation.rows, predict(model, validation))
            history.append(dict(epoch=epoch, loss=loss_sum / len(train), validation_f1=metrics["f1"]))
            print(f"Seed {seed} | epoch {epoch} complete | validation F1 {metrics['f1']:.4f}", flush=True)
            epoch, cursor, loss_sum = epoch + 1, 0, 0.
            save()

        atomic_json(output / "history.json", history)
        for split in ("seen", "unseen"):
            for condition in CONDITIONS:
                data = Images(parts[split], canonical, condition)
                prior = read_csv(start / f"{split}_{condition}.csv")
                if [(r["image_id"], int(r["label"])) for r in prior] != [
                    (r["image_id"], r["label"]) for r in data.rows
                ]:
                    raise ValueError("Published score rows differ from the test split")
                baseline = metric_row(data.rows, [float(row["score"]) for row in prior])
                score_path = output / f"epoch{final_epoch}_{split}_{condition}.csv"
                if score_path.exists():
                    saved_scores = read_csv(score_path)
                    if [r["image_id"] for r in saved_scores] != [r["image_id"] for r in data.rows]:
                        raise ValueError("Cached scores differ from the test split")
                    scores = [float(row["score"]) for row in saved_scores]
                else:
                    scores = predict(model, data)
                    write_csv(score_path, [dict(image_id=row["image_id"], label=row["label"], score=score)
                                           for row, score in zip(data.rows, scores)])
                result = metric_row(data.rows, scores)
                report.append(dict(seed=seed, epoch=final_epoch, split=split, condition=condition,
                                   epoch1_f1=baseline["f1"], epoch1_fpr=baseline["fpr"],
                                   delta_f1=result["f1"] - baseline["f1"],
                                   delta_fpr=result["fpr"] - baseline["fpr"], **result))
                print(f"Seed {seed} | {split} {condition} | F1 {result['f1']:.4f}", flush=True)

    write_csv(args.out / f"metrics_epoch{final_epoch}.csv", report)


if __name__ == "__main__":
    main()
