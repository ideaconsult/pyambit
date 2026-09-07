"""Benchmark concentration from AMBIT records.

The claims here are the ones that decide whether a BMD produced this way can be
reported: the grouping must follow the protocol, the interval must contain the truth
at its nominal rate, and the failure modes must be visible rather than silent.
"""

from __future__ import annotations

import numpy as np

import pyambit.datamodel as mb
import pytest
from pyambit.bmd import (
    bmd_cdf,
    bmd_recovery,
    bmd_vector,
    BmdSpec,
    consolidate_providers,
    DoseSeries,
    PropertyKey,
    series_from_protocol_application,
    series_from_substance,
)

CONC = np.array([0.0, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0])
BMR = (10.0, 20.0, 50.0, 80.0)
TRUE_EC50 = 12.0


def viability(c, ec50=TRUE_EC50, top=100.0):
    with np.errstate(divide="ignore"):
        x = np.log10(np.where(c > 0, c, 1e-9))
    return np.where(c > 0, top / (1.0 + 10 ** (x - np.log10(ec50))), top)


def true_bmd(levels=BMR, ec50=TRUE_EC50):
    """log10 concentration producing r units of decrease from a 100 % control."""
    return [float(np.log10(ec50 * (r / (100.0 - r)))) for r in levels]


def papp(
    lab="lab_A",
    ec50=TRUE_EC50,
    noise=4.0,
    time=24.0,
    cell="A549",
    n_rep=3,
    seed=0,
    endpoint="Viability",
    method="MTT",
    conc_unit="ug/mL",
    citation_owner=None,
    company_name=None,
    extra_parameters=None,
):
    rng = np.random.default_rng(seed)
    effects = []
    for c in CONC:
        for rep in range(n_rep):
            effects.append(
                mb.EffectRecord(
                    endpoint=endpoint,
                    endpointtype="TOXICITY",
                    result=mb.EffectResult(
                        loValue=float(
                            viability(np.array([c]), ec50)[0] + rng.normal(0, noise)
                        ),
                        errorValue=noise,
                        errQualifier="SD",
                        unit="%",
                    ),
                    conditions={
                        "CONCENTRATION": mb.Value(loValue=float(c), unit=conc_unit),
                        "EXPOSURE_TIME": mb.Value(loValue=time, unit="h"),
                        "REPLICATE": rep,
                    },
                )
            )
    citation = None
    if citation_owner is not None:
        citation = mb.Citation(owner=citation_owner, title="study", year=2015)
    return mb.ProtocolApplication(
        protocol=mb.Protocol(
            topcategory="TOX",
            category=mb.EndpointCategory(code="ENM_0000068_SECTION"),
        ),
        effects=effects,
        citation=citation,
        owner=mb.SampleLink(
            substance=mb.Sample(uuid="S1"),
            company=mb.Company(uuid=lab, name=company_name or lab),
        ),
        parameters={
            "E.method": method,
            "E.cell_type": cell,
            "MEDIUM": "DMEM",
            **(extra_parameters or {}),
        },
    )


def substance(studies, name="NM-101"):
    return mb.SubstanceRecord(name=name, i5uuid="SUB-1", study=studies)


SPEC = BmdSpec(benchmark_responses=BMR, n_bootstrap=300, log_window=(-1.0, 3.0), seed=0)


# ----------------------------------------------------------------------
# the adapter and the grouping key
# ----------------------------------------------------------------------
def test_replicate_is_not_part_of_the_property_key():
    """The bug that makes an interval look perfect.

    A per-well REPLICATE index is a real array dimension, as it should be. But for
    estimating a BMD the three wells at one concentration are three measurements of
    one point, not three properties. Reading them as separate series would leave one
    observation per concentration and the bootstrap nothing to resample -- BMDL, BMD
    and BMDU collapse and the result reads as certainty.
    """
    grouped = series_from_substance(substance([papp(n_rep=3)]))
    assert len(grouped) == 1
    key = next(iter(grouped))
    assert isinstance(key, PropertyKey)
    assert "REPLICATE" not in str(key)
    assert key.conditions == ()
    series = grouped[key]["lab_A"][0]
    assert series.n_observations == CONC.size * 3

    profile = bmd_cdf(series, SPEC)
    assert np.all(profile.bmdu[profile.determined] > profile.bmdl[profile.determined])


