import random
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from .data import CropDataset


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def loader(config, manifest, split):
    generator = torch.Generator().manual_seed(config.seed)
    return DataLoader(CropDataset(config, manifest, split), batch_size=config.batch_size,
                      shuffle=split == 'train', num_workers=0, generator=generator)


def run_epoch(model, batches, device, optimizer=None):
    training = optimizer is not None
    model.train(training)
    total_loss, correct, count, steps = 0.0, 0, 0, 0
    matrix = torch.zeros(model.num_classes, model.num_classes, dtype=torch.long)
    with torch.set_grad_enabled(training):
        for images, labels in batches:
            images, labels = images.to(device), labels.to(device)
            if training:
                optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            if logits.shape != (labels.numel(), model.num_classes):
                raise ValueError('Model output does not match configured class count.')
            loss = nn.functional.cross_entropy(logits, labels)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite loss; stopping without saving this epoch.')
            if training:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
                optimizer.step()
                steps += 1
            predicted = logits.argmax(1)
            count += labels.numel()
            total_loss += loss.item() * labels.numel()
            correct += (predicted == labels).sum().item()
            for actual, guess in zip(labels.cpu().tolist(), predicted.cpu().tolist()):
                matrix[actual, guess] += 1
    if count == 0:
        raise ValueError('Cannot measure an empty dataset.')
    return {'loss': total_loss / count, 'accuracy': correct / count,
            'samples': count, 'confusion_matrix': matrix.tolist(), 'optimizer_steps': steps}


def classification_report(matrix, class_names):
    matrix = torch.tensor(matrix)
    if matrix.shape != (len(class_names), len(class_names)):
        raise ValueError('Confusion matrix does not match class mapping.')
    report = {}
    for i, name in enumerate(class_names):
        tp = matrix[i, i].item()
        support = matrix[i].sum().item()
        predicted = matrix[:, i].sum().item()
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        report[name] = dict(precision=precision, recall=recall, f1=f1, support=support)
    return {'per_class': report, 'macro_f1': sum(row['f1'] for row in report.values()) / len(report)}
