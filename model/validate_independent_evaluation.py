"""Read-only checks for the Phase 6 independent evaluation collection."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time

from PIL import Image, ImageOps, UnidentifiedImageError

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = Path('/home/munaz/Projects/AgriSense-evaluation-data/tomato-independent-development-170')
DEFAULT_MANIFEST = REPOSITORY / 'model/data/tomato_splits.json'
REQUIRED_COLUMNS = (
    'image_id', 'image_file', 'raw_sha256', 'decoded_rgb_sha256', 'source_provenance',
    'source_url_or_record_id', 'permission_status', 'capture_date_if_known', 'category',
    'species', 'disease_label', 'reviewer_1_id', 'reviewer_1_category', 'reviewer_1_species',
    'reviewer_1_disease_label', 'reviewer_1_decision', 'reviewer_1_notes', 'reviewer_2_id',
    'reviewer_2_category', 'reviewer_2_species', 'reviewer_2_disease_label',
    'reviewer_2_decision', 'reviewer_2_notes', 'disagreement_resolution', 'adjudicator_id',
    'final_category', 'final_species', 'final_disease_label', 'notes',
)
CATEGORIES = ('tomato_leaf', 'other_plant_leaf', 'non_plant', 'ambiguous')
SHA_FIELDS = ('raw_sha256', 'decoded_rgb_sha256')
REVIEW_FIELDS = ('reviewer_1_id', 'reviewer_1_category', 'reviewer_1_species',
                 'reviewer_1_disease_label', 'reviewer_1_decision', 'reviewer_2_id',
                 'reviewer_2_category', 'reviewer_2_species', 'reviewer_2_disease_label',
                 'reviewer_2_decision')


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _decoded_digest(path):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        return hashlib.sha256(image.tobytes()).hexdigest()


def _manifest_sources(manifest_path, dataset_root, progress=None):
    """Hash each unique manifest path once and describe coverage of the source inventory."""
    started = time.monotonic()
    coverage = {
        'total_referenced_entries': 0,
        'unique_source_files': 0,
        'successfully_read_hashed': 0,
        'missing': 0,
        'unreadable': 0,
        'skipped': 0,
        'duplicate_references_skipped': 0,
        'complete': False,
        'elapsed_seconds': 0.0,
    }
    if not manifest_path or not Path(manifest_path).is_file() or not dataset_root or not Path(dataset_root).is_dir():
        return None, coverage
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        entries = [row for rows in manifest['splits'].values() for row in rows]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, coverage
    coverage['total_referenced_entries'] = len(entries)
    unique_paths = {}
    for row in entries:
        value = row.get('path') if isinstance(row, dict) else None
        key = value if isinstance(value, str) else ''
        unique_paths.setdefault(key, None)
    coverage['unique_source_files'] = len(unique_paths)
    coverage['duplicate_references_skipped'] = len(entries) - len(unique_paths)
    hashes = set()
    root = Path(dataset_root).expanduser().resolve()
    for index, relative in enumerate(unique_paths, start=1):
        if not relative:
            coverage['skipped'] += 1
        else:
            rel = Path(relative)
            candidate = (root / rel).resolve()
            if rel.is_absolute() or not candidate.is_relative_to(root):
                coverage['skipped'] += 1
            elif not candidate.is_file():
                coverage['missing'] += 1
            else:
                try:
                    raw_hash = _digest(candidate)
                    decoded_hash = _decoded_digest(candidate)
                except (OSError, UnidentifiedImageError, ValueError, SyntaxError):
                    coverage['unreadable'] += 1
                else:
                    hashes.add(('raw', raw_hash))
                    hashes.add(('decoded', decoded_hash))
                    coverage['successfully_read_hashed'] += 1
        if progress and index % 1000 == 0:
            progress(index, len(unique_paths))
    coverage['complete'] = (
        coverage['successfully_read_hashed'] == coverage['unique_source_files']
        and coverage['missing'] == 0 and coverage['unreadable'] == 0 and coverage['skipped'] == 0
    )
    coverage['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return hashes, coverage


def validate(workspace, manifest_path=DEFAULT_MANIFEST, dataset_root=None, progress=None):
    workspace = Path(workspace).expanduser().resolve()
    csv_path = workspace / 'labels.csv'
    report = {'workspace': str(workspace), 'image_count': 0, 'category_counts': {c: 0 for c in CATEGORIES},
              'overlap_check': 'unavailable', 'evaluation_candidate_count': 0,
              'overlap_result': 'not_evaluated', 'source_coverage': None,
              'errors': [], 'warnings': [], 'status': 'ok'}
    if not csv_path.is_file():
        report['errors'].append(f'Missing labels.csv: {csv_path}')
        report['status'] = 'error'
        return report
    try:
        with csv_path.open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            if len(columns) != len(set(columns)):
                report['errors'].append('CSV header contains duplicate column names.')
            missing = [name for name in REQUIRED_COLUMNS if name not in columns]
            extra = [name for name in columns if name not in REQUIRED_COLUMNS]
            if missing:
                report['errors'].append('Missing required columns: ' + ', '.join(missing))
            if extra:
                report['warnings'].append('Unexpected columns: ' + ', '.join(extra))
            rows = list(reader)
    except (OSError, csv.Error, UnicodeError) as exc:
        report['errors'].append(f'Cannot read labels.csv: {exc}')
        report['status'] = 'error'
        return report
    # An entirely empty (header-only) collection is a valid state.
    report['image_count'] = len(rows)
    ids = set()
    candidates, source_coverage = _manifest_sources(manifest_path, dataset_root, progress)
    report['source_coverage'] = source_coverage
    if candidates is not None:
        if not source_coverage['complete']:
            report['overlap_check'] = 'incomplete'
            report['warnings'].append('Curated source coverage is incomplete; full-manifest overlap verification was not completed.')
    else:
        report['warnings'].append('Curated dataset files or manifest are inaccessible; exact overlap was not checked.')
    overlap_hits = []
    evaluation_candidates = set()
    for line, row in enumerate(rows, start=2):
        if None in row:
            report['errors'].append(f'Row {line} has more values than the header.')
            continue
        image_id = (row.get('image_id') or '').strip()
        if not image_id:
            report['warnings'].append(f'Row {line} is missing image_id.')
        elif image_id in ids:
            report['errors'].append(f'Row {line} duplicates image_id {image_id!r}.')
        ids.add(image_id)
        category = (row.get('category') or '').strip()
        if category in report['category_counts']:
            report['category_counts'][category] += 1
        elif category:
            report['errors'].append(f'Row {line} has unsupported category {category!r}.')
        else:
            report['warnings'].append(f'Row {line} is missing category.')
        image_value = (row.get('image_file') or '').strip()
        image_path = (workspace / image_value).resolve() if image_value else workspace
        if not image_value:
            report['warnings'].append(f'Row {line} is missing image_file.')
        elif not image_path.is_relative_to(workspace):
            report['errors'].append(f'Row {line} image_file escapes the evaluation workspace.')
        elif not image_path.is_file():
            report['errors'].append(f'Row {line} references missing image: {image_value}')
        else:
            actual_hashes = {}
            try:
                actual_hashes['raw'] = _digest(image_path)
                actual_hashes['decoded'] = _decoded_digest(image_path)
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                report['errors'].append(f'Row {line} image cannot be decoded/hashed: {exc}')
            else:
                evaluation_candidates.add(str(image_path))
            for field, kind in (('raw_sha256', 'raw'), ('decoded_rgb_sha256', 'decoded')):
                if kind not in actual_hashes:
                    continue
                claimed = (row.get(field) or '').strip().lower()
                if not claimed:
                    report['warnings'].append(f'Row {line} is missing {field}.')
                actual = actual_hashes[kind]
                if claimed != actual:
                    if claimed:
                        report['errors'].append(f'Row {line} {field} does not match image bytes.')
                if candidates is not None and (kind, actual) in candidates:
                    overlap_hits.append({'row': line, 'field': field, 'image_id': image_id})
        for field in ('source_provenance', 'permission_status'):
            if not (row.get(field) or '').strip():
                report['warnings'].append(f'Row {line} is missing {field}.')
        missing_review = [field for field in REVIEW_FIELDS if not (row.get(field) or '').strip()]
        if missing_review:
            report['warnings'].append(f'Row {line} is missing reviewer information: ' + ', '.join(missing_review))
    report['evaluation_candidate_count'] = len(evaluation_candidates)
    report['exact_overlap_hits'] = overlap_hits
    if not evaluation_candidates:
        report['overlap_result'] = 'no_evaluation_candidates'
        if candidates is not None and source_coverage['complete']:
            report['overlap_check'] = 'no_evaluation_candidates'
    elif candidates is not None and source_coverage['complete']:
        report['overlap_check'] = 'complete'
        report['overlap_result'] = 'exact_overlaps_found' if overlap_hits else 'no_exact_overlaps'
    elif candidates is None:
        report['overlap_result'] = 'not_evaluated'
    else:
        report['overlap_result'] = 'partial_exact_overlaps_found' if overlap_hits else 'incomplete_no_exact_overlap_conclusion'
    if candidates is not None:
        if overlap_hits:
            report['errors'].append(f'Found {len(overlap_hits)} exact hash match(es) against accessible curated files.')
    if source_coverage and source_coverage['unique_source_files'] == 0 and candidates is not None:
        report['warnings'].append('The manifest references no source files; overlap coverage is vacuously complete.')
    report['warnings'].append('Hash matches detect exact bytes/pixels only; hashes do not establish source independence or label correctness.')
    report['status'] = 'error' if report['errors'] else ('warning' if report['warnings'] else 'ok')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--dataset-root', type=Path, help='Accessible root for train/valid files; omit to report overlap unavailable.')
    parser.add_argument('--progress', action='store_true', help='Print source hashing progress every 1,000 unique manifest paths to stderr.')
    args = parser.parse_args(argv)
    progress = (lambda done, total: print(f'Checked {done}/{total} unique manifest source paths...', file=__import__('sys').stderr)) if args.progress else None
    print(json.dumps(validate(args.workspace, args.manifest, args.dataset_root, progress), indent=2))


if __name__ == '__main__':
    main()
