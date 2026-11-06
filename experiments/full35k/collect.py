"""Audit the entire 35,000-row mirror and split independent exact-hash groups."""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATASET = "TheKernel01/Tiny-GenImage"
REVISION = "89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69"
NAMES = {0: "real", 1: "ADM", 2: "BigGAN", 3: "GLIDE", 4: "Midjourney",
         5: "SD14", 6: "SD15", 7: "VQDM", 8: "Wukong"}
SEED = 20261106


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def write_csv(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def sha_file(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=HERE / "cache")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    cache = args.cache.resolve()
    shards = cache / "parquet"
    images = cache / "images"
    shards.mkdir(parents=True, exist_ok=True)
    images.mkdir(exist_ok=True)
    started = time.time()
    url = f"https://huggingface.co/api/datasets/{DATASET}/revision/{REVISION}?blobs=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    if metadata["sha"] != REVISION:
        raise ValueError("Dataset revision mismatch")
    files = [s for s in metadata["siblings"] if s["rfilename"].endswith(".parquet")]
    atomic_json(HERE / "source_revision.json", dict(dataset=DATASET, revision=REVISION,
                files=files, accessed_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))

    def download(item):
        target = shards / Path(item["rfilename"]).name
        expected = item["lfs"]["sha256"]
        if target.exists() and target.stat().st_size == item["size"] and sha_file(target) == expected:
            print("SOURCE VERIFIED", target.name, flush=True)
            return target
        partial = target.with_suffix(".part")
        for attempt in range(5):
            try:
                request = urllib.request.Request(
                    f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{item['rfilename']}",
                    headers={"User-Agent": "AITU-GenImage-Research/1.0"})
                with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as f:
                    while block := response.read(1024 * 1024):
                        f.write(block)
                if partial.stat().st_size != item["size"] or sha_file(partial) != expected:
                    raise ValueError("Source size or SHA256 mismatch: " + target.name)
                partial.replace(target)
                print("SOURCE DOWNLOADED", target.name, item["size"], flush=True)
                return target
            except Exception as error:
                print("SOURCE RETRY", target.name, attempt + 1, repr(error), flush=True)
                if attempt == 4:
                    raise
                time.sleep(min(15, 2 ** attempt))

    with ThreadPoolExecutor(args.workers) as executor:
        list(executor.map(download, files))
    index_path = cache / "source_index.csv"
    if index_path.exists():
        with index_path.open(newline="") as f:
            records = list(csv.DictReader(f))
        for row in records:
            for key in ("row_idx", "label", "generator_id", "width", "height", "bytes"):
                row[key] = int(row[key])
        if len(records) != 35000 or any(not (images / (r["image_id"] + ".bin")).exists() for r in records):
            raise ValueError("Incomplete cached source index; remove source_index.csv and re-run")
        if not all(r["image_id"].startswith("tiny_parquet_") for r in records):
            for row in records:
                previous_path = images / (row["image_id"] + ".bin")
                row["image_id"] = f"tiny_parquet_{row['mirror_split']}_{row['row_idx']}"
                previous_path.rename(images / (row["image_id"] + ".bin"))
            write_csv(index_path, records)
    else:
        records = []
        offsets = Counter()
        for item in sorted(files, key=lambda x: x["rfilename"]):
            path = shards / Path(item["rfilename"]).name
            mirror_split = path.name.split("-", 1)[0]
            for batch in pq.ParquetFile(path).iter_batches(batch_size=32):
                for value in batch.to_pylist():
                    idx = offsets[mirror_split]
                    offsets[mirror_split] += 1
                    image_id = f"tiny_parquet_{mirror_split}_{idx}"
                    data = value["image"]["bytes"]
                    if data is None:
                        raise ValueError("Expected embedded source image bytes")
                    with Image.open(io.BytesIO(data)) as im:
                        im.load()
                        w, h = im.size
                        pixels = im.convert("RGB").tobytes()
                        tables = getattr(im, "quantization", None)
                        codec = im.format
                    pixel_hash = hashlib.sha256(f"{w}x{h}:RGB:".encode() + pixels).hexdigest()
                    target = images / (image_id + ".bin")
                    if not target.exists():
                        target.write_bytes(data)
                    generator = int(value["generator"])
                    label = int(value["label"])
                    if label != int(generator != 0):
                        raise ValueError("Source label/generator mismatch: " + image_id)
                    records.append(dict(image_id=image_id, mirror_split=mirror_split, row_idx=idx,
                        label=label, generator_id=generator, generator=NAMES[generator], width=w, height=h,
                        codec=codec, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        pixel_sha256=pixel_hash, jpeg_tables_sha256=hashlib.sha256(
                            json.dumps(tables, sort_keys=True).encode()).hexdigest() if tables else ""))
                    if len(records) % 1000 == 0:
                        print("IMAGES INDEXED", len(records), "/ 35000", flush=True)
            print("SHARD INDEXED", path.name, dict(offsets), flush=True)
        if dict(offsets) != {"train": 28000, "validation": 7000}:
            raise ValueError("Unexpected source split counts: " + str(offsets))
        write_csv(index_path, records)

    old = []
    for path in (REPO / "pilot/manifest.csv", REPO / "expanded_test/manifest.csv"):
        with path.open(newline="") as f:
            old.extend(csv.DictReader(f))
    old_by_id = {r["image_id"]: r for r in old}
    if len(old_by_id) != 2080:
        raise ValueError("Expected 2,080 previous IDs")
    # The viewer used JPEG quality 75 in the pilot. Give every raw source the
    # same baseline encoding before training or robustness transformations.
    canonical = cache / "canonical"
    canonical.mkdir(exist_ok=True)
    canonical_index = cache / "canonical_index.csv"
    if canonical_index.exists():
        with canonical_index.open(newline="") as f:
            additions = {r["image_id"]: r for r in csv.DictReader(f)}
        if set(additions) != {r["image_id"] for r in records}:
            raise ValueError("Canonical cache identities do not match source index")
        for row in records:
            row.update(additions[row["image_id"]])
    else:
        def canonicalize(row):
            with Image.open(images / (row["image_id"] + ".bin")) as im:
                rgb = im.convert("RGB")
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=75, subsampling=2)
            data = buffer.getvalue()
            with Image.open(io.BytesIO(data)) as im:
                pixels = im.convert("RGB").tobytes()
                w, h = im.size
            (canonical / (row["image_id"] + ".jpg")).write_bytes(data)
            return dict(image_id=row["image_id"], canonical_sha256=hashlib.sha256(data).hexdigest(),
                        canonical_pixel_sha256=hashlib.sha256(f"{w}x{h}:RGB:".encode() + pixels).hexdigest())
        additions = []
        with ThreadPoolExecutor(args.workers) as executor:
            for row, info in zip(records, executor.map(canonicalize, records)):
                row.update(info)
                additions.append(info)
                if len(additions) % 2000 == 0:
                    print("COMMON JPEG ENCODING", len(additions), "/", len(records), flush=True)
        write_csv(canonical_index, additions)
    # Previous IDs refer to the dataset viewer, whose image encoding need not
    # equal the embedded parquet bytes. Never equate those two row-ID namespaces.
    previous_hash_matches = len({r["sha256"] for r in old} & {r["sha256"] for r in records})
    previous_pixel_matches = len({r["pixel_sha256"] for r in old if r.get("pixel_sha256")} &
                                 {r["pixel_sha256"] for r in records})
    used_hashes = set()
    used_pixels = set()
    used_canonical = set()
    candidates = sorted(records, key=lambda r: r["image_id"])
    random.Random(SEED).shuffle(candidates)
    pools = {g: [] for g in NAMES}
    excluded = Counter()
    for row in candidates:
        if row["sha256"] in used_hashes or row["pixel_sha256"] in used_pixels or row["canonical_pixel_sha256"] in used_canonical:
            excluded["exact_source_or_canonical_duplicate"] += 1
        else:
            pools[row["generator_id"]].append(row)
            used_hashes.add(row["sha256"])
            used_pixels.add(row["pixel_sha256"])
            used_canonical.add(row["canonical_pixel_sha256"])
    dev = [1, 2, 3, 6, 7, 8]
    # Allocate all unique development images at approximately 2/3, 2/15, 1/5.
    # In the nominal 35k cohort this is exactly 20k / 4k / 6k / 5k.
    train_fake = round(sum(len(pools[g]) for g in dev) * 2 / 3)
    val_fake = round(sum(len(pools[g]) for g in dev) * 2 / 15)
    def allocate(total, capacities):
        base = {g: total * capacities[g] // sum(capacities.values()) for g in dev}
        ranking = sorted(dev, key=lambda g: (-(total * capacities[g] % sum(capacities.values())), g))
        for g in ranking[:total - sum(base.values())]:
            base[g] += 1
        return base
    train_counts = allocate(train_fake, {g: len(pools[g]) for g in dev})
    remaining = {g: len(pools[g]) - train_counts[g] for g in dev}
    val_counts = allocate(val_fake, remaining)
    seen_counts = {g: remaining[g] - val_counts[g] for g in dev}
    mj = len(pools[4])
    n_seen_real = sum(seen_counts.values())
    n_train_real = len(pools[0]) - mj - val_fake - n_seen_real
    if n_train_real < 1:
        raise ValueError("Insufficient real images for four disjoint partitions")
    targets = {
        "train": {0: n_train_real, **train_counts},
        "validation": {0: val_fake, **val_counts},
        "seen": {0: n_seen_real, **seen_counts},
        "unseen": {0: mj, 4: mj},
    }
    selected = []
    eligible_counts = {NAMES[g]: len(v) for g, v in pools.items()}
    for split, counts in targets.items():
        for g, n in counts.items():
            if len(pools[g]) < n:
                raise ValueError(f"Insufficient independent {NAMES[g]} images: {len(pools[g])} < {n}")
            selected.extend(dict(row, split=split) for row in pools[g][:n])
            pools[g] = pools[g][n:]
    selected.sort(key=lambda r: (r["split"], r["image_id"]))
    assert len(selected) == len({r["sha256"] for r in selected}) == len({r["pixel_sha256"] for r in selected})
    assert len({r["canonical_pixel_sha256"] for r in selected}) == len(selected)
    assert len(selected) == 35000 - sum(excluded.values())
    assert sum(len(v) for v in pools.values()) == 0
    assert all(r["generator"] != "Midjourney" for r in selected if r["split"] != "unseen")
    assert all(r["generator"] in ("real", "Midjourney") for r in selected if r["split"] == "unseen")
    write_csv(HERE / "manifest.csv", selected)
    summary = dict(dataset=DATASET, revision=REVISION, sampling_seed=SEED,
        source_rows=len(records), source_counts=dict(Counter(r["generator"] for r in records)),
        unique_selected=len(selected), previous_ids_excluded=0,
        previous_manifest_rows=len(old_by_id), previous_exact_file_matches=previous_hash_matches,
        previous_known_exact_pixel_matches=previous_pixel_matches, exclusion_counts=dict(excluded),
        eligible_counts=eligible_counts, counts=dict(Counter(r["split"] for r in selected)),
        groups={f"{s}/{l}": n for (s, l), n in sorted(Counter((r["split"], r["label"]) for r in selected).items())},
        generator_groups={f"{s}/{g}": n for (s, g), n in sorted(Counter((r["split"], r["generator"]) for r in selected).items())},
        unique_file_hashes=len({r["sha256"] for r in selected}),
        unique_pixel_hashes=len({r["pixel_sha256"] for r in selected}),
        unique_canonical_pixel_hashes=len({r["canonical_pixel_sha256"] for r in selected}),
        source_file_hashes_verified=True,
        image_access="Embedded raw parquet bytes, not dataset-viewer re-encoded images.",
        common_baseline_encoding=dict(codec="JPEG", quality=75, subsampling=2, before_robustness_conditions=True,
            note="Equal final encoding does not match prior compression history or native resolution."),
        manifest_sha256=sha_file(HERE / "manifest.csv"),
        selected_bytes=sum(r["bytes"] for r in selected), collection_seconds=time.time() - started,
        source_index_sha256=sha_file(index_path),
        native_size_by_generator={g: dict(width_min=min(r["width"] for r in group),
            width_max=max(r["width"] for r in group), height_min=min(r["height"] for r in group),
            height_max=max(r["height"] for r in group), jpeg_tables=dict(Counter(r["jpeg_tables_sha256"] for r in group)))
            for g in sorted({r["generator"] for r in selected})
            for group in [[r for r in selected if r["generator"] == g]]},
        limitations=["Third-party mirror; not an official GenImage archive audit.",
            "Source mirror train/validation rows are pooled before creating fresh study partitions.",
            "No category, native-size or compression-history matching; these remain potential confounds.",
            "Exact file/pixel deduplication does not establish absence of perceptual near-duplicates.",
            "SD14 has no rows in this mirror; development uses ADM, BigGAN, GLIDE, SD15, VQDM and Wukong.",
            "The user requested the entire mirror: previously studied source content can be included. This is a new split and refit, not a wholly fresh post-pilot cohort.",
            "Embedded parquet bytes and dataset-viewer image responses use separate ID namespaces; their byte/pixel encodings can differ."])
    atomic_json(HERE / "sample_audit.json", summary)
    atomic_json(HERE / "status.json", dict(stage="data_audited", updated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                counts=summary["counts"], manifest_sha256=summary["manifest_sha256"]))
    print("COHORT AUDIT COMPLETE", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
