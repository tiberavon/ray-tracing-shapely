"""
Python-specific module: test detector hit records
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
   - Hit records carry 'wavelength' (None unless colour simulation is on)
     and 'incident_angle' (radians, relative to the detector's normal --
     C-HIT-01, dev_doc/architecture/contracts/C-HIT-01.md).

2. Detector-path lineage analysis
   - rank_paths_by_energy(lineage, leaf_uuids=detector.get_hit_uuids())
     returns the path(s) that actually reached the detector.

3. LinearSensor
   - hit_uuids is non-empty after a ray crosses the active area.
   - pixel_hit_uuids places the uuid in the expected pixel, honouring the
     count_pixels_from_p1 convention.

4. One-sided absorbing semantics (C-DET-01)
   - A detector absorbs (records/accumulates) crossings from its declared
     absorbing_side only, by default; the opposite side is a no-op.
   - absorbing_side can be flipped; two_sided=True restores the original
     signed-net-flux behaviour.
   - The RXI receiver-cavity acceptance-angle curve
   (dev_doc/architecture/components/analysis_bidirectional.md) stays non-negative with the
     new default, and is shown to go negative under two_sided=True --
     reproducing the documented anomaly and confirming the fix in the
     same test.

5. Optical path length (P-RAY-LINEAGE / analysis_lineage.md)
   - geometric_path_length/optical_path_length (analysis/lineage_analysis.py)
     reproduce hand-computed 150.0 / 175.0 through a refIndex=1.5 slab, each
     leg exactly 50 units at normal incidence (no bending to complicate the
     arithmetic).
   - medium_index defaults to 1.0 (air) everywhere when no glass is present,
     collapsing optical_path_length to geometric_path_length exactly.
   - Fresnel-reflected sibling rays at both the entry and exit interfaces
     keep the medium they were already in (base_glass.py's
     ray2.medium_index = ray.medium_index), checked directly, not just
     inferred from the transmitted path.

6. Beam.emis_angle guard (C-BEAM-01)
   - A negative emis_angle now raises ValueError from
     Beam.on_simulation_start() instead of silently flipping every emitted
     ray's brightness sign.

Run with:
    python developer_tests/test_detector_hit_records.py

Or with pytest:
    pytest developer_tests/test_detector_hit_records.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

# Allow running as a script or with pytest
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.sensors.linear_sensor import LinearSensor
from ray_tracing_shapely.analysis.lineage_analysis import (
    rank_paths_by_energy, geometric_path_length, optical_path_length,
)


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


def test_detector_never_terminates_ray():
    """C-CORE-02: a Detector crossing is never ray-terminating -- the ray's
    own propagation continues to its natural endpoint regardless of
    absorbing_side/two_sided. Checked both for an absorbed crossing (the
    common case) and a non-absorbed one (the C-DET-01 no-op case), since
    C-CORE-02's Guarantee is that propagation is unconditional either way.
    """
    for absorbing_side in (1, -1):  # 1: this ray's crossing is absorbed;
                                     # -1: it isn't (C-DET-01 no-op)
        scene = Scene()
        _horizontal_ray(scene)  # (100, 80) -> (250, 80)
        detector = Detector(scene, {
            'type': 'Detector',
            'p1': {'x': 200, 'y': 0},
            'p2': {'x': 200, 'y': 160},
            'absorbing_side': absorbing_side,
        })
        scene.add_object(detector)

        sim, segments = _run(scene)

        # The ray's own propagation is unconditional: two segments exist
        # (before and after the crossing), and the post-crossing one keeps
        # travelling undeflected in the same +x direction with no further
        # intersection (Simulator extends an unobstructed ray far past its
        # nominal endpoint, per _process_rays' intersection-testing
        # extension) -- a Detector is a straight pass-through, not an
        # absorber of the ray itself.
        assert len(segments) == 2, (
            f"absorbing_side={absorbing_side}: expected 2 segments "
            f"(pre-/post-crossing), got {len(segments)}"
        )
        post_crossing = [s for s in segments if s.parent_uuid is not None]
        assert len(post_crossing) == 1
        tail = post_crossing[0]
        assert abs(tail.p1['x'] - 200.0) < 1e-9 and abs(tail.p1['y'] - 80.0) < 1e-9
        assert tail.p2['x'] > 1000.0, (
            f"expected the post-crossing segment to keep travelling in +x "
            f"unobstructed, got p2={tail.p2}"
        )
        assert abs(tail.p2['y'] - 80.0) < 1e-9  # undeflected: still y=80


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


def test_wavelength_none_when_color_simulation_disabled():
    """Scene.simulate_colors defaults to False, so SingleRay never sets
    Ray.wavelength -- the hit record should carry None, not a stale
    default, per Ray.__init__'s own Optional[float] = None convention."""
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
    })
    scene.add_object(detector)

    _run(scene)

    rec = detector.get_hit_records()[0]
    assert rec['wavelength'] is None


