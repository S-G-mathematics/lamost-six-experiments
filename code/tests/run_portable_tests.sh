#!/usr/bin/env bash
set -euo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${LAMOST_TEST_PYTHON:-python3.12}"
if [[ -n "${LAMOST_TEST_VENV_SITE:-}" ]]; then
  export PYTHONPATH="$LAMOST_TEST_VENV_SITE:$R/source:$R/tests:/home/ubuntu/.local/lib/python3.12/site-packages:/usr/lib/python3/dist-packages"
else
  export PYTHONPATH="$R/source:$R/tests${PYTHONPATH:+:$PYTHONPATH}"
fi
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
pytest_args=(-q --disable-warnings --tb=short -p no:cacheprovider)
if [[ "${LAMOST_TEST_COLLECT_ONLY:-0}" == "1" ]]; then
  pytest_args+=(--collect-only)
fi
test_files=(
  "$R/tests/test_raw_wide_profile.py" \
  "$R/tests/test_history_manifest_packaging.py" \
  "$R/tests/test_batch_policy.py" \
  "$R/tests/test_build_condition_findings.py" \
  "$R/tests/test_calibration_replay.py" \
  "$R/tests/test_calibration_replay_finalization_gate.py" \
  "$R/tests/test_calibration_replay_supervisor.py" \
  "$R/tests/test_cold_auditor.py" \
  "$R/tests/test_cold_auto_compaction.py" \
  "$R/tests/test_cold_batch_plan.py" \
  "$R/tests/test_cold_finalizer_adapter.py" \
  "$R/tests/test_cold_model_storage.py" \
  "$R/tests/test_cold_report_access.py" \
  "$R/tests/test_combined_resource_handover.py" \
  "$R/tests/test_condition_findings_finalizer.py" \
  "$R/tests/test_dependency_packing_dispatch.py" \
  "$R/tests/test_final_review_coverage.py" \
  "$R/tests/test_finalization_safety.py" \
  "$R/tests/test_pending_reclaim_guard.py" \
  "$R/tests/test_reporting_completion.py" \
  "$R/tests/test_reporting_environment_policy.py" \
  "$R/tests/test_weighted_mean_gate.py" \
  "$R/tests/test_cold_codec_storage.py" \
  "$R/tests/test_encoded_transactions.py" \
  "$R/tests/test_cold_model_storage_reader.py" \
  "$R/tests/test_codec_finalizer_contract.py" \
  "$R/tests/test_extracted_cold_source.py" \
  "$R/tests/test_final_review_codec_identity.py" \
  "$R/tests/test_auditor_extracted_cold.py" \
  "$R/tests/test_codec_policy.py" \
  "$R/tests/test_delivery_cron_codec.py" \
  "$R/tests/test_calibration_replay_supervisor_clock_race.py" \
  "$R/tests/test_codec_archive_projection_integration.py" \
  "$R/tests/test_cold_compaction_process_scan.py" \
  "$R/tests/test_arf_profiles.py" \
  "$R/tests/test_guard_runner_exit_identity.py" \
  "$R/tests/test_admission_profile.py" \
  "$R/tests/test_arf_lane_scheduling.py" \
  "$R/tests/test_admission_hysteresis.py" \
  "$R/tests/test_reporting_gaps.py" \
  "$R/tests/test_label_rate_gate.py" \
  "$R/tests/test_startup_identity.py" \
  "$R/tests/test_postcommit_receipt.py" \
  "$R/tests/test_candidate_provenance_filter.py" \
  "$R/tests/test_archive_io_profile.py" \
  "$R/tests/test_cold_cron_profiles.py" \
  "$R/tests/test_candidate_finalizer_publication_disclosure.py" \
  "$R/tests/test_e6_orphan_supervision.py" \
  "$R/tests/test_e6_overlay_controller.py" \
  "$R/tests/test_e6_v2_protocol.py" \
  "$R/tests/test_e6_v2_contract.py" \
  "$R/tests/test_e6_v2_controller_contract.py" \
  "$R/tests/test_e6_v2_validation.py" \
  "$R/tests/test_supervisor_e6_pairs.py" \
  "$R/tests/test_archive_transaction_cooldown.py" \
  "$R/tests/test_e6_v2_reporting.py" \
  "$R/tests/test_export_dispatch.py" \
  "$R/tests/test_e6_v2_finalizer_candidate.py" \
  "$R/tests/test_e6_artifact_resolution.py" \
  "$R/tests/test_native_e6_replay_tiny.py" \
  "$R/tests/test_feature_order_provenance.py" \
  "$R/tests/test_rf4_controller_policy.py" \
  "$R/tests/test_rf4_fit_jobs.py" \
  "$R/tests/test_member_comparison_status_count.py" \
  "$R/tests/test_e6_terminal_resume_idempotence.py" \
  "$R/tests/test_verified_zombie_reap.py" \
  "$R/tests/test_native_fit_scope.py" \
  "$R/tests/test_child_cache_adoption.py" \
  "$R/tests/test_archive_fit_launch_gate_legacy.py" \
  "$R/tests/test_e4_rf4_6g_admission.py" \
  "$R/tests/test_rf4_rep3_admission.py" \
  "$R/tests/test_rf4_rep3_controller_admit.py" \
  "$R/tests/test_e4_et_dependency_priority.py" \
  "$R/tests/test_public_registry_process_privacy.py" \
  "$R/tests/test_archive_digest_coalescing.py" \
  "$R/tests/test_nonfit_disk_drain.py" \
  "$R/tests/test_loop_snapshot_refresh.py" \
  "$R/tests/test_metadata_only_contract.py" \
  "$R/tests/test_mixed_family_scope.py" \
  "$R/tests/test_batch_inode_inventory.py" \
  "$R/tests/test_batch_inode_inventory_fixture.py" \
  "$R/tests/core_3bf/test_3bf_cold_model_storage.py" \
  "$R/tests/test_mixed_small_profile.py"
  "$R/tests/test_unlink_checkpoint_batch.py" \
  "$R/tests/test_recovery_archive_digest_reuse.py" \
  "$R/tests/test_legacy_checkpoint_migration.py" \
  "$R/tests/test_metadata_access_contract_v2.py"
  "$R/tests/test_et17_archive_scope.py"
  "$R/tests/test_durable_baseline_digest_cache.py"
  "$R/tests/test_native_fit_mixedsmall_profile.py"
  "$R/tests/test_native_fit_controller_harness.py"
)
exec "$python_bin" -m pytest "${pytest_args[@]}" "${test_files[@]}"