def test_reading_a_record_does_not_mutate_it():
    """bmd.py is a reader. The model it reads must come back untouched.

    The replicate index is a real array dimension and stays one -- NeXus needs it to
    write each well. Gathering it into repeated observations happens only in the
    DoseSeries handed to the bootstrap, never on the EffectArray.
    """
    record = papp()
    before_effects = len(record.effects)
    before_types = [type(e).__name__ for e in record.effects]
    before_conditions = [dict(e.conditions) for e in record.effects]
    before_values = [e.result.loValue for e in record.effects]

    arrays, _ = record.convert_effectrecords2array()
    array = arrays[0]
    axis_names = list(array.axes)
    axis_values = {k: np.array(v.values, copy=True) for k, v in array.axes.items()}
    signal_before = np.array(array.signal.values, copy=True)
    signal_shape = array.signal.values.shape

    series_from_protocol_application(record)

    # The record itself is untouched.
    assert len(record.effects) == before_effects
    assert [type(e).__name__ for e in record.effects] == before_types
    assert [dict(e.conditions) for e in record.effects] == before_conditions
    assert [e.result.loValue for e in record.effects] == before_values

    # And so is the array: the replicate axis is still an axis, same shape, same data.
    assert list(array.axes) == axis_names
    assert "REPLICATE" in axis_names
    assert array.signal.values.shape == signal_shape
    assert np.array_equal(array.signal.values, signal_before)
    for name, values in axis_values.items():
        assert np.array_equal(array.axes[name].values, values)


def test_a_record_still_writes_to_nexus_after_being_read_for_bmd():
    """The NeXus path is unaffected: same tree before and after a BMD read."""
    nx = pytest.importorskip("nexusformat.nexus.tree")
    from pyambit import nexus_writer  # noqa: F401  (registers to_nexus)

    import re

    def tree_of(record):
        root = nx.NXroot()
        substance([record]).to_nexus(root)
        # The writer stamps a creation time; normalise it so the comparison is
        # about the data, not about when the two trees were built.
        return re.sub(r"\d{2}:\d{2}:\d{2}\.\d+", "<time>", str(root.tree))

    untouched = papp()
    read_first = papp()
    series_from_protocol_application(read_first)

    assert tree_of(read_first) == tree_of(untouched)


def test_the_setup_lives_in_parameters_and_defines_the_property():
    """Cell line and method are ``ProtocolApplication.parameters`` in the AMBIT
    model, not ``EffectRecord.conditions``, and cell type gets its own key field."""
    grouped = series_from_substance(substance([papp(cell="A549"), papp(cell="HepG2")]))
    assert len(grouped) == 2
    assert {k.cell_type for k in grouped} == {"A549", "HepG2"}

    methods = series_from_substance(
        substance([papp(method="MTT"), papp(method="WST-1")])
    )
    assert {k.method for k in methods} == {"MTT", "WST-1"}


def test_bookkeeping_parameters_do_not_split_the_property():
    """Operator, preparation date and input filename identify who ran the study and
    when, not what was measured -- so two laboratories that differ only in those
    must still land under one PropertyKey and reach consolidate_providers together.

    This was a real failure: an earlier version folded every leftover
    ``ProtocolApplication.parameter`` into the key verbatim, and two independent
    laboratories essentially never share an operator name or a preparation date. On
    real AMBIT data every property came out with exactly one provider as a result --
    consolidate_providers's whole reason for existing never ran.
    """
    lab_a = papp(
        lab="lab_A",
        citation_owner="lab_A",
        extra_parameters={
            "OPERATOR": "J. Smith",
            "DATE_OF_PREPARATION": "2018-01-04",
            "__input_file": "lab_a_batch1.xlsx",
            "DISPERSION_MEDIUM": "0.5% BSA, prewetted",
        },
    )
    lab_b = papp(
        lab="lab_B",
        citation_owner="lab_B",
        seed=1,
        extra_parameters={
            "OPERATOR": "A. Dupont",
            "DATE_OF_PREPARATION": "2019-11-22",
            "__input_file": "labB_run3_final.xlsx",
            "DISPERSION_MEDIUM": "sonicated in serum-free medium",
        },
    )
    grouped = series_from_substance(substance([lab_a, lab_b]))
    assert len(grouped) == 1
    (by_provider,) = grouped.values()
    assert set(by_provider) == {"lab_A", "lab_B"}


