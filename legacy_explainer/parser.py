"""Parse Python source files into plain data structures using the built-in ast module.

No AI is involved here. The ast module reads the code the same way Python itself
does, so the structure we extract (functions, classes, imports) is always accurate.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Folders that never contain the project's own code.
SKIP_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env", "node_modules",
    "build", "dist", ".tox", ".pytest_cache", ".mypy_cache",
}


@dataclass
class FunctionInfo:
    name: str
    qualname: str          # "OrderMgr.add" for a method, "proc" for a plain function
    lineno: int
    args: list[str]
    docstring: str | None
    source: str            # exact source text, later sent to the local model


@dataclass
class ClassInfo:
    name: str
    lineno: int
    docstring: str | None
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str            # "os.path"; empty for "from . import x"
    names: list[str]       # names after "from ... import"; empty for a plain "import x"
    level: int = 0         # number of leading dots in a relative import


@dataclass
class ModuleInfo:
    path: str              # relative path with forward slashes, e.g. "billing/tax.py"
    name: str              # dotted module name, e.g. "billing.tax"
    docstring: str | None
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)

    @property
    def is_package(self) -> bool:
        return self.path.endswith("__init__.py")


@dataclass
class ParseError:
    path: str
    message: str


def module_name_from_path(rel: Path) -> str:
    """billing/tax.py -> 'billing.tax'; billing/__init__.py -> 'billing'."""
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__init__"


def _arg_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return names


def _function_info(node, source: str, prefix: str = "") -> FunctionInfo:
    return FunctionInfo(
        name=node.name,
        qualname=prefix + node.name,
        lineno=node.lineno,
        args=_arg_names(node),
        docstring=ast.get_docstring(node),
        source=ast.get_source_segment(source, node) or "",
    )


def parse_source(source: str, rel_path: Path) -> ModuleInfo:
    """Parse one file's text. Raises SyntaxError if the code is not valid Python 3."""
    tree = ast.parse(source)
    module = ModuleInfo(
        path=rel_path.as_posix(),
        name=module_name_from_path(rel_path),
        docstring=ast.get_docstring(tree),
    )

    # Imports: walk the whole tree, because old code often imports inside functions.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module.imports.append(ImportInfo(module=alias.name, names=[]))
        elif isinstance(node, ast.ImportFrom):
            module.imports.append(
                ImportInfo(
                    module=node.module or "",
                    names=[a.name for a in node.names],
                    level=node.level,
                )
            )

    # Functions and classes: only the top level of the file. Nested helpers are
    # part of their parent function's source, so they get explained with it.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module.functions.append(_function_info(node, source))
        elif isinstance(node, ast.ClassDef):
            cls = ClassInfo(
                name=node.name,
                lineno=node.lineno,
                docstring=ast.get_docstring(node),
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cls.methods.append(_function_info(item, source, prefix=node.name + "."))
            module.classes.append(cls)

    return module


def parse_project(root: Path) -> tuple[list[ModuleInfo], list[ParseError]]:
    """Parse every .py file under root. Files that cannot be parsed are reported, not fatal."""
    root = Path(root)
    modules: list[ModuleInfo] = []
    errors: list[ParseError] = []

    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            modules.append(parse_source(source, rel))
        except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
            # Legacy code is often Python 2 or has odd encodings; skip it, but say so.
            errors.append(ParseError(path=rel.as_posix(), message=f"{type(exc).__name__}: {exc}"))

    return modules, errors
