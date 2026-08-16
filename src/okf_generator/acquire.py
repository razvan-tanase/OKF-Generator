from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HTTP_SCHEMES = {"http", "https"}
GIT_SCHEMES = {"git", "ssh", "file"}
DEFAULT_MAX_HTTP_BYTES = 100 * 1024 * 1024


class AcquisitionError(RuntimeError):
    """Raised when Stage 01 cannot acquire a source without transformation."""


@dataclass(frozen=True)
class AcquisitionSpec:
    source_id: str
    locator: str
    provider: str = "auto"
    ref: str | None = None

    def validate(self) -> None:
        if not SOURCE_ID_RE.fullmatch(self.source_id):
            raise AcquisitionError(
                "source_id must match ^[A-Za-z0-9][A-Za-z0-9._-]*$"
            )
        if not self.locator.strip():
            raise AcquisitionError("locator must be non-empty")
        if self.provider not in {"auto", "local", "http", "git"}:
            raise AcquisitionError(f"unsupported provider: {self.provider}")
        if self.ref and self.provider not in {"auto", "git"}:
            raise AcquisitionError("ref is only valid for git acquisition")


@dataclass(frozen=True)
class ProviderResult:
    artifact_path: str
    artifact_kind: str
    observations: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcquisitionReceipt:
    schema_version: str
    stage: str
    source_id: str
    provider: str
    locator: str
    acquired_at: str
    artifact: Mapping[str, Any]
    observations: Mapping[str, Any]
    requested_ref: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


class AcquisitionProvider(Protocol):
    name: str

    def acquire(self, spec: AcquisitionSpec, workspace: Path) -> ProviderResult:
        ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _file_uri_to_path(locator: str) -> Path:
    parsed = urllib.parse.urlparse(locator)
    if parsed.scheme != "file":
        return Path(locator).expanduser()
    if parsed.netloc not in {"", "localhost"}:
        raise AcquisitionError("file:// URLs with remote hosts are not supported")
    return Path(urllib.request.url2pathname(parsed.path)).expanduser()


def infer_provider(locator: str) -> str:
    stripped = locator.strip()
    if stripped.startswith("git+"):
        return "git"
    if re.match(r"^[^/@\s]+@[^:\s]+:.+", stripped):
        return "git"

    parsed = urllib.parse.urlparse(stripped)
    if parsed.scheme in HTTP_SCHEMES:
        if parsed.path.endswith(".git"):
            return "git"
        return "http"
    if parsed.scheme == "file":
        return "local"
    if parsed.scheme in GIT_SCHEMES:
        return "git"
    return "local"


class LocalProvider:
    name = "local"

    def __init__(self, acquisition_root: Path) -> None:
        self.acquisition_root = acquisition_root.resolve()

    def acquire(self, spec: AcquisitionSpec, workspace: Path) -> ProviderResult:
        source = _file_uri_to_path(spec.locator)
        if not source.exists() and not source.is_symlink():
            raise AcquisitionError(f"local source does not exist: {source}")

        source_resolved = source.resolve(strict=False)
        if source.is_dir() and self.acquisition_root.is_relative_to(source_resolved):
            raise AcquisitionError(
                "acquisition output root must not be inside the source directory"
            )

        payload = workspace / "payload"
        payload.mkdir()
        dest = payload / (source.name or "source")

        if source.is_symlink():
            os.symlink(os.readlink(source), dest)
            kind = "symlink"
        elif source.is_file():
            shutil.copy2(source, dest, follow_symlinks=False)
            kind = "file"
        elif source.is_dir():
            shutil.copytree(source, dest, symlinks=True)
            kind = "directory"
        else:
            raise AcquisitionError(f"unsupported local source type: {source}")

        return ProviderResult(
            artifact_path=dest.relative_to(workspace).as_posix(),
            artifact_kind=kind,
            observations={"source_name": source.name or "source"},
        )


