"""Startup diagnostics must identify the failing stage without revealing local details."""
import logging

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.startup import startup_stage


def test_stage_logs_timing_and_exception_type_only(caplog):
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        with startup_stage('database'):
            pass
        with pytest.raises(RuntimeError):
            with startup_stage('tomato_checkpoint'):
                raise RuntimeError('secret configuration /private/weights')
    assert 'stage=database state=completed duration_seconds=' in caplog.text
    assert 'stage=tomato_checkpoint state=failed' in caplog.text
    assert 'error_type=RuntimeError' in caplog.text
    assert 'secret' not in caplog.text and '/private' not in caplog.text


def test_missing_checkpoint_still_serves_honest_health(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        with TestClient(create_app(tmp_path/'journal.db', tmp_path/'uploads',
                                   checkpoint_path=tmp_path/'missing.pt')) as client:
            health = client.get('/health').json()
            assert client.get('/ready').status_code == 503
    assert health['capabilities']['record_only'] is True
    assert health['capabilities']['tomato_analysis'] is False
    assert health['capabilities']['plant_content_screening'] is False
    assert 'stage=tomato_checkpoint state=failed' in caplog.text
    assert str(tmp_path) not in caplog.text


def test_production_requires_explicit_hosts_and_persistent_storage(monkeypatch, tmp_path):
    from app.main import ROOT
    monkeypatch.setenv('AGRISENSE_ENV', 'production')
    monkeypatch.delenv('AGRISENSE_ALLOWED_HOSTS', raising=False)
    with pytest.raises(RuntimeError, match='AGRISENSE_ALLOWED_HOSTS'):
        create_app(tmp_path/'journal.db', tmp_path/'uploads')

    monkeypatch.setenv('AGRISENSE_ALLOWED_HOSTS', 'api.example.test')
    monkeypatch.setenv('AGRISENSE_CHECKPOINT_PATH', str(tmp_path/'model.pt'))
    monkeypatch.setenv('AGRISENSE_PLANT_VERIFIER_WEIGHTS', str(tmp_path/'clip.safetensors'))
    (tmp_path/'model.pt').touch()
    (tmp_path/'clip.safetensors').touch()
    with pytest.raises(RuntimeError, match='persistent path'):
        create_app(ROOT/'database'/'journal.db', tmp_path/'uploads')


def test_production_hides_docs_checks_host_and_separates_readiness(monkeypatch, tmp_path):
    from app.prediction import TrainedTomatoPredictor
    from app.database import initialize
    from hashlib import sha256

    monkeypatch.setenv('AGRISENSE_ENV', 'production')
    monkeypatch.setenv('AGRISENSE_ALLOWED_HOSTS', 'api.example.test,testserver')
    monkeypatch.setenv('AGRISENSE_CORS_ORIGINS', 'https://app.example.test')
    checkpoint, verifier_weights = tmp_path/'model.pt', tmp_path/'clip.safetensors'
    checkpoint.touch()
    verifier_weights.touch()
    monkeypatch.setenv('AGRISENSE_CHECKPOINT_PATH', str(checkpoint))
    monkeypatch.setenv('AGRISENSE_PLANT_VERIFIER_WEIGHTS', str(verifier_weights))
    for name in ('AGRISENSE_CHECKPOINT_SHA256', 'AGRISENSE_PLANT_VERIFIER_SHA256'):
        monkeypatch.setenv(name, sha256(b'').hexdigest())
    monkeypatch.setenv('AGRISENSE_ACCESS_ISSUER', 'https://demo.cloudflareaccess.com')
    monkeypatch.setenv('AGRISENSE_ACCESS_AUD', 'test-audience')
    monkeypatch.setenv('AGRISENSE_DEMO_EMAILS', 'demo@example.test')
    initialize(tmp_path/'persistent'/'journal.db')
    (tmp_path/'persistent'/'uploads').mkdir()
    model = object.__new__(TrainedTomatoPredictor)
    app = create_app(tmp_path/'persistent'/'journal.db', tmp_path/'persistent'/'uploads',
                     predictor=model, plant_verifier=object())
    (tmp_path/'persistent'/'uploads'/'private-photo.jpg').write_bytes(b'private')
    with TestClient(app) as client:
        assert client.get('/docs').status_code == 401
        assert client.get('/openapi.json').status_code == 401
        assert client.get('/ready').json() == {'status': 'ready'}
        assert client.get('/uploads/private-photo.jpg').status_code == 401
        assert client.get('/health').status_code == 401
        assert client.get('/health', headers={'host': 'attacker.invalid'}).status_code == 400


def test_production_rejects_non_https_cors(monkeypatch, tmp_path):
    monkeypatch.setenv('AGRISENSE_ENV', 'production')
    monkeypatch.setenv('AGRISENSE_ALLOWED_HOSTS', 'api.example.test')
    monkeypatch.setenv('AGRISENSE_CORS_ORIGINS', 'http://app.example.test')
    for name in ('AGRISENSE_CHECKPOINT_PATH', 'AGRISENSE_PLANT_VERIFIER_WEIGHTS'):
        artifact = tmp_path/name
        artifact.touch()
        monkeypatch.setenv(name, str(artifact))
    with pytest.raises(RuntimeError, match='HTTPS'):
        create_app(tmp_path/'persistent'/'journal.db', tmp_path/'persistent'/'uploads')
