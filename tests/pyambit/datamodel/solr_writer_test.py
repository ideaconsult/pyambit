import json
import os.path
import tempfile
from pathlib import Path

import pytest

from pyambit import solr_writer
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
    _substances = Substances(substance=[substances.substance[0]])
    _json = _substances.to_solr_index()
    _file = os.path.join(tempfile.gettempdir(), "substances.json")
    print(_file)
    with open(_file, 'w') as file:
        json.dump(_json,file)
    
    