"""Explicit training entry point. Requires the supplied dataset and prepared manifest."""
import argparse
import json
import torch
from .agrisense_model.architecture import HybridCNNTransformer
from .agrisense_model.checkpoints import save_checkpoint
from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.data import load_manifest, manifest_digest
from .agrisense_model.engine import loader, run_epoch, seed_everything


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    config = load_config(args.config)
    checkpoint = config.path('checkpoint_path')
    if checkpoint.exists():
        raise SystemExit(f'Refusing to overwrite {checkpoint}. Configure a new checkpoint path for a new run.')
    manifest = load_manifest(config)
    seed_everything(config.seed)
    device = torch.device(args.device)
    model = HybridCNNTransformer(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=0.01)
    train_loader, val_loader = loader(config, manifest, 'train'), loader(config, manifest, 'val')
    best_loss, steps = float('inf'), 0
    history = []
    for epoch in range(1, config.epochs + 1):
        training = run_epoch(model, train_loader, device, optimizer)
        validation = run_epoch(model, val_loader, device)
        steps += training['optimizer_steps']
        record = {'epoch': epoch, 'train': training, 'validation': validation}
        history.append(record)
        print(json.dumps(record), flush=True)
        if validation['loss'] < best_loss:
            best_loss = validation['loss']
            save_checkpoint(checkpoint, model, optimizer, config, epoch, steps, best_loss, manifest_digest(manifest))
        checkpoint.with_suffix('.history.json').write_text(json.dumps(history, indent=2) + '\n')
    print(f'Best validation-loss checkpoint: {checkpoint}. Test split was not used for model selection.')


if __name__ == '__main__':
    main()
