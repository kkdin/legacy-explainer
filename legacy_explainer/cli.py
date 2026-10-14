"""Command-line entry point: python -m legacy_explainer <folder> [-o report.md]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .graph import build_dependency_graph
from .parser import FunctionInfo, ModuleInfo, parse_project
from .report import render_report, summary_key
from .summarizer import ModelUnavailable, Summarizer, make_ollama_generate

DEFAULT_MODEL = "qwen2.5-coder:7b"


def _all_functions(modules: list[ModuleInfo]) -> list[tuple[str, FunctionInfo]]:
    """Every function and method in the project, as (file path, function) pairs."""
    pairs: list[tuple[str, FunctionInfo]] = []
    for mod in modules:
        pairs += [(mod.path, fn) for fn in mod.functions]
        for cls in mod.classes:
            pairs += [(mod.path, m) for m in cls.methods]
    return pairs


def build_summaries(
    modules: list[ModuleInfo],
    summarizer: Summarizer,
    limit: int | None = None,
) -> dict[str, str]:
    pairs = _all_functions(modules)
    if limit is not None:
        pairs = pairs[:limit]
    summaries: dict[str, str] = {}
    for i, (path, fn) in enumerate(pairs, start=1):
        print(f"  [{i}/{len(pairs)}] {path}::{fn.qualname}")
        summaries[summary_key(path, fn)] = summarizer.summarize(fn, path)
    return summaries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="legacy_explainer",
        description="Generate a Markdown overview of a Python codebase.",
    )
    ap.add_argument("path", type=Path, help="folder containing the Python code")
    ap.add_argument("-o", "--output", type=Path, default=Path("report.md"),
                    help="where to write the report (default: report.md)")
    ap.add_argument("--no-ai", action="store_true",
                    help="skip the AI summaries (structure and dependency map only)")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"local Ollama model to use (default: {DEFAULT_MODEL})")
    ap.add_argument("--limit", type=int, default=None,
                    help="only summarise the first N functions (handy for a quick test)")
    ap.add_argument("--cache", type=Path, default=Path(".legacy_explainer_cache.json"),
                    help="where summaries are remembered between runs")
    args = ap.parse_args(argv)

    if not args.path.is_dir():
        print(f"error: {args.path} is not a folder", file=sys.stderr)
        return 2

    modules, errors = parse_project(args.path)
    graph = build_dependency_graph(modules)
    n_edges = sum(len(t) for t in graph.values())
    print(f"Parsed {len(modules)} files, {n_edges} dependencies, {len(errors)} skipped.")
    for err in errors:
        print(f"  skipped {err.path}: {err.message}")

    summaries = None
    if not args.no_ai:
        summarizer = Summarizer(make_ollama_generate(args.model), args.model, args.cache)
        print(f"Summarising functions with local model {args.model} ...")
        try:
            summaries = build_summaries(modules, summarizer, args.limit)
        except ModelUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("Tip: run with --no-ai to produce the report without summaries.", file=sys.stderr)
            return 1
        print(f"Model asked {summarizer.calls} time(s), {summarizer.cache_hits} answer(s) reused from cache.")

    report = render_report(
        args.path.resolve().name, modules, errors, graph,
        summaries=summaries, model=args.model,
    )
    args.output.write_text(report, encoding="utf-8")
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
