from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.main import MAX_IMAGE_BYTES, create_app
from app.prediction import Prediction


@pytest.fixture
def image():
    output = BytesIO()
    Image.new('RGB', (256, 256), 'green').save(output, format='PNG')
    return output.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db', tmp_path / 'uploads')) as client:
        yield client


def plant(client, name='Tomato'):
    response = client.post('/plants', json={'name': name})
    assert response.status_code == 201
    return response.json()['id']


def scan(client, plant_id, image, **context):
    return client.post(f'/plants/{plant_id}/observations',
                       files={'image': ('leaf.png', image, 'image/png')},
                       data={'temperature': '27', 'humidity': '65', 'soil_type': 'Loamy',
                             'soil_condition': 'Normal', **context})


def test_complete_flow_and_isolation(client, image):
    assert client.get('/health').json()['status'] == 'ok'
    first, second = plant(client), plant(client, 'Potato')
    assert len(client.get('/plants').json()) == 2
    assert client.get(f'/plants/{first}').json()['name'] == 'Tomato'
    assert client.get(f'/plants/{first}/observations').json() == []
    response = scan(client, first, image)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['plant_id'] == first
    assert result['is_mock'] is True
    assert result['temperature'] == 27
    assert result['humidity'] == 65
    assert result['soil_type'] == 'Loamy'
    assert result['soil_condition'] == 'Normal'
    assert 0 <= result['severity'] <= 100
    assert 0 <= result['confidence'] <= 100
    assert client.get(result['image_path']).content == image
    assert client.get(f'/plants/{first}/observations').json() == [result]
    assert client.get(f'/plants/{second}/observations').json() == []
    again = scan(client, first, image).json()
    assert [row['id'] for row in client.get(f'/plants/{first}/observations').json()] == [result['id'], again['id']]


def test_prediction_only_does_not_save(client, image):
    plant_id = plant(client)
    response = client.post('/predict', files={'image': ('leaf.png', image)})
    assert response.status_code == 200
    assert response.json()['is_mock'] is True
    assert client.get(f'/plants/{plant_id}/observations').json() == []


@pytest.mark.parametrize('context', [
    {'temperature': '71'}, {'temperature': '-51'}, {'temperature': 'nan'},
    {'humidity': '101'}, {'humidity': '-1'}, {'humidity': 'inf'},
    {'soil_type': '   '}, {'soil_condition': 'Unknown'},
])
def test_invalid_context(client, image, context):
    plant_id = plant(client)
    assert scan(client, plant_id, image, **context).status_code == 422
    assert client.get(f'/plants/{plant_id}/observations').json() == []


def test_invalid_plants_and_missing_data(client, image):
    assert client.post('/plants', json={'name': '   '}).status_code == 422
    assert client.get('/plants/missing').status_code == 404
    assert client.get('/plants/missing/observations').status_code == 404
    assert scan(client, 'missing', image).status_code == 404
    plant_id = plant(client)
    assert client.post(f'/plants/{plant_id}/observations').status_code == 422


def test_invalid_and_oversized_images(client):
    assert client.post('/predict', files={'image': ('fake.jpg', b'not an image', 'image/jpeg')}).status_code == 415
    assert client.post('/predict', files={'image': ('large.jpg', b'x' * (MAX_IMAGE_BYTES + 1))}).status_code == 413


def test_persistence_and_image_only_boundary(tmp_path, image):
    class SpyPredictor:
        def __init__(self): self.inputs = []
        def predict(self, data: bytes):
            self.inputs.append(data)
            return Prediction(disease='Early Blight', severity=18, confidence=91, predictor='test-mock', is_mock=True)

    predictor = SpyPredictor()
    path, uploads = tmp_path / 'persist.db', tmp_path / 'uploads'
    with TestClient(create_app(path, uploads, predictor)) as client:
        plant_id = plant(client)
        a = scan(client, plant_id, image).json()
        b = scan(client, plant_id, image, temperature='10', humidity='20', soil_type='Clay', soil_condition='Wet').json()
        assert a['severity'] == b['severity'] == 18
        assert predictor.inputs == [image, image]
    with TestClient(create_app(path, uploads)) as client:
        assert client.get(f'/plants/{plant_id}').json()['name'] == 'Tomato'
        assert len(client.get(f'/plants/{plant_id}/observations').json()) == 2
        assert client.get(a['image_path']).content == image
