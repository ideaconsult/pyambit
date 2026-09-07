"""nexus_plot: reading a written .nxs back for overview / figure use."""

import numpy as np
import nexusformat.nexus.tree as nx
import pytest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import pyambit.datamodel as mx
from pyambit import nexus_writer  # noqa: F401  (registers to_nexus)
from pyambit import nexus_plot


def _write_file(tmp_path, effects, *, provider="Test Lab", material="Sample 1",
                investigation=True):
    pa = mx.ProtocolApplication(
        uuid="pa1",
        protocol=mx.Protocol(
            topcategory="TOX",
            category=mx.EndpointCategory(code="NPO_1339_SECTION"),
            endpoint="Dose response - demo",
            guideline=[],
        ),
        effects=effects,
        parameters={"E.method": "Dose response - demo"},
        citation=mx.Citation(owner=provider, title="10.1234/demo", year=2025),
        # Real converter output always carries one (it is what groups the
        # entries of a study together), and it is where a summary figure
        # gets embedded.
        investigation_uuid=(
            mx.Investigation(
                uuid="inv1", title="Demo investigation",
                description="A demo assay, run for the test suite.",
            )
            if investigation
            else None
        ),
        owner=mx.SampleLink(
            substance=mx.Sample(uuid="s1"), company=mx.Company(name=provider)
        ),
    )
    substance = mx.SubstanceRecord(
        i5uuid="s1",
        name=material,
        publicname=material,
        ownerName="DEMO_PROJECT",
        ownerUUID="DEMO_PROJECT",
        study=[pa],
    )
    root = nx.NXroot()
    mx.Substances(substance=[substance]).to_nexus(root, hierarchy=False)
    path = tmp_path / "demo.nxs"
    root.save(str(path), mode="w")
    return path


def _dose_response_effect():
    """3 concentrations x 2 replicates, one time point -> shape (3, 1, 2)."""
    signal = np.array(
        [[[1.0, 1.2]], [[2.0, 2.4]], [[3.1, 2.9]]], dtype=float
    )
    return mx.EffectArray(
        endpoint="Fold change",
        endpointtype="AGGREGATED",
        signal=mx.ValueArray(values=signal, unit="a.u."),
        axes={
            "concentration": mx.ValueArray(
                values=np.array([0.0, 10.0, 100.0]), unit="ug/mL"
            ),
            "time": mx.ValueArray(values=np.array([24.0]), unit="h"),
            "Replicate": mx.ValueArray(values=np.array([1.0, 2.0])),
        },
        conditions={},
    )


def test_reads_metadata_from_written_entry(tmp_path):
    import h5py

    path = _write_file(tmp_path, [_dose_response_effect()], material="TiO2")
    with h5py.File(path, "r") as h5:
        (name, entry), = list(nexus_plot.iter_entries(h5))
        meta = nexus_plot.entry_metadata(h5, entry)

    assert meta["material"] == "TiO2"
    assert meta["provider"] == "Test Lab"
    assert meta["method"] == "Dose response - demo"
    # The investigation label -- nexus_writer stores `description` as a
    # FIELD on investigation/<uuid>, and the entry here references it by
    # collection_identifier only (no NXentry/investigation link), so this
    # exercises the by-uuid fallback in entry_metadata.
    assert meta["investigation"] == "Demo investigation"
    assert meta["investigation_description"] == (
        "A demo assay, run for the test suite."
    )
    assert meta["n_nonnan"] == 6
    assert not meta["empty"]
    # concentration range captured; Replicate recognised as a replicate axis
    assert meta["conditions"]["concentration"] == "0–100"
    assert meta["n_replicates"] == {"Replicate": 2}
    caption = nexus_plot.describe_entry(meta)
    assert "TiO2" in caption and "n=2" in caption


