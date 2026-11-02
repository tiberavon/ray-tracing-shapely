"""
Python-specific module: test physical scene
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
PHYSICAL SCENE + PHOTOMETRY -- framework verification
===============================================================================

Covers dev_doc/architecture/components/optical_elements_physics.md, "core" scope:
PhysicalScene, the ProjectionModel family, and Photoconversion.compute_irradiance
(W/m^2). compute_vout is DEFERRED (needs a luminous-efficacy convention), so it
is verified only to raise -- NotImplementedError when structurally valid, and
PhysicsContextError when the context is missing. The compute_irradiance path
carries the calibration/PhysicalScene guard coverage.

Every radiometric quantity here (calibration_factor,
power_per_m, projection heights/depths, photosensitivity, integration_time,
voltages, compute_irradiance's return value) is a pint.Quantity, not a bare
float -- see dev_doc/architecture/components/optical_elements_units.md. Scene geometry
(pixel_pitch_scene, p1/p2, scene_unit) stays plain float, unchanged.

Run with:
    python developer_tests/test_physical_scene.py

Or with pytest:
    pytest developer_tests/test_physical_scene.py -v
===============================================================================
"""

import sys
import math
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.optical_elements import (
    PhysicalScene,
    PhysicsContextError,
    ProjectionModel,
    CylindricalPerpendicularProjection,
    PointSourceProjection,
    LambertianStripProjection,
    RevolvedProjection,
    VALID_SYMMETRIES,
    Photoconversion,
    Photoemission,
    LIVCurve,
    LinearSensor,
    ureg,
    Quantity,
)

Q = ureg.Quantity


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as other:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {other!r}")
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# ---------------------------------------------------------------------------
# PhysicalScene
# ---------------------------------------------------------------------------

def test_physical_scene_unit_mm():
    ps = PhysicalScene('mm')
    assert ps.scene_unit == 'mm'
    assert ps.scene_unit_in_m == 1e-3


def test_physical_scene_unit_um():
    for spelling in ('µm', 'um'):
        ps = PhysicalScene(spelling)
        assert ps.scene_unit_in_m == 1e-6, spelling


def test_unknown_unit_raises():
    _assert_raises(ValueError, PhysicalScene, 'furlong')


def test_to_m_from_m_roundtrip():
    for unit in ('nm', 'um', 'mm', 'cm', 'm'):
        ps = PhysicalScene(unit)
        for x in (0.0, 1.0, 3.14159, 1234.5):
            assert math.isclose(ps.from_m(ps.to_m(x)), x, rel_tol=1e-12, abs_tol=1e-15)


def test_calibration_factor_none_by_default():
    assert PhysicalScene().calibration_factor is None


def test_set_calibration():
    ps = PhysicalScene()
    ps.set_calibration(brightness=0.5, power_per_m=Q(2.0, "W/m"))
    assert math.isclose(ps.calibration_factor.to("W/m").magnitude, 4.0)


def test_set_calibration_zero_brightness_raises():
    _assert_raises(ValueError, PhysicalScene().set_calibration, 0.0, Q(1.0, "W/m"))


# ---------------------------------------------------------------------------
# Dimensional safety -- the actual point [KC4]: a wrong unit or a bare
# float must raise, not silently compute a wrong number.
# ---------------------------------------------------------------------------

def test_set_calibration_rejects_plain_float():
    _assert_raises(ValueError, PhysicalScene().set_calibration, 1.0, 2.0)


def test_set_calibration_rejects_wrong_dimensionality():
    """J (energy) is not W/m (power per length) -- must not silently pass."""
    _assert_raises(ValueError, PhysicalScene().set_calibration, 1.0, Q(2.0, "J"))


def test_physical_scene_is_scene():
    assert isinstance(PhysicalScene(), Scene)


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------

def test_projection_base_not_implemented():
    base = ProjectionModel()
    _assert_raises(NotImplementedError, base.to_irradiance, 1.0, PhysicalScene())
    _assert_raises(NotImplementedError, base.to_power_per_m, 1.0, PhysicalScene())


def test_cylindrical_projection_to_irradiance():
    proj = CylindricalPerpendicularProjection(height_m=Q(2e-3, "m"))
    irr = proj.to_irradiance(Q(6.0, "W/m"), PhysicalScene())
    assert math.isclose(irr.to("W/m^2").magnitude, 3000.0)


def test_cylindrical_projection_to_power_per_m():
    proj = CylindricalPerpendicularProjection(height_m=Q(2e-3, "m"))
    ppm = proj.to_power_per_m(Q(6.0, "W"), PhysicalScene())
    assert math.isclose(ppm.to("W/m").magnitude, 3000.0)


