from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os

MAX_INITIAL_BYTES = 1 << 30
MAX_INITIAL_GROUPS = 8
MAX_LATER_BYTES = 2 << 30
MAX_LATER_GROUPS = 16
RAW_WIDE_MAX_BYTES = 8 << 30
RAW_WIDE_MAX_GROUPS = 64
RAW_WIDE_PROFILE = "bounded-1800-wide8gib"
RAW_WIDE_TRANSIENT_DISK_RESERVE_BYTES = 6 << 30
RAW_MIXED_SMALL_MAX_BYTES = 4 << 30
RAW_MIXED_SMALL_MAX_GROUPS = 2048
RAW_MIXED_SMALL_PROFILE = "bounded-1800-mixedsmall4gib2048"
RAW_MIXED_SMALL_TRANSIENT_DISK_RESERVE_BYTES = 6 << 30
RAW_ARCHIVE_IO_PROFILES = (RAW_WIDE_PROFILE, RAW_MIXED_SMALL_PROFILE)
ARCHIVABLE_FIT_METHODS = frozenset(['arf', 'cart', 'chow_liu', 'copula', 'extra_trees', 'gaussian_nb', 'gmm', 'hist_gb', 'kde', 'knn', 'lda', 'linear_svm', 'logistic', 'qda', 'random_forest', 'rbf_svm', 'shared_diagonal'])


def _terminal_success(task: dict[str, Any]) -> bool:
    return (task.get("status") == "validated_terminal" and
            task.get("outcome") == "successful" and
            task.get("validation_state") == "validated")


def _alias_owner(alias: str, records: dict[str, dict[str, Any]]) -> str | None:
    for key, row in records.items():
        base = f"runtime_20261025/artifacts/{key}"
        if alias == f"{base}/pipeline.joblib":
            return key
        result = row.get("result") or {}
        attempt_id = result.get("attempt_id")
        task_sha = result.get("task_sha256")
        if attempt_id and alias == f"{base}/attempts/{attempt_id}/pipeline.joblib":
            return key
        if task_sha and alias == f"{base}/checkpoints/{task_sha}/pipeline.joblib":
            return key
    return None


def build_candidates(root: Path, runtime: Path, records: dict[str, dict[str, Any]],
                     existing_members: set[str], safety: Any, cold: Any, *, packing: str = "smallest_first") -> list[dict[str, Any]]:
    """Build metadata-only candidates from one artifact walk; core rechecks every gate and SHA."""
    art_root = runtime / "artifacts"
    groups: dict[tuple[int, int], dict[str, Any]] = {}
    for current, dirs, files in os.walk(art_root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
        if "pipeline.joblib" not in files:
            continue
        p = Path(current) / "pipeline.joblib"
        try:
            st = p.lstat()
        except FileNotFoundError:
            continue
        if not p.is_file() or p.is_symlink():
            continue
        ident = (st.st_dev, st.st_ino)
        rel = p.relative_to(root).as_posix()
        group = groups.setdefault(ident, {"bytes": st.st_size, "nlink": st.st_nlink, "aliases": [], "identity": ident})
        if group["bytes"] != st.st_size or group["nlink"] != st.st_nlink:
            raise RuntimeError("inconsistent inode metadata during candidate walk")
        group["aliases"].append(rel)

    out = []
    for group in groups.values():
        aliases = sorted(group["aliases"])
        # Unknown/external hardlinks are never considered for a batch.
        if group["nlink"] != len(aliases):
            continue
        owners = [_alias_owner(a, records) for a in aliases]
        if any(k is None for k in owners):
            continue
        owner_keys = sorted(set(owners))
        owner_rows = [records[k] for k in owner_keys]
        if any(not _terminal_success(t) or t.get("kind") != "fit" or
               t.get("method") not in ARCHIVABLE_FIT_METHODS or int(t.get("experiment", 0)) not in (3, 4, 5, 6)
               for t in owner_rows):
            continue
        closures = {k: sorted(cold._consumer_closure(k, records)) for k in owner_keys}
        metadata_contract = None
        if any(any(records.get(c, {}).get("status") != "validated_terminal" for c in closure)
               for closure in closures.values()):
            # Keep the original one-producer v1 binding byte-for-byte; every
            # other pending closure uses the separately pinned v2 contract.
            if len(owner_keys) != 1:
                continue
            producer_key = owner_keys[0]
            try:
                if producer_key == "e3/rep_2/fit/synthetic/random_forest/copula":
                    import metadata_only_contract as contract_module
                    import hashlib
                    module_path=Path(contract_module.__file__)
                    if hashlib.sha256(module_path.read_bytes()).hexdigest()!="1d4e9f78bf3b0062effb3bc218fb5135aae0dba2375b2602773d21bf49d333a1":
                        continue
                    metadata_contract = contract_module.build_contract(root, producer_key, records, closures[producer_key])
                else:
                    import metadata_access_contract_v2 as contract_module
                    import hashlib
                    module_path=Path(contract_module.__file__)
                    if hashlib.sha256(module_path.read_bytes()).hexdigest()!='3cf04ce36ba65b70b5ee68bf82aecf18ae405948c3cc36b5a7c678439b6d5bf8':
                        continue
                    metadata_contract = contract_module.build_contract(root, producer_key, records, closures[producer_key])
            except Exception:
                continue
        # Canonical paths determine a producer. Attempt/checkpoint-only orphan groups fail closed.
        canonical = [k for k in owner_keys if f"runtime_20261025/artifacts/{k}/pipeline.joblib" in aliases]
        if not canonical:
            continue
        producer = canonical[0]
        logical = f"runtime_20261025/artifacts/{producer}/pipeline.joblib"
        if logical in existing_members:
            continue
        row = records[producer]
        try:
            digest = cold._pipeline_hash(row)
        except Exception:
            continue
        out.append({
            "producer_task": producer,
            "method": row.get("method"),
            "source_relpath": logical,
            "source_path": logical,
            "archive_member": logical,
            "source_sha256": digest,
            "recorded_artifact_sha256": digest,
            "aliases": aliases,
            "consumer_tasks": closures[producer],
            **({"metadata_only_consumer_contract": metadata_contract} if metadata_contract else {}),
            "bytes": int(group["bytes"]),
            "inode_identity": [int(x) for x in group["identity"]],
        })
    # One item per inode group; initial policy remains small-first. Follow-up favors
    # large groups to reduce the number of full-root inode inventory passes.
    if packing == "smallest_first":
        out.sort(key=lambda x: (x["bytes"], x["producer_task"]))
    elif packing == "largest_first":
        out.sort(key=lambda x: (-x["bytes"], x["producer_task"]))
    else:
        raise ValueError("unknown candidate packing policy")
    return out


def select_batch(candidates: list[dict[str, Any]], *, max_bytes: int = MAX_INITIAL_BYTES,
                 max_groups: int = MAX_INITIAL_GROUPS) -> list[dict[str, Any]]:
    if max_bytes <= 0 or max_groups <= 0:
        raise ValueError("positive batch limits required")
    selected: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    total = 0
    for item in candidates:
        ident = tuple(item["inode_identity"])
        if ident in seen:
            raise ValueError("duplicate inode group in candidate input")
        if len(selected) >= max_groups:
            break
        if item["bytes"] > max_bytes - total:
            continue
        selected.append(item)
        seen.add(ident)
        total += item["bytes"]
    return selected


def public_candidate_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"candidate_count": len(items), "source_bytes": sum(int(x["bytes"]) for x in items),
            "producer_keys": [x["producer_task"] for x in items],
            "inode_group_count": len({tuple(x["inode_identity"]) for x in items})}


