"""
===============================================================================
SURFACE HIT RECORDS -- Lineage backtracing Step B verification
===============================================================================

Verifies that, when a Simulator runs with record_surface_hits=True, each ray
segment that terminated on a surface carries the geometry of that interaction:
hit_surface_uuid, hit_point, hit_normal (unit), and incident_angle (radians,
[0, pi/2]). With the flag off (the default) every field stays None.

Covered (mirrors dev_doc/roadmap/proposed/ray_lineage_step_b_surface_hit_records.md):

Core (Python API)
  - test_flag_off_leaves_fields_none
  - test_glass_hit_point_matches_segment_p2
  - test_glass_incident_angle_known_geometry     (0deg / 30deg / 45deg)
  - test_hit_normal_is_unit
  - test_mirror_hit_records
  - test_children_have_no_hit_data
  - test_tir_segment_incident_angle_exceeds_critical
  - test_backward_compatible_when_flag_off

Agentic exposure
  - test_db_has_incidence_columns                (B-agentic.1)
  - test_paths_by_incidence_angle_tool           (B-agentic.2)

Run with:
    python developer_tests/test_surface_hit_records.py

Or with pytest:
    pytest developer_tests/test_surface_hit_records.py -v
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
from ray_tracing_shapely.core.ray import Ray
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    query_rays,
    paths_by_incidence_angle,
)


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------

N_GLASS = 1.5


def _glass_slab(scene: Scene) -> Glass:
    """A horizontal glass slab: top face at y=0, bottom at y=-100, x wide.

    The top/bottom faces are horizontal so their surface normal is vertical --
    a ray incident at `angle` from the vertical hits the top face at exactly
    `angle` angle of incidence.
    """
    glass = Glass(scene, {
        'path': [
            {'x': -1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': -100, 'arc': False},
            {'x': -1000, 'y': -100, 'arc': False},
        ],
        'refIndex': N_GLASS,
    })
    scene.add_object(glass)
    return glass


def _ray_from_above(angle_deg: float, x0: float = 0.0) -> Ray:
    """A ray descending onto the slab's top face at `angle_deg` from the normal."""
    a = math.radians(angle_deg)
    return Ray(
        p1={'x': x0, 'y': 100},
        p2={'x': x0 + math.sin(a), 'y': 100 - math.cos(a)},
        brightness_s=0.5,
        brightness_p=0.5,
    )


def _run(scene: Scene, ray: Ray, record: bool):
    sim = Simulator(scene, max_rays=40, record_surface_hits=record)
    sim.add_ray(ray)
    segments = sim.run()
    return sim, segments


# ---------------------------------------------------------------------------
# Core: flag semantics
# ---------------------------------------------------------------------------

def test_flag_off_leaves_fields_none():
    scene = Scene()
    _glass_slab(scene)
    _, segments = _run(scene, _ray_from_above(45.0), record=False)
    assert segments, "expected some segments"
    for s in segments:
        assert s.hit_surface_uuid is None
        assert s.hit_point is None
        assert s.hit_normal is None
        assert s.incident_angle is None


def test_backward_compatible_when_flag_off():
    """Default Simulator() (no flag) behaves exactly as before."""
    scene = Scene()
    _glass_slab(scene)
    sim = Simulator(scene)  # no record_surface_hits kwarg at all
    sim.add_ray(_ray_from_above(30.0))
    segments = sim.run()
    assert sim.record_surface_hits is False
    assert all(s.incident_angle is None for s in segments)


# ---------------------------------------------------------------------------
# Core: glass
# ---------------------------------------------------------------------------

def test_glass_hit_point_matches_segment_p2():
    scene = Scene()
    _glass_slab(scene)
    _, segments = _run(scene, _ray_from_above(45.0), record=True)
    recorded = [s for s in segments if s.hit_point is not None]
    assert recorded, "expected at least one recorded hit"
    for s in recorded:
        d = math.hypot(s.p2['x'] - s.hit_point['x'], s.p2['y'] - s.hit_point['y'])
        assert d < 1e-9, f"hit_point should equal truncated p2, dist={d}"


