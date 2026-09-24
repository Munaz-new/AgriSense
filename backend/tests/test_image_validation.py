from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.image_validation import MAX_IMAGE_BYTES, TechnicalPlantImageValidator, ValidationResult
from app.main import create_app
from app.prediction import MockPredictor


def picture(format='PNG', size=(256, 256)):
    output = BytesIO()
    # A gray test image intentionally passes: this is not semantic recognition.
    Image.new('RGB', size, 'gray').save(output, format=format)
    return output.getvalue()


class RecordingPredictor(MockPredictor):
    def __init__(self, events):
        self.events = events

    def predict(self, image):
        self.events.append('predict')
        return super().predict(image)


class RecordingValidator(TechnicalPlantImageValidator):
    def __init__(self, events):
        self.events = events

    def validate(self, image):
        self.events.append('validate')
        return super().validate(image)


@pytest.fixture
def setup(tmp_path):
    events = []
    uploads = tmp_path / 'uploads'
    app = create_app(tmp_path / 'test.db', uploads,
                     RecordingPredictor(events), RecordingValidator(events))
    with TestClient(app) as client:
        plant_id = client.post('/plants', json={'name': 'Tomato'}).json()['id']
        yield client, plant_id, uploads, events


def upload(client, path, data):
    # Filename and MIME must not override actual byte validation.
    return client.post(path, files={'image': ('leaf.jpg', data, 'image/jpeg')},
                       data={'temperature': 27, 'humidity': 65, 'soil_type': 'Loamy', 'soil_condition': 'Normal'})


@pytest.mark.parametrize('data,reason,status', [
    (b'', 'empty_upload', 422),
    (b'not an image', 'invalid_image', 415),
    (picture('GIF'), 'unsupported_format', 415),
    (picture()[:80], 'invalid_image', 415),
    (picture('JPEG')[:-40], 'invalid_image', 415),
    (b'x' * (MAX_IMAGE_BYTES + 1), 'image_too_large', 413),
    (picture(size=(223, 256)), 'resolution_too_small', 422),
    (picture(size=(256, 223)), 'resolution_too_small', 422),
    (picture(size=(8193, 224)), 'resolution_too_large', 422),
    (picture(size=(5000, 5000)), 'resolution_too_large', 422),
])
def test_rejected_on_every_route_without_side_effects(setup, data, reason, status):
    client, plant_id, uploads, events = setup
    for path in ['/validate-image', '/predict', f'/plants/{plant_id}/observations']:
        response = upload(client, path, data)
        assert response.status_code == status, response.text
        detail = response.json()['detail']
        assert detail['is_valid'] is False
        assert detail['reason'] == reason
        assert detail['message']
        assert client.get(f'/plants/{plant_id}/observations').json() == []
        assert list(uploads.iterdir()) == []
    assert events == ['validate'] * 3


@pytest.mark.parametrize('format', ['PNG', 'JPEG', 'WEBP'])
def test_valid_flow_validates_before_prediction_and_save(setup, format):
    client, plant_id, uploads, events = setup
    data = picture(format, size=(224, 224))
    response = upload(client, '/validate-image', data)
    assert response.status_code == 200
    assert response.json()['is_valid'] is True
    assert response.json()['reason'] == 'technical_checks_passed'
    assert 'not been verified' in response.json()['message']
    assert events == ['validate']
    assert list(uploads.iterdir()) == []
    preview = upload(client, '/predict', data)
    assert preview.status_code == 200
    assert events == ['validate', 'validate', 'predict']
    assert client.get(f'/plants/{plant_id}/observations').json() == []
    assert list(uploads.iterdir()) == []
    saved = upload(client, f'/plants/{plant_id}/observations', data)
    assert saved.status_code == 201
    assert saved.json()['severity'] == preview.json()['severity']
    assert events == ['validate', 'validate', 'predict', 'validate', 'predict']
    assert len(client.get(f'/plants/{plant_id}/observations').json()) == 1
    assert len(list(uploads.iterdir())) == 1


def test_previous_validation_cannot_approve_different_bytes(setup):
    client, plant_id, uploads, events = setup
    assert upload(client, '/validate-image', picture()).status_code == 200
    assert upload(client, '/predict', b'bad replacement').status_code == 415
    assert upload(client, f'/plants/{plant_id}/observations', b'bad replacement').status_code == 415
    assert 'predict' not in events
    assert list(uploads.iterdir()) == []


def test_future_semantic_validator_rejection_is_respected(tmp_path):
    # Test double verifies the extension point; it is NOT a real classifier.
    class RejectingValidator:
        def validate(self, image):
            return ValidationResult(is_valid=False, reason='unsuitable_image',
                                    message='This image is not suitable for plant analysis. Please upload a clear plant or leaf image.')
    events = []
    uploads = tmp_path / 'uploads'
    with TestClient(create_app(tmp_path / 'test.db', uploads, RecordingPredictor(events), RejectingValidator())) as client:
        plant_id = client.post('/plants', json={'name': 'Tomato'}).json()['id']
        for path in ['/validate-image', '/predict', f'/plants/{plant_id}/observations']:
            response = upload(client, path, picture())
            assert response.status_code == 422
            assert response.json()['detail']['reason'] == 'unsuitable_image'
        assert client.get(f'/plants/{plant_id}/observations').json() == []
        assert not events
        assert list(uploads.iterdir()) == []


def test_animated_image_is_rejected():
    output = BytesIO()
    first = Image.new('RGB', (256, 256), 'white')
    second = Image.new('RGB', (256, 256), 'black')
    first.save(output, format='PNG', save_all=True, append_images=[second], duration=100)
    result = TechnicalPlantImageValidator().validate(output.getvalue())
    assert not result.is_valid
    assert result.reason == 'animated_image'
