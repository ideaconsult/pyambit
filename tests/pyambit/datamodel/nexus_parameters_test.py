"""Protocol-application parameters must survive the NeXus round trip.

`to_nexus` routes every entry of `papp.parameters` into one of the NeXus
groups `nexus_writer.param_lookup` names -- but nothing read them back.
`Nexus2Ambit.parse_entry` recovered exactly three keys (E.method, wavelength,
instrument), so `__input_file` and the whole exposure / medium / cell /
instrument block were written to the .nxs file and then lost on read.

The visible symptom, in a real corpus: the `type_s:params` child of every
MOMENTUM document carried six identity fields and no parameters at all, and
`__input_file_s` -- present in AMBIT-backed collections -- was absent from
every document in the NeXus-backed one, so "was my file imported?" had no
answer on that side.
"""

import numpy as np
import nexusformat.nexus.tree as nx
import pyambit.datamodel as mx

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401
from pyambit.nexus_parser import Nexus2Ambit
from pyambit.solr_writer import Ambit2Solr

# One parameter per destination group, so a group dropped by the reader shows
# up as a specific missing key rather than a vague count mismatch. The comment
# on each is the branch of param_lookup that routes it.
PARAMETERS = {
    "__input_file": "MOMENTUM_cytokines_NHBE.xlsx",  # experiment_documentation
    "E.cell_type": "NHBE",  # environment, via prm.startswith("E.")
    "Medium": "DMEM + 10% FBS",  # environment, via "medium" in name
    "T.temperature": mx.Value(loValue=37.0, unit="degC"),  # instrument, "T."
    "Notes": "Cells seeded 24 h before exposure.",  # parameters (the fallback)
}


def _papp(uuid="pa1", owner_uuid="s1", parameters=None):
    papp = mx.ProtocolApplication(
        uuid=uuid,
        protocol=mx.Protocol(
            topcategory="TOX",
            category=mx.EndpointCategory(code="TO_CYTOTOXICITY_SECTION"),
            endpoint="Cytokine release",
            # a real guideline: parse_entry wraps protocol.guideline's attr in
            # a list, so an empty one round-trips to [[]] and fails validation.
            # Pre-existing quirk, unrelated to parameters.
            guideline=["OECD_TG_000"],
        ),
        effects=[
            mx.EffectArray(
                endpoint="Signal",
                endpointtype="RAW_DATA",
                signal=mx.ValueArray(values=np.array([1.0, 2.0]), unit="a.u."),
                axes={"x": mx.ValueArray(values=np.array([0.0, 1.0]))},
                conditions={},
            )
        ],
        citation=mx.Citation(owner="Test Lab", title="10.1234/test", year=2025),
        # parse_entry reads collection_identifier unconditionally, and the
        # writer only emits it when there is an investigation -- so a papp
        # without one is unparseable. Pre-existing, unrelated to parameters.
        investigation_uuid=mx.Investigation(uuid="study-1", title="Test study"),
        owner=mx.SampleLink(
            substance=mx.Sample(uuid=owner_uuid),
            company=mx.Company(name="Test Lab"),
        ),
    )
    # nexus_writer only writes experiment_identifier when assay_uuid is set
    papp.assay_uuid = "assay-1"
    papp.parameters = dict(parameters if parameters is not None else PARAMETERS)
    return papp


def _roundtrip(papp, tmp_path, name="parameters.nxs"):
    substances = mx.Substances(
        substance=[
            mx.SubstanceRecord(
                i5uuid=papp.owner.substance.uuid,
                name="Sample 1",
                publicname="Sample 1",
                ownerName="Test Lab",
                ownerUUID="Test Lab",
                study=[papp],
            )
        ]
    )
    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=False)
    path = tmp_path / name
    root.save(str(path), mode="w")

    parser = Nexus2Ambit(domain="/TEST", index_only=True)
    parser.parse(nx.nxload(str(path)), name)
    return parser


def test_every_parameter_group_is_read_back(tmp_path):
    """A parameter written into each of the four destination groups comes
    back under the key it went in as.

    Keys stay bare rather than becoming "experiment_documentation/__input_file"
    so that solr_writer names the field `__input_file_s` -- the same name an
    AMBIT-backed collection uses, which is what makes the two comparable.
    """
    parser = _roundtrip(_papp(), tmp_path)
    restored = parser.substances["s1"].study[0].parameters

    for key, expected in PARAMETERS.items():
        assert key in restored, "{} was written to NeXus and lost on read".format(key)
        assert restored[key] == expected


def test_input_file_reaches_the_solr_params_document(tmp_path):
    """The end the report depends on: __input_file_s in the index.

    Reading the parameter back is only half of it -- Ambit2Solr has to emit
    it too, and the params child was previously six identity fields with
    nothing else in it.
    """
    parser = _roundtrip(_papp(), tmp_path)

    with Ambit2Solr(prefix="TEST") as writer:
        docs = writer.to_json(parser.get_substances())
    params = [
        grandchild
        for doc in docs
        for child in doc.get("_childDocuments_", [])
        for grandchild in child.get("_childDocuments_", [])
        if grandchild.get("type_s") == "params"
    ]

    assert params, "no type_s:params document was written"
    assert params[0]["__input_file_s"] == "MOMENTUM_cytokines_NHBE.xlsx"
    assert params[0]["E.cell_type_s"] == "NHBE"
    # a Value becomes the _d / _UNIT_s pair, not a stringified object
    assert params[0]["T.temperature_d"] == 37.0
    assert params[0]["T.temperature_UNIT_s"] == "degC"


def test_model_fields_are_not_read_back_as_parameters(tmp_path):
    """`sample/provider` and `sample/substance` are written from the
    ProtocolApplication itself, not from parameters. Sweeping the sample
    group must not invent parameter keys for them -- they are already parsed
    into papp.owner, and a spurious `provider` key would then be indexed as
    a parameter that no source ever declared.
    """
    parser = _roundtrip(_papp(parameters={"Notes": "only this"}), tmp_path)
    restored = parser.substances["s1"].study[0].parameters

    assert restored["Notes"] == "only this"
    for invented in ("provider", "substance", "protocol", "date"):
        assert invented not in restored
    # the owner is still parsed, from its own model field
    assert parser.substances["s1"].study[0].owner.company.name == "Test Lab"


def test_measured_arrays_are_not_parameters(tmp_path):
    """Only scalars are parameters. An array sitting under a parameter group
    is measured data belonging to an effect; pulling it into papp.parameters
    would push whole signal vectors through prm2solr.
    """
    papp = _papp()
    parser = _roundtrip(papp, tmp_path, name="arrays.nxs")
    restored = parser.substances["s1"].study[0].parameters

    for key, value in restored.items():
        assert not isinstance(value, (list, tuple, np.ndarray)), (
            "{} came back as an array".format(key)
        )
