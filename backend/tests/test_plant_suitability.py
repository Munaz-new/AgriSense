"""Regression coverage for non-plant abstention before closed-set inference."""
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.plant_suitability import Suitability, SuitabilityResult, PlantContentVerifier
from app.prediction import Prediction, TrainedTomatoPredictor

FIXTURES = Path(__file__).parent / "fixtures"


class FixedVerifier:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def verify(self, image):
        self.calls += 1
        return SuitabilityResult(self.outcome, "Test suitability result")


class CountingPredictor:
    def __init__(self):
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return Prediction(disease="Septoria Leaf Spot", severity=None,
                          confidence=51.2, predictor="test predictor", is_mock=False)


def test_nonplant_and_inconclusive_images_never_reach_classifier_or_save(tmp_path):
    for outcome, code in ((Suitability.NON_PLANT, "non_plant_image"),
                          (Suitability.INCONCLUSIVE, "plant_content_uncertain")):
        verifier, predictor = FixedVerifier(outcome), CountingPredictor()
        with TestClient(create_app(tmp_path / f"{code}.db", tmp_path / code,
                                   predictor, plant_verifier=verifier)) as client:
            plant_id = client.post("/plants", json={"name": "Tomato", "crop_name": "tomato"}).json()["id"]
            data = (FIXTURES / "unrelated_resume_logo.png").read_bytes()
            assert client.post("/validate-image", files={"image": ("logo.png", data)}).json()["is_valid"]
            response = client.post(
                f"/plants/{plant_id}/observations",
                files={"image": ("logo.png", data, "image/png")},
                data={"request_id": str(uuid4())},
            )
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == code
            assert verifier.calls == 1 and predictor.calls == 0
            assert client.get(f"/plants/{plant_id}/observations").json() == []
            assert list((tmp_path / code).iterdir()) == []