def test_wavelength_recorded_when_color_simulation_enabled():
    scene = Scene()
    scene.simulate_colors = True
    ray_src = SingleRay(scene, {
        'type': 'SingleRay',
        'p1': {'x': 100, 'y': 80},
        'p2': {'x': 250, 'y': 80},
        'brightness': 1.0,
        'wavelength': 650.0,
    })
    scene.add_object(ray_src)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
    })
    scene.add_object(detector)

    _run(scene)

    rec = detector.get_hit_records()[0]
    assert rec['wavelength'] == 650.0


def test_incident_angle_at_normal_incidence():
    """The existing horizontal-ray / vertical-detector fixture hits the
    detector head-on (ray perpendicular to the detector line) -- incidence
    angle relative to the normal is 0."""
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
    })
    scene.add_object(detector)

    _run(scene)

    rec = detector.get_hit_records()[0]
    assert math.isclose(rec['incident_angle'], 0.0, abs_tol=1e-9)


def test_incident_angle_at_45_degrees():
    """A ray travelling at 45 deg to the horizontal, crossing a vertical
    detector, hits it at 45 deg to the detector's normal."""
    scene = Scene()
    ray_src = SingleRay(scene, {
        'type': 'SingleRay',
        'p1': {'x': 150, 'y': 80},
        'p2': {'x': 200, 'y': 130},  # dx=dy=50 -> 45 degrees
        'brightness': 1.0,
    })
    scene.add_object(ray_src)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
    })
    scene.add_object(detector)

    _run(scene)

    records = detector.get_hit_records()
    assert len(records) == 1
    assert math.isclose(records[0]['incident_angle'], math.pi / 4.0, rel_tol=1e-6)


def test_incident_angle_is_bounded():
    """Regardless of crossing direction, incident_angle must stay in the
    documented [0, pi/2] range (it is not signed, unlike 'sign'). Uses
    two_sided=True so a reversed-orientation detector still records the
    crossing -- C-DET-01's one-sided default would otherwise treat this
    orientation's crossing as coming from the non-absorbing side."""
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 160},  # reversed p1/p2 relative to other tests
        'p2': {'x': 200, 'y': 0},
        'two_sided': True,
    })
    scene.add_object(detector)

    _run(scene)

    rec = detector.get_hit_records()[0]
    assert 0.0 <= rec['incident_angle'] <= math.pi / 2.0 + 1e-9


# ---------------------------------------------------------------------------
# 4. One-sided absorbing semantics (C-DET-01)
# ---------------------------------------------------------------------------

def test_one_sided_absorption_is_default():
    """A crossing from the non-absorbing side is a complete no-op: no
    power, no hit record. absorbing_side defaults to +1."""
    scene = Scene()
    _horizontal_ray(scene)  # travels in +x, crosses the vertical detector
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
    })
    scene.add_object(detector)
    _run(scene)

    # This orientation/direction combination crosses with sign=+1 (see
    # test_incident_angle_at_normal_incidence's fixture) -- absorbed by
    # the default absorbing_side=1.
    assert len(detector.get_hit_records()) == 1
    assert detector.power > 0.0


