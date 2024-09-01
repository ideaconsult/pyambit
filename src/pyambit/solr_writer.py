
from pyambit.ambit_deco import add_ambitmodel_method
from typing import Any, Dict, List, Optional, Tuple, Union

from pyambit.ambit_deco import add_ambitmodel_method


from pyambit.datamodel import (
    EffectRecord,
    EffectResult,
    EffectArray,
    ProtocolApplication,
    SubstanceRecord,
    Substances,
    Value,
   
)


class Ambit2Solr:

    def __init__(self,prefix : str):
        self.prefix = prefix

    def prm2solr(self,params : Dict, key : str, value : Union[str, Value, None]):
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

    def effectresult2solr(self,effect_result: EffectResult, solr_index = None ):
        if solr_index is None:
            solr_index = {}
        if effect_result.loValue is not None: 
            solr_index["loValue_d"] =  effect_result.loValue
        if effect_result.loQualifier is not None: 
            solr_index["loQualifier_s"] =  effect_result.loQualifier
        if effect_result.upQualifier is not None: 
            solr_index["upQualifier_s"] =  effect_result.upQualifier                   
        if effect_result.upValue is not None: 
            solr_index["upValue_d"] =  effect_result.upValue
        if effect_result.unit is not None: 
            solr_index["unit_s"] =  effect_result.unit
        if effect_result.textValue is not None:                    
            solr_index["textValue_s"] =  effect_result.textValue

    def entry2solr(self,papp: ProtocolApplication):
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
                    self.effectresult2solr(effect.result,_solr)
            elif isinstance(effect,EffectArray):
                if effect.result is not None:  #EffectResult
                    self.effectresult2solr(effect.result,_solr)
                if effect.endpointtype == "embeddings":
                    _solr[effect.endpoint] = effect.signal.values

                # tbd - this is new in pyambit, we did not have array results implementation
            _conditions = {"type_s" : "conditions"}
            _conditions["topcategory_s"] = papp.protocol.topcategory
            _conditions["endpointcategory_s"] = "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code        
            _conditions["document_uuid_s"] = papp.uuid
            _conditions["id"] =  "{}/cn".format(_solr["id"])        
            for prm in effect.conditions:
                self.prm2solr(_conditions,prm,effect.conditions[prm])
            _solr["_childDocuments_"] = [_conditions]

        _params = {}
        for prm in papp.parameters:
            self.prm2solr(_params,prm,papp.parameters[prm])
        
            _params["document_uuid_s"] = papp.uuid
            _params["id"] =  "{}/prm".format(papp.uuid)
            _params["topcategory_s"] = papp.protocol.topcategory
            _params["endpointcategory_s"] = "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code
            if "E.method_s" in papp.parameters:
                _params["E.method_s"] = papp.parameters["E.method_s"]
            _params["type_s"] = "params"
            _solr["_childDocuments_"] = [_params]
        
        papp_solr.append(_solr)
        return papp_solr

    def substancerecord2solr(self,substance: SubstanceRecord):
        _solr = {}
        _solr["content_hss"] = []
        _solr["dbtag_hss"] = self.prefix
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
            _study_solr = self.entry2solr(_papp)
            for _study in _study_solr:
                _study["s_uuid_s"] = substance.i5uuid
                _study["type_s"] = "study"
                _study["name_s"] = substance.name
                _study["publicname_s"] = substance.publicname
                _study["substanceType_s"] = substance.substanceType
                _study["owner_name_s"] = substance.ownerName
            _studies.extend(_study_solr)
            _summary = "{}.{}".format(
                _papp.protocol.topcategory,"UNKNOWN" if _papp.protocol.category is None else _papp.protocol.category.code)
            #if not (_summary in _solr["SUMMARY.RESULTS_hss"]):
            #        _solr["SUMMARY.RESULTS_hss"].append([_summary])
        _solr["_childDocuments_"] = _studies
        _solr["SUMMARY.REFS_hss"] = []
        _solr["SUMMARY.REFOWNERS_hss"] = []

        return _solr

    
    def substances2solr(self,substances: Substances):
        _solr = []
        for substance in substances.substance:        
            _solr.append(self.substancerecord2solr(substance))
        return _solr
    
    def to_json(self,substances: Substances):
        return self.substances2solr(substances)   