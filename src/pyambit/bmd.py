"""Benchmark concentration (BMD) with its uncertainty, from AMBIT records.

A material has a concentration-effect property; the experiments in a
:class:`~pyambit.datamodel.SubstanceRecord` are noisy, partial, laboratory-distorted
measurements of it. The quantity those measurements exist to determine already has a
name and a regulatory definition -- the benchmark dose -- so that is what this module
estimates::

    BMD(r)  -- the concentration producing benchmark response r,
               with its uncertainty distribution

The object built is the **CDF of that distribution**, sampled on a fixed quantile
grid, so ``Q(0.05, r)`` is BMDL, ``Q(0.5, r)`` the point estimate and ``Q(0.95, r)``
BMDU: one object rather than three separate procedures. Flattened level-major it is
also a fixed-length vector in log10 concentration, so Euclidean distance between two
materials is an RMS displacement in decades.

Scale
-----
No rescaling of the readout. Benchmark responses are given in the assay's own units
and interpreted relative to the **control** -- the standard definition -- so a
viability assay with a control at 100 % and ``benchmark_responses=(10, 20, 50)`` asks
for the concentrations producing 10, 20 and 50 units of decrease. Normalising each
experiment to its own observed range would be affine-invariant across laboratories
but destroys efficacy, and the observed range is itself a noise-inflated order
statistic. Anchor to controls, not to the data range.

Grouping
--------
The key naming the property comes from the record, and which fields it comes from
matters more than it looks.

* **Not** ``Protocol.endpoint``: in practice it is not curated. The protocol is
  identified by ``topcategory``, ``category.code`` and the assay method parameter.
* **Parameters, not conditions -- but only method and cell type out of them.** The
  assay method and the cell line live in ``ProtocolApplication.parameters``, read
  through :mod:`pyambit.study_config` the same way as the dose axis and the control
  annotation, so the key works against arbitrary AMBIT records rather than one
  project's field names. Everything else in ``parameters`` -- medium formulation
  text, dispersion protocol wording, operator, preparation date, input filename,
  well-plate note -- is deliberately left out. It was folded in verbatim in an
  earlier version, and that made consolidation nearly impossible: two laboratories
  measuring the identical property essentially never share the same operator or
  date, so the key differed on that alone and ``consolidate_providers`` never saw
  both, even for materials with unambiguous multi-laboratory data under the coarser
  identity ``curate_passing.py`` / ``curate_failing.py`` (notebooks-ambit) already
  use -- material, category, method, cell type. ``EffectRecord.conditions`` carries
  what varies *within* the run: concentration, exposure time, replicate count,
  control annotation.
* **Units are converted where a conversion exists, and separate the key where it is
  not.** Concentrations are converted to mg/L within the mass-per-volume dimension
  and to umol/L within the molar one, via :mod:`pyambit.units`. The two dimensions
  are never interconverted: that needs a molar mass, which a nanomaterial does not
  have. So ug/mL and mg/L consolidate, values and all, while ug/mL and uM stay in
  different keys. A unit no path recognises keeps its own key -- the safe failure.
* **Exposure time is in the key.** A benchmark concentration at 24 h and one at 48 h
  are two properties, not two measurements of one.

Which condition names carry the dose, the exposure time, the assay method and the
control annotation is read from :mod:`pyambit.study_config` per endpoint category,
not hardcoded, so the module works against arbitrary AMBIT records rather than one
project's conventions.

Laboratories are what vary within a key, and they are what gets consolidated. The
provider is ``citation.owner`` -- the laboratory -- before ``owner.company.name``,
which is the *project*: getting that order wrong collapses every laboratory in a
project into one provider and silently turns consolidation into a no-op.

Writing results back onto the model is deliberately not implemented here. The natural
mapping, when it is wanted, is an :class:`~pyambit.datamodel.EffectRecord` per
benchmark response whose :class:`~pyambit.datamodel.EffectResult` carries the BMD as
``loValue`` with ``loQualifier`` / ``upQualifier`` holding the censoring, which would
then round-trip through ``nexus_writer`` and ``solr_writer`` unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from measurement.measures import Time

from pyambit import study_config as sc
from pyambit.datamodel import EffectArray
from pyambit.units import Concentration, ConcentrationMolar

__all__ = [
    "BmdProfile",
    "BmdSpec",
    "DoseSeries",
    "PropertyKey",
    "bmd_cdf",
    "bmd_recovery",
    "bmd_vector",
    "consolidate_providers",
    "series_from_protocol_application",
    "series_from_substance",
]

# Fallbacks used when study_config has nothing for a category.
DOSE_KEYS = ("CONCENTRATION", "DOSE", "CONC")
TIME_KEYS = ("E.EXPOSURE_TIME", "EXPOSURE_TIME", "TIME", "DURATION")
METHOD_PARAMETERS = ("E.method", "E.METHOD", "E.Method", "method", "E.assay", "ASSAY")
CELL_TYPE_PARAMETERS = ("E.cell_type", "E.CELL_TYPE", "E.Cell_Type", "cell_type", "CELL_TYPE")
# Conditions holding *how many* wells are behind a pre-aggregated row.
REPLICATE_COUNT_KEYS = ("NUMBER_OF_REPLICATES", "REPLICATES", "N_REPLICATES")

# Conditions that index a well rather than define a property.
#
# A per-well replicate index is a real array dimension, and rightly so: the array is
# the faithful record of what was measured, and NeXus needs that dimension to write
# each well's value. This module does not change that. What it does is *read* the
# array along the dose axis for the purpose of estimating a BMD, and for that purpose
# wells at one concentration are repeated measurements of a single point, not
# separate properties -- so the replicate dimension is gathered into repeated
# observations rather than iterated over as if each well were its own dose series.
#
# Nothing here is written back: the EffectArray, its axes and its signal are left
# exactly as the model holds them (test_reading_a_record_does_not_mutate_it).
REPLICATE_INDEX_KEYS = (
    "REPLICATE",
    "REPLICATE_ID",
    "REP",
    "WELL",
    "WELL_ID",
    "PLATE_WELL",
    "EXPERIMENT",
    "BIOLOGICAL_REPLICATE",
    "TECHNICAL_REPLICATE",
)

CONTROL_KEYS = ("material", "MATERIAL", "treatment_condition", "treatment")

MASS_PER_VOLUME = "mg/L"
MOLAR_PER_VOLUME = "umol/L"

_MASS_FALLBACK = {
    "g__l": 1e3,
    "mg__l": 1.0,
    "ug__l": 1e-3,
    "ng__l": 1e-6,
    "g__ml": 1e6,
    "mg__ml": 1e3,
    "ug__ml": 1.0,
    "ng__ml": 1e-3,
    "kg__l": 1e6,
    "ppm": None,
}
_MOLAR_FALLBACK = {
    "mol__l": 1e6,
    "mmol__l": 1e3,
    "umol__l": 1.0,
    "nmol__l": 1e-3,
    "pmol__l": 1e-6,
    "m": 1e6,
    "mm": 1e3,
    "um": 1.0,
    "nm": 1e-3,
    "pm": 1e-6,
    "mol__ml": 1e9,
    "mmol__ml": 1e6,
    "umol__ml": 1e3,
}
# Factors above are to the canonical unit of each dimension. The primary conversion
# path is pyambit.units; these tables are the fallback for units those classes do not
# carry -- nM and pM among them, since Molar defines only mol, mmol and umol.
#
# "ppm" maps to None deliberately: it equals mg/L only for dilute aqueous media, and
# guessing that would silently merge records that are not comparable.

_TIME_ALIASES = {
    "h": "hr",
    "hour": "hr",
    "hours": "hr",
    "hrs": "hr",
    "minute": "min",
    "minutes": "min",
    "mins": "min",
    "second": "sec",
    "seconds": "sec",
    "s": "sec",
    "days": "day",
    "d": "day",
    "week": "wk",
    "weeks": "wk",
}


# ----------------------------------------------------------------------
# small readers over the pyambit model
# ----------------------------------------------------------------------
def _scalar(value) -> float | None:
    """A number out of a pyambit ``Value``, a dict form of one, or a plain number."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        lo = value.get("loValue")
        return None if lo is None else float(lo)
    lo = getattr(value, "loValue", None)
    return None if lo is None else float(lo)


