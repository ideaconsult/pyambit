import json
import re

import uuid

from enum import Enum
from typing import Any, Dict, List, Optional, Union

import numpy as np
import numpy.typing as npt
from pydantic import field_validator, ConfigDict, AnyUrl, BaseModel, create_model, Field, model_validator


from pyambit.ambit_deco import add_ambitmodel_method


class AmbitModel(BaseModel):
    pass


class Value(AmbitModel):
    unit: Optional[str] = None
    loValue: Optional[float] = None
    upValue: Optional[float] = None
    loQualifier: Optional[str] = None
    upQualifier: Optional[str] = None
    annotation: Optional[str] = None
    errQualifier: Optional[str] = None
    errorValue: Optional[float] = None

    @classmethod
    def create(cls, loValue: float = None, unit: str = None, **kwargs):
        return cls(loValue=loValue, unit=unit, **kwargs)


class EndpointCategory(AmbitModel):
    code: str
    term: Optional[str] = None
    title: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, EndpointCategory):
            return False
        
        return (
            self.code == other.code and
            self.term == other.term and
            self.title == other.title
        )

    def __repr__(self):
        return (f"EndpointCategory(code={self.code!r}, term={self.term!r}, "
                f"title={self.title!r})")
    
class Protocol(AmbitModel):
    topcategory: Optional[str] = None
    category: Optional[EndpointCategory] = None
    endpoint: Optional[str] = None
    guideline: List[str] = None

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if self.category:
            data['category'] = self.category.model_dump()
        return data
    
    @classmethod
    def model_construct(cls, **data: Any) -> 'Protocol':
        if 'category' in data and isinstance(data['category'], dict):
            data['category'] = EndpointCategory(**data['category'])
        return super().model_construct(**data)

    def __repr__(self):
        return f"Protocol(topcategory={self.topcategory!r}, category={self.category!r}, endpoint={self.endpoint!r}, guideline={self.guideline!r})"

    def __eq__(self, other):
        if not isinstance(other, Protocol):
            return False
        
        return (
            self.topcategory == other.topcategory and
            self.category == other.category and
            self.endpoint == other.endpoint and
            self.guideline == other.guideline
        )
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

class EffectResult(AmbitModel):
    loQualifier: Optional[str] = None
    loValue: Optional[float] = None
    upQualifier: Optional[str] = None
    upValue: Optional[float] = None
    textValue: Optional[str] = None
    errQualifier: Optional[str] = None
    errorValue: Optional[float] = None
    unit: Optional[str] = None

    @classmethod
    def create(cls, loValue: float = None, unit: str = None, **kwargs):
        return cls(loValue=loValue, unit=unit, **kwargs)
    
    def __eq__(self, other):
        if not isinstance(other, EffectResult):
            return False
        return (
            self.loQualifier == other.loQualifier and
            self.loValue == other.loValue and
            self.upQualifier == other.upQualifier and
            self.upValue == other.upValue and
            self.textValue == other.textValue and
            self.errQualifier == other.errQualifier and
            self.errorValue == other.errorValue and
            self.unit == other.unit
        )

    def __repr__(self):
        return (f"EffectResult(loQualifier={self.loQualifier!r}, loValue={self.loValue!r}, "
                f"upQualifier={self.upQualifier!r}, upValue={self.upValue!r}, "
                f"textValue={self.textValue!r}, errQualifier={self.errQualifier!r}, "
                f"errorValue={self.errorValue!r}, unit={self.unit!r})")    


EffectResult = create_model("EffectResult", __base__=EffectResult)


