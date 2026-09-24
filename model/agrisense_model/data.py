"""PlantVillage-style folders, explicit class order, and persisted split membership."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import torch
from torch.utils.data import Dataset
from .config import Config

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
PREPROCESSING = 'rgb-resize-bilinear-imagenet-normalization-v1'


def image_digest(path: Path) -> str:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.load()
        return sha256(str(image.size).encode() + image.tobytes()).hexdigest()


def scan_classes(root: Path, classes):
    if not root.is_dir():
        raise ValueError(f'Dataset not found: {root}. Supply the real dataset first.')
    directories = {p.name for p in root.iterdir() if p.is_dir()}
    if directories != set(classes):
        raise ValueError(f'Class folders mismatch in {root}. Missing: {set(classes) - directories}; unexpected: {directories - set(classes)}')
    entries = []
    for label, name in enumerate(classes):
        files = sorted(p for p in (root / name).rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS)
        if not files:
            raise ValueError(f'No supported images in {root / name}')
        for path in files:
            entries.append({'path': path, 'label': label, 'digest': image_digest(path)})
    return entries


def prepare_manifest(config: Config, layout='unsplit'):
    if layout == 'train-valid':
        from .preparation import prepare_train_valid
        return prepare_train_valid(config)
    if layout not in {'unsplit', 'presplit'}:
        raise ValueError('Unknown dataset layout.')
    root = config.path('dataset_path').resolve()
    rng = random.Random(config.seed)
    splits = {name: [] for name in ('train', 'val', 'test')}
    if layout == 'presplit':
        for split in splits:
            splits[split] = scan_classes(root / split, config.class_names)
    else:
        entries = scan_classes(root, config.class_names)
        groups = defaultdict(list)
        for item in entries:
            groups[item['digest']].append(item)
        per_class = defaultdict(list)
        for group in groups.values():
            labels = {item['label'] for item in group}
            if len(labels) != 1:
                raise ValueError('Identical decoded images have conflicting class labels.')
            per_class[group[0]['label']].append(group)
        for label in range(len(config.class_names)):
            groups_for_class = per_class[label]
            if len(groups_for_class) < 3:
                raise ValueError(f'{config.class_names[label]} needs at least 3 unique images for three splits.')
            rng.shuffle(groups_for_class)
            n = len(groups_for_class)
            n_val = max(1, int(n * config.validation_fraction))
            n_test = max(1, int(n * config.test_fraction))
            if n_val + n_test >= n:
                raise ValueError('Too few unique images for the configured split fractions.')
            for split, selected in [('val', groups_for_class[:n_val]),
                                    ('test', groups_for_class[n_val:n_val + n_test]),
                                    ('train', groups_for_class[n_val + n_test:])]:
                splits[split].extend(item for group in selected for item in group)
    seen = {}
    for split, entries in splits.items():
        for entry in entries:
            previous = seen.setdefault(entry['digest'], (split, entry['label']))
            if previous != (split, entry['label']):
                raise ValueError('Identical decoded images cross splits or have conflicting labels.')
            entry['path'] = entry['path'].resolve().relative_to(root).as_posix()
    return {'version': 1, 'crop_name': config.crop_name, 'seed': config.seed, 'class_names': list(config.class_names), 'splits': splits}


def load_manifest(config: Config):
    path = config.path('manifest_path')
    if not path.is_file():
        raise ValueError(f'Split manifest missing: {path}. Run model.prepare_data first.')
    manifest = json.loads(path.read_text())
    if manifest.get('version') not in {1, 2} or manifest['class_names'] != list(config.class_names):
        raise ValueError('Manifest version or class mapping mismatch.')
    if manifest.get('crop_name') != config.crop_name:
        raise ValueError('Manifest crop mapping mismatch.')
    if manifest.get('version') == 2:
        from .preparation import validate_audit
        validate_audit(config, manifest)
    seen_paths, seen_hashes = set(), {}
    root = config.path('dataset_path').resolve()
    for split in ('train', 'val', 'test'):
        entries = manifest['splits'][split]
        if {e['label'] for e in entries} != set(range(config.num_classes)):
            raise ValueError(f'{split} must contain every class.')
        for entry in entries:
            if type(entry['label']) is not int or not 0 <= entry['label'] < config.num_classes:
                raise ValueError('Invalid class label in manifest.')
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root) or path in seen_paths:
                raise ValueError('Manifest contains duplicate or out-of-root paths.')
            seen_paths.add(path)
            if image_digest(path) != entry['digest']:
                raise ValueError(f'Dataset changed after split preparation: {path}')
            previous = seen_hashes.setdefault(entry['digest'], (split, entry['label']))
            if previous != (split, entry['label']):
                raise ValueError('Manifest contains cross-split duplicates or conflicting labels.')
    return manifest


def manifest_digest(manifest) -> str:
    return sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def preprocess(image: Image.Image, image_size: int, augment=False):
    image = ImageOps.exif_transpose(image).convert('RGB')
    if augment:
        if random.random() < 0.5:
            image = ImageOps.mirror(image)
        image = image.rotate(random.uniform(-15, 15), resample=Image.Resampling.BILINEAR)
        image = ImageEnhance.Brightness(image).enhance(random.uniform(0.9, 1.1))
        image = ImageEnhance.Contrast(image).enhance(random.uniform(0.9, 1.1))
    image = image.resize((image_size, image_size), Image.Resampling.BILINEAR)
    tensor = torch.from_numpy(np.array(image, dtype=np.float32) / 255.0).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406])[:, None, None]
    std = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
    return (tensor - mean) / std


class CropDataset(Dataset):
    def __init__(self, config: Config, manifest, split: str):
        self.config, self.entries, self.split = config, manifest['splits'][split], split

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        entry = self.entries[index]
        with Image.open(self.config.path('dataset_path') / entry['path']) as image:
            tensor = preprocess(image, self.config.image_size, augment=self.split == 'train')
        return tensor, entry['label']


# Backward-compatible import; implementation is crop-agnostic.
TomatoDataset = CropDataset
