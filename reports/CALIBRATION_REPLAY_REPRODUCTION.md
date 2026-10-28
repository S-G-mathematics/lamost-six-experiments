Installed validation code on existing EC2, 2026-10-26. The engineering fixture counts below describe the reviewed versions; no complete production q replay or qualification is claimed. One saved-LR numerical smoke matched q exactly; its separate engineering supervision was invalidated and is preserved as such. The original staged handoff text follows for provenance.

# Calibration replay finalization gate - staged handoff

Observed on 2026-10-26 17:07 UTC. This staging directory is not deployed and no calibration replay was run.

## Intended deployment files

Copy the following staged versions into the existing runtime_20261025/source/ only after root review:

- finalize_project.py
- final_review.py
- calibration_replay_supervisor.py (new)
- audit_artifacts.py and calibration_replay.py (the paired core versions listed below)

The staged tests are tests/test_calibration_replay_finalization_gate.py and tests/test_calibration_replay_supervisor.py; the other staged tests remain in the directory for the portable combined validation.

## Gate behavior

The artifact auditor writes its immutable q-replay audit with complete=false. The external supervisor launches that auditor with a fresh nonce, checks PID/start ticks, command, UID, process group and descendants, records phase start/finish proof, and writes a sanitized supervision receipt. Finalization accepts q coverage only when the receipt binds the exact audit, registry, ledger, per-fit replay identities, metadata/vector hashes and phase evidence. It writes a separate qualification report; it does not rewrite the auditor's report.

Per scoring fit, elapsed time is limited to 600 seconds. The supervisor samples the auditor process tree's /proc VmRSS every 100 ms, applies a 10 GiB sampled-RSS threshold, sends TERM, waits up to 30 seconds, then uses KILL only after rechecking process identity. This is an external sampled guard, not a kernel/cgroup memory limit: a short RSS spike between samples may go unobserved. The implementation records that measurement method and does not claim hard OS enforcement.

Private beacon and PID/start-tick phase ledger remain under EC2 logs/operational/ and are excluded from public archives. The retained calibration audit includes only the runtime-relative ledger locator and its SHA-256; ledger content is absent. The sanitized receipt and qualification report preserve scientific phase identities, wall times, sampled peak RSS, cap outcome, and ledger digest. Archived proof does not reproduce the private live process-identity check.



## Standalone calibration replay from an extracted archive

The public archive omits the raw private PID/start-tick phase ledger. Its archived receipt and qualification preserve the validated scientific phase measurements and ledger digest, but they cannot rerun the live process-identity check from the archived proof alone. To perform a fresh calibration replay, use an extracted working copy on the existing EC2 and create the exact runtime venv from the archived dependency specification first. Restore aliases from the extraction root with `python3 restore_archive_aliases.py`; do not run this against the original live project or from a laptop.

Before replay, confirm no fitting worker or project finalizer is active, available RAM covers the 10 GiB per-process limit plus the documented host/Harbor reserve, and no other calibration replay owns the working copy. Keep the supplied reports intact by using a separate writable extraction copy. This replay loads saved models and scores the saved calibration cohorts only; it does not fit models or infer on test rows. It does not require the original E1 ZIP or the full project finalizer.

From the extraction root, run this Python snippet with the recreated venv interpreter. It takes an exclusive lock for this working copy, gives the supervisor a fresh nonce, and writes a new audit, private ledger, supervision receipt, and qualification:

```python
from pathlib import Path
import fcntl, secrets, sys

runtime = Path.cwd() / 'runtime_20261025'
sys.path.insert(0, str(runtime / 'source'))
from calibration_replay_supervisor import run
from calibration_replay import write_qualification_report

python = Path(sys.executable)  # the recreated project venv interpreter
script = runtime / 'source' / 'audit_artifacts.py'
nonce = 'archive-' + secrets.token_hex(16)
audit = runtime / 'reports' / 'CALIBRATION_REPLAY_AUDIT.json'
receipt = runtime / 'reports' / 'CALIBRATION_REPLAY_SUPERVISION.json'
qualification = runtime / 'reports' / 'CALIBRATION_REPLAY_QUALIFICATION.json'
ledger = runtime / 'logs' / 'operational' / f'calibration_replay_phase_ledger_{nonce}.jsonl'
lock_path = runtime / 'locks' / 'standalone_calibration_replay.lock'
lock_path.parent.mkdir(parents=True, exist_ok=True)
with lock_path.open('a') as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    run(runtime, python, script, run_nonce=nonce, accepted_prior_index=None)
    write_qualification_report(
        audit, receipt, qualification,
        accepted_prior_receipts=None, phase_ledger_path=ledger,
    )
```

