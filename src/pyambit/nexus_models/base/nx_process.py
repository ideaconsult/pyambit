# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value

from pyambit.nexus_models.base.nx_data import NXData
from pyambit.nexus_models.base.nx_note import NXNote
from pyambit.nexus_models.base.nx_parameters import NXParameters


class NXProcess(BaseModel):
    """The :ref:`NXprocess` class describes an operation used to process data as part of an analysis workflow, providing information such as the software used, the date of the operation, the input parameters, and the resulting data."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXprocess'

    program: Optional[Union[str, Value]] = Field(default=None, alias='program', description='Name of the program used', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    sequence_index: Optional[Union[int, Value]] = Field(default=None, alias='sequence_index', description='Sequence index of processing, for determining the order of multiple **NXprocess** steps. Starts with 1.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    version: Optional[Union[str, Value]] = Field(default=None, alias='version', description='Version of the program used', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    date: Optional[Union[str, Value]] = Field(default=None, alias='date', description='Date and time of processing.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    note: Dict[str, NXNote] = Field(default_factory=dict, alias='NOTE', description='The note will contain information about how the data was processed or anything about the data provenance. The contents of the note can be anything that the processing code can understand, or simple text. The name will be numbered to allow for ordering of steps.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    parameters: Dict[str, NXParameters] = Field(default_factory=dict, alias='PARAMETERS', description='Parameters used in performing the data analysis.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    data: Dict[str, NXData] = Field(default_factory=dict, alias='DATA', description='The data resulting from the operation.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
