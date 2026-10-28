LAMOST DR10 v2 — clean seven-class photometric baseline

START HERE
The full baseline contains 2,330,835 source representatives and six numeric
features. The seven labels are A,F,G,K,M,GALAXY,QSO. No classifier has been
trained. Detailed measured counts and limitations are in
  docs/LAMOST_Cleaning_Report.txt
  docs/CLEANING_PROTOCOL.txt

FILES
  data/baseline.parquet           Native magnitudes, label/label_id, sample_id.
  data/splits.parquet             Development/test/reserve and reference split.
  data/metadata.parquet           Source/link IDs, observation/quality flags,
                                 label disagreement, strict_consensus boolean.
  data/reference_standardized.parquet
                                 1.5m rows: reference_fit/reference_tune/test;
                                 six standardized features + ID/label_id/partition.
  data/reference_*_scaler.joblib  Training-only fitted reference preprocessors.
  data/outlier_flags.parquet      Marginal magnitude-tail diagnostic (0 flagged).
  data/color_tail_flags.parquet   Color-tail diagnostics; do not auto-delete.
  data/source_candidates.parquet  2,330,850 per-UID candidates before 15 shared-
                                 counterpart reductions. Keep for sensitivity.
  audit/row_disposition.parquet    One reason per original catalog observation.
  audit/source_entity_membership.parquet
                                 Eligible UID -> linked entity mapping.
  audit/cleaning_audit.json        Full measured cleaning/split checks.
  audit/independent_validation.json Independent artifact integrity validation.
  audit/*pearson.csv, *spearman.csv, *profile.csv
                                 Statistics fitted/measured on reference fit only.
  audit/source_provenance.json    Raw mirror URL, headers, SHA256, caveat.
  audit/official_*                Checks against official SQL service.
  manifest.json                  SHA256 of delivered stable files.
  src/                           Reproducible scripts and contract tests.
  raw/query_speed_preview.csv    Official 10k-row validation export only.

READ THE REFERENCE SPLIT (Python, no classifier fitting)

  import pandas as pd
  import sys
  sys.path.insert(0, 'src')
  from preprocessing import FEATURE_COLUMNS, TrainOnlyPreprocessor

  data = pd.read_parquet('data/baseline.parquet')
  splits = pd.read_parquet('data/splits.parquet')
  data = data.merge(splits, on='sample_id', validate='one_to_one')
  train = data.loc[data.reference_partition.eq('reference_fit')]
  tune = data.loc[data.reference_partition.eq('reference_tune')]
  test = data.loc[data.reference_partition.eq('test')]
  features = list(FEATURE_COLUMNS)
  prep = TrainOnlyPreprocessor(scaler='standard').fit(train[features])
  X_train = prep.transform(train[features])
  X_tune = prep.transform(tune[features])
  X_test = prep.transform(test[features])
  y_train = train.label_id.to_numpy()

Do not include sample_id, label_id, partition, IDs or metadata in X.
For the precomputed reference_standardized.parquet, select precisely the same
six named feature columns; that file already has reference scaling applied.
Use it only for the fixed 800k/200k/500k reference setup. For smaller budgets,
new repetitions, or cross-validation, fit a fresh preprocessor on that run's
fit rows. Reuse source cleaning and frozen test IDs; do not reclean test data.

OUTLIERS AND CORRELATION
No blanket removal of valid extreme rows or correlated bands. The highest
fit-only Pearson correlation is 0.99656, but all six columns are distinct,
nonconstant, and full rank. Global color-tail cuts strongly target particular
valid classes. Model covariance regularization belongs in training/tuning.
Audit flags are available for explicit sensitivity work; they are not labels.
Native features are retained so model-specific transforms are reproducible.

SPLITS
  Test:              500,000 (fixed; natural class proportions)
  Development:     1,000,000 (reference fit 800k + tune 200k)
  Reserve:           830,835
Source IDs, linked entities and positive Gaia/PanSTARRS counterpart IDs do not
cross split boundaries. No spatial/plate independence claim is made. Future
paired repetitions may resample development from non-test rows, capped at 1m;
the permanent test membership must remain fixed. Conformal calibration
allocation is not specified by this preparation.

REPRODUCE FROM SOURCE
Python 3.12.14 was used. In an isolated environment install requirements.txt.
The delivered zip does not contain the 3.46GB raw FITS or temporary database.

  python -m pip install -r requirements.txt
  python src/download_source.py
  python src/official_sql_checks.py aggregate
  python src/official_sql_checks.py zero-probe
  python src/ingest_source.py
  python src/build_baseline.py
  python src/audit_colors.py
  python -m unittest discover -s src -p 'test_*.py' -v
  python src/verify_baseline.py

An original official 10k-row pilot is included. To fetch a fresh pilot, run
python src/official_sql_checks.py pilot before rebuilding. Full-source checks
refuse changed counts; do not suppress those assertions on a new release.
The public academic FITS mirror has been checked against official aggregate
counts, selected missing-value cases and 10,000 records. Bytewise equality
with the official compressed archive has not been authenticated.

ATTRIBUTION / SCIENTIFIC LIMITS
Original observations/catalog: LAMOST DR10 v2 LRS general catalog, with survey
photometry linked to PanSTARRS DR2 and Gaia DR3. Original source URLs are in
CLEANING_PROTOCOL.txt and source_provenance.json. Labels are spectral pipeline
outputs. Complete-case selection and pipeline/crossmatch uncertainty remain;
read the report before claiming a population-representative or error-free set.
