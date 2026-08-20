import base64
import math
import re
import traceback
from typing import Dict, List

import nexusformat.nexus as nx
import numpy as np

from h5py import string_dtype

from pyambit.ambit_deco import add_ambitmodel_method

from pyambit.datamodel import (
    Composition,
    EffectArray,
    Investigation,
    MetaValueArray,
    ProtocolApplication,
    Study,
    SubstanceRecord,
    Substances,
    Value,
    ValueArray,
)

# tbd parameterize


def _nx_group_for_class(nx_class: str) -> nx.NXgroup:
    """Instantiate the real NeXus group class for `nx_class` (e.g. "NXbeam"),
    falling back to a generic NXgroup for anything nexusformat doesn't
    recognize. nexusformat.nexus dynamically exposes an NXgroup subclass for
    any legal NX* base class name (getattr-based metaprogramming), so this is
    just a guarded attribute lookup, not a hardcoded class table.
    """
    cls = getattr(nx, nx_class, None)
    if cls is None:
        return nx.NXgroup()
    return cls()


def param_lookup(prm, value):
    target = ["environment"]
    _prmlo = prm.lower()
    if "instrument" in _prmlo:
        target = ["instrument"]
    elif "technique" in _prmlo:
        target = ["instrument"]
    elif "wavelength" in _prmlo:
        target = ["instrument", "beam_incident"]
    elif "sample" in _prmlo:
        target = ["sample"]
    elif "material" in _prmlo:
        target = ["sample"]
    elif "dispers" in _prmlo:
        target = ["sample"]
    elif "vortex" in _prmlo:
        target = ["sample"]
    elif "stirr" in _prmlo:
        target = ["sample"]
    elif ("ASSAY" == prm.upper()) or ("E.METHOD" == prm.upper()):
        target = ["experiment_documentation"]
    elif "E.SOP_REFERENCE" == prm:
        target = ["experiment_documentation"]
    elif "OPERATOR" == prm:
        target = ["experiment_documentation"]
    elif prm.startswith("T."):
        target = ["instrument"]
    elif prm.startswith("E."):
        target = ["environment"]
    elif "medium" in _prmlo:
        target = ["environment"]
    elif "cell" in _prmlo:
        target = ["environment"]
    elif "well" in _prmlo:
        target = ["environment"]
    elif "animal" in _prmlo:
        target = ["environment"]
    elif "EXPERIMENT_END_DATE" == prm:
        target = ["end_time"]
    elif "EXPERIMENT_START_DATE" == prm:
        target = ["start_time"]
    elif "__input_file" == prm:
        target = ["experiment_documentation"]
    else:
        target = ["parameters"]
    target.append(prm)
    return target


