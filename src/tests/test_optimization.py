from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ..core.text_measure import resolve_font
from ..layouts.templates import asset_geometry
from ..pipeline.project_reader import read_subtitles


class OptimizationRegressionTest(unittest.TestCase):
    def test_font_resolution_reuses_same_font_instance(self):
        first = resolve_font(None, 28)
        second = resolve_font(None, 28)
        self.assertIs(first, second)

    def test_asset_geometry_refreshes_after_asset_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.png"
            Image.new("RGBA", (10, 20), (255, 0, 0, 255)).save(path)
            self.assertEqual((asset_geometry(str(path)).source_width, asset_geometry(str(path)).source_height), (10, 20))

            Image.new("RGBA", (30, 40), (255, 0, 0, 255)).save(path)
            geometry = asset_geometry(str(path))
            self.assertEqual((geometry.source_width, geometry.source_height), (30, 40))

    def test_subtitles_support_quoted_and_legacy_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeline.csv"
            path.write_text(
                "index,text,time\n"
                "1,\"包含,逗号\",\"[0.0,1.25,1.25]\"\n"
                "2,旧格式,[1.25,2.5,1.25]\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_subtitles(path),
                [("包含,逗号", 0, 1250), ("旧格式", 1250, 2500)],
            )


if __name__ == "__main__":
    unittest.main()
