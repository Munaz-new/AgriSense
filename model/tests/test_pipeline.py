"""Synthetic code tests only: no dataset download, optimizer steps or trained artifacts."""
from io import BytesIO
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from PIL import Image
import pytest
import torch

from model.agrisense_model.architecture import HybridCNNTransformer
from model.agrisense_model.checkpoints import load_checkpoint, save_checkpoint
from model.agrisense_model.config import Config, TOMATO_CLASSES, load_config
from model.agrisense_model.data import (TomatoDataset, load_manifest, manifest_digest,
                                       prepare_manifest, preprocess)
from model.agrisense_model.engine import classification_report, run_epoch
from model.agrisense_model.inference import TomatoClassifier

# Small deterministic fixtures exercise code, not plant disease performance.
torch.set_num_threads(1)


@pytest.fixture
def config(tmp_path):
    return Config(dataset_path=str(tmp_path / 'dataset'), manifest_path=str(tmp_path / 'splits.json'),
                  checkpoint_path=str(tmp_path / 'checkpoint.pt'), image_size=32, patch_size=8,
                  embedding_dim=32, transformer_heads=4, transformer_layers=1, batch_size=2)


def make_images(root, offset=0, per_class=6):
    for label, name in enumerate(TOMATO_CLASSES):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(per_class):
            Image.new('RGB', (32, 40), (label * 20, index * 20 + offset, 100)).save(folder / f'{index}.png')


def write_manifest(config, manifest):
    config.path('manifest_path').write_text(json.dumps(manifest))


def test_default_config_paths_and_classes():
    config = load_config()
    assert config.class_names == TOMATO_CLASSES
    assert config.path('dataset_path') == Path(__file__).resolve().parents[1] / 'data/tomato'
    assert config.image_size == 224


@pytest.mark.parametrize('kwargs', [
    {'image_size': 225}, {'image_size': 4, 'patch_size': 4}, {'embedding_dim': 127},
    {'batch_size': 0}, {'learning_rate': float('nan')}, {'epochs': 0},
    {'validation_fraction': 0.7, 'test_fraction': 0.4}, {'class_names': ['Tomato']}, {'seed': -1},
])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)


def test_hybrid_shape_and_both_branch_gradients(config):
    model = HybridCNNTransformer(config)
    images = torch.randn(2, 3, 32, 32)
    before = {key: value.clone() for key, value in model.state_dict().items()}
    output = model(images)
    assert output.shape == (2, 10)
    assert torch.isfinite(output).all()
    # Autograd connectivity only: no optimizer and no parameter updates.
    grads = torch.autograd.grad(output.square().sum(),
                                [model.cnn[0].weight, model.patch_embedding.weight, model.position])
    assert all(torch.isfinite(grad).all() and grad.abs().sum() > 0 for grad in grads)
    assert all(torch.equal(before[key], value) for key, value in model.state_dict().items())
    with pytest.raises(ValueError, match='Expected batch'):
        model(torch.zeros(1, 3, 30, 30))


def test_default_architecture_forward_shape():
    model = HybridCNNTransformer(load_config()).eval()
    with torch.inference_mode():
        assert model(torch.zeros(1, 3, 224, 224)).shape == (1, 10)


def test_reproducible_splits_and_duplicate_grouping(config):
    make_images(config.path('dataset_path'))
    first_class = config.path('dataset_path') / TOMATO_CLASSES[0]
    shutil.copyfile(first_class / '0.png', first_class / 'copy.png')
    manifest = prepare_manifest(config)
    assert manifest == prepare_manifest(config)
    assert manifest_digest(manifest) == manifest_digest(prepare_manifest(config))
    write_manifest(config, manifest)
    assert load_manifest(config) == manifest
    hashes = {split: {row['digest'] for row in rows} for split, rows in manifest['splits'].items()}
    assert not hashes['train'] & hashes['val']
    assert not hashes['train'] & hashes['test']
    assert not hashes['val'] & hashes['test']
    assert sum(len(rows) for rows in manifest['splits'].values()) == 61
    for split in ('train', 'val', 'test'):
        assert {row['label'] for row in manifest['splits'][split]} == set(range(10))
        with patch('model.agrisense_model.data.preprocess', wraps=preprocess) as transform:
            tensor, label = TomatoDataset(config, manifest, split)[0]
            assert tensor.shape == (3, 32, 32)
            assert 0 <= label < 10
            assert transform.call_args.kwargs['augment'] is (split == 'train')


def test_validation_transform_is_deterministic():
    image = Image.new('L', (30, 40), 100)
    assert torch.equal(preprocess(image, 32), preprocess(image, 32))
    assert torch.isfinite(preprocess(image, 32)).all()


