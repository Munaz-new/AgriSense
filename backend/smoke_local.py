"""Bounded real HTTP smoke test. Uses disposable SQLite/uploads and committed fixtures.

Run from the repository root with model/.venv/bin/python -m backend.smoke_local --real-model.
Without --real-model, deliberately missing weights exercise record-only availability.
No mock predictor or suitability substitute is installed by this harness.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server(storage, real_model, timeout):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, AGRISENSE_DB_PATH=str(storage/'journal.db'),
               AGRISENSE_UPLOAD_DIR=str(storage/'uploads'), OMP_NUM_THREADS='4',
               AGRISENSE_CORS_ORIGINS='http://localhost:8081')
    env['AGRISENSE_CHECKPOINT_PATH'] = str(ROOT/'model/checkpoints/tomato_gpu_epoch5_retry2/best.pt'
                                          if real_model else storage/'intentionally-absent.pt')
    log_path = storage/'startup.log'
    with log_path.open('w') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                    '--host', '127.0.0.1', '--port', str(port), '--workers', '1',
                                    '--no-access-log'], cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=60, trust_env=False) as client:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Server exited during startup')
                try:
                    response = client.get('/health', timeout=1)
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(.2)
            else:
                raise TimeoutError('Server did not become ready before the startup deadline')
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        print(log_path.read_text(), flush=True)


def run(real_model=False, startup_timeout=60):
    # asyncio uses this mechanism to receive worker completion notifications.
    a, b = socket.socketpair()
    try:
        a.send(b'x')
    except PermissionError as error:
        raise RuntimeError('Sandbox blocks asyncio socketpair wakeups (EPERM). Run this local test '
                           'in an approved context allowing loopback sockets; do not bypass model checks.') from error
    finally:
        a.close()
        b.close()
    fixtures = ROOT/'backend/tests/fixtures'
    leaf = (fixtures/'tomato_leaf_bacterial_spot.jpg').read_bytes()
    logo = (fixtures/'unrelated_resume_logo.png').read_bytes()
    results = {}
    with TemporaryDirectory(prefix='agrisense-smoke-') as directory:
        storage = Path(directory)
        with server(storage, real_model, startup_timeout) as client:
            health = client.get('/health').json()
            assert health['capabilities']['tomato_analysis'] is real_model, health
            results['health'] = 'PASS'
            cors = client.get('/health', headers={'Origin': 'http://localhost:8081'})
            assert cors.headers.get('access-control-allow-origin') == 'http://localhost:8081'
            results['browser_origin_api_headers'] = 'PASS'
            response = client.post('/plants', json={'name': 'Disposable smoke plant', 'crop_name': 'tomato'})
            assert response.status_code == 201
            plant = response.json()['id']
            route = f'/plants/{plant}/records'
            def post(path, fields=None, image=leaf):
                return client.post(path, data=fields or {}, files={'image': ('fixture.jpg', image, 'image/jpeg')})
            assert post('/validate-image').status_code == 200
            assert post('/validate-image', image=b'corrupt').status_code == 415
            results['upload_and_corrupt_rejection'] = 'PASS'
            fields = {'request_id': 'smoke-record-0001', 'soil_condition': 'Normal',
                      'observed_at': '2025-01-01T00:00:00Z'}
            response = post(route, fields)
            assert response.status_code == 201
            first = response.json()
            assert all(first[k] is None for k in ('temperature', 'humidity', 'soil_type', 'disease', 'severity'))
            replay = post(route, fields)
            assert replay.status_code == 200 and replay.json() == first
            assert post(route, {**fields, 'humidity': '25'}).status_code == 409
            response = post(route, {**fields, 'request_id': 'smoke-record-0002', 'temperature': '21.5',
                                   'humidity': '0', 'soil_type': 'Sandy loam', 'observed_at': '2025-01-02T00:00:00Z'})
            assert response.status_code == 201
            second = response.json()
            assert (second['temperature'], second['humidity'], second['soil_type']) == (21.5, 0, 'Sandy loam')
            assert second['duplicate_of'] == first['id']
            assert post(route, {**fields, 'request_id': 'invalid-record-1', 'humidity': '101'}).status_code == 422
            results['records_context_nulls_retry_conflict'] = 'PASS'
            if real_model:
                assert post('/check-plant-suitability').status_code == 200
                rejected = post('/check-plant-suitability', image=logo)
                assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'non_plant_image'
                response = post(f'/plants/{plant}/observations', {'request_id': 'smoke-analysis-1'})
                assert response.status_code == 201, response.text
                result = response.json()
                assert result['analysis_status'] == 'completed' and result['is_mock'] is False
                assert result['severity'] is None and 0 <= result['prediction_score'] <= 100
                digest = hashlib.sha256((ROOT/'model/checkpoints/tomato_gpu_epoch5_retry2/best.pt').read_bytes()).hexdigest()
                assert result['checkpoint_id'] == 'sha256:' + digest
                again = post(f'/plants/{plant}/observations', {'request_id': 'smoke-analysis-1'})
                assert again.status_code == 200 and again.json() == result
                results['real_screening_and_analysis'] = 'PASS'
                results['fixture_output_not_accuracy_evidence'] = {k: result[k] for k in ('disease', 'prediction_score', 'severity')}
            else:
                assert post('/predict').status_code == 503
                assert post('/check-plant-suitability').status_code == 503
                results['honest_analysis_unavailable'] = 'PASS'
            history = client.get(f'/plants/{plant}/observations').json()
            assert len(history) == (3 if real_model else 2)
            assert history[:2] == [first, second]
            assert client.get(first['image_path']).content == leaf
            progress = client.get(f'/plants/{plant}/progression').json()
            assert progress['status'] == 'unavailable' and progress['delta'] is None
            results['history_images_unavailable_trends'] = 'PASS'
        with server(storage, False, startup_timeout) as client:
            assert client.get(f'/plants/{plant}/observations').json() == history
            results['persistence_after_process_restart'] = 'PASS'
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--startup-timeout', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.startup_timeout <= 300:
        parser.error('--startup-timeout must be between 1 and 300 seconds')
    run(args.real_model, args.startup_timeout)
