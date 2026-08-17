from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, _maybe_text, MAX_GIT_BLOBS, MAX_GIT_BLOB_BYTES, MAX_GIT_TOTAL_BYTES

def _run_git(repository: Path | None, args: list[str], *, git_executable: str, git_timeout: float, text: bool = False):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    command = [git_executable]
    if repository is not None:
        command += ["-C", str(repository)]
    command += args
    try:
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=git_timeout,
            text=text,
        )
    except FileNotFoundError as exc:
        raise ExtractorError("git executable is required for Git extraction") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExtractorError("Git extraction command timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        raise ExtractorError(f"Git extraction command failed: {detail.strip() or exc.returncode}") from exc


def extract_git(repository: Path, source_path: str, version_lock: Mapping[str, Any], *, git_executable: str = "git", git_timeout: float = 60.0) -> ExtractorResult:
    commit = version_lock.get("commit")
    if not isinstance(commit, str) or not commit:
        raise ExtractorError("Git extraction requires Stage 02 locked commit")
    result = _run_git(repository, ["ls-tree", "-rz", "-r", "--full-tree", commit],
                      git_executable=git_executable, git_timeout=git_timeout)
    records = [r for r in result.stdout.split(b"\x00") if r]
    if len(records) > MAX_GIT_BLOBS:
        raise ExtractorError("Git tree entry limit exceeded")
    units: list[RawUnit] = []
    total = 0
    for record in records:
        try:
            meta, path_bytes = record.split(b"\t", 1)
            mode, obj_type, oid = meta.decode("ascii").split(" ")
            relpath = path_bytes.decode("utf-8", errors="surrogateescape")
        except Exception as exc:
            raise ExtractorError("malformed git ls-tree record") from exc
        if obj_type == "blob":
            size_out = _run_git(repository, ["cat-file", "-s", oid], git_executable=git_executable,
                                git_timeout=git_timeout, text=True)
            try:
                size = int(size_out.stdout.strip())
            except ValueError as exc:
                raise ExtractorError("git cat-file returned a non-integer blob size") from exc
            if size > MAX_GIT_BLOB_BYTES:
                units.append(RawUnit(source_path, "git-blob", data={"mode": mode, "oid": oid, "size": size},
                                     native_locator={"commit": commit, "path": relpath},
                                     diagnostics=("git-blob-size-limit-not-read",)))
                continue
            total += size
            if total > MAX_GIT_TOTAL_BYTES:
                raise ExtractorError("Git total blob-read limit exceeded")
            blob = _run_git(repository, ["cat-file", "blob", oid], git_executable=git_executable,
                            git_timeout=git_timeout).stdout
            text_value = _maybe_text(blob)
            diag = () if text_value is not None else ("git-binary-blob-not-decoded",)
            units.append(RawUnit(source_path, "git-blob", text=text_value,
                                 data={"mode": mode, "oid": oid, "size": size, "sha256": hashlib.sha256(blob).hexdigest()},
                                 native_locator={"commit": commit, "path": relpath}, diagnostics=diag))
        else:
            units.append(RawUnit(source_path, "git-reference", data={"mode": mode, "object_type": obj_type, "oid": oid},
                                 native_locator={"commit": commit, "path": relpath}))
    version = _run_git(None, ["--version"], git_executable=git_executable, git_timeout=git_timeout, text=True).stdout.strip()
    return ExtractorResult(tuple(units), tools={"git": version.removeprefix("git version ")})

