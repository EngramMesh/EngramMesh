import ast
import importlib.util
from collections.abc import Iterable
from pathlib import Path

SERVICES_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = SERVICES_ROOT / "src"
ENGRAMMESH_ROOT = SOURCE_ROOT / "engrammesh"
TEMPORAL_MODULE = "temporalio"
ALLOWED_PREFIXES = (
    "engrammesh/modules/runtime/adapters/temporal/",
    "engrammesh/bootstrap/worker.py",
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


def _is_allowed_temporal_import(relative_path: str) -> bool:
    return any(
        relative_path == prefix or relative_path.startswith(prefix)
        for prefix in ALLOWED_PREFIXES
    )


def _temporal_import_violations() -> list[str]:
    violations: list[str] = []
    for source in sorted(ENGRAMMESH_ROOT.rglob("*.py")):
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if _is_allowed_temporal_import(relative):
            continue
        for target in _import_targets(source, SOURCE_ROOT):
            if target == TEMPORAL_MODULE or target.startswith(f"{TEMPORAL_MODULE}."):
                violations.append(
                    f"{source}: imports temporalio outside allowed locations: {target}"
                )
    return violations


def test_only_temporal_adapter_and_worker_import_temporalio() -> None:
    assert _temporal_import_violations() == []
