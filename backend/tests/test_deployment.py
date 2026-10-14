"""Production auth, persistence and Railway startup contracts. Synthetic data only."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.database import initialize
from app.demo_access import AccessVerifier
from app.deployment import verify_artifact, verify_journal, verify_production_files
from app.main import create_app
from app.prediction import TrainedTomatoPredictor

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.serve import server_options, prepare_volume_permissions
from backend.backup import backup
from backend.restore_demo import restore


@pytest.fixture
def production(tmp_path, monkeypatch):
    db, uploads = tmp_path/'journal.db', tmp_path/'uploads'
    initialize(db)
    uploads.mkdir()
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO plants VALUES ('test-plant', 'Synthetic demo', '2026-01-01', 'tomato')")
    (uploads/'test-photo.jpg').write_bytes(b'synthetic-photo')
    weights = tmp_path/'test-weights'
    weights.write_bytes(b'test-weights')
    settings = {
        'AGRISENSE_ENV': 'production', 'AGRISENSE_ALLOWED_HOSTS': 'testserver,healthcheck.railway.app',
        'AGRISENSE_CORS_ORIGINS': 'https://demo.pages.dev',
        'AGRISENSE_ACCESS_ISSUER': 'https://demo.cloudflareaccess.com',
        'AGRISENSE_ACCESS_AUD': 'demo-audience', 'AGRISENSE_DEMO_EMAILS': 'invited@example.test',
        'AGRISENSE_CHECKPOINT_PATH': str(weights), 'AGRISENSE_PLANT_VERIFIER_WEIGHTS': str(weights),
        'AGRISENSE_CHECKPOINT_SHA256': sha256(weights.read_bytes()).hexdigest(),
        'AGRISENSE_PLANT_VERIFIER_SHA256': sha256(weights.read_bytes()).hexdigest(),
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid='test-key', alg='RS256', use='sig')
    monkeypatch.setattr(jwt.PyJWKClient, 'fetch_data', lambda self: {'keys': [public]})
    def token(**changes):
        claims = dict(iss=settings['AGRISENSE_ACCESS_ISSUER'], aud='demo-audience',
                      sub='test-subject', email='invited@example.test', iat=int(time.time()), exp=int(time.time())+600)
        claims.update(changes)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})
    model = object.__new__(TrainedTomatoPredictor)
    return db, uploads, model, token


def test_production_auth_all_private_paths_and_direct_origin(production):
    db, uploads, model, token = production
    with TestClient(create_app(db, uploads, predictor=model, plant_verifier=object())) as client:
        for method, path in [('GET', '/plants'), ('GET', '/plants/test-plant'),
                             ('GET', '/plants/test-plant/observations'), ('GET', '/plants/test-plant/progression'),
                             ('POST', '/plants'), ('PATCH', '/plants/test-plant'),
                             ('POST', '/plants/test-plant/records'), ('POST', '/plants/test-plant/observations'),
                             ('POST', '/predict'), ('POST', '/validate-image'), ('POST', '/check-plant-suitability'),
                             ('GET', '/uploads/test-photo.jpg'), ('DELETE', '/plants/test-plant')]:
            response = client.request(method, path, headers={'cf-access-authenticated-user-email': 'invited@example.test'})
            assert response.status_code == 401, path
            assert response.headers['cache-control'] == 'no-store'
        headers = {'cf-access-jwt-assertion': token()}
        assert len(client.get('/plants', headers=headers).json()) == 1
        image = client.get('/uploads/test-photo.jpg', headers=headers)
        assert image.content == b'synthetic-photo' and image.headers['cache-control'] == 'no-store'
        assert client.get('/docs', headers=headers).status_code == 404
        assert client.delete('/plants/test-plant', headers=headers).status_code == 405
        assert client.get('/ready', headers={'host': 'healthcheck.railway.app'}).status_code == 200
        assert client.get('/ready', headers={'host': 'wrong.invalid'}).status_code == 400


@pytest.mark.parametrize('changes', [{'aud': 'wrong'}, {'iss': 'https://other.cloudflareaccess.com'},
                                    {'exp': 1}, {'iat': 9999999999}, {'email': 'uninvited@example.test'},
                                    {'email': None}, {'sub': ''}])
def test_invalid_identity_is_rejected(production, changes):
    db, uploads, model, token = production
    with TestClient(create_app(db, uploads, predictor=model, plant_verifier=object())) as client:
        assert client.get('/plants', headers={'cf-access-jwt-assertion': token(**changes)}).status_code == 401


def test_unsigned_forged_and_unavailable_keys_fail_closed(production, monkeypatch):
    db, uploads, model, token = production
    verifier = AccessVerifier()
    for value in ['garbage', jwt.encode({'email': 'invited@example.test'}, '', algorithm='none'),
                  jwt.encode({'email': 'invited@example.test'}, 'fake-test-secret', algorithm='HS256')]:
        with pytest.raises(Exception):
            verifier.verify(value)
    monkeypatch.setattr(jwt.PyJWKClient, 'fetch_data', lambda self: (_ for _ in ()).throw(OSError('offline')))
    with TestClient(create_app(db, uploads, predictor=model, plant_verifier=object())) as client:
        assert client.get('/plants', headers={'cf-access-jwt-assertion': token()}).status_code == 401


def test_exact_cors_patch_and_csrf(production):
    db, uploads, model, token = production
    with TestClient(create_app(db, uploads, predictor=model, plant_verifier=object())) as client:
        preflight = {'origin': 'https://demo.pages.dev', 'access-control-request-method': 'PATCH',
                     'access-control-request-headers': 'content-type'}
        response = client.options('/plants/test-plant', headers=preflight)
        assert response.status_code == 200 and response.headers['access-control-allow-origin'] == preflight['origin']
        preflight['origin'] = 'https://preview.demo.pages.dev'
        assert client.options('/plants/test-plant', headers=preflight).status_code == 400
        headers = {'cf-access-jwt-assertion': token(), 'origin': 'https://attacker.invalid'}
        assert client.patch('/plants/test-plant', headers=headers, json={'crop_name': 'potato'}).status_code == 403


def test_missing_database_never_replaced_and_readiness_detects_loss(production):
    db, uploads, model, token = production
    with TestClient(create_app(db, uploads, predictor=model, plant_verifier=object())) as client:
        db.unlink()
        assert client.get('/ready').status_code == 503
        assert not db.exists()
        with pytest.raises(sqlite3.OperationalError):
            client.get('/plants', headers={'cf-access-jwt-assertion': token()})
        assert not db.exists()
    with pytest.raises(RuntimeError, match='empty initialization'):
        create_app(db, uploads, predictor=model, plant_verifier=object())
    assert not db.exists()


def test_hashes_storage_and_missing_auth_fail_closed(production, monkeypatch):
    db, uploads, model, token = production
    with pytest.raises(RuntimeError, match='mismatch'):
        verify_artifact(db, '0'*64)
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_ID', 'test-environment')
    with pytest.raises(RuntimeError, match='attached volume'):
        verify_production_files(db, uploads)
    monkeypatch.delenv('AGRISENSE_ACCESS_AUD')
    with pytest.raises(RuntimeError, match='AGRISENSE_ACCESS'):
        create_app(db, uploads, predictor=model, plant_verifier=object())


def test_missing_referenced_photo_refuses_startup(production):
    db, uploads, *_ = production
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO observations(id,plant_id,image_path,created_at,is_mock) VALUES('o','test-plant','/uploads/missing.jpg','2026-01-01',0)")
    with pytest.raises(RuntimeError, match='photo'):
        verify_journal(db, uploads)


def test_port_and_one_worker(monkeypatch):
    monkeypatch.setenv('PORT', '9217')
    assert server_options() == dict(host='0.0.0.0', port=9217, workers=1, access_log=False,
                                   proxy_headers=False, limit_concurrency=16)
    for value in ['0', '65536', 'abc', '8000; echo unsafe']:
        monkeypatch.setenv('PORT', value)
        with pytest.raises(ValueError):
            server_options()


def test_railway_cannot_fall_back_to_unauthenticated_development(monkeypatch, tmp_path):
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_ID', 'test-environment')
    monkeypatch.setenv('AGRISENSE_ENV', 'development')
    with pytest.raises(RuntimeError, match='AGRISENSE_ENV=production'):
        create_app(tmp_path/'missing.db', tmp_path/'uploads')
    assert not (tmp_path/'missing.db').exists()


def test_volume_permissions_refuse_symlinks_without_touching_contents(monkeypatch, tmp_path):
    volume = tmp_path/'volume'; volume.mkdir()
    models = volume/'models'; models.mkdir()
    weights = models/'model.pt'; weights.write_bytes(b'test-only')
    changed = []
    monkeypatch.setattr('os.chown', lambda *args, **kwargs: changed.append(args[0]))
    prepare_volume_permissions(volume)
    assert weights.read_bytes() == b'test-only'
    assert weights in changed and weights.stat().st_mode & 0o777 == 0o600
    changed.clear()
    (models/'link').symlink_to(weights)
    with pytest.raises(RuntimeError, match='Unsafe'):
        prepare_volume_permissions(volume)
    assert not changed


def test_railway_drops_privileges_before_uvicorn(monkeypatch):
    from backend import serve
    events = []
    monkeypatch.setenv('RAILWAY_VOLUME_MOUNT_PATH', '/data')
    monkeypatch.setattr('os.geteuid', lambda: 0)
    monkeypatch.setattr(serve, 'prepare_volume_permissions', lambda p: events.append(('prepare', str(p))))
    monkeypatch.setattr('os.setgroups', lambda groups: events.append(('groups', groups)))
    monkeypatch.setattr('os.setgid', lambda gid: events.append(('gid', gid)))
    monkeypatch.setattr('os.setuid', lambda uid: events.append(('uid', uid)))
    monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: events.append(('serve', args[0])))
    serve.main()
    assert events == [('prepare', '/data'), ('groups', []), ('gid', 10001), ('uid', 10001), ('serve', 'backend.app.main:app')]


def test_restore_preserves_records_and_refuses_overwrite(tmp_path):
    db, uploads = tmp_path/'source.db', tmp_path/'source-uploads'
    initialize(db)
    uploads.mkdir()
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO plants VALUES ('p','test','2026-01-01',NULL)")
    archive = tmp_path/'backup.zip'
    original = db.read_bytes()
    backup(db, uploads, archive)
    volume = tmp_path/'volume'; volume.mkdir()
    restore(archive, volume)
    # SQLite's backup API may change header counters; compare logical records.
    with sqlite3.connect(volume/'journal/agrisense.db') as restored:
        assert restored.execute('SELECT * FROM plants').fetchall() == [('p', 'test', '2026-01-01', None)]
    assert db.read_bytes() == original
    with pytest.raises(FileExistsError):
        restore(archive, volume)