def test_protocol_identity_uses_topcategory_and_category_not_endpoint():
    """``Protocol.endpoint`` is not curated in practice, so it is not used."""
    key = next(iter(series_from_substance(substance([papp()]))))
    assert key.topcategory == "TOX"
    assert key.category == "ENM_0000068_SECTION"
    assert key.method == "MTT"


def test_exposure_time_is_part_of_the_property():
    """A benchmark concentration at 24 h and one at 48 h are two properties."""
    grouped = series_from_substance(substance([papp(time=24.0), papp(time=48.0)]))
    assert len(grouped) == 2
    assert sorted(k.hours for k in grouped) == [24.0, 48.0]
    assert all(len(v["lab_A"]) == 1 for v in grouped.values())


def test_exposure_time_is_normalised_to_hours():
    minutes = papp(time=24.0)
    for effect in minutes.effects:
        effect.conditions["EXPOSURE_TIME"] = mb.Value(loValue=1440.0, unit="min")
    key = next(iter(series_from_substance(substance([minutes]))))
    assert key.hours == pytest.approx(24.0)


def test_exposure_time_from_parameters_is_in_the_property_key():
    """Real records put the exposure time in ``parameters``, not in conditions.

    Searching only the conditions misses it, and two durations then merge into one
    bootstrap.
    """
    from_parameters = papp(time=24.0)
    for effect in from_parameters.effects:
        del effect.conditions["EXPOSURE_TIME"]
    from_parameters.parameters["E.EXPOSURE_TIME"] = mb.Value(loValue=24.0, unit="h")

    key = next(iter(series_from_substance(substance([from_parameters]))))
    assert key.hours == pytest.approx(24.0)


def test_endpoints_are_separate_properties():
    grouped = series_from_substance(
        substance([papp(endpoint="Viability"), papp(endpoint="LDH")])
    )
    assert {k.endpoint for k in grouped} == {"Viability", "LDH"}


def test_incompatible_concentration_units_are_not_merged():
    """ug/mL and uM cannot be converted without a molar mass -- which a
    nanomaterial does not have -- so they must remain separate properties."""
    grouped = series_from_substance(
        substance(
            [
                papp(lab="lab_A", conc_unit="ug/mL"),
                papp(lab="lab_B", conc_unit="uM"),
            ]
        )
    )
    assert len(grouped) == 2
    assert {k.concentration_unit for k in grouped} == {"mg/L", "umol/L"}


def test_identical_units_spelled_differently_are_merged():
    """ug/mL and mg/L are the same unit, so the two laboratories consolidate."""
    grouped = series_from_substance(
        substance(
            [
                papp(lab="lab_A", conc_unit="ug/mL"),
                papp(lab="lab_B", conc_unit="mg/L"),
            ]
        )
    )
    assert len(grouped) == 1
    assert set(next(iter(grouped.values()))) == {"lab_A", "lab_B"}


def test_concentrations_are_converted_not_just_relabelled():
    """mg/mL is a thousand times mg/L, and the numbers must move accordingly --
    via the measurement package, through pyambit.units.Concentration."""
    in_mg_per_l = series_from_protocol_application(papp(conc_unit="mg/L"))[0]
    in_mg_per_ml = series_from_protocol_application(papp(conc_unit="mg/mL"))[0]
    assert in_mg_per_l.concentration_unit == in_mg_per_ml.concentration_unit == "mg/L"
    positive = in_mg_per_l.concentration > 0
    assert np.allclose(
        in_mg_per_ml.concentration[positive],
        1000.0 * in_mg_per_l.concentration[positive],
        rtol=1e-9,
    )


def test_molar_units_convert_among_themselves_but_never_to_mass():
    grouped = series_from_substance(
        substance(
            [
                papp(lab="lab_A", conc_unit="uM"),
                papp(lab="lab_B", conc_unit="mmol/L"),
                papp(lab="lab_C", conc_unit="ug/mL"),
            ]
        )
    )
    by_unit = {k.concentration_unit: v for k, v in grouped.items()}
    assert set(by_unit) == {"umol/L", "mg/L"}
    assert set(by_unit["umol/L"]) == {"lab_A", "lab_B"}
    assert set(by_unit["mg/L"]) == {"lab_C"}


