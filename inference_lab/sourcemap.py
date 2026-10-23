"""Read-only source access for the Code Explorer.

Only files inside the repository, with an allowlisted extension, outside hidden/vendored
directories, can be read. Line ranges for a symbol are computed from the current file with
`ast`, so they always match the code that actually runs (no hand-maintained line numbers).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

ALLOWED_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".ts", ".tsx", ".css", ".sh"}
ALLOWED_NAMES = {"Dockerfile", "docker-compose.yml", "Makefile"}
DENIED_PARTS = {".git", ".venv", "node_modules", "__pycache__", "dist", ".env"}
MAX_BYTES = 400_000


class SourceAccessError(ValueError):
    pass


def safe_path(rel: str) -> Path:
    if not rel or rel.startswith(("/", "\\")) or "\x00" in rel:
        raise SourceAccessError("path must be repository-relative")
    p = (REPO_ROOT / rel).resolve()
    try:
        rel_parts = p.relative_to(REPO_ROOT).parts
    except ValueError as e:
        raise SourceAccessError("path escapes the repository") from e
    if any(part in DENIED_PARTS or part.startswith(".env") for part in rel_parts):
        raise SourceAccessError("path is not readable from the Code Explorer")
    if p.suffix not in ALLOWED_SUFFIXES and p.name not in ALLOWED_NAMES:
        raise SourceAccessError("file type not allowed")
    if not p.is_file():
        raise SourceAccessError("file not found")
    return p


def symbol_range(path: Path, symbol: str) -> tuple[int, int] | None:
    """1-based inclusive line range of a top-level or class-level def/class/assignment."""
    if path.suffix != ".py":
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = getattr(node, "name", None)
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            name = names[0] if names else None
        if name == symbol and hasattr(node, "lineno"):
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            return start, node.end_lineno or node.lineno
    return None


def read_source(rel: str, symbol: str | None = None) -> dict[str, Any]:
    p = safe_path(rel)
    if p.stat().st_size > MAX_BYTES:
        raise SourceAccessError("file too large to display")
    text = p.read_text(encoding="utf-8")
    rng = symbol_range(p, symbol) if symbol else None
    if symbol and rng is None and p.suffix == ".py":
        raise SourceAccessError(f"symbol {symbol!r} not found in {rel}")
    lang = {".py": "python", ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".md": "markdown", ".toml": "ini",
            ".ts": "typescript", ".tsx": "typescript", ".sh": "bash", ".css": "css"}.get(p.suffix, "plaintext")
    return {"path": rel, "language": lang, "content": text, "lines": text.count("\n") + 1,
            "symbol": symbol, "range": list(rng) if rng else None, "kind": "executed_source"}


def tree() -> list[str]:
    out = []
    for p in sorted(REPO_ROOT.rglob("*")):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if not p.is_file() or rel.startswith("frontend/"):
            continue
        try:
            safe_path(rel)
        except SourceAccessError:
            continue
        out.append(rel)
    return out
