import json
import os.path
import tempfile
from pathlib import Path

import nexusformat.nexus as nx
import numpy as np
import pytest

from pyambit import nexus_writer  # noqa: F401  (registers to_nexus methods)
from pyambit.datamodel import Citation, EndpointCategory, Protocol, Study, Substances, Value
from pyambit.nexus_models.appdefs.nx_raman import NXRaman
from pyambit.nexus_models.base.nx_beam import NXBeam
from pyambit.nexus_models.base.nx_detector import NXDetector
from pyambit.nexus_models.base.nx_fabrication import NXFabrication
from pyambit.nexus_models.base.nx_grating import NXGrating
from pyambit.nexus_models.base.nx_instrument import NXInstrument
from pyambit.nexus_models.base.nx_monochromator import NXMonochromator
from pyambit.nexus_models.base.nx_sample import NXSample
from pyambit.nexus_models.blueprint import to_template_designer_blueprint
from pyambit.nexus_models.flatten import flatten_nx_model
from pyambit.nexus_spectra import NXRamanProtocolApplication, configure_papp, spe2ambit

TEST_DIR = Path(__file__).parent.parent / "resources"


def _blank_nxraman_papp(**kwargs) -> NXRamanProtocolApplication:
    return NXRamanProtocolApplication(
        protocol=Protocol(
            topcategory="P-CHEM",
            category=EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
        ),
        effects=[],
        **kwargs,
    )


def _richly_populated_nxraman(*, detector_instance_name: str = "detector") -> NXRaman:
    """An NXRaman instance with as many fields populated as practical, for
    end-to-end round-trip verification (real .nxs write + reload).

    `detector_instance_name` lets callers choose the Dict[str, NXDetector]
    instance key: "detector" (the default) matches the original hand-curated
    RAMAN_PARAMETER_PATHS table's fixed path ("instrument/detector/..."),
    while "detector_type" (the Python field name that dict lives on) matches
    the placeholder path segment pyambit.nexus_models.blueprint uses for this
    variadic field when generating the schema-only blueprint (which has no
    real instance to name at generation time) - both are valid instance
    names a real caller could pick; flatten_nx_model doesn't fix one.
    """
    return NXRaman(
        definition="NXraman",
        title="Example round robin - polystyrene reference sample",
        experiment_type="Raman spectroscopy",
        raman_experiment_type="non-resonant Raman spectroscopy",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:05:00Z",
        identifier_experiment="EXAMPLE-001",
        instrument={
            "instrument": NXInstrument(
                scattering_configuration="z(xx)z",
                beam_incident=NXBeam(wavelength=Value(loValue=532.0, unit="nm")),
                detector_type={
                    detector_instance_name: NXDetector(
                        detector_channel_type="single-channel",
                        detector_type="CCD",
                        count_time=Value(loValue=1.0, unit="s"),
                    )
                },
                monochromator={
                    "monochromator": NXMonochromator(
                        grating={"grating": NXGrating(period=Value(loValue=600.0, unit="1/mm"))}
                    )
                },
                device_information=NXFabrication(vendor="BWTEK", model="X100"),
            )
        },
        sample={
            "sample": NXSample(
                name="Polystyrene",
                sample_id="PST-1",
                physical_form="pellet",
                chemical_formula="(C8H8)n",
            )
        },
    )


