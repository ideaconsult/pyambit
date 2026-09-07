"""Per-category study configuration shared with the jToxKit viewer.

`resources/study_config.json` is generated from the jToxKit React configs
(``jtoxkit-react/src/config/*.js``) by ``scripts/export-study-config.mjs`` — render
functions stripped, field roles preserved. It is the single source of truth for which
AMBIT condition carries the dose/concentration axis, which carries the control/treatment
designation, and which carry cell type / exposure time / method, **per endpoint category**.

pyambit uses this to drive ``convert_effectrecords2array`` (dose-axis selection) instead of
the hardcoded ``CONCENTRATION`` rule, and the eNanoMapper metadata pipeline uses it to build
config-correct Solr facet queries. Keep the JSON in sync by re-running the export script.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Dict, List, Optional

# Condition keys recognised as a dose/concentration axis even when the per-field "title" is
# absent. Titles "Concentration"/"Dose" are the primary signal; these cover the unit variants
# stored side by side (mass/volume/surface) and the ECOTOX "dose" axis.
_DOSE_KEYS = {
    "concentration",
    "concentration_mass",
    "concentration_ml",
    "concentration_surface",
    "dose",
    "total dose",
}
_DOSE_TITLES = {"concentration", "dose"}

# Condition keys recognised as the control–treatment designation, in preference order.
# `material` (title "Treatment") is the field that actually carries Positive/Negative/none
# in real eNanoMapper data; `treatment_condition` is the older/alternate slot.
_CONTROL_KEYS = ("material", "treatment_condition", "treatment")
_CONTROL_TITLES = {"treatment", "treatment condition"}

_SEMANTIC_TITLES = {
    "cell": "cell type",
    "time": "exposure time",
    "method": "method",
}


@lru_cache(maxsize=1)
def study_config() -> Dict:
    """The full per-category config (``{"columns": {CATEGORY: {...}}, ...}``)."""
    with resources.files("pyambit").joinpath("resources/study_config.json").open(
        "r", encoding="utf-8"
    ) as fh:
        return json.load(fh)


def _columns() -> Dict:
    return study_config().get("columns", {})


def category_config(category: Optional[str]) -> Dict:
    """Config block for one endpoint category, merged over the ``_`` defaults."""
    cols = _columns()
    base = dict(cols.get("_", {}))
    cat = cols.get(category, {}) if category else {}
    merged = dict(base)
    for section, fields in cat.items():
        if isinstance(fields, dict) and isinstance(merged.get(section), dict):
            merged[section] = {**merged[section], **fields}
        else:
            merged[section] = fields
    return merged


def _section(category: Optional[str], section: str) -> Dict:
    block = category_config(category).get(section, {})
    return block if isinstance(block, dict) else {}


def _title(field: Dict) -> str:
    return str((field or {}).get("title", "")).strip().lower()


def dose_condition_fields(category: Optional[str] = None) -> List[str]:
    """Condition keys that form the dose/concentration axis for this category.

    The first entry is the primary axis; the rest are unit-variant alternates
    (e.g. ``concentration`` then ``concentration_mass``).
    """
    conditions = _section(category, "conditions")
    primary, alternates = [], []
    for key, field in conditions.items():
        if not isinstance(field, dict):
            continue
        klow = key.lower()
        is_dose = klow in _DOSE_KEYS or _title(field) in _DOSE_TITLES
        if not is_dose:
            continue
        if klow in ("concentration", "dose"):
            primary.append(key)
        else:
            alternates.append(key)
    return primary + alternates


def control_field(category: Optional[str] = None) -> Optional[str]:
    """Condition key carrying the control/treatment designation, or ``None``.

    Prefers ``material`` (the field that actually holds Positive/Negative/none in real data)
    over the alternate ``treatment_condition`` slot.
    """
    conditions = _section(category, "conditions")
    present = {k.lower(): k for k, v in conditions.items() if isinstance(v, dict)}
    for preferred in _CONTROL_KEYS:
        if preferred in present:
            return present[preferred]
    for key, field in conditions.items():
        if isinstance(field, dict) and _title(field) in _CONTROL_TITLES:
            return key
    return None


def _semantic_field(category: Optional[str], title: str) -> Optional[str]:
    for section in ("conditions", "parameters"):
        for key, field in _section(category, section).items():
            if isinstance(field, dict) and _title(field) == title:
                return key
    return None


def cell_field(category: Optional[str] = None) -> Optional[str]:
    return _semantic_field(category, _SEMANTIC_TITLES["cell"])


def exposure_time_field(category: Optional[str] = None) -> Optional[str]:
    return _semantic_field(category, _SEMANTIC_TITLES["time"])


def method_field(category: Optional[str] = None) -> Optional[str]:
    return _semantic_field(category, _SEMANTIC_TITLES["method"])
