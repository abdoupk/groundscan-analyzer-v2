"""Detector pins ported to the refactored layout (fast regression)."""

import numpy as np

from groundscan import ScanData, ScanMetadata
from groundscan.core.anomaly import detect_anomalies
from groundscan.core.grid import reconstruct_grid


def _constant_field(n=16, spike=None):
    signal = np.zeros((n, n))
    if spike is not None:
        signal[spike] = 50.0
    x, y = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    return ScanData(
        x=x.ravel(), y=y.ravel(), z=np.zeros(n * n), signal=signal.ravel(), metadata=ScanMetadata()
    )


def test_single_spike_on_constant_field_yields_no_confident_candidate():
    scan = _constant_field(spike=(8, 8))
    grid = reconstruct_grid(scan)
    anomaly = detect_anomalies(grid, threshold=3.0, min_size=3)
    assert np.isfinite(np.asarray(anomaly.zscore)).all()
    # Single-cell spike must not survive the min-size + persistence guard.
    assert anomaly.n_components == 0
    assert (np.asarray(anomaly.labels) == 0).all()