@add_ambitmodel_method(ProtocolApplication)
def to_nexus(papp: ProtocolApplication, nx_root: nx.NXroot = None, hierarchy=False):
    """
    ProtocolApplication to nexus entry (NXentry)
    Tries to follow https://manual.nexusformat.org/rules.html

    Args:
        papp (ProtocolApplication): The object to be written into nexus format.
        nx_root (nx.NXroot()): Nexus root (or None).

    Returns:
        nx_root: Nexus root

    Raises:
        Exception: on parse

    Examples:
        from  pyambit.datamodel.nexus_writer import to_nexus
        from  pyambit.datamodel.measurements import ProtocolApplication
        pa = ProtocolApplication(**json_data)
        import nexusformat.nexus.tree as nx
        ne = pa.to_nexus(nx.NXroot())
        print(ne.tree)
    """
    if nx_root is None:
        print("nx_root = nx.NXroot()")
        nx_root = nx.NXroot()

    # https://manual.nexusformat.org/classes/base_classes/NXentry.html
    try:
        _categories_collection = ""
        if hierarchy:
            if papp.protocol.topcategory not in nx_root:
                nx_root[papp.protocol.topcategory] = nx.NXgroup()
            if papp.protocol.category.code not in nx_root[papp.protocol.topcategory]:
                nx_root[papp.protocol.topcategory][
                    papp.protocol.category.code
                ] = nx.NXgroup()
            _categories_collection = "/{}/{}".format(
                papp.protocol.topcategory, papp.protocol.category.code
            )
        try:
            provider = (
                ""
                if papp.citation.owner is None
                else papp.citation.owner.replace("/", "_").upper()
            )
        except BaseException:  # noqa: B036 FIXME
            provider = "@"
        if papp.nx_name is None:
            entry_id = "{}/{}_{}".format(_categories_collection, provider, papp.uuid)
        else:
            entry_id = "{}/{}_{}".format(
                _categories_collection,
                "entry" if papp.nx_name is None else papp.nx_name,
                papp.uuid,
            )
    except Exception:
        # print(err)
        entry_id = "/{}_{}".format(
            "entry" if papp.nx_name is None else papp.nx_name, papp.uuid
        )

    # entry_id can come out with a REDUNDANT leading "/" whenever there is
    # no real hierarchy path in front of it -- either hierarchy=False (the
    # common case; _categories_collection stayed "") or the except-branch
    # fallback (which always starts a fresh "/..." regardless of
    # _categories_collection). NXgroup's __setitem__ treats any "/" as a
    # path separator, so nx_root[entry_id] then splits on an empty first
    # segment and writes a mangled entry (observed: a literal "@_<name>"
    # key) instead of a normal NXentry -- confirmed by inspection, not a
    # guess. A genuine hierarchy path ("/CAT/CODE" + "/name_uuid") is a
    # single leading slash too, so only strip a slash that isn't already
    # accounted for by _categories_collection.
    if entry_id.startswith("/") and not entry_id.startswith(_categories_collection + "/"):
        entry_id = entry_id.lstrip("/")

    _categories_collection = "{}{}".format(_categories_collection, entry_id)
    if entry_id not in nx_root:
        nx_root[entry_id] = nx.tree.NXentry()
        nx_root[entry_id].attrs["name"] = entry_id

    nx_root["{}/entry_identifier_uuid".format(entry_id)] = papp.uuid

    nx_root["{}/definition".format(entry_id)] = papp.__class__.__name__

    # experiment_identifier
    # experiment_description
    # collection_identifier collection of related measurements or experiments.
    investigation = papp.investigation_uuid
    investigation_uuid = (
        investigation.uuid if isinstance(investigation, Investigation) else investigation
    )
    nx_root["{}/collection_identifier".format(entry_id)] = investigation_uuid
    nx_root["{}/experiment_identifier".format(entry_id)] = papp.assay_uuid
    # collection_description

    # An investigation can span many ProtocolApplications, many substances,
    # and many separate writes -- it belongs to none of them individually,
    # so its label is written ONCE per uuid (mirroring substance/<uuid>
    # below) and every entry that shares the uuid links to it, rather than
    # repeating the title/description into each entry. Every entry with an
    # investigation_uuid gets linked, whether or not the richer
    # Investigation(title=..., description=...) form was used -- a bare
    # uuid still groups its entries together, just without a label.
    if investigation_uuid is not None:
        investigation_id = "investigation/{}".format(investigation_uuid)
        if "investigation" not in nx_root:
            nx_root["investigation"] = nx.NXgroup()
        if investigation_id not in nx_root:
            nx_root[investigation_id] = nx.NXgroup()
            nx_root[investigation_id].attrs["uuid"] = investigation_uuid
        # Fill in the label whenever a richer Investigation object supplies
        # one, regardless of write order: a bare-uuid ProtocolApplication
        # may be processed before the one carrying the actual
        # Investigation(title=..., ...), and the group must not be left
        # permanently label-less just because it happened to be created
        # first. Never overwrite an already-set title/description, so this
        # stays idempotent no matter how many entries share the uuid.
        group = nx_root[investigation_id]
        if isinstance(investigation, Investigation):
            if investigation.title is not None and "title" not in group:
                group.title = investigation.title
            if (
                investigation.description is not None
                and "description" not in group.attrs
            ):
                group.attrs["description"] = investigation.description
            if investigation.image is not None and "image" not in group:
                # NXnote with type="image/png" and data as a uint8 byte
                # array is the NeXus-native way to embed a picture -- an
                # HDF5/NeXus-aware viewer (H5Web, HDFView) can render it
                # directly. A base64 STRING field would just show as text
                # ("iVBORw0KG...") to any such viewer; only code that knows
                # to decode it first would ever see a picture.
                image_bytes = base64.b64decode(investigation.image)
                note = nx.NXnote()
                note.type = "image/png"
                note.data = np.frombuffer(image_bytes, dtype=np.uint8)
                if investigation.image_filename is not None:
                    note.file_name = investigation.image_filename
                group["image"] = note
        nx_root["{}/investigation".format(entry_id)] = nx.NXlink(investigation_id)

    # duration
    # program_name
    # revision
    # experiment_documentation (SOP)
    # notes
    # USER: (optional) NXuser
    # SAMPLE: (optional) NXsample
    # INSTRUMENT: (optional) NXinstrument
    # COLLECTION: (optional) NXcollection
    # MONITOR: (optional) NXmonitor
    # PARAMETERS: (optional) NXparameters Container for parameters,
    #   usually used in processing or analysis.
    # PROCESS: (optional) NXprocess
    # SUBENTRY: (optional) NXsubentry Group of multiple application definitions
    #   for “multi-modal” (e.g. SAXS/WAXS) measurements.

    try:
        if not (papp.protocol is None):
            docid = "{}/experiment_documentation".format(entry_id)
            if docid not in nx_root:
                nx_root[docid] = nx.NXnote()
            experiment_documentation = nx_root[docid]
            experiment_documentation["date"] = papp.updated
            # category = nx.NXgroup()
            # experiment_documentation["category"] = category
            experiment_documentation["protocol"] = nx.NXcollection()
            experiment_documentation["protocol"].attrs[
                "topcategory"
            ] = papp.protocol.topcategory
            experiment_documentation["protocol"].attrs[
                "code"
            ] = papp.protocol.category.code
            experiment_documentation["protocol"].attrs[
                "term"
            ] = papp.protocol.category.term
            experiment_documentation["protocol"].attrs[
                "title"
            ] = papp.protocol.category.title
            experiment_documentation["protocol"].attrs[
                "endpoint"
            ] = papp.protocol.endpoint
            experiment_documentation["protocol"].attrs[
                "guideline"
            ] = papp.protocol.guideline
            # definition is usually reference to the Nexus XML definition
            # ambit category codes and method serve similar role.
            #
            # Exception: if papp.parameters already explicitly declares this
            # entry as NXraman (papp.parameters["/definition"] == "NXraman",
            # the exact signal NXRamanProtocolApplication.sync_parameters()
            # sets), skip the AMBIT_DATAMODEL rewrite entirely so an
            # explicitly-set Raman /definition survives to the written file.
            # Scoped narrowly to this one literal value - any other explicit
            # /definition (including other AMBIT-specific strings) still gets
            # overwritten exactly as before, so every other protocol/consumer
            # (including the generic AMBIT-JSON-upload path) is unaffected.
            _is_nxraman_entry = (
                papp.parameters is not None
                and papp.parameters.get("/definition", papp.parameters.get("definition"))
                == "NXraman"
            )
            if not _is_nxraman_entry:
                nx_root["{}/definition".format(entry_id)] = (
                    "/AMBIT_DATAMODEL/{}/{}/{}".format(
                        papp.protocol.topcategory,
                        papp.protocol.category.code,
                        papp.protocol.guideline,
                    )
                )

            if papp.parameters is not None:
                for tag in ["E.method", "ASSAY"]:
                    if tag in papp.parameters:
                        experiment_documentation.attrs["method"] = papp.parameters[tag]
                        if not _is_nxraman_entry:
                            nx_root["{}/definition".format(entry_id)] = (
                                "/AMBIT_DATAMODEL/{}/{}/{}".format(
                                    papp.protocol.topcategory,
                                    papp.protocol.category.code,
                                    papp.parameters[tag],
                                )
                            )

    except Exception as err:
        raise Exception(
            "ProtocolApplication: protocol parsing error " + str(err)
        ) from err

    nxmap = nx_root["{}/definition".format(entry_id)]
    nxmap.attrs["ProtocolApplication"] = entry_id
    nxmap.attrs["PROTOCOL_APPLICATION_UUID"] = "{}/entry_identifier_uuid".format(
        entry_id
    )

    # no need to repeat these, rather make a xml definition and refer to it
    # nxmap.attrs["INVESTIGATION_UUID"] = "{}/collection_identifier".format(entry_id)
    # nxmap.attrs["ASSAY_UUID"] = "{}/experiment_identifier".format(entry_id)
    # nxmap.attrs["Protocol"] = "{}/experiment_documentation".format(entry_id)
    # nxmap.attrs["Citation"] = "{}/reference".format(entry_id)
    # nxmap.attrs["Substance"] = "{}/sample".format(entry_id)
    # nxmap.attrs["Parameters"] = ["instrument", "environment", "parameters"]
    # nxmap.attrs["EffectRecords"] = "datasets"

    try:
        citation_id = "{}/reference".format(entry_id)
        if not (citation_id in nx_root):
            nx_root[citation_id] = nx.NXcite()
        if papp.citation is not None:
            nx_root[citation_id]["title"] = papp.citation.title
            nx_root[citation_id]["year"] = papp.citation.year
            nx_root[citation_id]["owner"] = papp.citation.owner
            doi = extract_doi(papp.citation.title)
            if doi is not None:
                nx_root[citation_id]["doi"] = doi
            if papp.citation.title.startswith("http"):
                nx_root[citation_id]["url"] = papp.citation.title

        # url, doi, description
    except Exception as err:
        raise Exception(
            "ProtocolApplication: citation data parsing error " + str(err)
        ) from err

    if "substance" not in nx_root:
        nx_root["substance"] = nx.NXgroup()

    # now the actual sample
    sample_id = "{}/sample".format(entry_id)
    if sample_id not in nx_root:
        nx_root["{}/sample".format(entry_id)] = nx.NXsample()

    sample = nx_root["{}/sample".format(entry_id)]

    if papp.owner is not None:
        substance_id = "substance/{}".format(papp.owner.substance.uuid)
        if substance_id not in nx_root:
            nx_root[substance_id] = nx.NXsample()
            nx_root[substance_id].attrs["uuid"] = papp.owner.substance.uuid
        # Absolute target ("/substance/...", not "substance/..."): NXlink
        # resolves a relative target against its OWN parent group
        # (nx.NXlink.internal_link), not the root - since this link lives
        # under "{entry_id}/sample/", a relative "substance/{uuid}" target
        # sends resolution on a walk that (with nexusformat 2.0.0, given many
        # ProtocolApplications sharing one owner substance, as in
        # study.json's fixture) recurses without terminating. Pre-existing
        # bug, reproduces on unmodified code; unrelated to but found during
        # NXraman work.
        nx_root["{}/sample/substance".format(entry_id)] = nx.NXlink(
            "/{}".format(substance_id)
        )

    nx_class_hints = {}
    nxraman = getattr(papp, "nxraman", None)
    if nxraman is not None:
        from pyambit.nexus_models.flatten import flatten_nx_model

        _, nx_class_hints = flatten_nx_model(nxraman)

    if papp.parameters is not None:
        for prm_path in papp.parameters:
            try:
                value = papp.parameters[prm_path]
                # Strip leading empty segments from a leading "/" (e.g.
                # "/definition".split("/") == ["", "definition"]) - a bare
                # parser fix, independent of any particular protocol/caller:
                # it can only turn a currently-broken path (which created a
                # stray ""-named group) into the correct one, never break an
                # already-working path, since no legitimate path was ever
                # relying on a leading empty segment.
                prms = [p for p in prm_path.split("/") if p != ""]
                if not prms:
                    continue
                if len(prms) == 1 and "/" not in prm_path:
                    prms = param_lookup(prm_path, value)
                # print(prms,prms[:-1])
                _entry = nx_root[entry_id]
                group_path_so_far = ""
                for _group in prms[:-1]:
                    group_path_so_far = (
                        f"{group_path_so_far}/{_group}" if group_path_so_far else _group
                    )
                    if _group not in _entry:
                        hinted_class = nx_class_hints.get(group_path_so_far)
                        if hinted_class is not None:
                            _entry[_group] = _nx_group_for_class(hinted_class)
                        elif _group == "instrument":
                            _entry[_group] = nx.NXinstrument()
                        elif _group == "environment":
                            _entry[_group] = nx.NXenvironment()
                        elif _group == "parameters":
                            _entry[_group] = nx.NXcollection()
                        elif _group == "experiment_documentation":
                            _entry[_group] = nx.NXnote()
                        else:
                            _entry[_group] = nx.NXgroup()
                    _entry = _entry[_group]
                target = _entry
                prm = prms[-1]

                if isinstance(value, str):
                    target[prm] = nx.NXfield(value)
                elif isinstance(value, int):
                    target[prm] = nx.NXfield(value)
                elif isinstance(value, float):
                    target[prm] = nx.NXfield(value)
                elif isinstance(value, Value):
                    # tbd ranges?
                    target[prm] = nx.NXfield(value.loValue, unit=value.unit)
                else:
                    target[prm] = nx.NXfield(str(value))
            except Exception as err:
                raise Exception(
                    "ProtocolApplication: parameters parsing error {} {}".format(
                        err, prm
                    )
                ) from err

    if papp.owner is not None:
        try:
            sample.attrs["uuid"] = papp.owner.substance.uuid
            sample["provider"] = papp.owner.company.name
        except Exception as err:
            raise Exception(
                "ProtocolApplication owner (sample) parsing error " + str(err)
            ) from err

    try:
        process_pa(papp, nx_root[entry_id], nx_root)
    except Exception as err:
        print("Exception traceback:\n%s", traceback.format_exc())
        raise Exception(
            "ProtocolApplication: effectrecords parsing error {} {}".format(
                err, entry_id
            )
        ) from err

    # nx_root["/group_byexperiment"] = nx.NXgroup()
    # print(nx_root[entry_id].attrs)
    # nx_root["/group_byexperiment{}".format(entry_id)] = nx.NXlink(
    #     "{}/RAW_DATA".format(entry_id),abspath=True,soft=True)
    # nx_root["/group_byexperiment/{}".format("xyz")] = nx.NXlink(substance_id)
    # nx.NXlink(nx_root[entry_id])
    # nx_root[_categories_collection] = nx.NXlink(entry_id)
    return nx_root


