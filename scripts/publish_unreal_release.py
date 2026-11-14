"""Upload the reviewed Unreal packages to a GitHub release."""
import argparse
import hashlib
import io
import json
import subprocess
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
REPO = 'miguelpepe/eca-experimental-system'
API = f'https://api.github.com/repos/{REPO}'


class Upload(io.BufferedReader):
    def __init__(self, path):
        super().__init__(io.FileIO(path, 'r'))
        self.name_label = path.name
        self.total = path.stat().st_size
        self.last = -1

    def read(self, size=-1):
        data = super().read(size)
        progress = int(10 * self.tell() / self.total) * 10 if self.total else 100
        if progress != self.last:
            self.last = progress
            print(f'{self.name_label}: {progress}%', flush=True)
        return data


def publish(make_public):
    manifest_path = ROOT / 'unreal/assets.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    version = manifest['version']
    folder = ROOT / '.eca/releases' / version
    files = [folder / item['name'] for item in manifest['packages']]
    files += [folder / 'assets.json', folder / 'SHA256SUMS.txt']
    for item in manifest['packages']:
        with (folder / item['name']).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256'], item['name']
    assert (folder / 'assets.json').read_bytes() == manifest_path.read_bytes()

    # use the existing Git credential without printing or persisting it
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            cwd=ROOT, capture_output=True, text=True, check=True)
    credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    session = requests.Session()
    session.headers.update({'Authorization': 'Bearer ' + credential['password'],
                            'Accept': 'application/vnd.github+json'})

    def call(method, url, **kwargs):
        response = session.request(method, url, timeout=(30, 1800), **kwargs)
        if not response.ok:
            raise RuntimeError(f'GitHub returned HTTP {response.status_code}: {response.json().get("message", "request failed")}')
        return response.json() if response.content else None

    response = session.get(API + '/releases/tags/' + version, timeout=30)
    if response.status_code == 404:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
        release = call('POST', API + '/releases', json={
            'tag_name': version, 'target_commitish': commit,
            'name': f'Unreal demo assets {version} (UE 5.6)', 'draft': True,
            'body': 'Public Unreal demo assets: ECA_Demo, shared MetaHuman assets, Keiji and Ada.\n\n'
                    'Clone the repository and run Setup.bat; choosing Frontend or Both downloads and verifies these packages automatically. '
                    'Git LFS is not required. Unreal Engine 5.6 and the NVIDIA plugins must be installed separately.\n\n'
                    'Private scenes, characters, prompts, voice recordings and RAG documents are excluded. '
                    'Assets retain their applicable Unreal/MetaHuman terms. See docs/unreal.md and THIRD_PARTY_NOTICES.md in the repository.',
        })
    else:
        response.raise_for_status()
        release = response.json()
    for path in files:
        existing = next((item for item in release['assets'] if item['name'] == path.name), None)
        with path.open('rb') as stream:
            checksum = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        if existing:
            if existing.get('digest') == checksum and existing['size'] == path.stat().st_size:
                print(f'Already uploaded: {path.name}', flush=True)
                continue
            if release['draft'] and existing.get('state') != 'uploaded':
                call('DELETE', existing['url'])
            else:
                raise RuntimeError(f'Refusing to overwrite an existing release asset: {path.name}')
        upload_url = release['upload_url'].split('{', 1)[0]
        with Upload(path) as stream:
            asset = call('POST', upload_url, params={'name': path.name}, data=stream,
                         headers={'Content-Type': 'application/zip' if path.suffix == '.zip' else 'application/octet-stream'})
        if asset.get('digest') != checksum or asset['size'] != path.stat().st_size:
            raise RuntimeError(f'Uploaded asset checksum mismatch: {path.name}')
    if make_public and release['draft']:
        release = call('PATCH', release['url'], json={'draft': False})
    print('Release: ' + release['html_url'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Publish after every upload has been verified')
    publish(parser.parse_args().publish)
