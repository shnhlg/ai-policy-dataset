"""Create a reproducible-content manifest and validated migration ZIP; no uploads."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git','.venv','__pycache__','.test-work','tmp','staging'}

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def included(path):
    rel=path.relative_to(ROOT)
    return (path.is_file() and not set(rel.parts)&EXCLUDED_DIRS
            and path.name not in {'migration_manifest.json','raw-root.txt','.env','.env.local'}
            and path.suffix not in {'.pyc','.log','.zip'}
            and not ('audit' in path.name and path.name.endswith('cache.jsonl'))
            and not path.name.endswith(('.db-wal','.db-shm','.building.db')))

def row(path):
    return {'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest-only',action='store_true')
    args=parser.parse_args()
    output=args.output.resolve()
    if ROOT in output.parents:
        raise SystemExit('Place the ZIP outside the project directory.')
    sys.path.insert(0, str(ROOT / 'viewer'))
    from indexer import build_index, index_is_current
    if not index_is_current():
        build_index()
    snapshot_paths=[ROOT/'viewer/policy_search.db',ROOT/'data/processed/ai_policies_content_master.csv',
                    ROOT/'data/processed/policy_fulltexts.jsonl',ROOT/'viewer/title_translations.jsonl',
                    ROOT/'viewer/ai_review_results.jsonl',*sorted((ROOT/'viewer').glob('*.py'))]
    snapshot=[row(p) for p in snapshot_paths]
    (ROOT/'viewer/portable_index.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    known={r['path']:r for r in snapshot}
    files=sorted(p for p in ROOT.rglob('*') if included(p))
    # Scan source/configuration only. Report filenames, never matching credentials.
    key_pattern=re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for p in files:
        if p.suffix.lower() in {'.py','.js','.md','.txt','.ps1','.bat','.json'} and p.stat().st_size<5_000_000:
            text=p.read_text(encoding='utf-8-sig',errors='replace')
            if key_pattern.search(text):
                raise SystemExit('Possible secret; inspect privately: '+p.relative_to(ROOT).as_posix())
    manifest=[known.get(p.relative_to(ROOT).as_posix()) or row(p) for p in files]
    manifest_path=ROOT/'migration_manifest.json'
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'manifest_files':len(manifest),'uncompressed_bytes':sum(r['bytes'] for r in manifest)},ensure_ascii=False),flush=True)
    if args.manifest_only:
        return
    if output.exists():
        raise SystemExit('Output already exists; refusing to overwrite.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for i,p in enumerate(files+[manifest_path],1):
            z.write(p,'ai-policy-dataset/'+p.relative_to(ROOT).as_posix())
            if i%300==0:
                print(f'Packed {i}/{len(files)+1}',flush=True)
    with zipfile.ZipFile(output) as z:
        failure=z.testzip()
        assert failure is None,failure
    sha=digest(output)
    output.with_suffix('.sha256.txt').write_text(sha+'  '+output.name+'\n',encoding='utf-8')
    print(json.dumps({'zip':str(output),'bytes':output.stat().st_size,'sha256':sha,'crc':'ok'},ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
