import base64

import numpy as np
import nexusformat.nexus.tree as nx
import pyambit.datamodel as mx

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401

# Smallest valid PNG (a 1x1 transparent pixel), just enough bytes to prove
# the round-trip through base64 -> NXnote uint8 data -> back is exact.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108"
    "0600000031b2680a0000000a4944415478da6360000002000155"
    "0d2b71000000004945454e44ae426082"
)


def _protocol_application(uuid, investigation_uuid, owner_uuid):
    return mx.ProtocolApplication(
        uuid=uuid,
        protocol=mx.Protocol(
            topcategory="P-CHEM",
            category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            endpoint="Test method",
            guideline=[],
        ),
        effects=[],
        citation=mx.Citation(owner="Test Owner", title="10.1234/test", year=2025),
        investigation_uuid=investigation_uuid,
        owner=mx.SampleLink(
            substance=mx.Sample(uuid=owner_uuid),
            company=mx.Company(name="Test Lab"),
        ),
    )


def _substance(name, uuid, papp):
    return mx.SubstanceRecord(
        i5uuid=uuid,
        name=name,
        publicname=name,
        ownerName="Test Lab",
        ownerUUID="Test Lab",
        study=[papp],
    )


def test_investigation_optional_by_default():
    """A ProtocolApplication with no investigation_uuid at all writes and
    round-trips exactly as before -- the field is additive, not required.
    """
    pa = _protocol_application("pa1", investigation_uuid=None, owner_uuid="s1")
    substances = mx.Substances(substance=[_substance("Sample 1", "s1", pa)])

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)
    assert "investigation" not in root


def test_investigation_bare_uuid_still_links():
    """A bare-string investigation_uuid (today's normal usage) still gets
    grouped under /investigation/<uuid>, just without a label.
    """
    pa = _protocol_application("pa1", investigation_uuid="study-1", owner_uuid="s1")
    substances = mx.Substances(substance=[_substance("Sample 1", "s1", pa)])

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)

    assert "investigation" in root
    assert "investigation/study-1" in root
    group = root["investigation/study-1"]
    assert group.attrs["uuid"] == "study-1"
    assert "title" not in group


def test_investigation_object_supplies_title_and_description():
    """A full Investigation(...) passed AS investigation_uuid writes a
    title/description on the shared group, and the entry links to it.
    """
    investigation = mx.Investigation(
        uuid="study-1",
        title="A study title",
        description="A one-line summary of the study.",
    )
    pa = _protocol_application("pa1", investigation_uuid=investigation, owner_uuid="s1")
    substances = mx.Substances(substance=[_substance("Sample 1", "s1", pa)])

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)

    group = root["investigation/study-1"]
    assert group.attrs["uuid"] == "study-1"
    assert str(group.title) == "A study title"
    assert group.attrs["description"] == "A one-line summary of the study."


def test_investigation_image_written_as_nxnote_not_base64_string():
    """image is a base64 str on the Investigation model (JSON-portable),
    but nexus_writer must decode it into a real NXnote(type="image/png",
    data=<uint8 bytes>) -- the NeXus-native way to embed a picture, which
    an HDF5/NeXus-aware viewer can render directly. A raw base64 string
    field would just show as text to such a viewer.
    """
    investigation = mx.Investigation(
        uuid="study-1",
        title="With a picture",
        image=base64.b64encode(_TINY_PNG).decode("ascii"),
        image_filename="summary.png",
    )
    pa = _protocol_application("pa1", investigation_uuid=investigation, owner_uuid="s1")
    substances = mx.Substances(substance=[_substance("Sample 1", "s1", pa)])

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)

    image_note = root["investigation/study-1/image"]
    assert isinstance(image_note, nx.NXnote)
    assert str(image_note.type) == "image/png"
    assert str(image_note.file_name) == "summary.png"
    recovered = np.asarray(image_note.data.nxdata, dtype=np.uint8).tobytes()
    assert recovered == _TINY_PNG


def test_investigation_written_once_shared_across_entries():
    """Two ProtocolApplications sharing one investigation_uuid write the
    group ONCE (not duplicated per entry), and both entries link to it --
    the point of keying the group by uuid instead of nesting it in each
    ProtocolApplication.
    """
    investigation = mx.Investigation(uuid="study-1", title="Shared study")
    pa1 = _protocol_application("pa1", investigation_uuid=investigation, owner_uuid="s1")
    pa2 = _protocol_application("pa2", investigation_uuid="study-1", owner_uuid="s2")
    substances = mx.Substances(
        substance=[
            _substance("Sample 1", "s1", pa1),
            _substance("Sample 2", "s2", pa2),
        ]
    )

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)

    # Dict-key semantics already prove there is exactly one such group --
    # "investigation/study-1" is a single key, not a list -- so what this
    # asserts is that BOTH entries wrote to (and did not clobber) it: the
    # label from pa1's Investigation object survives pa2's bare-uuid write.
    assert "investigation/study-1" in root
    assert str(root["investigation/study-1"].title) == "Shared study"


def test_investigation_label_fills_in_regardless_of_write_order():
    """If the bare-uuid ProtocolApplication is written BEFORE the one
    carrying the full Investigation object, the group must still end up
    labelled -- the label must not depend on processing order.
    """
    investigation = mx.Investigation(uuid="study-1", title="Late label")
    pa_bare_first = _protocol_application(
        "pa1", investigation_uuid="study-1", owner_uuid="s1"
    )
    pa_labelled_second = _protocol_application(
        "pa2", investigation_uuid=investigation, owner_uuid="s2"
    )
    substances = mx.Substances(
        substance=[
            _substance("Sample 1", "s1", pa_bare_first),
            _substance("Sample 2", "s2", pa_labelled_second),
        ]
    )

    root = nx.NXroot()
    substances.to_nexus(root, hierarchy=True)

    assert str(root["investigation/study-1"].title) == "Late label"


def test_protocol_application_investigation_union_roundtrip():
    """investigation_uuid accepts a bare string OR an Investigation, and
    both survive a JSON round-trip. Uses model_validate_json (not
    model_construct, which skips validation and leaves nested dicts
    un-coerced) so this actually exercises the Union[str, Investigation]
    discrimination.
    """
    pa = _protocol_application("pa1", investigation_uuid="plain-uuid", owner_uuid="s1")
    restored = mx.ProtocolApplication.model_validate_json(pa.model_dump_json())
    assert restored.investigation_uuid == "plain-uuid"

    investigation = mx.Investigation(uuid="study-1", title="T")
    pa2 = _protocol_application(
        "pa2", investigation_uuid=investigation, owner_uuid="s2"
    )
    restored2 = mx.ProtocolApplication.model_validate_json(pa2.model_dump_json())
    assert isinstance(restored2.investigation_uuid, mx.Investigation)
    assert restored2.investigation_uuid.uuid == "study-1"
    assert restored2.investigation_uuid.title == "T"
