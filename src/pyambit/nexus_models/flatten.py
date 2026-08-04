"""Flatten a generated NeXus application-definition model (pyambit.nexus_models.*)
into the flat parameter-path dict pyambit.nexus_writer.to_nexus already knows how
to consume, plus a parallel path -> NX class hint dict.

This is the one piece of hand-written (non-generated) logic in the
nexus_models package: generic over any model produced by
dev-tools/gen_nexus_models.py, not specific to NXraman or any other single
application definition.
"""

from __future__ import annotations

import typing
from typing import Dict, Tuple, Union

from pydantic import BaseModel

from pyambit.datamodel import Value

ParameterDict = Dict[str, Union[str, Value, None]]
NxClassHints = Dict[str, str]


def _is_model_type(tp: type) -> bool:
    # Value is itself a pydantic BaseModel, but it's a leaf value wrapper
    # (see the isinstance(value, Value) branch below), never a generated
    # nested NX group - excluding it here is what keeps a
    # Union[float, Value]-typed field (see dev-tools/gen_nexus_models.py)
    # from being misidentified as "this field is a nested submodel" and
    # wrongly recursed into instead of treated as a leaf.
    return isinstance(tp, type) and issubclass(tp, BaseModel) and tp is not Value


def _dict_value_model(annotation) -> typing.Optional[type]:
    """If `annotation` is Dict[str, SomeModel], return SomeModel, else None."""
    origin = typing.get_origin(annotation)
    if origin not in (dict, Dict):
        return None
    args = typing.get_args(annotation)
    if len(args) != 2 or not _is_model_type(args[1]):
        return None
    return args[1]


def _optional_model(annotation) -> typing.Optional[type]:
    """If `annotation` is Optional[SomeModel] (or SomeModel), return SomeModel."""
    origin = typing.get_origin(annotation)
    if origin is Union:
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            if _is_model_type(arg):
                return arg
        return None
    if _is_model_type(annotation):
        return annotation
    return None


def flatten_nx_model(
    model: BaseModel, prefix: str = ""
) -> Tuple[ParameterDict, NxClassHints]:
    """Walk a generated nested pydantic model instance depth-first, producing:

    - `parameters`: {"/"-joined NeXus path: value}, matching the shape
      `pyambit.datamodel.ProtocolApplication.parameters` expects. Unset
      (`None`) fields are skipped entirely - a caller who never populated a
      field produces no NeXus path for it, and no default is invented.
      Numeric leaves whose generated field carries an NXDL unit category
      (`json_schema_extra["nx_unit_category"]`) are wrapped in
      `Value(loValue=..., unit=<unit>)`; the *category* (e.g. "NX_WAVELENGTH")
      is not a literal unit string, so `unit` is left as the category name
      unless the caller supplied a `Value` directly with its own real unit
      (see below) - pyambit does not invent unit-conversion logic.
    - `nx_class_hints`: {"/"-joined NeXus group path: NX class name}, e.g.
      `"instrument/beam_incident" -> "NXbeam"`, for `to_nexus` to instantiate
      the correct NeXus group class instead of a generic NXgroup.

    A caller may set a leaf field to a `Value` instance directly (rather than
    a plain scalar) to supply an explicit real-world unit
    (`Value(loValue=532.0, unit="nm")`); that `Value` is passed through
    unchanged.
    """
    parameters: ParameterDict = {}
    nx_class_hints: NxClassHints = {}

    for field_name, field_info in type(model).model_fields.items():
        value = getattr(model, field_name)
        if value is None:
            continue
        alias = field_info.alias or field_name
        path = f"{prefix}/{alias}" if prefix else alias
        extra = field_info.json_schema_extra or {}

        dict_model_type = _dict_value_model(field_info.annotation)
        if dict_model_type is not None:
            if not isinstance(value, dict):
                continue
            for instance_name, submodel in value.items():
                if submodel is None:
                    continue
                # The caller's chosen instance name replaces the NXDL variadic
                # placeholder segment (e.g. "INSTRUMENT") rather than nesting
                # under it - matches the existing hand-curated convention
                # ("instrument/beam_incident/...", not
                # "INSTRUMENT/instrument/beam_incident/...").
                sub_path = f"{prefix}/{instance_name}" if prefix else instance_name
                nx_class_hints[sub_path] = _nx_class_of(submodel)
                sub_params, sub_hints = flatten_nx_model(submodel, prefix=sub_path)
                parameters.update(sub_params)
                nx_class_hints.update(sub_hints)
            continue

        submodel_type = _optional_model(field_info.annotation)
        if submodel_type is not None:
            if not isinstance(value, BaseModel):
                continue
            nx_class_hints[path] = _nx_class_of(value)
            sub_params, sub_hints = flatten_nx_model(value, prefix=path)
            parameters.update(sub_params)
            nx_class_hints.update(sub_hints)
            continue

        # Leaf field (scalar or an already-constructed Value/attribute).
        #
        # Top-level (prefix == "") scalar fields - e.g. NXRaman.definition,
        # .experiment_type, .title - are entry-root NeXus fields with no
        # parent group, so they get a leading "/": "/experiment_type", not
        # bare "experiment_type". This matters because of how to_nexus's
        # parameter loop (nexus_writer.py) dispatches on the split path:
        #   - "instrument/beam_incident/wavelength".split("/") -> 3 segments
        #     -> walked as real group/group/field, landing correctly nested.
        #   - bare "experiment_type".split("/") -> 1 segment -> to_nexus
        #     treats *any* single-segment key as an AMBIT condition name and
        #     hands it to param_lookup(), which guesses a location by
        #     substring match (e.g. "instrument" in the name -> instrument
        #     group) - a heuristic for free-form AMBIT condition keys, not
        #     NXDL field names, so it would misroute experiment_type instead
        #     of writing it at the entry root.
        #   - "/experiment_type".split("/") -> ["", "experiment_type"], 2
        #     segments -> skips param_lookup entirely; to_nexus's leading-
        #     empty-segment strip (the /definition bugfix) then reduces this
        #     to just ["experiment_type"], landing at the entry root, which
        #     is where NXDL actually puts it.
        # Nested leaf fields (already prefixed by an ancestor group's path,
        # e.g. "instrument/beam_incident/wavelength") must NOT get a second
        # leading slash - the prefix already guarantees 2+ segments.
        leaf_path = f"/{path}" if not prefix else path
        if isinstance(value, Value):
            parameters[leaf_path] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            unit_category = extra.get("nx_unit_category")
            parameters[leaf_path] = Value(loValue=value, unit=unit_category) if unit_category else value
        else:
            parameters[leaf_path] = value

    return parameters, nx_class_hints


def _nx_class_of(submodel: BaseModel) -> str:
    """The real NXDL class string (e.g. "NXoptical_lens"), as recorded on the
    generated model by dev-tools/gen_nexus_models.py. Reading the stored
    `NX_CLASS` rather than reverse-deriving it from the Python class name
    (NXOpticalLens) avoids lossy guessing - PascalCase can't be inverted back
    to the original underscore placement.
    """
    return getattr(type(submodel), "NX_CLASS", type(submodel).__name__)