class HttpProvider:
    name = "http"

    def __init__(self, max_bytes: int = DEFAULT_MAX_HTTP_BYTES, timeout: float = 30.0):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes
        self.timeout = timeout

    def acquire(self, spec: AcquisitionSpec, workspace: Path) -> ProviderResult:
        parsed = urllib.parse.urlparse(spec.locator)
        if parsed.scheme not in HTTP_SCHEMES:
            raise AcquisitionError("http provider accepts only http:// and https://")
        if parsed.username or parsed.password:
            raise AcquisitionError("credentials embedded in HTTP URLs are not allowed")

        request = urllib.request.Request(
            spec.locator,
            headers={"User-Agent": "OKF-Generator/0.1 Stage-01-Acquire"},
        )
        payload = workspace / "payload"
        payload.mkdir()

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                final_url = response.geturl()
                final_parsed = urllib.parse.urlparse(final_url)
                if final_parsed.scheme not in HTTP_SCHEMES:
                    raise AcquisitionError("HTTP redirect ended on a non-HTTP(S) URL")

                filename = Path(urllib.parse.unquote(final_parsed.path)).name
                filename = filename if filename not in {"", ".", ".."} else "response.bin"
                dest = payload / filename

                total = 0
                with dest.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise AcquisitionError(
                                f"HTTP response exceeds max_bytes={self.max_bytes}"
                            )
                        handle.write(chunk)

                observations = {
                    "final_url": final_url,
                    "status": getattr(response, "status", None),
                    "content_type": response.headers.get("Content-Type"),
                    "content_length": response.headers.get("Content-Length"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except AcquisitionError:
            raise
        except Exception as exc:
            raise AcquisitionError(f"HTTP acquisition failed: {exc}") from exc

        return ProviderResult(
            artifact_path=dest.relative_to(workspace).as_posix(),
            artifact_kind="file",
            observations={key: value for key, value in observations.items() if value is not None},
        )


def _normalize_git_locator(locator: str) -> str:
    normalized = locator[4:] if locator.startswith("git+") else locator
    if normalized.startswith("ext::"):
        raise AcquisitionError("git ext:: transport is not allowed")

    if re.match(r"^[^/@\s]+@[^:\s]+:.+", normalized):
        return normalized

    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme and parsed.scheme not in HTTP_SCHEMES | GIT_SCHEMES:
        raise AcquisitionError(f"unsupported git transport: {parsed.scheme}")
    return normalized


class GitProvider:
    name = "git"

    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout

    def _run(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
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
            return subprocess.run(
                args,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise AcquisitionError("git executable is required for git acquisition") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "git command failed").strip()
            raise AcquisitionError(detail) from exc
        except subprocess.TimeoutExpired as exc:
            raise AcquisitionError("git acquisition timed out") from exc

    def acquire(self, spec: AcquisitionSpec, workspace: Path) -> ProviderResult:
        locator = _normalize_git_locator(spec.locator)
        payload = workspace / "payload"
        payload.mkdir()
        repo = payload / "repository.git"

        self._run(["git", "clone", "--bare", "--", locator, str(repo)])
        if spec.ref:
            self._run(
                ["git", "rev-parse", "--verify", "--end-of-options", f"{spec.ref}^{{commit}}"],
                cwd=repo,
            )

        observations: dict[str, Any] = {"bare": True}
        if spec.ref:
            observations["requested_ref_present"] = True

        return ProviderResult(
            artifact_path=repo.relative_to(workspace).as_posix(),
            artifact_kind="bare-git-repository",
            observations=observations,
        )


class AcquisitionEngine:
    def __init__(
        self,
        output_root: Path | str,
        *,
        max_http_bytes: int = DEFAULT_MAX_HTTP_BYTES,
        clock: Callable[[], datetime] = _utc_now,
        providers: Mapping[str, AcquisitionProvider] | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.clock = clock
        self.providers: dict[str, AcquisitionProvider] = (
            dict(providers)
            if providers is not None
            else {
                "local": LocalProvider(self.output_root),
                "http": HttpProvider(max_bytes=max_http_bytes),
                "git": GitProvider(),
            }
        )

    def acquire(self, spec: AcquisitionSpec, *, replace: bool = False) -> AcquisitionReceipt:
        spec.validate()
        provider_name = infer_provider(spec.locator) if spec.provider == "auto" else spec.provider
        if spec.ref and provider_name != "git":
            raise AcquisitionError("ref is only valid for git acquisition")
        provider = self.providers.get(provider_name)
        if provider is None:
            raise AcquisitionError(f"provider not registered: {provider_name}")

        self.output_root.mkdir(parents=True, exist_ok=True)
        final_dir = self.output_root / spec.source_id
        if final_dir.exists() and not replace:
            raise AcquisitionError(
                f"acquisition already exists for {spec.source_id}; use replace=True intentionally"
            )

        temp_dir = Path(
            tempfile.mkdtemp(prefix=f".{spec.source_id}.", suffix=".tmp", dir=self.output_root)
        )
        backup_dir: Path | None = None
        try:
            result = provider.acquire(spec, temp_dir)
            acquired_at = self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            receipt = AcquisitionReceipt(
                schema_version="0.1",
                stage="01-acquire",
                source_id=spec.source_id,
                provider=provider_name,
                locator=spec.locator,
                requested_ref=spec.ref,
                acquired_at=acquired_at,
                artifact={"path": result.artifact_path, "kind": result.artifact_kind},
                observations=dict(result.observations),
            )
            (temp_dir / "receipt.json").write_text(receipt.to_json(), encoding="utf-8")

            if final_dir.exists():
                backup_dir = self.output_root / f".{spec.source_id}.{uuid.uuid4().hex}.backup"
                os.replace(final_dir, backup_dir)
            try:
                os.replace(temp_dir, final_dir)
            except Exception:
                if backup_dir is not None and backup_dir.exists():
                    os.replace(backup_dir, final_dir)
                raise
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir)
            return receipt
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise


def load_receipt(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
