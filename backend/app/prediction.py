"""Image-only boundary: replace MockPredictor with the trained model later."""
from hashlib import sha256
from typing import Protocol
from pydantic import BaseModel, Field


class Prediction(BaseModel):
    disease: str
    severity: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0, le=100)
    predictor: str
    is_mock: bool


class Predictor(Protocol):
    def predict(self, image: bytes) -> Prediction: ...


class MockPredictor:
    """Synthetic, repeatable demo values. Does NOT diagnose disease or inspect leaves."""
    def predict(self, image: bytes) -> Prediction:
        digest = sha256(image).digest()
        return Prediction(
            disease="Early Blight", severity=10 + digest[0] % 61,
            confidence=85 + digest[1] % 11,
            predictor="development-mock-v1", is_mock=True,
        )


class TrainedTomatoPredictor:
    """Explicit opt-in adapter for a future evaluated checkpoint. Never auto-enabled.

    Install model dependencies in the backend environment before using this class.
    Missing/untrained checkpoints raise; the default app still uses MockPredictor.
    This classifier does not verify plant content and supports TOMATO classes only.
    """
    def __init__(self, checkpoint):
        from pathlib import Path
        checkpoint = Path(checkpoint)
        if not checkpoint.is_file():
            raise FileNotFoundError('No trained tomato checkpoint; keep using the development mock.')
        # Backend can be launched from backend/ without installing model as a package.
        import sys
        repository = str(Path(__file__).resolve().parents[2])
        if repository not in sys.path:
            sys.path.insert(0, repository)
        from model.agrisense_model.inference import TomatoClassifier
        self.classifier = TomatoClassifier(checkpoint)

    def predict(self, image: bytes) -> Prediction:
        return Prediction(**self.classifier.predict(image))
