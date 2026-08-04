"""Generate pyambit/nexus_models/ pydantic submodels from a NeXus application
definition (NXDL), resolving its `extends` inheritance chain via pynxtools.

Dev/test-only tool. Requires the `nexus-codegen` poetry dependency group
(`poetry install --with nexus-codegen`); pynxtools/lxml/anytree are never a
runtime dependency of pyambit itself.

Usage:
    poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
    poetry run python dev-tools/gen_nexus_models.py --appdef NXraman --full

By default only "required" and "recommended" NXDL nodes are generated ("optional"
nodes are pruned) to keep the first generated model close to what real callers
populate. Pass --full to generate every node pynxtools resolves.

NX base-class submodels (NXbeam, NXinstrument, NXdetector, ...) are written once
to pyambit/nexus_models/base/ and reused across application definitions - running
this script again for a second appdef (e.g. NXxrd) that shares a base class will
not regenerate that base class's file differently, since the mapping from an NX
class to its generated field set is a function of the class's own NXDL definition,
not of which appdef referenced it.
"""

from __future__ import annotations

import argparse
import keyword
import re
from dataclasses import dataclass, field
from pathlib import Path

from pynxtools.nexus.nexus_tree import (
    NexusAttribute,
    NexusField,
    NexusGroup,
    NexusNode,
    generate_tree_from,
)

OPTIONALITY_RANK = {"required": 0, "recommended": 1, "optional": 2}

DTYPE_TO_PYTHON = {
    "NX_CHAR": "str",
    "NX_DATE_TIME": "str",
    "NX_BOOLEAN": "bool",
    "NX_NUMBER": "float",
    "NX_FLOAT": "float",
    "NX_INT": "int",
    "NX_UINT": "int",
    "NX_POSINT": "int",
}

MODELS_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "pyambit" / "nexus_models"
BASE_DIR = MODELS_PACKAGE / "base"
APPDEFS_DIR = MODELS_PACKAGE / "appdefs"

GENERATED_HEADER = """\
# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef {appdef}
# Source: NeXus application definition "{appdef}", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).
"""


def to_snake(name: str) -> str:
    """Python-identifier-safe field name for an NXDL node name.

    Variadic placeholder segments (uppercase words like TYPE/NAME/DEVICE) are
    lowercased like any other name - the placeholder-ness is tracked separately
    via `NexusNode.variadic` and only affects whether the generated field is a
    `Dict[str, Model]` (many named instances) or a plain `Optional[Model]`.

    Handles runs of consecutive capitals (e.g. "INSTRUMENT", "PID_CONTROLLER")
    as a single word instead of inserting an underscore between every letter -
    only splits before a capital that starts a new word, i.e. one preceded by
    a lowercase/digit, or one followed by a lowercase (end of an acronym run).
    """
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    snake = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", snake)
    snake = snake.lower()
    snake = re.sub(r"[^0-9a-z_]", "_", snake)
    snake = re.sub(r"_+", "_", snake).strip("_")
    if not snake:
        snake = "value"
    if snake[0].isdigit():
        snake = f"n_{snake}"
    if keyword.iskeyword(snake):
        snake = f"{snake}_"
    return snake


def to_class_name(nx_class: str) -> str:
    """NXbeam -> NXBeam, NXoptical_lens -> NXOpticalLens."""
    body = nx_class[2:] if nx_class.startswith("NX") else nx_class
    return "NX" + "".join(part.capitalize() for part in body.split("_"))


def class_name_to_module(class_name: str) -> str:
    """NXBeam -> nx_beam, NXOpticalLens -> nx_optical_lens.

    Operates on the already-PascalCase generated class name (not the raw NXDL
    `nx_class` string), so the `NX` prefix is treated as a single word rather
    than tripping the generic snake_case regex on back-to-back capitals.
    """
    body = class_name[2:] if class_name.startswith("NX") else class_name
    snake_body = re.sub(r"(?<!^)(?=[A-Z])", "_", body).lower()
    return f"nx_{snake_body}"


def clean_doc(doc: str | None) -> str:
    """Collapse an NXDL <doc> block to a single line, safe to embed in a
    generated docstring/description string (no embedded newlines/quotes)."""
    if not doc:
        return ""
    doc = " ".join(doc.split())
    return doc.replace('"""', "'''").replace("\\", "/")