class ValueArray(AmbitModel):
    unit: Optional[str] = None
    # the arrays can in fact contain strings, we don't need textValue!
    values: Union[npt.NDArray, None] = None
    errQualifier: Optional[str] = None
    errorValue: Optional[Union[npt.NDArray, None]] = None
    model_config = ConfigDict(
            arbitrary_types_allowed=True
        )

    @classmethod
    def create(
        cls,
        values: npt.NDArray = None,
        unit: str = None,
        errorValue: npt.NDArray = None,
        errQualifier: str = None,
    ):
        return cls(
            values=values, unit=unit, errorValue=errorValue, errQualifier=errQualifier
        )

    def model_dump_json(self, **kwargs) -> str:
        def serialize(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()  # Convert NumPy arrays to lists
            raise TypeError(f"Type {type(obj).__name__} not serializable")
        # Dump the model to a dictionary and then serialize it to JSON
        model_dict = self.model_dump()
        return json.dumps(model_dict, default=serialize, **kwargs)

    def __eq__(self, other):
        if not isinstance(other, ValueArray):
            return False
        return (
            self.unit == other.unit and
            self.errQualifier == other.errQualifier and
            np.array_equal(self.values, other.values) and
            np.array_equal(self.errorValue, other.errorValue)
        )

class EffectRecord(AmbitModel):
    endpoint: str
    endpointtype: Optional[str] = None
    result: EffectResult = None
    conditions: Optional[Dict[str, Union[str, int, float, Value, None]]] = None
    idresult: Optional[int] = None
    endpointGroup: Optional[int] = None
    endpointSynonyms: List[str] = None
    sampleID: Optional[str] = None

    @field_validator("endpoint", mode="before")
    @classmethod
    def clean_endpoint(cls, v):
        if v is None:
            return None
        else:
            return v.replace("/", "_")

    @field_validator("endpointtype", mode="before")
    @classmethod
    def clean_endpointtype(cls, v):
        if v is None:
            return None
        else:
            return v.replace("/", "_")

    def addEndpointSynonym(self, endpointSynonym: str):
        if self.endpointSynonyms is None:
            self.endpointSynonyms = []
        self.endpointSynonyms.append(endpointSynonym)

    def formatSynonyms(self, striplinks: bool) -> str:
        if self.endpointSynonyms:
            return ", ".join(self.endpointSynonyms)
        return ""

    def model_dump_json(self, **kwargs) -> str:
        def serialize(obj):
            if isinstance(obj, (EffectResult, Value)):
                return obj.model_dump()
            if isinstance(obj, (str, int, float, list, dict)):
                return obj
            raise TypeError(f"Type {type(obj).__name__} not serializable")

        model_dict = self.model_dump()
        return json.dumps(model_dict, default=serialize, **kwargs)

    @classmethod
    def model_construct(cls, **data: Any) -> 'EffectRecord':
        if 'result' in data and isinstance(data['result'], dict):
            data['result'] = EffectResult(**data['result'])

        if 'conditions' in data:
            new_conditions = {}
            for key, value in data['conditions'].items():
                if isinstance(value, dict):
                    new_conditions[key] = Value(**value)
                else:
                    new_conditions[key] = value
            data['conditions'] = new_conditions

        return super().model_construct(**data)
    
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def create(
        cls,
        endpoint: str = None,
        conditions: Dict[str, Union[str, Value, None]] = None,
        result: EffectResult = None,
    ):
        if conditions is None:
            conditions = {}
        return cls(endpoint=endpoint, conditions=conditions, result=result)



    @field_validator("conditions", mode="before")
    @classmethod
    def clean_parameters(cls, v):
        if v is None:
            return {}
        conditions = {}
        for key, value in v.items():
            if value is None:
                continue
            new_key = key.replace("/", "_") if "/" in key else key
            if value is None:
                pass
            elif key in [
                "REPLICATE",
                "EXPERIMENT",
                "BIOLOGICAL_REPLICATE",
                "TECHNICAL_REPLICATE",
            ]:
                if isinstance(value, dict):
                    conditions[new_key] = str(value["loValue"])
                    # print(key, type(value),value,conditions[new_key])
                elif isinstance(value, int):
                    conditions[new_key] = value
                elif isinstance(value, float):
                    print("warning>  Float value {}:{}".format(key, value))
                    conditions[new_key] = int(value)
                    raise Exception("warning>  Float value {}:{}".format(key, value))
                else:
                    # this is to extract nuber from e.g. 'Replicate 1'
                    match = re.search(r"[+-]?\d+(?:\.\d+)?", value)
                    if match:
                        conditions[new_key] = match.group()

            else:
                conditions[new_key] = value

        return conditions

    def __eq__(self, other):
        if not isinstance(other, EffectRecord):
            return False
        return (
            self.endpoint == other.endpoint and
            self.endpointtype == other.endpointtype and
            self.result == other.result and
            self.conditions == other.conditions and
            self.idresult == other.idresult and
            self.endpointGroup == other.endpointGroup and
            self.endpointSynonyms == other.endpointSynonyms and
            self.sampleID == other.sampleID
        )

    def __repr__(self):
        return (f"EffectRecord(endpoint={self.endpoint!r}, endpointtype={self.endpointtype!r}, "
                f"result={self.result!r}, conditions={self.conditions!r}, "
                f"idresult={self.idresult!r}, endpointGroup={self.endpointGroup!r}, "
                f"endpointSynonyms={self.endpointSynonyms!r}, sampleID={self.sampleID!r})")

EffectRecord = create_model("EffectRecord", __base__=EffectRecord)


class EffectArray(EffectRecord):
    signal: ValueArray = None
    axes: Optional[Dict[str, ValueArray]] = None

    @classmethod
    def create(cls, signal: ValueArray = None, axes: Dict[str, ValueArray] = None):
        return cls(signal=signal, axes=axes)

    def model_dump_json(self, **kwargs) -> str:
        def serialize(obj):
            if isinstance(obj, ValueArray):
                return obj.model_dump()
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        data = self.model_dump(exclude={"axes", "signal"})
        if self.signal:
            data["signal"] = self.signal.model_dump()
        if self.axes:
            data["axes"] = {key: value.model_dump() for key, value in self.axes.items()}
        return json.dumps(data, default=serialize, **kwargs)

    @classmethod
    def model_construct(cls, **data: Any) -> 'EffectArray':
        if 'signal' in data and isinstance(data['signal'], dict):
            data['signal'] = ValueArray.model_construct(**data['signal'])
        if 'axes' in data and isinstance(data['axes'], dict):
            new_axes = {}
            for key, value in data['axes'].items():
                if isinstance(value, dict):
                    new_axes[key] = ValueArray.model_construct(**value)
                else:
                    new_axes[key] = value
            data['axes'] = new_axes
        return super().model_construct(**data)

    def __eq__(self, other):
        if not isinstance(other, EffectArray):
            return False
        return (
            super().__eq__(other) and
            self.signal == other.signal and
            self.axes == other.axes
        )

    def __repr__(self):
        return (f"EffectArray(signal={self.signal!r}, axes={self.axes!r}, "
                f"{super().__repr__()})")
    
EffectArray = create_model("EffectArray", __base__=EffectArray)


class ProtocolEffectRecord(EffectRecord):
    protocol: Protocol
    documentUUID: str
    studyResultType: Optional[str] = None
    interpretationResult: Optional[str] = None

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data['protocol'] = self.protocol.model_dump()
        return data

    @classmethod
    def model_construct(cls, **data):
        if 'protocol' in data and isinstance(data['protocol'], dict):
            data['protocol'] = Protocol(**data['protocol'])
        return super().model_construct(**data)

    def __eq__(self, other):
        if not isinstance(other, ProtocolEffectRecord):
            return False
        return (
            super().__eq__(other) and
            self.protocol == other.protocol and
            self.documentUUID == other.documentUUID and
            self.studyResultType == other.studyResultType and
            self.interpretationResult == other.interpretationResult
        )
    
    def __repr__(self):
        return (f"ProtocolEffectRecord(protocol={self.protocol}, documentUUID={self.documentUUID}, "
                f"studyResultType={self.studyResultType}, interpretationResult={self.interpretationResult}, "
                f"{super().__repr__()})")
        
    
class STRUC_TYPE(str, Enum):
    NA = "NA"
    MARKUSH = "MARKUSH"
    D1 = "SMILES"
    D2noH = "2D no H"
    D2withH = "2D with H"
    D3noH = "3D no H"
    D3withH = "3D with H"
    optimized = "optimized"
    experimental = "experimental"
    NANO = "NANO"
    PDB = "PDB"


class ReliabilityParams(AmbitModel):
    r_isRobustStudy: Optional[str] = None
    r_isUsedforClassification: Optional[str] = None
    r_isUsedforMSDS: Optional[str] = None
    r_purposeFlag: Optional[str] = None
    r_studyResultType: Optional[str] = None
    r_value: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, ReliabilityParams):
            return False
        return (
            self.r_isRobustStudy == other.r_isRobustStudy and
            self.r_isUsedforClassification == other.r_isUsedforClassification and
            self.r_isUsedforMSDS == other.r_isUsedforMSDS and
            self.r_purposeFlag == other.r_purposeFlag and
            self.r_studyResultType == other.r_studyResultType and
            self.r_value == other.r_value
        )
    
    def __repr__(self):
        return (f"ReliabilityParams(r_isRobustStudy={self.r_isRobustStudy}, "
                f"r_isUsedforClassification={self.r_isUsedforClassification}, "
                f"r_isUsedforMSDS={self.r_isUsedforMSDS}, "
                f"r_purposeFlag={self.r_purposeFlag}, "
                f"r_studyResultType={self.r_studyResultType}, "
                f"r_value={self.r_value})")

