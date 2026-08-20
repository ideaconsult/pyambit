import re
import uuid
from datetime import datetime
from typing import Dict

import nexusformat.nexus.tree as nx
import numpy as np
import numpy.typing as npt
from pydantic import Field as PydanticField

import pyambit.datamodel as mx

from pyambit.nexus_models.appdefs.nx_raman import NXRaman
from pyambit.nexus_models.base.nx_beam import NXBeam
from pyambit.nexus_models.base.nx_detector import NXDetector
from pyambit.nexus_models.base.nx_fabrication import NXFabrication
from pyambit.nexus_models.base.nx_grating import NXGrating
from pyambit.nexus_models.base.nx_instrument import NXInstrument
from pyambit.nexus_models.base.nx_monochromator import NXMonochromator
from pyambit.nexus_models.flatten import flatten_nx_model
from pyambit.nexus_writer import to_nexus  # noqa: F401


class NXRamanProtocolApplication(mx.ProtocolApplication):
    """A ProtocolApplication carrying a typed NXraman model (see
    pyambit.nexus_models.appdefs.nx_raman.NXRaman) alongside the inherited
    free-form `parameters` dict.

    `nxraman` is the single source of truth for NXraman-schema values; use
    `sync_parameters()` (or `configure_papp`, which calls it) to flatten it
    into `parameters` via `flatten_nx_model` before writing to NeXus -
    `parameters` is not kept in sync automatically on every mutation of
    `nxraman`, since pydantic has no hook for "a nested model's field
    changed."
    """

    nxraman: NXRaman = PydanticField(default_factory=NXRaman)

    def sync_parameters(self) -> None:
        """Flatten `self.nxraman` into `self.parameters`, preserving any
        existing non-NXraman parameter entries (e.g. the generic
        `/parameters/{key}` fallback bucket) already present.

        Uses plain attribute assignment, not the constructor, so
        ProtocolApplication's `clean_parameters` validator (which flattens
        "/"-containing keys to "_", see datamodel.py) never runs on these
        path-shaped keys.
        """
        flattened, _ = flatten_nx_model(self.nxraman)
        merged = dict(self.parameters or {})
        merged.update(flattened)
        self.parameters = merged


def spe2effect(
    x: npt.NDArray,
    y: npt.NDArray,
    unit="cm-1",
    endpointtype="RAW_DATA",
    meta: Dict = None,
    nx_name=None,
):
    try:
        signal = meta["@signal"]
    except KeyError:
        signal = "y"
    try:
        axes = meta["@axes"]
    except KeyError:
        axes = ["y"]
    data_dict: Dict[str, mx.ValueArray] = {axes[0]: mx.ValueArray(values=x, unit=unit)}
    return mx.EffectArray(
        endpoint=signal,
        endpointtype=endpointtype,
        signal=mx.ValueArray(values=y, unit="Arbitr.Units"),
        axes=data_dict,
        nx_name=nx_name,
    )


# Backward-compat input-key -> NXRaman-field routing, replacing the original
# if/elif chain. Preserves every meta key string spectrastream (and any other
# existing caller) is documented to send verbatim, case-insensitively
# matched - including "pin hole size" (a legal spectrastream key that has no
# home in the generated NXRaman model today, since NXraman's own appdef XML
# never references NXoptical_lens/numerical_aperture; it falls through to the
# generic "/parameters/{key}" bucket like any other unrecognized key, exactly
# as it did before this key existed in any lookup table at all).
#
# Each entry is (lowercased key, setter) where setter(nxraman, value) mutates
# the NXRaman instance in place and returns True if it did, False if the
# value couldn't be routed to its typed field (e.g. a free-text value with no
# leading number, like "fibre", can't become NXGrating.period) - the caller
# treats False the same as an unrecognized key, falling back to the generic
# "/parameters/{key}" bucket so no caller-supplied value is ever silently
# dropped. Numeric-looking string values are coerced to float/Value since
# spectrastream/meta dicts may pass either type (e.g. wavelength arrives as
# `str(laser_wl)`, grating arrives as "600 g/mm").
def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_NUMBER_WITH_UNIT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(\S.*)?$")


def _coerce_value(value) -> "mx.Value | float | None":
    """Parse a bare number ("600", 532) or a "number unit" string
    ("600 g/mm", "100 um") into a float or a Value carrying the trailing text
    as its unit. Returns None for anything with no leading number at all
    (e.g. "fibre") - the field this feeds (NXGrating.period, NXDetector.
    count_time) is typed Optional[Union[float, Value]], matching NXDL's own
    NX_NUMBER declaration for these fields exactly; it is not widened to
    accept arbitrary strings, so a caller must treat None here as "couldn't
    route to the typed field" and fall back to the generic parameters bucket
    (see _BACKWARD_COMPAT_KEYS's callers) rather than silently dropping data.
    """
    as_float = _coerce_float(value)
    if as_float is not None:
        return as_float
    if not isinstance(value, str):
        return None
    match = _NUMBER_WITH_UNIT_RE.match(value)
    if not match:
        return None
    number_text, unit_text = match.groups()
    return mx.Value(loValue=float(number_text), unit=(unit_text or None))


