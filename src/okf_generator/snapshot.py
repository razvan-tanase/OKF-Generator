from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .acquire import SOURCE_ID_RE, load_receipt


class SnapshotError(RuntimeError):
    """Raised when Stage 02 cannot create or verify an immutable snapshot."""


CANONICAL_PAYLOAD_BASIS = "canonical-filesystem-v1"
GIT_IDENTITY_BASIS = "git-object-lock-v1"


@dataclass(frozen=True)
class SnapshotManifest:
    schema_version: str
    stage: str
    source_id: str
    snapshot_id: str
    artifact: Mapping[str, Any]
    source_fingerprint: Mapping[str, str]
    storage_fingerprint: Mapping[str, str]
    acquisition: Mapping[str, str]
    version_lock: Mapping[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class PayloadFingerprint:
    digest: str
    entries: tuple[Mapping[str, Any], ...]

    def integrity_json(self) -> str:
        payload = {
            "schema_version": "0.1",
            "basis": CANONICAL_PAYLOAD_BASIS,
            "sha256": self.digest,
            "entries": list(self.entries),
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _entry_kind(path: Path) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    raise SnapshotError(f"unsupported snapshot filesystem entry: {path}")


def _walk_entries(path: Path, relative: str = ".") -> Iterable[Mapping[str, Any]]:
    kind = _entry_kind(path)
    if kind == "symlink":
        yield {"path": relative, "kind": "symlink", "target": os.readlink(path)}
        return
    if kind == "file":
        size = os.lstat(path).st_size
        yield {
            "path": relative,
            "kind": "file",
            "size": size,
            "sha256": _sha256_file(path),
            "executable": bool(os.lstat(path).st_mode & 0o111),
        }
        return

    yield {"path": relative, "kind": "directory"}
    with os.scandir(path) as iterator:
        children = sorted(iterator, key=lambda item: os.fsencode(item.name))
    for child in children:
        child_rel = child.name if relative == "." else f"{relative}/{child.name}"
        yield from _walk_entries(Path(child.path), child_rel)


def fingerprint_payload(path: Path | str) -> PayloadFingerprint:
    artifact = Path(path)
    if not artifact.exists() and not artifact.is_symlink():
        raise SnapshotError(f"snapshot artifact does not exist: {artifact}")

    entries = tuple(_walk_entries(artifact))
    digest = hashlib.sha256()
    digest.update(f"{CANONICAL_PAYLOAD_BASIS}\n".encode("ascii"))
    for entry in entries:
        digest.update(_canonical_json_bytes(entry))
        digest.update(b"\n")
    return PayloadFingerprint(digest=digest.hexdigest(), entries=entries)


def _safe_artifact_path(acquisition_dir: Path, value: str) -> Path:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or value in {"", "."}:
        raise SnapshotError("acquisition receipt contains an unsafe artifact path")
    path = acquisition_dir.joinpath(*candidate.parts)
    try:
        path.relative_to(acquisition_dir)
    except ValueError as exc:
        raise SnapshotError("acquisition artifact escapes its acquisition directory") from exc
    if not path.exists() and not path.is_symlink():
        raise SnapshotError(f"acquisition artifact is missing: {path}")
    return path


def _copy_artifact(source: Path, destination: Path) -> None:
    kind = _entry_kind(source)
    if kind == "symlink":
        os.symlink(os.readlink(source), destination)
    elif kind == "file":
        shutil.copy2(source, destination, follow_symlinks=False)
    elif kind == "directory":
        shutil.copytree(source, destination, symlinks=True)
    else:  # pragma: no cover - _entry_kind already rejects this
        raise SnapshotError(f"unsupported artifact kind: {kind}")


class SnapshotEngine:
    def __init__(
        self,
        acquisition_root: Path | str = Path(".okf-generator/acquired"),
        snapshot_root: Path | str = Path(".okf-generator/snapshots"),
        *,
        git_executable: str = "git",
        git_timeout: float = 60.0,
    ) -> None:
        self.acquisition_root = Path(acquisition_root)
        self.snapshot_root = Path(snapshot_root)
        self.git_executable = git_executable
        self.git_timeout = git_timeout

    def _run_git(self, repository: Path, args: list[str]) -> str:
        env = os.environ.copy()
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "protocol.ext.allow",
                "GIT_CONFIG_VALUE_0": "never",
            }
        )
        try:
            result = subprocess.run(
                [self.git_executable, "-C", str(repository), *args],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=self.git_timeout,
            )
        except FileNotFoundError as exc:
            raise SnapshotError("git executable is required to snapshot git acquisitions") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "git command failed").strip()
            raise SnapshotError(detail) from exc
        except subprocess.TimeoutExpired as exc:
            raise SnapshotError("git snapshot operation timed out") from exc
        return result.stdout.strip()

    def _git_lock(self, repository: Path, requested_ref: str | None) -> Mapping[str, Any]:
        bare = self._run_git(repository, ["rev-parse", "--is-bare-repository"])
        if bare != "true":
            raise SnapshotError("git acquisition is not a bare repository")

        selected_ref = requested_ref or "HEAD"
        selected_object = self._run_git(
            repository,
            ["rev-parse", "--verify", "--end-of-options", selected_ref],
        )
        selected_object_type = self._run_git(
            repository,
            ["cat-file", "-t", selected_object],
        )
        commit = self._run_git(
            repository,
            ["rev-parse", "--verify", "--end-of-options", f"{selected_ref}^{{commit}}"],
        )
        try:
            object_format = self._run_git(repository, ["rev-parse", "--show-object-format"])
        except SnapshotError:
            try:
                object_format = self._run_git(
                    repository, ["config", "--get", "extensions.objectFormat"]
                )
            except SnapshotError:
                object_format = "sha1"
            object_format = object_format or "sha1"

        return {
            "kind": "git",
            "selected_ref": selected_ref,
            "object_format": object_format,
            "selected_object": selected_object,
            "selected_object_type": selected_object_type,
            "commit": commit,
        }

    @staticmethod
    def _source_identity(
        artifact_kind: str,
        payload: PayloadFingerprint,
        git_lock: Mapping[str, Any] | None,
    ) -> tuple[str, str, Mapping[str, Any]]:
        if artifact_kind == "bare-git-repository":
            if git_lock is None:
                raise SnapshotError("git snapshot identity requires a git lock")
            descriptor = {
                "kind": "git-object-lock",
                "object_format": git_lock["object_format"],
                "selected_object": git_lock["selected_object"],
                "selected_object_type": git_lock["selected_object_type"],
                "commit": git_lock["commit"],
            }
            digest = _sha256_bytes(_canonical_json_bytes(descriptor))
            return digest, GIT_IDENTITY_BASIS, git_lock

        return (
            payload.digest,
            CANONICAL_PAYLOAD_BASIS,
            {"kind": "content-digest", "sha256": payload.digest},
        )

    def snapshot(self, source_id: str) -> SnapshotManifest:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise SnapshotError("source_id must match Stage 01 source identifier rules")

        acquisition_dir = self.acquisition_root / source_id
        receipt_path = acquisition_dir / "receipt.json"
        if not receipt_path.is_file():
            raise SnapshotError(f"Stage 01 receipt is missing: {receipt_path}")

        receipt = load_receipt(receipt_path)
        if receipt.get("stage") != "01-acquire":
            raise SnapshotError("snapshot input is not a Stage 01 acquisition receipt")
        if receipt.get("source_id") != source_id:
            raise SnapshotError("snapshot source_id does not match the acquisition receipt")
        artifact_meta = receipt.get("artifact")
        if not isinstance(artifact_meta, dict):
            raise SnapshotError("acquisition receipt is missing artifact metadata")
        artifact_path_value = artifact_meta.get("path")
        artifact_kind = artifact_meta.get("kind")
        if not isinstance(artifact_path_value, str) or not isinstance(artifact_kind, str):
            raise SnapshotError("acquisition artifact metadata is malformed")

        artifact = _safe_artifact_path(acquisition_dir, artifact_path_value)
        observed_kind = _entry_kind(artifact)
        if artifact_kind == "file" and observed_kind != "file":
            raise SnapshotError("acquisition artifact kind no longer matches its receipt")
        if artifact_kind == "directory" and observed_kind != "directory":
            raise SnapshotError("acquisition artifact kind no longer matches its receipt")
        if artifact_kind == "symlink" and observed_kind != "symlink":
            raise SnapshotError("acquisition artifact kind no longer matches its receipt")
        if artifact_kind == "bare-git-repository" and observed_kind != "directory":
            raise SnapshotError("acquired git repository is no longer a directory")
        if artifact_kind not in {"file", "directory", "symlink", "bare-git-repository"}:
            raise SnapshotError(f"unsupported Stage 01 artifact kind: {artifact_kind}")

        before = fingerprint_payload(artifact)
        git_lock = (
            self._git_lock(artifact, receipt.get("requested_ref"))
            if artifact_kind == "bare-git-repository"
            else None
        )
        source_digest, source_basis, version_lock = self._source_identity(
            artifact_kind, before, git_lock
        )
        snapshot_id = f"sha256-{source_digest}"

        source_root = self.snapshot_root / source_id
        final_dir = source_root / snapshot_id
        if final_dir.exists():
            manifest = self._verify_existing(final_dir, source_id, snapshot_id, source_digest)
            after_existing = fingerprint_payload(artifact)
            current_digest, _, _ = self._source_identity(
                artifact_kind,
                after_existing,
                self._git_lock(artifact, receipt.get("requested_ref"))
                if artifact_kind == "bare-git-repository"
                else None,
            )
            if current_digest != source_digest:
                raise SnapshotError("acquisition changed while its snapshot identity was computed")
            return manifest

        source_root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}.", suffix=".tmp", dir=source_root))
        try:
            payload_dir = temp_dir / "payload"
            payload_dir.mkdir()
            snapshot_artifact = payload_dir / (artifact.name or "source")
            _copy_artifact(artifact, snapshot_artifact)

            after_source = fingerprint_payload(artifact)
            after_snapshot = fingerprint_payload(snapshot_artifact)
            if after_source.digest != before.digest:
                raise SnapshotError("acquisition changed while the snapshot was being copied")
            if after_snapshot.digest != before.digest:
                raise SnapshotError("snapshot copy does not match the acquired payload")

            if artifact_kind == "bare-git-repository":
                copied_lock = self._git_lock(snapshot_artifact, receipt.get("requested_ref"))
                copied_digest, _, _ = self._source_identity(
                    artifact_kind, after_snapshot, copied_lock
                )
                if copied_digest != source_digest:
                    raise SnapshotError("copied git snapshot does not match the locked git identity")

            receipt_bytes = receipt_path.read_bytes()
            (temp_dir / "acquisition-receipt.json").write_bytes(receipt_bytes)
            (temp_dir / "integrity.json").write_text(
                after_snapshot.integrity_json(), encoding="utf-8"
            )

            manifest = SnapshotManifest(
                schema_version="0.1",
                stage="02-snapshot",
                source_id=source_id,
                snapshot_id=snapshot_id,
                artifact={
                    "path": snapshot_artifact.relative_to(temp_dir).as_posix(),
                    "kind": artifact_kind,
                },
                source_fingerprint={
                    "algorithm": "sha256",
                    "value": source_digest,
                    "basis": source_basis,
                },
                storage_fingerprint={
                    "algorithm": "sha256",
                    "value": after_snapshot.digest,
                    "basis": CANONICAL_PAYLOAD_BASIS,
                },
                acquisition={
                    "receipt_path": "acquisition-receipt.json",
                    "receipt_sha256": _sha256_bytes(receipt_bytes),
                },
                version_lock=version_lock,
            )
            (temp_dir / "snapshot.json").write_text(manifest.to_json(), encoding="utf-8")

            try:
                os.replace(temp_dir, final_dir)
            except OSError:
                if final_dir.exists():
                    return self._verify_existing(
                        final_dir, source_id, snapshot_id, source_digest
                    )
                raise
            return manifest
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _verify_existing(
        self,
        snapshot_dir: Path,
        source_id: str,
        snapshot_id: str,
        source_digest: str,
    ) -> SnapshotManifest:
        manifest_path = snapshot_dir / "snapshot.json"
        if not manifest_path.is_file():
            raise SnapshotError("existing snapshot is missing snapshot.json")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SnapshotError("existing snapshot manifest is unreadable") from exc

        if data.get("stage") != "02-snapshot":
            raise SnapshotError("existing snapshot has the wrong stage")
        if data.get("source_id") != source_id or data.get("snapshot_id") != snapshot_id:
            raise SnapshotError("existing snapshot identity metadata is inconsistent")
        fingerprint = data.get("source_fingerprint")
        if not isinstance(fingerprint, dict) or fingerprint.get("value") != source_digest:
            raise SnapshotError("existing snapshot source fingerprint is inconsistent")

        artifact_meta = data.get("artifact")
        if not isinstance(artifact_meta, dict) or not isinstance(artifact_meta.get("path"), str):
            raise SnapshotError("existing snapshot artifact metadata is malformed")
        artifact = _safe_artifact_path(snapshot_dir, artifact_meta["path"])
        actual_storage = fingerprint_payload(artifact)
        storage = data.get("storage_fingerprint")
        if not isinstance(storage, dict) or storage.get("value") != actual_storage.digest:
            raise SnapshotError("existing immutable snapshot payload has been modified")

        artifact_kind = artifact_meta.get("kind")
        version_lock = data.get("version_lock")
        if not isinstance(version_lock, dict):
            raise SnapshotError("existing snapshot version lock is malformed")
        if artifact_kind == "bare-git-repository":
            selected_ref = version_lock.get("selected_ref")
            if not isinstance(selected_ref, str) or not selected_ref:
                raise SnapshotError("existing git snapshot lock is missing selected_ref")
            actual_lock = self._git_lock(artifact, selected_ref)
            actual_source_digest, actual_basis, _ = self._source_identity(
                "bare-git-repository", actual_storage, actual_lock
            )
            if actual_source_digest != source_digest or actual_basis != fingerprint.get("basis"):
                raise SnapshotError("existing git snapshot no longer matches its immutable identity")
            for field in (
                "object_format",
                "selected_object",
                "selected_object_type",
                "commit",
            ):
                if version_lock.get(field) != actual_lock.get(field):
                    raise SnapshotError("existing git snapshot version lock has been modified")
        else:
            if fingerprint.get("basis") != CANONICAL_PAYLOAD_BASIS:
                raise SnapshotError("existing snapshot uses an unexpected source identity basis")
            if actual_storage.digest != source_digest:
                raise SnapshotError("existing snapshot no longer matches its content address")
            if version_lock.get("kind") != "content-digest" or version_lock.get("sha256") != source_digest:
                raise SnapshotError("existing snapshot content lock has been modified")

        receipt_meta = data.get("acquisition")
        if not isinstance(receipt_meta, dict):
            raise SnapshotError("existing snapshot acquisition metadata is malformed")
        saved_receipt = snapshot_dir / str(receipt_meta.get("receipt_path", ""))
        if not saved_receipt.is_file():
            raise SnapshotError("existing snapshot acquisition receipt is missing")
        if _sha256_file(saved_receipt) != receipt_meta.get("receipt_sha256"):
            raise SnapshotError("existing snapshot acquisition receipt has been modified")

        integrity_path = snapshot_dir / "integrity.json"
        if not integrity_path.is_file():
            raise SnapshotError("existing snapshot integrity manifest is missing")
        try:
            integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SnapshotError("existing snapshot integrity manifest is unreadable") from exc
        if integrity.get("basis") != CANONICAL_PAYLOAD_BASIS:
            raise SnapshotError("existing snapshot integrity basis is inconsistent")
        if integrity.get("sha256") != actual_storage.digest:
            raise SnapshotError("existing snapshot integrity manifest is inconsistent")
        if integrity.get("entries") != list(actual_storage.entries):
            raise SnapshotError("existing snapshot integrity entries are inconsistent")

        return SnapshotManifest(
            schema_version=str(data["schema_version"]),
            stage=str(data["stage"]),
            source_id=str(data["source_id"]),
            snapshot_id=str(data["snapshot_id"]),
            artifact=dict(data["artifact"]),
            source_fingerprint=dict(data["source_fingerprint"]),
            storage_fingerprint=dict(data["storage_fingerprint"]),
            acquisition=dict(data["acquisition"]),
            version_lock=dict(data["version_lock"]),
        )


def load_snapshot_manifest(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
