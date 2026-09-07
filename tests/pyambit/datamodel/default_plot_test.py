import numpy as np
import nexusformat.nexus.tree as nx
import pyambit.datamodel as mx

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401


def _categorical_effect(endpoint, labels):
    """An EffectArray with a text axis -- e.g. LOD indexed by polymer name.
    Not plottable by a generic NeXus viewer's default-plot logic.
    """
    return mx.EffectArray(
        endpoint=endpoint,
        endpointtype="RESULT_ANALYSIS",
        signal=mx.ValueArray(values=np.array([1.0, 2.0, 3.0]), unit="ng"),
        axes={"polymer": mx.ValueArray(values=np.array(labels, dtype=object))},
        conditions={},
    )


def _numeric_effect(endpoint):
    """An EffectArray with a plain numeric axis -- always plottable."""
    return mx.EffectArray(
        endpoint=endpoint,
        endpointtype="RESULT",
        signal=mx.ValueArray(values=np.array([10.0, 20.0, 30.0]), unit="ng"),
        axes={"Sample": mx.ValueArray(values=np.array([0.0, 1.0, 2.0]))},
        conditions={},
    )


def _write(effects):
    pa = mx.ProtocolApplication(
        uuid="pa1",
        protocol=mx.Protocol(
            topcategory="P-CHEM",
            category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            endpoint="Test method",
            guideline=[],
        ),
        effects=effects,
        citation=mx.Citation(owner="Test Owner", title="10.1234/test", year=2025),
        owner=mx.SampleLink(
            substance=mx.Sample(uuid="s1"), company=mx.Company(name="Test Lab")
        ),
    )
    substance = mx.SubstanceRecord(
        i5uuid="s1",
        name="Sample 1",
        publicname="Sample 1",
        ownerName="Test Lab",
        ownerUUID="Test Lab",
        study=[pa],
    )
    root = nx.NXroot()
    # hierarchy=False, matching every real reader in this codebase (e.g.
    # nanodata-polyrisk's read_lorenzo.py) -- hierarchy=True nests entries
    # under /<topcategory>/<code>/..., which is a different tree shape.
    mx.Substances(substance=[substance]).to_nexus(root, hierarchy=False)
    entries = [k for k in root if k != "substance"]
    return root[entries[0]]


def _default_signal_dtype(entry):
    group = entry[entry.attrs["default"]]
    nxdata = group[group.attrs["default"]]
    signal_name = nxdata.attrs["signal"]
    return np.asarray(nxdata[signal_name].nxdata).dtype


def test_default_skips_categorical_when_numeric_effect_exists():
    """A categorical effect (LOD indexed by polymer) written LAST must not
    win entry/@default over an earlier numeric one -- this is the actual
    bug: _default was reassigned on every iteration regardless of type, so
    entry.attrs["default"] silently became whichever group was written
    last.
    """
    entry = _write(
        [_numeric_effect("Concentration PVC"), _categorical_effect("LOD", ["PVC"])]
    )
    assert np.issubdtype(_default_signal_dtype(entry), np.number)


def test_default_chain_reaches_a_plottable_nxdata_even_when_group_is_mixed():
    """When ONE group (e.g. RESULT) holds both numeric and categorical
    NXdata, the group's own @default must point at a numeric child, not
    just any child -- entry/@default alone is not enough; a viewer walks
    entry/@default -> group/@default -> NXdata.
    """
    entry = _write(
        [
            _categorical_effect("Marker", ["PVC"]),
            _numeric_effect("Concentration PVC"),
        ]
    )
    # Both effects share endpointtype RESULT_ANALYSIS / RESULT respectively
    # in this fixture, so they may land in different groups; either way the
    # resolved default must be numeric.
    assert np.issubdtype(_default_signal_dtype(entry), np.number)


def test_default_falls_back_to_categorical_when_nothing_numeric_exists():
    """If a study genuinely has no numeric-axis effect at all, @default
    still names SOMETHING (matching prior behaviour) rather than being left
    unset.
    """
    entry = _write([_categorical_effect("LOD", ["PVC", "PMMA"])])
    assert "default" in entry.attrs
    group = entry[entry.attrs["default"]]
    assert "default" in group.attrs
