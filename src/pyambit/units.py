"""eNanoMapper-specific unit conversion, built on the ``measurement`` package.

``measurement`` (https://python-measurement.readthedocs.io/) implements SI-prefixed
measures and bidimensional ratios (e.g. weight-per-volume) generically, but has no
notion of a concentration, a molar concentration, or the alternative spellings AMBIT
records use for them ("micrograms per ml", "% DNA in Tail", ...). This module adds
those, so the rest of pyambit can convert a recorded ``unit`` string without a
dependency on ``pynanomapper`` -- which depends on pyambit, not the other way round.

Do not port ``pynanomapper.units.convert_units``: it accepts a ``measures=`` argument
and never forwards it to ``measurement.utils.guess``, so it silently returns ``None``
for every concentration unit, and calling ``guess`` directly with an explicit measure
list raises ``KeyError: 'umol'`` from an alias collision. Construct the measure
classes directly instead, e.g. ``Concentration(ug__ml=10).mg__l``.
"""

from __future__ import annotations

from measurement.base import BidimensionalMeasure, MeasureBase
from measurement.measures import Area, Volume, Weight

__all__ = [
    "Concentration",
    "ConcentrationMolar",
    "ConcentrationSurface",
    "Dose",
    "Molar",
    "Percent",
]


class Percent(MeasureBase):
    """A bare percentage, plus the genotox-specific "DNA in tail" spellings."""

    STANDARD_UNIT = "percent"
    UNITS = {"percent": 1.0}
    ALIAS = {
        "%": "percent",
        "%DNA IN TAIL": "percent",
        "% DNA in Tail": "percent",
        "%DNA in Tail": "percent",
        "% DNA IN TAIL": "percent",
    }
    SI_UNITS = ["percent"]


class Molar(MeasureBase):
    """Amount of substance, in mol/mmol/umol.

    Deliberately narrower than a full molar-mass-aware unit system: nM and pM are
    handled as a fallback table in :mod:`pyambit.bmd`, since converting them here
    would need a reference concentration this class does not have.
    """

    STANDARD_UNIT = "mol"
    UNITS = {
        "mol": 1.0,
        "µmol": 1e-6,
        "umol": 1e-6,
        "mmol": 1e-3,
    }
    ALIAS = {
        "micromol": "umol",
        "millimol": "mmol",
    }
    SI_UNITS = ["mol"]


class Concentration(BidimensionalMeasure):
    """Mass-per-volume concentration (ug/mL, mg/L, g/L, ...)."""

    PRIMARY_DIMENSION = Weight
    REFERENCE_DIMENSION = Volume

    ALIAS = {
        "mg/l": "mg__l",
        "ug/l": "ug__l",
        "g/l": "g__l",
        "µg/l": "ug__l",
        "µg/ml": "ug__ml",
        "microgram/l": "ug__l",
        "micrograms per ml": "ug__ml",
        "milligram per l": "mg__l",
        "milligram / l": "mg__l",
        "micrograms per mL": "ug__ml",
    }


class ConcentrationMolar(BidimensionalMeasure):
    """Molar concentration (umol/L, mmol/L, ...).

    Kept as a dimension separate from :class:`Concentration`: converting between
    mass-per-volume and molar-per-volume needs a molar mass, which a nanomaterial
    does not have. A record in one dimension is never merged with one in the other.
    """

    PRIMARY_DIMENSION = Molar
    REFERENCE_DIMENSION = Volume

    ALIAS = {
        "mmol/l": "mmol__l",
        "umol/l": "umol__l",
        "mol/l": "mol__l",
        "µmol/l": "umol__l",
        "µmol/ml": "umol__ml",
        "micromol/l": "umol__l",
        "micromol per ml": "umol__l",
        "millimol per l": "mmol__l",
        "millimol / l": "mmol__l",
        "micromol per mL": "umol__ml",
    }


class ConcentrationSurface(BidimensionalMeasure):
    """Surface-area-per-volume dose (cm2/mL, ...).

    ``study_config._DOSE_KEYS`` lists ``concentration_surface`` as a dose field, for
    assays that report exposure as surface area rather than mass or moles. Yet a
    third dimension, never interconverted with the other two.
    """

    PRIMARY_DIMENSION = Area
    REFERENCE_DIMENSION = Volume

    ALIAS = {
        "cm2/ml": "sq_cm__ml",
        "cm2/l": "sq_cm__l",
        "cm²/ml": "sq_cm__ml",
        "cm²/l": "sq_cm__l",
        "sq cm/ml": "sq_cm__ml",
        "square cm per ml": "sq_cm__ml",
    }


class Dose(BidimensionalMeasure):
    """Volume-per-weight dose (l/kg)."""

    PRIMARY_DIMENSION = Volume
    REFERENCE_DIMENSION = Weight

    ALIAS = {"l/kg": "l__kg"}
