"""Train-partition-only preprocessing for the six LAMOST magnitude features.

This module deliberately does not drop rows. Outlier detection is exposed as a
separate mask so a caller can decide whether and how to use it on each split.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

try:  # pandas is only needed to accept DataFrame input.
    import pandas as pd
except ImportError:  # pragma: no cover - exercised only in minimal installs
    pd = None


FEATURE_COLUMNS = (
    "mag_ps_g",
    "mag_ps_r",
    "mag_ps_i",
    "mag_ps_z",
    "mag_ps_y",
    "gaia_g_mean_mag",
)


class TrainOnlyPreprocessor(BaseEstimator, TransformerMixin):
    """A small sklearn-style transformer whose learned state comes only from fit.

    Parameters
    ----------
    scaler:
        ``"standard"`` (mean/std), ``"robust"`` (median/IQR), or ``"none"``.
    winsorize:
        If true, clip each feature at training-partition quantiles before scaling.
    winsor_limits:
        Lower and upper quantiles used when winsorization is enabled.
    outlier_sigma:
        Robust-sigma threshold used by :meth:`outlier_mask`.

    DataFrames must contain precisely the six ``FEATURE_COLUMNS`` in that order.
    NumPy arrays must have six columns in the same order. IDs, labels, and any
    other columns are rejected rather than silently included in the transform.
    """

    def __init__(
        self,
        scaler: str = "standard",
        winsorize: bool = False,
        winsor_limits: tuple[float, float] = (0.005, 0.995),
        outlier_sigma: float = 8.0,
    ) -> None:
        if scaler not in {"standard", "robust", "none"}:
            raise ValueError("scaler must be 'standard', 'robust', or 'none'")
        if len(winsor_limits) != 2 or not (0 <= float(winsor_limits[0]) < float(winsor_limits[1]) <= 1):
            raise ValueError("winsor_limits must be an increasing pair within [0, 1]")
        if not np.isfinite(outlier_sigma) or outlier_sigma <= 0:
            raise ValueError("outlier_sigma must be positive and finite")
        self.scaler = scaler
        # Keep constructor parameters untouched so sklearn.clone can reproduce us.
        self.winsorize = winsorize
        self.winsor_limits = winsor_limits
        self.outlier_sigma = outlier_sigma

    def _array(self, X: Any) -> np.ndarray:
        if pd is not None and isinstance(X, pd.DataFrame):
            actual = tuple(X.columns)
            if actual != FEATURE_COLUMNS:
                raise ValueError(
                    "DataFrame columns must exactly match FEATURE_COLUMNS in order; "
                    f"got {actual!r}"
                )
            try:
                arr = X.to_numpy(dtype=np.float64, copy=True)
            except (TypeError, ValueError) as exc:
                raise ValueError("all feature columns must be numeric") from exc
        else:
            try:
                arr = np.asarray(X, dtype=np.float64)
            except (TypeError, ValueError) as exc:
                raise ValueError("X must be a numeric array or correctly named DataFrame") from exc
            if arr.ndim != 2:
                raise ValueError("X must be a two-dimensional array with six columns")
            if arr.shape[1] != len(FEATURE_COLUMNS):
                raise ValueError(f"X must have exactly {len(FEATURE_COLUMNS)} feature columns")
            arr = np.array(arr, dtype=np.float64, copy=True)
        if arr.ndim != 2 or arr.shape[1] != len(FEATURE_COLUMNS):
            raise ValueError(f"X must have exactly {len(FEATURE_COLUMNS)} feature columns")
        if arr.shape[0] == 0:
            raise ValueError("X must contain at least one row")
        if not np.isfinite(arr).all():
            raise ValueError("X contains NaN or infinite values")
        return arr

    def fit(self, X: Any, y: Any = None) -> "TrainOnlyPreprocessor":
        """Learn clipping, scaling, and outlier reference statistics from X only."""
        del y  # accepted for sklearn compatibility; labels are never used
        arr = self._array(X)
        self.n_fit_rows_ = int(arr.shape[0])
        self.feature_columns_ = FEATURE_COLUMNS
        self.medians_ = np.median(arr, axis=0)

        if self.winsorize:
            self.clip_lower_ = np.quantile(arr, self.winsor_limits[0], axis=0)
            self.clip_upper_ = np.quantile(arr, self.winsor_limits[1], axis=0)
        else:
            self.clip_lower_ = np.full(arr.shape[1], -np.inf)
            self.clip_upper_ = np.full(arr.shape[1], np.inf)

        # Outlier reference uses raw fit-partition magnitudes, independently of
        # whether the optional transform clipping is enabled.
        q25, q75 = np.quantile(arr, [0.25, 0.75], axis=0)
        mad = np.median(np.abs(arr - self.medians_), axis=0)
        robust_sigma = 1.4826 * mad
        iqr_fallback = (q75 - q25) / 1.349
        use_iqr = robust_sigma == 0
        robust_sigma[use_iqr] = iqr_fallback[use_iqr]
        self.outlier_scales_ = robust_sigma
        self.outlier_medians_ = self.medians_.copy()

        clipped = self._clip(arr)
        if self.scaler == "standard":
            self.center_ = np.mean(clipped, axis=0)
            self.scale_ = np.std(clipped, axis=0)
        elif self.scaler == "robust":
            self.center_ = np.median(clipped, axis=0)
            p25, p75 = np.quantile(clipped, [0.25, 0.75], axis=0)
            self.scale_ = p75 - p25
        else:
            self.center_ = np.zeros(arr.shape[1], dtype=np.float64)
            self.scale_ = np.ones(arr.shape[1], dtype=np.float64)
        # Constant or degenerate dimensions are left centered with unit scale.
        self.scale_ = np.where(self.scale_ > 0, self.scale_, 1.0)
        if not np.isfinite(self.center_).all() or not np.isfinite(self.scale_).all() or np.any(self.scale_ <= 0):
            raise ValueError("learned centers and scales must be finite with positive scales")
        self.training_inlier_mask_ = ~self.outlier_mask(arr)
        return self

    def _check_fitted(self) -> None:
        if not hasattr(self, "n_fit_rows_"):
            raise RuntimeError("preprocessor must be fitted before this operation")

    def _clip(self, arr: np.ndarray) -> np.ndarray:
        if not self.winsorize:
            return arr
        return np.clip(arr, self.clip_lower_, self.clip_upper_)

    def transform(self, X: Any) -> np.ndarray:
        """Clip if configured and scale X without changing its row count."""
        self._check_fitted()
        arr = self._array(X)
        transformed = (self._clip(arr) - self.center_) / self.scale_
        if transformed.shape[0] != arr.shape[0]:  # defensive invariant
            raise RuntimeError("transform unexpectedly changed the number of rows")
        return transformed

    def fit_transform(self, X: Any, y: Any = None, **fit_params: Any) -> np.ndarray:
        if fit_params:
            raise TypeError(f"unsupported fit parameters: {', '.join(fit_params)}")
        return self.fit(X, y=y).transform(X)

    def outlier_mask(self, X: Any) -> np.ndarray:
        """Return one boolean per row; true means any feature is an outlier.

        A nonzero MAD is converted to Gaussian-equivalent sigma using 1.4826.
        If MAD is zero, IQR/1.349 is used. A constant fit feature has both zero,
        so any held-out value different from the learned median is flagged.
        """
        self._check_fitted()
        arr = self._array(X)
        scales = self.outlier_scales_
        constant = scales == 0
        deviations = np.abs(arr - self.outlier_medians_)
        feature_outliers = np.zeros_like(deviations, dtype=bool)
        nonconstant = ~constant
        feature_outliers[:, nonconstant] = (
            deviations[:, nonconstant] > self.outlier_sigma * scales[nonconstant]
        )
        feature_outliers[:, constant] = deviations[:, constant] > 0
        return np.any(feature_outliers, axis=1)

    def training_inlier_mask(self, X: Any = None) -> np.ndarray:
        """Return fit-partition inliers, or inliers for explicitly supplied X.

        With no argument this returns a copy of the mask computed during fit.
        Supplying X evaluates it against the fit-only outlier reference.
        """
        self._check_fitted()
        if X is None:
            return self.training_inlier_mask_.copy()
        return ~self.outlier_mask(X)

    def summary(self) -> dict[str, Any]:
        """Return JSON-compatible fit metadata for reproducible experiment logs."""
        self._check_fitted()
        return {
            "feature_columns": list(FEATURE_COLUMNS),
            "scaler": self.scaler,
            "winsorize": self.winsorize,
            "winsor_limits": [float(x) for x in self.winsor_limits],
            "outlier_sigma": self.outlier_sigma,
            "n_fit_rows": self.n_fit_rows_,
            "medians": self.medians_.tolist(),
            "centers": self.center_.tolist(),
            "scales": self.scale_.tolist(),
            "clip_lower": [float(v) if np.isfinite(v) else None for v in self.clip_lower_],
            "clip_upper": [float(v) if np.isfinite(v) else None for v in self.clip_upper_],
            "outlier_scales": self.outlier_scales_.tolist(),
        }

    def summary_json(self, **kwargs: Any) -> str:
        """Serialize :meth:`summary` as JSON."""
        return json.dumps(self.summary(), **kwargs)

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        """Expose the fixed feature order using the sklearn transformer convention."""
        if input_features is not None and tuple(input_features) != FEATURE_COLUMNS:
            raise ValueError("input_features must exactly match FEATURE_COLUMNS in order")
        return np.asarray(FEATURE_COLUMNS, dtype=object)
