"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Tool Discovery Registry
===============================================================================
Static registry of all public analysis tools.  Provides a single entry point
for agents and users to discover available functions, classes, and their
signatures without reading source files.

The registry is maintained as a hardcoded list alongside the code. Of the
three tool lists (C-AGENT-02), the catalogue and the agentic list are kept
here by hand; the list the MCP server publishes is derived from them
(get_exposed_tools), and a package outside the core adds to all three
through register_tool.
===============================================================================
"""

from __future__ import annotations
import inspect
import sys
from typing import Any, Callable, Dict, List, Optional, Union


# =============================================================================
# Registry data
# =============================================================================

_REGISTRY: List[Dict[str, str]] = [
    # -------------------------------------------------------------------------
    # analysis.glass_geometry -- Glass boundary and edge analysis
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.glass_geometry',
        'name': 'EdgeType',
        'kind': 'Enum',
        'signature': 'LINE, CIRCULAR, EQUATION',
        'description': 'Type of edge geometry',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'EdgeDescription',
        'kind': 'dataclass',
        'signature': 'index, edge_type, p1, p2, midpoint, length, short_label, long_label',
        'description': 'Describes a single edge of a glass object',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'GlassInterface',
        'kind': 'dataclass',
        'signature': 'geometry, glass1, glass2, n1, n2',
        'description': 'Shared edge between two adjacent glass objects',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'GlassBoundary',
        'kind': 'dataclass',
        'signature': 'geometry, glass, n',
        'description': 'Full boundary polygon of a glass object',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'SceneGeometryAnalysis',
        'kind': 'dataclass',
        'signature': 'boundaries, interfaces, exterior_edges',
        'description': 'Complete geometric analysis of a scene\'s glass objects',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'get_edge_descriptions',
        'kind': 'function',
        'signature': '(glass) -> List[EdgeDescription]',
        'description': 'Get detailed descriptions of all edges in a glass object',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'describe_edges',
        'kind': 'function',
        'signature': "(glass, format='text', show_coordinates=True) -> str",
        'description': 'Generate a formatted description of all edges of a glass object',
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'glass_to_polygon',
        'kind': 'function',
        'signature': '(glass) -> Polygon',
        'description': "Convert a Glass object's path to a Shapely Polygon",
    },
    {
        'module': 'analysis.glass_geometry',
        'name': 'analyze_scene_geometry',
        'kind': 'function',
        'signature': '(scene) -> SceneGeometryAnalysis',
        'description': 'Analyze all glass objects in a scene and extract geometric relationships',
    },
    # -------------------------------------------------------------------------
    # analysis.saving -- Ray data export, filtering, and statistics
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.saving',
        'name': 'save_rays_csv',
        'kind': 'function',
        'signature': "(ray_segments, output_path, filename='rays.csv', ...) -> Path",
        'description': 'Export ray segment data to a CSV file',
    },
    {
        'module': 'analysis.saving',
        'name': 'rays_to_xml',
        'kind': 'function',
        'signature': '(ray_segments, precision_coords=4, precision_brightness=6) -> str',
        'description': 'Export ray segment data to an XML string',
    },
    {
        'module': 'analysis.saving',
        'name': 'filter_tir_rays',
        'kind': 'function',
        'signature': '(ray_segments, tir_only=True) -> List[Ray]',
        'description': 'Filter rays based on TIR status',
    },
    {
        'module': 'analysis.saving',
        'name': 'filter_grazing_rays',
        'kind': 'function',
        'signature': '(ray_segments, grazing_only=True, criterion=None) -> List[Ray]',
        'description': 'Filter rays based on grazing incidence status',
    },
    {
        'module': 'analysis.saving',
        'name': 'get_ray_statistics',
        'kind': 'function',
        'signature': '(ray_segments) -> dict',
        'description': 'Compute statistics about a collection of ray segments',
    },
    # -------------------------------------------------------------------------
    # analysis.simulation_result -- Simulation result container
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.simulation_result',
        'name': 'SceneSnapshot',
        'kind': 'dataclass',
        'signature': 'uuid, name, object_count, ...',
        'description': 'Captures the state of a scene at a point in time',
    },
    {
        'module': 'analysis.simulation_result',
        'name': 'SimulationResult',
        'kind': 'dataclass',
        'signature': 'uuid, name, timestamp, segments, lineage, ...',
        'description': 'Container for simulation results with full context',
    },
    {
        'module': 'analysis.simulation_result',
        'name': 'describe_simulation_result',
        'kind': 'function',
        'signature': "(result, format='xml', include_segments=False, max_segments=100) -> str",
        'description': 'Generate a formatted description of a simulation result',
    },
    # -------------------------------------------------------------------------
    # analysis.ray_geometry_queries -- Ray-geometry spatial queries
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'get_object_by_name',
        'kind': 'function',
        'signature': '(scene, name) -> BaseSceneObj',
        'description': 'Find a scene object by its user-defined name',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'get_object_by_uuid',
        'kind': 'function',
        'signature': '(scene, uuid) -> BaseSceneObj',
        'description': 'Find a scene object by UUID (exact or prefix match)',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'get_objects_by_type',
        'kind': 'function',
        'signature': '(scene, type_name) -> List[BaseSceneObj]',
        'description': 'Find all scene objects of a given type',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'find_rays_inside_glass',
        'kind': 'function',
        'signature': '(segments, glass_obj) -> List[Ray]',
        'description': 'Return rays whose midpoint is inside a glass object',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'find_rays_crossing_edge',
        'kind': 'function',
        'signature': '(segments, glass_obj, edge_label) -> List[Ray]',
        'description': 'Return rays that intersect a specific glass edge',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'find_rays_by_angle_to_edge',
        'kind': 'function',
        'signature': '(segments, glass_obj, edge_label, min_angle=0, max_angle=90, proximity=None) -> List[Ray]',
        'description': 'Return rays within an angle range relative to an edge',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'find_rays_by_polarization',
        'kind': 'function',
        'signature': '(segments, min_dop=0, max_dop=1) -> List[Ray]',
        'description': 'Filter rays by degree of polarization',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'interpolate_along_edge',
        'kind': 'function',
        'signature': "(glass_obj, edge_label, fraction=0.5) -> Tuple[float, float]",
        'description': 'Get (x, y) coordinates at a fractional position along a glass edge',
    },
    {
        'module': 'analysis.ray_geometry_queries',
        'name': 'describe_all_glass_edges',
        'kind': 'function',
        'signature': "(scene, format='text') -> str",
        'description': 'Describe all edges of all glass objects in a scene',
    },
    # -------------------------------------------------------------------------
    # analysis.lineage_analysis -- Post-hoc ray tree analysis
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.lineage_analysis',
        'name': 'rank_paths_by_energy',
        'kind': 'function',
        'signature': '(lineage, leaf_uuids=None) -> List[Dict]',
        'description': 'Rank optical paths by terminal segment brightness',
    },
    {
        'module': 'analysis.lineage_analysis',
        'name': 'get_branching_statistics',
        'kind': 'function',
        'signature': '(lineage) -> Dict',
        'description': 'Analyze ray tree branching patterns',
    },
    {
        'module': 'analysis.lineage_analysis',
        'name': 'detect_tir_traps',
        'kind': 'function',
        'signature': '(lineage, min_tir_count=2) -> List[Dict]',
        'description': 'Find ray subtrees trapped by repeated TIR',
    },
    {
        'module': 'analysis.lineage_analysis',
        'name': 'extract_angular_distribution',
        'kind': 'function',
        'signature': '(lineage, leaf_uuids=None) -> List[Dict]',
        'description': 'Compute emission angle for each leaf ray',
    },
    {
        'module': 'analysis.lineage_analysis',
        'name': 'build_angular_histogram',
        'kind': 'function',
        'signature': '(angular_data, n_bins=36, weight_by_energy=True) -> Dict',
        'description': 'Build histogram of emission angles',
    },
    {
        'module': 'analysis.lineage_analysis',
        'name': 'check_energy_conservation',
        'kind': 'function',
        'signature': '(lineage) -> Dict',
        'description': 'Verify energy conservation at each branching point',
    },
    # -------------------------------------------------------------------------
    # analysis.fresnel_utils -- Fresnel equation utilities
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.fresnel_utils',
        'name': 'fresnel_transmittances',
        'kind': 'function',
        'signature': '(n1, n2, theta_i_deg) -> Dict[str, float]',
        'description': 'Compute Fresnel power transmittances and reflectances at an interface',
    },
    {
        'module': 'analysis.fresnel_utils',
        'name': 'critical_angle',
        'kind': 'function',
        'signature': '(n1, n2) -> float',
        'description': 'Compute the critical angle for total internal reflection',
    },
    {
        'module': 'analysis.fresnel_utils',
        'name': 'brewster_angle',
        'kind': 'function',
        'signature': '(n1, n2) -> float',
        'description': "Compute Brewster's angle (where R_p = 0)",
    },
    {
        'module': 'analysis.fresnel_utils',
        'name': 'tir_analysis',
        'kind': 'function',
        'signature': '(n1, n2, theta_i_deg=None, delta_angle_deg=1.0) -> Dict[str, Any]',
        'description': 'Compute TIR angle, phase shifts, and Fresnel quantities for two media',
    },
    # -------------------------------------------------------------------------
    # analysis.agentic_db -- In-memory SQLite database for agentic queries
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.agentic_db',
        'name': 'create_database',
        'kind': 'function',
        'signature': '(scene, segments) -> sqlite3.Connection',
        'description': 'Create and populate in-memory SQLite database from simulation data',
    },
    # -------------------------------------------------------------------------
    # analysis.agentic_tools -- JSON-serializable wrappers for LLM tool-use
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.agentic_tools',
        'name': 'set_context',
        'kind': 'function',
        'signature': '(scene, segments, lineage=None) -> None',
        'description': 'Register simulation objects for agentic tool wrappers',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'set_context_from_result',
        'kind': 'function',
        'signature': '(scene, result) -> None',
        'description': 'Populate agentic tool context from a SimulationResult',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'set_extension_context',
        'kind': 'function',
        'signature': '(key: str, value: Any) -> None',
        'description': "Register a package's live objects under a namespaced key in the same context registry",
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'get_extension_context',
        'kind': 'function',
        'signature': '(key: str, missing: str) -> Any',
        'description': 'The objects a package registered, or RuntimeError with the given message',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'query_rays',
        'kind': 'function',
        'signature': '(sql: str) -> Dict[str, Any]',
        'description': 'Run a read-only SQL SELECT query against the simulation database',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'describe_schema',
        'kind': 'function',
        'signature': '() -> Dict[str, Any]',
        'description': 'Return schema of all tables in the simulation database',
    },
    # Phase 2: Lineage + Fresnel agentic wrappers
    {
        'module': 'analysis.agentic_tools',
        'name': 'rank_paths_by_energy',
        'kind': 'function',
        'signature': '(top_n=10) -> Dict[str, Any]',
        'description': 'Rank optical paths by terminal brightness (requires lineage)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'check_energy_conservation',
        'kind': 'function',
        'signature': '() -> Dict[str, Any]',
        'description': 'Verify energy conservation at each branching point (requires lineage)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'list_contexts',
        'kind': 'function',
        'signature': '() -> Dict[str, Any]',
        'description': 'List the loaded contexts (runs held at once) and which one the tools read',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'set_active_context',
        'kind': 'function',
        'signature': '(context_name) -> Dict[str, Any]',
        'description': 'Make a loaded context the one every tool reads',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'drop_context',
        'kind': 'function',
        'signature': '(context_name) -> Dict[str, Any]',
        'description': 'Free a saved, inactive context\'s memory; load_run_context brings it back',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'load_run_context',
        'kind': 'function',
        'signature': '(run_dir, context_name) -> Dict[str, Any]',
        'description': 'Load a saved run into a new named context, by reference (no live scene)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'save_context_tool',
        'kind': 'function',
        'signature': '(out_dir, design_id, run_id, physical_params=None, numerical_params=None, '
                     'context_name=None) -> Dict[str, Any]',
        'description': 'Save a live context as a run folder that load_run_context can load',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'compare_persisted_runs_tool',
        'kind': 'function',
        'signature': '(run_a, run_b, check_name_topology=True, top_n=20) -> Dict[str, Any]',
        'description': 'Compare two saved runs from disk: names checked, statistics, signature-spectrum diff',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'register_run_file_loader',
        'kind': 'function',
        'signature': '(file_name, loader) -> None',
        'description': 'Let load_run_context load a run-folder file a package outside the core knows',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'list_sources',
        'kind': 'function',
        'signature': '() -> Dict[str, Any]',
        'description': 'List the light sources in the scene and the rays each started (requires context)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'list_detectors',
        'kind': 'function',
        'signature': '() -> Dict[str, Any]',
        'description': 'List all Detector objects in the scene (requires context)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'rank_detector_paths',
        'kind': 'function',
        'signature': '(detector_name, top_n=10) -> Dict[str, Any]',
        'description': 'Rank optical paths that reached a named detector (requires scene + lineage)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'paths_by_incidence_angle',
        'kind': 'function',
        'signature': '(min_deg, max_deg, surface_name=None, top_n=10) -> Dict[str, Any]',
        'description': 'Rank ray segments by angle of incidence in a degree window (requires context + record_surface_hits run)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'fresnel_transmittances_tool',
        'kind': 'function',
        'signature': '(n1, n2, theta_i_deg) -> Dict[str, Any]',
        'description': 'Compute Fresnel transmittances/reflectances at an interface',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'tir_analysis_tool',
        'kind': 'function',
        'signature': '(glass_name_high_n, glass_name_low_n, theta_i_deg=None, delta_angle_deg=1.0) -> Dict[str, Any]',
        'description': 'Compute TIR angle, phase shifts, and Fresnel quantities between two named glasses',
    },
    # Ray-lineage Step C (bidirectional tracing) agentic exposure, C.5
    {
        'module': 'analysis.agentic_tools',
        'name': 'set_bidirectional_context',
        'kind': 'function',
        'signature': '(result: BidirectionalResult) -> None',
        'description': 'Register a BidirectionalResult for rank_bidirectional_paths() (additive to set_context())',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'rank_bidirectional_paths',
        'kind': 'function',
        'signature': '(detector_name=None, top_n=10) -> Dict[str, Any]',
        'description': 'Rank source->detector paths from a bidirectional trace by end-to-end energy (requires set_bidirectional_context)',
    },
    # Bidirectional path-auditing (dev_doc/architecture/components/analysis_signature.md)
    {
        'module': 'analysis.agentic_tools',
        'name': 'path_surfaces_tool',
        'kind': 'function',
        'signature': '(path_uuids: List[str]) -> Dict[str, Any]',
        'description': 'Per-hop surface/edge/interaction_type for a bidirectional path, with the parent/child pairing corrected (requires set_bidirectional_context)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'audit_bidirectional_paths',
        'kind': 'function',
        'signature': '(top_n=20, expected_max_hops=None, allowed_edges=None) -> Dict[str, Any]',
        'description': 'Flag ranked paths exceeding expected_max_hops or touching edges outside allowed_edges (requires set_bidirectional_context)',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'path_physical_summary_tool',
        'kind': 'function',
        'signature': '(path_uuids: List[str]) -> Dict[str, Any]',
        'description': 'Reconstruct a bidirectional path\'s polarization and total length at the detector (requires set_bidirectional_context)',
    },
    # Legacy XML tools (superseded by query_rays, kept for backward compat)
    {
        'module': 'analysis.agentic_tools',
        'name': 'find_rays_inside_glass_xml',
        'kind': 'function',
        'signature': '(glass_name) -> str',
        'description': 'Find rays inside a named glass, return XML string',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'find_rays_crossing_edge_xml',
        'kind': 'function',
        'signature': '(glass_name, edge_label) -> str',
        'description': 'Find rays crossing a named glass edge, return XML string',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'find_rays_by_angle_to_edge_xml',
        'kind': 'function',
        'signature': '(glass_name, edge_label, min_angle=0, max_angle=90) -> str',
        'description': 'Find rays by angle to a named glass edge, return XML string',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'find_rays_by_polarization_xml',
        'kind': 'function',
        'signature': '(min_dop=0, max_dop=1) -> str',
        'description': 'Filter rays by degree of polarization, return XML string',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'render_scene_svg',
        'kind': 'function',
        'signature': '(width=800, height=600, viewbox="auto") -> Dict[str, Any]',
        'description': 'Render full scene, save to file, return descriptor with svg_path and description',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'highlight_rays_inside_glass_svg',
        'kind': 'function',
        'signature': '(glass_name, highlight_color="yellow", width=800, height=600, viewbox="auto") -> Dict[str, Any]',
        'description': 'Highlight rays inside a glass, save to file, return descriptor',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'highlight_rays_crossing_edge_svg',
        'kind': 'function',
        'signature': '(glass_name, edge_label, highlight_color="yellow", width=800, height=600, viewbox="auto") -> Dict[str, Any]',
        'description': 'Highlight rays crossing an edge, save to file, return descriptor',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'highlight_rays_by_polarization_svg',
        'kind': 'function',
        'signature': '(min_dop=0, max_dop=1, highlight_color="magenta", width=800, height=600, viewbox="auto") -> Dict[str, Any]',
        'description': 'Highlight rays by polarization, save to file, return descriptor',
    },
    {
        'module': 'analysis.agentic_tools',
        'name': 'highlight_custom_rays_svg',
        'kind': 'function',
        'signature': '(ray_uuids_csv, highlight_color="yellow", width=800, height=600, viewbox="auto") -> Dict[str, Any]',
        'description': 'Highlight custom rays by uuid, save to file, return descriptor',
    },
    # -------------------------------------------------------------------------
    # analysis.tool_registry -- Tool discovery
    # -------------------------------------------------------------------------
    {
        'module': 'analysis.tool_registry',
        'name': 'list_available_tools',
        'kind': 'function',
        'signature': "(format='text') -> str | Dict",
        'description': 'List all public analysis tools available in the analysis module',
    },
    {
        'module': 'analysis.tool_registry',
        'name': 'get_agentic_tools',
        'kind': 'function',
        'signature': '() -> List[Dict[str, Any]]',
        'description': 'Return agentic tool wrappers with metadata for LLM frameworks',
    },
    {
        'module': 'analysis.tool_registry',
        'name': 'get_exposed_tools',
        'kind': 'function',
        'signature': '() -> List[Callable]',
        'description': 'The agentic tools the MCP server publishes: every agentic tool not withdrawn',
    },
    {
        'module': 'analysis.tool_registry',
        'name': 'register_tool',
        'kind': 'function',
        'signature': '(function, description, input_schema, *, module, expose=True, withdrawn_reason=None) -> bool',
        'description': 'Add an agentic tool from outside the core to the catalogue, the agentic list and the MCP server at once',
    },
    {
        'module': 'analysis.tool_registry',
        'name': 'withdrawn_tools',
        'kind': 'function',
        'signature': '() -> Dict[str, str]',
        'description': 'The agentic tools not published to agents, each with the reason',
    },
    {
        'module': 'analysis.tool_registry',
        'name': 'check_tool_lists',
        'kind': 'function',
        'signature': '() -> List[str]',
        'description': 'Problems with the agreement between the catalogue, the agentic list and the exposed list (C-AGENT-02)',
    },
]


# =============================================================================
# The three lists (C-AGENT-02)
# =============================================================================
#
# _REGISTRY            the Python API catalogue: every public function and
#                      class, agentic or not. A superset of the next.
# get_agentic_tools()  the agent tools, each with a JSON Schema, named by its
#                      function's own __name__ (the name MCP publishes).
# get_exposed_tools()  what the MCP server publishes: every agentic tool
#                      not in _WITHDRAWN_TOOLS. Derived, never written by hand,
#                      so it cannot drift from the agentic list.

#: Agentic tools kept callable from Python (KD12: deprecate rather than
#: remove) but not published to agents, each with the reason.
_WITHDRAWN_TOOLS: Dict[str, str] = {
    'find_rays_inside_glass_xml':
        'superseded by query_rays (SQL over the same rays) and highlight_rays_inside_glass_svg',
    'find_rays_crossing_edge_xml':
        'superseded by query_rays (SQL over the same rays) and highlight_rays_crossing_edge_svg',
    'find_rays_by_angle_to_edge_xml':
        'superseded by query_rays and paths_by_incidence_angle',
    'find_rays_by_polarization_xml':
        'superseded by query_rays and highlight_rays_by_polarization_svg',
}

#: Agentic tools registered from outside the core, through register_tool.
_EXTERNAL_TOOLS: List[Dict[str, Any]] = []


# =============================================================================
# Public API
# =============================================================================

def list_available_tools(format: str = 'text') -> Union[str, Dict[str, List[Dict[str, str]]]]:
    """
    List all public analysis tools available in the analysis module.

    Args:
        format: 'text' for a human-readable table, 'dict' for structured
            data organized by module.

    Returns:
        Formatted string (if format='text') or dict mapping module names
        to lists of tool entries (if format='dict').
    """
    if format == 'dict':
        result: Dict[str, List[Dict[str, str]]] = {}
        for entry in _REGISTRY:
            module = entry['module']
            if module not in result:
                result[module] = []
            result[module].append({
                'name': entry['name'],
                'kind': entry['kind'],
                'signature': entry['signature'],
                'description': entry['description'],
            })
        return result

    # Text format: grouped by module
    lines = []
    current_module = None
    for entry in _REGISTRY:
        if entry['module'] != current_module:
            current_module = entry['module']
            if lines:
                lines.append('')
            lines.append(f'--- {current_module} ---')

        kind_tag = f"[{entry['kind']}]"
        lines.append(f"  {entry['name']:40s} {kind_tag:12s} {entry['description']}")

    return '\n'.join(lines)


def _builtin_agentic_tools() -> List[Dict[str, Any]]:
    """
    The core's own agentic tool wrappers with metadata and JSON Schema definitions.

    Each entry contains:
    - 'name': function name (str)
    - 'function': the callable
    - 'description': one-line description (str)
    - 'input_schema': JSON Schema dict describing the function parameters

    These are framework-agnostic.  To use with a specific framework::

        # claudette
        from claudette import Chat
        tools = [t['function'] for t in get_agentic_tools()]
        chat = Chat(model, tools=tools)

        # langchain
        from langchain.tools import StructuredTool
        tools = [StructuredTool.from_function(t['function']) for t in get_agentic_tools()]

        # Claude API (raw tool definitions)
        tools = [{
            'name': t['name'],
            'description': t['description'],
            'input_schema': t['input_schema'],
        } for t in get_agentic_tools()]

    Returns:
        List of dicts with tool metadata, callables, and JSON Schema definitions.
    """
    from .agentic_tools import (
        list_contexts,
        set_active_context,
        drop_context,
        load_run_context,
        save_context_tool,
        compare_persisted_runs_tool,
        query_rays,
        describe_schema,
        rank_paths_by_energy,
        check_energy_conservation,
        list_detectors,
        list_sources,
        rank_detector_paths,
        paths_by_incidence_angle,
        rank_bidirectional_paths,
        path_surfaces_tool,
        audit_bidirectional_paths,
        path_physical_summary_tool,
        fresnel_transmittances_tool,
        tir_analysis_tool,
        find_rays_inside_glass_xml,
        find_rays_crossing_edge_xml,
        find_rays_by_angle_to_edge_xml,
        find_rays_by_polarization_xml,
        render_scene_svg,
        highlight_rays_inside_glass_svg,
        highlight_rays_crossing_edge_svg,
        highlight_rays_by_polarization_svg,
        highlight_custom_rays_svg,
    )

    # Shared schema fragments for SVG tools
    _SVG_COMMON_PROPS = {
        'width': {
            'type': 'integer',
            'description': 'SVG width in pixels.',
            'default': 800,
        },
        'height': {
            'type': 'integer',
            'description': 'SVG height in pixels.',
            'default': 600,
        },
        'viewbox': {
            'type': 'string',
            'description': 'Viewbox as "min_x,min_y,width,height" or "auto".',
            'default': 'auto',
        },
    }

    return [
        # --- Phase 1: SQL query tools ---
        {
            'name': 'query_rays',
            'function': query_rays,
            'description': 'Run a read-only SQL SELECT query against the simulation database. '
                           'Tables: rays, glass_objects, edges, ray_glass_membership, '
                           'ray_edge_crossing. Only SELECT is allowed. '
                           'Use describe_schema() to see column definitions.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'sql': {
                        'type': 'string',
                        'description': 'A SELECT query against tables: rays, glass_objects, '
                                       'edges, ray_glass_membership, ray_edge_crossing.',
                    },
                },
                'required': ['sql'],
            },
        },
        {
            'name': 'describe_schema',
            'function': describe_schema,
            'description': 'Return schema of all tables in the simulation database '
                           '(columns, types, descriptions, row counts).',
            'input_schema': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
        # --- Phase 2: Lineage + Fresnel tools ---
        {
            'name': 'rank_paths_by_energy',
            'function': rank_paths_by_energy,
            'description': 'Rank optical paths by terminal brightness (highest-energy first). '
                           'Returns path_uuids for use with highlight_custom_rays_svg. '
                           'Requires lineage.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'top_n': {
                        'type': 'integer',
                        'description': 'Maximum number of paths to return (highest-energy first).',
                        'default': 10,
                    },
                },
                'required': [],
            },
        },
        {
            'name': 'check_energy_conservation',
            'function': check_energy_conservation,
            'description': 'Verify energy conservation at each branching point in the ray tree. '
                           'Requires lineage.',
            'input_schema': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
        # --- Contexts: more than one run held at once ---
        {
            'name': 'list_contexts',
            'function': list_contexts,
            'description': 'List the loaded contexts -- runs held at once, each with its own '
                           'rays, lineage and database -- with the one every other tool reads '
                           'marked active: name, origin, segment count, whether it holds a '
                           'bidirectional result, and the packages with objects in it. Use this '
                           'to find context_name values for set_active_context().',
            'input_schema': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
        {
            'name': 'set_active_context',
            'function': set_active_context,
            'description': 'Make a loaded context the active one: every other tool reads it from '
                           'then on. Loading or re-simulating never switches, so this is the one '
                           'way to change what the tools read. An unknown name returns the names '
                           'that exist.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'context_name': {
                        'type': 'string',
                        'description': 'A name from list_contexts().',
                    },
                },
                'required': ['context_name'],
            },
        },
        {
            'name': 'drop_context',
            'function': drop_context,
            'description': 'Free the memory a context holds once you are done with it. Only a context '
                           'saved as a run bundle and not the active one is dropped, so load_run_context '
                           'can always bring it back from the folder this returns; an unsaved live run is '
                           'refused (save it first with save_context_tool). One context per call.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'context_name': {
                        'type': 'string',
                        'description': 'A name from list_contexts(); not the active one.',
                    },
                },
                'required': ['context_name'],
            },
        },
        {
            'name': 'load_run_context',
            'function': load_run_context,
            'description': 'Load a saved run (a folder save_context_tool wrote, or a flow\'s run '
                           'folder holding one) into a new named context, by reference: its ray '
                           'database read-only, its path graph if saved with one, and files the '
                           'packages know (a 3D trace\'s event log). No live scene: query_rays, '
                           'describe_schema and the bidirectional path tools work on it; tools that '
                           'need the scene say so. Never switches: call set_active_context to read it.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'run_dir': {
                        'type': 'string',
                        'description': 'The run folder (<out_dir>/<design_id>/<run_id>).',
                    },
                    'context_name': {
                        'type': 'string',
                        'description': 'A name not in use (list_contexts).',
                    },
                },
                'required': ['run_dir', 'context_name'],
            },
        },
        {
            'name': 'save_context_tool',
            'function': save_context_tool,
            'description': 'Save a live context as a run folder <out_dir>/<design_id>/<run_id> that '
                           'outlives the kernel: the ray database as the tools read it, the run\'s '
                           'statistics, the parameters given, the scene\'s names and, if '
                           'bidirectional, the path graph and signature spectrum. Never overwrites.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'out_dir': {'type': 'string', 'description': 'The folder runs are saved under.'},
                    'design_id': {'type': 'string', 'description': 'The design (a folder name).'},
                    'run_id': {'type': 'string', 'description': 'This run (a folder name, not in use).'},
                    'physical_params': {'type': 'object', 'description': 'The design\'s parameters.'},
                    'numerical_params': {'type': 'object', 'description': 'The run\'s numerical choices.'},
                    'context_name': {
                        'type': 'string',
                        'description': 'The context to save; omit for the active one.',
                    },
                },
                'required': ['out_dir', 'design_id', 'run_id'],
            },
        },
        {
            'name': 'compare_persisted_runs_tool',
            'function': compare_persisted_runs_tool,
            'description': 'Compare two saved runs from disk (neither need be loaded): refused if '
                           'they name different scene objects; then both runs\' parameters and '
                           'statistics and, when both have a path graph, the signatures whose '
                           'energy changed most.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'run_a': {
                        'type': 'string',
                        'description': 'A run folder, or the name of a context loaded from or saved to one.',
                    },
                    'run_b': {'type': 'string', 'description': 'The same, for the other run.'},
                    'check_name_topology': {
                        'type': 'boolean',
                        'description': 'False only to compare different scenes on purpose.',
                        'default': True,
                    },
                    'top_n': {
                        'type': 'integer',
                        'description': 'How many signatures to list, largest change first.',
                        'default': 20,
                    },
                },
                'required': ['run_a', 'run_b'],
            },
        },
        {
            'name': 'list_sources',
            'function': list_sources,
            'description': 'List the light sources in the scene (name, type, uuid, p1, p2, emis_angle, '
                           'brightness, wavelength) and how many rays each started in this run. Use it to '
                           'find a source\'s name, as the targeted_resimulation flow asks for. Requires context.',
            'input_schema': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
        # --- Detector-path tools (ray-lineage Step A agentic exposure) ---
        {
            'name': 'list_detectors',
            'function': list_detectors,
            'description': 'List all Detector objects in the scene (name, uuid, geometry, '
                           'hit_count), including a LinearSensor\'s internal detector '
                           '(\'<sensor_name>_detector\'). Use this to find detector_name '
                           'values for rank_detector_paths(). Requires context.',
            'input_schema': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
        {
            'name': 'rank_detector_paths',
            'function': rank_detector_paths,
            'description': 'Rank the optical paths that actually reached a named detector, '
                           'highest-energy first -- the detector-scoped counterpart to '
                           'rank_paths_by_energy(). Returns path_uuids for use with '
                           'highlight_custom_rays_svg. Requires scene + lineage.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'detector_name': {
                        'type': 'string',
                        'description': 'Name of the Detector in the scene (see list_detectors()).',
                    },
                    'top_n': {
                        'type': 'integer',
                        'description': 'Maximum number of paths to return (highest-energy first).',
                        'default': 10,
                    },
                },
                'required': ['detector_name'],
            },
        },
        # --- Surface-hit geometry tool (ray-lineage Step B agentic exposure) ---
        {
            'name': 'paths_by_incidence_angle',
            'function': paths_by_incidence_angle,
            'description': 'Rank ray segments whose angle of incidence falls in a degree '
                           'window [min_deg, max_deg], highest-brightness first. Surfaces '
                           'Step B hit geometry -- only populated when the run used '
                           'record_surface_hits=True. Compose with rank_detector_paths() to '
                           'ask e.g. "of paths that reached the sensor, which hit the entry '
                           'face above the critical angle?". Requires context.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'min_deg': {
                        'type': 'number',
                        'description': 'Lower bound of the incidence-angle window, in degrees.',
                    },
                    'max_deg': {
                        'type': 'number',
                        'description': 'Upper bound of the incidence-angle window, in degrees.',
                    },
                    'surface_name': {
                        'type': 'string',
                        'description': 'Optional. Restrict to hits on a named object (glass, '
                                       'mirror, detector).',
                    },
                    'top_n': {
                        'type': 'integer',
                        'description': 'Maximum number of segments to return (highest-brightness first).',
                        'default': 10,
                    },
                },
                'required': ['min_deg', 'max_deg'],
            },
        },
        # --- Bidirectional-path tool (ray-lineage Step C agentic exposure, C.5) ---
        {
            'name': 'rank_bidirectional_paths',
            'function': rank_bidirectional_paths,
            'description': 'Rank source->detector paths from a bidirectional (Step C) trace by '
                           'end-to-end energy through a matched forward/backward surface '
                           'connection -- distinct from rank_detector_paths(), which only ranks '
                           'forward-tree terminal brightness. Returns path_uuids for use with '
                           'highlight_custom_rays_svg. Requires set_bidirectional_context() '
                           '(from Simulator.run_bidirectional()). CAVEAT: an empty or sparse '
                           'result can mean the geometry genuinely has no matched paths, OR that '
                           'run_bidirectional()\'s spatial_tolerance/angular_tolerance_deg were '
                           'too tight for this scene\'s ray density -- the two look identical '
                           'from here. If paths are unexpectedly missing, check those tolerance '
                           'values against the scene before concluding the design has none.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'detector_name': {
                        'type': 'string',
                        'description': 'Optional sanity check against the bidirectional '
                                       'result\'s own detector -- not a filter (a '
                                       'BidirectionalResult already belongs to one detector). '
                                       'See list_detectors().',
                    },
                    'top_n': {
                        'type': 'integer',
                        'description': 'Maximum number of paths to return (highest-energy first).',
                        'default': 10,
                    },
                },
                'required': [],
            },
        },
        # --- Bidirectional path-auditing tools
        # (dev_doc/architecture/components/analysis_signature.md) ---
        {
            'name': 'path_surfaces_tool',
            'function': path_surfaces_tool,
            'description': 'Reduce a bidirectional path to its physical hop sequence -- '
                           'surface_name/edge_index/arc_position/hit_point per node, with '
                           'the interaction_type correctly paired to the hop it actually '
                           'happened at (fixes the parent/child pairing rank_bidirectional_paths\' '
                           'path_types is only approximate about). Two hops next to the '
                           'surface connection come back with interaction_type=None -- use '
                           'path_physical_summary for that location. Requires '
                           'set_bidirectional_context(); path_uuids from rank_bidirectional_paths.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'path_uuids': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'The path_uuids list from one rank_bidirectional_paths() entry.',
                    },
                },
                'required': ['path_uuids'],
            },
        },
        {
            'name': 'audit_bidirectional_paths',
            'function': audit_bidirectional_paths,
            'description': 'Flag ranked source->detector paths that exceed expected_max_hops '
                           'or touch a (surface_name, edge_index) outside allowed_edges -- '
                           'finds unintended routes like a stray TIR on an unblocked edge that '
                           'contaminates a measurement. Requires set_bidirectional_context().',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'top_n': {
                        'type': 'integer',
                        'description': 'Maximum number of ranked paths to audit.',
                        'default': 20,
                    },
                    'expected_max_hops': {
                        'type': 'integer',
                        'description': 'Optional. Paths with more nodes than this are flagged.',
                    },
                    'allowed_edges': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {},
                            'description': '[surface_name, edge_index_or_null] pair; '
                                           'null edge_index means "any edge on this surface".',
                        },
                        'description': 'Optional. A path touching a (surface_name, edge_index) '
                                       'not covered by this list is flagged.',
                    },
                },
                'required': [],
            },
        },
        {
            'name': 'path_physical_summary_tool',
            'function': path_physical_summary_tool,
            'description': 'Reconstruct one bidirectional path\'s polarization '
                           '(brightness_s/brightness_p, degree of polarization, '
                           'polarization_ratio) and total geometric length at the detector, '
                           'using the forward ray\'s true post-connection continuation and '
                           'Fresnel-reciprocal backward transfer functions. Requires '
                           'set_bidirectional_context(); path_uuids from rank_bidirectional_paths.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'path_uuids': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'The path_uuids list from one rank_bidirectional_paths() '
                                       'entry, spanning exactly one surface connection.',
                    },
                },
                'required': ['path_uuids'],
            },
        },
        {
            'name': 'fresnel_transmittances_tool',
            'function': fresnel_transmittances_tool,
            'description': 'Compute Fresnel power transmittances and reflectances at a '
                           'planar dielectric interface. Standalone — no context needed.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'n1': {
                        'type': 'number',
                        'description': 'Refractive index of the incident medium.',
                    },
                    'n2': {
                        'type': 'number',
                        'description': 'Refractive index of the transmitting medium.',
                    },
                    'theta_i_deg': {
                        'type': 'number',
                        'description': 'Angle of incidence in degrees (from normal).',
                    },
                },
                'required': ['n1', 'n2', 'theta_i_deg'],
            },
        },
        # --- TIR analysis tool ---
        {
            'name': 'tir_analysis_tool',
            'function': tir_analysis_tool,
            'description': (
                'Compute TIR critical angle, Brewster angle, Fresnel reflectances, '
                'and phase shifts between two named glasses. The first glass must have '
                'the higher refractive index. Optionally provide an angle of incidence; '
                'if omitted, defaults to critical_angle + delta_angle_deg.'
            ),
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name_high_n': {
                        'type': 'string',
                        'description': 'Name of the glass with the higher refractive index.',
                    },
                    'glass_name_low_n': {
                        'type': 'string',
                        'description': 'Name of the glass with the lower refractive index.',
                    },
                    'theta_i_deg': {
                        'type': 'number',
                        'description': (
                            'Angle of incidence in degrees (from normal). '
                            'If omitted, defaults to critical_angle + delta_angle_deg.'
                        ),
                    },
                    'delta_angle_deg': {
                        'type': 'number',
                        'description': (
                            'Proximity threshold in degrees for near-TIR and near-Brewster flags. '
                            'Also used as the offset from TIR when no angle is provided.'
                        ),
                        'default': 1.0,
                    },
                },
                'required': ['glass_name_high_n', 'glass_name_low_n'],
            },
        },
        # --- Legacy XML tools (superseded by query_rays, kept for backward compat) ---
        {
            'name': 'find_rays_inside_glass_xml',
            'function': find_rays_inside_glass_xml,
            'description': 'Find rays inside a named glass, return XML string.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name': {
                        'type': 'string',
                        'description': 'Name of the glass object in the scene.',
                    },
                },
                'required': ['glass_name'],
            },
        },
        {
            'name': 'find_rays_crossing_edge_xml',
            'function': find_rays_crossing_edge_xml,
            'description': 'Find rays crossing a named glass edge, return XML string.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name': {
                        'type': 'string',
                        'description': 'Name of the glass object in the scene.',
                    },
                    'edge_label': {
                        'type': 'string',
                        'description': 'Label of the edge (short_label, long_label, or index).',
                    },
                },
                'required': ['glass_name', 'edge_label'],
            },
        },
        {
            'name': 'find_rays_by_angle_to_edge_xml',
            'function': find_rays_by_angle_to_edge_xml,
            'description': 'Find rays by angle to a named glass edge, return XML string.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name': {
                        'type': 'string',
                        'description': 'Name of the glass object in the scene.',
                    },
                    'edge_label': {
                        'type': 'string',
                        'description': 'Label of the reference edge.',
                    },
                    'min_angle': {
                        'type': 'number',
                        'description': 'Minimum angle from edge normal in degrees.',
                        'default': 0,
                    },
                    'max_angle': {
                        'type': 'number',
                        'description': 'Maximum angle from edge normal in degrees.',
                        'default': 90,
                    },
                },
                'required': ['glass_name', 'edge_label'],
            },
        },
        {
            'name': 'find_rays_by_polarization_xml',
            'function': find_rays_by_polarization_xml,
            'description': 'Filter rays by degree of polarization, return XML string.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'min_dop': {
                        'type': 'number',
                        'description': 'Minimum degree of polarization (0-1).',
                        'default': 0,
                    },
                    'max_dop': {
                        'type': 'number',
                        'description': 'Maximum degree of polarization (0-1).',
                        'default': 1,
                    },
                },
                'required': [],
            },
        },
        # --- SVG rendering tools ---
        {
            'name': 'render_scene_svg',
            'function': render_scene_svg,
            'description': 'Render the full scene and rays; save SVG/PNG to file and return a descriptor with file paths and description.',
            'input_schema': {
                'type': 'object',
                'properties': {**_SVG_COMMON_PROPS},
                'required': [],
            },
        },
        {
            'name': 'highlight_rays_inside_glass_svg',
            'function': highlight_rays_inside_glass_svg,
            'description': 'Render scene with rays inside a glass highlighted; save SVG/PNG to file and return a descriptor.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name': {
                        'type': 'string',
                        'description': 'Name of the glass object.',
                    },
                    'highlight_color': {
                        'type': 'string',
                        'description': 'CSS color for highlighted rays.',
                        'default': 'yellow',
                    },
                    **_SVG_COMMON_PROPS,
                },
                'required': ['glass_name'],
            },
        },
        {
            'name': 'highlight_rays_crossing_edge_svg',
            'function': highlight_rays_crossing_edge_svg,
            'description': 'Render scene with rays crossing an edge highlighted; save SVG/PNG to file and return a descriptor.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'glass_name': {
                        'type': 'string',
                        'description': 'Name of the glass object.',
                    },
                    'edge_label': {
                        'type': 'string',
                        'description': 'Label of the edge.',
                    },
                    'highlight_color': {
                        'type': 'string',
                        'description': 'CSS color for highlighted rays.',
                        'default': 'yellow',
                    },
                    **_SVG_COMMON_PROPS,
                },
                'required': ['glass_name', 'edge_label'],
            },
        },
        {
            'name': 'highlight_rays_by_polarization_svg',
            'function': highlight_rays_by_polarization_svg,
            'description': 'Render scene with rays filtered by polarization highlighted; save SVG/PNG to file and return a descriptor.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'min_dop': {
                        'type': 'number',
                        'description': 'Minimum degree of polarization (0-1).',
                        'default': 0,
                    },
                    'max_dop': {
                        'type': 'number',
                        'description': 'Maximum degree of polarization (0-1).',
                        'default': 1,
                    },
                    'highlight_color': {
                        'type': 'string',
                        'description': 'CSS color for highlighted rays.',
                        'default': 'magenta',
                    },
                    **_SVG_COMMON_PROPS,
                },
                'required': [],
            },
        },
        {
            'name': 'highlight_custom_rays_svg',
            'function': highlight_custom_rays_svg,
            'description': 'Render scene with specific rays (by uuid) highlighted; save SVG/PNG to file and return a descriptor.',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'ray_uuids_csv': {
                        'type': 'string',
                        'description': 'Comma-separated ray uuids to highlight.',
                    },
                    'highlight_color': {
                        'type': 'string',
                        'description': 'CSS color for highlighted rays.',
                        'default': 'yellow',
                    },
                    **_SVG_COMMON_PROPS,
                },
                'required': ['ray_uuids_csv'],
            },
        },
    ]

def get_agentic_tools() -> List[Dict[str, Any]]:
    """
    Return the agentic tool wrappers with metadata and JSON Schema definitions.

    The core's own tools, then any registered from outside it
    (``register_tool``). Each entry: ``name`` (the function's own
    ``__name__``, the name MCP publishes), ``function``, ``description``,
    ``input_schema``. Withdrawn tools are included: they stay callable from
    Python; ``get_exposed_tools`` leaves them out.

    Returns:
        List of dicts with tool metadata, callables, and JSON Schema definitions.
    """
    return _builtin_agentic_tools() + [dict(t) for t in _EXTERNAL_TOOLS]


def get_exposed_tools() -> List[Callable[..., Any]]:
    """
    The functions the MCP server publishes: every agentic tool not withdrawn, in order.

    Returns:
        A list of callables.
    """
    return [t['function'] for t in _published_entries()]


def _published_entries() -> List[Dict[str, Any]]:
    """The agentic entries of the tools the MCP server publishes."""
    return [t for t in get_agentic_tools() if t['name'] not in _WITHDRAWN_TOOLS]


def withdrawn_tools() -> Dict[str, str]:
    """The withdrawn agentic tools: name -> why it is not published."""
    return dict(_WITHDRAWN_TOOLS)


def register_tool(
    function: Callable[..., Any],
    description: str,
    input_schema: Dict[str, Any],
    *,
    module: str,
    expose: bool = True,
    withdrawn_reason: Optional[str] = None,
) -> bool:
    """
    Add an agentic tool from outside the core to all three lists at once.

    A package that depends on the core (the core never imports it) calls
    this from an explicit setup function, not at import time, so importing
    the package does not change what an agent sees.

    Args:
        function: The tool. Its ``__name__`` is its name everywhere.
        description: One paragraph for the agent.
        input_schema: JSON Schema of its parameters.
        module: Where it lives, for the catalogue (``_REGISTRY``).
        expose: Publish it over MCP. False requires ``withdrawn_reason``.
        withdrawn_reason: Why an unexposed tool is not published.

    Returns:
        True.

    Raises:
        ValueError: If the name is taken, or ``expose`` is False without a
            reason (or True with one).
        RuntimeError: If the MCP server is already running: its clients
            have read the tool list, and a tool added now would reach some
            agents and not others.
    """
    name = function.__name__
    if any(t['name'] == name for t in get_agentic_tools()) or any(e['name'] == name for e in _REGISTRY):
        raise ValueError(f"a tool named {name!r} is already registered")
    if expose == (withdrawn_reason is not None):
        raise ValueError(f"{name!r}: give withdrawn_reason exactly when expose is False")
    server = sys.modules.get(__name__.rsplit('.', 1)[0] + '.mcp_server')
    if expose and server is not None and server.is_serving():
        raise RuntimeError(f"cannot register {name!r}: the MCP server is already running; "
                           "register tools before start_background()")
    try:
        signature = str(inspect.signature(function))
    except (TypeError, ValueError):
        signature = '(...)'
    _REGISTRY.append({'module': module, 'name': name, 'kind': 'function', 'signature': signature,
                      'description': description.split('. ')[0]})
    _EXTERNAL_TOOLS.append({'name': name, 'function': function, 'description': description,
                            'input_schema': input_schema})
    if not expose:
        _WITHDRAWN_TOOLS[name] = withdrawn_reason
    elif server is not None:
        server.expose(function)
    return True


def check_tool_lists() -> List[str]:
    """
    What breaks C-AGENT-02's agreement between the three lists, if anything.

    Returns:
        One line per problem; empty when the lists agree.
    """
    problems: List[str] = []
    agentic = get_agentic_tools()
    names = [t['name'] for t in agentic]
    catalogue = {e['name'] for e in _REGISTRY}
    for t in agentic:
        if t['name'] != t['function'].__name__:
            problems.append(f"agentic tool {t['name']!r} is the function {t['function'].__name__!r}: "
                            "MCP publishes the function's name, so the two lists name it differently")
        if t['name'] not in catalogue:
            problems.append(f"agentic tool {t['name']!r} is not in the catalogue (_REGISTRY)")
    for n in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"agentic tool {n!r} is listed more than once")
    for n, reason in _WITHDRAWN_TOOLS.items():
        if n not in names:
            problems.append(f"withdrawn tool {n!r} is not an agentic tool")
        if not reason:
            problems.append(f"withdrawn tool {n!r} has no reason")
    return problems


def generate_tool_note_for_solveit_notebook(tool_list:List[Dict[str, Any]]= None):
    """
    Generate a markdown text which is supposed to be copied in a note in a solve.it notebook.
    This is a little helper function for solve.it.com env, which is a jupyter notebook style
    environment for agent assisted exploratory programming.

    Returns:
        A string with the formatting that is used by solve.it.com.
    """
    if tool_list is None:
        tool_list = _published_entries()
    names = [t['name'] for t in tool_list]
    return f"### optical tools:\ntools from ray_tracing_shapely that you can use: &`[{', '.join(names)}]`"


def generate_tool_note_for_copilot(tool_list: List[Dict[str, Any]] = None) -> str:
    """
    Generate a prompt fragment to paste into GitHub Copilot Agent chat.

    Announces available ray-tracing MCP tools and sets agent expectations.
    Print the output of this function in a notebook cell, then copy-paste it
    as the first message in a Copilot Agent chat session before asking
    questions about the simulation.

    Args:
        tool_list: Optional list of tool dicts (from get_agentic_tools()).
            Defaults to the tools the MCP server publishes: withdrawn ones
            are not announced, since an agent could not call them.

    Returns:
        A markdown string ready to paste into Copilot Agent chat.
    """
    if tool_list is None:
        tool_list = _published_entries()
    names = ', '.join(f'`{t["name"]}`' for t in tool_list)
    return (
        f"**ray_tracing_shapely MCP tools available:** {names}\n\n"
        "The simulation context is set. Use these tools to explore the simulation. "
        "Start with `describe_schema()` if you need to understand the database layout, "
        "or `query_rays(sql=...)` for direct SQL queries against the ray data."
    )
