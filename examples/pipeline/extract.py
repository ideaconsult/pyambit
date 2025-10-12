import requests
from pyambit.datamodel import Substances, Study, EffectRecord
import nexusformat.nexus.tree as nx
import os.path
import traceback
# to_nexus is not added without this import
from pyambit import nexus_writer
from pathlib import Path
from IPython.display import display, HTML


# + tags=["parameters"]
upstream = []
product = None
url = None
hierarchy = None
single_nexus = None
max_substances = None
# -

Path(product["nexus"]).mkdir(parents=True, exist_ok=True)


def query(url="https://apps.ideaconsult.net/gracious/substance/",
          params = {"max" : 1}):
    substances = None
    headers = {'Accept': 'application/json'}
    result = requests.get(url, params=params, headers=headers)
    if result.status_code == 200:
        response =  result.json()
        substances = Substances.model_construct(**response)
        for substance in substances.substance:
            url_study = "{}/study?top=TOX&max=10000".format(substance.URI)
            print(url_study)
            study = requests.get(url_study, headers=headers)
            if study.status_code == 200:
                response_study = study.json()
                substance.study = Study.model_construct(**response_study).study
                break

    return substances


def write_studies_nexus(substances, single_file=single_nexus):
    if single_file:
        nxroot = nx.NXroot()
        substances.to_nexus(nxroot, hierarchy=hierarchy)
        file = os.path.join(product["nexus"], "remote.nxs")
        print(file)
        nxroot.save(file, mode="w")
    else:
        for substance in substances.substance:
            for study in substance.study:
                file = os.path.join(product["nexus"], "study_{}.nxs".format(study.uuid))
                print(file)
                nxroot = nx.NXroot()
                try:
                    study.to_nexus(nxroot)
                    nxroot.save(file, mode="w")
                except Exception as err:
                    #print("error",file,str(err))
                    print(file)


try:
    substances = query(url=url, params={"max" :  1 if max_substances is None else max_substances})
    _json = substances.model_dump(exclude_none=False)
    new_substances = Substances.model_construct(**_json)
    # new_substances = Substances(**_json)
    # test roundtrip
    assert substances == new_substances

    file = os.path.join(product["json"])
    # print(file)
    with open(file, 'w', encoding='utf-8') as file:
        file.write(substances.model_dump_json(exclude_none=True))  
    for s in substances.substance:
        for pa in s.study:
            for ea in pa.effects:
                ea.conditions = EffectRecord.clean_parameters(ea.conditions)
                _tagc = "CONCENTRATION"
                # this allows to split numeric concentrations into nxdata
                if _tagc in ea.conditions and (isinstance(ea.conditions[_tagc],str)):
                    if "TREATMENT" not in ea.conditions:
                        ea.conditions["TREATMENT"] = "control"
                            
            effectarrays_only, df = pa.convert_effectrecords2array()
            _file = os.path.join(product["nexus"], "study_{}.xlsx".format(pa.uuid))
            df.to_excel(_file)
            # print(_file)
            # display(df.dropna(axis=1, how="all"))
            # for ea in effectarrays_only:
            #    print(">>>", ea.endpoint, ea.endpointtype)
            #    for axis in ea.axes:
            #        print(axis, ea.axes[axis])
            #    print(">signal> ", ea.signal)
            #    for c in ea.conditions:
            #        print(c, ea.conditions[c])
            # break
    write_studies_nexus(substances, single_file=True)
except Exception as x:
    traceback.print_exc()