def test_suitable_leaf_continues_to_real_prediction_and_history(tmp_path):
    verifier, predictor = FixedVerifier(Suitability.PLANT), CountingPredictor()
    with TestClient(create_app(tmp_path / "db.sqlite", tmp_path / "uploads", predictor,
                               plant_verifier=verifier)) as client:
        plant_id = client.post("/plants", json={"name": "Tomato", "crop_name": "tomato"}).json()["id"]
        data = (FIXTURES / "tomato_leaf_bacterial_spot.jpg").read_bytes()
        response = client.post(
            f"/plants/{plant_id}/observations",
            files={"image": ("leaf.jpg", data, "image/jpeg")},
            data={"request_id": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["disease"] == "Septoria Leaf Spot"
        assert client.get(f"/plants/{plant_id}/observations").json() == [result]
        assert verifier.calls == predictor.calls == 1


def test_pretrained_verifier_on_real_leaf_and_unrelated_photos():
    """Fixed regression examples; this small sample is not an accuracy estimate."""
    try:
        verifier = PlantContentVerifier()
    except (FileNotFoundError, ImportError) as error:
        pytest.skip(f"Pretrained suitability verifier unavailable: {error}")
    diseased = verifier.verify((FIXTURES / "tomato_leaf_bacterial_spot.jpg").read_bytes())
    healthy = verifier.verify((FIXTURES / "tomato_leaf_healthy.jpg").read_bytes())
    logo = verifier.verify((FIXTURES / "unrelated_resume_logo.png").read_bytes())
    assert diseased.outcome == Suitability.PLANT
    assert healthy.outcome == Suitability.PLANT
    assert logo.outcome == Suitability.NON_PLANT


def test_real_models_reject_logo_and_save_tomato_leaf_prediction(tmp_path):
    """End-to-end smoke against the existing local weights and checkpoint."""
    checkpoint = Path(__file__).resolve().parents[2] / "model/checkpoints/tomato_gpu_epoch5_retry2/best.pt"
    if not checkpoint.is_file():
        pytest.skip("Existing tomato checkpoint is not provisioned locally")
    try:
        verifier = PlantContentVerifier()
    except ImportError as error:
        pytest.skip(f"OpenCLIP runtime unavailable: {error}")
    from unittest.mock import Mock
    from io import BytesIO
    from PIL import Image, ImageDraw
    predictor = TrainedTomatoPredictor(checkpoint)
    predictor.predict = Mock(wraps=predictor.predict)
    assert verifier.weights_path.is_file()
    assert not verifier._model.training
    assert not predictor.classifier.model.training
    with TestClient(create_app(tmp_path / "real.db", tmp_path / "real-uploads",
                               predictor, plant_verifier=verifier)) as client:
        assert client.get('/health').json()['capabilities']['plant_content_screening']
        plant_id = client.post("/plants", json={"name": "Tomato", "crop_name": "tomato"}).json()["id"]
        route = f"/plants/{plant_id}/observations"
        doc = Image.new('RGB', (800, 1000), 'white')
        draw = ImageDraw.Draw(doc)
        for i in range(25):
            draw.text((40, 30+i*30), 'Account statement - invoice 123456', fill='black', font_size=20)
        buffer = BytesIO(); doc.save(buffer, 'PNG')
        for unrelated in [(FIXTURES / "unrelated_resume_logo.png").read_bytes(), buffer.getvalue()]:
            files = {"image": ("unrelated.png", unrelated, "image/png")}
            assert client.post('/validate-image', files=files).json()['is_valid']
            for endpoint in ['/check-plant-suitability', '/predict', route]:
                rejected = client.post(endpoint, files=files, data={"request_id": str(uuid4())})
                assert rejected.status_code == 422, rejected.text
                assert rejected.json()["detail"]["code"] == "non_plant_image"
            assert client.get(route).json() == []
            assert list((tmp_path / 'real-uploads').iterdir()) == []
            predictor.predict.assert_not_called()
        saved_rows = []
        examples = [(name, (FIXTURES / name).read_bytes()) for name in
                    ['tomato_leaf_bacterial_spot.jpg', 'tomato_leaf_healthy.jpg']]
        # Simulate phone-sized JPEG bytes with EXIF rotation, not a physical capture.
        with Image.open(BytesIO(examples[1][1])) as original:
            rotated = original.resize((2048, 2048)).rotate(90, expand=True)
            exif = rotated.getexif(); exif[274] = 6
            encoded = BytesIO(); rotated.save(encoded, 'JPEG', quality=85, exif=exif)
        examples.append(('camera-oriented.jpg', encoded.getvalue()))
        for filename, leaf in examples:
            files = {"image": (filename, leaf, "image/jpeg")}
            assert client.post('/validate-image', files=files).json()['is_valid']
            assert client.post('/check-plant-suitability', files=files).json()['outcome'] == 'plant'
            fields = {"request_id": str(uuid4())}
            response = client.post(route, files=files, data=fields)
            assert response.status_code == 201, response.text
            saved = response.json()
            assert saved["analysis_status"] == "completed" and saved["is_mock"] is False
            assert saved["disease"] and saved["prediction_score"] is not None
            assert saved["checkpoint_id"] == predictor.checkpoint_id
            assert saved['severity'] is None
            assert client.get(saved['image_path']).content == leaf
            saved_rows.append(saved)
            replay = client.post(route, files=files, data=fields)
            assert replay.status_code == 200 and replay.json() == saved
        assert client.get(route).json() == saved_rows
        assert predictor.predict.call_count == len(examples)
        assert len(list((tmp_path/'real-uploads').iterdir())) == len(examples)


@pytest.mark.parametrize('outcome, status', [(Suitability.PLANT, 200), (Suitability.NON_PLANT, 422), (Suitability.INCONCLUSIVE, 422)])
def test_suitability_preview_is_separate_and_analysis_rechecks_bytes(tmp_path, outcome, status):
    verifier, predictor = FixedVerifier(outcome), CountingPredictor()
    with TestClient(create_app(tmp_path/'preview.db', tmp_path/'uploads', predictor, plant_verifier=verifier)) as client:
        leaf = (FIXTURES/'tomato_leaf_healthy.jpg').read_bytes()
        plant = client.post('/plants', json={'name': 'Tomato', 'crop_name': 'tomato'}).json()['id']
        assert client.post('/validate-image', files={'image': ('leaf.jpg', leaf)}).json()['is_valid']
        assert verifier.calls == predictor.calls == 0
        preview = client.post('/check-plant-suitability', files={'image': ('leaf.jpg', leaf)})
        assert preview.status_code == status
        assert verifier.calls == 1 and predictor.calls == 0
        assert client.get(f'/plants/{plant}/observations').json() == []
        assert list((tmp_path/'uploads').iterdir()) == []
        # Even prior acceptance cannot authorize changed bytes or a later rejection.
        verifier.outcome = Suitability.NON_PLANT
        logo = (FIXTURES/'unrelated_resume_logo.png').read_bytes()
        response = client.post(f'/plants/{plant}/observations', data={'request_id': 'changed-image-001'}, files={'image': ('logo.png', logo)})
        assert response.status_code == 422
        assert verifier.calls == 2 and predictor.calls == 0
        assert client.get(f'/plants/{plant}/observations').json() == []


def test_screening_failure_logs_error_and_never_classifies_or_saves(tmp_path, caplog):
    from unittest.mock import Mock
    verifier, predictor = FixedVerifier(Suitability.PLANT), CountingPredictor()
    verifier.verify = Mock(side_effect=RuntimeError('private verifier failure'))
    with TestClient(create_app(tmp_path/'failure.db', tmp_path/'uploads', predictor, plant_verifier=verifier)) as client:
        plant = client.post('/plants', json={'name': 'Tomato', 'crop_name': 'tomato'}).json()['id']
        leaf = (FIXTURES/'tomato_leaf_healthy.jpg').read_bytes()
        for route in ['/check-plant-suitability', '/predict', f'/plants/{plant}/observations']:
            response = client.post(route, data={'request_id': 'screen-failure-001'}, files={'image': ('leaf.jpg', leaf)})
            assert response.status_code == 503
            assert response.json()['detail']['code'] == 'plant_screening_unavailable'
            assert 'private verifier failure' not in response.text
        assert predictor.calls == 0
        assert client.get(f'/plants/{plant}/observations').json() == []
        assert list((tmp_path/'uploads').iterdir()) == []
    assert 'Plant-content screening failed: RuntimeError' in caplog.text
    assert 'private verifier failure' not in caplog.text


def test_injected_real_predictor_cannot_bypass_missing_screening(tmp_path, monkeypatch):
    from app import main
    from unittest.mock import Mock
    predictor = object.__new__(TrainedTomatoPredictor)
    predictor.predict = Mock()
    monkeypatch.setattr(main, 'PlantContentVerifier', Mock(side_effect=FileNotFoundError('missing test weights')))
    with TestClient(create_app(tmp_path/'missing.db', tmp_path/'uploads', predictor)) as client:
        assert not client.get('/health').json()['capabilities']['tomato_analysis']
        leaf = (FIXTURES/'tomato_leaf_healthy.jpg').read_bytes()
        for route in ['/predict', '/check-plant-suitability']:
            assert client.post(route, files={'image': ('leaf.jpg', leaf)}).status_code == 503
        predictor.predict.assert_not_called()


def test_invalid_file_never_reaches_suitability_preview(tmp_path):
    verifier, predictor = FixedVerifier(Suitability.PLANT), CountingPredictor()
    with TestClient(create_app(tmp_path/'invalid.db', tmp_path/'uploads', predictor, plant_verifier=verifier)) as client:
        assert client.post('/check-plant-suitability', files={'image': ('broken.png', b'broken')}).status_code == 415
    assert verifier.calls == predictor.calls == 0


def test_explicit_missing_weights_do_not_fall_back_to_cache(tmp_path, monkeypatch):
    pytest.importorskip('open_clip')
    missing = tmp_path/'missing.safetensors'
    monkeypatch.setenv('AGRISENSE_PLANT_VERIFIER_WEIGHTS', str(missing))
    assert PlantContentVerifier._find_cached_weights() == missing
    with pytest.raises(FileNotFoundError, match='weights are unavailable'):
        PlantContentVerifier()


def test_corrupt_weights_are_not_silently_replaced(tmp_path):
    pytest.importorskip('open_clip')
    from safetensors import SafetensorError
    corrupt = tmp_path/'corrupt.safetensors'
    corrupt.write_bytes(b'not a model')
    with pytest.raises(SafetensorError):
        PlantContentVerifier(corrupt)


def test_nonfinite_screening_output_fails_instead_of_looking_inconclusive():
    torch = pytest.importorskip('torch')
    from unittest.mock import Mock
    verifier = object.__new__(PlantContentVerifier)
    verifier._torch = torch
    verifier._preprocess = lambda image: torch.zeros(3, 224, 224)
    verifier._model = Mock()
    verifier._model.encode_image.return_value = torch.full((2, 3), float('nan'))
    verifier._text_features = torch.ones(12, 3)
    verifier._positive_count = 4
    with pytest.raises(RuntimeError, match='screening failed'):
        verifier.verify((FIXTURES/'tomato_leaf_healthy.jpg').read_bytes())
