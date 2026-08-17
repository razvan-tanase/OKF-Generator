from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping
from .structural_errors import StructuralizationError

def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StructuralizationError("structural artifact contains a non-canonical JSON value") from exc

def jsonl(rows: Iterable[Mapping[str, Any]]) -> str:
    try:
        return "".join(json.dumps(dict(row), sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n" for row in rows)
    except (TypeError, ValueError) as exc:
        raise StructuralizationError("structural JSONL contains a non-canonical value") from exc

def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def publish_run(final_dir: Path, files: Mapping[str,str]) -> None:
    if final_dir.exists():
        if not final_dir.is_dir(): raise StructuralizationError("existing structural run path is not a directory")
        for name,content in files.items():
            p=final_dir/name
            if not p.is_file() or p.read_text(encoding="utf-8")!=content:
                raise StructuralizationError("existing structural run differs from content-addressed output")
        extra=sorted(p.name for p in final_dir.iterdir() if p.name not in files)
        if extra: raise StructuralizationError(f"existing structural run has unexpected files: {extra}")
        return
    final_dir.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix=".structural.",suffix=".tmp",dir=final_dir.parent))
    try:
        for name,content in files.items():
            (temp/name).write_text(content,encoding="utf-8",newline="\n")
        try: os.replace(temp,final_dir)
        except OSError:
            if final_dir.exists() and all((final_dir/name).is_file() and (final_dir/name).read_text(encoding="utf-8")==content for name,content in files.items()): return
            raise
    except Exception:
        if temp.exists(): shutil.rmtree(temp,ignore_errors=True)
        raise