class Citation(AmbitModel):
    year: Optional[int] = None
    title: str
    owner: str

    @classmethod
    def create(cls, owner: str, citation_title: str, year: int = None):
        return cls(owner=owner, title=citation_title, year=year)

    def __eq__(self, other):
        if not isinstance(other, Citation):
            return False
        return (
            self.year == other.year and
            self.title == other.title and
            self.owner == other.owner
        )
    
    def __repr__(self):
        return (f"Citation(year={self.year}, title={self.title}, "
                f"owner={self.owner})")

Citation = create_model("Citation", __base__=Citation)


class Company(AmbitModel):
    uuid: Optional[str] = None
    name: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, Company):
            return False
        return (
            self.uuid == other.uuid and
            self.name == other.name
        )
    
    def __repr__(self):
        return (f"Company(uuid={self.uuid}, name={self.name})")

class Sample(AmbitModel):
    uuid: str
    def __eq__(self, other):
        if not isinstance(other, Sample):
            return False
        return self.uuid == other.uuid
    
    def __repr__(self):
        return f"Sample(uuid={self.uuid!r})"
    

class SampleLink(AmbitModel):
    substance: Sample
    company: Company = Company(name="Default company")

    @classmethod
    def create(cls, sample_uuid: str, sample_provider: str):
        return cls(substance=Sample(uuid=sample_uuid), company=Company(name=sample_provider))
    
    model_config = ConfigDict(populate_by_name=True)

    def model_dump_json(self, **kwargs) -> str:
        return json.dumps(self.model_dump(), **kwargs)
    
    @classmethod
    def model_construct(cls, **data):
        if 'substance' in data and isinstance(data['substance'], dict):
            data['substance'] = Sample(**data['substance'])
        if 'company' in data and isinstance(data['company'], dict):
            data['company'] = Company(**data['company'])
        return super().model_construct(**data)    
    
    def __eq__(self, other):
        if not isinstance(other, SampleLink):
            return False
        return (
            self.substance == other.substance and
            self.company == other.company
        )
        
    def __repr__(self):
        return (f"SampleLink(substance={self.substance!r}, company={self.company!r})")


