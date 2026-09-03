"""Read and plot the data a written NeXus (`.nxs`) file actually carries.

Generic, dataset-agnostic, and deliberately h5py-level:
`pyambit.nexus_parser.Nexus2Ambit`'s only implemented mode
(`index_only=True`) returns a link-path placeholder for every EffectArray
rather than the array itself, so it cannot see whether a file carries data
at all -- this module opens the arrays directly.

Two layers:

* **reading** -- follow the NeXus `@default` chain to the group a viewer
  would plot (`default_nxdata`), resolve its signal/axes by name
  (`signal_dataset` / `axis_names`), squeeze the size-1 "condition" axes a
  single run leaves behind (`squeeze_with_axes`), and reduce what's left to
  a line or a heatmap (`resolve_plot`). `entry_metadata` pulls the
  material / provider / method / investigation / condition ranges every
  NXentry `pyambit.nexus_writer` writes carries, for annotating a figure.

* **plotting** -- `apply_paper_style()` sets a restrained rcParams profile
  (thin spines, no top/right spine, minor ticks, tight layout) and `draw`
  renders one resolved plot, replicate-aware (mean +- SD across a
  Replicate/Experiment axis rather than a bare squeeze) and optionally
  annotated with an `entry_metadata` dict. `figure_png()` returns the same
  figure as PNG bytes for a viewer or thumbnail service to serve on
  demand. Figures are rendered when asked for -- never written back into
  the .nxs, which should carry measurements, not a stale rendering of
  them.

Ported from nanodata-momentum-clean's per-pipeline copies, which now
re-export from here.
"""

from __future__ import annotations

import datetime as _dt
import io

import h5py
import numpy as np

# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def _attr_str(group, name):
    """One NeXus/HDF5 attribute as a `str` (h5py hands text attrs back as
    `bytes`), or None when absent."""
    value = group.attrs.get(name)
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, np.ndarray):
        return _attr_str_scalar(value)
    return str(value)


def _attr_str_scalar(arr):
    if arr.shape == ():
        v = arr[()]
        return v.decode(errors="replace") if isinstance(v, bytes) else str(v)
    return ", ".join(
        x.decode(errors="replace") if isinstance(x, bytes) else str(x) for x in arr
    )


def _decode(v):
    """A single axis/label value as text: decode bytes, strip. Numbers pass
    through unchanged."""
    if isinstance(v, bytes):
        return v.decode(errors="replace").strip()
    return v


def iter_nxdata_groups(h5group, path=""):
    """Yield (path, h5py.Group) for every NXdata group under `h5group`."""
    for name, obj in h5group.items():
        child_path = f"{path}/{name}" if path else name
        if isinstance(obj, h5py.Group):
            if obj.attrs.get("NX_class") in (b"NXdata", "NXdata"):
                yield child_path, obj
            yield from iter_nxdata_groups(obj, child_path)


def iter_entries(h5file):
    """Yield (name, h5py.Group) for every NXentry in an open file -- i.e.
    every real study, skipping the shared `substance` / `investigation`
    groups `nexus_writer` links from them."""
    for name, obj in h5file.items():
        if isinstance(obj, h5py.Group) and _attr_str(obj, "NX_class") == "NXentry":
            yield name, obj


def signal_dataset(nxdata_group):
    """The (name, h5py.Dataset) an NXdata group's `signal` attr points at,
    or (None, None) if the attr is missing or dangling."""
    sig_name = _attr_str(nxdata_group, "signal")
    if sig_name is None or sig_name not in nxdata_group:
        return None, None
    return sig_name, nxdata_group[sig_name]


def default_nxdata(entry: h5py.Group):
    """The NXdata group `entry` designates as its plot, per the NeXus
    "finding plottable data" rule
    (https://manual.nexusformat.org/datarules.html#find-plottable-data):
    follow `@default` from the NXentry down through however many
    NXprocess/NXdata levels it takes, rather than guessing from directory
    order. `nexus_writer.to_nexus` stamps this chain on every entry it
    writes so a NeXus-aware viewer (nexpy, H5Web, nexusformat's `.plot()`)
    can find "the" plot without walking the whole tree.
    """
    node = entry
    seen = set()
    while True:
        if _attr_str(node, "NX_class") == "NXdata":
            return node
        default_name = _attr_str(node, "default")
        if default_name is None or default_name not in node:
            return None
        key = node.name + "/" + default_name
        if key in seen:
            return None  # defensive: a cyclic @default chain
        seen.add(key)
        node = node[default_name]


