# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value

from pyambit.nexus_models.base.nx_sensor import NXSensor


class NXEnvironment(BaseModel):
    """Sample temperature (either controlled or just measured)."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXenvironment'

    temperature_sensor: Optional[NXSensor] = Field(default=None, alias='temperature_sensor', description='Temperature sensor measuring the sample temperature. This should be a link to /entry/instrument/manipulator/temperature_sensor.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