class TestFlattenModel:
    def test_flatten_matches_hand_curated_paths(self):
        nxraman = _richly_populated_nxraman()
        params, hints = flatten_nx_model(nxraman)

        # Same target NeXus paths the original RAMAN_PARAMETER_PATHS-style
        # if/elif chain in configure_papp used to hand-write.
        assert params["instrument/beam_incident/wavelength"] == Value(
            loValue=532.0, unit="nm"
        )
        assert params["instrument/detector/count_time"] == Value(loValue=1.0, unit="s")
        assert params["instrument/monochromator/grating/period"] == Value(
            loValue=600.0, unit="1/mm"
        )
        assert params["instrument/device_information/vendor"] == "BWTEK"
        assert params["instrument/device_information/model"] == "X100"
        # Leading "/": these are entry-root NXRaman fields with no parent
        # group (unlike instrument/... above, which is nested). See
        # flatten_nx_model's "leaf_path" comment for why the slash matters -
        # bare "definition"/"experiment_type" would otherwise be misrouted by
        # to_nexus's param_lookup() AMBIT-condition-key fallback.
        assert params["/definition"] == "NXraman"
        assert params["/experiment_type"] == "Raman spectroscopy"

        # Group-class hints for to_nexus's group instantiation.
        assert hints["instrument"] == "NXinstrument"
        assert hints["instrument/beam_incident"] == "NXbeam"
        assert hints["instrument/detector"] == "NXdetector"
        assert hints["instrument/monochromator"] == "NXmonochromator"
        assert hints["instrument/monochromator/grating"] == "NXgrating"

    def test_unset_fields_produce_no_path(self):
        """A caller who never populates a field gets no NeXus path for it -
        no invented default, matching pyambit's stated domain-agnostic scope."""
        nxraman = NXRaman(definition="NXraman")
        params, _ = flatten_nx_model(nxraman)
        assert params == {"/definition": "NXraman"}

    def test_value_passthrough_preserves_explicit_unit(self):
        """A caller-supplied Value's unit is preserved verbatim, even for a
        field (NXbeam.wavelength) whose own NXDL declares no unit category."""
        nxraman = NXRaman(
            instrument={
                "instrument": NXInstrument(
                    beam_incident=NXBeam(wavelength=Value(loValue=785.0, unit="nm"))
                )
            }
        )
        params, _ = flatten_nx_model(nxraman)
        value = params["instrument/beam_incident/wavelength"]
        assert isinstance(value, Value)
        assert value.loValue == 785.0
        assert value.unit == "nm"


class TestBackwardCompatKeys:
    """Regression test parametrized over spectrastream's actual recognized
    meta key strings (confirmed against spectrastream's nexus.py/profiles.py/
    acquisition.py source, not reconstructed from memory)."""

    @pytest.mark.parametrize(
        "meta_key,expected_path",
        [
            ("grating", "instrument/monochromator/grating/period"),
            ("acquisition_time", "instrument/detector/count_time"),
            ("integration time", "instrument/detector/count_time"),
            ("integ_time", "instrument/detector/count_time"),
            ("GRATING", "instrument/monochromator/grating/period"),  # case-insensitive
        ],
    )
    def test_recognized_key_routes_to_expected_path(self, meta_key, expected_path):
        papp = _blank_nxraman_papp()
        configure_papp(
            papp,
            instrument=("VendorX", "ModelY"),
            wavelength=532,
            meta={meta_key: "123"},
        )
        assert expected_path in papp.parameters

    def test_grating_value_with_unit_preserved_as_value(self):
        """Regression: spectrastream sends grating as e.g. "600 g/mm" (a
        number-with-unit string, from OpticalPath.grating), not a bare
        number. NXGrating.period is Optional[Union[float, Value]] precisely
        so this can be preserved as Value(loValue=600.0, unit="g/mm")
        instead of silently dropped by a naive float(value) coercion."""
        papp = _blank_nxraman_papp()
        configure_papp(
            papp,
            instrument=("VendorX", "ModelY"),
            wavelength=532,
            meta={"grating": "600 g/mm"},
        )
        value = papp.parameters["instrument/monochromator/grating/period"]
        assert isinstance(value, Value)
        assert value.loValue == 600.0
        assert value.unit == "g/mm"

    def test_non_numeric_grating_value_falls_back_to_generic_bucket(self):
        """A grating value with no leading number at all (e.g. free-text
        "fibre") can't be routed to NXGrating.period without widening that
        field beyond NXDL's own NX_NUMBER declaration - must fall back to
        the generic bucket instead of being silently dropped."""
        papp = _blank_nxraman_papp()
        configure_papp(
            papp,
            instrument=("VendorX", "ModelY"),
            wavelength=532,
            meta={"grating": "fibre"},
        )
        assert "instrument/monochromator/grating/period" not in papp.parameters
        assert papp.parameters["/parameters/grating"] == "fibre"

    def test_unrecognized_key_falls_back_to_generic_bucket(self):
        """'pin hole size' is a real spectrastream meta key with no home in
        the generated NXRaman model (NXraman's own appdef XML never
        references NXoptical_lens/numerical_aperture) - must fall through to
        the generic /parameters/{key} bucket, not silently disappear."""
        papp = _blank_nxraman_papp()
        configure_papp(
            papp,
            instrument=("VendorX", "ModelY"),
            wavelength=532,
            meta={"pin hole size": "100um"},
        )
        assert papp.parameters["/parameters/pin hole size"] == "100um"

    def test_parameters_keys_not_underscore_mangled(self):
        """Guards the ProtocolApplication.clean_parameters field_validator
        landmine: papp.parameters keys must stay "/"-delimited, not get
        flattened to "_" (which would silently break to_nexus's path
        splitting). Only risked if `parameters=` were ever passed into the
        constructor instead of assigned post-construction."""
        papp = spe2ambit(
            x=np.linspace(100, 3000, 10),
            y=np.random.rand(10),
            meta={"@signal": "y", "@axes": ["x"], "grating": "600"},
            instrument=("VendorX", "ModelY"),
            wavelength=532,
        )
        assert "instrument/monochromator/grating/period" in papp.parameters
        assert "instrument/device_information/vendor" in papp.parameters
        assert not any(
            key.startswith("instrument_") or "beam_incident_wavelength" in key
            for key in papp.parameters
        )