def count_substances(h5file) -> int:
    """How many substances the file's shared `substance` group holds."""
    substance_group = h5file.get("substance")
    return len(substance_group) if substance_group is not None else 0


def axis_names(group) -> list:
    """`group.attrs["axes"]`, decoded, in signal-dimension order (axes[i]
    indexes signal.shape[i], the nexus_writer / nexusformat convention)."""
    axes = group.attrs.get("axes")
    if axes is None:
        return []
    if isinstance(axes, (bytes, str)):
        axes = [axes]
    return [a.decode(errors="replace") if isinstance(a, bytes) else str(a) for a in axes]


def squeeze_with_axes(values: np.ndarray, names: list):
    """Drop size-1 dimensions from `values`, keeping `names` in step with
    the dimensions that survive.

    A condition that does not vary within one file (a fixed `time`, a
    single `Experiment`) still gets its own length-1 axis in the written
    signal -- dose-response endpoints are commonly shape
    (n_concentration, 1, 1) for exactly this reason. Squeezing before
    picking a plot turns that back into the 1D curve it actually is,
    instead of being rejected as "not 1D" or mislabelled against the wrong
    axis.
    """
    values = np.asarray(values)
    if values.ndim != len(names):
        return np.squeeze(values), []
    keep = [i for i, n in enumerate(values.shape) if n != 1]
    return np.squeeze(values), [names[i] for i in keep]


def labeled(name, dataset) -> str:
    """"Concentration (ug/mL)" from a name and the dataset carrying its
    `units` attr -- nexus_writer stamps `units` on every axis and signal
    dataset it writes, so the unit is always right next to the values.

    Endpoint names in these templates sometimes already carry the unit
    ("Wavenumber (cm-1)"); appending it again gives "Wavenumber (cm-1)
    (cm-1)", so a unit already present in the name is not repeated.
    """
    if name is None:
        return "signal"
    name = str(name).strip()
    if dataset is None:
        return name
    unit = dataset.attrs.get("units")
    if unit is None:
        return name
    unit = unit.decode(errors="replace") if isinstance(unit, bytes) else str(unit)
    unit = unit.strip()
    if not unit or unit.lower() in name.lower():
        return name
    return f"{name} ({unit})"


_REPLICATE_AXES = {"replicate", "experiment", "run", "repeat"}


def _is_replicate(name) -> bool:
    return str(name).strip().lower() in _REPLICATE_AXES


def numeric_or_none(values):
    """`values` as a float array if EVERY element is numeric, else None.

    A condition axis is routinely mixed -- a dose series that also lists its
    controls by name ("0.003, 1-propanol, 0.017, 0.1, IC") -- and treating
    that as numeric is what makes `float(b' 1-propanol')` blow up. One
    all-or-nothing test, used everywhere an axis is about to be sorted,
    log-scaled or plotted as a continuous quantity.
    """
    if values is None:
        return None
    arr = np.asarray(values)
    if arr.dtype.kind in "fiu":
        return arr.astype(float)
    try:
        return np.asarray(
            [float(_decode(v)) for v in arr.ravel()], dtype=float
        ).reshape(arr.shape)
    except (TypeError, ValueError):
        return None