def test_resolve_plot_squeezes_and_keeps_replicate_axis(tmp_path):
    path = _write_file(tmp_path, [_dose_response_effect()])
    plot = nexus_plot.file_plottable(path)
    assert plot is not None
    kind, p = plot
    assert kind == "series"
    # time (length-1) squeezed away, concentration is x, Replicate retained
    assert p["x_label"].startswith("concentration")
    assert list(p["x"]) == [0.0, 10.0, 100.0]
    assert p["rep_name"] == "Replicate"
    assert p["grid"].shape == (3, 2)
    assert p["y"] == pytest.approx([1.1, 2.2, 3.0])
    assert p["categorical"] is False


def test_draw_series_with_replicate_band_runs(tmp_path):
    path = _write_file(tmp_path, [_dose_response_effect()])
    plot = nexus_plot.file_plottable(path)
    import h5py

    with h5py.File(path, "r") as h5:
        (name, entry), = list(nexus_plot.iter_entries(h5))
        meta = nexus_plot.entry_metadata(h5, entry)

    nexus_plot.apply_paper_style()
    fig, ax = plt.subplots()
    nexus_plot.draw(ax, plot[0], plot[1], title="demo", meta=meta)
    # the per-replicate context lines + the mean line
    assert len(ax.lines) >= 3
    assert ax.get_xlabel().startswith("concentration")
    plt.close(fig)


def _replicates_only_effect():
    """A response measured only across repeats -- no independent variable."""
    return mx.EffectArray(
        endpoint="PCR efficiency",
        endpointtype="RAW_DATA",
        signal=mx.ValueArray(values=np.array([2.08, 1.85, 1.79]), unit="%"),
        axes={"Experiment": mx.ValueArray(values=np.array([1.0, 2.0, 3.0]))},
        conditions={},
    )


def test_replicate_only_axis_is_not_drawn_as_a_trend(tmp_path):
    """Run number is nominal: a line across it invents a trend. The form
    must be points about a mean, not a curve."""
    path = _write_file(tmp_path, [_replicates_only_effect()])
    kind, p = nexus_plot.file_plottable(path)
    assert kind == "replicates"
    assert p["rep_name"] == "Experiment"
    assert p["y"] == pytest.approx([2.08, 1.85, 1.79])

    nexus_plot.apply_paper_style()
    fig, ax = plt.subplots()
    nexus_plot.draw(ax, kind, p)
    # the data itself is drawn with no connecting line
    data_lines = [
        ln for ln in ax.lines
        if str(ln.get_linestyle()).lower() == "none" and ln.get_marker() == "o"
    ]
    assert data_lines, "replicate points must not be joined by a line"
    assert ax.get_xlabel() == "Experiment"
    plt.close(fig)


def test_mixed_dose_axis_splits_controls_off(tmp_path):
    """A dose axis that also names its controls is not one scale: the
    numeric doses stay the curve, the named entries become references."""
    signal = np.array([1.0, 9.0, 2.0, 3.0], dtype=float)
    effect = mx.EffectArray(
        endpoint="MCP-1",
        endpointtype="RAW_DATA",
        signal=mx.ValueArray(values=signal, unit="pg/mL"),
        axes={
            "Dose": mx.ValueArray(
                values=np.array(["0.003", "1-propanol", "0.017", "0.1"], dtype=object)
            )
        },
        conditions={},
    )
    path = _write_file(tmp_path, [effect])
    kind, p = nexus_plot.file_plottable(path)
    assert kind == "series"
    assert p["categorical"] is False
    assert list(p["x"]) == pytest.approx([0.003, 0.017, 0.1])
    assert p["cat_labels"] == ["1-propanol"]
    assert list(p["cat_y"]) == pytest.approx([9.0])

    nexus_plot.apply_paper_style()
    fig, ax = plt.subplots()
    nexus_plot.draw(ax, kind, p)  # must not raise on the mixed axis
    plt.close(fig)


def test_figure_png_renders_on_demand(tmp_path):
    """A viewer / thumbnail service asks for the figure and gets PNG bytes.
    Nothing is written back to the file -- the .nxs carries measurements,
    not a rendering of them."""
    import h5py

    path = _write_file(tmp_path, [_dose_response_effect()])
    before = path.stat().st_size

    png = nexus_plot.figure_png(path)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    assert path.stat().st_size == before
    with h5py.File(path, "r") as h5:
        (inv_name,) = list(h5["investigation"])
        assert "image" not in h5["investigation"][inv_name]


