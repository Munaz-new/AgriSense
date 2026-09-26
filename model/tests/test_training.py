"""Training-control tests only. Epoch work/checkpoint saving are intercepted.

No real dataset, optimizer updates, trained-weight files or research results.
Numbers below are explicitly synthetic control-flow fixtures, never model metrics.
"""
import copy
from dataclasses import replace
import json
from pathlib import Path
import random
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
import pytest
import torch

from model import train as cli
from model.agrisense_model import training as flow
from model.agrisense_model.checkpoints import load_checkpoint, save_checkpoint
from model.agrisense_model.config import Config, TOMATO_CLASSES, load_config
from model.agrisense_model.data import prepare_manifest, manifest_digest
from model.agrisense_model.engine import loader, seed_everything


@pytest.fixture
def tiny(tmp_path):
    config = Config(crop_name='synthetic-fixture', class_names=('fixture_a', 'fixture_b'),
                    dataset_path=str(tmp_path / 'source'), manifest_path=str(tmp_path / 'manifest.json'),
                    checkpoint_path=str(tmp_path / 'outputs' / 'best.pt'), epochs=2,
                    image_size=32, patch_size=8, embedding_dim=16, transformer_heads=2,
                    transformer_layers=1, batch_size=2)
    root = config.path('dataset_path')
    for label, name in enumerate(config.class_names):
        folder = root / name
        folder.mkdir(parents=True)
        for index in range(4):
            Image.new('RGB', (32, 40), (label * 100, index * 30, 70)).save(folder / f'{index}.png')
    manifest = prepare_manifest(config)
    config.path('manifest_path').write_text(json.dumps(manifest))
    return config, manifest


@pytest.mark.parametrize('kwargs', [
    {'optimizer': 'unknown'}, {'weight_decay': -1}, {'weight_decay': float('nan')},
    {'momentum': 1}, {'momentum': float('inf')},
])
def test_invalid_optimizer_configuration(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)


def test_backward_compatible_defaults_and_windows_template():
    original = Config(**{'class_names': list(TOMATO_CLASSES)})
    example = load_config(Path(__file__).parents[1] / 'configs/tomato.windows.example.json')
    assert original.optimizer == example.optimizer == 'adamw'
    assert example.class_names == TOMATO_CLASSES and example.num_classes == 11
    assert example.class_names[-1] == 'powdery_mildew'
    assert all(not Path(value).is_absolute() for key, value in example.to_dict().items() if key.endswith('_path'))


@pytest.mark.parametrize('name,kind', [('adamw', torch.optim.AdamW), ('sgd', torch.optim.SGD)])
def test_optimizer_settings_without_updates(name, kind):
    model = torch.nn.Linear(2, 2)
    config = Config(optimizer=name, learning_rate=0.02, weight_decay=0.03, momentum=0.4)
    before = copy.deepcopy(model.state_dict())
    optimizer = flow.build_optimizer(model, config)
    assert isinstance(optimizer, kind)
    assert optimizer.param_groups[0]['lr'] == 0.02
    assert optimizer.param_groups[0]['weight_decay'] == 0.03
    if name == 'sgd':
        assert optimizer.param_groups[0]['momentum'] == 0.4
    assert all(torch.equal(before[key], value) for key, value in model.state_dict().items())


def test_check_only_does_not_construct_model_or_write_outputs(tiny):
    config, manifest = tiny
    with patch.object(flow, 'HybridCNNTransformer') as model, patch.object(flow, 'run_epoch') as epoch, \
            patch.object(flow, 'save_checkpoint') as save, patch.object(flow, 'build_optimizer') as optimizer:
        result = flow.train(config, check_only=True)
        for spy in (model, epoch, save, optimizer):
            spy.assert_not_called()
    assert result['split_counts'] == {key: len(rows) for key, rows in manifest['splits'].items()}
    assert not config.path('checkpoint_path').parent.exists()


@pytest.mark.parametrize('key', ['best', 'last', 'history', 'run'])
def test_existing_outputs_are_preserved(tiny, key):
    config, _ = tiny
    path = flow.output_paths(config)[key]
    path.parent.mkdir()
    path.write_text('existing evidence')
    with pytest.raises(ValueError, match='existing output'):
        flow.prepare_run(config, 'cpu')
    assert path.read_text() == 'existing evidence'


