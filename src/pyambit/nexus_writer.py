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
    MetaValueArray,
    ProtocolApplication,
    Study,
    SubstanceRecord,
    Substances,
    Value,
    ValueArray,
)

# tbd parameterize


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

    _categories_collection = "{}{}".format(_categories_collection, entry_id)
    if entry_id not in nx_root:
        nx_root[entry_id] = nx.tree.NXentry()
        nx_root[entry_id].attrs["name"] = entry_id

    nx_root["{}/entry_identifier_uuid".format(entry_id)] = papp.uuid

    nx_root["{}/definition".format(entry_id)] = papp.__class__.__name__

    # experiment_identifier
    # experiment_description
    # collection_identifier collection of related measurements or experiments.
    nx_root["{}/collection_identifier".format(entry_id)] = papp.investigation_uuid
    nx_root["{}/experiment_identifier".format(entry_id)] = papp.assay_uuid
    # collection_description

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
            # ambit category codes and method serve similar role
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
        nx_root["{}/sample/substance".format(entry_id)] = nx.NXlink(substance_id)

    if papp.parameters is not None:
        for prm_path in papp.parameters:
            try:
                value = papp.parameters[prm_path]
                prms = prm_path.split("/")
                if len(prms) == 1:
                    prms = param_lookup(prm_path, value)
                # print(prms,prms[:-1])
                _entry = nx_root[entry_id]
                for _group in prms[:-1]:
                    if _group not in _entry:
                        if _group == "instrument":
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

    if substance.composition is not None:
        for index, ce in enumerate(substance.composition):
            component = nx.NXsample_component()
            # name='' cas='' einecs='' inchikey='YVZATJAPAZIWIL-UHFFFAOYSA-M'
            # inchi='InChI=1S/H2O.Zn/h1H2;/q;+1/p-1' formula='HOZn'
            component.name = ce.component.compound.name
            component.einecs = ce.component.compound.einecs
            component.cas = ce.component.compound.cas
            component.formula = ce.component.compound.formula
            component.inchi = ce.component.compound.inchi
            component.inchikey = ce.component.compound.inchikey
            component.description = ce.relation
            # print(ce.component.values)
            # print(ce.proportion)
            # print(ce.relation)
            _path = "{}/{}_{}".format(substance_id, ce.relation.replace("HAS_", ""), index)
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
        axes.append(
            nx.tree.NXfield(
                effect.axes[key].values,
                name=key.replace("/", "_"),
                long_name="{}{}{}".format(
                    key,
                    "" if effect.axes[key].unit is None else "/",
                    "" if effect.axes[key].unit is None else effect.axes[key].unit
                ).strip(),
                errors=effect.axes[key].errorValue,
                units=effect.axes[key].unit,
            )
        )

    signal = nx.tree.NXfield(
        effect.signal.values,
        name=effect.endpoint,
        units=effect.signal.unit,
        long_name="{}{}{}".format(
            effect.endpoint,
            "" if effect.signal.unit is None else "/", 
            "" if effect.signal.unit is None else effect.signal.unit
        ).strip(),
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
            if isinstance(item, MetaValueArray or isinstance(item, ValueArray)):
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
                long_name = "{} ({}){}{}".format(
                    effect.endpoint,
                    a,
                    "" if effect.signal.unit is None else "/",
                    "" if effect.signal.unit is None else effect.signal.unit,
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
                "DEFAULT" if effect.endpointtype is None else effect.endpointtype
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
            if _default is None:
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
