"""
Python-specific module: profile export
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

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PROFILE EXPORT -- the profile.json handoff contract, C-PROFILE-01
===============================================================================
Exports a BasePrism's edges as the tool-independent Hermite handoff
dev_doc/architecture/contracts/C-PROFILE-01.md describes: points, exact
normals, role-tagged spans, construction parameters, and a symmetry
declaration -- the artifact an Optiland-side scene-assembly component
(dev_doc/architecture/components/optiland_nsq_run_registry.md
optiland_scene_bridge) consumes without ever importing this project's
Python types.

Scope of this first implementation: straight-edge BasePrism subclasses only
(RefractometerPrism today). A curved SMS profile's points/normals come from
sms_chain.SMSPoint instead of polygon edges -- a different producer for the
same schema, not built here (RRLens's own _edge_roles is still empty, so it
has no spans to export yet either).

Points and normals are stored PER SPAN, not per shared polygon vertex: at a
sharp corner two adjacent straight edges have different outward normals, so
each span gets its own two endpoint samples (with that edge's own constant
normal) rather than sharing a single ambiguous per-vertex entry. This also
generalises correctly to a future curved span, which would simply contribute
more than two samples with a continuously varying normal, still self
-contained inside its own span's index range.
===============================================================================
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..roles import Role, Mechanism

if TYPE_CHECKING:
    from .base_prism import BasePrism

PROFILE_SCHEMA_VERSION = "1.0"


def _edge_outward_normal(p1: tuple, p2: tuple) -> tuple:
    """Outward unit normal of a straight edge p1->p2 in a CCW-wound polygon.

    For a counter-clockwise polygon the interior lies to the left of the
    direction of travel, so the outward normal is 90 degrees to the right:
    rotating the edge direction (dx, dy) by -90 degrees gives (dy, -dx).
    This is the same convention notebooks/optiland_nsq_refractometer_intro.ipynb
    validated by hand against Optiland's own corner positions.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        raise ValueError(f"Degenerate edge: p1={p1}, p2={p2}")
    return (dy / length, -dx / length)


def export_profile(
    prism: "BasePrism",
    *,
    symmetry: Dict[str, Any],
    physical_params: Dict[str, Any],
    numerical_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Export a straight-edge BasePrism as a profile.json-shaped dict.

    Args:
        prism: A BasePrism instance with a populated ``path`` (i.e. one
            that has already been constructed -- ``_compute_path()`` has
            run) and Role-tagged ``_edge_roles`` (3-tuples; a 2-tuple edge
            role has no Role and is exported with ``role: null``, loud
            rather than guessed).
        symmetry: The C-PROFILE-01 symmetry declaration. Must have
            ``"kind"`` in ``{"extrude", "revolve", "free"}``. For
            ``"extrude"``, the kind alone is under-specified, so also
            required: ``"plane_axes"`` (which two
            world axes realise the 2D (x, y) plane, e.g. ``["x", "z"]``),
            ``"extrude_axis"`` (the third world axis), and ``"length"``.
            For ``"revolve"``, required: ``"axis"``.
        physical_params: Design-physical parameters (indices, angles,
            etendue, ...) -- the ``physical_params`` half of the
            physical/numerical split ``persist_run_artifacts`` already
            uses (``run_registry.py``).
        numerical_params: Numerical/construction-resolution parameters,
            the other half of that same split.

    Returns:
        A JSON-serializable dict matching C-PROFILE-01's target shape:
        ``schema_version``, ``points``, ``normals``, ``spans``,
        ``symmetry``, ``construction_params``, ``fit`` (always ``None``
        from the 2D side -- filled in later by whatever 3D tool fits this
        profile, per C-PROFILE-01's own note).

    Raises:
        ValueError: If ``prism.path`` is empty, or ``symmetry["kind"]`` is
            not one of the three C-PROFILE-01 values, or an ``"extrude"``
            symmetry omits ``plane_axes``/``extrude_axis``/``length``, or
            a ``"revolve"`` symmetry omits ``axis``.
    """
    if not prism.path:
        raise ValueError(
            f"{type(prism).__name__} has no path -- construct it before exporting."
        )

    kind = symmetry.get("kind")
    if kind not in ("extrude", "revolve", "free"):
        raise ValueError(
            f"symmetry['kind'] must be 'extrude', 'revolve', or 'free', got {kind!r}."
        )
    if kind == "extrude":
        missing = [k for k in ("plane_axes", "extrude_axis", "length") if k not in symmetry]
        if missing:
            raise ValueError(f"symmetry kind='extrude' is missing required key(s): {missing}")
    if kind == "revolve" and "axis" not in symmetry:
        raise ValueError("symmetry kind='revolve' is missing required key 'axis'")

    edge_mechanisms = getattr(prism, "_edge_mechanisms", {})

    points: List[List[float]] = []
    normals: List[List[float]] = []
    spans: List[Dict[str, Any]] = []

    n_edges = len(prism.path)
    for edge_index in range(n_edges):
        p1, p2 = prism.get_edge_endpoints(edge_index)
        nx, ny = _edge_outward_normal(p1, p2)

        index_start = len(points)
        points.append([p1[0], p1[1]])
        points.append([p2[0], p2[1]])
        normals.append([nx, ny])
        normals.append([nx, ny])
        index_end = len(points)

        short_label, long_label = prism.get_functional_label(edge_index) or (None, None)
        role: Optional[Role] = prism.get_edge_role(edge_index)
        mechanism: Optional[Mechanism] = edge_mechanisms.get(short_label)

        spans.append(
            {
                "index_start": index_start,
                "index_end": index_end,
                "short_label": short_label,
                "long_label": long_label,
                "role": role.value if role is not None else None,
                "mechanism": mechanism.value if mechanism is not None else None,
            }
        )

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "points": points,
        "normals": normals,
        "spans": spans,
        "symmetry": symmetry,
        "construction_params": {
            "physical_params": physical_params,
            "numerical_params": numerical_params,
        },
        "fit": None,
    }


def persist_profile_artifact(
    prism: "BasePrism",
    *,
    symmetry: Dict[str, Any],
    physical_params: Dict[str, Any],
    numerical_params: Dict[str, Any],
    out_dir: Path,
    design_id: str,
    run_id: str,
) -> Path:
    """Write ``export_profile``'s result to <out_dir>/<design_id>/<run_id>/profile.json.

    Mirrors ``analysis.run_registry.persist_run_artifacts``'s directory
    layout so a profile and a run of the device it describes can share one
    run directory.

    Returns:
        The path to the written ``profile.json``.
    """
    profile = export_profile(
        prism,
        symmetry=symmetry,
        physical_params=physical_params,
        numerical_params=numerical_params,
    )
    run_dir = Path(out_dir) / design_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_path = run_dir / "profile.json"
    profile_path.write_text(json.dumps(profile, indent=2))
    return profile_path