def node_docstring(node: NexusNode) -> str:
    """Most-specific <doc> text for `node`.

    `NexusNode.get_docstring()` returns {name: doc} walking the inheritance
    chain from the most general (base NXobject) to the most specific
    (the appdef's own override) definition, so the *last* value - not the
    first - is the one that actually describes this node in this appdef.
    """
    if not hasattr(node, "get_docstring"):
        return ""
    docs = node.get_docstring()
    if not docs:
        return ""
    return clean_doc(next(reversed(docs.values())))


@dataclass
class FieldSpec:
    py_name: str
    nx_name: str
    py_type: str
    optional: bool
    doc: str = ""
    unit_category: str | None = None
    enum_items: list | None = None
    enum_open: bool = False
    is_attribute: bool = False
    variadic: bool = False


@dataclass
class ModelSpec:
    class_name: str
    nx_class: str
    fields: list[FieldSpec] = field(default_factory=list)
    doc: str = ""


def is_kept(node: NexusNode, full: bool) -> bool:
    if full:
        return True
    if getattr(node, "_from_base_class", False):
        # Fields merged in from a referenced base class's own generic NXDL
        # definition (see base_class_children below) are always kept: the
        # appdef itself never marks them required/recommended/optional
        # (they're simply absent from its XML), so the required/recommended
        # prune has no signal to apply to them. Keeping them is what makes
        # e.g. NXdetector.count_time or NXmonochromator's GRATING subgroup
        # reachable at all - without this they're invisible even under --full.
        return True
    rank = OPTIONALITY_RANK.get(getattr(node, "optionality", "optional"), 2)
    return rank <= OPTIONALITY_RANK["recommended"]


# NX classes whose own generic NXDL definition gets merged in (see
# base_class_children). Deliberately narrow: NXinstrument/NXsensor/etc. have
# enormous generic definitions (covering synchrotrons, neutron choppers, ...)
# that are irrelevant to Raman/optical-spectroscopy callers and would bloat
# the generated package far beyond what any real caller needs. Extend this
# set (or pass --merge-base-class on the CLI) as new appdefs need more of
# their referenced classes' generic vocabulary surfaced.
DEFAULT_BASE_CLASS_MERGE_TARGETS = frozenset(
    {
        "NXdetector",
        "NXmonochromator",
        "NXoptical_lens",
        "NXsample",
        "NXgrating",
        "NXfabrication",
    }
)

_BASE_CLASS_TREE_CACHE: dict[str, NexusNode] = {}


def base_class_children(nx_class: str, merge_targets: frozenset[str]) -> list[NexusNode]:
    """Direct children of `nx_class`'s own NXDL definition (e.g. NXdetector's
    own count_time field), as opposed to only what an appdef re-declares for
    a group referenced with `type="NXdetector"`.

    NeXus base classes are generically usable: any field declared directly in
    e.g. NXdetector.nxdl.xml is legal on any NXdetector-typed group in any
    file, regardless of whether the enclosing application definition mentions
    it. `generate_tree_from(appdef)` only resolves what the appdef's own
    `extends` chain re-declares for a *referenced* group, so this separately
    loads the referenced class's own tree to fill that gap. Only classes in
    `merge_targets` are expanded this way (see DEFAULT_BASE_CLASS_MERGE_TARGETS)
    - most NX base classes are far too generic to merge in wholesale. Results
    are cached since many groups across a tree (and across appdefs, in a
    future multi-appdef run) reference the same base class.
    """
    if nx_class not in merge_targets:
        return []
    if nx_class in _BASE_CLASS_TREE_CACHE:
        tree = _BASE_CLASS_TREE_CACHE[nx_class]
    else:
        try:
            tree = generate_tree_from(nx_class)
        except Exception:
            # Not every `type="NX*"` reference resolves to a loadable
            # definition file (e.g. "NXobject" itself); skip silently.
            tree = None
        _BASE_CLASS_TREE_CACHE[nx_class] = tree
    if tree is None:
        return []
    for child in tree.children:
        child._from_base_class = True
    return list(tree.children)


