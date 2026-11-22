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
Exports a BasePrism's surfaces as the tool-independent Hermite handoff
dev_doc/architecture/contracts/C-PROFILE-01.md describes: points, exact
normals, role-tagged spans, construction parameters, and a symmetry
declaration -- the artifact an Optiland-side scene-assembly component
(dev_doc/architecture/components/optiland_nsq_run_registry.md
optiland_scene_bridge) consumes without ever importing this project's
Python types.

Schema 1.1: a span is one physical surface (core.glass_spans), a
straight edge or a whole circular arc. A line contributes its two end points
with its constant normal; an arc contributes ``curve_samples`` points (33 by
default) with the exact normal at each, plus an exact ``curve`` descriptor,
``{"type": "circle", "center": [a, b], "radius": R}``. The samples keep the
profile tool-independent and are what a consumer validates the descriptor
against. Every span says what it is: ``{"type": "line"}`` for a straight one
(1.0 profiles, with no ``curve``, still read as all-straight).

Schema 1.2: a glass edge may also be an exact conic or
spline (core.glass_curves), exported like an arc: ``curve_samples`` points
at equal steps along it with the exact normal at each, and its descriptor,
``{"type": "conic", "vertex", "axis", "radius", "conic"}`` (the
``ConicMirror`` convention) or ``{"type": "spline", "points", "tangents"}``.

Schema 1.3: a profile may also carry the light the element is designed
for, as ``sources``: a list of source specifications
(optical_elements.sources.source_spec), in the same 2D coordinates as the
points, so the 3D side builds the source where the 2D scene had it. Always
present from 1.3 on, empty when no source was given; a 1.2 profile has none.

Schema 1.4: a source may be a measured LED's rayfile (``kind`` "rayfile"):
the file's path and the format its parser takes, the count, flux and
digest it had when written, and how its 2D section is sliced (the limit on
h, and the share and number of rays it keeps). The file itself is not in
the profile; a relative path is relative to the profile's folder.

``fit`` (reserved until 1.5): for spans built from a measurement, a record
per span label, ``{"spans": {label: record}}`` (lenses.profile_scan:
the scan and its digest, the model the span holds, the fitted surface, the
residual, the symmetry assumed). Such a span's normals are its model's,
exact for the model; the residual says how far the model is from the data.

Schema 1.5: a glass edge may also be an exact even asphere,
``{"type": "asphere", "vertex", "axis", "radius", "conic", "coefficients"}``
(core.glass_curves.AsphereCurve: the conic's sag plus A1 s**2 + A2 s**4 + ...,
the coefficients in Zemax's and Optiland's order, ``radius`` None for a flat
base), exported like a conic: ``curve_samples`` points with exact normals,
and the descriptor.

``symmetry.kind = "revolve"`` declares ``axis = {"point": [a, b],
"direction": [ux, uy]}`` in profile coordinates. The outline must be
mirror-symmetric about that axis (a 2D section that is not cannot be the
slice of a round element: an error, not a warning), and the profile carries
only the half-section to the LEFT of the axis direction, as an open chain
from the axis back to the axis. Spans that cross the axis are cut there;
spans lying along it are dropped (revolving them makes no surface). The
top-level ``body`` is ``"solid"``: a BasePrism is glass with an interior.

Sheets: ``export_sheet_profile`` exports mirrors -- flat
``Mirror`` segments and exact ``ConicMirror``/``CircularArcMirror`` curves -- that
are not glass and enclose nothing. ``body`` is ``"sheet"``, every span's
mechanism is ``reflect``, and there is no interior material; reflectance is
not in the profile (the bridge takes one per span). Revolve only: the
mirrors together must be mirror-symmetric about the axis, and each keeps the
part left of it, as one span (spans need not join). A conic must have its
axis on the revolve axis (a tilted or offset one revolves into something
that is not a conic of revolution: a CPC, out of scope). A conic span runs
from the end nearest the axis outwards; its descriptor is ``{"type":
"conic", "vertex", "axis", "radius", "conic"}`` (``circle`` for an
CircularArcMirror), its normals the curve's own, towards the vertex's centre of
curvature. A sheet has no outside, so a line's stored normal is simply its
direction turned 90 degrees counter-clockwise.

