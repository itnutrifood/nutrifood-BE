import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = PROJECT_ROOT / "backend" / "apps"

SQL_PREFIXES = ("SELECT ", "INSERT INTO ", "UPDATE ", "DELETE FROM ")


def python_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def string_literals(tree: ast.Module) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_router_modules_are_http_adapters_only() -> None:
    router_files = sorted(APPS_ROOT.rglob("*routers.py"))
    assert router_files

    for path in router_files:
        tree = python_tree(path)
        imports = imported_modules(tree)
        assert "asyncpg" not in imports, path
        assert not any(module.startswith("pydantic") for module in imports), path
        assert not any(
            literal.lstrip().upper().startswith(SQL_PREFIXES) for literal in string_literals(tree)
        ), path


def test_service_modules_do_not_depend_on_fastapi_or_raw_sql() -> None:
    service_files = sorted(APPS_ROOT.rglob("*service.py"))
    assert service_files

    for path in service_files:
        tree = python_tree(path)
        imports = imported_modules(tree)
        assert not any(module.startswith("fastapi") for module in imports), path
        assert not any(
            literal.lstrip().upper().startswith(SQL_PREFIXES) for literal in string_literals(tree)
        ), path


def test_feature_modules_do_not_depend_on_admin_compatibility_modules() -> None:
    for path in sorted(APPS_ROOT.rglob("*.py")):
        if "admin" in path.relative_to(APPS_ROOT).parts:
            continue

        imports = imported_modules(python_tree(path))
        assert not any(module.startswith("backend.apps.admin") for module in imports), path
