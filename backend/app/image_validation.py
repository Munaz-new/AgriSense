"""Technical file checks. Semantic plant-content suitability is a separate step."""
from io import BytesIO
from typing import Protocol
import warnings

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_SIDE = 224
MAX_SIDE = 8192
MAX_PIXELS = 24_000_000
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class ValidationResult(BaseModel):
    is_valid: bool
    reason: str
    message: str


class PlantImageValidator(Protocol):
    def validate(self, image: bytes) -> ValidationResult: ...


def rejected(reason: str, message: str) -> ValidationResult:
    return ValidationResult(is_valid=False, reason=reason, message=message)


class TechnicalPlantImageValidator:
    """Check that bytes decode as a supported, bounded still image only."""
    def validate(self, image: bytes) -> ValidationResult:
        if not image:
            return rejected("empty_upload", "The image is empty. Please select a clear plant or leaf photo.")
        if len(image) > MAX_IMAGE_BYTES:
            return rejected("image_too_large", "Image must be 10 MB or smaller. Please choose a smaller photo.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(image)) as decoded:
                    if decoded.format not in EXTENSIONS:
                        return rejected("unsupported_format", "Unsupported image format. Please use JPEG, PNG, or WebP.")
                    width, height = decoded.size
                    if min(width, height) < MIN_SIDE:
                        return rejected("resolution_too_small", "Image is too small. Use a photo at least 224 pixels wide and high.")
                    if max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                        return rejected("resolution_too_large", "Image resolution is too large. Use at most 8192 pixels per side and 24 megapixels.")
                    if getattr(decoded, "n_frames", 1) != 1:
                        return rejected("animated_image", "Please upload a single still photo, not an animated image.")
                    decoded.verify()
                # verify() alone does not decode pixel data (notably for JPEG).
                with Image.open(BytesIO(image)) as decoded:
                    decoded.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            return rejected("resolution_too_large", "Image resolution is too large. Please choose a smaller photo.")
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError):
            return rejected("invalid_image", "This file cannot be read as a valid image. Please upload an undamaged JPEG, PNG, or WebP plant or leaf photo.")
        return ValidationResult(
            is_valid=True, reason="technical_checks_passed",
            message="Technical image checks passed. This does not confirm that the image contains a plant or leaf.",
        )


def image_extension(image: bytes) -> str:
    """Call only after successful validation; use decoded format, not filename."""
    with Image.open(BytesIO(image)) as decoded:
        return EXTENSIONS[decoded.format]
