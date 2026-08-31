import os.path
import tempfile

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
)
from pyambit.nexus_parser import Nexus2Ambit


def _papp(year, substance_id="ERM00000664"):
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
        citation=Citation(owner="MOMENTUM", title="Template Designer Export", year=year),
        owner=SampleLink(
            substance=Sample(uuid=substance_id),
            company=Company(name="MOMENTUM"),
        ),
    )


def _roundtrip(year, substance_id="ERM00000664"):
    substance = SubstanceRecord(
        i5uuid=substance_id,
        name=substance_id,
        publicname=substance_id,
        substanceType="CHEBI_51953",
        ownerName="MOMENTUM",
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
    `NeXusError: Invalid path` on every such file. That made the whole MOMENTUM
    Template Designer corpus unreadable, since the Template Designer blueprint
    carries no publication year and TemplateDesignerParser sets None.
    """
    substances = _roundtrip(year)

    assert len(substances) == 1
    studies = substances[0].study
    assert len(studies) == 1
    citation = studies[0].citation
    assert citation.year == year
    assert citation.owner == "MOMENTUM"
    assert citation.title == "Template Designer Export"


def test_substance_id_with_slash_round_trips():
    """A material name containing "/" (e.g. "PP/Talc leachate") must not
    break the written file.

    "/" is the NeXus/HDF5 path separator: `nx_root[f"substance/{uuid}"] = ...`
    raised `NeXusError: Invalid path` whenever a substance's i5uuid contained
    one, in both SubstanceRecord.to_nexus and ProtocolApplication.to_nexus
    (the latter keyed off `papp.owner.substance.uuid`, the same value). Seen
    on real MOMENTUM ELISA workbooks whose material list uses "/" as a
    separator between a blend's components.
    """
    substances = _roundtrip(2025, substance_id="PP/Talc leachate")

    assert len(substances) == 1
    assert substances[0].i5uuid == "PP/Talc leachate"
    assert substances[0].study[0].owner.substance.uuid == "PP/Talc leachate"


def test_parse_entry_without_reference_group():
    """An entry whose NXcite group is absent entirely must not raise either."""
    substance = SubstanceRecord(
        i5uuid="ERM00000664",
        name="ERM00000664",
        publicname="ERM00000664",
        ownerName="MOMENTUM",
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
