"""
Python-specific module: test phase1 agentic db
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
PHASE 1: SQLite Infrastructure - Feature Verification Test
===============================================================================

Tests the in-memory SQLite database created by agentic_db.py, including:
1. Schema creation and population
2. Rays table correctness
3. Glass objects table correctness
4. Edges table correctness
5. ray_glass_membership precomputation
6. ray_edge_crossing precomputation
7. query_rays agentic tool (SELECT enforcement, result format)
8. describe_schema agentic tool
9. SQL injection rejection
10. Integration with set_context_from_result

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_phase1_agentic_db

===============================================================================
"""

import sys
import os

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    query_rays,
    describe_schema,
)
from ray_tracing_shapely.analysis.ray_geometry_queries import (
    find_rays_inside_glass,
    find_rays_crossing_edge,
)
from ray_tracing_shapely.analysis.glass_geometry import get_edge_descriptions
from ray_tracing_shapely.analysis.tool_registry import (
    get_agentic_tools,
    list_available_tools,
)


def build_test_scene():
    """Build a minimal scene: one triangular prism + one single ray."""
    scene = Scene()

    prism = Glass(scene)
    prism.path = [
        {'x': 200, 'y': 50, 'arc': False},
        {'x': 250, 'y': 100, 'arc': False},
        {'x': 150, 'y': 100, 'arc': False},
    ]
    prism.refraction_index = 1.5
    prism.name = 'test_prism'
    scene.add_object(prism)

    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 100, 'y': 80}
    ray_src.p2 = {'x': 250, 'y': 80}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    # Label edges with cardinal directions
    prism.auto_label_cardinal()

    return scene, prism


def run_simulation(scene):
    """Run the simulator and return segments."""
    sim = Simulator(scene)
    segments = sim.run()
    return segments


# =============================================================================
# Tests
# =============================================================================