def dedupe_children(children: list[NexusNode]) -> list[NexusNode]:
    """Collapse exact-duplicate (name, kind) siblings, keeping the richer one.

    pynxtools' sibling-namefitting can attach the same (name, nx_class) group
    twice at one tree level (e.g. a bare variadic placeholder plus a namefitted
    concrete instance). Prefer whichever has more children; on a tie prefer the
    non-variadic (concretely named) one.
    """
    best: dict[tuple, NexusNode] = {}
    for child in children:
        key = (child.name, type(child).__name__, getattr(child, "nx_class", None))
        existing = best.get(key)
        if existing is None:
            best[key] = child
            continue
        existing_score = (len(existing.children), not getattr(existing, "variadic", False))
        child_score = (len(child.children), not getattr(child, "variadic", False))
        if child_score > existing_score:
            best[key] = child
    return list(best.values())


def build_model_specs(
    node: NexusGroup,
    full: bool,
    specs: dict[str, ModelSpec],
    merge_targets: frozenset[str],
) -> str:
    """Recursively build ModelSpecs for `node` and its descendants.

    Returns the generated class name for `node`. Populates `specs` keyed by
    class name as a side effect, so a base class (e.g. NXBeam) referenced from
    multiple places in the tree is only ever built once.

    Base-class field merging (see `base_class_children`) is allowlisted to
    `merge_targets`: a group's referenced NX class only gets its own generic
    NXDL fields merged in if that class is in `merge_targets` - regardless of
    whether the group itself was reached directly from the appdef tree or via
    another class's merge (e.g. NXmonochromator's GRATING field, itself
    merged in from NXmonochromator's base class, can still have NXgrating's
    own fields merged in too, since NXgrating is separately allowlisted).
    Classes not in `merge_targets` never get this treatment, which is what
    keeps the generated package from ballooning into unrelated generic NeXus
    vocabulary (see DEFAULT_BASE_CLASS_MERGE_TARGETS).
    """
    class_name = to_class_name(node.nx_class)
    if class_name in specs:
        return class_name

    doc = node_docstring(node)
    spec = ModelSpec(class_name=class_name, nx_class=node.nx_class, doc=doc)
    specs[class_name] = spec  # insert before recursing to break cycles (e.g. NXtransformations)

    merged = base_class_children(node.nx_class, merge_targets)
    all_children = list(node.children) + merged
    children = dedupe_children([c for c in all_children if is_kept(c, full)])
    seen_names: set[str] = set()
    for child in children:
        py_name = to_snake(child.name)
        while py_name in seen_names:
            py_name += "_"
        seen_names.add(py_name)

        child_doc = node_docstring(child)
        optional = getattr(child, "optionality", "optional") != "required"

        if isinstance(child, NexusGroup):
            child_class = build_model_specs(child, full, specs, merge_targets)
            py_type = f"Dict[str, {child_class}]" if child.variadic else f"Optional[{child_class}]"
            spec.fields.append(
                FieldSpec(
                    py_name=py_name,
                    nx_name=child.name,
                    py_type=py_type,
                    optional=optional,
                    doc=child_doc,
                    variadic=child.variadic,
                )
            )
        elif isinstance(child, (NexusField, NexusAttribute)):
            py_scalar = DTYPE_TO_PYTHON.get(child.dtype, "str")
            # Enum items (open or closed) are documented, not enforced as Literal:
            # pyambit must not add Raman/NeXus domain validation (see
            # NXRAMAN_COMPLIANCE_PLAN.md) - callers may legitimately need values
            # outside a "closed" enumeration in practice.
            # Union[..., Value] (not bare py_scalar): lets a caller supply an
            # explicit Value(loValue=..., unit=...) for fields where NXDL
            # itself declares no unit category (e.g. NXbeam.wavelength) but a
            # real-world unit still needs to reach the written NeXus file -
            # flatten_nx_model() passes an already-constructed Value straight
            # through unchanged.
            py_type = f"Optional[Union[{py_scalar}, Value]]"
            spec.fields.append(
                FieldSpec(
                    py_name=py_name,
                    nx_name=child.name,
                    py_type=py_type,
                    optional=True,
                    doc=child_doc,
                    unit_category=getattr(child, "unit", None),
                    enum_items=child.items,
                    enum_open=getattr(child, "open_enum", False),
                    is_attribute=isinstance(child, NexusAttribute),
                    variadic=child.variadic,
                )
            )
    return class_name