@add_ambitmodel_method(Study)
def to_nexus(study: Study, nx_root: nx.NXroot = None, hierarchy=False):  # noqa: F811
    if nx_root is None:
        nx_root = nx.NXroot()
    for papp in study.study:
        papp.to_nexus(nx_root=nx_root, hierarchy=hierarchy)

    return nx_root


@add_ambitmodel_method(SubstanceRecord)
def to_nexus(  # noqa: F811
    substance: SubstanceRecord, nx_root: nx.NXroot = None, hierarchy=False
):
    """
    SubstanceRecord to nexus entry (NXentry)

    Args:
        substance record (SubstanceRecord): The object to be written.
        nx_root (nx.NXroot()): Nexus root (or None).

    Returns:
        nx_root: Nexus root

    Raises:
        Exception: on parse

    Examples:
        import  pyambit.datamodel.measurements as m2n
        from pyambit.datamodel.nexus_writer import to_nexus
        import nexusformat.nexus.tree as nx
        substance="GRCS-18f0f0e8-b5f4-39bc-b8f8-9c869c8bd82f"
        url = "https://apps.ideaconsult.net/gracious/substance/{}?media=application/json".format(substance)
        response = requests.get(url)
        sjson = response.json()
        nxroot = nx.NXroot()
        substances = m2n.Substances(**sjson)
        for substance in substances.substance:
            url = "{}/composition?media=application/json".format(substance.URI)
            response = requests.get(url)
            pjson = response.json()
            cmp = m2n.Composition(**pjson)
            substance.composition = cmp.composition # note the assignment
            url = "{}/study?media=application/json".format(substance.URI)
            response = requests.get(url)
            sjson = response.json()
        substance.study = m2n.Study(**sjson).study
        try:
            ne = substance.to_nexus(nxroot)
        except Exception as err:
            print(substance.URI)
            print(err)
        nxroot.save("example.nxs",mode="w")
    """  # noqa: B950
    if nx_root is None:
        nx_root = nx.NXroot()

    if "substance" not in nx_root:
        nx_root["substance"] = nx.NXgroup()
    substance_id = "substance/{}".format(substance.i5uuid)
    if substance_id not in nx_root:
        nx_root[substance_id] = nx.NXsample()
    nx_root[substance_id].attrs["uuid"] = substance.i5uuid
    nx_root[substance_id].name = substance.name
    nx_root[substance_id].attrs["publicname"] = substance.publicname
    nx_root[substance_id].attrs["substanceType"] = substance.substanceType
    nx_root[substance_id].attrs["ownerName"] = substance.ownerName
    nx_root[substance_id].attrs["ownerUUID"] = substance.ownerUUID

    # externalIdentifiers is a list of (type, id) pairs (AMBIT Java's
    # ambit2.base.data.substance.ExternalIdentifier) -- NeXus/HDF5 attrs
    # can't hold a list of structs directly, so store as two parallel
    # string-array attrs rather than inventing a JSON-in-attr encoding;
    # nexus_parser.substance_from_nexus reads them back the same way.
    if substance.externalIdentifiers:
        nx_root[substance_id].attrs["externalIdentifierTypes"] = [
            "" if ext_id.type is None else ext_id.type
            for ext_id in substance.externalIdentifiers
        ]
        nx_root[substance_id].attrs["externalIdentifierIds"] = [
            "" if ext_id.id is None else ext_id.id
            for ext_id in substance.externalIdentifiers
        ]

    if substance.composition is not None:
        for index, ce in enumerate(substance.composition):
            component = nx.NXsample_component()
            # name='' cas='' einecs='' inchikey='YVZATJAPAZIWIL-UHFFFAOYSA-M'
            # inchi='InChI=1S/H2O.Zn/h1H2;/q;+1/p-1' formula='HOZn'
            component.name = ce.component.compound.name
            # NXsample_component's real NXDL declares "chemical_formula",
            # not "formula" -- writing "formula" here silently created a
            # field the schema doesn't recognize while never populating the
            # one it does. cas/einecs/inchi/inchikey have no NXDL field at
            # all on NXsample_component (nexusformat still lets you set
            # arbitrary attrs on the object), kept as attrs rather than
            # dropped since Compound carries real, useful identifiers.
            component.chemical_formula = ce.component.compound.formula
            component.attrs["einecs"] = ce.component.compound.einecs
            component.attrs["cas"] = ce.component.compound.cas
            component.attrs["inchi"] = ce.component.compound.inchi
            component.attrs["inchikey"] = ce.component.compound.inchikey
            component.description = ce.relation
            # print(ce.component.values)
            # print(ce.proportion)
            # print(ce.relation)
            _path = "{}/{}_{}".format(
                substance_id, ce.relation.replace("HAS_", ""), index
            )
            nx_root[_path] = component
            if ce.component.values is not None:
                for key in ce.component.values.keys():
                    nx_root[_path].attrs[key] = ce.component.values[key]

    if substance.study is not None:
        for papp in substance.study:
            papp.to_nexus(nx_root, hierarchy=hierarchy)

    return nx_root


