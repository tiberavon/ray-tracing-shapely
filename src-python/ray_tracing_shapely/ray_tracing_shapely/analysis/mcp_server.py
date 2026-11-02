"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Kernel-Embedded MCP Server
===============================================================================
FastMCP SSE server that exposes the ray-tracing analysis tools to GitHub Copilot
(Agent mode), Claude Code, and other MCP clients.

Design: the server runs as a daemon thread INSIDE the Jupyter notebook kernel,
sharing agentic_tools._CONTEXT directly via Python's module-singleton cache.
No Scene or SimulationResult objects are ever serialised — only tool outputs
(SQL rows, ray counts, render file paths) cross the MCP boundary.

Usage from a simulation notebook:
    from ray_tracing_shapely.analysis.agentic_tools import set_context_from_result
    from ray_tracing_shapely.analysis.mcp_server import start_background

    set_context_from_result(scene=my_result.scene, result=my_result.sim_results)
    start_background(port=7654)

Then add to .vscode/mcp.json (GitHub Copilot):
    {"type": "sse", "url": "http://127.0.0.1:7654/sse"}

And to .claude/settings.json (Claude Code):
    {"mcpServers": {"ray-tracing": {"url": "http://127.0.0.1:7654/sse"}}}

Requires: pip install mcp uvicorn
===============================================================================
"""

from __future__ import annotations

import socket
import threading
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .agentic_tools import (
    check_energy_conservation,
    describe_schema,
    fresnel_transmittances_tool,
    highlight_custom_rays_svg,
    highlight_rays_by_polarization_svg,
    highlight_rays_crossing_edge_svg,
    highlight_rays_inside_glass_svg,
    audit_bidirectional_paths,
    list_detectors,
    path_physical_summary_tool,
    path_surfaces_tool,
    paths_by_incidence_angle,
    query_rays,
    rank_bidirectional_paths,
    rank_detector_paths,
    rank_paths_by_energy,
    render_scene_svg,
    tir_analysis_tool,
)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("ray-tracing")

# Register all agentic tools by reference. Because agentic_tools is the same
# module object that the notebook imported, _CONTEXT is shared — the server
# reads live simulation data without any serialisation step.
_EXPOSED_TOOLS = [
    query_rays,
    describe_schema,
    rank_paths_by_energy,
    check_energy_conservation,
    list_detectors,
    rank_detector_paths,
    paths_by_incidence_angle,
    rank_bidirectional_paths,
    path_surfaces_tool,
    audit_bidirectional_paths,
    path_physical_summary_tool,
    fresnel_transmittances_tool,
    tir_analysis_tool,
    render_scene_svg,
    highlight_rays_inside_glass_svg,
    highlight_rays_crossing_edge_svg,
    highlight_rays_by_polarization_svg,
    highlight_custom_rays_svg,
]

for _fn in _EXPOSED_TOOLS:
    mcp.tool()(_fn)


# ---------------------------------------------------------------------------
# Server state — set by start_background(), cleared by stop_background()
# ---------------------------------------------------------------------------

_server: Optional[Any] = None          # uvicorn.Server instance (sse_app() path)
_thread: Optional[threading.Thread] = None


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def is_running(port: int = 7654, host: str = '127.0.0.1') -> bool:
    """Return True if something is accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def stop_background(port: int = 7654, host: str = '127.0.0.1') -> None:
    """
    Stop the MCP server if it was started by this kernel.

    If the server was started via the sse_app() + uvicorn path, it shuts down
    cleanly. If it was started via the mcp.run() fallback path, no handle is
    available — restart the kernel to free the port.

    Args:
        port: Port the server is bound to (default 7654).
        host: Host the server is bound to (default '127.0.0.1').
    """
    global _server, _thread
    if _server is not None:
        _server.should_exit = True
        if _thread is not None and _thread.is_alive():
            _thread.join(timeout=5)
        _server = None
        _thread = None
        print(f'MCP server on port {port} stopped.')
    elif _thread is not None and _thread.is_alive():
        print(
            'Server is running via mcp.run() — no stop handle is available.\n'
            'Restart the kernel to free the port.'
        )
    elif is_running(port, host):
        print(
            f'Port {port} is in use but was not started by this kernel.\n'
            f'Restart the kernel that owns it to free the port.'
        )
    else:
        print(f'No server running on port {port}.')


def start_background(port: int = 7654, host: str = '127.0.0.1') -> None:
    """
    Start the MCP SSE server in a daemon thread inside the notebook kernel.

    Must be called after set_context_from_result() so _CONTEXT is populated.
    The server runs until the kernel shuts down (daemon thread).

    Prefers the sse_app() + uvicorn path (gives a stop handle); falls back to
    mcp.run() for older FastMCP versions where sse_app() is not available.

    Args:
        port: TCP port to bind on localhost (default 7654, fixed by convention).
        host: Hostname to bind (default '127.0.0.1' — loopback only).
    """
    global _server, _thread

    if is_running(port, host):
        if _thread is not None and _thread.is_alive():
            print(f'MCP server already running (this kernel) at http://{host}:{port}/sse')
        else:
            print(
                f'Port {port} is in use by another process.\n'
                f'Call stop_background() if this kernel owns it, '
                f'or restart the owning kernel.'
            )
        return

    if hasattr(mcp, 'sse_app'):
        # Preferred path: drive uvicorn directly so we keep a server handle
        # for clean shutdown via stop_background().
        def _target() -> None:
            global _server
            import asyncio
            import uvicorn
            app = mcp.sse_app()
            config = uvicorn.Config(app, host=host, port=port, log_level='warning')
            srv = uvicorn.Server(config)
            _server = srv
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(srv.serve())
    else:
        # Fallback for FastMCP versions without sse_app(): stop_background()
        # will not be able to cleanly shut down the server.
        def _target() -> None:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                mcp.run(transport='sse', host=host, port=port)
            except TypeError:
                mcp.run(transport='sse')

    _thread = threading.Thread(target=_target, daemon=True, name='mcp-sse-server')
    _thread.start()
    print(f'MCP server started at http://{host}:{port}/sse')
    print(f'mcp.json entry: {{"type": "sse", "url": "http://{host}:{port}/sse"}}')
