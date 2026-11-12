"""Actual-run evidence. Unit fixtures are never integration evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from threading import Lock
from uuid import uuid4

from simulator.events import utc_now


_SECRET = re.compile(r"password|secret|token|authorization|private.?key|credential|originator", re.I)


def redact(value, secret_values=()):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _SECRET.search(str(k)) else redact(v, secret_values) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret_values) for v in value]
    if isinstance(value, str):
        if value in secret_values:
            return "[REDACTED]"
        try:
            nested = json.loads(value)
        except (ValueError, TypeError):
            nested = None
        if isinstance(nested, (dict, list)):
            return json.dumps(redact(nested, secret_values), separators=(",", ":"), allow_nan=False)
        for secret in secret_values:
            if len(secret) >= 4:
                value = value.replace(secret, "[REDACTED]")
    return value


def source_identity(root: Path) -> dict:
    manifest = {}
    for directory in ("backend", "onem2m", "simulator", "mec", "infra", "tests", "frontend", "fixtures"):
        for p in sorted((root / directory).rglob("*")):
            if p.is_file() and p.suffix in {".py", ".ini", ".txt", ".toml", ".yaml", ".yml", ".js", ".mjs", ".cjs", ".json", ".html", ".css"}:
                manifest[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ("compose.yaml", "pyproject.toml", "Makefile", ".python-version", ".node-version"):
        p = root / name
        if p.is_file():
            manifest[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    result = {"source_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(), "source_files": manifest}
    try:
        result["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True, timeout=3).strip()
        result["git_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, stderr=subprocess.DEVNULL, text=True, timeout=3).strip())
    except (OSError, subprocess.SubprocessError):
        result.update(git_commit=None, git_dirty=None)
    return result


class Evidence:
    def __init__(self, root: Path, secret_values=()):
        run = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ") + "-" + uuid4().hex[:8]
        self.path = root / run
        self.path.mkdir(parents=True, exist_ok=False)
        self.lock = Lock()
        self.secret_values = tuple(s for s in secret_values if s)

    def write(self, name: str, value: dict) -> None:
        target = self.path / name
        body = json.dumps(redact(value, self.secret_values), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        temporary = target.with_suffix(target.suffix + ".tmp")
        with self.lock:
            temporary.write_text(body, encoding="utf-8")
            temporary.replace(target)

    def append(self, name: str, value: dict) -> None:
        row = json.dumps(redact({"recorded_at_utc": utc_now(), **value}, self.secret_values), ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self.lock:
            with (self.path / name).open("a", encoding="utf-8") as stream:
                stream.write(row + "\n")

    def event(self, **value) -> None:
        self.append("events.jsonl", value)
