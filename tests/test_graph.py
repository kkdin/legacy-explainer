from pathlib import Path

from legacy_explainer.graph import build_dependency_graph, reverse_graph, to_mermaid
from legacy_explainer.parser import parse_project

SAMPLE = Path(__file__).resolve().parent.parent / "sample_legacy"


def make_project(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    modules, _ = parse_project(tmp_path)
    return build_dependency_graph(modules)


def test_plain_and_from_imports(tmp_path):
    g = make_project(tmp_path, {
        "a.py": "import b\nfrom c import thing\n",
        "b.py": "",
        "c.py": "thing = 1\n",
    })
    assert g["a"] == {"b", "c"}


def test_external_imports_are_ignored(tmp_path):
    g = make_project(tmp_path, {"a.py": "import os, json\nfrom pathlib import Path\n"})
    assert g["a"] == set()


def test_relative_imports(tmp_path):
    g = make_project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from . import b\nfrom .c import f\n",
        "pkg/b.py": "",
        "pkg/c.py": "def f(): pass\n",
    })
    assert g["pkg.a"] == {"pkg.b", "pkg.c"}


def test_parent_relative_import(tmp_path):
    g = make_project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/util.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/m.py": "from ..util import helper\n",
    })
    assert g["pkg.sub.m"] == {"pkg.util"}


def test_self_import_is_ignored(tmp_path):
    g = make_project(tmp_path, {"a.py": "import a\n"})
    assert g["a"] == set()


def test_reverse_graph():
    g = {"a": {"b"}, "b": set(), "c": {"b"}}
    assert reverse_graph(g) == {"a": set(), "b": {"a", "c"}, "c": set()}


def test_mermaid_output_is_deterministic():
    g = {"a": {"b"}, "b": set()}
    text = to_mermaid(g)
    assert text.splitlines() == [
        "graph LR",
        '    n0["a"]',
        '    n1["b"]',
        "    n0 --> n1",
    ]


def test_sample_project_edges():
    modules, _ = parse_project(SAMPLE)
    g = build_dependency_graph(modules)
    assert g == {
        "billing": {"billing.invoice"},
        "billing.invoice": {"billing.tax", "orders"},
        "billing.tax": set(),
        "db": set(),
        "orders": {"db", "utils"},
        "reports": {"orders", "utils"},
        "utils": set(),
    }