Points and normals are stored PER SPAN, not per shared polygon vertex: at a
sharp corner two adjacent straight edges have different outward normals, so
each span gets its own endpoint samples (with its own normal) rather than
sharing a single ambiguous per-vertex entry.
===============================================================================
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from ...core.glass_spans import GlassSpan, glass_spans, outline_coords
from ..roles import Role, Mechanism

if TYPE_CHECKING:
    from .base_prism import BasePrism

PROFILE_SCHEMA_VERSION = "1.5"

#: Samples per curved span unless the caller says otherwise. Descriptor and
#: samples come from the same formula, so a fixed count and fixed tolerances
#: suffice.
DEFAULT_CURVE_SAMPLES = 33

#: Allowed distance between the outline and its mirror image for a revolve
#: export, in scene units.
DEFAULT_SYMMETRY_TOL = 1e-9


def _edge_outward_normal(p1: tuple, p2: tuple) -> tuple:
    """Outward unit normal of a straight edge p1->p2 in a CCW-wound polygon.

    For a counter-clockwise polygon the interior lies to the left of the
    direction of travel, so the outward normal is 90 degrees to the right:
    rotating the edge direction (dx, dy) by -90 degrees gives (dy, -dx).
    The 3D bridge places each face from this normal, which was checked by
    hand against the corner positions Optiland itself computes.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        raise ValueError(f"Degenerate edge: p1={p1}, p2={p2}")
    return (dy / length, -dx / length)


def _signed_area(ring: Sequence[Tuple[float, float]]) -> float:
    n = len(ring)
    return 0.5 * sum(
        ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
        for i in range(n)
    )


def _validated_sources(sources: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """``sources`` validated for a profile's ``sources`` list (schema 1.3; the ``rayfile`` kind 1.4).

    Raises:
        ValueError: If a spec is invalid or two share a name.
    """
    from ..sources.source_spec import profile_sources  # noqa: PLC0415

    return profile_sources({"sources": list(sources or [])})


def revolve_axis(symmetry: Dict[str, Any]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Read and check a revolve symmetry's ``axis``: ``(point, unit direction)``.

    Raises:
        ValueError: If ``axis`` is not ``{"point": [a, b], "direction": [ux, uy]}``
            with a non-zero direction.
    """
    axis = symmetry.get("axis")
    try:
        point = (float(axis["point"][0]), float(axis["point"][1]))
        ux, uy = float(axis["direction"][0]), float(axis["direction"][1])
        if len(axis["point"]) != 2 or len(axis["direction"]) != 2:
            raise ValueError
    except (TypeError, KeyError, IndexError, ValueError):
        raise ValueError(
            "symmetry kind='revolve' needs axis = {'point': [a, b], 'direction': [ux, uy]} "
            f"in profile coordinates, got {axis!r}"
        ) from None
    length = math.hypot(ux, uy)
    if length == 0.0:
        raise ValueError("symmetry kind='revolve': axis direction is zero")
    return point, (ux / length, uy / length)


