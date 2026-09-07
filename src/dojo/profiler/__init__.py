"""Profiler facade: measure, then classify time and space."""

from dojo.profiler.fit import FitResult, classify
from dojo.profiler.measure import DEFAULT_SIZES, Measurement, measure

__all__ = ["DEFAULT_SIZES", "FitResult", "Measurement", "classify", "measure"]
