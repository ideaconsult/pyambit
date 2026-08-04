# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXCalibration(BaseModel):
    """Pre-calibration of an arbitrary device of the instrumental setup, which has the name DEVICE. You can specify here how, at which time by which method the calibration was done. As well the accuracy and a link to the calibration dataset."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXcalibration'

    device_path: Optional[Union[str, Value]] = Field(default=None, alias='device_path', description='Path to the device, which was calibrated. Example: entry/instrument/DEVICE', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    calibration_status: Optional[Union[str, Value]] = Field(default=None, alias='calibration_status', description="Was a calibration performed? If yes, when was it done? If the calibration time is provided, it should be specified in calibration_time. Allowed values: ['calibration time provided', 'no calibration', 'within 1 hour', 'within 1 day', 'within 1 week'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
