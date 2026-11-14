import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import avatar_backend.config.conditions as conditions


class ProfileTests(unittest.TestCase):
    def test_deployment_profile_sets_persona_stt_and_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'persona.txt').write_text('Example persona', encoding='utf-8')
            (root / 'avatar.toml').write_text('[stt]\nmodel="small"\n[voice]\nfile="custom.wav"\ntext="Matching text"', encoding='utf-8')
            try:
                with patch.dict(os.environ, {'ECA_CONFIG_DIR': directory}):
                    importlib.reload(conditions)
                    config = conditions.build_condition(True)
                    self.assertTrue(config['system_prompt'].startswith('Example persona'))
                    self.assertEqual(config['stt']['model'], 'small')
                    self.assertEqual(Path(config['tts']['ref_audio']).as_posix(), 'voices/custom.wav')
                    self.assertEqual(config['tts']['ref_text'], 'Matching text')
            finally:
                importlib.reload(conditions)

    def test_voice_path_cannot_escape_voice_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'persona.txt').write_text('Example persona', encoding='utf-8')
            (root / 'avatar.toml').write_text('[voice]\nfile="../outside.wav"\ntext="Text"', encoding='utf-8')
            try:
                with patch.dict(os.environ, {'ECA_CONFIG_DIR': directory}):
                    with self.assertRaisesRegex(ValueError, 'inside voices'):
                        importlib.reload(conditions)
            finally:
                importlib.reload(conditions)


if __name__ == '__main__':
    unittest.main()
