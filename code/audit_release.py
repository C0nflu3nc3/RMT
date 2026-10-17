"""Count actual image files in extracted GenImage generator/train|val/ai|nature folders.

Run this on the full release before asserting that matched split targets are feasible.
This counts readable headers only; matching, perceptual duplicates and labels still
require the study manifest. It does not infer counts from the published paper.
"""
import argparse,csv,hashlib
from collections import Counter
from pathlib import Path
from PIL import Image

def audit(root,out):
    rows=[];counts=Counter()
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.bmp'}:continue
        parts=path.relative_to(root).parts
        split=next((v for v in parts if v in {'train','val'}),None)
        kind=next((v for v in parts if v in {'ai','nature'}),None)
        if split is None or kind is None:continue
        generator=parts[0];valid=True
        try:
            with Image.open(path) as im:
                width,height=im.size;codec=im.format
                tables=str(getattr(im,'quantization',None))
                im.verify()
        except Exception:
            valid=False;width=height=None;codec='invalid';tables=''
        counts[(generator,split,kind,'valid' if valid else 'invalid')]+=1
        rows.append(dict(path=str(path.relative_to(root)),generator=generator,partition=split,label_folder=kind,
                         width=width,height=height,codec=codec,valid=valid,
                         jpeg_tables_sha256=hashlib.sha256(tables.encode()).hexdigest() if tables else ''))
    out.mkdir(parents=True,exist_ok=True)
    with (out/'release_file_audit.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['path']);w.writeheader();w.writerows(rows)
    with (out/'release_counts.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['generator','partition','label_folder','status','count'])
        for key,n in sorted(counts.items()):w.writerow([*key,n])
    print('Counted',len(rows),'image files; these counts precede duplicate filtering and matching.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path,default=Path('release_audit'))
    a=p.parse_args();audit(a.root,a.out)
