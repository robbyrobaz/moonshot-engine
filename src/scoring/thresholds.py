"""Helpers for safe entry threshold selection."""

import config


def effective_entry_threshold(
    entry_threshold: float | int | None,
    invalidation_threshold: float | int | None = None,
) -> float:
    """Clamp entry thresholds to avoid guaranteed invalidations."""
    thresholds = [config.ENTRY_THRESHOLD_FLOOR]
    if entry_threshold is not None:
        thresholds.append(float(entry_threshold))
    if invalidation_threshold is not None:
        thresholds.append(float(invalidation_threshold))
    return max(thresholds)
