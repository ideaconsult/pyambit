# + tags=["parameters"]
upstream = ["convert2nexus"]
product = None

# -

from pyambit.nexus_parser import Nexus2Ambit
from pyambit.datamodel import (
    Composition,
    EffectArray,
    effects2df,
    Protocol,
    ProtocolApplication,
    Citation,
    Study,
    SubstanceRecord,
    Substances,
    Value,
    MetaValueArray,
    ValueArray,
    EndpointCategory,
    SampleLink
)
from pyambit.solr_writer import to_solr_index

from nexusformat.nexus import nxload
import nexusformat.nexus as nx
import numpy as np 
import ramanchada2 as rc2
from pathlib import Path



#    _substances = Substances(substance=[substances.substance[0]])
#    _json = _substances.to_solr_index()
#    _file = os.path.join(tempfile.gettempdir(), "substances.json")
#    print(_file)
#    with open(_file, 'w') as file:
#        json.dump(_json,file)

def main():
    try:
        path = Path(upstream["convert2nexus"]["nexus"])
        parser : Nexus2Ambit = Nexus2Ambit(domain="/CHARISMA",index_only=True)        
        for item in path.rglob('*.nxs'):
            relative_path = item.relative_to(path)
            absolute_path = item.resolve() 
            if item.is_dir():
                pass
            elif item.name.endswith(".nxs"):
                absolute_path = item.resolve() 
                nexus_file = nxload(absolute_path)

                parser.parse(nexus_file,relative_path.as_posix())
                substances : Substances = parser.get_substances()
                   #     papp : ProtocolApplication = nexus_parser.from_nexus(relative_path.as_posix(),entry,index_only=True)
                print(substances.model_dump_json(exclude_none=True,indent=4))
                break
    except Exception as err:
        print(err)

main()        