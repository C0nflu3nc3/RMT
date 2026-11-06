# AI-generated image detection

Afanasyev Kirill and Amangeldi Beksultan · Astana IT University, BDA-2403.

[Paper](article/manuscript.pdf) · [LaTeX source](article/manuscript.tex) · [Citation](CITATION.cff)

This study compares ResNet-50 with a linear classifier on frozen CLIP ViT-B/32 features using 34,998 deduplicated Tiny-GenImage images. Midjourney is held out from training and validation. Both models use three training seeds.

## Reproduce the results

With Python 3.12, run from the repository root:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce_tables.py
```

This rebuilds and checks the paper outputs from saved scores without images, trained weights or a GPU.

## Retrain the models

Use a separate environment:

```bash
cd experiments/full35k
python -m pip install -r requirements.txt
bash run.sh
```

The scripts download the pinned dataset and pretrained weights. For CUDA, use a CUDA-enabled PyTorch environment, install `requirements_cuda_extra.txt` and run `python train_cuda.py --require-cuda` after collecting the data.

## Main files

- [article/](article/): paper and LaTeX source.
- [experiments/full35k/](experiments/full35k/): training code, dataset splits, saved predictions and evaluation outputs.
- [tables/](tables/): LaTeX result tables.

## Data and limitations

Dataset: [Tiny-GenImage, pinned revision](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage/tree/89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69). Images, feature caches and trained weights are excluded from Git.

Reported training used CPU only, with one ResNet epoch and 40 CLIP-head epochs. The study is exploratory: one unseen generator, reused pilot content and unmatched source characteristics. Confidence intervals apply to the selected checkpoints.

Code: [MIT](LICENSE). Dataset and pretrained-model licences apply separately.