def _unit(value) -> str | None:
    if isinstance(value, dict):
        return value.get("unit")
    return getattr(value, "unit", None)


def _first_key(mapping, candidates) -> str | None:
    for key in candidates:
        if key in mapping:
            return key
    lowered = {str(k).lower(): k for k in mapping}
    for key in candidates:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _as_text(value) -> str | None:
    """A parameter rendered for the key, keeping its unit if it has one."""
    if value is None:
        return None
    number, unit = _scalar(value), _unit(value)
    if number is not None:
        return f"{number:g}{unit}" if unit else f"{number:g}"
    text = getattr(value, "textValue", None) or value
    return str(text) if not isinstance(text, dict) else str(sorted(text.items()))


def _unit_token(unit: str | None) -> str | None:
    """Normalise a recorded unit into a ``measurement`` keyword.

    ``ug/mL``, ``µg/ml`` and ``UG / ML`` all become ``ug__ml``.
    """
    if unit is None:
        return None
    text = str(unit).strip().replace("µ", "u").replace("μ", "u")
    text = text.replace(" ", "").lower()
    return text.replace("/", "__") if text else None


def _concentration_in_canonical(values, unit: str | None):
    """Convert concentrations to mg/L or umol/L; return ``(values, unit_label)``.

    Mass-per-volume and molar-per-volume are separate dimensions and are **not**
    interconverted: that needs a molar mass, which a nanomaterial does not have. So
    ug/mL and mg/L consolidate -- same dimension, exact conversion -- while ug/mL and
    uM stay apart, in different keys.

    A unit neither path recognises is left untouched and keeps its own key, which is
    the safe failure: an unconvertible record is separated rather than silently
    merged on a guess.
    """
    token = _unit_token(unit)
    if token is None:
        return values, None

    for cls, canonical, label, fallback in (
        (Concentration, "mg__l", MASS_PER_VOLUME, _MASS_FALLBACK),
        (ConcentrationMolar, "umol__l", MOLAR_PER_VOLUME, _MOLAR_FALLBACK),
    ):
        try:  # the measurement package, where it knows the unit
            factor = float(getattr(cls(**{token: 1.0}), canonical))
        except Exception:
            factor = fallback.get(token)
        if factor:
            return values * factor, label
    return values, str(unit).strip()


def _hours(value, unit: str | None) -> float | None:
    """Exposure time in hours.

    An unrecognised time unit returns ``None`` rather than a guess: a duration that
    cannot be placed on a common axis must not be silently pooled with one that can.
    """
    number = _scalar(value)
    if number is None:
        return None
    token = _unit_token(unit)
    if token is None:
        return float(number)
    token = _TIME_ALIASES.get(token, token)
    try:
        return float(Time(**{token: float(number)}).hr)
    except Exception:
        return None