@add_ambitmodel_method(Substances)
def to_nexus(  # noqa: F811
    substances: Substances, nx_root: nx.NXroot = None, hierarchy=False
):
    if nx_root is None:
        nx_root = nx.NXroot()
    for substance in substances.substance:
        substance.to_nexus(nx_root, hierarchy)
    return nx_root


@add_ambitmodel_method(Composition)
def to_nexus(composition: Composition, nx_root: nx.NXroot = None):  # noqa: F811
    if nx_root is None:
        nx_root = nx.NXroot()

    return nx_root


def format_name(meta_dict, key, default=""):
    name = meta_dict[key] if key in meta_dict else default
    return name if isinstance(name, str) else default if math.isnan(name) else name


def effectarray2data(effect: EffectArray):

    def is_alternate_axis(key: str, alt_axes: Dict[str, List[str]]) -> bool:
        """
        Check if a given key is an alternate axis.

        Parameters:
        - key: The axis name to check.
        - alt_axes: Dictionary where keys are primary axis names and values are lists of
        alternative axis names.

        Returns:
        - True if the key is an alternate axis, False otherwise.
        """
        if alt_axes is None:
            return False
        for alt_list in alt_axes.values():
            if key in alt_list:
                return True
        return False

    # uncertanties can be specified for both signal and axes through FIELDNAME_errors
    axes = []
    for key in effect.axes:
        axis_values = effect.axes[key].values
        # A categorical axis (Location: "Norway"/"Utrecht") arrives as an
        # object-dtype numpy array of Python strings, which h5py cannot write
        # (h5t.py_create has no native equivalent for dtype('O')) -- the same
        # problem the textValue auxiliary already works around below.
        axis_dtype = None
        if isinstance(axis_values, np.ndarray) and axis_values.dtype.kind == "O":
            axis_dtype = string_dtype(encoding="utf-8")
        axes.append(
            nx.tree.NXfield(
                axis_values,
                name=key.replace("/", "_"),
                long_name="{}{}{}".format(
                    key,
                    "" if effect.axes[key].unit is None else "/",
                    "" if effect.axes[key].unit is None else effect.axes[key].unit,
                ).strip(),
                errors=effect.axes[key].errorValue,
                units=effect.axes[key].unit,
                dtype=axis_dtype,
            )
        )

    signal_values = effect.signal.values
    # Same object-dtype problem as the axes above, for a text-valued signal
    # (e.g. a "Marker" EffectArray whose values are compound names, not
    # numbers -- one legitimate array-shaped result, just not numeric).
    signal_dtype = None
    if isinstance(signal_values, np.ndarray) and signal_values.dtype.kind == "O":
        signal_dtype = string_dtype(encoding="utf-8")
    signal = nx.tree.NXfield(
        signal_values,
        name=effect.endpoint,
        units=effect.signal.unit,
        long_name="{}{}{}".format(
            effect.endpoint,
            "" if effect.signal.unit is None else "/",
            "" if effect.signal.unit is None else effect.signal.unit,
        ).strip(),
        dtype=signal_dtype,
    )
    if effect.signal.conditions is not None:
        for key in effect.signal.conditions:
            signal.attrs[key] = effect.signal.conditions[key]

    nxdata = nx.tree.NXdata(
        signal=signal,
        axes=None if len(axes) == 0 else axes,
        errors=effect.signal.errorValue,
        # auxiliary_signals=None if len(aux_signals) < 1 else aux_signals,
    )
    aux_signals = []

    if effect.signal.auxiliary:
        for a in effect.signal.auxiliary:
            item = effect.signal.auxiliary[a]
            # NB the operator precedence bug this replaces:
            # `isinstance(item, MetaValueArray or isinstance(item, ValueArray))`
            # collapses to `isinstance(item, MetaValueArray)`, because
            # `MetaValueArray or ...` short-circuits on the truthy class. A plain
            # ValueArray therefore fell through to the ndarray branch and
            # silently borrowed the SIGNAL's unit -- labelling a dimensionless
            # replicate count "g".
            if isinstance(item, (MetaValueArray, ValueArray)):
                _tmp = item.values
                _tmp_unit = item.unit
                _tmp_meta = item.conditions

            elif isinstance(item, np.ndarray):
                _tmp = item
                _tmp_unit = effect.signal.unit
                _tmp_meta = None
            else:
                continue

            if _tmp.size > 0:
                _auxname = a.replace("/", "_")
                # An auxiliary is named for ITSELF, with ITS OWN unit. Naming it
                # after the primary signal produced labels like
                # "Tm1 (1st heating) (Tc (cooling))/degC" -- which is what a
                # viewer displays, since it shows long_name -- and borrowed the
                # primary's unit even where the auxiliary had its own.
                # The auxiliary's OWN unit, with no fallback to the signal's: a
                # ValueArray carrying unit=None is deliberately dimensionless
                # (a replicate count, a normalised ratio), and borrowing the
                # signal's unit would label it "g" or "counts".
                long_name = "{}{}{}".format(
                    a,
                    "" if _tmp_unit is None else "/",
                    "" if _tmp_unit is None else _tmp_unit,
                ).strip()
                if _auxname == "textValue":
                    nxdata[_auxname] = nx.tree.NXfield(
                        _tmp,
                        name=_auxname,
                        units=_tmp_unit,
                        long_name=long_name,
                        dtype=string_dtype(encoding="utf-8"),
                    )
                else:
                    nxdata[_auxname] = nx.tree.NXfield(
                        _tmp, name=_auxname, units=_tmp_unit, long_name=long_name
                    )

                if _tmp_meta is not None:
                    for key in _tmp_meta:
                        nxdata[_auxname].attrs[key] = _tmp_meta[key]
                aux_signals.append(_auxname)

        if len(aux_signals) > 0:
            nxdata.attrs["auxiliary_signals"] = aux_signals
    if effect.conditions:
        for key in effect.conditions:
            nxdata.attrs[key] = effect.conditions[key]

    if effect.axis_groups:
        index = 0
        for key in effect.axes:
            if is_alternate_axis(key, effect.axis_groups):
                continue
            nxdata.attrs["{}_indices".format(key)] = index
            index = index + 1
        for primary_axis, alt_cols in effect.axis_groups.items():
            for alt_col in alt_cols:
                nxdata.attrs["{}_indices".format(alt_col)] = nxdata.attrs[
                    "{}_indices".format(primary_axis)
                ]
    else:
        index = len(effect.axes)
        # otherwise we don't need indices

    nxdata.attrs["interpretation"] = (
        "scalar" if index == 0 else ("spectrum" if index == 1 else "image")
    )
    nxdata.title = effect.nx_name
    return nxdata


