import ast
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path

SERVICES_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = SERVICES_ROOT / "src"
KERNEL_ROOT = SOURCE_ROOT / "engrammesh" / "shared" / "kernel"
MODULES_ROOT = SOURCE_ROOT / "engrammesh" / "modules"


def _architecture_sources() -> list[Path]:
    sources = list(KERNEL_ROOT.rglob("*.py"))
    for domain_root in MODULES_ROOT.glob("*/domain"):
        sources.extend(domain_root.rglob("*.py"))
    return sorted(sources)


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


def _owning_module(source: Path, source_root: Path) -> str | None:
    relative_parts = source.relative_to(source_root).parts
    try:
        modules_index = relative_parts.index("modules")
    except ValueError:
        return None
    return relative_parts[modules_index + 1]


def _dependency_violations(
    sources: Iterable[Path],
    source_root: Path = SOURCE_ROOT,
) -> list[str]:
    violations: list[str] = []
    for source in sources:
        owning_module = _owning_module(source, source_root)
        for target in _import_targets(source, source_root):
            root_name = target.partition(".")[0]
            if root_name in sys.stdlib_module_names:
                continue
            if target == "engrammesh.shared.kernel" or target.startswith("engrammesh.shared.kernel."):
                continue
            if target.endswith(".public") and target.startswith("engrammesh.modules."):
                continue
            module_prefix = "engrammesh.modules."
            if owning_module is not None:
                own_domain = f"{module_prefix}{owning_module}.domain"
                if target == own_domain or target.startswith(f"{own_domain}."):
                    continue
            if target.startswith(module_prefix):
                violations.append(f"{source}: imports another module's internals: {target}")
            else:
                violations.append(f"{source}: imports non-standard-library dependency: {target}")
    return violations


def test_architecture_sources_obey_dependency_rules() -> None:
    assert _dependency_violations(_architecture_sources()) == []


def test_dependency_rules_reject_non_stdlib_import(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source = source_root / "engrammesh" / "modules" / "memory" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text("import pydantic\n", encoding="utf-8")
    violations = _dependency_violations([source], source_root)

    assert any("non-standard-library dependency: pydantic" in item for item in violations)


def test_dependency_rules_reject_another_modules_internals(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source = source_root / "engrammesh" / "modules" / "memory" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from engrammesh.modules.identity.domain import Tenant\n",
        encoding="utf-8",
    )
    violations = _dependency_violations([source], source_root)

    assert any("another module's internals" in item for item in violations)


def test_dependency_rules_allow_another_modules_public_api(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source = source_root / "engrammesh" / "modules" / "runtime" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from engrammesh.modules.memory.public import MemoryScope\n",
        encoding="utf-8",
    )

    assert _dependency_violations([source], source_root) == []


def test_dependency_rules_reject_owning_module_adapters(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source = source_root / "engrammesh" / "modules" / "memory" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from engrammesh.modules.memory.adapters import MemoryRepository\n",
        encoding="utf-8",
    )
    violations = _dependency_violations([source], source_root)

    assert any("engrammesh.modules.memory.adapters" in item for item in violations)
