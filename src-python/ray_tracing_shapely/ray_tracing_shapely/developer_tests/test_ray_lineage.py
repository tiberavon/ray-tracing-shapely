"""
Python-specific module: test ray lineage
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
RAY LINEAGE -- cycle-guard verification (C-LINEAGE-01)
===============================================================================

RayLineage's tree-shape invariants (single parent, acyclic, parent
registered before any child can exist) are guaranteed by construction in
Simulator._process_rays()'s FIFO queue -- see
dev_doc/architecture/contracts/C-LINEAGE-01.md. These tests do not exercise
that construction; they hand-build a RayLineage with a manufactured cycle,
bypassing Simulator entirely, to verify the defensive guard added to
get_ancestors/get_full_path/get_tree_depth/get_descendants/get_subtree_uuids
actually fires -- RuntimeError, not an infinite loop or a silently
truncated/double-counted result -- if that invariant is ever violated by a
future regression.

Run with:
    python src-python/ray_tracing_shapely/developer_tests/test_ray_lineage.py
Or with pytest:
    pytest src-python/ray_tracing_shapely/developer_tests/test_ray_lineage.py -v
===============================================================================
"""

import sys
from pathlib import Path

# Allow running as a script or with pytest
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.ray_lineage import RayLineage


class _FakeSegment:
    """Minimal stand-in for a Ray -- RayLineage.register() only reads
    uuid/parent_uuid/interaction_type."""

    def __init__(self, uuid, parent_uuid, interaction_type='refract'):
        self.uuid = uuid
        self.parent_uuid = parent_uuid
        self.interaction_type = interaction_type


def _two_cycle_lineage():
    """A -> B -> A: neither is a real root, each is the other's parent."""
    lineage = RayLineage()
    a = _FakeSegment('a', 'b')
    b = _FakeSegment('b', 'a')
    lineage.register(a)
    lineage.register(b)
    return lineage


def test_get_ancestors_raises_on_cycle():
    lineage = _two_cycle_lineage()
    try:
        lineage.get_ancestors('a')
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert 'cycle' in str(exc).lower()


def test_get_full_path_raises_on_cycle():
    lineage = _two_cycle_lineage()
    try:
        lineage.get_full_path('a')
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert 'cycle' in str(exc).lower()


def test_get_tree_depth_raises_on_cycle():
    lineage = _two_cycle_lineage()
    try:
        lineage.get_tree_depth('a')
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert 'cycle' in str(exc).lower()


def test_get_descendants_raises_on_cycle():
    lineage = _two_cycle_lineage()
    try:
        lineage.get_descendants('a')
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert 'cycle' in str(exc).lower()


def test_get_subtree_uuids_raises_on_cycle():
    lineage = _two_cycle_lineage()
    try:
        lineage.get_subtree_uuids('a')
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert 'cycle' in str(exc).lower()


def test_acyclic_tree_is_unaffected():
    """The guard must not false-positive on an ordinary tree: a -> b -> c,
    plus a sibling d, exercised through every guarded method."""
    lineage = RayLineage()
    lineage.register(_FakeSegment('a', None, 'source'))
    lineage.register(_FakeSegment('b', 'a'))
    lineage.register(_FakeSegment('c', 'b'))
    lineage.register(_FakeSegment('d', 'a'))

    assert [s.uuid for s in lineage.get_ancestors('c')] == ['a', 'b']
    assert [s.uuid for s in lineage.get_full_path('c')] == ['a', 'b', 'c']
    assert lineage.get_tree_depth('c') == 2
    assert {s.uuid for s in lineage.get_descendants('a')} == {'b', 'c', 'd'}
    assert lineage.get_subtree_uuids('a') == {'a', 'b', 'c', 'd'}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_get_ancestors_raises_on_cycle,
        test_get_full_path_raises_on_cycle,
        test_get_tree_depth_raises_on_cycle,
        test_get_descendants_raises_on_cycle,
        test_get_subtree_uuids_raises_on_cycle,
        test_acyclic_tree_is_unaffected,
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
        print("\nAll RayLineage cycle-guard tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
