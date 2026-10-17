"""Small CPU feasibility pilot on the public Tiny-GenImage mirror.

This deliberately uses BigGAN and GLIDE for development and Midjourney only
for testing. It is not the native-size/JPEG-matched full GenImage experiment.
The 480 downloaded images are recorded by mirror row, SHA256 and dimensions.
"""
import argparse, csv, hashlib, io, json, os, platform, random, time, urllib.parse, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import clip
import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from torchvision import transforms
from sklearn.metrics import f1_score

torch.set_num_threads(6)
torch.set_num_interop_threads(2)
SOURCE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed', type=int, choices=[42,43,44], default=42)
parser.add_argument('--offline', action='store_true', help='Use the fixed manifest and hash-verified cached images; no dataset API calls.')
parser.add_argument('--manifest', type=Path, default=SOURCE/'manifest.csv')
parser.add_argument('--out', type=Path)
args=parser.parse_args()
random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
ROOT = args.out or SOURCE/'runs'/f'seed{args.seed}'
WORK = Path(os.environ.get('PILOT_WORK', str(SOURCE/'cache')))
WORK.mkdir(parents=True, exist_ok=True)
ROOT.mkdir(parents=True, exist_ok=True)
NAMES = {0:'real',2:'BigGAN',3:'GLIDE',4:'Midjourney'}
DATASET = 'TheKernel01/Tiny-GenImage'

def url_json(url):
    with urllib.request.urlopen(url, timeout=40) as r:return json.load(r)

def rows_page(split, offset):
    q=urllib.parse.urlencode(dict(dataset=DATASET,config='default',split=split,offset=offset,length=100))
    for attempt in range(3):
        try:return [(split,x) for x in url_json('https://datasets-server.huggingface.co/rows?'+q)['rows']]
        except Exception:
            if attempt==2:raise

def get_image(item):
    split, x=item; row=x['row']; image_id=f"tiny_{split}_{x['row_idx']}"
    path=WORK/(image_id+'.bin')
    if path.exists():data=path.read_bytes()
    else:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(row['image']['src'],timeout=35) as r:data=r.read()
                path.write_bytes(data);break
            except Exception:
                if attempt==2:raise
    with Image.open(io.BytesIO(data)) as im:
        im.load();size=im.size;fmt=im.format
    return dict(image_id=image_id,mirror_split=split,row_idx=x['row_idx'],label=row['label'],
                generator=NAMES[row['generator']],width=size[0],height=size[1],codec=fmt,
                sha256=hashlib.sha256(data).hexdigest(),path=str(path),split=x['study_split'])

