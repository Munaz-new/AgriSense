"""Synthetic preparation/compatibility tests; no training or trained checkpoint files."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from PIL import Image
import pytest
import torch

from model.agrisense_model.config import Config, TOMATO_CLASSES
from model.agrisense_model.architecture import HybridCNNTransformer
from model.agrisense_model.checkpoints import (ARCHITECTURE, class_mapping_digest, load_checkpoint)
from model.agrisense_model.data import PREPROCESSING, prepare_manifest, load_manifest
from model.agrisense_model.engine import run_epoch, classification_report
from model.prepare_data import main, write_output


@pytest.fixture
def prepared_source(tmp_path):
    config = Config(dataset_path=str(tmp_path / 'source'), manifest_path=str(tmp_path / 'manifest.json'),
                    image_size=32, patch_size=8, embedding_dim=16, transformer_heads=2,
                    transformer_layers=1, batch_size=2)
    root = config.path('dataset_path')
    for split, offset in [('train', 0), ('valid', 1)]:
        for label, name in enumerate(config.class_names):
            folder = root / split / name
            folder.mkdir(parents=True)
            for index in range(6):
                Image.new('RGB', (32, 32), (label * 20, index * 20 + offset, 80)).save(folder / f'{index}.png')
    return config


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}


def test_eleven_class_curation_and_source_immutability(prepared_source):
    config = prepared_source
    assert config.num_classes == 11 and config.class_names[-1] == 'powdery_mildew'
    root = config.path('dataset_path')
    first, second = config.class_names[:2]
    (root / 'valid' / first / 'bad.png').write_bytes(b'not an image')
    shutil.copyfile(root / 'train' / first / '0.png', root / 'train' / second / 'conflict.png')
    shutil.copyfile(root / 'train' / first / '1.png', root / 'valid' / first / 'overlap.png')
    shutil.copyfile(root / 'train' / first / '2.png', root / 'train' / first / 'duplicate.png')
    shutil.copyfile(root / 'valid' / first / '2.png', root / 'valid' / first / 'duplicate.png')
    before = snapshot(root)
    manifest = prepare_manifest(config, 'train-valid')
    assert manifest == prepare_manifest(config, 'train-valid')
    assert snapshot(root) == before
    assert manifest['summary']['exclusion_counts'] == {
        'unreadable_image': 1, 'conflicting_labels': 2,
        'train_validation_overlap': 1, 'within_split_duplicate': 2}
    assert len(manifest['conflicting_label_groups']) == 1
    assert len(manifest['inventory']) == 137
    assert sum(map(len, manifest['splits'].values())) == 131
    all_hashes = []
    for split, rows in manifest['splits'].items():
        assert {r['label'] for r in rows} == set(range(config.num_classes))
        assert all(r['path'].startswith('valid/' if split == 'val' else 'train/') for r in rows)
        all_hashes.extend(r['digest'] for r in rows)
    assert len(set(all_hashes)) == len(all_hashes)
    config.path('manifest_path').write_text(json.dumps(manifest))
    assert load_manifest(config) == manifest
    assert snapshot(root) == before


@pytest.mark.parametrize('classes', [(), ('one',), ('same', 'same'), ('ok', '../bad'),
                                     ('ok', ''), ('ok', ' bad'), ('ok', 1), 'abc'])
def test_reject_invalid_class_mappings(classes):
    with pytest.raises(ValueError):
        Config(class_names=classes)


@pytest.mark.parametrize('count', [2, 3, 11])
def test_generic_model_and_metrics_dimensions(count):
    config = Config(crop_name='synthetic-test', class_names=tuple(f'fixture_{i}' for i in range(count)),
                    image_size=32, patch_size=8, embedding_dim=16, transformer_heads=2,
                    transformer_layers=1)
    model = HybridCNNTransformer(config)
    before = {k: v.clone() for k, v in model.state_dict().items()}
    result = run_epoch(model, [(torch.zeros(2, 3, 32, 32), torch.tensor([0, count - 1]))], torch.device('cpu'))
    assert len(result['confusion_matrix']) == count
    assert all(len(row) == count for row in result['confusion_matrix'])
    assert result['optimizer_steps'] == 0
    assert all(torch.equal(before[k], v) for k, v in model.state_dict().items())
    assert set(classification_report(result['confusion_matrix'], config.class_names)['per_class']) == set(config.class_names)
    with pytest.raises(ValueError, match='matrix'):
        classification_report([[1]], config.class_names)


@pytest.mark.parametrize('change', ['order', 'count', 'crop', 'metadata'])
def test_checkpoint_mapping_rejected_before_model_construction(change):
    config = Config(class_names=('fixture_a', 'fixture_b'), crop_name='synthetic')
    expected = config
    payload = dict(format_version=2, architecture=ARCHITECTURE, trained=True,
                   completed_epochs=1, optimizer_steps=1, validation_loss=1.0,
                   manifest_digest='test-only', preprocessing=PREPROCESSING,
                   config=config.to_dict(), class_mapping_digest=class_mapping_digest(config))
    if change == 'order':
        expected = replace(config, class_names=tuple(reversed(config.class_names)))
    elif change == 'count':
        expected = replace(config, class_names=(*config.class_names, 'fixture_c'))
    elif change == 'crop':
        expected = replace(config, crop_name='another-synthetic-crop')
    else:
        payload['class_mapping_digest'] = 'tampered'
    # Mock metadata solely to exercise rejection; no checkpoint is created or used for inference.
    with patch.object(Path, 'is_file', return_value=True), patch('torch.load', return_value=payload), \
            patch('model.agrisense_model.checkpoints.HybridCNNTransformer') as factory:
        with pytest.raises(ValueError, match='class mapping'):
            load_checkpoint(Path('unused'), expected_config=expected)
        factory.assert_not_called()


def test_cli_dry_run_and_output_guards(prepared_source, tmp_path, monkeypatch, capsys):
    config = prepared_source
    config_file = tmp_path / 'config.json'
    config_file.write_text(json.dumps(config.to_dict()))
    audit = tmp_path / 'audit.json'
    before = snapshot(config.path('dataset_path'))
    monkeypatch.setattr('sys.argv', ['prepare', '--config', str(config_file), '--layout', 'train-valid',
                                   '--dry-run', '--audit-output', str(audit)])
    main()
    assert 'Active manifest not written' in capsys.readouterr().out
    assert audit.is_file() and not config.path('manifest_path').exists()
    assert snapshot(config.path('dataset_path')) == before
    with pytest.raises(SystemExit, match='Refusing'):
        main()
    with pytest.raises(ValueError, match='outside'):
        write_output(config.path('dataset_path') / 'output.json', {}, config.path('dataset_path'))


def test_source_and_manifest_tampering_rejected(prepared_source):
    config = prepared_source
    manifest = prepare_manifest(config, 'train-valid')
    target = config.path('manifest_path')
    target.write_text(json.dumps(manifest))
    reversed_config = replace(config, class_names=tuple(reversed(config.class_names)))
    with pytest.raises(ValueError, match='class mapping'):
        load_manifest(reversed_config)
    manifest['splits']['train'][0]['label'] = 1
    target.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='class/digest'):
        load_manifest(config)
    manifest = prepare_manifest(config, 'train-valid')
    target.write_text(json.dumps(manifest))
    (config.path('dataset_path') / manifest['inventory'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Dataset changed'):
        load_manifest(config)


def test_wrong_layout_and_class_coverage_fail(prepared_source):
    config = prepared_source
    root = config.path('dataset_path')
    (root / 'valid').rename(root / 'val')
    with pytest.raises(ValueError, match='exactly train/ and valid/'):
        prepare_manifest(config, 'train-valid')
    (root / 'val').rename(root / 'valid')
    for path in (root / 'valid' / config.class_names[-1]).iterdir():
        path.write_bytes(b'corrupt synthetic fixture')
    with pytest.raises(ValueError, match='coverage'):
        prepare_manifest(config, 'train-valid')


def test_exclusion_ledger_seed_and_duplicate_injection(prepared_source):
    config = prepared_source
    root = config.path('dataset_path')
    (root / 'train' / config.class_names[0] / 'notes.txt').write_text('synthetic metadata')
    manifest = prepare_manifest(config, 'train-valid')
    assert manifest['summary']['exclusion_counts'] == {'unsupported_extension': 1}
    changed_seed = prepare_manifest(replace(config, seed=43), 'train-valid')
    assert changed_seed['splits']['val'] == manifest['splits']['val']
    assert changed_seed['splits']['test'] != manifest['splits']['test']
    assert all(len([row for row in manifest['splits']['test'] if row['label'] == label]) == 1
               for label in range(config.num_classes))
    manifest['splits']['test'].append(manifest['splits']['train'][0])
    config.path('manifest_path').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='partition'):
        load_manifest(config)


def test_source_symlink_is_rejected(prepared_source):
    config = prepared_source
    root = config.path('dataset_path')
    folder = root / 'train' / config.class_names[0]
    (folder / 'link.png').symlink_to(folder / '0.png')
    with pytest.raises(ValueError, match='Symlink'):
        prepare_manifest(config, 'train-valid')


def test_cli_external_root_override(prepared_source, tmp_path, monkeypatch, capsys):
    config = prepared_source
    root = config.path('dataset_path')
    config_file = tmp_path / 'config.json'
    config_file.write_text(json.dumps(replace(config, dataset_path='missing-fixture').to_dict()))
    monkeypatch.setattr('sys.argv', ['prepare', '--config', str(config_file), '--layout', 'train-valid',
                                   '--dataset-root', str(root), '--dry-run'])
    main()
    assert 'Active manifest not written' in capsys.readouterr().out
    assert not config.path('manifest_path').exists()
