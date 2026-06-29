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
