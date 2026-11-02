"""
Python-specific module: test linear sensor
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
LINEAR SENSOR TESTS — Phase 1 Verification
===============================================================================

Tests for optical_elements.sensors.LinearSensor covering:

1. SIZE SPECIFICATION
   - pixel_pitch path
   - active_length path
   - Mutual-exclusion guard

2. ORIENTATION
   - p2 magnitude does not affect active area length

3. INTERNAL DETECTOR
   - bin_size == pixel_pitch
   - p1 == detector_start
   - active_length == n_pixels * pixel_pitch

4. EDGE BLOCKERS
   - use_edge_blockers=True adds exactly 2 Blockers to scene
   - use_edge_blockers=False adds no Blockers

5. from_center
   - Detector endpoints are symmetric around center_point projection
   - count_pixels_from_p1 flag

6. from_pixel_0
   - Centre of pixel 0 is at pixel_0_point projection
   - count_pixels_from_p1 flag

7. pixel_data / pixel_positions
   - None before simulation start
   - Length == n_pixels after simulation start
   - Reversed when count_pixels_from_p1=False
   - pixel_positions values

8. from_datasheet
   - S13131-1536 defaults
   - Delegates to from_center / from_pixel_0
   - Both placement helpers raises ValueError
   - Unknown model raises ValueError

9. compute_vout stub raises NotImplementedError

Run with:
    python developer_tests/test_linear_sensor.py

Or with pytest:
    pytest developer_tests/test_linear_sensor.py -v
===============================================================================
"""

import sys
import math
from pathlib import Path

# Allow running as a script or with pytest
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.optical_elements.sensors.linear_sensor import LinearSensor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_scene() -> Scene:
    return Scene()


def vertical_sensor(scene, n=10, pitch=1.0, **kwargs) -> LinearSensor:
    """Sensor running vertically (p1→p2 = upward) with p1 at origin."""
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    return LinearSensor(scene, p1, p2, n, pixel_pitch=pitch, **kwargs)


# ---------------------------------------------------------------------------
# 1. Size specification
# ---------------------------------------------------------------------------

def test_from_pixel_pitch():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=10, pitch=2.0)
    assert sensor.n_pixels == 10
    assert math.isclose(sensor.pixel_pitch, 2.0)
    assert math.isclose(sensor.active_length, 20.0)


def test_from_active_length():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor(scene, p1, p2, n_pixels=5, active_length=10.0)
    assert math.isclose(sensor.pixel_pitch, 2.0)
    assert math.isclose(sensor.active_length, 10.0)


def test_both_size_args_raises():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    try:
        LinearSensor(scene, p1, p2, n_pixels=5, pixel_pitch=1.0, active_length=5.0)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_no_size_arg_raises():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    try:
        LinearSensor(scene, p1, p2, n_pixels=5)
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# 2. Orientation — p2 magnitude does not affect active area
# ---------------------------------------------------------------------------

def test_p2_direction_only():
    scene1 = make_scene()
    scene2 = make_scene()
    p1 = {'x': 5.0, 'y': 3.0}
    p2_short = {'x': 5.0, 'y': 4.0}    # magnitude 1
    p2_long  = {'x': 5.0, 'y': 100.0}  # magnitude 97

    s1 = LinearSensor(scene1, p1, p2_short, n_pixels=4, pixel_pitch=1.0,
                      use_edge_blockers=False)
    s2 = LinearSensor(scene2, p1, p2_long, n_pixels=4, pixel_pitch=1.0,
                      use_edge_blockers=False)

    assert math.isclose(s1.active_length, s2.active_length)
    assert math.isclose(s1.detector.p2['y'], s2.detector.p2['y'])


# ---------------------------------------------------------------------------
# 3. Internal Detector
# ---------------------------------------------------------------------------

def test_detector_bin_size():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=8, pitch=0.5)
    assert math.isclose(sensor.detector.bin_size, 0.5)


