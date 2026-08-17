from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from .acquire import SOURCE_ID_RE
from .classify import RULESET_ID, SNAPSHOT_ID_RE
from .extract import PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalize import PROFILE_ID as NORMALIZATION_PROFILE_ID
from .synthesize import PROFILE_ID as SYNTHESIS_PROFILE_ID, PROVIDER_RE
from .resolve import PROFILE_ID as RESOLUTION_PROFILE_ID
from .plan import PROFILE_ID as PLANNING_PROFILE_ID
from .canonical_state import FINAL_ID_BASIS
from .compilation_errors import CompilationError
from .compilation_io import atomic_write_text
from .compilation_model import CompilationManifest
from .compilation_upstream import PLAN_RUN_RE, load_verified_plan, plan_run_dir
from .compilation_runner import compile_state

PROFILE_ID="builtin-v1"

class CompilationEngine:
    def __init__(self,
        synthesis_root:Path|str=Path(".okf-generator/syntheses"),
        resolution_root:Path|str=Path(".okf-generator/resolutions"),
        plan_root:Path|str=Path(".okf-generator/plans"),
        state_root:Path|str=Path(".okf-generator/state"), *,
        ruleset:str=RULESET_ID, extraction_profile:str=EXTRACTION_PROFILE_ID,
        normalization_profile:str=NORMALIZATION_PROFILE_ID, synthesis_profile:str=SYNTHESIS_PROFILE_ID,
        resolution_profile:str=RESOLUTION_PROFILE_ID, planning_profile:str=PLANNING_PROFILE_ID,
        profile:str=PROFILE_ID,
        plan_verifier:Callable[...,Any]=load_verified_plan,
        pointer_writer:Callable[[Path,str],None]=atomic_write_text,
    )->None:
        if (ruleset,extraction_profile,normalization_profile,synthesis_profile,resolution_profile,planning_profile)!=(RULESET_ID,EXTRACTION_PROFILE_ID,NORMALIZATION_PROFILE_ID,SYNTHESIS_PROFILE_ID,RESOLUTION_PROFILE_ID,PLANNING_PROFILE_ID):
            raise CompilationError("Stage 09 supports only the currently pinned upstream builtin-v1 profiles")
        if profile!=PROFILE_ID: raise CompilationError(f"unsupported compilation profile: {profile}")
        self.synthesis_root=Path(synthesis_root); self.resolution_root=Path(resolution_root); self.plan_root=Path(plan_root); self.state_root=Path(state_root)
        self.ruleset=ruleset; self.extraction_profile=extraction_profile; self.normalization_profile=normalization_profile
        self.synthesis_profile=synthesis_profile; self.resolution_profile=resolution_profile; self.planning_profile=planning_profile; self.profile=profile
        self.plan_verifier=plan_verifier; self.pointer_writer=pointer_writer

    def _validate_identity(self,source_id:str,snapshot_id:str,synthesis_provider:str,synthesis_run_id:str,resolution_run_id:str,plan_run_id:str)->None:
        if not SOURCE_ID_RE.fullmatch(source_id): raise CompilationError("source_id must match Stage 01 source identifier rules")
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id): raise CompilationError("snapshot_id must match Stage 02 content-addressed identifier rules")
        if not PROVIDER_RE.fullmatch(synthesis_provider): raise CompilationError("synthesis_provider is unsafe for compilation paths")
        for label,value in (("synthesis_run_id",synthesis_run_id),("resolution_run_id",resolution_run_id),("plan_run_id",plan_run_id)):
            if not PLAN_RUN_RE.fullmatch(value): raise CompilationError(f"{label} must be content-addressed")

    def _load_plan(self,source_id:str,snapshot_id:str,synthesis_provider:str,synthesis_run_id:str,resolution_run_id:str,plan_run_id:str):
        pdir=plan_run_dir(self.plan_root,source_id,snapshot_id,self.ruleset,self.extraction_profile,self.normalization_profile,
                          self.synthesis_profile,synthesis_provider,synthesis_run_id,self.resolution_profile,resolution_run_id,
                          self.planning_profile,plan_run_id)
        expected={"source_id":source_id,"snapshot_id":snapshot_id,"ruleset":self.ruleset,"extraction_profile":self.extraction_profile,
                  "normalization_profile":self.normalization_profile,"synthesis_profile":self.synthesis_profile,
                  "synthesis_provider":synthesis_provider,"synthesis_run_id":synthesis_run_id,"resolution_profile":self.resolution_profile,
                  "resolution_run_id":resolution_run_id,"planning_profile":self.planning_profile,"plan_run_id":plan_run_id}
        return pdir, self.plan_verifier(pdir,self.resolution_root,self.synthesis_root,expected)

    def compile(self,source_id:str,snapshot_id:str,synthesis_run_id:str,resolution_run_id:str,plan_run_id:str,*,synthesis_provider:str)->CompilationManifest:
        return compile_state(self,source_id,snapshot_id,synthesis_run_id,resolution_run_id,plan_run_id,synthesis_provider=synthesis_provider)

__all__=["PROFILE_ID","CompilationEngine","CompilationError","CompilationManifest","FINAL_ID_BASIS"]