def test_output_inside_dataset_is_refused(tiny):
    config, _ = tiny
    config = replace(config, checkpoint_path=str(config.path('dataset_path') / 'bad.pt'))
    with pytest.raises(ValueError, match='outside the source'):
        flow.prepare_run(config, 'cpu')
    assert not config.path('checkpoint_path').exists()


@pytest.mark.parametrize('suffix', ['best.pt', 'nested/best.pt'])
def test_output_parent_file_is_refused_before_dataset_access(tiny, suffix):
    config, _ = tiny
    blocker = config.path('checkpoint_path').parent
    blocker.write_text('existing evidence')
    config = replace(config, checkpoint_path=str(blocker / suffix))
    with patch.object(flow, 'load_manifest') as load:
        with pytest.raises(ValueError, match='parent must be a directory'):
            flow.prepare_run(config, 'cpu')
        load.assert_not_called()
    assert blocker.read_text() == 'existing evidence'


@pytest.mark.parametrize('classes', [TOMATO_CLASSES[:-1], tuple(reversed(TOMATO_CLASSES))])
def test_tomato_mapping_mismatch_fails_before_dataset_access(classes):
    with patch.object(flow, 'load_manifest') as load:
        with pytest.raises(ValueError, match='11 ordered classes'):
            flow.prepare_run(Config(class_names=classes), 'cpu')
        load.assert_not_called()


def test_cuda_unavailable_does_not_fall_back(monkeypatch):
    monkeypatch.delenv('CUBLAS_WORKSPACE_CONFIG', raising=False)
    with patch('torch.cuda.is_available', return_value=False):
        with pytest.raises(ValueError, match='CUDA requested but unavailable'):
            flow.select_device('cuda')


def test_cli_overrides_and_check_only(tiny):
    config, _ = tiny
    path = config.path('manifest_path').with_name('config.json')
    path.write_text(json.dumps(config.to_dict()))
    with patch.object(cli, 'train') as train:
        cli.main(['--config', str(path), '--epochs', '3', '--batch-size', '1', '--optimizer', 'sgd',
                  '--learning-rate', '0.01', '--weight-decay', '0.02', '--check-only'])
    actual = train.call_args.args[0]
    assert (actual.epochs, actual.batch_size, actual.optimizer, actual.learning_rate, actual.weight_decay) == (3, 1, 'sgd', 0.01, 0.02)
    assert train.call_args.kwargs == dict(resume=None, check_only=True)


def test_loader_restarts_identical_epoch_shuffle_and_augmentation(tiny):
    config, manifest = tiny
    seed_everything(43)
    first = list(loader(config, manifest, 'train', seed=43))
    seed_everything(43)
    repeated = list(loader(config, manifest, 'train', seed=43))
    assert all(torch.equal(x, y) and torch.equal(a, b) for (x, a), (y, b) in zip(first, repeated))
    assert sum(labels.numel() for _, labels in first) == len(manifest['splits']['train'])


def install_control_doubles(monkeypatch):
    """Capture orchestration in memory; never optimize or serialize model weights."""
    saved, calls, draws = {}, [], []
    monkeypatch.setattr(flow, 'HybridCNNTransformer', lambda config: torch.nn.Linear(2, 2))
    monkeypatch.setattr(flow, 'loader', lambda config, manifest, split, seed: (split, seed))

    def epoch(model, batches, device, optimizer=None):
        split, seed = batches
        calls.append((split, seed))
        draws.append((random.random(), np.random.rand(), float(torch.rand(()))))
        # Explicit control-flow fixtures; no actual forward/backward or optimizer step.
        loss = 1.0 if seed == 42 else 2.0
        return dict(loss=loss, accuracy=0.0, samples=2, optimizer_steps=int(optimizer is not None))

    def capture(path, model, optimizer, config, epoch, steps, loss, digest, training_state=None):
        saved[str(path)] = (copy.deepcopy(model), copy.deepcopy(config), dict(
            completed_epochs=epoch, optimizer_steps=steps, validation_loss=loss,
            manifest_digest=digest, optimizer_state_dict=optimizer.state_dict() if optimizer else {},
            training_state=copy.deepcopy(training_state)))

    monkeypatch.setattr(flow, 'run_epoch', epoch)
    monkeypatch.setattr(flow, 'save_checkpoint', capture)
    return saved, calls, draws