SampleLink = create_model("SampleLink", __base__=SampleLink)

"""
    ProtocolApplication : store results for single assay and a single sample

    Args:
        papp (ProtocolApplication): The object to be written into nexus format.

    Returns:
        protocol: Protocol
        effects: List[EffectRecord]

    Examples:
        from typing import List
        from pyambit.datamodel.ambit import EffectRecord, Protocol,
                EndpointCategory, ProtocolApplication
        effect_list: List[EffectRecord] = []
        effect_list.append(EffectRecord(endpoint="Endpoint 1",
                unit="Unit 1", loValue=5.0))
        effect_list.append(EffectRecord(endpoint="Endpoint 2",
                unit="Unit 2", loValue=10.0))
        papp = ProtocolApplication(protocol=Protocol(topcategory="P-CHEM",
                category=EndpointCategory(code="XYZ")),effects=effect_list)
        papp
"""


class ProtocolApplication(AmbitModel):
    uuid: Optional[str] = None
    # reliability: Optional[ReliabilityParams]
    interpretationResult: Optional[str] = None
    interpretationCriteria: Optional[str] = None
    parameters: Optional[Dict[str, Union[str, Value, None]]] = None
    citation: Optional[Citation] = None
    effects: List[Union[EffectRecord, EffectArray]]
    owner: Optional[SampleLink] = None
    protocol: Optional[Protocol] = None
    investigation_uuid: Optional[str] = None
    assay_uuid: Optional[str] = None
    updated: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def create(
        cls,
        protocol: Protocol = None,
        effects: List[Union[EffectRecord, EffectArray]] = None,
        **kwargs,
    ):
        if protocol is None:
            protocol = Protocol()
        if effects is None:
            effects = []
        return cls(protocol=protocol, effects=effects, **kwargs)

    @field_validator("parameters", mode="before")
    @classmethod
    def clean_parameters(cls, v):
        if v is None:
            return {}

        cleaned_params = {}
        for key, value in v.items():
            new_key = key.replace("/", "_") if "/" in key else key
            if isinstance(value, dict):
                cleaned_params[new_key] = Value(**value)
            else:
                cleaned_params[new_key] = value

        return cleaned_params

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if self.parameters:
            data['parameters'] = {
                k: (v.model_dump() if isinstance(v, BaseModel) else v) for k, v in self.parameters.items()
            }
        if self.citation:
            data['citation'] = self.citation.model_dump()
        if self.effects:
            data['effects'] = [e.model_dump() if isinstance(e, BaseModel) else e for e in self.effects]
        if self.owner:
            data['owner'] = self.owner.model_dump()
        if self.protocol:
            data['protocol'] = self.protocol.model_dump()
        return data

    @classmethod
    def model_construct(cls, **data):
        if 'parameters' in data and isinstance(data['parameters'], dict):
            data['parameters'] = {
                k: (Value(**v) if isinstance(v, dict) else v) for k, v in data['parameters'].items()
            }
        if 'citation' in data and isinstance(data['citation'], dict):
            data['citation'] = Citation(**data['citation'])
        if 'effects' in data:
            data['effects'] = [
                EffectRecord.model_construct(**e) if isinstance(e, dict) else e
                for e in data['effects']
            ]
        if 'owner' in data and isinstance(data['owner'], dict):
            data['owner'] = SampleLink.model_construct(**data['owner'])
        if 'protocol' in data and isinstance(data['protocol'], dict):
            data['protocol'] = Protocol.model_construct(**data['protocol'])
        return super().model_construct(**data)

    def __eq__(self, other):
        if not isinstance(other, ProtocolApplication):
            return False
        return (
            self.uuid == other.uuid and
            self.interpretationResult == other.interpretationResult and
            self.interpretationCriteria == other.interpretationCriteria and
            self.parameters == other.parameters and
            self.citation == other.citation and
            self.effects == other.effects and
            self.owner == other.owner and
            self.protocol == other.protocol and
            self.investigation_uuid == other.investigation_uuid and
            self.assay_uuid == other.assay_uuid and
            self.updated == other.updated
        )

    def __repr__(self):
        return (f"ProtocolApplication(uuid={self.uuid!r}, "
                f"interpretationResult={self.interpretationResult!r}, "
                f"interpretationCriteria={self.interpretationCriteria!r}, "
                f"parameters={self.parameters!r}, citation={self.citation!r}, "
                f"effects={self.effects!r}, owner={self.owner!r}, "
                f"protocol={self.protocol!r}, investigation_uuid={self.investigation_uuid!r}, "
                f"assay_uuid={self.assay_uuid!r}, updated={self.updated!r})")
    


