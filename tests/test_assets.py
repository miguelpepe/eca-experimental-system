import functools
import hashlib
import http.server
import json
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/assets.ps1'
ASSET = 'unreal/Content/ECA/Test.uasset'


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.downloads += 1
        super().do_GET()


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='eca-assets-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(self.root)))
        self.server.downloads = 0
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def manifest(self, files, version='test-v1', extras=None):
        archive = self.root / 'assets.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            for name, data in {**files, **(extras or {})}.items():
                bundle.writestr(name, data)
        value = {'schema': 1, 'version': version, 'packages': [{
            'name': 'assets.zip', 'size': archive.stat().st_size,
            'url': f'http://127.0.0.1:{self.server.server_port}/assets.zip',
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()],
        }]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path, value

    def install(self, manifest, success=True):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
                                 '-ProjectRoot', str(self.project), '-ManifestPath', str(manifest)], capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_fresh_install_and_cached_repair(self):
        path, _ = self.manifest({ASSET: b'public asset'})
        self.install(path)
        target = self.project / ASSET
        self.assertEqual(target.read_bytes(), b'public asset')
        self.assertEqual(self.server.downloads, 1)
        target.unlink()
        self.install(path)
        self.assertEqual(target.read_bytes(), b'public asset')
        self.assertEqual(self.server.downloads, 1)

    def test_private_files_and_modified_public_assets_survive_updates(self):
        private = self.project / 'unreal/Content/Main.umap'
        private.parent.mkdir(parents=True)
        private.write_bytes(b'private scene')
        path, _ = self.manifest({ASSET: b'original'})
        self.install(path)
        (self.project / ASSET).write_bytes(b'my local changes')
        added = 'unreal/Content/ECA/Next.umap'
        path, _ = self.manifest({ASSET: b'new default', added: b'new scene'}, version='test-v2')
        self.install(path)
        self.assertEqual((self.project / ASSET).read_bytes(), b'my local changes')
        self.assertEqual(private.read_bytes(), b'private scene')
        self.assertEqual((self.project / added).read_bytes(), b'new scene')

    def test_unmodified_managed_assets_are_updated(self):
        path, _ = self.manifest({ASSET: b'version one'})
        self.install(path)
        path, _ = self.manifest({ASSET: b'version two'}, version='test-v2')
        self.install(path)
        self.assertEqual((self.project / ASSET).read_bytes(), b'version two')

    def test_bad_archive_checksum_is_rejected(self):
        path, value = self.manifest({ASSET: b'asset'})
        value['packages'][0]['sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        self.install(path, success=False)
        self.assertFalse((self.project / ASSET).exists())

    def test_paths_outside_public_asset_folders_are_rejected_before_download(self):
        path, _ = self.manifest({'unreal/Content/ECA/../../outside.uasset': b'bad'})
        self.install(path, success=False)
        self.assertEqual(self.server.downloads, 0)

    def test_unlisted_zip_entries_are_rejected(self):
        path, _ = self.manifest({ASSET: b'asset'}, extras={'unreal/Content/Main.umap': b'private'})
        self.install(path, success=False)
        self.assertFalse((self.project / ASSET).exists())
        self.assertFalse((self.project / 'unreal/Content/Main.umap').exists())

    def test_file_checksum_is_checked_before_installation(self):
        path, value = self.manifest({ASSET: b'asset'})
        value['packages'][0]['files'][0]['sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        self.install(path, success=False)
        self.assertFalse((self.project / ASSET).exists())


if __name__ == '__main__':
    unittest.main()
