"""
Python-specific module: optical_elements package
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
OPTICAL ELEMENTS MODULE
===============================================================================
Top-level module for convenient optical element constructors.

Sub-modules:
- prisms: Prism types with physics-driven constructors
- lenses: (future) Lens types

This module provides convenience constructors that compute vertex geometry
from physical parameters, so users never have to specify raw vertex
coordinates for standard optical element types.
===============================================================================
"""

from .prisms import (
    # Base class
    BasePrism,
    # Prism classes
    EquilateralPrism,
    RightAnglePrism,
    RefractometerPrism,
    DTIRCPrism,
    RXIOptic,
    RRLens,
    RXConcentrator,
    RXIOpticDirect,
    # Factory functions
    equilateral_prism,
    right_angle_prism,
    refractometer_prism,
    dtirc_prism,
    build_angle_transformer,
    # Utility modules
    prism_utils,
    tir_utils,
    nonimaging_geometry,
    sms_chain,
)

from .roles import Role, Mechanism

from .sensors import LinearSensor

from .units import (
    ureg,
    Quantity,
    parse_quantity,
    ensure_quantity,
    ensure_radiometric_quantity,
    parse_radiometric_quantity,
    POWER,
    POWER_PER_LENGTH,
    IRRADIANCE,
    RADIANCE,
    RADIANT_EXPOSURE,
    LENGTH,
    TIME,
    VOLTAGE,
    PHOTOSENSITIVITY,
    SOLID_ANGLE,
    ANGLE,
)
from .physical_scene import PhysicalScene
from .physics import (
    PhysicsContextError,
    ProjectionModel,
    CylindricalPerpendicularProjection,
    PointSourceProjection,
    LambertianStripProjection,
    RevolvedProjection,
    VALID_SYMMETRIES,
    Photoconversion,
    Photoemission,
    LIVCurve,
)
from .eye_safety import iec60825_1, iec62471
from .eye_safety import (
    LimitResult,
    ALPHA_MIN_IEC62471_RAD,
    ALPHA_MIN_IEC60825_1_RAD,
    ALPHA_MAX_RAD,
    clip_alpha,
    alpha_from_axes,
    angle_from_size_distance,
    radiance_from_irradiance,
    irradiance_from_radiance,
    GAMMA_TH_IEC60825_1_RAD,
    alpha_eff_iec62471,
    t2_iec60825_1,
    gamma_ph_iec60825_1,
    limiting_aperture_diameter_iec62471,
    limiting_aperture_diameter_iec60825_1,
    average_over_aperture,
    SpectralPowerDistribution,
    interp_log,
    S_actinic_uv,
    B_blue_light,
    R_retinal_thermal,
    c3_iec60825_1,
    c4_iec60825_1,
    c6_iec60825_1,
    c7_iec60825_1,
)

__all__ = [
    # Base class
    'BasePrism',
    # Prism classes
    'EquilateralPrism',
    'RightAnglePrism',
    'RefractometerPrism',
    'DTIRCPrism',
    # Factory functions
    'equilateral_prism',
    'right_angle_prism',
    'refractometer_prism',
    'dtirc_prism',
    'build_angle_transformer',
    'RXIOptic',
    'RRLens',
    'RXConcentrator',
    'RXIOpticDirect',
    # Utility modules
    'prism_utils',
    'tir_utils',
    'nonimaging_geometry',
    'sms_chain',
    # Roles
    'Role',
    'Mechanism',
    # Sensors
    'LinearSensor',
    # Units (optical_elements_units, P-QUANTITY-PARSING)
    'ureg',
    'Quantity',
    'parse_quantity',
    'ensure_quantity',
    'ensure_radiometric_quantity',
    'parse_radiometric_quantity',
    'POWER',
    'POWER_PER_LENGTH',
    'IRRADIANCE',
    'RADIANCE',
    'RADIANT_EXPOSURE',
    'LENGTH',
    'TIME',
    'VOLTAGE',
    'PHOTOSENSITIVITY',
    'SOLID_ANGLE',
    'ANGLE',
    # Physical scene + photometry
    'PhysicsContextError',
    'PhysicalScene',
    'ProjectionModel',
    'CylindricalPerpendicularProjection',
    'PointSourceProjection',
    'LambertianStripProjection',
    'RevolvedProjection',
    'VALID_SYMMETRIES',
    'Photoconversion',
    'Photoemission',
    'LIVCurve',
    # Eye safety -- P-HAZARD-ROUTINES, dev_doc/architecture/components/eye_safety.md
    'iec60825_1',
    'iec62471',
    'LimitResult',
    'ALPHA_MIN_IEC62471_RAD',
    'ALPHA_MIN_IEC60825_1_RAD',
    'ALPHA_MAX_RAD',
    'clip_alpha',
    'alpha_from_axes',
    'angle_from_size_distance',
    'radiance_from_irradiance',
    'irradiance_from_radiance',
    'GAMMA_TH_IEC60825_1_RAD',
    'alpha_eff_iec62471',
    't2_iec60825_1',
    'gamma_ph_iec60825_1',
    'limiting_aperture_diameter_iec62471',
    'limiting_aperture_diameter_iec60825_1',
    'average_over_aperture',
    'SpectralPowerDistribution',
    'interp_log',
    'S_actinic_uv',
    'B_blue_light',
    'R_retinal_thermal',
    'c3_iec60825_1',
    'c4_iec60825_1',
    'c6_iec60825_1',
    'c7_iec60825_1',
]