ProtocolApplication = create_model("ProtocolApplication", __base__=ProtocolApplication)


# parsed_json["substance"][0]
# s = Study(**sjson)
class Study(AmbitModel):
    """
    Example:
        # Creating an instance of Substances, with studies
        # Parse json retrieved from AMBIT services
        from  pyambit.datamodel.measurements import Study
        import requests
        url = "https://apps.ideaconsult.net/gracious/substance/GRCS-7bd6de68-a312-3254-8b3f-9f46d6976ce6"
        response = requests.get(url+"/study?media=application/json")
        parsed_json = response.json()
        papps = Study(**parsed_json)
        for papp in papps:
            print(papp)
    """

    study: List[ProtocolApplication]

    model_config = ConfigDict(populate_by_name=True)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if 'study' in data:
            data['study'] = [pa.model_dump() for pa in data['study']]
        return data

    @classmethod
    def model_construct(cls, **data):
        if 'study' in data and isinstance(data['study'], list):
            data['study'] = [ProtocolApplication.model_construct(**pa) if isinstance(pa, dict) else pa for pa in data['study']]
        return super().model_construct(**data)

class ReferenceSubstance(AmbitModel):
    i5uuid: Optional[str] = None
    uri: Optional[str] = None


class TypicalProportion(AmbitModel):
    precision: Optional[str] = Field(None, pattern=r"^\S+$")
    value: Optional[float] = None
    unit: Optional[str] = Field(None, pattern=r"^\S+$")


