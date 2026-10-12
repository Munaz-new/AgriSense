"""Bounded real HTTP smoke test. Uses disposable SQLite/uploads and committed fixtures.

Run from the repository root with model/.venv/bin/python -m backend.smoke_local --real-model.
Without --real-model, deliberately missing weights exercise record-only availability.
Both modes verify an isolated backup restore; --extra-records adds a bounded journal check.
No mock predictor or suitability substitute is installed by this harness.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from zipfile import ZipFile

import httpx

from .backup import backup

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


def check_backup_restore(storage, plant, history, leaf, fields, startup_timeout):
    """Restore only this run's generated archive into a new disposable directory.

    This is an integration check, not an importer for user-supplied archives.
    """
    def source_hashes():
        return {str(path.relative_to(storage)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [storage/'journal.db', *sorted((storage/'uploads').iterdir())]}

    before = source_hashes()
    bundle = storage/'private-backup.zip'
    summary = backup(storage/'journal.db', storage/'uploads', bundle)
    assert summary['plants'] == 1 and summary['observations'] == len(history)
    assert bundle.stat().st_mode & 0o777 == 0o600
    restored = storage/'isolated-restore'
    restored.mkdir(mode=0o700)
    (restored/'uploads').mkdir(mode=0o700)
    names = {'journal.sqlite', 'records.json', *(row['image_path'].lstrip('/') for row in history)}
    with ZipFile(bundle) as archive:
        assert set(archive.namelist()) == names | {'manifest.json'}
        assert len(archive.namelist()) == len(names) + 1
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['format'] == 'agrisense-backup-v1'
        assert set(manifest['sha256']) == names
        for name in names:
            data = archive.read(name)
            assert hashlib.sha256(data).hexdigest() == manifest['sha256'][name]
        # Fixed database destination and photo basenames; never extractall().
        (restored/'journal.db').write_bytes(archive.read('journal.sqlite'))
        for row in history:
            name = row['image_path'].split('/')[-1]
            with (restored/'uploads'/name).open('xb') as photo:
                photo.write(archive.read('uploads/' + name))
    with sqlite3.connect(restored/'journal.db') as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == len(history)
    with server(restored, False, startup_timeout) as client:
        assert client.get('/plants').json() == [plant]
        route = f"/plants/{plant['id']}"
        assert client.get(route + '/observations').json() == history
        for row in history:
            response = client.get(row['image_path'])
            assert response.status_code == 200 and response.content == leaf
        replay = client.post(route + '/records', data=fields,
                             files={'image': ('fixture.jpg', leaf, 'image/jpeg')})
        assert replay.status_code == 200 and replay.json() == history[0]
        conflict = client.post(route + '/records', data={**fields, 'humidity': '25'},
                               files={'image': ('fixture.jpg', leaf, 'image/jpeg')})
        assert conflict.status_code == 409
        assert client.get(route + '/observations').json() == history
    assert source_hashes() == before
    return {'status': 'PASS', 'observations': len(history), 'images': len(history),
            'source_unchanged': True, 'retry_identity_preserved': True}


def run(real_model=False, startup_timeout=60, extra_records=0):
    if not 0 <= extra_records <= 1000:
        raise ValueError('extra_records must be between 0 and 1000')
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
            plant_fields = {'name': 'Disposable smoke plant', 'crop_name': 'tomato', 'request_id': 'smoke-plant-001'}
            response = client.post('/plants', json=plant_fields)
            assert response.status_code == 201
            plant_record = response.json()
            replay_plant = client.post('/plants', json=plant_fields)
            assert replay_plant.status_code == 200 and replay_plant.json() == plant_record
            assert client.post('/plants', json={**plant_fields, 'crop_name': 'potato'}).status_code == 409
            assert len(client.get('/plants').json()) == 1
            results['plant_creation_retry_conflict'] = 'PASS'
            plant = plant_record['id']
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
            expected = [first, second]
            if extra_records:
                started = time.monotonic()
                for index in range(extra_records):
                    timestamp = datetime(2025, 1, 3, tzinfo=timezone.utc) + timedelta(seconds=index)
                    response = post(route, {'request_id': f'smoke-load-{index:04d}',
                                            'soil_condition': 'Normal',
                                            'observed_at': timestamp.isoformat()})
                    assert response.status_code == 201, (index, response.status_code, response.text)
                    row = response.json()
                    assert row['duplicate_of'] == first['id']
                    assert row['analysis_status'] == 'not_requested'
                    assert all(row[key] is None for key in ('temperature', 'humidity', 'soil_type', 'disease', 'severity'))
                    expected.append(row)
                results['bounded_journal_writes'] = {
                    'status': 'PASS', 'extra_records': extra_records,
                    'elapsed_seconds': round(time.monotonic() - started, 3),
                }
            if real_model:
                assert post('/check-plant-suitability').status_code == 200
                rejected = post('/check-plant-suitability', image=logo)
                assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'non_plant_image'
                response = post(f'/plants/{plant}/observations', {'request_id': 'smoke-analysis-1'})
                assert response.status_code == 201, response.text
                result = response.json()
                expected.append(result)
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
            started = time.monotonic()
            response = client.get(f'/plants/{plant}/observations')
            assert response.status_code == 200
            history = response.json()
            assert history == sorted(expected, key=lambda row: (row['observed_at'] or row['created_at'], row['created_at'], row['id']))
            assert len({row['request_id'] for row in history}) == len(expected)
            results['journal_history'] = {
                'status': 'PASS', 'observations': len(history), 'response_bytes': len(response.content),
                'elapsed_seconds': round(time.monotonic() - started, 3),
            }
            assert client.get(first['image_path']).content == leaf
            progress = client.get(f'/plants/{plant}/progression').json()
            assert progress['status'] == 'unavailable' and progress['delta'] is None
            results['history_images_unavailable_trends'] = 'PASS'
        with server(storage, False, startup_timeout) as client:
            assert client.get(f'/plants/{plant}/observations').json() == history
            results['persistence_after_process_restart'] = 'PASS'
        results['isolated_backup_restore'] = check_backup_restore(
            storage, plant_record, history, leaf, fields, startup_timeout)
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--startup-timeout', type=int, default=60)
    parser.add_argument('--extra-records', type=int, default=0,
                        help='Create 0–1000 additional disposable record-only observations for a bounded journal check.')
    args = parser.parse_args()
    if not 1 <= args.startup_timeout <= 300:
        parser.error('--startup-timeout must be between 1 and 300 seconds')
    if not 0 <= args.extra_records <= 1000:
        parser.error('--extra-records must be between 0 and 1000')
    run(args.real_model, args.startup_timeout, args.extra_records)
