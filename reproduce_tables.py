"""Recreate Tables 2-5 from saved scores without GitHub, images or model weights."""
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
PROJECT=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='rmt-reproduce-') as directory:
    copy=Path(directory)/'project'
    shutil.copytree(PROJECT,copy,ignore=shutil.ignore_patterns('.git','cache','__pycache__','*.pt','*.pth','main.pdf','exports'))
    # Existing example JPEGs are sufficient for the illustrative figure.
    environment=os.environ.copy();environment.pop('PILOT_WORK',None)
    subprocess.run([sys.executable,str(copy/'pilot/analyze_pilot.py')],env=environment,check=True,stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable,str(copy/'pilot/write_tables.py')],env=environment,check=True,stdout=subprocess.DEVNULL)
    results={}
    for number,filename in [(2,'main_results.tex'),(3,'paired.tex'),(4,'robustness.tex'),(5,'sensitivity.tex')]:
        expected=(PROJECT/'tables'/filename).read_bytes();actual=(copy/'tables'/filename).read_bytes()
        if actual!=expected:raise SystemExit(f'Table {number}: reproduction mismatch')
        results[str(number)]={'status':'exact match','sha256':hashlib.sha256(actual).hexdigest()}
        print(f'Table {number}: exact match')
    (PROJECT/'pilot/reproduction_check.json').write_text(json.dumps({'method':'Regenerated from saved prediction/validation CSVs in an isolated temporary copy; no dataset or GitHub calls','tables':results},indent=2)+'\n')
print('Tables 2-5 reproduced successfully. Original exports were left unchanged.')
