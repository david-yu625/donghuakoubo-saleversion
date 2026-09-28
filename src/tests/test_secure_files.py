import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.security_guard.secure_files import (
    encrypt_file,
    is_encrypted,
    read_text,
    unlocked_files,
)


class SecureFilesTests(unittest.TestCase):
    def test_encrypts_and_restores_process_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storyboard_prompts.csv"
            path.write_text("prompt,secret\nhello,private\n", encoding="utf-8")
            with patch("src.security_guard.secure_files._read_or_create_install_id", return_value="test-install"):
                self.assertTrue(encrypt_file(path))
                self.assertTrue(is_encrypted(path))
                self.assertNotIn(b"private", path.read_bytes())
                self.assertEqual(read_text(path), "prompt,secret\nhello,private\n")
                self.assertTrue(is_encrypted(path))

    def test_context_encrypts_new_files_after_child_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("src.security_guard.secure_files._read_or_create_install_id", return_value="test-install"):
                with unlocked_files(root):
                    generated = root / "image_prompts_plus.csv"
                    generated.write_text("secret prompt", encoding="utf-8")
                    self.assertFalse(is_encrypted(generated))
                self.assertTrue(is_encrypted(generated))
                self.assertEqual(read_text(generated), "secret prompt")


if __name__ == "__main__":
    unittest.main()