def _split_numeric_axis(x_values, y, grid=None):
    """Partition an axis into its numeric part and its named part.

    Returns (num_x, num_y, num_grid, cat_labels, cat_y, cat_grid). A mixed
    dose axis is not one scale: the doses are a continuous series and the
    named entries are controls. Plotting them on a shared axis either
    crashes (float("1-propanol")) or silently orders a control as if it
    were a concentration.
    """
    labels = [_decode(v) for v in np.asarray(x_values).ravel()]
    num_idx, cat_idx = [], []
    for i, v in enumerate(labels):
        try:
            float(v)
            num_idx.append(i)
        except (TypeError, ValueError):
            cat_idx.append(i)
    take = lambda a, idx: (None if a is None else np.asarray(a)[idx])  # noqa: E731
    return (
        np.asarray([float(labels[i]) for i in num_idx]) if num_idx else None,
        take(y, num_idx),
        take(grid, num_idx),
        [labels[i] for i in cat_idx],
        take(y, cat_idx),
        take(grid, cat_idx),
    )


def resolve_plot(group, sig_name, values):
    """(kind, payload) for one NXdata group's already-loaded signal, or None
    when there is nothing sane to plot (still >=3D after squeezing every
    non-varying condition).

    Payload is a dict, so a caller reads fields by name rather than by
    tuple position:

    kind "series"   -- a response against one x axis.
      x, y, grid (x-by-replicate, or None), x_label, y_label, x_name,
      rep_name, categorical (x is names, not quantities),
      cat_labels / cat_y / cat_grid (the named controls split off a mixed
      axis, or None).
    kind "replicates" -- the ONLY surviving axis is replicate/experiment,
      so there is no independent variable: y per run, to be shown as points
      about a mean, never a trend line.
      y, rep_labels, y_label, rep_name.
    kind "heatmap"  -- two genuinely different conditions.
      grid, x, y, x_label, y_label.
    """
    names = axis_names(group)
    squeezed, kept = squeeze_with_axes(np.asarray(values, dtype=float), names)
    signal_label = labeled(sig_name, group.get(sig_name))

    if squeezed.ndim == 1:
        x_name = kept[0] if kept and kept[0] in group else None
        raw_x = np.asarray(group[x_name][()]) if x_name else None
        # A lone replicate/experiment axis is NOT an independent variable:
        # run number carries no magnitude, so a line across it would draw a
        # trend that does not exist. Show the runs as points about their
        # mean instead.
        if x_name is not None and _is_replicate(x_name):
            return "replicates", {
                "y": squeezed,
                "rep_labels": [_tick_label(v) for v in np.asarray(raw_x).ravel()],
                "y_label": signal_label,
                "rep_name": x_name,
            }
        return "series", _series_payload(
            signal_label, x_name, raw_x, squeezed, None, group
        )

    if squeezed.ndim == 2:
        rep_idx = next((i for i, n in enumerate(kept) if _is_replicate(n)), None)
        if rep_idx is not None:
            x_idx = 1 - rep_idx
            grid = squeezed if x_idx == 0 else squeezed.T  # (x, replicate)
            x_name = kept[x_idx]
            raw_x = (
                np.asarray(group[x_name][()]) if x_name in group else None
            )
            if _is_replicate(x_name) or raw_x is None:
                # both axes are repeats, or no x values to speak of
                return "replicates", {
                    "y": np.nanmean(grid, axis=0),
                    "rep_labels": [str(i + 1) for i in range(grid.shape[1])],
                    "y_label": signal_label,
                    "rep_name": kept[rep_idx],
                }
            payload = _series_payload(
                signal_label, x_name, raw_x, np.nanmean(grid, axis=1), grid, group
            )
            payload["rep_name"] = kept[rep_idx]
            return "series", payload

        # two genuinely different conditions -> heatmap
        x_name = kept[0] if kept else None
        y_name = kept[1] if len(kept) > 1 else None
        return "heatmap", {
            "grid": squeezed,
            "x": np.asarray(group[x_name][()]) if x_name in group else None,
            "y": np.asarray(group[y_name][()]) if y_name in group else None,
            "x_label": labeled(x_name, group.get(x_name)) if x_name else "axis 0",
            "y_label": labeled(y_name, group.get(y_name)) if y_name else "axis 1",
            "value_label": signal_label,
        }

    return None


