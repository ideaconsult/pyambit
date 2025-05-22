import json
import os.path
import tempfile
from pathlib import Path

import pytest
from pyambit.datamodel import Study, Substances

from pyambit.solr_writer import Ambit2Solr

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

    _substances = Substances(substance=[substances.substance[0]])
    writer: Ambit2Solr = Ambit2Solr(prefix="TEST")
    _json = writer.to_json(_substances)
    _file = os.path.join(tempfile.gettempdir(), "substances.json")
    print(_file)
    with open(_file, "w") as file:
        json.dump(_json, file)
