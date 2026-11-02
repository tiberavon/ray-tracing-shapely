# Ray Tracing Shapely prv_dev
this repo is the private version of my other repo  ray_tracing_shapely

## Process followed to create a private repo from a public one
- Duplicate your public repo (se  instructions at https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository)
    To maintain a mirror of a repository without forking it, you can run a special clone command, then mirror-push to the new repository
    + Create a **private** repository in github, e.g.  https://github.com/EXAMPLE-USER/NEW-REPOSITORY.git
    + Create a bare clone of the public repository.
        ```bash
        git clone --bare https://github.com/EXAMPLE-USER/OLD-REPOSITORY.git
        ```
    + Mirror-push to the new repository.
        ```bash
        cd OLD-REPOSITORY
        git push --mirror https://github.com/EXAMPLE-USER/NEW-REPOSITORY.git
        ```
    + Remove the temporary local repository you created earlier.        
        ```bash
        cd ..
        rm -rf OLD-REPOSITORY
        ```

- Clone the private new repo  to your machine.
    ```bash
    git clone https://github.com/EXAMPLE-USER/NEW-REPOSITORY.git
    ```
- In this local clone of your private repo **add a remote to your public repo:** 
    ```bash
    git remote add public git@github.com:...
    ```

- Push branches with commits intended for your public repo to that new public remote. Make sure you don't accidentally commit private-only code.
- You can bring in changes from your public repo using 
    ``` bash
    git fetch public 
    ```
    and then merge them locally and push to your remote private repo (origin remote).

## Ray Tracing Shapely

A Python ray tracing library using Shapely for computational geometry operations.

