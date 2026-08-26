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

===============================================================================
PYTHON-SPECIFIC MODULE: Analysis Utilities
===============================================================================
This module is a Python-specific addition and does NOT exist in the original
JavaScript Ray Optics Simulation codebase. It provides analysis utilities for
extracting geometric information from scenes, such as:

- Glass boundary properties (area, centroid, perimeter)
- Interface detection between adjacent glass objects
- Interface properties (length, center, normal vectors)

These utilities leverage the Shapely library for computational geometry
operations that are not available in the JavaScript version.
===============================================================================
"""


from .glass_geometry import (
    GlassInterface,
    GlassBoundary,
    SceneGeometryAnalysis,
    analyze_scene_geometry,
    glass_to_polygon,
    # Edge description (Python-specific)
    EdgeType,
    EdgeDescription,
    get_edge_descriptions,
    describe_edges,
    # Prism description (Python-specific)
    describe_prism,
)
from .saving import (
    save_rays_csv,
    rays_to_xml,
    filter_tir_rays,
    filter_grazing_rays,
    get_ray_statistics,
)
from .simulation_result import (
    SceneSnapshot,
    SimulationResult,
    describe_simulation_result,
)
from .ray_geometry_queries import (
    # Phase 0: Scene object lookup
    get_object_by_name,
    get_object_by_uuid,
    get_objects_by_type,
    # Phase 1: Ray-geometry queries
    find_rays_inside_glass,
    find_rays_crossing_edge,
    find_rays_by_angle_to_edge,
    find_rays_by_polarization,
    # Phase 2: Geometry convenience utilities
    interpolate_along_edge,
    normal_along_edge,
    describe_all_glass_edges,
)
from .fresnel_utils import (
    fresnel_transmittances,
    critical_angle,
    brewster_angle,
    tir_analysis,
)
from .tool_registry import (
    list_available_tools,
    get_agentic_tools,
    generate_tool_note_for_solveit_notebook,
    generate_tool_note_for_copilot,
)
from .agentic_tools import (
    set_context,
    set_context_from_result,
    get_context,
    clear_context,
    # Phase 1: SQL query tools
    query_rays,
    describe_schema,
    # Phase 2: Lineage + Fresnel agentic wrappers
    rank_paths_by_energy,
    check_energy_conservation,
    fresnel_transmittances_tool,
    tir_analysis_tool,
    # Legacy XML tools (backward compat)
    find_rays_inside_glass_xml,
    find_rays_crossing_edge_xml,
    find_rays_by_angle_to_edge_xml,
    find_rays_by_polarization_xml,
    # Phase 3: SVG rendering tools
    render_scene_svg,
    highlight_rays_inside_glass_svg,
    highlight_rays_crossing_edge_svg,
    highlight_rays_by_polarization_svg,
    highlight_custom_rays_svg,
)
from .render_result import (
    save_render,
    reset_render_counter,
)
from .agentic_db import (
    create_database,
)

__all__ = [
    # Glass geometry analysis
    'GlassInterface',
    'GlassBoundary',
    'SceneGeometryAnalysis',
    'analyze_scene_geometry',
    'glass_to_polygon',
    # Edge description (Python-specific)
    'EdgeType',
    'EdgeDescription',
    'get_edge_descriptions',
    'describe_edges',
    # Prism description (Python-specific)
    'describe_prism',
    # Ray data export and statistics
    'save_rays_csv',
    'rays_to_xml',
    'filter_tir_rays',
    'filter_grazing_rays',
    'get_ray_statistics',
    # Simulation result container (Python-specific)
    'SceneSnapshot',
    'SimulationResult',
    'describe_simulation_result',
    # Scene object lookup (Python-specific)
    'get_object_by_name',
    'get_object_by_uuid',
    'get_objects_by_type',
    # Ray-geometry queries (Python-specific)
    'find_rays_inside_glass',
    'find_rays_crossing_edge',
    'find_rays_by_angle_to_edge',
    'find_rays_by_polarization',
    'interpolate_along_edge',
    'normal_along_edge',
    'describe_all_glass_edges',
    # Fresnel equation utilities (Python-specific)
    'fresnel_transmittances',
    'critical_angle',
    'brewster_angle',
    'tir_analysis',
    # Tool discovery (Python-specific)
    'list_available_tools',
    'get_agentic_tools',
    'generate_tool_note_for_solveit_notebook',
    'generate_tool_note_for_copilot',
    # Agentic tools -- JSON-serializable wrappers (Python-specific)
    'set_context',
    'set_context_from_result',
    'get_context',
    'clear_context',
    'query_rays',
    'describe_schema',
    'rank_paths_by_energy',
    'check_energy_conservation',
    'fresnel_transmittances_tool',
    'tir_analysis_tool',
    # Phase 3: Render result layer
    'save_render',
    'reset_render_counter',
    'create_database',
    'find_rays_inside_glass_xml',
    'find_rays_crossing_edge_xml',
    'find_rays_by_angle_to_edge_xml',
    'find_rays_by_polarization_xml',
    # Phase 3: SVG rendering tools
    'render_scene_svg',
    'highlight_rays_inside_glass_svg',
    'highlight_rays_crossing_edge_svg',
    'highlight_rays_by_polarization_svg',
    'highlight_custom_rays_svg',
]

