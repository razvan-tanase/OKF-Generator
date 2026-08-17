from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .normalization_errors import NormalizationError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise NormalizationError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NormalizationError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"{label} must be a JSON object")
    return value


def load_units(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        raise NormalizationError(f"Stage 04 units are missing: {path}")
    units: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise NormalizationError(
                        f"Stage 04 units line {line_number} is not newline-terminated"
                    )
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise NormalizationError(
                        f"Stage 04 units line {line_number} is invalid JSON"
                    ) from exc
                if not isinstance(value, dict):
                    raise NormalizationError(
                        f"Stage 04 units line {line_number} must be a JSON object"
                    )
                units.append(value)
    except OSError as exc:
        raise NormalizationError("Stage 04 units are unreadable") from exc
    return tuple(units)


def publish_immutable(final_dir: Path, manifest_text: str, units_text: str, *, profile: str) -> None:
    final_manifest = final_dir / "normalization.json"
    final_units = final_dir / "units.jsonl"
    if final_dir.exists():
        if not final_manifest.is_file() or not final_units.is_file():
            raise NormalizationError("existing normalization directory is incomplete")
        if (
            final_manifest.read_text(encoding="utf-8") != manifest_text
            or final_units.read_text(encoding="utf-8") != units_text
        ):
            raise NormalizationError(
                "existing normalization differs for the same upstream extraction/profile; "
                "bump the normalization profile instead of overwriting"
            )
        return

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{profile}.", suffix=".tmp", dir=final_dir.parent)
    )
    try:
        (temp_dir / "units.jsonl").write_text(units_text, encoding="utf-8")
        (temp_dir / "normalization.json").write_text(manifest_text, encoding="utf-8")
        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            if (
                final_dir.exists()
                and final_manifest.is_file()
                and final_units.is_file()
                and final_manifest.read_text(encoding="utf-8") == manifest_text
                and final_units.read_text(encoding="utf-8") == units_text
            ):
                return
            raise
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
