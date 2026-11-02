"""
Python-specific module: test targeted resimulation
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
TARGETED RE-SIMULATION TESTS
===============================================================================
Tests analysis.targeted_resimulation (targeted_source_for_path /
run_targeted_resimulation) against a real bidirectional trace on the same
glass-slab fixture test_bidirectional.py uses.

  - test_targeted_source_matches_original_direction   p1/p2 reproduce the
                                                       identified path's own
                                                       forward root exactly
  - test_targeted_source_narrower_than_original        emis_angle = 2 *
                                                       cone_half_angle_deg
  - test_targeted_source_validates_inputs              empty path_uuids /
                                                       non-root first uuid /
                                                       non-positive cone
                                                       angle all raise
  - test_isolated_resimulation_reproduces_the_class    high-density re-run
                                                       stays inside the cone
  - test_isolated_run_does_not_mutate_original_scene    scene/source state
                                                       restored, including
                                                       when the run raises

Run with:
    python developer_tests/test_targeted_resimulation.py
Or with pytest:
    pytest developer_tests/test_targeted_resimulation.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.analysis.bidirectional import extract_ranked_paths
from ray_tracing_shapely.analysis.targeted_resimulation import (
    targeted_source_for_path,
    run_targeted_resimulation,
)


# ---------------------------------------------------------------------------
# Scene builder: same glass-slab fixture as test_bidirectional.py
# ---------------------------------------------------------------------------

def _build_scene():
    scene = Scene()
    scene.ray_density = 20
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3

    glass = Glass(scene, {
        'path': [
            {'x': -50, 'y': 0, 'arc': False},
            {'x': 50, 'y': 0, 'arc': False},
            {'x': 50, 'y': -40, 'arc': False},
            {'x': -50, 'y': -40, 'arc': False},
        ],
        'refIndex': 1.5,
    })
    glass.name = 'slab'
    scene.add_object(glass)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 30}
    source.p2 = {'x': 0, 'y': 29}
    source.emis_angle = 40
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    det = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': -30, 'y': -60},
        'p2': {'x': 30, 'y': -60},
        'irrad_map': True,
        'bin_size': 2.0,
    })
    det.name = 'det'
    scene.add_object(det)
    return scene, source, det


def _run_bidirectional(scene, det, **kwargs):
    sim = Simulator(scene, max_rays=40000, record_surface_hits=True)
    params = dict(acceptance_angle_deg=30, origin_samples=15, direction_samples=11,
                  spatial_tolerance=0.5, angular_tolerance_deg=2.0)
    params.update(kwargs)
    result = sim.run_bidirectional(det, **params)
    return sim, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_targeted_source_matches_original_direction():
    """The narrow source's p1/p2 exactly reproduce the identified path's own
    forward root -- same origin, same reference direction -- and are copies,
    not aliases, of the traced Ray's own dicts."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    assert paths, "expected at least one source->detector path"
    path = paths[0]

    root_ray = result.forward_lineage.get_segment(path['path_uuids'][0])
    targeted = targeted_source_for_path(path, result, source)

    assert targeted.p1 == root_ray.p1
    assert targeted.p2 == root_ray.p2
    assert targeted.p1 is not root_ray.p1
    assert targeted.p2 is not root_ray.p2

    targeted.p1['x'] += 1.0
    assert root_ray.p1['x'] != targeted.p1['x'], "must not alias the traced ray's own dict"
    print("  PASS: targeted source's p1/p2 exactly reproduce the path's forward root")
    return True


def test_targeted_source_narrower_than_original():
    """emis_angle is 2 * cone_half_angle_deg, strictly narrower than the
    original source's fan; brightness/wavelength carried over by default."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    path = paths[0]

    targeted = targeted_source_for_path(path, result, source, cone_half_angle_deg=1.5)
    assert targeted.emis_angle == 3.0
    assert targeted.emis_angle < source.emis_angle
    assert targeted.symmetric is True
    assert targeted.brightness == source.brightness
    assert targeted.wavelength == source.wavelength

    overridden = targeted_source_for_path(path, result, source, brightness=0.2)
    assert overridden.brightness == 0.2
    print(f"  PASS: emis_angle={targeted.emis_angle} < original {source.emis_angle}")
    return True


def test_targeted_source_validates_inputs():
    """Empty path_uuids, a non-root first uuid, and a non-positive
    cone_half_angle_deg all raise ValueError instead of building a
    nonsensical source."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    path = paths[0]

    try:
        targeted_source_for_path({'path_uuids': []}, result, source)
        raise AssertionError("expected ValueError for empty path_uuids")
    except ValueError:
        pass

    if len(path['path_uuids']) > 1:
        try:
            targeted_source_for_path(
                {'path_uuids': path['path_uuids'][1:]}, result, source,
            )
            raise AssertionError("expected ValueError for a non-root first uuid")
        except ValueError:
            pass

    try:
        targeted_source_for_path(path, result, source, cone_half_angle_deg=0.0)
        raise AssertionError("expected ValueError for cone_half_angle_deg=0")
    except ValueError:
        pass

    print("  PASS: empty path_uuids / non-root uuid / non-positive cone all raise")
    return True


