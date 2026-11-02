"""
Python-specific module: test architecture layering
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
ARCHITECTURE LAYERING -- import-direction check
(dev_doc/concepts/KC7_headless_components_never_import_the_visualization_ones.md)
===============================================================================

`dev_doc/architecture/00_component_map.md`'s chain diagram and
`01_ports.md`'s register both assert a layering nobody was checking:
`core/` never imports `analysis/` or `optical_elements/`, and
`optical_elements/` never imports `analysis/`.
dev_doc/concepts/KC7_headless_components_never_import_the_visualization_ones.md
calls the component map "currently the only part of the tree with no
status, no checked_by and no check of any kind -- it is asserted, not
verified," and this is that check, using only the standard library (`ast`,
`pathlib`) rather than a new dependency (`import-linter`/`pytest-archon`).

This is a real import-graph diff, not a text grep: it parses every module
with `ast` and resolves both `import x.y` and `from .relative import z`
forms to the package they actually name, so a docstring mentioning
"optical_elements" (which a naive grep would flag) does not count. It also
excludes `if TYPE_CHECKING:` blocks (never executed, no real dependency).

**Writing this test found three real, previously undocumented crossings**
(a naive text grep, tried first during this pass, missed the two most
interesting ones -- they're inside `if TYPE_CHECKING:`/method bodies, not
findable by grepping for the string "analysis" at module scope). All three
are genuine, deliberate reuse choices, not accidents, and are allow-listed
below with the reason -- this test's job is to catch a *new* undocumented
crossing, not to relitigate these three:

- `core/simulator.py`, `run_with_result`/`run_bidirectional`: import
  `analysis.simulation_result`/`analysis.bidirectional` *inside the method
  body*, not at module scope, specifically to avoid a real circular import
  (`analysis/` imports `core/` at module level, so `core/` cannot import
  `analysis/` at module level too). `Simulator`'s own module-level surface
  has no analysis-layer dependency; only these two optional,
  richer-return-type convenience methods do, and only at call time.
- `core/svg_renderer.py`, two rendering-helper lookups: imports
  `analysis.glass_geometry.get_edge_descriptions` and
  `analysis.ray_geometry_queries.get_object_by_name`/`_resolve_edge`
  inside method bodies, to label rendered edges/objects by the same names
  `analysis/` already computes rather than re-deriving them. `svg_renderer`
  is distributed as `core` (`00_component_map.md`) but reaches into
  `analysis/` for exactly two lookups; not fixed here, since doing so is a
  refactor decision (duplicate the lookup, or move it down a layer), not a
  bug.
- `optical_elements/prisms/tir_utils.py`, module level: imports
  `analysis.fresnel_utils.critical_angle` directly — the one *module-level*
  (not deferred) crossing found, by the module's own docstring's admission
  ("provides DESIGN utilities... Import existing critical_angle from
  fresnel_utils for consistency" rather than duplicating the formula).

Run with:
    python src-python/ray_tracing_shapely/developer_tests/test_architecture_layering.py
Or with pytest:
    pytest src-python/ray_tracing_shapely/developer_tests/test_architecture_layering.py -v
===============================================================================
"""

import ast
import sys
from pathlib import Path
from typing import List, Set, Tuple

PKG_ROOT = Path(__file__).parent.parent  # .../ray_tracing_shapely
if str(PKG_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT.parent))


# (file path suffix, imported subpackage): reasoned exceptions, see the
# module docstring above for why each one is here.
_ALLOWED: Set[Tuple[str, str]] = {
    ('core/simulator.py', 'analysis'),
    ('core/svg_renderer.py', 'analysis'),
    ('optical_elements/prisms/tir_utils.py', 'analysis'),
}