def test_tables_exist():
    """Test 1: All 7 tables are created."""
    print("\nTest 1: Tables exist")
    result = query_rays(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    assert result['status'] == 'ok', f"Query failed: {result}"
    table_names = [row[0] for row in result['data']['rows']]
    expected = ['detector_hits', 'detectors', 'edges', 'glass_objects',
                'ray_edge_crossing', 'ray_glass_membership', 'rays']
    assert table_names == expected, f"Expected {expected}, got {table_names}"
    print(f"  PASS: Found tables: {table_names}")
    return True


def test_rays_row_count(segments):
    """Test 2: rays table has one row per segment."""
    print("\nTest 2: rays row count")
    result = query_rays("SELECT COUNT(*) as n FROM rays")
    assert result['status'] == 'ok', f"Query failed: {result}"
    count = result['data']['rows'][0][0]
    assert count == len(segments), f"Expected {len(segments)} rows, got {count}"
    print(f"  PASS: {count} rows (matches {len(segments)} segments)")
    return True


def test_rays_columns():
    """Test 3: rays table has all expected columns."""
    print("\nTest 3: rays columns")
    result = query_rays("SELECT * FROM rays LIMIT 0")
    assert result['status'] == 'ok', f"Query failed: {result}"
    columns = result['data']['columns']
    expected_cols = [
        'uuid', 'parent_uuid', 'interaction_type',
        'p1_x', 'p1_y', 'p2_x', 'p2_y',
        'midpoint_x', 'midpoint_y', 'length',
        'brightness_s', 'brightness_p', 'brightness_total',
        'degree_of_polarization', 'polarization_ratio',
        'wavelength', 'gap', 'is_new',
        'is_tir_result', 'caused_tir', 'tir_count',
        'is_grazing_result__angle', 'caused_grazing__angle',
        'is_grazing_result__polar', 'caused_grazing__polar',
        'is_grazing_result__transm', 'caused_grazing__transm',
        'source_uuid', 'source_label',
        # Surface hit records (Step B)
        'hit_surface_uuid',
        'hit_point_x', 'hit_point_y',
        'hit_normal_x', 'hit_normal_y',
        'incident_angle',
        # Bidirectional tracing (path auditing)
        'tree',
    ]
    assert columns == expected_cols, (
        f"Column mismatch.\n  Expected: {expected_cols}\n  Got: {columns}"
    )
    print(f"  PASS: {len(columns)} columns match expected schema")
    return True


def test_computed_columns(segments):
    """Test 4: Computed columns (length, brightness_total, DOP) are correct."""
    print("\nTest 4: Computed columns")
    if not segments:
        print("  SKIP: no segments")
        return True

    seg = segments[0]
    result = query_rays(
        f"SELECT length, brightness_total, degree_of_polarization "
        f"FROM rays WHERE uuid = '{seg.uuid}'"
    )
    assert result['status'] == 'ok', f"Query failed: {result}"
    assert result['data']['row_count'] == 1, "Expected exactly 1 row"
    row = result['data']['rows'][0]
    db_length, db_bt, db_dop = row

    assert abs(db_bt - seg.total_brightness) < 1e-6, (
        f"brightness_total mismatch: DB={db_bt}, Ray={seg.total_brightness}"
    )
    assert abs(db_dop - seg.degree_of_polarization) < 1e-6, (
        f"DOP mismatch: DB={db_dop}, Ray={seg.degree_of_polarization}"
    )
    assert db_length > 0, "Length should be positive"
    print(f"  PASS: length={db_length:.4f}, brightness_total={db_bt:.6f}, DOP={db_dop:.6f}")
    return True


def test_glass_objects_table():
    """Test 5: glass_objects has correct entries."""
    print("\nTest 5: glass_objects table")
    result = query_rays("SELECT name, display_name, ref_index, edge_count FROM glass_objects")
    assert result['status'] == 'ok', f"Query failed: {result}"
    assert result['data']['row_count'] >= 1, "Expected at least 1 glass object"
    row = result['data']['rows'][0]
    name, display_name, ref_index, edge_count = row
    assert name == 'test_prism', f"Expected name 'test_prism', got {name!r}"
    assert edge_count == 3, f"Expected 3 edges for triangle, got {edge_count}"
    print(f"  PASS: name={name!r}, display={display_name!r}, "
          f"n={ref_index}, edges={edge_count}")
    return True


def test_edges_table(prism):
    """Test 6: edges table has correct entries per glass."""
    print("\nTest 6: edges table")
    result = query_rays(
        "SELECT glass_name, edge_index, short_label, long_label, edge_type "
        "FROM edges ORDER BY edge_index"
    )
    assert result['status'] == 'ok', f"Query failed: {result}"
    rows = result['data']['rows']
    assert len(rows) == 3, f"Expected 3 edges for triangle, got {len(rows)}"

    edge_descs = get_edge_descriptions(prism)
    for i, (row, ed) in enumerate(zip(rows, edge_descs)):
        assert row[1] == ed.index, f"Edge {i}: index mismatch"
        assert row[2] == ed.short_label, f"Edge {i}: short_label mismatch"
    print(f"  PASS: 3 edges with labels {[r[2] for r in rows]}")
    return True


def test_ray_glass_membership(segments, prism):
    """Test 7: ray_glass_membership matches find_rays_inside_glass()."""
    print("\nTest 7: ray_glass_membership")
    # Get expected result from Python function
    inside_rays = find_rays_inside_glass(segments, prism)
    expected_uuids = {r.uuid for r in inside_rays}

    # Get from SQL
    result = query_rays(
        "SELECT ray_uuid FROM ray_glass_membership "
        "WHERE glass_name = 'test_prism'"
    )
    assert result['status'] == 'ok', f"Query failed: {result}"
    db_uuids = {row[0] for row in result['data']['rows']}

    assert db_uuids == expected_uuids, (
        f"Membership mismatch: DB has {len(db_uuids)}, "
        f"Python has {len(expected_uuids)}"
    )
    print(f"  PASS: {len(db_uuids)} rays inside 'test_prism' "
          f"(matches find_rays_inside_glass)")
    return True


def test_ray_edge_crossing(segments, prism):
    """Test 8: ray_edge_crossing matches find_rays_crossing_edge()."""
    print("\nTest 8: ray_edge_crossing")
    edge_descs = get_edge_descriptions(prism)
    if not edge_descs:
        print("  SKIP: no edges")
        return True

    label = edge_descs[0].short_label
    crossing_rays = find_rays_crossing_edge(segments, prism, label)
    expected_uuids = {r.uuid for r in crossing_rays}

    result = query_rays(
        f"SELECT ray_uuid FROM ray_edge_crossing "
        f"WHERE glass_name = 'test_prism' AND edge_short_label = '{label}'"
    )
    assert result['status'] == 'ok', f"Query failed: {result}"
    db_uuids = {row[0] for row in result['data']['rows']}

    assert db_uuids == expected_uuids, (
        f"Crossing mismatch for edge '{label}': DB has {len(db_uuids)}, "
        f"Python has {len(expected_uuids)}"
    )
    print(f"  PASS: {len(db_uuids)} rays crossing edge '{label}' "
          f"(matches find_rays_crossing_edge)")
    return True


def test_query_rays_result_format():
    """Test 9: query_rays returns correct envelope structure."""
    print("\nTest 9: query_rays result format")
    result = query_rays("SELECT COUNT(*) as n, AVG(brightness_total) as avg_b FROM rays")
    assert result['status'] == 'ok', f"Expected ok status, got {result}"
    data = result['data']
    assert 'columns' in data, "Missing 'columns' key"
    assert 'rows' in data, "Missing 'rows' key"
    assert 'row_count' in data, "Missing 'row_count' key"
    assert data['columns'] == ['n', 'avg_b'], f"Unexpected columns: {data['columns']}"
    assert data['row_count'] == 1, f"Expected 1 row, got {data['row_count']}"
    print(f"  PASS: columns={data['columns']}, row_count={data['row_count']}")
    return True


def test_query_rays_join():
    """Test 10: query_rays with JOIN works."""
    print("\nTest 10: query_rays with JOIN")
    result = query_rays(
        "SELECT r.uuid, r.brightness_total "
        "FROM rays r "
        "JOIN ray_glass_membership m ON r.uuid = m.ray_uuid "
        "WHERE m.glass_name = 'test_prism' "
        "ORDER BY r.brightness_total DESC "
        "LIMIT 5"
    )
    assert result['status'] == 'ok', f"JOIN query failed: {result}"
    print(f"  PASS: {result['data']['row_count']} rows from JOIN query")
    return True


def test_reject_insert():
    """Test 11: query_rays rejects INSERT."""
    print("\nTest 11: Reject INSERT")
    result = query_rays("INSERT INTO rays (uuid) VALUES ('evil')")
    assert result['status'] == 'error', f"Expected error, got {result}"
    assert 'SELECT' in result['message'], f"Error should mention SELECT: {result['message']}"
    print(f"  PASS: Rejected with: {result['message'][:60]}...")
    return True


def test_reject_drop():
    """Test 12: query_rays rejects DROP TABLE."""
    print("\nTest 12: Reject DROP")
    result = query_rays("DROP TABLE rays")
    assert result['status'] == 'error', f"Expected error, got {result}"
    print(f"  PASS: Rejected with: {result['message'][:60]}...")
    return True


def test_reject_multi_statement():
    """Test 13: query_rays rejects multiple statements."""
    print("\nTest 13: Reject multi-statement")
    result = query_rays("SELECT 1; DROP TABLE rays")
    assert result['status'] == 'error', f"Expected error, got {result}"
    print(f"  PASS: Rejected with: {result['message'][:60]}...")
    return True


def test_describe_schema():
    """Test 14: describe_schema returns all tables."""
    print("\nTest 14: describe_schema")
    result = describe_schema()
    assert result['status'] == 'ok', f"describe_schema failed: {result}"
    tables = result['data']['tables']
    expected_tables = {'rays', 'glass_objects', 'edges',
                       'ray_glass_membership', 'ray_edge_crossing',
                       'detectors', 'detector_hits'}
    assert set(tables.keys()) == expected_tables, (
        f"Expected tables {expected_tables}, got {set(tables.keys())}"
    )
    for tname, tinfo in tables.items():
        assert 'columns' in tinfo, f"Table {tname} missing 'columns'"
        assert 'row_count' in tinfo, f"Table {tname} missing 'row_count'"
    rc_summary = ', '.join(f'{k}: {v["row_count"]}' for k, v in tables.items())
    print(f"  PASS: {len(tables)} tables with row counts: {{{rc_summary}}}")
    return True


def test_describe_schema_column_metadata():
    """Test 15: describe_schema columns have name, type, description."""
    print("\nTest 15: describe_schema column metadata")
    result = describe_schema()
    assert result['status'] == 'ok'
    rays_cols = result['data']['tables']['rays']['columns']
    assert len(rays_cols) == 36, f"Expected 36 ray columns, got {len(rays_cols)}"
    for col in rays_cols:
        assert 'name' in col, f"Column missing 'name': {col}"
        assert 'type' in col, f"Column missing 'type': {col}"
        assert 'description' in col, f"Column missing 'description': {col}"
    print(f"  PASS: rays table has {len(rays_cols)} columns with full metadata")
    return True


def test_clear_context_closes_db():
    """Test 16: clear_context() makes query_rays return error."""
    print("\nTest 16: clear_context closes DB")
    clear_context()
    result = query_rays("SELECT 1")
    assert result['status'] == 'error', f"Expected error after clear, got {result}"
    print(f"  PASS: query_rays returns error after clear_context()")
    return True


def test_tool_registry():
    """Test 17: Tool registry includes Phase 1 tools."""
    print("\nTest 17: Tool registry")
    tools = get_agentic_tools()
    names = [t['name'] for t in tools]
    assert 'query_rays' in names, "query_rays missing from get_agentic_tools()"
    assert 'describe_schema' in names, "describe_schema missing from get_agentic_tools()"

    text = list_available_tools()
    assert 'query_rays' in text, "query_rays missing from list_available_tools()"
    assert 'describe_schema' in text, "describe_schema missing from list_available_tools()"

    print(f"  PASS: query_rays and describe_schema in registry (total: {len(tools)} tools)")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("Phase 1: SQLite Infrastructure - Feature Verification")
    print("=" * 70)

    # --- Setup ---
    print("\nSetup: Building scene and running simulation...")
    scene, prism = build_test_scene()
    segments = run_simulation(scene)
    print(f"  Scene has {len(scene.objs)} objects, "
          f"simulation produced {len(segments)} segments")

    set_context(scene, segments)
    print("  Context set (DB created).\n")

    # --- Run tests ---
    results = []
    results.append(("Tables exist",              test_tables_exist()))
    results.append(("rays row count",             test_rays_row_count(segments)))
    results.append(("rays columns",               test_rays_columns()))
    results.append(("Computed columns",           test_computed_columns(segments)))
    results.append(("glass_objects table",        test_glass_objects_table()))
    results.append(("edges table",                test_edges_table(prism)))
    results.append(("ray_glass_membership",       test_ray_glass_membership(segments, prism)))
    results.append(("ray_edge_crossing",          test_ray_edge_crossing(segments, prism)))
    results.append(("query_rays format",          test_query_rays_result_format()))
    results.append(("query_rays JOIN",            test_query_rays_join()))
    results.append(("Reject INSERT",              test_reject_insert()))
    results.append(("Reject DROP",                test_reject_drop()))
    results.append(("Reject multi-statement",     test_reject_multi_statement()))
    results.append(("describe_schema",            test_describe_schema()))
    results.append(("describe_schema metadata",   test_describe_schema_column_metadata()))
    results.append(("clear_context closes DB",    test_clear_context_closes_db()))

    # Re-set context for registry test (since test 16 cleared it)
    set_context(scene, segments)
    results.append(("Tool registry",              test_tool_registry()))

    # --- Summary ---
    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print("=" * 70)

    if passed == total:
        print("\nAll Phase 1 agentic DB tools verified successfully!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
