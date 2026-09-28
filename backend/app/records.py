"""Record-only persistence, with atomic request deduplication per plant."""
from hashlib import sha256
import json
from uuid import uuid4

from .database import connect, insert_observation


class RequestConflict(ValueError):
    pass


def save_record(database_path, upload_dir, plant_id, data, extension, fields, created_at):
    digest = sha256(data).hexdigest()
    fingerprint = sha256(json.dumps(dict(plant_id=plant_id, image_sha256=digest, **fields),
                                    sort_keys=True, allow_nan=False).encode()).hexdigest()
    target = None
    written = False
    try:
        with connect(database_path) as db:
            # Lock before checking the key; concurrent retries cannot create two records.
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM observations WHERE plant_id=? AND request_id=?',
                                  (plant_id, fields['request_id'])).fetchone()
            if previous:
                if previous['request_fingerprint'] != fingerprint:
                    raise RequestConflict('Request ID already used with different content. Refresh history before starting a new record.')
                return dict(previous), True
            duplicate = db.execute('''SELECT id FROM observations WHERE plant_id=? AND image_sha256=?
                ORDER BY created_at, id LIMIT 1''', (plant_id, digest)).fetchone()
            identifier = str(uuid4())
            filename = f'{identifier}.{extension}'
            observation = dict(id=identifier, plant_id=plant_id, image_path=f'/uploads/{filename}',
                               created_at=created_at, disease=None, severity=None, confidence=None,
                               predictor=None, is_mock=False, analysis_status='not_requested',
                               image_sha256=digest, request_fingerprint=fingerprint,
                               duplicate_of=duplicate['id'] if duplicate else None, **fields)
            target = upload_dir / filename
            with target.open('xb') as output:
                written = True
                output.write(data)
            insert_observation(db, observation)
            saved = dict(db.execute('SELECT * FROM observations WHERE id=?', (identifier,)).fetchone())
        return saved, False
    except Exception:
        if written:
            target.unlink(missing_ok=True)
        raise
