# Stage 02 — Snapshot

Stage 02 converts an ephemeral Stage 01 acquisition into an immutable, content-addressed source version. It fingerprints acquired material, locks provider-specific version identity where one exists, copies the payload into immutable snapshot storage, and records enough integrity data to detect later mutation.

## Boundary

Stage 02 is deterministic and non-semantic.

- **Allowed:** SHA-256 hashing, canonical filesystem inventory, immutable copying, Git object/ref resolution, integrity verification, and acquisition-receipt preservation.
- **Forbidden:** media classification, parsing, text extraction, normalization, crawling, semantic deduplication, concept generation, provenance interpretation, or OKF serialization.

Stage 02 does not decide what a source *means*. It decides exactly which source version later stages are allowed to mean.

## Input

The input is one completed Stage 01 acquisition:

```text
.okf-generator/acquired/<source-id>/
  receipt.json
  payload/
    ...
```

The Stage 01 receipt must identify the same `<source-id>` and a safe artifact path inside that acquisition directory.

## Snapshot storage

Snapshots are append-only and content-addressed:

```text
.okf-generator/snapshots/<source-id>/sha256-<identity>/
  snapshot.json
  acquisition-receipt.json
  integrity.json
  payload/
    ... preserved source version ...
```

There is no `--replace` operation. A new source version gets a new identity and coexists with previous versions. Repeating Stage 02 for an already snapshotted version verifies the existing object and returns it as an idempotent no-op. If an existing snapshot has been modified, Stage 02 fails instead of repairing or replacing it.

## Canonical filesystem fingerprint

For ordinary file, directory, and symlink acquisitions, the snapshot identity is SHA-256 over a canonical entry stream (`canonical-filesystem-v1`). The stream includes:

- relative path and entry kind;
- file size, SHA-256 content digest, and portable executable-bit state;
- empty directories;
- symlink target text without dereferencing the target.

It intentionally excludes volatile host metadata such as mtime, uid/gid, and non-executable permission bits. This keeps the version identity stable across faithful copies while retaining source semantics that can affect execution.

Special filesystem entries such as devices, sockets, and FIFOs are rejected rather than silently transformed.

## Git version locking

A bare Git acquisition is treated differently because packfiles and repository housekeeping are storage representations rather than the source version itself.

Stage 02 resolves the requested Stage 01 ref, or `HEAD` when no ref was requested, and records:

- Git object format (`sha1` or `sha256`);
- selected ref label;
- selected raw object ID and object type;
- peeled commit ID.

Including the raw selected object preserves the identity of an annotated tag instead of reducing every tag to only its commit. The canonical snapshot identity is SHA-256 over this Git object-lock descriptor (`git-object-lock-v1`). The copied bare repository also receives a separate canonical filesystem storage fingerprint so mutation of the stored representation can be detected.

Later stages must consume the locked Git object/commit recorded in `snapshot.json`, not re-resolve mutable branch names.

## Acquisition provenance

The exact Stage 01 `receipt.json` bytes are preserved as `acquisition-receipt.json`, and `snapshot.json` records their SHA-256 digest. The acquisition receipt is provenance for how the bytes arrived; it does not participate in ordinary content identity. Re-acquiring identical bytes at a later time therefore does not manufacture a new source version.

## CLI

```bash
okf-generator snapshot paper
okf-generator snapshot code --acquired-root .okf-generator/acquired --out .okf-generator/snapshots
```

The command prints `snapshot.json` to stdout.

## Tool decision

No new third-party tool is required at this stage. Python's standard-library hashing and filesystem primitives implement ordinary snapshots. The existing Git CLI dependency is reused only to resolve and verify Git object identity. Cryptographic signing/issuer attestation is a packaging/trust concern and remains outside Stage 02.

## Completion tests

Stage 02 is complete when:

- ordinary source versions receive stable SHA-256 identities;
- volatile timestamps do not change identity, while executable-bit changes do;
- empty directories and symlink targets participate in identity;
- snapshots never dereference symlinks silently;
- previous versions coexist and are never overwritten;
- repeating an identical snapshot is idempotent;
- mutation of a published snapshot is detected;
- acquisition receipts are retained and integrity-checked;
- Git refs are locked to immutable object and commit IDs, including annotated tags;
- copied payload integrity is verified before publication;
- no Stage 03 classification or Stage 04 extraction behavior is introduced.
