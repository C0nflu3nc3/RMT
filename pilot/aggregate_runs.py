"""Combine real training runs on the same fixed 480-image manifest."""
import csv,json
from pathlib import Path
P=Path(__file__).resolve().parent
seeds=(42,43,44)
read=lambda path:list(csv.DictReader(path.open()))
def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for seed in seeds:
    r=P/'runs'/f'seed{seed}'
    if seed!=42 and (r/'manifest.csv').read_bytes()!=(P/'manifest.csv').read_bytes():
        raise ValueError('Manifest changed across training seeds')
for filename in ['predictions.csv','validation_predictions.csv']:
    combined=[]
    for seed in seeds:
        rows=read(P/'runs'/f'seed{seed}'/filename)
        if {int(x['seed']) for x in rows}!={seed}:raise ValueError('Wrong seed label')
        combined.extend(rows)
    write(P/filename,combined)
runs={str(seed):json.loads((P/'runs'/f'seed{seed}'/'run_metadata.json').read_text()) for seed in seeds}
meta={k:v for k,v in runs['42'].items() if k not in ['seed','download_seconds','model_load_seconds','training_including_preparation_seconds','forward_median_ms_per_image','total_seconds','limitations']}
meta.update(training_seeds=list(seeds),sampling_seed=42,per_seed=runs,
            limitations=['mirror subset, not official archive audit','BigGAN and GLIDE development only','no native-size or JPEG matching','no perceptual duplicate or category audit','three training seeds on one fixed small image subset'])
(P/'run_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
histories={str(seed):json.loads((P/'runs'/f'seed{seed}'/'training_history.json').read_text()) for seed in seeds}
(P/'training_history.json').write_text(json.dumps(histories,indent=2)+'\n')
print('Combined seeds',seeds,'on the same 480 images. Test prediction rows:',len(read(P/'predictions.csv')))
