from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .classification_detect import ClassificationDetectionError, EntryClassification, _summary, _walk_classifications
from .snapshot import SnapshotEngine, SnapshotError, SnapshotManifest

RULESET_ID = "builtin-v1"
SNAPSHOT_ID_RE = re.compile(r"^sha256-[0-9a-f]{64}$")


class ClassificationError(RuntimeError):
    """Raised when Stage 03 cannot deterministically classify a verified snapshot."""




@dataclass(frozen=True)
class ClassificationManifest:
    schema_version: str
    stage: str
    ruleset: str
    source_id: str
    snapshot_id: str
    snapshot_manifest_sha256: str
    source: Mapping[str, Any]
    entries: tuple[Mapping[str, Any], ...]
    summary: Mapping[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_snapshot_artifact(snapshot_dir: Path, value: str) -> Path:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or value in {"", "."}:
        raise ClassificationError("snapshot manifest contains an unsafe artifact path")
    path = snapshot_dir.joinpath(*candidate.parts)
    try:
        path.relative_to(snapshot_dir)
    except ValueError as exc:
        raise ClassificationError("snapshot artifact escapes its snapshot directory") from exc
    if not path.exists() and not path.is_symlink():
        raise ClassificationError("verified snapshot artifact is missing")
    return path



class ClassificationEngine:
    def __init__(
        self,
        snapshot_root: Path | str = Path(".okf-generator/snapshots"),
        output_root: Path | str = Path(".okf-generator/classifications"),
        *,
        ruleset: str = RULESET_ID,
        snapshot_verifier: Callable[[str, str], SnapshotManifest] | None = None,
    ) -> None:
        if ruleset != RULESET_ID:
            raise ClassificationError(f"unsupported classification ruleset: {ruleset}")
        self.snapshot_root = Path(snapshot_root)
        self.output_root = Path(output_root)
        self.ruleset = ruleset
        self.snapshot_engine = SnapshotEngine(snapshot_root=self.snapshot_root)
        self.snapshot_verifier = snapshot_verifier or self._verify_snapshot

    def _verify_snapshot(self, source_id: str, snapshot_id: str) -> SnapshotManifest:
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise ClassificationError("snapshot_id must be sha256- followed by 64 lowercase hex characters")
        snapshot_dir = self.snapshot_root / source_id / snapshot_id
        manifest_path = snapshot_dir / "snapshot.json"
        if not manifest_path.is_file():
            raise ClassificationError(f"Stage 02 snapshot manifest is missing: {manifest_path}")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ClassificationError("Stage 02 snapshot manifest is unreadable") from exc
        fingerprint = data.get("source_fingerprint")
        if not isinstance(fingerprint, dict) or not isinstance(fingerprint.get("value"), str):
            raise ClassificationError("Stage 02 snapshot fingerprint is malformed")
        source_digest = fingerprint["value"]
        if snapshot_id != f"sha256-{source_digest}":
            raise ClassificationError("snapshot path does not match its Stage 02 source identity")
        try:
            return self.snapshot_engine._verify_existing(snapshot_dir, source_id, snapshot_id, source_digest)
        except SnapshotError as exc:
            raise ClassificationError(f"Stage 02 snapshot verification failed: {exc}") from exc

    def classify(self, source_id: str, snapshot_id: str) -> ClassificationManifest:
        manifest = self.snapshot_verifier(source_id, snapshot_id)
        if manifest.stage != "02-snapshot" or manifest.source_id != source_id or manifest.snapshot_id != snapshot_id:
            raise ClassificationError("snapshot verifier returned inconsistent identity metadata")

        snapshot_dir = self.snapshot_root / source_id / snapshot_id
        snapshot_manifest_path = snapshot_dir / "snapshot.json"
        snapshot_manifest_sha256 = _sha256_file(snapshot_manifest_path)
        artifact_meta = manifest.artifact
        artifact_path_value = artifact_meta.get("path")
        artifact_kind = artifact_meta.get("kind")
        if not isinstance(artifact_path_value, str) or not isinstance(artifact_kind, str):
            raise ClassificationError("verified snapshot artifact metadata is malformed")
        artifact = _safe_snapshot_artifact(snapshot_dir, artifact_path_value)

        if artifact_kind == "bare-git-repository":
            entries = (
                EntryClassification(
                    ".", "directory", "application/x-git-repository", "git", "repository", "git",
                    {"basis": "stage-02-version-lock", "strength": "exact",
                     "object_format": manifest.version_lock.get("object_format"),
                     "selected_object_type": manifest.version_lock.get("selected_object_type")},
                    (),
                ),
            )
            source_kind = "git-repository"
        else:
            try:
                entries = tuple(_walk_classifications(artifact))
            except ClassificationDetectionError as exc:
                raise ClassificationError(str(exc)) from exc
            source_kind = {"file": "file", "directory": "directory", "symlink": "symlink"}.get(artifact_kind)
            if source_kind is None:
                raise ClassificationError(f"unsupported verified artifact kind: {artifact_kind}")

        verified_after = self.snapshot_verifier(source_id, snapshot_id)
        if verified_after != manifest or _sha256_file(snapshot_manifest_path) != snapshot_manifest_sha256:
            raise ClassificationError("Stage 02 snapshot changed while classification was running")

        entry_dicts = tuple(asdict(entry) for entry in entries)
        primary = entry_dicts[0]
        result = ClassificationManifest(
            schema_version="0.1",
            stage="03-classify",
            ruleset=self.ruleset,
            source_id=source_id,
            snapshot_id=snapshot_id,
            snapshot_manifest_sha256=snapshot_manifest_sha256,
            source={
                "kind": source_kind,
                "artifact_kind": artifact_kind,
                "primary_format": primary["format"],
                "primary_media_type": primary["media_type"],
                "primary_route": primary["route"],
            },
            entries=entry_dicts,
            summary=_summary(entries),
        )
        serialized = result.to_json()

        final_dir = self.output_root / source_id / snapshot_id / self.ruleset
        final_path = final_dir / "classification.json"
        if final_dir.exists():
            if not final_path.is_file():
                raise ClassificationError("existing classification directory is incomplete")
            if final_path.read_text(encoding="utf-8") != serialized:
                raise ClassificationError(
                    "existing classification differs for the same snapshot and ruleset; bump the ruleset instead of overwriting"
                )
            return result

        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{self.ruleset}.", suffix=".tmp", dir=final_dir.parent))
        try:
            (temp_dir / "classification.json").write_text(serialized, encoding="utf-8")
            try:
                os.replace(temp_dir, final_dir)
            except OSError:
                if final_dir.exists() and final_path.is_file() and final_path.read_text(encoding="utf-8") == serialized:
                    return result
                raise
            return result
        except Exception:
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
