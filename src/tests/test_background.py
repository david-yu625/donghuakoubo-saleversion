from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ..prepare import ensure_project_background


class BackgroundPreparationTest(unittest.TestCase):
    def test_background_is_project_local_visible_and_vertical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "output" / "topic"
            path = ensure_project_background(project, root)
            self.assertEqual(path.parent, project / "prepared_assets")
            with Image.open(path) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.mode, "RGB")
                red, green, blue = image.resize((1, 1)).getpixel((0, 0))
                self.assertGreater(red + green + blue, 90)
                self.assertGreater(green, red)

    def test_reference_background_is_copied_without_recoloring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "src" / "demos" / "background_1_1080x1920.png"
            reference.parent.mkdir(parents=True)
            Image.new("RGB", (1080, 1920), "#E8D3A8").save(reference)
            project = root / "output" / "topic"
            path = ensure_project_background(project, root)
            with Image.open(path) as image:
                self.assertEqual(image.getpixel((100, 100)), (232, 211, 168))

    def test_explicit_white_theme_background_is_fitted_and_kept_white(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "background_2.png"
            Image.new("RGB", (1984, 2272), "#FFFFFF").save(source)
            project = root / "output" / "topic"

            path = ensure_project_background(project, root, source=source)

            with Image.open(path) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getextrema(), ((255, 255), (255, 255), (255, 255)))

    def test_explicit_background_can_be_prepared_for_landscape_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "background_2.png"
            Image.new("RGB", (1080, 1920), "#FFFFFF").save(source)
            project = root / "output" / "topic"

            path = ensure_project_background(project, root, source=source, size=(1920, 1080))

            self.assertEqual(path.name, "background_1920x1080.png")
            with Image.open(path) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