def csv_write(path, rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

started=time.perf_counter()
if args.offline:
    with args.manifest.open(newline='') as handle: records=list(csv.DictReader(handle))
    for record in records:
        for key in ['row_idx','label','width','height']:record[key]=int(record[key])
        path=WORK/(record['image_id']+'.bin')
        if not path.is_file():raise FileNotFoundError(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Image hash mismatch: '+record['image_id'])
        with Image.open(path) as im:im.load()
        record['path']=str(path)
    records.sort(key=lambda r:r['image_id']);duplicates=set();selected=records
    print('Offline manifest verified',len(records),'images',flush=True)
else:
    with ThreadPoolExecutor(12) as pool:
        jobs=[pool.submit(rows_page,s,o) for s,n in [('train',1200),('validation',600)] for o in range(0,n,100)]
        candidates=[item for f in as_completed(jobs) for item in f.result()]
    print('Candidate rows retrieved',len(candidates),flush=True)
    selected=[]
    rng=random.Random(42)
    for mirror_split, targets in [('train',[('train',{0:120,2:60,3:60}),('validation',{0:40,2:20,3:20})]),
                                 ('validation',[('seen',{0:40,2:20,3:20}),('unseen',{0:40,4:40})])]:
        pools={g:sorted([x for s,x in candidates if s==mirror_split and x['row']['generator']==g],key=lambda z:z['row_idx']) for g in NAMES}
        for values in pools.values():rng.shuffle(values)
        for split, counts in targets:
            for generator,count in counts.items():
                if len(pools[generator])<count:raise ValueError(f'Not enough {mirror_split} {generator}: {len(pools[generator])}')
                for x in pools[generator][:count]:
                    x['study_split']=split;selected.append((mirror_split,x))
                pools[generator]=pools[generator][count:]
    records=[]
    with ThreadPoolExecutor(24) as pool:
        jobs=[pool.submit(get_image,x) for x in selected]
        for f in as_completed(jobs):
            records.append(f.result())
            if len(records)%40==0:print('Images downloaded',len(records),flush=True)
    records.sort(key=lambda r:r['image_id'])
    hash_counts=Counter(r['sha256'] for r in records)
    duplicates={h for h,n in hash_counts.items() if n>1}
    if duplicates:
        print('Removing all exact duplicate groups',len(duplicates),flush=True)
        records=[r for r in records if r['sha256'] not in duplicates]
csv_write(ROOT/'manifest.csv',[{k:v for k,v in r.items() if k!='path'} for r in records])
print('Final pilot counts',dict(Counter(r['split'] for r in records)),flush=True)
download_seconds=time.perf_counter()-started

def image_for(r,condition):
    with Image.open(r['path']) as im:im=im.convert('RGB')
    if condition=='jpeg65':
        b=io.BytesIO();im.save(b,format='JPEG',quality=65);b.seek(0)
        with Image.open(b) as decoded:im=decoded.convert('RGB')
    if condition=='resize112':im=im.resize((112,112),Image.Resampling.BICUBIC)
    return im

def common_transform(mean,std):
    return transforms.Compose([transforms.Resize((224,224),interpolation=transforms.InterpolationMode.BICUBIC),
                               transforms.ToTensor(),transforms.Normalize(mean,std)])

def tensor_data(rs,condition,transform):
    return torch.stack([transform(image_for(r,condition)) for r in rs]),torch.tensor([r['label'] for r in rs],dtype=torch.float32)

parts={s:[r for r in records if r['split']==s] for s in ['train','validation','seen','unseen']}
predictions=[];val_predictions=[];timings={};latencies={};histories={}
model_load_seconds={}
for name in ['resnet50','clip_linear']:
    t=time.perf_counter();print('Loading',name,flush=True)
    if name=='resnet50':
        model=torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.IMAGENET1K_V1)
        model.fc=nn.Linear(model.fc.in_features,1)
        transform=common_transform((.485,.456,.406),(.229,.224,.225))
        backbone=None
    else:
        backbone,_=clip.load('ViT-B/32',device='cpu',download_root=str(WORK/'weights'))
        backbone.float().eval()
        for p in backbone.parameters():p.requires_grad=False
        model=nn.Linear(512,1)
        transform=common_transform((.48145466,.4578275,.40821073),(.26862954,.26130258,.27577711))
    model_load_seconds[name]=time.perf_counter()-t
    t=time.perf_counter()
    x,y=tensor_data(parts['train'],'original',transform)
    vx,vy=tensor_data(parts['validation'],'original',transform)
    def embeddings(z):
        with torch.inference_mode():
            f=torch.cat([backbone.encode_image(batch) for batch in z.split(8)]).float()
            return f/f.norm(dim=1,keepdim=True)
    if backbone is not None:
        x=embeddings(x);vx=embeddings(vx)
    loader=DataLoader(TensorDataset(x,y),batch_size=8 if backbone is None else 32,shuffle=True,
                      generator=torch.Generator().manual_seed(args.seed))
    optim=torch.optim.Adam(model.parameters(),lr=1e-4 if backbone is None else 1e-3)
    loss_fn=nn.BCEWithLogitsLoss()
    history=[];best=-1
    epochs=1 if backbone is None else 40
    for epoch in range(epochs):
        model.train();total=0
        for bx,by in loader:
            optim.zero_grad();loss=loss_fn(model(bx).flatten(),by);loss.backward();optim.step();total+=float(loss.detach())*len(by)
        model.eval()
        with torch.inference_mode():vs=torch.cat([model(batch).flatten().sigmoid() for batch in vx.split(8)]).numpy()
        vf=f1_score(vy.numpy(),vs>=.5,zero_division=0)
        history.append({'epoch':epoch+1,'loss':total/len(y),'validation_f1':float(vf)})
        if vf>best:
            best=vf;torch.save(model.state_dict(),WORK/(name+f'_seed{args.seed}_best.pt'))
        if epoch%10==0 or epoch+1==epochs:print(name,'epoch',epoch+1,'val F1',float(vf),flush=True)
    timings[name]=time.perf_counter()-t
    model.load_state_dict(torch.load(WORK/(name+f'_seed{args.seed}_best.pt'),weights_only=True));model.eval()
    with torch.inference_mode():vs=torch.cat([model(batch).flatten().sigmoid() for batch in vx.split(8)]).numpy()
    for r,score in zip(parts['validation'],vs):
        val_predictions.append(dict(image_id=r['image_id'],label=r['label'],generator=r['generator'],split='validation',condition='original',model=name,seed=args.seed,score=float(score)))
    for split in ['seen','unseen']:
        for condition in ['original','jpeg65','resize112']:
            tx,ty=tensor_data(parts[split],condition,transform)
            if backbone is not None:tx=embeddings(tx)
            with torch.inference_mode():scores=torch.cat([model(batch).flatten().sigmoid() for batch in tx.split(8)]).numpy()
            for r,score in zip(parts[split],scores):
                predictions.append(dict(image_id=r['image_id'],label=r['label'],generator=r['generator'],split=split,condition=condition,model=name,seed=args.seed,score=float(score)))
            print(name,split,condition,'F1',float(f1_score(ty.numpy(),scores>=.5,zero_division=0)),flush=True)
    sample=transform(image_for(parts['seen'][0],'original')).unsqueeze(0)
    def predict_one():
        with torch.inference_mode():
            if backbone is not None:
                f=backbone.encode_image(sample).float();f=f/f.norm(dim=1,keepdim=True);return model(f).sigmoid()
            return model(sample).sigmoid()
    for _ in range(5):predict_one()
    elapsed=[]
    for _ in range(20):
        t=time.perf_counter();predict_one();elapsed.append((time.perf_counter()-t)*1000)
    latencies[name]=float(np.median(elapsed))
    histories[name]=history
    del x,vx,model,backbone
    import gc;gc.collect()
csv_write(ROOT/'predictions.csv',predictions);csv_write(ROOT/'validation_predictions.csv',val_predictions)
baseline=json.loads((SOURCE/'runs/seed42/run_metadata.json').read_text()) if (SOURCE/'runs/seed42/run_metadata.json').exists() else {}
meta=dict(dataset=DATASET,dataset_revision=baseline.get('dataset_revision') if args.offline else url_json('https://huggingface.co/api/datasets/'+DATASET).get('sha'),
          accessed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),seed=args.seed,sampling_seed=42,
          image_access_mode='offline verified cache' if args.offline else 'online row API',
          input_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest() if args.manifest.exists() else None,
          python=platform.python_version(),torch=torch.__version__,torchvision=torchvision.__version__,
          numpy=np.__version__,pillow=Image.__version__,platform=platform.platform(),
          cpu=next(s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),
          cpu_threads=6,cuda_available=torch.cuda.is_available(),container_memory_gib=8,
          epochs={'resnet50':1,'clip_linear':40},batch_sizes={'resnet50':8,'clip_linear':32},
          learning_rates={'resnet50':1e-4,'clip_linear':1e-3},
          counts=dict(Counter(r['split'] for r in records)),removed_duplicate_groups=len(duplicates),
          removed_duplicate_images=len(selected)-len(records),download_seconds=download_seconds,
          model_load_seconds=model_load_seconds,training_including_preparation_seconds=timings,
          forward_median_ms_per_image=latencies,total_seconds=time.perf_counter()-started,
          limitations=['mirror subset, not official archive audit','BigGAN and GLIDE development only',
                       'no native-size or JPEG matching','one run; aggregated with other training seeds separately','no perceptual duplicate or category audit'])
(ROOT/'run_metadata.json').write_text(json.dumps(meta,indent=2))
(ROOT/'training_history.json').write_text(json.dumps(histories,indent=2))
print('PILOT COMPLETE',json.dumps(meta),flush=True)
