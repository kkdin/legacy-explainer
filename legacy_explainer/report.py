"""Turn the parsed project into a Markdown document."""
from __future__ import annotations

from .graph import reverse_graph, to_mermaid
from .parser import FunctionInfo, ModuleInfo, ParseError


def summary_key(module_path: str, fn: FunctionInfo) -> str:
    """Key used to look up a function's AI summary."""
    return f"{module_path}::{fn.qualname}"


def _signature(fn: FunctionInfo) -> str:
    return f"{fn.qualname}({', '.join(fn.args)})"


def _count_functions(modules: list[ModuleInfo]) -> int:
    return sum(len(m.functions) + sum(len(c.methods) for c in m.classes) for m in modules)


def _function_lines(
    fn: FunctionInfo,
    module_path: str,
    summaries: dict[str, str] | None,
    indent: str,
) -> list[str]:
    lines = [f"{indent}- `{_signature(fn)}` (line {fn.lineno})"]
    summary = (summaries or {}).get(summary_key(module_path, fn))
    if summary:
        pad = indent + "  "
        lines.append(f"{pad}- *AI summary (verify against the code):* {summary}")
        # Original code stays one click away, so a human can check the summary.
        lines.append(f"{pad}<details><summary>Show code</summary>")
        lines.append("")
        lines.append(f"{pad}```python")
        lines += [pad + line for line in fn.source.splitlines()]
        lines.append(f"{pad}```")
        lines.append("")
        lines.append(f"{pad}</details>")
    return lines


def render_report(
    project_name: str,
    modules: list[ModuleInfo],
    errors: list[ParseError],
    graph: dict[str, set[str]],
    summaries: dict[str, str] | None = None,
    model: str | None = None,
) -> str:
    rev = reverse_graph(graph)
    n_edges = sum(len(t) for t in graph.values())

    out: list[str] = [f"# {project_name}: code overview", ""]

    if summaries:
        out += [
            f"> Function summaries were written by a local AI model (`{model}`) running on this "
            "machine, so no code left it. They can contain mistakes: check each one against "
            "the code shown under it.",
            "",
        ]

    out += [
        "## At a glance",
        "",
        f"- Files parsed: {len(modules)}",
        f"- Functions and methods: {_count_functions(modules)}",
        f"- Classes: {sum(len(m.classes) for m in modules)}",
        f"- Dependencies between files: {n_edges}",
        f"- Files that could not be parsed: {len(errors)}",
        "",
    ]

    # Most depended-on files are the riskiest to change, so surface them first.
    popular = sorted(rev.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    popular = [(name, users) for name, users in popular if users][:3]
    if popular:
        out += ["Most depended-on files (change these with care):", ""]
        for name, users in popular:
            out.append(f"- `{name}`, used by {len(users)} other file(s)")
        out.append("")

    out += ["## Dependency map", "", "```mermaid", to_mermaid(graph), "```", ""]

    out += ["## Modules", ""]
    for mod in modules:
        out += [f"### `{mod.path}`", ""]
        if mod.docstring:
            out += [mod.docstring.strip().splitlines()[0], ""]
        uses = sorted(graph[mod.name])
        used_by = sorted(rev[mod.name])
        out.append("- Imports from this project: " + (", ".join(f"`{u}`" for u in uses) or "none"))
        out.append("- Imported by: " + (", ".join(f"`{u}`" for u in used_by) or "no one"))
        out.append("")
        for fn in mod.functions:
            out += _function_lines(fn, mod.path, summaries, indent="")
        for cls in mod.classes:
            out.append(f"- class `{cls.name}` (line {cls.lineno})")
            for m in cls.methods:
                out += _function_lines(m, mod.path, summaries, indent="    ")
        out.append("")

    if errors:
        out += ["## Files that could not be parsed", ""]
        out += ["These are probably Python 2 or contain invalid syntax:", ""]
        for err in errors:
            out.append(f"- `{err.path}`: {err.message}")
        out.append("")

    return "\n".join(out)
