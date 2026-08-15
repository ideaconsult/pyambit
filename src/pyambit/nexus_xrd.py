"""X-ray powder diffraction -> AMBIT data model -> NeXus (NXxrd).

Mirrors `nexus_spectra.py` (the Raman path) for XRD: `xrd2effect` builds the
EffectArray, `configure_papp_xrd` puts the instrument metadata on the paths the
**NXxrd** application definition specifies, and `xrd2ambit` ties the two
together.

NXxrd extends NXmonopd and expects, per entry:

    definition                          = "NXxrd"
    NXinstrument/NXbeam/incident_energy  (or incident_wavelength)
    NXinstrument/NXdetector
    NXdata (raw_data): polar_angle [deg] + data

so the diffraction angle is written as **polar_angle** rather than a
free-form "2theta", which is what makes the result readable by NXxrd-aware
tools. Anything the definition does not name falls through to
`/parameters/{key}`, exactly as `configure_papp` does for Raman.

Vendor headers (Bruker RAW/UXD `_KEY = value` blocks) are recognised by their
native key names, so a caller can pass the parsed header through untouched.
"""

import uuid
from datetime import datetime
from typing import Dict

import numpy.typing as npt

import pyambit.datamodel as mx

from pyambit.nexus_writer import to_nexus  # noqa: F401

# CuKa1 in Angstrom; only used to convert a wavelength to incident_energy when
# the caller supplies no energy of its own.
_HC_KEV_ANGSTROM = 12.398419843320026


def wavelength_to_energy_kev(wavelength_angstrom: float) -> float:
    """E [keV] = hc / lambda, with hc = 12.3984 keV*A."""
    return _HC_KEV_ANGSTROM / float(wavelength_angstrom)


# Bruker UXD / RAW header keys -> NXxrd (or NXinstrument) paths. Keys are
# matched lowercase and without the leading underscore.
_HEADER_MAP = {
    "anode": "instrument/source/target_material",
    "kv": "instrument/source/voltage",
    "ma": "instrument/source/current",
    "goniometer_radius": "instrument/detector/distance",
    "stepsize": "/parameters/scan/step_size",
    "steptime": "/parameters/scan/step_time",
    "stepmode": "/parameters/scan/step_mode",
    "drive": "/parameters/scan/drive",
    "start": "/parameters/scan/start",
    "theta": "/parameters/scan/theta_start",
    "2theta": "/parameters/scan/two_theta_start",
    "detector": "instrument/detector/type",
    "hv": "instrument/detector/voltage",
    "gain": "instrument/detector/gain",
    "soller_slits": "instrument/collimator/soller_angle",
    "fixed_divslit": "instrument/collimator/divergence_slit",
    "fixed_detslit": "instrument/detector/slit",
    "fixed_antislit": "instrument/collimator/anti_scatter_slit",
    "monochromator": "instrument/monochromator/type",
    "datemeasured": "/parameters/start_time",
    "site": "/parameters/site",
    "user": "/parameters/user",
    "sample": "/parameters/sample_id",
}


def xrd2effect(
    two_theta: npt.NDArray,
    intensity: npt.NDArray,
    unit="deg",
    intensity_unit="counts",
    endpointtype="RAW_DATA",
    meta: Dict = None,
    nx_name=None,
):
    """One diffractogram as an EffectArray.

    The angular axis is named **polar_angle**, the field NXxrd/NXmonopd define
    for the diffraction angle; `meta["@axes"]`/`meta["@signal"]` may override
    the names when a caller needs the workbook's own wording.
    """
    meta = meta or {}
    signal = meta.get("@signal", "data")
    axes = meta.get("@axes", ["polar_angle"])
    data_dict: Dict[str, mx.ValueArray] = {
        axes[0]: mx.ValueArray(values=two_theta, unit=unit)
    }
    return mx.EffectArray(
        endpoint=signal,
        endpointtype=endpointtype,
        signal=mx.ValueArray(values=intensity, unit=intensity_unit),
        axes=data_dict,
        nx_name=nx_name,
    )


