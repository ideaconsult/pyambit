from pathlib import Path
import os.path 
import json
import pyambit.datamodel as mx

TEST_DIR = Path(__file__).parent.parent / "resources"

def test_substances_load():
    with open(os.path.join(TEST_DIR,"substance.json"), "r", encoding='utf-8') as file:
        json_substance = json.load(file)
        substances = mx.Substances(**json_substance)
        #print(substances)
        with open(os.path.join(TEST_DIR,"study.json"), "r", encoding='utf-8') as file:
            json_study = json.load(file)
            study = mx.Study(**json_study)
            substances.substance[0].study = study.study
    #print(substances)
