from __future__ import annotations
from pathlib import Path
from typing import Any
from .compilation_errors import CompilationError
from .compilation_state import load_current, load_generation
from .structural_errors import StructuralizationError
from .structural_io import sha_file

def load_verified_state(state_root:Path,generation_id:str|None=None):
    try:
        if generation_id is None:
            manifest,state=load_current(state_root)
            if manifest is None or state is None: raise StructuralizationError("canonical state has no active generation")
        else:
            manifest,state=load_generation(state_root,generation_id)
    except CompilationError as exc:
        raise StructuralizationError(f"Stage 09 canonical state verification failed: {exc}") from exc
    manifest_path=state_root/"generations"/manifest.generation_id/"state.json"
    return manifest,state,sha_file(manifest_path)
