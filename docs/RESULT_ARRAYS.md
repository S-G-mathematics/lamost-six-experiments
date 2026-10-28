# Scientific result-array delivery

[Download the verified result release](https://github.com/S-G-mathematics/lamost-six-experiments/releases/tag/results-2026-10-28).

The release contains 19 ZIP assets, 7,247,229,269 bytes, 4,455 member records and 3,688 additional alias paths. Every ZIP passed CRC validation; GitHub reports matching SHA-256 and byte size for every asset. The member manifest distinguishes historical and non-primary provenance. These are all available selected scientific result arrays, not missing historical artifacts or unfinished evaluations.

| Category | Unique member records | Source bytes |
|---|---:|---:|
| e1 predictions | 80 | 989,357,891 |
| e1 recovery predictions | 24 | 305,157,225 |
| e1 recovery roles | 106 | 24,376,826 |
| e1 roles | 180 | 118,292,294 |
| e2 fidelity diagnostic samples | 1,596 | 90,470,391 |
| e2 reference ids | 210 | 697,576 |
| e5 corruption audits | 27 | 3,064,554 |
| runtime historical outcomes | 18 | 28,388,604 |
| runtime roles | 3 | 8,149,413 |
| runtime test outcomes | 2,205 | 5,707,227,131 |
| runtime tuning posteriors | 6 | 16,190,966 |

Download release_manifest.json for member SHA-256 hashes and aliases; SHA256SUMS.txt contains archive hashes. Run sha256sum -c SHA256SUMS.txt after downloading all listed files. Each ZIP contains paths relative to the EC2 migration root; extract only into a new empty directory. Aliases identify identical content without redundant archive payloads.

E2 fidelity diagnostic samples and E5 corruption realizations are included. Fitted models, FITS, raw baseline matrices and generated downstream training datasets are excluded. Historical E1 arrays absent from EC2 cannot be restored by this release.

The array manifest binds to the initial audited code/report snapshot at commit 79ae75b8b2b01890f4771697cc18374f7d2e9198 (manifest f4b0940648604dda466f352c2dc7f5ce5c2f7d9e0b3bfe044f606c796a8897c3). Later documentation commits do not change those scientific results.


## Incremental outcomes staged after the base release

An additional E4 delta is staged at github_delta_results_20261028/e4_three_validated_cells_20261028T084431Z/e4_three_validated_outcomes_delta.zip. It contains two unique arrays for three validated records (the E5 direct Extra Trees clean record aliases the E4 rep-3 control). ZIP CRC passed; the ZIP is 3144012 bytes with SHA-256 49d94bba6fc13f4d4f56b10332e0410701e5a3e3d247ec1db37df772388c54a5. The archive and uniquely named manifest, README and checksum sidecars are uploaded to the existing GitHub Release results-2026-10-28. Remote downloads were compared byte-for-byte with the staged files; the verification receipt is metadata/E4_DELTA_RELEASE_UPLOAD_VERIFICATION_20261028.json. Its task-level manifest is linked from the incremental E4/E5 results supplement.