def test_non_absorbing_side_is_a_complete_no_op():
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'absorbing_side': -1,  # flip: this ray's crossing (+1) is now the back
    })
    scene.add_object(detector)
    _run(scene)

    assert detector.get_hit_records() == []
    assert detector.power == 0.0
    assert detector.normal == 0.0
    assert detector.shear == 0.0


def test_absorbing_side_flip_recovers_the_hit():
    """Same physical ray; flipping absorbing_side to match its sign makes
    the detector see it again."""
    scene = Scene()
    _horizontal_ray(scene)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 160},  # reversed orientation -> sign flips
        'p2': {'x': 200, 'y': 0},
        'absorbing_side': -1,
    })
    scene.add_object(detector)
    _run(scene)

    assert len(detector.get_hit_records()) == 1
    assert detector.get_hit_records()[0]['sign'] == -1


def test_two_sided_restores_signed_net_flux():
    """With two_sided=True, both directions accumulate -- two counter-
    propagating rays of equal brightness cancel to zero net power, exactly
    the old behaviour C-DET-01's default is meant to stop being the default."""
    from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay as _SR

    scene = Scene()
    forward = _SR(scene, {'type': 'SingleRay', 'brightness': 1.0,
                           'p1': {'x': 100, 'y': 80}, 'p2': {'x': 250, 'y': 80}})
    backward = _SR(scene, {'type': 'SingleRay', 'brightness': 1.0,
                            'p1': {'x': 250, 'y': 100}, 'p2': {'x': 100, 'y': 100}})
    scene.add_object(forward)
    scene.add_object(backward)
    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'two_sided': True,
    })
    scene.add_object(detector)
    _run(scene)

    assert len(detector.get_hit_records()) == 2
    assert math.isclose(detector.power, 0.0, abs_tol=1e-9)


def test_rxi_receiver_acceptance_curve_matches_15_bidirectional_3_4():
    """The RXI receiver-cavity fixture from test_rxi.py's
    test_rxi_receiver_cavity_collects_light, swept over the beam's
    incidence angle. dev_doc/architecture/components/analysis_bidirectional.md: this exact geometry
    previously showed "non-monotonic,
    partially sign-negative Detector.power" because rays crossed the
    detector line in both directions at some angles. Confirms both halves
    of the fix: two_sided=True reproduces the documented anomaly (power
    goes negative somewhere in the sweep), and the new one-sided default
    does not (power stays >= 0 for every angle swept)."""
    from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    def _receiver_power(incidence_deg: float, two_sided: bool) -> float:
        scene = Scene()
        scene.ray_density = 10
        scene.min_brightness_exp = 3

        rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0,
                        s1_segments=16, mirror_band_deg=(-10.0, 10.0),
                        receiver_half_width=3.0)
        rxi.name = 'rxi'
        scene.add_object(rxi)

        # Sweep the angle of incidence by rotating the illuminating beam's
        # segment about its own midpoint -- NOT by setting a negative
        # `Beam.emis_angle`. `emis_angle` is a divergence half-angle
        # (UI-restricted to [0, 180], beam.py:131) with no negative-value
        # guard: a negative value drives beam.py:361's
        # `num_angled_rays = 1 + floor(half_angle / s) * 2` negative,
        # silently producing negative per-ray brightness (found while
        # writing this test -- see C-BEAM-01,
        # dev_doc/architecture/contracts/C-BEAM-01.md; a genuine, separate,
        # pre-existing Beam defect, out of scope here). Rotating the
        # segment instead tilts the beam's propagation direction (always
        # perpendicular to the segment) by the same angle and stays inside
        # Beam's actual contract.
        theta = math.radians(incidence_deg)
        half_len = 25.0
        cx, cy = 0.0, 15.0
        dx = half_len * math.cos(theta)
        dy = half_len * math.sin(theta)
        beam = Beam(scene)
        beam.p1 = {'x': cx - dx, 'y': cy - dy}
        beam.p2 = {'x': cx + dx, 'y': cy + dy}
        beam.emis_angle = 0.0
        beam.brightness = 1.0
        scene.add_object(beam)

        det = Detector(scene, {
            'type': 'Detector',
            'p1': {'x': -3.0, 'y': -46.0},
            'p2': {'x': 3.0, 'y': -46.0},
            'two_sided': two_sided,
        })
        scene.add_object(det)

        Simulator(scene, max_rays=8000).run()
        return det.power

    angles_deg = [-40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0]

    two_sided_powers = [_receiver_power(a, two_sided=True) for a in angles_deg]
    one_sided_powers = [_receiver_power(a, two_sided=False) for a in angles_deg]

    assert any(p < 0.0 for p in two_sided_powers), (
        "expected the documented anomaly (a negative net power somewhere in "
        f"the sweep) under two_sided=True; got {two_sided_powers}"
    )
    assert all(p >= 0.0 for p in one_sided_powers), (
        f"one-sided (default) power must never go negative; got {one_sided_powers}"
    )


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
# 5. Optical path length (P-RAY-LINEAGE / analysis_lineage.md)
# ---------------------------------------------------------------------------

