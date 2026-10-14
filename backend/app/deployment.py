"""Read-only production checks; never initialize a replacement journal."""
from hashlib import file_digest
import os
from pathlib import Path
import re
import sqlite3


def verify_artifact(path: Path, expected: str):
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise RuntimeError('Production requires an explicit SHA-256 for each model artifact.')
    with path.open('rb') as source:
        if file_digest(source, 'sha256').hexdigest() != expected:
            raise RuntimeError('Model artifact SHA-256 mismatch; startup refused.')


def verify_journal(database: Path, uploads: Path):
    if not database.is_file() or not uploads.is_dir():
        raise RuntimeError('Restore the existing demo database and uploads before production startup; empty initialization is forbidden.')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise RuntimeError('Production requires a reviewed schema-3 journal; migrate an offline copy first.')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Journal integrity check failed.')
        db.execute('SELECT count(*) FROM plants').fetchone()
        for image_path, expected in db.execute('SELECT image_path, image_sha256 FROM observations'):
            if not re.fullmatch(r'/uploads/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)', image_path, re.IGNORECASE):
                raise RuntimeError('Journal contains an unsafe image reference.')
            photo = uploads / image_path.split('/')[-1]
            if photo.is_symlink() or not photo.is_file():
                raise RuntimeError('A referenced journal photo is missing or unsafe.')
            if expected:
                with photo.open('rb') as source:
                    if file_digest(source, 'sha256').hexdigest() != expected:
                        raise RuntimeError('A referenced journal photo failed integrity verification.')


def verify_production_files(database, uploads):
    mount = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
    if os.getenv('RAILWAY_ENVIRONMENT_ID') and mount != '/data':
        raise RuntimeError('Railway requires an attached volume mounted at /data.')
    for name in ('AGRISENSE_CHECKPOINT_PATH', 'AGRISENSE_PLANT_VERIFIER_WEIGHTS'):
        artifact = Path(os.environ[name])
        if mount and not artifact.resolve().is_relative_to(Path(mount).resolve()):
            raise RuntimeError('Railway model artifacts must be on the persistent volume.')
        hash_name = 'AGRISENSE_CHECKPOINT_SHA256' if name == 'AGRISENSE_CHECKPOINT_PATH' else 'AGRISENSE_PLANT_VERIFIER_SHA256'
        verify_artifact(artifact, os.getenv(hash_name, ''))
    if mount and any(not path.resolve().is_relative_to(Path(mount).resolve()) for path in (database, uploads)):
        raise RuntimeError('Railway database and uploads must be on the persistent volume.')
    verify_journal(database, uploads)
