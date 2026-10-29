#!/usr/bin/env python3
"""Write or verify the H5 publication SHA-256 inventory; standard library only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def inventory(folder, manifest):
    result=[]
    for path in sorted(folder.rglob('*')):
        relative=path.relative_to(folder)
        if not path.is_file() or path.resolve()==manifest.resolve() or any(part in {'.work','__pycache__'} for part in relative.parts):
            continue
        result.append(dict(path=relative.as_posix(),size_bytes=path.stat().st_size,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return result


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
            parser.error('Inventory exists; preserve or explicitly review its replacement')
        args.manifest.parent.mkdir(parents=True,exist_ok=True)
        args.manifest.write_text(json.dumps(dict(schema_version=1,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            scope='All published H5 files except this inventory; .work and Python caches excluded',
            nature='Integrity inventory, not an external authenticity signature',files=files),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'Inventoried {len(files)} files')
    elif json.loads(args.manifest.read_text())['files']!=files:
        raise SystemExit('Artifact inventory mismatch: file set, size or SHA-256 differs')
    else:
        print(f'Verified {len(files)} files; zero mismatches')


if __name__=='__main__':
    main()
