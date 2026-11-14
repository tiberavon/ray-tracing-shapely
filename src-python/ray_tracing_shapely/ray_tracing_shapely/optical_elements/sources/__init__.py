"""
Python-specific package: optical_elements.sources
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

Light sources written here: a source that emits a given list of rays, the
source specification that builds one source in 2D and in 3D, and a reader
for a measured LED's rayfile (IES TM-25), its slice into the 2D plane, and its
radiation plot.
"""

from .ray_set_source import RaySetSource
from .rayfile import Rayfile, intensity_vs_angle, read_rayfile, write_tm25
from .rayfile_slice import RayfileSlice, slice_rayfile
from .radiation_plot import RadiationPattern, radiation_pattern, radiation_plot_svg
from .source_spec import (build_source_2d, file_sha256, merged_sources, patch_centre, patch_section,
                          profile_sources, rayfile_source_spec, source_axes, spec_rayfile, validate_source_spec)

__all__ = ["RadiationPattern", "RaySetSource", "Rayfile", "RayfileSlice", "build_source_2d", "file_sha256", "intensity_vs_angle", "merged_sources", "patch_centre",
           "patch_section", "profile_sources", "radiation_pattern", "radiation_plot_svg", "rayfile_source_spec", "read_rayfile", "slice_rayfile", "source_axes",
           "spec_rayfile", "validate_source_spec",
           "write_tm25"]
