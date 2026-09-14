"""The curation pipeline: AI-generated problem curation with a verification
gate and a dual-oracle differential check. Separate from the tutor on
purpose (never-solve rule 1)."""

from dojo.curator.curator import (
    CuratorError,
    add_reference,
    apply,
    audit_curation,
    curate_dual,
    differential_check,
    make_isolated_namespace,
    propose,
    reference_findings,
    validate,
)

__all__ = [
    "CuratorError",
    "add_reference",
    "apply",
    "audit_curation",
    "curate_dual",
    "differential_check",
    "make_isolated_namespace",
    "propose",
    "reference_findings",
    "validate",
]
