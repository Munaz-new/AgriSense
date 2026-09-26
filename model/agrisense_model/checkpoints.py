"""Only our versioned, completed-training checkpoints may enter inference."""
from pathlib import Path
import math
import json
from hashlib import sha256
import torch
from .architecture import HybridCNNTransformer
from .config import Config
from .data import PREPROCESSING

ARCHITECTURE = 'agrisense-parallel-cnn-transformer-v1'


def class_mapping_digest(config):
    return sha256(json.dumps([config.crop_name, list(config.class_names)],
                             ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def save_checkpoint(path: Path, model, optimizer, config, epoch, steps, validation_loss, split_digest,
                    training_state=None):
    if epoch < 1 or steps < 1 or not math.isfinite(validation_loss):
        raise ValueError('Refusing to label an untrained/nonfinite model as a trained checkpoint.')
    payload = {
        'format_version': 2, 'class_mapping_digest': class_mapping_digest(config), 'architecture': ARCHITECTURE, 'trained': True,
        'completed_epochs': epoch, 'optimizer_steps': steps,
        'validation_loss': validation_loss, 'manifest_digest': split_digest,
        'config': config.to_dict(), 'preprocessing': PREPROCESSING,
        'state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict() if optimizer is not None else {},
    }
    if training_state is not None:
        payload['training_state'] = training_state
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    torch.save(payload, temporary)
    temporary.replace(path)


def load_checkpoint(path: Path, expected_config: Config | None = None):
    if not path.is_file():
        raise FileNotFoundError(f'No trained checkpoint: {path}. The application must remain in mock mode.')
    payload = torch.load(path, map_location='cpu', weights_only=True)
    if not isinstance(payload, dict) or payload.get('format_version') != 2:
        raise ValueError('Unsupported checkpoint format.')
    if (payload.get('architecture') != ARCHITECTURE or payload.get('trained') is not True
            or payload.get('completed_epochs', 0) < 1 or payload.get('optimizer_steps', 0) < 1
            or not math.isfinite(payload.get('validation_loss', float('nan')))
            or not payload.get('manifest_digest') or payload.get('preprocessing') != PREPROCESSING):
        raise ValueError('Checkpoint has missing/incompatible training or preprocessing metadata. Refusing inference.')
    if not isinstance(payload.get('config'), dict) or not {'class_names', 'crop_name'} <= payload['config'].keys():
        raise ValueError('Checkpoint must explicitly contain its crop and class mapping.')
    config = Config(**payload['config'])
    if payload.get('class_mapping_digest') != class_mapping_digest(config):
        raise ValueError('Checkpoint class mapping metadata mismatch.')
    if expected_config is not None and class_mapping_digest(config) != class_mapping_digest(expected_config):
        raise ValueError('Checkpoint class mapping does not match expected configuration.')
    model = HybridCNNTransformer(config)
    model.load_state_dict(payload['state_dict'], strict=True)
    if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
        raise ValueError('Checkpoint contains nonfinite weights.')
    model.eval()
    return model, config, payload
