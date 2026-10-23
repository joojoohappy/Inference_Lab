import os

import pytest

from inference_lab.sourcemap import SourceAccessError, read_source, safe_path, tree
from inference_lab.tutor.redact import redact


@pytest.mark.parametrize("secret", [
    "hf_abcdefghijklmnopqrstuvwxyz123456",
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
    "ghp_abcdefghijklmnopqrstuvwxyz1234",
    "AKIAABCDEFGHIJKLMNOP",
])
def test_redact_known_token_shapes(secret):
    assert secret not in redact(f"my key is {secret} ok")


def test_redact_env_assignments_and_bearer():
    out = redact("HF_TOKEN=abc123secretvalue\nAuthorization: Bearer xyz.secret.token")
    assert "abc123secretvalue" not in out and "xyz.secret.token" not in out
    assert "HF_TOKEN=" in out  # the name stays so the learner knows what was removed


def test_redact_live_env_value(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "plainvalue-without-prefix")
    assert "plainvalue-without-prefix" not in redact("debug: plainvalue-without-prefix")


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.py", ".git/HEAD", ".env", ".env.local",
                                 "node_modules/x.js", "inference_lab/../../etc/passwd", "a\x00b.py"])
def test_source_paths_denied(bad):
    with pytest.raises(SourceAccessError):
        safe_path(bad)


def test_source_tree_has_no_secrets_or_vendored_code():
    files = tree()
    assert "inference_lab/api.py" in files
    assert not any(f.startswith((".git/", ".venv/", "frontend/")) or "/.env" in f or f.startswith(".env") for f in files)


def test_read_source_symbol_range():
    s = read_source("inference_lab/bench/metrics.py", "percentile")
    a, b = s["range"]
    lines = s["content"].splitlines()
    assert lines[a - 1].startswith("def percentile") and a < b
    with pytest.raises(SourceAccessError):
        read_source("inference_lab/bench/metrics.py", "does_not_exist")


def test_hf_token_never_written_to_records(lab, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_supersecretsupersecret123456")
    run = lab.submit("hardware.scan", {}, wait=True)
    from inference_lab.config import load_settings
    for p in load_settings().runs_dir.glob("*.json"):
        assert "hf_supersecret" not in p.read_text()
    assert "hf_supersecret" not in str(run.result)


def test_servers_bind_localhost_only():
    from inference_lab.config import load_settings
    assert load_settings().host in ("127.0.0.1", "localhost", "::1") or os.environ.get("INFERENCE_LAB_HOST")