def revolve_azimuth(symmetry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Read and check a revolve symmetry's optional ``azimuth_deg``: the kept range.

    ``azimuth_deg = [start, end]`` cuts a revolved sheet to that range about the
    axis, in degrees measured from the half-section's own side (left of the
    axis direction) towards the 3D frame's +y (C-BRIDGE-12). It must
    keep the half-section itself (0 deg), since the 2D scene is the 3D
    section there.

    Returns:
        ``(start, end)``, or None for no cut (absent, or a full turn).

    Raises:
        ValueError: For a malformed range, an empty one, one over a full
            turn, or one that does not keep 0 deg.
    """
    az = symmetry.get("azimuth_deg")
    if az is None:
        return None
    try:
        start, end = float(az[0]), float(az[1])
        if len(az) != 2 or not (math.isfinite(start) and math.isfinite(end)):
            raise ValueError
    except (TypeError, IndexError, ValueError):
        raise ValueError(f"symmetry azimuth_deg must be [start, end] in degrees, got {az!r}") from None
    if not 0.0 < end - start <= 360.0:
        raise ValueError(f"symmetry azimuth_deg needs 0 < end - start <= 360, got {az!r}")
    if end - start == 360.0:
        return None
    if not azimuth_keeps((start, end), 0.0):
        raise ValueError(
            f"symmetry azimuth_deg {az!r} removes the half-section itself (0 deg): the 2D "
            "scene would show a section the 3D sheet does not have.")
    return start, end


def azimuth_keeps(azimuth: Optional[Tuple[float, float]], angle_deg: float) -> bool:
    """Whether an azimuth range (None: the full turn) keeps ``angle_deg``, edges included."""
    if azimuth is None:
        return True
    start, end = azimuth
    return (angle_deg - start) % 360.0 <= end - start


def _mirror(p: Tuple[float, float], point, direction) -> Tuple[float, float]:
    """Reflect ``p`` across the line through ``point`` along unit ``direction``."""
    vx, vy = p[0] - point[0], p[1] - point[1]
    along = vx * direction[0] + vy * direction[1]
    return (point[0] + 2 * along * direction[0] - vx, point[1] + 2 * along * direction[1] - vy)


def _left_distance(p, point, direction) -> float:
    """Signed distance of ``p`` from the axis, positive on its left."""
    return direction[0] * (p[1] - point[1]) - direction[1] * (p[0] - point[0])


def _onto_axis(p, point, direction, tol: float) -> Tuple[float, float]:
    """``p`` projected onto the axis if it is within ``tol`` of it, else ``p``."""
    if abs(_left_distance(p, point, direction)) > tol:
        return p
    along = (p[0] - point[0]) * direction[0] + (p[1] - point[1]) * direction[1]
    return (point[0] + along * direction[0], point[1] + along * direction[1])


def _check_mirror_symmetric(spans: List[GlassSpan], point, direction, tol: float) -> None:
    """Raise unless every span's mirror image lies on the outline."""
    for span in spans:
        for f in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0):
            image = _mirror(span.point_at(f), point, direction)
            gap = min(other.locate(image)[0] for other in spans)
            if gap > tol:
                raise ValueError(
                    f"outline is not mirror-symmetric about the revolve axis: the mirror "
                    f"image of a point on span {span.index} lies {gap:.3g} from the "
                    "outline. A section that is not symmetric cannot be the slice of a "
                    "round element."
                )


def _half_section(spans: List[GlassSpan], point, direction, tol: float) -> List[GlassSpan]:
    """The pieces of a CCW outline left of the axis, as one chain from axis to axis."""
    kept: List[GlassSpan] = []
    for span in spans:
        cuts = []
        if span.is_arc:
            # Where the circle meets the axis line, inside the arc.
            cx, cy = span.center
            d_center = _left_distance(span.center, point, direction)
            if abs(d_center) < span.radius:
                half = math.sqrt(span.radius ** 2 - d_center ** 2)
                foot = (cx + direction[1] * d_center, cy - direction[0] * d_center)
                for sign in (-1.0, 1.0):
                    q = (foot[0] + sign * half * direction[0], foot[1] + sign * half * direction[1])
                    dist, s = span.locate(q)
                    if dist <= tol and tol < s < span.length - tol:
                        cuts.append(s / span.length)
        elif span.is_freeform:
            # Where the curve meets the axis line, strictly inside the edge.
            for _, p in span.shape.line_hits(point, direction):
                s = span.shape.arc_length_to(p)
                if tol < s < span.length - tol:
                    cuts.append(s / span.length)
        else:
            d0 = _left_distance(span.start, point, direction)
            d1 = _left_distance(span.end, point, direction)
            if (d0 > tol and d1 < -tol) or (d0 < -tol and d1 > tol):
                cuts.append(d0 / (d0 - d1))
        bounds = [0.0] + sorted(cuts) + [1.0]
        for f0, f1 in zip(bounds[:-1], bounds[1:]):
            piece = span.piece(f0, f1)
            if _left_distance(piece.point_at(0.5), point, direction) > tol:
                # An end on the axis is put exactly on it: the revolve maps it to r = 0.
                kept.append(replace(
                    piece,
                    start=_onto_axis(piece.start, point, direction, tol),
                    end=_onto_axis(piece.end, point, direction, tol),
                ))

    if not kept:
        raise ValueError("no part of the outline lies left of the revolve axis")
    on_axis = [
        i for i, piece in enumerate(kept)
        if abs(_left_distance(piece.start, point, direction)) <= tol
    ]
    if len(on_axis) != 1:
        raise NotImplementedError(
            f"the outline meets the revolve axis {2 * len(on_axis)} times; a revolve "
            "half-section must be one chain from the axis to the axis."
        )
    chain = kept[on_axis[0]:] + kept[:on_axis[0]]
    for a, b in zip(chain[:-1], chain[1:]):
        if math.dist(a.end, b.start) > tol:
            raise NotImplementedError(
                "the half-section left of the revolve axis is not one connected chain."
            )
    if abs(_left_distance(chain[-1].end, point, direction)) > tol:
        raise NotImplementedError("the half-section does not end on the revolve axis.")
    return chain


