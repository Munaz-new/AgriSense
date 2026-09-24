"""Read-only source inspection and deterministic, auditable manifest curation."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import random

from PIL import Image, ImageOps, UnidentifiedImageError

from .data import EXTENSIONS, image_digest

POLICY = 'train-valid-exact-pixels-v1'


def source_files(config):
    root = config.path('dataset_path').resolve()
    if not root.is_dir():
        raise ValueError(f'Dataset not found: {root}')
    if {p.name for p in root.iterdir()} != {'train', 'valid'}:
        raise ValueError('train-valid layout requires exactly train/ and valid/ at the source root.')
    result = []
    for split in ('train', 'valid'):
        folder = root / split
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Source split must be a real directory.')
        if {p.name for p in folder.iterdir()} != set(config.class_names):
            raise ValueError(f'Class folders mismatch in {folder}')
        for label, name in enumerate(config.class_names):
            class_dir = folder / name
            if class_dir.is_symlink() or not class_dir.is_dir():
                raise ValueError('Class folder must be a real directory.')
            for path in sorted(class_dir.rglob('*')):
                if path.is_symlink():
                    raise ValueError(f'Symlink not allowed in source: {path}')
                if path.is_file():
                    result.append((split, label, path))
    return root, result


def summarize(rows, classes, split_key):
    result = {}
    for row in rows:
        counts = result.setdefault(row[split_key], {name: 0 for name in classes})
        counts[classes[row['label']]] += 1
    return result


def prepare_train_valid(config):
    root, files = source_files(config)
    inventory, exclusions = [], []
    groups = defaultdict(list)
    for split, label, path in files:
        before = path.stat()
        row = dict(path=path.relative_to(root).as_posix(), source_split=split,
                   label=label, bytes=before.st_size,
                   file_sha256=sha256(path.read_bytes()).hexdigest())
        inventory.append(row)
        if path.suffix.lower() not in EXTENSIONS:
            exclusions.append(dict(path=row['path'], reason='unsupported_extension'))
        else:
            try:
                with Image.open(path) as image:
                    row['format'] = image.format
                    row['size'] = list(ImageOps.exif_transpose(image).size)
                    # verify() must run on a newly opened image (EXIF transpose may load it).
                with Image.open(path) as image:
                    image.verify()
                row['digest'] = image_digest(path)
                groups[row['digest']].append(row)
            except (OSError, SyntaxError, ValueError, UnidentifiedImageError,
                    Image.DecompressionBombError) as error:
                exclusions.append(dict(path=row['path'], reason='unreadable_image',
                                       detail=f'{type(error).__name__}: {error}'))
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'Source changed during audit: {path}')

    selected = {'train': [], 'val': [], 'test': []}
    duplicate_groups, conflicts = [], []
    for digest, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row['path'])
        paths = [row['path'] for row in rows]
        if len(rows) > 1:
            duplicate_groups.append(dict(digest=digest, paths=paths))
        if len({row['label'] for row in rows}) > 1:
            conflicts.append(dict(digest=digest, paths=paths))
            exclusions.extend(dict(path=row['path'], reason='conflicting_labels',
                                   digest=digest) for row in rows)
            continue
        valid = [row for row in rows if row['source_split'] == 'valid']
        kept = (valid or rows)[0]
        selected['val' if valid else 'train'].append(kept)
        for row in rows:
            if row is kept:
                continue
            reason = ('train_validation_overlap' if valid and row['source_split'] == 'train'
                      else 'within_split_duplicate')
            exclusions.append(dict(path=row['path'], reason=reason, digest=digest,
                                   retained_path=kept['path']))

    rng = random.Random(config.seed)
    train = selected['train']
    selected['train'] = []
    for label in range(config.num_classes):
        candidates = sorted((row for row in train if row['label'] == label), key=lambda row: row['path'])
        if len(candidates) < 2 or not any(row['label'] == label for row in selected['val']):
            raise ValueError(f'{config.class_names[label]} lacks usable train/validation coverage after curation.')
        rng.shuffle(candidates)
        n_test = max(1, int(len(candidates) * config.test_fraction))
        selected['test'].extend(candidates[:n_test])
        selected['train'].extend(candidates[n_test:])

    splits = {split: [dict(path=row['path'], label=row['label'], digest=row['digest'])
                      for row in sorted(rows, key=lambda row: (row['label'], row['path']))]
              for split, rows in selected.items()}
    hashes = [row['digest'] for rows in splits.values() for row in rows]
    if len(hashes) != len(set(hashes)):
        raise ValueError('Internal error: duplicate survived curation.')
    original = summarize(inventory, config.class_names, 'source_split')
    manifest = dict(version=2, crop_name=config.crop_name, seed=config.seed,
                    class_names=list(config.class_names), splits=splits,
                    policy=dict(name=POLICY, test_fraction_of_clean_train=config.test_fraction,
                                validation='preserve cleaned valid; logical key val',
                                grouping='exact decoded RGB pixels only; source/near-duplicate review pending'),
                    source_root=str(root), inventory=inventory,
                    exclusions=sorted(exclusions, key=lambda row: row['path']),
                    duplicate_groups=duplicate_groups, conflicting_label_groups=conflicts)
    manifest['summary'] = dict(
        original_per_class=original,
        original_counts={split: sum(counts.values()) for split, counts in original.items()},
        usable_counts={split: len(rows) for split, rows in splits.items()},
        usable_per_class={split: dict(Counter(config.class_names[row['label']] for row in rows))
                          for split, rows in splits.items()},
        exclusion_counts=dict(sorted(Counter(row['reason'] for row in exclusions).items())),
        original_cross_split_duplicate_groups=sum(
            len({row['source_split'] for row in rows}) > 1 for rows in groups.values()),
        original_conflicting_label_groups=len(conflicts),
        unique_readable_pixel_hashes=len(groups),
        remaining_exact_duplicate_groups=0,
        below_224_source_images=sum(min(row.get('size', [224, 224])) < 224 for row in inventory),
        near_duplicates_checked=False)
    if len(inventory) != len(exclusions) + sum(map(len, splits.values())):
        raise ValueError('Internal error: audit does not account for every source file.')
    return manifest


def validate_audit(config, manifest):
    """Bind curated membership to its class map, source bytes and exclusion ledger."""
    if manifest.get('crop_name') != config.crop_name:
        raise ValueError('Manifest crop mapping mismatch.')
    if manifest.get('policy', {}).get('name') != POLICY:
        raise ValueError('Unknown preparation policy.')
    root, files = source_files(config)
    inventory = {row['path']: row for row in manifest['inventory']}
    if len(inventory) != len(manifest['inventory']):
        raise ValueError('Duplicate inventory paths.')
    actual = {path.relative_to(root).as_posix(): (split, label, path) for split, label, path in files}
    if set(actual) != set(inventory):
        raise ValueError('Dataset inventory changed after preparation.')
    for name, (split, label, path) in actual.items():
        row = inventory[name]
        if row['source_split'] != split or row['label'] != label:
            raise ValueError('Inventory class or source split mismatch.')
        if row['file_sha256'] != sha256(path.read_bytes()).hexdigest():
            raise ValueError(f'Dataset changed after split preparation: {path}')
    excluded = [row['path'] for row in manifest['exclusions']]
    selected = [row['path'] for rows in manifest['splits'].values() for row in rows]
    if (len(set(excluded)) != len(excluded) or len(set(selected)) != len(selected)
            or set(excluded) & set(selected) or set(excluded) | set(selected) != set(inventory)):
        raise ValueError('Manifest membership/exclusions do not partition source inventory.')
    hashes = set()
    for split, rows in manifest['splits'].items():
        if split not in {'train', 'val', 'test'}:
            raise ValueError('Unexpected logical split.')
        for row in rows:
            source = inventory[row['path']]
            if row['label'] != source['label'] or row['digest'] != source.get('digest'):
                raise ValueError('Manifest membership differs from audited class/digest.')
            if (source['source_split'] == 'valid') != (split == 'val'):
                raise ValueError('Manifest violates source validation membership.')
            if row['digest'] in hashes:
                raise ValueError('Manifest contains duplicate decoded images.')
            hashes.add(row['digest'])
