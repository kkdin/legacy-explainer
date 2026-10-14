import json

import pytest

from legacy_explainer.parser import FunctionInfo
from legacy_explainer.summarizer import (
    MAX_SOURCE_CHARS,
    ModelUnavailable,
    Summarizer,
    clean,
)


def make_fn(source="def f(x):\n    return x + 1\n", qualname="f"):
    return FunctionInfo(name=qualname.split(".")[-1], qualname=qualname, lineno=1,
                        args=["x"], docstring=None, source=source)


class FakeModel:
    """Stands in for Ollama: records prompts, returns a canned answer."""

    def __init__(self, answer="Adds one to the input."):
        self.answer = answer
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer


def test_clean_collapses_whitespace():
    assert clean("  Line one.\n\n  Line   two.  \n") == "Line one. Line two."


def test_prompt_contains_code_path_and_rules():
    model = FakeModel()
    Summarizer(model, "m").summarize(make_fn(), "pkg/mod.py")
    prompt = model.prompts[0]
    assert "def f(x):" in prompt
    assert "pkg/mod.py" in prompt
    assert "at most 2 sentences" in prompt
    assert "No analogies" in prompt


def test_answer_is_cleaned():
    s = Summarizer(FakeModel("  Adds one.\n\n  Done. "), "m")
    assert s.summarize(make_fn(), "a.py") == "Adds one. Done."


def test_same_function_is_only_sent_once():
    model = FakeModel()
    s = Summarizer(model, "m")
    s.summarize(make_fn(), "a.py")
    s.summarize(make_fn(), "a.py")
    assert len(model.prompts) == 1
    assert (s.calls, s.cache_hits) == (1, 1)


def test_cache_survives_restart(tmp_path):
    cache = tmp_path / "cache.json"
    first = FakeModel("First answer.")
    Summarizer(first, "m", cache).summarize(make_fn(), "a.py")
    assert cache.exists()

    second = FakeModel("Should not be used.")
    result = Summarizer(second, "m", cache).summarize(make_fn(), "a.py")
    assert result == "First answer."
    assert second.prompts == []


def test_cache_is_saved_after_each_function(tmp_path):
    cache = tmp_path / "cache.json"
    s = Summarizer(FakeModel(), "m", cache)
    s.summarize(make_fn("def a(): pass"), "a.py")
    assert len(json.loads(cache.read_text())) == 1
    s.summarize(make_fn("def b(): pass"), "a.py")
    assert len(json.loads(cache.read_text())) == 2


def test_changing_the_model_or_the_code_invalidates_the_cache(tmp_path):
    cache = tmp_path / "cache.json"
    Summarizer(FakeModel("old"), "model-a", cache).summarize(make_fn(), "a.py")

    other_model = FakeModel("new")
    Summarizer(other_model, "model-b", cache).summarize(make_fn(), "a.py")
    assert len(other_model.prompts) == 1

    changed_code = FakeModel("changed")
    Summarizer(changed_code, "model-a", cache).summarize(make_fn("def f(x): return x"), "a.py")
    assert len(changed_code.prompts) == 1


def test_damaged_cache_file_is_ignored(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{ this is not json")
    s = Summarizer(FakeModel(), "m", cache)
    assert s.summarize(make_fn(), "a.py") == "Adds one to the input."


def test_failed_calls_are_not_cached(tmp_path):
    def broken(prompt):
        raise ModelUnavailable("Ollama is not running")

    cache = tmp_path / "cache.json"
    s = Summarizer(broken, "m", cache)
    with pytest.raises(ModelUnavailable):
        s.summarize(make_fn(), "a.py")
    assert not cache.exists() or json.loads(cache.read_text()) == {}


def test_very_long_source_is_truncated():
    model = FakeModel()
    long_src = "def big():\n" + "    x = 1\n" * 5000
    Summarizer(model, "m").summarize(make_fn(long_src, "big"), "a.py")
    assert len(model.prompts[0]) < MAX_SOURCE_CHARS + 1000
