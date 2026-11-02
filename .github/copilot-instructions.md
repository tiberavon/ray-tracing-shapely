# ray_tracing_shapely — GitHub Copilot Instructions

## Project overview
2D ray tracer in Python using Shapely. Simulates refraction, reflection, and total
internal reflection (TIR) through polygonal glass objects.
Python translation of the JavaScript Ray Optics Simulation.

## Core workflow
```python
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.svg_renderer import SVGRenderer
from ray_tracing_shapely.analysis import *

scene = Scene()
scene.ray_density = 72          # ~100 rays/degree
scene.min_brightness_exp = 5    # track secondary paths to 2^-5 brightness
glass = Glass(scene)
glass.path = [{'x': 0, 'y': 0, 'arc': False}, ...]
glass.refIndex = 1.5
glass.name = 'my_glass'
scene.add_object(glass)
scene.auto_label_all_glass_cardinal()   # labels edges N/S/E/W

result = Simulator(scene).run_with_result(name='my_sim')
# result.segments: list[Ray]

renderer = SVGRenderer(width=800, height=600, viewbox=(0, 0, 300, 200))
renderer.draw_scene(scene, result.segments)
```

## Coordinate system
Y increases downward (SVG convention). Edges labeled by `auto_label_all_glass_cardinal()`:
N = top (min Y), S = bottom (max Y), E = right (max X), W = left (min X).

## Key settings
| Setting | Effect |
|---|---|
| `ray_density` | rays per 500° ≈ (ray_density × 100) rays/degree |
| `min_brightness_exp` | track secondary paths to 2^−N brightness |
| `grazing_polarization_ratio_threshold` | T_p/T_s ratio above which a ray is flagged "grazing" |

## MCP agentic tools
When a simulation is running in a Jupyter kernel and `set_context_from_result(scene, result)`
has been called, 11 tools are available via the kernel-embedded MCP server on port 7654.
Setup: run steps 1–3 in `notebooks/abbe_refractometer_llm_playground.ipynb`.

**SQL tools** (require simulation context):
- `query_rays(sql)` — SELECT-only SQL against the ray database
- `describe_schema()` — table names, columns, row counts; call this when unsure of column names

**Analysis tools**:
- `rank_paths_by_energy()` — top energy paths by source label
- `check_energy_conservation()` — energy balance audit
- `fresnel_transmittances_tool(n1, n2, theta_i_deg)` — Fresnel T_s/T_p (standalone, no context needed)
- `tir_analysis_tool(glass_name)` — critical angle, Brewster angle per glass interface

**SVG rendering tools** (require context):
- `render_scene_svg()` — full scene render
- `highlight_rays_inside_glass_svg(glass_name)` — highlight rays inside a named glass
- `highlight_rays_crossing_edge_svg(edge_label)` — highlight rays crossing an edge
- `highlight_rays_by_polarization_svg(threshold)` — highlight high-polarization rays
- `highlight_custom_rays_svg(ray_uuids)` — highlight specific rays by UUID list

MCP config: `.vscode/mcp.json` and `.claude/settings.json` both point to
`http://127.0.0.1:7654/sse`. The server is managed by the notebook kernel — it must
be running before tool calls can succeed.

## SQL database schema (when context is set)
| Table | Key columns |
|---|---|
| `rays` | `uuid`, `brightness_total`, `degree_of_polarization`, `source_name`, `interaction_type` |
| `ray_glass_membership` | `ray_uuid`, `glass_name` |
| `ray_edge_crossing` | `ray_uuid`, `edge_short_label`, `angle_to_normal` |
| `ray_lineage` | `ray_uuid`, `parent_uuid`, `generation` |

`interaction_type` values: `source` | `refract` | `reflect` | `tir`

**Workflow tip:** start with `describe_schema()` if column names are uncertain; use
`query_rays(sql=...)` for all data retrieval (SELECT only — writes are blocked).
