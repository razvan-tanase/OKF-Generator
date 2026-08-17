from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping
from .compilation_errors import CompilationError

def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompilationError("compilation artifact contains a non-canonical JSON value") from exc

def jsonl(rows: Iterable[Mapping[str, Any]]) -> str:
    try:
        return "".join(json.dumps(dict(row), sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n" for row in rows)
    except (TypeError, ValueError) as exc:
        raise CompilationError("compilation JSONL contains a non-canonical value") from exc

def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise CompilationError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise CompilationError(f"{label} must be a JSON object")
    return value

def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CompilationError(f"{label} is missing: {path}")
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise CompilationError(f"{label} line {number} is not LF-terminated")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise CompilationError(f"{label} line {number} must be an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationError(f"{label} is unreadable") from exc
    return rows

def publish_directory(final_dir: Path, files: Mapping[str, str]) -> bool:
    """Publish immutable generation. Returns True iff this call created it."""
    if final_dir.exists():
        if not final_dir.is_dir():
            raise CompilationError("existing state generation path is not a directory")
        for name, content in files.items():
            path = final_dir / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise CompilationError("existing state generation differs from content-addressed output")
        extra = sorted(p.name for p in final_dir.iterdir() if p.name not in files)
        if extra:
            raise CompilationError(f"existing state generation has unexpected files: {extra}")
        return False
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".generation.", suffix=".tmp", dir=final_dir.parent))
    try:
        for name, content in files.items():
            (temp_dir / name).write_text(content, encoding="utf-8", newline="\n")
        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            if final_dir.exists() and all((final_dir / name).is_file() and (final_dir / name).read_text(encoding="utf-8") == content for name, content in files.items()):
                return False
            raise
        return True
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

@contextmanager
def state_lock(state_root: Path):
    """Advisory cross-platform lock released automatically on process exit."""
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / ".compile.lock"
    handle = lock_path.open("a+b")
    try:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            try:
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                unlock = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
            except ImportError as exc:
                raise CompilationError("no supported standard-library file locking primitive is available") from exc
        yield
    finally:
        try:
            if "unlock" in locals():
                unlock()
        finally:
            handle.close()