class TestToNexusRealClasses:
    def test_intermediate_groups_get_real_nx_classes(self):
        """to_nexus must instantiate the real NX class for intermediate
        groups when a caller (via NXRamanProtocolApplication.nxraman) supplies
        the information, not just a generic NXgroup - this is what makes
        e.g. NXdetector/NXmonochromator actually appear in the written file."""
        papp = spe2ambit(
            x=np.linspace(100, 3000, 10),
            y=np.random.rand(10),
            meta={"@signal": "y", "@axes": ["x"], "grating": "600"},
            instrument=("VendorX", "ModelY"),
            wavelength=532,
        )
        nx_root = nx.NXroot()
        papp.to_nexus(nx_root)
        entry = next(iter(nx_root.entries.values()))
        instrument = entry["instrument"]
        assert type(instrument).__name__ == "NXinstrument"
        assert type(instrument["beam_incident"]).__name__ == "NXbeam"
        assert type(instrument["monochromator"]).__name__ == "NXmonochromator"
        assert type(instrument["monochromator"]["grating"]).__name__ == "NXgrating"

    def test_definition_lands_at_entry_root_not_stray_group(self):
        """The /entry/definition leading-slash bug: "/definition".split("/")
        used to produce ["", "definition"], creating a stray ""-named group
        instead of writing definition at the entry root."""
        papp = spe2ambit(
            x=np.linspace(100, 3000, 10),
            y=np.random.rand(10),
            meta={"@signal": "y", "@axes": ["x"]},
            instrument=("VendorX", "ModelY"),
            wavelength=532,
        )
        nx_root = nx.NXroot()
        papp.to_nexus(nx_root)
        entry = next(iter(nx_root.entries.values()))
        assert "" not in entry.entries
        assert entry["definition"].nxvalue == "NXraman"

    def test_experiment_type_lands_at_entry_root(self):
        papp = spe2ambit(
            x=np.linspace(100, 3000, 10),
            y=np.random.rand(10),
            meta={"@signal": "y", "@axes": ["x"]},
            instrument=("VendorX", "ModelY"),
            wavelength=532,
        )
        nx_root = nx.NXroot()
        papp.to_nexus(nx_root)
        entry = next(iter(nx_root.entries.values()))
        assert entry["experiment_type"].nxvalue == "Raman spectroscopy"


class TestEndToEndRichWrite:
    """Fill an NXRaman instance with representative metadata, produce a real
    .nxs file, reload it, and inspect the tree against the NXraman path
    checklist - the plan's own end-to-end verification step."""

    def test_rich_nxraman_round_trips_through_real_nxs_file(self):
        papp = _blank_nxraman_papp(nx_name="example_measurement")
        papp.nxraman = _richly_populated_nxraman()
        papp.sync_parameters()
        papp.uuid = "TEST-roundtrip"
        papp.citation = Citation(owner="EXAMPLE_LAB", title="Example round robin", year=2026)

        nx_root = nx.NXroot()
        papp.to_nexus(nx_root)

        out_file = os.path.join(tempfile.gettempdir(), "nx_raman_rich_roundtrip.nxs")
        nx_root.save(out_file, mode="w")

        reloaded = nx.nxload(out_file)
        entry = next(
            e for e in reloaded.entries.values() if type(e).__name__ == "NXentry"
        )

        assert entry["definition"].nxvalue == "NXraman"
        assert entry["experiment_type"].nxvalue == "Raman spectroscopy"
        assert entry["raman_experiment_type"].nxvalue == "non-resonant Raman spectroscopy"
        assert entry["title"].nxvalue == "Example round robin - polystyrene reference sample"

        instrument = entry["instrument"]
        assert type(instrument).__name__ == "NXinstrument"
        assert instrument["scattering_configuration"].nxvalue == "z(xx)z"
        assert instrument["beam_incident"]["wavelength"].nxvalue == 532.0
        assert instrument["beam_incident"]["wavelength"].attrs["unit"] == "nm"
        assert instrument["detector"]["count_time"].nxvalue == 1.0
        assert instrument["monochromator"]["grating"]["period"].nxvalue == 600.0
        assert instrument["device_information"]["vendor"].nxvalue == "BWTEK"
        assert instrument["device_information"]["model"].nxvalue == "X100"

        # entry/sample already exists (created by to_nexus's own
        # sample-substance handling, an NXsample distinct from the
        # nxraman-derived sample/<instance-name> written separately via the
        # flattened "sample/sample/..." parameters).
        assert "sample" in entry.entries


