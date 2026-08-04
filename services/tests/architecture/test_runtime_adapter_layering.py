import ast
import importlib.util
from collections.abc import Iterable
from pathlib import Path

SERVICES_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = SERVICES_ROOT / "src"
ENGRAMMESH_ROOT = SOURCE_ROOT / "engrammesh"


def _module_name(source: Path, source_root: Path) -> str:
    return ".".join(source.relative_to(source_root).with_suffix("").parts)


def _import_targets(source: Path, source_root: Path) -> Iterable[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    package = _module_name(source, source_root)
    if source.name != "__init__.py":
        package = package.rpartition(".")[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_name = "." * node.level + (node.module or "")
                yield importlib.util.resolve_name(relative_name, package)
            elif node.module:
                yield node.module


def test_postgres_adapter_does_not_import_temporal_adapter() -> None:
    postgres_root = ENGRAMMESH_ROOT / "modules/runtime/adapters/postgres"
    for source in postgres_root.rglob("*.py"):
        for target in _import_targets(source, SOURCE_ROOT):
            assert "adapters.temporal" not in target, f"{source} imports {target}"
