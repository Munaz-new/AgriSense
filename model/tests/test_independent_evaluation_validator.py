import csv
import json
from PIL import Image

from model.validate_independent_evaluation import REQUIRED_COLUMNS, validate


def write_labels(path, rows=()):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def row(**updates):
    result = {name: '' for name in REQUIRED_COLUMNS}
    result.update({'image_id': 'opaque-1', 'image_file': 'tomato-leaves/opaque-1.png',
                   'category': 'tomato_leaf', 'source_provenance': 'owner supplied',
                   'permission_status': 'granted'})
    result.update(updates)
    return result


def test_empty_header_only_workspace_is_valid_zero_image_state(tmp_path):
    write_labels(tmp_path / 'labels.csv')
    report = validate(tmp_path, manifest_path=tmp_path / 'absent.json', dataset_root=tmp_path / 'absent')
    assert report['image_count'] == 0
    assert report['category_counts']['tomato_leaf'] == 0
    assert report['status'] == 'warning'
    assert not report['errors']


def test_reports_missing_image_and_incomplete_provenance_review(tmp_path):
    write_labels(tmp_path / 'labels.csv', [row()])
    report = validate(tmp_path, manifest_path=tmp_path / 'absent.json')
    assert any('references missing image' in error for error in report['errors'])
    assert any('reviewer information' in warning for warning in report['warnings'])
    assert report['category_counts']['tomato_leaf'] == 1


def test_duplicate_ids_are_errors(tmp_path):
    write_labels(tmp_path / 'labels.csv', [row(), row(image_file='other.png')])
    report = validate(tmp_path)
    assert any('duplicates image_id' in error for error in report['errors'])


def test_hash_integrity_and_exact_manifest_overlap(tmp_path):
    image_dir = tmp_path / 'tomato-leaves'
    image_dir.mkdir()
    image = image_dir / 'opaque-1.png'
    Image.new('RGB', (3, 2), (12, 34, 56)).save(image)
    from model.validate_independent_evaluation import _decoded_digest, _digest
    record = row(raw_sha256=_digest(image), decoded_rgb_sha256=_decoded_digest(image))
    write_labels(tmp_path / 'labels.csv', [record])
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'same.png').write_bytes(image.read_bytes())
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'splits': {'train': [{'path': 'same.png'}]}}))
    report = validate(tmp_path, manifest, source)
    assert report['overlap_check'] == 'complete'
    assert report['overlap_result'] == 'exact_overlaps_found'
    assert len(report['exact_overlap_hits']) == 2
    assert any('exact hash match' in error for error in report['errors'])
    record['raw_sha256'] = '0' * 64
    write_labels(tmp_path / 'labels.csv', [record])
    assert any('raw_sha256 does not match' in error for error in validate(tmp_path, manifest, source)['errors'])


def write_manifest(path, entries):
    path.write_text(json.dumps({'splits': entries}))


def test_complete_coverage_deduplicates_logical_references_and_empty_collection(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    Image.new('RGB', (4, 3), (1, 2, 3)).save(source / 'one.png')
    manifest = tmp_path / 'manifest.json'
    write_manifest(manifest, {'train': [{'path': 'one.png'}], 'val': [{'path': 'one.png'}]})
    write_labels(tmp_path / 'labels.csv')
    report = validate(tmp_path, manifest, source)
    coverage = report['source_coverage']
    assert coverage['total_referenced_entries'] == 2
    assert coverage['unique_source_files'] == 1
    assert coverage['successfully_read_hashed'] == 1
    assert coverage['duplicate_references_skipped'] == 1
    assert coverage['missing'] == coverage['unreadable'] == coverage['skipped'] == 0
    assert coverage['complete'] is True
    assert report['evaluation_candidate_count'] == 0
    assert report['overlap_check'] == 'no_evaluation_candidates'
    assert report['overlap_result'] == 'no_evaluation_candidates'


def test_incomplete_coverage_reports_missing_source_without_success_claim(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    manifest = tmp_path / 'manifest.json'
    write_manifest(manifest, {'train': [{'path': 'missing.png'}]})
    write_labels(tmp_path / 'labels.csv')
    report = validate(tmp_path, manifest, source)
    assert report['source_coverage']['missing'] == 1
    assert report['source_coverage']['complete'] is False
    assert report['overlap_check'] == 'incomplete'
    assert report['overlap_result'] == 'no_evaluation_candidates'


def test_incomplete_coverage_reports_unreadable_source(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'bad.png').write_bytes(b'not an image')
    manifest = tmp_path / 'manifest.json'
    write_manifest(manifest, {'train': [{'path': 'bad.png'}]})
    write_labels(tmp_path / 'labels.csv')
    report = validate(tmp_path, manifest, source)
    assert report['source_coverage']['unreadable'] == 1
    assert report['source_coverage']['successfully_read_hashed'] == 0
    assert report['source_coverage']['complete'] is False
    assert report['overlap_check'] == 'incomplete'


def test_complete_overlap_scan_distinguishes_no_exact_overlap(tmp_path):
    workspace = tmp_path / 'evaluation'
    workspace.mkdir()
    image_dir = workspace / 'tomato-leaves'
    image_dir.mkdir()
    eval_image = image_dir / 'candidate.png'
    Image.new('RGB', (4, 3), (100, 110, 120)).save(eval_image)
    from model.validate_independent_evaluation import _decoded_digest, _digest
    write_labels(workspace / 'labels.csv', [row(
        image_file='tomato-leaves/candidate.png', raw_sha256=_digest(eval_image),
        decoded_rgb_sha256=_decoded_digest(eval_image))])
    source = tmp_path / 'source'
    source.mkdir()
    Image.new('RGB', (4, 3), (1, 2, 3)).save(source / 'source.png')
    manifest = tmp_path / 'manifest.json'
    write_manifest(manifest, {'train': [{'path': 'source.png'}]})
    report = validate(workspace, manifest, source)
    assert report['source_coverage']['complete'] is True
    assert report['evaluation_candidate_count'] == 1
    assert report['overlap_check'] == 'complete'
    assert report['overlap_result'] == 'no_exact_overlaps'
    assert report['exact_overlap_hits'] == []


def test_header_missing_required_field_is_error(tmp_path):
    with (tmp_path / 'labels.csv').open('w', newline='', encoding='utf-8') as stream:
        stream.write('image_id,image_file\n')
    report = validate(tmp_path)
    assert any('Missing required columns' in error for error in report['errors'])
