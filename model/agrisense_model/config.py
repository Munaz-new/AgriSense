from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
DEFAULT_CONFIG = ROOT / 'configs/tomato.json'
TOMATO_CLASSES = (
    'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___Late_blight',
    'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot',
    'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot',
    'Tomato___Tomato_Yellow_Leaf_Curl_Virus', 'Tomato___Tomato_mosaic_virus', 'Tomato___healthy',
)


@dataclass
class Config:
    dataset_path: str = 'model/data/tomato'
    manifest_path: str = 'model/data/tomato_splits.json'
    checkpoint_path: str = 'model/checkpoints/tomato_hybrid_best.pt'
    report_path: str = 'model/reports/tomato_test.json'
    image_size: int = 224
    batch_size: int = 16
    learning_rate: float = 0.0003
    epochs: int = 30
    seed: int = 42
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    patch_size: int = 16
    embedding_dim: int = 128
    transformer_heads: int = 4
    transformer_layers: int = 2
    dropout: float = 0.1
    class_names: tuple[str, ...] = TOMATO_CLASSES

    def __post_init__(self):
        self.class_names = tuple(self.class_names)
        if len(self.class_names) != 10 or set(self.class_names) != set(TOMATO_CLASSES):
            raise ValueError('Configuration must contain exactly the ten supported tomato classes.')
        for key in ('image_size', 'batch_size', 'epochs', 'patch_size', 'embedding_dim', 'transformer_heads', 'transformer_layers'):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError(f'{key} must be a positive integer.')
        if self.image_size < 8:
            raise ValueError('Image size must be at least 8 for three CNN pooling layers.')
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError('Seed must be an integer between 0 and 2**32 - 1.')
        if self.image_size % self.patch_size or self.embedding_dim % self.transformer_heads:
            raise ValueError('Image size must divide into patches; embedding dimension must divide into attention heads.')
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0 or not 0 <= self.dropout < 1:
            raise ValueError('Invalid learning rate or dropout.')
        if not (0 < self.validation_fraction < 1 and 0 < self.test_fraction < 1
                and self.validation_fraction + self.test_fraction < 1):
            raise ValueError('Validation/test fractions must leave a nonempty training split.')

    def path(self, name: str) -> Path:
        value = Path(getattr(self, name)).expanduser()
        return value if value.is_absolute() else REPOSITORY / value

    def to_dict(self):
        return asdict(self)


def load_config(path=DEFAULT_CONFIG) -> Config:
    return Config(**json.loads(Path(path).read_text()))
