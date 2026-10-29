import importlib.util, json, sys, tempfile, types
from pathlib import Path
from unittest.mock import patch

STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/"source"))
import cold_finalizer_adapter as locator_adapter
SOURCE=STAGE/"source"/"finalize_project.py"
spec=importlib.util.spec_from_file_location("history_manifest_finalizer",SOURCE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

def _fixture_empty_primary_archive_context(runtime):
    import hashlib, types
    raw=b'{"schema_version":"fixture-empty-primary/1"}\n'
    rel="manifests/FROZEN_E1_PRIMARY_ARCHIVED_ASSETS_20261030.json"
    path=Path(runtime)/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    module=types.ModuleType("frozen_e1_primary_archive")
    module.LOCATOR_REL=rel
    module.LOCATOR_SHA256=hashlib.sha256(raw).hexdigest()
    module.primary_e1_archive_entries=lambda *a,**k:([],b'{"fixture":"empty-primary"}')
    return patch.dict(sys.modules,{"frozen_e1_primary_archive":module})

def test_full_collection_includes_portable_history_manifest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); runtime=root/"runtime_20261025"
        for rel in ("project","e1_wrapup_20261024","e1_recovery_20261024","e2_20261024",
                    "runtime_20261025/manifests/imported_selections",
                    "runtime_20261025/source","runtime_20261025/tests",
                    "runtime_20261025/cache","runtime_20261025/artifacts",
                    "runtime_20261025/reports"):
            (root/rel).mkdir(parents=True,exist_ok=True)
        names=("freeze.json","startup_audit.json","authorization_and_decisions.json",
               "tasks.json","plan_summary.json","plan_amendments.json",
               "E3_MANIFEST.json","E4_MANIFEST.json","E5_MANIFEST.json",
               "E6_MANIFEST.json","COLD_VERIFIER_HISTORY_20261028.json")
        for name in names:
            (runtime/"manifests"/name).write_text(json.dumps({"fixture":name}))
        fake_hist=types.ModuleType("archive_scientific_histories")
        fake_hist.collect_scientific_attempt_entries=lambda *a,**k: ([],b"{}")
        with _fixture_empty_primary_archive_context(runtime), \
             patch.dict(sys.modules,{"archive_scientific_histories":fake_hist}), \
             patch.object(locator_adapter,"e1_locator_archive_entries",lambda *a,**k:([],b"{}")), \
             patch.object(module,"_add_public_provenance",lambda *a,**k: None), \
             patch.object(module,"_e3_incident_expected",lambda *a,**k: {
                 module.E3_RESTORE_MANIFEST:"unused",
                 module.SERIALIZATION_INCIDENT:"unused"}), \
             patch.object(module,"e6_private_phase_receipt_manifest",lambda *a,**k: b"{}"):
            entries=module.collect_full(root,runtime,b"readme",json.dumps({"tasks":[]}))
        by_member={entry.member:entry for entry in entries}
        member="runtime_20261025/manifests/COLD_VERIFIER_HISTORY_20261028.json"
        assert member in by_member
        assert Path(by_member[member].source).read_bytes()==(runtime/"manifests/COLD_VERIFIER_HISTORY_20261028.json").read_bytes()
