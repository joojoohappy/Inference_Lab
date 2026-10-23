# Source Code Explorer

Goal: every step can answer "what code just ran?" with the real file and line range.

## How a step finds its code

* Each allowlisted action declares `sources: [(file, symbol)]` and `tests: [...]` in `actions.py`.
* Each mission step can add its own `sources`. Both are covered by tests that resolve every file and symbol.
* `View source` opens `/api/source?path=…&symbol=…`; `sourcemap.symbol_range` uses Python's `ast` to find the
  1-based inclusive line range of a top-level or class-level `def`/`class`/assignment. The range is highlighted
  and scrolled into view.

## Labels

| Label | Meaning |
|---|---|
| Executed source | The real repository file, read from disk at request time |
| Illustrative | A simplified snippet inside an explanation (always labelled where it appears) |
| Suggested change | A change the tutor proposes; never applied automatically |

## Explanations

Four levels — Simple, Logic, Design, Trade-offs. Sources, in order: curated notes in `tutor/knowledge/code.yaml`
(`source: curated`), the symbol's docstring (`source: source`), an optional AI provider (`source: ai`, labelled
"check it"). Questions about a selected line send only that file's region and the question, after redaction.

## Safety

* Read-only. There is no write endpoint.
* Repository-relative paths only; `..`, absolute paths, NUL bytes, `.git`, `.venv`, `node_modules`, `dist`,
  `__pycache__` and `.env*` are refused; an extension allowlist applies; files over the size cap are refused.
* Highlighting: highlight.js output (which escapes its input) or an explicit HTML escape is the only content
  rendered as HTML, so repository text cannot inject markup.
