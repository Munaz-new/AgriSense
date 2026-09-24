"""Model integration readiness without importing torch or enabling a real model."""
from io import BytesIO
import sqlite3
from PIL import Image
from fastapi.testclient import TestClient
import pytest

from app.database import connect, initialize
from app.main import create_app
from app.prediction import Prediction, TrainedTomatoPredictor


def test_default_is_mock_and_missing_model_is_refused(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db', tmp_path / 'uploads')) as client:
        assert client.get('/health').json()['is_mock'] is True
        image = BytesIO()
        Image.new('RGB', (256, 256), 'white').save(image, format='PNG')
        result = client.post('/predict', files={'image': ('leaf.png', image.getvalue())})
        assert result.json()['is_mock'] is True
        assert result.json()['predictor'] == 'development-mock-v1'
    with pytest.raises(FileNotFoundError, match='keep using the development mock'):
        TrainedTomatoPredictor(tmp_path / 'missing.pt')


def test_nullable_severity_is_saved_and_returned(tmp_path):
    class NoSeverityTestStub:
        def predict(self, image):
            return Prediction(disease='test-only', severity=None, confidence=0,
                              predictor='test-stub', is_mock=True)
    path, uploads = tmp_path / 'test.db', tmp_path / 'uploads'
    with TestClient(create_app(path, uploads, NoSeverityTestStub())) as client:
        plant_id = client.post('/plants', json={'name': 'Tomato'}).json()['id']
        image = BytesIO()
        Image.new('RGB', (256, 256), 'white').save(image, format='PNG')
        response = client.post(f'/plants/{plant_id}/observations',
                               files={'image': ('leaf.png', image.getvalue())},
                               data={'temperature': 25, 'humidity': 65, 'soil_type': 'Loamy', 'soil_condition': 'Normal'})
        assert response.status_code == 201, response.text
        assert response.json()['severity'] is None
        assert client.get(f'/plants/{plant_id}/observations').json()[0]['severity'] is None
    with connect(path) as db:
        assert db.execute('SELECT severity FROM observations').fetchone()[0] is None


def test_old_database_migration_preserves_rows_and_foreign_keys(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE plants (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE observations (
                id TEXT PRIMARY KEY, plant_id TEXT NOT NULL REFERENCES plants(id),
                image_path TEXT NOT NULL, created_at TEXT NOT NULL,
                disease TEXT NOT NULL, severity REAL NOT NULL, confidence REAL NOT NULL,
                predictor TEXT NOT NULL, is_mock INTEGER NOT NULL, temperature REAL NOT NULL,
                humidity REAL NOT NULL, soil_type TEXT NOT NULL, soil_condition TEXT NOT NULL);
            INSERT INTO plants VALUES ('p', 'Tomato', '2026-01-01');
            INSERT INTO observations VALUES ('o', 'p', '/uploads/test.png', '2026-01-01',
                'test-only', 18, 91, 'test-mock', 1, 25, 65, 'Loamy', 'Normal');
        ''')
        original = db.execute('SELECT * FROM observations').fetchone()
    initialize(path)
    initialize(path)  # Idempotent on later startups.
    with connect(path) as db:
        assert tuple(db.execute('SELECT * FROM observations').fetchone()) == original
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert next(row for row in db.execute('PRAGMA table_info(observations)') if row['name'] == 'severity')['notnull'] == 0
        db.execute('UPDATE observations SET severity = NULL WHERE id = ?', ('o',))
        assert db.execute('SELECT severity FROM observations').fetchone()[0] is None
