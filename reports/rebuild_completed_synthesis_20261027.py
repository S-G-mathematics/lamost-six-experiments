from pathlib import Path
from datetime import datetime, timezone
import csv, json, hashlib, shutil, re

ROOT = Path("/home/ubuntu/lamost_e1_migration_20261023")
REPORTS = ROOT / "runtime_20261025/reports"
SCRIPT = REPORTS / "rebuild_completed_synthesis_20261027.py"
OUT = REPORTS / "COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027.md"
TABLE = REPORTS / "COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027.csv"
INPUTS = REPORTS / "COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027_INPUTS.json"
RECEIPT = REPORTS / "COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027_RECEIPT.json"
HISTORY = REPORTS / "history/synthesis_correction_20261027"
HISTORY.mkdir(parents=True, exist_ok=True)
OBSERVED = datetime.now(timezone.utc).isoformat(timespec="seconds")

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))

def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def dump_json(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

# Preserve the pre-correction synthesis and all provenance before changing it.
for path in (OUT, TABLE, INPUTS, RECEIPT):
    target = HISTORY / path.name
    if path.is_file() and not target.exists():
        shutil.copy2(path, target)
template = HISTORY / OUT.name
if not template.is_file():
    raise RuntimeError("No preserved pre-correction report template")

e1_csv = ROOT / "e1_wrapup_20261024/E1_frozen_cells_765.csv"
e1_json = ROOT / "project/benchmark/results/e1_report_validated_no_bootstrap.json"
recovery_csv = ROOT / "e1_wrapup_20261024/E1_recovery_cutoff_91.csv"
e1 = read_csv(e1_csv)
validated = json.loads(e1_json.read_text(encoding="utf-8"))
vmap = {(str(x["budget"]), str(x["repetition"]), str(x["method"])): x for x in validated["cells"]}
if len(e1) != 765 or len(vmap) != 765:
    raise ValueError("Frozen E1 ledger/report row count mismatch")

by_budget = {}
overall = {"successful": 0, "failed": 0, "unsupported": 0}
for row in e1:
    key = (str(row["budget"]), str(int(row["key"].split("/")[1].replace("rep_", ""))), str(row["method"]))
    cell = vmap.get(key)
    if cell is None:
        raise ValueError(f"No validated E1 cell for {key}")
    raw = cell["classification"]
    messages = " ".join(str(z.get("message", "")) for z in cell.get("failure_evidence", []))
    if raw == "successful_test_evaluation":
        state = "successful"
    elif raw in ("resource_failure", "supervisor_terminal_failure_without_cell_completion"):
        state = "failed"
    elif raw == "scientific_model_or_support_failure":
        state = "unsupported" if "unsupported:" in messages.lower() else "failed"
    else:
        raise ValueError(f"Unrecognized E1 classification {raw}")
    overall[state] += 1
    z = by_budget.setdefault(str(row["budget"]), {"planned": 0, "successful": 0, "failed": 0, "unsupported": 0})
    z["planned"] += 1
    z[state] += 1

if overall != {"successful": 674, "failed": 81, "unsupported": 10}:
    raise ValueError(f"E1 terminal state invariant failed: {overall}")
for budget, z in by_budget.items():
    if z["planned"] != z["successful"] + z["failed"] + z["unsupported"]:
        raise ValueError(f"E1 budget state sum failed: {budget} {z}")
if sum(z["planned"] for z in by_budget.values()) != 765:
    raise ValueError("E1 budget rows do not sum to 765")

recovery = read_csv(recovery_csv)
rstates = {"successful": 0, "failed": 0, "user_stopped": 0, "not_attempted_user_stopped": 0}
for row in recovery:
    status = row["recovery_status"]
    normalized = {"successful_test_evaluation": "successful", "failed": "failed",
                  "user_stopped": "user_stopped", "not_attempted_user_stopped": "not_attempted_user_stopped"}.get(status)
    if normalized not in rstates:
        raise ValueError(f"Unexpected recovery state {status}")
    rstates[normalized] += 1
if len(recovery) != 91 or rstates != {"successful": 24, "failed": 10, "user_stopped": 2, "not_attempted_user_stopped": 55}:
    raise ValueError(f"Recovery cutoff invariant failed: {rstates}")
if sum(rstates.values()) != 91:
    raise ValueError("Recovery terminal-state sum failed")

# Recompute supported cross-experiment rows from saved ledgers.
e2 = read_csv(ROOT / "e2_20261024/E2_all_generators_270.csv")
e3 = read_csv(REPORTS / "E3_FINAL_CELL_LEDGER_69.csv")
e3routes = read_csv(REPORTS / "E3_FINAL_ROUTE_REPETITIONS.csv")
e6 = read_csv(REPORTS / "E6_FINAL_CELL_LEDGER_21.csv")
e6members = read_csv(REPORTS / "E6_MEMBER_PER_REPETITION.csv")
if (len(e2), len(e3), len(e6)) != (270, 69, 21):
    raise ValueError("E2/E3/E6 source ledger count mismatch")

summary = []
def add(exp, group, planned, success, failed=0, unsupported=0, unavailable=0, pending=0,
        user_stopped=0, not_attempted=0, reps="", ba="", coverage="", set_size="", paired_n="", notes=""):
    summary.append({
        "experiment": exp, "group": group, "planned": planned, "successful": success,
        "failed": failed, "unsupported": unsupported, "unavailable": unavailable,
        "user_stopped": user_stopped, "not_attempted": not_attempted, "pending": pending,
        "actual_successful_repetitions": reps, "balanced_accuracy_mean": ba,
        "coverage_mean": coverage, "mean_set_size_mean": set_size, "paired_n": paired_n, "notes": notes
    })
for budget in sorted(by_budget, key=int):
    z = by_budget[budget]
    add("E1", "budget_" + budget, z["planned"], z["successful"], z["failed"], z["unsupported"],
        reps="see E1 method-budget table", notes="Frozen ledger; categories cross-checked against validated report.")
add("E1", "frozen_total", 765, 674, 81, 10, reps="cell-specific",
    notes="81 failures = 55 resource + 26 supervisor-terminal; 10 unsupported separate.")
add("E1 recovery", "stopped_supplement", 91, 24, 10, user_stopped=2, not_attempted=55,
    pending=0, reps="separate", notes="Recovery is terminal at user stop; do not merge into frozen E1.")
add("E2", "primary_five_generator", 150, 108, unavailable=42, reps="varies",
    paired_n="4 complete strata", notes="42 unavailable due failed frozen E1 dependencies.")
add("E2", "classical_reference", 120, 120, reps="separate",
    notes="Reference analysis separate from primary five-family grid.")
for row in e3routes:
    s = int(row["successful_repetitions"])
    if row["route"] == "direct":
        add("E3", "direct_" + row["generator"], 3, s, failed=3-s, reps=f"{s}/3",
            ba=row.get("balanced_accuracy_mean", ""), coverage=row.get("coverage_mean", ""),
            set_size=row.get("mean_set_size_mean", ""))
    elif row["route"] == "synthetic":
        add("E3", f"synthetic_{row['generator']}_{row['learner']}", 3, s, unavailable=3-s, reps=f"{s}/3",
            ba=row.get("balanced_accuracy_mean", ""), coverage=row.get("coverage_mean", ""),
            set_size=row.get("mean_set_size_mean", ""), paired_n=row.get("synthetic_minus_real_paired_n", ""),
            notes="Matched differences are reported in E3_FINAL_ROUTE_REPETITIONS.csv.")
    elif row["route"] == "real":
        add("E3", "real_" + row["learner"], 3, s, unavailable=3-s, reps=f"{s}/3",
            ba=row.get("balanced_accuracy_mean", ""), coverage=row.get("coverage_mean", ""),
            set_size=row.get("mean_set_size_mean", ""), notes="Shared real-only baseline.")
for family in ("gmm", "copula", "arf", "kde", "chow_liu"):
    selected = [x for x in e6members if x["family"] == family and x["outcome"] == "successful"]
    def mean(column):
        return sum(float(x[column]) for x in selected) / len(selected) if selected else ""
    add("E6", "member_" + family, 3, len(selected), unavailable=3-len(selected), reps=f"{len(selected)}/3",
        ba=mean("balanced_accuracy"), coverage=mean("coverage"), set_size=mean("mean_set_size"),
        paired_n="3" if len(selected) == 3 else "", notes="Reused E3 direct member result, not ensemble.")
for mode in ("equal", "learned"):
    add("E6", "ensemble_" + mode, 3, 0, unavailable=3, reps="0/3",
        notes="Unavailable before attempt because KDE direct member references timed out; no weight search.")
fields = ["experiment", "group", "planned", "successful", "failed", "unsupported", "unavailable",
          "user_stopped", "not_attempted", "pending", "actual_successful_repetitions",
          "balanced_accuracy_mean", "coverage_mean", "mean_set_size_mean", "paired_n", "notes"]
for item in summary:
    terminal_sum = sum(int(item[k]) for k in ("successful", "failed", "unsupported", "unavailable", "user_stopped", "not_attempted", "pending"))
    if int(item["planned"]) != terminal_sum:
        raise ValueError(f"Summary row state invariant failed: {item['experiment']} / {item['group']}")
write_csv(TABLE, summary, fields)

# Update the prior report using bounded exact text replacements and computed budget rows.
text = template.read_text(encoding="utf-8")
text = re.sub(r"Assembled .*? UTC on the existing EC2", f"Corrected and revalidated at {OBSERVED} UTC on the existing EC2", text, count=1)
text = text.replace(
    "| Experiment / group | Planned | Successful | Failed | Unsupported | Unavailable | Pending |",
    "| Experiment / group | Planned | Successful | Failed | Unsupported | Unavailable | User-stopped | Not attempted | Pending |"
)
text = text.replace(
    "|---|---:|---:|---:|---:|---:|---:|",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    1
)
text = text.replace(
    "| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 |",
    "| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 | 0 |"
).replace(
    "| E1 recovery supplement, separate | 91 | 24 | 10 | 0 | 0 | 57* |",
    "| E1 recovery supplement, separate | 91 | 24 | 10 | 0 | 0 | 2 | 55 | 0 |"
).replace(
    "| E2 primary five-generator grid | 150 | 108 | 0 | 0 | 42 | 0 |",
    "| E2 primary five-generator grid | 150 | 108 | 0 | 0 | 42 | 0 | 0 | 0 |"
).replace(
    "| E2 classical reference set | 120 | 120 | 0 | 0 | 0 | 0 |",
    "| E2 classical reference set | 120 | 120 | 0 | 0 | 0 | 0 | 0 | 0 |"
).replace(
    "| E3 evaluation grid | 69 | 64 | 3 | 0 | 2 | 0 |",
    "| E3 evaluation grid | 69 | 64 | 3 | 0 | 2 | 0 | 0 | 0 |"
).replace(
    "| E6 member references | 15 | 12 | 0 | 0 | 3 | 0 |",
    "| E6 member references | 15 | 12 | 0 | 0 | 3 | 0 | 0 | 0 |"
).replace(
    "| E6 primary ensembles | 6 | 0 | 0 | 0 | 6 | 0 |",
    "| E6 primary ensembles | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |"
)
text = text.replace(
    "*Recovery pending consists of 2 user-stopped partial cells and 55 not attempted after the stop decision. These are not scientific failures and are not part of frozen E1.",
    "*Recovery is stopped and terminal at the user decision: 2 user-stopped partial cells and 55 not attempted. These are not scientific failures and are not part of frozen E1."
)
needle = "The 100,000-row E1 budget had 67 successful of 85 planned and 18 failures. The complete frozen cell ledger and method-budget table retain actual repetition counts by method and budget."
budget_table = ["", "Frozen E1 terminal outcomes by budget (all 85 cells per budget):", "",
                "| Budget | Planned | Successful | Failed | Unsupported |", "|---:|---:|---:|---:|---:|"]
for budget in sorted(by_budget, key=int):
    z = by_budget[budget]
    budget_table.append(f"| {int(budget):,} | {z['planned']} | {z['successful']} | {z['failed']} | {z['unsupported']} |")
budget_table += [""]
if needle not in text:
    raise ValueError("Expected E1 summary sentence missing from template")
text = text.replace(needle, needle + "\n" + "\n".join(budget_table))
text = text.replace(
    "Historical fitted pipelines and per-test-row prediction arrays omitted from the compact migration remain unavailable.",
    "The compact migration omitted some historical fitted pipelines and per-test-row prediction arrays; a subset of original fits remains available, while omitted artifacts were not universally restored. E2/E3/E6 provenance labels identify original, reconstructed, reused, and new fits where relevant."
)
# Reject malformed Markdown tables before publication.
pipe_blocks = []
current = []
for line in text.splitlines():
    if line.strip().startswith("|") and line.strip().endswith("|"):
        current.append(line.strip())
    elif current:
        pipe_blocks.append(current)
        current = []
if current:
    pipe_blocks.append(current)
for block in pipe_blocks:
    widths = {len(line.strip("|").split("|")) for line in block}
    if len(widths) != 1:
        raise ValueError(f"Markdown table column mismatch: {widths}: {block[:3]}")
OUT.write_text(text, encoding="utf-8")

source_paths = [
    "e1_wrapup_20261024/E1_WRAPUP.md", "e1_wrapup_20261024/E1_frozen_cells_765.csv",
    "e1_wrapup_20261024/E1_method_budget_summary_153.csv", "e1_wrapup_20261024/E1_recovery_cutoff_91.csv",
    "project/benchmark/results/e1_report_validated_no_bootstrap.json",
    "e2_20261024/E2_CURRENT_REPORT.md", "e2_20261024/E2_RECONSTRUCTION_AMENDMENT.md",
    "e2_20261024/E2_INTEGRITY_AUDIT.json", "e2_20261024/E2_all_generators_270.csv",
    "e2_20261024/E2_all_class_reports_1596.csv",
    "runtime_20261025/reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv",
    "runtime_20261025/reports/E2_CORRELATIONS_INDEPENDENTLY_VERIFIED.csv",
    "runtime_20261025/reports/E3_FINAL_DESCRIPTIVE_REPORT.md",
    "runtime_20261025/reports/E3_FINAL_CELL_LEDGER_69.csv",
    "runtime_20261025/reports/E3_FINAL_ROUTE_REPETITIONS.csv",
    "runtime_20261025/reports/E6_FINAL_DESCRIPTIVE_REPORT.md",
    "runtime_20261025/reports/E6_FINAL_CELL_LEDGER_21.csv",
    "runtime_20261025/reports/E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv",
    "runtime_20261025/reports/E6_MEMBER_PER_REPETITION.csv",
    "runtime_20261025/reports/E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json"
]
sourceinfo = []
for rel in source_paths:
    path = ROOT / rel
    if not path.is_file():
        raise FileNotFoundError(rel)
    sourceinfo.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest(path)})
