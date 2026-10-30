# LAMOST six-experiment work report — 30 October 2026

Observed 2026-10-30 14:48:48 IST / 2026-10-30 09:18:48 UTC. **The project is not complete. Fourteen E5 evaluations remain pending.** This report distinguishes scientific outcomes, saved-artifact verification, operational work and delivery.

## Actual experiment state

| Experiment | Planned | Successful or evaluated | Scientific failures | Unsupported / unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen |765|674|81|10 unsupported|0|0|
| E2 primary |150|108 evaluated|0 new failures|42 unavailable|0|0 scheduled|
| E2 classical references |120|120 evaluated|0|0|0|0|
| E3 |69|64|3|2 unavailable|0|0|
| E4 |1773|1632|71|3 unavailable|67|0|
| E5 |960|717|50|78 unavailable|101|14|
| E6 member references |15|12 aliases|0|3 unavailable|0|0|
| E6 primary ensembles |6|0|3|3 unavailable|0|0|

E1's 81 failures include 55 resource failures and 26 supervisor-terminal cases whose detailed manifests remained “started.” The 10 unsupported cases are separate. Its 765-cell ledger was preserved; no E1 fits, retries or test inference were launched.

The separate stopped E1 recovery supplement remains 91 rows:24 successful retries,10 retry failures,2 user-stopped partial cells and55 not attempted. It remains stopped early and does not replace frozen E1.

The current later-experiment DAG has6243 of6270 tasks validated terminal, with27 waiting:13 E5 fits and14 E5 evaluations. No pending cell has been relabeled a scientific failure. The original2823 E3–E6 scientific-case denominator remains. The score-independent repetition amendment stopped168 scientific rows within334 other nonterminal DAG tasks; its retained prerequisite closure was167 tasks (77 already successful and90 pending for45 selected evaluations).

## Work completed and evidence preserved

### Frozen E1 and E2

The E1 and E2 saved tables were independently checked:all153 E1 method-budget groups matched their source arithmetic; E2's270 planned rows,228 evaluated cells and1596 class reports matched. Equal-class aggregation,210 low-precision flags and four complete five-family within-budget/repetition correlations were retained. No additional E1 or E2 fitting was performed.

Three final-ledger E1 learning curves were produced for balanced accuracy, conformal coverage and set size. They show means and sample SD conditional on success, actual n/5 for partial groups and explicit missing groups. Their full-resolution visual review passed. E1's100k budget remains67 successful and18 failed.

E2 remains108/150 primary evaluations, with42 missing ARF/KDE selected-fit dependencies, plus120/120 classical references. Original and reconstructed provenance stays distinct:43 original and185 reconstructed across both sets;31 reconstruction balanced-accuracy differences remain disclosed. The210 precision flags are preserved. The four complete five-family strata have descriptive Spearman values0.7,0.1,0.3,0.7; no general relationship or significance claim is made.

### Later-experiment results and reporting

E3's shared-real pairing table was corrected from stale availability accounting. Current matched counts are36/45 direct-versus-real,43/45 synthetic-versus-real and35/45 direct-versus-synthetic. Thirty-seven previously blank pairs were restored; existing paired balanced-accuracy values did not change. The GMM/synthetic-RF group has2/3 successful repetitions. Corrected E3 figures and E6 figures were reviewed.

E4 is fully accounted under the repetition amendment. Its descriptive paired tables cover910 strata:238 direct altered-versus-control strata and336 each for treatment-versus-control and treatment-versus-untreated. The respective matched repetition totals are600,969,969. Findings remain target-, severity- and learner-specific.

All717 saved E5 evaluation summaries were checked against their ledger bindings:5019 class rows and35133 confusion-matrix cells, with seven classes,10000 calibration rows and500000 test rows per evaluated case. This metadata/saved-summary check is not final calibration-threshold replay.

E6 has zero successful primary ensemble evaluations. Twelve member-reference aliases are available; three KDE references are unavailable. All three equal-weight primary test phases timed out and three learned-weight routes remain unavailable after their shared test phase. No ensemble superiority claim is made.

### Saved artifacts and storage operations

All2322 catalogued available later-experiment payload paths now have exact published member SHA-256, byte-size and CRC evidence. This includes canonical E3=64, E4=1611, E5=629 unique payload paths plus supplemental paths; aliases explain why payload counts differ from successful evaluation rows. It does not imply all planned cases were evaluated.

Seventeen E5 metadata entries missing from the prior Git ledger were synchronized. Thirteen arrays already had exact published matches; four were uploaded in a verified6.22MB result-array ZIP. A separate104-array gap-fill ZIP of163660895 bytes closed incomplete per-member backup evidence. Its remote download and all104 member checks passed. No fitted models or raw training datasets were uploaded.

The original1499 temporarily retired E4 groups (3862033862 source bytes) were restored from their verified release assets. Full native byte SHA and hard-link topology checks passed. The original retention index SHA3b0fe7d68da01760e2a3932e4627c94a91ea4fd2fac5711086028e9c87bdda2b was preserved in history; the fully restored clone was promoted transparently to index SHAda49e37819631b32748ccea7efdfcc59aef7172b46df002b45674d3547666c4e with restore_required=false. This was a separately documented maintenance restoration while27 scientific tasks remained pending; it does not claim the old normal terminal-only restoration gate passed.

