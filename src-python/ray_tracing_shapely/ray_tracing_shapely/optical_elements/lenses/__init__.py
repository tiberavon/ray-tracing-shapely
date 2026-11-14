"""
Python-specific module: lenses package
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

Labelled, exportable lenses (BasePrism subclasses with curved surfaces).

Classes:
- SingletLens: one piece of glass, two spherical or flat faces, Optiland's
  radius convention.
- TIRCollimator: the LED collimator of US 7,762,697 B2, FIG. 3, revolved: a
  central lens and a TIR ring, both designed to collimate a point F.
- FresnelLens: a straight-facet Fresnel collimator for a point F, grooves
  towards it or away.

Modules:
- collimator_design: the constant-path constructions both collimators use.
- profile_scan: a measured lens face, read from a profilometer's DXF, and an
  even asphere fitted to it with its vertex and tilt.
"""

from .fresnel import FresnelLens
from .profile_scan import ProfileScan, ScanFit, fit_scan_asphere, read_profile_scan
from .singlet import SingletLens, surface_sag
from .tir_collimator import TIRCollimator

__all__ = ["FresnelLens", "ProfileScan", "ScanFit", "SingletLens", "TIRCollimator", "fit_scan_asphere",
           "read_profile_scan", "surface_sag"]
