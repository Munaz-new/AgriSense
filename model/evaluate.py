"""Evaluate a completed-training checkpoint once on the held-out test split."""
import argparse
import json
import torch
from .agrisense_model.checkpoints import load_checkpoint
from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.data import load_manifest, manifest_digest
from .agrisense_model.engine import classification_report, loader, run_epoch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config = load_config(args.config)
    model, trained_config, metadata = load_checkpoint(config.path('checkpoint_path'), expected_config=config)
    if config.class_names != trained_config.class_names:
        raise ValueError('Evaluation class order does not match checkpoint.')
    manifest = load_manifest(config)
    if manifest_digest(manifest) != metadata['manifest_digest']:
        raise ValueError('Split manifest differs from training. Refusing ambiguous test evaluation.')
    # Checkpoint preprocessing settings are authoritative; data location can move.
    trained_config.dataset_path = str(config.path('dataset_path'))
    trained_config.batch_size = config.batch_size
    metrics = run_epoch(model, loader(trained_config, manifest, 'test'), torch.device('cpu'))
    metrics.pop('optimizer_steps')
    metrics.update(classification_report(metrics['confusion_matrix'], config.class_names))
    metrics.update(class_names=list(config.class_names), split='test',
                   manifest_digest=metadata['manifest_digest'], checkpoint=str(config.path('checkpoint_path')),
                   note='Measured held-out dataset results, not clinical/field validation; probabilities are uncalibrated.')
    report = config.path('report_path')
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(metrics, indent=2) + '\n')
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
