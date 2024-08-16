import math
import numbers
import re
import traceback
from typing import List

import nexusformat.nexus as nx
import numpy as np
import pandas as pd

# from pydantic import validate_arguments

from pyambit.datamodel import Substances,SubstanceRecord, Composition,Study, ProtocolApplication, Value, EffectArray, effects2df
from pyambit.ambit_deco import add_ambitmodel_method


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
        nx_root = nx.NXroot()

    # https://manual.nexusformat.org/classes/base_classes/NXentry.html
    try:
        _categories_collection = ""
        if hierarchy:
            nx_root[papp.protocol.topcategory] = nx.NXGroup()
            if papp.protocol.category.code not in nx_root[papp.protocol.topcategory]:
                nx_root[papp.protocol.topcategory][papp.protocol.category.code] = nx.NXGroup()
            _categories_collection = "/{}/{}".format(papp.protocol.topcategory,papp.protocol.category.code)
        try:
            provider = (
                ""
                if papp.citation.owner is None
                else papp.citation.owner.replace("/", "_").upper()
            )
        except BaseException:
            provider = "@"

        entry_id = "{}/entry_{}_{}".format(_categories_collection,provider, papp.uuid)
    except Exception as err:
        # print(err,papp.citation.owner)
        entry_id = "/entry_{}".format(papp.uuid)

    _categories_collection = "{}{}".format(_categories_collection,entry_id)
    if entry_id not in nx_root:
        nx_root[entry_id] = nx.tree.NXentry()
        nx_root[entry_id].attrs["name"] = entry_id
        #print("\n",_categories_collection, entry_id[1:])
       

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
            experiment_documentation.attrs["topcategory"] = papp.protocol.topcategory
            experiment_documentation.attrs["code"] = papp.protocol.category.code
            experiment_documentation.attrs["term"] = papp.protocol.category.term
            experiment_documentation.attrs["title"] = papp.protocol.category.title
            experiment_documentation.attrs["endpoint"] = papp.protocol.endpoint
            experiment_documentation.attrs["guideline"] = papp.protocol.guideline
            #definition is usually reference to the Nexus XML definition
            #ambit category codes and method serve similar role
            nx_root["{}/definition".format(entry_id)] = "/AMBIT_DATAMODEL/{}/{}/{}".format(papp.protocol.topcategory,papp.protocol.category.code,papp.protocol.guideline)
            if papp.parameters is not None:
                for tag in ["E.method", "ASSAY"]:
                    if tag in papp.parameters:
                        experiment_documentation.attrs["method"] = papp.parameters[tag]
                        nx_root["{}/definition".format(entry_id)] = "/AMBIT_DATAMODEL/{}/{}/{}".format(papp.protocol.topcategory,papp.protocol.category.code,papp.parameters[tag])

    except Exception as err:
        raise Exception(
            "ProtocolApplication: protocol parsing error " + str(err)
        ) from err

    nxmap = nx_root["{}/definition".format(entry_id)]
    nxmap.attrs["ProtocolApplication"] = entry_id
    nxmap.attrs["PROTOCOL_APPLICATION_UUID"] ="{}/entry_identifier_uuid".format(entry_id)
    nxmap.attrs["INVESTIGATION_UUID"] = "{}/collection_identifier".format(entry_id)
    nxmap.attrs["ASSAY_UUID"] = "{}/experiment_identifier".format(entry_id)
    nxmap.attrs["Protocol"] = "{}/experiment_documentation".format(entry_id)
    nxmap.attrs["Citation"] = "{}/reference".format(entry_id)
    nxmap.attrs["Substance"] = "{}/sample".format(entry_id)
    nxmap.attrs["Parameters"] = ["instrument", "environment", "parameters"]
    nxmap.attrs["EffectRecords"] = "datasets"

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

    # parameters
    if not ("{}/instrument".format(entry_id) in nx_root):
        nx_root["{}/instrument".format(entry_id)] = nx.NXinstrument()
    instrument = nx_root["{}/instrument".format(entry_id)]

    if not ("{}/parameters".format(entry_id) in nx_root):
        nx_root["{}/parameters".format(entry_id)] = nx.NXcollection()
    parameters = nx_root["{}/parameters".format(entry_id)]

    if not ("{}/environment".format(entry_id) in nx_root):
        nx_root["{}/environment".format(entry_id)] = nx.NXenvironment()
    environment = nx_root["{}/environment".format(entry_id)]

    if not (papp.parameters is None):
        for prm in papp.parameters:
            try:
                value = papp.parameters[prm]
                target = environment
                if "instrument" in prm.lower():
                    target = instrument
                if "technique" in prm.lower():
                    target = instrument
                if "wavelength" in prm.lower():
                    target = instrument
                elif "sample" in prm.lower():
                    target = sample
                elif "material" in prm.lower():
                    target = sample
                elif ("ASSAY" == prm.upper()) or ("E.METHOD" == prm.upper()):
                    target = nx_root[entry_id]["experiment_documentation"]
                    # continue
                elif "E.SOP_REFERENCE" == prm:
                    # target = instrument
                    target = nx_root[entry_id]["experiment_documentation"]
                elif "OPERATOR" == prm:
                    # target = instrument
                    target = nx_root[entry_id]["experiment_documentation"]
                elif prm.startswith("T."):
                    target = instrument

                if "EXPERIMENT_END_DATE" == prm:
                    nx_root[entry_id]["end_time"] = value
                elif "EXPERIMENT_START_DATE" == prm:
                    nx_root[entry_id]["start_time"] = value
                elif "__input_file" == prm:
                    nx_root[entry_id]["experiment_documentation"][prm] = value
                elif isinstance(value, str):
                    target[prm] = nx.NXfield(str(value))
                elif isinstance(value, Value):
                    # tbd ranges?
                    target[prm] = nx.NXfield(value.loValue, unit=value.unit)
                else:
                    target = parameters
            except Exception as err:
                raise Exception(
                    "ProtocolApplication: parameters parsing error " + str(err)
                ) from err

    if not (papp.owner is None):
        try:
            sample["uuid"] = papp.owner.substance.uuid
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
            "ProtocolApplication: effectrecords parsing error " + str(err)
        ) from err
    
    #nx_root["/group_byexperiment"] = nx.NXgroup()
    #print(nx_root[entry_id].attrs)
    #nx_root["/group_byexperiment{}".format(entry_id)] = nx.NXlink("{}/RAW_DATA".format(entry_id),abspath=True,soft=True)
    #nx_root["/group_byexperiment/{}".format("xyz")] = nx.NXlink(substance_id)
    #nx.NXlink(nx_root[entry_id])
    #nx_root[_categories_collection] = nx.NXlink(entry_id)
    return nx_root