def test_isolated_resimulation_reproduces_the_class():
    """Running the targeted source at high density (with adaptive sampling
    relaxed via min_brightness_exp) traces real segments, all of whose
    forward roots sit inside the requested cone around the original path's
    own forward-root direction."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    path = paths[0]

    cone_half_angle_deg = 0.5
    targeted = targeted_source_for_path(
        path, result, source, cone_half_angle_deg=cone_half_angle_deg,
    )
    isolated = run_targeted_resimulation(
        scene, source, targeted,
        max_rays=40000, record_surface_hits=True, min_brightness_exp=6,
        name="isolated",
    )
    assert len(isolated.segments) > 0, "expected the isolated run to trace some rays"

    root_ray = result.forward_lineage.get_segment(path['path_uuids'][0])
    root_angle = math.atan2(root_ray.p2['y'] - root_ray.p1['y'],
                            root_ray.p2['x'] - root_ray.p1['x'])

    checked = 0
    for seg in isolated.segments:
        if seg.parent_uuid is not None:
            continue  # only the newly-emitted roots of THIS run
        seg_angle = math.atan2(seg.p2['y'] - seg.p1['y'], seg.p2['x'] - seg.p1['x'])
        delta_deg = abs(math.degrees(seg_angle - root_angle))
        delta_deg = min(delta_deg, 360.0 - delta_deg)
        assert delta_deg <= cone_half_angle_deg + 1e-6, (
            f"root ray at {delta_deg:.4f} deg outside the {cone_half_angle_deg} deg cone"
        )
        checked += 1
    assert checked > 0, "expected at least one root segment from the isolated run"
    print(f"  PASS: {len(isolated.segments)} segments, {checked} roots all inside "
          f"the {cone_half_angle_deg} deg cone")
    return True


def test_ray_density_override_increases_samples_and_is_restored():
    """A narrower cone at the SAME ray_density would trace FEWER root rays
    (fan_width_rad / angular_step shrinks); ray_density must be boosted to
    actually concentrate more samples into the cone -- and scene.ray_density
    is restored after, like min_brightness_exp."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    path = paths[0]

    density_before = scene.ray_density
    targeted = targeted_source_for_path(path, result, source, cone_half_angle_deg=0.5)

    baseline = run_targeted_resimulation(
        scene, source, targeted, max_rays=200_000, min_brightness_exp=6,
    )
    boosted = run_targeted_resimulation(
        scene, source, targeted, max_rays=200_000, min_brightness_exp=6,
        ray_density=density_before * 20,
    )
    assert scene.ray_density == density_before, "ray_density must be restored after the call"

    n_roots_baseline = sum(1 for s in baseline.segments if s.parent_uuid is None)
    n_roots_boosted = sum(1 for s in boosted.segments if s.parent_uuid is None)
    assert n_roots_boosted > n_roots_baseline * 5, (
        f"expected ray_density=20x to produce far more root rays: "
        f"baseline={n_roots_baseline}, boosted={n_roots_boosted}"
    )
    print(f"  PASS: root rays baseline={n_roots_baseline} -> boosted={n_roots_boosted} "
          f"(ray_density restored to {scene.ray_density})")
    return True


def test_isolated_run_does_not_mutate_original_scene():
    """scene.objs/optical_objs/min_brightness_exp are restored exactly on
    success, AND when the simulation itself raises (a genuine try/finally
    regression, not just a happy-path check)."""
    scene, source, det = _build_scene()
    sim, result = _run_bidirectional(scene, det)
    paths = extract_ranked_paths(result.combined, top_n=5)
    path = paths[0]

    objs_before = list(scene.objs)
    optical_before = list(scene.optical_objs)
    threshold_before = scene.min_brightness_exp

    targeted = targeted_source_for_path(path, result, source, cone_half_angle_deg=0.5)
    run_targeted_resimulation(scene, source, targeted, max_rays=5000, min_brightness_exp=6)

    assert scene.objs == objs_before
    assert scene.optical_objs == optical_before
    assert scene.min_brightness_exp == threshold_before
    assert source in scene.objs and source in scene.optical_objs

    # Now force the simulation itself to raise, and confirm restoration still
    # happens (the whole point of the try/finally in run_targeted_resimulation).
    import ray_tracing_shapely.core.simulator as sim_module

    class _BoomSimulator:
        def __init__(self, *args, **kwargs):
            pass

        def run_with_result(self, name=None):
            raise RuntimeError("boom")

    real_simulator_cls = sim_module.Simulator
    sim_module.Simulator = _BoomSimulator
    try:
        try:
            run_targeted_resimulation(scene, source, targeted, min_brightness_exp=6)
            raise AssertionError("expected RuntimeError from the patched Simulator")
        except RuntimeError as e:
            assert str(e) == "boom"
    finally:
        sim_module.Simulator = real_simulator_cls

    assert scene.objs == objs_before
    assert scene.optical_objs == optical_before
    assert scene.min_brightness_exp == threshold_before
    print("  PASS: scene state restored on success and on a raise from inside the run")
    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_targeted_source_matches_original_direction,
        test_targeted_source_narrower_than_original,
        test_targeted_source_validates_inputs,
        test_isolated_resimulation_reproduces_the_class,
        test_ray_density_override_increases_samples_and_is_restored,
        test_isolated_run_does_not_mutate_original_scene,
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
        print("\nAll targeted re-simulation tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
