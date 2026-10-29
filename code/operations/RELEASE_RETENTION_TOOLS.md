# Release-backed result-array retention helpers

These two generic helpers manage already-published E4 test-outcome arrays in the existing GitHub release. They do not contain the deployment plan, approval, cache contents, runtime state, or process logs.

- release_retention_20261030/release_retention.py validates release-manifest bindings and plans bounded retention of eligible successful non-control E4 result arrays. Its default plan target is 2 GiB and its selection cap is 4 GiB. Alias-backed files are considered only as complete known inode groups; uncertain groups remain review-only. A restore path is provided so retained arrays can be returned before final validation.
- release_guardian_20261030/release_guardian.py checks state and process identity around the helper workflow, applies the configured disk floors, and requires the separately held approval and plan bindings. The operational config, plan, approval, state, cache, and launch details are intentionally kept on the EC2 project.

The focused tests are code/tests/test_release_retention.py (16 tests) and code/tests/test_release_guardian.py (11 tests); both suites had passed before this export. These helpers are data-retention tooling, not model-fitting or inference code. They do not change the scientific resource limits or experiment outcomes.