def _has_numeric_axes(group) -> bool:
    """True if `group` (an NXprocess/NXgroup holding NXdata children, as
    written above) has at least one NXdata whose signal and every axis are
    numeric -- i.e. something a generic NeXus viewer's default plot can
    actually render, as opposed to a categorical axis (e.g. "standard":
    ["VUA_PMMA_Co", ...]), which is exactly what triggers a viewer's
    "Expected numeric type" error when picked as the entry's @default.
    """
    return any(
        isinstance(child, nx.tree.NXdata) and _has_numeric_axes_data(child)
        for child in group.values()
    )


def _has_numeric_axes_data(nxdata) -> bool:
    """True if a single NXdata's signal and every axis are numeric."""
    signal_name = nxdata.attrs.get("signal")
    fields = [nxdata[signal_name]] if signal_name in nxdata else []
    axes = nxdata.attrs.get("axes")
    if axes:
        axes = [axes] if isinstance(axes, str) else list(axes)
        fields += [nxdata[a] for a in axes if a in nxdata]
    return bool(fields) and all(
        np.issubdtype(np.asarray(f.nxdata).dtype, np.number) for f in fields
    )


def process_pa(pa: ProtocolApplication, entry=None, nx_root: nx.NXroot = None):

    if entry is None:
        entry = nx.tree.NXentry()

    _default = None
    try:
        _path = "/substance/{}".format(pa.owner.substance.uuid)
        # print(_path, nx_root[_path].name)
        substance_name = nx_root[_path].name
    except BaseException:  # noqa: B036 FIXME
        substance_name = ""

    effectarrays_only, df = pa.convert_effectrecords2array()

    if effectarrays_only:  # if we have EffectArray in the pa list
        # _endpointtype_groups = {}
        index = 0
        for effect in effectarrays_only:
            index = index + 1
            _group_key = (
                "DEFAULT"
                if effect.endpointtype is None
                else effect.endpointtype.upper().replace(" ", "_")
            )
            if _group_key not in entry:
                if effect.endpointtype in ("RAW_DATA", "RAW DATA", "RAW", "raw data"):
                    entry[_group_key] = nx.tree.NXgroup()
                else:
                    entry[_group_key] = nx.tree.NXprocess()
                    # entry[_group_key]["NOTE"] = nx.tree.NXnote()
                    entry[_group_key]["description"] = effect.endpointtype
            #    entry[_group_key] = _endpointtype_groups[_group_key]

            entryid = "{}_{}".format(
                (
                    effect.endpoint
                    if effect.nx_name is None
                    else effect.nx_name.replace("/", "_")
                ),
                index,
            )
            if entryid in entry[_group_key]:
                del entry[_group_key][entryid]
                print("replacing {}/{}".format(_group_key, entryid))

            nxdata = effectarray2data(effect)

            entry[_group_key][entryid] = nxdata
            # `if _default is None` was true on EVERY iteration (_default is
            # never reassigned), so entry.attrs["default"] silently ended up
            # as whichever group was written LAST, not first -- and for a
            # study whose last-written effects are categorical (e.g.
            # CALIBRATION indexed by "standard", a string axis), a generic
            # NeXus viewer's default plot then fails with something like
            # "Expected numeric type". Fixed by tracking it properly AND
            # completing the @default chain one level further: NeXus
            # expects entry/@default to name a group whose OWN @default in
            # turn names a plottable NXdata (root -> entry -> group ->
            # NXdata) -- entry/@default alone is not enough, a viewer still
            # has to pick a child within that group, and previously nothing
            # told it which. Preferring a numeric NXdata here means the
            # first numeric group/entry found wins and is never displaced
            # by a later categorical one.
            group = entry[_group_key]
            is_numeric = _has_numeric_axes_data(nxdata)
            # Group-level default: set on the first child written to this
            # group (so the chain is always complete, even if nothing
            # numeric ever turns up), then upgraded the first time a
            # numeric child arrives.
            if "default" not in group.attrs or (
                is_numeric and not _has_numeric_axes_data(group[group.attrs["default"]])
            ):
                group.attrs["default"] = entryid

            if _default is None:
                _default = _group_key
                entry.attrs["default"] = _group_key
            else:
                current_default_numeric = _has_numeric_axes(
                    entry[entry.attrs.get("default", _default)]
                )
                if is_numeric and not current_default_numeric:
                    entry.attrs["default"] = _group_key

            if nxdata.title is None:
                nxdata.title = (
                    "{} (by {}) {}".format(
                        effect.endpoint, pa.citation.owner, substance_name
                    )
                    if pa.nx_name is None
                    else pa.nx_name
                )

    return entry


def extract_doi(input_str):
    # Regular expression pattern to match DOI
    doi_pattern = r"(10\.\d{4,}(?:\.\d+)*\/\S+)"
    # Search for the DOI pattern in the input string
    match = re.search(doi_pattern, input_str)
    if match:
        return match.group(1)  # Return the matched DOI
    else:
        return None  # Return None if DOI not found
