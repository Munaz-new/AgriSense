from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
DEFAULT_CONFIG = ROOT / 'configs/tomato.json'
TOMATO_CLASSES = (
    'Bacterial_spot', 'Early_blight', 'Late_blight',
    'Leaf_Mold', 'Septoria_leaf_spot',
    'Spider_mites Two-spotted_spider_mite', 'Target_Spot',
    'Tomato_Yellow_Leaf_Curl_Virus', 'Tomato_mosaic_virus', 'healthy', 'powdery_mildew',
)


@dataclass
class Config:
    crop_name: str = 'tomato'
    dataset_path: str = 'model/data/tomato'
    manifest_path: str = 'model/data/tomato_splits.json'
    checkpoint_path: str = 'model/checkpoints/tomato_hybrid_best.pt'
    report_path: str = 'model/reports/tomato_test.json'
    image_size: int = 224
    batch_size: int = 16
    learning_rate: float = 0.0003
    optimizer: str = 'adamw'
    weight_decay: float = 0.01
    momentum: float = 0.9
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
        if not isinstance(self.class_names, (list, tuple)):
            raise ValueError('class_names must be an ordered list or tuple.')
        self.class_names = tuple(self.class_names)
        if (len(self.class_names) < 2 or any(
                not isinstance(name, str) or not name.strip() or name != name.strip()
                or name in {'.', '..'} or '/' in name or '\\' in name or '\x00' in name
                for name in self.class_names)):
            raise ValueError('At least two nonempty, safe class directory names are required.')
        if len(set(self.class_names)) != len(self.class_names):
            raise ValueError('Class names must be unique and explicitly ordered.')
        if not isinstance(self.crop_name, str) or not self.crop_name.strip():
            raise ValueError('crop_name must be nonempty.')
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
        if self.optimizer not in {'adamw', 'sgd'}:
            raise ValueError('optimizer must be adamw or sgd.')
        if (not math.isfinite(self.weight_decay) or self.weight_decay < 0
                or not math.isfinite(self.momentum) or not 0 <= self.momentum < 1):
            raise ValueError('Invalid weight decay or SGD momentum.')
        if not (0 < self.validation_fraction < 1 and 0 < self.test_fraction < 1
                and self.validation_fraction + self.test_fraction < 1):
            raise ValueError('Validation/test fractions must leave a nonempty training split.')

    @property
    def num_classes(self):
        return len(self.class_names)

    def path(self, name: str) -> Path:
        value = Path(getattr(self, name)).expanduser()
        return value if value.is_absolute() else REPOSITORY / value

    def to_dict(self):
        return asdict(self)


def load_config(path=DEFAULT_CONFIG) -> Config:
    return Config(**json.loads(Path(path).read_text()))
