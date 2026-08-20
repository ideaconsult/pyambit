import json
import os.path
import tempfile
from pathlib import Path

import nexusformat.nexus.tree as nx
import pytest

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401
from pyambit.datamodel import ExternalIdentifier, Study, SubstanceRecord, Substances
from pyambit.nexus_parser import Nexus2Ambit

TEST_DIR = Path(__file__).parent.parent / "resources"


@pytest.fixture(scope="module")
def substances():
    """
    Fixture to load and return the Substances object.
    """

    with open(os.path.join(TEST_DIR, "substance.json"), "r", encoding="utf-8") as file:
        json_substance = json.load(file)
        substances = Substances(**json_substance)

    with open(os.path.join(TEST_DIR, "study.json"), "r", encoding="utf-8") as file:
        json_study = json.load(file)
        study = Study(**json_study)
        substances.substance[0].study = study.study
    return substances


def inspect_nexus_tree(node, path="root"):
    if isinstance(node, dict):  # If the node is a group/dictionary
        for key, child in node.items():
            inspect_nexus_tree(child, path + f"/{key}")
    elif hasattr(node, "dtype"):
        # Check if dtype is Unicode
        if node.dtype.char == "U":
            print(
                f"*****Problematic Unicode data found at {path} with dtype {node.dtype}"
            )
    # else:
    #    print(f"Skipping non-data node at {path}")


def test_substance_external_identifiers_roundtrip():
    """externalIdentifiers has no NeXus-native list-of-struct representation
    (see nexus_writer.to_nexus's SubstanceRecord handler), so it's written
    as two parallel string-array attrs and zipped back into
    ExternalIdentifier pairs by Nexus2Ambit.substance_from_nexus. Verify
    that write/read pair actually preserves type/id, matching how e.g.
    read_blop.py records a library's own item id (BLoP/SLoPP/OCEAN_POLYMERS
    external identifiers in pipeline_nexus's readers).

    Uses two identifiers deliberately: h5py collapses a length-1 string
    array attr back to a bare str on read (not a list-of-one), which a
    naive zip() would iterate character-by-character instead of
    element-by-element -- a single-item list wouldn't have caught that
    (confirmed: this test failed with exactly that symptom before
    nexus_parser.substance_from_nexus normalized the bare-str case).
    """
    substance = SubstanceRecord(
        name="Acrylic 1. Green Yarn",
        publicname="Acrylic 1. Green Yarn",
        ownerName="SLoPP",
        ownerUUID="SLOP-owner-uuid",
        substanceType="Acrylonitrile",
        externalIdentifiers=[
            ExternalIdentifier(type="SLoPP", id="Acrylic 1. Green Yarn"),
            ExternalIdentifier(type="DATASET", id="SLoPP"),
        ],
    )
    substance.i5uuid = "SLOP-substance-uuid"
    substance.study = []

    nxroot = nx.NXroot()
    substance.to_nexus(nxroot)

    file = os.path.join(tempfile.gettempdir(), "external_identifiers.nxs")
    nxroot.save(file, mode="w")

    nxroot_read = nx.nxload(file)
    parser = Nexus2Ambit(domain="/TEST", index_only=True)
    parser.parse_substances(nxroot_read["substance"])
    roundtripped = parser.substances[substance.i5uuid]

    assert roundtripped.externalIdentifiers == substance.externalIdentifiers


def test_substance_single_external_identifier_roundtrip():
    """Regression test for the h5py bare-str collapse itself: a SINGLE
    externalIdentifiers entry writes a length-1 string array attr, which
    h5py reads back as a plain str, not a list-of-one -- this is exactly
    the shape every pipeline_nexus reader (read_blop/read_ocean/
    read_slopp) actually produces, since each substance gets exactly one
    library/id pair.
    """
    substance = SubstanceRecord(
        name="PLAS193",
        publicname="ABS",
        ownerName="OCEAN_POLYMERS",
        ownerUUID="OSF-owner-uuid",
        substanceType="Acrylonitrile Butadiene Styrene (ABS)",
        externalIdentifiers=[
            ExternalIdentifier(type="OCEAN_POLYMERS", id="ABS PLAS193"),
        ],
    )
    substance.i5uuid = "OSF-single-ext-id"
    substance.study = []

    nxroot = nx.NXroot()
    substance.to_nexus(nxroot)

    file = os.path.join(tempfile.gettempdir(), "single_external_identifier.nxs")
    nxroot.save(file, mode="w")

    nxroot_read = nx.nxload(file)
    parser = Nexus2Ambit(domain="/TEST", index_only=True)
    parser.parse_substances(nxroot_read["substance"])
    roundtripped = parser.substances[substance.i5uuid]

    assert roundtripped.externalIdentifiers == substance.externalIdentifiers


def test_substance_without_external_identifiers_roundtrip():
    """externalIdentifiers is Optional -- most substances have none, and
    that absence must also round-trip as None, not an empty list or a
    KeyError on read.
    """
    substance = SubstanceRecord(
        name="No External Id",
        publicname="No External Id",
        ownerName="SLoPP",
        ownerUUID="SLOP-owner-uuid",
        substanceType="Acrylonitrile",
    )
    substance.i5uuid = "SLOP-no-ext-id"
    substance.study = []

    nxroot = nx.NXroot()
    substance.to_nexus(nxroot)

    file = os.path.join(tempfile.gettempdir(), "no_external_identifiers.nxs")
    nxroot.save(file, mode="w")

    nxroot_read = nx.nxload(file)
    parser = Nexus2Ambit(domain="/TEST", index_only=True)
    parser.parse_substances(nxroot_read["substance"])
    roundtripped = parser.substances[substance.i5uuid]

    assert roundtripped.externalIdentifiers is None


def test_substances(substances):
    #
    nxroot = nx.NXroot()
    # print(type(substances),dir(substances))
    substances.to_nexus(nxroot, hierarchy=True)
    file = os.path.join(tempfile.gettempdir(), "substances.nxs")
    print(file)
    inspect_nexus_tree(nxroot)
    nxroot.save(file, mode="w")


def test_study(substances):
    for substance in substances.substance:
        for study in substance.study:

            study.nx_name = "test"
            file = os.path.join(
                tempfile.gettempdir(), "study_{}.nxs".format(study.uuid)
            )
            nxroot = nx.NXroot()
            try:
                study.to_nexus(nxroot, hierarchy=True)
                inspect_nexus_tree(nxroot)
                nxroot.save(file, mode="w")
            except Exception as err:
                # inspect_nexus_tree(nxroot)
                # print(study.model_dump_json(exclude_none=True))
                effectarrays_only, df = study.convert_effectrecords2array()
                df.dropna(how="all").to_excel("bad.xlsx")
                for effect in effectarrays_only:
                    for key in effect.signal.auxiliary:
                        for element in effect.signal.auxiliary[key].flat:
                            print(element, end=".")
                # print(nxroot.tree)
                raise err