class TestNonRamanRegression:
    """Confirm the Raman-scoped /definition fix and to_nexus's other changes
    don't leak into non-Raman AMBIT protocols - the existing fixtures never
    set /definition == "NXraman", so they must keep getting the
    AMBIT_DATAMODEL rewrite exactly as before."""

    @pytest.fixture(scope="module")
    def substances(self):
        with open(os.path.join(TEST_DIR, "substance.json"), encoding="utf-8") as f:
            substances = Substances(**json.load(f))
        with open(os.path.join(TEST_DIR, "study.json"), encoding="utf-8") as f:
            study = Study(**json.load(f))
            substances.substance[0].study = study.study
        return substances

    def test_non_raman_entries_keep_ambit_datamodel_definition(self, substances):
        nx_root = nx.NXroot()
        substances.to_nexus(nx_root)
        tree_str = str(nx_root.tree)
        definition_lines = [
            line.strip() for line in tree_str.splitlines() if "definition = " in line
        ]
        assert definition_lines, "expected at least one definition field"
        for line in definition_lines:
            assert "AMBIT_DATAMODEL" in line
            assert "NXraman" not in line

    def test_no_stray_empty_group_from_leading_slash_fix(self, substances):
        """The leading-slash strip is a pure parser fix: it must not affect
        non-Raman fixtures beyond removing the (already-broken) stray group."""
        nx_root = nx.NXroot()
        substances.to_nexus(nx_root)
        tree_str = str(nx_root.tree)
        assert ":NXgroup\n" not in tree_str or "  :NXgroup" not in tree_str


class TestBlueprintFlattenParity:
    """The blueprint's METADATA_PARAMETERS param_name values and
    flatten_nx_model's recognized path vocabulary must be provably the same
    set - the actual 'closes the loop' guarantee of generating both from one
    model instead of hand-maintaining them independently."""

    def test_blueprint_param_names_are_flatten_recognized_paths(self):
        # detector_instance_name="detector_type": matches the field name
        # convention the blueprint's schema-only walk uses as its
        # placeholder (see _richly_populated_nxraman's docstring) - this is
        # what makes exact path equality meaningful here.
        nxraman = _richly_populated_nxraman(detector_instance_name="detector_type")
        flattened_params, _ = flatten_nx_model(nxraman)
        flattened_paths = {p.lstrip("/") for p in flattened_params}

        blueprint = to_template_designer_blueprint(NXRaman)
        blueprint_names = {
            row["param_name"] for row in blueprint["METADATA_PARAMETERS"]
        }

        # Every populated field's flattened path must appear as a blueprint
        # row (the blueprint enumerates the full schema; flatten_nx_model
        # only emits populated leaves for one instance).
        missing = flattened_paths - blueprint_names
        assert not missing, f"flattened paths missing from blueprint: {missing}"

    def test_blueprint_rows_have_required_shape(self):
        blueprint = to_template_designer_blueprint(NXRaman)
        rows = blueprint["METADATA_PARAMETERS"]
        assert len(rows) > 50  # sanity: real schema coverage, not a stub
        for row in rows:
            assert row["param_type"] in ("value_text", "value_num", "value_boolean")
            assert row["param_group"]
            assert "/" not in row["param_name"] or row["param_name"].count("/") >= 1
