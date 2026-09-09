"""The curation pipeline: AI-generated problem curation with a verification
gate and a dual-oracle differential check. Separate from the tutor on
purpose (never-solve rule 1)."""

from dojo.curator.curator import (
    CuratorError,
    apply,
    curate_dual,
    differential_check,
    make_isolated_namespace,
    propose,
    validate,
)

__all__ = [
    "CuratorError",
    "apply",
    "curate_dual",
    "differential_check",
    "make_isolated_namespace",
    "propose",
    "validate",
]
