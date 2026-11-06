# Entire-mirror refit: 35,000 source images

This experiment was started on 6 November 2026 at the user's request. Its results are separate from the earlier pilot. Check `status.json` for the last recorded stage. A running stage does not mean that training has finished. The earlier article's numerical results remain pilot results until the complete prediction table has been generated and checked.

The entire `TheKernel01/Tiny-GenImage` mirror at revision `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69` is used, after global exact-file and decoded-RGB deduplication. Previous pilot images are included. The original mirror train and validation splits are pooled before creating the new partitions. This is a new split and refit, not an independent cohort excluding previously inspected data.

Nominal allocation, before any deduplication:

| Study partition | Real | Generated | Total |
|---|---:|---:|---:|
| Training | 10,000 | 10,000 | 20,000 |
| Validation | 2,000 | 2,000 | 4,000 |
| Seen test | 3,000 | 3,000 | 6,000 |
| Unseen test | 2,500 | 2,500 | 5,000 |
| Total | 17,500 | 17,500 | 35,000 |

`sample_audit.json` and `manifest.csv` give the actual counts after deduplication. The completed audit retained 34,998 images: 19,998 training, 4,000 validation, 6,000 seen-test and 5,000 unseen-test images. Two duplicate real images were removed; training has 9,998 real and 10,000 generated images, with loss weighting based only on training counts. Midjourney is used only in the unseen test. Development uses ADM, BigGAN, GLIDE, SD15, VQDM and Wukong. SD14 has no rows in this mirror. Both classes share disjoint IDs, file hashes and decoded-pixel hashes across the four study partitions. Category, native resolution and prior compression are audited but are not matched. Their effects remain potential confounds.

ResNet-50 starts from torchvision ImageNet1K V1 weights and fine-tunes all parameters for one epoch. CLIP ViT-B/32 is frozen and its linear head trains for 40 epochs. Each model uses seeds 42, 43 and 44, with the same manifest and processing conditions. The checkpoint with highest validation F1 at threshold 0.5 is selected; the earliest epoch wins ties. The unequal training budgets are retained from the CPU baseline and are not a compute-matched architecture comparison.

All source images are converted to RGB and re-encoded to JPEG quality 75 (4:2:0) at native size before any training/test condition. The common encoding matches the pilot viewer quality, while prior compression history remains unmatched. Canonical pixel hashes are also deduplicated before partitioning. Images are then resized to exactly 224×224 with bicubic interpolation, and normalized for each model. There is no crop or augmentation. Tests use original images, JPEG quality 65 re-encoding, and downsampling to 112×112 before the common resize. On this CPU, the encoders use bfloat16 autocast with float32 parameters and Adam state; the CLIP head and stored features/scores use float32. `run_metadata.json` records the actual environment.

## Run or resume

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r experiments/full35k/requirements.txt
python -u experiments/full35k/collect.py
python -u experiments/full35k/train.py
```

The source parquet shards occupy about 8.4 GB; extracted images use additional space. The first collection verifies every source shard against its published LFS SHA256. Subsequent collections use the same pinned source and saved index. Training checkpoints are written atomically every 50 batches and after each epoch. Re-running `train.py` restores model and Adam states, epoch, image cursor, RNG state and history. Data loading defaults to zero subprocess workers for compatibility with this runtime; model computation uses six CPU threads. Manifest and configuration hashes must match before a checkpoint is accepted. Completed prediction groups and CLIP features are reused. A controlled pause can be made with `--stop-after-batches 2`; this option does not change the experiment configuration.

Final outputs are `predictions.csv`, `validation_predictions.csv`, and `evaluation/`. With all nominal images and all six fitted models, the test table has 198,000 score rows. These are repeated evaluations of 11,000 test images, not 198,000 unique images. `report_results.py` checks model/seed/condition alignment and reports confusion counts, mean and SD across seeds, stratified bootstrap intervals and paired model comparisons.

The portable recovery archive includes code, configuration, manifest, audit, status, and available training checkpoints. Source images and public pretrained encoder weights can be downloaded again from the pinned sources. A recovery archive records only its snapshot; it does not update itself while the live run continues.
