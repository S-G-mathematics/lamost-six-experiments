# Current LAMOST execution addendum

Observation 2026-10-27T07:20:32.626517+05:30 Asia/Kolkata; 2026-10-27T01:50:32.626517+00:00 UTC.

This is an interim delivery. E4/E5 remain active and production-wide calibration-threshold replay and final archive qualification are pending. No project-completion claim follows.

| Experiment | Planned | Successful/evaluated | Failed | Unsupported/unavailable | Pending/active |
|---|---:|---:|---:|---:|---:|
| Frozen E1 | 765 | 674 | 81 | 10 | 0 |
| E2 primary | 150 | 108 | 0 | 42 | 0 |
| E2 separate classical | 120 | 120 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1385 | 52 | 3 | 333 |
| E5 | 960 | 652 | 27 | 23 | 258 |
| E6 | 21 | 12 | 0 | 9 | 0 |

E1 remains immutable; its separate stopped recovery is24success10failure2user-stopped55notattempted. E2 reporting is finalized with incomplete primary coverage and all reconstruction/precision/history caveats preserved. E3/E6 have terminal accounting only; final scientific qualification remains pending.

Actual instance i-095641a281a4038b9; controller verified=True; verified scientific workers=4; current controller SHA=3306a15b3d246b7b169880a063ce52032488df3e5bf46c2710d78cae2e85c564. No liveness is inferred from old heartbeat/state files. No E1/E2 fitting, recovery restarts, bootstrap, infrastructure or Harbor changes occurred.

## Newly completed E5 direct-KNN descriptive block

All30/30plannedcells are validated:3cleanaliases to matchingE4controls and27corrupted evaluations. Every one of nine conditions has3matchedrepetitions. Tables include30metrics,27pairedchanges,210classrows,189classpairs,9condition summaries,63class summaries, exactfitprovenance andmatched KNN-versus-RF comparisons. Root independently verified2601arithmetic checks and allthree figures. Global E5saved-calibration q replay remains pending.

At20%affectedfittingrows, KNN mean corrupted-minus-clean changes (n=3) are:

| Corruption | Balanced accuracy change | Coverage change | Set-size change |
|---|---:|---:|---:|
| Feature noise | -0.009613 | -0.000293 | +0.027821 |
| Missingness | -0.006139 | -0.000031 | +0.024659 |
| Label noise | -0.023067 | +0.000125 | +0.494126 |

For20%labelnoise, KNN minus RF paired BA degradation was-0.005758 and set-size increase difference+0.252103, with all3pairedrepetitions retained. These are descriptive comparisons of these pipelines and corruption mechanisms, not significance/CIs or universal superiority. Per-repetition differences andsampleSD are in thetables. The sharedcleancontrol is reused visually across sweep panels, not refitted.

## Frozen identity and current engineering evidence

The fresh frozenE1/E2identitycheck passed, including all19E1sources,765ledger, stoppedrecovery cutoff andacceptedE2documents. The full4,976,984,354-byte E1archive streamedSHA256 matches bd4834a15d491844203ff7baf07b3b21dcdf972de97af68a744d8d2c042e7d34; its original completeCRC receipt remains cryptographically bound to those identicalbytes. No second fullCRC traversal is claimed.

Currentinstalled347tests+36subtests passed on immutable manifestb9273619e98107586dc48deddc1bfeedf6c1e1fe496fa6b3247776b7b4847ccb. Formalreceiptad0d182c9f6b41a459c69de38b2369b0b0fb4fd5371de9e54d575acd546078bb hasSHAd5a4a567a4be0ec8050d3d1ac8ab887a5b2c464ba1d4303c1bbb1f88d73f50c6. Currentrun-outputevidence livesoutside immutableinputmanifest. Earlierpost-runmanifest drift is preserved and explicitly corrected, withoutscientificrefits.

An E4generated-restorationRF memoryreview is complete and a narrow6GiB admissiongate is in isolatedstaging. It is NOT installed at this report cutoff. Existingattempts retain currentprofiles; strict stagedproposal covers only new matchingfits<=125934trainingrows, retaining10GiBhardcap,600spertrial/phase,promotion andhost/growthguards. It is not a newscientificvariant and doesnotchangeE1. SourceauditV1count/sidecar wording was superseded transparently byV2; publishedbytes arepreserved.

The historicalE4tables in thisZIP retain their own earlier1278-success snapshot and explicitdenominators. They are not silently relabeled as current counts. The E4column dictionary clarifies that validation_sha256 is the expected evaluation.json digest inside registryvalidation, not a digest of thereceipt file itself.

## Full archive and remaining work

The mutable BUILDING archive is at /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip. It is not final projectdelivery. Continue theexistingcontroller with storage-aware scheduling; do notlaunch asecondqueue orretryordinaryscientificfailures. FinishE4/E5, complete supervisedglobalartifact/calibration replay, finalfindings/figures/internalreview, verifiedfullandcompactarchives, laptopcopy/hash andexact-ownedshutdown. HistoricalE1pipelines/test-rowarrays omittedfrommigration are not claimed restored; someoriginalfits wereavailableforE2. Bootstrapstaysdropped.