def test_glass_incident_angle_known_geometry():
    # Normal incidence -> 0 deg; the first (source) hit is the entry face.
    for input_deg, expected_deg in ((0.0, 0.0), (30.0, 30.0), (45.0, 45.0)):
        scene = Scene()
        _glass_slab(scene)
        _, segments = _run(scene, _ray_from_above(input_deg), record=True)
        source_hit = next(s for s in segments if s.interaction_type == 'source'
                          and s.incident_angle is not None)
        got = math.degrees(source_hit.incident_angle)
        assert abs(got - expected_deg) < 1e-6, (
            f"input {input_deg}deg: expected {expected_deg}, got {got}"
        )


def test_hit_normal_is_unit():
    scene = Scene()
    _glass_slab(scene)
    _, segments = _run(scene, _ray_from_above(30.0), record=True)
    recorded = [s for s in segments if s.hit_normal is not None]
    assert recorded
    for s in recorded:
        mag = math.hypot(s.hit_normal['x'], s.hit_normal['y'])
        assert abs(mag - 1.0) < 1e-9, f"normal not unit: |n|={mag}"


def test_children_have_no_hit_data():
    """A freshly spawned child segment carries no hit data until it hits."""
    scene = Scene()
    _glass_slab(scene)
    _, segments = _run(scene, _ray_from_above(45.0), record=True)
    # The final refracted segment leaves the scene and never hits a surface,
    # so at least one non-source segment must have no hit record.
    unrecorded = [s for s in segments if s.incident_angle is None]
    assert unrecorded, "expected at least one segment that never hit a surface"
    # None of those may have a stray hit_surface_uuid / hit_point.
    for s in unrecorded:
        assert s.hit_surface_uuid is None
        assert s.hit_point is None


# ---------------------------------------------------------------------------
# Core: mirror
# ---------------------------------------------------------------------------

def test_mirror_hit_records():
    """Horizontal ray onto a vertical mirror -> normal incidence, normal (+/-1, 0)."""
    scene = Scene()
    mirror = Mirror(scene, {
        'p1': {'x': 200, 'y': 150},
        'p2': {'x': 200, 'y': 250},
        'filter': False,
    })
    scene.add_object(mirror)
    ray = Ray(p1={'x': 150, 'y': 200}, p2={'x': 250, 'y': 200},
              brightness_s=1.0, brightness_p=0.0)
    _, segments = _run(scene, ray, record=True)

    hits = [s for s in segments if s.incident_angle is not None]
    assert len(hits) == 1, f"expected 1 mirror hit, got {len(hits)}"
    s = hits[0]
    assert abs(math.degrees(s.incident_angle)) < 1e-9, "normal incidence expected"
    assert abs(s.hit_point['x'] - 200.0) < 1e-9
    assert abs(abs(s.hit_normal['x']) - 1.0) < 1e-9
    assert abs(s.hit_normal['y']) < 1e-9
    assert s.hit_surface_uuid == mirror.uuid


# ---------------------------------------------------------------------------
# Core: TIR
# ---------------------------------------------------------------------------

def test_tir_segment_incident_angle_exceeds_critical():
    """A ray inside glass hitting a face above the critical angle records TIR."""
    critical_deg = math.degrees(math.asin(1.0 / N_GLASS))  # ~41.8 deg
    scene = Scene()
    _glass_slab(scene)
    # Start INSIDE the slab, travel up toward the top face at 60deg from normal.
    a = math.radians(60.0)
    ray = Ray(p1={'x': 0, 'y': -50},
              p2={'x': math.sin(a), 'y': -50 + math.cos(a)},
              brightness_s=0.5, brightness_p=0.5)
    _, segments = _run(scene, ray, record=True)

    tir_causers = [s for s in segments if s.caused_tir and s.incident_angle is not None]
    assert tir_causers, "expected at least one segment that caused TIR with a hit record"
    for s in tir_causers:
        assert math.degrees(s.incident_angle) > critical_deg, (
            f"TIR incidence {math.degrees(s.incident_angle):.2f} should exceed "
            f"critical {critical_deg:.2f}"
        )


