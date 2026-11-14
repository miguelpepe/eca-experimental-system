import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docker.provision import APIError, configure_model, sync_rag, wait_for_file


class KnowledgeAPI:
    def __init__(self):
        self.uploads = {}
        self.members = set()
        self.removed = []
        self.upload_count = 0

    def call(self, method, path, **kwargs):
        if path.endswith('/files'):
            return {'items': [{'id': key, 'filename': self.uploads[key]} for key in self.members],
                    'total': len(self.members)}
        if path == '/api/v1/files/':
            self.upload_count += 1
            key = str(self.upload_count)
            self.uploads[key] = kwargs['files']['file'][0]
            return {'id': key}
        if path.endswith('/process/status'):
            return {'status': 'completed'}
        key = kwargs['json']['file_id']
        if path.endswith('/file/add'):
            self.members.add(key)
        elif path.endswith('/file/remove'):
            self.members.remove(key)
            self.removed.append(key)
        else:
            raise AssertionError(path)


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.api = KnowledgeAPI()
        self.state = {'knowledge_id': 'knowledge', 'files': {}}
        self.saved = None

    def sync(self):
        return sync_rag(self.api, self.root, self.state, self.save)

    def save(self):
        self.saved = copy.deepcopy(self.state)

    def test_unchanged_files_and_hidden_files_are_not_uploaded_again(self):
        (self.root / 'one.txt').write_text('first')
        (self.root / '.private').write_text('hidden')
        self.assertTrue(self.sync())
        self.assertTrue(self.sync())
        self.assertEqual(self.api.upload_count, 1)
        self.assertEqual(list(self.saved['files']), ['one.txt'])

    def test_changed_and_deleted_documents_are_removed_from_knowledge(self):
        one, two = self.root / 'one.txt', self.root / 'two.txt'
        one.write_text('first')
        two.write_text('second')
        self.sync()
        old_ids = set(self.api.members)
        one.write_text('changed')
        two.unlink()
        self.sync()
        self.assertEqual(len(self.api.members), 1)
        self.assertEqual(set(self.api.removed), old_ids)
        self.assertEqual(list(self.saved['files']), ['one.txt'])

    def test_duplicate_files_share_one_upload_and_survive_one_removal(self):
        (self.root / 'one.txt').write_text('same')
        (self.root / 'two.txt').write_text('same')
        self.sync()
        self.assertEqual(self.api.upload_count, 1)
        (self.root / 'one.txt').unlink()
        self.sync()
        self.assertEqual(len(self.api.members), 1)
        (self.root / 'two.txt').unlink()
        self.assertFalse(self.sync())
        self.assertEqual(self.api.members, set())

    def test_retry_recovers_upload_added_before_manifest_was_saved(self):
        (self.root / 'one.txt').write_text('first')
        self.sync()
        self.state['files'] = {}
        self.sync()
        self.assertEqual(self.api.upload_count, 1)

    def test_processing_failure_prevents_knowledge_add(self):
        with patch.object(self.api, 'call', return_value={'status': 'failed'}):
            with self.assertRaisesRegex(RuntimeError, 'could not be processed'):
                wait_for_file(self.api, 'failed')

    def test_existing_model_parameters_are_preserved(self):
        current = {'id': 'avatar', 'base_model_id': 'old', 'params': {'temperature': 0.7}, 'meta': {}}
        with patch.object(self.api, 'call', return_value=current) as call:
            configure_model(self.api, 'new')
            self.assertEqual(call.call_args.kwargs['json']['params'], {'temperature': 0.7})
            self.assertEqual(call.call_args.kwargs['json']['base_model_id'], 'new')

    def test_model_auth_failure_is_not_mistaken_for_absent_model(self):
        with patch.object(self.api, 'call', side_effect=APIError(403, '/model')):
            with self.assertRaises(APIError):
                configure_model(self.api, 'model')


if __name__ == '__main__':
    unittest.main()
