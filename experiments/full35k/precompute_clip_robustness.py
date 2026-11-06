"""Precompute robustness features with the unmodified experiment transforms."""
import csv
import hashlib
import json
import time

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
    with (HERE / 'manifest.csv').open(newline='') as handle:
        all_rows = list(csv.DictReader(handle))
    model, _ = clip.load('ViT-B/32', device='cpu', download_root=str(cache / 'weights'))
    model.float().eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    directory = cache / 'features'
    directory.mkdir(exist_ok=True)
    metadata = {'device': 'cpu', 'threads': 2, 'amp_bfloat16': True, 'torch': torch.__version__,
                'manifest_sha256': manifest_hash, 'config_sha256': config_hash,
                'batch_size': 16, 'groups': [], 'complete': False}
    for split in ('seen', 'unseen'):
        rows = [r for r in all_rows if r['split'] == split]
        for condition in ('jpeg65', 'resize112'):
            key = hashlib.sha256((manifest_hash + config_hash + condition + '|'.join(r['image_id'] for r in rows)).encode()).hexdigest()
            path = directory / (key + '.npy')
            state_path = path.with_suffix('.json')
            cursor = 0
            if state_path.exists():
                state = json.loads(state_path.read_text())
                assert state['manifest_sha256'] == manifest_hash and state['config_sha256'] == config_hash
                cursor = state['cursor']
            if cursor < len(rows):
                features = np.lib.format.open_memmap(path, mode='r+' if path.exists() else 'w+', dtype='float32', shape=(len(rows), 512))
                dataset = Images(rows[cursor:], cache, transform_for('clip_linear'), condition)
                started = time.monotonic()
                print('ROBUSTNESS START', split, condition, cursor, '/', len(rows), flush=True)
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
                            atomic_json(HERE / 'clip_robustness_status.json', dict(split=split, condition=condition, completed=cursor, total=len(rows), elapsed_seconds=time.monotonic()-started))
                            print('ROBUSTNESS FEATURES', split, condition, cursor, '/', len(rows), flush=True)
                del features
            metadata['groups'].append(dict(split=split, condition=condition, images=len(rows), feature_file=path.name, feature_sha256=sha_file(path)))
            atomic_json(HERE / 'clip_robustness_precompute.json', metadata)
    metadata['complete'] = True
    atomic_json(HERE / 'clip_robustness_precompute.json', metadata)
    print('ROBUSTNESS FEATURE PRECOMPUTE COMPLETE', flush=True)


if __name__ == '__main__':
    main()
