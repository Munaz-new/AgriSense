"""Pretrained, zero-shot image suitability screening before tomato inference.

This verifier is separate from the closed-set disease classifier. Its similarity
values are not probabilities or an accuracy claim. Ambiguous images abstain.
"""
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
import glob
import os
import logging

from PIL import Image, ImageOps


class Suitability(str, Enum):
    PLANT = "plant"
    NON_PLANT = "non_plant"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class SuitabilityResult:
    outcome: Suitability
    message: str
    plant_similarity: float | None = None
    unrelated_similarity: float | None = None


class PlantContentVerifier:
    """OpenCLIP ViT-B/32 pretrained on OpenAI data, with conservative abstention."""

    PLANT_PROMPTS = (
        "a close-up photograph of a green plant leaf",
        "a photograph of a tomato plant leaf with visible disease spots",
        "a photograph of a healthy tomato leaf",
        "a photograph of foliage on a living plant",
    )
    UNRELATED_PROMPTS = (
        "a document with text and a logo",
        "a company logo or brand graphic",
        "a screenshot of a computer interface",
        "an infographic or chart",
        "a photograph of a person",
        "a photograph of an animal",
        "a photograph of fruit without leaves",
        "a photograph of a household object",
    )
    # A relative cosine similarity margin, not a classifier confidence cutoff.
    CLEAR_MARGIN = 0.02

    def __init__(self, weights_path: str | Path | None = None):
        import torch
        import open_clip

        self._torch = torch
        weights_path = Path(weights_path) if weights_path else self._find_cached_weights()
        if not weights_path or not weights_path.is_file():
            raise FileNotFoundError(
                "Plant-content screening weights are unavailable; analysis is disabled."
            )
        # Use the cached pretrained weights explicitly: startup never downloads or
        # silently substitutes another model. QuickGELU matches the OpenAI checkpoint.
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained=str(weights_path), device="cpu",
            force_quick_gelu=True,
        )
        self._model.eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        prompts = self.PLANT_PROMPTS + self.UNRELATED_PROMPTS
        with torch.inference_mode():
            tokens = tokenizer(prompts)
            text = self._model.encode_text(tokens)
            self._text_features = text / text.norm(dim=-1, keepdim=True)
            if not torch.isfinite(self._text_features).all():
                raise RuntimeError("Plant-content screening produced invalid text features.")
        self._positive_count = len(self.PLANT_PROMPTS)
        self.weights_path = weights_path.resolve()
        logging.getLogger(__name__).info('Plant suitability ViT-B-32 OpenAI weights loaded locally')

    @staticmethod
    def _find_cached_weights() -> Path | None:
        configured = os.getenv("AGRISENSE_PLANT_VERIFIER_WEIGHTS")
        if configured:
            return Path(configured)
        # Hugging Face cache layout used by open_clip's published OpenAI ViT-B/32.
        matches = glob.glob(str(Path.home() / ".cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/snapshots/*/open_clip_model.safetensors"))
        return Path(sorted(matches)[0]) if matches else None

    def verify(self, image: bytes) -> SuitabilityResult:
        try:
            with Image.open(BytesIO(image)) as source:
                rgb = ImageOps.exif_transpose(source).convert("RGB")
                # The second view reduces dependence on the standard center crop.
                w, h = rgb.size
                side = int(min(w, h) * 0.72)
                left, top = (w - side) // 2, (h - side) // 2
                views = (rgb, rgb.crop((left, top, left + side, top + side)))
                batch = self._torch.stack([self._preprocess(view) for view in views])
            with self._torch.inference_mode():
                features = self._model.encode_image(batch)
                features = features / features.norm(dim=-1, keepdim=True)
                similarities = features @ self._text_features.T
                if not self._torch.isfinite(similarities).all():
                    raise ValueError("Plant-content screening produced non-finite similarities.")
                # Both views must independently support the same clear outcome.
                margins = []
                for row in similarities:
                    plant = row[:self._positive_count].max().item()
                    unrelated = row[self._positive_count:].max().item()
                    margins.append((plant, unrelated, plant - unrelated))
        except Exception as error:
            raise RuntimeError("Plant-content screening failed.") from error

        plant, unrelated, margin = margins[0]
        if all(m[2] >= self.CLEAR_MARGIN for m in margins):
            return SuitabilityResult(
                Suitability.PLANT,
                "Plant or leaf content is supported by the suitability check. Disease results can still be wrong.",
                plant, unrelated,
            )
        if all(m[2] <= -self.CLEAR_MARGIN for m in margins):
            return SuitabilityResult(
                Suitability.NON_PLANT,
                "This image appears unrelated to a plant or leaf. Choose a clear tomato-leaf photo before analysis.",
                plant, unrelated,
            )
        return SuitabilityResult(
            Suitability.INCONCLUSIVE,
            "Plant or leaf content could not be verified clearly. Choose a closer, well-lit tomato-leaf photo.",
            plant, unrelated,
        )
