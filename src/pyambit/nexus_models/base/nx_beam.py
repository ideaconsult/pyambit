# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXBeam(BaseModel):
    """Beam which is incident to the sample."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXbeam'

    wavelength: Optional[Union[float, Value]] = Field(default=None, alias='wavelength', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    parameter_reliability: Optional[Union[str, Value]] = Field(default=None, alias='parameter_reliability', description="Select the reliability of the respective beam characteristics. Either, the parameters are measured via another device or method or just given nominally via the properties of a light source properties (532nm, 100mW). Allowed values: ['measured', 'nominal'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    incident_wavelength: Optional[Union[float, Value]] = Field(default=None, alias='incident_wavelength', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    incident_wavelength_spread: Optional[Union[float, Value]] = Field(default=None, alias='incident_wavelength_spread', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    incident_polarization: Optional[Union[float, Value]] = Field(default=None, alias='incident_polarization', description='Polarization vector on entering beamline component Unit category: NX_ANY.', json_schema_extra={'nx_unit_category': 'NX_ANY', 'nx_is_attribute': False})
    extent: Optional[Union[float, Value]] = Field(default=None, alias='extent', description='Size of the beam entering this component. Note this represents a rectangular beam aperture, and values represent FWHM. If applicable, the first dimension shall represent the extent in the direction parallel to the azimuthal reference plane (by default it is [1,0,0]), and the second dimension shall be the normal to the reference plane (by default it is [0,1,0]). Unit category: NX_LENGTH.', json_schema_extra={'nx_unit_category': 'NX_LENGTH', 'nx_is_attribute': False})
