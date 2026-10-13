"""Deletion operates only on disposable journals and always preserves a recovery archive."""
import json
from pathlib import Path
import sqlite3
import sys
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.prediction import MockPredictor

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import delete_plant as deletion


@pytest.fixture
def journal(tmp_path):
    database, uploads = tmp_path/'journal.db', tmp_path/'uploads'
    photo = (Path(__file__).parent/'fixtures/tomato_leaf_healthy.jpg').read_bytes()
    with TestClient(create_app(database, uploads, MockPredictor())) as client:
        a = client.post('/plants', json={'name':'Delete me'}).json()['id']
        b = client.post('/plants', json={'name':'Keep me'}).json()['id']
        for plant, identity in [(a,'first-delete'),(a,'second-delete'),(b,'keep-record')]:
            response = client.post(f'/plants/{plant}/records',data={'request_id':identity,'soil_condition':'Normal'},
                                   files={'image':('leaf.jpg',photo,'image/jpeg')})
            assert response.status_code == 201
    return database, uploads, a, b


def test_preview_does_not_modify_source(journal):
    database, uploads, plant, _ = journal
    before = database.read_bytes()
    result = deletion.delete_plant(database, uploads, plant)
    assert result['observations'] == 2 and result['applied'] is False
    assert database.read_bytes() == before


def test_applied_deletion_has_complete_restorable_backup_and_retains_other_plant(journal, tmp_path):
    database, uploads, plant, other = journal
    photos = {p.name:p.read_bytes() for p in uploads.iterdir()}
    output = tmp_path/'backup.zip'
    result = deletion.delete_plant(database,uploads,plant,apply=True,confirm_name='Delete me',backup_path=output)
    assert result['applied'] is True and result['photos_retained'] is True
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT id FROM plants').fetchall() == [(other,)]
        assert db.execute('SELECT plant_id FROM observations').fetchall() == [(other,)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    with ZipFile(output) as archive:
        rows=json.loads(archive.read('records.json'))
        assert len(rows['plants']) == 2 and len(rows['observations']) == 3
        restored=tmp_path/'restored.sqlite';restored.write_bytes(archive.read('journal.sqlite'))
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 3
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert {p.name:p.read_bytes() for p in uploads.iterdir()} == photos
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('reason',['wrong-name','no-backup','existing-backup','missing-photo','missing-plant'])
def test_refusals_preserve_records(journal,tmp_path,reason):
    database,uploads,plant,_=journal
    output=tmp_path/'backup.zip';name='Delete me'
    if reason=='wrong-name': name='wrong'
    if reason=='no-backup': output=None
    if reason=='existing-backup': output.write_bytes(b'keep this existing archive')
    if reason=='missing-photo': next(uploads.iterdir()).unlink()
    if reason=='missing-plant': plant='missing'
    before=database.read_bytes()
    with pytest.raises((ValueError,OSError)):
        deletion.delete_plant(database,uploads,plant,apply=True,confirm_name=name,backup_path=output)
    assert database.read_bytes()==before
    if reason=='existing-backup': assert output.read_bytes()==b'keep this existing archive'


def test_concurrent_change_after_backup_refuses_deletion(journal,tmp_path,monkeypatch):
    database,uploads,plant,other=journal
    original=deletion.backup
    def changed(*args):
        result=original(*args)
        with sqlite3.connect(database) as db:
            db.execute('UPDATE plants SET name=? WHERE id=?',('Changed during backup',other))
        return result
    monkeypatch.setattr(deletion,'backup',changed)
    with pytest.raises(ValueError,match='Journal changed'):
        deletion.delete_plant(database,uploads,plant,apply=True,confirm_name='Delete me',backup_path=tmp_path/'backup.zip')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM plants').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==3