def test_cylindrical_projection_roundtrip():
    """Multiplying to_irradiance's W/m^2 output back by the height recovers W/m.

    (to_irradiance and to_power_per_m both divide by height but act on different
    domains -- W/m->W/m^2 and W->W/m -- so they are not mutual inverses; the
    height factor is the recoverable invariant.)
    """
    proj = CylindricalPerpendicularProjection(height_m=Q(0.5e-3, "m"))
    ps = PhysicalScene()
    x = Q(7.25, "W/m")
    recovered = proj.to_irradiance(x, ps) * proj.height_m
    assert math.isclose(recovered.to("W/m").magnitude, x.to("W/m").magnitude, rel_tol=1e-12)


def test_cylindrical_bad_height_raises():
    _assert_raises(ValueError, CylindricalPerpendicularProjection, Q(0.0, "m"))


def test_cylindrical_height_rejects_plain_float():
    _assert_raises(ValueError, CylindricalPerpendicularProjection, 2e-3)


def test_cylindrical_height_rejects_wrong_dimensionality():
    """A duration is not a length -- must not silently pass."""
    _assert_raises(ValueError, CylindricalPerpendicularProjection, Q(2e-3, "s"))


def test_cylindrical_to_irradiance_rejects_wrong_dimensionality():
    """J/m^2 (a dose) is not W/m (the 2D simulator's power convention)."""
    proj = CylindricalPerpendicularProjection(Q(2e-3, "m"))
    _assert_raises(ValueError, proj.to_irradiance, Q(6.0, "J/m^2"), PhysicalScene())


def test_point_source_projection_to_irradiance():
    proj = PointSourceProjection(effective_depth_m=Q(0.5e-3, "m"))
    irr = proj.to_irradiance(Q(1.0, "W/m"), PhysicalScene())
    assert math.isclose(irr.to("W/m^2").magnitude, 2000.0)


def test_point_source_projection_to_power_per_m():
    proj = PointSourceProjection(effective_depth_m=Q(0.5e-3, "m"))
    ppm = proj.to_power_per_m(Q(1.0, "W"), PhysicalScene())
    assert math.isclose(ppm.to("W/m").magnitude, 2000.0)


def test_lambertian_projection_stub_raises():
    proj = LambertianStripProjection(height_m=Q(1e-3, "m"))
    _assert_raises(NotImplementedError, proj.to_irradiance, Q(1.0, "W/m"), PhysicalScene())
    _assert_raises(NotImplementedError, proj.to_power_per_m, Q(1.0, "W"), PhysicalScene())


# ---------------------------------------------------------------------------
# C-UNITS-01: the symmetry declaration
# (contract C-EYE-03)
# ---------------------------------------------------------------------------

def test_projection_base_has_no_symmetry():
    """The abstract base declares no symmetry -- it has no real projection
    to declare one for."""
    assert ProjectionModel().symmetry is None


def test_cylindrical_projection_symmetry_is_extrude():
    proj = CylindricalPerpendicularProjection(height_m=Q(2e-3, "m"))
    assert proj.symmetry == 'extrude'


def test_point_source_projection_symmetry_is_free():
    """Not 'revolve': an infinite-line-in-z approximation of a point source
    is neither symmetry cleanly, per the note's own distinction."""
    proj = PointSourceProjection(effective_depth_m=Q(0.5e-3, "m"))
    assert proj.symmetry == 'free'


def test_lambertian_projection_symmetry_is_extrude():
    proj = LambertianStripProjection(height_m=Q(1e-3, "m"))
    assert proj.symmetry == 'extrude'


def test_revolved_projection_symmetry_is_revolve_but_unimplemented():
    """RevolvedProjection exists (so 'revolve' has a named, discoverable
    class) but is a stub: constructing it and reading .symmetry works;
    actually converting units does not, because the conversion factor
    depends on radial position on the receiver, which the current
    to_irradiance/to_power_per_m signature has no argument for."""
    proj = RevolvedProjection(receiver_radius_m=Q(0.01, "m"))
    assert proj.symmetry == 'revolve'
    _assert_raises(NotImplementedError, proj.to_irradiance, Q(1.0, "W/m"), PhysicalScene())
    _assert_raises(NotImplementedError, proj.to_power_per_m, Q(1.0, "W"), PhysicalScene())


def test_revolved_projection_bad_radius_raises():
    _assert_raises(ValueError, RevolvedProjection, Q(0.0, "m"))


def test_valid_symmetries_covers_every_concrete_projection():
    """Every concrete ProjectionModel subclass's .symmetry is one of the
    three declared values -- the field can't silently drift to something
    the rest of the codebase (and C-UNITS-01) doesn't recognise."""
    instances = [
        CylindricalPerpendicularProjection(height_m=Q(1e-3, "m")),
        PointSourceProjection(effective_depth_m=Q(1e-3, "m")),
        LambertianStripProjection(height_m=Q(1e-3, "m")),
        RevolvedProjection(receiver_radius_m=Q(1e-2, "m")),
    ]
    for proj in instances:
        assert proj.symmetry in VALID_SYMMETRIES


