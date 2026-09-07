# AGENTS.md

Guidance for AI agents working on `pyambit`. This file describes the current repository state and should be updated
whenever tooling, docs, or workflows change.

## Project Overview

`pyambit` is the Python implementation of the AMBIT data model (https://ambit.sourceforge.net/) — a simplified,
pydantic-based representation of ISA-TAB-style study data (substances, protocol applications, effects, conditions),
plus a NeXus/HDF5 writer and reader (`nexus_writer.py`, `nexus_parser.py`) and a Solr document writer
(`solr_writer.py`).

It is a foundational dependency for `pynanomapper` (Template Designer Excel parsing, Excel-to-NeXus conversion) and
for downstream ploomber pipelines that convert lab/instrument data to NeXus.

## Repository Layout

- `src/pyambit/datamodel.py`: the AMBIT data model itself — `SubstanceRecord`, `Substances`, `ProtocolApplication`,
  `Protocol`, `EndpointCategory`, `Citation`, `Investigation`, `EffectRecord`/`EffectArray`, `EffectResult`,
  `ValueArray`, `Composition`/`CompositionEntry`, `SampleLink`. Every model with a custom `__eq__`/`__repr__` is
  rewrapped at the bottom of its class block via `create_model("Name", __base__=Name)` — needed for forward
  references between models defined later in the file; follow this pattern for any new model used inside another.
- `src/pyambit/nexus_writer.py`: `ProtocolApplication`/`Study`/`SubstanceRecord`/`Substances`/`Composition` →
  NeXus, registered via `@add_ambitmodel_method` (`ambit_deco.py`) so e.g. `substance.to_nexus(nxroot)` works
  directly on the model. `hierarchy=False` (the default, and what every real caller in this codebase uses) writes
  entries flat at root; `hierarchy=True` nests them under `/<topcategory>/<category_code>/...`.
- `src/pyambit/nexus_parser.py`: the reverse direction, `Nexus2Ambit`. `parse_studies` iterates every top-level key
  in the NeXus root as a study entry EXCEPT `"substance"` and `"investigation"`, which are shared groups written
  once and linked from real entries (see `nexus_writer.to_nexus`) — add any future shared top-level group to that
  skip list too, or `parse_entry` will crash on it (it unconditionally reads `nxentry["definition"]`).
- `src/pyambit/nexus_spectra.py`, `nexus_xrd.py`: technique-specific helpers (`spe2effect`/`spe2ambit` for Raman,
  `xrd2effect`/`xrd2ambit` for XRD) that build the right `EffectArray`/`Protocol` shape for their NeXus application
  definition (`NXxrd` extends `NXmonopd` and wants `polar_angle`, not a generic axis name, etc.).
- `src/pyambit/study_config.py` + `src/pyambit/resources/study_config.json`: per-endpoint-category configuration
  shared with the jToxKit viewer, generated from `jtoxkit-react/src/config/*.js` by an external export script (not
  in this repo). Drives `convert_effectrecords2array`'s dose-axis selection instead of a hardcoded rule. Keep the
  JSON in sync with jtoxkit-react if that config changes; this repo cannot regenerate it standalone.
- `src/pyambit/units.py`: eNanoMapper measure classes built on the `measurement` package — `Concentration`
  (mass/volume), `ConcentrationMolar` (molar/volume), `ConcentrationSurface` (area/volume, for the
  `concentration_surface` dose field `study_config` names), `Molar`, `Percent` (including the `%DNA in Tail`
  spellings) and `Dose`. These live here, not in `pynanomapper`, because **pyambit must never import
  pynanomapper** — pynanomapper depends on pyambit, so the reverse is circular. `pynanomapper.units.convert_units`
  is deliberately NOT ported: it accepts a `measures=` argument and never forwards it to `measurement.utils.guess`,
  so it returns `None` for every concentration unit, and calling `guess` directly with an explicit measure list
  raises `KeyError: 'umol'` from an alias collision. Construct the classes directly
  (`Concentration(ug__ml=10).mg__l`). Note that a same-unit conversion factor is not exactly `1.0`, so never use a
  converted concentration as an exact dict key.
- `src/pyambit/bmd.py`: benchmark dose (BMD) with its uncertainty, from `SubstanceRecord`/`ProtocolApplication`.
  `series_from_substance` groups into `{PropertyKey: {provider: [DoseSeries]}}`, `bmd_cdf` bootstraps the BMD
  distribution (BMDL/BMD/BMDU are quantiles of one object), `consolidate_providers` mixes laboratories with equal
  weight, `bmd_vector` flattens to a fixed-length vector in log10 concentration. Reads the dose axis, exposure
  time, assay method and control annotation from `study_config` per endpoint category rather than hardcoding
  condition names, so it works against arbitrary AMBIT records. **It is a reader**: it never mutates the record or
  the `EffectArray`, and a record written to NeXus before and after a BMD read produces the same tree (pinned by
  `test_reading_a_record_does_not_mutate_it` and
  `test_a_record_still_writes_to_nexus_after_being_read_for_bmd`). Note in particular that a per-well `REPLICATE`
  index is a real array dimension and stays one — NeXus needs it to write each well; `bmd.py` only *reads* along
  the dose axis, gathering wells at one concentration into repeated observations of a single point for the
  bootstrap, in the `DoseSeries` it builds and nowhere else. One trap it does exist to avoid, which produced
  *confidently wrong output* rather than an error and is pinned by a test: the provider must be `citation.owner`
  (the laboratory) before `owner.company.name` (the funding project), or every lab in a project collapses into one
  provider and consolidation becomes a silent no-op.
- `src/pyambit/solr_writer.py`: `Ambit2Solr` — flattens `Substances`/`ProtocolApplication`/`EffectRecord` into Solr
  documents. Reads the bare `"E.method"` parameter key (same key `nexus_writer.to_nexus` reads for
  `experiment_documentation.attrs["method"]`) and appends the `_s` suffix itself when writing `E.method_s` into the
  Solr document — a caller sets `papp.parameters["E.method"]` once and both NeXus and Solr pick it up. (Previously
  `solr_writer.py` checked the literal `"E.method_s"` key instead, which no caller in this codebase's test fixtures
  ever set — fixed to read the bare key, consistent with the general rule that `_s`/`_d` suffixes are appended by
  the Solr indexer, not carried by source parameters.)
- `tests/pyambit/datamodel/`: pytest tests, one file per concern (`datamodel_test.py`, `nexus_writer_test.py`,
  `investigation_test.py`, `default_plot_test.py`, `solr_writer_test.py`, `spectra_writer_test.py`,
  `units_test.py`, `bmd_test.py`).
- `tests/pyambit/resources/`: JSON fixtures (`study.json`, `substance.json`, `composition.json`, `buggy.json`) used
  across multiple test files.

## Environment And Tooling

- Packaging and dependency management use Poetry (`pyproject.toml` has `[tool.poetry]`, no PEP 621 `[project]`
  table). **Do not** run `uv sync`/`uv run` directly in this repo — with no `[project]` table it resolves nothing
  and silently falls back to whatever venv happens to be active (observed: a stale, unrelated `pynanomapper/.venv`).
  Use `poetry install` / `poetry run` instead.
- Runtime dependencies now include `numpy` (long used directly by `datamodel.py`/`nexus_writer.py` but previously
  undeclared, arriving transitively via pandas) and `measurement` (for `units.py`). `pynanomapper` is **not** a
  dependency and must never become one — see `units.py` above.
- `pyproject.toml` declares `python = ">=3.10,<3.14"` (pyambit's own `python-version` line in `.python-version`, if
  present, should match).
- CI (`.github/workflows/ci.yml`) targets `main` and runs on Python 3.10–3.13 with Poetry 2.1.3.
- The active development branch at the time of writing is `study_config` (8 commits ahead of `main`, not yet
  merged) — check `git branch --show-current` before assuming `main` is current.
- `[tool.pytest.ini_options]` sets `pythonpath = ["src"]` and treats warnings as errors (`filterwarnings =
  ["error", ...]`) with one explicit ignore for a Python 3.14 deprecation notice.

Run the test suite:

```sh
poetry install
poetry run pytest
```

Run a focused test file during development:

```sh
poetry run pytest tests/pyambit/datamodel/nexus_writer_test.py -v
```

## Known Sharp Edges (found by direct reproduction, not guessed)

- **`entry_id` leading-slash bug** (`nexus_writer.to_nexus`): when `hierarchy=False` and the entry has no citation
  owner (or the `try` block raises), `entry_id` comes out with a redundant leading `"/"`. `NXgroup.__setitem__`
  treats any `/` as a path separator, so `nx_root[entry_id] = ...` then splits on an empty first segment and
  writes a mangled entry — confirmed by inspection (a literal `"@_<name>"` key, not a normal `NXentry`) rather than
  a normal one. Fixed for the common case (`entry_id.lstrip("/")` when there is no real hierarchy path in front of
  it), but the underlying fragility (any code path that leaves `_categories_collection` empty and provider empty)
  is still there — a citation with a real `owner` sidesteps it entirely.
- **`@default` chain**: NeXus expects `root/@default` → `entry/@default` → `group/@default` → a plottable `NXdata`.
  `process_pa` now tracks the first-seen NUMERIC-axis `NXdata` at both the entry and the containing-group level, so
  a generic viewer's default plot doesn't land on a categorical axis (e.g. `LOD` indexed by `"polymer"` name) and
  fail with something like "Expected numeric type". If a study has genuinely no numeric-axis effect, the chain
  still resolves to *something* (the first entry) rather than being left unset.
- **`EffectRecord`/`EffectArray` string axes and signals**: an axis or signal holding text (categorical axis
  values, or a `Marker`-type text result) arrives as a numpy object-dtype array. h5py has no native HDF5 type for
  `dtype('O')` and raises on write; both `effectarray2data`'s axis loop and its signal assignment pass an explicit
  `h5py.string_dtype(encoding="utf-8")` when the array is object-dtype — do the same for any new array-writing code
  path added here.
- **`ProtocolApplication.convert_effectrecords2array`** does NOT pivot multiple same-endpoint `EffectRecord`s that
  differ only in one condition value into a single array-with-an-axis; it produces one scalar `EffectArray` per
  record, still colliding on the same NXdata group name if written directly. Build a proper `EffectArray` with a
  real axis by hand instead (construct `ValueArray`s for `signal` and each `axes` entry directly) rather than
  relying on this conversion for that purpose.
- **`Investigation.image`** is a base64 `str` on the pydantic model (JSON-portable), but `nexus_writer` decodes it
  into a real `NXnote(type="image/png", data=<uint8 bytes>)` — the NeXus-native way to embed a picture (`NXnote`
  base class, `data` field is `NX_BINARY`, doc says explicitly "e.g. pictures, movies, audio"). A raw base64
  string field would just display as text (`iVBORw0KG...`) to any NeXus/HDF5-aware viewer.
- **`None`-valued attrs silently vanish on write, then crash on read**: `nexus_writer.to_nexus` writes several
  fields unconditionally as NXentry/NXsample attrs (`SubstanceRecord.ownerUUID` → `attrs["ownerUUID"]`,
  `Protocol.guideline` → `experiment_documentation/protocol.attrs["guideline"]`) without checking for `None` first.
  Both fields default to `None` on their models (`ownerUUID: Optional[str] = None`,
  `guideline: List[str] = None` — the latter a separate pre-existing type-hint-violating default). h5py/nexusformat
  silently drops an attribute assigned `None` rather than writing a null value, so the key is simply absent —
  `Nexus2Ambit.parse` then crashes with `KeyError('ownerUUID')` or `KeyError('guideline')` on read, not a clean
  validation error at write time. Any writer helper that builds a `SubstanceRecord`/`Protocol` (including
  `spe2ambit`/`configure_papp` in `nexus_spectra.py`, which never sets `guideline`) must set both fields
  explicitly — confirmed via real readers (`nanodata/pipeline_nexus/tasks/read_blop.py`) hitting both `KeyError`s
  in production use before setting them by hand.
- **The same `None` problem applies to NXfields, not just attrs — and there the fix belongs on the READ side.**
  `to_nexus` writes `nx_root["{entry_id}/collection_identifier"] = investigation_uuid` and
  `.../experiment_identifier` = `assay_uuid` unconditionally (`nexus_writer.py:181-186`); assigning `None` drops
  the field entirely, exactly as with attrs. But unlike `ownerUUID`/`guideline`, an absent
  `collection_identifier` is **legitimate**: `configure_papp(group_investigation=False)` deliberately leaves
  `investigation_uuid` unset for corpora that shouldn't be linked into a shared `investigation/<uuid>` group
  (RRUFF: one `.nxs` per sample, no reason to link thousands of unrelated minerals). `parse_entry` therefore must
  not call `.nxvalue` on the result of `nxentry.get(...)` unconditionally — it now null-checks both fields.
  Confirmed the hard way: before that fix, indexing the RRUFF corpus failed **every single entry** with
  `AttributeError: 'NoneType' object has no attribute 'nxvalue'`, producing a silently empty Solr index (the
  per-file `try/except` in the caller swallowed each one as a logged error). When adding a new field to
  `parse_entry`, null-check it unless a writer genuinely guarantees it is always set.
- **`ProtocolApplication.uuid` is a plain `Optional[str]`, with no UUID-format validation anywhere** — not in the
  pydantic model, not in `nexus_writer` (`entry_id` is built from `papp.nx_name`, and `entry_identifier_uuid` is
  written verbatim), not in `nexus_parser` (read back as an opaque string). A comment in an early version of
  `pipeline_nexus/tasks/read_rruff.py` claimed "the AMBIT parser expects [papp.uuid] to actually be a UUID" and
  hashed a readable identifier because of it; that claim does not hold against this code. The *real* constraint on
  `papp.uuid` is external — Java-side AMBIT code and the database schema — so it should still stay a uuid, but do
  not attribute that requirement to pyambit or go looking for the validation here. A consumer that needs a
  readable identifier should derive it from `nx_name` instead (see `import_pipeline`'s `NxNameDocumentIdMixin`).

## Development Guidance

- Make the smallest correct change. Avoid broad cleanup or formatting churn unless requested.
- When adding a new pydantic model referenced by an existing one (forward reference), follow the
  `create_model("Name", __base__=Name)` rewrap pattern already used throughout `datamodel.py`, and update that
  model's hand-written `__eq__`/`__repr__` to include the new field (they are NOT auto-generated).
- Prefer writing a real `pytest` test over an ad-hoc `python -c` script for anything meant to be verified more than
  once — ad-hoc scripts don't persist and don't get re-run by CI.
- `hierarchy=False` is the realistic default to test against; `hierarchy=True` produces a materially different
  tree shape (categories nested under root) that most real callers do not use.
- If NeXus/HDF5 conventions are unclear, check the actual `.nxdl.xml` base class definitions from the
  [NeXus definitions repository](https://github.com/nexusformat/definitions) rather than guessing from the field
  name alone.
- When code, tests, docs, or CI change, update this file.