def test_geometric_and_optical_path_length_through_glass_slab():
    scene = Scene()
    ray_src = SingleRay(scene, {'type': 'SingleRay', 'brightness': 1.0,
                                 'p1': {'x': 0, 'y': 100}, 'p2': {'x': 0, 'y': 90}})
    scene.add_object(ray_src)

    glass = Glass(scene, {
        'path': [
            {'x': -50, 'y': 50, 'arc': False},
            {'x': 50, 'y': 50, 'arc': False},
            {'x': 50, 'y': 0, 'arc': False},
            {'x': -50, 'y': 0, 'arc': False},
        ],
        'refIndex': 1.5,
    })
    glass.name = 'slab'
    scene.add_object(glass)

    det = Detector(scene, {'type': 'Detector',
                            'p1': {'x': -20, 'y': -50}, 'p2': {'x': 20, 'y': -50}})
    scene.add_object(det)

    sim = Simulator(scene, max_rays=100)
    sim.run()
    assert scene.error is None

    records = det.get_hit_records()
    assert len(records) == 1
    uid = records[0]['ray_uuid']

    # Three hand-computable 50-unit legs: air (n=1.0) -> glass (n=1.5) -> air (n=1.0).
    path = sim.lineage.get_full_path(uid)
    assert [round(s.medium_index, 6) for s in path] == [1.0, 1.5, 1.0]

    assert math.isclose(geometric_path_length(sim.lineage, uid), 150.0, rel_tol=1e-9)
    assert math.isclose(optical_path_length(sim.lineage, uid), 175.0, rel_tol=1e-9)
    # optical > geometric whenever any leg's index exceeds 1.0, and by
    # exactly the extra 0.5 * 50 the glass leg contributes.
    assert math.isclose(
        optical_path_length(sim.lineage, uid) - geometric_path_length(sim.lineage, uid),
        25.0, rel_tol=1e-9,
    )


def test_medium_index_default_is_air_with_no_glass():
    """With no refracting object in the scene, medium_index must stay 1.0
    throughout, and optical_path_length must degrade to exactly
    geometric_path_length."""
    scene = Scene()
    _horizontal_ray(scene)
    det = Detector(scene, {'type': 'Detector',
                            'p1': {'x': 200, 'y': 0}, 'p2': {'x': 200, 'y': 160}})
    scene.add_object(det)

    sim = Simulator(scene)
    sim.run()

    uid = det.get_hit_records()[0]['ray_uuid']
    path = sim.lineage.get_full_path(uid)
    assert all(s.medium_index == 1.0 for s in path)
    assert math.isclose(
        geometric_path_length(sim.lineage, uid),
        optical_path_length(sim.lineage, uid),
        rel_tol=1e-9,
    )


