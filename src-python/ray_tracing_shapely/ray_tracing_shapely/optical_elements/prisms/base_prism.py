"""
Python-specific module: base prism
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
BASE PRISM CLASS
===============================================================================
Base class for all prisms with:
- Dual-labeling architecture (functional + cardinal labels)
- Physics-driven geometry from parameters
- Convenient constructors

The dual-labeling system supports LLM-agent-in-the-loop optical design:
- Functional labels: what an edge does optically (invariant under rotation)
- Cardinal labels: where an edge points in scene coordinates (rotation-dependent)
===============================================================================
"""

from __future__ import annotations

import math
from abc import abstractmethod
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from ...core.scene import Scene

# Import Glass class
from ...core.glass_curves import curve_from_descriptor, transform_descriptor
from ...core.glass_spans import GlassSpan, glass_spans, outline_coords
from ...core.scene_objs.glass.glass import Glass


class BasePrism(Glass):
    """
    Base class for all prisms with convenient constructors.

    This class provides:
    - Dual-labeling architecture (functional labels + cardinal labels)
    - Abstract _compute_path() method for subclasses to define geometry
    - Anchor point support ('centroid' or 'apex' positioning)
    - apex_vertex property for querying apex location

    Subclasses must:
    1. Define _edge_roles and _vertex_roles class variables
    2. Define _apex_vertex_index class variable (or None if no apex)
    3. Implement _compute_path() to return vertex coordinates

    Attributes:
        size: Characteristic size parameter (meaning depends on subclass)
        _position: Reference point coordinates
        _rotation: Rotation angle in degrees
        _anchor: Position reference type ('centroid' or 'apex')
        _functional_labels: Dict mapping edge index to (short, long) functional labels
        _vertex_labels: Dict mapping vertex index to (short, long) labels
    """

    # --- Class variables (overridden by subclasses) ---
    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None

    # Classes that support local mesh refinement
    # (dev_doc/architecture/components/nonimaging_design.md)
    # override this to True and give _compute_path() a refinement_spans keyword
    # parameter. False by default so straight-edge subclasses (nothing to
    # refine) need no changes at all.
    _supports_refinement: ClassVar[bool] = False

    # Prism-specific type identifier
    type = 'BasePrism'

    def __init__(
        self,
        scene: 'Scene',
        size: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        n: float = 1.5,
        anchor: str = 'centroid',
        refinement_spans: Optional[List[Tuple[float, float, int]]] = None,
        **kwargs: Any
    ) -> None:
        """
        Initialize a prism.

        Args:
            scene: The scene this prism belongs to.
            size: Characteristic size (meaning depends on subclass).
            position: Reference point coordinates.
            rotation: Rotation angle in degrees (counterclockwise).
            n: Refractive index.
            anchor: Position reference - 'centroid' or 'apex'.
            refinement_spans: Local mesh-refinement spans, passed through to
                _compute_path() only for subclasses with
                _supports_refinement = True (dev_doc/architecture/components/nonimaging_design.md);
                ignored otherwise so straight-edge subclasses need no
                changes.
            **kwargs: Additional arguments passed to parent class.

        Raises:
            ValueError: If anchor is not 'centroid' or 'apex'.
        """
        if anchor not in ('centroid', 'apex'):
            raise ValueError(f"anchor must be 'centroid' or 'apex', got '{anchor}'")

        # Store parameters before calling parent __init__
        self.size = size
        self._position = position
        self._rotation = rotation
        self._anchor = anchor

        # Initialize parent class with empty JSON to avoid path issues
        super().__init__(scene, json_obj=None)

        # Set refractive index
        self.refIndex = n

        # Build geometry - this calls the subclass's _compute_path()
        if self._supports_refinement:
            self.path = self._compute_path(refinement_spans=refinement_spans)
        else:
            self.path = self._compute_path()

        # Apply both label layers
        self._apply_functional_labels()
        self._apply_vertex_labels()
        self.auto_label_cardinal()

    @abstractmethod
    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path from parameters.

        Contract:
        - Return vertices in counterclockwise order (Shapely convention).
        - Each vertex is {'x': float, 'y': float, 'arc': bool}. A circular
          arc is three entries: its start, a point it passes through flagged
          'arc': True, and its end (the Glass path convention).
        - Edges are spans (core.glass_spans): one per physical surface, a
          straight edge or a whole arc, numbered in path order. For a path
          with no arcs, edge i connects vertex i to vertex (i+1) % n.
        - _edge_roles is indexed by span; _vertex_roles by path entry.

        The implementation should:
        1. Compute vertices at origin in canonical orientation
        2. Apply rotation around origin
        3. Apply translation based on anchor point

        Returns:
            List of vertex dictionaries.
        """
        ...

    def _apply_rotation_and_translation(
        self,
        vertices: List[Tuple[float, float]]
    ) -> List[Dict[str, Union[float, bool]]]:
        """
        Apply rotation and translation to vertices based on anchor setting.

        Args:
            vertices: List of (x, y) tuples in canonical position/orientation.

        Returns:
            List of vertex dicts with 'x', 'y', 'arc' keys, properly positioned.
        """
        # Convert to radians
        theta = math.radians(self._rotation)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # First, rotate all vertices around origin
        rotated = []
        for x, y in vertices:
            rx = x * cos_t - y * sin_t
            ry = x * sin_t + y * cos_t
            rotated.append((rx, ry))

        # Compute centroid of rotated vertices
        cx = sum(v[0] for v in rotated) / len(rotated)
        cy = sum(v[1] for v in rotated) / len(rotated)

        # Determine translation offset based on anchor
        if self._anchor == 'centroid':
            # Move centroid to position
            offset_x = self._position[0] - cx
            offset_y = self._position[1] - cy
        elif self._anchor == 'apex':
            # Move apex vertex to position
            if self._apex_vertex_index is not None:
                apex = rotated[self._apex_vertex_index]
                offset_x = self._position[0] - apex[0]
                offset_y = self._position[1] - apex[1]
            else:
                # No apex defined, fall back to centroid
                offset_x = self._position[0] - cx
                offset_y = self._position[1] - cy
        else:
            offset_x = self._position[0] - cx
            offset_y = self._position[1] - cy

        # Apply translation and convert to path format
        path = []
        for rx, ry in rotated:
            path.append({
                'x': rx + offset_x,
                'y': ry + offset_y,
                'arc': False
            })

        return path

    # =========================================================================
    # Functional Labels (optical-function labels, rotation-invariant)
    # =========================================================================

    def _apply_functional_labels(self) -> None:
        """
        Apply optical-function labels to edges.

        Stored in a separate attribute from the cardinal labels in BaseGlass.
        Functional labels describe what an edge does optically (e.g., "Entrance",
        "Hypotenuse", "TIR Surface") and are invariant under rotation.

        Each _edge_roles entry is (short, long) or (short, long, role), where
        role is an optical_elements.roles.Role tag -- the third element is
        optional so existing 2-tuple _edge_roles keep working unchanged.
        """
        self._functional_labels: Dict[int, Tuple[str, str]] = {}
        self._edge_role_tags: Dict[int, Optional[Any]] = {}
        for i, entry in enumerate(self._edge_roles):
            short, long = entry[0], entry[1]
            self._functional_labels[i] = (short, long)
            self._edge_role_tags[i] = entry[2] if len(entry) > 2 else None

    def _apply_vertex_labels(self) -> None:
        """
        Apply optical-function labels to vertices.

        Vertex labels identify specific vertices (e.g., "Apex", "Right-Angle").
        """
        self._vertex_labels: Dict[int, Tuple[str, str]] = {}
        for i, (short, long) in enumerate(self._vertex_roles):
            self._vertex_labels[i] = (short, long)

    def get_functional_label(self, edge_index: int) -> Optional[Tuple[str, str]]:
        """
        Return (short, long) functional label for an edge.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            Tuple of (short_label, long_label), or None if not found.
        """
        return self._functional_labels.get(edge_index)

    def edge_reflects(self, edge_index: Optional[int]) -> bool:
        """
        Whether the edge that starts at path entry ``edge_index`` is mirror-coated:
        its functional label's mechanism is ``Mechanism.REFLECT``.

        The glass then reflects a ray there as a perfect mirror, from either side,
        instead of refracting it (``Glass.on_ray_incident``). The coating is the
        glass's own: no mirror object lies on the edge, which would tie with it.
        Labels are keyed by span, so the path entry is mapped to its span first;
        an element that declares no reflecting mechanism pays nothing.
        """
        from ..roles import Mechanism

        mechanisms = getattr(self, "_edge_mechanisms", None)
        if edge_index is None or not mechanisms or Mechanism.REFLECT not in mechanisms.values():
            return False
        span = next((sp for sp in self.spans if sp.path_indices[0] == edge_index), None)
        if span is None:
            return False
        label = self.get_functional_label(span.index)
        return label is not None and mechanisms.get(label[0]) is Mechanism.REFLECT

    def get_edge_role(self, edge_index: int) -> Optional[Any]:
        """
        Return the Role tag for an edge, if its _edge_roles entry supplied one.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            The optical_elements.roles.Role, or None if not tagged.
        """
        return self._edge_role_tags.get(edge_index)

    def find_edge_by_functional_label(self, short_label: str) -> Optional[int]:
        """
        Return edge index for a functional short label.

        Args:
            short_label: The functional short label (e.g., 'E', 'H', 'X').

        Returns:
            The edge index, or None if not found.
        """
        for i, (s, _) in self._functional_labels.items():
            if s == short_label:
                return i
        return None

    def get_vertex_label(self, vertex_index: int) -> Optional[Tuple[str, str]]:
        """
        Return (short, long) label for a vertex.

        Args:
            vertex_index: The vertex index (0-based).

        Returns:
            Tuple of (short_label, long_label), or None if not found.
        """
        return self._vertex_labels.get(vertex_index)

    def find_vertex_by_label(self, short_label: str) -> Optional[int]:
        """
        Return vertex index for a short label.

        Args:
            short_label: The vertex short label (e.g., 'A' for Apex).

        Returns:
            The vertex index, or None if not found.
        """
        for i, (s, _) in self._vertex_labels.items():
            if s == short_label:
                return i
        return None

    # =========================================================================
    # Apex Vertex Property
    # =========================================================================

    @property
    def apex_vertex(self) -> Optional[Tuple[float, float]]:
        """
        Return the coordinates of the apex vertex.

        The apex is defined as the vertex with the smallest interior angle,
        or the vertex explicitly designated by the subclass. For prisms with
        multiple equal-smallest angles (e.g., equilateral), the subclass
        defines which vertex is considered the "apex" for positioning.

        Returns:
            Tuple of (x, y) coordinates, or None if no apex is defined.
        """
        if self._apex_vertex_index is None:
            return None
        if not self.path or self._apex_vertex_index >= len(self.path):
            return None
        v = self.path[self._apex_vertex_index]
        return (v['x'], v['y'])

    # =========================================================================
    # Label Summary (for LLM agents)
    # =========================================================================

    def label_summary(self) -> str:
        """
        Return a text summary combining functional and cardinal labels.

        Useful for LLM agents to understand the full edge semantics.

        Example output:
          Edge 0: Entrance Face (E) | facing West (W)
          Edge 1: Hypotenuse (H)    | facing North-East (NE)
          Edge 2: Exit Face (X)     | facing South (S)

        Returns:
            Multi-line string describing all edges.
        """
        lines: List[str] = []
        for i in range(self._get_edge_count()):
            func = self._functional_labels.get(i, (str(i), str(i)))
            card = self.get_edge_label(i)  # cardinal, from BaseGlass
            card_short = card[0] if card else "?"
            card_long = card[1] if card else "?"
            lines.append(
                f"Edge {i}: {func[1]} ({func[0]}) | facing {card_long} ({card_short})"
            )
        return "\n".join(lines)

    # =========================================================================
    # Escape Hatch Constructor
    # =========================================================================

    @classmethod
    def from_vertices(
        cls,
        scene: 'Scene',
        vertices: List[Tuple[float, float]],
        n: float = 1.5
    ) -> 'BasePrism':
        """
        Create from explicit vertex coordinates (escape hatch).

        Contract:
        - This method lives on BasePrism only. Subclasses inherit but do not override.
        - Functional labels (_edge_roles, _vertex_roles) are NOT applied, because
          the geometry may not match the subclass's expected angles.
        - Cardinal labels ARE applied via auto_label_cardinal().
        - The returned instance has numeric edge labels (0, 1, 2, ...) for the
          functional layer.
        - Use this when you have a custom geometry that doesn't fit standard
          prism templates but still want dual-labeling infrastructure.

        Args:
            scene: The scene this prism belongs to.
            vertices: List of (x, y) tuples defining the prism boundary (CCW order).
            n: Refractive index.

        Returns:
            A new BasePrism instance with custom geometry.
        """
        # Create instance without calling __init__ to avoid _compute_path
        instance = object.__new__(cls)

        # Initialize parent class manually
        Glass.__init__(instance, scene, json_obj=None)

        # Set attributes
        instance.size = 0.0  # Not meaningful for custom geometry
        instance._position = (0.0, 0.0)
        instance._rotation = 0.0
        instance._anchor = 'centroid'
        instance.refIndex = n

        # Build path from vertices
        instance.path = [
            {'x': x, 'y': y, 'arc': False}
            for x, y in vertices
        ]

        # Apply numeric functional labels (not type-specific), and no roles
        instance._functional_labels = {
            i: (str(i), f"Edge {i}")
            for i in range(len(vertices))
        }
        instance._edge_role_tags = {}
        instance._vertex_labels = {
            i: (str(i), f"Vertex {i}")
            for i in range(len(vertices))
        }

        # Apply cardinal labels based on geometry
        instance.auto_label_cardinal()

        return instance

    @classmethod
    def from_profile(
        cls,
        scene: 'Scene',
        profile: Dict[str, Any],
        *,
        n: float,
        normal_tol: float = 1e-6,
        closure_tol: float = 1e-9,
        sag_tol: float = 1e-9,
    ) -> 'BasePrism':
        """
        Create from a profile.json dict, keeping its labels (the labelled escape hatch).

        The inverse of profile_export.export_profile. Where from_vertices
        gives every edge a numeric placeholder label, this applies each
        span's short/long label, Role and Mechanism, so a device that went
        out to 3D and came back stays addressable by the same names
        (C-LABEL-02). The result is always a plain BasePrism, whichever class
        this is called on: it has the profile's geometry, not a subclass's
        construction parameters, and an instance claiming to be a
        RefractometerPrism without n_prism or face_angle would be a worse
        lie than an honest BasePrism.

        Contract:
        - A span's ``curve`` says what it is (absent means a line, as in
          schema 1.0). A line has exactly two points. A ``circle`` has at
          least three, every one within ``sag_tol`` of the circle; it is
          rebuilt as an arc path entry through its middle sample, so the
          simulator traces the exact circle. A ``conic`` or ``spline``
          (schema 1.2) has at least two points, its ends on the curve and
          every sample within ``sag_tol`` of it; it is rebuilt as a curve
          path entry carrying its descriptor, traced exactly. Any other
          curve type raises NotImplementedError rather than being flattened.
        - ``symmetry.kind = "revolve"``: the spans are the half-section left
          of the axis, from the axis to the axis; the full section is
          rebuilt by mirroring it, and a surface the axis cut in two (a lens
          face, a flat face across the axis) is joined back into one span.
        - ``body`` must be ``"solid"`` (or absent): a sheet has no interior
          and is not glass.
        - Spans close up: each span's end point is the next span's start
          point, the last wrapping to the first, within ``closure_tol``.
        - The outline is counterclockwise (the Shapely convention BasePrism
          assumes), and every stored normal agrees with the outward normal
          the geometry implies at its point, within ``normal_tol`` on the
          cosine -- for a curved span, at every sample, so the slope
          is checked as well as the position. A disagreeing normal is the one profile defect
          C-PROFILE-01 calls silent; here it raises.
        - Role and mechanism strings must belong to the shared vocabulary
          (C-VOCAB-01); an unknown one raises ValueError from the enum.
        - Vertex labels are numeric: profile.json does not carry them.

        Args:
            scene: The scene this prism belongs to.
            profile: A profile.json-shaped dict (C-PROFILE-01).
            n: Refractive index. Required: profile.json has no standard
                field for it, and a silent default would rebuild the device
                in the wrong glass.
            normal_tol: Allowed 1 - cos(angle) between a stored normal and
                the one implied by the geometry.
            closure_tol: Allowed gap between consecutive spans' endpoints,
                and distance from the axis of a revolve half-section's ends,
                in scene units.
            sag_tol: Allowed distance of a curved span's samples from its
                descriptor, in scene units.

        Returns:
            A new BasePrism with the profile's geometry and labels.

        Raises:
            NotImplementedError: For a line span with other than two points,
                or a curve type other than line, circle, conic and spline.
            ValueError: For an empty profile, a sheet body, an outline that
                does not close, a clockwise outline, a sample off its
                circle, a stored normal that disagrees with the geometry, a
                malformed revolve half-section, an unknown role or
                mechanism, or two spans sharing a short label but declaring
                different mechanisms.
        """
        from ..roles import Mechanism, Role
        from .profile_export import revolve_axis

        spans = profile["spans"]
        points = profile["points"]
        normals = profile["normals"]
        if not spans:
            raise ValueError("profile has no spans -- nothing to build.")
        body = profile.get("body", "solid")
        if body != "solid":
            raise ValueError(
                f"profile body is {body!r}; only a 'solid' (glass with an interior) "
                "can be rebuilt as a BasePrism."
            )

        # --- read each span: end points, samples, normals, curve ---------------
        pieces: List[Dict[str, Any]] = []
        for i, span in enumerate(spans):
            curve = span.get("curve") or {"type": "line"}
            kind = curve.get("type")
            count = span["index_end"] - span["index_start"]
            label = span.get("short_label")
            samples = [tuple(points[k]) for k in range(span["index_start"], span["index_end"])]
            stored = [tuple(normals[k]) for k in range(span["index_start"], span["index_end"])]
            if kind == "line":
                if count != 2:
                    raise NotImplementedError(
                        f"Span {label!r} has {count} points; a span without a curve "
                        "descriptor must be a straight two-point span."
                    )
            elif kind == "circle":
                if count < 3:
                    raise ValueError(f"circle span {label!r} has {count} points; at least 3 are needed.")
                center = (float(curve["center"][0]), float(curve["center"][1]))
                radius = float(curve["radius"])
                for p in samples:
                    off = abs(math.dist(p, center) - radius)
                    if off > sag_tol:
                        raise ValueError(
                            f"span {label!r}: sample {list(p)} lies {off:.3g} from its "
                            f"circle (centre {list(center)}, radius {radius})."
                        )
            elif kind in ("conic", "asphere", "spline"):
                if count < 2:
                    raise ValueError(f"{kind} span {label!r} has {count} points; at least 2 are needed.")
                shape = curve_from_descriptor(curve, samples[0], samples[-1])
                for p in samples:
                    off = shape.nearest(p)[0]
                    if off > sag_tol:
                        raise ValueError(
                            f"span {label!r}: sample {list(p)} lies {off:.3g} from its {kind} curve."
                        )
            else:
                raise NotImplementedError(
                    f"Span {label!r} has curve type {kind!r}; only 'line', 'circle', 'conic', "
                    "'asphere' and 'spline' can be rebuilt in 2D."
                )
            pieces.append({
                "span": span, "kind": kind, "curve": curve, "samples": samples,
                "normals": stored, "through": None,
            })

        # --- a revolve half-section: mirror it into the full section ------------
        symmetry = profile.get("symmetry") or {}
        if symmetry.get("kind") == "revolve":
            pieces = cls._mirror_half_section(pieces, *revolve_axis(symmetry), closure_tol, sag_tol)

        count = len(pieces)
        for i in range(count):
            gap = math.dist(pieces[i]["samples"][-1], pieces[(i + 1) % count]["samples"][0])
            if gap > closure_tol:
                raise ValueError(
                    f"profile outline does not close: span {i} "
                    f"({pieces[i]['span'].get('short_label')!r}) ends {gap:.3g} from the "
                    f"start of span {(i + 1) % count}."
                )

        # --- the path: a line is its start; an arc its start and a through-point
        path: List[Dict[str, Union[float, bool]]] = []
        for piece in pieces:
            start = piece["samples"][0]
            path.append({'x': start[0], 'y': start[1], 'arc': False})
            if piece["kind"] in ("conic", "asphere", "spline"):
                path[-1]['curve'] = piece["curve"]
            if piece["kind"] == "circle":
                through = piece["through"]
                if through is None:
                    cx, cy = piece["curve"]["center"]
                    r = float(piece["curve"]["radius"])
                    mx, my = piece["samples"][len(piece["samples"]) // 2]
                    d = math.hypot(mx - cx, my - cy)
                    through = (cx + r * (mx - cx) / d, cy + r * (my - cy) / d)
                path.append({'x': through[0], 'y': through[1], 'arc': True})

        ring = outline_coords(path)
        signed_area = 0.5 * sum(
            ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
            for i in range(len(ring))
        )
        if signed_area <= 0.0:
            raise ValueError(
                "profile outline is clockwise or degenerate (signed area "
                f"{signed_area:.3g}); BasePrism requires counterclockwise order."
            )

        built = glass_spans(path)
        if len(built) != count:
            raise ValueError(
                f"the rebuilt outline has {len(built)} surfaces for {count} spans; "
                "a circle span's samples do not describe one arc."
            )
        for piece, span in zip(pieces, built):
            label = piece["span"].get("short_label")
            if piece["kind"] == "circle":
                if not span.is_arc or abs(span.radius - float(piece["curve"]["radius"])) > sag_tol:
                    raise ValueError(f"span {label!r}: the rebuilt arc does not match its descriptor.")
                implied = [span.outward_normal_at(p) for p in piece["samples"]]
            elif piece["kind"] in ("conic", "asphere", "spline"):
                if span.kind != piece["kind"]:
                    raise ValueError(f"span {label!r}: the rebuilt edge is not a {piece['kind']}.")
                implied = [span.outward_normal_at(p) for p in piece["samples"]]
            else:
                (x1, y1), (x2, y2) = span.start, span.end
                length = math.hypot(x2 - x1, y2 - y1)
                implied = [((y2 - y1) / length, -(x2 - x1) / length)] * 2
            for p, have, want in zip(piece["samples"], piece["normals"], implied):
                cos_angle = have[0] * want[0] + have[1] * want[1]
                if 1.0 - cos_angle > normal_tol:
                    raise ValueError(
                        f"span {label!r}: stored normal {list(have)} at {list(p)} "
                        f"disagrees with the outward normal its geometry implies "
                        f"{[want[0], want[1]]}."
                    )

        corners = [(e['x'], e['y']) for e in path if not e['arc']]
        instance = BasePrism.from_vertices(scene, corners, n=n)
        instance.path = path
        instance._vertex_labels = {
            i: (str(i), f"Vertex {i}") for i, e in enumerate(path) if not e['arc']
        }

        edge_roles: List[Tuple[str, str, Optional[Any]]] = []
        mechanisms: Dict[str, Optional[Any]] = {}
        for i, piece in enumerate(pieces):
            span = piece["span"]
            short = span.get("short_label") or str(i)
            long = span.get("long_label") or f"Edge {i}"
            role = Role(span["role"]) if span.get("role") is not None else None
            mechanism = (
                Mechanism(span["mechanism"]) if span.get("mechanism") is not None else None
            )
            if short in mechanisms and mechanisms[short] is not mechanism:
                raise ValueError(
                    f"spans labelled {short!r} declare different mechanisms "
                    f"({mechanisms[short]} and {mechanism}); the mechanism map is "
                    "keyed by short label and cannot hold both."
                )
            mechanisms[short] = mechanism
            edge_roles.append((short, long, role))

        instance._edge_roles = edge_roles
        instance._edge_mechanisms = mechanisms
        instance._apply_functional_labels()
        instance.auto_label_cardinal()
        return instance

    @staticmethod
    def _mirror_half_section(
        pieces: List[Dict[str, Any]],
        point: Tuple[float, float],
        direction: Tuple[float, float],
        closure_tol: float,
        sag_tol: float,
    ) -> List[Dict[str, Any]]:
        """The full section from a revolve half-section (from_profile's helper).

        The half-section runs from the axis to the axis on its left side.
        Its mirror image, traversed backwards, closes the outline. Where a
        surface meets its own image on the axis smoothly (an arc whose
        centre is on the axis, a line perpendicular to it), the two halves
        are one surface again; elsewhere (a point on the axis, such as a
        cone's tip) they stay two spans with the same label.
        """
        def mirror(p):
            vx, vy = p[0] - point[0], p[1] - point[1]
            along = vx * direction[0] + vy * direction[1]
            return (point[0] + 2 * along * direction[0] - vx,
                    point[1] + 2 * along * direction[1] - vy)

        def mirror_normal(nrm):
            along = nrm[0] * direction[0] + nrm[1] * direction[1]
            return (2 * along * direction[0] - nrm[0], 2 * along * direction[1] - nrm[1])

        def left(p):
            return direction[0] * (p[1] - point[1]) - direction[1] * (p[0] - point[0])

        for end in (pieces[0]["samples"][0], pieces[-1]["samples"][-1]):
            if abs(left(end)) > closure_tol:
                raise ValueError(
                    f"revolve half-section must start and end on the axis; {list(end)} "
                    f"is {left(end):.3g} from it."
                )
        for piece in pieces:
            for p in piece["samples"]:
                if left(p) < -closure_tol:
                    raise ValueError(
                        f"revolve half-section crosses to the right of its axis at {list(p)}."
                    )

        images = []
        for piece in reversed(pieces):
            curve = dict(piece["curve"])
            if piece["kind"] == "circle":
                curve["center"] = list(mirror(curve["center"]))
            elif piece["kind"] in ("conic", "asphere", "spline"):
                curve = transform_descriptor(curve, mirror, mirror_normal)
            images.append({
                "span": piece["span"], "kind": piece["kind"], "curve": curve,
                "samples": [mirror(p) for p in reversed(piece["samples"])],
                "normals": [mirror_normal(nrm) for nrm in reversed(piece["normals"])],
                "through": None,
            })

        def shape_of(piece):
            return curve_from_descriptor(piece["curve"], piece["samples"][0], piece["samples"][-1])

        def joins_smoothly(a, b):
            if a["kind"] != b["kind"] or a["span"].get("short_label") != b["span"].get("short_label"):
                return False
            if a["kind"] == "circle":
                return math.dist(a["curve"]["center"], b["curve"]["center"]) <= sag_tol
            if a["kind"] in ("conic", "asphere"):   # the same surface on both sides of the axis
                ca, cb = a["curve"], b["curve"]
                ra, rb = ca.get("radius"), cb.get("radius")
                same_radius = (ra is None and rb is None) or (
                    ra is not None and rb is not None and abs(float(ra) - float(rb)) <= sag_tol)
                same_terms = list(ca.get("coefficients", [])) == list(cb.get("coefficients", []))
                return (math.dist(ca["vertex"], cb["vertex"]) <= sag_tol
                        and math.dist(ca["axis"], cb["axis"]) <= 1e-12 and same_radius and same_terms
                        and abs(float(ca["conic"]) - float(cb["conic"])) <= 1e-12)
            if a["kind"] == "spline":  # one spline: b's points are a's, in some order
                return spline_join_domain(a, b) is not None
            (ax, ay), (bx, by) = a["samples"][0], b["samples"][-1]
            jx, jy = a["samples"][-1]
            cross = (jx - ax) * (by - jy) - (jy - ay) * (bx - jx)
            return abs(cross) <= sag_tol * max(math.dist((ax, ay), (jx, jy)), 1.0)

        def spline_join_domain(a, b):
            """If b runs on along the same spline as a (its points are a's, in the same or
            the reverse order, as when b is a's mirror image and the spline is symmetric
            about the axis), the joined edge's parameter range on a's spline; else None."""
            pa, ta = a["curve"]["points"], a["curve"]["tangents"]
            pb, tb = b["curve"]["points"], b["curve"]["tangents"]
            if len(pa) != len(pb):
                return None
            last = len(pa) - 1
            sa, sb = shape_of(a), shape_of(b)
            for flip in (False, True):
                idx = (lambda k: last - k) if flip else (lambda k: k)
                sign = -1.0 if flip else 1.0
                if all(math.dist(pb[k], pa[idx(k)]) <= sag_tol
                       and math.dist(tb[k], [sign * ta[idx(k)][0], sign * ta[idx(k)][1]]) <= 1e-9
                       for k in range(len(pa))):
                    b_start = last - sb.p_start if flip else sb.p_start
                    b_end = last - sb.p_end if flip else sb.p_end
                    if abs(b_start - sa.p_end) <= 1e-9 and (b_end - b_start) * (sa.p_end - sa.p_start) > 0:
                        return (sa.p_start, b_end)
            return None

        def join(a, b):
            joined = dict(a)
            joined["samples"] = a["samples"] + b["samples"][1:]
            joined["normals"] = a["normals"] + b["normals"][1:]
            if a["kind"] == "spline":
                p0, p1 = spline_join_domain(a, b)
                curve = {k: v for k, v in a["curve"].items() if k != "domain"}
                if {min(p0, p1), max(p0, p1)} != {0.0, float(len(curve["points"]) - 1)}:
                    curve["domain"] = [p0, p1]
                joined["curve"] = curve
            if a["kind"] in ("conic", "asphere", "spline"):
                return joined
            if a["kind"] == "circle":
                joined["through"] = a["samples"][-1]  # the vertex, on the axis
            else:
                joined["samples"] = [a["samples"][0], b["samples"][-1]]
                joined["normals"] = [a["normals"][0], b["normals"][-1]]
            return joined

        full = list(pieces)
        # Junction 1: the half-section's last span meets its own image.
        if joins_smoothly(full[-1], images[0]):
            full[-1] = join(full[-1], images[0])
            images = images[1:]
        full += images
        # Junction 2 (wrapping round): the last image meets the first span.
        if len(full) > 1 and joins_smoothly(full[-1], full[0]):
            full[0] = join(full[-1], full[0])
            full.pop()
        return full

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @property
    def spans(self) -> List[GlassSpan]:
        """The outline's physical surfaces in edge-index order (core.glass_spans).

        For a straight-edged prism, span i is exactly edge i (path entry i to
        i+1). An arc's three path entries are one span.
        """
        return glass_spans(self.path or [])

    def get_span(self, edge_index: int) -> Optional[GlassSpan]:
        """The span (physical surface) with this edge index, or None if invalid."""
        spans = self.spans
        if edge_index < 0 or edge_index >= len(spans):
            return None
        return spans[edge_index]

    def get_span_curve(self, edge_index: int) -> Optional[Dict[str, Any]]:
        """The exact shape of an edge, as profile.json's ``curve`` descriptor.

        ``{"type": "line"}`` or ``{"type": "circle", "center": [a, b],
        "radius": R}``; None for an invalid index.
        """
        span = self.get_span(edge_index)
        return span.curve if span is not None else None

    def get_edge_endpoints(self, edge_index: int) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        Get the start and end points of an edge (a span: for an arc, its two ends).

        Args:
            edge_index: The edge index (0-based).

        Returns:
            Tuple of ((x1, y1), (x2, y2)), or None if invalid index.
        """
        span = self.get_span(edge_index)
        if span is None:
            return None
        return (span.start, span.end)

    def get_edge_length(self, edge_index: int) -> float:
        """
        Get the length of an edge (the arc length, for a curved one).

        Args:
            edge_index: The edge index (0-based).

        Returns:
            The edge length, or 0.0 if invalid index.
        """
        span = self.get_span(edge_index)
        return span.length if span is not None else 0.0

    def get_interior_angle(self, vertex_index: int) -> float:
        """
        Get the interior angle at a vertex in degrees.

        Args:
            vertex_index: The vertex index (0-based).

        Returns:
            The interior angle in degrees, or 0.0 if invalid.
        """
        if not self.path or vertex_index < 0 or vertex_index >= len(self.path):
            return 0.0

        n = len(self.path)
        # Get three consecutive vertices
        p0 = self.path[(vertex_index - 1) % n]
        p1 = self.path[vertex_index]
        p2 = self.path[(vertex_index + 1) % n]

        # Vectors from p1 to p0 and p1 to p2
        v1 = (p0['x'] - p1['x'], p0['y'] - p1['y'])
        v2 = (p2['x'] - p1['x'], p2['y'] - p1['y'])

        # Dot product and magnitudes
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
        mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

        if mag1 == 0 or mag2 == 0:
            return 0.0

        # Clamp to avoid numerical issues with acos
        cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.degrees(math.acos(cos_angle))

    def get_centroid(self) -> Tuple[float, float]:
        """
        Get the centroid of the prism.

        Returns:
            Tuple of (x, y) coordinates.
        """
        return self._get_centroid()

    def signed_area(self) -> float:
        """
        Compute the signed area of the prism polygon.

        Positive area indicates counterclockwise vertex ordering.
        Negative area indicates clockwise ordering.

        Returns:
            The signed area.
        """
        if not self.path or len(self.path) < 3:
            return 0.0

        ring = outline_coords(self.path)  # arcs followed, not cut across
        area = 0.0
        n = len(ring)
        for i in range(n):
            j = (i + 1) % n
            area += ring[i][0] * ring[j][1] - ring[j][0] * ring[i][1]
        return area / 2.0
