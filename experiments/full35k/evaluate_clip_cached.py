"""Score fitted CLIP heads on complete, provenance-checked feature caches."""
import csv
import hashlib
import json

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import TensorDataset

from collect import atomic_json, sha_file, write_csv
from train import HERE, CONFIG, loader


def main():
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    manifest_hash, config_hash = sha_file(HERE/'manifest.csv'), sha_file(HERE/'config.json')
    with (HERE/'manifest.csv').open(newline='') as handle:
        all_rows = list(csv.DictReader(handle))
    completed = []
    for split in ('seen','unseen'):
        records = [r for r in all_rows if r['split']==split]
        for condition in CONFIG['conditions']:
            feature_rows = all_rows if condition=='original' else records
            key = hashlib.sha256((manifest_hash+config_hash+condition+'|'.join(r['image_id'] for r in feature_rows)).encode()).hexdigest()
            path = HERE/'cache/features'/(key+'.npy')
            state_path = path.with_suffix('.json')
            if not state_path.exists():
                continue
            state = json.loads(state_path.read_text())
            assert state['manifest_sha256']==manifest_hash and state['config_sha256']==config_hash
            if state['cursor'] != len(feature_rows):
                continue
            x = torch.from_numpy(np.load(path).copy())
            if condition=='original':
                x = x[[i for i,r in enumerate(all_rows) if r['split']==split]]
            y = torch.tensor([float(r['label']) for r in records])
            dataset = TensorDataset(x,y)
            for seed in CONFIG['training_seeds']:
                directory=HERE/'artifacts/clip_linear'/f'seed{seed}'
                target=directory/f'{split}_{condition}.csv'
                if target.exists():
                    continue
                saved=torch.load(directory/'last.pt',map_location='cpu',weights_only=False)
                assert saved['epoch']==CONFIG['models']['clip_linear']['epochs']
                assert saved['manifest_sha256']==manifest_hash and saved['config_sha256']==config_hash
                del saved
                model=nn.Linear(512,1)
                model.load_state_dict(torch.load(directory/'best.pt',map_location='cpu',weights_only=True))
                model.eval()
                scores=[]
                with torch.inference_mode():
                    for batch,_ in loader(dataset,32,0):
                        scores.extend(model(batch).flatten().float().sigmoid().numpy().tolist())
                assert len(scores)==len(records) and np.isfinite(scores).all()
                output=[dict(image_id=r['image_id'],label=r['label'],generator=r['generator'],split=split,
                             condition=condition,model='clip_linear',seed=seed,score=float(score))
                        for r,score in zip(records,scores)]
                write_csv(target,output)
                metric=float(f1_score(y.numpy(),np.asarray(scores)>=.5,zero_division=0))
                completed.append(dict(seed=seed,split=split,condition=condition,n=len(scores),f1=metric))
                print('CLIP CACHED EVALUATION',completed[-1],flush=True)
    atomic_json(HERE/'clip_cached_evaluation_last.json',dict(device='cpu',threads=1,manifest_sha256=manifest_hash,config_sha256=config_hash,groups_written=completed))


if __name__=='__main__':
    main()