def test_dataset_changed_after_manifest_is_rejected(config):
    make_images(config.path('dataset_path'))
    manifest = prepare_manifest(config)
    write_manifest(config, manifest)
    image = config.path('dataset_path') / manifest['splits']['train'][0]['path']
    Image.new('RGB', (32, 40), 'black').save(image)
    with pytest.raises(ValueError, match='Dataset changed'):
        load_manifest(config)


def test_missing_dataset_and_class_folder(config):
    with pytest.raises(ValueError, match='Dataset not found'):
        prepare_manifest(config)
    make_images(config.path('dataset_path'))
    (config.path('dataset_path') / TOMATO_CLASSES[0]).rename(config.path('dataset_path') / 'Wrong_class')
    with pytest.raises(ValueError, match='Class folders mismatch'):
        prepare_manifest(config)


def test_conflicting_labels_rejected(config):
    make_images(config.path('dataset_path'))
    root = config.path('dataset_path')
    shutil.copyfile(root / TOMATO_CLASSES[0] / '0.png', root / TOMATO_CLASSES[1] / 'wrong.png')
    with pytest.raises(ValueError, match='conflicting class labels'):
        prepare_manifest(config)


def test_presplit_layout_and_cross_split_duplicates(config):
    root = config.path('dataset_path')
    for index, split in enumerate(('train', 'val', 'test')):
        make_images(root / split, offset=index + 1)
    manifest = prepare_manifest(config, layout='presplit')
    write_manifest(config, manifest)
    assert load_manifest(config) == manifest
    shutil.copyfile(root / 'train' / TOMATO_CLASSES[0] / '0.png', root / 'test' / TOMATO_CLASSES[0] / 'bad.png')
    with pytest.raises(ValueError, match='cross splits'):
        prepare_manifest(config, layout='presplit')


def test_checkpoint_missing_and_untrained_refused(config):
    with pytest.raises(FileNotFoundError, match='No trained checkpoint'):
        TomatoClassifier(config.path('checkpoint_path'))
    path = config.path('checkpoint_path')
    # This rejected fixture is never claimed to be trained or used for inference.
    torch.save({'format_version': 1, 'trained': False}, path)
    with pytest.raises(ValueError, match='Refusing inference'):
        load_checkpoint(path)
    torch.save(HybridCNNTransformer(config).state_dict(), path)
    with pytest.raises(ValueError, match='Unsupported checkpoint format'):
        load_checkpoint(path)
    with pytest.raises(ValueError, match='untrained'):
        save_checkpoint(path, None, None, config, 0, 0, 0.0, 'test-only')


def test_inference_probability_math_and_absent_severity(config):
    class FixedLogits(torch.nn.Module):
        def forward(self, image):
            return torch.arange(10, dtype=torch.float32).unsqueeze(0)
    # Stub the guarded loader for this arithmetic test only; no checkpoint artifact.
    with patch('model.agrisense_model.inference.load_checkpoint', return_value=(FixedLogits(), config, {})):
        classifier = TomatoClassifier(Path('test-only-unused'))
        image = BytesIO()
        Image.new('RGB', (256, 256), 'white').save(image, format='PNG')
        result = classifier.predict(image.getvalue())
    assert result['disease'] == TOMATO_CLASSES[-1]
    assert result['confidence'] == pytest.approx(float(torch.softmax(torch.arange(10, dtype=torch.float32), 0)[-1]) * 100)
    assert result['severity'] is None


def test_validation_loop_has_no_optimizer_updates(config):
    model = HybridCNNTransformer(config)
    before = {key: value.clone() for key, value in model.state_dict().items()}
    metrics = run_epoch(model, [(torch.zeros(2, 3, 32, 32), torch.tensor([0, 1]))], torch.device('cpu'))
    assert metrics['samples'] == 2
    assert metrics['optimizer_steps'] == 0
    assert sum(map(sum, metrics['confusion_matrix'])) == 2
    assert all(torch.equal(before[key], value) for key, value in model.state_dict().items())
    with pytest.raises(ValueError, match='empty dataset'):
        run_epoch(model, [], torch.device('cpu'))


def test_report_math_only():
    matrix = [[0] * 10 for _ in range(10)]
    matrix[0][0], matrix[0][1], matrix[1][1] = 2, 1, 1
    report = classification_report(matrix, TOMATO_CLASSES)
    assert report['per_class'][TOMATO_CLASSES[0]]['recall'] == pytest.approx(2 / 3)
    assert report['per_class'][TOMATO_CLASSES[1]]['precision'] == 0.5
