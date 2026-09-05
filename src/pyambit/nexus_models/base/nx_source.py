# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value

from pyambit.nexus_models.base.nx_fabrication import NXFabrication


class NXSource(BaseModel):
    """Radiation source emitting a beam. Examples include particle sources (electrons, neutrons, protons) or sources for electromagnetic radiation (photons). This base class can also be used to describe neutron or x-ray storage ring/facilities."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXsource'

    type: Optional[Union[str, Value]] = Field(default=None, alias='type', description="type of radiation source (pick one from the enumerated list and spell exactly) Suggested values: ['Synchrotron X-ray Source', 'Rotating Anode X-ray', 'Fixed Tube X-ray', 'UV Laser', 'Optical Laser', 'Laser', 'Dye-Laser', 'Broadband Tunable Light Source', 'Halogen lamp', 'LED', 'Mercury Cadmium Telluride', 'Deuterium Lamp', 'Xenon Lamp', 'Globar'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    name: Optional[Union[str, Value]] = Field(default=None, alias='name', description='Name of source', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    device_information: Optional[NXFabrication] = Field(default=None, alias='device_information', description='Details about the device information.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    associated_beam: Optional[Union[str, Value]] = Field(default=None, alias='associated_beam', description='The path to a beam emitted by this source. Should be named with the same appendix, e.g., for TYPE=532nmlaser, there should as well be a NXbeam named "beam_532nmlaser" together with this source instance named "source_532nmlaser" Example: /entry/instrument/beam_532nmlaser', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
