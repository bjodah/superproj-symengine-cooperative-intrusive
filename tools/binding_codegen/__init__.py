"""Typed shared binding specification support.

This package intentionally has no renderer imports yet.  Phase 1 establishes
the validated intermediate representation that later renderers will consume.
"""

from .model import BindingSpec, SpecValidationError, load_spec, validate_spec

__all__ = ("BindingSpec", "SpecValidationError", "load_spec", "validate_spec")
