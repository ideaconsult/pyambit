# TODO

## Category-specific config for effect→array conversion (dose axis, cell type, exposure time, method, …)

### Problem
`ProtocolApplication.convert_effectrecords2array()` in [`src/pyambit/datamodel.py`](src/pyambit/datamodel.py)
selects the plot axis by a hardcoded rule:

```python
alt_axes = [s for s in conditions if s.startswith("CONCENTRATION")]
```

So only conditions named `CONCENTRATION*` become the X axis. Real eNanoMapper/AMBIT data is
**category-specific**: e.g. ECOTOX (`EC_*_SECTION`) carries the dose as a **`DOSE`** condition,
not `CONCENTRATION`. Those studies therefore convert without an axis and can't be plotted as a
dose–response curve. The same applies to other semantically-fixed conditions that consumers want
to surface (cell type, exposure time, method), which are currently only known to the **frontend**
study config, not to pyambit.

### Evidence / where this bites
- Consumers (e.g. `jtoxkit-react` dose–response chart, via `ramanchada-api`
  `POST /dataset/convert?format=effectarray`) need the axis to exist after conversion.
- The legacy jToxKit study config already encodes this per endpoint category — e.g.
  `e.cell_type` → "Cell type", `e.exposure_time` → "Exposure time", `e.method`, and `DOSE` as the
  ECOTOX dose axis (see `jtoxkit-react/src/config/{bao,npo,exposure,i5}.js`).

### Interim workaround (lives outside pyambit)
`ramanchada-api` `convertor_service._bridge_dose_axis()` renames `DOSE*` → `CONCENTRATION*` on each
effect's conditions before calling `convert_effectrecords2array`. This is a **stopgap**; the proper
fix belongs here in pyambit.

### Proposed change
Introduce a **category-specific config** in pyambit (analogous to jToxKit's `config_study`) keyed by
endpoint category code (`EC_ALGAETOX_SECTION`, `PC_*`, `TO_*`, …), declaring per category:
- the **dose/concentration axis** condition field(s) (e.g. `CONCENTRATION`, `DOSE`, `CONCENTRATION_MASS`),
- semantic condition fields worth tagging: `e.cell_type`, `e.exposure_time`, `e.method`, treatment/control, …

Then make `convert_effectrecords2array` (and `nexus_writer.effectarray2data`) **config-driven**:
- pick axes from the configured dose fields (with sensible defaults = current `CONCENTRATION*` behaviour),
- optionally annotate the resulting `EffectArray` / `NXdata` with the tagged semantic fields.

Design notes:
- Default config must reproduce today's behaviour (no regression for `CONCENTRATION`).
- Keep it data-driven (a dict/YAML), overridable by callers — same spirit as the frontend config.
- Update `tests/pyambit/datamodel/datamodel_test.py` with a `DOSE`-axis category case.

### Acceptance
- A study whose dose axis is `DOSE` converts to an `EffectArray` with a proper axis (no external bridge needed).
- `CONCENTRATION` studies are unchanged.
- The `ramanchada-api` `_bridge_dose_axis` stopgap can then be removed.

---

## Related issues found while wiring the dose–response chart

### (a) `EffectArray.model_dump_json` crashes on numpy scalars
The `serialize` default in `EffectArray.model_dump_json` returns unknown objects unchanged,
so a numpy scalar in a condition (e.g. `NUMBER_OF_REPLICATES` → `np.int64`) makes
`json.dumps` recurse and raise **"Circular reference detected"**. Real ENM oxidative-stress
data hits this, so the whole study fails to convert.
- Fix: the default should coerce `np.generic` → `.item()` and `np.ndarray` → `.tolist()`.
- Interim: `ramanchada-api` `convertor_service._earray_to_dict` serializes numpy-safely.

### (b) Numeric non-dose conditions become spurious axes
`convert_effectrecords2array` turns every numeric condition into an axis, so
`NUMBER_OF_REPLICATES` becomes a plot axis alongside `CONCENTRATION` (2-D signal, wrong X).
Replicate/blank counts should be excluded from axes (treated as replicates → mean±SD), per
the category config above (e.g. a `replicate` role for `NUMBER_OF_REPLICATES`, `replicate`).

### (c) Control designation field varies
Controls are flagged by different condition keys across datasets — `Treatment` in some,
**`material`** ("Positive control"/"Negative control"/"none") in ENM oxidative stress. The
category config should declare which condition carries the control role.

### (d) Dose series split across protocol applications == data import issue
Observed in ENM oxidative-stress data: each concentration is imported as a **separate**
protocol application (its own `document_uuid`, holding one dose level + controls), so no
single papp contains the curve. This is an **import-quality problem**, not a conversion
feature: correctly imported, one protocol application holds the whole concentration series
as its `effects[]`, and the per-`document_uuid` model plots the curve directly.
- Preferred fix: correct the import so one dose–response experiment = one `document_uuid`.
- Only if mis-imported data must be tolerated: optionally aggregate papps sharing an
  `investigation_uuid` / `assay_uuid` into one `EffectArray` (the deferred "same
  document_uuid" grouping) — a workaround, not the target state.
