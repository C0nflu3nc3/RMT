"""Use spare CPU threads for two remaining test groups; publish complete CSVs only."""
import csv
import json
import os
import time

import numpy as np
import torch
import torchvision
from torch import nn
from sklearn.metrics import f1_score

from collect import atomic_json, sha_file, write_csv
from train import HERE, Images, transform_for, loader


def main():
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    mh,ch=sha_file(HERE/'manifest.csv'),sha_file(HERE/'config.json')
    directory=HERE/'artifacts/resnet50/seed44'
    saved=torch.load(directory/'last.pt',map_location='cpu',weights_only=False)
    assert saved['epoch']==1 and saved['cursor']==0
    assert saved['manifest_sha256']==mh and saved['config_sha256']==ch
    del saved
    model=torchvision.models.resnet50(weights=None)
    model.fc=nn.Linear(model.fc.in_features,1)
    model.load_state_dict(torch.load(directory/'best.pt',map_location='cpu',weights_only=True))
    model.to(memory_format=torch.channels_last).eval()
    with (HERE/'manifest.csv').open(newline='') as handle:
        rows=[r for r in csv.DictReader(handle) if r['split']=='unseen']
    output_dir=HERE/'precomputed_predictions'
    output_dir.mkdir(exist_ok=True)
    groups=[]
    for condition in ('original','resize112'):
        target=directory/f'unseen_{condition}.csv'
        if target.exists():
            continue
        scores=[]
        dataset=Images(rows,HERE/'cache',transform_for('resnet50'),condition)
        for index,(x,_) in enumerate(loader(dataset,16,0)):
            with torch.inference_mode(),torch.autocast('cpu',dtype=torch.bfloat16):
                logits=model(x.contiguous(memory_format=torch.channels_last)).flatten()
            scores.extend(logits.float().sigmoid().numpy().tolist())
            if index%64==0:
                print('RESNET PRECOMPUTE',condition,len(scores),'/',len(rows),flush=True)
        assert len(scores)==len(rows) and np.isfinite(scores).all()
        output=[dict(image_id=r['image_id'],label=r['label'],generator=r['generator'],split='unseen',
                     condition=condition,model='resnet50',seed=44,score=float(s)) for r,s in zip(rows,scores)]
        candidate=output_dir/f'resnet50_seed44_unseen_{condition}.csv'
        write_csv(candidate,output)
        published=True
        try:
            os.link(candidate,target)
        except FileExistsError:
            published=False
        metric=float(f1_score([int(r['label']) for r in rows],np.asarray(scores)>=.5,zero_division=0))
        group=dict(condition=condition,n=len(scores),f1=metric,published=published,candidate_sha256=sha_file(candidate))
        groups.append(group)
        atomic_json(HERE/'resnet_evaluation_precompute.json',dict(device='cpu',threads=2,amp_bfloat16=True,
                    manifest_sha256=mh,config_sha256=ch,groups=groups))
        print('RESNET PRECOMPUTE COMPLETE',json.dumps(group),flush=True)
    print('RESNET EVALUATION PRECOMPUTE FINISHED',flush=True)


if __name__=='__main__':
    main()
