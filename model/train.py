"""Explicit training entry point. Use --check-only for read-only readiness checks."""
import argparse
from dataclasses import replace

from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.training import train


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--epochs', type=int, help='Total target epochs, including completed epochs when resuming.')
    parser.add_argument('--batch-size', type=int)
    parser.add_argument('--learning-rate', type=float)
    parser.add_argument('--optimizer', choices=['adamw', 'sgd'])
    parser.add_argument('--weight-decay', type=float)
    parser.add_argument('--dataset-root', help='External source directory; images are never copied or rewritten.')
    parser.add_argument('--checkpoint', help='New best .pt path; related outputs derive from it.')
    parser.add_argument('--resume', help='Trusted Phase 4A last checkpoint; requires a new output prefix.')
    parser.add_argument('--check-only', action='store_true', help='Validate device, manifest and outputs; no training or writes.')
    args = parser.parse_args(argv)
    overrides = {key: getattr(args, key) for key in
                 ('epochs', 'batch_size', 'learning_rate', 'optimizer', 'weight_decay')
                 if getattr(args, key) is not None}
    if args.dataset_root is not None:
        overrides['dataset_path'] = args.dataset_root
    if args.checkpoint is not None:
        overrides['checkpoint_path'] = args.checkpoint
    config = replace(load_config(args.config), **overrides)
    train(config, args.device, resume=args.resume, check_only=args.check_only)


if __name__ == '__main__':
    main()
