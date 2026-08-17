from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ..application.image_review import load_image_review_items
from ..prepare.image_prompts import PROMPT_FIELDS
from ..prepare.images import main as generate_images_main, select_rows


class ImageReviewTest(unittest.TestCase):
    def test_review_items_point_to_preserved_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_csv = root / "output" / "topic" / "image_prompts_plus.csv"
            prompt_csv.parent.mkdir(parents=True)
            asset = prompt_csv.parent / "generated_assets_plus" / "image.png"
            original = asset.parent / "originals" / asset.name
            original.parent.mkdir(parents=True)
            Image.new("RGB", (80, 60), "#FFFFFF").save(original)
            with prompt_csv.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=PROMPT_FIELDS)
                writer.writeheader()
                writer.writerow({
                    "element_id": "s1_img01",
                    "shot_id": "1",
                    "content": "机器人",
                    "width": "1024",
                    "height": "1536",
                    "asset_path": str(asset),
                    "prompt": "纯白背景机器人",
                })

            items = load_image_review_items(prompt_csv, root)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].element_id, "s1_img01")
        self.assertEqual(items[0].original_path, original)

    def test_selected_rows_preserve_csv_order(self):
        rows = [
            {"element_id": "first"},
            {"element_id": "second"},
            {"element_id": "third"},
        ]

        selected = select_rows(rows, ["third", "first"])

        self.assertEqual([row["element_id"] for row in selected], ["first", "third"])

    def test_unknown_selected_element_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不存在元素"):
            select_rows([{"element_id": "first"}], ["missing"])

    def test_selected_native_image_generation_writes_final_and_original_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_csv = root / "image_prompts_plus.csv"
            first = root / "generated_assets_plus" / "first.png"
            second = root / "generated_assets_plus" / "second.png"
            with prompt_csv.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=PROMPT_FIELDS)
                writer.writeheader()
                writer.writerows([
                    {
                        "element_id": "first",
                        "shot_id": "1",
                        "content": "下降箭头符号",
                        "width": "256",
                        "height": "384",
                        "asset_path": str(first),
                        "prompt": "下降箭头",
                    },
                    {
                        "element_id": "second",
                        "shot_id": "1",
                        "content": "上涨箭头警示符号",
                        "width": "256",
                        "height": "384",
                        "asset_path": str(second),
                        "prompt": "上涨箭头",
                    },
                ])
            arguments = [
                "images",
                str(prompt_csv),
                "--element-id",
                "second",
                "--overwrite",
            ]

            with patch("sys.argv", arguments):
                result = generate_images_main()

            self.assertEqual(result, 0)
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())
            self.assertTrue((second.parent / "originals" / second.name).exists())


if __name__ == "__main__":
    unittest.main()
