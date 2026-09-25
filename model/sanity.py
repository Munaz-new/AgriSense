"""One disposable CPU batch, one optimizer step; never save model weights.

Run with python -m model.sanity --help. Requires the existing Phase 3A audit
and active manifest; does not prepare data or run a full epoch.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import time
import warnings

import torch
from torch.utils.data import DataLoader, Subset

from model.agrisense_model.architecture import HybridCNNTransformer
from model.agrisense_model.config import TOMATO_CLASSES, load_config
from model.agrisense_model.data import CropDataset, load_manifest, manifest_digest
from model.agrisense_model.engine import seed_everything
from model.agrisense_model.preparation import source_files


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def snapshot(config):
    root, files = source_files(config)
    result = {}
    for _, _, path in files:
        stat = path.stat()
        result[path.relative_to(root).as_posix()] = {
            'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'sha256': sha256(path.read_bytes()).hexdigest(),
        }
    return result


def peak_rss_mib():
    # resource is unavailable on Windows; do not invent a memory measurement.
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024 if sys.platform == 'darwin' else 1024)


def validate_inputs(config, audit_path, report_path):
    require(config.class_names == TOMATO_CLASSES and config.crop_name == 'tomato',
            'Expected the validated ordered eleven tomato classes.')
    require(config.image_size == 224, 'Sanity check requires the configured 224-pixel input.')
    require(config.path('manifest_path').is_file(), 'Active manifest is required.')
    require(audit_path.is_file(), 'Existing Phase 3A audit is required.')
    require(not report_path.exists(), 'Refusing to overwrite existing sanity report.')
    require(not report_path.resolve().is_relative_to(config.path('dataset_path').resolve()),
            'Sanity report must be outside the source dataset.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Local config with the source dataset path.')
    parser.add_argument('--audit', required=True, help='Existing Phase 3A audit JSON.')
    parser.add_argument('--report', default='model/reports/tomato_sanity.json',
                        help='New local report path outside the source dataset; never overwritten.')
    args = parser.parse_args(argv)
    started, cpu_started = time.perf_counter(), time.process_time()
    config = load_config(args.config)
    audit_path = Path(args.audit).expanduser()
    report_path = Path(args.report).expanduser()
    validate_inputs(config, audit_path, report_path)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    report = dict(purpose='Phase 3B software readiness only; not model evaluation',
                  device='cpu', python=platform.python_version(), torch=torch.__version__,
                  cuda_available=torch.cuda.is_available(), cuda_build=torch.version.cuda,
                  logical_cpu_count=os.cpu_count(), torch_threads=torch.get_num_threads(),
                  full_training=False, checkpoint_saved=False, errors=[], warnings=[])
    before = snapshot(config)
    report['source_files_checked'] = len(before)
    print(f'Snapshotted {len(before)} source files; validating Phase 3A manifest.', flush=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            stage = time.perf_counter()
            manifest = load_manifest(config)
            audit = json.loads(audit_path.read_text())
            require(manifest == audit, 'Active manifest differs from Phase 3A audit.')
            require(manifest.get('version') == 2, 'Expected the Phase 3A audited manifest.')
            report['manifest_validation_seconds'] = time.perf_counter() - stage
            report['manifest_digest'] = manifest_digest(manifest)
            report['manifest_matches_phase3a'] = True
            report['split_counts'] = {key: len(rows) for key, rows in manifest['splits'].items()}
            report['class_mapping'] = dict(enumerate(config.class_names))
            report['num_classes'] = config.num_classes
            require(all(before[row['path']]['sha256'] == row['file_sha256']
                        for row in manifest['inventory']), 'Source differs from audited bytes.')
            datasets = {split: CropDataset(config, manifest, split) for split in manifest['splits']}
            indices = [next(i for i, row in enumerate(datasets['train'].entries)
                            if row['label'] == label) for label in range(config.num_classes)]
            report['selected_training_paths'] = [datasets['train'].entries[i]['path'] for i in indices]
            print('Manifest valid. Running one batch: 11 images, one per class.', flush=True)
            stage, training_cpu_started = time.perf_counter(), time.process_time()
            seed_everything(config.seed)
            batches = DataLoader(Subset(datasets['train'], indices), batch_size=11,
                                 shuffle=False, num_workers=0,
                                 generator=torch.Generator().manual_seed(config.seed))
            require(len(batches) == 1, 'Sanity run must contain exactly one batch.')
            images, labels = next(iter(batches))
            require(images.shape == (11, 3, 224, 224) and images.dtype == torch.float32
                    and bool(torch.isfinite(images).all()), 'Invalid input batch.')
            require(labels.shape == (11,) and labels.dtype == torch.int64
                    and labels.tolist() == list(range(11)), 'Incorrect labels or class mapping.')
            report.update(samples=11, batches=1, input_shape=list(images.shape),
                          input_dtype=str(images.dtype), label_shape=list(labels.shape),
                          label_dtype=str(labels.dtype), labels=labels.tolist(), batch_creation=True,
                          validation_samples_forwarded=0, test_samples_forwarded=0)
            model = HybridCNNTransformer(config).train()
            optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=0.01)
            weights_before = {name: p.detach().clone() for name, p in model.named_parameters()}
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            require(logits.shape == (11, 11) and bool(torch.isfinite(logits).all()), 'Invalid logits.')
            report.update(forward_pass=True, output_shape=list(logits.shape))
            loss = torch.nn.functional.cross_entropy(logits, labels)
            require(loss.ndim == 0 and bool(torch.isfinite(loss)), 'Nonfinite or nonscalar loss.')
            report.update(loss_calculation=True, diagnostic_loss=float(loss.detach()),
                          loss_note='Random initialization on one batch; not a research result.')
            loss.backward()
            require(all(p.grad is not None and bool(torch.isfinite(p.grad).all())
                        for p in model.parameters()), 'Missing or nonfinite gradients.')
            probes = ['cnn.0.weight', 'patch_embedding.weight', 'position',
                      'transformer.0.self_attn.in_proj_weight', 'classifier.3.weight']
            params = dict(model.named_parameters())
            require(all(bool(params[name].grad.abs().sum() > 0) for name in probes),
                    'A model branch has zero gradient.')
            report['backward_propagation'] = True
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            report['gradient_norm_before_clipping'] = float(norm)
            optimizer.step()
            require(all(bool(torch.isfinite(p).all()) for p in model.parameters()), 'Nonfinite weights.')
            require(all(not torch.equal(weights_before[name], params[name]) for name in probes),
                    'Optimizer did not update a model branch.')
            require(all(float(state['step']) == 1 for state in optimizer.state.values()),
                    'Expected exactly one optimizer step.')
            report.update(optimizer_step=True, optimizer_steps=1,
                          changed_branch_probes=probes,
                          parameter_count=sum(p.numel() for p in model.parameters()),
                          sanity_seconds=time.perf_counter() - stage,
                          sanity_cpu_seconds=time.process_time() - training_cpu_started)
        except Exception as error:
            report['errors'].append(f'{type(error).__name__}: {error}')
        finally:
            report['warnings'] = [f'{w.category.__name__}: {w.message}' for w in caught]
    after = snapshot(config)
    report['source_unchanged'] = before == after
    report['source_snapshot_sha256'] = sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    report['source_integrity_method'] = 'All paths, sizes, mtimes, SHA-256 before/after; bytes also match Phase 3A.'
    if before != after:
        report['errors'].append('Source snapshot changed during sanity test.')
    report['total_seconds'] = time.perf_counter() - started
    report['process_cpu_seconds'] = time.process_time() - cpu_started
    report['process_average_cpu_percent_one_core_basis'] = 100 * report['process_cpu_seconds'] / report['total_seconds']
    report['process_peak_rss_mib'] = peak_rss_mib()
    report['gpu_usage'] = 'Not measured: this bounded runner uses CPU only.'
    report['passed'] = not report['errors'] and report.get('optimizer_step', False) and report['source_unchanged']
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open('x') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps(report, indent=2), flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