def export_profile(
    prism: "BasePrism",
    *,
    symmetry: Dict[str, Any],
    physical_params: Dict[str, Any],
    numerical_params: Dict[str, Any],
    curve_samples: Optional[int] = None,
    symmetry_tol: float = DEFAULT_SYMMETRY_TOL,
    sources: Optional[Sequence[Dict[str, Any]]] = None,
    fit: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Export a BasePrism as a profile.json-shaped dict (schema ``PROFILE_SCHEMA_VERSION``).

    Args:
        prism: A BasePrism instance with a populated ``path`` (i.e. one
            that has already been constructed -- ``_compute_path()`` has
            run) and Role-tagged ``_edge_roles`` (3-tuples; a 2-tuple edge
            role has no Role and is exported with ``role: null``, loud
            rather than guessed). Its outline is walked by span
            (``BasePrism.spans``): a straight edge or a whole arc.
        symmetry: The C-PROFILE-01 symmetry declaration. Must have
            ``"kind"`` in ``{"extrude", "revolve", "free"}``. For
            ``"extrude"``, the kind alone is under-specified, so also
            required: ``"plane_axes"`` (which two
            world axes realise the 2D (x, y) plane, e.g. ``["x", "z"]``),
            ``"extrude_axis"`` (the third world axis), and ``"length"``.
            For ``"revolve"``, required: ``"axis"`` as
            ``{"point": [a, b], "direction": [ux, uy]}``; only the
            half-section left of the axis direction is exported.
        physical_params: Design-physical parameters (indices, angles,
            etendue, ...) -- the ``physical_params`` half of the
            physical/numerical split ``persist_run_artifacts`` already
            uses (``run_registry.py``).
        numerical_params: Numerical/construction-resolution parameters,
            the other half of that same split. When the outline has an
            arc, the sample count used is recorded in it as
            ``curve_samples``.
        curve_samples: Points per curved span (at least 3). Defaults to
            ``numerical_params["curve_samples"]`` if given, else
            ``DEFAULT_CURVE_SAMPLES``.
        symmetry_tol: For ``"revolve"``: how far, in scene units, the
            outline may stray from its mirror image, and how close a point
            must be to the axis to count as on it.
        sources: Source specifications for the light the element is
            designed for, written to ``sources`` after validation
            (``validate_source_spec``, defaults filled in). None or empty
            writes an empty list.
        fit: For spans built from a measurement, a record per span short
            label (``lenses.profile_scan.fit_record``: the scan, the model,
            the fitted surface, the residual), written to ``fit`` as
            ``{"spans": {label: record}}``. None writes None.

    Returns:
        A JSON-serializable dict matching C-PROFILE-01's target shape:
        ``schema_version``, ``points``, ``normals``, ``spans`` (each with a
        ``curve``), ``symmetry``, ``body``, ``construction_params``, ``sources``, ``fit``
        (always ``None`` from the 2D side -- filled in later by whatever 3D
        tool fits this profile, per C-PROFILE-01's own note).

    Raises:
        ValueError: If ``prism.path`` is empty, or ``symmetry["kind"]`` is
            not one of the three C-PROFILE-01 values, or an ``"extrude"``
            symmetry omits ``plane_axes``/``extrude_axis``/``length``, or
            a ``"revolve"`` symmetry has no well-formed ``axis``, or the
            outline is clockwise, or (revolve) it is not mirror-symmetric
            about the axis, or ``curve_samples`` is below 3.
        NotImplementedError: For a revolve outline that meets its axis
            more than twice.
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

    if curve_samples is None:
        curve_samples = int(numerical_params.get("curve_samples", DEFAULT_CURVE_SAMPLES))
    if curve_samples < 3:
        raise ValueError(f"curve_samples must be at least 3, got {curve_samples}")

    full = glass_spans(prism.path)
    if _signed_area(outline_coords(prism.path)) <= 0.0:
        raise ValueError(
            f"{type(prism).__name__}'s outline is clockwise or degenerate; "
            "BasePrism requires counterclockwise order."
        )

    symmetry_out = dict(symmetry)
    pieces: List[GlassSpan] = full
    if kind == "revolve":
        point, direction = revolve_axis(symmetry)
        if revolve_azimuth(symmetry) is not None:
            raise ValueError("an azimuth cut is for sheets only: a cut solid of revolution is not "
                             "closed (C-BRIDGE-12).")
        _check_mirror_symmetric(full, point, direction, symmetry_tol)
        pieces = _half_section(full, point, direction, symmetry_tol)
        symmetry_out["axis"] = {"point": list(point), "direction": list(direction)}

    edge_mechanisms = getattr(prism, "_edge_mechanisms", {})

    points: List[List[float]] = []
    normals: List[List[float]] = []
    spans: List[Dict[str, Any]] = []

    for piece in pieces:
        samples = piece.samples(curve_samples) if piece.is_curved else [piece.start, piece.end]
        if piece.is_curved:
            sample_normals = [piece.outward_normal_at(p) for p in samples]
        else:
            constant = _edge_outward_normal(piece.start, piece.end)
            sample_normals = [constant, constant]

        index_start = len(points)
        points.extend([p[0], p[1]] for p in samples)
        normals.extend([n[0], n[1]] for n in sample_normals)
        index_end = len(points)

        short_label, long_label = prism.get_functional_label(piece.index) or (None, None)
        role: Optional[Role] = prism.get_edge_role(piece.index)
        mechanism: Optional[Mechanism] = edge_mechanisms.get(short_label)

        spans.append(
            {
                "index_start": index_start,
                "index_end": index_end,
                "short_label": short_label,
                "long_label": long_label,
                "role": role.value if role is not None else None,
                "mechanism": mechanism.value if mechanism is not None else None,
                "curve": piece.curve,
            }
        )

    numerical_out = dict(numerical_params)
    if any(piece.is_curved for piece in pieces):
        numerical_out["curve_samples"] = curve_samples

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "points": points,
        "normals": normals,
        "spans": spans,
        "symmetry": symmetry_out,
        "body": "solid",
        "construction_params": {
            "physical_params": physical_params,
            "numerical_params": numerical_out,
        },
        "sources": _validated_sources(sources),
        "fit": _validated_fit(fit, spans),
    }


def _validated_fit(fit, spans) -> Optional[Dict[str, Any]]:
    """``fit`` as ``{"spans": {label: record}}``, each label a span's; None for none."""
    if not fit:
        return None
    labels = {sp["short_label"] for sp in spans}
    unknown = sorted(set(fit) - labels)
    if unknown:
        raise ValueError(f"fit records for {unknown}, which are not span labels of this profile ({sorted(labels)})")
    try:
        return json.loads(json.dumps({"spans": dict(fit)}))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"a fit record must be plain JSON: {exc}") from None