def test_an_unconvertible_unit_keeps_its_own_key():
    """ppm is mg/L only for dilute aqueous media, so it is deliberately not
    converted -- an unrecognised unit is separated, never merged on a guess."""
    grouped = series_from_substance(
        substance(
            [
                papp(lab="lab_A", conc_unit="mg/L"),
                papp(lab="lab_B", conc_unit="ppm"),
            ]
        )
    )
    assert {k.concentration_unit for k in grouped} == {"mg/L", "ppm"}


def test_provider_is_the_laboratory_not_the_project():
    """``owner.company.name`` is the funding project; ``citation.owner`` is the lab.

    Reading the project first collapses every laboratory in it into one provider,
    and consolidation silently becomes a no-op -- the between-laboratory spread it
    exists to measure vanishes with no error raised.
    """
    grouped = series_from_substance(
        substance(
            [
                papp(company_name="NANoREG", citation_owner="KI"),
                papp(company_name="NANoREG", citation_owner="NRCWE"),
            ]
        )
    )
    assert len(grouped) == 1
    assert set(next(iter(grouped.values()))) == {"KI", "NRCWE"}


def test_provider_falls_back_to_the_company_when_there_is_no_citation():
    grouped = series_from_substance(substance([papp(lab="lab_A"), papp(lab="lab_B")]))
    assert set(next(iter(grouped.values()))) == {"lab_A", "lab_B"}


def test_units_and_errors_survive_the_adapter():
    series = series_from_protocol_application(papp(), substance="NM-101")[0]
    assert series.concentration_unit == "mg/L"  # ug/mL canonicalised
    assert series.response_unit == "%"
    assert series.error_qualifier == "SD"
    assert series.error is not None and np.all(series.error > 0)


def test_aggregated_effect_rows_are_dropped_and_counted():
    """An IC50 summary row is not a dose series.

    Relying on ``CONCENTRATION: "AGGREGATED RESULT"`` failing to parse as a float is
    not a filter -- the row is dropped deliberately and counted, so a record that is
    *only* aggregated results is visibly empty rather than mysteriously absent.
    """
    mixed = papp()
    mixed.effects.append(
        mb.EffectRecord(
            endpoint="IC50",
            endpointtype="AGGREGATED",
            result=mb.EffectResult(loValue=0.0, unit="ug/ml", errQualifier="SD"),
            conditions={"CONCENTRATION": "AGGREGATED RESULT", "MATERIAL": ""},
        )
    )
    series = series_from_protocol_application(mixed)
    assert len(series) == 1
    assert series[0].metadata["n_aggregated_dropped"] == 1


def test_existing_effect_arrays_are_not_ignored():
    """``convert_effectrecords2array`` passes pre-built EffectArrays through.

    An adapter written against EffectRecord alone silently drops them.
    """
    conc = np.array([1.0, 3.0, 10.0, 30.0, 100.0])
    prebuilt = mb.ProtocolApplication(
        protocol=mb.Protocol(
            topcategory="TOX",
            category=mb.EndpointCategory(code="ENM_0000068_SECTION"),
        ),
        effects=[
            mb.EffectArray(
                endpoint="Viability",
                endpointtype="TOXICITY",
                signal=mb.ValueArray(values=viability(conc), unit="%"),
                axes={"CONCENTRATION": mb.ValueArray(values=conc, unit="ug/mL")},
                conditions={},
            )
        ],
        owner=mb.SampleLink(
            substance=mb.Sample(uuid="S1"),
            company=mb.Company(uuid="lab_A", name="lab_A"),
        ),
        parameters={"E.method": "MTT"},
    )
    series = series_from_protocol_application(prebuilt)
    assert len(series) == 1
    assert series[0].n_observations == conc.size
    assert series[0].concentration_unit == "mg/L"


def test_control_from_a_zero_concentration_is_the_fallback_route():
    """No annotation present, so the control is inferred from the zero dose -- and
    which route was taken is recorded rather than left implicit."""
    series = series_from_protocol_application(papp())[0]
    profile = bmd_cdf(series, SPEC)
    assert profile.control_route == "zero-concentration"
    assert profile.control == pytest.approx(100.0, abs=6.0)


