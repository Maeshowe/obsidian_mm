"""
OBSIDIAN MM Guardrails Module.

Operational guardrails to ensure the system remains:
- Diagnostic (not predictive)
- Stable across regimes
- Honest under incomplete data
- Resistant to silent drift
- Interpretable by humans

See docs/GUARDRAILS.md for full documentation.
"""

from obsidian.guardrails.types import (
    InstrumentType,
    DataCompleteness,
    GuardrailViolation,
    BaselineDriftWarning,
)
from obsidian.guardrails.validators import (
    validate_instrument_type,
    validate_data_completeness,
    validate_greeks_sign_convention,
    check_baseline_drift,
)
from obsidian.guardrails.conventions import (
    GREEKS_SIGN_CONVENTION,
    GreeksSignConvention,
)

__all__ = [
    # Types
    "InstrumentType",
    "DataCompleteness",
    "GuardrailViolation",
    "BaselineDriftWarning",
    # Validators
    "validate_instrument_type",
    "validate_data_completeness",
    "validate_greeks_sign_convention",
    "check_baseline_drift",
    # Conventions
    "GREEKS_SIGN_CONVENTION",
    "GreeksSignConvention",
]
