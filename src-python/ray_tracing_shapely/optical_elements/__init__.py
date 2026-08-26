"""
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

from .physical_scene import PhysicalScene
from .physics import (
    PhysicsContextError,
    ProjectionModel,
    CylindricalPerpendicularProjection,
    PointSourceProjection,
    LambertianStripProjection,
    Photoconversion,
    Photoemission,
    LIVCurve,
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
    # Physical scene + photometry
    'PhysicsContextError',
    'PhysicalScene',
    'ProjectionModel',
    'CylindricalPerpendicularProjection',
    'PointSourceProjection',
    'LambertianStripProjection',
    'Photoconversion',
    'Photoemission',
    'LIVCurve',
]
