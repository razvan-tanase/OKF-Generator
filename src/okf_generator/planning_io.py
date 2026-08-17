from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from pathlib import Path
from typing import Any, Mapping
from .planning_errors import PlanningError

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PlanningError(f'{label} is missing: {path}')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanningError(f'{label} is unreadable') from exc
    if not isinstance(value, dict):
        raise PlanningError(f'{label} must be a JSON object')
    return value

def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise PlanningError(f'{label} is missing: {path}')
    rows: list[dict[str, Any]] = []
    try:
        with path.open('r', encoding='utf-8', newline='') as handle:
            for number, line in enumerate(handle, start=1):
                if not line.endswith('\n'):
                    raise PlanningError(f'{label} line {number} is not LF-terminated')
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PlanningError(f'{label} line {number} must be an object')
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanningError(f'{label} is unreadable') from exc
    return rows

def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise PlanningError('planning artifact contains a non-canonical JSON value') from exc

def jsonl(rows: list[Mapping[str, Any]]) -> str:
    try:
        return ''.join(json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n' for row in rows)
    except (TypeError, ValueError) as exc:
        raise PlanningError('planning artifact contains a non-canonical JSON value') from exc

def publish_run(final_dir: Path, files: Mapping[str, str]) -> None:
    if final_dir.exists():
        for name, content in files.items():
            path = final_dir / name
            if not path.is_file() or path.read_text(encoding='utf-8') != content:
                raise PlanningError('existing planning run differs from content-addressed output')
        return
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix='.plan.', suffix='.tmp', dir=final_dir.parent))
    try:
        for name, content in files.items():
            (temp_dir / name).write_text(content, encoding='utf-8')
        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            if final_dir.exists() and all((final_dir / name).is_file() and (final_dir / name).read_text(encoding='utf-8') == content for name, content in files.items()):
                return
            raise
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
