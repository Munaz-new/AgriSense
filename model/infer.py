"""Local checkpoint inference. Refuses to run without completed-training metadata."""
import argparse
import json
from pathlib import Path
from .agrisense_model.config import DEFAULT_CONFIG, load_config
from .agrisense_model.inference import CropClassifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    # Apply exactly the same technical validation as the backend before inference.
    from backend.app.image_validation import TechnicalPlantImageValidator
    data = Path(args.image).read_bytes()
    validation = TechnicalPlantImageValidator().validate(data)
    if not validation.is_valid:
        raise SystemExit(validation.message)
    classifier = CropClassifier(config.path('checkpoint_path'), expected_config=config)
    print(json.dumps(classifier.predict(data), indent=2))
    print(f'{config.crop_name} configuration only. Softmax confidence is uncalibrated. Severity is not estimated.')


if __name__ == '__main__':
    main()
