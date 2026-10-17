"""Evaluate the unchanged three-seed checkpoints on the new test manifest.

No fitting, early stopping or threshold selection occurs in this script.
"""
import argparse
import csv
import gc
import hashlib
import io
import json
import platform
import time
from pathlib import Path

import clip
import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torchvision import transforms

HERE = Path(__file__).resolve().parent
SEEDS = (42, 43, 44)
CONDITIONS = ('original', 'jpeg65', 'resize112')
torch.set_num_threads(6)
torch.set_num_interop_threads(2)


def read_csv(path):
    return list(csv.DictReader(path.open()))


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def common_transform(mean, std):
    return transforms.Compose([
        transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.ToTensor(), transforms.Normalize(mean, std)])


def image_path(cache, image_id):
    for suffix in ['.bin', '.jpg', '.png', '.webp']:
        path = cache / (image_id + suffix)
        if path.is_file():
            return path
    raise FileNotFoundError(image_id)


def image_tensor(record, cache, condition, transform):
    with Image.open(image_path(cache, record['image_id'])) as source:
        image = source.convert('RGB')
    if condition == 'jpeg65':
        data = io.BytesIO()
        image.save(data, format='JPEG', quality=65)
        data.seek(0)
        with Image.open(data) as source:
            image = source.convert('RGB')
    if condition == 'resize112':
        image = image.resize((112, 112), Image.Resampling.BICUBIC)
    return transform(image)


def batches(records, cache, condition, transform):
    for start in range(0, len(records), 8):
        yield torch.stack([image_tensor(row, cache, condition, transform)
                           for row in records[start:start+8]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--checkpoints', type=Path, required=True)
    args = parser.parse_args()
    records = read_csv(HERE / 'manifest.csv')
    original = read_csv(HERE.parent / 'pilot/manifest.csv')
    original_scores = read_csv(HERE.parent / 'pilot/predictions.csv')
    old_ids = {r['image_id'] for r in original}
    old_hashes = {r['sha256'] for r in original}
    assert not old_ids.intersection(r['image_id'] for r in records)
    assert not old_hashes.intersection(r['sha256'] for r in records)
    for row in records:
        if hashlib.sha256(image_path(args.cache, row['image_id']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('New image hash mismatch: ' + row['image_id'])
    probes = [row for split in ['seen', 'unseen'] for label in ['0', '1']
              for row in [next(r for r in original if r['split'] == split and r['label'] == label)]]
    expected = {(r['model'], int(r['seed']), r['image_id']): float(r['score'])
                for r in original_scores if r['condition'] == 'original'}
    metadata = dict(started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        seeds=SEEDS, conditions=CONDITIONS, threshold=0.5, training_performed=False,
        validation_used_for_this_sample=False, python=platform.python_version(),
        torch=torch.__version__, torchvision=torchvision.__version__, numpy=np.__version__,
        pillow=Image.__version__, cpu_threads=6, batch_size=8,
        cpu=next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                 if line.startswith('model name')),
        manifest_sha256=hashlib.sha256((HERE/'manifest.csv').read_bytes()).hexdigest(),
        checkpoint_sha256={}, checkpoint_probe_max_absolute_error={})
    predictions = []
    started = time.perf_counter()
    for model_name in ['resnet50', 'clip_linear']:
        start_model = time.perf_counter()
        print('Loading', model_name, flush=True)
        if model_name == 'resnet50':
            transform = common_transform((.485, .456, .406), (.229, .224, .225))
            model = torchvision.models.resnet50(weights=None)
            model.fc = nn.Linear(model.fc.in_features, 1)
            for seed in SEEDS:
                path = args.checkpoints / f'{model_name}_seed{seed}_best.pt'
                metadata['checkpoint_sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
                model.eval()
                with torch.inference_mode():
                    score = model(next(batches(probes, args.checkpoints, 'original', transform))).flatten().sigmoid().numpy()
                error = max(abs(float(s)-expected[(model_name,seed,r['image_id'])]) for s,r in zip(score,probes))
                metadata['checkpoint_probe_max_absolute_error'][f'{model_name}_{seed}'] = error
                if error > 1e-4:
                    raise ValueError('Checkpoint does not reproduce original probe scores: ' + str(error))
                for condition in CONDITIONS:
                    with torch.inference_mode():
                        scores = torch.cat([model(batch).flatten().sigmoid()
                                            for batch in batches(records, args.cache, condition, transform)]).numpy()
                    predictions.extend(dict(image_id=r['image_id'], label=int(r['label']), generator=r['generator'],
                        split=r['split'], condition=condition, model=model_name, seed=seed, score=float(s))
                        for r,s in zip(records,scores))
                    write_csv(HERE/'predictions.csv', predictions)
                    print('Finished', model_name, seed, condition, len(scores), 'images', flush=True)
            del model
        else:
            transform = common_transform((.48145466,.4578275,.40821073), (.26862954,.26130258,.27577711))
            backbone, _ = clip.load('ViT-B/32', device='cpu', download_root=str(args.checkpoints/'weights'))
            backbone.float().eval()
            def features(rs, cache, condition):
                with torch.inference_mode():
                    f = torch.cat([backbone.encode_image(batch).float()
                                   for batch in batches(rs, cache, condition, transform)])
                    return f/f.norm(dim=1,keepdim=True)
            probe_features = features(probes, args.checkpoints, 'original')
            heads = {}
            for seed in SEEDS:
                path = args.checkpoints / f'{model_name}_seed{seed}_best.pt'
                metadata['checkpoint_sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                head = nn.Linear(512,1)
                head.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
                head.eval()
                with torch.inference_mode():
                    scores = head(probe_features).flatten().sigmoid().numpy()
                error = max(abs(float(s)-expected[(model_name,seed,r['image_id'])]) for s,r in zip(scores,probes))
                metadata['checkpoint_probe_max_absolute_error'][f'{model_name}_{seed}'] = error
                if error > 1e-4:
                    raise ValueError('CLIP checkpoint probe mismatch: ' + str(error))
                heads[seed] = head
            for condition in CONDITIONS:
                f = features(records,args.cache,condition)
                for seed,head in heads.items():
                    with torch.inference_mode():
                        scores = head(f).flatten().sigmoid().numpy()
                    predictions.extend(dict(image_id=r['image_id'], label=int(r['label']), generator=r['generator'],
                        split=r['split'], condition=condition, model=model_name, seed=seed, score=float(s))
                        for r,s in zip(records,scores))
                    print('Finished', model_name, seed, condition, len(scores), 'images', flush=True)
                write_csv(HERE/'predictions.csv', predictions)
            del backbone,heads,f
        gc.collect()
        metadata[model_name+'_evaluation_seconds'] = time.perf_counter()-start_model
    assert len(predictions) == len(records)*len(SEEDS)*len(CONDITIONS)*2
    metadata.update(completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                    new_unique_test_images=len(records), prediction_rows=len(predictions),
                    elapsed_seconds=time.perf_counter()-started)
    (HERE/'inference_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('EVALUATION COMPLETE',json.dumps(metadata),flush=True)


if __name__ == '__main__':
    main()
