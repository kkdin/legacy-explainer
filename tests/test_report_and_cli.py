from pathlib import Path

from legacy_explainer import cli
from legacy_explainer.graph import build_dependency_graph
from legacy_explainer.parser import parse_project
from legacy_explainer.report import render_report, summary_key
from legacy_explainer.summarizer import ModelUnavailable, Summarizer

SAMPLE = Path(__file__).resolve().parent.parent / "sample_legacy"


def parsed():
    modules, errors = parse_project(SAMPLE)
    return modules, errors, build_dependency_graph(modules)


def fake_generate(prompt):
    return "Fake summary."


def test_report_without_summaries_has_no_ai_labels():
    modules, errors, graph = parsed()
    text = render_report("sample", modules, errors, graph)
    assert "AI summary" not in text
    assert "<details>" not in text


def test_report_with_summaries_labels_them_and_shows_code():
    modules, errors, graph = parsed()
    utils = next(m for m in modules if m.name == "utils")
    proc = next(f for f in utils.functions if f.name == "proc")
    summaries = {summary_key("utils.py", proc): "Filters and sorts records."}

    text = render_report("sample", modules, errors, graph, summaries=summaries, model="test-model")

    assert "AI summary (verify against the code):* Filters and sorts records." in text
    assert "<details><summary>Show code</summary>" in text
    assert "def proc(d, t):" in text            # original code is shown next to the summary
    assert "`test-model`" in text               # the notice names the model
    assert "can contain mistakes" in text


def test_build_summaries_covers_functions_and_methods():
    modules, _, _ = parsed()
    result = cli.build_summaries(modules, Summarizer(fake_generate, "m"))
    # 11 functions and methods in the sample project
    assert len(result) == 11
    assert "orders.py::OrderMgr.load" in result


def test_build_summaries_respects_limit():
    modules, _, _ = parsed()
    result = cli.build_summaries(modules, Summarizer(fake_generate, "m"), limit=3)
    assert len(result) == 3


def test_cli_no_ai_writes_report(tmp_path):
    out = tmp_path / "r.md"
    code = cli.main([str(SAMPLE), "-o", str(out), "--no-ai"])
    assert code == 0
    assert "## Dependency map" in out.read_text(encoding="utf-8")


def test_cli_with_fake_model_writes_summaries_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "make_ollama_generate", lambda model: fake_generate)
    out, cache = tmp_path / "r.md", tmp_path / "c.json"
    code = cli.main([str(SAMPLE), "-o", str(out), "--cache", str(cache)])
    assert code == 0
    assert "Fake summary." in out.read_text(encoding="utf-8")
    assert cache.exists()


def test_cli_reports_unavailable_model_cleanly(tmp_path, monkeypatch, capsys):
    def broken(prompt):
        raise ModelUnavailable("Ollama is not running")

    monkeypatch.setattr(cli, "make_ollama_generate", lambda model: broken)
    out = tmp_path / "r.md"
    code = cli.main([str(SAMPLE), "-o", str(out), "--cache", str(tmp_path / "c.json")])
    assert code == 1
    assert "Ollama is not running" in capsys.readouterr().err
    assert not out.exists()


def test_cli_rejects_missing_folder(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope")]) == 2
    assert "not a folder" in capsys.readouterr().err