observed = OBSERVED
dump_json(INPUTS, {"schema": "lamost-cross-experiment-synthesis-inputs/1", "observed_utc": observed,
                   "inputs": sourceinfo, "scope": "Saved report and summary metadata only; no model or prediction array access."})
record = {
    "schema": "lamost-cross-experiment-synthesis-receipt/2",
    "observed_utc": observed,
    "status": "descriptive_synthesis_written_project_incomplete",
    "saved_report_metadata_only": True,
    "model_or_prediction_array_access": False,
    "e1_terminal_state_counts": overall,
    "e1_by_budget": by_budget,
    "recovery_terminal_state_counts": {"successful": 24, "failed": 10, "user_stopped": 2, "not_attempted": 55, "pending": 0},
    "invariants": {"e1_total": sum(overall.values()) == 765,
                   "e1_each_budget_sums": all(x["planned"] == x["successful"] + x["failed"] + x["unsupported"] for x in by_budget.values()),
                   "recovery_total": sum(rstates.values()) == 91,
                   "every_summary_row_planned_equals_terminal_states": True},
    "outputs": {str(path.relative_to(ROOT)): {"bytes": path.stat().st_size, "sha256": digest(path)}
                for path in (OUT, TABLE, INPUTS, SCRIPT)},
    "input_count": len(sourceinfo),
    "history_directory": str(HISTORY.relative_to(ROOT)),
    "limitations": "E4/E5 ongoing; global calibration-quantile replay and final project validation pending."
}
dump_json(RECEIPT, record)
print(json.dumps(record, indent=2))