def classify_control(value) -> str | None:
    """Classify a control annotation, or ``None`` for an ordinary material name.

    The control designation field is overloaded: it carries both control roles
    (``control_negative``, ``"Negative control"``, ``solvent_control``, ``"Blank"``)
    and ordinary treatment material names (TiO2, PLGA-PEO, ...). Only the former are
    controls, and ``"positively charged TiO2"`` must not read as a positive control,
    which is why the polarity tests also require a ``control`` token.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if "positive" in s and ("control" in s or s.startswith("control_")):
        return "positive"
    if "negative" in s and ("control" in s or s.startswith("control_")):
        return "negative"
    if "interference" in s:
        return "interference"
    if "solvent" in s or s == "vehicle":
        return "solvent"
    if s == "blank":
        return "blank"
    if s == "control":
        return "control"
    return None


# ----------------------------------------------------------------------
# the data the estimate is built from
# ----------------------------------------------------------------------
@dataclass
class DoseSeries:
    """One laboratory's concentration-response measurements of one property.

    Straight out of a :class:`~pyambit.datamodel.ProtocolApplication`: nothing is
    averaged, rescaled or reordered, so the replicate structure the bootstrap needs
    is still present. Concentrations are converted to the canonical unit of their
    dimension (mg/L or umol/L); the response is left in the units recorded.
    """

    concentration: np.ndarray  # canonical unit of its dimension
    response: np.ndarray  # the readout, original scale
    error: np.ndarray | None = None  # per-observation error, if the record has it
    error_qualifier: str | None = None  # "SD" / "SE" / ...
    replicates: np.ndarray | None = None  # wells behind each row, if recorded
    concentration_unit: str | None = None
    response_unit: str | None = None
    time: float | None = None  # hours
    provider: str | None = None
    control_response: float | None = None  # from an annotated control, if present
    control_route: str | None = None  # how that control was identified
    key: "PropertyKey | None" = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.concentration = np.asarray(self.concentration, dtype=float).ravel()
        self.response = np.asarray(self.response, dtype=float).ravel()
        if self.concentration.shape != self.response.shape:
            raise ValueError("concentration and response must have equal length")
        if self.error is not None:
            self.error = np.asarray(self.error, dtype=float).ravel()
        if self.replicates is not None:
            self.replicates = np.asarray(self.replicates, dtype=float).ravel()

    @property
    def n_observations(self) -> int:
        return int(self.concentration.size)


@dataclass(frozen=True)
class PropertyKey:
    """What the experiments were done to resolve.

    Ordered so that the coarse identifiers come first and the record-specific ones
    last, which makes a sorted listing group sensibly. Frozen, so it can key a
    dictionary, and its ``str`` is a readable one-line summary.
    """

    substance: str | None = None
    topcategory: str | None = None
    category: str | None = None  # EndpointCategory.code
    method: str | None = None  # the assay method parameter
    cell_type: str | None = None  # study_config.cell_field(category), if the category has one
    endpoint: str | None = None  # EffectRecord.endpoint
    endpointtype: str | None = None
    hours: float | None = None  # exposure time, normalised
    concentration_unit: str | None = None
    response_unit: str | None = None
    parameters: tuple[str, ...] = ()  # curated identity beyond cell type, if any is added later
    conditions: tuple[str, ...] = ()  # array-level conditions, minus the control

    def __str__(self) -> str:  # pragma: no cover - display only
        parts = [
            p
            for p in (
                self.substance,
                self.topcategory,
                self.category,
                self.method,
                self.cell_type,
                self.endpoint,
            )
            if p
        ]
        if self.hours is not None:
            parts.append(f"{self.hours:g}h")
        if self.concentration_unit:
            parts.append(f"conc[{self.concentration_unit}]")
        parts.extend(self.parameters)
        parts.extend(self.conditions)
        return " | ".join(parts)


# ----------------------------------------------------------------------
# the adapter
# ----------------------------------------------------------------------
def _dose_axis_names(category: str | None) -> tuple[str, ...]:
    """Condition names that carry the dose, per endpoint category.

    ``study_config`` is the curated source, shared with the jToxKit viewer. The
    literal fallbacks cover a record whose category has no config entry.
    """
    try:
        configured = tuple(sc.dose_condition_fields(category) or ())
    except Exception:
        configured = ()
    return tuple({*(c.upper() for c in configured), *DOSE_KEYS})


def _control_key_names(category: str | None) -> tuple[str, ...]:
    try:
        configured = sc.control_field(category)
    except Exception:
        configured = None
    names = [configured] if configured else []
    names.extend(CONTROL_KEYS)
    return tuple(dict.fromkeys(n for n in names if n))


def _pick_axis(axes, wanted: Sequence[str]) -> str | None:
    """Match an axis name case-insensitively; AMBIT upper-cases, config does not."""
    if not axes:
        return None
    upper = {w.upper() for w in wanted}
    for name in axes:
        if name.upper() in upper:
            return name
    for name in axes:
        if name.upper().startswith("CONCENTRATION") or name.upper().startswith("DOSE"):
            return name
    return None


def _replicate_index(papp, dose_names: Sequence[str]) -> dict[tuple, float]:
    """Replicate counts keyed by ``(endpoint, concentration)``.

    ``convert_effectrecords2array`` drops null condition columns, and
    ``NUMBER_OF_REPLICATES`` is exactly such a column -- its own source comments say
    so. The count has to be recovered from the raw ``EffectRecord.conditions``
    before the conversion, or every pre-aggregated row looks like a single well and
    the interval comes out inflated by sqrt(n).
    """
    index: dict[tuple, float] = {}
    upper = {n.upper() for n in dose_names}
    for effect in getattr(papp, "effects", None) or []:
        if isinstance(effect, EffectArray):
            continue
        conditions = getattr(effect, "conditions", None) or {}
        replicate_key = _first_key(conditions, REPLICATE_COUNT_KEYS)
        if replicate_key is None:
            continue
        replicates = _scalar(conditions[replicate_key])
        if replicates is None or replicates <= 0:
            continue
        concentration = None
        for name, value in conditions.items():
            if name.upper() in upper or name.upper().startswith("CONCENTRATION"):
                concentration = _scalar(value)
                break
        if concentration is None:
            continue
        index[(getattr(effect, "endpoint", None), float(concentration))] = float(
            replicates
        )
    return index


def _array_time_hours(array, axes_names, parameters) -> float | None:
    """Exposure time, from an axis if the array has one, else from the parameters.

    A parameter-level exposure time is constant for the whole protocol application,
    which is where real records put it; searching only the conditions misses it and
    silently merges 24 h and 48 h series into one bootstrap.
    """
    time_axis = _pick_axis(axes_names, TIME_KEYS)
    if time_axis is not None:
        values = getattr(array.axes[time_axis], "values", None)
        unit = getattr(array.axes[time_axis], "unit", None)
        if values is not None and np.size(values):
            unique = np.unique(np.asarray(values).ravel())
            if unique.size == 1:
                return _hours(float(unique[0]), unit)
    key = _first_key(parameters, TIME_KEYS)
    if key is not None:
        return _hours(parameters[key], _unit(parameters[key]))
    return None


def _is_replicate_axis(name: str) -> bool:
    upper = str(name).upper()
    return any(upper == k or upper.startswith(k) for k in REPLICATE_INDEX_KEYS)


def _slice_along_dose(signal, errors, conc, reps, axis_order, dose_axis, axes):
    """Read an N-d signal as a set of 1-d dose series.

    Read-only. Every operation below is a transpose, a reshape or a tile, all of
    which produce views or new arrays; the caller's ``signal``, ``errors`` and
    ``axes`` are never written to.

    Three kinds of axis, read differently:

    * the **dose** axis supplies the concentration of each observation;
    * a **replicate index** axis is gathered into repeated observations at the same
      concentration -- those are wells, i.e. repeated measurements of one point, not
      separate properties (see :data:`REPLICATE_INDEX_KEYS`);
    * any **other** axis is iterated, yielding one series per position and labelled
      into the key -- a record measuring at two exposure times is two properties.

    ``reps`` is the replicate count per dose position, carried through the same
    tiling as the concentration so it stays aligned with the observations.

    Returns ``[(concentration, response, error, replicates, labels), ...]``.
    """
    if signal.ndim <= 1:
        flat = signal.ravel()
        return [
            (
                conc[: flat.size],
                flat,
                None if errors is None else errors.ravel(),
                reps[: flat.size],
                (),
            )
        ]

    dose_position = axis_order.index(dose_axis)
    replicate_positions = [
        i
        for i, name in enumerate(axis_order)
        if i != dose_position and _is_replicate_axis(name)
    ]
    # A time axis is already carried in PropertyKey.hours; do not also label it.
    other_positions = [
        i
        for i, name in enumerate(axis_order)
        if i != dose_position
        and i not in replicate_positions
        and name.upper() not in {k.upper() for k in TIME_KEYS}
    ]
    time_positions = [
        i
        for i in range(len(axis_order))
        if i != dose_position
        and i not in replicate_positions
        and i not in other_positions
    ]

    permuted = np.transpose(
        signal, other_positions + time_positions + replicate_positions + [dose_position]
    )
    permuted_err = (
        None
        if errors is None
        else np.transpose(
            errors,
            other_positions + time_positions + replicate_positions + [dose_position],
        )
    )
    n_other = len(other_positions)
    # Time axes are single-valued here (checked by _array_time_hours); collapse them.
    lead = permuted.shape[:n_other]

    out = []
    for idx in np.ndindex(*lead) if lead else [()]:
        block = permuted[idx]
        block = block.reshape(-1, block.shape[-1])  # (repeats, n_dose)
        n_repeats, n_dose = block.shape
        values = block.reshape(-1)
        repeated = np.tile(conc[:n_dose], n_repeats)
        repeated_reps = np.tile(reps[:n_dose], n_repeats)
        if permuted_err is None:
            err = None
        else:
            err = permuted_err[idx].reshape(-1, n_dose).reshape(-1)
        labels = tuple(
            f"{axis_order[pos]}="
            f"{np.asarray(axes[axis_order[pos]].values).ravel()[i]}"
            for pos, i in zip(other_positions, idx)
        )
        out.append((repeated, values, err, repeated_reps, labels))
    return out


def series_from_protocol_application(
    papp,
    *,
    substance: str | None = None,
    extra_condition_keys: Sequence[str] = (),
) -> list[DoseSeries]:
    """Split one ``ProtocolApplication`` into one series per property.

    Built on :meth:`~pyambit.datamodel.ProtocolApplication.convert_effectrecords2array`,
    which is the canonical grouping: named axes each carrying their own unit,
    one array per endpoint/endpointtype/unit combination, and a split on the
    string-valued conditions -- which is also what separates an annotated control
    from the treatments. Entries that are already ``EffectArray`` are passed through
    by that method, so they are picked up here too rather than silently ignored.

    A property is one :class:`PropertyKey`, so a record measuring viability at 24 h
    and 48 h yields two series: a benchmark concentration at 24 h and one at 48 h
    are different numbers, not two measurements of one.
    """
    if not getattr(papp, "effects", None):
        return []

    protocol = getattr(papp, "protocol", None)
    topcategory = getattr(protocol, "topcategory", None) if protocol else None
    category = getattr(protocol, "category", None) if protocol else None
    category_code = (
        getattr(category, "code", None)
        if category is not None
        else (str(category) if category else None)
    )

    dose_names = _dose_axis_names(category_code)
    control_names = _control_key_names(category_code)

    parameters = dict(getattr(papp, "parameters", None) or {})
    method_name = _first_key(parameters, METHOD_PARAMETERS)
    try:
        configured_method = sc.method_field(category_code)
    except Exception:
        configured_method = None
    if method_name is None and configured_method:
        method_name = _first_key(parameters, (configured_method,))
    method = _as_text(parameters.get(method_name)) if method_name else None

    # Cell type is the one other parameter that defines the property rather than
    # describing who ran it and when. Everything else in `parameters` -- operator,
    # preparation date, input filename, well-plate note, medium formulation text,
    # dispersion protocol wording -- is deliberately left out of the key. Folding it
    # in was the previous behaviour, and it made consolidation nearly impossible: two
    # laboratories measuring the identical property essentially never share the same
    # operator or date, so the key differed and consolidate_providers never saw both.
    # curate_passing.py / curate_failing.py (notebooks-ambit) already treat material,
    # method and cell type as the property's identity and nothing else from
    # `parameters` -- this matches that, using study_config the same way method does.
    cell_name = _first_key(parameters, CELL_TYPE_PARAMETERS)
    try:
        configured_cell = sc.cell_field(category_code)
    except Exception:
        configured_cell = None
    if cell_name is None and configured_cell:
        cell_name = _first_key(parameters, (configured_cell,))
    cell_type = _as_text(parameters.get(cell_name)) if cell_name else None

    # The laboratory, not the project. owner.company.name is the funding project
    # (e.g. "NANoREG"); citation.owner is the lab that produced the data.
    citation = getattr(papp, "citation", None)
    owner = getattr(papp, "owner", None)
    company = getattr(owner, "company", None) if owner is not None else None
    provider = (
        (getattr(citation, "owner", None) if citation is not None else None)
        or getattr(company, "name", None)
        or getattr(papp, "investigation_uuid", None)
    )

    replicate_index = _replicate_index(papp, dose_names)

    arrays, _ = papp.convert_effectrecords2array()

    n_aggregated = 0
    controls: dict[tuple, list[float]] = {}
    candidates = []

    for array in arrays or []:
        endpointtype = getattr(array, "endpointtype", None)
        # Aggregated results (IC50 and friends) are summaries, not a dose series.
        # Dropped deliberately: relying on "AGGREGATED RESULT" failing to parse as a
        # float is not a filter.
        if isinstance(endpointtype, str) and endpointtype.strip().upper() == (
            "AGGREGATED"
        ):
            n_aggregated += 1
            continue

        axes = getattr(array, "axes", None) or {}
        dose_axis = _pick_axis(axes, dose_names)
        signal = getattr(array, "signal", None)
        if dose_axis is None or signal is None or signal.values is None:
            continue

        conditions = dict(getattr(array, "conditions", None) or {})
        control_name = _first_key(conditions, control_names)
        role = classify_control(conditions.get(control_name)) if control_name else None

        endpoint = getattr(array, "endpoint", None)
        hours = _array_time_hours(array, axes, parameters)
        candidates.append(
            (array, dose_axis, conditions, control_name, role, endpoint, hours)
        )

    # Negative / solvent controls give the baseline the benchmark response is
    # measured from; they are a separate array because the conversion splits on the
    # string-valued condition that annotates them.
    for entry in candidates:
        array, dose_axis, _conditions, _cname, role, endpoint, hours = entry
        if role in ("negative", "solvent", "blank", "control"):
            values = np.asarray(array.signal.values, dtype=float).ravel()
            values = values[np.isfinite(values)]
            if values.size:
                controls.setdefault((endpoint, hours), []).append(
                    float(np.mean(values))
                )

    series: list[DoseSeries] = []
    for entry in candidates:
        array, dose_axis, conditions, control_name, role, endpoint, hours = entry
        if role is not None:
            continue  # a control, not a dose-response series

        axes = array.axes or {}
        raw_conc = np.asarray(axes[dose_axis].values, dtype=float).ravel()
        conc, conc_unit = _concentration_in_canonical(
            raw_conc, getattr(axes[dose_axis], "unit", None)
        )

        signal_values = np.asarray(array.signal.values, dtype=float)
        errors = array.signal.errorValue
        errors = None if errors is None else np.asarray(errors, dtype=float)

        # Keyed on the *recorded* concentration, never the converted one: the
        # conversion factor is not exactly 1 even for identical units, so an
        # exact-float lookup on converted values silently misses every row.
        reps_per_dose = np.array(
            [replicate_index.get((endpoint, float(c)), 1.0) for c in raw_conc],
            dtype=float,
        )
        slices = _slice_along_dose(
            signal_values,
            errors,
            conc,
            reps_per_dose,
            list(axes.keys()),
            dose_axis,
            axes,
        )

        response_unit = getattr(array.signal, "unit", None)
        extra = tuple(
            f"{name}={conditions[name]}"
            for name in extra_condition_keys
            if name in conditions
        )

        control_value, control_route = None, None
        pooled = controls.get((endpoint, hours))
        if pooled:
            control_value = float(np.mean(pooled))
            control_route = "annotated"

        for conc_obs, values, errs, reps_obs, labels in slices:
            finite = np.isfinite(conc_obs) & np.isfinite(values)
            if finite.sum() < 2:
                continue
            key = PropertyKey(
                substance=substance,
                topcategory=topcategory,
                category=category_code,
                method=method,
                cell_type=cell_type,
                endpoint=None if endpoint is None else str(endpoint),
                endpointtype=(
                    None
                    if getattr(array, "endpointtype", None) is None
                    else str(array.endpointtype)
                ),
                hours=hours,
                concentration_unit=conc_unit,
                response_unit=(
                    str(response_unit).strip()
                    if isinstance(response_unit, str)
                    else None
                ),
                conditions=extra + labels,
            )
            series.append(
                DoseSeries(
                    concentration=conc_obs[finite],
                    response=values[finite],
                    error=None if errs is None else errs[finite],
                    error_qualifier=getattr(array.signal, "errQualifier", None),
                    replicates=reps_obs[finite],
                    concentration_unit=conc_unit,
                    response_unit=key.response_unit,
                    time=hours,
                    provider=provider,
                    control_response=control_value,
                    control_route=control_route,
                    key=key,
                    metadata={
                        "assay_uuid": getattr(papp, "assay_uuid", None),
                        "investigation_uuid": getattr(papp, "investigation_uuid", None),
                        "document_uuid": getattr(papp, "uuid", None),
                        "parameters": parameters,
                        "n_aggregated_dropped": n_aggregated,
                    },
                )
            )
    return series


def series_from_substance(
    record, **kwargs
) -> dict[PropertyKey, dict[str, list[DoseSeries]]]:
    """Every series in a ``SubstanceRecord``, grouped by property then by provider.

    Returns ``{PropertyKey: {provider: [DoseSeries, ...]}}``. A provider normally
    maps to a single series -- exposure time is part of the key -- and to more only
    when one laboratory genuinely ran the same property more than once, which is
    consolidatable evidence rather than an accident.
    """
    name = getattr(record, "name", None) or getattr(record, "i5uuid", None)
    grouped: dict[PropertyKey, dict[str, list[DoseSeries]]] = {}
    for papp in getattr(record, "study", None) or []:
        for series in series_from_protocol_application(papp, substance=name, **kwargs):
            grouped.setdefault(series.key, {}).setdefault(
                series.provider or "unknown", []
            ).append(series)
    return grouped


# ----------------------------------------------------------------------
# the benchmark concentration and its distribution
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class BmdSpec:
    """Constants of the analysis. Nothing here is derived from the cohort."""

    benchmark_responses: tuple[float, ...]
    """Benchmark responses in the assay's own units, as a change from control."""

    direction: str = "decreasing"
    """``"decreasing"`` for viability-like readouts, ``"increasing"`` for damage."""

    n_quantiles: int = 32
    n_bootstrap: int = 400
    control_concentration: float = 0.0
    """Concentration treated as the control when no control row is annotated."""

    log_window: tuple[float, float] | None = None
    """Optional fixed log10 concentration window, for a comparable index."""

    resample: str = "parametric"
    """How a bootstrap draw is generated.

    ``"parametric"`` (default) perturbs each concentration mean by
    ``N(0, sigma / sqrt(n))`` using the error the record already carries --
    ``EffectResult.errorValue`` -- pooled across concentrations when it is absent.
    ``"nonparametric"`` resamples the wells themselves.

    The default is not the textbook choice, and the reason is the replicate count.
    An in vitro plate typically has three wells per concentration, and resampling
    three values with replacement badly understates the variance: measured, a
    two-replicate series produced a *narrower* interval than a twelve-replicate one,
    which is the opposite of what an interval is for. The parametric draw behaves at
    n = 3 and uses information the data model already stores. Use
    ``"nonparametric"`` when there are many wells per concentration and the noise is
    visibly non-Gaussian.
    """

    seed: int = 0

    def __post_init__(self) -> None:
        if not self.benchmark_responses:
            raise ValueError("at least one benchmark response is required")
        if self.direction not in ("decreasing", "increasing"):
            raise ValueError("direction must be 'decreasing' or 'increasing'")
        if self.n_bootstrap < 20:
            raise ValueError("n_bootstrap must be at least 20 to give usable quantiles")
        if self.resample not in ("parametric", "nonparametric"):
            raise ValueError("resample must be 'parametric' or 'nonparametric'")

    @property
    def u_grid(self) -> np.ndarray:
        return (np.arange(self.n_quantiles) + 0.5) / self.n_quantiles

    @property
    def n_levels(self) -> int:
        return len(self.benchmark_responses)

    @property
    def dim(self) -> int:
        return self.n_quantiles * self.n_levels


