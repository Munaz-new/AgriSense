"""Serving contracts with explicit test doubles; never run the real checkpoint here."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app import main
from app.database import connect
from app.prediction import Prediction, PredictionUnavailableError
from app.plant_suitability import Suitability, SuitabilityResult


class ServingStub:
    checkpoint_id = 'sha256:test-artifact'

    def __init__(self, path):
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return Prediction(disease='Early_blight', confidence=72.5, severity=None,
                          predictor='test-architecture', is_mock=False)


class SuitableImageStub:
    def verify(self, image):
        return SuitabilityResult(Suitability.PLANT, 'test-only suitable image')


@pytest.fixture
def serving(tmp_path, monkeypatch):
    instances = []
    class Counted(ServingStub):
        def __init__(self, path):
            super().__init__(path)
            instances.append(self)
    monkeypatch.setattr(main, 'TrainedTomatoPredictor', Counted)
    db, uploads = tmp_path / 'journal.db', tmp_path / 'uploads'
    image = BytesIO()
    Image.new('RGB', (224, 224), 'gray').save(image, 'PNG')
    with TestClient(main.create_app(db, uploads, plant_verifier=SuitableImageStub())) as client:
        plant = client.post('/plants', json={'name': 'Tomato', 'crop_name': 'tomato'}).json()['id']
        yield client, plant, image.getvalue(), instances, db, uploads


def submit(s, key='analysis-001', route='observations', **changes):
    client, plant, image, *_ = s
    fields = dict(request_id=key, temperature=25, humidity=65, soil_type='Loamy',
                  soil_condition='Normal', observed_at='2025-01-01T10:00:00Z',
                  tracking_ref='leaf-1', notes='test journal context')
    fields.update(changes)
    return client.post(f'/plants/{plant}/{route}', data=fields, files={'image': ('leaf.png', image)})


def test_startup_once_real_result_and_sqlite_replay(serving):
    client, plant, _, instances, db, uploads = serving
    assert len(instances) == 1
    health = client.get('/health').json()
    assert health['capabilities']['tomato_analysis'] is True
    assert health['capabilities']['plant_content_screening'] is True
    assert health['capabilities']['severity_measurement'] is False
    first = submit(serving)
    assert first.status_code == 201, first.text
    row = first.json()
    assert row['disease'] == 'Early_blight'
    assert row['prediction_score'] == row['confidence'] == 72.5
    assert row['is_mock'] is False and row['analysis_status'] == 'completed'
    assert row['checkpoint_id'] == 'sha256:test-artifact'
    assert row['severity'] is None and row['severity_source'] is None
    assert row['notes'] == 'test journal context' and row['tracking_ref'] == 'leaf-1'
    repeat = submit(serving)
    assert repeat.status_code == 200 and repeat.json() == row
    assert len(instances) == instances[0].calls == 1
    assert submit(serving, temperature=26).status_code == 409
    assert submit(serving, route='records').status_code == 409
    assert client.get(f'/plants/{plant}/observations').json() == [row]
    with connect(db) as connection:
        stored = connection.execute('SELECT * FROM observations').fetchone()
        assert stored['confidence'] == 72.5 and stored['severity'] is None
        assert stored['is_mock'] == 0 and stored['analysis_status'] == 'completed'
    assert len(list(uploads.iterdir())) == 1
    second = submit(serving, key='analysis-002').json()
    assert second['duplicate_of'] == row['id']
    assert client.get(f'/plants/{plant}/progression?tracking_ref=leaf-1').json()['reason'] == 'severity_unavailable'


def test_concurrent_analysis_retries_infer_once(serving):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: submit(serving), range(3)))
    assert sorted(r.status_code for r in results) == [200, 200, 201]
    assert len({r.json()['id'] for r in results}) == 1
    assert serving[3][0].calls == 1


def test_scope_and_validation_precede_inference(serving):
    client, _, _, instances, *_ = serving
    other = client.post('/plants', json={'name': 'Other', 'crop_name': 'potato'}).json()['id']
    changed = list(serving); changed[1] = other
    rejected = submit(changed)
    assert rejected.status_code == 422
    assert rejected.json()['detail']['code'] == 'unsupported_crop'
    assert submit(changed, route='records').status_code == 201
    changed = list(serving); changed[2] = b'broken image'
    assert submit(changed).status_code == 415
    assert instances[0].calls == 0


def test_failed_inference_no_row_no_file_and_record_only_still_works(serving):
    client, plant, _, instances, _, uploads = serving
    instances[0].predict = Mock(side_effect=PredictionUnavailableError('private'))
    response = submit(serving)
    assert response.status_code == 503 and 'private' not in response.text
    assert client.get(f'/plants/{plant}/observations').json() == []
    assert list(uploads.iterdir()) == []
    assert submit(serving, key='record-only-001', route='records').status_code == 201


def test_inference_failure_is_distinct_and_retry_persists_once(serving, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    client, plant, _, instances, _, uploads = serving
    original = instances[0].predict
    instances[0].predict = Mock(side_effect=PredictionUnavailableError('private inference details'))
    failed = submit(serving, key='camera-retry-001', notes='private observation notes')
    assert failed.status_code == 503
    assert failed.json()['detail']['code'] == 'inference_failed'
    assert client.get(f'/plants/{plant}/observations').json() == []
    assert list(uploads.iterdir()) == []
    instances[0].predict = original
    saved = submit(serving, key='camera-retry-001', notes='private observation notes')
    assert saved.status_code == 201
    assert submit(serving, key='camera-retry-001', notes='private observation notes').json() == saved.json()
    assert client.get(f'/plants/{plant}/observations').json() == [saved.json()]
    assert len(list(uploads.iterdir())) == 1
    assert saved.headers['x-agrisense-request-id'] != failed.headers['x-agrisense-request-id']
    for name in ['upload_received', 'image_validation', 'plant_screening', 'tomato_inference', 'observation_saved']:
        assert f'stage={name}' in caplog.text
    for private in ['private inference details', 'private observation notes', plant, 'leaf.png']:
        assert private not in caplog.text


def test_startup_failure_is_not_retried_per_request(tmp_path, monkeypatch):
    class Broken:
        calls = 0
        def __init__(self, path):
            Broken.calls += 1
            raise RuntimeError('private load failure')
    monkeypatch.setattr(main, 'TrainedTomatoPredictor', Broken)
    with TestClient(main.create_app(tmp_path/'test.db', tmp_path/'uploads')) as client:
        assert client.get('/health').json()['capabilities']['tomato_analysis'] is False
        data = BytesIO(); Image.new('RGB', (224,224)).save(data,'PNG')
        for _ in range(2):
            r = client.post('/predict',files={'image':('leaf.png',data.getvalue())})
            assert r.status_code == 503 and 'private' not in r.text
        plant = client.post('/plants',json={'name':'Tomato','crop_name':'tomato'}).json()['id']
        assert submit((client,plant,data.getvalue()),route='records').status_code == 201
    assert Broken.calls == 1


@pytest.mark.parametrize('route', ['records', 'observations'])
def test_captured_time_timezone_optional_context_and_authoritative_save_time(serving, route):
    response = submit(serving, route=route, observed_at='2025-01-01T15:30:00+05:30',
                      observed_timezone='Asia/Kolkata (UTC+05:30)', tracking_ref='', notes='')
    assert response.status_code == 201
    row = response.json()
    assert row['observed_at'] == '2025-01-01T10:00:00+00:00'
    assert row['observed_timezone'] == 'Asia/Kolkata (UTC+05:30)'
    assert row['created_at'] != row['observed_at']
    assert row['tracking_ref'] is None and row['notes'] is None
    assert row['id']
    assert serving[0].get(f'/plants/{serving[1]}/observations').json() == [row]


def test_analysis_without_environment_and_explicit_crop_persistence(serving):
    client, plant, image, instances, *_ = serving
    assert client.get(f'/plants/{plant}').json()['crop_name'] == 'tomato'
    unknown = client.post('/plants', json={'name': 'tomato'}).json()
    assert unknown['crop_name'] is None
    response = client.post(f'/plants/{plant}/observations',
                           data={'request_id': 'no-environment-001'}, files={'image': ('leaf.png', image)})
    assert response.status_code == 201, response.text
    row = response.json()
    for key in ['temperature', 'humidity', 'soil_type', 'soil_condition']:
        assert row[key] is None
    assert row['analysis_status'] == 'completed'
    assert client.get(f'/plants/{plant}/observations').json() == [row]
    assert client.get(f"/plants/{unknown['id']}").json() == unknown
    assert client.post(f'/plants/{plant}/records', data={'request_id': 'no-environment-002'}, files={'image': ('leaf.png', image)}).status_code == 422


@pytest.mark.parametrize('changes', [{'temperature': 'nan'}, {'humidity': 101}, {'soil_condition': 'unknown'}, {'soil_type': '   '}])
def test_optional_environment_still_validates_supplied_values(serving, changes):
    client, plant, image, instances, *_ = serving
    response = client.post(f'/plants/{plant}/observations',
                           data={'request_id': 'invalid-optional-001', **changes}, files={'image': ('leaf.png', image)})
    assert response.status_code == 422
    assert instances[0].calls == 0