The project has started as a translation of the original [Ray Optics Simulation](https://github.com/ricktu288/ray-optics) JavaScript project. Original work copyright 2024 The Ray Optics Simulation authors 
and contributors.

If you use this please give credits to the original authors ( see section Acknowledgments)

## Overview

This library provides a Python implementation for 2D ray tracing simulations, including:

- **Core simulation engine** - Ray tracing through optical elements (lenses, prisms, mirrors)
- **Optical elements** - Glass objects, ideal lenses, spherical lenses, blockers, detectors
- **Nonimaging optics** - CPC-family concentrators (DTIRC, angle transformer, RXI) and Miñano–Benítez Simultaneous Multiple Surface (SMS) profile construction (RR/RX/RXI), built on a reusable 2-D geometry toolbox (Python-specific)
- **Light sources** - Point sources, beams, single rays, angle sources
- **Analysis utilities** - Geometric analysis of glass interfaces and boundaries (Python-specific)
- **Visualization** - SVG rendering of ray diagrams, with diagram-annotation helpers (point markers, vectors, angle arcs) for pedagogical overlays (Python-specific)

## Installation

Library is not in its complete version (part of the original work is not translated). Contributions are welcomed!

still in test.pypi.org (version 0.1.0). Install via pip from TestPyPI:
```bash
pip install -i https://test.pypi.org/simple/ ray-tracing-shapely==0.1.0
```

Or install from source:
We are currently in early development stage, so it is recommended to install from source:
current version is 0.2.0
```bash
git clone https://github.com/micheleben/ray_tracing_shapely.git
cd ray_tracing_shapely
pip install -e "src-python/ray_tracing_shapely"
```

(This repo is a monorepo publishing more than one distribution — see `CONTRIBUTING.md`
for the others. The command above installs just the core `ray-tracing-shapely` library.)

## Quick Start

```python
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs import Glass, SingleRay
from ray_tracing_shapely.core.simulator import Simulator

# Create a scene
scene = Scene()
scene.color_mode = 'linear'

# Add a glass prism
prism = Glass(scene)
prism.path = [
    {'x': 100, 'y': 50, 'arc': False},
    {'x': 200, 'y': 50, 'arc': False},
    {'x': 150, 'y': 150, 'arc': False}
]
prism.refIndex = 1.5
scene.add_object(prism)

# Add a light ray
ray = SingleRay(scene)
ray.p1 = {'x': 50, 'y': 100}
ray.p2 = {'x': 100, 'y': 100}
scene.add_object(ray)

# Run simulation
simulator = Simulator(scene, max_rays=1000)
segments = simulator.run()

print(f"Traced {len(segments)} ray segments")
```

## Nonimaging Optics (Python-Specific)

The `optical_elements.prisms` module provides CPC-family concentrators and
Miñano–Benítez Simultaneous Multiple Surface (SMS) design-method
constructions, grounded directly against Chaves, *Introduction to
Nonimaging Optics* (2nd ed., CRC Press) and Winston/Miñano/Benítez,
*Nonimaging Optics* (Elsevier, 2005) -- every class below carries
equation-level citations in its own docstring.

### Concentrator devices

```python
from ray_tracing_shapely.optical_elements.prisms import (
    DTIRCPrism, build_angle_transformer, RXIOptic,
)

# Dielectric TIR concentrator with a circular-arc entrance aperture
dtirc = DTIRCPrism(scene, theta_deg=10, n=1.5, size=1.0)

# Air-filled mirror composite transforming acceptance angle theta1 -> theta2
angle_transformer = build_angle_transformer(scene, theta1_deg=15, theta2_deg=60, exit_width=1.0)

# RXI-style dome (dielectric front surface + mirrored back), a mesh-refinement fixture
rxi = RXIOptic(scene, n=1.5, size=1.0)
```

### SMS profile construction (RR / RX / RXI)

Built on a shared alternating "SMS chain" engine
(`optical_elements.prisms.sms_chain`) that reproduces the book's own
worked examples exactly:

```python
from ray_tracing_shapely.optical_elements.prisms import RRLens, RXConcentrator, RXIOpticDirect

# Two-surface RR lens designed so E1->R2 and E2->R1 (the "crossed" condition)
rr_lens = RRLens(
    scene, e1=(-1, 2), e2=(1, 2), r1=(-0.5, -2), r2=(0.5, -2),
    seed_n_angle_deg=303.3, seed_x_angle_deg=42.7, n=1.5, etendue=1.0,
)

# RX concentrator: refractive top surface + mirror-coated bottom surface
rx = RXConcentrator(scene, r1=(-0.5, 0), r2=(0.5, 0), theta_deg=2.0, p0=(0, -4), n0=(0, -1))

# RXI built via the book's direct (non-iterative) method
rxi_direct = RXIOpticDirect(scene, r1=(-1, 0), r2=(1, 0), theta_deg=30.0, n=1.5)
```

The underlying geometry toolbox (`optical_elements.prisms.nonimaging_geometry`)
is also available standalone -- `isl`, `rfr`, `coptpt`, `coptsl`, `ccoptpt`,
`dcoptpt`, `rfnrm`, `rfxnrm`, `hyp` -- for building custom Cartesian-oval
and hyperbola-based profiles point by point.

## Analysis Utilities (Python-Specific)

The `analysis` module provides utilities not available in the JavaScript version.

### Geometry analysis

```python
from ray_tracing_shapely.analysis import analyze_scene_geometry, describe_edges

# Analyze glass interfaces and boundaries
analysis = analyze_scene_geometry(scene)
for interface in analysis.interfaces:
    print(f"Interface: n1={interface.n1}, n2={interface.n2}, length={interface.length}")

# Describe edges of a glass object (text or XML)
print(describe_edges(prism, format='text'))
```

### Ray-geometry queries

```python
from ray_tracing_shapely.analysis import (
    find_rays_inside_glass, find_rays_crossing_edge,
    find_rays_by_angle_to_edge, find_rays_by_polarization,
)

# Which rays are inside the prism? Which cross the exit face?
inside = find_rays_inside_glass(segments, prism)
crossing = find_rays_crossing_edge(segments, prism, 'SE')

# Filter by incidence angle or polarization state
grazing = find_rays_by_angle_to_edge(segments, prism, 'SE', min_angle=80, max_angle=90)
polarized = find_rays_by_polarization(segments, min_dop=0.5)
```

### Ray lineage tracking

Every ray segment carries a UUID and a parent link, forming a tree that
records how rays split at optical surfaces. After simulation, the lineage
tree supports post-hoc path analysis:

```python
result = simulator.run_with_result()
lineage = result.lineage

from ray_tracing_shapely.analysis.lineage_analysis import (
    rank_paths_by_energy, check_energy_conservation, detect_tir_traps,
)

# Rank optical paths by terminal brightness
ranked = rank_paths_by_energy(lineage)
for r in ranked[:3]:
    print(f"Energy={r['energy']:.4f}  path={' -> '.join(r['path_types'])}")

# Verify energy conservation at every branch point
check = check_energy_conservation(lineage)
print(f"Valid: {check['is_valid']}, checks: {check['total_checks']}")

# Detect rays trapped by repeated TIR
traps = detect_tir_traps(lineage, min_tir_count=2)
```

### Standalone Fresnel utilities

```python
from ray_tracing_shapely.analysis import fresnel_transmittances, critical_angle, brewster_angle

r = fresnel_transmittances(n1=1.0, n2=1.5, theta_i_deg=45)
print(f"T_s={r['T_s']:.4f}  T_p={r['T_p']:.4f}  theta_t={r['theta_t_deg']:.1f}°")

print(f"Critical angle (glass->air): {critical_angle(1.5, 1.0):.1f}°")
print(f"Brewster angle (air->glass): {brewster_angle(1.0, 1.5):.1f}°")
```

### Agentic tools (LLM tool-use APIs)

For use with Claude API, claudette, langchain, or similar frameworks where
tool inputs/outputs must be JSON-serializable:

```python
from ray_tracing_shapely.analysis import (
    set_context_from_result, get_agentic_tools,
)

# Register simulation context once
set_context_from_result(scene=scene, result=result)

# Get tool wrappers that accept strings and return XML
tools = get_agentic_tools()
# tools = [{'name': 'find_rays_inside_glass_xml', 'function': ..., 'description': ...}, ...]
```

### Tool discovery

```python
from ray_tracing_shapely.analysis import list_available_tools
print(list_available_tools())  # lists all analysis functions with signatures
```

## Project Structure

```
ray_tracing_shapely/
├── src-python/
│   └── ray_tracing_shapely/
│       ├── __init__.py
│       ├── analysis/              # Python-specific analysis utilities
│       │   ├── __init__.py
│       │   ├── glass_geometry.py  # Edge descriptions, interfaces, boundaries
│       │   ├── saving.py          # CSV/XML export, ray filtering, statistics
│       │   ├── simulation_result.py  # SimulationResult container
│       │   ├── ray_geometry_queries.py  # Spatial queries (rays vs. geometry)
│       │   ├── lineage_analysis.py    # Post-hoc ray tree analysis
│       │   ├── fresnel_utils.py       # Standalone Fresnel equation utilities
│       │   ├── agentic_tools.py       # JSON-serializable wrappers for LLM APIs
│       │   └── tool_registry.py       # Tool discovery registry
│       ├── core/                  # Core simulation engine
│       │   ├── scene.py
│       │   ├── simulator.py
│       │   ├── ray.py             # Ray with TIR, grazing, lineage tracking
│       │   ├── ray_lineage.py     # Parent-child tree tracker
│       │   ├── svg_renderer.py    # SVG rendering + diagram annotations
│       │   ├── geometry/
│       │   └── scene_objs/
│       ├── optical_elements/      # Physics-driven optical element constructors
│       │   └── prisms/
│       │       ├── base_prism.py          # Dual-labeling base class
│       │       ├── dtirc.py               # DTIRCPrism
│       │       ├── angle_transformer.py   # build_angle_transformer
│       │       ├── rxi.py                 # RXIOptic (Tier 0 dome)
│       │       ├── nonimaging_geometry.py # isl/rfr/coptpt/coptsl/ccoptpt/dcoptpt/rfnrm/rfxnrm/hyp
│       │       ├── sms_chain.py           # Shared SMS alternating-chain engine
│       │       ├── rr_lens.py             # RRLens (SMS)
│       │       ├── rx_concentrator.py     # RXConcentrator (SMS)
│       │       └── rxi_direct.py          # RXIOpticDirect (SMS, direct method)
│       ├── developer_tests/       # Development tests
│       └── examples/              # Example simulations
├── doc/
│   └── roadmap/                   # Design documents and implementation notes
├── pyproject.toml
├── README.md
└── .gitignore
```

## Dependencies

- Python >= 3.8
- shapely >= 2.0.0
- sympy >= 1.12
- numpy >= 1.20.0
- svgwrite >= 1.4.0

## Python-Specific Features

This library includes several features not available in the original JavaScript implementation:

1. **TIR Tracking** - Each ray segment tracks whether it was produced by Total Internal Reflection, whether its endpoint caused TIR, and the cumulative TIR count in its lineage
2. **Grazing Incidence Tracking** - Three independent criteria detect near-critical-angle refraction: angle threshold, polarization ratio, and total transmission
3. **Source Tracking** - Rays carry the UUID and label of the light source that emitted them, enabling multi-source and multi-wavelength analysis
4. **Ray Lineage Tracking** - Every segment has a UUID and parent link. The `RayLineage` class reconstructs the full ray tree after simulation for path analysis, branching statistics, and energy conservation checks
5. **Geometry Analysis** - Shapely-based analysis of glass interfaces, boundaries, edge descriptions, and ray-geometry spatial queries
6. **Fresnel Utilities** - Standalone Fresnel equation solver for transmittances, reflectances, critical angle, and Brewster's angle
7. **Agentic Tools** - JSON-serializable wrappers for LLM tool-use APIs (Claude, claudette, langchain)
8. **Simulation Results** - `SimulationResult` dataclass captures segments, scene snapshot, lineage, and metadata for post-hoc analysis
9. **Export** - CSV and XML export of ray data with filtering by TIR, grazing, wavelength, and source
10. **Nonimaging Optics Devices** - DTIRC, angle-transformer, and RXI-style CPC-family concentrators, plus Miñano–Benítez SMS profile construction (`RRLens`, `RXConcentrator`, `RXIOpticDirect`) built on a shared alternating-chain engine, validated directly against published worked examples
11. **Diagram Annotations** - `SVGRenderer` helpers (`draw_annotation_marker`, `draw_annotation_vector`, `draw_annotation_angle_arc`) for labeling points, directions, and angles on rendered ray diagrams, always drawn above the ray trace

<!-- attribution:begin -- generated by dev_doc/tools/attribution.py, do not edit -->
This project began as a translation of the
[Ray Optics Simulation](https://github.com/ricktu288/ray-optics) JavaScript project
(Copyright 2024 its authors and contributors, Apache-2.0,
[doi:10.5281/zenodo.6386611](https://doi.org/10.5281/zenodo.6386611)), and has grown a
great deal of new work on top of it.

Of this distribution's 145 source files, **35 are translations** of
that project — the ray-tracing engine and its scene objects — and **110
were written for this project**: the analysis layer, the nonimaging design
methods, the radiometric and photobiological layers, the agentic surface,
and the tests and examples. Every file says which it is in its own header,
and `NOTICE.txt` lists the translated set.

If you use this software please cite both, per `CITATION.cff`.
<!-- attribution:end -->

## License

Apache License 2.0

## Acknowledgments

Based on the [Ray Optics Simulation](https://github.com/ricktu288/ray-optics) JavaScript project.