A full successful fresh replay is required for `qualified_complete`; no prior cache receipt is supplied. Failed or unavailable routes remain disclosed and prevent complete q coverage. The private ledger/beacon should remain under `runtime_20261025/logs/operational/`; do not publish those raw files.

## Validation actually run

Using the existing EC2 venv, from this staging directory:

- python -m unittest discover -s tests -p 'test_*.py': 62 passed.
- python source/finalize_project.py --self-test: passed, including ZIP CRC/hash, archive privacy, restoration, report-cache and source-mutation checks.
- python -m py_compile on the five source modules listed below: passed.

These are engineering fixtures only. No production auditor, model load, calibration score replay, full artifact audit, final review, archive creation, or live queue action was run.

## Staged source SHA-256

- source/finalize_project.py: 1afda6c344417bedf41ce3edb1bdd678409cd7edc8dff96d7cd6988d3ebb0601
- source/final_review.py: 16074b11e7325dfa18c1bb5e18dbccc8ff6d8efddfc908214345e1aed67af9f6
- source/calibration_replay_supervisor.py: b44881bf04dabffc9ca4e6cd7249541d2c9a44f128d11f14d3b4aac19bd855b6
- source/audit_artifacts.py: 9a713bf34d7d6115b04ef97d40a69e7d3f86881caf9e2507102011f6c113ccb1
- source/calibration_replay.py: 85c7606b38fe6d0cec39e3c7889e089cc29670195061483e79ca4c49ad1ba6b9
- tests/test_calibration_replay_finalization_gate.py: 3f7d16e7b2ef62477ecf391edc72b44a99c17a3b98e4d820c7e1356e1bb530de
- tests/test_calibration_replay_supervisor.py: bf8b0df9cb4e56ac5f513d716381fff4f83de0babe05fb8d36edb9c231d64c03


## Current installed revision, 27 October 2026 IST
The staged source hashes and old fixture counts above are historical. Current production installation is recorded in engineering_audits/LOSSLESS_STORAGE_AND_GUARD_INSTALLED_20261027.json and LOSSLESS_STORAGE_PRODUCTION_STATUS_20261027.json. The current hash-bound portable suite passed 329 tests and 26 subtests. The full production calibration replay remains pending; no engineering fixture or one-model byte reconstruction qualifies scientific q coverage.

The supervisor now refreshes its monotonic observation after reading the beacon, fixing a deterministically reproduced race while still rejecting genuinely future phase timestamps. It retains PID/start-tick, nonce, exact-command and limits checks.

Archives may contain reversible-xz-v1 encoded model members. Keep current codec-aware source, extracted projection and decoder. The alias restorer intentionally does not expand encoded models into persistent duplicates. The report accessor reconstructs one requested model to a confined temporary file and verifies exact original compressed-joblib bytes before loading. Original logical model SHA/size/CRC and physical encoded SHA/size/CRC are distinct. Runtime decoder compatibility is pinned by descriptor to joblib compressor source identity and zlib 1.3 compile/runtime; recreate the recorded environment, do not silently decode with another implementation. Existing raw members remain readable. Do not blindly restore raw-only readers after an encoded commit.

The first real production encoded pipeline was independently reconstructed to original SHA 6ebb57bf9bcec539e7ab6b6ee784a78d78066b6d43bbea3d96ad2d693075d6ad, without model deserialization or inference. This is a storage proof for one model, not full artifact or calibration qualification.
