"""
Python-specific module: test roles
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
ROLE VOCABULARY TESTS -- Nonimaging Optics Phase 1, Step 1
===============================================================================
Covers:
1. Role / Mechanism enums (optical_elements.roles) -- values match
   Ray.interaction_type's literal strings. This is C-VOCAB-01's checked_by
   (dev_doc/architecture/contracts/C-VOCAB-01.md).
2. BaseSceneObj.role property (get/set/default), mirroring .name.
3. _apply_functional_labels() accepts 2- AND 3-tuple _edge_roles entries --
   the fix that makes the rationale document's "backward-compatible append"
   claim actually true, and part of what C-LABEL-02
   (dev_doc/architecture/contracts/C-LABEL-02.md) documents (see
   dev_doc/architecture/components/nonimaging_design.md for the original rationale).

Run with:
    python src-python/ray_tracing_shapely/developer_tests/test_roles.py
Or with pytest:
    pytest src-python/ray_tracing_shapely/developer_tests/test_roles.py -v
===============================================================================
"""

import sys
from pathlib import Path
from typing import ClassVar, List, Tuple

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def test_role_mechanism_enum_values():
    """Role/Mechanism enums exist with the documented vocabulary."""
    from ray_tracing_shapely.optical_elements.roles import Role, Mechanism

    expected_roles = {
        'entrance', 'wall', 'absorber', 'exit', 'blocker', 'source', 'sample_medium'
    }
    assert {r.value for r in Role} == expected_roles, "Role vocabulary mismatch"

    # Mechanism values MUST equal Ray.interaction_type's literal strings.
    assert Mechanism.REFRACT.value == 'refract'
    assert Mechanism.REFLECT.value == 'reflect'
    assert Mechanism.TIR.value == 'tir'
    print("  PASS: Role/Mechanism enum values")
    return True


def test_base_scene_obj_role_property():
    """BaseSceneObj.role defaults to None and round-trips like .name does."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
    from ray_tracing_shapely.optical_elements.roles import Role

    scene = Scene()
    blocker = Blocker(scene, {'p1': {'x': 0, 'y': 0}, 'p2': {'x': 1, 'y': 0}})

    assert blocker.role is None, "role should default to None"
    blocker.role = Role.BLOCKER
    assert blocker.role is Role.BLOCKER
    blocker.role = None
    assert blocker.role is None
    print("  PASS: BaseSceneObj.role get/set/default")
    return True


def test_edge_roles_three_tuple_backward_compat():
    """A 3-tuple _edge_roles (short, long, Role) builds without error, and
    get_functional_label()/get_edge_role() both work; a plain 2-tuple
    subclass is unaffected (no Role tag, no crash). RefractometerPrism
    used to be that 2-tuple example; it now carries Role tags of
    its own (profile_export.py needs them), so it is checked separately
    below instead of doubling as the "no Role" case."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
    from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism
    from ray_tracing_shapely.optical_elements.prisms.right_angle import RightAnglePrism
    from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism
    from ray_tracing_shapely.optical_elements.roles import Role, Mechanism

    class _ThrowawayRoleTaggedPrism(EquilateralPrism):
        """Throwaway subclass reusing EquilateralPrism's geometry, only to
        exercise a 3-tuple _edge_roles through BasePrism.__init__."""
        _edge_roles: ClassVar[List[Tuple]] = [
            ("B", "Base", Role.WALL),
            ("X", "Exit Face", Role.EXIT),
            ("E", "Entrance Face", Role.ENTRANCE),
        ]

    scene = Scene()
    prism = _ThrowawayRoleTaggedPrism(scene, side_length=50.0)

    assert prism.get_functional_label(0) == ("B", "Base")
    assert prism.get_functional_label(1) == ("X", "Exit Face")
    assert prism.get_edge_role(0) is Role.WALL
    assert prism.get_edge_role(1) is Role.EXIT
    assert prism.get_edge_role(2) is Role.ENTRANCE
    print("  PASS: 3-tuple _edge_roles builds, get_functional_label/get_edge_role correct")

    # A genuine 2-tuple subclass is unaffected: no role tag, no crash.
    # RightAnglePrism's _edge_roles is still (short, long) only.
    right_angle = RightAnglePrism(scene, leg_length=30.0)
    assert right_angle.get_functional_label(0) is not None
    assert right_angle.get_edge_role(0) is None, "2-tuple _edge_roles should report no Role"
    print("  PASS: existing 2-tuple _edge_roles subclasses unaffected")

    # RefractometerPrism itself is now Role/Mechanism-tagged
    # (profile_export.py's spans field needs this) -- see
    # developer_tests/test_profile_export.py for the fuller check.
    ref = RefractometerPrism(
        scene, n_prism=1.72, n_sample_range=(1.30, 1.50), measuring_surface_length=20.0
    )
    assert ref.get_edge_role(1) is Role.EXIT
    assert ref._edge_mechanisms["X"] is Mechanism.REFRACT
    print("  PASS: RefractometerPrism now carries Role/Mechanism tags")
    return True


def run_all_tests():
    tests = [
        ("Role/Mechanism enum values", test_role_mechanism_enum_values),
        ("BaseSceneObj.role property", test_base_scene_obj_role_property),
        ("_edge_roles 2-/3-tuple backward compat", test_edge_roles_three_tuple_backward_compat),
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
