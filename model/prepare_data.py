"""Inspect sources and create split metadata only; never modify images or train."""
import argparse
import json
from pathlib import Path
from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.data import prepare_manifest, manifest_digest


def write_output(target, manifest, source_root):
    target = Path(target).expanduser().resolve()
    if target.is_relative_to(source_root):
        raise ValueError('Generated metadata must be outside the source dataset.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as output:
        output.write(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--layout', choices=['unsplit', 'presplit', 'train-valid'], default='unsplit')
    parser.add_argument('--dataset-root', help='External source root; does not copy or modify images.')
    parser.add_argument('--dry-run', action='store_true', help='Do not write the active split manifest.')
    parser.add_argument('--audit-output', help='Optional full proposed manifest/audit, outside source data.')
    args = parser.parse_args()
    config = load_config(args.config)
    if args.dataset_root:
        config.dataset_path = str(Path(args.dataset_root).expanduser().resolve())
    source_root = config.path('dataset_path').resolve()
    outputs = ([config.path('manifest_path')] if not args.dry_run else [])
    if args.audit_output:
        outputs.append(Path(args.audit_output).expanduser())
    if len({p.resolve() for p in outputs}) != len(outputs):
        raise SystemExit('Manifest and audit output must have different paths.')
    for target in outputs:
        if target.resolve().is_relative_to(source_root) or target.exists():
            raise SystemExit(f'Refusing existing output or output inside source data: {target}')
    manifest = prepare_manifest(config, args.layout)
    for target in outputs:
        write_output(target, manifest, source_root)
    print(json.dumps(dict(dry_run=args.dry_run, class_names=list(config.class_names),
                          manifest_digest=manifest_digest(manifest),
                          summary=manifest.get('summary', {s: len(rows) for s, rows in manifest['splits'].items()})), indent=2))
    print('No training performed. ' + ('Active manifest not written.' if args.dry_run else
          'Manifest saved. Use the same external dataset_path in your configuration for future runs.'))


if __name__ == '__main__':
    main()
