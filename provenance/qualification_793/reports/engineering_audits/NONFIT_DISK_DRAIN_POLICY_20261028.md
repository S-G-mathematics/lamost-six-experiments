# Staged E4/E5 non-fit disk drain

**Status:** staged only; not deployed.  
**Observed:** 2026-10-28T07:17:04.697421+00:00

## Purpose and limits

This staged controller change addresses a deadlock pattern in which a storage forecast can block already-fitted E4/E5 evaluation outputs, while archive completion waits for those outputs. The ordinary storage admission gate remains unchanged. The fallback is restricted to ready, never-attempted random-forest or ExtraTrees evaluations with validated matching fits and physical model files, plus E5 clean evaluation aliases that refer to the matching E4 control result.

It admits no fits, generations, tuning trials, retries, or model serialization. It blocks if any active task is not itself one of the same narrow evaluation/alias tasks, if an archive operation is active or blocked, or if an operator admission hold exists. It keeps the original 20 GiB free-space floor and reserves 2 GiB for every active plus proposed drain task. The existing CPU/RAM admission and process supervision remain authoritative.

The controller verifies task, fit, validation-manifest and physical pipeline identities. It rejects symlinks and out-of-root artifact paths, hashes physical pipeline files in 4 MiB chunks without loading them, and records drain evidence in the admitted attempt resource profile. It walks candidates in the existing ready order and hashes at most the selected eligible pipeline in a scheduler pass.

## Output-size rationale

The existing bounded E4/E5 RF/ExtraTrees inventory recorded 302 successful evaluation outputs. The largest test_outcomes.npz was **1,677,742 bytes**; the largest checked alias JSON was **2,805 bytes**. The evaluation writer in source/science.py writes compressed row outcomes to a temporary file and atomically replaces the final file; it does not serialize a model. The 2 GiB per-task output reserve is over 1,200 times that observed maximum. A separate source-based calculation for a 500,000-row output gives 20 payload bytes per row across six arrays (10,000,000 raw bytes); the 2 GiB reserve is over 214 times that payload before NPZ metadata or compression. This scoped calculation is not a bound for larger future row counts. This is a practical reserve based on observed outputs, not a formal upper bound. The 20 GiB hard floor remains in place.

## Staged verification

The staged controller is based on live controller SHA **9caa7afd4c910e52e89cbb1e34370d0a3025fb8bb31b643cf809e9500f8990ba**. The staged controller SHA is **b2a16a7c48708eddfa9bb0807c08b1d08e5ce87ce3d6cec95a1b61077fd15c61**. The focused test SHA is **7f4a16d560a78e85f8e58cdd07222c939badd76c860990dc0501828e23a97abf**.

The guarded test run passed **8/8** in **0.224 seconds**, with peak process-tree RSS **37,801,984 bytes** under a 1 GiB cap. Preflight at 2026-10-28T07:16:06.375181+00:00 observed **30,308,560 KiB** MemAvailable and **35,613,855,744 bytes** free on the project filesystem. The test log SHA-256 is **0ec0f6e1320b6e617200c6e810bbab902cb6ede4f6238aecc984fa5a366dc6b2**.

Tests cover eligible fit-backed E4/E5 evaluations, E5 clean aliases, failed or missing dependency rejection, path and hash checks, attempted-task exclusion, active fit/generation/archive/hold denial, disk reserve arithmetic, and exact equality of the staged and live storage_allow() function source.

## Review boundary

This is an engineering stage only. No live controller files or task registry were changed, and no task was launched. The test suite uses small fake metadata/artifacts and does not validate a live scientific admission. Root must review and decide whether to integrate this staged patch.
