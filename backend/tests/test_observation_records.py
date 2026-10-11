"""Record-only contracts; temporary image fixtures, no model or measurements."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.database import connect
from app.main import create_app
from app.records import save_record


@pytest.fixture
def journal(tmp_path):
    predictor = Mock()
    predictor.predict.side_effect = AssertionError('Record-only path must never predict')
    path, uploads = tmp_path / 'journal.db', tmp_path / 'uploads'
    with TestClient(create_app(path, uploads, predictor)) as client:
        plant = client.post('/plants', json={'name': 'Plant A', 'crop_name': 'tomato'}).json()
        output = BytesIO()
        Image.new('RGB', (224, 224), 'white').save(output, format='PNG')
        yield client, plant['id'], output.getvalue(), path, uploads, predictor
    predictor.predict.assert_not_called()


def submit(journal, key='request-001', **overrides):
    client, plant_id, image, *_ = journal
    fields = dict(request_id=key, temperature='25', humidity='60', soil_type='Loamy',
                  soil_condition='Normal', tracking_ref='leaf-a')
    fields.update(overrides)
    return client.post(f'/plants/{plant_id}/records', data=fields, files={'image': ('fixture.png', image)})


def submit_optional_context(journal, key, fields):
    client, plant_id, image, *_ = journal
    payload = {'request_id': key, 'soil_condition': 'Normal', **fields}
    return client.post(f'/plants/{plant_id}/records', data=payload, files={'image': ('fixture.png', image)})


def test_record_only_roundtrip_capabilities_and_nulls(journal):
    client, plant_id, _, path, uploads, _ = journal
    capabilities = client.get('/health').json()['capabilities']
    assert capabilities == dict(record_only=True, technical_image_validation=True,
                                plant_content_screening=False, tomato_analysis=False,
                                severity_measurement=False, health_progression=False)
    assert client.get(f'/plants/{plant_id}').json()['crop_name'] == 'tomato'
    response = submit(journal, notes='  User-entered note  ')
    assert response.status_code == 201
    row = response.json()
    assert all(row[key] is None for key in ('disease', 'severity', 'confidence', 'predictor', 'observed_at', 'checkpoint_id', 'severity_source'))
    assert row['analysis_status'] == 'not_requested' and row['is_mock'] is False
    assert row['notes'] == 'User-entered note'
    assert 'request_fingerprint' not in row
    assert client.get(f'/plants/{plant_id}/observations').json() == [row]
    assert client.get(row['image_path']).status_code == 200
    assert len(list(uploads.iterdir())) == 1
    with connect(path) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('fields, expected', [
    ({}, {'temperature': None, 'humidity': None, 'soil_type': None}),
    ({'temperature': '21.5'}, {'temperature': 21.5, 'humidity': None, 'soil_type': None}),
    ({'humidity': '0'}, {'temperature': None, 'humidity': 0.0, 'soil_type': None}),
    ({'soil_type': '  Sandy loam  '}, {'temperature': None, 'humidity': None, 'soil_type': 'Sandy loam'}),
])
def test_record_only_context_fields_are_independently_optional(journal, fields, expected):
    response = submit_optional_context(journal, 'optional-context', fields)
    assert response.status_code == 201
    row = response.json()
    assert {key: row[key] for key in expected} == expected
    assert journal[0].get(f'/plants/{journal[1]}/observations').json() == [row]


@pytest.mark.parametrize('fields', [
    {'temperature': '-50.1'}, {'temperature': '70.1'}, {'temperature': 'nan'},
    {'temperature': 'inf'}, {'humidity': '-0.1'}, {'humidity': '100.1'},
    {'humidity': 'nan'}, {'soil_type': '   '}, {'soil_type': 'x' * 101},
])
def test_invalid_optional_context_never_persists(journal, fields):
    assert submit_optional_context(journal, 'invalid-context', fields).status_code == 422
    assert journal[0].get(f'/plants/{journal[1]}/observations').json() == []
    assert list(journal[4].iterdir()) == []


def test_optional_context_nulls_survive_restart(journal):
    first = submit(journal).json()
    with TestClient(create_app(journal[3], journal[4], journal[5])) as restarted:
        assert restarted.get(f'/plants/{journal[1]}/observations').json() == [first]


def test_replay_and_changed_payload_conflict(journal):
    first = submit(journal)
    repeat = submit(journal)
    assert repeat.status_code == 200 and repeat.json() == first.json()
    assert submit(journal, temperature='26').status_code == 409
    assert len(journal[0].get(f'/plants/{journal[1]}/observations').json()) == 1
    assert len(list(journal[4].iterdir())) == 1


def test_changed_image_same_key_conflicts(journal):
    submit(journal)
    changed = list(journal)
    output = BytesIO()
    Image.new('RGB', (224, 224), 'black').save(output, format='PNG')
    changed[2] = output.getvalue()
    assert submit(changed).status_code == 409


def test_repeated_image_flag_and_plant_isolation(journal):
    client, plant_id, image, path, uploads, predictor = journal
    first = submit(journal).json()
    repeated = submit(journal, 'request-002').json()
    assert repeated['id'] != first['id'] and repeated['duplicate_of'] == first['id']
    second_plant = client.post('/plants', json={'name': 'Plant B'}).json()['id']
    other = submit((client, second_plant, image, path, uploads, predictor)).json()
    assert other['duplicate_of'] is None
    assert client.get(f'/plants/{second_plant}/observations').json() == [other]
    assert len(client.get(f'/plants/{plant_id}/observations').json()) == 2


def test_observation_chronology_timezone_and_unknown_time(journal):
    late = submit(journal, 'request-late', observed_at='2025-04-02T10:00:00+05:30').json()
    early = submit(journal, 'request-early', observed_at='2025-04-01T10:00:00Z').json()
    unknown = submit(journal, 'request-unknown').json()
    assert late['observed_at'] == '2025-04-02T04:30:00+00:00'
    assert unknown['observed_at'] is None
    rows = journal[0].get(f'/plants/{journal[1]}/observations').json()
    assert [row['id'] for row in rows] == [early['id'], late['id'], unknown['id']]


@pytest.mark.parametrize('fields', [
    {'observed_at': '2025-01-01T00:00:00'}, {'observed_at': '2999-01-01T00:00:00Z'},
    {'observed_at': '2025-02-30T00:00:00Z'}, {'temperature': 'nan'}, {'humidity': '101'},
    {'soil_type': '   '}, {'request_id': 'bad'}, {'tracking_ref': 'x' * 101}, {'notes': 'x' * 2001},
])
def test_invalid_records_never_persist(journal, fields):
    assert submit(journal, **fields).status_code == 422
    assert journal[0].get(f'/plants/{journal[1]}/observations').json() == []
    assert list(journal[4].iterdir()) == []


def test_invalid_image_unknown_plant_and_unavailable_progression(journal):
    client, plant_id, *_ = journal
    bad = list(journal)
    bad[2] = b'invalid'
    assert submit(bad).status_code == 415
    bad[1] = 'missing'
    assert submit(bad).status_code == 404
    assert client.get('/plants/missing/progression').status_code == 404
    assert client.get(f'/plants/{plant_id}/progression').json()['status'] == 'insufficient_data'
    submit(journal)
    submit(journal, 'request-002')
    result = client.get(f'/plants/{plant_id}/progression?tracking_ref=leaf-a').json()
    assert result['status'] == 'unavailable' and result['reason'] == 'severity_unavailable'
    assert result['delta'] is None and result['policy_version'] is None
    assert client.get(f'/plants/{plant_id}/progression?tracking_ref=other').json()['status'] == 'insufficient_data'


def test_record_survives_restart(journal):
    first = submit(journal).json()
    with TestClient(create_app(journal[3], journal[4], journal[5])) as restarted:
        assert restarted.get(f'/plants/{journal[1]}/observations').json() == [first]


def test_concurrent_retries_create_one_row_and_image(journal):
    _, plant_id, image, path, uploads, _ = journal
    fields = dict(request_id='concurrent-001', temperature=25.0, humidity=60.0, soil_type='Loamy',
                  soil_condition='Normal', observed_at=None, tracking_ref=None, notes=None)
    def save(_):
        return save_record(path, uploads, plant_id, image, 'png', fields, '2025-01-01T00:00:00+00:00')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(save, range(4)))
    assert len({row['id'] for row, _ in results}) == 1
    assert sum(not replay for _, replay in results) == 1
    assert len(list(uploads.iterdir())) == 1


@pytest.mark.parametrize('after_insert', [False, True])
def test_failed_insert_rolls_back_image_and_allows_retry(journal, monkeypatch, after_insert):
    from app import records
    original = records.insert_observation
    def fail(db, row):
        if after_insert:
            original(db, row)
        raise RuntimeError('test-only storage failure')
    monkeypatch.setattr(records, 'insert_observation', fail)
    with pytest.raises(RuntimeError, match='test-only'):
        submit(journal)
    assert list(journal[4].iterdir()) == []
    assert journal[0].get(f'/plants/{journal[1]}/observations').json() == []
    monkeypatch.setattr(records, 'insert_observation', original)
    assert submit(journal).status_code == 201


def test_filename_collision_preserves_existing_image(journal, monkeypatch):
    from app import records
    monkeypatch.setattr(records, 'uuid4', lambda: 'existing')
    existing = journal[4] / 'existing.png'
    existing.write_bytes(b'existing test evidence')
    with pytest.raises(FileExistsError):
        submit(journal)
    assert existing.read_bytes() == b'existing test evidence'
    assert journal[0].get(f'/plants/{journal[1]}/observations').json() == []