def test_an_annotated_control_is_used_and_the_route_recorded():
    """Real records annotate the control in a condition rather than dosing it at 0.

    ``convert_effectrecords2array`` splits on the string-valued condition, so the
    control arrives as its own EffectArray and has to be recognised and used as the
    baseline instead of being treated as a second dose series.
    """
    rows = []
    # An annotated negative control, at no particular concentration.
    for _ in range(3):
        rows.append(
            mb.EffectRecord(
                endpoint="Viability",
                endpointtype="TOXICITY",
                result=mb.EffectResult(loValue=100.0, unit="%"),
                conditions={
                    "CONCENTRATION": mb.Value(loValue=0.0, unit="ug/mL"),
                    "material": "Negative control",
                },
            )
        )
    for c in CONC[1:]:
        rows.append(
            mb.EffectRecord(
                endpoint="Viability",
                endpointtype="TOXICITY",
                result=mb.EffectResult(
                    loValue=float(viability(np.array([c]))[0]), unit="%"
                ),
                conditions={
                    "CONCENTRATION": mb.Value(loValue=float(c), unit="ug/mL"),
                    "material": "NM-101",
                },
            )
        )
    annotated = mb.ProtocolApplication(
        protocol=mb.Protocol(
            topcategory="TOX",
            category=mb.EndpointCategory(code="ENM_0000068_SECTION"),
        ),
        effects=rows,
        owner=mb.SampleLink(
            substance=mb.Sample(uuid="S1"),
            company=mb.Company(uuid="lab_A", name="lab_A"),
        ),
        parameters={"E.method": "MTT"},
    )

    series = series_from_protocol_application(annotated)
    # The control is the baseline, not a second dose-response series.
    assert len(series) == 1
    assert series[0].control_route == "annotated"
    assert series[0].control_response == pytest.approx(100.0)

    profile = bmd_cdf(series[0], SPEC)
    assert profile.control_route == "annotated"
    assert profile.determined.any()


def test_a_treatment_named_like_a_control_is_not_one():
    """ "positively charged TiO2" is a material, not a positive control."""
    from pyambit.bmd import classify_control

    assert classify_control("Negative control") == "negative"
    assert classify_control("control_positive") == "positive"
    assert classify_control("solvent_control") == "solvent"
    assert classify_control("Blank") == "blank"
    assert classify_control("positively charged TiO2") is None
    assert classify_control("NM-101") is None


# ----------------------------------------------------------------------
# the estimate
# ----------------------------------------------------------------------
def test_bmd_recovers_a_known_benchmark_concentration():
    profile = bmd_cdf(series_from_protocol_application(papp(noise=3.0))[0], SPEC)
    result = bmd_recovery(profile, true_bmd())
    assert abs(result["bias"]) < 0.15  # decades
    assert result["rmse"] < 0.25


def test_the_interval_is_ordered_and_finite():
    profile = bmd_cdf(series_from_protocol_application(papp())[0], SPEC)
    determined = profile.determined
    assert np.all(profile.bmdl[determined] <= profile.bmd[determined])
    assert np.all(profile.bmd[determined] <= profile.bmdu[determined])
    assert np.all(np.isfinite(profile.Q[:, determined]))


def test_more_replicates_narrow_the_interval():
    """The interval has to respond to the amount of evidence, or it is decoration."""
    few = bmd_cdf(series_from_protocol_application(papp(n_rep=2, seed=5))[0], SPEC)
    many = bmd_cdf(series_from_protocol_application(papp(n_rep=12, seed=5))[0], SPEC)
    assert np.median(many.width[many.determined]) < np.median(few.width[few.determined])


