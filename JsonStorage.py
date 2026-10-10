"""Write JSON without truncating the last successfully saved file."""
import json
import os
from pathlib import Path
import tempfile
import uuid


def atomic_write_json(path, data):
    target = Path(path).resolve()
    temporary = None
    try:
        # Keep replacement on the same filesystem, and close before replacing
        # the destination (required on Windows).
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=4, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_write_bytes(path, payload):
    target = Path(path).resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f'.{target.name}.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def commit_json_updates(updates, *, expected, rename=None):
    """Apply a reference update with backups and rollback on a caught failure.

    Each replacement is atomic; the batch is not crash-atomic. A manifest and
    original bytes remain available if the process stops partway through.
    """
    payloads = {Path(path): json.dumps(data, indent=4, allow_nan=False).encode('utf-8')
                for path, data in updates.items()}
    expected = {Path(path): raw for path, raw in expected.items()}
    for path, raw in expected.items():
        if path.read_bytes() != raw:
            raise ValueError(f'{path.name} changed on disk. Reload before trying again.')
    if rename:
        source, destination = map(Path, rename)
        same_path = os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(destination))
        if destination.exists() and not same_path:
            raise FileExistsError(f'{destination.name} already exists.')
        payloads.setdefault(source, expected[source])
    if not payloads:
        return None
    backup = next(iter(payloads)).parent / '.map-backups' / uuid.uuid4().hex
    (backup / 'originals').mkdir(parents=True)
    for path in payloads:
        (backup / 'originals' / path.name).write_bytes(expected[path])
    atomic_write_json(backup / 'manifest.json', {
        'files': [str(path.resolve()) for path in payloads],
        'rename': [str(Path(path).resolve()) for path in rename] if rename else None,
    })
    written = []
    try:
        for path, payload in payloads.items():
            atomic_write_bytes(path, payload)
            written.append(path)
        if rename:
            os.replace(source, destination)
    except Exception as exc:
        failures = []
        for path in reversed(written):
            try:
                atomic_write_bytes(path, expected[path])
            except OSError as restore_error:
                failures.append(f'{path.name}: {restore_error}')
        detail = '\nRollback failures: ' + '; '.join(failures) if failures else '\nOriginal files restored.'
        raise OSError(f'Update failed: {exc}{detail}\nBackups: {backup}') from exc
    return backup
