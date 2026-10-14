"""Ask a local language model (via Ollama) to explain each function in plain language.

Design choices:
- The model only writes the explanations. Structure (names, line numbers, imports)
  always comes from the ast parser, so it is never made up.
- Answers are cached on disk after every single function. If the run is interrupted,
  or you run the tool again, finished functions are not sent to the model a second time.
- The model is injected as a plain function (prompt -> text), so tests can use a fake one.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from .parser import FunctionInfo

# Bump this when the prompt changes, so old cached answers are not reused.
PROMPT_VERSION = "v1"

MAX_SOURCE_CHARS = 6000  # very long functions are cut off to keep the model fast

PROMPT_TEMPLATE = """You are documenting legacy Python code for a public-sector IT team.
Summarise the function below in at most 2 sentences. Describe only what the code does, in plain business language.

Rules:
- No analogies.
- Do not guess units, currencies or purposes that the code does not state. For example, say "increases the amount by 21%" rather than calling it a tax.
- If something is unclear, say "unclear".

File: {path}
Function: {name}

```python
{source}
```"""


class ModelUnavailable(RuntimeError):
    """Raised when the local model cannot be reached (Ollama not running, model missing)."""


def make_ollama_generate(model: str) -> Callable[[str], str]:
    """Return a function that sends a prompt to a local Ollama model and returns its answer."""

    def generate(prompt: str) -> str:
        try:
            import ollama
        except ImportError as exc:
            raise ModelUnavailable("The 'ollama' package is missing. Run: pip install ollama") from exc
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},  # 0 = same input gives (nearly) the same output
            )
        except Exception as exc:  # connection refused, unknown model, ...
            raise ModelUnavailable(
                f"Could not get an answer from Ollama model '{model}': {exc}\n"
                f"Is Ollama running, and did you run: ollama pull {model}"
            ) from exc
        return response["message"]["content"]

    return generate


def clean(text: str) -> str:
    """Collapse the answer into a single tidy paragraph."""
    return " ".join(text.split())


class Summarizer:
    def __init__(self, generate: Callable[[str], str], model: str, cache_path: Path | None = None):
        self.generate = generate
        self.model = model
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache: dict[str, str] = {}
        self.calls = 0       # how many times the model was actually asked
        self.cache_hits = 0
        if self.cache_path and self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.cache = {}  # a damaged cache is just ignored

    def _key(self, source: str) -> str:
        raw = f"{self.model}|{PROMPT_VERSION}|{source}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _save(self) -> None:
        if self.cache_path:
            self.cache_path.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")

    def summarize(self, fn: FunctionInfo, path: str) -> str:
        source = fn.source[:MAX_SOURCE_CHARS]
        key = self._key(source)
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]

        prompt = PROMPT_TEMPLATE.format(path=path, name=fn.qualname, source=source)
        answer = clean(self.generate(prompt))  # ModelUnavailable propagates to the caller
        self.calls += 1
        self.cache[key] = answer
        self._save()  # checkpoint after every function
        return answer
