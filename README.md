# AI-generated image detection

Afanasyev Kirill and Amangeldi Beksultan · AITU, BDA-2403.

ResNet-50 and a frozen CLIP encoder with a linear head, evaluated over seeds 42, 43 and 44. The later tests contain 400 real and 400 generated images each; Midjourney is held out. These exploratory tests were selected after the smaller pilot.

## Reproduce the results

Use Python 3.12:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce_tables.py
```

This verifies Tables 1–5 and all 11 numerical exports byte for byte from saved scores. No images or model weights are needed.

| Folder | Contents |
| --- | --- |
| `article/` | Current analysis, numerical exports and verification record |
| `tables/` | Current LaTeX tables |
| `pilot/` | Initial predictions, validation scores, training history and training scripts |
| `expanded_test/` | Later predictions, manifests, sampling audit and collection/inference scripts |
| `code/` | Shared metric calculations |

Images and fitted checkpoints are supplied separately. Retraining requires `requirements-pilot.txt` and the image cache; `pilot/run_pilot.py` writes per-seed runs, which `pilot/aggregate_runs.py` combines. The current article PDF and Overleaf source are delivered separately. Earlier reports remain in Git history.

Source: [Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage). `SOURCE_REVISION.json` records the evidence revisions. Native resolution, compression history and category were not matched; intervals condition on the fitted checkpoints. Neither model met every success target.