class RealProportion(AmbitModel):
    lowerPrecision: Optional[str] = None
    lowerValue: Optional[float] = None
    upperPrecision: Optional[str] = None
    upperValue: Optional[float] = None
    unit: Optional[str] = Field(None, pattern=r"^\S+$")


class ComponentProportion(AmbitModel):
    typical: TypicalProportion
    real: RealProportion
    function_as_additive: Optional[float] = None
    model_config = ConfigDict(use_enum_values=True)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if 'typical' in data:
            data['typical'] = data['typical'].model_dump()
        if 'real' in data:
            data['real'] = data['real'].model_dump()
        return data

    @classmethod
    def model_construct(cls, **data):
        if 'typical' in data and isinstance(data['typical'], dict):
            data['typical'] = TypicalProportion.model_construct(**data['typical'])
        if 'real' in data and isinstance(data['real'], dict):
            data['real'] = RealProportion.model_construct(**data['real'])
        return super().model_construct(**data)

class Compound(AmbitModel):
    URI: Optional[AnyUrl] = None
    structype: Optional[str] = None
    metric: Optional[float] = None
    name: Optional[str] = None
    cas: Optional[str] = None  # Field(None, regex=r'^\d{1,7}-\d{2}-\d$')
    einecs: Optional[str] = None
         # Field(None, regex=   r'^[A-Za-z0-9/@+=(),:;\[\]{}\-.]+$')
    inchikey: Optional[str] = None  # Field(None, regex=r'^[A-Z\-]{27}$')
    inchi: Optional[str] = None
    formula: Optional[str] = None

    #model_config = ConfigDict(use_enum_values=True)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'Compound':
        if 'URI' in data:
            uri_value = data['URI']
            if uri_value is not None:
                data['URI'] = AnyUrl(uri_value) 
            else:
                data['URI'] = None 
        
        return super().model_construct(**data)
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Compound):
            return False
        
        return (
            self.URI == other.URI and
            self.structype == other.structype and
            self.metric == other.metric and
            self.name == other.name and
            self.cas == other.cas and
            self.einecs == other.einecs and
            self.inchikey == other.inchikey and
            self.inchi == other.inchi and
            self.formula == other.formula
        )

    def __repr__(self) -> str:
        return (f"Compound(URI={self.URI}, structype={self.structype}, metric={self.metric}, "
                f"name={self.name}, cas={self.cas}, einecs={self.einecs}, "
                f"inchikey={self.inchikey}, inchi={self.inchi}, formula={self.formula})")    

