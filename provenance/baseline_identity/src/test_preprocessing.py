"""Meaningful contract tests for the train-only LAMOST preprocessor."""
import json
import unittest

import numpy as np
import pandas as pd

from preprocessing import FEATURE_COLUMNS, TrainOnlyPreprocessor


def frame(values):
    return pd.DataFrame(values, columns=FEATURE_COLUMNS)


class TrainOnlyPreprocessorTests(unittest.TestCase):
    def setUp(self):
        self.fit_data = frame([
            [10, 20, 30, 40, 50, 60],
            [11, 21, 31, 41, 51, 61],
            [12, 22, 32, 42, 52, 62],
            [13, 23, 33, 43, 53, 63],
            [14, 24, 34, 44, 54, 64],
        ])

    def test_standard_scaler_learns_only_fit_partition_and_preserves_rows(self):
        proc = TrainOnlyPreprocessor().fit(self.fit_data)
        means_before = proc.center_.copy()
        scales_before = proc.scale_.copy()
        heldout = frame([[1000, 1001, 1002, 1003, 1004, 1005]])
        transformed = proc.transform(heldout)
        np.testing.assert_array_equal(proc.center_, means_before)
        np.testing.assert_array_equal(proc.scale_, scales_before)
        self.assertEqual(transformed.shape, heldout.shape)
        self.assertEqual(proc.n_fit_rows_, len(self.fit_data))
        np.testing.assert_allclose(proc.transform(self.fit_data).mean(axis=0), 0.0, atol=1e-12)

    def test_rejects_wrong_dataframe_schema_ids_and_nonfinite_values(self):
        proc = TrainOnlyPreprocessor().fit(self.fit_data)
        with self.assertRaisesRegex(ValueError, "exactly match"):
            proc.transform(self.fit_data[list(reversed(FEATURE_COLUMNS))])
        with self.assertRaisesRegex(ValueError, "exactly match"):
            proc.fit(self.fit_data.assign(source_id=np.arange(len(self.fit_data))))
        with self.assertRaisesRegex(ValueError, "exactly 6"):
            proc.fit(np.ones((3, 7)))
        bad = self.fit_data.astype(float).copy()
        bad.iloc[0, 0] = np.inf
        with self.assertRaisesRegex(ValueError, "NaN or infinite"):
            proc.fit(bad)
        bad.iloc[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "NaN or infinite"):
            proc.transform(bad)

    def test_outlier_detection_uses_fit_reference_and_flags_constant_feature_shift(self):
        data = self.fit_data.copy()
        data["mag_ps_g"] = [10, 11, 12, 13, 14]
        data["mag_ps_r"] = 7.0  # constant feature
        proc = TrainOnlyPreprocessor().fit(data)
        heldout = frame([[12, 7, 32, 42, 52, 62], [12, 8, 32, 42, 52, 62]])
        np.testing.assert_array_equal(proc.outlier_mask(heldout), [False, True])
        self.assertTrue(proc.training_inlier_mask().all())
        self.assertEqual(proc.training_inlier_mask(heldout).tolist(), [True, False])

    def test_iqr_fallback_handles_zero_mad_but_nonconstant_training_values(self):
        values = np.tile(np.array([0, 0, 0, 1, 2], dtype=float)[:, None], (1, 6))
        proc = TrainOnlyPreprocessor().fit(values)
        self.assertGreater(proc.outlier_scales_[0], 0)
        heldout = np.tile(np.array([20.0]), (1, 6))
        self.assertTrue(proc.outlier_mask(heldout)[0])

    def test_none_scaler_is_exact_and_robust_scaler_is_finite_on_constant_columns(self):
        proc = TrainOnlyPreprocessor(scaler="none").fit(self.fit_data)
        np.testing.assert_array_equal(proc.transform(self.fit_data), self.fit_data.to_numpy())
        robust = TrainOnlyPreprocessor(scaler="robust").fit(self.fit_data.assign(mag_ps_y=5.0))
        self.assertTrue(np.isfinite(robust.transform(self.fit_data.assign(mag_ps_y=5.0))).all())
        self.assertTrue(np.all(robust.scale_ > 0))

    def test_winsor_limits_are_learned_from_training_rows_only(self):
        values = np.arange(60, dtype=float).reshape(10, 6)
        proc = TrainOnlyPreprocessor(scaler="none", winsorize=True).fit(values)
        lower, upper = proc.clip_lower_.copy(), proc.clip_upper_.copy()
        heldout = np.full((2, 6), 1e9)
        clipped = proc.transform(heldout)
        np.testing.assert_array_equal(proc.clip_lower_, lower)
        np.testing.assert_array_equal(proc.clip_upper_, upper)
        np.testing.assert_array_equal(clipped, np.broadcast_to(upper, (2, 6)))
        self.assertEqual(clipped.shape[0], 2)

    def test_estimator_is_sklearn_clone_compatible(self):
        from sklearn.base import clone
        original = TrainOnlyPreprocessor(scaler="robust", winsorize=True)
        copied = clone(original)
        self.assertEqual(copied.get_params(), original.get_params())
        copied.fit(self.fit_data)
        self.assertEqual(copied.transform(self.fit_data).shape, self.fit_data.shape)

    def test_fit_metadata_is_json_serializable_and_has_fixed_feature_order(self):
        proc = TrainOnlyPreprocessor().fit(self.fit_data)
        payload = json.loads(proc.summary_json())
        self.assertEqual(payload["feature_columns"], list(FEATURE_COLUMNS))
        self.assertEqual(payload["n_fit_rows"], 5)
        self.assertEqual(len(payload["medians"]), 6)
        np.testing.assert_array_equal(proc.get_feature_names_out(), FEATURE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