def test_medium_index_on_fresnel_reflected_siblings():
    """Fresnel reflection at a glass surface must NOT change medium_index --
    ray2.medium_index = ray.medium_index exactly, per base_glass.py's
    refract(). Checked directly on the reflected sibling rays at both the
    entry (stays in air) and exit (stays in glass) interfaces, using the
    same slab fixture as test_geometric_and_optical_path_length_through_
    glass_slab."""
    scene = Scene()
    ray_src = SingleRay(scene, {'type': 'SingleRay', 'brightness': 1.0,
                                 'p1': {'x': 0, 'y': 100}, 'p2': {'x': 0, 'y': 90}})
    scene.add_object(ray_src)

    glass = Glass(scene, {
        'path': [
            {'x': -50, 'y': 50, 'arc': False},
            {'x': 50, 'y': 50, 'arc': False},
            {'x': 50, 'y': 0, 'arc': False},
            {'x': -50, 'y': 0, 'arc': False},
        ],
        'refIndex': 1.5,
    })
    glass.name = 'slab'
    scene.add_object(glass)

    sim = Simulator(scene, max_rays=100)
    segments = sim.run()
    assert scene.error is None

    root = [s for s in segments if s.interaction_type == 'source'][0]

    # Entry interface: root's children are the transmitted (into glass) and
    # the Fresnel-reflected (stays in air) rays.
    entry_children = sim.lineage.get_children(root.uuid)
    entry_transmitted = [c for c in entry_children if c.interaction_type == 'refract']
    entry_reflected = [c for c in entry_children if c.interaction_type == 'reflect']
    assert len(entry_transmitted) == 1 and len(entry_reflected) == 1
    assert math.isclose(entry_transmitted[0].medium_index, 1.5, rel_tol=1e-9)
    assert math.isclose(entry_reflected[0].medium_index, 1.0, rel_tol=1e-9)

    # Exit interface: the transmitted-into-glass ray's own children are the
    # transmitted (back into air) and Fresnel-reflected (stays in glass) rays.
    exit_children = sim.lineage.get_children(entry_transmitted[0].uuid)
    exit_transmitted = [c for c in exit_children if c.interaction_type == 'refract']
    exit_reflected = [c for c in exit_children if c.interaction_type == 'reflect']
    assert len(exit_transmitted) == 1 and len(exit_reflected) == 1
    assert math.isclose(exit_transmitted[0].medium_index, 1.0, rel_tol=1e-9)
    assert math.isclose(exit_reflected[0].medium_index, 1.5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 6. Beam.emis_angle guard (C-BEAM-01)
# ---------------------------------------------------------------------------

def test_beam_negative_emis_angle_raises():
    """C-BEAM-01: a negative emis_angle used to silently flip the sign of
    every emitted ray's brightness (num_angled_rays went negative). Now
    guarded: Beam.on_simulation_start() raises ValueError instead."""
    from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam

    scene = Scene()
    beam = Beam(scene)
    beam.p1 = {'x': 0, 'y': 0}
    beam.p2 = {'x': 10, 'y': 0}
    beam.emis_angle = -40.0
    scene.add_object(beam)

    try:
        beam.on_simulation_start()
        raise AssertionError("expected ValueError for negative emis_angle")
    except ValueError as exc:
        assert 'emis_angle' in str(exc)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_detector_records_single_hit,
        test_detector_never_terminates_ray,
        test_hit_uuid_resolves_in_lineage,
        test_hit_records_reset_on_rerun,
        test_wavelength_none_when_color_simulation_disabled,
        test_wavelength_recorded_when_color_simulation_enabled,
        test_incident_angle_at_normal_incidence,
        test_incident_angle_at_45_degrees,
        test_incident_angle_is_bounded,
        test_one_sided_absorption_is_default,
        test_non_absorbing_side_is_a_complete_no_op,
        test_absorbing_side_flip_recovers_the_hit,
        test_two_sided_restores_signed_net_flux,
        test_rxi_receiver_acceptance_curve_matches_15_bidirectional_3_4,
        test_rank_paths_by_detector_leaves,
        test_linear_sensor_pixel_hit_uuids,
        test_linear_sensor_pixel_hit_uuids_reversed,
        test_geometric_and_optical_path_length_through_glass_slab,
        test_medium_index_default_is_air_with_no_glass,
        test_medium_index_on_fresnel_reflected_siblings,
        test_beam_negative_emis_angle_raises,
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
