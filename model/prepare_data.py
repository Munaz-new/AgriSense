"""Create split metadata only; never downloads or trains anything."""
import argparse
import json
from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.data import prepare_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--layout', choices=['unsplit', 'presplit'], default='unsplit')
    args = parser.parse_args()
    config = load_config(args.config)
    target = config.path('manifest_path')
    if target.exists():
        raise SystemExit(f'Refusing to overwrite existing split manifest: {target}. Use a new path for a new experiment.')
    manifest = prepare_manifest(config, args.layout)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({split: len(entries) for split, entries in manifest['splits'].items()}))
    print(f'Saved {target}. Inspect splits and source provenance before training.')


if __name__ == '__main__':
    main()