def _point_segment_distance(q, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)


def _sheet_member(mirror):
    """``("conic", mirror)``, ``("spline", mirror)`` or ``("line", (p1, p2))`` for an exportable
    mirror."""
    from ..mirrors.conic import ConicMirror  # noqa: PLC0415
    from ..mirrors.spline import SplineMirror  # noqa: PLC0415

    if isinstance(mirror, ConicMirror):
        return "conic", mirror
    if isinstance(mirror, SplineMirror):
        return "spline", mirror
    p1, p2 = getattr(mirror, "p1", None), getattr(mirror, "p2", None)
    if getattr(mirror, "type", None) == "Mirror" and p1 is not None and p2 is not None:
        return "line", ((float(p1["x"]), float(p1["y"])), (float(p2["x"]), float(p2["y"])))
    raise TypeError(f"{type(mirror).__name__} is not an exportable mirror "
                    "(Mirror, ConicMirror, CircularArcMirror or SplineMirror).")


def _sheet_distance(member, q, tol: float) -> float:
    kind, m = member
    if kind == "line":
        return _point_segment_distance(q, *m)
    if kind == "spline":
        return m.curve.nearest(q)[0]
    s, _ = m.to_local(q)
    if not (m.extent[0] - tol <= s <= m.extent[1] + tol):
        return math.inf
    s = min(max(s, m.extent[0]), m.extent[1])
    return math.dist(q, m.point_at(s))