def require_reviewed_baseline(archive: Path, manifest: dict[str, Any], reviewed_sha256: str, sha256_file: Any) -> str:
    """Fail closed unless a regular existing archive matches explicit review and manifest."""
    expected = reviewed_sha256.lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("explicit 64-hex reviewed baseline SHA required")
    if archive.is_symlink() or not archive.is_file():
        raise RuntimeError("existing regular archive required; do not initialize or adopt")
    if not isinstance(manifest, dict) or manifest.get("archive_sha256") != expected:
        raise RuntimeError("manifest does not match explicit reviewed baseline")
    if sha256_file(archive) != expected:
        raise RuntimeError("archive does not match explicit reviewed baseline")
    return expected


def resource_admission_ready(unresolved_count: int, available_bytes: int, commitments: list[Any],
                             helper_reservation_bytes: int, memory_admission_ok: Any) -> bool:
    """Unknown running owners block; otherwise defer resource math to the pinned controller policy."""
    if unresolved_count != 0:
        return False
    return bool(memory_admission_ok(available_bytes, commitments, helper_reservation_bytes))


def validate_operation_directory(op: Path, runs: Path, operation_id: str,
                                 allowed_parent_files: set[str], child_owned_files: set[str]) -> None:
    """Accept only an empty unique run dir or its known supervisor-owned regular files."""
    op = op.resolve(strict=True); runs = runs.resolve(strict=True)
    try: op.relative_to(runs)
    except ValueError as exc: raise RuntimeError("operation directory escapes runs root") from exc
    if op.name != operation_id or not operation_id or operation_id in (".", ".."):
        raise RuntimeError("operation directory identity mismatch")
    for entry in op.iterdir():
        if entry.name in child_owned_files:
            raise RuntimeError("child-owned output already exists; refuse overwrite: " + entry.name)
        if entry.name not in allowed_parent_files or entry.is_symlink() or not entry.is_file():
            raise RuntimeError("unknown or non-regular operation-directory entry: " + entry.name)


def verify_alias_resolution(root: Path, resolver: Any, items: list[dict[str, Any]]) -> None:
    """Check every committed source alias has been removed physically and resolves by exact SHA."""
    for item in items:
        expected = item["sha256"]
        for alias in item["aliases"]:
            physical = root / alias
            if physical.exists() or physical.is_symlink():
                raise RuntimeError("post-commit physical alias remains: " + alias)
            if resolver.sha256(alias, expected_sha256=expected) != expected:
                raise RuntimeError("post-commit resolver SHA mismatch: " + alias)