def render_field(f: FieldSpec) -> str:
    doc_bits = []
    if f.doc:
        doc_bits.append(f.doc)
    if f.unit_category:
        doc_bits.append(f"Unit category: {f.unit_category}.")
    if f.enum_items:
        kind = "Suggested values" if f.enum_open else "Allowed values"
        doc_bits.append(f"{kind}: {f.enum_items!r}.")
    description = " ".join(doc_bits)

    is_dict = f.py_type.startswith("Dict[")
    default_kw = "default_factory=dict" if is_dict else "default=None"

    alias = f.nx_name
    # repr() rather than manual quoting/escaping: safe against embedded quotes,
    # backslashes, or (defensively) newlines in doc text pulled from NXDL <doc>.
    parts = [f"Field({default_kw}, alias={alias!r}"]
    if description:
        parts.append(f"description={description!r}")
    # json_schema_extra carries machine-readable NXDL metadata (unit category,
    # attribute-vs-field, variadic) for flatten_nx_model() to consume at
    # runtime - the free-text `description` above is for humans/IDEs only and
    # must not be parsed back for this.
    extra = {"nx_unit_category": f.unit_category, "nx_is_attribute": f.is_attribute}
    parts.append(f"json_schema_extra={extra!r}")
    field_call = ", ".join(parts) + ")"
    return f"    {f.py_name}: {f.py_type} = {field_call}"


def render_model(spec: ModelSpec, base_import: str) -> str:
    lines = [f"class {spec.class_name}({base_import}):"]
    doc = spec.doc or f'NeXus base class "{spec.nx_class}".'
    lines.append(f'    """{doc}"""')
    lines.append("")
    lines.append('    model_config = ConfigDict(populate_by_name=True)')
    # The real NXDL class string (e.g. "NXoptical_lens"), distinct from the
    # generated Python class name (NXOpticalLens) - flatten_nx_model() reads
    # this rather than reverse-deriving it from the class name, which would
    # be lossy (capitalization can't be inverted back to "_lens").
    lines.append(f"    NX_CLASS: ClassVar[str] = {spec.nx_class!r}")
    lines.append("")
    if not spec.fields:
        lines.append("    pass")
    for f in spec.fields:
        lines.append(render_field(f))
    return "\n".join(lines) + "\n"


def collect_referenced_classes(spec: ModelSpec) -> set[str]:
    refs = set()
    for f in spec.fields:
        m = re.search(r"\bNX\w+\b", f.py_type)
        if m:
            refs.add(m.group(0))
    return refs


def write_base_classes(specs: dict[str, ModelSpec], root_class: str, appdef: str) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    package_init = MODELS_PACKAGE / "__init__.py"
    if not package_init.exists():
        package_init.write_text("", encoding="utf-8")
    init_path = BASE_DIR / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")

    for class_name, spec in specs.items():
        if class_name == root_class:
            continue  # the appdef root model lives in appdefs/, not base/
        module_name = class_name_to_module(class_name)
        file_path = BASE_DIR / f"{module_name}.py"

        refs = sorted(collect_referenced_classes(spec) - {class_name})
        import_lines = []
        for ref in refs:
            ref_spec = specs.get(ref)
            if ref_spec is None:
                continue
            ref_module = class_name_to_module(ref)
            import_lines.append(f"from pyambit.nexus_models.base.{ref_module} import {ref}")

        content = GENERATED_HEADER.format(appdef=appdef)
        content += "\nfrom __future__ import annotations\n\n"
        content += "from typing import ClassVar, Dict, Optional, Union\n\n"
        content += "from pydantic import BaseModel, ConfigDict, Field\n\n"
        content += "from pyambit.datamodel import Value\n"
        if import_lines:
            content += "\n" + "\n".join(import_lines) + "\n"
        content += "\n\n"
        content += render_model(spec, base_import="BaseModel")
        file_path.write_text(content, encoding="utf-8")
        print(f"wrote {file_path.relative_to(MODELS_PACKAGE.parent.parent)}")


