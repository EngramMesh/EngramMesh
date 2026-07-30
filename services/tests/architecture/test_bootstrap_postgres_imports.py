import ast
import importlib.util
from collections.abc import Iterable
from pathlib import Path

SERVICES_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = SERVICES_ROOT / "src"
ENGRAMMESH_ROOT = SOURCE_ROOT / "engrammesh"
POSTGRES_ADAPTER_PREFIX = "engrammesh.modules.memory.adapters.postgres"
ALLOWED_PREFIXES = (
    "engrammesh/bootstrap/",
    "engrammesh/modules/memory/adapters/postgres/",
)


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


def _postgres_import_violations() -> list[str]:
    violations: list[str] = []
    for source in sorted(ENGRAMMESH_ROOT.rglob("*.py")):
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if any(relative.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        for target in _import_targets(source, SOURCE_ROOT):
            if target == POSTGRES_ADAPTER_PREFIX or target.startswith(
                f"{POSTGRES_ADAPTER_PREFIX}."
            ):
                violations.append(
                    f"{source}: imports postgres adapter outside bootstrap: {target}"
                )
    return violations


def test_only_bootstrap_and_postgres_adapter_import_postgres_module() -> None:
    assert _postgres_import_violations() == []