def _series_payload(signal_label, x_name, raw_x, y, grid, group):
    """Assemble a "series" payload, classifying the x axis as continuous or
    categorical and splitting the named controls off a mixed axis."""
    if x_name is None or raw_x is None:
        return {
            "x": np.arange(len(y), dtype=float),
            "y": y,
            "grid": grid,
            "x_label": "index",
            "y_label": signal_label,
            "x_name": None,
            "rep_name": None,
            "categorical": False,
            "cat_labels": None,
            "cat_y": None,
            "cat_grid": None,
        }

    x_label = labeled(x_name, group.get(x_name))
    numeric = numeric_or_none(raw_x)
    cat_labels = cat_y = cat_grid = None

    if numeric is None:
        num_x, num_y, num_grid, cat_labels, cat_y, cat_grid = _split_numeric_axis(
            raw_x, y, grid
        )
        if num_x is not None and len(num_x) >= 2:
            # mixed: a real dose series plus named controls
            x, y, grid, categorical = num_x, num_y, num_grid, False
        else:
            # wholly categorical: names are the axis
            x = np.arange(len(y), dtype=float)
            cat_labels = [_decode(v) for v in np.asarray(raw_x).ravel()]
            cat_y = cat_grid = None
            categorical = True
    else:
        x, categorical = numeric, False

    return {
        "x": x,
        "y": y,
        "grid": grid,
        "x_label": x_label,
        "y_label": signal_label,
        "x_name": x_name,
        "rep_name": None,
        "categorical": categorical,
        "cat_labels": cat_labels,
        "cat_y": cat_y,
        "cat_grid": cat_grid,
    }


