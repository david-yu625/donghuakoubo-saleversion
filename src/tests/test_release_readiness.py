from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReleaseReadinessTest(unittest.TestCase):
    def test_launchers_use_package_entrypoint(self):
        macos = (PROJECT_ROOT / "start_pipeline_app.command").read_text(encoding="utf-8")
        windows = (PROJECT_ROOT / "start_pipeline_app.bat").read_text(encoding="utf-8")
        self.assertIn("python3 -m src", macos)
        self.assertIn("-m src", windows)
        self.assertNotIn("08_pipeline_app", macos + windows)

    def test_secrets_and_generated_outputs_are_ignored(self):
        ignored = set((PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
        self.assertIn(".env", ignored)
        self.assertIn("output/", ignored)
        self.assertIn("__pycache__/", ignored)

if __name__ == "__main__":
    unittest.main()
