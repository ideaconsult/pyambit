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


class NXCalibration(BaseModel):
    """Pre-calibration of an arbitrary device of the instrumental setup, which has the name DEVICE. You can specify here how, at which time by which method the calibration was done. As well the accuracy and a link to the calibration dataset."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXcalibration'

    device_path: Optional[Union[str, Value]] = Field(default=None, alias='device_path', description='Path to the device, which was calibrated. Example: entry/instrument/DEVICE', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    calibration_status: Optional[Union[str, Value]] = Field(default=None, alias='calibration_status', description="Was a calibration performed? If yes, when was it done? If the calibration time is provided, it should be specified in calibration_time. Allowed values: ['calibration time provided', 'no calibration', 'within 1 hour', 'within 1 day', 'within 1 week'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    description: Optional[Union[str, Value]] = Field(default=None, alias='description', description='A description of the procedures employed.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    physical_quantity: Optional[Union[str, Value]] = Field(default=None, alias='physical_quantity', description='The physical quantity of the calibration, e.g., energy, momentum, time, etc.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    identifier_calibration_method: Optional[Union[str, Value]] = Field(default=None, alias='identifier_calibration_method', description='A digital persistent identifier (e.g., DOI, ISO standard) referring to a detailed description of a calibration method but no actual calibration data.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    identifier_calibration_reference: Optional[Union[str, Value]] = Field(default=None, alias='identifier_calibration_reference', description='A digital persistent identifier (e.g., a DOI) referring to a publicly available calibration measurement used for this instrument, e.g., a measurement of a known standard containing calibration information. The axis values may be copied or linked in the appropriate NXcalibration fields for reference.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    calibration_object: Optional[NXNote] = Field(default=None, alias='calibration_object', description='A file serialization of a calibration which may not be publicly available (externally from the NeXus file). This metadata can be a documentation of the source (file) or database (entry) from which pieces of information have been extracted for consumption (e.g. in a research data management system (RDMS)). It is also possible to include the actual file by using the `file` field. The axis values may be copied or linked in the appropriate NXcalibration fields for reference.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    note: Dict[str, NXNote] = Field(default_factory=dict, alias='NOTE', description='The note will contain information about how the data was processed or anything about the data provenance. The contents of the note can be anything that the processing code can understand, or simple text. The name will be numbered to allow for ordering of steps.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    last_process: Optional[Union[str, Value]] = Field(default=None, alias='last_process', description='Indicates the name of the last operation applied in the NXprocess sequence.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    applied: Optional[Union[bool, Value]] = Field(default=None, alias='applied', description='Has the calibration been applied?', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    original_axis: Optional[Union[float, Value]] = Field(default=None, alias='original_axis', description='Array containing the data coordinates in the original uncalibrated axis Unit category: NX_ANY.', json_schema_extra={'nx_unit_category': 'NX_ANY', 'nx_is_attribute': False})
    fit_formula_inputs: Optional[NXParameters] = Field(default=None, alias='fit_formula_inputs', description='Additional input axis to be used in the formula.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    parameters: Dict[str, NXParameters] = Field(default_factory=dict, alias='PARAMETERS', description='Parameters used in performing the data analysis.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    calibration_parameters: Optional[NXParameters] = Field(default=None, alias='calibration_parameters', description='Fit coefficients to be used in ``fit_formula_description``. As an example, for nonlinear energy calibrations, e.g. in a time-of-flight (TOF) detector, a polynomial function is fitted to a set of features (peaks) at well defined energy positions to determine E(TOF). Here we can store the fit coefficients for that procedure.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    fit_formula_description: Optional[Union[str, Value]] = Field(default=None, alias='fit_formula_description', description='Here we can store a description of the formula used for the fit function. For polynomial fits, use a0, a1, ..., an for the coefficients, corresponding to the values in the coefficients group. Use x0, x1, ..., xm for the mth position in the `original_axis` field. If there is the symbol attribute specified for the `original_axis` this may be used instead of x. If you want to use the whole axis use `x`. Alternate axis can also be available as specified by the `fit_formula_inputs` group. The data should then be referred here by the `SYMBOL` name, e.g., for a field name ``my_field`` in ``fit_formula_inputs``, it should be referred here by ``my_field`` or ``my_field0`` if you want to read the zeroth element of the array.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    mapping_mapping: Optional[Union[float, Value]] = Field(default=None, alias='mapping_MAPPING', description='Mapping data for calibration. This can be used to map data points from uncalibrated to calibrated values, i.e., by multiplying each point in the input axis by the corresponding point in the mapping data.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    calibrated_axis: Optional[Union[float, Value]] = Field(default=None, alias='calibrated_axis', description='An array representing the axis after calibration, matching the data length Unit category: NX_ANY.', json_schema_extra={'nx_unit_category': 'NX_ANY', 'nx_is_attribute': False})
    data: Dict[str, NXData] = Field(default_factory=dict, alias='DATA', description='Any data acquired/used during the calibration that does not fit the `NX_FLOAT` fields above. NXdata groups can be used for multidimensional data which are relevant to the calibration', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    default: Optional[Union[str, Value]] = Field(default=None, alias='default', description='.. index:: plotting Declares which child group contains a path leading to a :ref:`NXdata` group. It is recommended (as of NIAC2014) to use this attribute to help define the path to the default dataset to be plotted. See https://www.nexusformat.org/2014_How_to_find_default_data.html for a summary of the discussion.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': True})