def test_projection_model_rejects_invalid_symmetry():
    _assert_raises(ValueError, ProjectionModel, 'diagonal')


# ---------------------------------------------------------------------------
# Photoconversion
# ---------------------------------------------------------------------------

def test_photoconversion_for_sensor_catalogue():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=Q(771e-6, "s"))
    assert math.isclose(pc.photosensitivity.to("V/(lx*s)").magnitude, 280.0)
    assert math.isclose(pc.saturation_output_voltage.to("V").magnitude, 1.4)
    assert math.isclose(pc.projection.height_m.to("m").magnitude, 63.5e-6)


def test_photoconversion_unknown_model_raises():
    _assert_raises(ValueError, Photoconversion.for_sensor, 'NOPE',
                   pixel_pitch_scene=0.0055, integration_time=Q(1e-3, "s"))


def test_photoconversion_default_projection_cylindrical():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=Q(1e-3, "s"))
    assert isinstance(pc.projection, CylindricalPerpendicularProjection)


def test_compute_irradiance_values():
    pc = Photoconversion(pixel_pitch_scene=0.0055, photosensitivity=Q(280.0, "V/(lx*s)"),
                         integration_time=Q(1e-3, "s"),
                         projection=CylindricalPerpendicularProjection(Q(2e-3, "m")))
    ps = PhysicalScene()
    ps.set_calibration(brightness=1.0, power_per_m=Q(3.0, "W/m"))   # Phi = 3.0 W/m
    # pixel_data * Phi / height = [2, 1] * 3 / 2e-3 = [3000, 1500]
    irr = pc.compute_irradiance([2.0, 1.0], ps)
    assert irr.check("W/m^2")
    assert math.isclose(irr[0].to("W/m^2").magnitude, 3000.0)
    assert math.isclose(irr[1].to("W/m^2").magnitude, 1500.0)


def test_compute_irradiance_needs_physical_scene():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=Q(1e-3, "s"))
    _assert_raises(PhysicsContextError, pc.compute_irradiance, [1.0], Scene())


def test_compute_irradiance_needs_calibration():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=Q(1e-3, "s"))
    _assert_raises(PhysicsContextError, pc.compute_irradiance, [1.0], PhysicalScene())


def test_compute_vout_deferred():
    """Structurally valid call still raises NotImplementedError (deferred)."""
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=Q(1e-3, "s"))
    ps = PhysicalScene()
    ps.set_calibration(1.0, Q(1.0, "W/m"))
    _assert_raises(NotImplementedError, pc.compute_vout, [1.0], ps)


# ---------------------------------------------------------------------------
# Photoconversion: dimensional safety
# ---------------------------------------------------------------------------

def test_photoconversion_rejects_plain_float_photosensitivity():
    _assert_raises(ValueError, Photoconversion, 0.0055, 280.0, Q(1e-3, "s"),
                   CylindricalPerpendicularProjection(Q(2e-3, "m")))


def test_photoconversion_rejects_wrong_dimensionality_integration_time():
    """A voltage is not a duration -- must not silently pass."""
    _assert_raises(ValueError, Photoconversion, 0.0055, Q(280.0, "V/(lx*s)"),
                   Q(1e-3, "V"), CylindricalPerpendicularProjection(Q(2e-3, "m")))


def test_photoconversion_rejects_wrong_dimensionality_dark_output_voltage():
    """A current is not a voltage -- must not silently pass."""
    _assert_raises(
        ValueError, Photoconversion, 0.0055, Q(280.0, "V/(lx*s)"), Q(1e-3, "s"),
        CylindricalPerpendicularProjection(Q(2e-3, "m")),
        dark_output_voltage=Q(1.0, "A"),
    )


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

def test_photoemission_stub_raises():
    _assert_raises(NotImplementedError, Photoemission, 550.0, 20.0, 60.0, 1.0,
                   CylindricalPerpendicularProjection(Q(1e-3, "m")))


def test_liv_curve_stub_raises():
    _assert_raises(NotImplementedError, LIVCurve, [0.0], [0.0], [0.0])


# ---------------------------------------------------------------------------
# LinearSensor integration
# ---------------------------------------------------------------------------

def _sensor_scene(scene, photoconversion=None):
    """Horizontal 10-pixel sensor at y=0; source above shining straight down."""
    sensor = LinearSensor(
        scene,
        p1={'x': 0.0, 'y': 0.0},
        p2={'x': 10.0, 'y': 0.0},
        n_pixels=10,
        pixel_pitch=1.0,
        use_edge_blockers=False,
        name='sens',
        photoconversion=photoconversion,
    )
    source = AngleSource(scene)
    source.p1 = {'x': 5.0, 'y': 20.0}
    source.p2 = {'x': 5.0, 'y': 19.0}   # pointing -y toward the sensor
    source.emis_angle = 60
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)
    return sensor


