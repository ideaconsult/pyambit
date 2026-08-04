# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value

from pyambit.nexus_models.base.nx_beam import NXBeam
from pyambit.nexus_models.base.nx_calibration import NXCalibration
from pyambit.nexus_models.base.nx_detector import NXDetector
from pyambit.nexus_models.base.nx_fabrication import NXFabrication
from pyambit.nexus_models.base.nx_monochromator import NXMonochromator
from pyambit.nexus_models.base.nx_program import NXProgram
from pyambit.nexus_models.base.nx_sensor import NXSensor
from pyambit.nexus_models.base.nx_source import NXSource
from pyambit.nexus_models.base.nx_transformations import NXTransformations


class NXInstrument(BaseModel):
    """Metadata of the setup, its optical elements and physical properties which defines the Raman measurement."""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXinstrument'

    scattering_configuration: Optional[Union[str, Value]] = Field(default=None, alias='scattering_configuration', description='Scattering configuration as defined by the porto notation by three states, which are orthogonal to each other. Example: z(xx)z for parallel polarized backscattering configuration. See: https://www.cryst.ehu.es/cgi-bin/cryst/programs/nph-doc-raman A(BC)D A = The propagation direction of the incident light (k_i) B = The polarization direction of the incident light (E_i) C = The polarization direction of the scattered light (E_s) D = The propagation direction of the scattered light (k_s) An orthogonal base is assumed. Linear polarized light is displayed by e.g. "x","y" or "z" Unpolarized light is displayed by "." For non-orthogonal vectors, use the attribute porto_notation_vectors.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    beam_incident: Optional[NXBeam] = Field(default=None, alias='beam_incident', description='Beam which is incident to the sample.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    detector_type: Dict[str, NXDetector] = Field(default_factory=dict, alias='detector_TYPE', description='A detector, detector bank, or multidetector.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    source_type: Dict[str, NXSource] = Field(default_factory=dict, alias='source_TYPE', description='Radiation source emitting a beam. Examples include particle sources (electrons, neutrons, protons) or sources for electromagnetic radiation (photons). This base class can also be used to describe neutron or x-ray storage ring/facilities.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    monochromator: Dict[str, NXMonochromator] = Field(default_factory=dict, alias='MONOCHROMATOR', description='A wavelength defining device. This is a base class for everything which selects a wavelength or energy, be it a monochromator crystal, a velocity selector, an undulator or whatever. The expected units are: * wavelength: angstrom * energy: eV', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    angle_reference_frame: Optional[Union[str, Value]] = Field(default=None, alias='angle_reference_frame', description="Defines the reference frame which is used to describe the sample orientation with respect to the beam directions. A beam centered description is the default and uses 4 angles(similar to XRD): - Omega (angle between sample surface and incident beam) - 2Theta (angle between the transmitted beam and the detection beam) - Chi (sample tilt angle, angle between plane#1 and the surface normal, plane#1 = spanned by incidence beam and detection and detection. If Chi=0°, then plane#1 is the plane of incidence in reflection setups) - Phi (inplane rotation of sample, rotation axis is the samples surface normal) A sample normal centered description is possible as well: - angle of incidence (angle between incident beam and sample surface) - angle of detection (angle between detection beam and sample surface) - angle of incident and detection beam - angle of in-plane sample rotation (direction along the sample's surface normal) Allowed values: ['beam centered', 'sample-normal centered'].", json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    generic_beam_sample_angle_type: Dict[str, NXTransformations] = Field(default_factory=dict, alias='generic_beam_sample_angle_TYPE', description='Set of transformations, describing the relative orientation of different parts of the experiment (beams or sample). You may select one of the specified angles for incident and detection beam or sample, and then use polar and azimuthal angles to define the direction via spherical coordinates. This allows consistent definition between different coordinate system. You may refer to self defined coordinate system as well. If "angle_reference_frame = beam centered", then this coordinate system is used: McStas system (NeXus default) (https://manual.nexusformat.org/design.html#mcstas-and-nxgeometry-system) i.e. the z-coordinate math:`[0,0,1]` is along the incident beam direction and the x-coordinate math:`[1,0,0]` is in the horizontal plane. Hence, usually math:`[0,1,0]` is vertically oriented. If "angle_reference_frame = sample-normal centered", then this coordinate system is used z - math:`[0,0,1]` along sample surface normal x - math:`[1,0,0]` defined by sample surface projected incident beam. y - math:`[0,1,0]` in the sample surface, orthogonal to z and x. For this case, x may be ill defined, if the incident beam is perpendicular to the sample surface. In this case, use the beam centered description.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    temperature_sensor: Optional[NXSensor] = Field(default=None, alias='temperature_sensor', description='A sensor used to monitor an external condition The condition itself is described in :ref:`NXenvironment`.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    device_information: Optional[NXFabrication] = Field(default=None, alias='device_information', description='General device information of the optical spectroscopy setup, if suitable (e.g. for a tabletop spectrometer or other non-custom build setups). For custom build setups, this may be limited to the construction year.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    software_type: Dict[str, NXProgram] = Field(default_factory=dict, alias='software_TYPE', description='Base class to describe a software tool or library.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
    instrument_calibration_device: Dict[str, NXCalibration] = Field(default_factory=dict, alias='instrument_calibration_DEVICE', description='Pre-calibration of an arbitrary device of the instrumental setup, which has the name DEVICE. You can specify here how, at which time by which method the calibration was done. As well the accuracy and a link to the calibration dataset.', json_schema_extra={'nx_unit_category': None, 'nx_is_attribute': False})