# ---------------------------------------------------------------------------
# Agentic exposure (B-agentic.1 / .2)
# ---------------------------------------------------------------------------

def test_db_has_incidence_columns():
    scene = Scene()
    _glass_slab(scene)
    sim, segments = _run(scene, _ray_from_above(45.0), record=True)

    clear_context()
    set_context(scene, segments, lineage=sim.lineage)
    try:
        # New columns must exist and be selectable.
        res = query_rays(
            "SELECT uuid, incident_angle, hit_surface_uuid, "
            "hit_point_x, hit_point_y, hit_normal_x, hit_normal_y "
            "FROM rays WHERE incident_angle IS NOT NULL"
        )
        assert res['status'] == 'ok', f"query failed: {res}"
        assert res['data']['row_count'] >= 1, "expected recorded incidence rows"

        # degrees() over incident_angle works and is in a sane range.
        res2 = query_rays(
            "SELECT degrees(incident_angle) AS deg FROM rays "
            "WHERE incident_angle IS NOT NULL ORDER BY deg DESC"
        )
        assert res2['status'] == 'ok'
        top_deg = res2['data']['rows'][0][0]
        assert 0.0 <= top_deg <= 90.0 + 1e-9
    finally:
        clear_context()


def test_db_incidence_null_when_flag_off():
    scene = Scene()
    _glass_slab(scene)
    sim, segments = _run(scene, _ray_from_above(45.0), record=False)

    clear_context()
    set_context(scene, segments, lineage=sim.lineage)
    try:
        res = query_rays("SELECT COUNT(*) AS n FROM rays WHERE incident_angle IS NOT NULL")
        assert res['status'] == 'ok', f"query failed: {res}"
        assert res['data']['rows'][0][0] == 0, "flag off must leave incident_angle NULL"
    finally:
        clear_context()


def test_paths_by_incidence_angle_tool():
    scene = Scene()
    _glass_slab(scene)
    sim, segments = _run(scene, _ray_from_above(45.0), record=True)

    clear_context()
    set_context(scene, segments, lineage=sim.lineage)
    try:
        # The 45deg entry hit must fall in a 40..50 deg window.
        res = paths_by_incidence_angle(40.0, 50.0)
        assert res['status'] == 'ok', f"tool failed: {res}"
        assert len(res['data']) >= 1, "expected a segment near 45 deg"
        entry = res['data'][0]
        assert set(entry).issuperset({
            'uuid', 'interaction_type', 'incident_angle_deg', 'incident_angle_rad',
            'hit_surface_uuid', 'hit_point', 'brightness_s', 'brightness_p',
            'brightness_total',
        })
        assert 40.0 <= entry['incident_angle_deg'] <= 50.0

        # An empty window returns ok + empty list, not an error.
        res_empty = paths_by_incidence_angle(80.0, 89.0)
        assert res_empty['status'] == 'ok'
        assert res_empty['data'] == []

        # Unknown surface name -> structured error.
        res_bad = paths_by_incidence_angle(0.0, 90.0, surface_name='no_such_object')
        assert res_bad['status'] == 'error'
    finally:
        clear_context()


def test_paths_by_incidence_angle_requires_context():
    clear_context()
    res = paths_by_incidence_angle(0.0, 90.0)
    assert res['status'] == 'error', f"expected error with no context, got {res}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_flag_off_leaves_fields_none,
        test_backward_compatible_when_flag_off,
        test_glass_hit_point_matches_segment_p2,
        test_glass_incident_angle_known_geometry,
        test_hit_normal_is_unit,
        test_children_have_no_hit_data,
        test_mirror_hit_records,
        test_tir_segment_incident_angle_exceeds_critical,
        test_db_has_incidence_columns,
        test_db_incidence_null_when_flag_off,
        test_paths_by_incidence_angle_tool,
        test_paths_by_incidence_angle_requires_context,
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
        print("\nAll surface hit-record tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