def test_plain_scene_still_works():
    """LinearSensor with a plain Scene constructs and simulates fine."""
    scene = Scene()
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3
    scene.ray_mode_density = 20
    sensor = _sensor_scene(scene)
    Simulator(scene, max_rays=20000).run()
    assert sensor.pixel_data is not None and len(sensor.pixel_data) == 10


def test_linear_sensor_compute_irradiance_needs_photoconversion():
    scene = PhysicalScene()
    sensor = _sensor_scene(scene, photoconversion=None)
    _assert_raises(PhysicsContextError, sensor.compute_irradiance)


def test_linear_sensor_compute_vout_needs_physical_scene():
    scene = Scene()
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=1.0,
                                    integration_time=Q(1e-3, "s"))
    sensor = _sensor_scene(scene, photoconversion=pc)
    _assert_raises(PhysicsContextError, sensor.compute_vout)


def test_linear_sensor_compute_vout_deferred():
    scene = PhysicalScene()
    scene.set_calibration(1.0, Q(1.0, "W/m"))
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=1.0,
                                    integration_time=Q(1e-3, "s"))
    sensor = _sensor_scene(scene, photoconversion=pc)
    _assert_raises(NotImplementedError, sensor.compute_vout)


def test_linear_sensor_compute_irradiance_end_to_end():
    scene = PhysicalScene('mm')
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3
    scene.ray_mode_density = 20
    pc = Photoconversion(pixel_pitch_scene=1.0, photosensitivity=Q(280.0, "V/(lx*s)"),
                         integration_time=Q(1e-3, "s"),
                         projection=CylindricalPerpendicularProjection(Q(1e-3, "m")))
    sensor = _sensor_scene(scene, photoconversion=pc)
    scene.set_calibration(brightness=1.0, power_per_m=Q(1.0, "W/m"))
    Simulator(scene, max_rays=20000).run()
    irr = sensor.compute_irradiance()
    assert irr.check("W/m^2")
    assert len(irr) == 10
    magnitudes = irr.to("W/m^2").magnitude
    assert all(v >= 0.0 and math.isfinite(v) for v in magnitudes)
    assert any(v > 0.0 for v in magnitudes), "expected some illuminated pixels"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_physical_scene_unit_mm,
        test_physical_scene_unit_um,
        test_unknown_unit_raises,
        test_to_m_from_m_roundtrip,
        test_calibration_factor_none_by_default,
        test_set_calibration,
        test_set_calibration_zero_brightness_raises,
        test_set_calibration_rejects_plain_float,
        test_set_calibration_rejects_wrong_dimensionality,
        test_physical_scene_is_scene,
        test_projection_base_not_implemented,
        test_cylindrical_projection_to_irradiance,
        test_cylindrical_projection_to_power_per_m,
        test_cylindrical_projection_roundtrip,
        test_cylindrical_bad_height_raises,
        test_cylindrical_height_rejects_plain_float,
        test_cylindrical_height_rejects_wrong_dimensionality,
        test_cylindrical_to_irradiance_rejects_wrong_dimensionality,
        test_point_source_projection_to_irradiance,
        test_point_source_projection_to_power_per_m,
        test_lambertian_projection_stub_raises,
        test_projection_base_has_no_symmetry,
        test_cylindrical_projection_symmetry_is_extrude,
        test_point_source_projection_symmetry_is_free,
        test_lambertian_projection_symmetry_is_extrude,
        test_revolved_projection_symmetry_is_revolve_but_unimplemented,
        test_revolved_projection_bad_radius_raises,
        test_valid_symmetries_covers_every_concrete_projection,
        test_projection_model_rejects_invalid_symmetry,
        test_photoconversion_for_sensor_catalogue,
        test_photoconversion_unknown_model_raises,
        test_photoconversion_default_projection_cylindrical,
        test_compute_irradiance_values,
        test_compute_irradiance_needs_physical_scene,
        test_compute_irradiance_needs_calibration,
        test_compute_vout_deferred,
        test_photoconversion_rejects_plain_float_photosensitivity,
        test_photoconversion_rejects_wrong_dimensionality_integration_time,
        test_photoconversion_rejects_wrong_dimensionality_dark_output_voltage,
        test_photoemission_stub_raises,
        test_liv_curve_stub_raises,
        test_plain_scene_still_works,
        test_linear_sensor_compute_irradiance_needs_photoconversion,
        test_linear_sensor_compute_vout_needs_physical_scene,
        test_linear_sensor_compute_vout_deferred,
        test_linear_sensor_compute_irradiance_end_to_end,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {test.__name__}: {exc!r}")

    if failures:
        print(f"\n{failures} test(s) failed.")
    else:
        print("\nAll physical-scene + photometry tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
