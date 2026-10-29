#!/usr/bin/env python3
"""Create or verify the published H6 integrity inventory; no source authentication."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE / 'evidence/artifact-manifest.json'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def entries(root, inventory):
    result = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if (not path.is_file() or path == inventory or
                any(part in {'.work', '__pycache__'} for part in relative.parts) or
                path.suffix in {'.pyc', '.pyo'}):
            continue
        if path.is_symlink():
            raise ValueError(f'Published symbolic link is unsupported: {relative}')
        result.append(dict(path=relative.as_posix(), size_bytes=path.stat().st_size,
                           sha256=digest(path)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to(HERE):
        parser.error('Inventory must be inside the H6 folder')
    current = entries(HERE, destination)
    if args.verify:
        saved = json.loads(destination.read_text(encoding='utf-8'))
        expected = {entry['path']: entry for entry in saved['files']}
        observed = {entry['path']: entry for entry in current}
        differences = [name for name in sorted(expected.keys() | observed.keys())
                       if expected.get(name) != observed.get(name)]
        if differences:
            raise ValueError(f'Integrity inventory differs: {differences}')
        print(json.dumps(dict(status='passed', files=len(current), mismatches=0)))
        return
    if destination.exists():
        parser.error('Refusing to overwrite an existing inventory; verify it or use a new path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(schema_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(),
                   scope='All published H6 files except this inventory; .work and Python caches excluded',
                   nature='Integrity inventory, not an external authenticity signature', files=current)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='created', files=len(current))))


if __name__ == '__main__':
    main()
