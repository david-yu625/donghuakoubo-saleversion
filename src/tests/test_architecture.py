from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTest(unittest.TestCase):
    def test_numbered_steps_are_thin_entries_for_prepare_modules(self):
        implementations = {
            "01_generate_copywriting.py": "copywriting.py",
            "02_generate_voice_timeline.py": "voice_timeline.py",
            "03_generate_shot_timeline.py": "shot_timeline.py",
            "04_generate_storyboard_prompts.py": "storyboard_prompts.py",
            "05_generate_image_prompts.py": "image_prompts.py",
            "06_generate_images.py": "images.py",
        }
        for entry_name, implementation_name in implementations.items():
            entry = PACKAGE_ROOT / entry_name
            implementation = PACKAGE_ROOT / "prepare" / implementation_name
            self.assertTrue(entry.is_file())
            self.assertTrue(implementation.is_file())
            self.assertLess(len(entry.read_text(encoding="utf-8").splitlines()), 40)

    def test_visual_direction_has_no_geometry_fields(self):
        from ..visual_direction.models import VisualPlan

        forbidden = {"x", "y", "width", "height", "scale", "font_size"}
        self.assertTrue(forbidden.isdisjoint(VisualPlan.__dataclass_fields__))

    def test_upstream_layers_do_not_import_downstream_layers(self):
        forbidden = {
            "core": {"pipeline", "visual_direction", "layouts", "renderers", "application", "commands"},
            "prepare": {"pipeline", "visual_direction", "layouts", "renderers", "application", "commands"},
            "pipeline": {"visual_direction", "layouts", "renderers", "application", "commands"},
            "visual_direction": {"pipeline", "layouts", "renderers", "application", "commands"},
            "layouts": {"pipeline", "visual_direction", "renderers", "application", "commands"},
            "renderers": {"pipeline", "visual_direction", "layouts", "application", "commands"},
            "application": {"commands"},
        }
        for layer, blocked in forbidden.items():
            for path in (PACKAGE_ROOT / layer).glob("*.py"):
                imports = relative_import_targets(path)
                invalid = imports.intersection(blocked)
                self.assertFalse(invalid, f"{path.name} 不应导入下游层：{sorted(invalid)}")


def relative_import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.module:
            targets.add(node.module.split(".", 1)[0])
    return targets


if __name__ == "__main__":
    unittest.main()
