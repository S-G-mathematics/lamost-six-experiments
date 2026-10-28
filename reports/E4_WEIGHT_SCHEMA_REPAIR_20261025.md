# E4 untreated-cohort weight schema repair

This is an implementation correction, not a resource retry or a change to the scientific comparisons.

The original E4 producer serialized original-proportion per-row weights into untreated cohort containers. Those weights belong only to the explicit weighted treatment. The fitting runner correctly consumed a present weight vector, so flexible generators rejected the incorrectly weighted untreated input. The resulting “all tuning trials failed” records were invalid implementation attempts, not evidenced scientific model failures. No successful affected fit or test evaluation existed.

At 2026-10-25 17:00:22 UTC, the controller stopped dequeueing under a watchdog hold. The valid E3 repetition-3 Random Forest worker continued. The repair changed only the E4 producer schema: untreated cohorts contain X, y and source IDs; explicit weighted treatments retain their nonuniform mean-one weights. ROS, SMOTE and generated-restoration data remain unweighted.

The repair preserved 27 affected GMM attempt histories, comprising 25 falsely terminal failure records and two already interrupted/planned attempts. It superseded the 25 false failures and 225 dependent unavailability records, then queued only the affected work for a valid first scientific execution. The 42 affected cohort containers were preserved before regeneration. All 126 valid weighted/ROS/SMOTE helper artifacts were retained.

The read-only supersession audit verified all 42 regenerated cohorts: exact feature, label and source-ID dtype, shape and value equality with the retained containers; correct hashes and validation bindings; and no unintended sample_weight field. It reported 42 passed and zero issues at 2026-10-25 17:14:50 UTC. Thus cohort memberships and scientific feature values did not change.

The current producer SHA-256 is 5d5988b365613966778abc7438926d9e1b26ec36b779df98586aa600a3d20a1d. The frozen 6,270-task plan SHA remains 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb. The original scientific freeze timestamp remains 2026-10-25T04:46:31.018995+00:00. The science.py/phase_worker.py execution engine hash remains 75ec358024b13479203dbd23632565cb47f24d295a94e9b90505900520887bb0; the running E3 forest did not change code or restart.

The controller resumed at 2026-10-25T17:12:32.165349+00:00 with the user-authorized adaptive CPU/RAM scheduler. At 17:13:15 UTC, five actual fitting workers were verified: the unchanged E3 forest plus four E4 Gaussian-naive-Bayes fits. New workers use nice +10 to preserve Harbor CPU priority. This is an observation, not a guaranteed fixed worker count. The 10 GiB worker RSS maximum, 600-second trial/phase limits, one native thread, 30-second termination grace and 50,000-row prediction chunks remain unchanged.

Evidence:
- manifests/incidents/e4_weight_schema_20261025.json and the public copy reports/engineering_audits/e4_weight_schema_container_supersessions_20261025.json.
- reports/engineering_audits/E4_COHORT_CONTAINER_SUPERSESSION_AUDIT_20261025.json.
- reports/E4_INVALID_WEIGHT_SCHEMA_TRIAL_HISTORY_20261025.csv: curated invalid-trial history, without treating these attempts as scientific failures.
- artifacts/_superseded_e4_weighted_cohort_containers: exact retained original containers and producer source.
- artifacts/_invalid_e4_weight_schema_scientific_history: retained original optimizer databases and sampler states.
- Raw invalid attempt directories and process receipts remain on EC2 in logs/operational/e4_weight_schema_incident_20261025 and are excluded from public delivery.

Frozen E1, its stopped recovery supplement, and E2 were not fitted or changed. Ordinary E3 timeouts and RAM-limit failures remain terminal and were not reopened. Bootstrap remains excluded. E4 and the overall project remain in progress.
