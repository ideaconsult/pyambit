# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXProgram(BaseModel):
    """Base class to describe a software tool or library."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXprogram'

    program: Optional[Union[str, Value]] = Field(default=None, alias='program', description='Commercial or otherwise defined given name of the program that was used to control any parts of the optical spectroscopy setup. The uppercase TYPE should be replaced by a specification name, i.e. "software_detector" or "software_stage" to specify the respective program or software components.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
