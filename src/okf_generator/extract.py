from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .acquire import SOURCE_ID_RE
from .classify import ClassificationEngine, ClassificationError, RULESET_ID, SNAPSHOT_ID_RE
from .extractors import ExtractorError, RawUnit, dispatch_file, extract_git

PROFILE_ID = "builtin-v1"


class ExtractionError(RuntimeError):
    """Raised when Stage 04 cannot extract a verified classified snapshot."""


@dataclass(frozen=True)
class ExtractionUnit:
    unit_id: str
    source_path: str
    kind: str
    text: str | None
    data: Mapping[str, Any]
    native_locator: Mapping[str, Any]
    metadata: Mapping[str, Any]
    diagnostics: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


@dataclass(frozen=True)
class ExtractionManifest:
    schema_version: str
    stage: str
    profile: str
    source_id: str
    snapshot_id: str
    classification_ruleset: str
    snapshot_manifest_sha256: str
    classification_sha256: str
    units_path: str
    units_sha256: str
    unit_count: int
    diagnostic_count: int
    diagnostics: tuple[str, ...]
    tools: Mapping[str, str]
    routes: Mapping[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_child(root: Path, relative: str, *, allow_dot: bool = False) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or (relative in {"", "."} and not allow_dot):
        raise ExtractionError(f"unsafe source-relative path: {relative!r}")
    if relative == ".":
        return root
    path = root.joinpath(*candidate.parts)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ExtractionError("classified entry escapes snapshot artifact") from exc
    if not path.exists() and not path.is_symlink():
        raise ExtractionError(f"classified snapshot entry is missing: {relative}")
    return path


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExtractionError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExtractionError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ExtractionError(f"{label} must be a JSON object")
    return value


class ExtractionEngine:
    def __init__(
        self,
        snapshot_root: Path | str = Path(".okf-generator/snapshots"),
        classification_root: Path | str = Path(".okf-generator/classifications"),
        output_root: Path | str = Path(".okf-generator/extractions"),
        *,
        ruleset: str = RULESET_ID,
        profile: str = PROFILE_ID,
        classification_verifier: Callable[[str, str], Mapping[str, Any]] | None = None,
        git_executable: str = "git",
        git_timeout: float = 60.0,
    ) -> None:
        if profile != PROFILE_ID:
            raise ExtractionError(f"unsupported extraction profile: {profile}")
        self.snapshot_root = Path(snapshot_root)
        self.classification_root = Path(classification_root)
        self.output_root = Path(output_root)
        self.ruleset = ruleset
        self.profile = profile
        self.git_executable = git_executable
        self.git_timeout = git_timeout
        self.classification_engine = ClassificationEngine(
            snapshot_root=self.snapshot_root,
            output_root=self.classification_root,
            ruleset=self.ruleset,
        )
        self.classification_verifier = classification_verifier or self._verify_classification

    def _classification_path(self, source_id: str, snapshot_id: str) -> Path:
        return self.classification_root / source_id / snapshot_id / self.ruleset / "classification.json"

    def _verify_classification(self, source_id: str, snapshot_id: str) -> Mapping[str, Any]:
        path = self._classification_path(source_id, snapshot_id)
        existing = _load_json(path, "Stage 03 classification")
        try:
            derived = self.classification_engine.classify(source_id, snapshot_id)
        except ClassificationError as exc:
            raise ExtractionError(f"Stage 03 classification verification failed: {exc}") from exc
        if json.loads(derived.to_json()) != existing:
            raise ExtractionError("Stage 03 classification does not match the current verified snapshot")
        return existing

    def extract(self, source_id: str, snapshot_id: str) -> ExtractionManifest:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise ExtractionError("source_id must match Stage 01 source identifier rules")
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise ExtractionError("snapshot_id must match Stage 02 content-addressed identifier rules")

        classification_path = self._classification_path(source_id, snapshot_id)
        classification = dict(self.classification_verifier(source_id, snapshot_id))
        if classification.get("stage") != "03-classify" or classification.get("source_id") != source_id \
                or classification.get("snapshot_id") != snapshot_id or classification.get("ruleset") != self.ruleset:
            raise ExtractionError("classification verifier returned inconsistent identity metadata")
        classification_sha256 = _sha256_file(classification_path)

        snapshot_dir = self.snapshot_root / source_id / snapshot_id
        snapshot_path = snapshot_dir / "snapshot.json"
        snapshot = _load_json(snapshot_path, "Stage 02 snapshot manifest")
        if snapshot.get("stage") != "02-snapshot" or snapshot.get("source_id") != source_id or snapshot.get("snapshot_id") != snapshot_id:
            raise ExtractionError("Stage 02 snapshot manifest identity is inconsistent")
        snapshot_sha256 = _sha256_file(snapshot_path)
        artifact_meta = snapshot.get("artifact")
        if not isinstance(artifact_meta, dict) or not isinstance(artifact_meta.get("path"), str):
            raise ExtractionError("Stage 02 artifact metadata is malformed")
        artifact = _safe_child(snapshot_dir, artifact_meta["path"])

        units_raw: list[RawUnit] = []
        result_diagnostics: list[str] = []
        tools: dict[str, str] = {}
        routes: dict[str, int] = {}

        source_meta = classification.get("source")
        entries = classification.get("entries")
        if not isinstance(source_meta, dict) or not isinstance(entries, list):
            raise ExtractionError("Stage 03 classification structure is malformed")

        if artifact_meta.get("kind") == "bare-git-repository":
            version_lock = snapshot.get("version_lock")
            if not isinstance(version_lock, dict):
                raise ExtractionError("Git snapshot is missing its version lock")
            try:
                result = extract_git(artifact, ".", version_lock, git_executable=self.git_executable, git_timeout=self.git_timeout)
            except ExtractorError as exc:
                raise ExtractionError(str(exc)) from exc
            units_raw.extend(result.units)
            result_diagnostics.extend(result.diagnostics)
            self._merge_tools(tools, result.tools)
            routes["git"] = 1
        else:
            artifact_kind = artifact_meta.get("kind")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ExtractionError("classification entry must be an object")
                relative = entry.get("path")
                entry_kind = entry.get("entry_kind")
                route = str(entry.get("route"))
                if not isinstance(relative, str) or not isinstance(entry_kind, str):
                    raise ExtractionError("classification entry path/kind is malformed")
                routes[route] = routes.get(route, 0) + 1
                if relative == "." and artifact_kind == "file":
                    entry_path = artifact
                elif relative == "." and artifact_kind in {"directory", "symlink"}:
                    entry_path = artifact
                else:
                    if artifact_kind != "directory":
                        raise ExtractionError("nested classification entry requires a directory snapshot")
                    entry_path = _safe_child(artifact, relative, allow_dot=True)

                if entry_kind == "directory":
                    units_raw.append(RawUnit(relative, "directory", native_locator={"path": relative}))
                elif entry_kind == "symlink":
                    target = entry.get("detection", {}).get("target") if isinstance(entry.get("detection"), dict) else None
                    units_raw.append(RawUnit(relative, "symlink", data={"target": target},
                                             native_locator={"path": relative}, diagnostics=("symlink-not-dereferenced",)))
                elif entry_kind == "file":
                    try:
                        result = dispatch_file(entry_path, entry)
                    except ExtractorError as exc:
                        raise ExtractionError(f"extract {relative}: {exc}") from exc
                    units_raw.extend(result.units)
                    result_diagnostics.extend(result.diagnostics)
                    self._merge_tools(tools, result.tools)
                else:
                    raise ExtractionError(f"unsupported classified entry kind: {entry_kind}")

        classification_after = dict(self.classification_verifier(source_id, snapshot_id))
        if classification_after != classification or _sha256_file(classification_path) != classification_sha256 \
                or _sha256_file(snapshot_path) != snapshot_sha256:
            raise ExtractionError("snapshot or classification changed while extraction was running")

        units = tuple(
            ExtractionUnit(
                unit_id=f"u{index:06d}",
                source_path=unit.source_path,
                kind=unit.kind,
                text=unit.text,
                data=dict(unit.data),
                native_locator=dict(unit.native_locator),
                metadata=dict(unit.metadata),
                diagnostics=tuple(unit.diagnostics),
            )
            for index, unit in enumerate(units_raw, start=1)
        )
        units_text = "".join(unit.to_json() + "\n" for unit in units)
        units_sha256 = hashlib.sha256(units_text.encode("utf-8")).hexdigest()
        diagnostic_count = len(result_diagnostics) + sum(len(unit.diagnostics) for unit in units)
        manifest = ExtractionManifest(
            schema_version="0.1",
            stage="04-extract",
            profile=self.profile,
            source_id=source_id,
            snapshot_id=snapshot_id,
            classification_ruleset=self.ruleset,
            snapshot_manifest_sha256=snapshot_sha256,
            classification_sha256=classification_sha256,
            units_path="units.jsonl",
            units_sha256=units_sha256,
            unit_count=len(units),
            diagnostic_count=diagnostic_count,
            diagnostics=tuple(result_diagnostics),
            tools=dict(sorted(tools.items())),
            routes=dict(sorted(routes.items())),
        )
        self._publish(source_id, snapshot_id, manifest, units_text)
        return manifest

    @staticmethod
    def _merge_tools(target: dict[str, str], incoming: Mapping[str, str]) -> None:
        for name, version in incoming.items():
            existing = target.get(name)
            if existing is not None and existing != version:
                raise ExtractionError(f"extractor tool version conflict for {name}: {existing} != {version}")
            target[name] = version

    def _publish(self, source_id: str, snapshot_id: str, manifest: ExtractionManifest, units_text: str) -> None:
        final_dir = self.output_root / source_id / snapshot_id / self.ruleset / self.profile
        final_manifest = final_dir / "extraction.json"
        final_units = final_dir / "units.jsonl"
        serialized = manifest.to_json()
        if final_dir.exists():
            if not final_manifest.is_file() or not final_units.is_file():
                raise ExtractionError("existing extraction directory is incomplete")
            if final_manifest.read_text(encoding="utf-8") != serialized or final_units.read_text(encoding="utf-8") != units_text:
                raise ExtractionError(
                    "existing extraction differs for the same snapshot/ruleset/profile; bump the extraction profile or pin the toolchain"
                )
            return
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{self.profile}.", suffix=".tmp", dir=final_dir.parent))
        try:
            (temp_dir / "units.jsonl").write_text(units_text, encoding="utf-8")
            (temp_dir / "extraction.json").write_text(serialized, encoding="utf-8")
            try:
                os.replace(temp_dir, final_dir)
            except OSError:
                if final_dir.exists() and final_manifest.is_file() and final_units.is_file() \
                        and final_manifest.read_text(encoding="utf-8") == serialized \
                        and final_units.read_text(encoding="utf-8") == units_text:
                    return
                raise
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
