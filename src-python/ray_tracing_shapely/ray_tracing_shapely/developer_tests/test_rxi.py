"""
Python-specific module: test rxi
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
RXIOptic TESTS -- Nonimaging Optics Phase 2, Steps 2-3
===============================================================================
Tests RXIOptic (optical_elements.prisms.rxi): geometry sanity, the
refinement_spans mechanism (dev_doc/architecture/components/nonimaging_design.md, wired
through BasePrism.__init__'s _supports_refinement conditional), mirror
coating (s2 always, mirror_band_deg optionally), and parameter validation.
See test_signature_analysis.py for the natural refract/tir transition this
class produces, and estimate_role_transition finding it.

Run with:
    python developer_tests/test_rxi.py
Or with pytest:
    pytest developer_tests/test_rxi.py -v
===============================================================================
"""

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def test_rxi_default_construction():
    """A default RXIOptic builds a valid CCW polygon with the expected
    vertex count (2 + s1_segments + 1)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)

    assert len(rxi.path) == 2 + 16 + 1  # BL, BR, s1_segments+1 s1 points
    assert rxi.signed_area() > 0, "RXIOptic should be CCW (positive signed area)"
    assert len(rxi._edge_roles) == len(rxi.path)
    print(f"  PASS: default construction, {len(rxi.path)} vertices, CCW")
    return True


def test_rxi_refinement_spans_adds_local_vertices():
    """refinement_spans adds extra vertices concentrated in the given span,
    via BasePrism.__init__'s _supports_refinement conditional."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    base = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)

    scene2 = Scene()
    refined = RXIOptic(
        scene2, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16,
        refinement_spans=[(10.0, 20.0, 8)],
    )
    assert len(refined.path) > len(base.path)
    assert len(refined._edge_roles) == len(refined.path)
    print(f"  PASS: refinement_spans grew {len(base.path)} -> {len(refined.path)} vertices")
    return True


def test_rxi_supports_refinement_flag():
    """_supports_refinement=True is what makes BasePrism.__init__ thread
    refinement_spans through; unrelated classes are unaffected."""
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism
    from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism

    assert RXIOptic._supports_refinement is True
    assert DTIRCPrism._supports_refinement is False
    assert RefractometerPrism._supports_refinement is False
    print("  PASS: _supports_refinement is opt-in, RXIOptic is the only current opt-in class")
    return True


def test_rxi_mirror_coating():
    """s2 is always mirror-coated; mirror_band_deg additionally coats the
    matching s1 edges, and only those."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    assert len(rxi.mirrors) == 1
    assert rxi.mirrors[0].name.endswith('_s2_mirror')

    scene2 = Scene()
    rxi_band = RXIOptic(
        scene2, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16,
        mirror_band_deg=(-10.0, 10.0),
    )
    assert len(rxi_band.mirrors) > 1
    s1_mirrors = [m for m in rxi_band.mirrors if '_s1_mirror_seg' in m.name]
    assert len(s1_mirrors) >= 1
    print(f"  PASS: s2 always coated (1 mirror); mirror_band_deg adds {len(s1_mirrors)} s1 mirrors")
    return True


def test_rxi_parameter_validation():
    """Out-of-range parameters raise ValueError."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    for kwargs in [
        dict(n=1.5, phi_edge_deg=0.0),
        dict(n=1.5, phi_edge_deg=95.0),
        dict(n=1.5, depth=0.0),
        dict(n=1.5, s1_segments=0),
        dict(n=1.5, mirror_band_deg=(10.0, -10.0)),   # reversed
        dict(n=1.5, mirror_band_deg=(-60.0, 10.0)),   # outside phi_edge_deg
    ]:
        scene = Scene()
        try:
            RXIOptic(scene, **kwargs)
            raise AssertionError(f"expected ValueError for {kwargs}")
        except ValueError:
            pass
    print("  PASS: out-of-range parameters raise ValueError")
    return True