@dataclass
class BmdProfile:
    """The BMD CDF: one bootstrap distribution of log10 BMD per benchmark response."""

    Q: np.ndarray  # (n_quantiles, n_levels) log10 concentration
    determined: np.ndarray  # (n_levels,) bool: BMD inside the tested range
    censored_fraction: np.ndarray  # (n_levels,) fraction of draws that never crossed
    control: float = float("nan")
    control_route: str | None = None
    log_range: tuple[float, float] = (float("nan"), float("nan"))
    key: "PropertyKey | None" = None
    providers: list[str] = field(default_factory=list)
    spec: BmdSpec | None = None

    def _at(self, u: float) -> np.ndarray:
        assert self.spec is not None
        index = int(np.argmin(np.abs(self.spec.u_grid - u)))
        return self.Q[index]

    @property
    def bmd(self) -> np.ndarray:
        """Median of the bootstrap distribution, in log10 concentration."""
        return self._at(0.5)

    @property
    def bmdl(self) -> np.ndarray:
        return self._at(0.05)

    @property
    def bmdu(self) -> np.ndarray:
        return self._at(0.95)

    @property
    def width(self) -> np.ndarray:
        """BMDU - BMDL in decades: how well the concentration is determined."""
        return self.bmdu - self.bmdl


def _crossing(log_conc: np.ndarray, effect: np.ndarray, level: float) -> float:
    """Lowest log concentration at which the curve reaches ``level``.

    Linear interpolation between the bracketing concentrations -- the weakest
    assumption available. Returns ``nan`` when the curve never reaches the level.
    """
    above = effect >= level
    if not above.any():
        return float("nan")
    first = int(np.argmax(above))
    if first == 0:
        return float(log_conc[0])
    y0, y1 = effect[first - 1], effect[first]
    if y1 == y0:
        return float(log_conc[first])
    t = (level - y0) / (y1 - y0)
    return float(log_conc[first - 1] + t * (log_conc[first] - log_conc[first - 1]))


