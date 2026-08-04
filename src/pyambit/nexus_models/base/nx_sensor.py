# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXSensor(BaseModel):
    """A sensor used to monitor an external condition The condition itself is described in :ref:`NXenvironment`."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXsensor'

    name: Optional[Union[str, Value]] = Field(default=None, alias='name', description='Name for the sensor', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    measurement: Optional[Union[str, Value]] = Field(default=None, alias='measurement', description="name for measured signal Allowed values: ['temperature'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    value: Optional[Union[float, Value]] = Field(default=None, alias='value', description='nominal setpoint or average value - need [n] as may be a vector Unit category: NX_ANY.', json_schema_extra={'nx_unit_category': 'NX_ANY', 'nx_is_attribute': False})
