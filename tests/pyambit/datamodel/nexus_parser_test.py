import os.path
import tempfile

import numpy as np
import nexusformat.nexus as nx
import nexusformat.nexus.tree as nxtree
import pytest

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401
from pyambit.datamodel import (
    Citation,
    Company,
    EffectRecord,
    EffectResult,
    EndpointCategory,
    Protocol,
    ProtocolApplication,
    Sample,
    SampleLink,
    SubstanceRecord,
    Value,
)
from pyambit.nexus_parser import Nexus2Ambit


def _papp(year, substance_id="SUBSTANCE-1"):
    """One minimal ProtocolApplication, parameterised only by citation year."""
    return ProtocolApplication(
        uuid="22222222-2222-2222-2222-222222222222",
        investigation_uuid="33333333-3333-3333-3333-333333333333",
        assay_uuid="44444444-4444-4444-4444-444444444444",
        protocol=Protocol(
            topcategory="TOX",
            category=EndpointCategory(code="NPO_1339_SECTION"),
            endpoint="Dose response ELISA",
            guideline=["in-house SOP"],
        ),
        effects=[
            EffectRecord(
                endpoint="Viability",
                endpointtype="AGGREGATED",
                result=EffectResult(loValue=42.0, unit="%"),
                conditions={},
            )
        ],
        parameters={"E.method": "Dose response ELISA"},
        citation=Citation(owner="TestOwner", title="Template Designer Export", year=year),
        owner=SampleLink(
            substance=Sample(uuid=substance_id),
            company=Company(name="TestOwner"),
        ),
    )


def _roundtrip(year, substance_id="SUBSTANCE-1"):
    substance = SubstanceRecord(
        i5uuid=substance_id,
        name=substance_id,
        publicname=substance_id,
        substanceType="CHEBI_51953",
        ownerName="TestOwner",
        ownerUUID="11111111-1111-1111-1111-111111111111",
    )
    substance.study = [_papp(year, substance_id=substance_id)]

    nxroot = nxtree.NXroot()
    substance.to_nexus(nxroot)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "citation.nxs")
        nxroot.save(path, mode="w")

        parser = Nexus2Ambit(domain="", index_only=True)
        parser.parse(nx.nxload(path), "citation.nxs")
        return parser.get_substances().substance


@pytest.mark.parametrize("year", [2026, None])
def test_parse_entry_citation_year_optional(year):
    """A ProtocolApplication with no citation year must still round-trip.

    Citation.year is Optional, and to_nexus writes nothing for a None year --
    so the NXcite group simply has no `year` field. parse_entry used to read
    nxentry["reference"]["year"] unconditionally and raised
    `NeXusError: Invalid path` on every such file. That makes a whole
    Template Designer corpus unreadable, since such a blueprint carries no
    publication year and TemplateDesignerParser sets None.
    """
    substances = _roundtrip(year)

    assert len(substances) == 1
    studies = substances[0].study
    assert len(studies) == 1
    citation = studies[0].citation
    assert citation.year == year
    assert citation.owner == "TestOwner"
    assert citation.title == "Template Designer Export"


def test_substance_id_with_slash_round_trips():
    """A material name containing "/" (e.g. "Blend A/B") must not
    break the written file.

    "/" is the NeXus/HDF5 path separator: `nx_root[f"substance/{uuid}"] = ...`
    raised `NeXusError: Invalid path` whenever a substance's i5uuid contained
    one, in both SubstanceRecord.to_nexus and ProtocolApplication.to_nexus
    (the latter keyed off `papp.owner.substance.uuid`, the same value). Seen
    in templates whose material list uses "/" as a separator between a
    blend's components.
    """
    substances = _roundtrip(2025, substance_id="Blend A/B")

    assert len(substances) == 1
    assert substances[0].i5uuid == "Blend A/B"
    assert substances[0].study[0].owner.substance.uuid == "Blend A/B"


def test_parse_entry_without_reference_group():
    """An entry whose NXcite group is absent entirely must not raise either."""
    substance = SubstanceRecord(
        i5uuid="SUBSTANCE-1",
        name="SUBSTANCE-1",
        publicname="SUBSTANCE-1",
        ownerName="TestOwner",
        ownerUUID="11111111-1111-1111-1111-111111111111",
    )
    papp = _papp(None)
    papp.citation = None
    substance.study = [papp]

    nxroot = nxtree.NXroot()
    substance.to_nexus(nxroot)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "no_citation.nxs")
        nxroot.save(path, mode="w")

        parser = Nexus2Ambit(domain="", index_only=True)
        parser.parse(nx.nxload(path), "no_citation.nxs")
        substances = parser.get_substances().substance

    assert len(substances) == 1
    assert substances[0].study[0].citation.year is None


def _record(endpoint, value, conditions):
    return EffectRecord(
        endpoint=endpoint,
        endpointtype="AGGREGATED",
        result=EffectResult(loValue=value, unit="%"),
        conditions=conditions,
    )


def _pa_with(records):
    return ProtocolApplication(
        uuid="22222222-2222-2222-2222-222222222222",
        protocol=Protocol(
            topcategory="TOX",
            category=EndpointCategory(code="NPO_1339_SECTION"),
            endpoint="assay",
            guideline=["sop"],
        ),
        effects=records,
        owner=SampleLink(
            substance=Sample(uuid="SUBSTANCE-1"),
            company=Company(name="TestOwner"),
        ),
    )


def test_records_without_conditions_become_one_array():
    """Records that declare no conditions are a plain series, not a grid.

    With no condition to index by there are no axes, and building a 0-d
    matrix kept only whichever record was written last -- silently reducing
    a whole column of measurements to a single value.
    """
    pa = _pa_with([_record("PET", v, {}) for v in (11.5, 15.6, 21.8, 4.0)])

    arrays, _ = pa.convert_effectrecords2array()

    assert len(arrays) == 1
    values = np.asarray(arrays[0].signal.values, dtype=float)
    assert sorted(values.tolist()) == [4.0, 11.5, 15.6, 21.8]


def test_records_missing_a_condition_are_kept_not_dropped():
    """A record missing one condition must still reach an array.

    Not every record carries every condition -- a vehicle control has no
    concentration, and a table holding several endpoints only fills the
    conditions its own endpoint declares. Those rows used to hit an
    "ignore for now" branch that dropped them outright, losing real
    measurements; they are now grouped by which conditions they do have.
    """
    dosed = [
        _record("Viability", 10.0, {"conc": Value(loValue=1.0, unit="ug/mL")}),
        _record("Viability", 20.0, {"conc": Value(loValue=10.0, unit="ug/mL")}),
    ]
    controls = [_record("Viability", 99.0, {}), _record("Viability", 98.0, {})]
    pa = _pa_with(dosed + controls)

    arrays, _ = pa.convert_effectrecords2array()

    kept = []
    for effect in arrays:
        kept.extend(np.asarray(effect.signal.values, dtype=float).ravel().tolist())
    kept = [v for v in kept if not np.isnan(v)]
    assert sorted(kept) == [10.0, 20.0, 98.0, 99.0]
