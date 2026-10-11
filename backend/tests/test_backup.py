import hashlib
import json
import sqlite3
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.prediction import MockPredictor
from backup import backup


@pytest.fixture
def source(tmp_path):
    db, uploads = tmp_path/'journal.db', tmp_path/'uploads'
    with TestClient(create_app(db, uploads, MockPredictor())) as client:
        plant = client.post('/plants', json={'name':'Private test plant'}).json()
        image = BytesIO()
        Image.new('RGB', (224, 224), 'white').save(image, format='PNG')
        row = client.post(f"/plants/{plant['id']}/records", data={'request_id':'backup-test-01', 'soil_condition':'Normal'},
                          files={'image':('leaf.png', image.getvalue())})
        assert row.status_code == 201
    return db, uploads, tmp_path/'private.zip'


def test_backup_roundtrip_integrity_and_source_unchanged(source, tmp_path):
    db, uploads, output = source
    original = db.read_bytes()
    photos = {p.name:p.read_bytes() for p in uploads.iterdir()}
    assert backup(*source) == {'plants':1, 'observations':1, 'files':3}
    assert output.stat().st_mode & 0o777 == 0o600
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        records = json.loads(archive.read('records.json'))
        row = records['observations'][0]
        assert all(row[key] is None for key in ('temperature','humidity','soil_type','disease','severity'))
        assert 'request_fingerprint' not in row
        restored = tmp_path/'restored.sqlite'
        restored.write_bytes(archive.read('journal.sqlite'))
        with sqlite3.connect(restored) as connection:
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
            assert connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 1
    assert db.read_bytes() == original
    assert {p.name:p.read_bytes() for p in uploads.iterdir()} == photos
    with pytest.raises(FileExistsError):
        backup(*source)


@pytest.mark.parametrize('damage', ['missing', 'symlink', 'hash', 'path'])
def test_backup_refuses_incomplete_or_unsafe_images(source, damage):
    db, uploads, output = source
    image = next(uploads.iterdir())
    if damage == 'missing':
        image.unlink()
    elif damage == 'symlink':
        target = image.with_suffix('.private')
        image.rename(target)
        image.symlink_to(target)
    elif damage == 'hash':
        image.write_bytes(b'changed test fixture')
    else:
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE observations SET image_path='/uploads/../../private.png'")
    with pytest.raises(ValueError):
        backup(*source)
    assert not output.exists()
    assert not list(output.parent.glob('agrisense-backup-*'))


def test_backup_refuses_upload_destination(source):
    db, uploads, _ = source
    with pytest.raises(ValueError):
        backup(db, uploads, uploads/'backup.zip')
