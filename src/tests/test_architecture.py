from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTest(unittest.TestCase):
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
