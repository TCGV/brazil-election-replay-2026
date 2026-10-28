#!/usr/bin/env python3
"""Write or verify the H3 published-file SHA-256 inventory; stdlib only."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def inventory(folder, manifest):
    files = []
    for path in sorted(folder.rglob('*')):
        relative = path.relative_to(folder)
        if not path.is_file() or path.resolve()==manifest.resolve() or any(p in {'.work','__pycache__'} for p in relative.parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(dict(path=relative.as_posix(),size_bytes=path.stat().st_size,sha256=digest))
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write',action='store_true')
    mode.add_argument('--verify',action='store_true')
    parser.add_argument('--folder',type=Path,default=HERE)
    parser.add_argument('--manifest',type=Path,default=HERE/'evidence/artifact-manifest.json')
    args=parser.parse_args()
    files=inventory(args.folder.resolve(),args.manifest.resolve())
    if args.write:
        if args.manifest.exists():
            parser.error('Manifest already exists; choose a new path')
        args.manifest.parent.mkdir(parents=True,exist_ok=True)
        args.manifest.write_text(json.dumps(dict(schema_version=1,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            scope='All published H3 files except this inventory; local .work and Python caches excluded',
            nature='Integrity inventory, not an external authenticity signature',files=files),
            ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'Inventoried {len(files)} files')
    else:
        expected=json.loads(args.manifest.read_text())['files']
        if files!=expected:
            raise SystemExit('Artifact inventory mismatch: file set, size or SHA-256 differs')
        print(f'Verified {len(files)} files; zero mismatches')


if __name__=='__main__':
    main()
