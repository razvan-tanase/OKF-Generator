from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from .resolution_errors import ResolutionError


def publish_run(final_dir: Path, files: Mapping[str, str]) -> None:
    if final_dir.exists():
        for name, content in files.items():
            path = final_dir / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ResolutionError("existing resolution run differs from content-addressed output")
        return
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".resolve.", suffix=".tmp", dir=final_dir.parent))
    try:
        for name, content in files.items():
            (temp_dir / name).write_text(content, encoding="utf-8")
        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            if final_dir.exists() and all((final_dir / name).is_file() and (final_dir / name).read_text(encoding="utf-8") == content for name, content in files.items()):
                return
            raise
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
