"""
Original work Copyright 2024 The Ray Optics Simulation authors and contributors
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
Constants used throughout the ray optics simulation.

This module contains constants that would typically be in the Simulator class
in the JavaScript version, but are extracted here for easier access by mixins
and other modules without circular dependencies.
"""

# Minimum ray segment length to avoid numerical issues
# Must match JavaScript value of 1e-6 for correct behavior
# The offset workaround was removed, so this value must be 1e-6
MIN_RAY_SEGMENT_LENGTH = 1e-6

# Minimum ray segment length squared (for performance, to avoid sqrt in comparisons)
MIN_RAY_SEGMENT_LENGTH_SQUARED = MIN_RAY_SEGMENT_LENGTH * MIN_RAY_SEGMENT_LENGTH

# Edge detection threshold - much smaller than MIN_RAY_SEGMENT_LENGTH
# Used to detect when a ray hits exactly at a vertex (geometrically ambiguous)
# Should be small enough to only catch actual vertex hits, not near-vertex intersections
EDGE_DETECTION_THRESHOLD = 1e-9
EDGE_DETECTION_THRESHOLD_SQUARED = EDGE_DETECTION_THRESHOLD * EDGE_DETECTION_THRESHOLD

# Wavelengths (in nanometers)
UV_WAVELENGTH = 380          # Ultraviolet wavelength boundary
INFRARED_WAVELENGTH = 700    # Infrared wavelength boundary
GREEN_WAVELENGTH = 532       # Default green wavelength for lasers
RED_WAVELENGTH = 650
BLUE_WAVELENGTH = 450

# Add other Simulator constants as needed when translating more modules
