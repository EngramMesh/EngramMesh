"""Runtime adapters must not depend on bootstrap composition code."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

SERVICES_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = SERVICES_ROOT / "src"
ADAPTERS_ROOT = SOURCE_ROOT / "engrammesh" / "modules" / "runtime" / "adapters"


def _module_name(source: Path) -> str:
    return ".".join(source.relative_to(SOURCE_ROOT).with_suffix("").parts)


def _import_targets(source: Path) -> list[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    package = _module_name(source)
    if source.name != "__init__.py":
        package = package.rpartition(".")[0]

    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_name = "." * node.level + (node.module or "")
                targets.append(importlib.util.resolve_name(relative_name, package))
            elif node.module:
                targets.append(node.module)
    return targets


def test_runtime_adapters_do_not_import_bootstrap() -> None:
    violations: list[str] = []
    for source in sorted(ADAPTERS_ROOT.rglob("*.py")):
        for target in _import_targets(source):
            if target == "engrammesh.bootstrap" or target.startswith(
                "engrammesh.bootstrap."
            ):
                violations.append(f"{source}: imports bootstrap: {target}")
    assert violations == []
