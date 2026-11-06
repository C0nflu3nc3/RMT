"""Rebuild the completed 35k experiment's published outputs from committed scores."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
EXPERIMENT = Path('experiments/full35k')
TABLES = ('dataset.tex', 'main_results.tex', 'paired.tex', 'robustness.tex', 'sensitivity.tex')
FIGURES = tuple(name + '.' + suffix for name in ('unseen_robustness', 'unseen_confusion_seed42') for suffix in ('png', 'pdf'))


def digest(content):
    return hashlib.sha256(content).hexdigest()


def main():
    expected_dir = PROJECT / EXPERIMENT / 'evaluation'
    numerical = sorted([p.name for p in expected_dir.glob('*.csv')]) + ['paper_details.json']
    records = {}
    with tempfile.TemporaryDirectory(prefix='rmt-full35k-') as directory:
        temporary = Path(directory) / 'project'
        run = temporary / EXPERIMENT
        run.mkdir(parents=True)
        for name in ('report_results.py', 'publish_results.py', 'config.json', 'manifest.csv',
                     'sample_audit.json', 'predictions.csv', 'validation_predictions.csv'):
            shutil.copy2(PROJECT / EXPERIMENT / name, run / name)
        subprocess.run([sys.executable, str(run / 'report_results.py'), str(run / 'predictions.csv'),
                        '--out', str(run / 'evaluation')], check=True)
        subprocess.run([sys.executable, str(run / 'publish_results.py')], check=True)
        relative_paths = [EXPERIMENT / 'evaluation' / name for name in numerical]
        relative_paths += [Path('tables') / name for name in TABLES]
        relative_paths += [EXPERIMENT / 'figures' / name for name in FIGURES]
        for relative in relative_paths:
            expected = (PROJECT / relative).read_bytes()
            actual = (temporary / relative).read_bytes()
            if expected != actual:
                raise SystemExit('Reproduction mismatch: ' + str(relative))
            records[str(relative)] = dict(status='exact match', sha256=digest(actual))
    check_path = PROJECT / EXPERIMENT / 'reproduction_check.json'
    previous = json.loads(check_path.read_text()) if check_path.exists() else {}
    result = dict(method='Rebuilt from committed test scores, validation scores, manifest and protocol in an isolated temporary project; no training, images, weights or network.',
                  numerical_exports=len(numerical), tables=len(TABLES), figures=len(FIGURES), checks=records)
    if 'table4_jpeg_resnet_fpr_audit' in previous:
        result['table4_jpeg_resnet_fpr_audit'] = previous['table4_jpeg_resnet_fpr_audit']
    check_path.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Exact matches: {len(numerical)} numerical exports, {len(TABLES)} tables and {len(FIGURES)} figure files.')


if __name__ == '__main__':
    main()
