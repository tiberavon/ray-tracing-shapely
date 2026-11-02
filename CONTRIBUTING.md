# Contributing to Ray Tracing Shapely

Thank you for your interest in contributing! This document describes the
conventions, patterns, and architectural decisions you should follow when
working on this codebase.

## Getting Started

### Install from source (editable)

This is a monorepo publishing several independent distributions.
`src-python/<distribution>/` holds one `pyproject.toml` each, sibling to the others,
none special-cased at the repo root. Install the ones you need:

```bash
git clone https://github.com/micheleben/ray_tracing_shapely.git
cd ray_tracing_shapely
pip install -e "src-python/ray_tracing_shapely[dev]"        # core — start here
pip install -e "src-python/ray_tracing_shapely_optiland[dev]"  # 3D verification, planning stage
pip install -e "src-python/optiland_sms[dev]"                  # Optiland SMS plugin, planning stage
```

### Run the tests

Each distribution's tests run from inside its own directory (they are independent
packages, not a single unified test tree):

```bash
cd src-python/ray_tracing_shapely && pytest ray_tracing_shapely/developer_tests/
cd src-python/ray_tracing_shapely_optiland && pytest
cd src-python/optiland_sms && pytest
```

### Notebook hygiene (run this once per machine)

Saving a notebook writes whichever kernel is locally attached into its metadata
(`kernelspec.display_name`/`name`, `language_info.version`) — since every machine
registers its Jupyter kernel under a locally chosen name, this produces a diff on
every commit that touches purely which machine last saved the file, not its content.
`nbstripout` is set up to strip this (plus execution counts and per-cell execution
timestamps, which are the same problem) at commit time, while preserving actual cell
outputs. Run this once on every machine/clone that will commit notebooks — it is
local git configuration, not something that travels with the repository on its own:

```bash
pip install nbstripout
nbstripout --install --attributes .gitattributes
git config filter.nbstripout.clean "nbstripout --keep-output"
git config filter.nbstripout.extrakeys "metadata.kernelspec metadata.language_info.version"
```

`.gitattributes` (committed) tells git which files go through the filter; the four
lines above configure *what the filter does* on this machine, and are not themselves
stored in the repository — `nbstripout --status` shows the active configuration if
you want to confirm a machine is set up correctly.

## Project Layout

```
src-python/
    ray_tracing_shapely/                    # core distribution
        pyproject.toml
        ray_tracing_shapely/
            core/               # Simulation engine (scene, rays, objects, renderer)
            analysis/           # Python-specific analysis utilities
                glass_geometry.py          # Edge descriptions, interfaces, boundaries
                ray_geometry_queries.py    # Spatial queries (rays vs. geometry)
                saving.py                  # CSV/XML export, ray filtering, statistics
                simulation_result.py       # SimulationResult container
                lineage_analysis.py        # Post-hoc ray tree analysis
                fresnel_utils.py           # Standalone Fresnel equation utilities
                agentic_tools.py           # JSON-serializable wrappers for LLM APIs
                tool_registry.py           # Tool discovery registry
            optical_elements/   # Prism design helpers
            examples/           # Example simulations
            developer_tests/    # Development tests
    ray_tracing_shapely_optiland/           # 3D verification satellite (planning stage)
        pyproject.toml
        ray_tracing_shapely_optiland/
        tests/
    optiland_sms/                           # Optiland entry-point plugin (planning stage)
        pyproject.toml
        optiland_sms/
        tests/
dev_doc/architecture/       # Current-state component/port/contract catalogue
dev_doc/concepts/           # Why the code has the shape it has
```

## Coding Conventions

### Type annotations

Use full type annotations on all public functions and methods. Avoid `Any`
unless there is no practical alternative.

```python
def find_rays_inside_glass(segments: List[Ray], glass_obj: Glass) -> List[Ray]:
    ...
```

Use `TYPE_CHECKING` blocks for imports that are only needed by annotations,
to avoid circular imports at runtime:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.scene import Scene
```

### Method return conventions

- **Action methods** (methods that change state) return `bool` — `True` on
  success, `False` on failure.
- **Query methods** return the natural type for the data (a list, a dict, a
  float, etc.).

### Geometry conventions

- All glass polygons use **counter-clockwise (CCW) vertex ordering**, following
  the Shapely convention.
- Glass edges use a **dual-labeling system**: functional labels
  (rotation-invariant, e.g. `"entry_face"`) and cardinal labels
  (scene-orientation-dependent, e.g. `"N"`, `"SE"`).

### Floating-point safety

Always clamp the argument to `[-1.0, 1.0]` before calling `math.acos()`.
Floating-point dot products can produce values slightly outside that range
(e.g. `1.0000000000000002`), causing `ValueError: math domain error`:

```python
import math
angle = math.acos(max(-1.0, min(1.0, dot_product)))
```

## Agentic Tools — Conventions for LLM-Facing Code

The `analysis/agentic_tools.py` module provides wrappers that are designed
for use with LLM tool-use APIs (Claude API, claudette, langchain, etc.).
These wrappers sit between the LLM agent and the core analysis functions.

If you add or modify agentic tool functions, follow the conventions below.

### Structured error responses (mandatory)

Agentic tool functions **must not raise exceptions to the caller**. The
underlying analysis functions may raise freely — the agentic layer catches
and transforms exceptions into structured error dicts.

Every agentic tool returns a `dict` with a `"status"` key:

```python
# Success
{"status": "ok", "data": <result>}

# Failure
{"status": "error", "message": "No object named 'Prism1'. Available: ['Main Prism']"}
```

#### Pattern

```python
def some_agentic_tool(param: str) -> dict:
    """One-line description for the LLM agent."""
    try:
        result = underlying_analysis_function(param)
        return {"status": "ok", "data": result}
    except (ValueError, KeyError) as e:
        return {"status": "error", "message": str(e)}
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
```

#### Rationale

Different frameworks handle Python exceptions differently — claudette
returns the traceback to the LLM, raw API usage crashes the application,
langchain depends on its error handler. A structured dict is universally
safe and gives the agent enough information to recover (e.g. by listing
available object names in the error message).

#### What to catch

- `ValueError` — invalid parameter values (bad glass name, out-of-range
  angle, unknown edge label).
- `KeyError` — missing keys when resolving names or labels.
- `RuntimeError` — context not set, or other precondition failures.

Let unexpected errors (`TypeError`, `AttributeError`, etc.) propagate — they
indicate bugs, not user mistakes.

### JSON-serializable inputs and outputs

All parameters must be JSON-serializable types: `str`, `int`, `float`,
`bool`, or `list`/`dict` of these. No Python objects (Scene, Glass, Ray)
in the signature.

All return values must be JSON-serializable. Use `dict` or `list[dict]`
rather than dataclasses, XML strings, or custom objects.

### Context resolution

Agentic tools resolve live Python objects (scenes, segments) from the
module-level `_CONTEXT` dict, which is populated by `set_context()` or
`set_context_from_result()`. Tools should call `_require_context()` to get
the scene and segments, and return a structured error if the context is not
set.

### Discoverable parameter values

When an agentic tool fails because a parameter value is invalid, the error
message should include the valid alternatives when possible:

```python
# Good
{"status": "error", "message": "No object named 'Prism1'. Available: ['Main Prism', 'Lens A']"}

# Bad
{"status": "error", "message": "Object not found"}
```

This helps the LLM agent self-correct without needing a separate discovery
tool call.

## Commit Messages

Write concise commit messages that focus on the *why*, not the *what*. Use
the imperative mood ("add feature", not "added feature").

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0, consistent with the project license.
