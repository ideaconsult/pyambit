"""Generate an eNanoMapper Template Designer blueprint (the JSON schema a
researcher fills in via the SurveyJS wizard) from a generated NeXus
application-definition model class (pyambit.nexus_models.*).

Generic over any model produced by dev-tools/gen_nexus_models.py, not
specific to NXraman - the "generic procedure" this package implements is:
one NXDL appdef -> one generated nested pydantic class -> two derived
artifacts (flatten_nx_model for pyambit's ProtocolApplication.parameters,
and this module for a Template Designer blueprint), both traceable back to
the same schema-derived model instead of hand-maintained independently.
"""

from __future__ import annotations

import typing
from typing import Any, Dict, List, Type

from pydantic import BaseModel

from pyambit.nexus_models.flatten import _dict_value_model, _optional_model

# NXDL top-level entry-group name -> Template Designer's fixed param_group
# dropdown vocabulary (a closed, human-curated list unrelated to NXDL group
# names - see NXRAMAN_COMPLIANCE_PLAN.md's open questions). Extend this table
# as new application definitions introduce top-level groups not covered here;
# anything unmapped falls back to OTHER_METADATA rather than guessing.
PARAM_GROUP_BY_TOP_LEVEL = {
    "instrument": "INSTRUMENT",
    "sample": "MEDIUM",
    "environment": "ENVIRONMENT",
    "data": "RESULT_ANALYSIS",
}

# NXDL unit category -> a plausible literal default unit. Best-effort display
# hint for the blueprint form only, not unit-conversion logic: pyambit does
# not interpret or convert units anywhere (see flatten_nx_model), and a
# researcher filling in the form can override this.
UNIT_CATEGORY_DEFAULTS = {
    "NX_WAVELENGTH": "nm",
    "NX_LENGTH": "mm",
    "NX_TIME": "s",
    "NX_TEMPERATURE": "K",
    "NX_ANGLE": "deg",
    "NX_PRESSURE": "Pa",
    "NX_VOLTAGE": "V",
    "NX_MASS": "g",
    "NX_MASS_DENSITY": "g/cm3",
    "NX_FREQUENCY": "Hz",
    "NX_ENERGY": "eV",
}

DTYPE_TO_PARAM_TYPE = {
    "str": "value_text",
    "float": "value_num",
    "int": "value_num",
    "bool": "value_boolean",
}


def _param_type_for(annotation) -> str:
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    for arg in args:
        name = getattr(arg, "__name__", None)
        if name in DTYPE_TO_PARAM_TYPE:
            return DTYPE_TO_PARAM_TYPE[name]
    name = getattr(annotation, "__name__", None)
    return DTYPE_TO_PARAM_TYPE.get(name, "value_text")


def _walk_class(
    model_cls: Type[BaseModel], prefix: str, top_level_group: str, rows: List[Dict[str, Any]]
) -> None:
    for field_name, field_info in model_cls.model_fields.items():
        alias = field_info.alias or field_name
        extra = field_info.json_schema_extra or {}

        dict_model_type = _dict_value_model(field_info.annotation)
        if dict_model_type is not None:
            # Path segment is the Python field name (e.g. "instrument"), not
            # the NXDL alias (e.g. "INSTRUMENT"): flatten_nx_model() replaces
            # the variadic placeholder segment with the caller's chosen
            # instance name at runtime, and field_name is this module's
            # stand-in for "some instance name a caller will pick" - keeping
            # param_name aligned with what flatten_nx_model actually produces
            # is the whole point of generating the blueprint from this model.
            path = f"{prefix}/{field_name}" if prefix else field_name
            _walk_class(dict_model_type, path, top_level_group or field_name, rows)
            continue

        submodel_type = _optional_model(field_info.annotation)
        if submodel_type is not None:
            path = f"{prefix}/{alias}" if prefix else alias
            _walk_class(submodel_type, path, top_level_group or alias, rows)
            continue

        path = f"{prefix}/{alias}" if prefix else alias

        # Leaf field.
        unit_category = extra.get("nx_unit_category")
        row: Dict[str, Any] = {
            "param_group": PARAM_GROUP_BY_TOP_LEVEL.get(
                top_level_group.lower(), "OTHER_METADATA"
            ),
            "param_name": path,
            "param_type": _param_type_for(field_info.annotation),
        }
        if field_info.description:
            row["param_hint"] = field_info.description
        if unit_category:
            default_unit = UNIT_CATEGORY_DEFAULTS.get(unit_category)
            if default_unit:
                row["param_unit"] = default_unit
        rows.append(row)


def to_template_designer_blueprint(model_cls: Type[BaseModel]) -> Dict[str, Any]:
    """Generate a Template Designer blueprint dict for `model_cls` (a
    generated appdef root model, e.g. NXRaman - a class, not an instance:
    this produces the empty/reusable blueprint schema, not a filled-in one).

    `METADATA_PARAMETERS[].param_name` values are the literal NeXus path
    strings `flatten_nx_model` recognizes (e.g.
    "instrument/beam_incident/wavelength"), so a Template Designer form built
    from this blueprint and a `flatten_nx_model`-based pyambit call can never
    drift from each other - both derive from the same generated model class.
    """
    rows: List[Dict[str, Any]] = []
    _walk_class(model_cls, prefix="", top_level_group="", rows=rows)

    nx_class = getattr(model_cls, "NX_CLASS", model_cls.__name__)
    return {
        "template_name": f"{nx_class} (schema-generated)",
        "template_status": "DRAFT",
        "METADATA_PARAMETERS": rows,
    }