@add_ambitmodel_method(Study)
def to_nexus(study: Study, nx_root: nx.NXroot = None):
    if nx_root is None:
        nx_root = nx.NXroot()
    for papp in study.study:
        papp.to_nexus(nx_root)

    return nx_root


@add_ambitmodel_method(SubstanceRecord)
def to_nexus(substance: SubstanceRecord, nx_root: nx.NXroot = None):
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
    """
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
            # name='' cas='' einecs='' inchikey='YVZATJAPAZIWIL-UHFFFAOYSA-M' inchi='InChI=1S/H2O.Zn/h1H2;/q;+1/p-1' formula='HOZn'
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
            nx_root[
                "{}/{}_{}".format(substance_id, ce.relation.replace("HAS_", ""), index)
            ] = component

    if substance.study is not None:
        for papp in substance.study:
            papp.to_nexus(nx_root)

    return nx_root


@add_ambitmodel_method(Substances)
def to_nexus(substances: Substances, nx_root: nx.NXroot = None):
    if nx_root is None:
        nx_root = nx.NXroot()
    for substance in substances.substance:
        substance.to_nexus(nx_root)
    return nx_root


@add_ambitmodel_method(Composition)
def to_nexus(composition: Composition, nx_root: nx.NXroot = None):
    if nx_root is None:
        nx_root = nx.NXroot()

    return nx_root


def format_name(meta_dict, key, default=""):
    name = meta_dict[key] if key in meta_dict else default
    return name if isinstance(name, str) else default if math.isnan(name) else name


def nexus_data(selected_columns, group, group_df, condcols, debug=False):
    try:
        meta_dict = dict(zip(selected_columns, group))
        # print(group_df.columns)
        tmp = group_df.dropna(axis=1, how="all")
        _interpretation = "scalar"
        ds_conc = []
        ds_conditions = []
        ds_response = None
        ds_aux = []
        ds_aux_tags = []
        ds_errors = None
        _attributes = {}
        # for c in ["CONCENTRATION","CONCENTRATION_loValue",
        #       "CONCENTRATION_SURFACE_loValue","CONCENTRATION_MASS_loValue"]:
        #    if c in tmp.columns:
        #        tmp = tmp.sort_values(by=[c])
        #        c_tag = c
        #        c_unittag = "{}_unit".format(c_tag.replace("_loValue",""))
        #        c_unit = meta_dict[c_unittag] if c_unittag in tmp.columns else ""
        #        ds_conc.append(nx.tree.NXfield(tmp[c].values,
        #               name=c_tag, units=c_unit))

        if "loValue" in tmp:
            unit = meta_dict["unit"] if "unit" in meta_dict else ""
            ds_response = nx.tree.NXfield(
                tmp["loValue"].values, name=meta_dict["endpoint"], units=unit
            )

        if "upValue" in tmp:
            unit = meta_dict["unit"] if "unit" in meta_dict else ""
            name = "{}_upValue".format(meta_dict["endpoint"])
            ds_aux.append(nx.tree.NXfield(tmp["upValue"].values, name=name, units=unit))
            ds_aux_tags.append(name)

        if "errorValue" in tmp:
            unit = meta_dict["unit"] if "unit" in meta_dict else ""
            ds_errors = nx.tree.NXfield(
                tmp["errorValue"].values,
                name="{}_errors".format(meta_dict["endpoint"]),
                units=unit,
            )

        for tag in ["loQualifier", "upQualifier", "textValue", "errQualifier"]:
            if tag in tmp:
                vals = tmp[tag].unique()
                if len(vals) == 1 and (vals[0] == "" or vals[0] == "="):
                    # skip if all qualifiers are empty or '=' tbd also for nans
                    continue
                if len(vals) == 1 and tag != "textValue":
                    # skip if all qualifiers are empty or '=' tbd also for nans
                    _attributes[tag] = vals
                    continue
                str_array = np.array(
                    [
                        (
                            "=".encode("ascii", errors="ignore")
                            if (x is None)
                            else x.encode("ascii", errors="ignore")
                        )
                        for x in tmp[tag].values
                    ]
                )
                # nxdata.attrs[tag] =str_array
                # print(str_array.dtype,str_array)
                if ds_response is None and tag == "textValue":
                    ds_response = nx.tree.NXfield(str_array, name=tag)
                else:
                    ds_aux.append(nx.tree.NXfield(str_array, name=tag))
                    ds_aux_tags.append(tag)

        primary_axis = None
        for tag in condcols:
            if tag in tmp.columns:
                if tag in [
                    "REPLICATE",
                    "BIOLOGICAL_REPLICATE",
                    "TECHNICAL_REPLICATE",
                    "EXPERIMENT",
                ]:
                    unit = None
                    try:
                        int_array = np.array(
                            [
                                (
                                    int(x)
                                    if isinstance(x, str) and x.isdigit()
                                    else (
                                        np.nan
                                        if (x is None)
                                        or math.isnan(x)
                                        or (not isinstance(x, numbers.Number))
                                        else int(x)
                                    )
                                )
                                for x in tmp[tag].values
                            ]
                        )
                        ds_conditions.append(nx.tree.NXfield(int_array, name=tag))
                    except BaseException:
                        print(tmp[tag].values)
                elif tag in ["MATERIAL", "TREATMENT"]:
                    vals = tmp[tag].unique()
                    if len(vals) == 1:
                        _attributes[tag] = vals
                
                else:
                    try:
                        str_array = np.array(
                            [
                                (
                                    ""
                                    if (x is None)
                                    else (
                                        "{} {}".format(x['loValue'], x['unit']).encode("ascii", errors="ignore")
                                        if isinstance(x, dict)
                                        else x.encode("ascii", errors="ignore")
                                    ) 
                                        
                                )
                                for x in tmp[tag].values
                            ]
                        )
                        # add as axis
                        ds_conditions.append(nx.tree.NXfield(str_array, name=tag))
                    except Exception as err_condition:
                        print(err_condition, tag, tmp[tag].values)
                        print("Exception traceback:\n%s", traceback.format_exc())
            else:
                tag_value = "{}_loValue".format(tag)
                tag_unit = "{}_unit".format(tag)
                if tag_value in tmp.columns:
                    unit = (
                        tmp[tag_unit].unique()[0] if tag_unit in tmp.columns else None
                    )
                    axis = nx.tree.NXfield(tmp[tag_value].values, name=tag, units=unit)
                    ds_conc.append(axis)
                    if (
                        tag == "CONCENTRATION"
                        or tag == "DOSE"
                        or tag == "AMOUNT_OF_MATERIAL"
                        or tag == "TREATMENT_CONDITION"
                    ):
                        primary_axis = tag
                        _interpretation = "spectrum"

        ds_conc.extend(ds_conditions)

        if (ds_response is not None) and (len(ds_response) > 0):
            _interpretation = "spectrum"  # means vector

        if len(ds_conc) > 0:
            nxdata = nx.tree.NXdata(ds_response, ds_conc, errors=ds_errors)
        else:
            nxdata = nx.tree.NXdata(ds_response, errors=ds_errors)
        nxdata.attrs["interpretation"] = _interpretation

        nxdata.name = meta_dict["endpoint"]
        _attributes["endpoint"] = meta_dict["endpoint"]
        if primary_axis is not None:
            nxdata.attrs["{}_indices".format(primary_axis)] = 0
        if "endpointtype" in meta_dict:
            _attributes["endpointtype"] = meta_dict["endpointtype"]

        # unit is per axis/signal
        # if "unit" in meta_dict and not (meta_dict["unit"] is None):
        #    nxdata.attrs["unit"] = meta_dict["unit"]

        if len(_attributes) > 0:
            nxdata["META"] = nx.tree.NXnote()
            for tag in _attributes:
                nxdata["META"].attrs[tag] = _attributes[tag]

        if len(ds_aux) > 0:
            for index, a in enumerate(ds_aux_tags):
                nxdata[a] = ds_aux[index]
            nxdata.attrs["auxiliary_signals"] = ds_aux_tags
        if debug:
            print(nxdata.tree)
        return nxdata, meta_dict
    except Exception as err:
        print("Exception traceback:\n%s", traceback.format_exc())
        raise Exception(
            "EffectRecords: grouping error {} {} {}".format(
                selected_columns, group, err
            )
        ) from err


def effectarray2data(effect: EffectArray):

    signal = nx.tree.NXfield(
        effect.signal.values, name=effect.endpoint, units=effect.signal.unit
    )
    axes = []
    for key in effect.axes:
        axes.append(
            nx.tree.NXfield(
                effect.axes[key].values, name=key, units=effect.axes[key].unit
            )
        )
    return nx.tree.NXdata(signal, axes)


def process_pa(pa: ProtocolApplication, entry=None, nx_root: nx.NXroot = None):

    if entry is None:
        entry = nx.tree.NXentry()
               
    _default = None
    try:
        _path = "/substance/{}".format(pa.owner.substance.uuid)
        #print(_path, nx_root[_path].name)
        substance_name = nx_root[_path].name
    except BaseException:
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
                if effect.endpointtype in ("RAW_DATA","RAW DATA","RAW","raw data"):
                    entry[_group_key] = nx.tree.NXgroup()
                else:
                    entry[_group_key] = nx.tree.NXprocess()
                    entry[_group_key]["NOTE"] = nx.tree.NXnote()
                    entry[_group_key]["NOTE"].attrs["description"] = effect.endpointtype
            #    entry[_group_key] = _endpointtype_groups[_group_key]

            entryid = "{}_{}".format(effect.endpoint, index)
            if entryid in entry[_group_key]:
                del entry[_group_key][entryid]
                print("replacing {}/{}".format(_group_key, entryid))

            nxdata = effectarray2data(effect)
            nxdata.attrs["interpretation"] = "spectrum"
            entry[_group_key][entryid] = nxdata
            if _default is None:
                entry.attrs["default"] = _group_key
            nxdata.title = "{} (by {}) {}".format(
                effect.endpoint, pa.citation.owner, substance_name
            )


    return entry


def papp_mash(df, dfcols, condcols, drop_parsed_cols=True):
    for _col in condcols:
        df_normalized = pd.json_normalize(df[_col])
        df_normalized = df_normalized.add_prefix(df[_col].name + "_")
        # print(_col,df.shape,df_normalized.shape)
        for col in df_normalized.columns:
            df.loc[:, col] = df_normalized[col]
        # if there are non dict values, leave the column,
        # otherwise drop it, we have the values parsed
        if drop_parsed_cols and df[_col].apply(lambda x: isinstance(x, dict)).all():
            print(_col)
            df.drop(columns=[_col], inplace=True)
        # print(_col,df.shape,df_normalized.shape,df_c.shape)
        # break
    df.dropna(axis=1, how="all", inplace=True)
    # df.dropna(axis=0,how="all",inplace=True)
    return df




def extract_doi(input_str):
    # Regular expression pattern to match DOI
    doi_pattern = r"(10\.\d{4,}(?:\.\d+)*\/\S+)"
    # Search for the DOI pattern in the input string
    match = re.search(doi_pattern, input_str)
    if match:
        return match.group(1)  # Return the matched DOI
    else:
        return None  # Return None if DOI not found