def bmd_cdf(series: Sequence[DoseSeries] | DoseSeries, spec: BmdSpec) -> BmdProfile:
    """Bootstrap the benchmark concentration at each benchmark response.

    The concentration means are perturbed by their standard error, the crossing
    found by interpolation, and the empirical quantiles of those draws are the BMD
    CDF -- so BMDL, the point estimate and BMDU come from one object rather than
    three procedures.

    A draw in which the curve never reaches the benchmark response is *censored*,
    not discarded: it is counted, and a level whose draws are more than half
    censored is marked undetermined. That is the honest statement -- the experiment
    bounds the BMD from below but does not locate it.
    """
    if isinstance(series, DoseSeries):
        series = [series]
    concentration = np.concatenate([s.concentration for s in series])
    response = np.concatenate([s.response for s in series])
    recorded = np.concatenate(
        [
            s.error if s.error is not None else np.full(s.n_observations, np.nan)
            for s in series
        ]
    )
    replicates = np.concatenate(
        [
            (
                s.replicates
                if s.replicates is not None
                else np.ones(s.n_observations, dtype=float)
            )
            for s in series
        ]
    )

    annotated = [s.control_response for s in series if s.control_response is not None]
    if annotated:
        control = float(np.mean(annotated))
        control_route = "annotated"
    else:
        control_mask = concentration <= spec.control_concentration
        if control_mask.any():
            control = float(np.mean(response[control_mask]))
            control_route = "zero-concentration"
        else:
            control = float(
                np.max(response) if spec.direction == "decreasing" else np.min(response)
            )
            control_route = "extremum"

    positive = concentration > 0
    if positive.sum() < 2:
        raise ValueError("at least two positive concentrations are required")
    log_conc = np.log10(concentration[positive])
    values = response[positive]
    effect = (
        (control - values) if spec.direction == "decreasing" else (values - control)
    )

    unique, inverse = np.unique(log_conc, return_inverse=True)
    if unique.size < 2:
        raise ValueError("at least two distinct positive concentrations are required")
    groups = [np.flatnonzero(inverse == g) for g in range(unique.size)]
    observed = np.array([float(np.mean(effect[g])) for g in groups])

    # Wells behind each concentration mean: rows x recorded replicates. Raw wells
    # give rows = n with replicates = 1; a pre-aggregated row gives rows = 1 with
    # replicates = n. Both must divide sigma by sqrt(the same total).
    rep_positive = replicates[positive]
    wells = np.array(
        [float(np.sum(np.maximum(rep_positive[g], 1.0))) for g in groups],
        dtype=float,
    )

    if spec.resample == "nonparametric" and np.all(
        np.array([g.size for g in groups]) == 1
    ):
        raise ValueError(
            "resample='nonparametric' needs several rows per concentration, but this "
            "record is pre-aggregated (one row per concentration); use "
            "resample='parametric', which uses the recorded errorValue"
        )

    # Standard error of each concentration mean: the recorded error where the record
    # has one, else pooled within-concentration spread, else a fraction of the
    # observed range. Pooling matters -- a per-concentration SD from three wells is
    # itself far too noisy to set an interval with.
    recorded_positive = recorded[positive]
    finite_recorded = np.isfinite(recorded_positive)
    sigma = (
        float(np.mean(recorded_positive[finite_recorded]))
        if finite_recorded.any()
        else float("nan")
    )
    if not np.isfinite(sigma) or sigma <= 0:
        blocks = [effect[g] - effect[g].mean() for g in groups if g.size > 1]
        residuals = np.concatenate(blocks) if blocks else np.zeros(1)
        sizes = np.array([g.size for g in groups], dtype=float)
        dof = max(int(sizes[sizes > 1].sum() - (sizes > 1).sum()), 1)
        sigma = float(np.sqrt(np.sum(residuals**2) / dof))
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = max(0.05 * float(np.ptp(effect)), 1e-9)

    # errQualifier "SE" means the recorded value already IS a standard error and
    # must not be divided again; "SD" (and an absent qualifier) means a spread.
    qualifier = next((s.error_qualifier for s in series if s.error_qualifier), None)
    if (
        finite_recorded.any()
        and isinstance(qualifier, str)
        and (qualifier.strip().upper() == "SE")
    ):
        standard_error = np.full(unique.size, sigma)
    else:
        standard_error = sigma / np.sqrt(np.maximum(wells, 1.0))

    rng = np.random.default_rng(spec.seed)
    levels = np.asarray(spec.benchmark_responses, dtype=float)
    draws = np.full((spec.n_bootstrap, levels.size), np.nan)
    for b in range(spec.n_bootstrap):
        if spec.resample == "parametric":
            means = observed + rng.normal(0.0, standard_error)
        else:
            means = np.array(
                [
                    (
                        float(np.mean(effect[rng.choice(g, size=g.size, replace=True)]))
                        if g.size > 1
                        else float(effect[g[0]])
                    )
                    for g in groups
                ]
            )
        running = np.maximum.accumulate(means)  # lowest concentration reaching it
        for k, level in enumerate(levels):
            draws[b, k] = _crossing(unique, running, float(level))

    Q = np.full((spec.n_quantiles, levels.size), np.nan)
    censored = np.zeros(levels.size)
    for k in range(levels.size):
        column = draws[:, k]
        finite = column[np.isfinite(column)]
        censored[k] = 1.0 - finite.size / column.size
        if finite.size:
            Q[:, k] = np.quantile(finite, spec.u_grid)
    determined = censored <= 0.5

    if spec.log_window is not None:
        Q = np.clip(Q, *spec.log_window)

    return BmdProfile(
        Q=Q,
        determined=determined,
        censored_fraction=censored,
        control=control,
        control_route=control_route,
        log_range=(float(unique[0]), float(unique[-1])),
        key=series[0].key,
        providers=sorted({s.provider for s in series if s.provider}),
        spec=spec,
    )


