from pathlib import Path

from legacy_explainer.parser import module_name_from_path, parse_project, parse_source

SAMPLE = Path(__file__).resolve().parent.parent / "sample_legacy"


def test_module_name_from_path():
    assert module_name_from_path(Path("billing/tax.py")) == "billing.tax"
    assert module_name_from_path(Path("billing/__init__.py")) == "billing"
    assert module_name_from_path(Path("utils.py")) == "utils"


def test_extracts_functions_and_args():
    src = "def f(a, b=1, *args, c, **kw):\n    '''Doc.'''\n    return a\n"
    mod = parse_source(src, Path("x.py"))
    assert [f.name for f in mod.functions] == ["f"]
    fn = mod.functions[0]
    assert fn.args == ["a", "b", "*args", "c", "**kw"]
    assert fn.docstring == "Doc."
    assert fn.source.startswith("def f(")


def test_extracts_classes_and_methods():
    src = "class A:\n    def m(self):\n        pass\n    def n(self):\n        pass\n"
    mod = parse_source(src, Path("x.py"))
    assert mod.classes[0].name == "A"
    assert [m.qualname for m in mod.classes[0].methods] == ["A.m", "A.n"]


def test_nested_functions_are_not_top_level():
    src = "def outer():\n    def inner():\n        pass\n    return inner\n"
    mod = parse_source(src, Path("x.py"))
    assert [f.name for f in mod.functions] == ["outer"]


def test_finds_imports_including_inside_functions():
    src = "import os\nfrom a.b import c\n\ndef f():\n    import json\n"
    mod = parse_source(src, Path("x.py"))
    modules = sorted(i.module for i in mod.imports)
    assert modules == ["a.b", "json", "os"]


def test_relative_import_level():
    mod = parse_source("from ..x import y\n", Path("pkg/sub/m.py"))
    assert mod.imports[0].level == 2
    assert mod.imports[0].module == "x"


def test_python2_file_is_reported_not_fatal(tmp_path):
    (tmp_path / "good.py").write_text("def ok():\n    return 1\n")
    (tmp_path / "bad.py").write_text('print "hello"\n')
    modules, errors = parse_project(tmp_path)
    assert [m.name for m in modules] == ["good"]
    assert [e.path for e in errors] == ["bad.py"]


def test_skips_virtualenv_and_cache_folders(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("x = 1\n")
    modules, _ = parse_project(tmp_path)
    assert [m.name for m in modules] == ["app"]


def test_sample_project_counts():
    modules, errors = parse_project(SAMPLE)
    assert sorted(m.name for m in modules) == [
        "billing", "billing.invoice", "billing.tax", "db", "orders", "reports", "utils",
    ]
    assert [e.path for e in errors] == ["old_export.py"]
