# Final-only LAMOST GitHub publisher (staged)

This directory contains a proposed one-shot publisher for the final validated research package. It is staged for root review only: it has not been installed, scheduled, or launched, and it has not performed any Git operation.

The publisher waits until the finalizer has accepted the reviewed report, all 6,270 planned scientific tasks are terminal, frozen E1/E2 ledgers match, the full and compact archive receipts bind to the final report, portable qualification inputs still match, and no project controller, generic worker, parallel-RF worker, SVM-margin worker, E6 phase supervisor, or finalizer process is running.

The full archive is not rehashed by this publisher. It checks the finalizer-bound archive path, size, modification time, SHA receipt, CRC pass, receipt identity, and file identity metadata. The compact report ZIP is bounded to 512 MiB and is SHA-256 and CRC checked. Portable qualification checks every listed test and source input; the export includes every qualified runtime Python source in addition to the source-freeze files.

When approved and installed, the one-shot command is:

    python3 /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/source/publish_final.py --publish --remove-owned-cron-on-success

The cron line owned by this publisher must include the unique marker LAMOST_FINAL_GITHUB_PUBLISHER_20261028. On a verified publication, the option removes only crontab lines containing that exact marker. It does not modify any other cron line or systemd unit. Do not install a cron until root has reviewed this staged code and selected the exact user/crontab.

The publisher uses an exclusive nonblocking lock and durable state in runtime_20261025/logs/operational/. Deterministic invalid states latch to the SHA of publisher code and gate inputs; transient Git transport failures use bounded exponential backoff. Fixing code or changing verified inputs allows a fresh gate attempt. It pins the origin to S-G-mathematics/lamost-six-experiments, uses noninteractive Git, commits only explicit allowlisted paths, performs fast-forward pushes to main and results/snapshot-2026-10-28, and verifies both remote refs. Interrupted verified publication returns its receipt without creating a duplicate commit.

The gate hashes the live portable bundle and all 105 listed runtime qualification inputs; every listed Python source under runtime/source is included in the final export. It also requires the already-published Git copy of the exact test bundle, runner, and test files to match, so current qualification tests are not silently replaced during the final report commit.

Fitted models, FITS files, raw datasets, prediction arrays, credentials, and private process receipts are excluded. Full archive path and checksums are linked from the final scientific report. Prior dated interim reports remain in Git history. Fourteen focused staging tests currently cover an end-to-end finalizer-shaped gate fixture, worker exclusion, receipt binding, retry latching/backoff, privacy screening, and no-op publication recovery; publication itself has not been exercised.
