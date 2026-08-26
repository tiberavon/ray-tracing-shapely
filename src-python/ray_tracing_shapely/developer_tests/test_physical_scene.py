"""
===============================================================================
PHYSICAL SCENE + PHOTOMETRY -- framework verification
===============================================================================

Covers dev_doc/roadmap/proposed/physical_scene_photometry.md, "core" scope:
PhysicalScene, the ProjectionModel family, and Photoconversion.compute_irradiance
(W/m^2). compute_vout is DEFERRED (needs a luminous-efficacy convention), so it
is verified only to raise -- NotImplementedError when structurally valid, and
PhysicsContextError when the context is missing. The compute_irradiance path
carries the calibration/PhysicalScene guard coverage.

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
    Photoconversion,
    Photoemission,
    LIVCurve,
    LinearSensor,
)


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
    ps.set_calibration(brightness=0.5, power_per_m_W=2.0)
    assert math.isclose(ps.calibration_factor, 4.0)


def test_set_calibration_zero_brightness_raises():
    _assert_raises(ValueError, PhysicalScene().set_calibration, 0.0, 1.0)


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
    proj = CylindricalPerpendicularProjection(height_m=2e-3)
    assert math.isclose(proj.to_irradiance(6.0, PhysicalScene()), 3000.0)


def test_cylindrical_projection_to_power_per_m():
    proj = CylindricalPerpendicularProjection(height_m=2e-3)
    assert math.isclose(proj.to_power_per_m(6.0, PhysicalScene()), 3000.0)


def test_cylindrical_projection_roundtrip():
    """Multiplying to_irradiance's W/m^2 output back by the height recovers W/m.

    (to_irradiance and to_power_per_m both divide by height but act on different
    domains -- W/m->W/m^2 and W->W/m -- so they are not mutual inverses; the
    height factor is the recoverable invariant.)
    """
    proj = CylindricalPerpendicularProjection(height_m=0.5e-3)
    ps = PhysicalScene()
    x = 7.25  # W/m
    assert math.isclose(proj.to_irradiance(x, ps) * proj.height_m, x, rel_tol=1e-12)


def test_cylindrical_bad_height_raises():
    _assert_raises(ValueError, CylindricalPerpendicularProjection, 0.0)


def test_point_source_projection_to_irradiance():
    proj = PointSourceProjection(effective_depth_m=0.5e-3)
    assert math.isclose(proj.to_irradiance(1.0, PhysicalScene()), 2000.0)


def test_point_source_projection_to_power_per_m():
    proj = PointSourceProjection(effective_depth_m=0.5e-3)
    assert math.isclose(proj.to_power_per_m(1.0, PhysicalScene()), 2000.0)


def test_lambertian_projection_stub_raises():
    proj = LambertianStripProjection(height_m=1e-3)
    _assert_raises(NotImplementedError, proj.to_irradiance, 1.0, PhysicalScene())
    _assert_raises(NotImplementedError, proj.to_power_per_m, 1.0, PhysicalScene())


# ---------------------------------------------------------------------------
# Photoconversion
# ---------------------------------------------------------------------------

def test_photoconversion_for_sensor_catalogue():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=771e-6)
    assert math.isclose(pc.photosensitivity, 280.0)
    assert math.isclose(pc.saturation_output_voltage, 1.4)
    assert math.isclose(pc.projection.height_m, 63.5e-6)


def test_photoconversion_unknown_model_raises():
    _assert_raises(ValueError, Photoconversion.for_sensor, 'NOPE',
                   pixel_pitch_scene=0.0055, integration_time=1e-3)


def test_photoconversion_default_projection_cylindrical():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=1e-3)
    assert isinstance(pc.projection, CylindricalPerpendicularProjection)


def test_compute_irradiance_values():
    pc = Photoconversion(pixel_pitch_scene=0.0055, photosensitivity=280.0,
                         integration_time=1e-3,
                         projection=CylindricalPerpendicularProjection(2e-3))
    ps = PhysicalScene()
    ps.set_calibration(brightness=1.0, power_per_m_W=3.0)   # Phi = 3.0 W/m
    # pixel_data * Phi / height = [2, 1] * 3 / 2e-3 = [3000, 1500]
    irr = pc.compute_irradiance([2.0, 1.0], ps)
    assert math.isclose(irr[0], 3000.0) and math.isclose(irr[1], 1500.0)


def test_compute_irradiance_needs_physical_scene():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=1e-3)
    _assert_raises(PhysicsContextError, pc.compute_irradiance, [1.0], Scene())


def test_compute_irradiance_needs_calibration():
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=1e-3)
    _assert_raises(PhysicsContextError, pc.compute_irradiance, [1.0], PhysicalScene())


def test_compute_vout_deferred():
    """Structurally valid call still raises NotImplementedError (deferred)."""
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=0.0055,
                                    integration_time=1e-3)
    ps = PhysicalScene()
    ps.set_calibration(1.0, 1.0)
    _assert_raises(NotImplementedError, pc.compute_vout, [1.0], ps)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

def test_photoemission_stub_raises():
    _assert_raises(NotImplementedError, Photoemission, 550.0, 20.0, 60.0, 1.0,
                   CylindricalPerpendicularProjection(1e-3))


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
                                    integration_time=1e-3)
    sensor = _sensor_scene(scene, photoconversion=pc)
    _assert_raises(PhysicsContextError, sensor.compute_vout)


def test_linear_sensor_compute_vout_deferred():
    scene = PhysicalScene()
    scene.set_calibration(1.0, 1.0)
    pc = Photoconversion.for_sensor('S13131-1536', pixel_pitch_scene=1.0,
                                    integration_time=1e-3)
    sensor = _sensor_scene(scene, photoconversion=pc)
    _assert_raises(NotImplementedError, sensor.compute_vout)


def test_linear_sensor_compute_irradiance_end_to_end():
    scene = PhysicalScene('mm')
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3
    scene.ray_mode_density = 20
    pc = Photoconversion(pixel_pitch_scene=1.0, photosensitivity=280.0,
                         integration_time=1e-3,
                         projection=CylindricalPerpendicularProjection(1e-3))
    sensor = _sensor_scene(scene, photoconversion=pc)
    scene.set_calibration(brightness=1.0, power_per_m_W=1.0)
    Simulator(scene, max_rays=20000).run()
    irr = sensor.compute_irradiance()
    assert len(irr) == 10
    assert all(v >= 0.0 and math.isfinite(v) for v in irr)
    assert any(v > 0.0 for v in irr), "expected some illuminated pixels"


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
        test_physical_scene_is_scene,
        test_projection_base_not_implemented,
        test_cylindrical_projection_to_irradiance,
        test_cylindrical_projection_to_power_per_m,
        test_cylindrical_projection_roundtrip,
        test_cylindrical_bad_height_raises,
        test_point_source_projection_to_irradiance,
        test_point_source_projection_to_power_per_m,
        test_lambertian_projection_stub_raises,
        test_photoconversion_for_sensor_catalogue,
        test_photoconversion_unknown_model_raises,
        test_photoconversion_default_projection_cylindrical,
        test_compute_irradiance_values,
        test_compute_irradiance_needs_physical_scene,
        test_compute_irradiance_needs_calibration,
        test_compute_vout_deferred,
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