def consolidate_providers(
    by_provider: dict[str, Sequence[DoseSeries]], spec: BmdSpec
) -> BmdProfile:
    """One BMD CDF for the material, pooling the laboratories as a mixture.

    Each laboratory's bootstrap distribution is computed separately -- so its own
    replicate structure, control and concentration grid are used -- and the
    distributions are then mixed with equal weight per laboratory. A laboratory with
    two hundred wells therefore does not outvote one with twenty.

    The mixture is the right combination *here*, where the components are genuine
    uncertainty distributions: its spread is within-laboratory uncertainty plus
    between-laboratory disagreement, which is what a consolidated BMD should report.
    """
    if not by_provider:
        raise ValueError("no providers supplied")
    profiles, samples = [], []
    for provider in sorted(by_provider):
        profile = bmd_cdf(by_provider[provider], spec)
        profiles.append(profile)
        # Re-sample each laboratory's CDF on a common fine grid: equal weight.
        fine = (np.arange(512) + 0.5) / 512
        drawn = np.full((512, spec.n_levels), np.nan)
        for k in range(spec.n_levels):
            if profile.determined[k] and np.isfinite(profile.Q[:, k]).all():
                drawn[:, k] = np.interp(fine, spec.u_grid, profile.Q[:, k])
        samples.append(drawn)

    stacked = np.concatenate(samples, axis=0)
    Q = np.full((spec.n_quantiles, spec.n_levels), np.nan)
    censored = np.zeros(spec.n_levels)
    for k in range(spec.n_levels):
        column = stacked[:, k]
        finite = column[np.isfinite(column)]
        censored[k] = 1.0 - finite.size / column.size
        if finite.size:
            Q[:, k] = np.quantile(finite, spec.u_grid)

    lows = [p.log_range[0] for p in profiles]
    highs = [p.log_range[1] for p in profiles]
    routes = {p.control_route for p in profiles if p.control_route}
    return BmdProfile(
        Q=Q,
        determined=censored <= 0.5,
        censored_fraction=censored,
        control=float(np.mean([p.control for p in profiles])),
        # More than one route across laboratories is a consolidation hazard: the
        # baseline was defined differently in different records.
        control_route="+".join(sorted(routes)) if routes else None,
        log_range=(float(min(lows)), float(max(highs))),
        key=profiles[0].key,
        providers=sorted({p for prof in profiles for p in prof.providers}),
        spec=spec,
    )


