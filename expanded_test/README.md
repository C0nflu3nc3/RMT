# Expanded held-out test sample

This extension addresses the original pilot's small tests. It keeps the original article and its 480-image evidence intact. The new test is reported separately because it was collected after inspecting the first pilot.

## Selection

The source is [TheKernel01/Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), revision `89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69`. The collection script audits all 7,000 validation metadata rows and shuffles each source pool with sampling seed 20261017. Selection never uses model predictions.

The intended sample is 400 real and 400 generated images per test. Seen generated images are 200 BigGAN and 200 GLIDE images; unseen generated images are 400 Midjourney images. The two tests have different real images. Exact file and decoded-RGB pixel hashes exclude the entire original pilot and repeated new images. Accepted counts and any failed or removed candidates are recorded in `sample_audit.json`.

We chose 400 per class before running inference: this is ten times the original 40, and it fits within the 460 unused Midjourney validation rows after excluding the original 40. The remaining 60 Midjourney rows allow backfilling after failed downloads or duplicate checks.

`manifest.csv` records every source row, binary label, generator, dimensions, codec, JPEG-table hash, file SHA256 and decoded-pixel SHA256. A JPEG-table hash is an audit descriptor; it does not mean compression was matched.

## Collect the images

From the repository root, with Pillow installed and the original 480-image cache available:

```bash
python expanded_test/collect_samples.py --cache /path/to/new-cache --original-cache /path/to/original-cache --per-class 400
```

The source row service may throttle requests. Metadata pages and downloaded images are cached; retrying reuses them. The script checks the dataset revision before using current rows. Downloaded file hashes must match the supplied manifest before treating a later download as a reproduction.

The separately supplied reproduction ZIP includes the six fitted checkpoints and the four original image probes. The public CLIP backbone is downloaded on first inference unless its weights are already cached.

The separately supplied samples ZIP contains the original downloaded image bytes with normal image extensions. No image is resized or re-encoded for that bundle. Its `SHA256SUMS.txt` covers every archived image and manifest.

## Evaluate unchanged checkpoints

Install `requirements-pilot.txt` from the repository root. With the six existing seed-specific checkpoints and the cached CLIP backbone weights:

```bash
python expanded_test/evaluate_saved.py --cache /path/to/new-cache --checkpoints /path/to/original-cache
```

For an extracted samples ZIP, `--cache` can point to its `images` directory. The checkpoint directory must also contain the four original image IDs used by the score probes. The script records the checkpoint file hashes and compares predictions on those original images with the archived scores before evaluating the new sample. It does not fit models, select epochs or choose thresholds. The threshold stays 0.5. CLIP embeddings are shared across its three unchanged linear heads.

## Reproduce statistics from scores

Install `requirements-analysis.txt` and run:

```bash
python expanded_test/analyze.py
python expanded_test/analyze.py --check
```

This needs the saved prediction CSV and manifest, the original pilot manifest and `code/report_results.py`. It requires no image download, model weights or PyTorch. It regenerates per-run counts and metrics, across-seed means/SDs, 1,000 paired image-bootstrap intervals, 9,999 paired permutations and the condition figure. Bootstrap intervals condition on the three fitted checkpoint pairs. The original-unseen comparison is primary within this extension; other p-values are descriptive and unadjusted. The extension was not registered as a new confirmatory study.

## Scope

More images improve test precision. This sample still does not match native size, compression history or category, and exact/pixel checks cannot exclude all near-duplicates. Midjourney remains the only unseen generator. Three repeated training seeds do not increase the number of independent images.

Image source and labels: TheKernel01/Tiny-GenImage, derived from the Tiny-GenImage mirror linked in its dataset card. Dataset images retain the upstream [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) terms. No new rights are assigned to third-party images or model weights.
