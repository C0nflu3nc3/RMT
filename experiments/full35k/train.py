"""Resume-safe ResNet fine-tuning and frozen-CLIP evaluation on the audited cohort."""
import argparse
import csv
import gc
import hashlib
import io
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path

import clip
import numpy as np
import torch
import torchvision
from PIL import Image
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader, Dataset, TensorDataset
from torchvision import transforms

from collect import atomic_json, sha_file, write_csv

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
FIELDS = ("image_id", "label", "generator", "split", "condition", "model", "seed", "score")


class Images(Dataset):
    def __init__(self, rows, cache, transform, condition="original"):
        self.rows, self.cache, self.transform, self.condition = rows, cache, transform, condition

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(self.cache / "canonical" / (row["image_id"] + ".jpg")) as image:
            im = image.convert("RGB")
        if self.condition == "jpeg65":
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=65)
            buf.seek(0)
            with Image.open(buf) as decoded:
                im = decoded.convert("RGB")
        elif self.condition == "resize112":
            im = im.resize((112, 112), Image.Resampling.BICUBIC)
        return self.transform(im), float(row["label"])


def transform_for(name):
    if name == "resnet50":
        mean, std = (.485, .456, .406), (.229, .224, .225)
    else:
        mean = (.48145466, .4578275, .40821073)
        std = (.26862954, .26130258, .27577711)
    return transforms.Compose([transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BICUBIC),
                               transforms.ToTensor(), transforms.Normalize(mean, std)])


def atomic_save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temp)
    temp.replace(path)


