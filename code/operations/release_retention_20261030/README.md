# E4 outcome retention utility

This staged utility manages only already-published result ZIPs from
`S-G-mathematics/lamost-six-experiments` release
`results-2026-10-28`. It uses the existing `gh` CLI and
never prints command output that could contain credentials.

`plan` reads the release manifest, registry records, validation JSON,
and filesystem metadata. It does not hash native array payloads. Strict
single-link eligibility requires a successful, validated, non-control E4
evaluation, exact saved validation binding, no registry consumer, a regular
native file with one link, and no aliases. The separately reported
complete-known-inode groups require every canonical/attempt pathname to be a
successful same-task E4 outcome, the same inode and bytes, and an exact
enumerated link count. They are marked review-only in the plan. Retiring those
groups additionally requires `--include-groups` and a root approval
JSON with `allow_complete_known_groups=true`. The plan target defaults to 2 GiB and accepts an explicit target up to 4 GiB; the
release-asset cache remains limited to one asset of at most 1 GiB.

Before download or restore, the utility requires the root-owned
`runtime_20261025/finalize.lock` guardian lock, obtains and retains
`locks/cold_auto_compaction.lock` and `batch-wrapper.lock`,
creates its own exclusive `ADMISSION_HOLD.json`, and checks controller
PID/start-ticks/UID/source identity. It waits at most 690 seconds for already
running scientific workers to drain while the hold blocks new admissions;
worker task/attempt/request/result, PID/start-ticks/UID, argv, and frozen
worker-source SHA must match. It never stops a worker. Foreign storage/audit
processes, identity mismatches, and timeout fail closed; timeout removes only
the utility's own hold. Retirement enforces the 20 GiB disk floor. Each asset is at most 1 GiB in the project cache; the cache holds
one asset at a time. Whole-asset SHA, ZIP member uniqueness/modes and CRC are
verified once per stable asset, then each selected member's CRC, size and SHA
are verified against the native file and saved validation before any unlink.
The durable index is written before each unlink.

`restore` verifies or re-downloads each exact release asset and
streams original members to same-directory temporary files. It preserves
inode groups as hardlinks, original file mode and paths, refuses symlinks or
conflicts, fsyncs before atomic publication, and clears the restore-required
marker only after every entry is present. For the terminal-time 6 GiB
finalization reserve, use `--disk-floor 6442450944` only after the
guardian has proved all planned cases terminal and no workers remain.

## Current read-only plan

The metadata-only plan found 1,520 E4 outcome rows (3,972,192,639 bytes);
21 are controls and excluded. The 1,499 successful non-control rows
(3,862,033,862 bytes) all have native link count 2 and one recorded attempt
alias. Thus the strict single-link set is empty. The first 752 complete,
verified-by-metadata inode groups total 2,146,893,717 bytes under the
2 GiB target. They remain review-only; no GitHub assets were downloaded and no
native outcomes were retired.

## Commands

Read-only plan:
```sh
ROOT=/home/ubuntu/lamost_e1_migration_20261023
python3 "$ROOT/operations/release_retention_20261030/release_retention.py" plan   --root "$ROOT"   --manifest "$ROOT/github_release_results_20261028/release_manifest.json"   --registry "$ROOT/runtime_20261025/registry.sqlite"   --target-bytes 2147483648   --output "$ROOT/operations/release_retention_20261030/ACTUAL_METADATA_PLAN.json"
```

Retirement requires root's separately held guardian and an approval file bound
to the exact plan SHA. Do not use `--execute` until root authorizes it.
Restore command is `restore --root ROOT --state INDEX --cache CACHE
--repo S-G-mathematics/lamost-six-experiments --tag results-2026-10-28`;
default disk floor is 20 GiB.