def _sheet_samples(member, fractions):
    kind, m = member
    if kind == "line":
        (a, b) = m
        return [(a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])) for f in fractions]
    if kind == "spline":
        p0, p1 = m.curve.p_start, m.curve.p_end
        return [m.curve.point(p0 + f * (p1 - p0)) for f in fractions]
    s0, s1 = m.extent
    return [m.point_at(s0 + f * (s1 - s0)) for f in fractions]


def export_sheet_profile(
    mirrors: Sequence[Any],
    *,
    symmetry: Dict[str, Any],
    physical_params: Dict[str, Any],
    numerical_params: Dict[str, Any],
    curve_samples: Optional[int] = None,
    symmetry_tol: float = DEFAULT_SYMMETRY_TOL,
    sources: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Export mirrors as a profile.json-shaped dict with ``body: "sheet"`` (schema 1.1).

    Args:
        mirrors: ``Mirror``, ``ConicMirror``, ``CircularArcMirror`` and ``SplineMirror`` objects, each
            with a distinct ``name`` (its span's short label). Their
            ``role`` is exported as is; the mechanism is ``reflect``.
        symmetry: ``{"kind": "revolve", "axis": {"point": [a, b],
            "direction": [ux, uy]}}``, optionally with ``"azimuth_deg":
            [start, end]`` (see ``revolve_azimuth``): the sheet is then cut to
            that range. If the range removes 180 deg (the far side of the
            section), the mirrors are not required to be mirror-symmetric,
            and none may lie right of the axis: the 2D scene must be the 3D
            section, side for side.
        physical_params, numerical_params, curve_samples, symmetry_tol,
            sources: as for ``export_profile``.

    Raises:
        ValueError: For a missing or repeated name, mirrors that are not
            mirror-symmetric about the axis (when the far side is kept) or
            that lie right of it (when it is cut away), nothing left of the
            axis, a bad ``azimuth_deg``, or ``curve_samples`` below 3.
        NotImplementedError: For a symmetry other than revolve, a conic
            whose axis is not the revolve axis, or a spline that crosses the
            axis without a point on it (its half-section would not start at
            the axis on one of its own points).
        TypeError: For an object that is not one of the four mirrors.
    """
    kind = symmetry.get("kind")
    if kind != "revolve":
        raise NotImplementedError(f"sheet export is revolve only (C-BRIDGE-12), got kind {kind!r}.")
    point, direction = revolve_axis(symmetry)
    azimuth = revolve_azimuth(symmetry)
    if curve_samples is None:
        curve_samples = int(numerical_params.get("curve_samples", DEFAULT_CURVE_SAMPLES))
    if curve_samples < 3:
        raise ValueError(f"curve_samples must be at least 3, got {curve_samples}")
    names = [getattr(m, "name", None) for m in mirrors]
    if not mirrors or any(not n for n in names) or len(set(names)) != len(names):
        raise ValueError(f"each mirror needs a distinct name (its span label), got {names}")
    members = [_sheet_member(m) for m in mirrors]

    fractions = [k / 16 for k in range(17)]
    far_side_kept = azimuth_keeps(azimuth, 180.0)
    for name, member in zip(names, members):
        for q in _sheet_samples(member, fractions):
            if not far_side_kept:
                if _left_distance(q, point, direction) < -symmetry_tol:
                    raise ValueError(
                        f"{name!r} lies right of the revolve axis, on the side the azimuth cut "
                        f"{list(azimuth)} removes: the 3D sheet has nothing there.")
                continue
            image = _mirror(q, point, direction)
            gap = min(_sheet_distance(other, image, symmetry_tol) for other in members)
            if gap > symmetry_tol:
                raise ValueError(
                    f"the mirrors are not mirror-symmetric about the revolve axis: the mirror "
                    f"image of a point of {name!r} lies {gap:.3g} from every mirror.")

    left = (-direction[1], direction[0])
    points: List[List[float]] = []
    normals: List[List[float]] = []
    spans: List[Dict[str, Any]] = []
    any_curve = False
    for name, mirror, (kind_m, m) in zip(names, mirrors, members):
        if kind_m == "conic":
            cross = m.axis[0] * direction[1] - m.axis[1] * direction[0]
            if abs(_left_distance(m.vertex, point, direction)) > symmetry_tol or abs(cross) > 1e-12:
                raise NotImplementedError(
                    f"{name!r}: a conic whose axis is not the revolve axis revolves into a "
                    "surface that is not a conic of revolution (a CPC, out of scope: C-BRIDGE-12).")
            sign = 1.0 if m.left[0] * left[0] + m.left[1] * left[1] > 0.0 else -1.0
            lo, hi = (max(m.extent[0], 0.0), m.extent[1]) if sign > 0 else (m.extent[0], min(m.extent[1], 0.0))
            if hi - lo <= symmetry_tol:
                continue
            ends = (lo, hi) if sign > 0 else (hi, lo)       # from the end nearest the axis
            ss = [ends[0] + (ends[1] - ends[0]) * k / (curve_samples - 1) for k in range(curve_samples)]
            if abs(ss[0]) <= symmetry_tol:
                ss[0] = 0.0
            samples = [m.point_at(s) for s in ss]
            sample_normals = [m.normal_at(s) for s in ss]
            curve = m.descriptor()
            any_curve = True
        elif kind_m == "spline":
            # the points left of the axis, from the axis outward: the same cubic segments as the
            # whole mirror's between them, so the half-section's spline is the mirror's, exactly
            knots, tangents = m.curve.points, m.curve.tangents
            side = [_left_distance(q, point, direction) for q in knots]
            if all(d <= symmetry_tol for d in side):
                continue
            on_axis = [k for k, d in enumerate(side) if abs(d) <= symmetry_tol]
            if any(d < -symmetry_tol for d in side):
                if not on_axis:
                    raise NotImplementedError(
                        f"{name!r}: a spline mirror crossing the revolve axis needs one of its "
                        "points on the axis, where its half-section starts.")
                k0 = on_axis[0]
                idx = (list(range(k0, len(knots))) if side[-1] > symmetry_tol
                       else list(range(k0, -1, -1)))
            else:
                idx = list(range(len(knots))) if side[0] <= side[-1] else list(range(len(knots) - 1, -1, -1))
            forward = idx[1] > idx[0]
            samples = [_onto_axis(knots[k], point, direction, symmetry_tol) for k in idx]
            tans = [tangents[k] if forward else (-tangents[k][0], -tangents[k][1]) for k in idx]
            sample_normals = [(-t[1], t[0]) for t in tans]
            curve = {"type": "spline", "points": [list(q) for q in samples], "tangents": [list(t) for t in tans]}
            any_curve = True
        else:
            a, b = m
            da, db = _left_distance(a, point, direction), _left_distance(b, point, direction)
            if da <= symmetry_tol and db <= symmetry_tol:
                continue
            if (da > symmetry_tol and db < -symmetry_tol) or (da < -symmetry_tol and db > symmetry_tol):
                f = da / (da - db)
                cut = (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
                a, b = (a, cut) if da > 0 else (cut, b)
            a = _onto_axis(a, point, direction, symmetry_tol)
            b = _onto_axis(b, point, direction, symmetry_tol)
            n = _edge_outward_normal(a, b)
            samples, sample_normals = [a, b], [(-n[0], -n[1])]  * 2
            curve = {"type": "line"}
        index_start = len(points)
        points.extend([p[0], p[1]] for p in samples)
        normals.extend([v[0], v[1]] for v in sample_normals)
        role = getattr(mirror, "role", None)
        spans.append({
            "index_start": index_start,
            "index_end": len(points),
            "short_label": name,
            "long_label": name,
            "role": role.value if role is not None else None,
            "mechanism": Mechanism.REFLECT.value,
            "curve": curve,
        })
    if not spans:
        raise ValueError("no part of the mirrors lies left of the revolve axis")

    numerical_out = dict(numerical_params)
    if any_curve:
        numerical_out["curve_samples"] = curve_samples
    symmetry_out = dict(symmetry)
    symmetry_out["axis"] = {"point": list(point), "direction": list(direction)}
    symmetry_out.pop("azimuth_deg", None)
    if azimuth is not None:
        symmetry_out["azimuth_deg"] = list(azimuth)
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "points": points,
        "normals": normals,
        "spans": spans,
        "symmetry": symmetry_out,
        "body": "sheet",
        "construction_params": {
            "physical_params": physical_params,
            "numerical_params": numerical_out,
        },
        "sources": _validated_sources(sources),
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
    sources: Optional[Sequence[Dict[str, Any]]] = None,
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
        sources=sources,
    )
    run_dir = Path(out_dir) / design_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_path = run_dir / "profile.json"
    profile_path.write_text(json.dumps(profile, indent=2))
    return profile_path