def test_figure_png_is_none_when_nothing_is_plottable(tmp_path):
    nan_effect = mx.EffectArray(
        endpoint="all nan",
        endpointtype="RAW_DATA",
        signal=mx.ValueArray(values=np.full(3, np.nan), unit="a.u."),
        axes={"x": mx.ValueArray(values=np.array([0.0, 1.0, 2.0]))},
        conditions={},
    )
    path = _write_file(tmp_path, [nan_effect])
    assert nexus_plot.figure_png(path) is None


def test_labeled_does_not_duplicate_a_unit_already_in_the_name(tmp_path):
    import h5py

    effect = mx.EffectArray(
        endpoint="Transmission",
        endpointtype="RAW_DATA",
        signal=mx.ValueArray(values=np.array([1.0, 2.0]), unit="%"),
        axes={
            "Wavenumber (cm-1)": mx.ValueArray(
                values=np.array([700.0, 800.0]), unit="cm-1"
            )
        },
        conditions={},
    )
    path = _write_file(tmp_path, [effect])
    kind, p = nexus_plot.file_plottable(path)
    assert p["x_label"] == "Wavenumber (cm-1)"  # not "... (cm-1) (cm-1)"


def test_tick_label_decodes_bytes():
    assert nexus_plot._tick_label(b" 1-propanol") == "1-propanol"
    assert nexus_plot._tick_label(12.5) == "12.5"
    assert nexus_plot._tick_label("IC") == "IC"


def test_investigation_helpers_read_the_shared_label(tmp_path):
    import h5py

    path = _write_file(tmp_path, [_dose_response_effect()])
    with h5py.File(path, "r") as h5:
        labels = dict(nexus_plot.iter_investigations(h5))
        (name, entry), = list(nexus_plot.iter_entries(h5))
        meta = nexus_plot.entry_metadata(h5, entry)

    assert labels == {
        "inv1": {
            "title": "Demo investigation",
            "description": "A demo assay, run for the test suite.",
        }
    }

    # one study here; folded onto its group with the label carried through
    summary = nexus_plot.summarize_investigations([(meta, "demo_assay")])
    assert summary == {
        "inv1": {
            "title": "Demo investigation",
            "description": "A demo assay, run for the test suite.",
            "groups": ["demo_assay"],
            "n_studies": 1,
        }
    }


def test_summarize_investigations_folds_across_files():
    # A bare-uuid study (no label yet) seen before the labelled one must not
    # win: fields are taken the first time they are non-empty.
    bare = {"investigation_uuid": "inv9"}
    labelled = {
        "investigation_uuid": "inv9",
        "investigation": "Late label",
        "investigation_description": "filled in by a later entry",
    }
    summary = nexus_plot.summarize_investigations(
        [(bare, "a"), (labelled, "b"), (bare, "a")]
    )
    assert summary["inv9"]["title"] == "Late label"
    assert summary["inv9"]["description"] == "filled in by a later entry"
    assert summary["inv9"]["groups"] == ["a", "b"]
    assert summary["inv9"]["n_studies"] == 3


def test_empty_signal_flagged_not_raised(tmp_path):
    nan_effect = mx.EffectArray(
        endpoint="all nan",
        endpointtype="RAW_DATA",
        signal=mx.ValueArray(values=np.full(3, np.nan), unit="a.u."),
        axes={"x": mx.ValueArray(values=np.array([0.0, 1.0, 2.0]))},
        conditions={},
    )
    path = _write_file(tmp_path, [nan_effect])
    import h5py

    with h5py.File(path, "r") as h5:
        (name, entry), = list(nexus_plot.iter_entries(h5))
        meta = nexus_plot.entry_metadata(h5, entry)
    assert meta["empty"] is True
    assert nexus_plot.file_plottable(path) is None
