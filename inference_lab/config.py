"""Runtime configuration. Everything is local-first and overridable by env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    hf_endpoint: str
    max_download_bytes: int

    @property
    def experiments_dir(self) -> Path:
        return self.data_dir / "experiments"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def ensure(self) -> "Settings":
        for d in (self.data_dir, self.experiments_dir, self.runs_dir, self.models_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("INFERENCE_LAB_HOME", Path.home() / ".inference-lab")).expanduser()
    return Settings(
        data_dir=data_dir,
        # Localhost-only by default. Binding elsewhere is an explicit operator choice.
        host=os.environ.get("INFERENCE_LAB_HOST", "127.0.0.1"),
        port=int(os.environ.get("INFERENCE_LAB_PORT", "8765")),
        hf_endpoint=os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/"),
        # Downloads above this size are refused even with approval (default 2 GiB).
        max_download_bytes=int(os.environ.get("INFERENCE_LAB_MAX_DOWNLOAD_BYTES", str(2 * 1024**3))),
    )
