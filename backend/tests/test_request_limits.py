from fastapi.testclient import TestClient

from app.main import create_app
from app.prediction import MockPredictor
from app.request_limits import MAX_REQUEST_BYTES


def test_unapproved_browser_writes_are_rejected_without_persistence(tmp_path):
    with TestClient(create_app(tmp_path/'db', tmp_path/'uploads', MockPredictor())) as client:
        for origin in ('https://untrusted.example', 'null'):
            assert client.post('/plants', json={'name':'test'}, headers={'Origin':origin}).status_code == 403
        assert client.get('/plants').json() == []
        assert client.post('/plants', json={'name':'native request without Origin'}).status_code == 201
        assert client.post('/plants', json={'name':'approved browser'}, headers={'Origin':'http://localhost:8081'}).status_code == 201
        response = client.get('/plants')
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'


def test_request_limit_rejects_declared_and_streamed_bodies(tmp_path):
    with TestClient(create_app(tmp_path/'db', tmp_path/'uploads', MockPredictor())) as client:
        assert client.post('/plants', content=b'{}', headers={'Content-Length':str(MAX_REQUEST_BYTES+1)}).status_code == 413
        def chunks():
            for _ in range(MAX_REQUEST_BYTES // 65536 + 1):
                yield b'x' * 65536
        response = client.post('/plants', content=chunks(), headers={'Content-Type':'application/json'})
        assert response.status_code == 413
        assert client.get('/plants').json() == []
        assert list((tmp_path/'uploads').iterdir()) == []
