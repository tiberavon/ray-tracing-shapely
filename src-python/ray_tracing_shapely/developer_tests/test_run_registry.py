"""
===============================================================================
RUN PERSISTENCE / COMPARISON TESTS -- Nonimaging Optics Phase 1, Steps 4-5
===============================================================================
Tests analysis.run_registry's minimal Layer 1 (persist_run_artifacts) and
Layer 3 (compare_runs) slice: params.json/rays.sqlite/summary.json only, no
graph.json/signature_spectrum.json yet. Exercised against a real DTIRCPrism
n=1.5 vs n=1.8 sweep (15_p2_bidirectional_ray_tracing_rational.md §7.1) -- the
point of building the fixture before the persistence machinery.

Run with:
    python developer_tests/test_run_registry.py
Or with pytest:
    pytest developer_tests/test_run_registry.py -v
===============================================================================
"""

import json
import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def _build_and_run_dtirc(n_prism, ray_density=8):
    """Build a DTIRCPrism scene, trace it, return (scene, SimulationResult)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    scene.ray_density = ray_density

    prism = DTIRCPrism(scene, theta_deg=10.0, n=n_prism, size=30.0, position=(0, 0))
    prism.name = 'dtirc'
    scene.add_object(prism)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 60}
    source.p2 = {'x': 0, 'y': 40}
    source.emis_angle = 40.0
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    sim = Simulator(scene, max_rays=5000)
    result = sim.run_with_result(name=f'dtirc_n{n_prism}')
    return scene, result


def test_persist_run_artifacts_writes_expected_files():
    """persist_run_artifacts writes manifest/params/rays.sqlite/summary and
    they round-trip correctly."""
    from ray_tracing_shapely.analysis.run_registry import persist_run_artifacts

    scene, result = _build_and_run_dtirc(n_prism=1.5)

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        physical_params = {'n_prism': 1.5, 'theta_deg': 10.0}
        numerical_params = {'ray_density': scene.ray_density, 'wall_segments': 16}

        run_dir = persist_run_artifacts(
            scene, result,
            out_dir=out_dir, design_id='dtirc', run_id='n1.5',
            physical_params=physical_params, numerical_params=numerical_params,
        )

        assert run_dir == out_dir / 'dtirc' / 'n1.5'
        assert (run_dir / 'params.json').exists()
        assert (run_dir / 'rays.sqlite').exists()
        assert (run_dir / 'summary.json').exists()
        assert (out_dir / 'manifest.jsonl').exists()

        params = json.loads((run_dir / 'params.json').read_text())
        assert params['physical_params'] == physical_params
        assert params['numerical_params'] == numerical_params

        summary = json.loads((run_dir / 'summary.json').read_text())
        assert summary['segment_count'] == result.segment_count
        assert summary['processed_ray_count'] == result.processed_ray_count
        assert 'tir' in summary and 'grazing' in summary and 'wavelength' in summary

        manifest_rows = [json.loads(l) for l in (out_dir / 'manifest.jsonl').read_text().splitlines()]
        assert any(r['design_id'] == 'dtirc' and r['run_id'] == 'n1.5' for r in manifest_rows)

        # rays.sqlite is a real, queryable, file-backed database.
        import sqlite3
        conn = sqlite3.connect(str(run_dir / 'rays.sqlite'))
        count = conn.execute('SELECT COUNT(*) FROM rays').fetchone()[0]
        conn.close()
        assert count == len(result.segments)

    print("  PASS: persist_run_artifacts writes and round-trips all expected files")
    return True


def test_persist_run_artifacts_manifest_appends_across_runs():
    """Two persisted runs both show up in one manifest.jsonl (append-only)."""
    from ray_tracing_shapely.analysis.run_registry import persist_run_artifacts

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        for n_prism, run_id in [(1.5, 'n1.5'), (1.8, 'n1.8')]:
            scene, result = _build_and_run_dtirc(n_prism=n_prism)
            persist_run_artifacts(
                scene, result, out_dir=out_dir, design_id='dtirc', run_id=run_id,
                physical_params={'n_prism': n_prism}, numerical_params={},
            )

        rows = [json.loads(l) for l in (out_dir / 'manifest.jsonl').read_text().splitlines()]
        run_ids = {r['run_id'] for r in rows}
        assert run_ids == {'n1.5', 'n1.8'}
    print("  PASS: manifest.jsonl accumulates rows across separate persist calls")
    return True


def test_compare_runs_n15_vs_n18():
    """compare_runs reads two persisted DTIRCPrism runs' summaries, no live
    context / kernel involved -- the actual n=1.5 vs n=1.8 demo from
    15_p2_bidirectional_ray_tracing_rational.md §7.1."""
    from ray_tracing_shapely.analysis.run_registry import persist_run_artifacts, compare_runs

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        for n_prism, run_id in [(1.5, 'n1.5'), (1.8, 'n1.8')]:
            scene, result = _build_and_run_dtirc(n_prism=n_prism)
            persist_run_artifacts(
                scene, result, out_dir=out_dir, design_id='dtirc', run_id=run_id,
                physical_params={'n_prism': n_prism, 'theta_deg': 10.0}, numerical_params={},
            )

        diff = compare_runs('dtirc', 'n1.5', 'dtirc', 'n1.8', out_dir=out_dir)

        assert diff['params_a']['physical_params']['n_prism'] == 1.5
        assert diff['params_b']['physical_params']['n_prism'] == 1.8
        assert 'tir' in diff['summary_a'] and 'tir' in diff['summary_b']
        # A different refractive index at the same acceptance angle must
        # change the TIR/refract mix at the walls -- the comparison should
        # be able to see *some* real difference, not just echo identical data.
        assert diff['summary_a'] != diff['summary_b']
    print("  PASS: compare_runs diffs two persisted runs with zero live context")
    return True


def test_compare_runs_missing_run_raises():
    """compare_runs raises FileNotFoundError for a run that was never persisted."""
    from ray_tracing_shapely.analysis.run_registry import compare_runs

    with tempfile.TemporaryDirectory() as tmp:
        try:
            compare_runs('nope', 'nope', 'nope', 'nope', out_dir=Path(tmp))
            raise AssertionError("expected FileNotFoundError")
        except FileNotFoundError:
            pass
    print("  PASS: compare_runs raises FileNotFoundError for a missing run")
    return True


def run_all_tests():
    tests = [
        ("persist_run_artifacts writes expected files", test_persist_run_artifacts_writes_expected_files),
        ("manifest.jsonl appends across runs", test_persist_run_artifacts_manifest_appends_across_runs),
        ("compare_runs n=1.5 vs n=1.8", test_compare_runs_n15_vs_n18),
        ("compare_runs missing run raises", test_compare_runs_missing_run_raises),
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