def _type_checking_line_ranges(tree: ast.Module) -> List[Tuple[int, int]]:
    """(start, end) line ranges of every `if TYPE_CHECKING:` block's body,
    so imports inside them (never executed) can be excluded."""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_type_checking = (
                (isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING') or
                (isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING')
            )
            if is_type_checking and node.body:
                ranges.append((node.body[0].lineno, node.body[-1].end_lineno or node.body[-1].lineno))
    return ranges


def _resolve_import(node: ast.AST, module_path: Path) -> List[str]:
    """Return the top-level ray_tracing_shapely subpackage(s) (e.g. 'core',
    'analysis', 'optical_elements') a single import statement names, or []
    if it doesn't name one of ours."""
    names: List[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split('.')
            if parts[0] == 'ray_tracing_shapely' and len(parts) > 1:
                names.append(parts[1])
    elif isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            # Relative import: resolve against module_path's own location
            # inside ray_tracing_shapely, e.g. core/scene_objs/base_scene_obj.py
            # doing `from ..analysis import x` (level=2).
            rel_parts = module_path.relative_to(PKG_ROOT).parts[:-1]  # drop filename
            up = node.level - 1
            base_parts = list(rel_parts[:len(rel_parts) - up]) if up else list(rel_parts)
            target_parts = node.module.split('.') if node.module else []
            combined = base_parts + target_parts
            if combined:
                names.append(combined[0])
        elif node.module:
            parts = node.module.split('.')
            if parts[0] == 'ray_tracing_shapely' and len(parts) > 1:
                names.append(parts[1])
    return names


def _subpackage_imports(subpackage: str) -> List[Tuple[Path, str]]:
    """(file, imported_subpackage) pairs for every .py file under
    ray_tracing_shapely/<subpackage>/. Scans the whole file, including any
    __main__ demo block -- the conservative (stricter) choice."""
    results: List[Tuple[Path, str]] = []
    root = PKG_ROOT / subpackage
    for path in root.rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except SyntaxError:
            continue
        tc_ranges = _type_checking_line_ranges(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if any(start <= node.lineno <= end for start, end in tc_ranges):
                    continue  # TYPE_CHECKING-only: never executed
                for imported in _resolve_import(node, path):
                    if imported != subpackage:
                        results.append((path, imported))
    return results


def _not_allowed(violations: List[Tuple[Path, str]]) -> List[Tuple[Path, str]]:
    return [
        (p, imp) for p, imp in violations
        if (p.relative_to(PKG_ROOT).as_posix(), imp) not in _ALLOWED
    ]


def test_core_does_not_import_analysis_or_optical_elements():
    violations = _not_allowed([
        (p, imp) for p, imp in _subpackage_imports('core')
        if imp in ('analysis', 'optical_elements')
    ])
    assert not violations, (
        "core/ must not import analysis/ or optical_elements/ outside the "
        "allow-listed exceptions (core_simulator owns nothing above it in "
        "the chain -- 00_component_map.md); if this is a real new "
        "crossing, decide whether to allow-list it (with a reason, in this "
        "file's docstring) or fix it: " +
        ", ".join(f"{p.relative_to(PKG_ROOT)} imports {imp}" for p, imp in violations)
    )


def test_optical_elements_does_not_import_analysis():
    violations = _not_allowed([
        (p, imp) for p, imp in _subpackage_imports('optical_elements')
        if imp == 'analysis'
    ])
    assert not violations, (
        "optical_elements/ must not import analysis/ outside the "
        "allow-listed exceptions (analysis is the consumer layer, per "
        "00_component_map.md's chain): " +
        ", ".join(f"{p.relative_to(PKG_ROOT)} imports {imp}" for p, imp in violations)
    )


def test_allowlist_names_only_real_crossings():
    """The allow-list itself must stay accurate: every entry must actually
    exist as an import today (so it can't silently rot into a stale claim
    about the codebase), and there must be no unexplained crossing this
    test doesn't already know about via one of the two tests above."""
    all_core = {(p.relative_to(PKG_ROOT).as_posix(), imp)
                for p, imp in _subpackage_imports('core')}
    all_oe = {(p.relative_to(PKG_ROOT).as_posix(), imp)
              for p, imp in _subpackage_imports('optical_elements')}
    stale = _ALLOWED - all_core - all_oe
    assert not stale, f"allow-list entries no longer match a real import: {stale}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_core_does_not_import_analysis_or_optical_elements,
        test_optical_elements_does_not_import_analysis,
        test_allowlist_names_only_real_crossings,
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
        print("\nAll architecture-layering tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
