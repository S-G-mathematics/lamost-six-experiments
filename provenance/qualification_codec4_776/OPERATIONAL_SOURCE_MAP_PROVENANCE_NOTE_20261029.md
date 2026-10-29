# Operational source map provenance note

Observed UTC: 2026-10-29T06:23:01.699062+00:00

Candidate fingerprint: `215ed70ad2889bc6bebdd4f41105c49cf619dbc25971e4c8e9165b88e5257cfa`

freeze.operational_source_sha256 is the inherited ET770 baseline map used to record the amendment delta. It is not the authoritative current operational source map and must not be represented as current deployed-file hashes. The publisher checks its stable key set and expected delta; no runtime Python consumer reads this field. Current exact source identities are the policy/qdoc and PINS maps below, plus the explicit current worker reaper pointer. Historical freeze bytes remain unchanged.

## Inherited freeze baseline versus current files

| File | Inherited freeze value | Current file SHA-256 |
|---|---|---|
| `cold_auto_compaction.py` | `06addb644df2101c51dbd59beb822f6f5955b7131892f0c9ccdfa95ab9c30488` | `147a0a23c9fd5d9d6d98f5aae76a806bca89548b806b73f43d68019f4f340202` |
| `cold_model_storage.py` | `be06705a14efd458e7aeaa9ad0e5fc60ba95bbeb325a60e255a65602f2f7b172` | `be06705a14efd458e7aeaa9ad0e5fc60ba95bbeb325a60e255a65602f2f7b172` |
| `commit_batch_child.py` | `b719bac52e73fe9e52193b837415fb8617c3cc51d84d3497c0c05b7033beeee0` | `04eb0b0cd873396d9ce92dc8a8cd164a4a012b1eb1ef9aa5f35e0f2ffc55de46` |
| `run_batch.py` | `c2469d383d6b2982edb829cb0c956a72b760a6430374e6057e6a40568b6b5af3` | `8fe0e1b975d589a52dd3659b5c817d6192d47289a3566f1519f1a13ddf43873f` |

## Current authoritative maps

- Codec4 policy: `manifests/ARCHIVE_NATIVE_CODEC4_FIT_OVERLAP_20261029.json` SHA `5f24011571ac94024988496ca16f31c4aef2822c80a3f9078d3ebd66a8815f28`; source map is embedded in the policy and qualification document.
- Reaper source pointer: freeze `worker_reaper_source_sha256` matches `archive_fit_admission.py` current SHA.
- Current `cold_auto_compaction.py` and `run_batch.py` source pins are embedded in their `PINS`/`SOURCE_PINS` constants and match the codec4 policy source map.
- Scientific freeze source map remains exactly 19 files; task plan SHA and 6,270 task definitions are unchanged.

This supplemental note is outside the portable test fingerprint and does not alter the historical freeze or qualification result.