def test_detector_p1_equals_active_start():
    scene = make_scene()
    p1 = {'x': 3.0, 'y': 7.0}
    p2 = {'x': 3.0, 'y': 8.0}
    sensor = LinearSensor(scene, p1, p2, n_pixels=5, pixel_pitch=1.0,
                          use_edge_blockers=False)
    det = sensor.detector
    assert math.isclose(det.p1['x'], p1['x'])
    assert math.isclose(det.p1['y'], p1['y'])


def test_detector_active_length():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=12, pitch=0.25)
    det = sensor.detector
    det_len = math.sqrt(
        (det.p2['x'] - det.p1['x']) ** 2
        + (det.p2['y'] - det.p1['y']) ** 2
    )
    assert math.isclose(det_len, 12 * 0.25)


# ---------------------------------------------------------------------------
# 4. Edge Blockers
# ---------------------------------------------------------------------------

def test_edge_blockers_added():
    scene = make_scene()
    vertical_sensor(scene, n=4, pitch=1.0, use_edge_blockers=True)
    blockers = [o for o in scene.objs if isinstance(o, Blocker)]
    assert len(blockers) == 2


def test_no_edge_blockers():
    scene = make_scene()
    vertical_sensor(scene, n=4, pitch=1.0, use_edge_blockers=False)
    blockers = [o for o in scene.objs if isinstance(o, Blocker)]
    assert len(blockers) == 0


def test_edge_blockers_collinear():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=4, pitch=1.0, use_edge_blockers=True)
    det = sensor.detector
    blockers = [o for o in scene.objs if isinstance(o, Blocker)]

    # Both blockers share x-coordinate with the detector (vertical axis)
    for blk in blockers:
        assert math.isclose(blk.p1['x'], det.p1['x'], abs_tol=1e-9)
        assert math.isclose(blk.p2['x'], det.p1['x'], abs_tol=1e-9)


# ---------------------------------------------------------------------------
# 5. from_center
# ---------------------------------------------------------------------------