def write_appdef_model(specs: dict[str, ModelSpec], root_class: str, appdef: str) -> None:
    APPDEFS_DIR.mkdir(parents=True, exist_ok=True)
    init_path = APPDEFS_DIR / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")

    spec = specs[root_class]
    module_name = class_name_to_module(root_class)
    file_path = APPDEFS_DIR / f"{module_name}.py"

    refs = sorted(collect_referenced_classes(spec))
    import_lines = []
    for ref in refs:
        ref_spec = specs.get(ref)
        if ref_spec is None:
            continue
        ref_module = class_name_to_module(ref)
        import_lines.append(f"from pyambit.nexus_models.base.{ref_module} import {ref}")

    content = GENERATED_HEADER.format(appdef=appdef)
    content += "\nfrom __future__ import annotations\n\n"
    content += "from typing import ClassVar, Dict, Optional, Union\n\n"
    content += "from pydantic import BaseModel, ConfigDict, Field\n\n"
    content += "from pyambit.datamodel import Value\n"
    if import_lines:
        content += "\n" + "\n".join(import_lines) + "\n"
    content += "\n\n"
    content += render_model(spec, base_import="BaseModel")
    file_path.write_text(content, encoding="utf-8")
    print(f"wrote {file_path.relative_to(MODELS_PACKAGE.parent.parent)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appdef", required=True, help='e.g. "NXraman"')
    parser.add_argument(
        "--full",
        action="store_true",
        help="Generate every node (including optional), not just required+recommended.",
    )
    parser.add_argument(
        "--merge-base-class",
        action="append",
        default=[],
        metavar="NXclass",
        help=(
            "NX class to merge generic base-class fields into (see "
            "base_class_children), in addition to the defaults "
            f"({', '.join(sorted(DEFAULT_BASE_CLASS_MERGE_TARGETS))}). May be "
            "repeated."
        ),
    )
    args = parser.parse_args()
    merge_targets = DEFAULT_BASE_CLASS_MERGE_TARGETS | frozenset(args.merge_base_class)

    tree = generate_tree_from(args.appdef)
    entry = next((c for c in tree.children if isinstance(c, NexusGroup) and c.nx_class == "NXentry"), None)
    if entry is None:
        raise SystemExit(f"No NXentry group found under {args.appdef}")

    specs: dict[str, ModelSpec] = {}
    root_class = to_class_name(args.appdef)
    entry_doc = node_docstring(tree)

    root_spec = ModelSpec(class_name=root_class, nx_class=args.appdef, doc=entry_doc)
    specs[root_class] = root_spec

    children = dedupe_children([c for c in entry.children if is_kept(c, args.full)])
    seen_names: set[str] = set()
    for child in children:
        py_name = to_snake(child.name)
        while py_name in seen_names:
            py_name += "_"
        seen_names.add(py_name)

        child_doc = node_docstring(child)
        optional = getattr(child, "optionality", "optional") != "required"

        if isinstance(child, NexusGroup):
            child_class = build_model_specs(child, args.full, specs, merge_targets)
            py_type = f"Dict[str, {child_class}]" if child.variadic else f"Optional[{child_class}]"
            root_spec.fields.append(
                FieldSpec(py_name=py_name, nx_name=child.name, py_type=py_type, optional=optional, doc=child_doc)
            )
        elif isinstance(child, (NexusField, NexusAttribute)):
            py_scalar = DTYPE_TO_PYTHON.get(child.dtype, "str")
            root_spec.fields.append(
                FieldSpec(
                    py_name=py_name,
                    nx_name=child.name,
                    py_type=f"Optional[Union[{py_scalar}, Value]]",
                    optional=True,
                    doc=child_doc,
                    unit_category=getattr(child, "unit", None),
                    enum_items=child.items,
                    enum_open=getattr(child, "open_enum", False),
                    is_attribute=isinstance(child, NexusAttribute),
                )
            )

    write_base_classes(specs, root_class, args.appdef)
    write_appdef_model(specs, root_class, args.appdef)
    print(f"\n{len(specs)} model(s) generated for {args.appdef} (full={args.full}).")


if __name__ == "__main__":
    main()
