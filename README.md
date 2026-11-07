# AI-generated image detection

Afanasyev Kirill and Amangeldi Beksultan · Astana IT University, BDA-2403.

[Paper](article/manuscript.pdf) · [LaTeX source](article/manuscript.tex) · [Citation](CITATION.cff)

This study compares ResNet-50 with a linear classifier on frozen CLIP ViT-B/32 features using 34,998 deduplicated Tiny-GenImage images. Midjourney is held out from training and validation. Both models use three training seeds. The follow-up evaluates ResNet-50 after 40 total epochs on the same test images.

## Reproduce the results

With Python 3.12, run from the repository root:

```bash
python -m pip install -r requirements-analysis.txt
python experiments/resnet40/reproduce.py
python reproduce_tables.py
```

The first command recomputes the follow-up statistics from the public grouped evidence and rebuilds its tables and figures. The second verifies the archived one-epoch baseline.

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
- [experiments/resnet40/](experiments/resnet40/): 40-epoch results, training histories, tables and figures.
- [tables/](tables/): archived baseline tables.

## Data and limitations

Dataset: [Tiny-GenImage, pinned revision](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage/tree/89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69). Images, feature caches and trained weights are excluded from Git.

The baseline used one ResNet epoch and up to 40 CLIP-head epochs on CPU. The ResNet follow-up initializes a new Adam optimizer from the epoch-1 weights and uses a continuation script with CUDA as its default. The comparison covers one unseen generator. The mirror includes earlier pilot content and differences in source characteristics. Confidence intervals apply to the evaluated checkpoints.

Code: [MIT](LICENSE). Dataset and pretrained-model licences apply separately.
