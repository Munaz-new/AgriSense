from io import BytesIO
from pathlib import Path
from PIL import Image
import torch
from .checkpoints import ARCHITECTURE, load_checkpoint
from .data import preprocess


class CropClassifier:
    """Image-only classifier. No random/untrained fallback and no severity estimate."""
    def __init__(self, checkpoint: Path, expected_config=None):
        self.model, self.config, self.metadata = load_checkpoint(checkpoint, expected_config=expected_config)

    def predict(self, image: bytes) -> dict:
        with Image.open(BytesIO(image)) as decoded:
            tensor = preprocess(decoded, self.config.image_size, augment=False).unsqueeze(0)
        with torch.inference_mode():
            logits = self.model(tensor)
            if (not isinstance(logits, torch.Tensor)
                    or logits.shape != (1, self.config.num_classes)
                    or not logits.is_floating_point() or not torch.isfinite(logits).all()):
                raise ValueError('Model produced invalid logits for the configured class mapping.')
            probabilities = torch.softmax(logits, dim=1)[0]
        if not torch.isfinite(probabilities).all():
            raise ValueError('Model produced invalid probabilities.')
        index = int(probabilities.argmax())
        return {'disease': self.config.class_names[index], 'severity': None,
                'confidence': float(probabilities[index]) * 100,
                'predictor': ARCHITECTURE, 'is_mock': False}


TomatoClassifier = CropClassifier  # Compatibility alias for the existing backend adapter.
