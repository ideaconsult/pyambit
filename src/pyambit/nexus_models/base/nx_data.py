# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXData(BaseModel):
    """Contains the raw data collected by the detector before calibration. The data which is considered raw might change from experiment to experiment due to hardware pre-processing of the data. This field ideally collects the data with the lowest level of processing possible."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXdata'

    signal: Optional[Union[str, Value]] = Field(default=None, alias='signal', description=".. index:: find the default plottable data .. index:: plotting .. index:: signal attribute value The value is the :ref:`name <validItemName>` of the signal that contains the default plottable data. This field or link *must* exist and be a direct child of this NXdata group. It is recommended (as of NIAC2014) to use this attribute rather than adding a signal attribute to the field. See https://www.nexusformat.org/2014_How_to_find_default_data.html for a summary of the discussion. Allowed values: ['raw'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': True})
    raw: Optional[Union[float, Value]] = Field(default=None, alias='raw', description='Raw data before calibration.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
