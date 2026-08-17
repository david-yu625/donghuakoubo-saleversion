from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ..prepare import generate_native_graphic, native_graphic_kind


class NativeGraphicsTest(unittest.TestCase):
    def test_text_sensitive_assets_use_native_graphics(self):
        self.assertEqual(native_graphic_kind("价格标签牌 一百两"), "blank_tag")
        self.assertEqual(native_graphic_kind("下降的价格曲线"), "down_chart")
        self.assertIsNone(native_graphic_kind("唐僧形象持禅杖"))

    def test_native_graphic_is_transparent_rgba(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "chart.png"
            self.assertTrue(generate_native_graphic("上涨的价格曲线", output, 1024, 1536))
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (1024, 1536))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertGreater(image.getchannel("A").getbbox()[2], 500)


if __name__ == "__main__":
    unittest.main()
