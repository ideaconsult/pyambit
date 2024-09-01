import uuid
from datetime import datetime
from typing import Dict, List, Union

import nexusformat.nexus.tree as nx
import numpy as np
import numpy.typing as npt

import pyambit.datamodel as mx
from pyambit.nexus_writer import to_nexus


def spe2effect(
    x: npt.NDArray,
    y: npt.NDArray,
    unit="cm-1",
    endpointtype="RAW_DATA",
    meta: Dict = None,
):
    data_dict: Dict[str, mx.ValueArray] = {"x": mx.ValueArray(values=x, unit=unit)}
    return mx.EffectArray(
        endpoint="y",
        endpointtype=endpointtype,
        signal=mx.ValueArray(values=y, unit="count"),
        axes=data_dict,
    )


def configure_papp(
    papp: mx.ProtocolApplication = None,
    instrument=("vendor","model"),
    wavelength=None,
    provider="FNMT",
    sample="PST",
    sample_provider="CHARISMA",
    investigation="Round Robin 1",
    citation: mx.Citation = None,
    prefix="CRMA",
    meta=None,
):
    if papp is None:
        papp = mx.ProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            ),
            effects=[],
        )
    if citation is None:
        papp.citation = mx.Citation(
            owner=provider, title=investigation, year=datetime.now().year
        )
    else:
        papp.citation = citation
    papp.investigation_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, investigation))
    papp.assay_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_OID, "{} {}".format(investigation, provider))
    )
    papp.parameters = {
        "experiment_documentation/E.method": "Raman spectroscopy",
        "experiment_type" : "Raman spectroscopy" ,
        "instrument/beam_incident/wavelength":  mx.Value(loValue=wavelength,unit="nm"),
        "instrument/device_information/vendor": instrument[0],
        "instrument/device_information/model": instrument[1],
        "definition":"NXRaman"
        
    }

    papp.uuid = "{}-{}".format(
        prefix,
        uuid.uuid5(
            uuid.NAMESPACE_OID,
            "RAMAN {} {} {} {} {} {}".format(
                "" if investigation is None else investigation,
                "" if sample_provider is None else sample_provider,
                "" if sample is None else sample,
                "" if provider is None else provider,
                "" if instrument is None else instrument,
                "" if wavelength is None else wavelength,
            ),
        ),
    )
    company = mx.Company(name=sample_provider)
    substance = mx.Sample(
        uuid="{}-{}".format(prefix, uuid.uuid5(uuid.NAMESPACE_OID, sample))
    )
    papp.owner = mx.SampleLink(substance=substance, company=company)


def spe2ambit(
    x: npt.NDArray,
    y: npt.NDArray,
    meta: Dict,
    instrument=None,
    wavelength=None,
    provider="FNMT",
    investigation="Round Robin 1",
    sample="PST",
    sample_provider="CHARISMA",
    prefix="CRMA",
    endpointtype="RAW_DATA",
    unit="cm-1",
    papp=None,
):

    if papp is None:
        papp = mx.ProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            ),
            effects=[],
        )
        configure_papp(
            papp,
            instrument=instrument,
            wavelength=wavelength,
            provider=provider,
            sample=sample,
            sample_provider=sample_provider,
            investigation=investigation,
            citation=None,
            prefix=prefix,
            meta=meta,
        )
    papp.effects.append(spe2effect(x, y, unit, endpointtype, meta))
    return papp


def peaks2nxdata(df):

    nxdata = nx.NXdata()
    axes = ["height", "center", "sigma", "beta", "fwhm", "height"]
    for a in axes:
        nxdata[a] = nx.NXfield(df[a].values, name=a)
        a_err = f"{a}_errors"
        nxdata[a_err] = nx.NXfield(df[f"{a}_stderr"].values, name=a_err)
    str_array = np.array(
        [
            (
                "=".encode("ascii", errors="ignore")
                if (x is None)
                else x.encode("ascii", errors="ignore")
            )
            for x in df.index.values
        ]
    )
    nxdata["group_peak"] = nx.NXfield(str_array, name="group_peak")
    # nxdata.signal = 'amplitude'
    nxdata.attrs["signal"] = "height"
    nxdata.attrs["auxiliary_signals"] = ["amplitude", "beta", "sigma", "fwhm"]
    nxdata.attrs["axes"] = ["center"]
    nxdata.attrs["interpretation"] = "spectrum"
    nxdata.attrs["{}_indices".format("center")] = 0
    return nxdata