class Component(BaseModel):
    compound: Compound
    values: Dict[str, Any] = None
    # facets: list
    # bundles: dict
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if self.compound:
            data['compound'] = self.compound.model_dump()
        if self.values is None:
            data['values'] = {}
        else:
            data['values'] = self.values
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'Component':
        # Handle 'compound' construction
        if 'compound' in data and isinstance(data['compound'], dict):
            data['compound'] = Compound.model_construct(**data['compound'])

        # Handle 'values'
        if 'values' in data and data['values'] is None:
            data['values'] = {}

        return super().model_construct(**data)

class CompositionEntry(AmbitModel):
    component: Component
    compositionUUID: Optional[str] = None
    compositionName: Optional[str] = None
    relation: Optional[str] = "HAS_COMPONENT"
    proportion: Optional[ComponentProportion] = None
    hidden: bool = False
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if self.component:
            data['component'] = self.component.model_dump()
        if self.proportion:
            data['proportion'] = self.proportion.model_dump()
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'CompositionEntry':
        if 'component' in data and isinstance(data['component'], dict):
            data['component'] = Component.model_construct(**data['component'])
        
        if 'proportion' in data and isinstance(data['proportion'], dict):
            data['proportion'] = ComponentProportion.model_construct(**data['proportion'])
        
        return super().model_construct(**data)

def update_compound_features(composition: List[CompositionEntry], feature):
    # Modify the composition based on the feature
    for entry in composition:
        for key, value in entry.component.values.items():
            if "sameAs" in feature[key]:
                if feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#CASRN":
                    entry.component.compound.cas = value
                elif feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#EINECS":
                    entry.component.compound.einecs = value
                elif feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#ChemicalName":
                    entry.component.compound.name = value

    return composition


class Composition(AmbitModel):
    composition: List[CompositionEntry] = None
    feature: dict

    @model_validator(mode='before')
    def update_composition(cls, values):
        composition = values.get("composition")
        feature = values.get("feature")
        if composition and feature:
            values["composition"] = update_compound_features(composition, feature)
        return values

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if self.composition:
            data['composition'] = [entry.model_dump() for entry in self.composition]
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'Composition':
        if 'composition' in data:
            data['composition'] = [
                CompositionEntry.model_construct(**item) if isinstance(item, dict) else item
                for item in data['composition']
            ]
        return super().model_construct(**data)

