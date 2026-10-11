"""Create a private, consistent local journal export; never modifies source records.

Usage: python -m backend.backup --database PATH --uploads PATH --output /outside/repo/backup.zip
The archive contains SQLite, JSON, referenced photos and a SHA-256 inventory.
It includes photos and notes and is not encrypted. Stop the server before restoring.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def backup(database: Path, uploads: Path, output: Path):
    database, uploads, output = database.resolve(), uploads.resolve(), output.absolute()
    if output.resolve().is_relative_to(ROOT) or output.resolve().is_relative_to(uploads):
        raise ValueError('Keep private backups outside the repository and upload directory.')
    if output.exists():
        raise FileExistsError('Backup destination already exists; choose a new filename.')
    if not database.is_file() or not uploads.is_dir():
        raise ValueError('An existing journal database and upload directory are required.')
    # Read transaction and SQLite backup API preserve one committed snapshot.
    source = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10)
    source.row_factory = sqlite3.Row
    created = False
    try:
        source.execute('BEGIN')
        if source.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('Only journal schema 3 is supported; no migration is performed by backup.')
        plants = [dict(r) for r in source.execute('SELECT * FROM plants ORDER BY id')]
        observations = [dict(r) for r in source.execute('SELECT * FROM observations ORDER BY id')]
        with TemporaryDirectory(prefix='agrisense-backup-', dir=output.parent) as directory:
            temp = Path(directory)
            db_copy = temp/'journal.sqlite'
            with sqlite3.connect(db_copy) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or target.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Database integrity check failed; backup refused.')
            # The copied DB and rows now hold the snapshot. Existing upload files
            # are immutable in this API; release the DB read lock before compression.
            source.rollback()
            bundle = temp/'bundle.zip'
            inventory = {}
            def add(archive, name, data):
                archive.writestr(name, data)
                inventory[name] = hashlib.sha256(data).hexdigest()
            with ZipFile(bundle, 'w', compression=ZIP_DEFLATED) as archive:
                add(archive, 'journal.sqlite', db_copy.read_bytes())
                for row in observations:
                    if not re.fullmatch(r'/uploads/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)', row['image_path'], re.IGNORECASE):
                        raise ValueError('An observation has an unsafe image path; backup refused.')
                    file = uploads/row['image_path'].split('/')[-1]
                    if file.is_symlink() or not file.is_file():
                        raise ValueError('A referenced image is missing or is a symbolic link; backup refused.')
                    data = file.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    if row.get('image_sha256') and digest != row['image_sha256']:
                        raise ValueError('A referenced image hash does not match its record; backup refused.')
                    name = 'uploads/' + file.name
                    if name not in inventory:
                        add(archive, name, data)
                export = {'schema_version':3, 'plants':plants,
                          'observations':[{k:v for k,v in r.items() if k != 'request_fingerprint'} for r in observations]}
                add(archive, 'records.json', json.dumps(export, ensure_ascii=False, indent=2).encode())
                archive.writestr('manifest.json', json.dumps({'format':'agrisense-backup-v1', 'sha256':inventory}, indent=2))
            # Exclusive destination creation prevents overwriting another backup in a race.
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as destination, bundle.open('rb') as origin:
                import shutil
                shutil.copyfileobj(origin, destination)
                destination.flush()
                os.fsync(destination.fileno())
        return {'plants':len(plants), 'observations':len(observations), 'files':len(inventory)}
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    finally:
        source.rollback()
        source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--uploads', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(backup(args.database, args.uploads, args.output)))
