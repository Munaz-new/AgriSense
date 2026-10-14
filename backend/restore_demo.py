"""Offline restore into an empty volume. Never overwrite an existing journal.

Run only with the API stopped, after explicit approval to upload private demo data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .app.deployment import verify_journal


def restore(archive_path: Path, volume: Path):
    volume = volume.resolve()
    if not volume.is_dir():
        raise ValueError('The volume must already exist.')
    journal, uploads = volume/'journal', volume/'uploads'
    if journal.exists() or uploads.exists() or journal.is_symlink() or uploads.is_symlink():
        raise FileExistsError('Refusing to overwrite existing journal/uploads; restore to an empty volume.')
    with TemporaryDirectory(prefix='.restore-', dir=volume) as directory:
        temporary = Path(directory)
        (temporary/'journal').mkdir(mode=0o700)
        (temporary/'uploads').mkdir(mode=0o700)
        with ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names) or sum(info.file_size for info in archive.infolist()) > 2 * 1024**3:
                raise ValueError('Duplicate entries or oversized backup.')
            manifest = json.loads(archive.read('manifest.json'))
            inventory = manifest['sha256']
            if (manifest.get('format') != 'agrisense-backup-v1' or
                    set(names) != set(inventory) | {'manifest.json'} or
                    not {'journal.sqlite', 'records.json'} <= set(inventory)):
                raise ValueError('Invalid backup manifest.')
            for name, expected in inventory.items():
                if name not in {'journal.sqlite', 'records.json'} and not re.fullmatch(
                        r'uploads/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)', name, re.IGNORECASE):
                    raise ValueError('Unsafe backup member.')
                data = archive.read(name)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError('Backup checksum mismatch.')
                if name == 'records.json':
                    continue
                target = temporary/'journal'/'agrisense.db' if name == 'journal.sqlite' else temporary/name
                with target.open('xb') as destination:
                    destination.write(data)
                target.chmod(0o600)
        verify_journal(temporary/'journal'/'agrisense.db', temporary/'uploads')
        # Run offline: if interrupted between these renames, inspect the volume;
        # a second invocation refuses to replace the partially restored content.
        os.rename(temporary/'journal', journal)
        os.rename(temporary/'uploads', uploads)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--volume', type=Path, required=True)
    args = parser.parse_args()
    restore(args.archive, args.volume)
    print('Existing demo journal and referenced photos restored; no source data changed.')
