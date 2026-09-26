"""Training orchestration. Imported safely; execution requires an explicit caller."""
import copy
import json
import math
import os
from pathlib import Path
import platform
import time

import numpy as np
from PIL import __version__ as pillow_version
import torch

from .architecture import HybridCNNTransformer
from .checkpoints import load_checkpoint, save_checkpoint
from .config import TOMATO_CLASSES
from .data import load_manifest, manifest_digest
from .engine import loader, run_epoch, seed_everything

SEED_POLICY = 'epoch-seed-v1'


def select_device(name):
    if name not in {'cpu', 'cuda'}:
        raise ValueError('Device must be cpu or cuda.')
    if name == 'cuda':
        # Set before CUDA initialization; do not silently fall back to CPU.
        if os.environ.get('CUBLAS_WORKSPACE_CONFIG', ':4096:8') not in {':4096:8', ':16:8'}:
            raise ValueError('Deterministic CUDA requires CUBLAS_WORKSPACE_CONFIG=:4096:8 or :16:8.')
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        if not torch.cuda.is_available():
            raise ValueError('CUDA requested but unavailable. Install a compatible CUDA PyTorch build/driver or choose cpu.')
    return torch.device(name)


def runtime_info(device):
    return dict(python=platform.python_version(), torch=str(torch.__version__),
                numpy=np.__version__, pillow=pillow_version, system=platform.system(),
                machine=platform.machine(), device=device.type, cuda=torch.version.cuda,
                cudnn=torch.backends.cudnn.version(), threads=torch.get_num_threads(),
                device_name=torch.cuda.get_device_name(device) if device.type == 'cuda' else platform.processor())


def output_paths(config):
    best = config.path('checkpoint_path').resolve()
    if best.suffix != '.pt':
        raise ValueError('checkpoint_path must end in .pt.')
    return dict(best=best, last=best.with_suffix('.last.pt'),
                history=best.with_suffix('.history.json'), run=best.with_suffix('.run.json'))


def validate_outputs(config):
    paths = output_paths(config)
    source = config.path('dataset_path').resolve()
    for path in paths.values():
        for parent in path.parents:
            if (parent.exists() or parent.is_symlink()) and not parent.is_dir():
                raise ValueError(f'Training output parent must be a directory: {parent}')
        temporary = path.with_suffix('.tmp') if path.suffix == '.pt' else path.with_name(path.name + '.tmp')
        for target in (path, temporary):
            if target.is_relative_to(source):
                raise ValueError('Training outputs must be outside the source dataset.')
            if target.exists() or target.is_symlink():
                raise ValueError(f'Refusing existing output: {target}. Use a new checkpoint_path, including for resume.')
    return paths


def prepare_run(config, device_name):
    if config.crop_name == 'tomato' and config.class_names != TOMATO_CLASSES:
        raise ValueError('Tomato training requires all 11 ordered classes, including powdery_mildew.')
    paths = validate_outputs(config)
    device = select_device(device_name)
    manifest = load_manifest(config)  # Read-only integrity check; never prepares/resplits data.
    if config.crop_name == 'tomato' and manifest.get('version') != 2:
        raise ValueError('Tomato training requires the validated Phase 3A version-2 manifest.')
    return paths, device, manifest


def build_optimizer(model, config):
    if config.optimizer == 'adamw':
        return torch.optim.AdamW(model.parameters(), lr=config.learning_rate,
                                 weight_decay=config.weight_decay)
    return torch.optim.SGD(model.parameters(), lr=config.learning_rate,
                           weight_decay=config.weight_decay, momentum=config.momentum)


def resume_state(config, resume_path, digest, runtime):
    model, previous, payload = load_checkpoint(Path(resume_path), expected_config=config)
    state = payload.get('training_state')
    if not isinstance(state, dict) or state.get('version') != 1 or state.get('seed_policy') != SEED_POLICY:
        raise ValueError('Resume requires a Phase 4A last checkpoint; best/legacy checkpoints cannot resume.')
    if payload['manifest_digest'] != digest:
        raise ValueError('Resume manifest digest mismatch; do not change split membership.')
    # Moving the dataset/output locations and increasing total epochs are supported.
    ignored = {'dataset_path', 'manifest_path', 'checkpoint_path', 'report_path', 'epochs'}
    if any(value != previous.to_dict()[key] for key, value in config.to_dict().items() if key not in ignored):
        raise ValueError('Resume training configuration mismatch; only paths and total epochs may change.')
    if state.get('runtime') != runtime:
        raise ValueError('Resume runtime mismatch; use the same software, device, OS and thread settings.')
    epoch = payload['completed_epochs']
    if type(epoch) is not int or epoch < 1 or config.epochs <= epoch:
        raise ValueError('Resume epochs must exceed the completed epoch; epochs means total target epochs.')
    history = state.get('history')
    if not isinstance(history, list) or [row.get('epoch') for row in history] != list(range(1, epoch + 1)):
        raise ValueError('Resume history is incomplete.')
    best_epoch = state.get('best_epoch')
    if type(best_epoch) is not int or not 1 <= best_epoch <= epoch:
        raise ValueError('Invalid resume best epoch.')
    best_loss = state.get('best_loss')
    if not isinstance(best_loss, (int, float)) or not math.isfinite(best_loss) or best_loss < 0:
        raise ValueError('Invalid resume best loss.')
    if not payload.get('optimizer_state_dict'):
        raise ValueError('Resume optimizer state is missing.')
    try:
        steps = payload['optimizer_steps']
        best_steps = state['best_steps']
        if (type(steps) is not int or type(best_steps) is not int or not 1 <= best_steps <= steps
                or steps != sum(row['train']['optimizer_steps'] for row in history)
                or best_steps != sum(row['train']['optimizer_steps'] for row in history[:best_epoch])
                or payload['validation_loss'] != history[-1]['validation']['loss']
                or best_loss != history[best_epoch - 1]['validation']['loss']
                or best_loss != min(row['validation']['loss'] for row in history)):
            raise ValueError('Resume history/steps/best loss disagree.')
    except (KeyError, TypeError) as error:
        raise ValueError('Resume history is malformed.') from error
    best_model = copy.deepcopy(model)
    best_model.load_state_dict(state['best_state_dict'], strict=True)
    if not all(torch.isfinite(value).all() for value in best_model.state_dict().values()):
        raise ValueError('Resume best weights are nonfinite.')
    return model, best_model, payload, state


