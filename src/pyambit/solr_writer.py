
from pyambit.ambit_deco import add_ambitmodel_method
from typing import Any, Dict, List, Optional, Tuple, Union

from pyambit.datamodel import (
    Composition,
    EffectRecord,
    EffectArray,
    ProtocolApplication,
    Study,
    SubstanceRecord,
    Substances,
    Value,
    MetaValueArray,
    ValueArray,
    
)

def prm2solr(params : Dict, key : str, value : Union[str, Value, None]):
        if isinstance(value,str):
            params["{}_s".format(key)] = value
        elif isinstance(value,int):    
            params["{}_d".format(key)] = value            
        elif isinstance(value,float):    
            params["{}_d".format(key)] = value
        elif isinstance(value,Value):
            if value.loValue is not None:
                params["{}_d".format(key)] = value.loValue
            if value.unit is not None:
                params["{}_UNIT_s".format(key)] = value.unit       


@add_ambitmodel_method(ProtocolApplication)
def to_solr_index(papp: ProtocolApplication,prefix="TEST"):
    papp_solr = []
    for _id, effect in enumerate(papp.effects, start=1):
        _solr = {}
        _solr["id"] = "{}/{}".format(papp.uuid,_id)
        _solr["investigation_uuid_s"] = papp.investigation_uuid
        _solr["assay_uuid_s"] = papp.assay_uuid
        _solr["type_s"] = "study"
        _solr["document_uuid_s"] = papp.uuid

        _solr["topcategory_s"] = papp.protocol.topcategory
        _solr["endpointcategory_s"] = "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code
        _solr["guidance_s"] = papp.protocol.guideline
        #_solr["guidance_synonym_ss"] = ["FIX_0000058"]
        #_solr["E.method_synonym_ss"] = ["FIX_0000058"]
        _solr["endpoint_s"] = papp.protocol.endpoint
        _solr["effectendpoint_s"] = effect.endpoint
        _solr["effectendpoint_type_s"] = effect.endpointtype
        #_solr["effectendpoint_synonym_ss"] = ["CHMO_0000823"]
        _solr["reference_owner_s"] = papp.citation.owner
        _solr["reference_year_s"] = papp.citation.year
        _solr["reference_s"] = papp.citation.title
        _solr["updated_s"] = papp.updated
        if "E.method_s" in papp.parameters:
            _solr["E.method_s"] = papp.parameters["E.method_s"]
        if isinstance(effect,EffectRecord):
            #conditions
            if effect.result is not None:  #EffectResult
                if effect.result.loValue is not None: 
                   _solr["loValue_d"] =  effect.result.loValue
                if effect.result.loQualifier is not None: 
                   _solr["loQualifier_s"] =  effect.result.loQualifier
                if effect.result.upQualifier is not None: 
                   _solr["upQualifier_s"] =  effect.result.upQualifier                   
                if effect.result.upValue is not None: 
                   _solr["upValue_d"] =  effect.result.upValue
                if effect.result.unit is not None: 
                   _solr["unit_s"] =  effect.result.unit
                if effect.result.textValue is not None:                    
                   _solr["textValue_s"] =  effect.result.textValue
        elif isinstance(effect,EffectArray):
            pass
            # tbd - this is new in pyambit, we did not have array results implementation
        _conditions = {"type_s" : "conditions"}
        _conditions["topcategory_s"] = papp.protocol.topcategory
        _conditions["endpointcategory_s"] = "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code        
        _conditions["document_uuid_s"] = papp.uuid
        _conditions["id"] =  "{}/cn".format(_solr["id"])        
        for prm in effect.conditions:
            prm2solr(_conditions,prm,effect.conditions[prm])
        _solr["_childDocuments_"] = [_conditions]

    _params = {}
    for prm in papp.parameters:
        prm2solr(_params,prm,papp.parameters[prm])
       
        _params["document_uuid_s"] = papp.uuid
        _params["id"] =  "{}/prm".format(papp.uuid)
        _params["topcategory_s"] = papp.protocol.topcategory
        _params["endpointcategory_s"] = "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code
        if "E.method_s" in papp.parameters:
            _params["E.method_s"] = papp.parameters["E.method_s"]
        _params["type_s"] = "params"
        _solr["_childDocuments_"] = [_params]
        #_solr["spectrum_c1024"] = self.spectrum_embedding[0]
        #_solr["spectrum_p1024"] = self.spectrum_embedding[1]
        papp_solr.append(_solr)
    return papp_solr

@add_ambitmodel_method(SubstanceRecord)
def to_solr_index(substance: SubstanceRecord,prefix="TEST"):
    _solr = {}
    _solr["content_hss"] = []
    _solr["dbtag_hss"] = prefix
    _solr["name_hs"] = substance.name
    _solr["publicname_hs"] = substance.publicname
    _solr["owner_name_hs"] = substance.ownerName
    _solr["substanceType_hs"] = substance.substanceType
    _solr["type_s"] = "substance"
    _solr["s_uuid_hs"] = substance.i5uuid
    _solr["id"] = substance.i5uuid
    _studies = []
    _solr["SUMMARY.RESULTS_hss"] = []
    for _papp in substance.study:
        _study_solr = _papp.to_solr_index()

        for _study in _study_solr:
            _study["s_uuid_s"] = substance.i5uuid
            _study["type_s"] = "study"
            _study["name_s"] = substance.name
            _study["publicname_s"] = substance.publicname
            _study["substanceType_s"] = substance.substanceType
            _study["owner_name_s"] = substance.ownerName
        _studies.append(_study_solr)
        _summary = "{}.{}".format(
              _papp.protocol.topcategory,"UNKNOWN" if _papp.protocol.category is None else _papp.protocol.category.code)
        #if not (_summary in _solr["SUMMARY.RESULTS_hss"]):
        #        _solr["SUMMARY.RESULTS_hss"].append([_summary])
    _solr["_childDocuments_"] = _studies
    _solr["SUMMARY.REFS_hss"] = []
    _solr["SUMMARY.REFOWNERS_hss"] = []

    return _solr

@add_ambitmodel_method(Substances)
def to_solr_index(substances: Substances,prefix="TEST"):
    _solr = []
    for substance in substances.substance:        
        _solr.append(substance.to_solr_index(prefix))
    return _solr