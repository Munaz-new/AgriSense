"""Inference contracts with in-memory test doubles; no trained weights or metrics."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest
import torch

from model.agrisense_model.config import Config, TOMATO_CLASSES, load_config
from model.agrisense_model.data import CropDataset
from model.agrisense_model.inference import CropClassifier


class OutputStub(torch.nn.Module):
    """Fixed test data only, never a disease classifier."""
    def __init__(self, output):
        super().__init__()
        self.output = output
        self.inputs = []

    def forward(self, images):
        assert torch.is_inference_mode_enabled()
        self.inputs.append(images.clone())
        return self.output


def image_bytes(mode='RGB'):
    image = Image.new(mode, (256, 320))
    image.paste('white', (0, 0, 128, 160))
    exif = image.getexif()
    exif[274] = 6  # Exercise EXIF orientation as well as RGB conversion.
    data = BytesIO()
    image.save(data, format='PNG', exif=exif)
    return data.getvalue()


@pytest.mark.parametrize('mode', ['RGB', 'L', 'RGBA'])
def test_inference_matches_validation_preprocessing_at_224(tmp_path, mode):
    data = image_bytes(mode)
    (tmp_path / 'fixture.png').write_bytes(data)
    config = Config(dataset_path=str(tmp_path))
    dataset = CropDataset(config, {'splits': {'val': [{'path': 'fixture.png', 'label': 0}]}}, 'val')
    expected, _ = dataset[0]
    stub = OutputStub(torch.zeros(1, config.num_classes))
    with patch('model.agrisense_model.inference.load_checkpoint', return_value=(stub, config, {})), \
            patch('model.agrisense_model.data.random.random', side_effect=AssertionError('Augmentation in inference')):
        classifier = CropClassifier(Path('unused-test-double'))
        first = classifier.predict(data)
        second = classifier.predict(data)
    assert first == second
    assert stub.inputs[0].shape == (1, 3, 224, 224)
    assert stub.inputs[0].dtype == torch.float32
    assert torch.isfinite(stub.inputs[0]).all()
    assert torch.equal(stub.inputs[0][0], expected)
    assert torch.equal(stub.inputs[0], stub.inputs[1])


@pytest.mark.parametrize('label', range(11))
def test_each_logit_index_maps_to_exact_tomato_class(label):
    config = load_config()
    assert config.class_names == TOMATO_CLASSES
    assert config.class_names[10] == 'powdery_mildew'
    logits = torch.zeros(1, 11)
    logits[0, label] = 1  # Synthetic routing fixture, not a prediction on a real leaf.
    with patch('model.agrisense_model.inference.load_checkpoint',
               return_value=(OutputStub(logits), config, {})):
        result = CropClassifier(Path('unused-test-double')).predict(image_bytes())
    assert result['disease'] == config.class_names[label]
    assert result['severity'] is None


@pytest.mark.parametrize('output', [
    [[0.] * 11], torch.zeros(11), torch.zeros(2, 11), torch.zeros(1, 10),
    torch.zeros(1, 12), torch.zeros(1, 11, dtype=torch.int64),
    torch.full((1, 11), float('nan')), torch.full((1, 11), float('inf')),
])
def test_malformed_outputs_fail_without_returning_a_prediction(output):
    with patch('model.agrisense_model.inference.load_checkpoint',
               return_value=(OutputStub(output), load_config(), {})):
        classifier = CropClassifier(Path('unused-test-double'))
    with pytest.raises(ValueError, match='invalid logits'):
        classifier.predict(image_bytes())


def test_missing_checkpoint_never_constructs_a_random_model(tmp_path):
    with patch('model.agrisense_model.checkpoints.HybridCNNTransformer') as factory:
        with pytest.raises(FileNotFoundError, match='No trained checkpoint'):
            CropClassifier(tmp_path / 'missing.pt', expected_config=load_config())
        factory.assert_not_called()


def test_incompatible_checkpoint_is_not_replaced_with_fallback():
    with patch('model.agrisense_model.inference.load_checkpoint',
               side_effect=ValueError('Checkpoint class mapping mismatch.')):
        with pytest.raises(ValueError, match='mapping mismatch'):
            CropClassifier(Path('unused-rejected-checkpoint'), expected_config=load_config())
