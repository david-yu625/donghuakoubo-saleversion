from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ..prepare.images import generate_white_background


class ImageGenerationTest(unittest.TestCase):
    def test_background_is_generated_locally_as_uniform_white(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated_assets_plus" / "s1_bg01.png"

            generate_white_background(output, 1536, 864)

            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (1536, 864))
                self.assertEqual(image.getextrema(), ((255, 255), (255, 255), (255, 255)))


if __name__ == "__main__":
    unittest.main()