def write_json(path, data):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def train(config, device_name='cpu', resume=None, check_only=False):
    paths, device, manifest = prepare_run(config, device_name)
    digest = manifest_digest(manifest)
    runtime = runtime_info(device)
    seed_everything(config.seed)
    restored = resume_state(config, resume, digest, runtime) if resume else None
    summary = dict(device=str(device), class_names=list(config.class_names),
                   split_counts={split: len(rows) for split, rows in manifest['splits'].items()},
                   image_size=config.image_size, batch_size=config.batch_size, epochs=config.epochs,
                   optimizer=config.optimizer, learning_rate=config.learning_rate,
                   manifest_digest=digest, outputs={key: str(path) for key, path in paths.items()},
                   runtime=runtime, check_only=check_only)
    print(json.dumps(summary, indent=2), flush=True)
    if check_only:
        print('Preflight passed. No batches, optimizer steps, or output files created.', flush=True)
        return summary

    if restored:
        model, best_model, payload, state = restored
        start, steps = payload['completed_epochs'] + 1, payload['optimizer_steps']
        best_loss, best_epoch = state['best_loss'], state['best_epoch']
        best_steps, history = state['best_steps'], state['history']
    else:
        model = HybridCNNTransformer(config)
        best_model, best_loss, best_epoch, best_steps = None, float('inf'), 0, 0
        start, steps, history = 1, 0, []
    model.to(device)
    optimizer = build_optimizer(model, config)
    if restored:
        optimizer.load_state_dict(payload['optimizer_state_dict'])
    paths['run'].parent.mkdir(parents=True, exist_ok=True)
    # Reserve this output prefix exclusively; fresh and resumed runs never reuse files.
    with paths['run'].open('x') as output:
        json.dump(dict(**summary, config=config.to_dict(), seed_policy=SEED_POLICY,
                       resumed_from=str(resume) if resume else None), output, indent=2)
        output.write('\n')
    if restored:
        save_checkpoint(paths['best'], best_model, None, config, best_epoch, best_steps, best_loss, digest)

    for epoch in range(start, config.epochs + 1):
        started = time.perf_counter()
        epoch_seed = (config.seed + epoch - 1) % 2**32
        seed_everything(epoch_seed)
        # Recreate loaders per epoch to reproduce shuffle/augmentation after resume.
        training = run_epoch(model, loader(config, manifest, 'train', seed=epoch_seed), device, optimizer)
        validation = run_epoch(model, loader(config, manifest, 'val', seed=epoch_seed), device)
        steps += training['optimizer_steps']
        history.append(dict(epoch=epoch, train=training, validation=validation))
        if validation['loss'] < best_loss:
            best_loss, best_epoch, best_steps = validation['loss'], epoch, steps
            best_model = copy.deepcopy(model).cpu().eval()
            save_checkpoint(paths['best'], best_model, None, config, best_epoch, best_steps, best_loss, digest)
        # Last is authoritative for resume, including the best weights/history.
        # A partial epoch or failed write never advances this checkpoint.
        state = dict(version=1, seed_policy=SEED_POLICY, runtime=runtime, history=history,
                     best_loss=best_loss, best_epoch=best_epoch, best_steps=best_steps,
                     best_state_dict=best_model.state_dict())
        save_checkpoint(paths['last'], model, optimizer, config, epoch, steps, validation['loss'], digest,
                        training_state=state)
        write_json(paths['history'], history)
        print(f"Epoch {epoch}/{config.epochs} | train_loss={training['loss']:.6f} "
              f"val_loss={validation['loss']:.6f} val_accuracy={validation['accuracy']:.6f} "
              f"steps={steps} elapsed={time.perf_counter() - started:.2f}s", flush=True)
    print(f"Training finished. Best epoch: {best_epoch}. Best checkpoint: {paths['best']}. "
          'Test split was not used for model selection.', flush=True)
    return history