def test_best_last_history_and_resume_without_training(tiny, monkeypatch):
    config, manifest = tiny
    saved, calls, draws = install_control_doubles(monkeypatch)
    full = flow.train(config)
    assert calls == [('train', 42), ('val', 42), ('train', 43), ('val', 43)]
    assert all(split != 'test' for split, _ in calls)
    paths = flow.output_paths(config)
    assert saved[str(paths['best'])][2]['completed_epochs'] == 1
    assert saved[str(paths['last'])][2]['completed_epochs'] == 2
    assert json.loads(paths['history'].read_text()) == full
    assert not list(paths['best'].parent.glob('*.pt'))

    # Simulate an interruption after epoch 1; verify epoch 2 RNG/shuffle on resume.
    partial = replace(config, epochs=1, checkpoint_path=str(paths['best'].parent / 'partial' / 'best.pt'))
    flow.train(partial)
    last = flow.output_paths(partial)['last']
    monkeypatch.setattr(flow, 'load_checkpoint', lambda path, expected_config: copy.deepcopy(saved[str(path)]))
    resumed = replace(config, checkpoint_path=str(paths['best'].parent / 'resumed' / 'best.pt'))
    resumed_history = flow.train(resumed, resume=last)
    assert resumed_history == full
    assert draws[2:4] == draws[-2:]
    assert calls[-2:] == [('train', 43), ('val', 43)]
    resumed_best = saved[str(flow.output_paths(resumed)['best'])][2]
    assert resumed_best['completed_epochs'] == 1  # Preserve prior best even without improvement.


@pytest.mark.parametrize('change,match', [
    ('manifest', 'manifest digest'), ('config', 'configuration mismatch'), ('runtime', 'runtime mismatch'),
    ('legacy', 'last checkpoint'), ('epochs', 'epochs must exceed'), ('history', 'history is incomplete'),
    ('optimizer', 'optimizer state'), ('best', 'best loss'), ('steps', 'disagree'),
])
def test_incompatible_resume_is_rejected(tiny, monkeypatch, change, match):
    config, manifest = tiny
    saved, _, _ = install_control_doubles(monkeypatch)
    flow.train(replace(config, epochs=1))
    model, previous, payload = copy.deepcopy(saved[str(flow.output_paths(config)['last'])])
    runtime = flow.runtime_info(torch.device('cpu'))
    if change == 'manifest': payload['manifest_digest'] = 'different'
    elif change == 'config': config = replace(config, learning_rate=0.1)
    elif change == 'runtime': payload['training_state']['runtime'] = {}
    elif change == 'legacy': payload['training_state'] = None
    elif change == 'epochs': config = replace(config, epochs=1)
    elif change == 'history': payload['training_state']['history'] = []
    elif change == 'optimizer': payload['optimizer_state_dict'] = {}
    elif change == 'best': payload['training_state']['best_loss'] = float('nan')
    elif change == 'steps': payload['training_state']['best_steps'] = 2
    monkeypatch.setattr(flow, 'load_checkpoint', lambda *args, **kwargs: (model, previous, payload))
    with pytest.raises(ValueError, match=match):
        flow.resume_state(config, Path('unused'), manifest_digest(manifest), runtime)


def test_checkpoint_v2_compatibility_in_memory_only(tiny):
    config, _ = tiny
    model = flow.HybridCNNTransformer(config)
    payloads = []
    # Exercise serialization metadata and guarded loading without creating fake trained files.
    with patch('torch.save', side_effect=lambda payload, path: payloads.append(payload)), \
            patch.object(Path, 'replace'), patch.object(Path, 'mkdir'):
        save_checkpoint(Path('unused.pt'), model, None, config, 1, 1, 1.0, 'synthetic-fixture')
    payload = payloads[0]
    assert payload['format_version'] == 2
    assert payload['optimizer_state_dict'] == {}
    with patch.object(Path, 'is_file', return_value=True), patch('torch.load', return_value=payload) as load:
        loaded, actual, _ = load_checkpoint(Path('unused.pt'), expected_config=config)
    assert load.call_args.kwargs['weights_only'] is True
    assert actual.class_names == config.class_names and not loaded.training
    assert all(torch.equal(value, loaded.state_dict()[key]) for key, value in model.state_dict().items())
