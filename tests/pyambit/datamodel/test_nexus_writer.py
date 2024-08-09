from pathlib import Path
import os.path 
import json
from pyambit.datamodel import Substances, Study
import tempfile
import nexusformat.nexus.tree as nx
# to_nexus is not added without this import
from pyambit import nexus_writer

TEST_DIR = Path(__file__).parent.parent / "resources"

def substances_load():
    substances = None
    with open(os.path.join(TEST_DIR,"substance.json"), "r", encoding='utf-8') as file:
        json_substance = json.load(file)
        substances = Substances(**json_substance)
        #print(dir(substances))
        with open(os.path.join(TEST_DIR,"study.json"), "r", encoding='utf-8') as file:
            json_study = json.load(file)
            study = Study(**json_study)
            substances.substance[0].study = study.study
    return substances

def test_substances():
    substances = substances_load() 
    #
    nxroot = nx.NXroot()
    #print(type(substances),dir(substances))
    substances.to_nexus(nxroot)
    file = os.path.join(tempfile.gettempdir(), "substances.nxs")
    nxroot.save(file, mode="w")
