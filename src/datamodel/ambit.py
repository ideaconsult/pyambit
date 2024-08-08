import json
import re

import uuid

from enum import Enum
from json import JSONEncoder
from typing import Any, Dict, List, Optional, Union

import numpy as np
from numpy.typing import NDArray
from pydantic import AnyUrl, BaseModel, create_model, Field, root_validator, validator

from .ambit_deco import add_ambitmodel_method


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
    term: Optional[str]
    title: Optional[str]


class Protocol(AmbitModel):
    topcategory: Optional[str] = None
    category: Optional[EndpointCategory] = None
    endpoint: Optional[str] = None
    guideline: List[str] = None

    def to_json(self):
        def protocol_encoder(obj):
            if isinstance(obj, EndpointCategory):
                return obj.__dict__
            return obj

        protocol_dict = self.dict()
        return json.dumps(protocol_dict, default=protocol_encoder)


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


EffectResult = create_model("EffectResult", __base__=EffectResult)


class ValueArray(AmbitModel):
    unit: Optional[str] = None
    # the arrays can in fact contain strings, we don't need textValue!
    values: Union[NDArray, None] = None
    errQualifier: Optional[str] = None
    errorValue: Optional[Union[NDArray, None]] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def create(
        cls,
        values: NDArray = None,
        unit: str = None,
        errorValue: NDArray = None,
        errQualifier: str = None,
    ):
        return cls(
            values=values, unit=unit, errorValue=errorValue, errQualifier=errQualifier
        )

    def to_json(self):
        def value_array_encoder(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj.__dict__

        return json.dumps(self, default=value_array_encoder)


class EffectRecord(AmbitModel):
    endpoint: str
    endpointtype: Optional[str] = None
    result: EffectResult = None
    conditions: Optional[Dict[str, Union[str, int, float, Value, None]]] = None
    idresult: Optional[int] = None
    endpointGroup: Optional[int] = None
    endpointSynonyms: List[str] = None
    sampleID: Optional[str] = None

    @validator("endpoint", pre=True)
    def clean_endpoint(cls, v):
        if v is None:
            return None
        else:
            return v.replace("/", "_")

    @validator("endpointtype", pre=True)
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

    def to_dict(self):
        data = self.dict(exclude_none=True)
        if self.result:
            data["result"] = self.result.dict()
        return data

    class Config:
        allow_population_by_field_name = True

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

    def to_json(self):
        def custom_encoder(obj):
            if isinstance(obj, BaseModel):
                return obj.__dict__
            return obj

        return json.dumps(self, default=custom_encoder)

    # def to_json(self):
    #    def effect_record_encoder(obj):
    #        if isinstance(obj, List):
    #            return [item.__dict__ for item in obj]
    #        return obj
    #    return json.dumps(self.__dict__, default=effect_record_encoder)

    @validator("conditions", pre=True)
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

    @classmethod
    def from_dict(cls, data: dict):
        if "conditions" in data:
            parameters = data["conditions"]
            for key, value in parameters.items():
                if isinstance(value, dict):
                    parameters[key] = Value(**value)
        return cls(**data)


EffectRecord = create_model("EffectRecord", __base__=EffectRecord)


class EffectArray(EffectRecord):
    signal: ValueArray = None
    axes: Optional[Dict[str, ValueArray]] = None

    @classmethod
    def create(cls, signal: ValueArray = None, axes: Dict[str, ValueArray] = None):
        return cls(signal=signal, axes=axes)

    class EffectArrayEncoder(JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ValueArray):
                return obj.__dict__
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    def to_json(self):
        data = self.dict(exclude={"axes", "signal"})
        data["signal"] = self.signal.__dict__ if self.signal else None
        data["axes"] = (
            {key: value.__dict__ for key, value in self.axes.items()}
            if self.axes
            else None
        )
        return json.dumps(data, cls=self.EffectArrayEncoder)

    def to_dict(self):
        data = self.dict(exclude_none=True)
        if self.signal:
            data["signal"] = self.signal.dict()
        if self.axes:
            data["axes"] = {key: value.dict() for key, value in self.axes.items()}
        return data


EffectArray = create_model("EffectArray", __base__=EffectArray)


class ProtocolEffectRecord(EffectRecord):
    protocol: Protocol
    documentUUID: str
    studyResultType: Optional[str] = None
    interpretationResult: Optional[str] = None


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


class Citation(AmbitModel):
    year: Optional[str] = None
    title: str
    owner: str

    @classmethod
    def create(cls, owner: str, citation_title: str, year: str = None):
        return cls(owner=owner, title=citation_title, year=year)


Citation = create_model("Citation", __base__=Citation)


class Company(AmbitModel):
    uuid: Optional[str] = None
    name: Optional[str] = None


class Sample(AmbitModel):
    uuid: str


class SampleLink(AmbitModel):
    substance: Sample
    company: Company = Company(name="Default company")

    @classmethod
    def create(cls, sample_uuid: str, sample_provider: str):
        return cls(substance=Sample(sample_uuid), company=Company(name=sample_provider))

    class Config:
        allow_population_by_field_name = True

    def to_json(self):
        def custom_encoder(obj):
            if isinstance(obj, BaseModel):
                return obj.__dict__
            return obj

        return json.dumps(self, default=custom_encoder)


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
        from pyambit.datamodel.ambit import EffectRecord, Protocol, EndpointCategory, ProtocolApplication
        effect_list: List[EffectRecord] = []
        effect_list.append(EffectRecord(endpoint="Endpoint 1", unit="Unit 1", loValue=5.0))
        effect_list.append(EffectRecord(endpoint="Endpoint 2", unit="Unit 2", loValue=10.0))
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
    citation: Optional[Citation]
    effects: List[Union[EffectRecord, EffectArray]]
    owner: Optional[SampleLink] = None
    protocol: Optional[Protocol] = None
    investigation_uuid: Optional[str] = None
    assay_uuid: Optional[str] = None
    updated: Optional[str]

    class Config:
        allow_population_by_field_name = True

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

    @validator("parameters", pre=True)
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

    def to_json(self):
        def encode_numpy(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        data = self.dict(exclude={"effects"})
        data["effects"] = [effect.dict() for effect in self.effects]
        if self.citation:
            data["citation"] = self.citation.dict()
        if self.parameters:
            data["parameters"] = {
                key: value.dict() for key, value in self.parameters.items()
            }
        if self.owner:
            data["owner"] = self.owner.dict()
        if self.protocol:
            data["protocol"] = self.protocol.dict()
        return json.dumps(data, default=encode_numpy, indent=2)


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

    def to_json(self) -> str:
        data = {"study": [pa.dict() for pa in self.study]}
        return json.dumps(data)


class ReferenceSubstance(AmbitModel):
    i5uuid: Optional[str] = None
    uri: Optional[str] = None


class TypicalProportion(AmbitModel):
    precision: Optional[str] = Field(None, regex=r"^\S+$")
    value: Optional[float] = None
    unit: Optional[str] = Field(None, regex=r"^\S+$")


class RealProportion(AmbitModel):
    lowerPrecision: Optional[str] = None
    lowerValue: Optional[float] = None
    upperPrecision: Optional[str] = None
    upperValue: Optional[float] = None
    unit: Optional[str] = Field(None, regex=r"^\S+$")


class ComponentProportion(AmbitModel):
    typical: TypicalProportion
    real: RealProportion
    function_as_additive: Optional[float] = None

    class Config:
        use_enum_values = True


class Compound(AmbitModel):
    URI: Optional[AnyUrl] = None
    structype: Optional[str] = None
    metric: Optional[float] = None
    name: Optional[str] = None
    cas: Optional[str] = None  # Field(None, regex=r'^\d{1,7}-\d{2}-\d$')
    einecs: Optional[str] = (
        None  # Field(None, regex=   r'^[A-Za-z0-9/@+=(),:;\[\]{}\-.]+$')
    )
    inchikey: Optional[str] = None  # Field(None, regex=r'^[A-Z\-]{27}$')
    inchi: Optional[str] = None
    formula: Optional[str] = None


class Component(BaseModel):
    compound: Compound
    values: Dict[str, Any] = None
    # facets: list
    # bundles: dict


class CompositionEntry(AmbitModel):
    component: Component
    compositionUUID: Optional[str] = None
    compositionName: Optional[str] = None
    relation: Optional[str] = "HAS_COMPONENT"
    proportion: Optional[ComponentProportion] = None
    hidden: bool = False


def update_compound_features(composition: List[CompositionEntry], feature):
    # Modify the composition based on the feature
    for entry in composition:
        for key, value in entry.component.values.items():
            if feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#CASRN":
                entry.component.compound.cas = value
            elif feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#EINECS":
                entry.component.compound.einecs = value
            elif (
                feature[key]["sameAs"] == "http://www.opentox.org/api/1.1#ChemicalName"
            ):
                entry.component.compound.name = value

    return composition


class Composition(AmbitModel):
    composition: List[CompositionEntry] = None
    feature: dict

    @root_validator
    def update_composition(cls, values):
        composition = values.get("composition")
        feature = values.get("feature")
        if composition and feature:
            values["composition"] = update_compound_features(composition, feature)
        return values


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

    def to_json(self):
        def substance_record_encoder(obj):
            if isinstance(obj, List):
                return [item.__dict__ for item in obj]
            return obj.__dict__

        return json.dumps(self, default=substance_record_encoder)


# s = Substances(**parsed_json)


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

    def to_json(self):
        def substances_encoder(obj):
            if isinstance(obj, Substances):
                return obj.substance
            return obj.__dict__

        return json.dumps(self, default=substances_encoder)


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