def _timestamp(value):
    """A ms/s epoch or an ISO string -> "YYYY-MM-DD", or None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    if isinstance(value, str):
        return value.split("T")[0].strip() or None
    try:
        secs = float(value)
    except (TypeError, ValueError):
        return None
    if secs > 1e11:  # milliseconds
        secs /= 1000.0
    try:
        return _dt.datetime.fromtimestamp(secs, _dt.timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def entry_metadata(h5file, entry: h5py.Group) -> dict:
    """Everything worth putting next to (or on) a figure for one NXentry --
    read from the paths `pyambit.nexus_writer` populates. Missing values are
    simply absent from the dict.
    """
    meta: dict = {}

    sample = entry.get("sample")
    if sample is not None:
        provider = sample.get("provider")
        if provider is not None:
            meta["provider"] = _decode(provider[()])
        s_uuid = _attr_str(sample, "uuid")
        if s_uuid:
            meta["substance_uuid"] = s_uuid
            ref = h5file.get(f"substance/{s_uuid}")
            if ref is not None:
                name = _attr_str(ref, "publicname") or (
                    ref.get("name")[()] if "name" in ref else None
                )
                meta["material"] = _decode(name) if name is not None else s_uuid
                if _attr_str(ref, "ownerName"):
                    meta["owner"] = _attr_str(ref, "ownerName")

    doc = entry.get("experiment_documentation")
    if doc is not None:
        method = _attr_str(doc, "method")
        if method:
            meta["method"] = method
        if "date" in doc:
            when = _timestamp(doc["date"][()])
            if when:
                meta["date"] = when
        protocol = doc.get("protocol")
        if protocol is not None:
            for key in ("topcategory", "code", "endpoint", "guideline"):
                val = _attr_str(protocol, key)
                if val:
                    meta.setdefault("protocol", {})[key] = val

    ref = entry.get("reference")
    if ref is not None:
        for field in ("title", "owner", "year", "doi", "url"):
            if field in ref:
                meta.setdefault("reference", {})[field] = _decode(ref[field][()])

    inv_link = entry.get("investigation")
    if inv_link is not None:
        title = _attr_str(inv_link, "title") or (
            inv_link["title"][()] if "title" in inv_link else None
        )
        if title is not None:
            meta["investigation"] = _decode(title)
        desc = _attr_str(inv_link, "description")
        if desc:
            meta["investigation_description"] = desc

    for field, key in (
        ("entry_identifier_uuid", "study_uuid"),
        ("collection_identifier", "investigation_uuid"),
        ("experiment_identifier", "assay_uuid"),
    ):
        if field in entry:
            meta[key] = _decode(entry[field][()])

    # condition names + numeric ranges, from the default-plot NXdata's axes
    nxdata = default_nxdata(entry)
    if nxdata is not None:
        conditions = {}
        for name in axis_names(nxdata):
            if name not in nxdata:
                continue
            vals = np.asarray(nxdata[name][()])
            if vals.dtype.kind in "fiu":
                finite = vals[np.isfinite(vals)]
                if finite.size:
                    lo, hi = float(finite.min()), float(finite.max())
                    conditions[name] = (
                        f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
                    )
                    if name.lower() in _REPLICATE_AXES:
                        meta.setdefault("n_replicates", {})[name] = int(vals.size)
            else:
                uniq = sorted({_decode(v) for v in vals.ravel()})
                conditions[name] = (
                    ", ".join(map(str, uniq[:6])) + ("…" if len(uniq) > 6 else "")
                )
        if conditions:
            meta["conditions"] = conditions

    # measured-value counts across every NXdata under the entry
    n_values = n_nonnan = n_arrays = 0
    for _p, g in iter_nxdata_groups(entry):
        _sn, ds = signal_dataset(g)
        if ds is None or ds.dtype.kind not in "fiu":
            continue
        n_arrays += 1
        a = np.asarray(ds[()], dtype=float)
        n_values += a.size
        n_nonnan += int(np.count_nonzero(~np.isnan(a)))
    meta.update(n_signal_arrays=n_arrays, n_values=n_values, n_nonnan=n_nonnan)
    meta["empty"] = n_values > 0 and n_nonnan == 0

    return meta


def describe_entry(meta: dict) -> str:
    """A one-line plain-text caption from an `entry_metadata` dict, for the
    markdown beside an inline figure."""
    bits = []
    if meta.get("material"):
        bits.append(f"**{meta['material']}**")
    if meta.get("method"):
        bits.append(meta["method"])
    if meta.get("provider"):
        bits.append(f"by {meta['provider']}")
    if meta.get("date"):
        bits.append(meta["date"])
    reps = meta.get("n_replicates")
    if reps:
        bits.append(", ".join(f"n={v} {k.lower()}" for k, v in reps.items()))
    conditions = meta.get("conditions") or {}
    dose = next(
        (
            f"{k} {v}"
            for k, v in conditions.items()
            if k.lower() not in _REPLICATE_AXES and "–" in v
        ),
        None,
    )
    if dose:
        bits.append(dose)
    if meta.get("empty"):
        bits.append("_(no non-NaN values)_")
    return " · ".join(bits) if bits else "_(no metadata)_"


def file_plottable(nxs_path):
    """(kind, payload) for the NXdata the file's own @default chain points
    at -- the first NXentry that resolves to something with real data --
    or None."""
    with h5py.File(nxs_path, "r") as h5file:
        for _name, entry in iter_entries(h5file):
            nxdata = default_nxdata(entry)
            if nxdata is None:
                continue
            sig_name, dataset = signal_dataset(nxdata)
            if dataset is None or dataset.dtype.kind not in "fiu":
                continue
            values = np.asarray(dataset[()], dtype=float)
            if not np.any(~np.isnan(values)):
                continue
            plot = resolve_plot(nxdata, sig_name, values)
            if plot is not None:
                return plot
    return None


# --------------------------------------------------------------------------
# plotting
# --------------------------------------------------------------------------


def _looks_log_scale(values) -> bool:
    """True if `values` are all strictly positive and span >= 2 decades
    (e.g. particle-size bins, 0.011..5000 um). A linear plot over that
    range squashes the whole peak into a sliver; log-x shows the curve.
    Data-driven, not endpoint-name-specific.

    A non-numeric axis (named controls, cell lines) has no scale to speak
    of and returns False rather than raising -- coercing it is what turned
    a categorical dose axis into `float(b' 1-propanol')`.
    """
    values = numeric_or_none(values)
    if values is None:
        return False
    values = values[~np.isnan(values)]
    if values.size < 2 or np.any(values <= 0):
        return False
    return (values.max() / values.min()) >= 100


def _tick_label(v):
    """"12.5" for a real number, a plain decoded string otherwise -- an
    axis is not always numeric (a cell-line / vehicle label), and ":g"
    crashes on a string; HDF5 hands text axis values back as `bytes`, so
    decode before str() or the label is the literal `b'...'` repr.
    """
    if isinstance(v, bytes):
        return v.decode(errors="replace").strip()
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v).strip()




# --- design tokens -------------------------------------------------------
#
# Chart chrome and the categorical slots come from one validated palette
# (blue / orange / aqua -- worst adjacent CVD deltaE 9.2, normal-vision 27.6
# against the light surface). Only the first slot is used for a single
# series; the rest are here for callers that overlay more than one.

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
CONTEXT = "#c9c8c2"  # de-emphasised individual runs

PAPER_RCPARAMS = {
    "figure.dpi": 140,
    "savefig.dpi": 300,
    "figure.figsize": (5.4, 3.3),
    "figure.facecolor": SURFACE,
    "figure.constrained_layout.use": True,
    "savefig.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "font.family": ["DejaVu Sans"],
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 9,
    "axes.labelcolor": INK,
    "axes.edgecolor": AXIS,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "grid.linestyle": "-",
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "xtick.labelcolor": INK,
    "ytick.labelcolor": INK,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "legend.fontsize": 8,
    "legend.frameon": False,
    "legend.labelcolor": INK,
    "lines.linewidth": 2.0,
    "lines.solid_capstyle": "round",
    "lines.solid_joinstyle": "round",
    "lines.markersize": 4.5,
    "image.cmap": "Blues",
}

# A marker per point is right for a dose series (a handful of real,
# measured levels) and wrong for a spectrum (hundreds of samples), where
# the markers swamp the line they are meant to sit on.
_DENSE_POINTS = 40


def apply_paper_style(extra: dict | None = None):
    """Set the print-oriented rcParams profile. Call once at the top of a
    notebook; `extra` overrides individual keys."""
    import matplotlib as mpl

    mpl.rcParams.update(PAPER_RCPARAMS)
    if extra:
        mpl.rcParams.update(extra)


def _marker_size(n_points: int) -> float:
    """Bigger dots when there are few of them. Three replicate points on an
    empty axis need presence; forty need restraint."""
    if n_points <= 6:
        return 7.0
    if n_points <= 15:
        return 5.5
    return 4.5


def _legend(ax):
    """A legend placed out of the data's way. `loc="best"` routinely lands
    on top of a reference-line label in the top-right margin."""
    ax.legend(
        loc="upper left", bbox_to_anchor=(0.0, -0.16), ncol=3,
        handlelength=1.6, columnspacing=1.4, borderaxespad=0.0,
    )


def _finish(ax, meta=None, title=None, y_label=None, x_label=None):
    """Common chrome: labels, the identity line, a horizontal-only grid."""
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)
    ax.grid(axis="y")
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=3, width=0.8)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS)

    identity = _identity_line(meta) if meta else None
    if title and identity:
        ax.set_title(title, loc="left", fontsize=9, color=INK, pad=14)
        ax.text(
            0, 1.012, identity, transform=ax.transAxes,
            fontsize=8, color=INK_MUTED, va="bottom", ha="left",
        )
    elif title or identity:
        ax.set_title(
            title or identity, loc="left",
            fontsize=9, color=INK if title else INK_MUTED, pad=6,
        )


def _identity_line(meta: dict) -> str:
    """Material - method - provider - n, as one muted line above the plot,
    so a figure lifted into a document still says what it shows."""
    bits = []
    if meta.get("material"):
        bits.append(str(meta["material"]))
    if meta.get("method"):
        bits.append(str(meta["method"]))
    if meta.get("provider"):
        bits.append(str(meta["provider"]))
    for name, count in (meta.get("n_replicates") or {}).items():
        bits.append(f"n={count} {str(name).lower()}")
    return "  ·  ".join(bits)


def _draw_series(ax, p, meta=None, title=None):
    """A response against one x axis: continuous curve, or categorical
    strip. Replicates ride behind the mean as context, never as their own
    competing series."""
    x = np.asarray(p["x"], dtype=float)
    y = np.asarray(p["y"], dtype=float)
    grid = p.get("grid")
    order = np.argsort(x)
    x, y = x[order], y[order]
    if grid is not None:
        grid = np.asarray(grid)[order]

    dense = len(x) > _DENSE_POINTS
    marker = "" if dense else "o"
    # A bare positional "index" is not an ordering the data claims -- the
    # samples behind it are unrelated, so a connecting line would imply a
    # sequence that does not exist. Points only.
    positional = p.get("x_name") is None
    linestyle = "none" if positional else "-"
    if positional:
        marker = "o"

    if grid is not None and grid.ndim == 2 and grid.shape[1] > 1:
        # Emphasis: the mean is the point, the individual runs are context.
        sd = np.nanstd(grid, axis=1)
        ax.fill_between(
            x, y - sd, y + sd, color=SERIES[0], alpha=0.10, lw=0, zorder=2,
            label="±SD",
        )
        for j in range(grid.shape[1]):
            ax.plot(
                x, grid[:, j], color=CONTEXT, lw=0.9, zorder=1,
                label="individual runs" if j == 0 else None,
            )
        ax.plot(
            x, y, marker=marker, linestyle=linestyle, color=SERIES[0], zorder=3,
            markersize=_marker_size(len(x)),
            markerfacecolor=SERIES[0], markeredgecolor=SURFACE,
            markeredgewidth=1.2, label="mean",
        )
        _legend(ax)
    else:
        ax.plot(
            x, y, marker=marker, linestyle=linestyle, color=SERIES[0],
            markersize=_marker_size(len(x)),
            markerfacecolor=SERIES[0], markeredgecolor=SURFACE,
            markeredgewidth=1.2, zorder=3,
        )

    if p.get("categorical") and p.get("cat_labels"):
        ax.set_xticks(x)
        ax.set_xticklabels(
            [p["cat_labels"][i] for i in order], rotation=30, ha="right"
        )
        ax.grid(axis="x", visible=False)
    elif _looks_log_scale(x):
        ax.set_xscale("log")

    # FTIR and other wavenumber axes are conventionally read high -> low.
    x_name = str(p.get("x_name") or "")
    if "wavenumber" in x_name.lower():
        ax.invert_xaxis()

    # Named controls split off a mixed dose axis: shown as reference marks
    # on the right margin rather than pretending to be concentrations.
    cat_labels, cat_y = p.get("cat_labels"), p.get("cat_y")
    if not p.get("categorical") and cat_labels and cat_y is not None:
        _add_control_marks(ax, cat_labels, np.asarray(cat_y, dtype=float))

    _finish(ax, meta=meta, title=title,
            x_label=p.get("x_label"), y_label=p.get("y_label"))


def _add_control_marks(ax, labels, values):
    """Named controls (vehicle, blank, IC) as labelled reference lines --
    they belong to the same response scale but have no position on a
    concentration axis."""
    for label, value in zip(labels, np.atleast_1d(values)):
        if not np.isfinite(value):
            continue
        ax.axhline(value, color=SERIES[1], lw=1.0, ls=(0, (4, 3)), zorder=1.5)
        ax.annotate(
            str(label), xy=(1.0, value), xycoords=("axes fraction", "data"),
            xytext=(4, 0), textcoords="offset points",
            fontsize=7.5, color=INK_MUTED, va="center", ha="left",
            annotation_clip=False,
        )


def _draw_replicates(ax, p, meta=None, title=None):
    """No independent variable -- only repeats. Points about a mean line;
    never a trend line through run numbers."""
    y = np.asarray(p["y"], dtype=float)
    labels = p.get("rep_labels") or [str(i + 1) for i in range(len(y))]
    x = np.arange(len(y), dtype=float)

    mean = float(np.nanmean(y)) if y.size else np.nan
    sd = float(np.nanstd(y)) if y.size else np.nan
    if np.isfinite(mean):
        ax.axhspan(mean - sd, mean + sd, color=SERIES[0], alpha=0.08, lw=0, zorder=1)
        ax.axhline(mean, color=SERIES[0], lw=1.6, zorder=2,
                   label=f"mean {mean:.3g} ± {sd:.2g}")
    ax.plot(
        x, y, linestyle="none", marker="o",
        markersize=_marker_size(len(y)),
        markerfacecolor=SERIES[0], markeredgecolor=SURFACE,
        markeredgewidth=1.4, zorder=3,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlim(-0.6, len(y) - 0.4)
    if np.isfinite(mean):
        _legend(ax)

    rep = str(p.get("rep_name") or "run")
    _finish(ax, meta=meta, title=title,
            x_label=rep, y_label=p.get("y_label"))


def _draw_heatmap(ax, p, meta=None, title=None):
    grid = np.asarray(p["grid"], dtype=float)
    im = ax.imshow(grid.T, aspect="auto", origin="lower", interpolation="nearest")
    cbar = ax.figure.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label(p.get("value_label") or "", color=INK, fontsize=8)
    cbar.ax.tick_params(labelsize=8, color=AXIS, labelcolor=INK)
    cbar.outline.set_edgecolor(AXIS)
    cbar.outline.set_linewidth(0.8)

    x_values, y_values = p.get("x"), p.get("y")
    if x_values is not None and len(x_values) == grid.shape[0]:
        ax.set_xticks(range(len(x_values)))
        ax.set_xticklabels(
            [_tick_label(v) for v in x_values], rotation=30, ha="right"
        )
    if y_values is not None and len(y_values) == grid.shape[1]:
        ax.set_yticks(range(len(y_values)))
        ax.set_yticklabels([_tick_label(v) for v in y_values])
    ax.grid(False)
    _finish(ax, meta=meta, title=title,
            x_label=p.get("x_label"), y_label=p.get("y_label"))
    ax.grid(False)


_DRAW = {
    "series": _draw_series,
    "replicates": _draw_replicates,
    "heatmap": _draw_heatmap,
}


def draw(ax, kind, payload, *, title=None, meta=None):
    """Render one `resolve_plot` result onto `ax`.

    `kind` picks the form, which is decided by what the data actually is
    (see resolve_plot): a response against a real independent variable is a
    curve; bare repeats are points about a mean; two crossed conditions are
    a heatmap. `meta` (an `entry_metadata` dict) adds the identity line.
    """
    fn = _DRAW.get(kind)
    if fn is None:
        raise ValueError(f"unknown plot kind: {kind!r}")
    fn(ax, payload, meta=meta, title=title)


# --------------------------------------------------------------------------
# rendering a summary figure on demand
# --------------------------------------------------------------------------


def figure_png(nxs_path, entry_name=None, *, dpi=150) -> bytes | None:
    """Render one entry's default plot and return it as PNG bytes.

    `entry_name` picks the entry; by default the first one that resolves to
    something with real data -- the same rule `file_plottable` follows, so
    the picture is the one a viewer would show.

    Rendered on demand, for a viewer or a thumbnail service. The result is
    deliberately NOT written back into the .nxs: a figure is derived from
    the data, it goes stale the moment the plotting code changes, and an
    archival measurement file should not carry ~40KB of it per entry.
    """
    import matplotlib
    import matplotlib.pyplot as plt

    matplotlib.use("Agg", force=False)
    apply_paper_style()

    with h5py.File(nxs_path, "r") as h5file:
        entries = list(iter_entries(h5file))
        if entry_name is not None:
            entries = [(n, e) for n, e in entries if n == entry_name]
        for _name, entry in entries:
            nxdata = default_nxdata(entry)
            if nxdata is None:
                continue
            sig_name, dataset = signal_dataset(nxdata)
            if dataset is None or dataset.dtype.kind not in "fiu":
                continue
            values = np.asarray(dataset[()], dtype=float)
            if not np.any(~np.isnan(values)):
                continue
            plot = resolve_plot(nxdata, sig_name, values)
            if plot is None:
                continue
            meta = entry_metadata(h5file, entry)
            fig, ax = plt.subplots()
            try:
                draw(ax, plot[0], plot[1], meta=meta)
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
                return buffer.getvalue()
            except Exception:  # noqa: BLE001 -- a thumbnail is never fatal
                return None
            finally:
                plt.close(fig)
    return None
