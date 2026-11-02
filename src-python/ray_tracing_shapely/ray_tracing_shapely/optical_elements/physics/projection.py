"""
Python-specific module: Projection models (Photometry Framework)

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
PYTHON-SPECIFIC MODULE: ProjectionModel family
===============================================================================
Defines how a specific 3D source or detector geometry projects onto the 2D
simulation plane. The 2D simulator produces power in W/m (per unit out-of-plane
length z); a ProjectionModel converts between that and real 3D irradiance
(W/m^2) or total power (W).

P-PHYSICAL-SCENE, see dev_doc/architecture/components/
optical_elements_physics.md and C-UNITS-01
(dev_doc/architecture/contracts/C-UNITS-01.md) -- note the required
`symmetry` declaration C-UNITS-01 specifies is not yet implemented here.
Design rationale: dev_doc/architecture/components/optical_elements_physics.md.
===============================================================================
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..units import ensure_quantity, LENGTH, POWER, POWER_PER_LENGTH

if TYPE_CHECKING:
    import pint
    from ..physical_scene import PhysicalScene

#: C-UNITS-01's required declaration: which symmetry a 2D cross-section is
#: assumed to become solid under. See
#: contract C-EYE-03 for why this
#: is not a bookkeeping nicety -- concentration goes from n/sin(theta) to
#: n^2/sin^2(theta) depending on which one, and an undeclared choice makes
#: the two numbers indistinguishable while both stay plausible.
VALID_SYMMETRIES = ('revolve', 'extrude', 'free')


class ProjectionModel:
    """Abstract base for 2D <-> 3D power projection.

    All concrete subclasses must implement to_irradiance() and
    to_power_per_m(), and must declare which symmetry they assume the 2D
    cross-section becomes solid under (C-UNITS-01) -- 'revolve' (spun about
    the optical axis: a dish, a cone, a rotationally symmetric RXI),
    'extrude' (swept along a straight line: a trough, a linear Fresnel),
    or 'free' (neither -- an approximation with no clean closed-form
    solid, e.g. a point source represented as an infinite line in z).

    Args:
        symmetry: One of `VALID_SYMMETRIES`, or `None` for the abstract
            base itself (which has no real projection to declare a
            symmetry for -- both methods below always raise). Every
            concrete, usable subclass fixes this to one specific value in
            its own `__init__`; it is not a constructor argument a caller
            chooses freely, since a subclass's projection formula already
            *is* a specific symmetry, not a description of one.
    """

    def __init__(self, symmetry: Optional[str] = None) -> None:
        if symmetry is not None and symmetry not in VALID_SYMMETRIES:
            raise ValueError(
                f"symmetry={symmetry!r} is not one of {VALID_SYMMETRIES}."
            )
        self._symmetry = symmetry

    @property
    def symmetry(self) -> Optional[str]:
        """Which symmetry this projection assumes ('revolve' | 'extrude' |
        'free'), or None for the abstract base."""
        return self._symmetry

    def to_irradiance(self, power_per_m: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        """Convert 2D simulator power (W/m) to 3D irradiance (W/m^2).

        Used on the detector side: pixel_data x Phi gives W/m per bin; this
        method converts that to W/m^2 at the pixel.

        Args:
            power_per_m: pint.Quantity, dimensionality W/m.

        Returns:
            pint.Quantity, dimensionality W/m^2.
        """
        raise NotImplementedError

    def to_power_per_m(self, total_power: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        """Convert 3D source power (W) to the 2D simulator equivalent (W/m).

        Used on the source side: given the real emitted power, what W/m quantity
        should the 2D simulation represent?

        Args:
            total_power: pint.Quantity, dimensionality W.

        Returns:
            pint.Quantity, dimensionality W/m.
        """
        raise NotImplementedError


class CylindricalPerpendicularProjection(ProjectionModel):
    """Source or detector extends uniformly and infinitely in z (perpendicular
    to the simulation plane).

    Examples: a discharge lamp with axis perpendicular to the plane, a fibre
    viewed end-on, a strip LED viewed along its length, or a linear detector
    array whose active height is the full scene depth.

    This is the only geometry where the 2D simulation is an exact
    representation: L_z cancels on both source and detector sides. When both
    source and detector use it, relative measurements need no calibration.

    `symmetry = 'extrude'` -- swept along a straight line (the "trough" case
    in contract `C-EYE-03`), fixed by construction: this class
    *is* the extrude projection, not a configurable choice of one.

    Args:
        height_m: Physical z-extent of the source or detector, as a
            pint.Quantity with dimensionality m. For a source, the emitter
            length in z; for a detector, the pixel height in z. A physical
            detector/source dimension (a datasheet value), not a 2D scene
            coordinate [KC1: scene geometry stays a plain float; only the
            physical layer carries units].
    """

    def __init__(self, height_m: 'pint.Quantity') -> None:
        super().__init__(symmetry='extrude')
        height_m = ensure_quantity(height_m, LENGTH, name="height_m")
        if height_m.magnitude <= 0:
            raise ValueError("height_m must be positive.")
        self._height_m = height_m

    @property
    def height_m(self) -> 'pint.Quantity':
        """Physical z-extent, pint.Quantity with dimensionality m."""
        return self._height_m

    def to_irradiance(self, power_per_m: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        power_per_m = ensure_quantity(power_per_m, POWER_PER_LENGTH, name="power_per_m")
        return power_per_m / self._height_m

    def to_power_per_m(self, total_power: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        total_power = ensure_quantity(total_power, POWER, name="total_power")
        return total_power / self._height_m


class PointSourceProjection(ProjectionModel):
    """Source is a point emitter (LED, small lamp), or the detector subtends a
    small solid angle at the source.

    The 2D simulation treats a point source as an infinite line source in z. The
    projection is exact only at the calibration distance; elsewhere it is an
    approximation. ``effective_depth_m`` is the physical z-extent of the scene
    the 2D cross-section represents (e.g. LED package height, aperture diameter).

    `symmetry = 'free'` -- a compact/point-like source is neither a clean
    revolve nor a clean extrude; representing it as an infinite line in z is
    an explicit approximation, not a third exact symmetry. **This is not the
    revolved (dish/cone) case** in contract `C-EYE-03` -- a
    genuinely rotationally-symmetric concentrator has no ProjectionModel
    subclass yet (the note's `n^2/sin^2(theta)` case is not representable
    here today).

    Args:
        effective_depth_m: z-extent of the scene, as a pint.Quantity with
            dimensionality m.
    """

    def __init__(self, effective_depth_m: 'pint.Quantity') -> None:
        super().__init__(symmetry='free')
        effective_depth_m = ensure_quantity(effective_depth_m, LENGTH, name="effective_depth_m")
        if effective_depth_m.magnitude <= 0:
            raise ValueError("effective_depth_m must be positive.")
        self._depth = effective_depth_m

    @property
    def effective_depth_m(self) -> 'pint.Quantity':
        """Effective scene z-extent, pint.Quantity with dimensionality m."""
        return self._depth

    def to_irradiance(self, power_per_m: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        # At the calibration distance: W/m / effective_depth = W/m^2
        power_per_m = ensure_quantity(power_per_m, POWER_PER_LENGTH, name="power_per_m")
        return power_per_m / self._depth

    def to_power_per_m(self, total_power: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        # W / effective_depth = W/m (effective line-source strength)
        total_power = ensure_quantity(total_power, POWER, name="total_power")
        return total_power / self._depth


class LambertianStripProjection(ProjectionModel):
    """Extended Lambertian emitter (LED chip, diffuse surface) or a strip
    detector with a known active height.

    Models cos(theta)-weighted solid-angle projection. STUB: to_irradiance and
    to_power_per_m raise NotImplementedError until the LED roadmap provides the
    full Lambertian solid-angle integration.

    `symmetry = 'extrude'` -- a strip, same symmetry family as
    `CylindricalPerpendicularProjection`, just with Lambertian rather than
    uniform weighting across it.

    Args:
        height_m: Out-of-plane physical dimension, as a pint.Quantity with
            dimensionality m.
    """

    def __init__(self, height_m: 'pint.Quantity') -> None:
        super().__init__(symmetry='extrude')
        self._height_m = ensure_quantity(height_m, LENGTH, name="height_m")

    @property
    def height_m(self) -> 'pint.Quantity':
        """Out-of-plane physical dimension, pint.Quantity with dimensionality m."""
        return self._height_m

    def to_irradiance(self, power_per_m: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        raise NotImplementedError(
            "LambertianStripProjection is not yet implemented. "
            "See the LED light-source roadmap."
        )

    def to_power_per_m(self, total_power: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        raise NotImplementedError(
            "LambertianStripProjection is not yet implemented. "
            "See the LED light-source roadmap."
        )


class RevolvedProjection(ProjectionModel):
    """A profile spun about the optical axis -- a dish, a cone, a
    rotationally symmetric RXI or CPC. STUB: no concrete implementation
    exists yet. Registered here anyway so `'revolve'` has a named class,
    not just a string nobody can instantiate.

    `symmetry = 'revolve'`. This is the harder of the two real symmetries,
    structurally, not just because nobody has written it: for
    `CylindricalPerpendicularProjection` (extrude), the W/m -> W/m^2 factor
    is one fixed number (`height_m`) for the whole device, since the
    receiver strip has the same width at every point along its length. For
    a revolved receiver, an annulus at radius rho has area `2*pi*rho*drho`
    (contract `C-EYE-03`) -- the conversion factor *depends on
    radial position on the receiver*, which today's `to_irradiance`/
    `to_power_per_m(power_per_m, phys_scene)` signature has no argument
    for. Implementing this for real needs either a per-pixel radius
    argument or a receiver-geometry object to read one from -- an API
    change, not just a formula, and exactly the kind of thing the
    `profile.json` handoff (which carries a `symmetry` declaration
    alongside real receiver geometry) is positioned to supply once it
    exists. Blocked on that, not merely unwritten.

    Args:
        receiver_radius_m: Placeholder constructor parameter (the receiver
            disc's radius, as a pint.Quantity with dimensionality m) so a
            caller can at least construct and inspect `.symmetry` today;
            unused until `to_irradiance`/`to_power_per_m` are implemented
            for real.
    """

    def __init__(self, receiver_radius_m: 'pint.Quantity') -> None:
        super().__init__(symmetry='revolve')
        receiver_radius_m = ensure_quantity(receiver_radius_m, LENGTH, name="receiver_radius_m")
        if receiver_radius_m.magnitude <= 0:
            raise ValueError("receiver_radius_m must be positive.")
        self._receiver_radius_m = receiver_radius_m

    @property
    def receiver_radius_m(self) -> 'pint.Quantity':
        """Receiver disc radius, pint.Quantity with dimensionality m (placeholder; see class docstring)."""
        return self._receiver_radius_m

    def to_irradiance(self, power_per_m: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        raise NotImplementedError(
            "RevolvedProjection is not yet implemented: the W/m -> W/m^2 "
            "factor for a revolved receiver depends on radial position "
            "(area = 2*pi*rho*drho at radius rho), which this method's "
            "signature has no argument for. See the class docstring and "
            "contract C-EYE-03."
        )

    def to_power_per_m(self, total_power: 'pint.Quantity', phys_scene: 'PhysicalScene') -> 'pint.Quantity':
        raise NotImplementedError(
            "RevolvedProjection is not yet implemented: see to_irradiance's "
            "docstring for why this needs an API change, not just a formula."
        )