def configure_papp_xrd(
    papp: mx.ProtocolApplication = None,
    instrument=("vendor", "model"),
    wavelength=None,
    anode=None,
    provider="ABCD",
    sample="PST",
    sample_provider="TEST",
    investigation="My investigation",
    citation: mx.Citation = None,
    prefix="TEST",
    meta: Dict = None,
):
    """Populate a ProtocolApplication with NXxrd-conformant parameters.

    `meta` may carry a raw vendor header: keys named as in a Bruker UXD file
    (`_WL1`, `_ANODE`, `_KV`, `_STEPSIZE`, ...) are routed to their NXxrd paths,
    and anything unrecognised is preserved under `/parameters/{key}`.
    """
    if papp is None:
        papp = mx.ProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="CRYSTALLINE_PHASE_SECTION"),
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
        "/experiment_documentation/E.method": "X-ray diffraction",
        "/experiment_type": "X-ray diffraction",
        "instrument/device_information/vendor": instrument[0],
        "instrument/device_information/model": instrument[1],
        "/definition": "NXxrd",
    }
    if wavelength is not None:
        papp.parameters["instrument/beam/incident_wavelength"] = mx.Value(
            loValue=float(wavelength), unit="angstrom"
        )
        papp.parameters["instrument/beam/incident_energy"] = mx.Value(
            loValue=wavelength_to_energy_kev(wavelength), unit="keV"
        )
    if anode is not None:
        papp.parameters["instrument/source/target_material"] = anode

    for key in list((meta or {}).keys()):
        if key.startswith("@"):
            continue
        key_l = key.lower().lstrip("_")
        target = _HEADER_MAP.get(key_l)
        if target is not None:
            # Do not let a vendor header overwrite an explicit argument.
            papp.parameters.setdefault(target, meta[key])
        else:
            papp.parameters["/parameters/{}".format(key.lstrip('_'))] = meta[key]

    papp.uuid = "{}-{}".format(
        prefix,
        uuid.uuid5(
            uuid.NAMESPACE_OID,
            "XRD {} {} {} {} {} {}".format(
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
    return papp


def xrd2ambit(
    two_theta: npt.NDArray,
    intensity: npt.NDArray,
    meta: Dict,
    instrument=None,
    wavelength=None,
    anode=None,
    provider="FNMT",
    investigation="XRD study",
    sample="PST",
    sample_provider="LAB",
    prefix="XRD",
    endpointtype="RAW_DATA",
    unit="deg",
    intensity_unit="counts",
    papp=None,
):
    """A diffractogram as a ready-to-write ProtocolApplication."""
    if papp is None:
        papp = mx.ProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="CRYSTALLINE_PHASE_SECTION"),
            ),
            effects=[],
        )
        papp.nx_name = provider
        configure_papp_xrd(
            papp,
            instrument=instrument,
            wavelength=wavelength,
            anode=anode,
            provider=provider,
            sample=sample,
            sample_provider=sample_provider,
            investigation=investigation,
            citation=None,
            prefix=prefix,
            meta=meta,
        )
    papp.effects.append(
        xrd2effect(
            two_theta,
            intensity,
            unit,
            intensity_unit,
            endpointtype,
            meta,
            nx_name=sample,
        )
    )
    return papp


def peaks2effects(
    peaks,
    endpointtype="PEAKS",
    nx_name=None,
):
    """Indexed reflections as EffectRecords.

    `peaks` is an iterable of dicts with any of: `two_theta` (deg), `hkl`
    (Miller indices as a string, e.g. "(0 2 0)"), `net_area`, `d_spacing`,
    `reference`. Each becomes one EffectRecord whose conditions carry the
    indexing, so a peak table travels with its diffractogram instead of being
    flattened into free text.
    """
    effects = []
    for peak in peaks:
        conditions = {}
        if peak.get("hkl"):
            conditions["hkl"] = str(peak["hkl"])
        if peak.get("two_theta") is not None:
            conditions["polar_angle"] = mx.Value(
                loValue=float(peak["two_theta"]), unit="deg"
            )
        if peak.get("reference"):
            conditions["reference"] = str(peak["reference"])

        value = peak.get("net_area")
        effects.append(
            mx.EffectRecord(
                endpoint=peak.get("endpoint", "net area"),
                endpointtype=endpointtype,
                result=mx.EffectResult(
                    loValue=None if value is None else float(value),
                    unit=peak.get("unit"),
                ),
                conditions=conditions or None,
                nx_name=nx_name,
            )
        )
    return effects