The old temporary guardian was stopped only after all1499 groups were natively verified and its index was safe. The controller was restarted durably and its real process identity verified. Only the owned maintenance barriers were removed. No scientific worker was interrupted or scientific result reclassified.

The live codec12 operational bundle passed830 tests with zero skips and105 subtests; its354-path source/test/resource-proof deployment closure was checked. The storage wire-field repair did not change scientific algorithms, roles, seeds or model limits. A Go GitHub CLI network failure under a1GiB virtual-address cap was diagnosed; the restoration-only wrapper used4GiB address space, one Go/native thread and disabled core dumps. Later scientific limits stayed600 seconds and10GiB; frozen E1 remains180 seconds and6GiB.

A prospective wider result-retention tool was staged and tested but **not deployed**. Its plan exposed a payload-versus-asset evidence-layout mismatch; it must not be used without repair and review. Even its maximum in-scope cleanup cannot currently clear the existing fitting disk guard. No results were retired by that staged tool.

## Current verified blocker and independent validation

The controller is alive in tmux but has no active model worker. Disk backoff is active. Current free bytes are12920782848 (12.03GiB), below the21474836480-byte (20GiB) fitting guard. Even an idealized upper-bound reclamation of all5862880029 in-scope result bytes, generously rounded up for allocation, would leave at most17.51GiB. This remains below the existing guard and would not reserve later model/output growth.

Cleanup remains confined to LAMOST. Shared pip/uv caches and Harbor were not changed; no EC2 instance or storage was provisioned/resized and no AWS security settings were changed. Waiting work was not called failure or completion.

A supported standalone **evaluation-only incremental saved-result audit** was launched in tmux after checking RAM and actual process inventory. It audits the current successful snapshot and model-artifact integrity; it does not fit models, run new test inference or recompute conformal q. Its current pointer is runtime_20261025/logs/operational/INCREMENTAL_AUDIT_CURRENT_POINTER.json. At launch it was a live verified Python process; check actual processes and its report before claiming a completed audit. Final supervised calibration replay remains behind the all-terminal gate.

## Verified delivery already available

Git repository: https://github.com/S-G-mathematics/lamost-six-experiments

Both main and results/snapshot-2026-10-28 were verified at3b87e4abdaad0f891a24807724d25bd642609041. The code/results snapshot includes current717 E5 evaluation coverage, corrected report tables and figures, the qualified current operational closure, and a sanitized2322-payload availability inventory. Later publication of this progress report may advance those refs; verify them before claiming a newer head.

Readable scientific interim report: reports/interim_20261030T051951Z/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md; SHA256497c381c0326b99eab735ec4e9a073a8101775fe8d4fab10d5486c539aa5452e. Its scientific snapshot is05:19:51UTC and remains correctly labeled interim.

Compact reports-and-tables ZIP:
https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/LAMOST_INTERIM_REPORTS_TABLES_20261030T051951Z.zip

ZIP bytes5554450; SHA25656f608654c7aaf8f681b3e333153afab302856cb081e939c595187126e3b3c45;66 members; CRC verified. EC2 and laptop delivery copies matched. Laptop directory:D:/LAMOST_Overall_EC2_Handoff_20261023/delivery. This is an interim delivery, not the required final project delivery.

The existing full working archive remains:
/home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip
Last committed verified transaction:77623665563 bytes; SHA25610472c825e11645086d2628b1d46191d8644f2b7a608b86f4978fb3e8a46c2b8. It is BUILDING, not a final complete archive. The frozen E1 wrap and original snapshot are preserved.

## Remaining work and limitations

1. Obtain sufficient permitted existing-host disk headroom, then let the single durable controller execute only the13 pending E5 fits and14 evaluations under their recorded policies. Do not launch duplicates or retry terminal scientific failures.
2. Complete all-terminal artifact validation and supervised saved-calibration quantile replay; resolve genuine defects with preserved supersession evidence if discovered.
3. Regenerate final tables/figures and the cross-experiment report with actual repetition counts, matched pairs and coverage alongside set size; perform the exact internal review gate.
4. Create and verify the full EC2 archive and final compact delivery ZIP, transfer the latter, synchronize final Git results, and stop only project-owned workers/watchers.
5. Restore the canonical Git publication checkout and its paused publisher cron before final publication/completion; the current RAM checkout and remote repository are available, and all scientific source/results remain on EC2.

Historical E1 fitted models and per-test predictions omitted from migration were not magically restored. Seven auxiliary tuning-history discrepancies remain. E2 reconstruction differences and precision flags are retained. Timing remains hardware/shared-load dependent. One historical combined engineering-test collection record is unavailable; current830-test evidence remains saved. A superseded predeployment maintenance source version was not retained byte-for-byte; its old SHA/receipt/log were retained, and the actually used maintenance version and current focused proof are available. This affects historical engineering reproducibility, not a new scientific evaluation.

Bootstrap remains dropped. No confidence intervals or significance claims are fabricated. Missing/failed/unsupported cases, repetition cuts and conditional-on-success limitations remain explicit.
