"""Railway/Docker entry point. PORT is parsed without shell interpolation."""
import os
from pathlib import Path


def prepare_volume_permissions(volume: Path):
    """Claim only application directories, refusing symlinks; never edit contents."""
    if volume.is_symlink() or not volume.is_dir():
        raise RuntimeError('Expected a real persistent volume directory.')
    paths = [volume]
    for name in ('journal', 'uploads', 'models', 'cache'):
        directory = volume/name
        if directory.is_symlink():
            raise RuntimeError('Symlinks are forbidden in the demo volume.')
        if not directory.exists():
            continue
        paths.append(directory)
        paths.extend(directory.rglob('*'))
    # Validate all entries before changing metadata. Nothing outside these trees
    # is traversed, and symlinks are never followed by chown.
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in paths):
        raise RuntimeError('Unsafe entry in the demo volume.')
    for path in paths:
        os.chown(path, 10001, 10001, follow_symlinks=False)
        path.chmod(0o700 if path.is_dir() else 0o600)


def server_options():
    port = int(os.getenv('PORT', '8000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    return dict(host='0.0.0.0', port=port, workers=1, access_log=False,
                proxy_headers=False, limit_concurrency=16)


def main():
    # Railway mounts new volumes as root. Claim the app files, then permanently
    # drop privileges before loading models or accepting HTTP traffic.
    if os.getenv('RAILWAY_VOLUME_MOUNT_PATH'):
        if os.environ['RAILWAY_VOLUME_MOUNT_PATH'] != '/data':
            raise RuntimeError('Mount the Railway volume at /data.')
        if os.geteuid() == 0:
            prepare_volume_permissions(Path('/data'))
            os.setgroups([])
            os.setgid(10001)
            os.setuid(10001)
    import uvicorn
    uvicorn.run('backend.app.main:app', **server_options())


if __name__ == '__main__':
    main()
