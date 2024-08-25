import json
import os.path
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pyambit.datamodel as mb
from pydantic_core import from_json

TEST_DIR = Path(__file__).parent.parent / "resources"


def test_substances_load():
    substances = None
    with open(os.path.join(TEST_DIR, "substance.json"), "r", encoding="utf-8") as file:
        json_substance = json.load(file)
        substances = mb.Substances(**json_substance)
        with open(os.path.join(TEST_DIR, "study.json"), "r", encoding="utf-8") as file:
            json_study = json.load(file)
            study = mb.Study(**json_study)
            substances.substance[0].study = study.study
    data = json.loads(substances.model_dump_json())
    new_val = mb.Substances.model_construct(**data)
    assert substances == new_val


def test_basevaluearray_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ValueArray model.
    """
    a1: npt.NDArray[np.float64] = np.ones(5)
    a0: npt.NDArray[np.float64] = np.zeros(5)
    val = mb.BaseValueArray(values=a1, unit="unit", errQualifier="SD", errorValue=a0)

    data = json.loads(val.model_dump_json())
    print(data)
    new_val = mb.BaseValueArray.model_construct(**data)

    assert val == new_val

def test_metavaluearray_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the MetaValueArray model.
    """
    a1: npt.NDArray[np.float64] = np.ones(5)
    a0: npt.NDArray[np.float64] = np.zeros(5)
    val = mb.MetaValueArray(values=a1, unit="unit", errQualifier="SD", errorValue=a0 ,conditions={"test" : "test"})

    data = json.loads(val.model_dump_json())
    print(data)
    new_val = mb.MetaValueArray.model_construct(**data)

    assert val == new_val    

def test_valuearray_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ValueArray model.
    """
    a1: npt.NDArray[np.float64] = np.ones(5)
    a0: npt.NDArray[np.float64] = np.zeros(5)
    val = mb.ValueArray(values=a1, unit="unit", errQualifier="SD", errorValue=a0)

    data = json.loads(val.model_dump_json())
    new_val = mb.ValueArray.model_construct(**data)

    assert val == new_val


def test_valuearrayaux_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ValueArray model.
    """
    shape = tuple((3, 2, 1))
    matrix_vals = np.random.random(shape) * 3
    matrix_errs = np.random.random(shape)
    matrix_upValue = np.random.random(shape) * 5
    matrix_textValue = np.full(shape, "test")

    val = mb.ValueArray(
        values=matrix_vals,
        unit="unit",
        errQualifier="SD",
        errorValue=matrix_errs,
        auxiliary={"upValue": matrix_upValue, "textValue": matrix_textValue},
    )

    data = json.loads(val.model_dump_json())
    new_val = mb.ValueArray.model_construct(**data)
    for key in val.auxiliary:
        print("old",key,type(val.auxiliary[key]))
    for key in new_val.auxiliary:
        print("new",key,type(new_val.auxiliary[key]))
    assert val == new_val


def test_valuearray_roundtrip_withaux():
    """
    Test the roundtrip serialization and deserialization of the ValueArray model.
    """
    a1: npt.NDArray[np.float64] = np.ones(5)
    a0: npt.NDArray[np.float64] = np.zeros(5)
    val = mb.ValueArray(
        values=a1,
        unit="unit",
        errQualifier="SD",
        errorValue=a0,
        auxiliary={"upValue": a1},
    )

    data = json.loads(val.model_dump_json())
    new_val = mb.ValueArray.model_construct(**data)
    print(val,print(new_val))
    assert val == new_val

def test_valuearray_roundtrip_with_arrayaux():
    """
    Test the roundtrip serialization and deserialization of the ValueArray model.
    """

    b1: npt.NDArray[np.float64] = np.ones(10)
    aux = mb.MetaValueArray(values=b1,unit="bunit")

    a1: npt.NDArray[np.float64] = np.ones(5)
    a0: npt.NDArray[np.float64] = np.zeros(5)
    val = mb.ValueArray(
        values=a1,
        unit="unit",
        errQualifier="SD",
        errorValue=a0,
        auxiliary={"upValue": a1, "array" : aux},
    )

    data = json.loads(val.model_dump_json())
    new_val = mb.ValueArray.model_construct(**data)
    #print(val,print(new_val))
    assert val == new_val