def test_pre_aggregated_rows_use_the_recorded_replicate_count():
    """One row per concentration carrying mean, SD and n is the real-record shape.

    ``convert_effectrecords2array`` drops the replicate-count column, so unless it
    is recovered from the raw conditions the standard error is the SD itself and
    every interval comes out sqrt(n) too wide.
    """

    def aggregated(n_replicates):
        rows = []
        rng = np.random.default_rng(7)
        for c in CONC:
            rows.append(
                mb.EffectRecord(
                    endpoint="Viability",
                    endpointtype="TOXICITY",
                    result=mb.EffectResult(
                        loValue=float(viability(np.array([c]))[0] + rng.normal(0, 1.0)),
                        errorValue=6.0,
                        errQualifier="SD",
                        unit="%",
                    ),
                    conditions={
                        "CONCENTRATION": mb.Value(loValue=float(c), unit="ug/mL"),
                        "NUMBER_OF_REPLICATES": n_replicates,
                    },
                )
            )
        return mb.ProtocolApplication(
            protocol=mb.Protocol(
                topcategory="TOX",
                category=mb.EndpointCategory(code="ENM_0000068_SECTION"),
            ),
            effects=rows,
            owner=mb.SampleLink(
                substance=mb.Sample(uuid="S1"),
                company=mb.Company(uuid="lab_A", name="lab_A"),
            ),
            parameters={"E.method": "MTT"},
        )

    one = series_from_protocol_application(aggregated(1))[0]
    three = series_from_protocol_application(aggregated(3))[0]
    assert np.allclose(one.replicates, 1.0)
    assert np.allclose(three.replicates, 3.0)

    wide = bmd_cdf(one, SPEC)
    narrow = bmd_cdf(three, SPEC)
    both = wide.determined & narrow.determined
    assert both.any()
    ratio = np.median(wide.width[both]) / np.median(narrow.width[both])
    assert ratio == pytest.approx(np.sqrt(3.0), rel=0.35)


def test_nonparametric_resampling_refuses_pre_aggregated_rows():
    """One row per concentration has nothing to resample; say so, do not pretend."""
    rows = [
        mb.EffectRecord(
            endpoint="Viability",
            endpointtype="TOXICITY",
            result=mb.EffectResult(
                loValue=float(viability(np.array([c]))[0]),
                errorValue=4.0,
                errQualifier="SD",
                unit="%",
            ),
            conditions={
                "CONCENTRATION": mb.Value(loValue=float(c), unit="ug/mL"),
                "NUMBER_OF_REPLICATES": 3,
            },
        )
        for c in CONC
    ]
    aggregated = mb.ProtocolApplication(
        protocol=mb.Protocol(
            topcategory="TOX",
            category=mb.EndpointCategory(code="ENM_0000068_SECTION"),
        ),
        effects=rows,
        owner=mb.SampleLink(
            substance=mb.Sample(uuid="S1"),
            company=mb.Company(uuid="lab_A", name="lab_A"),
        ),
        parameters={"E.method": "MTT"},
    )
    series = series_from_protocol_application(aggregated)[0]
    spec = BmdSpec(
        benchmark_responses=(50.0,), n_bootstrap=50, resample="nonparametric"
    )
    with pytest.raises(ValueError, match="pre-aggregated"):
        bmd_cdf(series, spec)


def test_a_response_never_reached_is_censored_not_invented():
    """A weak material bounds the BMD from below; it does not locate it."""
    weak = series_from_protocol_application(papp(ec50=1e6, noise=1.0))[0]
    profile = bmd_cdf(
        weak,
        BmdSpec(
            benchmark_responses=(50.0, 80.0),
            n_bootstrap=200,
            log_window=(-1.0, 3.0),
        ),
    )
    assert not profile.determined.any()
    assert np.all(profile.censored_fraction > 0.5)


def test_direction_is_explicit():
    """A readout rising with concentration needs the other polarity, and the module
    refuses to guess."""
    rising = DoseSeries(concentration=CONC, response=100.0 - viability(CONC))
    spec = BmdSpec(
        benchmark_responses=(20.0,),
        direction="increasing",
        n_bootstrap=100,
        log_window=(-1.0, 3.0),
    )
    profile = bmd_cdf(rising, spec)
    assert profile.determined.all()
    with pytest.raises(ValueError, match="direction"):
        BmdSpec(benchmark_responses=(20.0,), direction="sideways")


def test_no_rescaling_of_the_readout():
    """Benchmark responses are in the assay's own units, so an experiment whose
    efficacy is lower reaches fewer of them -- efficacy is preserved, which
    range-normalising the response would destroy."""
    strong = bmd_cdf(series_from_protocol_application(papp(noise=1.0))[0], SPEC)
    weak_effects = papp(noise=1.0)
    for effect in weak_effects.effects:  # halve the amplitude
        effect.result.loValue = 100.0 - 0.5 * (100.0 - effect.result.loValue)
    weak = bmd_cdf(series_from_protocol_application(weak_effects)[0], SPEC)
    assert strong.determined.sum() > weak.determined.sum()


