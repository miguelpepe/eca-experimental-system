"""Build the public Unreal asset archives and their download manifest."""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'scene': 'unreal/Content/ECA/',
    'common': 'unreal/Content/MetaHumans/Common/',
    'keiji': 'unreal/Content/MetaHumans/Keiji/',
    'ada': 'unreal/Content/MetaHumans/Ada/',
}
EXCLUDED = {
    'unreal/Content/MetaHumans/Common/Face/BP_AI_VoiceManager.uasset',
    'unreal/Content/MetaHumans/Common/Face/audio2face.uasset',
    'unreal/Content/MetaHumans/Keiji/no_move.uasset',
}
EXTENSIONS = {'.uasset', '.umap', '.dna', '.ubulk', '.uexp'}
METADATA = {
    'unreal/Content/MetaHumans/Ada/SourceAssets/MigrationInfo.json',
    'unreal/Content/MetaHumans/Ada/VersionInfo.txt',
    'unreal/Content/MetaHumans/Common/VersionInfo.txt',
    'unreal/Content/MetaHumans/Keiji/VersionInfo.txt',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', version):
        raise ValueError('Invalid release version')
    manifest_path = ROOT / 'unreal/assets.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding='utf-8'))
        names = [item['path'] for bundle in previous['packages'] for item in bundle['files']]
    else:
        # first migration uses only the already reviewed Git asset inventory
        names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'unreal/Content'], cwd=ROOT).decode().split('\0')
        names = [name for name in names if name]
    if not names:
        raise ValueError('Public asset inventory is empty')
    output = ROOT / '.eca/releases' / version
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'schema': 1, 'version': version, 'packages': []}
    assigned = set()
    for group, prefix in GROUPS.items():
        selected = sorted(name for name in names if name.startswith(prefix))
        if not selected:
            continue
        archive = output / f'eca-unreal-{group}.zip'
        files = []
        print(f'Packing {archive.name}: {len(selected)} assets', flush=True)
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as bundle:
            for name in selected:
                source = ROOT / name
                if name in EXCLUDED or '..' in Path(name).parts or (source.suffix.lower() not in EXTENSIONS and name not in METADATA):
                    raise ValueError(f'Asset is not approved for publication: {name}')
                with source.open('rb') as stream:
                    if stream.read(64).startswith(b'version https://git-lfs.github.com/spec/'):
                        raise ValueError(f'Missing local asset bytes: {name}')
                files.append({'path': name, 'size': source.stat().st_size, 'sha256': digest(source)})
                bundle.write(source, name)
                assigned.add(name)
        if archive.stat().st_size >= 2 * 1024**3:
            raise ValueError(f'{archive.name} exceeds the GitHub release asset limit')
        manifest['packages'].append({
            'name': archive.name,
            'url': f'https://github.com/miguelpepe/eca-experimental-system/releases/download/{version}/{archive.name}',
            'size': archive.stat().st_size,
            'sha256': digest(archive),
            'files': files,
        })
        print(f'Ready: {archive.name}, {archive.stat().st_size / 1024**2:.1f} MiB', flush=True)
    if assigned != set(names):
        raise ValueError('Asset inventory contains paths outside the public package roots')
    text = json.dumps(manifest, indent=2) + '\n'
    manifest_path.write_text(text, encoding='utf-8')
    (output / 'assets.json').write_text(text, encoding='utf-8')
    checksums = ''.join(f"{item['sha256']}  {item['name']}\n" for item in manifest['packages'])
    (output / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    print(f'Public inventory: {len(assigned)} assets; manifest: {manifest_path}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    package(parser.parse_args().version)
