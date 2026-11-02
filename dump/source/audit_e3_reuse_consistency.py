#!/usr/bin/env python3
"""Read-only consistency audit for E3 fits reused from E2 saved reconstructions.

Does not deserialize models, perform inference, or modify source artifacts. Writes one CSV
and one JSON receipt under runtime_20261025/reports.
"""
from __future__ import annotations
import csv, datetime, hashlib, json, math
from pathlib import Path

ROOT = Path('/home/ubuntu/lamost_e1_migration_20261023')
RUNTIME = ROOT / 'runtime_20261025'
PLAN = RUNTIME / 'manifests/tasks.json'
E2_CSV = ROOT / 'e2_20261024/E2_all_generators_270.csv'
OUT_CSV = RUNTIME / 'reports/E3_REUSED_E2_CLASSIFICATION_CONSISTENCY.csv'
OUT_DIR = RUNTIME / 'reports/engineering_audits'

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def read_json(path: Path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)

def maybe_sha(path: Path):
    return sha(path) if path.is_file() else None

def read_e2_rows():
    with E2_CSV.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def audit():
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan = read_json(PLAN)
    tasks = plan.get('tasks', [])
    reuse_tasks = [t for t in tasks if t.get('experiment') == 3 and t.get('kind') == 'fit' and t.get('reuse_pipeline')]
    e2_rows = read_e2_rows()
    input_paths = {str(PLAN), str(E2_CSV)}
    for t in reuse_tasks:
        md = t.get('source_metadata') or {}
        for k in ('path', 'reconstruction', 'gate'):
            if md.get(k): input_paths.add(str(Path(md[k])))
        # Task's E2 pipeline path is independently recorded in reuse_pipeline.
        input_paths.add(str(Path(t['reuse_pipeline'])))
        base = RUNTIME / 'artifacts' / t['key']
        for rel in ('fit_result.json', 'pipeline.joblib', 'selection.json'):
            input_paths.add(str(base / rel))
        input_paths.add(str(RUNTIME / 'artifacts' / 'e3' / f"rep_{t['rep']}" / 'eval' / 'direct' / t['method'] / 'evaluation.json'))
    before = {p: maybe_sha(Path(p)) for p in sorted(input_paths)}
    results = []
    for t in sorted(reuse_tasks, key=lambda x: (int(x['rep']), x['method'])):
        rep, method = int(t['rep']), str(t['method'])
        md = t.get('source_metadata') or {}
        e2_pipe = Path(t['reuse_pipeline'])
        rec_path = Path(md.get('reconstruction', ''))
        gate_path = Path(md.get('gate', ''))
        e3_base = RUNTIME / 'artifacts' / t['key']
        fit_path = e3_base / 'fit_result.json'
        e3_pipe = e3_base / 'pipeline.joblib'
        eval_path = RUNTIME / 'artifacts' / 'e3' / f'rep_{rep}' / 'eval' / 'direct' / method / 'evaluation.json'
        issues = []
        rec = read_json(rec_path) if rec_path.is_file() else {}
        gate = read_json(gate_path) if gate_path.is_file() else {}
        fit = read_json(fit_path) if fit_path.is_file() else {}
        evaluation = read_json(eval_path) if eval_path.is_file() else {}
        e2_hash = maybe_sha(e2_pipe)
        e3_hash = maybe_sha(e3_pipe)
        if not e2_pipe.is_file(): issues.append('E2 pipeline missing')
        if not rec: issues.append('reconstruction record missing')
        if not gate: issues.append('reproduction gate missing')
        if rec:
            if rec.get('status') != 'reconstructed_tuning_checked': issues.append('reconstruction status mismatch')
            if int(rec.get('budget', -1)) != 100000 or int(rec.get('repetition', -1)) != rep or rec.get('method') != method: issues.append('reconstruction key mismatch')
            if [rec.get('fit_rows'), rec.get('tuning_rows'), rec.get('calibration_rows')] != [80000, 10000, 10000]: issues.append('role row counts mismatch')
            if rec.get('same_selected_params') is not True or rec.get('reconstructed_not_original') is not True: issues.append('reconstruction provenance flags mismatch')
            if rec.get('source_role_sha256') != t.get('role_membership_sha256'): issues.append('role-membership hash mismatch')
            if rec.get('reconstructed_pipeline_sha256') != e2_hash: issues.append('recorded E2 pipeline hash mismatch')
            if rec.get('fit_seed') != md.get('fit_seed') or rec.get('fit_seed') != t.get('seed'): issues.append('fit seed mismatch')
        if md.get('path') != str(e2_pipe): issues.append('plan source path mismatch')
        if not str(md.get('provenance', '')).startswith('E2 reconstructed fit'): issues.append('plan provenance label mismatch')
        if md.get('source_role_sha256') != t.get('role_membership_sha256'): issues.append('plan role hash mismatch')
        if md.get('selected_params_match') is not True: issues.append('plan selected-parameter match flag missing')
        if md.get('reconstruction_sha256') != maybe_sha(rec_path): issues.append('plan reconstruction SHA mismatch')
        if md.get('gate_sha256') != maybe_sha(gate_path): issues.append('plan gate SHA mismatch')
        if gate and gate.get('status') != md.get('gate_status'): issues.append('gate status mismatch')
        e2_matches = [r for r in e2_rows if str(r.get('budget')) == '100000' and str(r.get('repetition')) == str(rep) and r.get('method') == method]
        e2_ba = None
        e2_provenance = None
        if len(e2_matches) != 1:
            issues.append(f'E2 100k method/repetition rows={len(e2_matches)}, expected 1')
        else:
            row = e2_matches[0]
            e2_provenance = row.get('provenance')
            try: e2_ba = float(row['balanced_accuracy'])
            except (TypeError, ValueError, KeyError): issues.append('E2 measured balanced accuracy unavailable')
            if row.get('provenance') != 'E2_reconstructed_fit': issues.append('E2 comparison row provenance mismatch')
            if row.get('classification_source') != 'E2_reconstructed_fit_fixed_test_evaluation': issues.append('E2 comparison source mismatch')
        e3_ba = None
        if fit.get('status') != 'successful': issues.append('E3 reused fit not successful')
        fit_result = fit.get('result') or {}
        if fit_result.get('reused') is not True: issues.append('E3 fit result does not state pipeline reuse')
        if fit_result.get('source_sha256') != e2_hash: issues.append('E3 fit source SHA does not match E2 pipeline')
        if fit.get('artifact_sha256') != e3_hash: issues.append('E3 fit artifact SHA does not match E3 pipeline file')
        selection_path = e3_base / 'selection.json'
        selection = read_json(selection_path) if selection_path.is_file() else {}
        if selection.get('reused') is not True or selection.get('source_sha256') != e2_hash: issues.append('E3 selection provenance does not match reused E2 source')
        if selection.get('seed') != t.get('seed'): issues.append('E3 selection seed mismatch')
        if not evaluation: issues.append('E3 direct evaluation missing')
        else:
            if evaluation.get('task_key') != f'e3/rep_{rep}/eval/direct/{method}': issues.append('E3 evaluation task key mismatch')
            if evaluation.get('fit_key') != t['key']: issues.append('E3 evaluation fit dependency mismatch')
            if evaluation.get('pipeline_sha256') != e3_hash: issues.append('E3 evaluation pipeline SHA mismatch')
            try: e3_ba = float(evaluation['balanced_accuracy'])
            except (TypeError, ValueError, KeyError): issues.append('E3 balanced accuracy unavailable')
        diff = e3_ba - e2_ba if e3_ba is not None and e2_ba is not None else None
        exact = (diff == 0.0) if diff is not None else None
        results.append({
            'budget': 100000, 'repetition': rep, 'method': method,
            'provenance_group': 'E2 reconstructed fit reused by E3',
            'e2_reconstruction_status': rec.get('status'), 'e2_gate_status': gate.get('status'),
            'e2_provenance': e2_provenance, 'role_hash_match': rec.get('source_role_sha256') == t.get('role_membership_sha256'),
            'selected_params_match_flag': rec.get('same_selected_params'), 'reconstructed_not_original_flag': rec.get('reconstructed_not_original'),
            'e2_pipeline_sha256': e2_hash, 'e3_pipeline_sha256': e3_hash,
            'e3_pipeline_byte_match_to_e2_source': (e2_hash == e3_hash) if e2_hash and e3_hash else None,
            'e2_balanced_accuracy': e2_ba, 'e3_balanced_accuracy': e3_ba,
            'signed_difference_e3_minus_e2': diff, 'exact_float_score_match': exact,
            'model_or_prediction_identity_inferred': False,
            'comparison_status': 'checked' if not issues and diff is not None else 'incomplete_or_mismatch',
            'issues': '; '.join(issues)
        })
    after = {p: maybe_sha(Path(p)) for p in sorted(input_paths)}
    changed = [p for p in before if before[p] != after[p]]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    csv_fields = list(results[0].keys()) if results else ['budget','repetition','method','comparison_status','issues']
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=csv_fields); w.writeheader(); w.writerows(results)
    diffs = [r['signed_difference_e3_minus_e2'] for r in results if r['signed_difference_e3_minus_e2'] is not None]
    script_path = Path(__file__).resolve()
    audit = {
        'schema_version': 'e3-e2-reuse-consistency/1.1',
        'supersedes_prior_audit': str(OUT_DIR / 'E3_reused_E2_consistency_20261025T133639Z.json'),
        'supersession_note': 'Revision fixes two overstrict checks: accepts the documented verbose E2 reconstructed-fit provenance label and treats E2-to-E3 serialized byte equality as informational, while checking recorded source, result artifact and selection hashes. The earlier audit output is retained for provenance.', 'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'plan_path': str(PLAN), 'plan_sha256': before.get(str(PLAN)), 'e2_table_path': str(E2_CSV), 'e2_table_sha256': before.get(str(E2_CSV)),
        'planned_reuse_fits': len(reuse_tasks), 'comparisons_written': len(results),
        'checked_comparisons': sum(r['comparison_status'] == 'checked' for r in results),
        'missing_or_mismatched_comparisons': sum(r['comparison_status'] != 'checked' for r in results),
        'exact_score_matches': sum(r['exact_float_score_match'] is True for r in results),
        'nonzero_score_differences': sum(r['exact_float_score_match'] is False for r in results),
        'maximum_absolute_score_difference': max((abs(x) for x in diffs), default=None),
        'no_model_or_prediction_identity_inferred': True,
        'input_hashes_before': before, 'input_hashes_after': after, 'input_changed_during_audit': changed,
        'audit_script_path': str(script_path), 'audit_script_sha256': sha(script_path),
        'csv_path': str(OUT_CSV), 'csv_sha256': sha(OUT_CSV),
        'scope': 'Small JSON/CSV metadata and file SHA checks only. No joblib/model loads, fit, tuning, generation, predictions, bootstrap, large dataset scan, or source artifact writes.'
    }
    audit_path = OUT_DIR / f'E3_reused_E2_consistency_{stamp}.json'
    with audit_path.open('w', encoding='utf-8') as f: json.dump(audit, f, indent=2, sort_keys=True); f.write('\n')
    print(json.dumps({'audit_path': str(audit_path), 'csv_path': str(OUT_CSV), 'planned_reuse_fits': len(reuse_tasks), 'comparisons_written': len(results), 'checked': audit['checked_comparisons'], 'mismatched_or_missing': audit['missing_or_mismatched_comparisons'], 'input_changed': changed, 'script_sha256': audit['audit_script_sha256'], 'csv_sha256': audit['csv_sha256']}, sort_keys=True))

if __name__ == '__main__': audit()
