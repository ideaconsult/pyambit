import json
import os.path
import tempfile
from pathlib import Path

import nexusformat.nexus.tree as nx
import pytest

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401
from pyambit.datamodel import Study, Substances


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
