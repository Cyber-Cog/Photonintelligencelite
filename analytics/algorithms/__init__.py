"""Algorithm modules. Importing this package registers every algorithm via
``analytics.core.registry.register_algorithm``. The orchestrator never imports algorithm
modules directly — it only reads from the registry populated here.
"""
from analytics.algorithms import (  # noqa: F401  (import-for-registration side effects)
    box_plot,
    clipping_current,
    clipping_power,
    disconnected_strings,
    inverter_efficiency,
    module_damage,
    string_outlier,
)

__all__ = [
    "box_plot",
    "clipping_current",
    "clipping_power",
    "disconnected_strings",
    "inverter_efficiency",
    "module_damage",
    "string_outlier",
]
