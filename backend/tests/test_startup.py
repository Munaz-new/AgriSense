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
    assert health['capabilities']['record_only'] is True
    assert health['capabilities']['tomato_analysis'] is False
    assert health['capabilities']['plant_content_screening'] is False
    assert 'stage=tomato_checkpoint state=failed' in caplog.text
    assert str(tmp_path) not in caplog.text
