from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from ..paths import default_draft_folder, resolve_draft_folder


class ProjectPathsTest(unittest.TestCase):
    def test_macos_draft_folder(self):
        home = Path("/Users/tester")
        self.assertEqual(
            default_draft_folder(platform="darwin", home=home),
            home / "Movies" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
        )

    def test_windows_draft_folder(self):
        local = r"C:\Users\tester\AppData\Local"
        self.assertEqual(
            default_draft_folder(platform="win32", home=Path("C:/Users/tester"), local_app_data=local),
            Path(local) / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
        )

    def test_windows_draft_folder_falls_back_to_home(self):
        home = Path("C:/Users/tester")
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                default_draft_folder(platform="win32", home=home, local_app_data=""),
                home / "AppData" / "Local" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
            )

    def test_macos_ignores_a_configured_windows_draft_folder(self):
        home = Path("/Users/tester")
        self.assertEqual(
            resolve_draft_folder(
                r"C:\Users\old\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft",
                platform="darwin",
                home=home,
            ),
            default_draft_folder(platform="darwin", home=home),
        )

    def test_windows_ignores_a_configured_macos_draft_folder(self):
        home = Path("C:/Users/tester")
        local = r"C:\Users\tester\AppData\Local"
        self.assertEqual(
            resolve_draft_folder(
                "/Users/old/Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
                platform="win32",
                home=home,
                local_app_data=local,
            ),
            default_draft_folder(platform="win32", home=home, local_app_data=local),
        )

    def test_compatible_custom_draft_folder_is_preserved(self):
        custom = Path("/Volumes/Work/JianyingDrafts")
        self.assertEqual(
            resolve_draft_folder(custom, platform="darwin", home=Path("/Users/tester")),
            custom,
        )


if __name__ == "__main__":
    unittest.main()