# ----------------------------------------------------------------------
# consolidation
# ----------------------------------------------------------------------
def _three_labs(spread=0.15, noise=(4.0, 7.0, 5.0)):
    return substance(
        [
            papp("lab_A", TRUE_EC50 * 10**-spread, noise[0], seed=1),
            papp("lab_B", TRUE_EC50, noise[1], seed=2, n_rep=2),
            papp("lab_C", TRUE_EC50 * 10**spread, noise[2], seed=3),
        ]
    )


def test_consolidated_interval_covers_the_truth():
    grouped = series_from_substance(_three_labs())
    consensus = consolidate_providers(next(iter(grouped.values())), SPEC)
    result = bmd_recovery(consensus, true_bmd())
    assert result["coverage"] >= 0.75
    assert abs(result["bias"]) < 0.2


def test_consolidation_widens_the_interval_when_labs_disagree():
    """Between-laboratory disagreement must show up as uncertainty, not vanish."""
    agree = consolidate_providers(
        next(iter(series_from_substance(_three_labs(spread=0.0)).values())), SPEC
    )
    disagree = consolidate_providers(
        next(iter(series_from_substance(_three_labs(spread=0.35)).values())), SPEC
    )
    both = agree.determined & disagree.determined
    assert np.median(disagree.width[both]) > np.median(agree.width[both]) + 0.1


def test_consensus_is_wider_than_any_single_laboratory():
    grouped = next(iter(series_from_substance(_three_labs()).values()))
    consensus = consolidate_providers(grouped, SPEC)
    singles = [bmd_cdf(v, SPEC) for v in grouped.values()]
    determined = consensus.determined & np.all([s.determined for s in singles], axis=0)
    assert np.median(consensus.width[determined]) > max(
        np.median(s.width[determined]) for s in singles
    )


def test_a_noisy_laboratory_does_not_outvote_a_careful_one_by_well_count():
    """Equal weight per laboratory, not per well."""
    fair = substance(
        [
            papp("lab_A", TRUE_EC50, 3.0, n_rep=3, seed=1),
            papp("lab_B", TRUE_EC50 * 10**0.4, 9.0, n_rep=3, seed=2),
        ]
    )
    flooded = substance(
        [
            papp("lab_A", TRUE_EC50, 3.0, n_rep=3, seed=1),
            papp("lab_B", TRUE_EC50 * 10**0.4, 9.0, n_rep=30, seed=2),
        ]
    )
    a = consolidate_providers(next(iter(series_from_substance(fair).values())), SPEC)
    b = consolidate_providers(next(iter(series_from_substance(flooded).values())), SPEC)
    both = a.determined & b.determined
    assert np.max(np.abs(a.bmd[both] - b.bmd[both])) < 0.35


# ----------------------------------------------------------------------
# the vector
# ----------------------------------------------------------------------
def test_vector_is_the_cdf_and_reads_in_decades():
    grouped = next(iter(series_from_substance(_three_labs()).values()))
    consensus = consolidate_providers(grouped, SPEC)
    vector = bmd_vector(consensus, SPEC)
    assert vector.size == SPEC.dim == SPEC.n_quantiles * len(BMR)
    assert np.isfinite(vector).all()

    other = consolidate_providers(
        next(
            iter(
                series_from_substance(
                    substance(
                        [
                            papp("lab_A", TRUE_EC50 * 10**0.5, 4.0, seed=1),
                            papp("lab_B", TRUE_EC50 * 10**0.5, 7.0, seed=2, n_rep=2),
                            papp("lab_C", TRUE_EC50 * 10**0.5, 5.0, seed=3),
                        ]
                    )
                ).values()
            )
        ),
        SPEC,
    )
    distance = float(np.linalg.norm(vector - bmd_vector(other, SPEC)))
    assert distance == pytest.approx(0.5, abs=0.2)  # half a decade apart


def test_vector_is_a_pure_function_of_the_record():
    grouped = next(iter(series_from_substance(_three_labs()).values()))
    first = bmd_vector(consolidate_providers(grouped, SPEC), SPEC)
    second = bmd_vector(consolidate_providers(grouped, SPEC), SPEC)
    assert np.array_equal(first, second)  # the spec fixes the seed