def test_value_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Value model.
    """
    val = mb.Value(loValue=3.14, loQualifier=">", errorValue="0.314")

    data = json.loads(val.model_dump_json())
    new_val = mb.Value.model_construct(**data)

    assert val.loValue == new_val.loValue, "Mismatch in loValue"
    assert val.loQualifier == new_val.loQualifier, "Mismatch in loQualifier"
    assert val.upValue == new_val.upValue, "Mismatch in upValue"  # This may be None
    assert (
        val.upQualifier == new_val.upQualifier
    ), "Mismatch in upQualifier"  # This may be None
    assert val.errorValue == new_val.errorValue, "Mismatch in errorValue"


def test_endpoint_category_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the EndpointCategory model.

    """
    original = mb.EndpointCategory(code="ABC123", term="Some term", title="Some title")

    # Serialize the instance to JSON
    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.EndpointCategory(**data)
    assert original == new_instance


def test_protocol_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Protocol model.

    """
    original = mb.Protocol(
        topcategory="TopCat",
        category=mb.EndpointCategory(
            code="ABC123", term="Some term", title="Some title"
        ),
        endpoint="Some endpoint",
        guideline=["Rule 1", "Rule 2"],
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.Protocol(**data)
    assert original == new_instance


def test_effect_result_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the EffectResult model.
    """
    original = mb.EffectResult(
        loQualifier=">",
        loValue=3.14,
        upQualifier="<",
        upValue=6.28,
        textValue="Sample text",
        errQualifier="Error",
        errorValue=0.314,
        unit="units",
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.EffectResult(**data)

    assert original == new_instance


def test_effect_record_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the EffectRecord model.
    """
    original = create_effectrecord()

    data = json.loads(original.model_dump_json())
    new_instance = mb.EffectRecord.model_construct(**data)

    assert original == new_instance


def create_effectarray():
    return mb.EffectArray(
        endpoint="endpoint",
        endpointtype="type",
        conditions={
            "condition1": mb.Value(loValue=3.14, loQualifier=">", errorValue="0.314"),
            "condition2": 123,
            "condition3": 456.78,
        },
        signal=mb.ValueArray(
            unit="units",
            values=np.array([1.0, 2.0, 3.0]),
            errQualifier="Error",
            errorValue=np.array([0.1, 0.2, 0.3]),
        ),
        axes={
            "x": mb.ValueArray(
                unit="cm-1", values=np.array([0.0, 1.0]), errQualifier="Error_x"
            ),
            "x_nm": mb.ValueArray(
                unit="nm", values=np.array([0.0, 1.0]), errQualifier="Error_x"
            ),
            "y": mb.ValueArray(
                unit="units_y", values=np.array([10.0, 20.0]), errQualifier="Error_y"
            ),
        },
        axis_groups={"x": ["x_nm"]},
        idresult=1,
        endpointGroup=2,
        endpointSynonyms=["synonym1", "synonym2"],
        sampleID="sample123",
    )


def test_effect_array_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the EffectArray model.
    """
    original = create_effectarray()

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.EffectArray.model_construct(**data)

    assert original == new_instance


def test_protocol_effect_record_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ProtocolEffectRecord model.
    """
    protocol = mb.Protocol(
        topcategory="TOX",
        category=mb.EndpointCategory(code="ABC123"),
        endpoint="Some endpoint",
        guideline=["Rule 1", "Rule 2"],
    )

    original = mb.ProtocolEffectRecord(
        protocol=protocol,
        documentUUID="123e4567-e89b-12d3-a456-426614174000",
        studyResultType="StudyType",
        interpretationResult="Result",
        endpoint="endpoint",
        endpointtype="type",
        result=mb.EffectResult(
            loQualifier=">",
            loValue=3.14,
            upQualifier="<",
            upValue=6.28,
            textValue="Sample text",
            errQualifier="Error",
            errorValue=0.314,
            unit="units",
        ),
        conditions={
            "condition1": mb.Value(upValue=3.14, upQualifier="<=", errorValue="0.314"),
            "condition2": 123,
            "condition3": 456.78,
        },
        idresult=1,
        endpointGroup=2,
        endpointSynonyms=["synonym1", "synonym2"],
        sampleID="sample123",
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.ProtocolEffectRecord.model_construct(**data)

    assert original == new_instance


def test_reliability_params_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ReliabilityParams model.
    """
    original = mb.ReliabilityParams(
        r_isRobustStudy="Yes",
        r_isUsedforClassification="No",
        r_isUsedforMSDS="Yes",
        r_purposeFlag="Flag1",
        r_studyResultType="TypeA",
        r_value="Value1",
    )

    # Convert to JSON string
    json_string = original.model_dump_json()

    # Load JSON string into dictionary
    data = json.loads(json_string)

    # Reconstruct ReliabilityParams from dictionary
    new_instance = mb.ReliabilityParams.model_construct(**data)

    # Assertions to check equality
    assert original == new_instance


def test_citation_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Citation model.
    """
    original = mb.Citation(year=2023, title="toxicity test", owner="AB")
    json_string = original.model_dump_json()
    data = json.loads(json_string)

    new_instance = mb.Citation.model_construct(**data)
    assert original == new_instance


def test_company_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Company model.
    """
    original = mb.Company(
        uuid="123e4567-e89b-12d3-a456-426614174000", name="Chemicals Inc."
    )
    json_string = original.model_dump_json()

    data = json.loads(json_string)
    new_instance = mb.Company.model_construct(**data)
    assert original == new_instance


def test_sample_link_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the SampleLink model.
    """
    original = mb.SampleLink.create(
        sample_uuid="123e4567-e89b-12d3-a456-426614174000",
        sample_provider="Materials Inc.",
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.SampleLink.model_construct(**data)

    assert original == new_instance


def create_protocolapp4test():
    protocol = mb.Protocol(
        topcategory="TOX",
        category=mb.EndpointCategory(code="ABC123"),
        endpoint="Some endpoint",
        guideline=["Rule 1", "Rule 2"],
    )
    citation = mb.Citation(year=2024, title="Sample Title", owner="Sample Owner")
    return mb.ProtocolApplication(
        uuid="123e4567-e89b-12d3-a456-426614174000",
        interpretationResult="Result",
        interpretationCriteria="Criteria",
        parameters={
            "param1": "value1",
            "param2": {"loValue": 5.5, "loQualifier": ">=", "errorValue": "0.5"},
        },
        citation=citation,
        effects=[],
        owner=mb.SampleLink.create(
            sample_uuid="sample-uuid", sample_provider="Sample Provider"
        ),
        protocol=protocol,
        investigation_uuid="investigation-uuid",
        assay_uuid="assay-uuid",
        updated="2024-08-15",
    )


def create_effectrecord():

    return mb.EffectRecord(
        endpoint="endpoint",
        endpointtype="type",
        result=mb.EffectResult(
            loQualifier=">",
            loValue=3.14,
            upQualifier="<",
            upValue=6.28,
            textValue="Sample text",
            errQualifier="Error",
            errorValue=0.314,
            unit="units",
        ),
        conditions={
            "condition1": mb.Value(loValue=3.14, loQualifier=">", errorValue="0.314"),
            "condition2": 123,
            "condition3": 456.78,
        },
        idresult=1,
        endpointGroup=2,
        endpointSynonyms=["synonym1", "synonym2"],
        sampleID="sample123",
    )


def test_protocol_application_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ProtocolApplication model.
    """
    original = create_protocolapp4test()

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.ProtocolApplication.model_construct(**data)

    assert original == new_instance
    assert repr(original) == repr(new_instance)


def test_study_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Study model.
    """
    protocol = mb.Protocol(
        topcategory="TOX",
        category=mb.EndpointCategory(code="ABC123"),
        endpoint="Some endpoint",
        guideline=["Rule 1", "Rule 2"],
    )

    protocol_application = mb.ProtocolApplication.create(
        protocol=protocol, effects=[], uuid="123e4567-e89b-12d3-a456-426614174000"
    )

    study = mb.Study(study=[protocol_application])

    json_string = study.model_dump_json()
    data = json.loads(json_string)

    new_instance = mb.Study.model_construct(**data)

    assert study == new_instance
    assert repr(study) == repr(new_instance)


def test_component_proportion_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the ComponentProportion model.
    """
    typical = mb.TypicalProportion(precision="<", value=5.0, unit="g")

    real = mb.RealProportion(
        lowerPrecision=">", lowerValue=3.0, upperPrecision="<", upperValue=7.0, unit="g"
    )

    original = mb.ComponentProportion(
        typical=typical, real=real, function_as_additive=0.5
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.ComponentProportion.model_construct(**data)

    assert original == new_instance


def test_compound_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Compound model.
    """
    original = mb.Compound(
        URI="http://example.com/compound",
        structype="Organic",
        metric=None,
        name="Formaldehyde",
        cas="50-00-0",
        einecs="200-001-8",
        inchikey="WSFSSMOSKXFYEK-UHFFFAOYSA-N",
        inchi="InChI=1S/CH2O/c1-2/h1H2",
        formula="CH2O",
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.Compound.model_construct(**data)
    assert original == new_instance


def test_component_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Component model.
    """
    # Create an instance of Component with sample data
    original = mb.Component(
        compound=mb.Compound(
            URI="http://example.com/compound/123", name="Formaldehyde", cas="50-00-0"
        ),
        values={"quantity": 5.0, "unit": "g"},
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.Component.model_construct(**data)
    assert original == new_instance


def test_composition_entry_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the CompositionEntry model.
    """
    # Create an instance of CompositionEntry with sample data
    original = mb.CompositionEntry(
        component=mb.Component(
            compound=mb.Compound(
                URI="http://example.com/compound/123",
                name="Formaldehyde",
                cas="50-00-0",
            ),
            values={"quantity": 5.0, "unit": "g"},
        ),
        compositionUUID="comp-123",
        compositionName="Test Composition",
        relation="HAS_COMPONENT",
        proportion=mb.ComponentProportion(
            typical=mb.TypicalProportion(precision="high", value=10.0, unit="mg"),
            real=mb.RealProportion(
                lowerPrecision="medium",
                lowerValue=5.0,
                upperPrecision="high",
                upperValue=15.0,
                unit="mg",
            ),
            function_as_additive=0.1,
        ),
        hidden=False,
    )

    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.CompositionEntry.model_construct(**data)
    assert original == new_instance


def test_composition_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Composition model.

    see how features are expected
    https://apps.ideaconsult.net/gracious/compound/3?media=application/json&feature_uris=https://apps.ideaconsult.net/gracious/compound/3/feature
    """
    # Create sample data for Composition
    original = mb.Composition(
        composition=[
            mb.CompositionEntry(
                component=mb.Component(
                    compound=mb.Compound(
                        URI="http://example.com/compound/123",
                        name="Formaldehyde",
                        cas="50-00-0",
                    ),
                    values={"feature_url": 5.0},
                ),
                compositionUUID="comp-123",
                compositionName="Test Composition",
                relation="HAS_COMPONENT",
                proportion=mb.ComponentProportion(
                    typical=mb.TypicalProportion(
                        precision="high", value=10.0, unit="mg"
                    ),
                    real=mb.RealProportion(
                        lowerPrecision="medium",
                        lowerValue=5.0,
                        upperPrecision="high",
                        upperValue=15.0,
                        unit="mg",
                    ),
                    function_as_additive=0.1,
                ),
                hidden=False,
            )
        ],
        feature={
            "feature_url": {
                "units": "g",
                "name": "smth",
                # , "sameAs" : "mass"
            }
        },
    )
    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.Composition.model_construct(**data)
    assert original == new_instance


def create_substance_record() -> mb.SubstanceRecord:
    return mb.SubstanceRecord(
        URI="http://example.com/compound",
        ownerUUID="owner-uuid",
        ownerName="Owner Name",
        i5uuid="i5-uuid",
        name="Substance Name",
        publicname="Public Name",
        format="Format",
        substanceType="Type",
        referenceSubstance=mb.ReferenceSubstance(
            i5uuid="ref-i5uuid", uri="http://example.com/reference"
        ),
        study=[create_protocolapp4test()],
        composition=None,
    )


def test_substance_record_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the SubstanceRecord model.
    """
    original = create_substance_record()
    # Serialize to JSON
    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.SubstanceRecord.model_construct(**data)
    assert original == new_instance


def test_substances_roundtrip():
    """
    Test the roundtrip serialization and deserialization of the Substances model.
    """
    original = mb.Substances(substance=[create_substance_record()])
    json_string = original.model_dump_json()
    data = json.loads(json_string)
    new_instance = mb.Substances.model_construct(**data)
    assert original == new_instance


def test_convert_effectrecords2array():
    papp = create_protocolapp4test()
    papp.effects = [create_effectrecord()]
    arrays, _df = papp.convert_effectrecords2array()
