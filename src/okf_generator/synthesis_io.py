from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .synthesis_errors import SynthesisError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SynthesisError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SynthesisError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise SynthesisError(f"{label} must be a JSON object")
    return value


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SynthesisError(f"{label} is missing: {path}")
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise SynthesisError(f"{label} line {line_no} is not newline-terminated")
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SynthesisError(f"{label} line {line_no} is invalid JSON") from exc
                if not isinstance(value, dict):
                    raise SynthesisError(f"{label} line {line_no} must be a JSON object")
                out.append(value)
    except OSError as exc:
        raise SynthesisError(f"{label} is unreadable") from exc
    return out


def publish_run(final_dir: Path, files: dict[str, str]) -> None:
    if final_dir.exists():
        for name, expected in files.items():
            path = final_dir / name
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                raise SynthesisError("existing synthesis run is incomplete or has been modified")
        return
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".synthesis.", suffix=".tmp", dir=final_dir.parent))
    try:
        for name, content in files.items():
            (temp_dir / name).write_text(content, encoding="utf-8")
        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            if final_dir.exists() and all((final_dir / n).is_file() and (final_dir / n).read_text(encoding="utf-8") == c for n, c in files.items()):
                return
            raise
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
