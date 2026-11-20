"""
Python-specific module: mirrors from a sheet profile
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
MIRRORS FROM A SHEET PROFILE -- the inverse of export_sheet_profile
===============================================================================
A ``body: "sheet"`` profile holds the half-section of revolved mirrors, left
of the axis. `mirrors_from_sheet_profile` rebuilds the 2D section: each span
becomes a mirror with the span's label, and, unless an azimuth cut removes
the far side, its image across the axis. A piece the axis cut in two is
joined back into one mirror: a conic or circle that reaches the axis, and a
flat mirror across it.

    line     Mirror, from its two points
    conic    ConicMirror, from its descriptor; the extent from the samples
    circle   ArcMirror, its vertex on the axis on the samples' side
    spline   SplineMirror, through the span's points and their mirror images
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, List, Mapping, Tuple

from ..roles import Mechanism, Role
from .conic import ArcMirror, ConicMirror, max_single_valued_s

XY = Tuple[float, float]


def _left(p: XY, point: XY, u: XY) -> float:
    return u[0] * (p[1] - point[1]) - u[1] * (p[0] - point[0])


def _image(p: XY, point: XY, u: XY) -> XY:
    vx, vy = p[0] - point[0], p[1] - point[1]
    along = vx * u[0] + vy * u[1]
    return (point[0] + 2 * along * u[0] - vx, point[1] + 2 * along * u[1] - vy)


def _labelled(obj: Any, span: Mapping[str, Any]) -> Any:
    obj.name = span.get("short_label")
    role = span.get("role")
    obj.role = Role(role) if role is not None else None
    return obj


def _lines(scene: Any, span: Mapping[str, Any], pts: List[XY], point: XY, u: XY, far: bool, tol: float) -> List[Any]:
    from ...core.scene_objs.mirror.mirror import Mirror  # noqa: PLC0415

    if len(pts) != 2:
        raise NotImplementedError(f"span {span.get('short_label')!r}: a line span has two points, got {len(pts)}")
    a, b = pts

    def mirror(p: XY, q: XY) -> Any:
        return _labelled(Mirror(scene, {"p1": {"x": p[0], "y": p[1]}, "p2": {"x": q[0], "y": q[1]}}), span)

    if not far:
        return [mirror(a, b)]
    da, db = _left(a, point, u), _left(b, point, u)
    across = abs((b[0] - a[0]) * u[0] + (b[1] - a[1]) * u[1]) <= tol     # normal to the axis
    if across and min(abs(da), abs(db)) <= tol:                           # a flat mirror the axis cut
        end = a if abs(da) > abs(db) else b
        return [mirror(end, _image(end, point, u))]
    return [mirror(a, b), mirror(_image(a, point, u), _image(b, point, u))]


def _curved(scene: Any, span: Mapping[str, Any], pts: List[XY], point: XY, u: XY, far: bool,
            tol: float, sag_tol: float) -> List[Any]:
    curve = span["curve"]
    label = span.get("short_label")
    if len(pts) < 2:
        raise ValueError(f"span {label!r}: a curved span has at least two points, got {len(pts)}")
    if curve["type"] == "conic":
        vertex = (float(curve["vertex"][0]), float(curve["vertex"][1]))
        axis = (float(curve["axis"][0]), float(curve["axis"][1]))
        radius, conic, cls = float(curve["radius"]), float(curve.get("conic", 0.0)), ConicMirror
    else:                                                                  # circle
        centre = (float(curve["center"][0]), float(curve["center"][1]))
        if abs(_left(centre, point, u)) > tol:
            raise NotImplementedError(f"span {label!r}: a circle whose centre is off the revolve axis "
                                      "does not revolve into a sphere")
        r = abs(float(curve["radius"]))
        side = sum((p[0] - centre[0]) * u[0] + (p[1] - centre[1]) * u[1] for p in pts)
        side = 1.0 if side >= 0.0 else -1.0
        vertex = (centre[0] + side * r * u[0], centre[1] + side * r * u[1])
        axis, radius, conic, cls = u, -side * r, 0.0, ArcMirror
    length = math.hypot(*axis)
    cross = (axis[0] * u[1] - axis[1] * u[0]) / length
    if abs(_left(vertex, point, u)) > tol or abs(cross) > 1e-12:
        raise NotImplementedError(f"span {label!r}: a conic whose axis is not the revolve axis "
                                  "does not revolve into a conic of revolution")

    probe = ConicMirror(scene, vertex, axis, radius, conic, semi_diameter=1e-9)
    limit = max_single_valued_s(radius, conic)
    ss = []
    k1 = 1.0 + conic
    for p in pts:
        s, z = probe.to_local(p)
        # distance from F = s^2 - 2 R z + (1 + K) z^2 = 0, to first order: exact enough at the
        # equator, where the sag z(s) is vertical and a difference in z means nothing
        f, grad = s * s - 2.0 * radius * z + k1 * z * z, 2.0 * math.hypot(s, k1 * z - radius)
        gap = abs(f) / grad if grad > 0.0 else math.inf
        if k1 > 0.0 and k1 * z / radius > 1.0 + 1e-9:
            gap = math.inf                                               # past the equator: the far branch
        if gap > sag_tol:
            raise ValueError(f"span {label!r}: a sample lies {gap:.3g} from the vertex branch of its "
                             f"{curve['type']} (sag_tol {sag_tol:g})")
        ss.append(min(max(s, -limit), limit))                           # a rim at the equator, to rounding
    lo, hi = min(ss), max(ss)

    def make(extent: Tuple[float, float]) -> Any:
        kwargs = {"extent": extent, "name": label}
        if cls is ArcMirror:
            return _labelled(ArcMirror(scene, vertex, axis, radius, **kwargs), span)
        return _labelled(ConicMirror(scene, vertex, axis, radius, conic, **kwargs), span)

    if not far:
        return [make((lo, hi))]
    near, edge = min(abs(lo), abs(hi)), max(abs(lo), abs(hi))
    if near <= tol:                                                        # it reaches the axis
        return [make((-edge, edge))]
    return [make((near, edge)), make((-edge, -near))]


def _spline(scene: Any, span: Mapping[str, Any], point: XY, u: XY, far: bool, tol: float) -> Any:
    """One ``SplineMirror`` through the span's points; with the far side kept and the span
    starting on the axis, through their mirror images too, as one mirror across the axis."""
    from .spline import SplineMirror  # noqa: PLC0415

    curve = span["curve"]
    knots = [(float(q[0]), float(q[1])) for q in curve["points"]]
    tans = [(float(t[0]), float(t[1])) for t in curve["tangents"]]
    normals = [(-t[1], t[0]) for t in tans]
    if far and abs(_left(knots[0], point, u)) <= tol:
        images = [_image(q, point, u) for q in knots[1:]]
        # a direction's image across the axis: 2 (v . u) u - v
        image_normals = [(2 * (n[0] * u[0] + n[1] * u[1]) * u[0] - n[0],
                          2 * (n[0] * u[0] + n[1] * u[1]) * u[1] - n[1]) for n in normals[1:]]
        knots, normals = images[::-1] + knots, image_normals[::-1] + normals
    elif far:
        raise NotImplementedError(f"span {span.get('short_label')!r}: a spline sheet that does not "
                                  "reach the axis (a zone) has no 2D mirror yet")
    return _labelled(SplineMirror(scene, knots, normals), span)


def mirrors_from_sheet_profile(scene: Any, profile: Mapping[str, Any], *, tol: float = 1e-9,
                               sag_tol: float = 1e-9) -> List[Any]:
    """The 2D mirrors a ``body: "sheet"`` profile is the half-section of.

    Each span becomes a ``Mirror`` (a line), a ``ConicMirror`` (a conic), an
    ``ArcMirror`` (a circle) or a ``SplineMirror`` (a spline), named by its
    short label, with its role.
    The far side of the axis is rebuilt by mirroring, unless
    ``symmetry.azimuth_deg`` cuts it away (the 3D sheet has nothing there).
    A conic or circle that reaches the axis, and a flat mirror across it,
    come back as one mirror; a zone (a conic that does not reach it) as two.
    The mirrors are returned, not added to the scene.

    Args:
        scene: The scene the mirrors belong to.
        profile: An ``export_sheet_profile`` dict (C-PROFILE-01).
        tol: How near the axis a point counts as on it, in scene units.
        sag_tol: Allowed distance of a curved span's samples from its
            descriptor, in scene units.

    Raises:
        ValueError: For a profile that is not a sheet, a symmetry other than
            revolve, a span that does not reflect, or a sample off its curve.
        NotImplementedError: For a curve other than line, conic, circle and
            spline, or a conic whose axis is not the revolve axis.
    """
    from ..prisms.profile_export import azimuth_keeps, revolve_axis, revolve_azimuth  # noqa: PLC0415

    if profile.get("body") != "sheet":
        raise ValueError(f"profile body is {profile.get('body', 'solid')!r}: a solid is rebuilt by "
                         "BasePrism.from_profile")
    symmetry = profile.get("symmetry") or {}
    if symmetry.get("kind") != "revolve":
        raise ValueError(f"a sheet profile is revolved, got symmetry {symmetry.get('kind')!r}")
    point, u = revolve_axis(symmetry)
    far = azimuth_keeps(revolve_azimuth(symmetry), 180.0)
    points = [(float(p[0]), float(p[1])) for p in profile["points"]]
    out: List[Any] = []
    for span in profile["spans"]:
        label = span.get("short_label")
        if span.get("mechanism") != Mechanism.REFLECT.value:
            raise ValueError(f"span {label!r}: a sheet's spans reflect, got mechanism {span.get('mechanism')!r}")
        pts = points[int(span["index_start"]):int(span["index_end"])]
        kind = (span.get("curve") or {"type": "line"})["type"]
        if kind == "line":
            out.extend(_lines(scene, span, pts, point, u, far, tol))
        elif kind in ("conic", "circle"):
            out.extend(_curved(scene, span, pts, point, u, far, tol, sag_tol))
        elif kind == "spline":
            out.append(_spline(scene, span, point, u, far, tol))
        else:
            raise NotImplementedError(f"span {label!r}: a {kind!r} span has no 2D mirror")
    return out


__all__ = ["mirrors_from_sheet_profile"]
