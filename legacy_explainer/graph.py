"""Work out which files in the project import which, and draw it as a Mermaid diagram."""
from __future__ import annotations

from .parser import ImportInfo, ModuleInfo


def _resolve(imp: ImportInfo, mod: ModuleInfo, known: set[str]) -> set[str]:
    """Return the project modules that one import statement points to.

    Anything not in `known` (os, sqlite3, requests, ...) is external and ignored.
    """
    found: set[str] = set()

    if imp.level:  # relative import: "from . import x", "from ..pkg import y"
        pkg_parts = mod.name.split(".") if mod.is_package else mod.name.split(".")[:-1]
        drop = imp.level - 1
        if drop > len(pkg_parts):
            return found
        if drop:
            pkg_parts = pkg_parts[:-drop]
        base = ".".join(pkg_parts + ([imp.module] if imp.module else []))
    else:
        base = imp.module

    if not imp.names:
        # Plain "import a.b.c": use the longest prefix that is one of our modules.
        parts = base.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in known:
                found.add(prefix)
                break
        return found

    # "from base import n1, n2": each name may be a submodule or just an object in base.
    unresolved = False
    for name in imp.names:
        candidate = f"{base}.{name}" if base else name
        if candidate in known:
            found.add(candidate)
        else:
            unresolved = True
    if unresolved and base in known:
        found.add(base)
    return found


def build_dependency_graph(modules: list[ModuleInfo]) -> dict[str, set[str]]:
    """Map each module name to the set of project modules it imports."""
    known = {m.name for m in modules}
    graph: dict[str, set[str]] = {m.name: set() for m in modules}
    for mod in modules:
        for imp in mod.imports:
            graph[mod.name] |= _resolve(imp, mod, known)
        graph[mod.name].discard(mod.name)  # ignore self-imports
    return graph


def reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """Map each module to the modules that import it (who depends on me?)."""
    rev: dict[str, set[str]] = {name: set() for name in graph}
    for src, targets in graph.items():
        for dst in targets:
            rev[dst].add(src)
    return rev


def to_mermaid(graph: dict[str, set[str]]) -> str:
    """Render the graph as Mermaid text. GitHub draws it automatically in Markdown."""
    names = sorted(graph)
    ids = {name: f"n{i}" for i, name in enumerate(names)}
    lines = ["graph LR"]
    for name in names:
        lines.append(f'    {ids[name]}["{name}"]')
    for src in names:
        for dst in sorted(graph[src]):
            lines.append(f"    {ids[src]} --> {ids[dst]}")
    return "\n".join(lines)
