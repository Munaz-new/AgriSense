"""Preview or delete one plant's journal rows after a verified private backup.

Stop the backend first. Dry-run is the default. Applying requires the exact plant
name and a new backup path outside the repository. Photos are retained on disk:
this is journal cleanup, not secure erasure. Restore only to isolated storage.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .backup import backup


def snapshot(db):
    return {table: db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
            for table in ('plants', 'observations')}


def delete_plant(database: Path, uploads: Path, plant_id: str, *, apply=False,
                 confirm_name: str | None = None, backup_path: Path | None = None):
    database = database.resolve()
    # URI mode refuses to create an empty DB when an operator mistypes a path.
    db = sqlite3.connect(database.as_uri() + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=10)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        if db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('Only schema 3 is supported. No migration is performed.')
        plant = db.execute('SELECT name FROM plants WHERE id=?', (plant_id,)).fetchone()
        if plant is None:
            raise ValueError('Plant not found; no records were changed.')
        count = db.execute('SELECT COUNT(*) FROM observations WHERE plant_id=?', (plant_id,)).fetchone()[0]
        result = {'plant_id': plant_id, 'name': plant[0], 'observations': count,
                  'applied': False, 'photos_retained': True}
        if not apply:
            return result
        if confirm_name != plant[0] or backup_path is None:
            raise ValueError('Applying requires the exact plant name and a new private backup path.')
        backup(database, uploads, backup_path)
        # Compare with the actual backed-up rows while holding the write lock.
        # A save between backup and deletion aborts rather than deleting unbacked data.
        with TemporaryDirectory(prefix='agrisense-delete-') as directory:
            restored = Path(directory) / 'snapshot.sqlite'
            with ZipFile(backup_path) as archive:
                restored.write_bytes(archive.read('journal.sqlite'))
            reference = sqlite3.connect(restored)
            try:
                before = snapshot(reference)
            finally:
                reference.close()
            with db:
                db.execute('BEGIN IMMEDIATE')
                if snapshot(db) != before:
                    raise ValueError('Journal changed after backup. Stop the backend and retry with a new backup path.')
                if db.execute('SELECT name FROM plants WHERE id=?', (plant_id,)).fetchone() != (confirm_name,):
                    raise ValueError('Plant name changed; deletion refused.')
                result['observations'] = db.execute('SELECT COUNT(*) FROM observations WHERE plant_id=?', (plant_id,)).fetchone()[0]
                db.execute('DELETE FROM observations WHERE plant_id=?', (plant_id,))
                db.execute('DELETE FROM plants WHERE id=?', (plant_id,))
                if db.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Foreign key check failed; deletion rolled back.')
        return {**result, 'applied': True, 'backup': str(backup_path)}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--uploads', type=Path, required=True)
    parser.add_argument('--plant-id', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-name')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    try:
        result = delete_plant(args.database, args.uploads, args.plant_id, apply=args.apply,
                              confirm_name=args.confirm_name, backup_path=args.backup)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Deletion refused: {error}\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
