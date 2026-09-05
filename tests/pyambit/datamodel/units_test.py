"""Unit-conversion claims for :mod:`pyambit.units`.

Named as claims rather than as "test_concentration_1": each one states a property the
rest of pyambit relies on, so a failure names the broken assumption.
"""

import pytest
from measurement.utils import guess

from pyambit.units import (
    Concentration,
    ConcentrationMolar,
    ConcentrationSurface,
    Dose,
    Molar,
    Percent,
)


def test_microgram_per_ml_and_milligram_per_litre_are_the_same_concentration():
    """ug/mL == mg/L exactly, so records in either unit consolidate."""
    assert Concentration(**{"ug__ml": 10.0}).mg__l == pytest.approx(10.0)
    assert Concentration(mg__l=10.0).ug__ml == pytest.approx(10.0)


def test_mass_and_molar_concentration_are_separate_dimensions():
    """No molar mass exists for a nanomaterial, so the two must never interconvert.

    ``measurement`` refuses with ``KeyError`` rather than ``AttributeError`` -- the
    same alias collision that makes ``pynanomapper.units.convert_units`` unusable.
    What matters is that it raises instead of returning a plausible wrong number.
    """
    mass = Concentration(**{"ug__ml": 10.0})
    with pytest.raises((AttributeError, KeyError)):
        mass.umol__l

    molar = ConcentrationMolar(umol__l=10.0)
    with pytest.raises((AttributeError, KeyError)):
        molar.ug__ml


def test_molar_concentration_converts_within_its_own_dimension():
    assert ConcentrationMolar(umol__l=5000.0).mmol__l == pytest.approx(5.0)
    assert ConcentrationMolar(mol__l=1.0).mmol__l == pytest.approx(1000.0)


def test_the_micro_sign_spelling_resolves_to_the_ascii_unit():
    """AMBIT records carry both 'ug/ml' and the U+00B5 micro sign."""
    resolved = guess(10.0, "µg/ml", measures=[Concentration])
    assert isinstance(resolved, Concentration)
    assert resolved.mg__l == pytest.approx(10.0)


def test_surface_area_dose_has_a_conversion_path():
    """study_config lists concentration_surface as a dose field; it needs a measure."""
    assert ConcentrationSurface(sq_cm__ml=2.0).sq_cm__l == pytest.approx(2000.0)


def test_percent_covers_the_genotox_dna_in_tail_spellings():
    """The genotox readout is recorded under several spellings of the same unit."""
    for spelling in ("%", "%DNA IN TAIL", "% DNA in Tail", "%DNA in Tail"):
        assert Percent(**{spelling: 12.0}).percent == pytest.approx(12.0)


def test_molar_amount_units():
    assert Molar(umol=1000.0).mmol == pytest.approx(1.0)
    assert Molar(**{"micromol": 1000.0}).mmol == pytest.approx(1.0)


def test_dose_is_volume_per_weight():
    assert Dose(**{"l/kg": 2.0}).l__kg == pytest.approx(2.0)
