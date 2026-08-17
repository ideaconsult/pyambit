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
- `src/pyambit/solr_writer.py`: `Ambit2Solr` — flattens `Substances`/`ProtocolApplication`/`EffectRecord` into Solr
  documents. Reads specific parameter keys literally, not via a naming convention: `"E.method_s"` (already Solr's
  `_s` string-suffix convention, appended by the CALLER, not by `prm2solr`) is checked directly on
  `papp.parameters`. `nexus_writer.to_nexus` separately checks the bare `"E.method"` key for
  `experiment_documentation.attrs["method"]`. A caller that wants both NeXus and Solr to pick up the method name
  needs to set BOTH keys — there is no single canonical key today.
- `tests/pyambit/datamodel/`: pytest tests, one file per concern (`datamodel_test.py`, `nexus_writer_test.py`,
  `investigation_test.py`, `default_plot_test.py`, `solr_writer_test.py`, `spectra_writer_test.py`).
- `tests/pyambit/resources/`: JSON fixtures (`study.json`, `substance.json`, `composition.json`, `buggy.json`) used
  across multiple test files.

## Environment And Tooling

- Packaging and dependency management use Poetry (`pyproject.toml` has `[tool.poetry]`, no PEP 621 `[project]`
  table). **Do not** run `uv sync`/`uv run` directly in this repo — with no `[project]` table it resolves nothing
  and silently falls back to whatever venv happens to be active (observed: a stale, unrelated `pynanomapper/.venv`).
  Use `poetry install` / `poetry run` instead.
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