class SubstanceRecord(AmbitModel):
    URI: Optional[str] = None
    ownerUUID: Optional[str] = None
    ownerName: Optional[str] = None
    i5uuid: Optional[str] = None
    name: str
    publicname: Optional[str] = None
    format: Optional[str] = None
    substanceType: Optional[str] = None
    referenceSubstance: Optional[ReferenceSubstance] = None
    # composition : List[]
    # externalIdentifiers : List[]
    study: Optional[List[ProtocolApplication]] = None
    composition: Optional[List[CompositionEntry]] = None

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        data = super().model_dump(**kwargs)
        if self.study is not None:
            data['study'] = [pa.model_dump() for pa in self.study] if self.study else []
        if self.composition is not None:
            data['composition'] = [entry.model_dump() for entry in self.composition] if self.composition else []
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'SubstanceRecord':
        if 'study' in data and data['study'] is not None:
            data['study'] = [
                ProtocolApplication.model_construct(**item) if isinstance(item, dict) else item
                for item in data['study']
            ]
        if 'composition' in data:
            if data['composition'] is not None:
                data['composition'] = [
                    CompositionEntry.model_construct(**item) if isinstance(item, dict) else item
                    for item in data['composition']
                ]
            else:
                data['composition'] = None  # Explicitly set to None if it's originally None
        if 'referenceSubstance' in data and isinstance(data['referenceSubstance'], dict):
            data['referenceSubstance'] = ReferenceSubstance.model_construct(**data['referenceSubstance'])
        return super().model_construct(**data)

    def __eq__(self, other):
        if not isinstance(other, SubstanceRecord):
            return False
        return (
            self.URI == other.URI and
            self.ownerUUID == other.ownerUUID and
            self.ownerName == other.ownerName and
            self.i5uuid == other.i5uuid and
            self.name == other.name and
            self.publicname == other.publicname and
            self.format == other.format and
            self.substanceType == other.substanceType and
            self.referenceSubstance == other.referenceSubstance and
            self.study == other.study and
            self.composition == other.composition
        )

    def __repr__(self):
        return (f"SubstanceRecord(URI={self.URI}, ownerUUID={self.ownerUUID}, ownerName={self.ownerName}, "
                f"i5uuid={self.i5uuid}, name={self.name}, publicname={self.publicname}, format={self.format}, "
                f"substanceType={self.substanceType}, referenceSubstance={self.referenceSubstance}, "
                f"study={self.study}, composition={self.composition})")


class Substances(AmbitModel):
    """
    Example:
        # Creating an instance of Substances, with studies
        # Parse json retrieved from AMBIT services
        from  pyambit.datamodel.measurements import Substances
        _p = Substances(**parsed_json)
        for substance in _p.substance:
            papps = substance.study
            for papp in papps:
                print(papp.protocol)
                print(papp.parameters)
                for e in papp.effects:
                    print(e)

    """

    substance: List[SubstanceRecord]

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        data = super().model_dump(**kwargs)
        data['substance'] = [substance.model_dump() for substance in self.substance]
        return data

    @classmethod
    def model_construct(cls, **data: Any) -> 'Substances':
        if 'substance' in data:
            data['substance'] = [
                SubstanceRecord.model_construct(**item) if isinstance(item, dict) else item
                for item in data['substance']
            ]
        return super().model_construct(**data)

    def __repr__(self):
        return f"Substances(substance={self.substance})"

Substances = create_model("Substances", __base__=Substances)

def configure_papp(
    papp: ProtocolApplication,
    provider="My organisation",
    sample="My sample",
    sample_provider="PROJECT",
    investigation="My experiment",
    year=2024,
    prefix="XLSX",
    meta=None,
):
    papp.citation = Citation(owner=provider, title=investigation, year=year)
    papp.investigation_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, investigation))
    papp.assay_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_OID, "{} {}".format(investigation, provider))
    )
    papp.parameters = meta

    papp.uuid = "{}-{}".format(
        prefix,
        uuid.uuid5(
            uuid.NAMESPACE_OID,
            "{} {} {} {} {} {}".format(
                papp.protocol.category,
                "" if investigation is None else investigation,
                "" if sample_provider is None else sample_provider,
                "" if sample is None else sample,
                "" if provider is None else provider,
                "" if meta is None else str(meta),
            ),
        ),
    )
    company = Company(name=sample_provider)
    substance = Sample(
        uuid="{}-{}".format(prefix, uuid.uuid5(uuid.NAMESPACE_OID, sample))
    )
    papp.owner = SampleLink(substance=substance, company=company)
