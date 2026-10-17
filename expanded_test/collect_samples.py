"""Collect fresh Tiny-GenImage test images, excluding the entire original pilot.

Selection uses source labels and deterministic random order, never model scores.
Downloaded images stay in a separate cache; the portable manifest records hashes.
"""
import argparse
import csv
import hashlib
import io
import json
import random
import time
import urllib.parse
import urllib.request
import urllib.error
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DATASET = 'TheKernel01/Tiny-GenImage'
REVISION = '89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69'
NAMES = {0: 'real', 2: 'BigGAN', 3: 'GLIDE', 4: 'Midjourney'}
PAGE_REQUEST_LOCK = threading.Lock()
LAST_PAGE_REQUEST = 0.0


def request(url):
    global LAST_PAGE_REQUEST
    for attempt in range(8):
        try:
            if '/rows?' in url:
                with PAGE_REQUEST_LOCK:
                    time.sleep(max(0, 2.1 - (time.monotonic() - LAST_PAGE_REQUEST)))
                    LAST_PAGE_REQUEST = time.monotonic()
            with urllib.request.urlopen(url, timeout=35) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if attempt == 7:
                raise
            if error.code == 429:
                retry = error.headers.get('Retry-After', '')
                delay = float(retry) if retry.isdigit() else min(60, 15 * (attempt + 1))
                print('Rate limited; retrying after', delay, 'seconds', flush=True)
                time.sleep(delay)
            else:
                time.sleep(min(10, 2 ** attempt))
        except Exception:
            if attempt == 7:
                raise
            time.sleep(min(10, 2 ** attempt))


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def image_info(data):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        width, height = image.size
        codec = image.format
        pixels = image.convert('RGB').tobytes()
        pixel_hash = hashlib.sha256(f'{width}x{height}:RGB:'.encode() + pixels).hexdigest()
        quantization = getattr(image, 'quantization', None)
    return dict(width=width, height=height, codec=codec,
                sha256=hashlib.sha256(data).hexdigest(), pixel_sha256=pixel_hash,
                jpeg_tables_sha256=hashlib.sha256(json.dumps(quantization, sort_keys=True).encode()).hexdigest()
                if quantization else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--original-cache', type=Path, required=True)
    parser.add_argument('--per-class', type=int, default=400)
    parser.add_argument('--sampling-seed', type=int, default=20261017)
    args = parser.parse_args()
    assert args.per_class > 0 and args.per_class % 2 == 0
    args.cache.mkdir(parents=True, exist_ok=True)
    pages = args.cache / 'pages'
    pages.mkdir(exist_ok=True)
    start = time.perf_counter()
    revision = json.loads(request('https://huggingface.co/api/datasets/' + DATASET))['sha']
    if revision != REVISION:
        raise ValueError('Dataset revision changed; review row identities before proceeding')
    original = list(csv.DictReader((HERE.parent / 'pilot/manifest.csv').open()))
    old_ids = {row['image_id'] for row in original}
    old_hashes = {row['sha256'] for row in original}
    old_pixels = set()
    for row in original:
        data = (args.original_cache / (row['image_id'] + '.bin')).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Original image changed: ' + row['image_id'])
        old_pixels.add(image_info(data)['pixel_sha256'])

    def page(offset):
        path = pages / f'validation_{offset:05d}.json'
        if path.exists():
            content = json.loads(path.read_text())
        else:
            query = urllib.parse.urlencode(dict(dataset=DATASET, config='default',
                                               split='validation', offset=offset, length=100))
            content = json.loads(request('https://datasets-server.huggingface.co/rows?' + query))
            path.write_text(json.dumps(content))
        if content['num_rows_total'] != 7000:
            raise ValueError('Validation split size changed')
        return content['rows']

    with ThreadPoolExecutor(2) as pool:
        fetched = list(pool.map(page, range(0, 7000, 100)))
    rows = [row for page_rows in fetched for row in page_rows]
    assert len(rows) == len({row['row_idx'] for row in rows}) == 7000
    full_counts = Counter(row['row']['generator'] for row in rows)
    print('Full validation source counts:', dict(sorted(full_counts.items())), flush=True)
    pools = {g: [row for row in rows if row['row']['generator'] == g
                 and f"tiny_validation_{row['row_idx']}" not in old_ids] for g in NAMES}
    rng = random.Random(args.sampling_seed)
    for g in sorted(pools):
        pools[g].sort(key=lambda row: row['row_idx'])
        rng.shuffle(pools[g])
    requested = {0: 2 * args.per_class, 2: args.per_class // 2,
                 3: args.per_class // 2, 4: args.per_class}
    if any(len(pools[g]) < n for g, n in requested.items()):
        raise ValueError('Insufficient candidate rows: ' + str({g: len(v) for g, v in pools.items()}))
    (HERE / 'selection_protocol.json').write_text(json.dumps(dict(
        dataset=DATASET, dataset_revision=revision, mirror_split='validation',
        rows_audited=7000, sampling_seed=args.sampling_seed, target_per_class=args.per_class,
        requested_by_generator=requested, selection_uses_predictions=False,
        exclusions='All original 480 pilot IDs, file hashes and decoded RGB pixel hashes; subsequent duplicate files/pixels retain first in deterministic shuffled order.',
        original_manifest_sha256=hashlib.sha256((HERE.parent / 'pilot/manifest.csv').read_bytes()).hexdigest(),
        checkpoint_policy='Use the existing seeds 42, 43 and 44 without fitting or threshold selection on this sample.'
    ), indent=2) + '\n')

    def download(row):
        image_id = f"tiny_validation_{row['row_idx']}"
        path = args.cache / (image_id + '.bin')
        try:
            data = path.read_bytes() if path.exists() else request(row['row']['image']['src'])
            info = image_info(data)
            if not path.exists():
                path.write_bytes(data)
            generator = row['row']['generator']
            assert int(row['row']['label']) == (0 if generator == 0 else 1)
            return dict(image_id=image_id, mirror_split='validation', row_idx=row['row_idx'],
                        label=int(row['row']['label']), generator=NAMES[generator], **info), None
        except Exception as error:
            return None, dict(image_id=image_id, reason=type(error).__name__ + ': ' + str(error))

    used_hashes, used_pixels = set(old_hashes), set(old_pixels)
    selected, exclusions, failures = {}, [], []
    with ThreadPoolExecutor(32) as pool:
        for generator in [0, 2, 3, 4]:
            accepted = []
            position = 0
            while len(accepted) < requested[generator] and position < len(pools[generator]):
                need = requested[generator] - len(accepted)
                batch = pools[generator][position:position + min(500, need)]
                position += len(batch)
                for record, error in pool.map(download, batch):
                    if error:
                        failures.append(error)
                        continue
                    if record['sha256'] in used_hashes or record['pixel_sha256'] in used_pixels:
                        exclusions.append(dict(image_id=record['image_id'], reason='Original-pilot overlap or repeated file/decoded pixels'))
                        continue
                    used_hashes.add(record['sha256'])
                    used_pixels.add(record['pixel_sha256'])
                    accepted.append(record)
                print(NAMES[generator], 'accepted', len(accepted), 'of', requested[generator],
                      'candidate rows attempted', position, flush=True)
            if len(accepted) != requested[generator]:
                raise ValueError(f'Only {len(accepted)} independent {NAMES[generator]} images remained')
            selected[generator] = accepted
    records = []
    for generator, items in selected.items():
        for index, record in enumerate(items):
            record['split'] = ('seen' if index < args.per_class else 'unseen') if generator == 0 else ('unseen' if generator == 4 else 'seen')
            records.append(record)
    records.sort(key=lambda row: row['image_id'])
    write_csv(HERE / 'manifest.csv', records)
    if exclusions:
        write_csv(HERE / 'excluded_candidates.csv', exclusions)
    if failures:
        write_csv(HERE / 'failed_candidates.csv', failures)
    by_group = Counter((r['split'], r['generator']) for r in records)
    summary = dict(dataset=DATASET, dataset_revision=revision,
        accessed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        audited_validation_rows=len(rows), full_validation_source_counts=dict(full_counts),
        original_pilot_ids_excluded=len(old_ids), original_file_hashes_excluded=len(old_hashes),
        original_decoded_pixel_hashes_excluded=len(old_pixels), new_unique_images=len(records),
        new_file_hashes=len({r['sha256'] for r in records}), new_decoded_pixel_hashes=len({r['pixel_sha256'] for r in records}),
        source_counts={s + '/' + g: n for (s, g), n in sorted(by_group.items())},
        codecs=dict(Counter(r['codec'] for r in records)),
        native_size_and_encoding={name: dict(
            n=len(group), width_range=[min(x['width'] for x in group), max(x['width'] for x in group)],
            height_range=[min(x['height'] for x in group), max(x['height'] for x in group)],
            jpeg_table_counts=dict(Counter(x['jpeg_tables_sha256'] for x in group)))
            for name in NAMES.values() for group in [[x for x in records if x['generator']==name]]},
        duplicate_or_overlap_candidates_removed=len(exclusions), failed_candidates=len(failures),
        bytes_selected=sum((args.cache / (r['image_id'] + '.bin')).stat().st_size for r in records),
        collection_seconds=time.perf_counter()-start,
        limitations=['A later independent test sample after inspection of the original pilot.',
                    'Exact file and decoded-pixel checks do not establish absence of near-duplicates.',
                    'No category matching or native-size/compression matching.'])
    (HERE / 'sample_audit.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('COLLECTION COMPLETE', json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
