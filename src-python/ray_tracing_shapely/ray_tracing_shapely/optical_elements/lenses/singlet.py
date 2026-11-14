"""
Python-specific module: singlet lens
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
SINGLET LENS -- a labelled, exportable lens
===============================================================================
One piece of glass with two spherical (or flat) faces, as a BasePrism: its
surfaces carry functional labels, roles and mechanisms, so it exports to
profile.json (extruded: a cylindrical lens; revolved: a round lens) and comes
back by the same names.

Conventions are the light's, not the 2D UI's:

- Light travels along the lens's optical axis, which is +x rotated by
  ``rotation`` degrees. ``S1`` is the front surface (met first), ``S2`` the
  back surface.
- Radii follow Optiland's sign convention: positive when the centre of
  curvature lies downstream of the vertex (along the light), negative when
  upstream, ``math.inf`` (or None) for a flat face. A biconvex lens is
  ``(R1 > 0, R2 < 0)``. The same numbers go into an Optiland ``LensConfig``
  or a sequential prescription.
- ``position`` is the front vertex (where the axis meets ``S1``).

Edges, in counter-clockwise path order (one per physical surface):

    0  S1   Front Surface   entrance  refract
    1  RIM  Edge            blocker   (none: absorbing in 3D)
    2  S2   Back Surface    exit      refract
    3  RIM  Edge            blocker   (none)

The two RIM edges are the two sides of one cylinder; a revolve export keeps
only the one left of the axis. In 2D the rim is glass like the rest and
refracts; the empty mechanism tells the 3D bridge to make it absorbing, as
Optiland's own lens edge is.

SphericalLens (core/scene_objs/glass) is the same optical object with Ray
Optics Simulation's conventions (r1 is the face on one side of its aperture
line, whichever way the light goes); ``SingletLens.from_spherical_lens``
converts one.
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from ...core.glass_spans import glass_spans
from ..prisms.base_prism import BasePrism
from ..roles import Mechanism, Role

if TYPE_CHECKING:
    from ...core.scene import Scene
    from ...core.scene_objs.glass.spherical_lens import SphericalLens


def _radius(value: Optional[float]) -> float:
    if value is None:
        return math.inf
    value = float(value)
    if value == 0.0:
        raise ValueError("a radius of 0 is not a surface; use math.inf (or None) for a flat face")
    return value


def surface_sag(height: float, radius: float) -> float:
    """Axial distance from a face's vertex to the face at ``height`` from the axis.

    Signed along the light: positive when the face at that height lies
    downstream of its vertex (a face with ``radius > 0``).
    """
    if math.isinf(radius):
        return 0.0
    return radius - math.copysign(math.sqrt(radius * radius - height * height), radius)


class SingletLens(BasePrism):
    """A labelled singlet lens with spherical or flat faces.

    Args:
        scene: The scene this lens belongs to.
        radius_front: Radius of ``S1``, Optiland's sign convention
            (``math.inf`` or None: flat).
        radius_back: Radius of ``S2``, the same convention.
        thickness: Centre thickness, vertex to vertex along the axis.
        semi_diameter: Half the clear aperture: the rim's distance from the axis.
        n: Refractive index.
        position: The front vertex.
        rotation: Direction of the optical axis (of the light), degrees
            counter-clockwise from +x.

    Raises:
        ValueError: For a non-positive thickness or semi-diameter, a face
            whose radius does not exceed the semi-diameter, or an edge
            thickness that is not positive (the faces cross before the rim).
    """

    type = 'SingletLens'

    _edge_roles: ClassVar[List[Tuple[str, str, Role]]] = [
        ("S1", "Front Surface", Role.ENTRANCE),
        ("RIM", "Edge", Role.BLOCKER),
        ("S2", "Back Surface", Role.EXIT),
        ("RIM", "Edge", Role.BLOCKER),
    ]

    _edge_mechanisms: ClassVar[Dict[str, Optional[Mechanism]]] = {
        "S1": Mechanism.REFRACT,
        "RIM": None,
        "S2": Mechanism.REFRACT,
    }

    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None

    def __init__(
        self,
        scene: 'Scene',
        *,
        radius_front: Optional[float],
        radius_back: Optional[float],
        thickness: float,
        semi_diameter: float,
        n: float = 1.5,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
    ) -> None:
        self.radius_front = _radius(radius_front)
        self.radius_back = _radius(radius_back)
        self.thickness = float(thickness)
        self.semi_diameter = float(semi_diameter)
        if self.thickness <= 0.0:
            raise ValueError(f"thickness must be positive, got {thickness}")
        if self.semi_diameter <= 0.0:
            raise ValueError(f"semi_diameter must be positive, got {semi_diameter}")
        for name, r in (("radius_front", self.radius_front), ("radius_back", self.radius_back)):
            if abs(r) <= self.semi_diameter:
                raise ValueError(
                    f"|{name}| = {abs(r)} must exceed the semi-diameter {self.semi_diameter}: "
                    "a spherical face cannot reach further from its axis than its radius."
                )
        edge = self.edge_thickness
        if edge <= 0.0:
            raise ValueError(
                f"edge thickness {edge:.4g} is not positive: the faces cross before the rim. "
                "Increase the thickness or reduce the semi-diameter."
            )
        super().__init__(scene, size=2.0 * self.semi_diameter, position=position,
                         rotation=rotation, n=n)

    # --- geometry ------------------------------------------------------------

    @property
    def edge_thickness(self) -> float:
        """Axial thickness at the rim."""
        h = self.semi_diameter
        return self.thickness + surface_sag(h, self.radius_back) - surface_sag(h, self.radius_front)

    @property
    def axis_direction(self) -> Tuple[float, float]:
        """Unit vector along the optical axis, the way the light travels."""
        theta = math.radians(self._rotation)
        return (math.cos(theta), math.sin(theta))

    @property
    def front_vertex(self) -> Tuple[float, float]:
        return (float(self._position[0]), float(self._position[1]))

    @property
    def back_vertex(self) -> Tuple[float, float]:
        ux, uy = self.axis_direction
        return (self._position[0] + self.thickness * ux, self._position[1] + self.thickness * uy)

    def revolve_axis(self) -> Dict[str, List[float]]:
        """The optical axis as profile.json's ``symmetry.axis`` for a revolve export."""
        return {"point": list(self.front_vertex), "direction": list(self.axis_direction)}

    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """Counter-clockwise: S1 top to bottom, bottom rim, S2 bottom to top, top rim.

        A curved face is an arc through its vertex; a flat one a straight edge.
        """
        h, t = self.semi_diameter, self.thickness
        x1 = surface_sag(h, self.radius_front)
        x2 = t + surface_sag(h, self.radius_back)
        canonical: List[Tuple[float, float, bool]] = [(x1, h, False)]
        if not math.isinf(self.radius_front):
            canonical.append((0.0, 0.0, True))
        canonical += [(x1, -h, False), (x2, -h, False)]
        if not math.isinf(self.radius_back):
            canonical.append((t, 0.0, True))
        canonical.append((x2, h, False))

        ux, uy = self.axis_direction
        px, py = self.front_vertex
        return [
            {'x': px + x * ux - y * uy, 'y': py + x * uy + y * ux, 'arc': arc}
            for x, y, arc in canonical
        ]

    # --- paraxial optics -------------------------------------------------------

    def effective_focal_length(self, n: Optional[float] = None) -> float:
        """Paraxial effective focal length in air (thick-lens formula).

        Args:
            n: Refractive index; defaults to the lens's ``refIndex``.
        """
        n = self.refIndex if n is None else n
        c1, c2 = 1.0 / self.radius_front, 1.0 / self.radius_back
        power = (n - 1.0) * (c1 - c2 + (n - 1.0) * self.thickness * c1 * c2 / n)
        return math.inf if power == 0.0 else 1.0 / power

    def back_focal_length(self, n: Optional[float] = None) -> float:
        """Paraxial distance from the back vertex to the focus, along the light."""
        n = self.refIndex if n is None else n
        f = self.effective_focal_length(n)
        return f * (1.0 - (n - 1.0) * self.thickness / (n * self.radius_front))

    # --- conversion ------------------------------------------------------------

    @classmethod
    def from_spherical_lens(cls, lens: 'SphericalLens', first_surface: str = "r2") -> 'SingletLens':
        """The same lens, labelled, with the light's conventions.

        Args:
            lens: A SphericalLens with a valid path.
            first_surface: Which of its faces the light meets first, ``"r2"``
                or ``"r1"``. With ``p1`` above ``p2``, ``r1`` shapes the +x
                face and ``r2`` the -x face, so the default is light
                travelling along +x.

        Returns:
            A SingletLens with the same outline, the same refractive index and
            Cauchy coefficient, in the same scene.
        """
        if first_surface not in ("r1", "r2"):
            raise ValueError(f"first_surface must be 'r1' or 'r2', got {first_surface!r}")
        path = lens.path
        if not path or len(path) != 6:
            raise ValueError("the SphericalLens has no valid path to convert")
        # Ray Optics Simulation's own construction: the aperture line runs from
        # p1 (midpoint of entries 0, 1) to p2 (midpoint of entries 3, 4); the
        # face through entry 2 is r2's, the one through entry 5 is r1's.
        p1 = ((path[0]['x'] + path[1]['x']) / 2, (path[0]['y'] + path[1]['y']) / 2)
        p2 = ((path[3]['x'] + path[4]['x']) / 2, (path[3]['y'] + path[4]['y']) / 2)
        spans = glass_spans(path)
        r2_span, r1_span = spans[1], spans[3]
        r2_vertex = (path[2]['x'], path[2]['y'])
        r1_vertex = (path[5]['x'], path[5]['y'])
        if first_surface == "r2":
            front, back, v1, v2 = r2_span, r1_span, r2_vertex, r1_vertex
        else:
            front, back, v1, v2 = r1_span, r2_span, r1_vertex, r2_vertex
        ax, ay = v2[0] - v1[0], v2[1] - v1[1]
        thickness = math.hypot(ax, ay)
        if thickness == 0.0:
            raise ValueError("the SphericalLens has zero centre thickness")
        ux, uy = ax / thickness, ay / thickness

        def optiland_radius(span, vertex):
            if not span.is_arc:
                return math.inf
            downstream = (span.center[0] - vertex[0]) * ux + (span.center[1] - vertex[1]) * uy
            return math.copysign(span.radius, downstream)

        singlet = cls(
            lens.scene,
            radius_front=optiland_radius(front, v1),
            radius_back=optiland_radius(back, v2),
            thickness=thickness,
            semi_diameter=math.dist(p1, p2) / 2,
            n=lens.refIndex,
            position=v1,
            rotation=math.degrees(math.atan2(uy, ux)),
        )
        for attr in ("cauchyB", "cauchy_b"):  # the code base uses both spellings
            if hasattr(lens, attr):
                setattr(singlet, attr, getattr(lens, attr))
        return singlet

    def __repr__(self) -> str:
        return (f"SingletLens(R1={self.radius_front:g}, R2={self.radius_back:g}, "
                f"t={self.thickness:g}, h={self.semi_diameter:g}, n={self.refIndex:g})")


__all__ = ["SingletLens", "surface_sag"]