def loader(dataset, batch_size, workers=2):
    return DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=workers,
                      persistent_workers=workers > 0, prefetch_factor=2 if workers else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=HERE / "cache")
    parser.add_argument("--fit-clip-only", action="store_true", help="Fit CLIP heads and defer test scoring to the full run")
    parser.add_argument("--out", type=Path, default=HERE / "artifacts")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--stop-after-batches", type=int, default=0)
    args = parser.parse_args()
    args.cache = args.cache.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    os.environ["TORCH_HOME"] = str(args.cache / "weights")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp_enabled = device == "cpu" and CONFIG["precision"].startswith("CPU autocast bfloat16")
    def autocast():
        return torch.autocast("cpu", dtype=torch.bfloat16) if amp_enabled else nullcontext()
    manifest_hash = sha_file(HERE / "manifest.csv")
    config_hash = sha_file(HERE / "config.json")
    with (HERE / "manifest.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["label"] = int(row["label"])
    audit = json.loads((HERE / "sample_audit.json").read_text())
    if manifest_hash != audit["manifest_sha256"] or len(rows) != audit["unique_selected"]:
        raise ValueError("Manifest does not match audited cohort")
    if len({r["sha256"] for r in rows}) != len(rows) or len({r["pixel_sha256"] for r in rows}) != len(rows):
        raise ValueError("Exact duplicate in input cohort")
    parts = {s: [r for r in rows if r["split"] == s] for s in CONFIG["target_counts"]}
    metadata = dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dataset_revision=CONFIG["dataset_revision"], manifest_sha256=manifest_hash, config_sha256=config_hash,
        python=platform.python_version(), torch=torch.__version__, torchvision=torchvision.__version__,
        numpy=np.__version__, pillow=Image.__version__, platform=platform.platform(),
        cpu=next((l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                  if l.startswith("model name")), platform.processor()),
        device=device, threads=args.threads, workers=args.workers, amp_bfloat16=amp_enabled,
        counts={s: len(v) for s, v in parts.items()}, training_seeds=CONFIG["training_seeds"])
    atomic_json(HERE / ("clip_fit_run_metadata.json" if args.fit_clip_only else "run_metadata.json"), metadata)
    print("RUN STARTED", json.dumps(metadata), flush=True)
    session_start = time.monotonic()
    trained_batches = 0

    def status(stage, **kwargs):
        atomic_json(HERE / ("clip_fit_status.json" if args.fit_clip_only else "status.json"), dict(stage=stage, updated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    elapsed_session_seconds=time.monotonic() - session_start, **kwargs))

    def scores_for(model, dataset, name):
        values = []
        model.eval()
        with torch.inference_mode():
            for x, _ in loader(dataset, 32 if name == "clip_linear" else 16,
                               0 if name == "clip_linear" else args.workers):
                x = x.to(device=device, dtype=torch.float32)
                if name == "resnet50":
                    x = x.contiguous(memory_format=torch.channels_last)
                with autocast() if name == "resnet50" else nullcontext():
                    logits = model(x).flatten()
                values.extend(logits.float().sigmoid().cpu().numpy().tolist())
        result = np.asarray(values)
        if len(result) != len(dataset) or not np.isfinite(result).all():
            raise ValueError("Incomplete or non-finite scores")
        return result

    def prediction_rows(records, scores, name, seed, condition):
        return [dict(image_id=r["image_id"], label=r["label"], generator=r["generator"],
                     split=r["split"], condition=condition, model=name, seed=seed, score=float(score))
                for r, score in zip(records, scores)]

    feature_root = args.cache / "features"
    feature_root.mkdir(exist_ok=True)
    feature_memory = {}
    def feature_data(records, condition):
        key = hashlib.sha256((manifest_hash + config_hash + condition + "|".join(r["image_id"] for r in records)).encode()).hexdigest()
        if key in feature_memory:
            return feature_memory[key]
        path = feature_root / (key + ".npy")
        state_path = path.with_suffix(".json")
        cursor = 0
        if state_path.exists():
            saved = json.loads(state_path.read_text())
            if saved["manifest_sha256"] != manifest_hash or saved["config_sha256"] != config_hash:
                raise ValueError("Feature cache provenance mismatch")
            cursor = saved["cursor"]
        if cursor < len(records):
            status("clip_features", condition=condition, images_completed=cursor, images_total=len(records))
            print("CLIP FEATURE START", condition, cursor, "/", len(records), flush=True)
            backbone, _ = clip.load("ViT-B/32", device=device, download_root=str(args.cache / "weights"))
            backbone.float().eval()
            for p in backbone.parameters():
                p.requires_grad_(False)
            features = np.lib.format.open_memmap(path, mode="r+" if path.exists() else "w+", dtype="float32", shape=(len(records), 512))
            dataset = Images(records[cursor:], args.cache, transform_for("clip_linear"), condition)
            with torch.inference_mode():
                for x, _ in loader(dataset, 16, args.workers):
                    with autocast():
                        encoded = backbone.encode_image(x.to(device)).float()
                    encoded = encoded / encoded.norm(dim=1, keepdim=True)
                    n = len(x)
                    features[cursor:cursor + n] = encoded.cpu().numpy()
                    cursor += n
                    if cursor % 512 == 0 or cursor == len(records):
                        features.flush()
                        atomic_json(state_path, dict(cursor=cursor, manifest_sha256=manifest_hash, config_sha256=config_hash))
                        status("clip_features", condition=condition, images_completed=cursor, images_total=len(records))
                        print("CLIP FEATURES", condition, cursor, "/", len(records), flush=True)
            del backbone, features
            gc.collect()
        x = torch.from_numpy(np.load(path).copy())
        y = torch.tensor([r["label"] for r in records], dtype=torch.float32)
        data = TensorDataset(x, y)
        feature_memory[key] = data
        return data

    for name in (("clip_linear",) if args.fit_clip_only else ("resnet50", "clip_linear")):
        settings = CONFIG["models"][name]
        if name == "clip_linear":
            all_original = feature_data(rows, "original")
            indices = {s: [i for i, r in enumerate(rows) if r["split"] == s] for s in parts}
            train_data = TensorDataset(all_original.tensors[0][indices["train"]], all_original.tensors[1][indices["train"]])
            val_data = TensorDataset(all_original.tensors[0][indices["validation"]], all_original.tensors[1][indices["validation"]])
        else:
            train_data = Images(parts["train"], args.cache, transform_for(name))
            val_data = Images(parts["validation"], args.cache, transform_for(name))
        for seed in CONFIG["training_seeds"]:
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            directory = args.out / name / f"seed{seed}"
            directory.mkdir(parents=True, exist_ok=True)
            best_path, last_path = directory / "best.pt", directory / "last.pt"
            history_path = directory / "history.json"
            if name == "resnet50":
                model = torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.IMAGENET1K_V1)
                model.fc = nn.Linear(model.fc.in_features, 1)
                model = model.to(device=device, memory_format=torch.channels_last)
            else:
                model = nn.Linear(512, 1).to(device)
            optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"])
            labels = [r["label"] for r in parts["train"]]
            positive_weight = labels.count(0) / labels.count(1)
            criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(positive_weight, device=device))
            epoch, cursor, best, loss_sum, history, global_step = 0, 0, -1., 0., [], 0
            if last_path.exists():
                saved = torch.load(last_path, map_location=device, weights_only=False)
                if saved["manifest_sha256"] != manifest_hash or saved["config_sha256"] != config_hash:
                    raise ValueError("Checkpoint belongs to a different experiment")
                model.load_state_dict(saved["model"])
                optimizer.load_state_dict(saved["optimizer"])
                epoch, cursor, best, loss_sum, history, global_step = [saved[k] for k in
                    ("epoch", "cursor", "best", "loss_sum", "history", "global_step")]
                torch.set_rng_state(saved["torch_rng"].cpu())
                print("CHECKPOINT RESTORED", name, seed, "epoch", epoch, "cursor", cursor, "step", global_step, flush=True)

            def checkpoint(next_epoch, next_cursor, current_loss):
                atomic_save(last_path, dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                    epoch=next_epoch, cursor=next_cursor, best=best, loss_sum=current_loss, history=history,
                    global_step=global_step, torch_rng=torch.get_rng_state(), manifest_sha256=manifest_hash,
                    config_sha256=config_hash, seed=seed, model_name=name))

            while epoch < settings["epochs"]:
                order = torch.randperm(len(train_data), generator=torch.Generator().manual_seed(seed + epoch * 100003)).tolist()
                subset = torch.utils.data.Subset(train_data, order[cursor:])
                batches = loader(subset, settings["batch_size"], 0 if name == "clip_linear" else args.workers)
                model.train()
                epoch_start = time.monotonic()
                status("training", model=name, seed=seed, epoch=epoch + 1, cursor=cursor, images_total=len(train_data))
                for x, y in batches:
                    x, y = x.to(device=device, dtype=torch.float32), y.to(device=device, dtype=torch.float32)
                    if name == "resnet50":
                        x = x.contiguous(memory_format=torch.channels_last)
                    optimizer.zero_grad(set_to_none=True)
                    with autocast() if name == "resnet50" else nullcontext():
                        loss = criterion(model(x).flatten(), y)
                    if not torch.isfinite(loss):
                        raise ValueError("Non-finite training loss")
                    loss.backward()
                    optimizer.step()
                    loss_sum += float(loss.detach()) * len(y)
                    cursor += len(y)
                    global_step += 1
                    trained_batches += 1
                    if global_step % args.checkpoint_every == 0 or cursor == len(train_data) or (args.stop_after_batches and trained_batches >= args.stop_after_batches):
                        checkpoint(epoch, cursor, loss_sum)
                        status("training", model=name, seed=seed, epoch=epoch + 1, cursor=cursor,
                               images_total=len(train_data), loss=loss_sum / cursor, checkpoint=str(last_path))
                        print("TRAIN CHECKPOINT", name, seed, "epoch", epoch + 1, cursor, "/", len(train_data), "loss", loss_sum / cursor, flush=True)
                    if args.stop_after_batches and trained_batches >= args.stop_after_batches:
                        print("CONTROLLED PAUSE", name, seed, "step", global_step, flush=True)
                        return
                values = scores_for(model, val_data, name)
                val_f1 = float(f1_score([r["label"] for r in parts["validation"]], values >= .5, zero_division=0))
                history.append(dict(epoch=epoch + 1, loss=loss_sum / len(train_data), validation_f1=val_f1,
                                    seconds=time.monotonic() - epoch_start))
                if val_f1 > best:
                    best = val_f1
                    atomic_save(best_path, model.state_dict())
                epoch += 1
                cursor, loss_sum = 0, 0.
                checkpoint(epoch, cursor, loss_sum)
                atomic_json(history_path, history)
                print("EPOCH COMPLETE", name, seed, history[-1], flush=True)
            model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True))
            model.eval()
            if not (directory / "validation.csv").exists():
                values = scores_for(model, val_data, name)
                write_csv(directory / "validation.csv", prediction_rows(parts["validation"], values, name, seed, "original"))
            if args.fit_clip_only:
                del model, optimizer
                gc.collect()
                continue
            for split in ("seen", "unseen"):
                for condition in CONFIG["conditions"]:
                    target = directory / f"{split}_{condition}.csv"
                    if target.exists():
                        with target.open(newline="") as f:
                            previous = list(csv.DictReader(f))
                        if [r["image_id"] for r in previous] != [r["image_id"] for r in parts[split]]:
                            raise ValueError("Prediction identities differ from the cohort")
                        continue
                    status("evaluation", model=name, seed=seed, split=split, condition=condition)
                    if name == "clip_linear":
                        if condition == "original":
                            idx = indices[split]
                            test_data = TensorDataset(all_original.tensors[0][idx], all_original.tensors[1][idx])
                        else:
                            test_data = feature_data(parts[split], condition)
                    else:
                        test_data = Images(parts[split], args.cache, transform_for(name), condition)
                    values = scores_for(model, test_data, name)
                    write_csv(target, prediction_rows(parts[split], values, name, seed, condition))
                    print("EVALUATION COMPLETE", name, seed, split, condition, "n", len(values),
                          "F1", float(f1_score([r["label"] for r in parts[split]], values >= .5, zero_division=0)), flush=True)
            del model, optimizer
            gc.collect()
    if args.fit_clip_only:
        status("clip_fit_complete")
        print("CLIP FIT COMPLETE", flush=True)
        return
    predictions, validation = [], []
    for name in CONFIG["models"]:
        for seed in CONFIG["training_seeds"]:
            directory = args.out / name / f"seed{seed}"
            for split in ("seen", "unseen"):
                for condition in CONFIG["conditions"]:
                    with (directory / f"{split}_{condition}.csv").open(newline="") as f:
                        predictions.extend(csv.DictReader(f))
            with (directory / "validation.csv").open(newline="") as f:
                validation.extend(csv.DictReader(f))
    expected = (len(parts["seen"]) + len(parts["unseen"])) * 18
    if len(predictions) != expected:
        raise ValueError("Incomplete final prediction table")
    write_csv(HERE / "predictions.csv", predictions)
    write_csv(HERE / "validation_predictions.csv", validation)
    status("statistical_analysis", prediction_rows=len(predictions))
    subprocess.run([sys.executable, str(HERE / "report_results.py"), str(HERE / "predictions.csv"),
                    "--out", str(HERE / "evaluation")], check=True)
    status("complete", unique_images=len(rows), prediction_rows=len(predictions))
    print("EXPERIMENT COMPLETE", len(rows), "images", len(predictions), "predictions", flush=True)


if __name__ == "__main__":
    main()
