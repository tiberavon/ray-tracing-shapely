"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Render Result Layer
===============================================================================
Thin layer between SVGRenderer and the agentic tools.  Saves SVG strings to
files, optionally converts to PNG via cairosvg, and returns JSON-serializable
descriptors that LLM agents can work with.

The SVGRenderer itself is NOT modified — this module operates on the SVG
string output and handles the file I/O + metadata wrapping.
===============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional


# Module-level render counter for auto-generating unique filenames
_render_counter: int = 0


def reset_render_counter() -> None:
    """Reset the render counter to 0 (called by clear_context())."""
    global _render_counter
    _render_counter = 0


def _svg_to_png(
    svg_string: str,
    png_path: str,
    width: int,
    height: int,
) -> bool:
    """
    Convert an SVG string to PNG using cairosvg (optional dependency).

    Args:
        svg_string: The SVG content as a string.
        png_path: File path where the PNG should be saved.
        width: Output PNG width in pixels.
        height: Output PNG height in pixels.

    Returns:
        True if conversion succeeded, False if cairosvg is not installed.
    """
    try:
        import cairosvg
        cairosvg.svg2png(
            bytestring=svg_string.encode('utf-8'),
            write_to=png_path,
            output_width=width,
            output_height=height,
        )
        return True
    except (ImportError, OSError):
        return False


def save_render(
    svg_string: str,
    render_dir: str,
    prefix: str,
    width: int,
    height: int,
    description: str,
    highlight_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Save an SVG string to file, optionally convert to PNG, return descriptor.

    Auto-generates filenames using a module-level counter:
    ``{prefix}_{counter:03d}.svg`` (and ``.png`` if cairosvg is available).

    Args:
        svg_string: The SVG content from SVGRenderer.to_string().
        render_dir: Directory path where files will be saved.
        prefix: Filename prefix (e.g. 'scene', 'highlight_inside').
        width: SVG/PNG width in pixels.
        height: SVG/PNG height in pixels.
        description: Human-readable description of what the render shows.
        highlight_summary: Optional dict with highlight details (filter type,
            highlighted ray count, glass name, etc.).

    Returns:
        JSON-serializable descriptor dict with file paths and metadata.
    """
    global _render_counter
    _render_counter += 1

    render_path = Path(render_dir)
    render_path.mkdir(parents=True, exist_ok=True)

    base_name = f"{prefix}_{_render_counter:03d}"
    svg_path = render_path / f"{base_name}.svg"
    png_path = render_path / f"{base_name}.png"

    # Save SVG
    svg_path.write_text(svg_string, encoding='utf-8')

    # Attempt PNG conversion
    png_ok = _svg_to_png(svg_string, str(png_path), width, height)

    result: Dict[str, Any] = {
        'svg_path': str(svg_path),
        'png_path': str(png_path) if png_ok else None,
        'png_available': png_ok,
        'width': width,
        'height': height,
        'description': description,
        'highlight_summary': highlight_summary,
    }

    return result