def test_from_center_active_area_symmetric():
    scene = make_scene()
    center = {'x': 0.0, 'y': 10.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_center(
        scene, p1, p2, center, n_pixels=10, pixel_pitch=1.0,
        use_edge_blockers=False
    )
    det = sensor.detector
    mid_y = 0.5 * (det.p1['y'] + det.p2['y'])
    assert math.isclose(mid_y, center['y'])


def test_from_center_count_from_p1_true():
    scene = make_scene()
    center = {'x': 0.0, 'y': 10.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_center(
        scene, p1, p2, center, n_pixels=10, pixel_pitch=1.0,
        count_pixels_from_p1=True, use_edge_blockers=False
    )
    sensor.detector.on_simulation_start()
    assert sensor.pixel_data == sensor.detector.bin_data


def test_from_center_count_from_p1_false():
    scene = make_scene()
    center = {'x': 0.0, 'y': 10.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_center(
        scene, p1, p2, center, n_pixels=6, pixel_pitch=1.0,
        count_pixels_from_p1=False, use_edge_blockers=False
    )
    sensor.detector.on_simulation_start()
    assert sensor.pixel_data == list(reversed(sensor.detector.bin_data))


# ---------------------------------------------------------------------------
# 6. from_pixel_0
# ---------------------------------------------------------------------------

def test_from_pixel_0_centre_position_from_p1_true():
    scene = make_scene()
    px0 = {'x': 0.0, 'y': 5.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_pixel_0(
        scene, p1, p2, px0, n_pixels=10, pixel_pitch=1.0,
        count_pixels_from_p1=True, use_edge_blockers=False
    )
    det = sensor.detector
    # Centre of pixel 0 (first bin in det) = p1 + 0.5 * pitch
    px0_centre = det.p1['y'] + 0.5 * sensor.pixel_pitch
    assert math.isclose(px0_centre, px0['y'])


def test_from_pixel_0_centre_position_from_p1_false():
    scene = make_scene()
    px0 = {'x': 0.0, 'y': 5.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_pixel_0(
        scene, p1, p2, px0, n_pixels=10, pixel_pitch=1.0,
        count_pixels_from_p1=False, use_edge_blockers=False
    )
    det = sensor.detector
    # Centre of last bin (pixel 0 with reversed data) = p2 - 0.5 * pitch
    px0_centre = det.p2['y'] - 0.5 * sensor.pixel_pitch
    assert math.isclose(px0_centre, px0['y'])


def test_from_pixel_0_count_from_p1_false_reversal():
    scene = make_scene()
    px0 = {'x': 0.0, 'y': 5.0}
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_pixel_0(
        scene, p1, p2, px0, n_pixels=8, pixel_pitch=1.0,
        count_pixels_from_p1=False, use_edge_blockers=False
    )
    sensor.detector.on_simulation_start()
    assert sensor.pixel_data == list(reversed(sensor.detector.bin_data))


# ---------------------------------------------------------------------------
# 7. pixel_data / pixel_positions
# ---------------------------------------------------------------------------

def test_pixel_data_none_before_simulation():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=5, pitch=1.0)
    assert sensor.pixel_data is None


def test_pixel_data_length_after_simulation_start():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=7, pitch=1.0)
    sensor.detector.on_simulation_start()
    assert len(sensor.pixel_data) == 7


def test_pixel_positions_length():
    scene = make_scene()
    sensor = vertical_sensor(scene, n=6, pitch=2.0)
    assert len(sensor.pixel_positions) == 6


def test_pixel_positions_first_and_last():
    scene = make_scene()
    n, pitch = 8, 0.5
    sensor = vertical_sensor(scene, n=n, pitch=pitch)
    positions = sensor.pixel_positions
    assert math.isclose(positions[0], pitch / 2)
    assert math.isclose(positions[-1], n * pitch - pitch / 2)


# ---------------------------------------------------------------------------
# 8. from_datasheet
# ---------------------------------------------------------------------------

def test_from_datasheet_s13131_defaults():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    sensor = LinearSensor.from_datasheet(scene, 'S13131-1536', p1, p2)
    assert sensor.n_pixels == 1536
    assert math.isclose(sensor.pixel_pitch, 0.0055)


def test_from_datasheet_center():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    center = {'x': 0.0, 'y': 5.0}
    sensor = LinearSensor.from_datasheet(
        scene, 'S13131-1536', p1, p2, center_point=center
    )
    det = sensor.detector
    mid_y = 0.5 * (det.p1['y'] + det.p2['y'])
    assert math.isclose(mid_y, center['y'])


def test_from_datasheet_pixel_0():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    px0 = {'x': 0.0, 'y': 2.0}
    sensor = LinearSensor.from_datasheet(
        scene, 'S13131-1536', p1, p2, pixel_0_point=px0,
        count_pixels_from_p1=True
    )
    det = sensor.detector
    px0_centre = det.p1['y'] + 0.5 * sensor.pixel_pitch
    assert math.isclose(px0_centre, px0['y'])


def test_from_datasheet_both_raises():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    try:
        LinearSensor.from_datasheet(
            scene, 'S13131-1536', p1, p2,
            center_point={'x': 0.0, 'y': 5.0},
            pixel_0_point={'x': 0.0, 'y': 2.0},
        )
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_from_datasheet_unknown_model_raises():
    scene = make_scene()
    p1 = {'x': 0.0, 'y': 0.0}
    p2 = {'x': 0.0, 'y': 1.0}
    try:
        LinearSensor.from_datasheet(scene, 'XYZ-9999', p1, p2)
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# 9. compute_vout stub
# ---------------------------------------------------------------------------

def test_compute_vout_requires_photoconversion():
    """Without a Photoconversion attached, compute_vout raises PhysicsContextError.

    (compute_vout's photometric step is deferred; a sensor built with no
    photoconversion fails the structural guard first. See test_physical_scene.py
    for the full photometry contract.)
    """
    from ray_tracing_shapely.optical_elements.physics.exceptions import PhysicsContextError
    scene = make_scene()
    sensor = vertical_sensor(scene, n=5, pitch=1.0)
    try:
        sensor.compute_vout()
        assert False, "Expected PhysicsContextError"
    except PhysicsContextError:
        pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = 0
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} tests")
    return failed


if __name__ == '__main__':
    sys.exit(_run_all())
