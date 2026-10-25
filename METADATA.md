# Research metadata - Assignment 3

| Field | Details |
| --- | --- |
| Project/research title | Development of a System for Detecting AI-Generated Images Using Deep Learning Methods |
| Research team | Afanasyev Kirill and Amangeldi Beksultan; Big Data Analytics, BDA-2403 |
| Date of data collection | The report records access to the dataset mirror. Image creation dates are unavailable; |
| Place of data collection | Online, from the [Tiny-GenImage mirror on Hugging Face](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), revision `89c4fe9efd0e`. |
| Method of data collection | Secondary dataset sampling and download, with decoding checks and exact-file and decoded-pixel hash screening. Model predictions were then collected through computational experiments. |
| Documentation type | CSV image manifests and prediction scores; training and evaluation records; Python scripts; tables, figures and the research report. No interview recordings or transcripts form part of this experiment. |

## Dataset and experiment

| Item | Recorded information |
| --- | --- |
| Study type | Small-sample computational pilot; later test evaluation was exploratory. |
| Reported sample | 1,920 distinct images: 240 training, 80 validation, 800 seen-test and 800 unseen-test images. |
| Test composition | Each test has 400 real and 400 generated images. The seen test contains 200 BigGAN and 200 GLIDE images; the unseen test contains 400 Midjourney images. |
| Initial tests | Two earlier tests of 80 images each are retained separately and excluded from the 1,920-image total. Their scores are not pooled with the later tests. |
| Sampling | The initial tests used the first 600 mirror validation rows. After viewing those results, the later tests were drawn from the full 7,000-row frame with sampling seed `20261017`. |
| Exclusions and unused records | All 480 initial-pilot IDs and matching file/pixel hashes were excluded from later sampling. Of 460 eligible Midjourney rows, 400 were selected; the other 60 remained eligible but unused. All 1,600 later images downloaded and decoded successfully. |
| Models | Fine-tuned ResNet-50 and frozen CLIP ViT-B/32 with a trained linear classifier. |
| Training seeds | `42`, `43`, `44`; the same development splits were used for each seed. |
| Test conditions | Original images, JPEG quality 65 and independent downsampling to 112 × 112 pixels; primary decision threshold `0.5`. |
| Hardware | AMD EPYC 9V74 CPU, six PyTorch threads, 8 GiB container; no GPU. The earlier Intel run is excluded; that exclusion was not prespecified. |

Native resolution, compression history and category were not matched. Perceptual duplicate screening and the official GenImage archive audit remain incomplete. The 20,000-image matched study is planned work.

## Report and repository records

Repository: [C0nflu3nc3/RMT](https://github.com/C0nflu3nc3/RMT). The report identifies `6dc0d1027d60` as the test-evidence revision.

The report describes score reproduction with `python reproduce_tables.py`, covering Tables 1-5 and 11 numerical exports. This metadata file records the report's information; it does not represent a new training or reproduction run.

SHA-256 of the source PDF:

```text
69e19e062735253d35c37a60c52f61ac5c5512ea9402885e641d26858e8285b7
```