def test_rxi_no_cavity_s1_start_edge_index():
    """Without receiver_half_width, s2 is 1 edge and s1 starts at edge_index
    2 -- the pre-existing layout, guarded explicitly so the cavity feature
    can't silently shift it for the default (no-cavity) case."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    assert rxi.s1_start_edge_index == 2
    assert rxi.receiver_half_width is None
    print("  PASS: no-cavity RXIOptic keeps s1_start_edge_index=2 (backward compatible)")
    return True


def test_rxi_receiver_cavity_geometry():
    """receiver_half_width adds a 2-vertex/2-edge receiver gap in s2:
    S2L (mirror) - REC (uncoated) - S2R (mirror), and only the two flanks
    get a Mirror object."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic
    from ray_tracing_shapely.optical_elements.roles import Role

    scene = Scene()
    base = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)

    scene2 = Scene()
    rxi = RXIOptic(scene2, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16,
                    receiver_half_width=3.0)

    assert len(rxi.path) == len(base.path) + 2
    assert rxi.s1_start_edge_index == 4  # 3 s2 edges + 1 right-side edge
    assert len(rxi._edge_roles) == len(rxi.path)

    assert rxi.get_functional_label(0)[0] == 'S2L'
    assert rxi.get_functional_label(1)[0] == 'REC'
    assert rxi.get_functional_label(2)[0] == 'S2R'
    assert rxi.get_edge_role(0) is Role.WALL
    assert rxi.get_edge_role(1) is Role.ABSORBER
    assert rxi.get_edge_role(2) is Role.WALL

    mirror_names = {m.name for m in rxi.mirrors}
    assert mirror_names == {'rxi_s2_left_mirror', 'rxi_s2_right_mirror'}
    print("  PASS: receiver cavity adds S2L/REC/S2R, only flanks mirror-coated")
    return True


def test_rxi_receiver_cavity_validation():
    """Out-of-range receiver_half_width raises ValueError."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    for kwargs in [
        dict(n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, receiver_half_width=0.0),
        dict(n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, receiver_half_width=-1.0),
        # s2 half-width = size*sin(phi_edge_deg) ~= 22.98; must be strictly less than that.
        dict(n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, receiver_half_width=25.0),
    ]:
        scene = Scene()
        try:
            RXIOptic(scene, **kwargs)
            raise AssertionError(f"expected ValueError for {kwargs}")
        except ValueError:
            pass
    print("  PASS: out-of-range receiver_half_width raises ValueError")
    return True


def test_rxi_receiver_cavity_collects_light():
    """A Detector below the receiver gap collects real, non-trivial power
    from a beam illuminating s1 -- the cavity is a genuine optical exit,
    not just a geometric notch."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam
    from ray_tracing_shapely.core.scene_objs.other.detector import Detector
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    scene.ray_density = 20
    scene.min_brightness_exp = 3

    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16,
                    mirror_band_deg=(-10.0, 10.0), receiver_half_width=3.0)
    rxi.name = 'rxi'
    scene.add_object(rxi)

    beam = Beam(scene)
    beam.p1 = {'x': -25, 'y': 15}
    beam.p2 = {'x': 25, 'y': 15}
    beam.emis_angle = 0.0
    beam.brightness = 1.0
    scene.add_object(beam)

    det = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': -3.0, 'y': -45.0 - 1.0},
        'p2': {'x': 3.0, 'y': -45.0 - 1.0},
        'irrad_map': True, 'bin_size': 0.3,
    })
    det.name = 'receiver_detector'
    scene.add_object(det)

    sim = Simulator(scene, max_rays=20000)
    sim.run()
    assert scene.error is None
    assert det.power > 1.0, f"expected substantial collected power, got {det.power}"
    print(f"  PASS: receiver detector collects real power ({det.power:.2f})")
    return True


def test_rxi_simulator_smoke():
    """A built RXIOptic (with s2 mirror-coated) traces through the real
    Simulator without error, producing refract/reflect/tir interactions."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    scene.ray_density = 15
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    rxi.name = 'rxi'
    scene.add_object(rxi)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 40}
    source.p2 = {'x': 0, 'y': 20}
    source.emis_angle = 60.0
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    sim = Simulator(scene, max_rays=6000)
    segments = sim.run()
    assert scene.error is None, f"scene error: {scene.error}"
    types = {s.interaction_type for s in segments}
    assert {'refract', 'reflect'} <= types, f"expected refract+reflect at least, got {types}"
    print(f"  PASS: traced {len(segments)} segments, interaction types={types}")
    return True


def run_all_tests():
    tests = [
        ("Default construction (CCW, vertex count)", test_rxi_default_construction),
        ("refinement_spans adds local vertices", test_rxi_refinement_spans_adds_local_vertices),
        ("_supports_refinement opt-in flag", test_rxi_supports_refinement_flag),
        ("Mirror coating (s2 always, band optionally)", test_rxi_mirror_coating),
        ("Parameter validation", test_rxi_parameter_validation),
        ("No-cavity s1_start_edge_index (backward compat)", test_rxi_no_cavity_s1_start_edge_index),
        ("Receiver cavity geometry", test_rxi_receiver_cavity_geometry),
        ("Receiver cavity validation", test_rxi_receiver_cavity_validation),
        ("Receiver cavity collects light", test_rxi_receiver_cavity_collects_light),
        ("Simulator smoke test", test_rxi_simulator_smoke),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        print(f"\nTEST: {name}")
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAILED: {name}")
            print(f"    Error: {e}")

    print("\n" + "=" * 78)
    print(f"SUMMARY: {passed}/{len(tests)} tests passed")
    print("=" * 78)

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")
        return False

    print("\nAll tests passed!")
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
