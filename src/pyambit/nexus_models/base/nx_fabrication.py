# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXFabrication(BaseModel):
    """Details about a component as it is defined by its manufacturer."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXfabrication'

    vendor: Optional[Union[str, Value]] = Field(default=None, alias='vendor', description='Company name of the manufacturer.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    model: Optional[Union[str, Value]] = Field(default=None, alias='model', description='Version or model of the component named by the manufacturer.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    serial_number: Optional[Union[str, Value]] = Field(default=None, alias='serial_number', description='Serial number of the component.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    construction_date: Optional[Union[str, Value]] = Field(default=None, alias='construction_date', description="Datetime of component's initial construction. This refers to the date of first measurement after new construction or to the relocation date, if it describes a multicomponent/custom-build setup. Just the year is often sufficient, but if a full date/time is used, it is recommended to add an explicit time zone.", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    capability: Optional[Union[str, Value]] = Field(default=None, alias='capability', description='Free-text list of functionalities which the component offers.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
