"""Build and verify the self-contained paper evidence archive."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED
import json

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.with_suffix('.zip')
MANIFEST = ROOT / 'audit/package_manifest.json'
VERIFICATION = ROOT.with_suffix('.verification.json')


def digest(stream):
    h = sha256()
    while chunk := stream.read(1024 * 1024):
        h.update(chunk)
    return h.hexdigest()


files = sorted(p for p in ROOT.rglob('*') if p.is_file() and p != MANIFEST and '__pycache__' not in p.parts)
assert all(not p.is_symlink() for p in files)
entries = []
for p in files:
    with p.open('rb') as stream:
        entries.append({'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(stream)})
MANIFEST.write_text(json.dumps({'schema': 1, 'entries': entries}, ensure_ascii=False, separators=(',', ':')) + '\n')
files.append(MANIFEST)

with ZipFile(ARCHIVE, 'w', compression=ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
    for p in files:
        archive.write(p, f'{ROOT.name}/{p.relative_to(ROOT).as_posix()}')

expected = {f'{ROOT.name}/{item["path"]}': item['sha256'] for item in entries}
with MANIFEST.open('rb') as stream:
    expected[f'{ROOT.name}/{MANIFEST.relative_to(ROOT).as_posix()}'] = digest(stream)
with ZipFile(ARCHIVE) as archive:
    members = archive.namelist()
    assert len(members) == len(set(members)) == len(expected)
    assert set(members) == set(expected)
    for name in members:
        assert not name.startswith('/') and '..' not in Path(name).parts
        with archive.open(name) as stream:
            assert digest(stream) == expected[name], name

with ARCHIVE.open('rb') as stream:
    archive_sha256 = digest(stream)
result = {
    'archive': ARCHIVE.name,
    'archive_bytes': ARCHIVE.stat().st_size,
    'archive_sha256': archive_sha256,
    'members': len(members),
    'source_bytes': sum(item['bytes'] for item in entries),
    'member_sha256_and_crc': 'PASS',
    'path_and_duplicate_check': 'PASS',
    'self_contained_files': 'PASS',
}
VERIFICATION.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
