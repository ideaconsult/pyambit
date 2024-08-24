import json
import os.path
import tempfile
from pathlib import Path

import nexusformat.nexus.tree as nx
import pytest

# to_nexus is not added without this import
from pyambit import nexus_writer
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


def test_substances(substances):
    #
    nxroot = nx.NXroot()
    # print(type(substances),dir(substances))
    substances.to_nexus(nxroot, hierarchy=True)
    file = os.path.join(tempfile.gettempdir(), "substances.nxs")
    print(file)
    nxroot.save(file, mode="w")


def test_study(substances):
    for substance in substances.substance:
        for study in substance.study:
            study.nx_name = "test"
            file = os.path.join(
                tempfile.gettempdir(), "study_{}.nxs".format(study.uuid)
            )
            print(file)
            nxroot = nx.NXroot()
            try:
                study.to_nexus(nxroot)
                nxroot.save(file, mode="w")
            except Exception as err:
                print(study)
                raise err
            