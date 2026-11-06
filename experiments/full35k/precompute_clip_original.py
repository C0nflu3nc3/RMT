"""Cache original CLIP features using the unchanged train.py preprocessing."""
import csv
import hashlib
import json
import time
from pathlib import Path

import clip
import numpy as np
import torch

from collect import atomic_json, sha_file
from train import HERE, Images, transform_for, loader


def main():
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    cache = (HERE / 'cache').resolve()
    manifest_hash, config_hash = sha_file(HERE / 'manifest.csv'), sha_file(HERE / 'config.json')
    with (HERE / 'manifest.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    condition = 'original'
    key = hashlib.sha256((manifest_hash + config_hash + condition + '|'.join(r['image_id'] for r in rows)).encode()).hexdigest()
    directory = cache / 'features'
    directory.mkdir(exist_ok=True)
    path = directory / (key + '.npy')
    state_path = path.with_suffix('.json')
    cursor = 0
    if state_path.exists():
        state = json.loads(state_path.read_text())
        assert state['manifest_sha256'] == manifest_hash and state['config_sha256'] == config_hash
        cursor = state['cursor']
    if cursor == len(rows):
        print('ORIGINAL FEATURES ALREADY COMPLETE', cursor, flush=True)
        return
    model, _ = clip.load('ViT-B/32', device='cpu', download_root=str(cache / 'weights'))
    model.float().eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    features = np.lib.format.open_memmap(path, mode='r+' if path.exists() else 'w+', dtype='float32', shape=(len(rows), 512))
    started = time.monotonic()
    dataset = Images(rows[cursor:], cache, transform_for('clip_linear'), condition)
    metadata = dict(device='cpu', threads=2, amp_bfloat16=True, torch=torch.__version__, condition=condition,
                    manifest_sha256=manifest_hash, config_sha256=config_hash, feature_file=path.name,
                    started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), batch_size=16,
                    note='Frozen encoder precomputed alongside ResNet; preprocessing and cache keys match train.py.')
    atomic_json(HERE / 'clip_feature_precompute.json', metadata)
    print('PRECOMPUTE START', cursor, '/', len(rows), flush=True)
    with torch.inference_mode():
        for x, _ in loader(dataset, 16, 0):
            with torch.autocast('cpu', dtype=torch.bfloat16):
                encoded = model.encode_image(x).float()
            encoded = encoded / encoded.norm(dim=1, keepdim=True)
            n = len(x)
            features[cursor:cursor+n] = encoded.numpy()
            cursor += n
            if cursor % 512 == 0 or cursor == len(rows):
                features.flush()
                atomic_json(state_path, dict(cursor=cursor, manifest_sha256=manifest_hash, config_sha256=config_hash))
                atomic_json(HERE / 'clip_precompute_status.json', dict(completed=cursor, total=len(rows), elapsed_seconds=time.monotonic()-started))
                print('ORIGINAL CLIP FEATURES', cursor, '/', len(rows), flush=True)
    metadata.update(completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), elapsed_seconds=time.monotonic()-started,
                    complete=True, images=len(rows), feature_sha256=sha_file(path))
    atomic_json(HERE / 'clip_feature_precompute.json', metadata)
    print('ORIGINAL FEATURE PRECOMPUTE COMPLETE', cursor, flush=True)


if __name__ == '__main__':
    main()
