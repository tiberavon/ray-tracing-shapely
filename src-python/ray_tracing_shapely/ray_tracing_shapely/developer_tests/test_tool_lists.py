"""
Python-specific module: test tool lists
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

===============================================================================
The three tool lists agree (C-AGENT-02), and a tool from outside the core
reaches all three at once
===============================================================================
The catalogue (_REGISTRY), the agentic list (get_agentic_tools) and what the
MCP server publishes (get_exposed_tools) are checked here without the mcp
package: the exposed list is derived in tool_registry, so these tests run
where mcp is not installed, which is where the older per-tool MCP checks
skipped silently.
===============================================================================
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types

import pytest

from ray_tracing_shapely.analysis import tool_registry
from ray_tracing_shapely.analysis.tool_registry import (check_tool_lists, generate_tool_note_for_copilot,
                                                        generate_tool_note_for_solveit_notebook, get_agentic_tools,
                                                        get_exposed_tools, list_available_tools, register_tool,
                                                        withdrawn_tools)

#: What the MCP server published while its list was written by hand.
PUBLISHED_BEFORE = [
    'query_rays', 'describe_schema', 'rank_paths_by_energy', 'check_energy_conservation', 'list_detectors',
    'rank_detector_paths', 'paths_by_incidence_angle', 'rank_bidirectional_paths', 'path_surfaces_tool',
    'audit_bidirectional_paths', 'path_physical_summary_tool', 'fresnel_transmittances_tool',
    'tir_analysis_tool', 'render_scene_svg', 'highlight_rays_inside_glass_svg',
    'highlight_rays_crossing_edge_svg', 'highlight_rays_by_polarization_svg', 'highlight_custom_rays_svg',
]


@pytest.fixture
def clean_lists(monkeypatch):
    """Registration changes module state: give each test its own copies."""
    monkeypatch.setattr(tool_registry, '_REGISTRY', list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, '_EXTERNAL_TOOLS', [])
    monkeypatch.setattr(tool_registry, '_WITHDRAWN_TOOLS', dict(tool_registry._WITHDRAWN_TOOLS))
    monkeypatch.delitem(sys.modules, 'ray_tracing_shapely.analysis.mcp_server', raising=False)


def test_the_three_lists_agree():
    assert check_tool_lists() == []


def test_exposed_is_agentic_minus_withdrawn_and_unchanged():
    exposed = [f.__name__ for f in get_exposed_tools()]
    assert exposed == PUBLISHED_BEFORE
    agentic = [t['name'] for t in get_agentic_tools()]
    assert sorted(set(agentic) - set(exposed)) == sorted(withdrawn_tools())
    assert sorted(withdrawn_tools()) == ['find_rays_by_angle_to_edge_xml', 'find_rays_by_polarization_xml',
                                         'find_rays_crossing_edge_xml', 'find_rays_inside_glass_xml']


def test_the_paste_in_notes_announce_only_published_tools():
    """The incident C-AGENT-02 records: tools announced to the assistant that
    the server does not publish. The notes now name exactly the published list."""
    for note in (generate_tool_note_for_copilot(), generate_tool_note_for_solveit_notebook()):
        for name in PUBLISHED_BEFORE:
            assert name in note
        for name in withdrawn_tools():
            assert name not in note


def _tool_a(x: int = 1) -> dict:
    return {'status': 'ok', 'x': x}


def _tool_b() -> dict:
    return {'status': 'ok'}


def test_a_registered_tool_reaches_all_three(clean_lists):
    schema = {'type': 'object', 'properties': {'x': {'type': 'integer'}}}
    assert register_tool(_tool_a, 'A tool. More.', schema, module='satellite.agentic') is True
    assert check_tool_lists() == []
    assert get_agentic_tools()[-1]['name'] == '_tool_a'
    assert get_exposed_tools()[-1] is _tool_a
    assert '_tool_a' in list_available_tools('text')

    register_tool(_tool_b, 'B.', {'type': 'object'}, module='satellite.agentic', expose=False,
                  withdrawn_reason='for Python only')
    assert _tool_b not in get_exposed_tools() and withdrawn_tools()['_tool_b'] == 'for Python only'


def test_registration_refuses_a_taken_name_and_a_missing_reason(clean_lists):
    with pytest.raises(ValueError, match="already registered"):
        register_tool(get_agentic_tools()[0]['function'], 'dup', {}, module='m')
    with pytest.raises(ValueError, match="withdrawn_reason exactly when"):
        register_tool(_tool_a, 'A.', {}, module='m', expose=False)
    with pytest.raises(ValueError, match="withdrawn_reason exactly when"):
        register_tool(_tool_a, 'A.', {}, module='m', withdrawn_reason='why')


def test_registration_after_the_server_started_is_refused(clean_lists, monkeypatch):
    exposed = []
    fake = types.SimpleNamespace(is_serving=lambda: True, expose=exposed.append)
    monkeypatch.setitem(sys.modules, 'ray_tracing_shapely.analysis.mcp_server', fake)
    with pytest.raises(RuntimeError, match="already running"):
        register_tool(_tool_a, 'A.', {}, module='m')
    assert check_tool_lists() == [] and exposed == []          # nothing half-registered

    fake.is_serving = lambda: False
    register_tool(_tool_a, 'A.', {}, module='m')
    assert exposed == [_tool_a]                                 # a loaded, idle server gets it at once


def test_the_mcp_server_publishes_exactly_the_exposed_tools():
    """Where mcp is installed the server must import and publish the derived list.

    Not an ImportError skip: an mcp that installs but breaks the server (as
    2.x does, which renamed FastMCP) must fail here, not pass silently.
    """
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("mcp not installed (the agentic extra)")
    from ray_tracing_shapely.analysis import mcp_server

    published = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]
    assert published == [f.__name__ for f in get_exposed_tools()]
