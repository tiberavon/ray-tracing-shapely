"""
===============================================================================
ROLE VOCABULARY TESTS -- Nonimaging Optics Phase 1, Step 1
===============================================================================
Covers:
1. Role / Mechanism enums (optical_elements.roles) -- values match
   Ray.interaction_type's literal strings.
2. BaseSceneObj.role property (get/set/default), mirroring .name.
3. _apply_functional_labels() accepts 2- AND 3-tuple _edge_roles entries --
   the fix that makes the rationale document's "backward-compatible append"
   claim actually true (see 15_p3_cpc_and_sms_optical_elements.md §9.1).

Run with:
    python developer_tests/test_roles.py
Or with pytest:
    pytest developer_tests/test_roles.py -v
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
    subclass (RefractometerPrism) is unaffected."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
    from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism
    from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism
    from ray_tracing_shapely.optical_elements.roles import Role

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

    # Existing 2-tuple subclasses are unaffected: no role tag, no crash.
    ref = RefractometerPrism(
        scene, n_prism=1.72, n_sample_range=(1.30, 1.50), measuring_surface_length=20.0
    )
    assert ref.get_functional_label(0) == ("B", "Base")
    assert ref.get_edge_role(0) is None, "2-tuple _edge_roles should report no Role"
    print("  PASS: existing 2-tuple _edge_roles subclasses unaffected")
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