def _set_grating_period(nxraman: NXRaman, value) -> bool:
    coerced = _coerce_value(value)
    if coerced is None:
        return False
    instrument = nxraman.instrument.setdefault("instrument", NXInstrument())
    monochromator = instrument.monochromator.setdefault("monochromator", NXMonochromator())
    grating = monochromator.grating.setdefault("grating", NXGrating())
    grating.period = coerced
    return True


def _set_count_time(nxraman: NXRaman, value) -> bool:
    coerced = _coerce_value(value)
    if coerced is None:
        return False
    instrument = nxraman.instrument.setdefault("instrument", NXInstrument())
    detector = instrument.detector_type.setdefault("detector", NXDetector())
    detector.count_time = coerced
    return True


_BACKWARD_COMPAT_KEYS = {
    "grating": _set_grating_period,
    "acquisition_time": _set_count_time,
    "integration times(ms)": _set_count_time,
    "integration time": _set_count_time,
    "integ_time": _set_count_time,
}


def configure_papp(
    papp: mx.ProtocolApplication = None,
    instrument=("vendor", "model"),
    wavelength=None,
    provider="ABCD",
    sample="PST",
    sample_provider="TEST",
    investigation="My investigation",
    citation: mx.Citation = None,
    prefix="TEST",
    meta: Dict = None,
    group_investigation: bool = True,
):
    if papp is None:
        papp = NXRamanProtocolApplication(
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
    # group_investigation=False leaves papp.investigation_uuid unset (None)
    # -- nexus_writer.to_nexus only creates the shared investigation/<uuid>
    # NeXus group when investigation_uuid is not None, so this is how a
    # caller opts out of that grouping entirely (e.g. RRUFF: one .nxs file
    # per sample, with no reason to link samples into a shared
    # investigation node). investigation= keeps feeding Citation.title and
    # assay_uuid regardless -- those are independent of the shared group.
    if group_investigation:
        papp.investigation_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, investigation))
    papp.assay_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_OID, "{} {}".format(investigation, provider))
    )

    nxraman = getattr(papp, "nxraman", None)
    if nxraman is None:
        nxraman = NXRaman()
    nxraman.definition = "NXraman"
    nxraman.experiment_type = "Raman spectroscopy"
    nxraman_instrument = nxraman.instrument.setdefault("instrument", NXInstrument())
    # NXraman's own NXDL doesn't declare a unit category on NXbeam.wavelength
    # (unlike e.g. count_time), so flatten_nx_model can't infer "nm" on its
    # own without inventing unit logic pyambit is meant to stay out of. The
    # caller (spe2ambit/configure_papp) knows this is a laser wavelength in
    # nanometers, so it's supplied explicitly as a Value here - flatten_nx_model
    # passes an already-constructed Value straight through.
    wavelength_float = _coerce_float(wavelength)
    nxraman_instrument.beam_incident = NXBeam(
        wavelength=mx.Value(loValue=wavelength_float, unit="nm")
        if wavelength_float is not None
        else None
    )
    nxraman_instrument.device_information = NXFabrication(
        vendor=instrument[0], model=instrument[1]
    )

    extra_parameters: Dict[str, object] = {
        "/experiment_documentation/E.method": "Raman spectroscopy",
    }
    for key in list(meta.keys()):
        key_l = key.lower()
        setter = _BACKWARD_COMPAT_KEYS.get(key_l)
        # A setter returning False means the value couldn't be routed to its
        # typed NXDL field (e.g. "fibre" has no leading number, so it can't
        # become NXGrating.period without widening that field beyond NXDL's
        # own NX_NUMBER declaration) - fall back to the generic bucket rather
        # than silently dropping data a real caller supplied.
        if setter is not None and setter(nxraman, meta[key]):
            continue
        if not key.startswith("@"):
            extra_parameters["/parameters/{}".format(key)] = meta[key]

    if hasattr(papp, "nxraman"):
        papp.nxraman = nxraman
        papp.parameters = extra_parameters
        papp.sync_parameters()
    else:
        # Caller passed a plain (non-NXRaman) ProtocolApplication - fall back
        # to writing the flattened parameters directly, matching this
        # function's pre-existing contract for non-NXRaman callers.
        flattened, _ = flatten_nx_model(nxraman)
        merged = dict(extra_parameters)
        merged.update(flattened)
        papp.parameters = merged

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
    unit="cm¯¹",
    papp=None,
    group_investigation: bool = True,
):

    if papp is None:
        papp = NXRamanProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            ),
            effects=[],
        )
        # nx_name feeds nexus_writer.to_nexus's entry_id verbatim (unlike
        # citation.owner, which that same function sanitizes with
        # .replace("/", "_") before using it in a path). A provider that is
        # a DOI (e.g. "10.17605/OSF.IO/7CQV4") would otherwise make
        # NXgroup.__setitem__ treat the embedded "/" as a path separator and
        # raise NeXusError("Invalid path") when no such intermediate group
        # exists. Sanitize only the NeXus-facing name; provider itself
        # (citation, parameters, sample_provider linkage) stays untouched.
        papp.nx_name = provider.replace("/", "_") if provider else provider
        configure_papp(
            papp,
            instrument=instrument,
            wavelength=wavelength,
            provider=provider,
            sample=sample,
            sample_provider=sample_provider,
            investigation=investigation,
            citation=None,
            group_investigation=group_investigation,
            prefix=prefix,
            meta=meta,
        )
    papp.effects.append(spe2effect(x, y, unit, endpointtype, meta, nx_name=sample))
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
