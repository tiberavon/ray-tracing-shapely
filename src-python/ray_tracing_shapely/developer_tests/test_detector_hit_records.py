"""
===============================================================================
DETECTOR HIT RECORDS — Lineage backtracing Step A verification
===============================================================================

Verifies that a Detector (and, by composition, a LinearSensor) records which
ray-lineage uuid crossed which bin, so that post-hoc analysis can link detector
signal back to optical paths.

Covered:

1. Bare Detector
   - A ray crossing the detector produces exactly one hit record.
   - The recorded ray_uuid matches a segment uuid in the simulator lineage.
   - get_hit_uuids() returns that uuid; get_bin_uuids() locates it by bin.
   - hit_records reset on re-run.

2. Detector-path lineage analysis
   - rank_paths_by_energy(lineage, leaf_uuids=detector.get_hit_uuids())
     returns the path(s) that actually reached the detector.

3. LinearSensor
   - hit_uuids is non-empty after a ray crosses the active area.
   - pixel_hit_uuids places the uuid in the expected pixel, honouring the
     count_pixels_from_p1 convention.

Run with:
    python developer_tests/test_detector_hit_records.py

Or with pytest:
    pytest developer_tests/test_detector_hit_records.py -v
===============================================================================
"""

import sys
from pathlib import Path

# Allow running as a script or with pytest
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.sensors.linear_sensor import LinearSensor
from ray_tracing_shapely.analysis.lineage_analysis import rank_paths_by_energy


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------

def _horizontal_ray(scene: Scene) -> SingleRay:
    """A single ray from (100, 80) travelling in +x."""
    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 100, 'y': 80}
    ray_src.p2 = {'x': 250, 'y': 80}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)
    return ray_src


def _run(scene: Scene):
    sim = Simulator(scene)
    segments = sim.run()
    return sim, segments


# ---------------------------------------------------------------------------
# 1. Bare Detector
# ---------------------------------------------------------------------------

def test_detector_records_single_hit():
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'irrad_map': True,
        'bin_size': 10.0,
    })
    scene.add_object(detector)

    sim, _ = _run(scene)

    records = detector.get_hit_records()
    assert len(records) == 1, f"expected 1 hit record, got {len(records)}"

    rec = records[0]
    assert rec['ray_uuid'] is not None
    # Ray crosses at (200, 80); bin = 80 / 10 = 8
    assert rec['bin_index'] == 8, f"expected bin 8, got {rec['bin_index']}"
    assert abs(rec['position'] - 80.0) < 1e-9
    assert rec['brightness_total'] > 0.0


def test_hit_uuid_resolves_in_lineage():
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'irrad_map': True,
        'bin_size': 10.0,
    })
    scene.add_object(detector)

    sim, _ = _run(scene)

    hit_uuids = detector.get_hit_uuids()
    assert len(hit_uuids) == 1
    # The recorded uuid must be a real segment in the lineage tree.
    assert sim.lineage.get_segment(hit_uuids[0]) is not None
    # And locatable by bin.
    assert hit_uuids[0] in detector.get_bin_uuids(8)


def test_hit_records_reset_on_rerun():
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'irrad_map': True,
        'bin_size': 10.0,
    })
    scene.add_object(detector)

    sim = Simulator(scene)
    sim.run()
    assert len(detector.get_hit_records()) == 1
    sim.run()
    assert len(detector.get_hit_records()) == 1, "records must reset each run"


# ---------------------------------------------------------------------------
# 2. Detector-path lineage analysis
# ---------------------------------------------------------------------------

def test_rank_paths_by_detector_leaves():
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'irrad_map': True,
        'bin_size': 10.0,
    })
    scene.add_object(detector)

    sim, _ = _run(scene)

    ranked = rank_paths_by_energy(sim.lineage, leaf_uuids=detector.get_hit_uuids())
    assert len(ranked) == 1
    # The incident ray is the source segment itself (no optics in between).
    assert ranked[0]['path_types'][0] == 'source'
    assert ranked[0]['energy'] > 0.0


# ---------------------------------------------------------------------------
# 3. LinearSensor
# ---------------------------------------------------------------------------

def test_linear_sensor_pixel_hit_uuids():
    scene = Scene()
    _horizontal_ray(scene)
    # Vertical active area from y=70..90, 4 pixels of pitch 5; ray at y=80.
    sensor = LinearSensor(
        scene,
        p1={'x': 200, 'y': 70},
        p2={'x': 200, 'y': 90},
        n_pixels=4,
        pixel_pitch=5.0,
        use_edge_blockers=False,
    )

    _run(scene)

    hit_uuids = sensor.hit_uuids
    assert len(hit_uuids) == 1, f"expected 1 sensor hit, got {len(hit_uuids)}"

    per_pixel = sensor.pixel_hit_uuids
    assert len(per_pixel) == 4
    # Ray crosses at y=80 → dist 10 from p1 → bin 2 → pixel 2.
    assert per_pixel[2] == hit_uuids
    assert all(per_pixel[p] == [] for p in (0, 1, 3))


def test_linear_sensor_pixel_hit_uuids_reversed():
    scene = Scene()
    _horizontal_ray(scene)
    sensor = LinearSensor(
        scene,
        p1={'x': 200, 'y': 70},
        p2={'x': 200, 'y': 90},
        n_pixels=4,
        pixel_pitch=5.0,
        count_pixels_from_p1=False,
        use_edge_blockers=False,
    )

    _run(scene)

    per_pixel = sensor.pixel_hit_uuids
    # bin 2 reversed over 4 pixels → pixel 4-1-2 = 1.
    assert per_pixel[1] == sensor.hit_uuids
    assert all(per_pixel[p] == [] for p in (0, 2, 3))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_detector_records_single_hit,
        test_hit_uuid_resolves_in_lineage,
        test_hit_records_reset_on_rerun,
        test_rank_paths_by_detector_leaves,
        test_linear_sensor_pixel_hit_uuids,
        test_linear_sensor_pixel_hit_uuids_reversed,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors
            failures += 1
            print(f"  ERROR {test.__name__}: {exc!r}")

    if failures:
        print(f"\n{failures} test(s) failed.")
    else:
        print("\nAll detector hit-record tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