# ----------------------------------------------------------------------
def bmd_vector(
    profile: BmdProfile, spec: BmdSpec, *, fill: float | None = None
) -> np.ndarray:
    """The BMD CDF flattened, level-major: all quantiles for BMR 1, then BMR 2, ...

    Entries are log10 concentrations, so Euclidean distance between two vectors is
    an RMS displacement in decades and the vector doubles as the thing you would
    report: column ``u=0.05`` of level ``r`` is BMDL(r).

    Undetermined levels are filled with ``fill`` -- by default the top of
    ``spec.log_window`` if one is set, else the top of the tested range, meaning "no
    tested concentration produced this response".
    """
    if fill is None:
        fill = spec.log_window[1] if spec.log_window else profile.log_range[1]
    Q = np.where(profile.determined[None, :], profile.Q, fill)
    Q = np.where(np.isfinite(Q), Q, fill)
    return Q.T.ravel() / np.sqrt(spec.n_quantiles * spec.n_levels)


def bmd_recovery(profile: BmdProfile, truth: Sequence[float]) -> dict[str, float]:
    """Evaluate against a known BMD, which is what the estimate is for.

    Returns the median bias in decades, the RMS error, the width of the BMDL-to-BMDU
    interval, and the coverage -- the fraction of benchmark responses whose true BMD
    lies inside that interval. A calibrated 5-95 % interval covers 0.9 of the time;
    well below that means the uncertainty is understated, well above means it is
    uninformative.
    """
    truth = np.asarray(list(truth), dtype=float)
    determined = profile.determined & np.isfinite(profile.bmd)
    if not determined.any():
        return {
            "bias": float("nan"),
            "rmse": float("nan"),
            "width": float("nan"),
            "coverage": float("nan"),
            "n": 0.0,
        }
    error = profile.bmd[determined] - truth[determined]
    inside = (truth[determined] >= profile.bmdl[determined]) & (
        truth[determined] <= profile.bmdu[determined]
    )
    return {
        "bias": float(np.median(error)),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "width": float(np.median(profile.width[determined])),
        "coverage": float(np.mean(inside)),
        "n": float(determined.sum()),
    }
